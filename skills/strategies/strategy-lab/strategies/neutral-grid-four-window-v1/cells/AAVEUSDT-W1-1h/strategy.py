"""
neutral-grid-AAVEUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:AAVE/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [57.71, 58.57304240805545, 59.448991456175044, 60.338040160780906, 61.24038442482018, 62.15622308093243, 63.085757935262684, 64.02919381192969, 64.98673859815904, 65.95860329009155, 66.94500203927633, 67.9461521998595, 68.96227437647825, 69.99359247287151, 71.04033374121737, 72.10272883220821, 73.18101184587513, 74.27542038317193, 75.38619559833087, 76.51358225200134, 77.65782876518304, 78.81918727396592, 79.99791368508873, 81.1942677323282, 82.4085130337319, 83.6409171497066, 84.89175164197569, 86.16129213341799, 87.44981836880169, 88.7576142764264, 90.08496803068707, 91.4321721155736, 92.79952338912003, 94.18732314881754, 95.59587719800575, 97.02549591325683, 98.47649431276733, 99.94919212577285, 101.44391386300077, 102.96098888817653, 104.50075149059937, 106.06354095880332, 107.64970165531992, 109.25958309255883, 110.89354000982335, 112.55193245147767, 114.23512584628303, 115.94349108792039, 117.67740461671737, 119.43724850259723, 121.22341052926848, 123.03628427967351, 124.87626922271498, 126.74377080127938, 128.63920052157678, 130.56297604381675, 132.51552127424029, 134.49726645852797, 136.50864827660527, 138.55010993886546, 140.62210128383143, 142.7250788772782, 144.8595061128379, 147.02585331410882, 149.22459783829208, 151.4562241813776, 153.7212240849035, 156.02009664431202, 158.3533484189256, 160.721493543568, 163.1250538418544, 165.56455894117596, 168.04054638940383, 170.5535617733384, 173.10415883893003, 175.69289961329778, 178.3203545285725, 180.98710254759243, 183.6937312914783, 186.44083716911624, 189.22902550857745, 192.05891069050273, 194.93111628348205, 197.8462751814587, 200.80502974318813, 203.8080319337826, 206.8559434683723, 209.94943595791528, 213.08919105718752, 216.27590061498657, 219.51026682658105, 222.7930023884404, 226.12483065527843, 229.50648579944516, 232.93871297270272, 236.42226847042056, 239.95791989822587, 243.54644634114635, 247.18863853528265, 250.8852990420482, 254.63724242501402, 258.44529542939944, 262.3102971642459, 266.2330992873159, 270.2145661927567, 274.2555752015707, 278.3570167549339, 282.5197946104063, 286.744826041075, 291.0330420376775, 295.38538751374574, 299.8028215138195, 304.28631742477256, 308.83686319030016, 313.45546152861317, 318.1431301533886, 322.9009019980234, 327.72982544324344, 332.6309645481148, 337.6053992845108, 342.65422577508474, 347.7785565348023, 352.97952071608535, 358.2582643576217, 363.61595063689686, 369.05376012650066, 374.57289105426867, 380.1745595673126]
CELL_UPPER = [58.57304240805545, 59.448991456175044, 60.338040160780906, 61.24038442482018, 62.15622308093243, 63.085757935262684, 64.02919381192969, 64.98673859815904, 65.95860329009155, 66.94500203927633, 67.9461521998595, 68.96227437647825, 69.99359247287151, 71.04033374121737, 72.10272883220821, 73.18101184587513, 74.27542038317193, 75.38619559833087, 76.51358225200134, 77.65782876518304, 78.81918727396592, 79.99791368508873, 81.1942677323282, 82.4085130337319, 83.6409171497066, 84.89175164197569, 86.16129213341799, 87.44981836880169, 88.7576142764264, 90.08496803068707, 91.4321721155736, 92.79952338912003, 94.18732314881754, 95.59587719800575, 97.02549591325683, 98.47649431276733, 99.94919212577285, 101.44391386300077, 102.96098888817653, 104.50075149059937, 106.06354095880332, 107.64970165531992, 109.25958309255883, 110.89354000982335, 112.55193245147767, 114.23512584628303, 115.94349108792039, 117.67740461671737, 119.43724850259723, 121.22341052926848, 123.03628427967351, 124.87626922271498, 126.74377080127938, 128.63920052157678, 130.56297604381675, 132.51552127424029, 134.49726645852797, 136.50864827660527, 138.55010993886546, 140.62210128383143, 142.7250788772782, 144.8595061128379, 147.02585331410882, 149.22459783829208, 151.4562241813776, 153.7212240849035, 156.02009664431202, 158.3533484189256, 160.721493543568, 163.1250538418544, 165.56455894117596, 168.04054638940383, 170.5535617733384, 173.10415883893003, 175.69289961329778, 178.3203545285725, 180.98710254759243, 183.6937312914783, 186.44083716911624, 189.22902550857745, 192.05891069050273, 194.93111628348205, 197.8462751814587, 200.80502974318813, 203.8080319337826, 206.8559434683723, 209.94943595791528, 213.08919105718752, 216.27590061498657, 219.51026682658105, 222.7930023884404, 226.12483065527843, 229.50648579944516, 232.93871297270272, 236.42226847042056, 239.95791989822587, 243.54644634114635, 247.18863853528265, 250.8852990420482, 254.63724242501402, 258.44529542939944, 262.3102971642459, 266.2330992873159, 270.2145661927567, 274.2555752015707, 278.3570167549339, 282.5197946104063, 286.744826041075, 291.0330420376775, 295.38538751374574, 299.8028215138195, 304.28631742477256, 308.83686319030016, 313.45546152861317, 318.1431301533886, 322.9009019980234, 327.72982544324344, 332.6309645481148, 337.6053992845108, 342.65422577508474, 347.7785565348023, 352.97952071608535, 358.2582643576217, 363.61595063689686, 369.05376012650066, 374.57289105426867, 380.1745595673126, 385.86]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125, 0.0078125]
ARM_ORDER = [90, 91, 89, 92, 88, 93, 87, 94, 86, 85, 95, 84, 96, 83, 97, 82, 98, 81, 80, 99, 79, 100, 78, 101, 77, 76, 102, 75, 103, 74, 73, 104, 72, 71, 105, 70, 106, 69, 68, 107, 67, 66, 108, 65, 64, 109, 63, 62, 110, 61, 60, 111, 59, 58, 112, 57, 56, 55, 113, 54, 53, 114, 52, 51, 50, 115, 49, 48, 47, 116, 46, 45, 117, 44, 43, 42, 41, 118, 40, 39, 38, 119, 37, 36, 35, 120, 34, 33, 32, 31, 121, 30, 29, 28, 27, 122, 26, 25, 24, 23, 22, 123, 21, 20, 19, 18, 124, 17, 16, 15, 14, 13, 125, 12, 11, 10, 9, 8, 7, 126, 6, 5, 4, 3, 2, 1, 0, 127]
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
