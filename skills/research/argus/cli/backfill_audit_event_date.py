#!/usr/bin/env python3
"""Backfill event_date for existing audit records using source_signal_id."""

import sys
sys.path.insert(0, "/home/pascal/.openclaw/workspace-yquant")

from skills.portfolio.stock_pool.repository import StockPoolRepository
from skills.research.argus.config import ARGUS_CONFIG
from skills.data.data_interface import MongoReader
from datetime import datetime


def format_date(dt):
    """Format date for consistency."""
    if isinstance(dt, str):
        return dt[:10]
    if hasattr(dt, 'date'):
        return dt.date().isoformat() if hasattr(dt, 'date') else str(dt)[:10]
    return str(dt)[:10]


def main():
    repo = StockPoolRepository()
    reader = MongoReader(ARGUS_CONFIG)
    audit_collection = repo.audit_collection

    # Get signal_pool collection for lookups
    signal_pool_coll = reader.db["08_research_argus_signal_pool"]

    # Find all audit records
    audits = list(audit_collection.find({}))

    print(f"Total audit records: {len(audits)}")

    updated = 0
    skipped = 0
    errors = 0

    for audit in audits:
        audit_id = audit["_id"]
        pool_id = audit["pool_id"]

        current_event_date = audit.get("event_date")
        created_at = audit.get("created_at")
        actor = audit.get("actor", "")
        after_state = audit.get("after") or {}
        before_state = audit.get("before") or {}

        event_date = None

        # Try to get event_date from source_signal_id in after/before state
        if not event_date:
            source_signal_id = after_state.get("source_signal_id") or before_state.get("source_signal_id")
            if source_signal_id:
                signal = signal_pool_coll.find_one({"signal_id": source_signal_id}, {"date": 1})
                if signal and signal.get("date"):
                    event_date = format_date(signal["date"])

        # Try to get from entry_date in after/before state
        if not event_date:
            entry_date = after_state.get("entry_date") or before_state.get("entry_date")
            if entry_date:
                event_date = format_date(entry_date)

        # For manual/regular records, use created_at date as fallback
        if not event_date and created_at:
            event_date = format_date(created_at)

        # Only update if event_date is different from current
        if event_date and event_date != current_event_date:
            try:
                audit_collection.update_one(
                    {"_id": audit_id},
                    {"$set": {"event_date": event_date}}
                )
                updated += 1
                if updated <= 10:
                    print(f"Updated audit {audit_id}: pool={pool_id[:20]}, action={audit.get('action')}, event_date={event_date}, actor={actor[:30]}")
            except Exception as e:
                errors += 1
                print(f"Error updating audit {audit_id}: {e}")
        else:
            skipped += 1

    print(f"\nBackfill complete: {updated} updated, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()