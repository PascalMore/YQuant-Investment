"""UD 数据库非破坏迁移 — 03-018 §5。

固定源 ``tradingagents`` → 固定目标 ``yquant-data``，五个集合名完全相同：

1. ``03_data_ud_sector_ranking_daily``
2. ``03_data_ud_query_audit``
3. ``03_data_ud_market_sector_snapshot``
4. ``03_data_ud_market_sentiment_snapshot``
5. ``03_data_ud_stock_capital_flow``

三个子命令：

* ``plan`` —— 只读枚举元数据 / 扫描建 digest；**不写 DB / 不 DDL**。
* ``apply --manifest ... --apply`` —— 显式 apply 才写；缺 ``--apply`` 是
  参数错误（退出 20），不隐式执行。
* ``verify --manifest ...`` —— 只读逐 ID 比对；不写 DB。

退出码（本题专属 0/10/20/30/40，不改旧 03-016 脚本的 0–4）：

* 0 成功
* 10 部分通过 / 未校验完 / backlog
* 20 参数 / 冲突 / 漂移 / 校验失败
* 30 BUSY
* 40 超时 / 已知中断

比较口径：``bson.json_util.CANONICAL_JSON_OPTIONS``、对象键确定排序、
数组顺序保留、typed ``_id`` 同样 canonical 编码、SHA256 按 UTF-8；区分
int32/Int64、Decimal128、ObjectId/Binary/Date，不经 float。

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import sqlite3
import tempfile
from contextlib import contextmanager
from itertools import islice
from datetime import datetime, timezone
from pymongo import timeout
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

EXIT_OK = 0
EXIT_PARTIAL = 10
EXIT_FAIL = 20
EXIT_BUSY = 30
EXIT_TIMEOUT = 40

#: 五个显式迁移集合（不做通配复制）。
MIGRATION_COLLECTIONS: tuple[str, ...] = (
    "03_data_ud_sector_ranking_daily",
    "03_data_ud_query_audit",
    "03_data_ud_market_sector_snapshot",
    "03_data_ud_market_sentiment_snapshot",
    "03_data_ud_stock_capital_flow",
)

#: 归属证据符号（每集合对应的代码 ownership 证据）。
OWNERSHIP_EVIDENCE: dict[str, str] = {
    "03_data_ud_sector_ranking_daily": (
        "scripts/unified_data/sector_ranking_rollout/prod_repository.py:"
        "ProdRankingWriter.COLLECTION"
    ),
    "03_data_ud_query_audit": (
        "skills/data/unified_data/audit/logger.py:AuditLogger.collection_name"
    ),
    "03_data_ud_market_sector_snapshot": (
        "skills/data/unified_data/services/sector_service.py:"
        "get_sector_snapshot (materialised 03_data_ud_* prefix)"
    ),
    "03_data_ud_market_sentiment_snapshot": (
        "skills/data/unified_data/services/sentiment_service.py:"
        "refresh_market_sentiment (materialised 03_data_ud_* prefix)"
    ),
    "03_data_ud_stock_capital_flow": (
        "skills/data/unified_data/services/flow_service.py:"
        "refresh_capital_flow (materialised 03_data_ud_* prefix)"
    ),
}

#: 迁移 manifest 版本。
MANIFEST_VERSION = 1

#: 单批复制上限。
BATCH_SIZE = 1000

#: 服务端元数据（不可移植，不复制）。
NON_PORTABLE_INDEX_KEYS: frozenset[str] = frozenset({"v", "ns", "uuid", "buildUUID"})


class MigrationError(RuntimeError):
    """迁移 STOP 条件（冲突 / 漂移 / 未知归属）。"""


# ---------------------------------------------------------------------------
# digest 辅助
# ---------------------------------------------------------------------------


def canonical_digest(document: Any) -> str:
    """返回单个 BSON 文档的 canonical SHA-256。

    使用 ``bson.json_util.CANONICAL_JSON_OPTIONS``；ObjectId / Decimal128 /
    datetime / Binary / int64 都按其 BSON 类型编码。
    """
    from bson import json_util

    payload = json_util.dumps(document, json_options=json_util.CANONICAL_JSON_OPTIONS,
                              sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _portable_index(index: dict[str, Any]) -> dict[str, Any]:
    """返回可移植索引定义（排除服务端元数据键）。"""
    out = {k: v for k, v in index.items() if k not in NON_PORTABLE_INDEX_KEYS}
    if "key" in out:
        out["key"] = _ordered_index_keys(index)
    return out


def _ordered_index_keys(index: Mapping[str, Any]) -> list[list[Any]]:
    """返回有序的索引键列表（保顺序 / 方向）。

    pymongo 返回 ``SON`` / list-of-tuples；mongomock 返回 dict。两者都要
    规范成**有序**的 ``[[field, direction], ...]``，不按字段名排序。
    """
    raw = index.get("key") or []
    if isinstance(raw, Mapping):
        return [[str(name), int(direction)] for name, direction in raw.items()]
    return [[str(name), int(direction)] for name, direction in raw]


def index_signature(index: dict[str, Any]) -> str:
    """返回索引的可移植签名（键顺序 / 方向保留，不按字段名排序）。"""
    ordered = _ordered_index_keys(index)
    portable = _portable_index(index)
    portable.pop("key", None)
    payload = {"keys": ordered, "options": portable}
    return canonical_digest(payload)


# ---------------------------------------------------------------------------
# 数据访问（显式注入，便于测试替身）
# ---------------------------------------------------------------------------


class MigrationDatabase:
    """薄 Mongo 访问层（只允许 find / list / createCollection / createIndex / insert）。"""

    def __init__(self, source_db: Any, target_db: Any) -> None:
        if (source_db.name != "tradingagents" or target_db.name != "yquant-data"
                or source_db.client is not target_db.client):
            raise MigrationError("DATABASE_IDENTITY_MISMATCH")
        self.source_db = source_db
        self.target_db = target_db
        self.source_commands: list[str] = []
        self.target_commands: list[str] = []

    # -- 源（只读） ------------------------------------------------------
    def list_source_collections(self) -> list[str]:
        self.source_commands.append("listCollectionNames")
        with timeout(10):
            return list(self.source_db.list_collection_names())

    def source_options(self, collection: str) -> dict[str, Any]:
        self.source_commands.append("listCollections")
        try:
            info = self.source_db.command(
                {"listCollections": 1, "filter": {"name": collection}}
            )
        except Exception:
            raise MigrationError("COLLECTION_OPTIONS_UNREADABLE") from None
        for entry in info.get("cursor", {}).get("firstBatch", []):
            return dict(entry.get("options") or {})
        return {}

    def source_indexes(self, collection: str) -> list[dict[str, Any]]:
        self.source_commands.append("listIndexes")
        return [dict(idx) for idx in self.source_db[collection].list_indexes()]

    def iter_source(self, collection: str) -> Iterator[Any]:
        self.source_commands.append("find")
        yield from self._iterate(self.source_db[collection])

    def iter_target(self, collection: str) -> Iterator[Any]:
        """Stream target BSON in bounded batches with per-operation deadlines."""
        self.target_commands.append("find")
        yield from self._iterate(self.target_db[collection])

    @staticmethod
    def _iterate(collection: Any) -> Iterator[Any]:
        with timeout(10):
            cursor = collection.find({}).batch_size(BATCH_SIZE).max_time_ms(10000)
        try:
            while True:
                with timeout(10):
                    batch = list(islice(cursor, BATCH_SIZE))
                if not batch:
                    break
                yield from batch
        finally:
            cursor.close()

    def source_count(self, collection: str) -> int:
        self.source_commands.append("countDocuments")
        return int(self.source_db[collection].count_documents({}))

    # -- 目标（受限写） --------------------------------------------------
    def target_has_collection(self, collection: str) -> bool:
        self.target_commands.append("listCollectionNames")
        with timeout(10):
            return collection in self.target_db.list_collection_names()

    def target_options(self, collection: str) -> dict[str, Any]:
        self.target_commands.append("listCollections")
        try:
            info = self.target_db.command(
                {"listCollections": 1, "filter": {"name": collection}}
            )
        except Exception:
            raise MigrationError("COLLECTION_OPTIONS_UNREADABLE") from None
        for entry in info.get("cursor", {}).get("firstBatch", []):
            return dict(entry.get("options") or {})
        return {}

    def target_indexes(self, collection: str) -> list[dict[str, Any]]:
        self.target_commands.append("listIndexes")
        return [dict(idx) for idx in self.target_db[collection].list_indexes()]

    def create_collection(self, collection: str, options: dict[str, Any]) -> None:
        self.target_commands.append("createCollection")
        self.target_db.create_collection(collection, **options)

    def create_index(self, collection: str, index: dict[str, Any]) -> None:
        self.target_commands.append("createIndex")
        # mongomock / pymongo both need an ordered list of (field, direction)
        # tuples — a plain dict loses the key order.
        keys = _ordered_index_keys(index)
        options = _portable_index(index)
        options.pop("key", None)
        with timeout(10):
            self.target_db[collection].create_index([tuple(pair) for pair in keys], **options)

    def insert_many(self, collection: str, documents: list[Any]) -> Any:
        self.target_commands.append("insert")
        return self.target_db[collection].insert_many(documents, ordered=True)

    def target_find(self, collection: str, filter: dict[str, Any]) -> list[Any]:
        self.target_commands.append("find")
        with timeout(10):
            return list(self.target_db[collection].find(filter).max_time_ms(10000)
                        .batch_size(BATCH_SIZE))


# ---------------------------------------------------------------------------
# manifest 构建
# ---------------------------------------------------------------------------


def _typed_id(value: Any) -> str:
    from bson import json_util

    return json_util.dumps(value, json_options=json_util.CANONICAL_JSON_OPTIONS,
                           sort_keys=True, separators=(",", ":"))


def _index_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA cache_size=-2048")
    connection.execute("CREATE TABLE records (collection TEXT, side TEXT, id TEXT, "
                       "digest TEXT, fetched TEXT, PRIMARY KEY(collection, side, id))")


def _index_rows(connection, name, side, rows) -> int:
    count = 0
    for document in rows:
        fetched = document.get("fetched_at")
        if isinstance(fetched, datetime):
            if fetched.tzinfo is not None:
                fetched = fetched.astimezone(timezone.utc).replace(tzinfo=None)
            fetched = fetched.isoformat()
        else:
            fetched = None
        connection.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?)", (
            name, side, _typed_id(document["_id"]), canonical_digest(document), fetched,
        ))
        count += 1
        if count % BATCH_SIZE == 0:
            connection.commit()
    connection.commit()
    return count


def _plan_identity(manifest: dict[str, Any]) -> str:
    return canonical_digest({key: manifest[key] for key in (
        "manifest_version", "source_database", "target_database", "collections",
        "observed_at_utc", "digest_index_ref", "digest_index_sha256",
    )})


def _validate_manifest(manifest: dict[str, Any]) -> Path:
    if (manifest.get("manifest_version") != MANIFEST_VERSION
            or manifest.get("source_database") != "tradingagents"
            or manifest.get("target_database") != "yquant-data"
            or [entry.get("collection") for entry in manifest.get("collections", [])]
            != list(MIGRATION_COLLECTIONS)):
        raise MigrationError("MANIFEST_IDENTITY_MISMATCH")
    if manifest.get("plan_sha256") != _plan_identity(manifest):
        raise MigrationError("MANIFEST_CHANGED")
    path = Path(manifest["digest_index_ref"]).resolve()
    allowed = (Path(tempfile.gettempdir()).resolve(),
               Path("data/reports/2026-11-11-yquant-data-history/evidence").resolve())
    if not any(path.is_relative_to(root) for root in allowed):
        raise MigrationError("INDEX_PATH_NOT_ALLOWED")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["digest_index_sha256"]:
        raise MigrationError("DIGEST_INDEX_CHANGED")
    return path


def build_manifest(
    db: MigrationDatabase, collections: Iterable[str] = MIGRATION_COLLECTIONS, *,
    observed_at: datetime | None = None, index_dir: str | None = None,
) -> dict[str, Any]:
    """Read-only DB plan with bounded typed-ID SQLite evidence, including empty collections."""
    if tuple(collections) != MIGRATION_COLLECTIONS:
        raise MigrationError("COLLECTION_ALLOWLIST_MISMATCH")
    observed = observed_at or datetime.now(timezone.utc).replace(tzinfo=None)
    if observed.tzinfo is not None:
        observed = observed.astimezone(timezone.utc).replace(tzinfo=None)
    unknown = sorted(name for name in db.list_source_collections()
                     if name.startswith("03_data_ud_") and name not in MIGRATION_COLLECTIONS)
    if unknown:
        raise MigrationError("unknown 03_data_ud_* collection(s): " + ", ".join(unknown))
    handle = tempfile.NamedTemporaryFile(prefix="ud-migration-", suffix=".sqlite",
                                         dir=index_dir, delete=False)
    path = Path(handle.name)
    handle.close()
    entries = []
    with sqlite3.connect(path) as connection:
        _index_schema(connection)
        for name in MIGRATION_COLLECTIONS:
            with timeout(10):
                options = _portable_options(db.source_options(name))
                indexes = db.source_indexes(name)
            count = _index_rows(connection, name, "source", db.iter_source(name))
            target_count = _index_rows(connection, name, "target", db.iter_target(name))
            entries.append({
                "collection": name, "ownership_evidence": OWNERSHIP_EVIDENCE[name],
                "source_count": count, "source_options": options,
                "source_indexes": [{"name": index.get("name"),
                                    "signature": index_signature(index),
                                    "definition": _portable_index(index)} for index in indexes],
                "target_exists": db.target_has_collection(name), "target_count": target_count,
            })
    manifest = {
        "manifest_version": MANIFEST_VERSION, "source_database": "tradingagents",
        "target_database": "yquant-data", "observed_at_utc": observed.isoformat() + "Z",
        "collections": entries, "excluded_server_metadata": sorted(NON_PORTABLE_INDEX_KEYS),
        "permissions": {}, "quiescence": None, "result": "planned",
        "digest_index_ref": str(path.resolve()),
        "digest_index_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    manifest["plan_sha256"] = _plan_identity(manifest)
    return manifest


def _portable_options(options: dict[str, Any]) -> dict[str, Any]:
    """Drop only server identity metadata; unknown business options remain visible."""
    return {key: value for key, value in options.items() if key not in {"uuid", "idIndex"}}


# ---------------------------------------------------------------------------
# 复制
# ---------------------------------------------------------------------------


def _metadata_matches(db, entry, *, target=False, allow_missing=False) -> bool:
    name = entry["collection"]
    if target and not db.target_has_collection(name):
        return allow_missing
    with timeout(10):
        options = db.target_options(name) if target else db.source_options(name)
    if canonical_digest(_portable_options(options)) != canonical_digest(entry["source_options"]):
        return False
    with timeout(10):
        indexes = db.target_indexes(name) if target else db.source_indexes(name)
    expected = {item["name"]: item["signature"] for item in entry["source_indexes"]}
    actual = {item["name"]: index_signature(item) for item in indexes}
    # Empty source collections may have no _id index until their first write.
    if not expected:
        expected = {"_id_": index_signature({"name": "_id_", "key": [("_id", 1)]})}
    if not actual:
        actual = {"_id_": index_signature({"name": "_id_", "key": [("_id", 1)]})}
    return (all(key in expected and value == expected[key] for key, value in actual.items())
            and (allow_missing or actual == expected))


def compare_collections(db: MigrationDatabase, manifest: dict[str, Any]) -> dict[str, Any]:
    """Compare every typed ID against immutable pre-copy evidence and current source."""
    path = _validate_manifest(manifest)
    report = {"collections": {}, "ok": True, "drift": False}
    observed_end = datetime.now(timezone.utc).replace(tzinfo=None)
    with tempfile.TemporaryDirectory(prefix="ud-compare-") as directory:
        with sqlite3.connect(f"{directory}/live.sqlite") as connection:
            _index_schema(connection)
            connection.execute("ATTACH DATABASE ? AS baseline", (str(path),))
            for entry in manifest["collections"]:
                name = entry["collection"]
                _index_rows(connection, name, "source", db.iter_source(name))
                target_count = _index_rows(connection, name, "target", db.iter_target(name))
                counts = {"missing": 0, "extra": 0, "different": 0,
                          "ttl_expired_explained": 0, "unexplained_missing": 0,
                          "source_drift": 0, "source_count": entry["source_count"],
                          "target_count": target_count}
                ttl = _collection_ttl_seconds(manifest, name)
                for key, digest, fetched in connection.execute(
                    "SELECT id, digest, fetched FROM baseline.records "
                    "WHERE collection=? AND side='source'", (name,),
                ):
                    expired = (ttl is not None and fetched is not None
                               and datetime.fromisoformat(fetched) + _ttl_delta(ttl) <= observed_end)
                    for side in ("source", "target"):
                        current = connection.execute(
                            "SELECT digest FROM records WHERE collection=? AND side=? AND id=?",
                            (name, side, key),
                        ).fetchone()
                        if current is None:
                            if side == "source":
                                counts["source_drift"] += int(not expired)
                            else:
                                counts["missing"] += 1
                                counts["ttl_expired_explained"] += int(expired)
                                counts["unexplained_missing"] += int(not expired)
                        elif current[0] != digest:
                            counts["source_drift" if side == "source" else "different"] += 1
                for side in ("source", "target"):
                    extra = connection.execute(
                        "SELECT COUNT(*) FROM records live WHERE collection=? AND side=? "
                        "AND NOT EXISTS (SELECT 1 FROM baseline.records old "
                        "WHERE old.collection=live.collection AND old.side='source' AND old.id=live.id)",
                        (name, side),
                    ).fetchone()[0]
                    counts["source_drift" if side == "source" else "extra"] += extra
                counts["metadata_ok"] = (_metadata_matches(db, entry)
                                         and _metadata_matches(db, entry, target=True))
                counts["ok"] = (counts["metadata_ok"] and not any(counts[key] for key in (
                    "extra", "different", "unexplained_missing", "source_drift",
                )))
                report["collections"][name] = counts
                report["ok"] = report["ok"] and counts["ok"]
                report["drift"] = report["drift"] or bool(counts["source_drift"] or counts["different"])
    report["observed_end_utc"] = observed_end.isoformat() + "Z"
    return report


def _observed_end(manifest: dict[str, Any]) -> datetime:
    text = str(manifest.get("observed_at_utc", ""))
    if text.endswith("Z"):
        text = text[:-1]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)


def _collection_ttl_seconds(manifest: dict[str, Any], collection: str) -> int | None:
    for entry in manifest["collections"]:
        if entry["collection"] != collection:
            continue
        for index in entry.get("source_indexes", []):
            definition = index.get("definition", {})
            if "expireAfterSeconds" in definition:
                if (collection != "03_data_ud_query_audit"
                        or _ordered_index_keys(definition) != [["fetched_at", 1]]
                        or definition["expireAfterSeconds"] != 31_536_000):
                    raise MigrationError("UNSUPPORTED_TTL")
                return 31_536_000
    return None


def _ttl_expired_ids(
    db: MigrationDatabase,
    collection: str,
    ttl_seconds: int | None,
    observed_end: datetime,
) -> set[str]:
    """返回可由 TTL 自然过期解释的源 ID 集合（必须有原 fetched_at 证据）。"""
    if not ttl_seconds:
        return set()
    expired: set[str] = set()
    for document in db.iter_source(collection):
        fetched_at = document.get("fetched_at")
        if fetched_at is None:
            continue
        if fetched_at.tzinfo is not None:
            fetched_at = fetched_at.astimezone(timezone.utc).replace(tzinfo=None)
        if fetched_at + _ttl_delta(ttl_seconds) <= observed_end:
            expired.add(str(document["_id"]))
    return expired


def _ttl_delta(seconds: int):
    from datetime import timedelta

    return timedelta(seconds=seconds)


def _require_apply_evidence(db: MigrationDatabase, manifest: dict[str, Any], *,
                            write: bool = True) -> None:
    """Require finite caller facts and effective privileges; never grant roles."""
    facts = manifest.get("quiescence") or {}
    try:
        begin = datetime.fromisoformat(facts["start_utc"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(facts["end_utc"].replace("Z", "+00:00"))
        inventory = facts.get("caller_inventory")
        confirmation = facts.get("operator_confirmation")
        if (begin.utcoffset() != _ttl_delta(0) or end.utcoffset() != _ttl_delta(0)
                or begin >= end
                or facts.get("no_concurrent_ud_submissions") is not True
                or not isinstance(inventory, list) or not inventory
                or any(not isinstance(item, str) or not item.strip() for item in inventory)
                or not isinstance(confirmation, str) or not confirmation.strip()):
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise MigrationError("QUIESCENCE_NOT_VERIFIED") from None
    try:
        with timeout(10):
            status = db.source_db.command({"connectionStatus": 1, "showPrivileges": True})
        privileges = status["authInfo"]["authenticatedUserPrivileges"]
        requirements = (("tradingagents", {"find", "listCollections", "listIndexes"}),
                        ("yquant-data", {"find", "listCollections", "listIndexes",
                                         "createCollection", "createIndex", "insert"}))
        missing = []
        for database, actions in requirements:
            for name in MIGRATION_COLLECTIONS:
                granted = set()
                for privilege in privileges:
                    resource = privilege.get("resource", {})
                    if (resource.get("db") in ("", database)
                            and resource.get("collection") in ("", name)):
                        granted.update(privilege.get("actions", []))
                for action in sorted(actions - granted):
                    missing.append(database + "." + name + "/" + action)
        if missing:
            raise MigrationError("MISSING_RESOURCE_ACTION:" + ",".join(missing))
    except MigrationError:
        raise
    except Exception:
        raise MigrationError("EFFECTIVE_PRIVILEGES_UNREADABLE") from None


def copy_collections(
    db: MigrationDatabase,
    manifest: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """按 manifest 复制五个集合到目标库。

    规则（SPEC §4.2 M3/M4）：

    * 只创建**缺失**的目标集合；复现业务 options。
    * 每批 ≤1000 文档；按 ``_id`` insert-only。
    * 目标已存在且 typed canonical 完全相同 → skip。
    * 业务唯一键同值但不同 ``_id``，或相同 ``_id`` 内容不同 → 冲突
      （``MigrationError``），不覆盖、不 drop / rename。

    Args:
        db: :class:`MigrationDatabase`。
        manifest: manifest v1。
        dry_run: ``True`` 时只统计不写。

    Returns:
        ``{"inserted": n, "skipped": n, "conflicts": [...]}``。

    Raises:
        MigrationError: 目标冲突 / 未知业务 option。
    """
    path = _validate_manifest(manifest)
    if not dry_run:
        _require_apply_evidence(db, manifest)
    preflight = compare_collections(db, manifest)
    for entry in manifest["collections"]:
        name = entry["collection"]
        counts = preflight["collections"][name]
        if counts["different"]:
            raise MigrationError("SAME_ID_DIFFERENT_CONTENT")
        if counts["extra"] or counts["source_drift"] or not _metadata_matches(db, entry):
            raise MigrationError("SOURCE_DRIFT_OR_TARGET_EXTRA")
        if not _metadata_matches(db, entry, target=True, allow_missing=True):
            raise MigrationError("TARGET_METADATA_CONFLICT")
        if set(entry["source_options"]) - {
            "validator", "validationLevel", "validationAction", "collation",
        }:
            raise MigrationError("UNSUPPORTED_BUSINESS_OPTION")
        for index in entry["source_indexes"]:
            definition = index["definition"]
            if definition.get("unique") and index["name"] != "_id_":
                for document in db.iter_source(name):
                    query = {}
                    for field_name, _ in _ordered_index_keys(definition):
                        value = document
                        for component in field_name.split("."):
                            value = value.get(component) if isinstance(value, Mapping) else None
                        query[field_name] = value
                    for existing in db.target_find(name, query):
                        if _typed_id(existing["_id"]) != _typed_id(document["_id"]):
                            raise MigrationError("UNIQUE_KEY_DIFFERENT_ID")
    inserted = skipped = 0
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as baseline:
        for entry in manifest["collections"]:
            name = entry["collection"]
            if not dry_run and not db.target_has_collection(name):
                with timeout(10):
                    db.create_collection(name, entry["source_options"])
            if not dry_run:
                for index in _source_index_defs(db, name):
                    with timeout(10):
                        _ensure_target_index(db, name, index)
            pending = []
            for document in db.iter_source(name):
                original = baseline.execute(
                    "SELECT digest FROM records WHERE collection=? AND side='source' AND id=?",
                    (name, _typed_id(document["_id"])),
                ).fetchone()
                if original is None or original[0] != canonical_digest(document):
                    raise MigrationError("SOURCE_DRIFT")
                with timeout(10):
                    existing = db.target_find(name, {"_id": document["_id"]})
                if existing:
                    if len(existing) != 1 or canonical_digest(existing[0]) != original[0]:
                        raise MigrationError("SAME_ID_DIFFERENT_CONTENT")
                    skipped += 1
                    continue
                pending.append(document)
                if len(pending) == BATCH_SIZE:
                    if not dry_run:
                        with timeout(10):
                            result = db.insert_many(name, pending)
                            if not result.acknowledged:
                                raise MigrationError("UNKNOWN_ACK")
                    inserted += len(pending)
                    pending = []
            if pending:
                if not dry_run:
                    with timeout(10):
                        result = db.insert_many(name, pending)
                        if not result.acknowledged:
                            raise MigrationError("UNKNOWN_ACK")
                inserted += len(pending)
    if not dry_run and not compare_collections(db, manifest)["ok"]:
        raise MigrationError("POST_COPY_DRIFT_OR_READBACK")
    return {"inserted": inserted, "skipped": skipped, "conflicts": []}


def _source_index_defs(db: MigrationDatabase, collection: str) -> list[dict[str, Any]]:
    return [idx for idx in db.source_indexes(collection) if idx.get("name") != "_id_"]


def _ensure_target_index(
    db: MigrationDatabase, collection: str, index: dict[str, Any]
) -> None:
    """复现可移植索引（已存在同签名 → skip；属性矛盾 → STOP）。"""
    signature = index_signature(index)
    for existing in db.target_indexes(collection):
        if existing.get("name") == index.get("name"):
            if index_signature(existing) != signature:
                raise MigrationError(
                    f"index {collection}.{index.get('name')} business options differ"
                )
            return
    db.create_index(collection, index)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_ud_database",
        description="Non-destructive migration of UD collections to yquant-data.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="read-only enumeration; no DB write")
    plan.add_argument("--report-dir", required=True)

    apply_cmd = sub.add_parser("apply", help="copy collections (requires --apply)")
    apply_cmd.add_argument("--manifest", required=True)
    apply_cmd.add_argument("--apply", action="store_true")
    apply_cmd.add_argument("--report-dir", default=None)

    verify = sub.add_parser("verify", help="read-only per-id comparison")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--report-dir", default=None)
    return parser


def _open_databases() -> MigrationDatabase:
    """打开源 / 目标库（复用既有合法连接规则）。"""
    from skills.data.unified_data.storage import (
        TA_CN_DATABASE,
        UD_DATABASE,
        select_databases,
    )

    from skills.data.data_interface.mongo_reader import MongoReader

    reader = MongoReader(database=TA_CN_DATABASE)
    client = reader.db.client
    databases = select_databases(client)
    return MigrationDatabase(
        source_db=databases.ta_cn, target_db=client[UD_DATABASE]
    )


def main(argv: list[str] | None = None) -> int:
    """Validate local inputs first; BUSY/invalid apply never opens a DB connection."""
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit:
        return EXIT_FAIL
    from .ud_lock import UDLockBusy, acquire_ud_lock

    manifest: dict[str, Any] = {}
    if args.command != "plan":
        if args.command == "apply" and not args.apply:
            print("[migrate] EXIT_FAIL: EXPLICIT_APPLY_REQUIRED", file=sys.stderr)
            return EXIT_FAIL
        restored = _load_manifest(args.manifest)
        if restored is None:
            return EXIT_FAIL
        manifest = restored
    try:
        if args.command == "apply":
            with acquire_ud_lock():
                db = _open_databases()
                result = copy_collections(db, manifest)
                manifest["result"] = "applied"
                manifest["copy_counts"] = result
                _write_manifest(args.manifest, manifest)
                print("[migrate] apply ok")
            return EXIT_OK
        db = _open_databases()
        if args.command == "plan":
            report_dir = Path(args.report_dir)
            report_dir.mkdir(parents=True, exist_ok=True)
            manifest = build_manifest(db, index_dir=str(report_dir))
            _write_manifest(str(report_dir / "manifest.json"), manifest)
            print("[migrate] plan written")
            return EXIT_OK
        report = compare_collections(db, manifest)
        if args.report_dir:
            report_dir = Path(args.report_dir)
            report_dir.mkdir(parents=True, exist_ok=True)
            _write_manifest(str(report_dir / "verify.json"), report)
        if report["ok"]:
            print("[migrate] verify ok")
            return EXIT_OK
        print("[migrate] EXIT_FAIL: VERIFICATION_DIFFERENCES", file=sys.stderr)
        return EXIT_FAIL
    except UDLockBusy:
        print("[migrate] EXIT_BUSY", file=sys.stderr)
        return EXIT_BUSY
    except (KeyboardInterrupt, TimeoutError):
        print("[migrate] EXIT_TIMEOUT", file=sys.stderr)
        return EXIT_TIMEOUT
    except MigrationError as exc:
        code = str(exc)
        if not (code.startswith("MISSING_RESOURCE_ACTION:") or code in {
            "QUIESCENCE_NOT_VERIFIED", "EFFECTIVE_PRIVILEGES_UNREADABLE",
        }):
            code = "MIGRATION_FAILED"
        print(f"[migrate] EXIT_FAIL: {code}", file=sys.stderr)
        return EXIT_FAIL
    except Exception:
        print("[migrate] EXIT_FAIL: MIGRATION_FAILED", file=sys.stderr)
        return EXIT_FAIL


def _load_manifest(path: str) -> dict[str, Any] | None:
    from bson import json_util

    try:
        payload = json_util.loads(Path(path).read_text(encoding="utf-8"))
        _validate_manifest(payload)
    except Exception:
        print("[migrate] EXIT_FAIL: INVALID_MANIFEST", file=sys.stderr)
        return None
    if not isinstance(payload, dict) or payload.get("manifest_version") != MANIFEST_VERSION:
        print("[migrate] EXIT_FAIL: unsupported manifest version", file=sys.stderr)
        return None
    if payload.get("source_database") != "tradingagents" or payload.get(
        "target_database"
    ) != "yquant-data":
        print("[migrate] EXIT_FAIL: manifest source/target mismatch", file=sys.stderr)
        return None
    return payload


def _write_manifest(path: str, manifest: dict[str, Any]) -> None:
    from bson import json_util

    Path(path).write_text(json_util.dumps(
        manifest, json_options=json_util.CANONICAL_JSON_OPTIONS, indent=2, sort_keys=True,
    ), encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "BATCH_SIZE",
    "EXIT_BUSY",
    "EXIT_FAIL",
    "EXIT_OK",
    "EXIT_PARTIAL",
    "EXIT_TIMEOUT",
    "MANIFEST_VERSION",
    "MIGRATION_COLLECTIONS",
    "OWNERSHIP_EVIDENCE",
    "MigrationDatabase",
    "MigrationError",
    "build_manifest",
    "canonical_digest",
    "compare_collections",
    "copy_collections",
    "index_signature",
    "main",
]
