"""Sector / index classification domain service (Phase 1A).

Wraps two TA-CN collections:

* ``stock_sector_info``:
  * ``get_stock_sector``     — list of ``SectorClassification`` for a stock
  * ``get_stocks_by_sector`` — list of ``SectorClassification`` for an L1 sector
* ``index_daily_quotes``:
  * ``get_sector_index_bars`` — list of ``IndexDailyBar`` (申万行业指数路径)

Note: ``get_sector_index_bars`` accepts ``sector_code`` directly instead
of a :class:`SecurityId` (the data model here is sector, not security).
"""

from __future__ import annotations

from ..adapters import TA_CNMongoAdapter
from ..models import DataResult, SecurityId
from ..models.domain import IndexDailyBar, SectorClassification
from . import SERVICE_ERRORS, wrap_empty, wrap_error, wrap_success


class SectorService:
    """板块/行业域服务（Phase 1A — TA-CN MongoDB 只读）。"""

    DOMAIN = "sector"

    def __init__(self, adapter: TA_CNMongoAdapter) -> None:
        self._adapter = adapter

    def get_stock_sector(
        self,
        security_id: SecurityId,
        classify_system: str | None = "SW",
    ) -> DataResult:
        """返回 ``list[SectorClassification]``、空或错误结果。

        ``full_symbol`` 由 adapter 通过 ``SecurityId.to_full_symbol()``
        推导；非 CN 市场 ``full_symbol`` 可能为 ``None``，此情形直接返回
        空结果。
        """
        domain = self.DOMAIN
        operation = "stock_sector"
        full_symbol = security_id.to_full_symbol()
        if not full_symbol:
            return wrap_empty(security_id, domain, operation)
        try:
            docs = self._adapter.get_stock_sector_info(
                full_symbol,
                classify_system=classify_system,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        if not docs:
            return wrap_empty(security_id, domain, operation)
        try:
            records = [SectorClassification.from_ta_cn_doc(doc) for doc in docs]
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        return wrap_success(records, security_id, domain, operation)

    def get_stocks_by_sector(
        self,
        sector_code: str,
        classify_system: str = "SW",
        security_id: SecurityId | None = None,
    ) -> DataResult:
        """返回某申万一级行业下的全部 ``SectorClassification`` 记录。

        调用方一般传入 ``security_id=None``；为保持与其它 service 相同
        的 ``SecurityId`` 入参契约，这里允许可选 ``security_id`` 用于
        日志关联，但底层查询只依赖 ``sector_code``。
        """
        domain = self.DOMAIN
        operation = "stocks_by_sector"
        # Use a placeholder SecurityId for non-security results.
        placeholder = security_id or SecurityId(market="INDEX", symbol=sector_code)
        try:
            docs = self._adapter.get_stocks_by_sector(
                sector_code,
                classify_system=classify_system,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        if not docs:
            return wrap_empty(placeholder, domain, operation)
        try:
            records = [SectorClassification.from_ta_cn_doc(doc) for doc in docs]
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        return wrap_success(records, placeholder, domain, operation)

    def get_sector_index_bars(
        self,
        sector_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> DataResult:
        """返回某申万行业指数的日线 ``list[IndexDailyBar]``、空或错误结果。"""
        domain = self.DOMAIN
        operation = "sector_index_bars"
        placeholder = SecurityId(market="INDEX", symbol=sector_code)
        try:
            docs = self._adapter.get_index_daily_bars(
                sector_code=sector_code,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        if not docs:
            return wrap_empty(placeholder, domain, operation)
        try:
            bars = [IndexDailyBar.from_ta_cn_doc(doc) for doc in docs]
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        return wrap_success(bars, placeholder, domain, operation)


__all__ = ["SectorService"]
