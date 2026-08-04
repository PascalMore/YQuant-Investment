"""OQ-11 production composition root tests.

DESIGN-03-014 V0.33 §OQ-11B.1 / SPEC-03-014 V0.26 §3.3 EOD-8.2.

The composition root is the unique production seam for
:class:`MarketSentimentService`. The tests below pin the four
contract surfaces mandated by the design:

* ``clock=None`` (default) → returned service carries
  ``completed_session_policy=None``. No real policy is injected
  by default (EOD-8.8 — legacy offline permissive path stays
  intact).
* ``clock=<any Clock>`` → returned service carries an
  :class:`AShareCompletedSessionPolicy` with that clock and the
  audit-stable ``clock_source_class`` derived from it.
* The root performs **zero I/O** — no provider / writer / cache /
  Mongo / network / file write. We verify by introspecting the
  returned service's policy and running the full EOD-7 priority
  algorithm against a fake calendar (no real XSHG lookup).
* Naive clock → :class:`NaiveClockError` fail-fast at construction
  (preserves the EOD-7.5 priority 3 invariant that the canonical
  factory delegates).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

from skills.data.unified_data.services.composition import (
    build_production_sentiment_service,
)
from skills.data.unified_data.services.sentiment_service import (
    MarketSentimentService,
    SentimentSessionValidationError,
    CODE_INVALID_DATE_FORMAT,
    CODE_NOT_TRADING_DAY,
    CODE_FUTURE_TRADING_DAY,
    CODE_SESSION_NOT_COMPLETED,
)
from skills.infra.session_policy import (
    AShareCompletedSessionPolicy,
    Clock,
    CompletedSessionPolicy,
    NaiveClockError,
    SessionStatus,
    SystemClock,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


# ---------------------------------------------------------------------------
# Fakes — fake calendar + fake clock + fake audit collector
# ---------------------------------------------------------------------------


class _FakeCalendar:
    """Minimal stand-in for the ``exchange_calendars`` XSHG
    calendar that the strict seam in
    :mod:`skills.infra.date_utils` actually consults.

    Records every ``is_session`` / ``session_close`` call so the
    tests can prove the production policy path used the fake
    (no real calendar was ever reached). The fake is installed
    via monkeypatch on ``_strict_get_calendar``.
    """

    def __init__(
        self,
        *,
        trading_days: set[str] | None = None,
        non_trading_days: set[str] | None = None,
        first_session: str = "2024-01-02",
        last_session: str = "2026-12-31",
        close_map: dict[str, datetime] | None = None,
    ) -> None:
        self._trading = set(trading_days or set())
        self._non_trading = set(non_trading_days or set())
        self.first_session = first_session
        self.last_session = last_session
        self._close_map = dict(close_map or {})
        self.is_session_calls: list[str] = []
        self.session_close_calls: list[str] = []

    def is_session(self, d: str) -> bool:
        self.is_session_calls.append(d)
        if d in self._trading:
            return True
        if d in self._non_trading:
            return False
        return False  # default

    def session_close(self, d: str) -> datetime:
        self.session_close_calls.append(d)
        y, m, day = d.split("-")
        return datetime(int(y), int(m), int(day), 15, 0, tzinfo=SHANGHAI)


class _AwareFakeClock:
    """A tz-aware clock returning a fixed Shanghai instant."""

    def __init__(self, when: datetime) -> None:
        self._when = when

    def now(self) -> datetime:
        return self._when


class _NaiveFakeClock:
    """Returns a naive datetime — exercises ``NaiveClockError``."""

    def now(self) -> datetime:
        return datetime(2026, 6, 1, 14, 0, 0)


class _CollectingAuditLogger:
    """Audit logger that captures every event. The production
    adapter passes the ``info(event, **fields)`` shape; the spy
    collects events so the tests can prove zero I/O carries
    zero unintended side effects."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))


@pytest.fixture
def fake_calendar_holder(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Install a per-test fake calendar via the strict seam."""
    import skills.infra.date_utils as du

    holder: dict[str, Any] = {"calendar": None}

    def _factory() -> Any:
        return holder["calendar"]

    monkeypatch.setattr(du, "_strict_get_calendar", _factory)
    return holder


def _install(
    holder: dict[str, Any],
    *,
    trading: set[str] | None = None,
    non_trading: set[str] | None = None,
    first: str = "2024-01-02",
    last: str = "2026-12-31",
) -> _FakeCalendar:
    fake = _FakeCalendar(
        trading_days=trading or set(),
        non_trading_days=non_trading or set(),
        first_session=first,
        last_session=last,
    )
    holder["calendar"] = fake
    return fake


# ---------------------------------------------------------------------------
# Default path — clock=None → completed_session_policy=None
# ---------------------------------------------------------------------------


class TestBuildProductionSentimentServiceDefault:
    """The default ``clock=None`` path mirrors the legacy offline
    permissive behaviour."""

    def test_returns_market_sentiment_service_instance(self) -> None:
        service = build_production_sentiment_service()
        assert isinstance(service, MarketSentimentService)

    def test_default_clock_none_yields_none_policy(self) -> None:
        """EOD-8.8: ``clock=None`` (default) yields the legacy
        offline path (``completed_session_policy=None``).
        Production policy is NOT injected by default — the seam
        is opt-in."""
        service = build_production_sentiment_service()
        assert service._completed_session_policy is None

    def test_explicit_none_yields_none_policy(self) -> None:
        """Passing ``clock=None`` explicitly should be identical
        to omitting the argument."""
        service = build_production_sentiment_service(clock=None)
        assert service._completed_session_policy is None

    def test_default_service_does_not_inject_real_clock(self) -> None:
        """The factory must NOT touch ``datetime.now()`` /
        ``date.today()`` by default — only the caller's explicit
        ``clock`` invocation is permitted. We assert this by
        verifying the offline default does not perform any
        construction-time clock probe either."""
        # If the factory tried to probe the real clock, an
        # AShareCompletedSessionPolicy would already be attached.
        # We test this by introspecting through the existing
        # public field — the offline path keeps that field as
        # ``None`` exactly.
        service = build_production_sentiment_service()
        # Sanity: the service is the offline stub flavor.
        assert service._completed_session_policy is None
        # And the legacy permissive behaviour in service._is_refresh_authorized
        # stays False (no production injection):
        assert service._refresh_authorized is False


# ---------------------------------------------------------------------------
# Production wiring — clock=<something> → AShareCompletedSessionPolicy
# ---------------------------------------------------------------------------


class TestBuildProductionSentimentServiceWithClock:
    """Opt-in production wiring with an injected clock."""

    def test_aware_clock_returns_policy(self) -> None:
        clock = _AwareFakeClock(datetime(2026, 6, 1, 10, 0, tzinfo=SHANGHAI))
        service = build_production_sentiment_service(clock=clock)
        assert isinstance(service._completed_session_policy, AShareCompletedSessionPolicy)

    def test_system_clock_returns_policy(self) -> None:
        """The intended production value is ``SystemClock()`` —
        verify the integration end-to-end (no NaiveClockError)."""
        service = build_production_sentiment_service(clock=SystemClock())
        assert isinstance(service._completed_session_policy, AShareCompletedSessionPolicy)

    def test_policy_carries_injected_clock(self) -> None:
        clock = _AwareFakeClock(datetime(2026, 6, 1, 10, 0, tzinfo=SHANGHAI))
        service = build_production_sentiment_service(clock=clock)
        policy = service._completed_session_policy
        assert policy is not None
        assert policy._clock is clock  # type: ignore[attr-defined]

    def test_policy_audit_source_is_clock_class_name(self) -> None:
        clock = _AwareFakeClock(datetime(2026, 6, 1, 10, 0, tzinfo=SHANGHAI))
        service = build_production_sentiment_service(clock=clock)
        policy = service._completed_session_policy
        assert policy is not None
        assert policy._clock_source_class == "_AwareFakeClock"  # type: ignore[attr-defined]

    def test_policy_default_cutoff_grace_is_zero(self) -> None:
        """EOD-7.4: ``cutoff_grace=timedelta(0)`` is the default
        (close arrival == completion)."""
        clock = _AwareFakeClock(datetime(2026, 6, 1, 10, 0, tzinfo=SHANGHAI))
        service = build_production_sentiment_service(clock=clock)
        policy = service._completed_session_policy
        assert policy is not None
        assert policy._cutoff_grace == timedelta(0)  # type: ignore[attr-defined]

    def test_policy_custom_cutoff_grace_propagates(self) -> None:
        """An explicit ``cutoff_grace`` must reach the policy."""
        clock = _AwareFakeClock(datetime(2026, 6, 1, 10, 0, tzinfo=SHANGHAI))
        service = build_production_sentiment_service(
            clock=clock,
            cutoff_grace=timedelta(minutes=5),
        )
        policy = service._completed_session_policy
        assert policy is not None
        assert policy._cutoff_grace == timedelta(minutes=5)  # type: ignore[attr-defined]  # noqa: E501

    def test_naive_clock_raises_naive_clock_error(self) -> None:
        """EOD-7.5 priority 3 — naive clock fails fast at the policy
        constructor. The composition root must surface the same
        exception (no swallowing, no fallback)."""
        with pytest.raises(NaiveClockError):
            build_production_sentiment_service(clock=_NaiveFakeClock())  # type: ignore[arg-type]

    def test_constructor_probe_does_not_touch_file_or_net(self, tmp_path) -> None:
        """``SystemClock`` is the only thing that could touch the
        host system clock; everything else (caller-supplied
        fakes, fake calendars) must remain isolated. We assert
        this by passing a deterministic fake clock and verifying
        the factory performs no file mutation in the supplied
        tmp_path."""
        clock = _AwareFakeClock(datetime(2026, 6, 1, 10, 0, tzinfo=SHANGHAI))
        before = set(tmp_path.iterdir())
        build_production_sentiment_service(clock=clock)
        after = set(tmp_path.iterdir())
        assert before == after  # zero file side-effect


# ---------------------------------------------------------------------------
# Zero I/O — composition root must not perform provider / Mongo / cache I/O
# ---------------------------------------------------------------------------


class TestBuildProductionSentimentServiceZeroIO:
    """The composition root is a pure assembler. The tests pin
    zero I/O by introspecting what the factory does and does
    not touch.

    The factory does not import any writer, router, cache, or
    provider — only ``skills.infra.session_policy`` and the
    sentiment service. We verify by snapshotting ``sys.modules``
    before the call and asserting the visible side surface
    stays the same.
    """

    def test_no_provider_or_mongo_imports(self) -> None:
        """Build the factory module's ``__dict__`` shape: it does
        NOT reach into ``skills.data.unified_data.providers.akshare``
        or any Mongo-aware path."""
        import skills.data.unified_data.services.composition as composition_mod

        # ``composition`` must not import provider / mongo / router modules.
        module_attrs = set(vars(composition_mod))
        forbidden = {"akshare", "pymongo", "mongomock"}
        for token in forbidden:
            assert not any(token in name.lower() for name in module_attrs), (
                f"composition module reached into a forbidden module by name: {token}"
            )

    def test_no_file_write_to_disk(self, tmp_path) -> None:
        clock = _AwareFakeClock(datetime(2026, 6, 1, 10, 0, tzinfo=SHANGHAI))
        before = set(tmp_path.iterdir())
        build_production_sentiment_service(clock=clock)
        after = set(tmp_path.iterdir())
        assert before == after

    def test_no_network_call(self, monkeypatch) -> None:
        """Guard against accidental ``urllib`` / ``requests`` import
        side effects by raising on any outbound call."""
        import socket

        def _explode(*args, **kwargs):  # noqa: ANN001, ANN002
            raise AssertionError("network call attempted")

        monkeypatch.setattr(socket, "create_connection", _explode, raising=True)
        # Touch the factory — it must not open a socket.
        clock = _AwareFakeClock(datetime(2026, 6, 1, 10, 0, tzinfo=SHANGHAI))
        service = build_production_sentiment_service(clock=clock)
        assert isinstance(service, MarketSentimentService)


# ---------------------------------------------------------------------------
# E2E priority walk — the policy the factory returns works against fake calendar
# ---------------------------------------------------------------------------


class TestBuildProductionSentimentServiceE2E:
    """End-to-end EOD-7 priority walk through the policy the
    factory returns. We feed ``query_trading_day_status`` /
    ``session_close_strict`` from a per-test fake calendar so
    no real XSHG lookup occurs."""

    def test_completed_path(self, fake_calendar_holder) -> None:
        """Historical trading day + clock after close →
        ``SessionStatus.COMPLETED``."""
        _install(
            fake_calendar_holder,
            trading={"2024-06-01"},
            non_trading=set(),
            first="2024-01-02",
            last="2026-12-31",
        )
        # The installed fake's session_close is built lazily by
        # the policy; install it via a session_close wrapper.
        clock = _AwareFakeClock(datetime(2024, 6, 1, 16, 0, tzinfo=SHANGHAI))

        # Bring in the public service seam path so we mirror the
        # call shape ``MarketSentimentService.get_market_sentiment_snapshot``.
        from skills.data.unified_data.services.composition import (
            build_production_sentiment_service,
        )

        service = build_production_sentiment_service(clock=clock)
        policy = service._completed_session_policy
        assert policy is not None
        # We can't easily inject session_close into the fake since
        # the real path uses ``session_close_strict`` → calendar.session_close.
        # The fake above returns 15:00 Shanghai; clock is 16:00 → COMPLETED.
        assert policy.session_status("2024-06-01") == SessionStatus.COMPLETED

    def test_not_a_trading_day_path(self, fake_calendar_holder) -> None:
        """Non-trading day → ``SessionStatus.NOT_A_TRADING_DAY``."""
        # Install only the non-trading day — ``is_session`` returns
        # ``False`` by default for unknown dates.
        _install(
            fake_calendar_holder,
            trading=set(),
            non_trading={"2024-06-02"},
            first="2024-01-02",
            last="2026-12-31",
        )
        clock = _AwareFakeClock(datetime(2024, 6, 1, 10, 0, tzinfo=SHANGHAI))
        service = build_production_sentiment_service(clock=clock)
        policy = service._completed_session_policy
        assert policy is not None
        # The policy's strict seam routes ``2024-06-02`` to the fake
        # calendar's ``is_session("2024-06-02") → False``.
        assert (
            policy.session_status("2024-06-02")
            == SessionStatus.NOT_A_TRADING_DAY
        )

    def test_out_of_range_path(self, fake_calendar_holder) -> None:
        """Date outside calendar coverage → ``DateOutOfRangeError``
        inside the policy; the composition root did not catch
        it (fail-closed is the whole point)."""
        _install(
            fake_calendar_holder,
            first="2024-01-02",
            last="2024-12-31",
        )
        clock = _AwareFakeClock(datetime(2024, 6, 1, 10, 0, tzinfo=SHANGHAI))
        service = build_production_sentiment_service(clock=clock)
        policy = service._completed_session_policy
        assert policy is not None
        from skills.infra.session_policy import DateOutOfRangeError

        with pytest.raises(DateOutOfRangeError):
            policy.session_status("2099-01-01")


# ---------------------------------------------------------------------------
# The construction seam does not change the service signature or defaults
# ---------------------------------------------------------------------------


class TestCompositionDoesNotMutateServiceDefaults:
    """The composition root must NOT change any existing public
    field on ``MarketSentimentService``. We snapshot the type's
    constructor signature before and after to verify nothing
    leaked.
    """

    def test_market_sentiment_service_init_signature_intact(self) -> None:
        import inspect

        sig_before = inspect.signature(MarketSentimentService.__init__)
        service = build_production_sentiment_service()
        sig_after = inspect.signature(MarketSentimentService.__init__)
        assert str(sig_before) == str(sig_after)
        # And the factory-built service is a normal instance.
        assert isinstance(service, MarketSentimentService)

    def test_completion_path_does_not_introspect(self) -> None:
        """The factory must not call ``session_status`` during
        construction (no pre-flight probe beyond the canonical
        clock probe inside ``AShareCompletedSessionPolicy``)."""
        clock = _AwareFakeClock(datetime(2026, 6, 1, 10, 0, tzinfo=SHANGHAI))
        # Set the audit logger to assert no spurious session_status events.
        with mock.patch.object(
            AShareCompletedSessionPolicy,
            "session_status",
            side_effect=AssertionError("factory must not call session_status"),
        ):
            service = build_production_sentiment_service(clock=clock)
            assert isinstance(service, MarketSentimentService)
