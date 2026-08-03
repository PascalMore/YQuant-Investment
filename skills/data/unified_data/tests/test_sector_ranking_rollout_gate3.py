"""Offline tests for Gate-3 (gate3_backfill.py + prod_repository.ProdRankingWriter) — 03-016 rollout.

DESIGN-03-016 V0.6 §3.6 / SPEC-03-016 §3.4（L1 契约校正）。All tests run
against mongomock with explicit ``client_factory`` / ``env`` injection —
**zero environment reads and zero real I/O** (CL-5).

L1 契约：行情 join field = ``index_daily_quotes.full_symbol``（``.SI`` 后缀
L1 值集，来自 Gate-1 report ``expected_full_symbols``）；候选输出
``sector_code`` 为 ``.SI`` 后缀 L1 code。

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
    BudgetReader,
    BudgetViolation,
)
from scripts.unified_data.sector_ranking_rollout.prod_repository import (
    NamespaceViolation,
    ProdRankingWriter,
)
from skills.data.unified_data.models.domain.sector_ranking import SectorRankingDaily
from skills.data.unified_data.tests.fixtures.sector_ranking_rollout_fixtures import (
    AVAILABLE_DATES,
    DATASET,
    EXPECTED_UNIVERSE_31,
    EXPECTED_UNIVERSE_SI,
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
            sector_code="801780.SI",
            sector_name="银行",
            pct_chg=1.666667,
            rank=1,
            close=3050.0,
            pre_close=3000.0,
            trade_date=trade_date,
        ),
        _make_row(
            sector_code="801010.SI",
            sector_name="农林牧渔",
            pct_chg=1.0,
            rank=2,
            close=1010.0,
            pre_close=1000.0,
            trade_date=trade_date,
        ),
        _make_row(
            sector_code="801080.SI",
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
        assert codes == set(EXPECTED_UNIVERSE_SI)

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
        updated = next(r for r in rows if r["sector_code"] == "801780.SI")
        assert updated["close"] == 3051.0

    def test_constructor_rejects_none_db(self):
        with pytest.raises(TypeError):
            ProdRankingWriter(None)

    def test_get_returns_canonical_sort_not_insertion_order(self):
        # G3-S-007 回归：故意以非 canonical 插入顺序写集合，get() 必须返回
        # pct_chg DESC -> sector_code ASC（G3-V-003）。这是生产 Gate-3
        # canary 失败的根因——真实 Mongo natural order 非 canonical。
        writer = ProdRankingWriter(_fresh_db())
        rows = _complete_rows("2026-07-13")
        # 插入顺序故意打乱为非 canonical（rank=3 在前、rank=1 在后）。
        shuffled = [rows[2], rows[1], rows[0]]
        db = writer._db
        db[ProdRankingWriter.COLLECTION].insert_many(shuffled)
        read_back = writer.get(filter={"dataset": DATASET, "trade_date": "2026-07-13"})
        codes = [r["sector_code"] for r in read_back]
        # canonical：801780(1.667) > 801010(1.0) > 801080(-1.0)
        assert codes == ["801780.SI", "801010.SI", "801080.SI"]

    def test_get_sorts_tie_break_sector_code_ascending(self):
        # G3-V-003 tie-break：同 pct_chg 时 sector_code 升序。
        writer = ProdRankingWriter(_fresh_db())
        rows = _complete_rows("2026-07-13")
        # 构造两个同 pct_chg=1.0 的 code：801010(原) + 801080 改为 1.0
        rows[2]["pct_chg"] = 1.0
        rows[2]["rank"] = 2
        db = writer._db
        # 插入顺序反序，验证 tie-break 不受插入顺序影响
        db[ProdRankingWriter.COLLECTION].insert_many(
            [rows[2], rows[1], rows[0]]
        )
        read_back = writer.get(filter={"dataset": DATASET, "trade_date": "2026-07-13"})
        codes = [r["sector_code"] for r in read_back]
        # 801780(1.667) 先；801010 与 801080 同 1.0 → 801010 < 801080
        assert codes == ["801780.SI", "801010.SI", "801080.SI"]

    def test_canonical_sort_constant_is_restricted(self):
        # 证明 CANONICAL_SORT 是受限的固定排序，不可被调用方覆盖。
        assert ProdRankingWriter.CANONICAL_SORT == [("pct_chg", -1), ("sector_code", 1)]
        # get() 不接受 sort 参数（签名无 sort）——受限排序行为。
        import inspect

        sig = inspect.signature(ProdRankingWriter.get)
        assert "sort" not in sig.parameters


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
        assert plan.mode == "range-file"
        assert plan.dates == ["2026-07-13", "2026-07-14"]
        assert plan.full_coverage_dates == (
            "2026-07-10",
            "2026-07-13",
            "2026-07-14",
        )
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

    def test_range_file_filters_partial_dates_before_excluding_earliest(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import resolve_range

        report = _load_report(tmp_path)
        report["coverage_by_date"]["2026-07-09"] = {
            "expected": 3,
            "observed": 2,
            "ratio": 2 / 3,
        }
        report["coverage_by_date"]["2026-07-13"]["ratio"] = 0.5
        plan = resolve_range(
            report,
            canary_date=None,
            range_file="x.json",
            start_date=None,
            end_date=None,
            policy=None,
        )
        assert plan.full_coverage_dates == ("2026-07-10", "2026-07-14")
        assert plan.excluded_first == "2026-07-10"
        assert plan.dates == ["2026-07-14"]

    @pytest.mark.parametrize("ratio", [None, "bad", float("nan"), float("inf"), float("-inf")])
    def test_invalid_or_nonfinite_ratio_exit_param(self, tmp_path, ratio):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            parse_coverage_by_date,
        )

        report = _load_report(tmp_path)
        if ratio is None:
            report["coverage_by_date"]["2026-07-13"].pop("ratio")
        else:
            report["coverage_by_date"]["2026-07-13"]["ratio"] = ratio
        with pytest.raises(Gate3Stop) as exc:
            parse_coverage_by_date(report["coverage_by_date"])
        assert exc.value.sc_id == "G3-S-003"
        assert exc.value.exit_code == EXIT_PARAM

    @pytest.mark.parametrize("key", ["20260713", "2026/07/13", "2026-7-13"])
    def test_noncanonical_coverage_key_exit_param(self, tmp_path, key):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            parse_coverage_by_date,
        )

        report = _load_report(tmp_path)
        report["coverage_by_date"][key] = report["coverage_by_date"].pop("2026-07-13")
        with pytest.raises(Gate3Stop) as exc:
            parse_coverage_by_date(report["coverage_by_date"])
        assert exc.value.sc_id == "G3-S-003"
        assert exc.value.exit_code == EXIT_PARAM

    @pytest.mark.parametrize("coverage", [{}, {"2026-07-13": {"ratio": 0.5}}])
    def test_no_full_coverage_date_exit_param(self, coverage):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            parse_coverage_by_date,
        )

        with pytest.raises(Gate3Stop) as exc:
            parse_coverage_by_date(coverage)
        assert exc.value.sc_id == "G3-S-003"
        assert exc.value.exit_code == EXIT_PARAM

    def test_explicit_range_containing_partial_date_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        report["coverage_by_date"]["2026-07-13"]["ratio"] = 0.5
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file=None,
                start_date="2026-07-10",
                end_date="2026-07-14",
                policy=_policy(),
            )
        assert exc.value.sc_id == "G3-S-003"
        assert exc.value.exit_code == EXIT_PARAM

    def test_explicit_range_boundary_not_full_exit_param(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            resolve_range,
        )

        report = _load_report(tmp_path)
        report["coverage_by_date"]["2026-07-13"]["ratio"] = 0.5
        with pytest.raises(Gate3Stop) as exc:
            resolve_range(
                report,
                canary_date=None,
                range_file=None,
                start_date="2026-07-13",
                end_date="2026-07-14",
                policy=_policy(),
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
        assert plan.mode == "paired"
        assert plan.dates == ["2026-07-13", "2026-07-14"]
        assert plan.full_coverage_dates == (
            "2026-07-10",
            "2026-07-13",
            "2026-07-14",
        )
        assert plan.excluded_first is None


# ---------------------------------------------------------------------------
# process_day（DESIGN §3.6.4：前一日推导 / 固定 pct_chg / 完整性 / rt 剔除）
# ---------------------------------------------------------------------------


def _gate3_db(*, daily=None) -> Any:
    daily = daily if daily is not None else make_sw_index_docs(codes=EXPECTED_UNIVERSE_SI)
    return make_mongomock_db(index_daily=daily)


def _process_day_kwargs(
    trade_date: str,
    prev_date: str | None,
    *,
    db: Any,
    writer: ProdRankingWriter,
):
    return {
        "trade_date": trade_date,
        "prev_date": prev_date,
        "expected_codes": sorted(EXPECTED_UNIVERSE_SI),
        "expected_names": EXPECTED_UNIVERSE_SI,
        "expected_full_symbols": sorted(EXPECTED_UNIVERSE_SI),
        "db": db,
        "writer": writer,
        "updated_at": "2026-07-31T12:00:00Z",
    }


class TestProcessDay:
    def test_complete_day_builds_and_upserts(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            DATASET,
            process_day,
        )

        db = _gate3_db()
        writer = ProdRankingWriter(db)
        outcome = process_day(**_process_day_kwargs("2026-07-13", "2026-07-10", db=db, writer=writer))
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
        assert by_code["801780.SI"]["pct_chg"] == pytest.approx((3050 - 3000) / 3000 * 100)
        assert by_code["801010.SI"]["pct_chg"] == pytest.approx((1010 - 1000) / 1000 * 100)
        assert by_code["801080.SI"]["pct_chg"] == pytest.approx((1980 - 2000) / 2000 * 100)
        # 排序：pct_chg DESC（G3-V-003 / rank 连续 1-based）
        assert by_code["801780.SI"]["rank"] == 1
        assert by_code["801010.SI"]["rank"] == 2
        assert by_code["801080.SI"]["rank"] == 3
        # 候选输出 sector_code 为 .SI 后缀 L1 code（契约 6）
        assert all(code.endswith(".SI") for code in by_code)

    def test_first_day_without_prev_returns_empty(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            process_day,
        )

        db = _gate3_db()
        writer = ProdRankingWriter(db)
        outcome = process_day(**_process_day_kwargs("2026-07-10", None, db=db, writer=writer))
        assert outcome.status == "empty"
        assert outcome.reason == "no-prev-close"
        assert writer.estimated_document_count() == 0

    def test_incomplete_day_raises_g3_s_004(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            process_day,
        )

        # 去掉 801080.SI 在 2026-07-13 的行 → observed=2 != expected=3
        daily = [
            d
            for d in make_sw_index_docs(codes=EXPECTED_UNIVERSE_SI)
            if not (d["trade_date"] == "20260713" and d["full_symbol"] == "801080.SI")
        ]
        db = _gate3_db(daily=daily)
        writer = ProdRankingWriter(db)
        with pytest.raises(Gate3Stop) as exc:
            process_day(**_process_day_kwargs("2026-07-13", "2026-07-10", db=db, writer=writer))
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

        db = _gate3_db(
            daily=make_sw_index_docs_rt_marker("realtime", universe=EXPECTED_UNIVERSE_SI)
        )
        writer = ProdRankingWriter(db)
        with pytest.raises(Gate3Stop) as exc:
            process_day(**_process_day_kwargs("2026-07-13", "2026-07-10", db=db, writer=writer))
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

        db = _gate3_db(
            daily=make_sw_index_docs_missing_close(
                ["801010.SI"], universe=EXPECTED_UNIVERSE_SI
            )
        )
        writer = ProdRankingWriter(db)
        with pytest.raises(Gate3Stop) as exc:
            process_day(**_process_day_kwargs("2026-07-13", "2026-07-10", db=db, writer=writer))
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
        read_back_verify(writer, "2026-07-13", sorted(EXPECTED_UNIVERSE_SI))

    def test_read_back_verify_detects_missing_row(self):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            read_back_verify,
        )

        db = _gate3_db()
        writer = ProdRankingWriter(db)
        writer.upsert(_complete_rows("2026-07-13")[:2])  # 只写 2 行
        with pytest.raises(Gate3Stop) as exc:
            read_back_verify(writer, "2026-07-13", sorted(EXPECTED_UNIVERSE_SI))
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
            read_back_verify(writer, "2026-07-13", sorted(EXPECTED_UNIVERSE_SI))
        assert exc.value.sc_id == "G3-S-007"

    def test_read_back_verify_passes_with_noncanonical_insertion_order(self):
        # G3-S-007 回归（生产根因）：集合以非 canonical 顺序插入，但
        # read_back_verify 通过——证明 writer.get() 返回 canonical sorted
        # rows，校验比对的是受控排序而非 Mongo natural order。
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            read_back_verify,
        )

        db = _gate3_db()
        writer = ProdRankingWriter(db)
        rows = _complete_rows("2026-07-13")
        # 插入顺序故意反 canonical（rank=3 在前，rank=1 在后）
        db[DATASET_COLLECTION].insert_many([rows[2], rows[1], rows[0]])
        # 无异常即通过——get() 已强制 canonical sort
        read_back_verify(writer, "2026-07-13", sorted(EXPECTED_UNIVERSE_SI))

    def test_read_back_verify_fails_if_sort_genuinely_noncanonical(self):
        # 反向证明：若 writer 不 honor canonical sort（用绕过 get 的 fake），
        # 校验仍能检出非 canonical 顺序并报 G3-S-007。
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            read_back_verify,
        )

        rows = _complete_rows("2026-07-13")
        noncanonical = [rows[2], rows[1], rows[0]]  # rank 3,2,1 → 非 canonical

        class _UnsortedWriter:
            """模拟不 honor sort 的 writer：原样返回插入顺序。"""

            COLLECTION = ProdRankingWriter.COLLECTION

            def get(self, collection=None, filter=None):
                return [dict(r) for r in noncanonical]

        with pytest.raises(Gate3Stop) as exc:
            read_back_verify(
                _UnsortedWriter(),  # type: ignore[arg-type]  # duck-typed test stub
                "2026-07-13",
                sorted(EXPECTED_UNIVERSE_SI),
            )
        assert exc.value.sc_id == "G3-S-007"
        assert "G3-V-003" in str(exc.value)


DATASET_COLLECTION = "03_data_ud_sector_ranking_daily"


# ---------------------------------------------------------------------------
# main（CLI 退出码 / 日级原子 / canary 不进入全量 / report 产物）
# ---------------------------------------------------------------------------


class _ForbiddenClientFactory:
    calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        raise AssertionError("range fail-fast must not construct a database client")


class TestGate3Main:
    def test_dry_run_returns_zero_without_connection(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path, universe=EXPECTED_UNIVERSE_SI)
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

        report_path = make_gate1_report(tmp_path, universe=EXPECTED_UNIVERSE_SI)
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
        bad.write_text(json.dumps({"expected_sector_codes": ["801010.SI"]}))
        rc = main(
            ["--expected-file", str(bad), "--canary-date", "2026-07-14",
             "--report-dir", str(tmp_path / "out")]
        )
        assert rc == EXIT_PARAM

    def test_missing_expected_full_symbols_exit_1(self, tmp_path):
        # G3-S-002：缺 expected_full_symbols → 参数层 fail-fast exit 1，
        # 不等 process_day。
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        bad = tmp_path / "bad.json"
        bad.write_text(
            json.dumps(
                {
                    "expected_sector_codes": ["801010.SI", "801080.SI", "801780.SI"],
                    "expected_sector_names": {
                        "801010.SI": "农林牧渔",
                        "801080.SI": "电子",
                        "801780.SI": "银行",
                    },
                }
            )
        )
        rc = main(
            ["--expected-file", str(bad), "--canary-date", "2026-07-14",
             "--report-dir", str(tmp_path / "out")]
        )
        assert rc == EXIT_PARAM

    def test_non_si_expected_full_symbols_exit_1(self, tmp_path):
        # G3-S-002：expected_full_symbols 非 .SI 后缀 → exit 1。
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        bad = tmp_path / "bad.json"
        bad.write_text(
            json.dumps(
                {
                    "expected_sector_codes": ["801010.SI", "801080.SI", "801780.SI"],
                    "expected_sector_names": {
                        "801010.SI": "农林牧渔",
                        "801080.SI": "电子",
                        "801780.SI": "银行",
                    },
                    "expected_full_symbols": ["801010", "801080", "801780"],
                }
            )
        )
        rc = main(
            ["--expected-file", str(bad), "--canary-date", "2026-07-14",
             "--report-dir", str(tmp_path / "out")]
        )
        assert rc == EXIT_PARAM

    def test_no_range_source_exit_1(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path, universe=EXPECTED_UNIVERSE_SI)
        rc = main(
            ["--expected-file", str(report_path), "--report-dir", str(tmp_path / "out")]
        )
        assert rc == EXIT_PARAM

    def test_invalid_range_fail_fast_before_database_side_effects(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path, universe=EXPECTED_UNIVERSE_SI)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["coverage_by_date"]["2026-07-13"].pop("ratio")
        report_path.write_text(json.dumps(report), encoding="utf-8")
        factory = _ForbiddenClientFactory()
        rc = main(
            [
                "--expected-file",
                str(report_path),
                "--range-file",
                str(report_path),
                "--apply",
                "--yes",
                "--report-dir",
                str(tmp_path / "out"),
            ],
            client_factory=factory,
            env=TEST_ENV,
        )
        assert rc == EXIT_PARAM
        assert factory.calls == 0
        assert not (tmp_path / "out" / "gate3-report.json").exists()

    def test_canary_success_writes_report_and_materializes_day(self, tmp_path):
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path, universe=EXPECTED_UNIVERSE_SI)
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

        report_path = make_gate1_report(tmp_path, universe=EXPECTED_UNIVERSE_SI)
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

        report_path = make_gate1_report(tmp_path, universe=EXPECTED_UNIVERSE_SI)
        # 07-13 缺 801080.SI → G3-S-004；07-14 不应被处理（G3-B-002 日级原子）
        daily = [
            d
            for d in make_sw_index_docs(codes=EXPECTED_UNIVERSE_SI)
            if not (d["trade_date"] == "20260713" and d["full_symbol"] == "801080.SI")
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

        report_path = make_gate1_report(tmp_path, universe=EXPECTED_UNIVERSE_SI)
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


# ---------------------------------------------------------------------------
# Gate-3 per-day query-budget / resumability contract
# （G3-B-017~020 / G3-S-013 / DESIGN V0.8 §3.3.3 + §3.6.6）
# ---------------------------------------------------------------------------


class TestBudgetReaderGate3:
    """BudgetReader per-day 预算模型：reset 语义 + 日级上限 + Gate-1 非回归。"""

    def test_reset_stats_clears_cumulative_and_stats(self):
        # G3-B-017：reset 同时清零累计计数器与 stats 列表（per-day scoped）。
        db = _fresh_db()
        for i in range(3):
            db["index_daily_quotes"].insert_one(
                {"full_symbol": "801780.SI", "trade_date": f"2026{i:02d}01"}
            )
        reader = BudgetReader(db, cumulative_rows_limit=None, day_rows_limit=124)
        rows = reader.find("index_daily_quotes", {"full_symbol": "801780.SI"})
        assert len(rows) == 3
        assert reader.cumulative_rows == 3
        assert sum(s["rows"] for s in reader.stats()) == 3

        reader.reset_stats()
        assert reader.cumulative_rows == 0
        assert reader.stats() == []

        # 再次查询只计当日，不跨 reset 累加。
        rows = reader.find("index_daily_quotes", {"full_symbol": "801780.SI"})
        assert len(rows) == 3
        assert reader.cumulative_rows == 3
        assert sum(s["rows"] for s in reader.stats()) == 3

    def test_day_rows_limit_violation_raises_budget_violation(self):
        # G3-B-018：单日命中 > day_rows_limit → BudgetViolation（G3-S-013 源）。
        db = _fresh_db()
        for _ in range(125):
            db["index_daily_quotes"].insert_one(
                {"full_symbol": "801780.SI", "trade_date": "20260713"}
            )
        reader = BudgetReader(db, cumulative_rows_limit=None, day_rows_limit=124)
        with pytest.raises(BudgetViolation) as exc:
            reader.find("index_daily_quotes", {"full_symbol": "801780.SI"})
        assert "G3-B-018" in str(exc.value)
        # 违规查询仍计入累计（observed 审计证据，M5）。
        assert reader.cumulative_rows == 125

    def test_day_rows_limit_normal_day_allowed(self):
        # 正常单日 62 行（31 close + 31 pre_close）≤ 124 → 不触发。
        db = _fresh_db()
        for i in range(62):
            db["index_daily_quotes"].insert_one(
                {"full_symbol": f"80{1000 + i:04d}.SI", "trade_date": "20260713"}
            )
        reader = BudgetReader(db, cumulative_rows_limit=None, day_rows_limit=124)
        rows = reader.find("index_daily_quotes", {"trade_date": "20260713"})
        assert len(rows) == 62
        assert reader.cumulative_rows == 62

    def test_gate1_default_cumulative_cap_still_enforced(self):
        # Gate-1 非回归（G1-B-006）：默认 cumulative_rows_limit=100000 保留；
        # day_rows_limit 默认 None（Gate-1 不启用）。
        import inspect

        sig = inspect.signature(BudgetReader.__init__)
        assert sig.parameters["cumulative_rows_limit"].default == 100_000
        assert sig.parameters["day_rows_limit"].default is None
        db = _fresh_db()
        for i in range(11):
            db["index_daily_quotes"].insert_one(
                {"full_symbol": "801780.SI", "trade_date": f"2026{i:02d}01"}
            )
        reader = BudgetReader(db, cumulative_rows_limit=10)
        with pytest.raises(BudgetViolation):
            reader.find("index_daily_quotes", {"full_symbol": "801780.SI"})

    def test_cumulative_rows_limit_none_disables_global_cap(self):
        # G3-B-019：Gate-3 构造 None 禁用全局累计阻断。
        db = _fresh_db()
        for i in range(11):
            db["index_daily_quotes"].insert_one(
                {"full_symbol": "801780.SI", "trade_date": f"2026{i:02d}01"}
            )
        reader = BudgetReader(db, cumulative_rows_limit=None, day_rows_limit=None)
        rows = reader.find("index_daily_quotes", {"full_symbol": "801780.SI"})
        assert len(rows) == 11
        assert reader.cumulative_rows == 11

    def test_scan_protection_still_enforced_with_day_limit(self):
        # G3-B-020：per-day 模型不放宽扫描保护（空 filter / 单次 >1000）。
        reader = BudgetReader(
            _fresh_db(), cumulative_rows_limit=None, day_rows_limit=124
        )
        with pytest.raises(BudgetViolation):
            reader.find("index_daily_quotes", {})
        with pytest.raises(BudgetViolation):
            reader.find(
                "index_daily_quotes", {"full_symbol": "801780.SI"}, limit=1001
            )


class TestProcessDayBudgetViolation:
    def test_process_day_budget_violation_maps_to_g3_s_013(self):
        # G3-B-018 / G3-S-013：process_day 内 BudgetViolation → Gate3Stop。
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import (
            Gate3Stop,
            process_day,
        )

        db = _gate3_db()  # 3 code × 3 日；单日 find = 6 行
        writer = ProdRankingWriter(db)
        # 故意收紧日级上限 4 < 6：正常单日也触发 G3-S-013。
        budget = BudgetReader(db, cumulative_rows_limit=None, day_rows_limit=4)
        with pytest.raises(Gate3Stop) as exc:
            process_day(
                **_process_day_kwargs("2026-07-13", "2026-07-10", db=db, writer=writer),
                budget=budget,
            )
        assert exc.value.sc_id == "G3-S-013"
        assert exc.value.exit_code == EXIT_STOP
        assert "G3-B-018" in str(exc.value)
        # 违规日不物化（G3-B-012 精神）。
        assert writer.estimated_document_count() == 0


# 10 个连续可用交易日（覆盖 G3-B-017 跨日不累加）。
_MULTI_AGG_DATES = [
    "2026-07-01",
    "2026-07-02",
    "2026-07-03",
    "2026-07-06",
    "2026-07-07",
    "2026-07-08",
    "2026-07-09",
    "2026-07-10",
    "2026-07-13",
    "2026-07-14",
]


class TestGate3PerDayBudget:
    """per-day 预算集成（G3-B-017~020 / G3-S-013 / M4 / M5）。"""

    def test_multi_day_aggregation_no_budget_violation(self, tmp_path):
        # 跨多日正常聚合：reader.reset_stats() 使累计不跨日累加 →
        # 全量 apply 退出码 0，不命中 BudgetViolation（G3-B-017/019）。
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        dates = _MULTI_AGG_DATES
        internal = [d.replace("-", "") for d in dates]
        daily = make_sw_index_docs(codes=EXPECTED_UNIVERSE_SI, dates=internal)
        db = make_mongomock_db(index_daily=daily)
        report_path = make_gate1_report(
            tmp_path, universe=EXPECTED_UNIVERSE_SI, available_dates=dates
        )
        out = tmp_path / "out"
        rc = main(
            [
                "--expected-file", str(report_path),
                "--range-file", str(report_path),
                "--apply", "--yes",
                "--report-dir", str(out),
            ],
            client_factory=lambda **kw: _ClientShim(db),
            env=TEST_ENV,
            updated_at="2026-07-31T12:00:00Z",
        )
        assert rc == EXIT_OK
        payload = json.loads((out / "gate3-report.json").read_text())
        assert payload["stop_conditions_hit"] == []
        assert payload["summary"]["success_days"] == len(dates) - 1  # 最早日排除
        assert payload["summary"]["failed_days"] == 0
        # G3-B-018：日级上限实际值 = 4 × len(expected)（3 code → 12）。
        assert payload["summary"]["day_rows_limit"] == 4 * len(EXPECTED_UNIVERSE_SI)
        # G3-B-017：days[].query_budget 为单日计数（3 code × 2 日 = 6 行/日）。
        per_day_rows = [
            sum(item["rows"] for item in d["query_budget"]) for d in payload["days"]
        ]
        assert per_day_rows == [6] * (len(dates) - 1)
        # M4：total_query_rows / 顶层 query_budget 由保留记录派生（reset-safe）。
        assert payload["summary"]["total_query_rows"] == 6 * (len(dates) - 1)
        top_rows = sum(item["rows"] for item in payload["query_budget"])
        assert top_rows == 6 * (len(dates) - 1)
        assert payload["summary"]["resumption_boundary"] == dates[-1]
        assert payload["failed_days"] == []

    def test_day_exceeding_cap_hard_stop_no_later_date(self, tmp_path):
        # G3-S-013（31 code → day_limit 124）：首日 125 行 → 退出码 2，
        # failed_days[] 保留证据，停止后续日，resumption_boundary=None。
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        dates = ["2026-07-10", "2026-07-13", "2026-07-14"]
        # 07-10 无文档（首日被排除且不作为 prev 命中）；
        # 07-13 注入 125 行（31 唯一 + 94 重复 full_symbol）> 124；
        # 07-14 正常 31 行——不应被处理。
        daily = make_sw_index_docs(codes=EXPECTED_UNIVERSE_31, dates=["20260713"])
        for i in range(94):
            dup = dict(daily[i % len(daily)])
            dup["close"] = float(dup["close"]) + 1.0
            daily.append(dup)
        daily += make_sw_index_docs(codes=EXPECTED_UNIVERSE_31, dates=["20260714"])
        db = make_mongomock_db(index_daily=daily)
        report_path = make_gate1_report(
            tmp_path, universe=EXPECTED_UNIVERSE_31, available_dates=dates
        )
        out = tmp_path / "out"
        rc = main(
            [
                "--expected-file", str(report_path),
                "--range-file", str(report_path),
                "--apply", "--yes",
                "--report-dir", str(out),
            ],
            client_factory=lambda **kw: _ClientShim(db),
            env=TEST_ENV,
            updated_at="2026-07-31T12:00:00Z",
        )
        assert rc == EXIT_STOP
        payload = json.loads((out / "gate3-report.json").read_text())
        assert "G3-S-013" in payload["stop_conditions_hit"]
        assert payload["summary"]["day_rows_limit"] == 124
        # M5：失败日保留于 failed_days[]，不进成功 days[]。
        assert payload["days"] == []
        assert len(payload["failed_days"]) == 1
        fd = payload["failed_days"][0]
        assert fd["trade_date"] == "2026-07-13"
        assert fd["status"] == "budget-violation"
        assert fd["observed"] == 125
        assert fd["day_limit"] == 124
        assert fd["stop_id"] == "G3-S-013"
        assert "ms" in fd
        assert isinstance(fd["query_budget"], list)
        # G3-B-019：total_query_rows informational = 保留记录求和（125）。
        assert payload["summary"]["total_query_rows"] == 125
        assert payload["summary"]["resumption_boundary"] is None
        # 停止后续日：07-14 未物化。
        assert (
            db[DATASET_COLLECTION].count_documents({"trade_date": "2026-07-14"}) == 0
        )

    def test_day_exceeding_cap_after_success_records_resumption(self, tmp_path):
        # 部分成功：07-13 正常（62 行），07-14 注入 125 行 →
        # find = 125 + 31(prev) = 156 > 124 → G3-S-013；
        # resumption_boundary = 07-13（最后成功日），total = 62 + 156。
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        dates = ["2026-07-10", "2026-07-13", "2026-07-14"]
        daily = make_sw_index_docs(
            codes=EXPECTED_UNIVERSE_31, dates=["20260710", "20260713"]
        )
        daily += make_sw_index_docs(codes=EXPECTED_UNIVERSE_31, dates=["20260714"])
        for i in range(94):
            dup = dict(
                make_sw_index_docs(codes=EXPECTED_UNIVERSE_31, dates=["20260714"])[
                    i % len(EXPECTED_UNIVERSE_31)
                ]
            )
            dup["close"] = float(dup["close"]) + 1.0
            daily.append(dup)
        db = make_mongomock_db(index_daily=daily)
        report_path = make_gate1_report(
            tmp_path, universe=EXPECTED_UNIVERSE_31, available_dates=dates
        )
        out = tmp_path / "out"
        rc = main(
            [
                "--expected-file", str(report_path),
                "--range-file", str(report_path),
                "--apply", "--yes",
                "--report-dir", str(out),
            ],
            client_factory=lambda **kw: _ClientShim(db),
            env=TEST_ENV,
            updated_at="2026-07-31T12:00:00Z",
        )
        assert rc == EXIT_STOP
        payload = json.loads((out / "gate3-report.json").read_text())
        assert "G3-S-013" in payload["stop_conditions_hit"]
        assert payload["summary"]["success_days"] == 1
        assert payload["summary"]["day_rows_limit"] == 124
        assert payload["summary"]["resumption_boundary"] == "2026-07-13"
        assert payload["days"][0]["trade_date"] == "2026-07-13"
        fd = payload["failed_days"][0]
        assert fd["trade_date"] == "2026-07-14"
        assert fd["observed"] == 156  # 125(日) + 31(prev)
        assert fd["day_limit"] == 124
        assert fd["stop_id"] == "G3-S-013"
        # 保留记录 = days[0]（62 行）+ failed_days[0]（156 行）。
        assert payload["summary"]["total_query_rows"] == 62 + 156
        assert (
            db[DATASET_COLLECTION].count_documents({"trade_date": "2026-07-14"}) == 0
        )

    def test_failed_day_schema_for_non_budget_stop(self, tmp_path):
        # G3-S-004（incomplete）：failed_days[] 字段齐备，day_limit=null（非 013）。
        from scripts.unified_data.sector_ranking_rollout.gate3_backfill import main

        report_path = make_gate1_report(tmp_path, universe=EXPECTED_UNIVERSE_SI)
        daily = [
            d
            for d in make_sw_index_docs(codes=EXPECTED_UNIVERSE_SI)
            if not (d["trade_date"] == "20260713" and d["full_symbol"] == "801080.SI")
        ]
        db = make_mongomock_db(index_daily=daily)
        out = tmp_path / "out"
        rc = main(
            [
                "--expected-file", str(report_path),
                "--range-file", str(report_path),
                "--apply", "--yes",
                "--report-dir", str(out),
            ],
            client_factory=lambda **kw: _ClientShim(db),
            env=TEST_ENV,
            updated_at="2026-07-31T12:00:00Z",
        )
        assert rc == EXIT_STOP
        payload = json.loads((out / "gate3-report.json").read_text())
        assert "G3-S-004" in payload["stop_conditions_hit"]
        assert len(payload["failed_days"]) == 1
        fd = payload["failed_days"][0]
        # failed_days 必需字段齐备（DESIGN §3.6.6）。
        for key in (
            "trade_date",
            "status",
            "observed",
            "day_limit",
            "stop_id",
            "ms",
            "query_budget",
        ):
            assert key in fd
        assert fd["trade_date"] == "2026-07-13"
        assert fd["status"] == "incomplete"
        # find 命中 5 行：07-13 缺 801080（2 行）+ 07-10 全（3 行）。
        assert fd["observed"] == 5
        assert fd["day_limit"] is None  # 非 G3-S-013 → null
        assert fd["stop_id"] == "G3-S-004"
        assert isinstance(fd["query_budget"], list)
        # 保留记录仅 failed_days → total_query_rows = 5（reset-safe 派生）。
        assert payload["summary"]["total_query_rows"] == 5
        assert payload["summary"]["resumption_boundary"] is None
        assert payload["summary"]["day_rows_limit"] == 4 * len(EXPECTED_UNIVERSE_SI)
        assert payload["days"] == []
