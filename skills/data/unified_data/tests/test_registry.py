"""Tests for ProviderRegistry.

Phase 0 acceptance targets:
    * Provider registration works
    * Duplicate registration raises ValueError
    * Capability lookup returns providers in registration order
    * Market filtering works
"""

from __future__ import annotations

import pytest

from skills.data.unified_data import (
    Market,
    ProviderRegistry,
)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestProviderRegistration:
    def test_register_single_provider(self, fresh_registry, make_provider):
        provider = make_provider(
            capabilities={"market_data.kline_daily"},
            markets={Market.CN},
        )
        fresh_registry.register(provider)
        assert fresh_registry.list_provider_names() == ["fake"]
        assert fresh_registry.list_providers() == [provider]

    def test_register_preserves_order(self, fresh_registry, make_provider):
        first = make_provider(name="alpha", capabilities={"x.read"})
        second = make_provider(name="beta", capabilities={"x.read"})
        fresh_registry.register(first)
        fresh_registry.register(second)
        assert fresh_registry.get_providers("x.read") == [first, second]

    def test_duplicate_registration_raises(self, fresh_registry, make_provider):
        a = make_provider(name="dup", capabilities={"x.read"})
        b = make_provider(name="dup", capabilities={"x.read"})
        fresh_registry.register(a)
        with pytest.raises(ValueError):
            fresh_registry.register(b)
        # Registry still has only the first provider.
        assert fresh_registry.list_provider_names() == ["dup"]

    def test_register_rejects_empty_name(self, fresh_registry):
        class _Anon:
            @property
            def name(self) -> str:
                return ""

            @property
            def capabilities(self) -> set[str]:
                return set()

            @property
            def markets(self) -> set[Market]:
                return set()

            def is_available(self) -> bool:
                return True

            def fetch(self, domain, operation, security_id, **params):
                return None

        with pytest.raises(ValueError):
            fresh_registry.register(_Anon())

    def test_unregister_removes_provider_and_capability_index(
        self, fresh_registry, make_provider
    ):
        provider = make_provider(name="p1", capabilities={"x.read"})
        fresh_registry.register(provider)
        assert fresh_registry.unregister("p1") is True
        assert fresh_registry.get_providers("x.read") == []
        assert "x.read" not in fresh_registry.list_capabilities()
        # Second unregister is a no-op.
        assert fresh_registry.unregister("p1") is False

    def test_unregister_only_clears_capabilities_for_removed_provider(
        self, fresh_registry, make_provider
    ):
        a = make_provider(name="a", capabilities={"x.read"})
        b = make_provider(name="b", capabilities={"x.read"})
        fresh_registry.register(a)
        fresh_registry.register(b)
        fresh_registry.unregister("a")
        assert fresh_registry.get_providers("x.read") == [b]

    def test_clear(self, fresh_registry, make_provider):
        fresh_registry.register(make_provider(name="a", capabilities={"x.read"}))
        fresh_registry.register(make_provider(name="b", capabilities={"y.read"}))
        fresh_registry.clear()
        assert fresh_registry.list_providers() == []
        assert fresh_registry.list_capabilities() == set()


# ---------------------------------------------------------------------------
# Capability lookup
# ---------------------------------------------------------------------------


class TestCapabilityLookup:
    def test_get_providers_filters_by_capability(self, fresh_registry, make_provider):
        a = make_provider(
            name="a", capabilities={"market_data.kline_daily"}, markets={Market.CN}
        )
        b = make_provider(
            name="b", capabilities={"financial.income_statement"}, markets={Market.CN}
        )
        fresh_registry.register(a)
        fresh_registry.register(b)
        assert fresh_registry.get_providers("market_data.kline_daily") == [a]
        assert fresh_registry.get_providers("financial.income_statement") == [b]
        assert fresh_registry.get_providers("nonexistent.capability") == []

    def test_get_providers_filters_by_market(self, fresh_registry, make_provider):
        cn = make_provider(
            name="cn", capabilities={"x.read"}, markets={Market.CN}
        )
        hk = make_provider(
            name="hk", capabilities={"x.read"}, markets={Market.HK}
        )
        both = make_provider(
            name="both", capabilities={"x.read"}, markets={Market.CN, Market.HK}
        )
        for p in (cn, hk, both):
            fresh_registry.register(p)
        # No market filter → all three.
        assert fresh_registry.get_providers("x.read") == [cn, hk, both]
        # CN filter → cn and both.
        cn_list = fresh_registry.get_providers("x.read", Market.CN)
        assert cn_list == [cn, both]
        # HK filter → hk and both.
        hk_list = fresh_registry.get_providers("x.read", Market.HK)
        assert hk_list == [hk, both]
        # US filter → empty.
        assert fresh_registry.get_providers("x.read", Market.US) == []

    def test_get_providers_accepts_string_market(self, fresh_registry, make_provider):
        provider = make_provider(
            name="cn", capabilities={"x.read"}, markets={Market.CN}
        )
        fresh_registry.register(provider)
        assert fresh_registry.get_providers("x.read", "CN") == [provider]
        assert fresh_registry.get_providers("x.read", "ZZ") == []

    def test_has_capability(self, fresh_registry, make_provider):
        provider = make_provider(
            name="p",
            capabilities={"market_data.kline_daily"},
            markets={Market.CN},
        )
        fresh_registry.register(provider)
        assert fresh_registry.has_capability("market_data.kline_daily") is True
        assert fresh_registry.has_capability("market_data.kline_daily", Market.CN) is True
        assert fresh_registry.has_capability("market_data.kline_daily", Market.HK) is False
        assert fresh_registry.has_capability("other.op") is False

    def test_list_capabilities_unioned_across_providers(
        self, fresh_registry, make_provider
    ):
        fresh_registry.register(
            make_provider(name="a", capabilities={"a.1", "a.2"})
        )
        fresh_registry.register(make_provider(name="b", capabilities={"b.1"}))
        assert fresh_registry.list_capabilities() == {"a.1", "a.2", "b.1"}

    def test_get_returns_named_provider(self, fresh_registry, make_provider):
        provider = make_provider(name="alpha", capabilities={"x.read"})
        fresh_registry.register(provider)
        assert fresh_registry.get("alpha") is provider
        assert fresh_registry.get("missing") is None