#!/usr/bin/env python3
"""
扫描某归档目录下"已归档 vs 已跑过 pipeline"的差异。

用法：
    python check_pending_pipeline_runs.py [--date YYYY-MM-DD] [--json]

输出：
    - image_cache 唯一 hash 数（飞书推送的全部）
    - 归档目录 portfolio_*.jpg 唯一 hash 数（agent 第一步归档的）
    - 归档目录 xlsx / pending csv / vision_raw 三种 pipeline 痕迹数
    - 哪些图已跑过 / 未跑过（按 jpg 命名时间戳 vs 产物时间戳窗口匹配）
    - 完整待跑列表（按归档文件名排序）

实战背景（2026-06-27 用户多批推送 + pipeline 落盘逻辑不统一）：
    用户分多批（9:46 + 10:02 + 10:10）推同一批持仓截图，image_cache unique
    数看着不变，但 pipeline 实际只跑了第一轮的子集。仅凭"归档目录里有"
    不能说"全部入库了"——必须看 pipeline 痕迹。

判定规则（每张 jpg 独立判定）：

    1. jpg 命名时间戳 T_jpg = (YYYY-MM-DD, HHMMSS) — agent 归档时刻
    2. 候选 pipeline 产物（同 jpg_hash 之后 ≤ 30 分钟内出现的 xlsx / pending / vision_raw）
    3. 同 hash 允许多个 jpg 共用同一产物（按命名时间顺序贪心分配）
    4. jpg 判定为"已跑过"当且仅当：找到候选产物
    5. 无 jpg 但有同 hash archive（cache 清理残留）也归为"已跑过"（按 MongoDB source_image 二次校验可选）

历史教训（2026-06-27）：
    - 不要用 "xlsx_count >= 80% * archive_count" 启发式（误报"73 张未跑"，实际 0 张）
    - HHMMSS 整数差要按 (HHMMSS_a - HHMMSS_b) 算分钟，不是字符串差
    - xlsx 命名时间戳是 OCR 落盘时刻（晚于 jpg 归档时刻），不是 jpg 命名时间戳
    - pending csv 也要算 pipeline 跑过（不是只有 xlsx）
    - vision_raw/vision_error 也要算（pipeline 跑过但 OCR 失败也算）
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_REPO = Path("/home/pascal/workspace/yquant-investment")
DEFAULT_IMAGE_CACHE = Path("/home/pascal/.hermes/profiles/yquant/image_cache")
SM_ROOT = DEFAULT_REPO / "skills/data/source/smart-money"

# Pipeline 产物命名约定
XLSX_NAME_RE = re.compile(r"^(portfolio|trade)_(\d{8})_(\d{6})(_\d+)?\.xlsx$")
PENDING_NAME_RE = re.compile(r"^(portfolio|trade)_(\d{8})_(\d{6})(_\d+)?_pending\.csv$")
VISION_RAW_RE = re.compile(r"^pic_(\d{8})_(\d{6}).*_vision_(raw|error|retry)\.json$")

# 窗口：jpg 命名时间戳之后多少秒内的产物才算这张 jpg 的
WINDOW_SECONDS = 30 * 60  # 30 分钟


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def hhmmss_to_seconds(s: str) -> int:
    """HHMMSS → 当日 0 点起的秒数。"""
    h = int(s[0:2])
    m = int(s[2:4])
    s_ = int(s[4:6])
    return h * 3600 + m * 60 + s_


def parse_jpg_ts(name: str) -> int | None:
    """从 jpg 命名提取 HHMMSS 当日秒数。

    兼容三种命名：
    - portfolio_2026-06-27_201808.jpg  (YYYY-MM-DD_HHMMSS)
    - portfolio_20260627_201808.jpg    (YYYYMMDD_HHMMSS)
    - trade_20260627_201858.jpg
    关键：取文件名去掉 .jpg 后，末尾 _HHMMSS 是 6 位数字。
    jpg 命名不会有 _NN 序号后缀（只有 xlsx 会有）。
    """
    base = name.replace(".jpg", "")
    m = re.search(r"_(\d{6})$", base)
    if not m:
        return None
    return hhmmss_to_seconds(m.group(1))


def parse_product_ts(name: str) -> int | None:
    """从 xlsx/pending/vision_raw 命名提取 HHMMSS 当日秒数。

    命名约定：
    - {type}_YYYYMMDD_HHMMSS[(_NN)][.xlsx|_pending.csv]  e.g. portfolio_20260627_201858.xlsx
    - pic_YYYYMMDD_HHMMSS_vision_(raw|error|retry).json  e.g. pic_20260627_035246_vision_raw.json
    关键：HHMMSS 是 _YYYYMMDD_ 之后的下 6 位数字。
    """
    base = name
    for ext in [".xlsx", ".csv", ".json"]:
        if base.endswith(ext):
            base = base[: -len(ext)]
            break
    # 去掉 _NN 序号后缀（精确：必须是 _\d+ 且不是 _HHMMSS 的 6 位数字）
    # 即：剥离后剩下的 6 位数字是 HHMMSS
    base_no_2 = re.sub(r"_(\d{2})$", "", base)  # 候选：去掉末尾 2 位
    if re.search(r"_(\d{6})$", base_no_2):
        base = base_no_2
    # 去掉 _pending 后缀
    base = re.sub(r"_pending$", "", base)
    # 去掉 vision raw / error / retry 尾巴
    base = re.sub(r"_vision_(raw|error|retry)$", "", base)
    # 取 _YYYYMMDD_ 之后的下 6 位数字
    m = re.search(r"_(\d{6})$", base)
    if not m:
        return None
    return hhmmss_to_seconds(m.group(1))


def scan_dir(d: Path) -> dict[str, Path]:
    """返回 {md5: path} 字典（按 md5 去重，保留首个）。"""
    out: dict[str, Path] = {}
    for p in sorted(d.glob("*.jpg")):
        h = md5(p)
        out.setdefault(h, p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="归档日期 YYYY-MM-DD（默认今天）", default=None)
    ap.add_argument("--repo", default=str(DEFAULT_REPO))
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--window-minutes", type=int, default=30, help="jpg 命名后多少分钟内的产物算这张 jpg 跑过")
    args = ap.parse_args()

    repo = Path(args.repo)
    sm = repo / "skills/data/source/smart-money"
    date = args.date or dt.date.today().isoformat()
    window_sec = args.window_minutes * 60

    image_cache = DEFAULT_IMAGE_CACHE
    archive_dir = sm / date / "image"
    pending_dir = sm / date / "review_pending"

    if not archive_dir.exists():
        print(f"❌ 归档目录不存在: {archive_dir}")
        return 1

    # 1) image_cache 里所有 unique hash
    cache_hashes: dict[str, Path] = {}
    if image_cache.exists():
        cache_hashes = scan_dir(image_cache)

    # 2) 归档目录 jpg unique hash
    archive_hashes: dict[str, Path] = scan_dir(archive_dir)

    # 3) pipeline 痕迹（按 HHMMSS 当日秒数索引）
    xlsx_files = sorted(archive_dir.glob("*.xlsx"))
    xlsx_times: dict[int, list[Path]] = defaultdict(list)
    for x in xlsx_files:
        ts = parse_product_ts(x.name)
        if ts is not None:
            xlsx_times[ts].append(x)

    pending_files = sorted(pending_dir.glob("*_pending.csv")) if pending_dir.exists() else []
    pending_times: dict[int, list[Path]] = defaultdict(list)
    for p in pending_files:
        ts = parse_product_ts(p.name)
        if ts is not None:
            pending_times[ts].append(p)

    vision_files = sorted(archive_dir.glob("*vision_*.json"))
    vision_times: dict[int, list[Path]] = defaultdict(list)
    for v in vision_files:
        ts = parse_product_ts(v.name)
        if ts is not None:
            vision_times[ts].append(v)

    # 4) 对每张 jpg 判定（按命名时间戳 + 贪心分配）
    sorted_product_ts = sorted(set(list(xlsx_times.keys()) + list(pending_times.keys()) + list(vision_times.keys())))

    per_jpg_outcome: dict[str, dict] = {}  # jpg_basename -> {ran, via, products[]}
    used_products: set[tuple[int, str, int]] = set()  # (ts, product_basename, index)

    archive_jpgs = sorted(archive_hashes.values(), key=lambda p: parse_jpg_ts(p.name) or 0)

    for jpg in archive_jpgs:
        jpg_ts = parse_jpg_ts(jpg.name)
        if jpg_ts is None:
            per_jpg_outcome[jpg.name] = {"ran": False, "via": "no_ts", "products": []}
            continue
        ran = []
        via = []
        for ts in sorted_product_ts:
            if ts < jpg_ts:
                continue
            if ts - jpg_ts > window_sec:
                break  # 时间窗口已过

            # 贪心从 xlsx / pending / vision 中取一个未用的产物
            for kind, times in [("xlsx", xlsx_times), ("pending", pending_times), ("vision", vision_times)]:
                if ts in times and times[ts]:
                    p = times[ts].pop(0)
                    ran.append(p.name)
                    via.append(kind)
                    break  # 一张 jpg 一次只匹配一个产物
        if ran:
            per_jpg_outcome[jpg.name] = {"ran": True, "via": via, "products": ran}
        else:
            per_jpg_outcome[jpg.name] = {"ran": False, "via": None, "products": []}

    # 5) 汇总
    ran_count = sum(1 for v in per_jpg_outcome.values() if v["ran"])
    not_ran = [k for k, v in per_jpg_outcome.items() if not v["ran"]]

    in_cache_and_archive = cache_hashes.keys() & archive_hashes.keys()
    archive_only = archive_hashes.keys() - cache_hashes.keys()
    cache_only = cache_hashes.keys() - archive_hashes.keys()

    summary = {
        "date": date,
        "image_cache_unique": len(cache_hashes),
        "archive_unique_jpg": len(archive_hashes),
        "xlsx_count": len(xlsx_files),
        "pending_count": len(pending_files),
        "vision_raw_count": len(vision_files),
        "ran_count": ran_count,
        "not_ran_count": len(not_ran),
        "in_cache_and_archive": len(in_cache_and_archive),
        "archive_only": len(archive_only),
        "cache_only": len(cache_only),
        "not_ran_files": not_ran,
        "per_jpg_outcome": per_jpg_outcome,
    }

    if args.json:
        # per_jpg_outcome 太长，省略
        out = {k: v for k, v in summary.items() if k != "per_jpg_outcome"}
        out["not_ran_files_sample"] = not_ran[:20]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # 人类可读输出
    print(f"📦 image_cache unique hash: {len(cache_hashes)}")
    print(f"📁 归档目录 jpg unique hash: {len(archive_hashes)}")
    print(f"📊 xlsx: {len(xlsx_files)} | pending csv: {len(pending_files)} | vision_raw json: {len(vision_files)}")
    print()
    print(f"🔁 cache ∩ archive: {len(in_cache_and_archive)} 张")
    print(f"📂 archive \\ cache: {len(archive_only)} 张 (cache 已清)")
    print(f"🆕 cache \\ archive: {len(cache_only)} 张 (飞书新推未归档)")
    print()
    print(f"✅ 跑过 pipeline: {ran_count} / {len(per_jpg_outcome)} 张")
    print(f"❌ 未跑 pipeline: {len(not_ran)} 张")
    if not_ran:
        print()
        print("=== 未跑的 jpg ===")
        for n in not_ran:
            print(f"  {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
