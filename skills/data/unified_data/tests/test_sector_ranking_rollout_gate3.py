"""Offline tests for Gate-3 (gate3_backfill.py + prod_repository.ProdRankingWriter) — 03-016 rollout.

DESIGN-03-016 V0.4 §3.6 / SPEC-03-016 §3.4. All tests run against
mongomock with explicit ``client_factory`` / ``env`` injection —
**zero environment reads and zero real I/O** (CL-5).

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import mongomock
import pytest

from scripts.unified_data.sector_ranking_rollout.common import (
    EXIT_CONN,
    EXIT_OK,
    EXIT_PARAM,
    EXIT_STOP,
)
from scripts.unified_data.sector_ranking_rollout.prod_repository import (
    NamespaceViolation,
    ProdRankingWriter,
)
from skills.data.unified_data.models.domain.sector_ranking import SectorRankingDaily
from skills.data.unified_data.tests.fixtures.sector_ranking_rollout_fixtures import (
    AVAILABLE_DATES,
    DATASET,
    EXPECTED_UNIVERSE,
    make_gate1_report,
    make_mongomock_db,
    make_sw_index_docs,
)

TEST_ENV = {
    "MONGODB_HOST": "mongo-host-1",
    "MONGODB_PORT": "27017",
    "MONGODB_USERNAME": "svc-user",
    "MONGODB_PASSWORD": "svc-pass-123",
    "MONGODB_DATABASE": "tradingagents",
}


class _ClientShim:
    def __init__(self, db) -> None:
        self._db = db

    def get_database(self, name: str):
        return self._db


def _fresh_db() -> Any:
    return mongomock.MongoClient().get_database("tradingagents")


def _make_row(
    *,
    sector_code: str,
    sector_name: str,
    pct_chg: float,
    rank: int,
    close: float,
    pre_close: float,
    trade_date: str = "2026-07-13",
    dataset: str = DATASET,
    updated_at: str = "2026-07-31T12:00:00Z",
) -> dict:
    return asdict(
        SectorRankingDaily(
            dataset=dataset,
            trade_date=trade_date,
            sector_code=sector_code,
            sector_name=sector_name,
            pct_chg=pct_chg,
            rank=rank,
            close=close,
            pre_close=pre_close,
            updated_at=updated_at,
        )
    )


def _complete_rows(trade_date: str = "2026-07-13") -> list[dict]:
    return [
        _make_row(
            sector_code="801780",
            sector_name="银行",
            pct_chg=1.666667,
            rank=1,
            close=3050.0,
            pre_close=3000.0,
            trade_date=trade_date,
        ),
        _make_row(
            sector_code="801010",
            sector_name="农林牧渔",
            pct_chg=1.0,
            rank=2,
            close=1010.0,
            pre_close=1000.0,
            trade_date=trade_date,
        ),
        _make_row(
            sector_code="801080",
            sector_name="电子",
            pct_chg=-1.0,
            rank=3,
            close=1980.0,
            pre_close=2000.0,
            trade_date=trade_date,
        ),
    ]


# ---------------------------------------------------------------------------
# ProdRankingWriter（DESIGN §3.6.1）
# ---------------------------------------------------------------------------


class TestProdRankingWriter:
    def test_upsert_persists_rows_and_returns_outcome(self):
        writer = ProdRankingWriter(_fresh_db())
        rows = _complete_rows()
        outcome = writer.upsert(rows)
        assert outcome.persisted == len(rows)
        assert outcome.failed == 0
        assert writer.count({"dataset": DATASET, "trade_date": "2026-07-13"}) == 3

    def test_get_reads_back_rows_by_filter(self):
        writer = ProdRankingWriter(_fresh_db())
        writer.upsert(_complete_rows())
        rows = writer.get(
            filter={"dataset": DATASET, "trade_date": "2026-07-13"}
        )
        assert len(rows) == 3
        codes = {r["sector_code"] for r in rows}
        assert codes == set(EXPECTED_UNIVERSE)

    def test_get_rejects_foreign_collection(self):
        writer = ProdRankingWriter(_fresh_db())
        with pytest.raises(NamespaceViolation):
            writer.get(collection="portfolio_position", filter={})

    def test_upsert_and_count_are_namespace_pinned(self):
        writer = ProdRankingWriter(_fresh_db())
        # upsert/count/estimated_document_count 无 collection 参数——全部
        # 固定写目标 COLLECTION（DESIGN §3.6.1 约束：拒绝目标集合外读写）。
        outcome = writer.upsert(_complete_rows())
        assert outcome.persisted == 3
        assert writer.count({"dataset": DATASET}) == 3
        # get() 显式传入非白名单集合 → NamespaceViolation
        with pytest.raises(NamespaceViolation):
            writer.get(collection="portfolio_position", filter={})

    def test_estimated_document_count_after_upsert(self):
        writer = ProdRankingWriter(_fresh_db())
        writer.upsert(_complete_rows())
        assert writer.estimated_document_count() == 3

    def test_upsert_is_idempotent_by_unique_key(self):
        writer = ProdRankingWriter(_fresh_db())
        writer.upsert(_complete_rows())
        second = _complete_rows()
        second[0]["close"] = 3051.0  # 覆盖 801780
        outcome = writer.upsert(second)
        assert outcome.persisted == 3
        assert writer.estimated_document_count() == 3
        rows = writer.get(filter={"dataset": DATASET, "trade_date": "2026-07-13"})
        updated = next(r for r in rows if r["sector_code"] == "801780")
        assert updated["close"] == 3051.0

    def test_constructor_rejects_none_db(self):
        with pytest.raises(TypeError):
            ProdRankingWriter(None)


# ---------------------------------------------------------------------------
# 范围解析（DESIGN §3.6.3 / SPEC G3-B-013~016 / G3-S-003）
# ---------------------------------------------------------------------------


def _policy(
    trading_days: set[str] | None = None,
    now: datetime | None = None,
) -> Any:
    from scripts.unified_data.sector_ranking_rollout.common import (
        CompletedSessionPolicy,
        FakeTradeCalendar,
    )

    days = trading_days if trading_days is not None else set(AVAILABLE_DATES)
    clock = now if now is not None else datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    return CompletedSessionPolicy(FakeTradeCalendar(days), now_fn=lambda: clock)


def _load_report(tmp_path) -> dict:
    path = make_gate1_report(tmp_path)
    return json.loads(path.read_text(encoding="utf-8"))


class TestRangeResolution:
    def test_canary_single_day_mode_without_range_source(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            resolve_range,
        )

        report = _load_report(tmp_path)
        plan = resolve_range(
            report,
            canary_date="2026-07-14",
            range_file=None,
            start_date=None,
            end_date=None,
            policy=None,
        )
        assert plan.mode == "canary"
        assert plan.dates == ["2026-07-14"]
        assert plan.excluded_first is None

    def test_canary_not_in_candidates_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date="2026-07-10",  # 不在 canary_candidates
                range_file=None,
                start_date=None,
                end_date=None,
                policy=None,
            )
        assert exc.value.sc_id == "G3-S-003"
        assert exc.value.exit_code == EXIT_PARAM

    def test_canary_plus_range_file_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date="2026-07-14",
                range_file="x.json",
                start_date=None,
                end_date=None,
                policy=None,
            )
        assert exc.value.sc_id == "G3-S-003"
        assert exc.value.exit_code == EXIT_PARAM

    def test_canary_plus_paired_start_end_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date="2026-07-14",
                range_file=None,
                start_date="2026-07-13",
                end_date="2026-07-14",
                policy=_policy(),
            )
        assert exc.value.sc_id == "G3-S-003"

    def test_canary_plus_unpaired_start_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date="2026-07-14",
                range_file=None,
                start_date="2026-07-13",
                end_date=None,
                policy=_policy(),
            )
        assert exc.value.sc_id == "G3-S-003"
        assert exc.value.exit_code == EXIT_PARAM

    def test_no_range_source_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file=None,
                start_date=None,
                end_date=None,
                policy=None,
            )
        assert exc.value.sc_id == "G3-S-003"
        assert exc.value.exit_code == EXIT_PARAM

    def test_range_file_takes_coverage_keys_excluding_earliest(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            resolve_range,
        )

        report = _load_report(tmp_path)
        plan = resolve_range(
            report,
            canary_date=None,
            range_file="ignored.json",  # main 负责读取该文件；此处只做解析
            start_date=None,
            end_date=None,
            policy=None,
        )
        assert plan.mode == "range"
        assert plan.dates == ["2026-07-13", "2026-07-14"]
        assert plan.excluded_first == "2026-07-10"

    def test_range_file_dedups_and_sorts(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            resolve_range,
        )

        report = _load_report(tmp_path)
        report["coverage_by_date"]["2026-07-14"] = report["coverage_by_date"][
            "2026-07-14"
        ]  # 重复键（dict 天然去重）
        plan = resolve_range(
            report,
            canary_date=None,
            range_file="x.json",
            start_date=None,
            end_date=None,
            policy=None,
        )
        assert plan.dates == sorted(set(plan.dates))
        assert "2026-07-10" not in plan.dates

    def test_range_file_plus_start_end_mutually_exclusive(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file="x.json",
                start_date="2026-07-13",
                end_date="2026-07-14",
                policy=_policy(),
            )
        assert exc.value.sc_id == "G3-S-003"
        assert exc.value.exit_code == EXIT_PARAM

    def test_start_without_end_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file=None,
                start_date="2026-07-13",
                end_date=None,
                policy=_policy(),
            )
        assert exc.value.sc_id == "G3-S-003"

    def test_end_without_start_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file=None,
                start_date=None,
                end_date="2026-07-14",
                policy=_policy(),
            )
        assert exc.value.sc_id == "G3-S-003"

    def test_start_after_end_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file=None,
                start_date="2026-07-14",
                end_date="2026-07-13",
                policy=_policy(),
            )
        assert exc.value.sc_id == "G3-S-003"

    def test_start_outside_gate1_range_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file=None,
                start_date="2026-07-09",
                end_date="2026-07-14",
                policy=_policy(),
            )
        assert exc.value.sc_id == "G3-S-003"

    def test_future_start_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file=None,
                start_date="2026-08-02",  # 未来日
                end_date="2026-08-03",
                policy=_policy(),
            )
        assert exc.value.sc_id == "G3-S-003"

    def test_today_unclosed_start_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        report["trade_date_range"] = {"min": "2026-07-10", "max": "2026-07-31"}
        # 今日=2026-07-31（交易日），clock 04:00 UTC = 12:00 CST < 15:00 → 未收盘
        policy = _policy(
            trading_days={"2026-07-31"},
            now=datetime(2026, 7, 31, 4, 0, 0, tzinfo=timezone.utc),
        )
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file=None,
                start_date="2026-07-31",
                end_date="2026-07-31",
                policy=policy,
            )
        assert exc.value.sc_id == "G3-S-003"

    def test_explicit_mode_requires_policy_fail_closed(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file=None,
                start_date="2026-07-13",
                end_date="2026-07-14",
                policy=None,
            )
        assert exc.value.sc_id == "G3-S-003"

    def test_valid_paired_range_selects_coverage_subset(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            resolve_range,
        )

        report = _load_report(tmp_path)
        plan = resolve_range(
            report,
            canary_date=None,
            range_file=None,
            start_date="2026-07-13",
            end_date="2026-07-14",
            policy=_policy(),
        )
        assert plan.mode == "range"
        assert plan.dates == ["2026-07-13", "2026-07-14"]
        assert plan.excluded_first is None


# ---------------------------------------------------------------------------
# process_day（DESIGN §3.6.4：前一日推导 / 固定 pct_chg / 完整性 / rt 剔除）
# ---------------------------------------------------------------------------


def _gate3_db(*, daily=None, basic=None) -> Any:
    from skills.data.unified_data.tests.fixtures.sector_ranking_rollout_fixtures import (
        make_index_basic_docs,
    )

    daily = daily if daily is not None else make_sw_index_docs()
    basic = basic if basic is not None else make_index_basic_docs()
    return make_mongomock_db(index_daily=daily, index_basic=basic)


class TestProcessDay:
    def test_complete_day_builds_and_upserts(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            DATASET,
            process_day,
        )

        db = _gate3_db()
        writer = ProdRankingWriter(db)
        outcome = process_day(
            "2026-07-13",
            prev_date="2026-07-10",
            expected_codes=sorted(EXPECTED_UNIVERSE),
            expected_names=EXPECTED_UNIVERSE,
            db=db,
            writer=writer,
            updated_at="2026-07-31T12:00:00Z",
        )
        assert outcome.status == "complete"
        assert outcome.expected == 3
        assert outcome.observed == 3
        assert outcome.upserted == 3
        assert outcome.failed == 0
        rows = writer.get(filter={"dataset": DATASET, "trade_date": "2026-07-13"})
        assert len(rows) == 3
        # G3-B-007：输出 trade_date 为 YYYY-MM-DD
        assert {r["trade_date"] for r in rows} == {"2026-07-13"}
        by_code = {r["sector_code"]: r for r in rows}
        # G3-B-008：pct_chg 用 close/pre_close 重算，禁止上游值
        assert by_code["801780"]["pct_chg"] == pytest.approx((3050 - 3000) / 3000 * 100)
        assert by_code["801010"]["pct_chg"] == pytest.approx((1010 - 1000) / 1000 * 100)
        assert by_code["801080"]["pct_chg"] == pytest.approx((1980 - 2000) / 2000 * 100)
        # 排序：pct_chg DESC（G3-V-003 / rank 连续 1-based）
        assert by_code["801780"]["rank"] == 1
        assert by_code["801010"]["rank"] == 2
        assert by_code["801080"]["rank"] == 3

    def test_first_day_without_prev_returns_empty(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            process_day,
        )

        db = _gate3_db()
        writer = ProdRankingWriter(db)
        outcome = process_day(
            "2026-07-10",
            prev_date=None,
            expected_codes=sorted(EXPECTED_UNIVERSE),
            expected_names=EXPECTED_UNIVERSE,
            db=db,
            writer=writer,
            updated_at="2026-07-31T12:00:00Z",
        )
        assert outcome.status == "empty"
        assert outcome.reason == "no-prev-close"
        assert writer.estimated_document_count() == 0

    def test_incomplete_day_raises_g3_s_004(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            process_day,
        )

        # 去掉 801080 在 2026-07-13 的行 → observed=2 != expected=3
        daily = [
            d
            for d in make_sw_index_docs()
            if not (d["trade_date"] == "20260713" and d["sector_code"] == "801080")
        ]
        db = _gate3_db(daily=daily)
        writer = ProdRankingWriter(db)
        with pytest.raises(Gate3Stop) as exc:
            process_day(
                "2026-07-13",
                prev_date="2026-07-10",
                expected_codes=sorted(EXPECTED_UNIVERSE),
                expected_names=EXPECTED_UNIVERSE,
                db=db,
                writer=writer,
                updated_at="2026-07-31T12:00:00Z",
            )
        assert exc.value.sc_id == "G3-S-004"
        assert exc.value.exit_code == EXIT_STOP
        # G3-B-012：incomplete 不物化
        assert writer.estimated_document_count() == 0

    def test_rt_marker_day_raises_g3_s_010(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            process_day,
        )
        from skills.data.unified_data.tests.fixtures.sector_ranking_rollout_fixtures import (
            make_sw_index_docs_rt_marker,
        )

        db = _gate3_db(daily=make_sw_index_docs_rt_marker("realtime"))
        writer = ProdRankingWriter(db)
        with pytest.raises(Gate3Stop) as exc:
            process_day(
                "2026-07-13",
                prev_date="2026-07-10",
                expected_codes=sorted(EXPECTED_UNIVERSE),
                expected_names=EXPECTED_UNIVERSE,
                db=db,
                writer=writer,
                updated_at="2026-07-31T12:00:00Z",
            )
        assert exc.value.sc_id == "G3-S-010"
        assert writer.estimated_document_count() == 0

    def test_missing_close_day_raises_g3_s_004(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            process_day,
        )
        from skills.data.unified_data.tests.fixtures.sector_ranking_rollout_fixtures import (
            make_sw_index_docs_missing_close,
        )

        db = _gate3_db(daily=make_sw_index_docs_missing_close(["801010"]))
        writer = ProdRankingWriter(db)
        with pytest.raises(Gate3Stop) as exc:
            process_day(
                "2026-07-13",
                prev_date="2026-07-10",
                expected_codes=sorted(EXPECTED_UNIVERSE),
                expected_names=EXPECTED_UNIVERSE,
                db=db,
                writer=writer,
                updated_at="2026-07-31T12:00:00Z",
            )
        assert exc.value.sc_id == "G3-S-004"


class TestReadBackVerify:
    def test_read_back_verify_passes_on_complete_day(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            read_back_verify,
        )

        db = _gate3_db()
        writer = ProdRankingWriter(db)
        writer.upsert(_complete_rows("2026-07-13"))
        # 无异常即通过
        read_back_verify(writer, "2026-07-13", sorted(EXPECTED_UNIVERSE))

    def test_read_back_verify_detects_missing_row(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            read_back_verify,
        )

        db = _gate3_db()
        writer = ProdRankingWriter(db)
        writer.upsert(_complete_rows("2026-07-13")[:2])  # 只写 2 行
        with pytest.raises(Gate3Stop) as exc:
            read_back_verify(writer, "2026-07-13", sorted(EXPECTED_UNIVERSE))
        assert exc.value.sc_id == "G3-S-007"

    def test_read_back_verify_detects_duplicate_unique_key(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            read_back_verify,
        )

        db = _gate3_db()
        rows = _complete_rows("2026-07-13")
        duplicate = dict(rows[0])
        duplicate["sector_code"] = "801010"  # 与另一行同唯一键（同 dataset/date）
        rows.append(duplicate)
        db[DATASET_COLLECTION].insert_many(rows)
        writer = ProdRankingWriter(db)
        with pytest.raises(Gate3Stop) as exc:
            read_back_verify(writer, "2026-07-13", sorted(EXPECTED_UNIVERSE))
        assert exc.value.sc_id == "G3-S-007"


DATASET_COLLECTION = "03_data_ud_sector_ranking_daily"


# ---------------------------------------------------------------------------
# main（CLI 退出码 / 日级原子 / canary 不进入全量 / report 产物）
# ---------------------------------------------------------------------------


class TestGate3Main:
    def test_dry_run_returns_zero_without_connection(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path)
        rc = main(
            [
                "--expected-file", str(report_path),
                "--canary-date", "2026-07-14",
                "--report-dir", str(tmp_path / "out"),
            ]
        )
        assert rc == EXIT_OK
        assert not (tmp_path / "out" / "gate3-report.json").exists()

    def test_apply_without_yes_is_dry_run(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path)
        rc = main(
            [
                "--expected-file", str(report_path),
                "--canary-date", "2026-07-14",
                "--apply",
                "--report-dir", str(tmp_path / "out"),
            ],
            client_factory=mongomock.MongoClient,
            env=TEST_ENV,
        )
        assert rc == EXIT_OK
        assert not (tmp_path / "out" / "gate3-report.json").exists()

    def test_missing_expected_file_exit_1(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        rc = main(
            ["--expected-file", str(tmp_path / "nope.json"),
             "--canary-date", "2026-07-14", "--report-dir", str(tmp_path / "out")]
        )
        assert rc == EXIT_PARAM

    def test_incomplete_expected_json_exit_1(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"expected_sector_codes": ["801010"]}))
        rc = main(
            ["--expected-file", str(bad), "--canary-date", "2026-07-14",
             "--report-dir", str(tmp_path / "out")]
        )
        assert rc == EXIT_PARAM

    def test_no_range_source_exit_1(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path)
        rc = main(
            ["--expected-file", str(report_path), "--report-dir", str(tmp_path / "out")]
        )
        assert rc == EXIT_PARAM

    def test_canary_success_writes_report_and_materializes_day(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path)
        db = _gate3_db()
        out = tmp_path / "out"
        rc = main(
            [
                "--expected-file", str(report_path),
                "--canary-date", "2026-07-14",
                "--apply", "--yes",
                "--report-dir", str(out),
            ],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
            updated_at="2026-07-31T12:00:00Z",
        )
        assert rc == EXIT_OK
        rows = db[DATASET_COLLECTION].find({"trade_date": "2026-07-14"})
        assert len(list(rows)) == 3
        payload = json.loads((out / "gate3-report.json").read_text())
        assert payload["stop_conditions_hit"] == []
        assert payload["summary"]["success_days"] == 1
        assert payload["canary"]["date"] == "2026-07-14"

    def test_full_range_materializes_all_days_in_order(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path)
        db = _gate3_db()
        out = tmp_path / "out"
        rc = main(
            [
                "--expected-file", str(report_path),
                "--range-file", str(report_path),
                "--apply", "--yes",
                "--report-dir", str(out),
            ],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
            updated_at="2026-07-31T12:00:00Z",
        )
        assert rc == EXIT_OK
        assert db[DATASET_COLLECTION].count_documents({"dataset": "sw2021_ta_cn"}) == 6
        dates = sorted(
            {d["trade_date"] for d in db[DATASET_COLLECTION].find({})}
        )
        assert dates == ["2026-07-13", "2026-07-14"]  # 07-10 被默认排除
        payload = json.loads((out / "gate3-report.json").read_text())
        assert payload["range"]["excluded_first"] == "2026-07-10"
        assert payload["summary"]["success_days"] == 2

    def test_day_failure_stops_subsequent_days(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path)
        # 07-13 缺 801080 → G3-S-004；07-14 不应被处理（G3-B-002 日级原子）
        daily = [
            d
            for d in make_sw_index_docs()
            if not (d["trade_date"] == "20260713" and d["sector_code"] == "801080")
        ]
        db = _gate3_db(daily=daily)
        out = tmp_path / "out"
        rc = main(
            [
                "--expected-file", str(report_path),
                "--range-file", str(report_path),
                "--apply", "--yes",
                "--report-dir", str(out),
            ],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
            updated_at="2026-07-31T12:00:00Z",
        )
        assert rc == EXIT_STOP
        payload = json.loads((out / "gate3-report.json").read_text())
        assert "G3-S-004" in payload["stop_conditions_hit"]
        # 07-14 未物化
        assert db[DATASET_COLLECTION].count_documents({"trade_date": "2026-07-14"}) == 0

    def test_canary_not_in_candidates_exit_1(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path)
        rc = main(
            [
                "--expected-file", str(report_path),
                "--canary-date", "2026-07-10",
                "--apply", "--yes",
                "--report-dir", str(tmp_path / "out"),
            ],
            client_factory=mongomock.MongoClient,
            env=TEST_ENV,
        )
        assert rc == EXIT_PARAM
