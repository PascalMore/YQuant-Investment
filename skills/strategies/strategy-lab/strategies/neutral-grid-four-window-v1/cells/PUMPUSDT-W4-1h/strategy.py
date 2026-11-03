"""
neutral-grid-PUMPUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:PUMP/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.00147, 0.0014919738351446973, 0.0015142761392900525, 0.0015369118224521669, 0.0015598858680429836, 0.0015832033339674189, 0.0016068693537368986, 0.001630889137599539, 0.0016552679736872192, 0.0016800112291798044, 0.0017051243514867689, 0.0017306128694464828, 0.0017564823945434276, 0.0017827386221436052, 0.0018093873327484136, 0.0018364343932672693, 0.001863885758309247, 0.0018917474714940337, 0.0019200256667824748, 0.0019487265698270096, 0.0019778564993422954, 0.00200742186849632, 0.0020374291863223056, 0.0020678850591517215, 0.002098796192068717, 0.0021301693903862926, 0.002162011561144544, 0.002194329714631292, 0.002227130965925455, 0.0022604225364634798, 0.0022942117556291994, 0.0023285060623674464, 0.0023633130068217937, 0.0023986402519967746, 0.002434495575444946, 0.0024708868709791792, 0.002507822150410536, 0.0025453095453121287, 0.002583357308809349, 0.00262197381739685, 0.002661167572782694, 0.0027009472037600696, 0.0027413214681069778, 0.002782299254514327, 0.0028238895845428386, 0.0028661016146092145, 0.0029089446380019856, 0.002952428086927501, 0.0029965615345864936, 0.0030413546972816946, 0.0030868174365569464, 0.003132959761368293, 0.0031797918302875292, 0.0032273239537386816, 0.0032755665962679245, 0.0033245303788474274, 0.0033742260812136392, 0.003424664644240529, 0.003475857172348294, 0.003527814935948087, 0.003580549373923274, 0.0036340720961477915, 0.003688394886042143, 0.0037435297031676086, 0.0037994886858592307, 0.0038562841538981514, 0.0039139286112239114, 0.003972434748687278, 0.004031815446844231, 0.004092083778791714, 0.0041532530130457684, 0.004215336616462698, 0.004278348257203894, 0.0043423018077449835, 0.004407211347929957, 0.0044730911680709445, 0.004539955772094342, 0.004607819880733947, 0.004676698434771843, 0.004746606598327721, 0.00481755976219737, 0.004889573547241081, 0.0049626638078226785, 0.0050368466352999925, 0.00511213836156748, 0.005188555562651812, 0.005266115062361209, 0.005344833935989328, 0.0054247295140745075, 0.00550581938621522, 0.005588121404942549, 0.005671653689650551, 0.005756434630585377, 0.005842482892894024, 0.005929817420733593, 0.006018457441441999, 0.006108422469770995, 0.0061997323121825015, 0.006292407071209136, 0.006386467149879937, 0.006481933256212241, 0.006578826407770704, 0.00667716793629447, 0.006776979492393514, 0.006878283050315181, 0.006981100912781977, 0.0070854557159016835, 0.007191370434150854, 0.007298868385432815, 0.00740797323621128, 0.007518709006720694, 0.007631100076254458, 0.007745171188532215, 0.007860947457147363, 0.007978454371095994, 0.008097717800388479, 0.008218764001744953, 0.008341619624375917, 0.008466311715849257, 0.008592867728044967, 0.008721315523198879, 0.008851683380036746]
CELL_UPPER = [0.0014919738351446973, 0.0015142761392900525, 0.0015369118224521669, 0.0015598858680429836, 0.0015832033339674189, 0.0016068693537368986, 0.001630889137599539, 0.0016552679736872192, 0.0016800112291798044, 0.0017051243514867689, 0.0017306128694464828, 0.0017564823945434276, 0.0017827386221436052, 0.0018093873327484136, 0.0018364343932672693, 0.001863885758309247, 0.0018917474714940337, 0.0019200256667824748, 0.0019487265698270096, 0.0019778564993422954, 0.00200742186849632, 0.0020374291863223056, 0.0020678850591517215, 0.002098796192068717, 0.0021301693903862926, 0.002162011561144544, 0.002194329714631292, 0.002227130965925455, 0.0022604225364634798, 0.0022942117556291994, 0.0023285060623674464, 0.0023633130068217937, 0.0023986402519967746, 0.002434495575444946, 0.0024708868709791792, 0.002507822150410536, 0.0025453095453121287, 0.002583357308809349, 0.00262197381739685, 0.002661167572782694, 0.0027009472037600696, 0.0027413214681069778, 0.002782299254514327, 0.0028238895845428386, 0.0028661016146092145, 0.0029089446380019856, 0.002952428086927501, 0.0029965615345864936, 0.0030413546972816946, 0.0030868174365569464, 0.003132959761368293, 0.0031797918302875292, 0.0032273239537386816, 0.0032755665962679245, 0.0033245303788474274, 0.0033742260812136392, 0.003424664644240529, 0.003475857172348294, 0.003527814935948087, 0.003580549373923274, 0.0036340720961477915, 0.003688394886042143, 0.0037435297031676086, 0.0037994886858592307, 0.0038562841538981514, 0.0039139286112239114, 0.003972434748687278, 0.004031815446844231, 0.004092083778791714, 0.0041532530130457684, 0.004215336616462698, 0.004278348257203894, 0.0043423018077449835, 0.004407211347929957, 0.0044730911680709445, 0.004539955772094342, 0.004607819880733947, 0.004676698434771843, 0.004746606598327721, 0.00481755976219737, 0.004889573547241081, 0.0049626638078226785, 0.0050368466352999925, 0.00511213836156748, 0.005188555562651812, 0.005266115062361209, 0.005344833935989328, 0.0054247295140745075, 0.00550581938621522, 0.005588121404942549, 0.005671653689650551, 0.005756434630585377, 0.005842482892894024, 0.005929817420733593, 0.006018457441441999, 0.006108422469770995, 0.0061997323121825015, 0.006292407071209136, 0.006386467149879937, 0.006481933256212241, 0.006578826407770704, 0.00667716793629447, 0.006776979492393514, 0.006878283050315181, 0.006981100912781977, 0.0070854557159016835, 0.007191370434150854, 0.007298868385432815, 0.00740797323621128, 0.007518709006720694, 0.007631100076254458, 0.007745171188532215, 0.007860947457147363, 0.007978454371095994, 0.008097717800388479, 0.008218764001744953, 0.008341619624375917, 0.008466311715849257, 0.008592867728044967, 0.008721315523198879, 0.008851683380036746, 0.008984]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.00819672131147541, 0.008196721311475308]
ARM_ORDER = [85, 84, 86, 83, 87, 82, 88, 81, 89, 80, 90, 79, 91, 78, 92, 77, 76, 93, 75, 94, 74, 95, 73, 72, 96, 71, 97, 70, 69, 98, 68, 67, 99, 66, 100, 65, 64, 101, 63, 62, 102, 61, 60, 103, 59, 58, 104, 57, 56, 105, 55, 54, 106, 53, 52, 107, 51, 50, 108, 49, 48, 47, 109, 46, 45, 44, 110, 43, 42, 111, 41, 40, 39, 112, 38, 37, 36, 113, 35, 34, 33, 32, 114, 31, 30, 29, 115, 28, 27, 26, 25, 116, 24, 23, 22, 21, 117, 20, 19, 18, 17, 16, 118, 15, 14, 13, 12, 119, 11, 10, 9, 8, 7, 6, 120, 5, 4, 3, 2, 1, 121, 0]
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
