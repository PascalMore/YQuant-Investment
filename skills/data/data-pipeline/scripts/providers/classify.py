"""Failure classification + error sanitisation (SPEC-03-006 §4.5, §7.3).

Used by both providers to map raw subprocess/SDK errors into
``FailureReason(kind, retryable, message)`` so the Router can make
retry-vs-fallback decisions consistently.
"""
from __future__ import annotations

import os
import re

from .base import FailureKind, FailureReason


# Marker substrings (case-insensitive) used by ``classify_failure``.
# Order matters in RETRYABLE_MARKERS / QUOTA_MARKERS — earlier wins.
RETRYABLE_MARKERS: tuple[str, ...] = (
    "system error",
    "temporarily",
    "timeout",
    "timed out",
    "rate limit",
    "too many requests",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "connection reset",
    "connection refused",
    "econnreset",
    "econnrefused",
)

QUOTA_MARKERS: tuple[str, ...] = (
    "quota exceeded",
    "insufficient quota",
    "rate limit",
    "too many requests",
    "http 429",
    "额度",
    "配额",
)

PARSE_MARKERS: tuple[str, ...] = (
    "json decode",
    "expected json array",
    "no valid json",
    "jsondecodeerror",
)


_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Z_AI_API_KEY=[^\s\"'<>]+"),
    re.compile(r"MINIMAX_API_KEY=[^\s\"'<>]+"),
    re.compile(r"YQUANT_[A-Z_]+=[^\s\"'<>]+"),
)


def classify_failure(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int | None = None,
    exception: BaseException | None = None,
) -> FailureReason:
    """Map raw subprocess/SDK errors to a classified FailureReason.

    Rules (evaluated in order):
      1. ``FileNotFoundError``                       → CLI_NOT_FOUND, retryable=False
      2. ``subprocess.TimeoutExpired``               → TIMEOUT,       retryable=True
      3. QUOTA_MARKERS hit                          → QUOTA_EXCEEDED, retryable=False
      4. RETRYABLE_MARKERS hit                      → NETWORK,        retryable=True
      5. PARSE_MARKERS hit                          → PARSE_ERROR,    retryable=False
      6. returncode != 0                            → UNKNOWN,        retryable=False
      7. fallback                                   → UNKNOWN,        retryable=False
    """
    if isinstance(exception, FileNotFoundError):
        return FailureReason(FailureKind.CLI_NOT_FOUND, False, _exc_msg(exception))
    if exception is not None and _is_timeout_exception(exception):
        return FailureReason(FailureKind.TIMEOUT, True, _exc_msg(exception))

    text = f"{stdout or ''}\n{stderr or ''}".lower()

    if any(marker.lower() in text for marker in QUOTA_MARKERS):
        return FailureReason(
            FailureKind.QUOTA_EXCEEDED,
            False,
            sanitize_error(stdout or stderr or "quota exceeded"),
        )
    if any(marker.lower() in text for marker in RETRYABLE_MARKERS):
        return FailureReason(
            FailureKind.NETWORK,
            True,
            sanitize_error(stdout or stderr or "transient failure"),
        )
    if any(marker.lower() in text for marker in PARSE_MARKERS):
        return FailureReason(
            FailureKind.PARSE_ERROR,
            False,
            sanitize_error(stdout or stderr or "json parse error"),
        )
    if returncode not in (None, 0):
        return FailureReason(
            FailureKind.UNKNOWN,
            False,
            sanitize_error(stderr or stdout or f"returncode={returncode}"),
        )
    return FailureReason(
        FailureKind.UNKNOWN,
        False,
        sanitize_error(stdout or stderr or str(exception) or "unknown failure"),
    )


def _is_timeout_exception(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {"TimeoutExpired", "TimeoutError", "asyncio.TimeoutError"}:
        return True
    return False


def _exc_msg(exc: BaseException) -> str:
    return sanitize_error(str(exc) or type(exc).__name__)


# ---------------------------------------------------------------------------
# Error sanitisation (SPEC-03-006 §7.3)
# ---------------------------------------------------------------------------

_MAX_LEN = 500


def sanitize_error(text: str | None) -> str:
    """Redact API tokens, replace $HOME with <HOME>, truncate to <=500 chars.

    The output is safe to write to debug JSON, pending CSV/JSON, stdout.
    """
    if not text:
        return ""
    out = str(text)
    for pattern in _TOKEN_PATTERNS:
        out = pattern.sub("***", out)
    home = os.path.expanduser("~")
    if home and home != "~":
        out = out.replace(home, "<HOME>")
    # Defensive: also redact obvious home-prefixed paths.
    out = re.sub(r"/home/[A-Za-z0-9_\-]+", "<HOME>", out)
    if len(out) > _MAX_LEN:
        out = out[:_MAX_LEN] + "...<truncated>"
    return out
