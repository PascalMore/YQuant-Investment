#!/usr/bin/env python3
"""Thin, whitelist-only QuantDinger client used by the Strategy Lab skill.

Four commands are exposed (``trade``, ``fetch-klines``, ``agent-whoami`` and
``agent-backtest``) plus a small set of pure helpers that the research sample
imports.  There is no task engine, no persistence layer and no SDK: every
remote call goes through :func:`request_json` or :func:`agent_call`, which only
accept the frozen operation whitelist.

The ``agent-*`` commands use the Agent Gateway (``/api/agent/v1``) with an
agent token; the ``trade`` flow uses the Human API with a JWT.  The two
channels never share credentials inside one process.

Importing this module performs no I/O and no network access.
"""

from __future__ import annotations

import argparse
import ast
import csv
import datetime as dt
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

LAB_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = LAB_ROOT / "strategies"

EXIT_OK, EXIT_CONTRACT, EXIT_EVIDENCE = 0, 2, 3
EXIT_AUTH, EXIT_BUDGET, EXIT_USAGE = 4, 5, 64
HUMAN, AGENT = "human", "agent"
PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

# Business classification -> process exit code (SPEC §5 / Design §3.5).
EXIT_BY_CLASSIFICATION = {
    "skipped": EXIT_OK,
    "baseline-kept": EXIT_OK,
    "candidate": EXIT_OK,
    "no-qualified-candidate": EXIT_OK,
    "insufficient-evidence": EXIT_EVIDENCE,
}

TERMINAL_JOB_STATUS = frozenset(
    {"succeeded", "failed", "cancelled", "canceled", "workerinterrupted"}
)
RESERVE_SECONDS = 30.0
MAX_OUTER_JOBS = 8
MAX_FULL_RECHECK_GROUPS = 5
MAX_TRIALS = 64
MAX_EVOLUTION_RUNS = 8
MAX_RELATIVE_UNITS = 8
MIN_SAMPLE_ROWS = 200
EVOLUTION_FOLDS = 4
POLL_INTERVAL_SECONDS = 15.0
BACKTEST_JOB_SECONDS = 180.0
EVOLUTION_JOB_SECONDS = 600.0
DEFAULT_WALL_SECONDS = 1200.0
MAX_WALL_SECONDS = 1800.0
MAX_DATA_PAGES = 4
MAX_TOP_CANDIDATES = 4

# Agent channel (V1.5).  The token comes from the environment first and only
# falls back to the single approved key inside skills/.env.
AGENT_TOKEN_ENV = "QUANTDINGER_AGENT_TOKEN"
AGENT_TOKEN_ENV_FILE_KEY = "QUANT_DINGER_AI_AGENT_TOKEN_MYMQUANT"
AGENT_TOKEN_ENV_FILE = LAB_ROOT.parents[1] / ".env"
IDEMPOTENCY_KEY_MAX_LENGTH = 120
AGENT_JOB_SECONDS = 180.0
AGENT_WALL_SECONDS = 300.0

# operation -> (method, path template, api family). The only reachable routes.
HTTP_OPERATIONS: dict[str, tuple[str, str, str]] = {
    "public_config": ("GET", "/api/settings/public-config", HUMAN),
    "script_templates": ("GET", "/api/strategies/script-templates", HUMAN),
    "compile_source": ("POST", "/api/strategies/script-sources/compile", HUMAN),
    "create_source": ("POST", "/api/strategies/script-sources/create", HUMAN),
    "source_detail": ("GET", "/api/strategies/script-sources/detail", HUMAN),
    "backtest_submit": ("POST", "/api/backtest/jobs", HUMAN),
    "backtest_job": ("GET", "/api/backtest/jobs/{jobId}", HUMAN),
    "backtest_cancel": ("POST", "/api/backtest/jobs/{jobId}/cancel", HUMAN),
    "backtest_get": ("GET", "/api/backtest/get", HUMAN),
    "backtest_history": ("GET", "/api/backtest/history", HUMAN),
    "evolution_parameter_space": ("GET", "/api/strategy-evolution/parameter-space", HUMAN),
    "evolution_estimate": ("POST", "/api/strategy-evolution/estimate", HUMAN),
    "evolution_run": ("POST", "/api/strategy-evolution/run", HUMAN),
    "evolution_job": ("GET", "/api/strategy-evolution/jobs/{jobId}", HUMAN),
    "evolution_jobs": ("GET", "/api/strategy-evolution/jobs", HUMAN),
    "evolution_cancel": ("POST", "/api/strategy-evolution/jobs/{jobId}/cancel", HUMAN),
    "human_klines": ("GET", "/api/indicator/kline", HUMAN),
    "agent_klines": ("GET", "/api/agent/v1/klines", AGENT),
    "agent_whoami": ("GET", "/api/agent/v1/whoami", AGENT),
    "agent_compile": ("POST", "/api/agent/v1/strategy-sources/compile", AGENT),
    "agent_backtest_run": ("POST", "/api/agent/v1/backtest/run", AGENT),
    "agent_job": ("GET", "/api/agent/v1/jobs/{jobId}", AGENT),
}

# Agent backtest request fields accepted by the gateway whitelist.  Anything
# else (sourceId, persist, strategyId, ...) is rejected before sending.
AGENT_BACKTEST_FIELDS = ("code", "startDate", "endDate", "initialCapital", "commission",
                          "slippage", "leverageEnabled", "leverage", "params")
# Flat metrics and server injected context of an Agent job result.
AGENT_METRIC_KEYS = ("totalReturn", "maxDrawdown", "winRate", "sharpeRatio",
                      "annualizedReturn", "annualizedReturnAvailable",
                      "annualizedReturnCapped", "totalTrades")
AGENT_CONTEXT_KEYS = ("resultStatus", "dataProvenance", "executionAssumptions",
                      "benchmark", "excessReturn", "benchmarkRelativeMetrics", "diagnostics")
# Capabilities the Agent gateway does not expose; explained before any call.
AGENT_UNSUPPORTED = ("gridGenerate", "strategyEvolution", "runOrSourceIdReadback",
                      "agentTrading")

_PATH_VALUE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SECRET_KEY_RE = re.compile(
    r"(?i)\b(authorization|token|password|secret|jwt|api[_-]?key)\b\s*[:=]\s*\S+"
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9._\-]{10,}")
# Agent Gateway tokens are "qd_agent_" + token_urlsafe(32); they carry no JWT
# header, so they need their own redaction rule.
_AGENT_TOKEN_RE = re.compile(r"\bqd_agent_[A-Za-z0-9._\-]{8,}")


class LabError(Exception):
    """Business failure carrying the process exit code and a safe summary."""

    def __init__(self, exit_code: int, message: str, **details: Any) -> None:
        super().__init__(message)
        self.exit_code = int(exit_code)
        self.message = message
        self.details = details

    def summary(self) -> str:
        parts = [self.message]
        parts += [f"{k}={_scrub(str(v))}" for k, v in sorted(self.details.items())]
        return " ".join(parts)


def _scrub(text: str) -> str:
    """Remove credential-looking substrings from any user visible string."""
    cleaned = _BEARER_RE.sub("Bearer <redacted>", str(text or ""))
    cleaned = _JWT_RE.sub("<redacted>", cleaned)
    cleaned = _AGENT_TOKEN_RE.sub("<redacted>", cleaned)
    return _SECRET_KEY_RE.sub(lambda m: f"{m.group(1)}=<redacted>", cleaned)


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def platform_run(wrapper: Any) -> dict[str, Any]:
    """Return the platform run row of a wrapper or of a bare row.

    Every consumer goes through this single unwrap path so that a wrapper
    ``{"runId", "run", "params"}`` and the platform row itself are read the
    same way.  A missing row yields ``{}`` instead of a fabricated payload.
    """
    if not isinstance(wrapper, dict):
        return {}
    inner = wrapper.get("run")
    if isinstance(inner, dict) and inner:
        return inner
    return wrapper


def run_id_of(wrapper: Any) -> Optional[int]:
    """Return the platform run id of a wrapper (``runId``) or row (``id``)."""
    if not isinstance(wrapper, dict):
        return None
    for value in (wrapper.get("runId"), platform_run(wrapper).get("id")):
        try:
            parsed = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def run_params(wrapper: Any) -> dict[str, Any]:
    """Return the params of a wrapper, preferring the submitted ones.

    The wrapper value is what this client asked the platform to use; the run
    row value is the platform's own record.  :func:`read_back_params` exposes
    the latter separately so the two can be compared.
    """
    if not isinstance(wrapper, dict):
        return {}
    for value in (wrapper.get("params"), platform_run(wrapper).get("params")):
        if isinstance(value, dict):
            return dict(value)
    return {}


def submitted_params(wrapper: Any) -> dict[str, Any]:
    """Return the params this client submitted for a run."""
    if not isinstance(wrapper, dict):
        return {}
    value = wrapper.get("params")
    return dict(value) if isinstance(value, dict) else {}


def read_back_params(wrapper: Any) -> dict[str, Any]:
    """Return the params the platform itself recorded for a run."""
    params = platform_run(wrapper).get("params")
    return dict(params) if isinstance(params, dict) else {}


def _result_of(run: Any) -> dict[str, Any]:
    """Return the full-period metrics container (``data.result``) of a run.

    The platform keeps metrics, provenance and execution assumptions inside
    ``data.result``; a missing container means *unknown*, never zero.
    """
    result = platform_run(run).get("result")
    return result if isinstance(result, dict) else {}


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"check": name, "status": status, "detail": detail}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so credentials never leave the configured origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


_OPENER = urllib.request.build_opener(_NoRedirect())


def _http_exit_code(status: int) -> int:
    return EXIT_AUTH if status in (401, 403) else EXIT_CONTRACT


def _http_send(
    url: str, method: str, headers: dict[str, str], payload: Optional[bytes], timeout: float
) -> tuple[int, bytes, dict[str, str]]:
    """Perform one HTTP call and return ``(status, body, headers)``.

    HTTP error statuses are returned instead of raised so that the Agent
    contract (402 billing, 409 idempotency) can be judged by the caller.
    """
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return int(response.status), response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
        except Exception:  # pragma: no cover - defensive only
            raw = b""
        return int(exc.code), raw, dict(getattr(exc, "headers", {}) or {})
    except urllib.error.URLError as exc:
        raise LabError(
            EXIT_CONTRACT, "http.unreachable", detail=_scrub(str(exc.reason))
        ) from exc
    except TimeoutError as exc:
        raise LabError(EXIT_BUDGET, "http.timeout", url=_scrub(url.split("?")[0])) from exc


def _http_call(
    url: str, method: str, headers: dict[str, str], payload: Optional[bytes], timeout: float
) -> bytes:
    status, raw, _ = _http_send(url, method, headers, payload, timeout)
    if status < 400:
        return raw
    message = ""
    try:
        parsed = json.loads(raw.decode("utf-8"))
        if isinstance(parsed, dict):
            message = str(parsed.get("msg") or parsed.get("message") or "")
    except (UnicodeDecodeError, json.JSONDecodeError):
        message = ""
    raise LabError(
        _http_exit_code(status),
        f"http.{status}",
        detail=_scrub(message) or "httpError",
        url=_scrub(url.split("?")[0]),
    )


def _build_url(base_url: str, template: str, path_values: dict[str, Any]) -> str:
    origin = str(base_url or "").strip().rstrip("/")
    if not origin.startswith(("http://", "https://")):
        raise LabError(EXIT_USAGE, "baseUrl.invalid")
    parsed = urllib.parse.urlsplit(origin)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path):
        raise LabError(EXIT_USAGE, "baseUrl.invalid")
    path = template
    for key, value in path_values.items():
        token = str(value)
        if not _PATH_VALUE_RE.match(token):
            raise LabError(EXIT_USAGE, "pathValue.invalid", key=key)
        path = path.replace("{" + key + "}", token)
    return f"{origin}{path}"


def request_json(
    operation: str,
    *,
    base_url: str,
    token: Optional[str] = None,
    params: Optional[dict[str, Any]] = None,
    body: Optional[dict[str, Any]] = None,
    path_values: Optional[dict[str, Any]] = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any]]:
    """Perform one whitelisted HTTP call and return ``(status, payload)``.

    Only the operations declared in :data:`HTTP_OPERATIONS` are reachable; no
    caller supplied path, method or body key can escape the whitelist.
    """
    spec = HTTP_OPERATIONS.get(operation)
    if spec is None:
        raise LabError(EXIT_USAGE, "http.operationNotAllowed", operation=operation)
    method, template, _api = spec
    if not token and operation != "human_klines":
        raise LabError(EXIT_AUTH, "auth.missing", operation=operation)
    url = _build_url(base_url, template, path_values or {})
    query = {k: v for k, v in (params or {}).items() if v is not None}
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    headers = {"Accept": "application/json", "User-Agent": "yquant-strategy-lab/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = None
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if _finite(timeout) is None or timeout <= 0:
        raise LabError(EXIT_BUDGET, "http.deadlineExceeded")
    raw = _http_call(url, method, headers, payload, min(30.0, float(timeout)))
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {"data": parsed}
    return 200, parsed


def parse_envelope(operation: str, status: int, payload: dict[str, Any]) -> Any:
    """Return ``data`` from a Human (``code==1``) or Agent (``code==0``) reply."""
    api = HTTP_OPERATIONS[operation][2]
    code = payload.get("code")
    ok = (code == 1) if api == HUMAN else (code == 0)
    if not ok or status >= 400:
        message = str(payload.get("msg") or payload.get("message") or "businessError")
        raise LabError(
            _http_exit_code(status) if status >= 400 else EXIT_CONTRACT,
            "business.error",
            operation=operation,
            detail=_scrub(message),
        )
    return payload.get("data")


def call_data(operation: str, **kwargs: Any) -> Any:
    """Call one whitelisted operation and return the unwrapped ``data`` field."""
    status, payload = request_json(operation, **kwargs)
    return parse_envelope(operation, status, payload)


# ───────────────────────── Agent channel (V1.5) ─────────────────────────
# The Agent Gateway is a separate identity space: agent token in, agent routes
# out.  The Human JWT paths above are untouched by everything below.

def _agent_env_file_value(path: Path) -> Optional[str]:
    """Return only the approved key of skills/.env; every other line is ignored."""
    prefix = AGENT_TOKEN_ENV_FILE_KEY + "="
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped.startswith(prefix):
                    continue
                value = stripped[len(prefix):].strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                return value or None
    except OSError:
        return None
    return None


def resolve_agent_token(
    *,
    env: Optional[dict[str, str]] = None,
    env_file: Optional[Path] = None,
) -> Optional[str]:
    """Resolve the agent token: injected environment first, then the .env key.

    This is the single credential path of the Agent channel, shared by the
    market-data command and the agent commands.  The Human JWT path stays on
    the environment only and never reads ``.env``.
    """
    environ = os.environ if env is None else env
    injected = str(environ.get(AGENT_TOKEN_ENV) or "").strip()
    if injected:
        return injected
    path = AGENT_TOKEN_ENV_FILE if env_file is None else env_file
    return _agent_env_file_value(Path(path))


def new_idempotency_key() -> str:
    """Return one fresh idempotency key for one logical submission."""
    return uuid.uuid4().hex


def agent_call(
    operation: str,
    *,
    base_url: str,
    token: Optional[str],
    params: Optional[dict[str, Any]] = None,
    body: Optional[dict[str, Any]] = None,
    path_values: Optional[dict[str, Any]] = None,
    timeout: float = 30.0,
    idempotency_key: Optional[str] = None,
) -> tuple[Any, dict[str, str]]:
    """Call one whitelisted Agent operation and return ``(data, headers)``.

    The Agent envelope is judged on its own: ``code=0`` carries the payload, a
    failure carries the HTTP status and stops the client immediately.
    """
    spec = HTTP_OPERATIONS.get(operation)
    if spec is None:
        raise LabError(EXIT_USAGE, "http.operationNotAllowed", operation=operation)
    method, template, api = spec
    if api != AGENT:
        raise LabError(EXIT_USAGE, "agent.operationNotAllowed", operation=operation)
    if not token:
        raise LabError(EXIT_AUTH, "auth.missing", operation=operation)
    key = "" if idempotency_key is None else str(idempotency_key).strip()
    if idempotency_key is not None and (not key or len(key) > IDEMPOTENCY_KEY_MAX_LENGTH):
        raise LabError(EXIT_USAGE, "idempotency.keyInvalid")
    if method == "POST" and not key:
        # Every Agent write carries its own Idempotency-Key; a missing key is
        # rejected before the request leaves the process.
        raise LabError(EXIT_USAGE, "idempotency.keyMissing", operation=operation)
    url = _build_url(base_url, template, path_values or {})
    query = {k: v for k, v in (params or {}).items() if v is not None}
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    headers = {"Accept": "application/json", "User-Agent": "yquant-strategy-lab/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if key:
        headers["Idempotency-Key"] = key
    payload = None
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if _finite(timeout) is None or timeout <= 0:
        raise LabError(EXIT_BUDGET, "http.deadlineExceeded")
    status, raw, response_headers = _http_send(
        url, method, headers, payload, min(30.0, float(timeout))
    )
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {"data": parsed}
    message = str(parsed.get("message") or parsed.get("msg") or "")
    if status in (401, 403):
        raise LabError(EXIT_AUTH, f"http.{status}", detail=_scrub(message))
    if status == 402:
        raise LabError(EXIT_CONTRACT, "billing.charged", detail=_scrub(message))
    if status == 409:
        raise LabError(EXIT_CONTRACT, "idempotency.conflict", detail=_scrub(message))
    if status >= 400:
        raise LabError(EXIT_CONTRACT, f"http.{status}", detail=_scrub(message))
    if parsed.get("code") not in (0, "0"):
        raise LabError(EXIT_CONTRACT, "business.error", code=parsed.get("code"),
                       detail=_scrub(message))
    data = parsed.get("data")
    if data is None:
        raise LabError(EXIT_CONTRACT, "agent.dataMissing")
    return data, response_headers


def agent_submit(
    operation: str,
    body: dict[str, Any],
    *,
    base_url: str,
    token: Optional[str],
    idempotency_key: str,
    timeout: float = 30.0,
) -> tuple[dict[str, Any], bool]:
    """Submit one Agent write and return ``(receipt, idempotentReplay)``.

    A transport failure leaves the submission state unknown; the identical
    request is then replayed exactly once with the same Idempotency-Key.  Two
    transport failures are reported as outcome-unknown instead of sending a
    new submission under a new key.
    """
    for attempt in (1, 2):
        try:
            data, headers = agent_call(
                operation, base_url=base_url, token=token, body=body,
                idempotency_key=idempotency_key, timeout=timeout,
            )
        except LabError as exc:
            if exc.message not in {"http.unreachable", "http.timeout"}:
                raise
            if attempt == 1:
                continue
            raise LabError(EXIT_BUDGET, "agent.outcomeUnknown", operation=operation,
                           detail=_scrub(exc.message)) from exc
        replayed = str(headers.get("Idempotent-Replayed")
                       or headers.get("idempotent-replayed") or "").lower() == "true"
        return _as_dict(data), replayed
    raise LabError(EXIT_BUDGET, "agent.outcomeUnknown", operation=operation)


def build_agent_backtest_body(
    *,
    code: str,
    start: str,
    end: str,
    capital: float,
    commission: float,
    slippage: float,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Build the Agent backtest request body from the whitelist only."""
    body = {
        "code": code,
        "startDate": start,
        "endDate": end,
        "initialCapital": float(capital),
        "commission": float(commission),
        "slippage": float(slippage),
        "leverageEnabled": False,
        "leverage": 1,
        "params": dict(params),
    }
    if set(body) != set(AGENT_BACKTEST_FIELDS):
        raise LabError(EXIT_CONTRACT, "agent.backtestFieldsMismatch")
    return body


def billing_contradiction(billing: Any) -> Optional[str]:
    """Return a reason when billing contradicts the closed-billing premise."""
    if not isinstance(billing, dict):
        return None
    if str(billing.get("status") or "").strip().lower() == "charged":
        return "billing.status=charged"
    charged = _finite(billing.get("charged"))
    if charged is not None and charged > 0:
        return "billing.charged>0"
    return None


def agent_backtest(
    *,
    code: str,
    params: dict[str, Any],
    start: str,
    end: str,
    capital: float,
    commission: float,
    slippage: float,
    base_url: str,
    token: Optional[str],
    budget: Budget,
    job_timeout: float = AGENT_JOB_SECONDS,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Compile, submit and read one Agent backtest job to its terminal state.

    The compile is a precondition, not a side effect: a failed compile stops
    before any backtest submission.  The flat Agent result is returned as-is
    and is never merged with the Human ``data.result`` hierarchy.
    """
    budget.check()
    compiled, _ = agent_submit(
        "agent_compile", {"code": code}, base_url=base_url, token=token,
        idempotency_key=new_idempotency_key(), timeout=timeout,
    )
    manifest = _as_dict(compiled.get("manifest"))
    if not manifest:
        raise LabError(EXIT_CONTRACT, "agent.manifestMissing")
    reason = billing_contradiction(compiled.get("billing"))
    if reason:
        raise LabError(EXIT_CONTRACT, "billing.contradiction", reason=reason)
    body = build_agent_backtest_body(
        code=code, start=start, end=end, capital=capital, commission=commission,
        slippage=slippage, params=params,
    )
    budget.take_outer_job()
    receipt, replayed = agent_submit(
        "agent_backtest_run", body, base_url=base_url, token=token,
        idempotency_key=new_idempotency_key(), timeout=timeout,
    )
    job_id = str(receipt.get("job_id") or receipt.get("jobId") or "")
    submit_billing = receipt.get("billing")
    if not job_id:
        raise LabError(EXIT_CONTRACT, "agent.jobIdMissing")
    reason = billing_contradiction(submit_billing)
    if reason:
        raise LabError(EXIT_CONTRACT, "billing.contradiction", reason=reason, jobId=job_id)
    deadline = min(budget.deadline, time.monotonic() + float(job_timeout))
    job = poll_job(
        "agent_job",
        job_id,
        base_url=base_url,
        token=token,
        deadline=deadline,
        timeout=timeout,
        fetch=lambda: agent_call("agent_job", base_url=base_url, token=token,
                                 path_values={"jobId": job_id})[0],
    )
    state = str(job.get("status") or "").lower()
    job_billing = job.get("billing")
    if state != "succeeded":
        raise LabError(EXIT_CONTRACT, "agent.jobNotSucceeded", jobId=job_id, status=state,
                       detail=_scrub(str(job.get("error") or ""))[:600])
    result = _as_dict(job.get("result"))
    run_id = int(result.get("runId") or 0)
    if run_id <= 0:
        raise LabError(EXIT_CONTRACT, "agent.runIdMissing", jobId=job_id)
    reason = billing_contradiction(job_billing)
    if reason:
        raise LabError(EXIT_CONTRACT, "billing.contradiction", reason=reason, jobId=job_id)
    return {
        "jobId": job_id,
        "status": state,
        "runId": run_id,
        "kind": str(receipt.get("kind") or ""),
        "createdAt": str(receipt.get("created_at") or ""),
        "idempotentReplay": replayed,
        "compileManifest": manifest,
        "metrics": {key: result[key] for key in AGENT_METRIC_KEYS if key in result},
        "context": {key: result[key] for key in AGENT_CONTEXT_KEYS if key in result},
        "sampledArrays": {key: len(value) for key, value in result.items()
                          if isinstance(value, (list, tuple))},
        "billing": submit_billing if submit_billing is not None else job_billing,
        "billingStatus": "present" if (
            submit_billing is not None or job_billing is not None) else "absent",
        "sourceAssociation": "none: agent channel has no sourceId/run read-back route",
        "unsupported": list(AGENT_UNSUPPORTED),
    }


class Budget:
    """In-process counters for wall clock, replay and persisted job budgets."""

    def __init__(
        self,
        *,
        wall_seconds: float = DEFAULT_WALL_SECONDS,
        max_evolution_runs: int = MAX_EVOLUTION_RUNS,
        max_relative_units: int = MAX_RELATIVE_UNITS,
        max_outer_jobs: int = MAX_OUTER_JOBS,
        max_groups: int = MAX_FULL_RECHECK_GROUPS,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.wall_seconds = float(wall_seconds)
        self.max_evolution_runs = int(max_evolution_runs)
        self.max_relative_units = int(max_relative_units)
        self.max_outer_jobs = int(max_outer_jobs)
        self.max_groups = int(max_groups)
        self._monotonic = monotonic_fn
        self.started = monotonic_fn()
        self.outer_jobs = self.groups = self.estimate_calls = 0
        self.shrinks = self.evolution_runs = 0
        self.internal_runs_reported: Optional[int] = None

    @property
    def deadline(self) -> float:
        return self.started + self.wall_seconds - RESERVE_SECONDS

    def remaining(self) -> float:
        return self.deadline - self._monotonic()

    def check(self) -> None:
        if self.remaining() <= 0:
            raise LabError(EXIT_BUDGET, "budget.wallClockExceeded")

    def take_outer_job(self) -> None:
        if self.outer_jobs >= self.max_outer_jobs:
            raise LabError(EXIT_BUDGET, "budget.outerJobsExceeded")
        self.outer_jobs += 1

    def take_group(self) -> None:
        if self.groups >= self.max_groups:
            raise LabError(EXIT_BUDGET, "budget.recheckGroupsExceeded")
        self.groups += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "wallSecondsLimit": self.wall_seconds,
            "wallSecondsRemaining": round(max(0.0, self.remaining()), 1),
            "outerBacktestJobs": self.outer_jobs,
            "outerBacktestJobLimit": self.max_outer_jobs,
            "fullPeriodGroups": self.groups,
            "fullPeriodGroupLimit": self.max_groups,
            "evolutionRuns": self.evolution_runs,
            "evolutionRunLimit": self.max_evolution_runs,
            "estimateCalls": self.estimate_calls,
            "estimateShrinks": self.shrinks,
            "relativeUnitsLimit": self.max_relative_units,
            "internalBacktestRunsReported": self.internal_runs_reported,
        }


def resolve_strategy_dir(raw: str, lab_root: Path = STRATEGIES_ROOT) -> Path:
    """Resolve a strategy directory and refuse any escape from the strategies root.

    Only direct children of ``skills/strategies/strategy-lab/strategies/`` are
    accepted; nested directories, anything outside that root and symlink
    escapes are refused.
    """
    candidate = Path(str(raw)).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    resolved = candidate.resolve()
    if resolved.parent != Path(lab_root).resolve():
        raise LabError(
            EXIT_USAGE, "strategyDir.outsideStrategiesRoot", path=_scrub(str(resolved.parent))
        )
    if not resolved.is_dir():
        raise LabError(EXIT_USAGE, "strategyDir.missing", path=_scrub(str(resolved)))
    for name in ("spec.md", "config.json", "strategy.py", "reports"):
        target = resolved / name
        if not target.resolve().is_relative_to(resolved):
            raise LabError(EXIT_USAGE, "strategyDir.symlinkEscape", name=name)
        if name != "reports" and not target.is_file():
            raise LabError(EXIT_USAGE, "strategyDir.fileMissing", name=name)
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(EXIT_USAGE, "file.unreadable", path=path.name) from exc
    if not isinstance(payload, dict):
        raise LabError(EXIT_USAGE, "file.notAnObject", path=path.name)
    return payload


def params_consumed(code: str, name: str) -> bool:
    """Return True when the strategy source really reads ``name`` from params."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get" and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "params" and node.args
        and isinstance(node.args[0], ast.Constant) and node.args[0].value == name
        for node in ast.walk(tree)
    )


def parse_bar_time(raw: Any) -> dt.datetime:
    """Parse a bar timestamp into UTC, handling seconds, milliseconds and ISO."""
    if isinstance(raw, bool):
        raise LabError(EXIT_CONTRACT, "bar.timeInvalid")
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        text = str(raw or "").strip()
        if not text:
            raise LabError(EXIT_CONTRACT, "bar.timeInvalid")
        if text.replace(".", "", 1).isdigit():
            value = float(text)
        else:
            try:
                parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise LabError(EXIT_CONTRACT, "bar.timeInvalid") from exc
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
    if not math.isfinite(value):
        raise LabError(EXIT_CONTRACT, "bar.timeInvalid")
    if abs(value) > 1e11:  # milliseconds
        value = value / 1000.0
    try:
        return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)
    except (ValueError, OverflowError, OSError) as exc:
        raise LabError(EXIT_CONTRACT, "bar.timeInvalid") from exc


def _normalize_bar(raw: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    try:
        moment = parse_bar_time(raw.get("time", raw.get("timestamp")))
    except LabError:
        return None
    values: dict[str, float] = {}
    for field in ("open", "high", "low", "close", "volume"):
        number = _finite(raw.get(field))
        if number is None:
            return None
        values[field] = number
    if values["close"] <= 0 or values["volume"] < 0:
        return None
    if not (
        values["high"] >= max(values["open"], values["close"], values["low"])
        and values["low"] <= min(values["open"], values["close"], values["high"])
    ):
        return None
    return {
        "time": int(moment.timestamp()),
        "timeUtc": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        **values,
    }


def fetch_klines(
    *,
    data_api: str = HUMAN,
    market: str = "USStock",
    symbol: str = "SPY",
    timeframe: str = "1D",
    start: Optional[str] = None,
    end: Optional[str] = None,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    max_pages: int = MAX_DATA_PAGES,
    request: Optional[Callable[..., Any]] = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Fetch standardised ascending OHLCV bars from the platform.

    ``data_api`` selects the Human or Agent market-data route explicitly; the
    function never switches entry point after an authentication error.
    """
    if data_api not in (HUMAN, AGENT):
        raise LabError(EXIT_USAGE, "dataApi.unsupported", value=data_api)
    if not base_url:
        raise LabError(EXIT_USAGE, "baseUrl.missing")
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= MAX_DATA_PAGES:
        raise LabError(EXIT_USAGE, "dataPages.outOfRange")
    if _finite(timeout) is None or timeout <= 0:
        raise LabError(EXIT_USAGE, "timeout.invalid")
    operation = "human_klines" if data_api == HUMAN else "agent_klines"
    page_limit = 1000 if data_api == HUMAN else 2000
    caller = request or call_data
    start_day = _parse_date(start, "start") if start else None
    end_day = _parse_date(end, "end") if end else None
    if start_day and end_day and start_day > end_day:
        raise LabError(EXIT_USAGE, "window.invalid")
    cursor = int(dt.datetime.combine(end_day + dt.timedelta(days=1), dt.time(),
                                    tzinfo=dt.timezone.utc).timestamp()) if end_day else None
    collected: dict[int, dict[str, Any]] = {}
    deadline = time.monotonic() + 180.0
    for _page in range(max_pages):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LabError(EXIT_BUDGET, "data.deadlineExceeded")
        params: dict[str, Any] = {
            "market": market, "symbol": symbol, "timeframe": timeframe, "limit": page_limit,
        }
        if cursor is not None:
            params["before_time"] = cursor
        data = caller(operation, base_url=base_url, token=token, params=params,
                      timeout=min(30.0, timeout, remaining))
        if time.monotonic() >= deadline:
            raise LabError(EXIT_BUDGET, "data.deadlineExceeded")
        rows = data.get("klines") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise LabError(EXIT_CONTRACT, "data.klinesInvalid")
        if not rows:
            break
        parsed = [_normalize_bar(row) for row in rows]
        if any(bar is None for bar in parsed):
            raise LabError(EXIT_EVIDENCE, "data.invalidBar")
        oldest = min(bar["time"] for bar in parsed)
        if cursor is not None and oldest >= cursor:
            break  # Repeated/empty pages stop without starting another request.
        for bar in parsed:
            moment = dt.datetime.fromtimestamp(bar["time"], tz=dt.timezone.utc).date()
            if (start_day and moment < start_day) or (end_day and moment > end_day):
                continue
            collected[bar["time"]] = bar
        cursor = oldest
        if start_day and dt.datetime.fromtimestamp(oldest, tz=dt.timezone.utc).date() <= start_day:
            break
    return [collected[key] for key in sorted(collected)]


def poll_job(
    operation: str,
    job_id: str,
    *,
    base_url: str,
    token: Optional[str],
    deadline: float,
    interval: float = POLL_INTERVAL_SECONDS,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
    timeout: float = 30.0,
    cancel_operation: Optional[str] = None,
    fetch: Optional[Callable[[], Any]] = None,
) -> dict[str, Any]:
    """Poll one job until it reaches a terminal state or the deadline passes.

    The monotonic deadline is checked *before* every network call and the
    HTTP timeout is capped by the remaining budget, so a poll can never
    outlive its own deadline.  On timeout only the known job id of this run
    is cancelled and read back; a cancelled job is never reported as
    "remote compute stopped".
    """
    cleanup_deadline = deadline + RESERVE_SECONDS
    while True:
        remaining = deadline - monotonic_fn()
        if remaining <= 0:
            cancel = _cancel_job(
                cancel_operation, job_id, base_url=base_url, token=token,
                timeout=timeout, read_operation=operation,
                cleanup_deadline=cleanup_deadline, monotonic_fn=monotonic_fn,
            )
            raise LabError(EXIT_BUDGET, "job.deadlineExceeded", jobId=job_id,
                           status="deadline", **cancel)
        if fetch is not None:
            data = _as_dict(fetch())
        else:
            status, payload = request_json(
                operation, base_url=base_url, token=token, path_values={"jobId": job_id},
                timeout=min(30.0, float(timeout), remaining),
            )
            data = _as_dict(parse_envelope(operation, status, payload))
        if monotonic_fn() < deadline and str(data.get("status") or "").lower() in TERMINAL_JOB_STATUS:
            return data
        remaining = deadline - monotonic_fn()
        if remaining > 0:
            sleep_fn(min(max(POLL_INTERVAL_SECONDS, interval), remaining))


def _cancel_job(
    cancel_operation: Optional[str],
    job_id: str,
    *,
    base_url: str,
    token: Optional[str],
    timeout: float = 30.0,
    read_operation: Optional[str] = None,
    cleanup_deadline: Optional[float] = None,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """One cancel and one precise GET within the reserved cleanup budget, never a loop."""
    end = cleanup_deadline if cleanup_deadline is not None else monotonic_fn() + RESERVE_SECONDS
    outcome = {"cancelRequested": "False", "readBackStatus": "cancel-unconfirmed",
               "remoteStopped": "unknown"}
    if not cancel_operation:
        return outcome
    remaining = end - monotonic_fn()
    if remaining > 0:
        try:
            call_data(cancel_operation, base_url=base_url, token=token,
                      path_values={"jobId": job_id}, timeout=min(timeout, remaining / 2))
            outcome["cancelRequested"] = "True"
        except LabError:
            pass  # A timed-out POST may still have taken effect: always try the precise GET.
    remaining = end - monotonic_fn()
    if read_operation and remaining > 0:
        try:
            data = _as_dict(call_data(read_operation, base_url=base_url, token=token,
                                     path_values={"jobId": job_id}, timeout=min(timeout, remaining)))
            outcome["readBackStatus"] = str(data.get("status") or "cancel-unconfirmed").lower()
        except LabError:
            pass
    return outcome


def compile_source(
    code: str, *, base_url: str, token: Optional[str], timeout: float = 30.0
) -> dict[str, Any]:
    """Compile the strategy source and return ``manifest`` plus range policy."""
    data = _as_dict(
        call_data(
            "compile_source",
            base_url=base_url,
            token=token,
            body={"code": code},
            timeout=timeout,
        )
    )
    manifest = _as_dict(data.get("manifest"))
    if not manifest:
        raise LabError(EXIT_CONTRACT, "compile.manifestMissing")
    return {
        "manifest": manifest,
        "backtestRangePolicy": _as_dict(data.get("backtestRangePolicy")),
    }


def _assert_source_matches(
    detail: dict[str, Any], *, code: str, name: str, manifest: dict[str, Any],
    source_id: int,
) -> None:
    expected = {"id": source_id, "code": code, "name": name, "visibility": "private",
                "status": "draft", "asset_type": "script"}
    problems = [key for key, value in expected.items() if detail.get(key) != value]
    if detail.get("user_id") in (None, ""):
        problems.append("owner")
    recorded = _as_dict(_as_dict(detail.get("metadata")).get("strategy_manifest"))
    if not recorded or any(recorded.get(key) != value for key, value in manifest.items()):
        problems.append("metadata.strategy_manifest")
    if not _as_list(_as_dict(detail.get("param_schema")).get("params")):
        problems.append("param_schema")
    if problems:
        raise LabError(EXIT_CONTRACT, "source.readbackMismatch", sourceId=source_id,
                       fields=",".join(problems))


def save_source(
    *,
    code: str,
    name: str,
    description: str,
    template_key: str,
    base_url: str,
    token: Optional[str],
    source_id: Optional[int] = None,
    timeout: float = 30.0,
    pre_create_check: Optional[Callable[[dict[str, Any], dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """Compile and validate before create; verify created and reused private sources."""
    compiled = compile_source(code, base_url=base_url, token=token, timeout=timeout)
    if pre_create_check is not None:
        pre_create_check(compiled["manifest"], compiled["backtestRangePolicy"])
    created = source_id is None
    if created:
        item = _as_dict(call_data(
            "create_source", base_url=base_url, token=token, timeout=timeout,
            body={"name": name, "code": code, "description": description,
                  "template_key": template_key, "asset_type": "script",
                  "visibility": "private", "status": "draft"},
        ))
        source_id = run_id_of(item)
    if not source_id or source_id <= 0:
        raise LabError(EXIT_CONTRACT, "source.createMissingId")
    for attempt in range(2):
        detail = _as_dict(call_data("source_detail", base_url=base_url, token=token,
                                   params={"id": source_id}, timeout=timeout))
        try:
            _assert_source_matches(detail, code=code, name=name,
                                   manifest=compiled["manifest"], source_id=source_id)
        except LabError:
            if attempt == 1:
                raise
        else:
            return {"sourceId": source_id, "detail": detail, "compile": compiled,
                    "created": created}
    raise LabError(EXIT_CONTRACT, "source.readbackMismatch")


def run_backtest(
    *,
    source_id: int,
    start: str,
    end: str,
    capital: float,
    commission: float,
    slippage: float,
    params: dict[str, Any],
    base_url: str,
    token: Optional[str],
    budget: Budget,
    job_timeout: float = BACKTEST_JOB_SECONDS,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Submit one persisted backtest job, poll it and read the run back.

    The read-back is verified against the submitted request: the run must
    belong to the same source and owner, and the platform's own record of
    window, cost and params must match what was requested.  A mismatch is a
    contract failure, never a silently accepted result.
    """
    budget.check()
    budget.take_outer_job()
    submitted = _as_dict(
        call_data(
            "backtest_submit",
            base_url=base_url,
            token=token,
            body={
                "sourceId": int(source_id),
                "startDate": start,
                "endDate": end,
                "initialCapital": float(capital),
                "commission": float(commission),
                "slippage": float(slippage),
                "leverageEnabled": False,
                "leverage": 1,
                "params": dict(params),
                "persist": True,
            },
            timeout=timeout,
        )
    )
    job_id = str(submitted.get("jobId") or "")
    if not job_id:
        raise LabError(EXIT_CONTRACT, "backtest.jobIdMissing")
    deadline = min(budget.deadline, time.monotonic() + float(job_timeout))
    job = poll_job(
        "backtest_job",
        job_id,
        base_url=base_url,
        token=token,
        deadline=deadline,
        timeout=timeout,
        cancel_operation="backtest_cancel",
    )
    state = str(job.get("status") or "").lower()
    if state != "succeeded":
        raise LabError(
            EXIT_CONTRACT,
            "backtest.jobNotSucceeded",
            jobId=job_id,
            status=state,
            detail=_scrub(str(job.get("error") or "")),
        )
    run_id = int(_as_dict(job.get("result")).get("runId") or 0)
    if run_id <= 0:
        raise LabError(EXIT_CONTRACT, "backtest.runIdMissing", jobId=job_id)
    run = _as_dict(call_data("backtest_get", base_url=base_url, token=token,
                             params={"runId": run_id}, timeout=timeout))
    if not run:
        raise LabError(EXIT_CONTRACT, "backtest.runReadbackEmpty", runId=run_id)
    if run_id_of(run) != run_id:
        raise LabError(EXIT_CONTRACT, "backtest.runIdMismatch", runId=run_id)
    if not _same_number(_as_dict(platform_run(run)).get("initial_capital"), capital):
        raise LabError(EXIT_CONTRACT, "backtest.capitalMismatch", runId=run_id)
    _verify_run_readback(
        run,
        source_id=int(source_id),
        start=start,
        end=end,
        commission=float(commission),
        slippage=float(slippage),
        params=dict(params),
    )
    history = call_data(
        "backtest_history",
        base_url=base_url,
        token=token,
        params={"sourceId": int(source_id), "limit": 50},
        timeout=timeout,
    )
    rows = history if isinstance(history, list) else _as_list(_as_dict(history).get("items"))
    if not any(int(row.get("id") or 0) == run_id for row in rows if isinstance(row, dict)):
        raise LabError(EXIT_CONTRACT, "backtest.historyMismatch", runId=run_id)
    return {
        "jobId": job_id,
        "runId": run_id,
        "run": run,
        "params": dict(params),
    }


def _verify_run_readback(
    run: dict[str, Any],
    *,
    source_id: int,
    start: str,
    end: str,
    commission: float,
    slippage: float,
    params: dict[str, Any],
) -> None:
    """Check the platform run record against the submitted request."""
    identity = run_identity(run)
    problems: list[str] = []
    run_source = identity.get("sourceId")
    if run_source is None:
        problems.append("sourceId")
    elif int(run_source) != int(source_id):
        problems.append("sourceId")
    if identity.get("owner") is None:
        problems.append("owner")
    if str(identity.get("startDate") or "") != str(start):
        problems.append("startDate")
    if str(identity.get("endDate") or "") != str(end):
        problems.append("endDate")
    if not _same_number(identity.get("commission"), commission):
        problems.append("commission")
    if not _same_number(identity.get("slippage"), slippage):
        problems.append("slippage")
    recorded = read_back_params(run)
    if not recorded or recorded != params:
        problems.append("params")
    if problems:
        raise LabError(
            EXIT_CONTRACT,
            "backtest.readbackMismatch",
            runId=run_id_of(run),
            fields=",".join(problems),
        )


def _shrink_plan(plan: dict[str, Any], attempt: int) -> dict[str, Any]:
    """Shrink trials first, then the declared numeric space. Folds stay 4."""
    config = dict(plan.get("config") or {})
    space = [dict(row) for row in _as_list(plan.get("parameterSpace"))]
    method = str(config.get("method") or "tpe").lower()
    if attempt == 0:
        minimum = 24 if method == "tpe" else 1
        config["trials"] = max(minimum, int(config.get("trials") or 1) // 2)
        return {"parameterSpace": space, "config": config}
    narrowed = []
    for row in space:
        low, high = _finite(row.get("min")), _finite(row.get("max"))
        step = _finite(row.get("step"))
        if low is None or high is None or step is None or high <= low:
            narrowed.append(row)
            continue
        span = high - low
        new_low, new_high = low + span * 0.25, high - span * 0.25
        if step > 0:
            new_low = low + step * math.ceil((new_low - low) / step)
            new_high = high - step * math.floor((high - new_high) / step)
        if new_high < new_low:
            new_low, new_high = low, high
        row["min"], row["max"] = new_low, new_high
        narrowed.append(row)
    return {"parameterSpace": narrowed, "config": config}


def estimate_evolution(
    *,
    parameter_space: list[dict[str, Any]],
    config: dict[str, Any],
    base_url: str,
    token: Optional[str],
    budget: Budget,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Estimate the replay budget and shrink the plan at most twice.

    The returned payload carries the *effective* plan (the possibly shrunk
    parameter space and config).  The caller must run exactly that plan; a
    small estimate paired with the original large plan is a contract
    violation.
    """
    plan = {"parameterSpace": parameter_space, "config": dict(config)}
    for attempt in range(3):
        budget.check()
        budget.estimate_calls += 1
        estimate = _as_dict(
            call_data(
                "evolution_estimate",
                base_url=base_url,
                token=token,
                body={**plan, "universeSize": 1},
                timeout=timeout,
            )
        )
        if not isinstance(estimate.get("backtestRuns"), int) or isinstance(
            estimate.get("backtestRuns"), bool
        ) or estimate["backtestRuns"] < 0:
            raise LabError(EXIT_CONTRACT, "estimate.payloadInvalid")
        runs = estimate["backtestRuns"]
        units = estimate.get("relativeUnits")
        if not isinstance(units, int) or isinstance(units, bool) or units < 0:
            raise LabError(EXIT_CONTRACT, "estimate.payloadInvalid")
        if runs <= budget.max_evolution_runs and units <= budget.max_relative_units:
            return {
                **estimate,
                "effectiveParameterSpace": plan["parameterSpace"],
                "effectiveConfig": plan["config"],
                "shrinks": budget.shrinks,
            }
        if attempt >= 2:
            raise LabError(
                EXIT_BUDGET,
                "estimate.overBudget",
                backtestRuns=runs,
                relativeUnits=units,
                limit=budget.max_evolution_runs,
            )
        budget.shrinks += 1
        plan = _shrink_plan(plan, attempt)
    raise LabError(EXIT_BUDGET, "estimate.overBudget")


def evolve_once(
    *,
    source_id: int,
    start: str,
    end: str,
    capital: float,
    commission: float,
    slippage: float,
    parameter_space: list[dict[str, Any]],
    config: dict[str, Any],
    base_url: str,
    token: Optional[str],
    budget: Budget,
    job_timeout: float = EVOLUTION_JOB_SECONDS,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Run exactly one bounded native evolution job and cross-check the list."""
    budget.check()
    if budget.evolution_runs >= 1:
        raise LabError(EXIT_BUDGET, "evolution.alreadySubmitted")
    budget.evolution_runs += 1
    submitted = _as_dict(
        call_data(
            "evolution_run",
            base_url=base_url,
            token=token,
            body={
                "sourceId": int(source_id),
                "startDate": start,
                "endDate": end,
                "initialCapital": float(capital),
                "commission": float(commission),
                "slippage": float(slippage),
                "leverageEnabled": False,
                "leverage": 1,
                "parameterSpace": parameter_space,
                "config": dict(config),
            },
            timeout=timeout,
        )
    )
    job_id = str(submitted.get("jobId") or "")
    if not job_id:
        raise LabError(EXIT_CONTRACT, "evolution.jobIdMissing")
    deadline = min(budget.deadline, time.monotonic() + float(job_timeout))
    job = poll_job(
        "evolution_job",
        job_id,
        base_url=base_url,
        token=token,
        deadline=deadline,
        timeout=timeout,
        cancel_operation="evolution_cancel",
    )
    state = str(job.get("status") or "").lower()
    if state != "succeeded":
        failure = _as_dict(_as_dict(job.get("progress")).get("failure"))
        budget.internal_runs_reported = failure.get("actualBacktestRuns")
        raise LabError(
            EXIT_CONTRACT,
            "evolution.jobNotSucceeded",
            jobId=job_id,
            status=state,
            messageKey=_scrub(str(failure.get("messageKey") or "")),
            dominantReason=_scrub(str(failure.get("dominantReason") or "")),
            actualBacktestRuns=failure.get("actualBacktestRuns"),
            reasonCounts=_safe_fields(failure.get("reasonCounts")),
        )
    result = _as_dict(job.get("result"))
    if not result:
        raise LabError(EXIT_CONTRACT, "evolution.resultMissing", jobId=job_id)
    if int(_as_dict(result.get("source")).get("id") or 0) != int(source_id):
        raise LabError(EXIT_CONTRACT, "evolution.sourceMismatch", jobId=job_id)
    listing = call_data(
        "evolution_jobs",
        base_url=base_url,
        token=token,
        params={"sourceId": int(source_id), "limit": 50},
        timeout=timeout,
    )
    items = listing.get("items") if isinstance(listing, dict) else listing
    if not any(
        str(_as_dict(item).get("jobId") or "") == job_id for item in _as_list(items)
    ):
        raise LabError(EXIT_CONTRACT, "evolution.listMismatch", jobId=job_id)
    budget.internal_runs_reported = _as_dict(result.get("summary")).get("actualBacktestRuns")
    actual = _finite(budget.internal_runs_reported)
    if actual is None or not actual.is_integer() or actual < 0:
        raise LabError(EXIT_EVIDENCE, "evolution.actualBudgetUnknown", jobId=job_id)
    if actual > budget.max_evolution_runs:
        raise LabError(EXIT_BUDGET, "evolution.actualOverBudget", jobId=job_id,
                       actualBacktestRuns=actual)
    return {"jobId": job_id, "result": result}


def _assumptions(run: Any) -> dict[str, Any]:
    assumptions = _result_of(run).get("executionAssumptions")
    return assumptions if isinstance(assumptions, dict) else {}


# Identity fields that must be present and comparable before two full-period
# runs may be ranked against each other (source, owner, window, cost, market).
IDENTITY_FIELDS = (
    "sourceId",
    "owner",
    "startDate",
    "endDate",
    "commission",
    "slippage",
    "market",
    "symbol",
    "timeframe",
)


def _first_value(sources: list[dict[str, Any]], *keys: str) -> Any:
    for key in keys:
        for source in sources:
            value = source.get(key)
            if value not in (None, ""):
                return value
    return None


def run_identity(run: Any) -> dict[str, Any]:
    """Return the comparable identity of a run row.

    Values are taken from the platform run row and, as a fallback, from the
    run's ``executionAssumptions``.  A field that the platform did not return
    stays ``None`` and is treated as *unknown* by the evaluator.
    """
    row = platform_run(run)
    assumptions = _assumptions(run)
    sources = [row, assumptions]
    identity = {
        "sourceId": _first_value(sources, "source_id", "sourceId"),
        "owner": _first_value(sources, "user_id", "userId"),
        "startDate": _first_value(sources, "start_date", "startDate"),
        "endDate": _first_value(sources, "end_date", "endDate"),
        "commission": _first_value(sources, "commission"),
        "slippage": _first_value(sources, "slippage"),
        "market": _first_value(sources, "market"),
        "symbol": _first_value(sources, "symbol"),
        "timeframe": _first_value(sources, "timeframe"),
    }
    identity["params"] = read_back_params(run)
    return identity


def _same_number(left: Any, right: Any) -> bool:
    left_value, right_value = _finite(left), _finite(right)
    if left_value is None or right_value is None:
        return False
    return abs(left_value - right_value) <= 1e-9


def evaluate_candidate(
    run: Any,
    *,
    max_drawdown_pct: float,
    baseline: Optional[Any] = None,
    expected_params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Check one full-period run against the hard constraints (three-valued).

    Missing metrics, identity or params are *unknown*, never zero, and any
    unknown that can change the conclusion outranks a plain failure.
    """
    checks: list[dict[str, str]] = []
    result = _result_of(run)
    provenance = result.get("dataProvenance")
    if not isinstance(provenance, dict) or str(provenance.get("kind") or "") != "market":
        checks.append(_check("dataProvenance", UNKNOWN, "missingOrNotRealMarketData"))
    else:
        checks.append(_check("dataProvenance", PASS, str(provenance.get("source") or "market")))
    assumptions = _assumptions(run)
    if "leverageEnabled" not in assumptions:
        checks.append(_check("leverageEnabled", UNKNOWN, "missing"))
    total_return = _finite(result.get("totalReturn"))
    sharpe = _finite(result.get("sharpeRatio"))
    drawdown = _finite(result.get("maxDrawdown"))

    if None in (total_return, sharpe, drawdown):
        checks.append(_check("metrics", UNKNOWN, "missingOrNonFinite"))
    else:
        checks.append(_check("metrics", PASS, "finite"))

    try:
        executions_value = int(result.get("totalExecutions"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        executions_value = None
    if executions_value is None:
        checks.append(_check("executions", UNKNOWN, "missing"))
    elif executions_value > 0:
        checks.append(_check("executions", PASS, str(executions_value)))
    else:
        checks.append(_check("executions", FAIL, "noExecutions"))

    if drawdown is None:
        checks.append(_check("drawdownSign", UNKNOWN, "missing"))
    elif drawdown <= 0:
        checks.append(_check("drawdownSign", PASS, f"{drawdown:.4f}"))
    else:
        checks.append(_check("drawdownSign", FAIL, "positiveDrawdown"))

    if drawdown is None:
        checks.append(_check("drawdownLimit", UNKNOWN, "missing"))
    elif -drawdown <= float(max_drawdown_pct) + 1e-9:
        checks.append(_check("drawdownLimit", PASS, f"{-drawdown:.4f}"))
    else:
        checks.append(_check("drawdownLimit", FAIL, f"{-drawdown:.4f}>{max_drawdown_pct}"))

    identity = run_identity(run)
    identity.pop("params", None)
    missing_identity = [field for field in IDENTITY_FIELDS if identity.get(field) is None]
    if missing_identity:
        checks.append(
            _check("identity", UNKNOWN, "missing:" + ",".join(missing_identity))
        )
    else:
        checks.append(_check("identity", PASS, "sourceOwnerWindowCostMarket"))

    effective_params = read_back_params(run)
    if not effective_params:
        checks.append(_check("params", UNKNOWN, "missing"))
    elif expected_params is not None:
        differing = sorted(
            name for name in expected_params.keys() | effective_params.keys()
            if name not in expected_params or name not in effective_params
            or expected_params[name] != effective_params[name]
        )
        # A parameter set that differs from the requested one is an evidence
        # inconsistency (Design §3.4: same-window/same-cost evidence only).
        # It stays UNKNOWN instead of a plain failure so the run is never
        # silently dropped while the conclusion is reported as "all known".
        checks.append(
            _check(
                "params",
                UNKNOWN if differing else PASS,
                ",".join(differing) if differing else "allRequestedParamsApplied",
            )
        )
    else:
        checks.append(_check("params", PASS, "asReadBack"))

    if baseline is not None:
        base_identity = run_identity(baseline)
        mismatched = [
            field
            for field in IDENTITY_FIELDS
            if base_identity.get(field) is None or identity.get(field) is None
            or (
                field in {"commission", "slippage"}
                and not _same_number(base_identity.get(field), identity.get(field))
            )
            or (
                field not in {"commission", "slippage"}
                and str(base_identity.get(field)) != str(identity.get(field))
            )
        ]
        checks.append(
            _check(
                "costAndWindow",
                UNKNOWN if mismatched else PASS,
                ",".join(mismatched) if mismatched else "sameWindowCostOwnerSource",
            )
        )

    assumptions = _assumptions(run)
    funding_mode = str(assumptions.get("fundingMode") or "")
    # Verified unlevered spot-equity identity, judged from read-back run
    # evidence: exchangeEquityProducts is only populated for crypto targets,
    # so a stock run is verified via market/symbol, market_type=spot and both
    # leverage flags instead.
    row = platform_run(run)
    if not assumptions:
        checks.append(_check("fundingAndExposure", UNKNOWN, "assumptionsMissing"))
    elif funding_mode and funding_mode != "not_modeled":
        checks.append(_check("fundingAndExposure", PASS, funding_mode))
    elif (
        funding_mode == "not_modeled"
        and identity.get("market") == "USStock" and identity.get("symbol") == "SPY"
        and str(row.get("market_type") or "").lower() == "spot"
        and assumptions.get("leverageEnabled") is False
        and _as_dict(row.get("manifest")).get("leverageAllowed") is False
    ):
        checks.append(_check("fundingAndExposure", PASS, "notApplicableSpotEquity"))
    else:
        checks.append(_check("fundingAndExposure", UNKNOWN, funding_mode or "unknown"))

    statuses = {item["status"] for item in checks}
    overall = UNKNOWN if UNKNOWN in statuses else (FAIL if FAIL in statuses else PASS)
    reasons = [
        f"{item['check']}:{item['status']}({item['detail']})"
        for item in checks
        if item["status"] != PASS
    ]
    return {
        "status": overall,
        "checks": checks,
        "reasons": reasons,
        "totalReturn": total_return,
        "maxDrawdown": drawdown,
        "sharpeRatio": sharpe,
    }


def _decision(
    classification: str,
    reason: str,
    base: dict[str, Any],
    evals: list[dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "classification": classification,
        "reason": reason,
        "baseline": base,
        "candidates": evals,
        "recommendation": None,
    }
    payload.update(extra)
    return payload


def select_candidate(
    baseline: Any,
    candidates: Iterable[Any],
    *,
    max_drawdown_pct: float,
    tolerance: float = 1e-8,
) -> dict[str, Any]:
    """Classify the baseline and candidates into one frozen business branch.

    ``baseline`` and every candidate may be a run wrapper
    (``{"runId", "run", "params"}``) or a bare platform run row; both are
    unwrapped through :func:`platform_run`.
    """
    base_eval = evaluate_candidate(
        baseline, max_drawdown_pct=max_drawdown_pct,
        expected_params=run_params(baseline) or None,
    )
    candidate_list = list(candidates)
    evaluations = [
        evaluate_candidate(
            item,
            max_drawdown_pct=max_drawdown_pct,
            baseline=baseline,
            expected_params=run_params(item) or None,
        )
        for item in candidate_list
    ]
    qualified = [
        (index, item, ev)
        for index, (item, ev) in enumerate(zip(candidate_list, evaluations))
        if ev["status"] == PASS
    ]
    unknown = [
        (index, item, ev)
        for index, (item, ev) in enumerate(zip(candidate_list, evaluations))
        if ev["status"] == UNKNOWN
    ]
    best: Optional[tuple[int, Any, dict[str, Any]]] = None
    for index, item, ev in qualified:
        value = ev["totalReturn"]
        if value is None:
            continue
        if best is None or value > (best[2]["totalReturn"] or 0.0):
            best = (index, item, ev)

    if base_eval["status"] == UNKNOWN:
        return _decision(
            "insufficient-evidence", "baselineEvidenceUnknown", base_eval, evaluations
        )
    if best is None:
        if unknown:
            return _decision(
                "insufficient-evidence", "candidateEvidenceUnknown", base_eval, evaluations
            )
        if base_eval["status"] == PASS:
            return _decision("baseline-kept", "noQualifiedCandidateBeatsBaseline",
                             base_eval, evaluations, recommendation="baseline",
                             recommendedParams=run_params(baseline))
        return _decision(
            "no-qualified-candidate", "allKnownAndFailed", base_eval, evaluations
        )
    for _index, item, _ev in unknown:
        value = _finite(_result_of(item).get("totalReturn"))
        best_value = best[2]["totalReturn"]
        if value is None or best_value is None or value >= best_value:
            return _decision(
                "insufficient-evidence", "unknownCandidateMayWin", base_eval, evaluations
            )
    if base_eval["status"] == PASS:
        base_value = base_eval["totalReturn"] or 0.0
        best_value = best[2]["totalReturn"] or 0.0
        if best_value <= base_value + tolerance:
            return _decision(
                "baseline-kept",
                "noQualifiedCandidateBeatsBaseline",
                base_eval,
                evaluations,
                recommendation="baseline",
                recommendedParams=run_params(baseline),
            )
    return _decision(
        "candidate",
        "qualifiedCandidateSelected",
        base_eval,
        evaluations,
        recommendation="candidate",
        recommendedParams=run_params(best[1]),
        selectedIndex=best[0],
    )


COMPARISON_COLUMNS = [
    "role",
    "runId",
    "params",
    "totalReturn",
    "annualizedReturn",
    "sharpeRatio",
    "maxDrawdown",
    "winRate",
    "totalTrades",
    "totalExecutions",
    "status",
    "reason",
]


def _comparison_row(
    role: str, run: dict[str, Any], evaluation: dict[str, Any]
) -> dict[str, Any]:
    result = _result_of(run)
    return {
        "role": role,
        "runId": run.get("runId"),
        "params": json.dumps(run.get("params") or {}, ensure_ascii=False, sort_keys=True),
        "totalReturn": result.get("totalReturn"),
        "annualizedReturn": result.get("annualizedReturn"),
        "sharpeRatio": result.get("sharpeRatio"),
        "maxDrawdown": result.get("maxDrawdown"),
        "winRate": result.get("winRate"),
        "totalTrades": result.get("totalTrades"),
        "totalExecutions": result.get("totalExecutions"),
        "status": evaluation.get("status"),
        "reason": ";".join(evaluation.get("reasons") or []) or "allChecksPassed",
    }


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _render_csv(rows: list[dict[str, Any]]) -> str:
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=COMPARISON_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in COMPARISON_COLUMNS})
    return handle.getvalue()


def _report_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        f"# {report.get('title') or 'Strategy Lab report'}",
        "",
        f"- generatedAt (UTC): {report.get('generatedAt') or _utc_now_iso()}",
        f"- classification: {report.get('classification') or 'unknown'}",
    ]
    if report.get("reason"):
        lines.append(f"- reason: {_scrub(str(report['reason']))}")
    for key, value in sorted(_as_dict(report.get("identifiers")).items()):
        if value in (None, "", [], {}):
            continue
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        lines.append(f"- {key}: {_scrub(rendered)}")
    for key in ("recommendedParams", "estimate"):
        if report.get(key):
            lines.append(
                f"- {key}: " + json.dumps(report[key], ensure_ascii=False, sort_keys=True)
            )
    lines.append("")
    if report.get("summary"):
        lines.extend(["## Summary", "", str(report["summary"]), ""])
    if report.get("checks"):
        lines.extend(["## Checks", ""])
        for item in _as_list(report["checks"]):
            if isinstance(item, dict):
                lines.append(
                    f"- {item.get('check')}: {item.get('status')} ({item.get('detail')})"
                )
            else:
                lines.append(f"- {item}")
        lines.append("")
    if report.get("budget"):
        lines.extend(["## Budget", ""])
        lines += [f"- {k}: {v}" for k, v in sorted(_as_dict(report["budget"]).items())]
        lines.append("")
    if report.get("notes"):
        lines.extend(["## Limitations and notes", ""])
        lines += [f"- {_scrub(str(item))}" for item in _as_list(report["notes"])]
        lines.append("")
    if report.get("commands"):
        lines.extend(["## Reproduction", ""])
        for item in _as_list(report["commands"]):
            lines.extend(["```text", _scrub(str(item)), "```", ""])
    return lines


def _safe_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _safe_fields(item) for key, item in value.items()
                if not re.search(r"(?i)token|password|secret|jwt|authorization|api.?key|headers|user.?id|owner", str(key))}
    if isinstance(value, (list, tuple)):
        return [_safe_fields(item) for item in value]
    if isinstance(value, str):
        return _scrub(value)
    return value


def write_report(
    strategy_dir: Path,
    *,
    report: dict[str, Any],
    comparison_rows: Optional[list[dict[str, Any]]] = None,
) -> tuple[Path, Path]:
    """Write ``reports/report.md`` and ``reports/comparison.csv``.

    Only explicitly selected business fields are serialised; no raw HTTP body,
    header, environment value or credential ever reaches the report.
    """
    strategy_dir = Path(strategy_dir).resolve()
    reports_dir = strategy_dir / "reports"
    report_path = reports_dir / "report.md"
    csv_path = reports_dir / "comparison.csv"
    for target in (reports_dir, report_path, csv_path,
                   report_path.with_suffix(".md.tmp"), csv_path.with_suffix(".csv.tmp")):
        if not target.resolve().is_relative_to(strategy_dir):
            raise LabError(EXIT_USAGE, "report.pathEscape")
    allowed = {"title", "generatedAt", "classification", "reason", "identifiers", "summary",
               "recommendedParams", "estimate", "checks", "budget", "notes", "commands"}
    safe_report = _safe_fields({key: value for key, value in report.items() if key in allowed})
    safe_report["identifiers"] = {key: value for key, value in safe_report.get("identifiers", {}).items()
                                  if key in {"sourceId", "baselineRunId", "finalRunId", "evolutionJobId", "runIds", "jobIds"}}
    rows = []
    for row in comparison_rows or []:
        safe_row = {key: value for key, value in row.items() if key in COMPARISON_COLUMNS}
        params = safe_row.get("params", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        safe_row["params"] = json.dumps(_safe_fields(params), sort_keys=True)
        rows.append(_safe_fields(safe_row))
    _atomic_write(report_path, _scrub("\n".join(_report_lines(safe_report))).rstrip() + "\n")
    _atomic_write(csv_path, _scrub(_render_csv(rows)))
    return report_path, csv_path


def _parse_date(value: str, label: str) -> dt.date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
        raise LabError(EXIT_USAGE, f"{label}.invalid")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise LabError(EXIT_USAGE, f"{label}.invalid") from exc


def _parse_search(spec: str) -> dict[str, Any]:
    parts = str(spec).split(":")
    if len(parts) != 4:
        raise LabError(EXIT_USAGE, "search.formatInvalid")
    low, high, step = (_finite(value) for value in parts[1:])
    if not parts[0].strip() or None in (low, high, step):
        raise LabError(EXIT_USAGE, "search.numberInvalid")
    if step <= 0 or low > high:
        raise LabError(EXIT_USAGE, "search.valueInvalid")
    return {"name": parts[0].strip(), "min": low, "max": high, "step": step}


def _numeric_parameter_row(
    name: str, declaration: dict[str, Any], low: float, high: float, step: float
) -> dict[str, Any]:
    kind = str(declaration.get("type") or "").lower()
    if kind not in {"integer", "number", "percent"}:
        raise LabError(EXIT_CONTRACT, "parameter.typeUnsupported", name=name)
    values = [_finite(value) for value in (low, high, step)]
    if None in values or values[2] <= 0 or values[0] > values[1]:
        raise LabError(EXIT_CONTRACT, "parameter.valueInvalid", name=name)
    if kind == "integer" and any(not value.is_integer() for value in values):
        raise LabError(EXIT_CONTRACT, "parameter.integerRequired", name=name)
    lower, upper = _finite(declaration.get("min")), _finite(declaration.get("max"))
    if lower is None or upper is None or low < lower or high > upper:
        raise LabError(EXIT_CONTRACT, "parameter.rangeOutsideDeclaration", name=name)
    return {"name": name, "type": kind,
            **dict(zip(("min", "max", "step"),
                       [int(value) if kind == "integer" else value for value in values]))}


def build_parameter_space(
    declared: list[dict[str, Any]],
    searches: list[dict[str, Any]],
    config_values: dict[str, Any],
    code: str,
) -> list[dict[str, Any]]:
    """Build only declared, consumed numeric rows, retaining fixed config values."""
    by_name = {str(row.get("name") or ""): row for row in declared if isinstance(row, dict)}
    by_search = {item["name"]: item for item in searches}
    if len(by_search) != len(searches):
        raise LabError(EXIT_USAGE, "parameter.duplicateSearch")
    rows = []
    for name in dict.fromkeys([*config_values, *by_search]):
        declaration = by_name.get(name)
        if declaration is None:
            raise LabError(EXIT_CONTRACT, "parameter.notDeclared", name=name)
        if not params_consumed(code, name):
            raise LabError(EXIT_CONTRACT, "parameter.notConsumed", name=name)
        search = by_search.get(name)
        if str(declaration.get("type")) not in {"integer", "number", "percent"}:
            if search or "default" not in declaration or config_values[name] != declaration["default"]:
                raise LabError(EXIT_CONTRACT, "parameter.fixedValueUnsupported", name=name)
            continue
        value = config_values.get(name, declaration.get("default"))
        _numeric_parameter_row(name, declaration, value, value, declaration.get("step", 1))
        if search:
            # The platform marks declared numeric parameters optimizable by
            # omission; only an explicit false withdraws the capability.
            if declaration.get("optimizable") is False:
                raise LabError(EXIT_CONTRACT, "parameter.notOptimizable", name=name)
            low, high, step = search["min"], search["max"], search["step"]
        else:
            low = high = value
            step = declaration.get("step", 1)
        rows.append(_numeric_parameter_row(name, declaration, low, high, step))
    if not rows:
        raise LabError(EXIT_CONTRACT, "parameter.spaceEmpty")
    return rows


def _evolution_config(args: argparse.Namespace) -> dict[str, Any]:
    method = str(args.method).lower()
    if method not in {"grid", "random", "tpe"}:
        raise LabError(EXIT_USAGE, "method.unsupported", value=method)
    for name, upper in (("trials", MAX_TRIALS), ("max_evolution_runs", MAX_EVOLUTION_RUNS),
                        ("max_relative_units", MAX_RELATIVE_UNITS)):
        value = _finite(getattr(args, name))
        if value is None or not value.is_integer() or not 1 <= value <= upper:
            raise LabError(EXIT_USAGE, f"{name}.outOfRange")
    if method == "tpe" and args.trials < 24:
        raise LabError(EXIT_USAGE, "trials.tooSmallForTpe")
    if args.folds != EVOLUTION_FOLDS:
        raise LabError(EXIT_USAGE, "folds.mustBeFour")
    wall = _finite(args.wall_seconds)
    if wall is None or not 0 < wall <= MAX_WALL_SECONDS or not wall.is_integer():
        raise LabError(EXIT_USAGE, "wallSeconds.outOfRange")
    return {"method": method, "trials": int(args.trials), "folds": EVOLUTION_FOLDS,
            "trainRatio": 0.7, "blindRatio": 0.15, "seed": 42, "costMultipliers": [1, 2],
            "autoPrune": False, "monteCarloPaths": 100, "topCandidates": MAX_TOP_CANDIDATES}


def _validate_trade_args(args: argparse.Namespace) -> None:
    if _parse_date(args.start, "start") > _parse_date(args.end, "end"):
        raise LabError(EXIT_USAGE, "window.invalid")
    for label in ("capital", "commission", "slippage", "max_drawdown_pct"):
        number = _finite(getattr(args, label))
        if number is None or (number <= 0 if label in {"capital", "max_drawdown_pct"}
                              else not 0 <= number < 1):
            raise LabError(EXIT_USAGE, f"{label}.invalid")
    if args.source_id < 0:
        raise LabError(EXIT_USAGE, "sourceId.invalid")
    if str(args.objective) != "totalReturn":
        raise LabError(EXIT_USAGE, "objective.unsupported", value=str(args.objective))


def _trade_command(args: argparse.Namespace) -> str:
    parts = [
        "PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py trade",
        f"--strategy-dir {args.strategy_dir}",
    ]
    # Reusing an existing source is part of the executed command; argparse
    # defaults --source-id to 0 (= create a new source) and must not appear.
    if args.source_id > 0:
        parts.append(f"--source-id {args.source_id}")
    parts += [
        f"--start {args.start}",
        f"--end {args.end}",
        f"--capital {args.capital}",
        f"--commission {args.commission}",
        f"--slippage {args.slippage}",
        f"--objective {args.objective}",
        f"--max-drawdown-pct {args.max_drawdown_pct}",
        f"--method {args.method}",
        f"--trials {args.trials}",
        f"--folds {args.folds}",
        f"--max-evolution-runs {args.max_evolution_runs}",
        f"--max-relative-units {args.max_relative_units}",
        f"--wall-seconds {args.wall_seconds}",
    ]
    parts += [f"--search {item}" for item in args.search or []]
    if args.skip_evolution:
        parts.append("--skip-evolution")
    return " ".join(parts)


def _check_manifest(
    manifest: dict[str, Any], range_policy: dict[str, Any], args: argparse.Namespace
) -> None:
    markets = [str(item) for item in _as_list(manifest.get("markets"))]
    if markets != ["USStock"]:
        raise LabError(EXIT_CONTRACT, "manifest.marketMismatch", markets=",".join(markets))
    frequency = str(manifest.get("drivingFrequency") or "")
    if frequency.lower() not in {"1d", "1day"}:
        raise LabError(EXIT_CONTRACT, "manifest.frequencyMismatch", value=frequency)
    direction = str(manifest.get("directionMode") or "")
    if direction.lower() not in {"long_only", "longonly"}:
        raise LabError(EXIT_CONTRACT, "manifest.directionMismatch", value=direction)
    maximum = _finite(range_policy.get("maxSelectedDays"))
    if maximum is None or maximum <= 0 or not maximum.is_integer():
        raise LabError(EXIT_CONTRACT, "backtestRange.unknown")
    days = (_parse_date(args.end, "end") - _parse_date(args.start, "start")).days + 1
    if days > maximum:
        raise LabError(EXIT_CONTRACT, "backtestRange.exceeded", days=days, limit=maximum)


def _collect_candidates(
    evolution_result: dict[str, Any], base_params: dict[str, Any]
) -> list[dict[str, Any]]:
    """Take up to four native top candidates, de-duplicated by full params.

    A candidate whose full parameter set equals the baseline is dropped: the
    already read-back baseline run is reused instead of spending another
    full-period backtest on identical parameters.
    """
    candidates: list[dict[str, Any]] = []
    seen: set[str] = {json.dumps(base_params, sort_keys=True, ensure_ascii=False)}
    for item in _as_list(evolution_result.get("topCandidates")):
        params = _as_dict(item).get("params")
        if not isinstance(params, dict) or not params:
            continue
        merged = {**base_params, **params}
        key = json.dumps(merged, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({"params": merged, "native": params})
        if len(candidates) >= MAX_TOP_CANDIDATES:
            break
    return candidates


def _backtest(
    *,
    params: dict[str, Any],
    source_id: int,
    args: argparse.Namespace,
    base_url: str,
    token: Optional[str],
    budget: Budget,
) -> dict[str, Any]:
    return run_backtest(
        source_id=source_id,
        start=args.start,
        end=args.end,
        capital=float(args.capital),
        commission=float(args.commission),
        slippage=float(args.slippage),
        params=params,
        base_url=base_url,
        token=token,
        budget=budget,
    )


def _prepare_source(
    *, code: str, args: argparse.Namespace, base_url: str, token: str
) -> dict[str, Any]:
    """Verify free capability, then compile and save the private source."""
    public = _as_dict(call_data("public_config", base_url=base_url, token=token))
    billing = public.get("billing_enabled")
    if billing is not False:
        raise LabError(EXIT_CONTRACT, "billing.notDisabled", value=str(billing))
    templates = call_data("script_templates", base_url=base_url, token=token)
    items = _as_dict(templates).get("items") if isinstance(templates, dict) else templates
    if not any(
        isinstance(item, dict)
        and str(item.get("template_key") or item.get("key") or "")
        == "strategy_v2_single_ma"
        for item in _as_list(items)
    ):
        raise LabError(EXIT_CONTRACT, "template.missing", template="strategy_v2_single_ma")
    return save_source(
        code=code,
        name=str(args.source_name or args.strategy_dir),
        description=str(args.description or "Strategy Lab sample"),
        template_key="strategy_v2_single_ma",
        base_url=base_url,
        token=token,
        source_id=int(args.source_id) if args.source_id else None,
        pre_create_check=lambda manifest, policy: _check_manifest(manifest, policy, args),
    )


def _evolve_and_decide(
    *,
    source_id: int,
    code: str,
    params: dict[str, Any],
    args: argparse.Namespace,
    searches: list[dict[str, Any]],
    evolution_config: dict[str, Any],
    base_url: str,
    token: str,
    budget: Budget,
    baseline_run: dict[str, Any],
    comparison_rows: list[dict[str, Any]],
    report: dict[str, Any],
) -> tuple[str, str, Optional[dict[str, Any]]]:
    """Run the bounded native evolution and classify baseline against candidates."""
    space_data = _as_dict(
        call_data(
            "evolution_parameter_space",
            base_url=base_url,
            token=token,
            params={"sourceId": source_id},
        )
    )
    declared = _as_list(space_data.get("parameters"))
    if (str(space_data.get("scope") or "") == "none" or not declared
            or not any(_as_dict(row).get("optimizable") is not False for row in declared)
            or not searches or all(item["min"] == item["max"] for item in searches)):
        report["notes"].append("Evolution skipped: no declared, requested variable parameters.")
        return "skipped", "noOptimizableSearch", None

    space_rows = build_parameter_space(declared, searches, params, code)
    estimate = estimate_evolution(
        parameter_space=space_rows,
        config=evolution_config,
        base_url=base_url,
        token=token,
        budget=budget,
    )
    effective_space = _as_list(estimate.get("effectiveParameterSpace")) or space_rows
    effective_config = _as_dict(estimate.get("effectiveConfig")) or evolution_config
    report["estimate"] = {
        "backtestRuns": estimate.get("backtestRuns"),
        "relativeUnits": estimate.get("relativeUnits"),
        "folds": estimate.get("folds"),
        "isUpperBound": estimate.get("isUpperBound"),
        "shrinks": estimate.get("shrinks"),
    }
    evolution = evolve_once(
        source_id=source_id,
        start=args.start,
        end=args.end,
        capital=float(args.capital),
        commission=float(args.commission),
        slippage=float(args.slippage),
        parameter_space=effective_space,
        config=effective_config,
        base_url=base_url,
        token=token,
        budget=budget,
    )
    report["identifiers"]["evolutionJobId"] = evolution["jobId"]
    candidates = _collect_candidates(evolution["result"], params)
    report["notes"].append("Native OOS/blind evidence: " + json.dumps(_safe_fields({
        "summary": evolution["result"].get("summary"),
        "selection": evolution["result"].get("selection"),
        "validation": evolution["result"].get("validation"),
    }), sort_keys=True))
    for candidate in candidates:
        budget.take_group()
        candidate["run"] = _backtest(
            params=candidate["params"],
            source_id=source_id,
            args=args,
            base_url=base_url,
            token=token,
            budget=budget,
        )
        report["identifiers"].setdefault("runIds", []).append(candidate["run"]["runId"])
        report["identifiers"].setdefault("jobIds", []).append(candidate["run"]["jobId"])
    decision = select_candidate(
        baseline_run,
        [item["run"] for item in candidates],
        max_drawdown_pct=float(args.max_drawdown_pct),
    )
    for candidate, evaluation in zip(candidates, decision["candidates"]):
        comparison_rows.append(_comparison_row("candidate", candidate["run"], evaluation))
    report["checks"] = [
        {
            "check": "baseline",
            "status": decision["baseline"]["status"],
            "detail": ";".join(decision["baseline"]["reasons"]) or "allChecksPassed",
        }
    ]
    recommendation: Optional[dict[str, Any]] = None
    if decision["recommendation"] == "candidate":
        recommendation = candidates[decision["selectedIndex"]]
    elif decision["recommendation"] == "baseline":
        recommendation = {"params": dict(params), "run": baseline_run}
    return decision["classification"], decision["reason"], recommendation


def run_trade(args: argparse.Namespace) -> int:
    """Execute the bounded trade flow; offline tests never submit real HTTP writes."""
    strategy_dir = resolve_strategy_dir(args.strategy_dir)
    code = (strategy_dir / "strategy.py").read_text(encoding="utf-8")
    params = _read_json(strategy_dir / "config.json")
    _validate_trade_args(args)
    evolution_config = _evolution_config(args)
    searches = [_parse_search(item) for item in (args.search or [])]
    if not params or any(isinstance(value, bool) or not isinstance(value, (int, float))
                         or _finite(value) is None for value in params.values()):
        raise LabError(EXIT_USAGE, "config.finiteNumericParamsRequired")
    base_url = os.environ.get("QUANTDINGER_BASE_URL") or ""
    token = os.environ.get("QUANTDINGER_JWT") or ""
    budget = Budget(wall_seconds=args.wall_seconds, max_evolution_runs=args.max_evolution_runs,
                    max_relative_units=args.max_relative_units)
    report: dict[str, Any] = {
        "title": f"{strategy_dir.name} trade report", "generatedAt": _utc_now_iso(),
        "classification": "failed", "identifiers": {}, "notes": [],
        "commands": [_trade_command(args)],
    }
    comparison_rows: list[dict[str, Any]] = []
    try:
        if not base_url:
            raise LabError(EXIT_USAGE, "baseUrl.missing")
        if not token:
            raise LabError(EXIT_AUTH, "auth.missing")
        budget.check()
        source = _prepare_source(code=code, args=args, base_url=base_url, token=token)
        source_id = int(source["sourceId"])
        report["identifiers"]["sourceId"] = source_id
        budget.take_group()  # The baseline is one of the five unique full-period groups.
        baseline_run = _backtest(params=params, source_id=source_id, args=args,
                                 base_url=base_url, token=token, budget=budget)
        if run_identity(baseline_run)["owner"] != source["detail"]["user_id"]:
            raise LabError(EXIT_EVIDENCE, "backtest.sourceOwnerMismatch")
        baseline_eval = evaluate_candidate(baseline_run, max_drawdown_pct=args.max_drawdown_pct,
                                           expected_params=params)
        report["identifiers"].update(baselineRunId=baseline_run["runId"],
                                     jobIds=[baseline_run["jobId"]])
        comparison_rows.append(_comparison_row("baseline", baseline_run, baseline_eval))
        recommendation = None
        if args.skip_evolution:
            classification, reason = "skipped", "userRequestedNoEvolution"
        else:
            classification, reason, recommendation = _evolve_and_decide(
                source_id=source_id, code=code, params=params, args=args, searches=searches,
                evolution_config=evolution_config, base_url=base_url, token=token,
                budget=budget, baseline_run=baseline_run, comparison_rows=comparison_rows,
                report=report,
            )
        if classification == "skipped" and baseline_eval["status"] != PASS:
            classification = "insufficient-evidence" if baseline_eval["status"] == UNKNOWN else "no-qualified-candidate"
            reason = "skippedButBaselineNotQualified"
        if recommendation is not None:
            final_params = dict(recommendation["params"])
            final_run = _backtest(params=final_params, source_id=source_id, args=args,
                                 base_url=base_url, token=token, budget=budget)
            final_eval = evaluate_candidate(final_run, max_drawdown_pct=args.max_drawdown_pct,
                                            baseline=baseline_run, expected_params=final_params)
            comparison_rows.append(_comparison_row("final", final_run, final_eval))
            if final_eval["status"] != PASS:
                raise LabError(EXIT_EVIDENCE, "finalRun.notConfirmed", runId=final_run["runId"])
            report["identifiers"]["finalRunId"] = final_run["runId"]
            report["identifiers"]["jobIds"].append(final_run["jobId"])
            report["recommendedParams"] = final_params
        report.update(classification=classification, reason=reason, budget=budget.snapshot())
        report["notes"] += [
            "Native summary.maxDrawdown is validation-fold mean, not the full-period MDD constraint.",
            "Folds reuse one replay sliced in time, not per-fold retraining; full-period selection leaves no untouched holdout.",
            "Source: QuantDinger full-period data.result; fundingMode=not_modeled is disclosed and only inapplicable for verified unlevered direct equity.",
            "Turnover and information ratio: not provided/verified; no fabricated zero values.",
        ]
        write_report(strategy_dir, report=report, comparison_rows=comparison_rows)
        return EXIT_BY_CLASSIFICATION.get(classification, EXIT_CONTRACT)
    except LabError as exc:
        report.update(classification="insufficient-evidence" if exc.exit_code == EXIT_EVIDENCE else "failed",
                      reason=exc.summary(), budget=budget.snapshot())
        report["notes"].append(f"Stopped before completion; final confirmation incomplete: {exc.summary()}")
        write_report(strategy_dir, report=report, comparison_rows=comparison_rows)
        raise


def _agent_report_lines(payload: dict[str, Any]) -> list[str]:
    """Render the Agent backtest receipt as a short markdown report."""
    lines = [
        "# Strategy Lab agent backtest report",
        "",
        f"- generatedAt (UTC): {_utc_now_iso()}",
        f"- jobId: {payload.get('jobId')}",
        f"- status: {payload.get('status')}",
        f"- runId: {payload.get('runId')}",
        f"- kind: {payload.get('kind')}",
        f"- idempotentReplay: {payload.get('idempotentReplay')}",
        f"- billing: {payload.get('billingStatus')}",
        f"- sourceAssociation: {payload.get('sourceAssociation')}",
        "",
        "## Metrics (Agent flat job result)",
        "",
    ]
    for key, value in sorted(_as_dict(payload.get("metrics")).items()):
        lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
    lines += ["", "## Server injected context", ""]
    for key, value in sorted(_as_dict(payload.get("context")).items()):
        lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
    lines += ["", "## Sampled arrays (gateway bounded sample, not the full series)", ""]
    for key, value in sorted(_as_dict(payload.get("sampledArrays")).items()):
        lines.append(f"- {key}: {value} elements")
    lines += ["", "## Notes", ""]
    lines += [
        "- Agent curve arrays are reported by length only; the gateway samples "
        "closedTrades/executions to <=1500 and equity/benchmark curves to <=1200.",
        "- The Agent channel has no sourceId/run read-back route; the persisted "
        "run's source_id is NULL by platform contract and is not a failure.",
        "- Unsupported on this channel: grid generate, Strategy Evolution, "
        "run/sourceId read-back, agent trading.",
    ]
    return lines


def run_agent_whoami(args: argparse.Namespace) -> int:
    """Print the Agent identity; the token never reaches the output."""
    base_url = os.environ.get("QUANTDINGER_BASE_URL") or ""
    if not base_url:
        raise LabError(EXIT_USAGE, "baseUrl.missing")
    token = resolve_agent_token()
    if not token:
        raise LabError(EXIT_AUTH, "auth.missing")
    identity = _as_dict(agent_call("agent_whoami", base_url=base_url, token=token)[0])
    if not identity.get("agent_name"):
        raise LabError(EXIT_CONTRACT, "agent.identityMissing")
    safe = {key: value for key, value in identity.items() if key != "user_id"}
    print(json.dumps(safe, ensure_ascii=False))
    return EXIT_OK


def run_agent_backtest(args: argparse.Namespace) -> int:
    """Compile, submit and read one Agent backtest job."""
    strategy_dir = resolve_strategy_dir(args.strategy_dir)
    code = (strategy_dir / "strategy.py").read_text(encoding="utf-8")
    params = _read_json(strategy_dir / "config.json")
    if not params or any(isinstance(value, bool) or not isinstance(value, (int, float))
                         or _finite(value) is None for value in params.values()):
        raise LabError(EXIT_USAGE, "config.finiteNumericParamsRequired")
    for label, value in (("capital", args.capital), ("commission", args.commission),
                         ("slippage", args.slippage)):
        if _finite(value) is None:
            raise LabError(EXIT_USAGE, f"{label}.invalid")
    base_url = os.environ.get("QUANTDINGER_BASE_URL") or ""
    if not base_url:
        raise LabError(EXIT_USAGE, "baseUrl.missing")
    token = resolve_agent_token()
    if not token:
        raise LabError(EXIT_AUTH, "auth.missing")
    payload = agent_backtest(
        code=code,
        params=params,
        start=args.start,
        end=args.end,
        capital=float(args.capital),
        commission=float(args.commission),
        slippage=float(args.slippage),
        base_url=base_url,
        token=token,
        budget=Budget(wall_seconds=args.wall_seconds),
    )
    report_path = strategy_dir / "reports" / "agent-backtest.md"
    if not report_path.resolve().is_relative_to(strategy_dir.resolve()):
        raise LabError(EXIT_USAGE, "report.pathEscape")
    _atomic_write(report_path,
                  _scrub("\n".join(_agent_report_lines(payload))).rstrip() + "\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quantdinger.py",
        description="Thin QuantDinger client for the Strategy Lab skill.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    trade = sub.add_parser("trade", help="Run one bounded native trade flow.")
    trade.add_argument("--strategy-dir", required=True)
    trade.add_argument("--source-id", type=int, default=0)
    trade.add_argument("--source-name", default="")
    trade.add_argument("--description", default="")
    trade.add_argument("--start", required=True)
    trade.add_argument("--end", required=True)
    trade.add_argument("--capital", type=float, required=True)
    trade.add_argument("--commission", type=float, required=True)
    trade.add_argument("--slippage", type=float, required=True)
    trade.add_argument("--search", action="append", default=[])
    trade.add_argument("--objective", default="totalReturn")
    trade.add_argument("--max-drawdown-pct", type=float, required=True)
    trade.add_argument("--skip-evolution", action="store_true")
    trade.add_argument("--method", default="grid")
    trade.add_argument("--trials", type=int, default=4)
    trade.add_argument("--folds", type=int, default=EVOLUTION_FOLDS)
    trade.add_argument("--max-evolution-runs", type=int, default=MAX_EVOLUTION_RUNS)
    trade.add_argument("--max-relative-units", type=int, default=MAX_RELATIVE_UNITS)
    trade.add_argument("--wall-seconds", type=float, default=DEFAULT_WALL_SECONDS)

    klines = sub.add_parser("fetch-klines", help="Fetch standardised OHLCV bars.")
    klines.add_argument("--data-api", choices=[HUMAN, AGENT], default=HUMAN)
    klines.add_argument("--market", default="USStock")
    klines.add_argument("--symbol", default="SPY")
    klines.add_argument("--timeframe", default="1D")
    klines.add_argument("--start", default="")
    klines.add_argument("--end", default="")
    klines.add_argument("--max-pages", type=int, default=MAX_DATA_PAGES)

    sub.add_parser("agent-whoami", help="Show the Agent identity and scopes.")

    backtest = sub.add_parser(
        "agent-backtest", help="Run one Agent backtest job (compile -> run -> read job)."
    )
    backtest.add_argument("--strategy-dir", required=True)
    backtest.add_argument("--start", required=True)
    backtest.add_argument("--end", required=True)
    backtest.add_argument("--capital", type=float, required=True)
    backtest.add_argument("--commission", type=float, required=True)
    backtest.add_argument("--slippage", type=float, required=True)
    backtest.add_argument("--wall-seconds", type=float, default=AGENT_WALL_SECONDS)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "trade":
            return run_trade(args)
        if args.command == "agent-whoami":
            return run_agent_whoami(args)
        if args.command == "agent-backtest":
            return run_agent_backtest(args)
        if args.command == "fetch-klines":
            base_url = os.environ.get("QUANTDINGER_BASE_URL") or ""
            token = (
                os.environ.get("QUANTDINGER_JWT")
                if args.data_api == HUMAN
                else resolve_agent_token()
            )
            if not base_url:
                raise LabError(EXIT_USAGE, "baseUrl.missing")
            bars = fetch_klines(
                data_api=args.data_api,
                market=args.market,
                symbol=args.symbol,
                timeframe=args.timeframe,
                start=args.start or None,
                end=args.end or None,
                base_url=base_url,
                token=token or None,
                max_pages=args.max_pages,
            )
            print(json.dumps({"count": len(bars), "klines": bars}, ensure_ascii=False))
            return EXIT_OK
    except LabError as exc:
        print(_scrub(exc.summary()), file=sys.stderr)
        return exc.exit_code
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
