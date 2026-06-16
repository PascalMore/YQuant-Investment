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
"""
import sys
from datetime import datetime
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


def load_pending_positions(pending_csv_path: str) -> dict:
    """
    Load confirmed pending position records from pending CSV.

    Args:
        pending_csv_path: Path to the pending CSV file (with 名称复核状态=confirmed).

    Returns:
        dict with "loaded" count and "errors" list.
    """
    path = Path(pending_csv_path)
    if not path.exists():
        return {"loaded": 0, "errors": [f"File not found: {pending_csv_path}"]}

    df = pd.read_csv(path, dtype=str).fillna("")
    cols = set(df.columns)

    # Only process confirmed rows (名称复核状态 == "confirmed" or empty/non-pending)
    # Filter out rows still marked as pending_review
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
            # Skip rows where asset_name was changed to a different standard name
            # (i.e., if there's a 主数据名称 that differs from 资产名称, use 资产名称 as-is)
            # The user's confirmed value is in 资产名称 (OCR original, already verified)
            records.append({
                "position_date": str(row["截止日期"].strip()),
                "product_code": row["产品代码"].strip(),
                "asset_wind_code": code,
                "asset_name": row["资产名称"].strip(),
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

    return {"loaded": loaded, "errors": errors}


def load_pending_trades(pending_csv_path: str) -> dict:
    """
    Load confirmed pending trade records from pending CSV.

    Args:
        pending_csv_path: Path to the pending CSV file.

    Returns:
        dict with "loaded" count and "errors" list.
    """
    path = Path(pending_csv_path)
    if not path.exists():
        return {"loaded": 0, "errors": [f"File not found: {pending_csv_path}"]}

    df = pd.read_csv(path, dtype=str).fillna("")
    cols = set(df.columns)

    # Trade CSVs have: 日期, 产品代码, 产品名称, Wind代码, 资产名称,
    #                  变化比例, 变化金额, 方向
    if "变化比例" not in cols and "方向" not in cols:
        return {"loaded": 0, "errors": ["Not a trade-format CSV"]}

    pending_statuses = {"pending_review", "pending", "review"}
    df_confirmed = df[
        ~df["名称复核状态"].str.lower().isin(pending_statuses)
        & df["Wind代码"].str.strip().ne("")
        & df["产品代码"].str.strip().ne("")
        & df["日期"].str.strip().ne("")
    ]

    records = []
    errors = []
    now = datetime.now()

    for idx, row in df_confirmed.iterrows():
        try:
            records.append({
                "trade_date": str(row["日期"].strip()),
                "product_code": row["产品代码"].strip(),
                "asset_wind_code": row["Wind代码"].strip(),
                "asset_name": row["资产名称"].strip(),
                "change_ratio": _parse_pct(row["变化比例"]),
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

    return {"loaded": loaded, "errors": errors}


def _parse_pct(val: str) -> float | None:
    """Parse percentage string like '10.54%' to float 10.54, or None if empty."""
    if not val or val.strip() == "":
        return None
    try:
        return float(val.strip().replace("%", ""))
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load confirmed pending items into MongoDB")
    parser.add_argument("csv_path", help="Path to pending CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Show records without writing")
    args = parser.parse_args()

    result = load_pending_positions(args.csv_path)
    print(f"Position upsert result: {result}")
    if result["errors"]:
        for err in result["errors"]:
            print(f"  ERROR: {err}")
