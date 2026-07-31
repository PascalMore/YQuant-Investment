"""Gate-3 工具：真实 TA-CN 历史 backfill CLI（dry-run / canary / 全量，日级原子）。

DESIGN-03-016 V0.4 §3.6 / SPEC-03-016 §3.4。读取 Gate-1 report
（``--expected-file``，唯一 expected universe 来源，H-049u），从
``index_daily_quotes`` 按日构建（复用冻结 ``build_ranking_rows``，100%
exact-match、固定 pct_chg 公式），经 :class:`ProdRankingWriter` upsert 到
``03_data_ud_sector_ranking_daily``，写后读回（G3-V-001~004）。范围来源
二选一（``--range-file`` / 成对 ``--start-date``/``--end-date``）或 canary
单日（``--canary-date``），互斥规则按 F1 冻结（§3.6.3）。

退出码（SPEC G0-C-004）：0 成功 / 1 参数前置失败 / 2 停止条件 / 3 连接凭据失败。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from skills.data.unified_data.models.domain.sector_ranking import (
    SectorRankingDaily,
    coerce_float,
)
from skills.data.unified_data.services.historical_sector_service import (
    build_ranking_rows,
)

from .common import (
    BudgetReader,
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

# realtime/intraday 标记（G3-B-009 / G3-S-010，RT-4）。
REALTIME_MARKERS: frozenset[str] = frozenset({"realtime", "intraday", "rt"})


class Gate3Stop(Exception):
    """Gate-3 停止/参数失败条件命中。"""

    def __init__(self, sc_id: str, message: str, exit_code: int = EXIT_STOP) -> None:
        self.sc_id = sc_id
        self.exit_code = exit_code
        super().__init__(message)


@dataclass
class RangePlan:
    """范围解析结果（DESIGN §3.6.3）。"""

    mode: str  # "canary" | "range"
    dates: list[str] = field(default_factory=list)  # 升序去重处理日
    excluded_first: str | None = None  # --range-file 模式默认排除的最早可用日
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
    """读取并校验 Gate-1 report（G3-S-002 → EXIT_PARAM(1)）。"""
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
    if "expected_sector_codes" not in report or "expected_sector_names" not in report:
        raise Gate3Stop(
            "G3-S-002",
            "--expected-file JSON missing expected_sector_codes/expected_sector_names",
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
    * ``--range-file`` 模式：范围 = ``coverage_by_date`` 键集，升序去重，
      默认排除最早可用日（首日无前一日 close，G3-B-016）。
    * 显式成对 ``--start-date``/``--end-date``：必须成对、start<=end、
      均 ⊆ Gate-1 ``trade_date_range``、经 ``CompletedSessionPolicy`` 判定
      非未来日 / 非「当日未收盘」（policy 不可用 → fail-closed 退出码 1）。
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
        return RangePlan(mode="canary", dates=[canary_date], reason="canary single day")

    if range_file:
        if start_date or end_date:
            raise Gate3Stop(
                "G3-S-003",
                "--range-file is mutually exclusive with --start-date/--end-date",
                exit_code=EXIT_PARAM,
            )
        coverage = report.get("coverage_by_date") or {}
        dates = sorted({str(d) for d in coverage.keys()})
        excluded = dates[0] if dates else None
        if excluded is not None:
            dates = dates[1:]
        return RangePlan(
            mode="range",
            dates=dates,
            excluded_first=excluded,
            reason="full range from coverage_by_date, earliest excluded",
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
        coverage = report.get("coverage_by_date") or {}
        dates = [d for d in sorted(coverage) if start <= str(d) <= end]
        return RangePlan(mode="range", dates=dates, reason="explicit paired subrange")

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
) -> DayOutcome:
    """处理单个交易日（读取 → 构建 → upsert → 写后读回，日级原子）。

    * ``prev_date=None``（无前一日）→ ``DayOutcome(status=\"empty\",
      reason=\"no-prev-close\")``（G3-B-004 / G3-B-016）。
    * 任一完整性 / rt / upsert / 读回失败 → ``Gate3Stop``（G3-S-004~007/010），
      不物化部分榜单（G3-B-012）。
    """
    reader = budget if budget is not None else BudgetReader(db)
    if prev_date is None:
        return DayOutcome(
            trade_date=trade_date,
            status="empty",
            expected=len(expected_codes),
            reason="no-prev-close",
        )

    internal_day = _to_internal(trade_date, date_format)
    internal_prev = _to_internal(prev_date, date_format)

    docs = reader.find(
        "index_daily_quotes",
        {
            "sector_code": {"$in": expected_codes},
            "trade_date": {"$in": [internal_day, internal_prev]},
        },
    )
    if any(_is_rt_marker(doc.get("source")) for doc in docs):
        raise Gate3Stop(
            "G3-S-010",
            "realtime/intraday marker detected in index_daily_quotes rows; "
            "refusing to materialize (RT-4)",
        )

    day_docs = {str(d["sector_code"]): d for d in docs if d["trade_date"] == internal_day}
    prev_docs = {str(d["sector_code"]): d for d in docs if d["trade_date"] == internal_prev}

    candidates: list[dict[str, Any]] = []
    for code in expected_codes:
        day_row = day_docs.get(code)
        prev_row = prev_docs.get(code)
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
        ms=0.0,
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


def _build_report_payload(
    *,
    conn_fingerprint: Mapping[str, Any],
    plan: RangePlan,
    canary: Mapping[str, Any] | None,
    days: list[dict[str, Any]],
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
            "mode": plan.mode,
        },
        "canary": dict(canary) if canary else None,
        "days": list(days),
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
    budget = BudgetReader(db)
    expected_codes = [str(c) for c in report.get("expected_sector_codes", [])]
    expected_names = {
        str(k): str(v) for k, v in (report.get("expected_sector_names") or {}).items()
    }
    full_dates = sorted({str(d) for d in (report.get("coverage_by_date") or {})})
    date_format = str(report.get("trade_date_format") or "YYYYMMDD")

    days: list[dict[str, Any]] = []
    stop_conditions: list[str] = []
    canary_payload: dict[str, Any] | None = None
    day_outcomes: list[DayOutcome] = []

    try:
        for trade_date in plan.dates:
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
                    db=db,
                    writer=writer,
                    budget=budget,
                    date_format=date_format,
                    updated_at=updated_at,
                )
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
                    }
                )
            except Gate3Stop as exc:
                stop_conditions.append(exc.sc_id)
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
    failed_days = len(day_outcomes) - success_days
    summary = {
        "success_days": success_days,
        "failed_days": failed_days,
        "stop_conditions_hit": stop_conditions,
    }

    payload = _build_report_payload(
        conn_fingerprint=conn.fingerprint(),
        plan=plan,
        canary=canary_payload,
        days=days,
        summary=summary,
        expected_sector_codes=expected_codes,
        expected_sector_names=expected_names,
        query_budget=budget.stats(),
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
         "failed_days": failed_days, "stop_conditions_hit": stop_conditions},
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
