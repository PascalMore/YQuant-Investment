"""Phase 3 P3-C 22-field MarketSentimentSnapshot canonical contract tests.

The 22-field canonical contract (RFC-03-014 V0.16 / SPEC-03-014 V0.15 /
DESIGN-03-014 V0.23 §3.3) replaces the earlier T3-B 10-field offline
``sentiment_type`` aggregation model. Pascal 2026-07-30 ratified this
22-field full-market multi-dimensional snapshot as the canonical
product schema.

Unique key: ``{market, snapshot_date, snapshot_time}``.

This module exercises:

* Dataclass field schema (all 22 fields, defaults, ``frozen=False``).
* ``from_dict()`` round-trip + missing optionals + non-dict guard.
* northbound_net_flow / market_temperature fail-stop (Pascal C / OQ-2).
* ``limit_up_pool`` / ``limit_down_pool`` self-dedup invariant.
* ``continuous_limit_up`` dict structure constraints.
* Service layer read-path key plumbing (uses snapshot_date /
  snapshot_time, no sentiment_type).
* P3PersistenceWriter upsert round-trip with the
  ``{market, snapshot_date, snapshot_time}`` business key.
* ``LimitUpPoolRecord`` is unchanged (regression baseline).

All tests are offline:

* No real MongoDB — uses mongomock / FakeDatabase.
* No real Provider API call — uses StubSentimentProvider.
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
    LimitUpPoolRecord,
    MarketSentimentSnapshot,
)
from skills.data.unified_data.providers.sentiment_stub import (
    StubSentimentProvider,
)
from skills.data.unified_data.services.sentiment_service import (
    MarketSentimentService,
)
from skills.data.unified_data.tests.fixtures.sentiment_fixtures import (
    sample_market_sentiment_records,
)


SENTIMENT_CAP = "sentiment.market_snapshot"
SENTIMENT_COLLECTION = "03_data_ud_market_sentiment_snapshot"


# ===========================================================================
# Helpers
# ===========================================================================


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


# ===========================================================================
# Regression — default stub payload is the canonical 22-field contract
# ===========================================================================


class TestStubSentimentProviderCanonicalPayload:
    """The public offline stub must not expose the superseded 10-field shape."""

    def test_default_fetch_returns_only_canonical_22_field_records(self):
        records = StubSentimentProvider().fetch(
            "sentiment",
            "market_snapshot",
            None,
        )
        canonical_fields = set(MarketSentimentSnapshot.__dataclass_fields__)
        legacy_fields = {
            "sentiment_type",
            "market_date",
            "score",
            "sample_size",
            "source",
            "notes",
            "metadata",
        }

        assert records
        for record in records:
            assert set(record) == canonical_fields
            assert set(record).isdisjoint(legacy_fields)


# ===========================================================================
# Test ① — dataclass schema (22 fields, canonical unique key, Pascal C/X2)
# ===========================================================================


class TestMarketSentimentSnapshotSchema:
    """MarketSentimentSnapshot 22-field canonical contract per DESIGN §3.3."""

    def test_dataclass_has_exactly_22_fields(self):
        """The dataclass must declare exactly 22 fields — no more, no less.

        Per DESIGN-03-014 §3.3 / SPEC-03-014 V0.15 / RFC-03-014 V0.16.
        """
        fields = list(MarketSentimentSnapshot.__dataclass_fields__)
        assert len(fields) == 22, f"expected 22 fields, got {len(fields)}"

    def test_dataclass_field_names_match_canonical_contract(self):
        """The 22 field names must match the canonical Pascal contract."""
        expected = {
            "snapshot_date",
            "snapshot_time",
            "market",
            "limit_up_count",
            "limit_down_count",
            "limit_up_count_ex_st",
            "limit_down_count_ex_st",
            "advance_count",
            "decline_count",
            "flat_count",
            "total_listed_count",
            "market_temperature",
            "total_turnover",
            "hot_concepts",
            "continuous_limit_up",
            "max_continuous_days",
            "northbound_net_flow",
            "limit_up_pool",
            "limit_down_pool",
            "fetched_at",
            "provider",
            "raw_payload",
        }
        actual = set(MarketSentimentSnapshot.__dataclass_fields__)
        assert actual == expected, (
            f"field set mismatch.\n"
            f"missing: {expected - actual}\nextra: {actual - expected}"
        )

    def test_dataclass_is_not_frozen_or_slot(self):
        """Canonical dataclass is mutable (``frozen=False, slots=False``).

        Per SPEC-03-014 V0.15 §12.bis.1: 关闭 ``frozen=True, slots=True``
        (按 SPEC §3.3 可修改的 dataclass 模式). The T3-B frozen offline
        model has been superseded.
        """
        cls = MarketSentimentSnapshot
        assert cls.__dataclass_params__.frozen is False
        assert cls.__dataclass_params__.slots is False

    def test_unique_key_components_are_required_string_fields(self):
        """``snapshot_date`` and ``snapshot_time`` are positional required."""
        import dataclasses as _dc

        sig_fields = MarketSentimentSnapshot.__dataclass_fields__
        # snapshot_date and snapshot_time have no default → required.
        assert sig_fields["snapshot_date"].default is _dc.MISSING
        assert sig_fields["snapshot_time"].default is _dc.MISSING

    def test_market_defaults_to_cn(self):
        """``market`` defaults to ``"CN"`` when omitted."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )
        assert snap.market == "CN"

    def test_required_counts_default_to_zero(self):
        """Required count fields default to 0 (含 ST)."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )
        assert snap.limit_up_count == 0
        assert snap.limit_down_count == 0
        assert snap.advance_count == 0
        assert snap.decline_count == 0
        assert snap.flat_count == 0

    def test_optional_pool_fields_default_to_none(self):
        """Optional ex-ST / temperature / pool fields default to None."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )
        assert snap.limit_up_count_ex_st is None
        assert snap.limit_down_count_ex_st is None
        assert snap.total_listed_count is None
        assert snap.market_temperature is None
        assert snap.total_turnover is None
        assert snap.hot_concepts is None
        assert snap.continuous_limit_up is None
        assert snap.max_continuous_days is None
        assert snap.northbound_net_flow is None
        assert snap.limit_up_pool is None
        assert snap.limit_down_pool is None
        assert snap.fetched_at is None
        assert snap.raw_payload is None

    def test_provider_defaults_to_empty_string(self):
        """``provider`` defaults to ``""`` (filled by service layer)."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )
        assert snap.provider == ""


# ===========================================================================
# Test ② — from_dict round-trip + missing optionals
# ===========================================================================


class TestMarketSentimentSnapshotFromDict:
    """``from_dict`` 松弛映射，缺失字段填默认值，不抛 KeyError."""

    def test_from_dict_round_trip_with_all_22_fields(self):
        """``from_dict`` round-trips every canonical field."""
        sample = sample_market_sentiment_records()[0]
        snap = MarketSentimentSnapshot.from_dict(sample)
        # Required
        assert snap.snapshot_date == sample["snapshot_date"]
        assert snap.snapshot_time == sample["snapshot_time"]
        # Defaulted ints
        assert snap.limit_up_count == sample["limit_up_count"]
        assert snap.limit_down_count == sample["limit_down_count"]
        assert snap.advance_count == sample["advance_count"]
        # Optional ints
        assert snap.limit_up_count_ex_st == sample["limit_up_count_ex_st"]
        # Optional floats
        assert snap.market_temperature == sample["market_temperature"]
        assert snap.northbound_net_flow is None  # Pascal C — fixture forces None
        # Optional lists
        assert snap.hot_concepts == sample["hot_concepts"]
        assert snap.continuous_limit_up == sample["continuous_limit_up"]
        assert snap.limit_up_pool == sample["limit_up_pool"]
        # Metadata
        assert snap.provider == sample["provider"]
        assert snap.fetched_at == sample["fetched_at"]

    def test_from_dict_tolerates_missing_required_with_empty_strings(self):
        """Missing ``snapshot_date`` / ``snapshot_time`` coerce to ``""``."""
        snap = MarketSentimentSnapshot.from_dict({})
        assert snap.snapshot_date == ""
        assert snap.snapshot_time == ""
        assert snap.market == "CN"  # default

    def test_from_dict_tolerates_missing_optionals_with_defaults(self):
        """Missing optional fields fall back to declared defaults."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "market": "CN",
            }
        )
        assert snap.limit_up_count == 0
        assert snap.limit_down_count == 0
        assert snap.limit_up_count_ex_st is None
        assert snap.market_temperature is None
        assert snap.continuous_limit_up is None
        assert snap.limit_up_pool is None
        assert snap.provider == ""

    def test_from_dict_rejects_non_dict_input(self):
        """``from_dict`` raises TypeError on non-dict input."""
        with pytest.raises(TypeError):
            MarketSentimentSnapshot.from_dict("not_a_dict")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            MarketSentimentSnapshot.from_dict(123)  # type: ignore[arg-type]

    def test_default_stub_record_maps_to_valid_fail_stop_snapshot(self):
        record = StubSentimentProvider().fetch(
            "sentiment",
            "market_snapshot",
            None,
        )[0]

        snap = MarketSentimentSnapshot.from_dict(record)

        assert snap.snapshot_date == "2026-07-21"
        assert snap.snapshot_time == "close"
        assert snap.northbound_net_flow is None
        assert snap.market_temperature is None

    def test_from_dict_zero_count_falsy_values(self):
        """Zero / falsy counts are preserved (``d.get(..., 0) or 0``)."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "limit_up_count": 0,
                "limit_down_count": 0,
                "advance_count": 0,
                "decline_count": 0,
                "flat_count": 0,
            }
        )
        assert snap.limit_up_count == 0
        assert snap.limit_down_count == 0
        assert snap.advance_count == 0
        assert snap.decline_count == 0
        assert snap.flat_count == 0


# ===========================================================================
# Test ③ — Pascal C: northbound_net_flow is permanently None
# ===========================================================================


class TestMarketSentimentSnapshotNorthboundFailStop:
    """Pascal C: ``northbound_net_flow`` is permanently None (Phase 3)."""

    def test_northbound_net_flow_from_dict_is_none(self):
        """Even if source dict supplies a numeric value, dataclass ignores it.

        Per Pascal C 2026-07-26 (DESIGN §4.2.1): northbound_net_inflow 恒 None,
        fetch 路径不指向任何真实 endpoint.
        """
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "northbound_net_flow": 12345.6,  # must NOT propagate
            }
        )
        assert snap.northbound_net_flow is None

    def test_northbound_net_flow_constructor_is_none(self):
        """Direct constructor call still defaults to None."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )
        assert snap.northbound_net_flow is None


# ===========================================================================
# Test ④ — Pascal OQ-2: market_temperature is None (no fabricated formula)
# ===========================================================================


class TestMarketSentimentSnapshotTemperatureNone:
    """Pascal OQ-2: ``market_temperature`` allowed None — no fabricated formula."""

    def test_market_temperature_default_is_none(self):
        """``market_temperature`` is None when not provided."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )
        assert snap.market_temperature is None

    def test_market_temperature_from_dict_supplied_value_passes_through(self):
        """When source dict supplies a value, it passes through verbatim."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "market_temperature": 67.5,
            }
        )
        assert snap.market_temperature == 67.5


# ===========================================================================
# Test ⑤ — limit_up_pool / limit_down_pool self-dedup
# ===========================================================================


class TestMarketSentimentSnapshotPoolDedup:
    """同一文档中 limit_up_pool / limit_down_pool 列表自身去重."""

    def test_limit_up_pool_accepts_string_list(self):
        """``limit_up_pool`` accepts ``list[str]`` shape per DESIGN §3.3."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
            limit_up_pool=["600519", "000001", "002415"],
        )
        assert snap.limit_up_pool == ["600519", "000001", "002415"]

    def test_limit_down_pool_accepts_string_list(self):
        """``limit_down_pool`` accepts ``list[str]`` shape per DESIGN §3.3."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
            limit_down_pool=["300750", "002594"],
        )
        assert snap.limit_down_pool == ["300750", "002594"]

    def test_from_dict_stably_deduplicates_both_pools(self):
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "limit_up_pool": ["A", "A", "B"],
                "limit_down_pool": ["C", "C"],
            }
        )

        assert snap.limit_up_pool == ["A", "B"]
        assert snap.limit_down_pool == ["C"]

    @pytest.mark.parametrize("pool_field", ["limit_up_pool", "limit_down_pool"])
    def test_from_dict_preserves_pool_nullable_semantics(self, pool_field):
        missing = MarketSentimentSnapshot.from_dict(
            {"snapshot_date": "2026-07-21", "snapshot_time": "close"}
        )
        explicit_none = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                pool_field: None,
            }
        )
        empty = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                pool_field: [],
            }
        )

        assert getattr(missing, pool_field) is None
        assert getattr(explicit_none, pool_field) is None
        assert getattr(empty, pool_field) == []


# ===========================================================================
# Test ⑥ — continuous_limit_up shape
# ===========================================================================


class TestMarketSentimentSnapshotContinuousLimitUp:
    """``continuous_limit_up`` is ``list[dict]`` with symbol/days/reason."""

    def test_continuous_limit_up_accepts_dict_list(self):
        """Each dict carries ``symbol`` / ``days`` / ``reason``."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
            continuous_limit_up=[
                {"symbol": "600519", "days": 5, "reason": "白酒龙头"},
                {"symbol": "002415", "days": 3, "reason": "AI 概念"},
            ],
        )
        assert len(snap.continuous_limit_up) == 2
        assert snap.continuous_limit_up[0]["symbol"] == "600519"

    def test_max_continuous_days_accepts_int(self):
        """``max_continuous_days`` is a positive int (or None)."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
            max_continuous_days=7,
        )
        assert snap.max_continuous_days == 7


# ===========================================================================
# Test ⑦ — service read-path uses canonical snapshot_date/snapshot_time
# ===========================================================================


class TestMarketSentimentServiceReadPath:
    """``get_market_sentiment_snapshot`` uses ``snapshot_date`` / ``snapshot_time``."""

    def test_query_path_with_canonical_keys(self):
        """Service accepts ``snapshot_date`` + ``snapshot_time`` (no sentiment_type)."""
        registry = ProviderRegistry()
        stub = _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result = svc.get_market_sentiment_snapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )

        assert result.succeeded
        assert result.provider == "sentiment_stub"
        assert "ud_materialized" not in result.source_trace
        # Stub recorded exactly one fetch call.
        assert len(stub.call_log) == 1
        recorded_capability, recorded_market, recorded_params = stub.call_log[0]
        assert recorded_capability == SENTIMENT_CAP
        # snapshot_date / snapshot_time reach the provider as params.
        assert recorded_params.get("snapshot_date") == "2026-07-21"
        assert recorded_params.get("snapshot_time") == "close"

    def test_query_path_market_level_marker_in_source_trace(self):
        """Service appends the ``market_level_query(security_id=None)`` marker."""
        registry = ProviderRegistry()
        _register_stub(registry)
        router = DataRouter(registry=registry)
        svc = MarketSentimentService(adapter=None, router=router)

        result = svc.get_market_sentiment_snapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )

        marker = "market_level_query(security_id=None)"
        assert result.source_trace.count(marker) == 1

    def test_no_router_raises_provider_unavailable(self):
        """``MarketSentimentService(adapter)`` (no router) → query raises."""
        svc = MarketSentimentService(adapter=None)
        with pytest.raises(ProviderUnavailableError) as excinfo:
            svc.get_market_sentiment_snapshot(
                snapshot_date="2026-07-21",
                snapshot_time="close",
            )
        assert "no router wired" in str(excinfo.value)


# ===========================================================================
# Test ⑧ — P3PersistenceWriter round-trip with business unique key
# ===========================================================================


class TestMarketSentimentPersistenceRoundTrip:
    """Writer upsert round-trips via ``{market, snapshot_date, snapshot_time}``."""

    def test_writer_upsert_round_trip_with_canonical_key(self):
        """Records upsert via canonical 22-field unique key."""
        writer = P3PersistenceWriter(_make_db())
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
                "market_temperature": None,
                "northbound_net_flow": None,  # Pascal C
                "provider": "sentiment_stub",
            },
        ]
        outcome = writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=records,
            unique_key={"market", "snapshot_date", "snapshot_time"},
        )
        assert outcome.persisted == 1
        assert outcome.failed == 0

        # Read back via the canonical business unique key.
        docs = writer.get(
            SENTIMENT_COLLECTION,
            {
                "market": "CN",
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
            },
        )
        assert len(docs) == 1
        assert docs[0]["limit_up_count"] == 42
        assert docs[0]["northbound_net_flow"] is None

    def test_writer_upsert_extreme_market_conditions(self):
        """Extreme market scenario (large limit_up_count) round-trips cleanly."""
        writer = P3PersistenceWriter(_make_db())
        records = [
            {
                "market": "CN",
                "snapshot_date": "2026-07-22",
                "snapshot_time": "close",
                "limit_up_count": 450,  # extreme bull
                "limit_down_count": 5,
                "advance_count": 4800,
                "decline_count": 100,
                "flat_count": 100,
                "limit_up_pool": ["600519", "000001", "002415"],
                "continuous_limit_up": [
                    {"symbol": "600519", "days": 7, "reason": "白酒龙头"},
                ],
                "max_continuous_days": 7,
                "northbound_net_flow": None,  # Pascal C
                "provider": "sentiment_stub",
            },
        ]
        outcome = writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=records,
            unique_key={"market", "snapshot_date", "snapshot_time"},
        )
        assert outcome.persisted == 1
        docs = writer.get(
            SENTIMENT_COLLECTION,
            {
                "market": "CN",
                "snapshot_date": "2026-07-22",
                "snapshot_time": "close",
            },
        )
        assert docs[0]["limit_up_count"] == 450
        assert docs[0]["continuous_limit_up"][0]["days"] == 7


# ===========================================================================
# Test ⑨ — LimitUpPoolRecord regression baseline (unchanged)
# ===========================================================================


class TestLimitUpPoolRecordRegressionBaseline:
    """LimitUpPoolRecord is unchanged by the 22-field migration."""

    def test_limit_up_pool_record_field_count_unchanged(self):
        """LimitUpPoolRecord keeps its 17+1 field shape."""
        fields = set(LimitUpPoolRecord.__dataclass_fields__)
        # Spot-check: required core fields are still present.
        for required in (
            "symbol",
            "market",
            "trade_date",
            "status",
            "limit_up_time",
            "last_price",
            "pct_chg",
            "order_amount",
            "turnover_amount",
            "order_ratio",
            "turnover_rate",
            "consecutive_days",
            "reason",
            "market_cap",
            "fetched_at",
            "provider",
        ):
            assert required in fields, f"missing required field {required!r}"

    def test_limit_up_pool_record_from_dict_round_trip(self):
        """Round-trip via from_dict preserves the contract."""
        data = {
            "symbol": "600519",
            "market": "CN",
            "trade_date": "2026-07-22",
            "status": "limit_up",
            "limit_up_time": "09:30:05",
            "last_price": 150.25,
            "pct_chg": 10.0,
            "order_amount": 850_000_000.0,
            "turnover_amount": 120_000_000.0,
            "order_ratio": 7.08,
            "turnover_rate": 0.85,
            "consecutive_days": 3,
            "reason": "白酒板块强势",
            "market_cap": 188_700_000_000.0,
            "fetched_at": "2026-07-22T10:00:00",
            "provider": "stub",
        }
        record = LimitUpPoolRecord.from_dict(data)
        assert record.symbol == "600519"
        assert record.order_amount == 850_000_000.0
        assert record.consecutive_days == 3


# ===========================================================================
# Test ⑩ — EOD-6 / SPEC-03-014 V0.22 §3.3: total_turnover is permanently None
# ===========================================================================
#
# Per V0.22 §3.3 EOD-6: ``MarketSentimentSnapshot.total_turnover`` is
# permanently ``None`` on the canonical output path. The single
# implementation site is :meth:`MarketSentimentSnapshot.from_dict` — the
# offline default stub payload and both canonical fixtures also carry
# ``None`` so the contract is enforced at every ingress.


class TestTotalTurnoverPermanentlyNone:
    """``total_turnover`` is permanently ``None`` on the canonical path."""

    def test_offline_default_stub_payload_carries_none(self):
        """The default :class:`StubSentimentProvider` payload has ``total_turnover=None``."""
        records = StubSentimentProvider().fetch(
            "sentiment",
            "market_snapshot",
            None,
        )
        assert records
        for record in records:
            assert record["total_turnover"] is None

    def test_canonical_fixture_record_1_carries_none(self):
        """The first canonical fixture payload (``sample_market_sentiment_records()[0]``)
        has ``total_turnover=None``."""
        records = sample_market_sentiment_records()
        assert records
        assert records[0]["total_turnover"] is None

    def test_canonical_fixture_record_2_carries_none(self):
        """The second canonical fixture payload (extreme bull) also
        has ``total_turnover=None``."""
        records = sample_market_sentiment_records()
        assert len(records) >= 2
        assert records[1]["total_turnover"] is None

    def test_from_dict_keeps_none_when_source_is_none(self):
        """``from_dict({..., 'total_turnover': None})`` keeps ``total_turnover=None``."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "total_turnover": None,
            }
        )
        assert snap.total_turnover is None

    def test_from_dict_clamps_numeric_total_turnover_to_none(self):
        """``from_dict`` rejects a numeric ``total_turnover`` and
        coerces it to ``None`` (SPEC EOD-6 Pascal C-style fail-stop,
        mirroring the ``northbound_net_flow`` pattern)."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "total_turnover": 850_000_000_000.0,
            }
        )
        assert snap.total_turnover is None, (
            "EOD-6: total_turnover is permanently None on the canonical "
            "read path; from_dict must not propagate a numeric value"
        )

    def test_from_dict_clamps_fabricated_capital_flow_to_none(self):
        """A pseudo-value (e.g. capital flow) cannot be silently mapped
        to ``total_turnover`` — :func:`from_dict` coerces to ``None``."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                # 资金净流入 fabricated value — must not survive.
                "total_turnover": -12345678.9,
            }
        )
        assert snap.total_turnover is None

    def test_from_dict_does_not_mutate_caller_dict(self):
        """``from_dict`` does not mutate the caller-supplied dict —
        the canonical ``None`` is only enforced on the resulting
        dataclass instance (defensive copy semantics)."""
        source = {
            "snapshot_date": "2026-07-21",
            "snapshot_time": "close",
            "total_turnover": 42.0,
        }
        MarketSentimentSnapshot.from_dict(source)
        # Caller's dict is not mutated — the caller's value is preserved.
        assert source["total_turnover"] == 42.0

    def test_other_fields_unchanged_when_clamps_total_turnover(self):
        """The total_turnover fail-stop must not affect any other field."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "limit_up_count": 7,
                "advance_count": 1000,
                "total_turnover": 1.5e12,
                "northbound_net_flow": 999.0,  # must also be clamped
            }
        )
        assert snap.total_turnover is None
        assert snap.northbound_net_flow is None
        assert snap.limit_up_count == 7
        assert snap.advance_count == 1000