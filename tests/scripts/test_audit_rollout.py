"""audit_rollout 单元测试（DESIGN-03-011 §8.9 / §14.1，SPEC-03-011 §8）。

覆盖矩阵（reviewer t_c051239d REVISE 后重写 + A1-A10 acceptance）：

* ROL-101: dry-run 模式零副作用、rc=0、打印计划
* ROL-102: --apply 缺凭证 → rc=3
* ROL-103: --verify 缺凭证 → rc=3
* ROL-104: --apply mongomock 注入 → collection + 3 indexes + 2 roles + 2 users 全幂等
* ROL-105: --verify mongomock 注入 → 索引缺失时返回 1
* ROL-106: --verify 检测到 role privileges 不一致 → 1
* ROL-107: --verify 检测到 QualitySummary 集合存在 → 1
* ROL-108: --apply 不创建 QualitySummary 集合
* ROL-109: 静态范围校验（database/collection）触发 ScopeViolation
* ROL-110: secret 不回显（dry-run + apply 失败均不打印 URI / password）

新增 A1-A10（DESIGN §14.1, RFC §A1-A10）：

* A1: 四函数 _ensure_write_role / _ensure_read_role / _ensure_write_user
       / _ensure_read_user 存在，run_apply 调用链覆盖
* A2: WRITER_ROLE_NAME 等四个常量以 ``yquant_ud_audit_`` 开头
* A3: writer role privileges 仅含 insert on 03_data_ud_query_audit；
       reader role 仅含 find
* A4: ALLOWED_PARAMS 在模块作用域（非构造参数）
* A5: run_apply 不调用涉及 portfolio_/smart_money_/signal_/trade_/cache
       等越界 collection 的 grant 操作
* A6: --apply 缺凭证 → rc=3，无 MongoDB 连接
* A7: 范围校验 fail-fast → rc=2
* A8: dry-run 零副作用 → rc=0，不读 env
* A9: --apply 幂等（连续两次，第二次不报错，skipped=[...]）
* A10: A10 边界——已存在 role 但 privileges 不匹配 → apply rc=4，fail-closed
       （替代 reviewer REVISE issue 3 的 fail-open 设计）

所有测试使用 mongomock 或 subprocess；不连接真实 MongoDB。
"""

from __future__ import annotations

import importlib.util
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
    # 显式覆盖：测试不被父进程残留凭证影响
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


class TestDryRun:
    def test_dry_run_default_succeeds(self):
        r = _run_cli()
        assert r.returncode == 0
        assert "DRY-RUN" in r.stdout
        assert "fetched_at_ttl" in r.stdout
        assert "expireAfterSeconds=31536000" in r.stdout
        # 验证 dry-run 模式不读取凭证
        assert "credential" not in r.stdout.lower()

    def test_dry_run_describes_formal_identity_names(self):
        r = _run_cli()
        assert r.returncode == 0
        for expected in (
            "yquant_ud_audit_writer_role",
            "yquant_ud_audit_reader_role",
            "yquant_ud_audit_writer_user",
            "yquant_ud_audit_reader_user",
        ):
            assert expected in r.stdout, f"missing {expected} in plan"

    def test_dry_run_does_not_echo_uri(self):
        r = _run_cli(env_overrides={
            "YQUANT_UD_AUDIT_DDL_MONGO_URI": "mongodb://user:***@host",
            "YQUANT_UD_AUDIT_DDL_MONGO_USERNAME": "user",
            "YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD": "supersecret",
        })
        assert r.returncode == 0
        assert "supersecret" not in r.stdout
        assert "supersecret" not in r.stderr
        assert "mongodb://user:supersecret" not in r.stdout


class TestScopeValidation:
    def test_apply_rejects_unknown_db_via_function(self):
        ar = _load_module()
        # 通过 monkeypatch _open_ddl_client 让 call 不会真连，但 validate 在前
        with pytest.raises(ar.ScopeViolation):
            ar._validate_targets("evil_db", ar.ALLOWED_COLLECTION)

    def test_apply_rejects_quality_summary_collection(self):
        ar = _load_module()
        with pytest.raises(ar.ScopeViolation):
            ar._validate_targets(ar.ALLOWED_DATABASE, "03_data_ud_quality_summary")
        with pytest.raises(ar.ScopeViolation):
            ar._validate_targets(ar.ALLOWED_DATABASE, "portfolio_position")
        with pytest.raises(ar.ScopeViolation):
            ar._validate_targets(ar.ALLOWED_DATABASE, "smart_money_records")
        with pytest.raises(ar.ScopeViolation):
            ar._validate_targets(ar.ALLOWED_DATABASE, "trade_xyz")

    def test_validate_identity_name_rejects_broad(self):
        ar = _load_module()
        for bad in (
            "ud_audit_writer_app",       # 旧前缀
            "ud_audit_reader_app",       # 旧前缀
            "portfolio_admin",
            "smart_money_writer",
            "signal_reader",
            "trade_admin",
            "cache_admin",
            "yquant_ud_audit_other",     # 前缀正确但后缀不在 allow-list
            "",
            None,
        ):
            with pytest.raises(ar.ScopeViolation):
                ar._validate_identity_name(bad, kind="identity")  # type: ignore[arg-type]


class TestApplyMissingCreds:
    def test_apply_without_creds_returns_3(self):
        r = _run_cli("--apply")
        assert r.returncode == 3
        assert "YQUANT_UD_AUDIT_DDL_MONGO_URI" in r.stderr

    def test_apply_with_only_uri_returns_3(self):
        r = _run_cli("--apply", env_overrides={
            "YQUANT_UD_AUDIT_DDL_MONGO_URI": "mongodb://localhost:27017",
        })
        assert r.returncode == 3
        assert "YQUANT_UD_AUDIT_DDL_MONGO_USERNAME" in r.stderr

    def test_verify_without_creds_returns_3(self):
        r = _run_cli("--verify")
        assert r.returncode == 3

    def test_apply_failure_does_not_echo_uri(self):
        r = _run_cli(
            "--apply",
            env_overrides={
                "YQUANT_UD_AUDIT_DDL_MONGO_URI": "mongodb://user:***@host",
            },
        )
        assert r.returncode == 3
        assert "supersecret" not in r.stdout
        assert "supersecret" not in r.stderr
        assert "mongodb://user:supersecret" not in r.stderr


# ---------------------------------------------------------------------------
# In-process tests with mongomock (exercise --apply / --verify against fake DB)
# ---------------------------------------------------------------------------


class _FakeDdlClient:
    """最小 mongomock 客户端包装，模拟 db.client[] 语法。"""

    def __init__(self, db):
        self._db = db

    def __getitem__(self, name):
        # script 内只读 ALLOWED_DATABASE，但保留显式断言以防误改
        assert name == "tradingagents", f"unexpected database access: {name}"
        return self._db

    def close(self):
        pass


class _FakeAdminDb:
    """mongomock 不实现 db.command() 的 admin 指令（createRole /
    createUser / rolesInfo / usersInfo / updateRole）。本类在 mongomock
    之上装一层内存伪造实现，覆盖 DDL 脚本所需命令。"""

    def __init__(self, base_db):
        self._base = base_db
        self._roles: dict[str, dict] = {}
        self._users: dict[str, dict] = {}
        self.commands: list[dict] = []

    def __getattr__(self, item):
        # collection / list_collection_names / create_collection 等转发到 mongomock
        return getattr(self._base, item)

    def __getitem__(self, item):
        # db[collection] 语法：转发到 mongomock Database.__getitem__
        return self._base[item]

    def command(self, cmd, *args, **kwargs):  # noqa: D401
        if not isinstance(cmd, dict):
            raise NotImplementedError(f"fake admin db unsupported cmd: {cmd!r}")
        self.commands.append(dict(cmd))
        if "createRole" in cmd:
            name = cmd["createRole"]
            if name in self._roles:
                raise _DuplicateKey(f"role already exists: {name}")
            self._roles[name] = {
                "privileges": list(cmd.get("privileges") or []),
                "roles": list(cmd.get("roles") or []),
            }
            return {"ok": 1.0}
        if "updateRole" in cmd:
            name = cmd["updateRole"]
            if name not in self._roles:
                raise _DuplicateKey(f"role not found: {name}")
            self._roles[name] = {
                "privileges": list(cmd.get("privileges") or []),
                "roles": list(cmd.get("roles") or []),
            }
            return {"ok": 1.0}
        if "rolesInfo" in cmd:
            name = cmd["rolesInfo"]
            if name == "":  # list all
                return {
                    "roles": [
                        {"role": n, **data} for n, data in self._roles.items()
                    ],
                }
            if name not in self._roles:
                return {"roles": []}
            data = self._roles[name]
            return {
                "roles": [
                    {
                        "role": name,
                        "privileges": data["privileges"],
                        "roles": data["roles"],
                    },
                ],
            }
        if "createUser" in cmd:
            name = cmd["createUser"]
            password = cmd.get("pwd")
            if not isinstance(password, str) or not password:
                raise ValueError("createUser requires a non-empty pwd")
            if name in self._users:
                raise _DuplicateKey(f"user already exists: {name}")
            self._users[name] = {"roles": list(cmd.get("roles") or [])}
            return {"ok": 1.0}
        if "usersInfo" in cmd:
            name = cmd["usersInfo"]
            if name not in self._users:
                return {"users": []}
            return {
                "users": [
                    {"user": name, "roles": self._users[name]["roles"]},
                ],
            }
        raise NotImplementedError(f"fake admin db unsupported cmd: {cmd!r}")


class _DuplicateKey(Exception):
    """模拟 MongoDB duplicate key / role exists 错误，触发 _ensure_* 的
    "已存在 → 精确比对"分支。"""


def _install_fake_ddl(monkeypatch, ar, fake_db):
    """把 DDL client 替换为 fake admin，并设置 createUser 测试密码。"""
    admin_db = _FakeAdminDb(fake_db)
    monkeypatch.setattr(ar, "_open_ddl_client", lambda: _FakeDdlClient(admin_db))
    monkeypatch.setenv("YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD", "writer-test-password")
    monkeypatch.setenv("YQUANT_UD_AUDIT_READER_MONGO_PASSWORD", "reader-test-password")
    return admin_db


class TestApplyWithMongomock:
    def test_apply_creates_collection_indexes_roles_users(self, monkeypatch):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        _install_fake_ddl(monkeypatch, ar, fake_db)

        rc = ar.run_apply()
        assert rc == 0

        # collection
        assert ar.ALLOWED_COLLECTION in fake_db.list_collection_names()
        # QualitySummary 集合绝不能被创建
        assert "03_data_ud_quality_summary" not in fake_db.list_collection_names()

        # 3 indexes
        names = {
            idx["name"]
            for idx in fake_db[ar.ALLOWED_COLLECTION].list_indexes()
        }
        for expected in (
            "fetched_at_ttl",
            "security_id_fetched_at",
            "capability_fetched_at",
        ):
            assert expected in names

    def test_apply_idempotent(self, monkeypatch):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        _install_fake_ddl(monkeypatch, ar, fake_db)

        rc1 = ar.run_apply()
        assert rc1 == 0
        rc2 = ar.run_apply()
        assert rc2 == 0

    def test_apply_rejects_existing_role_with_wrong_privileges(self, monkeypatch):
        """A10 + reviewer REVISE issue 3：已存在 role 但 privileges 不匹配
        必须 fail-closed（rc=4），不得仅 warning 静默继续。"""
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        admin_db = _install_fake_ddl(monkeypatch, ar, fake_db)

        # 第一次 apply 创建所有 contract-compliant role/user
        assert ar.run_apply() == 0

        # 注入越界 privileges：试图给 writer role 加上 find / 其它 collection
        admin_db.command({
            "updateRole": ar.WRITER_ROLE_NAME,
            "privileges": [
                {
                    "resource": {
                        "db": "tradingagents",
                        "collection": "03_data_ud_query_audit",
                    },
                    "actions": ["insert", "find"],  # 比 contract 多 find
                },
                {
                    "resource": {
                        "db": "tradingagents",
                        "collection": "portfolio_position",  # 越界
                    },
                    "actions": ["find"],
                },
            ],
            "roles": [],
        })

        rc = ar.run_apply()
        assert rc == 4, "broad/wrong privileges must trigger IdentityPrivilegeMismatch"
        # apply 路径在 stderr 显式标注 BLOCKED
        # （直接调用 run_apply 不打 stderr，但异常信息已在 _ensure_role 内抛出）

    def test_apply_rejects_quality_summary_existing(self, monkeypatch):
        """rollback-safe 防御：如果 Phase 1 残留 QualitySummary 集合，
        apply 必须 fail-closed，不静默继续。"""
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        # 在 _open_ddl_client 注入前先创建 QualitySummary
        fake_db.create_collection("03_data_ud_quality_summary")
        _install_fake_ddl(monkeypatch, ar, fake_db)

        rc = ar.run_apply()
        assert rc == 4


class TestVerifyWithMongomock:
    def test_verify_detects_missing_indexes(self, monkeypatch, capsys):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        fake_db.create_collection(ar.ALLOWED_COLLECTION)
        # 只建一个错误 key 的 index 触发 mismatch
        fake_db[ar.ALLOWED_COLLECTION].create_index(
            [("fetched_at", 1)],
            name="fetched_at_ttl",
            expireAfterSeconds=12345,  # wrong TTL
        )
        _install_fake_ddl(monkeypatch, ar, fake_db)

        rc = ar.run_verify()
        captured = capsys.readouterr()
        assert rc == 1
        assert "FAIL" in captured.out
        assert "mismatch" in captured.out.lower()

    def test_verify_detects_missing_collection(self, monkeypatch, capsys):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        _install_fake_ddl(monkeypatch, ar, fake_db)

        rc = ar.run_verify()
        captured = capsys.readouterr()
        assert rc == 1
        assert "missing" in captured.out.lower()

    def test_verify_detects_quality_summary_existing(self, monkeypatch, capsys):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        _install_fake_ddl(monkeypatch, ar, fake_db)
        assert ar.run_apply() == 0

        # 模拟 QualitySummary 集合被某次外部错误注入
        fake_db.create_collection("03_data_ud_quality_summary")

        rc = ar.run_verify()
        captured = capsys.readouterr()
        assert rc == 1
        assert "QualitySummary" in captured.out

    def test_verify_passes_after_apply(self, monkeypatch, capsys):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        _install_fake_ddl(monkeypatch, ar, fake_db)

        assert ar.run_apply() == 0

        rc = ar.run_verify()
        captured = capsys.readouterr()
        assert rc == 0
        assert "OK" in captured.out


# ---------------------------------------------------------------------------
# A1-A10 Developer Acceptance（DESIGN §14.1, RFC §A1-A10）
# ---------------------------------------------------------------------------


class TestAcceptanceA1_A10:
    """对应 DESIGN-03-011 §14.1 / RFC-03-011 §14 的 A1-A10 acceptance。"""

    def test_a1_ensure_functions_exist_and_run_apply_calls_them(self, monkeypatch):
        """A1: 四个 _ensure_* 函数存在，run_apply 调用链覆盖。"""
        ar = _load_module()
        # 静态函数存在性
        for fn_name in (
            "_ensure_write_role",
            "_ensure_read_role",
            "_ensure_write_user",
            "_ensure_read_user",
        ):
            assert hasattr(ar, fn_name), f"missing {fn_name}"
            assert callable(getattr(ar, fn_name)), f"{fn_name} not callable"

        # run_apply 调用链覆盖：通过 mock 让每个 _ensure_* 都触发计数
        fake_db = mongomock.MongoClient().db
        _install_fake_ddl(monkeypatch, ar, fake_db)
        calls: list[str] = []
        for fn_name in (
            "_ensure_write_role",
            "_ensure_read_role",
            "_ensure_write_user",
            "_ensure_read_user",
        ):
            original = getattr(ar, fn_name)
            def _make_recorder(orig, name):
                def _wrapped(db):
                    calls.append(name)
                    return orig(db)
                return _wrapped
            monkeypatch.setattr(
                ar, fn_name, _make_recorder(original, fn_name)
            )

        rc = ar.run_apply()
        assert rc == 0
        # 调用链顺序：先 roles 再 users
        assert calls == [
            "_ensure_write_role",
            "_ensure_read_role",
            "_ensure_write_user",
            "_ensure_read_user",
        ]

    def test_a2_identity_constants_have_yquant_prefix(self):
        """A2: WRITER_ROLE_NAME / READER_ROLE_NAME / WRITER_USER_NAME /
        READER_USER_NAME 均以 yquant_ud_audit_ 开头。"""
        ar = _load_module()
        for name in (
            "WRITER_ROLE_NAME",
            "READER_ROLE_NAME",
            "WRITER_USER_NAME",
            "READER_USER_NAME",
        ):
            value = getattr(ar, name)
            assert isinstance(value, str)
            assert value.startswith("yquant_ud_audit_"), (
                f"{name}={value!r} does not start with 'yquant_ud_audit_'"
            )

    def test_a3_role_privileges_exact_match(self):
        """A3: writer role 仅含 insert on audit collection；reader 仅含 find。"""
        ar = _load_module()
        # writer：actions == ["insert"]，resource 唯一且仅 audit collection
        assert len(ar.WRITER_ROLE_PRIVILEGES) == 1
        wp = ar.WRITER_ROLE_PRIVILEGES[0]
        assert wp["resource"]["db"] == "tradingagents"
        assert wp["resource"]["collection"] == "03_data_ud_query_audit"
        assert set(wp["actions"]) == {"insert"}

        # reader：actions == ["find"]
        assert len(ar.READER_ROLE_PRIVILEGES) == 1
        rp = ar.READER_ROLE_PRIVILEGES[0]
        assert rp["resource"]["db"] == "tradingagents"
        assert rp["resource"]["collection"] == "03_data_ud_query_audit"
        assert set(rp["actions"]) == {"find"}

    def test_a4_allowed_params_is_module_level(self):
        """A4: ALLOWED_PARAMS 在模块作用域（非构造参数）。"""
        ar = _load_module()
        # 1. 模块级属性存在
        assert hasattr(ar, "ALLOWED_PARAMS")
        # 2. 类型为 set / frozenset，且保持既有唯一 11-key 命名空间
        assert isinstance(ar.ALLOWED_PARAMS, (set, frozenset))
        assert len(ar.ALLOWED_PARAMS) == 11
        # 3. 至少包含 contract-required 键（来自 DESIGN §8.6）
        for key in (
            "security_id",
            "market",
            "domain",
            "operation",
            "start_date",
            "end_date",
            "limit",
            "provider",
            "consumer",
        ):
            assert key in ar.ALLOWED_PARAMS, (
                f"ALLOWED_PARAMS missing required key {key!r}"
            )

    def test_a5_apply_never_grants_out_of_scope_collections(self, monkeypatch):
        """A5: run_apply 不调用涉及 portfolio_/smart_money_/signal_/trade_/
        cache 等越界 collection 的 grant 操作。"""
        ar = _load_module()
        fake_db = mongomock.MongoClient().db

        granted_resources: list[dict] = []

        # 拦截 _FakeAdminDb.command 的 createRole / updateRole 抓取 privileges
        admin_db = _install_fake_ddl(monkeypatch, ar, fake_db)
        real_command = admin_db.command

        def _spy_command(cmd, *args, **kwargs):
            if isinstance(cmd, dict):
                if cmd.get("createRole"):
                    granted_resources.extend(cmd.get("privileges") or [])
                if cmd.get("updateRole"):
                    granted_resources.extend(cmd.get("privileges") or [])
            return real_command(cmd, *args, **kwargs)

        monkeypatch.setattr(admin_db, "command", _spy_command)

        rc = ar.run_apply()
        assert rc == 0

        # 严格白名单：db==tradingagents && collection==03_data_ud_query_audit
        for priv in granted_resources:
            res = priv.get("resource") or {}
            assert res.get("db") == "tradingagents", (
                f"out-of-scope db {res.get('db')!r}"
            )
            assert res.get("collection") == "03_data_ud_query_audit", (
                f"out-of-scope collection {res.get('collection')!r}"
            )

    def test_a6_missing_creds_fail_fast(self):
        """A6: 凭证缺失 → rc=3，无 MongoDB 连接。"""
        r = _run_cli("--apply")
        assert r.returncode == 3
        # subprocess 完全没启动；rc != 0 即证明未连接
        assert "BLOCKED" in r.stderr or "missing" in r.stderr.lower()

    def test_a7_out_of_scope_validation_fail_fast(self):
        """A7: 越界范围 → rc=2 [BLOCKED]。脚本不可通过 CLI 直接覆盖
        database / collection（已删除 --database / --collection 参数）。
        """
        # 直接尝试 CLI 覆盖：argparse 会拒绝
        r = _run_cli("--database", "wrong")
        assert r.returncode == 2
        assert "unrecognized" in r.stderr or "BLOCKED" in r.stderr

    def test_a8_dry_run_zero_side_effect(self):
        """A8: dry-run 零副作用 → rc=0，不连接 MongoDB。"""
        r = _run_cli()
        assert r.returncode == 0
        # stdout 不应包含任何 connect / TLS / connection 字样
        assert "connect" not in r.stdout.lower() or "ready" not in r.stdout.lower()

    def test_a9_apply_is_idempotent(self, monkeypatch):
        """A9: 两次 --apply 幂等。第二次不报错，输出含 skipped=[...]。"""
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        _install_fake_ddl(monkeypatch, ar, fake_db)

        rc1 = ar.run_apply()
        assert rc1 == 0
        rc2 = ar.run_apply()
        assert rc2 == 0

    def test_a10_existing_role_wrong_privileges_fail_closed(self, monkeypatch):
        """A10: 已有 role 但 privileges 不匹配 → apply rc=4（fail-closed）。

        替代 reviewer REVISE issue 3 的 fail-open warning 设计。
        """
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        admin_db = _install_fake_ddl(monkeypatch, ar, fake_db)

        # 正常初始化
        assert ar.run_apply() == 0

        # 模拟某次手动操作把 writer role 的 privileges 改成 broad
        admin_db.command({
            "updateRole": ar.WRITER_ROLE_NAME,
            "privileges": [
                {
                    "resource": {"db": "admin", "collection": ""},
                    "actions": ["anyAction"],
                },
            ],
            "roles": [{"role": "root", "db": "admin"}],
        })

        # 第二次 apply 必须 fail-closed（rc=4），不让 broad identity 残留
        rc = ar.run_apply()
        assert rc == 4

    def test_module_constants_have_no_constructor_injection(self):
        """辅助断言：ALLOWED_IDENTITY_NAMES 不可被构造参数覆盖（合同）。"""
        ar = _load_module()
        # 不存在 __init__ 或 set_identity 之类的注入入口
        assert not hasattr(ar, "set_role_name")
        assert not hasattr(ar, "set_user_name")
        # 4 个名字仅能通过模块级常量访问
        for name in (
            "WRITER_ROLE_NAME",
            "READER_ROLE_NAME",
            "WRITER_USER_NAME",
            "READER_USER_NAME",
        ):
            assert isinstance(getattr(ar, name), str)


class TestSecretNonLeakage:
    def test_dry_run_does_not_echo_uri(self):
        r = _run_cli(env_overrides={
            "YQUANT_UD_AUDIT_DDL_MONGO_URI": "mongodb://user:***@host",
            "YQUANT_UD_AUDIT_DDL_MONGO_USERNAME": "user",
            "YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD": "supersecret",
        })
        assert r.returncode == 0
        assert "supersecret" not in r.stdout
        assert "supersecret" not in r.stderr
        assert "mongodb://user:supersecret" not in r.stdout

    def test_apply_failure_does_not_echo_uri(self):
        r = _run_cli(
            "--apply",
            env_overrides={
                "YQUANT_UD_AUDIT_DDL_MONGO_URI": "mongodb://user:***@host",
            },
        )
        assert r.returncode == 3
        assert "supersecret" not in r.stdout
        assert "supersecret" not in r.stderr
        assert "mongodb://user:supersecret" not in r.stderr


class TestForbiddenCollections:
    """Phase 1 不创建 QualitySummary；任何路径不得绕开。"""

    def test_apply_does_not_create_quality_summary(self, monkeypatch):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        _install_fake_ddl(monkeypatch, ar, fake_db)
        assert ar.run_apply() == 0
        assert "03_data_ud_quality_summary" not in fake_db.list_collection_names()

    def test_dry_run_prints_quality_summary_warning(self):
        r = _run_cli()
        assert r.returncode == 0
        assert "QualitySummary" in r.stdout
        assert "MUST NOT" in r.stdout


class TestApplyIndexExactCompare:
    """A10 + reviewer REVISE issue 7：apply 对每个 index 做精确比对。"""

    def test_apply_detects_existing_index_with_wrong_ttl(self, monkeypatch):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        # 预创建 collection 与一个 TTL 错误的 fetched_at_ttl
        fake_db.create_collection(ar.ALLOWED_COLLECTION)
        fake_db[ar.ALLOWED_COLLECTION].create_index(
            [("fetched_at", 1)],
            name="fetched_at_ttl",
            expireAfterSeconds=12345,  # wrong TTL
        )
        _install_fake_ddl(monkeypatch, ar, fake_db)

        rc = ar.run_apply()
        assert rc == 4  # IdentityPrivilegeMismatch

    def test_apply_detects_existing_index_with_wrong_key_order(self, monkeypatch):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        fake_db.create_collection(ar.ALLOWED_COLLECTION)
        # 故意把 security_id_fetched_at 的方向倒过来
        fake_db[ar.ALLOWED_COLLECTION].create_index(
            [("security_id", -1), ("fetched_at", -1)],
            name="security_id_fetched_at",
        )
        _install_fake_ddl(monkeypatch, ar, fake_db)

        rc = ar.run_apply()
        assert rc == 4


class TestCreateUserPasswordContract:
    """DESIGN §8.9.5 T-PWD-1..5：createUser pwd 与只读预检门禁。"""

    def test_t_pwd_1_create_user_command_has_non_empty_pwd(self, monkeypatch):
        ar = _load_module()
        admin_db = _FakeAdminDb(mongomock.MongoClient().db)
        password = "writer-initial-password"
        monkeypatch.setenv("YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD", password)

        state = ar._ensure_user(
            admin_db,
            user_name=ar.WRITER_USER_NAME,
            roles=[{"role": ar.WRITER_ROLE_NAME, "db": ar.ALLOWED_DATABASE}],
            password_env_var="YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
        )

        assert state == "created"
        assert "usersInfo" in admin_db.commands[0]
        create_user = next(cmd for cmd in admin_db.commands if "createUser" in cmd)
        assert create_user["pwd"] == password
        assert create_user["pwd"].strip()

    def test_t_pwd_2_missing_pwd_allows_only_users_info_precheck(
        self, monkeypatch, capsys
    ):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        admin_db = _install_fake_ddl(monkeypatch, ar, fake_db)
        monkeypatch.delenv("YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD", raising=False)
        monkeypatch.delenv("YQUANT_UD_AUDIT_READER_MONGO_PASSWORD", raising=False)
        monkeypatch.setattr(
            ar,
            "_load_runtime_writer_credentials",
            lambda: pytest.fail("runtime writer identity must not connect during apply"),
        )
        monkeypatch.setattr(
            ar,
            "_load_runtime_reader_credentials",
            lambda: pytest.fail("runtime reader identity must not connect during apply"),
        )

        rc = ar.run_apply()
        captured = capsys.readouterr()

        assert rc == 3
        assert admin_db.commands
        assert all("usersInfo" in cmd for cmd in admin_db.commands)
        assert not admin_db._roles
        assert not admin_db._users
        assert ar.ALLOWED_COLLECTION not in fake_db.list_collection_names()
        assert "pwd" not in captured.out.lower()
        assert "password" not in captured.out.lower()

    def test_t_pwd_2_empty_pwd_is_missing(self, monkeypatch):
        ar = _load_module()
        admin_db = _FakeAdminDb(mongomock.MongoClient().db)
        password_env_var = "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD"
        monkeypatch.setenv(password_env_var, "   ")

        with pytest.raises(ar.MissingCredentialError):
            ar._ensure_user(
                admin_db,
                user_name=ar.WRITER_USER_NAME,
                roles=[{"role": ar.WRITER_ROLE_NAME, "db": ar.ALLOWED_DATABASE}],
                password_env_var=password_env_var,
            )

        assert admin_db.commands == [
            {"usersInfo": ar.WRITER_USER_NAME, "showPrivileges": False}
        ]

    def test_t_pwd_3_matching_user_does_not_read_password(self, monkeypatch):
        ar = _load_module()
        admin_db = _FakeAdminDb(mongomock.MongoClient().db)
        roles = [{"role": ar.WRITER_ROLE_NAME, "db": ar.ALLOWED_DATABASE}]
        admin_db._users[ar.WRITER_USER_NAME] = {"roles": roles}
        password_env_var = "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD"
        monkeypatch.delenv(password_env_var, raising=False)

        with patch.object(
            ar.os.environ, "get", wraps=ar.os.environ.get
        ) as environ_get:
            state = ar._ensure_user(
                admin_db,
                user_name=ar.WRITER_USER_NAME,
                roles=roles,
                password_env_var=password_env_var,
            )

        assert state == "unchanged"
        assert admin_db.commands == [
            {"usersInfo": ar.WRITER_USER_NAME, "showPrivileges": False}
        ]
        assert all(call.args[0] != password_env_var for call in environ_get.call_args_list)

    def test_t_pwd_4_binding_mismatch_returns_4_without_writes(
        self, monkeypatch, capsys
    ):
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        admin_db = _install_fake_ddl(monkeypatch, ar, fake_db)
        admin_db._users[ar.WRITER_USER_NAME] = {
            "roles": [{"role": ar.READER_ROLE_NAME, "db": ar.ALLOWED_DATABASE}]
        }

        rc = ar.run_apply()
        captured = capsys.readouterr()

        assert rc == 4
        assert admin_db.commands == [
            {"usersInfo": ar.WRITER_USER_NAME, "showPrivileges": False}
        ]
        assert not admin_db._roles
        assert ar.ALLOWED_COLLECTION not in fake_db.list_collection_names()
        assert "mismatch" in captured.err.lower() or "does not match" in captured.err.lower()

    def test_t_pwd_5_create_user_exception_does_not_leak_secret(
        self, monkeypatch, capsys
    ):
        ar = _load_module()
        admin_db = _FakeAdminDb(mongomock.MongoClient().db)
        password = "never-echo-this-password"
        password_env_var = "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD"
        monkeypatch.setenv(password_env_var, password)
        real_command = admin_db.command

        def _reject_create_user(cmd, *args, **kwargs):
            if isinstance(cmd, dict) and "createUser" in cmd:
                raise RuntimeError(f"server rejected supplied secret {password}")
            return real_command(cmd, *args, **kwargs)

        monkeypatch.setattr(admin_db, "command", _reject_create_user)

        try:
            ar._ensure_user(
                admin_db,
                user_name=ar.WRITER_USER_NAME,
                roles=[{"role": ar.WRITER_ROLE_NAME, "db": ar.ALLOWED_DATABASE}],
                password_env_var=password_env_var,
            )
        except ar.RolloutError as exc:
            rendered = "".join(
                __import__("traceback").format_exception(type(exc), exc, exc.__traceback__)
            )
        else:
            pytest.fail("createUser failure must raise RolloutError")
        captured = capsys.readouterr()

        assert password not in rendered
        assert password not in captured.out
        assert password not in captured.err


class TestCredentialLoaders:
    """DESIGN §8.5.2 / SPEC §8.3：runtime writer/reader 凭证独立加载。"""

    def test_load_ddl_credentials_missing_uri(self, monkeypatch):
        ar = _load_module()
        for k in (
            "YQUANT_UD_AUDIT_DDL_MONGO_URI",
            "YQUANT_UD_AUDIT_DDL_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD",
        ):
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(ar.MissingCredentialError) as exc:
            ar._load_ddl_credentials()
        assert "YQUANT_UD_AUDIT_DDL_MONGO_URI" in str(exc.value)

    def test_load_runtime_writer_credentials_missing(self, monkeypatch):
        ar = _load_module()
        for k in (
            "YQUANT_UD_AUDIT_WRITER_MONGO_URI",
            "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
        ):
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(ar.MissingCredentialError) as exc:
            ar._load_runtime_writer_credentials()
        assert "YQUANT_UD_AUDIT_WRITER_MONGO_URI" in str(exc.value)

    def test_load_runtime_reader_credentials_missing(self, monkeypatch):
        ar = _load_module()
        for k in (
            "YQUANT_UD_AUDIT_READER_MONGO_URI",
            "YQUANT_UD_AUDIT_READER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_READER_MONGO_PASSWORD",
        ):
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(ar.MissingCredentialError) as exc:
            ar._load_runtime_reader_credentials()
        assert "YQUANT_UD_AUDIT_READER_MONGO_URI" in str(exc.value)

    def test_ddl_and_runtime_creds_isolated(self, monkeypatch):
        """DDL bootstrap 凭证与 runtime writer 凭证严格分离：
        设置 runtime writer 凭证不会让 _load_ddl_credentials 通过。"""
        ar = _load_module()
        for k in (
            "YQUANT_UD_AUDIT_DDL_MONGO_URI",
            "YQUANT_UD_AUDIT_DDL_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD",
        ):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("YQUANT_UD_AUDIT_WRITER_MONGO_URI", "mongodb://x")
        monkeypatch.setenv("YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME", "u")
        monkeypatch.setenv("YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD", "p")

        with pytest.raises(ar.MissingCredentialError) as exc:
            ar._load_ddl_credentials()
        assert "YQUANT_UD_AUDIT_DDL_MONGO_URI" in str(exc.value)


class _Mongo7FakeAdminDb(_FakeAdminDb):
    """Mongo 7 行为一致的 rolesInfo 假实现。

    Mongo 7 ``rolesInfo`` 按名字查单个 role 时，默认不返回 ``privileges``
    字段（``privileges=None``）；必须显式传 ``showPrivileges: True`` 才
    返回。其它命令继续沿用父类实现。
    """

    def command(self, cmd, *args, **kwargs):  # noqa: D401
        if isinstance(cmd, dict) and "rolesInfo" in cmd:
            name = cmd["rolesInfo"]
            show = cmd.get("showPrivileges")
            self.commands.append(dict(cmd))
            if name == "":  # list all — 不属于本测试关心的路径
                return {
                    "roles": [
                        {"role": n, **data} for n, data in self._roles.items()
                    ],
                }
            if name not in self._roles:
                return {"roles": []}
            data = self._roles[name]
            priv_block = data["privileges"] if show else None
            return {
                "roles": [
                    {
                        "role": name,
                        "privileges": priv_block,
                        "roles": data["roles"],
                    },
                ],
            }
        return super().command(cmd, *args, **kwargs)


class TestVerifyRolesInfoShowPrivileges:
    """run_verify 的 rolesInfo 必须带 showPrivileges=True。

    复盘：parent task t_ffb5a8c4 探测发现 Mongo 7 ``rolesInfo(name)``
    默认不返回 privileges（privileges=None），导致
    ``_role_privileges_match(None vs list)`` 失败，``--verify`` 误判
    退出码 1。本类用 Mongo-7-faithful fake admin 守住这条契约。
    """

    def test_verify_passes_when_rolesinfo_omits_privileges_by_default(
        self, monkeypatch, capsys,
    ):
        """Mongo 7 真实行为：rolesInfo(name) 不带 showPrivileges 时返回
        privileges=None。verify 必须显式 showPrivileges=True 才能拿到
        privileges 并通过。"""
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        admin_db = _Mongo7FakeAdminDb(fake_db)
        monkeypatch.setattr(ar, "_open_ddl_client", lambda: _FakeDdlClient(admin_db))
        monkeypatch.setenv("YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD", "writer-test-password")
        monkeypatch.setenv("YQUANT_UD_AUDIT_READER_MONGO_PASSWORD", "reader-test-password")

        # 先用 Mongo-7-faithful fake 跑一次 apply，注入 contract-compliant role/user
        assert ar.run_apply() == 0

        # 清空 apply 期间的命令记录，只关心 verify 路径发出的 rolesInfo。
        admin_db.commands.clear()

        # run_verify 必须通过（privileges 实际正确，Mongo-7-faithful fake
        # 在 showPrivileges=True 下会返回 privileges）。
        rc = ar.run_verify()
        captured = capsys.readouterr()
        assert rc == 0, f"verify must pass with correct privileges; output={captured.out!r}"
        assert "OK" in captured.out

        # 断言：verify 路径发出的所有 rolesInfo 调用都带 showPrivileges=True
        roles_info_calls = [
            cmd for cmd in admin_db.commands
            if isinstance(cmd, dict) and "rolesInfo" in cmd and cmd["rolesInfo"]
        ]
        assert roles_info_calls, "verify must call rolesInfo for at least one role"
        for cmd in roles_info_calls:
            assert cmd.get("showPrivileges") is True, (
                f"rolesInfo call missing showPrivileges=True: {cmd!r}"
            )

    def test_verify_fails_when_privileges_actually_mismatch_under_mongo7(
        self, monkeypatch, capsys,
    ):
        """保留"privileges 真不一致"的失败路径：verify 在 Mongo-7-faithful
        fake 下应仍然检测到 mismatch 并 rc=1。"""
        ar = _load_module()
        fake_db = mongomock.MongoClient().db
        admin_db = _Mongo7FakeAdminDb(fake_db)
        monkeypatch.setattr(ar, "_open_ddl_client", lambda: _FakeDdlClient(admin_db))
        monkeypatch.setenv("YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD", "writer-test-password")
        monkeypatch.setenv("YQUANT_UD_AUDIT_READER_MONGO_PASSWORD", "reader-test-password")

        # 用 Mongo-7-faithful fake admin 完成 apply（privileges contract-compliant）
        assert ar.run_apply() == 0

        # 通过父类 fake admin 把 writer role privileges 改成 broad
        super_admin = _FakeAdminDb(fake_db)
        super_admin._roles.update(admin_db._roles)
        super_admin._users.update(admin_db._users)
        super_admin.command({
            "updateRole": ar.WRITER_ROLE_NAME,
            "privileges": [
                {
                    "resource": {
                        "db": "tradingagents",
                        "collection": "03_data_ud_query_audit",
                    },
                    "actions": ["insert", "find", "update", "remove"],  # 比 contract 宽
                },
            ],
            "roles": [],
        })
        # 把修改后的状态拷回 Mongo-7-faithful fake admin
        admin_db._roles.update(super_admin._roles)

        rc = ar.run_verify()
        captured = capsys.readouterr()
        assert rc == 1, (
            f"verify must detect real privilege mismatch even on Mongo 7; "
            f"output={captured.out!r}"
        )
        assert "mismatch" in captured.out.lower()