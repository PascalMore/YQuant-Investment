"""Tests for the report serializer and the zero-write spy.

DESIGN-03-014 §15.7 / §15.9 / SPEC-03-014 §14.4.2 / A-021, A-022, A-024.

Coverage:

* Sanitizer redacts ``mongodb://``, ``https://``, ``password``,
  ``token=``, etc.
* Sanitizer redacts by field name (``value``, ``password``,
  ``secret``).
* Sanitizer truncates long strings.
* Sanitizer truncates large lists.
* ``yaml_parse`` roundtrip for primitive shapes.
* :class:`MaterializeSpyResult` exposes observed_calls and a
  boolean zero-write conclusion.
* Spy-based zero-write verification: when ``DataRouter.query`` is
  invoked for a P3 capability, the router's ``_materialize`` method
  is not called.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import scripts

scripts.__path__.append(str(Path(__file__).resolve().parents[2] / "scripts"))

import pytest

from scripts.t4_preflight.models import (
    AuthResult,
    ConnectionResult,
    DataSampleResult,
    FieldMappingResult,
    FixtureDeviationResult,
    FixtureDeviation,
    MaterializeSpyResult,
    OverallVerdict,
    PermissionResult,
    SecretAuditResult,
    SecretProbeResult,
    SmokeReport,
)
from scripts.t4_preflight.reporter import (
    sanitize,
    secret_audit_to_yaml,
    smoke_report_to_yaml,
    to_yaml,
    yaml_parse,
)
from scripts.t4_preflight.config import (
    SANITIZER_MAX_LIST_LENGTH,
    SANITIZER_MAX_STRING_LENGTH,
)


# ---------------------------------------------------------------------------
# Sanitizer
# ---------------------------------------------------------------------------


def test_sanitizer_redacts_mongodb_uri() -> None:
    out = sanitize({"uri": "mongodb://user:secret@host:27017/db"})
    assert "mongodb://" not in str(out)
    assert "user:secret" not in str(out)
    assert out["uri"] == "[REDACTED]"


def test_sanitizer_redacts_https_uri() -> None:
    out = sanitize({"endpoint": "https://example.com/path"})
    assert "https://" not in str(out)
    assert out["endpoint"] == "[REDACTED]"


def test_sanitizer_redacts_password_substring() -> None:
    out = sanitize({"note": "the password is hunter2"})
    assert "hunter2" not in str(out)
    assert out["note"] == "[REDACTED]"


def test_sanitizer_redacts_token_substring() -> None:
    out = sanitize({"data": "AKSHARE_TOKEN=abcdef"})
    assert "AKSHARE_TOKEN=abcdef" not in str(out)
    assert out["data"] == "[REDACTED]"


def test_sanitizer_redacts_by_field_name() -> None:
    out = sanitize(
        {"value": "anything", "password": "x", "secret": "y", "credential": "z"}
    )
    assert out["value"] == "[REDACTED]"
    assert out["password"] == "[REDACTED]"
    assert out["secret"] == "[REDACTED]"
    assert out["credential"] == "[REDACTED]"


def test_sanitizer_truncates_long_strings() -> None:
    s = "x" * (SANITIZER_MAX_STRING_LENGTH + 50)
    out = sanitize({"blob": s})
    assert isinstance(out["blob"], str)
    assert len(out["blob"]) < len(s)
    assert "chars truncated" in out["blob"]


def test_sanitizer_truncates_large_lists() -> None:
    items = list(range(SANITIZER_MAX_LIST_LENGTH + 10))
    out = sanitize({"items": items})
    assert isinstance(out["items"], list)
    assert len(out["items"]) == SANITIZER_MAX_LIST_LENGTH + 1
    # The last entry is a marker.
    assert "more" in str(out["items"][-1])


def test_sanitizer_does_not_touch_clean_strings() -> None:
    out = sanitize({"name": "BK0489", "count": 5})
    assert out["name"] == "BK0489"
    assert out["count"] == 5


def test_sanitizer_handles_nested_dict() -> None:
    out = sanitize(
        {"outer": {"inner": {"deep": "AKSHARE_TOKEN=zzz", "ok": "safe"}}}
    )
    assert "AKSHARE_TOKEN=zzz" not in str(out)
    assert out["outer"]["inner"]["ok"] == "safe"
    assert out["outer"]["inner"]["deep"] == "[REDACTED]"


def test_sanitizer_handles_tuples() -> None:
    out = sanitize({"items": ("a", "b", "c")})
    assert out["items"] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# YAML serializer roundtrip
# ---------------------------------------------------------------------------


def test_yaml_roundtrip_simple_dict() -> None:
    obj = {"a": 1, "b": "hello", "c": [1, 2, 3], "d": None, "e": True}
    text = to_yaml(obj)
    parsed = yaml_parse(text)
    assert parsed == obj


def test_yaml_roundtrip_nested_dict() -> None:
    obj = {
        "metadata": {"capability": "sector.snapshot", "provider": "akshare"},
        "connectivity": {"status": "success", "latency_ms": 123.4},
        "warnings": ["none"],
    }
    text = to_yaml(obj)
    parsed = yaml_parse(text)
    assert parsed == obj


def test_yaml_roundtrip_list_of_dicts() -> None:
    obj = {
        "rows": [
            {"a": 1, "b": 2},
            {"a": 3, "b": 4},
        ]
    }
    text = to_yaml(obj)
    parsed = yaml_parse(text)
    assert parsed == obj


# ---------------------------------------------------------------------------
# Report serialization
# ---------------------------------------------------------------------------


def test_secret_audit_to_yaml_has_no_value_field() -> None:
    """A-023: serialized SecretAuditResult must not contain any
    field that could carry a secret value."""
    result = SecretAuditResult(
        generated_at="2026-07-22T03:30:00+08:00",
        sources=(
            SecretProbeResult(
                source_name="project_root_env",
                file_exists=True,
                file_readable=True,
                key_declared=True,
                is_loadable=True,
            ),
        ),
        status="authorized",
    )
    text = secret_audit_to_yaml(result)
    parsed = yaml_parse(text)
    assert "secret_audit" in parsed
    assert "value" not in parsed["secret_audit"]["sources"][0]
    assert "raw_value" not in parsed["secret_audit"]["sources"][0]
    # source is a label, not a value.
    assert parsed["secret_audit"]["sources"][0]["source"] == "project_root_env"


def test_smoke_report_to_yaml_has_six_sections() -> None:
    """A-022: six independent sections per SPEC §14.4.2."""
    report = SmokeReport(
        metadata={"capability": "sector.snapshot", "provider": "akshare"},
        connectivity=ConnectionResult(status="success", latency_ms=100.0),
        auth=AuthResult(status="authorized"),
        permissions=PermissionResult(status="ok"),
        field_mapping=FieldMappingResult(
            total_expected_fields=5,
            matched_fields=4,
            missing_fields=("a",),
            extra_fields=("b",),
        ),
        data_sample=DataSampleResult(row_count=1, sample_rows=({"x": 1},)),
        vs_fixture=FixtureDeviationResult(
            deviations=(
                FixtureDeviation(
                    field="a", fixture_type="int", actual_type="str", impact="low"
                ),
            )
        ),
        overall=OverallVerdict(verdict="pass", memo="ok"),
    )
    text = smoke_report_to_yaml(report)
    parsed = yaml_parse(text)
    for section in (
        "capability",
        "connectivity",
        "auth",
        "permissions",
        "field_mapping",
        "data_sample",
        "vs_fixture",
        "overall",
    ):
        assert section in parsed


# ---------------------------------------------------------------------------
# Zero-write spy (A-021)
# ---------------------------------------------------------------------------


def test_materialize_spy_default_is_zero_write() -> None:
    r = MaterializeSpyResult()
    assert r.observed_calls == 0
    assert r.p3_materialize_observed is False
    assert r.p3_readonly_verified is True


def test_data_router_p3_capability_does_not_materialize() -> None:
    """A-021: ``DataRouter.query`` for a P3 capability must NOT call
    ``_materialize``.

    We use the real ``DataRouter`` + a real ``ProviderRegistry`` with
    a single fake P3-only provider. The router's ``_materialize`` is
    monkey-patched to record calls; a successful query must not
    trigger it.
    """
    pytest.importorskip("pymongo", reason="unified_data router needs pymongo")
    from skills.data.unified_data import (
        DataProvider,
        Market,
        ProviderRegistry,
        SecurityId,
    )
    from skills.data.unified_data.models import DataResult
    from skills.data.unified_data.router import DataRouter

    class _P3OnlyProvider(DataProvider):
        @property
        def name(self) -> str:
            return "fake_p3_sector"

        @property
        def capabilities(self) -> set[str]:
            return {"sector.snapshot"}

        @property
        def markets(self) -> set:
            return {Market.CN}

        def is_available(self) -> bool:
            return True

        def fetch(self, domain, operation, security_id, **params):
            return DataResult.success(
                data={"ok": True},
                security_id=security_id,
                domain=domain,
                operation=operation,
                provider=self.name,
            )

    registry = ProviderRegistry()
    registry.register(_P3OnlyProvider())
    router = DataRouter(registry)

    called: list[tuple] = []

    def _spy_materialize(*args, **kwargs):
        called.append((args, kwargs))
        return None

    router._materialize = _spy_materialize  # type: ignore[method-assign]

    sid = SecurityId(market="CN", symbol="600519")
    result = router.query(
        "sector", "snapshot", sid, provider="fake_p3_sector", params={}
    )
    assert result.succeeded
    # The spy must NOT have been called for a P3 capability.
    assert called == [], (
        f"_materialize was called for a P3 capability: {called}"
    )


def test_data_router_p3_capability_3_calls_no_materialize() -> None:
    """Stronger version: run three P3 capability queries and verify
    zero materialize calls.
    """
    pytest.importorskip("pymongo", reason="unified_data router needs pymongo")
    from skills.data.unified_data import (
        DataProvider,
        Market,
        ProviderRegistry,
        SecurityId,
    )
    from skills.data.unified_data.models import DataResult
    from skills.data.unified_data.router import DataRouter

    class _P3OnlyProvider(DataProvider):
        @property
        def name(self) -> str:
            return "fake_p3_flow"

        @property
        def capabilities(self) -> set[str]:
            return {"flow.capital_flow_daily"}

        @property
        def markets(self) -> set:
            return {Market.CN}

        def is_available(self) -> bool:
            return True

        def fetch(self, domain, operation, security_id, **params):
            return DataResult.success(
                data={"v": 1},
                security_id=security_id,
                domain=domain,
                operation=operation,
                provider=self.name,
            )

    registry = ProviderRegistry()
    registry.register(_P3OnlyProvider())
    router = DataRouter(registry)

    called: list[tuple] = []

    def _spy(*args, **kwargs):
        called.append((args, kwargs))

    router._materialize = _spy  # type: ignore[method-assign]

    sid = SecurityId(market="CN", symbol="600519")
    for _ in range(3):
        result = router.query(
            "flow", "capital_flow_daily", sid, provider="fake_p3_flow", params={}
        )
        assert result.succeeded
    assert called == [], f"_materialize was called: {called}"
