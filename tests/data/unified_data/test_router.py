"""Tests for DataRouter + UnifiedDataClient.

Phase 1B-A acceptance targets (DESIGN-03-008 §4.3):
    * DataRouter picks the first available provider from the chain
    * Fallback chain is exercised when the first provider fails
    * When every provider fails the router returns ``DataResult.error``
      (``provider == "error"``) instead of raising
      ``AllProvidersFailedError`` (Phase 0 → 1B-A behaviour change)
    * UnifiedDataClient can complete a query with a fake provider
    * Provider unavailable / wrong capability → skipped (not error)
    * Forced ``provider=`` parameter bypasses the fallback chain
    * ``provider="ta_cn_internal"`` short-circuits to Step 1 (TA-CN)
    * ``force_refresh=True`` skips Step 1 (TA-CN)
"""

from __future__ import annotations

import pytest

from skills.data.unified_data import (
    AllProvidersFailedError,
    DataRouter,
    Market,
    ProviderError,
    ProviderRegistry,
    ProviderUnavailableError,
    SecurityId,
    UnifiedDataClient,
    UnifiedDataConfig,
    UnsupportedCapabilityError,
)
from tests.data.unified_data.conftest import FakeProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


CN_CAP = "market_data.kline_daily"


def _register_cn_pair(
    registry: ProviderRegistry,
    *,
    first_payload=None,
    second_payload=None,
    first_raises: BaseException | None = None,
    second_raises: BaseException | None = None,
    first_available: bool = True,
    second_available: bool = True,
) -> tuple[FakeProvider, FakeProvider]:
    """Register two fake providers covering the CN market_data capability."""
    first = FakeProvider(
        name="primary",
        payload=first_payload,
        capabilities={CN_CAP},
        markets={Market.CN},
        raise_on_fetch=first_raises,
        available=first_available,
    )
    second = FakeProvider(
        name="fallback",
        payload=second_payload,
        capabilities={CN_CAP},
        markets={Market.CN},
        raise_on_fetch=second_raises,
        available=second_available,
    )
    registry.register(first)
    registry.register(second)
    return first, second


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestRouterHappyPath:
    def test_first_provider_succeeds(self, fresh_registry, cn_maotai, fixed_now):
        first, second = _register_cn_pair(
            fresh_registry,
            first_payload={"close": [100, 101]},
            second_payload={"close": [200]},
        )
        router = DataRouter(fresh_registry)
        result = router.query(
            "market_data",
            "kline_daily",
            cn_maotai,
            fetched_at=fixed_now,
        )
        assert result.provider == "primary"
        assert result.data == {"close": [100, 101]}
        assert result.freshness == "delayed"
        # Phase 1B-B: silent skip paths now append their own trace entries
        # (``ud_materialized(skipped: no adapter)`` / ``cache(skipped: no manager)``),
        # so we assert the expected provider outcome is present in the trace
        # rather than requiring the trace to equal it exactly.
        assert "primary(ok)" in result.source_trace
        # The fallback provider must not have been called.
        assert second.call_log == []

    def test_explicit_capability_chain_in_config(self, fresh_registry, cn_maotai):
        # Register out of order; the config-level chain should override.
        primary = FakeProvider(
            name="primary",
            payload={"primary": True},
            capabilities={CN_CAP},
            markets={Market.CN},
        )
        secondary = FakeProvider(
            name="secondary",
            payload={"secondary": True},
            capabilities={CN_CAP},
            markets={Market.CN},
        )
        fresh_registry.register(primary)
        fresh_registry.register(secondary)
        config = UnifiedDataConfig(
            default_fallback_chain=("secondary", "primary"),
        )
        router = DataRouter(fresh_registry, config=config)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "secondary"
        assert primary.call_log == []


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


class TestRouterFallback:
    def test_fallback_when_first_raises_provider_error(
        self, fresh_registry, cn_maotai, fixed_now
    ):
        first, second = _register_cn_pair(
            fresh_registry,
            first_raises=ProviderError("primary broken"),
            second_payload={"close": [50]},
        )
        router = DataRouter(fresh_registry)
        result = router.query(
            "market_data", "kline_daily", cn_maotai, fetched_at=fixed_now
        )
        assert result.provider == "fallback"
        assert result.data == {"close": [50]}
        # Trace records BOTH provider attempts. Phase 1B-B additionally appends
        # ``ud_materialized(skipped: no adapter)`` / ``cache(skipped: no manager)``
        # at the front when the corresponding components are not wired, so we
        # require both provider outcomes in order and tolerate the skip entries.
        expected_provider_trace = [
            "primary(error: primary broken)",
            "fallback(ok)",
        ]
        provider_trace = [
            entry for entry in result.source_trace
            if entry.startswith("primary(") or entry.startswith("fallback(")
        ]
        assert provider_trace == expected_provider_trace
        assert result.warnings == []

    def test_fallback_skips_unavailable_provider(
        self, fresh_registry, cn_maotai
    ):
        first, second = _register_cn_pair(
            fresh_registry,
            first_available=False,
            second_payload={"close": [42]},
        )
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "fallback"
        assert first.call_log == []
        assert second.call_log != []

    def test_fallback_skips_wrong_capability(self, fresh_registry, cn_maotai):
        wrong = FakeProvider(
            name="wrong",
            payload=None,
            capabilities={"financial.income_statement"},
            markets={Market.CN},
        )
        right = FakeProvider(
            name="right",
            payload={"close": [42]},
            capabilities={CN_CAP},
            markets={Market.CN},
        )
        fresh_registry.register(wrong)
        fresh_registry.register(right)
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "right"
        assert wrong.call_log == []

    def test_skipped_providers_do_not_block_fallback(
        self, fresh_registry, cn_maotai
    ):
        skipped = FakeProvider(
            name="skipped",
            payload={"never": "used"},
            capabilities={CN_CAP},
            markets={Market.CN},
            available=False,
        )
        winner = FakeProvider(
            name="winner",
            payload={"close": [1]},
            capabilities={CN_CAP},
            markets={Market.CN},
        )
        fresh_registry.register(skipped)
        fresh_registry.register(winner)
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "winner"
        # Phase 1B-B: ud_materialized / cache skip entries may appear at the
        # front of the trace; the unavailable-provider skip still must appear.
        assert "skipped(skipped: unavailable)" in result.source_trace

    def test_unsupported_capability_error_is_treated_as_failure(
        self, fresh_registry, cn_maotai
    ):
        inconsistent = FakeProvider(
            name="liar",
            payload={"x": 1},
            capabilities={"market_data.kline_daily"},
            markets={Market.CN},
            raise_on_fetch=UnsupportedCapabilityError("forced"),
        )
        ok = FakeProvider(
            name="ok",
            payload={"close": [1]},
            capabilities={CN_CAP},
            markets={Market.CN},
        )
        fresh_registry.register(inconsistent)
        fresh_registry.register(ok)
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "ok"

    def test_provider_unavailable_continues_fallback(
        self, fresh_registry, cn_maotai
    ):
        first, second = _register_cn_pair(
            fresh_registry,
            first_raises=ProviderUnavailableError("token expired"),
            second_payload={"close": [2]},
        )
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "fallback"
        assert "token expired" in " ".join(
            entry for entry in result.source_trace if "unavailable" in entry
        )


# ---------------------------------------------------------------------------
# All providers failed
# ---------------------------------------------------------------------------


class TestRouterAllFailed:
    def test_all_providers_fail_raises_with_attempts(
        self, fresh_registry, cn_maotai
    ):
        first, second = _register_cn_pair(
            fresh_registry,
            first_raises=ProviderError("err 1"),
            second_payload=None,
            second_raises=ProviderError("err 2"),
        )
        router = DataRouter(fresh_registry)
        # Phase 1B-A behaviour change: the router no longer raises
        # ``AllProvidersFailedError`` — it returns ``DataResult.error``
        # (``provider == "error"``) with no payload.
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error"
        assert result.data is None
        assert sum(1 for entry in result.source_trace if "error" in entry) == 2

    def test_registry_empty_raises(self, fresh_registry, cn_maotai):
        router = DataRouter(fresh_registry)
        # Phase 1B-A: empty registry → DataResult.error.
        # Phase 1B-B: ud_materialized / cache skip entries are appended even
        # when no external provider is registered, so the trace may contain
        # those skip entries. We assert no provider attempts were made.
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error"
        assert result.data is None
        provider_attempts = [
            entry for entry in result.source_trace
            if not (entry.startswith("ud_materialized(")
                    or entry.startswith("cache("))
        ]
        assert provider_attempts == []

    def test_all_skipped_raises(self, fresh_registry, cn_maotai):
        # All providers cover the capability but none is available.
        a = FakeProvider(
            name="a",
            capabilities={CN_CAP},
            markets={Market.CN},
            available=False,
        )
        b = FakeProvider(
            name="b",
            capabilities={CN_CAP},
            markets={Market.CN},
            available=False,
        )
        fresh_registry.register(a)
        fresh_registry.register(b)
        router = DataRouter(fresh_registry)
        # Phase 1B-A: every candidate unavailable → DataResult.error.
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error"
        assert result.data is None


# ---------------------------------------------------------------------------
# Forced provider
# ---------------------------------------------------------------------------


class TestRouterForcedProvider:
    def test_forced_provider_used_when_present(self, fresh_registry, cn_maotai):
        first, second = _register_cn_pair(
            fresh_registry,
            first_payload={"from": "primary"},
            second_payload={"from": "fallback"},
        )
        router = DataRouter(fresh_registry)
        # Force the fallback provider even though primary is registered first.
        result = router.query(
            "market_data", "kline_daily", cn_maotai, provider="fallback"
        )
        assert result.provider == "fallback"
        assert first.call_log == []

    def test_forced_provider_not_registered_raises(self, fresh_registry, cn_maotai):
        _register_cn_pair(
            fresh_registry, first_payload={"x": 1}, second_payload={"x": 2}
        )
        router = DataRouter(fresh_registry)
        # Phase 1B-A: unknown forced provider → DataResult.error.
        result = router.query(
            "market_data", "kline_daily", cn_maotai, provider="unknown"
        )
        assert result.provider == "error"

    def test_forced_provider_wrong_capability_raises(
        self, fresh_registry, cn_maotai
    ):
        # The forced provider covers a different capability/market combo.
        wrong = FakeProvider(
            name="wrong-cap",
            capabilities={"financial.income_statement"},
            markets={Market.CN},
        )
        fresh_registry.register(wrong)
        router = DataRouter(fresh_registry)
        # Phase 1B-A: capability/market mismatch → DataResult.error.
        result = router.query(
            "market_data", "kline_daily", cn_maotai, provider="wrong-cap"
        )
        assert result.provider == "error"


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


class TestRouterValidation:
    def test_invalid_domain_raises(self, fresh_registry, cn_maotai, make_provider):
        provider = make_provider(
            capabilities={CN_CAP}, markets={Market.CN}
        )
        fresh_registry.register(provider)
        router = DataRouter(fresh_registry)
        with pytest.raises(ValueError):
            router.query("market.data", "kline_daily", cn_maotai)

    def test_invalid_operation_raises(self, fresh_registry, cn_maotai, make_provider):
        provider = make_provider(
            capabilities={CN_CAP}, markets={Market.CN}
        )
        fresh_registry.register(provider)
        router = DataRouter(fresh_registry)
        with pytest.raises(ValueError):
            router.query("market_data", "kline.daily", cn_maotai)

    def test_invalid_market_argument_raises(
        self, fresh_registry, cn_maotai, make_provider
    ):
        provider = make_provider(
            capabilities={CN_CAP}, markets={Market.CN}
        )
        fresh_registry.register(provider)
        router = DataRouter(fresh_registry)
        with pytest.raises(ValueError):
            router.query(
                "market_data", "kline_daily", cn_maotai, market="ZZ"
            )


# ---------------------------------------------------------------------------
# UnifiedDataClient end-to-end
# ---------------------------------------------------------------------------


class TestUnifiedDataClient:
    def test_client_completes_query_with_fake_provider(
        self, fresh_client, cn_maotai, fixed_now
    ):
        provider = FakeProvider(
            name="memory",
            payload={"close": [99, 100]},
            capabilities={CN_CAP},
            markets={Market.CN},
        )
        fresh_client.register_provider(provider)
        result = fresh_client.query(
            "market_data", "kline_daily", cn_maotai, fetched_at=fixed_now
        )
        assert isinstance(result, type(fresh_client.router.query(
            "market_data", "kline_daily", cn_maotai
        )))
        assert result.provider == "memory"
        assert result.security_id == cn_maotai
        assert result.fetched_at == fixed_now

    def test_client_with_providers_factory(self, cn_maotai, fixed_now):
        a = FakeProvider(
            name="a", payload={"a": 1}, capabilities={CN_CAP}, markets={Market.CN}
        )
        b = FakeProvider(
            name="b", payload={"b": 1}, capabilities={CN_CAP}, markets={Market.CN}
        )
        client = UnifiedDataClient.with_providers([a, b])
        result = client.query(
            "market_data", "kline_daily", cn_maotai, fetched_at=fixed_now
        )
        assert result.provider == "a"
        assert client.registry.list_provider_names() == ["a", "b"]

    def test_client_forwards_provider_override(self, cn_maotai):
        a = FakeProvider(
            name="a", payload={"a": 1}, capabilities={CN_CAP}, markets={Market.CN}
        )
        b = FakeProvider(
            name="b", payload={"b": 1}, capabilities={CN_CAP}, markets={Market.CN}
        )
        client = UnifiedDataClient.with_providers([a, b])
        result = client.query(
            "market_data", "kline_daily", cn_maotai, provider="b"
        )
        assert result.provider == "b"

    def test_client_propagates_all_providers_failed(self, cn_maotai):
        a = FakeProvider(
            name="a",
            payload=None,
            capabilities={CN_CAP},
            markets={Market.CN},
            raise_on_fetch=ProviderError("boom"),
        )
        client = UnifiedDataClient.with_providers([a])
        # Phase 1B-A: client mirrors the router — DataResult.error,
        # no exception.
        result = client.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error"
        assert result.data is None

    def test_client_exposes_registry_and_config(self):
        client = UnifiedDataClient()
        assert client.registry is not None
        assert client.config is not None
        assert client.router is not None
        assert client.router.registry is client.registry