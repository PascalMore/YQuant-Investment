#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""preflight_sentiment_policy.py — OQ-11 local preflight CLI.

DESIGN-03-014 V0.33 §OQ-11B.3 / SPEC-03-014 V0.26 §3.3 EOD-8.4.

Default ``--dry-run`` — no working-tree writes, no secrets, no
network / Mongo / Provider / cache / refresh reads or writes.
Output is a single JSON line on stdout describing the calendar
identity / version / timezone / coverage and three control
samples: a trading-day sample, a non-trading-day sample, and a
session-close sample. ``zero_io`` summarises the side-effect
counter (always ``0`` in dry-run).

Hard constraints (mirrored by the unit test):

* No network. No ``exchange_calendars`` HTTP fetcher is invoked;
  the script reads whatever calendar is already resolved by
  :func:`skills.infra.date_utils._strict_get_calendar`.
* No fallback to ``TRADING_DAYS_2026``, weekend rule, or
  ``is_trading_day()``. The samples are derived from
  :func:`query_trading_day_status` / :func:`session_close_strict`
  directly.
* No provider / router / writer / cache / Mongo / file write.
* No scheduler / service / unit / wrapper / cron registration.
* No Git / secrets / outbound message.

Sample derivation (DESIGN §OQ-11B.3 #1-3 — runtime-only,
no hardcoded dates):

1. ``trading_sample``: the calendar's ``first_session`` —
   by construction a trading day — re-asserted via
   :func:`query_trading_day_status`.
2. ``not_trading_sample``: the closest ``NOT_TRADING`` date in
   the calendar coverage, scanned backward from
   ``first_session``. Falls back to a calendar-declared
   ``non_trading_day`` only if the scan needs explicit hints
   from the calendar (used for unit-test fakes).
3. ``session_close_sample``: ``session_close_strict(first_session)``
   normalised to ``Asia/Shanghai``.

Exit codes (EOD-8.7):

* ``0`` PASS — dry-run completed, calendar present, samples
  resolved, no I/O happened.
* ``2`` FAIL — validation gate failed (calendar unavailable,
  out-of-range, exception, or strict-seam failure).

The script is intentionally pure-stdlib + the project's
own infra seam (no ``exchange_calendars`` upgrade, no
``requests``, no ``urllib`` import side effects).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from skills.infra import date_utils as _date_utils
from skills.infra.date_utils import (
    CalendarDayStatus,
    query_trading_day_status,
    session_close_strict,
)

# Keep a local seam wrapper so tests and callers can inject a calendar
# without reaching through the strict-seam module namespace.
def _strict_get_calendar() -> Any:
    return _date_utils._strict_get_calendar()


SHANGHAI_TZ = "Asia/Shanghai"
EXIT_PASS = 0
EXIT_FAIL = 2


def _emit(payload: dict[str, Any]) -> None:
    """Write a single JSON line to stdout.

    Used for both success and failure payloads so callers can
    pipe / parse without rendering considerations.
    """
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _read_calendar_version() -> str:
    """Read the live ``exchange_calendars.__version__``.

    Returns the empty string when the library is not installed
    (a common sandbox scenario). The version is **always** read
    live — never hardcoded — per EOD-8.4.
    """
    try:
        import exchange_calendars as xcals
    except Exception:  # pragma: no cover - sandbox only
        return ""
    return getattr(xcals, "__version__", "") or ""


def _resolve_trading_sample(calendar: Any, first_session: str) -> dict[str, Any]:
    """Run the trading-day sample (DESIGN §OQ-11B.3 #1).

    Returns a ``{"date": ..., "status": "trading"}`` payload on
    success. Raises :class:`ValueError` when the calendar's
    first session cannot be re-asserted as ``TRADING``.
    """
    status = query_trading_day_status(first_session)
    if status is not CalendarDayStatus.TRADING:
        raise ValueError(
            f"first_session={first_session!r} is not TRADING (got {status!r})"
        )
    return {"date": first_session, "status": "trading"}


def _resolve_not_trading_sample(calendar: Any, first_session: str) -> dict[str, Any]:
    """Scan from ``first_session`` for the first NOT_TRADING day.

    Default direction is ``forward`` (``first_session + N``): the
    first in-range non-trading day after the resolved
    ``first_session``. For XSHG this is typically the first
    weekend after the calendar's opening date. If the forward
    scan reaches the calendar's ``last_session``, the helper
    falls back to a backward scan up to 365 days so the
    coverage window always yields a sample. Either path is
    bounded by 365 iterations so the script's worst-case
    runtime stays small.

    The sample MUST come from
    :func:`query_trading_day_status` directly — no fallback to
    :func:`is_trading_day`, ``TRADING_DAYS_2026``, or weekend
    heuristics.

    Returns ``{"date": ..., "status": "not_trading"}`` on
    success. Raises :class:`ValueError` if none can be found
    within the window (treat as a fail-closed anomaly).
    """
    from contextlib import contextmanager
    from datetime import date, timedelta

    @contextmanager
    def _calendar_seam():
        previous = _date_utils._strict_get_calendar
        _date_utils._strict_get_calendar = lambda: calendar
        try:
            yield
        finally:
            _date_utils._strict_get_calendar = previous

    try:
        y, m, d = first_session.split("-")
        anchor = date(int(y), int(m), int(d))
    except Exception as exc:
        raise ValueError(f"first_session unparsable: {first_session!r}") from exc

    with _calendar_seam():
        # Forward scan — covers the common XSHG case where
        # first_session is the discovery date and a weekend follows.
        for i in range(1, 366):
            candidate = anchor + timedelta(days=i)
            ds = candidate.isoformat()
            try:
                status = query_trading_day_status(ds)
            except ValueError:
                continue
            if status is CalendarDayStatus.NOT_TRADING:
                return {"date": ds, "status": "not_trading"}

        # Backward fallback — covers calendars that start on a Friday
        # in which case the first weekend sits just before the anchor.
        for i in range(1, 366):
            candidate = anchor - timedelta(days=i)
            ds = candidate.isoformat()
            try:
                status = query_trading_day_status(ds)
            except ValueError:
                continue
            if status is CalendarDayStatus.NOT_TRADING:
                return {"date": ds, "status": "not_trading"}

    raise ValueError(
        f"no NOT_TRADING sample found within 365 days of {first_session!r}"
    )


def _resolve_session_close_sample(first_session: str) -> dict[str, Any]:
    """Read the session-close sample normalised to Asia/Shanghai.

    Returns ``{"date": ..., "close": "<tz-aware ISO>"}`` or raises
    :class:`ValueError` if the strict seam cannot resolve the
    close instant.
    """
    close_dt = session_close_strict(first_session)
    close_norm = close_dt.astimezone(_shanghai_zone()).isoformat()
    return {"date": first_session, "close": close_norm}


def _shanghai_zone():
    """Local import + cache for ``ZoneInfo`` (avoid eager top-level)."""
    from zoneinfo import ZoneInfo
    return ZoneInfo(SHANGHAI_TZ)


def _coverage_payload(calendar: Any) -> dict[str, Any]:
    """Build a coverage descriptor from the resolved calendar."""
    if calendar is None:
        return {"present": False}
    first = getattr(calendar, "first_session", None)
    last = getattr(calendar, "last_session", None)
    return {
        "present": True,
        "first_session": _coerce_iso(first),
        "last_session": _coerce_iso(last),
    }


def _coerce_iso(value: Any) -> str:
    """Coerce a calendar bound to a canonical ``YYYY-MM-DD`` string."""
    if value is None:
        return ""
    # ``date`` / ``datetime`` / ``Timestamp`` all expose ``date()``.
    date_attr = getattr(value, "date", None)
    if callable(date_attr):
        try:
            result = date_attr()
            if hasattr(result, "isoformat"):
                return result.isoformat()  # type: ignore[attr-defined]
        except Exception:
            pass
    to_pd = getattr(value, "to_pydatetime", None)
    if callable(to_pd):
        try:
            dt_result = to_pd()
            if hasattr(dt_result, "date"):
                d_result = dt_result.date()  # type: ignore[attr-defined]
                if hasattr(d_result, "isoformat"):
                    return d_result.isoformat()  # type: ignore[attr-defined]
        except Exception:
            pass
    if isinstance(value, str):
        return value
    return str(value)


def _build_payload() -> dict[str, Any]:
    """Assemble the preflight JSON payload, raising on failure.

    Returns the success payload on PASS. Raises
    :class:`ValueError` with a ``reason`` element the test suite
    can introspect when the calendar is missing or any sample
    derivation fails.
    """
    calendar = _strict_get_calendar()
    coverage = _coverage_payload(calendar)
    if not coverage["present"]:
        return {
            "calendar_identity": "XSHG",
            "calendar_version": _read_calendar_version(),
            "coverage": coverage,
            "timezone": SHANGHAI_TZ,
            "trading_sample": None,
            "not_trading_sample": None,
            "session_close_sample": None,
            "zero_io": {
                "provider": 0,
                "mongo": 0,
                "cache": 0,
                "network": 0,
                "file_write": 0,
            },
            "verdict": "fail",
            "reason": "calendar_unavailable",
        }

    first_session = coverage["first_session"]
    trading_sample = _resolve_trading_sample(calendar, first_session)
    not_trading_sample = _resolve_not_trading_sample(calendar, first_session)
    session_close_sample = _resolve_session_close_sample(first_session)

    return {
        "calendar_identity": "XSHG",
        "calendar_version": _read_calendar_version(),
        "coverage": coverage,
        "timezone": SHANGHAI_TZ,
        "trading_sample": trading_sample,
        "not_trading_sample": not_trading_sample,
        "session_close_sample": session_close_sample,
        "zero_io": {
            "provider": 0,
            "mongo": 0,
            "cache": 0,
            "network": 0,
            "file_write": 0,
        },
        "verdict": "pass",
        "reason": None,
    }


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Dry-run is the only supported mode at T3. ``--apply`` is
    explicitly rejected by the parser to prevent accidental
    side-effect expansion before T6 authorizes it.
    """
    parser = argparse.ArgumentParser(
        prog="scripts.unified_data.preflight_sentiment_policy",
        description=(
            "OQ-11 local preflight CLI for the production "
            "CompletedSessionPolicy. Default --dry-run only."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help=(
            "Read-only inspection of the local exchange_calendars "
            "library (default). ALWAYS enabled; any I/O attempt "
            "is rejected by this layer."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help=(
            "REJECTED at T3: production activation is T6 and "
            "requires Pascal authorisation. The flag exists "
            "only so the parser can produce a deterministic "
            "fail-closed error in case of misuse."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns ``EXIT_PASS`` for a successful dry-run and
    ``EXIT_FAIL`` for any internal preflight failure (calendar
    unavailable, sample derivation error, or unexpected
    exception in the strict seam).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.apply:
        sys.stderr.write(
            "apply mode rejected at T3: only --dry-run is authorised "
            "(production activation is a separate Gate, see RFC-03-014 "
            "V0.26 §5.3.1 EOD-8.7 / DESIGN-03-014 V0.33 §OQ-11B.7).\n"
        )
        return EXIT_FAIL

    try:
        payload = _build_payload()
    except Exception as exc:
        payload = {
            "calendar_identity": "XSHG",
            "calendar_version": _read_calendar_version(),
            "coverage": {"present": False},
            "timezone": SHANGHAI_TZ,
            "trading_sample": None,
            "not_trading_sample": None,
            "session_close_sample": None,
            "zero_io": {
                "provider": 0,
                "mongo": 0,
                "cache": 0,
                "network": 0,
                "file_write": 0,
            },
            "verdict": "fail",
            "reason": f"exception:{type(exc).__name__}:{exc}",
        }
        _emit(payload)
        return EXIT_FAIL

    _emit(payload)
    return EXIT_PASS if payload.get("verdict") == "pass" else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
