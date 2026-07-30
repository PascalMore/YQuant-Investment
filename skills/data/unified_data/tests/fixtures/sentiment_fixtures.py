"""Phase 3 P3-C canonical 22-field MarketSentimentSnapshot fixtures + LimitUpPoolRecord fixtures.

This fixture module provides:

* :func:`sample_market_sentiment_records` — two canonical 22-field offline
  ``dict`` payloads covering the two main scenarios a T3-C test suite
  needs:

      1. A normal trading day (modest limit-up / decline breadth, full
         field population including ``continuous_limit_up``,
         ``limit_up_pool``, ``hot_concepts``).
      2. An extreme bull scenario (large ``limit_up_count``,
         very high ``max_continuous_days``, dense ``continuous_limit_up``).

  All records comply with the Pascal canonical contract (RFC-03-014
  V0.16 / SPEC-03-014 V0.15 / DESIGN-03-014 V0.23 §3.3). The unique
  key is ``{market, snapshot_date, snapshot_time}``. The
  ``northbound_net_flow`` field is **always** ``None`` — Pascal C
  fail-stop — and the fixtures carry ``market_temperature: None``
  reflecting Pascal OQ-2 (no fabricated synthesis).

* :func:`sample_limit_up_pool_records` — two offline ``dict`` payloads
  that cover the two common limit-up shapes a T3-C test suite needs:

      1. A standard limit-up stock (``600519``) with full limit-up
         fields (封单金额 / 封成比 / 连板天数 / 涨停原因).
      2. A limit-down stock (``000001``) with limit-down status and no
         order data (the stock opened limit-down with minimal turnover).

The fixture deliberately stays lightweight: no real AKShare call, no
MongoDB DDL, no schema impact.
"""

from __future__ import annotations

from skills.data.unified_data import DataProvider  # noqa: F401  (kept for backwards compat)


# Canonical 22-field offline payloads (Pascal canonical contract).
#
# Both records carry the full canonical field set so downstream
# tests can exercise every field. ``northbound_net_flow`` is set to
# ``None`` per Pascal C — and ``from_dict`` will keep it ``None``
# regardless of source (Pascal C fail-stop). ``market_temperature``
# is ``None`` per Pascal OQ-2 (no fabricated formula).
_SAMPLE_MARKET_SENTIMENT_RECORDS: tuple[dict, ...] = (
    # Record 1: normal trading day (2026-07-21 close).
    {
        "market": "CN",
        "snapshot_date": "2026-07-21",
        "snapshot_time": "close",
        # 涨跌停数据 (含 ST)
        "limit_up_count": 42,
        "limit_down_count": 8,
        # 涨跌停数据 (不含 ST)
        "limit_up_count_ex_st": 38,
        "limit_down_count_ex_st": 7,
        # 全市场涨跌数据
        "advance_count": 3250,
        "decline_count": 1500,
        "flat_count": 250,
        "total_listed_count": 5000,
        # 指数与温度 (Pascal OQ-2 — temperature is None, no fabricated formula)
        "market_temperature": None,
        "total_turnover": 850_000_000_000.0,
        # 热门概念与连板
        "hot_concepts": ["AI", "白酒", "新能源"],
        "continuous_limit_up": [
            {"symbol": "600519", "days": 3, "reason": "白酒龙头"},
            {"symbol": "002415", "days": 2, "reason": "AI 概念"},
        ],
        "max_continuous_days": 3,
        # Pascal C — northbound_net_flow is permanently None
        "northbound_net_flow": None,
        # 涨停 / 跌停池
        "limit_up_pool": ["600519", "000001", "002415", "300750"],
        "limit_down_pool": ["002594"],
        # 元数据
        "fetched_at": "2026-07-21T15:30:00",
        "provider": "sentiment_stub",
        "raw_payload": {"source": "offline_fixture", "scenario": "normal"},
    },
    # Record 2: extreme bull scenario (2026-07-22 close).
    {
        "market": "CN",
        "snapshot_date": "2026-07-22",
        "snapshot_time": "close",
        # 涨跌停数据 (含 ST)
        "limit_up_count": 450,
        "limit_down_count": 5,
        # 涨跌停数据 (不含 ST)
        "limit_up_count_ex_st": 442,
        "limit_down_count_ex_st": 4,
        # 全市场涨跌数据
        "advance_count": 4800,
        "decline_count": 100,
        "flat_count": 100,
        "total_listed_count": 5000,
        # 指数与温度 (extreme bull — temperature still None per Pascal OQ-2)
        "market_temperature": None,
        "total_turnover": 1_500_000_000_000.0,
        # 热门概念与连板
        "hot_concepts": ["AI", "新能源", "军工", "半导体"],
        "continuous_limit_up": [
            {"symbol": "600519", "days": 7, "reason": "白酒龙头连续"},
            {"symbol": "002415", "days": 5, "reason": "AI 主线"},
            {"symbol": "300750", "days": 4, "reason": "新能源龙头"},
            {"symbol": "002594", "days": 3, "reason": "汽车链"},
        ],
        "max_continuous_days": 7,
        # Pascal C — northbound_net_flow is permanently None
        "northbound_net_flow": None,
        # 涨停 / 跌停池
        "limit_up_pool": [
            "600519",
            "000001",
            "002415",
            "300750",
            "002594",
            "600276",
        ],
        "limit_down_pool": [],
        # 元数据
        "fetched_at": "2026-07-22T15:30:00",
        "provider": "sentiment_stub",
        "raw_payload": {"source": "offline_fixture", "scenario": "extreme_bull"},
    },
)


# Canonical offline payloads — covers the two documented limit-up shapes.
_SAMPLE_LIMIT_UP_RECORDS: tuple[dict, ...] = (
    # Record 1: 600519 (limit-up, full fields)
    {
        "symbol": "600519",
        "market": "CN",
        "trade_date": "2026-07-22",
        "status": "limit_up",
        "limit_up_time": "09:30:05",
        "last_price": 150.25,
        "pct_chg": 10.0,
        "order_amount": 850_000_000.0,
        "turnover_amount": 120_000_000.0,
        "order_ratio": 7.08,
        "turnover_rate": 0.85,
        "consecutive_days": 3,
        "reason": "白酒板块强势+业绩预增",
        "market_cap": 188_700_000_000.0,
        "fetched_at": "2026-07-22T10:00:00",
        "provider": "limit_up_stub",
    },
    # Record 2: 000001 (limit-down, minimal fields)
    {
        "symbol": "000001",
        "market": "CN",
        "trade_date": "2026-07-22",
        "status": "limit_down",
        "limit_up_time": "09:25:00",
        "last_price": 8.50,
        "pct_chg": -10.0,
        "order_amount": 0.0,
        "turnover_amount": 5_000_000.0,
        "order_ratio": 0.0,
        "turnover_rate": 0.12,
        "consecutive_days": 1,
        "reason": "利空公告",
        "market_cap": 5_200_000_000.0,
        "fetched_at": "2026-07-22T10:00:00",
        "provider": "limit_up_stub",
    },
)


def sample_market_sentiment_records() -> list[dict]:
    """Return two canonical 22-field offline MarketSentimentSnapshot records (defensive copy).

    Each record carries the full Pascal canonical contract. Useful for
    exercising the dataclass schema, ``from_dict`` round-trip, and
    the persistence writer's ``{market, snapshot_date, snapshot_time}``
    unique key path.
    """
    return [dict(record) for record in _SAMPLE_MARKET_SENTIMENT_RECORDS]


def sample_limit_up_pool_records() -> list[dict]:
    """Return two canonical offline limit-up pool records (defensive copy)."""
    return [dict(record) for record in _SAMPLE_LIMIT_UP_RECORDS]


__all__ = [
    "sample_market_sentiment_records",
    "sample_limit_up_pool_records",
]