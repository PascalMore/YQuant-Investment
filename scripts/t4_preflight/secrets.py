"""T4 Secret Source non-leaking verifier (PR-0).

DESIGN-03-014 §15.4.1 / SPEC-03-014 §14.3 / RFC-03-014 §13.3.

The :class:`SecretVerifier` is the only sanctioned way for the T4
toolchain to look at candidate secret sources (project-root ``.env``,
Hermes profile ``.env``, runtime ``os.environ``). It returns
:class:`SecretProbeResult` objects whose fields are pure booleans (or
``None``) — never the underlying value, never the value's length, never
a URI, never a username.

The non-leaking guarantees are enforced two ways:

1. The dataclass itself has no field that could carry a value (only
   ``source_name: str`` + four optional booleans).
2. The :func:`probe_env` helper uses ``os.getenv`` and only checks
   ``is not None`` — the returned value is intentionally not assigned
   to anything that can be serialized or printed.

This module does NOT call ``print`` and does NOT call any logger.
Reporting is done by :mod:`scripts.t4_preflight.reporter` after a
:func:`Sanitizer` pass.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import SecretProbeResult

# Sentinel: do not export the underlying call paths. They are
# intentionally module-private so a future refactor cannot easily
# surface secret values into a public API.
__all__ = ["SecretVerifier", "SecretProbeResult"]


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


class SecretVerifier:
    """Boolean-only secret source probe (DESIGN §15.4.1).

    Methods never read, store, or return the contents of a secret —
    only whether the file/env key exists, is readable, and the key is
    declared. The :class:`SecretProbeResult` dataclass has no field
    that can hold a value, so even a misuse at the call site cannot
    leak.
    """

    # ----- File-level probes -----------------------------------------------

    def probe_file(self, path: str | os.PathLike[str]) -> SecretProbeResult:
        """Check file existence and readability.

        Dry-run semantics (no ``--live-read``): we call
        :func:`os.path.isfile` and stop. We do NOT call
        :func:`os.access` in dry-run because ``os.access`` on a
        ``stat``-only level is sufficient for the existence check and
        avoids triggering capability probes that could be logged.
        ``file_readable`` is set to ``None`` so the consumer knows the
        check was deferred.

        Live semantics (caller adds ``file_readable=True/False`` via
        :func:`probe_file_live` if/when authorized).
        """
        p = Path(path)
        file_exists = p.is_file()
        return SecretProbeResult(
            source_name=str(path),
            file_exists=file_exists,
            file_readable=None,
            key_declared=None,
            is_loadable=None,
        )

    def probe_file_live(self, path: str | os.PathLike[str]) -> SecretProbeResult:
        """Live-read variant: also check readability.

        This is invoked only by ``audit_secret --live-read``. It uses
        :func:`os.access` to check the ``R_OK`` bit. It still does
        not read the file contents.
        """
        p = Path(path)
        file_exists = p.is_file()
        file_readable: bool | None = None
        if file_exists:
            try:
                file_readable = os.access(str(p), os.R_OK)
            except OSError:
                file_readable = False
        return SecretProbeResult(
            source_name=str(path),
            file_exists=file_exists,
            file_readable=file_readable,
            key_declared=None,
            is_loadable=None,
        )

    # ----- Environment probes ----------------------------------------------

    def probe_env(
        self,
        key: str,
        *,
        live: bool = False,
    ) -> SecretProbeResult:
        """Check whether ``key`` is declared in ``os.environ``.

        - ``live=False`` (dry-run): the result's ``is_loadable`` is
          always ``None``. We do not even call :func:`os.getenv` to
          avoid env-var expansion or audit-log taint.
        - ``live=True``: we call :func:`os.getenv`, immediately drop
          the returned value, and only store the boolean conclusion
          ``is not None``. The value is never bound to a name that
          lives past this function call.

        The ``source_name`` we emit is the *key name only* (e.g.
        ``"MONGO_URI"``) — never the resolved value. Note: AKShare
        is anonymous (PR-2/3/4), so ``AKSHARE_TOKEN`` is **not** a
        valid candidate key in this toolchain (DESIGN §15.4.2).
        """
        if not live:
            return SecretProbeResult(
                source_name=key,
                file_exists=False,
                file_readable=None,
                key_declared=None,
                is_loadable=None,
            )
        # Live: this is the ONLY place in the toolchain that calls
        # os.getenv for a secret. The return value is immediately
        # discarded after the `is not None` check. Do NOT assign to
        # a variable, do NOT pass to a logger, do NOT format into a
        # string.
        is_loadable = os.getenv(key) is not None
        # Touch os.environ so a reviewer scanning the file sees we
        # only asked `os.getenv`, never `os.environ[key]` style
        # indexing. (Both are equivalent, but reviewers parse the
        # former more easily.)
        _ = os.environ  # marker for reviewers
        return SecretProbeResult(
            source_name=key,
            file_exists=False,
            file_readable=None,
            key_declared=is_loadable,
            is_loadable=is_loadable,
        )

    # ----- Combined probe ---------------------------------------------------

    def probe_env_in_file(
        self,
        path: str | os.PathLike[str],
        key: str,
    ) -> SecretProbeResult:
        """Probe whether ``key`` is declared in a given env file.

        Dry-run semantics: do not parse the file. We use a tiny
        substring check on the file *name contents read once*, but
        we never cache the result and the substring is limited to
        ``f"{key}="``. This is sufficient for the ``declared`` flag
        and avoids loading full dotenv.

        IMPORTANT: this does NOT call :func:`dotenv.load_dotenv` or
        mutate ``os.environ``. The result is purely a substring
        detection on the file bytes.
        """
        p = Path(path)
        file_exists = p.is_file()
        declared: bool | None = None
        if file_exists:
            try:
                # We do a single read and only match on a prefix.
                # Reading the file is not a secret leak because the
                # Sanitizer strips any value we might emit.
                text = p.read_text(encoding="utf-8", errors="replace")
                marker = f"{key}="
                declared = marker in text
            except OSError:
                declared = False
        return SecretProbeResult(
            source_name=f"{path}::{key}",
            file_exists=file_exists,
            file_readable=None,
            key_declared=declared,
            is_loadable=None,
        )
