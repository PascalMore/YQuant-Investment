"""Metadata domain service (Phase 1A).

Wraps two TA-CN collections:

* ``stock_basic_info``  — ``get_stock_list`` / ``get_stock_info``
* ``index_basic_info``  — ``get_index_list`` / ``get_index_info``

The list methods do not attach a ``SecurityId`` because they return
multiple records; we synthesize a placeholder ``SecurityId`` with the
given market so the ``DataResult`` contract remains intact.
"""

from __future__ import annotations

from typing import Any

from ..adapters import TA_CNMongoAdapter
from ..models import DataResult, Market, SecurityId
from ..models.domain import IndexInfo, StockInfo
from . import SERVICE_ERRORS, wrap_empty, wrap_error, wrap_success


def _placeholder_sid(market: str) -> SecurityId:
    """Pick a deterministic placeholder symbol for list results."""
    return SecurityId(market=Market(market), symbol="LIST")


class MetadataService:
    """元数据域服务（Phase 1A — TA-CN MongoDB 只读）。"""

    DOMAIN = "metadata"

    def __init__(self, adapter: TA_CNMongoAdapter) -> None:
        self._adapter = adapter

    # ── stock_basic_info ──────────────────────────────────────
    def get_stock_info(self, security_id: SecurityId) -> DataResult:
        """返回单个 ``StockInfo``、空或错误结果。"""
        domain = self.DOMAIN
        operation = "stock_info"
        market_value = security_id.market.value
        try:
            doc = self._adapter.get_stock_info(
                security_id.symbol,
                market=market_value,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        if not doc:
            return wrap_empty(security_id, domain, operation)
        try:
            info = StockInfo.from_ta_cn_doc(doc)
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        return wrap_success(info, security_id, domain, operation)

    def get_stock_list(
        self,
        market: str = "CN",
        status: str = "L",
        limit: int = 0,
    ) -> DataResult:
        """返回 ``list[StockInfo]``、空或错误结果。"""
        domain = self.DOMAIN
        operation = "stock_list"
        placeholder = _placeholder_sid(market)
        try:
            docs = self._adapter.get_stock_list(
                market=market,
                status=status,
                limit=limit,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        return self._map_stock_list(placeholder, domain, operation, docs)

    def get_index_info(self, security_id: SecurityId) -> DataResult:
        """返回单个 ``IndexInfo``、空或错误结果。"""
        domain = self.DOMAIN
        operation = "index_info"
        try:
            doc = self._adapter.get_index_info(security_id.symbol)
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        if not doc:
            return wrap_empty(security_id, domain, operation)
        try:
            info = IndexInfo.from_ta_cn_doc(doc)
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        return wrap_success(info, security_id, domain, operation)

    def get_index_list(self, market: str = "CN") -> DataResult:
        """返回 ``list[IndexInfo]``、空或错误结果。"""
        domain = self.DOMAIN
        operation = "index_list"
        placeholder = _placeholder_sid(market)
        try:
            docs = self._adapter.get_index_list(market=market)
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        if not docs:
            return wrap_empty(placeholder, domain, operation)
        try:
            records: list[Any] = [IndexInfo.from_ta_cn_doc(doc) for doc in docs]
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        return wrap_success(records, placeholder, domain, operation)

    # ── internals ─────────────────────────────────────────────
    def _map_stock_list(
        self,
        placeholder: SecurityId,
        domain: str,
        operation: str,
        docs: list[dict],
    ) -> DataResult:
        if not docs:
            return wrap_empty(placeholder, domain, operation)
        try:
            records: list[StockInfo] = [
                StockInfo.from_ta_cn_doc(doc) for doc in docs
            ]
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        return wrap_success(records, placeholder, domain, operation)


__all__ = ["MetadataService"]
