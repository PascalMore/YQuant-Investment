"""BTC5m 历史 extractor 测试 — 03-018 UT09 / UT10 / UT14。

全部使用本地 HTTP 替身（不联网、不读真实 env）。
"""

from __future__ import annotations

import hashlib
import importlib
import io
import traceback
import urllib.error
import zipfile
from email.message import Message
from http.client import IncompleteRead

import pytest

_extractors = importlib.import_module(
    "skills.data.data-pipeline.scripts.btc5m_history.extractors"
)
_common = importlib.import_module(
    "skills.data.data-pipeline.scripts.btc5m_history.common"
)

BinanceDaySource = _extractors.BinanceDaySource
BinanceKlineExtractor = _extractors.BinanceKlineExtractor
PredictPageSource = _extractors.PredictPageSource
PredictRoundExtractor = _extractors.PredictRoundExtractor
ZipChunkSource = _extractors.ZipChunkSource

Budget = _common.Budget
HistoryHTTPError = _common.HistoryHTTPError
RawArchive = _common.RawArchive

CSV_BODY = (
    "1786320000000000,100.1,100.2,100.0,100.15,1.5,1786320000999999,150.0,12,"
    "0.75,75.0,0\n"
    "1786320001000000,100.15,100.3,100.1,100.2,2.0,1786320001999999,201.0,15,"
    "1.0,100.0,0\n"
)


def _zip_bytes(body: str = CSV_BODY) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("BTCUSDT-1s-2026-08-10.csv", body)
    return buffer.getvalue()


@pytest.fixture()
def budget() -> Budget:
    return Budget(max_days_per_source=1, wall_seconds=300, max_requests=50)


@pytest.fixture()
def archive(tmp_path) -> RawArchive:
    return RawArchive(tmp_path)


class _FakeHttp:
    """记录请求并返回预置响应。"""

    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str, **kwargs) -> bytes:
        self.calls.append(url)
        # Longest prefix wins so the ".CHECKSUM" stub is not shadowed by the
        # generic host prefix.
        for prefix in sorted(self.responses, key=len, reverse=True):
            if url.startswith(prefix):
                return self.responses[prefix]
        raise HistoryHTTPError("HTTP_ERROR", "no stub for url")


# ---------------------------------------------------------------------------
# UT09 — checksum / CRC / 404 / 坏 CSV / 缺秒
# ---------------------------------------------------------------------------


def test_ut09_checksum_mismatch_is_rejected(archive, budget, monkeypatch) -> None:
    payload = _zip_bytes()
    fake = _FakeHttp(
        {
            "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/"
            "BTCUSDT-1s-2026-08-10.zip.CHECKSUM": (
                b"0000000000000000000000000000000000000000000000000000000000000000"
                b"  BTCUSDT-1s-2026-08-10.zip\n"
            ),
            "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/"
            "BTCUSDT-1s-2026-08-10.zip": payload,
        }
    )
    monkeypatch.setattr(_extractors, "http_get", fake)
    extractor = BinanceKlineExtractor(archive)
    import asyncio

    with pytest.raises(HistoryHTTPError) as excinfo:
        asyncio.run(
            extractor.prepare_day(
                BinanceDaySource(utc_date="2026-08-10"), budget=budget
            )
        )
    assert excinfo.value.code == "ARCHIVE_NOT_PUBLISHED_OR_MISSING" or (
        excinfo.value.code == "CHECKSUM_MISMATCH"
    )


def test_ut09_matching_checksum_is_accepted(archive, budget, monkeypatch) -> None:
    payload = _zip_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    fake = _FakeHttp(
        {
            "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/"
            "BTCUSDT-1s-2026-08-10.zip.CHECKSUM": (
                f"{digest}  BTCUSDT-1s-2026-08-10.zip\n".encode()
            ),
            "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/"
            "BTCUSDT-1s-2026-08-10.zip": payload,
        }
    )
    monkeypatch.setattr(_extractors, "http_get", fake)
    extractor = BinanceKlineExtractor(archive)
    import asyncio

    result = asyncio.run(
        extractor.prepare_day(
            BinanceDaySource(utc_date="2026-08-10"), budget=budget
        )
    )
    assert result["row_count"] == 2
    assert result["checksum"] == digest


def test_ut09_corrupt_zip_is_rejected(archive, budget, monkeypatch) -> None:
    payload = b"not-a-zip"
    digest = hashlib.sha256(payload).hexdigest()
    fake = _FakeHttp(
        {
            "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/"
            "BTCUSDT-1s-2026-08-10.zip.CHECKSUM": (
                f"{digest}  BTCUSDT-1s-2026-08-10.zip\n".encode()
            ),
            "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/"
            "BTCUSDT-1s-2026-08-10.zip": payload,
        }
    )
    monkeypatch.setattr(_extractors, "http_get", fake)
    extractor = BinanceKlineExtractor(archive)
    import asyncio

    with pytest.raises(HistoryHTTPError) as excinfo:
        asyncio.run(
            extractor.prepare_day(
                BinanceDaySource(utc_date="2026-08-10"), budget=budget
            )
        )
    assert excinfo.value.code == "BAD_CSV"


def test_ut09_expected_denominator_is_not_shrunk(archive, budget, monkeypatch) -> None:
    """缺秒不被压缩：expected 仍是 86400。"""
    _runner = importlib.import_module(
        "skills.data.data-pipeline.scripts.btc5m_history.runner"
    )
    assert _runner.SECONDS_PER_DAY == 86400


def test_ut09_duplicate_conflicting_rows_are_detected() -> None:
    _validators = importlib.import_module(
        "skills.data.data-pipeline.scripts.btc5m_history.validators"
    )
    validator = _validators.HistoryValidator("binance_spot_btcusdt_1s")
    import asyncio

    records = [
        {"open_time_us": 1000},
        {"open_time_us": 1000},
    ]
    result = asyncio.run(validator.validate(records))
    assert result.has_errors
    assert any("NOT_STRICTLY_ORDERED" in error for error in result.errors)


# ---------------------------------------------------------------------------
# UT10 — 分页边界
# ---------------------------------------------------------------------------


def test_ut10_repeated_cursor_does_not_advance(archive, budget, monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(url: str, **kwargs) -> bytes:
        calls.append(url)
        return b'{"success": true, "data": [], "cursor": "same"}'

    monkeypatch.setattr(_extractors, "http_get", fake_get)
    extractor = PredictRoundExtractor(archive)
    import asyncio

    first = asyncio.run(
        extractor.extract_page(PredictPageSource(), budget=budget)
    )
    assert first.next_after == "same"
    second = asyncio.run(
        extractor.extract_page(
            PredictPageSource(after=first.next_after), budget=budget
        )
    )
    assert second.next_after == "same"
    assert len(calls) == 2


def test_ut10_empty_page_is_not_success() -> None:
    _validators = importlib.import_module(
        "skills.data.data-pipeline.scripts.btc5m_history.validators"
    )
    validator = _validators.HistoryValidator("predict_btc5m_rounds")
    import asyncio

    result = asyncio.run(validator.validate([]))
    assert result.valid is True
    # 空批本身合法 —— 但 runner / loader 绝不能据此判定日 complete。
    assert not result.has_errors


def test_ut10_non_allowlisted_url_is_rejected(budget) -> None:
    with pytest.raises(HistoryHTTPError) as excinfo:
        _common.http_get("https://example.com/secrets", budget=budget)
    assert excinfo.value.code == "HTTP_URL_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# UT14 — 预算与认证
# ---------------------------------------------------------------------------


@pytest.fixture()
def incomplete_read_transport(monkeypatch):
    """Fail at response.read, never at urlopen; retain calls and real backoff delays."""
    calls, responses, sleeps = [], [], []
    outcomes = []

    class Response(io.BytesIO):
        def __init__(self, outcome):
            super().__init__()
            self.outcome = outcome

        def read(self, size: int | None = -1) -> bytes:
            assert size == 8 * 1024 * 1024 + 1
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

    def open_response(request, *, timeout):
        calls.append((request, timeout))
        assert outcomes, "unexpected extra request"
        response = Response(outcomes.pop(0))
        responses.append(response)
        return response

    monkeypatch.setattr(_common, "_open_http", open_response)
    monkeypatch.setattr(_common.time, "sleep", sleeps.append)
    return outcomes, calls, responses, sleeps


def test_incomplete_read_retry_returns_only_complete_bytes(budget, incomplete_read_transport):
    outcomes, calls, responses, sleeps = incomplete_read_transport
    complete = b' {"success":true,"data":[]}\n'
    outcomes.extend([IncompleteRead(b"discarded-partial", 12), complete])
    assert _common.http_get(
        "https://api.predict.fun/v1/markets/1", budget=budget, api_key="local-test-key",
    ) == complete
    assert len(calls) == budget.requests_used == 2
    assert sleeps == [1]
    assert all(response.closed for response in responses)
    assert all(0 < timeout <= _common.HTTP_TIMEOUT_SECONDS for _, timeout in calls)
    assert all(dict(request.header_items()) == {
        "User-agent": "YQuant-DataHistory/1.0", "X-api-key": "local-test-key",
    } for request, _ in calls)


@pytest.mark.parametrize("attempts", [1, _common.HTTP_MAX_ATTEMPTS])
def test_incomplete_read_exhaustion_is_sanitized(budget, incomplete_read_transport, attempts):
    outcomes, calls, responses, sleeps = incomplete_read_transport
    outcomes.extend(IncompleteRead(b"partial-local-test-key-X-API-Key", 12)
                    for _ in range(attempts))
    with pytest.raises(HistoryHTTPError) as error:
        _common.http_get("https://api.predict.fun/v1/markets/1", budget=budget,
                         api_key="local-test-key", max_attempts=attempts)
    assert error.value.code == "HTTP_NETWORK_ERROR"
    assert str(error.value) == "HTTP_NETWORK_ERROR: urlopen failed"
    assert error.value.__cause__ is None and error.value.__suppress_context__
    formatted = "".join(traceback.format_exception(error.type, error.value, error.tb))
    for sensitive in ("partial-local-test-key", "X-API-Key", "IncompleteRead"):
        assert sensitive not in formatted
    assert len(calls) == budget.requests_used == attempts
    assert sleeps == [1, 2][:attempts - 1]
    assert all(response.closed for response in responses)


@pytest.mark.parametrize("limit", ["requests", "wall"])
def test_incomplete_read_budget_stops_before_extra_request(incomplete_read_transport, limit):
    outcomes, calls, responses, sleeps = incomplete_read_transport
    outcomes.append(IncompleteRead(b"discarded-partial", 12))
    budget = Budget(max_requests=1 if limit == "requests" else 50)
    if limit == "wall":
        # Deterministic monotonic clock: opening/read leaves no wall time for backoff.
        budget._started_at = 0
        clock = iter([0, 0, budget.wall_seconds])
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(_common.time, "monotonic", lambda: next(clock))
            with pytest.raises(_common.HistoryBudgetError, match="BUDGET_EXHAUSTED"):
                _common.http_get("https://api.predict.fun/v1/markets/1", budget=budget)
    else:
        with pytest.raises(_common.HistoryBudgetError, match="BUDGET_EXHAUSTED"):
            _common.http_get("https://api.predict.fun/v1/markets/1", budget=budget)
    assert len(calls) == budget.requests_used == 1
    assert sleeps == ([1] if limit == "requests" else [])
    assert all(response.closed for response in responses)


def test_incomplete_read_never_archives_partial(archive, budget, incomplete_read_transport):
    import asyncio

    outcomes, calls, _, _ = incomplete_read_transport
    # Even a syntactically complete JSON partial must not be accepted as success.
    outcomes.extend(IncompleteRead(b'{"success":true,"data":[]}', 12)
                    for _ in range(_common.HTTP_MAX_ATTEMPTS))
    with pytest.raises(HistoryHTTPError, match="HTTP_NETWORK_ERROR"):
        asyncio.run(PredictRoundExtractor(archive).extract_page(
            PredictPageSource(), budget=budget,
        ))
    assert len(calls) == budget.requests_used == _common.HTTP_MAX_ATTEMPTS
    assert not list(archive._root.rglob("*"))


@pytest.mark.parametrize("status, code", [
    (429, "HTTP_RATE_LIMITED"), (500, "HTTP_SERVER_ERROR"),
    (503, "HTTP_SERVER_ERROR"), (None, "HTTP_NETWORK_ERROR"),
])
def test_incomplete_read_fix_preserves_existing_retries(budget, monkeypatch, status, code):
    calls, sleeps = [], []

    def fail(request, *, timeout):
        calls.append(request)
        if status is None:
            raise urllib.error.URLError("local-transport-only")
        raise urllib.error.HTTPError(request.full_url, status, "local-only", Message(), None)

    monkeypatch.setattr(_common, "_open_http", fail)
    monkeypatch.setattr(_common.time, "sleep", sleeps.append)
    with pytest.raises(HistoryHTTPError) as error:
        _common.http_get("https://api.predict.fun/v1/markets/1", budget=budget)
    assert error.value.code == code
    assert len(calls) == budget.requests_used == _common.HTTP_MAX_ATTEMPTS
    assert sleeps == [1, 2]


def test_incomplete_read_fix_does_not_swallow_other_read_errors(budget, incomplete_read_transport):
    outcomes, calls, _, sleeps = incomplete_read_transport
    outcomes.append(ValueError("local-programming-error"))
    with pytest.raises(ValueError, match="local-programming-error"):
        _common.http_get("https://api.predict.fun/v1/markets/1", budget=budget)
    assert len(calls) == budget.requests_used == 1
    assert sleeps == []


def test_incomplete_read_cli_isolates_predict_and_attempts_binance(
    monkeypatch, tmp_path, capsys, incomplete_read_transport,
):
    """Offline CLI boundary: real HTTP/extractor error, fake store and Binance lane."""
    cli_tests = importlib.import_module(
        "skills.data.data-pipeline.scripts.btc5m_history.tests.test_cli"
    )
    cli, runner = cli_tests._cli, cli_tests._runner
    store = runner.IngestionStore(cli_tests.mongomock.MongoClient()["yquant-data"])
    for dataset in cli.DATASETS:
        store.init_stream(dataset, ingestion_start_us=_common.day_bounds_us("2026-08-10")[0])
    monkeypatch.setattr(cli, "_cutoff_date", lambda: "2026-08-11")
    monkeypatch.setattr(cli, "_api_key", lambda: "local-test-key")
    archive = RawArchive(tmp_path / "raw")
    monkeypatch.setattr(cli, "RawArchive", lambda: archive)
    outcomes, requests, _, _ = incomplete_read_transport
    outcomes.extend(IncompleteRead(b"partial-local-test-key-X-API-Key", 12)
                    for _ in range(_common.HTTP_MAX_ATTEMPTS))

    async def pending(*args, **kwargs):
        return []

    async def rounds(self, dates):
        # Isolate orchestration without changing runner/checkpoint business logic.
        await PredictRoundExtractor(self._archive).extract_page(
            PredictPageSource(), budget=self._budget, api_key=self._api_key,
        )
        pytest.fail("truncated Predict response must not succeed")

    binance_calls = []

    async def kline(self, day):
        self._budget.take_request()
        binance_calls.append(day)
        return runner.DayResult(cli.DATASETS[1], day, "gap")

    monkeypatch.setattr(runner, "recheck_pending", pending)
    monkeypatch.setattr(runner.HistoryRunner, "run_round_days", rounds)
    monkeypatch.setattr(runner.HistoryRunner, "run_kline_day", kline)
    args = cli.build_parser().parse_args(["daily", "--apply", "--max-requests", "10"])
    budget = Budget(max_requests=10)
    payload = {"datasets": {}}
    assert cli._run_apply(args, budget, store, payload) == _common.EXIT_FAIL
    assert len(requests) == _common.HTTP_MAX_ATTEMPTS
    assert budget.requests_used == _common.HTTP_MAX_ATTEMPTS + 1
    assert binance_calls == ["2026-08-10"]
    assert payload["datasets"][cli.DATASETS[0]]["results"] == []
    assert payload["datasets"][cli.DATASETS[1]]["results"][0]["state"] == "gap"
    assert not cli._is_complete(store, payload)
    assert not list(archive._root.rglob("*"))
    output = capsys.readouterr()
    assert "HTTP_NETWORK_ERROR" in output.err
    assert "local-test-key" not in output.out + output.err
    assert "X-API-Key" not in output.out + output.err


def test_ut14_request_budget_is_bounded() -> None:
    budget = Budget(max_days_per_source=1, wall_seconds=300, max_requests=2)
    budget.take_request()
    budget.take_request()
    with pytest.raises(Exception) as excinfo:
        budget.take_request()
    assert "BUDGET_EXHAUSTED" in str(excinfo.value)


@pytest.mark.parametrize("path", [
    "/v1/series/btc-updown-5m/rounds?status=ENDED&first=100",
    "/v1/markets/status-logs?ids=1,2",
    "/v1/markets/1",
    "/v1/categories/btc-updown-5m-local-stub",
])
@pytest.mark.parametrize("with_key", [False, True])
def test_ua_fix_predict_application_headers(path, with_key, budget, monkeypatch) -> None:
    """本地 HTTP 替身：四种 Predict 入口保留原认证头并声明真实应用。"""
    calls = []
    stub_key = "local-http-stub-only" if with_key else None

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        return io.BytesIO(b"local-response")

    monkeypatch.setattr(_common, "_open_http", fake_urlopen)
    assert _common.http_get(
        f"https://api.predict.fun{path}", budget=budget, api_key=stub_key,
    ) == b"local-response"
    assert len(calls) == budget.requests_used == 1
    assert calls[0].get_method() == "GET"
    expected_headers = {"User-agent": "YQuant-DataHistory/1.0"}
    if stub_key:
        expected_headers["X-api-key"] = stub_key
    assert dict(calls[0].header_items()) == expected_headers


@pytest.mark.parametrize("suffix", [".zip", ".zip.CHECKSUM"])
def test_ua_fix_binance_headers_unchanged(suffix, budget, monkeypatch) -> None:
    """本地 HTTP 替身：Binance 无新增应用头，也不附带 Predict 认证头。"""
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        return io.BytesIO(b"local-response")

    monkeypatch.setattr(_common, "_open_http", fake_urlopen)
    url = (
        "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/"
        f"BTCUSDT-1s-2026-08-10{suffix}"
    )
    assert _common.http_get(url, budget=budget) == b"local-response"
    assert len(calls) == budget.requests_used == 1
    assert dict(calls[0].header_items()) == {}


@pytest.mark.parametrize("status, code", [
    (401, "HTTP_UNAUTHORIZED"),
    (403, "HTTP_FORBIDDEN"),
])
def test_ua_fix_auth_errors_remain_single_attempt(status, code, budget, monkeypatch) -> None:
    """本地 HTTP 替身：应用头不改变认证失败的原错误及单次立停。"""
    import urllib.error

    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        raise urllib.error.HTTPError(request.full_url, status, "local-stub", {}, None)

    monkeypatch.setattr(_common, "_open_http", fake_urlopen)
    monkeypatch.setattr(
        _common, "_sleep_backoff", lambda *args: pytest.fail("auth error must not back off"),
    )
    with pytest.raises(HistoryHTTPError) as excinfo:
        _common.http_get(
            "https://api.predict.fun/v1/markets/1", budget=budget,
            api_key="local-http-stub-only",
        )
    assert excinfo.value.code == code
    assert str(excinfo.value) == f"{code}: status={status}"
    assert len(calls) == budget.requests_used == 1
    assert dict(calls[0].header_items()) == {
        "User-agent": "YQuant-DataHistory/1.0",
        "X-api-key": "local-http-stub-only",
    }


def test_ut14_unauthorized_is_not_retried(budget, monkeypatch) -> None:
    import urllib.error

    calls: list[str] = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(_common, "_open_http", fake_urlopen)
    with pytest.raises(HistoryHTTPError) as excinfo:
        _common.http_get(
            "https://api.predict.fun/v1/series/btc-updown-5m/rounds",
            budget=budget,
        )
    assert excinfo.value.code == "HTTP_UNAUTHORIZED"
    assert len(calls) == 1


@pytest.mark.parametrize("url", [
    "https://api.predict.fun.evil/v1/markets/1",
    "https://api.predict.fun/v1/series/other/rounds",
    "https://api.predict.fun/v1/markets/../private",
    "https://api.predict.fun/v1/markets/1?token=synthetic-secret",
    "https://api.predict.fun/v1/markets/status-logs?ids=1%26token=x",
    "https://data.binance.vision/data/spot/daily/klines/ETHUSDT/1s/x.zip",
])
def test_ut22_exact_http_allowlist_rejects_before_transport(url, budget, monkeypatch):
    monkeypatch.setattr(_common, "_open_http", lambda *args, **kwargs: pytest.fail("transport"))
    with pytest.raises(HistoryHTTPError, match="HTTP_URL_NOT_ALLOWED") as error:
        _common.http_get(url, budget=budget)
    assert "synthetic-secret" not in str(error.value)
    assert budget.requests_used == 0


def test_ut22_redirect_handler_never_forwards_credentials():
    with pytest.raises(HistoryHTTPError, match="HTTP_REDIRECT_NOT_ALLOWED"):
        _common._NoRedirect().redirect_request(None, None, 302, "", {},
                                               "https://evil.invalid/")


def test_ut22_raw_path_rejects_escape_and_symlink(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"synthetic")
    (root / "link.json").symlink_to(outside)
    archive = RawArchive(root)
    for reference in (outside, root / "link.json"):
        with pytest.raises(HistoryHTTPError, match="RAW_PATH_NOT_ALLOWED"):
            archive.read_bytes(str(reference))


def test_ut22_secret_response_not_returned(budget, monkeypatch):
    monkeypatch.setattr(_common, "_open_http", lambda *args, **kwargs: io.BytesIO(b"synthetic-key"))
    with pytest.raises(HistoryHTTPError, match="HTTP_SECRET_IN_RESPONSE"):
        _common.http_get("https://api.predict.fun/v1/markets/1", budget=budget,
                         api_key="synthetic-key")


def test_ut20_budget_lanes_charge_global_and_cannot_starve_other_source():
    budget = Budget(max_requests=6)
    first = budget.fork(requests=3, seconds=10)
    for _ in range(3):
        first.take_request()
    with pytest.raises(_common.HistoryBudgetError):
        first.take_request()
    second = budget.fork(requests=3, seconds=10)
    second.take_request()
    assert budget.requests_used == 4
    assert second.requests_used == 1
    assert second.remaining() <= budget.remaining()


@pytest.mark.parametrize("case", ["outside", "reverse", "duplicate", "member"])
def test_fix2_archive_rejects_whole_file_before_chunk_writes(archive, budget, monkeypatch, case):
    import asyncio

    begin, _ = _common.day_bounds_us("2026-08-10")
    opens = [begin, begin + 1_000_000, begin + 2_000_000]
    if case == "outside":
        opens[-1] = begin - 1_000_000
    elif case == "reverse":
        opens[-1] = begin + 500_000
    elif case == "duplicate":
        opens[-1] = opens[-2]
    text = "".join(f"{value},100,102,99,101,1,{value+999999},101,1,1,101,0\n" for value in opens)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("wrong.csv" if case == "member" else "BTCUSDT-1s-2026-08-10.csv", text)
    body = buffer.getvalue()
    checksum = (hashlib.sha256(body).hexdigest() + "  BTCUSDT-1s-2026-08-10.zip\n").encode()
    monkeypatch.setattr(_extractors, "http_get", lambda url, **kwargs: checksum if url.endswith(".CHECKSUM") else body)
    with pytest.raises(HistoryHTTPError, match="BAD_CSV"):
        asyncio.run(BinanceKlineExtractor(archive).prepare_day(BinanceDaySource("2026-08-10"), budget=budget))


def test_fix2_valid_archive_has_stable_multichunk_rows(archive, budget, monkeypatch):
    import asyncio

    body = _zip_bytes()
    checksum = (hashlib.sha256(body).hexdigest() + "  BTCUSDT-1s-2026-08-10.zip\n").encode()
    monkeypatch.setattr(_extractors, "http_get", lambda url, **kwargs: checksum if url.endswith(".CHECKSUM") else body)
    extractor = BinanceKlineExtractor(archive)
    prepared = asyncio.run(extractor.prepare_day(BinanceDaySource("2026-08-10"), budget=budget))
    chunks = [asyncio.run(extractor.extract_chunk(ZipChunkSource(prepared["raw_ref"], offset, 1))) for offset in range(2)]
    assert [row for chunk in chunks for row in chunk] == prepared["rows"]


# Minimal public excerpt, not a fabricated canonical-envelope HTTP response.
# Omitted display/reward fields are irrelevant; retained numeric tokens stay JSON numbers.
OFFICIAL_PAGE_SHA = "791a17406c0128d0712099563c7967df066140fccb1bb7c760405c7ff33ac245"
OFFICIAL_STATUS_SHA = "788cb2140d214bfaf106b1391b78b557ede11c10dca34808fb9c6e36960be666"
OFFICIAL_EXCERPT = b'''{"success":true,"cursor":"ZToxNzk0MzYwNjAwMDAwMDAwOjc0MjU5MA==","data":[{
  "id":744030,"slug":"btc-updown-5m-1794390300","seriesSlug":"btc-updown-5m",
  "startsAt":"2026-11-11T09:45:00.000Z","endsAt":"2026-11-11T09:50:00.000Z",
  "publishedAt":"2026-11-10T09:45:55.002Z","status":"RESOLVED",
  "variantData":{"startPrice":73638.005,"endPrice":73650.265,"priceFeedProvider":"CHAINLINK","priceFeedSymbol":"BTCUSDT"},
  "variantDetails":{
    "crypto":{"startPrice":73638.005,"endPrice":73650.265,"priceFeedProvider":"CHAINLINK","priceFeedSymbol":"BTCUSDT"},
    "upDown":{"startPrice":73638.005,"endPrice":73650.265,"priceFeedProvider":"CHAINLINK","priceFeedSymbol":"BTCUSDT"}},
  "markets":[{"id":4468600,"seriesSlug":"btc-updown-5m","categorySlug":"btc-updown-5m-1794390300",
    "conditionId":"0x015237ed51d33d9d5234714ca6599a1562390d39c0e9de2a1c8f85b63cb742e2",
    "status":"RESOLVED","tradingStatus":"CLOSED",
    "variantData":{"startPrice":73638.005,"endPrice":73650.265,"priceFeedProvider":"CHAINLINK","priceFeedSymbol":"BTCUSDT"},
    "outcomes":[
      {"indexSet":1,"name":"Up","status":"WON","onChainId":"69798214229359020279855699882924365370697840931301980402574215270815483436470"},
      {"indexSet":2,"name":"Down","status":"LOST","onChainId":"28919887097270776784214340420347555427371304011717694839514302107049610719231"}],
    "resolution":{"indexSet":1,"name":"Up","status":"WON","onChainId":"69798214229359020279855699882924365370697840931301980402574215270815483436470"}}]
}]}'''
OFFICIAL_STATUS_EXCERPT = b'''{"success":true,"data":[{"marketId":4468600,"logs":[
  {"logIndex":null,"proposedOutcomeId":null,"proposedOutcomeLabel":null,"resolutionProvider":"PREDICT_DOT_FUN","status":"REGISTERED","timestamp":"2026-11-10T09:45:18.000Z","transactionHash":"0x4cf1e61a6d3ceeee5cdd845ce06d4e0be1e99dac574ae7c37b2fb950c3c4ac10"},
  {"logIndex":null,"proposedOutcomeId":null,"proposedOutcomeLabel":null,"resolutionProvider":"CHAINLINK","status":"RESOLVED","timestamp":"2026-11-11T09:50:01.000Z","transactionHash":"0xdddeb171540f3677af0f99c5cc96cb349cea16d504bc33e72a5446a64f3786a8"}
]}]}'''


def shape_json_bytes(value):
    """Encode controlled test containers without converting Decimal tokens to floats."""
    import json
    from decimal import Decimal

    if isinstance(value, Decimal):
        return str(value).encode()
    if isinstance(value, dict):
        return b"{" + b",".join(json.dumps(key).encode() + b":" + shape_json_bytes(item)
                                 for key, item in value.items()) + b"}"
    if isinstance(value, list):
        return b"[" + b",".join(shape_json_bytes(item) for item in value) + b"]"
    return json.dumps(value).encode()


@pytest.fixture()
def shape_wire_bytes(request):
    """CI needs no ignored archives; a local evidence plugin can inject exact full bytes."""
    return getattr(request, "param", (OFFICIAL_EXCERPT, OFFICIAL_STATUS_EXCERPT))


def test_shape_fix_official_archive_boundary(archive, budget, monkeypatch, shape_wire_bytes):
    """HTTP bytes -> extractor -> raw replay; numeric prices and IDs are unchanged."""
    import asyncio
    import json
    from decimal import Decimal

    bodies = shape_wire_bytes
    originals = json.loads(bodies[0], parse_float=Decimal)
    transport = _FakeHttp({
        _common.PREDICT_BASE + "/v1/series/": bodies[0],
        _common.PREDICT_BASE + "/v1/markets/status-logs": bodies[1],
    })
    monkeypatch.setattr(_common, "_open_http", lambda request, **kwargs: io.BytesIO(transport(request.full_url)))
    page = asyncio.run(PredictRoundExtractor(archive).extract_page(PredictPageSource(), budget=budget))
    assert len(page.records) == len(originals["data"])
    assert page.records[0]["category"]["id"] == originals["data"][0]["id"]
    assert page.raw_sha256 == hashlib.sha256(bodies[0]).hexdigest()
    assert archive.read_bytes(page.raw_ref) == bodies[0]
    assert budget.requests_used == 2
    assert len(transport.calls) == 2
    history = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.runner")
    replay = history.read_round_page(archive, {
        "raw_ref": page.raw_ref, "raw_sha256": page.raw_sha256,
        "cursor": page.cursor, "count": len(page.records),
        "status_refs": page.records[0]["_status_raw_refs"],
    })
    transformer = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.transforms").PredictRoundTransformer()
    for original, extracted, reread in zip(originals["data"], page.records, replay):
        assert extracted["category"] == {key: value for key, value in original.items() if key != "markets"}
        assert extracted["markets"] == original["markets"]
        assert {key: value for key, value in reread.items() if key not in {"_raw_ref", "_raw_sha256"}} == extracted
        record = transformer.transform_one(reread)
        assert record["settlement_state"] == "resolved"
        assert record["start_price"] == original["variantData"]["startPrice"]
        assert record["end_price"] == original["variantData"]["endPrice"]
    assert transformer.transform_one(replay[0])["start_price"] == Decimal("73638.005")


@pytest.mark.parametrize("fault", ["null", "array", "category", "markets", "market", "dual_id", "dual_time", "nested_markets"])
def test_shape_fix_rejects_ambiguous_http_structure(archive, budget, monkeypatch, fault):
    import asyncio
    import json

    flat = json.loads(OFFICIAL_EXCERPT)["data"][0]
    if fault == "null":
        row = None
    elif fault == "array":
        row = []
    elif fault == "category":
        row = dict(flat, category=None)
    elif fault == "markets":
        row = dict(flat, markets={})
    elif fault == "market":
        row = dict(flat, markets=[None])
    elif fault == "nested_markets":
        row = {"category": flat, "markets": []}
    else:
        row = {"category": {key: value for key, value in flat.items() if key != "markets"}, "markets": flat["markets"]}
        row["id" if fault == "dual_id" else "startsAt"] = "contradictory"
    body = json.dumps({"success": True, "data": [row]}).encode()
    monkeypatch.setattr(_common, "_open_http", lambda *args, **kwargs: io.BytesIO(body))
    with pytest.raises(HistoryHTTPError, match="PREDICT_API_ERROR"):
        asyncio.run(PredictRoundExtractor(archive).extract_page(PredictPageSource(), budget=budget))


@pytest.mark.parametrize("canonical", [False, True])
def test_shape_fix_pending_and_enumeration_share_envelope(archive, budget, monkeypatch, canonical):
    import asyncio
    import json
    from decimal import Decimal

    flat = json.loads(OFFICIAL_EXCERPT, parse_float=Decimal)["data"][0]
    category = ({"category": {key: value for key, value in flat.items() if key != "markets"},
                 "markets": flat["markets"]} if canonical else flat)
    body = shape_json_bytes({"success": True, "data": category})
    calls = []

    def transport(request, **kwargs):
        calls.append(request.full_url)
        return io.BytesIO(OFFICIAL_STATUS_EXCERPT if "/status-logs" in request.full_url else body)

    monkeypatch.setattr(_common, "_open_http", transport)
    result = asyncio.run(PredictRoundExtractor(archive).extract_pending({
        "round_id": "744030", "round_slug": flat["slug"], "market_id": "4468600",
    }, budget=budget))
    assert len(calls) == budget.requests_used == 2
    assert archive.read_bytes(result.raw_ref) == body
    record = result.records[0]
    assert record["category"] == {key: value for key, value in flat.items() if key != "markets"}
    assert "category" not in record["category"]
    assert _extractors.normalize_round_envelope(record) == record
    transforms = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.transforms")
    transformed = transforms.PredictRoundTransformer().transform_one(record)
    assert transformed["round_id"] == "744030" and transformed["market_id"] == "4468600"
    assert transformed["start_price"] == Decimal("73638.005")
    assert transformed["settlement_state"] == "resolved" and transformed["official_outcome"] == "UP"


@pytest.mark.parametrize("fault", ["order", "duplicate", "round_id", "market", "variant"])
def test_shape_fix_real_boundary_keeps_strict_business_rejections(archive, budget, monkeypatch, fault):
    """Explicitly mutated excerpt negative fixtures, never claimed official facts."""
    import asyncio
    import copy
    import json
    from decimal import Decimal

    flat = json.loads(OFFICIAL_EXCERPT, parse_float=Decimal)["data"][0]
    damaged = copy.deepcopy(flat)
    if fault == "order":
        damaged["startsAt"] = "2026-11-11T09:50:00.000Z"
        damaged["endsAt"] = "2026-11-11T09:55:00.000Z"
    elif fault == "duplicate":
        damaged["status"] = "OPEN"
    elif fault == "round_id":
        damaged["id"] = True
    elif fault == "market":
        damaged["markets"][0]["seriesSlug"] = "eth-updown-5m"
    else:
        damaged["variantDetails"]["crypto"]["startPrice"] = Decimal("999")
    rows = [flat, damaged] if fault in {"order", "duplicate"} else [damaged]
    body = shape_json_bytes({"success": True, "data": rows, "cursor": None})

    def transport(request, **kwargs):
        status = OFFICIAL_STATUS_EXCERPT
        if fault == "market":
            status = b'{"success":true,"data":[]}'
        return io.BytesIO(status if "/status-logs" in request.full_url else body)

    monkeypatch.setattr(_common, "_open_http", transport)
    extractor = PredictRoundExtractor(archive)
    history = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.runner")
    if fault in {"order", "duplicate"}:
        scan = asyncio.run(history.scan_rounds(extractor, budget=budget,
            lower_us=0, upper_us=1, max_pages=1))
        assert not scan.closed
        assert scan.error_code == ("ORDER_REVERSAL" if fault == "order" else "DUPLICATE_CONFLICT")
    else:
        page = asyncio.run(extractor.extract_page(PredictPageSource(), budget=budget))
        transforms = importlib.import_module("skills.data.data-pipeline.scripts.btc5m_history.transforms")
        with pytest.raises(transforms.TransformError):
            transforms.PredictRoundTransformer().transform_one(page.records[0])


@pytest.mark.parametrize("status,code", [(429, "HTTP_RATE_LIMITED"), (503, "HTTP_SERVER_ERROR")])
@pytest.mark.parametrize("header", ["7200", "Thu, 12 Nov 2026 02:00:00 GMT"])
def test_step12_long_retry_after_is_not_shortened_or_slept_past_budget(
    monkeypatch, status, code, header,
):
    import urllib.error
    from datetime import datetime, timedelta

    moment = datetime(2026, 11, 12)
    monkeypatch.setattr(_common, "utc_now", lambda: moment)
    calls = []

    def transport(request, **kwargs):
        from email.message import Message

        calls.append(request.full_url)
        headers = Message()
        headers["Retry-After"] = header
        raise urllib.error.HTTPError(request.full_url, status, "synthetic", headers, None)

    monkeypatch.setattr(_common, "_open_http", transport)
    monkeypatch.setattr(_common.time, "sleep", lambda delay: pytest.fail("long sleep exceeded lane"))
    budget = _common.Budget()
    with pytest.raises(_common.HistoryHTTPError) as error:
        _common.http_get(_common.PREDICT_BASE + "/v1/series/btc-updown-5m/rounds", budget=budget)
    assert error.value.code == code
    assert error.value.retry_at == moment + timedelta(hours=2)
    assert len(calls) == budget.requests_used == 1


@pytest.mark.parametrize("value", [None, "", "not-a-date", "-1", "9999999999999999999999999"])
def test_step12_invalid_retry_after_does_not_expose_header(value):
    assert _common._retry_after_at(value) is None
