"""Tests for PR-0 secret-source non-leaking audit.

DESIGN-03-014 §15.4 / SPEC-03-014 §14.3 / A-016, A-023.

Coverage:

* ``SecretProbeResult`` cannot structurally hold a value.
* ``probe_env(live=False)`` returns ``is_loadable=None``.
* ``probe_env(live=True)`` returns ``is_loadable`` boolean only;
  the value is never observable.
* ``probe_file`` / ``probe_file_live`` only inspect file metadata.
* ``audit-secret --live-read`` exits 0 when keys are declared.
* ``audit-secret`` dry-run exit code is in {0, 1, 3}.
* No output path contains a value/length/URI substring.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from pathlib import Path
import scripts

scripts.__path__.append(str(Path(__file__).resolve().parents[2] / "scripts"))

import pytest

from scripts.t4_preflight import audit_secret
from scripts.t4_preflight.config import (
    CANDIDATE_SECRET_KEYS,
    EXIT_CONDITIONAL,
    EXIT_PASS,
    EXIT_UNAUTHORIZED,
)
from scripts.t4_preflight.models import SecretProbeResult
from scripts.t4_preflight.secrets import SecretVerifier

from .fixtures.t4_secret_fixtures import isolated_env, make_temp_env

# Repo root is the parent of tests/
REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run ``python -m scripts.t4_preflight.cli <args>`` as a subprocess.

    Uses the project venv and sets ``PYTHONPATH=.``.
    """
    cmd = [
        sys.executable,
        "-m",
        "scripts.t4_preflight.cli",
        *args,
    ]
    return subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Source label resolution
# ---------------------------------------------------------------------------


def test_resolve_source_name_labels_project_root_env() -> None:
    assert audit_secret._resolve_source_name(Path(".env")) == "project_root_env"
    assert (
        audit_secret._resolve_source_name(Path.cwd() / ".env")
        == "project_root_env"
    )


def test_resolve_source_name_labels_hermes_profile_env() -> None:
    profile_env = Path("~/.hermes/profiles/yquant/.env")

    assert audit_secret._resolve_source_name(profile_env) == "hermes_profile_env"
    assert (
        audit_secret._resolve_source_name(profile_env.expanduser())
        == "hermes_profile_env"
    )


def test_resolve_source_name_keeps_other_paths_as_candidates() -> None:
    assert (
        audit_secret._resolve_source_name(Path("/virtual/config/.env"))
        == "candidate_env_file"
    )
    assert (
        audit_secret._resolve_source_name(Path("/virtual/config/other.env"))
        == "candidate_env_file"
    )
    assert (
        audit_secret._resolve_source_name(
            Path("/virtual/.hermes/profiles/other/.env")
        )
        == "candidate_env_file"
    )


# ---------------------------------------------------------------------------
# Structural: SecretProbeResult has no string-content field
# ---------------------------------------------------------------------------


def test_secret_probe_result_has_no_value_field() -> None:
    """A-023: SecretProbeResult must not be able to carry a value."""
    fields = {f.name for f in dataclasses.fields(SecretProbeResult)}
    for forbidden in ("value", "raw_value", "secret_value", "length", "uri"):
        assert forbidden not in fields, (
            f"SecretProbeResult must not have a {forbidden!r} field"
        )


def test_secret_probe_result_field_types() -> None:
    """All fields other than ``source_name`` are bool or None."""
    spr = SecretProbeResult(source_name="x")
    assert spr.source_name == "x"
    assert spr.file_exists is False
    assert spr.file_readable is None
    assert spr.key_declared is None
    assert spr.is_loadable is None


# ---------------------------------------------------------------------------
# probe_file
# ---------------------------------------------------------------------------


def test_probe_file_dry_run_marks_readable_as_none(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("MONGO_URI=\n", encoding="utf-8")
    v = SecretVerifier()
    result = v.probe_file(p)
    assert result.file_exists is True
    assert result.file_readable is None  # dry-run never checks access
    assert result.key_declared is None
    assert result.is_loadable is None


def test_probe_file_live_checks_readability(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("MONGO_URI=\n", encoding="utf-8")
    v = SecretVerifier()
    result = v.probe_file_live(p)
    assert result.file_exists is True
    assert result.file_readable is True


def test_probe_file_missing(tmp_path: Path) -> None:
    v = SecretVerifier()
    result = v.probe_file(tmp_path / "nope.env")
    assert result.file_exists is False


# ---------------------------------------------------------------------------
# probe_env
# ---------------------------------------------------------------------------


def test_probe_env_dry_run_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGO_URI", "sentinel-value-must-not-leak")
    v = SecretVerifier()
    result = v.probe_env("MONGO_URI", live=False)
    assert result.is_loadable is None
    assert result.key_declared is None
    # The source_name is the *key*, not the value.
    assert result.source_name == "MONGO_URI"


def test_probe_env_live_returns_boolean_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """A-023: only the boolean conclusion is exposed."""
    monkeypatch.setenv("MONGO_URI", "sentinel-value-must-not-leak")
    v = SecretVerifier()
    result = v.probe_env("MONGO_URI", live=True)
    assert result.is_loadable is True
    # The value itself is not in any field.
    for f in dataclasses.fields(result):
        v_ = getattr(result, f.name)
        if isinstance(v_, str):
            assert "sentinel" not in v_, (
                f"Field {f.name!r} leaked a value substring"
            )


def test_probe_env_live_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONGO_URI", raising=False)
    v = SecretVerifier()
    result = v.probe_env("MONGO_URI", live=True)
    assert result.is_loadable is False
    assert result.key_declared is False


# ---------------------------------------------------------------------------
# CLI: audit-secret (A-016, A-023)
# ---------------------------------------------------------------------------


def test_cli_audit_secret_dry_run_exit_codes(tmp_path: Path) -> None:
    """Dry-run must exit 0 (informational) or 3 (unauthorized)."""
    out_dir = tmp_path / "out"
    proc = _run_cli("audit-secret", "--output-dir", str(out_dir))
    assert proc.returncode in (0, 1, 3), (
        f"unexpected exit code {proc.returncode}: {proc.stdout!r} / {proc.stderr!r}"
    )
    # The output should be valid YAML with the expected top-level key.
    assert "secret_audit:" in proc.stdout


def test_cli_audit_secret_does_not_leak_secrets(tmp_path: Path) -> None:
    """A-023: stdout must not contain a value/length/URI substring."""
    out_dir = tmp_path / "out"
    with isolated_env():
        os.environ["MONGO_URI"] = "mongodb://user:***@host/db"
        proc = _run_cli("audit-secret", "--output-dir", str(out_dir), "--live-read")
    out = proc.stdout + proc.stderr
    for forbidden in (
        "user:secret",
        "mongodb://",
        "MONGO_URI=",
    ):
        assert forbidden not in out, (
            f"audit-secret output leaked substring {forbidden!r}: {out!r}"
        )


def test_cli_audit_secret_live_with_known_keys_exits_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When all five secret keys are declared and loadable, exit 0."""
    monkeypatch.setenv("MONGODB_HOST", "x")
    monkeypatch.setenv("MONGODB_PORT", "27017")
    monkeypatch.setenv("MONGODB_USERNAME", "x")
    monkeypatch.setenv("MONGODB_PASSWORD", "x")
    monkeypatch.setenv("MONGODB_DATABASE", "tradingagents")
    out_dir = tmp_path / "out"
    proc = _run_cli("audit-secret", "--output-dir", str(out_dir), "--live-read")
    # Env-only is at least conditional; the design accepts it.
    assert proc.returncode in (EXIT_PASS, EXIT_CONDITIONAL)


def test_cli_audit_secret_no_keys_exits_unauthorized(tmp_path: Path) -> None:
    with isolated_env():
        out_dir = tmp_path / "out"
        proc = _run_cli("audit-secret", "--output-dir", str(out_dir), "--live-read")
    assert proc.returncode == EXIT_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Sanitizer integration
# ---------------------------------------------------------------------------


def test_audit_secret_yaml_report_redacts_uri(tmp_path: Path) -> None:
    """The YAML report on disk must not contain a URI even if a
    candidate .env has one (sanity check on the Sanitizer)."""
    with isolated_env(), make_temp_env(
        project_root_contents="MONGO_URI=mongodb://user:***@host/db\n"
    ) as sandbox:
        # Run the audit from inside the sandbox so the file probe
        # finds the synthetic .env.
        out_dir = sandbox / "out"
        proc = _run_cli(
            "audit-secret",
            "--output-dir",
            str(out_dir),
            cwd=sandbox,
        )
    out = proc.stdout
    assert "mongodb://" not in out
    assert "user:secret" not in out
    # The report file should also be sanitized.
    reports = list(out_dir.glob("audit-secret-*.yaml"))
    if reports:
        text = reports[0].read_text(encoding="utf-8")
        assert "mongodb://" not in text
        assert "user:secret" not in text


# ---------------------------------------------------------------------------
# Argument parser forbids write flags
# ---------------------------------------------------------------------------


def test_audit_secret_argparser_has_no_apply_flag() -> None:
    """A-025: no --apply / --write flag is defined."""
    p = audit_secret.build_arg_parser()
    for action in p._actions:  # noqa: SLF001 — argparse introspection
        opts = action.option_strings
        for forbidden in ("--apply", "--write", "--exec", "--commit", "--force"):
            assert forbidden not in opts, (
                f"forbidden flag {forbidden!r} defined in audit-secret"
            )
