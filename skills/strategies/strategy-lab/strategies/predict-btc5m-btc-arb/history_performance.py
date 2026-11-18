"""BTC5m 研究性能编排：结果复用、多实例共享输入、有界预取与可复现对拍。

本模块是 `history_research.py` 的旁路性能入口，只在研究层工作：

* `rescore` 复用**已签收**的 `samples.csv` 与配套身份做本地重评分；
  身份必须与固定可信清单逐文件校验，自算 hash 不构成自认证。
* `window` 用既有 facade / day_events / Rust 核心跑显式窗口；
* `candidates` 把同一有序事件流广播给少量**同配置**独立 Rust 核心，并与
  「逐实例独立重复读取」对拍；独立控制臂始终运行。

边界（来自主控事实校正）：`replay/types.rs` 的配置校验锁定原参数，
`vol_floor` 只能是 0.00005。本模块因此只做**多实例控制实验**（相同冻结
配置的多个独立连续核心），不交付不同 floor 的模型能力，不做模型择优，
不产生 PnL / Sharpe / MDD，不写生产库、调度或交易配置。

失败语义：任一实例非零退出、缺 values/summary、partial summary、写入阻塞
超时或预取未回收，都令整批失败；CLI 只在整批完整成功时返回 0。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import resource
import select
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
                             OFFSETS, aggregate)  # noqa: E402
from history_research import (BINARY, END, SAMPLE_COLUMNS, SPLIT, START, day_events,  # noqa: E402
                              merge_values, write_csv, write_json)
from skills.data.unified_data.history_types import HistoryRequest, parse_utc, to_us  # noqa: E402

#: 本主题唯一允许的证据根。
PERF_ROOT = ROOT / "data/reports/2026-11-17-btc5m-research-performance"
PERF_EVIDENCE = PERF_ROOT / "evidence/developer"
#: 本轮修复唯一允许的新证据目录。
FIX1_EVIDENCE = PERF_ROOT / "evidence/fix1"
#: 已签收的 94 日历史研究证据目录（只读复用）。
LEGACY_FULL = (ROOT / "data/reports/2026-11-12-btc5m-native-history-research"
               "/evidence/research/full-run3646")
#: Rust 配置校验唯一接受的波动率下限（replay/types.rs:97-102）。
FROZEN_VOL_FLOOR = 0.00005
#: 预取深度上限：最多并行的读取任务 / 有界待消费结果数。
MAX_PREFETCH_DEPTH = 2
#: 同时运行的同配置独立核心上限（少量、有界）。
MAX_INSTANCES = 3
#: 核心结束后的有界等待上限（秒）。
CORE_WAIT_SECONDS = 10.0
#: 核心回收：terminate 后的有界等待上限（秒）。
CORE_KILL_SECONDS = 5.0

#: 已签收归档的固定可信清单（主控原生 sha256sum 已核）。
#: 固定清单即可，不建通用信任平台；其它 source-dir 一律拒绝。
TRUSTED_ARCHIVE_SHA256 = {
    "samples.csv": "722facb5185eef2f1b192e9989c4f7a602b9b63a68bbb16af85ad747fa6d1970",
    "identities.json": "e3c6e8553e124157333b389e32669c530b39e795391180f6f309f2281d47dcb1",
    "params.json": "095f0288f29af977b5c8cce0ec4d28150a6040f90bddae6e4d2fe8a9a47b46c1",
    "coverage.json": "0f1e5212874d1348d3f2dff4a1f4614b2dd61d5c53d6c7c33da70f41d4f9d91e",
    "source-manifests.json": "bd4854c704ed0314d39cee4613e141cfe729a25f5048c3461bd4b1be2c418dfe",
}
#: 捕获时身份必须包含的键（旧 producer 的源码/二进制身份分层，不要求等于当前源码）。
REQUIRED_IDENTITY_KEYS = (
    "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/history_research.py",
    "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/history_metrics.py",
    "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/config.json",
    "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/history_input.py",
    "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits"
    "/src/bot/arbitrage.rs",
    "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits"
    "/src/bot/arbitrage/history.rs",
    "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits"
    "/src/bin/btc_arb_history.rs",
    "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits"
    "/target/debug/btc_arb_history",
)

#: The Rust summary contract (`src/bin/btc_arb_history.rs`): the exact fields
#: and types the core writes. A summary that misses a field is not a proof of
#: completion, so the fields are validated instead of trusting `complete`.
NATIVE_SUMMARY_FIELDS = ("native_exit", "spots", "values", "complete", "error")

#: Human-readable names for the cross-arm denominator comparison.
_DENOMINATOR_LABELS = {
    "samples_sha256": "samples identity",
    "samples_rows": "sample row count",
    "valued_rows": "valued row count",
    "missing_by_reason": "missing-reason denominators",
}

#: The performance test files whose inline fixtures the arms depend on.
#: Their identity belongs to the arm identity: a fixture change must be
#: visible in the start/after comparison, not only in the runner identity.
ARM_TEST_FILES = ("test_history_performance.py", "test_history_research.py",
                  "test_history_metrics.py", "test_history_input.py")

#: The installed distributions the arms really import. `bson` ships inside
#: `pymongo`, so the `pymongo` version pins both.
DEPENDENCY_DISTRIBUTIONS = ("numpy", "pandas", "pymongo")

#: The public facade files the arms read through. Every one of them belongs to
#: the arm identity, so a missing file is a refusal, not a smaller identity.
FACADE_FILES = ("client.py", "history_reader.py", "history_types.py", "storage.py")


SAMPLE_INT_COLUMNS = ("offset", "at_ms", "starts_at_ms", "ends_at_ms", "spot_at_ms",
                      "samples", "label_available_at_us")
SAMPLE_FLOAT_COLUMNS = ("secs_left", "strike", "spot", "sigma", "p_up")


# --------------------------------------------------------------------------- helpers


class CallCounters:
    """Observed entry counters for the database and the Rust core.

    The counters are incremented inside the only functions that can reach
    Mongo or the native core, so a zero count is an observation rather than a
    hard-coded constant.
    """

    def __init__(self) -> None:
        self.db_calls = 0
        self.core_calls = 0

    def reset(self) -> None:
        self.db_calls = 0
        self.core_calls = 0


COUNTERS = CallCounters()


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


def read_sample_csv(path: Path) -> list[dict[str, str]]:
    """Read an exported samples.csv as raw string rows (column-exact compare)."""
    with path.open(encoding="utf-8") as source:
        return [dict(record) for record in csv.DictReader(source)]


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


def compare_sample_rows(left: list[dict[str, str]], right: list[dict[str, str]],
                        columns: tuple[str, ...]) -> dict[str, Any]:
    """Compare two exported sample tables cell by cell; no tolerance is allowed."""
    if len(left) != len(right):
        return {"identical": False, "reason": "sample row count drift",
                "left_rows": len(left), "right_rows": len(right)}
    for index, (a, b) in enumerate(zip(left, right)):
        for column in columns:
            if a.get(column) != b.get(column):
                return {"identical": False,
                        "reason": f"sample drift row {index} column {column}: "
                                  f"{a.get(column)} != {b.get(column)}"}
    return {"identical": True, "rows": len(left), "columns": len(columns)}


# --------------------------------------------------------------------- trusted archive


def verify_trusted_archive(source_dir: Path,
                           trusted: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Verify the signed-off archive: file hashes, identity completeness and linkage.

    Self-computed hashes never certify the archive; the expectation comes from
    the fixed trusted manifest above.
    """
    expected_hashes = dict(trusted if trusted is not None else TRUSTED_ARCHIVE_SHA256)
    if not source_dir.is_dir():
        raise ValueError("source directory does not exist")
    hashes: dict[str, str] = {}
    for name, expected in expected_hashes.items():
        path = source_dir / name
        if not path.is_file():
            raise ValueError(f"untrusted archive: missing {name}")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"untrusted archive: hash mismatch for {name}")
        hashes[name] = actual
    identities = json.loads((source_dir / "identities.json").read_text())
    if not isinstance(identities, Mapping) or not identities:
        raise ValueError("untrusted archive: empty capture-time identities")
    missing_keys = [key for key in REQUIRED_IDENTITY_KEYS if key not in identities]
    if missing_keys:
        raise ValueError(f"untrusted archive: missing capture-time identities {missing_keys}")
    for key, value in identities.items():
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"untrusted archive: malformed identity for {key}")
    params = json.loads((source_dir / "params.json").read_text())
    for field in ("mode", "start", "end", "split", "as_of", "config", "offsets", "command"):
        if field not in params:
            raise ValueError(f"untrusted archive: params missing {field}")
    config = params["config"]
    if not isinstance(config, Mapping) or config.get("schema_version") != "btc-arb-replay/1":
        raise ValueError("untrusted archive: unexpected config schema")
    if float(config.get("vol_floor", 0.0)) != FROZEN_VOL_FLOOR:
        raise ValueError("untrusted archive: config floor is not the frozen floor")
    if tuple(params["offsets"]) != tuple(OFFSETS):
        raise ValueError("untrusted archive: offset set drift")
    coverage = json.loads((source_dir / "coverage.json").read_text())
    manifests = json.loads((source_dir / "source-manifests.json").read_text())
    if not isinstance(manifests, list) or not manifests:
        raise ValueError("untrusted archive: empty source manifests")
    if coverage.get("days") != len(manifests):
        raise ValueError("untrusted archive: manifest count drift against coverage")
    manifest_days = [item.get("day") for item in manifests]
    if len(set(manifest_days)) != len(manifest_days):
        raise ValueError("untrusted archive: duplicate manifest days")
    expected_days = [day.date().isoformat()
                     for day in window_days(naive_utc(parse_utc(params["start"])),
                                            naive_utc(parse_utc(params["end"])))]
    if manifest_days != expected_days:
        raise ValueError("untrusted archive: manifest window drift")
    if coverage.get("actual_positions") != coverage.get("theoretical_positions"):
        raise ValueError("untrusted archive: coverage denominator drift")
    if coverage.get("start") != params["start"] or coverage.get("end") != params["end"]:
        raise ValueError("untrusted archive: coverage window drift against params")
    return dict(hashes=hashes, identities=dict(identities), params=params,
                coverage=coverage, manifests=manifests)


def verify_sample_identity(rows: list[dict[str, Any]], params: Mapping[str, Any]) -> None:
    """Check the identity columns of every sample row against the archived window."""
    split = aware_utc(parse_utc(params["split"]))
    for index, row in enumerate(rows):
        start_ms, end_ms = row["starts_at_ms"], row["ends_at_ms"]
        if end_ms - start_ms != 300_000:
            raise ValueError(f"sample {index}: invalid round duration")
        if not start_ms <= row["at_ms"] <= end_ms:
            raise ValueError(f"sample {index}: decision time outside the round")
        offset_seconds = (row["at_ms"] - start_ms) / 1000
        if offset_seconds != int(offset_seconds) or \
                int(offset_seconds) not in OFFSETS:
            raise ValueError(f"sample {index}: decision offset drift")
        day = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).date().isoformat()
        if row["day"] != day:
            raise ValueError(f"sample {index}: day drift")
        day_start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        partition = "IS" if day_start < split else "OOS"
        if row["partition"] != partition:
            raise ValueError(f"sample {index}: partition drift")
        if row["label"] is not None and row["label"] not in ("UP", "DOWN", "DRAW"):
            raise ValueError(f"sample {index}: unknown label")
        if row["label"] is None and row["label_available_at_us"] is not None:
            raise ValueError(f"sample {index}: label availability without a label")
        if row["label"] is not None and row["label_available_at_us"] is not None:
            if row["label_available_at_us"] < end_ms * 1000:
                raise ValueError(f"sample {index}: label available before round end")


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
    """One prefetched day bundle; a started read cannot be killed."""

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
        """Start the read; the caller must not start a cancelled task."""
        self.started = True
        self.thread.start()


class BoundedPrefetcher:
    """Prefetch at most `depth` day bundles; pending results stay bounded.

    A day is *pending* until it is launched. `close` cancels every pending day
    before it can start, so a cancelled day provably never runs; a day whose
    read already started cannot be killed and is reported as `unreclaimed`
    while it stays visible in the registry.
    """

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
        """Register a day as pending; it is launched when the consumer reaches it."""
        if day in self._tasks:
            return
        self._tasks[day] = _OpenTask(day, self._open)

    def _launch(self, day: datetime) -> _OpenTask:
        """Start the read for one day and for the days that follow it."""
        task = self._tasks[day]
        if not task.started:
            task.start()
        for ahead, pending in self._tasks.items():
            if ahead == day or pending.started:
                continue
            if sum(1 for item in self._tasks.values() if item.started) >= self._depth:
                break
            pending.start()
        return task

    def take(self, day: datetime, timeout: float) -> Any:
        """Wait for one prefetched bundle; the task stays tracked until it arrives.

        A timeout must not lose the running task: it stays in the registry so
        `close` can still report and join it.
        """
        task = self._tasks.get(day)
        if task is None:
            raise KeyError(f"no prefetch task for {day}")
        self._launch(day)
        if not task.finished.wait(timeout):
            raise TimeoutError("prefetched bundle did not arrive in time")
        self._tasks.pop(day)
        if task.error is not None:
            raise task.error
        return task.bundle

    def close(self, join_timeout: float = CORE_WAIT_SECONDS,
              deadline: float | None = None) -> dict[str, Any]:
        """Cancel pending work and join the running ones; report the truth.

        A pending day is cancelled before it starts and never runs. A running
        read cannot be killed, so it is joined with a bounded wait and reported
        as `unreclaimed`; it stays in the registry so the gap stays visible.
        The wait obeys both `join_timeout` and the remaining `deadline`, so a
        cleanup can never wait longer than the cleanup budget allows.
        """
        cancelled, reclaimed, unreclaimed = 0, 0, 0
        for day, task in list(self._tasks.items()):
            if not task.started:
                cancelled += 1
                self._tasks.pop(day, None)
                continue
            remaining = join_timeout
            if deadline is not None:
                remaining = min(remaining, max(0.0, deadline - time.monotonic()))
            task.finished.wait(remaining)
            if task.thread.is_alive():
                unreclaimed += 1
            else:
                reclaimed += 1
                self._tasks.pop(day, None)
        self.cancelled += cancelled
        self.unreclaimed += unreclaimed
        self.reclaimed += reclaimed
        return {"cancelled": self.cancelled, "reclaimed": self.reclaimed,
                "unreclaimed": self.unreclaimed,
                "still_tracked": len(self._tasks)}


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
    #: The operating-system PID of the native core, so a failed run can prove
    #: that the child really exited instead of only claiming it was reaped.
    pid: int | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    samples_sha256: str | None = None
    samples_rows: int = 0
    valued_rows: int = 0
    missing_by_reason: dict[str, int] = field(default_factory=dict)
    complete: bool = False
    terminated: bool = False
    killed: bool = False
    reaped: bool = False
    timed_out: bool = False


def instance_config(base: dict[str, Any], vol_floor: float = FROZEN_VOL_FLOOR) -> dict[str, Any]:
    """Return a research parameter copy; the frozen parameters are unchanged.

    A non-frozen floor exists only so the CLI can prove the Rust gate refuses
    it; the CLI itself exposes no floor option.
    """
    config = dict(base)
    config["vol_floor"] = vol_floor
    return config


# --------------------------------------------------------------------------- runners


def _start_core(candidate: Instance, instance_dir: Path, start_ms: int, end_ms: int,
                flat: bool = False) -> dict[str, Any]:
    """Start one Rust history core on its own stdin pipe.

    The write end is non-blocking so the run-wide deadline also bounds the
    writes; a blocked child can therefore never freeze the orchestrator.
    """
    if not flat:
        instance_dir.mkdir(parents=True, exist_ok=False)
    config_path = instance_dir / "config.json"
    write_json(config_path, instance_config(json.loads((LAB / "config.json").read_text()),
                                            candidate.vol_floor))
    command = [str(BINARY), "--config", str(config_path), "--input", "-",
               "--output", str(instance_dir / "values.jsonl"),
               "--summary", str(instance_dir / "rust-summary.json"),
               "--from-ms", str(start_ms), "--to-ms", str(end_ms)]
    write_json(instance_dir / "command.json", command)
    handle = (instance_dir / "rust-stderr.log").open("xb")
    read_fd, write_fd = os.pipe()
    os.set_blocking(write_fd, False)
    COUNTERS.core_calls += 1
    process = subprocess.Popen(command, stdin=read_fd, stdout=subprocess.DEVNULL,
                               stderr=handle)
    os.close(read_fd)
    candidate.pid = process.pid
    return dict(instance=candidate, dir=instance_dir, command=command, process=process,
                stderr=handle, write_fd=write_fd, error=None, closed=False)


def _write_event(write_fd: int, payload: bytes, deadline: float) -> None:
    """Write one encoded event with a bounded, non-blocking write."""
    view = memoryview(payload)
    while view:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("performance budget exceeded while writing to the core")
        try:
            written = os.write(write_fd, view)
        except BlockingIOError:
            written = 0
        except BrokenPipeError as error:
            raise BrokenPipeError(str(error)) from error
        if written:
            view = view[written:]
            continue
        _, writable, _ = select.select([], [write_fd], [], min(remaining, 1.0))
        if not writable:
            continue


def _wait_child(process: Any, deadline: float) -> tuple[int | None, Any, bool]:
    """Wait for one child with a hard bound; never block past `deadline`.

    `os.wait4` is only used in non-blocking mode, so a core that never exits
    cannot freeze the orchestrator. The third element reports whether the
    bound was hit before the child exited.
    """
    while True:
        try:
            pid, status, usage = os.wait4(process.pid, os.WNOHANG)
        except ChildProcessError:
            return process.returncode, None, False
        if pid != 0:
            return os.waitstatus_to_exitcode(status), usage, False
        if time.monotonic() >= deadline:
            return None, None, True
        time.sleep(0.02)


def _signal_child(process: Any, kill: bool) -> None:
    """Terminate or kill a child, tolerating an already-dead process."""
    try:
        process.kill() if kill else process.terminate()
    except (ProcessLookupError, OSError):
        pass


def _reap_core(state: dict[str, Any], deadline: float) -> dict[str, Any]:
    """Wait with a bound, then terminate, kill and reap the child.

    Every wait is bounded: the run deadline bounds the first wait, and the
    cleanup phases get the explicit `CORE_WAIT_SECONDS` / `CORE_KILL_SECONDS`
    grace. A child that stays alive is never reported as reaped.
    """
    process = state["process"]
    if state.get("reaped"):
        return dict(native_exit=state.get("native_exit"), usage=None,
                    terminated=state.get("terminated", False),
                    killed=state.get("killed", False),
                    timed_out=state.get("timed_out", False), reaped=True)
    native_exit, usage, timed_out = _wait_child(process, deadline)
    if timed_out:
        state["timed_out"] = True
    if native_exit is None:
        state["terminated"] = True
        _signal_child(process, kill=False)
        native_exit, usage, _ = _wait_child(process, time.monotonic() + CORE_WAIT_SECONDS)
    if native_exit is None:
        state["killed"] = True
        _signal_child(process, kill=True)
        native_exit, usage, _ = _wait_child(process, time.monotonic() + CORE_KILL_SECONDS)
    reaped = native_exit is not None
    if reaped:
        process.returncode = native_exit
    state["reaped"] = reaped
    state["native_exit"] = native_exit
    state["usage"] = usage
    return dict(native_exit=native_exit, usage=usage, terminated=state.get("terminated", False),
                killed=state.get("killed", False), timed_out=state.get("timed_out", False),
                reaped=reaped)


def _close_handles(state: dict[str, Any]) -> None:
    """Close the write end and the stderr handle exactly once."""
    if not state.get("fd_closed"):
        state["fd_closed"] = True
        try:
            os.close(state["write_fd"])
        except OSError:
            pass
    if not state.get("handles_closed"):
        state["handles_closed"] = True
        try:
            state["stderr"].close()
        except OSError:
            pass


def _count_lines(path: Path) -> int:
    """Count the lines of a values output file with bounded reads."""
    total = 0
    with path.open("rb") as source:
        for _ in source:
            total += 1
    return total


def _check_native_summary(summary: Any, native_exit: int | None,
                          values_count: int | None, events: int | None = None) -> str | None:
    """Return why a native summary violates the Rust summary contract.

    The contract is the one the core writes (`src/bin/btc_arb_history.rs`):
    `native_exit` / `spots` / `values` are integers, `complete` is a boolean and
    `error` is a string or null. A `complete` summary must agree with the
    observed native exit and with the number of written values, otherwise the
    batch is not proven complete.
    """
    if not isinstance(summary, Mapping):
        return "native summary is not an object"
    if "complete" not in summary:
        return f"native summary missing fields {sorted(NATIVE_SUMMARY_FIELDS)}"
    if summary["complete"] is not True:
        return "incomplete native summary"
    missing = [name for name in NATIVE_SUMMARY_FIELDS if name not in summary]
    if missing:
        return f"native summary missing fields {missing}"
    for name in ("native_exit", "spots", "values"):
        value = summary[name]
        if isinstance(value, bool) or not isinstance(value, int):
            return f"native summary field {name} is not an integer"
    if summary["spots"] < 0 or summary["values"] < 0:
        return "native summary has a negative input/output count"
    if not isinstance(summary["error"], (str, type(None))):
        return "native summary field error is not a string or null"
    if summary["error"] is not None:
        return "native summary claims completion with an error"
    if summary["native_exit"] != 0:
        return "native summary claims completion with a nonzero native exit"
    if native_exit is not None and summary["native_exit"] != native_exit:
        return "native summary native exit disagrees with the observed exit"
    if values_count is not None and summary["values"] != values_count:
        return "native summary value count disagrees with the values output"
    if events is not None and summary["spots"] + summary["values"] != events:
        return "native summary input count disagrees with the sent events"
    return None


def _finish_core(state: dict[str, Any], event_sha256: str, events: int,
                 deadline: float) -> dict[str, Any]:
    """Reap the child, record its native exit, resource use and result integrity."""
    candidate: Instance = state["instance"]
    if not state.get("fd_closed"):
        _close_handles(state)
    outcome = _reap_core(state, deadline)
    _close_handles(state)
    native_exit = outcome["native_exit"]
    usage = outcome["usage"]
    candidate.native_exit = native_exit
    candidate.child_cpu_seconds = (usage.ru_utime + usage.ru_stime) if usage else 0.0
    candidate.child_max_rss_kib = usage.ru_maxrss if usage else 0
    candidate.event_sha256 = event_sha256
    candidate.events = events
    candidate.terminated = bool(outcome.get("terminated"))
    candidate.killed = bool(outcome.get("killed"))
    candidate.reaped = bool(outcome.get("reaped"))
    candidate.timed_out = bool(outcome.get("timed_out"))
    values = state["dir"] / "values.jsonl"
    candidate.values_sha256 = sha256_file(values) if values.exists() else None
    values_count = _count_lines(values) if values.exists() else None
    summary_path = state["dir"] / "rust-summary.json"
    if summary_path.exists():
        try:
            candidate.summary = json.loads(summary_path.read_text())
        except json.JSONDecodeError:
            candidate.summary = {}
    else:
        candidate.summary = {}
    if native_exit == 64:
        # The Rust configuration gate refused the parameters: a refusal, not a crash.
        candidate.status = "REFUSED"
        candidate.error = "Rust refused the frozen configuration"
    elif state["error"] is not None:
        candidate.status = "FAILED"
        candidate.error = state["error"]
    elif candidate.status == "FAILED":
        pass
    elif native_exit == 0:
        candidate.status = "EXECUTED"
    elif native_exit is None:
        candidate.status = "FAILED"
        candidate.error = "core did not exit before the deadline"
    else:
        candidate.status = "REFUSED"
        candidate.error = f"native exit {native_exit}"
    if native_exit == 0 and candidate.status == "EXECUTED":
        # A zero exit is not enough: the outputs must be complete and consistent.
        if not candidate.values_sha256:
            candidate.status = "FAILED"
            candidate.error = candidate.error or "missing values output"
        else:
            problem = _check_native_summary(candidate.summary, native_exit, values_count, events)
            if problem is not None:
                candidate.status = "FAILED"
                candidate.error = candidate.error or problem
    if outcome["timed_out"] and candidate.error is None:
        candidate.status = "FAILED"
        candidate.error = "core did not exit before the deadline"
    return outcome


def _sample_statistics(contexts: list[dict[str, Any]],
                       dates: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    """Aggregate one instance's own samples into the four statistic tables."""
    comparison, calibration, daily, monthly = aggregate(contexts, dates)
    return {"comparison": comparison, "calibration": calibration, "daily": daily,
            "monthly": monthly}


def _export_instance_samples(candidate: Instance, contexts: list[dict[str, Any]],
                              instance_dir: Path, dates: dict[str, list[str]]) -> dict[str, Any]:
    """Merge the core's values into a private context copy and export full samples."""
    values_path = instance_dir / "values.jsonl"
    rows = [dict(row) for row in contexts]
    requested = sum(row["reason"] == "requested" for row in rows)
    merge_values(rows, values_path)
    candidate.samples_rows = len(rows)
    candidate.valued_rows = sum(row["p_up"] is not None for row in rows)
    candidate.missing_by_reason = {
        reason: sum(row["reason"] == reason for row in rows)
        for reason in sorted({row["reason"] for row in rows})}
    samples_path = instance_dir / "samples.csv"
    write_csv(samples_path, SAMPLE_COLUMNS, rows)
    candidate.samples_sha256 = sha256_file(samples_path)
    tables = _sample_statistics(rows, dates)
    write_csv(instance_dir / "comparison.csv", COMPARISON_COLUMNS, tables["comparison"])
    write_csv(instance_dir / "calibration.csv", CALIBRATION_COLUMNS, tables["calibration"])
    write_csv(instance_dir / "daily.csv", DAILY_COLUMNS, tables["daily"])
    write_csv(instance_dir / "monthly.csv", DAILY_COLUMNS, tables["monthly"])
    return dict(samples_sha256=candidate.samples_sha256, samples_rows=candidate.samples_rows,
                valued_rows=candidate.valued_rows, missing_by_reason=candidate.missing_by_reason,
                requested_rows=requested, tables=tables)


def _instance_reports(instances: list[Instance]) -> list[dict[str, Any]]:
    """Build the per-instance report rows from the recorded instance state."""
    reports = []
    for candidate in instances:
        reports.append(dict(
            name=candidate.name, vol_floor=candidate.vol_floor, status=candidate.status,
            native_exit=candidate.native_exit, error=candidate.error,
            pid=candidate.pid,
            values_sha256=candidate.values_sha256, event_sha256=candidate.event_sha256,
            events=candidate.events, child_cpu_seconds=candidate.child_cpu_seconds,
            child_max_rss_kib=candidate.child_max_rss_kib, summary=candidate.summary,
            samples_sha256=candidate.samples_sha256, samples_rows=candidate.samples_rows,
            valued_rows=candidate.valued_rows, missing_by_reason=candidate.missing_by_reason,
            complete=candidate.complete, terminated=candidate.terminated,
            killed=candidate.killed, reaped=candidate.reaped,
            timed_out=candidate.timed_out))
    return reports


def _write_partial_failure(output_dir: Path, instances: list[Instance],
                            cleanup: Mapping[str, Any], failure: str,
                            cleanup_error: str | None) -> None:
    """Persist the partial run state before the original exception propagates."""
    write_json(output_dir / "failure.json",
               dict(failure=failure, cleanup_error=cleanup_error,
                    prefetch_cleanup=dict(cleanup),
                    instances=_instance_reports(instances)))


def run_instances(client: Any, *, start: datetime, end: datetime, as_of: datetime,
                  instances: list[Instance], output_dir: Path, budget_seconds: float,
                  prefetch: bool, label: str, strategy: str,
                  flat: bool = False) -> dict[str, Any]:
    """Run one explicit window over one or more independent Rust cores.

    The event stream is encoded once per day and broadcast to every core, so
    all cores see byte-identical input in identical order. Each core keeps its
    own context copy so the exported samples are independent and comparable.
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
    day_sources: dict[str, Any] = {}
    prefetcher: BoundedPrefetcher | None = None
    days = window_days(start, end)
    dates = {"IS": [], "OOS": []}
    split = aware_utc(SPLIT)
    for day in days:
        partition = "IS" if aware_utc(day) < split else "OOS"
        dates[partition].append(day.date().isoformat())
    if prefetch:
        prefetcher = BoundedPrefetcher(client, as_of)
    failure: str | None = None
    cleanup: dict[str, Any] = {"cancelled": 0, "reclaimed": 0, "unreclaimed": 0,
                                "still_tracked": 0}
    cleanup_error: str | None = None
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
                check_deadline(deadline)
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
                        _write_event(state["write_fd"], encoded, deadline)
                    except TimeoutError:
                        # A blocked core must fail the run, not just one instance.
                        raise
                    except (BrokenPipeError, OSError) as error:
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
            source = dict(day=day.date().isoformat(), verified=counted.counts["verify"] == 1,
                           content_sha256=content, events=day_events_count,
                           row_counts=dict(counted.counts),
                           coverage=_coverage_payload(coverage),
                           missing=list(getattr(window, "missing", [])),
                           pending=list(getattr(window, "pending", [])),
                           conflicts=list(getattr(window, "conflicts", [])),
                           content_manifest=getattr(window, "content_manifest", {}),
                           provenance_manifest=getattr(window, "provenance_manifest", {}))
            write_json(output_dir / f"source-{day.date().isoformat()}.json", source)
            day_sources[day.date().isoformat()] = source
        check_deadline(deadline)
        for state in states:
            _finish_core(state, stream_hash.hexdigest(), seq, deadline)
    except BaseException as error:  # noqa: BLE001 — the failure is reported, not hidden
        failure = f"{type(error).__name__}"
        for state in states:
            if state["instance"].native_exit is None:
                state["instance"].status = "FAILED"
                state["instance"].error = state["instance"].error or failure
            try:
                _finish_core(state, stream_hash.hexdigest(), seq, deadline)
            except BaseException as cleanup_failure:  # noqa: BLE001 — the original wins
                cleanup_error = cleanup_error or f"{type(cleanup_failure).__name__}"
                state["instance"].status = "FAILED"
                state["instance"].error = state["instance"].error or cleanup_error
        raise
    finally:
        if prefetcher is not None:
            try:
                cleanup = prefetcher.close(deadline=time.monotonic() + CORE_WAIT_SECONDS)
            except BaseException as cleanup_failure:  # noqa: BLE001 — the original wins
                cleanup_error = cleanup_error or f"{type(cleanup_failure).__name__}"
        for state in states:
            try:
                if state["instance"].native_exit is None:
                    _finish_core(state, stream_hash.hexdigest(), seq,
                                 time.monotonic() + CORE_WAIT_SECONDS)
            except BaseException as cleanup_failure:  # noqa: BLE001 — the original wins
                cleanup_error = cleanup_error or f"{type(cleanup_failure).__name__}"
            _close_handles(state)
        if failure is not None:
            # The partial state is persisted before the original exception escapes.
            _write_partial_failure(output_dir, instances, cleanup, failure, cleanup_error)
    instance_reports = []
    instance_dirs: dict[str, Path] = {}
    exported: dict[str, dict[str, Any]] = {}
    for candidate in instances:
        instance_dir = output_dir / candidate.name if not flat else output_dir
        instance_dirs[candidate.name] = instance_dir
        report: dict[str, Any] = {}
        if candidate.status == "EXECUTED" and candidate.native_exit == 0:
            try:
                report = _export_instance_samples(candidate, contexts, instance_dir, dates)
            except (ValueError, OSError) as error:
                candidate.status = "FAILED"
                candidate.error = f"result integrity: {type(error).__name__}"
        summary = candidate.summary or {}
        if candidate.status == "EXECUTED":
            values_path = instance_dir / "values.jsonl"
            problem = _check_native_summary(summary, candidate.native_exit,
                                            _count_lines(values_path)
                                            if values_path.exists() else None, seq)
            if problem is not None:
                candidate.status = "FAILED"
                candidate.error = candidate.error or problem
        if candidate.status == "EXECUTED" and not candidate.values_sha256:
            candidate.status = "FAILED"
            candidate.error = candidate.error or "missing values output"
        candidate.complete = candidate.status == "EXECUTED"
        exported[candidate.name] = report
    for item in _instance_reports(instances):
        item["samples"] = exported[item["name"]]
        instance_reports.append(item)
    comparison = _compare_instances(instance_reports, instance_dirs)
    complete = all(item["complete"] for item in instance_reports) and \
        comparison["identical"] and cleanup["unreclaimed"] == 0
    return dict(
        label=label, strategy=strategy, prefetch=prefetch,
        start=start.isoformat(), end=end.isoformat(), as_of=as_of.isoformat(),
        output_dir=str(output_dir),
        events=seq, event_sha256=stream_hash.hexdigest(), contexts=len(contexts),
        bundle_opens=bundle_opens, prefetch_opened=(prefetcher.opened if prefetcher else 0),
        prefetch_cancelled=cleanup["cancelled"], prefetch_reclaimed=cleanup["reclaimed"],
        prefetch_unreclaimed=cleanup["unreclaimed"],
        prefetch_still_tracked=cleanup["still_tracked"],
        prepare_seconds=prepare_seconds, verify_seconds=verify_seconds,
        row_counts=row_counts, day_content_sha256=day_digests,
        day_sources=day_sources,
        wall_seconds=time.monotonic() - started,
        parent_ru_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        parent_ru_maxrss_note="process high-water mark, not an isolated arm peak",
        complete=complete, failure=failure, instances=instance_reports,
        instance_comparison=comparison)


def _compare_instances(instance_reports: list[dict[str, Any]],
                       instance_dirs: dict[str, Path]) -> dict[str, Any]:
    """Compare every instance's exported samples and statistics cell by cell.

    The comparison is exact: no numeric tolerance is applied to the sample
    columns, so a changed label, DRAW outcome, availability time, missing
    reason, warm-up reason or denominator is visible.
    """
    if len(instance_reports) < 2:
        return {"identical": True, "compared": 0, "reason": "single instance"}
    reference = instance_reports[0]
    identical = True
    reasons = []
    for report in instance_reports[1:]:
        if not report["complete"] or not reference["complete"]:
            identical = False
            reasons.append(f"{report['name']} did not complete")
            continue
        left = read_sample_csv(instance_dirs[reference["name"]] / "samples.csv")
        right = read_sample_csv(instance_dirs[report["name"]] / "samples.csv")
        sample_check = compare_sample_rows(left, right, SAMPLE_COLUMNS)
        if not sample_check["identical"]:
            identical = False
            reasons.append(f"sample drift {report['name']} vs {reference['name']}: "
                           f"{sample_check.get('reason')}")
        for name, key in (("comparison", ("partition", "offset")),
                          ("calibration", ("partition", "offset", "bin")),
                          ("daily", ("partition", "day", "offset"))):
            result = compare_tables(report["samples"]["tables"][name],
                                    reference["samples"]["tables"][name], key)
            if not result["identical"]:
                identical = False
                reasons.append(f"{name} drift {report['name']} vs {reference['name']}: "
                               f"{result.get('reason')}")
        for field in ("samples_rows", "valued_rows"):
            if report[field] != reference[field]:
                identical = False
                reasons.append(f"{field} drift {report['name']} vs {reference['name']}: "
                               f"{report[field]} != {reference[field]}")
    return {"identical": identical, "compared": len(instance_reports),
            "reasons": reasons}


def _compare_sample_files(left: Path, right: Path, label: str,
                          reasons: list[str]) -> None:
    """Compare two exported samples files cell by cell; append any drift."""
    if not left.exists() or not right.exists():
        reasons.append(f"{label}: missing samples file")
        return
    check = compare_sample_rows(read_sample_csv(left), read_sample_csv(right),
                                SAMPLE_COLUMNS)
    if not check["identical"]:
        reasons.append(f"{label}: {check.get('reason')}")


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
    content_identities = {part["event_sha256"] for part in parts}
    day_identities = {json.dumps(part["day_content_sha256"], sort_keys=True)
                      for part in parts}
    consistent = len(content_identities) == 1 and len(day_identities) == 1
    # The control arm is compared on its own complete samples, not only on the
    # event identities: each part must export the same complete sample table.
    sample_reasons: list[str] = []
    source_reasons: list[str] = []
    if len(parts) > 1:
        reference = output_dir / parts[0]["instances"][0]["name"] / "samples.csv"
        for part in parts[1:]:
            _compare_day_sources(part.get("day_sources", {}), parts[0].get("day_sources", {}),
                                 f"independent {part['label']}", source_reasons)
            other = output_dir / part["instances"][0]["name"] / "samples.csv"
            _compare_sample_files(reference, other,
                                  f"independent {part['instances'][0]['name']} vs "
                                  f"{parts[0]['instances'][0]['name']}", sample_reasons)
    consistent = consistent and not sample_reasons and not source_reasons
    merged = dict(label=label, strategy="independent", prefetch=False,
                  start=start.isoformat(), end=end.isoformat(), as_of=as_of.isoformat(),
                  events=sum(part["events"] for part in parts),
                  per_instance_events={part["instances"][0]["name"]: part["events"]
                                       for part in parts},
                  event_sha256=parts[0]["event_sha256"],
                  contexts=parts[0]["contexts"],
                  bundle_opens=sum(part["bundle_opens"] for part in parts),
                  prefetch_opened=0, prefetch_cancelled=0, prefetch_unreclaimed=0,
                  prepare_seconds=sum(part["prepare_seconds"] for part in parts),
                  verify_seconds=sum(part["verify_seconds"] for part in parts),
                  row_counts={name: sum(part["row_counts"][name] for part in parts)
                              for name in parts[0]["row_counts"]},
                  day_content_sha256=parts[0]["day_content_sha256"],
                  day_sources=parts[0].get("day_sources", {}),
                  part_content_identities=sorted(content_identities),
                  part_day_identities=sorted(day_identities),
                  content_identities_consistent=consistent,
                  sample_comparison_reasons=sample_reasons,
                  source_comparison_reasons=source_reasons,
                  wall_seconds=time.monotonic() - started,
                  parent_ru_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  parent_ru_maxrss_note="process high-water mark, not an isolated arm peak",
                  complete=consistent and all(part["complete"] for part in parts),
                  instances=[item for part in parts for item in part["instances"]],
                  parts=[dict(label=part["label"], events=part["events"],
                              bundle_opens=part["bundle_opens"],
                              output_dir=part["output_dir"],
                              row_counts=part["row_counts"],
                              event_sha256=part["event_sha256"],
                              day_content_sha256=part["day_content_sha256"],
                              day_sources=part.get("day_sources", {}),
                              samples_sha256=part["instances"][0]["samples_sha256"],
                              samples_rows=part["instances"][0]["samples_rows"],
                              valued_rows=part["instances"][0]["valued_rows"],
                              missing_by_reason=part["instances"][0]["missing_by_reason"],
                              complete=part["complete"]) for part in parts])
    write_json(output_dir / "independent.json", merged)
    return merged


# ------------------------------------------------------------------------- rescore


def rescore(source_dir: Path, evidence_dir: Path,
            expect_samples_sha256: str | None,
            trusted: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Rebuild the archived statistics from the signed-off samples; no Rust, no Mongo."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    COUNTERS.reset()
    verified = verify_trusted_archive(source_dir, trusted)
    samples_sha = verified["hashes"]["samples.csv"]
    if expect_samples_sha256 and expect_samples_sha256 != samples_sha:
        raise ValueError("samples hash mismatch: refusing to rescore")
    samples_path = source_dir / "samples.csv"
    coverage, params = verified["coverage"], verified["params"]
    identities, manifests = verified["identities"], verified["manifests"]
    prepare_started = time.monotonic()
    rows = read_samples(samples_path)
    prepare_seconds = time.monotonic() - prepare_started
    if len(rows) != coverage["actual_positions"]:
        raise ValueError("samples row count drift against archived coverage")
    valued = sum(row["p_up"] is not None for row in rows)
    if valued != coverage["valued"]:
        raise ValueError("valued count drift against archived coverage")
    verify_sample_identity(rows, params)
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
        source_manifests_sha256=verified["hashes"]["source-manifests.json"],
        source_manifest_count=len(manifests),
        trusted_archive_sha256=verified["hashes"],
        capture_time_identities=identities,
        capture_time_identity_layer="signed-off archive producer; not required to equal "
                                    "the current source tree",
        archived_params=params, archived_coverage=coverage,
        validated_input="signed-off samples.csv verified against the fixed trusted "
                        "manifest plus capture-time source/binary/config identities",
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
                  parent_ru_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  child_max_rss_kib=0, child_cpu_seconds=0.0,
                  db_calls=COUNTERS.db_calls, core_calls=COUNTERS.core_calls,
                  trusted_archive=verified["hashes"],
                  checks=checks, all_identical=all(item["identical"] for item in checks.values()))
    write_json(evidence_dir / "rescore.json", result)
    if not result["all_identical"]:
        raise ValueError("rescored statistics drifted from the archived statistics")
    return result


# ------------------------------------------------------------------------------ CLI


def _require_subtree(path: Path) -> Path:
    """Accept only this theme's evidence subtree (developer, fix1 or validate)."""
    resolved = path.resolve()
    allowed = (PERF_ROOT / "evidence").resolve()
    if not resolved.is_relative_to(allowed):
        raise ValueError("evidence directory outside the authorized performance subtree")
    return resolved


def _open_client() -> Any:
    COUNTERS.db_calls += 1
    from skills.data.unified_data.client import UnifiedDataClient
    from skills.data.unified_data.history_reader import Btc5mHistoryReader
    from skills.data.unified_data.storage import open_databases

    return UnifiedDataClient(history_reader=Btc5mHistoryReader(open_databases().ud))


def _identity_key(path: Path) -> str:
    """Return the identity key of one file, relative to the repository root.

    A file outside the repository (a test fixture binary) keeps its absolute
    path, so the identity stays well-defined instead of raising.
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _source_identity() -> dict[str, Any]:
    """Hash the current source, test, config and binary identity of this entry point."""
    files = [LAB / "history_performance.py", LAB / "history_research.py",
             LAB / "history_metrics.py", LAB / "history_input.py", LAB / "config.json",
             LAB / "tests/test_history_performance.py"]
    if BINARY.exists():
        files.append(BINARY)
    identity = {_identity_key(path): sha256_file(path) for path in files}
    return identity


def _dependency_identity() -> dict[str, str]:
    """Return the installed versions of the distributions the arms import.

    The arms read through `numpy` (statistics), `pandas` (provider stubs) and
    `pymongo`/`bson` (the history reader). Their installed versions decide
    the numbers the arms produce, so they belong to the arm identity.
    """
    versions: dict[str, str] = {}
    for name in DEPENDENCY_DISTRIBUTIONS:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _arm_source_identity() -> dict[str, Any]:
    """Hash the identities the arms actually depend on, including the facade.

    The runner hashes its own sources; the arms additionally read through the
    public facade and the inline fixtures of the performance tests, so the
    facade files, the four performance test files and the installed
    dependency versions are part of the identity that makes an arm's result
    reproducible.
    """
    identity = _source_identity()
    facade = ROOT / "skills/data/unified_data"
    required = [facade / name for name in FACADE_FILES] + [
        LAB / "tests" / name for name in ARM_TEST_FILES]
    for path in required:
        if not path.is_file():
            raise ValueError(f"missing required identity: {_identity_key(path)}")
        identity[_identity_key(path)] = sha256_file(path)
    identity["dependencies"] = _dependency_identity()
    return identity


def _write_run_identity(evidence: Path, stage: str,
                       argv: list[str] | None = None) -> dict[str, Any]:
    """Persist the argv, cwd and source identity of one performance run."""
    identity = dict(stage=stage, argv=list(argv) if argv is not None else list(sys.argv),
                    cwd=os.getcwd(), python=sys.version.split()[0], executable=sys.executable,
                    sources=_source_identity(), arm_sources=_arm_source_identity())
    write_json(evidence / f"identity-{stage}.json", identity)
    return identity


def _instance_sample_path(run: dict[str, Any], name: str) -> Path:
    """Return the exported samples file of one instance of one arm."""
    return Path(run["output_dir"]) / name / "samples.csv"


def _collect_partial_failures(evidence: Path) -> list[dict[str, Any]]:
    """Collect the persisted per-arm failure records of a failed run.

    Every arm writes its own `failure.json` with the per-core native exit,
    reaping and cleanup state. The CLI record embeds them, so a failed run
    keeps the real per-core evidence instead of a boolean about it.
    """
    records: list[dict[str, Any]] = []
    for path in sorted(evidence.rglob("failure.json")):
        if path.parent == evidence:
            continue
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        records.append({"path": str(path.relative_to(evidence)), "record": record})
    return records


def _arm_cores(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten the per-core state of every arm into one list of rows."""
    rows: list[dict[str, Any]] = []
    for run in runs:
        for instance in run.get("instances", []):
            rows.append(dict(label=run.get("label"), strategy=run.get("strategy"),
                             name=instance.get("name"), status=instance.get("status"),
                             native_exit=instance.get("native_exit"),
                             error=instance.get("error"),
                             pid=instance.get("pid"),
                             reaped=instance.get("reaped"),
                             terminated=instance.get("terminated"),
                             killed=instance.get("killed"),
                             timed_out=instance.get("timed_out")))
    return rows


def _compare_day_sources(sources: Mapping[str, Any], reference: Mapping[str, Any],
                         label: str, reasons: list[str]) -> None:
    """Compare logical day inputs, including the facade's stable manifests.

    These are the existing facade source/coverage facts, not wall times, RSS
    or Python object identities. Repeated-read batch totals are never inputs.
    """
    if set(sources) != set(reference):
        reasons.append(f"{label}: source day set drift")
    for day in sorted(set(sources) & set(reference)):
        for field in ("verified", "content_sha256", "coverage", "missing", "pending",
                      "conflicts", "row_counts", "events", "content_manifest",
                      "provenance_manifest"):
            if sources[day].get(field) != reference[day].get(field):
                reasons.append(f"{label} {day}: {field} drift")


def _compare_arms(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare every arm against the first arm on identity and complete samples.

    The arms must observe the same logical single stream (event and day
    content identities), the same complete samples per instance and the same
    statistical denominators and source summaries. The independent arm's total
    event count is the sum of its own repeated reads, so it is never compared
    against the shared arm's single-stream count.
    """
    reasons: list[str] = []
    if not runs:
        return {"identical": True, "compared": 0, "reasons": reasons}
    reference = runs[0]
    reference_day = json.dumps(reference.get("day_content_sha256", {}), sort_keys=True)
    for run in runs[1:]:
        name = run.get("label", "?")
        if run.get("event_sha256") != reference.get("event_sha256"):
            reasons.append(f"{name}: event identity drift against "
                           f"{reference.get('label', '?')}")
        if json.dumps(run.get("day_content_sha256", {}), sort_keys=True) != reference_day:
            reasons.append(f"{name}: day content identity drift against "
                           f"{reference.get('label', '?')}")
        _compare_day_sources(run.get("day_sources", {}), reference.get("day_sources", {}),
                             name, reasons)
        # Every arm must agree on the complete samples and the denominators of
        # its own instances, not only on the arm-level event identities.
        reference_instances = {item["name"]: item
                               for item in reference.get("instances", [])}
        for item in run.get("instances", []):
            counterpart = reference_instances.get(item["name"])
            if counterpart is None:
                continue
            for field in ("samples_sha256", "samples_rows", "valued_rows",
                          "missing_by_reason"):
                if item.get(field) != counterpart.get(field):
                    reasons.append(f"{name} {item['name']}: {_DENOMINATOR_LABELS[field]} "
                                   f"drift against {reference.get('label', '?')}")
    independent = next((run for run in runs if run.get("strategy") == "independent"), None)
    if independent is not None:
        shared = next((run for run in runs if run.get("strategy") != "independent"
                       and run.get("label") == "shared"), None)
        if shared is not None:
            reference_instance = shared["instances"][0]
            for part in independent.get("parts", []):
                name = part["label"]
                _compare_day_sources(part.get("day_sources", {}), shared.get("day_sources", {}),
                                     f"independent {name}", reasons)
                if part.get("samples_sha256") != reference_instance.get("samples_sha256"):
                    reasons.append(f"independent {name}: samples identity drift against "
                                   f"the shared arm")
                if part.get("samples_rows") != reference_instance.get("samples_rows"):
                    reasons.append(f"independent {name}: sample row count drift against "
                                   f"the shared arm")
                if part.get("valued_rows") != reference_instance.get("valued_rows"):
                    reasons.append(f"independent {name}: valued row count drift against "
                                   f"the shared arm")
                if part.get("missing_by_reason") != \
                        reference_instance.get("missing_by_reason"):
                    reasons.append(f"independent {name}: missing-reason denominators "
                                   f"drift against the shared arm")
                _compare_sample_files(
                    _instance_sample_path(shared, reference_instance["name"]),
                    Path(part["output_dir"]) / "samples.csv",
                    f"independent {name} vs shared {reference_instance['name']}", reasons)
    return {"identical": not reasons, "compared": len(runs), "reasons": reasons}


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
    parser.add_argument("--strategy", choices=("serial", "prefetch", "both"), default="serial",
                        help="facade read strategy; default is serial, prefetch is opt-in")
    parser.add_argument("--budget-seconds", type=float, default=1800.0)
    args = parser.parse_args(argv)
    evidence: Path | None = None
    evidence_owned = False
    runs: list[dict[str, Any]] = []
    try:
        evidence = _require_subtree(args.evidence_dir)
        if evidence.exists():
            raise ValueError("evidence directory already exists")
        if args.mode == "rescore":
            source = (args.source_dir or LEGACY_FULL).resolve()
            if not source.is_dir():
                raise ValueError("source directory does not exist")
            cli_argv = [sys.argv[0], *sys.argv[1:]] if argv is None else list(argv)
            evidence.mkdir(parents=True, exist_ok=False)
            evidence_owned = True
            start_identity = _write_run_identity(evidence, "start", cli_argv)
            result = rescore(source, evidence, args.expect_samples_sha256)
            after = _arm_source_identity()
            unchanged = after == start_identity["arm_sources"]
            write_json(evidence / "identity-after.json",
                       dict(stage="after", argv=cli_argv, cwd=os.getcwd(),
                            sources=_source_identity(), arm_sources=after,
                            sources_unchanged=unchanged))
            print(json.dumps(result, default=str), flush=True)
            if not unchanged:
                print("source identity drifted during the run", file=sys.stderr)
                return 6
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
        evidence.mkdir(parents=True, exist_ok=False)
        evidence_owned = True
        cli_argv = [sys.argv[0], *sys.argv[1:]] if argv is None else list(argv)
        start_identity = _write_run_identity(evidence, "start", cli_argv)
        client = _open_client()
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
        after = _arm_source_identity()
        unchanged = after == start_identity["arm_sources"]
        write_json(evidence / "identity-after.json",
                   dict(stage="after", argv=cli_argv, cwd=os.getcwd(),
                        sources=_source_identity(), arm_sources=after,
                        sources_unchanged=unchanged))
        if not unchanged:
            print("source identity drifted during the run", file=sys.stderr)
            return 6
        if not all(run.get("complete") for run in runs):
            print("performance run incomplete: one or more arms did not complete",
                  file=sys.stderr)
            # The incomplete run keeps its per-core state on disk: the arm
            # reports carry the native exit and the reaping of every core.
            write_json(evidence / "failure.json",
                       dict(failure="IncompleteRun",
                            message="one or more arms did not complete",
                            cores=_arm_cores(runs),
                            partial_failures=_collect_partial_failures(evidence)))
            return 4
        arms = _compare_arms(runs)
        write_json(evidence / "arm-comparison.json", arms)
        if not arms["identical"]:
            print("performance run incomplete: the arms disagree on identity or "
                  "complete samples", file=sys.stderr)
            return 4
        return 0
    except BaseException as error:  # noqa: BLE001 — the failure is persisted, not hidden
        # The evidence directory keeps the failure state: the partial run
        # already wrote its own failure.json, and the CLI writes the top-level
        # record so an interrupted run is still auditable.
        try:
            if evidence_owned and evidence is not None:
                write_json(evidence / "failure.json",
                           dict(failure=type(error).__name__,
                                message=str(error)[:200],
                                cores=_arm_cores(runs),
                                partial_failures=_collect_partial_failures(evidence),
                                partial_failure=(evidence / "shared" / "failure.json")
                                .exists(),
                                independent_failure=(evidence / "independent" /
                                                    "failure.json").exists()))
        except OSError:
            pass
        print(f"performance run failed: {type(error).__name__}: {error}", file=sys.stderr)
        if isinstance(error, TimeoutError):
            return 5
        if isinstance(error, KeyboardInterrupt):
            return 7
        return 2 if isinstance(error, Exception) else 7


if __name__ == "__main__":
    raise SystemExit(main())
