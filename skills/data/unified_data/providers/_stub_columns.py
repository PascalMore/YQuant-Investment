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
    # Phase 3 P3-A (T3-C Repair-R2): sector snapshot / ranking columns
    # are constrained to the frozen contract in SPEC-03-014 §4.3:
    # ``sector.snapshot`` = 12 columns, ``sector.ranking`` = 8 columns,
    # in the exact order documented below. These column sets are
    # deliberately **narrower** than the SectorSnapshot dataclass field
    # set in :mod:`models.domain.sector` (SPEC §3.1 / DESIGN §3.1):
    # the stub schema only carries the columns that the contract §4.3
    # freezes, not every dataclass field. Provider / market /
    # leading_stock_name / leading_pct_chg / members / fetched_at /
    # raw_payload and similar dataclass-only fields belong to the
    # dataclass round-trip, not to the canonical stub columns.
    # The contract is purely schema-level — ``stub_dataframe_for``
    # returns 0 rows so consumers see only the column set, never the
    # row contents.
    "sector.snapshot": [
        "sector_code",
        "sector_name",
        "sector_type",
        "snapshot_date",
        "rank",
        "pct_chg",
        "leading_stock",
        "advance_count",
        "decline_count",
        "total_count",
        "turnover_rate",
        "main_net_inflow",
    ],
    # Same §4.3 frozen contract, narrower 8-column ranking shape.
    # The two capabilities address the same P3-A collection
    # ``03_data_ud_market_sector_snapshot`` per
    # :data:`P3_COLLECTION_BY_CAPABILITY` (V0.5 §0.4).
    "sector.ranking": [
        "sector_code",
        "sector_name",
        "sector_type",
        "snapshot_date",
        "rank",
        "pct_chg",
        "advance_count",
        "decline_count",
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