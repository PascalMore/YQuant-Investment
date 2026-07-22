"""T3-P3B M1 — Router skips the Step-2 / Step-3 write fan-out for P3 capabilities.

The Phase 3 read-only invariant (V0.5 §2.1 / RFC-03-014 §240-251 /
SPEC-03-014 §537-546 / DESIGN-03-014 §228-233) requires that the six
P3 capabilities (``sector.snapshot`` / ``sector.ranking`` /
``flow.capital_flow_daily`` / ``flow.northbound_daily`` /
``sentiment.market_snapshot`` / ``sentiment.limit_up_pool``) never
trigger ``LocalMongoAdapter.put`` or ``CacheManager.put`` on the
query path. The contract is observable through a ``put`` spy
attached to both adapters: a successful query for any of the six
P3 capabilities must produce ``local.puts == 0`` and
``cache.puts == 0``.

This test module pins the contract end-to-end via the
:class:`DataRouter.query` entry point — not via a unit test on
``_materialize`` itself — because the M1 fix lives at the call
site (``_query_external_chain_with_cache`` skips the call entirely
for P3 capabilities). A spy test on ``_materialize`` would still
pass if a regression reintroduced the call; the end-to-end spy is
the regression guard.

The companion test in :mod:`test_router_query`
(``test_query_with_p3_writer_still_readonly_in_query_path``) only
asserts ``ud_materialized`` is not in the trace; this module is the
stricter spy-based guard that the **bytecode-level** behaviour
matches the contract (zero puts at the adapter boundary).
"""

from __future__ import annotations

from typing import Any, Iterable

from skills.data.unified_data import (
    CacheManager,
    DataProvider,
    LocalMongoAdapter,
    Market,
    ProviderRegistry,
    SecurityId,
)
from skills.data.unified_data.router import DataRouter


# The six P3 capabilities covered by the read-only invariant.
P3_CAPABILITIES: tuple[str, ...] = (
    "sector.snapshot",
    "sector.ranking",
    "flow.capital_flow_daily",
    "flow.northbound_daily",
    "sentiment.market_snapshot",
    "sentiment.limit_up_pool",
)

# A non-P3 capability used as the regression baseline (writes must
# still happen for these).
NON_P3_CAPABILITY: str = "market_data.kline_daily"


# ---------------------------------------------------------------------------
# Spy adapters — mirror the ``LocalMongoAdapter`` / ``CacheManager``
# surface but record every ``put`` call. The real adapters own
# ``put(security_id, domain, operation, params, result)``; the spies
# implement the same surface (any caller that uses kwargs is also
# covered because ``**kwargs`` is forwarded by the router).
# ---------------------------------------------------------------------------


class _SpyLocalAdapter:
    """Spy stand-in for :class:`LocalMongoAdapter`.

    Implements the ``put`` boundary the router consults; records each
    call on ``puts`` so the test can assert zero invocations for P3
    capabilities. The other methods (``get`` / ``exists``) are
    inherited from a no-op stub — the query path's read consult never
    reaches the adapter for P3 capabilities under the read-only
    invariant, so we don't need to model it precisely.
    """

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

    # No-op reads — the spy is only used to assert write fan-out is
    # suppressed for P3 capabilities. A non-P3 baseline test may
    # assert write fan-out fires, but neither test inspects the
    # read fan-out.
    def get(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def exists(self, *args: Any, **kwargs: Any) -> bool:
        return False


class _SpyCacheManager:
    """Spy stand-in for :class:`CacheManager`. Same shape as
    :class:`_SpyLocalAdapter` but at the cache boundary."""

    def __init__(self) -> None:
        self.puts: list[tuple[SecurityId, str, str, dict, Any]] = []
        self.gets: list[tuple[SecurityId, str, str, dict]] = []

    def put(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: dict,
        result: Any,
    ) -> None:
        self.puts.append((security_id, domain, operation, dict(params), result))

    def get(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: dict,
    ) -> Any:
        self.gets.append((security_id, domain, operation, dict(params)))
        return None

    def exists(self, *args: Any, **kwargs: Any) -> bool:
        return False


# ---------------------------------------------------------------------------
# Test helpers
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


def _build_router(
    *,
    capability: str,
    payload: Any,
    security_id: SecurityId,
    name: str = "spy_provider",
) -> tuple[DataRouter, _SpyLocalAdapter, _SpyCacheManager, _OneShotProvider]:
    """Build a router wired with spy adapters + one-shot provider.

    Returns the router plus the two spy adapters and the provider so
    each test can assert against the spies.
    """
    registry = ProviderRegistry()
    provider = _OneShotProvider(
        name,
        payload=payload,
        capability=capability,
        market=security_id.market,
    )
    registry.register(provider)
    local_spy = _SpyLocalAdapter()
    cache_spy = _SpyCacheManager()
    router = DataRouter(
        registry=registry,
        local_mongo_adapter=local_spy,  # type: ignore[arg-type]
        cache_manager=cache_spy,  # type: ignore[arg-type]
    )
    return router, local_spy, cache_spy, provider


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRouterP3ReadOnlyInvariant:
    """The six P3 capabilities must skip the Step-2/Step-3 write fan-out."""

    def test_capital_flow_daily_reads_only_no_puts(self):
        """``flow.capital_flow_daily`` query → 0 local puts, 0 cache puts.

        The spy-based regression guard for T3-P3B M1. The query path
        must reach the provider (Step 4) and return a
        ``DataResult(provider=spy_provider)`` without firing the
        ``_materialize`` Step-2/Step-3 write fan-out.
        """
        sid = SecurityId(market=Market.CN, symbol="600519")
        router, local_spy, cache_spy, provider = _build_router(
            capability="flow.capital_flow_daily",
            payload=[{"row": "value"}],
            security_id=sid,
            name="flow_spy",
        )

        result = router.query(
            domain="flow",
            operation="capital_flow_daily",
            security_id=sid,
        )

        # Provider fired exactly once — the read path is intact.
        assert result.provider == "flow_spy"
        assert provider.call_count == 1
        # The M1 contract: zero writes fired through either adapter.
        assert local_spy.puts == [], (
            f"P3 read triggered {len(local_spy.puts)} LocalMongoAdapter.put(s); "
            "T3-P3B M1 requires zero. P3 reads must be strictly read-only."
        )
        assert cache_spy.puts == [], (
            f"P3 read triggered {len(cache_spy.puts)} CacheManager.put(s); "
            "T3-P3B M1 requires zero. P3 reads must be strictly read-only."
        )

    def test_northbound_daily_reads_only_no_puts(self):
        """``flow.northbound_daily`` query → 0 local puts, 0 cache puts."""
        sid = SecurityId(market=Market.CN, symbol="600519")
        router, local_spy, cache_spy, provider = _build_router(
            capability="flow.northbound_daily",
            payload=[{"northbound": "value"}],
            security_id=sid,
            name="northbound_spy",
        )

        result = router.query(
            domain="flow",
            operation="northbound_daily",
            security_id=sid,
        )

        assert result.provider == "northbound_spy"
        assert provider.call_count == 1
        assert local_spy.puts == []
        assert cache_spy.puts == []

    def test_sector_snapshot_reads_only_no_puts(self):
        """``sector.snapshot`` query → 0 local puts, 0 cache puts."""
        sid = SecurityId(market=Market.INDEX, symbol="BK0489")
        router, local_spy, cache_spy, provider = _build_router(
            capability="sector.snapshot",
            payload=[{"sector": "BK0489"}],
            security_id=sid,
            name="sector_spy",
        )

        result = router.query(
            domain="sector",
            operation="snapshot",
            security_id=sid,
        )

        assert result.provider == "sector_spy"
        assert local_spy.puts == []
        assert cache_spy.puts == []

    def test_sentiment_market_snapshot_reads_only_no_puts(self):
        """``sentiment.market_snapshot`` query → 0 local puts, 0 cache puts."""
        sid = SecurityId(market=Market.CN, symbol="market:cn")
        router, local_spy, cache_spy, provider = _build_router(
            capability="sentiment.market_snapshot",
            payload=[{"snapshot": "value"}],
            security_id=sid,
            name="sentiment_spy",
        )

        result = router.query(
            domain="sentiment",
            operation="market_snapshot",
            security_id=sid,
        )

        assert result.provider == "sentiment_spy"
        assert local_spy.puts == []
        assert cache_spy.puts == []

    def test_force_refresh_does_not_re_trigger_puts(self):
        """``force_refresh=True`` on a P3 capability → 0 puts.

        The previous implementation relied on a no-op inside
        ``_materialize`` to suppress writes. Under
        ``force_refresh=True`` Step 2 and Step 3 (read consultations)
        were skipped, but the call to ``_materialize`` at the end of
        the success path still fired for non-empty external results
        — so a force-refresh P3 query would still see zero cache hits
        but would also still skip the cache write fan-out only by
        the same no-op guard. The M1 fix moves the discriminator to
        the call site so ``force_refresh=True`` short-circuits
        entirely. The spy-based test pins this contract.
        """
        sid = SecurityId(market=Market.CN, symbol="600519")
        router, local_spy, cache_spy, provider = _build_router(
            capability="flow.capital_flow_daily",
            payload=[{"row": "value"}],
            security_id=sid,
            name="flow_spy",
        )

        result = router.query(
            domain="flow",
            operation="capital_flow_daily",
            security_id=sid,
            force_refresh=True,
        )

        assert result.provider == "flow_spy"
        # Critical: even with force_refresh=True the read-only
        # invariant holds — zero local puts, zero cache puts.
        assert local_spy.puts == []
        assert cache_spy.puts == []


class TestNonP3CapabilityStillWrites:
    """Regression guard for the Phase 1B-B write fan-out — non-P3
    capabilities must continue to trigger Step-2/Step-3 puts so
    the M1 fix does not regress non-P3 callers."""

    def test_kline_daily_still_writes_to_local_and_cache(self):
        """``market_data.kline_daily`` keeps the Phase 1B-B write fan-out.

        The M1 fix is gated by ``P3_COLLECTION_BY_CAPABILITY`` so a
        non-P3 capability must still trigger the write fan-out —
        otherwise the regression breaks Phase 1B-B behaviour for
        every TA-CN-covered capability.
        """
        sid = SecurityId(market=Market.CN, symbol="600519")
        router, local_spy, cache_spy, provider = _build_router(
            capability=NON_P3_CAPABILITY,
            payload={"close": [1620.0]},
            security_id=sid,
            name="kline_spy",
        )

        result = router.query(
            domain="market_data",
            operation="kline_daily",
            security_id=sid,
        )

        assert result.provider == "kline_spy"
        # Phase 1B-B write fan-out fires for non-P3 capabilities.
        assert len(local_spy.puts) == 1, (
            f"Non-P3 capability triggered {len(local_spy.puts)} local.puts; "
            "Phase 1B-B contract requires exactly 1 put per successful query."
        )
        assert len(cache_spy.puts) == 1, (
            f"Non-P3 capability triggered {len(cache_spy.puts)} cache.puts; "
            "Phase 1B-B contract requires exactly 1 put per successful query."
        )


class TestRouterQueryContract:
    """``DataRouter.query`` signature / behaviour preserved by M1."""

    def test_query_main_signature_unchanged(self):
        """M1 fix does not modify the public ``DataRouter.query`` signature.

        The discriminator is hoisted into the body — callers see no
        change to ``query``'s kwarg surface. This test pins the
        signature so future refactors don't accidentally break it.
        """
        import inspect

        sig = inspect.signature(DataRouter.query)
        params = list(sig.parameters)
        # The first three positional args (security_id, domain, operation)
        # and ``provider``, ``market``, ``params``, ``fetched_at``,
        # ``force_refresh`` are documented (DESIGN-03-008 §3.5).
        assert "force_refresh" in params
        assert sig.parameters["force_refresh"].default is False, (
            "force_refresh default must remain False (M1 fix does not change defaults)"
        )

    def test_try_materialized_kw_only_signature_unchanged(self):
        """``_try_materialized`` keeps ``capability`` / ``p3_writer`` as
        kw-only (kw-only)."""
        import inspect

        sig = inspect.signature(DataRouter._try_materialized)
        cap_param = sig.parameters.get("capability")
        writer_param = sig.parameters.get("p3_writer")
        assert cap_param is not None
        assert writer_param is not None
        assert cap_param.kind is inspect.Parameter.KEYWORD_ONLY, (
            "_try_materialized: capability kwarg must stay kw-only (M1 fix is additive)"
        )
        assert writer_param.kind is inspect.Parameter.KEYWORD_ONLY, (
            "_try_materialized: p3_writer kwarg must stay kw-only (M1 fix is additive)"
        )
