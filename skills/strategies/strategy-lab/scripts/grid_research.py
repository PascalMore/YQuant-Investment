"""Offline grid research calculations (SPEC-06-002 V1.4 / Design V1.3).

No platform imports, environment access, strategy execution or network calls.
File helpers write explicit, caller-selected synthetic/local carriers only.
A planned identity is NOT a cross-restart submission/replay implementation.
"""

from __future__ import annotations

import calendar
import copy
import csv
import datetime as dt
import hashlib
import json
import re
import math
from pathlib import Path
import statistics
from typing import Any

def generate_strategy_source(*, cell: str | dict, template_sha256: str,
                             geometry: dict | None = None,
                             timeframe: str = "15m") -> str:
    """Compatibility entry to the instance's static text generator, never the strategy.

    Resolve by file path without sys.path changes or a reverse module import.
    The instance has no import-time business I/O; only this explicit call reads
    the protected native template. Core accounting remains independent.
    """
    import importlib.util

    if isinstance(cell, str):
        contract, separator, window = cell.rpartition("-")
        if not separator:
            raise ValueError("cell identity must include a window")
        matches = [item for item in build_cells([contract]) if item["window"] == window]
        if len(matches) != 1:
            raise ValueError("unknown frozen window")
        cell = matches[0]
    path = Path(__file__).resolve().parents[1] / "strategies/neutral-grid-four-window-v1/research.py"
    spec = importlib.util.spec_from_file_location("neutral_grid_source_generator", path)
    if spec is None or spec.loader is None:
        raise ValueError("static generator missing")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    return generator.generate_strategy_source(
        cell=cell, template_sha256=template_sha256, geometry=geometry,
        timeframe=timeframe)


UTC = dt.timezone.utc
DEFAULT_CONTRACTS = ("PUMPUSDT", "AAVEUSDT", "JUPUSDT", "SUIUSDT")
# Anchor of the previous frozen batch. It is NOT a research default: since
# RFC-06-002 V1.10 (D4-1) the anchor is the research task date, so every
# research batch must pass anchor_utc explicitly and persist it together with
# task_date (anchor_utc must equal the UTC midnight of task_date).
PREVIOUS_BATCH_ANCHOR = dt.datetime(2026, 10, 31, tzinfo=UTC)
DEFAULT_ANCHOR = PREVIOUS_BATCH_ANCHOR
DEFAULT_WINDOW_COUNT = 4
INITIAL_MARGIN = 1000.0
# Default research bar frequency (seconds). Frequency is a research-instance
# parameter (D5-1): every batch passes frequency_seconds explicitly; K and
# expected bar counts derive from it instead of being hard-coded per TF.
DEFAULT_FREQUENCY_SECONDS = 3600
ABS_TOL = 1e-12
REL_TOL = 1e-10
NA = "N/A"
# Frozen risk envelope (RFC-06-002 V1.8 §51): gross/equity limit 2.5, and a
# 35% peak-to-trough drawdown as a result filter (not a stop-loss promise).
RISK_GROSS_TO_EQUITY_LIMIT = 2.5
RISK_DRAWDOWN_LIMIT_PCT = 35.0
# Fixed caliber disclosure so every carrier self-describes its metric
# semantics (Pascal 2026-11-04: returns are per-window period returns,
# NOT annualized; sharpe is per-bar-return annualized with the platform K).
METRICS_CALIBER = ("margin_return_pct=period return over window (NOT annualized); "
                   "sharpe=mean/std of per-bar equity returns x sqrt(periodsPerYear), "
                   "arithmetic-mean based (ignores variance drag); "
                   "max_drawdown_pct=peak-to-trough equity drawdown")
COMPRESSED_EQUITY_LIMITATION = (
    "Compressed equity cannot independently verify full equal-frequency Sharpe or MDD."
)
MARKET = {
    "venue": "gate", "market_type": "swap", "settle": "USDT",
    "product": "USDT-settled linear perpetual",
}
METRIC_COLUMNS = (
    "L", "U", "g_pct", "N", "margin_return_pct", "sharpe", "max_drawdown_pct",
    "downward_liquidation_price", "upward_liquidation_price",
)
TRANSITIONS = {
    "planned": {"prechecked", "history_insufficient", "insufficient_evidence", "failed",
                "not_submitted_due_to_stop"},
    "prechecked": {"submitting", "insufficient_evidence", "failed", "not_submitted_due_to_stop"},
    "submitting": {"submitted", "failed", "insufficient_evidence"},
    "submitted": {"succeeded", "failed", "insufficient_evidence"},
    "succeeded": set(), "history_insufficient": set(), "insufficient_evidence": set(),
    "failed": set(), "not_submitted_due_to_stop": set(),
}
BUDGET_LIMITS = {"target_jobs": 4, "outer_jobs": 8, "data_requests": 50,
                 "elapsed_seconds": 1800, "evolution": 0}


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: finite number required")
    if not math.isfinite(value):
        raise ValueError(f"{name}: non-finite number")
    return float(value)


def _time(value: Any) -> dt.datetime:
    if isinstance(value, str):
        try:
            value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid UTC timestamp") from exc
    if not isinstance(value, dt.datetime) or value.utcoffset() != dt.timedelta(0):
        raise ValueError("timezone-aware UTC timestamp required")
    return value.astimezone(UTC)


def _iso(value: Any) -> str:
    return _time(value).isoformat().replace("+00:00", "Z")


def _midnight(value: Any) -> dt.datetime:
    value = _time(value)
    if value.time() != dt.time():
        raise ValueError("UTC midnight required")
    return value


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name}: integer >= {minimum} required")
    return value


def _subtract_months(anchor: dt.datetime, months: int) -> dt.datetime:
    year, month = divmod(anchor.year * 12 + anchor.month - 1 - months, 12)
    month += 1
    return anchor.replace(year=year, month=month,
                          day=min(anchor.day, calendar.monthrange(year, month)[1]))


def build_cells(contracts: list[str] | None = None,
                windows_spec: list[dict] | None = None,
                anchor_utc: Any = None,
                frequency_seconds: int = DEFAULT_FREQUENCY_SECONDS) -> list[dict]:
    """Build parameterized half-open cells without consulting the machine clock.

    Frequency is a research-instance parameter (D5-1): callers pass
    ``frequency_seconds`` per batch (900/3600/14400/86400); expected bar counts
    derive from it. The real coordinating entry must separately call
    validate_run_anchor before any business use. Explicit future anchors here
    are valid offline calendars.
    """
    contracts = list(DEFAULT_CONTRACTS if contracts is None else contracts)
    if not contracts or any(not isinstance(name, str) or not name.strip() for name in contracts):
        raise ValueError("nonempty contracts required")
    if len(set(contracts)) != len(contracts):
        raise ValueError("duplicate contract")
    anchor = _midnight(DEFAULT_ANCHOR if anchor_utc is None else anchor_utc)
    if windows_spec is None:
        windows_spec = [
            {"start_utc": _subtract_months(anchor, 3 * index),
             "end_utc": _subtract_months(anchor, 3 * (index - 1))}
            for index in range(1, DEFAULT_WINDOW_COUNT + 1)
        ]
    if not windows_spec:
        raise ValueError("nonempty windows required")
    windows = []
    for index, window in enumerate(windows_spec, 1):
        start, end = _midnight(window["start_utc"]), _midnight(window["end_utc"])
        if start >= end or end > anchor:
            raise ValueError("invalid window or window beyond anchor")
        windows.append((f"W{index}", start, end))
    ordered = sorted(windows, key=lambda window: window[1])
    if any(left[2] > right[1] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("duplicate or overlapping windows")
    return [
        {"cell_id": f"{contract}-{window}", "contract": contract, "window": window,
         **MARKET, "native_instrument": None, "start_utc": start, "end_utc": end,
         "anchor_utc": anchor, "api_start_date": start.date().isoformat(),
         "api_end_date": (end - dt.timedelta(days=1)).date().isoformat(),
         "frequency_seconds": int(frequency_seconds),
         "expected_bars": int((end - start).total_seconds() // int(frequency_seconds))}
        for contract in contracts for window, start, end in windows
    ]


def check_window_coverage(bars_needed: int, venue_retained_bars: int,
                          listed_since_bars: int) -> dict:
    """Pre-flight the window coverage before any submission (D5-1/V1.11-09).

    A research window is only executable when the bar count fits BOTH the
    venue's retained history and the contract's own listing history. Frequency
    changes the retained span (Gate swap keeps 10000 bars: 1m ~6.9 days,
    15m ~104 days, 1h ~417 days), so this check is a frequency-aware
    mechanism, not a per-batch constant.
    """
    needed = _integer(bars_needed, "bars_needed", 1)
    retained = _integer(venue_retained_bars, "venue_retained_bars", 1)
    listed = _integer(listed_since_bars, "listed_since_bars", 1)
    limit = min(retained, listed)
    if needed <= limit:
        return {"ok": True, "bars_needed": needed, "effective_limit": limit,
                "reason": None}
    return {"ok": False, "bars_needed": needed, "effective_limit": limit,
            "reason": f"window needs {needed} bars but venue/listing allows {limit}"}


def validate_run_anchor(anchor_utc: Any, now_utc: Any) -> None:
    """Reject a not-yet-reached anchor at the coordinating boundary, clock injected."""
    if _midnight(anchor_utc) > _time(now_utc):
        raise ValueError("anchor has not been reached")


def check_coverage(bars: list[dict], identity: dict, start_utc: Any, end_utc: Any,
                   frequency_seconds: int) -> dict:
    """Compare every expected open timestamp and exact supplied market identity.

    Bars use open_time_utc/close_time_utc and an identity mapping. Duplicates
    (including identical duplicates) and unknown provenance are not success.
    """
    frequency = _integer(frequency_seconds, "frequency_seconds", 1)
    start, end = _time(start_utc), _time(end_utc)
    span = (end - start).total_seconds()
    if span <= 0 or span % frequency or not identity:
        raise ValueError("invalid coverage interval/identity")
    expected = {start + dt.timedelta(seconds=index * frequency)
                for index in range(int(span // frequency))}
    seen = {}
    duplicate = conflicting = misaligned = unclosed = identity_mismatches = 0
    for bar in bars:
        opened, closed = _time(bar["open_time_utc"]), _time(bar["close_time_utc"])
        if opened in seen:
            duplicate += 1
            conflicting += bar != seen[opened]
        seen[opened] = bar
        if opened not in expected or closed != opened + dt.timedelta(seconds=frequency):
            misaligned += 1
        if closed > end or bar.get("closed", True) is not True:
            unclosed += 1
        actual_identity = bar.get("identity", bar)
        if any(actual_identity.get(key) != value for key, value in identity.items()):
            identity_mismatches += 1
    missing = sorted(expected - seen.keys())
    reasons = []
    for label, count in (("missing", len(missing)), ("duplicate", duplicate),
                         ("conflicting", conflicting), ("misaligned", misaligned),
                         ("unclosed", unclosed), ("identity_mismatch", identity_mismatches)):
        if count:
            reasons.append(f"{label}={count}")
    return {"status": "ok" if not reasons else "insufficient_evidence",
            "reason": "; ".join(reasons) or None, "identity": dict(identity),
            "expected_count": len(expected), "actual_count": len(bars),
            "unique_count": len(seen), "duplicate_count": duplicate,
            "conflicting_count": conflicting, "missing_count": len(missing),
            "misaligned_count": misaligned, "unclosed_count": unclosed,
            "identity_mismatch_count": identity_mismatches,
            "missing_opens": [_iso(value) for value in missing],
            "first_open": _iso(min(seen)) if seen else None,
            "last_open": _iso(max(seen)) if seen else None}


def derive_geometry(closed_daily_bars: list[dict], start_utc: Any) -> dict:
    """Freeze geometry from at most 365 continuous, proven, pre-window daily bars."""
    start = _time(start_utc)
    bars = sorted((bar for bar in closed_daily_bars
                   if _time(bar["close_time_utc"]) <= start),
                  key=lambda bar: _time(bar["open_time_utc"]))[-365:]
    if len(bars) < 2:
        raise ValueError("fewer than two closed training bars")
    previous = None
    for bar in bars:
        opened, closed = _midnight(bar["open_time_utc"]), _midnight(bar["close_time_utc"])
        if closed != opened + dt.timedelta(days=1) or (previous and opened != previous):
            raise ValueError("daily history gap/duplicate/misalignment")
        if bar.get("provenance_ok") is not True:
            raise ValueError("training provenance unknown")
        low, high = _finite(bar["low"], "low"), _finite(bar["high"], "high")
        if not 0 < low <= high:
            raise ValueError("invalid training range")
        previous = closed
    lower = min(bar["low"] for bar in bars)
    upper = max(bar["high"] for bar in bars)
    if not lower < upper:
        raise ValueError("training L must be less than U")
    result = {"L": lower, "U": upper, "training_count": len(bars),
              "training_start_utc": _iso(bars[0]["open_time_utc"]),
              "training_end_utc": _iso(bars[-1]["close_time_utc"]),
              "training_available_at_utc": _iso(bars[-1]["close_time_utc"]),
              "short_history": len(bars) < 365, "n_max": 200,
              "g_lower": 0.45, "g_upper": 1.5, "old_cost_assumption_pct": 0.14,
              "new_score_cost_pct": 0.20,
              "actual_fill_rule": "native limit/market rules; no post-hoc cost deduction"}
    best = None
    for count in range(3, 201):
        gap = 100 * math.expm1((math.log(upper) - math.log(lower)) / count)
        if 0.45 <= gap <= 1.5:
            score = gap / 0.20
            if best is None or (score > best[0] and not math.isclose(
                    score, best[0], abs_tol=ABS_TOL, rel_tol=REL_TOL)):
                best = (score, count, gap)
    if best is None:
        return {**result, "status": "no-feasible-geometry", "N": None,
                "g_pct": None, "grid_lines": None, "reason": "no feasible N in 3..200"}
    score, count, gap = best
    return {**result, "status": "ok", "N": count, "g_pct": gap,
            "grid_lines": count + 1, "score": score, "reason": None}


def margin_metrics(bar_close_rows: list[dict],
                   frequency_seconds: int = DEFAULT_FREQUENCY_SECONDS) -> dict:
    """Compute margin return/MDD and population Sharpe on consecutive bar closes.

    Frequency is a research-instance parameter (D5-1): the annualization factor
    is K = 365 * 86400 / frequency_seconds (formula, not a hard-coded constant).
    M0 participates only in return/MDD, never in the first Sharpe return.
    Invalid/nonpositive equity preserves raw net PnL and raw MDD for diagnosis.
    """
    equities, times = [], []
    for row in bar_close_rows:
        if "time" not in row:
            raise ValueError("missing time")
        times.append(_time(row["time"]))
        if "equity" in row:
            equity = _finite(row["equity"], "equity")
        else:
            equity = INITIAL_MARGIN + _finite(row["realized_net_pnl"], "realized_net_pnl")
            equity += _finite(row["unrealized_pnl"], "unrealized_pnl")
        equities.append(_finite(equity, "computed equity"))
    peak, maximum_dd = INITIAL_MARGIN, 0.0
    peak_time = trough_time = None
    for timestamp, equity in zip(times, equities):
        if equity > peak:
            peak, peak_time = equity, _iso(timestamp)
        drawdown = (peak - equity) / peak * 100
        if drawdown > maximum_dd:
            maximum_dd, trough_time = drawdown, _iso(timestamp)
    frequency = int(frequency_seconds)
    missing = any((right - left).total_seconds() != frequency
                  for left, right in zip(times, times[1:]))
    reasons = []
    if not equities:
        reasons.append("empty equity sample")
    if missing:
        reasons.append("missing/duplicate/non-native bar")
    if any(equity <= 0 for equity in equities):
        reasons.append("nonpositive equity")
    valid_equity = bool(equities) and not missing and min(equities) > 0
    returns = [right / left - 1 for left, right in zip(equities, equities[1:])
               if left > 0]
    sharpe = NA
    if len(returns) < 2:
        reasons.append("insufficient return samples")
    if returns and statistics.pstdev(returns) == 0:
        reasons.append("zero volatility")
    if valid_equity and len(returns) >= 2 and statistics.pstdev(returns) > 0:
        periods_per_year = 365 * (86400 // frequency)
        sharpe = statistics.mean(returns) / statistics.pstdev(returns) * math.sqrt(periods_per_year)
    return {"status": "ok" if valid_equity else NA,
            "reason": "; ".join(reasons) or None,
            "net_pnl": equities[-1] - INITIAL_MARGIN if equities else NA,
            "margin_return_pct": 100 * (equities[-1] / INITIAL_MARGIN - 1)
            if valid_equity else NA,
            "peak_equity": peak,
            "max_drawdown_pct": maximum_dd if equities and not missing else NA,
            "raw_max_drawdown_pct": maximum_dd if equities else None,
            "peak_time": peak_time, "trough_time": trough_time,
            "sharpe": sharpe, "return_count": len(returns), "bar_count": len(equities),
            "risk_free": 0, "ddof": 0,
            "periods_per_year": 365 * (86400 // frequency),
            "limitation": COMPRESSED_EQUITY_LIMITATION}


def cross_liquidation(snapshot: dict, mmr: float, close_fee: float) -> dict:
    """Solve the single shared-pool cross_linear_v1 research scenario, not venue rules."""
    required = ("equity", "q_long", "q_short", "avg_long", "avg_short", "mark_price")
    result = {"formula_version": "cross_linear_v1", "mode": "cross/shared_pool",
              "price_proxy": snapshot.get("price_proxy", "last_not_mark"),
              "available_margin": snapshot.get("available_margin"),
              "available_margin_status": "UNKNOWN" if snapshot.get("available_margin") is None
              else "provided", "downward_liquidation_price": None,
              "upward_liquidation_price": None, "residual_abs": None, "residual_tol": None,
              "assumptions": "constant MMR/close fee; frozen positions; funding not_modeled"}
    # Reject a supplied NaN even if another required field is absent.
    for key in (*required, "available_margin"):
        if snapshot.get(key) is not None:
            _finite(snapshot[key], key)
    maintenance, fee = _finite(mmr, "mmr"), _finite(close_fee, "close_fee")
    if maintenance < 0 or fee < 0:
        raise ValueError("negative maintenance/fee")
    absent = [key for key in required if snapshot.get(key) is None]
    if absent:
        return {**result, "status": NA, "reason": "missing " + ",".join(absent)}
    equity, q_long, q_short, avg_long, avg_short, price = [snapshot[key] for key in required]
    if min(q_long, q_short, avg_long, avg_short) < 0 or price <= 0:
        raise ValueError("invalid position/price")
    if (q_long > 0 and avg_long <= 0) or (q_short > 0 and avg_short <= 0):
        raise ValueError("held side requires positive average price")
    quantity = q_long + q_short
    coefficient = q_long - q_short - maintenance * quantity - fee * quantity
    constant = equity - (q_long - q_short) * price
    residual_tol = 1e-8 * max(1, abs(equity), abs(quantity * price))
    coefficient_tol = 1e-12 * max(1, quantity)
    headroom = coefficient * price + constant
    result.update({"inputs": {**{key: snapshot[key] for key in required},
                              "mmr_long": maintenance, "mmr_short": maintenance,
                              "close_fee": fee}, "A": coefficient, "B": constant,
                   "H_at_p0": headroom, "coefficient_tol": coefficient_tol,
                   "residual_tol": residual_tol,
                   "downward_reason": "no_long" if q_long == 0 else "no_downward_root",
                   "upward_reason": "no_short" if q_short == 0 else "no_upward_root"})
    if quantity == 0:
        return {**result, "status": "no_position", "reason": "no_position"}
    # A-near-zero has its own frozen state machine, before the general H check.
    if abs(coefficient) <= coefficient_tol:
        status = "no_finite_solution" if constant > residual_tol else "already_breached"
        return {**result, "status": status, "reason": status}
    root = -constant / coefficient
    if math.isfinite(root) and math.isclose(root, price, abs_tol=ABS_TOL, rel_tol=REL_TOL):
        return {**result, "status": "already_breached", "reason": "root at p0"}
    if headroom <= residual_tol:
        return {**result, "status": "already_at_or_below_maintenance",
                "reason": "H(p0) at or below numerical zero"}
    if not math.isfinite(root):
        return {**result, "status": NA, "reason": "non-finite root"}
    if root <= 0:
        return {**result, "status": "no_positive_solution", "reason": "root <= 0"}
    # Evaluate the original H equation, not just A*p+B (which may round to zero).
    residual = abs(equity + (q_long - q_short) * (root - price)
                   - maintenance * q_long * root - maintenance * q_short * root
                   - fee * quantity * root)
    result["residual_abs"] = _finite(residual, "H(root) residual")
    if residual > residual_tol:
        return {**result, "status": NA, "reason": "root residual exceeds tolerance"}
    if root < price and q_long > 0:
        result.update(downward_liquidation_price=root, downward_reason=None)
    elif root > price and q_short > 0:
        result.update(upward_liquidation_price=root, upward_reason=None)
    else:
        return {**result, "status": NA, "reason": "root has no adverse held side"}
    return {**result, "status": "ok", "reason": None}


def liquidation_price_range(holding_snapshots: list[dict], instrument_rules: dict | None) -> dict:
    """Compute the liquidation price estimates from platform output.

    Following the frozen ``cross_liquidation`` semantics: ``downward_liquidation_price``
    is the LONG-side estimate (a falling price liquidates the long book) and
    ``upward_liquidation_price`` is the SHORT-side estimate (a rising price
    liquidates the short book). MMR and the liquidation close fee must come from
    the platform ``instrumentRulesSnapshot``; when that snapshot is missing the
    result is ``N/A`` with a fixed reason rather than a fabricated default
    (D5-2: the current platform output carries no MMR/close-fee fields, so both
    columns stay N/A until the platform starts publishing them).
    """
    result = {"downward_liquidation_price": NA, "upward_liquidation_price": NA,
              "status": NA, "reason": None, "mmr": None, "close_fee": None,
              "worst_snapshot_time": None, "worst_gross_to_equity": None,
              "downward_range": None, "upward_range": None}
    if not holding_snapshots:
        return {**result, "reason": "no holding snapshots"}
    mmr, fee = _instrument_rules_parameters(instrument_rules)
    if mmr is None or fee is None:
        return {**result, "reason": "instrument rules snapshot lacks MMR/close fee"}
    result["mmr"], result["close_fee"] = mmr, fee
    snapshots = [snapshot for snapshot in holding_snapshots
                 if snapshot.get("positions") and snapshot.get("value")]
    if not snapshots:
        return {**result, "status": "no_position", "reason": "no position in any snapshot"}
    # Platform runtime publishes grossExposure as the ratio gross/value already
    # (B-6): compare and report the raw ratio, never divide by value again.
    worst = max(snapshots,
                key=lambda snapshot: _finite(snapshot["grossExposure"], "grossExposure"))
    snapshot = _liquidation_snapshot(worst)
    solved = cross_liquidation(snapshot, mmr, fee)
    downward, upward = solved.get("downward_liquidation_price"), solved.get("upward_liquidation_price")
    ranges = _liquidation_ranges(snapshots, mmr, fee)
    return {**result,
            "downward_liquidation_price": NA if downward is None else downward,
            "upward_liquidation_price": NA if upward is None else upward,
            "status": solved.get("status"), "reason": solved.get("reason"),
            "worst_snapshot_time": worst.get("time"),
            "worst_gross_to_equity": _finite(worst["grossExposure"], "grossExposure"),
            "downward_range": ranges["downward"], "upward_range": ranges["upward"]}


def _instrument_rules_parameters(instrument_rules: dict | None) -> tuple[float | None, float | None]:
    """Read MMR and liquidation close fee from the platform instrument rules."""
    if not isinstance(instrument_rules, dict):
        return None, None
    for key in ("maintenanceMarginRate", "maintenance_margin_rate", "mmr"):
        if instrument_rules.get(key) is not None:
            mmr = _finite(instrument_rules[key], key)
            break
    else:
        mmr = None
    for key in ("liquidationFeeRate", "liquidation_fee_rate", "closeFee", "close_fee"):
        if instrument_rules.get(key) is not None:
            fee = _finite(instrument_rules[key], key)
            break
    else:
        fee = None
    return mmr, fee


def _liquidation_snapshot(snapshot: dict) -> dict:
    """Map a platform holding snapshot onto the cross_liquidation input shape."""
    positions = snapshot.get("positions") or {}
    long_position, short_position = {}, {}
    for key, position in positions.items():
        side = str(key).rsplit("::", 1)[-1]
        if side == "long":
            long_position = position
        elif side == "short":
            short_position = position
    mark_price = (long_position.get("lastPrice") or short_position.get("lastPrice")
                  or snapshot.get("lastPrice"))
    # The platform stores a short position's amount as a negative number, while
    # cross_liquidation requires both quantities to be non-negative magnitudes.
    return {"equity": snapshot.get("value"), "q_long": long_position.get("amount") or 0.0,
            "q_short": abs(short_position.get("amount") or 0.0),
            "avg_long": long_position.get("avgCost") or 0.0,
            "avg_short": short_position.get("avgCost") or 0.0, "mark_price": mark_price,
            "available_margin": snapshot.get("cash")}


def _liquidation_ranges(snapshots: list[dict], mmr: float, fee: float) -> dict:
    """Collect the min/max of each liquidation price across all snapshots."""
    downward, upward = [], []
    for snapshot in snapshots:
        solved = cross_liquidation(_liquidation_snapshot(snapshot), mmr, fee)
        if solved.get("downward_liquidation_price") is not None:
            downward.append(solved["downward_liquidation_price"])
        if solved.get("upward_liquidation_price") is not None:
            upward.append(solved["upward_liquidation_price"])
    return {"downward": [min(downward), max(downward)] if downward else None,
            "upward": [min(upward), max(upward)] if upward else None}


def _cell_index(cells: list[dict]) -> dict:
    indexed = {}
    for cell in cells:
        contract, window = cell["contract"], cell["window"]
        if window not in ("W1", "W2", "W3", "W4"):
            raise ValueError("summary requires W1..W4")
        key = (contract, window)
        if key in indexed:
            raise ValueError("duplicate summary cell")
        if cell["cell_id"] != f"{contract}-{window}":
            raise ValueError("cell identity mismatch")
        indexed[key] = cell
    return indexed


def summarize_cells(cells: list[dict]) -> list[dict]:
    """Summarize each supplied contract over W1..W4; retain losing/failed windows."""
    indexed = _cell_index(cells)
    contracts = list(dict.fromkeys(cell["contract"] for cell in cells))
    summaries = []
    for contract in contracts:
        windows = [indexed.get((contract, f"W{index}")) for index in range(1, 5)]
        row = {"contract": contract, "windows_present": sum(cell is not None for cell in windows)}
        row["windows_missing"] = 4 - row["windows_present"]
        for column in METRIC_COLUMNS:
            values, reasons = [], []
            for cell in windows:
                value = cell.get(column) if cell else None
                if value is None or value == NA:
                    values.append(NA)
                    reasons.append((cell or {}).get("reason") or "missing metric/cell")
                else:
                    values.append(_finite(value, column))
                    reasons.append(None)
            valid = [value for value in values if value != NA]
            mean = statistics.mean(valid) if valid else NA
            row.update({f"{column}_mean": mean, f"{column}_valid_count": len(valid),
                        f"{column}_windows": values, f"{column}_reasons": reasons,
                        column: f"{mean} ({'/'.join(map(str, values))}); {len(valid)}/4"})
        # D5-3 (B-3): qualification follows evidence completeness and risk
        # semantics, not a hard-coded value. The two liquidation columns are a
        # designed N/A degradation (the platform publishes no MMR/close fee),
        # so their reasons never gate evidence sufficiency; only the
        # performance columns do. A failed window fails the contract, any
        # risk-breach window breaches it, otherwise qualified.
        window_qualifications = [
            (cell or {}).get("qualification") for cell in windows if cell]
        window_reasons = []
        for window, cell in zip(("W1", "W2", "W3", "W4"), windows):
            _, reason = cell_qualification(cell)
            if reason and reason != NA:
                window_reasons.append(f"{window}: {reason}")
        row["qualification_reasons"] = "; ".join(window_reasons) if window_reasons else NA
        gating_reasons = any(
            any(column_reasons) for column_reasons in
            (row[f"{column}_reasons"] for column in METRIC_COLUMNS
             if column not in ("downward_liquidation_price",
                               "upward_liquidation_price")))
        derived = [cell_qualification(cell) for cell in windows]
        if row["windows_missing"] or gating_reasons:
            row["qualification"] = "insufficient-evidence"
        elif "failed" in window_qualifications:
            row["qualification"] = "failed"
        elif any(qualification == "risk-breach"
                 for qualification, _ in derived):
            row["qualification"] = "risk-breach"
        else:
            row["qualification"] = "qualified"
        summaries.append(row)
    return summaries


AUDIT_FIELDS = {
    "cell", "seq", "bar_open", "bar_close", "ohlcv", "ohlcv_units", "equity", "q_long", "q_short",
    "avg_long", "avg_short", "gross", "gross_to_equity", "reserved_open_notional",
    "risk_action", "status_changes", "peak_equity", "drawdown_pct", "previous_seq",
}
AUDIT_NUMBERS = {
    "equity", "q_long", "q_short", "avg_long", "avg_short", "gross",
    "reserved_open_notional", "peak_equity", "drawdown_pct",
}


def reconcile_audit(logs: list[str], cell: dict | str) -> dict:
    """Reconcile controlled logs against an explicit expected window, never array length.

    A cell mapping is authoritative. For a cell-id string, INIT must carry its
    start/end boundaries. Without boundaries, continuity cannot be proven.
    Optional native_* totals on the cell are independently compared, not inferred.
    """
    cell_id = cell["cell_id"] if isinstance(cell, dict) else cell
    # Frequency follows the batch parameter (D5-1/R-05): the authoritative
    # source is the cell mapping, otherwise the INIT record must declare it.
    cell_frequency = (cell.get("frequency_seconds") if isinstance(cell, dict) else None)
    entries = {prefix: [] for prefix in ("GRID_INIT_V1", "GRID_AUDIT_V1", "GRID_END_V1")}
    reasons = []
    for line in logs:
        prefix, separator, payload = line.partition(" ")
        if prefix not in entries:
            if prefix.startswith("GRID_"):
                reasons.append("unknown controlled prefix")
            continue
        if not separator:
            raise ValueError("missing controlled JSON")
        record = json.loads(payload)
        canonical_json(record)  # Reject NaN/Inf anywhere in controlled payloads.
        if not isinstance(record, dict) or record.get("cell") != cell_id:
            raise ValueError("controlled log cell mismatch")
        if record.get("schema", prefix) != prefix:
            raise ValueError("controlled schema mismatch")
        entries[prefix].append(record)
    initial, audits, final = (entries[key] for key in entries)
    result = {"status": "unknown", "bars_checked": len(audits), "missing_bar_closes": [],
              "bankruptcy_skipped_callback": False, "audit_incomplete": True,
              "init_schema": "GRID_INIT_V1" if len(initial) == 1 else None,
              "end_schema": "GRID_END_V1" if len(final) == 1 else None,
              "bar_close_audit": "unknown", "event_audit": "unknown",
              "intrabar_tick_audit": "not_observable", "native_reconciliation": "unknown"}
    if len(initial) != 1 or len(final) != 1:
        return {**result, "reason": "missing/duplicate INIT or END"}
    init, end = initial[0], final[0]
    if not {"params", "training_summary"} <= init.keys():
        raise ValueError("missing INIT fields")
    audit_frequency = int(cell_frequency or init.get("frequency_seconds")
                          or DEFAULT_FREQUENCY_SECONDS)
    if audit_frequency <= 0:
        raise ValueError("invalid frequency_seconds")
    if not {"bars_total", "peak_equity", "net_pnl", "max_drawdown_pct", "return_count",
            "return_sum", "return_square_sum", "return_valid",
            "risk_breach_observed"} <= end.keys():
        raise ValueError("missing END fields")
    total = _integer(end["bars_total"], "bars_total")
    _finite(end["peak_equity"], "end peak_equity")
    _finite(end["net_pnl"], "end net_pnl")
    if _finite(end["max_drawdown_pct"], "end max_drawdown_pct") < 0:
        raise ValueError("end max_drawdown_pct out of range")
    count = _integer(end["return_count"], "end return_count")
    _finite(end["return_sum"], "end return_sum")
    _finite(end["return_square_sum"], "end return_square_sum")
    if _finite(end["return_square_sum"], "end return_square_sum") < 0:
        raise ValueError("end return_square_sum negative")
    if count > total:
        raise ValueError("end return_count exceeds bars_total")
    if not isinstance(end["return_valid"], bool) or not isinstance(
            end["risk_breach_observed"], bool):
        raise ValueError("end return_valid/risk_breach_observed must be bool")
    boundary = cell if isinstance(cell, dict) else init
    start = _time(boundary["start_utc"]) if boundary.get("start_utc") is not None else None
    stop = _time(boundary["end_utc"]) if boundary.get("end_utc") is not None else None
    if start is None or stop is None:
        reasons.append("expected time boundaries missing")
        expected = set()
    else:
        span = (stop - start).total_seconds()
        if span <= 0 or span % audit_frequency:
            raise ValueError("invalid audit window")
        expected = {start + dt.timedelta(seconds=audit_frequency * index)
                    for index in range(1, int(span // audit_frequency) + 1)}
        if total != len(expected):
            reasons.append("native bar count differs from expected window")
    seen_times, seen_seqs = set(), set()
    previous_seq = None
    rows = []
    risk_failed = False
    for audit in audits:
        if not AUDIT_FIELDS <= audit.keys():
            raise ValueError("missing AUDIT fields: " + ",".join(sorted(AUDIT_FIELDS - audit.keys())))
        seq = _integer(audit["seq"], "seq", 1)
        opened, closed = _time(audit["bar_open"]), _time(audit["bar_close"])
        if seq in seen_seqs or closed in seen_times:
            raise ValueError("duplicate seq/time")
        if closed != opened + dt.timedelta(seconds=audit_frequency):
            raise ValueError("conflicting bar open/close")
        if start is not None and (closed != start + dt.timedelta(seconds=seq * audit_frequency)
                                  or closed not in expected):
            raise ValueError("seq conflicts with expected time")
        if audit["previous_seq"] != previous_seq or seq != (previous_seq or 0) + 1:
            reasons.append("seq/previous_seq gap")
        if previous_seq is not None and seq <= previous_seq:
            raise ValueError("out-of-order seq")
        for field in AUDIT_NUMBERS:
            _finite(audit[field], field)
        _integer(audit["status_changes"], "status_changes")
        if any(audit[field] < 0 for field in ("q_long", "q_short", "avg_long", "avg_short",
                                            "gross", "reserved_open_notional")):
            raise ValueError("negative position/risk quantity")
        if not isinstance(audit["ohlcv"], dict):
            raise ValueError("OHLCV mapping required")
        prices = {field: _finite(audit["ohlcv"][field], field)
                  for field in ("open", "high", "low", "close", "volume")}
        if (min(prices.values()) <= 0 or prices["low"] > min(prices["open"], prices["close"])
                or prices["high"] < max(prices["open"], prices["close"])):
            raise ValueError("invalid/nonpositive OHLCV")
        gross = (audit["q_long"] + audit["q_short"]) * prices["close"]
        if not math.isclose(gross, audit["gross"], abs_tol=ABS_TOL, rel_tol=REL_TOL):
            reasons.append("gross does not match both absolute position notionals")
        if not isinstance(audit["risk_action"], str) or not audit["risk_action"]:
            reasons.append("risk action unknown")
        if not isinstance(audit["ohlcv_units"], dict) or not audit["ohlcv_units"]:
            reasons.append("unknown OHLCV units")
        elif (audit["ohlcv_units"].get("price") != "USDT"
              or audit["ohlcv_units"].get("volume") != "base"):
            reasons.append("unverified OHLCV units")
        if audit["equity"] <= 0:
            risk_failed = True
        if audit.get("risk_breach_observed") is True:
            # Design §6: a retained breach fact must keep failing even when the
            # closing bar's instantaneous equity/ratio/drawdown have recovered.
            reasons.append("risk_breach_observed=true retained at bar close")
            risk_failed = True
        if audit["equity"] > 0:
            ratio = _finite(audit["gross_to_equity"], "gross_to_equity")
            if not math.isclose(audit["gross"] / audit["equity"], ratio,
                                abs_tol=ABS_TOL, rel_tol=REL_TOL):
                reasons.append("gross/equity mismatch")
            if ratio > 2.5 or audit["drawdown_pct"] > 35:
                risk_failed = True
        rows.append({"time": _iso(closed), "equity": audit["equity"]})
        seen_times.add(closed)
        seen_seqs.add(seq)
        previous_seq = seq
    missing = sorted(expected - seen_times)
    incomplete = bool(missing or reasons or len(audits) != total)
    if len(audits) != total:
        reasons.append("AUDIT count differs from END bars_total")
    if missing:
        reasons.append("missing expected bar closes")
    # Only a full, continuous window can attest END's accumulated statistics.
    # Risk observations still fail independently, including on incomplete logs.
    statistics_complete = (bool(expected) and not missing
                           and len(audits) == total == len(expected)
                           and "seq/previous_seq gap" not in reasons)
    bankrupt = any(row["equity"] <= 0 for row in rows)
    bankruptcy_skipped = bankrupt and incomplete
    metrics = margin_metrics(rows, frequency_seconds=audit_frequency)
    if rows:
        if not math.isclose(end["net_pnl"], metrics["net_pnl"],
                            abs_tol=ABS_TOL, rel_tol=REL_TOL):
            reasons.append("END net PnL mismatch")
        if not math.isclose(end["peak_equity"], metrics["peak_equity"],
                            abs_tol=ABS_TOL, rel_tol=REL_TOL):
            reasons.append("END peak mismatch")
        if statistics_complete:
            running_peak, max_drawdown = INITIAL_MARGIN, 0.0
            previous_equity = None
            return_count, return_sum, return_square_sum = 0, 0.0, 0.0
            return_valid = True
            for audit in audits:
                equity = audit["equity"]
                running_peak = max(running_peak, equity)
                current_drawdown = 100 * (running_peak - equity) / running_peak
                max_drawdown = max(max_drawdown, current_drawdown)
                if previous_equity is not None and min(previous_equity, equity) > 0:
                    change = equity / previous_equity - 1
                    return_count += 1
                    return_sum += change
                    return_square_sum += change * change
                if equity <= 0:
                    return_valid = False
                previous_equity = equity
                if not math.isclose(audit["peak_equity"], running_peak,
                                    abs_tol=ABS_TOL, rel_tol=REL_TOL):
                    reasons.append("bar peak mismatch")
                if not math.isclose(audit["drawdown_pct"], current_drawdown,
                                    abs_tol=ABS_TOL, rel_tol=REL_TOL):
                    reasons.append("bar drawdown mismatch")
            if end["return_count"] != return_count:
                reasons.append("END return_count mismatch")
            if end["return_valid"] is not return_valid:
                reasons.append("END return_valid mismatch")
            for field, computed in (("max_drawdown_pct", max_drawdown),
                                    ("return_sum", return_sum),
                                    ("return_square_sum", return_square_sum)):
                if not math.isclose(end[field], computed, abs_tol=ABS_TOL, rel_tol=REL_TOL):
                    reasons.append("END " + field + " mismatch")
    native_checked = False
    if isinstance(cell, dict):
        native_checked = all(field in cell for field in (
            "native_bars_total", "native_net_pnl", "native_peak_equity"))
        for field, computed in (("native_bars_total", len(audits)),
                                ("native_net_pnl", metrics["net_pnl"]),
                                ("native_peak_equity", metrics["peak_equity"])):
            if field in cell:
                if computed == NA or not math.isclose(_finite(cell[field], field), computed,
                                                      abs_tol=ABS_TOL, rel_tol=REL_TOL):
                    reasons.append(field + " mismatch")
    incomplete = incomplete or bool(reasons)
    if end["risk_breach_observed"] is True:
        # Design §6: retain the breach fact even when closing indicators recovered.
        reasons.append("risk_breach_observed=true in END record")
        risk_failed = True
    status = "fail" if risk_failed or bankruptcy_skipped else "unknown" if incomplete else "ok"
    return {**result, "status": status, "reason": "; ".join(dict.fromkeys(reasons)) or None,
            "missing_bar_closes": [_iso(value) for value in missing],
            "bankruptcy_skipped_callback": bankruptcy_skipped, "audit_incomplete": incomplete,
            "bar_close_audit": "fail" if risk_failed else "unknown" if incomplete else "pass",
            "native_reconciliation": "checked" if native_checked and not reasons else "unknown",
            "metrics": metrics}


def _json_default(value: Any) -> str:
    if isinstance(value, dt.datetime):
        return _iso(value)
    raise TypeError(f"unsupported JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize canonical UTF-8 JSON, rejecting every non-finite numeric value."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False, default=_json_default)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_null_receipt(cell_id: str, reason: str) -> dict:
    """Represent no submission honestly, without inventing native identifiers."""
    if not reason:
        raise ValueError("null receipt requires reason")
    return {"cell_id": cell_id, "job_id": None, "run_id": None, "reason": reason,
            "billing": {"status": "absent"}}


def build_manifest(cells: list[dict]) -> dict:
    """Build a versioned offline plan; missing source/data identity blocks precheck."""
    _cell_index(cells)
    items = []
    for cell in cells:
        identity = {"cell": copy.deepcopy(cell), "market": {key: cell.get(key) for key in MARKET},
                    "start_utc": cell["start_utc"], "end_utc": cell["end_utc"],
                    "strategy_sha256": cell.get("strategy_sha256"),
                    "generator_sha256": cell.get("generator_sha256"),
                    "parameters": cell.get("parameters"), "data_identity": cell.get("data_identity"),
                    "initial_margin": INITIAL_MARGIN, "leverage_enabled": True, "leverage": 10,
                    "commission": 0.0005, "slippage": 0.0005, "funding": "not_modeled"}
        digest = _digest(identity)
        items.append({**copy.deepcopy(cell), "status": "planned", "identity": identity,
                      "body_digest": digest, "idempotency_key": "grid-plan-" + digest,
                      **build_null_receipt(cell["cell_id"], "offline plan; not submitted"),
                      "coverage": copy.deepcopy(cell.get("coverage")),
                      "limitations": ["no submission/replay implementation"]})
    return {"schema_version": 1, "items": items,
            "budgets": {contract: {key: 0 for key in BUDGET_LIMITS}
                        for contract in dict.fromkeys(cell["contract"] for cell in cells)},
            "submission_implemented": False}


def validate_manifest(manifest: dict) -> None:
    """Validate schema, identities, terminal receipts and persisted group usage."""
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema")
    canonical_json(manifest)
    _cell_index(manifest["items"])
    for item in manifest["items"]:
        if item.get("status") not in TRANSITIONS:
            raise ValueError("invalid manifest state")
        if not item.get("reason") and (item.get("job_id") is None or item.get("run_id") is None):
            raise ValueError("missing receipt reason")
        if item.get("run_id") is not None:
            _integer(item["run_id"], "run_id", 1)
        if item.get("status") in {"submitted", "succeeded"} and not item.get("job_id"):
            raise ValueError("submitted state requires actual job_id")
        if item.get("body_digest") != _digest(item["identity"]):
            raise ValueError("manifest identity digest mismatch")
        frozen = item["identity"]["cell"]
        for field in ("cell_id", "contract", "window", "start_utc", "end_utc", *MARKET,
                      "native_instrument", "strategy_sha256", "generator_sha256",
                      "parameters", "data_identity"):
            if canonical_json(item.get(field)) != canonical_json(frozen.get(field)):
                raise ValueError("manifest cell differs from frozen identity: " + field)
        if item.get("idempotency_key") != "grid-plan-" + item["body_digest"]:
            raise ValueError("plan identity key mismatch")
    for contract in dict.fromkeys(item["contract"] for item in manifest["items"]):
        usage = manifest.get("budgets", {}).get(contract)
        if usage is None:
            raise ValueError("persisted group budget missing: STOP")
        budget_remaining(usage)


def transition_manifest(manifest: dict, cell_id: str, status: str, *, reason: str,
                        job_id: str | None = None, run_id: int | None = None) -> dict:
    """Return a validated copy with one legal state transition; never submit jobs."""
    validate_manifest(manifest)
    updated = copy.deepcopy(manifest)
    matches = [item for item in updated["items"] if item["cell_id"] == cell_id]
    if len(matches) != 1:
        raise ValueError("unknown/duplicate manifest cell")
    item = matches[0]
    if status not in TRANSITIONS[item["status"]]:
        raise ValueError("illegal manifest state transition")
    if status in {"prechecked", "submitting"}:
        identity = item["identity"]
        if any(identity.get(key) is None for key in (
                "strategy_sha256", "generator_sha256", "parameters", "data_identity")):
            raise ValueError("source/parameter/data identity not frozen")
        if (not item.get("native_instrument")
                or (item.get("coverage") or {}).get("status") != "ok"):
            raise ValueError("instrument/coverage unverified")
    if status == "submitting":
        usage = updated["budgets"][item["contract"]]
        if not budget_remaining(usage)["may_continue"] or any(
                other["status"] in {"failed", "insufficient_evidence", "not_submitted_due_to_stop"}
                for other in updated["items"]):
            raise ValueError("budget/earlier failure requires STOP")
        updated["budgets"][item["contract"]] = consume_budget(
            usage, target_jobs=1, outer_jobs=1)
    item.update(status=status, reason=reason)
    if job_id is not None:
        item["job_id"] = job_id
    if run_id is not None:
        item["run_id"] = run_id
    validate_manifest(updated)
    return updated


def budget_remaining(usage: dict) -> dict:
    """Compute group remaining budget from cumulative persisted usage, no reset defaults."""
    remaining = {}
    for key, limit in BUDGET_LIMITS.items():
        if key not in usage:
            raise ValueError("unproven remaining budget: STOP")
        value = _finite(usage[key], key)
        if value < 0 or (key != "elapsed_seconds" and value != int(value)):
            raise ValueError("invalid cumulative budget")
        remaining[key] = max(0, limit - value)
    remaining["may_continue"] = all(usage[key] < BUDGET_LIMITS[key]
                                    for key in BUDGET_LIMITS if key != "evolution")
    remaining["may_continue"] &= usage["evolution"] == 0
    return remaining


def consume_budget(usage: dict, **increments: float) -> dict:
    """Add usage without mutating/resetting prior counters, including elapsed wall time."""
    budget_remaining(usage)
    updated = dict(usage)
    for key, increment in increments.items():
        if key not in BUDGET_LIMITS or _finite(increment, key) < 0:
            raise ValueError("invalid budget increment")
        updated[key] += increment
    budget_remaining(updated)
    return updated


def stop_decision(job_state: str, billing: dict, budget: dict) -> dict:
    """Offline stop decision only; absent billing is not a claim of free execution."""
    reasons = []
    if job_state not in {"none", "succeeded", "history_insufficient"}:
        reasons.append("nonterminal/unknown/failed job state")
    amount = max(_finite(billing.get(field, 0), field)
                 for field in ("charged_amount", "charged"))
    if billing.get("status") not in {"absent", "free", "disabled"} or amount > 0:
        reasons.append("billing contradiction/charge")
    for field in ("remaining_outer_jobs", "remaining_data_requests", "remaining_seconds"):
        if field not in budget or _finite(budget[field], field) <= 0:
            reasons.append("exhausted/unproven " + field)
    if budget.get("remaining_target_jobs", 1) <= 0 or budget.get("evolution", 0) != 0:
        reasons.append("target/Evolution budget")
    return {"may_submit": not reasons, "reason": "; ".join(reasons) or None,
            "billing_status": billing.get("status", "unknown")}


def write_manifest(manifest: dict, path: str | Path) -> None:
    """Atomically replace a single-writer local manifest, including persisted budgets."""
    validate_manifest(manifest)
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_manifest(path: str | Path) -> dict:
    """Read/validate persisted usage; never reconstruct a fresh budget on resume."""
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def write_cell_parameters(parameters: dict, path: str | Path) -> dict:
    """Write only the approved parameter/source projection, without arbitrary payloads."""
    allowed = {"cell_id", "L", "U", "g_pct", "N", "grid_lines", "generator_sha256",
               "strategy_sha256", "generator_path", "generator_version", "training_start_utc",
               "training_end_utc", "training_available_at_utc", "training_count", "short_history",
               "training_identity", "parameters_digest", "reason"}
    result = {key: value for key, value in parameters.items() if key in allowed}
    Path(path).write_text(canonical_json(result) + "\n", encoding="utf-8")
    return result


CELL_RESULT_FIELDS = ("cell_id", "status", "reason", "net_pnl", "margin_return_pct", "sharpe",
                      "max_drawdown_pct", "peak_equity", "peak_time", "trough_time",
                      "raw_max_drawdown_pct", "return_count", "bar_count", "limitation",
                      "liquidation", "coverage_status", "tool_status", "research_status",
                      "qualification", "job_id", "run_id")
CELL_METRICS_FIELDS = ("cell_id", "formula_version", "net_pnl", "margin_return_pct", "sharpe",
                       "max_drawdown_pct", "peak_equity", "return_count", "bar_count",
                       "risk_free", "ddof", "periods_per_year", "reason", "limitation")
CELL_VOLUME_FIELDS = ("cell_id", "base_volume", "raw_v_contracts", "quanto_multiplier",
                      "quote_volume", "quote_volume_reason", "volume_unit",
                      "normalization_version", "historical_applicability", "coverage_status",
                      "evidence_missing", "reason")


def write_cell_result(result: dict, path: str | Path) -> dict:
    """Write the frozen CELL.result.json field projection (Design §7)."""
    projected = {key: result[key] for key in CELL_RESULT_FIELDS if key in result}
    Path(path).write_text(canonical_json(projected) + "\n", encoding="utf-8")
    return projected


def write_cell_metrics(metrics: dict, path: str | Path) -> dict:
    """Write the frozen CELL.metrics.json field projection (Design §7)."""
    projected = {key: metrics[key] for key in CELL_METRICS_FIELDS if key in metrics}
    Path(path).write_text(canonical_json(projected) + "\n", encoding="utf-8")
    return projected


def write_cell_volume(volume: dict, path: str | Path) -> dict:
    """Write the frozen CELL.volume.json field projection (Design §7)."""
    projected = {key: volume[key] for key in CELL_VOLUME_FIELDS if key in volume}
    Path(path).write_text(canonical_json(projected) + "\n", encoding="utf-8")
    return projected


def write_cell_audit(lines: list[str], path: str | Path) -> None:
    """Persist controlled GRID_*_V1 log lines; each line must re-serialize as canonical JSON."""
    canonical_json([json.loads(line.partition(" ")[2]) for line in lines if line.strip()])
    Path(path).write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def append_cell_receipt(receipt: dict, path: str | Path) -> None:
    """Append one receipt line; read-back never overwrites the original entries (Design §7)."""
    canonical_json(receipt)
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(canonical_json(receipt) + "\n")


def _write_csv(rows: list[dict], columns: list[str], path: str | Path) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def cell_qualification(cell: dict | None) -> tuple[str, str]:
    """Derive a cell's qualification and its human-readable reasons.

    Evidence gaps dominate first (missing window or missing metrics), then the
    frozen risk envelope: gross/equity above 2.5 or peak-to-tround drawdown
    beyond 35%. Reasons are semicolon-separated; N/A means no reason applies.
    """
    if not cell:
        return "insufficient-evidence", "missing window/cell"
    reasons = []
    gross = cell.get("worst_gross_to_equity")
    if isinstance(gross, (int, float)) and gross > RISK_GROSS_TO_EQUITY_LIMIT:
        reasons.append(f"杠杆超限(敞口/权益 {gross:.2f} > {RISK_GROSS_TO_EQUITY_LIMIT})")
    drawdown = cell.get("max_drawdown_pct")
    if isinstance(drawdown, (int, float)) and abs(drawdown) > RISK_DRAWDOWN_LIMIT_PCT:
        reasons.append(f"回撤超限({abs(drawdown):.1f}% > {RISK_DRAWDOWN_LIMIT_PCT}%)")
    if reasons:
        return "risk-breach", "; ".join(reasons)
    for column in METRIC_COLUMNS:
        value = cell.get(column)
        if value is None or value == NA:
            if column in ("downward_liquidation_price", "upward_liquidation_price"):
                continue
            return "insufficient-evidence", f"missing metric {column}"
    return "qualified", NA


def average_amount_per_grid(executions: list[dict] | None) -> tuple[float | None, int, int]:
    """Mean quote notional per grid cell, from the platform's own order stream.

    The platform encodes the grid cell in ``client_order_id`` (``grid-<n>-...``)
    and the filled quote notional in ``executions[].notional``. Cells are
    weighted equally: the mean is taken over per-cell means, so a cell traded
    many times does not dominate the figure. Returns
    ``(mean_notional, cells_traded, orders_counted)``.
    """
    if not executions:
        return None, 0, 0
    cells: dict[int, list[float]] = {}
    for execution in executions:
        match = re.match(r"grid-(\d+)-", str(execution.get("client_order_id") or ""))
        if not match:
            continue
        notional = float(execution.get("notional") or 0.0)
        cells.setdefault(int(match.group(1)), []).append(notional)
    if not cells:
        return None, 0, 0
    per_cell = [sum(values) / len(values) for values in cells.values() if values]
    if not per_cell:
        return None, 0, 0
    return sum(per_cell) / len(per_cell), len(per_cell), sum(len(v) for v in cells.values())


def _grid_count_field(row: dict) -> str:
    """Grid count column: mean(N1/N2/N3/N4); n/4 (Pascal 2026-11-04 addendum)."""
    return row.get("N") or NA


def _amount_per_grid_field(row: dict) -> str:
    """Average amount per grid cell, mean(W1/W2/W3/W4); n/4 format."""
    values = row.get("amount_per_grid_windows")
    if not values:
        return NA
    valid = [value for value in values if isinstance(value, (int, float))]
    count = len(valid)
    mean = (sum(valid) / count) if count else NA
    mean_s = f"{mean:.2f}" if isinstance(mean, float) else str(mean)
    shown = "/".join(("-" if not isinstance(value, (int, float))
                      else f"{value:.2f}") for value in values)
    return f"{mean_s} ({shown}); {count}/4"


def _total_pairs_field(row: dict) -> str:
    """Total matched-pair count column with the same mean(window) format."""
    values = row.get("pairs_windows")
    if not values:
        return NA
    valid = [value for value in values if isinstance(value, (int, float))]
    count = len(valid)
    mean = (sum(valid) / count) if count else NA
    mean_s = f"{mean:.2f}".rstrip("0").rstrip(".") if isinstance(mean, float) else str(mean)
    shown = "/".join(("-" if not isinstance(value, (int, float)) else
                      (f"{value:.2f}".rstrip("0").rstrip(".")
                       if isinstance(value, float) else str(int(value))))
                     for value in values)
    return f"{mean_s} ({shown}); {count}/4"


def _grid_params_field(row: dict) -> str:
    """Per-window ``[L,U]:g_pct%`` list, W1..W4 (Pascal 2026-11-04 carrier spec)."""
    cells = row.get("_source_cells") or {}
    parts = []
    for window in ("W1", "W2", "W3", "W4"):
        cell = cells.get(window)
        if cell and cell.get("L") is not None and cell.get("U") is not None:
            spacing = cell.get("g_pct")
            spacing = f"{spacing:g}" if isinstance(spacing, (int, float)) else NA
            parts.append(f"[{cell['L']:g},{cell['U']:g}]:{spacing}%")
        else:
            parts.append(f"[{NA},{NA}]:{NA}%")
    return ",".join(parts)


# Display symbols for the qualification enum (Pascal 2026-11-04): the report
# table reads as ticks and warnings, the carrier CSV keeps the machine enum.
QUALIFICATION_SYMBOLS = {
    "qualified": "\u2713",
    "risk-breach": "\u26a0",
    "failed": "\u2717",
    "insufficient-evidence": "?",
}


def qualification_symbol(qualification: str) -> str:
    """Symbol for a qualification verdict: tick, warning, cross or '?'."""
    return QUALIFICATION_SYMBOLS.get(qualification, "?")


def _window_qualifications_field(row: dict) -> str:
    """Per-window qualification list, W1..W4, from the source cells' rows."""
    indexed = row.get("_source_cells") or {}
    parts = [f"{window}:{cell_qualification(indexed.get(window))[0]}"
             for window in ("W1", "W2", "W3", "W4")]
    return ",".join(parts)


def write_comparison_csv(summary: list[dict], path: str | Path,
                         anchor_utc: Any = None,
                         source_cells: list[dict] | None = None) -> None:
    """Write four frozen-contract rows, retaining absent contracts as N/A with reasons.

    D5-3: explicit anchor required; task_date/anchor_utc land in the output and
    the placeholder qualification is ``insufficient-evidence`` (enum closure).
    """
    if anchor_utc is None:
        raise ValueError("anchor_utc is required (D5-3): pass the batch task date")
    task_date = _midnight(anchor_utc).date().isoformat()
    by_contract = {row["contract"]: row for row in summary}
    if len(by_contract) != len(summary) or set(by_contract) - set(DEFAULT_CONTRACTS):
        raise ValueError("comparison carrier requires unique frozen contracts")
    rows = []
    for contract in DEFAULT_CONTRACTS:
        fallback = summarize_cells([{"cell_id": f"{contract}-W1", "contract": contract,
                                     "window": "W1", "reason": "no submitted evidence"}])[0]
        if contract not in by_contract:
            fallback.update(windows_present=0, windows_missing=4)
        row = by_contract.get(contract, fallback)
        row.setdefault("task_date", task_date)
        row.setdefault("anchor_utc", _iso(_midnight(anchor_utc)))
        cells_index = _cell_index(source_cells or [])
        row["_source_cells"] = {window: cells_index.get((contract, window))
                                for window in ("W1", "W2", "W3", "W4")}
        row["pairs_windows"] = [(row["_source_cells"][window] or {}).get("pairs")
                                for window in ("W1", "W2", "W3", "W4")]
        row["amount_per_grid_windows"] = [
            (row["_source_cells"][window] or {}).get("avg_grid_order_notional")
            for window in ("W1", "W2", "W3", "W4")]
        row["grid_params"] = _grid_params_field(row)
        row["grid_count"] = _grid_count_field(row)
        row["amount_per_grid"] = _amount_per_grid_field(row)
        row["total_pairs"] = _total_pairs_field(row)
        row["window_qualifications"] = _window_qualifications_field(row)
        row["metrics_caliber"] = METRICS_CALIBER
        rows.append(row)
    # Table B export shape (Pascal 2026-11-04): the standalone geometry columns
    # (L, U, g_pct, N), the anchor and the caliber note are redundant against
    # grid_params / grid_count / task_date and are not exported. The frozen
    # METRIC_COLUMNS set stays unchanged; only the export list narrows.
    _write_csv(rows, ["contract", "task_date",
                      "margin_return_pct", "max_drawdown_pct",
                      "grid_params", "grid_count", "amount_per_grid", "total_pairs",
                      "sharpe",
                      "downward_liquidation_price", "upward_liquidation_price",
                      "window_qualifications", "qualification",
                      "qualification_reasons"], path)
    # The Markdown table is rendered from the very same rows, so the report and
    # the carrier cannot drift in order, headers or formats.
    markdown_path = Path(path).with_name("table-b-summary.md")
    write_summary_markdown(rows, markdown_path)


# Table B presentation contract (Pascal 2026-11-04). The column order, the
# Chinese headers and the number formats live here so that every research run
# emits the same table without hand-writing headers or formats.
TABLE_B_HEADERS = [
    ("contract", "合约"),
    ("task_date", "任务日"),
    ("margin_return_pct", "区间收益率%"),
    ("max_drawdown_pct", "MDD%"),
    ("grid_params", "网格参数[W1→W4]"),
    ("grid_count", "网格数量"),
    ("amount_per_grid", "平均每格金额(USDT)"),
    ("total_pairs", "总配对次数"),
    ("sharpe", "Sharpe"),
    ("downward_liquidation_price", "多头强平价"),
    ("upward_liquidation_price", "空头强平价"),
    ("window_qualifications", "逐窗判定"),
    ("qualification", "合约判定"),
    ("qualification_reasons", "风险警示原因"),
]

TABLE_B_FOOTNOTES = [
    "判定符号：✓ = qualified（合格）；⚠ = risk-breach（风险突破）；✗ = failed；? = 证据不足。"
    "逐窗判定按 W1→W4 排列（W1=最近三月）。",
    "指标口径：收益率 = 窗口区间累计收益（非年化，保证金口径）；Sharpe = 逐 bar 权益收益"
    "算术均值 × √periodsPerYear（不惩罚方差拖累，负区间收益可为正）；MDD = 权益峰谷回撤；"
    "强平价恒 N/A（平台无 MMR/强平费字段）；平均每格金额 = 平台成交流中每个网格格子的"
    "挂单名义金额均值（格等权，跨窗口再取均值），单位 USDT。括号内为逐窗口值。",
]


def format_summary_value(value: Any, digits: int = 2) -> str:
    """Format one multi-window cell as ``mean (W1/W2/W3/W4)``.

    Plain numbers keep their trailing zeros trimmed; a missing window shows
    as a dash so the reader sees the gap instead of a silent omission.
    """
    if value is None or value == NA:
        return NA
    body = str(value).split(";")[0].strip()
    if "(" not in body:
        return body
    mean, rest = body.split("(", 1)
    windows = rest.rstrip(")").split("/")

    def render(part: str) -> str:
        try:
            number = float(part)
        except (TypeError, ValueError):
            return part
        rendered = f"{number:.{digits}f}"
        return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered

    return f"{render(mean)} ({'/'.join(render(part) for part in windows)})"


def format_grid_params(value: Any) -> str:
    """Render the per-window grid parameters as ``[L,U]:gap%`` separated by ' · '."""
    if not value or value == NA:
        return NA
    parts = []
    for bounds, gap in re.findall(r"\[([^\]]*)\]:([^,\s]+)", str(value)):
        rendered = []
        for number in bounds.split(","):
            number = number.strip()
            try:
                rendered.append(f"{float(number):.6g}")
            except (TypeError, ValueError):
                rendered.append(number)
        parts.append(f"[{', '.join(rendered)}]:{gap}")
    return " · ".join(parts)


def render_summary_markdown(rows: list[dict]) -> str:
    """Render table B as Markdown from the frozen column contract.

    ``rows`` are the same dicts the CSV carrier writes, so the table and the
    carrier cannot drift: one shape, one order, one set of headers.
    """
    header = [label for _, label in TABLE_B_HEADERS]
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(["---"] * len(header)) + "|"]
    for row in rows:
        cells = []
        for key, _ in TABLE_B_HEADERS:
            value = row.get(key)
            if key == "grid_params":
                cells.append(format_grid_params(value))
            elif key in ("margin_return_pct", "max_drawdown_pct", "sharpe",
                         "grid_count", "amount_per_grid", "total_pairs"):
                cells.append(format_summary_value(value))
            elif key in ("window_qualifications", "qualification"):
                cells.append(_symbol_form(value))
            elif key in ("downward_liquidation_price", "upward_liquidation_price"):
                # Design N/A: the platform exposes no MMR data source, so the
                # report shows the marker, never the raw carrier string.
                cells.append(NA)
            else:
                cells.append(str(value) if value is not None else NA)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _symbol_form(value: Any) -> str:
    """Render a qualification enum as its display symbol."""
    if not value or value == NA:
        return NA
    if isinstance(value, str) and "," in value:
        parts = []
        for chunk in value.split(","):
            window, _, verdict = chunk.strip().partition(":")
            parts.append(f"{window}{qualification_symbol(verdict)}")
        return " ".join(parts)
    return qualification_symbol(str(value))


def write_summary_markdown(rows: list[dict], path: str | Path) -> None:
    """Write table B as a Markdown fragment with the frozen headers and notes."""
    body = render_summary_markdown(rows)
    notes = "\n\n".join(TABLE_B_FOOTNOTES)
    Path(path).write_text(body + "\n\n" + notes + "\n", encoding="utf-8")


def write_cells_csv(cells: list[dict], path: str | Path, anchor_utc: Any = None,
                    frequency_seconds: int = DEFAULT_FREQUENCY_SECONDS) -> None:
    """Write all sixteen frozen target rows; never drop missing/failed targets.

    D5-3 (B-1): the skeleton MUST be laid from an explicit anchor (the batch
    task date), never from a default constant, so placeholder rows carry the
    real window boundaries; task_date/anchor_utc land in the output (D5-3a).
    qualification placeholder is ``insufficient-evidence`` (B-3 enum closure);
    unknown tool states degrade to N/A instead of the undefined value.
    """
    indexed = _cell_index(cells)
    if anchor_utc is None:
        raise ValueError("anchor_utc is required (D5-3): pass the batch task date")
    planned = build_cells(anchor_utc=anchor_utc, frequency_seconds=frequency_seconds)
    task_date = _midnight(anchor_utc).date().isoformat()
    if set(indexed) - {(cell["contract"], cell["window"]) for cell in planned}:
        raise ValueError("cells carrier requires frozen target identities")
    rows = []
    for plan in planned:
        supplied = indexed.get((plan["contract"], plan["window"]))
        row = {**plan, "task_date": task_date,
               **{column: NA for column in METRIC_COLUMNS},
               "status": "insufficient_evidence", "reason": "no submitted evidence",
               "job_id": None, "run_id": None, "tool_status": NA,
               "research_status": "insufficient-evidence",
               "qualification": "insufficient-evidence"}
        if supplied:
            row.update(supplied)
        for key in ("start_utc", "end_utc", "anchor_utc"):
            row[key] = _iso(row[key])
        for column in METRIC_COLUMNS:
            if row[column] is None:
                row[column] = NA
        rows.append(row)
    _write_csv(rows, ["task_date", "anchor_utc", "cell_id", "contract", "window",
                      *MARKET, "native_instrument", "start_utc", "end_utc",
                      "frequency_seconds", "expected_bars",
                      *METRIC_COLUMNS, "status", "reason",
                      "job_id", "run_id", "tool_status", "research_status",
                      "qualification"], path)

    # ---- comparison carrier laid from the same explicit anchor (B-1/B-3) ----
    summary = summarize_cells(cells)
    comparison = []
    for contract in DEFAULT_CONTRACTS:
        match = [row for row in summary if row["contract"] == contract]
        comparison.extend(match)
    write_comparison_csv(comparison, Path(path).with_name(
        Path(path).stem + "-comparison" + Path(path).suffix), anchor_utc=anchor_utc)
