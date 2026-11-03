"""
neutral-grid-AAVEUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:AAVE/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [80.62, 81.82479011385566, 83.04758468341021, 84.2886527683291, 85.54826744912165, 86.82670588722858, 88.12424938600786, 89.44118345263168, 90.77779786090854, 92.13438671504409, 93.51124851435493, 94.90868621894923, 96.3270073163893, 97.76652388934994, 99.2275526842882, 100.7104151811391, 102.21543766405321, 103.74295129319088, 105.29329217758985, 106.86680144912143, 108.46382533755204, 110.08471524672655, 111.7298278318899, 113.39952507816447, 115.09417438019992, 116.81414862301366, 118.5598262640391, 120.33159141640029, 122.12983393343075, 123.9549494944557, 125.8073396918558, 127.68741211943242, 129.5955804620931, 131.53226458687746, 133.49789063534328, 135.49289111733341, 137.5177050061437, 139.5727778351132, 141.6585617956579, 143.77551583676953, 145.92410576600093, 148.10480435196106, 150.3180914283412, 152.56445399949618, 154.8443863476031, 157.15839014142148, 159.5069745466789, 161.8906563381061, 164.30996001314648, 166.76541790736448, 169.25757031157931, 171.78696559074848, 174.35416030462835, 176.95971933023762, 179.60421598615108, 182.28823215865057, 185.01235842976152, 187.77719420720257, 190.58334785627713, 193.43143683373623, 196.3220878236417, 199.25593687525947, 202.23362954301385, 205.25582102853323, 208.32317632481826, 211.43637036256507, 214.59608815867452, 217.80302496698096, 221.05788643123395, 224.36138874036536, 227.71425878607755, 231.11723432278598, 234.5710641299523, 238.07650817684353, 241.6343377897527, 245.2453358217193, 248.91029682478575, 252.63002722482761, 256.4053454989973, 260.23708235581864, 264.1260809179735, 268.07319690781986, 272.0792988356817, 276.1452681909534, 280.27199963605983, 284.46040120331463, 288.71139449472076, 293.02591488475696, 297.4049117261941, 301.84934855898786, 306.3602033222927, 310.9384685696445, 315.5851516873588, 320.30127511619247, 325.0878765763183, 329.94600929566184, 334.87674224164965, 339.88116035642173, 344.9603647955585, 350.11547317037525, 355.34761979383796, 360.6579559301534, 366.04765004808985, 371.5178880780828, 377.0698736731833, 382.7048284739059, 388.423992377034, 394.22862380844293]
CELL_UPPER = [81.82479011385566, 83.04758468341021, 84.2886527683291, 85.54826744912165, 86.82670588722858, 88.12424938600786, 89.44118345263168, 90.77779786090854, 92.13438671504409, 93.51124851435493, 94.90868621894923, 96.3270073163893, 97.76652388934994, 99.2275526842882, 100.7104151811391, 102.21543766405321, 103.74295129319088, 105.29329217758985, 106.86680144912143, 108.46382533755204, 110.08471524672655, 111.7298278318899, 113.39952507816447, 115.09417438019992, 116.81414862301366, 118.5598262640391, 120.33159141640029, 122.12983393343075, 123.9549494944557, 125.8073396918558, 127.68741211943242, 129.5955804620931, 131.53226458687746, 133.49789063534328, 135.49289111733341, 137.5177050061437, 139.5727778351132, 141.6585617956579, 143.77551583676953, 145.92410576600093, 148.10480435196106, 150.3180914283412, 152.56445399949618, 154.8443863476031, 157.15839014142148, 159.5069745466789, 161.8906563381061, 164.30996001314648, 166.76541790736448, 169.25757031157931, 171.78696559074848, 174.35416030462835, 176.95971933023762, 179.60421598615108, 182.28823215865057, 185.01235842976152, 187.77719420720257, 190.58334785627713, 193.43143683373623, 196.3220878236417, 199.25593687525947, 202.23362954301385, 205.25582102853323, 208.32317632481826, 211.43637036256507, 214.59608815867452, 217.80302496698096, 221.05788643123395, 224.36138874036536, 227.71425878607755, 231.11723432278598, 234.5710641299523, 238.07650817684353, 241.6343377897527, 245.2453358217193, 248.91029682478575, 252.63002722482761, 256.4053454989973, 260.23708235581864, 264.1260809179735, 268.07319690781986, 272.0792988356817, 276.1452681909534, 280.27199963605983, 284.46040120331463, 288.71139449472076, 293.02591488475696, 297.4049117261941, 301.84934855898786, 306.3602033222927, 310.9384685696445, 315.5851516873588, 320.30127511619247, 325.0878765763183, 329.94600929566184, 334.87674224164965, 339.88116035642173, 344.9603647955585, 350.11547317037525, 355.34761979383796, 360.6579559301534, 366.04765004808985, 371.5178880780828, 377.0698736731833, 382.7048284739059, 388.423992377034, 394.22862380844293, 400.12]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.009259259259259259, 0.0092592592592593]
ARM_ORDER = [73, 74, 72, 75, 71, 76, 70, 69, 77, 68, 78, 67, 79, 66, 80, 65, 81, 64, 63, 82, 62, 83, 61, 60, 84, 59, 85, 58, 57, 86, 56, 87, 55, 54, 88, 53, 89, 52, 51, 90, 50, 49, 91, 48, 47, 92, 46, 45, 93, 44, 43, 94, 42, 41, 40, 95, 39, 38, 96, 37, 36, 97, 35, 34, 33, 98, 32, 31, 30, 99, 29, 28, 27, 100, 26, 25, 24, 101, 23, 22, 21, 102, 20, 19, 18, 17, 103, 16, 15, 14, 104, 13, 12, 11, 10, 105, 9, 8, 7, 6, 5, 106, 4, 3, 2, 1, 0, 107]
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
