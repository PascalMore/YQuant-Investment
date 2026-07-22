"""Market-level sentiment snapshot domain object (Phase 3 P3-B / T3-B).

:class:`MarketSentimentSnapshot` is the canonical shape for the
``sentiment.market_snapshot`` capability (DESIGN-03-014 §3.3, abridged
to the T3-B offline scope). It is intentionally minimal — only the
fields the offline T3-B implementation needs to round-trip through
:mod:`mongomock` and the persistence writer's unique-key filter.

Scope (T3-B kanban task body):

* Required: ``market``, ``sentiment_type``, ``market_date``, ``score``,
  ``sample_size``, ``source``.
* Optional (defaulted): all other fields.
* No ``raw_payload`` (kept off the wire to avoid leaking provider
  internals).
* No ``snapshot_time`` granularity — V0.5 §3.3 supports it but the
  T3-B scope uses a single ``(market, sentiment_type, market_date)``
  triple.  ``sentiment_type`` keeps the uniqueness key expressive
  enough to coexist with future sub-aggregates (``market_sentiment``,
  ``breadth``, ``limit_up_temperature``, ...).

The dataclass is ``frozen=True, slots=True`` for immutability — matches
the canonical-object convention used by :class:`SecurityId` /
:class:`Capability` and avoids accidental mutation when records are
copied into service-layer return payloads.

``from_dict`` is deliberately permissive: every field defaults, no
``KeyError`` is raised on missing keys, and types are not enforced —
the canonical source of truth remains the persistence writer's
record schema, not the dataclass itself.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarketSentimentSnapshot:
    """Market-level sentiment snapshot (Phase 3 P3-B / T3-B offline).

    Each record represents a single sentiment aggregate for a market on
    a single calendar date. Consumers reach this object via
    :meth:`MarketSentimentService.get_market_sentiment_snapshot` (the
    P3-B implementation under ``services/sentiment_service.py``).

    The data is auxiliary research material — it does not constitute a
    trade instruction or investment recommendation.

    Attributes:
        market:          Market identifier (e.g. ``"CN"``).
        sentiment_type:  Which aggregate the record represents (e.g.
                         ``"market_sentiment"``, ``"breadth"``). The
                         canonical ``market.sentiment_snapshot``
                         capability is intentionally broader than a
                         single metric so future sub-aggregates can
                         share the same collection.
        market_date:     Calendar date the snapshot covers
                         (``"YYYY-MM-DD"``).
        score:           The aggregate score in the provider's native
                         units. Allowed range depends on
                         ``sentiment_type``; this dataclass does not
                         enforce it.
        sample_size:     Number of underlying observations the score
                         was derived from. Zero is allowed (e.g. a
                         null day); callers can choose to filter it
                         out.
        source:          Provider / source identifier (e.g.
                         ``"akshare"``, ``"stub"``). Empty string is
                         tolerated and treated as "unknown" by
                         downstream consumers.
        provider:        Concrete provider object name (matches the
                         ``source`` field in :class:`DataResult`). Same
                         semantics as :attr:`SectorClassification.datasource`.
        fetched_at:      ISO-8601 timestamp recorded by the provider.
        notes:           Free-form annotation field — kept tiny so it
                         fits inside MongoDB documents without
                         blowing up the index size. Optional.
        metadata:        Carries context the service / router may add
                         (``security_id`` placeholder, ``extra`` tags,
                         etc.). Not part of the unique key.
    """

    market: str
    sentiment_type: str
    market_date: str
    score: float
    sample_size: int
    source: str = ""
    provider: str = ""
    fetched_at: str | None = None
    notes: str | None = None
    metadata: dict[str, object] | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "MarketSentimentSnapshot":
        """Build a snapshot from a MongoDB-shaped ``dict``.

        Missing fields fall back to their declared defaults. ``None``
        inputs are coerced to empty strings for the required textual
        fields so downstream comparisons do not blow up on missing
        MongoDB documents.

        Args:
            data: MongoDB document / writer payload.

        Returns:
            A new :class:`MarketSentimentSnapshot` instance.
        """
        if not isinstance(data, dict):
            raise TypeError(
                "MarketSentimentSnapshot.from_dict expects a dict, "
                f"got {type(data).__name__}"
            )
        return cls(
            market=str(data.get("market") or ""),
            sentiment_type=str(data.get("sentiment_type") or ""),
            market_date=str(data.get("market_date") or ""),
            score=float(data.get("score") or 0.0),
            sample_size=int(data.get("sample_size") or 0),
            source=str(data.get("source") or ""),
            provider=str(data.get("provider") or ""),
            fetched_at=data.get("fetched_at"),
            notes=data.get("notes"),
            metadata=data.get("metadata"),
        )


@dataclass(frozen=True, slots=True)
class LimitUpPoolRecord:
    """涨停/跌停池个股记录 (Phase 3 P3-C / ``sentiment.limit_up_pool``).

    Each record represents a single stock that hit the daily limit-up
    (or limit-down) on a given trading day. Consumers reach this object
    via :meth:`MarketSentimentService.get_limit_up_pool` (the P3-C
    implementation under ``services/sentiment_service.py``).

    The business unique key is ``{market, symbol, trade_date}`` (per
    P3-C kanban task body, matching the per-stock pattern used by
    P3-B ``CapitalFlowRecord``). Multiple records for different stocks
    coexist in the same ``03_data_ud_market_sentiment_snapshot``
    collection alongside ``MarketSentimentSnapshot`` records.

    The data is auxiliary research material — it does not constitute a
    trade instruction or investment recommendation.

    Attributes:
        symbol:          Stock symbol (e.g. ``\"600519\"``).
        market:          Market identifier (e.g. ``\"CN\"``).
        trade_date:      Trading date (``\"YYYY-MM-DD\"``).
        status:          Limit-up status — ``\"limit_up\"`` or
                         ``\"limit_down\"``. Default ``\"limit_up\"``.
        limit_up_time:   Time the stock hit the limit
                         (``\"HH:MM:SS\"`` or ``\"close\"``).
        last_price:      Current / limit-up price.
        pct_chg:         Price change percentage (e.g. ``10.0``).
        order_amount:    封单金额 — order book size at the
                         limit price (yuan).
        turnover_amount: 成交额 — turnover (yuan).
        order_ratio:     封成比 — ``order_amount / turnover_amount``.
        turnover_rate:   换手率 — turnover rate (percent).
        consecutive_days: 连板天数 — consecutive limit-up days.
        reason:          涨停原因 — free-text reason annotation.
        market_cap:      流通市值 — float market cap (yuan).
        fetched_at:      ISO-8601 fetch timestamp.
        provider:        Data source identifier.
    """

    symbol: str  # (必填) 股票代码
    market: str  # (必填) 市场
    trade_date: str  # (必填) 交易日 YYYY-MM-DD

    # 涨跌停状态
    status: str = "limit_up"  # "limit_up" / "limit_down"

    # 涨停详情
    limit_up_time: str | None = None  # 涨停时间 "HH:MM:SS" 或 "close"
    last_price: float | None = None  # 最新价/涨停价
    pct_chg: float | None = None  # 涨幅 %

    # 封单数据
    order_amount: float | None = None  # 封单金额（元）
    turnover_amount: float | None = None  # 成交额（元）
    order_ratio: float | None = None  # 封成比（order_amount / turnover_amount）
    turnover_rate: float | None = None  # 换手率 %

    # 连板
    consecutive_days: int = 1  # 连板天数
    reason: str | None = None  # 涨停原因

    # 元数据
    market_cap: float | None = None  # 流通市值（元）
    fetched_at: str | None = None  # 数据获取时间 ISO-8601
    provider: str = ""  # 数据来源

    @classmethod
    def from_dict(cls, data: dict) -> "LimitUpPoolRecord":
        """Build a record from a MongoDB-shaped ``dict``.

        Missing fields fall back to their declared defaults. ``None``
        inputs are coerced to empty strings for the required textual
        fields so downstream comparisons do not blow up on missing
        MongoDB documents.

        Args:
            data: MongoDB document / writer payload.

        Returns:
            A new :class:`LimitUpPoolRecord` instance.
        """
        if not isinstance(data, dict):
            raise TypeError(
                "LimitUpPoolRecord.from_dict expects a dict, "
                f"got {type(data).__name__}"
            )
        return cls(
            symbol=str(data.get("symbol") or ""),
            market=str(data.get("market") or ""),
            trade_date=str(data.get("trade_date") or ""),
            status=str(data.get("status") or "limit_up"),
            limit_up_time=data.get("limit_up_time"),
            last_price=_safe_float(data.get("last_price")),
            pct_chg=_safe_float(data.get("pct_chg")),
            order_amount=_safe_float(data.get("order_amount")),
            turnover_amount=_safe_float(data.get("turnover_amount")),
            order_ratio=_safe_float(data.get("order_ratio")),
            turnover_rate=_safe_float(data.get("turnover_rate")),
            consecutive_days=int(data.get("consecutive_days") or 1),
            reason=data.get("reason"),
            market_cap=_safe_float(data.get("market_cap")),
            fetched_at=data.get("fetched_at"),
            provider=str(data.get("provider") or ""),
        )


def _safe_float(value: object) -> float | None:
    """Coerce ``value`` to float or return ``None``."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


__all__ = ["MarketSentimentSnapshot", "LimitUpPoolRecord"]