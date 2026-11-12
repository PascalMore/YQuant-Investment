"""BTC5m 历史 CLI 测试 — 03-018 UT15 / UT20–UT22。

覆盖：纯 plan 不写库、不初始化；未初始化 → 20；参数错误 → 20；
重入 / 锁 BUSY；secret 不出现在 stdout / stderr。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import mongomock
import pytest

_cli = importlib.import_module(
    "skills.data.data-pipeline.scripts.run_btc5m_history"
)
_common = importlib.import_module(
    "skills.data.data-pipeline.scripts.btc5m_history.common"
)
_runner = importlib.import_module(
    "skills.data.data-pipeline.scripts.btc5m_history.runner"
)

main = _cli.main
EXIT_FAIL = _common.EXIT_FAIL
EXIT_BUSY = _common.EXIT_BUSY
EXIT_OK = _common.EXIT_OK


@pytest.fixture(autouse=True)
def synthetic_credentials(monkeypatch):
    """Never inspect real process credentials in engineering tests."""
    monkeypatch.setenv("PM_PREDICT_API_KEY", "synthetic-cli-key")
    monkeypatch.delenv("PM_PREDICT_API_KEY_FILE", raising=False)


@pytest.fixture()
def patched_store(monkeypatch) -> mongomock.MongoClient:
    client = mongomock.MongoClient()
    store = _runner.IngestionStore(client["yquant-data"])
    monkeypatch.setattr(_cli, "_open_store", lambda: store)
    return client


def test_ut20_plan_does_not_write(patched_store, tmp_path, capsys) -> None:
    exit_code = main(
        [
            "plan",
            "--start-utc",
            "2026-08-10T00:00:00Z",
            "--end-utc",
            "2026-11-10T00:00:00Z",
            "--report-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == EXIT_OK
    assert patched_store["yquant-data"].list_collection_names() == []
    captured = capsys.readouterr()
    assert "plan only" in captured.out
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["mode"] == "plan"
    assert summary["note"].startswith("plan only")


def test_ut20_backfill_without_apply_does_not_write(patched_store, tmp_path) -> None:
    exit_code = main(
        [
            "backfill",
            "--start-utc",
            "2026-08-10T00:00:00Z",
            "--end-utc",
            "2026-11-10T00:00:00Z",
            "--report-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == EXIT_OK
    assert patched_store["yquant-data"].list_collection_names() == []


def test_ut20_invalid_parameters_exit_20(patched_store, capsys) -> None:
    exit_code = main(["backfill", "--start-utc", "not-a-time", "--end-utc", "x"])
    assert exit_code == EXIT_FAIL
    assert "EXIT_FAIL" in capsys.readouterr().err


def test_ut20_naive_timestamp_is_rejected(patched_store) -> None:
    exit_code = main(
        [
            "backfill",
            "--start-utc",
            "2026-08-10T00:00:00",
            "--end-utc",
            "2026-11-10T00:00:00Z",
        ]
    )
    assert exit_code == EXIT_FAIL


def test_ut20_daily_day_budget_is_capped(patched_store) -> None:
    exit_code = main(["daily", "--max-days-per-source", "30"])
    assert exit_code == EXIT_FAIL


def test_ut20_uninitialised_daily_reports_not_initialized(
    patched_store, monkeypatch, capsys
) -> None:
    exit_code = main(["daily", "--apply"])
    assert exit_code == EXIT_FAIL
    assert "NOT_INITIALIZED" in capsys.readouterr().err


def test_ut15_busy_lock_exits_30(patched_store, monkeypatch, capsys) -> None:
    from scripts.unified_data import ud_lock

    def _busy(*args, **kwargs):
        raise ud_lock.UDLockBusy("held")

    monkeypatch.setattr(ud_lock, "acquire_ud_lock", _busy)
    exit_code = main(
        [
            "backfill",
            "--start-utc",
            "2026-08-10T00:00:00Z",
            "--end-utc",
            "2026-11-10T00:00:00Z",
            "--apply",
        ]
    )
    assert exit_code == EXIT_BUSY
    assert "EXIT_BUSY" in capsys.readouterr().err


def test_ut22_secret_is_not_printed(patched_store, monkeypatch, capsys) -> None:
    secret = "pm-secret-token-value"

    def _explode(*args, **kwargs):
        raise RuntimeError(f"auth failed with token {secret}")

    monkeypatch.setattr(_cli, "_open_store", _explode)
    exit_code = main(["plan"])
    captured = capsys.readouterr()
    assert exit_code == EXIT_FAIL
    assert secret not in captured.out
    assert secret not in captured.err


def test_ut20_report_dir_is_inside_the_project(tmp_path) -> None:
    """``--report-dir`` 只接受项目主题 evidence 内的路径。"""
    parser = _cli.build_parser()
    args = parser.parse_args(
        ["plan", "--report-dir", "data/reports/2026-11-11-yquant-data-history/evidence/implement"]
    )
    assert args.report_dir.startswith("data/reports/")


def test_ut15_busy_precedes_database_open(patched_store, monkeypatch) -> None:
    from scripts.unified_data import ud_lock

    def busy():
        raise ud_lock.UDLockBusy("held")

    def forbidden():
        pytest.fail("BUSY must not open a database")

    monkeypatch.setattr(ud_lock, "acquire_ud_lock", busy)
    monkeypatch.setattr(_cli, "_open_store", forbidden)
    assert main([
        "backfill", "--start-utc", _cli.DEFAULT_START_UTC,
        "--end-utc", _cli.DEFAULT_END_UTC, "--apply",
    ]) == EXIT_BUSY


def test_ut20_invalid_window_precedes_database_open(monkeypatch) -> None:
    def forbidden():
        pytest.fail("invalid target must not open a database")

    monkeypatch.setattr(_cli, "_open_store", forbidden)
    assert main(["plan", "--start-utc", "bad", "--end-utc", "bad"]) == EXIT_FAIL
    assert main([
        "backfill", "--start-utc", "2026-08-11T00:00:00Z",
        "--end-utc", _cli.DEFAULT_END_UTC, "--apply",
    ]) == EXIT_FAIL
    assert main([
        "verify", "--start-utc", "2026-08-10T08:00:00+08:00",
        "--end-utc", _cli.DEFAULT_END_UTC,
    ]) == EXIT_FAIL


def test_ut20_raw_suffix_does_not_bypass_digest(tmp_path) -> None:
    raw = tmp_path / ("0" * 64 + ".json")
    raw.write_bytes(b"different bytes")
    assert _cli._verify_raw(str(raw)) is False


def test_ut20_verify_empty_complete_checkpoint_is_not_content(patched_store) -> None:
    db = patched_store["yquant-data"]
    store = _runner.IngestionStore(db)
    for dataset in _cli.DATASETS:
        store.write_day(dataset, "2026-08-10", state="complete", content_sha256="a" * 64)
    before = list(db[_common.INGESTION_COLLECTION].find({}))
    assert main([
        "verify", "--start-utc", "2026-08-10T00:00:00Z",
        "--end-utc", "2026-08-11T00:00:00Z",
    ]) == _common.EXIT_PARTIAL
    assert list(db[_common.INGESTION_COLLECTION].find({})) == before


def test_ut20_verify_resume_target_rejected_before_database(monkeypatch, tmp_path) -> None:
    resume = tmp_path / "summary.json"
    resume.write_text(json.dumps({"window": {"start_utc": "other"}}))

    def forbidden():
        pytest.fail("mismatched resume must not open DB")

    monkeypatch.setattr(_cli, "_open_store", forbidden)
    assert main([
        "verify", "--start-utc", "2026-08-10T00:00:00Z",
        "--end-utc", "2026-08-11T00:00:00Z", "--resume-report", str(resume),
    ]) == EXIT_FAIL


def test_ut20_direct_file_entry_reaches_validation_without_io() -> None:
    import subprocess
    import sys

    result = subprocess.run([
        sys.executable, str(Path(_cli.__file__).resolve()), "backfill",
        "--start-utc", "bad", "--end-utc", "bad",
    ], capture_output=True, text=True, timeout=20)
    assert result.returncode == EXIT_FAIL
    assert "EXIT_FAIL" in result.stderr
    assert "ImportError" not in result.stderr


def test_ut15_lock_is_shared_and_non_blocking(tmp_path) -> None:
    from scripts.unified_data.ud_lock import UDLockBusy, acquire_ud_lock

    path = tmp_path / "test.lock"
    with acquire_ud_lock(path):
        with pytest.raises(UDLockBusy):
            with acquire_ud_lock(path):
                pass
    # 释放后可再次获取
    with acquire_ud_lock(path):
        pass


@pytest.mark.parametrize("code", ["HTTP_UNAUTHORIZED", "HTTP_FORBIDDEN"])
def test_pending_auth_failure_stops_predict_but_attempts_binance(patched_store, monkeypatch, code):
    store = _runner.IngestionStore(patched_store["yquant-data"])
    anchor = _common.day_bounds_us("2026-08-10")[0]
    for dataset in _cli.DATASETS:
        store.init_stream(dataset, ingestion_start_us=anchor)
    monkeypatch.setattr(_cli, "_cutoff_date", lambda: "2026-08-11")
    monkeypatch.setattr(_cli, "_api_key", lambda: None)

    async def unauthorized(*args, **kwargs):
        raise _common.HistoryHTTPError(code)

    async def no_predict(*args, **kwargs):
        pytest.fail("Predict must stop after authentication failure")

    calls = []

    async def kline(self, day):
        self._budget.take_request()
        calls.append(day)
        return _runner.DayResult(_cli.DATASETS[1], day, "gap")

    monkeypatch.setattr(_runner, "recheck_pending", unauthorized)
    monkeypatch.setattr(_runner.HistoryRunner, "run_round_days", no_predict)
    monkeypatch.setattr(_runner.HistoryRunner, "run_kline_day", kline)
    args = _cli.build_parser().parse_args(["daily", "--apply", "--max-requests", "10"])
    payload = {"datasets": {}}
    assert _cli._run_apply(args, _common.Budget(max_requests=10), store, payload) == EXIT_FAIL
    assert calls == ["2026-08-10"]
    assert payload["pending_error"] == code
    assert payload["datasets"][_cli.DATASETS[0]]["error_code"] == code
    assert payload["datasets"][_cli.DATASETS[1]]["results"][0]["state"] == "gap"


@pytest.mark.parametrize("warmup", [0, 1, 3600, 90000])
def test_warmup_plan_and_apply_include_edge_day(patched_store, monkeypatch, tmp_path, warmup):
    from datetime import datetime, timedelta

    monkeypatch.setattr(_cli, "_api_key", lambda: None)
    monkeypatch.setattr(_cli, "_cutoff_date", lambda: "2026-11-11")
    arguments = ["backfill", "--start-utc", _cli.DEFAULT_START_UTC,
                 "--end-utc", _cli.DEFAULT_END_UTC, "--warmup-seconds", str(warmup)]
    assert main(arguments + ["--report-dir", str(tmp_path)]) == EXIT_OK
    summary = json.loads((tmp_path / "summary.json").read_text())
    edge = (datetime(2026, 8, 10) - timedelta(seconds=warmup)).strftime("%Y-%m-%d")
    for dataset in _cli.DATASETS:
        assert edge in [row["utc_date"] for row in summary["plans"][dataset]]
    assert patched_store["yquant-data"].list_collection_names() == []
    dates_by_source = {}

    async def pending(*args, **kwargs):
        return []

    async def rounds(self, dates):
        dates_by_source[_cli.DATASETS[0]] = dates
        return [_runner.DayResult(_cli.DATASETS[0], day, "gap") for day in dates]

    async def klines(self, day):
        dates_by_source.setdefault(_cli.DATASETS[1], []).append(day)
        return _runner.DayResult(_cli.DATASETS[1], day, "gap")

    monkeypatch.setattr(_runner, "recheck_pending", pending)
    monkeypatch.setattr(_runner.HistoryRunner, "run_round_days", rounds)
    monkeypatch.setattr(_runner.HistoryRunner, "run_kline_day", klines)
    assert main(arguments + ["--apply", "--report-dir", str(tmp_path)]) == _common.EXIT_PARTIAL
    store = _runner.IngestionStore(patched_store["yquant-data"])
    for dataset in _cli.DATASETS:
        assert edge in dates_by_source[dataset]
        assert store.get_stream(dataset)["ingestion_start_us"] == 1786320000000000 - warmup * 1000000
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["target_end_us"] == 1794268800000000


def test_apply_conflict_is_exit_20_and_does_not_starve_other_source(patched_store, monkeypatch):
    store = _runner.IngestionStore(patched_store["yquant-data"])
    for dataset in _cli.DATASETS:
        store.init_stream(dataset, ingestion_start_us=_common.day_bounds_us("2026-08-10")[0])
    monkeypatch.setattr(_cli, "_cutoff_date", lambda: "2026-08-11")
    monkeypatch.setattr(_cli, "_api_key", lambda: None)

    async def pending(*args, **kwargs):
        return []

    async def rounds(self, dates):
        return [_runner.DayResult(_cli.DATASETS[0], dates[0], "conflict")]

    calls = []

    async def kline(self, day):
        calls.append(day)
        return _runner.DayResult(_cli.DATASETS[1], day, "gap")

    monkeypatch.setattr(_runner, "recheck_pending", pending)
    monkeypatch.setattr(_runner.HistoryRunner, "run_round_days", rounds)
    monkeypatch.setattr(_runner.HistoryRunner, "run_kline_day", kline)
    assert main(["daily", "--apply"]) == EXIT_FAIL
    assert calls == ["2026-08-10"]


@pytest.mark.parametrize("case,expected", [("one", 10), ("conflict", 20)])
def test_verify_rejects_resolved_checkpoint_without_grid(patched_store, monkeypatch, tmp_path, case, expected):
    tests = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.tests.test_runner")
    loader = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.loader")
    rows = tests.synthetic_round_rows()[:1]
    if case == "conflict":
        rows[0]["settlement_state"] = "conflict"
    rows[0].update(raw_ref="a" * 64 + ".json", raw_sha256="a" * 64)
    rows[0]["record_sha256"] = loader._record_hash(rows[0], _cli.DATASETS[0])
    db = patched_store["yquant-data"]
    db[_common.ROUNDS_COLLECTION].insert_many(rows)
    store = _runner.IngestionStore(db)
    store.write_day(_cli.DATASETS[0], "2026-08-10", state="complete",
                    content_sha256=_runner._digest_of([], rows))
    # Explicit raw-verification boundary stub isolates coverage, not fake stored success.
    monkeypatch.setattr(_cli, "_verify_raw", lambda ref: True)

    async def raw(*args, **kwargs):
        return True

    monkeypatch.setattr(_cli, "_verify_predict_manifest", raw)
    before = list(db[_common.INGESTION_COLLECTION].find({}))
    assert main(["verify", "--start-utc", "2026-08-10T00:00:00Z",
                 "--end-utc", "2026-08-11T00:00:00Z", "--report-dir", str(tmp_path)]) == expected
    assert list(db[_common.INGESTION_COLLECTION].find({})) == before
    summary = json.loads((tmp_path / "summary.json").read_text())
    result = summary["datasets"][_cli.DATASETS[0] + "/2026-08-10"]
    assert not result["complete"]
    assert result["counts"]["missing_nominal_slots"] == 287
    assert summary["verified_content"] == {}


# Reuse transport/fake-DB fixtures, not business runner/loader success stubs.
_integration = importlib.import_module("tests.data.test_yquant_data_history_integration")
db_boundary = _integration.db_boundary
archive_run = _integration.archive_run


def test_fix2_public_apply_indexes_fresh_repeat_and_readonly(archive_run, monkeypatch):
    db, store, history = archive_run
    extractors = _integration.extractors
    original_http = extractors.http_get

    def transport(url, **kwargs):
        if "binance.vision" not in url:
            kwargs["budget"].take_request()
            raise _common.HistoryHTTPError("HTTP_UNAUTHORIZED")
        return original_http(url, **kwargs)

    monkeypatch.setattr(extractors, "http_get", transport)
    monkeypatch.setattr(_cli, "_open_store", lambda: store)
    monkeypatch.setattr(_cli, "RawArchive", lambda: history._archive)
    monkeypatch.setattr(_cli, "_api_key", lambda: None)
    monkeypatch.setattr(_cli, "_cutoff_date", lambda: "2026-08-11")
    args = ["backfill", "--start-utc", _cli.DEFAULT_START_UTC, "--end-utc", _cli.DEFAULT_END_UTC,
            "--max-days-per-source", "1", "--apply"]
    assert main(args) == EXIT_FAIL
    indexes = {name: db[name].index_information() for name in (
        _common.ROUNDS_COLLECTION, _common.KLINES_COLLECTION, _common.INGESTION_COLLECTION)}
    assert len(indexes[_common.ROUNDS_COLLECTION]) == 4
    assert len(indexes[_common.KLINES_COLLECTION]) == len(indexes[_common.INGESTION_COLLECTION]) == 2
    first = db[_common.KLINES_COLLECTION].find_one({})
    assert first and db[_common.KLINES_COLLECTION].count_documents({}) == 1
    monkeypatch.setattr(mongomock.collection.Collection, "create_index", lambda *a, **k: pytest.fail("repeat/read-only DDL"))
    # SPEC §9 no longer auto-retries authentication failures; explicitly review
    # this exact synthetic day to retain the old repeated-apply/index assertion.
    assert main(args + ["--retry-day", _cli.DATASETS[0] + ":2026-08-10"]) == EXIT_FAIL
    assert db[_common.KLINES_COLLECTION].find_one({}) == first
    assert indexes == {name: db[name].index_information() for name in indexes}
    before = {name: list(db[name].find({})) for name in indexes}
    assert main(["plan"]) == EXIT_OK
    assert main(["backfill", "--start-utc", _cli.DEFAULT_START_UTC, "--end-utc", _cli.DEFAULT_END_UTC]) == EXIT_OK
    assert main(["verify", "--start-utc", "2026-08-10T00:00:00Z",
                 "--end-utc", "2026-08-11T00:00:00Z"]) == _common.EXIT_PARTIAL
    assert before == {name: list(db[name].find({})) for name in indexes}


@pytest.mark.parametrize("bad", ["unique", "ttl", "partial", "direction"])
def test_fix2_public_apply_incompatible_index_stops_before_writes(db_boundary, monkeypatch, bad):
    db = db_boundary
    keys = [("source", 1), ("series_slug", 1), ("round_id", -1 if bad == "direction" else 1)]
    options = {"unique": bad != "unique"}
    if bad == "ttl":
        options["expireAfterSeconds"] = 5
    if bad == "partial":
        options["partialFilterExpression"] = {"round_id": {"$exists": True}}
    db[_common.ROUNDS_COLLECTION].create_index(keys, name="uniq_predict_round", **options)
    before = db[_common.ROUNDS_COLLECTION].index_information()
    monkeypatch.setattr(_cli, "_open_store", lambda: _runner.IngestionStore(db))
    monkeypatch.setattr(_common, "_open_http", lambda *a, **k: pytest.fail("HTTP after incompatible index"))
    assert main(["backfill", "--start-utc", _cli.DEFAULT_START_UTC,
                 "--end-utc", _cli.DEFAULT_END_UTC, "--apply"]) == EXIT_FAIL
    assert db[_common.ROUNDS_COLLECTION].index_information() == before
    assert db[_common.INGESTION_COLLECTION].count_documents({}) == 0
    assert db[_common.KLINES_COLLECTION].count_documents({}) == 0


@pytest.mark.parametrize("command", ["daily", "plan"])
def test_step12_default_plan_requires_initialization(patched_store, tmp_path, command):
    assert main([command, "--report-dir", str(tmp_path)]) == EXIT_FAIL
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["error_code"] == "NOT_INITIALIZED"
    assert summary["exit_code"] == EXIT_FAIL
    assert patched_store["yquant-data"].list_collection_names() == []


def test_step12_daily_plan_uses_same_anchor_as_apply(patched_store, tmp_path, monkeypatch):
    store = _runner.IngestionStore(patched_store["yquant-data"])
    for dataset in _cli.DATASETS:
        store.init_stream(dataset, ingestion_start_us=_common.day_bounds_us("2026-08-10")[0])
    monkeypatch.setattr(_cli, "_cutoff_date", lambda: "2026-08-13")
    before = list(store.db[_common.INGESTION_COLLECTION].find({}))
    assert main(["daily", "--report-dir", str(tmp_path)]) == EXIT_OK
    summary = json.loads((tmp_path / "summary.json").read_text())
    for dataset in _cli.DATASETS:
        assert {item["utc_date"] for item in summary["plans"][dataset]} == {
            "2026-08-10", "2026-08-11", "2026-08-12"}
    assert list(store.db[_common.INGESTION_COLLECTION].find({})) == before


@pytest.mark.parametrize("retry", ["other:2026-08-10", "predict_btc5m_rounds:2026-8-10",
    "predict_btc5m_rounds:2026-02-30", "predict_btc5m_rounds:2026-11-10",
    "predict_btc5m_rounds:2026-08-09"])
def test_step12_retry_syntax_and_window_fail_before_io(monkeypatch, retry):
    monkeypatch.setattr(_cli, "_open_store", lambda: pytest.fail("invalid retry opened store"))
    assert main(["backfill", "--start-utc", _cli.DEFAULT_START_UTC,
        "--end-utc", _cli.DEFAULT_END_UTC, "--retry-day", retry]) == EXIT_FAIL


def test_step12_retry_day_is_exact_repeatable_and_plan_only(patched_store, monkeypatch, tmp_path):
    from datetime import datetime, timedelta

    store = _runner.IngestionStore(patched_store["yquant-data"])
    moment = datetime(2026, 11, 12)
    monkeypatch.setattr(_runner, "utc_now", lambda: moment)
    monkeypatch.setattr(_cli, "_cutoff_date", lambda: "2026-11-12")
    for day in ("2026-08-11", "2026-11-09"):
        store.write_day(_cli.DATASETS[0], day, state="conflict", error_code="ROUND_CONFLICT",
                        next_retry_at=moment + timedelta(days=1))
    before = list(store.db[_common.INGESTION_COLLECTION].find({}))
    args = ["backfill", "--start-utc", _cli.DEFAULT_START_UTC,
            "--end-utc", _cli.DEFAULT_END_UTC, "--report-dir", str(tmp_path)]
    for day in ("2026-08-11", "2026-11-09", "2026-08-11"):
        args += ["--retry-day", _cli.DATASETS[0] + ":" + day]
    assert main(args) == EXIT_OK
    summary = json.loads((tmp_path / "summary.json").read_text())
    plans = summary["plans"][_cli.DATASETS[0]]
    assert {plan["utc_date"] for plan in plans if plan["reason"] == "operator_retry"} == {
        "2026-08-11", "2026-11-09"}
    assert summary["retry_days"] == [_cli.DATASETS[0] + ":2026-08-11",
                                       _cli.DATASETS[0] + ":2026-11-09"]
    assert before == list(store.db[_common.INGESTION_COLLECTION].find({}))


@pytest.mark.parametrize("case", ["complete", "cutoff", "before_anchor", "budget"])
def test_step12_retry_day_semantics_reject_before_any_apply_write(
    patched_store, monkeypatch, tmp_path, case,
):
    store = _runner.IngestionStore(patched_store["yquant-data"])
    for dataset in _cli.DATASETS:
        store.init_stream(dataset, ingestion_start_us=_common.day_bounds_us("2026-08-10")[0])
    monkeypatch.setattr(_cli, "_cutoff_date", lambda: "2026-08-12")
    day = {"cutoff": "2026-08-12", "before_anchor": "2026-08-09"}.get(case, "2026-08-10")
    if case == "complete":
        store.write_day(_cli.DATASETS[0], day, state="complete", content_sha256="a" * 64)
    before = list(store.db[_common.INGESTION_COLLECTION].find({}))
    monkeypatch.setattr(_runner, "ensure_history_indexes", lambda *a: pytest.fail("rejected request DDL"))
    args = ["daily", "--apply", "--retry-day", _cli.DATASETS[0] + ":" + day,
            "--report-dir", str(tmp_path)]
    if case == "budget":
        args += ["--max-days-per-source", "1", "--retry-day", _cli.DATASETS[0] + ":2026-08-11"]
    assert main(args) == EXIT_FAIL
    assert list(store.db[_common.INGESTION_COLLECTION].find({})) == before
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["exit_code"] == EXIT_FAIL


@pytest.mark.parametrize("case", ["missing", "empty", "unsafe", "symlink", "directory", "valid"])
def test_step12_key_file_safe_private_and_redacted(monkeypatch, tmp_path, capsys, case):
    monkeypatch.delenv("PM_PREDICT_API_KEY", raising=False)
    key_path = tmp_path / "synthetic-key"
    secret = "synthetic-step12-token"
    if case != "missing":
        if case == "directory":
            key_path.mkdir()
        else:
            key_path.write_text("  " if case == "empty" else secret + "\n")
            key_path.chmod(0o644 if case == "unsafe" else 0o600)
    if case == "symlink":
        link = tmp_path / "link"
        link.symlink_to(key_path)
        key_path = link
    monkeypatch.setenv("PM_PREDICT_API_KEY_FILE", str(key_path))
    if case == "valid":
        assert _cli._api_key() == secret
    else:
        with pytest.raises(_common.HistoryHTTPError, match="PREDICT_API_KEY") as error:
            _cli._api_key()
        assert secret not in str(error.value)
        assert str(key_path) not in str(error.value)
    output = capsys.readouterr()
    assert secret not in output.out + output.err


def test_step12_environment_key_has_priority(monkeypatch):
    monkeypatch.setenv("PM_PREDICT_API_KEY", " synthetic-env-only ")
    monkeypatch.setenv("PM_PREDICT_API_KEY_FILE", "/nonexistent-not-read")
    assert _cli._api_key() == "synthetic-env-only"


@pytest.mark.parametrize("code", ["HTTP_NETWORK_ERROR", "BUDGET_EXHAUSTED", "PREDICT_API_KEY_MISSING"])
def test_step12_summary_source_error_and_native_exit(patched_store, monkeypatch, tmp_path, code):
    store = _runner.IngestionStore(patched_store["yquant-data"])
    for dataset in _cli.DATASETS:
        store.init_stream(dataset, ingestion_start_us=_common.day_bounds_us("2026-08-10")[0])
    monkeypatch.setattr(_cli, "_cutoff_date", lambda: "2026-08-11")
    monkeypatch.setattr(_cli, "_api_key", lambda: "synthetic-key")
    if code.startswith("PREDICT_API_KEY"):
        def key_error():
            raise _common.HistoryHTTPError(code)
        monkeypatch.setattr(_cli, "_api_key", key_error)

    async def pending(*args, **kwargs):
        return []

    async def rounds(*args, **kwargs):
        if code == "BUDGET_EXHAUSTED":
            raise _common.HistoryBudgetError(code)
        raise _common.HistoryHTTPError(code)

    calls = []
    async def kline(self, day):
        calls.append(day)
        return _runner.DayResult(_cli.DATASETS[1], day, "gap")

    monkeypatch.setattr(_runner, "recheck_pending", pending)
    monkeypatch.setattr(_runner.HistoryRunner, "run_round_days", rounds)
    monkeypatch.setattr(_runner.HistoryRunner, "run_kline_day", kline)
    native = main(["daily", "--apply", "--report-dir", str(tmp_path)])
    assert native == (_common.EXIT_PARTIAL if code == "BUDGET_EXHAUSTED" else EXIT_FAIL)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["exit_code"] == native
    assert summary["datasets"][_cli.DATASETS[0]]["error_code"] == code
    assert calls == ["2026-08-10"]


def test_step12_restart_scan_plan_never_writes(patched_store, monkeypatch, tmp_path):
    store = _runner.IngestionStore(patched_store["yquant-data"])
    begin, end = _common.day_bounds_us("2026-08-10")
    for dataset in _cli.DATASETS:
        store.init_stream(dataset, ingestion_start_us=begin)
    store.write_stream(_cli.DATASETS[0], {"scan_lower_us": begin, "scan_upper_us": end,
        "scan_cursor": "opaque-cursor", "scan_manifest_ref": "not-read-by-plan"})
    before = list(store.db[_common.INGESTION_COLLECTION].find({}))
    assert main(["daily", "--restart-scan", "--report-dir", str(tmp_path)]) == EXIT_OK
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["restart_scan"]["lower_us"] == begin
    assert summary["restart_scan"]["upper_us"] == end
    assert before == list(store.db[_common.INGESTION_COLLECTION].find({}))


@pytest.mark.parametrize("boundary", ["main", "apply"])
@pytest.mark.parametrize("case", ["predict", "binance", "binance_after_day"])
def test_step12_interrupt_summary_preserves_obtained_results(
    patched_store, monkeypatch, tmp_path, capsys, boundary, case,
):
    """Report only returned DayResults, mark the source, and propagate the interrupt."""
    from contextlib import nullcontext
    import socket
    from scripts.unified_data import ud_lock

    store = _runner.IngestionStore(patched_store["yquant-data"])
    for dataset in _cli.DATASETS:
        store.init_stream(dataset, ingestion_start_us=_common.day_bounds_us("2026-08-09")[0])
        store.write_day(dataset, "2026-08-09", state="complete", content_sha256="f" * 64)
    before = list(store.db[_common.INGESTION_COLLECTION].find({}))
    # The existing planner reserves the recent day before the oldest backlog.
    dates = ["2026-08-12", "2026-08-10", "2026-08-11"]
    monkeypatch.setattr(_cli, "_cutoff_date", lambda: "2026-08-13")
    monkeypatch.setattr(_cli, "RawArchive", lambda: _common.RawArchive(tmp_path / "raw"))
    monkeypatch.setattr(_cli, "_api_key", lambda: "synthetic-interrupt-key")
    monkeypatch.setattr(ud_lock, "acquire_ud_lock", nullcontext)

    def forbidden(*args, **kwargs):
        pytest.fail("interrupt regression attempted external I/O")

    monkeypatch.setattr(_common, "_open_http", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    interruption = KeyboardInterrupt("synthetic-interrupt-secret")
    calls = []
    obtained = {dataset: [] for dataset in _cli.DATASETS}

    def result(dataset, day):
        returned = _runner.DayResult(
            dataset, day, "complete", counts={"accepted": 1}, content_sha256="a" * 64,
        )
        obtained[dataset].append({
            "utc_date": day, "state": returned.state, "error_code": returned.error_code,
            "content_sha256": returned.content_sha256, "counts": returned.counts,
        })
        return returned

    async def pending(*args, **kwargs):
        return []

    async def rounds(self, planned_dates):
        calls.append(("predict", list(planned_dates)))
        assert planned_dates == dates
        if case == "predict":
            raise interruption
        return [result(_cli.DATASETS[0], day) for day in planned_dates]

    async def kline(self, day):
        calls.append(("binance", day))
        if case == "binance" or day == dates[1]:
            raise interruption
        return result(_cli.DATASETS[1], day)

    monkeypatch.setattr(_runner, "recheck_pending", pending)
    monkeypatch.setattr(_runner.HistoryRunner, "run_round_days", rounds)
    monkeypatch.setattr(_runner.HistoryRunner, "run_kline_day", kline)
    arguments = ["daily", "--apply", "--report-dir", str(tmp_path)]
    if boundary == "main":
        native = main(arguments)
        summary = json.loads((tmp_path / "summary.json").read_text())
        assert native == summary["exit_code"] == _common.EXIT_TIMEOUT == 40
        assert summary["error_code"] == "INTERRUPTED"
    else:
        args = _cli.build_parser().parse_args(arguments)
        budget = _cli._validate_common(args)
        summary = {"datasets": {}}
        with pytest.raises(KeyboardInterrupt) as error:
            _cli._run_apply(args, budget, store, summary)
        assert error.value is interruption

    interrupted_source = _cli.DATASETS[0 if case == "predict" else 1]
    source = summary["datasets"][interrupted_source]
    assert source["planned_dates"] == dates
    assert source["results"] == obtained[interrupted_source]
    assert source.get("error_code") == "INTERRUPTED"
    if case == "predict":
        assert calls == [("predict", dates)]
        assert _cli.DATASETS[1] not in summary["datasets"]
        assert source["results"] == []  # Historical complete shards are not this run's results.
    else:
        previous = summary["datasets"][_cli.DATASETS[0]]
        assert previous == {"planned_dates": dates, "results": obtained[_cli.DATASETS[0]]}
        attempted = dates[:2] if case == "binance_after_day" else dates[:1]
        assert calls == [("predict", dates)] + [("binance", day) for day in attempted]
        assert len(source["results"]) == (1 if case == "binance_after_day" else 0)
    assert before == list(store.db[_common.INGESTION_COLLECTION].find({}))
    captured = capsys.readouterr()
    serialized = json.dumps(summary) + captured.out + captured.err
    assert "synthetic-interrupt-key" not in serialized
    assert "synthetic-interrupt-secret" not in serialized
