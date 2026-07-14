"""End-to-end tests for Unified Data Layer (Phase 1C).

Phase 1C is the **validation layer** of the Unified Data Layer — not a
new data capability layer. These tests reproduce the full internal-first
chain end-to-end:

    Step 1: TA-CN adapter (internal)
        →  Step 2: LocalMongoAdapter (UD materialised layer)
            →  Step 3: CacheManager (Query Cache)
                →  Step 4: external fallback chain

All tests use :mod:`mongomock` for the persistence/cache layer and the
existing ``FakeProvider`` / ``FakeTA_CNAdapter`` from
``tests/data/unified_data/conftest.py``. No real MongoDB, no real
external API calls.

Test inventory (7 TestClass × 16 test methods, per
DESIGN-03-010 §3.2 / SPEC-03-010 §3):

* Scene 1 (E2E-101..104): all miss + external success → write →
  subsequent hit on materialised layer
* Scene 2 (E2E-201): Cache hit → zero external calls
* Scene 3 (E2E-301): provider A fails → B succeeds (fallback chain)
* Scene 4 (E2E-401/402): all providers fail → ``DataResult.error`` with
  full trace
* Scene 5 (E2E-501..503): ``force_refresh`` skips Step 1/2/3
* Scene 6 (E2E-601..604): index dual path (internal hit + external
  fallback) — covers ``metadata.index_list`` and
  ``market_data.index_daily``. ``stock_sector_info`` is **out of scope**
  per Pascal's Path A decision (DESIGN-03-010 §3.5.6 OQ-01).
* Scene 7 (E2E-701/702): coverage gate (``--fail-under=60``)

Implementation discipline
-------------------------
* No production code changes — the file is **read-only** with respect
  to ``router.py`` / ``cache_manager.py`` / ``local_mongo_adapter.py``
  / ``conftest.py``.
* No real MongoDB or external API calls.
* No new pip dependencies; uses ``mongomock`` (already in dev deps)
  and ``coverage`` (already installed in ``.venv``).
* Each TestClass is independently runnable and uses isolated
  :func:`pytest.fixture` state.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from typing import Any

import mongomock
import pytest

from skills.data.unified_data import (
    CacheManager,
    DataResult,
    DataRouter,
    LocalMongoAdapter,
    Market,
    ProviderError,
    ProviderRegistry,
    SecurityId,
    UnifiedDataConfig,
)
from tests.data.unified_data.conftest import FakeProvider, FakeTA_CNAdapter


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KLINE_CAP = "market_data.kline_daily"
INDEX_LIST_CAP = "metadata.index_list"
INDEX_INFO_CAP = "metadata.index_info"
INDEX_DAILY_CAP = "market_data.index_daily"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_db() -> Any:
    """Create a fresh mongomock database for one test method."""
    return mongomock.MongoClient().get_database("tradingagents")


@pytest.fixture
def e2e_db() -> Any:
    """Independent mongomock database per test method."""
    return _make_db()


@pytest.fixture
def e2e_registry() -> ProviderRegistry:
    """Empty ProviderRegistry per test method."""
    return ProviderRegistry()


@pytest.fixture
def e2e_ta_cn_miss() -> FakeTA_CNAdapter:
    """TA-CN adapter with empty collections (every capability returns [])."""
    return FakeTA_CNAdapter(collections={})


@pytest.fixture
def e2e_ta_cn_with_kline(cn_maotai: SecurityId) -> FakeTA_CNAdapter:
    """TA-CN adapter with one ``stock_daily_quotes`` row for ``cn_maotai``.

    Used to verify ``force_refresh`` correctly **bypasses** Step 1.
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
    """TA-CN adapter with both ``index_basic_info`` and ``index_daily_quotes``.

    Used by Scene 6 (E2E-601..604) for the index dual-path coverage.
    """
    return FakeTA_CNAdapter(
        collections={
            "index_basic_info": [
                {
                    "symbol": "000300",
                    "full_symbol": "000300.SH",
                    "name": "沪深300",
                    "market": "SH",
                },
                {
                    "symbol": "000905",
                    "full_symbol": "000905.SH",
                    "name": "中证500",
                    "market": "SH",
                },
            ],
            "index_daily_quotes": [
                {
                    "sector_code": "000300",
                    "trade_date": "20260701",
                    "close": 4000.0,
                    "pct_chg": 0.5,
                },
                {
                    "sector_code": "000300",
                    "trade_date": "20260702",
                    "close": 4010.0,
                    "pct_chg": 0.25,
                },
            ],
        }
    )


@pytest.fixture
def e2e_tushare_ok() -> FakeProvider:
    """External Tushare provider that returns a non-empty kline payload."""
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
    """External Tushare provider that returns an index_list payload."""
    return FakeProvider(
        name="tushare",
        payload=[
            {
                "symbol": "000300",
                "full_symbol": "000300.SH",
                "name": "沪深300",
                "market": "SH",
            }
        ],
        capabilities={KLINE_CAP, INDEX_LIST_CAP, INDEX_DAILY_CAP},
        markets={Market.CN},
    )


@pytest.fixture
def e2e_tushare_index_daily_ok() -> FakeProvider:
    """External Tushare provider that returns an index_daily payload."""
    return FakeProvider(
        name="tushare",
        payload=[
            {
                "sector_code": "000300",
                "trade_date": "20260701",
                "close": 4000.0,
                "pct_chg": 0.5,
            }
        ],
        capabilities={KLINE_CAP, INDEX_LIST_CAP, INDEX_DAILY_CAP},
        markets={Market.CN},
    )


@pytest.fixture
def e2e_tushare_fail() -> FakeProvider:
    """External Tushare provider that raises on every fetch."""
    return FakeProvider(
        name="tushare",
        raise_on_fetch=ProviderError("tushare rate limit"),
        capabilities={KLINE_CAP},
        markets={Market.CN},
    )


@pytest.fixture
def e2e_akshare_ok() -> FakeProvider:
    """External AKShare provider that returns a non-empty kline payload.

    Payload values differ from ``e2e_tushare_ok`` so tests can assert on
    the data source.
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
    """External AKShare provider that raises on every fetch."""
    return FakeProvider(
        name="akshare",
        raise_on_fetch=ProviderError("akshare down"),
        capabilities={KLINE_CAP},
        markets={Market.CN},
    )


# ---------------------------------------------------------------------------
# Scene 1: all miss + external success + write + subsequent hit on Step 2
# ---------------------------------------------------------------------------


class TestE2EScene1_AllMissExternalSuccess:
    """Reproduce the all-miss path: TA-CN empty → Step 2 miss → Step 3
    miss → external success → materialised write → cache write → next
    query hits the materialised layer.
    """

    def _build_router(
        self,
        registry: ProviderRegistry,
        ta_cn: FakeTA_CNAdapter,
        db: Any,
    ) -> DataRouter:
        return DataRouter(
            registry,
            ta_cn_adapter=ta_cn,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=db),
            cache_manager=CacheManager(mongo_db=db),
        )

    def test_returns_external_data(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-101: full chain returns external provider data on first hit."""
        e2e_registry.register(e2e_tushare_ok)
        router = self._build_router(e2e_registry, e2e_ta_cn_miss, e2e_db)

        result = router.query("market_data", "kline_daily", cn_maotai)

        assert result.provider == "tushare"
        assert result.data == {
            "close": [1500, 1510],
            "open": [1490, 1500],
            "trade_date": ["20260701", "20260702"],
        }
        # Full chain in trace order:
        # TA-CN empty → Step 2 miss → Step 3 miss → external ok
        assert result.source_trace == [
            "ta_cn_internal(empty)",
            "ud_materialized(miss)",
            "cache(miss)",
            "tushare(ok)",
        ]
        assert result.freshness != "empty"
        assert result.warnings == []

    def test_materialized_written(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-102: after a successful external hit, Step 2 holds the data."""
        e2e_registry.register(e2e_tushare_ok)
        router = self._build_router(e2e_registry, e2e_ta_cn_miss, e2e_db)
        router.query("market_data", "kline_daily", cn_maotai)

        # Build a fresh adapter against the same db to verify the write
        # persisted (LocalMongoAdapter is stateless beyond the DB handle).
        adapter = LocalMongoAdapter(mongo_db=e2e_db)
        got = adapter.get(cn_maotai, "market_data", "kline_daily", {})

        assert got is not None
        assert got.provider == "ud_materialized"
        assert got.data == {
            "close": [1500, 1510],
            "open": [1490, 1500],
            "trade_date": ["20260701", "20260702"],
        }

    def test_cache_written(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-103: after a successful external hit, Step 3 cache holds data."""
        e2e_registry.register(e2e_tushare_ok)
        router = self._build_router(e2e_registry, e2e_ta_cn_miss, e2e_db)
        router.query("market_data", "kline_daily", cn_maotai)

        cache = CacheManager(mongo_db=e2e_db)
        got = cache.get(cn_maotai, "market_data", "kline_daily", {})

        assert got is not None
        assert got.freshness == "cached"
        # Original provider name is preserved on the cached entry.
        assert got.provider == "tushare"

    def test_subsequent_hit_materialized(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-104: second query with same args hits Step 2 (no external call)."""
        e2e_registry.register(e2e_tushare_ok)
        router = self._build_router(e2e_registry, e2e_ta_cn_miss, e2e_db)

        # Warm the cache + materialised layers via the first query.
        first = router.query("market_data", "kline_daily", cn_maotai)
        assert first.provider == "tushare"

        # Snapshot external-call count to assert no second invocation.
        first_call_count = len(e2e_tushare_ok.call_log)

        # Second query — should resolve at Step 2 (UD materialised).
        second = router.query("market_data", "kline_daily", cn_maotai)
        assert second.provider == "ud_materialized"
        assert len(e2e_tushare_ok.call_log) == first_call_count


# ---------------------------------------------------------------------------
# Scene 2: cache hit → zero external calls
# ---------------------------------------------------------------------------


class TestE2EScene2_CacheHit:
    """Cache hit short-circuits external providers.

    Implementation note (DESIGN-03-010 §3.5.2): when the TA-CN adapter
    covers a capability but its collection for the requested symbol is
    empty, the 1B-B router returns ``provider='empty'`` (the
    ``empty_ta_cn`` override at router.py:308-311) rather than falling
    through to the cache. To exercise the pure **cache hit** branch we
    therefore pass ``ta_cn_adapter=None`` so Step 1 emits the canonical
    ``(skipped: no adapter)`` skip trace and the chain proceeds to
    Step 3.
    """

    def test_cache_hit_zero_external(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_tushare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-201: pre-populated cache short-circuits Step 4."""
        # Pre-populate the cache with valid (non-expired) data.
        cache = CacheManager(mongo_db=e2e_db)
        cache.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [200, 201]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="tushare",
                fetched_at=datetime.utcnow(),
                source_trace=["tushare(ok)"],
                freshness="cached",
            ),
        )

        # Register external provider — must NOT be invoked.
        e2e_registry.register(e2e_tushare_ok)

        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=None,  # Step 1 bypassed; see class docstring
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=cache,
        )

        result = router.query("market_data", "kline_daily", cn_maotai)

        assert result.freshness == "cached"
        # Original provider name is preserved on the cached entry.
        assert result.provider == "tushare"
        # The cached payload is returned unchanged.
        assert result.data == {"close": [200, 201]}
        # No external invocation.
        assert e2e_tushare_ok.call_log == []


# ---------------------------------------------------------------------------
# Scene 3: provider A → B fallback (A raises, B succeeds)
# ---------------------------------------------------------------------------


class TestE2EScene3_ProviderFallback:
    """External fallback chain: Tushare raises → AKShare returns data."""

    def test_fallback_ordered(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_fail: FakeProvider,
        e2e_akshare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-301: tushare fails → akshare succeeds in declared chain order."""
        e2e_registry.register(e2e_tushare_fail)
        e2e_registry.register(e2e_akshare_ok)

        config = UnifiedDataConfig(default_fallback_chain=("tushare", "akshare"))
        router = DataRouter(
            e2e_registry,
            config=config,
            ta_cn_adapter=e2e_ta_cn_miss,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        result = router.query("market_data", "kline_daily", cn_maotai)

        assert result.provider == "akshare"
        assert result.data == {
            "close": [2500, 2510],
            "open": [2490, 2500],
            "trade_date": ["20260701", "20260702"],
        }
        # Trace records both attempts in chain order.
        assert any("tushare(error:" in entry for entry in result.source_trace)
        assert "akshare(ok)" in result.source_trace
        # Tushare failure recorded with the actual error message.
        tushare_err_entry = next(
            entry for entry in result.source_trace if entry.startswith("tushare(error:")
        )
        assert "tushare rate limit" in tushare_err_entry


# ---------------------------------------------------------------------------
# Scene 4: all providers fail → DataResult.error (Phase 1B-A semantics)
# ---------------------------------------------------------------------------


class TestE2EScene4_AllFail:
    """All external providers raise → ``DataResult.error`` (no exception).

    Phase 1B-A semantic change (SPEC-03-008 §0.2): the Router no longer
    raises ``AllProvidersFailedError``. Instead it returns
    ``DataResult(provider='error', freshness='empty')`` with
    ``warnings=['all external providers failed']``. Callers must branch
    on ``provider == 'error'`` rather than catching the legacy
    exception.

    Implementation note (DESIGN-03-010 §3.5.4): to observe the
    ``provider='error'`` branch the TA-CN adapter must **not** cover
    the capability (so the chain reaches Step 4 without an
    ``empty_ta_cn`` override). We pass ``ta_cn_adapter=None`` which is
    equivalent to "Step 1 has no adapter to consult".
    """

    def test_returns_error_result(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_tushare_fail: FakeProvider,
        e2e_akshare_fail: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-401: all providers fail → ``provider='error'``, no exception."""
        e2e_registry.register(e2e_tushare_fail)
        e2e_registry.register(e2e_akshare_fail)

        config = UnifiedDataConfig(default_fallback_chain=("tushare", "akshare"))
        router = DataRouter(
            e2e_registry,
            config=config,
            ta_cn_adapter=None,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        # No exception is raised — the Phase 1B-A error branch returns
        # ``DataResult.error(provider='error')`` instead.
        result = router.query("market_data", "kline_daily", cn_maotai)

        assert result.provider == "error"
        assert result.freshness == "empty"
        assert "all external providers failed" in result.warnings

    def test_trace_completeness(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_tushare_fail: FakeProvider,
        e2e_akshare_fail: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-402: trace contains every step's outcome."""
        e2e_registry.register(e2e_tushare_fail)
        e2e_registry.register(e2e_akshare_fail)

        config = UnifiedDataConfig(default_fallback_chain=("tushare", "akshare"))
        router = DataRouter(
            e2e_registry,
            config=config,
            ta_cn_adapter=None,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        result = router.query("market_data", "kline_daily", cn_maotai)

        # Step 1 is skipped (no adapter), Step 2 and Step 3 both miss,
        # then both external candidates fail in chain order. The trace
        # therefore contains 4 entries (one per attempted step).
        assert "ud_materialized(miss)" in result.source_trace
        assert "cache(miss)" in result.source_trace
        # No ``ta_cn_internal(empty)`` entry — Step 1 was bypassed.
        assert not any("ta_cn_internal" in entry for entry in result.source_trace)
        tushare_err = next(
            entry for entry in result.source_trace if entry.startswith("tushare(error:")
        )
        akshare_err = next(
            entry for entry in result.source_trace if entry.startswith("akshare(error:")
        )
        assert "tushare rate limit" in tushare_err
        assert "akshare down" in akshare_err
        # Chain order: misses before external attempts, external
        # attempts in declared chain order.
        assert result.source_trace.index("ud_materialized(miss)") < result.source_trace.index(
            "tushare(error: tushare rate limit)"
        )
        assert result.source_trace.index("cache(miss)") < result.source_trace.index(
            "akshare(error: akshare down)"
        )


# ---------------------------------------------------------------------------
# Scene 5: force_refresh — Step 1/2/3 skipped, external still writes back
# ---------------------------------------------------------------------------


class TestE2EScene5_ForceRefresh:
    """``force_refresh=True`` bypasses TA-CN, Step 2, and Step 3.

    Critical semantics (DESIGN-03-010 §3.5.5, Pascal-confirmed):

    * The TA-CN adapter is **not** invoked. ``call_log`` is empty.
    * The trace contains exactly two ``(skipped: force_refresh)`` rows:
      one for ``ud_materialized`` and one for ``cache``. **No**
      ``ta_cn_internal(skipped: force_refresh)`` entry is emitted (the
      Step 1 bypass is upstream of the trace accumulator).
    * The external chain still runs, and on success the result is
      written back into Step 2 (materialised) and Step 3 (cache).
    """

    def _build_router(
        self,
        registry: ProviderRegistry,
        ta_cn: FakeTA_CNAdapter,
        db: Any,
    ) -> tuple[DataRouter, LocalMongoAdapter, CacheManager]:
        local = LocalMongoAdapter(mongo_db=db)
        cache = CacheManager(mongo_db=db)
        router = DataRouter(
            registry,
            ta_cn_adapter=ta_cn,
            local_mongo_adapter=local,
            cache_manager=cache,
        )
        return router, local, cache

    def test_skipped_trace(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_with_kline: FakeTA_CNAdapter,
        e2e_tushare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-501: trace contains both skipped entries; TA-CN not called."""
        e2e_registry.register(e2e_tushare_ok)

        # Pre-populate materialised + cache so a hit *would* be returned
        # by Step 2/3 if force_refresh did not bypass them.
        local = LocalMongoAdapter(mongo_db=e2e_db)
        cache = CacheManager(mongo_db=e2e_db)
        local.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [100, 101]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="ud_materialized",
                fetched_at=datetime.utcnow(),
                freshness="cached",
            ),
        )
        cache.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [200, 201]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="tushare",
                fetched_at=datetime.utcnow(),
                freshness="cached",
            ),
        )

        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_with_kline,
            local_mongo_adapter=local,
            cache_manager=cache,
        )

        result = router.query(
            "market_data", "kline_daily", cn_maotai, force_refresh=True
        )

        assert result.provider == "tushare"
        # Both Step 2 and Step 3 skipped; external ok.
        assert "ud_materialized(skipped: force_refresh)" in result.source_trace
        assert "cache(skipped: force_refresh)" in result.source_trace
        assert "tushare(ok)" in result.source_trace
        # TA-CN adapter was **not** called — guard in router.query() line
        # 270-274 short-circuits Step 1 entirely when force_refresh=True.
        assert e2e_ta_cn_with_kline.call_log == []
        # No ``ta_cn_internal(skipped: ...)`` row — Pascal-confirmed.
        assert not any(
            entry.startswith("ta_cn_internal(skipped") for entry in result.source_trace
        )

    def test_write_unchanged(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_with_kline: FakeTA_CNAdapter,
        e2e_tushare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-502: post force_refresh, Step 2 + Step 3 hold the fresh data."""
        e2e_registry.register(e2e_tushare_ok)

        local = LocalMongoAdapter(mongo_db=e2e_db)
        cache = CacheManager(mongo_db=e2e_db)
        local.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [100, 101]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="ud_materialized",
                fetched_at=datetime.utcnow(),
                freshness="cached",
            ),
        )
        cache.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [200, 201]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="tushare",
                fetched_at=datetime.utcnow(),
                freshness="cached",
            ),
        )

        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_with_kline,
            local_mongo_adapter=local,
            cache_manager=cache,
        )

        router.query(
            "market_data", "kline_daily", cn_maotai, force_refresh=True
        )

        # Both layers were written with the full external tushare payload.
        expected_payload = {
            "close": [1500, 1510],
            "open": [1490, 1500],
            "trade_date": ["20260701", "20260702"],
        }
        local_hit = local.get(cn_maotai, "market_data", "kline_daily", {})
        cache_hit = cache.get(cn_maotai, "market_data", "kline_daily", {})
        assert local_hit is not None
        assert local_hit.data == expected_payload
        assert cache_hit is not None
        assert cache_hit.data == expected_payload

    def test_subsequent_hit(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-503: subsequent query without force_refresh hits Step 2.

        TA-CN adapter is empty here so the second call falls through to
        Step 2 (materialised) instead of being short-circuited by Step 1
        — keeping the assertion focused on cache-vs-external behaviour.
        """
        e2e_registry.register(e2e_tushare_ok)

        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_miss,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        # Force refresh + verify Step 1 was bypassed (one external call).
        router.query(
            "market_data", "kline_daily", cn_maotai, force_refresh=True
        )
        call_count_after_force = len(e2e_tushare_ok.call_log)

        # Second query — empty TA-CN falls through to Step 2 (materialised),
        # no extra external call.
        second = router.query("market_data", "kline_daily", cn_maotai)
        assert second.provider == "ud_materialized"
        assert len(e2e_tushare_ok.call_log) == call_count_after_force


# ---------------------------------------------------------------------------
# Scene 6: index dual path (internal hit + external fallback)
# ---------------------------------------------------------------------------


class TestE2EScene6_IndexDualPath:
    """Index capability has both internal-first (TA-CN) and external
    fallback paths. Covers ``metadata.index_list`` and
    ``market_data.index_daily`` only — ``stock_sector_info`` is
    **out of scope** for Phase 1C (Pascal Path A; see
    DESIGN-03-010 §3.5.6 OQ-01).
    """

    def test_index_list_internal(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_with_index: FakeTA_CNAdapter,
        e2e_tushare_index_list_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-601: TA-CN index_basic_info hit → no external call."""
        e2e_registry.register(e2e_tushare_index_list_ok)
        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_with_index,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        result = router.query("metadata", "index_list", cn_maotai)

        assert result.provider == "ta_cn_internal"
        # Two entries in the canned index_basic_info collection.
        assert isinstance(result.data, list)
        assert len(result.data) >= 1
        # External provider was never invoked.
        assert e2e_tushare_index_list_ok.call_log == []

    def test_index_list_external(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_index_list_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-602: TA-CN empty → external index_list fallback."""
        e2e_registry.register(e2e_tushare_index_list_ok)
        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_miss,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        result = router.query("metadata", "index_list", cn_maotai)

        assert result.provider == "tushare"
        assert result.data is not None

    def test_index_daily_internal(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_with_index: FakeTA_CNAdapter,
        e2e_tushare_index_daily_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-603: TA-CN index_daily_quotes hit → no external call."""
        e2e_registry.register(e2e_tushare_index_daily_ok)
        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_with_index,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        result = router.query("market_data", "index_daily", cn_maotai)

        assert result.provider == "ta_cn_internal"
        assert isinstance(result.data, list)
        assert len(result.data) >= 1
        # Sector code and close price must be present and reasonable.
        first = result.data[0]
        assert first.get("sector_code") == "000300"
        assert first.get("close") > 0
        assert e2e_tushare_index_daily_ok.call_log == []

    def test_index_daily_external(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_index_daily_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-604: TA-CN empty → external index_daily fallback."""
        e2e_registry.register(e2e_tushare_index_daily_ok)
        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=e2e_ta_cn_miss,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=CacheManager(mongo_db=e2e_db),
        )

        result = router.query("market_data", "index_daily", cn_maotai)

        assert result.provider == "tushare"
        assert result.data is not None


# ---------------------------------------------------------------------------
# Scene 7: coverage gate (hard requirement --fail-under=60)
# ---------------------------------------------------------------------------


class TestE2EScene7_CoverageGate:
    """E2E-701/702: ``coverage report --fail-under=60`` exits 0.

    Runs ``coverage`` as a subprocess against the existing unified_data
    test suite. The 60% line-coverage bar is a **hard gate** for
    Phase 1C Closeout (DESIGN-03-010 §7 / SPEC-03-010 §3 E2E-702).
    """

    def test_coverage_report_runs(self) -> None:
        """E2E-701 + E2E-702: ``coverage run`` + ``coverage report
        --fail-under=60`` both exit 0.

        Both commands run against the existing
        ``tests/data/unified_data`` suite (no path filter on the run
        side — collection is fast and avoids touching production code).
        """
        # Step 1: coverage run on the whole unified_data suite.
        # Exclude ``test_coverage_report_runs`` itself to avoid recursion
        # (this test spawns pytest on the same directory, which would
        # re-enter this method and recurse forever).
        run_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                "-m",
                "pytest",
                "tests/data/unified_data",
                "-q",
                "-k",
                "not test_coverage_report_runs",
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=120,
        )
        assert run_result.returncode == 0, (
            f"coverage run failed (rc={run_result.returncode})\n"
            f"STDOUT tail:\n{run_result.stdout[-2000:]}\n"
            f"STDERR tail:\n{run_result.stderr[-2000:]}"
        )

        # Step 2: coverage report with the hard --fail-under=60 gate.
        report_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "report",
                "--include=skills/data/unified_data/*",
                "--fail-under=60",
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=30,
        )
        assert report_result.returncode == 0, (
            f"coverage --fail-under=60 failed (rc={report_result.returncode})\n"
            f"STDOUT:\n{report_result.stdout}\n"
            f"STDERR:\n{report_result.stderr}"
        )
        # ``TOTAL`` line surfaces the line-coverage percentage for log
        # transparency. (``coverage report`` writes ``TOTAL`` in caps.)
        assert "TOTAL" in report_result.stdout