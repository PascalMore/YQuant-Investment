"""Phase 3 P0 mapping tests for the P3-C sentiment capability.

Covers the Phase 3 P0 contracts for ``sentiment.market_snapshot`` and
``sentiment.limit_up_pool`` (DESIGN-03-014 §P0.5 / §P0.6):

* ``_EXPECTED_SENTIMENT_FIELDS`` exact 22-field set (PC-1) — mirrors
  :class:`MarketSentimentSnapshot` byte-for-byte, no superseded
  10-field names.
* ``_EXPECTED_LIMIT_UP_FIELDS`` exact field set (PC-2) — mirrors
  :class:`LimitUpPoolRecord` byte-for-byte.
* **Pascal OQ-2**: ``market_temperature`` is ``None`` (no fabricated
  formula; the field is reserved for a future synthesis layer).
* **Pascal C**: ``northbound_net_flow`` is **permanently** ``None``
  on the read path — even if a source dict supplies a numeric
  value, ``from_dict`` rejects it.
* Empty-result semantics (X2): both ``get_market_sentiment_snapshot``
  and ``get_limit_up_pool`` return ``is_empty()`` + ``data=None`` on
  empty stub payload — empty is not a failure.
* ``limit_up_pool`` / ``limit_down_pool`` self-dedup invariant: a
  single stock does not appear twice in the same document.
* ``source_trace`` discipline: the read path never produces
  ``ud_materialized(ok)`` markers.
* Freshness table: ``sentiment`` (``sentiment_limit_up_pool``) and
  ``market_sentiment`` TTLs are both 3600s — both keys are exposed
  but the semantics are unchanged (the P0 contract pins the
  configuration, not the read logic).

All tests are offline: no real MongoDB / AKShare / network access.
"""

from __future__ import annotations

import pytest

from skills.data.unified_data import (
    DataRouter,
    Market,
    ProviderRegistry,
)
from skills.data.unified_data.freshness import FreshnessPolicy
from skills.data.unified_data.models.domain.sentiment import (
    LimitUpPoolRecord,
    MarketSentimentSnapshot,
)
from skills.data.unified_data.providers import _stub_columns
from skills.data.unified_data.providers.sentiment_stub import (
    StubSentimentProvider,
)
from skills.data.unified_data.services.sentiment_service import (
    MarketSentimentService,
)


# ---------------------------------------------------------------------------
# Constants — single source of truth for the P3-C capability strings.
# ---------------------------------------------------------------------------

CAP_SENTIMENT_SNAPSHOT = "sentiment.market_snapshot"
CAP_LIMIT_UP_POOL = "sentiment.limit_up_pool"

EXPECTED_SENTIMENT = getattr(_stub_columns, "_EXPECTED_SENTIMENT_FIELDS")
EXPECTED_LIMIT_UP = getattr(_stub_columns, "_EXPECTED_LIMIT_UP_FIELDS")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_registry(payload: list[dict] | None = None) -> ProviderRegistry:
    """Register a stub provider against the standard P3-C capabilities."""
    registry = ProviderRegistry()
    stub = StubSentimentProvider(
        name="sentiment_stub",
        payload=payload,
    )
    registry.register(stub)
    return registry


def _build_service(router: DataRouter | None) -> MarketSentimentService:
    """Build a :class:`MarketSentimentService` with a router wired via the
    constructor kwarg.

    The ``p3_writer`` is left at ``None`` so the read path is the only
    one we exercise here; the refresh path is reserved for the
    Gate-authorised sub-stage.
    """
    return MarketSentimentService(adapter=None, router=router)  # type: ignore[arg-type]


# ===========================================================================
# (1) ``_EXPECTED_SENTIMENT_FIELDS`` exact 22-field set (PC-1)
# ===========================================================================


class TestExpectedSentimentFieldsContract:
    """``_EXPECTED_SENTIMENT_FIELDS`` is the 22-field Pascal canonical contract."""

    def test_sentiment_set_has_exactly_twenty_two_fields(self) -> None:
        """PC-1: sentiment set must be exactly 22 fields."""
        assert len(EXPECTED_SENTIMENT) == 22, (
            f"_EXPECTED_SENTIMENT_FIELDS must be exactly 22 fields per "
            f"PC-1 / SPEC §3.3; got {len(EXPECTED_SENTIMENT)}"
        )

    def test_sentiment_set_matches_market_sentiment_snapshot_dataclass(self) -> None:
        """PC-1: the expected-set mirrors the 22-field dataclass exactly."""
        dataclass_fields = set(MarketSentimentSnapshot.__dataclass_fields__)
        expected = set(EXPECTED_SENTIMENT)
        assert dataclass_fields == expected, (
            f"sentiment expected-set mismatch with dataclass.\n"
            f"  dataclass has {len(dataclass_fields)} fields: "
            f"{sorted(dataclass_fields)}\n"
            f"  expected has {len(expected)} fields: "
            f"{sorted(expected)}\n"
            f"  dataclass-only: {sorted(dataclass_fields - expected)}\n"
            f"  expected-only:  {sorted(expected - dataclass_fields)}"
        )

    def test_sentiment_set_unique_key_leads(self) -> None:
        """PC-1: the 3 unique-key fields must lead the set."""
        assert EXPECTED_SENTIMENT[:3] == (
            "snapshot_date",
            "snapshot_time",
            "market",
        ), (
            f"_EXPECTED_SENTIMENT_FIELDS must begin with the 3 unique-key "
            f"fields (snapshot_date, snapshot_time, market); got first 3 = "
            f"{list(EXPECTED_SENTIMENT[:3])}"
        )

    def test_sentiment_set_no_superseded_ten_field_names(self) -> None:
        """PC-1: the 10-field superseded names are not present."""
        legacy_names = {
            "sentiment_type",
            "market_date",
            "score",
            "sample_size",
            "source",
            "notes",
            "metadata",
        }
        overlap = set(EXPECTED_SENTIMENT) & legacy_names
        assert not overlap, (
            f"_EXPECTED_SENTIMENT_FIELDS must NOT reference superseded "
            f"10-field names: {sorted(overlap)}"
        )


# ===========================================================================
# (2) ``_EXPECTED_LIMIT_UP_FIELDS`` exact field set (PC-2)
# ===========================================================================


class TestExpectedLimitUpFieldsContract:
    """``_EXPECTED_LIMIT_UP_FIELDS`` mirrors the 15-field dataclass."""

    def test_limit_up_set_matches_limit_up_pool_record_dataclass(self) -> None:
        """PC-2: the expected-set mirrors ``LimitUpPoolRecord`` exactly."""
        dataclass_fields = set(LimitUpPoolRecord.__dataclass_fields__)
        expected = set(EXPECTED_LIMIT_UP)
        assert dataclass_fields == expected, (
            f"limit-up expected-set mismatch with dataclass.\n"
            f"  dataclass has {len(dataclass_fields)} fields: "
            f"{sorted(dataclass_fields)}\n"
            f"  expected has {len(expected)} fields: "
            f"{sorted(expected)}\n"
            f"  dataclass-only: {sorted(dataclass_fields - expected)}\n"
            f"  expected-only:  {sorted(expected - dataclass_fields)}"
        )

    def test_limit_up_set_business_key_leads(self) -> None:
        """PC-2: the 3 business-key fields must lead the set."""
        assert EXPECTED_LIMIT_UP[:3] == (
            "symbol",
            "market",
            "trade_date",
        ), (
            f"_EXPECTED_LIMIT_UP_FIELDS must begin with the 3 business-key "
            f"fields (symbol, market, trade_date); got first 3 = "
            f"{list(EXPECTED_LIMIT_UP[:3])}"
        )


# ===========================================================================
# (3) Pascal OQ-2 — ``market_temperature`` is None
# ===========================================================================


class TestMarketTemperatureNoneInvariant:
    """Pascal OQ-2: ``market_temperature`` is None — no fabricated formula."""

    def test_default_market_temperature_is_none(self) -> None:
        """A freshly constructed snapshot defaults ``market_temperature``
        to ``None`` — no synthesis formula is implied at the
        dataclass layer."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )
        assert snap.market_temperature is None

    def test_from_dict_preserves_none_market_temperature(self) -> None:
        """``from_dict({..., 'market_temperature': None})`` keeps the field None."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "market_temperature": None,
            }
        )
        assert snap.market_temperature is None

    def test_from_dict_does_not_synthesize_market_temperature(self) -> None:
        """The dataclass does NOT derive a temperature from
        ``advance_count / (advance_count + decline_count)`` — even
        with extreme counts the field stays ``None``."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "advance_count": 4800,
                "decline_count": 100,
                "market_temperature": None,
            }
        )
        # OQ-2: extreme breadth does NOT trigger a derivation.
        assert snap.market_temperature is None


# ===========================================================================
# (4) Pascal C — ``northbound_net_flow`` is permanently None
# ===========================================================================


class TestNorthboundNetFlowNoneInvariant:
    """Pascal C: ``northbound_net_flow`` is permanently None on the read path."""

    def test_default_northbound_net_flow_is_none(self) -> None:
        """A freshly constructed snapshot defaults the field to ``None``."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )
        assert snap.northbound_net_flow is None

    def test_from_dict_zeros_northbound_net_flow_even_with_numeric_input(self) -> None:
        """Pascal C: ``from_dict`` rejects a numeric ``northbound_net_flow``
        — the read path never propagates a value, even if the source
        supplies one."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "northbound_net_flow": 1_234_567_890.0,  # would be a number
            }
        )
        assert snap.northbound_net_flow is None, (
            "Pascal C: northbound_net_flow must be permanently None on "
            "the read path; from_dict must not propagate a numeric value"
        )


# ===========================================================================
# (5) Empty-result semantics for both sentiment capabilities (X2)
# ===========================================================================


class TestSentimentEmptyResultSemantics:
    """Empty stub payload → ``is_empty()`` + ``data=None`` on both capabilities."""

    def test_market_snapshot_empty_payload_returns_empty_data_result(self) -> None:
        """Empty stub payload on ``sentiment.market_snapshot`` → empty + no failure."""
        registry = _build_registry(payload=[])
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_market_sentiment_snapshot(snapshot_date="2026-07-21")

        assert result.is_empty()
        assert result.data is None
        # Query path is read-only — no ``(ok)`` materialised marker.
        assert "ud_materialized(ok)" not in result.source_trace

    def test_limit_up_pool_empty_payload_returns_empty_data_result(self) -> None:
        """Empty stub payload on ``sentiment.limit_up_pool`` → empty + no failure."""
        registry = _build_registry(payload=[])
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_limit_up_pool(trade_date="2026-07-21")

        # The limit-up pool endpoint returns is_empty() on empty payload.
        assert result.is_empty()
        # Query path is read-only — no ``(ok)`` materialised marker.
        assert "ud_materialized(ok)" not in result.source_trace


# ===========================================================================
# (6) ``limit_up_pool`` / ``limit_down_pool`` self-dedup invariant
# ===========================================================================


class TestPoolStableDedup:
    """``from_dict`` preserves the **stable dedup** invariant on pool lists."""

    def test_limit_up_pool_dedups_duplicates_preserving_first_seen_order(self) -> None:
        """A pool carrying duplicate symbols survives intact as a
        first-seen-order, deduplicated list."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "limit_up_pool": [
                    "600519",
                    "000001",
                    "600519",  # duplicate
                    "002415",
                    "600519",  # duplicate
                ],
                "limit_down_pool": [
                    "002594",
                    "002594",  # duplicate
                    "300750",
                ],
            }
        )
        # Stable dedup: first-seen-order, no duplicates.
        assert snap.limit_up_pool == ["600519", "000001", "002415"]
        assert snap.limit_down_pool == ["002594", "300750"]

    def test_limit_up_pool_none_passes_through(self) -> None:
        """A ``None`` pool stays ``None`` after ``from_dict``."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "limit_up_pool": None,
                "limit_down_pool": None,
            }
        )
        assert snap.limit_up_pool is None
        assert snap.limit_down_pool is None

    def test_limit_up_pool_empty_list_passes_through(self) -> None:
        """An empty list pool stays an empty list after ``from_dict``."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "limit_up_pool": [],
                "limit_down_pool": [],
            }
        )
        assert snap.limit_up_pool == []
        assert snap.limit_down_pool == []


# ===========================================================================
# (7) ``source_trace`` discipline — read path is strictly read-only
# ===========================================================================


class TestSentimentSourceTraceDiscipline:
    """The read path never produces ``ud_materialized(ok)`` markers."""

    def test_market_snapshot_query_does_not_materialize(self) -> None:
        """``get_market_sentiment_snapshot`` is read-only — no ``(ok)`` markers."""
        registry = _build_registry()
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_market_sentiment_snapshot(
            snapshot_date="2026-07-21", snapshot_time="close"
        )

        assert "ud_materialized(ok)" not in result.source_trace

    def test_limit_up_pool_query_does_not_materialize(self) -> None:
        """``get_limit_up_pool`` is read-only — no ``(ok)`` markers."""
        registry = _build_registry()
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_limit_up_pool(trade_date="2026-07-21")

        assert "ud_materialized(ok)" not in result.source_trace


# ===========================================================================
# (8) Freshness — ``sentiment`` vs ``market_sentiment`` table exposure
# ===========================================================================


class TestFreshnessTableSentiment:
    """Freshness table exposes both ``sentiment_limit_up_pool`` and
    ``market_sentiment`` keys with the same 3600s TTL — the contract
    is "expose both keys, do not change semantics"."""

    def test_freshness_table_exposes_market_sentiment_key(self) -> None:
        """``FreshnessPolicy.DEFAULT_TTLS`` exposes ``market_sentiment``."""
        assert "market_sentiment" in FreshnessPolicy.DEFAULT_TTLS, (
            "freshness.DEFAULT_TTLS must expose the 'market_sentiment' "
            "key with a 3600s TTL per P0 contract"
        )

    def test_freshness_table_exposes_sentiment_limit_up_pool_key(self) -> None:
        """``FreshnessPolicy.DEFAULT_TTLS`` exposes
        ``sentiment_limit_up_pool`` (the sibling key the limit-up
        pool capability uses)."""
        assert "sentiment_limit_up_pool" in FreshnessPolicy.DEFAULT_TTLS, (
            "freshness.DEFAULT_TTLS must expose the "
            "'sentiment_limit_up_pool' key per P0 contract"
        )

    def test_freshness_table_sentiment_keys_share_3600s_ttl(self) -> None:
        """Both ``market_sentiment`` and ``sentiment_limit_up_pool``
        carry a 3600s TTL — the read logic is unchanged; only the
        configuration is pinned."""
        sentiment_ttl = FreshnessPolicy.DEFAULT_TTLS["market_sentiment"]
        limit_up_ttl = FreshnessPolicy.DEFAULT_TTLS["sentiment_limit_up_pool"]
        assert sentiment_ttl == 3600, (
            f"'market_sentiment' TTL must be 3600s; got {sentiment_ttl}"
        )
        assert limit_up_ttl == 3600, (
            f"'sentiment_limit_up_pool' TTL must be 3600s; got {limit_up_ttl}"
        )

    def test_freshness_lookup_returns_same_ttl_for_both_keys(self) -> None:
        """``get_ttl`` returns the same 3600s value for both keys —
        confirming the P0 contract that the two keys resolve to
        the same TTL bucket without rewriting read semantics."""
        policy = FreshnessPolicy()
        assert policy.get_ttl("market_sentiment") == 3600
        assert policy.get_ttl("sentiment_limit_up_pool") == 3600

    def test_sentiment_prefix_is_not_a_freshness_ttl_key(self) -> None:
        """F6 (SPEC-03-014-F6 C-3): ``sentiment`` is only a capability
        domain prefix — it must never be registered as a freshness TTL
        key (double key / alias would split freshness semantics)."""
        assert "sentiment" not in FreshnessPolicy.DEFAULT_TTLS, (
            "DEFAULT_TTLS must not register 'sentiment'; only the "
            "canonical keys 'market_sentiment' and "
            "'sentiment_limit_up_pool' (F6 ruling)."
        )


# ===========================================================================
# (8b) Total-turnover None invariant — SPEC-03-014 V0.22 §3.3 EOD-6
# ===========================================================================


class TestTotalTurnoverNoneInvariant:
    """``total_turnover`` is permanently ``None`` on the canonical read path.

    Per SPEC-03-014 V0.22 §3.3 EOD-6, ``total_turnover`` joins the
    pre-existing ``northbound_net_flow`` fail-stop pattern. The
    :meth:`MarketSentimentSnapshot.from_dict` ingress is the single
    implementation site; the offline default stub and the canonical
    fixtures also carry ``None``.
    """

    def test_default_total_turnover_is_none(self) -> None:
        """Direct constructor call defaults ``total_turnover`` to ``None``."""
        snap = MarketSentimentSnapshot(
            snapshot_date="2026-07-21",
            snapshot_time="close",
        )
        assert snap.total_turnover is None

    def test_from_dict_zeroes_total_turnover_when_numeric(self) -> None:
        """Numeric ``total_turnover`` is coerced back to ``None`` —
        even if the upstream source (e.g. a fabricated 资金净流入
        pseudo-value) tries to slip it in via the field key."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "total_turnover": 1.2e12,
            }
        )
        assert snap.total_turnover is None

    def test_from_dict_zeroes_fabricated_capital_flow_value(self) -> None:
        """A 资金净流入-style number cannot map to ``total_turnover``."""
        snap = MarketSentimentSnapshot.from_dict(
            {
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
                "total_turnover": -98765432.10,
            }
        )
        assert snap.total_turnover is None

    def test_default_stub_payload_has_none_total_turnover(self) -> None:
        """The offline default :class:`StubSentimentProvider` payload
        itself ships ``total_turnover=None`` (defence in depth)."""
        records = StubSentimentProvider().fetch(
            "sentiment",
            "market_snapshot",
            None,
        )
        assert records
        assert records[0]["total_turnover"] is None


__all__ = [
    "CAP_LIMIT_UP_POOL",
    "CAP_SENTIMENT_SNAPSHOT",
    "EXPECTED_LIMIT_UP",
    "EXPECTED_SENTIMENT",
    "TestExpectedSentimentFieldsContract",
    "TestExpectedLimitUpFieldsContract",
    "TestMarketTemperatureNoneInvariant",
    "TestNorthboundNetFlowNoneInvariant",
    "TestTotalTurnoverNoneInvariant",
    "TestSentimentEmptyResultSemantics",
    "TestPoolStableDedup",
    "TestSentimentSourceTraceDiscipline",
    "TestFreshnessTableSentiment",
]  # noqa: E501
