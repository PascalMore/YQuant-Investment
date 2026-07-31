"""Offline tests for Gate-4 (gate4_activate.py + prod_repository.ProdRankingReader) — 03-016 rollout.

DESIGN-03-016 V0.4 §3.7 / SPEC-03-016 §3.5. All tests run against
mongomock with explicit injection (client_factory / env / policy /
git_runner) — **zero environment reads, zero real I/O, zero real Git** (CL-5).

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import mongomock
import pytest

from scripts.unified_data.sector_ranking_rollout.common import (
    EXIT_OK,
    EXIT_PARAM,
    EXIT_STOP,
    CompletedSessionPolicy,
    FakeTradeCalendar,
    PolicyUnavailableError,
)
from scripts.unified_data.sector_ranking_rollout.prod_repository import (
    BindingDisabledError,
    NamespaceViolation,
    ProdRankingReader,
    load_binding,
    write_binding,
)
from skills.data.unified_data.services.historical_sector_service import (
    HistoricalSectorService,
    WARNING_EMPTY,
)
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

COLLECTION = "03_data_ud_sector_ranking_daily"


class _ClientShim:
    def __init__(self, db) -> None:
        self._db = db

    def get_database(self, name: str):
        return self._db


def _fresh_db() -> Any:
    return mongomock.MongoClient().get_database("tradingagents")


def _utc(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _policy(
    trading_days: set[str] | None = None,
    now: datetime | None = None,
) -> CompletedSessionPolicy:
    days = trading_days if trading_days is not None else set(AVAILABLE_DATES)
    clock = now if now is not None else _utc(2026, 8, 1)
    return CompletedSessionPolicy(FakeTradeCalendar(days), now_fn=lambda: clock)


def _materialize_canary(db: Any, trade_date: str = "2026-07-14") -> None:
    """用 gate3 process_day 物化 canary 日（3 code 完整行）。"""
    from scripts.unified_data.sector_ranking_rollout.gate3_backfill import process_day
    from scripts.unified_data.sector_ranking_rollout.prod_repository import (
        ProdRankingWriter,
    )

    writer = ProdRankingWriter(db)
    process_day(
        trade_date,
        prev_date="2026-07-13",
        expected_codes=sorted(EXPECTED_UNIVERSE),
        expected_names=EXPECTED_UNIVERSE,
        db=db,
        writer=writer,
        updated_at="2026-07-31T12:00:00Z",
    )


def _gate4_db(*, materialize: bool = True) -> Any:
    from skills.data.unified_data.tests.fixtures.sector_ranking_rollout_fixtures import (
        make_index_basic_docs,
    )

    db = make_mongomock_db(
        index_daily=make_sw_index_docs(),
        index_basic=make_index_basic_docs(),
    )
    if materialize:
        _materialize_canary(db)
    return db


def _make_service(db: Any, *, binding=True, policy=None) -> HistoricalSectorService:
    reader = ProdRankingReader(
        db,
        binding=lambda: binding,
        policy=policy if policy is not None else _policy(),
    )
    return HistoricalSectorService(
        writer=reader,
        expected_universe_by_dataset={DATASET: sorted(EXPECTED_UNIVERSE)},
    )


# ---------------------------------------------------------------------------
# BindingState（DESIGN §3.7.1）
# ---------------------------------------------------------------------------


class TestBindingState:
    def test_load_binding_missing_is_disabled(self, tmp_path):
        assert load_binding(str(tmp_path)) == {"enabled": False}

    def test_write_then_load_binding(self, tmp_path):
        payload = write_binding(str(tmp_path), True)
        assert payload["enabled"] is True
        assert payload["capability"] == "sector.ranking_history"
        assert payload["gate"] == 4
        loaded = load_binding(str(tmp_path))
        assert loaded["enabled"] is True

    def test_write_binding_records_previous(self, tmp_path):
        write_binding(str(tmp_path), True)
        second = write_binding(str(tmp_path), False)
        assert second["previous"] is True

    def test_load_binding_corrupt_file_is_disabled(self, tmp_path):
        (tmp_path / "binding_state.json").write_text("{not json")
        assert load_binding(str(tmp_path)) == {"enabled": False}


# ---------------------------------------------------------------------------
# ProdRankingReader（DESIGN §3.7.2 / G4-P-001~010 / G4-V-104）
# ---------------------------------------------------------------------------


class TestProdRankingReader:
    def test_binding_disabled_refuses_read(self):
        db = _gate4_db()
        reader = ProdRankingReader(db, binding=lambda: False, policy=_policy())
        with pytest.raises(BindingDisabledError):
            reader.get(filter={"dataset": DATASET, "trade_date": "2026-07-14"})

    def test_policy_none_fail_closed(self):
        db = _gate4_db()
        reader = ProdRankingReader(db, binding=lambda: True, policy=None)
        with pytest.raises(PolicyUnavailableError):
            reader.get(filter={"dataset": DATASET, "trade_date": "2026-07-14"})

    def test_read_returns_materialized_rows(self):
        db = _gate4_db()
        reader = ProdRankingReader(db, binding=lambda: True, policy=_policy())
        rows = reader.get(filter={"dataset": DATASET, "trade_date": "2026-07-14"})
        assert len(rows) == 3
        assert {r["sector_code"] for r in rows} == set(EXPECTED_UNIVERSE)

    def test_foreign_collection_refused(self):
        db = _gate4_db()
        reader = ProdRankingReader(db, binding=lambda: True, policy=_policy())
        with pytest.raises(NamespaceViolation):
            reader.get(collection="portfolio_position", filter={"dataset": DATASET})

    def test_missing_dataset_filter_refused(self):
        # G4-V-005：跨 dataset 混读拒绝（dataset 强制过滤）
        db = _gate4_db()
        reader = ProdRankingReader(db, binding=lambda: True, policy=_policy())
        with pytest.raises(ValueError):
            reader.get(filter={"trade_date": "2026-07-14"})

    def test_future_date_raises_value_error(self):
        db = _gate4_db()
        reader = ProdRankingReader(
            db,
            binding=lambda: True,
            policy=_policy(now=_utc(2026, 8, 1)),
        )
        with pytest.raises(ValueError, match="ERR_FUTURE_DATE"):
            reader.get(filter={"dataset": DATASET, "trade_date": "2026-08-02"})

    def test_today_unclosed_raises_value_error(self):
        db = _gate4_db()
        policy = _policy(
            trading_days={"2026-08-01"},
            now=_utc(2026, 8, 1, 4, 0, 0),  # 12:00 CST < 15:00
        )
        reader = ProdRankingReader(db, binding=lambda: True, policy=policy)
        with pytest.raises(ValueError, match="ERR_TODAY_UNCLOSED"):
            reader.get(filter={"dataset": DATASET, "trade_date": "2026-08-01"})

    def test_today_closed_reads_without_error(self):
        db = _gate4_db()
        policy = _policy(
            trading_days={"2026-08-01"},
            now=_utc(2026, 8, 1, 7, 30, 0),  # 15:30 CST >= 15:00
        )
        reader = ProdRankingReader(db, binding=lambda: True, policy=policy)
        rows = reader.get(filter={"dataset": DATASET, "trade_date": "2026-07-14"})
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# 冻结 service 集成（G4-V-001~008 冻结 token / 排序 / limit / 只读）
# ---------------------------------------------------------------------------


class TestFrozenServiceIntegration:
    def test_complete_day_full_ranking(self):
        service = _make_service(_gate4_db())
        result = service.get_sector_ranking_history("2026-07-14", DATASET)
        assert len(result.data) == 3
        assert result.warnings == []
        assert "completeness:complete" in result.source_trace
        assert "materialized:ok" in result.source_trace

    def test_unmaterialized_day_empty_token(self):
        service = _make_service(_gate4_db())
        result = service.get_sector_ranking_history("2026-07-10", DATASET)
        assert result.data == []
        assert result.warnings == [WARNING_EMPTY]
        assert "completeness:empty" in result.source_trace
        assert "materialized:ok" in result.source_trace

    def test_invalid_trade_date_raises_value_error(self):
        service = _make_service(_gate4_db())
        with pytest.raises(ValueError):
            service.get_sector_ranking_history("2026-13-45", DATASET)

    def test_ordering_pct_chg_desc_then_code_asc(self):
        service = _make_service(_gate4_db())
        result = service.get_sector_ranking_history("2026-07-14", DATASET)
        codes = [row.sector_code for row in result.data]
        pcts = [row.pct_chg for row in result.data]
        assert pcts == sorted(pcts, reverse=True)
        assert codes == sorted(
            codes, key=lambda c: (-result.data[codes.index(c)].pct_chg, c)
        )

    def test_limit_truncates_and_zero_returns_all(self):
        service = _make_service(_gate4_db())
        result1 = service.get_sector_ranking_history("2026-07-14", DATASET, limit=1)
        assert len(result1.data) == 1
        result_all = service.get_sector_ranking_history("2026-07-14", DATASET, limit=0)
        assert len(result_all.data) == 3

    def test_cross_dataset_unknown_rejected(self):
        service = _make_service(_gate4_db())
        with pytest.raises(ValueError):
            service.get_sector_ranking_history("2026-07-14", "eastmoney_industry")

    def test_readonly_no_writes(self):
        db = _gate4_db()
        before = db[COLLECTION].estimated_document_count()
        service = _make_service(db)
        service.get_sector_ranking_history("2026-07-14", DATASET)
        service.get_sector_ranking_history("2026-07-10", DATASET)
        assert db[COLLECTION].estimated_document_count() == before

    def test_non_trading_day_past_returns_empty_token(self):
        db = _gate4_db()
        # 2026-08-02 非交易日且为过去日 → 不抛错，读路径未物化 → empty token
        policy = _policy(trading_days={"2026-08-01"}, now=_utc(2026, 8, 3))
        reader = ProdRankingReader(db, binding=lambda: True, policy=policy)
        service = HistoricalSectorService(
            writer=reader,
            expected_universe_by_dataset={DATASET: sorted(EXPECTED_UNIVERSE)},
        )
        result = service.get_sector_ranking_history("2026-08-02", DATASET)
        assert result.data == []
        assert result.warnings == [WARNING_EMPTY]


# ---------------------------------------------------------------------------
# gate4_activate main（--enable/--disable / pre/post-smoke / scope diff）
# ---------------------------------------------------------------------------


class TestGate4Main:
    def test_dry_run_returns_zero_without_connection(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate4_activate import main

        report_path = make_gate1_report(tmp_path)
        rc = main(
            ["--expected-file", str(report_path), "--report-dir", str(tmp_path / "out")]
        )
        assert rc == EXIT_OK
        assert not (tmp_path / "out" / "gate4-report.json").exists()

    def test_apply_without_yes_is_dry_run(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate4_activate import main

        report_path = make_gate1_report(tmp_path)
        rc = main(
            ["--expected-file", str(report_path), "--apply",
             "--report-dir", str(tmp_path / "out")],
            client_factory=mongomock.MongoClient,
            env=TEST_ENV,
        )
        assert rc == EXIT_OK

    def test_missing_expected_file_exit_1(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate4_activate import main

        rc = main(
            ["--expected-file", str(tmp_path / "nope.json"),
             "--report-dir", str(tmp_path / "out")]
        )
        assert rc == EXIT_PARAM

    def test_disable_drill_writes_binding_and_proves_refusal(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate4_activate import main

        report_path = make_gate1_report(tmp_path)
        db = _gate4_db()
        out = tmp_path / "out"
        rc = main(
            ["--expected-file", str(report_path), "--disable", "--apply", "--yes",
             "--report-dir", str(out)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
        )
        assert rc == EXIT_OK
        assert load_binding(str(out))["enabled"] is False
        payload = json.loads((out / "gate4-report.json").read_text())
        assert payload["binding"]["after"] is False
        # 回滚预案：绑定 reader 拒绝读取（G4-V-104）
        reader = ProdRankingReader(db, binding=lambda: load_binding(str(out))["enabled"], policy=_policy())
        with pytest.raises(BindingDisabledError):
            reader.get(filter={"dataset": DATASET, "trade_date": "2026-07-14"})

    def test_enable_without_policy_fail_closed(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate4_activate import main

        report_path = make_gate1_report(tmp_path)
        db = _gate4_db()
        out = tmp_path / "out"
        rc = main(
            ["--expected-file", str(report_path), "--enable", "--apply", "--yes",
             "--report-dir", str(out)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
        )
        assert rc == EXIT_STOP
        payload = json.loads((out / "gate4-report.json").read_text())
        assert "G4-S-002" in payload["stop_conditions_hit"]
        assert load_binding(str(out))["enabled"] is False  # 未激活

    def test_enable_success_writes_binding_and_passes_post_smoke(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate4_activate import main

        report_path = make_gate1_report(tmp_path)
        db = _gate4_db()
        out = tmp_path / "out"
        rc = main(
            ["--expected-file", str(report_path), "--enable", "--apply", "--yes",
             "--report-dir", str(out)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
            policy=_policy(),
            git_runner=lambda paths: [],
        )
        assert rc == EXIT_OK
        assert load_binding(str(out))["enabled"] is True
        payload = json.loads((out / "gate4-report.json").read_text())
        assert payload["binding"]["after"] is True
        assert payload["stop_conditions_hit"] == []
        cases = {c["id"]: c for c in payload["cases"]}
        assert all(c["passed"] for c in cases.values())

    def test_enable_presmoke_failure_keeps_binding_disabled(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate4_activate import main

        report_path = make_gate1_report(tmp_path)
        db = _gate4_db(materialize=False)  # 未物化 07-14
        # 只 upsert 2 行 → 读回 incomplete token → pre-smoke 失败 → G4-S-002
        from scripts.unified_data.sector_ranking_rollout.prod_repository import (
            ProdRankingWriter,
        )

        writer = ProdRankingWriter(db)
        writer.upsert(_partial_rows())
        assert db[COLLECTION].count_documents({"trade_date": "2026-07-14"}) == 2
        out = tmp_path / "out"
        rc = main(
            ["--expected-file", str(report_path), "--enable", "--apply", "--yes",
             "--smoke-dates", "2026-07-14",
             "--report-dir", str(out)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
            policy=_policy(),
            git_runner=lambda paths: [],
        )
        assert rc == EXIT_STOP
        payload = json.loads((out / "gate4-report.json").read_text())
        assert "G4-S-002" in payload["stop_conditions_hit"]
        assert load_binding(str(out))["enabled"] is False

    def test_enable_scope_diff_violation_stops(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate4_activate import main

        report_path = make_gate1_report(tmp_path)
        db = _gate4_db()
        out = tmp_path / "out"
        rc = main(
            ["--expected-file", str(report_path), "--enable", "--apply", "--yes",
             "--report-dir", str(out)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
            policy=_policy(),
            git_runner=lambda paths: [
                "M scripts/unified_data/sector_ranking_rollout/gate3_backfill.py"
            ],
        )
        assert rc == EXIT_STOP
        payload = json.loads((out / "gate4-report.json").read_text())
        assert "G4-S-003" in payload["stop_conditions_hit"]


def _partial_rows():
    """仅 2 个 code 的完整行（07-14），用于 pre-smoke 失败用例。"""
    from skills.data.unified_data.models.domain.sector_ranking import SectorRankingDaily
    from dataclasses import asdict

    return [
        asdict(
            SectorRankingDaily(
                dataset=DATASET,
                trade_date="2026-07-14",
                sector_code="801080",
                sector_name="电子",
                pct_chg=1.515152,
                rank=1,
                close=2010.0,
                pre_close=1980.0,
                updated_at="2026-07-31T12:00:00Z",
            )
        ),
        asdict(
            SectorRankingDaily(
                dataset=DATASET,
                trade_date="2026-07-14",
                sector_code="801010",
                sector_name="农林牧渔",
                pct_chg=0.990099,
                rank=2,
                close=1020.0,
                pre_close=1010.0,
                updated_at="2026-07-31T12:00:00Z",
            )
        ),
    ]
