"""Offline tests for ``sector.ranking_history`` (RFC-03-015 T3).

Implements the applicable subset of SPEC T-015-001~015 and DESIGN
UT-015-001~021 (DESIGN-03-015 V0.5 §5.1). All tests run against
mongomock / pure functions — **zero real I/O** (no Mongo, no TA-CN, no
AKShare, no HTTP).

Coverage anchors required by the kanban task:

* 100% complete build (observed == expected) + full ranking read
* cross-dataset isolation / no silent fallback
* unique-key upsert (overwrite + updated_at refresh)
* trade_date / dataset / limit ``ValueError`` (Category 1)
* four frozen trace categories + success trace, verbatim order
* incomplete / empty builds never materialize (no DB write)
* stable tie-break (pct_chg DESC, sector_code ASC)
* E2E from an injected mongomock db (end-to-end proof for the
  conditional client facade)

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

import mongomock
import pytest

from skills.data.unified_data import UnifiedDataClient
from skills.data.unified_data.adapters.historical_ranking_writer import (
    HistoricalRankingWriter,
)
from skills.data.unified_data.models.domain.sector_ranking import (
    KNOWN_DATASETS,
    REQUIRED_FIELDS,
    SectorRankingDaily,
)
from skills.data.unified_data.services.historical_sector_service import (
    WARNING_EMPTY,
    WARNING_INCOMPLETE,
    BuildOutcome,
    HistoricalSectorService,
    build_ranking_rows,
)
from skills.data.unified_data.tests.fixtures.historical_ranking_fixtures import (
    DATASET,
    EXPECTED_SECTOR_CODES,
    TRADE_DATE,
    make_duplicate_rows,
    make_empty_rows,
    make_extra_code_rows,
    make_fully_complete_docs,
    make_incomplete_rows,
    make_invalid_close_rows,
    make_mongomock_db,
    make_tie_break_rows,
    make_valid_ranking_rows,
    make_writer,
    make_zero_pre_close_rows,
)

FIXED_UPDATED_AT = "2026-07-31T19:30:00.000000"

# 完整 source_trace 顺序（RFC §5.6.3 / SPEC H-051c）：
# dataset → trade_date → source → coverage → completeness → materialized
EXPECTED_TRACE_PREFIX = [
    f"dataset:{DATASET}",
    f"trade_date:{TRADE_DATE}",
    "source:ta_cn:index_daily_quotes",
]


def _service(
    db=None,
    *,
    expected_universe: dict | None = None,
) -> tuple[HistoricalSectorService, HistoricalRankingWriter]:
    """Build service + writer over a (fresh or injected) mongomock db."""
    writer = make_writer(db)
    universe = (
        expected_universe
        if expected_universe is not None
        else {DATASET: EXPECTED_SECTOR_CODES}
    )
    return HistoricalSectorService(writer, expected_universe_by_dataset=universe), writer


def _complete_doc(
    sector_code: str,
    sector_name: str,
    close: float | str,
    pre_close: float | str,
) -> dict:
    """One fully-populated 9-field collection doc."""
    close_f = float(close)
    pre_close_f = float(pre_close)
    return {
        "dataset": DATASET,
        "trade_date": TRADE_DATE,
        "sector_code": sector_code,
        "sector_name": sector_name,
        "pct_chg": (close_f - pre_close_f) / pre_close_f * 100,
        "rank": 1,
        "close": close_f,
        "pre_close": pre_close_f,
        "updated_at": FIXED_UPDATED_AT,
    }


# ---------------------------------------------------------------------------
# T-015-001 / UT-015-001 — SectorRankingDaily.from_dict schema validation
# ---------------------------------------------------------------------------


class TestSectorRankingDailyFromDict:
    """Pin the 9-field strict-validation contract (SPEC H-009 ~ H-018)."""

    def test_dataclass_shape(self):
        assert is_dataclass(SectorRankingDaily)

    def test_from_dict_all_fields(self):
        doc = _complete_doc("801120", "食品饮料", 5545.0, 5498.16)
        row = SectorRankingDaily.from_dict(doc)
        assert row.dataset == DATASET
        assert row.trade_date == TRADE_DATE
        assert row.sector_code == "801120"
        assert row.sector_name == "食品饮料"
        assert row.rank == 1
        assert row.close == 5545.0
        assert row.pre_close == 5498.16
        assert row.updated_at == FIXED_UPDATED_AT

    def test_missing_any_field_raises_value_error(self):
        # 缺失任一必填字段 → ValueError（SPEC H-018 / DESIGN §3.3.1）。
        base = _complete_doc("801120", "食品饮料", 5545.0, 5498.16)
        for field in REQUIRED_FIELDS:
            incomplete = {k: v for k, v in base.items() if k != field}
            with pytest.raises(ValueError):
                SectorRankingDaily.from_dict(incomplete)

    def test_none_value_raises_value_error(self):
        base = _complete_doc("801120", "食品饮料", 5545.0, 5498.16)
        for field in REQUIRED_FIELDS:
            doc = dict(base)
            doc[field] = None
            with pytest.raises(ValueError):
                SectorRankingDaily.from_dict(doc)

    def test_non_dict_raises_type_error(self):
        with pytest.raises(TypeError):
            SectorRankingDaily.from_dict(["not", "a", "dict"])

    def test_extra_keys_ignored(self):
        # A-015-DRIFT-2：上游额外字段静默忽略。
        doc = _complete_doc("801120", "食品饮料", 5545.0, 5498.16)
        doc["volume"] = 12345
        doc["raw_payload"] = {"x": 1}
        row = SectorRankingDaily.from_dict(doc)
        assert row.sector_code == "801120"

    def test_dataset_must_be_known(self):
        doc = _complete_doc("801120", "食品饮料", 5545.0, 5498.16)
        assert "sw2021_ta_cn" in KNOWN_DATASETS
        for bad in ("eastmoney_industry", "ths_industry", "", "SW2021"):
            bad_doc = dict(doc, dataset=bad)
            with pytest.raises(ValueError):
                SectorRankingDaily.from_dict(bad_doc)

    def test_trade_date_format(self):
        doc = _complete_doc("801120", "食品饮料", 5545.0, 5498.16)
        assert SectorRankingDaily.from_dict(doc).trade_date == TRADE_DATE
        for bad in ("2026-7-1", "20260713", "2026/07/13", "2026-13-01", "2026-02-30", ""):
            bad_doc = dict(doc, trade_date=bad)
            with pytest.raises(ValueError):
                SectorRankingDaily.from_dict(bad_doc)

    def test_numeric_validation(self):
        doc = _complete_doc("801120", "食品饮料", 5545.0, 5498.16)
        # pre_close == 0 → 除零守卫（冻结契约 #1）。
        with pytest.raises(ValueError):
            SectorRankingDaily.from_dict(dict(doc, pre_close=0))
        # rank < 1 → ValueError。
        with pytest.raises(ValueError):
            SectorRankingDaily.from_dict(dict(doc, rank=0))
        with pytest.raises(ValueError):
            SectorRankingDaily.from_dict(dict(doc, rank=-3))
        # 非数值 → ValueError。
        with pytest.raises(ValueError):
            SectorRankingDaily.from_dict(dict(doc, close="abc"))
        with pytest.raises(ValueError):
            SectorRankingDaily.from_dict(dict(doc, pct_chg=float("nan")))
        # bool 不是合法数值。
        with pytest.raises(ValueError):
            SectorRankingDaily.from_dict(dict(doc, close=True))

    def test_numeric_string_coercion(self):
        # A-015-DRIFT-4：数值字符串容错强转。
        doc = _complete_doc("801120", "食品饮料", "5545.0", "5498.16")
        doc["rank"] = "3"
        doc["pct_chg"] = "0.85"
        row = SectorRankingDaily.from_dict(doc)
        assert row.close == 5545.0
        assert row.pre_close == 5498.16
        assert row.rank == 3
        assert row.pct_chg == 0.85


# ---------------------------------------------------------------------------
# T-015-002 / UT-015-002 — unique-key upsert (HistoricalRankingWriter)
# ---------------------------------------------------------------------------


class TestHistoricalRankingWriter:
    """Writer round-trip: upsert / get / delete + offline guard."""

    def test_upsert_then_get_round_trip(self):
        writer = make_writer()
        docs = make_fully_complete_docs(make_valid_ranking_rows())
        outcome = writer.upsert(docs)
        assert outcome.persisted == 3
        assert outcome.failed == 0

        all_rows = writer.get(filter={})
        assert len(all_rows) == 3

        by_key = writer.get(filter={"dataset": DATASET, "trade_date": TRADE_DATE})
        assert {r["sector_code"] for r in by_key} == set(EXPECTED_SECTOR_CODES)

        single = writer.get(filter={"sector_code": "801120"})
        assert len(single) == 1
        assert single[0]["sector_name"] == "食品饮料"

    def test_upsert_idempotent_on_unique_key(self):
        # 相同 {dataset, trade_date, sector_code} 覆盖更新，updated_at 刷新
        # （SPEC H-020 / UT-015-002）。
        writer = make_writer()
        docs = make_fully_complete_docs(make_valid_ranking_rows())
        first = writer.upsert(docs)
        assert first.persisted == 3

        refreshed = [
            dict(doc, updated_at="2026-08-01T09:00:00.000000", rank=99)
            for doc in docs
        ]
        second = writer.upsert(refreshed)
        assert second.persisted == 3  # 覆盖而非新增

        rows = writer.get(filter={"dataset": DATASET, "trade_date": TRADE_DATE})
        assert len(rows) == 3  # 仍只有 3 行
        by_code = {r["sector_code"]: r for r in rows}
        assert by_code["801120"]["updated_at"] == "2026-08-01T09:00:00.000000"
        assert by_code["801120"]["rank"] == 99

    def test_upsert_outcome_captures_failed_records(self):
        writer = make_writer()
        docs = make_fully_complete_docs(make_valid_ranking_rows())
        docs.append({"sector_code": "801000", "sector_name": "缺键行"})  # 缺唯一键字段
        outcome = writer.upsert(docs)
        assert outcome.persisted == 3
        assert outcome.failed == 1
        assert len(outcome.failed_keys) == 1
        assert len(outcome.errors) == 1

    def test_delete_requires_filter(self):
        writer = make_writer()
        with pytest.raises(ValueError):
            writer.delete({})
        with pytest.raises(ValueError):
            writer.delete(None)  # type: ignore[arg-type]

    def test_delete_returns_count(self):
        writer = make_writer()
        writer.upsert(make_fully_complete_docs(make_valid_ranking_rows()))
        deleted = writer.delete({"sector_code": "801120"})
        assert deleted == 1
        remaining = writer.get(filter={"dataset": DATASET, "trade_date": TRADE_DATE})
        assert len(remaining) == 2

    def test_constructor_rejects_real_pymongo(self):
        # UT-015-016：拒绝真实 pymongo（离线 guard）。

        class FakePymongoDatabase:
            pass

        FakePymongoDatabase.__module__ = "pymongo.database"
        with pytest.raises(TypeError) as excinfo:
            HistoricalRankingWriter(FakePymongoDatabase())
        assert "pymongo" in str(excinfo.value).lower()

    def test_constructor_rejects_none(self):
        with pytest.raises(TypeError):
            HistoricalRankingWriter(None)  # type: ignore[arg-type]

    def test_accepts_mongomock_db(self):
        db = mongomock.MongoClient().get_database("unified_data_test")
        writer = HistoricalRankingWriter(db)
        assert writer.COLLECTION == "03_data_ud_sector_ranking_daily"
        assert writer.UNIQUE_KEY == frozenset({"dataset", "trade_date", "sector_code"})


# ---------------------------------------------------------------------------
# T-015-003/004/012 / UT-015-003/004/012/018/019 — build_ranking_rows
# ---------------------------------------------------------------------------


class TestBuildRankingRows:
    """Deterministic pure-function build: formula, sort, rank, completeness."""

    def test_complete_build_sorts_and_ranks(self):
        # T-015-003 / UT-015-003：pct_chg = (close - pre_close) / pre_close * 100。
        # T-015-004 / UT-015-004：pct_chg DESC 排名、连续 rank。
        outcome = build_ranking_rows(
            make_valid_ranking_rows(),
            EXPECTED_SECTOR_CODES,
            DATASET,
            TRADE_DATE,
            updated_at=FIXED_UPDATED_AT,
        )
        assert outcome.status == "complete"
        assert outcome.observed_sector_codes == EXPECTED_SECTOR_CODES
        assert outcome.skipped_invalid == 0
        assert outcome.skipped_duplicates == 0

        rows = outcome.rows
        assert [r.sector_code for r in rows] == ["801780", "801120", "801080"]
        assert [r.rank for r in rows] == [1, 2, 3]
        # 固定口径计算。
        assert rows[0].pct_chg == pytest.approx((3100.0 - 3050.0) / 3050.0 * 100)
        assert rows[1].pct_chg == pytest.approx((5545.0 - 5498.16) / 5498.16 * 100)
        assert rows[2].pct_chg == pytest.approx((4200.0 - 4300.0) / 4300.0 * 100)
        # dataset / trade_date 由 build 注入（T-015-012 适用部分）。
        assert all(r.dataset == DATASET for r in rows)
        assert all(r.trade_date == TRADE_DATE for r in rows)
        # 全部为 SectorRankingDaily domain 对象。
        assert all(isinstance(r, SectorRankingDaily) for r in rows)

    def test_tie_break_sector_code_asc(self):
        # UT-015-018：pct_chg 相同时按 sector_code ASC 确定性排序。
        expected = frozenset({"801010", "801020"})
        outcome = build_ranking_rows(
            make_tie_break_rows(),
            expected,
            DATASET,
            TRADE_DATE,
            updated_at=FIXED_UPDATED_AT,
        )
        assert outcome.status == "complete"
        assert [r.sector_code for r in outcome.rows] == ["801010", "801020"]
        assert [r.pct_chg for r in outcome.rows] == [pytest.approx(100.0)] * 2
        assert [r.rank for r in outcome.rows] == [1, 2]

    def test_missing_sector_incomplete(self):
        # T-015-006 / UT-015-006：缺行业 → incomplete，rows=[]。
        outcome = build_ranking_rows(
            make_incomplete_rows(),
            EXPECTED_SECTOR_CODES,
            DATASET,
            TRADE_DATE,
        )
        assert outcome.status == "incomplete"
        assert outcome.rows == []
        assert outcome.observed_sector_codes == frozenset({"801120", "801780"})
        assert outcome.coverage_ratio == pytest.approx(2 / 3)

    def test_duplicate_sector_incomplete(self):
        outcome = build_ranking_rows(
            make_duplicate_rows(),
            EXPECTED_SECTOR_CODES,
            DATASET,
            TRADE_DATE,
        )
        assert outcome.status == "incomplete"
        assert outcome.rows == []
        # 801120 重复 → 该代码全部行剔除（2 行）。
        assert outcome.skipped_duplicates == 2
        assert outcome.observed_sector_codes == frozenset({"801780", "801080"})

    def test_extra_code_incomplete(self):
        # 含 expected 之外代码 → incomplete（RFC §5.6.2）。
        outcome = build_ranking_rows(
            make_extra_code_rows(),
            EXPECTED_SECTOR_CODES,
            DATASET,
            TRADE_DATE,
        )
        assert outcome.status == "incomplete"
        assert outcome.rows == []
        assert "801999" in outcome.observed_sector_codes

    def test_invalid_close_incomplete(self):
        # T-015-008：非法 close 行不进入正式 ranking → observed != expected。
        outcome = build_ranking_rows(
            make_invalid_close_rows(),
            EXPECTED_SECTOR_CODES,
            DATASET,
            TRADE_DATE,
        )
        assert outcome.status == "incomplete"
        assert outcome.rows == []
        assert outcome.skipped_invalid == 1

    def test_zero_pre_close_incomplete(self):
        # pre_close == 0 → 非法（除零守卫）。
        outcome = build_ranking_rows(
            make_zero_pre_close_rows(),
            EXPECTED_SECTOR_CODES,
            DATASET,
            TRADE_DATE,
        )
        assert outcome.status == "incomplete"
        assert outcome.rows == []
        assert outcome.skipped_invalid == 1

    def test_missing_pre_close_fails_row(self):
        # T-015-005 / UT-015-005：缺 pre_close → 该行不入库（剔除）。
        rows = make_valid_ranking_rows()
        rows[0] = {"sector_code": "801120", "sector_name": "食品饮料", "close": 5545.0}
        outcome = build_ranking_rows(rows, EXPECTED_SECTOR_CODES, DATASET, TRADE_DATE)
        assert outcome.status == "incomplete"
        assert outcome.rows == []
        assert outcome.skipped_invalid == 1

    def test_zero_valid_rows_empty(self):
        # T-015-007 / UT-015-007：build 零有效行 → empty，rows=[]。
        outcome = build_ranking_rows(
            make_empty_rows(),
            EXPECTED_SECTOR_CODES,
            DATASET,
            TRADE_DATE,
        )
        assert outcome.status == "empty"
        assert outcome.rows == []
        assert outcome.observed_sector_codes == frozenset()
        assert outcome.coverage_ratio == 0.0

    def test_empty_input_rows_empty(self):
        outcome = build_ranking_rows([], EXPECTED_SECTOR_CODES, DATASET, TRADE_DATE)
        assert outcome.status == "empty"
        assert outcome.rows == []

    def test_expected_universe_is_explicit(self):
        # UT-015-019：expected universe 由调用方显式传入（fixture），不硬编码。
        # 不同的显式 universe → 同一 rows 得到不同完整性判定。
        three = build_ranking_rows(
            make_valid_ranking_rows(), EXPECTED_SECTOR_CODES, DATASET, TRADE_DATE
        )
        assert three.status == "complete"
        two = build_ranking_rows(
            make_valid_ranking_rows(), frozenset({"801120", "801780"}), DATASET, TRADE_DATE
        )
        assert two.status == "incomplete"  # 多余代码（801080 不在显式 universe 内）

    def test_incomplete_never_materializes(self):
        # 契约 #3：只有 complete 才写入；incomplete 不得调用 upsert。
        writer = make_writer()
        outcome = build_ranking_rows(
            make_incomplete_rows(), EXPECTED_SECTOR_CODES, DATASET, TRADE_DATE
        )
        assert outcome.status == "incomplete"
        # 没有发生任何写入。
        assert writer.get(filter={}) == []
        # 物化集合为空 → 查询走 Category 2（empty / materialized:ok）。
        service, _ = _service(writer.db)
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert result.data == []
        assert result.warnings == [WARNING_EMPTY]


# ---------------------------------------------------------------------------
# UT-015-010/011/014/015 — service parameter validation (Category 1)
# ---------------------------------------------------------------------------


class TestHistoricalSectorServiceValidation:
    """Category 1 — 参数非法一律 ValueError，不构造 DataResult / trace。"""

    @pytest.fixture(autouse=True)
    def _svc(self):
        self.service, _ = _service()

    def test_trade_date_none_rejected(self):
        with pytest.raises(ValueError):
            self.service.get_sector_ranking_history(None, DATASET)  # type: ignore[arg-type]

    def test_trade_date_format_rejected(self):
        for bad in ("", "20260713", "2026-7-1", "2026/07/13", "2026-13-01", "today"):
            with pytest.raises(ValueError):
                self.service.get_sector_ranking_history(bad, DATASET)

    def test_dataset_missing_rejected(self):
        with pytest.raises(ValueError):
            self.service.get_sector_ranking_history(TRADE_DATE, None)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            self.service.get_sector_ranking_history(TRADE_DATE, "")

    def test_dataset_unknown_rejected(self):
        with pytest.raises(ValueError):
            self.service.get_sector_ranking_history(TRADE_DATE, "eastmoney_industry")

    def test_dataset_list_rejected(self):
        # UT-015-015：禁止跨 dataset 列表参数。
        with pytest.raises(ValueError):
            self.service.get_sector_ranking_history(
                TRADE_DATE, ["sw2021_ta_cn", "eastmoney_industry"]
            )

    def test_limit_type_rejected(self):
        for bad in ("5", 5.0, True, [3]):
            with pytest.raises(ValueError):
                self.service.get_sector_ranking_history(TRADE_DATE, DATASET, limit=bad)

    def test_limit_non_positive_returns_all(self):
        # limit <= 0 / None → 全部（SPEC H-004 / UT-015-017）。
        writer = make_writer()
        writer.upsert(make_fully_complete_docs(make_valid_ranking_rows()))
        service = HistoricalSectorService(
            writer, expected_universe_by_dataset={DATASET: EXPECTED_SECTOR_CODES}
        )
        assert len(service.get_sector_ranking_history(TRADE_DATE, DATASET, limit=0).data) == 3
        assert len(service.get_sector_ranking_history(TRADE_DATE, DATASET, limit=-1).data) == 3
        assert len(service.get_sector_ranking_history(TRADE_DATE, DATASET, limit=None).data) == 3  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# T-015-013/014/015 / UT-015-009/013/017/020/021 — service query + traces
# ---------------------------------------------------------------------------


class TestHistoricalSectorServiceQuery:
    """Read path over the materialized collection + frozen trace contracts."""

    def test_category2_read_empty(self):
        # T-015-014 / UT-015-020：trade_date 合法但物化集合零条 →
        # empty + historical-ranking-empty，trace coverage:0/3,
        # completeness:empty, materialized:ok（逐字断言）。
        service, _ = _service()  # fresh db, nothing seeded
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert result.data == []
        assert result.is_empty()
        assert result.warnings == [WARNING_EMPTY]
        assert result.source_trace == EXPECTED_TRACE_PREFIX + [
            "coverage:0/3",
            "completeness:empty",
            "materialized:ok",
        ]

    def test_category3_incomplete_partial_rows(self):
        # T-015-006 / UT-015-006：物化集合含部分行 → 不返回部分榜单，
        # trace completeness:incomplete, materialized:miss，不写库。
        db = make_mongomock_db(make_fully_complete_docs(make_incomplete_rows()))
        service, writer = _service(db)
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert result.data == []
        assert result.warnings == [WARNING_INCOMPLETE]
        assert result.source_trace == EXPECTED_TRACE_PREFIX + [
            "coverage:2/3",
            "completeness:incomplete",
            "materialized:miss",
        ]
        # 不写库：集合内容保持不变。
        rows = writer.get(filter={"dataset": DATASET, "trade_date": TRADE_DATE})
        assert len(rows) == 2

    def test_category3_duplicate_rows(self):
        db = make_mongomock_db(make_fully_complete_docs(make_duplicate_rows()))
        service, _ = _service(db)
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert result.data == []
        assert result.warnings == [WARNING_INCOMPLETE]
        assert result.source_trace[-2:] == [
            "completeness:incomplete",
            "materialized:miss",
        ]

    def test_category4_zero_valid_rows(self):
        # T-015-007 / UT-015-007：build 零有效行 → empty +
        # historical-ranking-empty，trace coverage:0/3,
        # completeness:empty, materialized:miss（非 error）。
        raw_bad_docs = [
            {"dataset": DATASET, "trade_date": TRADE_DATE, "sector_code": "801120", "sector_name": "食品饮料"},
            {"dataset": DATASET, "trade_date": TRADE_DATE, "sector_code": "801780", "sector_name": "银行"},
        ]
        db = make_mongomock_db(raw_bad_docs)
        service, _ = _service(db)
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert result.data == []
        assert result.warnings == [WARNING_EMPTY]
        assert result.source_trace == EXPECTED_TRACE_PREFIX + [
            "coverage:0/3",
            "completeness:empty",
            "materialized:miss",
        ]

    def test_success_full_ranking(self):
        # T-015-015 / UT-015-021：observed == expected → 完整榜单，
        # warnings=[]，trace 顺序 dataset → trade_date → source →
        # coverage → completeness → materialized 逐字断言。
        db = make_mongomock_db(make_fully_complete_docs(make_valid_ranking_rows()))
        service, _ = _service(db)
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert result.warnings == []
        assert result.succeeded
        assert [r.sector_code for r in result.data] == ["801780", "801120", "801080"]
        assert [r.rank for r in result.data] == [1, 2, 3]
        assert result.source_trace == EXPECTED_TRACE_PREFIX + [
            "coverage:3/3",
            "completeness:complete",
            "materialized:ok",
        ]

    def test_success_ranking_is_stable_sorted(self):
        # 查询路径重新排序（不依赖存储顺序）：插入乱序仍稳定输出。
        docs = make_fully_complete_docs(make_valid_ranking_rows())
        docs = [docs[2], docs[0], docs[1]]  # 乱序插入
        db = make_mongomock_db(docs)
        service, _ = _service(db)
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert [r.sector_code for r in result.data] == ["801780", "801120", "801080"]

    def test_limit_truncation(self):
        # UT-015-017：limit > 0 → 前 N（截取仍按排名顺序）。
        db = make_mongomock_db(make_fully_complete_docs(make_valid_ranking_rows()))
        service, _ = _service(db)
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET, limit=2)
        assert len(result.data) == 2
        assert [r.sector_code for r in result.data] == ["801780", "801120"]

    def test_dataset_isolation_no_fallback(self):
        # T-015-009 / UT-015-009：不同 dataset 不混排、无静默 fallback。
        other_dataset = "eastmoney_industry"  # 仅用于模拟未来 dataset 的物化行
        db = make_mongomock_db(
            make_fully_complete_docs(make_valid_ranking_rows())
            + make_fully_complete_docs(
                [{"sector_code": "BK0489", "sector_name": "白酒", "close": 100.0, "pre_close": 99.0}],
                dataset=other_dataset,
            )
        )
        service, _ = _service(db)
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        # 只返回 sw2021_ta_cn 的行，不混入 eastmoney_industry。
        assert len(result.data) == 3
        assert {r.sector_code for r in result.data} == set(EXPECTED_SECTOR_CODES)

        # 无静默 fallback：仅其它 dataset 有行时，查询返回 empty 而非其行。
        db_only_other = make_mongomock_db(
            make_fully_complete_docs(
                [{"sector_code": "BK0489", "sector_name": "白酒", "close": 100.0, "pre_close": 99.0}],
                dataset=other_dataset,
            )
        )
        service2, _ = _service(db_only_other)
        result2 = service2.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert result2.data == []
        assert result2.warnings == [WARNING_EMPTY]
        assert result2.source_trace[-2:] == ["completeness:empty", "materialized:ok"]

    def test_revalidation_rejects_rank_tampering(self):
        # 物化行即使带错误 rank，也被 build 重新计算覆盖（服务以稳定排序为准）。
        docs = make_fully_complete_docs(make_valid_ranking_rows())
        docs[0]["rank"] = 999  # 篡改 rank 字段
        db = make_mongomock_db(docs)
        service, _ = _service(db)
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert [r.rank for r in result.data] == [1, 2, 3]

    def test_missing_expected_universe_fails_closed(self):
        # 未注入 expected universe 的 dataset → fail-closed：绝不断言 complete。
        service, _ = _service(expected_universe={})  # 无 universe 注入
        db = service.writer.db
        writer = service.writer
        writer.upsert(make_fully_complete_docs(make_valid_ranking_rows()))
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        # 物化行存在但无权威 universe → incomplete（不返回部分榜单）。
        assert result.data == []
        assert result.warnings == [WARNING_INCOMPLETE]
        assert db  # db 引用保持有效（测试完整性）


# ---------------------------------------------------------------------------
# E2E — injected mongomock db (task requirement: end-to-end proof)
# ---------------------------------------------------------------------------


class TestEndToEndInjectedDb:
    """Full offline chain: injected mongomock db → build → write → read."""

    def test_build_write_read_round_trip(self):
        db = mongomock.MongoClient().get_database("unified_data_test")
        writer = HistoricalRankingWriter(db)

        outcome = build_ranking_rows(
            make_valid_ranking_rows(),
            EXPECTED_SECTOR_CODES,
            DATASET,
            TRADE_DATE,
            updated_at=FIXED_UPDATED_AT,
        )
        assert outcome.status == "complete"

        write_result = writer.upsert([asdict(row) for row in outcome.rows])
        assert write_result.persisted == 3

        service = HistoricalSectorService(
            writer, expected_universe_by_dataset={DATASET: EXPECTED_SECTOR_CODES}
        )
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert result.warnings == []
        assert [r.sector_code for r in result.data] == ["801780", "801120", "801080"]
        assert result.source_trace == EXPECTED_TRACE_PREFIX + [
            "coverage:3/3",
            "completeness:complete",
            "materialized:ok",
        ]

    def test_empty_build_never_written(self):
        db = mongomock.MongoClient().get_database("unified_data_test")
        writer = HistoricalRankingWriter(db)
        outcome = build_ranking_rows(
            make_empty_rows(), EXPECTED_SECTOR_CODES, DATASET, TRADE_DATE
        )
        assert outcome.status == "empty"
        assert writer.get(filter={}) == []  # 零有效行不写库

        service = HistoricalSectorService(
            writer, expected_universe_by_dataset={DATASET: EXPECTED_SECTOR_CODES}
        )
        result = service.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert result.data == []
        assert result.warnings == [WARNING_EMPTY]  # 未物化 → Category 2


# ---------------------------------------------------------------------------
# Conditional client facade — only kept when client.py is modified
# ---------------------------------------------------------------------------


class TestClientFacadeE2E:
    """UnifiedDataClient.get_sector_ranking_history facade over injected db.

    These tests are the end-to-end proof required by the conditional
    allowlist entry (client.py): the facade is exercised from an
    injected mongomock db, not against a real Mongo / TA-CN.
    """

    def test_client_facade_returns_full_ranking(self):
        db = make_mongomock_db(make_fully_complete_docs(make_valid_ranking_rows()))
        client = UnifiedDataClient(
            historical_ranking_db=db,
            historical_ranking_expected_universe={DATASET: EXPECTED_SECTOR_CODES},
        )
        result = client.get_sector_ranking_history(TRADE_DATE, DATASET)
        assert result.warnings == []
        assert [r.sector_code for r in result.data] == ["801780", "801120", "801080"]
        assert result.source_trace == EXPECTED_TRACE_PREFIX + [
            "coverage:3/3",
            "completeness:complete",
            "materialized:ok",
        ]

    def test_client_facade_requires_injected_db(self):
        client = UnifiedDataClient()  # 无 mongomock db 注入
        with pytest.raises(RuntimeError):
            client.get_sector_ranking_history(TRADE_DATE, DATASET)
