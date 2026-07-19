"""AuditLogger — Phase 2 查询审计日志（DESIGN-03-011 §5, SPEC-03-011 §6）。

追加式审计写入器。``mongo_db=None`` 时为 noop；写入采用 catch-and-log，
不向调用方抛出异常。绝不自行建立连接或创建索引（DDL 留待 Pascal
生产确认后由独立脚本执行）。

``params`` 字段使用严格 allow-list（DESIGN §8.6 已确认白名单策略）：
仅记录 query 语义字段，未知键与命中敏感 deny-list 的键一律丢弃，
绝不写入审计文档。TTL 默认 365 天（DESIGN §5.3, §8.2 已确认）。

Phase 1 Audit-only：QualitySummary 不可注入。``__init__`` 不接受
``quality_summary`` 参数（SPEC-03-011 §11.3 QS-F2）；任何尝试注入
QualitySummary 的行为将导致 ``TypeError``。``log()`` 内无 QualitySummary
调用，确保 QualitySummary 不可达（QS-F3）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from ..models import DataResult

logger = logging.getLogger(__name__)

# Pascal 已确认的 params allow-list（DESIGN-03-011 §8.6, RFC §12, SPEC §7）：
# 仅记录 query 语义字段；凭据、令牌、连接串、账号等一律丢弃。
ALLOWED_PARAM_KEYS: frozenset[str] = frozenset({
    "security_id",
    "market",
    "domain",
    "operation",
    "start_date",
    "end_date",
    "limit",
    "frequency",
    "provider",
    "consumer",
    "force_refresh",
})

# 防御性敏感键 deny-list：即使未来误将某个 allow-list 之外的键传进来，
# 命中此集合的键也必须丢弃。匹配大小写不敏感、子串匹配。
_DENY_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "password",
    "secret",
    "authorization",
    "cookie",
    "apikey",
    "api_key",
)

# 防御性敏感值 deny-list：即便键名是允许的语义字段，若其值含连接串 /
# 凭据 / Authorization 头，仍必须丢弃。匹配大小写不敏感、子串匹配。
_DENY_VALUE_SUBSTRINGS: tuple[str, ...] = (
    "mongodb://",
    "mongodb+srv://",
    "bearer ",
)


def _sanitize_params(params: dict | None) -> dict:
    """仅保留 allow-list 中的键；命中 deny-list 子串的键直接丢弃。

    返回新 dict，不修改入参；非 dict 输入视为空 dict。
    """
    if not params or not isinstance(params, dict):
        return {}
    safe: dict = {}
    for key, value in params.items():
        if not isinstance(key, str):
            continue
        key_lower = key.lower()
        # 1. allow-list 之外直接丢弃
        if key not in ALLOWED_PARAM_KEYS:
            logger.debug("AuditLogger: dropping non-allow-listed param %r", key)
            continue
        # 2. allow-list 内但键名命中 deny-list 子串仍丢弃（防御纵深）
        if any(deny in key_lower for deny in _DENY_SUBSTRINGS):
            logger.warning(
                "AuditLogger: dropping suspicious allow-listed param %r "
                "(key matches deny-list substring)",
                key,
            )
            continue
        # 3. 键名合法但值含连接串 / Bearer 头等凭据信号也丢弃
        if isinstance(value, str):
            value_lower = value.lower()
            if any(deny in value_lower for deny in _DENY_VALUE_SUBSTRINGS):
                logger.warning(
                    "AuditLogger: dropping allow-listed param %r "
                    "whose value contains sensitive substring",
                    key,
                )
                continue
        safe[key] = value
    return safe


# 公共别名：方便外部测试与审计脚本直接引用。
sanitize_params = _sanitize_params


class AuditLogger:
    """追加式查询审计日志组件。

    Args:
        mongo_db: MongoDB 数据库句柄。``None`` 时进入 noop 模式，所有
            :meth:`log` 调用直接返回，不写入任何数据。
        collection_name: 审计集合名（默认 ``03_data_ud_query_audit``）。
        ttl_days: TTL 过期天数（默认 365 天，DESIGN §5.3 Pascal 已确认）。
            本组件不创建 TTL 索引，仅供将来 Pascal 确认后由独立迁移
            脚本使用。
        Phase 1 Audit-only：不接受 quality_summary 参数（SPEC §11.3 QS-F2）。
    """

    def __init__(
        self,
        mongo_db: Any = None,
        collection_name: str = "03_data_ud_query_audit",
        ttl_days: int = 365,
    ) -> None:
        self._mongo_db = mongo_db
        self._collection_name = collection_name
        self._ttl_days = ttl_days

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
            "params": _sanitize_params(params),
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


__all__ = ["AuditLogger", "ALLOWED_PARAM_KEYS", "sanitize_params"]