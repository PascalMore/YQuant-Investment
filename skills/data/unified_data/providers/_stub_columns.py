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


# ---------------------------------------------------------------------------
# Phase 3 P0 expected-field sets (PA-1 / PA-2 / PB-1 / PB-2 / PC-1 / PC-2)
# ---------------------------------------------------------------------------
# These frozen tuples declare the canonical column / field set the
# downstream ``from_dict`` factory / dataclass / mapping tests align
# against. They are **deliberately separate** from the per-capability
# STUB_COLUMNS dict above because:
#
# * STUB_COLUMNS is what the stub provider returns (DataFrame columns).
# * ``_EXPECTED_*_FIELDS`` is what the mapping layer / dataclass
#   contract requires (field-level coverage).
#
# The two layers overlap by design but the expected-sets are the
# authoritative contract — DESIGN-03-014 §P0.3 / §P0.4 / §P0.5. Each
# tuple is frozen (immutable sequence, not set) so a future refactor
# must move / delete deliberately. The twin definition in
# :mod:`skills.data.unified_data.providers.__init__` mirrors the
# canonical tuple byte-for-byte (test_p0_twin_equivalence pins the
# equivalence).
#
# PA-1 / PA-2 (P3-A sector)
# -------------------------
# Aligns with AKShare ``stock_board_industry_cons_em`` /
# ``stock_board_industry_rank_em`` documented field shape. The
# snapshot set (12 cols) and the ranking set (8 cols) are deliberately
# overlapping subsets; ranking ⊂ snapshot per DESIGN §P0.3.2.
#
# PB-1 / PB-2 (P3-B flow)
# -----------------------
# ``_EXPECTED_FLOW_FIELDS`` covers the 17-field V0.5 schema (incl. the
# business key + 4 flow bands + ratio + 3 northbound + 3 margin +
# metadata). ``_EXPECTED_NORTHBOUND_FIELDS`` is the strict 3-field
# Pascal C fail-stop projection.
#
# PC-1 / PC-2 (P3-C sentiment + limit-up)
# ---------------------------------------
# ``_EXPECTED_SENTIMENT_FIELDS`` mirrors the 22-field canonical
# :class:`MarketSentimentSnapshot` dataclass byte-for-byte. Any
# regression that introduces a superseded 10-field name
# (``sentiment_type``, ``market_date``, ``score``, ``sample_size``,
# ``source``, ``notes``, ``metadata``) breaks
# ``test_no_expected_set_references_superseded_sentiment_fields``.
# ``_EXPECTED_LIMIT_UP_FIELDS`` mirrors the 15-field
# :class:`LimitUpPoolRecord` dataclass byte-for-byte.

_EXPECTED_SECTOR_SNAPSHOT_FIELDS: tuple[str, ...] = (
    # P3-A §P0.3.1 / SPEC-03-014 §3.1 frozen snapshot column set.
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
)

_EXPECTED_SECTOR_RANKING_FIELDS: tuple[str, ...] = (
    # P3-A §P0.3.2 frozen narrower 8-column ranking set. Strict
    # subset of ``_EXPECTED_SECTOR_SNAPSHOT_FIELDS`` — see
    # ``test_sector_ranking_is_strict_subset_of_sector_snapshot``.
    "sector_code",
    "sector_name",
    "sector_type",
    "snapshot_date",
    "rank",
    "pct_chg",
    "advance_count",
    "decline_count",
)

_EXPECTED_FLOW_FIELDS: tuple[str, ...] = (
    # P3-B §P0.4.1 / SPEC-03-014 §3.2 frozen 17-field V0.5 contract.
    # 10 baseline fields per RFC §PB-1 (symbol / market / trade_date
    # + 4 flow bands + ratio + margin_balance) plus the remaining
    # band fields and metadata.
    "symbol",
    "market",
    "trade_date",
    "main_net_inflow",
    "super_large_net_inflow",
    "large_net_inflow",
    "medium_net_inflow",
    "small_net_inflow",
    "main_net_inflow_ratio",
    "northbound_net_inflow",
    "northbound_hold_shares",
    "northbound_hold_ratio",
    "margin_buy",
    "margin_sell",
    "margin_balance",
    "fetched_at",
    "provider",
)

_EXPECTED_NORTHBOUND_FIELDS: tuple[str, ...] = (
    # P3-B §P0.4.2 / Pascal C fail-stop. Exactly three fields, all
    # permanently None on the read path. Any future addition must
    # revisit SPEC §14.4.5.2 C.
    "northbound_net_inflow",
    "northbound_hold_shares",
    "northbound_hold_ratio",
)

_EXPECTED_SENTIMENT_FIELDS: tuple[str, ...] = (
    # P3-C §P0.5.1 / SPEC-03-014 §3.3 / RFC-03-014 V0.16. The 22-field
    # Pascal canonical contract — mirrors
    # :class:`MarketSentimentSnapshot.__dataclass_fields__` exactly.
    # Any drift between the dataclass and this tuple breaks
    # ``test_sentiment_set_matches_market_sentiment_snapshot_dataclass``.
    "snapshot_date",
    "snapshot_time",
    "market",
    "limit_up_count",
    "limit_down_count",
    "limit_up_count_ex_st",
    "limit_down_count_ex_st",
    "advance_count",
    "decline_count",
    "flat_count",
    "total_listed_count",
    "market_temperature",
    "total_turnover",
    "hot_concepts",
    "continuous_limit_up",
    "max_continuous_days",
    "northbound_net_flow",
    "limit_up_pool",
    "limit_down_pool",
    "fetched_at",
    "provider",
    "raw_payload",
)

_EXPECTED_LIMIT_UP_FIELDS: tuple[str, ...] = (
    # P3-C §P0.5.2 / SPEC-03-014 §3.3 limit-up pool. Mirrors the
    # 15-field :class:`LimitUpPoolRecord` dataclass exactly. Any
    # drift breaks
    # ``test_limit_up_set_matches_limit_up_pool_record_dataclass``.
    "symbol",
    "market",
    "trade_date",
    "status",
    "limit_up_time",
    "last_price",
    "pct_chg",
    "order_amount",
    "turnover_amount",
    "order_ratio",
    "turnover_rate",
    "consecutive_days",
    "reason",
    "market_cap",
    "fetched_at",
    "provider",
)


def stub_dataframe_for(capability: str) -> pd.DataFrame:
    """Return the Phase 1B-A stub ``pd.DataFrame`` for ``capability``.

    Returns an empty ``pd.DataFrame`` with the canonical columns
    defined in :data:`STUB_COLUMNS`. Callers must not rely on row
    contents — the contract is purely schema-level.
    """
    columns = STUB_COLUMNS.get(capability, ["data"])
    return pd.DataFrame(columns=columns)


__all__ = [
    "STUB_COLUMNS",
    "_EXPECTED_FLOW_FIELDS",
    "_EXPECTED_LIMIT_UP_FIELDS",
    "_EXPECTED_NORTHBOUND_FIELDS",
    "_EXPECTED_SECTOR_RANKING_FIELDS",
    "_EXPECTED_SECTOR_SNAPSHOT_FIELDS",
    "_EXPECTED_SENTIMENT_FIELDS",
    "stub_dataframe_for",
]