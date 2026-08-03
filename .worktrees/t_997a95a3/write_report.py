"""Generate precheck report JSON for t_997a95a3."""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/pascal/workspace/yquant-investment/skills/data/data-pipeline/scripts")

from loaders.mongodb_loader import PortfolioMongoLoader


def main():
    loader = PortfolioMongoLoader()
    db = loader._db()

    pos_zo_002_31 = db["portfolio_position"].count_documents(
        {"position_date": "2026-07-31", "product_code": "ZO-002"}
    )
    pos_sm004_31 = db["portfolio_position"].count_documents(
        {"position_date": "2026-07-31", "product_code": "SM004"}
    )
    pos_sm004_total = db["portfolio_position"].count_documents({"product_code": "SM004"})
    pos_zo_002_total = db["portfolio_position"].count_documents({"product_code": "ZO-002"})
    nav_zo_002 = db["portfolio_nav"].count_documents({"product_code": "ZO-002"})
    nav_sm004 = db["portfolio_nav"].count_documents({"product_code": "SM004"})
    trade_sm004 = db["portfolio_trade"].count_documents({"product_code": "SM004"})
    trade_zo_002 = db["portfolio_trade"].count_documents({"product_code": "ZO-002"})
    sm004_001232 = db["portfolio_position"].count_documents(
        {"product_code": "SM004", "asset_wind_code": "001232.SZ"}
    )
    bi_err = db["portfolio_basic_info"].count_documents(
        {"product_code": "ZO-002", "product_name": "SM004"}
    )
    bi_legit = db["portfolio_basic_info"].count_documents(
        {"product_code": "SM004", "product_name": "ZO-002"}
    )

    checks = [
        ("positions_ZO-002_2026-07-31 == 23", 23, pos_zo_002_31),
        ("positions_SM004_2026-07-31 == 0", 0, pos_sm004_31),
        ("nav_ZO-002 == 1", 1, nav_zo_002),
        ("nav_SM004 == 0 (spec assumed empty)", 0, nav_sm004),
        ("basic_info_erroneous_ZO-002/SM004 == 1", 1, bi_err),
        ("basic_info_legitimate_SM004/ZO-002 == 1", 1, bi_legit),
        ("SM004_trade_total == 1 (spec assumed)", 1, trade_sm004),
        ("001232.SZ_under_SM004 == 0 (spec assumed)", 0, sm004_001232),
    ]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_id": "t_997a95a3",
        "decision": "BLOCK — zero DML performed",
        "reason": (
            "Three precheck acceptance values from the task spec do not match "
            "actual database state. nav_SM004_total=264 (spec assumed 0); "
            "SM004_trade_total=1193 (spec assumed 1); "
            "001232.SZ under SM004=3 (spec assumed 0). "
            "Task rule: 'Any mismatch/conflict => zero DML, block.' "
            "Awaiting Pascal decision on whether the spec precheck values "
            "should be updated, or the scope should be revised."
        ),
        "precheck_summary": {
            "portfolio_position_ZO-002_2026-07-31": pos_zo_002_31,
            "portfolio_position_SM004_2026-07-31": pos_sm004_31,
            "portfolio_position_SM004_total_all_dates": pos_sm004_total,
            "portfolio_position_ZO-002_total_all_dates": pos_zo_002_total,
            "portfolio_nav_ZO-002_total": nav_zo_002,
            "portfolio_nav_SM004_total": nav_sm004,
            "portfolio_trade_SM004_total": trade_sm004,
            "portfolio_trade_ZO-002_total": trade_zo_002,
            "001232.SZ_under_SM004": sm004_001232,
            "basic_info_erroneous_ZO-002_named_SM004": bi_err,
            "basic_info_legitimate_SM004_named_ZO-002": bi_legit,
        },
        "spec_precheck_vs_actual": [
            {"check": label, "expected": exp, "actual": act,
             "status": "PASS" if act == exp else "FAIL"}
            for (label, exp, act) in checks
        ],
        "additional_finding": (
            "portfolio_basic_info contains 7 docs; only the SM004/ZO-002 pair "
            "matches the task spec. Other docs (SM001/JS-001, SM002/JS-002, "
            "SM003/ZO-001, SM012/CCT-001, CCT-001/SM012) also appear to have "
            "non-matching product_code/product_name pairs. Out of scope per "
            "task ('Authorized DML only: ... no other products/dates'), but "
            "Pascal should be aware."
        ),
    }

    out_path = "/home/pascal/workspace/yquant-investment/.worktrees/t_997a95a3/precheck_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"Written: {out_path} ({os.path.getsize(out_path)} bytes)")
    print(json.dumps(report["spec_precheck_vs_actual"], ensure_ascii=False, indent=2))
    loader.close()


if __name__ == "__main__":
    main()
