"""03-018 offline integration: synthetic fixtures and sourced public wire excerpts."""
import asyncio
import hashlib
import importlib
import io
import zipfile
from types import SimpleNamespace

import mongomock
import pytest

from skills.data.unified_data.storage import select_databases
from skills.data.unified_data.services.storage_composition import build_persistent_client

PREFIX = "skills.data.data-pipeline.scripts"
common = importlib.import_module(PREFIX + ".btc5m_history.common")
extractors = importlib.import_module(PREFIX + ".btc5m_history.extractors")
runner = importlib.import_module(PREFIX + ".btc5m_history.runner")
cli = importlib.import_module(PREFIX + ".run_btc5m_history")
lab = importlib.import_module(
    "skills.strategies.strategy-lab.strategies.predict-btc5m-btc-arb.tests.test_history_input"
)


@pytest.fixture()
def db_boundary(monkeypatch):
    """Adapt only the Mongo transport boundary to mongomock's update API."""
    monkeypatch.setenv("PM_PREDICT_API_KEY", "synthetic-integration-key")
    monkeypatch.delenv("PM_PREDICT_API_KEY_FILE", raising=False)

    def bulk_write(collection, operations, *, ordered):
        assert ordered is False
        matched = upserted = 0
        for operation in operations:
            result = collection.update_one(
                operation._filter, operation._doc, upsert=operation._upsert
            )
            matched += result.matched_count
            upserted += result.upserted_id is not None
        return SimpleNamespace(
            acknowledged=True, matched_count=matched, upserted_count=upserted
        )
    monkeypatch.setattr(mongomock.collection.Collection, "bulk_write", bulk_write)
    return mongomock.MongoClient()["yquant-data"]


def test_it01_two_database_wiring():
    client = mongomock.MongoClient()
    databases = select_databases(client)
    facade = build_persistent_client(databases)
    assert databases.ta_cn.name == "tradingagents"
    assert databases.ud.name == "yquant-data"
    assert facade.read_btc5m_history(
        "2026-08-10T00:00:00Z", "2026-08-10T00:00:01Z",
        as_of_utc="2026-08-11T00:00:00Z",
    ).status == "partial"
    assert client["tradingagents"].list_collection_names() == []
    assert client["yquant-data"].list_collection_names() == []


@pytest.fixture()
def archive_run(db_boundary, tmp_path, monkeypatch):
    """HTTP ZIP bytes -> real ETVL -> actual fake Mongo readback, no fake success."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("BTCUSDT-1s-2026-08-10.csv",
            "1786320000000000,100,102,99,101,1,1786320000999999,101,1,1,101,0\n")
    body = buffer.getvalue()
    checksum = (hashlib.sha256(body).hexdigest() + "  BTCUSDT-1s-2026-08-10.zip\n").encode()

    def get(url, **kwargs):
        return checksum if url.endswith(".CHECKSUM") else body

    monkeypatch.setattr(extractors, "http_get", get)
    store = runner.IngestionStore(db_boundary)
    start, _ = common.day_bounds_us("2026-08-10")
    store.init_stream(common.DATASET_KLINES, ingestion_start_us=start)
    history = runner.HistoryRunner(
        store, db_boundary, budget=common.Budget(), archive=common.RawArchive(tmp_path)
    )
    return db_boundary, store, history


def test_it01_factory_external_refresh_and_sector_actual_target():
    from skills.data.unified_data import Market, ProviderError, ProviderRegistry, SecurityId
    from skills.data.unified_data.tests.conftest import FakeProvider
    from scripts.unified_data.sector_ranking_rollout.prod_repository import ProdRankingWriter

    client = mongomock.MongoClient()
    databases = select_databases(client)
    databases.ta_cn["synthetic_source"].insert_one({"_id": "preserved", "value": 7})
    registry = ProviderRegistry()
    provider = FakeProvider("tushare", payload={"close": [1234]},
                            capabilities={"market_data.kline_daily"}, markets={Market.CN})
    registry.register(provider)
    facade = build_persistent_client(databases, registry=registry)
    security = SecurityId(market=Market.CN, symbol="600519")
    result = facade.query("market_data", "kline_daily", security, force_refresh=True)
    assert result.provider == "tushare" and len(provider.call_log) == 1
    assert databases.ud["03_data_ud_kline_daily"].count_documents({}) == 1
    before = list(databases.ud["03_data_ud_kline_daily"].find({}))
    provider._raise = ProviderError("synthetic failure")
    failed = facade.query("market_data", "kline_daily", security, force_refresh=True)
    assert failed.provider == "error"
    assert list(databases.ud["03_data_ud_kline_daily"].find({})) == before
    writer = ProdRankingWriter(databases.ud)
    outcome = writer.upsert([{"dataset": "sw2021_ta_cn", "trade_date": "2026-08-10",
                              "sector_code": "801010", "pct_chg": 1.0}])
    assert not outcome.failed
    assert databases.ud[writer.COLLECTION].count_documents({}) == 1
    assert databases.ta_cn.list_collection_names() == ["synthetic_source"]
    assert databases.ta_cn["synthetic_source"].find_one({}) == {"_id": "preserved", "value": 7}


def test_it02_archive_pipeline_readback(archive_run):
    db, store, history = archive_run
    result = asyncio.run(history.run_kline_day("2026-08-10"))
    assert result.state == "gap"
    assert result.counts["valid_unique_seconds"] == 1
    assert result.counts["missing_seconds"] == 86399
    assert db[common.KLINES_COLLECTION].count_documents({}) == 1
    assert cli._verify_archive_manifest(result.raw_manifest_ref, "2026-08-10", archive=history._archive) is True
    assert store.get_stream(common.DATASET_KLINES)["complete_through_us"] is None
    document = db[common.KLINES_COLLECTION].find_one({})
    assert cli._verify_raw(document["raw_ref"], archive=history._archive) is True
    assert document["raw_sha256"] == hashlib.sha256(
        history._archive.resolve(document["raw_ref"]).read_bytes()
    ).hexdigest()
    assert cli._verify_archive_manifest(result.raw_manifest_ref, "2026-08-10",
                                        archive=history._archive, rows=[document])
    from bson import Decimal128
    altered = dict(document, close=Decimal128("100.5"))
    assert not cli._verify_archive_manifest(result.raw_manifest_ref, "2026-08-10",
                                            archive=history._archive, rows=[altered])


def test_it03_idempotent_recovery(archive_run):
    db, store, history = archive_run
    first = asyncio.run(history.run_kline_day("2026-08-10"))
    before = db[common.KLINES_COLLECTION].find_one({})
    second = asyncio.run(history.run_kline_day("2026-08-10"))
    assert first.state == second.state == "gap"
    assert db[common.KLINES_COLLECTION].count_documents({}) == 1
    after = db[common.KLINES_COLLECTION].find_one({})
    assert before == after
    assert second.counts["skipped"] == 1
    assert store.get_stream(common.DATASET_KLINES)["complete_through_us"] is None


def test_it04_facade_to_history_input():
    _, client = lab.seeded_client()
    bundle = lab.adapter.iter_history_input(client, lab.request())
    assert not bundle.verified
    scheduled = list(bundle.iter_scheduled())
    labels = list(bundle.iter_labels())
    assert bundle.verify_consumed() and bundle.verified
    assert labels[0].payload["official_outcome"] == "UP"
    assert all("official_outcome" not in row.payload for row in scheduled)
    as_of_us = lab.to_us(lab.request().as_of_utc.replace(tzinfo=None))
    assert all(row.available_at_us <= as_of_us for row in scheduled)
    assert [row.available_at_us for row in scheduled] == sorted(
        row.available_at_us for row in scheduled
    )


def test_it05_daily_and_wrapper(db_boundary, monkeypatch):
    store = runner.IngestionStore(db_boundary)
    monkeypatch.setattr(cli, "_open_store", lambda: store)
    assert cli.main(["daily", "--apply"]) == common.EXIT_FAIL
    assert db_boundary.list_collection_names() == []
    # No initialized stream may be invented by a daily attempt.
    for dataset in cli.DATASETS:
        assert store.get_stream(dataset) is None


@pytest.mark.parametrize("resolved", [False, True])
def test_step12_recheck_attempts_survive_restart_and_do_not_change_facts(
    db_boundary, tmp_path, monkeypatch, resolved,
):
    """Actual synthetic identity/status HTTP and original ETVL; never fake a load result."""
    import json
    from datetime import datetime, timedelta

    factory = importlib.import_module(PREFIX + ".btc5m_history.tests.test_transforms")._round_envelope
    loaders = importlib.import_module(PREFIX + ".btc5m_history.loader")
    transforms = importlib.import_module(PREFIX + ".btc5m_history.transforms")
    clock = [datetime(2026, 11, 12)]
    monkeypatch.setattr(runner, "utc_now", lambda: clock[0])
    monkeypatch.setattr(common, "utc_now", lambda: clock[0])
    archive = common.RawArchive(tmp_path / "raw")
    pending = factory(market_status="OPEN", trading_status="OPEN")
    pending["_status_logs"] = {"4450895": []}
    initial_ref, initial_sha = archive.store_json("2026-11-12", {"success": True,
        "data": dict(pending["category"], markets=pending["markets"])})
    loader = loaders.HistoryBatchLoader(db_boundary, common.DATASET_ROUNDS)
    loader.set_context(raw_ref=initial_ref, raw_sha256=initial_sha,
                       fetched_at=clock[0] - timedelta(days=10))
    assert not asyncio.run(loader.load([transforms.PredictRoundTransformer().transform_one(pending)])).errors
    collection = db_boundary[common.ROUNDS_COLLECTION]
    collection.update_one({}, {"$set": {"next_check_at": clock[0]}})
    original = collection.find_one({})
    store = runner.IngestionStore(db_boundary)
    store.init_stream(common.DATASET_ROUNDS,
                      ingestion_start_us=common.day_bounds_us("2026-08-10")[0])
    # This intentionally has no day manifest: fixing a row cannot close this day.
    store.write_day(common.DATASET_ROUNDS, "2026-08-10", state="pending")
    calls = []
    response = factory() if resolved else pending

    def transport(request, *, timeout):
        calls.append(request.full_url)
        if "/categories/" in request.full_url:
            document = dict(response["category"], markets=response["markets"])
        else:
            document = [{"marketId": "4450895", "logs": response["_status_logs"]["4450895"]}]
        return io.BytesIO(json.dumps({"success": True, "data": document}).encode())

    monkeypatch.setattr(common, "_open_http", transport)
    for index, wait in enumerate((1, 2, 4, 7, 7), 1):
        prior = collection.find_one({})
        # Zero requests must not increment attempts or modify any row fields.
        assert asyncio.run(runner.recheck_pending(db_boundary, budget=common.Budget(max_requests=0),
            archive=common.RawArchive(tmp_path / "raw"), now=clock[0])) == []
        assert collection.find_one({}) == prior
        tried = asyncio.run(runner.recheck_pending(db_boundary, budget=common.Budget(),
            archive=common.RawArchive(tmp_path / "raw"), now=clock[0]))
        row = collection.find_one({})
        if resolved and index > 1:
            assert tried == [] and row == prior
            break
        assert len(tried) == 1
        assert row["recheck_attempts"] == index
        assert row["next_check_at"] == clock[0] + timedelta(days=wait)
        assert row["first_observed_at"] == original["first_observed_at"]
        assert row["start_price_observed_at"] == original["start_price_observed_at"]
        assert row["schema_version"] == original["schema_version"] == 1
        assert row["record_sha256"] == loaders._record_hash(row, common.DATASET_ROUNDS)
        assert row["record_sha256"] == loaders._record_hash(
            dict(row, recheck_attempts=999, next_check_at=datetime(2099, 1, 1)), common.DATASET_ROUNDS)
        if not resolved:
            assert row["record_sha256"] == original["record_sha256"]
            assert row["fetched_at"] == original["fetched_at"]
            assert row["label_observed_at"] == original["label_observed_at"]
        assert store.get_day(common.DATASET_ROUNDS, "2026-08-10")["state"] == "pending"
        assert store.get_day(common.DATASET_ROUNDS, "2026-08-10")["raw_manifest_ref"] is None
        assert store.get_stream(common.DATASET_ROUNDS)["complete_through_us"] is None
        clock[0] = row["next_check_at"]
    assert len(calls) == (2 if resolved else 10)
    assert archive.read_bytes(initial_ref)


def test_step12_transient_scan_persists_due_and_resumes_without_reset(
    db_boundary, tmp_path, monkeypatch,
):
    import json
    import urllib.error
    from datetime import datetime, timedelta

    moment = datetime(2026, 11, 12)
    monkeypatch.setattr(common, "utc_now", lambda: moment)
    monkeypatch.setattr(runner, "utc_now", lambda: moment)
    monkeypatch.setattr(common.time, "sleep", lambda delay: None)
    calls = []

    def transport(request, *, timeout):
        calls.append(request.full_url)
        raise urllib.error.URLError("synthetic-network-failure")

    monkeypatch.setattr(common, "_open_http", transport)
    store = runner.IngestionStore(db_boundary)
    store.init_stream(common.DATASET_ROUNDS,
                      ingestion_start_us=common.day_bounds_us("2026-08-10")[0])
    archive = common.RawArchive(tmp_path / "raw")
    budget = common.Budget()
    result = asyncio.run(runner.HistoryRunner(store, db_boundary, budget=budget,
        archive=archive).run_round_day("2026-08-10"))
    assert result.state == "failed" and result.error_code == "HTTP_NETWORK_ERROR"
    assert len(calls) == budget.requests_used == 3
    day = store.get_day(common.DATASET_ROUNDS, "2026-08-10")
    assert day["next_retry_at"] == moment + timedelta(minutes=15)
    assert store.get_stream(common.DATASET_ROUNDS)["scan_cursor"] is None
    assert store.get_stream(common.DATASET_ROUNDS)["complete_through_us"] is None
    assert not list((tmp_path / "raw").rglob("*.json"))


def test_it03_partial_bulk_then_resume_is_idempotent(archive_run, monkeypatch):
    db, store, history = archive_run
    original = mongomock.collection.Collection.bulk_write
    calls = []

    def interrupted(collection, operations, *, ordered):
        outcome = original(collection, operations, ordered=ordered)
        calls.append(len(operations))
        if len(calls) == 1:
            raise RuntimeError("synthetic transport disconnect after write")
        return outcome

    monkeypatch.setattr(mongomock.collection.Collection, "bulk_write", interrupted)
    first = asyncio.run(history.run_kline_day("2026-08-10"))
    assert first.state == "failed"
    before = db[common.KLINES_COLLECTION].find_one({})
    assert before is not None
    second = asyncio.run(history.run_kline_day("2026-08-10"))
    assert second.state == "gap"
    assert db[common.KLINES_COLLECTION].count_documents({}) == 1
    assert db[common.KLINES_COLLECTION].find_one({}) == before
    assert second.counts["skipped"] == 1
    assert store.get_stream(common.DATASET_KLINES)["complete_through_us"] is None


def test_it03_progress_write_interruption_keeps_content_for_resume(archive_run, monkeypatch):
    db, store, history = archive_run
    write = store.write_day
    failed = []

    def interrupted(*args, **kwargs):
        write(*args, **kwargs)
        if kwargs.get("state") == "gap" and not failed:
            failed.append(True)
            raise RuntimeError("synthetic checkpoint transport disconnect")

    monkeypatch.setattr(store, "write_day", interrupted)
    with pytest.raises(RuntimeError, match="checkpoint"):
        asyncio.run(history.run_kline_day("2026-08-10"))
    before = db[common.KLINES_COLLECTION].find_one({})
    result = asyncio.run(history.run_kline_day("2026-08-10"))
    assert result.state == "gap" and result.counts["skipped"] == 1
    assert db[common.KLINES_COLLECTION].find_one({}) == before
    assert store.get_stream(common.DATASET_KLINES)["complete_through_us"] is None


def test_it03_pending_identity_http_real_etvl_and_fair_queue(db_boundary, tmp_path, monkeypatch):
    """Old due rounds outside latest pages go through identity HTTP and real CAS/readback."""
    import json
    from datetime import timedelta

    transform_tests = importlib.import_module(PREFIX + ".btc5m_history.tests.test_transforms")
    transforms = importlib.import_module(PREFIX + ".btc5m_history.transforms")
    loader_module = importlib.import_module(PREFIX + ".btc5m_history.loader")
    archive = common.RawArchive(tmp_path)
    from skills.data.unified_data.history_types import ceil_ms_to_us, from_us
    moment = from_us(ceil_ms_to_us(common.utc_now()))
    loader = loader_module.HistoryBatchLoader(db_boundary, common.DATASET_ROUNDS)
    envelope = transform_tests._round_envelope(market_status="OPEN", trading_status="OPEN")
    ref, sha = archive.store_json("2026-08-10", {"synthetic": "seed pending"})
    loader.set_context(raw_ref=ref, raw_sha256=sha, fetched_at=moment - timedelta(days=10))
    record = transforms.PredictRoundTransformer().transform_one(envelope)
    assert not asyncio.run(loader.load([record])).errors
    db_boundary[common.ROUNDS_COLLECTION].update_one({}, {"$set": {
        "next_check_at": moment - timedelta(days=2),
    }})
    second = db_boundary[common.ROUNDS_COLLECTION].find_one({}, {"_id": 0})
    second["round_id"] = "9999999"
    second["next_check_at"] = moment - timedelta(days=1)
    db_boundary[common.ROUNDS_COLLECTION].insert_one(second)
    accepted = transform_tests._round_envelope()
    category = dict(accepted["category"], markets=accepted["markets"])
    calls = []

    def transport(request, *, timeout):
        calls.append(request.full_url)
        if "/categories/" in request.full_url:
            return io.BytesIO(json.dumps({"success": True, "data": category}).encode())
        return io.BytesIO(json.dumps({"success": True, "data": [{
            "marketId": "4450895", "logs": accepted["_status_logs"]["4450895"],
        }]}).encode())

    monkeypatch.setattr(common, "_open_http", transport)
    budget = common.Budget(max_requests=2)
    tried = asyncio.run(runner.recheck_pending(
        db_boundary, budget=budget, archive=archive, now=moment,
    ))
    assert [row["round_id"] for row in tried] == ["4450895"]
    first = db_boundary[common.ROUNDS_COLLECTION].find_one({"round_id": "4450895"})
    assert first["settlement_state"] == "resolved" and first["official_outcome"] == "UP"
    assert first["first_observed_at"] == moment - timedelta(days=10)
    assert first["next_check_at"] > moment
    untouched = db_boundary[common.ROUNDS_COLLECTION].find_one({"round_id": "9999999"})
    assert untouched["next_check_at"] == moment - timedelta(days=1)
    assert len(calls) == 2 and "/categories/" in calls[0]
    assert all("/rounds" not in url for url in calls)
    import urllib.error

    authentication_calls = []

    def unauthorized(request, *, timeout):
        authentication_calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 401, "synthetic", {}, None)

    third = dict(untouched)
    third.pop("_id")
    third["round_id"] = "8888888"
    third["next_check_at"] = moment
    db_boundary[common.ROUNDS_COLLECTION].insert_one(third)
    monkeypatch.setattr(common, "_open_http", unauthorized)
    with pytest.raises(common.HistoryHTTPError, match="HTTP_UNAUTHORIZED"):
        asyncio.run(runner.recheck_pending(db_boundary, budget=common.Budget(max_requests=10),
                                           archive=archive, now=moment))
    assert len(authentication_calls) == 1
    assert db_boundary[common.ROUNDS_COLLECTION].find_one({"round_id": "9999999"})["next_check_at"] > moment
    assert db_boundary[common.ROUNDS_COLLECTION].find_one({"round_id": "8888888"})["next_check_at"] == moment


def test_it05_initialized_daily_missing_day_and_wrapper_boundary(db_boundary, tmp_path, monkeypatch):
    import json
    import shlex

    wrapper_tests = importlib.import_module(PREFIX + ".btc5m_history.tests.test_wrapper")
    wrapper_tests.test_ut21_template_executes_with_a_stub(monkeypatch, tmp_path)
    # The real shell template's exec boundary yields argv; feed it to the real CLI
    # in-process so the Mongo/HTTP replacements remain explicit and no env is read.
    forwarded = shlex.split((tmp_path / "argv.txt").read_text().splitlines()[0])[1:]
    transform_tests = importlib.import_module(PREFIX + ".btc5m_history.tests.test_transforms")
    envelope = transform_tests._round_envelope(starts_at="2026-08-11T00:00:00Z",
                                               ends_at="2026-08-11T00:05:00Z")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("BTCUSDT-1s-2026-08-10.csv",
            "1786320000000000,100,102,99,101,1,1786320000999999,101,1,1,101,0\n")
    body = buffer.getvalue()
    checksum = (hashlib.sha256(body).hexdigest() + "  BTCUSDT-1s-2026-08-10.zip\n").encode()
    calls = []

    def transport(request, *, timeout):
        url = request.full_url
        calls.append(url)
        if url.endswith(".CHECKSUM"):
            return io.BytesIO(checksum)
        if url.endswith(".zip"):
            return io.BytesIO(body)
        if "/status-logs" in url:
            payload = {"success": True, "data": [{"marketId": "4450895", "logs": []}]}
        else:
            payload = {"success": True, "data": [envelope], "cursor": str(len(calls))}
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(common, "_open_http", transport)
    monkeypatch.setattr(cli, "_api_key", lambda: None)
    monkeypatch.setattr(cli, "RawArchive", lambda: common.RawArchive(tmp_path / "raw"))
    monkeypatch.setattr(cli, "_cutoff_date", lambda: "2026-08-11")
    store = runner.IngestionStore(db_boundary)
    anchor = common.day_bounds_us("2026-08-10")[0]
    for dataset in cli.DATASETS:
        store.init_stream(dataset, ingestion_start_us=anchor)
    monkeypatch.setattr(cli, "_open_store", lambda: store)
    # Deliberately small supported request budget forces the first lane to stop.
    result = cli.main(forwarded + ["--max-requests", "8", "--report-dir", str(tmp_path)])
    assert result == common.EXIT_PARTIAL
    assert any("binance.vision" in url for url in calls)
    assert len(calls) <= 8
    assert db_boundary[common.KLINES_COLLECTION].count_documents({}) == 1
    assert store.get_day(common.DATASET_KLINES, "2026-08-10")["state"] == "gap"
    assert store.get_stream(common.DATASET_KLINES)["complete_through_us"] is None


@pytest.mark.parametrize("full_day", [False, True])
@pytest.mark.parametrize("repeated", [False, True])
def test_it03_predict_page_checkpoint_survives_restart(db_boundary, tmp_path, monkeypatch, repeated, full_day):
    import json
    from datetime import timedelta
    from urllib.parse import parse_qs, urlsplit

    factory = importlib.import_module(PREFIX + ".btc5m_history.tests.test_transforms")._round_envelope
    newest = factory(starts_at="2026-08-11T00:00:00Z", ends_at="2026-08-11T00:05:00Z", round_id=3)
    target = factory(starts_at="2026-08-10T23:55:00Z", ends_at="2026-08-11T00:00:00Z", round_id=2)
    oldest = factory(starts_at="2026-08-09T23:55:00Z", ends_at="2026-08-10T00:00:00Z", round_id=1)
    # Full-day fixture preserves complete/resume/mutation safety assertions;
    # single-round fixture now explicitly proves that a closed scan is not full coverage.
    targets = [target]
    if full_day:
        from datetime import datetime

        targets = []
        for index in reversed(range(288)):
            begin = datetime(2026, 8, 10) + timedelta(seconds=index * 300)
            targets.append(factory(starts_at=begin.isoformat() + "Z",
                                   ends_at=(begin + timedelta(seconds=300)).isoformat() + "Z",
                                   round_id=index + 10))
    first_page = [newest] + targets[:99]
    remaining = targets[99:]
    pages = [first_page] + [remaining[index:index + 100] for index in range(0, len(remaining), 100)] + [[oldest]]
    calls = []

    def transport(request, *, timeout):
        url = request.full_url
        calls.append(url)
        if "/status-logs" in url:
            payload = {"success": True, "data": [{"marketId": "4450895", "logs": [{
                "status": "RESOLVED", "timestamp": "2026-08-12T00:00:00Z",
                "transactionHash": "synthetic-log", "logIndex": 1,
            }]}]}
        else:
            after = parse_qs(urlsplit(url).query).get("after", [None])[0]
            page_index = int(after[4:]) - 1 if after else 0
            payload = {"success": True, "data": pages[page_index],
                       "cursor": (after if repeated and after else
                                  "page" + str(page_index + 2) if page_index + 1 < len(pages) else None)}
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(common, "_open_http", transport)
    store = runner.IngestionStore(db_boundary)
    lower, upper = common.day_bounds_us("2026-08-10")
    store.init_stream(common.DATASET_ROUNDS, ingestion_start_us=lower)
    archive = common.RawArchive(tmp_path)
    first_runner = runner.HistoryRunner(store, db_boundary, budget=common.Budget(max_requests=2),
                                        archive=archive)
    first = asyncio.run(first_runner.run_round_days(["2026-08-10"]))
    assert first[0].state == "pending"
    checkpoint = store.get_stream(common.DATASET_ROUNDS)
    assert checkpoint["scan_cursor"] == "page2"
    assert (checkpoint["scan_lower_us"], checkpoint["scan_upper_us"]) == (lower, upper)
    before = db_boundary[common.ROUNDS_COLLECTION].find_one({})
    assert before["round_id"] == ("297" if full_day else "2")
    assert db_boundary[common.ROUNDS_COLLECTION].count_documents({}) == min(99, len(targets))
    restarted = runner.HistoryRunner(store, db_boundary, budget=common.Budget(max_requests=8),
                                     archive=archive)
    second = asyncio.run(restarted.run_round_days(["2026-08-10"]))
    assert db_boundary[common.ROUNDS_COLLECTION].find_one({}) == before
    page_urls = [url for url in calls if "/rounds?" in url]
    assert len(page_urls) == (2 if repeated else len(pages)) and "after=page2" in page_urls[1]
    if repeated:
        assert second[0].state == "conflict"
        assert second[0].error_code == "REPEATED_CURSOR"
        assert store.get_stream(common.DATASET_ROUNDS)["scan_cursor"] == "page2"
    else:
        assert second[0].state == ("complete" if full_day else "gap")
        assert store.get_stream(common.DATASET_ROUNDS)["complete_through_us"] == (upper if full_day else None)
        manifest = json.loads(archive.read_bytes(second[0].raw_manifest_ref))
        assert manifest["closed"] and len(manifest["pages"]) == len(pages)
        assert all(page["status_refs"] for page in manifest["pages"])
        monkeypatch.setattr(common, "_open_http", lambda *args, **kwargs: pytest.fail("verify HTTP"))
        rows = list(db_boundary[common.ROUNDS_COLLECTION].find({}, {"_id": 0}))
        assert asyncio.run(cli._verify_predict_manifest(
            second[0].raw_manifest_ref, "2026-08-10", rows, archive=archive,
        ))
        corrupted = dict(rows[0], official_outcome="DOWN")
        with pytest.raises(ValueError, match="RAW_SEMANTIC_READBACK_MISMATCH"):
            asyncio.run(cli._verify_predict_manifest(
                second[0].raw_manifest_ref, "2026-08-10", [corrupted] + rows[1:], archive=archive,
            ))
        broken = dict(manifest, pages=list(reversed(manifest["pages"])))
        broken_ref, _ = archive.store_json("2026-08-10", broken)
        with pytest.raises(ValueError, match="PAGE_CHAIN_BROKEN"):
            asyncio.run(cli._verify_predict_manifest(broken_ref, "2026-08-10", rows,
                                                      archive=archive))
        monkeypatch.setattr(cli, "_open_store", lambda: store)
        monkeypatch.setattr(cli, "RawArchive", lambda: archive)
        arguments = ["verify", "--start-utc", "2026-08-10T00:00:00Z",
                     "--end-utc", "2026-08-11T00:00:00Z", "--report-dir", str(tmp_path)]
        if not full_day:
            # Simulate the old false-complete checkpoint with otherwise valid raw/content.
            store.write_day(common.DATASET_ROUNDS, "2026-08-10", state="complete",
                            content_sha256=runner._digest_of([], rows),
                            raw_manifest_ref=second[0].raw_manifest_ref)
        stored_before = list(db_boundary[common.INGESTION_COLLECTION].find({}))
        assert cli.main(arguments) == common.EXIT_PARTIAL  # price day honestly absent
        assert list(db_boundary[common.INGESTION_COLLECTION].find({})) == stored_before
        summary = json.loads((tmp_path / "summary.json").read_text())
        if not full_day:
            coverage = summary["datasets"][common.DATASET_ROUNDS + "/2026-08-10"]
            assert coverage["raw_bytes_verified"] and not coverage["complete"]
            assert coverage["counts"]["missing_nominal_slots"] == 287
            assert summary["verified_content"] == {}
            return
        assert summary["verified_content"][common.DATASET_ROUNDS + "/2026-08-10"]
        assert summary["resume_sha256"] == cli._resume_digest(summary)
        original_find = mongomock.collection.Collection.find
        finds = []

        def changing_find(collection, *args, **kwargs):
            if collection.name == common.ROUNDS_COLLECTION:
                finds.append(True)
                if len(finds) == 2:
                    collection.update_one({}, {"$set": {"label_observed_at": common.utc_now() + timedelta(days=1)}})
            return original_find(collection, *args, **kwargs)

        monkeypatch.setattr(mongomock.collection.Collection, "find", changing_find)
        assert cli.main(arguments) == common.EXIT_FAIL
        changed = json.loads((tmp_path / "summary.json").read_text())
        assert changed["verified_content"] == {}


@pytest.mark.parametrize("code", ["HTTP_UNAUTHORIZED", "HTTP_FORBIDDEN"])
def test_pending_auth_failure_keeps_real_binance_etvl_and_readback(archive_run, monkeypatch, tmp_path, code):
    """Only HTTP/Mongo boundaries are replaced; pending, CLI and price ETVL are real."""
    from datetime import timedelta

    db, store, history = archive_run
    transforms = importlib.import_module(PREFIX + ".btc5m_history.transforms")
    loader_module = importlib.import_module(PREFIX + ".btc5m_history.loader")
    factory = importlib.import_module(PREFIX + ".btc5m_history.tests.test_transforms")._round_envelope
    loader = loader_module.HistoryBatchLoader(db, common.DATASET_ROUNDS)
    ref, sha = history._archive.store_json("2026-08-10", {"synthetic": "pending seed"})
    loader.set_context(raw_ref=ref, raw_sha256=sha,
                       fetched_at=common.utc_now() - timedelta(days=10))
    pending = transforms.PredictRoundTransformer().transform_one(factory(
        market_status="OPEN", trading_status="OPEN",
    ))
    assert not asyncio.run(loader.load([pending])).errors
    db[common.ROUNDS_COLLECTION].update_one({}, {"$set": {
        "next_check_at": common.utc_now() - timedelta(days=1),
    }})
    original = db[common.ROUNDS_COLLECTION].find_one({})
    start, _ = common.day_bounds_us("2026-08-10")
    store.init_stream(common.DATASET_ROUNDS, ingestion_start_us=start)
    archive_transport = extractors.http_get
    calls = []

    def transport(url, **kwargs):
        calls.append(url)
        if "binance.vision" not in url:
            kwargs["budget"].take_request()
            raise common.HistoryHTTPError(code)
        return archive_transport(url, **kwargs)

    monkeypatch.setattr(extractors, "http_get", transport)
    monkeypatch.setattr(cli, "_open_store", lambda: store)
    monkeypatch.setattr(cli, "RawArchive", lambda: history._archive)
    monkeypatch.setattr(cli, "_cutoff_date", lambda: "2026-08-11")
    monkeypatch.setattr(cli, "_api_key", lambda: None)
    assert cli.main(["daily", "--apply", "--report-dir", str(tmp_path)]) == common.EXIT_FAIL
    assert len([url for url in calls if "binance.vision" not in url]) == 1
    assert len([url for url in calls if "binance.vision" in url]) == 2
    accepted = db[common.KLINES_COLLECTION].find_one({}, {"_id": 0})
    assert accepted and db[common.KLINES_COLLECTION].count_documents({}) == 1
    day = store.get_day(common.DATASET_KLINES, "2026-08-10")
    assert day["state"] == "gap" and day["counts"]["missing_seconds"] == 86399
    assert cli._verify_archive_manifest(day["raw_manifest_ref"], "2026-08-10",
                                        archive=history._archive, rows=[accepted])
    remaining = db[common.ROUNDS_COLLECTION].find_one({})
    assert remaining["settlement_state"] == "pending"
    assert remaining["first_observed_at"] == original["first_observed_at"]
    assert remaining["official_outcome"] is None
    assert store.get_stream(common.DATASET_KLINES)["complete_through_us"] is None


def test_fix2_full_day_pending_fill_restart_daily_and_readonly_verify(db_boundary, tmp_path, monkeypatch):
    import json
    from datetime import datetime, timedelta
    from urllib.parse import parse_qs, urlsplit
    from bson import Decimal128

    factory = importlib.import_module(PREFIX + ".btc5m_history.tests.test_transforms")._round_envelope
    loaders = importlib.import_module(PREFIX + ".btc5m_history.loader")
    transforms = importlib.import_module(PREFIX + ".btc5m_history.transforms")
    moment = [datetime(2026, 8, 12, 1, 0, 0, 999500)]
    monkeypatch.setattr(common, "utc_now", lambda: moment[0])
    monkeypatch.setattr(runner, "utc_now", lambda: moment[0])
    targets = []
    for index in reversed(range(288)):
        begin = datetime(2026, 8, 10) + timedelta(seconds=index * 300)
        targets.append(factory(starts_at=begin.isoformat() + "Z",
                               ends_at=(begin + timedelta(seconds=300)).isoformat() + "Z",
                               round_id=index + 10,
                               market_status="OPEN" if index == 0 else "RESOLVED",
                               trading_status="OPEN" if index == 0 else "RESOLVED"))
    accepted = factory(round_id=10)
    newest = factory(starts_at="2026-08-11T00:00:00Z", ends_at="2026-08-11T00:05:00Z", round_id=9999)
    oldest = factory(starts_at="2026-08-09T23:55:00Z", ends_at="2026-08-10T00:00:00Z", round_id=9998)
    entries = [newest] + targets + [oldest]
    pages = [entries[offset:offset + 100] for offset in range(0, len(entries), 100)]
    calls = []

    def transport(request, *, timeout):
        url = request.full_url
        calls.append(url)
        if "/categories/" in url:
            payload = {"success": True, "data": dict(accepted["category"], markets=accepted["markets"])}
        elif "/status-logs" in url:
            payload = {"success": True, "data": [{"marketId": "4450895", "logs": accepted["_status_logs"]["4450895"]}]}
        else:
            page_index = int(parse_qs(urlsplit(url).query).get("after", ["0"])[0])
            payload = {"success": True, "data": pages[page_index],
                       "cursor": str(page_index + 1) if page_index + 1 < len(pages) else None}
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(common, "_open_http", transport)
    db = db_boundary
    store = runner.IngestionStore(db)
    start, stop = common.day_bounds_us("2026-08-10")
    store.init_stream(common.DATASET_ROUNDS, ingestion_start_us=start)
    archive = common.RawArchive(tmp_path / "raw")
    history = runner.HistoryRunner(store, db, budget=common.Budget(), archive=archive)
    first = asyncio.run(history.run_round_day("2026-08-10"))
    assert first.state == "pending" and first.counts["pending"] == 1
    row = db[common.ROUNDS_COLLECTION].find_one({"round_id": "10"})
    assert row["next_check_at"] is not None
    original_raw = archive.read_bytes(row["raw_ref"])
    assert asyncio.run(runner.recheck_pending(db, budget=common.Budget(), archive=archive, now=moment[0])) == []
    moment[0] += timedelta(days=2)
    before_requests = len(calls)
    tried = asyncio.run(runner.recheck_pending(db, budget=common.Budget(), archive=archive, now=moment[0]))
    assert len(tried) == 1 and len(calls) == before_requests + 2
    assert "/categories/" in calls[-2] and "/status-logs" in calls[-1]
    filled = db[common.ROUNDS_COLLECTION].find_one({"round_id": "10"})
    assert filled["settlement_state"] == "resolved" and filled["raw_history"][0]["raw_ref"] == row["raw_ref"]
    assert archive.read_bytes(row["raw_ref"]) == original_raw
    day = store.get_day(common.DATASET_ROUNDS, "2026-08-10")
    assert day["state"] == "complete" and day["counts"]["resolved"] == 288
    assert day["content_sha256"] == runner._digest_of([], list(db[common.ROUNDS_COLLECTION].find({})))
    assert store.get_stream(common.DATASET_ROUNDS)["complete_through_us"] == stop
    assert asyncio.run(runner.recheck_pending(db, budget=common.Budget(), archive=archive, now=moment[0])) == []
    calls_before = len(calls)
    restarted_store = runner.IngestionStore(db)
    restarted = runner.HistoryRunner(restarted_store, db, budget=common.Budget(), archive=common.RawArchive(tmp_path / "raw"))
    assert asyncio.run(restarted.run_round_day("2026-08-10")).state == "complete"
    assert len(calls) == calls_before
    assert db[common.ROUNDS_COLLECTION].find_one({"round_id": "10"}) == filled
    loader = loaders.HistoryBatchLoader(db, common.DATASET_ROUNDS)
    contradictory = dict(transforms.PredictRoundTransformer().transform_one(accepted), end_price=Decimal128("999"))
    assert asyncio.run(loader.load([contradictory])).errors
    assert db[common.ROUNDS_COLLECTION].find_one({"round_id": "10"}) == filled
    rows = list(db[common.ROUNDS_COLLECTION].find({}, {"_id": 0}))
    assert asyncio.run(cli._verify_predict_manifest(first.raw_manifest_ref, "2026-08-10", rows, archive=archive))
    monkeypatch.setattr(cli, "_open_store", lambda: restarted_store)
    monkeypatch.setattr(cli, "RawArchive", lambda: archive)
    monkeypatch.setattr(cli, "_api_key", lambda: None)
    monkeypatch.setattr(cli, "_cutoff_date", lambda: "2026-08-11")
    store.init_stream(common.DATASET_KLINES, ingestion_start_us=start)

    def unavailable(url, **kwargs):
        kwargs["budget"].take_request()
        assert "binance.vision" in url
        raise common.HistoryHTTPError("ARCHIVE_NOT_PUBLISHED_OR_MISSING")

    monkeypatch.setattr(extractors, "http_get", unavailable)
    for _ in range(2):
        assert cli.main(["daily", "--apply", "--max-days-per-source", "1"]) in (common.EXIT_FAIL, common.EXIT_PARTIAL)
        assert store.get_day(common.DATASET_ROUNDS, "2026-08-10")["state"] == "complete"
    before = {name: list(db[name].find({})) for name in db.list_collection_names()}
    monkeypatch.setattr(common, "_open_http", lambda *a, **k: pytest.fail("verify HTTP"))
    monkeypatch.setattr(mongomock.collection.Collection, "create_index", lambda *a, **k: pytest.fail("verify DDL"))
    assert cli.main(["verify", "--start-utc", "2026-08-10T00:00:00Z", "--end-utc", "2026-08-11T00:00:00Z",
                     "--report-dir", str(tmp_path / "verify")]) == common.EXIT_PARTIAL
    summary = json.loads((tmp_path / "verify" / "summary.json").read_text())
    assert summary["datasets"][common.DATASET_ROUNDS + "/2026-08-10"]["complete"]
    assert before == {name: list(db[name].find({})) for name in before}
    tampered = dict(filled, end_price=Decimal128("999"))
    tampered["record_sha256"] = loaders._record_hash(tampered, common.DATASET_ROUNDS)
    with pytest.raises(common.HistoryHTTPError, match="RAW_FILL_CONFLICT"):
        asyncio.run(cli._verify_predict_manifest(first.raw_manifest_ref, "2026-08-10",
                    [tampered if record["round_id"] == "10" else record for record in rows], archive=archive))


@pytest.mark.parametrize("microseconds", [1234, 999500])
def test_fix2_actual_fetch_clock_to_reader_availability(archive_run, monkeypatch, microseconds):
    from datetime import datetime, timedelta, timezone
    from skills.data.unified_data.history_reader import Btc5mHistoryReader
    from skills.data.unified_data.history_types import ceil_ms_to_us, from_us

    db, store, history = archive_run
    actual = datetime(2026, 11, 11, 4, 0, 0, microseconds)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return actual.replace(tzinfo=tz)

    monkeypatch.setattr(common, "datetime", Clock)
    monkeypatch.setattr(runner, "utc_now", common.utc_now)
    from bson import Decimal128

    result = asyncio.run(history.run_kline_day("2026-08-10"))
    assert result.counts["inserted"] == 1
    assert result.counts["coverage_ratio"] == Decimal128("0.000012")
    assert store.get_day(common.DATASET_KLINES, "2026-08-10")["counts"]["coverage_ratio"] == Decimal128("0.000012")
    loaders = importlib.import_module(PREFIX + ".btc5m_history.loader")
    transforms = importlib.import_module(PREFIX + ".btc5m_history.transforms")
    factory = importlib.import_module(PREFIX + ".btc5m_history.tests.test_transforms")._round_envelope
    loader = loaders.HistoryBatchLoader(db, common.DATASET_ROUNDS)
    loader.set_context(fetched_at=common.utc_now())
    assert not asyncio.run(loader.load([transforms.PredictRoundTransformer().transform_one(factory())])).errors
    rounded = from_us(ceil_ms_to_us(actual))
    for name in (common.ROUNDS_COLLECTION, common.KLINES_COLLECTION):
        row = db[name].find_one({})
        assert row["fetched_at"] == row["first_observed_at"] == rounded >= actual
    reader = Btc5mHistoryReader(db)
    kwargs = {"start_utc": "2026-08-10T00:00:00Z", "end_utc": "2026-08-11T00:00:00Z"}
    before = reader.read(**kwargs, as_of_utc=(actual - timedelta(microseconds=1)).replace(tzinfo=timezone.utc))
    assert list(before.iter_features()) == list(before.iter_labels()) == list(before.iter_round_metadata()) == []
    after = reader.read(**kwargs, as_of_utc=rounded.replace(tzinfo=timezone.utc))
    assert len(list(after.iter_features())) == 2  # one candle plus strike
    assert len(list(after.iter_labels())) == len(list(after.iter_round_metadata())) == 1
    assert after.verify_consumed()


def test_fix3_partial_price_fill_then_resolution_replays_old_page(db_boundary, tmp_path, monkeypatch):
    """A closed single-slot scan stays a gap through both legal fills and restart."""
    import copy
    import json
    from datetime import datetime, timedelta
    from bson import Decimal128

    factory = importlib.import_module(PREFIX + ".btc5m_history.tests.test_transforms")._round_envelope
    loaders = importlib.import_module(PREFIX + ".btc5m_history.loader")
    transforms = importlib.import_module(PREFIX + ".btc5m_history.transforms")
    clock = [datetime(2026, 11, 11)]
    monkeypatch.setattr(common, "utc_now", lambda: clock[0])
    monkeypatch.setattr(runner, "utc_now", lambda: clock[0])
    pending = factory(market_status="OPEN", trading_status="OPEN")
    pending["category"]["variantDetails"]["endPrice"] = None
    pending["_status_logs"] = {"4450895": []}
    partial = copy.deepcopy(pending)
    partial["category"]["variantDetails"]["endPrice"] = "101.5"
    final = factory()
    response = [partial]
    newest = factory(starts_at="2026-08-11T00:00:00Z", ends_at="2026-08-11T00:05:00Z", round_id=3)
    oldest = factory(starts_at="2026-08-09T23:55:00Z", ends_at="2026-08-10T00:00:00Z", round_id=1)
    calls = []

    def transport(request, *, timeout):
        url = request.full_url
        calls.append(url)
        if "/categories/" in url:
            payload = dict(response[0]["category"], markets=response[0]["markets"])
        elif "/status-logs" in url:
            payload = [{"marketId": "4450895", "logs": response[0]["_status_logs"]["4450895"]}]
        else:
            payload = [newest, pending, oldest]
        return io.BytesIO(json.dumps({"success": True, "data": payload, "cursor": None}).encode())

    monkeypatch.setattr(common, "_open_http", transport)
    db = db_boundary
    archive = common.RawArchive(tmp_path / "raw")
    store = runner.IngestionStore(db)
    begin, _ = common.day_bounds_us("2026-08-10")
    store.init_stream(common.DATASET_ROUNDS, ingestion_start_us=begin)
    history = runner.HistoryRunner(store, db, budget=common.Budget(), archive=archive)
    first = asyncio.run(history.run_round_day("2026-08-10"))
    original = db[common.ROUNDS_COLLECTION].find_one({})
    original_bytes = archive.read_bytes(original["raw_ref"])
    for expected in ("pending", "resolved"):
        clock[0] += timedelta(days=8)
        before_calls = len(calls)
        assert len(asyncio.run(runner.recheck_pending(db, budget=common.Budget(), archive=archive,
                                                     now=clock[0]))) == 1
        assert len(calls) == before_calls + 2
        row = db[common.ROUNDS_COLLECTION].find_one({})
        assert row["settlement_state"] == expected and row["end_price"] == Decimal128("101.5")
        assert row["first_observed_at"] == original["first_observed_at"]
        assert row["start_price_observed_at"] == original["start_price_observed_at"]
        assert len(row["raw_history"]) == (1 if expected == "pending" else 2)
        assert (row["resolution_evidence"] is None) == (expected == "pending")
        assert archive.read_bytes(original["raw_ref"]) == original_bytes
        rows = list(db[common.ROUNDS_COLLECTION].find({}, {"_id": 0}))
        assert asyncio.run(cli._verify_predict_manifest(first.raw_manifest_ref, "2026-08-10", rows, archive=archive))
        restarted_store = runner.IngestionStore(db)
        restarted = runner.HistoryRunner(restarted_store, db, budget=common.Budget(),
                                         archive=common.RawArchive(tmp_path / "raw"))
        assert asyncio.run(restarted.run_round_day("2026-08-10")).state == "gap"
        assert len(calls) == before_calls + 2
        assert db[common.ROUNDS_COLLECTION].find_one({}) == row
        assert restarted_store.get_stream(common.DATASET_ROUNDS)["complete_through_us"] is None
        assert restarted_store.get_day(common.DATASET_ROUNDS, "2026-08-10")["counts"]["missing_nominal_slots"] == 287
        response[0] = final
    writer = loaders.HistoryBatchLoader(db, common.DATASET_ROUNDS)
    contradiction = dict(transforms.PredictRoundTransformer().transform_one(final), end_price=Decimal128("999"))
    assert asyncio.run(writer.load([contradiction])).errors
    assert db[common.ROUNDS_COLLECTION].find_one({}) == row
    assert asyncio.run(runner.recheck_pending(db, budget=common.Budget(), archive=archive, now=clock[0])) == []


@pytest.mark.parametrize("inject_due_now", [False, True])
@pytest.mark.parametrize("missing_start", [False, True])
def test_fix3_pending_response_clock_controls_strike_and_label(
    db_boundary, tmp_path, monkeypatch, inject_due_now, missing_start,
):
    """Two delayed responses establish each new fact, never queue-selection time."""
    import json
    from datetime import datetime, timedelta, timezone
    from skills.data.unified_data.history_reader import Btc5mHistoryReader
    from skills.data.unified_data.history_types import ceil_ms_to_us, from_us

    factory = importlib.import_module(PREFIX + ".btc5m_history.tests.test_transforms")._round_envelope
    loaders = importlib.import_module(PREFIX + ".btc5m_history.loader")
    transforms = importlib.import_module(PREFIX + ".btc5m_history.transforms")
    start = datetime(2026, 11, 11, 4, 0, 0, 999500)
    clock = [start]
    monkeypatch.setattr(common, "utc_now", lambda: clock[0])
    monkeypatch.setattr(runner, "utc_now", lambda: clock[0])
    pending = factory(market_status="OPEN", trading_status="OPEN")
    pending["category"]["variantDetails"]["endPrice"] = None
    if missing_start:
        pending["category"]["variantDetails"]["startPrice"] = None
    writer = loaders.HistoryBatchLoader(db_boundary, common.DATASET_ROUNDS)
    writer.set_context(fetched_at=start - timedelta(days=2))
    assert not asyncio.run(writer.load([transforms.PredictRoundTransformer().transform_one(pending)])).errors
    original = db_boundary[common.ROUNDS_COLLECTION].find_one({})
    partial = factory(market_status="OPEN", trading_status="OPEN")
    partial["category"]["variantDetails"]["endPrice"] = None
    partial["_status_logs"] = {"4450895": []}
    response = [partial if missing_start else factory()]
    calls = []

    def transport(request, *, timeout):
        calls.append(request.full_url)
        clock[0] += timedelta(seconds=10)
        payload = (dict(response[0]["category"], markets=response[0]["markets"])
                   if "/categories/" in request.full_url else
                   [{"marketId": "4450895", "logs": response[0]["_status_logs"]["4450895"]}])
        return io.BytesIO(json.dumps({"success": True, "data": payload}).encode())

    monkeypatch.setattr(common, "_open_http", transport)
    archive = common.RawArchive(tmp_path / "raw")
    reader = Btc5mHistoryReader(db_boundary)

    def read(at, mode="observed"):
        return reader.read("2026-08-10T00:00:00Z", "2026-08-11T00:00:00Z",
                           as_of_utc=at.replace(tzinfo=timezone.utc), availability_mode=mode)

    strike_time = original.get("start_price_observed_at")
    for phase in (("strike", "label") if missing_start else ("label",)):
        selection = clock[0]
        kwargs = {"now": selection} if inject_due_now else {}
        assert len(asyncio.run(runner.recheck_pending(db_boundary, budget=common.Budget(),
                                                     archive=archive, **kwargs))) == 1
        row = db_boundary[common.ROUNDS_COLLECTION].find_one({})
        rounded = from_us(ceil_ms_to_us(clock[0]))
        field = "start_price_observed_at" if phase == "strike" else "label_observed_at"
        assert row[field] == rounded >= clock[0]
        assert row["first_observed_at"] == original["first_observed_at"]
        assert row["fetched_at"] == original["fetched_at"]
        assert row["starts_at_us"] == original["starts_at_us"]
        assert row["ends_at_us"] == original["ends_at_us"]
        if phase == "label":
            assert row["start_price_observed_at"] == strike_time
            assert row["resolved_at_us"] == transforms.PredictRoundTransformer().transform_one(factory())["resolved_at_us"]
        for before in (selection + timedelta(seconds=1), selection + timedelta(seconds=10),
                       clock[0], rounded - timedelta(microseconds=1)):
            window = read(before)
            if phase == "strike":
                assert not list(window.iter_features())
            assert not list(window.iter_labels())
        after = read(rounded)
        assert len(list(after.iter_features())) == 1
        assert len(list(after.iter_labels())) == (1 if phase == "label" else 0)
        proxy = read(selection, "event-time-proxy")
        assert len(list(proxy.iter_features())) == 1
        assert len(list(proxy.iter_labels())) == (1 if phase == "label" else 0)
        if phase == "strike":
            strike_time = row[field]
            response[0] = factory()
            clock[0] = row["next_check_at"] + timedelta(microseconds=999500)
    before_replay = db_boundary[common.ROUNDS_COLLECTION].find_one({})
    writer.set_context(fetched_at=clock[0] + timedelta(days=1))
    assert not asyncio.run(writer.load([transforms.PredictRoundTransformer().transform_one(factory())])).errors
    assert db_boundary[common.ROUNDS_COLLECTION].find_one({}) == before_replay
    assert len(calls) == (4 if missing_start else 2)


# This fixture always has a checked-in public excerpt. The local full-archive
# evidence run injects both immutable bodies through pytest parametrization.
shape_samples = importlib.import_module(PREFIX + ".btc5m_history.tests.test_extractors")
shape_wire_bytes = shape_samples.shape_wire_bytes


def test_shape_fix_exact_wire_day_replay(db_boundary, tmp_path, monkeypatch, shape_wire_bytes):
    """Unmodified full wire/excerpt -> real day ETVL; partial day stays partial."""
    import json
    from decimal import Decimal
    from bson import Decimal128

    page_body, status_body = shape_wire_bytes
    document = json.loads(page_body, parse_float=Decimal)
    originals = document["data"]
    calls = []

    def transport(request, *, timeout):
        url = request.full_url
        calls.append(url)
        if "/status-logs" in url:
            return io.BytesIO(status_body)
        if "&after=" in url:
            # Explicit controlled terminal empty container, not official pagination.
            return io.BytesIO(b'{"success":true,"data":[],"cursor":null}')
        return io.BytesIO(page_body)

    monkeypatch.setattr(common, "_open_http", transport)
    archive = common.RawArchive(tmp_path / "raw")
    store = runner.IngestionStore(db_boundary)
    begin, _ = common.day_bounds_us("2026-11-11")
    store.init_stream(common.DATASET_ROUNDS, ingestion_start_us=begin)
    history = runner.HistoryRunner(store, db_boundary, budget=common.Budget(max_requests=2), archive=archive)
    first = asyncio.run(history.run_round_day("2026-11-11"))
    assert first.state == "pending" and first.counts["inserted"] == len(originals)
    assert first.counts["stored_rounds"] == first.counts["resolved"] == len(originals)
    assert first.counts["missing_nominal_slots"] == 288 - len(originals)
    assert first.content_sha256 is None
    rows = list(db_boundary[common.ROUNDS_COLLECTION].find({}, {"_id": 0}))
    by_id = {row["round_id"]: row for row in rows}
    loaders = importlib.import_module(PREFIX + ".btc5m_history.loader")
    transforms = importlib.import_module(PREFIX + ".btc5m_history.transforms")
    manifest = json.loads(archive.read_bytes(first.raw_manifest_ref))
    assert not manifest["closed"] and len(manifest["pages"]) == 1
    raw_page = manifest["pages"][0]
    replayed = runner.read_round_page(archive, raw_page)
    assert len(replayed) == len(originals)
    for original, envelope in zip(originals, replayed):
        row = by_id[str(original["id"])]
        assert row["market_id"] == str(original["markets"][0]["id"])
        assert row["category_status"] == original["status"]
        assert row["market_status"] == original["markets"][0]["status"]
        assert row["start_price"] == Decimal128(original["variantData"]["startPrice"])
        assert row["end_price"] == Decimal128(original["variantData"]["endPrice"])
        assert row["raw_sha256"] == hashlib.sha256(page_body).hexdigest()
        assert archive.read_bytes(row["raw_ref"]) == page_body
        assert row["resolution_evidence"]["raw_sha256"] == hashlib.sha256(status_body).hexdigest()
        assert row["record_sha256"] == loaders._record_hash(transforms.PredictRoundTransformer().transform_one(envelope), common.DATASET_ROUNDS)
    before = list(db_boundary[common.ROUNDS_COLLECTION].find({}))
    restarted = runner.HistoryRunner(runner.IngestionStore(db_boundary), db_boundary,
        budget=common.Budget(max_requests=2), archive=common.RawArchive(tmp_path / "raw"))
    second = asyncio.run(restarted.run_round_day("2026-11-11"))
    assert second.state == "pending" and second.counts["skipped"] == len(originals)
    assert list(db_boundary[common.ROUNDS_COLLECTION].find({})) == before
    assert len(calls) == 3 and "&after=" in calls[-1]
    assert store.get_stream(common.DATASET_ROUNDS)["complete_through_us"] is None
    monkeypatch.setattr(common, "_open_http", lambda *a, **k: pytest.fail("verify HTTP"))
    monkeypatch.setattr(cli, "_open_store", lambda: store)
    monkeypatch.setattr(cli, "RawArchive", lambda: archive)
    snapshot = {name: list(db_boundary[name].find({})) for name in db_boundary.list_collection_names()}
    assert cli.main(["verify", "--start-utc", "2026-11-11T00:00:00Z", "--end-utc", "2026-11-12T00:00:00Z",
                     "--report-dir", str(tmp_path / "verify")]) == common.EXIT_PARTIAL
    summary = json.loads((tmp_path / "verify/summary.json").read_text())
    assert not summary["datasets"][common.DATASET_ROUNDS + "/2026-11-11"]["complete"]
    assert snapshot == {name: list(db_boundary[name].find({})) for name in snapshot}
    print("SHAPE_EXACT_RESULT", json.dumps({"records": len(rows), "day": second.state,
        "missing_slots": first.counts["missing_nominal_slots"], "page_sha256": hashlib.sha256(page_body).hexdigest(),
        "status_sha256": hashlib.sha256(status_body).hexdigest(), "business_sha256": runner._digest_of([], rows),
        "readonly_exit": common.EXIT_PARTIAL, "network_requests": 0, "production_db_access": False}, sort_keys=True))


def test_shape_fix_controlled_pagination_restart_verify(db_boundary, tmp_path, monkeypatch, shape_wire_bytes):
    """Synthetic page containers/boundary sentinels, untouched public records inside."""
    import json
    from urllib.parse import parse_qs, urlsplit
    page_body, status_body = shape_wire_bytes
    from decimal import Decimal
    targets = json.loads(page_body, parse_float=Decimal)["data"]
    statuses = json.loads(status_body)["data"]
    factory = importlib.import_module(PREFIX + ".btc5m_history.tests.test_transforms")._round_envelope
    newest = factory(starts_at="2026-11-12T00:00:00Z", ends_at="2026-11-12T00:05:00Z", round_id=9999998)
    oldest = factory(starts_at="2026-11-10T23:55:00Z", ends_at="2026-11-11T00:00:00Z", round_id=9999997)
    sentinels = [dict(row["category"], markets=row["markets"]) for row in (newest, oldest)]
    split = max(1, len(targets) // 2)
    pages = [[sentinels[0]] + targets[:split], targets[split:] + [sentinels[1]]]
    calls = []

    def transport(request, *, timeout):
        url = request.full_url
        calls.append(url)
        if "/status-logs" in url:
            ids = set(parse_qs(urlsplit(url).query)["ids"][0].split(","))
            payload = {"success": True, "data": [row for row in statuses if str(row["marketId"]) in ids]}
        else:
            index = int(parse_qs(urlsplit(url).query).get("after", ["0"])[0])
            payload = {"success": True, "data": pages[index], "cursor": "1" if index == 0 else None}
        return io.BytesIO(shape_samples.shape_json_bytes(payload))

    monkeypatch.setattr(common, "_open_http", transport)
    archive = common.RawArchive(tmp_path / "raw")
    store = runner.IngestionStore(db_boundary)
    begin, _ = common.day_bounds_us("2026-11-11")
    store.init_stream(common.DATASET_ROUNDS, ingestion_start_us=begin)
    first = asyncio.run(runner.HistoryRunner(store, db_boundary, budget=common.Budget(max_requests=2),
                                             archive=archive).run_round_day("2026-11-11"))
    assert first.state == "pending" and first.counts["inserted"] == split
    assert store.get_stream(common.DATASET_ROUNDS)["scan_cursor"] == "1"
    before = list(db_boundary[common.ROUNDS_COLLECTION].find({}))
    restarted = runner.HistoryRunner(runner.IngestionStore(db_boundary), db_boundary,
        budget=common.Budget(), archive=common.RawArchive(tmp_path / "raw"))
    second = asyncio.run(restarted.run_round_day("2026-11-11"))
    assert second.state == "gap" and second.counts["closed"]
    assert second.counts["stored_rounds"] == len(targets)
    assert second.counts["missing_nominal_slots"] == 288 - len(targets)
    assert second.counts["skipped"] == split
    assert all(db_boundary[common.ROUNDS_COLLECTION].find_one({"_id": row["_id"]}) == row for row in before)
    assert len(calls) == 4 and "after=1" in calls[2]
    rows = list(db_boundary[common.ROUNDS_COLLECTION].find({}, {"_id": 0}))
    monkeypatch.setattr(common, "_open_http", lambda *a, **k: pytest.fail("replay HTTP"))
    assert asyncio.run(cli._verify_predict_manifest(second.raw_manifest_ref, "2026-11-11", rows, archive=archive))
    again = asyncio.run(restarted.run_round_day("2026-11-11"))
    assert again.state == "gap" and again.counts["skipped"] == len(targets)
    assert store.get_stream(common.DATASET_ROUNDS)["complete_through_us"] is None
    assert second.content_sha256 is None
    monkeypatch.setattr(cli, "_open_store", lambda: runner.IngestionStore(db_boundary))
    monkeypatch.setattr(cli, "RawArchive", lambda: common.RawArchive(tmp_path / "raw"))
    monkeypatch.setattr(mongomock.collection.Collection, "create_index", lambda *a, **k: pytest.fail("verify DDL"))
    snapshot = {name: list(db_boundary[name].find({})) for name in db_boundary.list_collection_names()}
    assert cli.main(["verify", "--start-utc", "2026-11-11T00:00:00Z", "--end-utc", "2026-11-12T00:00:00Z",
                     "--report-dir", str(tmp_path / "verify")]) == common.EXIT_PARTIAL
    summary = json.loads((tmp_path / "verify/summary.json").read_text())
    coverage = summary["datasets"][common.DATASET_ROUNDS + "/2026-11-11"]
    assert coverage["raw_bytes_verified"] and not coverage["complete"]
    assert coverage["counts"]["missing_nominal_slots"] == 288 - len(targets)
    assert snapshot == {name: list(db_boundary[name].find({})) for name in snapshot}
    manifest = json.loads(archive.read_bytes(second.raw_manifest_ref))
    broken, _ = archive.store_json("2026-11-11", dict(manifest, pages=list(reversed(manifest["pages"]))))
    with pytest.raises(ValueError, match="PAGE_CHAIN_BROKEN"):
        asyncio.run(cli._verify_predict_manifest(broken, "2026-11-11", rows, archive=archive))
    print("SHAPE_CONTAINER_RESULT", len(rows), runner._digest_of([], rows), second.state)
