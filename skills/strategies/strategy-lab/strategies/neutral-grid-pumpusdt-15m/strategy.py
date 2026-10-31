"""
neutral-grid-PUMPUSDT-15m
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:PUMP/USDT@swap'
TIMEFRAME = '15m'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.0011514, 0.001168575632, 0.001186007477, 0.001203699355, 0.001221655145, 0.001239878786, 0.001258374271, 0.001277145657, 0.001296197059, 0.001315532654, 0.001335156682, 0.001355073444, 0.001375287308, 0.001395802706, 0.001416624136, 0.001437756162, 0.001459203419, 0.001480970608, 0.001503062502, 0.001525483944, 0.001548239851, 0.001571335212, 0.00159477509, 0.001618564625, 0.001642709033, 0.001667213607, 0.00169208372, 0.001717324824, 0.001742942455, 0.001768942228, 0.001795329844, 0.001822111089, 0.001849291834, 0.001876878039, 0.001904875753, 0.001933291113, 0.001962130349, 0.001991399786, 0.00202110584, 0.002051255024, 0.002081853949, 0.002112909324, 0.002144427956, 0.002176416758, 0.002208882742, 0.002241833026, 0.002275274836, 0.002309215503, 0.002343662469, 0.002378623286, 0.00241410562, 0.00245011725, 0.002486666071, 0.002523760098, 0.002561407462, 0.002599616419, 0.002638395345, 0.002677752743, 0.002717697243, 0.002758237601, 0.002799382707, 0.002841141581, 0.00288352338, 0.002926537396, 0.002970193059, 0.003014499941, 0.003059467756, 0.003105106364, 0.003151425771, 0.003198436132, 0.003246147756, 0.003294571101, 0.003343716787, 0.003393595586, 0.003444218437, 0.003495596437, 0.003547740852, 0.003600663114, 0.003654374826, 0.003708887766, 0.003764213884, 0.003820365311, 0.003877354359, 0.003935193523, 0.003993895483, 0.004053473111, 0.004113939468, 0.004175307812, 0.004237591599, 0.004300804483, 0.004364960325, 0.004430073191, 0.004496157357, 0.004563227311, 0.00463129776, 0.004700383627, 0.00477050006, 0.004841662432, 0.004913886345, 0.004987187635, 0.005061582373, 0.00513708687, 0.00521371768, 0.005291491606, 0.005370425698, 0.005450537264, 0.005531843868, 0.005614363337, 0.005698113763, 0.005783113509, 0.00586938121, 0.005956935781, 0.006045796419, 0.006135982607, 0.006227514117, 0.006320411019, 0.00641469368, 0.006510382772, 0.006607499274, 0.00670606448]
CELL_UPPER = [0.001168575632, 0.001186007477, 0.001203699355, 0.001221655145, 0.001239878786, 0.001258374271, 0.001277145657, 0.001296197059, 0.001315532654, 0.001335156682, 0.001355073444, 0.001375287308, 0.001395802706, 0.001416624136, 0.001437756162, 0.001459203419, 0.001480970608, 0.001503062502, 0.001525483944, 0.001548239851, 0.001571335212, 0.00159477509, 0.001618564625, 0.001642709033, 0.001667213607, 0.00169208372, 0.001717324824, 0.001742942455, 0.001768942228, 0.001795329844, 0.001822111089, 0.001849291834, 0.001876878039, 0.001904875753, 0.001933291113, 0.001962130349, 0.001991399786, 0.00202110584, 0.002051255024, 0.002081853949, 0.002112909324, 0.002144427956, 0.002176416758, 0.002208882742, 0.002241833026, 0.002275274836, 0.002309215503, 0.002343662469, 0.002378623286, 0.00241410562, 0.00245011725, 0.002486666071, 0.002523760098, 0.002561407462, 0.002599616419, 0.002638395345, 0.002677752743, 0.002717697243, 0.002758237601, 0.002799382707, 0.002841141581, 0.00288352338, 0.002926537396, 0.002970193059, 0.003014499941, 0.003059467756, 0.003105106364, 0.003151425771, 0.003198436132, 0.003246147756, 0.003294571101, 0.003343716787, 0.003393595586, 0.003444218437, 0.003495596437, 0.003547740852, 0.003600663114, 0.003654374826, 0.003708887766, 0.003764213884, 0.003820365311, 0.003877354359, 0.003935193523, 0.003993895483, 0.004053473111, 0.004113939468, 0.004175307812, 0.004237591599, 0.004300804483, 0.004364960325, 0.004430073191, 0.004496157357, 0.004563227311, 0.00463129776, 0.004700383627, 0.00477050006, 0.004841662432, 0.004913886345, 0.004987187635, 0.005061582373, 0.00513708687, 0.00521371768, 0.005291491606, 0.005370425698, 0.005450537264, 0.005531843868, 0.005614363337, 0.005698113763, 0.005783113509, 0.00586938121, 0.005956935781, 0.006045796419, 0.006135982607, 0.006227514117, 0.006320411019, 0.00641469368, 0.006510382772, 0.006607499274, 0.00670606448, 0.0068061]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333333, 0.008333333373]
ARM_ORDER = [83, 84, 82, 85, 81, 86, 80, 87, 79, 88, 78, 77, 89, 76, 90, 75, 91, 74, 92, 73, 72, 93, 71, 94, 70, 69, 95, 68, 96, 67, 66, 97, 65, 98, 64, 63, 99, 62, 61, 100, 60, 59, 101, 58, 57, 102, 56, 55, 103, 54, 53, 104, 52, 51, 105, 50, 49, 48, 106, 47, 46, 107, 45, 44, 43, 108, 42, 41, 109, 40, 39, 38, 110, 37, 36, 35, 111, 34, 33, 32, 31, 112, 30, 29, 28, 113, 27, 26, 25, 24, 114, 23, 22, 21, 20, 115, 19, 18, 17, 16, 116, 15, 14, 13, 12, 11, 117, 10, 9, 8, 7, 6, 118, 5, 4, 3, 2, 1, 0, 119]
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
