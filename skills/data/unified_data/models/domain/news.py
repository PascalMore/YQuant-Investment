"""Canonical news item (Phase 1A).

:class:`NewsItem` maps to ``stock_news``. The collection does not
declare a unique-key in the TA-CN schema — documents are returned in
``publish_time`` descending order by the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NewsItem:
    """个股新闻 — ``stock_news`` canonical。"""

    symbol: str | None
    title: str
    content: str | None = None
    source: str | None = None
    publish_time: str | None = None
    sentiment: str | None = None
    category: str | None = None
    importance: str | None = None
    url: str | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "NewsItem":
        """从 ``stock_news`` 文档映射。缺失字段填 ``None``。"""
        if not isinstance(doc, dict):
            raise TypeError(
                f"NewsItem.from_ta_cn_doc expects dict, got {type(doc).__name__}"
            )
        symbol = doc.get("symbol")
        return cls(
            symbol=str(symbol) if symbol is not None else None,
            title=str(doc.get("title", "")),
            content=doc.get("content"),
            source=doc.get("source"),
            publish_time=doc.get("publish_time"),
            sentiment=doc.get("sentiment"),
            category=doc.get("category"),
            importance=doc.get("importance"),
            url=doc.get("url"),
        )


__all__ = ["NewsItem"]
