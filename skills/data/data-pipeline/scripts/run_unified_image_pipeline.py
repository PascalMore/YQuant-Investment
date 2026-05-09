"""
Auto-detecting Image Pipeline — determines image type by column names, then routes to appropriate transformer.

Usage:
    python3 run_unified_image_pipeline.py --image path/to/image.jpg --date 2026-05-07
    python3 run_unified_image_pipeline.py --image path/to/image.jpg --date 2026-05-07 --dry-run
"""
import argparse
import asyncio
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add scripts/ to path for imports
_scripts = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts))

import pandas as pd

from extractors.minimax_image_extractor import MiniMaxImageExtractor
from transformers.portfolio_excel_transformer import PortfolioExcelTransformer
from transformers.trade_excel_transformer import TradeExcelTransformer
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

# Column sets for detection
# Trade-unique columns (not present in portfolio format)
TRADE_UNIQUE = {"变化比例", "变化金额"}
# Portfolio-unique columns (not present in trade format)
PORTFOLIO_UNIQUE = {"持仓比例", "最新净值", "最新份额", "最新规模"}


def detect_format(df: pd.DataFrame) -> str:
    """
    Detect image format based on column names.
    Returns 'trade' if 变化比例/变化金额/方向 present, else 'portfolio'.
    """
    cols = set(df.columns)
    trade_markers = {"变化比例", "变化金额", "方向"}
    if trade_markers & cols:
        return "trade"
    return "portfolio"


def save_excel(df: pd.DataFrame, date_str: str, source_root: Path, base_name: str, subdir: str = "image") -> Path:
    """Save DataFrame to Excel at {date}/{subdir}/ directory."""
    save_dir = source_root / date_str / subdir
    save_dir.mkdir(parents=True, exist_ok=True)
    excel_path = save_dir / f"{base_name}.xlsx"
    counter = 1
    while excel_path.exists():
        excel_path = save_dir / f"{base_name}_{counter:02d}.xlsx"
        counter += 1
    df.to_excel(excel_path, index=False, sheet_name="Sheet1")
    return excel_path


def archive_image(image_path: Path, date_str: str, source_root: Path, prefix: str, timestamp: str) -> Path:
    """Archive original image to {date}/image/ directory."""
    save_dir = source_root / date_str / "image"
    save_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{prefix}_{timestamp}"
    new_path = save_dir / f"{base_name}{image_path.suffix}"
    counter = 1
    while new_path.exists():
        new_path = save_dir / f"{base_name}_{counter:02d}{image_path.suffix}"
        counter += 1
    shutil.copy2(str(image_path), str(new_path))
    return new_path


async def run_pipeline(
    image_path: str,
    date_str: str,
    source_root: Path,
    dry_run: bool = False,
) -> dict:
    """Full pipeline: Image → MiniMax OCR → Auto-detect → Transform → Validate → MongoDB."""
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Step 1: MiniMax OCR
    logger.info(f"[Step1] OCR: {image_path}")
    extractor = MiniMaxImageExtractor()
    records = await extractor.extract(str(image_path))
    if not records:
        raise ValueError("OCR extracted no data")
    df = records[0]["df"]
    logger.info(f"[Step1] Parsed: {len(df)} rows, columns: {list(df.columns)}")

    # Step 1b: Detect format
    fmt = detect_format(df)
    logger.info(f"[Step1] Detected format: {fmt}")
    prefix = "trade" if fmt == "trade" else "portfolio"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{prefix}_{timestamp}"
    # Archive original image
    new_path = archive_image(image_path, date_str, source_root, prefix, timestamp)
    excel_path = save_excel(df, date_str, source_root, base_name, "image")
    logger.info(f"[Step1] Saved: {new_path}, {excel_path}")

    if dry_run:
        return {"image": str(new_path), "excel_path": str(excel_path), "rows": len(df), "format": fmt, "dry_run": True}

    # Step 2: Transform based on format
    if fmt == "trade":
        transformer = TradeExcelTransformer()
        nested = transformer.transform(records)
        if not nested or not nested[0].get("daily_data"):
            raise ValueError("No daily_data after transform")
        daily_data = nested[0]["daily_data"][0]
        normalized = normalize_trade(daily_data)
        records_to_validate = normalized.get("trade", [])
        logger.info(f"[Step2] Trade records: {len(records_to_validate)}")

        vr = validate_trade(records_to_validate)
        if vr.has_errors:
            logger.error(f"[Step3] Validation errors: {vr.errors}")
            raise ValueError(f"Validation failed")
        if vr.has_warnings:
            for w in vr.warnings:
                logger.warning(f"[Step3] Validation warning: {w}")

        loader = PortfolioMongoLoader()
        result = loader.load_trade({"trade": records_to_validate})
        logger.info(f"[Step4] MongoDB trade: {result.get('trade', 0)}")
        return {
            "image": str(new_path),
            "excel_path": str(excel_path),
            "rows": len(records_to_validate),
            "format": fmt,
            "trade": result.get("trade", 0),
            "validation": {"valid": True},
            "mongodb": result,
        }
    else:
        transformer = PortfolioExcelTransformer()
        nested = transformer.transform(records)
        normalized = normalize_portfolio(nested[0])
        position_records = normalized.get("position", [])
        logger.info(f"[Step2] Position records: {len(position_records)}")

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

        loader = PortfolioMongoLoader()
        result = loader.load_all(normalized)
        logger.info(f"[Step4] MongoDB: basic={result.get('basic_info', 0)}, nav={result.get('nav', 0)}, position={result.get('position', 0)}")
        return {
            "image": str(new_path),
            "excel_path": str(excel_path),
            "rows": len(position_records),
            "format": fmt,
            "basic_info": result.get("basic_info", 0),
            "nav": result.get("nav", 0),
            "position": result.get("position", 0),
            "validation": {"valid": True},
            "mongodb": result,
        }


def main():
    parser = argparse.ArgumentParser(description="Unified Image Pipeline (Auto-detect portfolio vs trade)")
    parser.add_argument("--image", required=True, help="Path to image file")
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Skip MongoDB write")
    args = parser.parse_args()

    source_root = Path(__file__).parent.parent / "data" / "source" / "smart-money"
    result = asyncio.run(run_pipeline(args.image, args.date, source_root, dry_run=args.dry_run))
    logger.info(f"[Done] {result}")


if __name__ == "__main__":
    main()
