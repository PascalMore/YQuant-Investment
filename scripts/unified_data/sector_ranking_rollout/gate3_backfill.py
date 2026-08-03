"""Gate-3 工具：真实 TA-CN 历史 backfill CLI（dry-run / canary / 全量，日级原子）。

DESIGN-03-016 V0.6 §3.6 / SPEC-03-016 §3.4（L1 契约校正）。读取 Gate-1 report
（``--expected-file``，唯一 expected universe 来源，H-049u），必含三字段
``expected_sector_codes`` / ``expected_sector_names`` / ``expected_full_symbols``
（后者 = ``.SI`` 后缀 L1 join 值集，即 ``index_daily_quotes.full_symbol``
值集；缺失/非法 → G3-S-002 参数层 fail-fast exit 1，不等 process_day）。
从 ``index_daily_quotes`` 按 ``full_symbol`` join 逐日构建（复用冻结
``build_ranking_rows``，100% exact-match、固定 pct_chg 公式），经
:class:`ProdRankingWriter` upsert 到 ``03_data_ud_sector_ranking_daily``，
写后读回（G3-V-001~004）。候选输出 ``sector_code`` 为 ``.SI`` 后缀 L1 code
（来自 code→name 映射；G3-B-011 / 契约 6）。范围来源二选一（``--range-file`` /
成对 ``--start-date``/``--end-date``）或 canary 单日（``--canary-date``），
互斥规则按 F1 冻结（§3.6.3）。

退出码（SPEC G0-C-004）：0 成功 / 1 参数前置失败 / 2 停止条件 / 3 连接凭据失败。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time as time_mod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from skills.data.unified_data.models.domain.sector_ranking import (
    SectorRankingDaily,
    coerce_float,
)
from skills.data.unified_data.services.historical_sector_service import (
    build_ranking_rows,
)

from .common import (
    BudgetReader,
    BudgetViolation,
    CompletedSessionPolicy,
    ConnLoader,
    EXIT_CONN,
    EXIT_OK,
    EXIT_PARAM,
    EXIT_STOP,
    MissingConnectionKeyError,
    log_jsonl,
    redact,
    resolve_report_dir,
    scan_secrets,
    write_report,
)
from .prod_repository import NamespaceViolation, ProdRankingWriter

TOOL = "gate3_backfill"
VERSION = "0.1.0"
DATASET = "sw2021_ta_cn"

# Gate-1 report 必填三字段（G3-S-002：任一缺失/非法 → 参数层 fail-fast exit 1）。
REQUIRED_EXPECTED_FIELDS: tuple[str, ...] = (
    "expected_sector_codes",
    "expected_sector_names",
    "expected_full_symbols",
)

# realtime/intraday 标记（G3-B-009 / G3-S-010，RT-4）。
REALTIME_MARKERS: frozenset[str] = frozenset({"realtime", "intraday", "rt"})


class Gate3Stop(Exception):
    """Gate-3 停止/参数失败条件命中。"""

    def __init__(self, sc_id: str, message: str, exit_code: int = EXIT_STOP) -> None:
        self.sc_id = sc_id
        self.exit_code = exit_code
        super().__init__(message)


@dataclass(frozen=True)
class CoverageSet:
    """合法 ``coverage_by_date`` 的满覆盖日期集。"""

    full_coverage_dates: tuple[str, ...]


@dataclass
class RangePlan:
    """范围解析结果（DESIGN §3.6.3）。"""

    mode: str  # "canary" | "range-file" | "paired"
    dates: list[str] = field(default_factory=list)  # 升序去重处理日
    full_coverage_dates: tuple[str, ...] = ()  # ratio==1.0 的 canonical 日期集
    excluded_first: str | None = None  # --range-file 模式默认排除的最早满覆盖日
    reason: str = ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="03-016 Gate-3 real TA-CN historical backfill (day-atomic)",
    )
    parser.add_argument(
        "--expected-file", required=True, help="Gate-1 report JSON（expected universe 唯一来源）"
    )
    parser.add_argument("--range-file", default=None, help="Gate-1 report JSON（全量范围来源，取 coverage_by_date）")
    parser.add_argument("--start-date", default=None, help="可选：YYYY-MM-DD（与 --end-date 成对）")
    parser.add_argument("--end-date", default=None, help="可选：YYYY-MM-DD（与 --start-date 成对）")
    parser.add_argument("--canary-date", default=None, help="可选：YYYY-MM-DD（来自 gate1-report.canary_candidates）")
    parser.add_argument("--apply", action="store_true", help="执行真实 backfill")
    parser.add_argument("--yes", action="store_true", help="确认执行副作用（--apply 必须伴随）")
    parser.add_argument("--report-dir", default=None, help="产物目录（默认 data/rollout/sector-ranking）")
    return parser


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_expected_report(path: str) -> dict[str, Any]:
    """读取并校验 Gate-1 report（G3-S-002 → EXIT_PARAM(1)，参数层 fail-fast）。

    必填三字段：``expected_sector_codes``（31 个 ``.SI`` 后缀 L1 code）、
    ``expected_sector_names``（code→name 映射）、``expected_full_symbols``
    （31 个 ``index_daily_quotes.full_symbol`` 值集，即 ``.SI`` 后缀 L1 join
    值集，Gate-3 行情 join 键）；任一缺失/类型非法 → G3-S-002，**不等
    process_day**（SPEC §3.4.1 / G3-S-002）。
    """
    p = Path(path)
    if not p.exists():
        raise Gate3Stop(
            "G3-S-002",
            f"--expected-file not found: {path}",
            exit_code=EXIT_PARAM,
        )
    try:
        report = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise Gate3Stop(
            "G3-S-002",
            f"--expected-file is not valid JSON: {type(exc).__name__}",
            exit_code=EXIT_PARAM,
        ) from exc
    if not isinstance(report, dict):
        raise Gate3Stop("G3-S-002", "--expected-file JSON must be an object", exit_code=EXIT_PARAM)

    missing = [field_name for field_name in REQUIRED_EXPECTED_FIELDS if field_name not in report]
    if missing:
        raise Gate3Stop(
            "G3-S-002",
            "--expected-file JSON missing required field(s): "
            + ", ".join(missing),
            exit_code=EXIT_PARAM,
        )

    codes = report["expected_sector_codes"]
    names = report["expected_sector_names"]
    symbols = report["expected_full_symbols"]
    if not isinstance(codes, list) or not codes:
        raise Gate3Stop(
            "G3-S-002",
            "expected_sector_codes must be a non-empty list",
            exit_code=EXIT_PARAM,
        )
    if not all(isinstance(c, str) and c.endswith(".SI") for c in codes):
        raise Gate3Stop(
            "G3-S-002",
            "expected_sector_codes must be .SI-suffixed L1 codes",
            exit_code=EXIT_PARAM,
        )
    if not isinstance(names, dict) or not names:
        raise Gate3Stop(
            "G3-S-002",
            "expected_sector_names must be a non-empty mapping",
            exit_code=EXIT_PARAM,
        )
    if not isinstance(symbols, list) or not symbols:
        raise Gate3Stop(
            "G3-S-002",
            "expected_full_symbols must be a non-empty list",
            exit_code=EXIT_PARAM,
        )
    if not all(isinstance(s, str) and s.endswith(".SI") for s in symbols):
        raise Gate3Stop(
            "G3-S-002",
            "expected_full_symbols must be .SI-suffixed L1 join values "
            "(index_daily_quotes.full_symbol)",
            exit_code=EXIT_PARAM,
        )
    return report


def _validate_trade_date(value: str) -> str:
    from skills.data.unified_data.models.domain.sector_ranking import (
        is_valid_trade_date,
    )

    if not is_valid_trade_date(value):
        raise Gate3Stop(
            "G3-S-003",
            f"invalid trade_date {value!r} (must be YYYY-MM-DD)",
            exit_code=EXIT_PARAM,
        )
    return value


def parse_coverage_by_date(coverage: Any) -> CoverageSet:
    """解析满覆盖日期；任一非法键或 ratio 均按 G3-S-003 fail-fast。"""
    if not isinstance(coverage, Mapping):
        raise Gate3Stop(
            "G3-S-003", "coverage_by_date must be an object", exit_code=EXIT_PARAM
        )

    full_dates: list[str] = []
    for raw_date, raw_entry in coverage.items():
        if not isinstance(raw_date, str) or _validate_trade_date(raw_date) != raw_date:
            raise Gate3Stop(
                "G3-S-003",
                f"coverage_by_date key {raw_date!r} must be canonical YYYY-MM-DD",
                exit_code=EXIT_PARAM,
            )
        if not isinstance(raw_entry, Mapping) or "ratio" not in raw_entry:
            raise Gate3Stop(
                "G3-S-003",
                f"coverage_by_date[{raw_date!r}] missing ratio",
                exit_code=EXIT_PARAM,
            )
        raw_ratio = raw_entry["ratio"]
        if isinstance(raw_ratio, bool):
            raise Gate3Stop(
                "G3-S-003",
                f"coverage_by_date[{raw_date!r}].ratio must be a finite number",
                exit_code=EXIT_PARAM,
            )
        try:
            ratio = float(raw_ratio)
        except (TypeError, ValueError) as exc:
            raise Gate3Stop(
                "G3-S-003",
                f"coverage_by_date[{raw_date!r}].ratio must be a finite number",
                exit_code=EXIT_PARAM,
            ) from exc
        if not math.isfinite(ratio):
            raise Gate3Stop(
                "G3-S-003",
                f"coverage_by_date[{raw_date!r}].ratio must be finite",
                exit_code=EXIT_PARAM,
            )
        if ratio == 1.0:
            full_dates.append(raw_date)

    full_coverage_dates = tuple(sorted(set(full_dates)))
    if not full_coverage_dates:
        raise Gate3Stop(
            "G3-S-003",
            "coverage_by_date contains no full-coverage date (ratio == 1.0)",
            exit_code=EXIT_PARAM,
        )
    return CoverageSet(full_coverage_dates=full_coverage_dates)


def resolve_range(
    report: Mapping[str, Any],
    *,
    canary_date: str | None,
    range_file: str | None,
    start_date: str | None,
    end_date: str | None,
    policy: CompletedSessionPolicy | None = None,
) -> RangePlan:
    """范围解析（DESIGN §3.6.3 / F1 冻结；全部非法 → G3-S-003 退出码 1）。

    * ``--canary-date`` 单日模式仅在无任何全量范围来源时合法；与
      ``--range-file`` / 成对或不成对 ``--start-date``/``--end-date``
      同时传入 → 退出码 1。
    * ``--range-file`` 模式：范围 = ``coverage_by_date`` 中 ratio==1.0 的
      canonical 日期键集，升序去重，默认排除最早满覆盖日（G3-B-016）。
    * 显式成对 ``--start-date``/``--end-date``：必须成对、start<=end，
      且窗口内全部 ``coverage_by_date`` 键均属于满覆盖集；经
      ``CompletedSessionPolicy`` 判定非未来日 / 非「当日未收盘」。
    """
    if canary_date is not None:
        if range_file or start_date or end_date:
            raise Gate3Stop(
                "G3-S-003",
                "--canary-date is mutually exclusive with any full-range source "
                "(--range-file / --start-date / --end-date)",
                exit_code=EXIT_PARAM,
            )
        candidates = list(report.get("canary_candidates") or [])
        if canary_date not in candidates:
            raise Gate3Stop(
                "G3-S-003",
                f"--canary-date {canary_date!r} not in gate1-report.canary_candidates "
                f"{candidates}",
                exit_code=EXIT_PARAM,
            )
        coverage_set = parse_coverage_by_date(report.get("coverage_by_date"))
        return RangePlan(
            mode="canary",
            dates=[canary_date],
            full_coverage_dates=coverage_set.full_coverage_dates,
            reason="canary single day",
        )

    if range_file:
        if start_date or end_date:
            raise Gate3Stop(
                "G3-S-003",
                "--range-file is mutually exclusive with --start-date/--end-date",
                exit_code=EXIT_PARAM,
            )
        coverage_set = parse_coverage_by_date(report.get("coverage_by_date"))
        full_dates = coverage_set.full_coverage_dates
        excluded = full_dates[0]
        return RangePlan(
            mode="range-file",
            dates=list(full_dates[1:]),
            full_coverage_dates=full_dates,
            excluded_first=excluded,
            reason="full range from full-coverage dates, earliest excluded",
        )

    if start_date or end_date:
        if not start_date or not end_date:
            raise Gate3Stop(
                "G3-S-003",
                "--start-date and --end-date must be provided as a pair",
                exit_code=EXIT_PARAM,
            )
        start = _validate_trade_date(start_date)
        end = _validate_trade_date(end_date)
        if start > end:
            raise Gate3Stop(
                "G3-S-003",
                f"--start-date {start} must be <= --end-date {end}",
                exit_code=EXIT_PARAM,
            )
        date_range = report.get("trade_date_range") or {}
        min_date = date_range.get("min")
        max_date = date_range.get("max")
        if min_date is None or max_date is None or start < str(min_date) or end > str(max_date):
            raise Gate3Stop(
                "G3-S-003",
                f"explicit range [{start}, {end}] outside Gate-1 trade_date_range "
                f"[{min_date}, {max_date}]",
                exit_code=EXIT_PARAM,
            )
        if policy is None:
            raise Gate3Stop(
                "G3-S-003",
                "CompletedSessionPolicy unavailable; fail-closed for explicit range",
                exit_code=EXIT_PARAM,
            )
        for value in (start, end):
            try:
                policy.classify(value)
            except ValueError as exc:
                raise Gate3Stop(
                    "G3-S-003",
                    f"explicit range date {value} rejected by CompletedSessionPolicy: {exc}",
                    exit_code=EXIT_PARAM,
                ) from exc
        coverage_set = parse_coverage_by_date(report.get("coverage_by_date"))
        full_dates = coverage_set.full_coverage_dates
        full_set = set(full_dates)
        coverage_keys = set(report["coverage_by_date"])
        window_keys = {d for d in coverage_keys if start <= d <= end}
        if start not in full_set or end not in full_set or window_keys - full_set:
            raise Gate3Stop(
                "G3-S-003",
                f"explicit range [{start}, {end}] contains date(s) outside the "
                "full-coverage set",
                exit_code=EXIT_PARAM,
            )
        dates = [d for d in full_dates if start <= d <= end]
        if not dates:
            raise Gate3Stop(
                "G3-S-003",
                f"explicit range [{start}, {end}] contains no full-coverage date",
                exit_code=EXIT_PARAM,
            )
        return RangePlan(
            mode="paired",
            dates=dates,
            full_coverage_dates=full_dates,
            reason="explicit paired full-coverage subrange",
        )

    raise Gate3Stop(
        "G3-S-003",
        "no range source: provide --range-file, paired --start-date/--end-date, "
        "or --canary-date",
        exit_code=EXIT_PARAM,
    )


def _print_dry_run_plan(
    args: argparse.Namespace,
    report_dir: str,
    plan: RangePlan,
    excluded_reason: str = "",
) -> None:
    print(f"[{TOOL}] dry-run plan (zero side effects)")
    print(f"  report-dir: {report_dir}")
    print(f"  mode: {plan.mode}")
    if plan.excluded_first:
        print(
            f"  excluded earliest available day: {plan.excluded_first} "
            f"(no previous close; G3-B-016) {excluded_reason}".rstrip()
        )
    print(f"  days to process ({len(plan.dates)}): {plan.dates[:10]}{'...' if len(plan.dates) > 10 else ''}")
    print("  dataset: sw2021_ta_cn (fixed, G3-B-006)")
    print("  no writes; --apply --yes required to execute real backfill")


# ---------------------------------------------------------------------------
# 日级处理（DESIGN §3.6.4 / SPEC G3-B-002~012）
# ---------------------------------------------------------------------------


@dataclass
class DayOutcome:
    """单日处理结果（G3-A-003）。"""

    trade_date: str
    status: str  # "complete" | "incomplete" | "empty"
    expected: int = 0
    observed: int = 0
    upserted: int = 0
    failed: int = 0
    ms: float = 0.0
    reason: str = ""
    query_budget: list[dict[str, Any]] = field(default_factory=list)


def _failed_status(sc_id: str) -> str:
    """失败类别映射（G3-S-xxx → 人读 status，DESIGN §3.6.6 failed_days[].status）。"""
    return {
        "G3-S-004": "incomplete",
        "G3-S-005": "empty",
        "G3-S-006": "upsert-failed",
        "G3-S-007": "read-back-mismatch",
        "G3-S-010": "realtime-marker",
        "G3-S-013": "budget-violation",
    }.get(sc_id, "stop")


def _to_internal(trade_date: str, date_format: str) -> str:
    if date_format == "YYYYMMDD":
        return trade_date.replace("-", "")
    return trade_date


def _is_rt_marker(source: Any) -> bool:
    return str(source or "").lower() in REALTIME_MARKERS


def process_day(
    trade_date: str,
    prev_date: str | None,
    expected_codes: list[str],
    expected_names: Mapping[str, str],
    db: Any,
    writer: ProdRankingWriter,
    *,
    budget: BudgetReader | None = None,
    date_format: str = "YYYYMMDD",
    updated_at: str | None = None,
    expected_full_symbols: list[str] | None = None,
) -> DayOutcome:
    """处理单个交易日（读取 → 构建 → upsert → 写后读回，日级原子）。

    * ``expected_full_symbols``：Gate-1 ``expected_full_symbols``（``.SI``
      后缀 L1 join 值集 = ``index_daily_quotes.full_symbol`` 值集）；行情
      join field = ``full_symbol``（L1 契约校正，非 ``sector_code``）。
      ``None``（兼容 gate4 冻结测试调用）时 fallback 到 ``expected_codes``
      （生产 Gate-3 CLI 始终显式传入 Gate-1 report 的该字段）。
    * 候选输出 ``sector_code`` 来自 ``expected_codes``（``.SI`` 后缀 L1
      code），``sector_name`` 来自 ``expected_names``（G3-B-011）。
    * ``prev_date=None``（无前一日）→ ``DayOutcome(status="empty",
      reason="no-prev-close")``（G3-B-004 / G3-B-016）。
    * 任一完整性 / rt / upsert / 读回失败 → ``Gate3Stop``（G3-S-004~007/010），
      不物化部分榜单（G3-B-012）。
    * 预算模型（G3-B-017~020）：开头调用 ``reader.reset_stats()`` 使累计计数
      **按日 scoped**；单日命中 > ``day_rows_limit`` → :class:`BudgetViolation`
      → ``Gate3Stop``（G3-S-013，退出码 2，停止后续日）。
    """
    reader = budget if budget is not None else BudgetReader(db)
    # G3-B-017：每 process_day 开头清零累计计数与 stats 列表（per-day scoped）。
    reader.reset_stats()
    day_start = time_mod.monotonic()
    if prev_date is None:
        return DayOutcome(
            trade_date=trade_date,
            status="empty",
            expected=len(expected_codes),
            reason="no-prev-close",
        )

    symbols = list(expected_full_symbols) if expected_full_symbols is not None else list(expected_codes)
    # code→full_symbol 映射（契约：带 .SI 的 l1_code 与 full_symbol 值集一一对应）。
    code_to_symbol = dict(zip(expected_codes, symbols))
    if len(code_to_symbol) != len(expected_codes):
        # 防御：长度不一致时退化为恒等映射（code 即 full_symbol 值）。
        code_to_symbol = {code: code for code in expected_codes}

    internal_day = _to_internal(trade_date, date_format)
    internal_prev = _to_internal(prev_date, date_format)

    try:
        docs = reader.find(
            "index_daily_quotes",
            {
                "full_symbol": {"$in": symbols},
                "trade_date": {"$in": [internal_day, internal_prev]},
            },
        )
    except BudgetViolation as exc:
        # G3-B-018 / G3-S-013：单日查询命中 > day_rows_limit → 停止后续日。
        raise Gate3Stop(
            "G3-S-013",
            f"{trade_date}: per-day query budget exceeded: {exc}",
        ) from exc
    if any(_is_rt_marker(doc.get("source")) for doc in docs):
        raise Gate3Stop(
            "G3-S-010",
            "realtime/intraday marker detected in index_daily_quotes rows; "
            "refusing to materialize (RT-4)",
        )

    day_docs = {str(d["full_symbol"]): d for d in docs if d["trade_date"] == internal_day}
    prev_docs = {str(d["full_symbol"]): d for d in docs if d["trade_date"] == internal_prev}

    candidates: list[dict[str, Any]] = []
    for code in expected_codes:
        symbol = code_to_symbol.get(code, code)
        day_row = day_docs.get(symbol)
        prev_row = prev_docs.get(symbol)
        if day_row is None:
            continue  # 缺 day 行 → 该 code 缺失（G3-B-010）
        close = coerce_float(day_row.get("close"))
        if close is None:
            continue  # close 非法 → 缺失（G3-B-010）
        pre_close = coerce_float(prev_row.get("close")) if prev_row is not None else None
        if pre_close is None or pre_close == 0:
            continue  # 缺 prev / pre_close 非法 → 不入库（G3-B-004 / G3-B-010）
        name = expected_names.get(code)
        if not name:
            continue  # sector_name 缺失 → 不入库（G3-B-011）
        candidates.append(
            {
                "sector_code": code,
                "sector_name": name,
                "close": close,
                "pre_close": pre_close,
            }
        )

    stamp = updated_at if updated_at is not None else _now_iso()
    outcome = build_ranking_rows(
        candidates,
        expected_codes,
        DATASET,
        trade_date,
        updated_at=stamp,
    )

    if outcome.status == "incomplete":
        raise Gate3Stop(
            "G3-S-004",
            f"{trade_date}: observed {len(outcome.observed_sector_codes)} != "
            f"expected {len(expected_codes)}; refusing to materialize partial ranking",
        )
    if outcome.status == "empty":
        raise Gate3Stop(
            "G3-S-005",
            f"{trade_date}: zero valid rows; refusing to materialize",
        )

    rows = [asdict(row) for row in outcome.rows]
    upsert_outcome = writer.upsert(rows)
    if upsert_outcome.failed > 0:
        raise Gate3Stop(
            "G3-S-006",
            f"{trade_date}: upsert failed={upsert_outcome.failed} errors="
            f"{upsert_outcome.errors[:3]}",
        )

    read_back_verify(writer, trade_date, expected_codes)

    return DayOutcome(
        trade_date=trade_date,
        status="complete",
        expected=len(expected_codes),
        observed=len(outcome.rows),
        upserted=upsert_outcome.persisted,
        failed=upsert_outcome.failed,
        ms=round(time_mod.monotonic() - day_start, 3),
        # G3-A-003：per-day query_budget（reset 后仅含单日计数，G3-B-017）。
        query_budget=reader.stats(),
    )


def read_back_verify(
    writer: ProdRankingWriter,
    trade_date: str,
    expected: list[str],
) -> None:
    """写后读回校验（G3-V-001~004；任一不符 → G3-S-007）。"""
    rows = writer.get(filter={"dataset": DATASET, "trade_date": trade_date})
    if len(rows) != len(expected):
        raise Gate3Stop(
            "G3-S-007",
            f"read-back row count {len(rows)} != expected {len(expected)} (G3-V-001)",
        )
    for doc in rows:
        try:
            SectorRankingDaily.from_dict(doc)
        except (ValueError, TypeError) as exc:
            raise Gate3Stop(
                "G3-S-007",
                f"read-back field validation failed: {exc} (G3-V-002)",
            ) from exc
    sorted_rows = sorted(rows, key=lambda r: (-float(r["pct_chg"]), str(r["sector_code"])))
    if [r["sector_code"] for r in rows] != [r["sector_code"] for r in sorted_rows]:
        raise Gate3Stop(
            "G3-S-007",
            "read-back ordering not pct_chg DESC -> sector_code ASC (G3-V-003)",
        )
    unique = {(r["dataset"], r["trade_date"], r["sector_code"]) for r in rows}
    if len(unique) != len(rows):
        raise Gate3Stop(
            "G3-S-007",
            "read-back unique key {dataset, trade_date, sector_code} has duplicates (G3-V-004)",
        )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _sum_query_rows(records: Iterable[Mapping[str, Any]]) -> int:
    """对保留的逐日记录（days[] ∪ failed_days[]）的 query_budget 条数求和。

    reset-safe（M2 / DESIGN §3.6.6）：只读保留记录，不读 reader 实时累计状态。
    """
    total = 0
    for rec in records:
        for item in rec.get("query_budget") or []:
            total += int(item.get("rows", 0))
    return total


def _aggregate_query_budget(
    records: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """跨日聚合保留记录的 query_budget（各查询类别次数/条数/耗时求和）。

    reset-safe（M4 / DESIGN §3.6.6）：由 days[] ∪ failed_days[] 派生，
    不读取 reader 实时累计状态。
    """
    merged: dict[str, dict[str, Any]] = {}
    for rec in records:
        for item in rec.get("query_budget") or []:
            kind = str(item.get("kind"))
            entry = merged.setdefault(
                kind, {"kind": kind, "count": 0, "rows": 0, "ms": 0.0}
            )
            entry["count"] += int(item.get("count", 0))
            entry["rows"] += int(item.get("rows", 0))
            entry["ms"] = round(entry["ms"] + float(item.get("ms", 0.0)), 3)
    return list(merged.values())


def _build_report_payload(
    *,
    conn_fingerprint: Mapping[str, Any],
    plan: RangePlan,
    canary: Mapping[str, Any] | None,
    days: list[dict[str, Any]],
    failed_days: list[dict[str, Any]],
    summary: dict[str, Any],
    expected_sector_codes: list[str],
    expected_sector_names: Mapping[str, str],
    query_budget: list[dict[str, Any]],
    checks: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "tool": TOOL,
        "version": VERSION,
        "timestamp": _now_iso(),
        "conn_source": "MONGODB_*",
        "conn_fingerprint": dict(conn_fingerprint),
        "range": {
            "start": plan.dates[0] if plan.dates else None,
            "end": plan.dates[-1] if plan.dates else None,
            "excluded_first": plan.excluded_first,
            "full_coverage_days": len(plan.full_coverage_dates),
            "mode": plan.mode,
        },
        "canary": dict(canary) if canary else None,
        "days": list(days),
        "failed_days": list(failed_days),
        "summary": dict(summary),
        "expected_sector_codes": list(expected_sector_codes),
        "expected_sector_names": dict(expected_sector_names),
        "query_budget": list(query_budget),
        "checks": dict(checks),
        "stop_conditions_hit": list(summary.get("stop_conditions_hit", [])),
    }


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
    env: Mapping[str, str] | None = None,
    policy: CompletedSessionPolicy | None = None,
    updated_at: str | None = None,
) -> int:
    """Gate-3 CLI 入口（dry-run 默认；``--apply --yes`` 才执行真实 backfill）。"""
    args = build_parser().parse_args(argv)
    report_dir = resolve_report_dir(args.report_dir)

    try:
        report = _load_expected_report(args.expected_file)
    except Gate3Stop as exc:
        print(f"[{TOOL}] EXIT_PARAM {exc.sc_id}: {exc}", file=sys.stderr)
        return exc.exit_code

    try:
        range_report = report
        if args.range_file:
            range_report = _load_expected_report(args.range_file)
        plan = resolve_range(
            range_report,
            canary_date=args.canary_date,
            range_file=args.range_file,
            start_date=args.start_date,
            end_date=args.end_date,
            policy=policy,
        )
    except Gate3Stop as exc:
        print(f"[{TOOL}] EXIT_PARAM {exc.sc_id}: {exc}", file=sys.stderr)
        return exc.exit_code

    if not (args.apply and args.yes):
        _print_dry_run_plan(args, report_dir, plan)
        return EXIT_OK

    try:
        conn = ConnLoader(env=env, client_factory=client_factory)
        db = conn.load_db()
    except MissingConnectionKeyError as exc:
        print(f"[{TOOL}] EXIT_CONN: {exc}", file=sys.stderr)
        return EXIT_CONN
    except Exception as exc:  # noqa: BLE001 — 连接/认证失败（G3-S-001）
        print(
            f"[{TOOL}] EXIT_CONN: connection/auth failed ({type(exc).__name__})",
            file=sys.stderr,
        )
        return EXIT_CONN

    secret_entries = conn.secret_entries()
    writer = ProdRankingWriter(db)
    expected_codes = [str(c) for c in report.get("expected_sector_codes", [])]
    expected_names = {
        str(k): str(v) for k, v in (report.get("expected_sector_names") or {}).items()
    }
    # L1 契约校正：行情 join 键 = Gate-1 expected_full_symbols（.SI 后缀）。
    expected_full_symbols = [str(s) for s in report.get("expected_full_symbols", [])]
    full_dates = list(plan.full_coverage_dates)
    date_format = str(report.get("trade_date_format") or "YYYYMMDD")

    # G3-B-018 / G3-B-019：Gate-3 reader 禁用全局累计阻断
    # （cumulative_rows_limit=None），启用日级上限 4 × len(expected)（31 → 124）。
    day_rows_limit = 4 * len(expected_codes)
    budget = BudgetReader(
        db,
        cumulative_rows_limit=None,
        day_rows_limit=day_rows_limit,
    )

    days: list[dict[str, Any]] = []
    failed_days: list[dict[str, Any]] = []
    stop_conditions: list[str] = []
    canary_payload: dict[str, Any] | None = None
    day_outcomes: list[DayOutcome] = []
    last_success: str | None = None

    try:
        for trade_date in plan.dates:
            day_start = time_mod.monotonic()
            try:
                if trade_date in full_dates:
                    day_index = full_dates.index(trade_date)
                    prev_date = full_dates[day_index - 1] if day_index > 0 else None
                else:
                    prev_date = None
                outcome = process_day(
                    trade_date,
                    prev_date=prev_date,
                    expected_codes=expected_codes,
                    expected_names=expected_names,
                    expected_full_symbols=expected_full_symbols,
                    db=db,
                    writer=writer,
                    budget=budget,
                    date_format=date_format,
                    updated_at=updated_at,
                )
                outcome.ms = round(time_mod.monotonic() - day_start, 3)
                day_outcomes.append(outcome)
                days.append(
                    {
                        "trade_date": outcome.trade_date,
                        "status": outcome.status,
                        "expected": outcome.expected,
                        "observed": outcome.observed,
                        "upserted": outcome.upserted,
                        "failed": outcome.failed,
                        "ms": round(outcome.ms, 3),
                        # G3-A-003：per-day query_budget（单日计数，G3-B-017）。
                        "query_budget": list(outcome.query_budget),
                    }
                )
                if outcome.status == "complete":
                    last_success = outcome.trade_date
            except Gate3Stop as exc:
                stop_conditions.append(exc.sc_id)
                # M5：失败日保留于 failed_days[]（即使不进成功 days[]）。
                failed_days.append(
                    {
                        "trade_date": trade_date,
                        "status": _failed_status(exc.sc_id),
                        # G3-S-013：observed = 该日实际命中行数（> day_limit）。
                        "observed": budget.cumulative_rows,
                        # G3-S-013 必填 day_limit；其他 SC 为 null（DESIGN §3.6.6）。
                        "day_limit": day_rows_limit if exc.sc_id == "G3-S-013" else None,
                        "stop_id": exc.sc_id,
                        "ms": round(time_mod.monotonic() - day_start, 3),
                        # 停止前已执行的单日查询统计（G3-B-017 per-day scoped）。
                        "query_budget": budget.stats(),
                    }
                )
                log_jsonl(
                    report_dir,
                    "gate3",
                    {"action": "day_stop", "trade_date": trade_date,
                     "sc_id": exc.sc_id, "message": str(exc)},
                    secret_entries=secret_entries,
                )
                break
    except NamespaceViolation as exc:
        stop_conditions.append("G3-S-009")
        log_jsonl(
            report_dir,
            "gate3",
            {"action": "stop", "sc_id": "G3-S-009", "message": str(exc)},
            secret_entries=secret_entries,
        )
    except Exception as exc:  # noqa: BLE001 — 任意未知异常（G3-S-012）
        stop_conditions.append("G3-S-012")
        log_jsonl(
            report_dir,
            "gate3",
            {"action": "stop", "sc_id": "G3-S-012",
             "message": f"{type(exc).__name__}: {exc}"},
            secret_entries=secret_entries,
        )

    if plan.mode == "canary" and day_outcomes:
        day = day_outcomes[0]
        canary_payload = {
            "date": day.trade_date,
            "outcome": day.status,
            "read_back": "ok" if day.status == "complete" else "n/a",
        }

    success_days = sum(1 for d in day_outcomes if d.status == "complete")
    # 失败日 = failed_days[]（停止条件命中的日）+ days[] 中非 complete 的日。
    failed_days_count = len(failed_days) + sum(
        1 for d in days if d["status"] != "complete"
    )
    # M4：job 级聚合由保留的逐日记录（days[] ∪ failed_days[]）派生，reset-safe。
    retained_records = days + failed_days
    total_query_rows = _sum_query_rows(retained_records)
    summary = {
        "success_days": success_days,
        "failed_days": failed_days_count,
        "stop_conditions_hit": stop_conditions,
        # G3-A-004：全量累计查询命中行数（informational，G3-B-019）。
        "total_query_rows": total_query_rows,
        # G3-A-004：停止时记录最后成功日，供修复后显式重跑（G3-B-001）。
        "resumption_boundary": last_success,
        # G3-B-018：日级上限实际值（4 × len(expected)，31 → 124）。
        "day_rows_limit": day_rows_limit,
    }

    payload = _build_report_payload(
        conn_fingerprint=conn.fingerprint(),
        plan=plan,
        canary=canary_payload,
        days=days,
        failed_days=failed_days,
        summary=summary,
        expected_sector_codes=expected_codes,
        expected_sector_names=expected_names,
        query_budget=_aggregate_query_budget(retained_records),
        checks={"G3-B-001": "PASS", "G3-B-013": "PASS", "G3-B-016": "PASS"}
        if not stop_conditions
        else {},
    )
    write_report(report_dir, "gate3", payload)
    hits = scan_secrets(
        json.dumps(payload, ensure_ascii=False), secret_entries=secret_entries
    )
    if hits:
        stop_conditions.append("G3-S-011")
        summary["stop_conditions_hit"] = stop_conditions
        payload["stop_conditions_hit"] = stop_conditions
        write_report(report_dir, "gate3", payload)
        print(
            f"[{TOOL}] STOP G3-S-011: secret leak detected in report output: {hits}",
            file=sys.stderr,
        )
        return EXIT_STOP

    log_jsonl(
        report_dir,
        "gate3",
        {"action": "apply_done", "success_days": success_days,
         "failed_days": failed_days_count, "stop_conditions_hit": stop_conditions},
        secret_entries=secret_entries,
    )
    if stop_conditions:
        print(
            f"[{TOOL}] STOP {stop_conditions}: see gate3-report.json",
            file=sys.stderr,
        )
        return EXIT_STOP
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
