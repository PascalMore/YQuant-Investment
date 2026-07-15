"""AuditLogger 单元测试（DESIGN-03-011 §5, SPEC-03-011 §6）。

行为矩阵 AL-101..105 + schema 完整性（DESIGN §5.2）：
* AL-101: mongo_db=None → noop，不写、不抛
* AL-102: mongo_db=mongomock → 写入审计集合
* AL-103: 写入异常 → catch-and-log，不抛
* AL-104: 非预期异常 → catch-and-log，不抛
* AL-105: uuid 唯一 + audit_id 字段存在

TDD 顺序：测试先于实现落地；RED 阶段 import 失败，GREEN 阶段由
``audit/logger.py`` 落地后转为 PASS。
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from uuid import UUID

import mongomock
import pytest

from skills.data.unified_data import DataResult, Market, SecurityId
from skills.data.unified_data.audit import AuditLogger
from skills.data.unified_data.quality.summary import QualitySummary


# ---------------------------------------------------------------------------
# Fixtures local to this file
# ---------------------------------------------------------------------------


@pytest.fixture
def mongomock_db():
    """Fresh mongomock DB per-test; no real MongoDB connection."""
    return mongomock.MongoClient().db


@pytest.fixture
def maotai_sid() -> SecurityId:
    return SecurityId(market=Market.CN, symbol="600519")


@pytest.fixture
def result_ok(maotai_sid, quality_fixed_now):
    """Normal delayed result with quality_score."""
    return DataResult(
        data=[{"close": 1500.0, "volume": 1000000}],
        security_id=maotai_sid,
        domain="market_data",
        operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=quality_fixed_now,
        freshness="delayed",
        quality_score=1.0,
        source_trace=["ta_cn_internal(ok)"],
    )


@pytest.fixture
def result_err(maotai_sid, quality_fixed_now):
    """Error result (provider='error')."""
    return DataResult.error(
        maotai_sid,
        "market_data",
        "kline_daily",
        "tushare",
        Exception("tushare rate limit"),
        fetched_at=quality_fixed_now,
    )


# ---------------------------------------------------------------------------
# AL-101: mongo_db=None → noop
# ---------------------------------------------------------------------------


class TestNoop:
    def test_log_with_none_db_does_not_raise(self, result_ok):
        logger = AuditLogger(mongo_db=None)
        # Should not raise, should not return anything useful.
        assert logger.log(result_ok) is None

    def test_log_with_none_db_does_not_create_collection(
        self, result_ok, mongomock_db
    ):
        # Note: this fixture provides a DB but we pass None to the logger.
        # Logger must not touch the DB even if one exists in scope.
        logger = AuditLogger(mongo_db=None)
        logger.log(result_ok, consumer="test", duration_ms=42)
        assert "03_data_ud_query_audit" not in mongomock_db.list_collection_names()


# ---------------------------------------------------------------------------
# AL-102: mongomock 写入
# ---------------------------------------------------------------------------


class TestMongomockWrite:
    def test_log_writes_one_document(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        logger.log(result_ok, consumer="ud_test", duration_ms=123)
        coll = mongomock_db["03_data_ud_query_audit"]
        docs = list(coll.find({}))
        assert len(docs) == 1

    def test_log_does_not_raise_with_default_kwargs(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        logger.log(result_ok)

    def test_same_result_is_append_only(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        logger.log(result_ok)
        logger.log(result_ok)
        assert mongomock_db["03_data_ud_query_audit"].count_documents({}) == 2

    def test_each_log_creates_unique_uuid4_audit_id(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        logger.log(result_ok)
        logger.log(result_ok)
        coll = mongomock_db["03_data_ud_query_audit"]
        ids = [doc["audit_id"] for doc in coll.find({})]
        parsed = [UUID(value) for value in ids]
        assert len(ids) == 2
        assert ids[0] != ids[1]
        assert all(value.version == 4 for value in parsed)

    def test_log_updates_injected_quality_summary(self, result_ok, mongomock_db):
        summary = QualitySummary(mongo_db=mongomock_db)
        logger = AuditLogger(mongo_db=mongomock_db, quality_summary=summary)
        logger.log(result_ok)
        doc = mongomock_db["03_data_ud_quality_summary"].find_one({})
        assert doc is not None
        assert doc["query_count"] == 1


# ---------------------------------------------------------------------------
# Schema 完整性（DESIGN §5.2）
# ---------------------------------------------------------------------------


class TestSchema:
    REQUIRED_FIELDS = (
        "audit_id",
        "security_id",
        "market",
        "capability",
        "consumer",
        "fetched_at",
        "duration_ms",
        "provider",
        "source_trace",
        "freshness",
        "quality_score",
        "quality_tier",
        "success",
        "error_message",
        "params",
        "quality_warnings",
    )

    def test_required_fields_present(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        logger.log(
            result_ok,
            consumer="ud_test",
            duration_ms=42,
            params={"limit": 120},
        )
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc is not None
        for field in self.REQUIRED_FIELDS:
            assert field in doc, f"missing field: {field}"

    def test_timestamp_is_stored_from_result(self, result_ok, mongomock_db):
        AuditLogger(mongo_db=mongomock_db).log(result_ok)
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc["fetched_at"] == result_ok.fetched_at

    def test_capability_format(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        logger.log(result_ok)
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        # capability = "domain.operation"
        assert doc["capability"] == "market_data.kline_daily"

    def test_security_id_is_canonical(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        logger.log(result_ok)
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc["security_id"] == "CN:600519"
        assert doc["market"] == "CN"

    def test_success_true_for_normal_result(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        logger.log(result_ok)
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc["success"] is True
        assert doc["error_message"] is None

    def test_success_false_for_error_result(self, result_err, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        logger.log(result_err)
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc["success"] is False
        assert doc["provider"] == "error"
        assert doc["error_message"] is not None

    def test_params_passthrough(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        params = {"limit": 120, "start_date": "2026-07-01"}
        logger.log(result_ok, params=params)
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc["params"] == params

    def test_quality_warnings_carry_scorer_warnings(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        # Mutate the result to have a quality warning list.
        result_ok.warnings = ["scored: 0.95"]
        logger.log(result_ok)
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc["quality_warnings"] == ["scored: 0.95"]


# ---------------------------------------------------------------------------
# AL-103/104: catch-and-log
# ---------------------------------------------------------------------------


class TestCatchAndLog:
    def test_write_failure_does_not_propagate(self, result_ok, mongomock_db):
        logger = AuditLogger(mongo_db=mongomock_db)
        # Patch insert_one to raise — must NOT escape.
        with patch.object(
            mongomock_db["03_data_ud_query_audit"],
            "insert_one",
            side_effect=ConnectionError("mongo down"),
        ):
            # Should not raise.
            logger.log(result_ok)

    def test_unexpected_exception_does_not_propagate(
        self, result_ok, mongomock_db
    ):
        logger = AuditLogger(mongo_db=mongomock_db)
        with patch.object(
            mongomock_db["03_data_ud_query_audit"],
            "insert_one",
            side_effect=RuntimeError("boom"),
        ):
            # Should not raise.
            logger.log(result_ok)

    def test_failure_logged_at_warning(self, result_ok, mongomock_db, caplog):
        import logging
        logger = AuditLogger(mongo_db=mongomock_db)
        with patch.object(
            mongomock_db["03_data_ud_query_audit"],
            "insert_one",
            side_effect=ConnectionError("mongo down"),
        ):
            with caplog.at_level(logging.WARNING, logger="skills.data.unified_data.audit"):
                logger.log(result_ok)
        assert any("audit" in r.message.lower() or "failed" in r.message.lower()
                   for r in caplog.records)


# ---------------------------------------------------------------------------
# Custom collection name
# ---------------------------------------------------------------------------


class TestCustomCollection:
    def test_custom_collection_name_used(self, result_ok, mongomock_db):
        logger = AuditLogger(
            mongo_db=mongomock_db,
            collection_name="custom_audit_collection",
        )
        logger.log(result_ok)
        assert "custom_audit_collection" in mongomock_db.list_collection_names()
        assert "03_data_ud_query_audit" not in mongomock_db.list_collection_names()