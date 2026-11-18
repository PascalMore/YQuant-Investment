"""Independent acceptance-side mathematics and immutable-artifact audit CLI.

No production research/statistics imports, database, network or subprocesses.
Developer execution is self-test, not an independent reviewer acceptance.
"""
from __future__ import annotations

import math
import argparse
import csv
import hashlib
import importlib.metadata
import itertools
import json
import os
import resource
import signal
import sys
import time
from contextlib import ExitStack
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

import numpy as np

ROOT = Path(__file__).resolve().parents[6]
EVIDENCE = ROOT / "data/reports/2026-11-18-btc5m-phase1-model-research/evidence"
FLOORS = {"M0": .00005, "M2-low": .000025, "M2-high": .0001}


@dataclass
class ReferenceState:
    """Independent scalar state; first price is not a return."""

    source: tuple[str, str] | None = None
    epoch: int = 0
    reset_reason: str = "NONE"
    previous_price: float | None = None
    previous_us: int | None = None
    variance: float | None = None
    samples: int = 0

    def observe(self, payload: dict[str, Any], at_us: int) -> None:
        """Update the frozen five-second sequence using actual return duration."""
        price = payload["price"]
        key = (payload["prediction_source"], payload["actual_pair"])
        if not math.isfinite(price) or price <= 0:
            raise ValueError("invalid reference price")
        if self.previous_us is not None and at_us <= self.previous_us:
            raise ValueError("nonmonotonic reference clock")
        reason = None
        if self.source is None:
            reason = "FIRST_SAMPLE"
        elif self.source != key:
            reason = "SOURCE_SWITCH"
        elif self.previous_us is not None and at_us - self.previous_us > 300_000_000:
            reason = "LONG_GAP"
        if reason is not None:
            self.epoch += 1
            self.reset_reason = reason
            self.previous_price = self.previous_us = self.variance = None
            self.samples = 0
        if self.previous_price is not None and self.previous_us is not None:
            seconds = (at_us - self.previous_us) / 1_000_000
            sample = math.log(price / self.previous_price) ** 2 / seconds
            weight = 1 - math.pow(.5, seconds / 300)
            self.variance = sample if self.variance is None else self.variance + weight * (sample - self.variance)
            self.samples += 1
        self.source, self.previous_price, self.previous_us = key, price, at_us


def normal_as(value: float) -> float:
    """Independent A&S expression, distinct from the erf comparison."""
    positive = abs(value)
    inverse = 1 / (1 + .2316419 * positive)
    polynomial = sum(coefficient * inverse ** power for power, coefficient in enumerate(
        (.319381530, -.356563782, 1.781477937, -1.821255978, 1.330274429), start=1))
    tail = math.exp(-positive * positive / 2) * polynomial / math.sqrt(2 * math.pi)
    return tail if value < 0 else 1 - tail


def probabilities(spot: float, strike: float, sigma: float, seconds: float) -> tuple[float, float]:
    """Return same-A&S and separate exact-erf probabilities."""
    if seconds <= 0 or sigma <= 0:
        result = 1. if spot > strike else 0. if spot < strike else .5
        return result, result
    total = sigma * math.sqrt(seconds)
    score = math.log(spot / strike) / total - total / 2
    return normal_as(score), .5 * (1 + math.erf(score / math.sqrt(2)))


def reference_value(state: ReferenceState, event: dict[str, Any], floor: float) -> dict[str, Any]:
    """Reconstruct numerical value and rejection order without a native core."""
    facts, at = event["payload"], event["at_us"]
    result: dict[str, Any] = dict(samples=state.samples, source_epoch=state.epoch or None,
        reset_reason=state.reset_reason, sigma_raw=None, sigma=None, floor_hit=None,
        p_up=None, p_erf=None, secs_left=None)
    ends, starts = facts["ends_at_us"], facts["starts_at_us"]
    if ends is not None:
        result["secs_left"] = (ends - at) / 1_000_000
    if any(facts[field] is None for field in ("round_id", "identity_available_at_us", "starts_at_us", "ends_at_us")):
        status = "MISSING_IDENTITY"
    elif facts["identity_available_at_us"] > at:
        status = "IDENTITY_NOT_AVAILABLE"
    elif ends - starts != 300_000_000 or starts != facts["planned_start_us"] or starts > at or ends - at < 30_000_000:
        status = "ROUND_INVALID"
    elif facts["strike"] is None or facts["strike_available_at_us"] is None:
        status = "MISSING_STRIKE"
    elif facts["strike_available_at_us"] > at:
        status = "STRIKE_NOT_AVAILABLE"
    elif facts["strike_available_at_us"] < starts:
        status = "ROUND_INVALID"
    elif state.previous_us != at:
        status = "MISSING_SPOT"
    elif state.samples < 20:
        status = "WARMUP"
    else:
        assert state.variance is not None and state.previous_price is not None
        raw = math.sqrt(state.variance)
        sigma = max(raw, floor)
        probability, exact = probabilities(state.previous_price, facts["strike"], sigma, result["secs_left"])
        result.update(sigma_raw=raw, sigma=sigma, floor_hit=raw <= floor, p_up=probability, p_erf=exact)
        status = "VALUED"
    result["valuation_status"] = status
    return result


def check_vectors(events: Iterable[dict[str, Any]],
                  native_rows: dict[str, Iterator[dict[str, Any]]],
                  floors: dict[str, float], *, sink: Any = None,
                  check: Any = lambda: None) -> dict[str, Any]:
    """Independently replay every event and consume each raw value exactly once.

    This pure boundary checks mathematics, state and value keys, not facade
    authentication, startup identity or the source run's complete flag. The
    caller must perform those independent engineering gates separately.
    """
    state = ReferenceState()
    rows, valued = 0, 0
    max_as_error = max_erf_error = 0.
    for event in events:
        check()
        if event["payload"]["type"] == "spot":
            state.observe(event["payload"], event["at_us"])
            continue
        rows += 1
        for model, floor in floors.items():
            native = next(native_rows[model], None)
            if native is None:
                raise ValueError("missing native vector")
            payload = event["payload"]
            for key in ("planned_start_us", "offset", "round_id", "starts_at_us", "ends_at_us",
                        "identity_available_at_us", "strike_available_at_us", "strike"):
                if native[key] != payload[key]:
                    raise ValueError(f"vector identity mismatch: {key}")
            if native["seq"] != event["seq"] or native["at_us"] != event["at_us"]:
                raise ValueError("vector sequence mismatch")
            expected = reference_value(state, event, floor)
            for key, value in expected.items():
                if key == "p_erf":
                    continue
                actual = native[key]
                if value is None or type(value) in (str, int, bool):
                    if type(actual) is not type(value) or actual != value:
                        raise ValueError(f"vector exact mismatch: {key}")
                elif actual is None or not math.isfinite(actual) or not math.isclose(actual, value, abs_tol=1e-12, rel_tol=1e-9):
                    raise ValueError(f"vector numerical mismatch: {key}")
            if expected["p_up"] is not None:
                valued += 1
                error = abs(native["p_up"] - expected["p_up"])
                exact_error = abs(native["p_up"] - expected["p_erf"])
                max_as_error, max_erf_error = max(max_as_error, error), max(max_erf_error, exact_error)
                if exact_error > 2e-7:
                    raise ValueError("A&S/erf tolerance exceeded")
            if sink is not None:
                sink(dict(model=model, seq=event["seq"], at_us=event["at_us"],
                    floor=floor, status=native["valuation_status"], samples=native["samples"],
                    source_epoch=native["source_epoch"], reset_reason=native["reset_reason"],
                    sigma_raw=native["sigma_raw"], sigma=native["sigma"],
                    native_p=native["p_up"], reference_p=expected["p_up"], erf_p=expected["p_erf"]))
    if not rows or not valued:
        raise ValueError("empty numerical vectors")
    if any(next(stream, None) is not None for stream in native_rows.values()):
        raise ValueError("extra native vector")
    return dict(slots=rows, valued_model_vectors=valued,
        max_same_as_error=max_as_error, max_erf_error=max_erf_error)


class Refusal(ValueError):
    """Invalid argument/path or unowned output (64)."""


class Mismatch(ValueError):
    """Mathematical/structural acceptance failure (4)."""


class Drift(Mismatch):
    """Source run or candidate identity changed (6)."""


def _pairs(pairs: list) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise Mismatch("duplicate JSON field")
        result[name] = value
    return result


def _nonfinite(value: str) -> None:
    raise Mismatch("nonfinite JSON")


def load(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=_pairs, parse_constant=_nonfinite)


def lines(path: Path) -> Iterator[dict]:
    with path.open("rb") as stream:
        for line in stream:
            if len(line) > 65536 or not line.endswith(b"\n"):
                raise Mismatch("bad framing")
            yield json.loads(line, object_pairs_hook=_pairs, parse_constant=_nonfinite)


def sha(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def save(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def plain_path(path: Path) -> Path:
    if ".." in path.parts:
        raise Refusal("path traversal")
    path = Path(os.path.abspath(path))
    for component in (path, *path.parents):
        if component.is_symlink():
            raise Refusal("symlink artifact path")
    return path


def bind_source(source: Path) -> dict:
    """Check the exact complete run and all capture-time file hashes before claiming output."""
    run = load(source / "run.json")
    if run.get("complete") is not True or run.get("exit_code") != 0 or run.get("data_qualified") is not True:
        raise Mismatch("source run is not qualified/complete")
    identity = load(source / "identity-start.json")
    if load(source / "identity-after.json") != identity:
        raise Drift("capture-time candidate drift")
    for name, expected in identity["files"].items():
        path = plain_path(ROOT / name)
        if not path.is_relative_to(ROOT) or sha(path) != expected:
            raise Drift("current candidate differs from captured candidate")
    if {name: importlib.metadata.version(name) for name in identity["dependencies"]} != identity["dependencies"]:
        raise Drift("dependency drift")
    for name, expected in run["artifacts"].items():
        path = plain_path(source / name)
        if not path.is_relative_to(source) or sha(path) != expected:
            raise Drift("source artifact drift")
    transport = run["transport"]
    if len(transport["cores"]) != 3 or not transport["complete"]:
        raise Mismatch("native batch incomplete")
    chains = set()
    for core in transport["cores"]:
        summary = load(source / "cores" / core["name"] / "rust-summary.json")
        if (not core["reaped"] or type(core["native_exit"]) is not int or core["native_exit"] != 0
                or summary != core["summary"] or summary["values"] != transport["values"]
                or summary["accepted_events"] != transport["events"]):
            raise Mismatch("native identity/count/exit mismatch")
        chains.add(summary["input_chain_keccak256"])
    if len(chains) != 1 or sha(source / "events.jsonl") != transport["event_sha256"]:
        raise Mismatch("shared input identity mismatch")
    return dict(run_sha256=sha(source / "run.json"), artifacts=run["artifacts"],
        source_identity=identity, reference_sha256=sha(Path(__file__)), executable=sys.executable)


class RefBudget:
    """Independent read-only computation budget; writes only its newly owned leaf."""

    def __init__(self, directory: Path, seconds: float):
        self.directory, self.started = directory, time.monotonic()
        self.deadline = self.started + seconds
        self.samples = []
        self.last = -math.inf
        self.handlers = {}

    def check(self, *unused: Any) -> None:
        now = time.monotonic()
        if now >= self.deadline:
            raise TimeoutError("reference deadline")
        if now-self.last < .5:
            return
        self.last = now
        with Path(f"/proc/{os.getpid()}/status").open() as source:
            rss_line = next(line for line in source if line.startswith("VmRSS:"))
        rss = int(rss_line.split()[1])
        size = sum(path.stat().st_size for path in self.directory.rglob("*") if path.is_file())
        self.samples.append(dict(elapsed=now-self.started, rss_kib=rss, written_bytes=size))
        if rss > 512*1024 or size > 128*(1 << 20):
            raise TimeoutError("reference resource cap")

    def start(self) -> None:
        for number in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM):
            self.handlers[number] = signal.getsignal(number)
            signal.signal(number, self.check if number == signal.SIGALRM else self.cancel)
        signal.setitimer(signal.ITIMER_REAL, .5, .5)

    def cancel(self, *unused: Any) -> None:
        raise KeyboardInterrupt()

    def close(self) -> None:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for number, handler in self.handlers.items():
            signal.signal(number, handler)


def decoded_csv(path: Path) -> Iterator[dict]:
    """Acceptance-side schema decoder, independent of production CSV helpers."""
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            for key, value in row.items():
                if value == "N/A":
                    row[key] = None
                elif key.endswith("floor_hit"):
                    if value not in ("true", "false"):
                        raise Mismatch("invalid raw boolean")
                    row[key] = value == "true"
                elif key.endswith(("_us", "_seq")) or key in ("seq", "fold", "offset", "samples", "source_epoch", "logical_elapsed_ms") or key.endswith(("_samples", "_source_epoch")):
                    row[key] = int(value)
                elif key in ("strike", "spot", "secs_left", "p_up", "sigma", "sigma_raw") or key.endswith(("_p_up", "_sigma", "_sigma_raw")):
                    row[key] = float(value)
            yield row


def equal(actual: Any, expected: Any, *, abs_tol: float = 1e-12, rel_tol: float = 1e-9) -> None:
    """Exact identities/statuses; tight numeric comparison without display rounding."""
    if type(expected) is float:
        if type(actual) not in (int, float) or not math.isfinite(actual) or not math.isclose(actual, expected, abs_tol=abs_tol, rel_tol=rel_tol):
            raise Mismatch("independent numerical mismatch")
    elif type(actual) is not type(expected) or actual != expected:
        raise Mismatch("independent exact mismatch")


def independent_fit(paths: list[Path], cutoff: int, as_of: int,
                    check: Any = lambda: None) -> dict:
    """Independent analytic 2x2 Newton/KKT solution, one read-only day map at a time."""
    def batches() -> Iterator[tuple]:
        for path in sorted(paths):
            check()
            mapped = np.load(path, mmap_mode="r", allow_pickle=False)
            try:
                selected = mapped[(mapped["valued"]) & (mapped["at_us"] < cutoff) &
                    (mapped["ends_at_us"] <= cutoff) & (mapped["label_available_at_us"] >= 0) &
                    (mapped["label_available_at_us"] <= min(cutoff, as_of)) &
                    ((mapped["label_code"] == 0) | (mapped["label_code"] == 1))]
                if len(selected):
                    _, counts = np.unique(selected["planned_start_us"], return_counts=True)
                    weights = np.concatenate([np.full(int(count), 1/count) for count in counts])
                    clipped = np.minimum(1-1e-12, np.maximum(1e-12, selected["p0"]))
                    yield np.log(clipped)-np.log1p(-clipped), selected["label_code"].astype(float), weights, selected
            finally:
                mapped._mmap.close()
    slots = rounds = positives = 0
    input_hash = hashlib.sha256()
    first_at = last_at = latest_label = None
    for logits, labels, weights, selected in batches():
        slots += len(labels)
        rounds += int(round(float(weights.sum())))
        positives += int(labels.sum())
        input_hash.update(selected.tobytes())
        first_at = min(first_at, int(selected["at_us"].min())) if first_at is not None else int(selected["at_us"].min())
        last_at = max(last_at or 0, int(selected["at_us"].max()))
        latest_label = max(latest_label or 0, int(selected["label_available_at_us"].max()))
    def evaluate(slope: float, intercept: float) -> tuple:
        objective = .0005*((slope-1)**2+intercept**2)
        ga, gb = .001*(slope-1), .001*intercept
        aa, ab, bb = .001, 0., .001
        for logits, labels, weights, _ in batches():
            weights = weights/rounds
            score = slope*logits+intercept
            prob = np.empty_like(score)
            positive = score >= 0
            prob[positive] = 1/(1+np.exp(-score[positive]))
            exponent = np.exp(score[~positive])
            prob[~positive] = exponent/(1+exponent)
            objective += float(np.dot(weights, np.maximum(score, 0)+np.log1p(np.exp(-np.abs(score)))-labels*score))
            residual = weights*(prob-labels)
            curvature = weights*prob*(1-prob)
            ga += float(residual @ logits)
            gb += float(residual.sum())
            aa += float(curvature @ (logits*logits))
            ab += float(curvature @ logits)
            bb += float(curvature.sum())
        return objective, ga, gb, aa, ab, bb
    record = dict(fit_status="FIT_EMPTY" if not slots else "FIT_SINGLE_CLASS",
                  a=None, b=None, slot_count=slots, unique_rounds=rounds,
                  up_count=positives, down_count=slots-positives, evaluate=evaluate,
                  input_hash=input_hash.hexdigest(), latest_label_available_at_us=latest_label,
                  prediction_range_us=dict(first_at_us=first_at, last_at_us=last_at) if slots else None)
    if not slots or positives in (0, slots):
        return record
    slope, intercept = 1., 0.
    for iteration in range(500):
        objective, ga, gb, aa, ab, bb = evaluate(slope, intercept)
        pg = max(abs(slope-max(0., slope-ga)), abs(gb))
        if pg <= 1e-8:
            return dict(record, fit_status="FIT_OK", a=slope, b=intercept,
                        objective=objective, projected_gradient=pg)
        if slope == 0 and ga >= 0:
            da, db = 0., -gb/bb
        else:
            determinant = aa*bb-ab*ab
            da, db = (-ga*bb+gb*ab)/determinant, (-gb*aa+ga*ab)/determinant
        if ga*da+gb*db >= 0:
            da, db = max(0., slope-ga)-slope, -gb
        for backtrack in range(50):
            step = math.ldexp(1., -backtrack)
            candidate_a, candidate_b = max(0., slope+step*da), intercept+step*db
            delta = ga*(candidate_a-slope)+gb*(candidate_b-intercept)
            if delta < 0 and evaluate(candidate_a, candidate_b)[0] <= objective+1e-4*delta:
                slope, intercept = candidate_a, candidate_b
                break
        else:
            break
    return dict(record, fit_status="FIT_NOT_CONVERGED")


OFFSETS = (30, 60, 120, 180, 240, 270)
MODELS = ("M0", "M1", "M2-low", "M2-high", "B0", "B1", "B2")
DAY = 86_400_000_000
C0 = int(datetime.fromisoformat("2026-09-21T00:00:00+00:00").timestamp())*1_000_000
STRATA = (("[0,0.000025)", 0., .000025), ("[0.000025,0.00005)", .000025, .00005),
          ("[0.00005,0.0001)", .00005, .0001), ("[0.0001,+inf)", .0001, math.inf))


def reference_logloss(probability: float, label: str) -> float:
    probability = max(1e-12, min(1-1e-12, probability))
    return -(math.log(probability) if label == "UP" else math.log1p(-probability))


def reference_abstain(row: dict, m0_row: dict) -> int:
    """SPEC-06-003 4.6.2 abstain rule, written from the contract alone.

    A probability model abstains only when it carries a legal probability
    exactly equal to 0.5.  B2 has no probability: it abstains only on a legal
    slot whose spot and strike were both already available at the observation
    time and are exactly equal.  Warmup, failed fit, not applicable and
    missing-price slots keep their own counters and never abstain.
    """
    if row["model"] == "B2":
        if m0_row["valuation_status"] not in ("VALUED", "WARMUP"):
            return 0
        spot, strike = row.get("spot"), row.get("strike")
        spot_at, strike_at = row.get("spot_available_at_us"), row.get("strike_available_at_us")
        at_us = row.get("at_us")
        if spot is None or strike is None or spot_at is None or strike_at is None or at_us is None:
            return 0
        if spot_at > at_us or strike_at > at_us:
            return 0
        return int(spot == strike)
    probability = row.get("p_up")
    return int(probability is not None and probability == .5)


def reference_reduction(sample_rows: Iterable[dict], as_of: int,
                        check: Any = lambda: None) -> tuple:
    """Reconstruct round/day numerators and buckets directly from raw seven-model rows."""
    losses = defaultdict(dict)
    buckets = defaultdict(dict)
    coverage = {model: defaultdict(int) for model in MODELS}
    def add(key: tuple, day: str, values: list) -> None:
        aggregate = losses[key].setdefault(day, [0., 0, 0])
        if values:
            aggregate[0] += math.fsum(values)/len(values)
            aggregate[1] += 1
            aggregate[2] += len(values)
    def calibrate(key: tuple, day: str, members: list) -> None:
        output = buckets[key].setdefault(day, np.zeros((10, 5)))
        counts = defaultdict(int)
        for member in members:
            probability = member["p_up"]
            index = min(9, math.floor(probability*10))
            output[index, 0] += 1/len(members)
            output[index, 1] += probability/len(members)
            output[index, 2] += int(member["label"] == "UP")/len(members)
            output[index, 3] += 1
            counts[index] += 1
        for index in counts:
            output[index, 4] += 1
    from datetime import datetime, timezone
    for planned, group in itertools.groupby(sample_rows, lambda row: row["planned_start_us"]):
        check()
        day = datetime.fromtimestamp(planned/1_000_000, timezone.utc).date().isoformat()
        by_slot = defaultdict(dict)
        for row in group:
            if row["model"] in by_slot[row["offset"]]:
                raise Mismatch("duplicate slot/model")
            by_slot[row["offset"]][row["model"]] = row
        for offset in sorted(by_slot):
            slot = by_slot[offset]
            for model in MODELS:
                row = slot[model]
                count = coverage[model]
                known = row["label_available_at_us"] is not None and row["label_available_at_us"] <= as_of
                binary = known and row["label"] in ("UP", "DOWN")
                quantities = dict(theoretical_slots=1, observed_identity=int(row["round_id"] is not None),
                    valid_probability=int(row["p_up"] is not None), known_label=int(known),
                    binary_scored=int(binary and row["p_up"] is not None),
                    draw_label=int(known and row["label"] == "DRAW"),
                    draw_scored=int(known and row["label"] == "DRAW" and row["p_up"] is not None),
                    missing_label=int(not known), unvalued=int(row["p_up"] is None),
                    directed=int(row["direction"] is not None),
                    abstain=reference_abstain(row, slot["M0"]),
                    correct=int(binary and row["direction"] == row["label"]))
                quantities[f"reason:{row['valuation_status']}"] = 1
                for name, value in quantities.items():
                    count[name] += value
        if set(by_slot) != set(OFFSETS) or any(set(slot) != set(MODELS) for slot in by_slot.values()):
            raise Mismatch("incomplete round/model matrix")
        matrix = [by_slot[offset] for offset in OFFSETS]
        for model in MODELS:
            valid = sum(slot[model]["p_up"] is not None for slot in matrix)
            coverage[model]["theoretical_rounds"] += 1
            coverage[model]["zero_probability_rounds"] += int(valid == 0)
            coverage[model]["complete_six_probability_rounds"] += int(valid == 6)
        first = matrix[0]["M0"]
        periods = ["ALL"] + (["VALIDATION", f"FOLD_{first['fold']}"] if first["period"] == "VALIDATION" else
                              ["LATEST"] if first["period"] == "LATEST" else [])
        groups = [("ALL", "ALL", matrix)] + [(offset, "ALL", [by_slot[offset]]) for offset in OFFSETS]
        groups += [("ALL", name, [slot for slot in matrix if slot["M0"]["sigma_raw"] is not None
                    and lower <= slot["M0"]["sigma_raw"] < upper]) for name, lower, upper in STRATA]
        for period in periods:
            for offset, stratum, selected in groups:
                for model in MODELS:
                    own = [slot[model] for slot in selected]
                    known = [row for row in own if row["label_available_at_us"] is not None
                             and row["label_available_at_us"] <= as_of]
                    binary = [row for row in known if row["label"] in ("UP", "DOWN") and row["p_up"] is not None]
                    prefix = (period, offset, stratum, model, "N/A", "OWN")
                    add((*prefix, "binary_brier"), day, [(row["p_up"]-int(row["label"] == "UP"))**2 for row in binary])
                    add((*prefix, "binary_logloss"), day, [reference_logloss(row["p_up"], row["label"]) for row in binary])
                    add((*prefix, "payout_mse"), day, [(row["p_up"]-{"UP": 1., "DOWN": 0., "DRAW": .5}[row["label"]])**2
                        for row in known if row["p_up"] is not None and row["label"] in ("UP", "DOWN", "DRAW")])
                    add((*prefix, "direction_accuracy"), day, [float(row["direction"] == row["label"])
                        for row in known if row["direction"] is not None and row["label"] in ("UP", "DOWN")])
                    calibrate(prefix, day, binary)
                    if model in FLOORS:
                        add((*prefix, "floor_share"), day, [float(row["sigma_raw"] <= FLOORS[model])
                            for row in own if row["sigma_raw"] is not None])
                    if model == "M0":
                        add((*prefix, "reference_difference_bps"), day, [(row["spot"]/row["strike"]-1)*10000
                            for row in own if row["spot"] is not None and row["strike"] is not None])
                configurations = [("C0B", "M0", "B0", ("M0", "B0", "B1")),
                    ("C0B", "M0", "B1", ("M0", "B0", "B1")),
                    ("C2", "M2-low", "M0", tuple(FLOORS)), ("C2", "M2-high", "M0", tuple(FLOORS))]
                if period != "ALL":
                    configurations += [("C10", "M1", "M0", ("M0", "M1"))]
                seen_buckets = set()
                for comparison, left, right, required in configurations:
                    common = [slot for slot in selected if all(slot[model]["p_up"] is not None for model in required)
                        and slot[left]["label_available_at_us"] is not None and slot[left]["label_available_at_us"] <= as_of]
                    for metric in ("binary_brier", "binary_logloss", "payout_mse"):
                        differences = []
                        for slot in common:
                            label = slot[left]["label"]
                            if label not in ("UP", "DOWN", "DRAW") or label == "DRAW" and metric != "payout_mse":
                                continue
                            def loss(probability: float) -> float:
                                if metric == "binary_logloss":
                                    return reference_logloss(probability, label)
                                return (probability-{"UP": 1, "DOWN": 0, "DRAW": .5}[label])**2
                            differences.append(loss(slot[left]["p_up"])-loss(slot[right]["p_up"]))
                        add((period, offset, stratum, left, right, comparison, metric+"_difference"), day, differences)
                        if comparison == "C10" and offset == stratum == "ALL":
                            add((period, offset, "COMPLETE_SIX", left, right, comparison, metric+"_difference"),
                                day, differences if len(differences) == 6 else [])
                    for model in (left, right):
                        key = (period, offset, stratum, model, right, comparison)
                        if key not in seen_buckets:
                            calibrate(key, day, [slot[model] for slot in common if slot[model]["label"] in ("UP", "DOWN")])
                            seen_buckets.add(key)
                directions = []
                for slot in selected:
                    left, right = slot["M0"], slot["B2"]
                    if (left["direction"] is not None and right["direction"] is not None and
                        left["label"] in ("UP", "DOWN") and left["label_available_at_us"] is not None and
                        left["label_available_at_us"] <= as_of):
                        directions.append(float(left["direction"] == left["label"])-float(right["direction"] == right["label"]))
                add((period, offset, stratum, "M0", "B2", "D02", "direction_accuracy_difference"), day, directions)
    return losses, buckets, {model: dict(count, probability_coverage=count["valid_probability"]/count["theoretical_slots"]
        if count["theoretical_slots"] else None) for model, count in coverage.items()}


def audit_samples(source: Path, fits: dict, check: Any, ref_fits: Any = None) -> dict:
    """Rebuild source/native/model/fit-day linkage without calling the producer."""
    samples = iter(decoded_csv(source / "samples.csv"))
    contexts = iter(lines(source / "contexts.jsonl"))
    values = {model: iter(lines(source / "cores" / model / "values.jsonl")) for model in FLOORS}
    count = 0
    maximum_gap = 0.
    identical = True
    params = load(source / "params.json")
    for day, group in itertools.groupby(decoded_csv(source / "native-samples.csv"), lambda row: row["planned_start_us"]//DAY):
        check()
        mapped = np.load(source / "fit-days" / f"{datetime.fromtimestamp(day*86400, timezone.utc).date()}.npy",
                         mmap_mode="r", allow_pickle=False)
        try:
            day_count = 0
            for wide in group:
                equal(wide["planned_start_us"], params["start_us"]+(count//6)*300_000_000)
                equal(wide["offset"], OFFSETS[count%6])
                equal(wide["at_us"], wide["planned_start_us"]+wide["offset"]*1_000_000)
                context = next(contexts)
                for key, expected in context.items():
                    equal(wide[key], expected, abs_tol=0., rel_tol=0.)
                native = {}
                for model, iterator in values.items():
                    row = next(iterator)
                    native[model] = row
                    prefix = {"M0": "m0", "M2-low": "m2_low", "M2-high": "m2_high"}[model]
                    for key, expected in row.items():
                        name = f"{prefix}_{key}" if key in ("source_epoch", "reset_reason", "samples", "sigma_raw", "sigma", "floor_hit", "p_up", "valuation_status") else key
                        if key in ("sigma", "floor_hit", "p_up") and model != "M0":
                            name = f"{prefix}_{key}"
                        equal(wide[name], expected, abs_tol=0., rel_tol=0.)
                    equal(wide[f"{prefix}_value_seq"], row["seq"])
                    equal(row["seq"], (row["at_us"]-params["start_us"])//5_000_000+count)
                    equal(row["samples"], (row["at_us"]-params["start_us"])//5_000_000-1)
                    equal(row["source_epoch"], 1)
                    equal(row["reset_reason"], "FIRST_SAMPLE")
                entry = mapped[day_count]
                for field in ("planned_start_us", "offset", "at_us", "ends_at_us", "label_available_at_us"):
                    equal(int(entry[field]), wide[field] if wide[field] is not None else -1)
                equal(float(entry["p0"]), wide["m0_p_up"] if wide["m0_p_up"] is not None else 0.)
                equal(bool(entry["valued"]), wide["m0_p_up"] is not None)
                equal(int(entry["label_code"]), {"UP": 1, "DOWN": 0, "DRAW": 2}.get(wide["label"], -1))
                day_count += 1
                fold = None if wide["at_us"] < C0 else min(8, (wide["at_us"]-C0)//(7*DAY))
                expected_period = "TRAIN_PREFIX" if fold is None else "LATEST" if fold == 8 else "VALIDATION"
                for model in MODELS:
                    row = next(samples)
                    expected = {field: wide.get(field) for field in row}
                    expected.update(schema_version="btc5m-phase1-samples/1", model=model, period=expected_period,
                                    fold=fold, parameter_ref=None, fit_status=None)
                    parent = "M0" if model == "M1" else model
                    for field in ("source_epoch", "reset_reason", "samples", "sigma_raw", "sigma", "floor_hit", "p_up", "valuation_status"):
                        expected[field] = native[parent][field] if parent in native else None
                    if model not in FLOORS and model != "M1":
                        expected["valuation_status"] = "NOT_APPLICABLE"
                    if model in ("M1", "B1"):
                        frozen = fits.get(str(fold), {})
                        expected["parameter_ref"] = f"parameters.json#{fold}" if frozen else None
                        if model == "B1":
                            expected["p_up"] = frozen.get("b1", {}).get("value")
                        else:
                            fit = frozen.get("m1", {})
                            expected["fit_status"] = fit.get("fit_status", "NOT_APPLICABLE")
                            probability = native["M0"]["p_up"]
                            if fit.get("fit_status") == "FIT_OK" and probability is not None:
                                clipped = max(1e-12, min(1-1e-12, probability))
                                score = fit["a"]*(math.log(clipped)-math.log1p(-clipped))+fit["b"]
                                expected["p_up"] = 1/(1+math.exp(-score)) if score >= 0 else math.exp(score)/(1+math.exp(score))
                                if ref_fits is not None:
                                    independently_fitted = ref_fits[str(fold)]
                                    independent_score = independently_fitted["a"]*(math.log(clipped)-math.log1p(-clipped))+independently_fitted["b"]
                                    independent_probability = (1/(1+math.exp(-independent_score)) if independent_score >= 0
                                        else math.exp(independent_score)/(1+math.exp(independent_score)))
                                    equal(row["p_up"], independent_probability, abs_tol=1e-6, rel_tol=0.)
                            else:
                                expected["p_up"] = None
                    elif model == "B0":
                        expected["p_up"] = .5
                    probability = expected["p_up"]
                    direction = "UP" if probability is not None and probability > .5 else (
                        "DOWN" if probability is not None and probability < .5 else None)
                    if model == "B2" and native["M0"]["valuation_status"] in ("VALUED", "WARMUP"):
                        direction = "UP" if wide["spot"] > wide["strike"] else "DOWN" if wide["spot"] < wide["strike"] else None
                    expected["direction"] = direction
                    for key in row:
                        equal(row[key], expected[key])
                    if expected_period == "VALIDATION" and model == "M1" and row["p_up"] is not None and wide["label"] in ("UP", "DOWN"):
                        gap = abs(row["p_up"]-native["M0"]["p_up"])
                        maximum_gap = max(maximum_gap, gap)
                        identical &= math.isclose(row["p_up"], native["M0"]["p_up"], abs_tol=1e-12, rel_tol=1e-9)
                count += 1
            equal(day_count, len(mapped))
        finally:
            mapped._mmap.close()
    if next(samples, None) is not None or next(contexts, None) is not None or any(next(iterator, None) is not None for iterator in values.values()):
        raise Mismatch("extra source/native/sample record")
    equal(count, (params["end_us"]-params["start_us"])//300_000_000*6)
    return dict(slots=count, identical=identical, max_abs_probability_gap=maximum_gap)


def audit_statistics(source: Path, check: Any = lambda: None) -> dict:
    """Independent source-sample reductions, bootstrap, buckets, carriers and verdict."""
    params = load(source / "params.json")
    raw = load(source / "statistics.json")
    losses, buckets, coverage = reference_reduction(decoded_csv(source / "samples.csv"), params["as_of_us"], check)
    equal(raw["coverage"], coverage)
    def days_for(period: str) -> list[str]:
        first, last = params["start_us"]//DAY, (params["end_us"]-1)//DAY+1
        if period == "VALIDATION":
            first, last = C0//DAY, C0//DAY+56
        elif period == "LATEST":
            first, last = C0//DAY+56, C0//DAY+57
        elif period.startswith("FOLD_"):
            first = C0//DAY+int(period.split("_")[1])*7
            last = first+7
        return [datetime.fromtimestamp(day*86400, timezone.utc).date().isoformat() for day in range(first, last)]
    def interval(numerators: np.ndarray, denominators: np.ndarray, index: np.ndarray) -> dict:
        den = denominators[index].sum(axis=1)
        num = numerators[index].sum(axis=1)
        valid = den > 0
        values = num[valid]/den[valid]
        return dict(lo95=float(np.quantile(values, .025, method="linear")) if len(values) else None,
            hi95=float(np.quantile(values, .975, method="linear")) if len(values) else None,
            valid_replicates=int(valid.sum()), invalid_replicates=int((~valid).sum()))
    with np.load(source / "bootstrap.npz", allow_pickle=False) as saved:
        expected_indices = {}
        for period in {key[0] for key in losses}:
            days = days_for(period)
            equal(raw["bootstrap"][period]["days"], days)
            equal(raw["bootstrap"][period]["day_order_sha256"],
                  hashlib.sha256(json.dumps(days, separators=(",", ":")).encode()).hexdigest())
            expected_indices[period+"_day"] = np.random.Generator(np.random.PCG64(42)).integers(
                0, len(days), size=(1000, len(days)), dtype=np.int64)
            if len(days) > 7:
                starts = np.random.Generator(np.random.PCG64(42)).integers(0, len(days),
                    size=(1000, (len(days)+6)//7), dtype=np.int64)
                expected_indices[period+"_seven"] = np.concatenate(
                    [(starts[:, index, None]+np.arange(7)) % len(days) for index in range(starts.shape[1])], axis=1)[:, :len(days)]
        if set(saved.files) != set(expected_indices) or any(saved[key].dtype != np.int64 or not np.array_equal(saved[key], value)
                for key, value in expected_indices.items()):
            raise Mismatch("bootstrap index mismatch")
    expected_rows = {}
    for key, quantities in losses.items():
        check()
        days = days_for(key[0])
        num = np.array([quantities.get(day, (0, 0, 0))[0] for day in days])
        den = np.array([quantities.get(day, (0, 0, 0))[1] for day in days], dtype=np.int64)
        numerator, denominator = float(num.sum()), int(den.sum())
        expected_rows[key] = dict(numerator=numerator, denominator=denominator,
            value=numerator/denominator if denominator else None, status="OK" if denominator else "N/A_ZERO_DENOMINATOR",
            **interval(num, den, expected_indices[key[0]+"_day"]))
        if key[0]+"_seven" in expected_indices:
            seven = interval(num, den, expected_indices[key[0]+"_seven"])
            seven.update(point=numerator/denominator if denominator else None,
                         status="OK" if seven["valid_replicates"] else "N/A_ZERO_DENOMINATOR")
        else:
            seven = dict(point=None, lo95=None, hi95=None, valid_replicates=0, invalid_replicates=0,
                         status="N/A_INSUFFICIENT_BLOCKS")
        expected_rows[key]["seven_day"] = seven
    ece = {}
    for key, quantities in buckets.items():
        check()
        total = sum(quantities.values(), np.zeros((10, 5)))
        weight = float(total[:, 0].sum())
        numerator = float(np.abs(total[:, 1]-total[:, 2]).sum())
        per_day = np.array([quantities.get(day, np.zeros((10, 5))) for day in days_for(key[0])])
        sampled = per_day[expected_indices[key[0]+"_day"]].sum(axis=1)
        den = sampled[:, :, 0].sum(axis=1)
        estimates = np.full(1000, np.nan)
        valid = den > 0
        estimates[valid] = np.abs(sampled[valid, :, 1]-sampled[valid, :, 2]).sum(axis=1)/den[valid]
        ece[key] = (numerator/weight if weight else None, estimates)
        expected_rows[(*key, "ece")] = dict(numerator=numerator, denominator=weight, value=numerator/weight if weight else None,
            lo95=float(np.quantile(estimates[valid], .025)) if valid.any() else None,
            hi95=float(np.quantile(estimates[valid], .975)) if valid.any() else None,
            valid_replicates=int(valid.sum()), invalid_replicates=int((~valid).sum()), status="OK" if weight else "N/A_ZERO_DENOMINATOR")
    for key, (point, estimates) in ece.items():
        period, offset, stratum, model, reference, comparison = key
        other = (period, offset, stratum, reference, reference, comparison)
        if comparison == "C10" and model == "M1":
            other_point, other_estimates = ece[other]
            difference = estimates-other_estimates
            valid = np.isfinite(difference)
            expected_rows[(*key, "ece_difference")] = dict(numerator=None, denominator=None,
                value=point-other_point if point is not None and other_point is not None else None,
                lo95=float(np.quantile(difference[valid], .025)) if valid.any() else None,
                hi95=float(np.quantile(difference[valid], .975)) if valid.any() else None,
                valid_replicates=int(valid.sum()), invalid_replicates=int((~valid).sum()),
                status="OK" if point is not None else "N/A_ZERO_DENOMINATOR")
    fields = ("period", "offset", "stratum", "model", "reference", "comparison_set", "metric")
    actual = {tuple(row[name] for name in fields): row for row in raw["rows"]}
    if len(actual) != len(raw["rows"]) or actual.keys() != expected_rows.keys():
        raise Mismatch("statistical schema/missing or duplicate series")
    for key, expected in expected_rows.items():
        for name, value in expected.items():
            if name == "seven_day":
                for subfield, subvalue in value.items():
                    equal(actual[key][name][subfield], subvalue)
            else:
                equal(actual[key][name], value)
    for row in raw["daily"]:
        key = tuple(row[name] for name in fields)
        num, den, _ = losses[key].get(row["utc_day"], (0., 0, 0))
        equal(row["numerator"], float(num))
        equal(row["denominator"], int(den))
        equal(row["value"], float(num/den) if den else None)
    daily_keys = {(tuple(row[name] for name in fields), row["utc_day"]) for row in raw["daily"]}
    required_daily = {(key, day) for key in losses for day in days_for(key[0])}
    if len(daily_keys) != len(raw["daily"]) or daily_keys != required_daily:
        raise Mismatch("missing or duplicate daily statistic")
    for row in raw["monthly"]:
        key = tuple(row[name] for name in fields)
        quantities = [value for day, value in losses[key].items() if day.startswith(row["utc_month"])]
        num, den = math.fsum(value[0] for value in quantities), sum(value[1] for value in quantities)
        equal(row["numerator"], num)
        equal(row["denominator"], den)
        equal(row["value"], num/den if den else None)
    for row in raw["calibration_rows"]:
        key = tuple(row[name] for name in fields[:-1])
        total = sum(buckets[key].values(), np.zeros((10, 5)))
        weight, prob, labels, slots, rounds = total[row["bin"]]
        for name, expected in dict(slot_count=int(slots), round_count=int(rounds), weight=float(weight/total[:, 0].sum()) if total[:, 0].sum() else 0.,
            mean_p=float(prob/weight) if weight else None, up_rate=float(labels/weight) if weight else None).items():
            equal(row[name], expected)
    cal_keys = {(tuple(row[name] for name in fields[:-1]), row["bin"]) for row in raw["calibration_rows"]}
    if len(cal_keys) != len(raw["calibration_rows"]) or cal_keys != {(key, index) for key in buckets for index in range(10)}:
        raise Mismatch("missing or duplicate calibration bucket")
    for name, rows in (("comparison", raw["rows"]), ("calibration", raw["calibration_rows"]),
        ("daily", raw["daily"]), ("monthly", raw["monthly"]),
        ("volatility", [row for row in raw["rows"] if row["stratum"] in {item[0] for item in STRATA}]),
        ("floor", [row for row in raw["rows"] if row["metric"] == "floor_share"]),
        ("leave-one-day-out", raw["leave_one_day_out"])):
        with (source / f"{name}.csv").open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            columns = ["schema_version", "period", "fold", "offset", "model", "reference", "comparison_set", "metric",
                "stratum", "numerator", "denominator", "value", "lo95", "hi95", "valid_replicates", "invalid_replicates", "status"]
            if name == "calibration":
                columns += ["bin", "lower", "upper", "slot_count", "round_count", "weight", "mean_p", "up_rate"]
            elif name in ("daily", "leave-one-day-out"):
                columns += ["utc_day"]
            elif name == "monthly":
                columns += ["utc_month"]
            equal(reader.fieldnames, columns)
            for expected in rows:
                row = next(reader)
                for field, value in row.items():
                    expected_value = expected.get(field)
                    equal(value, "N/A" if expected_value is None else repr(expected_value) if type(expected_value) is float else str(expected_value))
            if next(reader, None) is not None:
                raise Mismatch("extra projected CSV row")
    return dict(statistic_series=len(expected_rows), coverage=coverage, rows=actual, reference_rows=expected_rows)


def audit(source: Path, output: Path, *, check: Any, sink: Any = None) -> dict:
    """Full independent audit; never starts another price/core/database replay."""
    params = load(source / "params.json")
    frozen = dict(mode="full", start_us=int(datetime.fromisoformat("2026-08-10T00:00:00+00:00").timestamp())*1_000_000,
        end_us=int(datetime.fromisoformat("2026-11-17T00:00:00+00:00").timestamp())*1_000_000,
        as_of_us=int(datetime.fromisoformat("2026-11-17T15:00:00+00:00").timestamp())*1_000_000,
        sample_seconds=5, warmup_seconds=0, half_life_seconds=300, min_vol_samples=20, offsets=list(OFFSETS), floors=FLOORS)
    if any(params.get(name) != value for name, value in frozen.items()):
        raise Mismatch("audit input is not the frozen full study")
    if load(source / "run.json").get("source_days") != 99:
        raise Mismatch("full source day denominator")
    fits = load(source / "parameters.json")["fits"]
    if set(fits) != {str(index) for index in range(9)}:
        raise Mismatch("nine frozen fitting windows required")
    independently_fitted = {}
    for index in range(9):
        check()
        entry = fits[str(index)]
        cutoff = C0+index*7*DAY
        equal(entry["cutoff_us"], cutoff)
        fitted = independent_fit(list((source / "fit-days").glob("*.npy")), cutoff, params["as_of_us"], check)
        independently_fitted[str(index)] = fitted
        actual = entry["m1"]
        equal(actual["lambda"], .001)
        equal(actual["optimizer_id"], "projected-newton-2d/1")
        equal(actual["max_iterations"], 500)
        equal(actual["train_cutoff_us"], cutoff)
        equal(actual["as_of_us"], params["as_of_us"])
        if actual["fit_status"] != "FIT_NOT_CONVERGED":
            equal(actual["fit_status"], fitted["fit_status"])
        elif fitted["fit_status"] in ("FIT_EMPTY", "FIT_SINGLE_CLASS"):
            raise Mismatch("false nonconvergence status")
        for field in ("unique_rounds", "slot_count", "up_count", "down_count", "input_hash",
                      "latest_label_available_at_us", "prediction_range_us"):
            equal(actual[field], fitted[field])
        if actual["fit_status"] != "FIT_OK":
            if actual["a"] is not None or actual["b"] is not None:
                raise Mismatch("failed fit emits parameters")
        if actual["fit_status"] == "FIT_NOT_CONVERGED":
            last = actual["last_iterate"]
            if not 0 < actual["iterations"] <= 500 or last["a"] < 0:
                raise Mismatch("invalid nonconvergence evidence")
            objective, ga, gb, *_ = fitted["evaluate"](last["a"], last["b"])
            equal(actual["objective"], objective)
            if max(abs(last["a"]-max(0., last["a"]-ga)), abs(gb)) <= 1e-8:
                raise Mismatch("converged last iterate incorrectly reported unavailable")
        if actual["fit_status"] == "FIT_OK":
            for field in ("a", "b"):
                equal(actual[field], fitted[field], abs_tol=1e-5, rel_tol=1e-5)
            objective, ga, gb, *_ = fitted["evaluate"](actual["a"], actual["b"])
            equal(actual["objective"], objective)
            equal(actual["objective"], fitted["objective"], abs_tol=1e-10, rel_tol=0.)
            if actual["a"] < 0 or max(abs(actual["a"]-max(0., actual["a"]-ga)), abs(gb)) > 1e-8:
                raise Mismatch("saved fit violates feasibility/projected gradient")
        up = down = 0
        for row in decoded_csv(source / "rounds.csv"):
            if row["ends_at_us"] <= cutoff and row["label_available_at_us"] is not None and row["label_available_at_us"] <= min(cutoff, params["as_of_us"]):
                up += row["label"] == "UP"
                down += row["label"] == "DOWN"
        equal(entry["b1"]["counted_rounds"], up+down)
        equal(entry["b1"]["value"], up/(up+down) if up+down else None)
    samples = audit_samples(source, fits, check, independently_fitted)
    statistics = audit_statistics(source, check)
    raw = load(source / "statistics.json")
    primary = statistics["rows"][("VALIDATION", "ALL", "ALL", "M1", "M0", "C10", "binary_brier_difference")]
    every_fold = all(statistics["rows"][(f"FOLD_{index}", "ALL", "ALL", "M1", "M0", "C10", "binary_brier_difference")]["denominator"] > 0 for index in range(8))
    if (any(fits[str(index)]["m1"]["fit_status"] != "FIT_OK" for index in range(8)) or
            not every_fold or primary["valid_replicates"] != 1000):
        verdict = "INSUFFICIENT_EVIDENCE"
    elif samples["identical"]:
        verdict = "HYPOTHESIS_NOT_SUPPORTED"
    elif primary["hi95"] < -1e-12:
        verdict = "SUPPORT_FURTHER_VALIDATION"
    elif primary["lo95"] > 1e-12:
        verdict = "HYPOTHESIS_NOT_SUPPORTED"
    else:
        verdict = "INSUFFICIENT_EVIDENCE"
    equal(raw["preaudit_classification"], verdict)
    equal(raw["primary_evidence"]["difference"], primary["value"])
    for endpoint in ("lo95", "hi95"):
        equal(raw["primary_evidence"]["interval"][endpoint], primary[endpoint])
    equal(raw["primary_evidence"]["numerically_identical"], samples["identical"])
    for row in raw["leave_one_day_out"]:
        removed = next(item for item in raw["daily"] if item["period"] == "VALIDATION" and item["offset"] == item["stratum"] == "ALL" and
            item["comparison_set"] == "C10" and item["metric"] == "binary_brier_difference" and item["utc_day"] == row["utc_day"])
        numerator, denominator = primary["numerator"]-removed["numerator"], primary["denominator"]-removed["denominator"]
        equal(row["numerator"], numerator)
        equal(row["denominator"], denominator)
        equal(row["value"], numerator/denominator if denominator else None)
    diagnostics = [row for row in raw["rows"] if row["comparison_set"] == "C10"]
    equal(raw["robustness_diagnostics"], diagnostics)
    conflicts = [row for row in diagnostics if row["metric"].endswith("_difference") and row["value"] is not None
        and row["value"] > 1e-12 and primary["value"] is not None and primary["value"] < -1e-12]
    if (primary["value"] is not None and primary["value"] < -1e-12 and primary["seven_day"]["hi95"] is not None
            and primary["seven_day"]["hi95"] >= -1e-12):
        conflicts.append(dict(item="seven_day_does_not_support", **primary["seven_day"]))
    conflicts += [dict(row, diagnostic="leave_one_day_out") for row in raw["leave_one_day_out"]
        if row["value"] is not None and row["value"] > 1e-12 and primary["value"] is not None and primary["value"] < -1e-12]
    equal(raw["diagnostic_conflicts"], conflicts)
    if raw["proxy_error"] != "UNKNOWN" or raw["economic_value_status"] != "NOT_VERIFIED" or raw["research_verdict"] is not None:
        raise Mismatch("economic or pre-audit claim exceeds evidence")
    verdict_payload = load(source / "verdict.json")
    if any(verdict_payload[key] != raw[key] for key in verdict_payload):
        raise Mismatch("verdict carrier diverges from raw")
    for leaf in ("developer-pilot-v01", "validate-pilot-v01"):
        pilot = EVIDENCE / leaf
        bind_source(pilot)
        reference = load(pilot / "reference/run.json")
        if (not reference["complete"] or reference["exit_code"] != 0 or
                reference["source_run_sha256"] != sha(pilot / "run.json")):
            raise Mismatch("pilot vectors missing")
        for name, expected in reference["artifacts"].items():
            if sha(pilot / "reference" / name) != expected:
                raise Drift("pilot reference artifact drift")
        if sink is not None and leaf == "developer-pilot-v01":
            with (pilot / "reference/vectors.csv").open(newline="") as stream:
                for row in csv.DictReader(stream):
                    sink(row)
        for name in ("events.jsonl", "native-samples.csv", "samples.csv", "contexts.jsonl",
            "cores/M0/values.jsonl", "cores/M2-low/values.jsonl", "cores/M2-high/values.jsonl"):
            with (source / name).open("rb") as stream:
                prefix = stream.read((pilot / name).stat().st_size)
            if hashlib.sha256(prefix).hexdigest() != sha(pilot / name):
                raise Mismatch("full/pilot first-day prefix mismatch")
    with (output / "statistic-differences.csv").open("x", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("series", "metric", "actual", "reference", "absolute_error", "status"))
        for key, actual in statistics["rows"].items():
            expected = statistics["reference_rows"][key]
            for field in ("numerator", "denominator", "value", "lo95", "hi95"):
                left, right = actual.get(field), expected.get(field)
                writer.writerow((str(key), field, "N/A" if left is None else repr(left),
                    "N/A" if right is None else repr(right), abs(left-right) if left is not None and right is not None else "N/A",
                    "TIGHT_TOLERANCE_MATCH"))
    return dict(slots=samples["slots"], statistic_series=statistics["statistic_series"],
                research_verdict=verdict, engineering_checks="PASS", price_vectors="BOUND_TO_BOTH_PILOTS_AND_FULL_FIRST_DAY")


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise Refusal(message)


def main(argv: list[str] | None = None) -> int:
    """Run vectors/audit once against an immutable, qualified source run."""
    started = time.monotonic()
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--mode", choices=("vectors", "audit"), required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    try:
        args = parser.parse_args(arguments)
        source, output = plain_path(args.source_dir), plain_path(args.evidence_dir)
        leaves = ("developer-small", "developer-small-retry-1", "developer-small-retry-2",
                  "developer-small-retry-3", "developer-small-retry-4", "developer-small-retry-5",
                  "developer-pilot", "developer-pilot-retry-1", "validate-small", "validate-pilot",
                  "developer-small-v01", "validate-small-v01",
                  "developer-pilot-v01", "validate-pilot-v01")
        if args.mode == "vectors":
            if source not in {EVIDENCE / leaf for leaf in leaves} or output != source / "reference":
                raise Refusal("unapproved vectors scope")
        elif source != EVIDENCE / "full-v01" or output != EVIDENCE / "audit-v01":
            raise Refusal("unapproved audit scope")
        if output.exists():
            raise Refusal("reference output already exists")
        before = bind_source(source)
        output.mkdir(exist_ok=False)
    except (Refusal, FileExistsError, FileNotFoundError):
        return 64
    except Drift:
        return 6
    except Mismatch:
        return 4
    guard = RefBudget(output, 120 if args.mode == "vectors" else 2400)
    guard.started = started
    guard.deadline = started + (120 if args.mode == "vectors" else 2400)
    code, error = 0, None
    result = {}
    guard.start()
    try:
        guard.check()
        save(output / "identity-start.json", before)
        save(output / "commands.json", dict(argv=list(sys.orig_argv) if argv is None else [sys.executable, "-B", str(Path(__file__)), *arguments],
            cwd=str(Path.cwd()), executable=sys.executable))
        with (output / "vectors.csv").open("x", encoding="utf-8", newline="") as stream:
            columns = ("model", "seq", "at_us", "floor", "status", "samples", "source_epoch", "reset_reason",
                       "sigma_raw", "sigma", "native_p", "reference_p", "erf_p")
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            def sink(row: dict) -> None:
                writer.writerow({name: "N/A" if value is None else repr(value) if type(value) is float else value
                                 for name, value in row.items()})
            if args.mode == "vectors":
                result = check_vectors(lines(source / "events.jsonl"),
                    {model: lines(source / "cores" / model / "values.jsonl") for model in FLOORS}, FLOORS,
                    sink=sink, check=guard.check)
            else:
                result = audit(source, output, check=guard.check, sink=sink)
        save(output / "reference.json", dict(passed=True, mode=args.mode, **result))
    except BaseException as problem:
        error = type(problem).__name__
        code = 6 if isinstance(problem, Drift) else 5 if isinstance(problem, TimeoutError) else (
            7 if isinstance(problem, KeyboardInterrupt) else 4 if isinstance(problem, (ValueError, StopIteration)) else 2)
    finally:
        guard.close()
        try:
            after = bind_source(source)
            save(output / "identity-after.json", after)
            if before != after:
                error, code = error or "Drift", code or 6
        except BaseException as problem:
            error, code = error or type(problem).__name__, code or 6
        if error:
            save(output / "failure.json", dict(error=error, exit_code=code))
        save(output / "run.json", dict(complete=error is None, exit_code=code, error=error,
            wall_seconds=time.monotonic()-guard.started, resource_samples=guard.samples,
            ru_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, source_dir=str(source),
            source_run_sha256=before["run_sha256"], artifacts={str(path.relative_to(output)): sha(path)
                for path in output.iterdir() if path.is_file()}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
