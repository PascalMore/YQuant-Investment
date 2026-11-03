"""
neutral-grid-SUIUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:SUI/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.5479, 0.5560947984390827, 0.5644121643566417, 0.5728539309627178, 0.5814219588861994, 0.59011813658492, 0.5989443807618874, 0.6079026367877403, 0.6169948791295223, 0.6262231117858694, 0.6355893687287063, 0.645095714351549, 0.654744243924513, 0.6645370840561263, 0.6744763931620501, 0.6845643619408098, 0.6948032138566415, 0.7051952056295598, 0.7157426277327569, 0.7264478048974391, 0.737313096625215, 0.748340897708149, 0.7595336387565893, 0.7708937867348942, 0.7824238455051691, 0.7941263563791365, 0.8060038986782607, 0.8180590903022489, 0.8302945883060565, 0.8427130894855221, 0.8553173309717613, 0.8681100908344511, 0.8810941886941372, 0.8942724863437002, 0.9076478883791151, 0.9212233428396478, 0.9350018418576234, 0.9489864223179159, 0.9631801665272998, 0.9775862028938143, 0.9922077066162872, 1.0070479003841735, 1.0221100550878597, 1.0373974905395928, 1.0529135762051927, 1.0686617319467062, 1.0846454287761718, 1.100868189620656, 1.1173335900987345, 1.1340452593085824, 1.151006880627858, 1.1682221925255447, 1.185694989385939, 1.2034291223449605, 1.2214285001389724, 1.2396970899662945, 1.2582389183616058, 1.2770580720834213, 1.296158699014845, 1.315545009077795, 1.335221275160901, 1.3551918340612814, 1.375461087440407, 1.396033502794259, 1.4169136144379995, 1.4381060245053685, 1.4596154039630285, 1.4814464936400813, 1.5036041052729816, 1.526093122566081, 1.5489185022680327, 1.5720852752642953, 1.5955985476859793, 1.6194635020352757, 1.6436853983277195, 1.6682695752515357, 1.6932214513443269, 1.71854652618736, 1.7442503816177142, 1.7703386829585614, 1.7968171802678448, 1.823691709605636, 1.8509681943204455, 1.8786526463547741, 1.9067511675701905, 1.935269951092226, 1.9642152826753871, 1.993593542088584, 2.0234112045212775, 2.053674842010661, 2.0843911248901867, 2.1155668232597575, 2.1472088084779073, 2.1793240546762993, 2.211919640296881, 2.245002749652021, 2.278580674507988, 2.3126608156921127, 2.3472506847239822, 2.382357905471038, 2.417990215828932, 2.454155469427019, 2.490861637359355, 2.528116809941584, 2.5659291984941075, 2.604307137151921, 2.6432590847015183, 2.6827936264452723, 2.7229194760937023, 2.763645477686037, 2.804980607539513, 2.846933976227817, 2.8895148305891296, 2.932732555764194, 2.9765966772648746, 3.0211168630736513, 3.0663029257745134, 3.1121648247157276, 3.158712668204956, 3.2059567157372006, 3.2539073802560723, 3.3025752304488845, 3.351970993076071, 3.402105555335443, 3.4529899672618116, 3.5046354441624956, 3.5570533690892643, 3.6102552953472427, 3.66425294904135, 3.7190582316608207, 3.7746832227023823, 3.8311401823326667, 3.8884415540904445, 3.9465999676292736, 4.00562824150117, 4.065539385981913, 4.126346605938608, 4.18806330374014, 4.250703082211155, 4.3142797476302235, 4.378807312772852]
CELL_UPPER = [0.5560947984390827, 0.5644121643566417, 0.5728539309627178, 0.5814219588861994, 0.59011813658492, 0.5989443807618874, 0.6079026367877403, 0.6169948791295223, 0.6262231117858694, 0.6355893687287063, 0.645095714351549, 0.654744243924513, 0.6645370840561263, 0.6744763931620501, 0.6845643619408098, 0.6948032138566415, 0.7051952056295598, 0.7157426277327569, 0.7264478048974391, 0.737313096625215, 0.748340897708149, 0.7595336387565893, 0.7708937867348942, 0.7824238455051691, 0.7941263563791365, 0.8060038986782607, 0.8180590903022489, 0.8302945883060565, 0.8427130894855221, 0.8553173309717613, 0.8681100908344511, 0.8810941886941372, 0.8942724863437002, 0.9076478883791151, 0.9212233428396478, 0.9350018418576234, 0.9489864223179159, 0.9631801665272998, 0.9775862028938143, 0.9922077066162872, 1.0070479003841735, 1.0221100550878597, 1.0373974905395928, 1.0529135762051927, 1.0686617319467062, 1.0846454287761718, 1.100868189620656, 1.1173335900987345, 1.1340452593085824, 1.151006880627858, 1.1682221925255447, 1.185694989385939, 1.2034291223449605, 1.2214285001389724, 1.2396970899662945, 1.2582389183616058, 1.2770580720834213, 1.296158699014845, 1.315545009077795, 1.335221275160901, 1.3551918340612814, 1.375461087440407, 1.396033502794259, 1.4169136144379995, 1.4381060245053685, 1.4596154039630285, 1.4814464936400813, 1.5036041052729816, 1.526093122566081, 1.5489185022680327, 1.5720852752642953, 1.5955985476859793, 1.6194635020352757, 1.6436853983277195, 1.6682695752515357, 1.6932214513443269, 1.71854652618736, 1.7442503816177142, 1.7703386829585614, 1.7968171802678448, 1.823691709605636, 1.8509681943204455, 1.8786526463547741, 1.9067511675701905, 1.935269951092226, 1.9642152826753871, 1.993593542088584, 2.0234112045212775, 2.053674842010661, 2.0843911248901867, 2.1155668232597575, 2.1472088084779073, 2.1793240546762993, 2.211919640296881, 2.245002749652021, 2.278580674507988, 2.3126608156921127, 2.3472506847239822, 2.382357905471038, 2.417990215828932, 2.454155469427019, 2.490861637359355, 2.528116809941584, 2.5659291984941075, 2.604307137151921, 2.6432590847015183, 2.6827936264452723, 2.7229194760937023, 2.763645477686037, 2.804980607539513, 2.846933976227817, 2.8895148305891296, 2.932732555764194, 2.9765966772648746, 3.0211168630736513, 3.0663029257745134, 3.1121648247157276, 3.158712668204956, 3.2059567157372006, 3.2539073802560723, 3.3025752304488845, 3.351970993076071, 3.402105555335443, 3.4529899672618116, 3.5046354441624956, 3.5570533690892643, 3.6102552953472427, 3.66425294904135, 3.7190582316608207, 3.7746832227023823, 3.8311401823326667, 3.8884415540904445, 3.9465999676292736, 4.00562824150117, 4.065539385981913, 4.126346605938608, 4.18806330374014, 4.250703082211155, 4.3142797476302235, 4.378807312772852, 4.4443]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.0070921985815602835, 0.007092198581560294]
ARM_ORDER = [102, 101, 103, 100, 104, 99, 105, 98, 97, 106, 96, 107, 95, 108, 94, 109, 93, 92, 110, 91, 111, 90, 112, 89, 88, 113, 87, 114, 86, 85, 115, 84, 116, 83, 82, 117, 81, 80, 118, 79, 78, 119, 77, 76, 120, 75, 74, 121, 73, 72, 122, 71, 70, 123, 69, 68, 124, 67, 66, 65, 125, 64, 63, 126, 62, 61, 60, 127, 59, 58, 57, 128, 56, 55, 54, 129, 53, 52, 51, 130, 50, 49, 48, 131, 47, 46, 45, 44, 132, 43, 42, 41, 40, 133, 39, 38, 37, 36, 134, 35, 34, 33, 32, 31, 135, 30, 29, 28, 27, 26, 136, 25, 24, 23, 22, 21, 137, 20, 19, 18, 17, 16, 15, 138, 14, 13, 12, 11, 10, 9, 8, 139, 7, 6, 5, 4, 3, 2, 1, 140, 0]
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
