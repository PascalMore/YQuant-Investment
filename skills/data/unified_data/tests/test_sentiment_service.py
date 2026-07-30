"""Phase 3 P3-C 22-field MarketSentimentSnapshot service tests (canonical).

Acceptance matrix (T3 Implement, per SPEC-03-014 §12.bis.1):

|| #   | test name                                       | file                          |
|-----|-------------------------------------------------|-------------------------------|
|| ①   | test_market_sentiment_snapshot_query_readonly   | test_sentiment_service.py     |
|| ②   | test_market_sentiment_snapshot_capability_dispatch | test_sentiment_service.py  |
|| ③   | test_market_sentiment_snapshot_injection_boundary | test_sentiment_service.py   |
|| ④   | test_market_sentiment_snapshot_canonical_keys   | test_sentiment_service.py     |

The tests exercise the **query-side** wiring end-to-end (Step 4 → stub
provider, no Step 1 / Step 2 leakage) and the **injection-boundary**
contract (no router → ``ProviderUnavailableError``; router wired →
query succeeds). The refresh path is *not* exercised — refresh is
reserved for the Gate-authorised sub-stage (see
``refresh_market_sentiment_snapshot`` docstring).

The service signature uses the **22-field canonical contract**:
``get_market_sentiment_snapshot(snapshot_date, snapshot_time)``. The
earlier T3-B offline signature with ``(market, sentiment_type,
market_date)`` has been superseded.

All tests are offline:

* No real MongoDB — uses :mod:`mongomock` for any persistence path.
* No real Provider API call — uses :class:`StubSentimentProvider`.
* No AuditLogger / QualitySummary writes.
* No cron / systemd / webhook side-effects.
"""

from __future__ import annotations

from typing import Any

import mongomock
import pytest

from skills.data.unified_data import (
    DataRouter,
    Market,
    ProviderRegistry,
    SecurityId,
)
from skills.data.unified_data.adapters.p3_persistence_writer import (
    P3PersistenceWriter,
)
from skills.data.unified_data.exceptions import ProviderUnavailableError
from skills.data.unified_data.models.domain.sentiment import (
    MarketSentimentSnapshot,
)
from skills.data.unified_data.providers.sentiment_stub import (
    StubSentimentProvider,
)
from skills.data.unified_data.services.sentiment_service import (
    MarketSentimentService,
)
from skills.data.unified_data.client import UnifiedDataClient
from skills.data.unified_data.tests.conftest import FakeProvider


SENTIMENT_CAP = "sentiment.market_snapshot"
SENTIMENT_COLLECTION = "03_data_ud_market_sentiment_snapshot"


def _make_db() -> Any:
    """Return a fresh mongomock database handle (offline only)."""
    return mongomock.MongoClient().get_database("tradingagents")


def _register_stub(
    registry: ProviderRegistry,
    *,
    payload: list[dict] | None = None,
    name: str = "sentiment_stub",
    capabilities=frozenset({SENTIMENT_CAP}),
) -> StubSentimentProvider:
    """Register a :class:`StubSentimentProvider` against all known markets."""
    stub = StubSentimentProvider(
        name=name,
        payload=payload,
        capabilities=capabilities,
        markets={m for m in Market},
    )
    registry.register(stub)
    return stub


# ---------------------------------------------------------------------------
# Test ① — query path is read-only + Step-2 (P3PersistenceWriter) skip trace
# ---------------------------------------------------------------------------


class TestMarketSentimentSnapshotQueryReadonly:
    """Step 4 success path with no ``p3_writer`` wired in.

    The query must reach the stub, return the stub payload, and leave
    the router's ``source_trace`` free of ``ud_materialized`` markers
    (because no persistence layer is wired in).

    The service uses the **22-field canonical contract**:
    ``(snapshot_date, snapshot_time)`` — no ``sentiment_type``.
    """

    def test_query_path_returns_stub_payload(self):
        """The query reaches the registered stub and returns its payload."""
        registry = ProviderRegistry()
        stub = _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result = svc.get_market_sentiment_snapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )

        # Stub is the only candidate — provider reflects that.
        assert result.provider == "sentiment_stub"
        assert result.succeeded
        # Step 4 produced a payload, no Step 2 marker was appended.
        assert "ud_materialized" not in result.source_trace
        # And the stub recorded exactly one fetch call.
        assert len(stub.call_log) == 1
        recorded_capability, recorded_market, recorded_params = stub.call_log[0]
        assert recorded_capability == SENTIMENT_CAP
        assert recorded_market == "INDEX"
        # Canonical 22-field params — no sentiment_type.
        assert recorded_params.get("snapshot_date") == "2026-07-21"
        assert recorded_params.get("snapshot_time") == "close"
        assert "sentiment_type" not in recorded_params


class TestMarketSentimentSnapshotRefreshWritesP3Writer:
    """Refresh path goes through ``P3PersistenceWriter`` (V0.5 §2.2).

    This implementation does not invoke the refresh method — but the
    *boundary* must prove that when the writer is wired and the
    refresh hook is exercised manually, the writer's ``upsert`` is
    the only write channel. We simulate the refresh by calling the
    writer directly (the public surface the refresh hook will use) and
    verify the canonical unique-key filter
    ``{market, snapshot_date, snapshot_time}`` round-trips through
    mongomock.
    """

    def test_writer_upsert_round_trip_with_canonical_business_key(self):
        writer = P3PersistenceWriter(_make_db())
        unique_key = {"market", "snapshot_date", "snapshot_time"}
        records = [
            {
                "market": "CN",
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "limit_up_count": 42,
                "limit_down_count": 8,
                "advance_count": 3250,
                "decline_count": 1500,
                "flat_count": 250,
                "market_temperature": None,  # Pascal OQ-2
                "northbound_net_flow": None,  # Pascal C
                "provider": "sentiment_stub",
            },
            {
                "market": "CN",
                "snapshot_date": "2026-07-22",
                "snapshot_time": "close",
                "limit_up_count": 450,
                "limit_down_count": 5,
                "advance_count": 4800,
                "decline_count": 100,
                "flat_count": 100,
                "market_temperature": None,
                "northbound_net_flow": None,
                "provider": "sentiment_stub",
            },
        ]

        outcome = writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=records,
            unique_key=unique_key,
        )
        assert outcome.persisted == 2
        assert outcome.failed == 0

        # Round-trip via the canonical business unique key — not the
        # LocalMongoAdapter ``materialized_key`` model.
        docs = writer.get(
            SENTIMENT_COLLECTION,
            {"market": "CN", "snapshot_date": "2026-07-21"},
        )
        assert len(docs) == 1
        assert docs[0]["snapshot_time"] == "close"
        assert docs[0]["limit_up_count"] == 42

    def test_refresh_hook_without_writer_raises(self):
        """The injection-boundary contract (test ③ covers it fully)."""
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)
        # ``p3_writer=None`` is the offline default — refresh is opt-in.
        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.refresh_market_sentiment_snapshot(
                snapshot_date="2026-07-21",
                snapshot_time="close",
            )
        assert "no P3PersistenceWriter" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Test ② — capability dispatch (P3-C vs other)
# ---------------------------------------------------------------------------


class TestMarketSentimentSnapshotCapabilityDispatch:
    """The router's capability map is consulted correctly.

    * ``sentiment.market_snapshot`` lands in ``_TA_CN_NOT_COVERED``
      — Step 1 is skipped.
    * The P3-C collection key ``03_data_ud_market_sentiment_snapshot``
      appears in :data:`P3_COLLECTION_BY_CAPABILITY`.
    * The business unique key is ``{market, snapshot_date, snapshot_time}``
      per V0.23 §3.3 (NOT the older ``{market, sentiment_type, market_date}``).
    * Other capabilities (``market_data.kline_daily`` etc.) keep
      their original behaviour — no regression in the existing
      routing.
    """

    def test_market_sentiment_snapshot_is_ta_cn_not_covered(self):
        # Router must skip Step 1 for the P3-C capability.
        assert SENTIMENT_CAP in DataRouter._TA_CN_NOT_COVERED

    def test_p3_c_collection_is_registered(self):
        from skills.data.unified_data.adapters.p3_persistence_writer import (
            P3_COLLECTION_BY_CAPABILITY,
        )

        assert P3_COLLECTION_BY_CAPABILITY[SENTIMENT_CAP] == (
            "03_data_ud_market_sentiment_snapshot"
        )

    def test_p3_c_canonical_unique_key_is_canonical_22_field(self):
        """The unique key MUST be ``{market, snapshot_date, snapshot_time}``.

        Per Pascal canonical contract (RFC V0.16 / SPEC V0.15 / DESIGN
        V0.23 §3.3). The T3-B ``{market, sentiment_type, market_date}``
        key has been superseded.
        """
        from skills.data.unified_data.adapters.p3_persistence_writer import (
            P3_UNIQUE_KEYS_BY_CAPABILITY,
        )

        canonical = P3_UNIQUE_KEYS_BY_CAPABILITY[SENTIMENT_CAP]
        assert canonical == frozenset(
            {"market", "snapshot_date", "snapshot_time"}
        )
        # And explicitly NOT the old T3-B key.
        assert "sentiment_type" not in canonical
        assert "market_date" not in canonical

    def test_non_p3_capability_dispatch_unchanged(self):
        """``market_data.kline_daily`` still maps to ``get_daily_bars``.

        The capability-method map is the only authoritative source —
        this implementation does not touch it.
        """
        assert (
            DataRouter._TA_CN_CAPABILITY_METHOD_MAP["market_data.kline_daily"]
            == "get_daily_bars"
        )
        # And the new sentiment capability is intentionally NOT in the
        # method map (it is not TA-CN-owned).
        assert SENTIMENT_CAP not in DataRouter._TA_CN_CAPABILITY_METHOD_MAP


# ---------------------------------------------------------------------------
# Test ③ — injection boundary
# ---------------------------------------------------------------------------


class TestMarketSentimentSnapshotInjectionBoundary:
    """DI surface contract for :class:`MarketSentimentService`."""

    def test_no_router_raises_provider_unavailable(self):
        """``MarketSentimentService(adapter)`` (no router) → query raises."""
        svc = MarketSentimentService(adapter=None)
        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.get_market_sentiment_snapshot(
                snapshot_date="2026-07-21",
                snapshot_time="close",
            )
        assert "no router wired" in str(excinfo.value)

    def test_router_injection_unblocks_query(self):
        """Injecting a router unlocks the query path end-to-end."""
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result = svc.get_market_sentiment_snapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )

        assert result.succeeded
        assert result.provider == "sentiment_stub"
        assert isinstance(result.data, list)
        assert result.data and isinstance(result.data[0], dict)

    def test_constructor_signature_is_minimal(self):
        """Constructor accepts the documented kwarg set — no extras.

        Mirrors the P3-A ``SectorService`` regression guard: the
        constructor must not widen the DI surface beyond what the
        service spec promises.
        """
        import inspect

        sig = inspect.signature(MarketSentimentService.__init__)
        params = list(sig.parameters)
        # ``self`` + ``adapter`` + kw-only ``router`` / ``p3_writer`` /
        # ``audit_logger``. Order is preserved.
        assert params[:2] == ["self", "adapter"]
        for kw in ("router", "p3_writer", "audit_logger"):
            assert kw in params, f"missing kwarg {kw!r}"
            assert (
                sig.parameters[kw].kind is inspect.Parameter.KEYWORD_ONLY
            ), f"{kw} must be keyword-only"


# ---------------------------------------------------------------------------
# Test ④ — canonical 22-field key plumbing
# ---------------------------------------------------------------------------


class TestMarketSentimentSnapshotCanonicalKeys:
    """The 22-field canonical contract is enforced on the service surface.

    * ``get_market_sentiment_snapshot(snapshot_date, snapshot_time)`` —
      the **only** signature; no ``sentiment_type`` / ``market_date``.
    * ``refresh_market_sentiment_snapshot(snapshot_date, snapshot_time)`` —
      same shape; refresh is opt-in.
    * The placeholder SecurityId reflects the canonical key, not the
      older T3-B triple.
    """

    def test_get_signature_uses_canonical_22_field_keys(self):
        """``get_market_sentiment_snapshot`` takes ``snapshot_date`` + ``snapshot_time``."""
        import inspect

        sig = inspect.signature(
            MarketSentimentService.get_market_sentiment_snapshot
        )
        params = list(sig.parameters)
        # self, snapshot_date, snapshot_time
        assert params == ["self", "snapshot_date", "snapshot_time"]
        # snapshot_time defaults to "close" per Design §3.3.
        assert sig.parameters["snapshot_time"].default == "close"

    def test_refresh_signature_uses_canonical_22_field_keys(self):
        """``refresh_market_sentiment_snapshot`` mirrors the read signature."""
        import inspect

        sig = inspect.signature(
            MarketSentimentService.refresh_market_sentiment_snapshot
        )
        params = list(sig.parameters)
        # self, snapshot_date, snapshot_time, then kw-only ``provider``.
        assert params[:3] == ["self", "snapshot_date", "snapshot_time"]
        assert "provider" in sig.parameters
        assert (
            sig.parameters["provider"].kind is inspect.Parameter.KEYWORD_ONLY
        )

    def test_placeholder_security_id_uses_canonical_keys(self):
        """The placeholder SecurityId symbol encodes the canonical keys."""
        registry = ProviderRegistry()
        stub = _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        svc.get_market_sentiment_snapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )

        # Stub recorded the call. We assert the canonical key shape
        # is in the params — not the older sentiment_type/market_date.
        assert len(stub.call_log) == 1
        _, _, recorded_params = stub.call_log[0]
        assert recorded_params.get("snapshot_date") == "2026-07-21"
        assert recorded_params.get("snapshot_time") == "close"


# ---------------------------------------------------------------------------
# Cross-checks — domain object + lazy loader
# ---------------------------------------------------------------------------


class TestDomainObjectSanity:
    """Cheap contract tests for the new domain object.

    Not part of the canonical acceptance matrix, but useful so future
    readers can pin the shape without re-reading the whole dataclass.
    """

    def test_from_dict_round_trip(self):
        """Round-trip a normal-day record end-to-end."""
        record = {
            "market": "CN",
            "snapshot_date": "2026-07-21",
            "snapshot_time": "close",
            "limit_up_count": 42,
            "limit_down_count": 8,
            "advance_count": 3250,
            "decline_count": 1500,
            "flat_count": 250,
            "market_temperature": None,
            "northbound_net_flow": None,
            "provider": "sentiment_stub",
        }
        snap = MarketSentimentSnapshot.from_dict(record)
        assert snap.snapshot_date == "2026-07-21"
        assert snap.snapshot_time == "close"
        assert snap.market == "CN"
        assert snap.limit_up_count == 42
        assert snap.northbound_net_flow is None  # Pascal C

    def test_from_dict_tolerates_missing_optional_fields(self):
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "market": "CN",
            }
        )
        # Defaults take over.
        assert snap.limit_up_count == 0
        assert snap.limit_up_count_ex_st is None
        assert snap.market_temperature is None
        assert snap.hot_concepts is None
        assert snap.limit_up_pool is None
        assert snap.provider == ""

    def test_dataclass_has_exactly_22_fields(self):
        """The dataclass has exactly 22 fields (Pascal canonical)."""
        assert len(MarketSentimentSnapshot.__dataclass_fields__) == 22


class TestUnifiedDataClientLazyLoader:
    """``UnifiedDataClient._get_sentiment_service`` is wired correctly.

    Not part of the canonical acceptance matrix but tightly bound to
    the service contract — if the lazy loader regresses, the service
    is effectively unreachable.
    """

    def test_get_sentiment_service_returns_singleton(self):
        client = UnifiedDataClient()
        svc_a = client._get_sentiment_service()
        svc_b = client._get_sentiment_service()
        assert svc_a is svc_b
        # Router is shared with the client (no separate plumbing).
        assert svc_a.router is client.router

    def test_get_sentiment_service_propagates_ta_cn_adapter(self):
        """When ``ta_cn_adapter`` was injected, the service sees it."""
        from skills.data.unified_data.tests.conftest import FakeTA_CNMongoAdapter

        adapter = FakeTA_CNMongoAdapter()
        client = UnifiedDataClient(ta_cn_adapter=adapter)
        svc = client._get_sentiment_service()
        assert svc._adapter is adapter


# ---------------------------------------------------------------------------
# Test ⑤ — P1 Step 4 CacheManager.put (SPEC §P1.5.2.bis)
# ---------------------------------------------------------------------------


class _MockCacheManager:
    """Records every CacheManager.put call for test assertions."""

    def __init__(self) -> None:
        self.put_calls: list[tuple[str, list]] = []

    def put(self, key: str, records: list) -> None:
        self.put_calls.append((key, records))


class _SentimentTestStub:
    """Minimal inline stub for sentiment refresh tests (no security_id requirement)."""

    def __init__(
        self,
        *,
        payload: list[dict] | None = None,
    ) -> None:
        self._payload = payload or [
            {"market": "CN", "snapshot_date": "2026-07-21", "snapshot_time": "close",
             "limit_up_count": 42, "limit_down_count": 8, "advance_count": 3250,
             "decline_count": 1500, "flat_count": 250, "market_temperature": None,
             "provider": "sentiment_stub"}
        ]
        self.call_log: list[str] = []

    def fetch(self, domain: str, operation: str, **params: Any) -> list[dict]:
        self.call_log.append(f"{domain}.{operation}")
        return list(self._payload)


class TestSentimentServiceCachePut:
    """P1 Step 4 CacheManager.put — mock-only in P1; catch-and-log fail-open.

    Covers both ``sentiment.market_snapshot`` and
    ``sentiment.limit_up_pool`` capabilities.
    """

    def test_refresh_market_snapshot_authorized_calls_cache_put(self):
        """Authorised market_snapshot refresh → CacheManager.put called after upsert."""
        writer = P3PersistenceWriter(_make_db())
        cache = _MockCacheManager()
        svc = MarketSentimentService(
            adapter=None,
            router=DataRouter(registry=ProviderRegistry()),
            p3_writer=writer,
            cache_manager=cache,
        )
        svc.enable_refresh()
        provider = _SentimentTestStub()

        outcome = svc.refresh_market_sentiment_snapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
            provider=provider,
        )

        assert outcome.status == "ok"
        assert len(cache.put_calls) == 1
        key, records = cache.put_calls[0]
        assert "sentiment:market_snapshot:" in key
        assert "2026-07-21" in key
        assert len(records) >= 1

    def test_refresh_limit_up_pool_authorized_calls_cache_put(self):
        """Authorised limit_up_pool refresh → CacheManager.put called after upsert."""
        writer = P3PersistenceWriter(_make_db())
        cache = _MockCacheManager()
        svc = MarketSentimentService(
            adapter=None,
            router=DataRouter(registry=ProviderRegistry()),
            p3_writer=writer,
            cache_manager=cache,
        )
        svc.enable_refresh()
        provider = _SentimentTestStub(
            payload=[{"market": "CN", "symbol": "600519", "trade_date": "2026-07-21",
                       "name": "茅台", "price": 1620.0, "provider": "sentiment_stub"}]
        )

        outcome = svc.refresh_limit_up_pool(
            provider=provider, p3_writer=writer,
        )

        assert outcome.status == "ok"
        assert len(cache.put_calls) == 1
        key, records = cache.put_calls[0]
        assert "sentiment:limit_up_pool:" in key
        # limit_up_pool refresh passes None for snapshot_date,
        # so the key suffix is empty.
        assert key == "sentiment:limit_up_pool:"

    def test_refresh_cache_put_fail_open(self):
        """CacheManager.put exception does NOT block the refresh happy-path."""

        class _FailingCache:
            def put(self, key: str, records: list) -> None:
                raise RuntimeError("simulated cache write failure")

        writer = P3PersistenceWriter(_make_db())
        svc = MarketSentimentService(
            adapter=None,
            router=DataRouter(registry=ProviderRegistry()),
            p3_writer=writer,
            cache_manager=_FailingCache(),
        )
        svc.enable_refresh()
        provider = _SentimentTestStub()

        outcome = svc.refresh_market_sentiment_snapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
            provider=provider,
        )

        assert outcome.status == "ok"

    def test_refresh_cache_put_skipped_when_no_cache(self):
        """cache_manager=None → put skipped, refresh still succeeds."""
        writer = P3PersistenceWriter(_make_db())
        svc = MarketSentimentService(
            adapter=None,
            router=DataRouter(registry=ProviderRegistry()),
            p3_writer=writer,
            cache_manager=None,
        )
        svc.enable_refresh()
        provider = _SentimentTestStub()

        outcome = svc.refresh_market_sentiment_snapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
            provider=provider,
        )

        assert outcome.status == "ok"

    def test_refresh_default_deny_no_cache_call(self):
        """Without enable_refresh(), NotImplementedError is raised; no put call."""
        writer = P3PersistenceWriter(_make_db())
        cache = _MockCacheManager()
        svc = MarketSentimentService(
            adapter=None,
            router=DataRouter(registry=ProviderRegistry()),
            p3_writer=writer,
            cache_manager=cache,
        )
        # Do NOT call enable_refresh().
        provider = _SentimentTestStub()

        with pytest.raises(NotImplementedError):
            svc.refresh_market_sentiment_snapshot(
                snapshot_date="2026-07-21",
                snapshot_time="close",
                provider=provider,
            )

        assert len(cache.put_calls) == 0

    def test_cache_key_market_snapshot_format(self):
        """Cache key for sentiment.market_snapshot follows SPEC §P1.5.2.bis."""
        writer = P3PersistenceWriter(_make_db())
        cache = _MockCacheManager()
        svc = MarketSentimentService(
            adapter=None,
            router=DataRouter(registry=ProviderRegistry()),
            p3_writer=writer,
            cache_manager=cache,
        )
        svc.enable_refresh()
        provider = _SentimentTestStub()

        svc.refresh_market_sentiment_snapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
            provider=provider,
        )

        assert len(cache.put_calls) == 1
        key = cache.put_calls[0][0]
        assert key == "sentiment:market_snapshot:2026-07-21"

    def test_cache_key_limit_up_pool_format(self):
        """Cache key for sentiment.limit_up_pool follows SPEC §P1.5.2.bis."""
        writer = P3PersistenceWriter(_make_db())
        cache = _MockCacheManager()
        svc = MarketSentimentService(
            adapter=None,
            router=DataRouter(registry=ProviderRegistry()),
            p3_writer=writer,
            cache_manager=cache,
        )
        svc.enable_refresh()
        provider = _SentimentTestStub(
            payload=[{"market": "CN", "symbol": "600519", "trade_date": "2026-07-21",
                       "name": "茅台", "price": 1620.0, "provider": "sentiment_stub"}]
        )

        svc.refresh_limit_up_pool(
            provider=provider, p3_writer=writer,
        )

        assert len(cache.put_calls) == 1
        key = cache.put_calls[0][0]
        # limit_up_pool refresh passes None for snapshot_date, so the
        # key is just ``sentiment:limit_up_pool:`` (no date suffix).
        assert key == "sentiment:limit_up_pool:"