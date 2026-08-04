"""T4 Preflight report serialization with sanitization.

DESIGN-03-014 §15.7.2 (Sanitizer rules).

Implementation notes
--------------------

The YQuant project treats PyYAML as an *optional* dependency (used
lazily by ``scripts/upgrade/*.py``). T4 toolchain cannot introduce a
new required dependency, so this module provides a **minimal YAML
serializer** that supports the exact structures the smoke reports
contain (dicts, lists, strings, numbers, booleans, None, datetimes).

The serializer deliberately does NOT aim to be a full YAML 1.2
implementation — it is bounded to:

* ``dict`` → block style mapping
* ``list`` → block style sequence
* ``str`` / ``int`` / ``float`` / ``bool`` / ``None`` → scalar
* ``datetime`` / ``date`` → ISO 8601

It is paired with a thin ``yaml_parse`` shim so tests can use the
``yaml`` module when present (preferred), or fall back to a
constrained parser. Tests in this toolchain always pass through the
serializer for output and the parser (when PyYAML is present) for
verification.

Sanitizer rules (DESIGN §15.7.2) are applied to ALL scalar values
BEFORE serialization. A raw secret value can never reach the output
even if the caller forgot to scrub it.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .config import (
    P3_BUSINESS_COLLECTIONS,
    SANITIZER_MAX_LIST_LENGTH,
    SANITIZER_MAX_STRING_LENGTH,
)
from .models import (
    ConnectionResult,
    AuthResult,
    LedgerBlock,
    PermissionResult,
    FieldMappingResult,
    DataSampleResult,
    FixtureDeviationResult,
    OverallVerdict,
    SecretAuditAggregate,
    SecretAuditResult,
    SecretProbeResult,
    SmokeReport,
    MongoPreflightAggregate,
    BaselineCollectionPresence,
)

# ---------------------------------------------------------------------------
# Sanitizer
# ---------------------------------------------------------------------------

#: Patterns that mark a value as "secret-shaped" and must be redacted
#: (DESIGN §15.7.2 Sanitizer rules). Order matters; first match wins.
#: Case-insensitive substring match.
#:
#: The Sanitizer uses **generic secret-shaped patterns**, not a single
#: canonical T4 key. Phase 2 introduced the five ``MONGODB_*`` keys
#: (handled at the resolver layer) and dropped the legacy single-key
#: contract (``MONGO_URI`` / ``AKSHARE_TOKEN``). Any scalar value whose
#: text contains a URI prefix, ``password``/``passwd``/``secret``,
#: ``token``/``api_key``/``apikey``, or the legacy ``MONGO_URI=`` /
#: ``MONGO_URI:`` form is redacted regardless of its field name; see
#: DESIGN §15.7.2 and SPEC §14.3.
_SECRET_PATTERNS: tuple[str, ...] = (
    "mongodb://",
    "mongodb+srv://",
    "https://",
    "http://",
    "MONGO_URI=",
    "MONGO_URI:",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "secret",
    "token",
    "credential",
)

#: Field name substrings that mark a value as never-to-emit (drop entirely).
#: Generic secret-shaped names; NOT a single canonical key.
_SECRET_FIELD_NAMES: tuple[str, ...] = (
    "value",
    "password",
    "passwd",
    "secret",
    "raw_secret",
    "token",
    "credential",
    "apikey",
    "api_key",
)


def _is_secret_shaped(s: str) -> bool:
    """Return True if the string looks like a secret value (DESIGN §15.7.2)."""
    lo = s.lower()
    return any(pat.lower() in lo for pat in _SECRET_PATTERNS)


def _truncate_string(s: str) -> str:
    """Truncate long strings (DESIGN §15.7.2)."""
    if len(s) <= SANITIZER_MAX_STRING_LENGTH:
        return s
    return f"{s[:SANITIZER_MAX_STRING_LENGTH]}... ({len(s)} chars truncated)"


def _truncate_list(items: list[Any]) -> list[Any]:
    """Truncate large lists (DESIGN §15.7.2)."""
    if len(items) <= SANITIZER_MAX_LIST_LENGTH:
        return items
    return [*items[:SANITIZER_MAX_LIST_LENGTH], f"(and {len(items) - SANITIZER_MAX_LIST_LENGTH} more)"]


def _scrub_scalar(value: Any, *, field_name: str | None = None) -> Any:
    """Sanitize a single scalar value (DESIGN §15.7.2).

    Order:
    1. If ``field_name`` matches a forbidden name → ``[REDACTED]``.
    2. If the value is a string that looks secret-shaped → ``[REDACTED]``.
    3. If the value is a string longer than the cap → truncate.
    4. Otherwise → return as-is (caller handles type conversion).
    """
    if field_name is not None:
        lo = field_name.lower()
        if any(name in lo for name in _SECRET_FIELD_NAMES):
            return "[REDACTED]"

    if isinstance(value, str):
        if _is_secret_shaped(value):
            return "[REDACTED]"
        return _truncate_string(value)
    return value


def _scrub_container(
    value: Any,
    *,
    field_name: str | None = None,
    _seen: set[int] | None = None,
) -> Any:
    """Recursively scrub a container (dict / list / scalar)."""
    if _seen is None:
        _seen = set()
    if id(value) in _seen:
        # Cycle protection: emit a stable placeholder.
        return "<cycle>"
    if isinstance(value, dict):
        _seen.add(id(value))
        return {
            str(k): _scrub_container(v, field_name=str(k), _seen=_seen)
            for k, v in value.items()
        }
    if isinstance(value, list):
        _seen.add(id(value))
        scrubbed = [_scrub_container(v, field_name=field_name, _seen=_seen) for v in value]
        return _truncate_list(scrubbed)
    if isinstance(value, tuple):
        _seen.add(id(value))
        scrubbed = tuple(
            _scrub_container(v, field_name=field_name, _seen=_seen) for v in value
        )
        # Tuple → list for serialization.
        return _truncate_list(list(scrubbed))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return _scrub_scalar(value, field_name=field_name)


def sanitize(value: Any) -> Any:
    """Public entry point: recursively sanitize any value."""
    return _scrub_container(value)


# ---------------------------------------------------------------------------
# YAML serializer (no external dependency)
# ---------------------------------------------------------------------------


def _yaml_scalar(v: Any) -> str:
    """Convert a scalar to a YAML scalar string. Quotes when needed."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return _yaml_quote(v)
    raise TypeError(f"unsupported scalar type: {type(v).__name__}")


_NEEDS_QUOTING = re.compile(r"[#:&*!|>%@`,{}\[\]\n\r\t]|^\s|\s$|^-|^--|^---?$|^\?|^:")


def _yaml_quote(s: str) -> str:
    """Quote a string for YAML. Use double-quote style with escapes."""
    if s == "":
        return '""'
    if not _NEEDS_QUOTING.search(s) and s.lower() not in {"null", "true", "false", "yes", "no", "on", "off"}:
        # safe to leave unquoted
        # reject if first/last char would confuse parser
        if s[:1].isdigit() and s.replace(".", "").replace("-", "").isdigit() is False:
            return f'"{s}"'
        return s
    # double-quote with backslash escapes for " and \
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f'"{escaped}"'


def _yaml_dump(data: Any, indent: int = 0) -> str:
    """Render a Python value as YAML."""
    spc = "  " * indent
    if isinstance(data, dict):
        if not data:
            return f"{spc}{{}}\n"
        out: list[str] = []
        for k, v in data.items():
            key_str = _yaml_quote(str(k))
            if isinstance(v, dict):
                if not v:
                    out.append(f"{spc}{key_str}: {{}}\n")
                else:
                    out.append(f"{spc}{key_str}:\n")
                    out.append(_yaml_dump(v, indent + 1))
            elif isinstance(v, list):
                if not v:
                    out.append(f"{spc}{key_str}: []\n")
                else:
                    out.append(_yaml_dump_list(v, key_str, indent))
            else:
                out.append(f"{spc}{key_str}: {_yaml_scalar(v)}\n")
        return "".join(out)
    if isinstance(data, list):
        if not data:
            return f"{spc}[]\n"
        return _yaml_dump_list(data, None, indent)
    return f"{spc}{_yaml_scalar(data)}\n"


def _yaml_dump_list(data: list[Any], key_str: str | None, indent: int) -> str:
    """Render a list, optionally under a mapping key."""
    spc = "  " * indent
    out: list[str] = []
    head = f"{spc}{key_str}:\n" if key_str is not None else ""
    for i, v in enumerate(data):
        prefix = head if key_str is not None and i == 0 else ""
        if prefix:
            out.append(prefix)
        if isinstance(v, dict):
            if not v:
                out.append(f"{spc}- {{}}\n")
            else:
                items = list(v.items())
                out.append(f"{spc}- {_yaml_quote(str(items[0][0]))}: {_yaml_scalar(items[0][1])}\n")
                for k, vv in items[1:]:
                    if isinstance(vv, dict):
                        if not vv:
                            out.append(f"{spc}  {_yaml_quote(str(k))}: {{}}\n")
                        else:
                            out.append(f"{spc}  {_yaml_quote(str(k))}:\n")
                            out.append(_yaml_dump(vv, indent + 2))
                    elif isinstance(vv, list):
                        if not vv:
                            out.append(f"{spc}  {_yaml_quote(str(k))}: []\n")
                        else:
                            out.append(_yaml_dump_list(vv, _yaml_quote(str(k)), indent + 1))
                    else:
                        out.append(f"{spc}  {_yaml_quote(str(k))}: {_yaml_scalar(vv)}\n")
        elif isinstance(v, list):
            if not v:
                out.append(f"{spc}- []\n")
            else:
                out.append(f"{spc}-\n")
                out.append(_yaml_dump(v, indent + 1))
        else:
            out.append(f"{spc}- {_yaml_scalar(v)}\n")
    return "".join(out)


# ---------------------------------------------------------------------------
# To-dict conversion (dataclass → plain dict for serialization)
# ---------------------------------------------------------------------------


def _dataclass_to_dict(obj: Any) -> Any:
    """Convert dataclass → dict, recursing into nested dataclasses / tuples."""
    from dataclasses import asdict, is_dataclass

    if is_dataclass(obj) and not isinstance(obj, type):
        d = asdict(obj)
        return _convert(d)
    return _convert(obj)


# ---------------------------------------------------------------------------
# Worktree-change detection helper (DESIGN §15.14.3)
# ---------------------------------------------------------------------------


def detect_worktree_changed(*, cwd: str | None = None) -> bool:
    """Return ``True`` iff the working tree has uncommitted changes.

    DESIGN §15.14.3 row 2710 specifies the detection rule:
    ``subprocess.run(["git", "diff", "--quiet"])``. Exit 0 → clean
    (``False``); exit != 0 → dirty (``True``). This is a pure shell
    probe — never touches the database, never mutates the working
    tree, never writes a file. Falls back to ``False`` when ``git`` is
    missing / the call errors out so the smoke report can still be
    emitted.

    IMPORTANT (T3 X2 scope): This helper is **opt-in**. It is NOT
    invoked by ``smoke_report_to_yaml`` itself; the reporter renders
    six ledger fields and does not touch worktree state. Per
    Pascal's 2026-07-26 X2 direction, smoke flows under X2 do not
    call this function — they construct ``LedgerBlock(...)`` with
    only the six documented accounting fields so the dry-run path
    emits zero subprocess side-effects. The helper remains available
    for future Pascal-authorised live-read
    flows that legitimately need the probe.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode != 0


def _convert(value: Any) -> Any:
    """Convert tuples to lists recursively (YAML serializer prefers lists)."""
    if isinstance(value, dict):
        return {str(k): _convert(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_convert(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Public serialization API
# ---------------------------------------------------------------------------


def to_yaml(obj: Any) -> str:
    """Serialize a report dataclass (or any sanitizable value) to YAML.

    The input is sanitized FIRST, then serialized. The serializer never
    re-emits raw secret values.
    """
    sanitized = sanitize(_dataclass_to_dict(obj))
    return _yaml_dump(sanitized)


def yaml_parse(text: str) -> Any:
    """Parse YAML text using PyYAML when present, else a constrained fallback.

    The fallback parser only supports the small subset of YAML this
    toolchain emits (block-style mapping / sequence / scalars). PyYAML
    is preferred when available for full compatibility.
    """
    try:
        import yaml  # type: ignore
    except ImportError:
        return _fallback_parse(text)
    return yaml.safe_load(text)  # type: ignore


def _fallback_parse(text: str) -> Any:
    """Parse the bounded block-style YAML subset emitted by ``_yaml_dump``."""
    lines = _strip_yaml_lines(text)
    if not lines:
        return None

    def coerce(value: str) -> Any:
        value = value.strip()
        if value in ("", "null", "~"):
            return None
        if value in ("true", "yes", "on"):
            return True
        if value in ("false", "no", "off"):
            return False
        if value == "{}":
            return {}
        if value == "[]":
            return []
        if value.startswith('"') and value.endswith('"'):
            import json
            return json.loads(value)
        if value.startswith("'") and value.endswith("'"):
            return value[1:-1]
        try:
            return float(value) if any(c in value for c in ".eE") else int(value)
        except ValueError:
            return value

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        is_list = lines[index][1] == "-" or lines[index][1].startswith("- ")
        container: Any = [] if is_list else {}
        while index < len(lines):
            current_indent, content = lines[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError("invalid indentation in fallback YAML")
            if is_list:
                if not (content == "-" or content.startswith("- ")):
                    break
                rest = content[1:].strip()
                if not rest:
                    item, index = parse_block(index + 1, lines[index + 1][0])
                    container.append(item)
                    continue
                if ":" in rest:
                    key, value = (part.strip() for part in rest.split(":", 1))
                    item = {key: coerce(value)}
                    index += 1
                    while index < len(lines) and lines[index][0] > indent:
                        child_indent, child = lines[index]
                        child_key, child_value = (part.strip() for part in child.split(":", 1))
                        if child_value:
                            item[child_key] = coerce(child_value)
                            index += 1
                        else:
                            nested, index = parse_block(index + 1, lines[index + 1][0])
                            item[child_key] = nested
                    container.append(item)
                    continue
                container.append(coerce(rest))
                index += 1
                continue
            if content.startswith("-"):
                break
            key, value = (part.strip() for part in content.split(":", 1))
            index += 1
            if value:
                container[key] = coerce(value)
            elif index < len(lines) and (
                lines[index][0] > indent
                or lines[index][1] == "-"
                or lines[index][1].startswith("- ")
            ):
                container[key], index = parse_block(index, lines[index][0])
            else:
                container[key] = {}
        return container, index

    return parse_block(0, lines[0][0])[0]


def _strip_yaml_lines(text: str) -> list[tuple[int, str]]:
    """Strip a YAML text into (indent, content) lines, ignoring comments."""
    out: list[tuple[int, str]] = []
    for raw in text.splitlines():
        # strip comments (only after whitespace; simple heuristic)
        if raw.strip().startswith("#"):
            continue
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        out.append((indent, raw.strip()))
    return out


# Self-test for the YAML serializer + parser.
if __name__ == "__main__":
    obj = {
        "capability": "sector.snapshot",
        "provider": "akshare",
        "date_range": ["2026-07-20", "2026-07-22"],
        "connectivity": {"status": "success", "latency_ms": 120},
        "data_sample": {"row_count": 5, "sample_rows": [{"a": 1, "b": 2}]},
    }
    out = to_yaml(obj)
    print("YAML output:\n", out)
    parsed = yaml_parse(out)
    print("Parsed back:\n", parsed)
    assert parsed == obj, f"roundtrip failed: {parsed}"
    print("Roundtrip OK")


def secret_audit_to_yaml(result: SecretAuditResult) -> str:
    """R1 aggregate-only serialization of a :class:`SecretAuditResult`.

    Per RFC-03-014-p3a-readonly-gate V0.2 §2.4 裁定 2 / SPEC §0 R1
    锚定 2 / DESIGN §4.4, the **only** fields permitted to reach
    stdout / YAML for PR-0 are:

    * ``generated_at`` — ISO 8601 timestamp.
    * ``source_kind`` — generic label from :data:`R1_SOURCE_KINDS`.
    * ``overall.verdict`` — single aggregate verdict.
    * ``overall.error_class`` — generic redacted error-class label.

    The legacy fields ``sources[]``, ``missing_keys``,
    per-source / per-key boolean detail (file_exists /
    file_readable / key_declared / is_loadable) are explicitly
    omitted. Reviewers cannot derive key names, declared/runtime
    state, password markers, paths, values, lengths, hashes, or
    URIs from the resulting YAML.

    The internal :class:`SecretAuditResult` still carries the full
    boolean detail for the verdict computation; this serializer is
    the gate that decides what reaches the wire.
    """
    aggregate = _to_secret_audit_aggregate(result)
    return _yaml_dump(sanitize(_secret_aggregate_to_payload(aggregate)))


def _to_secret_audit_aggregate(result: SecretAuditResult) -> SecretAuditAggregate:
    """Project a :class:`SecretAuditResult` to its R1 aggregate form.

    The mapping is deterministic and does NOT carry any per-key /
    per-source boolean detail. Only the verdict, a generic
    source-kind label, and a generic redacted error-class reach the
    :class:`SecretAuditAggregate`.
    """
    # Source-kind selection: we always emit the canonical
    # ``phase2_skills_env`` label regardless of which candidate
    # produced the verdict (RFC V0.2 §5.1; SPEC F-PR0-005). The
    # internal probe may have inspected multiple paths; the
    # external surface collapses them to one generic label.
    source_kind = "phase2_skills_env"

    # Error-class mapping: coarse category derived from the
    # aggregate verdict, never the per-key detail. ``unauthorized``
    # with no probe detail → ``file_missing`` (the canonical
    # not-found state for ``skills/.env``). ``conditional_authorized``
    # has no error to surface. ``authorized`` has no error either.
    verdict = result.status
    if verdict == "authorized":
        error_class = None
    elif verdict == "conditional_authorized":
        # R1: file-declared / runtime env absent = conditional. We
        # emit no error-class here (the verdict itself carries the
        # conditional signal); keeping ``None`` ensures no
        # forbidden tokens can leak through this channel.
        error_class = None
    else:  # unauthorized
        # Coarse: only the presence/absence of a candidate file is
        # summarised; we never name which key or path is missing.
        # ``file_missing`` is the canonical signal for
        # ``skills/.env`` not being present.
        error_class = "file_missing"

    return SecretAuditAggregate(
        source_kind=source_kind,
        verdict=verdict,
        error_class=error_class,
        generated_at=result.generated_at,
    )


def _secret_aggregate_to_payload(agg: SecretAuditAggregate) -> dict[str, Any]:
    """Render an R1 :class:`SecretAuditAggregate` to the YAML payload.

    The payload is structurally minimal — exactly the four permitted
    top-level keys (RFC V0.2 §4.4 / SPEC §4.1).
    """
    return {
        "secret_audit": {
            "generated_at": agg.generated_at,
            "source_kind": agg.source_kind,
            "overall": {
                "verdict": agg.verdict,
                "error_class": agg.error_class,
            },
        }
    }


def mongo_preflight_aggregate_to_yaml(agg: MongoPreflightAggregate) -> str:
    """R1 aggregate-only serialization of a :class:`MongoPreflightAggregate`.

    The external PR-1 surface exposes designated baseline presence plus a
    generic unexpected-presence signal. It never emits arbitrary collection
    names or the internal collection enumeration.

    * ``generated_at`` — ISO 8601 timestamp.
    * ``preflight_mongo.connectivity`` — generic label.
    * ``preflight_mongo.latency_ms`` — coarse latency number (no
      per-operation breakdown).
    * ``preflight_mongo.baseline_collections`` — presence booleans
      for the 3 designated baseline collections, by name. Never the
      full :func:`list_collection_names` enumeration.
    * ``preflight_mongo.unexpected_presence`` — generic boolean for
      non-designated collection presence (``true`` → Pascal review).
      Collection names are never emitted.
    * ``preflight_mongo.warnings`` — generic warning labels.
    * ``overall.verdict`` — pass / conditional_pass / fail /
      unauthorized.

    The legacy fields ``collections`` (full enumeration),
    ``p3_collections_found`` (the old name), ``detail``, and
    ``MONGODB_*``-shaped strings are explicitly omitted.
    """
    return _yaml_dump(sanitize(_mongo_aggregate_to_payload(agg)))


def _mongo_aggregate_to_payload(agg: MongoPreflightAggregate) -> dict[str, Any]:
    """Render an R1 :class:`MongoPreflightAggregate` to YAML payload.

    The payload is structurally minimal — exactly the allowed
    aggregate keys; no free-form collection names are serialized.
    """
    # Treat the aggregate as an external boundary, not as a trusted
    # internal object.  Only the canonical designated names may appear
    # in the wire payload, even if a malformed/synthetic aggregate was
    # constructed by a caller with arbitrary ``BaselineCollectionPresence``
    # entries.  Fill absent entries with ``False`` so the three-state
    # surface remains stable without echoing unknown names.
    observed_presence = {
        entry.name: entry.present
        for entry in agg.baseline_collections
        if entry.name in P3_BUSINESS_COLLECTIONS
    }
    baseline_collections = [
        {"name": name, "present": observed_presence.get(name, False)}
        for name in P3_BUSINESS_COLLECTIONS
    ]

    # Warning values are also an external boundary.  Preserve only the
    # known generic labels; collapse arbitrary text (which may contain a
    # collection name) to a fixed generic signal.  Prefix matching keeps
    # the generic unexpected-presence meaning while discarding any suffix.
    safe_warnings: list[str] = []
    for warning in agg.warnings:
        if warning.startswith("unexpected_collection_presence"):
            safe_warnings.append("unexpected_collection_presence")
        elif warning.startswith("list_collections_unauthorized"):
            safe_warnings.append("list_collections_unauthorized")
        elif warning in {"dry_run", "env_missing", "preflight_warning"}:
            safe_warnings.append(warning)
        else:
            safe_warnings.append("preflight_warning")

    return {
        "preflight_mongo": {
            "generated_at": agg.generated_at,
            "connectivity": agg.connectivity,
            "latency_ms": agg.latency_ms,
            "baseline_collections": baseline_collections,
            "unexpected_presence": agg.unexpected_presence,
            "warnings": safe_warnings,
        },
        "overall": {
            "verdict": agg.overall_verdict,
        },
    }


def smoke_report_to_yaml(report: SmokeReport) -> str:
    """Convenience: serialize a SmokeReport to YAML (SPEC §14.4.2 template).

    The ``preflight`` metadata key is rendered as a dedicated YAML
    section (DESIGN §15.3.2 / §15.10.2). It holds the dry-run-only
    fields ``would_call``, ``akshare.importable``, ``test_symbol``
    and the fixed ``date_range``. Sanitizer rules still apply; the
    block contains no values.

    B0 Fix D — ``endpoint_status`` is emitted as a top-level YAML
    field only when ``report.metadata`` carries the key explicitly.
    Callers (currently :mod:`scripts.t4_preflight.smoke_sector`) set
    it only on the live-read path when both PR-2 calls fail with
    ``ProxyError`` / ``ConnectionError``. Dry-run, success paths, and
    generic RuntimeError failures therefore keep the field absent
    (the YAML stays clean — no ``endpoint_status: null`` noise).

    B2 ledger — every report carries the six-field ``ledger:`` block
    (DESIGN §15.14.3): ``provider_attempts`` / ``actual_calls`` /
    ``retry_count`` / ``fallback_count`` / ``mongo_calls`` /
    ``write_operations``. The block is sourced from ``report.ledger``;
    if absent it defaults to a fresh ``LedgerBlock()`` so legacy
    callers keep producing YAML that matches the §15.14.3 contract.
    """
    ledger = report.ledger
    if not isinstance(ledger, LedgerBlock):
        ledger = LedgerBlock()  # backstop — never observed in practice
    payload: dict[str, Any] = {
        "capability": report.metadata.get("capability", "unknown"),
        "provider": report.metadata.get("provider", "unknown"),
        "smoke_at": report.metadata.get("smoke_at", "unknown"),
        "test_target": report.metadata.get("test_target", "unknown"),
        "date_range": report.metadata.get("date_range", []),
        "preflight": dict(report.metadata.get("preflight", {})),
        "connectivity": {
            "status": report.connectivity.status,
            "latency_ms": report.connectivity.latency_ms,
            "error": report.connectivity.error,
        },
        "auth": {
            "status": report.auth.status,
            "error": report.auth.error,
        },
        "permissions": {
            "status": report.permissions.status,
            "note": report.permissions.note,
        },
        "field_mapping": {
            "total_expected_fields": report.field_mapping.total_expected_fields,
            "matched_fields": report.field_mapping.matched_fields,
            "missing_fields": list(report.field_mapping.missing_fields),
            "extra_fields": list(report.field_mapping.extra_fields),
            "unmatched_types": [dict(d) for d in report.field_mapping.type_mismatches],
        },
        "data_sample": {
            "row_count": report.data_sample.row_count,
            "sample_rows": [dict(r) for r in report.data_sample.sample_rows],
            "null_ratio": report.data_sample.null_ratio,
        },
        "vs_fixture": {
            "deviations": [
                {
                    "field": d.field,
                    "fixture_type": d.fixture_type,
                    "actual_type": d.actual_type,
                    "impact": d.impact,
                }
                for d in report.vs_fixture.deviations
            ]
        },
        "ledger": {
            "provider_attempts": ledger.provider_attempts,
            "actual_calls": ledger.actual_calls,
            "retry_count": ledger.retry_count,
            "fallback_count": ledger.fallback_count,
            "mongo_calls": ledger.mongo_calls,
            "write_operations": ledger.write_operations,
        },
        "overall": {
            "verdict": report.overall.verdict,
            "memo": report.overall.memo,
        },
    }
    # B0 Fix D — emit ``endpoint_status`` only when the caller set it
    # in metadata. Absent key keeps the YAML clean (no ``null`` noise
    # on dry-run / success / generic RuntimeError paths).
    if "endpoint_status" in report.metadata:
        payload["endpoint_status"] = report.metadata["endpoint_status"]
    return _yaml_dump(sanitize(payload))


# Re-export commonly used dataclasses for tests
__all__ = [
    "sanitize",
    "to_yaml",
    "secret_audit_to_yaml",
    "mongo_preflight_aggregate_to_yaml",
    "smoke_report_to_yaml",
    "detect_worktree_changed",
    "ConnectionResult",
    "AuthResult",
    "LedgerBlock",
    "PermissionResult",
    "FieldMappingResult",
    "DataSampleResult",
    "FixtureDeviationResult",
    "OverallVerdict",
    "SmokeReport",
    "SecretProbeResult",
    "SecretAuditResult",
    "SecretAuditAggregate",
    "MongoPreflightAggregate",
    "BaselineCollectionPresence",
]
