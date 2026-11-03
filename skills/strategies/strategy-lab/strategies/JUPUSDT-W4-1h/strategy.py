"""
neutral-grid-JUPUSDT-1h
Strategy API V2 grid robot generated from the visual builder.
"""

INSTRUMENT = 'Crypto:JUP/USDT@swap'
TIMEFRAME = '1h'
GRID_SIDE = 'neutral'
DYNAMIC_ANCHOR = False
CELL_LOWER = [0.1069, 0.10850121584734457, 0.11012641571891539, 0.11177595886260466, 0.11345020990734682, 0.11514953894371925, 0.11687432160575015, 0.11862493915395197, 0.1204017785595983, 0.12220523259026342, 0.12403569989664281, 0.12589358510067444, 0.1277792988849796, 0.12969325808364385, 0.13163588577435742, 0.13360761137193589, 0.1356088707232418, 0.1376401062035276, 0.13970176681422244, 0.14179430828218287, 0.14391819316043067, 0.1460738909303996, 0.14826187810571334, 0.15048263833751818, 0.15273666252139337, 0.1550244489058627, 0.1573465032025318, 0.15970333869787462, 0.16209547636669477, 0.16452344498728616, 0.16698778125831856, 0.1694890299174741, 0.1720277438618606, 0.17460448427022865, 0.17721982072701925, 0.17987433134826966, 0.1825686029094049, 0.1853032309749437, 0.18807882003014698, 0.19089598361463844, 0.19375534445802656, 0.19665753461755786, 0.19960319561783238, 0.20259297859261155, 0.20562754442875025, 0.20870756391228498, 0.21183371787671, 0.2150066973534743, 0.21822720372473345, 0.2214959488783886, 0.22481365536544842, 0.22818105655974794, 0.2315988968200594, 0.23506793165463188, 0.23858892788819508, 0.2421626638314648, 0.2457899294531871, 0.24947152655476004, 0.2532082689474703, 0.2570009826323849, 0.2608505059829378, 0.2647576899302505, 0.2687233981512295, 0.2727485072594805, 0.27683390699908256, 0.28098050044126444, 0.2851892041840274, 0.2894609485547575, 0.2937966778158732, 0.29819735037355294, 0.30266393898958943, 0.3071974309964169, 0.31179882851535984, 0.31646914867814996, 0.32120942385176177, 0.3260207018666154, 0.3309040462481984, 0.33586053645215597, 0.3408912681029028, 0.3459973532358097, 0.351179920543017, 0.35644011562292993, 0.3617791012334516, 0.3671980575490089, 0.3726981824214281, 0.3782806916447182, 0.38394681922382007, 0.38969781764738154, 0.39553495816461803, 0.40145953106632015, 0.40747284597007044, 0.4135762321097325, 0.4197710386292756, 0.42605863488100143, 0.4324404107282367, 0.4389177768525607, 0.4454921650656344, 0.4521650286256993, 0.45893784255881886, 0.4658121039849303, 0.4727893324487804, 0.47987107025581927, 0.4870588828131234, 0.49435435897542745, 0.501759111396338, 0.509274776884807, 0.5169030167669476, 0.5246455172532661, 0.5325039898113972, 0.5404801715444209, 0.5485758255748459, 0.5567927414343461, 0.5651327354593331, 0.5735976511924543, 0.5821893597901063, 0.5909097604360493, 0.5997607807612202, 0.6087443772698322, 0.6178625357718561, 0.6271172718219815, 0.6365106311651513, 0.6460446901887708, 0.6557215563816902, 0.6655433688000606, 0.6755122985401704, 0.6856305492183621, 0.6959003574581375, 0.7063239933845615, 0.7169037611260682, 0.7276419993237855, 0.7385410816484883, 0.7496034173252943, 0.7608314516662196, 0.772227666610711, 0.7837945812742748, 0.7955347525053242, 0.8074507754503649, 0.81954528412765, 0.8318209520094247, 0.8442804926128928, 0.8569266601000365, 0.8697622498864183, 0.8827900992591048, 0.8960130880038436, 0.909434139041635, 0.9230562190748403, 0.9368823392429655, 0.9509155557882701, 0.9651589707313448, 0.9796157325568058, 0.9942890369092662, 1.0091821272997255, 1.024298295822543, 1.0396408838831523, 1.0552132829366696, 1.0710189352375739, 1.0870613346006097, 1.103344027173089, 1.1198706122187625, 1.136644742913432, 1.1536701271524767, 1.1709505283704804, 1.1884897663731304, 1.206291718181582, 1.224360318889467, 1.2426995625327377, 1.261313502972547, 1.2802062547913433, 1.2993819942023959, 1.3188449599729393, 1.3385994543611448, 1.3586498440671302, 1.379000561198211, 1.3996561042486098, 1.4206210390938432]
CELL_UPPER = [0.10850121584734457, 0.11012641571891539, 0.11177595886260466, 0.11345020990734682, 0.11514953894371925, 0.11687432160575015, 0.11862493915395197, 0.1204017785595983, 0.12220523259026342, 0.12403569989664281, 0.12589358510067444, 0.1277792988849796, 0.12969325808364385, 0.13163588577435742, 0.13360761137193589, 0.1356088707232418, 0.1376401062035276, 0.13970176681422244, 0.14179430828218287, 0.14391819316043067, 0.1460738909303996, 0.14826187810571334, 0.15048263833751818, 0.15273666252139337, 0.1550244489058627, 0.1573465032025318, 0.15970333869787462, 0.16209547636669477, 0.16452344498728616, 0.16698778125831856, 0.1694890299174741, 0.1720277438618606, 0.17460448427022865, 0.17721982072701925, 0.17987433134826966, 0.1825686029094049, 0.1853032309749437, 0.18807882003014698, 0.19089598361463844, 0.19375534445802656, 0.19665753461755786, 0.19960319561783238, 0.20259297859261155, 0.20562754442875025, 0.20870756391228498, 0.21183371787671, 0.2150066973534743, 0.21822720372473345, 0.2214959488783886, 0.22481365536544842, 0.22818105655974794, 0.2315988968200594, 0.23506793165463188, 0.23858892788819508, 0.2421626638314648, 0.2457899294531871, 0.24947152655476004, 0.2532082689474703, 0.2570009826323849, 0.2608505059829378, 0.2647576899302505, 0.2687233981512295, 0.2727485072594805, 0.27683390699908256, 0.28098050044126444, 0.2851892041840274, 0.2894609485547575, 0.2937966778158732, 0.29819735037355294, 0.30266393898958943, 0.3071974309964169, 0.31179882851535984, 0.31646914867814996, 0.32120942385176177, 0.3260207018666154, 0.3309040462481984, 0.33586053645215597, 0.3408912681029028, 0.3459973532358097, 0.351179920543017, 0.35644011562292993, 0.3617791012334516, 0.3671980575490089, 0.3726981824214281, 0.3782806916447182, 0.38394681922382007, 0.38969781764738154, 0.39553495816461803, 0.40145953106632015, 0.40747284597007044, 0.4135762321097325, 0.4197710386292756, 0.42605863488100143, 0.4324404107282367, 0.4389177768525607, 0.4454921650656344, 0.4521650286256993, 0.45893784255881886, 0.4658121039849303, 0.4727893324487804, 0.47987107025581927, 0.4870588828131234, 0.49435435897542745, 0.501759111396338, 0.509274776884807, 0.5169030167669476, 0.5246455172532661, 0.5325039898113972, 0.5404801715444209, 0.5485758255748459, 0.5567927414343461, 0.5651327354593331, 0.5735976511924543, 0.5821893597901063, 0.5909097604360493, 0.5997607807612202, 0.6087443772698322, 0.6178625357718561, 0.6271172718219815, 0.6365106311651513, 0.6460446901887708, 0.6557215563816902, 0.6655433688000606, 0.6755122985401704, 0.6856305492183621, 0.6959003574581375, 0.7063239933845615, 0.7169037611260682, 0.7276419993237855, 0.7385410816484883, 0.7496034173252943, 0.7608314516662196, 0.772227666610711, 0.7837945812742748, 0.7955347525053242, 0.8074507754503649, 0.81954528412765, 0.8318209520094247, 0.8442804926128928, 0.8569266601000365, 0.8697622498864183, 0.8827900992591048, 0.8960130880038436, 0.909434139041635, 0.9230562190748403, 0.9368823392429655, 0.9509155557882701, 0.9651589707313448, 0.9796157325568058, 0.9942890369092662, 1.0091821272997255, 1.024298295822543, 1.0396408838831523, 1.0552132829366696, 1.0710189352375739, 1.0870613346006097, 1.103344027173089, 1.1198706122187625, 1.136644742913432, 1.1536701271524767, 1.1709505283704804, 1.1884897663731304, 1.206291718181582, 1.224360318889467, 1.2426995625327377, 1.261313502972547, 1.2802062547913433, 1.2993819942023959, 1.3188449599729393, 1.3385994543611448, 1.3586498440671302, 1.379000561198211, 1.3996561042486098, 1.4206210390938432, 1.4419]
CELL_ROLES = ['long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'long_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry', 'short_entry']
CELL_BUDGET_PCTS = [0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285714, 0.005714285714285672]
ARM_ORDER = [133, 132, 134, 131, 135, 130, 136, 129, 137, 128, 127, 138, 126, 139, 125, 140, 124, 141, 123, 122, 142, 121, 143, 120, 119, 144, 118, 145, 117, 116, 146, 115, 147, 114, 113, 148, 112, 111, 149, 110, 109, 150, 108, 107, 151, 106, 105, 152, 104, 103, 153, 102, 101, 154, 100, 99, 155, 98, 97, 96, 156, 95, 94, 157, 93, 92, 91, 158, 90, 89, 88, 159, 87, 86, 85, 160, 84, 83, 82, 161, 81, 80, 79, 162, 78, 77, 76, 75, 163, 74, 73, 72, 71, 164, 70, 69, 68, 67, 165, 66, 65, 64, 63, 62, 166, 61, 60, 59, 58, 57, 167, 56, 55, 54, 53, 52, 168, 51, 50, 49, 48, 47, 46, 169, 45, 44, 43, 42, 41, 40, 39, 170, 38, 37, 36, 35, 34, 33, 32, 171, 31, 30, 29, 28, 27, 26, 25, 24, 23, 172, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 173, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0, 174]
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
