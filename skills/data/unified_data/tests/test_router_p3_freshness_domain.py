"""Router freshness-domain resolution spy tests (SPEC-03-014-F6 V-4 / C-5).

Proves the runtime freshness/cache TTL consult for sentiment
capabilities resolves to the canonical freshness domain key
(``market_sentiment`` / ``sentiment_limit_up_pool``) and never to the
capability-domain prefix ``sentiment`` (RFC-03-014-F6 §3.1 / C-2 / C-5).
Non-sentiment capabilities keep their identity mapping so the Phase 1B-B
behaviour is byte-for-byte unchanged.

Coverage layers (DESIGN-03-014-F6 §4.2):

* ① ``_freshness_domain_for`` mapping assertion — canonical for the two
  sentiment capabilities, identity for everything else.
* ② label-domain spy on the empty-result branch — observable because
  ``label`` is actually invoked there (``from_cache=False``).
* ③ ``_materialize`` put-domain derivation — the TTL consult inside
  ``CacheManager.put`` / ``LocalMongoAdapter.put`` flows from the
  resolution function (identity for non-P3; canonical for sentiment
  when the P3 guard is bypassed).
* ④ P3 read-only invariant — ``_materialize`` with a sentiment
  capability stays a no-op (zero puts).

Zero real I/O — mongomock-free, ``unittest.mock``-free pure spies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from skills.data.unified_data.freshness import FreshnessPolicy
from skills.data.unified_data.models import DataResult, Market, SecurityId
from skills.data.unified_data.provider import DataProvider
from skills.data.unified_data.registry import ProviderRegistry
from skills.data.unified_data.router import DataRouter


# ---------------------------------------------------------------------------
# Recording freshness policy — records the ``domain`` arg of every call
# ---------------------------------------------------------------------------


class _RecordingFreshnessPolicy(FreshnessPolicy):
    """FreshnessPolicy spy — records the ``domain`` arg of every call."""

    def __init__(self) -> None:
        super().__init__()
        self.label_domains: list[str] = []
        self.get_ttl_domains: list[str] = []

    def label(self, fetched_at, data_date, domain, from_cache):
        self.label_domains.append(domain)
        return super().label(fetched_at, data_date, domain, from_cache)

    def get_ttl(self, domain: str) -> int:
        self.get_ttl_domains.append(domain)
        return super().get_ttl(domain)


# ---------------------------------------------------------------------------
# Spy adapters — mirror the LocalMongoAdapter / CacheManager ``put``
# surface but record every call. Same shape as the spies in
# ``test_router_p3_readonly.py``.
# ---------------------------------------------------------------------------


class _SpyLocalAdapter:
    """Spy stand-in for :class:`LocalMongoAdapter`."""

    def __init__(self) -> None:
        self.puts: list[tuple[SecurityId, str, str, dict, Any]] = []

    def put(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: dict,
        result: Any,
    ) -> None:
        self.puts.append((security_id, domain, operation, dict(params), result))

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def exists(self, *args: Any, **kwargs: Any) -> bool:
        return False


class _SpyCacheManager:
    """Spy stand-in for :class:`CacheManager`. Same shape as
    :class:`_SpyLocalAdapter` but at the cache boundary."""

    def __init__(self) -> None:
        self.puts: list[tuple[SecurityId, str, str, dict, Any]] = []

    def put(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: dict,
        result: Any,
    ) -> None:
        self.puts.append((security_id, domain, operation, dict(params), result))

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def exists(self, *args: Any, **kwargs: Any) -> bool:
        return False


# ---------------------------------------------------------------------------
# One-shot provider — returns ``payload`` on every fetch
# ---------------------------------------------------------------------------


class _OneShotProvider(DataProvider):
    """Single-shot provider — returns ``payload`` once, then empty."""

    def __init__(
        self,
        name: str,
        *,
        payload: Any,
        capability: str,
        market: Market = Market.CN,
    ) -> None:
        self._name = name
        self._payload = payload
        self._capability = capability
        self._market = market
        self._available = True
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> set[str]:
        return {self._capability}

    @property
    def markets(self) -> set[Market]:
        return {self._market}

    def is_available(self) -> bool:
        return self._available

    def fetch(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        **params: Any,
    ) -> Any:
        self.call_count += 1
        return self._payload


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _build_router(
    *,
    capability: str,
    payload: Any,
    security_id: SecurityId,
    name: str = "spy_provider",
) -> tuple[DataRouter, _RecordingFreshnessPolicy, _SpyLocalAdapter, _SpyCacheManager]:
    """Build a router wired with a recording freshness policy, spy
    adapters and a one-shot provider."""
    registry = ProviderRegistry()
    provider = _OneShotProvider(
        name,
        payload=payload,
        capability=capability,
        market=security_id.market,
    )
    registry.register(provider)
    freshness = _RecordingFreshnessPolicy()
    local_spy = _SpyLocalAdapter()
    cache_spy = _SpyCacheManager()
    router = DataRouter(
        registry=registry,
        local_mongo_adapter=local_spy,  # type: ignore[arg-type]
        cache_manager=cache_spy,  # type: ignore[arg-type]
        freshness=freshness,
    )
    return router, freshness, local_spy, cache_spy


def _fake_result() -> DataResult:
    """A minimal non-empty :class:`DataResult` for ``_materialize`` calls."""
    return DataResult(
        data=[{"row": 1}],
        security_id=SecurityId(market=Market.CN, symbol="600519"),
        domain="market_data",
        operation="kline_daily",
        provider="spy_provider",
        fetched_at=datetime(2026, 8, 2, 12, 0, 0),
        source_trace=[],
        freshness="delayed",
    )


# ---------------------------------------------------------------------------
# ① Mapping assertions
# ---------------------------------------------------------------------------


class TestFreshnessDomainMapping:
    def test_freshness_domain_mapping_is_canonical(self):
        """``_freshness_domain_for`` returns canonical keys for sentiment
        and identity for everything else."""
        router = DataRouter(registry=ProviderRegistry())
        assert (
            router._freshness_domain_for("sentiment.market_snapshot")
            == "market_sentiment"
        )
        assert (
            router._freshness_domain_for("sentiment.limit_up_pool")
            == "sentiment_limit_up_pool"
        )
        # identity — sector / flow / non-P3 unchanged
        assert router._freshness_domain_for("sector.snapshot") == "sector"
        assert router._freshness_domain_for("flow.capital_flow_daily") == "flow"
        assert router._freshness_domain_for("market_data.kline_daily") == "market_data"


# ---------------------------------------------------------------------------
# ② label-domain spy (empty-result branch)
# ---------------------------------------------------------------------------


class TestRouterLabelDomainSpy:
    def test_sentiment_market_snapshot_query_label_uses_canonical_domain(self):
        """Empty external result → label() receives ``market_sentiment``,
        never ``sentiment`` (C-5)."""
        sid = SecurityId(market=Market.CN, symbol="market:cn")
        router, freshness, _local_spy, _cache_spy = _build_router(
            capability="sentiment.market_snapshot", payload=[], security_id=sid
        )

        router.query(
            domain="sentiment", operation="market_snapshot", security_id=sid
        )

        assert "market_sentiment" in freshness.label_domains
        assert "sentiment" not in freshness.label_domains

    def test_sentiment_limit_up_pool_query_label_uses_canonical_domain(self):
        """Empty external result → label() receives
        ``sentiment_limit_up_pool``, never ``sentiment`` (C-5)."""
        sid = SecurityId(market=Market.CN, symbol="limit_up_pool:2026-08-01")
        router, freshness, _local_spy, _cache_spy = _build_router(
            capability="sentiment.limit_up_pool", payload=[], security_id=sid
        )

        router.query(
            domain="sentiment", operation="limit_up_pool", security_id=sid
        )

        assert "sentiment_limit_up_pool" in freshness.label_domains
        assert "sentiment" not in freshness.label_domains

    def test_non_sentiment_label_domain_is_identity(self):
        """A non-P3 query keeps the identity freshness domain — the
        Phase 1B-B behaviour is unchanged."""
        sid = SecurityId(market=Market.CN, symbol="600519")
        router, freshness, _local_spy, _cache_spy = _build_router(
            capability="market_data.kline_daily", payload=[], security_id=sid
        )

        router.query(
            domain="market_data", operation="kline_daily", security_id=sid
        )

        assert "market_data" in freshness.label_domains

    def test_get_ttl_never_receives_sentiment_on_query_path(self):
        """No sentiment-capability query path may call get_ttl with the
        capability-domain prefix ``sentiment`` (C-2/C-5). P3 read-only
        invariant keeps _materialize (the only get_ttl consumer) off the
        query path, and label(from_cache=False) never consults TTL."""
        sid = SecurityId(market=Market.CN, symbol="market:cn")
        router, freshness, _local_spy, _cache_spy = _build_router(
            capability="sentiment.market_snapshot", payload=[{"row": 1}], security_id=sid
        )

        router.query(
            domain="sentiment", operation="market_snapshot", security_id=sid
        )

        assert "sentiment" not in freshness.get_ttl_domains


# ---------------------------------------------------------------------------
# ③ _materialize put-domain derivation
# ---------------------------------------------------------------------------


class TestMaterializePutDomain:
    def test_materialize_put_domain_derived_from_capability(self):
        """Direct _materialize call with a NON-P3 capability → the put
        domain equals ``_freshness_domain_for(capability)`` (identity);
        proves the TTL consult inside CacheManager.put /
        LocalMongoAdapter.put flows from the resolution function (C-5)."""
        sid = SecurityId(market=Market.CN, symbol="600519")
        router, _freshness, local_spy, cache_spy = _build_router(
            capability="market_data.kline_daily", payload=[{"row": 1}], security_id=sid
        )
        router._materialize(
            sid, "market_data", "kline_daily", {}, _fake_result(),
            capability="market_data.kline_daily",
        )
        assert local_spy.puts[0][1] == "market_data"  # put domain == identity
        assert cache_spy.puts[0][1] == "market_data"

    def test_materialize_sentiment_put_domain_uses_canonical_key(self):
        """Direct _materialize call where the P3 guard is bypassed (an
        operation not registered in ``P3_COLLECTION_BY_CAPABILITY``) →
        the put domain resolves to the canonical freshness key, never the
        raw ``sentiment`` prefix (C-5). Guards the future-proofing case
        of DESIGN-03-014-F6 §2.1 F-7: if the read-only guard is ever
        relaxed or a non-P3 sentiment capability is added, the TTL
        consult must still hit the canonical key."""
        sid = SecurityId(market=Market.CN, symbol="600519")
        router, _freshness, local_spy, cache_spy = _build_router(
            capability="sentiment.market_snapshot", payload=[{"row": 1}], security_id=sid
        )
        router._materialize(
            sid, "sentiment", "non_p3_operation", {}, _fake_result(),
            capability="sentiment.market_snapshot",
        )
        assert local_spy.puts[0][1] == "market_sentiment"
        assert cache_spy.puts[0][1] == "market_sentiment"


# ---------------------------------------------------------------------------
# ④ P3 read-only invariant regression
# ---------------------------------------------------------------------------


class TestMaterializeReadOnlyInvariant:
    def test_p3_sentiment_materialize_still_readonly(self):
        """P3 guard unchanged: _materialize with a sentiment capability
        is a no-op (zero puts) — the read-only invariant is preserved
        (V-5 compatibility with test_router_p3_readonly)."""
        sid = SecurityId(market=Market.CN, symbol="market:cn")
        router, _freshness, local_spy, cache_spy = _build_router(
            capability="sentiment.market_snapshot", payload=[{"row": 1}], security_id=sid
        )
        router._materialize(
            sid, "sentiment", "market_snapshot", {}, _fake_result(),
            capability="sentiment.market_snapshot",
        )
        assert local_spy.puts == []
        assert cache_spy.puts == []
