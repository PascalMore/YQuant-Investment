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
        """UT-012: health_check=None 时 Phase 4 跳过 health check."""
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
        with patch.object(us, "run_cmd") as mock_run:
            mock_run.return_value = us.CommandResult(
                cmd=[], cwd=None, exit_code=0, stdout="", stderr="")
            pr = us.phase_restart(state, dry_run=False)
        assert pr.status == "pass"
        assert "SKIP" in pr.detail or "skip" in pr.detail.lower()

    def test_health_check_fail_aborts_push(self, us, tmp_path):
        """UT-011: health_check FAIL aborts push."""
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
            if "sh" in cmd and "-c" in cmd:
                return us.CommandResult(cmd=cmd, cwd=None, exit_code=1,
                                        stdout="", stderr="connection refused")
            return us.CommandResult(cmd=cmd, cwd=None, exit_code=0,
                                    stdout="", stderr="")
        with patch.object(us, "run_cmd", side_effect=mock_run):
            pr = us.phase_restart(state, dry_run=False)
        assert pr.status == "fail"
        assert "health" in pr.detail.lower()


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
