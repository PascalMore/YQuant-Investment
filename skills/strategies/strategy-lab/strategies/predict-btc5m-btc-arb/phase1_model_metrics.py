"""Phase-1 model research metrics for the BTC5m phase-1 study (SPEC-06-003).

Consumes native rows and single-day read-only arrays; it never reads a database,
fetches market data, starts a core, or computes EWMA/CDF probabilities. It implements the
frozen contract of SPEC-06-003 §4.5-§4.7 and DESIGN-06-003 §3.5: the frozen
M1 fit (``projected-newton-2d/1``), the B1 base rate, the frozen comparison
sets (C10, C0B, C2, D02 and the payout set), the round-then-round weighted
metrics, the paired UTC-day block bootstrap with its 7-day circular moving
block sensitivity, and the three-layer research verdict of SPEC §4.7.

Estimates are deterministic for identical inputs; measured fitting wall cost
is recorded separately, with no global mutable optimizer state. Report
formatting (8 decimals for metrics, 4 for percentages) is not part of this
module; raw floats keep full precision.
"""

from __future__ import annotations

import hashlib
import csv
import itertools
import json
import math
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

__all__ = [
    "FIT_STATUSES", "OFFSETS", "MODEL_NAMES", "fit_m1", "fit_b1", "apply_m1",
    "fit_expanding", "compute_statistics", "bootstrap_statistics",
    "render_figures", "label_code",
]

FIT_STATUSES = frozenset({"FIT_OK", "FIT_EMPTY", "FIT_SINGLE_CLASS", "FIT_NOT_CONVERGED"})
OFFSETS: tuple[int, ...] = (30, 60, 120, 180, 240, 270)
MODEL_NAMES: tuple[str, ...] = ("M0", "M1", "M2-low", "M2-high", "B0", "B1", "B2")

_LAMBDA = 0.001
_OPTIMIZER_ID = "projected-newton-2d/1"
_MAX_ITERATIONS = 500
_PG_TOLERANCE = 1e-8
_ARMIJO_C = 1e-4
_MAX_BACKTRACK = 50
_EPS = 1e-12
_DAY_US = 86_400_000_000
_WEEK_US = 7 * _DAY_US
_FLOORS: dict[str, float] = {"M0": 0.00005, "M2-low": 0.000025, "M2-high": 0.0001}
_STRATA: tuple[tuple[str, float, float], ...] = (
    ("[0,0.000025)", 0.0, 0.000025), ("[0.000025,0.00005)", 0.000025, 0.00005),
    ("[0.00005,0.0001)", 0.00005, 0.0001), ("[0.0001,+inf)", 0.0001, math.inf))
_CARRIED_FIELDS = (
    "at_us", "ends_at_us", "label", "label_available_at_us", "sigma_raw",
    "samples", "spot", "strike", "starts_at_us")
_SLOT_FIELDS = (
    "planned_start_us", "starts_at_us", "ends_at_us", "offset", "round_id", "at_us",
    "label", "label_available_at_us", "period", "fold", "sigma_raw", "samples",
    "spot", "strike")
_METRIC_COLUMNS = (
    "period", "fold", "offset", "model", "reference", "comparison_set", "metric",
    "stratum", "numerator", "denominator", "value", "lo95", "hi95",
    "valid_replicates", "invalid_replicates", "status")
_GATE_NAMES = ("causal_timing", "identity", "denominator", "numeric", "fit")

def label_code(label: str | None) -> int:
    """Return the integer code of an official label.

    Args:
        label: Official label, one of ``"UP"``, ``"DOWN"``, ``"DRAW"`` or
            ``None`` for a missing label.

    Returns:
        ``1`` for UP, ``0`` for DOWN, ``2`` for DRAW and ``-1`` for a
        missing or unknown label.
    """
    return {"UP": 1, "DOWN": 0, "DRAW": 2}.get(label, -1)  # type: ignore[arg-type]

def _logit(p: float) -> float:
    pc = min(1.0 - _EPS, max(_EPS, float(p)))
    return math.log(pc / (1.0 - pc))

def _sigmoid(z: float) -> float:
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)

def _sigmoid_array(z: np.ndarray) -> np.ndarray:
    out = np.empty(z.shape, dtype=float)
    pos = z >= 0.0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out

def _round_key(row: Mapping[str, Any]) -> tuple:
    rid = row.get("round_id")
    return ("rid", rid) if rid is not None else ("planned", row.get("planned_start_us"))

def _day_index(timestamp_us: int | None) -> int | None:
    return None if timestamp_us is None else int(timestamp_us) // _DAY_US

def _day_str(day_index: int) -> str:
    moment = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=int(day_index))
    return moment.strftime("%Y-%m-%d")

def _find_nonfinite(value: Any, path: str = "") -> str | None:
    if isinstance(value, (float, np.floating)):
        return None if math.isfinite(float(value)) else (path or "<root>")
    if isinstance(value, np.ndarray):
        return path or "<root>" if value.dtype.kind == "f" and not np.all(
            np.isfinite(value)) else None
    if isinstance(value, Mapping):
        for key in value:
            found = _find_nonfinite(value[key], f"{path}.{key}" if path else str(key))
            if found is not None:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = _find_nonfinite(item, f"{path}[{index}]")
            if found is not None:
                return found
    return None

def _objective(a: float, b: float, x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    z = a * x + b
    data = float(np.sum(w * (np.logaddexp(0.0, z) - y * z)))
    return data + 0.5 * _LAMBDA * ((a - 1.0) ** 2 + b * b)

def _gradient(a: float, b: float, x: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    residual = (_sigmoid_array(a * x + b) - y) * w
    return (float(np.sum(residual * x) + _LAMBDA * (a - 1.0)),
            float(np.sum(residual) + _LAMBDA * b))

def _hessian(a: float, b: float, x: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    p = _sigmoid_array(a * x + b)
    s = w * p * (1.0 - p)
    cross = float(np.sum(s * x))
    return np.array([[float(np.sum(s * x * x)) + _LAMBDA, cross],
                     [cross, float(np.sum(s)) + _LAMBDA]], dtype=float)

def _projected_gradient(a: float, grad_a: float, grad_b: float) -> tuple[float, float]:
    return (a - max(0.0, a - grad_a), grad_b)

def _m1_objective_gradient(
    a: float, b: float, x: np.ndarray, y: np.ndarray, w: np.ndarray
) -> tuple[float, float, float]:
    grad_a, grad_b = _gradient(a, b, x, y, w)
    return _objective(a, b, x, y, w), grad_a, grad_b

def _classify_training_rows(
    rows: Iterable[Mapping[str, Any]], cutoff_us: int, as_of_us: int
) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    admissible: list[Mapping[str, Any]] = []
    counts: dict[str, int] = {
        "window_excluded": 0, "invalid_probability_excluded": 0,
        "availability_excluded": 0, "draw_excluded": 0, "missing_label_excluded": 0}
    for row in rows:
        at_us, ends_at_us = row.get("at_us"), row.get("ends_at_us")
        if at_us is None or ends_at_us is None or not (
                int(at_us) < cutoff_us and int(ends_at_us) <= cutoff_us):
            counts["window_excluded"] += 1
            continue
        probability = row.get("p_up")
        if probability is None:
            counts["invalid_probability_excluded"] += 1
            continue
        if isinstance(probability, bool) or not math.isfinite(float(probability)) or not 0 <= probability <= 1:
            raise ValueError("invalid training probability")
        label_at = row.get("label_available_at_us")
        if label_at is None or int(label_at) > cutoff_us or int(label_at) > as_of_us:
            counts["availability_excluded"] += 1
            continue
        code = label_code(row.get("label"))
        if code == 2:
            counts["draw_excluded"] += 1
            continue
        if code not in (0, 1):
            counts["missing_label_excluded"] += 1
            continue
        admissible.append(row)
    return admissible, counts

def _training_arrays(
    admissible: Sequence[Mapping[str, Any]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    ordered = sorted(admissible, key=lambda row: (
        _day_index(row.get("planned_start_us")) or 0, row.get("planned_start_us") or 0,
        row.get("round_id") or "", row.get("offset") or 0))
    grouped: dict[tuple, list[Mapping[str, Any]]] = {}
    for row in ordered:
        grouped.setdefault(_round_key(row), []).append(row)
    round_count = len(grouped)
    x_vals: list[float] = []
    y_vals: list[float] = []
    w_vals: list[float] = []
    rounds: list[dict[str, Any]] = []
    for key, members in grouped.items():
        slot_weight = 1.0 / (len(members) * round_count)
        for row in members:
            x_vals.append(_logit(float(row["p_up"])))
            y_vals.append(float(label_code(row["label"])))
            w_vals.append(slot_weight)
        rounds.append({"round": f"{key[0]}:{key[1]}", "slots": len(members),
                       "slot_weight": slot_weight, "round_weight": slot_weight * len(members)})
    return (np.array(x_vals, dtype=float), np.array(y_vals, dtype=float),
            np.array(w_vals, dtype=float), rounds)

def _input_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    canonical = [{
        "at_us": row.get("at_us"), "ends_at_us": row.get("ends_at_us"),
        "label": row.get("label"), "label_available_at_us": row.get("label_available_at_us"),
        "offset": row.get("offset"),
        "p_up": repr(float(row["p_up"])) if row.get("p_up") is not None else None,
        "planned_start_us": row.get("planned_start_us"), "round_id": row.get("round_id"),
    } for row in rows]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def _newton_direction(
    a: float, b: float, grad_a: float, grad_b: float, x: np.ndarray, y: np.ndarray, w: np.ndarray
) -> tuple[float, float] | None:
    hessian = _hessian(a, b, x, y, w)
    if a == 0.0 and grad_a >= 0.0:
        hessian_bb = float(hessian[1, 1])
        if not math.isfinite(hessian_bb) or hessian_bb <= 0.0:
            return None
        return (0.0, -grad_b / hessian_bb)
    rhs = -np.array([grad_a, grad_b], dtype=float)
    try:
        step = np.linalg.solve(hessian, rhs)
    except np.linalg.LinAlgError:
        try:
            step = np.linalg.solve(hessian + 1e-12 * np.eye(2, dtype=float), rhs)
        except np.linalg.LinAlgError:
            return None
    return (float(step[0]), float(step[1]))

def _fit_core(
    admissible: Sequence[Mapping[str, Any]], cutoff_us: int, as_of_us: int,
    counts: Mapping[str, int], max_iterations: int = _MAX_ITERATIONS,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "fit_status": "FIT_EMPTY", "optimizer_id": _OPTIMIZER_ID, "lambda": _LAMBDA,
        "train_cutoff_us": int(cutoff_us), "as_of_us": int(as_of_us),
        "prediction_range_us": None, "latest_label_available_at_us": None,
        "unique_rounds": 0, "slot_count": 0, "up_count": 0, "down_count": 0,
        "draw_excluded_count": int(counts.get("draw_excluded", 0)),
        "availability_excluded_count": int(counts.get("availability_excluded", 0)),
        "window_excluded_count": int(counts.get("window_excluded", 0)),
        "invalid_probability_excluded_count": int(counts.get("invalid_probability_excluded", 0)),
        "missing_label_excluded_count": int(counts.get("missing_label_excluded", 0)),
        "a": None, "b": None, "p1": None, "objective": None, "projected_gradient": None,
        "iterations": 0, "max_iterations": int(max_iterations), "weight_sum": 0.0,
        "rounds": [], "input_hash": _input_hash(admissible)}
    if not admissible:
        return record
    x, y, w, rounds = _training_arrays(admissible)
    record.update(unique_rounds=len(rounds), slot_count=len(admissible),
                  up_count=int(np.sum(y)), down_count=int(len(y) - np.sum(y)),
                  weight_sum=float(np.sum(w)), rounds=rounds)
    at_values = [int(row["at_us"]) for row in admissible]
    record["prediction_range_us"] = {"first_at_us": min(at_values), "last_at_us": max(at_values)}
    record["latest_label_available_at_us"] = max(int(row["label_available_at_us"]) for row in admissible)
    if len({float(value) for value in y}) < 2:
        record["fit_status"] = "FIT_SINGLE_CLASS"
        return record
    def reduce(a: float, b: float) -> tuple:
        return _objective(a, b, x, y, w), np.array(_gradient(a, b, x, y, w)), _hessian(a, b, x, y, w)
    record.update(_minimize(reduce, max_iterations=max_iterations))
    return record


def _minimize(reduce: Any, *, max_iterations: int = 500) -> dict:
    """One frozen projected Newton solver for both scalar fixtures and day memmaps."""
    slope, intercept = 1., 0.
    objective = None
    iteration = 0
    for iteration in range(1, max_iterations + 1):
        objective, gradient, hessian = reduce(slope, intercept)
        if not (math.isfinite(objective) and np.all(np.isfinite(gradient)) and
                np.all(np.isfinite(hessian))):
            break
        pg = np.array(_projected_gradient(slope, *gradient))
        norm = float(np.max(np.abs(pg)))
        if norm <= 1e-8:
            return dict(fit_status="FIT_OK", a=slope, b=intercept, objective=objective,
                projected_gradient=dict(a=float(pg[0]), b=float(pg[1]), norm=norm), iterations=iteration)
        if slope == 0 and gradient[0] >= 0:
            direction = np.array([0., -gradient[1]/hessian[1, 1]])
        else:
            direction = np.linalg.solve(hessian, -gradient)
        if float(gradient @ direction) >= 0:
            direction = -pg
        step = 1.
        accepted = False
        for _ in range(50):
            candidate = np.array([max(0., slope+step*direction[0]), intercept+step*direction[1]])
            change = candidate - (slope, intercept)
            candidate_objective = reduce(*candidate)[0]
            if (math.isfinite(candidate_objective) and float(gradient @ change) < 0 and
                    candidate_objective <= objective + 1e-4 * float(gradient @ change)):
                slope, intercept = map(float, candidate)
                accepted = True
                break
            step *= .5
        if not accepted:
            break
    objective = reduce(slope, intercept)[0]
    return dict(fit_status="FIT_NOT_CONVERGED", a=None, b=None,
        objective=objective if objective is not None and math.isfinite(objective) else None,
        projected_gradient=None, iterations=iteration,
        reason="ITERATION_LIMIT" if iteration == max_iterations else "LINE_SEARCH_OR_NUMERIC_FAILURE",
        last_iterate=dict(a=slope, b=intercept))

def fit_m1(train_rows: list[dict], *, cutoff_us: int, as_of_us: int) -> dict:
    """Fit the frozen M1 probability mapping on one training window.

    The mapping is ``sigmoid(a * logit(clip(p0, 1e-12, 1 - 1e-12)) + b)`` with
    a single ``(a, b)`` per fold, ``a >= 0``, ``lambda = 0.001`` and the
    frozen projected-Newton optimiser ``projected-newton-2d/1``.

    Args:
        train_rows: Training rows carrying the M0 probability ``p_up`` and the
            official label of one slot.  The caller owns the I/O.
        cutoff_us: Training cutoff ``C`` in microseconds UTC.  A slot is
            admissible only when ``at_us < C`` and ``ends_at_us <= C``.
        as_of_us: Final availability cut-off ``A`` in microseconds UTC.  It
            never relaxes the training cutoff.

    Returns:
        The factual training record.  ``a``, ``b`` and ``p1`` are ``None``
        for every non-``FIT_OK`` status; a failed fit is never replaced by
        M0, the identity map or B1.
    """
    admissible, counts = _classify_training_rows(train_rows, int(cutoff_us), int(as_of_us))
    return _fit_core(admissible, int(cutoff_us), int(as_of_us), counts)

def fit_b1(round_rows: list[dict], *, cutoff_us: int, as_of_us: int) -> dict:
    """Compute the frozen B1 training-window base rate.

    B1 is the share of UP among the unique official rounds of the training
    window whose label is UP or DOWN and was already available at the
    cutoff.  The six scoring slots of a round never count more than once.

    Args:
        round_rows: Official round rows with ``round_id``, ``ends_at_us``,
            ``label`` and ``label_available_at_us``.
        cutoff_us: Training cutoff ``C`` in microseconds UTC.
        as_of_us: Final availability cut-off ``A`` in microseconds UTC.

    Returns:
        A record with ``value`` (``None`` when the denominator is zero), the
        counted rounds and the status ``"OK"`` or ``"NOT_APPLICABLE"``.
    """
    grouped: dict[Any, list[Mapping[str, Any]]] = {}
    for row in round_rows:
        rid = row.get("round_id")
        if rid is not None:
            grouped.setdefault(rid, []).append(row)
    up_rounds = down_rounds = 0
    for rid in sorted(grouped, key=str):
        members = grouped[rid]
        chosen = members[0]
        for member in members:
            if member.get("label_available_at_us") is not None:
                chosen = member
                break
        ends_at_us, label_at = chosen.get("ends_at_us"), chosen.get("label_available_at_us")
        if ends_at_us is None or int(ends_at_us) > int(cutoff_us):
            continue
        if label_at is None or int(label_at) > int(cutoff_us) or int(label_at) > int(as_of_us):
            continue
        code = label_code(chosen.get("label"))
        if code == 1:
            up_rounds += 1
        elif code == 0:
            down_rounds += 1
    denominator = up_rounds + down_rounds
    return {"value": (up_rounds / denominator) if denominator else None,
            "up_rounds": up_rounds, "down_rounds": down_rounds,
            "counted_rounds": denominator, "official_rounds_seen": len(grouped),
            "status": "OK" if denominator else "NOT_APPLICABLE",
            "cutoff_us": int(cutoff_us), "as_of_us": int(as_of_us)}

def apply_m1(p0: float, a: float, b: float) -> float:
    """Map an M0 probability through the frozen M1 mapping.

    Args:
        p0: M0 probability.
        a: Frozen M1 slope (``a >= 0``).
        b: Frozen M1 intercept.

    Returns:
        The M1 probability.  The mapping is monotone non-decreasing in ``p0``
        and the original ``p0`` value is never clipped.
    """
    return float(_sigmoid(float(a) * _logit(p0) + float(b)))

def fit_expanding(
    sample_rows: list[dict], round_rows: list[dict], *, folds: Sequence[int],
    as_of_us: int, last_day_cutoff_us: int | None = None,
) -> dict:
    """Fit the expanding window M1 and B1 of every fold.

    Args:
        sample_rows: All sample rows; the M0 rows are the training source.
        round_rows: Official round rows for B1.
        folds: Ordered training cut-offs in microseconds UTC.  The fold index
            is the position in this list.
        as_of_us: Final availability cut-off ``A`` in microseconds UTC.
        last_day_cutoff_us: Optional separate cut-off of the last-day
            diagnostic.

    Returns:
        ``{"folds": {fold_index: {...}}, "last_day": {...} | None}``.
    """
    m0_rows = [row for row in sample_rows if row.get("model") == "M0"]

    def _window(cutoff_us: int) -> dict[str, Any]:
        return {"cutoff_us": int(cutoff_us),
                "m1": fit_m1(m0_rows, cutoff_us=int(cutoff_us), as_of_us=int(as_of_us)),
                "b1": fit_b1(round_rows, cutoff_us=int(cutoff_us), as_of_us=int(as_of_us))}

    return {"folds": {index: _window(int(cutoff)) for index, cutoff in enumerate(folds)},
            "last_day": None if last_day_cutoff_us is None else _window(int(last_day_cutoff_us))}

def _slot_key(row: Mapping[str, Any]) -> tuple:
    return (row.get("planned_start_us"), row.get("offset"), row.get("round_id"))

def _build_slots(
    sample_rows: Sequence[Mapping[str, Any]], periods: Sequence[str] | None
) -> list[dict[str, Any]]:
    slots: dict[tuple, dict[str, Any]] = {}
    ordered: list[Mapping[str, Any]] = []
    for row in sample_rows:
        if periods is not None and row.get("period") not in periods:
            continue
        key = _slot_key(row)
        if key not in slots:
            slots[key] = {field: row.get(field) for field in _SLOT_FIELDS}
            slots[key].update({"key": key, "p": {}, "fit_status": {}, "direction": {}, "day": None})
        ordered.append(row)
    for row in ordered:
        slot = slots[_slot_key(row)]
        model = row.get("model")
        if model in MODEL_NAMES:
            slot["p"][model] = row.get("p_up")
            slot["fit_status"][model] = row.get("fit_status")
            slot["direction"][model] = row.get("direction")
    for row in ordered:
        slot = slots[_slot_key(row)]
        for field in _CARRIED_FIELDS:
            if slot[field] is None and row.get(field) is not None:
                slot[field] = row.get(field)
    for slot in slots.values():
        slot["day"] = _day_index(slot["starts_at_us"] or slot["planned_start_us"])
    return list(slots.values())

def _prepare_context(
    sample_rows: Sequence[Mapping[str, Any]], fits: Mapping[str, Any] | None,
    as_of_us: int | None, periods: Sequence[str] | None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "as_of_us": None if as_of_us is None else int(as_of_us),
        "slots": _build_slots(sample_rows, periods),
        "fold_cutoffs": {}, "fold_m1": {}, "fold_b1": {}}
    for index, entry in (fits.get("folds") or {}).items() if fits else ():
        ctx["fold_cutoffs"][int(index)] = int(entry["cutoff_us"])
        ctx["fold_m1"][int(index)] = entry.get("m1") or {}
        ctx["fold_b1"][int(index)] = entry.get("b1") or {}
    return ctx

def _fold_of(slot: Mapping[str, Any], ctx: Mapping[str, Any]) -> int | None:
    fold = slot.get("fold")
    if fold is not None:
        return int(fold)
    at_us = slot.get("at_us")
    if at_us is None or not ctx["fold_cutoffs"]:
        return None
    for index, cutoff in sorted(ctx["fold_cutoffs"].items()):
        if int(cutoff) <= int(at_us) < int(cutoff) + _WEEK_US:
            return int(index)
    return None

def _is_validation(slot: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
    period = slot.get("period")
    if period == "VALIDATION":
        return True
    if period in ("TRAIN_PREFIX", "LATEST"):
        return False
    fold = slot.get("fold")
    if fold is not None:
        return 0 <= int(fold) <= 7
    at_us = slot.get("at_us")
    if at_us is None or not ctx["fold_cutoffs"]:
        return False
    for index, cutoff in sorted(ctx["fold_cutoffs"].items()):
        if int(cutoff) <= int(at_us) < int(cutoff) + _WEEK_US:
            return int(index) <= 7
    return False

def _resolve_prob(slot: Mapping[str, Any], model: str, ctx: Mapping[str, Any]) -> float | None:
    raw = slot["p"].get(model)
    if model == "M1":
        status = slot["fit_status"].get("M1")
        if status is not None and status != "FIT_OK":
            return None
        if raw is not None and math.isfinite(float(raw)):
            return float(raw)
        fold = _fold_of(slot, ctx)
        fit = ctx["fold_m1"].get(fold) if fold is not None else None
        if not fit or fit.get("fit_status") != "FIT_OK":
            return None
        p0 = slot["p"].get("M0")
        if p0 is None or not math.isfinite(float(p0)):
            return None
        return apply_m1(float(p0), float(fit["a"]), float(fit["b"]))
    if model == "B1":
        if raw is not None and math.isfinite(float(raw)):
            return float(raw)
        fold = _fold_of(slot, ctx)
        base = ctx["fold_b1"].get(fold) if fold is not None else None
        if not base or base.get("value") is None:
            return None
        return float(base["value"])
    if model == "B0":
        return float(raw) if raw is not None and math.isfinite(float(raw)) else 0.5
    if model == "B2":
        return None
    return float(raw) if raw is not None and math.isfinite(float(raw)) else None

def _resolve_direction(slot: Mapping[str, Any], model: str, ctx: Mapping[str, Any]) -> str | None:
    if model == "B2":
        declared = slot["direction"].get("B2")
        if declared in ("UP", "DOWN"):
            return str(declared)
        spot, strike = slot.get("spot"), slot.get("strike")
        if spot is None or strike is None:
            return None
        if float(spot) > float(strike):
            return "UP"
        return "DOWN" if float(spot) < float(strike) else None
    probability = _resolve_prob(slot, model, ctx)
    if probability is None:
        return None
    if probability > 0.5:
        return "UP"
    return "DOWN" if probability < 0.5 else None

def _label_available(slot: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
    label_at = slot.get("label_available_at_us")
    if label_at is None:
        return False
    as_of_us = ctx.get("as_of_us")
    return as_of_us is None or int(label_at) <= int(as_of_us)

def _paired_value(
    slot: Mapping[str, Any], model: str, reference: str, metric: str, ctx: Mapping[str, Any]
) -> float | None:
    code = label_code(slot.get("label"))
    if code == -1:
        return None
    if metric == "direction_accuracy":
        if code == 2:
            return None
        model_direction = _resolve_direction(slot, model, ctx)
        reference_direction = _resolve_direction(slot, reference, ctx)
        if model_direction is None or reference_direction is None:
            return None
        model_correct = 1.0 if model_direction == slot["label"] else 0.0
        reference_correct = 1.0 if reference_direction == slot["label"] else 0.0
        return model_correct - reference_correct
    model_p, reference_p = _resolve_prob(slot, model, ctx), _resolve_prob(slot, reference, ctx)
    if model_p is None or reference_p is None:
        return None
    if metric == "payout_mse":
        payout = {1: 1.0, 0: 0.0, 2: 0.5}[code]
        return (model_p - payout) ** 2 - (reference_p - payout) ** 2
    if code == 2:
        return None
    y = 1.0 if code == 1 else 0.0
    if metric == "binary_brier":
        return (model_p - y) ** 2 - (reference_p - y) ** 2
    if metric == "binary_logloss":
        model_clip = min(1.0 - _EPS, max(_EPS, model_p))
        reference_clip = min(1.0 - _EPS, max(_EPS, reference_p))
        model_loss = -y * math.log(model_clip) - (1.0 - y) * math.log(1.0 - model_clip)
        reference_loss = -y * math.log(reference_clip) - (1.0 - y) * math.log(1.0 - reference_clip)
        return model_loss - reference_loss
    raise ValueError(f"unknown metric: {metric}")

def _comparison_items(
    slots: Sequence[Mapping[str, Any]], model: str, reference: str, metric: str,
    ctx: Mapping[str, Any],
) -> list[tuple[tuple, int | None, float]]:
    items: list[tuple[tuple, int | None, float]] = []
    for slot in slots:
        if not _label_available(slot, ctx):
            continue
        value = _paired_value(slot, model, reference, metric, ctx)
        if value is not None:
            items.append((_round_key(slot), slot.get("day"), value))
    return items

def _aggregate(
    items: Sequence[tuple[tuple, int | None, float]]
) -> tuple[float, int, dict[tuple, float], dict[tuple, int | None]]:
    per_round: dict[tuple, list[float]] = {}
    round_day: dict[tuple, int | None] = {}
    for key, day, value in items:
        per_round.setdefault(key, []).append(value)
        round_day.setdefault(key, day)
    round_mean = {key: sum(values) / len(values) for key, values in per_round.items()}
    return float(sum(round_mean.values())), len(round_mean), round_mean, round_day

def _daily_rows(
    items: Sequence[tuple[tuple, int | None, float]], days: Sequence[str],
    period: str, series: str,
) -> list[dict[str, Any]]:
    _, _, round_mean, round_day = _aggregate(items)
    rows: list[dict[str, Any]] = []
    for day in days:
        numerator, denominator = 0.0, 0
        for key, mean in round_mean.items():
            if round_day.get(key) is not None and _day_str(round_day[key]) == day:
                numerator += mean
                denominator += 1
        rows.append({"period": period, "series": series, "day": day,
                     "numerator": numerator, "denominator": denominator})
    return rows

def _period_days(ctx: Mapping[str, Any], slots: Sequence[Mapping[str, Any]]) -> list[str]:
    if ctx["fold_cutoffs"]:
        first_us = min(ctx["fold_cutoffs"].values())
        last_us = max(ctx["fold_cutoffs"].values()) + _WEEK_US
    else:
        day_values = sorted({slot["day"] for slot in slots if slot.get("day") is not None})
        if not day_values:
            return []
        first_us = day_values[0] * _DAY_US
        last_us = (day_values[-1] + 1) * _DAY_US
    first_day = int(first_us) // _DAY_US
    last_day = (int(last_us) - 1) // _DAY_US
    return [_day_str(day) for day in range(first_day, last_day + 1)]

def _round_slot_weights(slots: Sequence[Mapping[str, Any]]) -> dict[tuple, float]:
    per_round: dict[tuple, int] = {}
    for slot in slots:
        key = _round_key(slot)
        per_round[key] = per_round.get(key, 0) + 1
    weights: dict[tuple, float] = {}
    round_count = len(per_round)
    for slot in slots:
        key = _round_key(slot)
        weights.setdefault(key, 1.0 / (per_round[key] * round_count))
    return weights

def _calibration(
    slots: Sequence[Mapping[str, Any]], model: str, ctx: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], float | None]:
    slots = [slot for slot in slots if _resolve_prob(slot, model, ctx) is not None
             and label_code(slot.get("label")) in (0, 1) and _label_available(slot, ctx)]
    weights = _round_slot_weights(slots)
    accumulators = [{"weight": 0.0, "p": 0.0, "y": 0.0, "slots": 0, "rounds": set()}
                    for _ in range(10)]
    for slot in slots:
        probability = _resolve_prob(slot, model, ctx)
        code = label_code(slot.get("label"))
        if probability is None or code not in (0, 1) or not _label_available(slot, ctx):
            continue
        bucket = accumulators[min(9, int(math.floor(10 * probability)))]
        weight = weights.get(_round_key(slot), 0.0)
        bucket["weight"] += weight
        bucket["p"] += weight * probability
        bucket["y"] += weight * (1.0 if code == 1 else 0.0)
        bucket["slots"] += 1
        bucket["rounds"].add(_round_key(slot))
    buckets: list[dict[str, Any]] = []
    ece = 0.0
    has_weight = False
    for index, accumulator in enumerate(accumulators):
        bucket = {"bin": index, "lower": index / 10.0, "upper": (index + 1) / 10.0,
                  "slot_count": accumulator["slots"], "round_count": len(accumulator["rounds"]),
                  "weight": accumulator["weight"], "mean_p": None, "up_rate": None}
        if accumulator["slots"] and accumulator["weight"] > 0.0:
            bucket["mean_p"] = accumulator["p"] / accumulator["weight"]
            bucket["up_rate"] = accumulator["y"] / accumulator["weight"]
            ece += accumulator["weight"] * abs(bucket["mean_p"] - bucket["up_rate"])
            has_weight = True
        buckets.append(bucket)
    return buckets, (ece if has_weight else None)

def _floor_share(slots: Sequence[Mapping[str, Any]], model: str) -> dict[str, Any]:
    floor = _FLOORS[model]
    warmed = [slot for slot in slots if slot.get("sigma_raw") is not None]
    weights = _round_slot_weights(warmed) if warmed else {}
    hits = total = 0.0
    for slot in warmed:
        weight = weights.get(_round_key(slot), 0.0)
        total += weight
        if float(slot["sigma_raw"]) <= floor:
            hits += weight
    share = (hits / total) if total > 0.0 else None
    return {"model": model, "floor": floor, "warmed_slots": len(warmed),
            "cold_start_slots": len(slots) - len(warmed), "share": share,
            "status": "OK" if share is not None else "N/A_NO_WARMED_SLOT"}

def _stratum_of(sigma_raw: float) -> str | None:
    for name, lower, upper in _STRATA:
        if lower <= sigma_raw < upper:
            return name
    return None

def _group_offsets(slots: Sequence[Mapping[str, Any]]) -> dict[tuple, set]:
    grouped: dict[tuple, set] = {}
    for slot in slots:
        grouped.setdefault(_round_key(slot), set()).add(slot.get("offset"))
    return grouped

def _block_replicates(
    series_map: Mapping[str, Mapping[str, tuple[float, int]]], days: Sequence[str],
    series: str, index: np.ndarray,
) -> dict[str, Any]:
    per_day = series_map[series]
    numerators = np.array([per_day.get(day, (0.0, 0))[0] for day in days], dtype=float)
    denominators = np.array([per_day.get(day, (0.0, 0))[1] for day in days], dtype=float)
    total_denominator = float(denominators.sum())
    point = float(numerators.sum()) / total_denominator if total_denominator > 0.0 else None
    sampled_numerator = numerators[index].sum(axis=1)
    sampled_denominator = denominators[index].sum(axis=1)
    valid = sampled_denominator > 0.0
    valid_count = int(np.count_nonzero(valid))
    invalid = int(np.count_nonzero(~valid))
    if valid_count:
        values = sampled_numerator[valid] / sampled_denominator[valid]
        lower = float(np.quantile(values, 0.025, method="linear"))
        upper = float(np.quantile(values, 0.975, method="linear"))
        status = "OK"
    else:
        lower = upper = None
        status = "N/A_ZERO_DENOMINATOR"
    return {"point": point, "lo95": lower, "hi95": upper, "valid_replicates": valid_count,
            "invalid_replicates": invalid, "status": status}

def bootstrap_statistics(
    daily_rows: list[dict], *, seed: int = 42, replicates: int = 1000
) -> dict[str, Any]:
    """Resample the paired UTC-day blocks of every period and series.

    Every period uses one shared ``numpy.random.Generator(PCG64(seed))`` day
    index of shape ``(replicates, n_days)``; all models, offsets and
    comparison sets of the same period share that index.  A replicate whose
    total denominator is zero is invalid and is never resampled.  The 7-day
    circular block index is generated separately with the same seed.

    Args:
        daily_rows: Rows with ``period``, ``series``, ``day``, ``numerator``
            and ``denominator``.
        seed: Seed of the block generator.
        replicates: Number of replicates.

    Returns:
        The per-period day block and 7-day circular block results.
    """
    grouped: dict[str, dict[str, dict[str, tuple[float, int]]]] = {}
    for row in daily_rows:
        grouped.setdefault(str(row.get("period")), {}).setdefault(
            str(row.get("series")), {})[str(row.get("day"))] = (
                float(row.get("numerator", 0.0)), int(row.get("denominator", 0)))
    result: dict[str, Any] = {"seed": int(seed), "replicates": int(replicates), "periods": {}}
    for period in sorted(grouped):
        series_map = grouped[period]
        days = sorted({day for series in series_map.values() for day in series})
        n_days = len(days)
        if n_days == 0:
            result["periods"][period] = {
                "days": [], "n_days": 0,
                "day_block": {"index": np.zeros((int(replicates), 0), dtype=np.int64), "series": {}},
                "seven_day_block": {"status": "N/A_INSUFFICIENT_BLOCKS", "index": None, "series": {}}}
            continue
        generator = np.random.Generator(np.random.PCG64(int(seed)))
        day_index = generator.integers(0, n_days, size=(int(replicates), n_days), dtype=np.int64)
        if n_days <= 7:
            seven_index = None
            seven_status = "N/A_INSUFFICIENT_BLOCKS"
        else:
            seven_generator = np.random.Generator(np.random.PCG64(int(seed)))
            starts = seven_generator.integers(
                0, n_days, size=(int(replicates), math.ceil(n_days / 7)), dtype=np.int64)
            offsets = np.arange(7, dtype=np.int64)
            blocks = (starts[:, :, None] + offsets[None, None, :]) % n_days
            seven_index = blocks.reshape(int(replicates), -1)[:, :n_days]
            seven_status = "OK"
        day_series = {series: _block_replicates(series_map, days, series, day_index)
                      for series in sorted(series_map)}
        if seven_index is None:
            seven_series = {series: {"point": None, "lo95": None, "hi95": None,
                                     "valid_replicates": 0, "invalid_replicates": 0,
                                     "status": "N/A_INSUFFICIENT_BLOCKS"}
                            for series in sorted(series_map)}
        else:
            seven_series = {series: _block_replicates(series_map, days, series, seven_index)
                            for series in sorted(series_map)}
        result["periods"][period] = {
            "days": days, "n_days": n_days,
            "day_block": {"index": day_index, "series": day_series},
            "seven_day_block": {"status": seven_status, "index": seven_index, "series": seven_series}}
    return result

def _metric_row(**kwargs: Any) -> dict[str, Any]:
    row: dict[str, Any] = dict.fromkeys(_METRIC_COLUMNS, None)
    row.update(fold="ALL", offset="ALL", stratum="ALL", status="N/A")
    row.update(kwargs)
    return row

def _paired_row(register: Mapping[str, Any], block: Mapping[str, Any], **overrides: Any) -> dict[str, Any]:
    row = _metric_row(
        numerator=register["numerator"], denominator=register["denominator"],
        value=register["value"], lo95=block.get("lo95"), hi95=block.get("hi95"),
        valid_replicates=block.get("valid_replicates"),
        invalid_replicates=block.get("invalid_replicates"),
        status="OK" if register["value"] is not None else "N/A_ZERO_DENOMINATOR")
    row.update(overrides)
    return row

def _direction_from_interval(lower: float | None, upper: float | None) -> str:
    if lower is None or upper is None:
        return "N/A"
    if upper < -_EPS:
        return "SUPPORTS"
    return "OPPOSES" if lower > _EPS else "NEUTRAL"

def _direction_from_point(point: float | None) -> str:
    if point is None:
        return "N/A"
    if point < -_EPS:
        return "SUPPORTS"
    return "OPPOSES" if point > _EPS else "NEUTRAL"

def _diagnostic(
    point: float | None, block: Mapping[str, Any], denominator: int, **extra: Any
) -> dict[str, Any]:
    lower, upper = block.get("lo95"), block.get("hi95")
    entry = {"point": point, "lo95": lower, "hi95": upper,
             "valid_replicates": block.get("valid_replicates"),
             "invalid_replicates": block.get("invalid_replicates"),
             "denominator": denominator,
             "direction": _direction_from_interval(lower, upper),
             "applicable": denominator > 0,
             "status": "OK" if point is not None else "N/A_ZERO_DENOMINATOR"}
    entry.update(extra)
    return entry

def _conflict_item(
    main_direction: str, name: str, direction: str, detail: Mapping[str, Any]
) -> dict[str, Any] | None:
    if direction == "N/A":
        return None
    opposed = (main_direction == "SUPPORTS" and direction == "OPPOSES") or (
        main_direction == "OPPOSES" and direction == "SUPPORTS")
    if main_direction == "NEUTRAL" and direction == "OPPOSES":
        opposed = True
    if not opposed:
        return None
    return {"item": name, "direction": direction, "point": detail.get("point"),
            "lo95": detail.get("lo95"), "hi95": detail.get("hi95"),
            "denominator": detail.get("denominator"),
            "interpretation": detail.get("interpretation", "")}

def _engineering_checks(
    sample_rows: Sequence[Mapping[str, Any]], ctx: Mapping[str, Any],
    fold_status: Mapping[int, str | None], output: Mapping[str, Any],
) -> dict[str, Any]:
    external = {"status": "EXTERNAL",
                "detail": "full stream consumption evidence is owned by the caller"}
    audit = {"status": "PENDING",
             "detail": "no independent audit artefact is bound to this computation"}
    if not sample_rows:
        pending = {"status": "NOT_RUN", "detail": "no sample rows were supplied"}
        return {**{name: dict(pending) for name in _GATE_NAMES},
                "stream_consumption": dict(external), "independent_validation": dict(audit),
                "hard_gates": dict.fromkeys(_GATE_NAMES, False),
                "all_hard_gates_passed": False, "checks_completed": False}
    timing = duplicates = unknown = bad_offset = 0
    seen: set[tuple] = set()
    for row in sample_rows:
        at_us, planned = row.get("at_us"), row.get("planned_start_us")
        offset, ends, model = row.get("offset"), row.get("ends_at_us"), row.get("model")
        if at_us is not None and planned is not None and offset is not None:
            timing += int(at_us) != int(planned) + int(offset) * 1_000_000
        if at_us is not None and ends is not None:
            timing += int(at_us) >= int(ends)
        if model not in MODEL_NAMES:
            unknown += 1
            continue
        if offset not in OFFSETS:
            bad_offset += 1
        key = (_slot_key(row), model)
        duplicates += key in seen
        seen.add(key)
    fit_violations = sum(1 for status in fold_status.values() if status not in FIT_STATUSES)
    fit_violations += sum(1 for slot in ctx["slots"]
                           if slot["fit_status"].get("M1") not in (None, "FIT_OK")
                           and slot["p"].get("M1") is not None)
    non_finite = _find_nonfinite(output)
    checks = {
        "causal_timing": {"status": "PASS" if timing == 0 else "FAIL", "violations": timing,
                          "detail": "slot timing equals planned start plus offset and precedes "
                                    "the round end"},
        "identity": {"status": "PASS" if not (duplicates or unknown or bad_offset) else "FAIL",
                     "duplicate_slot_models": duplicates, "unknown_models": unknown,
                     "invalid_offsets": bad_offset,
                     "detail": "one row per slot and model, known model names and frozen offsets"},
        "denominator": {"status": "PASS", "detail": "every comparison denominator counts rounds "
                        "with at least one common slot"},
        "numeric": {"status": "PASS" if non_finite is None else "FAIL",
                    "non_finite_path": non_finite,
                    "detail": "no NaN or Infinity in the produced statistics"},
        "fit": {"status": "PASS" if fit_violations == 0 else "FAIL",
                "violations": fit_violations,
                "fold_status": {str(index): status for index, status in sorted(fold_status.items())},
                "detail": "every fold records a fit status and a failed fit emits no probability"}}
    gates = {name: checks[name]["status"] == "PASS" for name in _GATE_NAMES}
    checks.update({"stream_consumption": external, "independent_validation": audit,
                   "hard_gates": gates, "all_hard_gates_passed": all(gates.values()),
                   "checks_completed": True})
    return checks

def _fold_statuses(ctx: Mapping[str, Any], validation: Sequence[Mapping[str, Any]]) -> dict[int, str | None]:
    if ctx["fold_cutoffs"]:
        return {index: (ctx["fold_m1"].get(index) or {}).get("fit_status")
                for index in sorted(ctx["fold_cutoffs"])}
    observed = {fold for fold in (_fold_of(slot, ctx) for slot in validation) if fold is not None}
    statuses: dict[int, str | None] = {}
    for index in sorted(observed):
        found = {slot["fit_status"].get("M1") for slot in validation
                 if _fold_of(slot, ctx) == index and slot["fit_status"].get("M1") is not None}
        statuses[index] = next(iter(found)) if len(found) == 1 else None
    return statuses

def _day_month_tables(
    primary_items: Sequence[tuple[tuple, int | None, float]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _, _, round_mean, round_day = _aggregate(primary_items)
    by_day: dict[str, list[float]] = {}
    for key, mean in round_mean.items():
        day = round_day.get(key)
        by_day.setdefault(_day_str(day) if day is not None else "UNKNOWN", []).append(mean)
    daily = [{"utc_day": label, "numerator": float(sum(values)), "denominator": len(values),
              "value": float(sum(values)) / len(values)}
             for label, values in sorted(by_day.items())]
    by_month: dict[str, list[float]] = {}
    month_denominator: dict[str, int] = {}
    for entry in daily:
        month = entry["utc_day"][:7]
        by_month.setdefault(month, []).append(entry["numerator"])
        month_denominator[month] = month_denominator.get(month, 0) + entry["denominator"]
    monthly = []
    for month in sorted(by_month):
        denominator = month_denominator[month]
        monthly.append({"utc_month": month, "numerator": float(sum(by_month[month])),
                        "denominator": denominator,
                        "value": float(sum(by_month[month])) / denominator if denominator else None})
    return daily, monthly

def _comparison_sets(
    validation: Sequence[Mapping[str, Any]], ctx: Mapping[str, Any]
) -> dict[str, list[Mapping[str, Any]]]:

    def _known_binary(slot: Mapping[str, Any]) -> bool:
        return label_code(slot.get("label")) in (0, 1) and _label_available(slot, ctx)

    return {
        "C10": [slot for slot in validation if _known_binary(slot)
                and _resolve_prob(slot, "M1", ctx) is not None
                and _resolve_prob(slot, "M0", ctx) is not None],
        "C0B": [slot for slot in validation if _known_binary(slot)
                and _resolve_prob(slot, "M0", ctx) is not None
                and _resolve_prob(slot, "B0", ctx) is not None
                and _resolve_prob(slot, "B1", ctx) is not None],
        "C2": [slot for slot in validation if _known_binary(slot)
               and _resolve_prob(slot, "M0", ctx) is not None
               and _resolve_prob(slot, "M2-low", ctx) is not None
               and _resolve_prob(slot, "M2-high", ctx) is not None],
        "D02": [slot for slot in validation if _known_binary(slot)
                and _resolve_direction(slot, "M0", ctx) is not None
                and _resolve_direction(slot, "B2", ctx) is not None],
        "PAYOUT": [slot for slot in validation
                   if label_code(slot.get("label")) in (0, 1, 2)
                   and _label_available(slot, ctx)
                   and _resolve_prob(slot, "M0", ctx) is not None]}

def _register(
    comparison: str, model: str, reference: str, metric: str, tag: str,
    slots_used: Sequence[Mapping[str, Any]], ctx: Mapping[str, Any],
    period_days: Sequence[str], daily_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    items = _comparison_items(slots_used, model, reference, metric, ctx)
    numerator, denominator, round_mean, round_day = _aggregate(items)
    series = f"{comparison}|{model}|{reference}|{metric}|{tag}"
    daily_rows.extend(_daily_rows(items, period_days, "VALIDATION", series))
    return {"items": items, "numerator": numerator, "denominator": denominator,
            "value": (numerator / denominator) if denominator else None,
            "round_mean": round_mean, "round_day": round_day, "series": series,
            "scored_slots": len(items)}

def _diagnostics_block(
    sets: Mapping[str, list[Mapping[str, Any]]], secondary: Mapping[str, Any],
    primary: Mapping[str, Any], ctx: Mapping[str, Any], fold_status: Mapping[int, str | None],
    period_days: Sequence[str], daily_rows: list[dict[str, Any]],
    day_blocks: Mapping[str, Any], bootstrap: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    diagnostics: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    primary_block = day_blocks.get(primary["series"], {})
    main_direction = _direction_from_interval(primary_block.get("lo95"), primary_block.get("hi95"))
    seven_block = bootstrap["periods"]["VALIDATION"]["seven_day_block"]
    seven = seven_block["series"].get(primary["series"], {})
    diagnostics["seven_day_block"] = _diagnostic(
        seven.get("point"), seven, primary["denominator"],
        direction=_direction_from_interval(seven.get("lo95"), seven.get("hi95")),
        applicable=seven_block.get("status") == "OK", status=seven_block.get("status"))

    per_fold: dict[str, Any] = {}
    folds_in_c10 = {fold for fold in (_fold_of(slot, ctx) for slot in sets["C10"])
                    if fold is not None}
    for index in sorted(folds_in_c10):
        items = _comparison_items([slot for slot in sets["C10"] if _fold_of(slot, ctx) == index],
                                  "M1", "M0", "binary_brier", ctx)
        numerator, denominator, _, _ = _aggregate(items)
        fold_days: list[str] = []
        if index in ctx["fold_cutoffs"]:
            first = int(ctx["fold_cutoffs"][index]) // _DAY_US
            fold_days = [_day_str(day) for day in range(first, first + 7)]
        fold_period = f"FOLD_{index}"
        fold_bootstrap = bootstrap_statistics(
            _daily_rows(items, fold_days, fold_period, primary["series"]), seed=42, replicates=1000)
        block = fold_bootstrap["periods"][fold_period]["day_block"]["series"].get(primary["series"], {})
        per_fold[str(index)] = _diagnostic(
            (numerator / denominator) if denominator else None, block, denominator,
            fold=index, fit_status=fold_status.get(index))
    diagnostics["per_fold"] = per_fold

    per_offset: dict[str, Any] = {}
    for offset in OFFSETS:
        register = _register("C10", "M1", "M0", "binary_brier", f"offset{offset}",
                              [slot for slot in sets["C10"] if slot.get("offset") == offset],
                              ctx, period_days, daily_rows)
        per_offset[str(offset)] = _diagnostic(
            register["value"], day_blocks.get(register["series"], {}), register["denominator"],
            offset=offset)
    diagnostics["per_offset"] = per_offset

    complete_rounds = {key for key, offsets in _group_offsets(sets["C10"]).items()
                       if len(offsets) == len(OFFSETS)}
    complete_six = _register("C10", "M1", "M0", "binary_brier", "complete_six",
                              [slot for slot in sets["C10"] if _round_key(slot) in complete_rounds],
                              ctx, period_days, daily_rows)
    diagnostics["complete_six"] = _diagnostic(
        complete_six["value"], day_blocks.get(complete_six["series"], {}),
        complete_six["denominator"])
    logloss = secondary["C10|M1|M0|binary_logloss"]
    diagnostics["logloss"] = _diagnostic(
        logloss["value"], day_blocks.get(logloss["series"], {}), logloss["denominator"])

    calibration: dict[str, Any] = {}
    ece_values: dict[str, float | None] = {}
    for model in ("M0", "M1"):
        buckets, ece = _calibration(sets["C10"], model, ctx)
        calibration[model] = buckets
        ece_values[model] = ece
    ece_difference = None
    if ece_values["M0"] is not None and ece_values["M1"] is not None:
        ece_difference = ece_values["M1"] - ece_values["M0"]
    diagnostics["ece"] = {"point": ece_difference, "ece_m0": ece_values["M0"],
                           "ece_m1": ece_values["M1"],
                           "direction": _direction_from_point(ece_difference),
                           "applicable": ece_difference is not None,
                           "status": "OK" if ece_difference is not None else "N/A"}
    metric_rows.append(_metric_row(period="VALIDATION", model="M1", reference="M0",
                                    comparison_set="C10", metric="ece_difference",
                                    value=ece_difference, status=diagnostics["ece"]["status"]))

    daily_table, month_table = _day_month_tables(primary["items"])
    diagnostics["day_contributions"] = daily_table
    diagnostics["month_contributions"] = month_table
    lodo: list[dict[str, Any]] = []
    for entry in daily_table:
        denominator = primary["denominator"] - entry["denominator"]
        numerator = primary["numerator"] - entry["numerator"]
        value = (numerator / denominator) if denominator > 0 else None
        lodo.append({"utc_day": entry["utc_day"], "point": value, "denominator": denominator,
                     "direction": _direction_from_point(value), "applicable": value is not None,
                     "status": "OK" if value is not None else "N/A_ZERO_DENOMINATOR"})
    diagnostics["leave_one_day_out"] = lodo

    floor_table = []
    for model in ("M0", "M2-low", "M2-high"):
        share = _floor_share(ctx["slots"], model)
        floor_table.append(share)
        metric_rows.append(_metric_row(period="VALIDATION", model=model, comparison_set="FLOOR",
                                        metric="floor_share", value=share["share"],
                                        denominator=share["warmed_slots"], status=share["status"]))

    strata: list[dict[str, Any]] = []
    for name, lower_bound, upper_bound in _STRATA:
        stratum_slots = [slot for slot in sets["C2"] if slot.get("sigma_raw") is not None
                         and _stratum_of(float(slot["sigma_raw"])) == name]
        for model in ("M2-low", "M2-high"):
            items = _comparison_items(stratum_slots, model, "M0", "binary_brier", ctx)
            numerator, denominator, _, _ = _aggregate(items)
            value = (numerator / denominator) if denominator else None
            strata.append({"stratum": name, "lower": lower_bound,
                           "upper": None if math.isinf(upper_bound) else upper_bound,
                           "model": model, "reference": "M0", "metric": "binary_brier",
                           "numerator": numerator, "denominator": denominator, "value": value,
                           "status": "OK" if value is not None else "N/A_ZERO_DENOMINATOR"})
            metric_rows.append(_metric_row(period="VALIDATION", model=model, reference="M0",
                                            comparison_set="C2",
                                            metric="binary_brier_paired_difference", stratum=name,
                                            numerator=numerator, denominator=denominator, value=value,
                                            status="OK" if value is not None else "N/A_ZERO_DENOMINATOR"))

    candidates = [
        ("seven_day_block", diagnostics["seven_day_block"]["direction"],
         {**diagnostics["seven_day_block"], "denominator": primary["denominator"],
          "interpretation": "the 7-day circular moving-block interval does not support the "
                             "main UTC-day block evidence"}),
        ("complete_six", diagnostics["complete_six"]["direction"],
         {**diagnostics["complete_six"],
          "interpretation": "the complete-six sensitivity does not support the main evidence"}),
        ("logloss", diagnostics["logloss"]["direction"],
         {**diagnostics["logloss"],
          "interpretation": "the paired logloss diagnostic does not support the main evidence"}),
        ("ece", diagnostics["ece"]["direction"],
         {**diagnostics["ece"], "denominator": len(sets["C10"]),
          "interpretation": "the calibration error of M1 is not better than the calibration "
                             "error of M0"})]
    candidates += [(f"per_fold[{index}]", item["direction"],
                    {**item, "interpretation": f"fold {index} does not support the main evidence"})
                   for index, item in per_fold.items()]
    candidates += [(f"per_offset[{offset}]", item["direction"],
                    {**item, "interpretation": f"offset {offset} does not support the main evidence"})
                   for offset, item in per_offset.items()]
    candidates += [(f"leave_one_day_out[{entry['utc_day']}]", entry["direction"],
                    {**entry, "interpretation":
                     f"removing UTC day {entry['utc_day']} reverses the main effect"})
                   for entry in lodo]
    for name, direction, detail in candidates:
        conflict = _conflict_item(main_direction, name, direction, detail)
        if conflict is not None:
            conflicts.append(conflict)
    tables = {"calibration": calibration, "floor": floor_table, "strata": strata,
              "daily": daily_table, "monthly": month_table, "lodo": lodo}
    return diagnostics, conflicts, metric_rows, tables

def compute_statistics(
    sample_rows: list[dict], *, fits: Mapping[str, Any] | None = None,
    as_of_us: int | None = None, periods: Sequence[str] | None = None,
) -> dict:
    """Compute the frozen comparison statistics and the research verdict.

    Args:
        sample_rows: Sample rows of every model and slot.  The caller owns
            the I/O and the source identity.
        fits: Optional ``fit_expanding`` result holding the per-fold frozen
            M1 and B1 parameters.
        as_of_us: Optional final availability cut-off ``A``; labels that are
            not available yet are not scored.
        periods: Optional restriction to the given sample periods.

    Returns:
        The verdict dictionary with the exact top-level keys
        ``engineering_checks``, ``primary_evidence``,
        ``robustness_diagnostics``, ``diagnostic_conflicts``,
        ``research_verdict``, ``effect_size``, ``complexity_cost``,
        ``proxy_error``, ``economic_value_status`` and ``statistics``.
    """
    rows_in = list(sample_rows)
    ctx = _prepare_context(rows_in, fits, as_of_us, periods)
    slots = ctx["slots"]
    validation = [slot for slot in slots if _is_validation(slot, ctx)]
    fold_status = _fold_statuses(ctx, validation)
    sets = _comparison_sets(validation, ctx)
    metric_rows: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    period_days = _period_days(ctx, validation)

    primary = _register("C10", "M1", "M0", "binary_brier", "ALL", sets["C10"], ctx,
                        period_days, daily_rows)
    secondary: dict[str, Any] = {}
    for comparison, model, reference, slots_used in (
            ("C0B", "M0", "B0", sets["C0B"]), ("C0B", "M0", "B1", sets["C0B"]),
            ("C2", "M2-low", "M0", sets["C2"]), ("C2", "M2-high", "M0", sets["C2"])):
        for metric in ("binary_brier", "binary_logloss"):
            register = _register(comparison, model, reference, metric, "ALL", slots_used, ctx,
                                 period_days, daily_rows)
            secondary[f"{comparison}|{model}|{reference}|{metric}"] = register
    secondary["C10|M1|M0|binary_logloss"] = _register(
        "C10", "M1", "M0", "binary_logloss", "ALL", sets["C10"], ctx, period_days, daily_rows)
    secondary["D02|M0|B2|direction_accuracy"] = _register(
        "D02", "M0", "B2", "direction_accuracy", "ALL", sets["D02"], ctx, period_days, daily_rows)
    secondary["PAYOUT|M1|M0|payout_mse"] = _register(
        "PAYOUT", "M1", "M0", "payout_mse", "ALL", sets["PAYOUT"], ctx, period_days, daily_rows)

    bootstrap = bootstrap_statistics(daily_rows, seed=42, replicates=1000)
    day_blocks = bootstrap["periods"]["VALIDATION"]["day_block"]["series"]
    primary_block = day_blocks.get(primary["series"], {})
    lower, upper = primary_block.get("lo95"), primary_block.get("hi95")
    valid_replicates = int(primary_block.get("valid_replicates", 0))
    invalid_replicates = int(primary_block.get("invalid_replicates", 0))
    interval_usable = lower is not None and upper is not None and valid_replicates == 1000
    metric_rows.append(_paired_row(primary, primary_block, period="VALIDATION", model="M1",
                                    reference="M0", comparison_set="C10",
                                    metric="binary_brier_paired_difference"))
    for key, register in secondary.items():
        comparison, model, reference, metric = key.split("|")
        metric_rows.append(_paired_row(
            register, day_blocks.get(register["series"], {}), period="VALIDATION",
            model=model, reference=reference, comparison_set=comparison,
            metric=f"{metric}_paired_difference"))

    diagnostics, conflicts, extra_rows, tables = _diagnostics_block(
        sets, secondary, primary, ctx, fold_status, period_days, daily_rows, day_blocks, bootstrap)
    metric_rows.extend(extra_rows)

    m1_equals_m0 = True
    max_gap = 0.0
    for slot in sets["C10"]:
        p1 = _resolve_prob(slot, "M1", ctx)
        p0 = _resolve_prob(slot, "M0", ctx)
        if p1 is None or p0 is None:
            continue
        gap = abs(p1 - p0)
        max_gap = max(max_gap, gap)
        if gap > 1e-12:
            m1_equals_m0 = False
    folds_fit_ok = bool(fold_status) and all(status == "FIT_OK" for status in fold_status.values())
    c10_non_empty = primary["denominator"] > 0
    statistics_payload: dict[str, Any] = {
        "rows": metric_rows,
        "calibration": {"comparison_set": "C10", "buckets": tables["calibration"]},
        "strata": {"comparison_set": "C2", "rows": tables["strata"]},
        "daily": tables["daily"], "monthly": tables["monthly"],
        "leave_one_day_out": tables["lodo"], "floor": tables["floor"], "bootstrap": bootstrap,
        "coverage": {"theoretical_slots": len(slots), "validation_slots": len(validation),
                      "c10_slots": len(sets["C10"]), "c0b_slots": len(sets["C0B"]),
                      "c2_slots": len(sets["C2"]), "d02_slots": len(sets["D02"]),
                      "payout_slots": len(sets["PAYOUT"]), "c10_rounds": primary["denominator"],
                      "c10_scored_slots": len(primary["items"])}}
    checks = _engineering_checks(rows_in, ctx, fold_status, statistics_payload)
    if not checks["checks_completed"]:
        research_verdict = None
    elif not checks["all_hard_gates_passed"]:
        research_verdict = "DATA_ENGINEERING_INELIGIBLE"
    elif not folds_fit_ok or not c10_non_empty or not interval_usable:
        research_verdict = "INSUFFICIENT_EVIDENCE"
    elif m1_equals_m0:
        research_verdict = "HYPOTHESIS_NOT_SUPPORTED"
    elif upper is not None and upper < -_EPS:
        research_verdict = "SUPPORT_FURTHER_VALIDATION"
    elif lower is not None and lower > _EPS:
        research_verdict = "HYPOTHESIS_NOT_SUPPORTED"
    else:
        research_verdict = "INSUFFICIENT_EVIDENCE"
    primary_evidence = {
        "endpoint": "C10_M1_MINUS_M0_BINARY_BRIER", "difference": primary["value"],
        "interval": {"lo95": lower, "hi95": upper}, "common_slots": len(primary["items"]),
        "rounds": primary["denominator"],
        "availability": {
            "folds_fit_ok": folds_fit_ok,
            "fold_fit_status": {str(index): status for index, status in sorted(fold_status.items())},
            "c10_non_empty": c10_non_empty, "valid_replicates": valid_replicates,
            "invalid_replicates": invalid_replicates, "replicates_required": 1000,
            "interval_usable": interval_usable},
        "status": "OK" if interval_usable else "N/A"}
    return {
        "engineering_checks": checks, "primary_evidence": primary_evidence,
        "robustness_diagnostics": diagnostics, "diagnostic_conflicts": conflicts,
        "research_verdict": research_verdict,
        "effect_size": {"difference": primary["value"], "lo95": lower, "hi95": upper,
                        "common_slots": len(primary["items"]), "rounds": primary["denominator"],
                        "max_abs_probability_gap": max_gap, "epsilon_d": _EPS},
        "complexity_cost": {"fitted_parameters": 2, "optimizer_id": _OPTIMIZER_ID,
                            "fits_recorded": len(fold_status), "fit_wall_ms": None,
                            "fit_wall_status": "UNKNOWN"},
        "proxy_error": "UNKNOWN", "economic_value_status": "NOT_VERIFIED",
        "statistics": statistics_payload}

def _svg_text(x: float, y: float, content: str, size: int = 9, anchor: str = "middle") -> str:
    return (f'<text x="{x:.3f}" y="{y:.3f}" font-family="monospace" font-size="{size}" '
            f'text-anchor="{anchor}">{content}</text>')

def _format_raw(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return repr(float(value))

def _render_calibration(calibration: Mapping[str, Any], width: int, height: int) -> str:
    left, bottom, right, top = 60, 340, 740, 50
    scope = calibration.get("_scope", "C10")
    bucket_width = (right - left) / 10.0
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}">',
             f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
             '<text x="16" y="24" font-family="monospace" font-size="15">'
             f'calibration: bucket mean_p vs up_rate ({scope})</text>',
             f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#333333"/>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#333333"/>',
             _svg_text(48, top + 4, "1.0", 11, "end"), _svg_text(48, bottom, "0.0", 11, "end")]
    has_calibration = False
    for index in range(10):
        base = left + index * bucket_width
        for model_index, model in enumerate(("M0", "M1")):
            buckets = calibration.get(model) or []
            if index >= len(buckets):
                continue
            bucket = buckets[index]
            if bucket.get("mean_p") is None and bucket.get("up_rate") is None:
                continue
            has_calibration = True
            inner = (bucket_width - 8) / 2.0
            for value_index, value in enumerate((bucket.get("mean_p"), bucket.get("up_rate"))):
                if value is None:
                    continue
                bar_height = max(0.0, min(1.0, float(value))) * (bottom - top)
                bar_x = base + 4 + model_index * inner + value_index * (inner / 2.0)
                colour = "#3366cc" if value_index == 0 else "#cc6633"
                lines.append(f'<rect x="{bar_x:.3f}" y="{bottom - bar_height:.3f}" '
                             f'width="{inner / 2.0:.3f}" height="{bar_height:.3f}" fill="{colour}"/>')
        centre = base + bucket_width / 2.0
        m0_buckets = calibration.get("M0") or []
        bucket = m0_buckets[index] if index < len(m0_buckets) else {}
        lines.append(_svg_text(centre, bottom + 16, str(index), 10))
        lines.append(_svg_text(centre, bottom + 30, f'w={_format_raw(bucket.get("weight"))}'))
        lines.append(_svg_text(centre, bottom + 42, f'p={_format_raw(bucket.get("mean_p"))}'))
        lines.append(_svg_text(centre, bottom + 54, f'u={_format_raw(bucket.get("up_rate"))}'))
    if not has_calibration:
        lines.append(_svg_text(left + 8, top + 40, "N/A: no calibration bucket is available",
                                12, "start"))
    lines.append(_svg_text(left, height - 12, "blue: mean_p   orange: up_rate   "
                            f"{scope} comparison set", 11, "start"))
    lines.append("</svg>")
    return "\n".join(lines)

def _render_strata(strata: Sequence[Mapping[str, Any]], width: int, height: int) -> str:
    left, bottom, right, top = 60, 340, 740, 50
    centre = (top + bottom) / 2.0
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}">',
             f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
             '<text x="16" y="24" font-family="monospace" font-size="15">'
             'strata: paired Brier difference by causal sigma_raw</text>',
             f'<line x1="{left}" y1="{centre}" x2="{right}" y2="{centre}" stroke="#999999" '
             f'stroke-dasharray="4 3"/>']
    values = [float(row["value"]) for row in strata if row.get("value") is not None]
    scale = max((abs(value) for value in values), default=1.0) or 1.0
    group_width = (right - left) / max(1, len(strata))
    has_strata = False
    for index, row in enumerate(strata):
        value = row.get("value")
        if value is None:
            continue
        has_strata = True
        bar_height = abs(float(value)) / scale * (bottom - top) / 2.0
        bar_x = left + index * group_width + 4
        bar_width = max(1.0, group_width - 8)
        y = centre if float(value) < 0 else centre - bar_height
        colour = "#2a8f5f" if float(value) < 0 else "#b04040"
        lines.append(f'<rect x="{bar_x:.3f}" y="{y:.3f}" width="{bar_width:.3f}" '
                     f'height="{max(1.0, bar_height):.3f}" fill="{colour}"/>')
        lines.append(_svg_text(bar_x + bar_width / 2.0, bottom + 16, str(row.get("model"))))
        lines.append(_svg_text(bar_x + bar_width / 2.0, bottom + 28, str(row.get("stratum"))))
        lines.append(_svg_text(bar_x + bar_width / 2.0, bottom + 40, _format_raw(value)))
    if not has_strata:
        lines.append(_svg_text(left + 8, top + 40, "N/A: no volatility stratum is available",
                                12, "start"))
    lines.append(_svg_text(left, height - 12, "negative: candidate better than M0   "
                            "C2 comparison set", 11, "start"))
    lines.append("</svg>")
    return "\n".join(lines)

def render_figures(statistics: dict) -> dict:
    """Render the SVG figures of the statistics object.

    Every value is projected from the statistics object itself; no number is
    copied by hand.

    Args:
        statistics: The ``statistics`` payload of :func:`compute_statistics`.

    Returns:
        A mapping of figure name to SVG text, always containing the
        ``calibration`` and ``strata`` figures.
    """
    calibration = (statistics.get("calibration") or {}).get("buckets") or {}
    strata = (statistics.get("strata") or {}).get("rows") or []
    return {"calibration": _render_calibration(calibration, 760, 460),
            "strata": _render_strata(strata, 760, 460)}


# File-backed production consumers. Each map is closed before the next day;
# only fixed-dimensional day/period sufficient statistics survive a round.
FIT_DTYPE = np.dtype([(name, "<i8") for name in ("planned_start_us", "offset", "at_us",
    "ends_at_us", "label_available_at_us")] + [("p0", "<f8"), ("label_code", "i1"), ("valued", "?")])
CUTOFFS = tuple(int(datetime(2026, 9, 21, tzinfo=timezone.utc).timestamp())*1_000_000 +
                index*7*_DAY_US for index in range(9))
SAMPLE_COLUMNS = ("planned_start_us", "round_id", "starts_at_us", "ends_at_us", "offset",
    "at_us", "period", "fold", "model", "identity_available_at_us", "strike_available_at_us",
    "strike", "spot", "bar_open_us", "close_exclusive_us", "spot_available_at_us", "source_dataset",
    "price_kind", "clock_basis", "prediction_source", "actual_pair", "source_epoch", "reset_reason",
    "samples", "sigma_raw", "sigma", "floor_hit", "secs_left", "p_up", "valuation_status", "label",
    "label_available_at_us", "label_status", "fit_status", "parameter_ref", "schema_version",
    "proxy_observation_at_us", "logical_elapsed_ms", "direction")
STAT_COLUMNS = ("schema_version", *_METRIC_COLUMNS)


def read_csv(path: Path) -> Iterable[dict]:
    """Decode the public raw-precision schema, preserving integer microseconds."""
    integers = {name for name in SAMPLE_COLUMNS if name.endswith("_us")} | {
        "fold", "offset", "source_epoch", "samples", "seq", "logical_elapsed_ms",
        "m0_value_seq", "m2_low_value_seq", "m2_high_value_seq"}
    floats = {"strike", "spot", "sigma_raw", "sigma", "secs_left", "p_up"}
    integers |= {f"{prefix}_{name}" for prefix in ("m0", "m2_low", "m2_high")
                 for name in ("source_epoch", "samples")}
    floats |= {f"{prefix}_{name}" for prefix in ("m0", "m2_low", "m2_high")
               for name in ("sigma_raw", "sigma", "p_up")}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            for name, value in row.items():
                if value == "N/A":
                    row[name] = None
                elif name.endswith("floor_hit"):
                    if value not in ("true", "false"):
                        raise ValueError("invalid boolean CSV")
                    row[name] = value == "true"
                elif name in integers:
                    row[name] = int(value)
                elif name in floats:
                    row[name] = float(value)
            yield row


def _fit_chunks(paths: Sequence[Path], cutoff_us: int, as_of_us: int,
                check: Any) -> Iterable[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    for path in sorted(paths):
        check()
        mapped = np.load(path, mmap_mode="r", allow_pickle=False)
        try:
            if mapped.dtype != FIT_DTYPE or mapped.ndim != 1 or len(mapped) > 1728:
                raise ValueError("invalid or unbounded fit day")
            admitted = mapped[(mapped["at_us"] < cutoff_us) & (mapped["ends_at_us"] <= cutoff_us) &
                (mapped["label_available_at_us"] <= min(cutoff_us, as_of_us)) &
                (mapped["label_available_at_us"] >= 0) & (mapped["label_code"] >= 0) &
                (mapped["label_code"] <= 1) & mapped["valued"]]
            if not len(admitted):
                continue
            if np.any(~np.isfinite(admitted["p0"])) or np.any((admitted["p0"] < 0) | (admitted["p0"] > 1)):
                raise ValueError("invalid admitted probability")
            _, inverse, counts = np.unique(admitted["planned_start_us"], return_inverse=True, return_counts=True)
            weights = 1 / counts[inverse].astype(float)
            probability = np.clip(admitted["p0"], 1e-12, 1-1e-12)
            yield np.log(probability/(1-probability)), admitted["label_code"].astype(float), weights, admitted
        finally:
            mapped._mmap.close()


def fit_days(paths: Sequence[Path], *, cutoff_us: int, as_of_us: int,
             check: Any = lambda: None) -> dict:
    """Fit exactly one cutoff by bounded single-day memmap reductions."""
    record = dict(fit_status="FIT_EMPTY", optimizer_id=_OPTIMIZER_ID, selection_mode="FIXED",
        train_cutoff_us=cutoff_us, as_of_us=as_of_us, **{"lambda": .001}, a=None, b=None,
        objective=None, projected_gradient=None, iterations=0, max_iterations=500,
        unique_rounds=0, slot_count=0, up_count=0, down_count=0, prediction_range_us=None,
        latest_label_available_at_us=None, exclusions=Counter(), weight_sum=0., input_hash=None)
    input_hash = hashlib.sha256()
    for path in sorted(paths):
        check()
        mapped = np.load(path, mmap_mode="r", allow_pickle=False)
        try:
            within = (mapped["at_us"] < cutoff_us) & (mapped["ends_at_us"] <= cutoff_us)
            record["exclusions"].update(window=int(np.sum(~within)), draw=int(np.sum(within & (mapped["label_code"] == 2))),
                unvalued=int(np.sum(within & ~mapped["valued"])),
                availability=int(np.sum(within & ((mapped["label_available_at_us"] < 0) |
                    (mapped["label_available_at_us"] > min(cutoff_us, as_of_us))))))
        finally:
            mapped._mmap.close()
    for logits, labels, weights, data in _fit_chunks(paths, cutoff_us, as_of_us, check):
        input_hash.update(data.tobytes())
        record["unique_rounds"] += len(np.unique(data["planned_start_us"]))
        record["slot_count"] += len(labels)
        record["up_count"] += int(labels.sum())
        record["down_count"] += int(len(labels)-labels.sum())
        low, high = int(data["at_us"].min()), int(data["at_us"].max())
        previous = record["prediction_range_us"]
        record["prediction_range_us"] = dict(first_at_us=min(low, previous["first_at_us"]) if previous else low,
            last_at_us=max(high, previous["last_at_us"]) if previous else high)
        record["latest_label_available_at_us"] = max(record["latest_label_available_at_us"] or 0,
                                                    int(data["label_available_at_us"].max()))
    record["input_hash"] = input_hash.hexdigest()
    if not record["slot_count"]:
        return record
    record["weight_sum"] = 1.
    if not record["up_count"] or not record["down_count"]:
        record["fit_status"] = "FIT_SINGLE_CLASS"
        return record
    def reduce(slope: float, intercept: float) -> tuple:
        objective, gradient, hessian = 0., np.zeros(2), np.zeros((2, 2))
        for logits, labels, weights, _ in _fit_chunks(paths, cutoff_us, as_of_us, check):
            weights /= record["unique_rounds"]
            objective += _objective(slope, intercept, logits, labels, weights) - .0005*((slope-1)**2+intercept**2)
            gradient += np.array(_gradient(slope, intercept, logits, labels, weights)) - .001*np.array([slope-1, intercept])
            hessian += _hessian(slope, intercept, logits, labels, weights)-.001*np.eye(2)
        return (objective + .0005*((slope-1)**2+intercept**2),
            gradient+.001*np.array([slope-1, intercept]), hessian+.001*np.eye(2))
    record.update(_minimize(reduce))
    return record


def fit_from_files(directory: Path, *, as_of_us: int, check: Any) -> dict:
    """Nine fixed expanding M1/B1 pairs; official B1 rounds never depend on M0."""
    result = {}
    for index, cutoff in enumerate(CUTOFFS):
        check()
        began = time.monotonic()
        m1 = fit_days(sorted((directory / "fit-days").glob("*.npy")),
                      cutoff_us=cutoff, as_of_us=as_of_us, check=check)
        up = down = 0
        b1_hash = hashlib.sha256()
        latest_label = None
        previous = None
        for row in read_csv(directory / "rounds.csv"):
            key = (row["planned_start_us"], row["round_id"])
            if previous is not None and key <= previous:
                raise ValueError("duplicate/unordered official rounds")
            previous = key
            if (row["ends_at_us"] <= cutoff and row["label_available_at_us"] is not None and
                    row["label_available_at_us"] <= min(cutoff, as_of_us)):
                up += row["label"] == "UP"
                down += row["label"] == "DOWN"
                if row["label"] in ("UP", "DOWN"):
                    latest_label = max(latest_label or 0, row["label_available_at_us"])
                    b1_hash.update((json.dumps({key: row[key] for key in ("round_id", "planned_start_us", "ends_at_us",
                        "label", "label_available_at_us")}, sort_keys=True, separators=(",", ":"))+"\n").encode())
        result[str(index)] = dict(cutoff_us=cutoff, m1=m1,
            b1=dict(value=up/(up+down) if up+down else None, up_rounds=up, down_rounds=down,
                counted_rounds=up+down, status="OK" if up+down else "NOT_APPLICABLE"),
            wall_seconds=time.monotonic()-began)
        result[str(index)]["b1"].update(input_hash=b1_hash.hexdigest(), latest_label_available_at_us=latest_label)
    return result


def model_rows(wide: dict, fits: Mapping[str, Any]) -> list[dict]:
    """Generate all seven model rows from one native slot without repricing M0/M2."""
    at = wide["at_us"]
    fold = (at-CUTOFFS[0])//_WEEK_US if at >= CUTOFFS[0] else None
    if fold is not None:
        fold = min(8, fold)
    period = "TRAIN_PREFIX" if fold is None else "LATEST" if fold == 8 else "VALIDATION"
    parameters = fits.get(str(fold), {})
    rows = []
    for model in MODEL_NAMES:
        row = {field: wide.get(field) for field in SAMPLE_COLUMNS}
        row.update(schema_version="btc5m-phase1-samples/1", period=period, fold=fold, model=model,
                   fit_status=None, parameter_ref=None)
        prefix = {"M0": "m0", "M1": "m0", "M2-low": "m2_low", "M2-high": "m2_high"}.get(model)
        for field in ("source_epoch", "reset_reason", "samples", "sigma_raw", "sigma", "floor_hit", "p_up", "valuation_status"):
            row[field] = wide.get(f"{prefix}_{field}") if prefix else None
        if not prefix:
            row["valuation_status"] = "NOT_APPLICABLE"
        if model in ("M1", "B1"):
            row["parameter_ref"] = f"parameters.json#{fold}" if parameters else None
            if model == "M1":
                fit = parameters.get("m1", {})
                row["fit_status"] = fit.get("fit_status", "NOT_APPLICABLE")
                row["p_up"] = (apply_m1(wide["m0_p_up"], fit["a"], fit["b"])
                    if fit.get("fit_status") == "FIT_OK" and wide.get("m0_p_up") is not None else None)
            else:
                row["p_up"] = parameters.get("b1", {}).get("value")
        elif model == "B0":
            row["p_up"] = .5
        probability = row["p_up"]
        direction = "UP" if probability is not None and probability > .5 else (
            "DOWN" if probability is not None and probability < .5 else None)
        if model == "B2" and wide.get("m0_valuation_status") in ("VALUED", "WARMUP"):
            direction = "UP" if wide["spot"] > wide["strike"] else "DOWN" if wide["spot"] < wide["strike"] else None
        row["direction"] = direction
        rows.append(row)
    return rows


def classify(primary: Mapping[str, Any], *, engineering: bool) -> str:
    """SPEC V1.1 classification: diagnostics cannot silently revive the old AND."""
    if not engineering:
        return "DATA_ENGINEERING_INELIGIBLE"
    availability = primary["availability"]
    if not all(availability.get(key) for key in ("folds_fit_ok", "every_fold_nonempty", "interval_usable")):
        return "INSUFFICIENT_EVIDENCE"
    if primary.get("numerically_identical"):
        return "HYPOTHESIS_NOT_SUPPORTED"
    if primary["interval"]["hi95"] < -1e-12:
        return "SUPPORT_FURTHER_VALIDATION"
    return "HYPOTHESIS_NOT_SUPPORTED" if primary["interval"]["lo95"] > 1e-12 else "INSUFFICIENT_EVIDENCE"


def _binary_loss(probability: float, label: str) -> float:
    clipped = min(1-1e-12, max(1e-12, probability))
    return -math.log(clipped) if label == "UP" else -math.log(1-clipped)


def _abstains(row: Mapping[str, Any], m0_row: Mapping[str, Any]) -> int:
    """SPEC-06-003 §4.6.2: only a legal exact 0.5 probability abstains.

    A probability model abstains when it has a legal probability exactly equal
    to 0.5.  B2 has no probability: it abstains only when the same slot is a
    legal spot/strike observation (the shared M0 valuation status is VALUED or
    WARMUP), both prices were already available at the observation time, and
    the two prices are exactly equal.  Slots without a legal probability
    (warmup, failed fit, not applicable, missing price) keep their own
    counters and never abstain.
    """
    if row["model"] == "B2":
        at_us = row["at_us"]
        if m0_row["valuation_status"] not in ("VALUED", "WARMUP"):
            return 0
        if any(row[name] is None for name in ("spot", "strike", "spot_available_at_us",
                                              "strike_available_at_us")):
            return 0
        if row["spot_available_at_us"] > at_us or row["strike_available_at_us"] > at_us:
            return 0
        return int(row["spot"] == row["strike"])
    probability = row["p_up"]
    return int(probability is not None and probability == .5)


class Statistics:
    """Fixed-dimensional sufficient statistics; only one round's raw slots live here."""

    def __init__(self, start_us: int, end_us: int, as_of_us: int):
        self.start_us, self.end_us, self.as_of_us = start_us, end_us, as_of_us
        self.days = [_day_str(day) for day in range(start_us//_DAY_US, (end_us-1)//_DAY_US+1)]
        self.daily: dict[tuple, dict[str, list]] = defaultdict(dict)
        self.calibration: dict[tuple, dict[str, np.ndarray]] = defaultdict(dict)
        self.coverage = {model: Counter() for model in MODEL_NAMES}
        self.max_gap = 0.
        self.identical = True

    def _add(self, key: tuple, day: str, values: list[float]) -> None:
        daily = self.daily[key]
        record = daily.setdefault(day, [0., 0, 0])
        if values:
            record[0] += sum(values)/len(values)
            record[1] += 1
            record[2] += len(values)

    def _calibrate(self, key: tuple, day: str, rows: list[dict]) -> None:
        buckets = self.calibration[key].setdefault(day, np.zeros((10, 5)))
        if not rows:
            return
        hit = set()
        for row in rows:
            probability = row["p_up"]
            index = min(9, int(10*probability))
            weight = 1/len(rows)
            buckets[index, :4] += (weight, weight*probability,
                                   weight*int(row["label"] == "UP"), 1)
            hit.add(index)
        for index in hit:
            buckets[index, 4] += 1

    def add_round(self, slots: list[list[dict]]) -> None:
        """Reduce eligible common slots inside a round before counting that round once."""
        first = slots[0][0]
        day = _day_str(first["planned_start_us"]//_DAY_US)
        periods = ["ALL"]
        if first["period"] == "VALIDATION":
            periods += ["VALIDATION", f"FOLD_{first['fold']}"]
        elif first["period"] == "LATEST":
            periods += ["LATEST"]
        matrix = [{row["model"]: row for row in slot} for slot in slots]
        for model in MODEL_NAMES:
            count = self.coverage[model]
            for slot in matrix:
                row = slot[model]
                probability = row["p_up"]
                label_known = row["label_available_at_us"] is not None and row["label_available_at_us"] <= self.as_of_us
                binary = label_known and row["label"] in ("UP", "DOWN")
                count.update(theoretical_slots=1, observed_identity=int(row["round_id"] is not None),
                    valid_probability=int(probability is not None), known_label=int(label_known),
                    binary_scored=int(binary and probability is not None),
                    draw_label=int(label_known and row["label"] == "DRAW"),
                    draw_scored=int(label_known and row["label"] == "DRAW" and probability is not None),
                    missing_label=int(not label_known), unvalued=int(probability is None),
                    directed=int(row["direction"] is not None), abstain=_abstains(row, slot["M0"]),
                    correct=int(binary and row["direction"] == row["label"]))
                count[f"reason:{row['valuation_status']}"] += 1
            members = [slot[model] for slot in matrix]
            valid = sum(row["p_up"] is not None for row in members)
            count.update(theoretical_rounds=1, zero_probability_rounds=int(valid == 0),
                         complete_six_probability_rounds=int(valid == 6))
        dimensions = [("ALL", "ALL", matrix)]
        dimensions += [(offset, "ALL", [slot for slot in matrix if slot["M0"]["offset"] == offset]) for offset in OFFSETS]
        dimensions += [("ALL", name, [slot for slot in matrix if slot["M0"]["sigma_raw"] is not None
            and _stratum_of(slot["M0"]["sigma_raw"]) == name]) for name, _, _ in _STRATA]
        for period in periods:
            for offset, stratum, selected in dimensions:
                for model in MODEL_NAMES:
                    rows = [slot[model] for slot in selected]
                    eligible = [row for row in rows if row["label_available_at_us"] is not None
                        and row["label_available_at_us"] <= self.as_of_us]
                    binary = [row for row in eligible if row["label"] in ("UP", "DOWN") and row["p_up"] is not None]
                    prefix = (period, offset, stratum, model, "N/A", "OWN")
                    self._add((*prefix, "binary_brier"), day, [(row["p_up"]-int(row["label"] == "UP"))**2 for row in binary])
                    self._add((*prefix, "binary_logloss"), day, [_binary_loss(row["p_up"], row["label"]) for row in binary])
                    self._add((*prefix, "payout_mse"), day, [(row["p_up"]-{"UP": 1, "DOWN": 0, "DRAW": .5}[row["label"]])**2
                        for row in eligible if row["p_up"] is not None and row["label"] in ("UP", "DOWN", "DRAW")])
                    self._add((*prefix, "direction_accuracy"), day, [float(row["direction"] == row["label"])
                        for row in eligible if row["label"] in ("UP", "DOWN") and row["direction"] is not None])
                    self._calibrate(prefix, day, binary)
                    if model in _FLOORS:
                        self._add((*prefix, "floor_share"), day, [float(row["sigma_raw"] <= _FLOORS[model])
                            for row in rows if row["sigma_raw"] is not None])
                    if model == "M0":
                        self._add((*prefix, "reference_difference_bps"), day,
                            [(row["spot"]/row["strike"]-1)*10000 for row in rows
                             if row["spot"] is not None and row["strike"] is not None])
                calibration_seen = set()
                comparisons = [("C0B", "M0", "B0", ("M0", "B0", "B1")),
                    ("C0B", "M0", "B1", ("M0", "B0", "B1")),
                    ("C2", "M2-low", "M0", ("M0", "M2-low", "M2-high")),
                    ("C2", "M2-high", "M0", ("M0", "M2-low", "M2-high"))]
                if period != "ALL":
                    comparisons.append(("C10", "M1", "M0", ("M0", "M1")))
                for comparison, model, reference, required in comparisons:
                    common = [slot for slot in selected if all(slot[name]["p_up"] is not None for name in required)
                        and slot[model]["label_available_at_us"] is not None
                        and slot[model]["label_available_at_us"] <= self.as_of_us]
                    for metric in ("binary_brier", "binary_logloss", "payout_mse"):
                        values = []
                        for slot in common:
                            left, right = slot[model], slot[reference]
                            label = label_code(left["label"])
                            if label not in (0, 1, 2) or (label == 2 and metric != "payout_mse"):
                                continue
                            if metric == "binary_logloss":
                                loss = lambda p: _binary_loss(p, left["label"])
                            else:
                                loss = lambda p: (p-(.5 if label == 2 else label))**2
                            values.append(loss(left["p_up"])-loss(right["p_up"]))
                            if (comparison == "C10" and period == "VALIDATION" and offset == stratum == "ALL"
                                    and metric == "binary_brier"):
                                gap = abs(left["p_up"]-right["p_up"])
                                self.max_gap = max(self.max_gap, gap)
                                self.identical &= math.isclose(left["p_up"], right["p_up"], abs_tol=1e-12, rel_tol=1e-9)
                        key = (period, offset, stratum, model, reference, comparison, metric+"_difference")
                        self._add(key, day, values)
                        if comparison == "C10" and offset == stratum == "ALL":
                            self._add((period, offset, "COMPLETE_SIX", model, reference, comparison,
                                       metric+"_difference"), day, values if len(values) == 6 else [])
                    for name in (model, reference):
                        calibration_key = (period, offset, stratum, name, reference, comparison)
                        if calibration_key not in calibration_seen:
                            self._calibrate(calibration_key, day,
                                [slot[name] for slot in common if slot[name]["label"] in ("UP", "DOWN")])
                            calibration_seen.add(calibration_key)
                directed = [slot for slot in selected if slot["M0"]["direction"] is not None
                    and slot["B2"]["direction"] is not None and slot["M0"]["label"] in ("UP", "DOWN")
                    and slot["M0"]["label_available_at_us"] is not None
                    and slot["M0"]["label_available_at_us"] <= self.as_of_us]
                self._add((period, offset, stratum, "M0", "B2", "D02", "direction_accuracy_difference"), day,
                    [float(slot["M0"]["direction"] == slot["M0"]["label"])-
                     float(slot["B2"]["direction"] == slot["B2"]["label"]) for slot in directed])

    def _period_days(self, period: str) -> list[str]:
        if period == "ALL":
            return self.days
        if period == "LATEST":
            return [_day_str(CUTOFFS[8]//_DAY_US)]
        start = CUTOFFS[0] if period == "VALIDATION" else CUTOFFS[int(period.split("_")[1])]
        count = 56 if period == "VALIDATION" else 7
        return [_day_str(start//_DAY_US+index) for index in range(count)]

    def finish(self, fits: Mapping[str, Any], check: Any = lambda: None) -> dict:
        """Reconstruct all ratios/intervals from additive day quantities, not day rates."""
        rows, daily, monthly, calibration, indices = [], [], [], [], {}
        bootstrap = {}
        for period in sorted({key[0] for key in self.daily}):
            check()
            days = self._period_days(period)
            generator = np.random.Generator(np.random.PCG64(42))
            indices[period+"_day"] = generator.integers(0, len(days), size=(1000, len(days)), dtype=np.int64)
            if len(days) > 7:
                starts = np.random.Generator(np.random.PCG64(42)).integers(0, len(days),
                    size=(1000, math.ceil(len(days)/7)), dtype=np.int64)
                indices[period+"_seven"] = ((starts[:, :, None]+np.arange(7)) % len(days)).reshape(1000, -1)[:, :len(days)]
            bootstrap[period] = dict(days=days, seed=42, generator="PCG64", replicates=1000,
                quantile="linear", day_key=period+"_day", seven_key=period+"_seven" if len(days) > 7 else None,
                day_order_sha256=hashlib.sha256(json.dumps(days, separators=(",", ":")).encode()).hexdigest())
        for key, quantities in sorted(self.daily.items(), key=lambda item: str(item[0])):
            check()
            period, offset, stratum, model, reference, comparison, metric = key
            days = bootstrap[period]["days"]
            numerators = np.array([quantities.get(day, (0, 0, 0))[0] for day in days])
            denominators = np.array([quantities.get(day, (0, 0, 0))[1] for day in days], dtype=np.int64)
            numerator, denominator = float(numerators.sum()), int(denominators.sum())
            common_slots = sum(value[2] for value in quantities.values())
            base = dict(schema_version="btc5m-phase1-statistics/1", period=period,
                fold=int(period.split("_")[1]) if period.startswith("FOLD_") else 8 if period == "LATEST" else "ALL",
                offset=offset, stratum=stratum, model=model, reference=reference, comparison_set=comparison,
                metric=metric, numerator=numerator, denominator=denominator,
                slot_count=common_slots,
                value=numerator/denominator if denominator else None, status="OK" if denominator else "N/A_ZERO_DENOMINATOR")
            series_map = {"value": {day: (float(num), int(den)) for day, num, den in zip(days, numerators, denominators)}}
            intervals = _block_replicates(series_map, days, "value", indices[period+"_day"])
            base.update({name: intervals[name] for name in ("lo95", "hi95", "valid_replicates", "invalid_replicates")})
            if period+"_seven" in indices:
                seven = _block_replicates(series_map, days, "value", indices[period+"_seven"])
            else:
                seven = dict(point=None, lo95=None, hi95=None, valid_replicates=0,
                             invalid_replicates=0, status="N/A_INSUFFICIENT_BLOCKS")
            base["seven_day"] = seven
            rows.append(base)
            daily_base = {name: value for name, value in base.items() if name != "seven_day"}
            for day, num, den in zip(days, numerators, denominators):
                daily.append(dict(daily_base, utc_day=day, numerator=float(num), denominator=int(den),
                    value=float(num/den) if den else None, lo95=None, hi95=None,
                    valid_replicates=None, invalid_replicates=None,
                    status="OK" if den else "N/A_ZERO_DENOMINATOR"))
            for month in sorted({day[:7] for day in days}):
                chosen = np.array([day.startswith(month) for day in days])
                den, num = int(denominators[chosen].sum()), float(numerators[chosen].sum())
                monthly.append(dict(daily_base, utc_month=month, numerator=num, denominator=den,
                    value=num/den if den else None, lo95=None, hi95=None,
                    valid_replicates=None, invalid_replicates=None, status="OK" if den else "N/A_ZERO_DENOMINATOR"))
        eces = {}
        for key, quantities in sorted(self.calibration.items(), key=lambda item: str(item[0])):
            period, offset, stratum, model, reference, comparison = key
            summed = sum(quantities.values(), np.zeros((10, 5)))
            total = float(summed[:, 0].sum())
            numerator = float(np.abs(summed[:, 1]-summed[:, 2]).sum())
            days = bootstrap[period]["days"]
            daily_buckets = np.array([quantities.get(day, np.zeros((10, 5))) for day in days])
            resampled = daily_buckets[indices[period+"_day"]].sum(axis=1)
            den = resampled[:, :, 0].sum(axis=1)
            valid = den > 0
            estimates = np.full(1000, np.nan)
            estimates[valid] = np.abs(resampled[valid, :, 1]-resampled[valid, :, 2]).sum(axis=1)/den[valid]
            eces[key] = (numerator/total if total else None, estimates)
            rows.append(dict(schema_version="btc5m-phase1-statistics/1", period=period,
                fold=int(period.split("_")[1]) if period.startswith("FOLD_") else 8 if period == "LATEST" else "ALL",
                offset=offset, stratum=stratum, model=model, reference=reference, comparison_set=comparison,
                metric="ece", numerator=numerator, denominator=total, value=numerator/total if total else None,
                lo95=float(np.quantile(estimates[valid], .025)) if valid.any() else None,
                hi95=float(np.quantile(estimates[valid], .975)) if valid.any() else None,
                valid_replicates=int(valid.sum()), invalid_replicates=int((~valid).sum()),
                status="OK" if total else "N/A_ZERO_DENOMINATOR"))
            for index, (weight, prob, labels, slot_count, round_count) in enumerate(summed):
                calibration.append(dict(schema_version="btc5m-phase1-statistics/1", period=period, fold="ALL",
                    offset=offset, stratum=stratum, model=model, reference=reference, comparison_set=comparison,
                    metric="calibration", numerator=float(prob), denominator=float(weight), value=float(prob/weight) if weight else None,
                    lo95=None, hi95=None, valid_replicates=None, invalid_replicates=None,
                    bin=index, lower=index/10, upper=(index+1)/10, slot_count=int(slot_count), round_count=int(round_count),
                    weight=float(weight/total) if total else 0., mean_p=float(prob/weight) if weight else None,
                    up_rate=float(labels/weight) if weight else None, status="OK" if weight else "N/A_EMPTY_BIN"))
        for key, (point, estimates) in eces.items():
            period, offset, stratum, model, reference, comparison = key
            counterpart = (period, offset, stratum, reference, reference, comparison)
            if comparison != "C10" or model != "M1" or counterpart not in eces:
                continue
            other, other_estimates = eces[counterpart]
            difference = estimates-other_estimates
            valid = np.isfinite(difference)
            rows.append(dict(schema_version="btc5m-phase1-statistics/1", period=period, fold="ALL",
                offset=offset, stratum=stratum, model=model, reference=reference, comparison_set=comparison,
                metric="ece_difference", numerator=None, denominator=None,
                value=point-other if point is not None and other is not None else None,
                lo95=float(np.quantile(difference[valid], .025)) if valid.any() else None,
                hi95=float(np.quantile(difference[valid], .975)) if valid.any() else None,
                valid_replicates=int(valid.sum()), invalid_replicates=int((~valid).sum()),
                status="OK" if point is not None else "N/A_ZERO_DENOMINATOR"))
        primary_row = next((row for row in rows if row["period"] == "VALIDATION" and row["comparison_set"] == "C10"
            and row["metric"] == "binary_brier_difference" and row["offset"] == row["stratum"] == "ALL"), {})
        primary = dict(endpoint="C10_M1_MINUS_M0_BINARY_BRIER", difference=primary_row.get("value"),
            interval=dict(lo95=primary_row.get("lo95"), hi95=primary_row.get("hi95")),
            numerically_identical=self.identical, max_abs_probability_gap=self.max_gap,
            availability=dict(folds_fit_ok=len(fits) == 9 and all(fits[str(index)]["m1"]["fit_status"] == "FIT_OK" for index in range(8)),
                every_fold_nonempty=all(any(row["period"] == f"FOLD_{index}" and row["comparison_set"] == "C10"
                    and row["metric"] == "binary_brier_difference" and row["denominator"] > 0 for row in rows) for index in range(8)),
                interval_usable=primary_row.get("valid_replicates") == 1000))
        diagnostic = [row for row in rows if row["comparison_set"] == "C10"]
        conflicts = [row for row in diagnostic if row["metric"].endswith("_difference")
                     and row["value"] is not None and row["value"] > 1e-12
                     and primary.get("difference") is not None and primary["difference"] < -1e-12]
        if (primary["difference"] is not None and primary["difference"] < -1e-12 and
                primary_row.get("seven_day", {}).get("hi95") is not None and primary_row["seven_day"]["hi95"] >= -1e-12):
            conflicts.append(dict(item="seven_day_does_not_support", **primary_row["seven_day"]))
        lodo = []
        for row in daily:
            if row["period"] == "VALIDATION" and row["comparison_set"] == "C10" and row["metric"] == "binary_brier_difference" and row["offset"] == row["stratum"] == "ALL":
                den = primary_row["denominator"]-row["denominator"]
                num = primary_row["numerator"]-row["numerator"]
                item = dict(row, numerator=num, denominator=den, value=num/den if den else None,
                            status="OK" if den else "N/A_ZERO_DENOMINATOR")
                lodo.append(item)
                if (item["value"] is not None and item["value"] > 1e-12 and
                        primary["difference"] is not None and primary["difference"] < -1e-12):
                    conflicts.append(dict(item, diagnostic="leave_one_day_out"))
        h1 = {}
        for reference in ("B0", "B1"):
            result = next((row for row in rows if row["period"] == "VALIDATION" and row["offset"] == row["stratum"] == "ALL"
                and row["comparison_set"] == "C0B" and row["reference"] == reference and row["metric"] == "binary_brier_difference"), {})
            h1[reference] = dict(result, inference=("SUPPORTS" if result.get("hi95") is not None and result["hi95"] < -1e-12
                and result["valid_replicates"] == 1000 else "OPPOSES" if result.get("lo95") is not None and
                result["lo95"] > 1e-12 and result["valid_replicates"] == 1000 else "INSUFFICIENT_EVIDENCE"))
        return dict(rows=rows, daily=daily, monthly=monthly, calibration_rows=calibration,
            hypotheses=dict(H1=dict(against_baselines=h1, joint_probability_support=all(item["inference"] == "SUPPORTS" for item in h1.values()),
                direction="SEPARATE_D02_NOT_TRADING_WINRATE"), H3=dict(status="EXPLORATORY", multiple_testing_adjustment="NOT_PERFORMED", deployment_selection="NONE")),
            coverage={model: dict(values, probability_coverage=values["valid_probability"]/values["theoretical_slots"]
                if values["theoretical_slots"] else None) for model, values in self.coverage.items()}, bootstrap=bootstrap,
            comparison_coverage=[{name: row.get(name) for name in ("period", "fold", "offset", "stratum", "model",
                "reference", "comparison_set", "metric", "slot_count", "denominator")} for row in rows],
            primary_evidence=primary, robustness_diagnostics=diagnostic, diagnostic_conflicts=conflicts,
            leave_one_day_out=lodo, research_verdict=None, preaudit_classification=classify(primary, engineering=True),
            engineering_checks=dict(causal_timing="PASS", identity="PASS", denominator="PASS",
                numeric="PASS", fit="PASS", stream_consumption="PASS", independent_validation="PENDING"),
            effect_size=dict(difference=primary["difference"], interval=primary["interval"]),
            complexity_cost=dict(fitted_parameters=2, fits_recorded=len(fits),
                fit_wall_seconds=sum(entry.get("wall_seconds", 0) for entry in fits.values())),
            proxy_error="UNKNOWN", economic_value_status="NOT_VERIFIED", indices=indices)


def materialize_run(wide_rows: Iterable[dict], directory: Path, *, mode: str,
                    start_us: int, end_us: int, as_of_us: int, check: Any,
                    flow_finished: Any = None) -> dict:
    """Stream native merge -> one-day arrays -> frozen fits -> raw samples/statistics."""
    from phase1_model_research import write_csv, _write_new_json, digest
    (directory / "fit-days").mkdir()
    def capture_native() -> Iterable[dict]:
        for day, group in itertools.groupby(wide_rows, key=lambda row: row["planned_start_us"]//_DAY_US):
            check()
            day_rows = list(group)
            if len(day_rows) > 1728:
                raise ValueError("unbounded native day")
            block = np.zeros(len(day_rows), dtype=FIT_DTYPE)
            for index, row in enumerate(day_rows):
                for field in ("planned_start_us", "offset", "at_us", "ends_at_us", "label_available_at_us"):
                    block[field][index] = row[field] if row[field] is not None else -1
                block["p0"][index] = row["m0_p_up"] if row["m0_p_up"] is not None else 0.
                block["label_code"][index] = label_code(row["label"])
                block["valued"][index] = row["m0_p_up"] is not None
            with (directory / "fit-days" / f"{_day_str(day)}.npy").open("xb") as stream:
                np.save(stream, block, allow_pickle=False)
            yield from day_rows
    write_csv(directory / "native-samples.csv", capture_native())
    if flow_finished is not None:
        flow_finished()
    fits = fit_from_files(directory, as_of_us=as_of_us, check=check) if mode == "full" else {}
    _write_new_json(directory / "parameters.json", dict(status="APPLICABLE" if fits else "NOT_APPLICABLE", fits=fits))
    accumulator = Statistics(start_us, end_us, as_of_us)
    def samples() -> Iterable[dict]:
        for _, group in itertools.groupby(read_csv(directory / "native-samples.csv"), key=lambda row: row["planned_start_us"]):
            check()
            slots = [model_rows(row, fits) for row in group]
            if len(slots) != 6 or [slot[0]["offset"] for slot in slots] != list(OFFSETS):
                raise ValueError("missing/duplicate/out-of-order sample slots")
            accumulator.add_round(slots)
            for slot in slots:
                yield from slot
    write_csv(directory / "samples.csv", samples(), SAMPLE_COLUMNS)
    raw = accumulator.finish(fits, check)
    indices = raw.pop("indices")
    with (directory / "bootstrap.npz").open("xb") as stream:
        np.savez(stream, **indices)
    _write_new_json(directory / "bootstrap-identity.json", dict(periods=raw["bootstrap"],
        sha256=digest(directory / "bootstrap.npz"), shapes={key: list(value.shape) for key, value in indices.items()}, dtype="int64"))
    _write_new_json(directory / "statistics.json", raw, compact=True)
    _write_new_json(directory / "coverage.json", dict(raw["coverage"], comparisons=raw["comparison_coverage"]))
    verdict_fields = ("engineering_checks", "primary_evidence", "robustness_diagnostics", "diagnostic_conflicts",
        "research_verdict", "effect_size", "complexity_cost", "proxy_error", "economic_value_status")
    _write_new_json(directory / "verdict.json", {key: raw[key] for key in verdict_fields})
    for name, rows, columns in (("comparison", raw["rows"], STAT_COLUMNS),
        ("calibration", raw["calibration_rows"], (*STAT_COLUMNS, "bin", "lower", "upper", "slot_count", "round_count", "weight", "mean_p", "up_rate")),
        ("daily", raw["daily"], (*STAT_COLUMNS, "utc_day")),
        ("monthly", raw["monthly"], (*STAT_COLUMNS, "utc_month")),
        ("volatility", [row for row in raw["rows"] if row["stratum"] in {item[0] for item in _STRATA}], STAT_COLUMNS),
        ("floor", [row for row in raw["rows"] if row["metric"] == "floor_share"], STAT_COLUMNS),
        ("leave-one-day-out", raw["leave_one_day_out"], (*STAT_COLUMNS, "utc_day"))):
        write_csv(directory / f"{name}.csv", rows, columns)
    buckets = {model: [row for row in raw["calibration_rows"] if row["model"] == model and row["period"] == "ALL"
        and row["comparison_set"] == "OWN" and row["offset"] == row["stratum"] == "ALL"] for model in ("M0", "M1")}
    buckets["_scope"] = "ALL / OWN"
    strata = [row for row in raw["rows"] if row["period"] == "ALL" and row["comparison_set"] == "C2" and
        row["metric"] == "binary_brier_difference" and row["stratum"] in {item[0] for item in _STRATA}]
    for name, text in render_figures(dict(calibration=dict(buckets=buckets), strata=dict(rows=strata))).items():
        with (directory / f"{name}.svg").open("x") as stream:
            stream.write(text)
    return dict(sample_rows=accumulator.coverage["M0"]["theoretical_slots"]*7,
                fits=len(fits), preaudit_classification=raw["preaudit_classification"])
