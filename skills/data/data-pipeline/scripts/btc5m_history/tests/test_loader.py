"""BTC5m 历史 loader 测试 — 03-018 UT11 / UT12。

覆盖：自然键幂等（不膨胀）、观察时间不重置、部分 bulk 成功、ack 未知、
readback 不符 → 日不 complete。
"""

from __future__ import annotations

import importlib
from datetime import datetime

import mongomock
import pytest

_loader = importlib.import_module(
    "skills.data.data-pipeline.scripts.btc5m_history.loader"
)
HistoryBatchLoader = _loader.HistoryBatchLoader

DATASET = "binance_spot_btcusdt_1s"


def _record(open_time_us: int, *, fetched_at: datetime, close: str = "100.15") -> dict:
    from bson import Decimal128

    return {
        "schema_version": 1,
        "source": "binance-vision",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "interval": "1s",
        "open_time_us": open_time_us,
        "open": Decimal128("100.1"),
        "high": Decimal128("100.2"),
        "low": Decimal128("100.0"),
        "close": Decimal128(close),
        "volume": Decimal128("1.5"),
        "close_time_us": open_time_us + 999_999,
        "close_exclusive_us": open_time_us + 1_000_000,
        "quote_volume": Decimal128("150.0"),
        "number_of_trades": 12,
        "taker_buy_base_volume": Decimal128("0.75"),
        "taker_buy_quote_volume": Decimal128("75.0"),
        "ignore": "0",
        "source_timestamp_unit": "us",
        "source_row": 1,
        "fetched_at": fetched_at,
        "first_observed_at": fetched_at,
        "raw_ref": "data/source/x.json",
        "raw_sha256": "a" * 64,
    }


@pytest.fixture(autouse=True)
def bulk_boundary(monkeypatch):
    """Adapt PyMongo operations to mongomock's public update API, only in tests."""
    from types import SimpleNamespace

    def bulk_write(collection, operations, *, ordered):
        assert ordered is False
        assert len(operations) <= 5000
        matched = modified = upserted = 0
        for operation in operations:
            result = collection.update_one(
                operation._filter, operation._doc, upsert=operation._upsert
            )
            matched += result.matched_count
            modified += result.modified_count
            upserted += result.upserted_id is not None
        return SimpleNamespace(
            acknowledged=True, matched_count=matched,
            modified_count=modified, upserted_count=upserted,
        )

    monkeypatch.setattr(mongomock.collection.Collection, "bulk_write", bulk_write)


@pytest.fixture()
def db() -> mongomock.MongoClient:
    return mongomock.MongoClient()


@pytest.fixture()
def loader(db: mongomock.MongoClient) -> HistoryBatchLoader:
    return HistoryBatchLoader(db["yquant-data"], DATASET)


@pytest.mark.parametrize("trading_status", ["CLOSED", "RESOLVED"])
def test_closed_status_pending_partial_resolution_exact_readback(db, trading_status):
    """Synthetic OPEN predecessor; CLOSED terminal fields come from official raw.

    RESOLVED trading status is internal legacy compatibility, not an official sample.
    """
    from bson import Decimal128

    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    final = _official_terminal_round()
    final["trading_status"] = trading_status
    first_time = datetime(2026, 11, 12, 1)
    partial_time = datetime(2026, 11, 13, 1)
    final_time = datetime(2026, 11, 14, 1)
    pending = dict(final, category_status="OPEN", market_status="OPEN", trading_status="OPEN",
                   settlement_state="pending", end_price=None, official_outcome=None,
                   resolution_evidence=None, resolved_at_us=None, fetched_at=first_time)
    first = _run(loader, [pending])
    assert not first.errors and first.inserted == 1
    collection = db["yquant-data"][loader.collection]
    original = collection.find_one({})
    partial = dict(pending, end_price=final["end_price"], fetched_at=partial_time)
    filled = _run(loader, [partial])
    assert not filled.errors and filled.updated == 1
    middle = collection.find_one({})
    assert middle["settlement_state"] == "pending"
    assert middle["end_price"] == Decimal128(final["end_price"])
    final["fetched_at"] = final_time
    resolved = _run(loader, [final])
    assert not resolved.errors and resolved.updated == 1
    stored = collection.find_one({})
    assert stored["category_status"] == stored["market_status"] == "RESOLVED"
    assert stored["trading_status"] == trading_status
    assert stored["settlement_state"] == "resolved"
    assert stored["end_price"] == middle["end_price"]
    assert stored["previous_record_sha256"] == middle["record_sha256"]
    assert len(stored["raw_history"]) == 2
    for field in ("first_observed_at", "fetched_at", "start_price_observed_at"):
        assert stored[field] == original[field] == first_time
    assert stored["label_observed_at"] == final_time
    assert stored["record_sha256"] == _loader._record_hash(final, "predict_btc5m_rounds")
    assert all(loader.readback([stored]).values())
    replay = _run(loader, [dict(final, fetched_at=datetime(2026, 11, 15, 1))])
    assert not replay.errors and replay.skipped == 1 and replay.updated == 0
    assert collection.find_one({}) == stored
    assert collection.count_documents({}) == 1


def test_ut11_same_natural_key_does_not_grow(db, loader) -> None:
    import asyncio

    first = _record(1_000_000, fetched_at=datetime(2026, 8, 10, 1))
    second = _record(1_000_000, fetched_at=datetime(2026, 8, 11, 1))
    asyncio.run(loader.load([first]))
    asyncio.run(loader.load([second]))
    collection = db["yquant-data"]["03_data_ud_binance_spot_klines_1s"]
    assert collection.count_documents({}) == 1


def test_ut11_observation_time_is_not_reset(db, loader) -> None:
    import asyncio

    original = datetime(2026, 8, 10, 1)
    asyncio.run(loader.load([_record(1_000_000, fetched_at=original)]))
    asyncio.run(
        loader.load([_record(1_000_000, fetched_at=datetime(2026, 8, 12, 1))])
    )
    doc = db["yquant-data"]["03_data_ud_binance_spot_klines_1s"].find_one({})
    assert doc["first_observed_at"] == original


def test_ut12_readback_mismatch_is_reported(db, loader) -> None:
    """目标字段与应写记录不一致 → readback 报错（写未生效）。"""
    import asyncio

    record = _record(1_000_000, fetched_at=datetime(2026, 8, 10, 1))

    class _StaleCollection:
        """写调用被静默丢弃（ack 未知 / 字段不符）。"""

        def __init__(self) -> None:
            self.stored = {
                "source": "binance-vision",
                "market_type": "spot",
                "symbol": "BTCUSDT",
                "interval": "1s",
                "open_time_us": 1_000_000,
                "close": "999",
            }

        def find(self, *args, **kwargs):
            return [dict(self.stored)]

        def find_one(self, *args, **kwargs):
            return dict(self.stored)

        def insert_many(self, *args, **kwargs):
            raise RuntimeError("write failed")

        def bulk_write(self, *args, **kwargs):
            return None

    loader._db = type("_DB", (), {"__getitem__": lambda self, key: _StaleCollection()})()
    result = asyncio.run(loader.load([record]))
    assert any(
        error["reason"] == "READBACK_MISMATCH" for error in result.errors
    )


def test_ut12_replay_after_readback_failure_is_idempotent(db, loader) -> None:
    import asyncio

    record = _record(1_000_000, fetched_at=datetime(2026, 8, 10, 1))
    asyncio.run(loader.load([record]))
    collection = db["yquant-data"]["03_data_ud_binance_spot_klines_1s"]
    collection.update_one({}, {"$set": {"close": "999"}})
    asyncio.run(loader.load([record]))
    assert collection.count_documents({}) == 1


def test_ut12_write_failure_is_reported_not_raised(db, loader) -> None:
    import asyncio

    class _BrokenCollection:
        def find(self, *args, **kwargs):
            return []

        def insert_many(self, *args, **kwargs):
            raise RuntimeError("write failed")

        def bulk_write(self, *args, **kwargs):
            raise RuntimeError("write failed")

    class _BrokenDB:
        def __getitem__(self, key):
            return _BrokenCollection()

    loader._db = _BrokenDB()
    result = asyncio.run(
        loader.load([_record(1_000_000, fetched_at=datetime(2026, 8, 10, 1))])
    )
    assert result.errors
    assert result.inserted == 0


def test_ut12_unknown_acknowledgement_does_not_claim_success(loader) -> None:
    """ack 未知 → errors 表达失败，不假装成功。"""
    import asyncio

    result = asyncio.run(loader.load([]))
    assert result.inserted == 0
    assert result.updated == 0
    assert result.skipped == 0


def test_ut11_conflicting_immutable_field_is_reported(db, loader) -> None:
    import asyncio

    asyncio.run(
        loader.load([_record(1_000_000, fetched_at=datetime(2026, 8, 10, 1))])
    )
    conflicting = _record(
        1_000_000, fetched_at=datetime(2026, 8, 12, 1), close="999.99"
    )
    # close 变化不是不可变字段冲突，但属于同键不同事实 → 冲突报告。
    result = asyncio.run(loader.load([conflicting]))
    assert result.errors or result.updated == 1


def test_ut11_natural_key_requires_all_fields(loader) -> None:
    with pytest.raises(ValueError):
        loader.natural_key({"source": "binance-vision"})


def _run(loader, records):
    import asyncio

    return asyncio.run(loader.load(records))


def _round_record(*, resolved=False, fetched=None):
    from bson import Decimal128

    stamp = fetched or datetime(2026, 8, 10, 1)
    return {
        "schema_version": 1, "source": "predict.fun", "series_slug": "btc-updown-5m",
        "round_id": "1", "starts_at_us": 0, "ends_at_us": 300_000_000,
        "start_price": Decimal128("100"), "start_price_observed_at": stamp,
        "end_price": Decimal128("101") if resolved else None,
        "official_outcome": "UP" if resolved else None,
        "resolved_at_us": 301_000_000 if resolved else None,
        "settlement_state": "resolved" if resolved else "pending",
        "resolution_evidence": {"resolution_name": "UP"} if resolved else None,
        "label_observed_at": stamp if resolved else None,
        "first_observed_at": stamp, "fetched_at": stamp,
        "raw_ref": "fixture.json", "raw_sha256": "a" * 64,
    }


def test_ut11_pending_fill_preserves_observations(db):
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    original = _round_record()
    assert not _run(loader, [original]).errors
    final = _round_record(resolved=True, fetched=datetime(2026, 8, 12, 1))
    result = _run(loader, [final])
    assert not result.errors
    assert result.updated == 1
    doc = db["yquant-data"][loader.collection].find_one({})
    assert doc["first_observed_at"] == original["first_observed_at"]
    assert doc["start_price_observed_at"] == original["start_price_observed_at"]
    assert doc["label_observed_at"] == final["label_observed_at"]
    replay = _round_record(resolved=True, fetched=datetime(2026, 8, 13, 1))
    assert not _run(loader, [replay]).errors
    assert db["yquant-data"][loader.collection].find_one({}) == doc


@pytest.mark.parametrize("dataset", [DATASET, "predict_btc5m_rounds"])
def test_ut11_revisions_have_zero_writes(db, monkeypatch, dataset):
    loader = HistoryBatchLoader(db["yquant-data"], dataset)
    original = (_record(0, fetched_at=datetime(2026, 8, 10))
                if dataset == DATASET else _round_record(resolved=True))
    assert not _run(loader, [original]).errors
    candidate = dict(original)
    candidate["close" if dataset == DATASET else "end_price"] = "999"
    collection = db["yquant-data"][loader.collection]
    before = collection.find_one({})
    monkeypatch.setattr(collection, "bulk_write", lambda *a, **k: pytest.fail("write"))
    assert _run(loader, [candidate]).errors
    assert collection.find_one({}) == before


def test_ut11_duplicate_conflict_precedes_any_write(loader, db, monkeypatch):
    first = _record(0, fetched_at=datetime(2026, 8, 10))
    conflict = dict(first, close="999")
    collection = db["yquant-data"][loader.collection]
    monkeypatch.setattr(collection, "bulk_write", lambda *a, **k: pytest.fail("write"))
    assert _run(loader, [first, conflict]).errors
    assert collection.count_documents({}) == 0


def test_ut12_missing_hash_is_not_cas_permission(db):
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    collection = db["yquant-data"][loader.collection]
    collection.insert_one(_round_record())
    assert _run(loader, [_round_record(resolved=True)]).errors
    assert collection.find_one({})["settlement_state"] == "pending"


def test_ut12_cas_uses_first_read_hash(db, monkeypatch):
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    assert not _run(loader, [_round_record()]).errors
    collection = db["yquant-data"][loader.collection]
    old_hash = collection.find_one({})["record_sha256"]
    bulk = collection.bulk_write

    def concurrent(operations, **kwargs):
        assert operations[0]._filter["record_sha256"] == old_hash
        assert operations[0]._upsert is False
        collection.update_one({}, {"$set": {"record_sha256": "b" * 64}})
        return bulk(operations, **kwargs)

    monkeypatch.setattr(collection, "bulk_write", concurrent)
    result = _run(loader, [_round_record(resolved=True)])
    assert result.errors and result.updated == 0
    assert collection.find_one({})["settlement_state"] == "pending"


def test_ut12_unknown_ack_is_failure(loader, db, monkeypatch):
    monkeypatch.setattr(db["yquant-data"][loader.collection], "bulk_write", lambda *a, **k: None)
    result = _run(loader, [_record(0, fetched_at=datetime(2026, 8, 10))])
    assert result.errors and result.inserted == result.updated == 0


def test_ut12_observation_readback_mismatch(loader, db, monkeypatch):
    collection = db["yquant-data"][loader.collection]
    bulk = collection.bulk_write

    def corrupt(operations, **kwargs):
        result = bulk(operations, **kwargs)
        collection.update_one({}, {"$set": {"first_observed_at": datetime(2030, 1, 1)}})
        return result

    monkeypatch.setattr(collection, "bulk_write", corrupt)
    result = _run(loader, [_record(0, fetched_at=datetime(2026, 8, 10))])
    assert any(error["reason"] == "READBACK_MISMATCH" for error in result.errors)
    assert result.inserted == 0


def test_ut11_conflict_across_bulk_boundary_precedes_write(loader, db, monkeypatch):
    monkeypatch.setattr(_loader, "MAX_BULK", 2)
    records = [_record(index * 1_000_000, fetched_at=datetime(2026, 8, 10)) for index in range(3)]
    records.append(dict(records[0], close="999"))
    assert _run(loader, records).errors
    assert db["yquant-data"][loader.collection].count_documents({}) == 0


def test_ut12_partial_bulk_failure_never_claims_success(loader, db, monkeypatch):
    from pymongo.errors import BulkWriteError

    collection = db["yquant-data"][loader.collection]
    bulk = collection.bulk_write

    def partial(operations, **kwargs):
        bulk(operations[:1], **kwargs)
        raise BulkWriteError({"writeErrors": [{"code": 11000}], "nInserted": 1})

    monkeypatch.setattr(collection, "bulk_write", partial)
    rows = [_record(index * 1_000_000, fetched_at=datetime(2026, 8, 10)) for index in range(2)]
    failed = _run(loader, rows)
    assert failed.errors and failed.inserted == failed.updated == failed.skipped == 0
    assert collection.count_documents({}) == 1
    monkeypatch.setattr(collection, "bulk_write", bulk)
    recovered = _run(loader, rows)
    assert not recovered.errors
    assert recovered.inserted == recovered.skipped == 1
    assert collection.count_documents({}) == 2


@pytest.mark.parametrize("field,value", [
    ("start_price", "999"), ("end_price", "999"),
    ("official_outcome", "DOWN"), ("resolved_at_us", 999),
    ("settlement_state", "pending"),
])
def test_ut11_all_resolved_fact_revisions_are_rejected(db, monkeypatch, field, value):
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    original = _round_record(resolved=True)
    assert not _run(loader, [original]).errors
    collection = db["yquant-data"][loader.collection]
    before = collection.find_one({})
    monkeypatch.setattr(collection, "bulk_write", lambda *a, **k: pytest.fail("write"))
    assert _run(loader, [dict(original, **{field: value})]).errors
    assert collection.find_one({}) == before


def test_ut11_first_start_price_fill_gets_new_observation(db):
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    original = dict(_round_record(), start_price=None, start_price_observed_at=None)
    assert not _run(loader, [original]).errors
    fetched = datetime(2026, 8, 12, 1, 0, 0, 1234)
    filled = _round_record(fetched=fetched)
    assert not _run(loader, [filled]).errors
    doc = db["yquant-data"][loader.collection].find_one({})
    assert doc["first_observed_at"] == original["first_observed_at"]
    assert doc["start_price_observed_at"] == fetched.replace(microsecond=2000)
    assert doc["label_observed_at"] is None


def test_ut11_lifecycle_changes_with_first_resolution_are_allowed(db):
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    pending = dict(_round_record(), category_status="OPEN", market_status="OPEN", trading_status="OPEN")
    final = dict(_round_record(resolved=True), category_status="RESOLVED", market_status="RESOLVED", trading_status="RESOLVED")
    assert not _run(loader, [pending]).errors
    assert not _run(loader, [final]).errors


def test_ut12_query_and_bulk_are_bounded_without_per_key_read(loader, db, monkeypatch):
    monkeypatch.setattr(_loader, "MAX_BULK", 2)
    collection = db["yquant-data"][loader.collection]
    find, bulk = collection.find, collection.bulk_write
    reads, writes = [], []

    def bounded_find(query, *args, **kwargs):
        reads.append(len(query["$or"]))
        assert len(query["$or"]) <= 2
        return find(query, *args, **kwargs)

    def bounded_bulk(operations, **kwargs):
        writes.append(len(operations))
        return bulk(operations, **kwargs)

    monkeypatch.setattr(collection, "find", bounded_find)
    monkeypatch.setattr(collection, "bulk_write", bounded_bulk)
    monkeypatch.setattr(collection, "find_one", lambda *a, **k: pytest.fail("per-key read"))
    monkeypatch.setattr(collection, "create_index", lambda *a, **k: pytest.fail("DDL"))
    rows = [_record(index * 1_000_000, fetched_at=datetime(2026, 8, 10)) for index in range(5)]
    assert not _run(loader, rows).errors
    assert writes == [2, 2, 1] and reads == [2, 2, 2, 2, 1, 1]


def test_ut12_namespace_cannot_fall_back(db, loader):
    with pytest.raises(ValueError, match="namespace"):
        HistoryBatchLoader(db["tradingagents"], DATASET)
    wrong_source = dict(_record(0, fetched_at=datetime(2026, 8, 10)), source="other")
    assert _run(loader, [wrong_source]).errors
    assert db["yquant-data"][loader.collection].count_documents({}) == 0


def test_ut12_missing_unique_key_invariant_is_failure(loader, db):
    collection = db["yquant-data"][loader.collection]
    record = _record(0, fetched_at=datetime(2026, 8, 10))
    assert not _run(loader, [record]).errors
    duplicate = collection.find_one({})
    duplicate.pop("_id")
    collection.insert_one(duplicate)
    assert _run(loader, [record]).errors
    assert not all(loader.readback([record]).values())


@pytest.mark.parametrize("precision", [6, 28, 50])
def test_fix2_decimal_comparison_is_exact_and_context_independent(db, precision):
    from decimal import Decimal, localcontext
    from bson import Decimal128
    from skills.data.unified_data.history_types import decimal_text

    left = Decimal("100.1234567890123456789012345678901")
    right = Decimal("100.1234567890123456789012345678902")
    with localcontext() as context:
        context.prec = precision
        assert decimal_text(left) == str(left)
        assert decimal_text(Decimal("-0.000")) == "0"
        assert decimal_text(Decimal("100.1000")) == "100.1"
        assert _loader._normalize(Decimal128("100.100")) == _loader._normalize(Decimal("100.1"))
        loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
        first = dict(_round_record(resolved=True), start_price=left)
        second = dict(first, start_price=right)
        assert _loader._record_hash(first, "predict_btc5m_rounds") != _loader._record_hash(second, "predict_btc5m_rounds")
        assert not _run(loader, [first]).errors
        before = db["yquant-data"][loader.collection].find_one({})
        assert _run(loader, [second]).errors
        assert db["yquant-data"][loader.collection].find_one({}) == before


@pytest.mark.parametrize("microseconds", [1234, 999500])
def test_fix2_production_clock_preserves_observation_before_ceil(db, monkeypatch, microseconds):
    from datetime import timezone
    from skills.data.unified_data.history_types import ceil_ms_to_us, from_us

    common = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.common")
    actual = datetime(2026, 11, 11, 4, 0, 0, microseconds)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return actual.replace(tzinfo=tz or timezone.utc)

    monkeypatch.setattr(common, "datetime", Clock)
    fetched = common.utc_now()
    assert fetched == actual
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    row = _round_record(resolved=True, fetched=fetched)
    assert not _run(loader, [row]).errors
    stored = db["yquant-data"][loader.collection].find_one({})
    for field in ("first_observed_at", "fetched_at", "start_price_observed_at", "label_observed_at"):
        assert stored[field] == from_us(ceil_ms_to_us(actual)) >= actual


def test_fix2_new_pending_has_due_time_without_manual_db_edit(db):
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    row = dict(_round_record(), next_check_at=None)
    assert not _run(loader, [row]).errors
    stored = db["yquant-data"][loader.collection].find_one({})
    assert stored["next_check_at"] == stored["first_observed_at"]


def _official_terminal_round():
    """Use public terminal excerpts; never claim a captured OPEN history.

    Source SHA constants identify the full archives, not the excerpt bytes.
    """
    import json
    from decimal import Decimal

    package = "skills.data.data-pipeline.scripts.btc5m_history"
    samples = importlib.import_module(package + ".tests.test_extractors")
    assert (samples.OFFICIAL_PAGE_SHA, samples.OFFICIAL_STATUS_SHA) == (
        "791a17406c0128d0712099563c7967df066140fccb1bb7c760405c7ff33ac245",
        "788cb2140d214bfaf106b1391b78b557ede11c10dca34808fb9c6e36960be666",
    )
    bodies = [json.loads(body, parse_float=Decimal) for body in (
        samples.OFFICIAL_EXCERPT, samples.OFFICIAL_STATUS_EXCERPT,
    )]
    extractors = importlib.import_module(package + ".extractors")
    transforms = importlib.import_module(package + ".transforms")
    envelope = extractors.normalize_round_envelope(bodies[0]["data"][0])
    envelope["_status_logs"] = {str(row["marketId"]): row["logs"] for row in bodies[1]["data"]}
    final = transforms.PredictRoundTransformer().transform_one(envelope)
    assert (final["category_status"], final["market_status"], final["trading_status"],
            final["settlement_state"]) == ("RESOLVED", "RESOLVED", "CLOSED", "resolved")
    return final


@pytest.mark.parametrize("changes", [
    {"category_status": "CLOSED"}, {"market_status": "CLOSED"},
    {"trading_status": "UNKNOWN"}, {"trading_status": "HALTED"},
    {"trading_status": "OPEN"}, {"category_status": "OPEN"},
    {"market_status": "OPEN"}, {"settlement_state": "pending"},
    {"start_price": "999"}, {"end_price": "999"},
    {"market_id": "wrong"}, {"condition_id": "wrong"},
    {"round_slug": "wrong"}, {"starts_at_us": 0},
])
def test_closed_status_invalid_fill_has_zero_writes(db, monkeypatch, changes):
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    final = _official_terminal_round()
    pending = dict(final, category_status="PENDING", market_status="PENDING",
                   trading_status="PENDING", settlement_state="pending",
                   official_outcome=None, resolved_at_us=None, resolution_evidence=None)
    assert not _run(loader, [pending]).errors
    collection = db["yquant-data"][loader.collection]
    before = collection.find_one({})
    monkeypatch.setattr(collection, "bulk_write", lambda *a, **k: pytest.fail("write"))
    rejected = _run(loader, [dict(final, **changes)])
    assert rejected.errors and rejected.updated == rejected.inserted == 0
    assert collection.find_one({}) == before


@pytest.mark.parametrize("state", ["pending", "unavailable", "conflict"])
@pytest.mark.parametrize("field,target", [
    ("trading_status", "CLOSED"), ("trading_status", "RESOLVED"),
    ("category_status", "RESOLVED"), ("market_status", "RESOLVED"),
])
def test_closed_status_nonresolved_status_change_rejected(db, monkeypatch, state, field, target):
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    pending = dict(_round_record(), category_status="OPEN", market_status="OPEN",
                   trading_status="OPEN")
    assert not _run(loader, [pending]).errors
    collection = db["yquant-data"][loader.collection]
    before = collection.find_one({})
    monkeypatch.setattr(collection, "bulk_write", lambda *a, **k: pytest.fail("write"))
    assert _run(loader, [dict(pending, settlement_state=state, **{field: target})]).errors
    assert collection.find_one({}) == before


@pytest.mark.parametrize("field,value", [
    ("trading_status", "OPEN"), ("trading_status", "RESOLVED"),
    ("category_status", "OPEN"), ("market_status", "OPEN"),
    ("settlement_state", "pending"), ("start_price", "999"), ("end_price", "999"),
    ("official_outcome", "DOWN"), ("resolved_at_us", 0),
    ("resolution_evidence", {"resolution_name": "wrong"}),
    ("market_id", "wrong"), ("condition_id", "wrong"),
])
def test_closed_status_accepted_terminal_cannot_be_overwritten(db, monkeypatch, field, value):
    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    final = _official_terminal_round()
    assert not _run(loader, [final]).errors
    collection = db["yquant-data"][loader.collection]
    before = collection.find_one({})
    monkeypatch.setattr(collection, "bulk_write", lambda *a, **k: pytest.fail("write"))
    rejected = _run(loader, [dict(final, **{field: value})])
    assert rejected.errors and rejected.updated == rejected.inserted == 0
    assert collection.find_one({}) == before


def _flat_candidate(index=0):
    """Public five-market excerpts with explicitly synthetic final status logs."""
    samples = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.tests.test_transforms")
    transforms = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.transforms")
    result = transforms.PredictRoundTransformer().transform_one(samples._official_flat_excerpt(index))
    assert (result["settlement_state"], result["official_outcome"]) == ("resolved", "DRAW")
    return result


@pytest.mark.parametrize("index", range(5))
def test_official_flat_conflict_correction_cas_history_and_restart(db, monkeypatch, index):
    import copy

    dataset = "predict_btc5m_rounds"
    loader = HistoryBatchLoader(db["yquant-data"], dataset)
    candidate = _flat_candidate(index)
    old_time, new_time = datetime(2026, 11, 11, 12), datetime(2026, 11, 11, 13)
    previous = dict(candidate, settlement_state="conflict", official_outcome=None,
                    resolution_evidence=None, resolved_at_us=None, fetched_at=old_time,
                    raw_ref="synthetic-old-page", raw_sha256="a" * 64)
    assert not _run(loader, [previous]).errors
    collection = db["yquant-data"][loader.collection]
    before = collection.find_one({})
    bulk = collection.bulk_write
    cas_filters = []

    def observe_cas(operations, **kwargs):
        cas_filters.extend(copy.deepcopy(operation._filter) for operation in operations)
        return bulk(operations, **kwargs)

    monkeypatch.setattr(collection, "bulk_write", observe_cas)
    candidate.update(fetched_at=new_time, raw_ref="synthetic-new-page", raw_sha256="b" * 64,
                     label_observed_at=old_time)  # Never backdate the newly accepted label.
    result = _run(loader, [candidate])
    assert not result.errors and result.updated == 1 and result.inserted == 0
    corrected = collection.find_one({})
    assert cas_filters == [dict(loader.natural_key(candidate), record_sha256=before["record_sha256"])]
    assert corrected["previous_record_sha256"] == before["record_sha256"]
    assert corrected["raw_history"][-1] == {
        "raw_ref": before["raw_ref"], "raw_sha256": before["raw_sha256"],
        "record_sha256": before["record_sha256"],
    }
    for field in ("first_observed_at", "fetched_at", "start_price_observed_at"):
        assert corrected[field] == before[field]
    assert before["label_observed_at"] is None
    assert corrected["label_observed_at"] == new_time
    assert corrected["updated_at"] == new_time
    assert corrected["official_outcome"] == "DRAW"
    assert corrected["start_price"] == before["start_price"]
    assert corrected["end_price"] == before["end_price"]
    restart = HistoryBatchLoader(db["yquant-data"], dataset)
    replay = _run(restart, [dict(candidate, fetched_at=datetime(2026, 11, 12))])
    assert not replay.errors and replay.skipped == 1 and replay.updated == 0
    assert collection.find_one({}) == corrected


@pytest.mark.parametrize("fault", [
    "old_up", "old_evidence", "old_resolved", "direction", "no_evidence", "bad_rule",
    "unequal", "price_changed", "market", "condition", "event_time", "published_time",
    "no_transition", "wrong_transition", "wrong_rule_source", "wrong_market_proof",
])
def test_official_flat_correction_rejects_unauthorized_changes(db, monkeypatch, fault):
    import copy
    from decimal import Decimal

    loader = HistoryBatchLoader(db["yquant-data"], "predict_btc5m_rounds")
    candidate = _flat_candidate()
    previous = dict(candidate, settlement_state="conflict", official_outcome=None,
                    resolution_evidence=None, resolved_at_us=None)
    if fault == "old_up":
        previous["official_outcome"] = "UP"
    elif fault == "old_evidence":
        previous["resolution_evidence"] = {"accepted": "contradictory"}
    elif fault == "old_resolved":
        previous = dict(candidate)
    assert not _run(loader, [previous]).errors
    collection = db["yquant-data"][loader.collection]
    before = copy.deepcopy(collection.find_one({}))
    if fault in ("old_resolved", "direction"):
        candidate["official_outcome"] = "UP"
    elif fault == "no_evidence":
        candidate["resolution_evidence"] = None
    elif fault == "bad_rule":
        candidate["resolution_evidence"]["rule_text"] = "50-50"
    elif fault == "unequal":
        candidate["end_price"] += Decimal("0.001")
    elif fault == "price_changed":
        candidate["start_price"] = candidate["end_price"] = Decimal("1")
    elif fault in ("market", "condition", "event_time", "published_time"):
        field = {"market": "market_id", "condition": "condition_id", "event_time": "ends_at_us",
                 "published_time": "published_at_us"}[fault]
        candidate[field] = "wrong" if fault in ("market", "condition") else 0
    elif fault == "no_transition":
        candidate["resolution_evidence"].pop("final_transition")
    elif fault == "wrong_transition":
        candidate["resolved_at_us"] += 1
    elif fault == "wrong_rule_source":
        candidate["resolution_evidence"]["rule_source"] = "external message"
    elif fault == "wrong_market_proof":
        candidate["resolution_evidence"]["market_id"] = "other"
    monkeypatch.setattr(collection, "bulk_write", lambda *args, **kwargs: pytest.fail("unexpected write"))
    rejected = _run(loader, [candidate])
    assert rejected.errors and rejected.updated == rejected.inserted == 0
    assert collection.find_one({}) == before

