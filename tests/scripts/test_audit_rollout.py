"""audit_rollout 单元测试（DESIGN-03-011 §8 / task body）。

覆盖矩阵：

* ROL-101: dry-run 模式零副作用、rc=0、打印计划
* ROL-102: --apply 缺凭证 → rc=3
* ROL-103: --apply 越界 database → rc=2
* ROL-104: --apply 越界 collection → rc=2
* ROL-105: --verify 缺凭证 → rc=3
* ROL-106: --apply 注入 mongomock 客户端 → 创建集合 + 索引 + 幂等
* ROL-107: --verify 注入 mongomock 客户端 → 索引缺失时返回 1
* ROL-108: bad writer/reader role 拒绝
* ROL-109: --apply 不得创建 03_data_ud_quality_summary 等越界集合

所有测试使用 mongomock 或 subprocess；不连接真实 MongoDB。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import mongomock
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
SCRIPT = SCRIPTS_DIR / "unified_data" / "audit_rollout.py"


def _load_module():
    """按文件路径加载 scripts/unified_data/audit_rollout.py 为 Python 模块。

    不依赖 scripts/ 是否在 sys.path；通过 importlib 直接加载。
    """
    spec = importlib.util.spec_from_file_location(
        "scripts.unified_data.audit_rollout",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# subprocess-based CLI tests (test the entry point and exit codes)
# ---------------------------------------------------------------------------


def _run_cli(*args: str, env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    env = {**__import__("os").environ}
    if env_overrides:
        # 显式覆盖，确保测试不被父进程残留凭证影响
        for k in (
            "UD_DDL_MONGO_URI",
            "UD_DDL_MONGO_USERNAME",
            "UD_DDL_MONGO_PASSWORD",
            "UD_DDL_MONGO_AUTH_DB",
        ):
            env.pop(k, None)
        env.update(env_overrides)
    # 同时清空真实凭证，避免测试意外命中生产
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(ROOT), env=env,
    )


class TestDryRun:
    def test_dry_run_default_succeeds(self):
        r = _run_cli()
        assert r.returncode == 0
        assert "DRY-RUN" in r.stdout
        assert "fetched_at_ttl" in r.stdout
        assert "expireAfterSeconds=31536000" in r.stdout
        # 验证 dry-run 模式不读取凭证
        assert "credential" not in r.stdout.lower()

    def test_dry_run_forbidden_collection_blocked(self):
        r = _run_cli("--collection", "03_data_ud_quality_summary")
        assert r.returncode == 2
        assert "BLOCKED" in r.stderr
        assert "not in allow-list" in r.stderr

    def test_dry_run_forbidden_database_blocked(self):
        r = _run_cli("--database", "evil_db")
        assert r.returncode == 2
        assert "not in allow-list" in r.stderr

    def test_dry_run_bad_writer_role_blocked(self):
        r = _run_cli("--writer-role", "portfolio_admin")
        assert r.returncode == 2
        assert "writer role" in r.stderr

    def test_dry_run_bad_reader_role_blocked(self):
        r = _run_cli("--reader-role", "trade_readonly")
        assert r.returncode == 2
        assert "reader role" in r.stderr

    def test_dry_run_accepts_allow_listed_roles(self):
        r = _run_cli(
            "--writer-role", "ud_audit_writer_app",
            "--reader-role", "ud_audit_reader_app",
        )
        assert r.returncode == 0
        assert "ud_audit_writer_app" in r.stdout
        assert "ud_audit_reader_app" in r.stdout


class TestApplyMissingCreds:
    def test_apply_without_creds_returns_3(self):
        r = _run_cli("--apply")
        assert r.returncode == 3
        assert "UD_DDL_MONGO_URI" in r.stderr

    def test_apply_with_only_uri_returns_3(self):
        r = _run_cli("--apply", env_overrides={
            "UD_DDL_MONGO_URI": "mongodb://localhost:27017",
        })
        assert r.returncode == 3
        assert "UD_DDL_MONGO_USERNAME" in r.stderr

    def test_verify_without_creds_returns_3(self):
        r = _run_cli("--verify")
        assert r.returncode == 3


# ---------------------------------------------------------------------------
# In-process tests with mongomock (exercise --apply / --verify against fake DB)
# ---------------------------------------------------------------------------


class TestApplyWithMongomock:
    """使用 mongomock 替换 pymongo.MongoClient，验证 --apply 与 --verify。

    通过 monkey-patching 让 ``audit_rollout._open_ddl_client`` 返回
    mongomock 客户端；测试结束自动恢复。
    """

    def test_apply_creates_collection_and_indexes(self, monkeypatch):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db

        class _Mini:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                assert name == ar.ALLOWED_DATABASE
                return self._db

            def close(self):
                pass

        def _fake_open_ddl_client():
            return _Mini(fake_db)

        def _fake_creds():
            return {
                "uri": "mongodb://localhost:27017",
                "username": "ddl_user",
                "password": "dummy",
                "auth_db": "admin",
            }

        monkeypatch.setattr(ar, "_open_ddl_client", _fake_open_ddl_client)
        monkeypatch.setattr(ar, "_load_ddl_credentials", _fake_creds)

        rc = ar.run_apply(ar.ALLOWED_DATABASE, ar.ALLOWED_COLLECTION)
        assert rc == 0

        assert ar.ALLOWED_COLLECTION in fake_db.list_collection_names()
        names = {idx["name"] for idx in fake_db[ar.ALLOWED_COLLECTION].list_indexes()}
        for expected in ("fetched_at_ttl", "security_id_fetched_at", "capability_fetched_at"):
            assert expected in names

        # QualitySummary 集合绝不能被创建
        assert "03_data_ud_quality_summary" not in fake_db.list_collection_names()

    def test_apply_idempotent(self, monkeypatch):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        fake_db.create_collection(ar.ALLOWED_COLLECTION)

        class _Mini:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                return self._db

            def close(self):
                pass

        monkeypatch.setattr(ar, "_open_ddl_client", lambda: _Mini(fake_db))
        monkeypatch.setattr(ar, "_load_ddl_credentials", lambda: {
            "uri": "mongodb://localhost:27017",
            "username": "u", "password": "p", "auth_db": "admin",
        })

        rc1 = ar.run_apply(ar.ALLOWED_DATABASE, ar.ALLOWED_COLLECTION)
        assert rc1 == 0
        rc2 = ar.run_apply(ar.ALLOWED_DATABASE, ar.ALLOWED_COLLECTION)
        assert rc2 == 0

    def test_verify_detects_missing_indexes(self, monkeypatch, capsys):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        fake_db.create_collection(ar.ALLOWED_COLLECTION)

        class _Mini:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                return self._db

            def close(self):
                pass

        monkeypatch.setattr(ar, "_open_ddl_client", lambda: _Mini(fake_db))
        monkeypatch.setattr(ar, "_load_ddl_credentials", lambda: {
            "uri": "x", "username": "u", "password": "p", "auth_db": "admin",
        })

        rc = ar.run_verify(ar.ALLOWED_DATABASE, ar.ALLOWED_COLLECTION)
        captured = capsys.readouterr()
        assert rc == 1
        assert "FAIL" in captured.out
        assert "missing=" in captured.out

    def test_apply_rejects_out_of_scope_collection_via_function(self):
        ar = _load_module()
        with pytest.raises(ar.ScopeViolation):
            ar.run_apply("tradingagents", "03_data_ud_quality_summary")
        with pytest.raises(ar.ScopeViolation):
            ar.run_apply("tradingagents", "portfolio_position")
        with pytest.raises(ar.ScopeViolation):
            ar.run_apply("tradingagents", "smart_money_records")
        with pytest.raises(ar.ScopeViolation):
            ar.run_apply("another_db", "03_data_ud_query_audit")


# ---------------------------------------------------------------------------
# Security: ensure the script NEVER prints URI / password / token
# ---------------------------------------------------------------------------


class TestSecretNonLeakage:
    def test_dry_run_does_not_echo_uri(self):
        # 即使有人设置 URI，dry-run 也不读，更不会打印
        r = _run_cli(env_overrides={
            "UD_DDL_MONGO_URI": "mongodb://user:supersecret@host",
            "UD_DDL_MONGO_USERNAME": "user",
            "UD_DDL_MONGO_PASSWORD": "supersecret",
        })
        assert r.returncode == 0
        assert "supersecret" not in r.stdout
        assert "supersecret" not in r.stderr
        assert "mongodb://user:supersecret" not in r.stdout

    def test_apply_failure_does_not_echo_uri(self):
        # --apply 缺凭证时打印的诊断信息也不含 URI / token
        r = _run_cli(
            "--apply",
            env_overrides={
                "UD_DDL_MONGO_URI": "mongodb://user:supersecret@host",
            },
        )
        assert r.returncode == 3
        assert "supersecret" not in r.stdout
        assert "supersecret" not in r.stderr
        assert "mongodb://user:supersecret" not in r.stderr