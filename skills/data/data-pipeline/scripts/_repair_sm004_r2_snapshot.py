"""SM004 R2 repair snapshot — dump current state of target-date rows to disk
before any DML. Read-only. Captures:
  - portfolio_position 2026-07-31 ZO-002 (all 23 rows) — key business fields
  - portfolio_nav 2026-07-31 ZO-002 (1 row)
  - portfolio_basic_info {product_code:'ZO-002',product_name:'SM004'} (1 row)
  - portfolio_basic_info {product_code:'SM004',product_name:'ZO-002'} (1 row)
Counts only (sanity):
  - portfolio_nav SM004 all / portfolio_trade SM004 all / portfolio_position SM004 all
  - portfolio_nav max nav_date
No _id, no secrets. Output to skills/data/source/smart-money/2026-08-03/review_pending/."""
import json
import os

from loaders.mongodb_loader import PortfolioMongoLoader

OUT_DIR = "/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/2026-08-03/review_pending"
OUT_BASE = os.path.join(OUT_DIR, "sm004_2026-07-31_repair_r2_snapshot")

db = PortfolioMongoLoader()._db()

snap = {}
snap["captured_at"] = "2026-08-03T20:00:00Z"  # tag for audit
snap["repair"] = "R2 SM004 product_code reassignment 2026-07-31 ZO-002 -> SM004"

# 1. Position 23 rows for 2026-07-31 ZO-002 — capture business fields
pos_filter = {"position_date": "2026-07-31", "product_code": "ZO-002"}
pos_proj = {
    "_id": 0,
    "position_date": 1,
    "product_code": 1,
    "asset_wind_code": 1,
    "asset_name": 1,
    "quantity": 1,
    "weight": 1,
    "market_value": 1,
    "currency": 1,
    "share": 1,
    "nav": 1,
}
pos_rows = list(db["portfolio_position"].find(pos_filter, pos_proj))
pos_rows.sort(key=lambda r: (r.get("asset_wind_code") or ""))
snap["position_2026-07-31_ZO-002_rows"] = pos_rows
snap["position_2026-07-31_ZO-002_count"] = len(pos_rows)

# 2. Nav 1 row for 2026-07-31 ZO-002 — full content (excluding _id/updated_at)
nav_filter = {"nav_date": "2026-07-31", "product_code": "ZO-002"}
nav_proj = {"_id": 0, "updated_at": 0}
nav_rows = list(db["portfolio_nav"].find(nav_filter, nav_proj))
snap["nav_2026-07-31_ZO-002_rows"] = nav_rows
snap["nav_2026-07-31_ZO-002_count"] = len(nav_rows)

# 3. basic_info two keys
basic_错误 = list(
    db["portfolio_basic_info"].find(
        {"product_code": "ZO-002", "product_name": "SM004"}, {"_id": 0, "updated_at": 0}
    )
)
basic_合法 = list(
    db["portfolio_basic_info"].find(
        {"product_code": "SM004", "product_name": "ZO-002"}, {"_id": 0, "updated_at": 0}
    )
)
snap["basic_错误_反向_ZO-002_nameSM004_rows"] = basic_错误
snap["basic_错误_反向_ZO-002_nameSM004_count"] = len(basic_错误)
snap["basic_合法_SM004_nameZO-002_rows"] = basic_合法
snap["basic_合法_SM004_nameZO-002_count"] = len(basic_合法)

# 4. Historical SM004 sanity counts (read-only)
snap["nav_SM004_all_count"] = db["portfolio_nav"].count_documents(
    {"product_code": "SM004"}
)
snap["trade_SM004_all_count"] = db["portfolio_trade"].count_documents(
    {"product_code": "SM004"}
)
snap["position_SM004_all_count"] = db["portfolio_position"].count_documents(
    {"product_code": "SM004"}
)
mx = db["portfolio_nav"].find_one({}, sort=[("nav_date", -1)], projection={"nav_date": 1})
snap["portfolio_nav_max_nav_date"] = mx and mx.get("nav_date")

# 5. 001232.SZ scope check
snap["position_2026-07-31_001232.SZ_in_[SM004,ZO-002]_count"] = db[
    "portfolio_position"
].count_documents(
    {
        "position_date": "2026-07-31",
        "product_code": {"$in": ["SM004", "ZO-002"]},
        "asset_wind_code": "001232.SZ",
    }
)

# Write files
json_path = OUT_BASE + ".json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(snap, f, ensure_ascii=False, indent=2, sort_keys=False)

# Also dump a CSV of the 23 position rows for diff ease
import csv

csv_path = OUT_BASE + "_position_23rows.csv"
fieldnames = [
    "position_date",
    "product_code",
    "asset_wind_code",
    "asset_name",
    "quantity",
    "weight",
    "market_value",
    "currency",
    "share",
    "nav",
]
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for r in pos_rows:
        w.writerow({k: r.get(k) for k in fieldnames})

print(f"WROTE {json_path}")
print(f"WROTE {csv_path}")
print(f"position rows captured = {len(pos_rows)}")
print(f"nav rows captured      = {len(nav_rows)}")
print(f"basic_错误 captured    = {len(basic_错误)}")
print(f"basic_合法 captured    = {len(basic_合法)}")
print(f"max nav_date           = {snap['portfolio_nav_max_nav_date']}")