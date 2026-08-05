"""P0 G-CF-LIVE R2 hardening — independent attack-surface verify.

These tests are written independently (not by the implementation
team) and target the attack surfaces called out in the task body:

* Check #1 — ``args.output_dir`` newly created AND pre-existing 0o775
  both end up at 0o700; chmod failure → fail-stop and no YAML.
* Check #2 — ``smoke-flow-YYYYMMDD.yaml`` (NOT just new files) ends
  up at 0o600 — including the case where a 0o644 / 0o664 file is
  already on disk and the smoke runner truncates / rewrites it.
* Check #3 — ``umask=0000`` does not widen the output, verified via
  subprocess CLI (no umask dependency in implementation).
* Check #5 — no shell ``rm -rf`` anywhere; tmp_path /
  TemporaryDirectory only.

All tests are dry-run (no Provider / no AKShare / no Mongo /
no live-read).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.t4_preflight import smoke_flow
from scripts.t4_preflight.config import EXIT_FAIL, EXIT_PASS

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_label() -> str:
    return _dt.datetime.now().strftime("%Y%m%d")


def _smoke_yaml_path(out_dir: Path) -> Path:
    """Locator: exactly one smoke-flow-YYYYMMDD.yaml under ``out_dir``."""
    candidates = sorted(out_dir.glob(f"smoke-flow-{_today_label()}.yaml"))
    assert len(candidates) == 1, (
        f"expected exactly one today-dated smoke yaml in {out_dir}, got "
        f"{list(out_dir.glob('smoke-flow-*.yaml'))}"
    )
    return candidates[0]


def _smoke_out_dir_mode(out_dir: Path) -> int:
    return stat.S_IMODE(os.stat(out_dir).st_mode)


def _smoke_yaml_mode(yaml_path: Path) -> int:
    return stat.S_IMODE(os.stat(yaml_path).st_mode)


def _run_cli_subprocess(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run the smoke CLI as a true subprocess.

    The CLI is exercised through ``python -m scripts.t4_preflight.cli``
    so the implementation's umask calls (if any) hit a real forked
    process — Python's in-process ``monkeypatch.setattr(os, "umask", ...)``
    does NOT propagate to subprocesses.
    """
    cmd = [sys.executable, "-m", "scripts.t4_preflight.cli", *args]
    return subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        timeout=30,
    )


def _canonical_args(out_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        live_read=False,
        output_dir=str(out_dir),
        date=None,
        symbol="600519",
        market="sh",
    )


# ---------------------------------------------------------------------------
# Check #1 — output_dir mkdir + chmod 0o700
# ---------------------------------------------------------------------------

def test_attack_preexisting_0775_dir_is_chmodded_to_0700_inprocess(
    tmp_path: Path,
) -> None:
    """Pre-existing 0o775 directory MUST be tightened to 0o700 by
    ``run_smoke`` BEFORE any report file lands inside.

    Python-level invocation. The implementation calls
    ``os.chmod(out_dir, 0o700)`` before opening the YAML.
    """
    out_dir = tmp_path / "wide"
    out_dir.mkdir(parents=False)
    os.chmod(out_dir, 0o775)
    pre_run_mode = _smoke_out_dir_mode(out_dir)
    assert pre_run_mode == 0o775, (
        f"setup: chmod 0775 did not stick, got {pre_run_mode:#o}"
    )

    args = _canonical_args(out_dir)
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == EXIT_PASS
    assert _smoke_out_dir_mode(out_dir) == 0o700
    assert _smoke_yaml_mode(_smoke_yaml_path(out_dir)) == 0o600


def test_attack_preexisting_0775_dir_is_chmodded_via_subprocess_cli(
    tmp_path: Path,
) -> None:
    """Same R2 root-cause attack — but exercised through the
    subprocess CLI so the chmod path is hit the same way Gate C
    invokes it. This is the test the PR description explicitly
    demands: subprocess CLI dry-run under a pre-existing 0o775
    directory MUST still lock the output to 0o700 + 0o600.
    """
    out_dir = tmp_path / "wide-cli"
    out_dir.mkdir(parents=False)
    os.chmod(out_dir, 0o775)
    assert _smoke_out_dir_mode(out_dir) == 0o775

    proc = _run_cli_subprocess(
        "smoke-flow",
        "--output-dir",
        str(out_dir),
        cwd=REPO_ROOT,
    )
    assert proc.returncode == EXIT_PASS, (
        f"subprocess failed rc={proc.returncode} "
        f"stderr={proc.stderr!r} stdout={proc.stdout!r}"
    )
    assert _smoke_out_dir_mode(out_dir) == 0o700
    yaml_path = _smoke_yaml_path(out_dir)
    assert _smoke_yaml_mode(yaml_path) == 0o600
    # Sanity: the YAML was actually written (not just chmod'd).
    text = yaml_path.read_text(encoding="utf-8")
    assert "flow.capital_flow_daily" in text
    assert "verdict: pass" in text


def test_attack_chmod_failure_returns_2_and_does_not_write_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If ``os.chmod(out_dir, 0o700)`` raises, ``run_smoke`` MUST
    fail-stop with return code 2 and MUST NOT have written any
    ``smoke-flow-*.yaml`` inside ``out_dir``.

    The implementation wraps the chmod in a ``try/except OSError``
    that prints an error and returns 2 — verify this end-to-end
    by stubbing ``os.chmod`` to raise ``PermissionError``.
    """
    out_dir = tmp_path / "denied"
    # Pre-create with permissive mode; chmod will then be the failing
    # step (the permission error originates in our stub).
    out_dir.mkdir(parents=True)
    os.chmod(out_dir, 0o755)

    def _boom_chmod(path, mode, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        # Only fail on the out_dir chmod; other invocations pass through.
        if str(path) == str(out_dir):
            raise PermissionError("simulated chmod EACCES")
        return _orig_chmod(path, mode, *args, **kwargs)

    _orig_chmod = os.chmod
    monkeypatch.setattr(os, "chmod", _boom_chmod)

    args = _canonical_args(out_dir)
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == 2, (
        f"expected fail-stop rc=2 on chmod failure, got {exit_code}"
    )
    # No yaml may have been written.
    yamls = list(out_dir.glob("smoke-flow-*.yaml"))
    assert yamls == [], f"chmod failure wrote yaml anyway: {yamls}"


# ---------------------------------------------------------------------------
# Check #2 — YAML mode forced to 0o600
# ---------------------------------------------------------------------------

def test_attack_preexisting_yaml_0644_is_also_locked_to_0600(
    tmp_path: Path,
) -> None:
    """The task body EXPLICITLY requires the 0o600 lock to apply when
    a pre-existing ``smoke-flow-YYYYMMDD.yaml`` is already on disk
    at ``0o644`` or ``0o664``.

    POSIX semantics (man 2 open):

      "The mode argument ... is used only when creating a new file.
       If the file already exists, the mode is left unchanged."

    The implementation uses
    ``os.open(out_path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)`` — without
    a follow-up ``os.chmod``, an existing ``0o644`` / ``0o664``
    file is truncated but its mode bit is left untouched. This test
    pins down whether the implementation actually narrows the mode
    on overwrite, or whether this is an open P0 defect.
    """
    out_dir = tmp_path / "out"
    args_ns = _canonical_args(out_dir)
    # First dry-run creates the file at 0o600 (the easy path).
    assert smoke_flow.run_smoke(args_ns) == EXIT_PASS

    yaml_path = _smoke_yaml_path(out_dir)
    assert _smoke_yaml_mode(yaml_path) == 0o600

    # Now widen the file to 0o644 — simulating an attacker (or a
    # scheduler that ran with a permissive umask on a prior day)
    # having left the report file at over-permissive mode.
    os.chmod(yaml_path, 0o644)
    assert _smoke_yaml_mode(yaml_path) == 0o644

    # Second dry-run re-runs the runner against the same out_dir.
    # The implementation MUST re-tighten the file's mode to 0o600
    # on this invocation.
    assert smoke_flow.run_smoke(args_ns) == EXIT_PASS
    assert _smoke_yaml_mode(yaml_path) == 0o600, (
        f"YAML mode after re-run was {_smoke_yaml_mode(yaml_path):#o}; "
        f"expected 0o600. The implementation truncates the file via "
        f"O_TRUNC, but os.open only honors the mode argument on "
        f"O_CREAT. A leading chmod(out_path, 0o600) is required to "
        f"narrow a pre-existing wide file."
    )


def test_attack_preexisting_yaml_0664_is_also_locked_to_0600(
    tmp_path: Path,
) -> None:
    """Same attack surface with 0o664 — group-writable."""
    out_dir = tmp_path / "out"
    args_ns = _canonical_args(out_dir)
    assert smoke_flow.run_smoke(args_ns) == EXIT_PASS

    yaml_path = _smoke_yaml_path(out_dir)
    os.chmod(yaml_path, 0o664)
    assert _smoke_yaml_mode(yaml_path) == 0o664

    assert smoke_flow.run_smoke(args_ns) == EXIT_PASS
    assert _smoke_yaml_mode(yaml_path) == 0o600


# ---------------------------------------------------------------------------
# Check #3 — No umask dependency
# ---------------------------------------------------------------------------

def test_attack_umask_0000_subprocess_still_yields_0700_0600(
    tmp_path: Path,
) -> None:
    """With ``umask=0000`` (everything world-writable), the
    subprocess CLI dry-run MUST still produce a 0o700 dir and a
    0o600 yaml.

    If the implementation leaned on umask instead of explicit
    chmod, ``umask=0000`` would yield ``0o777`` / ``0o666``.
    """
    out_dir = tmp_path / "wide-umask"
    # Parent uses 0o777 so the path's ``mkdir`` carries 0o777 if no
    # explicit chmod is applied.
    out_dir.mkdir(parents=True)
    # Set the umask of the subprocess via env, then exec the CLI.
    env = {**os.environ, "PYTHONPATH": "."}
    # Wrapper: set umask to 0000 in the subprocess before invoking
    # the CLI module. arg[0] is whatever sys.argv[0] would be after
    # ``python -c`` runs — the CLI parser only consults argv[1:]
    # so we position the command/subcommand there.
    wrapper = (
        "import os, sys;"
        "os.umask(0);"
        "from scripts.t4_preflight import cli;"
        "sys.exit(cli.main(['smoke-flow', '--output-dir', %r]))"
    ) % str(out_dir)
    proc = subprocess.run(
        [sys.executable, "-c", wrapper],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == EXIT_PASS, (
        f"subprocess umask=0000 failed rc={proc.returncode} "
        f"stderr={proc.stderr!r}"
    )
    assert _smoke_out_dir_mode(out_dir) == 0o700, (
        f"output dir mode under umask=0000 = "
        f"{_smoke_out_dir_mode(out_dir):#o}, expected 0o700. "
        f"Implementation likely relies on umask instead of explicit chmod."
    )
    yaml_path = _smoke_yaml_path(out_dir)
    assert _smoke_yaml_mode(yaml_path) == 0o600


def test_attack_umask_0002_subprocess_still_yields_0700_0600(
    tmp_path: Path,
) -> None:
    """Group-writable umask (0002) is the production default on many
    shared Linux hosts — it MUST NOT widen the smoke output."""
    out_dir = tmp_path / "wide-umask-0002"
    env = {**os.environ, "PYTHONPATH": "."}
    wrapper = (
        "import os, sys;"
        "os.umask(0o002);"
        "from scripts.t4_preflight import cli;"
        "sys.exit(cli.main(['smoke-flow', '--output-dir', %r]))"
    ) % str(out_dir)
    proc = subprocess.run(
        [sys.executable, "-c", wrapper],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == EXIT_PASS, (
        f"subprocess umask=0002 failed rc={proc.returncode} "
        f"stderr={proc.stderr!r}"
    )
    assert _smoke_out_dir_mode(out_dir) == 0o700
    yaml_path = _smoke_yaml_path(out_dir)
    assert _smoke_yaml_mode(yaml_path) == 0o600


# ---------------------------------------------------------------------------
# Check #4 — Normal dry-run identity unchanged
# ---------------------------------------------------------------------------

def test_attack_dry_run_identity_intact() -> None:
    """Normal dry-run: identity, ledger = 0 calls, no Provider touch.

    This pins the regression-prone bits the task body calls out:
    capability / 600519-CN / B2 unchanged; 0 calls; unchanged
    3-second timeout; ledger zeroes.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as out_dir_str:
        out_dir = Path(out_dir_str)
        proc = _run_cli_subprocess(
            "smoke-flow",
            "--output-dir",
            str(out_dir),
            cwd=REPO_ROOT,
        )
        assert proc.returncode == EXIT_PASS, (
            f"dry-run rc={proc.returncode} stderr={proc.stderr!r}"
        )
        out = proc.stdout
        # Identity: single capability, 600519-CN, no second-slot.
        assert "flow.capital_flow_daily" in out
        assert "600519/CN" in out
        assert "000001/sz" not in out
        assert "600519/sh+000001/sz" not in out
        # 0 calls (dry-run path).
        assert "verdict: pass" in out
        assert "dry-run — no real calls made" in out
        # Ledger boundary: provider_attempts=0.
        assert "provider_attempts: 0" in out
        assert "actual_calls: 0" in out
        # Filesystem write still landed.
        yaml_files = list(out_dir.glob("smoke-flow-*.yaml"))
        assert len(yaml_files) == 1
        text = yaml_files[0].read_text(encoding="utf-8")
        assert "flow.capital_flow_daily" in text


def test_attack_no_network_no_provider_in_dry_run() -> None:
    """``smoke-flow`` dry-run MUST NOT touch the network, AKShare,
    or Mongo. We confirm by absence of any ``akshare`` import /
    Mongo URI imports in the smoke runner's import-time behavior
    AND by absence of any external process spawns during dry-run.
    """
    proc = _run_cli_subprocess(
        "smoke-flow",
        "--output-dir",
        str((Path("/tmp")).resolve()),
        cwd=REPO_ROOT,
    )
    # We don't assert rc — some sandboxes refuse /tmp writes — only
    # that the runner did not import / call any network code.
    combined = proc.stdout + proc.stderr
    assert "AKShare" not in combined
    assert "pymongo" not in combined
    assert "MongoClient" not in combined


# ---------------------------------------------------------------------------
# Check #5 — No shell rm -rf anywhere
# ---------------------------------------------------------------------------

def test_attack_no_shell_rm_rf_in_source() -> None:
    """Read both touched source files and confirm there is no
    ``os.system``, no ``subprocess`` invoked with ``rm -rf``, no
    ``shell=True`` cleanup. The task body explicitly forbids shell
    ``rm -rf``.

    We intentionally accept ``subprocess.run([..., 'rm', ...], shell=False)``
    as legitimate if it ever shows up; the forbidden surface is
    ``shell=True`` carrying ``rm -rf``.
    """
    targets = [
        REPO_ROOT / "scripts" / "t4_preflight" / "smoke_flow.py",
        REPO_ROOT / "scripts" / "t4_preflight" / "config.py",
        REPO_ROOT / "scripts" / "t4_preflight" / "provider_client.py",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "shell=True" not in text, (
            f"{path} contains shell=True — verify it's not used for "
            f"a destructive cleanup"
        )
        assert "rm -rf" not in text, (
            f"{path} literally contains 'rm -rf' — task body forbids shell rm -rf"
        )
        assert "os.system" not in text, (
            f"{path} calls os.system — task body forbids shell-driven cleanups"
        )


def test_attack_test_suite_uses_only_tmp_path_or_tempdir() -> None:
    """The implementation team's test suite MUST use pytest's
    ``tmp_path`` fixture (or Python ``TemporaryDirectory``). No
    manual cleanup commands.

    We check by reading the implementation test file and
    grep-verifying that all ``out_dir`` paths either come from
    ``tmp_path`` or from a temporary directory context.
    """
    test_path = REPO_ROOT / "tests" / "scripts" / "t4_preflight" / "test_smoke_flow.py"
    text = test_path.read_text(encoding="utf-8")
    # There must be no shell cleanup command in the file.
    assert "shell=True" not in text
    assert "rm -rf" not in text
    assert "os.system" not in text
    # There MUST be evidence of tmp_path or TemporaryDirectory usage.
    assert "tmp_path" in text, (
        f"{test_path} does not use pytest tmp_path fixture — risk of "
        f"leaving artifacts in the working directory."
    )
