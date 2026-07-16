"""DataRouter provider health-state integration tests (Phase 2 T22)."""

from __future__ import annotations

from skills.data.unified_data import DataRouter, Market, ProviderRegistry
from tests.data.unified_data.conftest import FakeProvider


CAPABILITY = "market_data.kline_daily"


def _provider(name: str, payload: dict) -> FakeProvider:
    return FakeProvider(
        name=name,
        payload=payload,
        capabilities={CAPABILITY},
        markets={Market.CN},
    )


def test_health_filtered_chain_uses_healthy_fallback_and_preserves_trace(
    fresh_registry, cn_maotai
):
    disabled = _provider("disabled", {"from": "disabled"})
    fallback = _provider("fallback", {"from": "fallback"})
    fresh_registry.register(disabled)
    fresh_registry.register(fallback)
    fresh_registry.set_health("disabled", "disabled")

    result = DataRouter(fresh_registry).query(
        "market_data", "kline_daily", cn_maotai
    )

    assert result.provider == "fallback"
    assert disabled.call_log == []
    assert "disabled(skipped: health=disabled)" in result.source_trace
    assert "fallback(ok)" in result.source_trace
    assert "ud_materialized(skipped: no adapter)" in result.source_trace
    assert "cache(skipped: no manager)" in result.source_trace


def test_unhealthy_explicit_provider_is_not_fetched_and_returns_error(
    fresh_registry, cn_maotai
):
    provider = _provider("unhealthy", {"never": "used"})
    fresh_registry.register(provider)
    fresh_registry.set_health("unhealthy", "unhealthy")

    result = DataRouter(fresh_registry).query(
        "market_data", "kline_daily", cn_maotai, provider="unhealthy"
    )

    assert result.provider == "error"
    assert result.data is None
    assert provider.call_log == []
    assert result.source_trace == ["unhealthy(skipped: health=unhealthy)"]
    assert result.warnings == ["all external providers failed"]


def test_priority_and_health_choose_first_healthy_provider(
    fresh_registry, cn_maotai
):
    unhealthy_primary = _provider("unhealthy-primary", {"from": "bad"})
    healthy_secondary = _provider("healthy-secondary", {"from": "secondary"})
    healthy_last = _provider("healthy-last", {"from": "last"})
    for provider in (unhealthy_primary, healthy_secondary, healthy_last):
        fresh_registry.register(provider)
    fresh_registry.set_priority("unhealthy-primary", 1)
    fresh_registry.set_priority("healthy-secondary", 2)
    fresh_registry.set_priority("healthy-last", 3)
    fresh_registry.set_health("unhealthy-primary", "unhealthy")

    result = DataRouter(fresh_registry).query(
        "market_data", "kline_daily", cn_maotai
    )

    assert result.provider == "healthy-secondary"
    assert unhealthy_primary.call_log == []
    assert healthy_secondary.call_log != []
    assert healthy_last.call_log == []


def test_unset_health_defaults_to_healthy_and_is_available_still_controls_fetch(
    fresh_registry, cn_maotai
):
    unavailable = FakeProvider(
        name="unavailable",
        payload={"never": "used"},
        capabilities={CAPABILITY},
        markets={Market.CN},
        available=False,
    )
    healthy = _provider("healthy", {"from": "healthy"})
    fresh_registry.register(unavailable)
    fresh_registry.register(healthy)

    assert fresh_registry.get_health("unavailable") == "healthy"
    result = DataRouter(fresh_registry).query(
        "market_data", "kline_daily", cn_maotai
    )

    assert result.provider == "healthy"
    assert unavailable.call_log == []
    assert "unavailable(skipped: unavailable)" in result.source_trace
