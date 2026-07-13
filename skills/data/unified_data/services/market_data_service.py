"""Market data domain service (Phase 1A).

Wraps three TA-CN MongoDB collections:

* ``market_quotes``     -> ``get_realtime_quote``
* ``stock_daily_quotes`` -> ``get_kline_daily``
* ``index_daily_quotes`` -> ``get_index_daily`` (market index path)

All methods take a :class:`SecurityId` plus optional filters; the
underlying symbol (``SecurityId.symbol``) is used as the TA-CN
``symbol`` field. Each method returns a ``DataResult`` with the
canonical ``provider="ta_cn_adapter"`` / freshness labels.
"""

from __future__ import annotations

from ..adapters import TA_CNMongoAdapter
from ..models import DataResult, SecurityId
from ..models.domain import DailyBar, IndexDailyBar, RealtimeQuote
from . import SERVICE_ERRORS, wrap_empty, wrap_error, wrap_success


class MarketDataService:
    """行情域服务（Phase 1A — TA-CN MongoDB 只读）。"""

    DOMAIN = "market_data"

    def __init__(self, adapter: TA_CNMongoAdapter) -> None:
        self._adapter = adapter

    # ── market_quotes ─────────────────────────────────────────
    def get_realtime_quote(self, security_id: SecurityId) -> DataResult:
        """返回 ``RealtimeQuote`` 或空/错误结果。"""
        domain = self.DOMAIN
        operation = "realtime_quote"
        try:
            doc = self._adapter.get_realtime_quotes(security_id.symbol)
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        if not doc:
            return wrap_empty(security_id, domain, operation)
        try:
            quote = RealtimeQuote.from_ta_cn_doc(doc)
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        return wrap_success(quote, security_id, domain, operation)

    # ── stock_daily_quotes ────────────────────────────────────
    def get_kline_daily(
        self,
        security_id: SecurityId,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> DataResult:
        """返回 ``list[DailyBar]``、空或错误结果。"""
        domain = self.DOMAIN
        operation = "kline_daily"
        try:
            docs = self._adapter.get_daily_bars(
                security_id.symbol,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        if not docs:
            return wrap_empty(security_id, domain, operation)
        try:
            bars = [DailyBar.from_ta_cn_doc(doc) for doc in docs]
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        return wrap_success(bars, security_id, domain, operation)

    # ── index_daily_quotes (market index) ─────────────────────
    def get_index_daily(
        self,
        security_id: SecurityId,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> DataResult:
        """返回 ``list[IndexDailyBar]``、空或错误结果。

        调用方传入的 ``security_id`` 既可是大盘指数（``Market.INDEX``）
        也可是 ``SecurityId(market=Market.CN, symbol="<index code>")``；
        adapter 的 ``symbol``/``sector_code`` 多字段 fallback 已覆盖。
        """
        domain = self.DOMAIN
        operation = "index_daily"
        try:
            docs = self._adapter.get_index_daily_bars(
                symbol=security_id.symbol,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        if not docs:
            return wrap_empty(security_id, domain, operation)
        try:
            bars = [IndexDailyBar.from_ta_cn_doc(doc) for doc in docs]
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        return wrap_success(bars, security_id, domain, operation)


__all__ = ["MarketDataService"]
