"""Synthetic BSON records exercise real facade/reader/thin input boundaries."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib

from bson import Decimal128
import mongomock
import pytest

from skills.data.unified_data.client import UnifiedDataClient
from skills.data.unified_data.history_reader import Btc5mHistoryReader
from skills.data.unified_data.history_types import HistoryError, HistoryRequest, to_us

adapter = importlib.import_module(
    "skills.strategies.strategy-lab.strategies.predict-btc5m-btc-arb.history_input"
)
START = datetime(2026, 8, 10)


def seeded_client():
    """Return synthetic database and the production reader/facade composition."""
    db = mongomock.MongoClient()["yquant-data"]
    base = to_us(START)
    db["03_data_ud_binance_spot_klines_1s"].insert_one({
        "schema_version": 1, "source": "binance-vision", "market_type": "spot",
        "symbol": "BTCUSDT", "interval": "1s", "open_time_us": base,
        "open": Decimal128("100"), "high": Decimal128("102"),
        "low": Decimal128("99"), "close": Decimal128("101"),
        "volume": Decimal128("1"), "close_time_us": base + 999999,
        "close_exclusive_us": base + 1000000, "first_observed_at": START,
    })
    db["03_data_ud_predict_btc5m_rounds"].insert_one({
        "schema_version": 1, "source": "predict.fun", "series_slug": "btc-updown-5m",
        "round_id": "123", "round_slug": "synthetic-123", "market_id": "456",
        "condition_id": "synthetic-condition", "published_at_us": base - 1000000,
        "starts_at_us": base, "ends_at_us": base + 300000000,
        "start_price": Decimal128("100.25"), "end_price": Decimal128("101.25"),
        "price_feed_provider": "CHAINLINK", "price_feed_symbol": "BTCUSDT",
        "first_observed_at": START, "start_price_observed_at": START,
        "label_observed_at": START + timedelta(minutes=6),
        "settlement_state": "resolved", "official_outcome": "UP",
        "resolved_at_us": base + 360000000,
        "resolution_evidence": {"resolution_name": "UP"},
    })
    return db, UnifiedDataClient(history_reader=Btc5mHistoryReader(db))


def request(as_of_minutes=10):
    """Build an explicit UTC synthetic window request."""
    return HistoryRequest(
        start_utc=START.replace(tzinfo=timezone.utc),
        end_utc=(START + timedelta(minutes=5)).replace(tzinfo=timezone.utc),
        as_of_utc=(START + timedelta(minutes=as_of_minutes)).replace(tzinfo=timezone.utc),
    )


def test_ut16_real_facade_preserves_decimal_and_separates_labels():
    _, client = seeded_client()
    bundle = adapter.iter_history_input(client, request())
    assert not bundle.verified
    with pytest.raises(HistoryError, match="INCOMPLETE_CONSUMPTION"):
        bundle.verify_consumed()
    features = list(bundle.iter_features())
    metadata = list(bundle.iter_metadata())
    labels = list(bundle.iter_labels())
    assert bundle.verify_consumed()
    assert labels[0].payload["official_outcome"] == "UP"
    assert all("official_outcome" not in row.payload for row in features)
    candle = next(row for row in features if row.source == "binance-vision")
    assert isinstance(candle.payload["close"], Decimal)
    assert {row.source for row in features} == {"binance-vision", "predict.fun"}
    assert metadata[0].payload["market_id"] == "456"


def test_ut19_as_of_hides_future_label_and_repeat_is_stable():
    _, client = seeded_client()
    before = adapter.iter_history_input(client, request(as_of_minutes=1))
    assert list(before.labels) == []
    first = adapter.iter_history_input(client, request())
    second = adapter.iter_history_input(client, request())
    assert first.content_sha256 == second.content_sha256
    assert first.numeric_conversion is None


def test_ut19_consumption_failure_propagates_without_a_bundle(monkeypatch):
    _, client = seeded_client()

    def changed(self):
        raise HistoryError("DATASET_CHANGED", "synthetic concurrent change")

    from skills.data.unified_data.history_types import HistoryWindow
    monkeypatch.setattr(HistoryWindow, "verify_consumed", changed)
    bundle = adapter.iter_history_input(client, request())
    list(bundle.iter_features())
    list(bundle.iter_metadata())
    list(bundle.iter_labels())
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        bundle.verify_consumed()
    assert not bundle.verified


def test_ut19_lazy_two_page_consumption_and_mutation(monkeypatch):
    reader_module = importlib.import_module("skills.data.unified_data.history_reader")
    monkeypatch.setattr(reader_module, "MAX_BATCH", 1)
    db, client = seeded_client()
    collection = db["03_data_ud_binance_spot_klines_1s"]
    second = collection.find_one({}, {"_id": 0})
    second["open_time_us"] += 1000000
    second["close_time_us"] += 1000000
    second["close_exclusive_us"] += 1000000
    collection.insert_one(second)
    bundle = adapter.iter_history_input(client, request())
    assert bundle._completed == set()
    assert not isinstance(bundle.features, list)
    first = next(bundle.iter_features())
    assert first.source in {"predict.fun", "binance-vision"}
    assert bundle._completed == set()
    collection.update_one({"open_time_us": second["open_time_us"]},
                          {"$set": {"close": Decimal128("103")}})
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        list(bundle.iter_features())
    assert not bundle.verified


def test_ut16_scheduled_stream_is_sorted_and_labels_are_independent():
    _, client = seeded_client()
    bundle = adapter.iter_history_input(client, request())
    schedule = bundle.iter_scheduled()
    first = next(schedule)
    assert first.kind != "official_outcome"
    list(bundle.iter_labels())
    with pytest.raises(HistoryError, match="INCOMPLETE_CONSUMPTION"):
        bundle.verify_consumed()
    events = [first, *schedule]
    assert [row.available_at_us for row in events] == sorted(
        row.available_at_us for row in events
    )
    assert any(row.kind == "round_identity" for row in events)
    assert all("official_outcome" not in row.payload for row in events)
    assert bundle.verify_consumed()


def test_ut19_final_verification_detects_change_after_all_yields():
    db, client = seeded_client()
    bundle = adapter.iter_history_input(client, request())
    list(bundle.iter_scheduled())
    list(bundle.iter_labels())
    db["03_data_ud_predict_btc5m_rounds"].update_one(
        {"round_id": "123"}, {"$set": {"end_price": Decimal128("999")}}
    )
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        bundle.verify_consumed()
    assert not bundle.verified
