"""Canonical domain objects — Phase 1A.

8 dataclasses covering the 8 TA-CN MongoDB collections in scope for
Phase 1A (DESIGN-03-007 §Phase 1A / SPEC-03-007 §4).

Phase 3 P3-B (T3-P3B) re-export: :class:`CapitalFlowRecord` lives in
:mod:`.flow` and is re-exported here so consumers can reach it via
the same path as the Phase 1A dataclasses (mirrors the sector /
metadata surface).
"""

from .financial import VALID_STATEMENT_TYPES, FinancialStatement
from .flow import CapitalFlowRecord
from .market_data import DailyBar, IndexDailyBar, RealtimeQuote
from .metadata import IndexInfo, StockInfo
from .news import NewsItem
from .sector import SectorClassification
from .sentiment import LimitUpPoolRecord

__all__ = [
    "DailyBar",
    "IndexDailyBar",
    "RealtimeQuote",
    "FinancialStatement",
    "VALID_STATEMENT_TYPES",
    "IndexInfo",
    "StockInfo",
    "NewsItem",
    "SectorClassification",
    # Phase 3 P3-B (T3-P3B): capital-flow canonical record.
    "CapitalFlowRecord",
    # Phase 3 P3-C (T3-P3C): limit-up pool canonical record.
    "LimitUpPoolRecord",
]
