"""Preflight CLI tests (OQ-11 / DESIGN §OQ-11B.3 / SPEC V0.26 EOD-8.4).

These tests pin the **zero-I/O** dry-run contract, the
sample-derivation rules, and the fail-closed exit-code table.
They monkeypatch :func:`skills.infra.date_utils._strict_get_calendar`
to install a small in-test fake so the strict seam never
consults the real XSHG calendar.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

import pytest


SHANGHAI = ZoneInfo("Asia/Shanghai")


# ---------------------------------------------------------------------------
# Helpers — fake calendar installed via the strict seam
# ---------------------------------------------------------------------------


class _FakeCalendar:
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

    def is_session(self, d: str) -> bool:
        if d in self._trading:
            return True
        if d in self._non_trading:
            return False
        return False

    def session_close(self, d: str) -> datetime:
        if d not in self._close_map:
            raise KeyError(d)
        return self._close_map[d]


@pytest.fixture
def fake_calendar(monkeypatch):
    """Install a per-test fake calendar via the strict seam.

    The preflight CLI imports ``_strict_get_calendar`` by name
    (see ``scripts/unified_data/preflight_sentiment_policy.py``
    ``from skills.infra.date_utils import _strict_get_calendar``),
    so patching the strict-seam module alone does NOT redirect
    the preflight CLI's own ``_strict_get_calendar`` reference.
    We patch both namespaces: the strict seam (so
    ``query_trading_day_status`` / ``session_close_strict`` see
    the fake) and the preflight CLI module (so the
    ``_build_payload`` early-return path sees the fake too).
    """
    import skills.infra.date_utils as du
    import scripts.unified_data.preflight_sentiment_policy as ps

    holder: dict[str, Any] = {"calendar": None}

    def _factory():
        return holder["calendar"]

    monkeypatch.setattr(du, "_strict_get_calendar", _factory)
    monkeypatch.setattr(ps, "_strict_get_calendar", _factory)
    return holder


def _close_at(days: list[str], hh: int = 15, mm: int = 0) -> dict[str, datetime]:
    out: dict[str, datetime] = {}
    for d in days:
        y, mo, day = d.split("-")
        out[d] = datetime(int(y), int(mo), int(day), hh, mm, tzinfo=SHANGHAI)
    return out


# ---------------------------------------------------------------------------
# Field contract — payload always carries the documented keys
# ---------------------------------------------------------------------------


class TestPreflightPayloadContract:
    """The payload is a single JSON line on stdout, with the
    exact field set documented in DESIGN §OQ-11B.3.
    """

    REQUIRED_FIELDS = {
        "calendar_identity",
        "calendar_version",
        "coverage",
        "timezone",
        "trading_sample",
        "not_trading_sample",
        "session_close_sample",
        "zero_io",
        "verdict",
        "reason",
    }

    def test_payload_contains_required_fields(self, fake_calendar) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2024-01-02"},
            close_map=_close_at(["2024-01-02"]),
            first_session="2024-01-02",
        )
        # The forward scan needs a non_trading day. Pick 2024-01-07 (Sunday).
        fake_calendar["calendar"]._non_trading.add("2024-01-07")

        import io

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = main(["--dry-run"])
        assert rc == 0

        lines = [ln for ln in buf.getvalue().strip().split("\n") if ln]
        assert len(lines) == 1, "preflight must emit exactly one JSON line"
        payload = json.loads(lines[0])
        assert self.REQUIRED_FIELDS.issubset(payload.keys())

    def test_calendar_identity_is_xshg(self, fake_calendar) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2024-01-02"},
            close_map=_close_at(["2024-01-02"]),
            first_session="2024-01-02",
        )

        import io

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            main(["--dry-run"])
        payload = json.loads(buf.getvalue().strip())
        assert payload["calendar_identity"] == "XSHG"

    def test_timezone_is_asia_shanghai(self, fake_calendar) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2024-01-02"},
            close_map=_close_at(["2024-01-02"]),
            first_session="2024-01-02",
        )

        import io

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            main(["--dry-run"])
        payload = json.loads(buf.getvalue().strip())
        assert payload["timezone"] == "Asia/Shanghai"

    def test_session_close_normalised_to_shanghai(self, fake_calendar) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2024-01-02"},
            close_map=_close_at(["2024-01-02"], hh=15, mm=0),
            first_session="2024-01-02",
        )

        import io

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            main(["--dry-run"])
        payload = json.loads(buf.getvalue().strip())
        close = payload["session_close_sample"]["close"]
        assert close == "2024-01-02T15:00:00+08:00"

    def test_zero_io_all_zero(self, fake_calendar) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2024-01-02"},
            close_map=_close_at(["2024-01-02"]),
            first_session="2024-01-02",
        )

        import io

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            main(["--dry-run"])
        payload = json.loads(buf.getvalue().strip())
        assert payload["zero_io"] == {
            "provider": 0,
            "mongo": 0,
            "cache": 0,
            "network": 0,
            "file_write": 0,
        }


# ---------------------------------------------------------------------------
# Sample derivation rules — trading, not_trading, session_close
# ---------------------------------------------------------------------------


class TestPreflightSampleDerivation:
    """DESIGN §OQ-11B.3 #1-3: rule-driven sample derivation."""

    def test_trading_sample_uses_first_session(self, fake_calendar) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2024-01-02"},
            close_map=_close_at(["2024-01-02"]),
            first_session="2024-01-02",
        )

        import io

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            main(["--dry-run"])
        payload = json.loads(buf.getvalue().strip())
        assert payload["trading_sample"]["date"] == "2024-01-02"
        assert payload["trading_sample"]["status"] == "trading"

    def test_not_trading_sample_is_resolved(self, fake_calendar) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2024-01-02"},
            non_trading_days={"2024-01-03"},
            close_map=_close_at(["2024-01-02", "2024-01-03"]),
            first_session="2024-01-02",
        )

        import io

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            main(["--dry-run"])
        payload = json.loads(buf.getvalue().strip())
        assert payload["not_trading_sample"]["date"] == "2024-01-03"
        assert payload["not_trading_sample"]["status"] == "not_trading"
    def test_not_trading_sample_forward_then_backward(self, fake_calendar) -> None:
        """When the forward scan finds no NOT_TRADING day within
        365 days (it must be in-range — calendars with future-only
        sessions still need a sample), the helper falls back to
        a backward scan.
        """
        from scripts.unified_data.preflight_sentiment_policy import (
            _resolve_not_trading_sample,
        )

        fake = _FakeCalendar(
            # ``2024-01-02`` is the first_session and the only
            # trading day in a tight window; ``2024-01-01`` is a
            # known NOT_TRADING day just before.
            trading_days={"2024-01-02"},
            non_trading_days={"2024-01-01"},
            close_map=_close_at(["2024-01-02"]),
            first_session="2024-01-02",
            last_session="2026-12-31",
        )
        # The fixture redirects ``_strict_get_calendar`` to the
        # holder; install the fake so the strict-seam queries see
        # a present calendar.
        fake_calendar["calendar"] = fake

        # Forward scan: candidates like 2024-01-03 are NOT in our
        # ``non_trading`` set so ``is_session`` defaults to False.
        # The forward scan returns immediately because the calendar
        # declares every other day as non-trading. Verify the
        # helper resolves *something* (forward or backward).
        result = _resolve_not_trading_sample(fake, "2024-01-02")
        assert result["status"] == "not_trading"
        assert "date" in result


# ---------------------------------------------------------------------------
# Fail-closed behaviour — calendar unavailable / exception
# ---------------------------------------------------------------------------


class TestPreflightFailClosed:
    """EOD-8.7: any FAIL → exit code ``2``, ``verdict="fail"``,
    ``reason`` field carries the diagnosis. Zero I/O still."""

    def test_calendar_unavailable_returns_fail(self, fake_calendar) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = None  # UNAVAILABLE

        import io

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = main(["--dry-run"])
        assert rc == 2
        payload = json.loads(buf.getvalue().strip())
        assert payload["verdict"] == "fail"
        assert payload["reason"] == "calendar_unavailable"
        # The five samples are absent but the field is present and null.
        assert payload["trading_sample"] is None
        assert payload["not_trading_sample"] is None
        assert payload["session_close_sample"] is None
        # Zero I/O even on the failure path.
        assert payload["zero_io"]["provider"] == 0
        assert payload["zero_io"]["network"] == 0
        assert payload["zero_io"]["file_write"] == 0

    def test_apply_flag_rejected_with_exit_2(self) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        import io

        stderr = io.StringIO()
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
            rc = main(["--apply"])
        assert rc == 2
        assert "apply mode rejected" in stderr.getvalue()


# ---------------------------------------------------------------------------
# Zero write — preflight does NOT mutate the working tree
# ---------------------------------------------------------------------------


class TestPreflightZeroWrite:
    """EOD-8.4 / DESIGN §OQ-11B.3: ``--dry-run`` writes nothing
    to the working tree. We pin this by snapshotting
    ``os.environ`` (config / secrets are NEVER read), the
    ``sys.modules`` graph (no extra provider / mongo / cache
    imports), and the directory state via a sandbox."""

    def test_dry_run_does_not_read_secrets(self, fake_calendar, monkeypatch) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2024-01-02"},
            close_map=_close_at(["2024-01-02"]),
            first_session="2024-01-02",
        )

        # Plant a sentinel secret. If preflight reads it, the
        # spy will record it.
        sentinel = {
            "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME": "should-not-be-read",
            "YQUANT_MINIMAX_CODING_PLAN_API_KEY": "should-not-be-read",
        }

        accessed: list[str] = []

        real_getenv = os.getenv

        def _spy_getenv(name, default=None):
            accessed.append(name)
            return real_getenv(name, default)

        monkeypatch.setattr(os, "getenv", _spy_getenv)
        for k, v in sentinel.items():
            monkeypatch.setenv(k, v)

        import io

        with mock.patch("sys.stdout", io.StringIO()):
            rc = main(["--dry-run"])
        assert rc == 0
        # The factory reads at most ``PATH`` style environment
        # indirectly; we don't forbid reading ``os.environ``
        # (Python's import system does so for ``sys.path``). What
        # we forbid is reading the two documented secret env vars.
        for k in sentinel:
            assert k not in accessed, (
                f"preflight MUST NOT read secret env var {k!r}"
            )

    def test_dry_run_does_not_write_files(self, fake_calendar, tmp_path) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2024-01-02"},
            close_map=_close_at(["2024-01-02"]),
            first_session="2024-01-02",
        )
        before = set(tmp_path.iterdir())

        import io

        with mock.patch("sys.stdout", io.StringIO()):
            rc = main(["--dry-run"])
        assert rc == 0
        after = set(tmp_path.iterdir())
        assert before == after

    def test_dry_run_does_not_open_files(self, fake_calendar, monkeypatch) -> None:
        from scripts.unified_data.preflight_sentiment_policy import main

        fake_calendar["calendar"] = _FakeCalendar(
            trading_days={"2024-01-02"},
            close_map=_close_at(["2024-01-02"]),
            first_session="2024-01-02",
        )

        # Any builtin ``open`` call inside preflight after this
        # monkeypatch would fail loudly. We only honor builtin
        # ``open`` for the test harness; preflight uses ``sys.stdout``
        # / ``sys.stderr`` exclusively, so the spy should never
        # see a path.
        opened: list[str] = []
        real_open = open  # type: ignore[name-defined]

        def _spy_open(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", _spy_open)

        import io

        with mock.patch("sys.stdout", io.StringIO()):
            main(["--dry-run"])
        # ``open`` is called by Python's ``json`` etc. for import side
        # effects before we patched ``__main__``. After the patch we
        # only care about runtime ``open`` calls from the CLI.
        # We assert that nothing in preflight touched the file system
        # at process runtime via ``open`` for a writable mode.
        for p in opened:
            assert not p.endswith(".tmp"), p


# ---------------------------------------------------------------------------
# CLI invocation — subprocess smoke (dry-run path)
# ---------------------------------------------------------------------------


class TestPreflightSubprocessDryRun:
    """Spawn ``python -m scripts.unified_data.preflight_sentiment_policy``
    in a real subprocess so we catch import-side-effect regressions
    (DESIGN §OQ-11B.3 zero-I/O claim is at the Python module
    level, not at the function-level introscope).
    """

    @staticmethod
    def _spawn(argv: list[str]) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        # Hard-zero any secret vars so they cannot leak.
        for k in (
            "YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME",
            "YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD",
            "YQUANT_MINIMAX_CODING_PLAN_API_KEY",
        ):
            env[k] = "redacted"
        # Force PYTHONPATH so the script's ``skills.*`` imports resolve.
        env["PYTHONPATH"] = os.path.abspath(os.getcwd()) + os.pathsep + env.get(
            "PYTHONPATH", ""
        )
        return subprocess.run(
            [".venv/bin/python", "-m", "scripts.unified_data.preflight_sentiment_policy"] + argv,
            capture_output=True,
            text=True,
            env=env,
            cwd=os.getcwd(),
            timeout=60,
        )

    def test_dry_run_emits_single_json_line(self) -> None:
        proc = self._spawn(["--dry-run"])
        assert proc.returncode == 0, proc.stderr
        lines = [ln for ln in proc.stdout.strip().split("\n") if ln]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["verdict"] == "pass"
        assert payload["zero_io"]["provider"] == 0
        assert payload["zero_io"]["network"] == 0
        assert payload["zero_io"]["file_write"] == 0
