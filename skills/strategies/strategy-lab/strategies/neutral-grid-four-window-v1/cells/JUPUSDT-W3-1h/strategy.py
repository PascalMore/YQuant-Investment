"""
neutral-grid-JUPUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:JUP/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.1069, 0.10850126882851431, 0.11012652326845213, 0.11177612260336729, 0.1134504314985681, 0.11514982008173137, 0.11687466402472398, 0.11862534462664985, 0.12040224889814118, 0.12220576964691213, 0.1240363055645941, 0.12589426131487158, 0.12778004762293835, 0.1296940813662937, 0.13163678566689843, 0.1336085899847116, 0.13560993021262804, 0.13764124877283837, 0.1397029947146319, 0.14179562381366503, 0.14391959867271614, 0.1460753888239501, 0.14826347083271438, 0.15048432840288994, 0.15273845248382034, 0.1550263413788424, 0.15734850085544258, 0.15970544425706354, 0.1620976926165852, 0.16452577477150598, 0.1669902274808491, 0.16949159554382012, 0.17203043192024178, 0.1746072978527931, 0.1772227629910793, 0.1798774055175601, 0.18257181227536456, 0.1853065788980204, 0.18808230994112637, 0.19089961901599722, 0.1937591289253104, 0.19666147180078455, 0.1996072892429206, 0.20259723246283576, 0.20563196242622217, 0.208712149999462, 0.21183847609793105, 0.21501163183652408, 0.2182323186824345, 0.2215012486102229, 0.22481914425920846, 0.2281867390932172, 0.23160477756272418, 0.23507401526942373, 0.23859521913326498, 0.2421691675619894, 0.24579665062320802, 0.2494784702190562, 0.2532154402634642, 0.2570083868620836, 0.2608581484949087, 0.26476557620163327, 0.268731533769784, 0.27275689792567165, 0.2768425585282034, 0.28098941876559685, 0.2851983953550422, 0.289470418745354, 0.2938064333226592, 0.2982073976191657, 0.3026742845250585, 0.30720808150356976, 0.31180979080927, 0.3164804297096297, 0.32122103070989955, 0.3260326417813589, 0.3309163265929834, 0.3358731647465832, 0.34090425201546204, 0.34601070058665334, 0.35119363930678255, 0.35645421393161375, 0.36179358737933376, 0.36721293998763027, 0.3727134697746209, 0.37829639270369014, 0.3839629429522948, 0.3897143731847936, 0.3955519548293662, 0.4014769783590778, 0.4074907535771556, 0.41359460990653724, 0.4197898966837578, 0.42607798345723724, 0.43246026029003715, 0.4389381380671525, 0.4455130488074055, 0.4521864459800124, 0.4589598048258913, 0.465834622683784, 0.4728124193212608, 0.4798947372706862, 0.4870831421702149, 0.4943792231098967, 0.501784592982965, 0.5093008888423883, 0.516929772262762, 0.5246729297076205, 0.5325320729022519, 0.5405089392120976, 0.5486052920268185, 0.5568229211501164, 0.565163643195392, 0.5736293019873319, 0.5822217689695091, 0.5909429436180904, 0.59979475386174, 0.6087791565078132, 0.6178981376749337, 0.6271537132320518, 0.636547929244077, 0.6460828624241882, 0.6557606205929175, 0.6655833431441115, 0.6755532015178722, 0.6856723996805814, 0.6959431746121167, 0.7063677968003645, 0.7169485707431406, 0.7276878354576296, 0.7385879649974554, 0.7496513689774952, 0.7608804931065571, 0.7722778197280364, 0.783845868368668, 0.7955871962955015, 0.8075043990812178, 0.8196001111779151, 0.8318770064994874, 0.8443377990127279, 0.8569852433372879, 0.8698221353546198, 0.8828513128260428, 0.8960756560200679, 0.9094980883491179, 0.9231215770157858, 0.9369491336687732, 0.9509838150686546, 0.9652287237636131, 0.9796870087753001, 0.9943618662949663, 1.009256540390022, 1.0243743237211793, 1.039718558270339, 1.0552926360793768]
CELL_UPPER = [0.10850126882851431, 0.11012652326845213, 0.11177612260336729, 0.1134504314985681, 0.11514982008173137, 0.11687466402472398, 0.11862534462664985, 0.12040224889814118, 0.12220576964691213, 0.1240363055645941, 0.12589426131487158, 0.12778004762293835, 0.1296940813662937, 0.13163678566689843, 0.1336085899847116, 0.13560993021262804, 0.13764124877283837, 0.1397029947146319, 0.14179562381366503, 0.14391959867271614, 0.1460753888239501, 0.14826347083271438, 0.15048432840288994, 0.15273845248382034, 0.1550263413788424, 0.15734850085544258, 0.15970544425706354, 0.1620976926165852, 0.16452577477150598, 0.1669902274808491, 0.16949159554382012, 0.17203043192024178, 0.1746072978527931, 0.1772227629910793, 0.1798774055175601, 0.18257181227536456, 0.1853065788980204, 0.18808230994112637, 0.19089961901599722, 0.1937591289253104, 0.19666147180078455, 0.1996072892429206, 0.20259723246283576, 0.20563196242622217, 0.208712149999462, 0.21183847609793105, 0.21501163183652408, 0.2182323186824345, 0.2215012486102229, 0.22481914425920846, 0.2281867390932172, 0.23160477756272418, 0.23507401526942373, 0.23859521913326498, 0.2421691675619894, 0.24579665062320802, 0.2494784702190562, 0.2532154402634642, 0.2570083868620836, 0.2608581484949087, 0.26476557620163327, 0.268731533769784, 0.27275689792567165, 0.2768425585282034, 0.28098941876559685, 0.2851983953550422, 0.289470418745354, 0.2938064333226592, 0.2982073976191657, 0.3026742845250585, 0.30720808150356976, 0.31180979080927, 0.3164804297096297, 0.32122103070989955, 0.3260326417813589, 0.3309163265929834, 0.3358731647465832, 0.34090425201546204, 0.34601070058665334, 0.35119363930678255, 0.35645421393161375, 0.36179358737933376, 0.36721293998763027, 0.3727134697746209, 0.37829639270369014, 0.3839629429522948, 0.3897143731847936, 0.3955519548293662, 0.4014769783590778, 0.4074907535771556, 0.41359460990653724, 0.4197898966837578, 0.42607798345723724, 0.43246026029003715, 0.4389381380671525, 0.4455130488074055, 0.4521864459800124, 0.4589598048258913, 0.465834622683784, 0.4728124193212608, 0.4798947372706862, 0.4870831421702149, 0.4943792231098967, 0.501784592982965, 0.5093008888423883, 0.516929772262762, 0.5246729297076205, 0.5325320729022519, 0.5405089392120976, 0.5486052920268185, 0.5568229211501164, 0.565163643195392, 0.5736293019873319, 0.5822217689695091, 0.5909429436180904, 0.59979475386174, 0.6087791565078132, 0.6178981376749337, 0.6271537132320518, 0.636547929244077, 0.6460828624241882, 0.6557606205929175, 0.6655833431441115, 0.6755532015178722, 0.6856723996805814, 0.6959431746121167, 0.7063677968003645, 0.7169485707431406, 0.7276878354576296, 0.7385879649974554, 0.7496513689774952, 0.7608804931065571, 0.7722778197280364, 0.783845868368668, 0.7955871962955015, 0.8075043990812178, 0.8196001111779151, 0.8318770064994874, 0.8443377990127279, 0.8569852433372879, 0.8698221353546198, 0.8828513128260428, 0.8960756560200679, 0.9094980883491179, 0.9231215770157858, 0.9369491336687732, 0.9509838150686546, 0.9652287237636131, 0.9796870087753001, 0.9943618662949663, 1.009256540390022, 1.0243743237211793, 1.039718558270339, 1.0552926360793768, 1.0711]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.0064516129032258064, 0.006451612903225823]
ARM_ORDER = [114, 115, 113, 116, 112, 117, 111, 118, 110, 119, 109, 108, 120, 107, 121, 106, 122, 105, 123, 104, 103, 124, 102, 125, 101, 100, 126, 99, 127, 98, 97, 128, 96, 129, 95, 94, 130, 93, 92, 131, 91, 90, 132, 89, 88, 133, 87, 86, 134, 85, 84, 135, 83, 82, 136, 81, 80, 137, 79, 78, 77, 138, 76, 75, 74, 139, 73, 72, 140, 71, 70, 69, 141, 68, 67, 66, 142, 65, 64, 63, 62, 143, 61, 60, 59, 144, 58, 57, 56, 55, 145, 54, 53, 52, 51, 146, 50, 49, 48, 47, 147, 46, 45, 44, 43, 42, 148, 41, 40, 39, 38, 37, 149, 36, 35, 34, 33, 32, 31, 150, 30, 29, 28, 27, 26, 25, 151, 24, 23, 22, 21, 20, 19, 18, 152, 17, 16, 15, 14, 13, 12, 11, 10, 153, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 154]
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
