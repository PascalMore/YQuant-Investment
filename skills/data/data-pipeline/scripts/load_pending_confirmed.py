"""
Load confirmed pending items from pending CSV into MongoDB.

This function is called AFTER the user confirms the pending CSV correction.
It reads the pending CSV, maps to standard pipeline schema, and upserts to MongoDB.

Standard schema (MUST use these exact field names):
    position_date   ← 截止日期
    product_code    ← 产品代码
    asset_wind_code ← Wind代码
    asset_name      ← 资产名称 (OCR原名，已确认)
    holding_ratio   ← 持仓比例
    shares          ← 数量
    market_value    ← 市值(本币)
    updated_at      ← now

No master_asset_name, name_review_status, name_review_reason, review_resolved_at, etc.

CLI usage:
    # Single file
    python3 load_pending_confirmed.py --csv path/to/pending.csv

    # Batch: all pending CSVs for a date
    python3 load_pending_confirmed.py --date 2026-06-17

    # Name override
    python3 load_pending_confirmed.py --csv pending.csv --name-mapping '{"688847.SH": "华虹半导体"}'

    # Dry run
    python3 load_pending_confirmed.py --csv pending.csv --dry-run
"""
import glob
import json as json_lib
import sys
from datetime import datetime, timezone
from pathlib import Path

_scripts = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts))

import pandas as pd
from loaders.mongodb_loader import PortfolioMongoLoader

logger_name = "load_pending_confirmed"
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(logger_name)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Core load functions
# ---------------------------------------------------------------------------

def _detect_format(headers: list[str]) -> str:
    """Detect 'portfolio' or 'trade' from CSV headers."""
    cols = set(headers)
    if {"变化比例", "变化金额", "方向"} & cols:
        return "trade"
    return "portfolio"


def _first_existing_column(cols: set[str], candidates: tuple[str, ...]) -> str | None:
    """Return the first available column name from candidates."""
    return next((col for col in candidates if col in cols), None)


def load_pending_positions(pending_csv_path: str, name_mapping: dict | None = None) -> dict:
    """
    Load confirmed pending position records from pending CSV.

    Args:
        pending_csv_path: Path to the pending CSV file.
        name_mapping: Optional dict {wind_code: confirmed_name} to override asset names.

    Returns:
        dict with "loaded" count and "errors" list.
    """
    path = Path(pending_csv_path)
    if not path.exists():
        return {"loaded": 0, "errors": [f"File not found: {pending_csv_path}"]}

    df = pd.read_csv(path, dtype=str).fillna("")

    pending_statuses = {"pending_review", "pending", "review"}
    df_confirmed = df[
        ~df["名称复核状态"].str.lower().isin(pending_statuses)
        & df["Wind代码"].str.strip().ne("")
        & df["产品代码"].str.strip().ne("")
        & df["截止日期"].str.strip().ne("")
    ]

    records = []
    errors = []
    now = datetime.now()

    for idx, row in df_confirmed.iterrows():
        try:
            code = row["Wind代码"].strip()
            asset_name = row["资产名称"].strip()
            # Apply user-confirmed name mapping if provided
            if name_mapping and code in name_mapping:
                asset_name = name_mapping[code]
            records.append({
                "position_date": str(row["截止日期"].strip()),
                "product_code": row["产品代码"].strip(),
                "asset_wind_code": code,
                "asset_name": asset_name,
                "holding_ratio": _parse_pct(row["持仓比例"]),
                "shares": _parse_num(row["数量"]),
                "market_value": _parse_num(row["市值(本币)"]),
                "updated_at": now,
            })
        except Exception as e:
            errors.append(f"Row {idx}: {e}")

    if not records:
        return {"loaded": 0, "errors": errors or ["No valid records to load"]}

    loader = PortfolioMongoLoader()
    loaded = loader.upsert_position(records)

    return {"loaded": loaded, "errors": errors, "records": len(records)}


def load_pending_trades(pending_csv_path: str, name_mapping: dict | None = None) -> dict:
    """
    Load confirmed pending trade records from pending CSV.

    Args:
        pending_csv_path: Path to the pending CSV file.
        name_mapping: Optional dict {wind_code: confirmed_name} to override asset names.

    Returns:
        dict with "loaded" count and "errors" list.
    """
    path = Path(pending_csv_path)
    if not path.exists():
        return {"loaded": 0, "errors": [f"File not found: {pending_csv_path}"]}

    df = pd.read_csv(path, dtype=str).fillna("")
    cols = set(df.columns)

    date_col = _first_existing_column(cols, ("日期", "截止日期"))
    ratio_col = _first_existing_column(cols, ("变化比例", "持仓比例"))
    required_cols = ["名称复核状态", "Wind代码", "产品代码", "资产名称", "变化金额", "方向"]
    missing = [col for col in required_cols if col not in cols]
    if date_col is None:
        missing.append("日期/截止日期")
    if ratio_col is None:
        missing.append("变化比例/持仓比例")
    if missing:
        return {"loaded": 0, "errors": [f"Missing required trade columns: {', '.join(missing)}"]}

    pending_statuses = {"pending_review", "pending", "review"}
    df_confirmed = df[
        ~df["名称复核状态"].str.lower().isin(pending_statuses)
        & df["Wind代码"].str.strip().ne("")
        & df["产品代码"].str.strip().ne("")
        & df[date_col].str.strip().ne("")
    ]

    records = []
    errors = []
    now = datetime.now()

    for idx, row in df_confirmed.iterrows():
        try:
            code = row["Wind代码"].strip()
            asset_name = row["资产名称"].strip()
            if name_mapping and code in name_mapping:
                asset_name = name_mapping[code]
            records.append({
                "trade_date": str(row[date_col].strip()),
                "product_code": row["产品代码"].strip(),
                "asset_wind_code": code,
                "asset_name": asset_name,
                "change_ratio": _parse_pct(row[ratio_col]),
                "change_amount": _parse_num(row["变化金额"]),
                "direction": row["方向"].strip(),
                "updated_at": now,
            })
        except Exception as e:
            errors.append(f"Row {idx}: {e}")

    if not records:
        return {"loaded": 0, "errors": errors or ["No valid records to load"]}

    loader = PortfolioMongoLoader()
    loaded = loader.upsert_trade(records)

    return {"loaded": loaded, "errors": errors, "records": len(records)}


# ---------------------------------------------------------------------------
# F-010: Resolved marker — mark pending JSON as resolved after successful load
# ---------------------------------------------------------------------------

def _mark_json_resolved(csv_path: str, loaded_count: int) -> bool:
    """Update the companion JSON file status to 'resolved'.

    Returns True if JSON was found and updated, False otherwise.
    """
    csv_p = Path(csv_path)
    json_p = csv_p.with_suffix(".json")
    if not json_p.exists():
        return False

    try:
        payload = json_lib.loads(json_p.read_text(encoding="utf-8"))
        payload["status"] = "resolved"
        payload["resolved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        payload["resolved_records"] = loaded_count
        json_p.write_text(json_lib.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# F-009: Batch mode — process all pending CSVs for a given date
# ---------------------------------------------------------------------------

def load_all_pending_for_date(date_str: str, name_mapping: dict | None = None, dry_run: bool = False) -> dict:
    """Process all pending CSVs under source_root/<date>/review_pending/.

    Returns aggregate summary dict.
    """
    source_root = Path(__file__).resolve().parents[4] / "skills" / "data" / "source" / "smart-money"
    review_dir = source_root / date_str / "review_pending"
    csv_files = sorted(glob.glob(str(review_dir / "*_pending.csv")))

    if not csv_files:
        logger.info(f"No pending CSV files found in {review_dir}")
        return {"total_files": 0, "total_loaded": 0, "results": []}

    logger.info(f"Found {len(csv_files)} pending CSV file(s) for {date_str}")
    all_results = []
    total_loaded = 0

    for csv_path in csv_files:
        result = _process_single_csv(csv_path, name_mapping=name_mapping, dry_run=dry_run)
        all_results.append({"csv": csv_path, **result})
        total_loaded += result.get("loaded", 0)

    return {"total_files": len(csv_files), "total_loaded": total_loaded, "results": all_results}


def _process_single_csv(csv_path: str, name_mapping: dict | None = None, dry_run: bool = False) -> dict:
    """Process a single pending CSV: detect format, load, mark resolved."""
    # Read headers to detect format
    df_check = pd.read_csv(csv_path, nrows=0, dtype=str)
    fmt = _detect_format(list(df_check.columns))

    if dry_run:
        logger.info(f"[DRY] {csv_path}: format={fmt}")
        return {"loaded": 0, "format": fmt, "dry_run": True}

    if fmt == "trade":
        result = load_pending_trades(csv_path, name_mapping=name_mapping)
    else:
        result = load_pending_positions(csv_path, name_mapping=name_mapping)

    # F-010: mark JSON as resolved
    loaded = result.get("loaded", 0)
    if loaded > 0:
        _mark_json_resolved(csv_path, loaded)
        logger.info(f"Marked resolved: {csv_path} ({loaded} records)")

    return result


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_pct(val: str) -> float | None:
    """Parse percentage string like '10.54%' to decimal 0.1054, or None if empty.

    Matches the holding_ratio convention used elsewhere in the pipeline
    (e.g. portfolio_normalizer outputs decimals, not whole-number percentages).
    """
    if not val or val.strip() == "":
        return None
    try:
        v = float(val.strip().replace("%", "").replace("％", ""))
        return v / 100 if v > 0.4 else v
    except ValueError:
        return None


def _parse_num(val: str) -> float | None:
    """Parse numeric string (possibly with commas) to float, or None if empty."""
    if not val or val.strip() == "":
        return None
    try:
        return float(val.strip().replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Load confirmed pending items into MongoDB with standard schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file
  python3 load_pending_confirmed.py --csv path/to/pending.csv

  # Batch: all pending for a date
  python3 load_pending_confirmed.py --date 2026-06-17

  # Name override
  python3 load_pending_confirmed.py --csv pending.csv --name-mapping '{"688847.SH": "华虹半导体"}'
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--csv", help="Path to a single pending CSV file")
    group.add_argument("--date", help="Process all pending CSVs for this date (YYYY-MM-DD)")
    parser.add_argument("--name-mapping", help='JSON dict of {wind_code: confirmed_name} overrides', default=None)
    parser.add_argument("--dry-run", action="store_true", help="Show what would be loaded without writing")
    args = parser.parse_args()

    # Parse name mapping
    name_mapping = None
    if args.name_mapping:
        try:
            name_mapping = json_lib.loads(args.name_mapping)
        except json_lib.JSONDecodeError as e:
            print(f"Error: invalid --name-mapping JSON: {e}")
            sys.exit(1)

    if args.date:
        # F-009: batch mode
        summary = load_all_pending_for_date(args.date, name_mapping=name_mapping, dry_run=args.dry_run)
        mode = "DRY RUN" if args.dry_run else "DONE"
        print(f"\n=== {mode}: {summary['total_files']} file(s), {summary['total_loaded']} records loaded ===")
        for r in summary["results"]:
            print(f"  {r.get('csv', '?')}: loaded={r.get('loaded', 0)}, format={r.get('format', '?')}")
    else:
        # Single file mode
        csv_path = args.csv
        df_check = pd.read_csv(csv_path, nrows=0, dtype=str)
        fmt = _detect_format(list(df_check.columns))

        if args.dry_run:
            print(f"[DRY RUN] format={fmt}, csv={csv_path}")
        else:
            if fmt == "trade":
                result = load_pending_trades(csv_path, name_mapping=name_mapping)
            else:
                result = load_pending_positions(csv_path, name_mapping=name_mapping)

            # Mark resolved
            loaded = result.get("loaded", 0)
            if loaded > 0:
                _mark_json_resolved(csv_path, loaded)

            print(f"Result: format={fmt}, loaded={loaded}, records={result.get('records', 0)}")
            if result["errors"]:
                for err in result["errors"]:
                    print(f"  ERROR: {err}")
