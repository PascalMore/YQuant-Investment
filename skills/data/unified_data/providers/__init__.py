"""External data providers for unified_data (Phase 1B-A).

This package ships the **Phase 1B-A stub** implementations of the
external data providers (Tushare / AKShare). Both providers extend
:class:`BaseExternalProvider` and return pre-defined ``pd.DataFrame``
shapes without performing any real network call — Phase 1B-A
explicitly defers real HTTP / API integration to later phases.

The package exposes:

* :class:`RateLimiter` / :func:`with_retry` — composable rate limiting
  and exponential-backoff retry helpers (see
  :mod:`.rate_limiter`).
* :class:`BaseExternalProvider` — abstract base class that all external
  providers inherit from. It owns the rate limiter, supplies the
  ``_check_capability`` / ``_to_canonical`` hooks, and guarantees the
  ``fetch()`` entry contract (returns a ``pd.DataFrame`` even if empty).
* :class:`TushareProvider` / :class:`AKShareProvider` — concrete stub
  providers with the conservative capability sets defined in
  SPEC-03-008 §4.5.
* :data:`STUB_COLUMNS` / :func:`stub_dataframe_for` — the canonical
  stub DataFrame column definitions shared by both providers and
  exposed for tests / fixtures.

Security note (P-10):
    No provider in this module ever reads, prints, persists or logs a
    real Tushare / AKShare token. ``is_available()`` checks only the
    presence of an environment variable (or importability) and never
    leaks its value.
"""

from __future__ import annotations

import pandas as pd

from .base_external import BaseExternalProvider
from .rate_limiter import RateLimiter, with_retry
from .tushare import TushareProvider
from .akshare import AKShareProvider

__all__ = [
    "AKShareProvider",
    "BaseExternalProvider",
    "RateLimiter",
    "STUB_COLUMNS",
    "TushareProvider",
    "stub_dataframe_for",
    "with_retry",
]


# ---------------------------------------------------------------------------
# Stub DataFrame column definitions
# ---------------------------------------------------------------------------
# Per SPEC-03-008 §4.5 and DESIGN-03-008 §3.3.7. Each capability maps to a
# list of canonical column names; the providers return an empty
# ``pd.DataFrame`` with these columns so consumers can rely on a stable
# schema without performing a real network call in 1B-A.

STUB_COLUMNS: dict[str, list[str]] = {
    "market_data.kline_daily": [
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ],
    "market_data.kline_weekly": [
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ],
    "market_data.realtime_quote": [
        "symbol",
        "name",
        "price",
        "change",
        "pct_chg",
        "volume",
        "amount",
    ],
    "market_data.adj_factor": [
        "trade_date",
        "adj_factor",
    ],
    "financial.income_statement": [
        "report_period",
        "total_revenue",
        "operating_profit",
        "net_profit",
    ],
    "financial.balance_sheet": [
        "report_period",
        "total_assets",
        "total_liabilities",
        "shareholder_equity",
    ],
    "financial.cash_flow": [
        "report_period",
        "operating_cf",
        "investing_cf",
        "financing_cf",
    ],
    "valuation.daily_basic": [
        "trade_date",
        "pe",
        "pe_ttm",
        "pb",
        "ps",
        "ps_ttm",
        "total_mv",
    ],
    "calendar.trading_days": [
        "cal_date",
        "is_open",
        "pretrade_date",
    ],
    "calendar.is_trading_day": [
        "cal_date",
        "is_open",
    ],
    "metadata.stock_list": [
        "symbol",
        "name",
        "area",
        "industry",
        "market",
        "list_date",
    ],
    "metadata.index_members": [
        "index_code",
        "index_name",
        "con_code",
        "con_name",
    ],
    "news.stock_news": [
        "title",
        "content",
        "source",
        "publish_time",
    ],
}


def stub_dataframe_for(capability: str) -> pd.DataFrame:
    """Return the 1B-A stub ``pd.DataFrame`` for ``capability``.

    The DataFrame has the canonical column set defined in
    :data:`STUB_COLUMNS` (or a single ``"data"`` column for unknown
    capabilities) and zero rows. Callers must not rely on the contents;
    the contract is purely **schema-level**.

    Args:
        capability: The ``"domain.operation"`` capability string.

    Returns:
        A ``pd.DataFrame`` instance with the canonical columns for the
        capability. Always empty (zero rows) in Phase 1B-A.
    """
    columns = STUB_COLUMNS.get(capability, ["data"])
    return pd.DataFrame(columns=columns)