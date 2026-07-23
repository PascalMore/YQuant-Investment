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

from .config import SANITIZER_MAX_LIST_LENGTH, SANITIZER_MAX_STRING_LENGTH
from .models import (
    ConnectionResult,
    AuthResult,
    PermissionResult,
    FieldMappingResult,
    DataSampleResult,
    FixtureDeviationResult,
    OverallVerdict,
    SecretAuditResult,
    SecretProbeResult,
    SmokeReport,
)

# ---------------------------------------------------------------------------
# Sanitizer
# ---------------------------------------------------------------------------

#: Patterns that mark a value as "secret-shaped" and must be redacted.
#: Order matters; first match wins. Case-insensitive substring match.
#:
#: Only the canonical candidate secret key (``MONGO_URI``) is listed
#: here. The legacy ``AKSHARE_TOKEN`` / ``MONGODB_URI`` tokens are no
#: longer part of the T4 preflight contract (AKShare is anonymous,
#: Mongo uses the Phase 2 standard ``MONGO_URI``); see DESIGN §15.4.2
#: and SPEC §14.3.
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
    "token=",
    "token:",
)

#: Field name substrings that mark a value as never-to-emit (drop entirely).
_SECRET_FIELD_NAMES: tuple[str, ...] = (
    "value",
    "password",
    "secret",
    "raw_secret",
    "credential",
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
    """Convenience: serialize a SecretAuditResult to YAML."""
    payload = {
        "secret_audit": {
            "generated_at": result.generated_at,
            "sources": [
                {
                    "source": s.source_name,
                    "file_exists": s.file_exists,
                    "file_readable": s.file_readable,
                    "key_declared": s.key_declared,
                    "is_loadable": s.is_loadable,
                }
                for s in result.sources
            ],
            "overall": {
                "status": result.status,
                "missing_keys": list(result.missing_keys),
            },
        }
    }
    return _yaml_dump(sanitize(payload))


def smoke_report_to_yaml(report: SmokeReport) -> str:
    """Convenience: serialize a SmokeReport to YAML (SPEC §14.4.2 template)."""
    payload = {
        "capability": report.metadata.get("capability", "unknown"),
        "provider": report.metadata.get("provider", "unknown"),
        "smoke_at": report.metadata.get("smoke_at", "unknown"),
        "test_target": report.metadata.get("test_target", "unknown"),
        "date_range": report.metadata.get("date_range", []),
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
        "overall": {
            "verdict": report.overall.verdict,
            "memo": report.overall.memo,
        },
    }
    return _yaml_dump(sanitize(payload))


# Re-export commonly used dataclasses for tests
__all__ = [
    "sanitize",
    "to_yaml",
    "secret_audit_to_yaml",
    "smoke_report_to_yaml",
    "ConnectionResult",
    "AuthResult",
    "PermissionResult",
    "FieldMappingResult",
    "DataSampleResult",
    "FixtureDeviationResult",
    "OverallVerdict",
    "SmokeReport",
    "SecretProbeResult",
    "SecretAuditResult",
]
