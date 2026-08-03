"""
Precheck script for t_997a95a3 SM004 production repair.
Read-only counts + schema sampling. No DML.
"""
import sys
import json
import os
from datetime import datetime, timezone

sys.path.insert(0, "/home/pascal/workspace/yquant-investment/skills/data/data-pipeline/scripts")

from loaders.mongodb_loader import PortfolioMongoLoader

REPORT_DIR = "/home/pascal/workspace/yquant-investment/.worktrees/t_997a95a3"
os.makedirs(REPORT_DIR, exist_ok=True)


def jdump(o):
    return json.dumps(o, ensure_ascii=False, indent=2, default=str)


def main():
    loader = PortfolioMongoLoader()
    db = loader._db()
    started = datetime.now(timezone.utc).isoformat()

    print("=" * 70)
    print(f"PRECHECK  start_time={started}")
    print("=" * 70)

    # 1. portfolio_position: source ZO-002 / target SM004 on 2026-07-31
    pos_filter = {"position_date": "2026-07-31", "product_code": "ZO-002"}
    pos_src_count = db["portfolio_position"].count_documents(pos_filter)
    pos_target_count = db["portfolio_position"].count_documents(
        {"position_date": "2026-07-31", "product_code": "SM004"}
    )

    # 2. portfolio_nav: source ZO-002 / target SM004
    nav_src = db["portfolio_nav"].count_documents({"product_code": "ZO-002"})
    nav_target = db["portfolio_nav"].count_documents({"product_code": "SM004"})

    # 3. portfolio_basic_info
    basic_err = db["portfolio_basic_info"].count_documents(
        {"product_code": "ZO-002", "product_name": "SM004"}
    )
    basic_legit = db["portfolio_basic_info"].count_documents(
        {"product_code": "SM004", "product_name": "ZO-002"}
    )

    # 4. Context checks: 001232.SZ under SM004, total SM004 trade count
    pos_001232_sm004 = db["portfolio_position"].count_documents(
        {"product_code": "SM004", "asset_wind_code": "001232.SZ"}
    )
    trade_sm004 = db["portfolio_trade"].count_documents({"product_code": "SM004"})

    # 5. Other context: total positions per product on 2026-07-31
    all_products_on_date = list(
        db["portfolio_position"].aggregate(
            [
                {"$match": {"position_date": "2026-07-31"}},
                {"$group": {"_id": "$product_code", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
        )
    )

    # 6. Show nav product_codes list
    nav_products = sorted(db["portfolio_nav"].distinct("product_code"))

    # 7. Show basic_info all docs
    basic_info_all = list(
        db["portfolio_basic_info"].find({}, {"_id": 0, "product_code": 1, "product_name": 1})
    )

    # 8. Snapshot the 23 position docs' key business fields (no _id)
    pos_docs = list(
        db["portfolio_position"].find(
            pos_filter,
            {"_id": 0, "position_date": 1, "product_code": 1, "asset_wind_code": 1,
             "asset_name": 1, "position_volume": 1, "position_market_value": 1,
             "cost_price": 1, "close_price": 1, "weight": 1, "source": 1,
             "created_at": 1, "updated_at": 1},
        )
    )

    # 9. Snapshot the 1 nav doc's key fields
    nav_docs = list(
        db["portfolio_nav"].find(
            {"product_code": "ZO-002"},
            {"_id": 0, "nav_date": 1, "product_code": 1, "nav": 1, "share": 1, "aum": 1,
             "accumulated_nav": 1, "source": 1, "created_at": 1, "updated_at": 1},
        )
    )

    # 10. Snapshot both basic_info docs
    basic_err_doc = db["portfolio_basic_info"].find_one(
        {"product_code": "ZO-002", "product_name": "SM004"}, {"_id": 0}
    )
    basic_legit_doc = db["portfolio_basic_info"].find_one(
        {"product_code": "SM004", "product_name": "ZO-002"}, {"_id": 0}
    )

    precheck = {
        "precheck_at": started,
        "task_id": "t_997a95a3",
        "portfolio_position": {
            "source_ZO-002_2026-07-31": pos_src_count,
            "target_SM004_2026-07-31": pos_target_count,
            "all_products_2026-07-31": {p["_id"]: p["count"] for p in all_products_on_date},
        },
        "portfolio_nav": {
            "source_ZO-002_total": nav_src,
            "target_SM004_total": nav_target,
            "all_product_codes": nav_products,
        },
        "portfolio_basic_info": {
            "erroneous_ZO-002_named_SM004": basic_err,
            "legitimate_SM004_named_ZO-002": basic_legit,
            "all_docs": basic_info_all,
        },
        "context": {
            "SM004_trade_total": trade_sm004,
            "001232.SZ_under_SM004_positions": pos_001232_sm004,
        },
    }

    print(jdump(precheck))

    print("\n--- SAMPLE position doc (ZO-002, 2026-07-31) ---")
    if pos_docs:
        print(jdump(pos_docs[0]))
    print(f"\n--- Total position docs to move: {len(pos_docs)} ---")

    print("\n--- nav docs (ZO-002) ---")
    print(jdump(nav_docs))

    print("\n--- basic_info erroneous (ZO-002, SM004) ---")
    print(jdump(basic_err_doc))
    print("\n--- basic_info legitimate (SM004, ZO-002) ---")
    print(jdump(basic_legit_doc))

    # Acceptance check vs. task spec
    print("\n" + "=" * 70)
    print("ACCEPTANCE CHECK (precheck values vs. task spec)")
    print("=" * 70)
    checks = [
        ("portfolio_position source ZO-002 == 23", pos_src_count == 23),
        ("portfolio_position target SM004 == 0", pos_target_count == 0),
        ("portfolio_nav source ZO-002 == 1", nav_src == 1),
        ("portfolio_nav target SM004 == 0", nav_target == 0),
        ("basic_info erroneous == 1", basic_err == 1),
        ("basic_info legitimate == 1", basic_legit == 1),
        ("SM004 trade count == 1 (no change)", trade_sm004 == 1),
        ("001232.SZ under SM004 == 0 (no change)", pos_001232_sm004 == 0),
    ]
    all_ok = True
    for label, ok in checks:
        marker = "OK " if ok else "FAIL"
        print(f"  [{marker}] {label}")
        all_ok = all_ok and ok

    print("\nALL CHECKS PASSED" if all_ok else "\nSOME CHECKS FAILED -- DO NOT PROCEED")
    if not all_ok:
        loader.close()
        sys.exit(1)

    # Write snapshot to disk for rollback use
    snapshot = {
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "task_id": "t_997a95a3",
        "positions_to_move": pos_docs,
        "nav_to_move": nav_docs,
        "basic_erroneous_doc": basic_err_doc,
        "basic_legitimate_doc": basic_legit_doc,
        "context": precheck["context"],
    }
    snap_path = os.path.join(REPORT_DIR, "snapshot_before.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nSnapshot written: {snap_path} (size={os.path.getsize(snap_path)} bytes)")

    loader.close()


if __name__ == "__main__":
    main()
