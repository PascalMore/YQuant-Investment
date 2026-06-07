#!/usr/bin/env python3
"""Backfill Portfolio stock-pool audit from historical Argus signal-pool snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

sys.path.insert(0, "/home/pascal/.openclaw/workspace-yquant")

from skills.data.data_interface import MongoReader
from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService, StockPoolTransitionPipeline
from skills.portfolio.stock_pool.repository import StockPoolRepository
from skills.portfolio.stock_pool.service import StockPoolService


SIGNAL_POOL_COLLECTION = "08_research_argus_signal_pool"
SUMMARY_KEYS = ("entry", "promote", "demote", "exit", "retain", "update", "skipped")


def backfill_audit(start_date: str, end_date: str, database: str = "tradingagents") -> Dict[str, Any]:
    """Replay adjacent Argus signal-pool snapshots into Portfolio stock-pool audit."""
    reader = MongoReader(database=database)
    ingestion = StockPoolIngestionService(StockPoolService(StockPoolRepository(database=database)))
    pipeline = StockPoolTransitionPipeline(ingestion)
    dates = _available_signal_pool_dates(reader, start_date, end_date)

    total = {key: 0 for key in SUMMARY_KEYS}
    daily_results = []
    for previous_date, current_date in zip(dates, dates[1:]):
        previous = reader.read(previous_date, collection_name=SIGNAL_POOL_COLLECTION)
        current = reader.read(current_date, collection_name=SIGNAL_POOL_COLLECTION)
        summary = pipeline.run_incremental_transition(
            current_signals=current,
            previous_signals=previous,
            actor="system:argus_backfill",
            event_date=current_date,
            dry_run=False,
        )
        for key in SUMMARY_KEYS:
            total[key] += summary.get(key, 0)
        daily_results.append(
            {
                "date": current_date,
                "previous_date": previous_date,
                **{key: summary.get(key, 0) for key in SUMMARY_KEYS},
                "errors": summary.get("errors", []),
            }
        )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "dates_processed": len(daily_results),
        "total": total,
        "daily": daily_results,
    }


def _available_signal_pool_dates(reader: MongoReader, start_date: str, end_date: str) -> List[str]:
    query = {"date": {"$gte": start_date, "$lte": end_date}}
    dates = reader.db[SIGNAL_POOL_COLLECTION].distinct("date", query)
    return sorted(str(date) for date in dates)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--database", default="tradingagents")
    args = parser.parse_args()

    result = backfill_audit(args.start_date, args.end_date, args.database)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
