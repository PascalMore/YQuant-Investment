#!/usr/bin/env python3
"""
审计 pending CSV：判断哪些行还未真正入库 MongoDB。

判定逻辑（4 类状态）：
  - ✅ 已在 DB（已入库）
  - ❌ 孤儿 CSV（CSV 状态=resolved/confirmed，但实际未入 DB——需 --confirm-all 重试）
  - ⏸ 待人工复核（CSV 状态=pending_review/missing_master，需用户决定）
  - 🚫 跳过（CSV 行 Wind 代码为空、无法入）

用法：
  .venv/bin/python audit_pending_unmigrated.py                     # 扫描所有日期
  .venv/bin/python audit_pending_unmigrated.py --date 2026-06-22   # 单日期
  .venv/bin/python audit_pending_unmigrated.py --format csv         # CSV 报告
  .venv/bin/python audit_pending_unmigrated.py --action confirm-all # 自动 confirm-all
"""
import argparse
import csv
import os
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))
from loaders.mongodb_loader import PortfolioMongoLoader  # noqa: E402

SOURCE_ROOT = _BASE.parent.parent.parent / "data" / "source" / "smart-money"


def audit_pending_csvs(date_filter: str | None = None) -> dict:
    """扫描所有 review_pending/*_pending.csv，对照 MongoDB 判别状态。"""
    db = PortfolioMongoLoader()._db()
    pending_dirs = sorted(SOURCE_ROOT.glob("*/review_pending"))

    buckets = {
        "in_db": [],          # 已在 MongoDB（孤儿 CSV，可归档）
        "orphan_csv": [],     # CSV 说 resolved 但 DB 无
        "needs_review": [],   # CSV 状态 pending_review/missing_master，未入
        "skipped": [],        # Wind 代码空
    }
    stats = {"files": 0, "rows": 0}

    for rp_dir in pending_dirs:
        date_dir = rp_dir.parent.name
        if date_filter and date_dir != date_filter:
            continue
        for csv_path in sorted(rp_dir.glob("*_pending.csv")):
            stats["files"] += 1
            with csv_path.open(encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    stats["rows"] += 1
                    biz_date = row.get("截止日期", "")
                    product = row.get("产品代码", "")
                    code = row.get("Wind代码", "").strip()
                    asset = row.get("资产名称", "")
                    csv_status = row.get("名称复核状态", "?")

                    coll = "portfolio_trade" if "trade_" in csv_path.name else "portfolio_position"
                    date_field = "trade_date" if coll == "portfolio_trade" else "position_date"

                    if not code:
                        buckets["skipped"].append({
                            "date_dir": date_dir, "csv": csv_path.name,
                            "biz_date": biz_date, "product": product,
                            "code": code, "asset": asset, "csv_status": csv_status,
                        })
                        continue

                    rec = db[coll].find_one({
                        date_field: biz_date,
                        "product_code": product,
                        "asset_wind_code": code,
                    })
                    if rec:
                        buckets["in_db"].append({
                            "date_dir": date_dir, "csv": csv_path.name,
                            "biz_date": biz_date, "product": product,
                            "code": code, "asset": asset, "csv_status": csv_status,
                            "db_name": rec.get("asset_name", ""),
                        })
                    elif csv_status in {"resolved", "confirmed", ""}:
                        # CSV 说已审但 DB 无 = 孤儿
                        buckets["orphan_csv"].append({
                            "date_dir": date_dir, "csv": csv_path.name,
                            "biz_date": biz_date, "product": product,
                            "code": code, "asset": asset, "csv_status": csv_status,
                        })
                    else:
                        # pending_review / missing_master / 其他待审
                        buckets["needs_review"].append({
                            "date_dir": date_dir, "csv": csv_path.name,
                            "biz_date": biz_date, "product": product,
                            "code": code, "asset": asset, "csv_status": csv_status,
                        })

    return {"stats": stats, "buckets": buckets}


def print_human_report(result: dict) -> None:
    stats = result["stats"]
    buckets = result["buckets"]
    print("=" * 80)
    print("Pending CSV 审计报告")
    print("=" * 80)
    print(f"扫描 CSV: {stats['files']} 个, 总行数: {stats['rows']}")
    print()
    print(f"✅ 已在 MongoDB（可归档 CSV）:        {len(buckets['in_db']):>4d} 行")
    print(f"❌ 孤儿 CSV（CSV resolved 但 DB 无）:  {len(buckets['orphan_csv']):>4d} 行  ← 需 --confirm-all 重试")
    print(f"⏸  待人工复核（pending/missing）:      {len(buckets['needs_review']):>4d} 行  ← 等用户确认")
    print(f"🚫 Wind 代码空（无法入）:              {len(buckets['skipped']):>4d} 行")
    print()

    if buckets["orphan_csv"]:
        print("-" * 80)
        print("❌ 孤儿 CSV 详细（CSV 状态=resolved 但 DB 无记录）:")
        print("-" * 80)
        print(f"  {'归档日':12s} {'业务日':12s} {'产品':6s} {'Wind代码':10s} {'资产名':12s} {'CSV':12s}")
        for r in buckets["orphan_csv"]:
            print(
                f"  {r['date_dir']:12s} {r['biz_date']:12s} "
                f"{r['product']:6s} {r['code']:10s} {r['asset']:12s} {r['csv_status']:12s}"
            )
        print()

    if buckets["needs_review"]:
        print("-" * 80)
        print("⏸ 待人工复核详细:")
        print("-" * 80)
        print(f"  {'归档日':12s} {'业务日':12s} {'产品':6s} {'Wind代码':10s} {'资产名':12s} {'CSV':14s}")
        for r in buckets["needs_review"][:50]:
            print(
                f"  {r['date_dir']:12s} {r['biz_date']:12s} "
                f"{r['product']:6s} {r['code']:10s} {r['asset']:12s} {r['csv_status']:14s}"
            )
        if len(buckets["needs_review"]) > 50:
            print(f"  ... ({len(buckets['needs_review']) - 50} more)")
        print()

    if not buckets["orphan_csv"] and not buckets["needs_review"]:
        print("🎉 无需处理的 pending：")
        print("  • 孤儿 CSV 0 条（所有 resolved 都已入 DB）")
        print("  • 待人工复核 0 条")
        print("  • 可以归档所有 review_pending/ 到 review_resolved/")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--date", help="只审计指定日期 (YYYY-MM-DD)")
    parser.add_argument("--format", choices=["human", "csv"], default="human")
    parser.add_argument(
        "--action",
        choices=["report", "confirm-all"],
        help="action=confirm-all 时对所有 orphan_csv + needs_review 跑 --confirm-all",
    )
    args = parser.parse_args()

    result = audit_pending_csvs(date_filter=args.date)
    if args.format == "human":
        print_human_report(result)

    if args.action == "confirm-all":
        from load_pending_confirmed import _process_single_csv
        targets = result["buckets"]["orphan_csv"] + result["buckets"]["needs_review"]
        if not targets:
            print("Nothing to confirm-all.")
            return 0
        csv_to_rows: dict[str, list[dict]] = {}
        for r in targets:
            csv_to_rows.setdefault(f"{r['date_dir']}/review_pending/{r['csv']}", []).append(r)
        print(f"Auto confirm-all {len(targets)} rows in {len(csv_to_rows)} CSV file(s)...")
        for csv_rel, rows in csv_to_rows.items():
            csv_abs = SOURCE_ROOT / csv_rel
            res = _process_single_csv(str(csv_abs), confirm_all=True)
            print(f"  {csv_abs.name}: loaded={res.get('loaded', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
