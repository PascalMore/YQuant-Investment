"""
neutral-grid-JUPUSDT-geometric
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:JUP/USDT@swap'
TIMEFRAME = '1D'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.1352, 0.137222065263, 0.139274372744, 0.14135737475, 0.14347153035, 0.145617305481, 0.147795173048, 0.150005613029, 0.15224911258, 0.154526166144, 0.156837275558, 0.159182950165, 0.161563706925, 0.163980070531, 0.166432573523, 0.168921756404, 0.171448167763, 0.174012364393, 0.176614911415, 0.179256382401, 0.181937359501, 0.184658433574, 0.187420204314, 0.190223280385, 0.193068279552, 0.195955828823, 0.198886564582, 0.201861132729, 0.204880188826, 0.207944398241, 0.211054436291, 0.214210988393, 0.217414750216, 0.220666427835, 0.223966737883, 0.22731640771, 0.230716175548, 0.234166790668, 0.237669013546, 0.241223616034, 0.244831381526, 0.248493105135, 0.252209593862, 0.255981666782, 0.259810155216, 0.263695902922, 0.267639766274, 0.271642614457, 0.275705329654, 0.279828807242, 0.28401395599, 0.288261698257, 0.2925729702, 0.296948721974, 0.301389917948, 0.30589753691, 0.31047257229, 0.315116032375, 0.319828940532, 0.324612335434, 0.329467271287, 0.334394818066, 0.339396061747, 0.344472104549, 0.349624065175, 0.35485307906, 0.360160298621, 0.365546893509, 0.371014050871, 0.376562975607, 0.382194890638, 0.387911037177, 0.393712674998, 0.399601082717, 0.405577558075, 0.41164341822]
CELL_UPPER = [0.137222065263, 0.139274372744, 0.14135737475, 0.14347153035, 0.145617305481, 0.147795173048, 0.150005613029, 0.15224911258, 0.154526166144, 0.156837275558, 0.159182950165, 0.161563706925, 0.163980070531, 0.166432573523, 0.168921756404, 0.171448167763, 0.174012364393, 0.176614911415, 0.179256382401, 0.181937359501, 0.184658433574, 0.187420204314, 0.190223280385, 0.193068279552, 0.195955828823, 0.198886564582, 0.201861132729, 0.204880188826, 0.207944398241, 0.211054436291, 0.214210988393, 0.217414750216, 0.220666427835, 0.223966737883, 0.22731640771, 0.230716175548, 0.234166790668, 0.237669013546, 0.241223616034, 0.244831381526, 0.248493105135, 0.252209593862, 0.255981666782, 0.259810155216, 0.263695902922, 0.267639766274, 0.271642614457, 0.275705329654, 0.279828807242, 0.28401395599, 0.288261698257, 0.2925729702, 0.296948721974, 0.301389917948, 0.30589753691, 0.31047257229, 0.315116032375, 0.319828940532, 0.324612335434, 0.329467271287, 0.334394818066, 0.339396061747, 0.344472104549, 0.349624065175, 0.35485307906, 0.360160298621, 0.365546893509, 0.371014050871, 0.376562975607, 0.382194890638, 0.387911037177, 0.393712674998, 0.399601082717, 0.405577558075, 0.41164341822, 0.4178]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894737, 0.013157894725]
ARM_ORDER = [48, 47, 49, 46, 50, 45, 51, 44, 52, 43, 42, 53, 41, 54, 40, 55, 39, 56, 38, 37, 57, 36, 58, 35, 34, 59, 33, 60, 32, 31, 61, 30, 62, 29, 28, 63, 27, 26, 64, 25, 24, 65, 23, 66, 22, 21, 67, 20, 19, 18, 68, 17, 16, 69, 15, 14, 70, 13, 12, 71, 11, 10, 9, 72, 8, 7, 6, 73, 5, 4, 3, 74, 2, 1, 0, 75]
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
