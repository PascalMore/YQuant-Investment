#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_rollout.py — Unified Data Phase 2 Audit-only 受控 DDL 工具。

DESIGN-03-011 §8.5 / §8.8 / §8.9 / §14，SPEC-03-011 §8，RFC-03-011 §8 —
Pascal 已确认的 Phase 2 Audit-only production rollout 脚本。本脚本仅在 Pascal
显式授权后执行；默认 dry-run，零副作用。

本文件已被 Remediation Implement 阶段（task t_445911bf）按 reviewer
t_c051239d REVISE 意见完整重写。新增要点：

* 正式身份名称常量 ``WRITER_ROLE_NAME`` / ``READER_ROLE_NAME`` /
  ``WRITER_USER_NAME`` / ``READER_USER_NAME`` —— 一律以 ``yquant_ud_audit_``
  开头，DDL 脚本拒绝任何不一致命名（fail-fast）。
* 模块级 ``ALLOWED_PARAMS`` 白名单常量（DESIGN §8.6, RFC §A4）—— Implement
  阶段固化具体键列表，初始化后不可变。脚本本身不使用（审计写入由
  AuditLogger 负责），但按 RFC/SPEC/DESIGN 要求在此模块显式导出。
* ``_ensure_write_role`` / ``_ensure_read_role`` / ``_ensure_write_user``
  / ``_ensure_read_user`` —— 幂等创建/校验 role 与 user，对已存在的
  role/user 做**精确** privileges / role-binding 比对，任何不匹配一律
  fail-fast（DESIGN §8.9.3 退出码 4；reviewer REVISE issue 3）。
* ``run_apply`` 现在做：collection（仅 audit）→ 3 indexes（TTL=31536000 +
  两个二级索引，逐条精确比对，缺失或定义不符 fail-fast；reviewer REVISE
  issue 7）→ 2 roles → 2 users。``QualitySummary`` 集合**全程不创建**。
* 移除 ``--writer-role`` / ``--reader-role`` CLI 参数 —— 它们在 apply 模式下
  实际无效，改为模块级不可变常量；reviewer REVISE issue 6。
* ``--verify`` 现在做完整 DDL 结果验证（collection + 3 indexes + 2 roles +
  2 users + 无 QualitySummary），仍然是只读路径；reviewer REVISE issue 9。
* 运行时 writer/reader 凭证读取函数 ``_load_runtime_writer_credentials`` /
  ``_load_runtime_reader_credentials`` —— 仅用于 verify 模式下的可选
  round-trip smoke 校验；环境变量缺失明确 fail-fast，绝不打 URI / password。
  reviewer REVISE issue 8 闭环要求。
* 全程不直接以 DDL bootstrap 身份执行 runtime 写入；DDL 身份与 runtime
  writer/reader 严格分离（DESIGN §8.5.2 §"禁止复用规则"）。

退出码：

    0  成功（dry-run / verify / apply）
    1  验证失败（verify 路径：collection/index/role/user 不符合契约）
    2  静态范围校验失败（database / collection / role / user 不在 allow-list）
    3  凭证缺失（fail-fast）
    4  apply 阶段运行时错误（pymongo 抛出或已存在 role/user 的 privileges
       / binding 与契约不一致，fail-closed）

DSA 安全约束：

* 任何函数都不打印 URI / username / password / token；createUser 失败仅输出
  异常类型等结构性字段，不串联可能包含 secret 的底层异常 traceback/context。
* ``_load_*_credentials`` 不会持久化任何凭证，也不会出现在输出中
  （仅返回字典引用；调用方负责不向日志写入）。
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# 静态 allow-list 与正式命名（DESIGN §8.5.1, SPEC §8.2, RFC §8.4/§8.5）
# ---------------------------------------------------------------------------

ALLOWED_DATABASE: str = "tradingagents"
ALLOWED_COLLECTION: str = "03_data_ud_query_audit"
FORBIDDEN_COLLECTIONS: frozenset[str] = frozenset({
    "03_data_ud_quality_summary",  # Phase 1 不启用（DESIGN §6, SPEC §8.6）
})

# 索引设计：TTL (fetched_at, expireAfterSeconds=31536000) + 两个二级索引
TTL_SECONDS: int = 365 * 24 * 3600  # 365 天，DESIGN §5.3 / §14.1 Pascal 已确认

# 索引元组： (name, keys, options)。opts["name"] 固定为索引名，createIndex 时
# 同时透传 keys 与 options。Implement Remediation 阶段对每个索引执行
# "逐字段精确比对"，与 verify 路径一致（reviewer REVISE issue 7）。
INDEX_SPECS: list[tuple[str, list[tuple[str, int]], dict[str, Any]]] = [
    (
        "fetched_at_ttl",
        [("fetched_at", 1)],
        {"expireAfterSeconds": TTL_SECONDS, "name": "fetched_at_ttl"},
    ),
    (
        "security_id_fetched_at",
        [("security_id", 1), ("fetched_at", -1)],
        {"name": "security_id_fetched_at"},
    ),
    (
        "capability_fetched_at",
        [("capability", 1), ("fetched_at", -1)],
        {"name": "capability_fetched_at"},
    ),
]

# 正式身份名称（DESIGN §8.5.1, SPEC §8.2）。所有模块内部逻辑、CLI 输出、
# 单元测试断言都引用这四个常量，**不通过 CLI 参数覆盖**。任何不一致命名
# （包括 ``ud_audit_*`` / ``portfolio_admin`` 等）一律被本模块拒绝。
WRITER_ROLE_NAME: str = "yquant_ud_audit_writer_role"
READER_ROLE_NAME: str = "yquant_ud_audit_reader_role"
WRITER_USER_NAME: str = "yquant_ud_audit_writer_user"
READER_USER_NAME: str = "yquant_ud_audit_reader_user"

# 角色 / 用户完整 allow-list。run_apply / run_verify / dry-run 都用同一份
# 集合做"精确等于"校验（reviewer REVISE issue 6）。
ALLOWED_IDENTITY_NAMES: frozenset[str] = frozenset({
    WRITER_ROLE_NAME,
    READER_ROLE_NAME,
    WRITER_USER_NAME,
    READER_USER_NAME,
})

# Writer / reader role 的精确 privileges（DESIGN §14.1 A3 验收要求）。
# 不允许 anyOtherActions / cluster-wide / db-wide / 其它 collection：
# _ensure_role 通过精确比对验证（reviewer REVISE issue 3）。
WRITER_ROLE_PRIVILEGES: list[dict[str, Any]] = [
    {
        "resource": {"db": ALLOWED_DATABASE, "collection": ALLOWED_COLLECTION},
        "actions": ["insert"],
    },
]
READER_ROLE_PRIVILEGES: list[dict[str, Any]] = [
    {
        "resource": {"db": ALLOWED_DATABASE, "collection": ALLOWED_COLLECTION},
        "actions": ["find"],
    },
]
WRITER_ROLE_ROLES: list[dict[str, Any]] = []  # 不继承任何其它 role
READER_ROLE_ROLES: list[dict[str, Any]] = []  # 不继承任何其它 role

# 模块级 params 白名单唯一命名空间（DESIGN §8.6, SPEC §8.4, RFC §8.4）。
# 与 AuditLogger 已生效 allow-list 保持同一组 11 个查询语义键；不引入 alias、
# fallback 或第二套键集合。
ALLOWED_PARAMS: frozenset[str] = frozenset({
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


# ---------------------------------------------------------------------------
# 错误类
# ---------------------------------------------------------------------------


class RolloutError(Exception):
    """Rollout 阶段非预期的运行时错误（apply 失败 / verify 检测到不一致）。"""


class ScopeViolation(RolloutError):
    """目标不在 allow-list 内（fail-fast；reviewer REVISE issue 3）。"""


class MissingCredentialError(RolloutError):
    """缺少 DDL bootstrap 或 createUser 所需 runtime 密码（fail-fast）。"""


class IdentityPrivilegeMismatch(RolloutError):
    """已存在的 role / user 与契约不一致（fail-closed；reviewer REVISE issue 3）。"""


# ---------------------------------------------------------------------------
# 静态校验
# ---------------------------------------------------------------------------


def _validate_targets(database: str, collection: str) -> None:
    """校验 database / collection 在 allow-list 内；不在则 fail-closed。"""
    if database != ALLOWED_DATABASE:
        raise ScopeViolation(
            f"database {database!r} not in allow-list "
            f"(only {ALLOWED_DATABASE!r})"
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


def _validate_identity_name(name: str, *, kind: str) -> None:
    """校验 role/user 名称精确等于 ALLOWED_IDENTITY_NAMES 中的常量。

    拒绝任何"前缀匹配"以外的写法：``ud_audit_*`` / ``portfolio_*`` /
    ``smart_money_*`` / ``signal_*`` / ``trade_*`` / ``cache_*`` 等
    broad business identity 一律 fail-fast（reviewer REVISE issue 5/6）。
    """
    if not isinstance(name, str):
        raise ScopeViolation(
            f"{kind} name must be a string, got {type(name).__name__}"
        )
    if name not in ALLOWED_IDENTITY_NAMES:
        raise ScopeViolation(
            f"{kind} name {name!r} not in ALLOWED_IDENTITY_NAMES "
            f"(must be one of {sorted(ALLOWED_IDENTITY_NAMES)})"
        )


def _load_ddl_credentials() -> dict[str, str]:
    """从显式环境变量读取 DDL bootstrap 凭证；缺失即 fail-fast。

    禁止打印、记录或持久化任何凭证字段。DDL bootstrap 凭证与 runtime
    writer/reader 凭证严格分离（DESIGN §8.5.2）。
    """
    uri = os.environ.get("YQUANT_UD_AUDIT_DDL_MONGO_URI", "").strip()
    user = os.environ.get("YQUANT_UD_AUDIT_DDL_MONGO_USERNAME", "").strip()
    password = os.environ.get("YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD", "").strip()
    auth_db = (
        os.environ.get("YQUANT_UD_AUDIT_DDL_MONGO_AUTH_DB", "admin").strip() or "admin"
    )

    missing: list[str] = []
    if not uri:
        missing.append("YQUANT_UD_AUDIT_DDL_MONGO_URI")
    if not user:
        missing.append("YQUANT_UD_AUDIT_DDL_MONGO_USERNAME")
    if not password:
        missing.append("YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD")
    if missing:
        raise MissingCredentialError(
            f"missing DDL bootstrap credentials: {', '.join(missing)}"
        )

    return {
        "uri": uri,
        "username": user,
        "password": password,
        "auth_db": auth_db,
    }


def _load_runtime_writer_credentials() -> dict[str, str]:
    """读取 runtime writer 凭证（DESIGN §8.5.2, SPEC §8.3）。

    用于 verify 路径下的"模拟 writer 写入" round-trip smoke。缺失即
    fail-fast；强制项 vs 可选项与 SPEC §8.3 一致（URI/USERNAME/PASSWORD
    全部 required；AUTH_DB 默认 admin）。
    """
    uri = os.environ.get("YQUANT_UD_AUDIT_WRITER_MONGO_URI", "").strip()
    user = os.environ.get("YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME", "").strip()
    password = os.environ.get("YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD", "").strip()
    auth_db = (
        os.environ.get("YQUANT_UD_AUDIT_WRITER_MONGO_AUTH_DB", "admin").strip()
        or "admin"
    )

    missing: list[str] = []
    if not uri:
        missing.append("YQUANT_UD_AUDIT_WRITER_MONGO_URI")
    if not user:
        missing.append("YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME")
    if not password:
        missing.append("YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD")
    if missing:
        raise MissingCredentialError(
            f"missing runtime writer credentials: {', '.join(missing)}"
        )

    return {
        "uri": uri,
        "username": user,
        "password": password,
        "auth_db": auth_db,
    }


def _load_runtime_reader_credentials() -> dict[str, str]:
    """读取 runtime reader 凭证（DESIGN §8.5.2, SPEC §8.3）。

    Phase 1 不创建 reader，但契约要求本模块也能加载凭证以备将来启用。
    """
    uri = os.environ.get("YQUANT_UD_AUDIT_READER_MONGO_URI", "").strip()
    user = os.environ.get("YQUANT_UD_AUDIT_READER_MONGO_USERNAME", "").strip()
    password = os.environ.get("YQUANT_UD_AUDIT_READER_MONGO_PASSWORD", "").strip()
    auth_db = (
        os.environ.get("YQUANT_UD_AUDIT_READER_MONGO_AUTH_DB", "admin").strip()
        or "admin"
    )

    missing: list[str] = []
    if not uri:
        missing.append("YQUANT_UD_AUDIT_READER_MONGO_URI")
    if not user:
        missing.append("YQUANT_UD_AUDIT_READER_MONGO_USERNAME")
    if not password:
        missing.append("YQUANT_UD_AUDIT_READER_MONGO_PASSWORD")
    if missing:
        raise MissingCredentialError(
            f"missing runtime reader credentials: {', '.join(missing)}"
        )

    return {
        "uri": uri,
        "username": user,
        "password": password,
        "auth_db": auth_db,
    }


# ---------------------------------------------------------------------------
# MongoDB 客户端（带隔离）
# ---------------------------------------------------------------------------


def _open_ddl_client() -> Any:
    """打开独立的 DDL bootstrap 连接；不在脚本间共享；close 立即释放。

    不缓存、不写入日志；本脚本用完即销毁。
    """
    try:
        import pymongo  # local import: 缺 pymongo 时给出清晰错误
    except ImportError as exc:  # pragma: no cover - 实际环境已装
        raise RolloutError(f"pymongo is required: {exc}") from exc

    creds = _load_ddl_credentials()
    client = pymongo.MongoClient(
        creds["uri"],
        username=creds["username"],
        password=creds["password"],
        authSource=creds["auth_db"],
        # 短超时：DDL 操作不应该长时间挂起
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    return client


# ---------------------------------------------------------------------------
# Role / User 创建与校验（DESIGN §8.9.2, RFC §A1-A5）
# ---------------------------------------------------------------------------


def _role_privileges_match(actual: Any, expected: list[dict[str, Any]]) -> bool:
    """精确比对 role privileges。

    pymongo ``db.command({"rolesInfo": name})`` 返回的 ``roles`` 字段里
    ``inheritedPrivileges`` / ``privileges`` 都是 list[dict]，每条形如
    ``{"resource": {...}, "actions": [...]}``。本函数做：
    - list 长度一致；
    - 每条 ``resource`` 字典完全一致；
    - 每条 ``actions`` list 集合一致（顺序不重要，因 MongoDB 不保证）。
    """
    if not isinstance(actual, list):
        return False
    if len(actual) != len(expected):
        return False

    def _sort_key(p: Any) -> tuple[str, str]:
        if not isinstance(p, dict):
            return ("", "")
        res = p.get("resource") or {}
        if not isinstance(res, dict):
            return ("", "")
        return (
            str(res.get("db", "")),
            str(res.get("collection", "")),
        )

    actual_sorted = sorted(actual, key=_sort_key)
    expected_sorted = sorted(expected, key=_sort_key)
    for got, want in zip(actual_sorted, expected_sorted):
        if got.get("resource") != want.get("resource"):
            return False
        if set(got.get("actions", [])) != set(want.get("actions", [])):
            return False
    return True


def _role_inherited_roles_match(actual: Any, expected: list[dict[str, Any]]) -> bool:
    """精确比对 role 继承的 roles 列表。

    Phase 1 禁止继承任何其它 role；非空 list 一律 fail-fast。
    """

    def _key(item: Any) -> str:
        if isinstance(item, dict):
            return f"{item.get('role', '')}@{item.get('db', '')}"
        return str(item)

    return sorted(actual or [], key=_key) == sorted(expected, key=_key)


def _ensure_role(
    db: Any,
    *,
    role_name: str,
    privileges: list[dict[str, Any]],
    roles: list[dict[str, Any]],
) -> str:
    """幂等创建/校验 custom role；任何不一致 fail-closed。

    Returns:
        ``"created"`` / ``"unchanged"`` —— 仅用于诊断打印。
    """
    _validate_identity_name(role_name, kind="role")

    cmd = {
        "createRole": role_name,
        "privileges": privileges,
        "roles": roles,
    }
    try:
        db.command(cmd)
        return "created"
    except Exception as exc:  # 包括 pymongo.errors.DuplicateKey / OperationFailure
        # MongoDB 抛 DuplicateKey（code 11000）或 NamespaceExists；mongomock 抛
        # OperationFailure(code=51024)。统一吞掉这类"已存在"信号再做精确校验。
        msg = str(exc).lower()
        is_existing = (
            "already exists" in msg
            or "duplicate" in msg
            or "code: 51024" in msg
            or "code: 11000" in msg
        )
        if not is_existing:
            raise RolloutError(
                f"createRole({role_name!r}) failed: {type(exc).__name__}: {exc}"
            ) from exc

    # 已存在 → 精确 privileges / roles 比对。任一不一致立即 fail-closed
    # （DESIGN §8.9.3 退出码 4；reviewer REVISE issue 3：必须硬失败，不得
    # 仅 warning 静默继续）。
    info = db.command({"rolesInfo": role_name, "showPrivileges": True})
    roles_block = info.get("roles") or []
    if not roles_block:
        raise IdentityPrivilegeMismatch(
            f"role {role_name!r} reports empty info block"
        )
    role_info = roles_block[0]
    if not _role_privileges_match(role_info.get("privileges"), privileges):
        raise IdentityPrivilegeMismatch(
            f"role {role_name!r} privileges do not match expected contract "
            f"(expected={privileges}, got={role_info.get('privileges')})"
        )
    if not _role_inherited_roles_match(role_info.get("roles"), roles):
        raise IdentityPrivilegeMismatch(
            f"role {role_name!r} inherited roles do not match expected "
            f"(expected={roles}, got={role_info.get('roles')})"
        )
    return "unchanged"


def _user_role_key(item: Any) -> str:
    """为 user role binding 生成稳定比较键。"""
    if isinstance(item, dict):
        return f"{item.get('role', '')}@{item.get('db', '')}"
    return str(item)


def _existing_user_info(
    db: Any,
    *,
    user_name: str,
    roles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """经当前 DDL bootstrap 连接只读预检 user，并校验已有 binding。"""
    info = db.command({"usersInfo": user_name, "showPrivileges": False})
    users_block = info.get("users") or []
    if not users_block:
        return None

    user_info = users_block[0]
    actual_roles = sorted(user_info.get("roles") or [], key=_user_role_key)
    expected_roles = sorted(roles, key=_user_role_key)
    if actual_roles != expected_roles:
        raise IdentityPrivilegeMismatch(
            f"user {user_name!r} role binding does not match expected "
            f"(expected={expected_roles}, got={actual_roles})"
        )
    return user_info


def _ensure_user(
    db: Any,
    *,
    user_name: str,
    roles: list[dict[str, Any]],
    password_env_var: str,
) -> str:
    """幂等创建/校验 custom user；createUser 初始密码按需读取。

    先经 DDL bootstrap identity 的现有连接执行只读 ``usersInfo``。用户已
    存在时只精确校验 role binding，不读取、轮换或重设密码。仅当用户不存在
    时才读取 ``password_env_var``；缺失或空值在任何 createUser 写 DDL 前抛
    ``MissingCredentialError``。密码仅作为单条 createUser 命令的 ``pwd`` 值，
    不打印、返回或持久化。

    Returns:
        ``"created"`` / ``"unchanged"`` —— 仅用于诊断打印。
    """
    _validate_identity_name(user_name, kind="user")

    if _existing_user_info(db, user_name=user_name, roles=roles) is not None:
        return "unchanged"

    password = os.environ.get(password_env_var, "").strip()
    if not password:
        raise MissingCredentialError(
            f"missing createUser credential: {password_env_var}"
        )

    error_type: str | None = None
    try:
        db.command({
            "createUser": user_name,
            "pwd": password,
            "roles": roles,
        })
    except Exception as exc:
        error_type = type(exc).__name__
        del exc

    # 不让 password 或底层异常对象进入本函数抛出的异常 traceback/context。
    del password
    if error_type is not None:
        raise RolloutError(
            f"createUser({user_name!r}) failed: {error_type}"
        )
    return "created"


def _preflight_runtime_users(db: Any) -> None:
    """在任何写 DDL 前只读校验 users，并为缺失 user 验证 createUser 密码。"""
    targets = (
        (
            WRITER_USER_NAME,
            [{"role": WRITER_ROLE_NAME, "db": ALLOWED_DATABASE}],
            "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
        ),
        (
            READER_USER_NAME,
            [{"role": READER_ROLE_NAME, "db": ALLOWED_DATABASE}],
            "YQUANT_UD_AUDIT_READER_MONGO_PASSWORD",
        ),
    )
    for user_name, roles, password_env_var in targets:
        if _existing_user_info(db, user_name=user_name, roles=roles) is not None:
            continue
        if not os.environ.get(password_env_var, "").strip():
            raise MissingCredentialError(
                f"missing createUser credential: {password_env_var}"
            )


def _ensure_write_role(db: Any) -> str:
    """创建或校验 writer role：对 03_data_ud_query_audit 的 insert-only 权限。"""
    return _ensure_role(
        db,
        role_name=WRITER_ROLE_NAME,
        privileges=WRITER_ROLE_PRIVILEGES,
        roles=WRITER_ROLE_ROLES,
    )


def _ensure_read_role(db: Any) -> str:
    """创建或校验 reader role：对 03_data_ud_query_audit 的 find-only 权限。"""
    return _ensure_role(
        db,
        role_name=READER_ROLE_NAME,
        privileges=READER_ROLE_PRIVILEGES,
        roles=READER_ROLE_ROLES,
    )


def _ensure_write_user(db: Any) -> str:
    """创建或校验 writer user：授予 WRITER_ROLE_NAME。"""
    return _ensure_user(
        db,
        user_name=WRITER_USER_NAME,
        roles=[{"role": WRITER_ROLE_NAME, "db": ALLOWED_DATABASE}],
        password_env_var="YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
    )


def _ensure_read_user(db: Any) -> str:
    """创建或校验 reader user：授予 READER_ROLE_NAME。"""
    return _ensure_user(
        db,
        user_name=READER_USER_NAME,
        roles=[{"role": READER_ROLE_NAME, "db": ALLOWED_DATABASE}],
        password_env_var="YQUANT_UD_AUDIT_READER_MONGO_PASSWORD",
    )


# ---------------------------------------------------------------------------
# Index 精确比对（reviewer REVISE issue 7）
# ---------------------------------------------------------------------------


def _index_matches(actual: dict[str, Any], keys: list[tuple[str, int]], opts: dict[str, Any]) -> bool:
    """精确比对单个 index 的 keys 与 options。

    顺序敏感（MongoDB index key 是有序的），TTL expireAfterSeconds 必须
    完全等于 TTL_SECONDS（31536000）。
    """
    actual_key = list((actual.get("key") or {}).items())
    if actual_key != list(keys):
        return False
    # name 必须一致
    if actual.get("name") != opts.get("name"):
        return False
    # TTL 比对
    target_ttl = opts.get("expireAfterSeconds")
    actual_ttl = actual.get("expireAfterSeconds")
    if target_ttl is not None and actual_ttl != target_ttl:
        return False
    if target_ttl is None and actual_ttl is not None:
        return False
    return True


def _ensure_indexes(db: Any, collection: str) -> dict[str, list[str]]:
    """幂等创建 3 个索引；与 verify 路径使用同一份 INDEX_SPECS 做精确比对。

    Returns:
        dict with ``created`` / ``skipped`` / ``mismatched`` 列表。
    """
    coll = db[collection]
    existing = {idx["name"]: idx for idx in coll.list_indexes()}

    created: list[str] = []
    skipped: list[str] = []
    mismatched: list[str] = []
    for name, keys, opts in INDEX_SPECS:
        cur = existing.get(name)
        if cur is None:
            coll.create_index(list(keys), **opts)
            created.append(name)
            continue
        if _index_matches(cur, keys, opts):
            skipped.append(name)
        else:
            mismatched.append(name)
    return {"created": created, "skipped": skipped, "mismatched": mismatched}


# ---------------------------------------------------------------------------
# 三大模式
# ---------------------------------------------------------------------------


def _describe_plan() -> list[str]:
    """打印人类可读的执行计划（dry-run 与 --verify 都使用）。"""
    lines: list[str] = []
    lines.append(
        f"Plan: ensure collection {ALLOWED_DATABASE!r}.{ALLOWED_COLLECTION!r} "
        f"exists (no-op if already present)."
    )
    lines.append("Plan: ensure indexes (idempotent, exact-match verify):")
    for name, keys, opts in INDEX_SPECS:
        keys_repr = ", ".join(f"{k}: {v}" for k, v in keys)
        opts_repr = ", ".join(
            f"{k}={v}" for k, v in opts.items() if k != "name"
        )
        lines.append(f"  - {name} on ({keys_repr}) [{opts_repr}]")
    lines.append("Plan: ensure custom roles (idempotent, exact-match verify):")
    lines.append(
        f"  - {WRITER_ROLE_NAME}: insert on "
        f"{ALLOWED_DATABASE}.{ALLOWED_COLLECTION}"
    )
    lines.append(
        f"  - {READER_ROLE_NAME}: find on "
        f"{ALLOWED_DATABASE}.{ALLOWED_COLLECTION}"
    )
    lines.append("Plan: ensure runtime users (idempotent, role-binding verify):")
    lines.append(f"  - {WRITER_USER_NAME} ← {WRITER_ROLE_NAME}")
    lines.append(f"  - {READER_USER_NAME} ← {READER_ROLE_NAME}")
    lines.append("Plan: QualitySummary collection MUST NOT be created (Phase 1).")
    return lines


def run_dry_run() -> int:
    """默认模式：只打印预期操作，零副作用。"""
    _validate_targets(ALLOWED_DATABASE, ALLOWED_COLLECTION)
    # dry-run 也对所有身份名称做一次精确校验（防止常量被误改）。
    for name in (WRITER_ROLE_NAME, READER_ROLE_NAME, WRITER_USER_NAME, READER_USER_NAME):
        _validate_identity_name(name, kind="identity")

    print("[DRY-RUN] audit_rollout — no side effects will be performed.")
    for line in _describe_plan():
        print(f"  {line}")
    print("[DRY-RUN] done. Pass --apply to execute.")
    return 0


def run_verify() -> int:
    """只读验证：检查 collection / 3 indexes / 2 roles / 2 users 是否符合契约。

    任一项不符即退出码 1；同时显式校验 QualitySummary 集合**不存在**。
    """
    _validate_targets(ALLOWED_DATABASE, ALLOWED_COLLECTION)
    for name in (WRITER_ROLE_NAME, READER_ROLE_NAME, WRITER_USER_NAME, READER_USER_NAME):
        _validate_identity_name(name, kind="identity")

    try:
        client = _open_ddl_client()
    except MissingCredentialError as exc:
        print(f"[VERIFY] cannot connect without credentials: {exc}", file=sys.stderr)
        return 3

    try:
        db = client[ALLOWED_DATABASE]
        problems: list[str] = []

        # 1. collection 存在
        if ALLOWED_COLLECTION not in db.list_collection_names():
            problems.append(
                f"collection {ALLOWED_DATABASE!r}.{ALLOWED_COLLECTION!r} missing"
            )
        else:
            coll = db[ALLOWED_COLLECTION]
            existing = {idx["name"]: idx for idx in coll.list_indexes()}
            for name, keys, opts in INDEX_SPECS:
                cur = existing.get(name)
                if cur is None:
                    problems.append(f"index {name!r} missing")
                elif not _index_matches(cur, keys, opts):
                    problems.append(
                        f"index {name!r} definition mismatch "
                        f"(expected keys={keys} opts={opts}, "
                        f"got keys={list(cur.get('key', {}).items())} "
                        f"opts={{'expireAfterSeconds': {cur.get('expireAfterSeconds')}, "
                        f"'name': {cur.get('name')!r}}})"
                    )

        # 2. QualitySummary 集合必须不存在
        if "03_data_ud_quality_summary" in db.list_collection_names():
            problems.append(
                "QualitySummary collection 03_data_ud_quality_summary must NOT "
                "exist in Phase 1"
            )

        # 3. roles 存在且 privileges / inherited roles 精确匹配
        # 注意：Mongo 7 在 ``rolesInfo`` 按名字查单个 role 时，默认不返回
        # privileges 字段（即 ``privileges=None``），必须显式传
        # ``showPrivileges: True``，否则 ``_role_privileges_match`` 会把
        # ``None`` 与期望列表比成 False，导致 verify 在合法状态下退出 1。
        for role_name, expected_privs, expected_roles in (
            (WRITER_ROLE_NAME, WRITER_ROLE_PRIVILEGES, WRITER_ROLE_ROLES),
            (READER_ROLE_NAME, READER_ROLE_PRIVILEGES, READER_ROLE_ROLES),
        ):
            info = db.command({"rolesInfo": role_name, "showPrivileges": True})
            roles_block = info.get("roles") or []
            if not roles_block:
                problems.append(f"role {role_name!r} missing")
                continue
            rinfo = roles_block[0]
            if not _role_privileges_match(rinfo.get("privileges"), expected_privs):
                problems.append(
                    f"role {role_name!r} privileges mismatch "
                    f"(expected={expected_privs}, got={rinfo.get('privileges')})"
                )
            if not _role_inherited_roles_match(rinfo.get("roles"), expected_roles):
                problems.append(
                    f"role {role_name!r} inherited roles mismatch "
                    f"(expected={expected_roles}, got={rinfo.get('roles')})"
                )

        # 4. users 存在且 role binding 一致
        for user_name, expected_role_binding in (
            (WRITER_USER_NAME, [{"role": WRITER_ROLE_NAME, "db": ALLOWED_DATABASE}]),
            (READER_USER_NAME, [{"role": READER_ROLE_NAME, "db": ALLOWED_DATABASE}]),
        ):
            info = db.command({"usersInfo": user_name})
            users_block = info.get("users") or []
            if not users_block:
                problems.append(f"user {user_name!r} missing")
                continue
            uinfo = users_block[0]

            def _verify_user_role_key(item: Any) -> str:
                if isinstance(item, dict):
                    return f"{item.get('role', '')}@{item.get('db', '')}"
                return str(item)

            actual_roles = sorted(uinfo.get("roles") or [], key=_verify_user_role_key)
            expected_sorted = sorted(expected_role_binding, key=_verify_user_role_key)
            if actual_roles != expected_sorted:
                problems.append(
                    f"user {user_name!r} role binding mismatch "
                    f"(expected={expected_sorted}, got={actual_roles})"
                )

        if problems:
            print(f"[VERIFY] FAIL: {len(problems)} issue(s):")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(
            f"[VERIFY] OK: collection {ALLOWED_DATABASE!r}.{ALLOWED_COLLECTION!r}, "
            f"3 indexes, 2 roles, 2 users all match contract; QualitySummary absent."
        )
        return 0
    except ScopeViolation:
        raise
    except Exception as exc:
        print(f"[VERIFY] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    finally:
        client.close()


def run_apply() -> int:
    """执行 DDL：创建/校验 collection、3 indexes、2 roles、2 users（全部幂等）。"""
    _validate_targets(ALLOWED_DATABASE, ALLOWED_COLLECTION)
    for name in (WRITER_ROLE_NAME, READER_ROLE_NAME, WRITER_USER_NAME, READER_USER_NAME):
        _validate_identity_name(name, kind="identity")

    try:
        client = _open_ddl_client()
    except MissingCredentialError as exc:
        print(f"[APPLY] missing credentials: {exc}", file=sys.stderr)
        return 3

    try:
        db = client[ALLOWED_DATABASE]

        # 0. 只读 user 预检。缺失 runtime 密码或 binding 不匹配时，在任何
        # collection/index/role/user 写 DDL 前退出；预检始终使用 DDL identity。
        _preflight_runtime_users(db)

        # 1. collection（仅 audit；QualitySummary 永不创建）
        try:
            db.create_collection(ALLOWED_COLLECTION)
        except Exception as exc:
            if ALLOWED_COLLECTION not in db.list_collection_names():
                raise RolloutError(
                    f"create_collection failed and target missing: {exc}"
                ) from exc
        # 防御性：QualitySummary 集合在 apply 流程中**绝对不能**被创建
        if "03_data_ud_quality_summary" in db.list_collection_names():
            raise RolloutError(
                "QualitySummary collection 03_data_ud_quality_summary must NOT "
                "exist in Phase 1 — refusing to proceed"
            )

        # 2. 3 indexes（精确比对 / 缺失或定义不符 fail-closed）
        idx = _ensure_indexes(db, ALLOWED_COLLECTION)
        if idx["mismatched"]:
            raise IdentityPrivilegeMismatch(
                f"index definition mismatch: {idx['mismatched']}"
            )

        # 3. 2 roles（精确 privileges 比对）
        writer_role_state = _ensure_write_role(db)
        reader_role_state = _ensure_read_role(db)

        # 4. 2 users（精确 role binding 比对）
        writer_user_state = _ensure_write_user(db)
        reader_user_state = _ensure_read_user(db)

        print(
            f"[APPLY] OK: collection {ALLOWED_DATABASE!r}.{ALLOWED_COLLECTION!r} ready. "
            f"indexes created={idx['created']} skipped={idx['skipped']} "
            f"mismatched={idx['mismatched']}; "
            f"writer_role={writer_role_state}; reader_role={reader_role_state}; "
            f"writer_user={writer_user_state}; reader_user={reader_user_state}"
        )
        return 0
    except ScopeViolation:
        raise
    except IdentityPrivilegeMismatch as exc:
        print(f"[APPLY] BLOCKED: {exc}", file=sys.stderr)
        return 4
    except MissingCredentialError as exc:
        print(f"[APPLY] missing credentials: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        # 注意：绝不打 URI / user / password / token
        print(
            f"[APPLY] ERROR: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 4
    finally:
        client.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit_rollout",
        description=(
            "Phase 2 Audit-only 受控 DDL 工具。"
            "默认 dry-run；仅在 Pascal 显式授权后 --apply。"
            "role/user 名称为模块级常量，不可通过 CLI 覆盖。"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行 DDL；不传时默认 dry-run。",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="只读验证 collection/index/role/user 全部 DDL 结果；不动数据。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --apply / --verify 互斥；都不传 → dry-run
    if args.apply and args.verify:
        parser.error("--apply and --verify are mutually exclusive")

    try:
        if args.verify:
            return run_verify()
        if args.apply:
            return run_apply()
        return run_dry_run()
    except ScopeViolation as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 2
    except MissingCredentialError as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())