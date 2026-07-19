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


# ---------------------------------------------------------------------------
# Phase 2 rollout fixes — params allow-list + sensitive deny-list + 365d TTL
# (DESIGN-03-011 §5.3, §8.6 — Pascal 已确认)
# ---------------------------------------------------------------------------


class TestDefaultTtlDays:
    """AL-301: ttl_days 默认 365 天（Pascal 已确认；非历史 90）。"""

    def test_default_ttl_days_is_365(self):
        from skills.data.unified_data.audit import AuditLogger as AL

        assert AL().ttl_days == 365

    def test_explicit_ttl_days_honored(self):
        from skills.data.unified_data.audit import AuditLogger as AL

        assert AL(ttl_days=120).ttl_days == 120


class TestParamsAllowList:
    """AL-302..308: params 严格白名单 + 敏感 deny-list。"""

    def test_known_query_keys_kept(self, result_ok, mongomock_db):
        AuditLogger(mongo_db=mongomock_db).log(
            result_ok,
            params={
                "security_id": "CN:600519",
                "market": "CN",
                "domain": "market_data",
                "operation": "kline_daily",
                "start_date": "2026-07-01",
                "end_date": "2026-07-16",
                "limit": 120,
                "frequency": "1d",
                "provider": "tushare",
                "consumer": "ud_test",
                "force_refresh": False,
            },
        )
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc is not None
        for key in (
            "security_id", "market", "domain", "operation",
            "start_date", "end_date", "limit", "frequency",
            "provider", "consumer", "force_refresh",
        ):
            assert key in doc["params"], f"allowed key dropped: {key}"

    def test_unknown_keys_dropped(self, result_ok, mongomock_db):
        AuditLogger(mongo_db=mongomock_db).log(
            result_ok,
            params={
                "limit": 50,
                "sneaky_field": "x",
                "internal_token": "leaked",  # both unknown AND contains token
                "trace_id": "abc",
                "extra_blob": {"foo": "bar"},
            },
        )
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc is not None
        assert doc["params"] == {"limit": 50}

    def test_sensitive_keys_never_persisted(self, result_ok, mongomock_db):
        AuditLogger(mongo_db=mongomock_db).log(
            result_ok,
            params={
                "token": "leaked-token",
                "password": "leaked-pw",
                "secret": "leaked-secret",
                "Authorization": "Bearer leaked",
                "cookie": "session=leaked",
                "mongodb_uri": "mongodb://user:pass@host",
                "api_key": "leaked-key",
                "limit": 10,
            },
        )
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc is not None
        serialized = repr(doc["params"]).lower()
        for forbidden in (
            "token", "password", "secret", "bearer", "cookie",
            "mongodb://", "api_key", "leaked",
        ):
            assert forbidden not in serialized, (
                f"sensitive substring {forbidden!r} leaked into params: {doc['params']!r}"
            )
        # allow-list 中的 limit 仍保留
        assert doc["params"].get("limit") == 10

    def test_connection_string_substring_dropped(self, result_ok, mongomock_db):
        # 即使键名是某个允许的语义字段，子串匹配到 mongodb:// 也丢弃
        AuditLogger(mongo_db=mongomock_db).log(
            result_ok,
            params={
                "market": "mongodb://localhost:27017",
                "limit": 5,
            },
        )
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc is not None
        assert "market" not in doc["params"], (
            "connection-string value must be dropped even if key is allow-listed"
        )
        assert doc["params"] == {"limit": 5}

    def test_none_params_yields_empty_dict(self, result_ok, mongomock_db):
        AuditLogger(mongo_db=mongomock_db).log(result_ok, params=None)
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc is not None
        assert doc["params"] == {}

    def test_non_string_key_dropped(self, result_ok, mongomock_db):
        AuditLogger(mongo_db=mongomock_db).log(
            result_ok,
            params={"limit": 7, 123: "numeric-key", ("a", "b"): "tuple-key"},
        )
        doc = mongomock_db["03_data_ud_query_audit"].find_one({})
        assert doc is not None
        assert doc["params"] == {"limit": 7}

    def test_sanitize_helper_directly(self):
        from skills.data.unified_data.audit import (
            ALLOWED_PARAM_KEYS,
            sanitize_params,
        )

        # 已确认的 allow-list 必须至少包含这些键（SPEC/RFC 已声明的 query 语义字段）
        for key in (
            "security_id", "market", "domain", "operation",
            "limit", "frequency", "provider", "consumer",
            "force_refresh",
        ):
            assert key in ALLOWED_PARAM_KEYS, (
                f"required allow-list key missing: {key}"
            )

        sanitized = sanitize_params(
            {"limit": 1, "TOKEN": "x", "mongodb_uri": "mongodb://x", "x": 1}
        )
        assert sanitized == {"limit": 1}


class TestAuditContractUnchanged:
    """AL-309: 既有 noop / catch-and-log 语义保持。"""

    def test_default_ctor_uses_365(self):
        # 默认 365，且不创建任何索引/连接
        al = AuditLogger()
        assert al.ttl_days == 365
        # mongo_db=None 时 log 必须不抛
        from datetime import datetime
        from skills.data.unified_data import DataResult, Market, SecurityId
        r = DataResult(
            data=[{"close": 1.0}],
            security_id=SecurityId(market=Market.CN, symbol="000001"),
            domain="market_data",
            operation="kline_daily",
            provider="ta_cn_internal",
            fetched_at=datetime.now(),
            freshness="delayed",
            quality_score=1.0,
        )
        assert al.log(r) is None

    def test_qs_f3_quality_summary_injection_rejected(self):
        """QS-F3 (SPEC §11.3): AuditLogger.__init__ 不接受 quality_summary 参数。

        Phase 1 Audit-only 中 QualitySummary 不可注入。显式传入
        quality_summary kwarg 时 __init__ 必须抛 TypeError。
        """
        with pytest.raises(TypeError):
            AuditLogger(mongo_db=None, quality_summary="anything")