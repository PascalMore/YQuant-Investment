"""
Single Moving Average
SPY trend regime driven by a configurable moving average.
"""

# @param ma_period int 50 range=2:250:1
# @param target_pct float 0.95 range=0.05:1:0.05

def initialize(context):
    g.symbol = "USStock:SPY"
    context.set_universe([g.symbol])
    context.set_benchmark(g.symbol)
    context.subscribe(frequency="1d")
    context.set_metadata(direction_mode="long_only")
    context.set_warmup(260)


def handle_data(context, data):
    ma_period = int(context.params.get("ma_period", 50))
    target_pct = float(context.params.get("target_pct", 0.95))
    bars = get_history(ma_period + 2, "1d", "close", g.symbol)
    if len(bars) < ma_period + 1:
        return
    close = bars["close"]
    average = float(close.iloc[:-1].tail(ma_period).mean())
    price = float(close.iloc[-1])
    position = get_position(g.symbol)
    is_long = float(position.amount or 0.0) > 0
    if price > average and not is_long:
        order_target_percent(g.symbol, target_pct, reason="single_ma_entry")
    elif price <= average and is_long:
        order_target_percent(g.symbol, 0.0, reason="single_ma_exit")
