"""Offline tests for Gate-1 (gate1_smoke.py) — 03-016 rollout.

DESIGN-03-016 V0.6 §3.4 / SPEC-03-016 §3.2（L1 契约校正）。All tests run
against mongomock with explicit ``client_factory`` / ``env`` injection —
**zero environment reads and zero real I/O** (CL-5).

L1 universe 唯一主来源 = ``stock_sector_info``（``classify_system=\"SW\"``
distinct ``(l1_code,l1_name)`` 恰好 31）；行情 join field =
``index_daily_quotes.full_symbol``（``.SI`` 后缀值集）。``index_basic_info``
不得作为 L1 主来源。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import mongomock
import pytest

from scripts.unified_data.sector_ranking_rollout.common import (
    EXIT_CONN,
    EXIT_OK,
    EXIT_STOP,
    BudgetReader,
)
from scripts.unified_data.sector_ranking_rollout.gate1_smoke import (
    EXPECTED_L1_COUNT,
    Gate1Stop,
    UNIVERSE_SOURCE,
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
    EXPECTED_UNIVERSE_31,
    EXPECTED_UNIVERSE_SI,
    make_mismatch_reference_csv,
    make_mongomock_db,
    make_reference_csv,
    make_stock_sector_info_docs,
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


def _db(
    *,
    universe: dict[str, str] | None = None,
    rt_source: str | None = None,
    missing_close: list[str] | None = None,
):
    uni = universe if universe is not None else EXPECTED_UNIVERSE_31
    daily = make_sw_index_docs(codes=uni)
    if rt_source is not None:
        daily = make_sw_index_docs_rt_marker(rt_source, universe=uni)
    if missing_close:
        daily = make_sw_index_docs_missing_close(missing_close, universe=uni)
    return make_mongomock_db(
        index_daily=daily,
        stock_sector_info=make_stock_sector_info_docs(universe=uni),
    )


class _BudgetReaderSpy(BudgetReader):
    """BudgetReader spy：记录 find/distinct/aggregate 调用，可注入聚合结果。

    仅用于 ``check_close_completeness`` 的查询模式/预算证明（CL-5 零真实
    I/O）：复用父类 ``_record`` 记账，使 ``stats()`` 反映真实 BudgetReader
    会计；``aggregate_rows`` 非空时跳过底层 mongomock 聚合（高日期规模下
    mongomock ``$addToSet`` 过慢），直接注入按日期分组的行。
    """

    def __init__(self, db: Any, *, aggregate_rows: list[dict[str, Any]] | None = None):
        super().__init__(db)
        self.calls: list[str] = []
        self._aggregate_rows = aggregate_rows

    def find(self, collection, filter, *, limit=1000, projection=None):
        self.calls.append("find")
        return super().find(collection, filter, limit=limit, projection=projection)

    def distinct(self, collection, key, filter):
        self.calls.append("distinct")
        return super().distinct(collection, key, filter)

    def aggregate(self, collection, pipeline):
        self.calls.append("aggregate")
        if self._aggregate_rows is None:
            return super().aggregate(collection, pipeline)
        import time as time_mod

        start = time_mod.monotonic()
        self._record(
            "aggregate", len(self._aggregate_rows), time_mod.monotonic() - start
        )
        return list(self._aggregate_rows)


# ---------------------------------------------------------------------------
# enumerate_sw_l1（G1-C-001 / G1-S-002 / G1-S-003；主来源 stock_sector_info）
# ---------------------------------------------------------------------------


class TestEnumerateSwL1:
    def test_returns_31_l1_from_stock_sector_info(self):
        db = _db()
        universe = enumerate_sw_l1(db)
        assert universe == EXPECTED_UNIVERSE_31
        assert len(universe) == EXPECTED_L1_COUNT
        # canonical code = .SI 后缀（G1-S-003 通过）
        assert all(code.endswith(".SI") for code in universe)

    def test_empty_stock_sector_info_stops_g1_s_002(self):
        db = make_mongomock_db(index_daily=make_sw_index_docs(codes=EXPECTED_UNIVERSE_31))
        with pytest.raises(Gate1Stop) as exc:
            enumerate_sw_l1(db)
        assert exc.value.sc_id == "G1-S-002"

    def test_wrong_count_stops_g1_s_002(self):
        # 3 code 小集合 ≠ 31 → G1-S-002（非 31 停止）
        db = make_mongomock_db(
            index_daily=make_sw_index_docs(codes=EXPECTED_UNIVERSE_SI),
            stock_sector_info=make_stock_sector_info_docs(universe=EXPECTED_UNIVERSE_SI),
        )
        with pytest.raises(Gate1Stop) as exc:
            enumerate_sw_l1(db)
        assert exc.value.sc_id == "G1-S-002"

    def test_duplicate_l1_code_stops_g1_s_003(self):
        # 相同 l1_code 但不同 l1_name → distinct (l1_code, l1_name) 出现重复
        # l1_code → G1-S-003。
        docs = make_stock_sector_info_docs()
        dup = dict(docs[0])
        dup["l1_name"] = "农林牧渔（重复名）"  # 同 l1_code 801010.SI，不同 name
        docs.append(dup)
        db = make_mongomock_db(
            index_daily=make_sw_index_docs(codes=EXPECTED_UNIVERSE_31),
            stock_sector_info=docs,
        )
        with pytest.raises(Gate1Stop) as exc:
            enumerate_sw_l1(db)
        assert exc.value.sc_id == "G1-S-003"

    def test_non_si_l1_code_stops_g1_s_003(self):
        # 非 .SI 后缀 canonical 形态 → G1-S-003（旧 sector_code 形态被拒绝）
        uni = dict(EXPECTED_UNIVERSE_31)
        uni["801990"] = "非法形态"
        docs = make_stock_sector_info_docs(universe=uni)
        # 替换一个为无 .SI 后缀的 code
        docs[-1]["l1_code"] = "801990"
        db = make_mongomock_db(
            index_daily=make_sw_index_docs(codes=EXPECTED_UNIVERSE_31),
            stock_sector_info=docs,
        )
        with pytest.raises(Gate1Stop) as exc:
            enumerate_sw_l1(db)
        assert exc.value.sc_id == "G1-S-003"

    def test_non_sw_classify_system_excluded(self):
        # 非 SW 的 classify_system 不进入 universe（$match 过滤，G1-C-006 隔离）
        uni = dict(EXPECTED_UNIVERSE_31)
        docs = make_stock_sector_info_docs(universe=uni)
        docs.append(
            {
                "l1_code": "999999.SI",
                "l1_name": "概念指数",
                "classify_system": "concept",
            }
        )
        db = make_mongomock_db(
            index_daily=make_sw_index_docs(codes=EXPECTED_UNIVERSE_31),
            stock_sector_info=docs,
        )
        universe = enumerate_sw_l1(db)
        assert "999999.SI" not in universe


# ---------------------------------------------------------------------------
# cross_check_reference（G1-C-001 可选交叉核对 / OQ-016-2：不阻断主 universe）
# ---------------------------------------------------------------------------


class TestCrossCheckReference:
    def test_missing_reference_file_reports_reference_missing(self, tmp_path):
        missing_path = tmp_path / "reference" / "sw_l1_reference.csv"
        discrepancies, ref_missing = cross_check_reference(
            EXPECTED_UNIVERSE_SI, str(missing_path)
        )
        assert ref_missing is True
        assert discrepancies == []

    def test_matching_reference_has_no_discrepancies(self, tmp_path):
        ref_path = make_reference_csv(tmp_path)
        discrepancies, ref_missing = cross_check_reference(
            EXPECTED_UNIVERSE_SI, str(ref_path)
        )
        assert ref_missing is False
        assert discrepancies == []

    def test_mismatch_reference_records_discrepancies(self, tmp_path):
        ref_path = make_mismatch_reference_csv(tmp_path)
        discrepancies, ref_missing = cross_check_reference(
            EXPECTED_UNIVERSE_SI, str(ref_path)
        )
        assert ref_missing is False
        kinds = {d["kind"] for d in discrepancies}
        assert "name_mismatch" in kinds  # 801010.SI name 不一致
        assert "db_only" in kinds  # 801080.SI db 有 reference 无
        assert "ref_only" in kinds  # 801999.SI reference 有 db 无


# ---------------------------------------------------------------------------
# compute_coverage（G1-C-003；join field = full_symbol）
# ---------------------------------------------------------------------------


class TestComputeCoverage:
    def test_coverage_by_date_and_range(self):
        db = _db()
        date_range, coverage = compute_coverage(db, EXPECTED_UNIVERSE_31)
        assert date_range == {"min": "2026-07-10", "max": "2026-07-14"}
        assert set(coverage) == set(AVAILABLE_DATES)
        for entry in coverage.values():
            assert entry["expected"] == EXPECTED_L1_COUNT
            assert entry["observed"] == EXPECTED_L1_COUNT
            assert entry["ratio"] == 1.0

    def test_coverage_marks_partial_days(self):
        db = _db()
        # 去掉 801080.SI 在 2026-07-13 的行 → 该日 observed=30
        daily = make_sw_index_docs(codes=EXPECTED_UNIVERSE_31)
        daily = [
            d
            for d in daily
            if not (
                d["trade_date"] == "20260713" and d["full_symbol"] == "801080.SI"
            )
        ]
        db2 = make_mongomock_db(
            index_daily=daily,
            stock_sector_info=make_stock_sector_info_docs(universe=EXPECTED_UNIVERSE_31),
        )
        _, coverage = compute_coverage(db2, EXPECTED_UNIVERSE_31)
        assert coverage["2026-07-13"]["observed"] == 30
        assert coverage["2026-07-13"]["ratio"] == pytest.approx(30 / 31)

    def test_min_max_trade_date_filter(self):
        db = _db()
        _, coverage = compute_coverage(
            db, EXPECTED_UNIVERSE_31, min_trade_date="2026-07-13"
        )
        assert set(coverage) == {"2026-07-13", "2026-07-14"}


# ---------------------------------------------------------------------------
# check_close_completeness（G1-C-004；full_symbol join）
# ---------------------------------------------------------------------------


class TestCloseCompleteness:
    def test_complete_days_have_no_missing(self):
        db = _db()
        missing = check_close_completeness(db, EXPECTED_UNIVERSE_31)
        assert missing == {d: [] for d in AVAILABLE_DATES}

    def test_missing_close_recorded(self):
        db = _db(missing_close=["801010.SI"])
        missing = check_close_completeness(db, EXPECTED_UNIVERSE_31)
        assert "801010.SI" in missing["2026-07-13"]

    def test_single_aggregate_no_find(self):
        # 回归（G1-S-007）：close completeness 必须单次 aggregate，不得
        # distinct dates + 逐日 find（N-date 查询模式）。
        db = _db()
        spy = _BudgetReaderSpy(db)
        missing = check_close_completeness(db, EXPECTED_UNIVERSE_31, budget=spy)
        assert missing == {d: [] for d in AVAILABLE_DATES}
        assert spy.calls == ["aggregate"]
        stats = spy.stats()
        assert [s["kind"] for s in stats] == ["aggregate"]
        assert stats[0]["count"] == 1
        assert stats[0]["rows"] == len(AVAILABLE_DATES)

    def test_budget_at_gate1_scale_4592_dates(self):
        # 真实 Gate-1 规模特征（失败证据：4,592 个 trade_date）：聚合实现
        # 只按日期数计行，远低于 100,000 累计上限；旧实现 4,592 轮 find 产生
        # 87,099 行 + distinct 6,422 → 触发 G1-S-007。reader spy 注入按日期
        # 分组的聚合行，复用真实 BudgetReader._record 会计（CL-5 零真实 I/O）。
        db = _db()
        internal_dates = [
            (date(2010, 1, 1) + timedelta(days=i)).strftime("%Y%m%d")
            for i in range(4592)
        ]
        sample_codes = list(EXPECTED_UNIVERSE_SI)
        spy = _BudgetReaderSpy(
            db,
            aggregate_rows=[
                {
                    "_id": internal,
                    "symbols": [
                        {"symbol": code, "close": 1000.0} for code in sample_codes
                    ],
                }
                for internal in internal_dates
            ],
        )
        missing = check_close_completeness(db, EXPECTED_UNIVERSE_31, budget=spy)
        expected_external = {
            f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in internal_dates
        }
        assert set(missing) == expected_external
        assert all(value == [] for value in missing.values())
        assert spy.calls == ["aggregate"]
        stats = spy.stats()
        assert [s["kind"] for s in stats] == ["aggregate"]
        assert stats[0]["count"] == 1
        assert stats[0]["rows"] == 4592
        assert sum(s["rows"] for s in stats) < 100_000

    def test_mixed_close_semantics_match_old_behavior(self):
        # 回归（G1-S-007）：聚合实现与旧逐日 find 语义一致——close 缺失 /
        # 非有限 / 非数值字符串 → 缺失；数值字符串 → 有效；完整日期 → 空列表。
        daily = make_sw_index_docs(codes=EXPECTED_UNIVERSE_31)
        for doc in daily:
            if doc["trade_date"] == "20260713" and doc["full_symbol"] == "801010.SI":
                doc["close"] = None
            if doc["trade_date"] == "20260713" and doc["full_symbol"] == "801080.SI":
                doc["close"] = "nan"  # 非有限字符串 → 缺失
            if doc["trade_date"] == "20260714" and doc["full_symbol"] == "801780.SI":
                doc["close"] = float("nan")  # 非有限 float → 缺失
            if doc["trade_date"] == "20260714" and doc["full_symbol"] == "801030.SI":
                doc["close"] = "1980.5"  # 数值字符串 → 有效
        db = make_mongomock_db(
            index_daily=daily,
            stock_sector_info=make_stock_sector_info_docs(universe=EXPECTED_UNIVERSE_31),
        )
        missing = check_close_completeness(db, EXPECTED_UNIVERSE_31)
        assert missing["2026-07-10"] == []
        assert missing["2026-07-13"] == ["801010.SI", "801080.SI"]
        assert missing["2026-07-14"] == ["801780.SI"]


# ---------------------------------------------------------------------------
# check_source_distribution（G1-C-005 / G1-S-006；full_symbol join）
# ---------------------------------------------------------------------------


class TestSourceDistribution:
    def test_sw_source_distribution(self):
        db = _db()
        source_dist, markers = check_source_distribution(db, EXPECTED_UNIVERSE_31)
        assert source_dist.get("sw") == EXPECTED_L1_COUNT * 3
        assert markers == []

    def test_realtime_marker_detected(self):
        db = _db(rt_source="realtime")
        _, markers = check_source_distribution(db, EXPECTED_UNIVERSE_31)
        assert "realtime" in markers


# ---------------------------------------------------------------------------
# select_candidates（G1-C-003/004 + OQ-016-3）
# ---------------------------------------------------------------------------


class TestSelectCandidates:
    def test_full_coverage_dates_are_candidates(self):
        coverage = {
            d: {"expected": 31, "observed": 31, "ratio": 1.0} for d in AVAILABLE_DATES
        }
        candidates, recommended = select_candidates(
            coverage, {d: [] for d in AVAILABLE_DATES}, today="2026-07-10"
        )
        assert candidates == ["2026-07-13", "2026-07-14"]
        assert recommended == "2026-07-14"

    def test_partial_day_excluded(self):
        coverage = {
            d: {"expected": 31, "observed": 31, "ratio": 1.0} for d in AVAILABLE_DATES
        }
        coverage["2026-07-14"]["observed"] = 30
        coverage["2026-07-14"]["ratio"] = 30 / 31
        candidates, _ = select_candidates(
            coverage, {d: [] for d in AVAILABLE_DATES}, today="2026-07-10"
        )
        assert "2026-07-14" not in candidates

    def test_missing_close_day_excluded(self):
        coverage = {
            d: {"expected": 31, "observed": 31, "ratio": 1.0} for d in AVAILABLE_DATES
        }
        close_missing = {d: [] for d in AVAILABLE_DATES}
        close_missing["2026-07-13"] = ["801010.SI"]
        candidates, _ = select_candidates(coverage, close_missing, today="2026-07-10")
        assert "2026-07-13" not in candidates

    def test_today_excluded(self):
        coverage = {
            d: {"expected": 31, "observed": 31, "ratio": 1.0} for d in AVAILABLE_DATES
        }
        candidates, _ = select_candidates(
            coverage, {d: [] for d in AVAILABLE_DATES}, today="2026-07-14"
        )
        assert "2026-07-14" not in candidates

    def test_no_candidates_when_none_full(self):
        coverage = {
            d: {"expected": 31, "observed": 30, "ratio": 30 / 31}
            for d in AVAILABLE_DATES
        }
        candidates, recommended = select_candidates(
            coverage, {d: [] for d in AVAILABLE_DATES}, today="2026-07-10"
        )
        assert candidates == []
        assert recommended is None


# ---------------------------------------------------------------------------
# build_report（G1-R-001 ~ G1-R-010，L1 契约校正：expected_full_symbols）
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
            expected_sector_codes=sorted(EXPECTED_UNIVERSE_31),
            expected_sector_names=EXPECTED_UNIVERSE_31,
            expected_full_symbols=sorted(EXPECTED_UNIVERSE_31),
            universe_source=UNIVERSE_SOURCE,
            trade_date_range={"min": "2026-07-10", "max": "2026-07-14"},
            trade_date_format="YYYYMMDD",
            coverage_by_date={},
            close_missing_by_date={},
            source_distribution={"sw": 93},
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
            "expected_full_symbols",
            "universe_source",
            "trade_date_range",
            "coverage_by_date",
            "source_distribution",
            "canary_candidates",
            "checks",
            "stop_conditions_hit",
        ):
            assert key in payload
        assert payload["expected_full_symbols"] == sorted(EXPECTED_UNIVERSE_31)
        assert payload["universe_source"] == "stock_sector_info"
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
        assert payload["expected_sector_codes"] == sorted(EXPECTED_UNIVERSE_31)
        assert payload["expected_sector_names"] == EXPECTED_UNIVERSE_31
        assert payload["expected_full_symbols"] == sorted(EXPECTED_UNIVERSE_31)
        assert payload["universe_source"] == "stock_sector_info"
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
        before_sector = db["stock_sector_info"].estimated_document_count()

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
        assert db["stock_sector_info"].estimated_document_count() == before_sector

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
        db = make_mongomock_db(index_daily=make_sw_index_docs(codes=EXPECTED_UNIVERSE_31))
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

    def test_apply_wrong_l1_count_stops_exit_2(self, tmp_path):
        # 非 31（3 code）→ G1-S-002
        db = make_mongomock_db(
            index_daily=make_sw_index_docs(codes=EXPECTED_UNIVERSE_SI),
            stock_sector_info=make_stock_sector_info_docs(universe=EXPECTED_UNIVERSE_SI),
        )
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

    def test_apply_missing_reference_does_not_block(self, tmp_path):
        # L1 契约校正：reference 缺失只记录，不阻断主 universe。
        db = _db()

        def factory(**kwargs):
            return _ClientShim(db)

        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=factory,
            env=TEST_ENV,
            reference_path=str(tmp_path / "reference" / "missing.csv"),
        )
        assert rc == EXIT_OK
        payload = json.loads((tmp_path / "gate1-report.json").read_text())
        assert payload["stop_conditions_hit"] == []
        kinds = {d.get("kind") for d in payload["discrepancies"]}
        assert "reference_missing" in kinds

    def test_apply_yyyy_mm_dd_source_close_missing_detected(self, tmp_path):
        # 回归（03-016 T5 MINOR-1）：源 trade_date 为 YYYY-MM-DD 时，
        # check_close_completeness 必须收到 _detect_source_format 探测出的
        # trade_date_format；否则默认 YYYYMMDD 会把内部日期转成 20260713
        # 查不到行 → close_missing 漏报、G1-C-004 fail-stop 静默失效。
        from datetime import datetime, timezone

        daily = make_sw_index_docs(codes=EXPECTED_UNIVERSE_31)
        for doc in daily:
            doc["trade_date"] = (
                f"{doc['trade_date'][:4]}-{doc['trade_date'][4:6]}-{doc['trade_date'][6:]}"
            )
            if doc["trade_date"] == "2026-07-13" and doc["full_symbol"] == "801010.SI":
                doc["close"] = None
        db = make_mongomock_db(
            index_daily=daily,
            stock_sector_info=make_stock_sector_info_docs(universe=EXPECTED_UNIVERSE_31),
        )
        ref_path = make_reference_csv(tmp_path)

        def factory(**kwargs):
            return _ClientShim(db)

        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=factory,
            env=TEST_ENV,
            reference_path=str(ref_path),
            now_fn=lambda: datetime(2026, 7, 31, 0, 0, 0, tzinfo=timezone.utc),
        )
        assert rc == EXIT_OK
        payload = json.loads((tmp_path / "gate1-report.json").read_text())
        # G1-C-004：YYYY-MM-DD 源 close=None 必须被检出（修复前漏报为 []）。
        assert "801010.SI" in payload["close_missing_by_date"]["2026-07-13"]
        # fail-stop 证据：该日不得进入 canary candidates。
        assert "2026-07-13" not in payload["canary_candidates"]


class _ClientShim:
    """mongomock client shim：load_db 时返回预置 db（避免二次构造）。"""

    def __init__(self, db) -> None:
        self._db = db

    def get_database(self, name: str):
        return self._db
