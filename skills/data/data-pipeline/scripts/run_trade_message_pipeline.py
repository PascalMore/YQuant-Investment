"""
Trade Message Pipeline — Entry point for parsing trade data from text/CSV messages.

Usage:
    python3 run_trade_message_pipeline.py --raw "<message text>" --date 2026-05-07
    python3 run_trade_message_pipeline.py --input portfolio_trades.csv --date 2026-05-07
    python3 run_trade_message_pipeline.py --input portfolio_trades.csv --date 2026-05-07 --dry-run
"""
import argparse
import asyncio
import io
import logging
import sys
from pathlib import Path

# Add scripts/ to path for imports
_scripts = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts))

from pandas import read_csv

# Pipeline components
from transformers.trade_excel_transformer import TradeExcelTransformer
from transformers.trade_normalizer import normalize_all
from validators.trade_validator import validate_trade
from loaders.mongodb_loader import PortfolioMongoLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column aliases for trade data
# ---------------------------------------------------------------------------
STANDARD_COLUMNS = ["日期", "产品代码", "产品名称", "Wind代码", "资产名称", "变化比例", "变化金额", "方向"]

COLUMN_ALIASES = {
    "日期": ["日期", "date", "交易日期"],
    "产品代码": ["产品代码", "代码", "code"],
    "产品名称": ["产品名称", "产品", "name"],
    "Wind代码": ["Wind代码", "wind_code", "wind", "Wind"],
    "资产名称": ["资产名称", "资产", "股票名称", "标的"],
    "变化比例": ["变化比例", "比例", "ratio", "变化率"],
    "变化金额": ["变化金额", "金额", "amount"],
    "方向": ["方向", "买卖方向", "direction", "操作"],
}


def detect_separator(text: str) -> str:
    """Detect separator: comma, tab, or pipe."""
    lines = text.strip().splitlines()
    if not lines:
        return "\t"
    first_line = lines[0]
    if "\t" in first_line:
        return "\t"
    if "," in first_line:
        return ","
    if "|" in first_line:
        return "|"
    return "fixed"


def normalize_column(col: str) -> str | None:
    """Normalize column name to standard using COLUMN_ALIASES."""
    col_clean = col.strip()
    for std_name, aliases in COLUMN_ALIASES.items():
        if col_clean in aliases or col_clean == std_name:
            return std_name
    return None


def parse_text_to_df(text: str) -> "DataFrame":
    """Parse raw text into a pandas DataFrame."""
    text = text.strip()
    if not text:
        raise ValueError("输入文本为空")

    sep = detect_separator(text)

    if sep != "fixed":
        df = read_csv(
            io.StringIO(text),
            sep=sep,
            header=0,
            dtype=str,
            keep_default_na=False,
        )
        df = df.dropna(how="all")
        df = df.rename(columns={c: c.strip() for c in df.columns})
    else:
        raise ValueError("固定宽度格式暂不支持，请使用 Tab 或逗号分隔")

    # Column name normalization
    renamed = {}
    for col in df.columns:
        std = normalize_column(col)
        if std:
            renamed[col] = std
    df = df.rename(columns=renamed)

    #补全标准列
    for col in STANDARD_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    return df


async def run_pipeline(
    raw_text: str,
    date_str: str,
    dry_run: bool = False,
) -> dict:
    """
    Parse trade text data → normalize → validate → MongoDB.
    """
    logger.info(f"[Step1] Parse text ({len(raw_text)} chars)")

    # Step 1: Parse text → DataFrame
    df = parse_text_to_df(raw_text)
    logger.info(f"[Step1] Parsed {len(df)} rows, columns: {list(df.columns)}")

    # Override date column with date_str if data doesn't contain date info
    if "日期" not in df.columns or df["日期"].isna().all():
        df["日期"] = date_str
    else:
        df["日期"] = df["日期"].fillna(date_str)

    # Step 2: Transform DataFrame → nested JSON → normalized records
    transformer = TradeExcelTransformer()
    nested = transformer.transform([{"df": df, "source": "message"}])

    # Extract first daily_data entry for normalize_all
    if not nested or not nested[0].get("daily_data"):
        raise ValueError("No daily_data after transform")
    daily_data = nested[0]["daily_data"][0]

    # Build proper structure for normalize_all (it expects the daily_data dict)
    normalized = normalize_all(daily_data)
    trade_records = normalized.get("trade", [])
    logger.info(f"[Step2] Normalized: {len(trade_records)} trade records")

    if not trade_records:
        raise ValueError("No trade records after normalization")

    # Step 3: Validate
    vr = validate_trade(trade_records)
    if vr.has_errors:
        logger.error(f"[Step3] Validation errors: {vr.errors}")
        raise ValueError(f"Validation failed: {'; '.join(vr.errors)}")

    if vr.has_warnings:
        for w in vr.warnings:
            logger.warning(f"[Step3] Validation warning: {w}")

    if dry_run:
        logger.info("[Step3] Dry-run mode, skipping MongoDB")
        return {"rows": len(trade_records), "dry_run": True, "validation": {"valid": True}}

    # Step 4: MongoDB
    loader = PortfolioMongoLoader()
    result = loader.load_trade({"trade": trade_records})

    return {
        "rows": len(trade_records),
        "trade": result.get("trade", 0),
        "validation": {"valid": True, "errors": vr.errors, "warnings": vr.warnings},
        "mongodb": result,
    }


def main():
    parser = argparse.ArgumentParser(description="Trade Message Pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--raw", help="Raw trade text message")
    group.add_argument("--input", help="Input CSV file path")
    parser.add_argument("--date", default="", help="Trade date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Skip MongoDB write")
    args = parser.parse_args()

    if args.input:
        raw_text = Path(args.input).read_text()
    else:
        raw_text = args.raw

    if not args.date:
        raise ValueError("--date is required")

    result = asyncio.run(run_pipeline(raw_text, args.date, dry_run=args.dry_run))
    logger.info(f"[Done] Result: {result}")


if __name__ == "__main__":
    main()
