#!/usr/bin/env python3
"""Read-only ad-hoc query against tradingagents MongoDB.

Usage:
    python scripts/query_portfolio.py --product SM002 --start 2026-06-20 --end 2026-06-25
    python scripts/query_portfolio.py --product SM002 --no-date           # 全表
    python scripts/query_portfolio.py --product SM002 --list-products     # 只列 distinct codes

Environment: MongoDB credentials read from skills/.env (via PortfolioMongoLoader).
Always run with project root .venv:
    PYTHONPATH=skills/data/data-pipeline/scripts:/home/pascal/workspace/yquant-investment \
      /home/pascal/workspace/yquant-investment/.venv/bin/python scripts/query_portfolio.py ...
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).parent.resolve()
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS.parents[3]))  # project root

from loaders.mongodb_loader import PortfolioMongoLoader  # noqa: E402

COLLECTIONS = {
    "portfolio_basic_info": None,  # no business date field
    "portfolio_nav": "nav_date",
    "portfolio_position": "position_date",
    "portfolio_trade": "trade_date",
}


def query(db, collection: str, date_field: str | None, product: str, start: str | None, end: str | None) -> list[dict]:
    coll = db[collection]
    flt: dict = {"product_code": product}
    if date_field and start and end:
        flt[date_field] = {"$gte": start, "$lte": end}
    cur = coll.find(flt)
    if date_field:
        cur = cur.sort([(date_field, 1)])
    rows = []
    for r in cur:
        r["_id"] = str(r["_id"])
        rows.append(r)
    return rows


def sanity_check(db, product: str) -> dict:
    """Total document counts + closest alternatives if exact match is empty."""
    out: dict = {"exact_match_total": {}, "candidates": [], "all_distinct": []}
    for cn, df in COLLECTIONS.items():
        out["exact_match_total"][cn] = db[cn].count_documents({"product_code": product})

    if all(v == 0 for v in out["exact_match_total"].values()):
        # Try common variants
        variants = {product, product.upper(), product.lower(), product.replace("-", "_"), product.replace("-", "")}
        for cn in ("portfolio_position", "portfolio_basic_info"):
            for v in variants:
                n = db[cn].count_documents({"product_code": v})
                if n:
                    out["candidates"].append({"collection": cn, "product_code": v, "count": n})

        # Fuzzy regex on basic_info (smallest, fastest)
        rgx = re.compile(f"^{re.escape(product[:2])}.*{re.escape(product[-2:])}$", re.IGNORECASE)
        hits = list(db["portfolio_basic_info"].find({"product_code": rgx}, {"product_code": 1, "_id": 0}).limit(5))
        if hits:
            out["candidates"].append({"regex": rgx.pattern, "matches": [h["product_code"] for h in hits]})

    out["all_distinct"] = sorted(db["portfolio_position"].distinct("product_code"))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--product", required=True, help="product_code, e.g. SM002")
    p.add_argument("--start", help="YYYY-MM-DD")
    p.add_argument("--end", help="YYYY-MM-DD")
    p.add_argument("--list-products", action="store_true", help="Only print distinct product_codes and exit")
    p.add_argument("--sanity", action="store_true", help="Print sanity-check diagnostic instead of rows")
    args = p.parse_args()

    loader = PortfolioMongoLoader()
    db = loader._db()  # Note: _db(), NOT _client() — see skill SKILL.md

    if args.list_products:
        distincts = sorted(db["portfolio_position"].distinct("product_code"))
        print(f"portfolio_position distinct product_code ({len(distincts)}): {distincts}")
        return

    if args.sanity:
        print(json.dumps(sanity_check(db, args.product), ensure_ascii=False, indent=2))
        return

    for coll, df in COLLECTIONS.items():
        rows = query(db, coll, df, args.product, args.start, args.end)
        scope = f"{df} in [{args.start},{args.end}]" if df and args.start and args.end else "全表"
        print(f"\n--- {coll} | {scope} | count={len(rows)} ---")
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, default=str))

    print("\n=== sanity ===")
    print(json.dumps(sanity_check(db, args.product), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()