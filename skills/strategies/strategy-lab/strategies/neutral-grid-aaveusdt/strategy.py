"""
neutral-grid-AAVEUSDT-geometric
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:AAVE/USDT@swap'
TIMEFRAME = '1D'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [57.83, 58.685726134981, 59.554114680789, 60.435353006537, 61.329631253891, 62.237142378095, 63.158082189603, 64.092649396328, 65.041045646521, 66.003475572272, 66.980146833673, 67.971270163613, 68.977059413256, 69.997731598179, 71.033506945195, 72.084608939876, 73.151264374767, 74.233703398326, 75.332159564578, 76.446869883513, 77.578074872218, 78.726018606779, 79.890948774942, 81.073116729553, 82.272777542796, 83.490190061227, 84.725616961624, 85.979324807663, 87.251584107438, 88.54266937182, 89.852859173696, 91.182436208067, 92.531687353052, 93.900903731782, 95.290380775213, 96.700418285876, 98.13132050256, 99.583396165957, 101.05695858528, 102.552325705859, 104.069820177753, 105.609769425356, 107.172505718052, 108.758366241904, 110.367693172408, 112.000833748324, 113.658140346597, 115.339970558389, 117.046687266236, 118.778658722343, 120.536258628044, 122.319866214433, 124.129866324188, 125.966649494606, 127.830612041875, 129.722156146576, 131.641689940468, 133.589627594542, 135.566389408394, 137.572401900903, 139.608097902265, 141.673916647379, 143.770303870625, 145.897711902032, 148.056599764881, 150.247433274742, 152.470685139985, 154.726835063775, 157.016369847572, 159.339783496171, 161.697577324286, 164.090260064724, 166.518347978147, 168.982364964465, 171.482842675878, 174.020320631586, 176.595346334202, 179.20847538788, 181.860271618203, 184.551307193829, 187.282162749954, 190.053427513587, 192.865699430691, 195.719585295195, 198.615700879923, 201.554671069453, 204.537129994953, 207.563721170999, 210.635097634425, 213.751922085231, 216.914867029564, 220.124614924829, 223.381858326936, 226.687300039732, 230.041653266644, 233.445641764561]
CELL_UPPER = [58.685726134981, 59.554114680789, 60.435353006537, 61.329631253891, 62.237142378095, 63.158082189603, 64.092649396328, 65.041045646521, 66.003475572272, 66.980146833673, 67.971270163613, 68.977059413256, 69.997731598179, 71.033506945195, 72.084608939876, 73.151264374767, 74.233703398326, 75.332159564578, 76.446869883513, 77.578074872218, 78.726018606779, 79.890948774942, 81.073116729553, 82.272777542796, 83.490190061227, 84.725616961624, 85.979324807663, 87.251584107438, 88.54266937182, 89.852859173696, 91.182436208067, 92.531687353052, 93.900903731782, 95.290380775213, 96.700418285876, 98.13132050256, 99.583396165957, 101.05695858528, 102.552325705859, 104.069820177753, 105.609769425356, 107.172505718052, 108.758366241904, 110.367693172408, 112.000833748324, 113.658140346597, 115.339970558389, 117.046687266236, 118.778658722343, 120.536258628044, 122.319866214433, 124.129866324188, 125.966649494606, 127.830612041875, 129.722156146576, 131.641689940468, 133.589627594542, 135.566389408394, 137.572401900903, 139.608097902265, 141.673916647379, 143.770303870625, 145.897711902032, 148.056599764881, 150.247433274742, 152.470685139985, 154.726835063775, 157.016369847572, 159.339783496171, 161.697577324286, 164.090260064724, 166.518347978147, 168.982364964465, 171.482842675878, 174.020320631586, 176.595346334202, 179.20847538788, 181.860271618203, 184.551307193829, 187.282162749954, 190.053427513587, 192.865699430691, 195.719585295195, 198.615700879923, 201.554671069453, 204.537129994953, 207.563721170999, 210.635097634425, 213.751922085231, 216.914867029564, 220.124614924829, 223.381858326936, 226.687300039732, 230.041653266644, 233.445641764561, 236.9]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666667, 0.010416666635]
ARM_ORDER = [63, 64, 62, 65, 61, 66, 60, 67, 59, 58, 68, 57, 69, 56, 70, 55, 71, 54, 53, 72, 52, 73, 51, 74, 50, 49, 75, 48, 76, 47, 46, 77, 45, 44, 78, 43, 79, 42, 41, 80, 40, 39, 81, 38, 37, 82, 36, 35, 83, 34, 33, 84, 32, 31, 85, 30, 29, 28, 86, 27, 26, 87, 25, 24, 23, 88, 22, 21, 89, 20, 19, 18, 90, 17, 16, 15, 91, 14, 13, 12, 92, 11, 10, 9, 8, 93, 7, 6, 5, 4, 94, 3, 2, 1, 95, 0]
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
