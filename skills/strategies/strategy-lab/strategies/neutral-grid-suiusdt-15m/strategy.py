"""
neutral-grid-SUIUSDT-15m
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:SUI/USDT@swap'
TIMEFRAME = '15m'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.6353, 0.644760727465, 0.654362341698, 0.66410694075, 0.673996653915, 0.684033642195, 0.694220098776, 0.7045582495, 0.715050353358, 0.725698702983, 0.736505625146, 0.74747348127, 0.758604667943, 0.769901617442, 0.781366798265, 0.793002715671, 0.804811912227, 0.81679696836, 0.828960502929, 0.841305173789, 0.853833678375, 0.866548754294, 0.879453179918, 0.892549774996, 0.905841401267, 0.919330963085, 0.933021408058, 0.946915727687, 0.961016958022, 0.975328180324, 0.989852521741, 1.00459315599, 1.019553304049, 1.034736234861, 1.050145266052, 1.065783764652, 1.08165514783, 1.097762883647, 1.114110491805, 1.130701544423, 1.147539666815, 1.164628538281, 1.181971892914, 1.199573520412, 1.21743726691, 1.235567035818, 1.253966788675, 1.272640546013, 1.291592388239, 1.310826456523, 1.330346953703, 1.350158145206, 1.37026435998, 1.390669991436, 1.411379498412, 1.432397406147, 1.453728307265, 1.475376862786, 1.497347803139, 1.519645929197, 1.542276113329, 1.565243300458, 1.588552509149, 1.6122088327, 1.636217440259, 1.66058357795, 1.685312570021, 1.710409820009, 1.735880811918, 1.761731111418, 1.787966367063, 1.814592311521, 1.841614762833, 1.869039625679, 1.896872892669, 1.925120645656, 1.953789057059, 1.98288439122, 2.012413005762, 2.04238135299, 2.07279598129, 2.103663536569, 2.1349907637, 2.166784508001, 2.199051716728, 2.231799440595, 2.265034835311, 2.298765163147, 2.332997794523, 2.367740209618]
CELL_UPPER = [0.644760727465, 0.654362341698, 0.66410694075, 0.673996653915, 0.684033642195, 0.694220098776, 0.7045582495, 0.715050353358, 0.725698702983, 0.736505625146, 0.74747348127, 0.758604667943, 0.769901617442, 0.781366798265, 0.793002715671, 0.804811912227, 0.81679696836, 0.828960502929, 0.841305173789, 0.853833678375, 0.866548754294, 0.879453179918, 0.892549774996, 0.905841401267, 0.919330963085, 0.933021408058, 0.946915727687, 0.961016958022, 0.975328180324, 0.989852521741, 1.00459315599, 1.019553304049, 1.034736234861, 1.050145266052, 1.065783764652, 1.08165514783, 1.097762883647, 1.114110491805, 1.130701544423, 1.147539666815, 1.164628538281, 1.181971892914, 1.199573520412, 1.21743726691, 1.235567035818, 1.253966788675, 1.272640546013, 1.291592388239, 1.310826456523, 1.330346953703, 1.350158145206, 1.37026435998, 1.390669991436, 1.411379498412, 1.432397406147, 1.453728307265, 1.475376862786, 1.497347803139, 1.519645929197, 1.542276113329, 1.565243300458, 1.588552509149, 1.6122088327, 1.636217440259, 1.66058357795, 1.685312570021, 1.710409820009, 1.735880811918, 1.761731111418, 1.787966367063, 1.814592311521, 1.841614762833, 1.869039625679, 1.896872892669, 1.925120645656, 1.953789057059, 1.98288439122, 2.012413005762, 2.04238135299, 2.07279598129, 2.103663536569, 2.1349907637, 2.166784508001, 2.199051716728, 2.231799440595, 2.265034835311, 2.298765163147, 2.332997794523, 2.367740209618, 2.403]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111111, 0.011111111121]
ARM_ORDER = [58, 59, 57, 60, 56, 61, 55, 62, 54, 63, 53, 64, 52, 65, 51, 50, 66, 49, 67, 48, 68, 47, 46, 69, 45, 70, 44, 43, 71, 42, 72, 41, 40, 73, 39, 38, 74, 37, 75, 36, 35, 76, 34, 33, 77, 32, 31, 78, 30, 29, 79, 28, 27, 80, 26, 25, 24, 81, 23, 22, 82, 21, 20, 19, 83, 18, 17, 84, 16, 15, 14, 85, 13, 12, 11, 86, 10, 9, 8, 87, 7, 6, 5, 4, 88, 3, 2, 1, 0, 89]
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
    current_equity = float(context.portfolio.total_value or 0.0)
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


def handle_data(context, data):
    if g.halted:
        return
    price = data.current(INSTRUMENT, "close", frequency=TIMEFRAME)
    if price <= 0:
        return
    if g.anchor_price <= 0:
        g.anchor_price = price
    _reconcile_initial()
    _reconcile_cells()
    if _risk_exit(context):
        return
    if INITIAL_POSITION_PCT > 0 and not g.initial_ref:
        side = "short" if GRID_SIDE == "short" else "long"
        value = float(context.portfolio.starting_cash) * INITIAL_POSITION_PCT
        if side == "short":
            value = -value
        g.initial_ref = "grid-initial-" + side
        order_value(
            INSTRUMENT,
            value,
            position_side=side,
            reason="grid_initial_" + side,
            client_order_id=g.initial_ref,
        )
    _arm_orders(context, price)
