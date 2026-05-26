#!/usr/bin/env python3
# skills/research/argus/cli/backfill_all.py
"""Backfill all Argus output collections over a date range.

Usage:
    python -m skills.research.argus.cli.backfill_all              # 默认从 2025-12-31 到今天
    python -m skills.research.argus.cli.backfill_all --start 2026-01-01 --end 2026-05-25
    python -m skills.research.argus.cli.backfill_all --from 2026-05-15   # refresh from 5/15 through today
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

DEFAULT_START = '2025-12-31'
DEFAULT_END = format_date(datetime.now().date())  # 默认今天，与 daily_processor 保持一致


def backfill_all(
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    output_dir: Optional[Path] = None,
    write_mongo: bool = True,
) -> Dict:
    """Backfill Argus for every trading day in [start, end]."""
    database = ARGUS_CONFIG.get('mongo', {}).get('database', 'tradingagents')
    reader = MongoReader(database=database)
    writer = MongoWriter(database=database) if write_mongo else None
    trading_days = _trading_days(start, end)

    logger.info("[Argus Backfill] Starting backfill from %s to %s (%s trading days)", start, end, len(trading_days))
    summary = {
        'start': start,
        'end': end,
        'trading_days': len(trading_days),
        'processed_days': 0,
        'skipped_days': 0,
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
            logger.warning("[Argus Backfill] No portfolio_position for %s; skipped", trade_date)
            continue

        result = process_date(
            trade_date,
            reader=reader,
            writer=writer,
            output_dir=output_dir,
            write_mongo=write_mongo,
        )
        summary['processed_days'] += 1
        summary['industry_weights_written'] += result.get('industry_weights_written', 0)
        summary['credential_scores_written'] += result.get('credential_scores_written', 0)
        summary['signals_written'] += result.get('signals_written', 0)
        summary['signal_pool_written'] += result.get('signal_pool_written', 0)
        summary['daily_results'].append(result)
        logger.info("[Argus Backfill] Completed %s: %s", trade_date, _brief_result(result))

    logger.info("[Argus Backfill] Finished: %s", _brief_result(summary))
    return summary


def _trading_days(start: str, end: str) -> List[str]:
    """Return trading dates, covering the 2025-12-31 bootstrap day."""
    dates = set(get_trading_dates(start, end))
    start_dt = parse_date(start)
    end_dt = parse_date(end)
    current = start_dt
    while current <= end_dt:
        if current.year != 2026 and current.weekday() < 5:
            dates.add(format_date(current))
        current += timedelta(days=1)
    return sorted(dates)


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
    )
    return {key: result[key] for key in keys if key in result}


def main() -> None:
    parser = argparse.ArgumentParser(description='Backfill all Argus outputs with upsert semantics.')
    parser.add_argument('--start', default=DEFAULT_START, help='Start date, inclusive (YYYY-MM-DD)')
    parser.add_argument('--end', default=DEFAULT_END, help='End date, inclusive (YYYY-MM-DD)')
    parser.add_argument('--from', dest='refresh_from', default=None,
                        help='Refresh from this date through --end (implies --end=today); '
                             'useful when a specific day raw data was corrected and all subsequent days need refresh')
    parser.add_argument('--output-dir', type=Path, default=None, help='Optional JSON output directory')
    parser.add_argument('--dry-run', action='store_true', help='Run calculations and JSON output without Mongo writes')
    args = parser.parse_args()

    # --from mode: refresh from a fixed date through today
    if args.refresh_from:
        from_date = args.refresh_from
        import datetime
        end_date = datetime.date.today().strftime('%Y-%m-%d')
    else:
        from_date = args.start
        end_date = args.end

    summary = backfill_all(
        start=from_date,
        end=end_date,
        output_dir=args.output_dir,
        write_mongo=not args.dry_run,
    )

    print(f"\n=== Argus Backfill Results ===")
    if args.refresh_from:
        print(f"Mode: --from {from_date} (cascade refresh through {end_date})")
    print(f"Range: {summary['start']} ~ {summary['end']}")
    print(f"Trading Days: {summary['trading_days']}")
    print(f"Processed Days: {summary['processed_days']}")
    print(f"Skipped Days: {summary['skipped_days']}")
    print(f"Industry Weights Written: {summary['industry_weights_written']}")
    print(f"Credential Scores Written: {summary['credential_scores_written']}")
    print(f"Signals Written: {summary['signals_written']}")
    print(f"Signal Pool Written: {summary['signal_pool_written']}")


if __name__ == '__main__':
    main()
