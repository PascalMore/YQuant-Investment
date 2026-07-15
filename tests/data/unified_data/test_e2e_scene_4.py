"""Phase 1C E2E scene 4: all external providers fail.

Scene 4 (E2E-401, E2E-402): every external candidate raises ->
``DataResult.error(provider='error')`` with the full trace of attempts
preserved. The Router does NOT raise an exception (SPEC-03-008 §0.2);
callers branch on ``provider == "error"``.

Semantic note (Design §3.5.4): to exercise ``provider='error'`` the
TA-CN adapter must be ``None`` (or have ``covered_capabilities=set()``).
The current ``router.py:308-311`` returns ``provider='empty'`` when
TA-CN covers the capability but returns an empty payload — that
separate path is **out of Phase 1C scope**.
"""

from __future__ import annotations

# Load the Phase 1C E2E fixtures module so the @pytest.fixture functions
# defined there are auto-discoverable by pytest for this file's tests.
# We can't add them to the package-level ``conftest.py`` because that's
# excluded from this task's permitted-files list (Design §3.9.4).
pytest_plugins = ["tests.data.unified_data.test_e2e_fixtures"]

from typing import Any

from skills.data.unified_data import (
    CacheManager,
    DataRouter,
    LocalMongoAdapter,
    ProviderRegistry,
    SecurityId,
    UnifiedDataConfig,
)

from tests.data.unified_data.conftest import FakeProvider


class TestE2EScene4_AllFail:
    """All external providers raise -> ``DataResult.error`` (no exception)."""

    def test_returns_error_result(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_tushare_fail: FakeProvider,
        e2e_akshare_fail: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-401: all providers fail -> ``provider='error'``, no exception."""
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

        # No exception is raised — Phase 1B-A error branch returns
        # ``DataResult.error(provider='error')`` instead.
        result = router.query("market_data", "kline_daily", cn_maotai)

        assert result.provider == "error"
        assert result.freshness == "empty"
        assert "all external providers failed" in result.warnings
        # Both providers attempted exactly once before failing.
        assert len(e2e_tushare_fail.call_log) == 1
        assert len(e2e_akshare_fail.call_log) == 1

    def test_trace_completeness(
        self,
        e2e_db: Any,
        e2e_registry: ProviderRegistry,
        e2e_tushare_fail: FakeProvider,
        e2e_akshare_fail: FakeProvider,
        cn_maotai: SecurityId,
    ) -> None:
        """E2E-402: trace contains every step's outcome in declared order.

        Step 1 is bypassed (no adapter), Step 2 and Step 3 both miss,
        then both external candidates fail in chain order. The trace
        therefore contains 4 entries with deterministic error text.
        """
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

        # Exact-list equality (SPEC-03-010 §6.1.1): four entries with
        # no ta_cn_internal(empty) prefix because Step 1 was bypassed.
        assert result.source_trace == [
            "ud_materialized(miss)",
            "cache(miss)",
            "tushare(error: tushare rate limit)",
            "akshare(error: akshare down)",
        ]