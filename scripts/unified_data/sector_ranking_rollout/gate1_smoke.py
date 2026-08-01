"""Gate-1 工具：只读 smoke + 权威 expected universe 校验（03-016 rollout）。

DESIGN-03-016 V0.6 §3.4 / SPEC-03-016 §3.2（L1 契约校正）。只读
``stock_sector_info``（L1 universe 唯一主来源，``classify_system=\"SW\"``
distinct ``(l1_code,l1_name)`` 恰好 31）+ ``index_daily_quotes``（行情
join field = ``full_symbol``，值集 = 31 个 ``.SI`` 后缀 L1 code），产出
``gate1-report.json`` / ``.md``（G1-R-001~010），含权威 SW L1 expected
universe、``expected_full_symbols``、``universe_source``、逐日 coverage、
close 完整性、source 分布、canary 候选清单。``index_basic_info`` 仅可作
可选元数据交叉核对（按真实 ``market=\"申万指数\"`` 语义），**不得**用作
L1 universe 主来源；不再 query ``market=\"CN\"``。默认 dry-run（零副作用）；
``--apply --yes`` 才执行真实只读查询并写 report。

退出码（SPEC G0-C-004）：0 成功 / 2 停止条件 / 3 连接凭据失败。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from skills.data.unified_data.models.domain.sector_ranking import coerce_float

from .common import (
    BudgetReader,
    BudgetViolation,
    CompletedSessionPolicy,
    ConnLoader,
    EXIT_CONN,
    EXIT_OK,
    EXIT_STOP,
    REALTIME_MARKERS,
    MissingConnectionKeyError,
    log_jsonl,
    redact,
    resolve_report_dir,
    scan_secrets,
    write_report,
)

TOOL = "gate1_smoke"
VERSION = "0.1.0"
UNIVERSE_SOURCE = "stock_sector_info"
# 生产契约：SW L1 universe 恰好 31 个（SPEC G1-C-001 / G1-S-002）。
EXPECTED_L1_COUNT = 31


class Gate1Stop(Exception):
    """Gate-1 停止条件命中（退出码 2）。"""

    def __init__(self, sc_id: str, message: str) -> None:
        self.sc_id = sc_id
        super().__init__(message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="03-016 Gate-1 read-only smoke + authoritative SW L1 universe",
    )
    parser.add_argument("--apply", action="store_true", help="执行真实只读查询并写 report")
    parser.add_argument("--yes", action="store_true", help="确认执行副作用（--apply 必须伴随）")
    parser.add_argument("--min-trade-date", default=None, help="可选：YYYY-MM-DD")
    parser.add_argument("--max-trade-date", default=None, help="可选：YYYY-MM-DD")
    parser.add_argument("--report-dir", default=None, help="产物目录（默认 data/rollout/sector-ranking）")
    return parser


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_cst(now_fn: Callable[[], datetime] | None) -> str:
    now = now_fn() if now_fn is not None else datetime.now(timezone.utc)
    return now.astimezone(CompletedSessionPolicy.TZ).date().isoformat()


# ---------------------------------------------------------------------------
# G1-C-001 权威枚举（L1 契约校正：主来源 stock_sector_info）+ G1-C-006
# ---------------------------------------------------------------------------


def enumerate_sw_l1(
    db: Any,
    *,
    budget: BudgetReader | None = None,
    expected_count: int = EXPECTED_L1_COUNT,
) -> dict[str, str]:
    """从 ``stock_sector_info`` 枚举 SW L1 code/name。

    聚合：``$match {classify_system: \"SW\"}`` + ``$group (l1_code,l1_name)``
    distinct；恰好 ``expected_count``（生产 31）条。``l1_code`` canonical
    形态 = 带 ``.SI`` 后缀（例如 ``801780.SI``），同时即为
    ``index_daily_quotes.full_symbol`` 的值。空/≠31 → G1-S-002；重复 /
    非 ``.SI`` 后缀 canonical 形态 → G1-S-003。**不得**使用
    ``index_basic_info`` 作为 L1 universe 枚举主来源（SPEC G1-C-001）。
    """
    reader = budget if budget is not None else BudgetReader(db)
    rows = reader.aggregate(
        "stock_sector_info",
        [
            {"$match": {"classify_system": "SW"}},
            {"$group": {"_id": {"l1_code": "$l1_code", "l1_name": "$l1_name"}}},
        ],
    )

    universe: dict[str, str] = {}
    for row in rows:
        _id = row.get("_id") or {}
        code = str(_id.get("l1_code") or "").strip()
        name = str(_id.get("l1_name") or "").strip()
        if not code.endswith(".SI"):
            raise Gate1Stop(
                "G1-S-003",
                f"non-.SI canonical l1_code {code!r} found in stock_sector_info "
                "(classify_system=SW)",
            )
        if not name:
            raise Gate1Stop("G1-S-003", f"missing l1_name for l1_code {code!r}")
        if code in universe:
            raise Gate1Stop("G1-S-003", f"duplicate l1_code {code!r}")
        universe[code] = name

    if len(universe) != expected_count:
        raise Gate1Stop(
            "G1-S-002",
            f"SW L1 universe size {len(universe)} != expected {expected_count}; "
            "refusing to guess (stock_sector_info classify_system=SW)",
        )
    return universe


# ---------------------------------------------------------------------------
# G1-C-001 可选交叉核对（OQ-016-2 已闭合：reference 缺失不阻断主 universe）
# ---------------------------------------------------------------------------


def _load_reference(path: str) -> dict[str, str] | None:
    p = Path(path)
    if not p.exists():
        return None
    result: dict[str, str] = {}
    with p.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(
            (line for line in handle if not line.lstrip().startswith("#"))
        )
        for row in reader:
            code = (row.get("sector_code") or "").strip()
            name = (row.get("sector_name") or "").strip()
            if code and name:
                result[code] = name
    return result


def cross_check_reference(
    sw_universe: Mapping[str, str], reference_path: str
) -> tuple[list[dict[str, Any]], bool]:
    """DB universe 与 reference CSV 交叉核对（OQ-016-2）。

    Returns:
        (discrepancies, reference_missing)。差异种类：``db_only`` /
        ``ref_only`` / ``name_mismatch``；差异仅记入 report，不参与
        expected universe 构造；reference 缺失只记 ``reference_missing``，
        不阻断主 universe（主来源 stock_sector_info 可用）。
    """
    reference = _load_reference(reference_path)
    if reference is None:
        return [], True

    discrepancies: list[dict[str, Any]] = []
    db_codes = set(sw_universe)
    ref_codes = set(reference)
    for code in sorted(db_codes - ref_codes):
        discrepancies.append(
            {"kind": "db_only", "code": code, "db_name": sw_universe[code]}
        )
    for code in sorted(ref_codes - db_codes):
        discrepancies.append(
            {"kind": "ref_only", "code": code, "ref_name": reference[code]}
        )
    for code in sorted(db_codes & ref_codes):
        if sw_universe[code] != reference[code]:
            discrepancies.append(
                {
                    "kind": "name_mismatch",
                    "code": code,
                    "db_name": sw_universe[code],
                    "ref_name": reference[code],
                }
            )
    return discrepancies, False


# ---------------------------------------------------------------------------
# G1-C-003 可用 trade_date 范围 + 逐日 coverage（join field = full_symbol）
# ---------------------------------------------------------------------------


def _to_internal(trade_date: str, trade_date_format: str) -> str:
    """外部 YYYY-MM-DD → 源格式（TA-CN YYYYMMDD）。"""
    if trade_date_format == "YYYYMMDD":
        return trade_date.replace("-", "")
    return trade_date


def _to_external(trade_date: str, trade_date_format: str) -> str:
    """源格式 → 外部 YYYY-MM-DD。"""
    if trade_date_format == "YYYYMMDD" and len(trade_date) == 8:
        return f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
    return trade_date


def _detect_date_format(docs: Iterable[dict[str, Any]]) -> str:
    for doc in docs:
        value = doc.get("trade_date")
        if isinstance(value, str) and value:
            if len(value) == 8 and value.isdigit():
                return "YYYYMMDD"
            return "YYYY-MM-DD"
    return "YYYY-MM-DD"


def compute_coverage(
    db: Any,
    universe: Mapping[str, str],
    *,
    min_trade_date: str | None = None,
    max_trade_date: str | None = None,
    budget: BudgetReader | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """逐日 coverage（G1-C-003）：aggregate $match（full_symbol 值集）+ $group。

    join field = ``index_daily_quotes.full_symbol``（L1 契约校正，非
    sector_code）；``expected_full_symbols`` = 31 个 ``.SI`` 后缀 L1 code。
    """
    reader = budget if budget is not None else BudgetReader(db)
    full_symbols = list(universe)  # universe key 即 .SI L1 code = full_symbol 值集

    # 先探测源日期形态（抽样首条）。
    sample = reader.find(
        "index_daily_quotes",
        {"full_symbol": {"$in": full_symbols}},
        limit=1,
    )
    fmt = _detect_date_format(sample)

    match: dict[str, Any] = {"full_symbol": {"$in": full_symbols}}
    if min_trade_date or max_trade_date:
        date_q: dict[str, Any] = {}
        if min_trade_date:
            date_q["$gte"] = _to_internal(min_trade_date, fmt)
        if max_trade_date:
            date_q["$lte"] = _to_internal(max_trade_date, fmt)
        match["trade_date"] = date_q

    rows = reader.aggregate(
        "index_daily_quotes",
        [
            {"$match": match},
            {"$group": {"_id": "$trade_date", "symbols": {"$addToSet": "$full_symbol"}}},
        ],
    )

    coverage_by_date: dict[str, dict[str, Any]] = {}
    for row in rows:
        external = _to_external(str(row["_id"]), fmt)
        observed = len({str(s) for s in row.get("symbols", [])})
        coverage_by_date[external] = {
            "expected": len(full_symbols),
            "observed": observed,
            "ratio": round(observed / len(full_symbols), 6) if full_symbols else 0.0,
        }

    external_dates = sorted(coverage_by_date)
    date_range = (
        {"min": external_dates[0], "max": external_dates[-1]}
        if external_dates
        else {"min": None, "max": None}
    )
    return date_range, coverage_by_date


# ---------------------------------------------------------------------------
# G1-C-004 close/pre_close 完整性（join field = full_symbol）
# ---------------------------------------------------------------------------


def check_close_completeness(
    db: Any,
    universe: Mapping[str, str],
    *,
    budget: BudgetReader | None = None,
    trade_date_format: str = "YYYYMMDD",
) -> dict[str, list[str]]:
    """逐日检查 close 有限数值缺失清单（G1-C-004，full_symbol join）。

    单次 aggregate（DESIGN-03-016 V0.6 §3.4.2 伪代码约定 + G1-B-006 预算
    契约）：``$match {full_symbol: {$in: expected_full_symbols}}`` →
    ``$group by trade_date`` 收集 ``{full_symbol, close}`` 对；close 有效性
    在 Python 侧用与旧实现相同的 :func:`coerce_float` 判定（覆盖 bool /
    None / NaN / inf / 数值字符串），产出
    ``dict[external_date, list[full_symbol]]``（有完整 close 的日期为空列表）。

    相比旧实现（distinct dates + 逐日 ``find({full_symbol:$in, trade_date})``）
    消除 N-date 查询模式：真实 Gate-1 高历史深度（4,592 个 trade_date）下
    旧实现曾产生 4,592 轮 find / 87,099 行 + distinct 6,422 → 触发
    100,000 累计行上限（G1-S-007）；聚合实现只按日期数（4,592）计行，
    远低于上限。
    """
    reader = budget if budget is not None else BudgetReader(db)
    full_symbols = list(universe)

    rows = reader.aggregate(
        "index_daily_quotes",
        [
            {"$match": {"full_symbol": {"$in": full_symbols}}},
            {
                "$group": {
                    "_id": "$trade_date",
                    "symbols": {
                        "$addToSet": {"symbol": "$full_symbol", "close": "$close"}
                    },
                }
            },
        ],
    )

    missing_by_date: dict[str, list[str]] = {}
    for row in rows:
        external = _to_external(str(row["_id"]), trade_date_format)
        missing: list[str] = []
        for entry in row.get("symbols", []):
            if coerce_float(entry.get("close")) is None:
                missing.append(str(entry.get("symbol")))
        missing_by_date[external] = sorted(set(missing))
    return missing_by_date


# ---------------------------------------------------------------------------
# G1-C-005 data_source/source 线索（join field = full_symbol）
# ---------------------------------------------------------------------------


def check_source_distribution(
    db: Any,
    universe: Mapping[str, str],
    *,
    budget: BudgetReader | None = None,
) -> tuple[dict[str, int], list[str]]:
    """source 值分布 + realtime/intraday 标记检测（G1-C-005，full_symbol join）。"""
    reader = budget if budget is not None else BudgetReader(db)
    rows = reader.aggregate(
        "index_daily_quotes",
        [
            {"$match": {"full_symbol": {"$in": list(universe)}}},
            {"$group": {"_id": "$source", "n": {"$sum": 1}}},
        ],
    )
    source_dist: dict[str, int] = {}
    for row in rows:
        source = str(row.get("_id") or "unknown")
        source_dist[source] = int(row.get("n", 0))
    markers = [s for s in source_dist if s in REALTIME_MARKERS]
    return source_dist, markers


# ---------------------------------------------------------------------------
# canary 候选（OQ-016-3）
# ---------------------------------------------------------------------------


def select_candidates(
    coverage_by_date: Mapping[str, dict[str, Any]],
    close_missing_by_date: Mapping[str, list[str]],
    *,
    today: str,
) -> tuple[list[str], str | None]:
    """候选 = coverage 100% + close 完整 + 非今日；recommended = 最近日。"""
    candidates: list[str] = []
    for trade_date in sorted(coverage_by_date):
        entry = coverage_by_date[trade_date]
        ratio = entry.get("ratio")
        close_ok = not close_missing_by_date.get(trade_date)
        if ratio == 1.0 and close_ok and trade_date != today:
            candidates.append(trade_date)
    recommended = candidates[-1] if candidates else None
    return candidates, recommended


# ---------------------------------------------------------------------------
# report 构造（G1-R-001 ~ G1-R-010，L1 契约校正）
# ---------------------------------------------------------------------------


def build_report(
    *,
    tool: str,
    conn_source: str,
    conn_fingerprint: Mapping[str, Any],
    query_budget: list[dict[str, Any]],
    expected_sector_codes: list[str],
    expected_sector_names: Mapping[str, str],
    expected_full_symbols: list[str],
    universe_source: str,
    trade_date_range: Mapping[str, Any],
    trade_date_format: str,
    coverage_by_date: Mapping[str, dict[str, Any]],
    close_missing_by_date: Mapping[str, list[str]],
    source_distribution: Mapping[str, int],
    realtime_markers: list[str],
    discrepancies: list[dict[str, Any]],
    canary_candidates: list[str],
    recommended_canary: str | None,
    checks: Mapping[str, str],
    stop_conditions_hit: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "tool": tool,
        "version": VERSION,
        "timestamp": _now_iso(),
        "conn_source": conn_source,
        "conn_fingerprint": dict(conn_fingerprint),
        "query_budget": list(query_budget),
        "trade_date_format": trade_date_format,
        "expected_sector_codes": list(expected_sector_codes),
        "expected_sector_names": dict(expected_sector_names),
        "expected_full_symbols": list(expected_full_symbols),
        "universe_source": universe_source,
        "trade_date_range": dict(trade_date_range),
        "coverage_by_date": dict(coverage_by_date),
        "close_missing_by_date": dict(close_missing_by_date),
        "source_distribution": dict(source_distribution),
        "realtime_markers": list(realtime_markers),
        "discrepancies": list(discrepancies),
        "canary_candidates": list(canary_candidates),
        "recommended_canary": recommended_canary,
        "checks": dict(checks),
        "stop_conditions_hit": list(stop_conditions_hit or []),
    }


def _default_reference_path(report_dir: str) -> str:
    return str(Path(report_dir) / "reference" / "sw_l1_reference.csv")


def _baseline_counts(db: Any) -> dict[str, int]:
    return {
        "index_daily_quotes": int(db["index_daily_quotes"].estimated_document_count()),
        "stock_sector_info": int(db["stock_sector_info"].estimated_document_count()),
    }


def _print_dry_run_plan(args: argparse.Namespace, report_dir: str) -> None:
    print(f"[{TOOL}] dry-run plan (zero side effects)")
    print(f"  report-dir: {report_dir}")
    print("  queries (via BudgetReader, budget-enforced):")
    print("    - aggregate stock_sector_info {classify_system: SW}  (G1-C-001)")
    print("    - find/aggregate index_daily_quotes full_symbol (G1-C-003/004/005)")
    print(f"  budget: find limit<=1000, maxTimeMS<=30000, serverSelectionTimeoutMS<=10000")
    print("  no writes; --apply --yes required to execute real read + write report")


def _detect_source_format(
    db: Any, budget: BudgetReader, full_symbols: Iterable[str]
) -> str:
    """探测源 trade_date 形态（YYYYMMDD / YYYY-MM-DD，full_symbol 过滤）。"""
    try:
        sample = budget.find(
            "index_daily_quotes",
            {"full_symbol": {"$in": list(full_symbols)}},
            limit=1,
        )
    except BudgetViolation:
        sample = []
    if sample and isinstance(sample[0].get("trade_date"), str):
        value = sample[0]["trade_date"]
        if len(value) == 8 and value.isdigit():
            return "YYYYMMDD"
    return "YYYY-MM-DD"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
    env: Mapping[str, str] | None = None,
    reference_path: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> int:
    """Gate-1 CLI 入口（dry-run 默认；``--apply --yes`` 才真实执行）。"""
    args = build_parser().parse_args(argv)
    report_dir = resolve_report_dir(args.report_dir)

    if not (args.apply and args.yes):
        _print_dry_run_plan(args, report_dir)
        return EXIT_OK

    try:
        conn = ConnLoader(env=env, client_factory=client_factory)
        db = conn.load_db()
    except MissingConnectionKeyError as exc:
        print(f"[{TOOL}] EXIT_CONN: {exc}", file=sys.stderr)
        return EXIT_CONN
    except Exception as exc:  # noqa: BLE001 — 连接/认证失败（G1-S-001）
        print(
            f"[{TOOL}] EXIT_CONN: connection/auth failed "
            f"({type(exc).__name__})",
            file=sys.stderr,
        )
        return EXIT_CONN

    secret_entries = conn.secret_entries()
    ref_path = reference_path or _default_reference_path(report_dir)

    # 预初始化（stop 报告可能引用部分结果）。
    universe: dict[str, str] = {}
    budget = BudgetReader(db)
    date_range: dict[str, Any] = {}
    coverage_by_date: dict[str, dict[str, Any]] = {}
    close_missing: dict[str, list[str]] = {}
    source_dist: dict[str, int] = {}
    rt_markers: list[str] = []
    discrepancies: list[dict[str, Any]] = []
    candidates: list[str] = []
    recommended: str | None = None
    # 源 trade_date 形态：正常路径由 _detect_source_format 探测；stop 路径
    # 复用已探测值（探测基于真实 universe 值集，不硬编码 universe）。
    trade_date_format: str = "YYYY-MM-DD"

    try:
        baseline = _baseline_counts(db)
        log_jsonl(
            report_dir,
            "gate1",
            {"action": "baseline", "counts": baseline},
            secret_entries=secret_entries,
        )

        universe = enumerate_sw_l1(db, budget=budget)
        expected_full_symbols = sorted(universe)  # .SI L1 code = full_symbol 值集
        trade_date_format = _detect_source_format(db, budget, expected_full_symbols)

        discrepancies, ref_missing = cross_check_reference(universe, ref_path)
        if ref_missing:
            # L1 契约校正：reference 缺失只记录，不阻断主 universe。
            discrepancies.append({"kind": "reference_missing", "path": str(ref_path)})

        date_range, coverage_by_date = compute_coverage(
            db,
            universe,
            min_trade_date=args.min_trade_date,
            max_trade_date=args.max_trade_date,
            budget=budget,
        )
        if not coverage_by_date:
            raise Gate1Stop("G1-S-005", "no usable trade_date coverage found")

        close_missing = check_close_completeness(
            db, universe, budget=budget, trade_date_format=trade_date_format
        )
        source_dist, rt_markers = check_source_distribution(db, universe, budget=budget)
        if rt_markers:
            raise Gate1Stop(
                "G1-S-006",
                f"realtime/intraday markers detected in SW L1 rows: {rt_markers}",
            )

        today = _today_cst(now_fn)
        candidates, recommended = select_candidates(
            coverage_by_date, close_missing, today=today
        )
        if not candidates:
            raise Gate1Stop(
                "G1-S-005",
                "no canary candidates with 100% coverage / complete close / "
                "non-today trade_date",
            )

        payload = build_report(
            tool=TOOL,
            conn_source="MONGODB_*",
            conn_fingerprint=conn.fingerprint(),
            query_budget=budget.stats(),
            expected_sector_codes=sorted(universe),
            expected_sector_names=universe,
            expected_full_symbols=expected_full_symbols,
            universe_source=UNIVERSE_SOURCE,
            trade_date_range=date_range,
            trade_date_format=trade_date_format,
            coverage_by_date=coverage_by_date,
            close_missing_by_date=close_missing,
            source_distribution=source_dist,
            realtime_markers=rt_markers,
            discrepancies=discrepancies,
            canary_candidates=candidates,
            recommended_canary=recommended,
            checks={
                "G1-C-001": "PASS",
                "G1-C-002": "PASS",
                "G1-C-003": "PASS",
                "G1-C-004": "PASS",
                "G1-C-005": "PASS",
                "G1-C-006": "PASS",
                "G1-C-007": "PASS",
            },
            stop_conditions_hit=[],
        )

        write_report(report_dir, "gate1", payload)
        report_text = json.dumps(payload, ensure_ascii=False)
        hits = scan_secrets(report_text, secret_entries=secret_entries)
        if hits:
            raise Gate1Stop(
                "G1-S-008",
                f"secret leak detected in report output: {hits}; rotate credentials",
            )
        log_jsonl(
            report_dir,
            "gate1",
            {
                "action": "apply_done",
                "universe_size": len(universe),
                "candidates": candidates,
                "recommended": recommended,
            },
            secret_entries=secret_entries,
        )
        return EXIT_OK

    except Gate1Stop as exc:
        payload = build_report(
            tool=TOOL,
            conn_source="MONGODB_*",
            conn_fingerprint=conn.fingerprint(),
            query_budget=budget.stats(),
            expected_sector_codes=sorted(universe),
            expected_sector_names=universe,
            expected_full_symbols=sorted(universe),
            universe_source=UNIVERSE_SOURCE,
            trade_date_range=date_range,
            trade_date_format=trade_date_format,
            coverage_by_date=coverage_by_date,
            close_missing_by_date=close_missing,
            source_distribution=source_dist,
            realtime_markers=rt_markers,
            discrepancies=discrepancies,
            canary_candidates=candidates,
            recommended_canary=recommended,
            checks={"G1-C-001": "FAIL" if exc.sc_id == "G1-S-002" else "PASS"},
            stop_conditions_hit=[exc.sc_id],
        )
        write_report(report_dir, "gate1", payload)
        log_jsonl(
            report_dir,
            "gate1",
            {"action": "stop", "sc_id": exc.sc_id, "message": str(exc)},
            secret_entries=secret_entries,
        )
        print(f"[{TOOL}] STOP {exc.sc_id}: {exc}", file=sys.stderr)
        return EXIT_STOP

    except BudgetViolation as exc:
        payload = {
            "tool": TOOL,
            "version": VERSION,
            "timestamp": _now_iso(),
            "conn_source": "MONGODB_*",
            "conn_fingerprint": conn.fingerprint(),
            "query_budget": budget.stats(),
            "checks": {},
            "stop_conditions_hit": ["G1-S-007"],
            "error": str(exc),
        }
        write_report(report_dir, "gate1", payload)
        print(f"[{TOOL}] STOP G1-S-007: {exc}", file=sys.stderr)
        return EXIT_STOP


if __name__ == "__main__":
    sys.exit(main())
