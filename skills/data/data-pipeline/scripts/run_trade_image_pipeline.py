"""
Trade Image Pipeline — Entry point for parsing trade data from image files.

Usage:
    python3 run_trade_image_pipeline.py --image path/to/image.jpg --date 2026-05-07
    python3 run_trade_image_pipeline.py --image path/to/image.jpg --date 2026-05-07 --dry-run
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
from openpyxl import load_workbook

from extractors.minimax_image_extractor import MiniMaxImageExtractor
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


def save_excel(df: pd.DataFrame, date_str: str, source_root: Path, base_name: str) -> Path:
    """Save DataFrame to Excel, archiving to source/smart-money/{date}/image/."""
    image_dir = source_root / date_str / "image"
    image_dir.mkdir(parents=True, exist_ok=True)
    excel_path = image_dir / f"{base_name}.xlsx"
    counter = 1
    while excel_path.exists():
        excel_path = image_dir / f"{base_name}_{counter:02d}.xlsx"
        counter += 1
    df.to_excel(excel_path, index=False, sheet_name="Sheet1")
    return excel_path


def archive_image(image_path: Path, date_str: str, source_root: Path) -> Path:
    """Archive original image to source/smart-money/{date}/image/."""
    image_dir = source_root / date_str / "image"
    image_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"trade_{timestamp}"
    new_path = image_dir / f"{base_name}{image_path.suffix}"
    counter = 1
    while new_path.exists():
        new_path = image_dir / f"{base_name}_{counter:02d}{image_path.suffix}"
        counter += 1
    shutil.copy2(str(image_path), str(new_path))
    return new_path


async def run_pipeline(
    image_path: str,
    date_str: str,
    source_root: Path,
    dry_run: bool = False,
) -> dict:
    """Full pipeline: Image → MiniMax OCR → Excel → Transform → Validate → MongoDB."""
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Step 1: MiniMax OCR Image → DataFrame
    logger.info(f"[Step1] Starting OCR: {image_path}")
    extractor = MiniMaxImageExtractor()
    records = await extractor.extract(str(image_path))
    if not records:
        raise ValueError("OCR 未提取到数据")
    df = records[0]["df"]
    logger.info(f"[Step1] OCR done: {len(df)} rows")

    # Step 1b: Archive image + save Excel
    archived = archive_image(image_path, date_str, source_root)
    base_name = archived.stem
    excel_path = save_excel(df, date_str, source_root, base_name)
    logger.info(f"[Step1] Image archived: {archived}")
    logger.info(f"[Step1] Excel saved: {excel_path} ({len(df)} rows)")

    if dry_run:
        return {"image": str(archived), "excel_path": str(excel_path), "rows": len(df), "dry_run": True}

    # Step 2: Transform
    transformer = TradeExcelTransformer()
    nested = transformer.transform(records)
    if not nested or not nested[0].get("daily_data"):
        raise ValueError("No daily_data after transform")
    daily_data = nested[0]["daily_data"][0]
    normalized = normalize_all(daily_data)
    trade_records = normalized.get("trade", [])
    logger.info(f"[Step2] Normalized: {len(trade_records)} trade records")

    # Step 3: Validate
    vr = validate_trade(trade_records)
    if vr.has_errors:
        logger.error(f"[Step3] Validation errors: {vr.errors}")
        raise ValueError(f"Validation failed: {'; '.join(vr.errors)}")
    if vr.has_warnings:
        for w in vr.warnings:
            logger.warning(f"[Step3] Validation warning: {w}")

    # Step 4: MongoDB
    loader = PortfolioMongoLoader()
    result = loader.load_trade({"trade": trade_records})
    logger.info(f"[Step4] MongoDB: trade={result.get('trade', 0)}")

    return {
        "image": str(archived),
        "excel_path": str(excel_path),
        "rows": len(trade_records),
        "trade": result.get("trade", 0),
        "validation": {"valid": True, "errors": vr.errors, "warnings": vr.warnings},
        "mongodb": result,
    }


def main():
    parser = argparse.ArgumentParser(description="Trade Image Pipeline")
    parser.add_argument("--image", required=True, help="Path to image file")
    parser.add_argument("--date", required=True, help="Trade date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Skip MongoDB write")
    args = parser.parse_args()

    source_root = Path(__file__).resolve().parents[4] / "skills" / "data" / "source" / "smart-money"
    result = asyncio.run(run_pipeline(args.image, args.date, source_root, dry_run=args.dry_run))
    logger.info(f"[Done] Result: {result}")


if __name__ == "__main__":
    main()
