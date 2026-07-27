#!/usr/bin/env python3.12
"""Read-only readiness probes for the four YQuant user services.

The probe uses only local GET calls and local process/systemd/journal
queries.  The optional report is the sole writable artifact and is replaced
atomically.  Each status line is emitted as one JSON object (ndJSON).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


# Tracks the most recently emitted probe_error string for the active
# probe_service invocation. Used by the DSA budget machine to surface
# the last failed observation on its terminal ``failed`` emission
# without re-running or re-fetching from external state. Reset at the
# start of every probe_service call.
_LAST_EMITTED_PROBE_ERROR: list[str | None] = [None]  # mutable single-slot buffer

DSA_HEALTH_URL = "http://127.0.0.1:8888/health"
DSA_API_HEALTH_URL = "http://127.0.0.1:8888/api/health"
TACN_READYZ_URL = "http://localhost:8000/api/readyz"
TACN_HEALTH_URL = "http://localhost:8000/api/health"

DSA_SERVICE_NAME = "DSA"
TACN_SERVICE_NAME = "TA-CN"
GW_YQUANT_SERVICE_NAME = "gw-yquant"
GW_YINGLONG_SERVICE_NAME = "gw-yinglong"
ALL_SERVICES = (
    DSA_SERVICE_NAME,
    TACN_SERVICE_NAME,
    GW_YQUANT_SERVICE_NAME,
    GW_YINGLONG_SERVICE_NAME,
)

DSA_UNIT = "daily-stock-analysis.service"
TACN_UNIT = "tradingagents-cn.service"
GW_YQUANT_UNIT = "hermes-gateway-yquant.service"
GW_YINGLONG_UNIT = "hermes-gateway-yinglong.service"

DEFAULT_TIMEOUT = 10.0
DEFAULT_INTERVAL = 5.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_TOTAL_WAIT = 120.0
# DSA cold-start budget is frozen by RFC-10-010 §5.3.1 / SPEC §5.4.1 /
# DESIGN-10-010 §2.2 to exactly 14s measured API-ready + 10s safety
# margin = 24 seconds. The CLI rejects any value other than 24.0 so
# future callers cannot silently shorten the budget nor grow it into
# an unbounded wait.
DEFAULT_DSA_BUDGET_SECONDS = 24.0
DSA_HEALTH_LISTEN = "127.0.0.1:8888"
DSA_CGROUP_UNIT_FRAGMENT = "daily-stock-analysis.service"
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_TIMEOUT = 2
EXIT_BAD_ARGS = 3
EXIT_INTERNAL = 10

SCRIPT_PATH = Path(__file__).resolve()
REPORT_PATH = SCRIPT_PATH.parents[2] / "logs" / "cold-start-report.json"
PLATFORM_CONNECTED_PATTERNS = re.compile(
    r"(?:\bconnected\b|session\s+started|platform\s*.*\bconnected\b|websocket\s*.*\bconnected\b)",
    re.IGNORECASE,
)
# Tests may replace this value without consuming a fake systemd response.
UNIT_ACTIVE_TS_OVERRIDE: int | None = None


class _CompletedProcess:
    """Small subprocess result seam used by offline tests."""

    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode: int, stdout: Any = "", stderr: Any = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run(
    cmd: list[str],
    *,
    timeout: float | None = None,
    capture: bool = False,
    text: bool | None = None,
    check: bool = False,
) -> _CompletedProcess:
    """Run a read-only local command behind an injectable test seam."""

    kwargs: dict[str, Any] = {"check": check}
    if capture:
        kwargs["capture_output"] = True
    if text is not None:
        kwargs["text"] = text
    result = subprocess.run(list(cmd), timeout=timeout, **kwargs)
    return _CompletedProcess(
        result.returncode,
        result.stdout if capture else "",
        result.stderr if capture else "",
    )


def _journal(unit_name: str, since_ts: int) -> _CompletedProcess:
    """Read only the selected unit's journal since its active timestamp."""

    return _run(
        [
            "journalctl",
            f"--since=@{since_ts}",
            f"_SYSTEMD_UNIT={unit_name}",
            "--output=short-iso",
            "--no-pager",
        ],
        timeout=10,
        capture=True,
        text=True,
    )


def _http_get(
    url: str, timeout: float, *, parse_json: bool = False
) -> tuple[bool, int | None, str | None, Any | None]:
    """Perform one bounded GET and return success, status, error, and body."""

    if parse_json:
        cmd = ["curl", "-sf", "--max-time", str(timeout), url]
    else:
        cmd = [
            "curl",
            "-sf",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "--max-time",
            str(timeout),
            url,
        ]
    try:
        result = _run(cmd, timeout=timeout, capture=True, text=True)
    except subprocess.TimeoutExpired:
        return False, None, "timeout", None
    except FileNotFoundError:
        return False, None, "curl_not_found", None

    if result.returncode != 0:
        error = (result.stderr or "").strip() or f"curl_exit_{result.returncode}"
        return False, None, error, None

    if parse_json:
        try:
            payload = json.loads(result.stdout or "")
        except json.JSONDecodeError as exc:
            return False, None, f"invalid_json:{exc.msg}", None
        return True, 200, None, payload
    raw_status = (result.stdout or "").strip()
    # An empty status in a unit-test fake represents a successful HTTP GET.
    status = int(raw_status) if raw_status.isdigit() else 0
    if status == 200:
        return True, status, None, None
    if status == 0:
        return True, status, None, None
    return False, status, f"http_status_{status}", None


def _build_state(
    *,
    service: str,
    status: str,
    probe: str,
    probe_http_status: int | None,
    probe_error: str | None,
    probe_count: int,
    elapsed_seconds: float,
    platform_connected: str | None,
    platform_evidence: str | None,
) -> dict[str, Any]:
    """Build the minimum status object required by the readiness contract."""

    return {
        "service": service,
        "status": status,
        "probe": probe,
        "probe_http_status": probe_http_status,
        "probe_error": probe_error,
        "probe_count": probe_count,
        "elapsed_seconds": round(float(elapsed_seconds), 3),
        "platform_connected": platform_connected,
        "platform_evidence": platform_evidence,
        "side_effect_free": True,
    }


def _emit(state: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(state, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    # Mirror the last probe_error so the DSA terminal ``failed`` branch
    # can carry the most recent observation without re-running probes.
    _LAST_EMITTED_PROBE_ERROR[0] = state.get("probe_error")


def _last_emitted_probe_error() -> str | None:
    """Return the last probe_error string emitted by this process.

    Used solely by the DSA budget machine to surface the most recent
    failure reason when the 24-second deadline expires. Reads the
    single-slot module buffer populated by :func:`_emit`.
    """

    return _LAST_EMITTED_PROBE_ERROR[0] or None


# Individual probe functions -------------------------------------------------


def probe_dsa_p1(timeout: float) -> tuple[bool, int | None, str | None]:
    ok, status, error, _ = _http_get(DSA_HEALTH_URL, timeout)
    return ok, status, error


def probe_dsa_p2(timeout: float) -> tuple[bool, int | None, str | None]:
    ok, status, error, _ = _http_get(DSA_API_HEALTH_URL, timeout)
    return ok, status, error


def probe_dsa_p3() -> tuple[bool, int | None, str | None]:
    return _probe_pid_alive(DSA_UNIT)


def probe_tacn_p1() -> tuple[bool, int | None, str | None]:
    try:
        result = _run(["ss", "-tlnp"], capture=True, text=True, timeout=10)
    except FileNotFoundError:
        return False, None, "ss_not_found"
    if result.returncode != 0:
        return False, None, (result.stderr or "").strip() or "ss_failed"
    if re.search(r"(?:\*|0\.0\.0\.0|127\.0\.0\.1|::):8000(?:\s|$)", result.stdout or ""):
        return True, None, None
    return False, None, "port_not_bound"


def probe_tacn_p2(timeout: float) -> tuple[bool, int | None, str | None]:
    ok, status, error, _ = _http_get(TACN_READYZ_URL, timeout)
    return ok, status, error


def probe_tacn_p3(timeout: float) -> tuple[bool, int | None, str | None]:
    ok, status, error, payload = _http_get(TACN_HEALTH_URL, timeout, parse_json=True)
    if not ok:
        return False, status, error
    if isinstance(payload, dict) and payload.get("success") is True:
        return True, 200, None
    return False, 200, "success_false"


def probe_tacn_p4() -> tuple[bool, int | None, str | None]:
    return _probe_pid_alive(TACN_UNIT)


def probe_gwy_p1(unit_name: str) -> tuple[bool, int | None, str | None]:
    try:
        result = _run(["systemctl", "--user", "is-active", "--quiet", unit_name], timeout=10)
    except FileNotFoundError:
        return False, None, "systemctl_not_found"
    return result.returncode == 0, None, None if result.returncode == 0 else "inactive"


def probe_gwy_p2(unit_name: str) -> tuple[bool, int | None, str | None]:
    return _probe_pid_alive(unit_name)


def _sanitize_evidence(line: str) -> str:
    """Keep only timestamp and a bounded connection category."""

    timestamp = line[:25].strip()
    lowered = line.lower()
    if "session started" in lowered:
        category = "session started"
    elif "websocket" in lowered and "connected" in lowered:
        category = "websocket connected"
    elif "platform" in lowered and "connected" in lowered:
        category = "platform connected"
    else:
        category = "connected"
    return f"{timestamp[:64]} [{category}]"[:128]


def probe_gwy_p3(
    unit_name: str, unit_active_ts: int
) -> tuple[bool, str | None, str | None, str | None]:
    """Find bounded, redacted connection evidence in the unit journal."""

    try:
        result = _journal(unit_name, unit_active_ts)
    except subprocess.TimeoutExpired:
        return False, None, None, "journal_timeout"
    except FileNotFoundError:
        return False, None, None, "journalctl_not_found"
    if result.returncode != 0:
        return False, None, None, "journal_unreadable"
    for line in (result.stdout or "").splitlines():
        if PLATFORM_CONNECTED_PATTERNS.search(line):
            timestamp = line[:25].strip() or None
            return True, timestamp, _sanitize_evidence(line), None
    return False, None, None, None


def _probe_pid_alive(unit_name: str) -> tuple[bool, int | None, str | None]:
    try:
        shown = _run(
            ["systemctl", "--user", "show", "-p", "MainPID", unit_name, "--value"],
            capture=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return False, None, "systemctl_not_found"
    except subprocess.TimeoutExpired:
        return False, None, "systemctl_timeout"
    if shown.returncode != 0:
        return False, None, "show_failed"
    pid = (shown.stdout or "").strip()
    pid = pid.split()[0] if pid else ""
    if not pid or pid == "0" or not pid.isdigit():
        return False, None, "no_main_pid"
    try:
        process = _run(["ps", "-p", pid], timeout=10)
    except FileNotFoundError:
        return False, None, "ps_not_found"
    except subprocess.TimeoutExpired:
        return False, None, "ps_timeout"
    return process.returncode == 0, None, None if process.returncode == 0 else "pid_dead"


def _unit_for_service(service: str) -> str:
    return {
        DSA_SERVICE_NAME: DSA_UNIT,
        TACN_SERVICE_NAME: TACN_UNIT,
        GW_YQUANT_SERVICE_NAME: GW_YQUANT_UNIT,
        GW_YINGLONG_SERVICE_NAME: GW_YINGLONG_UNIT,
    }[service]


def _unit_active_ts(unit_name: str) -> int:
    """Read the unit active timestamp when available, with a safe fallback."""

    if UNIT_ACTIVE_TS_OVERRIDE is not None:
        return UNIT_ACTIVE_TS_OVERRIDE
    legacy_override = getattr(_run, "_UNIT_ACTIVE_TS_OVERRIDE", None)
    if legacy_override is not None:
        return int(legacy_override)
    try:
        result = _run(
            [
                "systemctl",
                "--user",
                "show",
                "-p",
                "ActiveEnterTimestamp",
                unit_name,
                "--value",
            ],
            capture=True,
            text=True,
            timeout=10,
        )
        raw = (result.stdout or "").strip()
        match = re.search(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})", raw)
        if result.returncode == 0 and match:
            parsed = datetime.strptime(
                f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M:%S"
            )
            return int(parsed.timestamp())
    except (FileNotFoundError, ValueError, subprocess.SubprocessError):
        pass
    return int(time.time())


# Round evaluators -----------------------------------------------------------


def _probe_pid_and_listener() -> tuple[int | None, str | None, int | None, list[str]]:
    """Return (main_pid, error, listener_pid, ls_cache_lines) for DSA's P-DSA-3 + P-DSA-4.

    The cache is exposed so ``_probe_dsa_with_budget`` can answer P-DSA-4's
    consistency checks without re-invoking ``ss -ltnp``. Listener PID is
    parsed only from a single ``127.0.0.1:8888`` line; if multiple distinct
    PIDs listen the round marks ``listener_pid_ambiguous`` so a foreign
    process squatting on 8888 cannot masquerade as DSA's ready evidence.
    """

    ls_cache: list[str] = []
    try:
        shown = _run(
            ["systemctl", "--user", "show", "-p", "MainPID", DSA_UNIT, "--value"],
            capture=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return None, "systemctl_not_found", None, ls_cache
    except subprocess.TimeoutExpired:
        return None, "systemctl_timeout", None, ls_cache
    if shown.returncode != 0:
        return None, "show_failed", None, ls_cache
    pid_text = (shown.stdout or "").strip().split()
    pid_value = pid_text[0] if pid_text else ""
    if not pid_value or pid_value == "0" or not pid_value.isdigit():
        return None, "no_main_pid", None, ls_cache
    main_pid = int(pid_value)
    try:
        process = _run(["ps", "-p", str(main_pid)], timeout=10)
    except FileNotFoundError:
        return main_pid, "ps_not_found", None, ls_cache
    except subprocess.TimeoutExpired:
        return main_pid, "ps_timeout", None, ls_cache
    if process.returncode != 0:
        return main_pid, "pid_dead", None, ls_cache

    try:
        ss_result = _run(["ss", "-ltnp"], capture=True, text=True, timeout=10)
    except FileNotFoundError:
        return main_pid, None, None, ls_cache
    except subprocess.TimeoutExpired:
        return main_pid, "ss_timeout", None, ls_cache
    if ss_result.returncode != 0:
        return main_pid, None, None, ls_cache
    raw_lines: list[str] = [str(line) for line in ((ss_result.stdout or "").splitlines())]
    ls_cache = raw_lines
    listener_pids: set[int] = set()
    for line in raw_lines:
        match = re.search(
            rf"127\.0\.0\.1:8888\b.*?pid=(\d+)",
            line,
        )
        if match:
            listener_pids.add(int(match.group(1)))
    if not listener_pids:
        return main_pid, None, None, ls_cache
    if len(listener_pids) > 1:
        return main_pid, "listener_pid_ambiguous", None, ls_cache
    return main_pid, None, next(iter(listener_pids)), ls_cache


def _cgroup_for_pid(pid: int) -> str | None:
    """Read ``/proc/<pid>/cgroup`` and return the raw, trimmed text.

    Errors (``No such file or directory``, permission denied) become
    ``None``; the caller decides whether a missing cgroup is fatal. We
    intentionally swallow permission errors so a partial read does not
    produce a false ``cgroup_mismatch`` against the systemd default.
    """

    try:
        return Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _probe_dsa_p4(main_pid: int, listener_pid: int | None) -> tuple[bool, int | None, str | None]:
    """P-DSA-4 — MainPID == listener PID, both inside the DSA unit cgroup.

    A standalone ``DSA_HEALTH_URL`` 200 is NOT sufficient evidence: an
    unrelated process squatting on 8888 would otherwise be able to mark
    DSA ready. This probe enforces the unit/PID/PORT/cgroup quaternary
    contract required by RFC-10-010 §4.3.1 / SPEC §3.2.1.
    """

    if not main_pid or main_pid <= 0:
        return False, None, "no_main_pid"
    if listener_pid is None:
        return False, None, "listener_not_found"
    if listener_pid != main_pid:
        return False, None, "listener_pid_mismatch"
    main_cgroup = _cgroup_for_pid(main_pid)
    listener_cgroup = _cgroup_for_pid(listener_pid)
    if main_cgroup is None or listener_cgroup is None:
        return False, None, "cgroup_unreadable"
    if main_cgroup != listener_cgroup:
        return False, None, "cgroup_mismatch"
    if DSA_CGROUP_UNIT_FRAGMENT not in main_cgroup:
        return False, None, "cgroup_unit_mismatch"
    return True, None, None


def _probe_round_dsa(args: argparse.Namespace) -> dict[str, Any]:
    p1 = (DSA_HEALTH_URL, *probe_dsa_p1(args.timeout))
    p2: tuple[str, bool, int | None, str | None] | None = None
    if not p1[1]:
        p2 = (DSA_API_HEALTH_URL, *probe_dsa_p2(args.timeout))
    main_pid, p3_error, listener_pid, _ls = _probe_pid_and_listener()
    p3_ok = main_pid is not None and p3_error is None
    p3 = (f"systemd:{DSA_UNIT}", p3_ok, None, p3_error)
    if listener_pid is None:
        p4 = ("listener:127.0.0.1:8888", False, None, "listener_not_found")
    elif main_pid is None:
        p4 = ("listener:127.0.0.1:8888", False, None, "no_main_pid")
    else:
        p4 = ("listener:127.0.0.1:8888", *_probe_dsa_p4(main_pid, listener_pid))
    result: dict[str, Any] = {"P-DSA-1": p1, "P-DSA-3": p3, "P-DSA-4": p4}
    if p2 is not None:
        result["P-DSA-2"] = p2
    result["_listener_pid"] = listener_pid
    result["_main_pid"] = main_pid
    return result


def _evaluate_dsa(results: dict[str, Any]) -> str:
    p1 = results["P-DSA-1"][1]
    p2 = results.get("P-DSA-2", (None, False, None, None))[1]
    p3 = results["P-DSA-3"][1]
    p4 = results["P-DSA-4"][1]
    return "ready" if ((p1 or p2) and p3 and p4) else "starting"


def _probe_round_tacn(args: argparse.Namespace) -> dict[str, Any]:
    p1 = ("tcp:8000", *probe_tacn_p1())
    p2 = (TACN_READYZ_URL, *probe_tacn_p2(args.timeout))
    p3 = (TACN_HEALTH_URL, *probe_tacn_p3(args.timeout))
    p4 = (f"systemd:{TACN_UNIT}", *probe_tacn_p4())
    return {"P-TACN-1": p1, "P-TACN-2": p2, "P-TACN-3": p3, "P-TACN-4": p4}


def _evaluate_tacn(results: dict[str, Any]) -> str:
    p1, p2, p3, p4 = (results[f"P-TACN-{i}"][1] for i in range(1, 5))
    p3_error = results["P-TACN-3"][3]
    if p1 and p2 and p4 and (p3 or p3_error == "timeout"):
        return "ready"
    if p1 and p4 and not p2 and p3_error == "success_false":
        return "degraded"
    return "starting"


def _probe_round_gwy(unit: str, unit_active_ts: int) -> dict[str, Any]:
    p1 = (f"systemd:{unit}", *probe_gwy_p1(unit))
    p2 = (f"pid:{unit}", *probe_gwy_p2(unit))
    matched, timestamp, evidence, error = probe_gwy_p3(unit, unit_active_ts)
    p3 = ("journal:platform_connected", matched, timestamp, evidence, error)
    return {"P-GWY-1": p1, "P-GWY-2": p2, "P-GWY-3": p3}


def _evaluate_gwy(results: dict[str, Any]) -> tuple[str, str | None, str | None]:
    p1 = results["P-GWY-1"][1]
    p2 = results["P-GWY-2"][1]
    matched = results["P-GWY-3"][1]
    evidence = results["P-GWY-3"][3]
    if p1 and p2 and matched:
        return "ready", "confirmed_at_boot", evidence
    if p1 and p2 and not matched:
        return "degraded", "unknown", None
    return "starting", None, None


def _first_error(*entries: tuple[Any, ...]) -> str | None:
    for entry in entries:
        error = entry[-1]
        if error:
            return str(error)
    return None


def _state_probe_details(service: str, results: dict[str, Any]) -> tuple[str, int | None, str | None]:
    if service == DSA_SERVICE_NAME:
        entries = [
            results["P-DSA-1"],
            results.get("P-DSA-2"),
            results["P-DSA-3"],
            results["P-DSA-4"],
        ]
    elif service == TACN_SERVICE_NAME:
        entries = [results[f"P-TACN-{i}"] for i in (2, 3, 1, 4)]
    else:
        entries = [results["P-GWY-3"], results["P-GWY-2"], results["P-GWY-1"]]
    entries = [entry for entry in entries if entry is not None]
    for entry in entries:
        if entry[1]:
            return str(entry[0]), entry[2] if isinstance(entry[2], int) else None, None
    entry = entries[0]
    return str(entry[0]), entry[2] if isinstance(entry[2], int) else None, _first_error(*entries)


def _dsa_pick_last_error(results: dict[str, Any]) -> str | None:
    """Pick the most specific failure reason from a DSA round.

    The DSA budget machine must surface the deepest subsystem error
    (e.g. ``listener_pid_mismatch``, ``cgroup_unit_mismatch``) on the
    terminal ``failed`` emission, not the generic
    ``consecutive_failures`` placeholder that ``_state_probe_details``
    falls back to when no probe is "PASS". Returns ``None`` if every
    probe reports success.
    """

    for key in ("P-DSA-4", "P-DSA-3", "P-DSA-1", "P-DSA-2"):
        entry = results.get(key)
        if entry is None:
            continue
        if entry[1]:
            continue
        error = entry[-1]
        if error:
            return str(error)
    return None


# State machine --------------------------------------------------------------


def _dsa_max_probes_before_deadline(interval: float, timeout: float, budget: float) -> int:
    """Closed-form integer cap from RFC §5.3.1 / DESIGN §2.3 schedule.

    Returns the maximum number of DSA probe rounds that can fully
    complete before the 24-second budget deadline, given the configured
    per-probe HTTP timeout and the inter-round sleep interval.

    The formula assumes each round costs at most ``timeout + interval``
    wall-clock time. ``timeout + interval`` is clamped to ``budget`` so
    extreme inputs cannot make the cap negative.
    """

    slot = max(float(timeout) + float(interval), 1e-9)
    slot = min(slot, float(budget))
    complete = int(float(budget - float(timeout)) // slot) + 1
    return max(1, complete)


def _probe_dsa_with_budget(
    args: argparse.Namespace,
    started: float,
    deadline: float,
    count: int,
    interval: float,
    max_retries: int,
    consecutive_failures: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int, int]:
    """Run the DSA-specific bounded-wait state machine.

    Returns ``(ready_state, final_failed_state, next_count, next_consecutive_failures)``.

    Semantics (DESIGN §2.3, SPEC R-006):

    * ``now < deadline`` → at most one new probe round may run; any
      non-ready status stays ``starting`` regardless of consecutive
      failures or the closed-form cap, and the cap is purely a
      scheduling capacity (it never emits ``failed`` by itself).
    * ``now >= deadline`` → MUST NOT call ``_probe_round_dsa`` or
      ``systemctl``/``ss``/``curl`` for a new probe; the helper
      adjudicates synchronously based on the last cached failure
      observation plus ``consecutive_failures``. Only the threshold
      branch can produce a terminal ``failed``; otherwise final state
      stays ``starting`` and the per-service observation ends.
    * ``max_retries`` is honored only as the confirmation guard for
      that final ``failed`` emission.

    The TA-CN and Gateway branches in ``probe_service`` still flow
    through the legacy while-loop and remain byte-for-byte identical.
    """

    now = time.monotonic()
    elapsed = now - started
    deadline_reached = now >= deadline
    cap = _dsa_max_probes_before_deadline(
        interval, args.timeout, deadline - started
    )

    # Deadline branch — no new probe, no network/systemctl call.
    if deadline_reached:
        final_state = _build_dsa_deadline_state(
            elapsed=elapsed,
            count=count,
            consecutive_failures=consecutive_failures,
            max_retries=max_retries,
        )
        _emit(final_state)
        if final_state["status"] == "failed":
            return None, final_state, count, consecutive_failures
        # Under-threshold: the deadline observation ends the per-service
        # observation. Return the final ``starting`` as ``ready_state``
        # so the caller's ``if ready_state is not None: return ready_state``
        # catches it and terminates the probe loop (DESIGN §2.3 rule 4).
        return final_state, None, count, consecutive_failures

    # Schedule-gate: once the closed-form cap has been fully exhausted
    # (``count >= cap``), the helper MUST NOT issue any further probe
    # rounds. Instead, it waits for the deadline to arrive (computing
    # the remaining wall time directly) and then adjudicates
    # synchronously — bypassing the outer loop to avoid a 7th probe
    # round (DESIGN §2.3 rule 5).
    if count >= cap:
        remaining = max(0.0, deadline - now)
        if remaining > 0:
            time.sleep(remaining)
        deadline_now = time.monotonic()
        deadline_elapsed = deadline_now - started
        final_state = _build_dsa_deadline_state(
            elapsed=deadline_elapsed,
            count=count,
            consecutive_failures=consecutive_failures,
            max_retries=max_retries,
        )
        _emit(final_state)
        if final_state["status"] == "failed":
            return None, final_state, count, consecutive_failures
        return final_state, None, count, consecutive_failures

    # Within the budget: run exactly one round and adjudicate it.
    probe_count = count + 1
    results = _probe_round_dsa(args)
    status = _evaluate_dsa(results)
    probe, http_status, error = _state_probe_details(DSA_SERVICE_NAME, results)
    # Surface the deepest failing probe error on each round emission;
    # when the round was a complete success we fall back to the legacy
    # state-details error, then to ``consecutive_failures`` only as a
    # last resort so a true ``ready`` emission still carries ``None``.
    round_error = error or _dsa_pick_last_error(results) or "consecutive_failures"
    last_error = round_error if status != "ready" else error
    state = _build_state(
        service=DSA_SERVICE_NAME,
        status=status,
        probe=probe,
        probe_http_status=http_status,
        probe_error=last_error,
        probe_count=probe_count,
        elapsed_seconds=elapsed,
        platform_connected=None,
        platform_evidence=None,
    )
    _emit(state)

    if status == "ready":
        return state, None, probe_count, 0

    next_consecutive_failures = consecutive_failures + 1
    if probe_count < cap:
        return None, None, probe_count, next_consecutive_failures
    # ``probe_count == cap``: the last scheduled round was just
    # completed. The next loop iteration will trigger the schedule-gate
    # which waits for the deadline and adjudicates.
    return None, None, probe_count, next_consecutive_failures


def _build_dsa_deadline_state(
    *,
    elapsed: float,
    count: int,
    consecutive_failures: int,
    max_retries: int,
) -> dict[str, Any]:
    """Produce the single terminal DSA observation at the deadline.

    Per DESIGN §2.3 rule 4: emit one terminal ``failed`` only when
    ``consecutive_failures >= max_retries``; otherwise emit the final
    ``starting`` and end the per-service observation. No new probe is
    triggered in either branch (DESIGN §2.3 rule 4 + SPEC R-006).
    """
    last_error = _last_emitted_probe_error()
    if consecutive_failures >= max_retries:
        probe_error = last_error or "consecutive_failures"
        return _build_state(
            service=DSA_SERVICE_NAME,
            status="failed",
            probe=f"systemd:{DSA_UNIT}",
            probe_http_status=None,
            probe_error=probe_error,
            probe_count=count,
            elapsed_seconds=elapsed,
            platform_connected=None,
            platform_evidence=None,
        )
    return _build_state(
        service=DSA_SERVICE_NAME,
        status="starting",
        probe=f"systemd:{DSA_UNIT}",
        probe_http_status=None,
        probe_error=last_error,
        probe_count=count,
        elapsed_seconds=elapsed,
        platform_connected=None,
        platform_evidence=None,
    )


def probe_service(service: str, args: argparse.Namespace) -> dict[str, Any]:
    """Poll one service until ready, failed, or the bounded wait expires.

    DSA executes inside a bounded, finite 24-second budget (RFC §5.3.1 /
    SPEC §5.4.1 / DESIGN §2.2). The helper
    ``_probe_dsa_with_budget`` owns scheduling + emission so this while
    loop can keep the legacy TA-CN/Gateway branches byte-for-byte
    identical. TA-CN and Gateway branches intentionally retain the
    original ``total_wait`` + ``consecutive_failures`` machinery so this
    change does not silently broaden any non-DSA semantics.
    """

    unit = _unit_for_service(service)
    started = time.monotonic()
    total_wait = float(getattr(args, "total_wait", DEFAULT_TOTAL_WAIT))
    interval = max(0.0, float(args.interval))
    max_retries = max(1, int(args.max_retries))
    active_ts = _unit_active_ts(unit) if service.startswith("gw-") else 0
    count = 0
    consecutive_failures = 0

    # DSA budget: deadline pinned to the START of this probe call's
    # monotonic clock; never inherited from another service, an old
    # journal, or a previous probe run. Non-DSA services receive a
    # non-binding placeholder budget so the loop-scoped type checker
    # remains happy without affecting their semantic behavior.
    dsa_budget = float(getattr(args, "dsa_budget_seconds", DEFAULT_DSA_BUDGET_SECONDS))
    deadline = started + dsa_budget
    _LAST_EMITTED_PROBE_ERROR[0] = None  # reset per-invocation observation

    while True:
        elapsed = time.monotonic() - started
        if service == DSA_SERVICE_NAME:
            # DSA budget-gated state machine. The helper owns both the
            # ``_emit`` calls and the probe-count management; it returns
            # ``count`` so the outer loop does not increment on its own.
            ready_state, failed_state, count, next_cf = _probe_dsa_with_budget(
                args, started, deadline, count, interval, max_retries,
                consecutive_failures,
            )
            consecutive_failures = next_cf
            if ready_state is not None:
                return ready_state
            if failed_state is not None:
                return failed_state
            # Still inside the budget. Honor ``interval`` but never sleep
            # past the deadline; convert any remaining budget to the
            # next round's cadence.
            sleep_for = min(interval, max(0.0, deadline - time.monotonic()))
            if sleep_for > 0:
                time.sleep(sleep_for)
            continue
        if service == TACN_SERVICE_NAME:
            results = _probe_round_tacn(args)
            status = _evaluate_tacn(results)
            platform_connected = platform_evidence = None
        else:
            results = _probe_round_gwy(unit, active_ts)
            status, platform_connected, platform_evidence = _evaluate_gwy(results)

        probe, http_status, error = _state_probe_details(service, results)
        if service.startswith("gw-"):
            journal_error = results["P-GWY-3"][4]
            if error is None and journal_error:
                error = journal_error
        state = _build_state(
            service=service,
            status=status,
            probe=probe,
            probe_http_status=http_status,
            probe_error=error,
            probe_count=count,
            elapsed_seconds=elapsed,
            platform_connected=platform_connected,
            platform_evidence=platform_evidence,
        )
        _emit(state)

        if status == "ready":
            return state
        if status == "degraded" and not service.startswith("gw-"):
            return state

        if status == "starting":
            consecutive_failures += 1
        else:
            consecutive_failures = 0

        if elapsed >= total_wait:
            state["status"] = "failed" if status == "starting" else status
            state["probe_error"] = "total_timeout"
            _emit(state)
            return state
        if status == "starting" and consecutive_failures >= max_retries:
            state["status"] = "failed"
            state["probe_error"] = error or "consecutive_failures"
            _emit(state)
            return state
        if interval:
            time.sleep(interval)


def _boot_id() -> str:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        if value:
            return value
    except (OSError, UnicodeError):
        pass
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _report_service(state: dict[str, Any]) -> dict[str, Any]:
    """Map ndJSON status fields to the cold-start report contract."""

    return {
        "name": state["service"],
        "status": state["status"],
        "probe_count": state["probe_count"],
        "elapsed": state["elapsed_seconds"],
        "platform_connected": state.get("platform_connected"),
        "platform_evidence": state.get("platform_evidence"),
        "error": state.get("probe_error"),
        "side_effect_free": True,
    }


def _complete_service_record(item: dict[str, Any]) -> dict[str, Any]:
    """Ensure every per-service record carries every schema-required field.

    The ``cold_start_report_schema.json`` ``additionalProperties: false``
    contract requires ``name``, ``status``, ``probe_count``, ``elapsed`` and
    ``side_effect_free`` to be present on every services[] entry. When a
    merge input is missing ``probe_count`` or supplies one that is not an
    integer ``>= 1`` (bool is also invalid), this helper raises
    ``ValueError`` so the malformed entry cannot be injected into
    services[]. For the remaining optional fields a missing value is
    filled with a safe default so the on-disk report cannot regress the
    schema invariant. ``side_effect_free`` is always forced to ``True`` —
    the readiness probe is read-only by contract and this invariant must
    not be relaxed by a merge input.
    """

    completed = dict(item)
    # cold_start_report_schema.json requires ``probe_count``: integer, minimum 1.
    # Reject missing, non-int (bool is also invalid), or <1 so a partial /
    # malformed payload cannot inject a schema-invalid entry into services[].
    probe_count = completed.get("probe_count")
    if isinstance(probe_count, bool) or not isinstance(probe_count, int) or probe_count < 1:
        raise ValueError(f"probe_count must be int >= 1 (got {probe_count!r})")
    completed.setdefault("elapsed", 0.0)
    completed.setdefault("platform_connected", None)
    completed.setdefault("platform_evidence", None)
    completed.setdefault("error", None)
    completed["side_effect_free"] = True
    return completed


def _merge_reports(existing: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
    """Merge concurrent per-service callbacks without losing prior states.

    When two readiness probes complete during the same boot (e.g. the four
    systemd ``ExecStartPost=`` callbacks racing), the second writer must
    not silently drop a service record from the first writer. This merger:

    * Keeps the latest per-service record by ``name``.
    * Fills in any schema-required field that is missing on either side,
      so the merged document always satisfies the
      ``cold_start_report_schema.json`` contract (``additionalProperties:
      false`` and the per-service ``required`` list).
    * Forces ``side_effect_free`` to ``True`` at every level. The probe is
      zero-side-effect by construction; the merge must not introduce a
      window where the report claims otherwise.
    """

    if not existing or existing.get("boot_id") != payload.get("boot_id"):
        # Different boot: the incoming payload supersedes the previous file.
        completed = dict(payload)
        completed["side_effect_free"] = True
        completed["services"] = [_complete_service_record(s)
                                  for s in completed.get("services", [])
                                  if isinstance(s, dict)]
        return completed
    merged = dict(existing)
    services: dict[str, dict[str, Any]] = {}
    for item in existing.get("services", []):
        if isinstance(item, dict) and item.get("name"):
            services[str(item["name"])] = _complete_service_record(item)
    for item in payload.get("services", []):
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = str(item["name"])
        prior = services.get(name, {})
        # Newer values overwrite older ones; missing keys fall back to the
        # prior record so neither writer regresses the schema.
        merged_item = dict(prior)
        merged_item.update(item)
        services[name] = _complete_service_record(merged_item)
    merged["services"] = list(services.values())
    merged["total_wait_seconds"] = max(
        [float(merged.get("total_wait_seconds", 0.0))]
        + [float(item.get("elapsed", 0.0)) for item in services.values()]
    )
    merged["side_effect_free"] = True
    return merged


@contextmanager
def _report_lock(parent: Path) -> Iterator[None]:
    """Serialize report replacements using a lock on the report directory."""

    directory_fd = os.open(parent, os.O_RDONLY)
    try:
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(directory_fd, fcntl.LOCK_UN)
        os.close(directory_fd)


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    """Atomically replace a report; inability to write is warning-only."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _report_lock(path.parent):
            existing: dict[str, Any] | None = None
            try:
                existing_payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing_payload, dict):
                    existing = existing_payload
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                pass
            merged = _merge_reports(existing, payload)
            fd, temporary = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(merged, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            except BaseException:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                raise
    except Exception as exc:  # report persistence must not alter readiness
        print(
            f"readiness_probe: cannot write report to {path}: "
            f"{exc.__class__.__name__}: {exc}",
            file=sys.stderr,
        )


def _build_report(services: list[dict[str, Any]], boot_id: str | None = None) -> dict[str, Any]:
    converted = [_report_service(state) for state in services]
    return {
        "boot_id": boot_id or _boot_id(),
        "services": converted,
        "total_wait_seconds": round(
            max((float(item["elapsed"]) for item in converted), default=0.0), 3
        ),
        "side_effect_free": True,
    }


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_BAD_ARGS, f"{self.prog}: error: {message}\n")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="readiness_probe.py",
        description="Probe YQuant service readiness using bounded, read-only checks.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--service", choices=ALL_SERVICES)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument(
        "--dsa-budget-seconds",
        type=float,
        default=DEFAULT_DSA_BUDGET_SECONDS,
        help=(
            "DSA-only cold-start budget in seconds. The RFC-10-010 / "
            "DESIGN-10-010 freeze this value at exactly 14s measured "
            "API-ready + 10s safety margin = 24. Any other value is "
            "rejected with EXIT_BAD_ARGS=3; the parameter exists only "
            "for documentation / future re-evaluation, not for silent "
            "shrinking or unlimited growth."
        ),
    )
    parser.add_argument("--report", type=str)
    parser.add_argument("--boot-id", type=str)
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not 0 < args.timeout <= DEFAULT_TIMEOUT:
        parser.error("--timeout must be in (0, 10]")
    if args.interval < 0:
        parser.error("--interval must be non-negative")
    if args.max_retries < 1:
        parser.error("--max-retries must be at least 1")
    # DSA budget is frozen to exactly 24 seconds per RFC §5.3.1 / SPEC
    # §5.4.1 / DESIGN §2.2. We still accept float input (and reject the
    # sentinel 0) but hard-reject any drift away from 24.0 so a future
    # operator can't silently expand the budget into an unbounded wait
    # or trim it below the measured cold-start baseline. The default of
    # ``DEFAULT_DSA_BUDGET_SECONDS`` already yields 24.0 on a clean
    # checkout; the explicit ``abs(...) <= 1e-9`` allows a tiny float
    # repr drift without permitting a real change.
    if not (abs(float(args.dsa_budget_seconds) - DEFAULT_DSA_BUDGET_SECONDS) <= 1e-9
            and float(args.dsa_budget_seconds) > 0):
        parser.error(
            f"--dsa-budget-seconds must be exactly "
            f"{DEFAULT_DSA_BUDGET_SECONDS} (got {args.dsa_budget_seconds})"
        )
    if args.report:
        try:
            requested = Path(args.report).expanduser().resolve(strict=False)
            allowed = REPORT_PATH.resolve(strict=False)
        except OSError:
            parser.error("--report path cannot be resolved")
        if requested != allowed:
            parser.error(f"--report must be exactly {allowed}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    services = list(ALL_SERVICES) if args.all else [args.service]
    final_states: list[dict[str, Any]] = []
    try:
        for service in services:
            final_states.append(probe_service(str(service), args))
    except Exception as exc:  # unexpected command/runtime failure
        print(f"readiness_probe: internal error: {exc}", file=sys.stderr)
        return EXIT_INTERNAL

    if args.report:
        if args.all:
            _write_report(
                REPORT_PATH,
                _build_report(final_states, boot_id=args.boot_id),
            )
        else:
            print(
                "readiness_probe: skipping canonical report write for --service; "
                "use --all --report to write the four-service report",
                file=sys.stderr,
            )
    if any(state["status"] == "failed" for state in final_states):
        return EXIT_FAILED
    if any(
        state["probe_error"] == "total_timeout" and state["status"] != "degraded"
        for state in final_states
    ):
        return EXIT_TIMEOUT
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
