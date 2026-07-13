"""Canonical market data objects (Phase 1A).

Three dataclasses map to the corresponding TA-CN MongoDB collections:

* :class:`RealtimeQuote`        — ``market_quotes``
* :class:`DailyBar`             — ``stock_daily_quotes``
* :class:`IndexDailyBar`        — ``index_daily_quotes``

All objects provide a ``from_ta_cn_doc()`` classmethod that performs a
lenient (``doc.get(field)``) mapping from the raw MongoDB document.
Missing fields default to ``None``; the mapping never raises ``KeyError``.

Date fields are stored as ``str`` to match the TA-CN storage format
(``"YYYYMMDD"``), with no Python ``date`` / ``datetime`` conversion.
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
class RealtimeQuote:
    """实时行情快照 — ``market_quotes`` canonical."""

    symbol: str
    current_price: float | None
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    pre_close: float | None = None
    volume: float | None = None
    amount: float | None = None
    update_time: str | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "RealtimeQuote":
        """从 ``market_quotes`` 文档映射。

        ``current_price`` fallback to ``close``；``change_percent``
        fallback to ``pct_chg``；``update_time`` fallback to
        ``updated_at`` / ``timestamp``。
        """
        if not isinstance(doc, dict):
            raise TypeError(
                f"RealtimeQuote.from_ta_cn_doc expects dict, got {type(doc).__name__}"
            )
        current_price = doc.get("current_price")
        if current_price is None:
            current_price = doc.get("close")
        change_percent = doc.get("change_percent")
        if change_percent is None:
            change_percent = doc.get("pct_chg")
        update_time = doc.get("update_time")
        if update_time is None:
            update_time = doc.get("updated_at")
        if update_time is None:
            update_time = doc.get("timestamp")
        return cls(
            symbol=str(doc.get("symbol", "")),
            current_price=_f(current_price, field="current_price"),
            change=_f(doc.get("change"), field="change"),
            change_percent=_f(change_percent, field="change_percent"),
            open=_f(doc.get("open"), field="open"),
            high=_f(doc.get("high"), field="high"),
            low=_f(doc.get("low"), field="low"),
            pre_close=_f(doc.get("pre_close"), field="pre_close"),
            volume=_f(doc.get("volume"), field="volume"),
            amount=_f(doc.get("amount"), field="amount"),
            update_time=str(update_time) if update_time is not None else None,
        )


@dataclass
class DailyBar:
    """日线行情 — ``stock_daily_quotes`` canonical."""

    symbol: str
    trade_date: str              # 'YYYY-MM-DD' or 'YYYYMMDD'
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    pre_close: float | None = None
    change: float | None = None
    pct_chg: float | None = None
    volume: float | None = None
    amount: float | None = None
    turnover_rate: float | None = None
    volume_ratio: float | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "DailyBar":
        """从 ``stock_daily_quotes`` 文档映射。

        ``volume`` fallback to ``vol``。``trade_date`` 直接透传（保留
        ``"YYYYMMDD"`` 字符串）。
        """
        if not isinstance(doc, dict):
            raise TypeError(
                f"DailyBar.from_ta_cn_doc expects dict, got {type(doc).__name__}"
            )
        volume = doc.get("volume")
        if volume is None:
            volume = doc.get("vol")
        return cls(
            symbol=str(doc.get("symbol", "")),
            trade_date=str(doc.get("trade_date", "")),
            open=_f(doc.get("open"), field="open"),
            high=_f(doc.get("high"), field="high"),
            low=_f(doc.get("low"), field="low"),
            close=_f(doc.get("close"), field="close"),
            pre_close=_f(doc.get("pre_close"), field="pre_close"),
            change=_f(doc.get("change"), field="change"),
            pct_chg=_f(doc.get("pct_chg"), field="pct_chg"),
            volume=_f(volume, field="volume"),
            amount=_f(doc.get("amount"), field="amount"),
            turnover_rate=_f(doc.get("turnover_rate"), field="turnover_rate"),
            volume_ratio=_f(doc.get("volume_ratio"), field="volume_ratio"),
        )


@dataclass
class IndexDailyBar:
    """指数/行业指数日线 — ``index_daily_quotes`` canonical."""

    symbol: str
    trade_date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    pct_chg: float | None = None
    volume: float | None = None
    amount: float | None = None
    data_source: str = ""

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "IndexDailyBar":
        """从 ``index_daily_quotes`` 文档映射。

        ``symbol`` fallback to ``sector_code`` / ``code``。``volume``
        fallback to ``vol``。
        """
        if not isinstance(doc, dict):
            raise TypeError(
                f"IndexDailyBar.from_ta_cn_doc expects dict, got {type(doc).__name__}"
            )
        symbol = doc.get("symbol")
        if symbol is None:
            symbol = doc.get("sector_code")
        if symbol is None:
            symbol = doc.get("code")
        volume = doc.get("volume")
        if volume is None:
            volume = doc.get("vol")
        return cls(
            symbol=str(symbol if symbol is not None else ""),
            trade_date=str(doc.get("trade_date", "")),
            open=_f(doc.get("open"), field="open"),
            high=_f(doc.get("high"), field="high"),
            low=_f(doc.get("low"), field="low"),
            close=_f(doc.get("close"), field="close"),
            pct_chg=_f(doc.get("pct_chg"), field="pct_chg"),
            volume=_f(volume, field="volume"),
            amount=_f(doc.get("amount"), field="amount"),
            data_source=str(doc.get("source", "")),
        )


__all__ = ["RealtimeQuote", "DailyBar", "IndexDailyBar"]
