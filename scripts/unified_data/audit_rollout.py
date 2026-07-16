#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_rollout.py — Unified Data Phase 2 Audit-only 受控 DDL 工具。

DESIGN-03-011 §5.3 / §8.5 / §8.8 — Pascal 已确认的 Phase 2 Audit-only
production rollout 脚本。本脚本仅在 Pascal 显式授权后执行；默认 dry-run。

设计原则（来自 task body 与 §8）：

1. **静态范围**：仅创建 / 校验 ``tradingagents.03_data_ud_query_audit``
   集合与索引。不得创建 / 校验 ``03_data_ud_quality_summary``，不得触碰
   portfolio_/smart_money_/signal_/trade_* 等既有业务集合。
2. **DDL 账号隔离**：通过 ``UD_DDL_MONGO_URI`` / ``UD_DDL_MONGO_USERNAME`` /
   ``UD_DDL_MONGO_PASSWORD`` 显式环境变量读取 DDL 凭证；缺失即 fail-fast；
   不得复用运行时 writer 凭证。
3. **默认 dry-run**：未传 ``--apply`` 时只打印预期操作，零副作用。
4. **--verify**：只读路径，对目标集合索引状态做检查。
5. **幂等**：``--apply`` 重复执行不会重复创建已存在索引。
6. **fail-closed on target mismatch**：database/collection/role 名称不在
   硬编码 allow-list 内直接拒绝（fail-fast），绝不向其他目标发起连接。

退出码：
    0  成功（dry-run / verify / apply）
    2  静态范围校验失败（target 不在 allow-list）
    3  凭证缺失（fail-fast）
    4  apply 阶段运行时错误（被 pymongo 抛出）
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# 静态 allow-list（Pascal 已确认）
# ---------------------------------------------------------------------------

ALLOWED_DATABASE: str = "tradingagents"
ALLOWED_COLLECTION: str = "03_data_ud_query_audit"

# 索引设计：TTL (fetched_at, expireAfterSeconds=31536000) + 两个二级索引
TTL_SECONDS: int = 365 * 24 * 3600  # 365 天，Pascal 已确认

# 索引元组： (name, keys, options)
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

# 运行时 writer / reader 角色 / 用户前缀 — 仅校验命名空间前缀。
# DDL 脚本仅校验命名空间，禁止授予任何 portfolio / smart_money / signal /
# trade / cache 集合权限；这些是 Design §8.5 的硬规则。
WRITER_ROLE_PREFIX: str = "ud_audit_writer"
READER_ROLE_PREFIX: str = "ud_audit_reader"


# ---------------------------------------------------------------------------
# 错误类
# ---------------------------------------------------------------------------


class RolloutError(Exception):
    """Rollout 阶段非预期的运行时错误（apply 失败）。"""


class ScopeViolation(RolloutError):
    """目标不在 allow-list 内（fail-fast）。"""


class MissingCredentialError(RolloutError):
    """缺少 DDL 凭证（fail-fast）。"""


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


def _validate_role_name(role_name: str, *, kind: str) -> None:
    """校验运行时 role/user 命名符合 allow-list 前缀。

    不实际授予权限（脚本只校验命名空间）；DDL bootstrap 不允许成为
    运行时身份（DESIGN §8.5）。
    """
    if kind == "writer" and not role_name.startswith(WRITER_ROLE_PREFIX):
        raise ScopeViolation(
            f"writer role/user {role_name!r} must start with "
            f"{WRITER_ROLE_PREFIX!r}"
        )
    if kind == "reader" and not role_name.startswith(READER_ROLE_PREFIX):
        raise ScopeViolation(
            f"reader role/user {role_name!r} must start with "
            f"{READER_ROLE_PREFIX!r}"
        )


def _load_ddl_credentials() -> dict[str, str]:
    """从显式环境变量读取 DDL 凭证；缺失即 fail-fast。

    禁止打印、记录或持久化任何凭证字段。
    """
    uri = os.environ.get("UD_DDL_MONGO_URI", "").strip()
    user = os.environ.get("UD_DDL_MONGO_USERNAME", "").strip()
    password = os.environ.get("UD_DDL_MONGO_PASSWORD", "").strip()
    auth_db = os.environ.get("UD_DDL_MONGO_AUTH_DB", "admin").strip() or "admin"

    missing = []
    if not uri:
        missing.append("UD_DDL_MONGO_URI")
    if not user:
        missing.append("UD_DDL_MONGO_USERNAME")
    if not password:
        missing.append("UD_DDL_MONGO_PASSWORD")
    if missing:
        raise MissingCredentialError(
            f"missing DDL credentials: {', '.join(missing)}"
        )

    # 不打印任何凭证字段；只回传必要句柄
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
    """打开独立的 DDL 连接；不在脚本间共享；close 立即释放。

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


def _describe_plan(
    database: str,
    collection: str,
    *,
    writer_role: str | None,
    reader_role: str | None,
) -> list[str]:
    """打印人类可读的执行计划（dry-run 与 --verify 都使用）。"""
    lines: list[str] = []
    lines.append(
        f"Plan: ensure collection {database!r}.{collection!r} exists "
        f"(no-op if already present; mongomock-friendly)."
    )
    lines.append("Plan: ensure indexes (idempotent):")
    for name, keys, opts in INDEX_SPECS:
        keys_repr = ", ".join(f"{k}: {v}" for k, v in keys)
        opts_repr = ", ".join(f"{k}={v}" for k, v in opts.items() if k != "name")
        lines.append(f"  - {name} on ({keys_repr}) [{opts_repr}]")
    lines.append(
        "Plan: validate runtime writer/reader role names "
        "(DDL script grants permissions to pre-existing roles only — "
        "actual privilege granting is out of Phase 1 scope)."
    )
    if writer_role:
        lines.append(f"  writer role/user: {writer_role!r}")
    if reader_role:
        lines.append(f"  reader role/user: {reader_role!r}")
    return lines


# ---------------------------------------------------------------------------
# 三大模式
# ---------------------------------------------------------------------------


def run_dry_run(
    database: str,
    collection: str,
    *,
    writer_role: str | None,
    reader_role: str | None,
) -> int:
    """默认模式：只打印预期操作，零副作用。"""
    _validate_targets(database, collection)
    if writer_role:
        _validate_role_name(writer_role, kind="writer")
    if reader_role:
        _validate_role_name(reader_role, kind="reader")

    print("[DRY-RUN] audit_rollout — no side effects will be performed.")
    for line in _describe_plan(
        database, collection,
        writer_role=writer_role, reader_role=reader_role,
    ):
        print(f"  {line}")
    print("[DRY-RUN] done. Pass --apply to execute.")
    return 0


def run_verify(database: str, collection: str) -> int:
    """只读验证：检查目标集合索引状态。"""
    _validate_targets(database, collection)

    try:
        client = _open_ddl_client()
    except MissingCredentialError as exc:
        print(f"[VERIFY] cannot connect without credentials: {exc}", file=sys.stderr)
        return 3

    try:
        db = client[database]
        if collection not in db.list_collection_names():
            print(
                f"[VERIFY] FAIL: collection {database!r}.{collection!r} "
                f"does not exist."
            )
            return 1
        coll = db[collection]
        existing = {idx["name"]: idx for idx in coll.list_indexes()}
        missing: list[str] = []
        mismatched: list[str] = []
        for name, keys, opts in INDEX_SPECS:
            if name not in existing:
                missing.append(name)
                continue
            cur = existing[name]
            cur_key = list(cur.get("key", []).items())
            cur_ttl = cur.get("expireAfterSeconds")
            target_key = list(keys)
            target_ttl = opts.get("expireAfterSeconds")
            if cur_key != target_key or cur_ttl != target_ttl:
                mismatched.append(name)
        if missing or mismatched:
            print(f"[VERIFY] FAIL: missing={missing} mismatched={mismatched}")
            return 1
        print(
            f"[VERIFY] OK: collection {database!r}.{collection!r} "
            f"has all expected indexes."
        )
        return 0
    except Exception as exc:
        print(f"[VERIFY] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    finally:
        client.close()


def run_apply(database: str, collection: str) -> int:
    """执行 DDL：创建集合与索引（幂等）。"""
    _validate_targets(database, collection)

    try:
        client = _open_ddl_client()
    except MissingCredentialError as exc:
        print(f"[APPLY] missing credentials: {exc}", file=sys.stderr)
        return 3

    try:
        db = client[database]
        # ensureCollection is pymongo 4+ idempotent creation; mongomock 反而
        # 严格（已存在则抛 CollectionInvalid），因此 swallow 该异常以保持
        # 与 pymongo 一致的幂等语义。
        try:
            db.create_collection(collection)
        except Exception as exc:
            # pymongo: CollectionInvalid；mongomock: CollectionInvalid；
            # 只要 collection 随后可见即视为已存在，跳过。
            if collection not in db.list_collection_names():
                raise RolloutError(
                    f"create_collection failed and target missing: {exc}"
                ) from exc
        coll = db[collection]

        created: list[str] = []
        skipped: list[str] = []
        for name, keys, opts in INDEX_SPECS:
            if name in {idx["name"] for idx in coll.list_indexes()}:
                skipped.append(name)
                continue
            # pymongo 不允许在 createIndex 中同时指定 name 与 key 重名，
            # 这里 opts["name"] 就是索引名，直接透传即可
            coll.create_index(list(keys), **opts)
            created.append(name)

        print(
            f"[APPLY] OK: collection {database!r}.{collection!r} ready. "
            f"created={created} skipped={skipped}"
        )
        return 0
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
        ),
    )
    parser.add_argument(
        "--database",
        default=ALLOWED_DATABASE,
        help=(
            f"目标 database (default: {ALLOWED_DATABASE}; "
            "hardcoded allow-list, --database 之外的值会被拒绝)"
        ),
    )
    parser.add_argument(
        "--collection",
        default=ALLOWED_COLLECTION,
        help=(
            f"目标 collection (default: {ALLOWED_COLLECTION}; "
            "hardcoded allow-list)"
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
        help="只读验证索引状态；不动数据。",
    )
    parser.add_argument(
        "--writer-role",
        default=None,
        help=(
            "运行时审计 writer role/user 名（仅校验命名空间前缀，"
            "脚本不实际授予权限）。"
        ),
    )
    parser.add_argument(
        "--reader-role",
        default=None,
        help=(
            "运行时审计 reader role/user 名（仅校验命名空间前缀，"
            "脚本不实际授予权限）。"
        ),
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
            return run_verify(args.database, args.collection)
        if args.apply:
            return run_apply(args.database, args.collection)
        return run_dry_run(
            args.database,
            args.collection,
            writer_role=args.writer_role,
            reader_role=args.reader_role,
        )
    except ScopeViolation as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 2
    except MissingCredentialError as exc:
        print(f"[BLOCKED] {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())