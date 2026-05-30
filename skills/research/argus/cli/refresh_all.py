#!/usr/bin/env python3
# skills/research/argus/cli/refresh_all.py
"""Clear and re-backfill all Argus output collections.

Operation is split into two phases:
  1. --clear   : drop all docs from Argus output tables + stock_pool tables
                  (portfolio_position/nav/trade/basic_info are NOT touched)
  2. --backfill : run daily_processor one trading day at a time from START_DATE

Usage:
    # Step 1: clear all output tables (requires confirmation)
    python -m skills.research.argus.cli.refresh_all --clear --confirm

    # Step 2: backfill from first trading day after 2025-12-31 through today
    python -m skills.research.argus.cli.refresh_all --backfill

    # Or chain them (clear then backfill):
    python -m skills.research.argus.cli.refresh_all --clear --confirm --backfill

    # Backfill only a range:
    python -m skills.research.argus.cli.refresh_all --backfill --start 2026-01-05 --end 2026-04-30

    # Dry run (calculate but do not write to Mongo):
    python -m skills.research.argus.cli.refresh_all --backfill --dry-run
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, '/home/pascal/.openclaw/workspace-yquant')

from skills.data.data_interface import MongoReader, MongoWriter
from skills.infra import format_date, get_logger, get_trading_dates, parse_date
from skills.research.argus.cli.daily_processor import process_date
from skills.research.argus.config import ARGUS_CONFIG

logger = get_logger('argus', 'research/argus')

# 第一个交易日 = 2025-12-31 的下一个交易日
START_DATE = '2026-01-05'
DEFAULT_END = format_date(datetime.now().date())

# Collections to CLEAR (all are Argus outputs + stock_pool sync tables)
# portfolio_position / portfolio_nav / portfolio_trade / portfolio_basic_info are NOT listed
CLEAR_COLLECTIONS = [
    '08_research_argus_signal',
    '08_research_argus_signal_pool',
    '08_research_argus_industry_weight',
    '08_research_argus_consensus_direction',
    '08_research_argus_credential_score',
    '08_research_argus_darwin_event',
    '05_portfolio_stock_pool',
    '05_portfolio_stock_pool_audit',
]

# Collections that are ALWAYS preserved (must NOT be cleared)
PRESERVED_COLLECTIONS = [
    'portfolio_position',
    'portfolio_nav',
    'portfolio_trade',
    'portfolio_basic_info',
]


def _brief_result(result: Dict) -> Dict:
    keys = (
        'processed_days',
        'skipped_days',
        'products_processed',
        'signals_generated',
        'industry_weights_written',
        'credential_scores_written',
        'signals_written',
        'signal_pool_written',
        'stock_pool_written',
        'portfolio_stock_pool_sync',
    )
    return {key: result[key] for key in keys if key in result}


# ---------------------------------------------------------------------------
# Phase 1: Clear
# ---------------------------------------------------------------------------

def clear_all(output: bool = True) -> Dict[str, int]:
    """Drop all documents from CLEAR_COLLECTIONS. Returns {collection: deleted_count}."""
    database = ARGUS_CONFIG.get('mongo', {}).get('database', 'tradingagents')
    writer = MongoWriter(database=database)
    db = writer.db

    results = {}
    for coll in CLEAR_COLLECTIONS:
        count = db[coll].count_documents({})
        if count > 0:
            db[coll].delete_many({})
            logger.warning("[Refresh] DELETED %d docs from '%s'", count, coll)
            results[coll] = count
        else:
            logger.info("[Refresh] '%s' already empty, skipped", coll)
            results[coll] = 0

    if output:
        _print_clear_summary(results)

    return results


def _print_clear_summary(results: Dict[str, int]) -> None:
    total = sum(results.values())
    print("\n=== Argus Clear Summary ===")
    for coll, count in results.items():
        status = 'DELETED' if count > 0 else 'already empty'
        print(f"  {coll}: {count} docs ({status})")
    print(f"Total docs removed: {total}")
    print(f"\nPRESERVED (safe): {PRESERVED_COLLECTIONS}")


# ---------------------------------------------------------------------------
# Phase 2: Backfill
# ---------------------------------------------------------------------------

def backfill(
    start: str = START_DATE,
    end: str = DEFAULT_END,
    output_dir: Optional[Path] = None,
    write_mongo: bool = True,
) -> Dict:
    """Backfill Argus one trading day at a time (daily_processor, not backfill_all)."""
    database = ARGUS_CONFIG.get('mongo', {}).get('database', 'tradingagents')
    reader = MongoReader(database=database)
    writer = MongoWriter(database=database) if write_mongo else None

    trading_days = sorted(get_trading_dates(start, end))
    logger.info("[Refresh Backfill] %s ~ %s (%d trading days)", start, end, len(trading_days))

    summary = {
        'start': start,
        'end': end,
        'trading_days': len(trading_days),
        'processed_days': 0,
        'skipped_days': 0,
        'failed_days': 0,
        'industry_weights_written': 0,
        'credential_scores_written': 0,
        'signals_written': 0,
        'signal_pool_written': 0,
        'daily_results': [],
    }

    for trade_date in trading_days:
        positions = reader.read(trade_date, collection_name='portfolio_position')
        if not positions:
            summary['skipped_days'] += 1
            logger.warning("[Refresh Backfill] No portfolio_position for %s; skipped", trade_date)
            continue

        try:
            result = process_date(
                trade_date,
                reader=reader,
                writer=None,           # writer=None triggers _default_stock_pool_ingestion() internally
                write_mongo=write_mongo,
            )
        except Exception as e:
            summary['failed_days'] += 1
            logger.error("[Refresh Backfill] FAILED %s: %s", trade_date, e)
            continue

        summary['processed_days'] += 1
        summary['industry_weights_written'] += result.get('industry_weights_written', 0)
        summary['credential_scores_written'] += result.get('credential_scores_written', 0)
        summary['signals_written'] += result.get('signals_written', 0)
        summary['signal_pool_written'] += result.get('signal_pool_written', 0)
        summary['daily_results'].append(result)
        logger.info("[Refresh Backfill] %s done: %s", trade_date, _brief_result(result))

    logger.info("[Refresh Backfill] Finished: %s", _brief_result(summary))
    return summary


def _print_backfill_summary(summary: Dict) -> None:
    print("\n=== Argus Backfill Summary ===")
    print(f"Range: {summary['start']} ~ {summary['end']}")
    print(f"Trading Days: {summary['trading_days']}")
    print(f"Processed: {summary['processed_days']}")
    print(f"Skipped (no position data): {summary['skipped_days']}")
    print(f"Failed: {summary['failed_days']}")
    print(f"Industry Weights Written: {summary['industry_weights_written']}")
    print(f"Credential Scores Written: {summary['credential_scores_written']}")
    print(f"Signals Written: {summary['signals_written']}")
    print(f"Signal Pool Written: {summary['signal_pool_written']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Clear and re-backfill all Argus output collections. '
                   'Run --clear first, then --backfill.'
    )
    parser.add_argument('--clear', action='store_true',
                        help='Drop all docs from argus output + stock_pool collections')
    parser.add_argument('--confirm', action='store_true',
                        help='Required with --clear to actually execute (safety guard)')
    parser.add_argument('--backfill', action='store_true',
                        help='Run daily_processor one day at a time from START_DATE')
    parser.add_argument('--start', default=START_DATE,
                        help=f'Backfill start date (default: {START_DATE})')
    parser.add_argument('--end', default=DEFAULT_END,
                        help=f'Backfill end date (default: {DEFAULT_END})')
    parser.add_argument('--output-dir', type=Path, default=None,
                        help='Optional JSON output directory per day')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run calculations without Mongo writes')
    args = parser.parse_args()

    if not args.clear and not args.backfill:
        parser.print_help()
        return

    write_mongo = not args.dry_run

    # ---- Phase 1: Clear ----
    if args.clear:
        if not args.confirm:
            print("ERROR: --clear requires --confirm to execute.")
            print("       This will DELETE all data from:")
            for c in CLEAR_COLLECTIONS:
                print(f"         - {c}")
            print(f"\n       The following are PRESERVED (NOT touched):")
            for c in PRESERVED_COLLECTIONS:
                print(f"         - {c}")
            print("\n       Re-run with --confirm to proceed.")
            sys.exit(1)

        clear_all(output=True)

    # ---- Phase 2: Backfill ----
    if args.backfill:
        print(f"\n[Refresh] Starting backfill: {args.start} ~ {args.end}")
        summary = backfill(
            start=args.start,
            end=args.end,
            output_dir=args.output_dir,
            write_mongo=write_mongo,
        )
        _print_backfill_summary(summary)

        if summary['failed_days'] > 0:
            print(f"\nWARNING: {summary['failed_days']} day(s) failed. Check logs above.")
            sys.exit(1)


if __name__ == '__main__':
    main()