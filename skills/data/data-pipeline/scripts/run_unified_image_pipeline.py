"""
Auto-detecting Image Pipeline — determines image type by column names, then routes to appropriate transformer.

Usage:
    python3 run_unified_image_pipeline.py --image path/to/image.jpg --date 2026-05-07
    python3 run_unified_image_pipeline.py --image path/to/image.jpg --date 2026-05-07 --dry-run
"""
import argparse
import asyncio
import logging
import re
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
from transformers.a_share_name_corrector import correct_dataframe_asset_names
from transformers.image_portfolio_normalizer import normalize_all as normalize_portfolio
from transformers.trade_normalizer import normalize_all as normalize_trade
from validators.trade_validator import validate_trade, ValidationResult
from validators.portfolio_validator import validate_position, validate_nav, validate_basic_info
from loaders.mongodb_loader import PortfolioMongoLoader
from stock_name_corrections import STOCK_NAME_CORRECTIONS

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


def standardize_asset_name(name: str) -> str:
    """Standardize stock name: remove spaces, unify full-width/half-width characters."""
    if not isinstance(name, str):
        return name
    # Remove all whitespace
    name = re.sub(r'\s+', '', name)
    # Unify full-width parentheses to half-width
    name = name.replace('（', '(').replace('）', ')')
    # Unify full-width dash to half-width dash (－ → -, — → -)
    name = name.replace('－', '-').replace('—', '-')
    # Unify full-width ASCII letters (Ｗ→W, Ｂ→B, etc.)
    name = name.translate(str.maketrans('ＷＸＹＺＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶ', 
                                       'WXYZABCDEFGHIJKLMNOPQRSTUV'))
    return name


def standardize_df_asset_names(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize asset_name column in DataFrame if present."""
    df = df.copy()
    if '资产名称' in df.columns:
        df['资产名称'] = df['资产名称'].apply(standardize_asset_name)
    return df


def correct_stock_names(df: pd.DataFrame) -> pd.DataFrame:
    """Correct stock names using a pre-defined mapping. If code not in mapping, skip."""
    df = df.copy()
    if '资产名称' not in df.columns or 'Wind代码' not in df.columns:
        return df
    
    def correct_name(row):
        code = row.get('Wind代码', '')
        name = row.get('资产名称', '')
        if not code or not name:
            return name
        correct_name = STOCK_NAME_CORRECTIONS.get(code)
        if correct_name and name != correct_name:
            return correct_name
        return name
    
    df['资产名称'] = df.apply(correct_name, axis=1)
    return df


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


def correct_year_if_ocr_error(records: list) -> list:
    """
    Fix common OCR year errors based on OCR data itself.
    Correction triggers when:
    - OCR year > current_year (e.g., 2027+ when current is 2026) → auto-correct
    - OCR year <= current_year - 2 (e.g., 2024 when current is 2026) → auto-correct
    
    Records format: list[dict] with keys 'df' (DataFrame) and 'source_path'.
    Date fields are columns in the DataFrame, not dict keys.
    
    No dependence on --date parameter; correction is purely based on
    whether the OCR year itself is clearly erroneous relative to current year.
    """
    import re
    current_year = datetime.now().year  # e.g. 2026

    DATE_FIELDS = ['截止日期', 'date', 'nav_date', 'position_date', 'trade_date']

    def fix_df(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        """Fix year errors in DataFrame date columns. Returns (fixed_df, change_count)."""
        changes = 0
        df = df.copy()  # Don't modify original
        
        for field in DATE_FIELDS:
            if field not in df.columns:
                continue
            
            for idx in range(len(df)):
                val = df.at[idx, field]
                if pd.isna(val) or val is None:
                    continue
                
                val_str = str(val)
                m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', val_str)
                if not m:
                    m = re.match(r'^(\d{4})/(\d{2})/(\d{2})$', val_str)
                if not m:
                    continue
                
                year = int(m.group(1))
                if year > current_year:
                    # Case 1: future year — auto-correct
                    fixed = f"{current_year}-{m.group(2)}-{m.group(3)}"
                    df.at[idx, field] = fixed
                    changes += 1
                    logger.warning(
                        f"[Step1b] OCR year corrected: row={idx} field={field} {year}→{current_year} "
                        f"(original value: {val_str}, future year > current_year)"
                    )
                elif year <= current_year - 2:
                    # Case 2: past year <= current_year - 2 — auto-correct
                    fixed = f"{current_year}-{m.group(2)}-{m.group(3)}"
                    df.at[idx, field] = fixed
                    changes += 1
                    logger.warning(
                        f"[Step1b] OCR year corrected: row={idx} field={field} {year}→{current_year} "
                        f"(original value: {val_str}, past year <= current_year-2)"
                    )
        
        return df, changes

    # Process each record: records = [{'df': DataFrame, 'source_path': str}, ...]
    total_changes = 0
    for record in records:
        if 'df' not in record:
            continue
        df = record['df']
        df_fixed, changes = fix_df(df)
        record['df'] = df_fixed  # Write back corrected DataFrame
        total_changes += changes

    if total_changes:
        logger.warning(f"[Step1b] OCR year auto-corrected {total_changes} cells")
    
    return records


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
    folder_date: str = None,
    output_dir: Path = None,
    dry_run: bool = False,
) -> dict:
    """Full pipeline: Image → MiniMax OCR → Auto-detect → Transform → Validate → MongoDB.
    
    Args:
        date_str: Data date from spreadsheet content (used for OCR context and MongoDB records)
        folder_date: System date when image was received (used for folder path). Defaults to date_str.
        output_dir: Directory for raw JSON debug files. Defaults to source_root/folder_date/image.
    """
    # Folder date = system date (when image arrived), not data date
    if folder_date is None:
        folder_date = date_str

    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # output_dir for raw JSON = folder_date (system date)
    if output_dir is None:
        output_dir = source_root / folder_date / "image"

    # Step 1: MiniMax OCR
    logger.info(f"[Step1] OCR: {image_path}")
    extractor = MiniMaxImageExtractor(output_dir=str(output_dir), date_str=date_str)
    records = await extractor.extract(str(image_path))
    if not records:
        raise ValueError("OCR extracted no data")
    df = records[0]["df"]
    logger.info(f"[Step1] Parsed: {len(df)} rows, columns: {list(df.columns)}")

    # Step 1b: Fix OCR year errors (e.g., 2099 or 2024 misread for 2026)
    records = correct_year_if_ocr_error(records)
    df = records[0]["df"]

    # Step 1c: Standardize asset names (remove spaces, unify full/half-width chars)
    df = standardize_df_asset_names(df)
    records[0]["df"] = df

    # Step 1d: Correct stock names via pre-defined mapping
    df = correct_stock_names(df)
    records[0]["df"] = df

    # Step 1e: Correct A-share names via stock_basic_info master data before DB load
    df = correct_dataframe_asset_names(df)
    records[0]["df"] = df

    # Step 1f: Detect format
    fmt = detect_format(df)
    logger.info(f"[Step1] Detected format: {fmt}")
    prefix = "trade" if fmt == "trade" else "portfolio"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{prefix}_{timestamp}"
    # Archive original image to folder_date (system date), not data date
    new_path = archive_image(image_path, folder_date, source_root, prefix, timestamp)
    excel_path = save_excel(df, folder_date, source_root, base_name, "image")
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
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Data date (YYYY-MM-DD), i.e. the date in the spreadsheet. Used for OCR and MongoDB records.")
    parser.add_argument("--dry-run", action="store_true", help="Skip MongoDB write")
    args = parser.parse_args()


    # Folder date is always system date (when the image was received/uploaded)
    folder_date = datetime.now().strftime("%Y-%m-%d")
    source_root = Path(__file__).resolve().parents[4] / "skills" / "data" / "source" / "smart-money"
    result = asyncio.run(run_pipeline(args.image, args.date, source_root, folder_date=folder_date, dry_run=args.dry_run))
    logger.info(f"[Done] {result}")


if __name__ == "__main__":
    main()
