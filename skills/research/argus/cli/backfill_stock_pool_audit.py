#!/usr/bin/env python3
"""Backfill stock_pool audit from argus_signal_pool data."""

import sys
sys.path.insert(0, "/home/pascal/.openclaw/workspace-yquant")

from datetime import datetime, timedelta
from skills.data.data_interface import MongoReader
from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService
from skills.portfolio.stock_pool.service import StockPoolService
from skills.portfolio.stock_pool.repository import StockPoolRepository
from skills.research.argus.config import ARGUS_CONFIG
from skills.infra import format_date, get_trading_dates


def main():
    start = "2026-01-01"
    end = "2026-05-25"
    trading_days = get_trading_dates(start, end)
    
    db_name = ARGUS_CONFIG.get('mongo', {}).get('database', 'tradingagents')
    reader = MongoReader(database=db_name)
    signal_pool = reader.db["08_research_argus_signal_pool"]
    
    from skills.portfolio.stock_pool.repository import StockPoolRepository
    repo = StockPoolRepository()
    ingestion = StockPoolIngestionService(StockPoolService(repo))
    
    total_entry = total_promote = total_demote = total_exit = total_update = total_skipped = 0
    
    print(f"Processing {len(trading_days)} trading days from {start} to {end}")
    
    for i, day in enumerate(trading_days):
        prev_day = trading_days[i - 1] if i > 0 else None
        
        # Get signals for current day
        current_signals = list(signal_pool.find({"date": day}))
        
        # Get signals for previous day
        previous_signals = []
        if prev_day:
            previous_signals = list(signal_pool.find({"date": prev_day}))
        
        if not current_signals and not previous_signals:
            print(f"  {day}: no signals, skipped")
            continue
        
        # Run incremental ingestion
        result = ingestion.ingest_signals_incremental(
            current_signals=current_signals,
            previous_signals=previous_signals,
            actor="system:argus_backfill",
            event_date=day,
        )
        
        total_entry += result.get("entry", 0)
        total_promote += result.get("promote", 0)
        total_demote += result.get("demote", 0)
        total_exit += result.get("exit", 0)
        total_update += result.get("update", 0)
        total_skipped += result.get("skipped", 0)
        
        if (i + 1) % 20 == 0 or i == len(trading_days) - 1:
            print(f"  [{i+1}/{len(trading_days)}] {day}: entry={result.get('entry')}, promote={result.get('promote')}, demote={result.get('demote')}, exit={result.get('exit')}, update={result.get('update')}")
    
    print(f"\n=== Stock Pool Audit Backfill Complete ===")
    print(f"Total: entry={total_entry}, promote={total_promote}, demote={total_demote}, exit={total_exit}, update={total_update}, skipped={total_skipped}")


if __name__ == "__main__":
    main()