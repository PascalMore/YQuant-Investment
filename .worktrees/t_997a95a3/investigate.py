"""
Deep investigation for t_997a95a3 — gather more context about the
precheck mismatch before blocking for human decision.
Read-only.
"""
import sys
import json
import os
from datetime import datetime, timezone

sys.path.insert(0, "/home/pascal/workspace/yquant-investment/skills/data/data-pipeline/scripts")

from loaders.mongodb_loader import PortfolioMongoLoader

REPORT_DIR = "/home/pascal/workspace/yquant-investment/.worktrees/t_997a95a3"


def jdump(o):
    return json.dumps(o, ensure_ascii=False, indent=2, default=str)


def main():
    loader = PortfolioMongoLoader()
    db = loader._db()
    started = datetime.now(timezone.utc).isoformat()

    print("=" * 70)
    print(f"DEEP INVESTIGATION  start_time={started}")
    print("=" * 70)

    # A. Distribution of SM004 nav by nav_date
    sm004_nav_by_date = list(
        db["portfolio_nav"].aggregate(
            [
                {"$match": {"product_code": "SM004"}},
                {"$group": {"_id": "$nav_date", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
        )
    )
    sm004_nav_date_count = len(sm004_nav_by_date)
    sm004_nav_total = db["portfolio_nav"].count_documents({"product_code": "SM004"})
    print(f"\n--- SM004 nav total rows: {sm004_nav_total}, distinct dates: {sm004_nav_date_count} ---")
    print("First 3 dates:", sm004_nav_by_date[:3])
    print("Last 3 dates:", sm004_nav_by_date[-3:])

    # B. SM004 trade by date
    sm004_trade_by_date = list(
        db["portfolio_trade"].aggregate(
            [
                {"$match": {"product_code": "SM004"}},
                {"$group": {"_id": "$trade_date", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
        )
    )
    sm004_trade_total = db["portfolio_trade"].count_documents({"product_code": "SM004"})
    print(f"\n--- SM004 trade total rows: {sm004_trade_total}, distinct dates: {len(sm004_trade_by_date)} ---")
    print("First 3 dates:", sm004_trade_by_date[:3])
    print("Last 3 dates:", sm004_trade_by_date[-3:])

    # C. SM004 positions by date
    sm004_pos_by_date = list(
        db["portfolio_position"].aggregate(
            [
                {"$match": {"product_code": "SM004"}},
                {"$group": {"_id": "$position_date", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
        )
    )
    print(f"\n--- SM004 position total rows: {db['portfolio_position'].count_documents({'product_code': 'SM004'})}, distinct dates: {len(sm004_pos_by_date)} ---")
    print("All dates with count:")
    for d in sm004_pos_by_date:
        print(f"  {d['_id']}: {d['count']}")

    # D. SM004 positions on 2026-07-31
    sm004_pos_20260731 = list(
        db["portfolio_position"].find(
            {"product_code": "SM004", "position_date": "2026-07-31"},
            {"_id": 0, "asset_wind_code": 1, "asset_name": 1, "updated_at": 1},
        )
    )
    print(f"\n--- SM004 positions on 2026-07-31: {len(sm004_pos_20260731)} ---")
    for p in sm004_pos_20260731:
        print(f"  {p}")

    # E. Are there any other product_codes named SM004 in nav/position/trade?
    sm004_products_in_pos = db["portfolio_position"].distinct("product_code")
    sm004_products_in_nav = db["portfolio_nav"].distinct("product_code")
    sm004_products_in_trade = db["portfolio_trade"].distinct("product_code")
    print(f"\n--- All distinct product_codes in position: {sorted(sm004_products_in_pos)}")
    print(f"--- All distinct product_codes in nav: {sorted(sm004_products_in_nav)}")
    print(f"--- All distinct product_codes in trade: {sorted(sm004_products_in_trade)}")

    # F. ZO-002 stats
    zo002_pos_total = db["portfolio_position"].count_documents({"product_code": "ZO-002"})
    zo002_pos_dates = list(
        db["portfolio_position"].aggregate(
            [
                {"$match": {"product_code": "ZO-002"}},
                {"$group": {"_id": "$position_date", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
        )
    )
    zo002_nav_dates = list(
        db["portfolio_nav"].aggregate(
            [
                {"$match": {"product_code": "ZO-002"}},
                {"$group": {"_id": "$nav_date", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
        )
    )
    zo002_trade_total = db["portfolio_trade"].count_documents({"product_code": "ZO-002"})
    print(f"\n--- ZO-002 position total: {zo002_pos_total}, dates: {zo002_pos_dates}")
    print(f"--- ZO-002 nav dates: {zo002_nav_dates}")
    print(f"--- ZO-002 trade total: {zo002_trade_total}")

    # G. 001232.SZ under SM004 detail
    sm004_001232 = list(
        db["portfolio_position"].find(
            {"product_code": "SM004", "asset_wind_code": "001232.SZ"},
            {"_id": 0, "position_date": 1, "asset_wind_code": 1, "asset_name": 1,
             "position_volume": 1, "position_market_value": 1, "updated_at": 1},
        )
    )
    print(f"\n--- 001232.SZ under SM004 ({len(sm004_001232)} rows): ---")
    for p in sm004_001232:
        print(f"  {p}")

    # H. same asset codes between ZO-002 (2026-07-31) and SM004 (2026-07-31)
    zo002_assets = set(
        r["asset_wind_code"]
        for r in db["portfolio_position"].find(
            {"position_date": "2026-07-31", "product_code": "ZO-002"},
            {"asset_wind_code": 1, "_id": 0},
        )
    )
    sm004_assets_20260731 = set(
        r["asset_wind_code"]
        for r in db["portfolio_position"].find(
            {"position_date": "2026-07-31", "product_code": "SM004"},
            {"asset_wind_code": 1, "_id": 0},
        )
    )
    overlap = zo002_assets & sm004_assets_20260731
    print(f"\n--- Overlap (asset_wind_code) ZO-002 ∩ SM004 on 2026-07-31: {len(overlap)} ---")
    if overlap:
        print("  overlap items:", sorted(overlap))

    # I. updated_at times for basic_info
    bi_all = list(
        db["portfolio_basic_info"].find({}, {"_id": 0})
    )
    print("\n--- portfolio_basic_info all docs ---")
    for d in bi_all:
        d2 = {k: v for k, v in d.items()}
        print(f"  {d2}")

    loader.close()


if __name__ == "__main__":
    main()
