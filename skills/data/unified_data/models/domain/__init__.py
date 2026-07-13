"""Canonical domain objects — Phase 1A.

8 dataclasses covering the 8 TA-CN MongoDB collections in scope for
Phase 1A (DESIGN-03-007 §Phase 1A / SPEC-03-007 §4).
"""

from .financial import VALID_STATEMENT_TYPES, FinancialStatement
from .market_data import DailyBar, IndexDailyBar, RealtimeQuote
from .metadata import IndexInfo, StockInfo
from .news import NewsItem
from .sector import SectorClassification

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
]
