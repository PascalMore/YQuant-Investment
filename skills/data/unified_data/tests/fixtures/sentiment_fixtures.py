"""Limit-up pool fixtures for T3-P3C offline implementation tests (Phase 3 P3-C).

This fixture module provides:

* :func:`sample_limit_up_pool_records` — two offline ``dict`` payloads that
  cover the two common limit-up shapes a T3-P3C test suite needs:

    1. A standard limit-up stock (``600519``) with full limit-up fields
       (封单金额/封成比/连板天数/涨停原因).
    2. A limit-down stock (``000001``) with limit-down status and no
       order data (the stock opened limit-down with minimal turnover).

* :class:`StubLimitUpPoolProvider` — a minimal :class:`DataProvider`-compatible
  stub that advertises ``sentiment.limit_up_pool`` and returns the fixture
  records.

The fixture deliberately stays lightweight: no real AKShare call, no
MongoDB DDL, no schema impact.
"""

from __future__ import annotations

from typing import Any, Iterable

from skills.data.unified_data import DataProvider, Market


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


def sample_limit_up_pool_records() -> list[dict]:
    """Return two canonical offline limit-up pool records (defensive copy)."""
    return [dict(record) for record in _SAMPLE_LIMIT_UP_RECORDS]


__all__ = [
    "sample_limit_up_pool_records",
]
