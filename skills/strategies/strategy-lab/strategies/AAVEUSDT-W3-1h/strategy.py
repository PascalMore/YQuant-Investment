"""
neutral-grid-AAVEUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:AAVE/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [80.62, 81.81967784718915, 83.0372076782165, 84.27285514217088, 85.52688984117164, 86.79958538919249, 88.0912194717603, 89.40207390654258, 90.73243470483636, 92.08259213397217, 93.45284078064644, 94.84347961519663, 96.25481205683252, 97.68714603983844, 99.14079408076037, 100.61607334659303, 102.11330572398158, 103.6328178894531, 105.17494138069303, 106.74001266888249, 108.3283732321118, 109.94036962988658, 111.57635357874247, 113.23668202898509, 114.92171724257197, 116.63182687215333, 118.36738404128904, 120.12876742585944, 121.91636133668729, 123.73055580338948, 125.57174665947639, 127.44033562871753, 129.33673041279246, 131.26134478024596, 133.21459865676692, 135.19691821681053, 137.20873597658417, 139.2504908884166, 141.32262843653183, 143.42560073424764, 145.55986662262117, 147.72589177056167, 149.92414877643373, 152.15511727117172, 154.41928402292925, 156.71714304328543, 159.04919569503193, 161.41595080156355, 163.81792475789712, 166.25564164334173, 168.7296333358465, 171.240439628049, 173.78860834505096, 176.37469546394686, 178.99926523513057, 181.66289030540742, 184.3661518429384, 187.1096396640434, 189.89395236189128, 192.71969743710528, 195.58749143031156, 198.49796005666036, 201.4517383423489, 204.44947076317575, 207.491811385157, 210.5794240072349, 213.71298230611023, 216.89316998322963, 220.12068091396034, 223.3962192989848, 226.7204998179478, 230.09424778539068, 233.51819930900496, 236.99310145024177, 240.5197123873108, 244.09880158060477, 247.73114994058582, 251.4175499981697, 255.15880607764595, 258.95573447217066, 262.8091636218713, 266.71993429460093, 270.68889976938357, 274.71692602258787, 278.8048919168721, 282.9536893929406, 287.16422366415304, 291.4374134140309, 295.7741909967017, 300.1755026403265, 304.64230865355484, 309.17558363505105, 313.77631668613947, 318.44551162661287, 323.1841872137533, 327.99337736461126, 332.87413138159303, 337.82751418140487, 342.8546065274035, 347.9565052654049, 353.1343235630018, 358.38919115244187, 363.72225457712085, 369.1346774417433, 374.6276406662059, 380.20234274325844]
CELL_UPPER = [81.81967784718915, 83.0372076782165, 84.27285514217088, 85.52688984117164, 86.79958538919249, 88.0912194717603, 89.40207390654258, 90.73243470483636, 92.08259213397217, 93.45284078064644, 94.84347961519663, 96.25481205683252, 97.68714603983844, 99.14079408076037, 100.61607334659303, 102.11330572398158, 103.6328178894531, 105.17494138069303, 106.74001266888249, 108.3283732321118, 109.94036962988658, 111.57635357874247, 113.23668202898509, 114.92171724257197, 116.63182687215333, 118.36738404128904, 120.12876742585944, 121.91636133668729, 123.73055580338948, 125.57174665947639, 127.44033562871753, 129.33673041279246, 131.26134478024596, 133.21459865676692, 135.19691821681053, 137.20873597658417, 139.2504908884166, 141.32262843653183, 143.42560073424764, 145.55986662262117, 147.72589177056167, 149.92414877643373, 152.15511727117172, 154.41928402292925, 156.71714304328543, 159.04919569503193, 161.41595080156355, 163.81792475789712, 166.25564164334173, 168.7296333358465, 171.240439628049, 173.78860834505096, 176.37469546394686, 178.99926523513057, 181.66289030540742, 184.3661518429384, 187.1096396640434, 189.89395236189128, 192.71969743710528, 195.58749143031156, 198.49796005666036, 201.4517383423489, 204.44947076317575, 207.491811385157, 210.5794240072349, 213.71298230611023, 216.89316998322963, 220.12068091396034, 223.3962192989848, 226.7204998179478, 230.09424778539068, 233.51819930900496, 236.99310145024177, 240.5197123873108, 244.09880158060477, 247.73114994058582, 251.4175499981697, 255.15880607764595, 258.95573447217066, 262.8091636218713, 266.71993429460093, 270.68889976938357, 274.71692602258787, 278.8048919168721, 282.9536893929406, 287.16422366415304, 291.4374134140309, 295.7741909967017, 300.1755026403265, 304.64230865355484, 309.17558363505105, 313.77631668613947, 318.44551162661287, 323.1841872137533, 327.99337736461126, 332.87413138159303, 337.82751418140487, 342.8546065274035, 347.9565052654049, 353.1343235630018, 358.38919115244187, 363.72225457712085, 369.1346774417433, 374.6276406662059, 380.20234274325844, 385.86]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150943, 0.009433962264150941]
ARM_ORDER = [71, 72, 70, 73, 69, 74, 68, 75, 67, 76, 66, 77, 65, 78, 64, 63, 79, 62, 80, 61, 81, 60, 59, 82, 58, 83, 57, 56, 84, 55, 85, 54, 53, 86, 52, 51, 87, 50, 88, 49, 48, 89, 47, 46, 90, 45, 44, 91, 43, 42, 92, 41, 40, 39, 93, 38, 37, 94, 36, 35, 95, 34, 33, 32, 96, 31, 30, 29, 97, 28, 27, 98, 26, 25, 24, 99, 23, 22, 21, 20, 100, 19, 18, 17, 101, 16, 15, 14, 13, 102, 12, 11, 10, 9, 103, 8, 7, 6, 5, 104, 4, 3, 2, 1, 0, 105]
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
