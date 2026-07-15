"""AuditLogger — Phase 2 查询审计日志（DESIGN-03-011 §5, SPEC-03-011 §6）。

追加式审计写入器。``mongo_db=None`` 时为 noop；写入采用 catch-and-log，
不向调用方抛出异常。绝不自行建立连接或创建索引（DDL 留待 Pascal
生产确认后由独立脚本执行）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from ..models import DataResult

logger = logging.getLogger(__name__)


class AuditLogger:
    """追加式查询审计日志组件。

    Args:
        mongo_db: MongoDB 数据库句柄。``None`` 时进入 noop 模式，所有
            :meth:`log` 调用直接返回，不写入任何数据。
        collection_name: 审计集合名（默认 ``03_data_ud_query_audit``）。
        ttl_days: TTL 过期天数（默认 90 天）。本组件不创建 TTL 索引，
            仅供将来 Pascal 确认后由独立迁移脚本使用。
        quality_summary: 可选 QualitySummary 实例。注入后每次 log()
            内部触发 summary.update()。（DESIGN §8 设计选择）。
    """

    def __init__(
        self,
        mongo_db: Any = None,
        collection_name: str = "03_data_ud_query_audit",
        ttl_days: int = 90,
        quality_summary: "QualitySummary | None" = None,
    ) -> None:
        self._mongo_db = mongo_db
        self._collection_name = collection_name
        self._ttl_days = ttl_days
        self._quality_summary = quality_summary

    @property
    def collection_name(self) -> str:
        return self._collection_name

    @property
    def ttl_days(self) -> int:
        return self._ttl_days

    def log(
        self,
        result: DataResult,
        *,
        consumer: str = "unified_data",
        duration_ms: int = 0,
        params: dict | None = None,
    ) -> None:
        """记录一次查询审计事件。catch-and-log，不向调用方抛出异常。

        Args:
            result: 查询结果 DataResult。
            consumer: 调用方标识。
            duration_ms: 查询耗时（毫秒）。
            params: 查询参数（不含敏感字段）。
        """
        if self._mongo_db is None:
            return  # noop

        try:
            doc = self._build_document(
                result, consumer, duration_ms, params
            )
            self._mongo_db[self._collection_name].insert_one(doc)

            # Phase 2 internal: trigger QualitySummary update (DESIGN §8)
            if self._quality_summary is not None:
                self._quality_summary.update(
                    result,
                    quality_score=result.quality_score,
                    quality_tier=doc.get("quality_tier"),
                    now=result.fetched_at,
                )
        except Exception as exc:
            logger.warning(
                "AuditLogger.log failed (catch-and-log): %s", exc
            )

    def _build_document(
        self,
        result: DataResult,
        consumer: str,
        duration_ms: int,
        params: dict | None,
    ) -> dict[str, Any]:
        """构造审计文档（DESIGN §5.2 schema）。"""
        is_error = result.provider == "error"
        quality_tier = _infer_tier_from_score(result.quality_score)
        return {
            "audit_id": str(uuid.uuid4()),
            "security_id": result.security_id.canonical,
            "market": result.security_id.market.value
            if hasattr(result.security_id.market, "value")
            else str(result.security_id.market),
            "capability": f"{result.domain}.{result.operation}",
            "consumer": consumer,
            "fetched_at": result.fetched_at,
            "duration_ms": int(duration_ms),
            "provider": result.provider,
            "source_trace": list(result.source_trace or []),
            "freshness": result.freshness,
            "quality_score": result.quality_score,
            "quality_tier": quality_tier,
            "success": not is_error and not result.is_empty(),
            "error_message": (
                "; ".join(result.warnings) if is_error else None
            ),
            "params": dict(params) if params else {},
            "quality_warnings": list(result.warnings or []),
        }


def _infer_tier_from_score(score: float | None) -> str | None:
    """根据 quality_score 推断 tier（与 scorer 阈值一致）。"""
    if score is None:
        return None
    if score >= 0.9:
        return "direct_use"
    if score >= 0.7:
        return "warning"
    if score >= 0.3:
        return "degrade"
    return "reject"


__all__ = ["AuditLogger"]