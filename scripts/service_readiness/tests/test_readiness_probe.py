#!/usr/bin/env python3.12
"""Offline tests for the YQuant cold-start readiness probe."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import scripts.service_readiness.readiness_probe as rp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCompletedProcess:
    """Minimal stand-in for ``subprocess.CompletedProcess``."""

    def __init__(
        self,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeRunner:
    """Records every ``_run`` invocation and returns preset responses."""

    def __init__(self, responses: list[_FakeCompletedProcess] | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self._responses = list(responses or [])
        self._default_response = _FakeCompletedProcess(0, "", "")

    def __call__(
        self,
        cmd: list[str],
        *,
        timeout: float | None = None,
        capture: bool = False,
        text: bool | None = None,
        check: bool = False,
    ) -> _FakeCompletedProcess:
        self.calls.append((list(cmd), {"timeout": timeout, "capture": capture, "text": text}))
        if self._responses:
            return self._responses.pop(0)
        return _FakeCompletedProcess(self._default_response.returncode,
                                     self._default_response.stdout,
                                     self._default_response.stderr)


class _FakeJournal:
    """Records every ``_journal`` invocation and returns preset stdout."""

    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.calls: list[dict[str, Any]] = []
        self._stdout = stdout
        self._returncode = returncode

    def __call__(self, unit_name: str, since_ts: int) -> _FakeCompletedProcess:
        self.calls.append({"unit_name": unit_name, "since_ts": since_ts})
        return _FakeCompletedProcess(self._returncode, self._stdout, "")


def _patch_runner_and_journal(
    monkeypatch: pytest.MonkeyPatch,
    runner: _FakeRunner,
    journal: _FakeJournal,
    *,
    unit_active_ts: int = 1_700_000_000,
) -> None:
    """Install fakes; default ``unit_active_ts`` keeps tests deterministic."""
    monkeypatch.setattr(rp, "_run", runner)
    monkeypatch.setattr(rp, "_journal", journal)
    monkeypatch.setattr(rp, "UNIT_ACTIVE_TS_OVERRIDE", unit_active_ts)


class _SimpleNamespace:
    """Lightweight stand-in for ``argparse.Namespace``."""

    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


def _make_args(**overrides: Any) -> Any:
    """Build a minimal argparse Namespace mirroring the real CLI defaults."""
    defaults: dict[str, Any] = {
        "service": None,
        "all": False,
        "timeout": 10,
        "interval": 0.0,
        "max_retries": 3,
        "report": None,
        "boot_id": None,
    }
    defaults.update(overrides)
    return _SimpleNamespace(**defaults)


# ss -ltnp ``LISTEN`` row with a single PID matching MainPID=900
_SS_READY_LINES_900 = (
    'State   Recv-Q Send-Q Local Address:Port  Peer Address:Port\n'
    'LISTEN  0      128    127.0.0.1:8888      0.0.0.0:*    users:(("python3.12",pid=900,fd=7))\n'
)

# ss -ltnp ``LISTEN`` row with a FOREIGN PID (910) — should NOT pass
# MainPID consistency for a unit whose MainPID is 900.
_SS_FOREIGN_LINES_910 = (
    'State   Recv-Q Send-Q Local Address:Port  Peer Address:Port\n'
    'LISTEN  0      128    127.0.0.1:8888      0.0.0.0:*    users:(("intruder",pid=910,fd=7))\n'
)

# cgroup for a real DSA launch: user slice -> unit fragment
_CGROUP_DSA_FRAGMENT = (
    "0::/user.slice/user-1000.slice/user@1000.service/"
    "app.slice/daily-stock-analysis.service\n"
)

# cgroup belonging to a DIFFERENT unit — must trip P-DSA-4
_CGROUP_OTHER_UNIT = (
    "0::/user.slice/user-1000.slice/user@1000.service/"
    "app.slice/some-other-service.service\n"
)


def _patch_dsa_cgroup(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """Helper: return ``text`` from ``_cgroup_for_pid`` regardless of pid."""
    monkeypatch.setattr(rp, "_cgroup_for_pid", lambda _pid: text)


def _monotonic_at(values: list[float]) -> Any:
    """Return a callable serving ``values`` in order, repeating the last value.

    The first call captures ``started`` (DESIGN §2.3 requires it to be
    the very first ``time.monotonic()`` invocation); subsequent calls
    return the deque tail so the probe observes a deterministic clock.
    """

    iterator = iter(values)
    last_remaining = values[-1]

    def fake() -> float:
        try:
            return next(iterator)
        except StopIteration:
            return last_remaining

    return fake


def _patch_probe_round_spy(
    monkeypatch: pytest.MonkeyPatch,
) -> list[int]:
    """Wrap ``_probe_round_dsa`` with a call counter.

    Returns a list (mutable reference) whose length equals the number
    of times ``_probe_round_dsa`` was invoked during the test.  This
    is the canonical round-level seam — raw ``_run`` call counts
    cannot distinguish per-round internal probe detail from a seventh
    probe (per T3.1F contract).
    """
    original = rp._probe_round_dsa
    counter: list[int] = []

    def spy(args: argparse.Namespace) -> dict[str, Any]:  # type: ignore[arg-type]  # noqa: PGH003
        counter.append(1)
        return original(args)

    monkeypatch.setattr(rp, "_probe_round_dsa", spy)
    return counter


# ---------------------------------------------------------------------------
# DSA-UT-01: health=200 + MainPID + listener PID + cgroup consistent → ready
# ---------------------------------------------------------------------------


def test_dsa_ut_01_health_pid_listener_cgroup_consistent_yields_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSA-UT-01 — health=200 + MainPID + listener PID match + matching
    cgroup containing the unit fragment → status=ready on the very
    first probe round (no failed emissions).
    """

    runner = _FakeRunner(
        [
            _FakeCompletedProcess(0, "", ""),               # P-DSA-1 curl /health=200
            _FakeCompletedProcess(0, "900\n", ""),          # systemctl MainPID=900
            _FakeCompletedProcess(0, "900 ...", ""),        # ps -p 900 PASS
            _FakeCompletedProcess(0, _SS_READY_LINES_900, ""),  # ss -ltnp
        ]
    )
    journal = _FakeJournal()
    _patch_runner_and_journal(monkeypatch, runner, journal)
    _patch_dsa_cgroup(monkeypatch, _CGROUP_DSA_FRAGMENT)

    args = _make_args(timeout=2, interval=2, max_retries=3)
    final = rp.probe_service("DSA", args)

    assert final["status"] == "ready"
    assert final["probe_count"] == 1
    assert final["side_effect_free"] is True


# ---------------------------------------------------------------------------
# DSA-UT-02: health=200 but listener PID mismatch → stays starting (under threshold)
# ---------------------------------------------------------------------------


def test_dsa_ut_02_health_200_but_listener_pid_mismatch_stays_starting_under_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSA-UT-02 — health=200 but the 127.0.0.1:8888 listener is a
    DIFFERENT process than MainPID → P-DSA-4 reports
    ``listener_pid_mismatch``. Only 1 failure inside the budget means
    consecutive_failures=1 < max_retries=3 at the deadline, so the
    deadline branch keeps the final state ``starting``
    (DESIGN §2.3 rule 4 + SPEC R-006).
    """

    runner = _FakeRunner(
        [
            # round 1 — health=200, MainPID=900, listener=910 (mismatch)
            _FakeCompletedProcess(0, "", ""),
            _FakeCompletedProcess(0, "900\n", ""),
            _FakeCompletedProcess(0, "900 ...", ""),
            _FakeCompletedProcess(0, _SS_FOREIGN_LINES_910, ""),
            # round 2 — same setup (cheap cushion before the deadline)
            _FakeCompletedProcess(0, "", ""),
            _FakeCompletedProcess(0, "900\n", ""),
            _FakeCompletedProcess(0, "900 ...", ""),
            _FakeCompletedProcess(0, _SS_FOREIGN_LINES_910, ""),
        ]
    )
    journal = _FakeJournal()
    _patch_runner_and_journal(monkeypatch, runner, journal)
    _patch_dsa_cgroup(monkeypatch, _CGROUP_DSA_FRAGMENT)

    # Round 1 at t≈1s, then jump to t=30 > deadline=24.
    monkeypatch.setattr(
        rp.time, "monotonic", _monotonic_at([0.0, 0.0, 1.0, 30.0])
    )

    args = _make_args(timeout=2, interval=2, max_retries=3)
    final = rp.probe_service("DSA", args)

    # Only 1 failure → consecutive_failures=1 < max_retries=3 → stays starting
    assert final["status"] == "starting", (
        f"under-threshold deadline must stay 'starting', got {final['status']!r}"
    )
    assert final["probe_count"] == 1, (
        f"only 1 round completed before deadline, got probe_count={final['probe_count']}"
    )
    assert final["probe_error"] == "listener_pid_mismatch"
    assert final["side_effect_free"] is True


# ---------------------------------------------------------------------------
# DSA-UT-03: cgroup not in unit → 3 rounds reach cf=3 at deadline → failed
# ---------------------------------------------------------------------------


def test_dsa_ut_03_cgroup_not_in_unit_marks_failed_at_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSA-UT-03 — health=200, MainPID matches listener PID, but the
    cgroup does NOT include ``daily-stock-analysis.service`` →
    P-DSA-4 reports ``cgroup_unit_mismatch``. The DSA budget machine
    runs 3 consecutive mismatch rounds inside the budget, reaching
    ``consecutive_failures=3 == max_retries`` at the 24-second
    deadline, then emits ``failed`` with that exact reason.
    """

    ss_lines = (
        'LISTEN 0 128 127.0.0.1:8888 0.0.0.0:* users:(("python",pid=777,fd=7))\n'
    )
    # 3 rounds × 4 _run calls each = 12 responses
    runner = _FakeRunner(
        [
            _FakeCompletedProcess(0, "", ""),      # curl /health=200
            _FakeCompletedProcess(0, "777\n", ""),  # MainPID
            _FakeCompletedProcess(0, "777 ...", ""),# ps -p 777
            _FakeCompletedProcess(0, ss_lines, ""), # ss -ltnp
            _FakeCompletedProcess(0, "", ""),
            _FakeCompletedProcess(0, "777\n", ""),
            _FakeCompletedProcess(0, "777 ...", ""),
            _FakeCompletedProcess(0, ss_lines, ""),
            _FakeCompletedProcess(0, "", ""),
            _FakeCompletedProcess(0, "777\n", ""),
            _FakeCompletedProcess(0, "777 ...", ""),
            _FakeCompletedProcess(0, ss_lines, ""),
        ]
    )
    journal = _FakeJournal()
    _patch_runner_and_journal(monkeypatch, runner, journal)
    _patch_dsa_cgroup(monkeypatch, _CGROUP_OTHER_UNIT)

    # 3 cgroup-mismatch rounds at t≈[0, 4, 8], then cross deadline
    monkeypatch.setattr(
        rp.time,
        "monotonic",
        _monotonic_at(
            [
                0.0,    # started
                0.0, 0.0, 4.5,   # R1
                4.5, 5.0, 8.5,   # R2
                8.5, 9.0, 12.5,  # R3
                24.0, 24.0,       # deadline adjudication
            ]
        )
    )

    args = _make_args(timeout=2, interval=2, max_retries=3)
    final = rp.probe_service("DSA", args)

    # 3 rounds of cgroup mismatch → consecutive_failures=3 >= max_retries=3
    assert final["status"] == "failed"
    assert final["probe_count"] == 3
    assert final["probe_error"] == "cgroup_unit_mismatch"


# ---------------------------------------------------------------------------
# DSA-UT-04: cap=6 inside budget → all 6 rounds emit starting, no premature failed
# ---------------------------------------------------------------------------


def test_dsa_ut_04_consecutive_failures_inside_budget_still_starting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DSA-UT-04 — once the 6-round closed-form cap has been consumed
    but ``elapsed_seconds`` is still below the 24-second deadline, the
    DSA budget machine MUST emit ``starting`` on every round and MUST
    NEVER emit a terminal ``failed`` within the budget window. The
    ``probe_count`` on the 6th emission must equal the closed-form cap.

    We capture all emitted ndJSON lines so the test can verify budget-
    window emissions independently of the final deadline observation
    (which may legitimately produce ``failed`` when
    ``consecutive_failures`` reaches the threshold at the deadline).

    The previous loose ``status in {'starting', 'failed'}`` assertion
    silently accepted the cap-vs-deadline misfire that T2.1R / T3R
    flagged as R1; this stricter form is the canonical contract.
    """

    runner = _FakeRunner(
        [
            # 6 rounds × 2 _run calls each = 12 responses.
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
        ]
    )
    journal = _FakeJournal()
    _patch_runner_and_journal(monkeypatch, runner, journal)
    round_spy = _patch_probe_round_spy(monkeypatch)

    # Six rounds at t≈[0, 4, 8, 12, 16, 20]; round 6 ends at t≈22;
    # then the outer loop triggers schedule-gate / deadline at t=24.
    monkeypatch.setattr(
        rp.time,
        "monotonic",
        _monotonic_at(
            [
                0.0,   # started
                0.0, 0.0, 0.5,     # round 1
                4.5, 4.5, 5.0,     # round 2
                8.5, 8.5, 9.0,     # round 3
                12.5, 12.5, 13.0,  # round 4
                16.5, 16.5, 17.0,  # round 5
                20.5, 20.5, 22.0,  # round 6
                24.0, 24.0,        # deadline adjudication
            ]
        ),
    )

    args = _make_args(timeout=2, interval=2, max_retries=3)
    final = rp.probe_service("DSA", args)

    emitted_lines = capsys.readouterr().out.strip().splitlines()
    # 6 round emissions + 1 terminal deadline observation = 7
    assert len(emitted_lines) == 7, (
        f"expected 7 emissions (6 rounds + 1 deadline), got {len(emitted_lines)}"
    )

    for i in range(6):
        state = json.loads(emitted_lines[i])
        assert state["status"] == "starting", (
            f"round {state['probe_count']} must be 'starting', got {state['status']!r}"
        )
        assert state["probe_count"] == i + 1

    # Terminal deadline: cf=6 ≥ 3 → failed
    assert final["status"] == "failed"
    assert final["probe_count"] == 6
    assert final["probe_error"] in {
        "listener_not_found",
        "no_main_pid",
        "consecutive_failures",
    }
    assert final["side_effect_free"] is True
    # Round spy confirms exactly 6 probe rounds (no 7th).
    assert len(round_spy) == 6, (
        f"expected exactly 6 _probe_round_dsa calls, got {len(round_spy)}"
    )


# ---------------------------------------------------------------------------
# DSA-UT-05: budget=12, cf=3 >= mr=3 at deadline → exactly one failed
# ---------------------------------------------------------------------------


def test_dsa_ut_05_budget_expired_with_consecutive_failures_emits_exactly_one_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSA-UT-05 — once the budget deadline elapses without ready AND
    ``consecutive_failures`` has reached ``max_retries`` (3) inside the
    budget, the helper emits EXACTLY one terminal ``failed`` line. The
    threshold is genuinely exercised by driving three fully-failed
    rounds before the deadline observation (cap=3 via budget=12,
    interval=2, timeout=2). An off-by-one or strict-failed-on-cap-6
    behavior would surface as a 4th probe round or as ``starting``
    instead.

    Adjusts previous fixture to verifiably demonstrate the
    consecutive-failure threshold is met (cf=3 >= max_retries=3).
    """

    runner = _FakeRunner(
        [
            _FakeCompletedProcess(7, "", "curl_exit_7"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl_exit_7"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl_exit_7"),
            _FakeCompletedProcess(0, "0\n", ""),
        ]
    )
    journal = _FakeJournal()
    _patch_runner_and_journal(monkeypatch, runner, journal)
    round_spy = _patch_probe_round_spy(monkeypatch)

    args = _make_args(timeout=2, interval=2, max_retries=3, dsa_budget_seconds=12.0)

    # 3 failing rounds inside budget=12, then deadline fires.
    # Round 3's now must be < 12.0 so the probe runs before deadline.
    monkeypatch.setattr(
        rp.time,
        "monotonic",
        _monotonic_at(
            [
                0.0,   # started
                0.0, 0.5, 2.5,   # round 1
                4.5, 7.0, 9.0,   # round 2
                11.0, 11.5, 11.5, # round 3 (now=11.5 < deadline=12.0)
                # Deadline adjudication
                14.0, 14.0,       # deadline check: now=14 >= 12
            ]
        ),
    )

    final = rp.probe_service("DSA", args)

    assert final["status"] == "failed"
    assert final["probe_count"] == 3
    assert final["probe_error"] in {
        "listener_not_found",
        "no_main_pid",
        "consecutive_failures",
    }
    # Round spy confirms exactly 3 probe rounds (no 4th).
    assert len(round_spy) == 3, (
        f"expected exactly 3 _probe_round_dsa calls, got {len(round_spy)}"
    )


# ---------------------------------------------------------------------------
# DSA-UT-05a: 6 closed-form cap rounds, deadline adjudication, no 7th probe
# ---------------------------------------------------------------------------


def test_dsa_ut_05a_deadline_exact_edge_no_seventh_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSA-UT-05a — when all 6 closed-form cap rounds complete before
    the 24-second deadline, the helper MUST NOT start a seventh probe
    round. The 6th round completes at t≈22s; the outer loop's next
    invocation crosses the deadline and enters the deadline branch,
    which adjudicates (cf=6 ≥ 3 → failed) without any new
    ``_probe_round_dsa`` call. Total ``_run`` calls must equal
    exactly 12 (6 rounds × 2 = curl + systemctl per round).
    """

    runner = _FakeRunner(
        [
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(7, "", "curl: (7)"),
            _FakeCompletedProcess(0, "0\n", ""),
        ]
    )
    journal = _FakeJournal()
    _patch_runner_and_journal(monkeypatch, runner, journal)
    round_spy = _patch_probe_round_spy(monkeypatch)

    args = _make_args(timeout=2, interval=2, max_retries=3)

    monkeypatch.setattr(
        rp.time,
        "monotonic",
        _monotonic_at(
            [
                0.0,   # started
                0.0, 0.0, 0.5,     # round 1
                4.5, 4.5, 5.0,     # round 2
                8.5, 8.5, 9.0,     # round 3
                12.5, 12.5, 13.0,  # round 4
                16.5, 16.5, 17.0,  # round 5
                20.5, 20.5, 22.0,  # round 6
                24.0, 24.0,        # deadline adjudication
            ]
        ),
    )

    final = rp.probe_service("DSA", args)

    assert final["status"] == "failed"
    assert final["probe_count"] == 6
    assert final["probe_error"] in {
        "listener_not_found",
        "no_main_pid",
        "consecutive_failures",
    }
    # Round spy confirms exactly 6 probe rounds (no 7th).
    assert len(round_spy) == 6, (
        f"expected exactly 6 _probe_round_dsa calls, got {len(round_spy)}"
    )


# ---------------------------------------------------------------------------
# DSA-UT-05b: deadline under threshold (cf=3 < mr=4) → final starting, no failed
# ---------------------------------------------------------------------------


def test_dsa_ut_05b_deadline_under_threshold_no_fake_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSA-UT-05b — when the budget deadline expires with
    ``consecutive_failures < max_retries`` (cf=3, max_retries=4), the
    DSA budget machine MUST emit exactly one final ``starting``
    observation, MUST NOT fabricate a ``failed``, and MUST NOT start
    a 4th probe round.

    Three fully-failed rounds produce cf=3 which is below the
    max_retries=4 guard, so at deadline the adjudication yields
    terminal ``starting``.
    """

    runner = _FakeRunner(
        [
            # 3 rounds × 2 _run calls each = 6 responses.
            # P-DSA-1 curl OK (status=0) → skips P-DSA-2; systemctl returns MainPID=0.
            _FakeCompletedProcess(0, "", ""),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(0, "", ""),
            _FakeCompletedProcess(0, "0\n", ""),
            _FakeCompletedProcess(0, "", ""),
            _FakeCompletedProcess(0, "0\n", ""),
        ]
    )
    journal = _FakeJournal()
    _patch_runner_and_journal(monkeypatch, runner, journal)
    round_spy = _patch_probe_round_spy(monkeypatch)

    args = _make_args(timeout=2, interval=2, max_retries=4, dsa_budget_seconds=12.0)

    monkeypatch.setattr(
        rp.time,
        "monotonic",
        _monotonic_at(
            [
                0.0,   # started
                0.0, 0.5, 2.5,   # round 1
                4.5, 7.0, 9.0,   # round 2
                11.0, 11.5, 11.5, # round 3 (now=11.5 < deadline=12.0)
                # Deadline adjudication
                14.0, 14.0,       # deadline check: now=14 >= 12
            ]
        ),
    )

    final = rp.probe_service("DSA", args)

    assert final["status"] == "starting", (
        f"deadline-without-threshold must end at 'starting', got {final['status']!r}"
    )
    assert final["probe_count"] == 3
    # Round spy confirms exactly 3 probe rounds (no 4th).
    assert len(round_spy) == 3, (
        f"expected exactly 3 _probe_round_dsa calls, got {len(round_spy)}"
    )
    assert final["side_effect_free"] is True


# ---------------------------------------------------------------------------
# GWY-UT-06: _journal() queries the user-systemd field, not the system one
# ---------------------------------------------------------------------------


def test_journal_queries_user_systemd_unit_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_journal() must select the user-systemd journal field.

    All four readiness targets (DSA, TA-CN, both Hermes Gateways) are
    started under ``systemd --user``. The journal records their entries
    under ``_SYSTEMD_USER_UNIT``; querying ``_SYSTEMD_UNIT`` returns
    empty stdout, which silently masks the real readiness evidence and
    drives the boot audit to ``unknown`` until the 90-second total_wait
    expires. This test pins the selector so a future regression to the
    system-wide field would be caught locally.

    Read-only journal query contract is preserved: ``journalctl``
    (read-only invocation), ``--since=@<since_ts>``, the matching unit
    selector, ``--output=short-iso`` and ``--no-pager`` are all
    unchanged.
    """

    captured: list[list[str]] = []

    def runner(
        cmd: list[str],
        *,
        timeout: float | None = None,
        capture: bool = False,
        text: bool | None = None,
        check: bool = False,
    ) -> _FakeCompletedProcess:
        captured.append(list(cmd))
        # Mimic ``journalctl`` returning the selected unit's records.
        return _FakeCompletedProcess(0, "", "")

    monkeypatch.setattr(rp, "_run", runner)

    result = rp._journal("hermes-gateway.service", since_ts=1_700_000_000)

    assert result.returncode == 0
    assert len(captured) == 1, f"expected exactly one _run call, got {len(captured)}"
    cmd = captured[0]
    assert cmd[0] == "journalctl", f"first arg must be 'journalctl', got {cmd[0]!r}"
    assert "--no-pager" in cmd, "must keep '--no-pager' so the query stays read-only"
    assert "--output=short-iso" in cmd, "must keep '--output=short-iso'"
    assert f"--since=@{1_700_000_000}" in cmd, "must forward since_ts as '--since=@<ts>'"

    user_selectors = [arg for arg in cmd if arg.startswith("_SYSTEMD_USER_UNIT=")]
    sys_selectors = [arg for arg in cmd if arg.startswith("_SYSTEMD_UNIT=")]
    assert user_selectors == [
        "_SYSTEMD_USER_UNIT=hermes-gateway.service"
    ], (
        "Gateway is a user-systemd unit; _journal must use "
        f"_SYSTEMD_USER_UNIT=<unit>, got {user_selectors!r}"
    )
    assert sys_selectors == [], (
        "_SYSTEMD_UNIT=... would always return empty stdout for user units "
        f"and silently mask readiness evidence; got {sys_selectors!r}"
    )


# ---------------------------------------------------------------------------
# GWY-UT-07: journal connected evidence is unit-level corroboration only
# ---------------------------------------------------------------------------


def test_journal_connected_evidence_is_redacted_unit_level_corroboration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The journal ``connected`` line stays a redacted unit-level signal.

    After the multiplexed-gateway migration the journal belongs to ONE
    unit serving every profile, so its ``connected`` lines carry no
    profile name. They are therefore corroboration only and must never
    decide a per-profile verdict (see GWY-UT-08).

    The redaction contract must not be relaxed: the evidence string
    keeps a bounded timestamp prefix, collapses the message into the
    redacted ``[connected]`` category, and stays under the 128-char cap.
    """

    journal_line = (
        "2026-07-28T07:30:01+08:00 hermes[1234]: "
        "[Lark] connected with session_id=abc123\n"
    )

    captured: list[list[str]] = []

    def runner(
        cmd: list[str],
        *,
        timeout: float | None = None,
        capture: bool = False,
        text: bool | None = None,
        check: bool = False,
    ) -> _FakeCompletedProcess:
        captured.append(list(cmd))
        # Only the journalctl invocation should reach _run; any other
        # command means the probe leaked past the journal layer.
        if cmd and cmd[0] == "journalctl":
            return _FakeCompletedProcess(0, journal_line, "")
        return _FakeCompletedProcess(0, "", "")

    monkeypatch.setattr(rp, "_run", runner)
    monkeypatch.setattr(rp, "UNIT_ACTIVE_TS_OVERRIDE", 1_700_000_000)

    matched, timestamp, evidence, error = rp.probe_gwy_journal_connected(
        "hermes-gateway.service", unit_active_ts=1_700_000_000
    )

    assert matched is True, "the `[Lark] connected` line must match the platform_connected pattern"
    assert error is None
    assert timestamp is not None and timestamp.strip()
    assert evidence is not None
    assert "[connected]" in evidence, (
        f"evidence must carry the redacted `[connected]` category, got {evidence!r}"
    )
    assert len(evidence) <= 128, (
        f"evidence stays bounded to 128 chars, got {len(evidence)} (>128) in {evidence!r}"
    )
    # The journalctl invocation used the user-unit selector.
    assert any(
        arg == "_SYSTEMD_USER_UNIT=hermes-gateway.service" for arg in captured[0]
    ), f"journalctl must use _SYSTEMD_USER_UNIT=..., got {captured[0]!r}"


# ---------------------------------------------------------------------------
# GWY-UT-08: P-GWY-3 reads the multiplexed gateway state per profile
# ---------------------------------------------------------------------------


def _write_gateway_state(
    tmp_path: Path,
    *,
    platforms: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inject a fake ``~/.hermes/gateway_state.json`` for offline tests."""

    state_path = tmp_path / "gateway_state.json"
    state_path.write_text(
        json.dumps({"platforms": platforms}),
        encoding="utf-8",
    )
    monkeypatch.setattr(rp, "GATEWAY_STATE_PATH", state_path)


def test_probe_gwy_p3_reads_per_profile_platform_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P-GWY-3 must judge ``platforms["<profile>:feishu"]`` only.

    The multiplexed gateway serves every profile from one unit, so the
    gateway state file's per-profile entry is the ONLY source that can
    attribute a connection to one profile.
    """

    _write_gateway_state(
        tmp_path,
        platforms={
            "yquant:feishu": {
                "state": "connected",
                "writer_pid": 66990,
                "updated_at": "2026-10-27T17:07:53.170497+00:00",
            },
            "yinglong:feishu": {
                "state": "disconnected",
                "writer_pid": 66990,
                "updated_at": "2026-10-27T17:07:51.490755+00:00",
            },
        },
        monkeypatch=monkeypatch,
    )

    matched, timestamp, evidence, error = rp.probe_gwy_p3("yquant", 66990)
    assert matched is True
    assert error is None
    assert timestamp is not None
    assert evidence is not None and "connected" in evidence
    assert len(evidence) <= 128

    matched, _timestamp, evidence, error = rp.probe_gwy_p3("yinglong", 66990)
    assert matched is False, "a disconnected profile must not be reported connected"
    assert evidence is None
    assert error == "platform_not_connected"


def test_probe_gwy_p3_ignores_journal_connected_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A journal ``connected`` line must NOT confirm a profile.

    Both gateway profiles share one unit, so a journal ``connected`` line
    would otherwise let two profiles reuse the same evidence. P-GWY-3
    must stay unknown when the gateway state file has no entry for the
    profile.
    """

    _write_gateway_state(
        tmp_path,
        platforms={
            "yquant:feishu": {
                "state": "connected",
                "writer_pid": 66990,
                "updated_at": "2026-10-27T17:07:53.170497+00:00",
            },
        },
        monkeypatch=monkeypatch,
    )

    journal_line = (
        "2026-10-28T01:07:24+08:00 hermes[66990]: "
        "[Lark] connected to wss://msg-frontier.feishu.cn/ws/v2\n"
    )

    def runner(
        cmd: list[str],
        *,
        timeout: float | None = None,
        capture: bool = False,
        text: bool | None = None,
        check: bool = False,
    ) -> _FakeCompletedProcess:
        if cmd and cmd[0] == "journalctl":
            return _FakeCompletedProcess(0, journal_line, "")
        return _FakeCompletedProcess(0, "", "")

    monkeypatch.setattr(rp, "_run", runner)
    monkeypatch.setattr(rp, "UNIT_ACTIVE_TS_OVERRIDE", 1_700_000_000)

    matched, _timestamp, evidence, error = rp.probe_gwy_p3("yinglong", 66990)
    assert matched is False, (
        "the journal 'connected' line is unit-level only and must not "
        "confirm a profile that has no gateway-state entry"
    )
    assert evidence is None
    assert error == "platform_not_found"


# ---------------------------------------------------------------------------
# GWY-UT-09: stale gateway-state records are never reported connected
# ---------------------------------------------------------------------------


def test_probe_gwy_p3_rejects_stale_writer_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale ``writer_pid`` must degrade to "no evidence".

    ``gateway_state.json`` is not refreshed while the gateway is down,
    so a leftover ``connected`` record from a previous gateway lifetime
    must not be reported as a live connection. The record is judged
    unknown, not connected.
    """

    _write_gateway_state(
        tmp_path,
        platforms={
            "yquant:feishu": {
                "state": "connected",
                "writer_pid": 24440,  # previous gateway lifetime
                "updated_at": "2026-10-27T16:37:36.014115+00:00",
            },
        },
        monkeypatch=monkeypatch,
    )

    matched, _timestamp, evidence, error = rp.probe_gwy_p3("yquant", 66990)
    assert matched is False, "a stale writer_pid must not be judged connected"
    assert evidence is None
    assert error == "platform_state_stale"


# ---------------------------------------------------------------------------
# GWY-UT-10: both gateway probes target the single multiplexed unit
# ---------------------------------------------------------------------------


def test_gateway_probes_target_single_multiplexed_unit() -> None:
    """Both gateway services must map to ``hermes-gateway.service``.

    The per-profile units were deleted during the multiplexed-gateway
    migration; pointing the probes at them would make P-GWY-1/P-GWY-2
    fail permanently.
    """

    assert rp.GW_UNIT == "hermes-gateway.service"
    assert rp._unit_for_service("gw-yquant") == "hermes-gateway.service"
    assert rp._unit_for_service("gw-yinglong") == "hermes-gateway.service"
    assert rp.GW_SERVICE_PROFILES == {
        "gw-yquant": "yquant",
        "gw-yinglong": "yinglong",
    }


def test_gateway_round_uses_state_for_p3_and_journal_only_as_corroboration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P-GWY-3 must come from the state file; the journal is corroboration.

    The round result must expose P-GWY-3 (per-profile, from the state
    file) and P-GWY-3J (unit-level journal) separately so a reviewer can
    see that the journal never decides the per-profile verdict.
    """

    _write_gateway_state(
        tmp_path,
        platforms={
            "yquant:feishu": {
                "state": "connected",
                "writer_pid": 66990,
                "updated_at": "2026-10-27T17:07:53.170497+00:00",
            },
        },
        monkeypatch=monkeypatch,
    )

    def runner(
        cmd: list[str],
        *,
        timeout: float | None = None,
        capture: bool = False,
        text: bool | None = None,
        check: bool = False,
    ) -> _FakeCompletedProcess:
        if cmd[:2] == ["systemctl", "--user"] and "is-active" in cmd:
            return _FakeCompletedProcess(0, "", "")
        if cmd[:2] == ["systemctl", "--user"] and "show" in cmd:
            return _FakeCompletedProcess(0, "66990\n", "")
        if cmd[:1] == ["ps"]:
            return _FakeCompletedProcess(0, "66990 ...", "")
        if cmd and cmd[0] == "journalctl":
            return _FakeCompletedProcess(0, "", "")
        return _FakeCompletedProcess(0, "", "")

    monkeypatch.setattr(rp, "_run", runner)
    monkeypatch.setattr(rp, "UNIT_ACTIVE_TS_OVERRIDE", 1_700_000_000)

    results = rp._probe_round_gwy("gw-yquant", "hermes-gateway.service", 1_700_000_000)

    assert results["P-GWY-1"][1] is True
    assert results["P-GWY-2"][1] is True
    assert results["P-GWY-3"][1] is True
    assert results["P-GWY-3"][0] == "gateway_state:platform_connected"
    assert results["P-GWY-3J"][1] is False, "no journal connected line was emitted"

    status, platform_connected, platform_evidence = rp._evaluate_gwy(results)
    assert status == "ready"
    assert platform_connected == "confirmed_at_boot"
    assert platform_evidence == results["P-GWY-3"][3]


def test_gateway_round_degrades_when_state_has_no_profile_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit healthy but no per-profile evidence → degraded/unknown.

    The journal reports a ``connected`` line for the shared unit, but the
    yquant profile has no entry in the gateway state file, so the
    per-profile verdict must stay unknown.
    """

    _write_gateway_state(
        tmp_path,
        platforms={
            "yinglong:feishu": {
                "state": "connected",
                "writer_pid": 66990,
                "updated_at": "2026-10-27T17:07:51.490755+00:00",
            },
        },
        monkeypatch=monkeypatch,
    )

    journal_line = (
        "2026-10-28T01:07:24+08:00 hermes[66990]: [Lark] connected\n"
    )

    def runner(
        cmd: list[str],
        *,
        timeout: float | None = None,
        capture: bool = False,
        text: bool | None = None,
        check: bool = False,
    ) -> _FakeCompletedProcess:
        if cmd[:2] == ["systemctl", "--user"] and "is-active" in cmd:
            return _FakeCompletedProcess(0, "", "")
        if cmd[:2] == ["systemctl", "--user"] and "show" in cmd:
            return _FakeCompletedProcess(0, "66990\n", "")
        if cmd[:1] == ["ps"]:
            return _FakeCompletedProcess(0, "66990 ...", "")
        if cmd and cmd[0] == "journalctl":
            return _FakeCompletedProcess(0, journal_line, "")
        return _FakeCompletedProcess(0, "", "")

    monkeypatch.setattr(rp, "_run", runner)
    monkeypatch.setattr(rp, "UNIT_ACTIVE_TS_OVERRIDE", 1_700_000_000)

    results = rp._probe_round_gwy("gw-yquant", "hermes-gateway.service", 1_700_000_000)

    assert results["P-GWY-1"][1] is True
    assert results["P-GWY-2"][1] is True
    assert results["P-GWY-3"][1] is False
    assert results["P-GWY-3J"][1] is True, "the journal line is unit-level corroboration"

    status, platform_connected, platform_evidence = rp._evaluate_gwy(results)
    assert status == "degraded"
    assert platform_connected == "unknown"
    assert platform_evidence is None


@pytest.mark.parametrize("writer_pid", [True, 66990.5, "66990", [], {}, -1])
def test_gateway_rejects_invalid_writer_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writer_pid: Any
) -> None:
    """Only the integer PID written by the gateway is valid evidence."""
    _write_gateway_state(
        tmp_path,
        platforms={"yquant:feishu": {"state": "connected", "writer_pid": writer_pid}},
        monkeypatch=monkeypatch,
    )
    assert rp.probe_gwy_p3("yquant", 66990) == (
        False, None, None, "platform_writer_pid_invalid"
    )


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        (None, "gateway_state_missing"),
        (b"\xff", "gateway_state_unreadable"),
        (b"{", "gateway_state_invalid_json"),
        (b"[]", "gateway_state_invalid_payload"),
        (b"{}", "gateway_state_no_platforms"),
    ],
)
def test_gateway_invalid_state_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: bytes | None, error: str
) -> None:
    """Missing or corrupt local state must never confirm a connection."""
    state_path = tmp_path / "gateway_state.json"
    if raw is not None:
        state_path.write_bytes(raw)
    monkeypatch.setattr(rp, "GATEWAY_STATE_PATH", state_path)
    assert rp.probe_gwy_p3("yquant", 66990) == (False, None, None, error)


def test_gateway_does_not_echo_untrusted_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unexpected state text must not leak into emitted error strings."""
    _write_gateway_state(
        tmp_path,
        platforms={"yquant:feishu": {"state": "secret=" + "s" * 500, "writer_pid": 66990}},
        monkeypatch=monkeypatch,
    )
    assert rp.probe_gwy_p3("yquant", 66990) == (
        False, None, None, "platform_not_connected"
    )


@pytest.mark.parametrize("unit_active,pid_alive", [(False, True), (True, False)])
def test_gateway_unhealthy_unit_eventually_fails(
    monkeypatch: pytest.MonkeyPatch, unit_active: bool, pid_alive: bool
) -> None:
    """Current profile evidence cannot override inactive/dead unit probes."""
    monkeypatch.setattr(rp, "UNIT_ACTIVE_TS_OVERRIDE", 1_700_000_000)
    monkeypatch.setattr(rp, "probe_gwy_p1", lambda unit: (unit_active, None, None))
    monkeypatch.setattr(rp, "_unit_main_pid", lambda unit: (66990, None))
    monkeypatch.setattr(rp, "probe_gwy_p2", lambda unit, pid: (pid_alive, None, None))
    monkeypatch.setattr(rp, "probe_gwy_p3", lambda profile, pid: (True, None, "connected", None))
    monkeypatch.setattr(rp, "probe_gwy_journal_connected", lambda *args: (False, None, None, None))
    result = rp.probe_service("gw-yquant", _make_args(max_retries=1))
    assert result["status"] == "failed"


def test_gateway_ready_is_not_polluted_by_auxiliary_journal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Journal availability must not affect authoritative readiness evidence."""
    monkeypatch.setattr(rp, "UNIT_ACTIVE_TS_OVERRIDE", 1_700_000_000)
    monkeypatch.setattr(rp, "probe_gwy_p1", lambda unit: (True, None, None))
    monkeypatch.setattr(rp, "_unit_main_pid", lambda unit: (66990, None))
    monkeypatch.setattr(rp, "probe_gwy_p2", lambda unit, pid: (True, None, None))
    monkeypatch.setattr(rp, "probe_gwy_p3", lambda profile, pid: (True, None, "connected", None))
    monkeypatch.setattr(
        rp, "probe_gwy_journal_connected", lambda *args: (False, None, None, "journal_unreadable")
    )
    result = rp.probe_service("gw-yquant", _make_args())
    assert result["status"] == "ready"
    assert result["probe_error"] is None
