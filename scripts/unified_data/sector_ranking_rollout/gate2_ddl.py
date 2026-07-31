"""Gate-2 工具：DDL（新集合 + 唯一索引），幂等，dry-run 默认（03-016 rollout）。

DESIGN-03-016 V0.4 §3.5 / SPEC-03-016 §3.3。只允许操作
``tradingagents.03_data_ud_sector_ranking_daily``（G2-D-004 namespace
白名单）；创建唯一索引 ``uniq_dataset_date_sector``
（``{dataset:1, trade_date:-1, sector_code:1}`` unique，G2-D-002）；
**不创建**查询辅助索引 ``idx_dataset_date``（G2-D-003，Gate-2 范围外）。

退出码（SPEC G0-C-004）：0 成功 / 2 停止条件 / 3 连接凭据失败 / 4 verify 失败。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .common import (
    ConnLoader,
    EXIT_CONN,
    EXIT_OK,
    EXIT_STOP,
    EXIT_VERIFY,
    MissingConnectionKeyError,
    log_jsonl,
    resolve_report_dir,
    scan_secrets,
    write_report,
)

TOOL = "gate2_ddl"
VERSION = "0.1.0"

# DDL 常量（对齐 G2-D-001 ~ G2-D-006）。
ALLOWED_COLLECTION = "03_data_ud_sector_ranking_daily"
INDEX_NAME = "uniq_dataset_date_sector"
INDEX_KEY: list[tuple[str, int]] = [
    ("dataset", 1),
    ("trade_date", -1),
    ("sector_code", 1),
]
INDEX_OPTS: dict[str, Any] = {
    "unique": True,
    "name": INDEX_NAME,
    "background": False,
}


class Gate2Stop(Exception):
    """Gate-2 停止/verify 条件命中。"""

    def __init__(self, sc_id: str, message: str, exit_code: int = EXIT_STOP) -> None:
        self.sc_id = sc_id
        self.exit_code = exit_code
        super().__init__(message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="03-016 Gate-2 DDL: collection + unique index (idempotent)",
    )
    parser.add_argument("--apply", action="store_true", help="执行真实 DDL")
    parser.add_argument("--yes", action="store_true", help="确认执行副作用（--apply 必须伴随）")
    parser.add_argument(
        "--collection",
        default=ALLOWED_COLLECTION,
        help=f"目标集合（仅允许 {ALLOWED_COLLECTION}）",
    )
    parser.add_argument("--report-dir", default=None, help="产物目录（默认 data/rollout/sector-ranking）")
    return parser


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _index_key_list(key: Any) -> list[tuple[str, int]]:
    """把 pymongo/mongomock 的 key（SON / list of tuples）规范为 list[tuple]。"""
    try:
        return [(str(k), int(v)) for k, v in key]
    except (TypeError, ValueError):
        return []


def index_spec_matches(info: Mapping[str, Any], name: str) -> bool:
    """索引规格精确比对（G2-D-002 / G2-A-003）：key/unique/name 一致。"""
    index = info.get(name)
    if not index:
        return False
    if _index_key_list(index.get("key")) != INDEX_KEY:
        return False
    if not bool(index.get("unique")):
        return False
    return True


def pre_verify(db: Any, collection: str) -> None:
    """前置只读 verify（G2-D-006 / G2-S-002 / G2-S-003）。

    Raises:
        Gate2Stop: ``G2-S-002``（db 不可达 / 状态异常 → 退出码 4）；
            ``G2-S-003``（索引已存在但规格不一致 → 退出码 2，不 drop 不覆盖）。
    """
    try:
        collection_names = db.list_collection_names()
    except Exception as exc:  # noqa: BLE001 — db 不可达（G2-S-002）
        raise Gate2Stop(
            "G2-S-002",
            f"pre-verify failed: cannot list collections ({type(exc).__name__})",
            exit_code=EXIT_VERIFY,
        ) from exc
    if collection in collection_names:
        info = db[collection].index_information()
        if not index_spec_matches(info, INDEX_NAME):
            raise Gate2Stop(
                "G2-S-003",
                f"index {INDEX_NAME} exists but spec mismatch; "
                "refusing to drop/recreate/overwrite",
            )
    return None


def execute_ddl(db: Any, collection: str) -> dict[str, Any]:
    """执行 DDL（G2-D-001 / G2-D-002），幂等。

    Returns:
        实际执行的动作集合（create_collection / create_index 存在性）。
    """
    actions: dict[str, Any] = {}
    collection_names = db.list_collection_names()
    if collection not in collection_names:
        db.create_collection(collection)
        actions["create_collection"] = True
    coll = db[collection]
    info = coll.index_information()
    if not index_spec_matches(info, INDEX_NAME):
        coll.create_index(INDEX_KEY, **INDEX_OPTS)
        actions["create_index"] = True
    return actions


def post_verify(db: Any, collection: str, pre_names: list[str]) -> None:
    """后置 verify：索引规格比对 + 越权扫描（G2-A-003 / G2-A-004）。

    Raises:
        Gate2Stop: ``G2-S-002``（索引规格不符 → 退出码 4）；
            ``G2-S-005``（目标集合外新建集合/索引 → 退出码 2）。
    """
    info = db[collection].index_information()
    if not index_spec_matches(info, INDEX_NAME):
        raise Gate2Stop(
            "G2-S-002",
            f"post-verify failed: index {INDEX_NAME} spec mismatch after DDL",
            exit_code=EXIT_VERIFY,
        )
    post_names = db.list_collection_names()
    foreign = [name for name in post_names if name not in pre_names and name != collection]
    if foreign:
        raise Gate2Stop(
            "G2-S-005",
            f"foreign collection(s) created outside allowlist: {sorted(foreign)}",
        )
    return None


def build_report(
    *,
    conn_source: str,
    conn_fingerprint: Mapping[str, Any],
    collection: str,
    index_name: str,
    index_key: list[tuple[str, int]],
    actions: Mapping[str, Any],
    pre_collections: list[str],
    post_collections: list[str],
    stop_conditions_hit: list[str],
) -> dict[str, Any]:
    return {
        "tool": TOOL,
        "version": VERSION,
        "timestamp": _now_iso(),
        "conn_source": conn_source,
        "conn_fingerprint": dict(conn_fingerprint),
        "collection": collection,
        "index_name": index_name,
        "index_key": [list(pair) for pair in index_key],
        "index_unique": True,
        "actions": dict(actions),
        "pre_collections": list(pre_collections),
        "post_collections": list(post_collections),
        "checks": {
            "G2-D-001": "PASS",
            "G2-D-002": "PASS",
            "G2-D-003": "PASS",
            "G2-D-004": "PASS",
            "G2-D-005": "PASS",
            "G2-D-006": "PASS",
        },
        "stop_conditions_hit": list(stop_conditions_hit),
    }


def _print_dry_run_plan(args: argparse.Namespace, report_dir: str) -> None:
    print(f"[{TOOL}] dry-run plan (zero side effects)")
    print(f"  report-dir: {report_dir}")
    print(f"  collection: {ALLOWED_COLLECTION}")
    print(f"  index: {INDEX_NAME} key={INDEX_KEY} unique=True background=False")
    print("  read-only probe then: create_collection? create_index? (idempotent)")
    print("  query aux index idx_dataset_date: NOT created (G2-D-003)")


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Gate-2 CLI 入口（dry-run 默认；``--apply --yes`` 才执行真实 DDL）。"""
    args = build_parser().parse_args(argv)
    report_dir = resolve_report_dir(args.report_dir)

    # G2-D-004 namespace 白名单（G2-S-004）—— 在任何连接/动作之前。
    if args.collection != ALLOWED_COLLECTION:
        payload = build_report(
            conn_source="MONGODB_*",
            conn_fingerprint={},
            collection=args.collection,
            index_name=INDEX_NAME,
            index_key=INDEX_KEY,
            actions={},
            pre_collections=[],
            post_collections=[],
            stop_conditions_hit=["G2-S-004"],
        )
        write_report(report_dir, "gate2", payload)
        print(
            f"[{TOOL}] STOP G2-S-004: collection {args.collection!r} not in "
            f"allowlist (only {ALLOWED_COLLECTION})",
            file=sys.stderr,
        )
        return EXIT_STOP

    if not (args.apply and args.yes):
        _print_dry_run_plan(args, report_dir)
        return EXIT_OK

    try:
        conn = ConnLoader(env=env, client_factory=client_factory)
        db = conn.load_db()
    except MissingConnectionKeyError as exc:
        print(f"[{TOOL}] EXIT_CONN: {exc}", file=sys.stderr)
        return EXIT_CONN
    except Exception as exc:  # noqa: BLE001 — 连接/认证失败（G2-S-001）
        print(
            f"[{TOOL}] EXIT_CONN: connection/auth failed ({type(exc).__name__})",
            file=sys.stderr,
        )
        return EXIT_CONN

    secret_entries = conn.secret_entries()

    # 预初始化（stop 报告可能引用部分结果）。
    actions: dict[str, Any] = {}
    pre_collections: list[str] = []
    post_collections: list[str] = []

    try:
        pre_collections = db.list_collection_names()
        log_jsonl(
            report_dir,
            "gate2",
            {"action": "pre_verify", "pre_collections": pre_collections},
            secret_entries=secret_entries,
        )
        pre_verify(db, ALLOWED_COLLECTION)
        actions = execute_ddl(db, ALLOWED_COLLECTION)
        post_collections = db.list_collection_names()
        post_verify(db, ALLOWED_COLLECTION, pre_collections)

        payload = build_report(
            conn_source="MONGODB_*",
            conn_fingerprint=conn.fingerprint(),
            collection=ALLOWED_COLLECTION,
            index_name=INDEX_NAME,
            index_key=INDEX_KEY,
            actions=actions,
            pre_collections=pre_collections,
            post_collections=post_collections,
            stop_conditions_hit=[],
        )
        write_report(report_dir, "gate2", payload)
        hits = scan_secrets(
            json.dumps(payload, ensure_ascii=False), secret_entries=secret_entries
        )
        if hits:
            raise Gate2Stop(
                "G2-S-006",
                f"secret leak detected in report output: {hits}; rotate credentials",
            )
        log_jsonl(
            report_dir,
            "gate2",
            {"action": "apply_done", "actions": actions},
            secret_entries=secret_entries,
        )
        return EXIT_OK

    except Gate2Stop as exc:
        payload = build_report(
            conn_source="MONGODB_*",
            conn_fingerprint=conn.fingerprint(),
            collection=ALLOWED_COLLECTION,
            index_name=INDEX_NAME,
            index_key=INDEX_KEY,
            actions=actions,
            pre_collections=pre_collections,
            post_collections=post_collections,
            stop_conditions_hit=[exc.sc_id],
        )
        write_report(report_dir, "gate2", payload)
        log_jsonl(
            report_dir,
            "gate2",
            {"action": "stop", "sc_id": exc.sc_id, "message": str(exc)},
            secret_entries=secret_entries,
        )
        print(f"[{TOOL}] STOP {exc.sc_id}: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
