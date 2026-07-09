# -*- coding: utf-8 -*-
"""Tests for scripts/upgrade/update_submodules.py
(SPEC-10-008 / DESIGN-10-008 / RFC-10-008 V2.0).

Covers (SPEC §9):
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
"""
import importlib.util
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
