"""Shared stub DataFrame definitions for Phase 1B-A providers.

This module exposes the canonical stub column definitions and the
``stub_dataframe_for(capability)`` factory used by every external
provider in :mod:`skills.data.unified_data.providers`. Keeping it in
its own submodule avoids the circular import that would otherwise
occur when :mod:`tushare` and :mod:`akshare` both import from
:mod:`.providers.__init__` while that ``__init__`` is still being
initialised.

Per SPEC-03-008 §4.5 and DESIGN-03-008 §3.3.7.
"""

from __future__ import annotations

import pandas as pd


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
    """Return the Phase 1B-A stub ``pd.DataFrame`` for ``capability``.

    Returns an empty ``pd.DataFrame`` with the canonical columns
    defined in :data:`STUB_COLUMNS`. Callers must not rely on row
    contents — the contract is purely schema-level.
    """
    columns = STUB_COLUMNS.get(capability, ["data"])
    return pd.DataFrame(columns=columns)


__all__ = ["STUB_COLUMNS", "stub_dataframe_for"]