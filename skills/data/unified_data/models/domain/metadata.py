"""Canonical metadata objects (Phase 1A).

Two dataclasses map to TA-CN ``stock_basic_info`` and
``index_basic_info`` respectively:

* :class:`StockInfo`   — single stock basic information record.
* :class:`IndexInfo`   — single index basic information record.
"""

from __future__ import annotations

from dataclasses import dataclass


def _f(value: object, *, field: str) -> float | None:
    """Coerce a present numeric value to ``float`` or fail loudly."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric, got bool")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be numeric, got {value!r}") from exc
    raise TypeError(f"{field} must be numeric, got {type(value).__name__}")


@dataclass
class StockInfo:
    """股票基础信息 — ``stock_basic_info`` canonical。"""

    symbol: str
    full_symbol: str
    name: str
    industry: str | None = None
    area: str | None = None
    total_mv: float | None = None
    circ_mv: float | None = None
    pe: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    pb_mrq: float | None = None
    roe: float | None = None
    list_date: str | None = None
    status: str | None = None
    market_info: dict | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "StockInfo":
        """从 ``stock_basic_info`` 文档映射。"""
        if not isinstance(doc, dict):
            raise TypeError(
                f"StockInfo.from_ta_cn_doc expects dict, got {type(doc).__name__}"
            )
        return cls(
            symbol=str(doc.get("symbol", "")),
            full_symbol=str(doc.get("full_symbol", "")),
            name=str(doc.get("name", "")),
            industry=doc.get("industry"),
            area=doc.get("area"),
            total_mv=_f(doc.get("total_mv"), field="total_mv"),
            circ_mv=_f(doc.get("circ_mv"), field="circ_mv"),
            pe=_f(doc.get("pe"), field="pe"),
            pe_ttm=_f(doc.get("pe_ttm"), field="pe_ttm"),
            pb=_f(doc.get("pb"), field="pb"),
            pb_mrq=_f(doc.get("pb_mrq"), field="pb_mrq"),
            roe=_f(doc.get("roe"), field="roe"),
            list_date=doc.get("list_date"),
            status=doc.get("status"),
            market_info=doc.get("market_info"),
        )


@dataclass
class IndexInfo:
    """指数基础信息 — ``index_basic_info`` canonical。"""

    symbol: str
    full_symbol: str
    name: str
    fullname: str | None = None
    market: str | None = None
    publisher: str | None = None
    category: str | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "IndexInfo":
        """从 ``index_basic_info`` 文档映射。"""
        if not isinstance(doc, dict):
            raise TypeError(
                f"IndexInfo.from_ta_cn_doc expects dict, got {type(doc).__name__}"
            )
        return cls(
            symbol=str(doc.get("symbol", "")),
            full_symbol=str(doc.get("full_symbol", "")),
            name=str(doc.get("name", "")),
            fullname=doc.get("fullname"),
            market=doc.get("market"),
            publisher=doc.get("publisher"),
            category=doc.get("category"),
        )


__all__ = ["StockInfo", "IndexInfo"]
