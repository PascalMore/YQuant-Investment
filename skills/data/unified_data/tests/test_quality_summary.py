"""QualitySummary 单元测试（DESIGN-03-011 §6, SPEC-03-011 §7）。

行为矩阵 QS-101..105 + 设计契约：
* QS-101: mongo_db=None → noop
* QS-102/104: mongomock upsert 按 (domain, security_id, date) 复合键；query_count 累加
* QS-103: 写入异常 catch-and-log
* QS-105: get_summary 无数据 → []
* schema 字段（DESIGN §6.2）+ min/max/avg + 复合键隔离 + 日期范围 + 排序

TDD：测试先于补全；RED 阶段 import 失败 / 行为不符，GREEN 由
``quality/summary.py`` 现有实现转为 PASS。
"""

from __future__ import annotations

from datetime import datetime

import mongomock
import pytest

from skills.data.unified_data import DataResult, Market, SecurityId
from skills.data.unified_data.quality.summary import QualitySummary


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def mongomock_db():
    return mongomock.MongoClient().db


@pytest.fixture
def maotai_sid() -> SecurityId:
    return SecurityId(market=Market.CN, symbol="600519")


@pytest.fixture
def result_ok(maotai_sid, quality_fixed_now):
    return DataResult(
        data=[{"close": 1500.0, "volume": 1000000}],
        security_id=maotai_sid,
        domain="market_data",
        operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=quality_fixed_now,
        freshness="delayed",
    )


# --- QS-101: noop -----------------------------------------------------------


class TestNoop:
    def test_update_with_none_db_does_not_raise(self, result_ok):
        summary = QualitySummary(mongo_db=None)
        assert (
            summary.update(
                result_ok, quality_score=0.9, quality_tier="direct_use"
            )
            is None
        )

    def test_get_summary_with_none_db_returns_empty(self, maotai_sid):
        summary = QualitySummary(mongo_db=None)
        assert summary.get_summary("market_data", maotai_sid) == []

    def test_update_with_none_db_does_not_create_collection(
        self, result_ok, mongomock_db
    ):
        QualitySummary(mongo_db=None).update(
            result_ok, quality_score=0.9, quality_tier="direct_use"
        )
        assert (
            "03_data_ud_quality_summary"
            not in mongomock_db.list_collection_names()
        )


# --- QS-102/104: upsert + 累加 + provider distribution --------------------


class TestUpsert:
    def test_repeated_key_upserts_single_document(
        self, result_ok, mongomock_db, quality_fixed_now
    ):
        summary = QualitySummary(mongo_db=mongomock_db)
        for _ in range(2):
            summary.update(
                result_ok,
                quality_score=0.9,
                quality_tier="direct_use",
                now=quality_fixed_now,
            )
        assert mongomock_db["03_data_ud_quality_summary"].count_documents({}) == 1

    def test_update_creates_doc_with_composite_key(
        self, result_ok, mongomock_db, quality_fixed_now
    ):
        QualitySummary(mongo_db=mongomock_db).update(
            result_ok,
            quality_score=0.9,
            quality_tier="direct_use",
            now=quality_fixed_now,
        )
        date_str = quality_fixed_now.strftime("%Y-%m-%d")
        doc = mongomock_db["03_data_ud_quality_summary"].find_one(
            {"_id": f"{result_ok.domain}:{result_ok.security_id.canonical}:{date_str}"}
        )
        assert doc is not None
        assert doc["domain"] == "market_data"
        assert doc["security_id"] == "CN:600519"
        assert doc["date"] == date_str
        assert doc["last_updated"] == quality_fixed_now

    def test_update_increments_query_count(
        self, result_ok, mongomock_db, quality_fixed_now
    ):
        summary = QualitySummary(mongo_db=mongomock_db)
        for _ in range(3):
            summary.update(
                result_ok,
                quality_score=0.9,
                quality_tier="direct_use",
                now=quality_fixed_now,
            )
        assert (
            mongomock_db["03_data_ud_quality_summary"].find_one({})["query_count"]
            == 3
        )

    def test_update_increments_provider_distribution(
        self, result_ok, mongomock_db, quality_fixed_now
    ):
        summary = QualitySummary(mongo_db=mongomock_db)
        summary.update(
            result_ok,
            quality_score=0.9,
            quality_tier="direct_use",
            now=quality_fixed_now,
        )
        result_ok.provider = "tushare"
        summary.update(
            result_ok,
            quality_score=0.8,
            quality_tier="warning",
            now=quality_fixed_now,
        )
        doc = mongomock_db["03_data_ud_quality_summary"].find_one({})
        assert doc["provider_distribution"] == {
            "ta_cn_internal": 1,
            "tushare": 1,
        }


# --- min / max / avg correctness (DESIGN §6.2 + §6.3) ---------------------


class TestMinMaxAvg:
    def _drive(self, result_ok, mongomock_db, scores, quality_fixed_now):
        summary = QualitySummary(mongo_db=mongomock_db)
        for s in scores:
            summary.update(
                result_ok,
                quality_score=s,
                quality_tier="direct_use",
                now=quality_fixed_now,
            )
        return mongomock_db["03_data_ud_quality_summary"].find_one({})

    def test_min_quality_score_tracks_lowest(
        self, result_ok, mongomock_db, quality_fixed_now
    ):
        doc = self._drive(result_ok, mongomock_db, [0.9, 0.5, 0.7], quality_fixed_now)
        assert doc["min_quality_score"] == pytest.approx(0.5)

    def test_max_quality_score_tracks_highest(
        self, result_ok, mongomock_db, quality_fixed_now
    ):
        doc = self._drive(result_ok, mongomock_db, [0.6, 0.95, 0.7], quality_fixed_now)
        assert doc["max_quality_score"] == pytest.approx(0.95)

    def test_avg_quality_score_is_running_average(
        self, result_ok, mongomock_db, quality_fixed_now
    ):
        doc = self._drive(result_ok, mongomock_db, [0.8, 0.9, 1.0], quality_fixed_now)
        assert doc["avg_quality_score"] == pytest.approx(0.9)


# --- 复合键隔离 + get_summary ---------------------------------------------


class TestKeyAndGet:
    def test_different_date_creates_separate_doc(
        self, result_ok, mongomock_db
    ):
        summary = QualitySummary(mongo_db=mongomock_db)
        summary.update(
            result_ok,
            quality_score=0.9,
            quality_tier="direct_use",
            now=datetime(2026, 7, 15, 10, 0, 0),
        )
        summary.update(
            result_ok,
            quality_score=0.5,
            quality_tier="warning",
            now=datetime(2026, 7, 16, 10, 0, 0),
        )
        assert (
            mongomock_db["03_data_ud_quality_summary"].count_documents({}) == 2
        )

    def test_different_security_creates_separate_doc(
        self, result_ok, mongomock_db, quality_fixed_now
    ):
        summary = QualitySummary(mongo_db=mongomock_db)
        summary.update(
            result_ok,
            quality_score=0.9,
            quality_tier="direct_use",
            now=quality_fixed_now,
        )
        result_ok.security_id = SecurityId(market=Market.CN, symbol="000001")
        summary.update(
            result_ok,
            quality_score=0.7,
            quality_tier="warning",
            now=quality_fixed_now,
        )
        docs = list(mongomock_db["03_data_ud_quality_summary"].find({}))
        assert len(docs) == 2
        assert {d["security_id"] for d in docs} == {"CN:600519", "CN:000001"}

    def test_get_summary_returns_empty_when_no_data(
        self, maotai_sid, mongomock_db
    ):
        summary = QualitySummary(mongo_db=mongomock_db)
        assert summary.get_summary("market_data", maotai_sid) == []

    def test_get_summary_date_range_and_sort(self, result_ok, mongomock_db):
        summary = QualitySummary(mongo_db=mongomock_db)
        for day in (13, 14, 15, 16, 17):
            summary.update(
                result_ok,
                quality_score=0.9,
                quality_tier="direct_use",
                now=datetime(2026, 7, day, 12, 0, 0),
            )
        rows = summary.get_summary(
            "market_data",
            result_ok.security_id,
            from_date="2026-07-15",
            to_date="2026-07-16",
        )
        assert sorted(r["date"] for r in rows) == ["2026-07-15", "2026-07-16"]
        all_rows = summary.get_summary("market_data", result_ok.security_id)
        dates = [r["date"] for r in all_rows]
        assert dates == sorted(dates, reverse=True)


# --- QS-103: catch-and-log -------------------------------------------------


class TestCatchAndLog:
    def test_update_with_broken_db_does_not_raise(
        self, result_ok, mongomock_db, quality_fixed_now
    ):
        coll = mongomock_db["03_data_ud_quality_summary"]
        original = coll.update_one
        coll.update_one = lambda *a, **kw: (_ for _ in ()).throw(
            ConnectionError("mongo down")
        )
        try:
            QualitySummary(mongo_db=mongomock_db).update(
                result_ok,
                quality_score=0.9,
                quality_tier="direct_use",
                now=quality_fixed_now,
            )
        finally:
            coll.update_one = original

    def test_get_summary_with_broken_db_returns_empty(
        self, maotai_sid, mongomock_db
    ):
        coll = mongomock_db["03_data_ud_quality_summary"]
        original = coll.find
        coll.find = lambda *a, **kw: (_ for _ in ()).throw(
            ConnectionError("mongo down")
        )
        try:
            assert (
                QualitySummary(mongo_db=mongomock_db).get_summary(
                    "market_data", maotai_sid
                )
                == []
            )
        finally:
            coll.find = original