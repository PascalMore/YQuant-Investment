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