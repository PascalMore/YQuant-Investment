# -*- coding: utf-8 -*-
"""Tests for scripts/upgrade/update_submodules.py
(SPEC-10-008 / DESIGN-10-008 / RFC-10-008 V2.0;
 SPEC-10-012 / DESIGN-10-012 / RFC-10-012 V2.2.0).

Covers (SPEC-10-008 §9):
  UT-001 CLI --help
  UT-002 .gitmodules 解析
  UT-003 启发式 venv 推断
  UT-004 启发式 pip_install 推断
  UT-005 启发式 systemd 推断
  UT-006 opt-in 覆盖 venv
  UT-007 opt-in 加载失败回落
  UT-008 behind=0 跳过 merge
  UT-009 merge 冲突 abort
  UT-010 pip 失败 abort
  UT-011 health_check FAIL abort push
  UT-012 health_check None 跳过
  UT-013 --only 过滤（短名）
  UT-014 --only 多次
  UT-015 --only 缺名报错
  UT-016 dry-run no mutation
  UT-017 --apply 与 --dry-run 互斥
  UT-018 upstream 缺失报错
  UT-019 audit 日志生成

Added in v2.2.0 (SPEC-10-012 §5, DESIGN-10-012 §5.1):
  UT-020 install_exclude 字段默认空 tuple
  UT-021 opt-in install_exclude 合法 -> merge 后生效
  UT-022 opt-in install_exclude 非法类型 -> warning + 丢弃
  UT-023 _filter_requirements 锚定行命中, 注释/选项/其他行保留 (Fix-2: -r/-c 重写)
  UT-024 _filter_requirements 禁止子串包含 (bridge 不命中 longbridge)
  UT-025 _filter_requirements 包名 PEP 503 规范化等价
  UT-026 phase_install degraded detail (mock pip exit 0)
  UT-027 phase_install 未命中声明包透明列出
  UT-028 phase_install 无 -r 引用 -> warning + no-op
  UT-029 phase_install tempfile 写失败 -> fail (不静默降级)
  UT-030 classify sample 优先含包名+版本约束 (RFC 2026-10-06 真实文本)
  UT-031 classify sample 回落首个命中行 (仅 yanked)
  UT-032 daily_stock_analysis opt-in merge + 破损回落
  UT-033 version 升 2.2.0 且 CLI 参数面不变
  UT-034 phase_install argv 严格断言 (-r 相对含 pip_bin 前缀的完整 argv, Fix-1 回归)

Fix-2 回归矩阵 (DESIGN-10-012 §5.2; RFC/SPEC/DESIGN 既有契约 + 严格覆盖三缺陷):
  UT-035 _filter_requirements 重写根副本中相对 -r/-c 为原目录绝对路径 (Fix-2 缺陷 A)
  UT-036 pip parser 实际解析嵌套 -r/-c: 重写后引用仍指向原文件, 不递归排除 (Fix-2 缺陷 A)
  UT-037 phase_install 等号形式 --requirement= 保留选项前缀 (Fix-2 缺陷 B)
  UT-038 phase_install 等号形式 -r= 保留选项前缀 (Fix-2 缺陷 B)
  UT-039 phase_install 多根 -r 引用 (同名根副本不互相覆盖) (Fix-2 缺陷 B/C 边界)
  UT-039b phase_install 多根 -r 引用 (同父目录 basename 不互相覆盖) (Fix-3 严格回归)
  UT-040 phase_install 源缺失 -> 临时目录清理 (Fix-2 缺陷 C)
  UT-041 phase_install 写失败 -> 临时目录清理 (Fix-2 缺陷 C)
  UT-042 phase_install pip 失败 -> 临时目录清理 (Fix-2 缺陷 C)
  UT-043 phase_install 成功 -> 临时目录清理 (Fix-2 缺陷 C)
  UT-044 phase_install dry-run -> 临时目录清理 (Fix-2 缺陷 C)
  UT-045 phase_install 无 install_exclude 时 argv 与 v2.1.0 一致 (默认行为回归)
"""
import importlib.util
import glob
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "upgrade" / "update_submodules.py"


# ---------------------------------------------------------------------------
# module loader
# ---------------------------------------------------------------------------


def _load_module():
    name = "update_submodules"
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def us():
    return _load_module()


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def _git(cwd, *args, env=None, check=True):
    r = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, env=env, cwd=str(cwd),
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args} failed in {cwd}: {r.stderr}")
    return r


def _make_repo(path: Path) -> Path:
    """Create a bare git repo and return its path."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--bare")
    return path


def _make_worktree(path: Path, origin_url: str, upstream_url: str = None,
                   branch: str = "main", with_venv: bool = False,
                   with_requirements: bool = False) -> Path:
    """Create a git worktree with origin and optional upstream remote."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--initial-branch", branch)
    _git(path, "remote", "add", "origin", origin_url)
    if upstream_url:
        _git(path, "remote", "add", "upstream", upstream_url)
    # initial commit
    (path / "README.md").write_text("# test\n", encoding="utf-8")
    _git(path, "add", ".")
    env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@test.com",
           "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"}
    _git(path, "commit", "-m", "initial", env=env)
    if with_venv:
        venv_bin = path / ".venv" / "bin"
        venv_bin.mkdir(parents=True, exist_ok=True)
        (venv_bin / "pip").write_text("#!/bin/sh\necho pip mock\n", encoding="utf-8")
        (venv_bin / "pip").chmod(0o755)
    if with_requirements:
        (path / "requirements.txt").write_text("# reqs\n", encoding="utf-8")
    return path


def _make_project(tmp_path: Path, submodules: list[tuple[str, str, bool]]) -> Path:
    """Create a fake project root with .gitmodules.
    submodules: [(name, rel_path, has_upstream)]
    Each submodule is a real git repo under tmp_path/rel_path.
    """
    project = tmp_path / "project"
    project.mkdir(parents=True, exist_ok=True)
    # gitmodules
    lines = []
    for name, rel, _ in submodules:
        lines.append(f'[submodule "{name}"]')
        lines.append(f"\tpath = {rel}")
        lines.append(f"\turl = https://github.com/test/{name}.git")
        lines.append("")
    (project / ".gitmodules").write_text("\n".join(lines), encoding="utf-8")

    # create each submodule repo
    for name, rel, has_up in submodules:
        sub_path = project / rel
        up_url = "https://github.com/upstream/{name}.git" if has_up else None
        _make_worktree(sub_path, f"https://github.com/test/{name}.git",
                       upstream_url=up_url, with_venv=True, with_requirements=True)
    return project


# ---------------------------------------------------------------------------
# UT-001: CLI --help
# ---------------------------------------------------------------------------


class TestCLIHelp:
    def test_help_shows_all_args(self, us):
        r = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        for arg in ("--only", "--push", "--apply", "--dry-run",
                     "--skip-merge", "--skip-install", "--skip-restart",
                     "--resume-after-merge"):
            assert arg in r.stdout, f"missing {arg} in --help"


# ---------------------------------------------------------------------------
# UT-002: .gitmodules 解析
# ---------------------------------------------------------------------------


class TestParseGitmodules:
    def test_parse_two_submodules(self, us, tmp_path):
        project = _make_project(tmp_path, [
            ("skills/research/daily_stock_analysis",
             "skills/research/daily_stock_analysis", True),
            ("skills/apps/TradingAgents-CN",
             "skills/apps/TradingAgents-CN", True),
        ])
        result = us.parse_gitmodules(project)
        assert len(result) == 2
        names = [n for n, _ in result]
        assert "skills/research/daily_stock_analysis" in names
        assert "skills/apps/TradingAgents-CN" in names

    def test_no_gitmodules(self, us, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = us.parse_gitmodules(empty)
        assert result == []


# ---------------------------------------------------------------------------
# UT-003/004: 启发式 venv / pip_install 推断
# ---------------------------------------------------------------------------


class TestHeuristicDiscovery:
    def test_normalize_remote_branch(self, us):
        assert us.normalize_remote_branch("origin/main") == "main"
        assert us.normalize_remote_branch("refs/remotes/origin/main") == "main"
        assert us.normalize_remote_branch("origin/feature/x") == "feature/x"
        assert us.normalize_remote_branch("main") == "main"
        assert us.normalize_remote_branch("origin/HEAD") is None

    def test_parse_origin_head_strips_short_remote_prefix(self, us, tmp_path):
        sub_path = tmp_path / "repo"
        sub_path.mkdir()
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=str(sub_path), exit_code=0,
                stdout="origin/main\n", stderr=""
            )
            assert us.parse_origin_head(sub_path) == "main"

    def test_venv_and_pip_detected(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        assert cfg.venv == Path(".venv")
        assert cfg.pip_install_cmd == ("install", "-r", "requirements.txt")

    def test_no_venv_no_pip(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub2", "sub2", True)])
        sub_path = project / "sub2"
        # remove venv and requirements
        import shutil
        shutil.rmtree(sub_path / ".venv")
        (sub_path / "requirements.txt").unlink()
        cfg = us.discover_submodule("sub2", Path("sub2"), project)
        assert cfg.venv is None
        assert cfg.pip_install_cmd is None

    def test_upstream_detected(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub3", "sub3", True)])
        cfg = us.discover_submodule("sub3", Path("sub3"), project)
        assert cfg.upstream is not None
        assert "upstream" in cfg.upstream

    def test_upstream_missing_sets_none(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub4", "sub4", False)])
        cfg = us.discover_submodule("sub4", Path("sub4"), project)
        assert cfg.upstream is None

    def test_health_check_default_none(self, us, tmp_path):
        """V2.0: health_check 默认 None (A-022)."""
        project = _make_project(tmp_path, [("sub5", "sub5", True)])
        cfg = us.discover_submodule("sub5", Path("sub5"), project)
        assert cfg.health_check is None


# ---------------------------------------------------------------------------
# UT-005: 启发式 systemd 推断
# ---------------------------------------------------------------------------


class TestSystemdMatch:
    def test_match_systemd_unit(self, us, tmp_path):
        mock_output = (
            "daily-stock-analysis.service loaded active running Daily Stock Analysis\n"
            "other.service loaded active running Other\n"
        )
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=0, stdout=mock_output, stderr=""
            )
            result = us.match_systemd_unit(Path("/some/daily_stock_analysis"))
            assert result == "daily-stock-analysis.service"

    def test_no_match_returns_none(self, us, tmp_path):
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=0,
                stdout="unrelated.service loaded active running\n", stderr=""
            )
            result = us.match_systemd_unit(Path("/some/random_path"))
            assert result is None


# ---------------------------------------------------------------------------
# UT-006/007: opt-in override
# ---------------------------------------------------------------------------


class TestOptinOverride:
    def test_load_optin_override_applies(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        # write opt-in
        optin = sub_path / us.OPTIN_FILENAME
        optin.write_text(
            "schema_version: 1\n"
            "health_check: \"systemctl --user is-active --quiet test.service\"\n"
            "branch: develop\n",
            encoding="utf-8",
        )
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        override = us.load_optin_override(sub_path)
        assert override is not None
        merged = us.merge_override(cfg, override)
        assert merged.health_check == "systemctl --user is-active --quiet test.service"
        assert merged.branch == "develop"
        assert merged.config_source == "heuristic+opt-in"

    def test_optin_venv_override(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub2", "sub2", True)])
        sub_path = project / "sub2"
        optin = sub_path / us.OPTIN_FILENAME
        optin.write_text("schema_version: 1\nvenv: custom_venv\n", encoding="utf-8")
        cfg = us.discover_submodule("sub2", Path("sub2"), project)
        override = us.load_optin_override(sub_path)
        merged = us.merge_override(cfg, override)
        assert merged.venv == Path("custom_venv")

    def test_optin_skip_push(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub3", "sub3", True)])
        sub_path = project / "sub3"
        optin = sub_path / us.OPTIN_FILENAME
        optin.write_text("schema_version: 1\nskip_push: true\n", encoding="utf-8")
        cfg = us.discover_submodule("sub3", Path("sub3"), project)
        override = us.load_optin_override(sub_path)
        merged = us.merge_override(cfg, override)
        assert merged.skip_push is True

    def test_optin_not_exists_returns_none(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub4", "sub4", True)])
        sub_path = project / "sub4"
        result = us.load_optin_override(sub_path)
        assert result is None

    def test_optin_bad_schema_returns_none(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub5", "sub5", True)])
        sub_path = project / "sub5"
        optin = sub_path / us.OPTIN_FILENAME
        optin.write_text("schema_version: not_a_number\nbranch: main\n", encoding="utf-8")
        result = us.load_optin_override(sub_path)
        assert result is None

    def test_optin_stdlib_fallback_yaml(self, us, tmp_path):
        """Test stdlib YAML fallback parser (no PyYAML)."""
        project = _make_project(tmp_path, [("sub6", "sub6", True)])
        sub_path = project / "sub6"
        optin = sub_path / us.OPTIN_FILENAME
        optin.write_text(
            "schema_version: 1\n"
            "pre_merge_hooks:\n"
            '  - "git stash push -u -m pre-update"\n'
            "health_check: \"echo ok\"\n",
            encoding="utf-8",
        )
        # Force stdlib fallback by mocking yaml import failure
        with patch.dict(sys.modules, {"yaml": None}):
            raw = us.load_yaml(optin)
        assert raw.get("schema_version") == 1
        assert "pre_merge_hooks" in raw


# ---------------------------------------------------------------------------
# UT-018: upstream 缺失报错 (V2.0 关键)
# ---------------------------------------------------------------------------


class TestUpstreamMissing:
    def test_validate_upstream_missing(self, us, tmp_path):
        project = _make_project(tmp_path, [("nosub", "nosub", False)])
        cfg = us.discover_submodule("nosub", Path("nosub"), project)
        errors = us.validate_submodule(cfg)
        assert len(errors) > 0
        assert any("upstream" in e for e in errors)
        # 不自动 add (提示用户手动 git remote add)
        assert any("remote add" in e for e in errors)

    def test_phase_fetch_upstream_none_aborts(self, us, tmp_path):
        project = _make_project(tmp_path, [("nosub2", "nosub2", False)])
        cfg = us.discover_submodule("nosub2", Path("nosub2"), project)
        assert cfg.upstream is None
        state = us.SubmoduleState(
            config=cfg, abs_path=(project / "nosub2").resolve(),
            pre_head=None, behind=0, ahead=0, upstream_ref="",
        )
        pr = us.phase_fetch(state, dry_run=True)
        assert pr.status == "fail"
        assert "upstream" in pr.detail


# ---------------------------------------------------------------------------
# UT-008: behind=0 跳过 merge
# ---------------------------------------------------------------------------


class TestBehindZero:
    def test_behind_zero_skips_merge(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        state = us.SubmoduleState(
            config=cfg, abs_path=(project / "sub1").resolve(),
            pre_head="abc", behind=0, ahead=0, upstream_ref="upstream/main",
        )
        pr = us.phase_merge(state, dry_run=True)
        assert pr.status == "skip"
        assert "behind=0" in pr.detail


# ---------------------------------------------------------------------------
# UT-009: merge 冲突 abort
# ---------------------------------------------------------------------------


class TestMergeConflict:
    def test_merge_conflict_aborts(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        state = us.SubmoduleState(
            config=cfg, abs_path=(project / "sub1").resolve(),
            pre_head="abc", behind=1, ahead=1, upstream_ref="upstream/main",
        )
        # mock merge failure + conflict status
        call_count = [0]
        def mock_run(cmd, **kwargs):
            call_count[0] += 1
            if "merge" in cmd and "--abort" not in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=1,
                                        stdout="", stderr="CONFLICT")
            if "status" in cmd and "--porcelain" in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                        stdout="UU\tfile.py\n", stderr="")
            if "--abort" in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                        stdout="", stderr="")
            return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                    stdout="", stderr="")
        with patch.object(us, "run_cmd", side_effect=mock_run):
            pr = us.phase_merge(state, dry_run=False)
        assert pr.status == "fail"
        assert "冲突" in pr.detail or "abort" in pr.detail.lower()


# ---------------------------------------------------------------------------
# UT-010: pip 失败 abort
# ---------------------------------------------------------------------------


class TestInstallFail:
    def test_pip_fail_aborts(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        state = us.SubmoduleState(
            config=cfg, abs_path=(project / "sub1").resolve(),
            pre_head="abc", behind=0, ahead=0, upstream_ref="upstream/main",
        )
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=1, stdout="",
                stderr="pip install error",
            )
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "fail"
        assert "pip" in pr.detail.lower()

    def test_install_skip_no_venv(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub2", "sub2", True)])
        import shutil
        shutil.rmtree(project / "sub2" / ".venv")
        cfg = us.discover_submodule("sub2", Path("sub2"), project)
        state = us.SubmoduleState(
            config=cfg, abs_path=(project / "sub2").resolve(),
            pre_head="abc", behind=0, ahead=0, upstream_ref="upstream/main",
        )
        pr = us.phase_install(state, dry_run=False)
        assert pr.status == "skip"


# ---------------------------------------------------------------------------
# UT-011/012: health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_health_check_none_skips(self, us, tmp_path):
        """UT-012: health_check=None 时 Phase 4 跳过 health check.

        P-7/P-13: phase_restart now also waits for ``systemctl --user is-active``
        to report "active".  The mock below returns "active" so the wait
        passes and the restart phase reports PASS.
        """
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        assert cfg.health_check is None  # V2.0 default
        state = us.SubmoduleState(
            config=cfg, abs_path=(project / "sub1").resolve(),
            pre_head="abc", behind=0, ahead=0, upstream_ref="upstream/main",
        )
        # mock systemd_service to trigger restart phase
        state.config = us._replace_config(cfg, {"systemd_service": "test.service"},
                                          cfg.config_source)
        def mock_run(cmd, **kwargs):
            if "is-active" in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                        stdout="active\n", stderr="")
            return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                     stdout="", stderr="")
        with patch.object(us, "run_cmd", side_effect=mock_run):
            pr = us.phase_restart(state, dry_run=False)
        assert pr.status == "pass"
        assert "SKIP" in pr.detail or "skip" in pr.detail.lower()

    def test_health_check_fail_aborts_push(self, us, tmp_path):
        """UT-011: health_check FAIL aborts push.

        Same is-active mock as above so we exercise the full happy path
        before hitting the shell-failing health_check.
        """
        project = _make_project(tmp_path, [("sub2", "sub2", True)])
        cfg = us.discover_submodule("sub2", Path("sub2"), project)
        # set health_check to a cmd
        cfg2 = us._replace_config(cfg,
                                   {"systemd_service": "svc.service",
                                    "health_check": "curl -f http://localhost:9999"},
                                   cfg.config_source)
        state = us.SubmoduleState(
            config=cfg2, abs_path=(project / "sub2").resolve(),
            pre_head="abc", behind=0, ahead=0, upstream_ref="upstream/main",
        )
        call_count = [0]
        def mock_run(cmd, **kwargs):
            call_count[0] += 1
            if "restart" in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                        stdout="", stderr="")
            if "is-active" in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                        stdout="active\n", stderr="")
            if "sh" in cmd and "-c" in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=1,
                                        stdout="", stderr="connection refused")
            return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                     stdout="", stderr="")
        with patch.object(us, "run_cmd", side_effect=mock_run):
            pr = us.phase_restart(state, dry_run=False)
        assert pr.status == "fail"
        assert "health" in pr.detail.lower()

    def test_wait_for_active_fails_when_inactive(self, us, tmp_path):
        """P-7: when restart returns 0 but unit never enters active within
        the wait window, phase_restart must surface that as FAIL rather than
        silently pass.
        """
        project = _make_project(tmp_path, [("sub3", "sub3", True)])
        cfg = us.discover_submodule("sub3", Path("sub3"), project)
        cfg2 = us._replace_config(cfg, {"systemd_service": "stuck.service"},
                                  cfg.config_source)
        state = us.SubmoduleState(
            config=cfg2, abs_path=(project / "sub3").resolve(),
            pre_head="abc", behind=0, ahead=0, upstream_ref="upstream/main",
        )
        import time as _t
        original_sleep = us.time.sleep
        try:
            # patch sleep so the wait window passes instantly
            us.time.sleep = lambda *_a, **_kw: None
            def mock_run(cmd, **kwargs):
                if "restart" in cmd:
                    return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                             stdout="", stderr="")
                if "is-active" in cmd:
                    return us.CommandResult(cmd=cmd, cwd=None, exit_code=3,
                                             stdout="", stderr="inactive")
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                         stdout="", stderr="")
            with patch.object(us, "run_cmd", side_effect=mock_run):
                pr = us.phase_restart(state, dry_run=False)
        finally:
            us.time.sleep = original_sleep
        assert pr.status == "fail"
        assert "active" in pr.detail.lower()

    def test_wait_for_active_zero_timeout(self, us):
        """P-7: timeout_s=0 means 'skip wait' semantics still produce a
        deterministic, non-blocking poll.
        """
        with patch.object(us, "time") as mock_time:
            mock_time.time.side_effect = [100.0, 100.0, 100.0]
            def mock_run(cmd, **kwargs):
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                         stdout="active\n", stderr="")
            with patch.object(us, "run_cmd", side_effect=mock_run):
                ok, detail = us._wait_for_active_state("anything",
                                                         timeout_s=0.01,
                                                         poll_s=0.0)
        assert ok is True
        assert "active" in detail.lower()


# ---------------------------------------------------------------------------
# UT-013/014/015: --only filter
# ---------------------------------------------------------------------------


class TestOnlyFilter:
    def test_only_short_name_match(self, us, tmp_path):
        subs = [
            ("skills/research/daily_stock_analysis", Path("skills/research/daily_stock_analysis")),
            ("skills/apps/TradingAgents-CN", Path("skills/apps/TradingAgents-CN")),
        ]
        result = us.filter_by_only(subs, ["daily_stock_analysis"])
        assert len(result) == 1
        assert result[0][0] == "skills/research/daily_stock_analysis"

    def test_only_short_name_hyphen_normalized(self, us):
        """用户用 daily-stock-analysis (连字符) 匹配 daily_stock_analysis (下划线)."""
        subs = [
            ("skills/research/daily_stock_analysis", Path("skills/research/daily_stock_analysis")),
        ]
        result = us.filter_by_only(subs, ["daily-stock-analysis"])
        assert len(result) == 1

    def test_only_full_name_match(self, us):
        subs = [
            ("skills/research/daily_stock_analysis", Path("skills/research/daily_stock_analysis")),
        ]
        result = us.filter_by_only(subs, ["skills/research/daily_stock_analysis"])
        assert len(result) == 1

    def test_only_multiple(self, us):
        subs = [
            ("skills/research/daily_stock_analysis", Path("skills/research/daily_stock_analysis")),
            ("skills/apps/TradingAgents-CN", Path("skills/apps/TradingAgents-CN")),
        ]
        result = us.filter_by_only(subs, ["daily_stock_analysis", "TradingAgents-CN"])
        assert len(result) == 2

    def test_only_no_match_exit1(self, us):
        subs = [
            ("skills/research/daily_stock_analysis", Path("skills/research/daily_stock_analysis")),
        ]
        with pytest.raises(SystemExit) as exc_info:
            us.filter_by_only(subs, ["nonexistent"])
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# UT-016: dry-run no mutation
# ---------------------------------------------------------------------------


class TestDryRunNoMutation:
    def test_dry_run_does_not_mutate(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        # record git state
        before = _git(sub_path, "rev-parse", "HEAD").stdout.strip()
        result = us.process_submodule(
            "sub1", Path("sub1"), project, dry_run=True,
        )
        after = _git(sub_path, "rev-parse", "HEAD").stdout.strip()
        assert before == after, "dry-run should not change HEAD"


# ---------------------------------------------------------------------------
# UT-017: --apply 与 --dry-run 互斥
# ---------------------------------------------------------------------------


class TestMutexArgs:
    def test_apply_dry_run_mutex(self, us):
        rc = us.main(["--apply", "--dry-run",
                      "--repo-root", "/tmp", "--no-audit"])
        assert rc == 2

    def test_skip_merge_resume_mutex(self, us):
        rc = us.main(["--skip-merge", "--resume-after-merge",
                      "--repo-root", "/tmp", "--no-audit"])
        assert rc == 2


# ---------------------------------------------------------------------------
# UT-019: audit 日志生成
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_audit_log_generated(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        rc = us.main([
            "--dry-run",
            "--repo-root", str(project),
            "--audit-dir", str(audit_dir),
        ])
        assert rc == 0
        audit_files = list(audit_dir.glob("update_submodules_audit_*.md"))
        assert len(audit_files) >= 1
        content = audit_files[0].read_text(encoding="utf-8")
        assert "## Config" in content
        assert "## Summary" in content
        assert "sub1" in content


# ---------------------------------------------------------------------------
# Process pipeline integration
# ---------------------------------------------------------------------------


class TestProcessSubmodule:
    def test_process_pass_with_upstream(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        result = us.process_submodule(
            "sub1", Path("sub1"), project, dry_run=True,
        )
        assert result.overall == "pass"
        assert len(result.phases) == 5
        # push should be skip (no --push)
        push_phase = [p for p in result.phases if p.phase == "push"][0]
        assert push_phase.status == "skip"

    def test_process_fail_no_upstream(self, us, tmp_path):
        project = _make_project(tmp_path, [("nosub", "nosub", False)])
        result = us.process_submodule(
            "nosub", Path("nosub"), project, dry_run=True,
        )
        assert result.overall == "fail"
        fetch_phase = [p for p in result.phases if p.phase == "fetch"][0]
        assert fetch_phase.status == "fail"
        assert "upstream" in fetch_phase.detail


# -------------------------------------------------------------------
# P-2: upstream default branch detection
# -------------------------------------------------------------------


class TestUpstreamDefaultBranch:
    def test_detect_via_remote_show(self, us, tmp_path):
        """upstream/main in `git remote show upstream` -> branch=main."""
        sub_path = tmp_path / "repo"
        sub_path.mkdir()

        def mock_run(cmd, **kwargs):
            if "symbolic-ref" in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=1,
                                         stdout="", stderr="")
            if cmd[:3] == ["git", "remote", "show"]:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                         stdout="  HEAD branch: main\n"
                                                "  Remote branches: foo\n",
                                         stderr="")
            if cmd[:3] == ["git", "rev-parse", "--verify"]:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                         stdout="abc", stderr="")
            return us.CommandResult(cmd=cmd, cwd=None, exit_code=1,
                                    stdout="", stderr="")
        with patch.object(us, "run_cmd", side_effect=mock_run):
            branch = us._detect_upstream_default_branch(sub_path)
        assert branch == "main"

    def test_detect_falls_back_to_probe(self, us, tmp_path):
        """When HEAD branch isn't set but upstream/develop ref exists, return develop."""
        sub_path = tmp_path / "repo"
        sub_path.mkdir()

        def mock_run(cmd, **kwargs):
            if "symbolic-ref" in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=1,
                                         stdout="", stderr="")
            if cmd[:3] == ["git", "remote", "show"]:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                         stdout="  Remote branches:\n",
                                         stderr="")
            if cmd[:3] == ["git", "rev-parse", "--verify"]:
                if "upstream/develop" in cmd:
                    return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                             stdout="abc", stderr="")
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=1,
                                         stdout="", stderr="")
            return us.CommandResult(cmd=cmd, cwd=None, exit_code=1,
                                    stdout="", stderr="")
        with patch.object(us, "run_cmd", side_effect=mock_run):
            branch = us._detect_upstream_default_branch(sub_path)
        assert branch == "develop"

    def test_detect_returns_none_when_nothing(self, us, tmp_path):
        sub_path = tmp_path / "repo"
        sub_path.mkdir()
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=1, stdout="", stderr="")
            assert us._detect_upstream_default_branch(sub_path) is None

    def test_discover_branch_priority(self, us, tmp_path):
        """opt-in > upstream > origin > 'main'."""
        sub_path = tmp_path / "repo"
        sub_path.mkdir()
        with patch.object(us, "_detect_upstream_default_branch",
                          return_value="detect-A") as m_upstream:
            with patch.object(us, "parse_origin_head",
                              return_value="origin-B") as m_origin:
                assert us._discover_branch(sub_path, optin_branch=None) == "detect-A"
                assert us._discover_branch(sub_path, optin_branch="optin-C") == "optin-C"
                m_upstream.return_value = None
                assert us._discover_branch(sub_path, optin_branch=None) == "origin-B"
                m_origin.return_value = None
                assert us._discover_branch(sub_path, optin_branch=None) == "main"
                m_upstream.assert_called()
                m_origin.assert_called()


# -------------------------------------------------------------------
# P-6: pip failure classification
# -------------------------------------------------------------------


class TestPipFailureClassification:
    def test_classify_platform_incompatible_glibc_hint(self, us):
        stderr = (
            "  Skipping link: none of the wheel's tags (cp312-cp312-manylinux_2_39_x86_64) "
            "are compatible (Requires-Python: >=3.8)\n"
            "ERROR: No matching distribution found for longbridge==4.2.0\n"
        )
        kind, sample = us.classify_pip_failure(stderr)
        assert kind == "platform_incompatible"
        assert "manylinux" in sample

    def test_classify_missing_dependency(self, us):
        stderr = "ERROR: Could not find a version that satisfies the requirement foo==99.99\n"
        kind, sample = us.classify_pip_failure(stderr)
        assert kind == "missing_dependency"
        assert "foo==99.99" in sample

    def test_classify_source_build_error(self, us):
        stderr = (
            "      feature `edition2024` is required\n"
            "      The package requires the Cargo feature called `edition2024`\n"
        )
        kind, _ = us.classify_pip_failure(stderr)
        assert kind == "source_build_error"

    def test_classify_network_error(self, us):
        stderr = "Could not fetch URL https://pypi.org/simple/foo/: NewConnectionError\n"
        kind, _ = us.classify_pip_failure(stderr)
        assert kind == "network_error"

    def test_classify_resolution_conflict(self, us):
        stderr = "ResolutionImpossible: for some-package\n"
        kind, _ = us.classify_pip_failure(stderr)
        assert kind == "resolution_conflict"

    def test_classify_other(self, us):
        stderr = "Weird unrelated error message\n"
        kind, _ = us.classify_pip_failure(stderr)
        assert kind == "other"

    def test_classify_empty(self, us):
        assert us.classify_pip_failure("") == ("other", "")

    def test_install_phase_failure_uses_classification(self, us, tmp_path):
        """phase_install FAIL detail should include the classification bucket
        and the hint, so the audit log is immediately actionable.
        """
        project = _make_project(tmp_path, [("ip", "ip", True)])
        cfg = us.discover_submodule("ip", Path("ip"), project)
        state = us.SubmoduleState(
            config=cfg, abs_path=(project / "ip").resolve(),
            pre_head="abc", behind=0, ahead=0, upstream_ref="upstream/main",
        )
        stderr = "ERROR: Could not find a version that satisfies the requirement foo==99\n"
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=1,
                stdout="", stderr=stderr,
            )
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "fail"
        assert "(missing_dependency)" in pr.detail
        assert "hint" in pr.detail.lower()


# -------------------------------------------------------------------
# P-15: conflict file list
# -------------------------------------------------------------------


class TestConflictFiles:
    def test_collect_conflict_files_basic(self, us):
        status = (
            "UU\tsrc/market_analyzer.py\n"
            "AA\tdocs/full-guide.md\n"
            " M\tother.py\n"
            "??\tnew_file\n"
            "UD\t.env.example\n"
        )
        files = us._collect_conflict_files(status)
        assert files == ["src/market_analyzer.py",
                          "docs/full-guide.md", ".env.example"]

    def test_collect_conflict_files_empty(self, us):
        assert us._collect_conflict_files("") == []
        assert us._collect_conflict_files(" M\tsrc/foo.py\n") == []

    def test_conflict_files_dedupe(self, us):
        status = "UU\tsrc/market_analyzer.py\nUU\tsrc/market_analyzer.py\n"
        files = us._collect_conflict_files(status)
        assert files == ["src/market_analyzer.py"]

    def test_merge_conflict_lists_files_in_detail(self, us, tmp_path):
        """phase_merge FAIL detail must include the file list (P-15)."""
        project = _make_project(tmp_path, [("cf", "cf", True)])
        cfg = us.discover_submodule("cf", Path("cf"), project)
        state = us.SubmoduleState(
            config=cfg, abs_path=(project / "cf").resolve(),
            pre_head="abc", behind=1, ahead=1, upstream_ref="upstream/main",
        )
        def mock_run(cmd, **kwargs):
            if "merge" in cmd and "--abort" not in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=1,
                                         stdout="", stderr="CONFLICT")
            if "status" in cmd and "--porcelain" in cmd:
                return us.CommandResult(
                    cmd=cmd, cwd=None, exit_code=0,
                    stdout=("UU\tsrc/market_analyzer.py\n"
                            "AA\tdocs/full-guide.md\n"),
                    stderr="")
            if "--abort" in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                         stdout="", stderr="")
            return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                     stdout="", stderr="")
        with patch.object(us, "run_cmd", side_effect=mock_run):
            pr = us.phase_merge(state, dry_run=False)
        assert pr.status == "fail"
        assert "src/market_analyzer.py" in pr.detail
        assert "docs/full-guide.md" in pr.detail
        assert "2 files" in pr.detail


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


class TestRedact:
    def test_redact_token(self, us):
        text = "token=ghp_1234567890abcdefghijklmnop"
        result = us.redact(text)
        assert "ghp_" not in result
        assert "REDACTED" in result

    def test_redact_long_hex(self, us):
        text = "key=abcdef0123456789abcdef0123456789abcdef01"
        result = us.redact(text)
        assert "REDACTED" in result


# ---------------------------------------------------------------------------
# YAML stdlib fallback parser
# ---------------------------------------------------------------------------


class TestStdlibYaml:
    def test_simple_key_value(self, us):
        text = "schema_version: 1\nbranch: main\n"
        result = us._parse_simple_yaml(text)
        assert result.get("schema_version") == 1
        assert result.get("branch") == "main"

    def test_null_value(self, us):
        text = "health_check: null\nvenv: ~\n"
        result = us._parse_simple_yaml(text)
        assert result.get("health_check") is None
        assert result.get("venv") is None

    def test_quoted_string(self, us):
        text = 'notes: "hello world"\n'
        result = us._parse_simple_yaml(text)
        assert result.get("notes") == "hello world"

    def test_list_values(self, us):
        text = (
            "schema_version: 1\n"
            "pre_merge_hooks:\n"
            '  - "git stash"\n'
            '  - "echo done"\n'
        )
        result = us._parse_simple_yaml(text)
        assert "pre_merge_hooks" in result


# -----------------------------------------------------------------------
# v2.2.0 (RFC-10-012 / SPEC-10-012) install_exclude + classify sample
# -----------------------------------------------------------------------


# RFC-10-012 §5.2 / DESIGN-10-012 §5.2 冻结文本, 逐字取自 2026-10-06 audit
REAL_PIP_STDERR_20261006 = (
    "ERROR: Ignored the following yanked versions: 0.2.2, 0.2.3, 0.2.4, 0.2.5, 0.2.6\n"
    "ERROR: No matching distribution found for longbridge<5,>=4.0.5\n"
)

# DESIGN-10-012 §5.2 过滤用 requirements fixture
REQUIREMENTS_FIXTURE = (
    "tushare>=1.4.0              # Priority 2\n"
    "-r extra-reqs.txt\n"
    "# Longbridge 4.x Linux wheels currently require manylinux_2_39.\n"
    'longbridge>=4.0.5,<5; platform_system != "Linux" or python_version >= "3.12"\n'
    'longbridge==0.2.74; platform_system == "Linux" and python_version < "3.12"\n'
    "tickflow>=0.1.24\n"
)


class TestInstallExcludeConfig:
    """UT-020 ~ UT-022: install_exclude 字段声明 / 透传 / 非法类型."""

    def test_install_exclude_field_default(self, us, tmp_path):
        """A-100: 启发式构造的 config.install_exclude 默认空 tuple."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        assert cfg.install_exclude == ()

    def test_optin_install_exclude_applies(self, us, tmp_path):
        """A-100: opt-in 声明 list[str] -> merge 后 tuple."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / us.OPTIN_FILENAME).write_text(
            "schema_version: 1\n"
            "install_exclude:\n"
            "  - longbridge\n"
            "  - Some_Pkg.Name\n",
            encoding="utf-8",
        )
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        override = us.load_optin_override(sub_path)
        merged = us.merge_override(cfg, override)
        assert merged.install_exclude == ("longbridge", "Some_Pkg.Name")
        assert merged.config_source == "heuristic+opt-in"

    def test_optin_install_exclude_invalid_type(self, us, tmp_path):
        """A-101: 非 list / 元素非 str -> warning + 丢弃, config 为空 tuple."""
        # 非 list: 字符串
        bad = us.validate_override({"schema_version": 1, "install_exclude": "longbridge"})
        assert bad is not None
        assert "install_exclude" not in bad
        # 元素非 str
        bad2 = us.validate_override(
            {"schema_version": 1, "install_exclude": ["ok", 42, "fine"]}
        )
        assert bad2 is not None
        assert "install_exclude" not in bad2
        # 空字符串元素也视作非法
        bad3 = us.validate_override(
            {"schema_version": 1, "install_exclude": ["ok", ""]}
        )
        assert bad3 is not None
        assert "install_exclude" not in bad3


class TestFilterRequirements:
    """UT-023 ~ UT-025: _filter_requirements 行处理语义."""

    def _write_req(self, tmp_path: Path, content: str = REQUIREMENTS_FIXTURE,
                    name: str = "requirements.txt") -> Path:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_filter_requirements_anchored_line(self, us, tmp_path):
        """A-102: 排除 longbridge -> 两 longbridge 行删, 注释/选项/其他行保留.

        Fix-2 / SPEC §4.2 / DESIGN §3.4: 副本中保留的 -r/-c 引用必须重写为
        原目录的绝对路径 (但选项与嵌套目标解析不变). 此处 -r extra-reqs.txt
        路径被重写, 但选项前缀 `-r ` 与文件基名 `extra-reqs.txt` 仍可识别.
        """
        import re as _re
        req = self._write_req(tmp_path)
        out, hits = us._filter_requirements(req, ("longbridge",))
        out_text = out.read_text(encoding="utf-8")
        # 注释 / tushare / tickflow 行原样保留
        assert "tushare>=1.4.0              # Priority 2" in out_text
        assert "# Longbridge 4.x Linux wheels currently require manylinux_2_39." in out_text
        assert "tickflow>=0.1.24" in out_text
        # 嵌套 -r extra-reqs.txt 重写为原目录绝对路径 (option 与 base name 保留)
        assert "-r " in out_text
        assert "extra-reqs.txt" in out_text
        assert str(req.parent.resolve()) in out_text  # 原目录绝对路径前缀
        # longbridge 包行 (行首 longbridge, 锚定) 应全部删除
        assert not _re.search(r"^longbridge\b", out_text, _re.MULTILINE)
        # 命中列表: 两个 longbridge 行去重 -> 单元素
        assert hits == ["longbridge"]

    def test_filter_requirements_no_substring_match(self, us, tmp_path):
        """A-103: 排除 bridge 不得命中 longbridge (PEP 503 锚定, 非子串)."""
        req = self._write_req(tmp_path)
        out, hits = us._filter_requirements(req, ("bridge",))
        out_text = out.read_text(encoding="utf-8")
        # 所有 longbridge 行原样保留
        assert "longbridge>=4.0.5,<5" in out_text
        assert "longbridge==0.2.74" in out_text
        assert hits == []

    def test_filter_requirements_pkg_name_normalized(self, us, tmp_path):
        """A-104: longbridge / LONGBRIDGE / long-bridge 在 PEP 503 下互为等价.

        SPEC §4.2 严格 PEP 503 规则:
          - `longbridge` / `LONGBRIDGE` (无分隔符) -> canonical `longbridge`;
          - `long-bridge` / `Long_Bridge` / `long.bridge` (有分隔符) -> canonical `long-bridge`.
        两者在 PEP 503 下不相等 (PyPI 上也是两个不同的包名).
        """
        import re as _re
        # 行首包名行 (非注释行) 含 longbridge 应被全部删除
        pkg_row_re = _re.compile(r"^longbridge\b", _re.MULTILINE)
        # 等价集合 1: longbridge / LONGBRIDGE / LongBridge 都规范化为 longbridge
        for declared in ("longbridge", "LONGBRIDGE", "LongBridge"):
            req = self._write_req(tmp_path)
            out, hits = us._filter_requirements(req, (declared,))
            out_text = out.read_text(encoding="utf-8")
            assert not pkg_row_re.search(out_text), (
                f"declared={declared!r} should remove all longbridge package rows"
            )
            assert hits == ["longbridge"], (
                f"declared={declared!r} hits={hits!r}"
            )
        # 等价集合 2: long-bridge / Long_Bridge / long.bridge 都规范化为 long-bridge,
        # 与 `longbridge` 不等价 (PEP 503 不同 canonical form), 故不应误命中
        for declared in ("long-bridge", "Long_Bridge", "long.bridge"):
            req = self._write_req(tmp_path)
            out, hits = us._filter_requirements(req, (declared,))
            out_text = out.read_text(encoding="utf-8")
            assert _re.search(r"^longbridge\b", out_text, _re.MULTILINE), (
                f"declared={declared!r} (PEP 503: long-bridge) should NOT match "
                f"`longbridge` rows"
            )
            assert hits == [], (
                f"declared={declared!r} hits={hits!r} (expected empty)"
            )

    def test_filter_requirements_comment_and_option_preserved(self, us, tmp_path):
        """SPEC §4.2: 行内注释 + 行尾注释, 注释行不被误判为包行."""
        content = (
            "# comment\n"
            "--index-url https://pypi.org/simple\n"
            "tushare>=1.4.0  # inline comment\n"
            "longbridge>=4.0.5,<5; marker\n"
        )
        req = self._write_req(tmp_path, content)
        out, hits = us._filter_requirements(req, ("longbridge",))
        out_text = out.read_text(encoding="utf-8")
        assert "# comment" in out_text
        assert "--index-url https://pypi.org/simple" in out_text
        assert "tushare>=1.4.0  # inline comment" in out_text
        assert "longbridge" not in out_text
        assert hits == ["longbridge"]


class TestPhaseInstallDegraded:
    """UT-026 ~ UT-029: phase_install 在 install_exclude 配置下的行为."""

    @staticmethod
    def _make_state(us, project, name, pip_install_cmd=None,
                     install_exclude=()):
        cfg = us.discover_submodule(name, Path(name), project)
        if pip_install_cmd is not None or install_exclude:
            cfg = us._replace_config(cfg, {
                "pip_install_cmd": pip_install_cmd if pip_install_cmd is not None
                else cfg.pip_install_cmd,
                "install_exclude": install_exclude,
            }, cfg.config_source)
        state = us.SubmoduleState(
            config=cfg, abs_path=(project / name).resolve(),
            pre_head="abc", behind=0, ahead=0, upstream_ref="upstream/main",
        )
        return state

    def test_phase_install_degraded_detail(self, us, tmp_path):
        """A-105: pip 成功 + 有命中 -> degraded detail + status=pass."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        # 写 requirements + extra-reqs (后者被 -r 引用, 也含 longbridge 行)
        (sub_path / "requirements.txt").write_text(REQUIREMENTS_FIXTURE, encoding="utf-8")
        (sub_path / "extra-reqs.txt").write_text("longbridge==0.2.74\n", encoding="utf-8")
        state = self._make_state(
            us, project, "sub1",
            pip_install_cmd=("install", "-r", "requirements.txt"),
            install_exclude=("longbridge",),
        )
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=0, stdout="", stderr="")
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "pass"
        assert "(excluded: longbridge)" in pr.detail
        assert "OK (degraded)" in pr.detail

    def test_phase_install_exclude_miss_listing(self, us, tmp_path):
        """A-106: 声明包未命中 -> 普通 OK + miss 清单 (无 degraded 字样)."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / "requirements.txt").write_text("tushare>=1.4.0\n", encoding="utf-8")
        state = self._make_state(
            us, project, "sub1",
            pip_install_cmd=("install", "-r", "requirements.txt"),
            install_exclude=("nonexistent_pkg",),
        )
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=0, stdout="", stderr="")
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "pass"
        assert "OK" in pr.detail
        assert "degraded" not in pr.detail
        assert "nonexistent_pkg" in pr.detail  # miss 清单透明列出

    def test_phase_install_no_r_ref_warning_noop(self, us, tmp_path, capsys):
        """A-107: pip_install_cmd 无 -r -> warning + 排除 no-op + audit OK."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        state = self._make_state(
            us, project, "sub1",
            pip_install_cmd=("install", "some-direct-pkg"),  # 无 -r
            install_exclude=("longbridge",),
        )
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=0, stdout="", stderr="")
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "pass"
        assert pr.detail == "pip install OK"
        captured = capsys.readouterr()
        assert "no-op" in captured.err or "no-op" in captured.out

    def test_phase_install_tempfile_fail_is_fail(self, us, tmp_path):
        """A-108: 临时文件写失败 -> install fail (不静默降级)."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / "requirements.txt").write_text("longbridge>=4.0.5\n", encoding="utf-8")
        state = self._make_state(
            us, project, "sub1",
            pip_install_cmd=("install", "-r", "requirements.txt"),
            install_exclude=("longbridge",),
        )
        # 直接使 mkdtemp 抛 OSError
        import tempfile
        with patch.object(tempfile, "mkdtemp",
                          side_effect=OSError("simulated disk full")):
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "fail"
        assert "install_exclude" in pr.detail
        assert "simulated disk full" in pr.detail

    def test_phase_install_argv_replacement_offset(self, us, tmp_path):
        """A-105/Fix-1: 替换的是 argv 中 -r 的路径 token, 不是 -r 标志本身.

        _parse_requirement_paths 返回相对 cfg.pip_install_cmd 的索引, 而
        phase_install 的 cmd = [pip_bin] + pip_install_cmd 前置了 pip_bin;
        替换必须对应该偏移, 否则 -r 被覆盖成临时副本路径, 原 requirements
        路径残留为位置包参数 (pip install <tmpfile> requirements.txt).
        """
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / "requirements.txt").write_text(
            REQUIREMENTS_FIXTURE, encoding="utf-8")
        state = self._make_state(
            us, project, "sub1",
            pip_install_cmd=("install", "-r", "requirements.txt"),
            install_exclude=("longbridge",),
        )
        captured_cmds: list[list[str]] = []
        req_snapshot: dict[str, str] = {}  # argv path -> content (tmpdir 会被 finally 清理)

        def _fake_run(cmd, cwd=None, **kwargs):
            captured_cmds.append(list(cmd))
            for tok in cmd[1:]:
                if tok.endswith("requirements.txt") and tok != "install":
                    p = Path(str(tok))
                    if p.exists():
                        req_snapshot[str(tok)] = p.read_text(encoding="utf-8")
            return us.CommandResult(
                cmd=list(cmd), cwd=cwd, exit_code=0, stdout="", stderr="")

        with patch.object(us, "run_cmd", side_effect=_fake_run):
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "pass"
        assert len(captured_cmds) == 1
        argv = captured_cmds[0]
        # argv[0] 是 pip_bin; "install" 与 "-r" 标志必须原样保留
        assert argv[0].endswith("/bin/pip")
        assert argv[1] == "install"
        assert argv[2] == "-r"
        # argv[3] 是过滤后的临时副本, 不再是原 requirements.txt 路径
        assert argv[3] != str(sub_path / "requirements.txt")
        assert argv[3].endswith("requirements.txt")  # 副本同名
        assert "longbridge" not in req_snapshot[str(argv[3])]
        assert "tushare" in req_snapshot[str(argv[3])]


class TestClassifySamplePriority:
    """UT-030 / UT-031: classify_pip_failure sample 二次选择."""

    def test_classify_sample_prefers_constraint_line(self, us):
        """A-109: RFC 2026-10-06 真实 stderr -> 选 longbridge 行, 不选 yanked."""
        kind, sample = us.classify_pip_failure(REAL_PIP_STDERR_20261006)
        assert kind == "missing_dependency"
        assert "longbridge" in sample
        assert "longbridge<5,>=4.0.5" in sample or "No matching distribution" in sample
        assert "yanked" not in sample  # 不能是被 yanked 行遮蔽

    def test_classify_sample_fallback_first_match(self, us):
        """A-110: 仅 yanked 行 -> 回落首个命中行 (v2.1.0 行为)."""
        stderr = "ERROR: Ignored the following yanked versions: 0.2.2, 0.2.3\n"
        kind, sample = us.classify_pip_failure(stderr)
        assert kind == "missing_dependency"
        assert "yanked" in sample

    def test_classify_sample_invariant(self, us):
        """A-110: 六类分类判定不变 (回归既有 UT)."""
        # platform_incompatible 仍命中
        stderr_p = (
            "  Skipping link: none of the wheel's tags (cp312-cp312-manylinux_2_39_x86_64) "
            "are compatible (Requires-Python: >=3.8)\n"
            "ERROR: No matching distribution found for longbridge==4.2.0\n"
        )
        kind, sample = us.classify_pip_failure(stderr_p)
        assert kind == "platform_incompatible"
        assert "manylinux" in sample


class TestDailyStockAnalysisOptin:
    """UT-032: daily_stock_analysis opt-in merge + 破损回落 (A-111/A-112)."""

    OPTIN_CONTENT = (
        "schema_version: 1\n"
        "systemd_service: daily-stock-analysis\n"
        'health_check: "curl -fsS --max-time 5 http://127.0.0.1:8888/health"\n'
    )

    def test_legal_yaml_merges(self, us, tmp_path):
        """A-111: 三字段经 merge_override 后值精确等于 SPEC §4.4."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / us.OPTIN_FILENAME).write_text(self.OPTIN_CONTENT, encoding="utf-8")
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        override = us.load_optin_override(sub_path)
        merged = us.merge_override(cfg, override)
        assert merged.systemd_service == "daily-stock-analysis"
        assert merged.health_check == "curl -fsS --max-time 5 http://127.0.0.1:8888/health"
        assert merged.config_source == "heuristic+opt-in"

    def test_broken_yaml_falls_back_to_heuristic(self, us, tmp_path):
        """A-112: schema_version 非法 -> warning + 回落启发式."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / us.OPTIN_FILENAME).write_text(
            "schema_version: not_a_number\n"
            "systemd_service: daily-stock-analysis\n"
            'health_check: "curl http://x"\n',
            encoding="utf-8",
        )
        # 加载应返回 None, merge 不被调用 (config_source 保持 heuristic)
        override = us.load_optin_override(sub_path)
        assert override is None
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        assert cfg.health_check is None
        assert cfg.config_source == "heuristic"


class TestVersionAndCliUnchanged:
    """UT-033: version 升 2.2.0 + CLI 参数面与 v2.1.0 相同 (A-114)."""

    def test_version_is_2_2_0(self, us):
        assert us.__version__ == "2.2.0"

    def test_help_args_invariant(self, us):
        """A-114: --help 输出包含全部既有参数 (CLI 面零变化)."""
        r = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        for arg in ("--only", "--push", "--apply", "--dry-run",
                     "--skip-merge", "--skip-install", "--skip-restart",
                     "--resume-after-merge", "--fail-fast", "--force-dirty",
                     "--verbose", "--no-audit", "--repo-root", "--audit-dir"):
            assert arg in r.stdout, f"missing {arg} in --help"


# ----------------------------------------------------------------------
# Fix-2 回归矩阵 (DESIGN-10-012 §5.2; SPEC §4.2 §7 / RFC §5.1)
# ----------------------------------------------------------------------


def _list_filter_tmpdirs() -> set[str]:
    """返回当前 TMPDIR 下所有 update_submodules_filter_* 临时目录路径."""
    import tempfile as _tempfile
    return set(glob.glob(os.path.join(_tempfile.gettempdir(),
                                      "update_submodules_filter_*")))


def _diff_filter_tmpdirs(before: set[str], after: set[str]) -> set[str]:
    """返回新增且仍存在的临时目录 (= 泄漏)."""
    return after - before


def _record_or_noop(cmd, kw, bucket: dict[str, str]) -> None:
    """记录 mock run_cmd 期间 cmd 中所有 update_submodules_filter_* 副本
    内容. 副本由 phase_install 的 finally 清理, 测试必须在 mock 内捕获.

    对分离形式 (-r X / -c X) 路径在 cmd[2]/[4]/..., 等号形式 (-r=X /
    --requirement=X) 路径在 cmd 任意 token 里, 这里只取现存且含
    ``update_submodules_filter_`` 的路径 token, 然后读其内容进 bucket.
    """
    for tok in cmd[2:]:
        if not isinstance(tok, str):
            continue
        if "update_submodules_filter_" not in tok:
            continue
        # 分离形式是路径本身; 等号形式需先剥 option=
        path = tok.split("=", 1)[-1]
        p = Path(path)
        if not p.is_absolute():
            p = (Path(kw.get("cwd") or ".") / path).resolve()
        if p.exists():
            bucket[tok] = p.read_text(encoding="utf-8")


class TestFix2RelativeRefRewrite:
    """UT-035 / UT-036: 副本内相对 -r/-c 重写 + pip parser 真实解析.

    Fix-2 缺陷 A: 根副本迁移到 tmpdir 后, 嵌套 -r/-c 相对引用会指向 tmpdir
    下不存在的目标. SPEC §4.2 / DESIGN §3.4 要求重写为原目录绝对路径.
    """

    def test_rewrite_relative_refs_to_abs(self, us, tmp_path):
        """UT-035: 副本里 -r extra-reqs.txt -> 原目录绝对路径."""
        sub = tmp_path / "sub"
        nested = sub / "nested"
        nested.mkdir(parents=True)
        req = sub / "requirements.txt"
        req.write_text(
            "-r nested/extra.txt\n"
            "--requirement nested/extra.txt\n"
            "-c nested/c.txt\n"
            "-r=nested/extra.txt\n"
            "--requirement=nested/extra.txt\n",
            encoding="utf-8",
        )
        out, _ = us._filter_requirements(req, ("longbridge",))
        text = out.read_text(encoding="utf-8")
        orig_abs = str(sub.resolve())
        # 所有 5 行都被重写为原目录绝对路径; option 形态保留
        assert text.count(f"-r {orig_abs}/nested/extra.txt") == 1
        assert text.count(f"--requirement {orig_abs}/nested/extra.txt") == 1
        assert text.count(f"-c {orig_abs}/nested/c.txt") == 1
        assert text.count(f"-r={orig_abs}/nested/extra.txt") == 1
        assert text.count(f"--requirement={orig_abs}/nested/extra.txt") == 1
        # 不出现裸 "nested/extra.txt" 或 "extra-reqs.txt" 等相对形式残留
        assert " nested/extra.txt\n" not in text

    def test_pip_parser_resolves_nested_refs(self, us, tmp_path):
        """UT-036: 用已安装 pip parser 实际解析, 验证引用仍指向原文件.

        副本中嵌套 -r 应被解析为原目录下的 nested/extra.txt; nested 文件里
        的 longbridge 行不参与排除 (不递归). 仅 mock run_cmd 成功, 验证
        argv 形态和副本路径仍由 pip parser 解析为原文件.

        Fix-2 fixture: 测试需要 venv/bin/pip (否则 phase_install skip).
        通过 _make_project 走 _make_worktree 创建真实 git+mock pip.
        副本内容必须在 mock run_cmd 期间捕获, phase_install finally 之后
        副本目录已清理.
        """
        try:
            from pip._internal.req import parse_requirements  # type: ignore
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"pip parser 不可用: {exc}")

        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        # 写需求: 顶层 tushare + 嵌套 -r; nested/extra.txt 含 longbridge (不递归排除)
        (sub_path / "requirements.txt").write_text(
            "tushare>=1.4.0\n"
            "-r nested/extra.txt\n",
            encoding="utf-8",
        )
        (sub_path / "nested").mkdir(exist_ok=True)
        nested_extra = sub_path / "nested" / "extra.txt"
        nested_extra.write_text(
            "longbridge>=4.0.5\n"
            "tickflow>=0.1.24\n",
            encoding="utf-8",
        )
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        cfg2 = us._replace_config(cfg, {
            "pip_install_cmd": ("install", "-r", "requirements.txt"),
            "install_exclude": ("longbridge",),
        }, cfg.config_source)
        state = us.SubmoduleState(
            config=cfg2, abs_path=(project / "sub1").resolve(),
            pre_head=None, behind=0, ahead=0, upstream_ref="upstream/main",
        )

        captured: list[list[str]] = []
        # finally 会清理副本, 必须在 mock run_cmd 期间读副本并消费 pip parser
        filtered_snapshot: dict[str, str] = {}
        parsed_reqs: list = []

        def fake_run(cmd, cwd=None, **kw):
            captured.append(list(cmd))
            # 拿副本路径: argv[2] == "-r", argv[3] 是过滤后的 requirements 副本
            if len(cmd) >= 4 and cmd[2] == "-r":
                fp = Path(cmd[3])
                if fp.exists():
                    filtered_snapshot["text"] = fp.read_text(encoding="utf-8")
                    # 真消费 pip parser: 解析副本顶层, 不递归 (只验顶端不被误删)
                    from pip._internal.network.session import PipSession  # type: ignore
                    parsed_reqs.extend(
                        parse_requirements(str(fp), session=PipSession())
                    )
            return us.CommandResult(cmd=list(cmd), cwd=cwd, exit_code=0,
                                    stdout="", stderr="")

        with patch.object(us, "run_cmd", side_effect=fake_run):
            pr = us.phase_install(state, dry_run=False)

        assert pr.status == "pass"
        argv = captured[0]
        assert argv[0].endswith("/bin/pip")
        assert argv[1] == "install"
        assert argv[2] == "-r"
        # 副本路径已被 mock 期间捕获; finally 之后已清理, 不能再 read_text
        assert "update_submodules_filter_" in argv[3]
        assert argv[3].endswith("requirements.txt")
        # 副本内容: 嵌套 -r 重写为绝对路径, 顶层 tushare 保留, 顶层 longbridge
        # (无) 不出现; nested 行的 longbridge 不在副本顶层内容中
        text = filtered_snapshot["text"]
        expected_nested = str((sub_path / "nested" / "extra.txt").resolve())
        assert expected_nested in text, (
            f"嵌套 -r 应重写为绝对路径, 副本内容={text!r}"
        )
        assert "tushare" in text, "顶层 tushare 应保留"
        assert "longbridge" not in text, "顶层 longbridge 行已被排除"
        assert "-r nested/extra.txt" not in text, "相对形式应被重写"
        # pip parser 真消费: parse_Requirements 默认递归跟随 -r, 所以副本
        # 顶层 (filtered 重写为绝对 path) 解析出的所有 requirement: tushare +
        # nested/extra.txt 中的 longbridge + tickflow. 此即验证:
        # (a) 嵌套 -r 已被重写为绝对路径且仍被 pip 解析读到 nested;
        # (b) 顶层 longbridge 行已被排除 (副本文本中无 longbridge).
        # pip 24+ 返回包装 ParsedRequirement, .requirement 是 Requirement 对象
        # (str() 即 spec, e.g. 'tushare>=1.4.0'); 较老 pip 直接返回 Requirement.
        def _spec(r):
            req = getattr(r, "requirement", r)
            return str(req)
        top_specs = [_spec(r) for r in parsed_reqs if r is not None]
        assert any(s.startswith("tushare") for s in top_specs), (
            f"pip parser 顶层解析={top_specs!r}"
        )
        assert any(s.startswith("longbridge") for s in top_specs), (
            f"嵌套 longbridge 应被 pip 从 nested 读到, top_specs={top_specs!r}"
        )
        assert any(s.startswith("tickflow") for s in top_specs), (
            f"嵌套 tickflow 应被 pip 从 nested 读到, top_specs={top_specs!r}"
        )
        # 原始 nested/extra.txt 未被修改, 仍含 longbridge (不递归)
        assert nested_extra.read_text(encoding="utf-8").count("longbridge") == 1


class TestFix2EqualsArgv:
    """UT-037 / UT-038: 等号形式 requirement 参数保留选项前缀.

    Fix-2 缺陷 B: -r=path / --requirement=path 被裸副本路径覆盖, 丢前缀.
    """

    def test_dashdash_requirement_equals_preserved(self, us, tmp_path):
        """UT-037: --requirement=foo.txt -> --requirement=<filtered>."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / "requirements.txt").write_text(
            "longbridge>=4.0.5\n", encoding="utf-8")
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        cfg2 = us._replace_config(cfg, {
            "pip_install_cmd": ("install", "--requirement=requirements.txt"),
            "install_exclude": ("longbridge",),
        }, cfg.config_source)
        state = us.SubmoduleState(
            config=cfg2, abs_path=(project / "sub1").resolve(),
            pre_head=None, behind=0, ahead=0, upstream_ref="upstream/main",
        )
        # 快照副本内容 (finally 会清理)
        snapshot: dict[str, str] = {}
        captured: list[list[str]] = []
        def fake_run(cmd, cwd=None, **kw):
            captured.append(list(cmd))
            for tok in cmd[2:]:
                if "update_submodules_filter_" in tok and "=" in tok:
                    p = tok.split("=", 1)[1]
                    pp = Path(p)
                    if not pp.is_absolute():
                        pp = (Path(cwd or state.abs_path) / p).resolve()
                    if pp.exists():
                        snapshot[tok] = pp.read_text(encoding="utf-8")
            return us.CommandResult(cmd=list(cmd), cwd=cwd, exit_code=0,
                                    stdout="", stderr="")
        with patch.object(us, "run_cmd", side_effect=fake_run):
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "pass"
        argv = captured[0]
        assert argv[0].endswith("/bin/pip")
        assert argv[1] == "install"
        # 等号形式必须保留 --requirement= 前缀
        tok = argv[2]
        assert tok.startswith("--requirement="), f"前缀丢失: {tok!r}"
        # 路径必须指向过滤副本 (含 update_submodules_filter_)
        assert "update_submodules_filter_" in tok
        assert "requirements.txt" in tok
        # 副本内容已过滤 longbridge; 文件名 (requirements.txt) 已由
        # argv[2] 的 update_submodules_filter_*/requirements.txt 路径
        # 隐含表达, 不必再断言内容含字面 "requirements.txt" (过滤后
        # 内容可能为空, 强加字面字符串无意义).
        assert tok in snapshot, "snapshot miss"
        assert "longbridge" not in snapshot[tok]

    def test_dash_r_equals_preserved(self, us, tmp_path):
        """UT-038: -r=foo.txt -> -r=<filtered>."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / "requirements.txt").write_text(
            "longbridge>=4.0.5\n", encoding="utf-8")
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        cfg2 = us._replace_config(cfg, {
            "pip_install_cmd": ("install", "-r=requirements.txt"),
            "install_exclude": ("longbridge",),
        }, cfg.config_source)
        state = us.SubmoduleState(
            config=cfg2, abs_path=(project / "sub1").resolve(),
            pre_head=None, behind=0, ahead=0, upstream_ref="upstream/main",
        )
        captured = []
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.side_effect = lambda cmd, **kw: (
                captured.append(list(cmd))
                or us.CommandResult(cmd=list(cmd), cwd=kw.get("cwd"),
                                    exit_code=0, stdout="", stderr="")
            )
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "pass"
        argv = captured[0]
        assert argv[1] == "install"
        tok = argv[2]
        assert tok.startswith("-r="), f"前缀丢失: {tok!r}"
        assert "update_submodules_filter_" in tok


class TestFix2MultiRoot:
    """UT-039: 多根 -r 引用, 同名根副本不互相覆盖."""

    def test_multi_root_same_name_does_not_clobber(self, us, tmp_path):
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        # 两个同名为 requirements.txt 的根文件位于不同目录
        (sub_path / "reqA").mkdir()
        (sub_path / "reqB").mkdir()
        (sub_path / "reqA" / "requirements.txt").write_text(
            "longbridge>=4.0.5\ntushare>=1.4.0\n", encoding="utf-8")
        (sub_path / "reqB" / "requirements.txt").write_text(
            "longbridge==0.2.74\ntickflow>=0.1.24\n", encoding="utf-8")
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        cfg2 = us._replace_config(cfg, {
            "pip_install_cmd": ("install", "-r", "reqA/requirements.txt",
                                 "-r", "reqB/requirements.txt"),
            "install_exclude": ("longbridge",),
        }, cfg.config_source)
        state = us.SubmoduleState(
            config=cfg2, abs_path=(project / "sub1").resolve(),
            pre_head=None, behind=0, ahead=0, upstream_ref="upstream/main",
        )
        captured = []
        # finally 会清理副本, 必须在 mock run_cmd 期间读两个副本内容
        copy_text: dict[str, str] = {}
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.side_effect = lambda cmd, **kw: (
                captured.append(list(cmd))
                or _record_or_noop(cmd, kw, copy_text)
                or us.CommandResult(cmd=list(cmd), cwd=kw.get("cwd"),
                                    exit_code=0, stdout="", stderr="")
            )
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "pass"
        argv = captured[0]
        # argv: [pip_bin, install, -r, <A>, -r, <B>]
        # 两个路径不同 (否则副本互相覆盖, 仅最后一个被读)
        assert argv[3] != argv[5], "多根同名副本未互相覆盖保护"
        # 两个副本都存在并被过滤 (内容在 mock 期间快照)
        a_text = copy_text.get(argv[3], "")
        b_text = copy_text.get(argv[5], "")
        assert "longbridge" not in a_text
        assert "tushare" in a_text
        assert "longbridge" not in b_text
        assert "tickflow" in b_text

    def test_multi_root_same_parent_basename_no_clobber(self, us, tmp_path):
        """UT-039b: 同父目录 basename 的多根 -r 引用 (Fix-3 严格回归).

        serviceA/reqs/requirements.txt 与 serviceB/reqs/requirements.txt
        的 parent.name 都是 'reqs'. 修前会把两份副本都写到同一个
        tmpdir/reqs/requirements.txt, 互相覆盖. 修后每个根得到独立
        tmpdir 子目录, 两份内容互不丢失. argv 两条 -r 路径不同,
        run_cmd 期间读取两份真实过滤内容 (排除 longbridge), 第一根
        tushare 与第二根 tickflow 都存在, 不互相覆盖.
        """
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        # 两个 serviceX/reqs/ 同父目录 (basename == 'reqs'),
        # 同名 requirements.txt
        (sub_path / "serviceA" / "reqs").mkdir(parents=True)
        (sub_path / "serviceB" / "reqs").mkdir(parents=True)
        (sub_path / "serviceA" / "reqs" / "requirements.txt").write_text(
            "longbridge>=4.0.5\ntushare>=1.4.0\n", encoding="utf-8")
        (sub_path / "serviceB" / "reqs" / "requirements.txt").write_text(
            "longbridge==0.2.74\ntickflow>=0.1.24\n", encoding="utf-8")
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        cfg2 = us._replace_config(cfg, {
            "pip_install_cmd": ("install",
                                 "-r", "serviceA/reqs/requirements.txt",
                                 "-r", "serviceB/reqs/requirements.txt"),
            "install_exclude": ("longbridge",),
        }, cfg.config_source)
        state = us.SubmoduleState(
            config=cfg2, abs_path=(project / "sub1").resolve(),
            pre_head=None, behind=0, ahead=0, upstream_ref="upstream/main",
        )
        captured = []
        copy_text: dict[str, str] = {}
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.side_effect = lambda cmd, **kw: (
                captured.append(list(cmd))
                or _record_or_noop(cmd, kw, copy_text)
                or us.CommandResult(cmd=list(cmd), cwd=kw.get("cwd"),
                                    exit_code=0, stdout="", stderr="")
            )
            pr = us.phase_install(state, dry_run=False)
        assert pr.status == "pass"
        argv = captured[0]
        # argv: [pip_bin, install, -r, <A>, -r, <B>]
        assert argv[3] != argv[5], "同父 basename 双根副本被覆盖到同一路径"
        a_text = copy_text.get(argv[3], "")
        b_text = copy_text.get(argv[5], "")
        # 修前: a_text 是第二根 (tickflow), tushare 丢失.
        # 修后: a_text 仍是第一根 (tushare), b_text 是第二根 (tickflow).
        assert "longbridge" not in a_text
        assert "tushare" in a_text, (
            f"第一根依赖丢失 (被第二根覆盖): a_text={a_text!r}"
        )
        assert "longbridge" not in b_text
        assert "tickflow" in b_text


class TestFix2TempdirCleanup:
    """UT-040~UT-044: 清理矩阵覆盖源缺失/写失败/pip 失败/成功/dry-run.

    Fix-2 缺陷 C: 临时目录创建后, 提前 return 必须走 finally 清理.
    """

    @staticmethod
    def _setup_state(us, project, name, pip_install_cmd, install_exclude):
        cfg = us.discover_submodule(name, Path(name), project)
        cfg2 = us._replace_config(cfg, {
            "pip_install_cmd": pip_install_cmd,
            "install_exclude": install_exclude,
        }, cfg.config_source)
        return us.SubmoduleState(
            config=cfg2, abs_path=(project / name).resolve(),
            pre_head=None, behind=0, ahead=0, upstream_ref="upstream/main",
        )

    def test_source_missing_cleans_tmpdir(self, us, tmp_path):
        """UT-040: 源缺失 -> install fail, 临时目录清理."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        before = _list_filter_tmpdirs()
        state = self._setup_state(
            us, project, "sub1",
            pip_install_cmd=("install", "-r", "missing_req.txt"),
            install_exclude=("longbridge",),
        )
        pr = us.phase_install(state, dry_run=False)
        after = _list_filter_tmpdirs()
        assert pr.status == "fail"
        assert _diff_filter_tmpdirs(before, after) == set()

    def test_write_fail_cleans_tmpdir(self, us, tmp_path):
        """UT-041: 写副本失败 -> install fail, 临时目录清理."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / "requirements.txt").write_text(
            "longbridge>=4.0.5\n", encoding="utf-8")
        before = _list_filter_tmpdirs()
        state = self._setup_state(
            us, project, "sub1",
            pip_install_cmd=("install", "-r", "requirements.txt"),
            install_exclude=("longbridge",),
        )
        # 让 mkdtemp 抛 OSError
        import tempfile
        with patch.object(tempfile, "mkdtemp",
                          side_effect=OSError("simulated disk full")):
            pr = us.phase_install(state, dry_run=False)
        after = _list_filter_tmpdirs()
        assert pr.status == "fail"
        assert "install_exclude" in pr.detail
        assert _diff_filter_tmpdirs(before, after) == set()

    def test_pip_fail_cleans_tmpdir(self, us, tmp_path):
        """UT-042: pip 失败 -> install fail, 临时目录清理."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / "requirements.txt").write_text(
            "longbridge>=4.0.5\ntushare>=1.4.0\n", encoding="utf-8")
        before = _list_filter_tmpdirs()
        state = self._setup_state(
            us, project, "sub1",
            pip_install_cmd=("install", "-r", "requirements.txt"),
            install_exclude=("longbridge",),
        )
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=1, stdout="",
                stderr="ERROR: No matching distribution found for x\n")
            pr = us.phase_install(state, dry_run=False)
        after = _list_filter_tmpdirs()
        assert pr.status == "fail"
        assert _diff_filter_tmpdirs(before, after) == set()

    def test_success_cleans_tmpdir(self, us, tmp_path):
        """UT-043: pip 成功 -> install pass, 临时目录清理."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / "requirements.txt").write_text(
            "longbridge>=4.0.5\ntushare>=1.4.0\n", encoding="utf-8")
        before = _list_filter_tmpdirs()
        state = self._setup_state(
            us, project, "sub1",
            pip_install_cmd=("install", "-r", "requirements.txt"),
            install_exclude=("longbridge",),
        )
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=0, stdout="", stderr="")
            pr = us.phase_install(state, dry_run=False)
        after = _list_filter_tmpdirs()
        assert pr.status == "pass"
        assert "degraded" in pr.detail
        assert _diff_filter_tmpdirs(before, after) == set()

    def test_dry_run_cleans_tmpdir(self, us, tmp_path):
        """UT-044: dry-run -> 临时目录清理."""
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        sub_path = project / "sub1"
        (sub_path / "requirements.txt").write_text(
            "longbridge>=4.0.5\n", encoding="utf-8")
        before = _list_filter_tmpdirs()
        state = self._setup_state(
            us, project, "sub1",
            pip_install_cmd=("install", "-r", "requirements.txt"),
            install_exclude=("longbridge",),
        )
        pr = us.phase_install(state, dry_run=True)
        after = _list_filter_tmpdirs()
        assert pr.status == "pass"
        assert "[dry-run]" in pr.detail
        assert _diff_filter_tmpdirs(before, after) == set()


class TestFix2DefaultBehaviorUnchanged:
    """UT-045: 无 install_exclude 默认行为与 v2.1.0 一致."""

    def test_no_install_exclude_no_filter(self, us, tmp_path):
        """无 install_exclude 时 argv 完全不变: -r 路径仍指向原 requirements.txt,
        没有任何副本生成, 不引入 update_submodules_filter_ 目录.

        v2.1.0 默认行为: pip_install_cmd 沿用启发式 ('install', '-r',
        'requirements.txt'), -r 后的 path 是相对路径 (相对 cwd=state.abs_path),
        与 _setup_state 完全一致. 绝不能改为绝对路径 (会破坏子模块自洽,
        子模块移动后路径需更新).
        """
        project = _make_project(tmp_path, [("sub1", "sub1", True)])
        before = _list_filter_tmpdirs()
        cfg = us.discover_submodule("sub1", Path("sub1"), project)
        state = us.SubmoduleState(
            config=cfg, abs_path=(project / "sub1").resolve(),
            pre_head=None, behind=0, ahead=0, upstream_ref="upstream/main",
        )
        captured = []
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.side_effect = lambda cmd, **kw: (
                captured.append(list(cmd))
                or us.CommandResult(cmd=list(cmd), cwd=kw.get("cwd"),
                                    exit_code=0, stdout="", stderr="")
            )
            pr = us.phase_install(state, dry_run=False)
        after = _list_filter_tmpdirs()
        assert pr.status == "pass"
        assert pr.detail == "pip install OK"
        # argv 与 v2.1.0 一致: -r 后仍是原相对 requirements.txt (非绝对,
        # 非副本). 不引入 update_submodules_filter_ 目录.
        argv = captured[0]
        assert argv[3] == "requirements.txt"
        assert "update_submodules_filter_" not in argv[3]
        # 无任何临时目录被创建
        assert _diff_filter_tmpdirs(before, after) == set()
