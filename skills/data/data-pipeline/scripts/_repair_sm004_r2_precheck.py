"""Preflight for SM004 R2 repair — read-only counts on 2026-07-31 only.
No writes, no inserts, no deletes. Pure verification."""
import json
from loaders.mongodb_loader import PortfolioMongoLoader

db = PortfolioMongoLoader()._db()

out = {}
out["position_2026-07-31_ZO-002"] = db["portfolio_position"].count_documents(
    {"position_date": "2026-07-31", "product_code": "ZO-002"}
)
out["position_2026-07-31_SM004"] = db["portfolio_position"].count_documents(
    {"position_date": "2026-07-31", "product_code": "SM004"}
)
out["nav_2026-07-31_ZO-002"] = db["portfolio_nav"].count_documents(
    {"nav_date": "2026-07-31", "product_code": "ZO-002"}
)
out["nav_2026-07-31_SM004"] = db["portfolio_nav"].count_documents(
    {"nav_date": "2026-07-31", "product_code": "SM004"}
)
out["basic_错误_反向_ZO-002_nameSM004"] = db["portfolio_basic_info"].count_documents(
    {"product_code": "ZO-002", "product_name": "SM004"}
)
out["basic_合法_SM004_nameZO-002"] = db["portfolio_basic_info"].count_documents(
    {"product_code": "SM004", "product_name": "ZO-002"}
)
out["position_2026-07-31_001232.SZ_in_[SM004,ZO-002]"] = db[
    "portfolio_position"
].count_documents(
    {
        "position_date": "2026-07-31",
        "product_code": {"$in": ["SM004", "ZO-002"]},
        "asset_wind_code": "001232.SZ",
    }
)
out["trade_2026-07-31_SM004"] = db["portfolio_trade"].count_documents(
    {"trade_date": "2026-07-31", "product_code": "SM004"}
)
out["trade_2026-07-31_ZO-002"] = db["portfolio_trade"].count_documents(
    {"trade_date": "2026-07-31", "product_code": "ZO-002"}
)
# historical SM004 sanity (read counts only)
out["nav_SM004_all"] = db["portfolio_nav"].count_documents({"product_code": "SM004"})
out["trade_SM004_all"] = db["portfolio_trade"].count_documents(
    {"product_code": "SM004"}
)
out["position_SM004_all"] = db["portfolio_position"].count_documents(
    {"product_code": "SM004"}
)
mx = db["portfolio_nav"].find_one({}, sort=[("nav_date", -1)], projection={"nav_date": 1})
out["portfolio_nav_max_nav_date"] = mx and mx.get("nav_date")

print(json.dumps(out, ensure_ascii=False, indent=2))