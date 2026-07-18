"""Shared constants and fixtures for the Phase 1C E2E test suite.

Fixture-only — no ``TestClass`` definitions live here. Each scenario
module (``test_e2e_scene_*.py``) imports constants and fixtures from
this file to keep test classes <= 300 lines per file
(DESIGN-03-010 §3.9).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import mongomock
import pytest

from skills.data.unified_data import (
    CacheManager,
    DataResult,
    LocalMongoAdapter,
    Market,
    ProviderError,
    ProviderRegistry,
    SecurityId,
)

from skills.data.unified_data.tests.conftest import FakeProvider, FakeTA_CNAdapter


# Capability + project-root constants (DESIGN-03-010 §4.1)
KLINE_CAP = "market_data.kline_daily"
INDEX_LIST_CAP = "metadata.index_list"
INDEX_DAILY_CAP = "market_data.index_daily"

# Project root used by Scene 7's coverage subprocess.
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
)


# Database / registry fixtures ----------------------------------------------------


def _make_db() -> Any:
    """Fresh mongomock database for one test method."""
    return mongomock.MongoClient().get_database("tradingagents")


@pytest.fixture
def e2e_db() -> Any:
    """Independent mongomock database per test method."""
    return _make_db()


@pytest.fixture
def e2e_registry() -> ProviderRegistry:
    """Empty :class:`ProviderRegistry` per test method.

    Tests that need providers must call ``register(...)`` explicitly
    inside the test body.
    """
    return ProviderRegistry()


# TA-CN adapter fixtures ---------------------------------------------------------


@pytest.fixture
def e2e_ta_cn_miss() -> FakeTA_CNAdapter:
    """TA-CN adapter with empty collections."""
    return FakeTA_CNAdapter(collections={})


@pytest.fixture
def e2e_ta_cn_with_kline(cn_maotai: SecurityId) -> FakeTA_CNAdapter:
    """TA-CN adapter pre-populated with one ``stock_daily_quotes`` row.

    Used by Scene 5 (force_refresh) to verify Step 1 is **bypassed**
    when ``force_refresh=True``.
    """
    return FakeTA_CNAdapter(
        collections={
            "stock_daily_quotes": [
                {
                    "symbol": cn_maotai.symbol,
                    "trade_date": "20260713",
                    "open": 1600,
                    "close": 1620,
                }
            ]
        }
    )


@pytest.fixture
def e2e_ta_cn_with_index() -> FakeTA_CNAdapter:
    """TA-CN adapter carrying both ``index_basic_info`` and
    ``index_daily_quotes`` for Scene 6 (E2E-601..604) dual-path coverage.
    """
    return FakeTA_CNAdapter(
        collections={
            "index_basic_info": [
                {"symbol": "000300", "full_symbol": "000300.SH",
                 "name": "沪深300", "market": "SH"},
                {"symbol": "000905", "full_symbol": "000905.SH",
                 "name": "中证500", "market": "SH"},
            ],
            "index_daily_quotes": [
                {"sector_code": "000300", "trade_date": "20260701",
                 "close": 4000.0, "pct_chg": 0.5},
                {"sector_code": "000300", "trade_date": "20260702",
                 "close": 4010.0, "pct_chg": 0.25},
            ],
        }
    )


# External provider fixtures ------------------------------------------------------


@pytest.fixture
def e2e_tushare_ok() -> FakeProvider:
    """External Tushare provider with a non-empty kline payload."""
    return FakeProvider(
        name="tushare",
        payload={
            "close": [1500, 1510],
            "open": [1490, 1500],
            "trade_date": ["20260701", "20260702"],
        },
        capabilities={KLINE_CAP, INDEX_LIST_CAP, INDEX_DAILY_CAP},
        markets={Market.CN},
    )


@pytest.fixture
def e2e_tushare_index_list_ok() -> FakeProvider:
    """External Tushare provider for ``metadata.index_list``."""
    return FakeProvider(
        name="tushare",
        payload=[
            {"symbol": "000300", "full_symbol": "000300.SH",
             "name": "沪深300", "market": "SH"}
        ],
        capabilities={KLINE_CAP, INDEX_LIST_CAP, INDEX_DAILY_CAP},
        markets={Market.CN},
    )


@pytest.fixture
def e2e_tushare_index_daily_ok() -> FakeProvider:
    """External Tushare provider for ``market_data.index_daily``."""
    return FakeProvider(
        name="tushare",
        payload=[
            {"sector_code": "000300", "trade_date": "20260701",
             "close": 4000.0, "pct_chg": 0.5}
        ],
        capabilities={KLINE_CAP, INDEX_LIST_CAP, INDEX_DAILY_CAP},
        markets={Market.CN},
    )


@pytest.fixture
def e2e_tushare_fail() -> FakeProvider:
    """External Tushare provider that raises ``ProviderError`` on every fetch.

    Deterministic error text ``"tushare rate limit"`` matches the
    Router's trace format ``"<name>(error: <message>)"`` so Scene 3
    and Scene 4 can assert exact trace equality (SPEC-03-010 §6.1.1).
    """
    return FakeProvider(
        name="tushare",
        raise_on_fetch=ProviderError("tushare rate limit"),
        capabilities={KLINE_CAP},
        markets={Market.CN},
    )


@pytest.fixture
def e2e_akshare_ok() -> FakeProvider:
    """External AKShare provider with a kline payload distinct from Tushare.

    Close values ``[2500, 2510]`` differ from Tushare's ``[1500, 1510]``
    so the data-source can be proven by the payload's contents.
    """
    return FakeProvider(
        name="akshare",
        payload={
            "close": [2500, 2510],
            "open": [2490, 2500],
            "trade_date": ["20260701", "20260702"],
        },
        capabilities={KLINE_CAP},
        markets={Market.CN},
    )


@pytest.fixture
def e2e_akshare_fail() -> FakeProvider:
    """External AKShare provider that raises ``ProviderError`` on every fetch.

    Deterministic error text ``"akshare down"`` matches Scene 4's
    exact trace assertion (SPEC-03-010 §6.1.1).
    """
    return FakeProvider(
        name="akshare",
        raise_on_fetch=ProviderError("akshare down"),
        capabilities={KLINE_CAP},
        markets={Market.CN},
    )


# Cache + materialized adapter fixtures (Scene 2, Scene 5 prepolulation) --------


@pytest.fixture
def e2e_prepop_cache(e2e_db: Any) -> CacheManager:
    """:class:`CacheManager` bound to ``e2e_db`` for prepopulation."""
    return CacheManager(mongo_db=e2e_db)


@pytest.fixture
def e2e_prepop_local(e2e_db: Any) -> LocalMongoAdapter:
    """:class:`LocalMongoAdapter` bound to ``e2e_db`` for prepopulation."""
    return LocalMongoAdapter(mongo_db=e2e_db)


# Cached DataResult factory ------------------------------------------------------


def make_cached_result(
    security_id: SecurityId,
    *,
    data: Any,
    provider: str,
    freshness: str = "cached",
    source_trace: list[str] | None = None,
) -> DataResult:
    """Build a :class:`DataResult` for ``CacheManager.put`` /
    ``LocalMongoAdapter.put`` prepopulation.

    ``freshness`` is a ``FreshnessLabel`` Literal at runtime; the
    ``str`` annotation keeps the helper callable with any canonical
    label.
    """
    return DataResult(
        data=data,
        security_id=security_id,
        domain="market_data",
        operation="kline_daily",
        provider=provider,
        fetched_at=datetime.utcnow(),
        source_trace=source_trace if source_trace is not None else ["tushare(ok)"],
        freshness=freshness,  # type: ignore[arg-type]
    )