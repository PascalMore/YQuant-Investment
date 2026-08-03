# skills/infra/date_utils.py
"""Date utility functions."""

from datetime import date, datetime, timedelta
from enum import Enum
from typing import List, Optional

try:
    import exchange_calendars as xcals
except ImportError:  # pragma: no cover - fallback path for minimal envs
    xcals = None


# Chinese stock trading days (2026) - basic implementation
# In production, this should be loaded from a config or external calendar
TRADING_DAYS_2026 = set([
    # January 2026
    '2026-01-02', '2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08',
    '2026-01-09', '2026-01-12', '2026-01-13', '2026-01-14', '2026-01-15',
    '2026-01-16', '2026-01-19', '2026-01-20', '2026-01-21', '2026-01-22',
    '2026-01-23', '2026-01-26', '2026-01-27', '2026-01-28', '2026-01-29', '2026-01-30',
    # February 2026
    '2026-02-02', '2026-02-03', '2026-02-04', '2026-02-05', '2026-02-06',
    '2026-02-09', '2026-02-10', '2026-02-11', '2026-02-12', '2026-02-13',
    '2026-02-16', '2026-02-17', '2026-02-18', '2026-02-19', '2026-02-20',
    '2026-02-23', '2026-02-24', '2026-02-25', '2026-02-26', '2026-02-27',
    # March 2026
    '2026-03-02', '2026-03-03', '2026-03-04', '2026-03-05', '2026-03-06',
    '2026-03-09', '2026-03-10', '2026-03-11', '2026-03-12', '2026-03-13',
    '2026-03-16', '2026-03-17', '2026-03-18', '2026-03-19', '2026-03-20',
    '2026-03-23', '2026-03-24', '2026-03-25', '2026-03-26', '2026-03-27', '2026-03-30', '2026-03-31',
    # April 2026
    '2026-04-01', '2026-04-02', '2026-04-03', '2026-04-07', '2026-04-08',
    '2026-04-09', '2026-04-10', '2026-04-13', '2026-04-14', '2026-04-15',
    '2026-04-16', '2026-04-17', '2026-04-20', '2026-04-21', '2026-04-22',
    '2026-04-23', '2026-04-24', '2026-04-27', '2026-04-28', '2026-04-29', '2026-04-30',
    # May 2026
    '2026-05-04', '2026-05-05', '2026-05-06', '2026-05-07', '2026-05-08',
    '2026-05-11', '2026-05-12', '2026-05-13', '2026-05-14', '2026-05-15',
    '2026-05-18', '2026-05-19', '2026-05-20', '2026-05-21', '2026-05-22',
    '2026-05-25', '2026-05-26', '2026-05-27', '2026-05-28', '2026-05-29',
    # June 2026 (2026-06-19 Dragon Boat Festival market holiday)
    '2026-06-01', '2026-06-02', '2026-06-03', '2026-06-04', '2026-06-05',
    '2026-06-08', '2026-06-09', '2026-06-10', '2026-06-11', '2026-06-12',
    '2026-06-15', '2026-06-16', '2026-06-17', '2026-06-18',
    '2026-06-22', '2026-06-23', '2026-06-24', '2026-06-25', '2026-06-26',
    '2026-06-29', '2026-06-30',
])

_CN_CALENDAR = None


def _get_cn_calendar():
    """Return the A-share exchange calendar when exchange_calendars is available."""
    global _CN_CALENDAR
    if xcals is None:
        return None
    if _CN_CALENDAR is None:
        _CN_CALENDAR = xcals.get_calendar('XSHG')
    return _CN_CALENDAR


def _calendar_is_trading_day(d: str) -> Optional[bool]:
    """Check XSHG calendar, returning None when the dynamic calendar cannot answer."""
    calendar = _get_cn_calendar()
    if calendar is None:
        return None
    try:
        return bool(calendar.is_session(d))
    except Exception:
        return None


def is_trading_day(d: str) -> bool:
    """Check if a date is a trading day.
    
    Args:
        d: Date string in YYYY-MM-DD format
    
    Returns:
        bool: True if trading day, False otherwise
    """
    calendar_result = _calendar_is_trading_day(d)
    if calendar_result is not None:
        return calendar_result
    return d in TRADING_DAYS_2026


def get_latest_trading_day(d: str) -> str:
    """Get the latest trading day on or before the given date.
    
    Args:
        d: Date string in YYYY-MM-DD format
    
    Returns:
        str: Latest trading day (YYYY-MM-DD)
    """
    if is_trading_day(d):
        return d
    
    # Search backwards
    dt = parse_date(d)
    for i in range(1, 10):
        check_date = dt - timedelta(days=i)
        check_str = format_date(check_date)
        if is_trading_day(check_str):
            return check_str
    
    return d  # fallback


def get_next_trading_day(d: str) -> str:
    """Get the next trading day after the given date.
    
    Args:
        d: Date string in YYYY-MM-DD format
    
    Returns:
        str: Next trading day (YYYY-MM-DD)
    """
    dt = parse_date(d)
    for i in range(1, 10):
        check_date = dt + timedelta(days=i)
        check_str = format_date(check_date)
        if is_trading_day(check_str):
            return check_str
    
    return d  # fallback


def get_trading_dates(start: str, end: str) -> List[str]:
    """Get list of trading days between start and end dates (inclusive).
    
    Args:
        start: Start date in YYYY-MM-DD format
        end: End date in YYYY-MM-DD format
    
    Returns:
        List[str]: List of trading days
    """
    start_dt = parse_date(start)
    end_dt = parse_date(end)

    calendar = _get_cn_calendar()
    if calendar is not None:
        try:
            sessions = calendar.sessions_in_range(start_dt, end_dt)
            return [format_date(session.date()) for session in sessions]
        except Exception:
            pass
    
    dates = []
    current = start_dt
    while current <= end_dt:
        current_str = format_date(current)
        if is_trading_day(current_str):
            dates.append(current_str)
        current += timedelta(days=1)
    
    return dates


def parse_date(d: str) -> date:
    """Parse date string to date object.
    
    Args:
        d: Date string (supports YYYY-MM-DD, YYYYMMDD, etc.)
    
    Returns:
        date: Parsed date object
    """
    # Handle YYYYMMDD format
    d = d.replace('-', '')
    return datetime.strptime(d, '%Y%m%d').date()


def format_date(d: date, fmt: str = '%Y-%m-%d') -> str:
    """Format date object to string.

    Args:
        d: Date object
        fmt: Format string, default '%Y-%m-%d'

    Returns:
        str: Formatted date string
    """
    return d.strftime(fmt)


# ---------------------------------------------------------------------------
# Strict seam — OQ-11 / SPEC-03-014 V0.25 EOD-7 (production adapter only)
# ---------------------------------------------------------------------------
#
# The block below is the **strict query seam** for the production
# ``AShareCompletedSessionPolicy`` adapter (skills/infra/session_policy.py).
# It is independent from the six existing public APIs above: those keep
# the legacy behaviour (``is_trading_day`` still falls back to
# ``TRADING_DAYS_2026`` on calendar failure, ``parse_date`` still
# accepts the loose ``YYYYMMDD`` shape). The strict seam never falls
# back, never folds ``None``/``bool``, and never returns "best-effort"
# guesses — it surfaces the five-state calendar verdict, raises
# ``ValueError`` on non-canonical input, and propagates calendar
# unavailability / out-of-range / query exception as fail-closed
# exceptions so the adapter can map them to its internal error
# hierarchy.
#
# Rules (SPEC EOD-7.1 / EOD-7.2 / EOD-7.3):
#
# * Only canonical ``YYYY-MM-DD`` strings are accepted by the strict
#   seam; non-canonical input raises ``ValueError`` immediately and
#   never touches the calendar or the legacy ``parse_date`` parser.
# * The calendar's first/last session define the covered range;
#   dates outside that range return ``CalendarDayStatus.OUT_OF_RANGE``
#   (NOT ``False``, NOT ``None``).
# * Calendar query exceptions map to ``CalendarDayStatus.ERROR``;
#   missing ``exchange_calendars`` / ``get_calendar`` failures map to
#   ``CalendarDayStatus.UNAVAILABLE``.
# * ``session_close_strict`` returns the calendar's native tz-aware
#   close instant. The adapter is responsible for normalising the
#   time zone — the seam must never hardcode 15:00 or assume
#   Shanghai local time.
# * The strict seam must not be reached by the legacy public APIs
#   (``is_trading_day`` / ``get_latest_trading_day`` etc.); the
#   production adapter is the only intended caller.


class CalendarDayStatus(Enum):
    """A-share calendar day status — five-state discriminator.

    SPEC-03-014 V0.25 EOD-7.2. The five states are mutually
    exclusive and exhaustive over any canonical ``YYYY-MM-DD`` input
    passed to :func:`query_trading_day_status`. ``bool`` /
    ``None`` folding is forbidden — production policy code must
    pattern-match on the enum and only the enum.
    """

    TRADING = "trading"            # calendar explicitly says trading day
    NOT_TRADING = "not_trading"    # calendar explicitly says non-trading day
    UNAVAILABLE = "unavailable"    # calendar dependency missing / get_calendar failed
    OUT_OF_RANGE = "out_of_range"  # date outside calendar coverage window
    ERROR = "error"                # calendar query raised an exception


def _strict_parse_canonical(d: object) -> date:
    """Validate a canonical ``YYYY-MM-DD`` string; raise on failure.

    Internal helper for the strict seam. ``parse_date_strict`` and
    :func:`query_trading_day_status` / :func:`session_close_strict`
    all share this gate. ``ValueError`` is the only failure mode
    (consistent with EOD-7.3's "non-canonical → format error"
    contract — the adapter translates to its own
    :class:`InvalidDateFormatError` if reached, but the service
    layer is the canonical owner and rejects bad input before the
    adapter is consulted).
    """
    if not isinstance(d, str):
        raise ValueError(
            "strict seam requires a canonical YYYY-MM-DD string; "
            f"got non-string {type(d).__name__}"
        )
    import re

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        raise ValueError(
            "strict seam requires a canonical YYYY-MM-DD string; "
            f"got {d!r}"
        )
    # Re-use the existing ``datetime.strptime`` path to validate
    # calendar arithmetic (e.g. 2026-02-30 is regex-valid but
    # date-invalid). We do NOT fall back to ``parse_date`` — the
    # goal is to reject anything that isn't strict-canonical.
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(
            "strict seam requires a canonical YYYY-MM-DD string; "
            f"got {d!r} ({exc})"
        ) from exc


def _strict_get_calendar():
    """Resolve the XSHG calendar or return ``None`` for UNAVAILABLE.

    Returns ``None`` when ``exchange_calendars`` is missing or the
    first ``get_calendar`` call fails. The caller is responsible
    for mapping the ``None`` to :attr:`CalendarDayStatus.UNAVAILABLE`.
    """
    if xcals is None:
        return None
    try:
        return xcals.get_calendar("XSHG")
    except Exception:
        return None


def _strict_date_in_calendar_bounds(d_iso: str, calendar) -> bool:
    """Return ``True`` iff ``d_iso`` is within the calendar's coverage.

    Uses the calendar's ``first_session`` / ``last_session``
    attributes to bound the covered range. Dates that fall outside
    this window are flagged as
    :attr:`CalendarDayStatus.OUT_OF_RANGE` and the adapter maps to
    :class:`DateOutOfRangeError` (fail-closed). The check is
    inclusive on both ends.

    ``first_session`` / ``last_session`` may be returned as a
    ``datetime`` / ``Timestamp`` / ``date`` / ``str`` depending on
    the ``exchange_calendars`` version; the helper coerces to a
    :class:`datetime.date` for the comparison. ``str`` values are
    treated as canonical ``YYYY-MM-DD`` (the calendar docs
    guarantee this shape for the bound attributes).
    """
    try:
        first = calendar.first_session
        last = calendar.last_session
    except Exception:
        return False
    if first is None or last is None:
        return False

    def _coerce(value):
        if hasattr(value, "date") and callable(value.date):
            return value.date()
        if hasattr(value, "to_pydatetime"):
            return value.to_pydatetime().date()
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        if isinstance(value, date):
            return value
        return None

    try:
        first_date = _coerce(first)
        last_date = _coerce(last)
        target = datetime.strptime(d_iso, "%Y-%m-%d").date()
    except Exception:
        return False
    if first_date is None or last_date is None:
        return False
    return first_date <= target <= last_date


def query_trading_day_status(d: str) -> CalendarDayStatus:
    """Strict five-state trading-day verdict for the production adapter.

    SPEC-03-014 V0.25 EOD-7.2 / DESIGN-03-014 V0.32 OQ-11.2.2.

    Args:
        d: Canonical ``YYYY-MM-DD`` string. Non-canonical input
            raises :class:`ValueError` immediately — the strict
            seam never falls back to the loose ``parse_date``
            parser.

    Returns:
        One of the five :class:`CalendarDayStatus` values. The
        function NEVER returns ``None`` and NEVER folds to ``bool``.

    Raises:
        ValueError: ``d`` is not a canonical ``YYYY-MM-DD`` string.
    """
    d_iso = _strict_parse_canonical(d).isoformat()
    calendar = _strict_get_calendar()
    if calendar is None:
        return CalendarDayStatus.UNAVAILABLE
    if not _strict_date_in_calendar_bounds(d_iso, calendar):
        return CalendarDayStatus.OUT_OF_RANGE
    try:
        is_trading = bool(calendar.is_session(d_iso))
    except Exception:
        return CalendarDayStatus.ERROR
    return (
        CalendarDayStatus.TRADING
        if is_trading
        else CalendarDayStatus.NOT_TRADING
    )


def session_close_strict(d: str) -> datetime:
    """Strict tz-aware close instant for the production adapter.

    SPEC-03-014 V0.25 EOD-7.2 / DESIGN-03-014 V0.32 OQ-11.2.2.

    Args:
        d: Canonical ``YYYY-MM-DD`` string. Non-canonical input
            raises :class:`ValueError` immediately.

    Returns:
        The calendar's native session-close instant for ``d`` as
        a :class:`datetime.datetime` with non-``None`` ``tzinfo``
        (the production adapter is responsible for normalising to
        Shanghai local time before comparison). The seam never
        substitutes a hardcoded ``15:00`` value.

    Raises:
        ValueError: ``d`` is not a canonical ``YYYY-MM-DD`` string,
            the calendar is unavailable, the date is out of
            range, or the calendar query raised. All four
            failure modes share ``ValueError`` to keep the seam
            minimal — the adapter maps to its own internal
            error hierarchy
            (:class:`InvalidDateFormatError` /
            :class:`CalendarUnavailableError` /
            :class:`DateOutOfRangeError`).
    """
    d_iso = _strict_parse_canonical(d).isoformat()
    calendar = _strict_get_calendar()
    if calendar is None:
        raise ValueError(
            f"calendar unavailable for strict close query on {d_iso!r}"
        )
    if not _strict_date_in_calendar_bounds(d_iso, calendar):
        raise ValueError(
            f"date {d_iso!r} is out of calendar range for strict close query"
        )
    try:
        close = calendar.session_close(d_iso)
    except Exception as exc:
        raise ValueError(
            f"calendar query raised on strict close query for {d_iso!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    # ``session_close`` may return pandas.Timestamp / numpy.datetime64
    # depending on the exchange_calendars version; coerce to a stdlib
    # ``datetime`` with tzinfo preserved. The seam must not assume the
    # return type — only that ``tzinfo`` is set.
    if hasattr(close, "to_pydatetime"):
        close = close.to_pydatetime()
    elif hasattr(close, "astype"):
        # numpy.datetime64 fallback
        import pandas as pd  # local import — only used in fallback path
        close = pd.Timestamp(close).to_pydatetime()
    if not isinstance(close, datetime):
        raise ValueError(
            f"calendar returned non-datetime close for {d_iso!r}: "
            f"{type(close).__name__}"
        )
    if close.tzinfo is None or close.utcoffset() is None:
        raise ValueError(
            f"calendar returned naive close instant for {d_iso!r}; "
            "strict seam requires a timezone-aware datetime"
        )
    return close


def parse_date_strict(d: str) -> date:
    """Strict canonical-date parser for the production adapter.

    SPEC-03-014 V0.25 EOD-7.3 / DESIGN-03-014 V0.32 OQ-11.2.2.

    Accepts only canonical ``YYYY-MM-DD`` strings. Non-canonical
    input (including ``"YYYYMMDD"``, ``datetime`` objects, anything
    with a time component, or invalid calendar dates such as
    ``2026-02-30``) raises :class:`ValueError`. The legacy
    :func:`parse_date` loose parser is intentionally not called
    here — the production seam must reject non-canonical input
    at the front gate, not absorb it.

    Args:
        d: Canonical ``YYYY-MM-DD`` string.

    Returns:
        :class:`datetime.date` instance for the parsed value.

    Raises:
        ValueError: ``d`` is not a canonical ``YYYY-MM-DD`` string
            or the calendar date is invalid.
    """
    return _strict_parse_canonical(d)
