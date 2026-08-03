"""SM004 R2 repair post-DML verification.

Strict date-bounded checks per task acceptance criteria:
  - position 2026-07-31 SM004=23, ZO-002=0
  - position rows: same 23 (asset_wind_code, asset_name, market_value) as snapshot
  - nav 2026-07-31 SM004=1, ZO-002=0; trade 2026-07-31 SM004 count preserved (=1)
  - 001232.SZ on 2026-07-31 SM004/ZO-002 = 0
  - basic 合法 SM004 = 1; 错误 ZO-002 = 0
  - legal basic latest_nav = post-fix 2026-07-31 SM004 nav; latest_aum/share consistent
  - historical SM004 nav/trade/position counts unchanged (264/1193/8249)
  - explicitly assert no other date/product/collection got touched
"""
import json

from loaders.mongodb_loader import PortfolioMongoLoader

db = PortfolioMongoLoader()._db()
out = {}
all_pass = True


def check(name, cond, detail=None):
    global all_pass
    out[name] = {"pass": bool(cond), "detail": detail}
    if not cond:
        all_pass = False


# 1. position 7/31 SM004=23
n_pos_sm004 = db["portfolio_position"].count_documents(
    {"position_date": "2026-07-31", "product_code": "SM004"}
)
n_pos_zo002 = db["portfolio_position"].count_documents(
    {"position_date": "2026-07-31", "product_code": "ZO-002"}
)
check("position_7-31_SM004=23", n_pos_sm004 == 23, n_pos_sm004)
check("position_7-31_ZO-002=0", n_pos_zo002 == 0, n_pos_zo002)

# 2. position 23 rows: same business fields as snapshot (no data drift)
with open(
    "/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/2026-08-03/review_pending/sm004_2026-07-31_repair_r2_snapshot.json"
) as f:
    snap = json.load(f)
snap_keys = {"asset_wind_code", "asset_name", "market_value"}
post_proj = {"_id": 0, "asset_wind_code": 1, "asset_name": 1, "market_value": 1}
post_rows = list(
    db["portfolio_position"].find(
        {"position_date": "2026-07-31", "product_code": "SM004"}, post_proj
    )
)
post_rows.sort(key=lambda r: r["asset_wind_code"] or "")
post_compact = [{k: r.get(k) for k in snap_keys} for r in post_rows]
snap_compact = [
    {k: r.get(k) for k in snap_keys}
    for r in snap["position_2026-07-31_ZO-002_rows"]
]
snap_compact.sort(key=lambda r: r["asset_wind_code"] or "")
check(
    "position_23_rows_unchanged_business_fields",
    post_compact == snap_compact,
    f"mismatch_count={sum(1 for a,b in zip(post_compact, snap_compact) if a != b)}",
)

# 3. nav 7/31 SM004=1, ZO-002=0
n_nav_sm004 = db["portfolio_nav"].count_documents(
    {"nav_date": "2026-07-31", "product_code": "SM004"}
)
n_nav_zo002 = db["portfolio_nav"].count_documents(
    {"nav_date": "2026-07-31", "product_code": "ZO-002"}
)
check("nav_7-31_SM004=1", n_nav_sm004 == 1, n_nav_sm004)
check("nav_7-31_ZO-002=0", n_nav_zo002 == 0, n_nav_zo002)

# nav content == snapshot nav (same values, only product_code changed)
nav_row = db["portfolio_nav"].find_one(
    {"nav_date": "2026-07-31", "product_code": "SM004"},
    projection={"_id": 0, "nav": 1, "aum": 1, "share": 1},
)
snap_nav = snap["nav_2026-07-31_ZO-002_rows"][0]
check(
    "nav_7-31_SM004_values_equal_snapshot",
    nav_row.get("nav") == snap_nav.get("nav")
    and nav_row.get("aum") == snap_nav.get("aum")
    and nav_row.get("share") == snap_nav.get("share"),
    {"post": nav_row, "snap": snap_nav},
)

# 4. trade 7/31 SM004 count preserved = 1
n_trade_sm004 = db["portfolio_trade"].count_documents(
    {"trade_date": "2026-07-31", "product_code": "SM004"}
)
check("trade_7-31_SM004=1", n_trade_sm004 == 1, n_trade_sm004)

# 5. 001232.SZ on 2026-07-31 SM004/ZO-002 = 0
n_001232 = db["portfolio_position"].count_documents(
    {
        "position_date": "2026-07-31",
        "product_code": {"$in": ["SM004", "ZO-002"]},
        "asset_wind_code": "001232.SZ",
    }
)
check("position_7-31_001232.SZ_in_[SM004,ZO-002]=0", n_001232 == 0, n_001232)

# 6. basic 合法 SM004 = 1, 错误 ZO-002 = 0
n_basic_legal = db["portfolio_basic_info"].count_documents(
    {"product_code": "SM004", "product_name": "ZO-002"}
)
n_basic_错误 = db["portfolio_basic_info"].count_documents(
    {"product_code": "ZO-002", "product_name": "SM004"}
)
check("basic_合法_SM004=1", n_basic_legal == 1, n_basic_legal)
check("basic_错误_ZO-002=0", n_basic_错误 == 0, n_basic_错误)

# 7. legal basic latest_* equals post-fix 2026-07-31 SM004 nav
legal = db["portfolio_basic_info"].find_one(
    {"product_code": "SM004", "product_name": "ZO-002"}, {"_id": 0}
)
check(
    "basic_合法_latest_nav_eq_post-fix_nav",
    legal.get("latest_nav") == nav_row.get("nav"),
    {"latest_nav_legal": legal.get("latest_nav"), "post_nav": nav_row.get("nav")},
)
check(
    "basic_合法_latest_aum_eq_post-fix_aum",
    legal.get("latest_aum") == nav_row.get("aum"),
    {"latest_aum_legal": legal.get("latest_aum"), "post_aum": nav_row.get("aum")},
)
check(
    "basic_合法_latest_share_eq_post-fix_share",
    legal.get("latest_share") == nav_row.get("share"),
    {"latest_share_legal": legal.get("latest_share"), "post_share": nav_row.get("share")},
)

# 8. SM004 historical counts unchanged
nav_all = db["portfolio_nav"].count_documents({"product_code": "SM004"})
trade_all = db["portfolio_trade"].count_documents({"product_code": "SM004"})
pos_all = db["portfolio_position"].count_documents({"product_code": "SM004"})
check("nav_SM004_all_unchanged_264", nav_all == 264, nav_all)
check("trade_SM004_all_unchanged_1193", trade_all == 1193, trade_all)
check("position_SM004_all_unchanged_8249", pos_all == 8249, pos_all)

# 9. No other dates for position changed
# Other SM004 dates: any position row with position_date != 2026-07-31 should equal
# (SM004 historical count - 23) since only the 7/31 row was tagged to be reassigned
# from ZO-002. Position SM004 historical went from 8249 (snapshot) to current.
other_pos_dates = db["portfolio_position"].count_documents(
    {"product_code": "SM004", "position_date": {"$ne": "2026-07-31"}}
)
# snapshot had SM004 all = 8249 (no 7/31 SM004 before). After DML SM004 all still 8249.
check(
    "position_SM004_non-7-31_count_unchanged",
    other_pos_dates == 8249,
    other_pos_dates,
)

# 10. No other date touched for ZO-002 (which should now have 0 position rows period
# but the task did not mandate delete-non-7-31; just no writes on other dates).
# Confirm: the only ZO-002 rows in portfolio_position should be zero (since 7/31 was
# the only ZO-002 rowset that existed post-pipeline).
zo_all = db["portfolio_position"].count_documents({"product_code": "ZO-002"})
check("position_ZO-002_all=0", zo_all == 0, zo_all)

# Same for nav
zo_nav_all = db["portfolio_nav"].count_documents({"product_code": "ZO-002"})
check("nav_ZO-002_all=0", zo_nav_all == 0, zo_nav_all)

# 11. SM004 trade historical — the 2026-07-31 trade row should not have been touched
n_trade_sm004_7_31 = db["portfolio_trade"].count_documents(
    {"trade_date": "2026-07-31", "product_code": "SM004"}
)
check("trade_7-31_SM004_unmodified=1", n_trade_sm004_7_31 == 1, n_trade_sm004_7_31)

# 12. portfolio_basic_info total = should now be only the legal SM004 (1) record,
# assuming no other ZO-002-* records existed. Quick check on total:
all_basic = db["portfolio_basic_info"].count_documents(
    {"$or": [{"product_code": "SM004"}, {"product_code": "ZO-002"}]}
)
# Pre-fix: 2 (合法 + 错误). Post-fix: 1 (only 合法). The 错误 was deleted.
check("basic_total_SM004_or_ZO-002=1", all_basic == 1, all_basic)

out["ALL_PASS"] = all_pass
print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
print("\nALL_PASS =", all_pass)