"""Offline tests for Gate-2 (gate2_ddl.py) — 03-016 rollout.

DESIGN-03-016 V0.4 §3.5 / SPEC-03-016 §3.3. All tests run against
mongomock with explicit ``client_factory`` / ``env`` injection —
**zero environment reads and zero real I/O** (CL-5).

本数据为辅助研究数据，不构成交易指令或投资建议。
"""

from __future__ import annotations

import json
from typing import Any

import mongomock
import pytest

from scripts.unified_data.sector_ranking_rollout.common import (
    EXIT_CONN,
    EXIT_OK,
    EXIT_PARAM,
    EXIT_STOP,
    EXIT_VERIFY,
)
from scripts.unified_data.sector_ranking_rollout.gate2_ddl import (
    ALLOWED_COLLECTION,
    INDEX_KEY,
    INDEX_NAME,
    Gate2Stop,
    build_report,
    execute_ddl,
    index_spec_matches,
    main,
    post_verify,
    pre_verify,
)

TEST_ENV = {
    "MONGODB_HOST": "mongo-host-1",
    "MONGODB_PORT": "27017",
    "MONGODB_USERNAME": "svc-user",
    "MONGODB_PASSWORD": "svc-pass-123",
    "MONGODB_DATABASE": "tradingagents",
}


class _ClientShim:
    def __init__(self, db) -> None:
        self._db = db

    def get_database(self, name: str):
        return self._db


def _fresh_db() -> Any:
    return mongomock.MongoClient().get_database("tradingagents")


class TestIndexSpec:
    def test_index_spec_matches_created_index(self):
        db = _fresh_db()
        coll = db[ALLOWED_COLLECTION]
        coll.create_index(INDEX_KEY, unique=True, name=INDEX_NAME, background=False)
        info = coll.index_information()
        assert index_spec_matches(info, INDEX_NAME) is True

    def test_index_spec_mismatch_when_unique_false(self):
        db = _fresh_db()
        coll = db[ALLOWED_COLLECTION]
        coll.create_index(INDEX_KEY, unique=False, name=INDEX_NAME)
        info = coll.index_information()
        assert index_spec_matches(info, INDEX_NAME) is False

    def test_index_spec_mismatch_when_key_differs(self):
        db = _fresh_db()
        coll = db[ALLOWED_COLLECTION]
        coll.create_index([("dataset", 1)], unique=True, name=INDEX_NAME)
        info = coll.index_information()
        assert index_spec_matches(info, INDEX_NAME) is False

    def test_index_spec_missing_when_absent(self):
        assert index_spec_matches({}, INDEX_NAME) is False


class TestPreVerify:
    def test_pre_verify_passes_on_empty_db(self):
        db = _fresh_db()
        assert pre_verify(db, ALLOWED_COLLECTION) is None

    def test_pre_verify_skips_when_collection_exists_with_matching_index(self):
        db = _fresh_db()
        coll = db[ALLOWED_COLLECTION]
        coll.create_index(INDEX_KEY, unique=True, name=INDEX_NAME, background=False)
        assert pre_verify(db, ALLOWED_COLLECTION) is None

    def test_pre_verify_stops_on_index_mismatch(self):
        db = _fresh_db()
        coll = db[ALLOWED_COLLECTION]
        coll.create_index(INDEX_KEY, unique=False, name=INDEX_NAME)
        with pytest.raises(Gate2Stop) as exc:
            pre_verify(db, ALLOWED_COLLECTION)
        assert exc.value.sc_id == "G2-S-003"
        assert exc.value.exit_code == EXIT_STOP

    def test_pre_verify_fails_when_db_unreachable(self):
        class BrokenDB:
            def list_collection_names(self):
                raise RuntimeError("db unreachable")

        with pytest.raises(Gate2Stop) as exc:
            pre_verify(BrokenDB(), ALLOWED_COLLECTION)
        assert exc.value.sc_id == "G2-S-002"
        assert exc.value.exit_code == EXIT_VERIFY


class TestExecuteDdl:
    def test_execute_creates_collection_and_index(self):
        db = _fresh_db()
        actions = execute_ddl(db, ALLOWED_COLLECTION)
        assert "create_collection" in actions
        assert "create_index" in actions
        coll = db[ALLOWED_COLLECTION]
        info = coll.index_information()
        assert index_spec_matches(info, INDEX_NAME) is True

    def test_execute_is_idempotent(self):
        db = _fresh_db()
        execute_ddl(db, ALLOWED_COLLECTION)
        actions2 = execute_ddl(db, ALLOWED_COLLECTION)
        assert "create_collection" not in actions2
        assert "create_index" not in actions2
        coll = db[ALLOWED_COLLECTION]
        assert index_spec_matches(coll.index_information(), INDEX_NAME) is True

    def test_execute_does_not_create_query_aux_index(self):
        db = _fresh_db()
        execute_ddl(db, ALLOWED_COLLECTION)
        info = db[ALLOWED_COLLECTION].index_information()
        assert "idx_dataset_date" not in info


class TestPostVerify:
    def test_post_verify_ok_after_execute(self):
        db = _fresh_db()
        execute_ddl(db, ALLOWED_COLLECTION)
        assert post_verify(db, ALLOWED_COLLECTION, pre_names=[]) is None

    def test_post_verify_detects_index_mismatch(self):
        db = _fresh_db()
        coll = db[ALLOWED_COLLECTION]
        coll.create_index([("dataset", 1)], unique=False, name=INDEX_NAME)
        with pytest.raises(Gate2Stop) as exc:
            post_verify(db, ALLOWED_COLLECTION, pre_names=[])
        assert exc.value.sc_id == "G2-S-002"
        assert exc.value.exit_code == EXIT_VERIFY

    def test_post_verify_detects_foreign_collection_created(self):
        db = _fresh_db()
        execute_ddl(db, ALLOWED_COLLECTION)
        db["portfolio_position"].insert_one({"x": 1})
        with pytest.raises(Gate2Stop) as exc:
            post_verify(db, ALLOWED_COLLECTION, pre_names=[])
        assert exc.value.sc_id == "G2-S-005"
        assert exc.value.exit_code == EXIT_STOP


class TestGate2Main:
    def test_dry_run_returns_zero_without_connection(self, tmp_path):
        rc = main(["--report-dir", str(tmp_path)])
        assert rc == EXIT_OK
        assert not (tmp_path / "gate2-report.json").exists()

    def test_apply_without_yes_is_dry_run(self, tmp_path):
        rc = main(
            ["--apply", "--report-dir", str(tmp_path)],
            client_factory=mongomock.MongoClient,
            env=TEST_ENV,
        )
        assert rc == EXIT_OK

    def test_apply_missing_env_key_exit_3(self, tmp_path):
        env = {k: v for k, v in TEST_ENV.items() if k != "MONGODB_PORT"}
        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=mongomock.MongoClient,
            env=env,
        )
        assert rc == EXIT_CONN

    def test_apply_creates_ddl_and_writes_report(self, tmp_path):
        db = _fresh_db()
        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
        )
        assert rc == EXIT_OK
        assert ALLOWED_COLLECTION in db.list_collection_names()
        info = db[ALLOWED_COLLECTION].index_information()
        assert index_spec_matches(info, INDEX_NAME) is True
        payload = json.loads((tmp_path / "gate2-report.json").read_text())
        assert payload["stop_conditions_hit"] == []
        assert payload["collection"] == ALLOWED_COLLECTION

    def test_apply_second_run_is_idempotent(self, tmp_path):
        db = _fresh_db()
        rc1 = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
        )
        rc2 = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
        )
        assert rc1 == EXIT_OK
        assert rc2 == EXIT_OK
        info = db[ALLOWED_COLLECTION].index_information()
        assert index_spec_matches(info, INDEX_NAME) is True

    def test_apply_index_mismatch_stops_exit_2(self, tmp_path):
        db = _fresh_db()
        db[ALLOWED_COLLECTION].create_index(
            INDEX_KEY, unique=False, name=INDEX_NAME
        )
        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
        )
        assert rc == EXIT_STOP
        payload = json.loads((tmp_path / "gate2-report.json").read_text())
        assert "G2-S-003" in payload["stop_conditions_hit"]

    def test_apply_namespace_violation_exit_2(self, tmp_path):
        db = _fresh_db()
        rc = main(
            ["--apply", "--yes", "--collection", "other_collection",
             "--report-dir", str(tmp_path)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
        )
        assert rc == EXIT_STOP
        assert "other_collection" not in db.list_collection_names()
        payload = json.loads((tmp_path / "gate2-report.json").read_text())
        assert "G2-S-004" in payload["stop_conditions_hit"]

    def test_apply_detects_foreign_collection_created_exit_2(self, tmp_path, monkeypatch):
        import scripts.unified_data.sector_ranking_rollout.gate2_ddl as gate2

        db = _fresh_db()

        def _rogue_execute(database, collection):
            actions = execute_ddl(database, collection)
            database["portfolio_position"].insert_one({"x": 1})  # 越权新建
            return actions

        monkeypatch.setattr(gate2, "execute_ddl", _rogue_execute)
        rc = main(
            ["--apply", "--yes", "--report-dir", str(tmp_path)],
            client_factory=lambda **kwargs: _ClientShim(db),
            env=TEST_ENV,
        )
        assert rc == EXIT_STOP
        payload = json.loads((tmp_path / "gate2-report.json").read_text())
        assert "G2-S-005" in payload["stop_conditions_hit"]
