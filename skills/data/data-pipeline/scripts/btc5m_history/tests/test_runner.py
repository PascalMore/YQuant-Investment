"""BTC5m 历史 runner 测试 — 03-018 UT10 / UT13 / UT14 / UT20。

覆盖：日 / stream 提交、连续水位不越 gap、pending 公平、预算与退出。
"""

from __future__ import annotations

import importlib

import mongomock
import pytest

_runner = importlib.import_module(
    "skills.data.data-pipeline.scripts.btc5m_history.runner"
)
_common = importlib.import_module(
    "skills.data.data-pipeline.scripts.btc5m_history.common"
)

IngestionStore = _runner.IngestionStore
advance_contiguous = _runner.advance_contiguous
combined_complete_through = _runner.combined_complete_through
plan_days = _runner.plan_days

Budget = _common.Budget
HistoryBudgetError = _common.HistoryBudgetError

DATASET = "predict_btc5m_rounds"
OTHER = "binance_spot_btcusdt_1s"


@pytest.fixture()
def store() -> IngestionStore:
    return IngestionStore(mongomock.MongoClient()["yquant-data"])


# ---------------------------------------------------------------------------
# UT13 — 日提交与连续水位
# ---------------------------------------------------------------------------


def test_ut13_complete_day_requires_content_hash(store: IngestionStore) -> None:
    with pytest.raises(ValueError):
        store.write_day(DATASET, "2026-08-10", state="complete")


def test_ut13_contiguous_watermark_does_not_skip_gap(store: IngestionStore) -> None:
    store.write_day(DATASET, "2026-08-10", state="complete", content_sha256="a" * 64)
    store.write_day(DATASET, "2026-08-11", state="gap")
    store.write_day(DATASET, "2026-08-12", state="complete", content_sha256="b" * 64)
    start_us = 1786320000000000
    boundary = advance_contiguous(store, DATASET, ingestion_start_us=start_us)
    # 只能推进到 gap 之前的那一天
    assert boundary == start_us + 86400_000_000


def test_ut13_interrupted_running_day_is_retried(store: IngestionStore) -> None:
    store.write_day(DATASET, "2026-08-10", state="running")
    plans = plan_days(
        store, DATASET, cutoff_utc_date="2026-08-12", max_days=7
    )
    reasons = {plan.utc_date: plan.reason for plan in plans}
    assert reasons.get("2026-08-10") == "interrupted_retry"


def test_ut13_conflict_day_is_reviewed(store: IngestionStore) -> None:
    # SPEC §9: a conflict now requires an exact operator review, never auto retry.
    store.write_day(DATASET, "2026-08-10", state="conflict")
    plans = plan_days(store, DATASET, cutoff_utc_date="2026-08-12", max_days=7,
                      retry_dates=["2026-08-10"])
    reasons = {plan.utc_date: plan.reason for plan in plans}
    assert reasons.get("2026-08-10") == "operator_retry"


@pytest.mark.parametrize("code", ["HTTP_NETWORK_ERROR", "HTTP_SERVER_ERROR", "HTTP_RATE_LIMITED"])
def test_step12_legacy_transient_due_is_readonly_fifteen_minutes(store, monkeypatch, code):
    from datetime import datetime, timedelta

    attempted = datetime(2026, 11, 12)
    moment = attempted + timedelta(minutes=16)
    monkeypatch.setattr(_runner, "utc_now", lambda: moment)
    store.write_day(OTHER, "2026-08-10", state="failed", error_code=code,
                    last_attempt_at=attempted, next_retry_at=attempted + timedelta(days=1))
    before = store.get_day(OTHER, "2026-08-10")
    plans = plan_days(store, OTHER, cutoff_utc_date="2026-08-11", max_days=7,
                      start_utc_date="2026-08-10")
    assert [plan.utc_date for plan in plans] == ["2026-08-10"]
    assert plans[0].stored_due == attempted + timedelta(days=1)
    assert plans[0].effective_due == attempted + timedelta(minutes=15)
    assert plans[0].retry_policy == "transient_15m"
    assert store.get_day(OTHER, "2026-08-10") == before
    monkeypatch.setattr(_runner, "utc_now", lambda: attempted + timedelta(minutes=14))
    assert plan_days(store, OTHER, cutoff_utc_date="2026-08-11", max_days=7,
                     start_utc_date="2026-08-10") == []


@pytest.mark.parametrize("code", ["BUDGET_EXHAUSTED", "SCAN_NOT_CLOSED"])
def test_step12_old_bounded_continuation_is_immediately_due(store, monkeypatch, code):
    from datetime import datetime, timedelta

    moment = datetime(2026, 11, 12)
    monkeypatch.setattr(_runner, "utc_now", lambda: moment)
    store.write_day(DATASET, "2026-08-10", state="pending", error_code=code,
                    next_retry_at=moment + timedelta(days=1))
    assert [plan.utc_date for plan in plan_days(
        store, DATASET, cutoff_utc_date="2026-08-11", max_days=7,
        start_utc_date="2026-08-10")] == ["2026-08-10"]


@pytest.mark.parametrize("code", ["HTTP_UNAUTHORIZED", "HTTP_FORBIDDEN", "BAD_CSV",
                                  "CHECKSUM_MISMATCH", "ROUND_CONFLICT", "ORDER_REVERSAL"])
def test_step12_nontransient_never_automatically_retries(store, monkeypatch, code):
    from datetime import datetime, timedelta

    moment = datetime(2026, 11, 12)
    monkeypatch.setattr(_runner, "utc_now", lambda: moment)
    store.write_day(DATASET, "2026-08-10", state="failed", error_code=code,
                    next_retry_at=moment - timedelta(days=1))
    assert plan_days(store, DATASET, cutoff_utc_date="2026-08-11", max_days=7,
                     start_utc_date="2026-08-10") == []


@pytest.mark.parametrize("code,minutes", [("HTTP_NETWORK_ERROR", 15),
    ("HTTP_SERVER_ERROR", 15), ("HTTP_RATE_LIMITED", 15), ("BUDGET_EXHAUSTED", 0),
    ("ARCHIVE_NOT_PUBLISHED_OR_MISSING", 1440)])
def test_step12_new_failure_persists_classified_due(store, monkeypatch, code, minutes):
    from datetime import datetime, timedelta

    moment = datetime(2026, 11, 12)
    monkeypatch.setattr(_runner, "utc_now", lambda: moment)
    history = _runner.HistoryRunner(store, store.db, budget=Budget())
    history._fail_day(OTHER, "2026-08-10", code)
    day = store.get_day(OTHER, "2026-08-10")
    assert day["next_retry_at"] == (moment + timedelta(minutes=minutes) if minutes else None)


def test_step12_closed_flag_without_manifest_never_completes(store):
    rows = synthetic_round_rows()
    store.db[_common.ROUNDS_COLLECTION].insert_many(rows)
    begin, stop = _common.day_bounds_us("2026-08-10")
    store.init_stream(DATASET, ingestion_start_us=begin)
    history = _runner.HistoryRunner(store, store.db, budget=Budget())
    review = history._review_round_day("2026-08-10", begin, stop)
    result = history._finish_round_day("2026-08-10", counts=review, review=review,
        scan=_runner.RoundScanResult(closed=True), errors=[])
    assert result.state == "pending"
    assert result.error_code == "DAY_MANIFEST_MISSING"
    assert store.get_stream(DATASET)["complete_through_us"] is None
    assert store.get_stream(DATASET)["enumerated_through_us"] is None


@pytest.mark.parametrize("restart", [False, True])
def test_step12_restart_scan_is_explicit_frozen_and_preserves_raw(
    store, scan_checkpoint_fixture, restart,
):
    import asyncio
    import json

    context, archive, history = scan_checkpoint_fixture
    asyncio.run(history().run_round_days(["2026-08-10"]))
    before = store.get_stream(DATASET)
    reference = before["scan_manifest_ref"]
    original = archive.read_bytes(reference)
    if restart:
        result = asyncio.run(history().run_round_days(["2026-08-11"], restart_scan=True))
        assert context["calls"] == [None, None]
        assert result[0].state == "pending"
        assert reference in store.get_stream(DATASET)["scan_restart_history"]
    else:
        result = asyncio.run(history().run_round_days(["2026-08-11"]))
        assert context["calls"] == [None, "2026-08-10/page1"]
        assert result[0].state == "complete"
    assert result[0].utc_date == "2026-08-10"
    manifest = json.loads(archive.read_bytes(result[0].raw_manifest_ref))
    assert manifest["lower_us"] == before["scan_lower_us"]
    assert manifest["upper_us"] == before["scan_upper_us"]
    assert manifest["utc_dates"] == ["2026-08-10"]
    assert archive.read_bytes(reference) == original


def test_step12_enumerated_and_complete_are_distinct_contiguous_watermarks(
    store, scan_checkpoint_fixture,
):
    import asyncio

    context, archive, history = scan_checkpoint_fixture
    context["case"] = "gap"
    asyncio.run(history().run_round_days(["2026-08-10"]))
    asyncio.run(history().run_round_days(["2026-08-10"]))
    assert store.get_stream(DATASET)["enumerated_through_us"] is None
    # A real closed enumeration with full identity/slots may precede settlement.
    context["case"] = "complete"
    asyncio.run(history().run_round_days(["2026-08-10"], restart_scan=True))
    asyncio.run(history().run_round_days(["2026-08-10"]))
    boundary = _common.day_bounds_us("2026-08-10")[1]
    assert store.get_stream(DATASET)["enumerated_through_us"] == boundary
    store.db[_common.ROUNDS_COLLECTION].update_one({"starts_at_us": boundary - 300_000_000},
        {"$set": {"settlement_state": "pending", "official_outcome": None,
                  "resolved_at_us": None, "resolution_evidence": None, "end_price": None}})
    loaders = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.loader")
    row = store.db[_common.ROUNDS_COLLECTION].find_one({"starts_at_us": boundary - 300_000_000})
    store.db[_common.ROUNDS_COLLECTION].update_one({"_id": row["_id"]},
        {"$set": {"record_sha256": loaders._record_hash(row, DATASET)}})
    day = store.get_day(DATASET, "2026-08-10")
    checked = history()
    review = checked._review_round_day("2026-08-10", *_common.day_bounds_us("2026-08-10"))
    checked._finish_round_day("2026-08-10", counts=dict(review, closed=True), review=review,
        scan=_runner.RoundScanResult(closed=True, raw_manifest_ref=day["raw_manifest_ref"]), errors=[])
    assert store.get_stream(DATASET)["complete_through_us"] is None
    assert store.get_stream(DATASET)["enumerated_through_us"] == boundary


def test_ut13_combined_watermark_is_the_minimum(store: IngestionStore) -> None:
    start_us = 1786320000000000
    store.write_day(DATASET, "2026-08-10", state="complete", content_sha256="a" * 64)
    store.write_day(OTHER, "2026-08-10", state="complete", content_sha256="b" * 64)
    store.write_day(DATASET, "2026-08-11", state="complete", content_sha256="c" * 64)
    combined = combined_complete_through(
        {DATASET: store, OTHER: store}, ingestion_start_us=start_us
    )
    assert combined == start_us + 86400_000_000


def test_ut13_combined_watermark_is_none_when_one_source_lags(
    store: IngestionStore,
) -> None:
    start_us = 1786320000000000
    store.write_day(DATASET, "2026-08-10", state="complete", content_sha256="a" * 64)
    assert (
        combined_complete_through(
            {DATASET: store, OTHER: store}, ingestion_start_us=start_us
        )
        is None
    )


def test_ut13_day_digest_recomputes_actual_content_and_pairs_keys() -> None:
    loader = importlib.import_module(
        "skills.data.data-pipeline.scripts.btc5m_history.loader"
    )
    rows = [{"schema_version": 1, "open_time_us": value, "close": str(value)}
            for value in (2_000_000, 1_000_000)]
    for row in rows:
        row["record_sha256"] = loader._record_hash(row, OTHER)
    assert _runner._digest_of([], rows) == _runner._digest_of([], list(reversed(rows)))
    rows[0]["close"] = "tampered-without-changing-stored-hash"
    with pytest.raises(_common.HistoryHTTPError, match="READBACK_MISMATCH"):
        _runner._digest_of([], rows)


def test_ut13_non_midnight_warmup_ends_at_day_boundary(store: IngestionStore) -> None:
    start, stop = _common.day_bounds_us("2026-08-10")
    store.write_day(DATASET, "2026-08-10", state="complete", content_sha256="a" * 64)
    assert advance_contiguous(
        store, DATASET, ingestion_start_us=start + 123_000_000
    ) == stop


def test_ut13_conflict_retracts_existing_watermark(store: IngestionStore) -> None:
    start, stop = _common.day_bounds_us("2026-08-10")
    store.init_stream(DATASET, ingestion_start_us=start, complete_through_us=stop)
    store.write_day(DATASET, "2026-08-10", state="conflict")
    runner = _runner.HistoryRunner(store, store.db, budget=Budget())
    runner._advance_stream(DATASET)
    assert store.get_stream(DATASET)["complete_through_us"] is None


def test_ut20_backfill_plan_never_includes_outside_target(store: IngestionStore) -> None:
    plans = plan_days(
        store, DATASET, cutoff_utc_date="2026-11-11", max_days=7,
        start_utc_date="2026-08-10", end_utc_date="2026-11-10",
    )
    assert all("2026-08-10" <= plan.utc_date < "2026-11-10" for plan in plans)
    assert plans[0].utc_date == "2026-11-09"


# ---------------------------------------------------------------------------
# UT20 — 计划公平性与预算
# ---------------------------------------------------------------------------


def test_ut20_recent_complete_day_gets_one_slot(store: IngestionStore) -> None:
    plans = plan_days(store, DATASET, cutoff_utc_date="2026-08-12", max_days=7)
    assert any(plan.reason == "recent_complete_day" for plan in plans)


def test_ut20_oldest_incomplete_day_has_priority(store: IngestionStore) -> None:
    store.write_day(DATASET, "2026-08-10", state="gap")
    store.write_day(DATASET, "2026-08-11", state="gap")
    plans = plan_days(store, DATASET, cutoff_utc_date="2026-08-20", max_days=2)
    dates = [plan.utc_date for plan in plans]
    # 先保留最近完整日 1 名额，其余按最早未完成日期。
    assert dates[0] == "2026-08-19"
    assert dates[1] == "2026-08-10"


def test_ut20_single_day_budget_keeps_old_backlog(store: IngestionStore) -> None:
    store.write_day(DATASET, "2026-08-01", state="gap")
    plans = plan_days(store, DATASET, cutoff_utc_date="2026-08-20", max_days=1)
    assert len(plans) == 1
    assert plans[0].utc_date == "2026-08-19"


def test_ut20_budget_is_bounded() -> None:
    budget = Budget(max_days_per_source=7, wall_seconds=1800, max_requests=1000)
    budget.validate()
    with pytest.raises(HistoryBudgetError):
        Budget(max_days_per_source=0).validate()
    with pytest.raises(HistoryBudgetError):
        Budget(wall_seconds=10).validate()
    with pytest.raises(HistoryBudgetError):
        Budget(max_requests=99999).validate()
    with pytest.raises(HistoryBudgetError):
        Budget(chunk_size=99999).validate()


def test_ut20_day_budget_is_capped(store: IngestionStore) -> None:
    for index in range(20):
        store.write_day(
            DATASET, f"2026-07-{index + 1:02d}", state="gap"
        )
    plans = plan_days(store, DATASET, cutoff_utc_date="2026-08-20", max_days=3)
    assert len(plans) <= 3


# ---------------------------------------------------------------------------
# UT14 — pending 公平
# ---------------------------------------------------------------------------


def test_ut14_pending_days_are_not_starved(store: IngestionStore) -> None:
    """旧 pending 仍出现在计划里（不会被最新日挤出）。"""
    store.write_day(DATASET, "2026-07-01", state="pending")
    store.write_day(DATASET, "2026-08-01", state="pending")
    plans = plan_days(store, DATASET, cutoff_utc_date="2026-08-20", max_days=7)
    dates = [plan.utc_date for plan in plans]
    assert "2026-07-01" in dates


def synthetic_round_rows():
    """Build a full nominal day from explicitly synthetic official-schema envelopes."""
    from datetime import datetime, timedelta
    from bson import Decimal128

    factory = importlib.import_module(
        "skills.data.data-pipeline.scripts.btc5m_history.tests.test_transforms"
    )._round_envelope
    transforms = importlib.import_module(
        "skills.data.data-pipeline.scripts.btc5m_history.transforms"
    )
    loader = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.loader")
    rows = []
    for index in range(288):
        start = datetime(2026, 8, 10) + timedelta(seconds=index * 300)
        row = transforms.PredictRoundTransformer().transform_one(factory(
            starts_at=start.isoformat() + "Z",
            ends_at=(start + timedelta(seconds=300)).isoformat() + "Z", round_id=index + 1,
        ))
        for field_name in ("start_price", "end_price"):
            row[field_name] = Decimal128(row[field_name])
        row["record_sha256"] = loader._record_hash(row, DATASET)
        rows.append(row)
    return rows


@pytest.mark.parametrize("case,expected", [
    ("complete", "complete"), ("missing", "gap"), ("one", "gap"), ("empty", "gap"),
    ("duplicate", "conflict"), ("overlap", "conflict"), ("off_grid", "conflict"),
    ("identity", "conflict"), ("pending", "pending"), ("unavailable", "pending"),
    ("settlement_conflict", "conflict"), ("unknown_state", "conflict"),
    ("missing_start_price", "gap"), ("invalid_label", "conflict"),
])
def test_round_day_requires_identity_grid_and_official_settlement(
    store, case, expected, scan_checkpoint_fixture,
):
    import asyncio

    # Obtain a real closed manifest before isolating individual day-review faults.
    context, archive, make_history = scan_checkpoint_fixture
    asyncio.run(make_history().run_round_days(["2026-08-10"]))
    closed = asyncio.run(make_history().run_round_days(["2026-08-10"]))[0]
    store.db[_common.ROUNDS_COLLECTION].delete_many({})
    loader = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.loader")
    rows = synthetic_round_rows()
    if case == "missing":
        rows.pop(1)
    elif case == "one":
        rows = rows[:1]
    elif case == "empty":
        rows = []
    elif case == "duplicate":
        rows[1]["round_id"] = rows[0]["round_id"]
    elif case in ("overlap", "off_grid"):
        rows[1]["starts_at_us"] += -150_000_000 if case == "overlap" else 1_000_000
        rows[1]["ends_at_us"] = rows[1]["starts_at_us"] + 300_000_000
    elif case == "identity":
        rows[1]["price_feed_symbol"] = "ETHUSDT"
    elif case in ("pending", "unavailable", "settlement_conflict", "unknown_state"):
        state = {"settlement_conflict": "conflict", "unknown_state": "other"}.get(case, case)
        for row in rows:
            row.update(settlement_state=state, official_outcome=None, resolved_at_us=None,
                       resolution_evidence=None, end_price=None)
    elif case == "missing_start_price":
        rows[1].update(start_price=None, settlement_state="pending")
    elif case == "invalid_label":
        rows[1]["official_outcome"] = None
    for row in rows:
        row["record_sha256"] = loader._record_hash(row, DATASET)
    if rows:
        store.db[_common.ROUNDS_COLLECTION].insert_many(rows)
    begin, stop = _common.day_bounds_us("2026-08-10")
    store.init_stream(DATASET, ingestion_start_us=begin, complete_through_us=stop)
    history = _runner.HistoryRunner(store, store.db, budget=Budget(), archive=archive)
    review = history._review_round_day("2026-08-10", begin, stop)
    result = history._finish_round_day(
        "2026-08-10", counts=review, review=review,
        scan=_runner.RoundScanResult(closed=True, raw_manifest_ref=closed.raw_manifest_ref), errors=[],
    )
    assert result.state == expected
    assert review["stored"] == len(rows)
    assert sum(review[key] for key in ("resolved", "pending", "unavailable", "conflict")) == len(rows)
    assert store.get_stream(DATASET)["complete_through_us"] == (stop if expected == "complete" else None)
    assert bool(result.content_sha256) == (expected == "complete")
    if case == "missing":
        assert review["missing_nominal_slots"] == 1
        assert review["missing_nominal_intervals"] == [[begin + 300_000_000, begin + 600_000_000]]
    if case == "one":
        assert review["resolved"] == 1 and review["missing_nominal_slots"] == 287
    if case == "duplicate":
        assert review["distinct_start_slots"] == 288 and review["duplicate_natural_keys"] == 1
    if case == "pending":
        assert review["pending"] == 288 and review["missing_nominal_slots"] == 0
    if case in ("overlap", "off_grid"):
        assert review["off_grid"] == review["overlaps"] == 1


@pytest.mark.parametrize("days_per_run", [1, 7])
def test_fix2_plan_due_and_unseen_progress_across_repeated_failures(store, monkeypatch, days_per_run):
    from datetime import datetime, timedelta

    moment = datetime(2026, 11, 11)
    monkeypatch.setattr(_runner, "utc_now", lambda: moment)
    for day in range(10, 17):
        store.write_day(DATASET, f"2026-08-{day}", state="pending",
                        next_retry_at=moment + timedelta(days=10))
    store.write_day(DATASET, "2026-08-17", state="pending", next_retry_at=moment - timedelta(days=1))
    visited = set()
    # The fixed 92-day window must drain unseen days even if every attempt fails;
    # once enumerated, oldest-attempted due days must also recur.
    for index in range(100):
        plans = plan_days(store, DATASET, cutoff_utc_date="2026-11-11", max_days=days_per_run,
                          start_utc_date="2026-08-10", end_utc_date="2026-11-10")
        dates = [plan.utc_date for plan in plans]
        assert len(dates) <= days_per_run and len(set(dates)) == len(dates)
        assert not any(f"2026-08-{day}" in dates for day in range(10, 17))
        visited.update(dates)
        for day in dates:
            store.write_day(DATASET, day, state="failed", error_code="ARCHIVE_NOT_PUBLISHED_OR_MISSING",
                            last_attempt_at=moment + timedelta(seconds=index), next_retry_at=moment)
        assert advance_contiguous(store, DATASET, ingestion_start_us=_common.day_bounds_us("2026-08-10")[0]) is None
    assert "2026-08-17" in visited and "2026-08-18" in visited
    assert len(visited) >= min(10, days_per_run * 2)


def test_fix2_apply_index_initialization_is_exact_repeatable_and_rejects_drift(store, monkeypatch):
    from pymongo.errors import DuplicateKeyError

    _runner.ensure_history_indexes(store.db)
    before = {name: store.db[name].index_information() for name in store.db.list_collection_names()}
    monkeypatch.setattr(mongomock.collection.Collection, "create_index", lambda *a, **k: pytest.fail("repeat DDL"))
    _runner.ensure_history_indexes(store.db)
    assert before == {name: store.db[name].index_information() for name in before}
    for collection_name, fields in (
        (_common.ROUNDS_COLLECTION, ("source", "series_slug", "round_id")),
        (_common.KLINES_COLLECTION, ("source", "market_type", "symbol", "interval", "open_time_us")),
        (_common.INGESTION_COLLECTION, ("kind", "dataset", "utc_date")),
    ):
        collection = store.db[collection_name]
        row = {field: "synthetic" for field in fields}
        collection.insert_one(dict(row))
        with pytest.raises(DuplicateKeyError):
            collection.insert_one(dict(row))
        assert all("expireAfterSeconds" not in spec for spec in before[collection_name].values())


@pytest.mark.parametrize("fault", [
    None, "missing_raw", "bad_raw", "bad_sha", "identity", "business_hash", "price",
])
def test_fix3_partial_fill_replays_exact_category_or_rejects_damage(tmp_path, fault):
    import copy
    import json
    from decimal import Decimal

    loaders = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.loader")
    transforms = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.transforms")
    factory = importlib.import_module(
        "skills.data.data-pipeline.scripts.btc5m_history.tests.test_transforms"
    )._round_envelope
    archive = _common.RawArchive(tmp_path / "raw")
    original = factory(market_status="OPEN", trading_status="OPEN")
    original["category"]["variantDetails"]["endPrice"] = None
    original["_status_logs"] = {"4450895": []}
    original_ref, original_sha = archive.store_json("2026-08-10", {
        "success": True, "data": [original], "cursor": None,
    })
    original.update(_raw_ref=original_ref, _raw_sha256=original_sha)
    transform = transforms.PredictRoundTransformer()
    initial = transform.transform_one(original)
    latest = copy.deepcopy(original)
    latest["category"]["variantDetails"]["endPrice"] = "101.5"
    category = dict(latest["category"], markets=latest["markets"])
    if fault == "identity":
        category["id"] += 1
    current_ref, current_sha = archive.store_json("2026-08-10", {
        "success": True, "data": category,
    })
    current = transform.transform_one(latest)
    current.update(raw_ref=current_ref, raw_sha256=current_sha,
                   record_sha256=loaders._record_hash(current, DATASET), raw_history=[{
                       "raw_ref": original_ref, "raw_sha256": original_sha,
                       "record_sha256": loaders._record_hash(initial, DATASET),
                   }])
    assert current["resolution_evidence"] is None
    if fault == "missing_raw":
        archive.resolve(current_ref).unlink()
    elif fault == "bad_raw":
        archive.resolve(current_ref).write_bytes(b"corrupt synthetic raw")
    elif fault == "bad_sha":
        current["raw_sha256"] = "0" * 64
    elif fault == "business_hash":
        current["record_sha256"] = "0" * 64
    elif fault == "price":
        current["end_price"] = Decimal("999")
        current["record_sha256"] = loaders._record_hash(current, DATASET)
    if fault:
        before = copy.deepcopy(current)
        with pytest.raises((OSError, ValueError, _common.HistoryHTTPError)):
            _runner.reconcile_round_raw(original, current, archive)
        assert current == before
    else:
        replay = _runner.reconcile_round_raw(original, current, archive)
        record = transform.transform_one(replay)
        assert record["settlement_state"] == "pending"
        assert record["end_price"] == Decimal("101.5")
        assert record["resolution_evidence"] is None
        assert loaders._record_hash(record, DATASET) == current["record_sha256"]
        assert json.loads(archive.read_bytes(original_ref))["data"][0]["category"]["variantDetails"]["endPrice"] is None


@pytest.mark.parametrize("shape", ["flat_list", "canonical_list", "flat_category"])
@pytest.mark.parametrize("terminal", [False, True])
def test_shape_fix_reconcile_latest_raw_uses_shared_boundary(tmp_path, shape, terminal):
    """Explicit synthetic pending fills exercise both identity and enumeration raw."""
    import copy
    from decimal import Decimal

    modules = "skills.data.data-pipeline.scripts.btc5m_history."
    factory = importlib.import_module(modules + "tests.test_transforms")._round_envelope
    transforms = importlib.import_module(modules + "transforms")
    loaders = importlib.import_module(modules + "loader")
    archive = _common.RawArchive(tmp_path)
    original = factory(market_status="OPEN", trading_status="OPEN")
    original["category"]["variantDetails"]["endPrice"] = None
    original["_status_logs"] = {"4450895": []}
    original_ref, original_sha = archive.store_json("2026-08-10", {
        "success": True, "data": [dict(original["category"], markets=original["markets"])], "cursor": None,
    })
    original.update(_raw_ref=original_ref, _raw_sha256=original_sha)
    latest = factory() if terminal else copy.deepcopy(original)
    latest["category"]["variantDetails"]["endPrice"] = "101.5"
    flat = dict(latest["category"], markets=latest["markets"])
    data = flat if shape == "flat_category" else [flat if shape == "flat_list" else latest]
    current_ref, current_sha = archive.store_json("2026-08-10", {"success": True, "data": data})
    if terminal:
        ref, sha = archive.store_json("2026-08-10", {"success": True, "data": [{
            "marketId": "4450895", "logs": latest["_status_logs"]["4450895"],
        }]})
        latest["_status_raw_refs"] = [{"raw_ref": ref, "raw_sha256": sha}]
    transformer = transforms.PredictRoundTransformer()
    first = transformer.transform_one(original)
    current = transformer.transform_one(latest)
    current.update(raw_ref=current_ref, raw_sha256=current_sha,
        record_sha256=loaders._record_hash(current, DATASET), raw_history=[{
            "raw_ref": original_ref, "raw_sha256": original_sha,
            "record_sha256": loaders._record_hash(first, DATASET),
        }])
    before = copy.deepcopy(current)
    replay = _runner.reconcile_round_raw(original, current, archive)
    record = transformer.transform_one(replay)
    assert record["end_price"] == Decimal("101.5")
    assert record["settlement_state"] == ("resolved" if terminal else "pending")
    assert loaders._record_hash(record, DATASET) == current["record_sha256"]
    assert current == before


@pytest.mark.parametrize("fault", ["page_bytes", "page_hash", "status_bytes", "status_hash", "duplicate_status", "dual_structure"])
def test_shape_fix_read_raw_still_rejects_damage(tmp_path, fault):
    import json

    samples = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.tests.test_extractors")
    archive = _common.RawArchive(tmp_path)
    page_ref, page_sha = archive.store_bytes("2026-11-11", samples.OFFICIAL_EXCERPT)
    status_ref, status_sha = archive.store_bytes("2026-11-11", samples.OFFICIAL_STATUS_EXCERPT)
    page = {"raw_ref": page_ref, "raw_sha256": page_sha, "count": 1,
            "cursor": json.loads(samples.OFFICIAL_EXCERPT)["cursor"],
            "status_refs": [{"raw_ref": status_ref, "raw_sha256": status_sha}]}
    if fault == "page_bytes":
        archive.resolve(page_ref).write_bytes(b"damaged fixture")
    elif fault == "page_hash":
        page["raw_sha256"] = "0" * 64
    elif fault == "status_bytes":
        archive.resolve(status_ref).write_bytes(b"damaged fixture")
    elif fault == "status_hash":
        page["status_refs"][0]["raw_sha256"] = "0" * 64
    elif fault == "duplicate_status":
        page["status_refs"] *= 2
    else:
        document = json.loads(samples.OFFICIAL_EXCERPT)
        document["data"][0]["category"] = {"id": 1}
        page["raw_ref"], page["raw_sha256"] = archive.store_json("2026-11-11", document)
    with pytest.raises(_common.HistoryHTTPError):
        _runner.read_round_page(archive, page)


bulk_boundary = importlib.import_module(
    "skills.data.data-pipeline.scripts.btc5m_history.tests.test_loader"
).bulk_boundary


@pytest.fixture()
def scan_checkpoint_fixture(store, tmp_path, monkeypatch, bulk_boundary):
    """Synthetic official pages; real scan/ETVL/archive, mongomock, no network."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    modules = "skills.data.data-pipeline.scripts.btc5m_history."
    extractors = importlib.import_module(modules + "extractors")
    factory = importlib.import_module(modules + "tests.test_transforms")._round_envelope
    archive = _common.RawArchive(tmp_path / "raw")
    context = {"day": "2026-08-10", "case": "complete", "calls": []}
    start, _ = _common.day_bounds_us(context["day"])
    store.init_stream(DATASET, ingestion_start_us=start)

    async def extract_page(self, source, *, budget, api_key=None):
        budget.take_request()
        context["calls"].append(source.after)
        day = source.after.split("/")[0] if source.after else context["day"]
        origin = datetime.fromisoformat(day)
        slots = list(range(288, -1, -1)) if source.after is None else [-1]
        cursor = day + "/page1" if source.after is None else day + "/closed"
        records = []
        logs = []
        for slot in slots:
            if context["case"] == "gap" and slot == 1:
                continue
            begin = origin + timedelta(minutes=5 * slot)
            end = begin + timedelta(minutes=5)
            identity = int(begin.replace(tzinfo=timezone.utc).timestamp())
            row = factory(starts_at=begin.isoformat() + "Z", ends_at=end.isoformat() + "Z",
                          round_id=identity)
            row["markets"][0]["id"] = str(identity)
            if context["case"] in ("conflict", "flat") and slot == 1:
                row["markets"][0]["outcomes"][1]["status"] = "WON"
                if context["case"] == "flat":
                    row["category"]["variantDetails"]["endPrice"] = "100.5"
                    row["markets"][0]["description"] = (
                        "If the two prices are exactly equal, the market will resolve 50-50.")
            log = dict(row.pop("_status_logs")["4450895"][0],
                       timestamp=(end + timedelta(minutes=1)).isoformat() + "Z")
            logs.append({"marketId": str(identity), "logs": [log]})
            records.append(row)
        status_ref, status_sha = archive.store_json(day, {"success": True, "data": logs})
        raw_ref, raw_sha = archive.store_json(day, {
            "success": True, "data": records, "cursor": cursor,
        })
        page = {"raw_ref": raw_ref, "raw_sha256": raw_sha, "count": len(records),
                "cursor": cursor, "status_refs": [{"raw_ref": status_ref, "raw_sha256": status_sha}]}
        return SimpleNamespace(records=_runner.read_round_page(archive, page), next_after=cursor,
                               raw_ref=raw_ref, raw_sha256=raw_sha)

    monkeypatch.setattr(extractors.PredictRoundExtractor, "extract_page", extract_page)

    def history():
        return _runner.HistoryRunner(store, store.db, archive=archive,
                                     budget=Budget(max_requests=1, max_days_per_source=1))

    return context, archive, history


@pytest.mark.parametrize("changed_day", [False, True])
@pytest.mark.parametrize("case", ["complete", "gap", "conflict", "flat"])
def test_scan_checkpoint_rollover_restart(store, scan_checkpoint_fixture, changed_day, case):
    import asyncio
    import json

    context, archive, history = scan_checkpoint_fixture
    context["case"] = case
    first = asyncio.run(history().run_round_days(["2026-08-10"]))
    assert [(item.utc_date, item.state) for item in first] == [
        ("2026-08-10", "conflict" if case == "conflict" else "pending")]
    stream = store.get_stream(DATASET)
    initial_ref = stream["scan_manifest_ref"]
    initial = json.loads(archive.read_bytes(initial_ref))
    assert initial["next_after"] == stream["scan_cursor"] == "2026-08-10/page1"
    assert initial["lower_us"] == stream["scan_lower_us"]
    assert initial["upper_us"] == stream["scan_upper_us"]
    assert initial["closed"] is False
    assert store.get_stream(DATASET)["complete_through_us"] is None

    planned_day = "2026-08-11" if changed_day else "2026-08-10"
    second = asyncio.run(history().run_round_days([planned_day]))
    expected_state = "complete" if case == "flat" else case
    assert [(item.utc_date, item.state) for item in second] == [("2026-08-10", expected_state)]
    assert store.get_day(DATASET, "2026-08-11") is None
    stream = store.get_stream(DATASET)
    closed_ref = stream["scan_manifest_ref"]
    closed = json.loads(archive.read_bytes(closed_ref))
    assert closed_ref != initial_ref
    assert closed["closed"] is True
    assert closed["next_after"] == stream["scan_cursor"] == "2026-08-10/closed"
    assert closed["lower_us"] == initial["lower_us"] == stream["scan_lower_us"]
    assert closed["upper_us"] == initial["upper_us"] == stream["scan_upper_us"]
    assert store.get_day(DATASET, "2026-08-10")["raw_manifest_ref"] == closed_ref
    assert second[0].counts["missing_nominal_slots"] == (1 if case == "gap" else 0)
    assert second[0].counts["conflict"] == (1 if case == "conflict" else 0)
    boundary = _common.day_bounds_us("2026-08-10")[1] if expected_state == "complete" else None
    assert stream["complete_through_us"] == boundary
    if case == "flat":
        flat = store.db[_common.ROUNDS_COLLECTION].find_one({"official_outcome": "DRAW"})
        assert flat["settlement_state"] == "resolved"
        assert flat["resolution_evidence"]["settlement_rule"] == "official-flat-50-50"
    if case == "conflict":
        conflict = store.db[_common.ROUNDS_COLLECTION].find_one({"settlement_state": "conflict"})
        assert conflict["official_outcome"] is None

    context["day"], context["case"] = "2026-08-11", "complete"
    third = asyncio.run(history().run_round_days(["2026-08-11"]))
    assert [(item.utc_date, item.state) for item in third] == [("2026-08-11", "pending")]
    assert context["calls"] == [None, "2026-08-10/page1", None]
    stream = store.get_stream(DATASET)
    assert stream["scan_lower_us"] == _common.day_bounds_us("2026-08-11")[0]
    assert store.get_day(DATASET, "2026-08-10")["raw_manifest_ref"] == closed_ref
    fourth = asyncio.run(history().run_round_days(["2026-08-12"]))
    assert [(item.utc_date, item.state) for item in fourth] == [("2026-08-11", "complete")]
    assert store.get_day(DATASET, "2026-08-12") is None
    assert store.get_stream(DATASET)["complete_through_us"] == (
        _common.day_bounds_us("2026-08-11")[1] if expected_state == "complete" else None)


def test_scan_checkpoint_legacy_day_only_resume(store, scan_checkpoint_fixture):
    import asyncio

    context, archive, history = scan_checkpoint_fixture
    asyncio.run(history().run_round_days(["2026-08-10"]))
    store.db[_common.INGESTION_COLLECTION].update_one(
        {"_id": store.stream_id(DATASET)}, {"$unset": {"scan_manifest_ref": ""}})
    result = asyncio.run(history().run_round_days(["2026-08-11"]))
    assert [(item.utc_date, item.state) for item in result] == [("2026-08-10", "complete")]
    assert context["calls"] == [None, "2026-08-10/page1"]
    assert store.get_stream(DATASET)["scan_manifest_ref"] == result[0].raw_manifest_ref


@pytest.mark.parametrize("fault", ["missing", "checksum", "wrong_window", "wrong_cursor", "wrong_kind"])
@pytest.mark.parametrize("restart", [False, True])
def test_scan_checkpoint_bad_direct_reference_fails_closed(store, scan_checkpoint_fixture, fault, restart):
    import asyncio
    import copy
    import json

    context, archive, history = scan_checkpoint_fixture
    asyncio.run(history().run_round_days(["2026-08-10"]))
    stream = store.get_stream(DATASET)
    reference = store.get_day(DATASET, "2026-08-10")["raw_manifest_ref"]
    candidate = json.loads(archive.read_bytes(reference))
    if fault in ("missing", "checksum"):
        damaged_ref, _ = archive.store_json("2026-08-10", dict(candidate, marker="damaged"))
        if fault == "missing":
            archive.resolve(damaged_ref).unlink()
        else:
            archive.resolve(damaged_ref).write_bytes(b"corrupt synthetic manifest")
    else:
        candidate[{"wrong_window": "lower_us", "wrong_cursor": "next_after",
                   "wrong_kind": "kind"}[fault]] = "wrong"
        damaged_ref, _ = archive.store_json("2026-08-10", candidate)
    store.write_stream(DATASET, {"scan_manifest_ref": damaged_ref})
    before = copy.deepcopy(store.get_stream(DATASET))
    with pytest.raises((OSError, ValueError, _common.HistoryHTTPError)):
        asyncio.run(history().run_round_days(["2026-08-11"], restart_scan=restart))
    assert store.get_stream(DATASET) == before
    assert context["calls"] == [None]
    assert store.get_day(DATASET, "2026-08-10")["raw_manifest_ref"] == reference
    assert store.get_stream(DATASET)["scan_cursor"] == stream["scan_cursor"]


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("natural_end", [False, True])
def test_scan_checkpoint_closed_window_review_is_day_bounded(
    store, scan_checkpoint_fixture, legacy, natural_end,
):
    import asyncio
    import json

    context, archive, history = scan_checkpoint_fixture
    asyncio.run(history().run_round_days(["2026-08-10"]))
    stream = store.get_stream(DATASET)
    seed = json.loads(archive.read_bytes(stream["scan_manifest_ref"]))
    seed.update(closed=True, upper_us=_common.day_bounds_us("2026-08-11")[1])
    if legacy:
        seed.pop("utc_dates")
    else:
        seed["utc_dates"] = ["2026-08-10", "2026-08-11"]
    if natural_end:
        seed["next_after"] = None
    reference, _ = archive.store_json("2026-08-10", seed)
    store.write_stream(DATASET, {"scan_cursor": seed["next_after"],
                               "scan_upper_us": seed["upper_us"], "scan_manifest_ref": reference})
    if legacy and not natural_end:
        # The original day-only format has neither direct ref nor frozen dates.
        store.write_day(DATASET, "2026-08-10", state="pending", raw_manifest_ref=reference)
        store.db[_common.INGESTION_COLLECTION].update_one(
            {"_id": store.stream_id(DATASET)}, {"$unset": {"scan_manifest_ref": ""}})
    first = asyncio.run(history().run_round_days(["2026-08-12", "2026-08-13"]))
    assert [(item.utc_date, item.state) for item in first] == [("2026-08-10", "complete")]
    assert store.get_day(DATASET, "2026-08-11") is None
    second = asyncio.run(history().run_round_days(["2026-08-12"]))
    assert [(item.utc_date, item.state) for item in second] == [("2026-08-11", "gap")]
    assert second[0].counts["stored_rounds"] == 1
    assert second[0].counts["missing_nominal_slots"] == 287
    assert context["calls"] == [None]  # Closed replay never needs a request.
    assert store.get_stream(DATASET)["scan_manifest_ref"] == reference
    assert store.get_stream(DATASET)["complete_through_us"] == _common.day_bounds_us("2026-08-10")[1]
    context["day"] = "2026-08-12"
    third = asyncio.run(history().run_round_days(["2026-08-12"]))
    assert [(item.utc_date, item.state) for item in third] == [("2026-08-12", "pending")]
    assert context["calls"] == [None, None]


def test_scan_checkpoint_missing_legacy_reference_is_not_reset(store, scan_checkpoint_fixture):
    import asyncio

    context, archive, history = scan_checkpoint_fixture
    asyncio.run(history().run_round_days(["2026-08-10"]))
    store.db[_common.INGESTION_COLLECTION].update_one(
        {"_id": store.stream_id(DATASET)}, {"$unset": {"scan_manifest_ref": ""}})
    store.write_day(DATASET, "2026-08-10", state="pending")
    before = store.get_stream(DATASET)
    with pytest.raises(_common.HistoryHTTPError, match="SCAN_STATE_MISSING"):
        asyncio.run(history().run_round_days(["2026-08-11"]))
    assert store.get_stream(DATASET) == before
    assert context["calls"] == [None]


@pytest.mark.parametrize("closed", [False, True])
def test_scan_checkpoint_wall_budget_does_not_commit_partial_replay(
    store, scan_checkpoint_fixture, monkeypatch, closed,
):
    import asyncio
    import json

    context, archive, history = scan_checkpoint_fixture
    asyncio.run(history().run_round_days(["2026-08-10"]))
    stream = store.get_stream(DATASET)
    if closed:
        seed = json.loads(archive.read_bytes(stream["scan_manifest_ref"]))
        seed["closed"] = True
        reference, _ = archive.store_json("2026-08-10", seed)
        store.write_stream(DATASET, {"scan_manifest_ref": reference})
    before = store.get_stream(DATASET)
    limited = history()
    monkeypatch.setattr(limited._budget, "remaining", lambda: -1)
    result = asyncio.run(limited.run_round_days(["2026-08-11"]))
    assert [(item.utc_date, item.state, item.error_code) for item in result] == [
        ("2026-08-10", "pending", "BUDGET_EXHAUSTED")]
    assert result[0].counts["closed"] is False
    assert result[0].raw_manifest_ref == before["scan_manifest_ref"]
    assert store.get_stream(DATASET)["scan_cursor"] == before["scan_cursor"]
    assert store.get_stream(DATASET)["complete_through_us"] is None
    assert context["calls"] == [None]
    resumed = asyncio.run(history().run_round_days(["2026-08-11"]))
    assert [(item.utc_date, item.state) for item in resumed] == [("2026-08-10", "complete")]

