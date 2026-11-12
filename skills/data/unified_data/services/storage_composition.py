"""UD 生产装配工厂 — 03-018 §3.1 / §4.2。

``build_persistent_client`` 是**纯装配**：不联网、不建索引、不写库、不读
env。检查两个库名 → TA-CN adapter 绑定只读源 → local/cache 绑定 UD 目标 →
可选 audit 绑定显式 audit_db → history reader 绑定目标 → Client 注入。

``audit_db`` 未显式给出时**不启用** audit（没有共享高权凭据回退）。
``quality_scorer`` 只透传显式注入对象；``build_quality_summary`` 是独立
builder，保持"质量汇总不自动启用"的现状。
"""

from __future__ import annotations

from typing import Any

from ..cache_manager import CacheManager
from ..client import UnifiedDataClient
from ..history_reader import Btc5mHistoryReader
from ..local_mongo_adapter import LocalMongoAdapter
from ..quality.summary import QualitySummary
from ..storage import UDDatabases, assert_ud_database


def build_quality_summary(ud_db: Any) -> QualitySummary:
    """构造绑定 UD 目标库的质量汇总组件（不自动调用）。"""
    assert_ud_database(ud_db)
    return QualitySummary(mongo_db=ud_db)


def build_persistent_client(
    databases: UDDatabases,
    *,
    registry: Any | None = None,
    config: Any | None = None,
    audit_db: Any | None = None,
    quality_scorer: Any | None = None,
) -> UnifiedDataClient:
    """纯装配生产 :class:`UnifiedDataClient`。

    Args:
        databases: :class:`~skills.data.unified_data.storage.UDDatabases`，
            由同一个 client 派生。
        registry: 可选 provider registry；``None`` 用默认空 registry。
        config: 可选 :class:`UnifiedDataConfig`。
        audit_db: 显式审计库句柄；``None`` 表示**不启用** audit。
        quality_scorer: 显式质量打分器；``None`` 表示不启用打分。

    Returns:
        装配完成的 :class:`UnifiedDataClient`。

    Raises:
        UDDatabaseError: 传入句柄的库名与目标不符。
    """
    assert_ud_database(databases.ud)
    if audit_db is not None:
        assert_ud_database(audit_db)

    local_adapter = LocalMongoAdapter(databases.ud)
    cache_manager = CacheManager(databases.ud)
    audit_logger = None
    if audit_db is not None:
        from ..audit.logger import AuditLogger

        audit_logger = AuditLogger(mongo_db=audit_db)
    history_reader = Btc5mHistoryReader(databases.ud)

    return UnifiedDataClient(
        registry=registry,
        config=config,
        local_mongo_adapter=local_adapter,
        cache_manager=cache_manager,
        quality_scorer=quality_scorer,
        audit_logger=audit_logger,
        history_reader=history_reader,
    )


__all__ = ["build_persistent_client", "build_quality_summary"]
