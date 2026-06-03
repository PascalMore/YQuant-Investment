#!/usr/bin/env python3
"""Clean portfolio_position.asset_name consistency for A-share positions.

Rules:
1. Group portfolio_position by asset_wind_code and asset_name.
2. Pick the most frequent name as the code's primary name.
3. Update all records for that code only when the primary name matches
   stock_basic_info's standard name.
4. Never delete data. asset_wind_code=None/empty records are reported only.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo import MongoClient, UpdateMany

_scripts = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts))

from transformers.a_share_name_corrector import load_a_share_name_map, normalize_a_share_code

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def mongo_client_from_env() -> MongoClient:
    host = os.getenv("MONGODB_HOST", "172.25.240.1")
    port = int(os.getenv("MONGODB_PORT", "27017"))
    username = os.getenv("MONGODB_USERNAME", "myq")
    password = os.getenv("MONGODB_PASSWORD", "6812345")
    if username and password:
        uri = f"mongodb://{username}:{password}@{host}:{port}/?authSource=admin"
    else:
        uri = f"mongodb://{host}:{port}/"
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def clean_name(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def name_counts_by_code(collection) -> list[dict[str, Any]]:
    pipeline = [
        {
            "$group": {
                "_id": {"code": "$asset_wind_code", "name": "$asset_name"},
                "count": {"$sum": 1},
            }
        },
        {
            "$group": {
                "_id": "$_id.code",
                "total": {"$sum": "$count"},
                "names": {"$push": {"name": "$_id.name", "count": "$count"}},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    return list(collection.aggregate(pipeline, allowDiskUse=True))


def most_common_name(names: list[dict[str, Any]]) -> tuple[str, int]:
    counts = Counter({clean_name(item.get("name")): int(item.get("count", 0)) for item in names})
    if not counts:
        return "", 0
    return counts.most_common(1)[0]


def none_code_report(collection) -> dict[str, Any]:
    query = {
        "$or": [
            {"asset_wind_code": None},
            {"asset_wind_code": {"$exists": False}},
            {"asset_wind_code": ""},
        ]
    }
    pipeline = [
        {"$match": query},
        {"$group": {"_id": "$asset_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": 1}},
    ]
    by_name = [
        {"asset_name": clean_name(row.get("_id")), "count": row["count"]}
        for row in collection.aggregate(pipeline)
    ]
    return {"count": sum(row["count"] for row in by_name), "by_name": by_name}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_plan(collection, standard_names: dict[str, str]) -> dict[str, Any]:
    eligible: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    missing_master: list[dict[str, Any]] = []
    skipped_non_a_share: list[dict[str, Any]] = []

    for group in name_counts_by_code(collection):
        raw_code = group.get("_id")
        code = normalize_a_share_code(raw_code)
        primary_name, primary_count = most_common_name(group.get("names", []))
        total = int(group.get("total", 0))

        if not code:
            continue

        standard_name = standard_names.get(code)
        base = {
            "raw_code": raw_code,
            "standard_code": code,
            "primary_name": primary_name,
            "primary_count": primary_count,
            "total": total,
            "name_variants": sorted(
                [
                    {"name": clean_name(item.get("name")), "count": int(item.get("count", 0))}
                    for item in group.get("names", [])
                ],
                key=lambda item: (-item["count"], item["name"]),
            ),
        }

        if standard_name is None:
            missing_master.append(base)
        elif primary_name == standard_name:
            eligible.append({**base, "standard_name": standard_name})
        else:
            mismatches.append({**base, "standard_name": standard_name})

    return {
        "eligible": eligible,
        "mismatches": mismatches,
        "missing_master": missing_master,
        "skipped_non_a_share": skipped_non_a_share,
        "none_code": none_code_report(collection),
    }


def apply_updates(collection, eligible: list[dict[str, Any]], batch_size: int = 500) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    matched = 0
    modified = 0

    for offset in range(0, len(eligible), batch_size):
        batch = eligible[offset : offset + batch_size]
        ops = [
            UpdateMany(
                {"asset_wind_code": item["raw_code"]},
                {"$set": {"asset_name": item["standard_name"], "updated_at": now}},
            )
            for item in batch
        ]
        if not ops:
            continue
        result = collection.bulk_write(ops, ordered=False)
        matched += result.matched_count
        modified += result.modified_count

    return {"matched": matched, "modified": modified}


def sample_validation(collection, eligible: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    samples = []
    for item in eligible[:limit]:
        variants = list(
            collection.aggregate(
                [
                    {"$match": {"asset_wind_code": item["raw_code"]}},
                    {"$group": {"_id": "$asset_name", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1, "_id": 1}},
                ]
            )
        )
        samples.append(
            {
                "asset_wind_code": item["raw_code"],
                "standard_name": item["standard_name"],
                "variants_after": [
                    {"asset_name": clean_name(row.get("_id")), "count": row["count"]} for row in variants
                ],
            }
        )
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix A-share asset_name consistency in portfolio_position")
    parser.add_argument("--apply", action="store_true", help="Write updates to MongoDB. Without this flag, only reports are generated.")
    parser.add_argument("--output-dir", type=Path, default=_scripts / "reports", help="Report output directory")
    args = parser.parse_args()

    client = mongo_client_from_env()
    try:
        database = os.getenv("MONGODB_DATABASE", "tradingagents")
        collection = client[database]["portfolio_position"]
        collection.database.client.admin.command("ping")

        standard_names = load_a_share_name_map()
        plan = build_plan(collection, standard_names)
        update_result = {"matched": 0, "modified": 0}
        if args.apply:
            update_result = apply_updates(collection, plan["eligible"])

        samples = sample_validation(collection, plan["eligible"])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        report_path = args.output_dir / f"asset_name_consistency_report_{timestamp}.json"
        mismatch_path = args.output_dir / f"asset_name_mismatches_{timestamp}.csv"

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "apply" if args.apply else "dry_run",
            "eligible_code_count": len(plan["eligible"]),
            "mismatch_code_count": len(plan["mismatches"]),
            "missing_master_code_count": len(plan["missing_master"]),
            "none_code_count": plan["none_code"]["count"],
            "planned_records_to_update": sum(item["total"] for item in plan["eligible"]),
            "update_result": update_result,
            "sample_validation": samples,
            "none_code": plan["none_code"],
            "eligible": plan["eligible"],
            "mismatches": plan["mismatches"],
            "missing_master": plan["missing_master"],
        }
        write_json(report_path, report)
        write_csv(
            mismatch_path,
            [
                {
                    "raw_code": item["raw_code"],
                    "standard_code": item["standard_code"],
                    "primary_name": item["primary_name"],
                    "standard_name": item["standard_name"],
                    "primary_count": item["primary_count"],
                    "total": item["total"],
                }
                for item in plan["mismatches"]
            ],
            ["raw_code", "standard_code", "primary_name", "standard_name", "primary_count", "total"],
        )

        logger.info("mode=%s", report["mode"])
        logger.info("eligible_code_count=%s", report["eligible_code_count"])
        logger.info("planned_records_to_update=%s", report["planned_records_to_update"])
        logger.info("updated matched=%s modified=%s", update_result["matched"], update_result["modified"])
        logger.info("mismatch_code_count=%s", report["mismatch_code_count"])
        logger.info("missing_master_code_count=%s", report["missing_master_code_count"])
        logger.info("none_code_count=%s (reported only, no update/delete)", report["none_code_count"])
        logger.info("report=%s", report_path)
        logger.info("mismatch_csv=%s", mismatch_path)
    finally:
        client.close()


if __name__ == "__main__":
    main()
