# -*- coding: utf-8 -*-
"""Offline regression tests for scripts/start-btc5m-live.sh.

Every test runs the REAL wrapper file, but inside a throwaway fake project
tree under pytest's tmp_path: a fake networkless `.venv/bin/python` and a fake
`btc5m_launch.py` that only records argv / cwd / environment. The real
launcher is never executed, no network, no Mongo, no keyring, no account.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "start-btc5m-live.sh"
TOOLS_REL = Path(
    "skills/trading/auto-trading/prediction-markets/"
    "Prediction-Markets-Trading-Bot-Toolkits/tools/predictfun"
)
# The same public pattern the launcher enforces (btc5m_control.RUN_ID_PATTERN).
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

RECORD_ENV_KEYS = (
    "PWD", "PYTHONPATH", "PYTHONHOME", "TMPDIR", "PATH", "HOME",
)


def _fake_python(path: Path) -> None:
    """A networkless fake interpreter: records the invocation, then waits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/bash\n"
        "OUT=\"${FAKE_RECORD_DIR:?}\"\n"
        "mkdir -p \"$OUT\"\n"
        "for a in \"$@\"; do printf '%s\\n' \"$a\"; done > \"$OUT/args.tmp\"\n"
        "mv \"$OUT/args.tmp\" \"$OUT/args.txt\"\n"
        "echo -n \"cwd=\" > \"$OUT/env.tmp\"\n"
        "pwd >> \"$OUT/env.tmp\"\n"
        "for k in " + " ".join(RECORD_ENV_KEYS) + "; do\n"
        "  v=\"$(printenv \"$k\" || true)\"\n"
        "  printf '%s=%s\\n' \"$k\" \"$v\" >> \"$OUT/env.tmp\"\n"
        "done\n"
        "mv \"$OUT/env.tmp\" \"$OUT/env.txt\"\n"
        "sleep 3\n"
        "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _fake_launcher(path: Path) -> None:
    """A fake launcher that only proves it was reached; it never trades."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# fake launcher: no trading, no network\n", encoding="utf-8")
    path.chmod(0o755)


def _make_fake_project(root: Path) -> Path:
    """Build the isolated fake project and return the copied wrapper path."""
    fake_python = root / ".venv" / "bin" / "python"
    _fake_python(fake_python)
    tools = root / TOOLS_REL
    _fake_launcher(tools / "btc5m_launch.py")
    (tools / "btc5m-controlled-paper.json").write_text("{}\n", encoding="utf-8")
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    wrapper = root / "scripts" / "start-btc5m-live.sh"
    shutil.copy2(SCRIPT_PATH, wrapper)
    wrapper.chmod(0o755)
    return wrapper


def _run(wrapper: Path, *args: str, cwd: Path | None = None,
         env: dict | None = None) -> subprocess.CompletedProcess:
    record_dir = wrapper.parents[1] / "record"
    for stale in ("args.txt", "env.txt"):
        (record_dir / stale).unlink(missing_ok=True)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["FAKE_RECORD_DIR"] = str(wrapper.parents[1] / "record")
    if env:
        environment.update(env)
    return subprocess.run(
        [str(wrapper), *args], cwd=str(cwd or Path("/")), env=environment,
        capture_output=True, text=True, timeout=60, check=False,
    )


def _record(wrapper: Path) -> dict:
    """Wait for the fake child to record, then return its argv and environment."""
    record_dir = wrapper.parents[1] / "record"
    args_file = record_dir / "args.txt"
    env_file = record_dir / "env.txt"
    deadline = time.time() + 30
    while time.time() < deadline:
        if args_file.exists() and env_file.exists() and env_file.stat().st_size > 0:
            break
        time.sleep(0.1)
    else:  # pragma: no cover - the fake child always records
        pytest.fail("fake child did not record its invocation")
    argv = args_file.read_text(encoding="utf-8").splitlines()
    environment = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            environment[key] = value
    return {"argv": argv, "env": environment}


def _dispatch_files(root: Path) -> list[Path]:
    return sorted((root / "data" / "reports").glob("*/evidence/wrapper/*/dispatch.json"))


def _fake_date_bin(bin_dir: Path) -> Path:
    """A deterministic `date` stub so the log directory name is reproducible."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "date"
    stub.write_text(
        "#!/bin/bash\n"
        "case \"$1\" in\n"
        "  +%F) echo '2026-11-24' ;;\n"
        "  +%Y%m%dT%H%M%S) echo '20261124T090000' ;;\n"
        "  --iso-8601=seconds) echo '2026-11-24T09:00:00+08:00' ;;\n"
        "  *) exec /bin/date \"$@\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def _deterministic_env(tmp_path: Path) -> dict:
    """Env that pins the wrapper's date and RANDOM, so STAMP is reproducible.

    The wrapper has no test switch: determinism comes only from an isolated
    PATH holding a `date` stub and a BASH_ENV that seeds RANDOM.
    """
    bin_dir = tmp_path / "fakebin"
    _fake_date_bin(bin_dir)
    bash_env = tmp_path / "bashenv.sh"
    bash_env.write_text("RANDOM=42\n", encoding="utf-8")
    environment = dict(os.environ)
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment.get('PATH', '')}"
    environment["BASH_ENV"] = str(bash_env)
    return environment


def _log_dir_of(dispatch_file: Path) -> Path:
    record = json.loads(dispatch_file.read_text(encoding="utf-8"))
    return Path(record["log_file"]).parent


def test_no_redundant_dot_parent_sibling_directory(tmp_path: Path) -> None:
    """A run creates the real parent chain only, never a "<name>.parent" twin."""
    wrapper = _make_fake_project(tmp_path / "project")
    result = _run(wrapper, "--authorization-ref", "no-parent-ref")
    assert result.returncode == 0, result.stderr

    wrapper_root = wrapper.parents[1] / "data" / "reports"
    created = sorted(p for p in wrapper_root.rglob("*") if p.is_dir())
    assert created, "expected the run to create its log directory"
    assert not [p for p in created if p.name.endswith(".parent")], (
        f"redundant '.parent' directory left behind: {[str(p) for p in created]}"
    )
    # The log directory's parent is the 'wrapper' directory itself.
    log_dir = _log_dir_of(_dispatch_files(wrapper.parents[1])[0])
    assert log_dir.parent.name == "wrapper"
    assert log_dir.parent.parent.name == "evidence"


def test_existing_log_directory_is_refused_and_old_output_survives(tmp_path: Path) -> None:
    """Reusing an existing log directory is refused; old logs stay untouched."""
    wrapper = _make_fake_project(tmp_path / "project")
    env = _deterministic_env(tmp_path)
    first = _run(wrapper, "--authorization-ref", "collide-ref", env=env)
    assert first.returncode == 0, first.stderr

    dispatch_files = _dispatch_files(wrapper.parents[1])
    assert len(dispatch_files) == 1
    log_dir = _log_dir_of(dispatch_files[0])
    assert log_dir.exists()
    old_log = log_dir / "launch.log"
    old_log.write_text("first run output\n", encoding="utf-8")

    record_dir = wrapper.parents[1] / "record"
    args_file = record_dir / "args.txt"
    recorded = _record(wrapper)
    args_before = args_file.read_text(encoding="utf-8")
    assert recorded["argv"]

    time.sleep(0.2)
    second = _run(wrapper, "--authorization-ref", "collide-ref", env=env)
    assert second.returncode == 2
    assert "日志目录已存在" in second.stderr

    # The old output is intact and no second child was dispatched.
    assert old_log.read_text(encoding="utf-8") == "first run output\n"
    assert len(_dispatch_files(wrapper.parents[1])) == 1
    assert not args_file.exists(), "a second child process was dispatched"
    assert args_before


def test_help_has_no_side_effect(tmp_path: Path) -> None:
    """--help prints usage, spawns nothing and writes nothing."""
    wrapper = _make_fake_project(tmp_path / "project")
    result = _run(wrapper, "--help")
    assert result.returncode == 0
    assert "用法" in result.stdout
    assert not (wrapper.parents[1] / "record" / "args.txt").exists()
    assert not (wrapper.parents[1] / "data").exists()


def test_unknown_argument_is_refused_before_any_side_effect(tmp_path: Path) -> None:
    """An unknown parameter is refused, and no child or log is produced."""
    wrapper = _make_fake_project(tmp_path / "project")
    result = _run(wrapper, "--not-a-flag")
    assert result.returncode == 2
    assert "未知参数" in result.stderr
    assert not (wrapper.parents[1] / "record" / "args.txt").exists()
    assert not (wrapper.parents[1] / "data").exists()


def test_missing_interpreter_is_refused_before_any_side_effect(tmp_path: Path) -> None:
    """A missing interpreter is refused before a child or a log directory exists."""
    wrapper = _make_fake_project(tmp_path / "project")
    (wrapper.parents[1] / ".venv" / "bin" / "python").unlink()
    result = _run(wrapper)
    assert result.returncode == 2
    assert "解释器" in result.stderr
    assert not (wrapper.parents[1] / "record" / "args.txt").exists()
    assert not (wrapper.parents[1] / "data").exists()


def test_invalid_authorization_ref_is_refused(tmp_path: Path) -> None:
    """An authorization reference outside RUN_ID_PATTERN is refused."""
    wrapper = _make_fake_project(tmp_path / "project")
    result = _run(wrapper, "--authorization-ref", "NOT ALLOWED")
    assert result.returncode == 2
    assert "RUN_ID_PATTERN" in result.stderr
    assert not (wrapper.parents[1] / "record" / "args.txt").exists()


def test_dispatch_from_another_cwd_with_correct_argv_and_env(tmp_path: Path) -> None:
    """From any cwd: the child runs in the project root with the fixed argv."""
    wrapper = _make_fake_project(tmp_path / "project")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = _run(wrapper, cwd=elsewhere,
                  env={"PYTHONPATH": "/tmp/evil", "PYTHONHOME": "/tmp/evil"})
    assert result.returncode == 0, result.stderr
    assert "已派发" in result.stdout
    assert "不代表实盘启动成功" in result.stdout

    recorded = _record(wrapper)
    argv = recorded["argv"]
    launcher = str(wrapper.parents[1] / TOOLS_REL / "btc5m_launch.py")
    assert argv[0] == launcher
    assert "--auto-prepare" in argv
    assert argv[argv.index("--operations-mode") + 1] == "unattended"
    assert argv[argv.index("--config") + 1] == str(
        wrapper.parents[1] / TOOLS_REL / "btc5m-controlled-paper.json")
    ref = argv[argv.index("--authorization-ref") + 1]
    assert RUN_ID_PATTERN.fullmatch(ref) is not None

    assert recorded["env"]["cwd"] == str(wrapper.parents[1])
    assert recorded["env"].get("PYTHONPATH", "") == ""
    assert recorded["env"].get("PYTHONHOME", "") == ""
    assert recorded["env"]["TMPDIR"].startswith("/home/pascal/.hermes/profiles/")


def test_explicit_arguments_are_passed_verbatim(tmp_path: Path) -> None:
    """An explicit reference and a config path with spaces survive unchanged."""
    wrapper = _make_fake_project(tmp_path / "project")
    config = tmp_path / "with space" / "cfg.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}\n", encoding="utf-8")
    result = _run(wrapper, "--authorization-ref", "my-ref-01",
                  "--config", str(config))
    assert result.returncode == 0, result.stderr
    recorded = _record(wrapper)
    argv = recorded["argv"]
    assert argv[argv.index("--authorization-ref") + 1] == "my-ref-01"
    assert argv[argv.index("--config") + 1] == str(config)
    assert "my-ref-01" in result.stdout


def test_relative_config_is_resolved_against_the_caller_cwd(tmp_path: Path) -> None:
    """A relative --config path resolves against the caller's cwd, not the root."""
    wrapper = _make_fake_project(tmp_path / "project")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "cfg.json").write_text("{}\n", encoding="utf-8")
    result = _run(wrapper, "--config", "cfg.json", cwd=elsewhere)
    assert result.returncode == 0, result.stderr
    recorded = _record(wrapper)
    argv = recorded["argv"]
    assert argv[argv.index("--config") + 1] == str(elsewhere / "cfg.json")


def test_missing_config_is_refused(tmp_path: Path) -> None:
    """A missing --config file is refused before any side effect."""
    wrapper = _make_fake_project(tmp_path / "project")
    result = _run(wrapper, "--config", str(tmp_path / "absent.json"))
    assert result.returncode == 2
    assert "配置文件不存在" in result.stderr
    assert not (wrapper.parents[1] / "record" / "args.txt").exists()


def test_default_authorization_ref_is_unique_per_run(tmp_path: Path) -> None:
    """Two default runs get two different, pattern-conforming references."""
    wrapper = _make_fake_project(tmp_path / "project")
    refs = []
    for _ in range(2):
        result = _run(wrapper)
        assert result.returncode == 0, result.stderr
        recorded = _record(wrapper)
        argv = recorded["argv"]
        refs.append(argv[argv.index("--authorization-ref") + 1])
        time.sleep(0.2)
    assert refs[0] != refs[1]
    assert all(RUN_ID_PATTERN.fullmatch(ref) for ref in refs)


def test_logs_are_private_new_directories_and_old_output_survives(tmp_path: Path) -> None:
    """Each run owns a fresh private log directory; earlier logs stay intact."""
    wrapper = _make_fake_project(tmp_path / "project")
    assert _run(wrapper, "--authorization-ref", "run-one").returncode == 0
    first = _dispatch_files(wrapper.parents[1])
    assert len(first) == 1
    first_dir = first[0].parent
    assert stat.S_IMODE(first_dir.stat().st_mode) == 0o700
    first_log = first_dir / "launch.log"
    first_log.write_text("first run output\n", encoding="utf-8")

    time.sleep(0.2)
    assert _run(wrapper, "--authorization-ref", "run-two").returncode == 0
    second = _dispatch_files(wrapper.parents[1])
    assert len(second) == 2
    assert second[0].parent != second[1].parent
    assert first_log.read_text(encoding="utf-8") == "first run output\n"
    assert stat.S_IMODE(second[1].parent.stat().st_mode) == 0o700


def test_dispatch_record_reports_pid_reference_and_log_path(tmp_path: Path) -> None:
    """The dispatch record carries the PID, the reference and the log path."""
    wrapper = _make_fake_project(tmp_path / "project")
    assert _run(wrapper, "--authorization-ref", "audit-ref-1").returncode == 0
    record = json.loads(_dispatch_files(wrapper.parents[1])[0].read_text(encoding="utf-8"))
    assert record["authorization_ref"] == "audit-ref-1"
    assert isinstance(record["pid"], int) and record["pid"] > 0
    assert record["cwd"] == str(wrapper.parents[1])
    assert record["log_file"].startswith(str(wrapper.parents[1] / "data" / "reports"))
    assert "Asia/Shanghai" in record["dispatched_at"] or record["dispatched_at"].endswith("+08:00")
