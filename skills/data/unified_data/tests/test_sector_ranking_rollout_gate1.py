"""Offline tests for Gate-1 (gate1_smoke.py) — 03-016 rollout.

DESIGN-03-016 V0.4 §3.4 / SPEC-03-016 §3.2. All tests run against
mongomock with explicit ``client_factory`` / ``env`` injection —
**zero environment reads and zero real I/O** (CL-5).

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json

import mongomock
import pytest

from scripts.unified_data.sector_ranking_rollout.common import (
    EXIT_CONN,
    EXIT_OK,
    EXIT_STOP,
)
from scripts.unified_data.sector_ranking_rollout.gate1_smoke import (
    Gate1Stop,
    build_report,
    check_close_completeness,
    check_source_distribution,
    compute_coverage,
    cross_check_reference,
    enumerate_sw_l1,
    main,
    select_candidates,
)
from skills.data.unified_data.tests.fixtures.sector_ranking_rollout_fixtures import (
    AVAILABLE_DATES,
    EXPECTED_UNIVERSE,
    make_index_basic_docs,
    make_mismatch_reference_csv,
    make_mongomock_db,
    make_reference_csv,
    make_sw_index_docs,
    make_sw_index_docs_missing_close,
    make_sw_index_docs_rt_marker,
)

TEST_ENV = {
    "MONGODB_HOST": "mongo-host-1",
    "MONGODB_PORT": "27017",
    "MONGODB_USERNAME": "svc-user",
    "MONGODB_PASSWORD": "svc-pass-123",
    "MONGODB_DATABASE": "tradingagents",
}


def _db(*, rt_source: str | None = None, missing_close: list[str] | None = None):
    daily = make_sw_index_docs()
    if rt_source is not None:
        daily = make_sw_index_docs_rt_marker(rt_source)
    if missing_close:
        daily = make_sw_index_docs_missing_close(missing_close)
    return make_mongomock_db(index_daily=daily, index_basic=make_index_basic_docs())


# ---------------------------------------------------------------------------
# enumerate_sw_l1（G1-C-001 / G1-S-002 / G1-S-003 / G1-C-006）
# ---------------------------------------------------------------------------


class TestEnumerateSwL1:
    def test_returns_code_name_from_market_cn(self):
        db = _db()
        universe = enumerate_sw_l1(db)
        assert universe == EXPECTED_UNIVERSE

    def test_empty_index_basic_stops_g1_s_002(self):
        db = make_mongomock_db(index_daily=make_sw_index_docs())
        with pytest.raises(Gate1Stop) as exc:
            enumerate_sw_l1(db)
        assert exc.value.sc_id == "G1-S-002"

    def test_duplicate_sector_code_stops_g1_s_003(self):
        docs = make_index_basic_docs()
        docs.append(dict(docs[0]))  # duplicate 801010
        db = make_mongomock_db(index_daily=make_sw_index_docs(), index_basic=docs)
        with pytest.raises(Gate1Stop) as exc:
            enumerate_sw_l1(db)
        assert exc.value.sc_id == "G1-S-003"

    def test_non_sw_prefix_stops_g1_s_003(self):
        docs = make_index_basic_docs()
        docs.append(
            {"market": "CN", "sector_code": "000001", "name": "上证指数", "type": "指数"}
        )
        db = make_mongomock_db(index_daily=make_sw_index_docs(), index_basic=docs)
        with pytest.raises(Gate1Stop) as exc:
            enumerate_sw_l1(db)
        assert exc.value.sc_id == "G1-S-003"

    def test_concept_classify_stops_g1_c_006(self):
        docs = make_index_basic_docs(classify="concept")
        db = make_mongomock_db(index_daily=make_sw_index_docs(), index_basic=docs)
        with pytest.raises(Gate1Stop) as exc:
            enumerate_sw_l1(db)
        assert exc.value.sc_id == "G1-C-006"

    def test_code_fallback_when_sector_code_absent(self):
        docs = make_index_basic_docs(use_code_fallback=True)
        db = make_mongomock_db(index_daily=make_sw_index_docs(), index_basic=docs)
        assert enumerate_sw_l1(db) == EXPECTED_UNIVERSE


# ---------------------------------------------------------------------------
# cross_check_reference（G1-C-001 双源 / OQ-016-2）
# ---------------------------------------------------------------------------


class TestCrossCheckReference:
    def test_missing_reference_file_reports_reference_missing(self, tmp_path):
        missing_path = tmp_path / "reference" / "sw_l1_reference.csv"
        discrepancies, ref_missing = cross_check_reference(
            EXPECTED_UNIVERSE, str(missing_path)
        )
        assert ref_missing is True
        assert discrepancies == []

    def test_matching_reference_has_no_discrepancies(self, tmp_path):
        ref_path = make_reference_csv(tmp_path)
        discrepancies, ref_missing = cross_check_reference(
            EXPECTED_UNIVERSE, str(ref_path)
        )
        assert ref_missing is False
        assert discrepancies == []

    def test_mismatch_reference_records_discrepancies(self, tmp_path):
        ref_path = make_mismatch_reference_csv(tmp_path)
        discrepancies, ref_missing = cross_check_reference(
            EXPECTED_UNIVERSE, str(ref_path)
        )
        assert ref_missing is False
        kinds = {d["kind"] for d in discrepancies}
        assert "name_mismatch" in kinds  # 801010 name 不一致
        assert "db_only" in kinds  # 801080 db 有 reference 无
        assert "ref_only" in kinds  # 801999 reference 有 db 无


# ---------------------------------------------------------------------------
# compute_coverage（G1-C-003）
# ---------------------------------------------------------------------------


class TestComputeCoverage:
    def test_coverage_by_date_and_range(self):
        db = _db()
        date_range, coverage = compute_coverage(db, EXPECTED_UNIVERSE)
        assert date_range == {"min": "2026-07-10", "max": "2026-07-14"}
        assert set(coverage) == set(AVAILABLE_DATES)
        for entry in coverage.values():
            assert entry["expected"] == 3
            assert entry["observed"] == 3
            assert entry["ratio"] == 1.0

    def test_coverage_marks_partial_days(self):
        db = _db()
        # 去掉 801080 在 2026-07-13 的行 → 该日 observed=2
        daily = make_sw_index_docs()
        daily = [
            d
            for d in daily
            if not (d["trade_date"] == "20260713" and d["sector_code"] == "801080")
        ]
        db2 = make_mongomock_db(index_daily=daily, index_basic=make_index_basic_docs())
        _, coverage = compute_coverage(db2, EXPECTED_UNIVERSE)
        assert coverage["2026-07-13"]["observed"] == 2
        assert coverage["2026-07-13"]["ratio"] == pytest.approx(2 / 3)

    def test_min_max_trade_date_filter(self):
        db = _db()
        _, coverage = compute_coverage(
            db, EXPECTED_UNIVERSE, min_trade_date="2026-07-13"
        )
        assert set(coverage) == {"2026-07-13", "2026-07-14"}


# ---------------------------------------------------------------------------
# check_close_completeness（G1-C-004）
# ---------------------------------------------------------------------------


class TestCloseCompleteness:
    def test_complete_days_have_no_missing(self):
        db = _db()
        missing = check_close_completeness(db, EXPECTED_UNIVERSE)
        assert missing == {d: [] for d in AVAILABLE_DATES}

    def test_missing_close_recorded(self):
        db = _db(missing_close=["801010"])
        missing = check_close_completeness(db, EXPECTED_UNIVERSE)
        assert "801010" in missing["2026-07-13"]


# ---------------------------------------------------------------------------
# check_source_distribution（G1-C-005 / G1-S-006）
# ---------------------------------------------------------------------------


class TestSourceDistribution:
    def test_sw_source_distribution(self):
        db = _db()
        source_dist, markers = check_source_distribution(db, EXPECTED_UNIVERSE)
        assert source_dist.get("sw") == 9
        assert markers == []

    def test_realtime_marker_detected(self):
        db = _db(rt_source="realtime")
        _, markers = check_source_distribution(db, EXPECTED_UNIVERSE)
        assert "realtime" in markers


# ---------------------------------------------------------------------------
# select_candidates（G1-C-003/004 + OQ-016-3）
# ---------------------------------------------------------------------------


class TestSelectCandidates:
    def test_full_coverage_dates_are_candidates(self):
        coverage = {
            d: {"expected": 3, "observed": 3, "ratio": 1.0} for d in AVAILABLE_DATES
        }
        candidates, recommended = select_candidates(
            coverage, {d: [] for d in AVAILABLE_DATES}, today="2026-07-10"
        )
        assert candidates == ["2026-07-13", "2026-07-14"]
        assert recommended == "2026-07-14"

    def test_partial_day_excluded(self):
        coverage = {
            d: {"expected": 3, "observed": 3, "ratio": 1.0} for d in AVAILABLE_DATES
        }
        coverage["2026-07-14"]["observed"] = 2
        coverage["2026-07-14"]["ratio"] = 2 / 3
        candidates, _ = select_candidates(
            coverage, {d: [] for d in AVAILABLE_DATES}, today="2026-07-10"
        )
        assert "2026-07-14" not in candidates

    def test_missing_close_day_excluded(self):
        coverage = {
            d: {"expected": 3, "observed": 3, "ratio": 1.0} for d in AVAILABLE_DATES
        }
        close_missing = {d: [] for d in AVAILABLE_DATES}
        close_missing["2026-07-13"] = ["801010"]
        candidates, _ = select_candidates(coverage, close_missing, today="2026-07-10")
        assert "2026-07-13" not in candidates

    def test_today_excluded(self):
        coverage = {
            d: {"expected": 3, "observed": 3, "ratio": 1.0} for d in AVAILABLE_DATES
        }
        candidates, _ = select_candidates(
            coverage, {d: [] for d in AVAILABLE_DATES}, today="2026-07-14"
        )
        assert "2026-07-14" not in candidates

    def test_no_candidates_when_none_full(self):
        coverage = {
            d: {"expected": 3, "observed": 2, "ratio": 2 / 3} for d in AVAILABLE_DATES
        }
        candidates, recommended = select_candidates(
            coverage, {d: [] for d in AVAILABLE_DATES}, today="2026-07-10"
        )
        assert candidates == []
        assert recommended is None


# ---------------------------------------------------------------------------
# build_report（G1-R-001 ~ G1-R-010）
# ---------------------------------------------------------------------------


class TestBuildReport:
    def test_report_contains_all_required_fields(self):
        conn_fingerprint = {
            "source": "MONGODB_*",
            "keys_present": list(TEST_ENV),
            "auth_configured": True,
        }
        payload = build_report(
            tool="gate1_smoke",
            conn_source="MONGODB_*",
            conn_fingerprint=conn_fingerprint,
            query_budget=[],
            expected_sector_codes=sorted(EXPECTED_UNIVERSE),
            expected_sector_names=EXPECTED_UNIVERSE,
            trade_date_range={"min": "2026-07-10", "max": "2026-07-14"},
            trade_date_format="YYYYMMDD",
            coverage_by_date={},
            close_missing_by_date={},
            source_distribution={"sw": 9},
            realtime_markers=[],
            discrepancies=[],
            canary_candidates=["2026-07-14"],
            recommended_canary="2026-07-14",
            checks={"G1-C-001": "PASS"},
        )
        for key in (
            "tool",
            "version",
            "timestamp",
            "conn_source",
            "conn_fingerprint",
            "query_budget",
            "expected_sector_codes",
            "expected_sector_names",
            "trade_date_range",
            "coverage_by_date",
            "source_distribution",
            "canary_candidates",
            "checks",
            "stop_conditions_hit",
        ):
            assert key in payload
        assert payload["stop_conditions_hit"] == []


# ---------------------------------------------------------------------------
# main（CLI 退出码 / 只读证明 / report 产物）
# ---------------------------------------------------------------------------


class TestGate1Main:
    def test_dry_run_returns_zero_without_connection(self, tmp_path):
        rc = main(["--report-dir", str(tmp_path)])
        assert rc == EXIT_OK
        assert not list(tmp_path.glob("gate1-report.json"))

    def test_apply_without_yes_is_dry_run(self, tmp_path):
        rc = main(
            ["--apply", "--report-dir", str(tmp_path)],
            client_factory=mongomock.MongoClient,
            env=TEST_ENV,
        )
        assert rc == EXIT_OK
        assert not list(tmp_path.glob("gate1-report.json"))

    def test_apply_missing_env_key_fails_fast_exit_3(self, tmp_path):
        env = {k: v for k, v in TEST_ENV.items() if k != "MONGODB_PASSWORD"}
        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=mongomock.MongoClient,
            env=env,
        )
        assert rc == EXIT_CONN

    def test_apply_success_writes_report(self, tmp_path):
        from datetime import datetime, timezone

        db = _db()
        ref_path = make_reference_csv(tmp_path)
        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
            reference_path=str(ref_path),
            now_fn=lambda: datetime(2026, 7, 31, 0, 0, 0, tzinfo=timezone.utc),
        )
        assert rc == EXIT_OK
        report_path = tmp_path / "gate1-report.json"
        assert report_path.exists()
        payload = json.loads(report_path.read_text())
        assert payload["expected_sector_codes"] == sorted(EXPECTED_UNIVERSE)
        assert payload["expected_sector_names"] == EXPECTED_UNIVERSE
        assert payload["trade_date_range"] == {
            "min": "2026-07-10",
            "max": "2026-07-14",
        }
        assert payload["canary_candidates"] == ["2026-07-10", "2026-07-13", "2026-07-14"]
        assert payload["recommended_canary"] == "2026-07-14"
        assert payload["stop_conditions_hit"] == []
        assert "G1-C-001" in payload["checks"]
        md_path = tmp_path / "gate1-report.md"
        assert md_path.exists()

    def test_apply_is_read_only(self, tmp_path):
        db = _db()
        ref_path = make_reference_csv(tmp_path)
        before_daily = db["index_daily_quotes"].estimated_document_count()
        before_basic = db["index_basic_info"].estimated_document_count()

        def factory(**kwargs):
            return _ClientShim(db)

        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=factory,
            env=TEST_ENV,
            reference_path=str(ref_path),
        )
        assert rc == EXIT_OK
        assert db["index_daily_quotes"].estimated_document_count() == before_daily
        assert db["index_basic_info"].estimated_document_count() == before_basic

    def test_apply_realtime_marker_stops_exit_2(self, tmp_path):
        db = _db(rt_source="realtime")
        ref_path = make_reference_csv(tmp_path)

        def factory(**kwargs):
            return _ClientShim(db)

        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=factory,
            env=TEST_ENV,
            reference_path=str(ref_path),
        )
        assert rc == EXIT_STOP
        payload = json.loads((tmp_path / "gate1-report.json").read_text())
        assert "G1-S-006" in payload["stop_conditions_hit"]

    def test_apply_empty_universe_stops_exit_2(self, tmp_path):
        db = make_mongomock_db(index_daily=make_sw_index_docs())
        ref_path = make_reference_csv(tmp_path)

        def factory(**kwargs):
            return _ClientShim(db)

        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=factory,
            env=TEST_ENV,
            reference_path=str(ref_path),
        )
        assert rc == EXIT_STOP
        payload = json.loads((tmp_path / "gate1-report.json").read_text())
        assert "G1-S-002" in payload["stop_conditions_hit"]


class _ClientShim:
    """mongomock client shim：load_db 时返回预置 db（避免二次构造）。"""

    def __init__(self, db) -> None:
        self._db = db

    def get_database(self, name: str):
        return self._db
