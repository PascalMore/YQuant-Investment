"""
neutral-grid-SUIUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:SUI/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.5479, 0.5560912464094626, 0.5644049540668545, 0.5728429537994388, 0.5814071038058188, 0.5900992900651459, 0.5989214267524475, 0.607875456660161, 0.616963351625972, 0.6261871129670493, 0.635548771920769, 0.6450503900920307, 0.6546940599072593, 0.6644819050751947, 0.6744160810545704, 0.6844987755287848, 0.6947322088876672, 0.705118634716448, 0.7156603402920388, 0.7263596470867312, 0.7372189112794261, 0.7482405242745083, 0.7594269132284741, 0.7707805415844368, 0.7823039096146194, 0.7939995549709604, 0.8058700532439494, 0.8179180185298189, 0.8301461040062145, 0.842557002516472, 0.8551534471626312, 0.8679382119073116, 0.8809141121845904, 0.8940840055200109, 0.9074507921598606, 0.9210174157098576, 0.9347868637833853, 0.948762168659418, 0.9629464079502837, 0.9773427052794088, 0.9919542309691958, 1.006784202739186, 1.0218358864146577, 1.0371125966458201, 1.0526176976377593, 1.0683546038912946, 1.0843267809549144, 1.1005377461879513, 1.116991069535168, 1.1336903743129225, 1.1506393380070874, 1.1678416930828983, 1.18530122780691, 1.203021787081239, 1.2210072732902815, 1.2392616471600872, 1.257788928630583, 1.276593197740835, 1.2956785955275456, 1.3150493249369861, 1.3347096517505586, 1.3546639055241971, 1.3749164805418164, 1.3954718367830081, 1.4163345009052108, 1.4375090672405597, 1.4590001988076415, 1.4808126283383738, 1.502951159320238, 1.5254206670540935, 1.5482260997278054, 1.5713724795059245, 1.5948649036356584, 1.618708545569375, 1.642908656103891, 1.667470564536791, 1.6923996798400334, 1.717701491851103, 1.7433815724819732, 1.7694455769461384, 1.7958992450039943, 1.8227484022268372, 1.8499989612797556, 1.8776569232237093, 1.905728378837067, 1.934219509956906, 1.9631365908403644, 1.992485989546343, 2.0222741693378663, 2.052507690105411, 2.083193209811507, 2.1143374859569444, 2.1459473770688935, 2.1780298442112755, 2.2105919525177145, 2.243640872747405, 2.277183882864243, 2.311228369639563, 2.345781830278836, 2.3808518740726923, 2.416446224072619, 2.4525727187917177, 2.4892393139308826, 2.52645408413079, 2.564225224750078, 2.6025610536701134, 2.6414700131267344, 2.680960671569383, 2.721041725548034, 2.761722001628328, 2.8030104583353395, 2.844916188126406, 2.8874484193934475, 2.930616518495226, 2.9744299918199855, 3.0188984878789253, 3.0640317994309783, 3.109839865639352, 3.1563327742603082, 3.203520763864668, 3.251414226092529, 3.300023707941691, 3.349359914090292, 3.3994337092541715, 3.4502561205794753, 3.50183834007103, 3.5541917270570216, 3.6073278106905264, 3.661258292488433, 3.715995048908328, 3.7715501339639053, 3.827935781879474, 3.8851644097841525, 3.9432486204463464, 4.002201205049101, 4.062035146006949, 4.122763619824871]
CELL_UPPER = [0.5560912464094626, 0.5644049540668545, 0.5728429537994388, 0.5814071038058188, 0.5900992900651459, 0.5989214267524475, 0.607875456660161, 0.616963351625972, 0.6261871129670493, 0.635548771920769, 0.6450503900920307, 0.6546940599072593, 0.6644819050751947, 0.6744160810545704, 0.6844987755287848, 0.6947322088876672, 0.705118634716448, 0.7156603402920388, 0.7263596470867312, 0.7372189112794261, 0.7482405242745083, 0.7594269132284741, 0.7707805415844368, 0.7823039096146194, 0.7939995549709604, 0.8058700532439494, 0.8179180185298189, 0.8301461040062145, 0.842557002516472, 0.8551534471626312, 0.8679382119073116, 0.8809141121845904, 0.8940840055200109, 0.9074507921598606, 0.9210174157098576, 0.9347868637833853, 0.948762168659418, 0.9629464079502837, 0.9773427052794088, 0.9919542309691958, 1.006784202739186, 1.0218358864146577, 1.0371125966458201, 1.0526176976377593, 1.0683546038912946, 1.0843267809549144, 1.1005377461879513, 1.116991069535168, 1.1336903743129225, 1.1506393380070874, 1.1678416930828983, 1.18530122780691, 1.203021787081239, 1.2210072732902815, 1.2392616471600872, 1.257788928630583, 1.276593197740835, 1.2956785955275456, 1.3150493249369861, 1.3347096517505586, 1.3546639055241971, 1.3749164805418164, 1.3954718367830081, 1.4163345009052108, 1.4375090672405597, 1.4590001988076415, 1.4808126283383738, 1.502951159320238, 1.5254206670540935, 1.5482260997278054, 1.5713724795059245, 1.5948649036356584, 1.618708545569375, 1.642908656103891, 1.667470564536791, 1.6923996798400334, 1.717701491851103, 1.7433815724819732, 1.7694455769461384, 1.7958992450039943, 1.8227484022268372, 1.8499989612797556, 1.8776569232237093, 1.905728378837067, 1.934219509956906, 1.9631365908403644, 1.992485989546343, 2.0222741693378663, 2.052507690105411, 2.083193209811507, 2.1143374859569444, 2.1459473770688935, 2.1780298442112755, 2.2105919525177145, 2.243640872747405, 2.277183882864243, 2.311228369639563, 2.345781830278836, 2.3808518740726923, 2.416446224072619, 2.4525727187917177, 2.4892393139308826, 2.52645408413079, 2.564225224750078, 2.6025610536701134, 2.6414700131267344, 2.680960671569383, 2.721041725548034, 2.761722001628328, 2.8030104583353395, 2.844916188126406, 2.8874484193934475, 2.930616518495226, 2.9744299918199855, 3.0188984878789253, 3.0640317994309783, 3.109839865639352, 3.1563327742603082, 3.203520763864668, 3.251414226092529, 3.300023707941691, 3.349359914090292, 3.3994337092541715, 3.4502561205794753, 3.50183834007103, 3.5541917270570216, 3.6073278106905264, 3.661258292488433, 3.715995048908328, 3.7715501339639053, 3.827935781879474, 3.8851644097841525, 3.9432486204463464, 4.002201205049101, 4.062035146006949, 4.122763619824871, 4.1844]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.0072992700729927005, 0.007299270072992692]
ARM_ORDER = [98, 99, 97, 100, 96, 95, 101, 94, 102, 93, 103, 92, 104, 91, 105, 90, 89, 106, 88, 107, 87, 108, 86, 85, 109, 84, 110, 83, 82, 111, 81, 112, 80, 79, 113, 78, 77, 114, 76, 115, 75, 74, 116, 73, 72, 117, 71, 70, 118, 69, 68, 119, 67, 66, 65, 120, 64, 63, 121, 62, 61, 60, 122, 59, 58, 123, 57, 56, 55, 124, 54, 53, 52, 125, 51, 50, 49, 126, 48, 47, 46, 127, 45, 44, 43, 42, 128, 41, 40, 39, 38, 129, 37, 36, 35, 34, 130, 33, 32, 31, 30, 131, 29, 28, 27, 26, 25, 132, 24, 23, 22, 21, 20, 133, 19, 18, 17, 16, 15, 14, 134, 13, 12, 11, 10, 9, 8, 135, 7, 6, 5, 4, 3, 2, 1, 136, 0]
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
