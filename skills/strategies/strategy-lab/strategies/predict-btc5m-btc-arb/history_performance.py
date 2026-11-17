"""BTC5m 研究性能编排：结果复用、多实例共享输入、有界预取与可复现对拍。

本模块是 `history_research.py` 的旁路性能入口，只在研究层工作：

* `rescore` 复用既有 `samples.csv` 本地重评分，不再启动 Rust 或 Mongo；
* `window` 用既有 facade / day_events / Rust 核心跑显式窗口；
* `candidates` 把同一有序事件流广播给少量**同配置**独立 Rust 核心，并与
  「逐实例独立重复读取」对拍。

边界（来自主控事实校正）：`replay/types.rs` 的配置校验锁定原参数，
`vol_floor` 只能是 0.00005。本模块因此只做**多实例控制实验**（相同冻结
配置的多个独立连续核心），不交付不同 floor 的模型能力，不做模型择优，
不产生 PnL / Sharpe / MDD，不写生产库、调度或交易配置。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import resource
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(LAB))

from history_metrics import (CALIBRATION_COLUMNS, COMPARISON_COLUMNS, DAILY_COLUMNS,
                             aggregate)  # noqa: E402
from history_research import (BINARY, END, START, day_events, write_csv,  # noqa: E402
                              write_json)
from skills.data.unified_data.history_types import HistoryRequest, parse_utc, to_us  # noqa: E402

#: 本主题唯一允许的证据根。
PERF_ROOT = ROOT / "data/reports/2026-11-17-btc5m-research-performance"
PERF_EVIDENCE = PERF_ROOT / "evidence/developer"
#: 已签收的 94 日历史研究证据目录（只读复用）。
LEGACY_FULL = (ROOT / "data/reports/2026-11-12-btc5m-native-history-research"
               "/evidence/research/full-run3646")
#: Rust 配置校验唯一接受的波动率下限（replay/types.rs:97-102）。
FROZEN_VOL_FLOOR = 0.00005
#: 预取深度上限：最多并行的读取任务 / 有界待消费结果数。
MAX_PREFETCH_DEPTH = 2
#: 同时运行的同配置独立核心上限（少量、有界）。
MAX_INSTANCES = 3
SAMPLE_INT_COLUMNS = ("offset", "at_ms", "starts_at_ms", "ends_at_ms", "spot_at_ms",
                      "samples", "label_available_at_us")
SAMPLE_FLOAT_COLUMNS = ("secs_left", "strike", "spot", "sigma", "p_up")


# --------------------------------------------------------------------------- helpers


def sha256_file(path: Path) -> str:
    """Hash a file with bounded reads."""
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def naive_utc(value: datetime) -> datetime:
    """Return the naive-UTC projection used by the facade contract."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def aware_utc(value: datetime) -> datetime:
    """Return the tz-aware UTC projection the facade request contract requires."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def window_days(start: datetime, end: datetime) -> list[datetime]:
    """Return the UTC day starts covering [start, end)."""
    days, day = [], start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        days.append(day)
        day += timedelta(days=1)
    return days


def check_deadline(deadline: float) -> None:
    """Enforce the run-wide wall-clock budget."""
    if time.monotonic() >= deadline:
        raise TimeoutError("performance budget exceeded")


def _coverage_payload(coverage: Any) -> dict[str, Any]:
    """Return the facade coverage as a plain mapping."""
    if coverage is None:
        return {}
    if is_dataclass(coverage) and not isinstance(coverage, type):
        return asdict(coverage)
    if isinstance(coverage, Mapping):
        return dict(coverage)
    return {}


def read_samples(path: Path) -> list[dict[str, Any]]:
    """Read a samples.csv back into typed rows; 'N/A' becomes None."""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for record in csv.DictReader(source):
            row: dict[str, Any] = dict(record)
            for column in SAMPLE_INT_COLUMNS:
                row[column] = None if record[column] == "N/A" else int(record[column])
            for column in SAMPLE_FLOAT_COLUMNS:
                row[column] = None if record[column] == "N/A" else float(record[column])
            row["label"] = None if record["label"] == "N/A" else record["label"]
            rows.append(row)
    return rows


def read_numeric_csv(path: Path) -> list[dict[str, Any]]:
    """Read a statistics CSV into rows where 'N/A' becomes None."""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for record in csv.DictReader(source):
            row: dict[str, Any] = {}
            for column, value in record.items():
                if value == "N/A":
                    row[column] = None
                elif column in ("partition", "day"):
                    row[column] = value
                elif column in ("offset", "bin"):
                    row[column] = int(value)
                else:
                    row[column] = float(value)
            rows.append(row)
    return rows


def compare_tables(rebuilt: list[dict[str, Any]], original: list[dict[str, Any]],
                   key: tuple[str, ...]) -> dict[str, Any]:
    """Compare two statistics tables column by column; report the largest drift."""
    if len(rebuilt) != len(original):
        return {"identical": False, "reason": "row count drift",
                "rebuilt_rows": len(rebuilt), "original_rows": len(original)}
    drift = 0.0
    for left, right in zip(rebuilt, original):
        if tuple(left[name] for name in key) != tuple(right[name] for name in key):
            return {"identical": False,
                    "reason": f"key drift {tuple(left[n] for n in key)} != "
                              f"{tuple(right[n] for n in key)}"}
        for column in right:
            if column not in left:
                return {"identical": False, "reason": f"missing column {column}"}
            a, b = left[column], right[column]
            if isinstance(a, float) or isinstance(b, float):
                if a is None or b is None:
                    if a is not b:
                        return {"identical": False, "reason": f"null drift {column}"}
                    continue
                drift = max(drift, abs(a - b))
            elif a != b:
                return {"identical": False, "reason": f"value drift {column}: {a} != {b}"}
    return {"identical": drift == 0.0, "max_abs_drift": drift}


# --------------------------------------------------------------------- facade plumbing


class CountingBundle:
    """Count facade rows per stream without changing the facade contract."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.counts = {"features": 0, "metadata": 0, "labels": 0, "verify": 0}

    def _wrap(self, name: str, iterator: Iterator[Any]) -> Iterator[Any]:
        for row in iterator:
            self.counts[name] += 1
            yield row

    def iter_features(self) -> Iterator[Any]:
        return self._wrap("features", self._inner.iter_features())

    def iter_metadata(self) -> Iterator[Any]:
        return self._wrap("metadata", self._inner.iter_metadata())

    def iter_labels(self) -> Iterator[Any]:
        return self._wrap("labels", self._inner.iter_labels())

    def verify_consumed(self) -> str:
        self.counts["verify"] += 1
        return self._inner.verify_consumed()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _OpenTask:
    """One prefetched day bundle; the worker thread is a daemon and may be unreclaimable."""

    def __init__(self, day: datetime, opener: Any) -> None:
        self.day = day
        self._opener = opener
        self.bundle: Any = None
        self.error: BaseException | None = None
        self.finished = threading.Event()
        self.started = False
        self.thread = threading.Thread(target=self._run, name=f"btc5m-prefetch-{day.date()}",
                                       daemon=True)

    def _run(self) -> None:
        self.started = True
        try:
            self.bundle = self._opener(self.day)
        except BaseException as error:  # noqa: BLE001 — propagated to the consumer
            self.error = error
        finally:
            self.finished.set()

    def start(self) -> None:
        self.thread.start()

    def cancel(self) -> bool:
        """Return True when the task never started; a running read cannot be killed."""
        return not self.started


class BoundedPrefetcher:
    """Prefetch at most `depth` day bundles; pending results stay bounded."""

    def __init__(self, client: Any, as_of: datetime, depth: int = MAX_PREFETCH_DEPTH) -> None:
        self._client = client
        self._as_of = as_of
        self._depth = depth
        self._tasks: "OrderedDict[datetime, _OpenTask]" = OrderedDict()
        self.opened = 0
        self.cancelled = 0
        self.reclaimed = 0
        self.unreclaimed = 0

    def _open(self, day: datetime) -> Any:
        from history_input import iter_history_input

        request = HistoryRequest(start_utc=aware_utc(day),
                                 end_utc=aware_utc(day + timedelta(days=1)),
                                 as_of_utc=self._as_of,
                                 availability_mode="event-time-proxy")
        bundle = iter_history_input(self._client, request)
        self.opened += 1
        return bundle

    def submit(self, day: datetime) -> None:
        if day in self._tasks:
            return
        task = _OpenTask(day, self._open)
        self._tasks[day] = task
        task.start()

    def take(self, day: datetime, timeout: float) -> Any:
        """Wait for one prefetched bundle; the task stays tracked until it arrives.

        A timeout must not lose the running task: it stays in the registry so
        `close` can still report and join it.
        """
        task = self._tasks.get(day)
        if task is None:
            raise KeyError(f"no prefetch task for {day}")
        if not task.finished.wait(timeout):
            raise TimeoutError("prefetched bundle did not arrive in time")
        self._tasks.pop(day)
        if task.error is not None:
            raise task.error
        return task.bundle

    def close(self, join_timeout: float = 30.0) -> dict[str, Any]:
        """Cancel queued work and join the running ones; report the truth.

        A running read cannot be killed, so it is joined with a bounded wait and
        reported as `unreclaimed` when it is still alive afterwards.
        """
        cancelled, reclaimed, unreclaimed = 0, 0, 0
        for task in list(self._tasks.values()):
            if task.cancel():
                cancelled += 1
                continue
            task.finished.wait(join_timeout)
            if task.thread.is_alive():
                unreclaimed += 1
            else:
                reclaimed += 1
        self._tasks.clear()
        self.cancelled += cancelled
        self.unreclaimed += unreclaimed
        self.reclaimed += reclaimed
        return {"cancelled": self.cancelled, "reclaimed": self.reclaimed,
                "unreclaimed": self.unreclaimed}


# ------------------------------------------------------------------------ instances


@dataclass
class Instance:
    """One research instance: its own config copy, output directory and Rust state."""

    name: str
    vol_floor: float = FROZEN_VOL_FLOOR
    status: str = "PENDING"
    native_exit: int | None = None
    error: str | None = None
    values_sha256: str | None = None
    event_sha256: str | None = None
    events: int = 0
    wall_seconds: float = 0.0
    child_cpu_seconds: float = 0.0
    child_max_rss_kib: int = 0
    summary: dict[str, Any] = field(default_factory=dict)


def instance_config(base: dict[str, Any]) -> dict[str, Any]:
    """Return a research parameter copy; the frozen parameters are unchanged."""
    return dict(base)


# --------------------------------------------------------------------------- runners


def _start_core(candidate: Instance, instance_dir: Path, start_ms: int, end_ms: int,
                flat: bool = False) -> dict[str, Any]:
    """Start one Rust history core on its own stdin/stdout pipes."""
    if not flat:
        instance_dir.mkdir(parents=True, exist_ok=False)
    config_path = instance_dir / "config.json"
    write_json(config_path, instance_config(json.loads((LAB / "config.json").read_text())))
    command = [str(BINARY), "--config", str(config_path), "--input", "-",
               "--output", str(instance_dir / "values.jsonl"),
               "--summary", str(instance_dir / "rust-summary.json"),
               "--from-ms", str(start_ms), "--to-ms", str(end_ms)]
    write_json(instance_dir / "command.json", command)
    handle = (instance_dir / "rust-stderr.log").open("xb")
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=handle)
    return dict(instance=candidate, dir=instance_dir, command=command, process=process,
                stderr=handle, error=None)


def _finish_core(state: dict[str, Any], event_sha256: str, events: int) -> None:
    """Close stdin, reap the child and record its native exit and resource use."""
    candidate: Instance = state["instance"]
    process = state["process"]
    try:
        if process.stdin is not None:
            process.stdin.close()
    except (BrokenPipeError, ValueError):
        pass
    native_exit, usage = None, None
    try:
        _, status, usage = os.wait4(process.pid, 0)
        native_exit = os.waitstatus_to_exitcode(status)
    except ChildProcessError:
        native_exit = process.returncode
    except Exception:  # noqa: BLE001 — the native exit stays unknown
        native_exit = None
    process.returncode = native_exit
    state["stderr"].close()
    candidate.native_exit = native_exit
    candidate.child_cpu_seconds = (usage.ru_utime + usage.ru_stime) if usage else 0.0
    candidate.child_max_rss_kib = usage.ru_maxrss if usage else 0
    candidate.event_sha256 = event_sha256
    candidate.events = events
    values = state["dir"] / "values.jsonl"
    candidate.values_sha256 = sha256_file(values) if values.exists() else None
    summary_path = state["dir"] / "rust-summary.json"
    if summary_path.exists():
        candidate.summary = json.loads(summary_path.read_text())
    if candidate.status != "FAILED":
        candidate.status = "EXECUTED" if native_exit == 0 else "REFUSED"
        if native_exit == 64:
            candidate.error = "Rust refused the frozen configuration"


def run_instances(client: Any, *, start: datetime, end: datetime, as_of: datetime,
                  instances: list[Instance], output_dir: Path, budget_seconds: float,
                  prefetch: bool, label: str, strategy: str,
                  flat: bool = False) -> dict[str, Any]:
    """Run one explicit window over one or more independent Rust cores.

    The event stream is encoded once per day and broadcast to every core, so
    all cores see byte-identical input in identical order.
    """
    output_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started + budget_seconds
    start_ms = to_us(start.replace(tzinfo=None)) // 1000
    end_ms = to_us(end.replace(tzinfo=None)) // 1000
    contexts: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    stream_hash = hashlib.sha256()
    seq = 0
    prepare_seconds = 0.0
    verify_seconds = 0.0
    row_counts = {"features": 0, "metadata": 0, "labels": 0}
    bundle_opens = 0
    day_digests: dict[str, str] = {}
    prefetcher: BoundedPrefetcher | None = None
    days = window_days(start, end)
    if prefetch:
        prefetcher = BoundedPrefetcher(client, as_of)
    try:
        for candidate in instances:
            instance_dir = output_dir / candidate.name if not flat else output_dir
            states.append(_start_core(candidate, instance_dir, start_ms, end_ms, flat))
        for index, day in enumerate(days):
            check_deadline(deadline)
            day_started = time.monotonic()
            if prefetcher is not None:
                for ahead in days[index:index + MAX_PREFETCH_DEPTH]:
                    prefetcher.submit(ahead)
                bundle = prefetcher.take(day, max(0.01, deadline - time.monotonic()))
            else:
                from history_input import iter_history_input

                request = HistoryRequest(start_utc=aware_utc(day),
                                         end_utc=aware_utc(day + timedelta(days=1)),
                                         as_of_utc=as_of,
                                         availability_mode="event-time-proxy")
                bundle = iter_history_input(client, request)
                bundle_opens += 1
            counted = CountingBundle(bundle)
            # The facade's own day_events helper compares against an aware SPLIT.
            day_start = aware_utc(max(start, day))
            day_end = aware_utc(min(end, day + timedelta(days=1)))
            day_events_count = 0
            for event in day_events(counted, day_start, day_end, contexts):
                at_ms = event["at_ms"]
                # The Rust core accepts [from_ms, to_ms] inclusive; keep the same bound.
                if at_ms < start_ms or at_ms > end_ms:
                    continue
                event["schema_version"] = "btc-arb-history/1"
                event["seq"] = seq
                encoded = (json.dumps(event, separators=(",", ":"),
                                      allow_nan=False) + "\n").encode()
                for state in states:
                    if state["error"] is not None:
                        continue
                    try:
                        state["process"].stdin.write(encoded)
                    except (BrokenPipeError, ValueError) as error:
                        state["error"] = f"{type(error).__name__}: candidate stream closed"
                        state["instance"].status = "FAILED"
                stream_hash.update(encoded)
                seq += 1
                day_events_count += 1
            prepare_seconds += time.monotonic() - day_started
            check_deadline(deadline)
            verify_started = time.monotonic()
            content = counted.verify_consumed()
            verify_seconds += time.monotonic() - verify_started
            for name in row_counts:
                row_counts[name] += counted.counts[name]
            day_digests[day.date().isoformat()] = content
            window = getattr(counted, "_window", None)
            coverage = getattr(window, "coverage", None)
            write_json(output_dir / f"source-{day.date().isoformat()}.json",
                       dict(day=day.date().isoformat(), verified=counted.counts["verify"] == 1,
                            content_sha256=content, events=day_events_count,
                            row_counts=dict(counted.counts),
                            coverage=_coverage_payload(coverage),
                            missing=list(getattr(window, "missing", [])),
                            pending=list(getattr(window, "pending", [])),
                            conflicts=list(getattr(window, "conflicts", [])),
                            content_manifest=getattr(window, "content_manifest", {}),
                            provenance_manifest=getattr(window, "provenance_manifest", {})))
        check_deadline(deadline)
        for state in states:
            _finish_core(state, stream_hash.hexdigest(), seq)
        if prefetcher is not None:
            prefetcher.close()
        return dict(
            label=label, strategy=strategy, prefetch=prefetch,
            start=start.isoformat(), end=end.isoformat(), as_of=as_of.isoformat(),
            events=seq, event_sha256=stream_hash.hexdigest(), contexts=len(contexts),
            bundle_opens=bundle_opens, prefetch_opened=(prefetcher.opened if prefetcher else 0),
            prefetch_cancelled=(prefetcher.cancelled if prefetcher else 0),
            prefetch_unreclaimed=(prefetcher.unreclaimed if prefetcher else 0),
            prepare_seconds=prepare_seconds, verify_seconds=verify_seconds,
            row_counts=row_counts, day_content_sha256=day_digests,
            wall_seconds=time.monotonic() - started,
            parent_max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            instances=[dict(name=item.name, vol_floor=item.vol_floor, status=item.status,
                            native_exit=item.native_exit, error=item.error,
                            values_sha256=item.values_sha256,
                            event_sha256=item.event_sha256, events=item.events,
                            child_cpu_seconds=item.child_cpu_seconds,
                            child_max_rss_kib=item.child_max_rss_kib, summary=item.summary)
                       for item in instances])
    finally:
        if prefetcher is not None:
            prefetcher.close()
        for state in states:
            process = state["process"]
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def run_independent(client: Any, *, start: datetime, end: datetime, as_of: datetime,
                    instances: list[Instance], output_dir: Path, budget_seconds: float,
                    label: str) -> dict[str, Any]:
    """Run each instance with its own repeated facade read (the control arm)."""
    output_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    parts = []
    for candidate in instances:
        part = run_instances(client, start=start, end=end, as_of=as_of,
                             instances=[candidate], output_dir=output_dir / candidate.name,
                             budget_seconds=max(1.0, budget_seconds - (time.monotonic() - started)),
                             prefetch=False, label=candidate.name, strategy="independent",
                             flat=True)
        parts.append(part)
    merged = dict(label=label, strategy="independent", prefetch=False,
                  start=start.isoformat(), end=end.isoformat(), as_of=as_of.isoformat(),
                  events=parts[0]["events"], event_sha256=parts[0]["event_sha256"],
                  contexts=parts[0]["contexts"],
                  bundle_opens=sum(part["bundle_opens"] for part in parts),
                  prefetch_opened=0, prefetch_cancelled=0, prefetch_unreclaimed=0,
                  prepare_seconds=sum(part["prepare_seconds"] for part in parts),
                  verify_seconds=sum(part["verify_seconds"] for part in parts),
                  row_counts=parts[0]["row_counts"],
                  day_content_sha256=parts[0]["day_content_sha256"],
                  wall_seconds=time.monotonic() - started,
                  parent_max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  instances=[item for part in parts for item in part["instances"]])
    write_json(output_dir / "independent.json", merged)
    return merged


# ------------------------------------------------------------------------- rescore


def rescore(source_dir: Path, evidence_dir: Path,
            expect_samples_sha256: str | None) -> dict[str, Any]:
    """Rebuild the archived statistics from the archived samples; no Rust, no Mongo."""
    evidence_dir.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    samples_path = source_dir / "samples.csv"
    samples_sha = sha256_file(samples_path)
    if expect_samples_sha256 and expect_samples_sha256 != samples_sha:
        raise ValueError("samples hash mismatch: refusing to rescore")
    coverage = json.loads((source_dir / "coverage.json").read_text())
    params = json.loads((source_dir / "params.json").read_text())
    identities = json.loads((source_dir / "identities.json").read_text())
    manifests_path = source_dir / "source-manifests.json"
    manifests = json.loads(manifests_path.read_text())
    prepare_started = time.monotonic()
    rows = read_samples(samples_path)
    prepare_seconds = time.monotonic() - prepare_started
    if len(rows) != coverage["actual_positions"]:
        raise ValueError("samples row count drift against archived coverage")
    valued = sum(row["p_up"] is not None for row in rows)
    if valued != coverage["valued"]:
        raise ValueError("valued count drift against archived coverage")
    start = naive_utc(parse_utc(params["start"]))
    end = naive_utc(parse_utc(params["end"]))
    split = naive_utc(parse_utc(params["split"]))
    dates = {partition: [day.date().isoformat() for day in window_days(start, end)
                          if (day < split) == (partition == "IS")]
             for partition in ("IS", "OOS")}
    rescore_started = time.monotonic()
    comparison, calibration, daily, monthly = aggregate(rows, dates)
    rescore_seconds = time.monotonic() - rescore_started
    checks = {}
    for name, rebuilt, original, key in (
        ("comparison", comparison, read_numeric_csv(source_dir / "comparison.csv"),
         ("partition", "offset")),
        ("calibration", calibration, read_numeric_csv(source_dir / "calibration.csv"),
         ("partition", "offset", "bin")),
        ("daily", daily, read_numeric_csv(source_dir / "daily.csv"),
         ("partition", "day", "offset")),
        ("monthly", monthly, read_numeric_csv(source_dir / "monthly.csv"),
         ("partition", "day", "offset")),
    ):
        checks[name] = compare_tables(rebuilt, original, key)
    identity = dict(
        samples_sha256=samples_sha, samples_bytes=samples_path.stat().st_size,
        samples_rows=len(rows), valued_rows=valued,
        source_dir=str(source_dir.relative_to(ROOT)),
        source_manifests_sha256=sha256_file(manifests_path),
        source_manifest_count=len(manifests),
        capture_time_identities=identities,
        archived_params=params, archived_coverage=coverage,
        validated_input="archived samples.csv plus capture-time source/binary/config identities",
        current_raw_database_state="NOT_RECHECKED_BY_THIS_PATH (no Mongo read in rescore)",
    )
    write_json(evidence_dir / "identity.json", identity)
    write_csv(evidence_dir / "comparison.csv", COMPARISON_COLUMNS, comparison)
    write_csv(evidence_dir / "calibration.csv", CALIBRATION_COLUMNS, calibration)
    write_csv(evidence_dir / "daily.csv", DAILY_COLUMNS, daily)
    write_csv(evidence_dir / "monthly.csv", DAILY_COLUMNS, monthly)
    result = dict(mode="rescore", source_dir=str(source_dir.relative_to(ROOT)),
                  samples_sha256=samples_sha, samples_rows=len(rows),
                  prepare_seconds=prepare_seconds, rescore_seconds=rescore_seconds,
                  verify_seconds=0.0, model_seconds=0.0,
                  wall_seconds=time.monotonic() - started,
                  parent_max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  child_max_rss_kib=0, child_cpu_seconds=0.0,
                  db_calls=0, core_calls=0,
                  checks=checks, all_identical=all(item["identical"] for item in checks.values()))
    write_json(evidence_dir / "rescore.json", result)
    if not result["all_identical"]:
        raise ValueError("rescored statistics drifted from the archived statistics")
    return result


# ------------------------------------------------------------------------------ CLI


def _require_subtree(path: Path) -> Path:
    """Accept only this theme's evidence subtree (developer or validate)."""
    resolved = path.resolve()
    allowed = (PERF_ROOT / "evidence").resolve()
    if not resolved.is_relative_to(allowed):
        raise ValueError("evidence directory outside the authorized performance subtree")
    return resolved


def _open_client() -> Any:
    from skills.data.unified_data.client import UnifiedDataClient
    from skills.data.unified_data.history_reader import Btc5mHistoryReader
    from skills.data.unified_data.storage import open_databases

    return UnifiedDataClient(history_reader=Btc5mHistoryReader(open_databases().ud))


def main(argv: list[str] | None = None) -> int:
    """Parse the narrow CLI before opening the existing read connection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("rescore", "window", "candidates"), required=True)
    parser.add_argument("--as-of", help="explicit frozen UTC as-of (not in the future)")
    parser.add_argument("--start", help="explicit window lower bound (inclusive)")
    parser.add_argument("--end", help="explicit window upper bound (exclusive)")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, help="archived research evidence to rescore")
    parser.add_argument("--expect-samples-sha256", help="external expectation for the samples hash")
    parser.add_argument("--instances", type=int, default=2,
                        help="number of identical-config independent Rust cores (1..3)")
    parser.add_argument("--strategy", choices=("serial", "prefetch", "both"), default="both",
                        help="facade read strategy; 'both' runs the serial/prefetch comparison")
    parser.add_argument("--budget-seconds", type=float, default=1800.0)
    args = parser.parse_args(argv)
    try:
        evidence = _require_subtree(args.evidence_dir)
        if evidence.exists():
            raise ValueError("evidence directory already exists")
        if args.mode == "rescore":
            source = (args.source_dir or LEGACY_FULL).resolve()
            if not source.is_dir():
                raise ValueError("source directory does not exist")
            result = rescore(source, evidence, args.expect_samples_sha256)
            print(json.dumps(result, default=str), flush=True)
            return 0
        if not (args.start and args.end and args.as_of):
            raise ValueError("window mode requires --start, --end and --as-of")
        start = naive_utc(parse_utc(args.start))
        end = naive_utc(parse_utc(args.end))
        as_of = parse_utc(args.as_of).replace(tzinfo=timezone.utc)
        if start >= end:
            raise ValueError("start must be < end")
        if as_of < end.replace(tzinfo=timezone.utc):
            raise ValueError("as-of must cover the window")
        if as_of > datetime.now(timezone.utc):
            raise ValueError("as-of must not be in the future")
        if not 1 <= args.instances <= MAX_INSTANCES:
            raise ValueError(f"--instances must be between 1 and {MAX_INSTANCES}")
        client = _open_client()
        runs = []
        if args.mode == "window":
            strategies = ("serial", "prefetch") if args.strategy == "both" else (args.strategy,)
            for strategy in strategies:
                instances = [Instance(name=f"core-{index + 1}")
                             for index in range(args.instances)]
                metrics = run_instances(client, start=start, end=end, as_of=as_of,
                                        instances=instances,
                                        output_dir=evidence / f"shared-{strategy}",
                                        budget_seconds=args.budget_seconds,
                                        prefetch=(strategy == "prefetch"),
                                        label=strategy, strategy=strategy)
                runs.append(metrics)
                print(json.dumps(metrics, default=str), flush=True)
        else:
            instances = [Instance(name=f"core-{index + 1}") for index in range(args.instances)]
            shared = run_instances(client, start=start, end=end, as_of=as_of,
                                   instances=instances, output_dir=evidence / "shared",
                                   budget_seconds=args.budget_seconds, prefetch=False,
                                   label="shared", strategy="shared")
            runs.append(shared)
            print(json.dumps(shared, default=str), flush=True)
            if args.strategy in ("prefetch", "both"):
                prefetched = run_instances(client, start=start, end=end, as_of=as_of,
                                           instances=[Instance(name=f"core-{index + 1}")
                                                      for index in range(args.instances)],
                                           output_dir=evidence / "shared-prefetch",
                                           budget_seconds=args.budget_seconds,
                                           prefetch=True, label="prefetch",
                                           strategy="prefetch")
                runs.append(prefetched)
                print(json.dumps(prefetched, default=str), flush=True)
            independent = run_independent(client, start=start, end=end, as_of=as_of,
                                          instances=[Instance(name=f"core-{index + 1}")
                                                     for index in range(args.instances)],
                                          output_dir=evidence / "independent",
                                          budget_seconds=args.budget_seconds,
                                          label="independent")
            runs.append(independent)
            print(json.dumps(independent, default=str), flush=True)
        write_json(evidence / "runs.json", runs)
        return 0
    except Exception as error:
        print(f"performance run failed: {type(error).__name__}", file=sys.stderr)
        return 5 if isinstance(error, TimeoutError) else 2


if __name__ == "__main__":
    raise SystemExit(main())
