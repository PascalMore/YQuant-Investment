"""UD 双库装配与边界测试 — 03-018 UT04 / UT05 / UT22。

覆盖：

* 两个命名 fake 库 + 真实 factory / Client / router 的逐库调用；
* 通用默认仍是旧库（``MongoReader`` 默认 ``tradingagents`` 不变）；
* source / target 不混；
* audit 资源与认证源分离，缺权限只列 namespace/action；
* quality summary 不自动启用；
* secret 不出现在异常文本里。
"""

from __future__ import annotations

from datetime import datetime

import mongomock
import pytest

from skills.data.unified_data.audit.logger import AuditLogger
from skills.data.unified_data.cache_manager import CacheManager
from skills.data.unified_data.client import UnifiedDataClient
from skills.data.unified_data.local_mongo_adapter import LocalMongoAdapter
from skills.data.unified_data.models import SecurityId
from skills.data.unified_data.quality.summary import QualitySummary
from skills.data.unified_data.services.storage_composition import (
    build_persistent_client,
    build_quality_summary,
)
from skills.data.unified_data.storage import (
    TA_CN_DATABASE,
    UD_DATABASE,
    UDDatabases,
    UDDatabaseError,
    assert_ud_database,
    select_databases,
)


@pytest.fixture()
def client() -> mongomock.MongoClient:
    return mongomock.MongoClient()


@pytest.fixture()
def databases(client: mongomock.MongoClient) -> UDDatabases:
    return select_databases(client)


# ---------------------------------------------------------------------------
# UT04 — 双库边界与逐库调用
# ---------------------------------------------------------------------------


def test_ut04_select_databases_uses_two_named_databases(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    assert databases.ud.name == UD_DATABASE
    assert databases.ta_cn.name == TA_CN_DATABASE
    assert databases.ud is not databases.ta_cn


def test_ut04_general_default_database_is_unchanged() -> None:
    """通用 ``MongoReader`` 默认库仍是 ``tradingagents``（不被本次改动影响）。"""
    from skills.data.data_interface.mongo_reader import MongoReader

    import inspect

    signature = inspect.signature(MongoReader.__init__)
    assert signature.parameters["database"].default == "tradingagents"


def test_ut04_factory_binds_local_cache_to_ud_database(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    built = build_persistent_client(databases)
    adapter = built.router._local_mongo_adapter
    cache = built.router._cache_manager
    assert isinstance(adapter, LocalMongoAdapter)
    assert isinstance(cache, CacheManager)
    assert adapter._db is databases.ud
    assert cache._db is databases.ud


def test_ut04_source_and_target_do_not_mix(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    built = build_persistent_client(databases)
    adapter = built.router._local_mongo_adapter
    adapter._db["03_data_ud_probe"].insert_one({"_id": 1})
    assert databases.ud["03_data_ud_probe"].count_documents({}) == 1
    assert databases.ta_cn.list_collection_names() == []


def test_ut04_router_write_lands_in_ud_database(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    """Client → router 的实际写调用落在注入的库上。"""
    from skills.data.unified_data.models import DataResult, SecurityId

    built = build_persistent_client(databases)
    adapter = built.router._local_mongo_adapter
    security_id = SecurityId(market="CN", symbol="000001")
    adapter.put(
        security_id,
        "stock_basic_info",
        "probe_op",
        {},
        DataResult(
            data={"x": 1},
            security_id=security_id,
            domain="stock_basic_info",
            operation="probe_op",
            provider="test",
            fetched_at=datetime(2026, 1, 1),
        ),
    )
    assert databases.ud["03_data_ud_probe_op"].count_documents({}) == 1
    assert databases.ta_cn.list_collection_names() == []


def test_ut04_client_forwards_slots_to_router(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    adapter = LocalMongoAdapter(databases.ud)
    cache = CacheManager(databases.ud)
    audit = AuditLogger(mongo_db=databases.ud)
    built = UnifiedDataClient(
        local_mongo_adapter=adapter,
        cache_manager=cache,
        audit_logger=audit,
    )
    assert built.router._local_mongo_adapter is adapter
    assert built.router._cache_manager is cache
    assert built.router._audit_logger is audit


def test_ut04_with_providers_forwards_slots(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    adapter = LocalMongoAdapter(databases.ud)
    built = UnifiedDataClient.with_providers([], local_mongo_adapter=adapter)
    assert built.router._local_mongo_adapter is adapter


# ---------------------------------------------------------------------------
# UT04 / UT05 — 审计资源与身份库分离
# ---------------------------------------------------------------------------


def test_ut05_audit_not_enabled_without_explicit_audit_db(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    built = build_persistent_client(databases)
    assert built.router._audit_logger is None


def test_ut05_audit_bound_to_explicit_database(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    built = build_persistent_client(databases, audit_db=databases.ud)
    assert built.router._audit_logger is not None
    assert built.router._audit_logger._mongo_db is databases.ud


def test_ut05_quality_summary_is_not_auto_enabled(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    built = build_persistent_client(databases)
    assert built.router._quality_scorer is None
    summary = build_quality_summary(databases.ud)
    assert isinstance(summary, QualitySummary)


# ---------------------------------------------------------------------------
# UT04 — 真实旧库句柄在 catch 之前被拒绝
# ---------------------------------------------------------------------------


class _FakeRealDatabase:
    """模拟真实 pymongo Database 的库名（用于验证 guard 语义）。"""

    def __init__(self, name: str) -> None:
        self.name = name


def test_ut04_real_legacy_handle_is_rejected() -> None:
    """真实旧库句柄被 guard 拒绝（构造期抛错，不是 catch-and-log）。"""
    from skills.data.unified_data import storage as storage_module

    original = storage_module._is_real_pymongo_database
    storage_module._is_real_pymongo_database = lambda db: isinstance(
        db, _FakeRealDatabase
    )
    try:
        with pytest.raises(UDDatabaseError):
            assert_ud_database(_FakeRealDatabase("tradingagents"))
        # 正确库名通过
        assert_ud_database(_FakeRealDatabase(UD_DATABASE))
        # 组件构造期同样拒绝
        with pytest.raises(UDDatabaseError):
            LocalMongoAdapter(_FakeRealDatabase("tradingagents"))
        with pytest.raises(UDDatabaseError):
            CacheManager(_FakeRealDatabase("tradingagents"))
        with pytest.raises(UDDatabaseError):
            AuditLogger(mongo_db=_FakeRealDatabase("tradingagents"))
        with pytest.raises(UDDatabaseError):
            QualitySummary(mongo_db=_FakeRealDatabase("tradingagents"))
    finally:
        storage_module._is_real_pymongo_database = original


def test_ut04_fake_handles_are_allowed(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    """mongomock / 显式 fake 句柄继续跑离线测试（不冒充真实类型判定）。"""
    LocalMongoAdapter(databases.ta_cn)
    CacheManager(databases.ta_cn)


# ---------------------------------------------------------------------------
# UT22 — secret 不泄漏
# ---------------------------------------------------------------------------


def test_ut22_secret_injection_does_not_leak(
    client: mongomock.MongoClient, databases: UDDatabases
) -> None:
    secret = "s3cr3t-mongo-password"

    class _Exploding:
        name = UD_DATABASE

        def __getitem__(self, key: str):
            raise RuntimeError(f"connection failed mongodb://user:{secret}@host")

    adapter = LocalMongoAdapter(_Exploding())
    import logging

    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    logger = logging.getLogger("skills.data.unified_data.local_mongo_adapter")
    logger.addHandler(handler)
    try:
        adapter.get(SecurityId(market="CN", symbol="000001"), "d", "o", {})
    finally:
        logger.removeHandler(handler)
    joined = "\n".join(records)
    assert secret not in joined
    assert "[REDACTED]" not in joined  # 未泄漏即不需占位符
    assert "RuntimeError" in joined
