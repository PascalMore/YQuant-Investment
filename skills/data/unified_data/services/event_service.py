"""Event / news domain service (Phase 1A).

Single TA-CN collection: ``stock_news``. Wrapped via the adapter's
``get_news()`` + :class:`NewsItem.from_ta_cn_doc`.
"""

from __future__ import annotations

from ..adapters import TA_CNMongoAdapter
from ..models import DataResult, SecurityId
from ..models.domain import NewsItem
from . import SERVICE_ERRORS, wrap_empty, wrap_error, wrap_success


class EventService:
    """事件/催化剂域服务（Phase 1A — TA-CN MongoDB 只读）。"""

    DOMAIN = "event"

    def __init__(self, adapter: TA_CNMongoAdapter) -> None:
        self._adapter = adapter

    def get_news(
        self,
        security_id: SecurityId,
        limit: int = 20,
    ) -> DataResult:
        """返回 ``list[NewsItem]``、空或错误结果。"""
        domain = self.DOMAIN
        operation = "news"
        try:
            docs = self._adapter.get_news(security_id.symbol, limit=limit)
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        if not docs:
            return wrap_empty(security_id, domain, operation)
        try:
            items = [NewsItem.from_ta_cn_doc(doc) for doc in docs]
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        return wrap_success(items, security_id, domain, operation)


__all__ = ["EventService"]
