"""Bounded facade-only, three-native-core BTC5m research (SPEC/Design-06-003)."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import itertools
import json
import math
import os
import re
import resource
import signal
import sys
import subprocess
import time
from dataclasses import asdict, replace
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[4]
sys.path.insert(0, str(ROOT))
from skills.data.unified_data.history_types import DATASET_KLINES, DATASET_ROUNDS, to_us
from skills.data.unified_data.history_types import HistoryError, HistoryRequest, canonical_json

BOT = ROOT / "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits"
BINARY = BOT / "target/debug/btc_arb_phase1_history"
EVIDENCE = ROOT / "data/reports/2026-11-18-btc5m-phase1-model-research/evidence"
# Facade to_us accepts naive UTC, never local time or floating timestamps.
START = datetime(2026, 8, 10)
AS_OF = datetime(2026, 11, 17, 15)
OFFSETS = (30, 60, 120, 180, 240, 270)
FLOORS = {"M0": .00005, "M2-low": .000025, "M2-high": .0001}
SCHEMA = "btc-arb-phase1-history/1"
SUMMARY_FIELDS = frozenset(("schema_version", "native_exit", "spots", "values", "complete",
    "error", "accepted_events", "last_seq", "input_chain_keccak256", "max_active_rounds"))
VALUE_FIELDS = frozenset(("schema_version", "seq", "planned_start_us", "offset", "at_us",
    "round_id", "starts_at_us", "ends_at_us", "identity_available_at_us", "strike_available_at_us",
    "strike", "spot", "bar_open_us", "close_exclusive_us", "spot_available_at_us",
    "proxy_observation_at_us", "logical_elapsed_ms", "prediction_source", "actual_pair",
    "source_dataset", "price_kind", "clock_basis", "source_epoch", "reset_reason", "samples",
    "sigma_raw", "sigma", "floor_hit", "secs_left", "p_up", "valuation_status"))
LOCAL_FIELDS = ("source_epoch", "reset_reason", "samples", "sigma_raw", "sigma", "floor_hit",
                "p_up", "valuation_status")
MODELS = ("M0", "M1", "M2-low", "M2-high", "B0", "B1", "B2")
BUSINESS_SECONDS = {"small": 120, "pilot": 180, "full": 10000}
DAY_US = 86_400_000_000
END = datetime(2026, 11, 17)
PROTECTED = {
    "docs/rfc/06_strategy/RFC-06-003-btc5m-phase1-model-research.md":
        "8e087fe28251ed5847a73735f3ba3ac8d0f197102814168a4122f4f2df1b3409",
    "docs/spec/06_strategy/SPEC-06-003-btc5m-phase1-model-research.md":
        "d5abffc1e23fb91bdc5718c56ce370f5e192b13ad094e2181971329bb7cd516f",
    "docs/design/06_strategy/DESIGN-06-003-btc5m-phase1-model-research.md":
        "bf3763ac36114e76c33778d2e23a0ca068f6104a4fe2a34421da04d265c36a93",
    str((LAB / "history_performance.py").relative_to(ROOT)):
        "40f1251ed20de8198fed135e41fa78b38fcd5283f73c8fa0f282c4fd483588b3",
    str((LAB / "tests/test_history_performance.py").relative_to(ROOT)):
        "f78e6c6516ec55d9bf8efd00882c42bfabd33fb4bd6aefe12805beff71198219",
    str((LAB / "README.md").relative_to(ROOT)):
        "f439b9b02ef2a1d1fa4c422b34b7599e64c987ef44b9d4ecf168af72fbf643ae",
    str((BOT / "target/debug/btc_arb_history").relative_to(ROOT)):
        "2b90871b5e0e4c49cc0a0781684be72b4c6c431ed3303f9cc6fdd60f3e76a5f1",
}


class PreflightError(ValueError):
    """Argument/path preflight failure; intended CLI mapping is 64."""


class DataError(ValueError):
    """Data/consumer integrity failure; intended CLI mapping is 4."""


class DriftError(DataError):
    """Candidate, dependency or source identity changed (exit 6)."""


class BudgetError(TimeoutError):
    """Frozen wall, RSS or disk budget exceeded (exit 5)."""


class Cancelled(InterruptedError):
    """SIGINT/SIGTERM cancelled the batch (exit 7)."""


def failure_code(error: BaseException) -> int:
    """Map actual failure independently of observed child native exit codes."""
    if isinstance(error, PreflightError):
        return 64
    if isinstance(error, DriftError) or isinstance(error, HistoryError) and error.code == "DATASET_CHANGED":
        return 6
    if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
        return 5
    if isinstance(error, (Cancelled, KeyboardInterrupt)):
        return 7
    if isinstance(error, (DataError, HistoryError, BrokenPipeError)):
        return 4
    return 2


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise DataError("nonfinite JSON value")


def strict_loads(text: str) -> Any:
    """Decode JSON without silently discarding duplicate keys or nonfinite values."""
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite)


def encode_event(event: dict[str, Any]) -> bytes:
    """Encode once for shared disk/three-core transport, enforcing the wire cap."""
    line = (json.dumps(event, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()
    if len(line) > 65536:
        raise DataError("wire line exceeds 64KiB")
    return line


def claim_run(path: Path, mode: str) -> Path:
    """Claim exactly an approved, fresh leaf; never write to a pre-existing run."""
    expected = {"small": ("developer-small", "developer-small-retry-1", "developer-small-retry-2",
                          "developer-small-retry-3", "developer-small-retry-4", "developer-small-retry-5",
                          "validate-small", "developer-small-v01", "validate-small-v01"),
                "pilot": ("developer-pilot", "developer-pilot-retry-1", "validate-pilot",
                          "developer-pilot-v01", "validate-pilot-v01"),
                "full": ("full", "full-v01")}
    if mode not in expected:
        raise PreflightError("mode has no T3 output authorization")
    if ".." in path.parts:
        raise PreflightError("parent traversal forbidden")
    path = Path(os.path.abspath(path))
    if path not in {EVIDENCE / leaf for leaf in expected[mode]}:
        raise PreflightError("unapproved evidence path")
    for component in reversed((path, *path.parents)):
        if component.is_symlink():
            raise PreflightError("symlink evidence path")
    if path.exists():
        raise PreflightError("evidence leaf already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise PreflightError("evidence ownership race") from error
    return path


def core_config(start_us: int, end_us: int, floor: float, *,
                as_of: datetime | None = None) -> dict[str, Any]:
    """Build the isolated research config; no production configuration is loaded."""
    if floor not in FLOORS.values():
        raise PreflightError("unfrozen floor")
    cutoff = to_us(AS_OF if as_of is None else as_of)
    if as_of is not None and cutoff < end_us:
        raise PreflightError("research cutoff precedes window end")
    version = 1 if as_of is None else 2
    return dict(schema_version=f"btc-arb-phase1-research-config/{version}", symbol="BTCUSDT",
        window_start_us=start_us, window_end_us=end_us, as_of_us=cutoff,
        sample_seconds=5, half_life_secs=300, min_vol_samples=20,
        vol_floor=floor, clock_basis="event_time_proxy")


def core_command(directory: Path, start_us: int, end_us: int, *,
                 binary: Path | None = None) -> list[str]:
    """Return the frozen native argv, never the legacy binary or runtime bot."""
    return [str(BINARY if binary is None else binary), "--config", str(directory / "config.json"), "--input", "-",
        "--output", str(directory / "values.jsonl"), "--summary", str(directory / "rust-summary.json"),
        "--from-us", str(start_us), "--to-us", str(end_us)]


def check_summary(summary: Any, native: int | None, events: int, values: int) -> None:
    """Validate all new summary fields in addition to the legacy five-field check."""
    if not isinstance(summary, dict) or summary.keys() != SUMMARY_FIELDS:
        raise DataError("new summary exact field set mismatch")
    for name in ("native_exit", "spots", "values", "accepted_events", "max_active_rounds"):
        if type(summary[name]) is not int or summary[name] < 0:
            raise DataError("summary integer invalid")
    last = summary["last_seq"]
    if last is not None and (type(last) is not int or last < 0):
        raise DataError("last seq invalid")
    if summary["schema_version"] != "btc-arb-phase1-summary/1" or type(native) is not int or native != 0:
        raise DataError("native/version mismatch")
    if summary["native_exit"] != native or summary["complete"] is not True or summary["error"] is not None:
        raise DataError("native incomplete")
    if summary["values"] != values or summary["accepted_events"] != events:
        raise DataError("consumer counts mismatch")
    if summary["spots"] + summary["values"] != events or last != (events - 1 if events else None):
        raise DataError("input counts/last seq mismatch")
    if summary["max_active_rounds"] > 1 or (values and summary["max_active_rounds"] != 1):
        raise DataError("unbounded/missing active round")
    chain = summary["input_chain_keccak256"]
    if not isinstance(chain, str) or re.fullmatch(r"[0-9a-f]{64}", chain) is None:
        raise DataError("receiver chain invalid")


def _required_int(value: Any) -> int:
    # The facade preserves BSON Int64; normalize it without admitting bool/float.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DataError("invalid integer UTC")
    return int(value)


def merge_phase1_values(contexts: Iterator[dict[str, Any]], directory: Path) -> Iterator[dict[str, Any]]:
    """Stream the context and three raw native files into one wide sample row.

    No probability is recomputed here and no complete values file is loaded in
    memory. All same-input facts/status/state must agree across floors; only
    sigma, floor_hit and p_up may differ. Caller owns source qualification.
    """
    with ExitStack() as stack:
        streams = {model: stack.enter_context((directory / "cores" / model / "values.jsonl").open("rb"))
                   for model in FLOORS}
        for context in contexts:
            values = {}
            for model, stream in streams.items():
                line = stream.readline(65537)
                if not line or len(line) > 65536 or not line.endswith(b"\n"):
                    raise DataError("missing/invalid native value line")
                value = strict_loads(line.decode("utf-8"))
                if not isinstance(value, dict) or value.keys() != VALUE_FIELDS:
                    raise DataError("native value exact field set mismatch")
                if value["schema_version"] != "btc-arb-phase1-value/1":
                    raise DataError("native value version mismatch")
                for field in ("planned_start_us", "offset", "at_us", "seq", "samples"):
                    _required_int(value[field])
                for field in ("starts_at_us", "ends_at_us", "identity_available_at_us", "strike_available_at_us",
                              "bar_open_us", "close_exclusive_us", "spot_available_at_us",
                              "proxy_observation_at_us", "logical_elapsed_ms", "source_epoch"):
                    if value[field] is not None:
                        _required_int(value[field])
                for field in ("planned_start_us", "offset", "at_us", "round_id", "starts_at_us",
                              "ends_at_us", "identity_available_at_us", "strike_available_at_us", "strike"):
                    if value[field] != context[field]:
                        raise DataError("native/context identity mismatch")
                for field in ("p_up", "sigma", "sigma_raw", "spot", "strike", "secs_left"):
                    number = value[field]
                    if number is not None and (type(number) not in (int, float) or not math.isfinite(number)):
                        raise DataError("invalid native numeric field")
                if value["p_up"] is not None and not 0 <= value["p_up"] <= 1:
                    raise DataError("native probability out of range")
                if value["floor_hit"] is not None and type(value["floor_hit"]) is not bool:
                    raise DataError("native floor flag invalid")
                if value["valuation_status"] not in ("MISSING_IDENTITY", "IDENTITY_NOT_AVAILABLE",
                    "ROUND_INVALID", "MISSING_STRIKE", "STRIKE_NOT_AVAILABLE", "MISSING_SPOT",
                    "INPUT_INVALID", "CLOCK_INVALID", "SPOT_STALE", "WARMUP", "VALUED"):
                    raise DataError("unknown native valuation status")
                model_fields = ("sigma_raw", "sigma", "floor_hit", "p_up")
                if value["valuation_status"] == "VALUED":
                    if any(value[field] is None for field in model_fields) or value["samples"] < 20:
                        raise DataError("incomplete valued model")
                    if value["sigma_raw"] < 0 or value["sigma"] <= 0:
                        raise DataError("invalid valued sigma")
                elif any(value[field] is not None for field in model_fields):
                    raise DataError("unvalued model carries probability/sigma")
                values[model] = value
            common = {key: value for key, value in values["M0"].items()
                      if key not in ("sigma", "floor_hit", "p_up")}
            if any({key: value for key, value in row.items()
                    if key not in ("sigma", "floor_hit", "p_up")} != common for row in values.values()):
                raise DataError("native shared input/state mismatch")
            wide = {key: value for key, value in values["M0"].items() if key not in LOCAL_FIELDS}
            wide.update(context)
            for model, row in values.items():
                prefix = {"M0": "m0", "M2-low": "m2_low", "M2-high": "m2_high"}[model]
                wide[f"{prefix}_value_seq"] = row["seq"]
                wide.update({f"{prefix}_{field}": row[field] for field in LOCAL_FIELDS})
            yield wide
        if any(stream.read(1) for stream in streams.values()):
            raise DataError("extra native value row")


def _write_new_json(path: Path, value: Any, *, compact: bool = False) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, allow_nan=False, ensure_ascii=False,
                  indent=None if compact else 2, separators=(",", ":") if compact else None)
        stream.write("\n")


def broadcast_phase1(events: Iterator[dict[str, Any]], directory: Path,
                     start_us: int, end_us: int, deadline: float,
                     guard: Any = None, *, as_of: datetime | None = None,
                     binary: Path | None = None) -> dict[str, Any]:
    """Broadcast once-encoded events to three real isolated native processes.

    The caller owns the new directory, total signal/resource watchdog, source
    authentication and theoretical-slot count. This primitive owns all native
    child descriptors and bounded cleanup, including when a transport fails.
    It neither opens the facade nor computes probabilities in Python.
    """
    from history_performance import Instance, _write_event, _finish_core, _close_handles

    states = []
    sent = []
    event_hash = hashlib.sha256()
    count = values = 0
    problem = None
    outcomes = []
    business_started = time.monotonic()
    try:
        (directory / "cores").mkdir(exist_ok=False)
        for model, floor in FLOORS.items():
            core_dir = directory / "cores" / model
            core_dir.mkdir(exist_ok=False)
            config = (core_config(start_us, end_us, floor) if as_of is None else
                      core_config(start_us, end_us, floor, as_of=as_of))
            _write_new_json(core_dir / "config.json", config)
            command = (core_command(core_dir, start_us, end_us) if binary is None else
                       core_command(core_dir, start_us, end_us, binary=binary))
            _write_new_json(core_dir / "command.json", command)
            stderr = (core_dir / "rust-stderr.log").open("xb")
            read_fd, write_fd = os.pipe()
            os.set_blocking(write_fd, False)
            try:
                process = subprocess.Popen(command, stdin=read_fd, stdout=subprocess.DEVNULL,
                                           stderr=stderr)
            except BaseException:
                os.close(write_fd)
                stderr.close()
                raise
            finally:
                os.close(read_fd)
            instance = Instance(model, floor)
            instance.pid = process.pid
            states.append(dict(instance=instance, dir=core_dir, command=command,
                process=process, stderr=stderr, write_fd=write_fd, error=None, closed=False))
            sent.append(dict(hash=hashlib.sha256(), events=0))
            if guard is not None:
                guard.pids.append(process.pid)
        with (directory / "events.jsonl").open("xb") as sink:
            for event in events:
                if guard is not None:
                    guard.check()
                if time.monotonic() >= deadline:
                    raise TimeoutError("business deadline")
                # Sequence is generated once, not separately by each consumer.
                line = encode_event(dict(event, seq=count))
                sink.write(line)
                event_hash.update(line)
                if guard is not None and guard.daily_hash is not None:
                    guard.daily_hash.update(line)
                for state, accepted in zip(states, sent):
                    _write_event(state["write_fd"], line, min(deadline, time.monotonic() + 10))
                    accepted["hash"].update(line)
                    accepted["events"] += 1
                count += 1
                values += event["payload"]["type"] == "value"
                if guard is not None:
                    guard.sent_events = count
    except BaseException as error:
        problem = error
    finally:
        if guard is not None:
            guard.pause()
        # EOF every stdin before waiting for any child. Never leave healthy peers
        # awaiting EOF while another peer is being reaped.
        for state in states:
            _close_handles(state)
        for state, accepted in zip(states, sent):
            if problem is not None:
                state["error"] = "batch incomplete"
            try:
                _finish_core(state, accepted["hash"].hexdigest(), accepted["events"],
                             min(deadline, time.monotonic() + 1))
                summary = strict_loads((state["dir"] / "rust-summary.json").read_text())
                if problem is None:
                    check_summary(summary, state.get("native_exit"), count, values)
                instance = asdict(state["instance"])
                instance["complete"] = problem is None and instance["status"] == "EXECUTED"
                usage = state.get("usage")
                instance["child_max_rss_kib"] = usage.ru_maxrss if usage else None
                instance["child_cpu_seconds"] = usage.ru_utime + usage.ru_stime if usage else None
                if usage is not None and usage.ru_maxrss > 256*1024 and problem is None:
                    problem = BudgetError("native RSS high-water limit exceeded")
                    instance["complete"] = False
                outcomes.append(instance)
                if state["instance"].status != "EXECUTED" and problem is None:
                    problem = DataError("native batch incomplete")
            except BaseException as error:
                # _finish_core reaps before parsing output, so record the actual
                # observed status even when the output/summary was corrupt.
                outcomes.append(dict(name=state["instance"].name, pid=state["process"].pid,
                    native_exit=state.get("native_exit"), reaped=state.get("reaped", False),
                    complete=False, error="native finalization failed"))
                if problem is None:
                    problem = error
    location = None
    trace = problem.__traceback__ if problem is not None else None
    while trace is not None:
        location = dict(file=Path(trace.tb_frame.f_code.co_filename).name,
                        line=trace.tb_lineno, function=trace.tb_frame.f_code.co_name)
        trace = trace.tb_next
    result = dict(complete=problem is None, events=count, values=values,
        event_sha256=event_hash.hexdigest(), cores=outcomes,
        wall_seconds=time.monotonic() - business_started,
        error=None if problem is None else type(problem).__name__,
        failure_location=location,
        source_error_code=problem.code if isinstance(problem, HistoryError) else None,
        failure_code=0 if problem is None else failure_code(problem))
    if problem is None:
        chains = {item["summary"]["input_chain_keccak256"] for item in outcomes}
        hashes = {item["event_sha256"] for item in outcomes}
        if len(outcomes) != 3 or len(chains) != 1 or hashes != {event_hash.hexdigest()}:
            result.update(complete=False, error="consumer identity mismatch")
            result["failure_code"] = 4
    return result


def iter_phase1_day(bundle: Any, start_us: int, end_us: int,
                    contexts: list[dict], rounds: list[dict], *,
                    as_of: datetime | None = None) -> Iterator[dict[str, Any]]:
    """Stream one day through the causal five-second adapter, preserving all slots.

    The caller must exhaust this iterator, authenticate bundle.verify_consumed,
    and validate dataset/coverage counts. This adapter does not infer successful
    source authentication from reaching EOF. All labels remain outside events.
    """
    if start_us % 300_000_000 or end_us % 300_000_000 or not 0 < end_us - start_us <= 86_400_000_000:
        raise DataError("invalid day intersection")
    if contexts or rounds:
        raise DataError("day buffers must be fresh, not growing across days")
    identities, by_start, strikes = {}, {}, {}
    for row in bundle.iter_metadata():
        payload = row.payload
        key = payload["round_id"]
        planned = _required_int(payload["starts_at_us"])
        if not isinstance(key, str) or not key or key in identities or planned in by_start:
            raise DataError("duplicate/invalid official identity")
        if row.source != "predict.fun" or payload["dataset"] != DATASET_ROUNDS:
            raise DataError("identity source invalid")
        if not start_us <= planned < end_us or planned % 300_000_000:
            raise DataError("identity outside day")
        identities[key] = row
        by_start[planned] = key
    features = iter(bundle.iter_features())
    first = None
    for row in features:
        if row.payload["dataset"] == DATASET_KLINES:
            first = row
            break
        key = row.payload.get("round_id")
        if row.payload["dataset"] != DATASET_ROUNDS or row.source != "predict.fun" or key in strikes:
            raise DataError("round feature source/duplicate invalid")
        if key not in identities:
            raise DataError("strike has no official identity")
        strike = float(row.payload["start_price"])
        if not math.isfinite(strike) or strike <= 0:
            raise DataError("strike invalid")
        strikes[key] = row
    requests = []
    for planned in range(start_us, end_us, 300_000_000):
        key = by_start.get(planned)
        identity, strike_row = identities.get(key), strikes.get(key)
        facts = dict(round_id=key, planned_start_us=planned,
            starts_at_us=identity.payload["starts_at_us"] if identity else None,
            ends_at_us=identity.payload["ends_at_us"] if identity else None,
            identity_available_at_us=identity.available_at_us if identity else None,
            strike_available_at_us=strike_row.available_at_us if strike_row else None,
            strike=float(strike_row.payload["start_price"]) if strike_row else None,
            label=None, label_available_at_us=None, label_status="MISSING")
        if identity:
            rounds.append(dict(facts))
        for offset in OFFSETS:
            at = planned + offset * 1_000_000
            context = dict(facts, offset=offset, at_us=at)
            contexts.append(context)
            payload = {name: value for name, value in facts.items()
                       if name not in ("label", "label_available_at_us", "label_status")}
            payload.update(type="value", symbol="BTCUSDT", offset=offset)
            requests.append(dict(schema_version=SCHEMA, at_us=at, payload=payload))
    index = 0
    previous = start_us
    candles = itertools.chain(() if first is None else (first,), features)
    for row in candles:
        payload = row.payload
        if payload["dataset"] != DATASET_KLINES or row.source != "binance-vision":
            raise DataError("unexpected candle source/dataset")
        closed = _required_int(payload["close_exclusive_us"])
        opened = _required_int(payload["open_time_us"])
        if closed - opened != 1_000_000 or closed % 1_000_000 or not previous < closed <= end_us:
            raise DataError("candle framing/order invalid")
        if row.available_at_us != closed:
            raise DataError("proxy availability mismatch")
        price = float(payload["close"])
        if not math.isfinite(price) or price <= 0:
            raise DataError("candle price invalid")
        while index < len(requests) and requests[index]["at_us"] < closed:
            yield requests[index]
            index += 1
        if closed % 5_000_000 == 0:
            yield dict(schema_version=SCHEMA, at_us=closed,
                payload=dict(type="spot", symbol="BTCUSDT", price=price, bar_open_us=opened,
                    close_exclusive_us=closed, available_at_us=closed, prediction_source="Binance",
                    actual_pair="BTCUSDT", source_dataset="binance-vision", price_kind="trade_close",
                    clock_basis="event_time_proxy"))
        while index < len(requests) and requests[index]["at_us"] == closed:
            yield requests[index]
            index += 1
        previous = closed
    yield from requests[index:]
    labels = {}
    for row in bundle.iter_labels():
        key = row.payload["round_id"]
        if key not in identities or key in labels or row.source != "predict.fun":
            raise DataError("label identity/source/duplicate invalid")
        identity = identities[key].payload
        if any(row.payload[field] != identity[field] for field in ("starts_at_us", "ends_at_us")):
            raise DataError("label identity mismatch")
        if row.available_at_us < row.payload["ends_at_us"]:
            raise DataError("label before round end")
        if row.payload["official_outcome"] not in ("UP", "DOWN", "DRAW"):
            raise DataError("unknown official label")
        labels[key] = row
    for context in itertools.chain(contexts, rounds):
        label = labels.get(context["round_id"])
        if label is not None:
            context.update(label=label.payload["official_outcome"],
                label_available_at_us=label.available_at_us,
                label_status=("AFTER_CUTOFF" if label.available_at_us > to_us(AS_OF if as_of is None else as_of) else
                    {"UP": "BINARY_UP", "DOWN": "BINARY_DOWN", "DRAW": "DRAW"}[label.payload["official_outcome"]]))


def digest(path: Path) -> str:
    """Hash a specific public artifact with bounded reads."""
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def capture_identity() -> dict[str, Any]:
    """Bind sources, tests, facade, dependencies, compiler and both binaries."""
    from history_performance import FACADE_FILES
    files = [ROOT / name for name in PROTECTED]
    files += [LAB / name for name in ("phase1_model_research.py", "phase1_model_metrics.py",
        "tests/test_phase1_model_research.py", "tests/test_phase1_model_metrics.py",
        "tests/phase1_reference.py", "history_input.py", "history_research.py", "history_metrics.py")]
    files += [BOT / name for name in ("src/bot/arbitrage.rs", "src/bot/arbitrage/phase1.rs",
        "src/bot/arbitrage/phase1_history.rs", "src/bin/btc_arb_phase1_history.rs",
        "src/service/spot.rs", "Cargo.toml", "Cargo.lock")]
    files += [ROOT / "skills/data/unified_data" / name for name in FACADE_FILES]
    files.append(BINARY)
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in files}
    if any(hashes[name] != expected for name, expected in PROTECTED.items()):
        raise DriftError("protected baseline mismatch")
    repositories = {}
    for label, directory in (("root", ROOT), ("bot", BOT)):
        repositories[label] = {}
        for field, arguments in (("head", ["rev-parse", "HEAD"]),
                                  ("branch", ["branch", "--show-current"])):
            repositories[label][field] = subprocess.check_output(
                ["git", *arguments], cwd=directory, text=True, timeout=5).strip()
        if repositories[label]["branch"] != "main":
            raise PreflightError("research requires existing main branches")
    dependencies = {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "pymongo")}
    import numpy
    import pandas
    import pymongo
    return dict(files=hashes, repositories=repositories, dependencies=dependencies,
        executable=sys.executable, python=sys.version, compiler={
            name: subprocess.check_output([name, "--version"], text=True, timeout=5).strip()
            for name in ("cargo", "rustc")})


class RunBudget:
    """Main-thread deadline and <=1s RSS/disk samples of this owned run only."""

    def __init__(self, directory: Path, seconds: float, mode: str):
        self.directory = directory
        self.started = time.monotonic()
        self.deadline = self.started + seconds
        self.disk_limit = (4096 if mode == "full" else 128) * (1 << 20)
        self.pids: list[int] = []
        self.samples: list[dict] = []
        self.sent_events = 0
        self.daily_hash = None
        self.read_registry: list[dict] = []
        self.last_sample = -math.inf
        self.original_handlers: dict = {}
        self.cleanup_errors: list[str] = []

    def check(self, force: bool = False) -> None:
        """Check a boundary; the periodic alarm also interrupts blocked main-thread I/O."""
        now = time.monotonic()
        if now >= self.deadline:
            raise BudgetError("business deadline exceeded")
        if not force and now - self.last_sample < .5:
            return
        self.last_sample = now
        rss = {}
        for pid in [os.getpid(), *self.pids]:
            try:
                with Path(f"/proc/{pid}/status").open() as source:
                    match = re.search(r"^VmRSS:\s+(\d+) kB$", source.read(), re.MULTILINE)
                rss[str(pid)] = int(match[1]) if match else None
            except FileNotFoundError:
                rss[str(pid)] = None
        written = sum(path.stat().st_size for path in self.directory.rglob("*") if path.is_file())
        self.samples.append(dict(elapsed=now-self.started, rss_kib=rss, written_bytes=written))
        parent = rss[str(os.getpid())]
        if parent is None or parent > 512 * 1024 or any(
                value is not None and value > 256 * 1024 for pid, value in rss.items()
                if pid != str(os.getpid())) or sum(value or 0 for value in rss.values()) > 1280 * 1024:
            raise BudgetError("RSS limit exceeded")
        if written > self.disk_limit:
            raise BudgetError("disk budget exceeded")

    def _alarm(self, signum: int, frame: Any) -> None:
        self.check(force=True)

    def _cancel(self, signum: int, frame: Any) -> None:
        raise Cancelled("cancelled by signal")

    def start(self) -> None:
        """Install Linux timers; no background reader or prefetch task is created."""
        for number in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM):
            self.original_handlers[number] = signal.getsignal(number)
            signal.signal(number, self._alarm if number == signal.SIGALRM else self._cancel)
        self.resume()

    def pause(self) -> None:
        """Disarm business cancellation during the frozen <=60s cleanup window."""
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def resume(self) -> None:
        """Re-arm without extending the original business deadline."""
        signal.signal(signal.SIGINT, self._cancel)
        signal.signal(signal.SIGTERM, self._cancel)
        signal.setitimer(signal.ITIMER_REAL, max(.001, min(.5, self.deadline-time.monotonic())), .5)

    def close(self) -> None:
        """Restore embedding process handlers after owned children are reaped."""
        signal.setitimer(signal.ITIMER_REAL, 0)
        for number, handler in self.original_handlers.items():
            signal.signal(number, handler)


def open_bundle(client: Any, request: HistoryRequest) -> Any:
    """Use the unchanged approved facade adapter, not a temporary DB probe."""
    from history_input import iter_history_input
    # Internal DTO/to_us uses naive UTC; the public facade requires explicit UTC.
    # Convert only at this boundary, preserving the integer-time DTO and adapter.
    explicit = replace(request, start_utc=request.start_utc.replace(tzinfo=timezone.utc),
        end_utc=request.end_utc.replace(tzinfo=timezone.utc),
        as_of_utc=request.as_of_utc.replace(tzinfo=timezone.utc))
    return iter_history_input(client, explicit)


def _manifest_snapshot(value: Any) -> Any:
    """Preserve facade-native Decimal/datetime values using its canonical encoding."""
    return json.loads(canonical_json(value))


def _bounded_call(guard: RunBudget, function: Any) -> Any:
    import pymongo
    guard.check()
    # read()/verify() span multiple pages. The reader retains its 10s page
    # deadlines; the outer scope must bound the whole call by the run budget.
    with pymongo.timeout(max(.001, guard.deadline - time.monotonic())):
        return function()


class CountedDay:
    """One day's three streams with explicit completion and dataset counters."""

    def __init__(self, bundle: Any, guard: RunBudget, registry: dict):
        self.bundle, self.guard, self.registry = bundle, guard, registry
        self.counts = dict(features=0, metadata=0, labels=0)
        self.datasets = {DATASET_KLINES: 0, DATASET_ROUNDS: 0}
        self.exhausted: list[str] = []

    def _iterate(self, name: str) -> Iterator[Any]:
        self.registry["stage"] = name
        source = iter(getattr(self.bundle, f"iter_{name}")())
        while True:
            try:
                row = _bounded_call(self.guard, lambda: next(source))
            except StopIteration:
                self.exhausted.append(name)
                return
            self.counts[name] += 1
            if name == "features":
                dataset = row.payload["dataset"]
                if dataset not in self.datasets:
                    raise DataError("unknown source dataset")
                self.datasets[dataset] += 1
            yield row

    def iter_metadata(self) -> Iterator[Any]:
        return self._iterate("metadata")

    def iter_features(self) -> Iterator[Any]:
        return self._iterate("features")

    def iter_labels(self) -> Iterator[Any]:
        return self._iterate("labels")


ROUND_COLUMNS = ("round_id", "planned_start_us", "starts_at_us", "ends_at_us",
    "identity_available_at_us", "strike_available_at_us", "strike", "label",
    "label_available_at_us", "label_status")


def csv_value(value: Any) -> Any:
    """Lossless scalar representation with explicit null and boolean tokens."""
    if value is None:
        return "N/A"
    if type(value) is bool:
        return "true" if value else "false"
    return repr(value) if type(value) is float else value


def write_csv(path: Path, rows: Any, columns: Any = None) -> None:
    """Exclusive raw CSV projection; never rounds timestamps or probabilities."""
    source = iter(rows)
    first = next(source, None)
    fields = list(columns if columns is not None else (first or {}).keys())
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in itertools.chain(() if first is None else (first,), source):
            writer.writerow({key: csv_value(row.get(key)) for key in fields})


def json_lines(path: Path) -> Iterator[dict]:
    """Read immutable LF-framed evidence, rejecting duplicate/nonfinite values."""
    with path.open("rb") as stream:
        for line in stream:
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise DataError("invalid evidence framing")
            yield strict_loads(line.decode())


def consume_days(client: Any, directory: Path, start: datetime, end: datetime,
                 guard: RunBudget, source_records: list[dict], *,
                 as_of: datetime | None = None) -> Iterator[dict]:
    """Open one facade day, authenticate all three streams and release day buffers."""
    with (directory / "contexts.jsonl").open("xb") as context_file, (
            directory / "rounds.csv").open("x", newline="", encoding="utf-8") as round_file:
        writer = csv.DictWriter(round_file, fieldnames=ROUND_COLUMNS)
        writer.writeheader()
        day = start
        while day < end:
            day_end = min(end, day + timedelta(days=1))
            record = dict(day=day.date().isoformat(), started=time.monotonic()-guard.started,
                          stage="open", finished=False)
            guard.read_registry.append(record)
            day_started = time.monotonic()
            evidence: dict[str, Any] = dict(day=record["day"], verified=False)
            try:
                request = HistoryRequest(day, day_end, AS_OF if as_of is None else as_of, warmup_seconds=0,
                                         availability_mode="event-time-proxy")
                source = _bounded_call(guard, lambda: open_bundle(client, request))
                opened = time.monotonic()
                before = _manifest_snapshot(source.content_manifest)
                evidence["content_manifest_start"] = before
                counted = CountedDay(source, guard, record)
                evidence.update(stream_counts=counted.counts, dataset_counts=counted.datasets,
                                exhausted=counted.exhausted)
                contexts, rounds = [], []
                daily_hash = guard.daily_hash = hashlib.sha256()
                events = values = 0
                first_event = guard.sent_events
                for event in iter_phase1_day(counted, to_us(day), to_us(day_end), contexts, rounds, as_of=as_of):
                    guard.check()
                    events += 1
                    values += event["payload"]["type"] == "value"
                    yield event
                consumed = time.monotonic()
                record["stage"] = "verify"
                content = _bounded_call(guard, source.verify_consumed)
                verified_at = time.monotonic()
                window = source._window
                evidence.update(content_manifest_after=_manifest_snapshot(source.content_manifest),
                    content_manifest=_manifest_snapshot(window.content_manifest),
                    provenance_manifest=_manifest_snapshot(window.provenance_manifest),
                    coverage=asdict(window.coverage), status=window.status,
                    missing=window.missing, pending=window.pending, conflicts=window.conflicts,
                    stream_counts=counted.counts, dataset_counts=counted.datasets,
                    exhausted=counted.exhausted, content_sha256=content, verified=source.verified,
                    canonical_content_sha256=before.get("content_sha256"), consumed_output_sha256=content,
                    event_sha256=daily_hash.hexdigest(), events=events, values=values,
                    first_seq=first_event, last_seq=first_event+events-1,
                    assumptions=getattr(source, "availability_assumptions", []),
                    timings=dict(open_seconds=opened-day_started, consume_seconds=consumed-opened,
                        verify_seconds=verified_at-consumed))
                if (before != evidence["content_manifest_after"] or
                        before != evidence["content_manifest"]):
                    raise DriftError("daily manifest drift")
                seconds = (to_us(day_end)-to_us(day)) // 1_000_000
                expected_rounds = seconds // 300
                if (not source.verified or content != before.get("output_sha256") or
                    sorted(counted.exhausted) != ["features", "labels", "metadata"] or
                    window.status != "complete" or window.missing or window.pending or window.conflicts or
                    counted.counts != dict(features=seconds+expected_rounds,
                                           metadata=expected_rounds, labels=expected_rounds) or
                    counted.datasets != {DATASET_KLINES: seconds, DATASET_ROUNDS: expected_rounds} or
                    len(contexts) != expected_rounds*6 or values != len(contexts)):
                    raise DataError("day qualification/complete consumption failed")
                record["stage"] = "write"
                for context in contexts:
                    context_file.write(encode_event(context))
                for row in rounds:
                    writer.writerow({key: csv_value(row.get(key)) for key in ROUND_COLUMNS})
                evidence["timings"].update(write_seconds=time.monotonic()-verified_at,
                                           total_seconds=time.monotonic()-day_started)
                source_records.append(evidence)
            except HistoryError as problem:
                evidence["error_code"] = problem.code  # Stable public code, never raw DB exception text.
                raise
            finally:
                record.update(finished=True, finished_seconds=time.monotonic()-guard.started,
                              interrupted=record["stage"] != "write")
                primary = sys.exc_info()[0]
                try:
                    _write_new_json(directory / f"source-{record['day']}.json", evidence)
                except Exception as problem:
                    guard.cleanup_errors.append(type(problem).__name__)
                    if primary is None:
                        raise
            day = day_end


def _artifact_hashes(directory: Path) -> dict[str, str]:
    return {str(path.relative_to(directory)): digest(path) for path in sorted(directory.rglob("*"))
            if path.is_file() and path.name not in ("run.json", "failure.json")
            and "reference" not in path.relative_to(directory).parts}


def run_phase1(directory: Path, mode: str, argv: list[str], client: Any = None,
               remaining_seconds: int | None = None) -> int:
    """Run all owned stages, preserving real native exits and failed partial evidence."""
    from phase1_model_metrics import materialize_run
    start = START
    end = START + (timedelta(seconds=300) if mode == "small" else timedelta(days=1))
    if mode == "full":
        end = END
    budget = RunBudget(directory, BUSINESS_SECONDS[mode], mode)
    began = datetime.now(timezone.utc).isoformat()
    run: dict[str, Any] = dict(complete=False, mode=mode, transport={}, read_registry=budget.read_registry)
    identity = None
    error = None
    code = 0
    databases = None
    sources: list[dict] = []
    budget.start()
    def finish_flow() -> None:
        budget.check()
        run["flow_wall_seconds"] = time.monotonic()-budget.started
        budget.deadline = time.monotonic()+min(1800,
            remaining_seconds-run["flow_wall_seconds"]-2400-300-800)
    try:
        identity = capture_identity()
        _write_new_json(directory / "identity-start.json", identity)
        _write_new_json(directory / "commands.json", dict(argv=argv, cwd=str(Path.cwd()),
                                                         executable=sys.executable))
        _write_new_json(directory / "params.json", dict(mode=mode, start_us=to_us(start),
            end_us=to_us(end), as_of_us=to_us(AS_OF), sample_seconds=5, warmup_seconds=0,
            offsets=OFFSETS, floors=FLOORS, half_life_seconds=300, min_vol_samples=20,
            clock_basis="event_time_proxy", source_dataset="binance-vision", price_kind="trade_close",
            numeric_conversion="decimal_to_float_single_pass", remaining_seconds=remaining_seconds,
            fit=dict(optimizer="projected-newton-2d/1", regularization=.001, max_iterations=500,
                     projected_gradient=1e-8, selection_mode="FIXED"),
            bootstrap=dict(seed=42, replicates=1000, generator="PCG64", quantile="linear")))
        budget.check()
        if client is None:
            from skills.data.unified_data.client import UnifiedDataClient
            from skills.data.unified_data.history_reader import Btc5mHistoryReader
            from skills.data.unified_data.storage import open_databases
            databases = _bounded_call(budget, open_databases)
            client = UnifiedDataClient(history_reader=Btc5mHistoryReader(databases.ud))
        run["transport"] = broadcast_phase1(consume_days(client, directory, start, end, budget, sources),
            directory, to_us(start), to_us(end), budget.deadline, guard=budget)
        budget.resume()
        if not run["transport"]["complete"]:
            code = run["transport"]["failure_code"]
            raise DataError("transport/source batch incomplete")
        budget.check()
        expected = (to_us(end)-to_us(start)) // 300_000_000 * 6
        if run["transport"]["values"] != expected:
            raise DataError("theoretical slot count mismatch")
        merged = merge_phase1_values(json_lines(directory / "contexts.jsonl"), directory)
        run["statistics"] = materialize_run(merged, directory, mode=mode,
            start_us=to_us(start), end_us=to_us(end), as_of_us=to_us(AS_OF), check=budget.check,
            flow_finished=finish_flow if mode == "full" else None)
        budget.check(force=True)
        run["data_qualified"] = True
    except BaseException as problem:
        error = type(problem).__name__
        code = code or failure_code(problem)
    finally:
        budget.pause()
        cleanup_errors = budget.cleanup_errors
        if databases is not None:
            try:
                databases.ud.client.close()
            except Exception as problem:
                cleanup_errors.append(type(problem).__name__)
        try:
            after = capture_identity()
            _write_new_json(directory / "identity-after.json", after)
            if identity is not None and identity != after:
                error, code = error or "DriftError", code or 6
        except BaseException as problem:
            error, code = error or type(problem).__name__, code or failure_code(problem)
        if cleanup_errors:
            error, code = error or "CleanupError", code or 2
        business_wall = time.monotonic()-budget.started
        if business_wall > BUSINESS_SECONDS[mode] and mode != "full" and error is None:
            error, code = "BudgetError", 5
        run.update(complete=error is None, error=error, exit_code=code, utc_start=began,
            utc_end=datetime.now(timezone.utc).isoformat(), wall_seconds=time.monotonic()-budget.started,
            resource_samples=budget.samples, disk_bytes=sum(p.stat().st_size for p in directory.rglob("*")
                if p.is_file()), parent_ru_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            rss_scope="/proc samples of parent and registered cores; ru_maxrss is process lifetime",
            cleanup_errors=cleanup_errors, read_cleanup=dict(cancelled=0, reclaimed=0,
                unreclaimed=0, still_tracked=0, execution="serial main thread; no prefetch tasks"),
            source_days=len(sources), artifacts=_artifact_hashes(directory))
        run["wall_seconds"] = time.monotonic()-budget.started
        if run["wall_seconds"] > BUSINESS_SECONDS[mode] and mode != "full" and error is None:
            error, code = "BudgetError", 5
            run.update(complete=False, error=error, exit_code=code)
        if mode == "pilot" and run["complete"]:
            run["t4_admission"] = dict(status="DEVELOPER_ONLY_AWAIT_INDEPENDENT_PILOT",
                e_flow_seconds=math.ceil(1.5*99*run["wall_seconds"]+300),
                rule="ceil(1.5*99*max(developer_wall,independent_wall)+300)", flow_limit_seconds=10000)
        # Exact final byte count includes this manifest, without a self-referential hash.
        existing_bytes = sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
        for _ in range(5):
            size = existing_bytes+len((json.dumps(run, ensure_ascii=False, allow_nan=False, indent=2)+"\n").encode())
            if run["disk_bytes"] == size:
                break
            run["disk_bytes"] = size
        if run["disk_bytes"] > budget.disk_limit and error is None:
            error, code = "BudgetError", 5
            run.update(complete=False, error=error, exit_code=code)
        if error is not None:
            _write_new_json(directory / "failure.json", dict(error=error, exit_code=code))
        _write_new_json(directory / "run.json", run)
        budget.close()
    return code


class StrictParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise PreflightError(message)


def verify_run(directory: Path) -> dict:
    """Bind an existing complete run without importing acceptance-side code."""
    for component in (directory, *directory.parents):
        if component.is_symlink():
            raise PreflightError("symlink input run")
    run = strict_loads((directory / "run.json").read_text())
    if run.get("complete") is not True or run.get("exit_code") != 0 or run.get("data_qualified") is not True:
        raise PreflightError("unqualified prerequisite run")
    for name, expected in run["artifacts"].items():
        path = directory / name
        if ".." in Path(name).parts or path.is_symlink() or not path.is_relative_to(directory) or digest(path) != expected:
            raise DriftError("prerequisite artifact drift")
    identity = strict_loads((directory / "identity-start.json").read_text())
    if identity != strict_loads((directory / "identity-after.json").read_text()) or identity != capture_identity():
        raise DriftError("prerequisite candidate drift")
    return run


def full_preflight(args: argparse.Namespace) -> None:
    """Require two qualified pilots/vectors and conservative frozen flow/disk admission."""
    if (args.pilot_dir != EVIDENCE / "developer-pilot-v01" or
            args.independent_pilot_dir != EVIDENCE / "validate-pilot-v01" or
            type(args.remaining_seconds) is not int or not 0 < args.remaining_seconds <= 17377):
        raise PreflightError("full prerequisite arguments")
    pilots = []
    for path in (args.pilot_dir, args.independent_pilot_dir):
        run = verify_run(path)
        reference = strict_loads((path / "reference/run.json").read_text())
        if (reference.get("complete") is not True or reference.get("exit_code") != 0 or
                reference.get("source_run_sha256") != digest(path / "run.json") or
                strict_loads((path / "reference/reference.json").read_text()).get("passed") is not True):
            raise PreflightError("pilot vectors incomplete")
        for name, expected in reference["artifacts"].items():
            if digest(path / "reference" / name) != expected:
                raise DriftError("pilot reference drift")
        pilots.append(run)
    for name in ("params.json", "events.jsonl", "native-samples.csv", "samples.csv"):
        if digest(args.pilot_dir / name) != digest(args.independent_pilot_dir / name):
            raise PreflightError("pilots differ in parameters/input/native samples")
    estimate = math.ceil(1.5*99*max(run["wall_seconds"] for run in pilots)+300)
    disk = math.ceil(1.5*99*max(run["disk_bytes"] for run in pilots)) + 512*(1 << 20)
    free = os.statvfs(EVIDENCE)
    if (estimate > 10000 or estimate+1800+2400+300+800 > args.remaining_seconds or
            disk > 4*(1 << 30) or free.f_bavail*free.f_frsize < disk+512*(1 << 20)):
        raise PreflightError("full resource admission failed")


def publish(args: argparse.Namespace) -> int:
    """Render the sole report from immutable full raw and its independently bound audit."""
    if (args.source_dir != EVIDENCE / "full-v01" or args.evidence_dir != args.source_dir or
            args.audit_dir != EVIDENCE / "audit-v01" or args.report != EVIDENCE.parent / "report.md"):
        raise PreflightError("publish scope")
    for component in (args.report, *args.report.parents, args.audit_dir):
        if component.is_symlink():
            raise PreflightError("publish symlink")
    if args.report.exists():
        raise PreflightError("report already exists")
    run = verify_run(args.source_dir)
    if run.get("mode") != "full":
        raise PreflightError("publish requires the frozen full mode")
    audit_run = strict_loads((args.audit_dir / "run.json").read_text())
    audit_result = strict_loads((args.audit_dir / "reference.json").read_text())
    if (audit_run.get("complete") is not True or audit_run.get("exit_code") != 0 or
            audit_run.get("source_run_sha256") != digest(args.source_dir / "run.json") or
            audit_result.get("passed") is not True or audit_result.get("research_verdict") not in (
                "INSUFFICIENT_EVIDENCE", "HYPOTHESIS_NOT_SUPPORTED", "SUPPORT_FURTHER_VALIDATION")):
        raise PreflightError("independent audit not qualified")
    for name, expected in audit_run["artifacts"].items():
        if digest(args.audit_dir / name) != expected:
            raise DriftError("audit artifact drift")
    raw = strict_loads((args.source_dir / "statistics.json").read_text())
    parameters = strict_loads((args.source_dir / "parameters.json").read_text())
    bound = digest(args.source_dir / "run.json"), digest(args.audit_dir / "run.json")
    def number(value: Any) -> str:
        return "N/A" if value is None else f"{value:.8f}" if type(value) is float else str(value)
    def table(rows: list[dict], columns: tuple[str, ...]) -> str:
        return "\n".join(["|"+"|".join(columns)+"|", "|"+"|".join("---" for _ in columns)+"|"] +
            ["|"+"|".join(number(row.get(column)) for column in columns)+"|" for row in rows])
    columns = ("period", "offset", "stratum", "model", "reference", "metric", "numerator", "denominator", "value", "lo95", "hi95")
    m0 = [row for row in raw["rows"] if row["model"] == "M0" and row["comparison_set"] == "OWN" and row["period"] == "ALL"]
    m1 = [row for row in raw["rows"] if row["comparison_set"] == "C10" and row["offset"] == "ALL" and row["stratum"] in ("ALL", "COMPLETE_SIX")]
    h1 = [row for row in raw["rows"] if row["period"] == "VALIDATION" and row["comparison_set"] in ("C0B", "D02")]
    m2 = [row for row in raw["rows"] if row["comparison_set"] == "C2" and row["period"] in ("ALL", "VALIDATION", "LATEST")]
    metadata = {key: raw[key] for key in ("effect_size", "complexity_cost", "proxy_error", "economic_value_status")}
    effect = raw["effect_size"]
    metadata["effect_size"] = dict(difference=number(effect["difference"]),
        interval={key: number(value) for key, value in effect["interval"].items()}
        if effect["interval"] is not None else "N/A")
    metadata["complexity_cost"] = {key: number(value) if type(value) is float else value
        for key, value in raw["complexity_cost"].items()}
    text = "\n\n".join(["# BTC5m phase1 概率研究（99个UTC日）", "研究结论："+audit_result["research_verdict"],
        "来源与工程资格：Predict.fun官方身份/strike/标签；Binance Vision BTCUSDT 1秒成交close。"
        f"5秒闭合采样、event-time-proxy，非严格PIT或真实midpoint。三流完整消费与三核认证见{args.source_dir.relative_to(args.report.parent).as_posix()}。"
        "既有94日/旧OOS/末日观察构成研究者先验暴露，本轮为历史时间隔离验证而非盲测。",
        "## M0偏差诊断（先行）", table(m0, columns),
        "十桶mean_p/up_rate、六时点与因果sigma_raw层、floor命中与UTC日/月可加轮次损失见完整raw/CSV；"
        "(S/K−1)×10000为轮内价格参考差bps，不是同刻纯基差。",
        "![校准](evidence/full-v01/calibration.svg)", "## M1主要端点与冻结参数", table(m1, columns),
        "## H1次要概率与方向证据（共同分母）", table(h1, columns),
        json.dumps(parameters, ensure_ascii=False, indent=2), "## 稳健性诊断与冲突（不是采纳AND）",
        json.dumps(raw["diagnostic_conflicts"], ensure_ascii=False, indent=2),
        "7日circular块、各折/六时点、complete-six、logloss/ECE、日/月贡献和LODO详见raw/CSV；"
        "反向结果不隐藏，也不自动改主要端点分类。支持继续验证不表示替换M0。",
        "## M2完整探索（EXPLORATORY，未多重校正）", table(m2, columns),
        "![因果分层](evidence/full-v01/strata.svg)", "## 效应、复杂度、代理与经济适用性",
        json.dumps(metadata, ensure_ascii=False),
        "M1单调非减校准只拟合两个参数、九套窗口，可能移动0.5方向边界但没有增加市场特征。"
        "校准、方向信息与可交易价值分开；无同期midpoint，close-mid误差UNKNOWN，经济意义未验证。"
        "候选/成交/PnL/交易胜率/Sharpe/MDD等均N/A（NO_REAL_BOOK_EXECUTION）。"
        "1秒敏感性NOT_EXECUTED，不声称采样稳健。无可靠改善保留M0，M2不选冠军部署，不继续扩参。",
        f"绑定完整run SHA256：{bound[0]}；独立audit SHA256：{bound[1]}。完整业务wall：{run['wall_seconds']:.8f}秒。"])
    if bound != (digest(args.source_dir / "run.json"), digest(args.audit_dir / "run.json")):
        raise DriftError("publish inputs drifted")
    verify_run(args.source_dir)
    with args.report.open("x", encoding="utf-8") as stream:
        stream.write(text+"\n")
    return 0


def main(argv: list[str] | None = None, *, client: Any = None) -> int:
    """Parse frozen CLI; reject collisions before source/core invocation."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = StrictParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--mode", choices=("small", "pilot", "full", "publish"), required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    for name in ("source-dir", "audit-dir", "report", "pilot-dir", "independent-pilot-dir"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--remaining-seconds", type=int)
    try:
        args = parser.parse_args(arguments)
        for name in ("evidence_dir", "source_dir", "audit_dir", "report", "pilot_dir", "independent_pilot_dir"):
            path = getattr(args, name)
            if path is not None:
                if ".." in path.parts:
                    raise PreflightError("parent traversal forbidden")
                setattr(args, name, Path(os.path.abspath(path)))
        if args.as_of != "2026-11-17T15:00:00Z":
            raise PreflightError("as-of is frozen")
        publish_fields = (args.source_dir, args.audit_dir, args.report)
        full_fields = (args.pilot_dir, args.independent_pilot_dir, args.remaining_seconds)
        if args.mode != "publish" and any(value is not None for value in publish_fields):
            raise PreflightError("publish-only arguments")
        if args.mode != "full" and any(value is not None for value in full_fields):
            raise PreflightError("full-only arguments")
        if args.mode == "publish":
            return publish(args)
        if args.mode == "full":
            full_preflight(args)
        directory = claim_run(args.evidence_dir, args.mode)
    except (PreflightError, DriftError, OSError) as error:
        print(f"phase1 preflight refused: {type(error).__name__}", file=sys.stderr)
        return 6 if isinstance(error, DriftError) else 64
    invocation = list(sys.orig_argv) if argv is None else [sys.executable, "-B",
        str(LAB / "phase1_model_research.py"), *arguments]
    code = run_phase1(directory, args.mode, invocation, client=client,
                      remaining_seconds=args.remaining_seconds)
    print(json.dumps(dict(mode=args.mode, exit_code=code, evidence_dir=str(directory))))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
