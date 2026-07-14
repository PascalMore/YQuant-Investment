"""Internal-first Router orchestration tests (DESIGN-03-008 §4.2 DR-001..012
+ IT-001..004).

These tests cover the four-step orchestration the Phase 1B-A Router
implements:

    Step 1 — TA-CN (internal-first, optional, skipped for "not covered"
             capabilities).
    Step 2 — local Mongo adapter (Phase 1B-B slot, always skipped in 1B-A).
    Step 3 — cache manager    (Phase 1B-B slot, always skipped in 1B-A).
    Step 4 — external fallback chain (Tushare → AKShare).

The fixtures (``fake_ta_cn_adapter``, ``fake_ta_cn_with_kline``) live in
``tests/data/unified_data/conftest.py``.
"""

from __future__ import annotations

import pytest

from skills.data.unified_data import (
    DataRouter,
    ProviderError,
    ProviderRegistry,
    ProviderUnavailableError,
    SecurityId,
    UnifiedDataClient,
)
from tests.data.unified_data.conftest import FakeProvider


# ---------------------------------------------------------------------------
# Constants shared by multiple tests
# ---------------------------------------------------------------------------

KLINE_CAP = "market_data.kline_daily"
VALUATION_CAP = "valuation.daily_basic"
INDEX_CAP = "metadata.index_list"


# ---------------------------------------------------------------------------
# Step 1 — TA-CN hit / not covered / exception
# ---------------------------------------------------------------------------


class TestTACNStep:
    def test_ta_cn_hit(self, fake_ta_cn_with_kline, fresh_registry, cn_maotai):
        """DR-101: TA-CN returns data, no external providers called."""
        router = DataRouter(
            fresh_registry,
            ta_cn_adapter=fake_ta_cn_with_kline,
        )
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "ta_cn_internal"
        assert result.source_trace == ["ta_cn_internal(ok)"]
        assert fake_ta_cn_with_kline.call_log == ["get_daily_bars"]
        assert fresh_registry.list_provider_names() == []

    def test_ta_cn_not_covered_external_ok(
        self, fake_ta_cn_adapter, fresh_registry, cn_maotai
    ):
        """DR-101: TA-CN does not cover the capability → external chain runs."""
        for name, payload in (("tushare", {"close": [1]}), ("akshare", {"close": [2]})):
            fresh_registry.register(
                FakeProvider(
                    name=name,
                    payload=payload,
                    capabilities={VALUATION_CAP},
                    markets={type(cn_maotai).market if False else cn_maotai.market},
                )
            )
        router = DataRouter(
            fresh_registry, ta_cn_adapter=fake_ta_cn_adapter
        )
        result = router.query("valuation", "daily_basic", cn_maotai)
        assert result.provider == "tushare"
        # Step 1 must have been bypassed — TA-CN has no valuation capability.
        assert fake_ta_cn_adapter.call_log == []
        assert any(entry.startswith("tushare") for entry in result.source_trace)

    def test_ta_cn_exception_fallback(self, fresh_registry, cn_maotai):
        """DR-101: TA-CN raises → Router records a warning and falls back."""
        from tests.data.unified_data.conftest import FakeTA_CNAdapter

        boom = FakeTA_CNAdapter(
            collections={},
            raise_on_query=RuntimeError("simulated TA-CN failure"),
        )
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1700]},
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
            )
        )
        router = DataRouter(fresh_registry, ta_cn_adapter=boom)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "tushare"
        assert any("ta_cn_internal(error" in e for e in result.source_trace)
        assert "ta_cn_internal" in result.warnings


# ---------------------------------------------------------------------------
# Provider override / force_refresh branches
# ---------------------------------------------------------------------------


class TestProviderOverride:
    def test_force_refresh_skip_ta_cn(
        self, fake_ta_cn_with_kline, fresh_registry, cn_maotai
    ):
        """DR-102: force_refresh=True skips Step 1 entirely."""
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [900]},
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
            )
        )
        router = DataRouter(
            fresh_registry, ta_cn_adapter=fake_ta_cn_with_kline
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai, force_refresh=True
        )
        assert result.provider == "tushare"
        assert fake_ta_cn_with_kline.call_log == []

    def test_provider_tushare_skip_ta_cn(
        self, fake_ta_cn_with_kline, fresh_registry, cn_maotai
    ):
        """DR-103: explicit provider="tushare" pins Step 4 and skips Step 1."""
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [950]},
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
            )
        )
        router = DataRouter(
            fresh_registry, ta_cn_adapter=fake_ta_cn_with_kline
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai, provider="tushare"
        )
        assert result.provider == "tushare"
        assert fake_ta_cn_with_kline.call_log == []

    def test_provider_ta_cn_internal(self, fake_ta_cn_with_kline, cn_maotai):
        """DR-104: provider="ta_cn_internal" runs Step 1 only (no registry used)."""
        # Even with an empty registry, the router should not raise.
        router = DataRouter(
            ProviderRegistry(), ta_cn_adapter=fake_ta_cn_with_kline
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai, provider="ta_cn_internal"
        )
        assert result.provider == "ta_cn_internal"
        assert fake_ta_cn_with_kline.call_log == ["get_daily_bars"]

    def test_ta_cn_none_degraded(self, fresh_registry, cn_maotai):
        """DR-105: Phase 0 compatibility — no adapter → Router goes straight to Step 4."""
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1000]},
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
            )
        )
        router = DataRouter(fresh_registry)  # ta_cn_adapter=None (Phase 0)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "tushare"


# ---------------------------------------------------------------------------
# Step 4 — external chain failure handling
# ---------------------------------------------------------------------------


class TestExternalChainFailure:
    def test_all_external_unavailable(self, fresh_registry, cn_maotai):
        """DR-106: every external provider unavailable → DataResult.error."""
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
                available=False,
            )
        )
        fresh_registry.register(
            FakeProvider(
                name="akshare",
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
                available=False,
            )
        )
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error"
        assert result.data is None
        assert "all external providers unavailable" in result.warnings

    def test_all_external_fetch_fail(self, fresh_registry, cn_maotai):
        """DR-107: every external provider raises → DataResult.error with 2 trace entries."""
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
                raise_on_fetch=ProviderError("tushare boom"),
            )
        )
        fresh_registry.register(
            FakeProvider(
                name="akshare",
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
                raise_on_fetch=ProviderError("akshare boom"),
            )
        )
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error"
        assert result.data is None
        assert sum(1 for e in result.source_trace if "error" in e) == 2
        assert "all external providers failed" in result.warnings

    def test_no_provider_registered(self, cn_maotai):
        """DR-108: empty registry → DataResult.error.

        Phase 1B-B: ud_materialized / cache skip entries are appended even
        when no external provider is registered, so the trace may contain
        those skip entries. We assert no provider attempts were made.
        """
        router = DataRouter(ProviderRegistry())
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error"
        assert result.data is None
        provider_attempts = [
            entry for entry in result.source_trace
            if not (entry.startswith("ud_materialized(")
                    or entry.startswith("cache("))
        ]
        assert provider_attempts == []


# ---------------------------------------------------------------------------
# source_trace / warnings
# ---------------------------------------------------------------------------


class TestTraceAndWarnings:
    def test_source_trace_full(self, fresh_registry, cn_maotai):
        """DR-109: 3-step trace — TA-CN error + Tushare fail + AKShare ok."""
        from tests.data.unified_data.conftest import FakeTA_CNAdapter

        adapter = FakeTA_CNAdapter(
            collections={},
            raise_on_query=RuntimeError("ta_cn fail"),
        )
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
                raise_on_fetch=ProviderError("tushare fail"),
            )
        )
        fresh_registry.register(
            FakeProvider(
                name="akshare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
            )
        )
        router = DataRouter(fresh_registry, ta_cn_adapter=adapter)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "akshare"
        # Phase 1B-B: ud_materialized / cache skip entries are appended on
        # the silent-skip path when their components are not wired, so the
        # trace now has 5 entries (3 real attempts + 2 skip entries). The
        # skip entries are interleaved with the real attempts, not appended
        # at the end, so we assert by membership + count of real attempts.
        joined = " ".join(result.source_trace)
        assert "ta_cn_internal(error" in joined
        assert "tushare(error" in joined
        assert "akshare(ok)" in joined
        # The three real provider / adapter attempts must still be present
        # in addition to any skip entries appended by silent-skip paths.
        real_attempts = [
            entry for entry in result.source_trace
            if entry.startswith("ta_cn_internal(")
            or entry.startswith("tushare(")
            or entry.startswith("akshare(")
        ]
        assert len(real_attempts) == 3

    def test_warnings_fallback(self, fresh_registry, cn_maotai):
        """DR-110: tushare unavailable + akshare ok ⇒ only the fallback warning."""
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
                available=False,
            )
        )
        fresh_registry.register(
            FakeProvider(
                name="akshare",
                payload={"close": [42]},
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
            )
        )
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "akshare"
        # The unavailable candidate contributed no warning by itself —
        # the chain only emits "all providers unavailable" when none
        # succeed. Mixing one unavailable + one success ⇒ no warning.
        assert result.warnings == []


# ---------------------------------------------------------------------------
# Integration tests — UnifiedDataClient.query end-to-end
# ---------------------------------------------------------------------------


class TestClientIntegration:
    def _build_client(
        self, adapter=None, registry=None
    ) -> UnifiedDataClient:
        return UnifiedDataClient(registry=registry, ta_cn_adapter=adapter)

    def test_it_001_client_ta_cn_hit_no_external(
        self, fake_ta_cn_with_kline, cn_maotai
    ):
        """IT-001: end-to-end, TA-CN covers the capability, no external call."""
        client = self._build_client(adapter=fake_ta_cn_with_kline)
        result = client.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "ta_cn_internal"
        assert fake_ta_cn_with_kline.call_log == ["get_daily_bars"]

    def test_it_002_client_valuation_falls_back_to_akshare(
        self, fake_ta_cn_adapter, cn_maotai
    ):
        """IT-002: end-to-end, capability not in TA-CN → AKShare fallback."""
        registry = ProviderRegistry()
        # ``tushare`` reports as unavailable here to force AKShare to win.
        registry.register(
            FakeProvider(
                name="tushare",
                capabilities={VALUATION_CAP},
                markets={cn_maotai.market},
                available=False,
            )
        )
        registry.register(
            FakeProvider(
                name="akshare",
                payload={"pe": 12.3},
                capabilities={VALUATION_CAP},
                markets={cn_maotai.market},
            )
        )
        client = self._build_client(
            adapter=fake_ta_cn_adapter, registry=registry
        )
        result = client.query("valuation", "daily_basic", cn_maotai)
        assert result.provider == "akshare"

    def test_it_003_client_force_refresh_skips_ta_cn(
        self, fake_ta_cn_with_kline, cn_maotai
    ):
        """IT-003: end-to-end, force_refresh=True skips Step 1."""
        registry = ProviderRegistry()
        registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [800]},
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
            )
        )
        client = UnifiedDataClient(
            registry=registry, ta_cn_adapter=fake_ta_cn_with_kline
        )
        result = client.query(
            "market_data", "kline_daily", cn_maotai, force_refresh=True
        )
        assert result.provider == "tushare"
        assert fake_ta_cn_with_kline.call_log == []

    def test_it_004_client_provider_override(self, fake_ta_cn_with_kline, cn_maotai):
        """IT-004: end-to-end, provider="tushare" pins Step 4."""
        registry = ProviderRegistry()
        registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [870]},
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
            )
        )
        registry.register(
            FakeProvider(
                name="akshare",
                payload={"close": [10]},  # tiny so ak-share wouldn't naturally win
                capabilities={KLINE_CAP},
                markets={cn_maotai.market},
            )
        )
        client = UnifiedDataClient(
            registry=registry, ta_cn_adapter=fake_ta_cn_with_kline
        )
        result = client.query(
            "market_data", "kline_daily", cn_maotai, provider="tushare"
        )
        assert result.provider == "tushare"
        assert fake_ta_cn_with_kline.call_log == []
