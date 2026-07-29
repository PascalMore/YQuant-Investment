"""Phase 3 P3-A SectorService injection-boundary test (offline T3-A).

T3-A acceptance matrix entry ④ (kanban task body, decision C.a):

| #   | test name                       | file                       |
|-----|---------------------------------|----------------------------|
| ④   | test_sector_service_injection   | test_sector_service.py     |

The current ``SectorService`` (Phase 1A) takes only
``adapter: TA_CNMongoAdapter`` and exposes three TA-CN MongoDB
read-only methods. T3-A is **offline only**: it must NOT add the
future ``get_sector_snapshot`` / ``get_sector_ranking`` methods
(those arrive in Gate-authorised implementation phases), and it
must NOT modify ``services/sector_service.py``.

This test therefore validates the **DI surface that T3-A can lock in
without touching the service module**:

* The current ``SectorService.__init__`` signature still accepts the
  Phase 1A ``adapter`` kwarg (regression guard).
* ``SectorService.DOMAIN == "sector"`` — the future
  ``get_sector_snapshot`` method will need a domain constant for
  router dispatch, even when added later.
* ``SectorService`` can be constructed with a stub adapter and the
  existing Phase 1A read methods are still reachable.
* The constructor signature remains narrow — T3-A is forbidden from
  widening it (``adapter`` only; no extra kwargs at this point).
* Two ``SectorService`` instances share no mutable state.

No real MongoDB / AKShare / cron / AuditLogger / QualitySummary
side-effects are exercised.
"""

from __future__ import annotations

import inspect

from skills.data.unified_data.services.sector_service import SectorService


class _StubTA_CNAdapter:
    """Minimal duck-type stand-in for ``TA_CNMongoAdapter``.

    Phase 1A's ``SectorService`` only requires an object that exposes
    the three adapter methods (``get_stock_sector_info``,
    ``get_stocks_by_sector``, ``get_index_daily_bars``) when those
    methods are actually called. ``SectorService`` injection
    boundary testing does not invoke them, so an empty object is
    sufficient.
    """

    def __init__(self) -> None:
        self.call_log: list[str] = []

    def get_stock_sector_info(self, full_symbol, classify_system=None):
        self.call_log.append("get_stock_sector_info")
        return []

    def get_stocks_by_sector(self, l1_code, classify_system="SW"):
        self.call_log.append("get_stocks_by_sector")
        return []

    def get_index_daily_bars(
        self,
        symbol=None,
        sector_code=None,
        start_date=None,
        end_date=None,
        limit=120,
    ):
        self.call_log.append("get_index_daily_bars")
        return []


class TestSectorServiceInjection:
    """P3-A ``SectorService`` injection boundary."""

    def test_constructs_with_phase_1a_adapter_kwarg(self):
        """Regression guard — current API surface still works."""
        adapter = _StubTA_CNAdapter()
        service = SectorService(adapter=adapter)
        assert service is not None
        # Internal attribute matches the injected adapter (no rebinding).
        assert service._adapter is adapter

    def test_domain_constant_is_sector(self):
        """Future ``get_sector_snapshot`` will need the domain constant."""
        assert SectorService.DOMAIN == "sector"

    def test_phase_1a_methods_still_present(self):
        """Regression guard — existing methods are NOT removed by T3-A."""
        for name in (
            "get_stock_sector",
            "get_stocks_by_sector",
            "get_sector_index_bars",
        ):
            assert hasattr(SectorService, name), f"missing {name!r}"
            assert callable(getattr(SectorService, name))

    def test_constructor_signature_is_phase_1a_plus_router(self):
        """T3-A + D3 locks the constructor signature.

        ``adapter`` is required (Phase 1A regression guard, T3-A) and
        has no default — dropping it would silently break every
        caller that built a service without a router. ``router``
        gained a ``None`` default at D3 so offline / Phase 1A-only
        callers keep working; the router is the only D3 widening of
        the signature, and there is no setter (the lazy ``router``
        attribute was removed). Keep this test in sync with the
        SectorService ``__init__`` source of truth.
        """
        sig = inspect.signature(SectorService.__init__)
        params = list(sig.parameters)
        # ``self`` plus ``adapter`` (required) and ``router`` (D3
        # added kwarg with ``None`` default). No other kwargs.
        assert params == ["self", "adapter", "router"]
        assert sig.parameters["adapter"].default is inspect.Parameter.empty
        # ``router`` defaults to ``None`` — offline callers build the
        # service without a router and the P3-A methods then raise
        # ``ProviderUnavailableError``.
        assert sig.parameters["router"].default is None

    def test_can_be_constructed_multiple_times_independently(self):
        """Two SectorService instances share no mutable state."""
        a = SectorService(adapter=_StubTA_CNAdapter())
        b = SectorService(adapter=_StubTA_CNAdapter())
        assert a is not b
        assert a._adapter is not b._adapter

    def test_module_exposes_domain_constant_for_router_dispatch(self):
        """The ``DOMAIN`` constant is reachable from the class itself,
        which the future P3-A ``get_sector_snapshot`` method will
        consult to build the router capability string
        (``f"{DOMAIN}.snapshot"``).
        """
        # Class attribute access (not instance attribute) — mirrors
        # the way Service subclasses reference the constant.
        assert SectorService.DOMAIN
        assert isinstance(SectorService.DOMAIN, str)
        assert "." not in SectorService.DOMAIN


# ---------------------------------------------------------------------------
# P3-A / T3-B — SectorSnapshot service layer (DESIGN-03-014 §17.6.1)
# ---------------------------------------------------------------------------
# Six test cases for the offline ``get_sector_snapshot`` / ``get_sector_ranking``
# contract. The T3-A injection-boundary tests above remain untouched.
#
# Contract (SPEC-03-014 §5.5 / DESIGN-03-014 §17.3.1):
#
# * ``get_sector_snapshot(sector_code, date=None)`` → ``DataResult.data`` is a
#   single ``SectorSnapshot`` (or ``None`` for empty).
# * ``get_sector_ranking(date=None, sector_type=None, limit=20)`` →
#   ``DataResult.data`` is a ``list[SectorSnapshot]`` sorted by ``pct_chg``
#   desc with ``None pct_chg`` at the end and ``sector_code`` asc as the
#   tiebreaker (DESIGN §17.3.3).
# * Empty / error semantics follow the standard ``DataResult`` contract
#   (``is_empty=True`` for empty; ``provider="error"`` for failure).
# * ``source_trace`` must not include ``"ud_materialized(ok)"`` or
#   ``"cache(ok)"`` (SPEC §5.5 / A-021, V0.12 D1 contract) — the
#   P3 read path is read-only. ``"(skipped: ...)"`` / ``"miss"`` /
#   ``"error: ..."`` entries from non-wired Step 2/3 slots are still
#   allowed; only the canonical ``"(ok)"`` success markers are
#   forbidden.
# * ``router=None`` → ``ProviderUnavailableError`` (DESIGN §17.3.2).
#
# Tests are offline — no real MongoDB, no real AKShare, no env reads.


from typing import Any

import pytest

from skills.data.unified_data import (
    DataRouter,
    Market,
    ProviderRegistry,
    SecurityId,
)
from skills.data.unified_data.exceptions import ProviderUnavailableError
from skills.data.unified_data.models.domain.sector import SectorSnapshot
from skills.data.unified_data.services.sector_service import (
    SectorService as _ImportedSectorService,
)
from skills.data.unified_data.tests.fixtures.sector_fixtures import (
    StubAKShareSectorProvider,
)


# Re-export so the class can be referenced uniformly inside this module
# without re-importing in every test.
SectorService = _ImportedSectorService


def _build_service(router: DataRouter | None) -> SectorService:
    """Build a :class:`SectorService` with a router wired via the constructor kwarg.

    D3 changed the constructor signature to
    ``__init__(self, adapter, router: DataRouter | None = None)`` —
    the previous lazy ``router`` setter was removed. ``adapter`` is
    still required (Phase 1A regression guard, T3-A) but is
    irrelevant on the P3-A read path so we pass ``None`` here.
    """
    return SectorService(adapter=None, router=router)  # type: ignore[arg-type]


SNAPSHOT_CAP = "sector.snapshot"
RANKING_CAP = "sector.ranking"


def _register_stub(
    registry: ProviderRegistry,
    *,
    payload: list[dict] | None = None,
    name: str = "sector_stub",
    raise_on_fetch: BaseException | None = None,
) -> StubAKShareSectorProvider:
    """Register a :class:`StubAKShareSectorProvider` for the P3-A capabilities."""
    stub = StubAKShareSectorProvider(
        name=name,
        payload=payload,
        capabilities=(SNAPSHOT_CAP, RANKING_CAP),
        markets={Market.CN},
        raise_on_fetch=raise_on_fetch,
    )
    registry.register(stub)
    return stub


def _to_snapshot(d: dict) -> SectorSnapshot:
    """Serialise a stub dict to a canonical :class:`SectorSnapshot`."""
    return SectorSnapshot.from_dict(d)


class TestGetSectorSnapshotOffline:
    """Test ①–③: ``get_sector_snapshot`` happy / empty / error paths."""

    def test_normal_returns_sector_snapshot(self):
        """Step 4 success → ``DataResult`` carries one ``SectorSnapshot``."""
        payload = [
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "rank": 5,
                "pct_chg": 2.35,
                "advance_count": 12,
                "decline_count": 3,
                "total_count": 15,
            }
        ]
        registry = ProviderRegistry()
        stub = _register_stub(registry, payload=payload)
        router = DataRouter(registry=registry)
        # The Phase 1A adapter is still accepted (regression guard —
        # the constructor signature must remain compatible with T3-A).
        svc = _build_service(router)

        result = svc.get_sector_snapshot(sector_code="BK0489", date="2026-07-21")

        assert result.succeeded
        assert isinstance(result.data, SectorSnapshot)
        assert result.data.sector_code == "BK0489"
        assert result.data.sector_name == "白酒"
        assert result.data.pct_chg == 2.35
        assert result.data.rank == 5
        # Stub is the only candidate — provider reflects that.
        assert result.provider == "sector_stub"
        # Query path is read-only — Step 2 / Step 3 must NOT record
        # the canonical ``"(ok)"`` success markers. ``skipped`` /
        # ``miss`` / ``error: ...`` entries are still allowed (the
        # trace just must not claim Step 2/3 produced data).
        assert "ud_materialized(ok)" not in result.source_trace
        assert "cache(ok)" not in result.source_trace
        # The stub was hit exactly once with the right capability.
        assert len(stub.call_log) == 1
        recorded_name, recorded_capability, _sid, _params = stub.call_log[0]
        assert recorded_name == "sector_stub"
        assert recorded_capability == SNAPSHOT_CAP

    def test_empty_returns_data_result_with_is_empty(self):
        """Empty stub payload → ``DataResult.is_empty`` is ``True``."""
        registry = ProviderRegistry()
        _register_stub(registry, payload=[])
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_snapshot(sector_code="BK0489")

        assert result.is_empty()
        # Empty payload — data is None (per Phase 0 ``DataResult.success``).
        assert result.data is None
        # Query path is read-only — Step 2 / Step 3 must NOT record
        # the canonical ``"(ok)"`` success markers even on the empty
        # path. ``skipped`` / ``miss`` / ``error: ...`` entries are
        # still allowed (the trace just must not claim Step 2/3
        # produced data).
        assert "ud_materialized(ok)" not in result.source_trace
        assert "cache(ok)" not in result.source_trace

    def test_provider_failure_returns_data_result_error(self):
        """Provider raises → ``DataResult.error(provider="error")``."""
        registry = ProviderRegistry()
        _register_stub(
            registry,
            raise_on_fetch=RuntimeError("simulated akshare failure"),
        )
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_snapshot(sector_code="BK0489")

        # Router records the failure in ``provider="error"``; the
        # service layer does not re-raise — it returns the wrapped
        # error DataResult.
        assert result.provider == "error"
        assert result.data is None
        assert result.is_empty()
        # The original provider name is preserved in source_trace.
        assert any("sector_stub" in entry for entry in result.source_trace)


class TestGetSectorRankingOffline:
    """Test ④–⑤: ``get_sector_ranking`` happy path + sort stability."""

    def test_normal_returns_list_of_sector_snapshots(self):
        """Step 4 success → ``DataResult`` carries ``list[SectorSnapshot]``."""
        payload = [
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 2.35,
            },
            {
                "sector_code": "BK0500",
                "sector_name": "证券",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 0.10,
            },
        ]
        registry = ProviderRegistry()
        stub = _register_stub(registry, payload=payload)
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_ranking(date="2026-07-21")

        assert result.succeeded
        assert isinstance(result.data, list)
        assert all(isinstance(item, SectorSnapshot) for item in result.data)
        assert len(result.data) == 2
        # Provider reflects the stub.
        assert result.provider == "sector_stub"
        # Query path is read-only — Step 2 / Step 3 must NOT record
        # the canonical ``"(ok)"`` success markers. ``skipped`` /
        # ``miss`` / ``error: ...`` entries are still allowed.
        assert "ud_materialized(ok)" not in result.source_trace
        assert "cache(ok)" not in result.source_trace
        # Capability dispatched correctly.
        assert stub.call_log[0][1] == RANKING_CAP

    def test_sort_stability_with_none_pct_chg_at_end(self):
        """Sort: ``pct_chg`` desc, ties broken by ``sector_code`` asc,
        ``None pct_chg`` placed at the end (DESIGN §17.3.3).

        Fixture layout (3 records):

        * BK0490 / pct_chg=2.5
        * BK0489 / pct_chg=2.5   ← tie-break by sector_code
        * BK0500 / pct_chg=None  ← goes to the end

        Expected order: BK0489 (2.5), BK0490 (2.5), BK0500 (None).
        """
        payload = [
            {
                "sector_code": "BK0490",
                "sector_name": "证券",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 2.5,
            },
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 2.5,
            },
            {
                "sector_code": "BK0500",
                "sector_name": "新能源",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": None,
            },
        ]
        registry = ProviderRegistry()
        _register_stub(registry, payload=payload)
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_ranking()

        assert result.succeeded
        ordered_codes = [s.sector_code for s in result.data]
        assert ordered_codes == ["BK0489", "BK0490", "BK0500"]
        # The None-pct_chg record lands at the end.
        assert result.data[-1].pct_chg is None

    def test_sort_stability_with_sector_name_asc(self):
        """DESIGN §17.3.3 稳定性：同 ``pct_chg`` + 同 ``sector_code``
        时按 ``sector_name`` 升序决定相对顺序。

        Fixture (3 records) — two records deliberately share both
        ``pct_chg`` AND ``sector_code`` (a benign quirk: the AKShare
        sector provider has historically returned duplicates for
        the same board when ``sector_type`` filters mis-fire); the
        third record uses different codes so we can also confirm
        ``pct_chg`` desc still wins over sector_name.

        Layout:

        * BK0001 / pct_chg=1.5 / sector_name="证券"
        * BK0001 / pct_chg=1.5 / sector_name="白酒"  ← same code, ties → sector_name asc
        * BK0002 / pct_chg=0.8 / sector_name="新能源"

        Expected order (sorted):
            BK0001 / 白酒 (1.5),
            BK0001 / 证券 (1.5),
            BK0002 / 新能源 (0.8).

        The two BK0001 records are ordered by ``"白酒" < "证券"``
        (Unicode codepoint order — "白酒" (U+767D) < "证券" (U+8BC1)),
        which the new 4-tuple sort key resolves deterministically.
        """
        payload = [
            # Same pct_chg + same code, sector_name last in Unicode
            # order — must end up AFTER the 白酒 record.
            {
                "sector_code": "BK0001",
                "sector_name": "证券",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 1.5,
            },
            # Same pct_chg + same code, sector_name first in Unicode
            # order — must lead the BK0001 pair.
            {
                "sector_code": "BK0001",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 1.5,
            },
            # Lower pct_chg — must trail the BK0001 pair regardless
            # of its sector_name (desc wins over asc sector_name).
            {
                "sector_code": "BK0002",
                "sector_name": "新能源",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 0.8,
            },
        ]
        registry = ProviderRegistry()
        _register_stub(registry, payload=payload)
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_ranking()

        assert result.succeeded
        # Identify each record by ``(sector_code, sector_name)`` —
        # the duplicate ``sector_code`` makes ``sector_code`` alone
        # ambiguous as a positional check.
        ordered_pairs = [
            (s.sector_code, s.sector_name) for s in result.data
        ]
        assert ordered_pairs == [
            ("BK0001", "白酒"),
            ("BK0001", "证券"),
            ("BK0002", "新能源"),
        ]
        # pct_chg still wins: the lowest pct_chg record is last,
        # even though its sector_name sorts AFTER the BK0001 pair.
        assert result.data[0].pct_chg == 1.5
        assert result.data[-1].pct_chg == 0.8


class TestGetSectorSnapshotInjectionBoundary:
    """Test ⑥: ``router=None`` → ``ProviderUnavailableError``."""

    def test_router_none_raises_provider_unavailable(self):
        """No router wired → service refuses to query (DESIGN §17.3.2)."""
        # Build a SectorService without a router. The Phase 1A
        # ``adapter`` kwarg is preserved so the existing T3-A
        # injection-boundary tests stay green.
        svc = _build_service(router=None)

        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.get_sector_snapshot(sector_code="BK0489")
        # Message identifies the surface.
        assert "router" in str(excinfo.value).lower() or "wired" in str(excinfo.value).lower()

        with pytest.raises(ProviderUnavailableError):
            svc.get_sector_ranking()


# ---------------------------------------------------------------------------
# Lite/P3-A D2 Fix — external Provider Step-4 freshness must be "delayed"
# (RFC-03-014 V0.13 §5.1.5; SPEC-03-014 V0.12 §5.5; DESIGN-03-014 V0.19
# §17.6.2). Offline, single-stub, no MongoDB / AKShare / Provider / network.
# ---------------------------------------------------------------------------


class TestP3ExternalFreshnessDelayed:
    """D2 contract pin: P3 Step-4 success → ``freshness == "delayed"``.

    Without the D2 fix, ``_query_external_chain`` delegates
    ``freshness_label`` to :meth:`FreshnessPolicy.label`, which uses
    ``ts`` age: ``fetched_at`` defaults to ``datetime.utcnow()`` so a
    fresh-enough request (within the 60s realtime threshold) would
    yield ``"realtime"``. SPEC-03-014 §5.5 / DESIGN-03-014 §17.6.2
    forbid that branch for P3 capabilities — every Step-4 success
    must surface ``"delayed"``. These tests cover both P3-A
    capabilities end-to-end through :class:`SectorService` and also
    pin the underlying router helper / single-provider pin path so
    D1/D3 callers can rely on a stable invariance.
    """

    @staticmethod
    def _build_router_with_sector_stub(
        payload: list[dict], name: str = "sector_stub"
    ) -> tuple[DataRouter, StubAKShareSectorProvider]:
        registry = ProviderRegistry()
        stub = _register_stub(registry, payload=payload, name=name)
        return DataRouter(registry=registry), stub

    def test_p3_sector_snapshot_step4_success_is_delayed(self):
        """``sector.snapshot`` Step-4 success → ``freshness == "delayed"``.

        ``DataRouter.query(fetched_at=datetime.utcnow())`` would, with
        the age-based policy, report ``"realtime"`` because the call
        happens well within the 60s threshold. The D2 fix overrides
        that branch for the six P3 capabilities so consumers can rely
        on ``freshness=="delayed"`` to mean "external, not persisted".
        """
        payload = [
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "rank": 5,
                "pct_chg": 2.35,
                "advance_count": 12,
                "decline_count": 3,
                "total_count": 15,
            }
        ]
        router, stub = self._build_router_with_sector_stub(payload)
        svc = _build_service(router)

        result = svc.get_sector_snapshot(sector_code="BK0489")

        assert result.succeeded
        # D2 contract pin — see module docstring.
        assert result.freshness == "delayed", (
            "P3 sector.snapshot Step-4 success must surface "
            "freshness='delayed' (SPEC §5.5 / DESIGN §17.6.2); "
            f"got {result.freshness!r}"
        )
        # Provider surface is unchanged.
        assert result.provider == "sector_stub"
        # Stub was invoked exactly once with the expected capability.
        assert len(stub.call_log) == 1
        assert stub.call_log[0][1] == SNAPSHOT_CAP

    def test_p3_sector_ranking_step4_success_is_delayed(self):
        """``sector.ranking`` Step-4 success → ``freshness == "delayed"``.

        The other P3-A capability. Same D2 contract.
        """
        payload = [
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 2.35,
            },
            {
                "sector_code": "BK0500",
                "sector_name": "证券",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 0.10,
            },
        ]
        router, stub = self._build_router_with_sector_stub(payload)
        svc = _build_service(router)

        result = svc.get_sector_ranking(date="2026-07-21")

        assert result.succeeded
        assert result.freshness == "delayed"
        assert result.provider == "sector_stub"
        assert stub.call_log[0][1] == RANKING_CAP

    def test_p3_external_single_step4_success_is_delayed(self):
        """Router-level single-provider pin path also pins ``"delayed"``.

        ``_query_external_single`` is the Step-4 path used when the
        caller passes ``provider=<name>``. Same D2 contract applies —
        covers the alternative code path that the chain helper does
        not exercise.
        """
        from datetime import datetime, timezone

        from skills.data.unified_data import Market, SecurityId

        registry = ProviderRegistry()
        stub = _register_stub(
            registry,
            payload=[
                {
                    "sector_code": "BK0489",
                    "sector_name": "白酒",
                    "sector_type": "industry",
                    "snapshot_date": "2026-07-21",
                    "market": "CN",
                    "provider": "sector_stub",
                    "pct_chg": 2.35,
                }
            ],
        )
        router = DataRouter(registry=registry)

        # ``fetched_at=now`` keeps the call well within the 60s
        # realtime branch — D2 must override.
        ts = datetime.now(timezone.utc).replace(tzinfo=None)
        result = router.query(
            "sector",
            "snapshot",
            SecurityId(symbol="BK0489", market=Market.CN),
            provider="sector_stub",
            fetched_at=ts,
        )

        assert result.succeeded
        assert result.freshness == "delayed"
        assert result.provider == "sector_stub"

    def test_non_p3_capability_keeps_age_based_label(self):
        """Non-P3 capability → age-based label is preserved.

        Regression guard: the D2 fix must NOT touch the freshness
        semantics for non-P3 capabilities. We drive a non-P3
        capability through the chain path with ``fetched_at=now`` so
        the legacy age-based branch reports ``"realtime"`` and the
        test pins that the override is capability-scoped, not
        global.
        """
        from datetime import datetime, timezone

        from skills.data.unified_data import DataProvider, Market, SecurityId
        from skills.data.unified_data.freshness import FreshnessPolicy

        # Sanity: pre-bound DEFAULT_TTLS has no "sector" / "flow" /
        # "sentiment" entry — but it does have "market_data". A
        # ``market_data`` query that goes external-to-OK should
        # therefore keep the age-based label.
        # ``realtime`` requires age < 60s.
        assert FreshnessPolicy()._REALTIME_THRESHOLD == 60

        # Build a stub provider for a non-P3 capability. Inherits
        # from :class:`DataProvider` so the registry's ``register``
        # accepts it without type complaints.
        class _NonP3Stub(DataProvider):
            @property
            def name(self) -> str:
                return "non_p3_stub"

            @property
            def capabilities(self) -> set[str]:
                return {"market_data.daily_bars"}

            @property
            def markets(self) -> set[Market]:
                return {Market.CN}

            def is_available(self) -> bool:
                return True

            def supports(self, capability: str, market: Market | str) -> bool:
                return capability == "market_data.daily_bars" and (
                    market == Market.CN or market == "CN"
                )

            def fetch(self, domain, operation, security_id, **params):
                return [{"close": 1.0}]

        registry = ProviderRegistry()
        registry.register(_NonP3Stub())
        router = DataRouter(registry=registry)

        ts = datetime.now(timezone.utc).replace(tzinfo=None)
        result = router.query(
            "market_data",
            "daily_bars",
            SecurityId(symbol="000001", market=Market.CN),
            provider="non_p3_stub",
            fetched_at=ts,
        )

        assert result.succeeded
        # Non-P3 keeps age-based semantics: a within-60s fetch surfaces
        # ``"realtime"`` rather than the P3-forced ``"delayed"``.
        assert result.freshness == "realtime", (
            "Non-P3 capabilities must keep the age-based "
            f"realtime/delayed split; got {result.freshness!r}"
        )