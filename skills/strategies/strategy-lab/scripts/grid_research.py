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
import math
from pathlib import Path
import statistics
from typing import Any

def generate_strategy_source(*, cell: str | dict, template_sha256: str,
                             geometry: dict | None = None) -> str:
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
        cell=cell, template_sha256=template_sha256, geometry=geometry)


UTC = dt.timezone.utc
DEFAULT_CONTRACTS = ("PUMPUSDT", "AAVEUSDT", "JUPUSDT", "SUIUSDT")
DEFAULT_ANCHOR = dt.datetime(2026, 10, 31, tzinfo=UTC)
DEFAULT_WINDOW_COUNT = 4
INITIAL_MARGIN = 1000.0
FREQUENCY_SECONDS = 900
ABS_TOL = 1e-12
REL_TOL = 1e-10
NA = "N/A"
COMPRESSED_EQUITY_LIMITATION = (
    "Compressed equity cannot independently verify full equal-frequency Sharpe or MDD."
)
MARKET = {
    "venue": "gate", "market_type": "swap", "settle": "USDT",
    "product": "USDT-settled linear perpetual", "frequency": "15m",
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
                anchor_utc: Any = None) -> list[dict]:
    """Build parameterized half-open cells without consulting the machine clock.

    The real coordinating entry must separately call validate_run_anchor before
    any business use. Explicit future anchors here are valid offline calendars.
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
         "expected_15m_bars": int((end - start).total_seconds() // FREQUENCY_SECONDS)}
        for contract in contracts for window, start, end in windows
    ]


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


def margin_metrics(bar_close_rows: list[dict]) -> dict:
    """Compute margin return/MDD and population Sharpe on consecutive 15m closes.

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
    missing = any((right - left).total_seconds() != FREQUENCY_SECONDS
                  for left, right in zip(times, times[1:]))
    reasons = []
    if not equities:
        reasons.append("empty equity sample")
    if missing:
        reasons.append("missing/duplicate/non-15m bar")
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
        sharpe = statistics.mean(returns) / statistics.pstdev(returns) * math.sqrt(35040)
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
            "risk_free": 0, "ddof": 0, "periods_per_year": 35040,
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
        row["qualification"] = "insufficient-evidence"
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
        if span <= 0 or span % FREQUENCY_SECONDS:
            raise ValueError("invalid audit window")
        expected = {start + dt.timedelta(seconds=FREQUENCY_SECONDS * index)
                    for index in range(1, int(span // FREQUENCY_SECONDS) + 1)}
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
        if closed != opened + dt.timedelta(seconds=FREQUENCY_SECONDS):
            raise ValueError("conflicting bar open/close")
        if start is not None and (closed != start + dt.timedelta(seconds=seq * FREQUENCY_SECONDS)
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
    metrics = margin_metrics(rows)
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


def write_comparison_csv(summary: list[dict], path: str | Path) -> None:
    """Write four frozen-contract rows, retaining absent contracts as N/A with reasons."""
    by_contract = {row["contract"]: row for row in summary}
    if len(by_contract) != len(summary) or set(by_contract) - set(DEFAULT_CONTRACTS):
        raise ValueError("comparison carrier requires unique frozen contracts")
    rows = []
    for contract in DEFAULT_CONTRACTS:
        fallback = summarize_cells([{"cell_id": f"{contract}-W1", "contract": contract,
                                     "window": "W1", "reason": "no submitted evidence"}])[0]
        if contract not in by_contract:
            fallback.update(windows_present=0, windows_missing=4)
        rows.append(by_contract.get(contract, fallback))
    _write_csv(rows, ["contract", *METRIC_COLUMNS, "windows_present", "windows_missing",
                      "qualification"], path)


def write_cells_csv(cells: list[dict], path: str | Path) -> None:
    """Write all sixteen frozen target rows; never drop missing/failed targets."""
    indexed = _cell_index(cells)
    planned = build_cells()
    if set(indexed) - {(cell["contract"], cell["window"]) for cell in planned}:
        raise ValueError("cells carrier requires frozen target identities")
    rows = []
    for plan in planned:
        supplied = indexed.get((plan["contract"], plan["window"]))
        row = {**plan, **{column: NA for column in METRIC_COLUMNS},
               "status": "insufficient_evidence", "reason": "no submitted evidence",
               "job_id": None, "run_id": None, "tool_status": "unknown",
               "research_status": "insufficient-evidence", "qualification": "unknown"}
        if supplied:
            row.update(supplied)
        for key in ("start_utc", "end_utc"):
            row[key] = _iso(row[key])
        for column in METRIC_COLUMNS:
            if row[column] is None:
                row[column] = NA
        rows.append(row)
    _write_csv(rows, ["cell_id", "contract", "window", *MARKET, "native_instrument",
                      "start_utc", "end_utc", *METRIC_COLUMNS, "status", "reason",
                      "job_id", "run_id", "tool_status", "research_status", "qualification"], path)
