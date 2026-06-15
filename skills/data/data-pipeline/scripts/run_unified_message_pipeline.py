"""
Unified Message Pipeline — auto-detects portfolio vs trade format, routes to appropriate transformer.

Usage:
    python3 run_unified_message_pipeline.py --raw "<message text>" --date 2026-05-07
    python3 run_unified_message_pipeline.py --input data.csv --date 2026-05-07
    python3 run_unified_message_pipeline.py --raw "<message text>" --date 2026-05-07 --dry-run
"""
import argparse
import asyncio
import io
import logging
import sys
from datetime import datetime
from pathlib import Path

_scripts = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts))

from pandas import DataFrame, read_csv

from transformers.portfolio_excel_transformer import PortfolioExcelTransformer
from transformers.trade_excel_transformer import TradeExcelTransformer
from transformers.a_share_name_corrector import AUDIT_ATTR
from transformers.asset_identity_review import (
    apply_asset_identity_review,
    build_review_summary,
    filter_pending_normalized_records,
    high_risk_asset_name_issues,
    save_pending_review,
    split_review_rows,
)
from transformers.image_portfolio_normalizer import normalize_all as normalize_portfolio
from transformers.trade_normalizer import normalize_all as normalize_trade
from validators.trade_validator import validate_trade, ValidationResult
from validators.portfolio_validator import validate_position, validate_nav, validate_basic_info
from loaders.mongodb_loader import PortfolioMongoLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# Standard columns for portfolio
PORTFOLIO_COLS = {"截止日期", "产品名称", "产品代码", "Wind代码", "资产名称", "持仓比例", "数量", "市值(本币)", "最新净值", "最新份额", "最新规模"}
# Standard columns for trade
TRADE_COLS = {"日期", "产品代码", "产品名称", "Wind代码", "资产名称", "变化比例", "变化金额", "方向"}


def detect_format(df) -> str:
    """Detect format based on column names. Returns 'trade' or 'portfolio'."""
    cols = set(df.columns)
    if {"变化比例", "变化金额", "方向"} & cols:
        return "trade"
    return "portfolio"


def parse_text_to_df(text: str):
    """Parse raw text into DataFrame, auto-detecting separator."""
    text = text.strip()
    if not text:
        raise ValueError("输入文本为空")

    sep = "\t" if "\t" in text else ","
    df = read_csv(io.StringIO(text), sep=sep, header=0, dtype=str, keep_default_na=False)
    df = df.dropna(how="all")
    df.columns = [c.strip() for c in df.columns]
    return df


def save_raw_txt(raw_text: str, date_str: str, source_root: Path, prefix: str, timestamp: str) -> Path:
    """Save raw message text to {date}/message/ directory."""
    save_dir = source_root / date_str / "message"
    save_dir.mkdir(parents=True, exist_ok=True)
    txt_path = save_dir / f"{prefix}_{timestamp}.txt"
    counter = 1
    while txt_path.exists():
        txt_path = save_dir / f"{prefix}_{timestamp}_{counter:02d}.txt"
        counter += 1
    txt_path.write_text(raw_text, encoding="utf-8")
    return txt_path


def normalize_percent_columns(df: DataFrame) -> DataFrame:
    """Convert percentage strings in ratio columns to decimals.
    
    Handles 持仓比例, 变化比例 columns: '9.44%' -> 0.0944
    """
    df = df.copy()
    for col in ["持仓比例", "变化比例"]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: (float(str(x).replace("%", "").replace("％", "")) / 100)
                if isinstance(x, str) and ("%" in x or "％" in x)
                else x
            )
    return df


def save_excel(df, date_str: str, source_root: Path, prefix: str, timestamp: str) -> Path:
    """Save DataFrame to Excel at {date}/message/ directory."""
    save_dir = source_root / date_str / "message"
    save_dir.mkdir(parents=True, exist_ok=True)
    excel_path = save_dir / f"{prefix}_{timestamp}.xlsx"
    counter = 1
    while excel_path.exists():
        excel_path = save_dir / f"{prefix}_{timestamp}_{counter:02d}.xlsx"
        counter += 1
    df_normalized = normalize_percent_columns(df)
    df_normalized.to_excel(excel_path, index=False, sheet_name="Sheet1")
    return excel_path


async def run_pipeline(raw_text: str, date_str: str, source_root: Path, folder_date: str = None, dry_run: bool = False) -> dict:
    """Full pipeline: text → parse → detect format → transform → validate → MongoDB.
    
    Args:
        date_str: Data date from spreadsheet content (used for MongoDB records)
        folder_date: System date when message arrived (used for folder path). Defaults to date_str.
    """
    # Folder date = system date (when message arrived), not data date
    if folder_date is None:
        folder_date = date_str

    logger.info(f"[Step1] Parsing text ({len(raw_text)} chars)")
    df = parse_text_to_df(raw_text)
    logger.info(f"[Step1] Parsed {len(df)} rows, columns: {list(df.columns)}")

    fmt = detect_format(df)
    logger.info(f"[Step1] Detected format: {fmt}")
    # Fill 截止日期 from date_str if missing
    if fmt == "portfolio" and "截止日期" not in df.columns:
        df["截止日期"] = date_str
        logger.info(f"[Step1] Added 截止日期 = {date_str}")
    df = apply_asset_identity_review(df)
    asset_name_issues = high_risk_asset_name_issues(df)
    if asset_name_issues:
        logger.warning("[Step1] Pending asset identity review: %s", asset_name_issues)

    prefix = "trade" if fmt == "trade" else "portfolio"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Archive to folder_date (system date), not data date
    txt_path = save_raw_txt(raw_text, folder_date, source_root, prefix, timestamp)
    excel_path = save_excel(df, folder_date, source_root, prefix, timestamp)
    logger.info(f"[Step1] Saved: {txt_path}, {excel_path}")
    accepted_df, pending_df = split_review_rows(df)
    pending = save_pending_review(
        pending_df=pending_df,
        audit=asset_name_issues,
        source_root=source_root,
        folder_date=folder_date,
        prefix=prefix,
        timestamp=timestamp,
        fmt=fmt,
        source_path=str(txt_path),
        excel_path=str(excel_path),
    )
    review = build_review_summary(
        total_rows=len(df),
        accepted_rows=len(accepted_df),
        pending_rows=len(pending_df),
        audit=df.attrs.get(AUDIT_ATTR, []),
        pending=pending,
    )

    if fmt == "trade":
        # --- Trade Pipeline ---
        transformer = TradeExcelTransformer()
        nested = transformer.transform([{"df": df, "source": "message"}])
        if not nested or not nested[0].get("daily_data"):
            raise ValueError("No daily_data after transform")
        daily_data = nested[0]["daily_data"][0]
        normalized = normalize_trade(daily_data)
        normalized = filter_pending_normalized_records(normalized, pending_df, "trade")
        records = normalized.get("trade", [])
        logger.info(f"[Step2] Trade records: {len(records)}")

        if not records:
            return {
                "status": "pending_review" if pending else "failed",
                "rows": 0,
                "format": "trade",
                "trade": 0,
                "txt": str(txt_path),
                "excel": str(excel_path),
                "review": review,
                "pending": pending,
                "validation": {"valid": True},
                "mongodb": {"trade": 0},
            }

        vr = validate_trade(records)
        if vr.has_errors:
            logger.error(f"[Step3] Validation errors: {vr.errors}")
            raise ValueError(f"Validation failed")
        if vr.has_warnings:
            for w in vr.warnings:
                logger.warning(f"[Step3] Validation warning: {w}")

        if dry_run:
            return {
                "status": "dry_run",
                "rows": len(records),
                "format": "trade",
                "dry_run": True,
                "review": review,
                "pending": pending,
            }

        loader = PortfolioMongoLoader()
        result = loader.load_trade({"trade": records})
        logger.info(f"[Step4] MongoDB trade: {result.get('trade', 0)}")
        return {
            "status": "partial_success" if pending else "success",
            "rows": len(records),
            "format": "trade",
            "trade": result.get("trade", 0),
            "txt": str(txt_path),
            "excel": str(excel_path),
            "review": review,
            "pending": pending,
            "validation": {"valid": True},
            "mongodb": result,
        }

    else:
        # --- Portfolio Pipeline ---
        transformer = PortfolioExcelTransformer()
        nested = transformer.transform([{"df": df, "source": "message"}])
        normalized = normalize_portfolio(nested[0])
        normalized = filter_pending_normalized_records(normalized, pending_df, "portfolio")
        position_records = normalized.get("position", [])
        logger.info(f"[Step2] Position records: {len(position_records)}")
        if not position_records and pending:
            return {
                "status": "pending_review",
                "rows": 0,
                "format": "portfolio",
                "basic_info": 0,
                "nav": 0,
                "position": 0,
                "txt": str(txt_path),
                "excel": str(excel_path),
                "review": review,
                "pending": pending,
                "validation": {"valid": True},
                "mongodb": {"basic_info": 0, "nav": 0, "position": 0},
            }

        vr_pos = validate_position(position_records)
        vr_basic = validate_basic_info(normalized.get("basic_info", []))
        vr_nav = validate_nav(normalized.get("nav", []))
        merged = ValidationResult()
        merged.merge(vr_pos)
        merged.merge(vr_basic)
        merged.merge(vr_nav)

        if merged.has_errors:
            logger.error(f"[Step3] Validation errors: {merged.errors}")
            raise ValueError(f"Validation failed")
        if merged.has_warnings:
            for w in merged.warnings:
                logger.warning(f"[Step3] Validation warning: {w}")

        if dry_run:
            return {
                "status": "dry_run",
                "rows": len(position_records),
                "format": "portfolio",
                "dry_run": True,
                "review": review,
                "pending": pending,
            }

        loader = PortfolioMongoLoader()
        result = loader.load_all(normalized)
        logger.info(f"[Step4] MongoDB: basic={result.get('basic_info', 0)}, nav={result.get('nav', 0)}, position={result.get('position', 0)}")
        return {
            "status": "partial_success" if pending else "success",
            "rows": len(position_records),
            "format": "portfolio",
            "basic_info": result.get("basic_info", 0),
            "nav": result.get("nav", 0),
            "position": result.get("position", 0),
            "txt": str(txt_path),
            "excel": str(excel_path),
            "review": review,
            "pending": pending,
            "validation": {"valid": True},
            "mongodb": result,
        }


def main():
    parser = argparse.ArgumentParser(description="Unified Message Pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--raw", help="Raw message text")
    group.add_argument("--input", help="Input CSV file path")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--dry-run", action="store_true", help="Skip MongoDB write")
    args = parser.parse_args()

    raw_text = Path(args.input).read_text() if args.input else args.raw
    # Folder date is always system date (when the message arrived)
    folder_date = datetime.now().strftime("%Y-%m-%d")
    source_root = Path(__file__).resolve().parents[4] / "skills" / "data" / "source" / "smart-money"
    result = asyncio.run(run_pipeline(raw_text, args.date, source_root, folder_date=folder_date, dry_run=args.dry_run))
    logger.info(f"[Done] {result}")


if __name__ == "__main__":
    main()
