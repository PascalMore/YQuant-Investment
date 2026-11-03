"""
neutral-grid-JUPUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:JUP/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.1069, 0.10849434252578395, 0.11011246361180667, 0.11175471789950678, 0.11342146531956455, 0.1151130711707873, 0.11682990620017161, 0.11857234668415931, 0.12034077451110554, 0.12213557726497677, 0.12395714831029694, 0.1258058868783607, 0.12768219815473242, 0.12958649336805014, 0.131519189880154, 0.13348071127755892, 0.1354714874642914, 0.13749195475611115, 0.13954255597613763, 0.14162374055190324, 0.14373596461385363, 0.1458796910953171, 0.1480553898339653, 0.15026353767478673, 0.1525046185745964, 0.15477912370810382, 0.1570875515755632, 0.15943040811202905, 0.16180820679824143, 0.16422146877316454, 0.16667072294820437, 0.16915650612312935, 0.17167936310372, 0.17423984682117338, 0.17683851845328824, 0.1794759475474577, 0.18215271214549583, 0.184869398910327, 0.18762660325456323, 0.1904249294710005, 0.19326499086506063, 0.1961474098892086, 0.19907281827937456, 0.20204185719341078, 0.20505517735161305, 0.2081134391793385, 0.21121731295174984, 0.21436747894071892, 0.21756462756392086, 0.220809459536152, 0.22410268602290462, 0.22744502879623232, 0.23083722039293944, 0.23428000427513054, 0.23777413499315384, 0.24132037835097497, 0.24491951157401737, 0.2485723234795056, 0.25227961464934945, 0.25604219760560626, 0.25986089698856035, 0.2637365497374587, 0.2676700052739411, 0.2716621256882073, 0.2757137859279601, 0.2798258739901663, 0.2839992911156779, 0.2882349519867558, 0.29253378492753945, 0.2968967321075069, 0.30132474974796797, 0.30581880833163866, 0.3103798928153403, 0.31500900284587124, 0.31970715297909835, 0.3244753729023154, 0.32931470765991844, 0.33422621788244716, 0.3392109800190414, 0.34427008657336516, 0.3494046463430493, 0.3546157846627054, 0.35990464365056324, 0.36527238245878785, 0.37072017752752934, 0.3762492228427615, 0.38186073019796624, 0.38755592945972056, 0.3933360688372449, 0.3992024151559718, 0.4051562541351939, 0.41119889066985316, 0.41733164911653353, 0.4235558735837182, 0.42987292822637585, 0.4362841975449407, 0.442791086688752, 0.4493950217640183, 0.4560974501463755, 0.46289984079810614, 0.4698036845900896, 0.4768104946285553, 0.48392180658670675, 0.4911391790412941, 0.4984641938142048, 0.5058984563191496, 0.5134435959135191, 0.5211012662554869, 0.528873145666441, 0.5367609374988184, 0.5447663705094268, 0.5528911992383337, 0.5611372043934073, 0.569506193240591]
CELL_UPPER = [0.10849434252578395, 0.11011246361180667, 0.11175471789950678, 0.11342146531956455, 0.1151130711707873, 0.11682990620017161, 0.11857234668415931, 0.12034077451110554, 0.12213557726497677, 0.12395714831029694, 0.1258058868783607, 0.12768219815473242, 0.12958649336805014, 0.131519189880154, 0.13348071127755892, 0.1354714874642914, 0.13749195475611115, 0.13954255597613763, 0.14162374055190324, 0.14373596461385363, 0.1458796910953171, 0.1480553898339653, 0.15026353767478673, 0.1525046185745964, 0.15477912370810382, 0.1570875515755632, 0.15943040811202905, 0.16180820679824143, 0.16422146877316454, 0.16667072294820437, 0.16915650612312935, 0.17167936310372, 0.17423984682117338, 0.17683851845328824, 0.1794759475474577, 0.18215271214549583, 0.184869398910327, 0.18762660325456323, 0.1904249294710005, 0.19326499086506063, 0.1961474098892086, 0.19907281827937456, 0.20204185719341078, 0.20505517735161305, 0.2081134391793385, 0.21121731295174984, 0.21436747894071892, 0.21756462756392086, 0.220809459536152, 0.22410268602290462, 0.22744502879623232, 0.23083722039293944, 0.23428000427513054, 0.23777413499315384, 0.24132037835097497, 0.24491951157401737, 0.2485723234795056, 0.25227961464934945, 0.25604219760560626, 0.25986089698856035, 0.2637365497374587, 0.2676700052739411, 0.2716621256882073, 0.2757137859279601, 0.2798258739901663, 0.2839992911156779, 0.2882349519867558, 0.29253378492753945, 0.2968967321075069, 0.30132474974796797, 0.30581880833163866, 0.3103798928153403, 0.31500900284587124, 0.31970715297909835, 0.3244753729023154, 0.32931470765991844, 0.33422621788244716, 0.3392109800190414, 0.34427008657336516, 0.3494046463430493, 0.3546157846627054, 0.35990464365056324, 0.36527238245878785, 0.37072017752752934, 0.3762492228427615, 0.38186073019796624, 0.38755592945972056, 0.3933360688372449, 0.3992024151559718, 0.4051562541351939, 0.41119889066985316, 0.41733164911653353, 0.4235558735837182, 0.42987292822637585, 0.4362841975449407, 0.442791086688752, 0.4493950217640183, 0.4560974501463755, 0.46289984079810614, 0.4698036845900896, 0.4768104946285553, 0.48392180658670675, 0.4911391790412941, 0.4984641938142048, 0.5058984563191496, 0.5134435959135191, 0.5211012662554869, 0.528873145666441, 0.5367609374988184, 0.5447663705094268, 0.5528911992383337, 0.5611372043934073, 0.569506193240591, 0.578]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.008771929824561403, 0.00877192982456143]
ARM_ORDER = [78, 79, 77, 80, 76, 81, 75, 74, 82, 73, 83, 72, 84, 71, 85, 70, 86, 69, 68, 87, 67, 88, 66, 65, 89, 64, 90, 63, 62, 91, 61, 92, 60, 59, 93, 58, 94, 57, 56, 95, 55, 54, 96, 53, 52, 97, 51, 50, 98, 49, 48, 99, 47, 46, 45, 100, 44, 43, 101, 42, 41, 102, 40, 39, 38, 103, 37, 36, 35, 104, 34, 33, 32, 105, 31, 30, 29, 106, 28, 27, 26, 107, 25, 24, 23, 108, 22, 21, 20, 19, 109, 18, 17, 16, 15, 110, 14, 13, 12, 11, 10, 111, 9, 8, 7, 6, 112, 5, 4, 3, 2, 1, 0, 113]
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
