"""Fixtures for PR-0 secret-audit tests.

DESIGN-03-014 §15.4 / SPEC-03-014 §14.3.

Provides a tiny helper to create a temp directory with a synthetic
``.env`` file. Tests use :func:`make_temp_env` to fabricate a clean
sandbox where ``SecretVerifier`` can probe without touching the
real ``~/.hermes`` or project-root ``.env``.

The fixtures never contain real secret values. They only declare
keys with empty or placeholder values to test the boolean probe
contract.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def make_temp_env(
    *,
    project_root_contents: str | None = None,
    project_root_present: bool = True,
) -> Iterator[Path]:
    """Create a sandbox directory with a synthetic ``.env`` file.

    Parameters
    ----------
    project_root_contents:
        Text content of the synthetic ``.env`` file. Pass ``None`` to
        omit the file entirely (file_exists=False path).
    project_root_present:
        When False, the file is not created regardless of contents.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if project_root_present and project_root_contents is not None:
            (root / ".env").write_text(project_root_contents, encoding="utf-8")
        # Sanity: caller can chdir if they want, but we don't enforce
        # it here. The SecretVerifier accepts an absolute path.
        yield root


@contextmanager
def isolated_env(
    *,
    clear: tuple[str, ...] = (
        "MONGO_URI",
        "MONGODB_URI",
        "MONGODB_HOST",
        "MONGODB_PORT",
        "MONGODB_USERNAME",
        "MONGODB_PASSWORD",
        "MONGODB_DATABASE",
    ),
) -> Iterator[None]:
    """Context manager that snapshots and clears sensitive env vars.

    The caller is expected to set the env vars they want to test
    *inside* the ``with`` block. The pre-existing values are
    restored on exit.
    """
    saved: dict[str, str | None] = {}
    for key in clear:
        saved[key] = os.environ.get(key)
        if key in os.environ:
            del os.environ[key]
    try:
        yield
    finally:
        for key, val in saved.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
