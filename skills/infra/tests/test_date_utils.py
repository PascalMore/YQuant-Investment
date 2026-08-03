import unittest
from datetime import datetime
from unittest import mock

import pytest

from skills.infra import get_next_trading_day, get_trading_dates, is_trading_day
from skills.infra.date_utils import (
    CalendarDayStatus,
    parse_date_strict,
    query_trading_day_status,
    session_close_strict,
)


class DateUtilsTest(unittest.TestCase):
    def test_get_trading_dates_includes_2026_06_01_session(self):
        self.assertEqual(
            get_trading_dates('2026-05-28', '2026-06-03'),
            [
                '2026-05-28',
                '2026-05-29',
                '2026-06-01',
                '2026-06-02',
                '2026-06-03',
            ],
        )

    def test_is_trading_day_uses_cn_exchange_calendar(self):
        self.assertTrue(is_trading_day('2026-06-01'))
        self.assertFalse(is_trading_day('2026-06-19'))

    def test_next_trading_day_crosses_hardcoded_boundary(self):
        self.assertEqual(get_next_trading_day('2026-05-29'), '2026-06-01')


if __name__ == '__main__':
    unittest.main()


# ---------------------------------------------------------------------------
# Strict seam tests (OQ-11 / SPEC-03-014 V0.25 EOD-7)
# ---------------------------------------------------------------------------
#
# These tests cover the **strict** query seam in
# ``skills.infra.date_utils`` — the production-adapter-facing
# surface. They use fake calendar objects (not the real XSHG
# calendar) so the five-state verdict is exercised end-to-end
# without depending on the live environment. The legacy six
# public APIs above stay untouched; this block is additive.
#
# The strict seam must NEVER fall back to
# ``TRADING_DAYS_2026`` or to weekend-rule heuristics. The tests
# below cover every state in the
# :class:`CalendarDayStatus` enum plus the canonical input gate
# and the timezone-aware close instant contract.


class _FakeCalendar:
    """Minimal stand-in for ``exchange_calendars`` XSHG.

    Configured per test via the constructor: a set of in-range
    ``is_session`` answers, an explicit first/last session
    bound, an optional ``session_close`` mapping, and an
    ``is_session_exc`` flag to exercise the ``ERROR`` branch.
    The fake implements exactly the surface
    :mod:`skills.infra.date_utils` uses; nothing more.
    """

    def __init__(
        self,
        *,
        trading_days=None,
        first_session="2020-01-02",
        last_session="2030-12-31",
        close_map=None,
        is_session_exc=False,
    ) -> None:
        self._trading = set(trading_days or set())
        self.first_session = first_session
        self.last_session = last_session
        self._close_map = dict(close_map or {})
        self._is_session_exc = is_session_exc

    def is_session(self, d: str) -> bool:  # type: ignore[override]
        if self._is_session_exc:
            raise RuntimeError("simulated calendar failure")
        return d in self._trading

    def session_close(self, d: str) -> datetime:
        return self._close_map[d]


@pytest.fixture
def fake_calendar(monkeypatch):
    """Patch ``_strict_get_calendar`` to return a per-test fake.

    Uses ``monkeypatch.setattr`` so the patch is reverted at
    test teardown and the real calendar is never consulted.
    Tests that need a different calendar shape can override
    the local ``calendar`` variable after the fixture runs.
    """
    import skills.infra.date_utils as du

    holder: dict[str, object] = {"calendar": None}

    def _factory():
        return holder["calendar"]

    monkeypatch.setattr(du, "_strict_get_calendar", _factory)
    return holder


class TestParseDateStrict:
    """Canonical ``YYYY-MM-DD`` parser — no loose fallback."""

    @pytest.mark.parametrize(
        "canonical",
        ["2026-06-01", "2020-01-02", "1999-12-31", "2099-01-01"],
    )
    def test_canonical_strings_pass(self, canonical: str) -> None:
        from datetime import date

        assert parse_date_strict(canonical) == date.fromisoformat(canonical)

    @pytest.mark.parametrize(
        "bad",
        [
            "20260601",       # YYYYMMDD loose form
            "2026-06-01 09:30",  # with time
            "2026/06/01",     # wrong separator
            "06-01-2026",     # US-style
            "2026-6-1",       # non-zero-padded
            "not-a-date",
            "",
            "2026-13-01",     # regex OK but invalid month
            "2026-02-30",     # regex OK but invalid day
        ],
    )
    def test_non_canonical_rejected_with_value_error(self, bad: str) -> None:
        with pytest.raises(ValueError, match="canonical YYYY-MM-DD"):
            parse_date_strict(bad)

    @pytest.mark.parametrize("bad", [None, 1234, 1.5, [], {}, b"2026-06-01"])
    def test_non_string_rejected_with_value_error(self, bad) -> None:
        with pytest.raises(ValueError, match="canonical YYYY-MM-DD"):
            parse_date_strict(bad)  # type: ignore[arg-type]


class TestQueryTradingDayStatus:
    """Five-state discriminator for the production adapter."""

    def test_trading_day_returns_trading(self, fake_calendar) -> None:
        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2026-06-01"},
            first_session="2020-01-02",
            last_session="2030-12-31",
        )
        assert query_trading_day_status("2026-06-01") is CalendarDayStatus.TRADING

    def test_non_trading_day_returns_not_trading(self, fake_calendar) -> None:
        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2026-06-01"},
            first_session="2020-01-02",
            last_session="2030-12-31",
        )
        assert query_trading_day_status("2026-06-19") is CalendarDayStatus.NOT_TRADING

    def test_out_of_range_returns_out_of_range(self, fake_calendar) -> None:
        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2026-06-01"},
            first_session="2020-01-02",
            last_session="2026-12-31",
        )
        assert query_trading_day_status("2099-01-01") is CalendarDayStatus.OUT_OF_RANGE

    def test_before_first_session_is_out_of_range(self, fake_calendar) -> None:
        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2026-06-01"},
            first_session="2024-01-02",
            last_session="2030-12-31",
        )
        assert query_trading_day_status("2020-01-02") is CalendarDayStatus.OUT_OF_RANGE

    def test_calendar_query_exception_maps_to_error(self, fake_calendar) -> None:
        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2026-06-01"},
            is_session_exc=True,
        )
        assert query_trading_day_status("2026-06-01") is CalendarDayStatus.ERROR

    def test_calendar_missing_maps_to_unavailable(self, monkeypatch) -> None:
        import skills.infra.date_utils as du

        monkeypatch.setattr(du, "_strict_get_calendar", lambda: None)
        assert query_trading_day_status("2026-06-01") is CalendarDayStatus.UNAVAILABLE

    def test_non_canonical_rejected_before_calendar(self, fake_calendar) -> None:
        """Bad input must fail before any calendar I/O happens."""
        fake_calendar["calendar"] = _FakeCalendar(trading_days=set())
        with pytest.raises(ValueError, match="canonical YYYY-MM-DD"):
            query_trading_day_status("20260601")

    def test_never_returns_none_or_bool(self, fake_calendar) -> None:
        """The seam is exhaustive over the five states only."""
        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2026-06-01"},
            first_session="2024-01-02",
            last_session="2026-12-31",
        )
        for d in ("2026-06-01", "2026-06-19", "2099-01-01", "2020-01-02"):
            result = query_trading_day_status(d)
            assert isinstance(result, CalendarDayStatus)
            assert result is not None  # type: ignore[comparison-overlap]

    def test_does_not_fall_back_to_trading_days_2026(self, monkeypatch) -> None:
        """When the calendar is unavailable, the strict seam must
        return ``UNAVAILABLE`` and must NOT consult
        ``TRADING_DAYS_2026`` (no hardcoded fallback).
        """
        import skills.infra.date_utils as du

        # Make TRADING_DAYS_2026 lookup explode if anyone tries.
        sentinel = mock.Mock(side_effect=AssertionError("no hardcoded fallback"))
        monkeypatch.setattr(
            du, "TRADING_DAYS_2026", sentinel, raising=False
        )
        monkeypatch.setattr(du, "_strict_get_calendar", lambda: None)
        assert query_trading_day_status("2026-06-01") is CalendarDayStatus.UNAVAILABLE
        # TRADING_DAYS_2026 was never read.
        assert sentinel.call_count == 0


class TestSessionCloseStrict:
    """Tz-aware close instant — never hardcoded 15:00."""

    def test_returns_tz_aware_close(self, fake_calendar) -> None:
        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2026-06-01"},
            close_map={
                "2026-06-01": datetime(2026, 6, 1, 7, 0, tzinfo=__import__("zoneinfo").ZoneInfo("UTC")),
            },
        )
        close = session_close_strict("2026-06-01")
        assert close.tzinfo is not None
        assert close.utcoffset() is not None
        assert close == datetime(2026, 6, 1, 7, 0, tzinfo=__import__("zoneinfo").ZoneInfo("UTC"))

    def test_non_canonical_raises(self, fake_calendar) -> None:
        fake_calendar["calendar"] = _FakeCalendar()
        with pytest.raises(ValueError, match="canonical YYYY-MM-DD"):
            session_close_strict("20260601")

    def test_out_of_range_raises(self, fake_calendar) -> None:
        fake_calendar["calendar"] = _FakeCalendar(
            first_session="2024-01-02",
            last_session="2026-12-31",
        )
        with pytest.raises(ValueError, match="out of calendar range"):
            session_close_strict("2099-01-01")

    def test_calendar_unavailable_raises(self, monkeypatch) -> None:
        import skills.infra.date_utils as du

        monkeypatch.setattr(du, "_strict_get_calendar", lambda: None)
        with pytest.raises(ValueError, match="calendar unavailable"):
            session_close_strict("2026-06-01")

    def test_naive_close_raises(self, fake_calendar) -> None:
        fake_calendar["calendar"] = _FakeCalendar(
            close_map={"2026-06-01": datetime(2026, 6, 1, 7, 0)},
        )
        with pytest.raises(ValueError, match="timezone-aware"):
            session_close_strict("2026-06-01")

    def test_calendar_query_exception_raises(self, monkeypatch) -> None:
        """``session_close`` raising → seam raises ``ValueError``
        (not silently substituting a hardcoded value)."""
        import skills.infra.date_utils as du

        class _BoomCalendar:
            first_session = "2024-01-02"
            last_session = "2026-12-31"

            def session_close(self, d):
                raise RuntimeError("simulated calendar failure")

        monkeypatch.setattr(du, "_strict_get_calendar", lambda: _BoomCalendar())
        with pytest.raises(ValueError, match="calendar query raised"):
            session_close_strict("2026-06-01")


class TestStrictSeamExports:
    """The new symbols are exported from the infra package."""

    def test_calendar_day_status_enum_has_five_states(self) -> None:
        assert {m.name for m in CalendarDayStatus} == {
            "TRADING",
            "NOT_TRADING",
            "UNAVAILABLE",
            "OUT_OF_RANGE",
            "ERROR",
        }

    def test_package_reexports_strict_seam(self) -> None:
        import skills.infra as infra

        for name in (
            "CalendarDayStatus",
            "query_trading_day_status",
            "session_close_strict",
            "parse_date_strict",
        ):
            assert hasattr(infra, name), f"missing infra export {name!r}"
            assert name in infra.__all__
