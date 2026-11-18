"""Joint four-group BTC5m forward-validation preparation (phase1 joint).

This module prepares the frozen candidate for the future 14-day joint window
(M0 / M1 / M2-low / M3-joint) and performs the read-only controlled-paper
audit.  It never writes production data, never starts a new paper run, never
opens a database except through the approved ``UnifiedDataClient`` /
``Btc5mHistoryReader`` facade, and never recomputes the native EWMA/CDF
mathematics: the Rust core and ``phase1_model_metrics`` stay the single source
of the core formulas and of the frozen ``fit_m1`` algorithm.

Four groups, all fed by the same slot input:

* ``M0``       – native floor ``0.00005`` output.
* ``M1``       – the frozen M0 output passed through the M1 calibration
  (``a1, b1``) fitted on the M0 output.
* ``M2-low``   – native floor ``0.000025`` output.
* ``M3-joint`` – the frozen M2-low output re-fitted with its own calibration
  (``a3, b3``); it never reuses the M1 parameters.

Sub-commands
-------------
``prepare``     – read-only fit of the two calibrations over the existing
  99-day archive carrier; writes the training identity, the filter counts, the
  parameters, the state and the freeze-ready experiment manifest.
``dev``         – one real development window (one complete UTC day) read through the existing facade, consumed completely, verified and
  replayed through the existing native cores; writes the real four-group
  output of that window.
``paper-audit`` – read-only audit of the existing controlled-paper evidence.
``forward``     – consume a reviewer freeze after its full 14-day window ends;
  replay continuous cores with one preceding UTC warm-up day and never re-fit.

Exit codes: 0 ok, 2 unexpected, 4 data/consumer failure, 5 budget, 6 drift,
7 cancelled, 64 preflight refusal.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import itertools
import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[4]
for _path in (str(ROOT), str(LAB)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import phase1_model_research as research  # noqa: E402

# ``phase1_model_metrics`` (and therefore numpy) is imported lazily: importing
# it in the parent process inflates the RSS high-water mark of every forked
# native core, which the frozen run budget rejects.

REPORT_DIR = ROOT / "data/reports/2026-11-18-btc5m-joint-forward-validation"
EVIDENCE_ROOT = REPORT_DIR / "evidence"
ARCHIVE = ROOT / "data/reports/2026-11-18-btc5m-phase1-model-research/evidence/full-v01"
PAPER_RUN = ROOT / "data/reports/2026-11-17-btc5m-controlled-paper/evidence/20261117-phase1-paper-182348"

GROUPS = ("M0", "M1", "M2-low", "M3-joint")
BASE_GROUP = {"M0": "M0", "M1": "M0", "M2-low": "M2-low", "M3-joint": "M2-low"}
CALIBRATION_OF = {"M1": "M1", "M3-joint": "M3-joint"}
FLOORS = {"M0": 0.00005, "M2-low": 0.000025}
OFFSETS = (30, 60, 120, 180, 240, 270)
STRATA = (("[0,0.000025)", 0.0, 0.000025), ("[0.000025,0.00005)", 0.000025, 0.00005),
          ("[0.00005,0.0001)", 0.00005, 0.0001), ("[0.0001,+inf)", 0.0001, math.inf))
PAIRS = (("M3-joint", "M0"), ("M3-joint", "M2-low"), ("M1", "M0"), ("M2-low", "M0"))
SEED = 42
REPLICATES = 1000
WINDOW_DAYS = 14
DAY_US = 86_400_000_000
EPS = 1e-12


class PreflightError(ValueError):
    """Argument/path preflight failure (exit 64)."""


class DataError(ValueError):
    """Data/consumer integrity failure (exit 4)."""


class DriftError(DataError):
    """Identity changed (exit 6)."""


class BudgetError(TimeoutError):
    """Frozen wall/disk budget exceeded (exit 5)."""


def failure_code(error: BaseException) -> int:
    """Map a failure to its stable CLI exit code."""
    if isinstance(error, PreflightError):
        return 64
    if isinstance(error, DriftError):
        return 6
    if isinstance(error, TimeoutError):
        return 5
    if isinstance(error, KeyboardInterrupt):
        return 7
    if isinstance(error, (DataError, ValueError)):
        return 4
    return 2


def digest(path: Path) -> str:
    """SHA256 of one file with bounded reads."""
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write one new JSON artefact; never overwrite."""
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def utc(value: datetime) -> int:
    """Naive or aware datetime to integer microseconds UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    elapsed = value.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds


def day_of(at_us: int) -> str:
    """UTC day label of an integer-microsecond instant."""
    return datetime.fromtimestamp(at_us / 1_000_000, timezone.utc).date().isoformat()


def compute_window(freeze_utc: datetime) -> dict[str, Any]:
    """Derive the future half-open window from the actual freeze instant.

    The window starts at the next UTC midnight after the freeze day and spans
    fourteen complete UTC days, half open.  Nothing that exists before the
    freeze may be presented as future validation data.
    """
    if freeze_utc.tzinfo is None:
        freeze_utc = freeze_utc.replace(tzinfo=timezone.utc)
    freeze_utc = freeze_utc.astimezone(timezone.utc)
    start = datetime(freeze_utc.year, freeze_utc.month, freeze_utc.day, tzinfo=timezone.utc)
    start += timedelta(days=1)
    end = start + timedelta(days=WINDOW_DAYS)
    return dict(freeze_utc=freeze_utc.astimezone(timezone.utc).isoformat(),
                start_utc=start.isoformat(), end_utc=end.isoformat(),
                days=WINDOW_DAYS, interval="half-open [start_utc, end_utc)",
                start_us=utc(start), end_us=utc(end))


# --------------------------------------------------------------------------
# carrier access (read-only)
# --------------------------------------------------------------------------
def carrier_rows(path: Path) -> Iterator[dict[str, Any]]:
    """Stream the existing native-samples carrier with the frozen decoder."""
    import phase1_model_metrics as metrics
    if not path.is_file():
        raise PreflightError(f"carrier missing: {path}")
    yield from metrics.read_csv(path)


def training_rows(path: Path, key: str) -> list[dict[str, Any]]:
    """Build the frozen fit input of one calibration from the carrier.

    Only the time, availability, label and draw filters of the frozen
    ``fit_m1`` implementation may exclude a slot; the probability itself is
    taken unchanged from the carrier column.
    """
    rows: list[dict[str, Any]] = []
    for row in carrier_rows(path):
        probability = row.get(key)
        if probability is None:
            continue
        rows.append(dict(at_us=row["at_us"], ends_at_us=row["ends_at_us"],
                         label=row["label"], label_available_at_us=row["label_available_at_us"],
                         planned_start_us=row["planned_start_us"], p_up=probability))
    return rows


def fit_calibration(rows: list[dict[str, Any]], cutoff_us: int, as_of_us: int) -> dict[str, Any]:
    """Fit one calibration with the frozen ``fit_m1`` algorithm."""
    import phase1_model_metrics as metrics
    record = metrics.fit_m1(rows, cutoff_us=int(cutoff_us), as_of_us=int(as_of_us))
    return dict(fit_status=record["fit_status"], a=record["a"], b=record["b"],
                optimizer_id=record["optimizer_id"], regularization=record["lambda"],
                train_cutoff_us=record["train_cutoff_us"], as_of_us=record["as_of_us"],
                unique_rounds=record["unique_rounds"], slot_count=record["slot_count"],
                up_count=record["up_count"], down_count=record["down_count"],
                draw_excluded_count=record["draw_excluded_count"],
                availability_excluded_count=record["availability_excluded_count"],
                window_excluded_count=record["window_excluded_count"],
                invalid_probability_excluded_count=record["invalid_probability_excluded_count"],
                missing_label_excluded_count=record["missing_label_excluded_count"],
                input_hash=record["input_hash"], iterations=record["iterations"],
                objective=record["objective"], projected_gradient=record["projected_gradient"],
                prediction_range_us=record["prediction_range_us"],
                latest_label_available_at_us=record["latest_label_available_at_us"])


def calibration_parameters(cutoff_us: int, as_of_us: int) -> dict[str, Any]:
    """Fit both calibrations on the same historical training rows.

    Each calibration consumes only its own base output: ``M1`` the M0 output,
    ``M3-joint`` the M2-low output.  The two fits never share parameters.
    """
    carrier = ARCHIVE / "native-samples.csv"
    fitted: dict[str, Any] = {}
    for name, key in (("M1", "m0_p_up"), ("M3-joint", "m2_low_p_up")):
        rows = training_rows(carrier, key)
        record = fit_calibration(rows, cutoff_us, as_of_us)
        record["input_group"] = BASE_GROUP[name]
        record["input_column"] = key
        fitted[name] = record
    return fitted


# --------------------------------------------------------------------------
# four-group probabilities and paired metrics
# --------------------------------------------------------------------------
def group_probability(group: str, p_base: float | None,
                       parameters: dict[str, Any]) -> float | None:
    """Probability of one group; a failed fit emits no probability."""
    import phase1_model_metrics as metrics
    if p_base is None:
        return None
    if group not in CALIBRATION_OF:
        return float(p_base)
    record = parameters.get(CALIBRATION_OF[group]) or {}
    if record.get("fit_status") != "FIT_OK":
        return None
    return metrics.apply_m1(float(p_base), float(record["a"]), float(record["b"]))


def binary_brier(probability: float, up: bool) -> float:
    """Brier loss of one binary outcome."""
    return (probability - (1.0 if up else 0.0)) ** 2


def binary_logloss(probability: float, up: bool) -> float:
    """Clipped binary log loss of one outcome."""
    clipped = min(1 - EPS, max(EPS, probability))
    return -math.log(clipped) if up else -math.log1p(-clipped)


def payout_mse(probability: float, payout: float) -> float:
    """Squared error against the payout (0.5 for a draw)."""
    return (probability - payout) ** 2


class Series:
    """Round-then-round daily sufficient statistics of one comparison series.

    Every round contributes its mean slot difference once, exactly like the
    frozen research contract: the round weight is equal and the slot weight is
    equal inside the round.
    """

    def __init__(self) -> None:
        self.days: dict[str, list[float]] = {}

    def add(self, day: str, values: list[float]) -> None:
        # Calendar membership is independent of whether this round is valued.
        entry = self.days.setdefault(day, [0.0, 0])
        if not values:
            return
        entry[0] += sum(values) / len(values)
        entry[1] += 1

    def totals(self) -> tuple[float, int]:
        numerator = sum(value[0] for value in self.days.values())
        denominator = sum(value[1] for value in self.days.values())
        return numerator, denominator


class Buckets:
    """Calibration buckets of one group: weight, probability and up rate."""

    def __init__(self) -> None:
        self.days: dict[str, list[list[float]]] = {}

    def _bins(self, day: str) -> list[list[float]]:
        return self.days.setdefault(day, [[0.0, 0.0, 0.0, 0.0, 0.0] for _ in range(10)])

    def add(self, day: str, index: int, weight: float, probability: float, up: bool) -> None:
        bins = self._bins(day)
        bins[index][0] += weight
        bins[index][1] += weight * probability
        bins[index][2] += weight * (1.0 if up else 0.0)
        bins[index][3] += 1

    def close_round(self, day: str, index: int) -> None:
        self._bins(day)[index][4] += 1

    def summary(self) -> dict[str, Any]:
        total = [[0.0, 0.0, 0.0, 0.0, 0.0] for _ in range(10)]
        for bins in self.days.values():
            for index, values in enumerate(bins):
                for position, value in enumerate(values):
                    total[index][position] += value
        weight = sum(bin_[0] for bin_ in total)
        numerator = sum(abs(bin_[1] - bin_[2]) for bin_ in total)
        return dict(value=numerator / weight if weight else None, weight=weight,
                    numerator=numerator, denominator=weight,
                    bins=[dict(bin=index, lower=index / 10, upper=(index + 1) / 10,
                               weight=bin_[0], mean_p=(bin_[1] / bin_[0]) if bin_[0] else None,
                               up_rate=(bin_[2] / bin_[0]) if bin_[0] else None,
                               slot_count=int(bin_[3]), round_count=int(bin_[4]))
                          for index, bin_ in enumerate(total)])


def _label_state(slot: dict[str, Any], as_of_us: int) -> tuple[bool, bool | None]:
    """Return (label known, binary up flag)."""
    known = (slot.get("label_available_at_us") is not None
             and int(slot["label_available_at_us"]) <= as_of_us)
    if not known:
        return False, None
    label = slot.get("label")
    if label == "UP":
        return True, True
    if label == "DOWN":
        return True, False
    return True, None


def evaluate(rows: Iterable[dict[str, Any]], parameters: dict[str, Any], *,
             as_of_us: int, gate_at_us: int | None = None) -> dict[str, Any]:
    """Compute the paired joint statistics from grouped round rows.

    ``rows`` yields one dictionary per slot with the native base
    probabilities, the official label and the causal sigma.  Every comparison
    uses the common denominator of the slots where both models carry a legal
    probability and a known binary label.
    """
    series: dict[str, Series] = {}
    offsets: dict[tuple[str, str, str], Series] = {}
    strata: dict[tuple[str, str, str], Series] = {}
    own = {name: {metric: Series() for metric in ("binary_brier", "binary_logloss", "payout_mse")}
           for name in GROUPS}
    buckets = {name: Buckets() for name in GROUPS}
    counts: dict[str, dict[str, int]] = {name: {} for name in GROUPS}
    rounds = 0

    def count(group: str, key: str) -> None:
        counts[group][key] = counts[group].get(key, 0) + 1

    for _, group in itertools.groupby(rows, key=lambda row: row["planned_start_us"]):
        slots = list(group)
        if not slots:
            continue
        rounds += 1
        day = day_of(slots[0]["planned_start_us"])
        probabilities: dict[str, list[float | None]] = {name: [] for name in GROUPS}
        for slot in slots:
            gated = gate_at_us is not None and int(slot["at_us"]) >= gate_at_us
            known, up = _label_state(slot, as_of_us)
            for name in GROUPS:
                base = slot["p_m0"] if BASE_GROUP[name] == "M0" else slot["p_low"]
                probability = group_probability(name, base, parameters)
                probabilities[name].append(probability)
                if gated:
                    count(name, "future_gate_excluded")
                    continue
                count(name, "slots")
                count(name, "valued" if probability is not None else "unvalued")
                count(name, "label_known" if known else "missing_label")
                if known and slot.get("label") == "DRAW":
                    count(name, "draw_label")
                if probability == 0.5:
                    count(name, "abstain")
                if probability is None or not known or up is None:
                    continue
                count(name, "binary_scored")
                if abs(probability - (1.0 if up else 0.0)) >= 0.5:
                    count(name, "extreme_misjudgement")
                if probability != 0.5 and (probability > 0.5) != up:
                    count(name, "direction_conflict")
        for name in GROUPS:
            for metric, loss in (("binary_brier", binary_brier), ("binary_logloss", binary_logloss),
                                 ("payout_mse", payout_mse)):
                losses = []
                for probability, item in zip(probabilities[name], slots):
                    known, up = _label_state(item, as_of_us)
                    if probability is None or not known or (gate_at_us is not None and item["at_us"] >= gate_at_us):
                        continue
                    if metric == "payout_mse":
                        losses.append(loss(probability, 0.5 if up is None else float(up)))
                    elif up is not None:
                        losses.append(loss(probability, up))
                own[name][metric].add(day, losses)
            valid = [(probability, slot) for probability, slot in zip(probabilities[name], slots)
                     if probability is not None and _label_state(slot, as_of_us)[1] is not None
                     and not (gate_at_us is not None and int(slot["at_us"]) >= gate_at_us)]
            if not valid:
                continue
            weight = 1.0 / len(valid)
            used: set[int] = set()
            for probability, slot in valid:
                index = min(9, int(10 * probability))
                buckets[name].add(day, index, weight, probability,
                                  bool(_label_state(slot, as_of_us)[1]))
                used.add(index)
            for index in used:
                buckets[name].close_round(day, index)
        for model, reference in PAIRS:
            for metric, loss in (("binary_brier", None), ("binary_logloss", None),
                                 ("payout_mse", None)):
                key = f"{model}|{reference}|{metric}"
                values: list[float] = []
                for index, slot in enumerate(slots):
                    if gate_at_us is not None and int(slot["at_us"]) >= gate_at_us:
                        continue
                    left = probabilities[model][index]
                    right = probabilities[reference][index]
                    if left is None or right is None:
                        continue
                    known, up = _label_state(slot, as_of_us)
                    if not known:
                        continue
                    if metric == "payout_mse":
                        payout = 0.5 if up is None else (1.0 if up else 0.0)
                        values.append(payout_mse(left, payout) - payout_mse(right, payout))
                        continue
                    if up is None:
                        continue
                    if metric == "binary_brier":
                        values.append(binary_brier(left, up) - binary_brier(right, up))
                    else:
                        values.append(binary_logloss(left, up) - binary_logloss(right, up))
                series.setdefault(key, Series()).add(day, values)
            for offset in OFFSETS:
                local: list[float] = []
                for index, slot in enumerate(slots):
                    if (slot["offset"] != offset or
                            gate_at_us is not None and int(slot["at_us"]) >= gate_at_us):
                        continue
                    left = probabilities[model][index]
                    right = probabilities[reference][index]
                    if left is None or right is None:
                        continue
                    known, up = _label_state(slot, as_of_us)
                    if not known or up is None:
                        continue
                    local.append(binary_brier(left, up) - binary_brier(right, up))
                offsets.setdefault((model, reference, str(offset)), Series()).add(day, local)
            for name, lower, upper in STRATA:
                local = []
                for index, slot in enumerate(slots):
                    if gate_at_us is not None and int(slot["at_us"]) >= gate_at_us:
                        continue
                    sigma = slot.get("sigma_m0")
                    if sigma is None or not (lower <= float(sigma) < upper):
                        continue
                    left = probabilities[model][index]
                    right = probabilities[reference][index]
                    if left is None or right is None:
                        continue
                    known, up = _label_state(slot, as_of_us)
                    if not known or up is None:
                        continue
                    local.append(binary_brier(left, up) - binary_brier(right, up))
                strata.setdefault((model, reference, name), Series()).add(day, local)
    daily_rows: list[dict[str, Any]] = []
    for name, item in series.items():
        for day, (numerator, denominator) in item.days.items():
            daily_rows.append(dict(period="WINDOW", series=name, day=day,
                                    numerator=numerator, denominator=denominator))
    import phase1_model_metrics as metrics
    bootstrap = metrics.bootstrap_statistics(daily_rows, seed=SEED, replicates=REPLICATES)
    block = bootstrap["periods"]["WINDOW"]["day_block"]["series"]
    comparisons: dict[str, Any] = {}
    for name in sorted(block):
        entry = block[name]
        comparisons[name] = {field: entry.get(field) for field in
                             ("point", "lo95", "hi95", "valid_replicates", "invalid_replicates")}
    # A comparison without any legal slot is reported explicitly as null.
    for model, reference in PAIRS:
        for metric in ("binary_brier", "binary_logloss", "payout_mse"):
            name = f"{model}|{reference}|{metric}"
            comparisons.setdefault(name, dict(point=None, lo95=None, hi95=None,
                                              valid_replicates=0, invalid_replicates=0))
    primary_name = "M3-joint|M0|binary_brier"
    primary = dict(series=primary_name, **{field: comparisons.get(primary_name, {}).get(field)
                                            for field in ("point", "lo95", "hi95",
                                                          "valid_replicates", "invalid_replicates")})
    leave_one_day_out: list[dict[str, Any]] = []
    primary_series = series.get(primary_name)
    if primary_series is not None:
        total_numerator, total_denominator = primary_series.totals()
        for day, (numerator, denominator) in primary_series.days.items():
            remaining_denominator = total_denominator - denominator
            remaining_numerator = total_numerator - numerator
            leave_one_day_out.append(dict(
                utc_day=day, denominator=remaining_denominator,
                point=remaining_numerator / remaining_denominator if remaining_denominator else None))
    diagnostics = {
        "per_offset": {f"{model}|{reference}|{offset}": _series_summary(item)
                       for (model, reference, offset), item in offsets.items()},
        "per_stratum": {f"{model}|{reference}|{name}": _series_summary(item)
                        for (model, reference, name), item in strata.items()},
    }
    return dict(rounds=rounds, primary=primary, comparisons=comparisons,
                models={name: {metric: _series_summary(item) for metric, item in losses.items()}
                        for name, losses in own.items()},
                counts=counts, ece={name: buckets[name].summary() for name in GROUPS},
                diagnostics=diagnostics, leave_one_day_out=leave_one_day_out,
                bootstrap=dict(seed=SEED, replicates=REPLICATES, generator="PCG64",
                               days=bootstrap["periods"]["WINDOW"]["days"]))


def _series_summary(item: Series) -> dict[str, Any]:
    """Numerator, denominator and value of one diagnostic series."""
    numerator, denominator = item.totals()
    return dict(numerator=numerator, denominator=denominator,
                value=numerator / denominator if denominator else None)


# --------------------------------------------------------------------------
# prepare
# --------------------------------------------------------------------------
IDENTITY_FILES = (
    "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/phase1_joint_validation.py",
    "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/phase1_model_research.py",
    "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/phase1_model_metrics.py",
    "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/tests/phase1_reference.py",
    "skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/history_input.py",
)


def identity(cutoff_us: int, as_of_us: int) -> dict[str, Any]:
    """Bind the code, the carrier and the dependency versions of this run."""
    carrier = ARCHIVE / "native-samples.csv"
    files = {name: digest(ROOT / name) for name in IDENTITY_FILES}
    for extra in (carrier, ARCHIVE / "rounds.csv", ARCHIVE / "parameters.json"):
        files[str(extra.relative_to(ROOT))] = digest(extra)
    return dict(files=files, cutoff_us=cutoff_us, as_of_us=as_of_us,
                executable=sys.executable, python=sys.version,
                dependencies={name: importlib.metadata.version(name)
                              for name in ("numpy", "pandas", "pymongo")},
                carrier_rows=sum(1 for _ in carrier_rows(carrier)))


def manifest(parameters: dict[str, Any], identity_payload: dict[str, Any],
             cutoff_us: int, as_of_us: int, freeze_utc: datetime | None) -> dict[str, Any]:
    """Build the freeze-ready experiment manifest of the future window."""
    window = (compute_window(freeze_utc) if freeze_utc is not None else
              dict(rule="the next UTC 00:00 after the freeze day, 14 complete UTC days, half open",
                   freeze_utc=None, start_utc=None, end_utc=None, days=WINDOW_DAYS,
                   interval="half-open [start_utc, end_utc)"))
    return dict(
        schema_version="btc5m-joint-forward-validation-manifest/1",
        status="FREEZE_READY_NOT_FROZEN" if freeze_utc is None else "FREEZE_CANDIDATE",
        window=window,
        training=dict(cutoff_rule="the freeze instant", as_of_rule="the freeze instant",
                      carrier=str((ARCHIVE / "native-samples.csv").relative_to(ROOT)),
                      algorithm="phase1_model_metrics.fit_m1 / projected-newton-2d/1",
                      regularization=0.001, weighting="round-then-round slot weight",
                      label_filter="binary UP/DOWN only; the label must be available at or "
                                   "before the cutoff and at or before the as-of instant; "
                                   "the slot must end at or before the cutoff",
                      demo_cutoff_us=cutoff_us, demo_as_of_us=as_of_us),
        calibrations={name: dict(input_group=record["input_group"],
                                 input_column=record["input_column"],
                                 floor=FLOORS.get(record["input_group"]),
                                 fit_status=record["fit_status"], a=record["a"], b=record["b"],
                                 optimizer_id=record["optimizer_id"], lambda_=record["regularization"],
                                 input_hash=record["input_hash"])
                      for name, record in parameters.items()},
        groups={name: dict(base=BASE_GROUP[name], calibrated=name in CALIBRATION_OF,
                            floor=FLOORS.get(BASE_GROUP[name])) for name in GROUPS},
        state=dict(ewma_half_life_seconds=300, min_vol_samples=20, sample_seconds=5,
                   daily_reset=False,
                   core_continuity="one continuous native core across the warm-up window and the "
                                   "whole validation window; no per-day restart",
                   warmup="one complete UTC day immediately preceding the first scored day",
                   warmup_scored=False,
                   validation_start_state="the carried EWMA state at the first scored round; the "
                                           "warm-up slots are not scored"),
        endpoints=dict(primary="M3-joint minus M0, paired common-valid-slot binary Brier "
                               "difference, 95% UTC-day block interval",
                       attribution="M3-joint minus M2-low",
                       auxiliary=["M1 minus M0", "M2-low minus M0"],
                       round_weighting="equal weight per round, then equal weight per slot",
                       bootstrap=dict(seed=SEED, replicates=REPLICATES, generator="PCG64",
                                      unit="UTC day")),
        diagnostics=["binary logloss", "calibration error (ECE)", "extreme misjudgement",
                     "causal sigma strata", "six offset points", "single-day contribution"],
        not_verified=["PnL", "trade win rate", "Sharpe", "maximum drawdown", "economic value",
                      "the 14-day significance"],
        identity=identity_payload)


def prepare(leaf: Path, cutoff_us: int, as_of_us: int,
            freeze_utc: datetime | None) -> dict[str, Any]:
    """Fit both calibrations on the existing archive and freeze the identity."""
    parameters = calibration_parameters(cutoff_us, as_of_us)
    identity_payload = identity(cutoff_us, as_of_us)
    payload = manifest(parameters, identity_payload, cutoff_us, as_of_us, freeze_utc)
    write_json(leaf / "parameters.json", dict(
        schema_version="btc5m-joint-parameters/1", cutoff_us=cutoff_us, as_of_us=as_of_us,
        calibrations=parameters,
        note="demonstration fit on the historical archive carrier; the future window must re-run "
             "the same frozen algorithm on the training rows available at the freeze"))
    write_json(leaf / "training-identity.json", identity_payload)
    write_json(leaf / "state.json", payload["state"])
    write_json(leaf / "manifest.json", payload)
    return dict(cutoff_us=cutoff_us, as_of_us=as_of_us,
                carrier_rows=identity_payload["carrier_rows"],
                calibrations={name: dict(fit_status=record["fit_status"], a=record["a"],
                                         b=record["b"], slot_count=record["slot_count"],
                                         unique_rounds=record["unique_rounds"],
                                         window_excluded_count=record["window_excluded_count"],
                                         availability_excluded_count=record["availability_excluded_count"],
                                         draw_excluded_count=record["draw_excluded_count"])
                              for name, record in parameters.items()})


# --------------------------------------------------------------------------
# dev window (real facade read, real native cores)
# --------------------------------------------------------------------------
def merged_dev_rows(leaf: Path) -> list[dict[str, Any]]:
    """Merge the native cores of a finished dev leaf into the joint input rows."""
    rows: list[dict[str, Any]] = []
    for wide in research.merge_phase1_values(research.json_lines(leaf / "contexts.jsonl"), leaf):
        rows.append(dict(planned_start_us=wide["planned_start_us"], offset=wide["offset"],
                         at_us=wide["at_us"], ends_at_us=wide["ends_at_us"],
                         label=wide["label"], label_available_at_us=wide["label_available_at_us"],
                         p_m0=wide.get("m0_p_up"), p_low=wide.get("m2_low_p_up"),
                         sigma_m0=wide.get("m0_sigma_raw"),
                         sigma_low=wide.get("m2_low_sigma_raw")))
    return rows


def run_dev(leaf: Path, start: datetime, as_of: datetime, cutoff: datetime) -> dict[str, Any]:
    """Read one real development UTC day through the facade and replay the cores.

    The facade qualifies a window only when a complete UTC day was consumed,
    so the development window is one whole UTC day (the day of ``start``).

    The calibrations are fitted only after the native transport finished: the
    carrier of the historical archive is a large Python structure and loading it
    before the fork inflates the inherited RSS of every native core.
    """
    day_start = datetime(start.year, start.month, start.day)
    day_end = day_start + timedelta(days=1)
    budget = research.RunBudget(leaf, 1800, "dev")
    budget.start()
    start_us = utc(day_start)
    end_us = utc(day_end)
    databases = None
    try:
        from skills.data.unified_data.client import UnifiedDataClient
        from skills.data.unified_data.history_reader import Btc5mHistoryReader
        from skills.data.unified_data.storage import open_databases
        databases = research._bounded_call(budget, open_databases)
        client = UnifiedDataClient(history_reader=Btc5mHistoryReader(databases.ud))
        sources: list[dict[str, Any]] = []
        transport = research.broadcast_phase1(
            research.consume_days(client, leaf, day_start, day_end, budget, sources),
            leaf, start_us, end_us, budget.deadline, guard=budget)
        budget.resume()
        if not transport["complete"]:
            # The transport reports its own stable failure code; do not mask a
            # budget failure behind a generic data failure.
            if transport.get("failure_code") == 5:
                raise BudgetError(f"dev transport budget failure: {transport.get('error')}")
            raise DataError(f"dev transport incomplete: {transport.get('error')}")
        parameters = calibration_parameters(utc(cutoff), utc(as_of))
        write_json(leaf / "parameters.json", dict(cutoff_us=utc(cutoff), as_of_us=utc(as_of),
                                                  calibrations=parameters))
        rows = merged_dev_rows(leaf)
        evaluation = evaluate(rows, parameters, as_of_us=utc(as_of))
        groups = [{name: dict(base=BASE_GROUP[name],
                              p_base=(row["p_m0"] if BASE_GROUP[name] == "M0" else row["p_low"]),
                              p_up=group_probability(
                                  name, row["p_m0"] if BASE_GROUP[name] == "M0" else row["p_low"],
                                  parameters))
                   for name in GROUPS} for row in rows]
        write_json(leaf / "dev-four-groups.json", dict(
            schema_version="btc5m-joint-dev-groups/1", start_us=start_us, end_us=end_us,
            as_of_us=utc(as_of), transport=transport, slots=len(rows),
            groups=groups, evaluation=evaluation))
        return dict(transport=dict(complete=transport["complete"], events=transport["events"],
                                   values=transport["values"],
                                   cores=[dict(name=core["name"],
                                               native_exit=core["native_exit"],
                                               complete=core["complete"])
                                          for core in transport["cores"]]),
                    slots=len(rows), evaluation=evaluation)
    finally:
        budget.pause()
        if databases is not None:
            try:
                databases.ud.client.close()
            except Exception:  # noqa: BLE001 - cleanup must not mask the real failure
                pass
        budget.close()


# --------------------------------------------------------------------------
# paper audit (read-only)
# --------------------------------------------------------------------------
def paper_audit(leaf: Path) -> dict[str, Any]:
    """Audit the existing controlled-paper evidence without changing anything."""
    events_path = PAPER_RUN / "events.jsonl"
    if not events_path.is_file():
        raise PreflightError("paper events missing")
    decisions: dict[str, dict[str, Any]] = {}
    fills: list[dict[str, Any]] = []
    settlements: list[dict[str, Any]] = []
    kinds: dict[str, int] = {}
    for line in events_path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        kind = event.get("event_kind")
        kinds[kind] = kinds.get(kind, 0) + 1
        source = event.get("source") or {}
        if kind == "summary":
            decision = source.get("decision") or {}
            identifier = decision.get("decision_id")
            if identifier is not None:
                decisions[str(identifier)] = decision
        elif kind == "fill":
            fills.append(event)
        elif kind == "settlement":
            settlements.append(event)
    missing: dict[str, int] = {}
    fee_ok = net_ok = cost_ok = price_ok = limit_ok = fair_ok = 0
    rows: list[dict[str, Any]] = []
    for event in fills:
        source = event["source"]
        price = float(source["price"])
        rate = float(source["fee_rate_bps"]) / 10_000
        gross = float(source["gross_shares"])
        fee_cash = float(source["fee"])
        fee_shares = float(source["fee_shares"])
        net = float(source["net_shares"])
        cost = float(source["cost"])
        # The paper fee model charges cash: fee = gross * rate * min(price, 1-price).
        expected_fee_cash = gross * rate * min(price, 1 - price)
        expected_fee_shares = expected_fee_cash / price
        expected_net = gross - fee_shares
        expected_cost = gross * price
        fee_ok += abs(expected_fee_cash - fee_cash) <= 1e-9 and \
            abs(expected_fee_shares - fee_shares) <= 1e-9
        net_ok += abs(expected_net - net) <= 1e-9
        cost_ok += abs(expected_cost - cost) <= 1e-9
        decision = decisions.get(str(source.get("decision_id")))
        if decision is None:
            missing["fill_without_decision"] = missing.get("fill_without_decision", 0) + 1
            continue
        sides = {name: decision.get(name) or {} for name in ("up", "down")}
        # The fill records a generic buy side; the traded leg is identified by
        # the token of the fill against the two legs of the decision.
        token = event.get("token")
        selected = None
        for name, side_payload in sides.items():
            if side_payload.get("token") and side_payload["token"] == token:
                selected = name
        if selected is None:
            selected = "up" if (decision.get("selected_token") or "") == (token or "") \
                and (sides.get("down") or {}).get("token") != token else "down"
        side = sides.get(selected) or {}
        fair = side.get("fair")
        limit = side.get("limit_price")
        fair_ok += fair is not None
        limit_ok += limit is not None and abs(float(limit) - price) <= 1e-9
        price_ok += side.get("execution_net_shares") is not None and abs(
            float(side["execution_net_shares"]) - net) <= 1e-9
        for name, value in (("fair", fair),
                            ("limit_price", limit),
                            ("best_yes_ask", decision.get("best_yes_ask")),
                            ("best_yes_bid", decision.get("best_yes_bid")),
                            ("source_state", decision.get("source_state")),
                            ("starts_at", decision.get("starts_at")),
                            ("ends_at", decision.get("ends_at")),
                            ("sigma", decision.get("sigma")),
                            ("p_up", decision.get("p_up")),
                            ("depth_levels", side.get("depth_levels")),
                            ("walk_vwap", side.get("walk_vwap")),
                            ("source_at", (decision.get("book_clock") or {}).get("source_at")),
                            ("spot_source_at", (decision.get("spot_clock") or {}).get("source_at"))):
            if value is None:
                missing[f"decision_missing_{name}"] = missing.get(f"decision_missing_{name}", 0) + 1
        rows.append(dict(market_id=event.get("market_id"), side=selected, price=price,
                         gross_shares=gross, net_shares=net, fee_cash=fee_cash, fee_shares=fee_shares,
                         cost=cost, fee_rate_bps=source.get("fee_rate_bps"),
                         price_source=(source.get("price_source") or {}).get("name"),
                         decision_id=source.get("decision_id"), fair=fair, limit_price=limit,
                         best_yes_ask=decision.get("best_yes_ask"),
                         best_yes_bid=decision.get("best_yes_bid"),
                         source_state=decision.get("source_state"),
                         starts_at=decision.get("starts_at"), ends_at=decision.get("ends_at"),
                         fee_matches=abs(expected_fee_cash - fee_cash) <= 1e-9 and
                         abs(expected_fee_shares - fee_shares) <= 1e-9,
                         net_matches=abs(expected_net - net) <= 1e-9,
                         cost_matches=abs(expected_cost - cost) <= 1e-9,
                         limit_price_matches=limit is not None and abs(float(limit) - price) <= 1e-9,
                         execution_net_shares_matches=side.get("execution_net_shares") is not None and
                         abs(float(side["execution_net_shares"]) - net) <= 1e-9))
    by_market = {str(event.get("market_id")): event["source"] for event in fills}
    settlement_rows: list[dict[str, Any]] = []
    settlement_ok = 0
    income_ok = 0
    for event in settlements:
        source = event["source"]
        fill = by_market.get(str(event.get("market_id")))
        payout = float(source.get("payout") or 0.0)
        income = float(source.get("income") or 0.0)
        shares = float(source.get("shares") or 0.0)
        basis = float(source.get("basis") or 0.0)
        expected_pnl = None
        if fill is not None:
            # The paper settlement books the realised income against the basis.
            expected_pnl = income - basis
            settlement_ok += abs(expected_pnl - (income - float(fill["cost"]))) <= 1e-9
            income_ok += abs(income - shares * payout) <= 1e-9
        settlement_rows.append(dict(market_id=event.get("market_id"), payout=payout, income=income,
                                    basis=basis, shares=shares, provider=source.get("provider"),
                                    expected_pnl=expected_pnl,
                                    income_matches_shares_payout=abs(income - shares * payout) <= 1e-9,
                                    refund_field_present=("refund" in source
                                                           or "refunded" in source)))
    write_json(leaf / "paper-audit.json", dict(
        schema_version="btc5m-paper-audit/1",
        scope="read-only audit of the existing controlled-paper evidence",
        events_path=str(events_path.relative_to(ROOT)), events_sha256=digest(events_path),
        event_kinds=kinds, fills=len(fills), settlements=len(settlements),
        fee_matches=fee_ok, net_matches=net_ok, cost_matches=cost_ok,
        limit_price_matches=limit_ok, execution_net_shares_matches=price_ok,
        side_fair_present=fair_ok,
        settlement_recomputed=settlement_ok, settlement_income_matches=income_ok,
        missing_fields=missing,
        refundability="NOT_PRESENT in the event schema; recorded as a missing field",
        external_crosscheck="NOT_EXECUTED"))
    with (leaf / "paper-fills.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()) if rows else ["market_id"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    with (leaf / "paper-settlements.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(settlement_rows[0].keys())
                                if settlement_rows else ["market_id"])
        writer.writeheader()
        for row in settlement_rows:
            writer.writerow(row)
    return dict(fills=len(fills), settlements=len(settlements), event_kinds=kinds,
                fee_matches=fee_ok, net_matches=net_ok, cost_matches=cost_ok,
                limit_price_matches=limit_ok, execution_net_shares_matches=price_ok,
                side_fair_present=fair_ok, settlement_recomputed=settlement_ok,
                settlement_income_matches=income_ok, missing_fields=missing)


# --------------------------------------------------------------------------
# Forward consumer: no fitting and no access before the frozen window ends.
# --------------------------------------------------------------------------
FORWARD_BINARY = EVIDENCE_ROOT / "main-implementation/btc_arb_phase1_history-forward"
FORWARD_FILES = (*IDENTITY_FILES, str(FORWARD_BINARY.relative_to(ROOT)),
    str((LAB / "tests/test_phase1_joint_validation.py").relative_to(ROOT)),
    str((research.BOT / "src/bot/arbitrage/phase1_history.rs").relative_to(ROOT)),
    str((LAB / "history_performance.py").relative_to(ROOT)),
    *(f"skills/data/unified_data/{name}" for name in
      ("client.py", "history_reader.py", "history_types.py", "storage.py")))


def aware(value: str) -> datetime:
    """Require an explicit timezone and normalize an experiment clock to UTC."""
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise PreflightError("experiment clocks require an explicit timezone")
    return instant.astimezone(timezone.utc)


def load_freeze(path: Path, as_of: datetime, now: datetime) -> tuple[dict, dict]:
    """Authenticate a reviewer freeze and fixed parameters before acquisition.

    Freeze schema btc5m-joint-freeze/1: verdict=PASS, freeze_utc, window (the
    exact compute_window result), parameters={path (repo relative), sha256},
    files={every FORWARD_FILES path: sha256}, and state={warmup_days:1,
    daily_reset:false}. Warm-up is one complete preceding UTC day because the
    facade authenticates full days; it is consumed but never scored.
    """
    if not path.resolve().is_relative_to(EVIDENCE_ROOT.resolve()):
        raise PreflightError("freeze must be under this experiment's evidence")
    frozen = research.strict_loads(path.read_text())
    if frozen.get("schema_version") != "btc5m-joint-freeze/1" or frozen.get("verdict") != "PASS":
        raise PreflightError("independent freeze PASS required")
    window = compute_window(aware(frozen["freeze_utc"]))
    if frozen.get("window") != window or frozen.get("state") != {"warmup_days": 1, "daily_reset": False}:
        raise PreflightError("frozen window/state mismatch")
    if utc(now) < window["end_us"] or not window["end_us"] <= utc(as_of) <= utc(now):
        raise PreflightError("full frozen window not yet available")
    files = frozen.get("files", {})
    if set(files) != set(FORWARD_FILES):
        raise DriftError("freeze file set mismatch")
    for name, expected in files.items():
        if digest(ROOT / name) != expected:
            raise DriftError("frozen candidate changed")
    parameter_path = (ROOT / frozen["parameters"]["path"]).resolve()
    if not parameter_path.is_relative_to(EVIDENCE_ROOT.resolve()):
        raise PreflightError("parameters must be existing experiment evidence")
    if digest(parameter_path) != frozen["parameters"]["sha256"]:
        raise DriftError("frozen parameters changed")
    payload = research.strict_loads(parameter_path.read_text())
    if not 0 <= payload["cutoff_us"] <= payload["as_of_us"] <= utc(aware(frozen["freeze_utc"])):
        raise PreflightError("training cutoff after freeze")
    parameters = payload["calibrations"]
    if set(parameters) != set(CALIBRATION_OF):
        raise PreflightError("calibration set mismatch")
    for name, record in parameters.items():
        if (record["fit_status"] != "FIT_OK" or record["input_group"] != BASE_GROUP[name]
                or not all(type(record[key]) in (int, float) and math.isfinite(record[key])
                           for key in ("a", "b")) or record["a"] < 0):
            raise PreflightError("invalid frozen calibration")
    return frozen, parameters


def replay_forward(leaf: Path, start: datetime, end: datetime, as_of: datetime) -> list[dict]:
    """Read qualified facade days and use one continuous set of native cores."""
    budget = research.RunBudget(leaf, 1800, "full")
    budget.start()
    databases = None
    try:
        from skills.data.unified_data.client import UnifiedDataClient
        from skills.data.unified_data.history_reader import Btc5mHistoryReader
        from skills.data.unified_data.storage import open_databases
        databases = research._bounded_call(budget, open_databases)
        client = UnifiedDataClient(history_reader=Btc5mHistoryReader(databases.ud))
        # DTO boundaries are naive UTC; the existing adapter adds explicit UTC.
        read_start = (start - timedelta(days=1)).replace(tzinfo=None)
        read_end, cutoff = end.replace(tzinfo=None), as_of.replace(tzinfo=None)
        sources: list[dict] = []
        transport = research.broadcast_phase1(
            research.consume_days(client, leaf, read_start, read_end, budget, sources, as_of=cutoff),
            leaf, utc(read_start), utc(read_end), budget.deadline, guard=budget,
            as_of=cutoff, binary=FORWARD_BINARY)
        budget.resume()
        write_json(leaf / "transport.json", transport)
        if not transport["complete"]:
            if transport["failure_code"] == 5:
                raise BudgetError("forward transport budget")
            if transport["failure_code"] == 6:
                raise DriftError("forward transport/source drift")
            raise DataError("forward transport incomplete")
        if len(sources) != WINDOW_DAYS + 1 or budget.cleanup_errors:
            raise DataError("source/cleanup completeness mismatch")
        rows = merged_dev_rows(leaf)
        expected = (WINDOW_DAYS + 1) * 288 * len(OFFSETS)
        if len(rows) != expected or transport["values"] != expected:
            raise DataError("native theoretical slot count mismatch")
        return rows
    finally:
        budget.pause()
        try:
            if databases is not None:
                databases.ud.client.close()
        finally:
            budget.close()


def run_forward(leaf: Path, freeze_path: Path | None, as_of: datetime) -> dict:
    """Execute the frozen future experiment, never fitting on validation labels."""
    if freeze_path is None:
        raise PreflightError("--freeze-file is required for forward")
    frozen, parameters = load_freeze(freeze_path, as_of, datetime.now(timezone.utc))
    freeze_hash = digest(freeze_path)
    window = frozen["window"]
    rows = replay_forward(leaf, aware(window["start_utc"]), aware(window["end_utc"]), as_of)
    scored = [row for row in rows if window["start_us"] <= row["planned_start_us"] < window["end_us"]]
    if len(scored) != WINDOW_DAYS * 288 * len(OFFSETS):
        raise DataError("scored window incomplete")
    columns = ("planned_start_us", "offset", "at_us", "ends_at_us", "label",
               "label_available_at_us", "sigma_m0", "sigma_low", *GROUPS)
    def predictions() -> Iterator[dict]:
        for row in scored:
            yield {**row, **{name: group_probability(name,
                row["p_m0"] if BASE_GROUP[name] == "M0" else row["p_low"], parameters)
                for name in GROUPS}}
    research.write_csv(leaf / "predictions.csv", predictions(), columns)
    statistics = evaluate(scored, parameters, as_of_us=utc(as_of))
    # Recheck exact candidate/parameter bytes after computation, not just before.
    load_freeze(freeze_path, as_of, datetime.now(timezone.utc))
    if digest(freeze_path) != freeze_hash:
        raise DriftError("freeze record changed during run")
    write_json(leaf / "statistics.json", statistics)
    write_json(leaf / "binding.json", dict(freeze_sha256=freeze_hash, window=window,
        parameters=frozen["parameters"], files=frozen["files"], as_of_utc=as_of.isoformat(),
        warmup_slots=len(rows)-len(scored), scored_slots=len(scored), economic_value="NOT_VERIFIED"))
    return dict(window=window, slots=len(scored), primary=statistics["primary"],
                independent_audit="PENDING", economic_value="NOT_VERIFIED")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
class StrictParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise PreflightError(message)


def claim_leaf(name: str) -> Path:
    """Create one new evidence leaf; an existing leaf is never overwritten."""
    if ".." in Path(name).parts or "/" in name:
        raise PreflightError("invalid evidence leaf")
    leaf = EVIDENCE_ROOT / name
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        leaf.mkdir(exist_ok=False)
    except FileExistsError as error:
        raise PreflightError("evidence leaf already exists") from error
    return leaf


def main(argv: list[str] | None = None) -> int:
    """Parse the frozen CLI and run one owned stage."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = StrictParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--mode", choices=("prepare", "dev", "paper-audit", "forward"), required=True)
    parser.add_argument("--evidence-leaf", required=True)
    parser.add_argument("--cutoff", default="2026-11-17T15:00:00Z")
    parser.add_argument("--as-of", default="2026-11-17T15:00:00Z")
    parser.add_argument("--dev-start", default="2026-11-16T00:00:00Z")
    parser.add_argument("--freeze-utc", default=None)
    parser.add_argument("--freeze-file", type=Path)
    code = 0
    error = None
    leaf: Path | None = None
    started = time.monotonic()
    try:
        args = parser.parse_args(arguments)
        cutoff = datetime.fromisoformat(args.cutoff.replace("Z", "+00:00"))
        as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        freeze = (datetime.fromisoformat(args.freeze_utc.replace("Z", "+00:00"))
                  if args.freeze_utc else None)
        leaf = claim_leaf(args.evidence_leaf)
        write_json(leaf / "commands.json", dict(argv=arguments, cwd=str(Path.cwd()),
                                                executable=sys.executable, mode=args.mode))
        if args.mode == "forward":
            result = run_forward(leaf, args.freeze_file, aware(args.as_of))
        elif args.mode == "prepare":
            result = prepare(leaf, utc(cutoff), utc(as_of), freeze)
        elif args.mode == "dev":
            start = datetime.fromisoformat(args.dev_start.replace("Z", "+00:00"))
            result = run_dev(leaf, start, as_of, cutoff)
        else:
            result = paper_audit(leaf)
        write_json(leaf / "result.json", dict(complete=True, mode=args.mode,
                                              wall_seconds=time.monotonic() - started,
                                              result=result))
    except PreflightError as problem:
        error, code = type(problem).__name__, 64
    except DriftError as problem:
        error, code = type(problem).__name__, 6
    except BudgetError as problem:
        error, code = type(problem).__name__, 5
    except (DataError, ValueError) as problem:
        error, code = type(problem).__name__, 4
    except KeyboardInterrupt:
        error, code = "Cancelled", 7
    except SystemExit:
        raise
    except BaseException as problem:  # noqa: BLE001 - the CLI maps every failure
        error, code = type(problem).__name__, failure_code(problem)
    if error is not None:
        print(f"joint validation refused: {error}", file=sys.stderr)
        if leaf is not None and leaf.exists():
            try:
                write_json(leaf / "failure.json", dict(error=error, exit_code=code))
            except OSError:
                pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
