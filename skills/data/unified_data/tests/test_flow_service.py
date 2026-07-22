"""Phase 3 P3-B FlowService tests (offline T3-P3B).

Covers the V0.5 §5.2 contract for :class:`FlowService`:

* The two read methods (``get_capital_flow`` / ``get_northbound_flow``)
  route through the existing :class:`DataRouter`, with no TA-CN
  involvement (capabilities are in ``_TA_CN_NOT_COVERED``).
* The injection-boundary contract: ``FlowService(router=None)`` raises
  :class:`ProviderUnavailableError` on read; injecting a router unlocks
  the read path.
* The read path is **read-only** — :meth:`DataRouter.query` is the only
  call the service makes; no Step-2 / P3 writer / cache write fires
  during a read (``source_trace`` stays free of ``ud_materialized``).
* The refresh path implements the full five-branch contract
  (happy_path / partial_failure / skip_empty / write_forbidden /
  already_written) via T3-P3B M3 — not a stub.
  ``refresh_capital_flow`` raises :class:`ProviderUnavailableError`
  when ``p3_writer is None``; when wired it fetches, validates,
  upserts, and returns a :class:`PersistenceResult`.
* The :class:`UnifiedDataClient` facade exposes a lazy
  ``_get_flow_service`` loader plus ``get_capital_flow`` and
  ``get_northbound_flow`` domain methods that route through the
  service.
* Capability dispatch: the two P3-B capabilities are in
  ``DataRouter._TA_CN_NOT_COVERED`` (T3-P3B added them) and the
  collection routing goes through
  :data:`P3_COLLECTION_BY_CAPABILITY`.
* The P3 writer upsert round-trip uses the ``{market, symbol,
  trade_date}`` business key — the writer's only write channel for
  P3-B.

All tests are offline:

* No real MongoDB — :mod:`mongomock` only.
* No real Provider API call — :class:`StubFlowProvider`.
* No AuditLogger / QualitySummary writes.
* No cron / systemd / webhook side-effects.
"""

from __future__ import annotations

import inspect
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
from skills.data.unified_data.providers.flow_stub import StubFlowProvider
from skills.data.unified_data.services.flow_service import FlowService
from skills.data.unified_data.client import UnifiedDataClient


CAP_FLOW_DAILY = "flow.capital_flow_daily"
CAP_FLOW_NORTHBOUND = "flow.northbound_daily"
COLLECTION_FLOW = "03_data_ud_stock_capital_flow"
UNIQUE_KEY_FLOW = frozenset({"market", "symbol", "trade_date"})


def _make_db() -> Any:
    """Return a fresh mongomock database handle (offline only)."""
    return mongomock.MongoClient().get_database("tradingagents")


def _register_stub(
    registry: ProviderRegistry,
    *,
    payload: list[dict] | None = None,
    name: str = "flow_stub",
    capabilities: frozenset[str] | set[str] = frozenset(
        {CAP_FLOW_DAILY, CAP_FLOW_NORTHBOUND}
    ),
) -> StubFlowProvider:
    """Register a :class:`StubFlowProvider` covering CN markets."""
    stub = StubFlowProvider(
        name=name,
        payload=payload,
        capabilities=capabilities,
        markets={Market.CN},
    )
    registry.register(stub)
    return stub


# ---------------------------------------------------------------------------
# Test ① — query path is read-only + Step-2 (P3PersistenceWriter) skip trace
# ---------------------------------------------------------------------------


class TestCapitalFlowQueryReadonly:
    """The query must reach the stub and never trigger Step-2 writes."""

    def test_get_capital_flow_returns_stub_payload(self):
        """``get_capital_flow`` returns the stub payload via the router."""
        registry = ProviderRegistry()
        stub = _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = svc.get_capital_flow(security_id=sid, trade_date="2026-07-21")

        # Stub is the only candidate — provider reflects that.
        assert result.provider == "flow_stub"
        assert result.succeeded
        # No Step 2 marker (no p3_writer wired; the read path is read-only).
        assert "ud_materialized" not in result.source_trace
        # And the stub recorded exactly one fetch call with the right
        # capability / market / params.
        assert len(stub.call_log) == 1
        capability, market_label, params = stub.call_log[0]
        assert capability == CAP_FLOW_DAILY
        assert market_label == "CN"
        assert params.get("trade_date") == "2026-07-21"

    def test_get_northbound_flow_returns_stub_payload(self):
        """``get_northbound_flow`` routes through ``flow.northbound_daily``."""
        registry = ProviderRegistry()
        stub = _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        # V0.5 m4 alignment: northbound arg is ``date=`` (not ``trade_date=``).
        result = svc.get_northbound_flow(security_id=sid, date="2026-07-21")

        assert result.provider == "flow_stub"
        assert result.succeeded
        assert "ud_materialized" not in result.source_trace
        # Capability dispatch must use the northbound flavour.
        capability, _, _ = stub.call_log[0]
        assert capability == CAP_FLOW_NORTHBOUND

    def test_get_capital_flow_payload_preserves_northbound_none(self):
        """The non-港通 fixture record keeps ``northbound_*`` = None end-to-end.

        Pins the V0.5 §2.3 "部分字段不可用" contract that ``None`` flows
        through the read path without being silently coerced to ``0``.
        T3-P3B M2 — the service now shapes Router output as
        ``list[CapitalFlowRecord]``, so the test asserts on attribute
        access rather than dict subscript.
        """
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="300999")

        result = svc.get_capital_flow(security_id=sid, trade_date="2026-07-21")

        assert result.succeeded
        # The Router returned the stub payload; the service shaped it
        # into ``list[CapitalFlowRecord]``. Locate the non-港通 record.
        records = result.data
        non_hk = next(r for r in records if r.symbol == "300999")
        assert non_hk.northbound_net_inflow is None
        assert non_hk.northbound_hold_shares is None
        assert non_hk.northbound_hold_ratio is None


# ---------------------------------------------------------------------------
# Test ② — refresh path is reserved (T3-B sentiment precedent)
# ---------------------------------------------------------------------------


class TestCapitalFlowRefreshReserved:
    """``refresh_capital_flow`` is reserved — follows the T3-B precedent.

    Per the kanban task body, "explicit ``refresh_capital_flow`` only
    verifiable on fake adapter/writer". The T3-B sentiment service set
    the precedent: refresh with ``p3_writer=None`` raises
    :class:`ProviderUnavailableError`; refresh with ``p3_writer``
    wired raises :class:`NotImplementedError` (T3-P3B does not ship
    the full happy-path; the refresh path is deferred to a Gate-
    authorised sub-stage).
    """

    def test_refresh_without_writer_raises(self):
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.refresh_capital_flow(security_id=sid, date="2026-07-21")
        assert "no P3PersistenceWriter" in str(excinfo.value)

    def test_refresh_with_writer_raises_not_implemented(self):
        """When ``p3_writer`` is wired, refresh raises NotImplementedError.

        T3-P3B m4 alignment: refresh kwargs use ``date=`` (single-day
        filter). The ``NotImplementedError`` assertion below is a
        placeholder for the M3 happy-path branch — once M3 lands, the
        assertion flips to ``status == "ok"``. Per the M3 scope, the
        happy-path IS implemented; this test stays as a regression
        guard for the "writer not wired" branch only.
        """
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        writer = P3PersistenceWriter(_make_db())
        svc = FlowService(adapter=None, router=router, p3_writer=writer)
        sid = SecurityId(market=Market.CN, symbol="600519")

        # M3 happy-path: with the stub + writer wired the refresh
        # path now returns a ``PersistenceResult(status="ok", ...)``
        # rather than raising ``NotImplementedError``. The
        # M3-task-body documents this as the "write-path
        # implementation" landing in T3-P3B itself (not a deferred
        # sub-stage). The result is the documented surface; the test
        # is the regression guard.
        from skills.data.unified_data.services import PersistenceResult

        result = svc.refresh_capital_flow(security_id=sid, date="2026-07-21")
        assert isinstance(result, PersistenceResult)


# ---------------------------------------------------------------------------
# Test ③ — capability dispatch + collection routing
# ---------------------------------------------------------------------------


class TestCapitalFlowCapabilityDispatch:
    """The router's capability maps are correctly consulted."""

    def test_both_p3b_capabilities_in_ta_cn_not_covered(self):
        """T3-P3B registers both flow capabilities in ``_TA_CN_NOT_COVERED``."""
        assert CAP_FLOW_DAILY in DataRouter._TA_CN_NOT_COVERED
        assert CAP_FLOW_NORTHBOUND in DataRouter._TA_CN_NOT_COVERED

    def test_both_p3b_capabilities_route_to_same_collection(self):
        """Both capabilities share the P3-B collection key."""
        from skills.data.unified_data.adapters.p3_persistence_writer import (
            P3_COLLECTION_BY_CAPABILITY,
            P3_UNIQUE_KEYS_BY_CAPABILITY,
        )

        assert P3_COLLECTION_BY_CAPABILITY[CAP_FLOW_DAILY] == COLLECTION_FLOW
        assert P3_COLLECTION_BY_CAPABILITY[CAP_FLOW_NORTHBOUND] == COLLECTION_FLOW
        assert P3_UNIQUE_KEYS_BY_CAPABILITY[CAP_FLOW_DAILY] == UNIQUE_KEY_FLOW
        assert P3_UNIQUE_KEYS_BY_CAPABILITY[CAP_FLOW_NORTHBOUND] == UNIQUE_KEY_FLOW

    def test_non_p3_capability_dispatch_unchanged(self):
        """``market_data.kline_daily`` still maps to ``get_daily_bars``."""
        assert (
            DataRouter._TA_CN_CAPABILITY_METHOD_MAP["market_data.kline_daily"]
            == "get_daily_bars"
        )
        # And the new flow capabilities are intentionally NOT in the
        # method map (they are not TA-CN-owned).
        assert CAP_FLOW_DAILY not in DataRouter._TA_CN_CAPABILITY_METHOD_MAP
        assert CAP_FLOW_NORTHBOUND not in DataRouter._TA_CN_CAPABILITY_METHOD_MAP


# ---------------------------------------------------------------------------
# Test ④ — injection boundary + DI surface
# ---------------------------------------------------------------------------


class TestCapitalFlowInjectionBoundary:
    """``FlowService`` DI surface contract."""

    def test_no_router_raises_provider_unavailable(self):
        """``FlowService(adapter)`` (no router) → query raises."""
        svc = FlowService(adapter=None)
        sid = SecurityId(market=Market.CN, symbol="600519")
        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.get_capital_flow(security_id=sid)
        assert "no router wired" in str(excinfo.value)

    def test_no_router_northbound_query_raises(self):
        svc = FlowService(adapter=None)
        sid = SecurityId(market=Market.CN, symbol="600519")
        with pytest.raises(ProviderUnavailableError):
            svc.get_northbound_flow(security_id=sid)

    def test_router_injection_unblocks_query(self):
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = svc.get_capital_flow(security_id=sid)
        assert result.succeeded
        assert result.provider == "flow_stub"

    def test_constructor_signature_is_minimal(self):
        """Mirror the T3-A / T3-B regression guard: P3-B must not widen DI."""
        sig = inspect.signature(FlowService.__init__)
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
# Test ⑤ — P3PersistenceWriter upsert round-trip
# ---------------------------------------------------------------------------


class TestCapitalFlowP3WriterUpsert:
    """``P3PersistenceWriter.upsert`` round-trip for P3-B.

    The writer is the only write channel for the
    ``03_data_ud_stock_capital_flow`` collection. T3-P3B does **not**
    invoke it from the read path; the test exercises it directly to
    pin the ``{market, symbol, trade_date}`` business key behaviour.
    """

    def test_writer_upsert_round_trip_with_business_key(self):
        writer = P3PersistenceWriter(_make_db())
        from skills.data.unified_data.tests.fixtures.flow_fixtures import (
            sample_capital_flow_records,
        )

        records = sample_capital_flow_records()
        outcome = writer.upsert(
            collection=COLLECTION_FLOW,
            records=records,
            unique_key=UNIQUE_KEY_FLOW,
        )
        # T3-P3B m4 fixture expansion: 4 records now (mainland /
        # 非港通 / HK Connect / US). All four carry the unique-key
        # fields so all four persist.
        assert outcome.persisted == 4
        assert outcome.failed == 0

        # Round-trip via the business unique key — each fixture
        # symbol must be independently retrievable.
        docs = writer.get(
            COLLECTION_FLOW,
            {"market": "CN", "symbol": "600519"},
        )
        assert len(docs) == 1
        assert docs[0]["trade_date"] == "2026-07-21"
        assert docs[0]["main_net_inflow"] == 1_230_000.0

        # And the non-港通 record is independently retrievable.
        docs_300999 = writer.get(
            COLLECTION_FLOW,
            {"market": "CN", "symbol": "300999"},
        )
        assert len(docs_300999) == 1
        assert docs_300999[0]["northbound_net_inflow"] is None
        assert docs_300999[0]["northbound_hold_shares"] is None

    def test_writer_idempotent_upsert(self):
        """Same business key upserted twice does not duplicate (V0.5 §6.1 V-GEN-1)."""
        writer = P3PersistenceWriter(_make_db())
        from skills.data.unified_data.tests.fixtures.flow_fixtures import (
            sample_capital_flow_records,
        )

        records = sample_capital_flow_records()
        first = writer.upsert(
            collection=COLLECTION_FLOW,
            records=records,
            unique_key=UNIQUE_KEY_FLOW,
        )
        # Same records, different signed field — upsert overwrites in place.
        mutated = []
        for r in records:
            d = dict(r)
            d["main_net_inflow"] = (d.get("main_net_inflow") or 0) + 999.0
            mutated.append(d)
        second = writer.upsert(
            collection=COLLECTION_FLOW,
            records=mutated,
            unique_key=UNIQUE_KEY_FLOW,
        )

        # T3-P3B m4 fixture is 4 records now (was 2 in the prior
        # round).
        assert first.persisted == 4 and first.failed == 0
        assert second.persisted == 4 and second.failed == 0

        # Still 4 documents (no duplicates) — 3 CN + 1 US.
        all_cn = writer.get(COLLECTION_FLOW, {"market": "CN"})
        all_us = writer.get(COLLECTION_FLOW, {"market": "US"})
        assert len(all_cn) == 3
        assert len(all_us) == 1
        assert len(all_cn) + len(all_us) == 4


# ---------------------------------------------------------------------------
# Test ⑥ — DomainService facade + lazy loader
# ---------------------------------------------------------------------------


class TestUnifiedDataClientFacade:
    """``UnifiedDataClient`` exposes the P3-B domain methods + lazy loader."""

    def test_get_capital_flow_facade(self):
        """``client.get_capital_flow(...)`` routes through the service."""
        client = UnifiedDataClient()
        registry = client.registry
        _register_stub(registry)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = client.get_capital_flow(security_id=sid, trade_date="2026-07-21")

        assert result.succeeded
        assert result.provider == "flow_stub"

    def test_get_northbound_flow_facade(self):
        client = UnifiedDataClient()
        registry = client.registry
        _register_stub(registry)
        sid = SecurityId(market=Market.CN, symbol="600519")

        # V0.5 m4 alignment: northbound facade uses ``date=``.
        result = client.get_northbound_flow(security_id=sid, date="2026-07-21")

        assert result.succeeded
        assert result.provider == "flow_stub"

    def test_get_flow_service_returns_singleton(self):
        """The lazy loader returns the same instance every call."""
        client = UnifiedDataClient()
        svc_a = client._get_flow_service()
        svc_b = client._get_flow_service()
        assert svc_a is svc_b
        # Router is shared with the client (no separate plumbing).
        assert svc_a.router is client.router

    def test_get_flow_service_propagates_ta_cn_adapter(self):
        """When ``ta_cn_adapter`` was injected, the service sees it."""
        from skills.data.unified_data.tests.conftest import FakeTA_CNMongoAdapter

        adapter = FakeTA_CNMongoAdapter()
        client = UnifiedDataClient(ta_cn_adapter=adapter)
        svc = client._get_flow_service()
        assert svc._adapter is adapter

    def test_freshness_ttl_for_flow_domain(self):
        """``flow`` domain TTL is 43200s — V0.5 §4.4 explicit value."""
        from skills.data.unified_data.freshness import FreshnessPolicy

        policy = FreshnessPolicy()
        assert policy.get_ttl("flow") == 43200


# ---------------------------------------------------------------------------
# Test ⑦ — T3-P3B M2 read-path canonical shaping (list[CapitalFlowRecord])
# ---------------------------------------------------------------------------


class TestCapitalFlowCanonicalShaping:
    """M2 — the service shapes Router output into ``list[CapitalFlowRecord]``."""

    def test_get_capital_flow_returns_canonical_records(self):
        """``get_capital_flow`` returns dataclass records (not raw dicts)."""
        from skills.data.unified_data.models.domain.flow import CapitalFlowRecord

        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        # Call without a ``trade_date`` so the per-symbol filter is
        # the only narrowing clause. The M2 fixture (4 records)
        # returns 4 records once shape is corrected.
        result = svc.get_capital_flow(security_id=sid)

        # Every list entry must be a CapitalFlowRecord instance.
        assert isinstance(result.data, list)
        # The per-symbol filter pins to one row.
        assert len(result.data) == 1
        assert all(
            isinstance(r, CapitalFlowRecord) for r in result.data
        ), "service must shape Router data into CapitalFlowRecord"

    def test_get_northbound_flow_projects_to_northbound_field_subset(self):
        """``get_northbound_flow`` returns the V0.5 §3.2 ``record_scope``.

        The five flow bands + three ``margin_*`` fields are explicitly
        ``None`` regardless of source. Only ``northbound_*`` + business
        key + ``fetched_at`` + ``provider`` are populated.
        """
        from skills.data.unified_data.models.domain.flow import CapitalFlowRecord

        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = svc.get_northbound_flow(security_id=sid, date="2026-07-21")

        assert isinstance(result.data, list)
        # Every entry is a CapitalFlowRecord.
        assert all(
            isinstance(r, CapitalFlowRecord) for r in result.data
        )
        # 600519 is 沪股通 — northbound fields populated; the five
        # band fields + margin_* are None per the projection.
        record_600519 = next(r for r in result.data if r.symbol == "600519")
        assert record_600519.northbound_net_inflow == 250_000.0
        assert record_600519.northbound_hold_shares == 9_500_000.0
        assert record_600519.northbound_hold_ratio == 7.55
        # The five flow bands are explicitly None — the projection
        # redacts them regardless of what the source dict carries.
        assert record_600519.main_net_inflow is None
        assert record_600519.super_large_net_inflow is None
        assert record_600519.large_net_inflow is None
        assert record_600519.medium_net_inflow is None
        assert record_600519.small_net_inflow is None
        assert record_600519.main_net_inflow_ratio is None
        # margin_* fields are also None per the projection.
        assert record_600519.margin_buy is None
        assert record_600519.margin_sell is None
        assert record_600519.margin_balance is None
        # Business key + provider metadata are preserved.
        assert record_600519.symbol == "600519"
        assert record_600519.market == "CN"
        assert record_600519.trade_date == "2026-07-21"
        assert record_600519.provider == "flow_stub"
        assert record_600519.fetched_at == "2026-07-21T18:30:00"


# ---------------------------------------------------------------------------
# Test ⑧ — T3-P3B M2 filter semantics: security_id / date / range / limit
# ---------------------------------------------------------------------------


class TestCapitalFlowFilterSemantics:
    """M2 — caller-supplied filters are applied at the service boundary."""

    def test_security_id_filter_keeps_only_matching_symbol(self):
        """``get_capital_flow(sid)`` returns docs matching ``{market, symbol}``.

        Regression guard for the T3-P3B Review #2 finding (the
        pre-fix stub returned both 600519 + 300999 regardless of the
        caller's symbol; the fix routes through the Router but
        applies the per-symbol filter at the service boundary so
        callers see exactly the records they asked for.
        """
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid_600519 = SecurityId(market=Market.CN, symbol="600519")

        result = svc.get_capital_flow(security_id=sid_600519, trade_date="2026-07-21")

        symbols = [r.symbol for r in result.data]
        # Filter applied: only the 600519 record survives; the 300999
        # record (non-港通 counter-example) is filtered out.
        assert symbols == ["600519"]

    def test_other_symbol_filter_does_not_mix_records(self):
        """The T3-P3B Review #2 contract: 600519 query never contains 300999."""
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid_300999 = SecurityId(market=Market.CN, symbol="300999")

        result = svc.get_capital_flow(security_id=sid_300999, trade_date="2026-07-21")

        symbols = [r.symbol for r in result.data]
        assert symbols == ["300999"]

    def test_trade_date_filter_pins_to_single_date(self):
        """A ``trade_date`` filter restricts results to the requested date."""
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = svc.get_capital_flow(security_id=sid, trade_date="2026-07-21")

        assert len(result.data) == 1
        assert result.data[0].trade_date == "2026-07-21"

    def test_limit_truncates_after_filters(self):
        """``limit`` truncates AFTER the security_id / date filters."""
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        # Stub returns all 4 fixture records; with a per-symbol filter
        # only 600519 survives. limit=1 then truncates to 1.
        result = svc.get_capital_flow(
            security_id=sid, trade_date="2026-07-21", limit=1
        )
        assert len(result.data) == 1
        assert result.data[0].symbol == "600519"


# ---------------------------------------------------------------------------
# Test ⑨ — T3-P3B m4 signature alignment (northbound ``date=`` arg)
# ---------------------------------------------------------------------------


class TestCapitalFlowNorthboundSignatureV05:
    """m4 — northbound arg renamed from ``trade_date`` to ``date``."""

    def test_northbound_accepts_optional_security_id(self):
        """``get_northbound_flow(security_id=None)`` does not raise TypeError."""
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)

        # ``security_id=None`` is the market-level pattern; the
        # service must NOT raise TypeError.
        result = svc.get_northbound_flow(security_id=None, date="2026-07-21")

        assert result.succeeded
        # No security_id filter was applied — every fixture record
        # survives.
        assert isinstance(result.data, list)
        assert len(result.data) >= 3

    def test_northbound_drops_limit_kwarg(self):
        """``get_northbound_flow`` no longer accepts ``limit`` (V0.5 m4).

        The V0.5 contract for northbound removes the ``limit`` param
        — the northbound payload is a market aggregate, not a
        per-symbol batch.
        """
        import inspect

        sig = inspect.signature(FlowService.get_northbound_flow)
        params = list(sig.parameters)
        assert "limit" not in params, (
            "T3-P3B m4 — V0.5 northbound signature drops the limit "
            "kwarg; V0.5 northbound is market-level (no per-symbol "
            "batch limit)."
        )

    def test_northbound_signature_has_optional_security_id(self):
        """``get_northbound_flow(security_id=None)`` is the V0.5 contract."""
        import inspect

        sig = inspect.signature(FlowService.get_northbound_flow)
        params = sig.parameters
        # ``security_id`` defaults to ``None`` — market-level pattern.
        assert "security_id" in params
        assert params["security_id"].default is None
        # ``date`` is the new kw-only name (replaces ``trade_date``).
        assert "date" in params


# ---------------------------------------------------------------------------
# Test ⑩ — T3-P3B M3 refresh-path happy-path + 5 branches
# ---------------------------------------------------------------------------


class TestCapitalFlowRefreshHappyPath:
    """M3 — ``refresh_capital_flow`` returns ``PersistenceResult``.

    Pins the T3-P3B Review #3 contract: refresh must call
    ``p3_writer.upsert(...)`` end-to-end, **not** raise
    :class:`NotImplementedError`. The skip / partial_failure /
    write_forbidden branches are covered in dedicated classes below
    — this class is the happy-path regression guard.
    """

    def test_refresh_happy_path_returns_persistence_result(self):
        """With stub + mongomock writer wired, refresh returns ok/2 persisted."""
        from skills.data.unified_data.services import PersistenceResult

        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        writer = P3PersistenceWriter(_make_db())
        svc = FlowService(adapter=None, router=router, p3_writer=writer)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = svc.refresh_capital_flow(security_id=sid, date="2026-07-21")

        assert isinstance(result, PersistenceResult)
        assert result.status == "ok"
        # Default stub payload is 4 records (m4 expansion).
        assert result.persisted >= 2
        assert result.failed == 0
        assert result.skipped is False
        assert result.capability == "flow.capital_flow_daily"
        assert result.collection == "03_data_ud_stock_capital_flow"
        # Writer upsert outcome is preserved for audit logging.
        assert result.writer_outcome is not None
        assert isinstance(result.writer_outcome.persisted, int)

    def test_refresh_persisted_to_writer_collection(self):
        """Happy-path refresh actually upserts into the P3 collection.

        Distinct from the regression guard above — this test reads
        back the documents via ``writer.get(...)`` to prove the
        data was persisted end-to-end (not just ``upsert`` was
        called). V0.5 §5.4 happy-path contract.
        """
        writer = P3PersistenceWriter(_make_db())
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router, p3_writer=writer)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = svc.refresh_capital_flow(security_id=sid, date="2026-07-21")

        assert result.persisted >= 2
        # Read back at least one of the persisted documents.
        docs_600519 = writer.get(
            "03_data_ud_stock_capital_flow",
            {"market": "CN", "symbol": "600519"},
        )
        assert len(docs_600519) >= 1
        assert docs_600519[0]["trade_date"] == "2026-07-21"


class TestCapitalFlowRefreshSkipEmpty:
    """M3 ``skip_empty``: provider returns an empty list → writer not called."""

    def test_skip_empty_returns_persistence_result(self):
        from skills.data.unified_data.services import PersistenceResult

        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)

        # A FakeProvider-style inline stub returning ``[]``.
        class _EmptyProvider:
            name = "empty_provider"
            capabilities = {"flow.capital_flow_daily"}
            markets = {Market.CN}

            def __init__(self) -> None:
                self.call_count = 0

            def is_available(self) -> bool:
                return True

            def fetch(self, *args, **kwargs) -> list[dict]:
                self.call_count += 1
                return []

        empty = _EmptyProvider()
        writer = P3PersistenceWriter(_make_db())
        svc = FlowService(
            adapter=None, router=router, p3_writer=writer
        )
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = svc.refresh_capital_flow(
            security_id=sid, date="2026-07-21", provider=empty
        )

        assert isinstance(result, PersistenceResult)
        assert result.status == "skipped"
        assert result.skipped is True
        assert result.reason == "empty_payload"
        assert result.persisted == 0
        assert result.failed == 0
        assert result.writer_outcome is None
        # Provider was still called (we just skipped the writer).
        assert empty.call_count == 1


class TestCapitalFlowRefreshWriteForbidden:
    """M3 ``write_forbidden``: ``_write_disabled_flag`` set → writer not called."""

    def test_write_disabled_returns_skipped(self):
        from skills.data.unified_data.services import PersistenceResult

        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        writer = P3PersistenceWriter(_make_db())
        svc = FlowService(adapter=None, router=router, p3_writer=writer)
        sid = SecurityId(market=Market.CN, symbol="600519")

        # Flip the production guard via monkey-patch.
        svc._write_disabled_flag = True

        result = svc.refresh_capital_flow(security_id=sid, date="2026-07-21")

        assert isinstance(result, PersistenceResult)
        assert result.status == "skipped"
        assert result.skipped is True
        assert result.reason == "write_forbidden"
        # Writer was NOT invoked.
        assert result.writer_outcome is None
        # Collection was empty post-refresh (writer never called).
        docs = writer.get("03_data_ud_stock_capital_flow", {"market": "CN"})
        assert docs == []


class TestCapitalFlowRefreshAlreadyWritten:
    """M3 ``already_written``: re-running refresh is idempotent (doc count stable)."""

    def test_refresh_twice_does_not_increase_doc_count(self):
        from skills.data.unified_data.services import PersistenceResult

        writer = P3PersistenceWriter(_make_db())
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router, p3_writer=writer)
        sid = SecurityId(market=Market.CN, symbol="600519")

        first = svc.refresh_capital_flow(security_id=sid, date="2026-07-21")
        second = svc.refresh_capital_flow(security_id=sid, date="2026-07-21")

        assert isinstance(first, PersistenceResult) and first.status == "ok"
        assert isinstance(second, PersistenceResult) and second.status == "ok"
        assert first.persisted >= 2 and second.persisted >= 2
        # Doc count stays at the first refresh's level — the
        # business-key upsert is idempotent.
        docs = writer.get("03_data_ud_stock_capital_flow", {"market": "CN"})
        symbols = sorted({d["symbol"] for d in docs})
        # Same set of symbols — no duplicates introduced.
        assert "600519" in symbols
        # All four fixture symbols survive across both refreshes
        # without doc-count doubling.
        assert len(docs) == len(set((d["symbol"], d["trade_date"]) for d in docs))


class TestCapitalFlowRefreshPartialFailure:
    """M3 ``partial_failure``: malformed records fail at the writer."""

    def test_partial_failure_returns_status_and_counts(self):
        """A mixed-payload provider triggers ``partial_failure``."""
        from skills.data.unified_data.services import PersistenceResult

        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        writer = P3PersistenceWriter(_make_db())
        svc = FlowService(adapter=None, router=router, p3_writer=writer)
        sid = SecurityId(market=Market.CN, symbol="600519")

        # Build a "mixed" provider payload: two well-formed rows +
        # one row missing the ``trade_date`` business key. The
        # P3PersistenceWriter's per-record upsert should catch the
        # missing-key case and surface it through ``failed``.
        mixed_payload = [
            {  # valid
                "symbol": "600519",
                "market": "CN",
                "trade_date": "2026-07-21",
                "main_net_inflow": 1_000_000.0,
                "provider": "mixed_stub",
            },
            {  # missing trade_date key
                "symbol": "000001",
                "market": "CN",
                "main_net_inflow": 500_000.0,
                "provider": "mixed_stub",
            },
            {  # valid
                "symbol": "300999",
                "market": "CN",
                "trade_date": "2026-07-21",
                "main_net_inflow": -200_000.0,
                "provider": "mixed_stub",
            },
        ]

        class _MixedProvider:
            name = "mixed_provider"
            capabilities = {"flow.capital_flow_daily"}
            markets = {Market.CN}

            def is_available(self) -> bool:
                return True

            def fetch(self, *args, **kwargs) -> list[dict]:
                return mixed_payload

        mixed = _MixedProvider()
        result = svc.refresh_capital_flow(
            security_id=sid, date="2026-07-21", provider=mixed
        )

        assert isinstance(result, PersistenceResult)
        assert result.status == "partial_failure"
        # Two valid rows persisted; one row failed.
        assert result.persisted == 2
        assert result.failed == 1
        assert result.skipped is False


class TestCapitalFlowRefreshMissingWriter:
    """M3 — when ``p3_writer`` is None the refresh raises ProviderUnavailable."""

    def test_no_writer_raises(self):
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)  # no p3_writer
        sid = SecurityId(market=Market.CN, symbol="600519")

        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.refresh_capital_flow(security_id=sid, date="2026-07-21")
        assert "no P3PersistenceWriter" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Test ⑪ — T3-P3B m4 package-level exports
# ---------------------------------------------------------------------------


class TestCapitalFlowPackageExports:
    """m4 — ``CapitalFlowRecord`` and ``FlowService`` are top-level exports."""

    def test_capital_flow_record_re_exported_from_models_domain(self):
        from skills.data.unified_data.models.domain import CapitalFlowRecord as CFR1
        from skills.data.unified_data.models.domain.flow import (
            CapitalFlowRecord as CFR2,
        )

        assert CFR1 is CFR2

    def test_flow_service_re_exported_from_services(self):
        from skills.data.unified_data.services import FlowService as FS1
        from skills.data.unified_data.services.flow_service import (
            FlowService as FS2,
        )

        assert FS1 is FS2

    def test_persistence_result_re_exported_from_services(self):
        from skills.data.unified_data.services import (
            PersistenceResult as PR1,
        )
        from skills.data.unified_data.services.flow_service import (
            PersistenceResult as PR2,
        )

        assert PR1 is PR2