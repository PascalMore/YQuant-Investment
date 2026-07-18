"""Phase 1C E2E scenes 1, 2, 3.

Scene inventory (per DESIGN-03-010 §3.2 / SPEC-03-010 §3):

* Scene 1 (E2E-101..104): all-miss + external success + write + next
  query hits Step 2.
* Scene 2 (E2E-201): cache hit -> zero external calls.
* Scene 3 (E2E-301): provider A raises -> provider B succeeds with
  **exact** source_trace equality (SPEC-03-010 §6.1.1).

Each ``TestClass`` lives independently and uses the shared fixtures
from :mod:`test_e2e_fixtures`.
"""

from __future__ import annotations

# Load the Phase 1C E2E fixtures module so the @pytest.fixture functions
# defined there are auto-discoverable by pytest for this file's tests.
# We can't add them to the package-level ``conftest.py`` because that's
# excluded from this task's permitted-files list (Design §3.9.4).
pytest_plugins = ["skills.data.unified_data.tests.test_e2e_fixtures"]

from typing import Any

import pytest

from skills.data.unified_data import (
    CacheManager,
    DataRouter,
    LocalMongoAdapter,
    ProviderRegistry,
    SecurityId,
    UnifiedDataConfig,
)

from skills.data.unified_data.tests.conftest import FakeProvider, FakeTA_CNAdapter

from skills.data.unified_data.tests.test_e2e_fixtures import KLINE_CAP


# ---------------------------------------------------------------------------
# Scene 1: all miss + external success + write + subsequent hit on Step 2
# ---------------------------------------------------------------------------


class TestE2EScene1_AllMissExternalSuccess:
    """Reproduce the all-miss path:

    TA-CN empty -> Step 2 miss -> Step 3 miss -> external success
    -> materialised write -> cache write -> next query hits Step 2.
    """

    @staticmethod
    def _build_router(
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
        # Full chain in trace order: TA-CN empty -> Step 2 miss -> Step 3
        # miss -> external ok. Exact-list equality (SPEC §6.1.1).
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
        """E2E-104: second query hits Step 2 (no second external call)."""
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
# Scene 2: cache hit -> zero external calls
# ---------------------------------------------------------------------------


class TestE2EScene2_CacheHit:
    """Cache hit short-circuits external providers.

    Implementation note (DESIGN-03-010 §3.5.2): when the TA-CN adapter
    covers a capability but its collection for the requested symbol is
    empty, the 1B-B router returns ``provider='empty'``
    (router.py:308-311) rather than falling through to the cache. To
    exercise the pure **cache hit** branch we pass
    ``ta_cn_adapter=None`` so Step 1 emits the canonical
    ``(skipped: no adapter)`` skip trace and the chain proceeds to
    Step 3.
    """

    def test_cache_hit_zero_external(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_tushare_ok: FakeProvider,
        e2e_prepop_cache: CacheManager,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-201: pre-populated cache short-circuits Step 4."""
        from skills.data.unified_data.tests.test_e2e_fixtures import make_cached_result

        # Pre-populate the cache with valid (non-expired) data.
        e2e_prepop_cache.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            make_cached_result(
                cn_maotai,
                data={"close": [200, 201]},
                provider="tushare",
                freshness="cached",
                source_trace=["tushare(ok)"],
            ),
        )

        # Register external provider — must NOT be invoked.
        e2e_registry.register(e2e_tushare_ok)

        router = DataRouter(
            e2e_registry,
            ta_cn_adapter=None,  # Step 1 bypassed; see class docstring.
            local_mongo_adapter=LocalMongoAdapter(mongo_db=e2e_db),
            cache_manager=e2e_prepop_cache,
        )

        result = router.query("market_data", "kline_daily", cn_maotai)

        assert result.freshness == "cached"
        # Original provider name is preserved on the cached entry.
        assert result.provider == "tushare"
        # The cached payload is returned unchanged.
        assert result.data == {"close": [200, 201]}
        # No external invocation.
        assert e2e_tushare_ok.call_log == []
        # The cached entry's source_trace is the original payload's
        # trace (``["tushare(ok)"]``), preserved through the cache. The
        # router does not append ``cache(ok)`` to the returned DataResult
        # — instead the cached entry's own source_trace is what surfaces
        # to the caller. The proof of "cache really hit" is the
        # preserved payload + zero external calls + freshness="cached".
        assert result.source_trace == ["tushare(ok)"]


# ---------------------------------------------------------------------------
# Scene 3: provider A -> B fallback (A raises, B succeeds)
# ---------------------------------------------------------------------------


class TestE2EScene3_ProviderFallback:
    """External fallback chain: Tushare raises -> AKShare returns data."""

    def test_fallback_ordered(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_miss: FakeTA_CNAdapter,
        e2e_tushare_fail: FakeProvider,
        e2e_akshare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-301: tushare fails -> akshare succeeds in declared chain order.

        Asserts the **exact** source_trace list (SPEC-03-010 §6.1.1):
        TA-CN empty -> Step 2 miss -> Step 3 miss -> tushare error ->
        akshare ok. Order, count, and error text are all part of the
        contract.
        """
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
        # Distinct close values prove the data came from AKShare, not
        # Tushare (Tushare raised before its payload could surface).
        assert result.data == {
            "close": [2500, 2510],
            "open": [2490, 2500],
            "trade_date": ["20260701", "20260702"],
        }
        # Exact-list equality (SPEC-03-010 §6.1.1).
        assert result.source_trace == [
            "ta_cn_internal(empty)",
            "ud_materialized(miss)",
            "cache(miss)",
            "tushare(error: tushare rate limit)",
            "akshare(ok)",
        ]
        # Tushare attempted exactly once before failing.
        assert len(e2e_tushare_fail.call_log) == 1
        # Tushare call captured the requested capability.
        tushare_call = e2e_tushare_fail.call_log[0]
        assert tushare_call[0] == "tushare"
        assert tushare_call[1] == KLINE_CAP
        # AKShare attempted exactly once and succeeded.
        assert len(e2e_akshare_ok.call_log) == 1