"""TA-CN MongoDB read-only adapter.

Phase 1A unified_data implementation (see DESIGN-03-007 §Phase 1A).

The adapter wraps a MongoDB ``Database`` handle injected by the caller.
T1/T2 design notes refer to eight collections; this class exposes 11 public read
methods because several collections support both single-record and
list/sector entry points.

    * ``stock_basic_info``
    * ``market_quotes``
    * ``stock_daily_quotes``
    * ``stock_financial_data``
    * ``stock_news``
    * ``index_basic_info``
    * ``index_daily_quotes``
    * ``stock_sector_info``

The adapter is **read-only by construction**:

* No method calls ``insert`` / ``update`` / ``delete`` / ``replace_one``.
* The constructor never invokes ``create_collection`` or
  ``create_index``; callers are responsible for schema/collection setup.
* MongoDB connection exceptions (``ConnectionFailure``,
  ``ServerSelectionTimeoutError``) are *not* caught here — they bubble
  up to the domain service layer, where they are converted into a
  ``DataResult.error(...)``.

Each method returns either a raw MongoDB document (``dict``) or a list
of such documents. **No canonical-domain mapping happens inside the
adapter** — that responsibility belongs to the domain services (see
``services/``) and the ``from_ta_cn_doc()`` classmethods on the
``skills.data.unified_data.models.domain`` dataclasses.

Date handling
-------------
* Public ``start_date`` / ``end_date`` parameters are accepted as
  ``"YYYY-MM-DD"`` strings and converted to ``"YYYYMMDD"`` (TA-CN's
  internal ``trade_date`` representation) inside the adapter.
* ``report_period`` parameters are accepted as ``"YYYYMMDD"`` directly,
  matching the TA-CN ``stock_financial_data.report_period`` storage.
* Date fields are returned as raw ``str`` values — no Python
  ``date``/``datetime`` conversion is performed in the adapter.

Design references
-----------------
* DESIGN-03-007 §Phase 1A "TA_CNMongoAdapter 详细设计" (1A.2)
* SPEC-03-007 §4 (canonical contract)
* RFC-03-007 §5 (collection scope)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Minimal structural types for the injected ``db`` handle
# ---------------------------------------------------------------------------


class _Collection(Protocol):
    """Minimal subset of a pymongo Collection that this adapter needs."""

    def find_one(self, filter: dict, *args: Any, **kwargs: Any) -> dict | None: ...
    def find(self, filter: dict, *args: Any, **kwargs: Any) -> Any: ...


class _Database(Protocol):
    """Minimal subset of a pymongo Database that this adapter needs."""

    def __getitem__(self, name: str) -> _Collection: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_yyyymmdd(date_str: str | None, *, field: str) -> str | None:
    """Validate public ``YYYY-MM-DD`` input and convert to TA-CN format.

    Phase 1A deliberately fails fast on non-canonical or impossible dates;
    silently passing malformed values into a MongoDB range query would look
    like a legitimate empty result and hide caller errors.
    """
    if date_str is None:
        return None
    if not isinstance(date_str, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string, got {date_str!r}")
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"{field} must be a valid YYYY-MM-DD date, got {date_str!r}"
        ) from exc
    if parsed.strftime("%Y-%m-%d") != date_str:
        raise ValueError(
            f"{field} must be a canonical YYYY-MM-DD date, got {date_str!r}"
        )
    return parsed.strftime("%Y%m%d")


def _validate_report_period(report_period: str | None) -> str | None:
    """Validate an optional TA-CN ``YYYYMMDD`` financial report period."""
    if report_period is None:
        return None
    if not isinstance(report_period, str):
        raise ValueError(
            f"report_period must be a YYYYMMDD string, got {report_period!r}"
        )
    try:
        parsed = datetime.strptime(report_period, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(
            f"report_period must be a valid YYYYMMDD date, got {report_period!r}"
        ) from exc
    if parsed.strftime("%Y%m%d") != report_period:
        raise ValueError(
            f"report_period must be a canonical YYYYMMDD date, got {report_period!r}"
        )
    return report_period


def _validate_limit(limit: int, *, field: str = "limit") -> int:
    """Require a non-negative integer; ``0`` means unlimited."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError(f"{field} must be a non-negative integer, got {limit!r}")
    return limit


def _list_of_docs(cursor: Any) -> list[dict]:
    """Materialize a Mongo cursor (or any iterable of dicts) into a list."""
    return [doc for doc in cursor]


def _sort_desc(field: str) -> list[tuple[str, int]]:
    """Return a ``[(field, -1)]`` sort spec for descending order."""
    return [(field, -1)]


def _sort_asc(field: str) -> list[tuple[str, int]]:
    """Return a ``[(field, 1)]`` sort spec for ascending order."""
    return [(field, 1)]


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class TA_CNMongoAdapter:
    """TA-CN MongoDB 只读 adapter.

    覆盖 8 个 TA-CN 生产集合，只做 find/find_one，不做写入。
    所有方法返回 list[dict] 或 dict（原始 MongoDB 文档），不做 canonical 映射
    （映射在 domain service 层完成）。返回 None 或空列表表示无数据。
    """

    DATABASE_NAME = "tradingagents"

    # Canonical collection names — kept as class attributes so tests and
    # factories can refer to them without stringly-typed drift.
    COLLECTION_STOCK_BASIC_INFO = "stock_basic_info"
    COLLECTION_MARKET_QUOTES = "market_quotes"
    COLLECTION_STOCK_DAILY_QUOTES = "stock_daily_quotes"
    COLLECTION_STOCK_FINANCIAL_DATA = "stock_financial_data"
    COLLECTION_STOCK_NEWS = "stock_news"
    COLLECTION_INDEX_BASIC_INFO = "index_basic_info"
    COLLECTION_INDEX_DAILY_QUOTES = "index_daily_quotes"
    COLLECTION_STOCK_SECTOR_INFO = "stock_sector_info"

    def __init__(self, db: Any) -> None:
        """注入已初始化的 pymongo Database 句柄。不做连接、不建索引。

        ``db`` may be any object that supports ``db[collection_name]``
        returning a cursor-bearing collection (e.g. pymongo
        ``Database``, a custom in-memory fake used by tests, etc.).
        """
        self._db = db

    # ── stock_basic_info ──────────────────────────────────────
    def get_stock_info(self, symbol: str, market: str = "CN") -> dict | None:
        """按 symbol 查询单只股票基础信息。返回原始文档或 None。"""
        if not symbol:
            return None
        coll = self._db[self.COLLECTION_STOCK_BASIC_INFO]
        return coll.find_one({"symbol": symbol, "market": market})

    def get_stock_list(
        self,
        market: str = "CN",
        status: str = "L",
        limit: int = 0,
    ) -> list[dict]:
        """查询股票列表。status='L' 仅上市。limit=0 表示不限。

        按 ``symbol`` 升序返回。若 ``status`` 为空字符串则不附加状态过滤。
        """
        _validate_limit(limit)
        coll = self._db[self.COLLECTION_STOCK_BASIC_INFO]
        query: dict = {"market": market}
        if status:
            query["status"] = status
        cursor = coll.find(query).sort(_sort_asc("symbol"))
        docs = _list_of_docs(cursor)
        if limit and len(docs) > limit:
            return docs[:limit]
        return docs

    # ── market_quotes ─────────────────────────────────────────
    def get_realtime_quotes(self, symbol: str) -> dict | None:
        """查询单只股票实时行情快照。返回原始文档或 None。"""
        if not symbol:
            return None
        coll = self._db[self.COLLECTION_MARKET_QUOTES]
        return coll.find_one({"symbol": symbol})

    # ── stock_daily_quotes ────────────────────────────────────
    def get_daily_bars(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> list[dict]:
        """查询日线行情。

        ``start_date`` / ``end_date`` 必须是 ``"YYYY-MM-DD"``；adapter
        校验后转换为 ``"YYYYMMDD"``。按 ``trade_date`` 降序（最新在前），
        至多返回 ``limit`` 条（``0`` 表示不限）。
        """
        _validate_limit(limit)
        if not symbol:
            return []
        coll = self._db[self.COLLECTION_STOCK_DAILY_QUOTES]
        query: dict = {"symbol": symbol}
        start = _to_yyyymmdd(start_date, field="start_date")
        end = _to_yyyymmdd(end_date, field="end_date")
        if start is not None or end is not None:
            trade_date_filter: dict = {}
            if start is not None:
                trade_date_filter["$gte"] = start
            if end is not None:
                trade_date_filter["$lte"] = end
            query["trade_date"] = trade_date_filter
        cursor = coll.find(query).sort(_sort_desc("trade_date"))
        docs = _list_of_docs(cursor)
        if limit and len(docs) > limit:
            return docs[:limit]
        return docs

    # ── stock_financial_data ──────────────────────────────────
    def get_financials(
        self,
        symbol: str,
        report_period: str | None = None,
    ) -> dict | None:
        """查询财务数据。

        ``report_period`` 格式 ``"YYYYMMDD"``（与 TA-CN
        ``stock_financial_data.report_period`` 存储格式一致）。
        返回原始嵌套文档（含 ``raw_data`` 内三条报表列表），由 service
        层根据 ``statement_type`` 提取。
        """
        period = _validate_report_period(report_period)
        if not symbol:
            return None
        coll = self._db[self.COLLECTION_STOCK_FINANCIAL_DATA]
        query: dict = {"symbol": symbol}
        if period is not None:
            query["report_period"] = period
        return coll.find_one(query)

    # ── stock_news ────────────────────────────────────────────
    def get_news(self, symbol: str, limit: int = 20) -> list[dict]:
        """查询个股新闻。按 ``publish_time`` 降序（最新在前）。"""
        _validate_limit(limit)
        if not symbol:
            return []
        coll = self._db[self.COLLECTION_STOCK_NEWS]
        cursor = coll.find({"symbol": symbol}).sort(_sort_desc("publish_time"))
        docs = _list_of_docs(cursor)
        if limit and len(docs) > limit:
            return docs[:limit]
        return docs

    # ── index_basic_info ──────────────────────────────────────
    def get_index_info(self, symbol: str) -> dict | None:
        """查询单个指数基础信息。"""
        if not symbol:
            return None
        coll = self._db[self.COLLECTION_INDEX_BASIC_INFO]
        return coll.find_one({"symbol": symbol})

    def get_index_list(self, market: str = "CN") -> list[dict]:
        """查询指数列表。按 ``symbol`` 升序。"""
        coll = self._db[self.COLLECTION_INDEX_BASIC_INFO]
        cursor = coll.find({"market": market}).sort(_sort_asc("symbol"))
        return _list_of_docs(cursor)

    # ── index_daily_quotes ────────────────────────────────────
    def get_index_daily_bars(
        self,
        symbol: str | None = None,
        sector_code: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> list[dict]:
        """查询指数/申万行业指数日线。

        支持按 ``symbol``（大盘指数）或 ``sector_code``（申万行业指数）
        查询。``sector_code`` 优先匹配 ``sector_code`` 字段；若不提供则
        退而匹配 ``code`` / ``symbol`` 字段。按 ``trade_date`` 降序，
        至多 ``limit`` 条。
        """
        _validate_limit(limit)
        coll = self._db[self.COLLECTION_INDEX_DAILY_QUOTES]
        query: dict = {}
        selector = sector_code or symbol
        if selector:
            query["$or"] = [
                {"sector_code": selector},
                {"symbol": selector},
                {"code": selector},
            ]
        start = _to_yyyymmdd(start_date, field="start_date")
        end = _to_yyyymmdd(end_date, field="end_date")
        if start is not None or end is not None:
            trade_date_filter: dict = {}
            if start is not None:
                trade_date_filter["$gte"] = start
            if end is not None:
                trade_date_filter["$lte"] = end
            query["trade_date"] = trade_date_filter
        cursor = coll.find(query).sort(_sort_desc("trade_date"))
        docs = _list_of_docs(cursor)
        if limit and len(docs) > limit:
            return docs[:limit]
        return docs

    # ── stock_sector_info ─────────────────────────────────────
    def get_stock_sector_info(
        self,
        full_symbol: str,
        classify_system: str | None = None,
    ) -> list[dict]:
        """查询个股行业分类。

        ``classify_system`` 默认 ``"SW"``（申万）。当 ``classify_system``
        为 ``None`` 或空字符串时，不附加 ``classify_system`` 过滤，
        返回该 ``full_symbol`` 的全部分类记录。
        """
        if not full_symbol:
            return []
        coll = self._db[self.COLLECTION_STOCK_SECTOR_INFO]
        query: dict = {"full_symbol": full_symbol}
        if classify_system:
            query["classify_system"] = classify_system
        cursor = coll.find(query).sort(_sort_asc("l1_code"))
        return _list_of_docs(cursor)

    def get_stocks_by_sector(
        self,
        l1_code: str,
        classify_system: str = "SW",
    ) -> list[dict]:
        """查询某申万一级行业下的全部个股。"""
        if not l1_code:
            return []
        coll = self._db[self.COLLECTION_STOCK_SECTOR_INFO]
        cursor = coll.find(
            {"l1_code": l1_code, "classify_system": classify_system}
        ).sort(_sort_asc("full_symbol"))
        return _list_of_docs(cursor)


__all__ = ["TA_CNMongoAdapter"]
