#!/usr/bin/env python3
"""Backfill Argus signal pool_zone and fix negative industry weights.

Usage:
    python -m skills.research.argus.cli.backfill_signal_pool_zone_and_weight
    ARGUS_MONGO_URI=mongodb://... python -m skills.research.argus.cli.backfill_signal_pool_zone_and_weight
"""

import os
import sys

sys.path.insert(0, '/home/pascal/.openclaw/workspace-yquant')

from pymongo import MongoClient


DEFAULT_MONGO_URI = 'mongodb://myq:6812345@172.25.240.1:27017/admin'
DEFAULT_DATABASE = 'tradingagents'
SIGNAL_COLLECTION = '08_research_argus_signal'
INDUSTRY_WEIGHT_COLLECTION = '08_research_argus_industry_weight'


def backfill_signal_pool_zone(db) -> int:
    result = db[SIGNAL_COLLECTION].update_many(
        {'metadata.pool_zone': {'$exists': True}},
        [{'$set': {'pool_zone': '$metadata.pool_zone'}}],
    )
    return result.modified_count


def fix_negative_industry_weight(db) -> int:
    result = db[INDUSTRY_WEIGHT_COLLECTION].update_one(
        {
            'date': '2026-05-06',
            'product_code': 'SM004',
            'sw1_code': '801880.SI',
        },
        {'$set': {'weight_pct': 0}},
    )
    return result.modified_count


def count_signal_pool_zone_mismatches(db) -> int:
    rows = list(db[SIGNAL_COLLECTION].aggregate([
        {
            '$project': {
                'pool_zone': 1,
                'metadata.pool_zone': 1,
                'match': {'$eq': ['$pool_zone', '$metadata.pool_zone']},
            }
        },
        {'$match': {'match': False}},
        {'$count': 'mismatched'},
    ]))
    return rows[0]['mismatched'] if rows else 0


def count_negative_industry_weights(db) -> int:
    return db[INDUSTRY_WEIGHT_COLLECTION].count_documents({'weight_pct': {'$lt': 0}})


def main() -> int:
    mongo_uri = os.getenv('ARGUS_MONGO_URI', DEFAULT_MONGO_URI)
    database = os.getenv('ARGUS_MONGO_DATABASE', DEFAULT_DATABASE)

    client = MongoClient(mongo_uri)
    db = client[database]

    signal_modified = backfill_signal_pool_zone(db)
    weight_modified = fix_negative_industry_weight(db)
    mismatches = count_signal_pool_zone_mismatches(db)
    negative_weights = count_negative_industry_weights(db)

    print("=== Argus Backfill Results ===")
    print(f"Signal pool_zone modified: {signal_modified}")
    print(f"Negative industry weight modified: {weight_modified}")
    print(f"Signal pool_zone mismatches remaining: {mismatches}")
    print(f"Negative industry weights remaining: {negative_weights}")

    return 0 if mismatches == 0 and negative_weights == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
