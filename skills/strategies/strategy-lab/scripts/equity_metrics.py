"""Shared equity metrics (SPEC-07-001 M2 §12–§13).

One implementation of the return / drawdown / Sharpe calculation, used by the
grid research wrapper and by the BTC5m research instance. The module is
stdlib-only and has no network, platform or research behaviour: it takes
parsed rows and returns a dictionary of metrics.

The arithmetic here is the original grid calculation, unchanged: the peak
starts at the initial capital, the interval return is measured against that
capital, the drawdown is peak-to-trough, and the Sharpe ratio uses only
adjacent equity returns with a population standard deviation and no risk-free
rate. The annualization factor is ``365 * (86400 // frequency_seconds)``, which
is the original expression and is deliberately not replaced by an exact
division.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from typing import Any

# The value written where a metric does not apply.
NA = "N/A"


def _iso(value: dt.datetime) -> str:
    """The UTC ISO form the grid carrier uses."""
    return value.isoformat().replace("+00:00", "Z")


def equity_metrics(
    rows: list[tuple[dt.datetime, float]],
    *,
    initial_capital: float,
    frequency_seconds: int,
    limitation: str,
) -> dict[str, object]:
    """Compute return, drawdown and population Sharpe from parsed equity rows.

    ``rows`` holds ``(UTC time, finite equity)`` pairs in the order they were
    observed. The caller has already validated the numbers and the times; the
    helper keeps the original grid semantics, including its deliberately
    counter-intuitive diagnostics: a nonpositive equity still produces a raw
    net PnL and a raw drawdown, and a status of ``ok`` does not imply a Sharpe
    ratio exists.

    The returned keys are the shared ones; a caller that needs a different
    name for one of them renames it rather than recomputing it.
    """
    equities = [equity for _, equity in rows]
    times = [moment for moment, _ in rows]

    peak, maximum_dd = initial_capital, 0.0
    peak_time = trough_time = None
    for timestamp, equity in zip(times, equities):
        if equity > peak:
            peak, peak_time = equity, _iso(timestamp)
        drawdown = (peak - equity) / peak * 100
        if drawdown > maximum_dd:
            maximum_dd, trough_time = drawdown, _iso(timestamp)
    frequency = int(frequency_seconds)
    missing = any((right - left).total_seconds() != frequency
                  for left, right in zip(times, times[1:]))
    reasons = []
    if not equities:
        reasons.append("empty equity sample")
    if missing:
        reasons.append("missing/duplicate/non-native bar")
    if any(equity <= 0 for equity in equities):
        reasons.append("nonpositive equity")
    valid_equity = bool(equities) and not missing and min(equities) > 0
    returns = [right / left - 1 for left, right in zip(equities, equities[1:])
               if left > 0]
    sharpe = NA
    if len(returns) < 2:
        reasons.append("insufficient return samples")
    if returns and statistics.pstdev(returns) == 0:
        reasons.append("zero volatility")
    if valid_equity and len(returns) >= 2 and statistics.pstdev(returns) > 0:
        periods_per_year = 365 * (86400 // frequency)
        sharpe = statistics.mean(returns) / statistics.pstdev(returns) * math.sqrt(periods_per_year)
    return {"status": "ok" if valid_equity else NA,
            "reason": "; ".join(reasons) or None,
            "net_pnl": equities[-1] - initial_capital if equities else NA,
            "return_pct": 100 * (equities[-1] / initial_capital - 1)
            if valid_equity else NA,
            "peak_equity": peak,
            "max_drawdown_pct": maximum_dd if equities and not missing else NA,
            "raw_max_drawdown_pct": maximum_dd if equities else None,
            "peak_time": peak_time, "trough_time": trough_time,
            "sharpe": sharpe, "return_count": len(returns), "bar_count": len(equities),
            "risk_free": 0, "ddof": 0,
            "periods_per_year": 365 * (86400 // frequency),
            "limitation": limitation}
