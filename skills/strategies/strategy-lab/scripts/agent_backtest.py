"""Agent backtest body and flow; all client dependencies are injected at call time.

Importing this module does not read business files, credentials or environment,
construct an HTTP client, or import the CLI in reverse.
"""

from __future__ import annotations

import json
import math
import time
from typing import Any, Callable, Optional

PLATFORM_MAX_LEVERAGE = 100

# Verdicts of the engine read-back against the requested execution facts.
READBACK_CONSISTENT = "consistent"
READBACK_MISMATCH = "mismatch"
READBACK_UNKNOWN = "unknown"
READBACK_FIELDS = ("initialCapital", "leverageEnabled", "leverage")


def _validate_leverage(
    enabled: bool,
    leverage: float,
    *,
    error_type: Callable[..., Exception],
    exit_usage: int,
) -> None:
    """Reject invalid leverage without coercion, clamping or remote calls."""
    if not isinstance(enabled, bool):
        raise error_type(exit_usage, "agent.leverageEnabledInvalid")
    if (isinstance(leverage, bool) or not isinstance(leverage, (int, float))
            or not 1 <= leverage <= PLATFORM_MAX_LEVERAGE or not math.isfinite(leverage)):
        raise error_type(exit_usage, "agent.leverageInvalid")
    if not enabled and leverage != 1:
        raise error_type(exit_usage, "agent.leverageDisabledConflict")


def build_agent_backtest_body(
    *,
    code: str,
    start: str,
    end: str,
    capital: float,
    commission: float,
    slippage: float,
    params: dict[str, Any],
    leverage_enabled: bool = False,
    leverage: float = 1,
    error_type: Callable[..., Exception],
    exit_usage: int,
    exit_contract: int,
    body_fields: tuple[str, ...],
) -> dict[str, Any]:
    """Build exactly the existing nine fields, preserving capital and params."""
    _validate_leverage(leverage_enabled, leverage, error_type=error_type, exit_usage=exit_usage)
    body = {
        "code": code,
        "startDate": start,
        "endDate": end,
        "initialCapital": float(capital),
        "commission": float(commission),
        "slippage": float(slippage),
        "leverageEnabled": leverage_enabled,
        "leverage": leverage,
        "params": dict(params),
    }
    if set(body) != set(body_fields):
        raise error_type(exit_contract, "agent.backtestFieldsMismatch")
    return body


def billing_contradiction(
    billing: Any, *, finite: Callable[[Any], Optional[float]],
) -> Optional[str]:
    """Return a reason when billing contradicts the closed-billing premise."""
    if not isinstance(billing, dict):
        return None
    if str(billing.get("status") or "").strip().lower() == "charged":
        return "billing.status=charged"
    charged = finite(billing.get("charged"))
    if charged is not None and charged > 0:
        return "billing.charged>0"
    return None


def _read_number(value: Any, finite: Callable[[Any], Optional[float]]) -> Optional[float]:
    """Return a finite number for a readable numeric field, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return finite(value)


def read_back_execution_facts(
    result: dict[str, Any],
    *,
    capital: float,
    leverage_enabled: bool,
    leverage: float,
    finite: Callable[[Any], Optional[float]],
) -> dict[str, Any]:
    """Compare the engine read-back with the requested execution facts.

    A field that is absent or cannot be read as a finite number / boolean
    stays UNKNOWN.  It is never back-filled from the request, so a missing
    read-back can never be reported as a consistent execution.
    """
    assumptions = result.get("executionAssumptions")
    assumptions = assumptions if isinstance(assumptions, dict) else {}
    requested = {
        "initialCapital": float(capital),
        "leverageEnabled": bool(leverage_enabled),
        "leverage": float(leverage),
    }
    read_back: dict[str, Any] = {}
    unknown: list[str] = []
    mismatches: list[str] = []

    value = _read_number(assumptions.get("initialCapital"), finite)
    if value is None:
        unknown.append("initialCapital")
    else:
        read_back["initialCapital"] = value
        if value != requested["initialCapital"]:
            mismatches.append("initialCapital")

    enabled = assumptions.get("leverageEnabled")
    if not isinstance(enabled, bool):
        unknown.append("leverageEnabled")
    else:
        read_back["leverageEnabled"] = enabled
        if enabled is not requested["leverageEnabled"]:
            mismatches.append("leverageEnabled")

    multiple = _read_number(assumptions.get("leverage"), finite)
    if multiple is None:
        unknown.append("leverage")
    else:
        read_back["leverage"] = multiple
        if multiple != requested["leverage"]:
            mismatches.append("leverage")

    if mismatches:
        verdict = READBACK_MISMATCH
    elif unknown:
        verdict = READBACK_UNKNOWN
    else:
        verdict = READBACK_CONSISTENT
    return {
        "verdict": verdict,
        "requested": requested,
        "readBack": read_back,
        "mismatches": mismatches,
        "unknownFields": unknown,
    }


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
    budget: Any,
    job_timeout: float = 180.0,
    timeout: float = 30.0,
    leverage_enabled: bool = False,
    leverage: float = 1,
    agent_submit: Callable[..., Any],
    agent_call: Callable[..., Any],
    poll_job: Callable[..., Any],
    new_idempotency_key: Callable[[], str],
    build_body: Callable[..., dict[str, Any]],
    check_billing: Callable[[Any], Optional[str]],
    error_type: Callable[..., Exception],
    exit_contract: int,
    exit_evidence: int = 3,
    as_dict: Callable[[Any], dict[str, Any]],
    scrub: Callable[[str], str],
    finite: Callable[[Any], Optional[float]],
    metric_keys: tuple[str, ...],
    context_keys: tuple[str, ...],
    unsupported: tuple[str, ...],
) -> dict[str, Any]:
    """Compile, submit and poll one job, preserving the flat Agent projection.

    Pure input checks precede even compile. Only a leveraged request requires
    explicit compile permission; legacy manifests remain valid at leverage 1.
    The engine read-back is checked after the job reached a terminal state:
    a contradiction with the request is a contract failure, a missing
    read-back is insufficient evidence and never back-filled from the request.
    """
    body = build_body(
        code=code, start=start, end=end, capital=capital, commission=commission,
        slippage=slippage, params=params, leverage_enabled=leverage_enabled, leverage=leverage,
    )
    budget.check()
    compiled, _ = agent_submit(
        "agent_compile", {"code": code}, base_url=base_url, token=token,
        idempotency_key=new_idempotency_key(), timeout=timeout,
    )
    manifest = as_dict(compiled.get("manifest"))
    if not manifest:
        raise error_type(exit_contract, "agent.manifestMissing")
    reason = check_billing(compiled.get("billing"))
    if reason:
        raise error_type(exit_contract, "billing.contradiction", reason=reason)
    if leverage > 1 and manifest.get("leverageAllowed") is not True:
        raise error_type(exit_contract, "agent.leverageNotAllowed")
    budget.take_outer_job()
    receipt, replayed = agent_submit(
        "agent_backtest_run", body, base_url=base_url, token=token,
        idempotency_key=new_idempotency_key(), timeout=timeout,
    )
    job_id = str(receipt.get("job_id") or receipt.get("jobId") or "")
    submit_billing = receipt.get("billing")
    if not job_id:
        raise error_type(exit_contract, "agent.jobIdMissing")
    reason = check_billing(submit_billing)
    if reason:
        raise error_type(exit_contract, "billing.contradiction", reason=reason, jobId=job_id)
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
        raise error_type(exit_contract, "agent.jobNotSucceeded", jobId=job_id, status=state,
                         detail=scrub(str(job.get("error") or ""))[:600])
    result = as_dict(job.get("result"))
    run_id = int(result.get("runId") or 0)
    if run_id <= 0:
        raise error_type(exit_contract, "agent.runIdMissing", jobId=job_id)
    reason = check_billing(job_billing)
    if reason:
        raise error_type(exit_contract, "billing.contradiction", reason=reason, jobId=job_id)
    read_back = read_back_execution_facts(
        result,
        capital=capital,
        leverage_enabled=leverage_enabled,
        leverage=leverage,
        finite=finite,
    )
    if read_back["verdict"] == READBACK_MISMATCH:
        raise error_type(
            exit_contract, "agent.leverageReadbackMismatch", jobId=job_id,
            mismatches=",".join(read_back["mismatches"]),
            readBack=scrub(json.dumps(read_back["readBack"], ensure_ascii=False,
                                       sort_keys=True))[:600],
        )
    if read_back["verdict"] == READBACK_UNKNOWN:
        raise error_type(
            exit_evidence, "agent.executionReadbackUnknown", jobId=job_id,
            unknownFields=",".join(read_back["unknownFields"]),
            readBack=scrub(json.dumps(read_back["readBack"], ensure_ascii=False,
                                       sort_keys=True))[:600],
        )
    return {
        "jobId": job_id,
        "status": state,
        "runId": run_id,
        "kind": str(receipt.get("kind") or ""),
        "createdAt": str(receipt.get("created_at") or ""),
        "idempotentReplay": replayed,
        "compileManifest": manifest,
        "metrics": {key: result[key] for key in metric_keys if key in result},
        "context": {key: result[key] for key in context_keys if key in result},
        "sampledArrays": {key: len(value) for key, value in result.items()
                          if isinstance(value, (list, tuple))},
        "billing": submit_billing if submit_billing is not None else job_billing,
        "billingStatus": "present" if (
            submit_billing is not None or job_billing is not None) else "absent",
        "sourceAssociation": "none: agent channel has no sourceId/run read-back route",
        "executionReadBack": read_back,
        "unsupported": list(unsupported),
    }
