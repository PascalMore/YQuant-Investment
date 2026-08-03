"""Production A-share completed-session policy (OQ-11).

SPEC-03-014 V0.25 §3.3 EOD-7 / DESIGN-03-014 V0.32 §OQ-11.

This module owns the canonical definitions of the
``SessionStatus`` enum and the ``CompletedSessionPolicy`` /
``Clock`` Protocols that gate ``sentiment.market_snapshot`` /
``sentiment.limit_up_pool`` reads and refreshes. The
``AShareCompletedSessionPolicy`` adapter implements EOD-7.5's
priority-1..7 status algorithm on top of the strict
``date_utils`` seam and an injected timezone-aware ``Clock``.

Module boundary (EOD-7.2 / OQ-11.2.4):

* Does **not** import :mod:`skills.data.unified_data` — the
  adapter is infra-layer and would otherwise create a reverse
  dependency from infra → business.
* Does **not** import ``exchange_calendars`` directly — the
  calendar is reached exclusively via the strict seam in
  :mod:`skills.infra.date_utils` (``query_trading_day_status`` /
  ``session_close_strict`` / ``parse_date_strict``).
* Does **not** call ``datetime.now()`` / ``date.today()``
  implicitly. All time reads go through the injected ``Clock``;
  construction fails fast with :class:`NaiveClockError` if the
  clock is naive. The composition root is the only place a real
  system clock is permitted — and even there only after Pascal's
  Gate authorisation.
* Does **not** perform any side effect: no provider fetch, no
  writer upsert, no cache put, no Mongo / network / log / file
  write. Audit metadata is carried on the exception instances
  only.

The four-state :class:`SessionStatus` enum and the
:class:`CompletedSessionPolicy` Protocol live here as the
canonical location. ``skills.data.unified_data.services
.sentiment_service`` re-exports both names to preserve module-
level import compatibility with prior iterations (no
``sentiment_service`` caller or test has to change its
``from skills.data.unified_data.services.sentiment_service
import SessionStatus, CompletedSessionPolicy`` line).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from skills.infra.date_utils import (
    CalendarDayStatus,
    parse_date_strict,
    query_trading_day_status,
    session_close_strict,
)


# ---------------------------------------------------------------------------
# Canonical SessionStatus / CompletedSessionPolicy / Clock Protocols
# ---------------------------------------------------------------------------


class SessionStatus(Enum):
    """Canonical session-status verdict (EOD-1 / EOD-7).

    The four states are mutually exclusive and exhaustive over
    any canonical ``YYYY-MM-DD`` input the production adapter
    can answer. The values are stable public tokens; renaming or
    widening the set requires a SPEC iteration. The
    ``sentiment_service`` re-exports this enum to keep
    module-level callers compatible.
    """

    COMPLETED = "completed"
    NOT_A_TRADING_DAY = "not_a_trading_day"
    FUTURE_TRADING_DAY = "future_trading_day"
    SESSION_NOT_COMPLETED = "session_not_completed"


@runtime_checkable
class CompletedSessionPolicy(Protocol):
    """Minimal read-only protocol for EOD session validation.

    Implementations must judge whether ``date`` (canonical
    ``YYYY-MM-DD``) is a completed A-share trading session. The
    protocol is ``runtime_checkable`` so lightweight test fakes
    pass :func:`isinstance` checks. Spec EOD-2 / EOD-7.2.
    """

    def session_status(self, date: str) -> SessionStatus:
        ...


@runtime_checkable
class Clock(Protocol):
    """Timezone-aware clock seam (EOD-7.2).

    A compliant clock's ``now()`` must return a
    :class:`datetime.datetime` with non-``None`` ``tzinfo`` and a
    non-``None`` :meth:`utcoffset`. The production adapter
    probes the clock at construction time and raises
    :class:`NaiveClockError` otherwise.
    """

    def now(self) -> datetime:
        ...


# ---------------------------------------------------------------------------
# Internal error hierarchy (fail-closed carrier)
# ---------------------------------------------------------------------------


class SessionPolicyError(Exception):
    """Base class for all production-policy errors.

    The error carries a minimal, safe audit record on its
    instance — ``date`` (caller input), ``clock_source_class``
    (the ``type(clock).__name__`` so the audit can tell a real
    system clock from a fake test clock), and ``reason`` (a
    short human-readable hint). It does NOT carry full calendar
    payloads, exchange session data, or credentials (EOD-7.6).

    Subclasses map to distinct EOD-7.5 priority-1..3 failure
    modes so the service layer can pattern-match on type without
    parsing message strings.
    """

    def __init__(
        self,
        *,
        date: Optional[str] = None,
        clock_source_class: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        super().__init__(
            f"SessionPolicyError("
            f"date={date!r}, "
            f"clock_source_class={clock_source_class!r}, "
            f"reason={reason!r})"
        )
        self.date = date
        self.clock_source_class = clock_source_class
        self.reason = reason


class CalendarUnavailableError(SessionPolicyError):
    """Calendar dependency missing or query exception (EOD-7.5 priority 2).

    Raised when the strict ``date_utils`` seam reports
    :attr:`CalendarDayStatus.UNAVAILABLE` (no calendar in the
    environment) or :attr:`CalendarDayStatus.ERROR` (calendar
    present but the query raised). The service layer maps this
    to :class:`ProviderUnavailableError`.
    """


class DateOutOfRangeError(SessionPolicyError):
    """Date outside calendar coverage (EOD-7.5 priority 2).

    Raised when the strict ``date_utils`` seam reports
    :attr:`CalendarDayStatus.OUT_OF_RANGE`. The service layer
    maps this to :class:`ProviderUnavailableError`.
    """


class NaiveClockError(SessionPolicyError):
    """Injected clock returned a naive datetime (EOD-7.5 priority 3).

    Raised at construction time, before any
    :meth:`AShareCompletedSessionPolicy.session_status` call
    can run. The production adapter refuses to spin up if the
    clock cannot express time-zone-aware time.
    """


class InvalidDateFormatError(SessionPolicyError):
    """Non-canonical ``YYYY-MM-DD`` input reached the adapter (EOD-7.3).

    The service layer is the canonical owner of the format
    check and rejects bad input before consulting the adapter,
    so this error is normally unreachable from production code
    paths. It is kept as a defensive guard for direct callers
    (e.g. a future composition root or a unit test) — the
    adapter must never silently fall back to the loose
    :func:`parse_date` parser.
    """


# ---------------------------------------------------------------------------
# Production adapter
# ---------------------------------------------------------------------------


class AShareCompletedSessionPolicy:
    """Production A-share completed-session policy (EOD-7.5).

    Implements the seven-priority status algorithm on top of the
    strict :mod:`skills.infra.date_utils` seam and an injected
    timezone-aware :class:`Clock`. The adapter is the canonical
    realisation of the production ``CompletedSessionPolicy``
    that ``MarketSentimentService`` will eventually receive from
    a future composition root (this task does **not** wire that
    root — the default :class:`MarketSentimentService` still
    ships with ``completed_session_policy=None``).

    Construction contract:

    * ``clock`` is mandatory and probed at construction time;
      a naive clock raises :class:`NaiveClockError` immediately.
    * ``cutoff_grace`` defaults to ``timedelta(0)`` (close
      arrival = completed). It is an independent, configurable,
      auditable policy parameter carried in audit metadata as
      ``cutoff_policy_id``; this task does not create a config
      file or change the value via env / YAML.
    * ``timezone`` defaults to ``ZoneInfo("Asia/Shanghai")``
      (the current XSHG calendar tz). All comparisons are
      normalised to this zone before evaluation.
    * ``audit_logger`` defaults to ``None`` (no audit write).
      When supplied it is expected to expose
      ``.info(event: str, **fields)`` and is invoked at most
      once per ``session_status`` call; this task does not
      provide a concrete logger implementation.

    Side-effect contract (EOD-7.7 / OQ-11.4.3):

    * 0 provider fetch / 0 writer upsert / 0 cache put.
    * 0 Mongo / 0 network / 0 file write / 0 log write (unless
      an ``audit_logger`` is explicitly injected).
    * 0 implicit ``datetime.now()`` / ``date.today()`` reads —
      the clock is the only time source.
    """

    def __init__(
        self,
        clock: Clock,
        *,
        cutoff_grace: timedelta = timedelta(0),
        timezone: ZoneInfo = ZoneInfo("Asia/Shanghai"),
        audit_logger: Any | None = None,
    ) -> None:
        # Validate the clock up front (EOD-7.5 priority 3 — fail-fast).
        if clock is None:
            raise NaiveClockError(
                date=None,
                clock_source_class=None,
                reason="clock is required",
            )
        try:
            sample = clock.now()
        except Exception as exc:  # pragma: no cover - defensive
            raise NaiveClockError(
                date=None,
                clock_source_class=type(clock).__name__,
                reason=f"clock.now() raised {type(exc).__name__}: {exc}",
            ) from exc
        if not isinstance(sample, datetime):
            raise NaiveClockError(
                date=None,
                clock_source_class=type(clock).__name__,
                reason=f"clock.now() must return datetime; got {type(sample).__name__}",
            )
        if sample.tzinfo is None or sample.utcoffset() is None:
            raise NaiveClockError(
                date=None,
                clock_source_class=type(clock).__name__,
                reason="clock.now() must be timezone-aware (tzinfo is None)",
            )
        self._clock: Clock = clock
        self._cutoff_grace: timedelta = cutoff_grace
        self._timezone: ZoneInfo = timezone
        self._audit_logger = audit_logger
        self._clock_source_class: str = type(clock).__name__

    # ------------------------------------------------------------------
    # Public API — the only method on CompletedSessionPolicy
    # ------------------------------------------------------------------

    def session_status(self, date: str) -> SessionStatus:
        """Return the canonical SessionStatus verdict for ``date``.

        Strict seven-priority algorithm (EOD-7.5):
        1. Non-canonical input → :class:`InvalidDateFormatError`.
        2. Calendar unavailable / out-of-range / exception →
           :class:`CalendarUnavailableError` or
           :class:`DateOutOfRangeError` (fail-closed; never folds
           to ``NOT_A_TRADING_DAY`` and never falls back to the
           hardcoded ``TRADING_DAYS_2026`` / weekend rules).
        3. Naive clock → caught at construction (here we only
           re-validate if a future refactor moves the check
           out of ``__init__``).
        4. Calendar says non-trading day →
           :attr:`SessionStatus.NOT_A_TRADING_DAY`.
        5. Future trading day →
           :attr:`SessionStatus.FUTURE_TRADING_DAY`.
        6. Today and earlier than close + grace →
           :attr:`SessionStatus.SESSION_NOT_COMPLETED`.
        7. Today and at/after close + grace, **or** any
           historical trading day →
           :attr:`SessionStatus.COMPLETED`.

        Returns:
            One of the four :class:`SessionStatus` values.

        Raises:
            InvalidDateFormatError: ``date`` is not a canonical
                ``YYYY-MM-DD`` string.
            CalendarUnavailableError: The strict seam reports
                ``UNAVAILABLE`` or ``ERROR``.
            DateOutOfRangeError: The strict seam reports
                ``OUT_OF_RANGE``.
        """
        # Priority 1 — format check.
        try:
            parsed = parse_date_strict(date)
        except ValueError as exc:
            raise InvalidDateFormatError(
                date=date,
                clock_source_class=self._clock_source_class,
                reason=str(exc),
            ) from exc

        # Priority 2 — calendar status (strict seam, no fallbacks).
        try:
            status = query_trading_day_status(date)
        except ValueError as exc:
            # The strict seam raises ValueError on non-canonical
            # input. We already passed the format gate above, so
            # this branch is defensive only.
            raise InvalidDateFormatError(
                date=date,
                clock_source_class=self._clock_source_class,
                reason=str(exc),
            ) from exc

        if status is CalendarDayStatus.UNAVAILABLE:
            self._audit(event="session_status_unavailable", date=date, status=None)
            raise CalendarUnavailableError(
                date=date,
                clock_source_class=self._clock_source_class,
                reason=CalendarDayStatus.UNAVAILABLE.value,
            )
        if status is CalendarDayStatus.ERROR:
            self._audit(event="session_status_error", date=date, status=None)
            raise CalendarUnavailableError(
                date=date,
                clock_source_class=self._clock_source_class,
                reason=CalendarDayStatus.ERROR.value,
            )
        if status is CalendarDayStatus.OUT_OF_RANGE:
            self._audit(event="session_status_out_of_range", date=date, status=None)
            raise DateOutOfRangeError(
                date=date,
                clock_source_class=self._clock_source_class,
                reason=CalendarDayStatus.OUT_OF_RANGE.value,
            )

        # Priority 3 — the constructor already rejected naive
        # clocks. We re-derive the source class from the clock
        # type to keep the audit field accurate even after a
        # potential future clock swap (defensive: the constructor
        # stores the original class, so this is mostly a
        # consistency check).
        now = self._clock.now()
        if now.tzinfo is None or now.utcoffset() is None:  # pragma: no cover
            raise NaiveClockError(
                date=date,
                clock_source_class=self._clock_source_class,
                reason="clock returned naive datetime at query time",
            )
        now_local = now.astimezone(self._timezone)
        today = now_local.date()

        # Priority 4 — calendar says non-trading day.
        if status is CalendarDayStatus.NOT_TRADING:
            verdict = SessionStatus.NOT_A_TRADING_DAY
            self._audit(event="session_status", date=date, status=verdict.value)
            return verdict

        # Priority 5 — future trading day.
        if parsed > today:
            verdict = SessionStatus.FUTURE_TRADING_DAY
            self._audit(event="session_status", date=date, status=verdict.value)
            return verdict

        # Priorities 6 & 7 — current day boundary check.
        try:
            close_local = session_close_strict(date).astimezone(self._timezone)
        except ValueError as exc:
            # The status gate above already guaranteed the date
            # is in range and the calendar query succeeded for
            # ``is_session``; if ``session_close`` now fails
            # the seam is inconsistent — fail-closed as
            # CalendarUnavailableError.
            self._audit(
                event="session_status_close_query_failed",
                date=date,
                status=None,
            )
            raise CalendarUnavailableError(
                date=date,
                clock_source_class=self._clock_source_class,
                reason=f"session_close_strict failed: {exc}",
            ) from exc
        if parsed == today and now_local < (close_local + self._cutoff_grace):
            verdict = SessionStatus.SESSION_NOT_COMPLETED
            self._audit(event="session_status", date=date, status=verdict.value)
            return verdict

        # Priority 7 — historical trading day or today after close.
        verdict = SessionStatus.COMPLETED
        self._audit(event="session_status", date=date, status=verdict.value)
        return verdict

    # ------------------------------------------------------------------
    # Internal audit hook — never raises, never writes to disk
    # ------------------------------------------------------------------

    def _audit(
        self,
        *,
        event: str,
        date: Optional[str],
        status: Optional[str],
    ) -> None:
        """Record a single audit event.

        Default behaviour is a no-op: ``audit_logger=None`` is
        the offline default and the production composition
        root is the only place that injects a real logger. The
        hook swallows ``AttributeError`` / ``TypeError`` so a
        misbehaving logger cannot block the status verdict.
        No log / file / DB / network writes happen here when
        the logger is the default ``None``.
        """
        if self._audit_logger is None:
            return
        try:
            self._audit_logger.info(
                event,
                calendar_identity="XSHG",
                timezone=str(self._timezone),
                cutoff_policy_id=(
                    f"OQ11-grace{int(self._cutoff_grace.total_seconds())}"
                ),
                date=date,
                clock_source_class=self._clock_source_class,
                status=status,
                error_reason=None,
            )
        except Exception:
            # Audit is best-effort and must never block the
            # verdict. The exception is intentionally swallowed.
            return


__all__ = [
    "SessionStatus",
    "CompletedSessionPolicy",
    "Clock",
    "SessionPolicyError",
    "CalendarUnavailableError",
    "DateOutOfRangeError",
    "NaiveClockError",
    "InvalidDateFormatError",
    "AShareCompletedSessionPolicy",
]
