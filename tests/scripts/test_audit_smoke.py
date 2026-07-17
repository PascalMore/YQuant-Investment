"""audit_smoke 单元测试（DESIGN-03-011 §8.5 writer insert + reader precise find）。

Pascal 已确认方案 A：新增 ``scripts/unified_data/audit_smoke.py``，作为正式、
可复用的 audit smoke CLI。DESIGN-03-011 §8.5 已定义 smoke 目标：writer insert
一条最小 event + reader 用其 ``_id`` ``find_one`` 读回，并验证标识字段一致。
本卡严格只实现这一最小 smoke；不补 / 不更新 RFC / SPEC / Design。

覆盖矩阵（按 6 个契约 + 4 个边界）：

* SMOKE-101: 默认 dry-run → rc=0，零副作用（不连库、不读真凭证）
* SMOKE-102: dry-run 输出包含 collection 常量、insert/read 计划
* SMOKE-103: dry-run 不回显 URI / password / 完整连接错误
* SMOKE-104: 缺 writer 凭证 → rc=3，无任何 MongoDB 连接
* SMOKE-105: 缺 reader 凭证 → rc=3
* SMOKE-106: ``--apply`` 经 mongomock fake Mongo：writer insert 一条最小
              event + reader 用其 ``_id`` find_one 读回，标识字段一致
* SMOKE-107: ``--apply`` 拒绝越界 collection（任何非 ``03_data_ud_query_audit``）
* SMOKE-108: ``--apply`` 拒绝越界 database（任何非 ``tradingagents``）
* SMOKE-109: 事件无敏感字段（不含 param / account / secret）
* SMOKE-110: writer / reader 使用不同 client / 不同凭证配置
* SMOKE-111: 任何失败 fail-closed：rc ∈ {2, 3, 4}，绝不 rc=0
* SMOKE-112: 事件必含 ``fetched_at`` UTC 时间 + smoke 标识（``event_type`` /
              ``source``），不含业务字段

所有测试使用 mongomock 或 subprocess；不连接真实 MongoDB。``audit_rollout``
已存在且按本任务约定不修改；``audit_smoke`` 只在 ``--apply`` 路径下使用
``pymongo`` 或 mongomock client，dry-run 路径必须不连。
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
SCRIPT = SCRIPTS_DIR / "unified_data" / "audit_smoke.py"


# ---------------------------------------------------------------------------
# module loading helpers (mirror audit_rollout test layout)
# ---------------------------------------------------------------------------


def _load_module():
    """按文件路径加载 scripts/unified_data/audit_smoke.py 为 Python 模块。"""
    spec = importlib.util.spec_from_file_location(
        "scripts.unified_data.audit_smoke", SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_cli(*args: str, env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    """调用 audit_smoke CLI 的 subprocess；显式覆盖 audit_rollout 系列 env。

    dry-run 路径不得因父进程残留凭证被默默切换到连库路径。
    """
    env = {**os.environ}
    for k in (
        "YQUANT_UD_AUDIT_DDL_MONGO_URI",
        "YQUANT_UD_AUDIT_DDL_MONGO_USERNAME",
        "YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD",
        "YQUANT_UD_AUDIT_DDL_MONGO_AUTH_DB",
        "YQUANT_UD_AUDIT_WRITER_MONGO_URI",
        "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME",
        "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
        "YQUANT_UD_AUDIT_WRITER_MONGO_AUTH_DB",
        "YQUANT_UD_AUDIT_READER_MONGO_URI",
        "YQUANT_UD_AUDIT_READER_MONGO_USERNAME",
        "YQUANT_UD_AUDIT_READER_MONGO_PASSWORD",
        "YQUANT_UD_AUDIT_READER_MONGO_AUTH_DB",
    ):
        env.pop(k, None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(ROOT), env=env,
    )


# ---------------------------------------------------------------------------
# fake Mongo (mongomock + 必要的 rolesInfo/usersInfo 兼容)
# ---------------------------------------------------------------------------


class _FakeRuntimeClient:
    """最小 mongomock 客户端包装，断言数据库访问严格在白名单内。"""

    def __init__(self, db, *, kind: str):
        self._db = db
        self._kind = kind  # "writer" / "reader"，仅用于诊断

    def __getitem__(self, name):
        assert name == "tradingagents", (
            f"[{self._kind}] unexpected database access: {name!r}"
        )
        return self._db

    def close(self):
        pass


# ---------------------------------------------------------------------------
# SMOKE-101/102/103: dry-run 默认零副作用 + 输出契约
# ---------------------------------------------------------------------------


class TestDryRunDefault:
    """默认 dry-run：零连接、零副作用、零凭证读取；输出非敏感摘要。"""

    def test_dry_run_default_returns_zero(self):
        """SMOKE-101: 默认无参数 → rc=0，stdout 含 DRY-RUN 标记。"""
        r = _run_cli()
        assert r.returncode == 0
        assert "DRY-RUN" in r.stdout

    def test_dry_run_describes_collection_and_plan(self):
        """SMOKE-102: 输出包含 collection 常量与 insert/read 计划。"""
        r = _run_cli()
        assert r.returncode == 0
        assert "03_data_ud_query_audit" in r.stdout
        assert "insert" in r.stdout.lower()
        assert "find_one" in r.stdout.lower() or "read" in r.stdout.lower()

    def test_dry_run_does_not_echo_secrets(self):
        """SMOKE-103: dry-run 不回显 URI / password / 完整连接错误敏感字段。"""
        r = _run_cli(env_overrides={
            "YQUANT_UD_AUDIT_WRITER_MONGO_URI": "mongodb://user:supersecret@host",
            "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME": "writer-user",
            "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD": "writer-supersecret",
            "YQUANT_UD_AUDIT_READER_MONGO_URI": "mongodb://user:supersecret@host",
            "YQUANT_UD_AUDIT_READER_MONGO_USERNAME": "reader-user",
            "YQUANT_UD_AUDIT_READER_MONGO_PASSWORD": "reader-supersecret",
        })
        assert r.returncode == 0
        assert "writer-supersecret" not in r.stdout
        assert "reader-supersecret" not in r.stdout
        assert "supersecret" not in r.stdout
        assert "supersecret" not in r.stderr
        # dry-run 不得打印任何凭据字段名 (URI / pwd 整段 / mongodb://)
        assert "mongodb://" not in r.stdout


# ---------------------------------------------------------------------------
# SMOKE-104/105: --apply 凭证缺失 fail-fast
# ---------------------------------------------------------------------------


class TestApplyMissingCreds:
    def test_apply_without_writer_creds_returns_3(self):
        """SMOKE-104: 缺 writer 凭证 → rc=3，无任何 MongoDB 连接。"""
        r = _run_cli("--apply")
        assert r.returncode == 3
        # stderr 应明确指出缺失的 writer 字段；不打印 credential 值
        out = r.stderr.lower()
        assert "writer" in out
        assert "missing" in out or "credential" in out

    def test_apply_without_reader_creds_returns_3(self):
        """SMOKE-105: 缺 reader 凭证 → rc=3。"""
        r = _run_cli("--apply", env_overrides={
            "YQUANT_UD_AUDIT_WRITER_MONGO_URI": "mongodb://host",
            "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME": "writer-user",
            "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD": "writer-pwd",
        })
        assert r.returncode == 3
        out = r.stderr.lower()
        assert "reader" in out
        assert "writer-pwd" not in r.stderr
        assert "writer-pwd" not in r.stdout

    def test_apply_uses_separate_client_for_writer_and_reader(self, monkeypatch):
        """SMOKE-110: writer 与 reader 必须使用不同 client / 不同凭证配置。

        注入计数器：open_writer_client / open_reader_client 必须各被调用一次。
        """
        sm = _load_module()
        fake_db = mongomock.MongoClient().db

        calls: list[str] = []

        def _open_writer_client():
            calls.append("writer")
            return _FakeRuntimeClient(fake_db, kind="writer")

        def _open_reader_client():
            calls.append("reader")
            return _FakeRuntimeClient(fake_db, kind="reader")

        monkeypatch.setattr(sm, "_open_writer_client", _open_writer_client)
        monkeypatch.setattr(sm, "_open_reader_client", _open_reader_client)
        for k in (
            "YQUANT_UD_AUDIT_WRITER_MONGO_URI",
            "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
            "YQUANT_UD_AUDIT_READER_MONGO_URI",
            "YQUANT_UD_AUDIT_READER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_READER_MONGO_PASSWORD",
        ):
            monkeypatch.setenv(k, "fake-" + k.lower())

        rc = sm.run_apply()
        assert rc == 0
        # writer 先于 reader
        assert calls == ["writer", "reader"]


# ---------------------------------------------------------------------------
# SMOKE-107/108: 静态范围校验 (db / collection 硬编码 + 拒绝越界)
# ---------------------------------------------------------------------------


class TestStaticScope:
    """模块级静态白名单；任何越界 fail-closed (rc=2)。"""

    def test_module_exposes_canonical_constants(self):
        """白名单常量在模块作用域且唯一。"""
        sm = _load_module()
        assert sm.ALLOWED_DATABASE == "tradingagents"
        assert sm.ALLOWED_COLLECTION == "03_data_ud_query_audit"

    def test_validate_targets_rejects_out_of_scope_collection(self):
        sm = _load_module()
        for bad in (
            "03_data_ud_quality_summary",   # Phase 1 禁用
            "portfolio_position",
            "portfolio_trade",
            "smart_money_records",
            "trade_xyz",
            "signal_pool",
            "argus_signal",
            "cache_keys",
        ):
            with pytest.raises(sm.ScopeViolation):
                sm._validate_targets(sm.ALLOWED_DATABASE, bad)

    def test_validate_targets_rejects_out_of_scope_database(self):
        sm = _load_module()
        for bad in ("admin", "local", "config", "evil_db", ""):
            with pytest.raises(sm.ScopeViolation):
                sm._validate_targets(bad, sm.ALLOWED_COLLECTION)


# ---------------------------------------------------------------------------
# SMOKE-109/112: 事件字段契约 — 无敏感 / 必含 fetched_at + smoke 标识
# ---------------------------------------------------------------------------


class TestEventContract:
    """事件必须最小、可识别、无业务敏感字段。"""

    def test_build_smoke_event_has_no_business_or_secret_fields(self):
        """SMOKE-109/112: 事件不含参数 / 账户 / 证券 / 业务字段 / secret。

        标识字段应明确（如 ``event_type`` / ``source``）以隔离真实审计事件。
        """
        sm = _load_module()
        event = sm._build_smoke_event()

        # 标识字段
        assert "event_type" in event
        assert "source" in event
        assert "fetched_at" in event  # 满足既有 TTL 索引

        # 禁用业务/敏感字段
        for forbidden in (
            "params", "param",
            "account", "user_id",
            "security_id", "market", "capability",
            "provider", "consumer",
            "audit_id",  # 不混入真实审计事件标识
            "password", "secret", "token",
        ):
            assert forbidden not in event, (
                f"smoke event must not contain {forbidden!r}"
            )

    def test_build_smoke_event_fetched_at_is_utc_datetime(self):
        sm = _load_module()
        event = sm._build_smoke_event()
        from datetime import datetime, timezone
        ts = event["fetched_at"]
        assert isinstance(ts, datetime)
        assert ts.tzinfo is not None
        offset = ts.utcoffset()
        assert offset is not None and offset.total_seconds() == 0, (
            f"fetched_at must be UTC, got tzinfo={ts.tzinfo}"
        )
        # 不应是 1970 / 未来
        assert ts.year >= 2024
        assert ts.year <= 2100

    def test_apply_rejects_event_with_business_fields(self, monkeypatch):
        """构造含业务字段的事件 → apply 必须 fail-closed (rc=4)。"""
        sm = _load_module()
        fake_db = mongomock.MongoClient().db

        def _bad_event():
            return {
                "event_type": "smoke",
                "source": "audit_smoke",
                "fetched_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                "security_id": "CN:600519",  # 业务字段 → 越界
            }

        monkeypatch.setattr(sm, "_open_writer_client",
                            lambda: _FakeRuntimeClient(fake_db, kind="writer"))
        monkeypatch.setattr(sm, "_open_reader_client",
                            lambda: _FakeRuntimeClient(fake_db, kind="reader"))
        monkeypatch.setattr(sm, "_build_smoke_event", _bad_event)
        for k in (
            "YQUANT_UD_AUDIT_WRITER_MONGO_URI",
            "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
            "YQUANT_UD_AUDIT_READER_MONGO_URI",
            "YQUANT_UD_AUDIT_READER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_READER_MONGO_PASSWORD",
        ):
            monkeypatch.setenv(k, "fake-" + k.lower())

        rc = sm.run_apply()
        assert rc == 4, "forbidden business field must trigger fail-closed"


# ---------------------------------------------------------------------------
# SMOKE-106: --apply writer insert + reader precise find_one round-trip
# ---------------------------------------------------------------------------


class TestApplyRoundTrip:
    """``--apply`` 主路径：writer insert + reader ``find_one({_id})`` 验证。"""

    def test_apply_writes_then_reads_event_with_matching_id(self, monkeypatch, capsys):
        sm = _load_module()
        fake_db = mongomock.MongoClient().db

        # 注入 fake clients (writer / reader 各自独立)
        monkeypatch.setattr(sm, "_open_writer_client",
                            lambda: _FakeRuntimeClient(fake_db, kind="writer"))
        monkeypatch.setattr(sm, "_open_reader_client",
                            lambda: _FakeRuntimeClient(fake_db, kind="reader"))
        for k in (
            "YQUANT_UD_AUDIT_WRITER_MONGO_URI",
            "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
            "YQUANT_UD_AUDIT_READER_MONGO_URI",
            "YQUANT_UD_AUDIT_READER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_READER_MONGO_PASSWORD",
        ):
            monkeypatch.setenv(k, "fake-" + k.lower())

        rc = sm.run_apply()
        captured = capsys.readouterr()
        assert rc == 0, f"apply failed: {captured.out!r} {captured.err!r}"

        # collection 中存在 1 条事件
        coll = fake_db[sm.ALLOWED_COLLECTION]
        assert coll.count_documents({}) == 1

        doc = coll.find_one({})
        assert doc is not None
        assert "_id" in doc

        # 标识字段与 smoke marker 一致（_id 是 ObjectId，不能直接下标访问）
        for key in ("event_type", "source"):
            assert doc[key] == sm.SMOKE_EVENT_TYPE if key == "event_type" else sm.SMOKE_EVENT_SOURCE, (
                f"smoke marker {key!r} must equal the module constant"
            )

        # 输出包含 ObjectId（可显示）
        assert "ObjectId" in captured.out or "_id" in captured.out

    def test_apply_calls_only_insert_and_find_one(self, monkeypatch):
        """SMOKE-110 + SMOKE-109: --apply 仅 insert_one + find_one({_id})。

        禁止 delete / update / replace / aggregate / 额外索引 / DDL / role /
        user 操作。reader 必须用 writer 返回的 ``_id`` 精确 find_one。
        """
        sm = _load_module()
        fake_db = mongomock.MongoClient().db

        # 替换真实 writer / reader 为 spy，统计调用方法
        writer_calls: list[str] = []
        reader_calls: list[str] = []

        class _SpyWriterColl:
            def __init__(self, real):
                self._real = real

            def insert_one(self, doc):
                writer_calls.append("insert_one")
                # 直接转发到 mongomock（mongomock 会自动补 _id）
                result = self._real.insert_one(dict(doc))
                return result

            def __getattr__(self, name):
                # 任何其它方法被调用 → 失败
                def _fail(*a, **kw):
                    writer_calls.append(name)
                    raise AssertionError(
                        f"writer collection method {name!r} is forbidden in smoke"
                    )
                return _fail

        class _SpyReaderColl:
            def __init__(self, real):
                self._real = real

            def find_one(self, filt, *args, **kwargs):
                reader_calls.append("find_one")
                # 必须用 _id 精确查询
                assert isinstance(filt, dict) and "_id" in filt and len(filt) == 1, (
                    f"reader must find_one by exact _id, got {filt!r}"
                )
                return self._real.find_one(filt)

            def __getattr__(self, name):
                def _fail(*a, **kw):
                    reader_calls.append(name)
                    raise AssertionError(
                        f"reader collection method {name!r} is forbidden in smoke"
                    )
                return _fail

        class _SpyDb:
            """代理 db，确保 collection 访问走 spy，但 db 自身任何方法调用都被禁止。"""

            def __init__(self, real_db, spy_coll_cls):
                self._real = real_db
                self._spy_cls = spy_coll_cls

            def __getitem__(self, coll_name):
                # 强制白名单
                assert coll_name == sm.ALLOWED_COLLECTION, (
                    f"unexpected collection access: {coll_name!r}"
                )
                return self._spy_cls(self._real[coll_name])

            def __getattr__(self, name):
                def _fail(*a, **kw):
                    raise AssertionError(
                        f"db method {name!r} is forbidden in smoke"
                    )
                return _fail

        class _SpyWriterClient:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                assert name == "tradingagents"
                return _SpyDb(self._db[name], _SpyWriterColl)

            def close(self):
                pass

        class _SpyReaderClient:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                assert name == "tradingagents"
                return _SpyDb(self._db[name], _SpyReaderColl)

            def close(self):
                pass

        monkeypatch.setattr(sm, "_open_writer_client", lambda: _SpyWriterClient(fake_db))
        monkeypatch.setattr(sm, "_open_reader_client", lambda: _SpyReaderClient(fake_db))
        for k in (
            "YQUANT_UD_AUDIT_WRITER_MONGO_URI",
            "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
            "YQUANT_UD_AUDIT_READER_MONGO_URI",
            "YQUANT_UD_AUDIT_READER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_READER_MONGO_PASSWORD",
        ):
            monkeypatch.setenv(k, "fake-" + k.lower())

        rc = sm.run_apply()
        assert rc == 0, f"apply must succeed; calls writer={writer_calls} reader={reader_calls}"

        # writer 仅一次 insert_one
        assert writer_calls == ["insert_one"], writer_calls
        # reader 至少一次 find_one
        assert "find_one" in reader_calls

        # 验证事件字段与 smoke marker 一致（从 spy 走过的 tradingagents db）
        doc = fake_db["tradingagents"][sm.ALLOWED_COLLECTION].find_one({})
        assert doc is not None
        assert doc["event_type"] == sm.SMOKE_EVENT_TYPE
        assert doc["source"] == sm.SMOKE_EVENT_SOURCE


# ---------------------------------------------------------------------------
# SMOKE-111: 失败 fail-closed — rc ∈ {2, 3, 4}
# ---------------------------------------------------------------------------


class TestFailClosed:
    """任何异常路径都不允许 rc=0；失败必须显式非零退出码。"""

    def test_missing_collection_constant_is_rejected(self, monkeypatch):
        sm = _load_module()
        # 临时覆盖白名单 → 立即校验失败
        monkeypatch.setattr(sm, "ALLOWED_COLLECTION", "")
        with pytest.raises(sm.ScopeViolation):
            sm._validate_targets(sm.ALLOWED_DATABASE, sm.ALLOWED_COLLECTION)

    @staticmethod
    def _set_smoke_env(monkeypatch):
        """注入 6 个 fake runtime 凭证（含 URI / 用户名 / 密码字面量）。"""
        for k in (
            "YQUANT_UD_AUDIT_WRITER_MONGO_URI",
            "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
            "YQUANT_UD_AUDIT_READER_MONGO_URI",
            "YQUANT_UD_AUDIT_READER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_READER_MONGO_PASSWORD",
        ):
            monkeypatch.setenv(k, "fake-" + k.lower())

    @staticmethod
    def _assert_no_secret_leak(captured, *, sentinels):
        """集中检查 stderr / stdout 不含任何敏感字面量（含 URI / 用户 / 密码）。"""
        for label in ("stderr", "stdout"):
            text = (captured.err if label == "stderr" else captured.out) or ""
            for needle in sentinels:
                assert needle not in text, (
                    f"{label} leaked secret {needle!r}: {text!r}"
                )
            # URI scheme 子串绝对不外泄
            assert "mongodb://" not in text, (
                f"{label} leaked Mongo URI scheme: {text!r}"
            )

    def test_run_apply_returns_nonzero_on_writer_exception(self, monkeypatch, capsys):
        """writer insert 抛异常 → rc=4 (fail-closed)。

        旧断言 ``sm.__dict__.get('_LAST_ERR','')`` 永远为空串（恒真，无验证作用）；
        这里替换为基于 ``captured.err`` 的真实验证。
        """
        sm = _load_module()
        fake_db = mongomock.MongoClient().db

        class _BoomWriter:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                assert name == "tradingagents"

                class _BoomDb:
                    def __getitem__(self, coll_name):
                        assert coll_name == sm.ALLOWED_COLLECTION

                        class _BoomColl:
                            def insert_one(self, doc):
                                raise RuntimeError("simulated writer failure")

                        return _BoomColl()

                return _BoomDb()

            def close(self):
                pass

        class _OkReader:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                return self._db[name]

            def close(self):
                pass

        monkeypatch.setattr(sm, "_open_writer_client", lambda: _BoomWriter(fake_db))
        monkeypatch.setattr(sm, "_open_reader_client", lambda: _OkReader(fake_db))
        self._set_smoke_env(monkeypatch)

        rc = sm.run_apply()
        captured = capsys.readouterr()
        assert rc == 4
        # 旧死断言去掉；新断言：实际 stderr 不含 secret，且异常类型名仍保留
        assert "RuntimeError" in captured.err
        # 旧注入仅含无 secret 文本，但仍确认绝不出现所注入的 6 个 fake 凭证
        for needle in (
            "fake-yquant_ud_audit_writer_mongo_uri",
            "fake-yquant_ud_audit_writer_mongo_username",
            "fake-yquant_ud_audit_writer_mongo_password",
            "fake-yquant_ud_audit_reader_mongo_uri",
            "fake-yquant_ud_audit_reader_mongo_username",
            "fake-yquant_ud_audit_reader_mongo_password",
        ):
            assert needle not in captured.err, (
                f"stderr leaked fake credential {needle!r}: {captured.err!r}"
            )

    def test_run_apply_does_not_leak_secret_in_writer_exception(self, monkeypatch, capsys):
        """writer insert 抛 **含 URI/用户名/密码字面量** 的异常 → stderr 不得出现这些字面量。

        模拟 ``pymongo.errors.ServerSelectionTimeoutError`` / ``OperationFailure``
        默认把完整 URI（含 user:password 部分）拼到异常消息里的真实行为。
        """
        sm = _load_module()
        fake_db = mongomock.MongoClient().db

        leaky_uri = "mongodb://LEAKED-W-USER:LEAKED-W-PWD-12345@host:27017"
        leaky_msg = f"auth failed: {leaky_uri} (authdb=admin)"

        class _LeakyWriter:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                assert name == "tradingagents"

                class _LeakyDb:
                    def __getitem__(self, coll_name):
                        assert coll_name == sm.ALLOWED_COLLECTION

                        class _LeakyColl:
                            def insert_one(self, doc):
                                raise RuntimeError(leaky_msg)

                        return _LeakyColl()

                return _LeakyDb()

            def close(self):
                pass

        class _OkReader:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                return self._db[name]

            def close(self):
                pass

        monkeypatch.setattr(sm, "_open_writer_client", lambda: _LeakyWriter(fake_db))
        monkeypatch.setattr(sm, "_open_reader_client", lambda: _OkReader(fake_db))
        self._set_smoke_env(monkeypatch)

        rc = sm.run_apply()
        captured = capsys.readouterr()
        assert rc == 4, f"expected rc=4, got {rc} stderr={captured.err!r}"
        # 关键：类型名（=非敏感分类）必须保留
        assert "RuntimeError" in captured.err, (
            f"non-sensitive error category must be preserved: {captured.err!r}"
        )
        # 关键：URI / 用户名 / 密码字面量一律不得出现在任何输出
        self._assert_no_secret_leak(
            captured,
            sentinels=(
                "LEAKED-W-USER", "LEAKED-W-PWD-12345", leaky_uri,
                # fake 凭证（注入但未在异常消息中出现）也确保安全
                "fake-yquant_ud_audit_writer_mongo_password",
                "fake-yquant_ud_audit_reader_mongo_password",
            ),
        )

    def test_run_apply_returns_nonzero_on_reader_exception(self, monkeypatch, capsys):
        """reader find_one 抛异常 → rc=4。"""
        sm = _load_module()
        fake_db = mongomock.MongoClient().db

        class _BoomReader:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                assert name == "tradingagents"

                class _BoomDb:
                    def __getitem__(self, coll_name):
                        assert coll_name == sm.ALLOWED_COLLECTION

                        class _BoomColl:
                            def find_one(self, filt, *a, **kw):
                                raise RuntimeError("simulated reader failure")

                        return _BoomColl()

                return _BoomDb()

            def close(self):
                pass

        monkeypatch.setattr(sm, "_open_writer_client",
                            lambda: _FakeRuntimeClient(fake_db, kind="writer"))
        monkeypatch.setattr(sm, "_open_reader_client", lambda: _BoomReader(fake_db))
        self._set_smoke_env(monkeypatch)

        rc = sm.run_apply()
        captured = capsys.readouterr()
        assert rc == 4
        # 异常类型名（非敏感分类）必须保留
        assert "RuntimeError" in captured.err

    def test_run_apply_does_not_leak_secret_in_reader_exception(self, monkeypatch, capsys):
        """reader find_one 抛 **含 URI/用户名/密码字面量** 的异常 → stderr 不外泄。"""
        sm = _load_module()
        fake_db = mongomock.MongoClient().db

        leaky_uri = "mongodb://LEAKED-R-USER:LEAKED-R-PWD-67890@host:27017/?replicaSet=rs0"
        leaky_msg = f"ServerSelectionTimeoutError: {leaky_uri} timed out"

        class _LeakyReader:
            def __init__(self, db):
                self._db = db

            def __getitem__(self, name):
                assert name == "tradingagents"

                class _LeakyDb:
                    def __getitem__(self, coll_name):
                        assert coll_name == sm.ALLOWED_COLLECTION

                        class _LeakyColl:
                            def find_one(self, filt, *a, **kw):
                                raise RuntimeError(leaky_msg)

                        return _LeakyColl()

                return _LeakyDb()

            def close(self):
                pass

        monkeypatch.setattr(sm, "_open_writer_client",
                            lambda: _FakeRuntimeClient(fake_db, kind="writer"))
        monkeypatch.setattr(sm, "_open_reader_client", lambda: _LeakyReader(fake_db))
        self._set_smoke_env(monkeypatch)

        # writer 需先成功插入一条 event，否则 reader path 走不到；用 mongomock fake
        coll = fake_db[sm.ALLOWED_COLLECTION]
        coll.insert_one({
            "event_type": sm.SMOKE_EVENT_TYPE,
            "source": sm.SMOKE_EVENT_SOURCE,
            "fetched_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc,
            ),
        })

        rc = sm.run_apply()
        captured = capsys.readouterr()
        assert rc == 4, f"expected rc=4, got {rc} stderr={captured.err!r}"
        assert "RuntimeError" in captured.err, (
            f"non-sensitive error category must be preserved: {captured.err!r}"
        )
        self._assert_no_secret_leak(
            captured,
            sentinels=(
                "LEAKED-R-USER", "LEAKED-R-PWD-67890", leaky_uri,
                "fake-yquant_ud_audit_writer_mongo_password",
                "fake-yquant_ud_audit_reader_mongo_password",
            ),
        )


# ---------------------------------------------------------------------------
# 静态契约：dry-run 路径不连库、不读真凭证
# ---------------------------------------------------------------------------


class TestNoConnectionOnDryRun:
    """dry-run 模式必须不调用 pymongo 或 mongomock；可作静态配置检查但不连。"""

    def test_dry_run_does_not_invoke_pymongo_or_clients(self):
        """通过 monkeypatch 监测 dry-run 是否调用 _open_*_client。

        dry-run 路径完全不应触达 client opener。
        """
        sm = _load_module()

        def _boom_writer():
            raise AssertionError(
                "dry-run must not call _open_writer_client"
            )

        def _boom_reader():
            raise AssertionError(
                "dry-run must not call _open_reader_client"
            )

        with patch.object(sm, "_open_writer_client", _boom_writer), \
             patch.object(sm, "_open_reader_client", _boom_reader):
            rc = sm.run_dry_run()
        assert rc == 0


# ---------------------------------------------------------------------------
# CLI 形状：参数互斥、dry-run 与 --apply 互斥
# ---------------------------------------------------------------------------


class TestCliShape:
    def test_unknown_arg_rejected(self):
        """未声明的 CLI 参数必须 fail-fast (argparse rc=2)。

        必须先产生 DRY-RUN 输出（rc=0）再尝试解析 ``--evil-flag``；否则视为
        脚本根本未加载 (FileNotFoundError → 意外 rc=2)。
        """
        # 1. dry-run 先 rc=0：证明脚本可加载
        r0 = _run_cli()
        assert r0.returncode == 0, (
            f"dry-run must succeed; got rc={r0.returncode} stderr={r0.stderr!r}"
        )

        # 2. 未知 flag 必须被 argparse 拒绝为 rc=2
        r = _run_cli("--evil-flag")
        assert r.returncode == 2
        # 错误信息含 unknown / unrecognized / unrecognised 之一
        out = (r.stderr + r.stdout).lower()
        assert any(
            kw in out for kw in ("unrecognized", "unrecognised", "unknown", "invalid")
        ), f"expected argparse error text, got: {r.stderr!r}"

    def test_module_main_uses_argparse(self):
        sm = _load_module()
        # 至少存在 main / _build_parser
        assert hasattr(sm, "main")
        assert callable(sm.main)
        assert hasattr(sm, "_build_parser")
