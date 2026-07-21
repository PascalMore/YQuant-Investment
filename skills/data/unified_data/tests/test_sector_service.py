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

    def test_constructor_signature_is_phase_1a_only(self):
        """T3-A must NOT widen the constructor signature.

        The future P3-A ``get_sector_snapshot`` will receive the
        router via a lazy attribute (set after construction), **not**
        as a constructor kwarg — keeping the Phase 1A boundary
        untouched. Lock that contract here so future sub-phases can
        extend safely.
        """
        sig = inspect.signature(SectorService.__init__)
        params = list(sig.parameters)
        # ``self`` plus the single ``adapter`` parameter — nothing
        # else. P3-A must not introduce extra kwargs at this point.
        assert params == ["self", "adapter"]
        assert sig.parameters["adapter"].default is inspect.Parameter.empty

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