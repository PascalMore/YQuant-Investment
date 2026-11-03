"""Offline coordinator/static generator for SPEC-06-002; never runs a strategy.

Only source text and the existing grid_research pure calculations are used.
No CLI business operation is enabled while G-01/G-02/G-03 remain unresolved.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

LAB = Path(__file__).resolve().parents[2]
TEMPLATE = LAB / "strategies/neutral-grid-pumpusdt/strategy.py"
TEMPLATE_SHA256 = "25320a59133818ecbb2d363cc418b0bae717bdcf669fc9f46f67be294056ac85"
TEMPLATE_PATH = "neutral-grid-pumpusdt/strategy.py"

# Source text only. These functions are executed exclusively by the native sandbox,
# never imported/executed by this module or the offline tests.
AUDIT_SOURCE = '''
def _number(value):
    number = float(value)
    if number != number or abs(number) == float("inf"):
        raise ValueError("nonfinite audit field")
    return number


def _utc(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _emit(context, prefix, fields):
    context.log(prefix + " " + json.dumps(
        dict(fields, schema=prefix, cell=CELL_ID), sort_keys=True,
        separators=(",", ":"), allow_nan=False))


def _risk_snapshot(context, price):
    equity = _number(context.portfolio.available_cash)
    q_long = 0.0
    q_short = 0.0
    cost_long = 0.0
    cost_short = 0.0
    for position in get_positions().values():
        amount = _number(position.amount)
        average = _number(position.avg_cost)
        equity += position.amount * price
        if position.position_side == "long" and amount >= 0:
            q_long += amount
            cost_long += amount * average
        elif position.position_side == "short" and amount <= 0:
            q_short += abs(amount)
            cost_short += abs(amount) * average
        else:
            raise ValueError("position side/sign unknown")
    gross = (q_long + q_short) * price
    return {"equity": equity, "q_long": q_long, "q_short": q_short,
            "avg_long": cost_long / q_long if q_long else 0.0,
            "avg_short": cost_short / q_short if q_short else 0.0,
            "gross": gross, "gross_to_equity": gross / equity if equity > 0 else None}


def _refresh_open_orders():
    changes = 0
    references = list(g.open_entries)
    references.extend(ref for ref in g.cell_refs if ref and ref not in g.open_entries)
    for reference in references:
        status = _status(reference)
        name = str(status.get("status") or "unknown").lower()
        filled_quantity = _number(status.get("filled_quantity"))
        if filled_quantity < 0:
            raise ValueError("negative cumulative fill")
        observation = (name, filled_quantity)
        if g.order_observations.get(reference) != observation:
            changes += 1
            g.order_observations[reference] = observation
        if reference not in g.open_entries:
            continue
        entry = g.open_entries[reference]
        if filled_quantity + 1e-12 < entry["filled_quantity"]:
            raise ValueError("cumulative fill regressed")
        entry["filled_quantity"] = filled_quantity
        entry["status"] = name
        if name in ("filled", "cancelled", "rejected"):
            entry["remaining"] = 0.0
        elif name in ("queued", "deferred", "submitted", "open", "partial", "cancel_pending"):
            entry["remaining"] = max(0.0, entry["target_quantity"] - filled_quantity)
        else:
            g.stop_adding = True
            g.risk_action = "unknown_order_status_stop"
            # Unknown is not zero exposure: retain the full unfilled reservation.
            entry["remaining"] = max(0.0, entry["target_quantity"] - filled_quantity)
    g.status_changes += changes
    g.reserved_open_notional = sum(
        entry["remaining"] * entry["limit_price"] for entry in g.open_entries.values())


def _cancel_open_entries():
    for reference, entry in g.open_entries.items():
        if entry["remaining"] > 0:
            cancel_order(reference)
    # Cancellation is not assumed synchronous. Re-read public cumulative status.
    _refresh_open_orders()


def _capacity_allows(context, side, target_quantity, entry_price):
    _refresh_open_orders()
    if g.stop_adding:
        return False
    snapshot = _risk_snapshot(context, g.current_price)
    reserved_open_notional = g.reserved_open_notional
    candidate_notional = target_quantity * entry_price
    pending = [entry for entry in g.open_entries.values() if entry["remaining"] > 0]
    pending.append({"remaining": target_quantity, "limit_price": entry_price, "side": side})
    scenario_low = min(CELL_LOWER[0], g.current_low, entry_price, g.current_price)
    scenario_high = max(CELL_UPPER[-1], g.current_high, entry_price, g.current_price)
    # Explicit finite price-range scenario, NOT a guarantee against arbitrary gaps.
    # All opening remainders may fill; favorable subset PnL is not used as funding.
    for scenario_price in (scenario_low, g.current_price, scenario_high):
        reserved_gross = sum(entry["remaining"] * scenario_price for entry in pending)
        estimated_cost = (reserved_open_notional + candidate_notional + reserved_gross) * (
            FEE_RATE + SLIPPAGE_RATE)
        pending_adverse_pnl = sum(min(0.0, entry["remaining"] * (
            scenario_price - entry["limit_price"]) * (1 if entry["side"] == "long" else -1))
            for entry in pending)
        scenario_equity = snapshot["equity"] + (
            snapshot["q_long"] - snapshot["q_short"]) * (
                scenario_price - g.current_price) + pending_adverse_pnl - estimated_cost
        scenario_gross = (snapshot["q_long"] + snapshot["q_short"]) * scenario_price + reserved_gross
        if scenario_equity <= 0 or scenario_gross > GROSS_LIMIT * scenario_equity:
            g.risk_action = "capacity_refused_price_range_scenario"
            return False
    return True


def _observe_risk(context, price):
    snapshot = _risk_snapshot(context, price)
    equity = snapshot["equity"]
    gross = snapshot["gross"]
    g.audit_peak = max(g.audit_peak, equity)
    drawdown = 100 * (g.audit_peak - equity) / g.audit_peak
    if equity <= 0 or gross / equity > GROSS_LIMIT or drawdown > 35:
        g.risk_breach = True
        g.stop_adding = True
        g.risk_action = "visible_breach_cancel_open_reduce_next_bar"
        _cancel_open_entries()
        if not g.risk_reduction_sent:
            _close_all("grid_visible_risk_breach")
            g.risk_reduction_sent = True
    elif g.stop_adding:
        _cancel_open_entries()
    return snapshot


def handle_data(context, data):
    g.current_price = _number(data.current(INSTRUMENT, "close", frequency=TIMEFRAME))
    g.current_low = _number(data.current(INSTRUMENT, "low", frequency=TIMEFRAME))
    g.current_high = _number(data.current(INSTRUMENT, "high", frequency=TIMEFRAME))
    if min(g.current_price, g.current_low, g.current_high) <= 0:
        raise ValueError("nonpositive price: audit unknown")
    _refresh_open_orders()
    _observe_risk(context, g.current_price)
    if g.halted:
        return
    _reconcile_initial()
    _reconcile_cells()
    _arm_orders(context, g.current_price)


def after_trading_end(context, data):
    # The engine has synchronized fills before handle_data. New/cancelled intents
    # are publicly visible here. total_value is updated later: revalue cash/legs.
    _refresh_open_orders()
    price = _number(data.current(INSTRUMENT, "close", frequency=TIMEFRAME))
    snapshot = _risk_snapshot(context, price)
    _observe_risk(context, price)
    opened = _utc(context.current_dt)
    closed = opened + datetime.timedelta(seconds=900)
    previous_seq = g.audit_seq if g.audit_seq else None
    g.audit_seq += 1
    equity = snapshot["equity"]
    g.audit_peak = max(g.audit_peak, equity)
    g.audit_max_drawdown = max(g.audit_max_drawdown, 100 * (g.audit_peak - equity) / g.audit_peak)
    if g.previous_equity is not None and min(g.previous_equity, equity) > 0:
        change = equity / g.previous_equity - 1
        g.return_count += 1
        g.return_sum += change
        g.return_square_sum += change * change
    elif equity <= 0:
        g.return_valid = False
    g.previous_equity = equity
    ohlcv = {field: _number(data.current(INSTRUMENT, field, frequency=TIMEFRAME))
             for field in ("open", "high", "low", "close", "volume")}
    _emit(context, "GRID_AUDIT_V1", dict(snapshot,
        seq=g.audit_seq, previous_seq=previous_seq,
        bar_open=opened.isoformat().replace("+00:00", "Z"),
        bar_close=closed.isoformat().replace("+00:00", "Z"),
        ohlcv=ohlcv, ohlcv_units=OHLCV_UNITS,
        reserved_open_notional=g.reserved_open_notional, risk_action=g.risk_action,
        risk_breach_observed=g.risk_breach, status_changes=g.status_changes,
        peak_equity=g.audit_peak, drawdown_pct=100 * (g.audit_peak - equity) / g.audit_peak,
        event_audit="unknown", intrabar_tick_audit="not_observable",
        capacity_model="finite_price_range_scenario_not_gap_guarantee"))
    g.status_changes = 0
    if closed.isoformat().replace("+00:00", "Z") == END_UTC:
        _emit(context, "GRID_END_V1", {
            "bars_total": g.audit_seq, "peak_equity": g.audit_peak,
            "net_pnl": equity - INITIAL_MARGIN, "max_drawdown_pct": g.audit_max_drawdown,
            "return_count": g.return_count, "return_sum": g.return_sum,
            "return_square_sum": g.return_square_sum, "return_valid": g.return_valid,
            "risk_breach_observed": g.risk_breach,
            "event_audit": "unknown", "intrabar_tick_audit": "not_observable"})
'''

INIT_APPEND = '''
    g.open_entries = {}
    g.order_observations = {}
    g.reserved_open_notional = 0.0
    g.status_changes = 0
    g.stop_adding = False
    g.risk_action = "observed_no_action"
    g.risk_breach = False
    g.risk_reduction_sent = False
    g.audit_seq = 0
    g.audit_peak = INITIAL_MARGIN
    g.audit_max_drawdown = 0.0
    g.previous_equity = None
    g.return_count = 0
    g.return_sum = 0.0
    g.return_square_sum = 0.0
    g.return_valid = True
    _emit(context, "GRID_INIT_V1", {
        "params": FROZEN_PARAMETERS, "training_summary": TRAINING_SUMMARY,
        "start_utc": START_UTC, "end_utc": END_UTC,
        "generator_path": TEMPLATE_PATH, "generator_sha256": TEMPLATE_SHA256,
        "evidence_ready": EVIDENCE_READY})
    if not EVIDENCE_READY:
        raise ValueError("G-01/G-02/G-03 unresolved; offline source only")
'''

ENTRY_GUARD = '''
    target_quantity = quantity if quantity > 1e-12 else (
        INITIAL_MARGIN * float(CELL_BUDGET_PCTS[index]) * LEVERAGE / entry_price)
    if not _capacity_allows(context, side, target_quantity, entry_price):
        return
    g.open_entries[ref] = {
        "side": side, "limit_price": entry_price, "target_quantity": target_quantity,
        "filled_quantity": 0.0, "remaining": target_quantity, "status": "queued"}
'''


def _load_calculations() -> Any:
    spec = importlib.util.spec_from_file_location("grid_research_offline", LAB / "scripts/grid_research.py")
    if spec is None or spec.loader is None:
        raise ValueError("grid_research calculations missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate_strategy_source(*, cell: str | dict, template_sha256: str,
                             geometry: dict | None = None,
                             timeframe: str = "15m") -> str:
    """Generate sandbox source text, locked offline until evidence gates close.

    Defaults are explicitly synthetic examples, not inferred training history.
    Numeric geometry overrides permit deterministic offline generator verification.
    No evidence-ready switch or business submission path is exposed in this phase.
    """
    raw = TEMPLATE.read_bytes()
    actual_hash = hashlib.sha256(raw).hexdigest()
    if template_sha256 != TEMPLATE_SHA256 or actual_hash != TEMPLATE_SHA256:
        raise ValueError("native template identity mismatch")
    cell_id = cell["cell_id"] if isinstance(cell, dict) else cell
    if not isinstance(cell_id, str) or not cell_id or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in cell_id):
        raise ValueError("invalid cell identity")
    values = {"L": 90.0, "U": 100.0, "N": 8, **(geometry or {})}
    lower, upper, count = values["L"], values["U"], values["N"]
    if (type(lower) not in (int, float) or type(upper) not in (int, float)
            or not math.isfinite(lower) or not math.isfinite(upper) or not 0 < lower < upper
            or type(count) is not int or not 3 <= count <= 200):
        raise ValueError("invalid frozen geometry")
    gap = 100 * math.expm1(math.log(upper / lower) / count)
    if not 0.45 <= gap <= 1.5:
        raise ValueError("no-feasible-geometry: frozen gap outside SPEC")
    points = [lower * (upper / lower) ** (index / count) for index in range(count + 1)]
    points[0], points[-1] = lower, upper
    reference = (lower + upper) / 2
    roles = ["long_entry" if (low + high) / 2 < reference else "short_entry"
             for low, high in zip(points[:-1], points[1:])]
    weights = [1 / count for _ in roles]
    weights[-1] = 1 - sum(weights[:-1])
    arm_order = sorted(range(count), key=lambda index: abs(
        (points[index] if roles[index].startswith("long") else points[index + 1]) - reference))
    # Preserve native role partition, entry priority and complete cell lifecycle.
    # An unverified instrument is never inferred to be a verified Gate identity.
    constants = {
        "INSTRUMENT": cell.get("native_instrument") if isinstance(cell, dict) else None,
        "TIMEFRAME": timeframe, "CELL_LOWER": points[:-1], "CELL_UPPER": points[1:],
        "CELL_ROLES": roles, "CELL_BUDGET_PCTS": weights, "ARM_ORDER": arm_order,
        "MAX_OPEN_ENTRY_ORDERS": min(4, count),
    }
    extra = {
        "CELL_ID": cell_id, "TEMPLATE_PATH": TEMPLATE_PATH, "TEMPLATE_SHA256": actual_hash,
        "EVIDENCE_READY": False, "SOURCE_KIND": "offline_example_not_research_evidence",
        "INITIAL_MARGIN": 1000.0, "LEVERAGE": 10.0, "GROSS_LIMIT": 2.5,
        "FEE_RATE": 0.0005, "SLIPPAGE_RATE": 0.0005,
        "START_UTC": cell.get("start_utc") if isinstance(cell, dict) else "2026-07-31T00:00:00Z",
        "END_UTC": cell.get("end_utc") if isinstance(cell, dict) else "2026-10-31T00:00:00Z",
        "OHLCV_UNITS": {"price": "USDT", "volume": "unknown"},
        "FROZEN_PARAMETERS": {"L": lower, "U": upper, "N": count, "g_pct": gap,
                              "grid_lines": count + 1, "generator_sha256": actual_hash},
        "TRAINING_SUMMARY": {"status": "unknown", "reason": "G-02/G-03 unresolved; synthetic geometry"},
    }
    # JSON validates finite values; repr below emits Python literals, not JSON code.
    json.dumps(extra, allow_nan=False, default=str)
    for key in ("START_UTC", "END_UTC"):
        if isinstance(extra[key], dt.datetime):
            extra[key] = extra[key].isoformat().replace("+00:00", "Z")
    original = raw.decode("utf-8")
    lines = original.splitlines(keepends=True)
    replacements = []
    for node in ast.parse(original).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in constants:
                replacements.append((node.lineno - 1, node.end_lineno, f"{name} = {constants[name]!r}\n"))
        elif isinstance(node, ast.FunctionDef):
            text = "".join(lines[node.lineno - 1:node.end_lineno])
            if node.name == "initialize":
                header, body = text.split("\n", 1)
                text = header + "\n" + INIT_APPEND + body
            elif node.name == "_place_entry":
                marker = "    if quantity > 1e-12:\n"
                if text.count(marker) != 1:
                    raise ValueError("native entry sizing seam changed")
                text = text.replace(marker, ENTRY_GUARD + marker)
            elif node.name == "_equity_risk_reason":
                text = text.replace("float(context.portfolio.total_value or 0.0)",
                                    '_risk_snapshot(context, g.current_price)["equity"]')
            elif node.name == "handle_data":
                text = ""  # Replaced by the audited public-API callback below.
            else:
                continue
            replacements.append((node.lineno - 1, node.end_lineno, text + "\n"))
    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start:end] = [replacement]
    source = ("\"\"\"OFFLINE ONLY: native neutral grid, frozen geometry and audit extension.\"\"\"\n"
              "import json\nimport datetime\n" +
              "\n".join(f"{name} = {value!r}" for name, value in extra.items()) + "\n" +
              "".join(lines) + "\n" + AUDIT_SOURCE)
    ast.parse(source)  # Static syntax only, not sandbox compile or execution.
    return source


_FREQUENCY_SECONDS = {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def describe_plan(*, contracts: list[str] | None = None, windows_spec: list[dict] | None = None,
                  anchor_utc: Any = None, now_utc: Any = None,
                  frequency_seconds: int = 3600) -> dict:
    """Return an in-memory offline plan, retaining all unresolved evidence gates."""
    calculations = _load_calculations()
    anchor = calculations.DEFAULT_ANCHOR if anchor_utc is None else anchor_utc
    calculations.validate_run_anchor(anchor, dt.datetime.now(dt.timezone.utc) if now_utc is None else now_utc)
    cells = calculations.build_cells(contracts, windows_spec, anchor,
                                   frequency_seconds=frequency_seconds)
    return {"mode": "offline_only", "submission_implemented": False,
            "runtime_loaded": "NOT_VERIFIED", "historical_evidence": "UNKNOWN",
            "full_research_status": "DEFERRED", "unresolved_gates": ["G-01", "G-02", "G-03"],
            "manifest": calculations.build_manifest(cells)}


def main(argv: list[str] | None = None) -> int:
    """Describe the offline plan or write a locked example; reject all execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", nargs="+")
    parser.add_argument("--anchor",
                        help="research task date anchor (UTC midnight, required "
                             "for describe/write-example)")
    parser.add_argument("--frequency", default="1h",
                        help="bar frequency for the batch (1m/15m/1h/4h/1d)")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--describe", action="store_true")
    action.add_argument("--write-example", type=Path, help="static source; only own strategy.py may be refreshed")
    action.add_argument("--execute", action="store_true", help="unsupported: fail closed, zero requests")
    args = parser.parse_args(argv)
    if args.execute:
        # Fail closed before any anchor validation: business execution stays
        # disabled and the exit code keeps its frozen meaning (D5-3).
        parser.exit(3, "insufficient-evidence: G-01/G-02/G-03 unresolved; business execution disabled\n")
    if not args.anchor:
        parser.error("--anchor is required (D5-3): pass the research task date")
    frequency_seconds = _FREQUENCY_SECONDS.get(args.frequency, 3600)
    plan = describe_plan(contracts=args.contracts, anchor_utc=args.anchor,
                          frequency_seconds=frequency_seconds)
    if args.write_example:
        source = generate_strategy_source(cell=plan["manifest"]["items"][0],
                                          template_sha256=TEMPLATE_SHA256,
                                          timeframe=args.frequency)
        # Explicit caller-selected source output, never a business report/receipt.
        own_example = Path(__file__).resolve().with_name("strategy.py")
        mode = "w" if args.write_example.resolve() == own_example else "x"
        with args.write_example.open(mode, encoding="utf-8") as output:
            output.write(source)
        print(json.dumps({"mode": "offline_example", "path": str(args.write_example),
                          "strategy_sha256": hashlib.sha256(source.encode()).hexdigest(),
                          "evidence_ready": False}, sort_keys=True))
    else:
        print(_load_calculations().canonical_json(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
