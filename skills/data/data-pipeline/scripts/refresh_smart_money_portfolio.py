#!/usr/bin/env python3
"""Refresh smart-money portfolio MongoDB collections from archived Excel files."""
from __future__ import annotations

# ⚠️ 已禁用 - 请勿执行
# 该脚本会清空原始数据 portfolio_position/trade/nav，危险！
# 如需重新运行，必须先经过人工确认。
import sys
if __name__ == "__main__":
    sys.exit('ERROR: refresh_smart_money_portfolio.py 已禁用（危险操作）。如需启用请联系管理员。')

import argparse
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pymongo import MongoClient

_SCRIPTS = Path(__file__).parent.resolve()
_WORKSPACE = _SCRIPTS.parents[3]
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_WORKSPACE))

from loaders.mongodb_loader import PortfolioMongoLoader  # noqa: E402
from transformers.a_share_name_corrector import correct_dataframe_asset_names  # noqa: E402
from transformers.image_portfolio_normalizer import normalize_all as normalize_portfolio  # noqa: E402
from transformers.portfolio_excel_transformer import PortfolioExcelTransformer  # noqa: E402
from transformers.trade_excel_transformer import TradeExcelTransformer  # noqa: E402
from transformers.trade_normalizer import normalize_all as normalize_trade  # noqa: E402
from validators.portfolio_validator import (  # noqa: E402
    ValidationResult as PortfolioValidationResult,
    validate_basic_info,
    validate_nav,
    validate_position,
)
from validators.trade_validator import validate_trade  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logging.getLogger("transformers.a_share_name_corrector").setLevel(logging.WARNING)
logging.getLogger("skills.data.data_interface.stock.stock_info_api").setLevel(logging.WARNING)

PORTFOLIO_DATE_FIELDS = {
    "portfolio_nav": "nav_date",
    "portfolio_position": "position_date",
    "portfolio_trade": "trade_date",
}


def mongo_client_from_env() -> MongoClient:
    host = os.getenv("MONGODB_HOST", "172.25.240.1")
    port = int(os.getenv("MONGODB_PORT", "27017"))
    username = os.getenv("MONGODB_USERNAME", "myq")
    password = os.getenv("MONGODB_PASSWORD", "6812345")
    uri = (
        f"mongodb://{username}:{password}@{host}:{port}/?authSource=admin"
        if username and password
        else f"mongodb://{host}:{port}/"
    )
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def excel_files(source_root: Path) -> list[Path]:
    return sorted(
        path
        for path in source_root.rglob("*.xlsx")
        if path.name.startswith(("portfolio_", "trade_"))
    )


def normalize_date(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d")
    return text[:10]


def read_excel(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=object, keep_default_na=False)
    df.columns = [str(col).strip() for col in df.columns]
    for column in ("截止日期", "日期"):
        if column in df.columns:
            df[column] = df[column].apply(normalize_date)
    return correct_dataframe_asset_names(df)


def merge_validation(results: list[PortfolioValidationResult]) -> PortfolioValidationResult:
    merged = PortfolioValidationResult()
    for result in results:
        merged.merge(result)
    return merged


def parse_portfolio_file(path: Path, start: str) -> dict[str, list[dict[str, Any]]]:
    df = read_excel(path)
    transformed = PortfolioExcelTransformer().transform([{"df": df, "source_path": str(path)}])
    normalized = normalize_portfolio(transformed[0])
    normalized["nav"] = [r for r in normalized["nav"] if normalize_date(r.get("nav_date")) >= start]
    normalized["position"] = [
        r for r in normalized["position"] if normalize_date(r.get("position_date")) >= start
    ]

    active_codes = {
        r.get("product_code")
        for bucket in (normalized["nav"], normalized["position"])
        for r in bucket
        if r.get("product_code")
    }
    normalized["basic_info"] = [
        r for r in normalized["basic_info"] if r.get("product_code") in active_codes
    ]

    validation = merge_validation(
        [
            validate_position(normalized["position"]),
            validate_nav(normalized["nav"]),
            validate_basic_info(normalized["basic_info"]),
        ]
    )
    if validation.has_errors:
        raise ValueError("; ".join(validation.errors[:8]))
    return normalized


def parse_trade_file(path: Path, start: str) -> dict[str, list[dict[str, Any]]]:
    df = read_excel(path)
    transformed = TradeExcelTransformer().transform([{"df": df, "source_path": str(path)}])
    records: list[dict[str, Any]] = []
    for daily_data in transformed[0].get("daily_data", []):
        records.extend(normalize_trade(daily_data).get("trade", []))
    records = [r for r in records if normalize_date(r.get("trade_date")) >= start]

    validation = validate_trade(records)
    if validation.has_errors:
        raise ValueError("; ".join(validation.errors[:8]))
    return {"trade": records}


def aggregate_source(source_root: Path, start: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    records = {"basic_info": [], "nav": [], "position": [], "trade": []}
    stats: dict[str, Any] = {
        "files_total": 0,
        "files_ok": 0,
        "files_failed": 0,
        "by_type": Counter(),
        "errors": [],
    }

    for path in excel_files(source_root):
        stats["files_total"] += 1
        kind = "trade" if path.name.startswith("trade_") else "portfolio"
        stats["by_type"][kind] += 1
        try:
            parsed = parse_trade_file(path, start) if kind == "trade" else parse_portfolio_file(path, start)
            for key, rows in parsed.items():
                records[key].extend(rows)
            stats["files_ok"] += 1
        except Exception as exc:
            stats["files_failed"] += 1
            stats["errors"].append({"path": str(path), "error": str(exc)})
            logger.error("[parse failed] %s: %s", path, exc)

    stats["source_records"] = {key: len(value) for key, value in records.items()}
    stats["by_type"] = dict(stats["by_type"])
    return records, stats


def clear_portfolio_since(db, start: str) -> dict[str, int]:
    deleted = {}
    deleted["portfolio_basic_info"] = db["portfolio_basic_info"].delete_many({}).deleted_count
    for collection, field in PORTFOLIO_DATE_FIELDS.items():
        deleted[collection] = db[collection].delete_many({field: {"$gte": start}}).deleted_count
    return deleted


def collection_summary(db, start: str) -> dict[str, Any]:
    summary = {}
    for collection, field in PORTFOLIO_DATE_FIELDS.items():
        summary[collection] = {
            "count_since_start": db[collection].count_documents({field: {"$gte": start}}),
            "first": db[collection].find_one(
                {field: {"$gte": start}}, sort=[(field, 1)], projection={field: 1, "_id": 0}
            ),
            "last": db[collection].find_one(sort=[(field, -1)], projection={field: 1, "_id": 0}),
            "distinct_dates_since_start": len(db[collection].distinct(field, {field: {"$gte": start}})),
        }
    summary["portfolio_basic_info"] = {"count": db["portfolio_basic_info"].count_documents({})}
    return summary


def load_records(records: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    loader = PortfolioMongoLoader()
    try:
        result = loader.load_all(
            {
                "basic_info": records["basic_info"],
                "nav": records["nav"],
                "position": records["position"],
            }
        )
        result.update(loader.load_trade({"trade": records["trade"]}))
        return result
    finally:
        loader.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-12-01")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=_WORKSPACE / "skills" / "data" / "source" / "smart-money",
    )
    parser.add_argument("--apply", action="store_true", help="Delete target range and write MongoDB")
    parser.add_argument("--allow-errors", action="store_true", help="Continue apply even if source files fail")
    args = parser.parse_args()

    records, stats = aggregate_source(args.source_root, args.start)
    print("=== Source Parse Summary ===")
    print(stats)
    if stats["files_failed"] and (args.apply and not args.allow_errors):
        raise SystemExit("Source parse has failures; re-run with --allow-errors only if this is acceptable.")
    if not args.apply:
        print("Dry run only. Re-run with --apply to refresh MongoDB.")
        return

    client = mongo_client_from_env()
    try:
        database = os.getenv("MONGODB_DATABASE", "tradingagents")
        db = client[database]
        db.client.admin.command("ping")
        before = collection_summary(db, args.start)
        deleted = clear_portfolio_since(db, args.start)
        loaded = load_records(records)
        after = collection_summary(db, args.start)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "start": args.start,
            "source": stats,
            "before": before,
            "deleted": deleted,
            "loaded": loaded,
            "after": after,
        }
        print("=== Refresh Report ===")
        print(report)
    finally:
        client.close()


if __name__ == "__main__":
    main()
