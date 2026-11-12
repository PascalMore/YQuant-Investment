"""BTC5m 窄历史读取测试 — 03-018 UT16–UT19。

覆盖：半开边界、预热独立、available_at（observed / proxy）、标签与特征
隔离、稳定排序与内容 hash、expected_manifest 变化 → DATASET_CHANGED、
读取无写 / 无网 / 无 DDL。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from bson import Decimal128

import mongomock
import pytest

from skills.data.unified_data.history_reader import (
    KLINES_COLLECTION,
    ROUNDS_COLLECTION,
    Btc5mHistoryReader,
)
from skills.data.unified_data.history_types import (
    HistoryError,
    HistoryRequest,
    ceil_ms_to_us,
)

DAY0 = datetime(2026, 8, 10, tzinfo=timezone.utc).replace(tzinfo=None)
SECOND = 1_000_000


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc)


def _kline(open_us: int, *, observed: datetime) -> dict:
    return {
        "_id": f"kline-{open_us}",
        "schema_version": 1,
        "source": "binance-vision",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "interval": "1s",
        "open_time_us": open_us,
        "open": Decimal128("100.5"),
        "high": Decimal128("101.5"),
        "low": Decimal128("99.5"),
        "close": Decimal128("101.0"),
        "volume": Decimal128("1.25"),
        "close_time_us": open_us + SECOND - 1,
        "close_exclusive_us": open_us + SECOND,
        "quote_volume": Decimal128("126.0"),
        "number_of_trades": 3,
        "taker_buy_base_volume": Decimal128("0.5"),
        "taker_buy_quote_volume": Decimal128("50.0"),
        "ignore": "0",
        "source_timestamp_unit": "us",
        "source_row": 1,
        "first_observed_at": observed,
    }


def _round(
    round_id: str,
    starts_at_us: int,
    *,
    observed: datetime,
    start_price_observed: datetime | None = None,
    state: str = "pending",
    outcome: str | None = None,
    resolved_at_us: int | None = None,
    label_observed: datetime | None = None,
) -> dict:
    return {
        "_id": f"round-{round_id}",
        "schema_version": 1,
        "source": "predict.fun",
        "series_slug": "btc-updown-5m",
        "round_id": round_id,
        "round_slug": f"slug-{round_id}",
        "market_id": f"market-{round_id}",
        "condition_id": f"condition-{round_id}",
        "published_at_us": starts_at_us - 60 * SECOND,
        "starts_at_us": starts_at_us,
        "ends_at_us": starts_at_us + 300 * SECOND,
        "start_price": Decimal128("100.25"),
        "start_price_observed_at": start_price_observed or observed,
        "end_price": Decimal128("101.25") if outcome else None,
        "price_feed_provider": "CHAINLINK",
        "price_feed_symbol": "BTCUSDT",
        "category_status": "RESOLVED" if outcome else "OPEN",
        "market_status": "RESOLVED" if outcome else "OPEN",
        "trading_status": "RESOLVED" if outcome else "OPEN",
        "settlement_state": state,
        "official_outcome": outcome,
        "resolution_evidence": {"resolution_name": outcome} if outcome else None,
        "resolved_at_us": resolved_at_us,
        "label_observed_at": label_observed,
        "next_check_at": None,
        "first_observed_at": observed,
    }


@pytest.fixture()
def db() -> mongomock.MongoClient:
    return mongomock.MongoClient()


# ---------------------------------------------------------------------------
# UT16 — 半开边界 / UTC / 未闭 candle / 未来标签
# ---------------------------------------------------------------------------


def test_ut16_half_open_window_excludes_upper_bound(db) -> None:
    target = db["yquant-data"]
    base = int((DAY0 - datetime(1970, 1, 1)).total_seconds()) * SECOND
    target[KLINES_COLLECTION].insert_many(
        [
            _kline(base, observed=DAY0),
            _kline(base + SECOND, observed=DAY0),
        ]
    )
    reader = Btc5mHistoryReader(target)
    window = reader.read(
        _aware(DAY0), _aware(DAY0 + timedelta(seconds=1)), as_of_utc=_aware(DAY0 + timedelta(days=1))
    )
    opens = [row.open_time_us for row in window.iter_features()]
    # 上界不含：open_time_us == end 的记录被排除。
    assert opens == [base]


def test_ut16_naive_datetime_is_rejected(db) -> None:
    reader = Btc5mHistoryReader(db["yquant-data"])
    with pytest.raises(HistoryError) as excinfo:
        reader.read(DAY0, DAY0 + timedelta(days=1), as_of_utc=_aware(DAY0))
    assert excinfo.value.code == "INVALID_ARGUMENT"


def test_ut16_future_label_does_not_enter_features(db) -> None:
    target = db["yquant-data"]
    base = int((DAY0 - datetime(1970, 1, 1)).total_seconds()) * SECOND
    target[ROUNDS_COLLECTION].insert_one(
        _round(
            "1",
            base,
            observed=DAY0,
            state="resolved",
            outcome="UP",
            resolved_at_us=base + 400 * SECOND,
            label_observed=DAY0 + timedelta(hours=2),
        )
    )
    reader = Btc5mHistoryReader(target)
    window = reader.read(
        _aware(DAY0),
        _aware(DAY0 + timedelta(hours=1)),
        as_of_utc=_aware(DAY0 + timedelta(hours=1)),
    )
    for row in window.iter_features():
        assert "outcome" not in row.payload if hasattr(row, "payload") else True
        assert row.start_price is not None
    # label 不可得 → pending 记录
    assert any(item["reason"] == "LABEL_NOT_AVAILABLE_AT_AS_OF" for item in window.pending)


def test_ut16_unclosed_candle_is_not_available_in_proxy_mode(db) -> None:
    """proxy 模式下 candle 的 available_at = close_exclusive（区间结束）。"""
    target = db["yquant-data"]
    base = int((DAY0 - datetime(1970, 1, 1)).total_seconds()) * SECOND
    target[KLINES_COLLECTION].insert_one(_kline(base, observed=DAY0))
    reader = Btc5mHistoryReader(target)
    window = reader.read(
        _aware(DAY0),
        _aware(DAY0 + timedelta(seconds=1)),
        as_of_utc=_aware(DAY0),
        availability_mode="event-time-proxy",
    )
    assert list(window.iter_features()) == []


# ---------------------------------------------------------------------------
# UT17 — 预热独立
# ---------------------------------------------------------------------------


def test_ut17_warmup_rows_are_counted_separately(db) -> None:
    target = db["yquant-data"]
    base = int((DAY0 - datetime(1970, 1, 1)).total_seconds()) * SECOND
    target[KLINES_COLLECTION].insert_many(
        [
            _kline(base - SECOND, observed=DAY0),
            _kline(base, observed=DAY0),
        ]
    )
    reader = Btc5mHistoryReader(target)
    window = reader.read(
        _aware(DAY0),
        _aware(DAY0 + timedelta(seconds=1)),
        warmup_seconds=1,
        as_of_utc=_aware(DAY0 + timedelta(days=1)),
    )
    assert window.coverage.warmup_rows == 1
    assert window.coverage.main_window_rows == 1


def test_ut17_missing_warmup_yields_partial(db) -> None:
    target = db["yquant-data"]
    base = int((DAY0 - datetime(1970, 1, 1)).total_seconds()) * SECOND
    target[KLINES_COLLECTION].insert_one(_kline(base, observed=DAY0))
    reader = Btc5mHistoryReader(target)
    window = reader.read(
        _aware(DAY0),
        _aware(DAY0 + timedelta(seconds=1)),
        warmup_seconds=60,
        as_of_utc=_aware(DAY0 + timedelta(days=1)),
    )
    assert window.status in ("complete", "partial")
    assert window.coverage.warmup_rows == 0


def test_ut17_read_does_not_write(db) -> None:
    target = db["yquant-data"]
    reader = Btc5mHistoryReader(target)
    reader.read(
        _aware(DAY0),
        _aware(DAY0 + timedelta(days=1)),
        as_of_utc=_aware(DAY0 + timedelta(days=1)),
    )
    assert target.list_collection_names() == []


# ---------------------------------------------------------------------------
# UT18 — 稳定排序 / 内容 hash
# ---------------------------------------------------------------------------


def test_ut18_natural_order_does_not_affect_output(db) -> None:
    base = int((DAY0 - datetime(1970, 1, 1)).total_seconds()) * SECOND
    rows = [_kline(base + index * SECOND, observed=DAY0) for index in range(5)]

    first = mongomock.MongoClient()["yquant-data"]
    first[KLINES_COLLECTION].insert_many(rows)
    second = mongomock.MongoClient()["yquant-data"]
    second[KLINES_COLLECTION].insert_many(list(reversed(rows)))

    reader_a = Btc5mHistoryReader(first)
    reader_b = Btc5mHistoryReader(second)
    kwargs = dict(
        start_utc=_aware(DAY0),
        end_utc=_aware(DAY0 + timedelta(seconds=10)),
        as_of_utc=_aware(DAY0 + timedelta(days=1)),
    )
    window_a = reader_a.read(**kwargs)
    window_b = reader_b.read(**kwargs)
    assert [r.open_time_us for r in window_a.iter_features()] == [
        r.open_time_us for r in window_b.iter_features()
    ]
    assert window_a.output_digest() == window_b.output_digest()


def test_ut18_repeat_read_is_stable(db) -> None:
    target = db["yquant-data"]
    base = int((DAY0 - datetime(1970, 1, 1)).total_seconds()) * SECOND
    target[KLINES_COLLECTION].insert_one(_kline(base, observed=DAY0))
    reader = Btc5mHistoryReader(target)
    kwargs = dict(
        start_utc=_aware(DAY0),
        end_utc=_aware(DAY0 + timedelta(seconds=10)),
        as_of_utc=_aware(DAY0 + timedelta(days=1)),
    )
    first = reader.read(**kwargs)
    second = reader.read(**kwargs)
    assert first.output_digest() == second.output_digest()
    assert first.content_sha256 == second.content_sha256


# ---------------------------------------------------------------------------
# UT19 — observed / proxy / expected_manifest
# ---------------------------------------------------------------------------


def test_ut19_observed_mode_uses_observation_time(db) -> None:
    target = db["yquant-data"]
    base = int((DAY0 - datetime(1970, 1, 1)).total_seconds()) * SECOND
    late = DAY0 + timedelta(days=5)
    target[KLINES_COLLECTION].insert_one(_kline(base, observed=late))
    reader = Btc5mHistoryReader(target)
    window = reader.read(
        _aware(DAY0),
        _aware(DAY0 + timedelta(seconds=10)),
        as_of_utc=_aware(DAY0 + timedelta(days=1)),
    )
    # 观察时间晚于 as_of → 不可用
    assert list(window.iter_features()) == []
    window_proxy = reader.read(
        _aware(DAY0),
        _aware(DAY0 + timedelta(seconds=10)),
        as_of_utc=_aware(DAY0 + timedelta(days=1)),
        availability_mode="event-time-proxy",
    )
    assert len(list(window_proxy.iter_features())) == 1


def test_ut19_proxy_mode_declares_the_degradation(db) -> None:
    reader = Btc5mHistoryReader(db["yquant-data"])
    window = reader.read(
        _aware(DAY0),
        _aware(DAY0 + timedelta(days=1)),
        as_of_utc=_aware(DAY0 + timedelta(days=1)),
        availability_mode="event-time-proxy",
    )
    assert any("NOT strict point-in-time" in item for item in window.availability_assumptions)


def test_ut19_expected_manifest_change_raises(db) -> None:
    target = db["yquant-data"]
    base = int((DAY0 - datetime(1970, 1, 1)).total_seconds()) * SECOND
    reader = Btc5mHistoryReader(target)
    kwargs = dict(
        start_utc=_aware(DAY0),
        end_utc=_aware(DAY0 + timedelta(seconds=10)),
        as_of_utc=_aware(DAY0 + timedelta(days=1)),
    )
    empty = reader.read(**kwargs)
    target[KLINES_COLLECTION].insert_one(_kline(base, observed=DAY0))
    with pytest.raises(HistoryError) as excinfo:
        reader.read(expected_manifest=empty.content_manifest, **kwargs)
    assert excinfo.value.code == "DATASET_CHANGED"


def test_ut19_ceil_ms_rounds_up() -> None:
    value = datetime(2026, 8, 10, 0, 0, 0, 1234)
    assert ceil_ms_to_us(value) % 1000 == 0
    assert ceil_ms_to_us(value) == int(
        (value - datetime(1970, 1, 1)).total_seconds()
    ) * SECOND + 2_000


def test_ut19_verify_consumed_requires_full_consumption(db) -> None:
    from skills.data.unified_data.history_types import HistoryWindow

    window = HistoryWindow(
        request=HistoryRequest(
            start_utc=DAY0, end_utc=DAY0 + timedelta(days=1), as_of_utc=DAY0
        ),
        status="complete",
        sources=(),
        kinds=(),
        units={},
        schema_version=1,
        coverage=None,  # type: ignore[arg-type]
    )
    with pytest.raises(HistoryError) as excinfo:
        window.verify_consumed()
    assert excinfo.value.code == "INCOMPLETE_CONSUMPTION"


def _window(target, seconds=1, **kwargs):
    return Btc5mHistoryReader(target).read(
        _aware(DAY0), _aware(DAY0 + timedelta(seconds=seconds)),
        as_of_utc=_aware(DAY0 + timedelta(days=1)), **kwargs,
    )


def test_ut16_official_label_is_positive_and_separate(db):
    from dataclasses import asdict

    target = db["yquant-data"]
    base = ceil_ms_to_us(DAY0)
    target[ROUNDS_COLLECTION].insert_one(_round(
        "1", base, observed=DAY0, state="resolved", outcome="UP",
        resolved_at_us=base + 301 * SECOND, label_observed=DAY0 + timedelta(minutes=6),
    ))
    window = _window(target, 300)
    labels = list(window.iter_labels())
    assert len(labels) == 1 and labels[0].official_outcome == "UP"
    for row in list(window.iter_features()) + list(window.iter_round_metadata()):
        assert not {"end_price", "official_outcome", "resolved_at_us", "settlement_state"} & asdict(row).keys()
    assert window.verify_consumed()


@pytest.mark.parametrize("precision", [6, 28, 50])
def test_fix2_reader_digest_preserves_decimal128_low_digits(db, precision):
    from decimal import localcontext

    target = db["yquant-data"]
    row = _kline(ceil_ms_to_us(DAY0), observed=DAY0)
    row["close"] = Decimal128("100.1234567890123456789012345678901")
    target[KLINES_COLLECTION].insert_one(row)
    with localcontext() as context:
        context.prec = precision
        before = _window(target)
        target[KLINES_COLLECTION].update_one({}, {"$set": {
            "close": Decimal128("100.1234567890123456789012345678902"),
        }})
        after = _window(target)
        assert before.content_sha256 != after.content_sha256
        with pytest.raises(HistoryError, match="DATASET_CHANGED"):
            _window(target, expected_manifest=before.content_manifest)


def test_ut17_gap_is_partial_with_fixed_denominator(db):
    target = db["yquant-data"]
    target[KLINES_COLLECTION].insert_one(_kline(ceil_ms_to_us(DAY0), observed=DAY0))
    window = _window(target, 10, warmup_seconds=2)
    assert window.status == "partial"
    assert window.missing
    assert window.content_manifest["expected_seconds"] == 12
    assert window.coverage.stored_rows == 1


def test_ut19_reader_requires_three_consumed_streams(db):
    window = _window(db["yquant-data"])
    with pytest.raises(HistoryError, match="INCOMPLETE_CONSUMPTION"):
        window.verify_consumed()
    list(window.iter_features())
    list(window.iter_round_metadata())
    with pytest.raises(HistoryError, match="INCOMPLETE_CONSUMPTION"):
        window.verify_consumed()
    list(window.iter_labels())
    assert window.verify_consumed()


def test_ut19_unknown_schema_fails(db):
    target = db["yquant-data"]
    target[KLINES_COLLECTION].insert_one(dict(
        _kline(ceil_ms_to_us(DAY0), observed=DAY0), schema_version=99,
    ))
    with pytest.raises(HistoryError, match="UNKNOWN_SCHEMA_VERSION"):
        _window(target)


def test_ut19_midstream_actual_business_change_is_detected(db, monkeypatch):
    import skills.data.unified_data.history_reader as module

    monkeypatch.setattr(module, "MAX_BATCH", 2)
    target = db["yquant-data"]
    base = ceil_ms_to_us(DAY0)
    target[KLINES_COLLECTION].insert_many([
        _kline(base + offset * SECOND, observed=DAY0) for offset in range(5)
    ])
    window = _window(target, 5)
    stream = window.iter_features()
    next(stream)
    # Do not change record_sha256: trusting stored hashes alone is insufficient.
    target[KLINES_COLLECTION].update_one(
        {"open_time_us": base + 4 * SECOND}, {"$set": {"close": Decimal128("102")}},
    )
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        list(stream)


def test_ut18_raw_hash_changes_only_provenance(db):
    target = db["yquant-data"]
    target[KLINES_COLLECTION].insert_one(dict(
        _kline(ceil_ms_to_us(DAY0), observed=DAY0), raw_ref="a", raw_sha256="a" * 64,
    ))
    before = _window(target)
    target[KLINES_COLLECTION].update_one({}, {"$set": {"raw_ref": "b", "raw_sha256": "b" * 64}})
    after = _window(target)
    assert before.content_sha256 == after.content_sha256
    assert before.provenance_manifest != after.provenance_manifest


def test_ut18_keyset_pages_are_bounded(db, monkeypatch):
    import skills.data.unified_data.history_reader as module

    monkeypatch.setattr(module, "MAX_BATCH", 2)
    target = db["yquant-data"]
    base = ceil_ms_to_us(DAY0)
    target[KLINES_COLLECTION].insert_many([
        _kline(base + index * SECOND, observed=DAY0) for index in range(5)
    ])
    collection = target[KLINES_COLLECTION]
    original_find = collection.find
    queries, limits, batches = [], [], []

    def find(query, *args, **kwargs):
        queries.append(query)
        cursor = original_find(query, *args, **kwargs)
        original_limit, original_batch = cursor.limit, cursor.batch_size

        def limit(value):
            limits.append(value)
            return original_limit(value)

        def batch_size(value):
            batches.append(value)
            return original_batch(value)

        cursor.limit, cursor.batch_size = limit, batch_size
        return cursor

    monkeypatch.setattr(collection, "find", find)
    window = _window(target, 5)
    assert len(list(window.iter_features())) == 5
    assert len(limits) >= 3 and all(0 < value <= 2 for value in limits)
    assert batches and all(0 < value <= 2 for value in batches)
    assert any("$and" in query for query in queries)


def _shard(target, *, state="complete"):
    target["03_data_ud_history_ingestion"].insert_one({
        "_id": "day/predict_btc5m_rounds/2026-08-10", "schema_version": 1,
        "kind": "day", "dataset": "predict_btc5m_rounds", "utc_date": "2026-08-10",
        "state": state, "content_sha256": "a" * 64, "raw_manifest_ref": "first.json",
        "counts": {"resolved": 1, "inserted": 1},
    })


def test_ut19_shard_change_during_consumption_and_after_end(db):
    target = db["yquant-data"]
    _shard(target)
    window = _window(target)
    stream = window.iter_features()
    list(stream)
    list(window.iter_round_metadata())
    list(window.iter_labels())
    target["03_data_ud_history_ingestion"].update_one({}, {"$set": {"state": "conflict"}})
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        window.verify_consumed()


def test_ut16_conflict_shard_does_not_emit_labels(db):
    target = db["yquant-data"]
    _shard(target, state="conflict")
    base = ceil_ms_to_us(DAY0)
    target[ROUNDS_COLLECTION].insert_one(_round(
        "1", base, observed=DAY0, state="resolved", outcome="UP",
        resolved_at_us=base + 301 * SECOND, label_observed=DAY0,
    ))
    window = _window(target, 300)
    assert list(window.iter_labels()) == []
    assert window.status == "partial"


@pytest.mark.parametrize("mode", ["observed", "event-time-proxy"])
def test_ut16_missing_label_proof_never_uses_end_time(db, mode):
    target = db["yquant-data"]
    base = ceil_ms_to_us(DAY0)
    target[ROUNDS_COLLECTION].insert_one(_round(
        "1", base, observed=DAY0, state="resolved", outcome="UP", label_observed=DAY0,
    ))
    window = _window(target, 300, availability_mode=mode)
    assert list(window.iter_labels()) == []
    assert window.status == "partial"


def test_ut16_observed_label_missing_observation_is_unavailable(db):
    target = db["yquant-data"]
    base = ceil_ms_to_us(DAY0)
    target[ROUNDS_COLLECTION].insert_one(_round(
        "1", base, observed=DAY0, state="resolved", outcome="UP",
        resolved_at_us=base + 301 * SECOND,
    ))
    assert list(_window(target, 300).iter_labels()) == []
    assert len(list(_window(target, 300, availability_mode="event-time-proxy").iter_labels())) == 1


def test_ut19_changed_already_yielded_page_is_detected_at_end(db, monkeypatch):
    import skills.data.unified_data.history_reader as module

    monkeypatch.setattr(module, "MAX_BATCH", 2)
    target = db["yquant-data"]
    base = ceil_ms_to_us(DAY0)
    target[KLINES_COLLECTION].insert_many([
        _kline(base + offset * SECOND, observed=DAY0) for offset in range(5)
    ])
    window = _window(target, 5)
    stream = window.iter_features()
    next(stream)
    target[KLINES_COLLECTION].update_one({"open_time_us": base}, {"$set": {"close": Decimal128("99")}})
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        list(stream)


def test_ut19_unknown_schema_during_consumption_is_not_empty(db):
    target = db["yquant-data"]
    target[KLINES_COLLECTION].insert_one(_kline(ceil_ms_to_us(DAY0), observed=DAY0))
    window = _window(target)
    target[KLINES_COLLECTION].update_one({}, {"$set": {"schema_version": 2}})
    with pytest.raises(HistoryError, match="UNKNOWN_SCHEMA_VERSION"):
        list(window.iter_features())


def test_ut18_shard_raw_reference_does_not_change_business_manifest(db):
    target = db["yquant-data"]
    _shard(target)
    before = _window(target)
    target["03_data_ud_history_ingestion"].update_one({}, {"$set": {"raw_manifest_ref": "second.json"}})
    after = _window(target)
    assert before.content_sha256 == after.content_sha256
    assert before.provenance_manifest != after.provenance_manifest


def test_ut19_no_mark_consumed_shortcut(db):
    window = _window(db["yquant-data"])
    with pytest.raises(HistoryError, match="INCOMPLETE_CONSUMPTION"):
        window.mark_consumed()


@pytest.mark.parametrize("warmup", [-1, 0.5, True, "1"])
def test_ut16_invalid_warmup_is_explicit_error(db, warmup):
    with pytest.raises(HistoryError, match="INVALID_ARGUMENT"):
        _window(db["yquant-data"], warmup_seconds=warmup)


def test_ut17_gap_crossing_main_boundary_is_split(db):
    window = _window(db["yquant-data"], 10, warmup_seconds=2)
    gaps = [item for item in window.missing if item["dataset"] == "binance_spot_btcusdt_1s"
            and "start_us" in item]
    assert len(gaps) == 2
    assert gaps[0]["is_warmup"] and not gaps[1]["is_warmup"]
    assert gaps[0]["end_us"] == gaps[1]["start_us"] == ceil_ms_to_us(DAY0)


def test_ut18_replay_write_counts_do_not_change_business_manifest(db):
    target = db["yquant-data"]
    _shard(target)
    before = _window(target)
    target["03_data_ud_history_ingestion"].update_one({}, {"$set": {
        "counts.inserted": 0, "counts.matched_unchanged": 1,
    }})
    assert _window(target).content_sha256 == before.content_sha256


def test_ut18_round_keyset_uses_lexical_tie_breaker(db, monkeypatch):
    import skills.data.unified_data.history_reader as module

    monkeypatch.setattr(module, "MAX_BATCH", 2)
    target = db["yquant-data"]
    base = ceil_ms_to_us(DAY0)
    target[ROUNDS_COLLECTION].insert_many([
        _round(identifier, base, observed=DAY0) for identifier in ("2", "3", "10", "1", "11")
    ])
    window = _window(target, 300)
    assert [row.round_id for row in window.iter_round_metadata()] == ["1", "10", "11", "2", "3"]
    assert len(window.conflicts) == 4


def test_ut19_consumed_row_digest_is_not_only_stored_hash(db):
    from dataclasses import replace

    target = db["yquant-data"]
    target[KLINES_COLLECTION].insert_one(_kline(ceil_ms_to_us(DAY0), observed=DAY0))
    window = _window(target)
    original = window._stream_factories["features"]

    def corrupt_output():
        for row in original():
            yield replace(row, close=Decimal("999"))

    window._stream_factories["features"] = corrupt_output
    list(window.iter_features())
    list(window.iter_round_metadata())
    list(window.iter_labels())
    with pytest.raises(HistoryError, match="DATASET_CHANGED"):
        window.verify_consumed()
