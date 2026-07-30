"""Market-level sentiment snapshot domain object (Phase 3 P3-C canonical).

:class:`MarketSentimentSnapshot` is the **Pascal canonical contract** for the
``sentiment.market_snapshot`` capability (RFC-03-014 V0.16 / SPEC-03-014
V0.15 / DESIGN-03-014 V0.23 §3.3). It is a 22-field full-market
multi-dimensional snapshot with the unique key
``{market, snapshot_date, snapshot_time}``.

Provenance
----------

Pascal 2026-07-30 ratified this 22-field schema as the canonical product
schema, replacing the earlier T3-B offline 10-field
``sentiment_type`` aggregation model (which used the unique key
``{market, sentiment_type, market_date}`` and ``frozen=True, slots=True``).

The earlier 10-field shape is **superseded**; the field names
``sentiment_type``, ``market_date``, ``score``, ``sample_size``,
``source``, ``notes``, ``metadata`` are no longer part of the canonical
contract. Any subsequent persistence write, Provider mapping, or new
test must use the 22-field schema. The 10-field offline implementation
was kept on disk by the same Pascal ruling (SPEC §12.bis.3) but is
removed in this migration — every code path through
:func:`from_dict` now produces the 22-field shape exclusively.

The dataclass is intentionally **not** ``frozen`` and not ``slots``
(SPEC §12.bis.1 / DESIGN §3.3) — the canonical shape is a mutable
dataclass so consumers can update optional fields after construction
(e.g. attach a ``provider`` / ``fetched_at`` post-init).

Pascal C — northbound fail-stop
-------------------------------

``northbound_net_flow`` is **permanently** ``None``. The fetch path
does not point at any real endpoint; the field is preserved for schema
completeness but never populated with a non-``None`` value. This is a
hard constraint (DESIGN §4.2.1, SPEC §14.4.5.2 Pascal C).

Pascal OQ-2 — temperature
------------------------

``market_temperature`` is allowed to be ``None``. The synthesis formula
is intentionally undefined — no fabricated formula, no derivation
frome.g. ``advance_count / (advance_count + decline_count)`` is
performed. The field is reserved for a future synthesis layer.

``limit_up_pool`` / ``limit_down_pool`` self-dedup invariant
-----------------------------------------------------------

``MarketSentimentSnapshot``'s ``limit_up_pool`` and ``limit_down_pool``
lists are self-deduped (a single stock does not appear twice in the
same document). Cross-document uniqueness is guaranteed by the
``P3PersistenceWriter`` upsert via the canonical
``{market, snapshot_date, snapshot_time}`` business key.

``from_dict``
-------------

The constructor is deliberately permissive: every field defaults, no
``KeyError`` is raised on missing keys, and types are not enforced
(``None`` and ``""`` are tolerated for the textual unique-key
components so downstream comparisons do not blow up on missing Mongo
documents). The canonical source of truth remains the persistence
writer's record schema, not the dataclass itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MarketSentimentSnapshot:
    """Market-level sentiment snapshot (Phase 3 P3-C canonical, 22 fields).

    Each record represents a single full-market sentiment / temperature
    snapshot at one observation time point. Consumers reach this object
    via :meth:`MarketSentimentService.get_market_sentiment_snapshot`
    (the P3-C implementation under ``services/sentiment_service.py``).

    Unique business key (RFC/SPEC/DESIGN §3.3):
    ``{market, snapshot_date, snapshot_time}``.

    Attributes:
        snapshot_date:             Calendar date the snapshot covers
            (``"YYYY-MM-DD"``).
        snapshot_time:             Observation time (``"HH:MM:SS"`` or
            ``"close"``).
        market:                    Market identifier (e.g. ``"CN"``).
        limit_up_count:            涨停家数，含 ST。
        limit_down_count:          跌停家数，含 ST。
        limit_up_count_ex_st:      涨停家数（不含 ST），Provider 待验证。
        limit_down_count_ex_st:    跌停家数（不含 ST），Provider 待验证。
        advance_count:             全市场上涨家数。
        decline_count:             全市场下跌家数。
        flat_count:                全市场平盘家数。
        total_listed_count:        全市场上市公司总数（日级）。
        market_temperature:        市场温度 0-100。**Pascal OQ-2 允许
            None**，不强制合成，不编造公式。
        total_turnover:            全市场成交额（元）。
        hot_concepts:              当日热门概念列表。
        continuous_limit_up:       连板股票列表，每条 ``dict`` 含
            ``symbol`` / ``days`` / ``reason``。
        max_continuous_days:       当日最大连板天数，基于
            ``continuous_limit_up`` 派生。
        northbound_net_flow:       北向资金净流入（元）。**Pascal C 恒
            None**，fetch 路径不指向真实 endpoint。
        limit_up_pool:             涨停股票代码列表（与独立
            ``sentiment.limit_up_pool`` capability 共存边界见
            DESIGN §3.3）。
        limit_down_pool:           跌停股票代码列表。
        fetched_at:                数据获取时间（ISO-8601）。
        provider:                  数据来源标识，如 ``"akshare"``。
        raw_payload:               原始 Provider 返回（调试 / 审计用，
            不用于生产查询路径）。

    The data is auxiliary research material — it does not constitute a
    trade instruction or investment recommendation.
    """

    # Required unique-key fields (positional, no default).
    snapshot_date: str
    snapshot_time: str

    # Market (defaulted to CN).
    market: str = "CN"

    # 涨跌停数据 (含 ST)
    limit_up_count: int = 0
    limit_down_count: int = 0

    # 涨跌停数据 (不含 ST，可选)
    limit_up_count_ex_st: int | None = None
    limit_down_count_ex_st: int | None = None

    # 全市场涨跌数据
    advance_count: int = 0
    decline_count: int = 0
    flat_count: int = 0

    # 全市场总数 (可选)
    total_listed_count: int | None = None

    # 指数与温度
    # market_temperature: Pascal OQ-2 — 允许 None，无已确认公式，禁止编造。
    market_temperature: float | None = None
    total_turnover: float | None = None

    # 热门概念与连板
    hot_concepts: list[str] | None = None
    continuous_limit_up: list[dict] | None = None
    max_continuous_days: int | None = None

    # 北向资金（Pascal C — 恒 None）
    northbound_net_flow: float | None = None

    # 涨停 / 跌停池（可选：若单独提供 limit_up_pool capability，本字段可为空）
    limit_up_pool: list[str] | None = None
    limit_down_pool: list[str] | None = None

    # 元数据
    fetched_at: str | None = None
    provider: str = ""
    raw_payload: dict | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "MarketSentimentSnapshot":
        """Build a snapshot from a MongoDB-shaped ``dict``.

        Missing fields fall back to declared defaults. ``None`` inputs
        are coerced to empty strings for the required textual fields
        so downstream comparisons do not blow up on missing Mongo
        documents.

        **Pascal C — northbound fail-stop**: even if the source dict
        supplies a numeric ``northbound_net_flow``, the resulting
        snapshot keeps it ``None``. This is a hard constraint.

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
            snapshot_date=str(data.get("snapshot_date", "") or ""),
            snapshot_time=str(data.get("snapshot_time", "") or ""),
            market=str(data.get("market", "CN") or "CN"),
            limit_up_count=int(data.get("limit_up_count", 0) or 0),
            limit_down_count=int(data.get("limit_down_count", 0) or 0),
            limit_up_count_ex_st=data.get("limit_up_count_ex_st"),
            limit_down_count_ex_st=data.get("limit_down_count_ex_st"),
            advance_count=int(data.get("advance_count", 0) or 0),
            decline_count=int(data.get("decline_count", 0) or 0),
            flat_count=int(data.get("flat_count", 0) or 0),
            total_listed_count=data.get("total_listed_count"),
            # Pascal OQ-2 — temperature is allowed None; no fabrication.
            market_temperature=data.get("market_temperature"),
            total_turnover=data.get("total_turnover"),
            hot_concepts=data.get("hot_concepts"),
            continuous_limit_up=data.get("continuous_limit_up"),
            max_continuous_days=data.get("max_continuous_days"),
            # Pascal C — northbound_net_flow is permanently None.
            # Even if upstream supplies a number, do not propagate it.
            northbound_net_flow=None,
            limit_up_pool=_stable_dedup(data.get("limit_up_pool")),
            limit_down_pool=_stable_dedup(data.get("limit_down_pool")),
            fetched_at=data.get("fetched_at"),
            provider=str(data.get("provider", "") or ""),
            raw_payload=data.get("raw_payload"),
        )


def _stable_dedup(values: list[str] | None) -> list[str] | None:
    """Return a first-seen-order copy without duplicates, preserving nullability."""
    if values is None:
        return None
    return list(dict.fromkeys(values))


@dataclass
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
        symbol:          Stock symbol (e.g. ``"600519"``).
        market:          Market identifier (e.g. ``"CN"``).
        trade_date:      Trading date (``"YYYY-MM-DD"``).
        status:          Limit-up status — ``"limit_up"`` or
                         ``"limit_down"``. Default ``"limit_up"``.
        limit_up_time:   Time the stock hit the limit
                         (``"HH:MM:SS"`` or ``"close"``).
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