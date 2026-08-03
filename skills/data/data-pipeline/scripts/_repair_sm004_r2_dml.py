"""SM004 R2 repair DML — authorized, date-bounded, scope-bounded.

DML 1: portfolio_position.update_many({position_date:'2026-07-31', product_code:'ZO-002'}, {$set:{product_code:'SM004'}})
DML 2: portfolio_nav.update_one({nav_date:'2026-07-31', product_code:'ZO-002'}, {$set:{product_code:'SM004'}})
DML 3: portfolio_basic_info.delete_one({product_code:'ZO-002', product_name:'SM004'})
       + read back the corrected 2026-07-31 SM004 nav and update only
         latest_nav/latest_aum/latest_share on the legal basic record
         ({product_code:'SM004', product_name:'ZO-002'}).

Forbidden: any other date, any other product, trade collection, stock_basic_info,
pending 001232 data, code/docs/config/git, DDL, insert.

Each step captures matched/modified/deleted for handoff. Idempotent re-run is
NOT the goal — this is a one-shot authorized repair.
"""
import json
from datetime import datetime, timezone

from loaders.mongodb_loader import PortfolioMongoLoader

db = PortfolioMongoLoader()._db()

results = {}
now = datetime.now(timezone.utc)

# --- DML 1: position 23 rows -> SM004
f1 = {"position_date": "2026-07-31", "product_code": "ZO-002"}
matched = db["portfolio_position"].count_documents(f1)
upd1 = db["portfolio_position"].update_many(
    f1, {"$set": {"product_code": "SM004", "updated_at": now}}
)
results["DML1_position"] = {
    "filter": f1,
    "matched": matched,
    "modified": upd1.modified_count,
}

# --- DML 2: nav 1 row -> SM004
f2 = {"nav_date": "2026-07-31", "product_code": "ZO-002"}
matched2 = db["portfolio_nav"].count_documents(f2)
upd2 = db["portfolio_nav"].update_one(
    f2, {"$set": {"product_code": "SM004", "updated_at": now}}
)
results["DML2_nav"] = {
    "filter": f2,
    "matched": matched2,
    "modified": upd2.modified_count,
}

# --- DML 3a: delete 错误 basic
f3a = {"product_code": "ZO-002", "product_name": "SM004"}
matched3a = db["portfolio_basic_info"].count_documents(f3a)
del3a = db["portfolio_basic_info"].delete_one(f3a)
results["DML3a_basic_delete_错误"] = {
    "filter": f3a,
    "matched": matched3a,
    "deleted": del3a.deleted_count,
}

# --- DML 3b: read post-fix SM004 nav 2026-07-31 and update legal basic
nav_row = db["portfolio_nav"].find_one(
    {"nav_date": "2026-07-31", "product_code": "SM004"},
    projection={"_id": 0, "nav": 1, "aum": 1, "share": 1},
)
assert nav_row is not None, "post-DML nav row missing — aborting"
f3b = {"product_code": "SM004", "product_name": "ZO-002"}
matched3b = db["portfolio_basic_info"].count_documents(f3b)
upd3b = db["portfolio_basic_info"].update_one(
    f3b,
    {
        "$set": {
            "latest_nav": nav_row.get("nav"),
            "latest_aum": nav_row.get("aum"),
            "latest_share": nav_row.get("share"),
            "updated_at": now,
        }
    },
)
results["DML3b_basic_update_合法"] = {
    "filter": f3b,
    "matched": matched3b,
    "modified": upd3b.modified_count,
    "values_applied": {
        "latest_nav": nav_row.get("nav"),
        "latest_aum": nav_row.get("aum"),
        "latest_share": nav_row.get("share"),
    },
}

print(json.dumps(results, ensure_ascii=False, indent=2, default=str))