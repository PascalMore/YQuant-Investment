"""UD 迁移测试 — 03-018 UT01–UT03。

覆盖：五集合（含空集合）、typed _id / BSON / fetched_at / options / index
完整性、同 _id 不同内容 / 唯一键冲突 / 未知归属拒绝、并发非 TTL 漂移
失败、严格过期子集归因。
"""

from __future__ import annotations

from datetime import datetime

import mongomock
import pytest
from bson import Decimal128, Int64, ObjectId

from scripts.unified_data.migrate_ud_database import (
    MIGRATION_COLLECTIONS,
    MigrationDatabase,
    MigrationError,
    _ttl_expired_ids,
    build_manifest as _build_manifest,
    canonical_digest,
    compare_collections,
    copy_collections,
    index_signature,
)


@pytest.fixture(autouse=True)
def fake_metadata_commands(monkeypatch):
    """Only the Mongo command boundary is faked; guard logic remains real."""
    def command(database, spec, **kwargs):
        if "listCollections" in spec:
            name = spec["filter"]["name"]
            return {"cursor": {"firstBatch": [{"name": name, "options": {}}]}}
        if "connectionStatus" in spec:
            return {"authInfo": {"authenticatedUserPrivileges": [
                {"resource": {"db": database_name, "collection": name},
                 "actions": ["find", "listCollections", "listIndexes", "createCollection",
                             "createIndex", "insert"]}
                for database_name in ("tradingagents", "yquant-data")
                for name in MIGRATION_COLLECTIONS
            ]}}
        raise AssertionError("unexpected command")
    monkeypatch.setattr(mongomock.database.Database, "command", command)


def build_manifest(db, **kwargs):
    """Attach clearly synthetic finite-writer facts for this fake-only test suite."""
    manifest = _build_manifest(db, **kwargs)
    manifest["quiescence"] = {
        "start_utc": "2026-08-10T00:00:00Z",
        "end_utc": "2026-08-10T02:00:00Z",
        "no_concurrent_ud_submissions": True,
        "caller_inventory": ["synthetic in-process mongomock only"],
        "operator_confirmation": "synthetic fixture, NOT production evidence",
    }
    return manifest


class _FixedSource:
    """固定文档序列的源库替身（避免 mongomock 的 TTL 删除模拟）。"""

    def __init__(self, documents: list[dict]) -> None:
        self._documents = documents

    def __getitem__(self, name: str):
        return self

    def find(self, *args, **kwargs):
        collection = mongomock.MongoClient()["synthetic"]["records"]
        collection.insert_many(self._documents)
        return collection.find({})

    def list_collection_names(self):
        return ["03_data_ud_query_audit"]

    def count_documents(self, *args, **kwargs):
        return len(self._documents)


def _index_keys(index: dict) -> list[tuple[str, int]]:
    """返回有序的索引键（mongomock 返回 dict，pymongo 返回 tuple 列表）。"""
    raw = index.get("key") or {}
    if isinstance(raw, dict):
        return [(str(name), int(direction)) for name, direction in raw.items()]
    return [(str(name), int(direction)) for name, direction in raw]

UTC = datetime(2026, 8, 10, 1, 0, 0)


def _source_db() -> mongomock.MongoClient:
    client = mongomock.MongoClient()
    db = client["tradingagents"]
    db["03_data_ud_sector_ranking_daily"].insert_many(
        [
            {
                "_id": "2026-08-10:sw2021_ta_cn:801010",
                "dataset": "sw2021_ta_cn",
                "trade_date": "2026-08-10",
                "sector_code": "801010",
                "pct_chg": Decimal128("1.25"),
                "fetched_at": UTC,
            }
        ]
    )
    db["03_data_ud_sector_ranking_daily"].create_index(
        [("dataset", 1), ("trade_date", -1), ("sector_code", 1)],
        name="uniq_dataset_date_sector",
        unique=True,
    )
    db["03_data_ud_query_audit"].insert_one(
        {
            "_id": ObjectId("64b0000000000000000000a1"),
            "audit_id": "a1",
            "fetched_at": UTC,
            "duration_ms": Int64(12),
        }
    )
    db["03_data_ud_query_audit"].create_index(
        [("fetched_at", 1)],
        name="fetched_at_ttl",
        expireAfterSeconds=31536000,
    )
    # 三个空集合也必须被创建 / 校验
    for name in (
        "03_data_ud_market_sector_snapshot",
        "03_data_ud_market_sentiment_snapshot",
        "03_data_ud_stock_capital_flow",
    ):
        db.create_collection(name)
    return client


def _databases() -> MigrationDatabase:
    """构造源 / 目标句柄（同一个 client 的两个命名库）。"""
    client = mongomock.MongoClient()
    source = client["tradingagents"]
    target = client["yquant-data"]
    for name in MIGRATION_COLLECTIONS:
        if name not in source.list_collection_names():
            source.create_collection(name)
    return MigrationDatabase(source_db=source, target_db=target)


def _seeded_databases() -> MigrationDatabase:
    """构造带源数据的源 / 目标句柄（同一个 client）。"""
    client = mongomock.MongoClient()
    source = client["tradingagents"]
    target = client["yquant-data"]
    source["03_data_ud_sector_ranking_daily"].insert_many(
        [
            {
                "_id": "2026-08-10:sw2021_ta_cn:801010",
                "dataset": "sw2021_ta_cn",
                "trade_date": "2026-08-10",
                "sector_code": "801010",
                "pct_chg": Decimal128("1.25"),
                "fetched_at": UTC,
            }
        ]
    )
    source["03_data_ud_sector_ranking_daily"].create_index(
        [("dataset", 1), ("trade_date", -1), ("sector_code", 1)],
        name="uniq_dataset_date_sector",
        unique=True,
    )
    source["03_data_ud_query_audit"].insert_one(
        {
            "_id": ObjectId("64b0000000000000000000a1"),
            "audit_id": "a1",
            "fetched_at": UTC,
            "duration_ms": Int64(12),
        }
    )
    source["03_data_ud_query_audit"].create_index(
        [("fetched_at", 1)],
        name="fetched_at_ttl",
        expireAfterSeconds=31536000,
    )
    for name in (
        "03_data_ud_market_sector_snapshot",
        "03_data_ud_market_sentiment_snapshot",
        "03_data_ud_stock_capital_flow",
    ):
        source.create_collection(name)
    return MigrationDatabase(source_db=source, target_db=target)


# ---------------------------------------------------------------------------
# UT01 — 五集合（含空）与类型保真
# ---------------------------------------------------------------------------


def test_ut01_manifest_covers_five_collections_including_empty() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db)
    names = [entry["collection"] for entry in manifest["collections"]]
    assert names == list(MIGRATION_COLLECTIONS)
    counts = {entry["collection"]: entry["source_count"] for entry in manifest["collections"]}
    assert counts["03_data_ud_market_sector_snapshot"] == 0
    assert counts["03_data_ud_sector_ranking_daily"] == 1


def test_ut01_plan_does_not_write_to_the_target() -> None:
    db = _seeded_databases()
    build_manifest(db)
    assert db.target_db.list_collection_names() == []
    assert "createCollection" not in db.target_commands


def test_ut01_copy_preserves_typed_id_and_bson_types() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db)
    copy_collections(db, manifest)
    doc = db.target_db["03_data_ud_sector_ranking_daily"].find_one({})
    assert isinstance(doc["_id"], str)
    assert isinstance(doc["pct_chg"], Decimal128)
    assert doc["fetched_at"] == UTC
    audit = db.target_db["03_data_ud_query_audit"].find_one({})
    assert isinstance(audit["_id"], ObjectId)
    assert isinstance(audit["duration_ms"], Int64)


def test_ut01_copy_preserves_index_direction_and_ttl() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db)
    copy_collections(db, manifest)
    ranking_indexes = {
        index["name"]: index
        for index in db.target_db["03_data_ud_sector_ranking_daily"].list_indexes()
    }
    assert "uniq_dataset_date_sector" in ranking_indexes
    # mongomock returns the key as a dict; the direction / order must still be
    # the business one (dataset +1, trade_date -1, sector_code +1).
    assert _index_keys(ranking_indexes["uniq_dataset_date_sector"]) == [
        ("dataset", 1),
        ("trade_date", -1),
        ("sector_code", 1),
    ]
    audit_indexes = {
        index["name"]: index
        for index in db.target_db["03_data_ud_query_audit"].list_indexes()
    }
    assert audit_indexes["fetched_at_ttl"]["expireAfterSeconds"] == 31536000


def test_ut01_empty_collections_are_created_with_options() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db)
    copy_collections(db, manifest)
    for name in (
        "03_data_ud_market_sector_snapshot",
        "03_data_ud_market_sentiment_snapshot",
        "03_data_ud_stock_capital_flow",
    ):
        assert name in db.target_db.list_collection_names()


def test_ut01_index_signature_ignores_server_metadata() -> None:
    left = {"name": "i", "key": [("a", 1)], "v": 2, "ns": "db.coll"}
    right = {"name": "i", "key": [("a", 1)], "v": 5, "ns": "db.other"}
    assert index_signature(left) == index_signature(right)


def test_ut01_index_signature_keeps_key_order() -> None:
    left = {"name": "i", "key": [("a", 1), ("b", -1)]}
    right = {"name": "i", "key": [("b", -1), ("a", 1)]}
    assert index_signature(left) != index_signature(right)


# ---------------------------------------------------------------------------
# UT02 — 冲突与未知归属
# ---------------------------------------------------------------------------


def test_ut02_same_id_different_content_is_a_conflict() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db)
    db.target_db["03_data_ud_sector_ranking_daily"].insert_one(
        {
            "_id": "2026-08-10:sw2021_ta_cn:801010",
            "dataset": "sw2021_ta_cn",
            "trade_date": "2026-08-10",
            "sector_code": "801010",
            "pct_chg": Decimal128("9.99"),
            "fetched_at": UTC,
        }
    )
    with pytest.raises(MigrationError) as excinfo:
        copy_collections(db, manifest)
    assert "SAME_ID_DIFFERENT_CONTENT" in str(excinfo.value)
    # 源不被修改
    assert db.source_db["03_data_ud_sector_ranking_daily"].count_documents({}) == 1


def test_ut02_unknown_ud_collection_stops_the_plan() -> None:
    db = _seeded_databases()
    db.source_db["03_data_ud_unknown_thing"].insert_one({"_id": 1})
    with pytest.raises(MigrationError) as excinfo:
        build_manifest(db)
    assert "03_data_ud_unknown_thing" in str(excinfo.value)


def test_ut02_source_is_never_written() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db)
    copy_collections(db, manifest)
    assert set(db.source_commands) <= {
        "listCollectionNames",
        "listCollections",
        "listIndexes",
        "find",
        "countDocuments",
    }


def test_ut02_target_only_receives_allowed_commands() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db)
    copy_collections(db, manifest)
    assert set(db.target_commands) <= {
        "listCollectionNames",
        "listCollections",
        "listIndexes",
        "createCollection",
        "createIndex",
        "insert",
        "find",
    }


def test_ut02_identical_document_is_skipped() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db)
    copy_collections(db, manifest)
    result = copy_collections(db, manifest)
    assert result["inserted"] == 0
    assert result["skipped"] == 2


# ---------------------------------------------------------------------------
# UT03 — 漂移与 TTL 归因
# ---------------------------------------------------------------------------


def test_ut03_verification_reports_missing_and_extra() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db)
    copy_collections(db, manifest)
    db.target_db["03_data_ud_sector_ranking_daily"].delete_one({})
    db.target_db["03_data_ud_query_audit"].insert_one({"_id": "extra"})
    report = compare_collections(db, manifest)
    assert report["ok"] is False
    assert report["collections"]["03_data_ud_sector_ranking_daily"]["missing"] == 1
    assert report["collections"]["03_data_ud_query_audit"]["extra"] == 1


def test_ut03_different_content_is_reported() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db)
    copy_collections(db, manifest)
    db.target_db["03_data_ud_sector_ranking_daily"].update_one(
        {}, {"$set": {"pct_chg": Decimal128("7.77")}}
    )
    report = compare_collections(db, manifest)
    assert report["ok"] is False
    assert report["collections"]["03_data_ud_sector_ranking_daily"]["different"] == 1


def test_ut03_expired_ids_are_detected_from_fetched_at() -> None:
    """``fetched_at + TTL <= 观察结束`` 的源 ID 属于自然过期子集。

    NOTE: mongomock emulates TTL deletion once a TTL index exists, so the
    expired document is removed from the fake source itself. The attribution
    helper is therefore exercised against a fixed source stub (the production
    server keeps the document until the TTL monitor actually removes it).
    """
    db = _seeded_databases()
    db.source_db = _FixedSource(
        [
            {
                "_id": "expired-1",
                "audit_id": "e1",
                "fetched_at": datetime(2020, 1, 1),
            },
            {
                "_id": "live-1",
                "audit_id": "e2",
                "fetched_at": datetime(2026, 8, 10, 1),
            },
        ]
    )
    expired = _ttl_expired_ids(
        db, "03_data_ud_query_audit", 31536000, datetime(2026, 8, 10, 2, 0, 0)
    )
    assert expired == {"expired-1"}


def test_ut03_expired_ttl_subset_is_attributed(monkeypatch) -> None:
    """A vanished source ID is explained by its saved original time, not a mocked verdict."""
    db = _seeded_databases()
    name = "03_data_ud_query_audit"
    original = db.source_db[name].find_one({})
    original["fetched_at"] = datetime(2020, 1, 1)
    iterate = db.iter_source
    monkeypatch.setattr(db, "iter_source", lambda collection: (
        iter([original]) if collection == name else iterate(collection)
    ))
    manifest = build_manifest(db)
    copy_collections(db, manifest)
    db.target_db[name].delete_one({})
    monkeypatch.setattr(db, "iter_source", lambda collection: (
        iter([]) if collection == name else iterate(collection)
    ))
    report = compare_collections(db, manifest)
    entry = report["collections"][name]
    assert entry["ttl_expired_explained"] == 1
    assert entry["unexplained_missing"] == 0
    assert entry["source_drift"] == 0
    assert report["ok"] is True


def test_ut03_unexpired_difference_fails() -> None:
    db = _seeded_databases()
    manifest = build_manifest(db, observed_at=datetime(2026, 8, 10, 2, 0, 0))
    copy_collections(db, manifest)
    db.target_db["03_data_ud_query_audit"].delete_one({})
    report = compare_collections(db, manifest)
    entry = report["collections"]["03_data_ud_query_audit"]
    assert entry["unexplained_missing"] == 1
    assert report["ok"] is False


def test_ut03_canonical_digest_distinguishes_bson_types() -> None:
    left = {"_id": 1, "value": Int64(5)}
    right = {"_id": 1, "value": 5}
    assert canonical_digest(left) != canonical_digest(right)


def test_ut01_nested_objects_sorted_but_arrays_and_index_keys_ordered():
    assert canonical_digest({"b": {"d": 1, "c": 2}, "a": 0}) == canonical_digest(
        {"a": 0, "b": {"c": 2, "d": 1}}
    )
    assert canonical_digest([1, 2]) != canonical_digest([2, 1])
    assert index_signature({"name": "nested", "key": [("b", 1), ("a", -1)],
                            "partialFilterExpression": {"z": 1, "a": 2}}) == index_signature(
        {"partialFilterExpression": {"a": 2, "z": 1}, "key": [("b", 1), ("a", -1)],
         "name": "nested"}
    )


def test_ut01_typed_id_sqlite_index_keeps_string_and_objectid_distinct():
    import sqlite3

    db = _databases()
    name = MIGRATION_COLLECTIONS[0]
    identifier = ObjectId()
    db.source_db[name].insert_many([{"_id": identifier}, {"_id": str(identifier)}])
    manifest = build_manifest(db)
    with sqlite3.connect(manifest["digest_index_ref"]) as connection:
        assert connection.execute("SELECT count(*) FROM records WHERE side='source'").fetchone()[0] == 2
    assert "source_digests" not in manifest["collections"][0]
    copy_collections(db, manifest)
    assert compare_collections(db, manifest)["ok"]
    assert db.target_db[name].count_documents({}) == 2


@pytest.mark.parametrize("failure", ["quiescence", "privileges", "source_update", "source_delete",
                                    "extra_target", "last_index", "manifest", "index_bytes"])
def test_ut02_all_preflight_failures_have_zero_writes(failure, monkeypatch):
    db = _seeded_databases()
    manifest = build_manifest(db)
    if failure == "quiescence":
        manifest["quiescence"] = None
    elif failure == "privileges":
        old_command = db.source_db.command
        monkeypatch.setattr(db.source_db, "command", lambda spec, **kwargs: (
            {"authInfo": {"authenticatedUserPrivileges": []}} if "connectionStatus" in spec
            else old_command(spec, **kwargs)
        ))
    elif failure == "source_update":
        db.source_db[MIGRATION_COLLECTIONS[0]].update_one({}, {"$set": {"pct_chg": Decimal128("8")}})
    elif failure == "source_delete":
        db.source_db[MIGRATION_COLLECTIONS[0]].delete_one({})
    elif failure == "extra_target":
        db.target_db[MIGRATION_COLLECTIONS[-1]].insert_one({"_id": "extra"})
    elif failure == "last_index":
        db.target_db[MIGRATION_COLLECTIONS[-1]].create_index([("extra", 1)], name="conflict")
    elif failure == "manifest":
        manifest["collections"][0]["source_count"] += 1
    elif failure == "index_bytes":
        with open(manifest["digest_index_ref"], "ab") as handle:
            handle.write(b"synthetic corruption")
    db.target_commands.clear()
    with pytest.raises(MigrationError):
        copy_collections(db, manifest)
    assert not {"createCollection", "createIndex", "insert"} & set(db.target_commands)


def test_ut03_source_change_during_insert_is_detected(monkeypatch):
    db = _seeded_databases()
    manifest = build_manifest(db)
    insert = db.insert_many

    def changing_insert(name, documents):
        result = insert(name, documents)
        db.source_db[MIGRATION_COLLECTIONS[0]].update_one({}, {"$set": {"changed": True}})
        return result

    monkeypatch.setattr(db, "insert_many", changing_insert)
    with pytest.raises(MigrationError, match="POST_COPY_DRIFT"):
        copy_collections(db, manifest)
    assert db.target_db[MIGRATION_COLLECTIONS[0]].find_one({}).get("changed") is None


def test_ut02_missing_apply_flag_is_zero_db(monkeypatch):
    from scripts.unified_data import migrate_ud_database as migration

    monkeypatch.setattr(migration, "_open_databases", lambda: pytest.fail("DB opened"))
    assert migration.main(["apply", "--manifest", "not-read.json"]) == 20


def test_ut01_manifest_roundtrip_keeps_bson_and_order(tmp_path):
    from scripts.unified_data import migrate_ud_database as migration

    db = _seeded_databases()
    manifest = build_manifest(db)
    path = tmp_path / "manifest.json"
    migration._write_manifest(str(path), manifest)
    restored = migration._load_manifest(str(path))
    assert restored is not None
    copy_collections(db, restored)
    assert compare_collections(db, restored)["ok"]


def test_finite_quiescence_needs_no_global_proof_or_freshness_token():
    db = _seeded_databases()
    manifest = build_manifest(db)
    assert set(manifest["quiescence"]) == {
        "start_utc", "end_utc", "caller_inventory", "operator_confirmation",
        "no_concurrent_ud_submissions",
    }
    assert copy_collections(db, manifest)["inserted"] == 2
    assert compare_collections(db, manifest)["ok"]


@pytest.mark.parametrize("field,value", [
    ("operator_confirmation", " "), ("operator_confirmation", True),
    ("caller_inventory", []), ("caller_inventory", "not a list"),
    ("caller_inventory", [""]), ("no_concurrent_ud_submissions", False),
    ("start_utc", "2026-08-10T00:00:00"),
    ("end_utc", "2026-08-09T00:00:00Z"),
    ("end_utc", "2026-08-10T02:00:00+08:00"),
])
def test_missing_or_invalid_window_facts_are_zero_write(field, value):
    db = _seeded_databases()
    manifest = build_manifest(db)
    manifest["quiescence"][field] = value
    with pytest.raises(MigrationError, match="QUIESCENCE_NOT_VERIFIED"):
        copy_collections(db, manifest)
    assert not {"createCollection", "createIndex", "insert"} & set(db.target_commands)


def test_cli_reports_exact_missing_namespace_actions_without_identity(monkeypatch, capsys):
    from scripts.unified_data import migrate_ud_database as migration

    db = _seeded_databases()
    manifest = build_manifest(db)
    command = db.source_db.command

    def missing_insert(spec, **kwargs):
        status = command(spec, **kwargs)
        if "connectionStatus" in spec:
            status["authInfo"]["authenticatedUsers"] = [{"user": "synthetic-private-identity"}]
            for privilege in status["authInfo"]["authenticatedUserPrivileges"]:
                if privilege["resource"]["db"] == "yquant-data":
                    privilege["actions"].remove("insert")
        return status

    monkeypatch.setattr(db.source_db, "command", missing_insert)
    monkeypatch.setattr(migration, "_load_manifest", lambda path: manifest)
    monkeypatch.setattr(migration, "_open_databases", lambda: db)
    assert migration.main(["apply", "--manifest", "synthetic", "--apply"]) == 20
    output = capsys.readouterr().err
    for name in MIGRATION_COLLECTIONS:
        assert "yquant-data." + name + "/insert" in output
    assert "synthetic-private-identity" not in output
    assert "MIGRATION_FAILED" not in output
    assert not {"createCollection", "createIndex", "insert"} & set(db.target_commands)


def test_unreadable_privileges_report_classification_only(monkeypatch, capsys):
    from scripts.unified_data import migrate_ud_database as migration

    db = _seeded_databases()
    manifest = build_manifest(db)

    def unreadable(*args, **kwargs):
        raise RuntimeError("synthetic-secret-uri")

    monkeypatch.setattr(db.source_db, "command", unreadable)
    monkeypatch.setattr(migration, "_load_manifest", lambda path: manifest)
    monkeypatch.setattr(migration, "_open_databases", lambda: db)
    assert migration.main(["apply", "--manifest", "synthetic", "--apply"]) == 20
    output = capsys.readouterr().err
    assert "EFFECTIVE_PRIVILEGES_UNREADABLE" in output
    assert "synthetic-secret-uri" not in output
    assert not {"createCollection", "createIndex", "insert"} & set(db.target_commands)
