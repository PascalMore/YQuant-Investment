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
