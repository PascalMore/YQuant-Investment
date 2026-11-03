"""
neutral-grid-JUPUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:JUP/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.1069, 0.10849622556040392, 0.11011628588263841, 0.11176053686619886, 0.11342933972485453, 0.11512306106600097, 0.11684207297119732, 0.11858675307790645, 0.1203574846624552, 0.12215465672423384, 0.12397866407115235, 0.12582990740637315, 0.12770879341633867, 0.12961573486011324, 0.13155115066005946, 0.13351546599386802, 0.13550911238796207, 0.13753252781229613, 0.13958615677657069, 0.14167045042788323, 0.14378586664983764, 0.14593287016313325, 0.14811193262765615, 0.15032353274609478, 0.15256815636910256, 0.15484629660203114, 0.15715845391325703, 0.1595051362441261, 0.16188685912053943, 0.16430414576620558, 0.16675752721758397, 0.16924754244054432, 0.1717747384487683, 0.17433967042391915, 0.17694290183760533, 0.17958500457516594, 0.1822665590613038, 0.18498815438759492, 0.187750388441902, 0.19055386803971985, 0.1933992090574826, 0.19628703656786103, 0.19921798497708051, 0.20219269816428892, 0.20521182962300616, 0.20827604260468527, 0.2113860102644175, 0.21454241580881292, 0.2177459526460892, 0.22099732453840154, 0.22429724575644716, 0.2276464412363783, 0.23104564673905834, 0.2344956090116958, 0.23799708595189178, 0.2415508467741374, 0.2451576721787968, 0.2488183545236137, 0.2525336979977787, 0.25630451879859606, 0.26013164531078825, 0.26401591828847776, 0.2679581910398864, 0.27195932961479247, 0.2760202129947873, 0.28014173328637215, 0.2843247959169387, 0.28857031983367626, 0.2928792377054485, 0.29725249612768473, 0.3016910558303309, 0.3061958918889054, 0.31076799393870663, 0.3154083663922184, 0.3201180286597629, 0.32489801537344704, 0.3297493766144536, 0.3346731781437263, 0.3396705016360989, 0.34474244491792083, 0.34989012220823074, 0.3551146643635313, 0.3604172191262191, 0.36579895137672397, 0.37126104338941324, 0.37680469509231695, 0.3824311243307319, 0.38814156713476117, 0.39393727799084854, 0.39981953011736804, 0.4057896157443281, 0.4118488463972522, 0.4179985531852986, 0.42424008709368244, 0.4305748192804638, 0.43700414137776755, 0.4435294657975015, 0.45015222604163874, 0.45687387701713356, 0.4636958953555394, 0.4706197797374, 0.47764705122148327, 0.48477925357893215, 0.49201795363240475, 0.49936474160027833, 0.5068212314459927, 0.5143890612326107, 0.5220698934826732, 0.5298654155434254, 0.5377773399574989, 0.5458074048391284, 0.5539573742559847, 0.562229038616711, 0.5706242150642444, 0.5791447478750114, 0.5877925088640831, 0.5965693977963824, 0.6054773428040285, 0.6145183008099145, 0.6236942579576112, 0.633007230047687, 0.6424592629805458, 0.6520524332058761, 0.6617888481788116, 0.6716706468229021]
CELL_UPPER = [0.10849622556040392, 0.11011628588263841, 0.11176053686619886, 0.11342933972485453, 0.11512306106600097, 0.11684207297119732, 0.11858675307790645, 0.1203574846624552, 0.12215465672423384, 0.12397866407115235, 0.12582990740637315, 0.12770879341633867, 0.12961573486011324, 0.13155115066005946, 0.13351546599386802, 0.13550911238796207, 0.13753252781229613, 0.13958615677657069, 0.14167045042788323, 0.14378586664983764, 0.14593287016313325, 0.14811193262765615, 0.15032353274609478, 0.15256815636910256, 0.15484629660203114, 0.15715845391325703, 0.1595051362441261, 0.16188685912053943, 0.16430414576620558, 0.16675752721758397, 0.16924754244054432, 0.1717747384487683, 0.17433967042391915, 0.17694290183760533, 0.17958500457516594, 0.1822665590613038, 0.18498815438759492, 0.187750388441902, 0.19055386803971985, 0.1933992090574826, 0.19628703656786103, 0.19921798497708051, 0.20219269816428892, 0.20521182962300616, 0.20827604260468527, 0.2113860102644175, 0.21454241580881292, 0.2177459526460892, 0.22099732453840154, 0.22429724575644716, 0.2276464412363783, 0.23104564673905834, 0.2344956090116958, 0.23799708595189178, 0.2415508467741374, 0.2451576721787968, 0.2488183545236137, 0.2525336979977787, 0.25630451879859606, 0.26013164531078825, 0.26401591828847776, 0.2679581910398864, 0.27195932961479247, 0.2760202129947873, 0.28014173328637215, 0.2843247959169387, 0.28857031983367626, 0.2928792377054485, 0.29725249612768473, 0.3016910558303309, 0.3061958918889054, 0.31076799393870663, 0.3154083663922184, 0.3201180286597629, 0.32489801537344704, 0.3297493766144536, 0.3346731781437263, 0.3396705016360989, 0.34474244491792083, 0.34989012220823074, 0.3551146643635313, 0.3604172191262191, 0.36579895137672397, 0.37126104338941324, 0.37680469509231695, 0.3824311243307319, 0.38814156713476117, 0.39393727799084854, 0.39981953011736804, 0.4057896157443281, 0.4118488463972522, 0.4179985531852986, 0.42424008709368244, 0.4305748192804638, 0.43700414137776755, 0.4435294657975015, 0.45015222604163874, 0.45687387701713356, 0.4636958953555394, 0.4706197797374, 0.47764705122148327, 0.48477925357893215, 0.49201795363240475, 0.49936474160027833, 0.5068212314459927, 0.5143890612326107, 0.5220698934826732, 0.5298654155434254, 0.5377773399574989, 0.5458074048391284, 0.5539573742559847, 0.562229038616711, 0.5706242150642444, 0.5791447478750114, 0.5877925088640831, 0.5965693977963824, 0.6054773428040285, 0.6145183008099145, 0.6236942579576112, 0.633007230047687, 0.6424592629805458, 0.6520524332058761, 0.6617888481788116, 0.6716706468229021, 0.6817]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008000000000000007]
ARM_ORDER = [88, 87, 89, 86, 85, 90, 84, 91, 83, 92, 82, 93, 81, 94, 80, 95, 79, 78, 96, 77, 97, 76, 98, 75, 74, 99, 73, 100, 72, 71, 101, 70, 69, 102, 68, 103, 67, 66, 104, 65, 64, 105, 63, 62, 106, 61, 60, 107, 59, 58, 108, 57, 56, 109, 55, 54, 110, 53, 52, 51, 111, 50, 49, 112, 48, 47, 46, 113, 45, 44, 43, 114, 42, 41, 40, 115, 39, 38, 37, 116, 36, 35, 34, 33, 117, 32, 31, 30, 118, 29, 28, 27, 26, 119, 25, 24, 23, 22, 120, 21, 20, 19, 18, 17, 121, 16, 15, 14, 13, 12, 122, 11, 10, 9, 8, 7, 123, 6, 5, 4, 3, 2, 1, 0, 124]
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
