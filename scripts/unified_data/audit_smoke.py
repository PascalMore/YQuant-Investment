#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""audit_smoke.py — Unified Data Phase 2 audit smoke CLI。

DESIGN-03-011 §8.5（writer insert + reader precise find）+ Pascal 任务
t_188225f4 选择方案 A：本文件是新增的正式、可复用的 audit smoke CLI。

契约（来自任务卡 + DESIGN §8.5 + RFC/SPEC 不补不改）：

* 默认 dry-run / 无生产副作用：仅打印预期计划，不连接 MongoDB、不读取真实凭证。
* 真实 smoke 必须由显式 ``--apply`` 才执行。
* 仅使用 ``YQUANT_UD_AUDIT_WRITER_MONGO_*`` 与 ``YQUANT_UD_AUDIT_READER_MONGO_*``
  两组运行时凭证建立两个独立 client；不重用 DDL/root/业务身份。
* 目标硬编码：DB ``tradingagents``、collection ``03_data_ud_query_audit``；
  拒绝越界（QualitySummary、portfolio、Smart Money、交易、缓存）。
* ``--apply`` writer ``insert_one`` 一条最小、可识别、无业务敏感字段的 event；
  reader 必须用该 event 的精确 ``_id`` ``find_one`` 读回，并验证标识字段一致。
* 禁止 delete / update / replace / aggregate / 额外索引 / DDL / role / user 操作。
* event 必带 ``fetched_at`` UTC 时间（满足既有 TTL 索引）+ smoke 标识
  （``event_type`` / ``source``）；不含参数、账户、证券、业务数据、secret。
* 成功输出仅非敏感摘要（dry-run/apply、collection 常量、insert/read 成功、
  ObjectId 可显示）；任何失败 fail-closed 为非零退出码。
* ``--apply`` 路径下凭证加载由本模块自有的 ``_load_writer_credentials`` /
  ``_load_reader_credentials`` 实现（见下文 ``# Credential loaders``），从
  ``YQUANT_UD_AUDIT_WRITER_MONGO_*`` / ``YQUANT_UD_AUDIT_READER_MONGO_*`` 环境
  变量读取。该实现**未复用** ``audit_rollout`` 的 loader（``audit_rollout`` 实现了
  形态一致但作用域不同的 ``_load_runtime_writer_credentials`` /
  ``_load_runtime_reader_credentials``，本模块为保持零私有副作用耦合而自带实现，
  fail-fast / strip / 默认 auth_db='admin' 行为与 audit_rollout loader 对齐）。
  ``audit_rollout`` 的 apply/verify/CLI 契约完全不变。

退出码：

    0  成功（dry-run / apply）
    2  静态范围校验失败 / argparse 拒绝
    3  凭证缺失（fail-fast）
    4  apply 阶段运行时错误（writer insert 失败 / reader find_one 失败 /
       event 字段越界 / 越权调用 / 事件 _id 不一致）

DSA 安全约束：

* 任何函数都不打印 URI / username / password / token；createUser-style
  ``pwd`` 字段也不存在（smoke 不创建用户）。
* event 不含 secret / token / password / 业务字段；ObjectId 输出经 ``str()`` 序列化。
* 任何异常 traceback 不串联包含 secret 的底层异常对象。
* pymongo 触达点（client 打开 / insert_one / find_one）的异常一律在
  ``_write_then_read`` 内翻译为 ``WriterRuntimeError`` / ``ReaderRuntimeError`` ——
  消息固定且**不含 secret**；``run_apply`` 的兜底 ``except Exception`` 只输出
  ``{type(exc).__name__}`` + 固定脱敏短语，**绝不**打印 ``{exc}``。pymongo 的
  ``ServerSelectionTimeoutError`` / ``OperationFailure`` 等默认会把含
  user:password 的完整 URI 嵌进 ``str(exc)``，因此这一层兜底至关重要。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# 静态 allow-list（DESIGN §8.5.1, SPEC §8.2, RFC §8.4/§8.5）
# 与 audit_rollout 共用同一组常量定义；这里以独立常量实现以避免私有副作用耦合
# ---------------------------------------------------------------------------

ALLOWED_DATABASE: str = "tradingagents"
ALLOWED_COLLECTION: str = "03_data_ud_query_audit"

# Smoke 显式禁用任何 QualitySummary / portfolio / Smart Money / 交易 / 缓存 /
# Signal 等其它集合。设计 8.5 要求本工具**绝不**访问这些 collection。
FORBIDDEN_COLLECTIONS: frozenset[str] = frozenset({
    "03_data_ud_quality_summary",  # Phase 1 不启用
    "portfolio_position",
    "portfolio_trade",
    "smart_money_records",
    "smart_money_normalized",
    "trade_xyz",
    "signal_pool",
    "argus_signal",
    "cache_keys",
})

# Writer / reader 环境变量命名空间（DESIGN §8.5.2, SPEC §8.3）。
# 复用既有 12 键 YQUANT_UD_AUDIT_* 命名空间，不引入别名 / fallback。
WRITER_ENV_KEYS: tuple[str, ...] = (
    "YQUANT_UD_AUDIT_WRITER_MONGO_URI",
    "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME",
    "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
    "YQUANT_UD_AUDIT_WRITER_MONGO_AUTH_DB",
)
READER_ENV_KEYS: tuple[str, ...] = (
    "YQUANT_UD_AUDIT_READER_MONGO_URI",
    "YQUANT_UD_AUDIT_READER_MONGO_USERNAME",
    "YQUANT_UD_AUDIT_READER_MONGO_PASSWORD",
    "YQUANT_UD_AUDIT_READER_MONGO_AUTH_DB",
)

# Smoke event 必含字段（DESIGN §8.5 writer insert + reader precise find）。
SMOKE_EVENT_TYPE: str = "audit_smoke_round_trip"
SMOKE_EVENT_SOURCE: str = "audit_smoke_cli"

# Event 字段白名单：除了 fetched_at / event_type / source 之外，event 不应再
# 包含任何字段；此常量用于运行时断言插入文档字段严格属于本集合（fail-closed）。
ALLOWED_EVENT_FIELDS: frozenset[str] = frozenset({
    "_id",
    "event_type",
    "source",
    "fetched_at",
})


# ---------------------------------------------------------------------------
# 错误类
# ---------------------------------------------------------------------------


class SmokeError(Exception):
    """Smoke 阶段非预期的运行时错误（apply 失败 / verify 检测到不一致）。"""


class ScopeViolation(SmokeError):
    """目标不在 allow-list 内（fail-fast）。"""


class MissingCredentialError(SmokeError):
    """缺少 writer 或 reader 运行时凭证（fail-fast）。"""


class EventContractViolation(SmokeError):
    """Event 字段越界 / 缺标识字段 / 读回 _id 不一致（fail-closed）。"""


# 红色安全包装：任何 pymongo / 运行时异常一律翻译为下列子类，**消息固定且不含
# secret**（绝不把底层异常对象的 ``str()`` 拼进去——pymongo 默认会把含 user:password
# 的完整 URI 嵌进 ServerSelectionTimeoutError / OperationFailure 消息里）。
# ``run_apply`` 的外层 except 只会看到这些固定消息或 SmokeError 子类。
class WriterRuntimeError(SmokeError):
    """Writer 路径运行时异常（insert / client 打开）；详情见日志，不外泄 secret。"""


class ReaderRuntimeError(SmokeError):
    """Reader 路径运行时异常（find_one / client 打开）；详情见日志，不外泄 secret。"""


# ---------------------------------------------------------------------------
# 静态校验
# ---------------------------------------------------------------------------


def _validate_targets(database: str, collection: str) -> None:
    """校验 database / collection 在 allow-list 内；不在则 fail-closed。

    dry-run 与 apply 共享同一份静态校验（dry-run 可静态检查，但不连）。
    显式拒绝空字符串（防止 monkeypatch 或构造错误静默通过）。
    """
    if not isinstance(database, str) or not database:
        raise ScopeViolation(
            f"database {database!r} must be a non-empty string in allow-list "
            f"(only {ALLOWED_DATABASE!r})"
        )
    if database != ALLOWED_DATABASE:
        raise ScopeViolation(
            f"database {database!r} not in allow-list "
            f"(only {ALLOWED_DATABASE!r})"
        )
    if not isinstance(collection, str) or not collection:
        raise ScopeViolation(
            f"collection {collection!r} must be a non-empty string in allow-list "
            f"(only {ALLOWED_COLLECTION!r})"
        )
    if collection != ALLOWED_COLLECTION:
        raise ScopeViolation(
            f"collection {collection!r} not in allow-list "
            f"(only {ALLOWED_COLLECTION!r})"
        )
    if collection in FORBIDDEN_COLLECTIONS:
        raise ScopeViolation(
            f"collection {collection!r} is explicitly forbidden in Phase 1 "
            f"(see FORBIDDEN_COLLECTIONS)"
        )


def _validate_event_fields(event: dict[str, Any]) -> None:
    """校验 smoke event 字段严格属于 ``ALLOWED_EVENT_FIELDS``。

    任意业务字段（params / account / security_id / market / capability /
    provider / consumer / audit_id / secret 类）必须 fail-closed（DESIGN §8.5）。
    """
    if not isinstance(event, dict):
        raise EventContractViolation(
            f"smoke event must be a dict, got {type(event).__name__}"
        )
    extras = sorted(set(event) - ALLOWED_EVENT_FIELDS)
    if extras:
        raise EventContractViolation(
            f"smoke event must not contain fields outside "
            f"{sorted(ALLOWED_EVENT_FIELDS)} (forbidden={extras})"
        )
    for required in ("event_type", "source", "fetched_at"):
        if required not in event:
            raise EventContractViolation(
                f"smoke event missing required field {required!r}"
            )


# ---------------------------------------------------------------------------
# Event 构造（DESIGN §8.5：最小、可识别、含 fetched_at UTC）
# ---------------------------------------------------------------------------


def _build_smoke_event() -> dict[str, Any]:
    """构造一条最小 smoke event。

    字段严格限于 ``ALLOWED_EVENT_FIELDS``。``fetched_at`` 必须是 UTC
    ``datetime``（含 tzinfo）以满足既有 TTL 索引。

    标识字段 ``event_type`` / ``source`` 与 ``_id`` 在 ``_write_then_read``
    中再次断言一致（fail-closed）。
    """
    return {
        "event_type": SMOKE_EVENT_TYPE,
        "source": SMOKE_EVENT_SOURCE,
        "fetched_at": datetime.now(timezone.utc),
    }


# ---------------------------------------------------------------------------
# Credential loaders（DESIGN §8.5.2 / SPEC §8.3：runtime writer/reader 凭证隔离）
# ---------------------------------------------------------------------------


def _load_writer_credentials() -> dict[str, str]:
    """读取 runtime writer 凭证；缺失即 fail-fast（不返回部分字段）。"""
    creds = {
        "uri": os.environ.get(WRITER_ENV_KEYS[0], "").strip(),
        "username": os.environ.get(WRITER_ENV_KEYS[1], "").strip(),
        "password": os.environ.get(WRITER_ENV_KEYS[2], "").strip(),
        "auth_db": (
            os.environ.get(WRITER_ENV_KEYS[3], "admin").strip() or "admin"
        ),
    }
    missing = [
        k for k in WRITER_ENV_KEYS[:3]  # URI / USERNAME / PASSWORD 必需
        if not os.environ.get(k, "").strip()
    ]
    if missing:
        raise MissingCredentialError(
            f"missing runtime writer credentials: {', '.join(missing)}"
        )
    return creds


def _load_reader_credentials() -> dict[str, str]:
    """读取 runtime reader 凭证；缺失即 fail-fast。

    与 writer 凭证严格分离：reader 缺失不会让 writer 通过，反之亦然。
    """
    creds = {
        "uri": os.environ.get(READER_ENV_KEYS[0], "").strip(),
        "username": os.environ.get(READER_ENV_KEYS[1], "").strip(),
        "password": os.environ.get(READER_ENV_KEYS[2], "").strip(),
        "auth_db": (
            os.environ.get(READER_ENV_KEYS[3], "admin").strip() or "admin"
        ),
    }
    missing = [
        k for k in READER_ENV_KEYS[:3]
        if not os.environ.get(k, "").strip()
    ]
    if missing:
        raise MissingCredentialError(
            f"missing runtime reader credentials: {', '.join(missing)}"
        )
    return creds


# ---------------------------------------------------------------------------
# MongoDB 客户端（带隔离）
# ---------------------------------------------------------------------------


def _open_writer_client() -> Any:
    """打开独立的 writer client；不在脚本间共享；close 立即释放。

    与 reader client 严格独立（DESIGN §8.5.2）。
    """
    try:
        import pymongo  # local import: 缺 pymongo 时给出清晰错误
    except ImportError as exc:  # pragma: no cover - 实际环境已装
        raise SmokeError(f"pymongo is required: {exc}") from exc

    creds = _load_writer_credentials()
    return pymongo.MongoClient(
        creds["uri"],
        username=creds["username"],
        password=creds["password"],
        authSource=creds["auth_db"],
        # 短超时：smoke 操作不应该长时间挂起
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )


def _open_reader_client() -> Any:
    """打开独立的 reader client；与 writer client 物理隔离。"""
    try:
        import pymongo  # local import: 缺 pymongo 时给出清晰错误
    except ImportError as exc:  # pragma: no cover - 实际环境已装
        raise SmokeError(f"pymongo is required: {exc}") from exc

    creds = _load_reader_credentials()
    return pymongo.MongoClient(
        creds["uri"],
        username=creds["username"],
        password=creds["password"],
        authSource=creds["auth_db"],
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )


# ---------------------------------------------------------------------------
# 三大模式
# ---------------------------------------------------------------------------


def _describe_plan() -> list[str]:
    """打印人类可读的 smoke 执行计划（dry-run 专用）。"""
    lines: list[str] = []
    lines.append(
        f"Plan: writer user will insert_one a minimal event into "
        f"{ALLOWED_DATABASE!r}.{ALLOWED_COLLECTION!r}."
    )
    lines.append(
        f"Plan: reader user will find_one by exact _id returned by writer."
    )
    lines.append(
        f"Plan: event fields strictly limited to {sorted(ALLOWED_EVENT_FIELDS)} "
        f"(no business / secret fields)."
    )
    lines.append(
        "Plan: writer / reader use independent clients and credentials."
    )
    lines.append(
        "Plan: QualitySummary / portfolio / Smart Money / trade / signal / "
        "cache collections MUST NOT be touched."
    )
    return lines


def run_dry_run() -> int:
    """默认模式：只打印预期操作，零副作用（不连库、不读真凭证）。"""
    _validate_targets(ALLOWED_DATABASE, ALLOWED_COLLECTION)
    # 静态检查 event 字段契约：dry-run 期间 event 已构造出来但未写入
    _validate_event_fields(_build_smoke_event())

    print("[DRY-RUN] audit_smoke — no side effects will be performed.")
    for line in _describe_plan():
        print(f"  {line}")
    print("[DRY-RUN] done. Pass --apply to execute the real round-trip.")
    return 0


def _write_then_read() -> dict[str, Any]:
    """writer insert + reader find_one({_id}) 主路径；只允许 insert_one / find_one。

    安全契约：pymongo 异常（``ServerSelectionTimeoutError`` / ``OperationFailure``
    等）默认把含 user:password 的完整 URI 嵌入 ``str(exc)`` 中。本函数把所有
    pymongo 触达点（writer / reader client 打开、insert_one、find_one）的异常
    翻译为 ``WriterRuntimeError`` / ``ReaderRuntimeError`` —— 消息固定且**不含
    secret**，绝不调用 ``str(exc)``。这样 ``run_apply`` 的外层 except 即使兜底，
    也无法外泄 URI / 密码。

    Returns:
        ``{"inserted_id": ObjectId, "fetched_doc": dict}`` — 含 ``_id``。

    Raises:
        SmokeError / EventContractViolation / WriterRuntimeError /
        ReaderRuntimeError — 全部 fail-closed。
    """
    # 静态校验：越界直接 fail-closed
    _validate_targets(ALLOWED_DATABASE, ALLOWED_COLLECTION)

    event = _build_smoke_event()
    _validate_event_fields(event)

    # 安全打开 writer client：构造异常可能含 URI
    try:
        writer_client = _open_writer_client()
    except SmokeError:
        raise
    except Exception:
        raise WriterRuntimeError("writer client open failed (see logs without secrets)")
    # 安全打开 reader client
    try:
        reader_client = _open_reader_client()
    except SmokeError:
        raise
    except Exception:
        raise ReaderRuntimeError("reader client open failed (see logs without secrets)")
    try:
        writer_db = writer_client[ALLOWED_DATABASE]
        reader_db = reader_client[ALLOWED_DATABASE]
        writer_coll = writer_db[ALLOWED_COLLECTION]
        reader_coll = reader_db[ALLOWED_COLLECTION]

        # Writer insert_one — 仅允许此调用；异常一律包装（绝不透传 pymongo str(exc)）
        try:
            insert_result = writer_coll.insert_one(event)
        except Exception:
            raise WriterRuntimeError("writer insert failed (see logs without secrets)")
        inserted_id = insert_result.inserted_id

        # Reader find_one 必须用 _id 精确查询（fail-closed on mismatch）
        try:
            fetched_doc = reader_coll.find_one({"_id": inserted_id})
        except Exception:
            raise ReaderRuntimeError("reader find_one failed (see logs without secrets)")
        if fetched_doc is None:
            raise SmokeError(
                "reader find_one returned None for writer-inserted _id"
            )

        # 标识字段与 _id 一致：smoke 标记用于人工/自动定位
        # 注：_id 是 ObjectId，不含 event_type/source；这里校验的是插入的 doc
        # 与 _id 字典映射一致（实际为 fetched_doc 自身字段）。
        for marker_key in ("event_type", "source"):
            marker_value = fetched_doc.get(marker_key)
            if marker_value != event[marker_key]:
                raise EventContractViolation(
                    f"smoke marker {marker_key!r} mismatch: "
                    f"inserted={event[marker_key]!r}, fetched={marker_value!r}"
                )

        # Reader 返回 doc 必须仍在 ALLOWED_EVENT_FIELDS 内（防越权写入扩散）
        fetched_extras = sorted(set(fetched_doc) - ALLOWED_EVENT_FIELDS)
        if fetched_extras:
            raise EventContractViolation(
                f"reader fetched doc has fields outside "
                f"{sorted(ALLOWED_EVENT_FIELDS)} (forbidden={fetched_extras})"
            )

        return {"inserted_id": inserted_id, "fetched_doc": fetched_doc}
    finally:
        writer_client.close()
        reader_client.close()


def run_apply() -> int:
    """执行 smoke：writer insert + reader find_one({_id})；任一失败 fail-closed。

    返回值（直接被 main() 调用或单元测试断言）：

    * 0 — 成功
    * 2 — 静态范围校验失败（ScopeViolation）
    * 3 — 凭证缺失（MissingCredentialError）
    * 4 — event 字段越界 / 运行时异常 / _id 不一致
    """
    _validate_targets(ALLOWED_DATABASE, ALLOWED_COLLECTION)

    try:
        result = _write_then_read()
    except ScopeViolation as exc:
        # ScopeViolation 消息仅含静态白名单常量 / 入参 db/coll 名（均为脚本内常量），
        # 不含 secret；保留详情以辅助排查。
        print(f"[APPLY] BLOCKED: {exc}", file=sys.stderr)
        return 2
    except MissingCredentialError as exc:
        # MissingCredentialError 消息只列出缺失的环境变量名（不含值），不外泄 secret。
        print(f"[APPLY] missing credentials: {exc}", file=sys.stderr)
        return 3
    except EventContractViolation as exc:
        # EventContractViolation 消息只含字段名 / smoke marker（不含 secret）。
        print(f"[APPLY] BLOCKED: {exc}", file=sys.stderr)
        return 4
    except (WriterRuntimeError, ReaderRuntimeError) as exc:
        # 已包装的 pymongo 运行时异常：消息固定且**不含 secret**。
        # 类型名（=非敏感分类，如 WriterRuntimeError）显式打印，保留分类。
        print(f"[APPLY] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        # 兜底：任何未被上游翻译的异常一律只输出**类型名 + 固定脱敏短语**，
        # 绝不打印 ``{exc}`` —— pymongo 异常的 ``str()`` 默认会把含 user:password
        # 的完整 URI 嵌进消息里（HIGH 安全风险，见审查 FINDING-1）。
        # 类型名本身不含 secret（仅类名，如 OperationFailure）。
        print(
            f"[APPLY] {type(exc).__name__}: internal error "
            f"(details suppressed to avoid leaking credentials; see logs)",
            file=sys.stderr,
        )
        return 4

    inserted_id = result["inserted_id"]
    print(
        f"[APPLY] OK: writer inserted event into "
        f"{ALLOWED_DATABASE!r}.{ALLOWED_COLLECTION!r}; "
        f"reader find_one by exact _id returned matching document; "
        f"ObjectId={str(inserted_id)}"
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit_smoke",
        description=(
            "Phase 2 Audit-only smoke CLI。默认 dry-run；仅在 Pascal 显式"
            "授权后 --apply。仅写入 tradingagents.03_data_ud_query_audit，"
            "writer / reader 凭证严格分离；事件字段严格受限于 {event_type, "
            "source, fetched_at, _id}。"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行 writer insert + reader find_one round-trip；不传时默认 dry-run。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.apply:
            return run_apply()
        return run_dry_run()
    except ScopeViolation as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 2
    except MissingCredentialError as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 3
    except EventContractViolation as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
