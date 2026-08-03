"""Final scope verification — confirm only the 2026-07-31 SM004 reassignment
touched the database. Historical rows untouched.

Pre-fix snapshot totals (from snapshot JSON):
  nav_SM004_all = 264, trade_SM004_all = 1193, position_SM004_all = 8249
  nav_2026-07-31_SM004 = 0, position_2026-07-31_SM004 = 0

After fix:
  +1 nav row on 2026-07-31 moved ZO-002->SM004  → SM004 nav all = 264+1 = 265
  +23 position rows on 2026-07-31 moved ZO-002->SM004  → SM004 position all = 8249+23 = 8272
  Trade collection: not touched (same product_code for trade rows)
"""
import json

from loaders.mongodb_loader import PortfolioMongoLoader

db = PortfolioMongoLoader()._db()

with open(
    "/home/pascal/workspace/yquant-investment/skills/data/source/smart-money/2026-08-03/review_pending/sm004_2026-07-31_repair_r2_snapshot.json"
) as f:
    snap = json.load(f)

# Historical (excluding 7/31) counts must equal pre-snapshot totals
nav_sm004_other = db["portfolio_nav"].count_documents(
    {"product_code": "SM004", "nav_date": {"$ne": "2026-07-31"}}
)
pos_sm004_other = db["portfolio_position"].count_documents(
    {"product_code": "SM004", "position_date": {"$ne": "2026-07-31"}}
)
trade_sm004_other = db["portfolio_trade"].count_documents(
    {"product_code": "SM004", "trade_date": {"$ne": "2026-07-31"}}
)

print("=== Historical (non-2026-07-31) SM004 counts ===")
print(f"nav_SM004_other        = {nav_sm004_other}  (expected {snap['nav_SM004_all_count']})  match={nav_sm004_other == snap['nav_SM004_all_count']}")
print(f"position_SM004_other   = {pos_sm004_other}  (expected {snap['position_SM004_all_count']})  match={pos_sm004_other == snap['position_SM004_all_count']}")
print(f"trade_SM004_other      = {trade_sm004_other}  (expected {snap['trade_SM004_all_count']})  match={trade_sm004_other == snap['trade_SM004_all_count']}")

# ZO-002 collection — should now be empty for position & nav
# (pre-fix ZO-002 was 23 position + 1 nav, all on 2026-07-31)
print()
print("=== ZO-002 totals post-fix (must be 0 for position & nav; trade untouched so >0 historical) ===")
zo_pos = db["portfolio_position"].count_documents({"product_code": "ZO-002"})
zo_nav = db["portfolio_nav"].count_documents({"product_code": "ZO-002"})
zo_trade = db["portfolio_trade"].count_documents({"product_code": "ZO-002"})
print(f"position_ZO-002 = {zo_pos}  (expected 0)")
print(f"nav_ZO-002      = {zo_nav}  (expected 0)")
print(f"trade_ZO-002    = {zo_trade}  (historical, unchanged from before)")

# Basic info remaining — only the legal SM004 record
print()
print("=== basic_info scope ===")
print(f"basic total count = {db['portfolio_basic_info'].count_documents({})}")