"""T4 Preflight & Smoke report dataclasses.

DESIGN-03-014 §15.4.1 / §15.5.2 / §15.6.1 / §15.7.1.

All result types are ``frozen=True`` where possible so they can be
serialized and sanity-checked without mutation. The fields are
intentionally minimal — no raw secret values, no raw URIs, no raw
passwords, no per-record user data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# PR-0: Secret Source Audit (DESIGN §15.4.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecretProbeResult:
    """Boolean-only secret probe result (DESIGN §15.4.1)."""

    source_name: str
    file_exists: bool = False
    file_readable: bool | None = None
    key_declared: bool | None = None
    is_loadable: bool | None = None


@dataclass(frozen=True)
class SecretAuditResult:
    """Aggregate secret audit verdict (DESIGN §15.4.2).

    Internal-only carrier. Holds the full per-source / per-key
    probe detail used to derive the verdict, but **never** the
    values, lengths, URIs, or paths themselves
    (SecretProbeResult has no such fields — see §15.4.1).

    Per RFC-03-014-p3a-readonly-gate V0.2 §2.4 / SPEC §0 R1 锚定 2
    and DESIGN §4.4, this object **must not** reach any external
    serialization path (YAML / stdout / handoff). External
    serialization is performed exclusively via
    :class:`SecretAuditAggregate` below; :class:`SecretAuditResult`
    is kept for the internal verdict computation and the unit-test
    surface that exercises the boolean contract directly.
    """

    generated_at: str
    sources: tuple[SecretProbeResult, ...] = ()
    missing_keys: tuple[str, ...] = ()
    # Verdict: "authorized" / "conditional_authorized" / "unauthorized"
    status: str = "unauthorized"


# ---------------------------------------------------------------------------
# R1 aggregate-only external serialization (RFC V0.2 §2.4 裁定 2;
# SPEC §0 R1 锚定 2; DESIGN §4.4) — minimal carrier that carries the
# ONLY fields permitted to reach stdout / YAML / Kanban handoff.
# ---------------------------------------------------------------------------


#: Generic redacted error-class taxonomy (RFC V0.2 §5.1). The labels
#: are coarse, sanitized categories — never the underlying exception
#: type / message. Designers may add new categories, but they must
#: remain generic (no key names, no paths, no values). The literal
#: ``None`` sentinel is allowed to indicate "no error"; validators
#: normalise this to a missing key when materialising aggregates.
R1_REDACTED_ERROR_CLASSES: frozenset[str | None] = frozenset(
    {
        None,
        "file_missing",
        "file_unreadable",
        "key_undeclared",
        "env_unloadable",
        "key_invalid",  # coarse — covers port-not-int / db-not-tradingagents
        "io_error",
        "unknown",
    }
)

#: Generic source-kind taxonomy. Only the canonical
#: ``phase2_skills_env`` label and the catch-all
#: ``candidate_env_file`` are permitted (RFC V0.2 §5.1; SPEC
#: F-PR0-005). Never emit raw paths or filenames.
R1_SOURCE_KINDS: frozenset[str] = frozenset(
    {"phase2_skills_env", "candidate_env_file"}
)


@dataclass(frozen=True)
class SecretAuditAggregate:
    """External-only R1 aggregate verdict (RFC V0.2 §2.4 裁定 2).

    The ONLY fields permitted to reach stdout / YAML / handoff for
    PR-0. The structural shape deliberately excludes any per-source,
    per-key, per-path detail; reviewers cannot derive key names,
    declared/runtime state, password markers, paths, values,
    lengths, hashes, or URIs from an instance of this class.

    Designers must use :func:`reporter.secret_audit_to_yaml` (which
    routes through :class:`SecretAuditAggregate`) for any external
    evidence. Direct serialization of :class:`SecretAuditResult`
    would leak forbidden tokens and is disallowed by the V0.2 R1
    contract.
    """

    # Generic source-kind label (one of R1_SOURCE_KINDS). Never the
    # absolute path, never a per-source path.
    source_kind: str = "candidate_env_file"
    # Single aggregate verdict: authorized / conditional_authorized /
    # unauthorized.
    verdict: str = "unauthorized"
    # Generic redacted error-class label (one of
    # R1_REDACTED_ERROR_CLASSES, or None when no error). Never the
    # underlying exception class name or message detail.
    error_class: str | None = None
    # ISO 8601 timestamp generated at audit time (Asia/Shanghai).
    generated_at: str = ""


# ---------------------------------------------------------------------------
# PR-1: MongoDB Preflight (DESIGN §15.5.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MongoPreflightResult:
    """MongoDB zero-write preflight result (DESIGN §15.5.2).

    Internal-only carrier. Holds the full collection list returned
    by ``list_collection_names()`` so the caller can derive the
    baseline-presence and unexpected-presence booleans. The
    ``collections`` tuple **must not** reach any external
    serialization path (RFC V0.2 §2.4 裁定 1 / SPEC §0 R1 锚定 1):
    external evidence uses :class:`MongoPreflightAggregate` which
    emits only the designated baseline presence list.
    """

    # connectivity: "success" / "dns_failure" / "timeout" / "auth_failure"
    connectivity: str = "skipped"
    latency_ms: float | None = None
    collections: tuple[str, ...] | None = None
    p3_collections_found: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    # Optional positional details for diagnostic, but no secrets.
    detail: str | None = None


# ---------------------------------------------------------------------------
# R1 aggregate-only external serialization for PR-1
# (RFC V0.2 §2.4 裁定 1; SPEC §0 R1 锚定 1; DESIGN §5.5) — minimal
# carrier. Only the 3 designated baseline collections appear (by name)
# with a presence boolean; the full enumeration of ``list_collection_names()``
# is structurally excluded.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaselineCollectionPresence:
    """Per-baseline presence observation (DESIGN §5.5).

    The ``name`` is one of the three designated historical baseline
    collections (RFC V0.2 §2.4 裁定 1). Non-designated collection
    names must never appear in :class:`MongoPreflightAggregate`.
    """

    name: str
    present: bool


@dataclass(frozen=True)
class MongoPreflightAggregate:
    """External-only R1 aggregate for PR-1 (RFC V0.2 §2.4 裁定 1).

    The ONLY fields permitted to reach stdout / YAML / handoff for
    PR-1. The structural shape excludes the full collection
    enumeration returned by ``list_collection_names()``; reviewers
    cannot derive unrelated (non-designated) collection names from
    an instance of this class.
    """

    # Generic connectivity label — one of
    # success / dns_failure / timeout / auth_failure / env_missing / dry_run.
    # Never the underlying exception class name or message detail.
    connectivity: str = "dry_run"
    latency_ms: float | None = None
    # Presence observation for each of the three designated baseline
    # collections (DESIGN §5.5). At most 3 entries — the canonical
    # baseline names — never the raw ``collections`` tuple.
    baseline_collections: tuple[BaselineCollectionPresence, ...] = ()
    # Generic aggregate signal for any non-designated collection observed
    # by the internal preflight. The external contract deliberately carries
    # no collection name or free-form collection list.
    unexpected_presence: bool = False
    warnings: tuple[str, ...] = ()
    overall_verdict: str = "skipped"  # pass / conditional_pass / fail / unauthorized
    # ISO 8601 timestamp generated at preflight time (Asia/Shanghai).
    generated_at: str = ""


# ---------------------------------------------------------------------------
# PR-2/PR-3/PR-4: Provider Smoke (DESIGN §15.6.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SmokeCallResult:
    """Single AKShare call result (DESIGN §15.6.1)."""

    capability: str
    call_index: int
    # connectivity: "success" / "timeout" / "rate_limited" / "error" / "skipped"
    connectivity: str = "skipped"
    latency_ms: float | None = None
    raw_row_count: int | None = None
    actual_fields: tuple[str, ...] | None = None
    sample: tuple[dict[str, Any], ...] | None = None
    error: str | None = None
    # Deterministic error class label for fail-mode triage. Populated only
    # when ``connectivity`` is ``error`` / ``timeout`` / ``rate_limited``.
    # Values: "Timeout" / "ProxyError" / "ConnectionError" /
    # "RateLimited" / "Other" (None when ``connectivity`` is success /
    # skipped). See provider_client._one_call for the classification rules.
    error_class: str | None = None


# ---------------------------------------------------------------------------
# Six-section smoke report (SPEC §14.4.2 / DESIGN §15.7.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConnectionResult:
    status: str  # "success" / "failed"
    latency_ms: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class AuthResult:
    status: str  # "authorized" / "unauthorized"
    error: str | None = None


@dataclass(frozen=True)
class PermissionResult:
    status: str  # "ok" / "restricted"
    note: str | None = None


@dataclass(frozen=True)
class FieldMappingResult:
    total_expected_fields: int
    matched_fields: int
    missing_fields: tuple[str, ...] = ()
    extra_fields: tuple[str, ...] = ()
    type_mismatches: tuple[dict[str, str], ...] = ()

    @property
    def matched_ratio(self) -> float:
        if self.total_expected_fields == 0:
            return 0.0
        return self.matched_fields / self.total_expected_fields


@dataclass(frozen=True)
class DataSampleResult:
    row_count: int
    sample_rows: tuple[dict[str, Any], ...] = ()
    null_ratio: float = 0.0


@dataclass(frozen=True)
class FixtureDeviation:
    field: str
    fixture_type: str
    actual_type: str
    impact: str  # "low" / "medium" / "high"


@dataclass(frozen=True)
class FixtureDeviationResult:
    deviations: tuple[FixtureDeviation, ...] = ()


@dataclass(frozen=True)
class OverallVerdict:
    # "pass" / "conditional_pass" / "fail" / "unauthorized"
    verdict: str
    memo: str = ""


# ---------------------------------------------------------------------------
# Reporter ledger block (DESIGN §15.14.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerBlock:
    """Six-field reporter ledger (DESIGN §15.14.3 最小实现 / T3 X2).

    Captures the minimum accounting surface every smoke report must
    carry. The four ``*_count`` fields (``retry_count`` /
    ``fallback_count`` / ``mongo_calls`` / ``write_operations``) are
    fixed at ``0`` in the current no-retry / no-fallback /
    zero-write scope (DESIGN §15.5.3 / §15.9). ``worktree_changed``
    was removed by the 2026-07-26 T3 Implementer following Pascal's
    X2 minimum-scope direction — worktree probing stays opt-in via
    ``reporter.detect_worktree_changed`` and is NOT emitted by the
    smoke path. Empty-return semantics are conveyed through
    ``OverallVerdict.verdict`` / ``OverallVerdict.memo`` rather than
    a dedicated field.

    Attributes:
        provider_attempts: Number of provider attempts in this smoke
            (incl. retried calls — currently 1 per call because no
            retry is wired).
        actual_calls: Number of network round-trips actually issued.
        retry_count: 0 in the current scope (DESIGN §15.6.1).
        fallback_count: 0 in the current scope (no fallback wired).
        mongo_calls: 0 — query-path read-only.
        write_operations: 0 — zero-persistence-write (A-021 / §15.9).
    """

    provider_attempts: int = 0
    actual_calls: int = 0
    retry_count: int = 0
    fallback_count: int = 0
    mongo_calls: int = 0
    write_operations: int = 0


def _default_ledger() -> "LedgerBlock":
    """Build the default ``LedgerBlock`` used by ``SmokeReport``."""
    return LedgerBlock()


@dataclass(frozen=True)
class SmokeReport:
    """Standard smoke report (SPEC §14.4.2 / DESIGN §15.7.1)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    connectivity: ConnectionResult = field(default_factory=lambda: ConnectionResult("skipped"))
    auth: AuthResult = field(default_factory=lambda: AuthResult("skipped"))
    permissions: PermissionResult = field(default_factory=lambda: PermissionResult("skipped"))
    field_mapping: FieldMappingResult = field(
        default_factory=lambda: FieldMappingResult(total_expected_fields=0, matched_fields=0)
    )
    data_sample: DataSampleResult = field(
        default_factory=lambda: DataSampleResult(row_count=0)
    )
    vs_fixture: FixtureDeviationResult = field(default_factory=FixtureDeviationResult)
    overall: OverallVerdict = field(default_factory=lambda: OverallVerdict("skipped"))
    # DESIGN §15.14.3 ledger block. Carries the six-field accounting surface
    # (provider_attempts / actual_calls / retry_count / fallback_count /
    # mongo_calls / write_operations). Default empty block — callers
    # populate via ``LedgerBlock(...)``.
    ledger: "LedgerBlock" = field(  # type: ignore[name-defined]
        default_factory=lambda: _default_ledger()
    )


# ---------------------------------------------------------------------------
# MaterializeSpy result (DESIGN §15.9 / SPEC A-021)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaterializeSpyResult:
    """Observation of P3 read-path zero-write spy."""

    # Total number of `_materialize` calls observed on the patched router.
    observed_calls: int = 0
    # Did any of them reference a P3 capability?
    p3_materialize_observed: bool = False
    # True iff the spy observed zero P3 materialize calls.
    p3_readonly_verified: bool = True
