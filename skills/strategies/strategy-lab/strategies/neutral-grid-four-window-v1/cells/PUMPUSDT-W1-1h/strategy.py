"""
neutral-grid-PUMPUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:PUMP/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.00115, 0.001167133836176924, 0.0011845229491730985, 0.0012021711423547844, 0.0012200822757545517, 0.0012382602669155493, 0.001256709091748354, 0.0012754327854005868, 0.001294435443139484, 0.0013137212212476195, 0.001333294337931972, 0.0013531590742465343, 0.0013733197750286721, 0.0013937808498494303, 0.001414546773977999, 0.0014356220893605516, 0.0014570114056136623, 0.001478719401032527, 0.0015007508236142056, 0.00152311049209611, 0.0015458032970099612, 0.0015688342017514548, 0.0015922082436658593, 0.0016159305351497886, 0.001640006264769394, 0.0016644406983952096, 0.0016892391803539125, 0.0017144071345972392, 0.0017399500658883166, 0.001765873561005672, 0.0017921832899651787, 0.0018188850072602084, 0.0018459845531202607, 0.001873487854788343, 0.001901400927817387, 0.0019297298773859736, 0.001958480899633667, 0.0019876602830162394, 0.0020172744096810906, 0.0020473297568631573, 0.0020778328983016227, 0.0021087905056777303, 0.0021402093500740215, 0.002172096303455317, 0.002204458340171757, 0.002237302538484241, 0.0022706360821125936, 0.0023044662618067935, 0.0023388004769416167, 0.0023736462371350335, 0.002409011163890724, 0.002444902992265059, 0.0024813295725589204, 0.002518298872034731, 0.002555818976659058, 0.002593898092871188, 0.0026325445493780497, 0.002671766798975874, 0.0027115734203990026, 0.002751973120196236, 0.0027929747346351406, 0.002834587231634729, 0.0028768197127269296, 0.002919681415047285, 0.0029631817133553115, 0.0030073301220849527, 0.00305213629742559, 0.003097610039434054, 0.0031437612941781047, 0.0031906001559118464, 0.0032381368692835527, 0.00328638183157639, 0.0033353455949825194, 0.0033850388689110893, 0.0034354725223306056, 0.0034866575861462025, 0.003538605255612341, 0.00359132689278144, 0.0036448340289890043, 0.0036991383673757668, 0.0037542517854474104, 0.003810186337672438, 0.003866954258118728, 0.003924567963129393, 0.003983040054038493, 0.004042383319927207, 0.0041026107404210895, 0.004163735488528971, 0.004225770933524189, 0.004288730643868721, 0.004352628390180894, 0.00441747814824732, 0.004483294102079678, 0.004550090647017071, 0.00461788239287459, 0.004686684167138777, 0.004756511018210724, 0.004827378218697469, 0.004899301268752438, 0.004972295899465657, 0.00504637807630447, 0.005121564002605534, 0.005197870123118816, 0.005275313127604421, 0.005353909954482989, 0.005433677794540478, 0.005514634094688172, 0.005596796561778665, 0.005680183166478742, 0.005764812147199931, 0.005850702014087641, 0.005937871553069709, 0.006026339829965286, 0.0061161261946549375, 0.00620725028531286, 0.006299732032702178, 0.006393591664534214, 0.0064888497098927155, 0.006585527003724006, 0.00668364469139402, 0.006783224233313248, 0.0068842874096305805, 0.006986856324997077, 0.007090953413400736, 0.007196601443073264, 0.007303823521469988, 0.00741264310032393, 0.007523083980775196, 0.007635170318576801, 0.007748926629378025, 0.007864377794086518, 0.007981549064310273, 0.008100466067880684, 0.008221154814457905, 0.008343641701219689, 0.008467953518635036, 0.00859411745632382, 0.008722161109003729, 0.008852112482525825]
CELL_UPPER = [0.001167133836176924, 0.0011845229491730985, 0.0012021711423547844, 0.0012200822757545517, 0.0012382602669155493, 0.001256709091748354, 0.0012754327854005868, 0.001294435443139484, 0.0013137212212476195, 0.001333294337931972, 0.0013531590742465343, 0.0013733197750286721, 0.0013937808498494303, 0.001414546773977999, 0.0014356220893605516, 0.0014570114056136623, 0.001478719401032527, 0.0015007508236142056, 0.00152311049209611, 0.0015458032970099612, 0.0015688342017514548, 0.0015922082436658593, 0.0016159305351497886, 0.001640006264769394, 0.0016644406983952096, 0.0016892391803539125, 0.0017144071345972392, 0.0017399500658883166, 0.001765873561005672, 0.0017921832899651787, 0.0018188850072602084, 0.0018459845531202607, 0.001873487854788343, 0.001901400927817387, 0.0019297298773859736, 0.001958480899633667, 0.0019876602830162394, 0.0020172744096810906, 0.0020473297568631573, 0.0020778328983016227, 0.0021087905056777303, 0.0021402093500740215, 0.002172096303455317, 0.002204458340171757, 0.002237302538484241, 0.0022706360821125936, 0.0023044662618067935, 0.0023388004769416167, 0.0023736462371350335, 0.002409011163890724, 0.002444902992265059, 0.0024813295725589204, 0.002518298872034731, 0.002555818976659058, 0.002593898092871188, 0.0026325445493780497, 0.002671766798975874, 0.0027115734203990026, 0.002751973120196236, 0.0027929747346351406, 0.002834587231634729, 0.0028768197127269296, 0.002919681415047285, 0.0029631817133553115, 0.0030073301220849527, 0.00305213629742559, 0.003097610039434054, 0.0031437612941781047, 0.0031906001559118464, 0.0032381368692835527, 0.00328638183157639, 0.0033353455949825194, 0.0033850388689110893, 0.0034354725223306056, 0.0034866575861462025, 0.003538605255612341, 0.00359132689278144, 0.0036448340289890043, 0.0036991383673757668, 0.0037542517854474104, 0.003810186337672438, 0.003866954258118728, 0.003924567963129393, 0.003983040054038493, 0.004042383319927207, 0.0041026107404210895, 0.004163735488528971, 0.004225770933524189, 0.004288730643868721, 0.004352628390180894, 0.00441747814824732, 0.004483294102079678, 0.004550090647017071, 0.00461788239287459, 0.004686684167138777, 0.004756511018210724, 0.004827378218697469, 0.004899301268752438, 0.004972295899465657, 0.00504637807630447, 0.005121564002605534, 0.005197870123118816, 0.005275313127604421, 0.005353909954482989, 0.005433677794540478, 0.005514634094688172, 0.005596796561778665, 0.005680183166478742, 0.005764812147199931, 0.005850702014087641, 0.005937871553069709, 0.006026339829965286, 0.0061161261946549375, 0.00620725028531286, 0.006299732032702178, 0.006393591664534214, 0.0064888497098927155, 0.006585527003724006, 0.00668364469139402, 0.006783224233313248, 0.0068842874096305805, 0.006986856324997077, 0.007090953413400736, 0.007196601443073264, 0.007303823521469988, 0.00741264310032393, 0.007523083980775196, 0.007635170318576801, 0.007748926629378025, 0.007864377794086518, 0.007981549064310273, 0.008100466067880684, 0.008221154814457905, 0.008343641701219689, 0.008467953518635036, 0.00859411745632382, 0.008722161109003729, 0.008852112482525825, 0.008984]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316547, 0.007194244604316502]
ARM_ORDER = [100, 99, 101, 98, 102, 97, 103, 96, 104, 95, 105, 94, 93, 106, 92, 107, 91, 108, 90, 89, 109, 88, 110, 87, 111, 86, 85, 112, 84, 113, 83, 82, 114, 81, 80, 115, 79, 116, 78, 77, 117, 76, 75, 118, 74, 73, 119, 72, 71, 120, 70, 69, 121, 68, 67, 66, 122, 65, 64, 123, 63, 62, 61, 124, 60, 59, 125, 58, 57, 56, 126, 55, 54, 53, 127, 52, 51, 50, 128, 49, 48, 47, 46, 129, 45, 44, 43, 130, 42, 41, 40, 39, 131, 38, 37, 36, 35, 132, 34, 33, 32, 31, 30, 133, 29, 28, 27, 26, 134, 25, 24, 23, 22, 21, 20, 135, 19, 18, 17, 16, 15, 14, 136, 13, 12, 11, 10, 9, 8, 137, 7, 6, 5, 4, 3, 2, 1, 0, 138]
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
