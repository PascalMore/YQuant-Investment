"""OFFLINE ONLY: native neutral grid, frozen geometry and audit extension."""
import json
import datetime
CELL_ID = 'PUMPUSDT-W1'
TEMPLATE_PATH = 'neutral-grid-pumpusdt/strategy.py'
TEMPLATE_SHA256 = '25320a59133818ecbb2d363cc418b0bae717bdcf669fc9f46f67be294056ac85'
EVIDENCE_READY = False
SOURCE_KIND = 'offline_example_not_research_evidence'
INITIAL_MARGIN = 1000.0
LEVERAGE = 10.0
GROSS_LIMIT = 2.5
FEE_RATE = 0.0005
SLIPPAGE_RATE = 0.0005
START_UTC = '2026-07-31T00:00:00Z'
END_UTC = '2026-10-31T00:00:00Z'
OHLCV_UNITS = {'price': 'USDT', 'volume': 'unknown'}
FROZEN_PARAMETERS = {'L': 90.0, 'U': 100.0, 'N': 8, 'g_pct': 1.3257171738912976, 'grid_lines': 9, 'generator_sha256': '25320a59133818ecbb2d363cc418b0bae717bdcf669fc9f46f67be294056ac85'}
TRAINING_SUMMARY = {'status': 'unknown', 'reason': 'G-02/G-03 unresolved; synthetic geometry'}
"""
neutral-grid-PUMPUSDT-geometric
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = None
TIMEFRAME = '15m'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [90.0, 91.19314545650217, 92.40210864723068, 93.62709927060472, 94.86832980505139, 96.12601554586078, 97.40037464252967, 98.69162813660016]
CELL_UPPER = [91.19314545650217, 92.40210864723068, 93.62709927060472, 94.86832980505139, 96.12601554586078, 97.40037464252967, 98.69162813660016, 100.0]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.125, 0.125, 0.125, 0.125, 0.125, 0.125, 0.125, 0.125]
ARM_ORDER = [4, 3, 5, 2, 6, 1, 0, 7]
INITIAL_POSITION_PCT = 0.0
MAX_OPEN_ENTRY_ORDERS = 4
EQUITY_TAKE_PROFIT = 0.0
EQUITY_STOP_LOSS = 0.0
EQUITY_TRAILING_ENABLED = False
EQUITY_TRAILING_ACTIVATION = 0.05
EQUITY_TRAILING_CALLBACK = 0.03
PERSIST_RUNTIME_STATE = True
GRID_TEMPLATE_VERSION = 7


def initialize(context):

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
    context.set_universe([INSTRUMENT])
    context.subscribe(frequency=TIMEFRAME)
    context.set_metadata(
        direction_mode='neutral',
        strategy_family="grid",
        executor_type="grid",
    )
    context.set_warmup(2)
    context.allow_leverage(max_leverage=100)
    g.anchor_price = 0.0
    g.initial_ref = ""
    g.initial_allocated = False
    g.cell_states = ["disabled" if role.endswith("_seed") else "entry_ready" for role in CELL_ROLES]
    g.cell_refs = ["" for _ in CELL_ROLES]
    g.cell_quantities = [0.0 for _ in CELL_ROLES]
    g.cell_cycles = [1 for _ in CELL_ROLES]
    g.halted = False
    g.equity_peak_return = 0.0
    g.equity_trailing_armed = False
    g.equity_exit_pending = False
    g.equity_stop_reason = ""



def _price(raw):
    if not DYNAMIC_ANCHOR:
        return float(raw or 0.0)
    return float(raw or 0.0) * float(g.anchor_price or 0.0)


def _status(ref):
    return get_order_status(ref) if ref else {"status": "unknown"}


def _status_name(ref):
    return str(_status(ref).get("status") or "unknown").strip().lower()


def _cancel_working_orders():
    if g.initial_ref and _status_name(g.initial_ref) in ("queued", "deferred", "submitted", "open", "partial"):
        cancel_order(g.initial_ref)
    for ref in g.cell_refs:
        if ref and _status_name(ref) in ("queued", "deferred", "submitted", "open", "partial"):
            cancel_order(ref)


def _close_all(reason):
    _cancel_working_orders()
    if GRID_SIDE in ("long", "neutral"):
        position = get_position(INSTRUMENT, position_side="long")
        if abs(float(position.amount or 0.0)) > 1e-12:
            order_target_value(
                INSTRUMENT,
                0.0,
                position_side="long",
                reason=reason,
                client_order_id="grid-risk-long",
            )
    if GRID_SIDE in ("short", "neutral"):
        position = get_position(INSTRUMENT, position_side="short")
        if abs(float(position.amount or 0.0)) > 1e-12:
            order_target_value(
                INSTRUMENT,
                0.0,
                position_side="short",
                reason=reason,
                client_order_id="grid-risk-short",
            )
    g.halted = True




def _equity_risk_reason(context):
    starting_equity = float(context.portfolio.starting_cash or 0.0)
    if starting_equity <= 0:
        return ""
    current_equity = _risk_snapshot(context, g.current_price)["equity"]
    total_return = (current_equity / starting_equity) - 1.0
    g.equity_peak_return = max(float(g.equity_peak_return or 0.0), total_return)
    deployment_managed = bool(
        context.params.get("_deployment_equity_risk_managed")
    )
    if not deployment_managed:
        if EQUITY_TAKE_PROFIT > 0 and total_return >= EQUITY_TAKE_PROFIT:
            return "equity_take_profit"
        if EQUITY_STOP_LOSS > 0 and total_return <= -EQUITY_STOP_LOSS:
            return "equity_stop_loss"
    if EQUITY_TRAILING_ENABLED:
        if total_return >= EQUITY_TRAILING_ACTIVATION:
            g.equity_trailing_armed = True
        drawdown_from_peak = float(g.equity_peak_return or 0.0) - total_return
        if g.equity_trailing_armed and drawdown_from_peak >= EQUITY_TRAILING_CALLBACK:
            return "equity_trailing_stop"
    return ""




def _risk_exit(context):
    if g.equity_exit_pending:
        return False
    reason = _equity_risk_reason(context)
    if not reason:
        return False
    full_reason = "grid_" + reason
    g.equity_exit_pending = True
    g.equity_stop_reason = full_reason
    _close_all(full_reason)
    return True


def _equity_risk_exit(context):
    return _risk_exit(context)


def _release_equity_risk_exit():
    g.equity_exit_pending = False
    g.equity_stop_reason = ""
    g.halted = False


def _reconcile_initial():
    if not g.initial_ref or g.initial_allocated:
        return
    status = _status(g.initial_ref)
    name = str(status.get("status") or "unknown").strip().lower()
    if name == "filled":
        filled = abs(float(status.get("filled_quantity") or 0.0))
        seed_indexes = [index for index, role in enumerate(CELL_ROLES) if role.endswith("_seed")]
        total_seed_pct = sum(float(CELL_BUDGET_PCTS[index] or 0.0) for index in seed_indexes)
        for index in seed_indexes:
            share = float(CELL_BUDGET_PCTS[index] or 0.0) / total_seed_pct if total_seed_pct > 0 else 0.0
            g.cell_quantities[index] = filled * share
            g.cell_states[index] = "exit_ready" if g.cell_quantities[index] > 1e-12 else "disabled"
        g.initial_allocated = True
    elif name in ("rejected", "cancelled"):
        g.halted = True


def _reconcile_cells():
    for index in range(len(CELL_ROLES)):
        ref = g.cell_refs[index]
        if not ref:
            continue
        status = _status(ref)
        name = str(status.get("status") or "unknown").strip().lower()
        if name == "filled":
            state = g.cell_states[index]
            if state == "entry_pending":
                g.cell_quantities[index] = abs(float(status.get("filled_quantity") or 0.0))
                g.cell_states[index] = "exit_ready"
            elif state == "exit_pending":
                g.cell_states[index] = "entry_ready"
                g.cell_cycles[index] += 1
            g.cell_refs[index] = ""
        elif name in ("rejected", "cancelled"):
            state = g.cell_states[index]
            g.cell_states[index] = "entry_ready" if state == "entry_pending" else "exit_ready"
            g.cell_refs[index] = ""


def _place_entry(context, index):
    role = CELL_ROLES[index]
    side = "long" if role.startswith("long") else "short"
    entry_price = _price(CELL_LOWER[index] if side == "long" else CELL_UPPER[index])
    cycle = int(g.cell_cycles[index] or 1)
    ref = "grid-%s-%s-entry-%s" % (index, side, cycle)
    quantity = abs(float(g.cell_quantities[index] or 0.0))

    target_quantity = quantity if quantity > 1e-12 else (
        INITIAL_MARGIN * float(CELL_BUDGET_PCTS[index]) * LEVERAGE / entry_price)
    if not _capacity_allows(context, side, target_quantity, entry_price):
        return
    g.open_entries[ref] = {
        "side": side, "limit_price": entry_price, "target_quantity": target_quantity,
        "filled_quantity": 0.0, "remaining": target_quantity, "status": "queued"}
    if quantity > 1e-12:
        signed_quantity = quantity if side == "long" else -quantity
        order(
            INSTRUMENT,
            signed_quantity,
            position_side=side,
            order_type="limit",
            limit_price=entry_price,
            reason=side + "_entry",
            client_order_id=ref,
        )
    else:
        quote_value = float(context.portfolio.starting_cash) * float(CELL_BUDGET_PCTS[index] or 0.0)
        signed_value = quote_value if side == "long" else -quote_value
        order_value(
            INSTRUMENT,
            signed_value,
            position_side=side,
            order_type="limit",
            limit_price=entry_price,
            reason=side + "_entry",
            client_order_id=ref,
        )
    g.cell_refs[index] = ref
    g.cell_states[index] = "entry_pending"



def _place_exit(index):
    role = CELL_ROLES[index]
    side = "long" if role.startswith("long") else "short"
    quantity = abs(float(g.cell_quantities[index] or 0.0))
    if quantity <= 1e-12:
        g.cell_states[index] = "entry_ready"
        return
    exit_price = _price(CELL_UPPER[index] if side == "long" else CELL_LOWER[index])
    cycle = int(g.cell_cycles[index] or 1)
    ref = "grid-%s-%s-exit-%s" % (index, side, cycle)
    signed_quantity = -quantity if side == "long" else quantity
    order(
        INSTRUMENT,
        signed_quantity,
        position_side=side,
        order_type="limit",
        limit_price=exit_price,
        reason=side + "_exit",
        client_order_id=ref,
    )
    g.cell_refs[index] = ref
    g.cell_states[index] = "exit_pending"


def _entry_price(index):
    return _price(CELL_LOWER[index] if CELL_ROLES[index].startswith("long") else CELL_UPPER[index])


def _arm_orders(context, price):
    for index in range(len(CELL_ROLES)):
        if g.cell_states[index] == "exit_ready":
            _place_exit(index)
    pinned = []
    candidates = []
    for index in ARM_ORDER:
        state = g.cell_states[index]
        if state not in ("entry_ready", "entry_pending"):
            continue
        if state == "entry_pending":
            status = _status(g.cell_refs[index])
            if abs(float(status.get("filled_quantity") or 0.0)) > 1e-12:
                pinned.append(index)
                continue
        entry_price = _entry_price(index)
        if (CELL_ROLES[index].startswith("long") and entry_price <= price) or (CELL_ROLES[index].startswith("short") and entry_price >= price):
            candidates.append(index)
    candidates.sort(key=lambda index: (abs(_entry_price(index) - price), index))
    selected = candidates[:max(0, MAX_OPEN_ENTRY_ORDERS - len(pinned))]
    for index in ARM_ORDER:
        if g.cell_states[index] == "entry_pending" and index not in selected and index not in pinned:
            if cancel_order(g.cell_refs[index]):
                g.cell_refs[index] = ""
                g.cell_states[index] = "entry_ready"
                g.cell_cycles[index] += 1
    active_entries = sum(1 for state in g.cell_states if state == "entry_pending")
    for index in selected:
        if active_entries >= MAX_OPEN_ENTRY_ORDERS:
            break
        if g.cell_states[index] == "entry_ready":
            _place_entry(context, index)
            active_entries += 1





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
