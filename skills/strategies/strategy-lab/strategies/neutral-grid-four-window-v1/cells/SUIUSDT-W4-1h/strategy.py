"""
neutral-grid-SUIUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:SUI/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.5479, 0.5560809698771134, 0.5643840939212832, 0.5728111960776839, 0.5813641275257306, 0.5900447670857275, 0.5988550216315875, 0.6077968265097151, 0.616872145964143, 0.6260829735680177, 0.6354313326615266, 0.644919276796365, 0.654548890186839, 0.6643222881677051, 0.674241617658844, 0.6843090576368751, 0.6945268196138108, 0.7048971481228598, 0.7154223212114822, 0.7261046509418083, 0.7369464838985281, 0.7479502017043658, 0.7591182215432493, 0.7704529966912931, 0.7819570170557085, 0.793632809721761, 0.8054829395078945, 0.8175100095291443, 0.829716661768963, 0.8421055776595834, 0.8546794786710494, 0.8674411269090395, 0.8803933257216187, 0.8935389203150484, 0.9068807983787932, 0.9204218907198581, 0.9341651719065982, 0.9481136609221417, 0.9622704218275691, 0.9766385644349946, 0.9912212449906982, 1.0060216668684563, 1.0210430812732276, 1.0362887879553435, 1.0517621359353637, 1.0674665242397543, 1.083405402647552, 1.099582272448175, 1.1160006872105521, 1.1326642535637321, 1.1495766319891527, 1.1667415376247372, 1.1841627410809972, 1.201844069269323, 1.2197894062426384, 1.2380026940486124, 1.2564879335956043, 1.2752491855315453, 1.294290571135938, 1.3136162732251788, 1.3332305370713937, 1.3531376713349978, 1.3733420490111778, 1.3938481083905052, 1.4146603540338967, 1.4357833577621275, 1.457221759660125, 1.478980269096251, 1.5010636657568122, 1.5234768006960089, 1.5462245974015665, 1.5693120528762772, 1.5927442387356892, 1.6165263023221874, 1.6406634678357104, 1.665161037481347, 1.6900243926340714, 1.7152589950208688, 1.7408703879205096, 1.7668641973812442, 1.79324613345667, 1.8200219914600633, 1.847197653237429, 1.874779088459568, 1.902772355933431, 1.931183604933058, 1.960019076550383, 1.9892851050662188, 2.018988119341701, 2.049134644230521, 2.0797313020122314, 2.110784813846968, 2.1423020012518776, 2.1742897875996077, 2.2067551996391543, 2.239705369039431, 2.273147533955876, 2.307089040620464, 2.3415373449554413, 2.3765000142111754, 2.411984728628443, 2.4479992831255535, 2.484551589010651, 2.521649675719595, 2.559301692579779, 2.597515910600294, 2.636300724288821, 2.6756646534956445, 2.715616345285214, 2.7561645758356335, 2.79731825236653, 2.8390864150956956, 2.8814782392249523, 2.924503036955664, 2.968170259534348, 3.0124894993288254, 3.057470491935377, 3.1031231183173555, 3.1494574069757393, 3.196483536152085, 3.2442118360643852, 3.292652791176298, 3.3418170425002747, 3.3917153899350594, 3.4423587946381087, 3.4937583814334188, 3.54592544125532, 3.5988714336287444, 3.6526079891865484, 3.707146912224399, 3.7625001832938305, 3.818679961834003, 3.8756985888427637, 3.9335685895875963, 3.9923026763570344, 4.051913751253176, 4.112414909025878, 4.173819439949282, 4.236140832741278, 4.29939277752658, 4.363589168844015, 4.428744108698755, 4.494871909660075, 4.5619870980054165, 4.630104416911351, 4.699238829692226, 4.76940552308714, 4.840619910596018, 4.912897635865485, 4.986254576125308, 5.060706845676138, 5.136270799429338, 5.212963036499657, 5.290800403851564]
CELL_UPPER = [0.5560809698771134, 0.5643840939212832, 0.5728111960776839, 0.5813641275257306, 0.5900447670857275, 0.5988550216315875, 0.6077968265097151, 0.616872145964143, 0.6260829735680177, 0.6354313326615266, 0.644919276796365, 0.654548890186839, 0.6643222881677051, 0.674241617658844, 0.6843090576368751, 0.6945268196138108, 0.7048971481228598, 0.7154223212114822, 0.7261046509418083, 0.7369464838985281, 0.7479502017043658, 0.7591182215432493, 0.7704529966912931, 0.7819570170557085, 0.793632809721761, 0.8054829395078945, 0.8175100095291443, 0.829716661768963, 0.8421055776595834, 0.8546794786710494, 0.8674411269090395, 0.8803933257216187, 0.8935389203150484, 0.9068807983787932, 0.9204218907198581, 0.9341651719065982, 0.9481136609221417, 0.9622704218275691, 0.9766385644349946, 0.9912212449906982, 1.0060216668684563, 1.0210430812732276, 1.0362887879553435, 1.0517621359353637, 1.0674665242397543, 1.083405402647552, 1.099582272448175, 1.1160006872105521, 1.1326642535637321, 1.1495766319891527, 1.1667415376247372, 1.1841627410809972, 1.201844069269323, 1.2197894062426384, 1.2380026940486124, 1.2564879335956043, 1.2752491855315453, 1.294290571135938, 1.3136162732251788, 1.3332305370713937, 1.3531376713349978, 1.3733420490111778, 1.3938481083905052, 1.4146603540338967, 1.4357833577621275, 1.457221759660125, 1.478980269096251, 1.5010636657568122, 1.5234768006960089, 1.5462245974015665, 1.5693120528762772, 1.5927442387356892, 1.6165263023221874, 1.6406634678357104, 1.665161037481347, 1.6900243926340714, 1.7152589950208688, 1.7408703879205096, 1.7668641973812442, 1.79324613345667, 1.8200219914600633, 1.847197653237429, 1.874779088459568, 1.902772355933431, 1.931183604933058, 1.960019076550383, 1.9892851050662188, 2.018988119341701, 2.049134644230521, 2.0797313020122314, 2.110784813846968, 2.1423020012518776, 2.1742897875996077, 2.2067551996391543, 2.239705369039431, 2.273147533955876, 2.307089040620464, 2.3415373449554413, 2.3765000142111754, 2.411984728628443, 2.4479992831255535, 2.484551589010651, 2.521649675719595, 2.559301692579779, 2.597515910600294, 2.636300724288821, 2.6756646534956445, 2.715616345285214, 2.7561645758356335, 2.79731825236653, 2.8390864150956956, 2.8814782392249523, 2.924503036955664, 2.968170259534348, 3.0124894993288254, 3.057470491935377, 3.1031231183173555, 3.1494574069757393, 3.196483536152085, 3.2442118360643852, 3.292652791176298, 3.3418170425002747, 3.3917153899350594, 3.4423587946381087, 3.4937583814334188, 3.54592544125532, 3.5988714336287444, 3.6526079891865484, 3.707146912224399, 3.7625001832938305, 3.818679961834003, 3.8756985888427637, 3.9335685895875963, 3.9923026763570344, 4.051913751253176, 4.112414909025878, 4.173819439949282, 4.236140832741278, 4.29939277752658, 4.363589168844015, 4.428744108698755, 4.494871909660075, 4.5619870980054165, 4.630104416911351, 4.699238829692226, 4.76940552308714, 4.840619910596018, 4.912897635865485, 4.986254576125308, 5.060706845676138, 5.136270799429338, 5.212963036499657, 5.290800403851564, 5.3698]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.006493506493506494, 0.00649350649350644]
ARM_ORDER = [113, 114, 112, 115, 111, 116, 110, 117, 109, 118, 108, 107, 119, 106, 120, 105, 121, 104, 122, 103, 102, 123, 101, 124, 100, 99, 125, 98, 126, 97, 96, 127, 95, 128, 94, 93, 129, 92, 91, 130, 90, 89, 131, 88, 87, 132, 86, 85, 133, 84, 83, 134, 82, 81, 135, 80, 79, 136, 78, 77, 76, 137, 75, 74, 138, 73, 72, 71, 139, 70, 69, 68, 140, 67, 66, 65, 141, 64, 63, 62, 142, 61, 60, 59, 58, 143, 57, 56, 55, 54, 144, 53, 52, 51, 50, 145, 49, 48, 47, 46, 146, 45, 44, 43, 42, 41, 147, 40, 39, 38, 37, 36, 148, 35, 34, 33, 32, 31, 149, 30, 29, 28, 27, 26, 25, 24, 150, 23, 22, 21, 20, 19, 18, 17, 151, 16, 15, 14, 13, 12, 11, 10, 152, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 153]
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
