"""Phase 3 P0 mapping tests for the P3-B flow capability.

Covers the Phase 3 P0 contracts for ``flow.capital_flow_daily`` and
``flow.northbound_daily`` (DESIGN-03-014 §P0.4.1 / §P0.4.2 / §P0.6):

* ``_EXPECTED_FLOW_FIELDS`` baseline coverage (PB-1) — 10 mandatory
  fields plus the remaining band / metadata fields.
* Sign convention (SPEC §3.2): positive = net inflow, negative = net
  outflow. ``CapitalFlowRecord.from_dict`` is a passthrough — the
  dataclass does NOT transform signs.
* ``_EXPECTED_NORTHBOUND_FIELDS`` is exactly 3 fields
  (``northbound_net_inflow``, ``northbound_hold_shares``,
  ``northbound_hold_ratio``) (PB-2).
* PB-7 / PB-8 fail-stop guard: ``FlowService._is_northbound_refresh_disallowed()``
  is hard-coded to ``True`` regardless of construction kwargs.
* PB-8 fail-stop guard: ``_is_refresh_authorized()`` always returns
  ``False`` for ``flow.northbound_daily`` — northbound refresh must
  not enter the authorised state.
* Empty-result semantics (PB-3): an empty stub payload produces a
  successful ``DataResult`` with ``data=[]`` and ``provider="flow_stub"``
  — not a failure, not ``None``. ``source_trace`` stays free of
  ``ud_materialized`` markers.
* ``source_trace`` discipline: regardless of fixture size the read
  path produces zero ``ud_materialized(ok)`` markers (the P3 read
  path is read-only).
* ``CapitalFlowRecord.from_dict`` 松映射 + missing-field contract:
  missing optionals default to ``None``; ``trade_date`` keeps its raw
  ``"YYYY-MM-DD"`` shape (no auto-reformat).

All tests are offline: no real MongoDB / AKShare / network access.
"""

from __future__ import annotations

import inspect

import pytest

from skills.data.unified_data import (
    DataRouter,
    Market,
    ProviderRegistry,
    SecurityId,
)
from skills.data.unified_data.models.domain.flow import CapitalFlowRecord
from skills.data.unified_data.providers import _stub_columns
from skills.data.unified_data.providers.flow_stub import StubFlowProvider
from skills.data.unified_data.services.flow_service import FlowService


# ---------------------------------------------------------------------------
# Constants — single source of truth for the P3-B capability strings.
# ---------------------------------------------------------------------------

CAP_FLOW_DAILY = "flow.capital_flow_daily"
CAP_FLOW_NORTHBOUND = "flow.northbound_daily"

EXPECTED_FLOW = getattr(_stub_columns, "_EXPECTED_FLOW_FIELDS")
EXPECTED_NORTHBOUND = getattr(_stub_columns, "_EXPECTED_NORTHBOUND_FIELDS")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_registry(payload: list[dict] | None = None) -> tuple[ProviderRegistry, StubFlowProvider]:
    """Register a stub provider against the standard P3-B capabilities."""
    registry = ProviderRegistry()
    stub = StubFlowProvider(
        name="flow_stub",
        payload=payload,
        capabilities=frozenset({CAP_FLOW_DAILY, CAP_FLOW_NORTHBOUND}),
        markets={Market.CN},
    )
    registry.register(stub)
    return registry, stub


# ===========================================================================
# (1) ``_EXPECTED_FLOW_FIELDS`` baseline + ordering
# ===========================================================================


class TestExpectedFlowFieldsContract:
    """``_EXPECTED_FLOW_FIELDS`` baseline + frozen ordering contract."""

    def test_flow_set_includes_business_key_first(self) -> None:
        """The 3 business-key fields must lead the set (P3-B unique key)."""
        assert EXPECTED_FLOW[:3] == ("symbol", "market", "trade_date"), (
            f"_EXPECTED_FLOW_FIELDS must begin with the business unique key "
            f"(symbol / market / trade_date); got first 3 = "
            f"{list(EXPECTED_FLOW[:3])}"
        )

    def test_flow_set_carries_all_four_band_fields(self) -> None:
        """All four flow bands must be present."""
        flow_set = set(EXPECTED_FLOW)
        for field in (
            "main_net_inflow",
            "super_large_net_inflow",
            "large_net_inflow",
            "medium_net_inflow",
            "small_net_inflow",
        ):
            assert field in flow_set, (
                f"_EXPECTED_FLOW_FIELDS missing band {field!r}"
            )

    def test_flow_set_carries_main_ratio_field(self) -> None:
        """``main_net_inflow_ratio`` is the 10th mandatory field (PB-1)."""
        assert "main_net_inflow_ratio" in set(EXPECTED_FLOW)

    def test_flow_set_carries_margin_balance_field(self) -> None:
        """``margin_balance`` is mandatory (PB-1)."""
        assert "margin_balance" in set(EXPECTED_FLOW)

    def test_flow_set_carries_all_three_northbound_fields(self) -> None:
        """The 3 northbound_* fields are part of the V0.5 schema (PB-2)."""
        flow_set = set(EXPECTED_FLOW)
        for field in (
            "northbound_net_inflow",
            "northbound_hold_shares",
            "northbound_hold_ratio",
        ):
            assert field in flow_set, (
                f"_EXPECTED_FLOW_FIELDS missing northbound {field!r}"
            )

    def test_flow_set_carries_metadata_fields(self) -> None:
        """``fetched_at`` / ``provider`` are mandatory metadata fields."""
        flow_set = set(EXPECTED_FLOW)
        for field in ("fetched_at", "provider"):
            assert field in flow_set, (
                f"_EXPECTED_FLOW_FIELDS missing metadata {field!r}"
            )


# ===========================================================================
# (2) Sign convention (SPEC §3.2 表 footnote)
# ===========================================================================


class TestFlowSignConvention:
    """``from_dict`` preserves the sign of ``*_net_inflow`` fields.

    Positive = net inflow; negative = net outflow. The dataclass is a
    strict passthrough — ``from_dict`` MUST NOT transform / invert /
    coerce the sign.
    """

    @pytest.mark.parametrize(
        "field, value",
        [
            ("main_net_inflow", 1_230_000.0),
            ("super_large_net_inflow", 800_000.0),
            ("large_net_inflow", 430_000.0),
            ("medium_net_inflow", -50_000.0),
            ("small_net_inflow", -120_000.0),
        ],
    )
    def test_each_band_sign_preserved(self, field: str, value: float) -> None:
        record = CapitalFlowRecord.from_dict(
            {
                "symbol": "600519",
                "market": "CN",
                "trade_date": "2026-07-21",
                field: value,
            }
        )
        assert getattr(record, field) == value, (
            f"from_dict must preserve sign of {field!r}; "
            f"input={value}, output={getattr(record, field)}"
        )

    def test_negative_total_means_outflow(self) -> None:
        """When all bands are negative, the record represents net outflow."""
        record = CapitalFlowRecord.from_dict(
            {
                "symbol": "300999",
                "market": "CN",
                "trade_date": "2026-07-21",
                "main_net_inflow": -340_000.0,
                "super_large_net_inflow": -150_000.0,
                "large_net_inflow": -190_000.0,
                "medium_net_inflow": 30_000.0,
                "small_net_inflow": 80_000.0,
                "main_net_inflow_ratio": -2.1,
            }
        )
        # Main three bands negative → net outflow; only medium/small
        # are positive (retail buying).
        assert record.main_net_inflow < 0
        assert record.super_large_net_inflow < 0
        assert record.large_net_inflow < 0
        # main_net_inflow_ratio is a percentage — negative = outflow
        # share exceeds inflow share.
        assert record.main_net_inflow_ratio < 0


# ===========================================================================
# (3) Northbound three-fields-are-None contract (PB-2)
# ===========================================================================


class TestNorthboundFieldsContract:
    """``_EXPECTED_NORTHBOUND_FIELDS`` is exactly the 3 fail-stop fields."""

    def test_northbound_set_has_exactly_three_fields(self) -> None:
        assert len(EXPECTED_NORTHBOUND) == 3, (
            f"_EXPECTED_NORTHBOUND_FIELDS must be exactly 3 fields per "
            f"PB-2 / Pascal C; got {len(EXPECTED_NORTHBOUND)}"
        )

    def test_northbound_set_carries_exact_field_names(self) -> None:
        assert set(EXPECTED_NORTHBOUND) == {
            "northbound_net_inflow",
            "northbound_hold_shares",
            "northbound_hold_ratio",
        }

    def test_northbound_fields_are_subset_of_flow_fields(self) -> None:
        """The 3 northbound fields must be present in the parent flow set."""
        assert set(EXPECTED_NORTHBOUND).issubset(set(EXPECTED_FLOW))


# ===========================================================================
# (4) PB-7 / PB-8 fail-stop guards
# ===========================================================================


class TestNorthboundFailStopGuards:
    """PB-7 / PB-8: northbound refresh is permanently disallowed."""

    def test_is_northbound_refresh_disallowed_is_true(self) -> None:
        """PB-7: hard-coded ``True`` regardless of construction kwargs."""
        svc_no_writer = FlowService(adapter=None)
        assert svc_no_writer._is_northbound_refresh_disallowed() is True

        registry, _ = _build_registry()
        router = DataRouter(registry=registry)
        svc_with_router = FlowService(adapter=None, router=router)
        assert (
            svc_with_router._is_northbound_refresh_disallowed() is True
        )

    def test_is_northbound_refresh_disallowed_has_minimal_signature(self) -> None:
        """The guard must be a no-argument callable.

        ``@staticmethod`` is allowed (no ``self``); instance method
        with just ``self`` is also allowed. No configuration knobs.
        """
        method = FlowService._is_northbound_refresh_disallowed
        sig = inspect.signature(method)
        params = list(sig.parameters)
        # ``self`` (instance method) OR empty (staticmethod).
        assert params in (["self"], []), (
            f"_is_northbound_refresh_disallowed must take only ``self`` "
            f"(or be a staticmethod with no args); got params={params}"
        )

    def test_is_refresh_authorized_denies_northbound(self) -> None:
        """PB-8: northbound capability is never refresh-authorised."""
        svc = FlowService(adapter=None)
        # Capability string must be the frozen ``flow.northbound_daily``.
        authorised = svc._is_refresh_authorized(
            capability="flow.northbound_daily"
        )
        assert authorised is False, (
            "PB-8: northbound capability must never be refresh-authorised"
        )

    def test_is_refresh_authorized_signature_minimal(self) -> None:
        """``_is_refresh_authorized`` accepts only ``capability`` keyword.

        The P0 contract: no other configuration knobs. ``@staticmethod``
        is allowed (no ``self``); instance method with ``self`` is
        also allowed.
        """
        sig = inspect.signature(FlowService._is_refresh_authorized)
        params = list(sig.parameters)
        assert params in (["self", "capability"], ["capability"]), (
            f"_is_refresh_authorized must accept (capability) — "
            f"optionally as a staticmethod — got params={params}"
        )
        # The capability parameter must be keyword-only.
        capability_param = sig.parameters["capability"]
        assert (
            capability_param.kind is inspect.Parameter.KEYWORD_ONLY
        ), (
            "capability must be keyword-only so the P0 contract "
            "cannot be silently extended by positional callers"
        )


# ===========================================================================
# (5) Empty-result semantics (PB-3 / V0.5 §3.1)
# ===========================================================================


class TestFlowEmptyResultSemantics:
    """Empty payload → ``is_empty()`` + ``provider="flow_stub"`` + no failure.

    The V0.5 §3.1 contract: an empty DataFrame yields
    ``DataResult.success(data=None, provider="flow_stub")`` — empty
    is **not** a failure. The result carries ``provider="flow_stub"``
    (the stub returned, just empty) and ``source_trace`` stays free of
    ``ud_materialized(ok)`` markers (the read path is read-only).
    """

    def test_empty_payload_returns_empty_data_result(self) -> None:
        registry, _ = _build_registry(payload=[])
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = svc.get_capital_flow(security_id=sid)

        # Empty is not a failure; it is just empty.
        assert result.is_empty()
        # Provider attribution: stub was called and returned [].
        assert result.provider == "flow_stub"
        # No P3 step-2 (ok) marker — read path is read-only.
        assert "ud_materialized(ok)" not in result.source_trace

    def test_empty_payload_northbound_also_empty(self) -> None:
        registry, _ = _build_registry(payload=[])
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)

        result = svc.get_northbound_flow(date="2026-07-21")

        assert result.is_empty()
        assert result.provider == "flow_stub"
        assert "ud_materialized(ok)" not in result.source_trace


# ===========================================================================
# (6) source_trace discipline — read path is strictly read-only
# ===========================================================================


class TestFlowSourceTraceDiscipline:
    """The read path never produces ``ud_materialized(ok)`` markers.

    Per sector precedent (``test_sector_service.py`` empty path) the
    trace may carry ``skipped`` / ``miss`` / ``error: ...`` entries but
    must NOT claim Step 2 / Step 3 produced data via the canonical
    ``(ok)`` marker.
    """

    def test_get_capital_flow_does_not_materialize(self) -> None:
        registry, _ = _build_registry()
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = svc.get_capital_flow(
            security_id=sid, trade_date="2026-07-21"
        )

        assert "ud_materialized(ok)" not in result.source_trace

    def test_get_northbound_flow_does_not_materialize(self) -> None:
        registry, _ = _build_registry()
        router = DataRouter(registry=registry)
        svc = FlowService(adapter=None, router=router)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = svc.get_northbound_flow(
            security_id=sid, date="2026-07-21"
        )

        assert "ud_materialized(ok)" not in result.source_trace


# ===========================================================================
# (7) ``from_dict`` 松映射 + missing-field contract
# ===========================================================================


class TestCapitalFlowFromDictToleratesMissing:
    """``from_dict`` does not raise on missing optionals (SPEC §3.2)."""

    def test_minimal_dict_returns_none_fields(self) -> None:
        record = CapitalFlowRecord.from_dict(
            {
                "symbol": "600519",
                "market": "CN",
                "trade_date": "2026-07-21",
            }
        )
        assert record.symbol == "600519"
        assert record.market == "CN"
        assert record.trade_date == "2026-07-21"
        assert record.main_net_inflow is None
        assert record.super_large_net_inflow is None
        assert record.large_net_inflow is None
        assert record.medium_net_inflow is None
        assert record.small_net_inflow is None
        assert record.main_net_inflow_ratio is None
        assert record.northbound_net_inflow is None
        assert record.northbound_hold_shares is None
        assert record.northbound_hold_ratio is None
        assert record.margin_buy is None
        assert record.margin_sell is None
        assert record.margin_balance is None
        assert record.fetched_at is None
        assert record.provider == ""

    def test_trade_date_iso_passthrough(self) -> None:
        """``trade_date`` keeps its raw ``"YYYY-MM-DD"`` shape."""
        record = CapitalFlowRecord.from_dict(
            {
                "symbol": "600519",
                "market": "CN",
                "trade_date": "2026-07-21",
            }
        )
        assert record.trade_date == "2026-07-21"


# ===========================================================================
# (8) Drift tolerance — extra fields silently ignored, no KeyError
# ===========================================================================


class TestCapitalFlowFieldDrift:
    """``from_dict`` silently ignores extra keys; no KeyError on missing.

    Per DESIGN-03-014 §P0.3.1 the upstream AKShare endpoint may carry
    extra fields. ``from_dict`` MUST NOT raise on:
    * missing required text keys (defaults to ``""``),
    * extra keys not declared in the dataclass.
    """

    def test_extra_keys_silently_ignored(self) -> None:
        record = CapitalFlowRecord.from_dict(
            {
                "symbol": "600519",
                "market": "CN",
                "trade_date": "2026-07-21",
                # Drift: extra fields the dataclass does not know.
                "made_up_field": 12345,
                "another_drift": "foo",
            }
        )
        # Business keys survive; no KeyError raised.
        assert record.symbol == "600519"
        assert record.market == "CN"
        assert record.trade_date == "2026-07-21"


__all__ = [
    "CAP_FLOW_DAILY",
    "CAP_FLOW_NORTHBOUND",
    "TestExpectedFlowFieldsContract",
    "TestFlowSignConvention",
    "TestNorthboundFieldsContract",
    "TestNorthboundFailStopGuards",
    "TestFlowEmptyResultSemantics",
    "TestFlowSourceTraceDiscipline",
    "TestCapitalFlowFromDictToleratesMissing",
    "TestCapitalFlowFieldDrift",
]
