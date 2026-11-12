"""BTC5m 官方历史摄入 CLI — 03-018 §7.1。

子命令：``backfill`` / ``daily`` / ``plan`` / ``verify``。

* ``plan`` 与**不带** ``--apply`` 的 backfill / daily 只读检查点、输出计划；
  不 DDL、不下载历史、不创建 raw / stream。
* ``verify`` 只读精确区间（raw 文件校验 / DB 读回 / manifest 比较）；
  不联网、不 DDL、不推进状态。
* 实际写入必须显式 ``--apply``；不新增审批 token / 审批平台。
* 参数错误先于 env / I/O；argparse 错误也映射为退出码 20。

退出码：0 / 10 / 20 / 30 / 40（见 :mod:`btc5m_history.common`）。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# 文件入口与包入口共用同一模块身份，不注入扁平 scripts 路径。
if __name__ == "__main__" and not __package__:
    import importlib

    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    raise SystemExit(importlib.import_module(
        "skills.data.data-pipeline.scripts.run_btc5m_history"
    ).main())

from .btc5m_history.common import (
    Budget,
    EXIT_BUSY,
    EXIT_FAIL,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_TIMEOUT,
    HistoryBudgetError,
    HistoryHTTPError,
    RawArchive,
    day_bounds_us,
    utc_now,
)
from .btc5m_history.runner import (
    HistoryRunner,
    IngestionStore,
    advance_contiguous,
    combined_complete_through,
    plan_days,
)

#: 首次主窗口（固定）。
DEFAULT_START_UTC = "2026-08-10T00:00:00Z"
DEFAULT_END_UTC = "2026-11-10T00:00:00Z"

#: 两个数据集（固定顺序）。
DATASETS = ("predict_btc5m_rounds", "binance_spot_btcusdt_1s")


def _parse_utc(text: str) -> datetime:
    """解析显式 UTC 时间（拒绝 naive / 非 UTC）。"""
    value = text.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid UTC timestamp {text!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError("naive timestamps are not accepted")
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("non-UTC timestamps are not accepted")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _add_common(parser: argparse.ArgumentParser, *, require_window: bool) -> None:
    if require_window:
        parser.add_argument("--start-utc", required=True)
        parser.add_argument("--end-utc", required=True)
    else:
        parser.add_argument("--start-utc", default=None)
        parser.add_argument("--end-utc", default=None)
    parser.add_argument("--warmup-seconds", type=int, default=0)
    parser.add_argument("--max-days-per-source", type=int, default=7)
    parser.add_argument("--wall-seconds", type=int, default=1800)
    parser.add_argument("--max-requests", type=int, default=1000)
    parser.add_argument("--chunk-size", type=int, default=5000)
    if parser.prog.split()[-1] != "verify":
        parser.add_argument("--retry-day", action="append", default=[],
                            metavar="DATASET:YYYY-MM-DD")
        parser.add_argument("--restart-scan", action="store_true")
    parser.add_argument("--report-dir", default=None)


def build_parser() -> argparse.ArgumentParser:
    """构造 CLI 参数解析器。

    Returns:
        :class:`argparse.ArgumentParser`。
    """
    parser = argparse.ArgumentParser(
        prog="run_btc5m_history",
        description="Ingest official BTC5m rounds / Binance spot 1s history.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    backfill = sub.add_parser("backfill", help="explicit-window backfill / resume")
    _add_common(backfill, require_window=True)
    backfill.add_argument("--apply", action="store_true")

    daily = sub.add_parser("daily", help="incremental daily catch-up")
    _add_common(daily, require_window=False)
    daily.add_argument("--apply", action="store_true")

    plan = sub.add_parser("plan", help="read-only plan; never writes")
    _add_common(plan, require_window=False)

    verify = sub.add_parser("verify", help="read-only verification of a window")
    _add_common(verify, require_window=True)
    verify.add_argument("--resume-report", default=None)
    return parser


def _validate_common(args: argparse.Namespace) -> Budget:
    """校验公共参数并返回预算。

    Raises:
        ValueError: 参数越界 / 时间非法。
    """
    budget = Budget(
        max_days_per_source=args.max_days_per_source,
        wall_seconds=args.wall_seconds,
        max_requests=args.max_requests,
        chunk_size=args.chunk_size,
    )
    budget.validate()
    if args.warmup_seconds < 0:
        raise ValueError("warmup-seconds must be >= 0")
    if args.command in ("backfill", "verify", "plan"):
        if bool(args.start_utc) != bool(args.end_utc):
            raise ValueError("both window bounds are required")
        if args.start_utc:
            start, end = _parse_utc(args.start_utc), _parse_utc(args.end_utc)
            if start >= end:
                raise ValueError("start-utc must be < end-utc")
            if args.command == "backfill" and (
                start != _parse_utc(DEFAULT_START_UTC)
                or end != _parse_utc(DEFAULT_END_UTC)
            ):
                raise ValueError("backfill requires the frozen 92-day target")
    if args.command == "daily" and (args.start_utc or args.end_utc):
        raise ValueError("daily uses the stored anchor and actual cutoff")
    if args.command == "daily" and not 1 <= args.max_days_per_source <= 7:
        raise ValueError("daily max-days-per-source must be within 1..7")
    args.retry_days = sorted(set(getattr(args, "retry_day", [])))
    for token in args.retry_days:
        dataset, separator, day = token.partition(":")
        if not separator or dataset not in DATASETS:
            raise ValueError("RETRY_DAY_INVALID")
        try:
            parsed = datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            raise ValueError("RETRY_DAY_INVALID") from None
        if parsed.strftime("%Y-%m-%d") != day:
            raise ValueError("RETRY_DAY_INVALID")
        lower, upper = _window_start_date(args), _window_end_date(args)
        if (lower and day < lower) or (upper and day >= upper):
            raise ValueError("RETRY_DAY_OUTSIDE_WINDOW")
    return budget


def _open_store() -> IngestionStore:
    """打开 UD 目标库的检查点存储。"""
    from skills.data.unified_data.storage import UD_DATABASE

    from skills.data.data_interface.mongo_reader import MongoReader

    reader = MongoReader(database=UD_DATABASE)
    return IngestionStore(reader.db)


def _write_summary(report_dir: str | None, payload: dict[str, Any]) -> str | None:
    """写本地 summary（主题 evidence 内）。"""
    if not report_dir:
        return None
    directory = Path(report_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "summary.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return str(path)


def _api_key() -> str | None:
    """Read an injected key without exposing its value or file path in errors."""
    import os
    import stat

    value = os.environ.get("PM_PREDICT_API_KEY", "").strip()
    if value:
        return value
    filename = os.environ.get("PM_PREDICT_API_KEY_FILE")
    if not filename:
        raise HistoryHTTPError("PREDICT_API_KEY_MISSING")
    descriptor = None
    try:
        descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or metadata.st_mode & 0o077 or metadata.st_size > 65536):
            raise HistoryHTTPError("PREDICT_API_KEY_FILE_UNSAFE")
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            descriptor = None
            value = handle.read(65537).strip()
        if not value:
            raise HistoryHTTPError("PREDICT_API_KEY_FILE_EMPTY")
        return value
    except (OSError, UnicodeError, ValueError):
        raise HistoryHTTPError("PREDICT_API_KEY_FILE_UNAVAILABLE") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _window_bounds(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """返回显式窗口边界（naive-UTC）。"""
    start = _parse_utc(args.start_utc)
    end = _parse_utc(args.end_utc)
    return start, end


def _date_of(moment: datetime) -> str:
    """返回 naive-UTC datetime 的 UTC 日。"""
    return moment.strftime("%Y-%m-%d")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。

    Args:
        argv: 参数列表（默认 ``sys.argv[1:]``）。

    Returns:
        退出码 0 / 10 / 20 / 30 / 40。
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return EXIT_FAIL

    try:
        budget = _validate_common(args)
    except (ValueError, HistoryBudgetError) as exc:
        print(f"[history] EXIT_FAIL: {exc}", file=sys.stderr)
        return EXIT_FAIL

    if args.command == "verify":
        return _run_verify(args, budget)

    if getattr(args, "apply", False):
        from scripts.unified_data.ud_lock import UDLockBusy, acquire_ud_lock

        try:
            with acquire_ud_lock():
                return _run_ingestion(args, budget)
        except UDLockBusy:
            print("[history] EXIT_BUSY: ud lock is held", file=sys.stderr)
            return EXIT_BUSY
    return _run_ingestion(args, budget)


def _run_ingestion(args: argparse.Namespace, budget: Budget) -> int:
    """拿写锁之后才打开数据库；只读规划无需写锁。"""
    try:
        store = _open_store()
    except Exception as exc:  # noqa: BLE001 — 连接 / 权限失败
        print(
            f"[history] EXIT_FAIL: cannot open the ingestion store "
            f"({type(exc).__name__})",
            file=sys.stderr,
        )
        return EXIT_FAIL

    cutoff_date = _cutoff_date()
    payload: dict[str, Any] = {
        "command": args.command,
        "mode": "apply" if getattr(args, "apply", False) else "plan",
        "cutoff_utc_date": cutoff_date,
        "budget": {
            "max_days_per_source": budget.max_days_per_source,
            "wall_seconds": budget.wall_seconds,
            "max_requests": budget.max_requests,
            "chunk_size": budget.chunk_size,
        },
        "datasets": {},
    }

    payload["retry_days"] = getattr(args, "retry_days", [])
    exit_code = EXIT_FAIL
    try:
        planned = _ingestion_plans(args, budget, store, cutoff_date)
        payload["plans"] = {dataset: [_plan_payload(plan) for plan in plans]
                            for dataset, plans in planned.items()}
        payload["deferred_days"] = _deferred_days(args, store, cutoff_date, planned)
        if getattr(args, "restart_scan", False):
            stream = store.get_stream(DATASETS[0]) or {}
            payload["restart_scan"] = {
                "lower_us": stream.get("scan_lower_us"),
                "upper_us": stream.get("scan_upper_us"),
                "manifest_ref": stream.get("scan_manifest_ref"),
                "mode": "apply" if getattr(args, "apply", False) else "plan",
            }
            if not (stream.get("scan_cursor") or stream.get("scan_manifest_ref")):
                raise ValueError("NO_ACTIVE_SCAN")
            start, end = _source_window(args, store, DATASETS[0], cutoff_date)
            lower, upper = stream.get("scan_lower_us"), stream.get("scan_upper_us")
            if (not isinstance(lower, int) or not isinstance(upper, int)
                    or not day_bounds_us(start)[0] <= lower < upper <= day_bounds_us(end)[0]):
                raise ValueError("RESTART_SCAN_OUTSIDE_WINDOW")
            retries = [token.split(":")[1] for token in payload["retry_days"]
                       if token.split(":")[0] == DATASETS[0]]
            if any(not lower <= day_bounds_us(day)[0] < upper for day in retries):
                raise ValueError("RETRY_DAY_RESTART_SCAN_CONFLICT")
        if args.command == "plan" or not getattr(args, "apply", False):
            payload["note"] = "plan only; no DB write, no raw download"
            payload["watermarks"] = _watermarks(store)
            print("[history] plan only — no DB write, no raw download")
            exit_code = EXIT_OK
        else:
            exit_code = _run_apply(args, budget, store, payload)
    except HistoryBudgetError:
        payload["error_code"] = "BUDGET_EXHAUSTED"
        exit_code = EXIT_PARTIAL
    except HistoryHTTPError as exc:
        payload["error_code"] = exc.code
        print(f"[history] EXIT_FAIL: {exc.code}", file=sys.stderr)
    except ValueError as exc:
        payload["error_code"] = str(exc)
        print(f"[history] EXIT_FAIL: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        payload["error_code"] = "INTERRUPTED"
        exit_code = EXIT_TIMEOUT
    finally:
        payload["exit_code"] = exit_code
        _write_summary(args.report_dir, payload)
    return exit_code


def _plan_payload(plan: Any) -> dict[str, Any]:
    return {"utc_date": plan.utc_date, "reason": plan.reason,
            "stored_due": plan.stored_due, "effective_due": plan.effective_due,
            "retry_policy": plan.retry_policy}


def _source_window(args: argparse.Namespace, store: IngestionStore,
                   dataset: str, cutoff: str) -> tuple[str, str]:
    start = _window_start_date(args)
    if start is None:
        stream = store.get_stream(dataset)
        if not stream or stream.get("ingestion_start_us") is None:
            raise HistoryHTTPError("NOT_INITIALIZED")
        start = _date_of(datetime(1970, 1, 1) + timedelta(
            microseconds=stream["ingestion_start_us"]))
    return start, min(_window_end_date(args) or cutoff, cutoff)


def _ingestion_plans(args: argparse.Namespace, budget: Budget, store: IngestionStore,
                     cutoff: str) -> dict[str, Any]:
    plans = {}
    for dataset in DATASETS:
        start, end = _source_window(args, store, dataset, cutoff)
        plans[dataset] = plan_days(store, dataset, cutoff_utc_date=cutoff,
            max_days=budget.max_days_per_source, start_utc_date=start, end_utc_date=end,
            retry_dates=[token.split(":")[1] for token in getattr(args, "retry_days", [])
                         if token.split(":")[0] == dataset])
    return plans


def _deferred_days(args: argparse.Namespace, store: IngestionStore, cutoff: str,
                   plans: dict[str, Any]) -> dict[str, Any]:
    from .btc5m_history.runner import day_retry_policy

    result = {}
    moment = utc_now()
    for dataset in DATASETS:
        start, end = _source_window(args, store, dataset, cutoff)
        selected = {plan.utc_date for plan in plans[dataset]}
        deferred = []
        for day in store.list_days(dataset):
            date = day["utc_date"]
            if not start <= date < end or day["state"] == "complete":
                continue
            effective, policy = day_retry_policy(day)
            if date not in selected:
                deferred.append({"utc_date": date, "error_code": day.get("error_code"),
                    "stored_due": day.get("next_retry_at"), "effective_due": effective,
                    "retry_policy": policy, "deferred_reason": "manual_review" if policy == "manual_review"
                    else "cooldown" if effective and effective > moment else "day_budget"})
        result[dataset] = deferred
    return result


def _previous_day(utc_date: str) -> str:
    """返回前一个 UTC 日。"""
    day = datetime.strptime(utc_date, "%Y-%m-%d")
    return (day - timedelta(days=1)).strftime("%Y-%m-%d")


def _cutoff_date() -> str:
    """返回本次 cutoff UTC 日（当前 UTC 日，不含）。"""
    from .btc5m_history.common import utc_today

    return utc_today()


def _window_start_date(args: argparse.Namespace) -> str | None:
    """显式窗口下界日（无窗口返回 ``None``）。"""
    if not getattr(args, "start_utc", None):
        return None
    return _date_of(_parse_utc(args.start_utc) - timedelta(seconds=args.warmup_seconds))


def _window_end_date(args: argparse.Namespace) -> str | None:
    """显式窗口上界日（无窗口返回 ``None``）。"""
    if not getattr(args, "end_utc", None):
        return None
    return _date_of(_parse_utc(args.end_utc))


def _run_apply(
    args: argparse.Namespace,
    budget: Budget,
    store: IngestionStore,
    payload: dict[str, Any],
) -> int:
    """执行 apply（真实管道 + 日提交 + 水位推进）。

    ``backfill`` 首次运行会显式初始化两源 stream 锚点；``daily`` 必须已有
    锚点，否则 ``NOT_INITIALIZED`` / 退出 20。
    """
    command = args.command
    cutoff_date = payload.get("cutoff_utc_date") or _cutoff_date()
    if command == "daily" and any(store.get_stream(dataset) is None for dataset in DATASETS):
        print("[history] EXIT_FAIL: NOT_INITIALIZED — run backfill first", file=sys.stderr)
        return EXIT_FAIL
    from .btc5m_history.runner import ensure_history_indexes

    ensure_history_indexes(store.db)
    end: datetime | None = None
    if command == "backfill":
        start, end = _window_bounds(args)
        start_us = int((start - datetime(1970, 1, 1)).total_seconds()) * 1_000_000
        start_us -= args.warmup_seconds * 1_000_000
        for dataset in DATASETS:
            try:
                store.init_stream(dataset, ingestion_start_us=start_us)
            except HistoryBudgetError as exc:
                print(f"[history] EXIT_FAIL: {exc}", file=sys.stderr)
                return EXIT_FAIL
        payload["ingestion_start_us"] = start_us
        target_end_us = int((end - datetime(1970, 1, 1)).total_seconds()) * 1_000_000
    elif command == "daily":
        for dataset in DATASETS:
            if store.get_stream(dataset) is None:
                print(
                    "[history] EXIT_FAIL: NOT_INITIALIZED — run backfill first",
                    file=sys.stderr,
                )
                return EXIT_FAIL
        target_end_us = day_bounds_us(cutoff_date)[0]
        payload["ingestion_start_us"] = None
    else:
        print(f"[history] EXIT_FAIL: unsupported command {command!r}", file=sys.stderr)
        return EXIT_FAIL

    exit_code = EXIT_OK
    payload["target_end_us"] = target_end_us

    archive = RawArchive()
    api_key = None
    predict_error = None
    try:
        api_key = _api_key()
    except HistoryHTTPError as exc:
        predict_error = exc.code
        exit_code = _worse(exit_code, EXIT_FAIL)
    from .btc5m_history.runner import recheck_pending

    pending_budget = budget.fork(
        requests=min(200, max(2, budget.max_requests // 5)),
        seconds=max(0.0, budget.remaining() / 5),
    )
    try:
        if not predict_error:
            payload["pending_rechecked"] = asyncio.run(recheck_pending(
                store.db, budget=pending_budget, archive=archive, api_key=api_key,
            ))
    except HistoryBudgetError:
        payload["pending_error"] = "BUDGET_EXHAUSTED"
        exit_code = _worse(exit_code, EXIT_PARTIAL)
    except HistoryHTTPError as exc:
        payload["pending_error"] = exc.code
        exit_code = _worse(exit_code, EXIT_FAIL)
        predict_error = exc.code
    except Exception as exc:  # No external exception text may expose headers or credentials.
        payload["pending_error"] = type(exc).__name__
        predict_error = type(exc).__name__
        exit_code = _worse(exit_code, EXIT_FAIL)

    source_plans = (payload.get("plans") or {
        dataset: [_plan_payload(plan) for plan in plans]
        for dataset, plans in _ingestion_plans(args, budget, store, cutoff_date).items()
    })
    for source_index, dataset in enumerate(DATASETS):
        remaining_sources = len(DATASETS) - source_index
        source_budget = budget.fork(
            requests=(budget.max_requests - budget.requests_used) // remaining_sources,
            seconds=budget.remaining() / remaining_sources,
        )
        runner = HistoryRunner(store, store.db, budget=source_budget,
                               archive=archive, api_key=api_key)
        dates = [plan["utc_date"] for plan in source_plans[dataset]]
        payload["datasets"][dataset] = {
            "planned_dates": dates,
            "results": [],
        }
        if dataset == "predict_btc5m_rounds" and predict_error:
            payload["datasets"][dataset]["error_code"] = predict_error
            continue
        if not dates and not (dataset == DATASETS[0] and getattr(args, "restart_scan", False)):
            continue
        results = []
        try:
            if dataset == "predict_btc5m_rounds":
                options = {"restart_scan": True} if getattr(args, "restart_scan", False) else {}
                results = asyncio.run(runner.run_round_days(dates, **options))
            else:
                for date in dates:
                    results.append(asyncio.run(runner.run_kline_day(date)))
        except HistoryBudgetError:
            payload["datasets"][dataset]["error_code"] = "BUDGET_EXHAUSTED"
            print("[history] EXIT_PARTIAL: BUDGET_EXHAUSTED", file=sys.stderr)
            exit_code = _worse(exit_code, EXIT_PARTIAL)
        except HistoryHTTPError as exc:
            payload["datasets"][dataset]["error_code"] = exc.code
            print(f"[history] EXIT_FAIL: {exc.code}", file=sys.stderr)
            exit_code = _worse(exit_code, EXIT_FAIL)
        except KeyboardInterrupt:
            payload["datasets"][dataset]["error_code"] = "INTERRUPTED"
            raise
        except Exception as exc:
            payload["datasets"][dataset]["error_code"] = type(exc).__name__
            exit_code = _worse(exit_code, EXIT_FAIL)
        finally:
            # Preserve returned results even when interruption skips the remaining sources.
            for result in results:
                if result.error_code:
                    payload["datasets"][dataset].setdefault("error_code", result.error_code)
                payload["datasets"][dataset]["results"].append(
                    {
                        "utc_date": result.utc_date,
                        "state": result.state,
                        "error_code": result.error_code,
                        "content_sha256": result.content_sha256,
                        "counts": result.counts,
                    }
                )
                if result.state in ("failed", "conflict"):
                    exit_code = _worse(exit_code, EXIT_FAIL)
                elif result.state in ("gap", "pending"):
                    exit_code = _worse(exit_code, EXIT_PARTIAL)

    payload["watermarks"] = _watermarks(store)
    if exit_code == EXIT_OK and not _is_complete(store, payload):
        exit_code = EXIT_PARTIAL
    return exit_code


def _worse(current: int, candidate: int) -> int:
    """按 20 > 40 > 10 > 0 的优先级取更严重者。"""
    rank = {EXIT_OK: 0, EXIT_PARTIAL: 1, EXIT_TIMEOUT: 2, EXIT_FAIL: 3}
    if rank.get(candidate, 0) > rank.get(current, 0):
        return candidate
    return current


def _watermarks(store: IngestionStore) -> dict[str, Any]:
    """返回两源水位与联合水位。"""
    out: dict[str, Any] = {}
    anchors: list[int] = []
    for dataset in DATASETS:
        stream = store.get_stream(dataset)
        anchor = stream.get("ingestion_start_us") if stream else None
        complete = stream.get("complete_through_us") if stream else None
        out[dataset] = {
            "ingestion_start_us": anchor,
            "complete_through_us": complete,
            "enumerated_through_us": (
                stream.get("enumerated_through_us") if stream else None
            ),
        }
        if anchor is not None:
            anchors.append(int(anchor))
    combined = None
    if len(anchors) == len(DATASETS):
        combined = combined_complete_through(
            {dataset: store for dataset in DATASETS},
            ingestion_start_us=anchors[0],
        )
    out["combined_complete_through_us"] = combined
    return out


def _is_complete(store: IngestionStore, payload: dict[str, Any]) -> bool:
    """返回两源是否都已推进到目标窗口末端。"""
    watermarks = payload.get("watermarks") or {}
    combined = watermarks.get("combined_complete_through_us")
    if combined is None:
        return False
    target_end = payload.get("target_end_us")
    if target_end is None:
        return False
    return int(combined) >= int(target_end)


def _verification_snapshot(rows: list[dict[str, Any]], day: dict[str, Any] | None) -> str:
    """Bind final consumption to exact BSON, observation times and shard/raw references."""
    import hashlib
    from bson import json_util

    ordered = sorted(rows, key=lambda row: (row.get("open_time_us", row.get("starts_at_us", 0)),
                                            row.get("round_id", "")))
    raw = json_util.dumps({"rows": ordered, "shard": day},
                          json_options=json_util.CANONICAL_JSON_OPTIONS, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _resume_digest(payload: dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(json.dumps({key: payload.get(key) for key in (
        "command", "window", "verified_content", "verified_snapshots",
    )}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _run_verify(args: argparse.Namespace, budget: Budget) -> int:
    """只读重算实际日内容与 raw 字节；有界续核不把检查点当内容证明。"""
    from pymongo import timeout
    from .btc5m_history.runner import _digest_of, _window_dates
    from .btc5m_history.common import DATASET_KLINES, KLINES_COLLECTION, ROUNDS_COLLECTION

    start, end = _window_bounds(args)
    window = {"start_utc": args.start_utc, "end_utc": args.end_utc,
              "warmup_seconds": args.warmup_seconds, "chunk_size": args.chunk_size,
              "max_days_per_source": args.max_days_per_source,
              "wall_seconds": args.wall_seconds, "max_requests": args.max_requests,
              "datasets": list(DATASETS), "verification_version": 1}
    resume = _load_resume(args.resume_report)
    if args.resume_report and (not resume or resume.get("window") != window
                               or resume.get("command") != "verify"
                               or resume.get("resume_sha256") != _resume_digest(resume)):
        print("[history] EXIT_FAIL: RESUME_TARGET_MISMATCH", file=sys.stderr)
        return EXIT_FAIL
    previous = (resume or {}).get("verified_content", {})
    previous_snapshots = (resume or {}).get("verified_snapshots", {})
    verified = {}
    snapshots = {}
    final_checks = {}
    payload = {"command": "verify", "window": window, "datasets": {},
               "verified_content": verified, "verified_snapshots": snapshots,
               "exit_code": EXIT_PARTIAL}
    try:
        store = _open_store()
        lower = start - timedelta(seconds=args.warmup_seconds)
        final_date = end if end.time() == datetime.min.time() else end + timedelta(days=1)
        dates = _window_dates(_date_of(lower), _date_of(final_date))
        checked_new = {dataset: 0 for dataset in DATASETS}
        incomplete = False
        conflicts = False
        reviewer = HistoryRunner(store, store.db, budget=budget)
        for utc_date in dates:
            begin, stop = day_bounds_us(utc_date)
            for dataset in DATASETS:
                key = dataset + "/" + utc_date
                if budget.exhausted():
                    incomplete = True
                    break
                if key not in previous and checked_new[dataset] >= budget.max_days_per_source:
                    incomplete = True
                    continue
                is_price = dataset == DATASET_KLINES
                query = ({"source": "binance-vision", "market_type": "spot",
                          "symbol": "BTCUSDT", "interval": "1s"} if is_price else
                         {"source": "predict.fun", "series_slug": "btc-updown-5m"})
                time_field = "open_time_us" if is_price else "starts_at_us"
                query[time_field] = {"$gte": begin, "$lt": stop}
                collection = KLINES_COLLECTION if is_price else ROUNDS_COLLECTION
                with timeout(10):
                    rows = list(store.db[collection].find(query, {"_id": 0})
                                .max_time_ms(10000).batch_size(5000))
                    day = store.get_day(dataset, utc_date)
                digest = _digest_of([], rows)
                snapshot = _verification_snapshot(rows, day)
                if key in previous and (previous[key] != digest
                                        or previous_snapshots.get(key) != snapshot):
                    raise ValueError("RESUME_CONTENT_CHANGED")
                if any(row.get("schema_version") != 1 for row in rows):
                    raise ValueError("UNKNOWN_SCHEMA")
                if not is_price and (len({row.get("round_id") for row in rows}) != len(rows)
                        or any(not isinstance(row.get("round_id"), str)
                               or not row["round_id"].isascii() or not row["round_id"].isdecimal()
                               or row.get("ends_at_us", 0) - row.get("starts_at_us", 0) != 300000000
                               for row in rows)):
                    raise ValueError("NATURAL_KEY_OR_TIME_INVALID")
                final_checks[key] = (collection, query, dataset, utc_date, snapshot)
                raw_refs = {row.get("raw_ref") for row in rows}
                raw_ok = bool(rows) and all(
                    isinstance(ref, str) and _verify_raw(ref) for ref in raw_refs
                )
                for row in rows:
                    ref = row.get("raw_ref")
                    if not isinstance(ref, str) or Path(ref).stem != row.get("raw_sha256"):
                        raise ValueError("RAW_REFERENCE_MISMATCH")
                    evidence = row.get("resolution_evidence") or {}
                    if evidence.get("raw_ref") and not _verify_raw(evidence["raw_ref"]):
                        raise ValueError("SETTLEMENT_RAW_MISMATCH")
                if is_price:
                    raw_ok = raw_ok and bool(day) and _verify_archive_manifest(
                        day.get("raw_manifest_ref"), utc_date, rows=rows
                    )
                else:
                    raw_ok = raw_ok and bool(day) and asyncio.run(_verify_predict_manifest(
                        day.get("raw_manifest_ref"), utc_date, rows,
                    ))
                unique = {row[time_field] for row in rows}
                if is_price:
                    counts = {"valid_unique_seconds": len(unique),
                              "missing_seconds": 86400 - len(unique)}
                    coverage_ok = len(rows) == len(unique) == 86400 and all(
                        (value - begin) % 1000000 == 0 for value in unique
                    )
                else:
                    counts = reviewer._review_round_day(utc_date, begin, stop, docs=rows)
                    coverage_ok = (counts["coverage_ok"] and counts["resolved"] == len(rows))
                    conflicts = conflicts or any(counts[key] for key in (
                        "conflict", "duplicate_natural_keys", "invalid_identity", "overlaps",
                        "off_grid", "invalid_settlement",
                    ))
                conflicts = conflicts or bool(day and day.get("state") == "conflict")
                complete = bool(day and day.get("state") == "complete" and raw_ok
                                and coverage_ok and day.get("content_sha256") == digest)
                payload["datasets"][key] = {
                    "rows": len(rows), "actual_content_sha256": digest,
                    "raw_bytes_verified": raw_ok, "coverage_ok": coverage_ok,
                    "counts": counts, "complete": complete,
                }
                if key not in previous:
                    checked_new[dataset] += 1
                if complete:
                    verified[key] = digest
                    snapshots[key] = snapshot
                else:
                    incomplete = True
        for key in list(verified):
            if budget.remaining() <= 0:
                incomplete = True
                verified.pop(key)
                snapshots.pop(key)
                payload["datasets"][key]["complete"] = False
                continue
            collection, query, dataset, utc_date, original = final_checks[key]
            with timeout(10):
                final_rows = list(store.db[collection].find(query, {"_id": 0})
                                  .max_time_ms(10000).batch_size(5000))
                final_day = store.get_day(dataset, utc_date)
            if _verification_snapshot(final_rows, final_day) != original:
                raise ValueError("DATASET_CHANGED_DURING_VERIFY")
            if final_day is None:
                raise ValueError("DATASET_CHANGED_DURING_VERIFY")
            final_raw_ok = (_verify_archive_manifest(final_day.get("raw_manifest_ref"), utc_date,
                                                     rows=final_rows)
                            if dataset == DATASET_KLINES else asyncio.run(_verify_predict_manifest(
                                final_day.get("raw_manifest_ref"), utc_date, final_rows,
                            )))
            if not final_raw_ok:
                raise ValueError("RAW_CHANGED_DURING_VERIFY")
        payload["exit_code"] = (EXIT_FAIL if conflicts else
                                EXIT_PARTIAL if incomplete else EXIT_OK)
    except Exception as exc:
        verified.clear()
        snapshots.clear()
        payload["exit_code"] = EXIT_FAIL
        payload["error_code"] = getattr(exc, "code", type(exc).__name__)
        print("[history] EXIT_FAIL: verification failed", file=sys.stderr)
    payload["resume_sha256"] = _resume_digest(payload)
    _write_summary(args.report_dir, payload)
    return payload["exit_code"]


def _verify_raw(raw_ref: str, *, archive: RawArchive | None = None) -> bool:
    """Verify exact bytes only inside the configured archive and its canonical layout."""
    import hashlib

    try:
        path = (archive or RawArchive()).resolve(raw_ref)
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == path.stem
    except (OSError, HistoryHTTPError, ValueError):
        return False


def _verify_archive_manifest(raw_ref: str | None, utc_date: str, *,
                             archive: RawArchive | None = None,
                             rows: list[dict[str, Any]] | None = None) -> bool:
    """Validate exact manifest/ZIP/official CHECKSUM bytes without HTTP or writes."""
    import zipfile

    archive = archive or RawArchive()
    if not raw_ref or not _verify_raw(raw_ref, archive=archive):
        return False
    manifest = json.loads(archive.read_bytes(raw_ref).decode("utf-8"))
    if manifest.get("utc_date") != utc_date:
        return False
    for ref_key, sha_key in (("raw_ref", "raw_sha256"),
                             ("checksum_ref", "checksum_sha256")):
        ref = manifest.get(ref_key)
        if not ref or not _verify_raw(ref, archive=archive) or Path(ref).stem != manifest.get(sha_key):
            return False
    checksum = archive.read_bytes(manifest["checksum_ref"]).decode("utf-8").split()
    expected_name = f"BTCUSDT-1s-{utc_date}.zip"
    if (len(checksum) != 2 or checksum[0] != manifest["raw_sha256"]
            or checksum[1].lstrip("*") != expected_name):
        return False
    with zipfile.ZipFile(archive.resolve(manifest["raw_ref"])) as zipped:
        from .btc5m_history.common import MAX_ZIP_UNCOMPRESSED_BYTES

        if (zipped.namelist() != [expected_name[:-4] + ".csv"]
                or zipped.infolist()[0].file_size > MAX_ZIP_UNCOMPRESSED_BYTES
                or zipped.testzip() is not None):
            return False
        if rows is None:
            return True
        import csv
        import io
        from .btc5m_history.transforms import BinanceKlineTransformer
        from .btc5m_history.loader import _record_hash

        actual = {row["open_time_us"]: _record_hash(row, DATASETS[1]) for row in rows}
        if len(actual) != len(rows):
            return False
        transformer = BinanceKlineTransformer()
        begin, stop = day_bounds_us(utc_date)
        previous = None
        row_number = 0
        with zipped.open(zipped.namelist()[0]) as member:
            for cols in csv.reader(io.TextIOWrapper(member, encoding="utf-8")):
                if not cols:
                    continue
                row_number += 1
                record = transformer.transform_one({"cols": cols, "row_number": row_number})
                opened = record["open_time_us"]
                if (not begin <= opened < stop or (previous is not None and opened <= previous)
                        or actual.pop(opened, None) != _record_hash(record, DATASETS[1])):
                    return False
                previous = opened
        return not actual


async def _verify_predict_manifest(raw_ref: str | None, utc_date: str,
                                   rows: list[dict[str, Any]], *,
                                   archive: RawArchive | None = None) -> bool:
    """Replay the entire fixed-bound page chain and compare official business facts."""
    from .btc5m_history.runner import read_round_page, scan_rounds, _select_day_records, reconcile_round_raw
    from .btc5m_history.extractors import ExtractResult
    from .btc5m_history.transforms import PredictRoundTransformer
    from .btc5m_history.loader import _record_hash

    archive = archive or RawArchive()
    if not raw_ref or not _verify_raw(raw_ref, archive=archive):
        return False
    manifest = json.loads(archive.read_bytes(raw_ref))
    begin, stop = day_bounds_us(utc_date)
    pages = manifest.get("pages", [])
    if (manifest.get("kind") != "predict-scan" or not manifest.get("closed") or not pages
            or manifest.get("lower_us", begin + 1) > begin
            or manifest.get("upper_us", stop - 1) < stop):
        return False
    expected = {}
    enumerated = {}
    by_id = {row["round_id"]: row for row in rows}
    transformer = PredictRoundTransformer()

    class Replay:
        index = 0

        async def extract_page(self, source, **kwargs):
            page = pages[self.index]
            self.index += 1
            if source.after != page["after"]:
                raise ValueError("PAGE_CHAIN_BROKEN")
            records = read_round_page(archive, page)
            records = [{key: value for key, value in record.items()
                        if key not in {"_raw_ref", "_raw_sha256"}} for record in records]
            return ExtractResult(records=records, next_after=page["cursor"],
                                 raw_ref=page["raw_ref"], raw_sha256=page["raw_sha256"])

    async def collect(records, page, state):
        for record in _select_day_records(records, begin, stop):
            transformed = transformer.transform_one(record)
            key = transformed["round_id"]
            digest = _record_hash(transformed, DATASETS[0])
            if key in enumerated and enumerated[key] != digest:
                raise ValueError("RAW_ROUND_CONFLICT")
            enumerated[key] = digest
            latest = reconcile_round_raw(
                dict(record, _raw_ref=page["raw_ref"], _raw_sha256=page["raw_sha256"]),
                by_id.get(key), archive,
            )
            expected[key] = _record_hash(transformer.transform_one(latest), DATASETS[0])

    replay = Replay()
    scan = await scan_rounds(replay, budget=Budget(), lower_us=manifest["lower_us"],
                             upper_us=manifest["upper_us"], max_pages=len(pages),
                             on_page=collect, collect_records=False)
    actual = {row["round_id"]: _record_hash(row, DATASETS[0]) for row in rows}
    if len(actual) != len(rows) or actual != expected:
        raise ValueError("RAW_SEMANTIC_READBACK_MISMATCH")
    return scan.closed and scan.error_code is None and replay.index == len(pages)


def _load_resume(report_path: str | None) -> dict[str, Any] | None:
    """加载前次本地 verify 摘要（只读，不写库）。"""
    if not report_path:
        return None
    import tempfile

    path = Path(report_path).resolve()
    roots = (Path(tempfile.gettempdir()).resolve(),
             Path("data/reports/2026-11-11-yquant-data-history/evidence").resolve())
    if (not any(path.is_relative_to(root) for root in roots)
            or path.name != "summary.json" or not path.is_file()):
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "DEFAULT_END_UTC",
    "DEFAULT_START_UTC",
    "build_parser",
    "main",
]
