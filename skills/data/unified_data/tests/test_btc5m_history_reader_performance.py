"""Reader request-local reuse and unchanged mutation/provenance contracts."""
from dataclasses import asdict
from datetime import timedelta
from unittest.mock import patch

import mongomock
import pytest
from bson import BSON, Decimal128
from bson.codec_options import CodecOptions
from bson.raw_bson import RawBSONDocument

from skills.data.unified_data import history_reader as module
from skills.data.unified_data.history_types import HistoryError, ceil_ms_to_us
from skills.data.unified_data.tests.test_btc5m_history_reader import (
    DAY0, SECOND, _aware, _kline, _round, _shard, _window,
)


class RawCursor:
    """Keep mongomock keyset behavior, but return actual lazy BSON documents."""

    def __init__(self, cursor):
        self.cursor = cursor

    def sort(self, order):
        self.cursor.sort(order)
        return self

    def limit(self, count):
        self.cursor.limit(count)
        return self

    def batch_size(self, count):
        self.cursor.batch_size(count)
        return self

    def __iter__(self):
        return (RawBSONDocument(BSON.encode(doc)) for doc in self.cursor)


class RawCollection:
    """Exercise PyMongo's codec selection without opening a connection."""

    def __init__(self, collection, *, raw=False):
        self.collection = collection
        self.raw = raw
        self.codec_options = CodecOptions()

    def with_options(self, *, codec_options):
        assert codec_options.document_class is RawBSONDocument
        return RawCollection(self.collection, raw=True)

    def find(self, *args, **kwargs):
        cursor = self.collection.find(*args, **kwargs)
        return RawCursor(cursor) if self.raw else cursor

    def __getattr__(self, name):
        return getattr(self.collection, name)


class RawDatabase:
    """Only business collections use the real BSON codec; ledger reads stay ordinary."""

    def __init__(self, database):
        self.database = database

    def __getitem__(self, name):
        collection = self.database[name]
        return collection if name == module.INGESTION_COLLECTION else RawCollection(collection)


@pytest.fixture(params=[False, True], ids=["mapping", "raw-bson"])
def target(monkeypatch, request):
    monkeypatch.setattr(module, "MAX_BATCH", 2)
    database = mongomock.MongoClient()["yquant-data"]
    if request.param:
        monkeypatch.setattr(module, "Collection", RawCollection)
        database = RawDatabase(database)
    base = ceil_ms_to_us(DAY0)
    database[module.KLINES_COLLECTION].insert_many([
        _kline(base + index * SECOND, observed=DAY0) for index in range(5)
    ])
    database[module.ROUNDS_COLLECTION].insert_one(_round(
        "r1", base, observed=DAY0, state="resolved", outcome="UP",
        resolved_at_us=base + 301 * SECOND, label_observed=DAY0,
    ))
    _shard(database)
    return database


def consume(window):
    return [list(window.iter_features()), list(window.iter_round_metadata()), list(window.iter_labels())]


def test_one_manifest_scan_and_no_repeated_business_projection(target):
    with patch.object(module.Btc5mHistoryReader, "_scan", autospec=True,
                      side_effect=module.Btc5mHistoryReader._scan) as scans, \
            patch.object(module, "_business", wraps=module._business) as business:
        window = _window(target, 5)
        consume(window)
        window.verify_consumed()
        assert scans.call_count == 1
        assert business.call_count == 6


def test_metadata_labels_do_not_construct_discarded_candle_features(target):
    window = _window(target, 5)
    original = module.FeatureRow
    with patch.object(module, "FeatureRow", wraps=original) as features:
        list(window.iter_round_metadata())
        list(window.iter_labels())
        assert features.call_count == 0


@pytest.mark.parametrize("change", [
    {"close": Decimal128("100.000000000000000000000000000001")},
    {"first_observed_at": DAY0 + timedelta(days=2)},
    {"close_exclusive_us": ceil_ms_to_us(DAY0) + 2 * SECOND},
    {"source_row": 999},
])
@pytest.mark.parametrize("phase", ["before_stream", "visited_page", "after_streams"])
def test_actual_content_change_in_every_phase(target, change, phase):
    window = _window(target, 5)
    if phase == "visited_page":
        iterator = window.iter_features()
        # Round feature, then first candle from the first page.
        next(iterator)
        next(iterator)
    elif phase == "after_streams":
        consume(window)
    target[module.KLINES_COLLECTION].update_one(
        {"open_time_us": ceil_ms_to_us(DAY0)}, {"$set": change},
    )
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        if phase == "visited_page":
            list(iterator)
        elif phase == "after_streams":
            window.verify_consumed()
        else:
            list(window.iter_features())


@pytest.mark.parametrize("operation", ["insert", "delete", "label", "schema", "shard"])
def test_changes_after_all_streams_are_not_hidden(target, operation):
    window = _window(target, 6)
    consume(window)
    if operation == "insert":
        target[module.KLINES_COLLECTION].insert_one(_kline(
            ceil_ms_to_us(DAY0) + 5 * SECOND, observed=DAY0,
        ))
    elif operation == "delete":
        target[module.KLINES_COLLECTION].delete_one({"open_time_us": ceil_ms_to_us(DAY0)})
    elif operation == "label":
        target[module.ROUNDS_COLLECTION].update_one({}, {"$set": {"official_outcome": "DOWN"}})
    elif operation == "schema":
        target[module.KLINES_COLLECTION].update_one({}, {"$set": {"schema_version": 9}})
    else:
        target[module.INGESTION_COLLECTION].update_one({}, {"$set": {"counts.resolved": 2}})
    with pytest.raises(HistoryError, match="UNKNOWN_SCHEMA_VERSION" if operation == "schema" else "DATASET_CHANGED"):
        window.verify_consumed()


def test_raw_only_changes_fall_back_to_business_projection(target):
    window = _window(target, 5)
    original_provenance = window.provenance_manifest
    target[module.KLINES_COLLECTION].update_one({}, {"$set": {
        "raw_ref": "new.json", "raw_sha256": "b" * 64,
    }})
    target[module.ROUNDS_COLLECTION].update_one({}, {"$set": {
        "resolution_evidence.raw_ref": "nested-new.json",
        "resolution_evidence.raw_sha256": "c" * 64,
    }})
    target[module.INGESTION_COLLECTION].update_one({}, {"$set": {"raw_manifest_ref": "new.json"}})
    first = consume(window)
    window.verify_consumed()
    fresh = _window(target, 5)
    assert consume(fresh) == first
    fresh.verify_consumed()
    assert fresh.content_manifest == window.content_manifest
    assert window.provenance_manifest == original_provenance
    assert fresh.provenance_manifest != original_provenance


def test_repeated_iteration_and_interleaved_requests_are_isolated(target):
    reader = module.Btc5mHistoryReader(target)
    args = (_aware(DAY0), _aware(DAY0 + timedelta(seconds=5)))
    before = reader.read(*args, as_of_utc=_aware(DAY0 + timedelta(days=1)))
    first = consume(before)
    assert consume(before) == first
    before.verify_consumed()
    target[module.KLINES_COLLECTION].update_one({}, {"$set": {"close": Decimal128("99")}})
    after = reader.read(*args, as_of_utc=_aware(DAY0 + timedelta(days=1)))
    consume(after)
    after.verify_consumed()
    assert before.content_sha256 != after.content_sha256
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        before.verify_consumed()
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        list(before.iter_features())


def test_decimal_conversion_reuses_only_exact_page_local_values(target):
    target[module.ROUNDS_COLLECTION].delete_many({})
    original = Decimal128.to_decimal
    with patch.object(Decimal128, "to_decimal", autospec=True, side_effect=original) as conversions:
        window = _window(target, 5)
        values = consume(window)
        window.verify_consumed()
        # Three pages: eight business decimals and five output decimals per page.
        assert conversions.call_count == 39
        assert len(values[0]) == 5
        assert all(row.close == original(Decimal128("101.0")) for row in values[0])


def test_verify_unchanged_raw_pages_does_not_reinflate_business_rows(target):
    if not isinstance(target, RawDatabase):
        return
    window = _window(target, 5)
    consume(window)
    with patch.object(RawCollection, "with_options", autospec=True,
                      side_effect=RawCollection.with_options) as codecs, \
            patch.object(module, "_business", wraps=module._business) as business, \
            patch.object(RawBSONDocument, "__getitem__", autospec=True,
                         side_effect=RawBSONDocument.__getitem__) as accesses:
        window.verify_consumed()
        assert codecs.call_count == 2
        assert business.call_count == 0
        # One round page has two ordering keys; three candle pages have one each.
        assert accesses.call_count == 5


def test_short_ledger_page_does_not_query_empty_tail(target, monkeypatch):
    monkeypatch.setattr(module, "MAX_BATCH", 3)
    reader = module.Btc5mHistoryReader(target)
    request = _window(target, 5).request
    collection = target[module.INGESTION_COLLECTION]
    with patch.object(collection, "find", wraps=collection.find) as finds:
        states = reader._states(request)
    assert len(states) == 1
    assert finds.call_count == 1


def test_short_ledger_page_still_detects_boundary_insert(target, monkeypatch):
    monkeypatch.setattr(module, "MAX_BATCH", 3)
    window = _window(target, 5)
    consume(window)
    collection = target[module.INGESTION_COLLECTION]
    document = collection.find_one({})
    document["_id"] = "zz-boundary-ledger"
    collection.insert_one(document)
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        window.verify_consumed()


def test_available_time_and_decimal_are_preserved(target):
    window = _window(target, 5)
    rows = consume(window)
    assert rows[0][1].close == Decimal128("101.0").to_decimal()
    assert rows[0][1].available_at_us == ceil_ms_to_us(DAY0) + SECOND
    assert not {"official_outcome", "end_price"} & asdict(rows[0][0]).keys()
    window.verify_consumed()
