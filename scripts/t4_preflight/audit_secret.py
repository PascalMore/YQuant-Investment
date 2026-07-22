"""PR-0: Secret source non-leaking audit CLI (DESIGN §15.4 / SPEC §14.3).

Default dry-run: do not read file contents, do not call os.getenv.
Output is a YAML audit report (boolean conclusions only) written to
``--output-dir`` and printed to stdout.

Hard rules (DESIGN §15.3.1, §15.4.1):

* No ``--apply`` / ``--write`` / ``--force`` flags.
* No secret value/length/URI ever enters stdout, stderr, or the YAML
  report. The :class:`SecretProbeResult` dataclass is structurally
  incapable of carrying a value; the :class:`Sanitizer` provides a
  second line of defense.
* Exit code:

  - 0 → at least one candidate has both ``file_exists=True`` and
        ``key_declared=True`` (when ``--live-read`` is on).
  - 1 → conditional (declared in env but file unreadable, or
        declared in file but not in env, etc.).
  - 3 → all candidates ``file_exists=False`` AND env
        ``is_loadable=False`` (NOT_AUTHORIZED).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import (
    CANDIDATE_ENV_FILES,
    CANDIDATE_SECRET_KEYS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TIMEOUT_SECONDS,
    EXIT_CONDITIONAL,
    EXIT_PASS,
    EXIT_UNAUTHORIZED,
)
from .models import SecretAuditResult, SecretProbeResult
from .reporter import secret_audit_to_yaml
from .secrets import SecretVerifier

__all__ = ["build_arg_parser", "run_audit", "main"]


# Avoid zoneinfo dependency. YQuant project is in Asia/Shanghai
# (+08:00) and we use a fixed offset for ISO 8601 timestamps.
_CST = timezone(timedelta(hours=8))


def _now_iso() -> str:
    """ISO 8601 in Asia/Shanghai."""
    return datetime.now(tz=_CST).replace(microsecond=0).isoformat()


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI argument parser. No ``--apply`` / ``--write`` / ``--force``."""
    p = argparse.ArgumentParser(
        prog="scripts.t4_preflight.cli audit-secret",
        description=(
            "PR-0: Non-leaking audit of candidate secret sources. "
            "Default dry-run; pass --live-read to invoke os.getenv."
        ),
    )
    p.add_argument(
        "--live-read",
        action="store_true",
        default=False,
        help=(
            "Authorize live env probing. Without this flag, the tool "
            "stops at file existence + accessibility."
        ),
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="YAML report output directory.",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Reserved; current implementation does not perform network I/O.",
    )
    return p


def _candidate_paths() -> list[Path]:
    """Resolve candidate env file paths relative to CWD.

    The first entry is always ``<cwd>/.env`` (project root). The
    second is the Hermes profile path, expanded to the user's home.
    The toolchain never assumes a hardcoded path; it always uses
    :class:`Path` so test fixtures can override.
    """
    out: list[Path] = []
    for raw in CANDIDATE_ENV_FILES:
        p = Path(raw).expanduser()
        out.append(p)
    return out


def _resolve_source_name(p: Path) -> str:
    """Map a path to a stable source label.

    The label is the *label only* — not the path. The reporter will
    emit a separate ``path_checked`` field if the absolute path is
    needed (it is not, by design).
    """
    expanded = p.expanduser()
    hermes_profile_env = Path("~/.hermes/profiles/yquant/.env").expanduser()
    if expanded == hermes_profile_env:
        return "hermes_profile_env"
    if expanded == Path(".env") or expanded == Path.cwd() / ".env":
        return "project_root_env"
    return "candidate_env_file"


def run_audit(args: argparse.Namespace) -> int:
    """Execute the audit and return an exit code."""
    verifier = SecretVerifier()
    sources: list[SecretProbeResult] = []
    missing_keys: list[str] = []

    # ----- File candidates -------------------------------------------------
    for path in _candidate_paths():
        label = _resolve_source_name(path)
        if args.live_read:
            file_probe = verifier.probe_file_live(path)
        else:
            file_probe = verifier.probe_file(path)
        # We rename the source to the label so the YAML report does
        # not contain absolute paths.
        file_probe = SecretProbeResult(
            source_name=label,
            file_exists=file_probe.file_exists,
            file_readable=file_probe.file_readable,
            key_declared=file_probe.key_declared,
            is_loadable=file_probe.is_loadable,
        )
        # Per-key probes within this file.
        for key in CANDIDATE_SECRET_KEYS:
            key_probe = verifier.probe_env_in_file(path, key)
            # Combine the file-level and key-level conclusions into a
            # single SecretProbeResult for this key, with the source
            # name as the label.
            combined = SecretProbeResult(
                source_name=f"{label}::{key}",
                file_exists=file_probe.file_exists,
                file_readable=file_probe.file_readable,
                key_declared=key_probe.key_declared,
                is_loadable=None,
            )
            sources.append(combined)
            if (
                combined.file_exists
                and combined.key_declared is False
                and key not in missing_keys
            ):
                # File exists but the key is not declared in it —
                # candidate missing.
                missing_keys.append(key)
        # Also add a bare file existence entry (no key) so the
        # report makes the file-level conclusion visible.
        sources.append(file_probe)

    # ----- Runtime env candidates -----------------------------------------
    for key in CANDIDATE_SECRET_KEYS:
        env_probe = verifier.probe_env(key, live=args.live_read)
        # Rename to a stable label.
        env_probe = SecretProbeResult(
            source_name=f"runtime_env::{key}",
            file_exists=False,
            file_readable=None,
            key_declared=env_probe.key_declared,
            is_loadable=env_probe.is_loadable,
        )
        sources.append(env_probe)

    # ----- Verdict ---------------------------------------------------------
    # Per SPEC §14.3: at least one source must have BOTH a
    # key-declared True AND (file exists OR env loadable) for the
    # overall status to be `authorized`. In dry-run, we mark
    # `conditional_authorized`.
    any_declared_in_file = any(
        s.key_declared is True and s.file_exists for s in sources
    )
    any_loadable_in_env = any(s.is_loadable is True for s in sources)

    if args.live_read:
        if any_declared_in_file and any_loadable_in_env:
            status = "authorized"
            exit_code = EXIT_PASS
        elif any_declared_in_file or any_loadable_in_env:
            status = "conditional_authorized"
            exit_code = EXIT_CONDITIONAL
        else:
            status = "unauthorized"
            exit_code = EXIT_UNAUTHORIZED
    else:
        if any_declared_in_file:
            status = "conditional_authorized"
            exit_code = EXIT_CONDITIONAL
        else:
            status = "unauthorized"
            exit_code = EXIT_UNAUTHORIZED

    # ----- Output ----------------------------------------------------------
    result = SecretAuditResult(
        generated_at=_now_iso(),
        sources=tuple(sources),
        missing_keys=tuple(missing_keys),
        status=status,
    )
    yaml_text = secret_audit_to_yaml(result)

    out_dir = Path(args.output_dir).expanduser()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"audit-secret-{datetime.now().strftime('%Y%m%d')}.yaml"
        out_path.write_text(yaml_text, encoding="utf-8")
    except OSError as exc:
        # We deliberately do not print the path on disk-write failure
        # to avoid leaking layout; we exit with FAIL.
        print(f"audit-secret: cannot write report: {exc.__class__.__name__}", file=sys.stderr)
        return 2

    print(yaml_text)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_audit(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
