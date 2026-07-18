"""Phase 1C E2E scene 5: ``force_refresh`` semantics.

Scene 5 (E2E-501, E2E-502, E2E-503): ``force_refresh=True`` bypasses
Step 1 (TA-CN), Step 2 (materialised), and Step 3 (query cache). The
external chain still runs and writes the result back into both layers.

Critical semantics (DESIGN-03-010 §3.5.5, Pascal-confirmed):

* The TA-CN adapter is **not** invoked. ``call_log`` is empty.
* The trace contains exactly two ``(skipped: force_refresh)`` rows:
  one for ``ud_materialized`` and one for ``cache``. **No**
  ``ta_cn_internal(skipped: force_refresh)`` entry is emitted (the
  Step 1 bypass is upstream of the trace accumulator).
* The external chain still runs, and on success the result is
  written back into Step 2 (materialised) and Step 3 (cache).
"""

from __future__ import annotations

# Load the Phase 1C E2E fixtures module so the @pytest.fixture functions
# defined there are auto-discoverable by pytest for this file's tests.
# We can't add them to the package-level ``conftest.py`` because that's
# excluded from this task's permitted-files list (Design §3.9.4).
pytest_plugins = ["skills.data.unified_data.tests.test_e2e_fixtures"]

from typing import Any

from skills.data.unified_data import (
    CacheManager,
    DataRouter,
    LocalMongoAdapter,
    ProviderRegistry,
    SecurityId,
)

from skills.data.unified_data.tests.conftest import FakeProvider, FakeTA_CNAdapter

from skills.data.unified_data.tests.test_e2e_fixtures import make_cached_result


class TestE2EScene5_ForceRefresh:
    """``force_refresh=True`` bypasses TA-CN, Step 2, and Step 3."""

    @staticmethod
    def _build_router(
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
            make_cached_result(
                cn_maotai,
                data={"close": [100, 101]},
                provider="ud_materialized",
            ),
        )
        cache.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            make_cached_result(
                cn_maotai,
                data={"close": [200, 201]},
                provider="tushare",
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
        # Exact-list equality (SPEC-03-010 §6.1.1): only the two skipped
        # rows plus the external ok — no ta_cn_internal(skipped: ...)
        # row (Pascal-confirmed: Step 1 bypass is upstream of the trace).
        assert result.source_trace == [
            "ud_materialized(skipped: force_refresh)",
            "cache(skipped: force_refresh)",
            "tushare(ok)",
        ]
        # TA-CN adapter was **not** called — guard in router.query()
        # short-circuits Step 1 entirely when force_refresh=True.
        assert e2e_ta_cn_with_kline.call_log == []
        # The local + cache ``get()`` calls must NOT have surfaced any
        # ok/miss trace entry — both layers were force-bypassed. The
        # trace-list assertion above already enforces this, but the
        # absence is also worth an explicit guard against future
        # regression.
        assert "ud_materialized(ok)" not in result.source_trace
        assert "ud_materialized(miss)" not in result.source_trace
        assert "cache(ok)" not in result.source_trace
        assert "cache(miss)" not in result.source_trace
        # External provider was called exactly once.
        assert len(e2e_tushare_ok.call_log) == 1

    def test_write_unchanged(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_ta_cn_with_kline: FakeTA_CNAdapter,
        e2e_tushare_ok: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-502: post force_refresh, Step 2 + Step 3 hold the fresh data.

        Both layers were written with the full external Tushare payload,
        not the pre-populated ``[100, 101]`` / ``[200, 201]`` values.
        """
        e2e_registry.register(e2e_tushare_ok)

        local = LocalMongoAdapter(mongo_db=e2e_db)
        cache = CacheManager(mongo_db=e2e_db)
        local.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            make_cached_result(
                cn_maotai,
                data={"close": [100, 101]},
                provider="ud_materialized",
            ),
        )
        cache.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            make_cached_result(
                cn_maotai,
                data={"close": [200, 201]},
                provider="tushare",
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

        # Both layers were written with the full external Tushare payload.
        expected_payload = {
            "close": [1500, 1510],
            "open": [1490, 1500],
            "trade_date": ["20260701", "20260702"],
        }
        local_hit = local.get(cn_maotai, "market_data", "kline_daily", {})
        cache_hit = cache.get(cn_maotai, "market_data", "kline_daily", {})
        assert local_hit is not None
        assert local_hit.data == expected_payload
        assert local_hit.provider == "ud_materialized"
        assert cache_hit is not None
        assert cache_hit.data == expected_payload
        assert cache_hit.freshness == "cached"
        # Original provider name is preserved on the cached entry.
        assert cache_hit.provider == "tushare"

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