"""Phase 3 P3-B / T3-B sentiment service tests (offline scaffold).

T3-B acceptance matrix (kanban task body, decision F.a — minimum 5
tests):

| #   | test name                                       | file                          |
|-----|-------------------------------------------------|-------------------------------|
| ①   | test_market_sentiment_snapshot_query_readonly   | test_sentiment_service.py     |
| ②   | test_market_sentiment_snapshot_refresh_writes_p3_writer | test_sentiment_service.py |
| ③   | test_market_sentiment_snapshot_capability_dispatch | test_sentiment_service.py  |
| ④   | test_market_sentiment_snapshot_injection_boundary | test_sentiment_service.py   |
| ⑤   | test_market_sentiment_snapshot_security_id_none  | test_sentiment_service.py     |

The tests exercise the **query-side** wiring end-to-end (Step 4 → stub
provider, no Step 1 / Step 2 leakage) and the **injection-boundary**
contract (no router → ``ProviderUnavailableError``; router wired →
query succeeds). The refresh path is *not* exercised — T3-B scope
explicitly leaves it for T3-C (see ``refresh_market_sentiment_snapshot``
docstring).

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
    """

    def test_query_path_returns_stub_payload(self):
        """The query reaches the registered stub and returns its payload."""
        registry = ProviderRegistry()
        stub = _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result = svc.get_market_sentiment_snapshot(
            market="CN",
            sentiment_type="market_sentiment",
            market_date="2026-07-21",
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
        assert recorded_params.get("sentiment_type") == "market_sentiment"


class TestMarketSentimentSnapshotRefreshWritesP3Writer:
    """Refresh path goes through ``P3PersistenceWriter`` (V0.5 §2.2).

    T3-B does not invoke the refresh method — but the *boundary*
    must prove that when the writer is wired and the refresh hook is
    exercised manually, the writer's ``upsert`` is the only write
    channel. We simulate the refresh by calling the writer directly
    (the public surface the refresh hook will use) and verify the
    unique-key filter ``{market, sentiment_type, market_date}``
    round-trips through mongomock.
    """

    def test_writer_upsert_round_trip_with_business_key(self):
        writer = P3PersistenceWriter(_make_db())
        unique_key = {"market", "sentiment_type", "market_date"}
        records = [
            {
                "market": "CN",
                "sentiment_type": "market_sentiment",
                "market_date": "2026-07-21",
                "score": 52.3,
                "sample_size": 4250,
                "source": "stub",
                "provider": "sentiment_stub",
            },
            {
                "market": "CN",
                "sentiment_type": "breadth",
                "market_date": "2026-07-21",
                "score": 0.42,
                "sample_size": 4250,
                "source": "stub",
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

        # Round-trip via the business unique key — not the
        # LocalMongoAdapter ``materialized_key`` model.
        docs = writer.get(
            SENTIMENT_COLLECTION,
            {"market": "CN", "sentiment_type": "market_sentiment"},
        )
        assert len(docs) == 1
        assert docs[0]["market_date"] == "2026-07-21"
        assert docs[0]["score"] == 52.3

    def test_refresh_hook_without_writer_raises(self):
        """The injection-boundary contract (test ④ covers it fully)."""
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)
        # ``p3_writer=None`` is the T3-B default — refresh is opt-in.
        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.refresh_market_sentiment_snapshot(
                market="CN",
                sentiment_type="market_sentiment",
                market_date="2026-07-21",
            )
        assert "no P3PersistenceWriter" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Test ③ — capability dispatch (P3-B vs other)
# ---------------------------------------------------------------------------


class TestMarketSentimentSnapshotCapabilityDispatch:
    """The router's capability map is consulted correctly.

    * ``market.sentiment_snapshot`` lands in ``_TA_CN_NOT_COVERED``
      (set during T3-B) — Step 1 is skipped.
    * The P3-B collection key ``03_data_ud_market_sentiment_snapshot``
      appears in :data:`P3_COLLECTION_BY_CAPABILITY`.
    * Other capabilities (``market_data.kline_daily`` etc.) keep
      their original behaviour — no regression in the existing
      routing.
    """

    def test_market_sentiment_snapshot_is_ta_cn_not_covered(self):
        # Router must skip Step 1 for the new P3-B capability.
        assert SENTIMENT_CAP in DataRouter._TA_CN_NOT_COVERED

    def test_p3_b_collection_is_registered(self):
        from skills.data.unified_data.adapters.p3_persistence_writer import (
            P3_COLLECTION_BY_CAPABILITY,
        )

        assert P3_COLLECTION_BY_CAPABILITY[SENTIMENT_CAP] == (
            "03_data_ud_market_sentiment_snapshot"
        )

    def test_non_p3_capability_dispatch_unchanged(self):
        """``market_data.kline_daily`` still maps to ``get_daily_bars``.

        The capability-method map is the only authoritative source —
        T3-B does not touch it.
        """
        assert (
            DataRouter._TA_CN_CAPABILITY_METHOD_MAP["market_data.kline_daily"]
            == "get_daily_bars"
        )
        # And the new sentiment capability is intentionally NOT in the
        # method map (it is not TA-CN-owned).
        assert SENTIMENT_CAP not in DataRouter._TA_CN_CAPABILITY_METHOD_MAP


# ---------------------------------------------------------------------------
# Test ④ — injection boundary
# ---------------------------------------------------------------------------


class TestMarketSentimentSnapshotInjectionBoundary:
    """DI surface contract for :class:`MarketSentimentService`."""

    def test_no_router_raises_provider_unavailable(self):
        """``MarketSentimentService(adapter)`` (no router) → query raises."""
        svc = MarketSentimentService(adapter=None)
        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.get_market_sentiment_snapshot(
                market="CN",
                sentiment_type="market_sentiment",
                market_date="2026-07-21",
            )
        assert "no router wired" in str(excinfo.value)

    def test_router_injection_unblocks_query(self):
        """Injecting a router unlocks the query path end-to-end."""
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result = svc.get_market_sentiment_snapshot(
            market="CN",
            sentiment_type="market_sentiment",
            market_date="2026-07-21",
        )

        assert result.succeeded
        assert result.provider == "sentiment_stub"
        assert isinstance(result.data, list)
        assert result.data and isinstance(result.data[0], dict)

    def test_constructor_signature_is_minimal(self):
        """Constructor accepts the documented kwarg set — no extras.

        Mirrors the T3-A ``SectorService`` regression guard: P3-B
        must not widen the DI surface beyond what V0.5 §4.5 promises.
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
# Test ⑤ — security_id placeholder + market-level marker
# ---------------------------------------------------------------------------


class TestMarketSentimentSnapshotSecurityIdNone:
    """The market-level query must not pass a per-security ``SecurityId``.

    The service synthesises a placeholder SecurityId (so the router
    has something to log against), then appends a marker to
    ``source_trace`` so consumers can identify the market-level shape
    without inspecting the canonical string.

    The T3-B contract — adopted because :class:`DataResult` does not
    yet carry a ``metadata`` field — is:
    ``"market_level_query(security_id=None)" in result.source_trace``.
    """

    def test_market_level_marker_in_source_trace(self):
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result = svc.get_market_sentiment_snapshot(
            market="CN",
            sentiment_type="market_sentiment",
            market_date="2026-07-21",
        )

        # The explicit market-level marker is appended exactly once.
        marker = "market_level_query(security_id=None)"
        assert result.source_trace.count(marker) == 1

    def test_no_security_id_passed_to_provider(self):
        """The placeholder SecurityId is local to the service — it
        must not leak to the provider's ``security_id`` argument.

        The stub records the *canonical* string it received in its
        call log; verifying the placeholder's canonical form never
        surfaces confirms the boundary is clean.
        """
        registry = ProviderRegistry()
        stub = _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        svc.get_market_sentiment_snapshot(
            market="CN",
            sentiment_type="market_sentiment",
            market_date="2026-07-21",
        )

        # The stub's call log only contains (capability, market,
        # params) — the security_id's canonical string is not in the
        # recorded tuple. This proves the provider-side signature is
        # sanitised (the router does the full SecurityId plumbing).
        assert len(stub.call_log) == 1
        recorded_capability, recorded_market, _ = stub.call_log[0]
        assert recorded_capability == SENTIMENT_CAP
        assert recorded_market == "INDEX"  # SecurityId market slot

    def test_market_level_marker_survives_multiple_calls(self):
        """The marker is appended once per call (not duplicated)."""
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result_a = svc.get_market_sentiment_snapshot(
            market="CN",
            sentiment_type="market_sentiment",
            market_date="2026-07-21",
        )
        result_b = svc.get_market_sentiment_snapshot(
            market="CN",
            sentiment_type="breadth",
            market_date="2026-07-21",
        )

        marker = "market_level_query(security_id=None)"
        assert result_a.source_trace.count(marker) == 1
        assert result_b.source_trace.count(marker) == 1


# ---------------------------------------------------------------------------
# Cross-checks — domain object + lazy loader
# ---------------------------------------------------------------------------


class TestDomainObjectSanity:
    """Cheap contract tests for the new domain object.

    Not part of the F.a acceptance matrix, but useful so future
    readers can pin the shape without re-reading the whole dataclass.
    """

    def test_from_dict_round_trip(self):
        record = {
            "market": "CN",
            "sentiment_type": "market_sentiment",
            "market_date": "2026-07-21",
            "score": 52.3,
            "sample_size": 4250,
            "source": "stub",
            "provider": "sentiment_stub",
            "notes": "neutral-to-slightly-bullish",
        }
        snap = MarketSentimentSnapshot.from_dict(record)
        assert snap.market == "CN"
        assert snap.sentiment_type == "market_sentiment"
        assert snap.market_date == "2026-07-21"
        assert snap.score == 52.3
        assert snap.sample_size == 4250

    def test_from_dict_tolerates_missing_optional_fields(self):
        snap = MarketSentimentSnapshot.from_dict(
            {
                "market": "CN",
                "sentiment_type": "breadth",
                "market_date": "2026-07-21",
                "score": 0.0,
                "sample_size": 0,
            }
        )
        # Defaults take over.
        assert snap.source == ""
        assert snap.provider == ""
        assert snap.fetched_at is None
        assert snap.notes is None


class TestUnifiedDataClientLazyLoader:
    """``UnifiedDataClient._get_sentiment_service`` is wired correctly.

    Not part of the F.a acceptance matrix but tightly bound to the
    service contract — if the lazy loader regresses, the service is
    effectively unreachable.
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