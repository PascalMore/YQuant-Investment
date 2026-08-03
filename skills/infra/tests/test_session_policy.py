"""AShareCompletedSessionPolicy tests (OQ-11 / SPEC-03-014 V0.25 EOD-7).

DESIGN-03-014 V0.32 §OQ-11.5.2 test matrix — fake calendar + fake
timezone-aware clock. The matrix covers the seven-priority
algorithm exhaustively:

  1. invalid canonical date   → ``InvalidDateFormatError``
  2. unavailable / out-of-range / error → ``CalendarUnavailableError``
                                          or ``DateOutOfRangeError``
  3. naive clock              → ``NaiveClockError`` at construction
  4. NOT_TRADING              → ``SessionStatus.NOT_A_TRADING_DAY``
  5. future trading day       → ``SessionStatus.FUTURE_TRADING_DAY``
  6. today pre-close          → ``SessionStatus.SESSION_NOT_COMPLETED``
  7. today post-close / hist. → ``SessionStatus.COMPLETED``
  + cutoff_grace boundary
  + zero I/O (no provider / writer / cache / Mongo / network)
  + canonical export surface

The tests use a tiny in-test fake calendar that is **swapped in via
monkeypatch** so the real ``exchange_calendars`` XSHG calendar is
never consulted. This keeps the suite fast, deterministic, and
fully offline — no real Provider / Mongo / network / system
clock is touched.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

from skills.infra.session_policy import (
    AShareCompletedSessionPolicy,
    CalendarUnavailableError,
    Clock,
    CompletedSessionPolicy,
    DateOutOfRangeError,
    InvalidDateFormatError,
    NaiveClockError,
    SessionPolicyError,
    SessionStatus,
)


# ---------------------------------------------------------------------------
# Fakes — fake calendar + fake clock
# ---------------------------------------------------------------------------


class FakeCalendar:
    """In-test XSHG stand-in. Mirrors the surface
    :class:`skills.infra.date_utils.query_trading_day_status` /
    :func:`session_close_strict` actually call.

    The fake is configured per-test via the constructor; tests
    that need exception behaviour flip ``is_session_exc`` or
    ``session_close_exc`` and the seam returns the
    CalendarDayStatus.ERROR / CalendarUnavailableError variant.
    """

    def __init__(
        self,
        *,
        trading_days: set[str] | None = None,
        non_trading_days: set[str] | None = None,
        first_session: str = "2024-01-02",
        last_session: str = "2026-12-31",
        close_map: dict[str, datetime] | None = None,
        is_session_exc: bool = False,
        session_close_exc: bool = False,
    ) -> None:
        self._trading = set(trading_days or set())
        self._non_trading = set(non_trading_days or set())
        self.first_session = first_session
        self.last_session = last_session
        self._close_map = dict(close_map or {})
        self._is_session_exc = is_session_exc
        self._session_close_exc = session_close_exc
        # Track calls for zero-I/O assertions / spy use.
        self.is_session_calls: list[str] = []
        self.session_close_calls: list[str] = []

    def is_session(self, d: str) -> bool:
        self.is_session_calls.append(d)
        if self._is_session_exc:
            raise RuntimeError("simulated calendar failure")
        if d in self._trading:
            return True
        if d in self._non_trading:
            return False
        # default: NOT_TRADING (i.e. weekday-like non-trading days)
        return False

    def session_close(self, d: str) -> datetime:
        self.session_close_calls.append(d)
        if self._session_close_exc:
            raise RuntimeError("simulated calendar close failure")
        return self._close_map[d]


class FakeAwareClock:
    """A clock that returns a fixed tz-aware datetime.

    Implements the :class:`Clock` protocol. The ``now()`` is
    deterministic so each test can pin a precise Shanghai
    instant.
    """

    def __init__(self, when: datetime) -> None:
        self._when = when
        self.call_count = 0

    def now(self) -> datetime:
        self.call_count += 1
        return self._when


class FakeNaiveClock:
    """Returns a naive datetime — used to exercise the
    construction-time ``NaiveClockError`` branch (EOD-7.5 priority 3).
    """

    def now(self) -> datetime:
        return datetime(2026, 6, 1, 14, 0, 0)


# ---------------------------------------------------------------------------
# Helpers — fixtures / builders
# ---------------------------------------------------------------------------


SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")


def _shanghai(yyyymmdd: str, hh: int = 0, mm: int = 0) -> datetime:
    y, m, d = yyyymmdd.split("-")
    return datetime(int(y), int(m), int(d), hh, mm, tzinfo=SHANGHAI)


def _utc(yyyymmdd: str, hh: int = 0, mm: int = 0) -> datetime:
    y, m, d = yyyymmdd.split("-")
    return datetime(int(y), int(m), int(d), hh, mm, tzinfo=UTC)


@pytest.fixture
def patch_calendar(monkeypatch):
    """Install a per-test :class:`FakeCalendar` for the
    ``_strict_get_calendar`` seam so neither
    :func:`query_trading_day_status` nor :func:`session_close_strict`
    ever consults the real XSHG calendar.
    """
    import skills.infra.date_utils as du

    holder: dict[str, Any] = {"calendar": None}

    def _factory():
        return holder["calendar"]

    monkeypatch.setattr(du, "_strict_get_calendar", _factory)
    return holder


def _install_calendar(
    patch_calendar,
    *,
    trading_days: set[str] | None = None,
    non_trading_days: set[str] | None = None,
    close_at: dict[str, datetime] | None = None,
    first_session: str = "2024-01-02",
    last_session: str = "2026-12-31",
    is_session_exc: bool = False,
    session_close_exc: bool = False,
) -> FakeCalendar:
    fake = FakeCalendar(
        trading_days=trading_days or set(),
        non_trading_days=non_trading_days or set(),
        close_map=close_at or {},
        first_session=first_session,
        last_session=last_session,
        is_session_exc=is_session_exc,
        session_close_exc=session_close_exc,
    )
    patch_calendar["calendar"] = fake
    return fake


# Common close map: every configured day closes at 15:00 Shanghai
# (= 07:00 UTC, matching the real XSHG calendar offset).
def _close_at(days: list[str]) -> dict[str, datetime]:
    return {d: _shanghai(d, 15, 0) for d in days}


# ---------------------------------------------------------------------------
# Construction-time tests
# ---------------------------------------------------------------------------


class TestAShareCompletedSessionPolicyConstruction:
    """Naive clock / no clock / type errors at construction time."""

    def test_naive_clock_raises_naive_clock_error(self) -> None:
        with pytest.raises(NaiveClockError) as excinfo:
            AShareCompletedSessionPolicy(clock=FakeNaiveClock())  # type: ignore[arg-type]
        assert excinfo.value.clock_source_class == "FakeNaiveClock"
        assert "timezone-aware" in (excinfo.value.reason or "")

    def test_none_clock_raises_naive_clock_error(self) -> None:
        with pytest.raises(NaiveClockError) as excinfo:
            AShareCompletedSessionPolicy(clock=None)  # type: ignore[arg-type]
        assert "clock is required" in (excinfo.value.reason or "")

    def test_clock_returning_non_datetime_raises_naive_clock_error(self) -> None:
        class BadClock:
            def now(self):
                return "not-a-datetime"

        with pytest.raises(NaiveClockError) as excinfo:
            AShareCompletedSessionPolicy(clock=BadClock())  # type: ignore[arg-type]
        assert "must return datetime" in (excinfo.value.reason or "")

    def test_clock_returning_naive_with_utcoffset_raises(self) -> None:
        """A datetime with ``tzinfo`` set to a value that returns
        ``None`` from ``utcoffset()`` is still considered naive by
        the seam (EOD-7.2)."""
        class _NaiveTz:
            def utcoffset(self, dt):  # noqa: ANN001
                return None
            def dst(self, dt):  # noqa: ANN001
                return None
            def tzname(self, dt):  # noqa: ANN001
                return None

        class _FakeTzClock:
            def now(self):
                return datetime(2026, 6, 1, 14, 0, tzinfo=_NaiveTz())

        with pytest.raises(NaiveClockError):
            AShareCompletedSessionPolicy(clock=_FakeTzClock())  # type: ignore[arg-type]

    def test_clock_returning_invalid_datetime_is_handled(self) -> None:
        """If ``clock.now()`` itself raises, the constructor
        still raises :class:`NaiveClockError` (defensive guard
        — the audit metadata captures the underlying exception)."""

        class _RaisingClock:
            def now(self):
                raise RuntimeError("boom")

        with pytest.raises(NaiveClockError) as excinfo:
            AShareCompletedSessionPolicy(clock=_RaisingClock())  # type: ignore[arg-type]
        assert "boom" in (excinfo.value.reason or "")

    def test_aware_clock_constructs_cleanly(self) -> None:
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        assert policy is not None

    def test_default_cutoff_grace_is_zero(self, patch_calendar) -> None:
        """The default ``cutoff_grace`` is ``timedelta(0)`` so the
        close instant is the boundary (EOD-7.5 priority 6 default)."""
        clock = FakeAwareClock(_shanghai("2026-06-01", 14, 59))
        policy = AShareCompletedSessionPolicy(clock=clock)
        # Just under the close → SESSION_NOT_COMPLETED at default grace=0
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.SESSION_NOT_COMPLETED
        )

    def test_isinstance_completed_session_policy(self) -> None:
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        assert isinstance(policy, CompletedSessionPolicy)


# ---------------------------------------------------------------------------
# Priority 1 — InvalidDateFormatError
# ---------------------------------------------------------------------------


class TestASharePolicyInvalidFormat:
    """Priority 1: invalid canonical input."""

    def test_non_canonical_raises_invalid_format(self, patch_calendar) -> None:
        _install_calendar(patch_calendar)
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        with pytest.raises(InvalidDateFormatError) as excinfo:
            policy.session_status("20260601")
        assert excinfo.value.date == "20260601"

    def test_date_with_time_raises_invalid_format(self, patch_calendar) -> None:
        _install_calendar(patch_calendar)
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        with pytest.raises(InvalidDateFormatError):
            policy.session_status("2026-06-01 09:30:00")

    def test_invalid_calendar_date_raises_invalid_format(self, patch_calendar) -> None:
        """``2026-02-30`` is regex-canonical but date-invalid; the
        strict seam rejects it as format error (EOD-7.3)."""
        _install_calendar(patch_calendar)
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        with pytest.raises(InvalidDateFormatError):
            policy.session_status("2026-02-30")

    def test_non_string_raises_invalid_format(self, patch_calendar) -> None:
        _install_calendar(patch_calendar)
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        with pytest.raises(InvalidDateFormatError):
            policy.session_status(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Priority 2 — calendar unavailable / out-of-range / error
# ---------------------------------------------------------------------------


class TestASharePolicyCalendarFailures:
    """Priority 2: fail-closed on calendar unavailability,
    out-of-range, and query exceptions (EOD-7.5 priority 2)."""

    def test_calendar_unavailable_raises_calendar_unavailable(
        self, patch_calendar
    ) -> None:
        patch_calendar["calendar"] = None  # UNAVAILABLE
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        with pytest.raises(CalendarUnavailableError) as excinfo:
            policy.session_status("2026-06-01")
        assert excinfo.value.date == "2026-06-01"
        assert excinfo.value.reason == "unavailable"

    def test_out_of_range_raises_date_out_of_range(self, patch_calendar) -> None:
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            first_session="2024-01-02",
            last_session="2026-12-31",
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        with pytest.raises(DateOutOfRangeError) as excinfo:
            policy.session_status("2099-01-01")
        assert excinfo.value.date == "2099-01-01"

    def test_before_first_session_raises_out_of_range(self, patch_calendar) -> None:
        _install_calendar(
            patch_calendar,
            first_session="2024-01-02",
            last_session="2026-12-31",
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        with pytest.raises(DateOutOfRangeError):
            policy.session_status("2020-01-02")

    def test_calendar_query_exception_raises_calendar_unavailable(
        self, patch_calendar
    ) -> None:
        """``is_session`` raising → ``CalendarUnavailableError``
        (mapped from CalendarDayStatus.ERROR)."""
        _install_calendar(
            patch_calendar, is_session_exc=True
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        with pytest.raises(CalendarUnavailableError) as excinfo:
            policy.session_status("2026-06-01")
        assert excinfo.value.reason == "error"

    def test_session_close_exception_raises_calendar_unavailable(
        self, patch_calendar
    ) -> None:
        """``session_close`` raising after the in-range + TRADING
        gate passed → ``CalendarUnavailableError`` (defensive
        fail-closed)."""
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at={},  # no entry → session_close will fail
            session_close_exc=True,
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        with pytest.raises(CalendarUnavailableError):
            policy.session_status("2026-06-01")

    def test_no_fallback_to_trading_days_2026_on_unavailable(
        self, monkeypatch, patch_calendar
    ) -> None:
        """Production adapter must NOT consult TRADING_DAYS_2026
        when the calendar is unavailable (EOD-7.5 priority 2)."""
        patch_calendar["calendar"] = None
        import skills.infra.date_utils as du
        from unittest import mock

        sentinel = mock.Mock(side_effect=AssertionError("no hardcoded fallback"))
        monkeypatch.setattr(du, "TRADING_DAYS_2026", sentinel, raising=False)

        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        with pytest.raises(CalendarUnavailableError):
            policy.session_status("2026-06-01")
        assert sentinel.call_count == 0

    def test_unknown_dependency_state_never_returns_not_a_trading_day(
        self, patch_calendar
    ) -> None:
        """SPEC EOD-7.5: an unknown dependency state (unavailable
        / out_of_range / error) MUST never collapse to
        ``NOT_A_TRADING_DAY``. Verify for all three failure modes."""
        clock = FakeAwareClock(_shanghai("2026-06-01", 10, 0))

        # unavailable
        patch_calendar["calendar"] = None
        policy = AShareCompletedSessionPolicy(clock=clock)
        with pytest.raises(CalendarUnavailableError):
            policy.session_status("2026-06-01")

        # out_of_range
        _install_calendar(
            patch_calendar,
            first_session="2024-01-02",
            last_session="2026-12-31",
        )
        with pytest.raises(DateOutOfRangeError):
            policy.session_status("2099-01-01")

        # error
        _install_calendar(patch_calendar, is_session_exc=True)
        with pytest.raises(CalendarUnavailableError):
            policy.session_status("2026-06-01")


# ---------------------------------------------------------------------------
# Priority 4 — NOT_A_TRADING_DAY
# ---------------------------------------------------------------------------


class TestASharePolicyNonTradingDay:
    """Priority 4: calendar says NOT_TRADING → NOT_A_TRADING_DAY."""

    def test_historical_non_trading_day_returns_not_a_trading_day(
        self, patch_calendar
    ) -> None:
        _install_calendar(
            patch_calendar,
            non_trading_days={"2026-06-19"},  # Dragon Boat Festival
            close_at={},
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        assert (
            policy.session_status("2026-06-19")
            is SessionStatus.NOT_A_TRADING_DAY
        )

    def test_future_non_trading_day_returns_not_a_trading_day(
        self, patch_calendar
    ) -> None:
        """A future weekend in calendar coverage returns
        ``NOT_A_TRADING_DAY`` (priority 4 runs before priority 5)."""
        _install_calendar(
            patch_calendar,
            non_trading_days={"2026-08-15"},
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        assert (
            policy.session_status("2026-08-15")
            is SessionStatus.NOT_A_TRADING_DAY
        )


# ---------------------------------------------------------------------------
# Priority 5 — FUTURE_TRADING_DAY
# ---------------------------------------------------------------------------


class TestASharePolicyFutureTradingDay:
    """Priority 5: future trading day in calendar coverage."""

    def test_future_trading_day_returns_future_trading_day(
        self, patch_calendar
    ) -> None:
        """Today is 2026-06-01; 2026-12-30 is a future trading day."""
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01", "2026-12-30"},
            close_at=_close_at(["2026-06-01", "2026-12-30"]),
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        assert (
            policy.session_status("2026-12-30")
            is SessionStatus.FUTURE_TRADING_DAY
        )

    def test_future_close_lookup_never_called(self, patch_calendar) -> None:
        """For a future trading day the algorithm must short-circuit
        at priority 5 — the calendar's ``session_close`` is never
        consulted (priority 6 only fires for today's date)."""
        fake = _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01", "2026-12-30"},
            close_at=_close_at(["2026-06-01", "2026-12-30"]),
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        policy.session_status("2026-12-30")
        assert "2026-12-30" not in fake.session_close_calls


# ---------------------------------------------------------------------------
# Priority 6 — SESSION_NOT_COMPLETED (today, before close + grace)
# ---------------------------------------------------------------------------


class TestASharePolicySessionNotCompleted:
    """Priority 6: today and earlier than close + grace."""

    def test_today_pre_close_returns_not_completed(self, patch_calendar) -> None:
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        # Clock at 14:59 Shanghai — well before 15:00 close.
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 14, 59))
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.SESSION_NOT_COMPLETED
        )

    def test_today_exactly_at_close_with_zero_grace_returns_completed(
        self, patch_calendar
    ) -> None:
        """Boundary: ``now == close + grace`` (grace=0). The seam
        uses ``<`` so equality is COMPLETED, not SESSION_NOT_COMPLETED."""
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 15, 0))
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.COMPLETED
        )

    def test_clock_in_utc_normalised_to_shanghai(self, patch_calendar) -> None:
        """Clock returning UTC must be normalised to Shanghai before
        the today / close comparison (EOD-7.3.1)."""
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at={"2026-06-01": _utc("2026-06-01", 7, 0)},  # 15:00 Shanghai
        )
        # Clock at 06:00 UTC = 14:00 Shanghai → pre-close.
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_utc("2026-06-01", 6, 0))
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.SESSION_NOT_COMPLETED
        )

    def test_close_instant_is_not_hardcoded_15_00(self, patch_calendar) -> None:
        """The close instant comes from the calendar — verify the
        adapter does NOT substitute a hardcoded 15:00 when the
        calendar reports 16:00 (some half-day / special sessions)."""
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at={"2026-06-01": _shanghai("2026-06-01", 16, 0)},
        )
        # 15:30 Shanghai — after the "fake" 16:00 close? No, before.
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 15, 30))
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.SESSION_NOT_COMPLETED
        )
        # And after 16:00 → COMPLETED.
        policy2 = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 16, 30))
        )
        assert (
            policy2.session_status("2026-06-01")
            is SessionStatus.COMPLETED
        )


# ---------------------------------------------------------------------------
# Priority 7 — COMPLETED
# ---------------------------------------------------------------------------


class TestASharePolicyCompleted:
    """Priority 7: today post-close / historical trading day."""

    def test_historical_trading_day_returns_completed(self, patch_calendar) -> None:
        _install_calendar(
            patch_calendar,
            trading_days={"2026-05-25"},
            close_at=_close_at(["2026-05-25"]),
        )
        # Today is 2026-06-01 — well after 2026-05-25.
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 10, 0))
        )
        assert (
            policy.session_status("2026-05-25")
            is SessionStatus.COMPLETED
        )

    def test_today_post_close_returns_completed(self, patch_calendar) -> None:
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 16, 0))
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.COMPLETED
        )


# ---------------------------------------------------------------------------
# cutoff_grace boundary
# ---------------------------------------------------------------------------


class TestASharePolicyCutoffGrace:
    """``cutoff_grace`` shifts the close boundary by a configurable
    timedelta (EOD-7.3.2)."""

    def test_within_grace_returns_not_completed(self, patch_calendar) -> None:
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        # Close at 15:00; grace = 5 min; now = 15:02 → within grace.
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 15, 2)),
            cutoff_grace=timedelta(minutes=5),
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.SESSION_NOT_COMPLETED
        )

    def test_at_grace_boundary_returns_completed(self, patch_calendar) -> None:
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        # Close at 15:00; grace = 5 min; now = 15:05 exactly → COMPLETED.
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 15, 5)),
            cutoff_grace=timedelta(minutes=5),
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.COMPLETED
        )

    def test_past_grace_returns_completed(self, patch_calendar) -> None:
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 15, 6)),
            cutoff_grace=timedelta(minutes=5),
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.COMPLETED
        )

    def test_zero_grace_default_keeps_completed_at_close(
        self, patch_calendar
    ) -> None:
        """Default grace=0: exactly-at-close → COMPLETED."""
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 15, 0))
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.COMPLETED
        )


# ---------------------------------------------------------------------------
# Zero-I/O contract
# ---------------------------------------------------------------------------


class TestASharePolicyZeroSideEffect:
    """The adapter is a pure function of (clock, calendar) — no
    provider fetch, no writer upsert, no cache put, no Mongo, no
    network, no file write, no log write (when no audit_logger is
    injected)."""

    def test_no_io_modules_imported_by_adapter(self) -> None:
        """The module must not import provider / writer / cache /
        Mongo / network / scheduling packages.

        The check parses the source's ``import ...`` statements
        rather than a substring search, so the module's
        docstring / comments can still reference the legacy
        modules for context.
        """
        import ast

        import skills.infra.session_policy as sp

        source = open(sp.__file__).read()
        tree = ast.parse(source)
        # Collect every imported module / attribute.
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
                    # also capture top-level package
                    top = alias.name.split(".")[0]
                    imported.add(top)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
                    imported.add(node.module.split(".")[0])
                for alias in node.names:
                    imported.add(alias.name)
        for forbidden in (
            "exchange_calendars",
            "pymongo",
            "mongomock",
            "p3_persistence_writer",
            "DataRouter",
            "ProviderRegistry",
            "unified_data",
            "CacheManager",
            "requests",
            "urllib",
            "http",
        ):
            assert forbidden not in imported, (
                f"session_policy.py must not import {forbidden!r}; "
                f"got: {imported}"
            )

    def test_audit_logger_none_produces_no_output(
        self, patch_calendar, capsys
    ) -> None:
        """With the default ``audit_logger=None`` no log/stdout
        bytes are produced across all four status verdicts."""
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01", "2026-05-25", "2026-12-30"},
            non_trading_days={"2026-06-19"},
            close_at=_close_at(
                ["2026-06-01", "2026-05-25", "2026-12-30"]
            ),
        )
        clock = FakeAwareClock(_shanghai("2026-06-01", 16, 0))
        policy = AShareCompletedSessionPolicy(clock=clock)
        for d in ("2026-06-01", "2026-05-25", "2026-12-30", "2026-06-19"):
            policy.session_status(d)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_audit_logger_receives_minimal_safe_record(
        self, patch_calendar
    ) -> None:
        """When a logger is injected, the recorded payload carries
        the documented fields and does NOT include full calendar
        payload or credentials."""
        captured: list[dict[str, Any]] = []

        class _SpyLogger:
            def info(self, event: str, **fields: Any) -> None:
                captured.append({"event": event, **fields})

        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 16, 0)),
            audit_logger=_SpyLogger(),
        )
        policy.session_status("2026-06-01")
        assert captured, "audit logger should have been called"
        rec = captured[0]
        # Required audit fields per EOD-7.6.
        assert rec["calendar_identity"] == "XSHG"
        assert rec["timezone"] == "Asia/Shanghai"
        assert rec["cutoff_policy_id"].startswith("OQ11-grace")
        assert rec["date"] == "2026-06-01"
        assert rec["clock_source_class"] == "FakeAwareClock"
        assert rec["status"] == SessionStatus.COMPLETED.value
        # No forbidden fields (calendar payload / secrets).
        for forbidden in ("trading_days", "first_session", "last_session",
                          "api_key", "password", "secret"):
            assert forbidden not in rec

    def test_audit_logger_failure_does_not_block_verdict(
        self, patch_calendar
    ) -> None:
        class _BrokenLogger:
            def info(self, event: str, **fields: Any) -> None:
                raise RuntimeError("simulated logger failure")

        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 16, 0)),
            audit_logger=_BrokenLogger(),
        )
        # Verdict still returns correctly.
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.COMPLETED
        )

    def test_session_status_does_not_call_datetime_now(
        self, patch_calendar
    ) -> None:
        """The adapter must NEVER call ``datetime.now()`` /
        ``date.today()`` directly — all time reads go through the
        injected clock (EOD-7.2).

        AST-level check: the module's source must not contain an
        ``datetime.now()`` / ``date.today()`` attribute-access
        pattern.
        """
        import ast

        import skills.infra.session_policy as sp

        source = open(sp.__file__).read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in (
                "now",
                "today",
            ):
                if isinstance(node.value, ast.Name) and node.value.id in (
                    "datetime",
                    "date",
                ):
                    raise AssertionError(
                        f"session_policy.py must not call "
                        f"{node.value.id}.{node.attr}() implicitly; "
                        f"got an AST node at line {node.lineno}"
                    )

        # And the runtime check: the only time source is the
        # injected clock; replacing the clock's ``now`` with a
        # spy that records invocations must produce exactly one
        # call per ``session_status``.
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        clock = FakeAwareClock(_shanghai("2026-06-01", 16, 0))
        policy = AShareCompletedSessionPolicy(clock=clock)
        # Reset call_count in case the constructor probes the clock
        # (it does — to validate tz-awareness).
        clock.call_count = 0
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.COMPLETED
        )
        # The clock's ``now()`` was consulted exactly once.
        assert clock.call_count == 1

    def test_session_status_does_not_call_date_today(
        self, patch_calendar
    ) -> None:
        """The adapter must NEVER call ``date.today()`` directly.

        The adapter does not import ``date`` from datetime at
        module level (it imports only ``datetime`` and
        ``timedelta``), so we assert via the AST that no
        ``date.today()`` attribute-access pattern is reachable
        at runtime.
        """
        import ast

        import skills.infra.session_policy as sp

        source = open(sp.__file__).read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "today":
                if isinstance(node.value, ast.Name) and node.value.id in (
                    "datetime",
                    "date",
                ):
                    raise AssertionError(
                        f"session_policy.py must not call "
                        f"{node.value.id}.today() implicitly; "
                        f"got an AST node at line {node.lineno}"
                    )

        # Sanity: the adapter still produces a verdict.
        _install_calendar(
            patch_calendar,
            trading_days={"2026-06-01"},
            close_at=_close_at(["2026-06-01"]),
        )
        policy = AShareCompletedSessionPolicy(
            clock=FakeAwareClock(_shanghai("2026-06-01", 16, 0))
        )
        assert (
            policy.session_status("2026-06-01")
            is SessionStatus.COMPLETED
        )


# ---------------------------------------------------------------------------
# Error hierarchy invariants
# ---------------------------------------------------------------------------


class TestASharePolicyErrorHierarchy:
    """All internal errors inherit ``SessionPolicyError``."""

    @pytest.mark.parametrize(
        "exc_cls",
        [
            CalendarUnavailableError,
            DateOutOfRangeError,
            NaiveClockError,
            InvalidDateFormatError,
        ],
    )
    def test_subclass_of_session_policy_error(self, exc_cls) -> None:
        assert issubclass(exc_cls, SessionPolicyError)

    def test_audit_metadata_fields_round_trip(self) -> None:
        err = CalendarUnavailableError(
            date="2026-06-01", clock_source_class="FakeClock", reason="unavailable"
        )
        assert err.date == "2026-06-01"
        assert err.clock_source_class == "FakeClock"
        assert err.reason == "unavailable"
        assert isinstance(err, SessionPolicyError)

    def test_all_errors_carry_default_metadata(self) -> None:
        """Default-construction must succeed without arguments so a
        generic ``raise SomeError()`` does not crash the audit
        collection. Specific error subclasses are documented to
        carry the three documented fields."""
        for cls in (
            CalendarUnavailableError,
            DateOutOfRangeError,
            NaiveClockError,
            InvalidDateFormatError,
        ):
            err = cls()
            assert err.date is None
            assert err.clock_source_class is None
            assert err.reason is None
            assert isinstance(err, SessionPolicyError)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


class TestASharePolicyPackageExports:
    """The package-level exports include the new symbols."""

    def test_session_policy_exports_present(self) -> None:
        import skills.infra as infra

        for name in (
            "SessionStatus",
            "CompletedSessionPolicy",
            "Clock",
            "SessionPolicyError",
            "CalendarUnavailableError",
            "DateOutOfRangeError",
            "NaiveClockError",
            "InvalidDateFormatError",
            "AShareCompletedSessionPolicy",
        ):
            assert hasattr(infra, name), f"missing export {name!r}"
            assert name in infra.__all__

    def test_session_status_values(self) -> None:
        assert {m.value for m in SessionStatus} == {
            "completed",
            "not_a_trading_day",
            "future_trading_day",
            "session_not_completed",
        }

    def test_completed_session_policy_is_runtime_checkable(self) -> None:
        class _AdHoc:
            def session_status(self, date):  # noqa: ANN001
                return SessionStatus.COMPLETED

        assert isinstance(_AdHoc(), CompletedSessionPolicy)
