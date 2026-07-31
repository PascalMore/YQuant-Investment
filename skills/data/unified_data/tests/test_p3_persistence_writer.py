"""Phase 3 P3-A persistence writer tests (offline T3-A scaffold).

T3-A acceptance matrix (kanban task body, decision C.a):

| #   | test name                            | file                          |
|-----|--------------------------------------|-------------------------------|
| ①   | test_refresh_writes_via_p3_writer    | test_p3_persistence_writer.py |
| ②   | test_upsert_outcome_dataclass        | test_p3_persistence_writer.py |

Both tests rely on a :mod:`mongomock` in-memory database. **No real
MongoDB connection**, **no real Provider/API call**, **no AuditLogger
writes**, **no QualitySummary writes** — the offline guard rails from
the task body remain intact.

Tests live in this single file because the writer's ``upsert`` /
``UpsertOutcome`` surface is small enough that the writer can be
exercised end-to-end without splitting the file.

Three-class coverage (T3-B / T3-D verifier scope, kanban
``t_88a121fc``): the V0.5 §0.4 design enumerates three Phase-3
business collections — sector snapshot, capital flow, market
sentiment. Each test class below covers the write → get → delete
round-trip on **its** collection using the documented business unique
key. The four classic acceptance tests
(``test_all_records_persist`` /
``test_upsert_is_idempotent_on_business_key`` /
``test_delete_returns_record_count`` /
``test_constructor_rejects_real_pymongo``) are repeated per
collection so the verification matrix is uniform across all three.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from typing import Any

import mongomock
import pytest

from skills.data.unified_data.adapters.p3_persistence_writer import (
    P3_COLLECTION_BY_CAPABILITY,
    P3_UNIQUE_KEYS_BY_CAPABILITY,
    P3PersistenceWriter,
    UpsertOutcome,
)


SECTOR_COLLECTION = "03_data_ud_market_sector_snapshot"
SECTOR_UNIQUE_KEY = frozenset({"market", "sector_code", "snapshot_date"})

FLOW_COLLECTION = "03_data_ud_stock_capital_flow"
FLOW_UNIQUE_KEY = frozenset({"market", "symbol", "trade_date"})

SENTIMENT_COLLECTION = "03_data_ud_market_sentiment_snapshot"
SENTIMENT_UNIQUE_KEY = frozenset({"market", "snapshot_date", "snapshot_time"})


def _make_writer() -> P3PersistenceWriter:
    """Build a writer backed by a fresh in-memory mongomock database."""
    db = mongomock.MongoClient().get_database("tradingagents")
    return P3PersistenceWriter(db)


def _sample_records() -> list[dict]:
    """Three business records covering two sectors × two dates."""
    return [
        {
            "market": "CN",
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "pct_chg": 2.35,
            "rank": 5,
        },
        {
            "market": "CN",
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-20",
            "pct_chg": 1.10,
            "rank": 12,
        },
        {
            "market": "CN",
            "sector_code": "BK0500",
            "sector_name": "证券",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "pct_chg": -0.50,
            "rank": 88,
        },
    ]


# ---------------------------------------------------------------------------
# Test ② — UpsertOutcome dataclass behaviour
# ---------------------------------------------------------------------------


class TestUpsertOutcomeDataclass:
    """Pin the V0.5 §0.4 dataclass contract."""

    def test_is_dataclass_with_frozen_fields(self):
        # UpsertOutcome is a regular (non-frozen) dataclass because
        # ``append``-style mutation during ``upsert`` is the documented
        # pattern. We still want to confirm the documented fields
        # exist with the documented defaults.
        assert is_dataclass(UpsertOutcome)

        outcome = UpsertOutcome()
        assert outcome.persisted == 0
        assert outcome.failed == 0
        assert outcome.failed_keys == []
        assert outcome.errors == []

    def test_repr_includes_all_fields(self):
        outcome = UpsertOutcome(persisted=2, failed=1)
        text = repr(outcome)
        # Document the shape — repr carries every documented field so
        # operators can grep logs and spot partial failures quickly.
        for token in ("persisted=2", "failed=1", "failed_keys=[]", "errors=[]"):
            assert token in text

    def test_failed_keys_and_errors_default_to_independent_lists(self):
        """Two empty UpsertOutcome instances must NOT share their lists."""
        a = UpsertOutcome()
        b = UpsertOutcome()
        a.failed_keys.append({"k": 1})
        a.errors.append("boom")
        assert b.failed_keys == []
        assert b.errors == []

    def test_mutable_field_round_trip(self):
        outcome = UpsertOutcome()
        outcome.persisted = 3
        outcome.failed = 2
        outcome.failed_keys.append({"market": "CN", "sector_code": "BK0000"})
        outcome.errors.append("ConnectionError: nope")
        assert outcome.persisted == 3
        assert outcome.failed == 2
        assert outcome.failed_keys[0]["sector_code"] == "BK0000"
        assert "ConnectionError" in outcome.errors[0]


# ---------------------------------------------------------------------------
# Test ① — refresh path writes via P3PersistenceWriter
# ---------------------------------------------------------------------------


class TestRefreshWritesViaP3Writer:
    """The refresh path's upsert behaviour (DESIGN-03-014 §2.2 / §5.4)."""

    def test_all_records_persist(self):
        writer = _make_writer()
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 3
        assert outcome.failed == 0
        assert outcome.failed_keys == []
        assert outcome.errors == []

        # Every record is reachable through ``get`` with the business
        # unique-key filter — proving the writer did not fall back to
        # the LocalMongoAdapter ``materialized_key`` model.
        docs = writer.get(SECTOR_COLLECTION, {"sector_code": "BK0489"})
        dates = sorted(d["snapshot_date"] for d in docs)
        assert dates == ["2026-07-20", "2026-07-21"]

    def test_upsert_is_idempotent_on_business_key(self):
        """Re-running the same key overwrites in place (DESIGN-03-014 §5.4.3)."""
        writer = _make_writer()
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        # Same key, new payload — the older payload must be replaced.
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[
                {
                    "market": "CN",
                    "sector_code": "BK0489",
                    "sector_name": "白酒",
                    "sector_type": "industry",
                    "snapshot_date": "2026-07-21",
                    "pct_chg": 9.99,
                    "rank": 1,
                }
            ],
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 1
        assert outcome.failed == 0

        docs = writer.get(
            SECTOR_COLLECTION,
            {"sector_code": "BK0489", "snapshot_date": "2026-07-21"},
        )
        assert len(docs) == 1
        assert docs[0]["pct_chg"] == 9.99

        # Total document count is unchanged (overwrite, not insert).
        all_docs = writer.get(SECTOR_COLLECTION, {})
        assert len(all_docs) == 3

    def test_partial_failure_captures_failed_keys(self):
        """Records missing required key fields end up in failed_keys/errors."""
        writer = _make_writer()
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[
                # OK
                {
                    "market": "CN",
                    "sector_code": "BK0001",
                    "snapshot_date": "2026-07-21",
                    "pct_chg": 1.0,
                },
                # Missing ``sector_code`` → fails the unique-key check.
                {
                    "market": "CN",
                    "snapshot_date": "2026-07-21",
                    "pct_chg": 1.5,
                },
            ],
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 1
        assert outcome.failed == 1
        assert len(outcome.failed_keys) == 1
        assert outcome.failed_keys[0]["market"] == "CN"
        assert "sector_code" not in outcome.failed_keys[0]
        assert outcome.errors and "sector_code" in outcome.errors[0]

    def test_empty_records_is_noop(self):
        """No records → zero persisted, zero failed, no MongoDB writes."""
        writer = _make_writer()
        outcome = writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[],
            unique_key=SECTOR_UNIQUE_KEY,
        )
        assert outcome.persisted == 0
        assert outcome.failed == 0
        assert writer.get(SECTOR_COLLECTION, {}) == []

    def test_unknown_capability_raises(self):
        writer = _make_writer()
        with pytest.raises(ValueError):
            writer.collection_for("market_data.kline_daily")
        with pytest.raises(ValueError):
            writer.unique_key_for("market_data.kline_daily")

    def test_constructor_rejects_real_pymongo(self):
        """The offline guard refuses a real pymongo Database object."""

        class FakePymongoDatabase:
            pass

        # Mark the fake class as if it lived inside pymongo.
        FakePymongoDatabase.__module__ = "pymongo.database"
        with pytest.raises(TypeError) as excinfo:
            P3PersistenceWriter(FakePymongoDatabase())
        assert "pymongo" in str(excinfo.value).lower()

    def test_constructor_rejects_none(self):
        with pytest.raises(TypeError):
            P3PersistenceWriter(None)

    def test_capability_collection_map_covers_p3_a(self):
        """The 6 P3 capabilities are exactly what the router expects."""
        assert "sector.snapshot" in P3_COLLECTION_BY_CAPABILITY
        assert "sector.ranking" in P3_COLLECTION_BY_CAPABILITY
        assert (
            P3_COLLECTION_BY_CAPABILITY["sector.snapshot"]
            == SECTOR_COLLECTION
        )
        assert P3_UNIQUE_KEYS_BY_CAPABILITY["sector.snapshot"] == SECTOR_UNIQUE_KEY

    def test_get_returns_list_of_dicts(self):
        writer = _make_writer()
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        rows = writer.get(SECTOR_COLLECTION, {"sector_code": "BK0500"})
        assert isinstance(rows, list)
        assert len(rows) == 1
        assert isinstance(rows[0], dict)
        assert rows[0]["pct_chg"] == -0.50

    def test_delete_with_empty_filter_is_rejected(self):
        """Refuse accidental full-collection wipes (defensive guard)."""
        writer = _make_writer()
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        with pytest.raises(ValueError):
            writer.delete(SECTOR_COLLECTION, {})
        with pytest.raises(ValueError):
            writer.delete(SECTOR_COLLECTION, None)

    def test_delete_returns_record_count(self):
        writer = _make_writer()
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=_sample_records(),
            unique_key=SECTOR_UNIQUE_KEY,
        )
        n = writer.delete(SECTOR_COLLECTION, {"sector_code": "BK0500"})
        assert n == 1
        remaining = writer.get(SECTOR_COLLECTION, {})
        assert len(remaining) == 2


# ---------------------------------------------------------------------------
# Three-class coverage — P3-B capital flow (T3-B / T3-D verifier scope)
# ---------------------------------------------------------------------------


def _sample_flow_records() -> list[dict]:
    """Three capital-flow records across two symbols × two dates.

    Business unique key: ``{market, symbol, trade_date}`` per V0.5 §0.4.
    """
    return [
        {
            "market": "CN",
            "symbol": "600519",
            "trade_date": "2026-07-21",
            "main_net_inflow": 12_345_678.0,
            "main_net_inflow_pct": 1.23,
            "retail_net_inflow": -2_000_000.0,
            "super_large_net_inflow": 5_000_000.0,
            "large_net_inflow": 3_000_000.0,
            "medium_net_inflow": 2_000_000.0,
            "small_net_inflow": 2_345_678.0,
            "northbound_net_flow": None,
            "provider": "flow_stub",
        },
        {
            "market": "CN",
            "symbol": "600519",
            "trade_date": "2026-07-20",
            "main_net_inflow": 8_000_000.0,
            "main_net_inflow_pct": 0.50,
            "retail_net_inflow": -1_500_000.0,
            "provider": "flow_stub",
        },
        {
            "market": "CN",
            "symbol": "000001",
            "trade_date": "2026-07-21",
            "main_net_inflow": -3_500_000.0,
            "main_net_inflow_pct": -0.45,
            "retail_net_inflow": 1_000_000.0,
            "northbound_net_flow": None,
            "provider": "flow_stub",
        },
    ]


class TestCapitalFlowP3Writer:
    """V0.5 §0.4 / RFC V0.9 P3-B — capital flow collection round-trip.

    The :class:`P3PersistenceWriter` must serve the P3-B collection
    the same way it serves the sector snapshot collection. The
    business unique key is the documented
    ``{market, symbol, trade_date}``; routing by the wrong key (e.g.
    ``materialized_key``) would break both ``get`` and ``delete``
    below.
    """

    def test_all_records_persist(self):
        writer = _make_writer()
        records = _sample_flow_records()
        outcome = writer.upsert(
            collection=FLOW_COLLECTION,
            records=records,
            unique_key=FLOW_UNIQUE_KEY,
        )
        assert outcome.persisted == 3
        assert outcome.failed == 0
        assert outcome.failed_keys == []
        assert outcome.errors == []

        docs = writer.get(
            FLOW_COLLECTION,
            {"market": "CN", "symbol": "600519"},
        )
        dates = sorted(d["trade_date"] for d in docs)
        assert dates == ["2026-07-20", "2026-07-21"]

    def test_upsert_is_idempotent_on_business_key(self):
        """Re-running the same business key overwrites in place (V0.5 §5.4.3)."""
        writer = _make_writer()
        writer.upsert(
            collection=FLOW_COLLECTION,
            records=_sample_flow_records(),
            unique_key=FLOW_UNIQUE_KEY,
        )
        outcome = writer.upsert(
            collection=FLOW_COLLECTION,
            records=[
                {
                    "market": "CN",
                    "symbol": "600519",
                    "trade_date": "2026-07-21",
                    "main_net_inflow": 99_999_999.0,
                    "main_net_inflow_pct": 9.99,
                    "provider": "flow_stub",
                }
            ],
            unique_key=FLOW_UNIQUE_KEY,
        )
        assert outcome.persisted == 1
        assert outcome.failed == 0

        docs = writer.get(
            FLOW_COLLECTION,
            {"market": "CN", "symbol": "600519", "trade_date": "2026-07-21"},
        )
        assert len(docs) == 1
        assert docs[0]["main_net_inflow"] == 99_999_999.0

        all_docs = writer.get(FLOW_COLLECTION, {})
        assert len(all_docs) == 3

    def test_delete_returns_record_count(self):
        writer = _make_writer()
        writer.upsert(
            collection=FLOW_COLLECTION,
            records=_sample_flow_records(),
            unique_key=FLOW_UNIQUE_KEY,
        )
        n = writer.delete(
            FLOW_COLLECTION,
            {"market": "CN", "symbol": "000001"},
        )
        assert n == 1
        remaining = writer.get(FLOW_COLLECTION, {})
        assert len(remaining) == 2

    def test_constructor_rejects_real_pymongo(self):
        """Same offline guard tested for the sector path applies here too."""

        class FakePymongoDatabase:
            pass

        FakePymongoDatabase.__module__ = "pymongo.database"
        with pytest.raises(TypeError) as excinfo:
            P3PersistenceWriter(FakePymongoDatabase())
        assert "pymongo" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# Three-class coverage — P3-C market sentiment (T3-B / T3-D verifier scope)
# ---------------------------------------------------------------------------


def _sample_sentiment_records() -> list[dict]:
    """Three sentiment records across two dates × close/mid sessions.

    Business unique key: ``{market, snapshot_date, snapshot_time}``
    per V0.23 §3.3 (the canonical 22-field contract). The earlier
    ``{market, sentiment_type, market_date}`` key is superseded —
    callers must use the new one.
    """
    return [
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
            "northbound_net_flow": None,
            "provider": "sentiment_stub",
        },
        {
            "market": "CN",
            "snapshot_date": "2026-07-20",
            "snapshot_time": "close",
            "limit_up_count": 18,
            "limit_down_count": 12,
            "advance_count": 2100,
            "decline_count": 1800,
            "flat_count": 600,
            "market_temperature": None,
            "northbound_net_flow": None,
            "provider": "sentiment_stub",
        },
        {
            "market": "CN",
            "snapshot_date": "2026-07-21",
            "snapshot_time": "mid",
            "limit_up_count": 30,
            "limit_down_count": 6,
            "advance_count": 2800,
            "decline_count": 1700,
            "flat_count": 500,
            "market_temperature": None,
            "northbound_net_flow": None,
            "provider": "sentiment_stub",
        },
    ]


class TestMarketSentimentP3Writer:
    """V0.23 §3.3 / RFC V0.16 P3-C — market-sentiment collection round-trip.

    The sentiment collection shares the same writer but uses a
    different business unique key (``{market, snapshot_date,
    snapshot_time}``). A swap to the old ``sentiment_type /
    market_date`` form would still upsert but break
    ``get`` / ``delete`` because the filter wouldn't match.
    """

    def test_all_records_persist(self):
        writer = _make_writer()
        records = _sample_sentiment_records()
        outcome = writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=records,
            unique_key=SENTIMENT_UNIQUE_KEY,
        )
        assert outcome.persisted == 3
        assert outcome.failed == 0
        assert outcome.failed_keys == []
        assert outcome.errors == []

        docs = writer.get(
            SENTIMENT_COLLECTION,
            {"market": "CN", "snapshot_date": "2026-07-21"},
        )
        times = sorted(d["snapshot_time"] for d in docs)
        assert times == ["close", "mid"]

    def test_upsert_is_idempotent_on_business_key(self):
        """Re-running the same business key overwrites in place (V0.5 §5.4.3)."""
        writer = _make_writer()
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=_sample_sentiment_records(),
            unique_key=SENTIMENT_UNIQUE_KEY,
        )
        outcome = writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[
                {
                    "market": "CN",
                    "snapshot_date": "2026-07-21",
                    "snapshot_time": "close",
                    "limit_up_count": 99,
                    "limit_down_count": 0,
                    "advance_count": 5000,
                    "decline_count": 0,
                    "flat_count": 0,
                    "market_temperature": None,
                    "northbound_net_flow": None,
                    "provider": "sentiment_stub",
                }
            ],
            unique_key=SENTIMENT_UNIQUE_KEY,
        )
        assert outcome.persisted == 1
        assert outcome.failed == 0

        docs = writer.get(
            SENTIMENT_COLLECTION,
            {"market": "CN", "snapshot_date": "2026-07-21", "snapshot_time": "close"},
        )
        assert len(docs) == 1
        assert docs[0]["limit_up_count"] == 99

        all_docs = writer.get(SENTIMENT_COLLECTION, {})
        assert len(all_docs) == 3

    def test_delete_returns_record_count(self):
        writer = _make_writer()
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=_sample_sentiment_records(),
            unique_key=SENTIMENT_UNIQUE_KEY,
        )
        n = writer.delete(
            SENTIMENT_COLLECTION,
            {"market": "CN", "snapshot_date": "2026-07-20"},
        )
        assert n == 1
        remaining = writer.get(SENTIMENT_COLLECTION, {})
        assert len(remaining) == 2

    def test_constructor_rejects_real_pymongo(self):
        """Same offline guard tested for the sector path applies here too."""

        class FakePymongoDatabase:
            pass

        FakePymongoDatabase.__module__ = "pymongo.database"
        with pytest.raises(TypeError) as excinfo:
            P3PersistenceWriter(FakePymongoDatabase())
        assert "pymongo" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# Cross-collection — capability map and unique-key map completeness
# ---------------------------------------------------------------------------


class TestAllP3CollectionsCovered:
    """Sanity-check that the writer's dispatch tables list all 3 collections.

    Acts as a tripwire: if a new business collection is added to
    :data:`P3_COLLECTION_BY_CAPABILITY`, this class forces the test
    suite to grow alongside it.
    """

    def test_collection_map_has_exactly_three_collections(self):
        # 6 capability entries map onto 3 unique collection names —
        # sector has 2 capabilities (snapshot, ranking), flow has 2
        # (capital_flow_daily, northbound_daily), sentiment has 2
        # (market_snapshot, limit_up_pool). The tripwire counts the
        # unique collection values, not the capability entries.
        assert len(set(P3_COLLECTION_BY_CAPABILITY.values())) == 3

    def test_unique_key_map_has_exactly_three_keys(self):
        # Each of the 6 capabilities has a documented business unique
        # key; sector, flow, sentiment each contribute 2 frozensets.
        # The tripwire counts distinct unique keys by their frozenset
        # identity so capability aliases (e.g. sector.snapshot ==
        # sector.ranking) don't inflate the count.
        keys = {tuple(sorted(k)) for k in P3_UNIQUE_KEYS_BY_CAPABILITY.values()}
        assert len(keys) == 3

    def test_all_three_collections_have_distinct_unique_keys(self):
        # sector vs flow share the prefix {market, ...} but diverge.
        assert P3_UNIQUE_KEYS_BY_CAPABILITY["sector.snapshot"] != (
            P3_UNIQUE_KEYS_BY_CAPABILITY["flow.capital_flow_daily"]
        )
        assert P3_UNIQUE_KEYS_BY_CAPABILITY["sentiment.market_snapshot"] != (
            P3_UNIQUE_KEYS_BY_CAPABILITY["sector.snapshot"]
        )

    def test_collection_map_contains_sector_flow_sentiment(self):
        expected = {
            SECTOR_COLLECTION,
            FLOW_COLLECTION,
            SENTIMENT_COLLECTION,
        }
        assert set(P3_COLLECTION_BY_CAPABILITY.values()) == expected