"""Audit 子包 — Phase 2 审计日志。

DESIGN-03-011 / SPEC-03-011 范围：追加式审计；mongo_db=None → noop。

Phase 2 提供的公共符号：

* :class:`AuditLogger` — 审计日志写入器（catch-and-log）
* :data:`ALLOWED_PARAM_KEYS` — params 字段 allow-list 集合
"""

from .logger import ALLOWED_PARAM_KEYS, AuditLogger, sanitize_params

__all__ = ["AuditLogger", "ALLOWED_PARAM_KEYS", "sanitize_params"]