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

scripts.__path__.append(str(Path(__file__).resolve().parents[3] / "scripts"))

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
    mongo_preflight_aggregate_to_yaml,
    sanitize,
    secret_audit_to_yaml,
    smoke_report_to_yaml,
    to_yaml,
    yaml_parse,
)
from scripts.t4_preflight.secrets import forbidden_in_serialized
from scripts.t4_preflight.config import (
    SANITIZER_MAX_LIST_LENGTH,
    SANITIZER_MAX_STRING_LENGTH,
    P3_BUSINESS_COLLECTIONS,
)
from scripts.t4_preflight.models import (
    BaselineCollectionPresence,
    MongoPreflightAggregate,
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
    out = sanitize({"data": "MONGO_URI=abcdef"})
    assert "MONGO_URI=abcdef" not in str(out)
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
        {"outer": {"inner": {"deep": "MONGO_URI=zzz", "ok": "safe"}}}
    )
    assert "MONGO_URI=zzz" not in str(out)
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
    """A-023 / R1: serialized SecretAuditResult must not contain any
    field that could carry a secret value.

    Per RFC-03-014-p3a-readonly-gate V0.2 §2.4 裁定 2 / SPEC §0 R1
    锚定 2 / DESIGN §4.4, the only fields permitted to reach
    stdout / YAML for PR-0 are:

    * ``secret_audit.generated_at`` — ISO 8601 timestamp.
    * ``secret_audit.source_kind`` — generic label from
      :data:`R1_SOURCE_KINDS`.
    * ``secret_audit.overall.verdict`` — single aggregate verdict.
    * ``secret_audit.overall.error_class`` — generic redacted
      error-class label.

    The legacy ``sources[]`` array, per-key ``value`` / ``raw_value``
    / ``secret_value`` / ``length`` / ``uri`` fields and any
    ``key_declared`` / ``file_exists`` / ``file_readable`` /
    ``runtime_env`` markers must NEVER appear. The internal
    :class:`SecretAuditResult` still carries the full boolean
    detail for the verdict computation; the test below verifies
    the R1 contract on the external YAML.
    """
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
    # R1 contract: only the four permitted top-level keys.
    assert "secret_audit" in parsed
    sec = parsed["secret_audit"]
    assert set(sec.keys()) == {"generated_at", "source_kind", "overall"}, (
        f"R1 contract violated: unexpected keys {set(sec.keys()) - {'generated_at', 'source_kind', 'overall'}}"
    )
    # Overall block is exactly {verdict, error_class}.
    assert set(sec["overall"].keys()) == {"verdict", "error_class"}
    # Verdict is the internal status verbatim.
    assert sec["overall"]["verdict"] == "authorized"
    # Source-kind is one of the canonical R1 labels.
    assert sec["source_kind"] == "phase2_skills_env"
    # The legacy sources[] array must NOT appear externally.
    assert "sources" not in sec
    # Defensive: no R1-forbidden tokens anywhere in the serialized text.
    forbidden = forbidden_in_serialized(text)
    assert forbidden == [], f"R1-forbidden tokens leaked: {forbidden!r}"


# -----------------------------------------------------------------------
# R1 aggregate contract — additional offline tests
# (RFC-03-014-p3a-readonly-gate V0.2 §2.4 裁定 2; SPEC §0 R1 锚定 2)
# -----------------------------------------------------------------------


def test_secret_audit_to_yaml_r1_authorized_authorized_has_no_error_class() -> None:
    """R1: ``authorized`` verdict emits ``error_class: null`` — no
    generic error-class reaches the wire on a healthy pass."""
    result = SecretAuditResult(
        generated_at="2026-08-04T00:00:00+08:00",
        sources=(),
        missing_keys=(),
        status="authorized",
    )
    text = secret_audit_to_yaml(result)
    parsed = yaml_parse(text)
    assert parsed["secret_audit"]["overall"]["verdict"] == "authorized"
    assert parsed["secret_audit"]["overall"]["error_class"] is None
    assert parsed["secret_audit"]["source_kind"] == "phase2_skills_env"
    assert forbidden_in_serialized(text) == []


def test_secret_audit_to_yaml_r1_unauthorized_emits_file_missing() -> None:
    """R1: ``unauthorized`` verdict maps to the generic
    ``file_missing`` error-class — never names a key or path."""
    result = SecretAuditResult(
        generated_at="2026-08-04T00:00:00+08:00",
        sources=(),
        missing_keys=(),
        status="unauthorized",
    )
    text = secret_audit_to_yaml(result)
    parsed = yaml_parse(text)
    assert parsed["secret_audit"]["overall"]["verdict"] == "unauthorized"
    assert parsed["secret_audit"]["overall"]["error_class"] == "file_missing"
    assert forbidden_in_serialized(text) == []


def test_secret_audit_to_yaml_r1_conditional_authorized_emits_no_error_class() -> None:
    """R1: ``conditional_authorized`` keeps ``error_class: null`` —
    the conditional signal is conveyed by the verdict itself, not by
    a forbidden token."""
    result = SecretAuditResult(
        generated_at="2026-08-04T00:00:00+08:00",
        sources=(),
        missing_keys=(),
        status="conditional_authorized",
    )
    text = secret_audit_to_yaml(result)
    parsed = yaml_parse(text)
    assert parsed["secret_audit"]["overall"]["verdict"] == "conditional_authorized"
    assert parsed["secret_audit"]["overall"]["error_class"] is None
    assert forbidden_in_serialized(text) == []


def test_secret_audit_to_yaml_r1_never_enumerates_sources_or_missing_keys() -> None:
    """R1: the external wire must NOT carry ``sources[]`` /
    ``missing_keys`` / per-key state fields — even when the
    internal carrier has them populated."""
    result = SecretAuditResult(
        generated_at="2026-08-04T00:00:00+08:00",
        sources=(
            SecretProbeResult(source_name="phase2_skills_env::MONGODB_HOST",
                              file_exists=True, file_readable=True,
                              key_declared=True, is_loadable=True),
            SecretProbeResult(source_name="phase2_skills_env::MONGODB_PASSWORD",
                              file_exists=True, file_readable=True,
                              key_declared=True, is_loadable=True),
        ),
        missing_keys=("MONGODB_USERNAME", "MONGODB_DATABASE"),
        status="conditional_authorized",
    )
    text = secret_audit_to_yaml(result)
    parsed = yaml_parse(text)
    # Internal carrier is preserved.
    assert len(result.sources) == 2
    assert "MONGODB_USERNAME" in result.missing_keys
    # External wire: nothing of that detail leaks.
    sec = parsed["secret_audit"]
    assert "sources" not in sec
    assert "missing_keys" not in sec
    assert "file_exists" not in text
    assert "file_readable" not in text
    assert "key_declared" not in text
    assert "is_loadable" not in text
    # No R1-forbidden tokens at all (covers the synthetic secrets
    # embedded in the source_name labels too).
    assert forbidden_in_serialized(text) == []


# -----------------------------------------------------------------------
# R1 PR-1 aggregate contract — designated baseline presence
# (RFC-03-014-p3a-readonly-gate V0.2 §2.4 裁定 1; SPEC §0 R1 锚定 1;
# DESIGN §5.5)
# -----------------------------------------------------------------------


def test_mongo_preflight_aggregate_to_yaml_r1_emits_only_baseline_presence() -> None:
    """R1: PR-1 YAML exposes only the three designated baseline
    collection presence booleans. The full enumeration returned by
    ``list_collection_names()`` is structurally excluded."""
    agg = MongoPreflightAggregate(
        connectivity="success",
        latency_ms=12.3,
        baseline_collections=tuple(
            BaselineCollectionPresence(name=n, present=True)
            for n in P3_BUSINESS_COLLECTIONS
        ),
        unexpected_presence=False,
        warnings=("dry_run",),
        overall_verdict="pass",
        generated_at="2026-08-04T00:00:00+08:00",
    )
    text = mongo_preflight_aggregate_to_yaml(agg)
    parsed = yaml_parse(text)
    assert "preflight_mongo" in parsed
    pm = parsed["preflight_mongo"]
    # Only the seven permitted top-level keys for the R1 schema
    # (DESIGN §5.5): generated_at, connectivity, latency_ms,
    # baseline_collections, unexpected_presence, warnings, overall.
    # External R1 keys include a generic presence signal, never a
    # free-form unexpected collection-name list.
    expected_keys = {
        "generated_at",
        "connectivity",
        "latency_ms",
        "baseline_collections",
        "unexpected_presence",
        "warnings",
    }
    assert set(pm.keys()) == expected_keys, (
        f"unexpected keys: {set(pm.keys()) - expected_keys}"
    )
    # baseline_collections is exactly the three designated baseline names.
    names = [b["name"] for b in pm["baseline_collections"]]
    assert names == list(P3_BUSINESS_COLLECTIONS)
    # No non-designated collection leaks through this surface.
    assert pm["unexpected_presence"] is False
    # Overall block is exactly {verdict}.
    assert parsed["overall"] == {"verdict": "pass"}


def test_mongo_preflight_aggregate_to_yaml_r1_rejects_unexpected_presence() -> None:
    """R1: unexpected collection presence is reduced to a generic
    boolean signal. No non-designated collection name reaches YAML.
    """
    agg = MongoPreflightAggregate(
        connectivity="success",
        latency_ms=15.0,
        baseline_collections=tuple(
            BaselineCollectionPresence(name=n, present=True)
            for n in P3_BUSINESS_COLLECTIONS
        ),
        unexpected_presence=True,
        warnings=("unexpected_collection_presence",),
        overall_verdict="fail",
        generated_at="2026-08-04T00:00:00+08:00",
    )
    text = mongo_preflight_aggregate_to_yaml(agg)
    parsed = yaml_parse(text)
    pm = parsed["preflight_mongo"]
    # No free-form collection list or legacy key is emitted.
    assert "collections" not in pm
    assert pm["unexpected_presence"] is True
    assert "03_data_ud_unrelated_legacy_collection" not in text
    assert "03_data_ud_mystery_p3_collection" not in text
    assert parsed["overall"]["verdict"] == "fail"


def test_mongo_preflight_aggregate_to_yaml_r1_never_emits_unknown_baseline_names() -> None:
    """R1: serializer defensively drops malformed non-designated
    baseline entries and warning text instead of echoing their names.
    """
    unknown = "03_data_ud_unrelated_legacy_collection"
    agg = MongoPreflightAggregate(
        connectivity="success",
        baseline_collections=(
            BaselineCollectionPresence(
                name=P3_BUSINESS_COLLECTIONS[0], present=True
            ),
            BaselineCollectionPresence(name=unknown, present=True),
        ),
        unexpected_presence=True,
        warnings=(f"unexpected_collection_presence: {unknown}",),
        overall_verdict="fail",
        generated_at="2026-08-04T00:00:00+08:00",
    )

    text = mongo_preflight_aggregate_to_yaml(agg)
    parsed = yaml_parse(text)
    payload = parsed["preflight_mongo"]
    assert unknown not in text
    assert "baseline_unexpected" not in text
    assert [item["name"] for item in payload["baseline_collections"]] == [
        *P3_BUSINESS_COLLECTIONS
    ]
    assert payload["unexpected_presence"] is True


def test_mongo_preflight_aggregate_to_yaml_r1_carries_no_legacy_collections_field() -> None:
    """R1: the legacy ``collections`` / ``p3_collections_found`` /
    ``live_read`` / ``detail`` fields must never appear in the R1
    external YAML — even if a buggy caller hands them a non-empty
    value via :class:`MongoPreflightResult`."""
    agg = MongoPreflightAggregate(
        connectivity="success",
        latency_ms=1.0,
        baseline_collections=tuple(
            BaselineCollectionPresence(name=n, present=False)
            for n in P3_BUSINESS_COLLECTIONS
        ),
        unexpected_presence=False,
        warnings=(),
        overall_verdict="pass",
        generated_at="2026-08-04T00:00:00+08:00",
    )
    text = mongo_preflight_aggregate_to_yaml(agg)
    # R1 contract: the legacy ``collections:`` (free-form enumeration
    # of list_collection_names()) and ``p3_collections_found:`` and
    # ``live_read:`` and ``detail:`` fields must never appear. We
    # check for the YAML keys (with trailing colon + EOL or EOL
    # before next key) rather than the bare substring, because the
    # permitted R1 key ``baseline_collections:`` naturally contains
    # the substring ``collections:``.
    for legacy_key in (
        "live_read:",
        "p3_collections_found:",
        "detail:",
    ):
        assert legacy_key not in text, (
            f"R1 contract violated: legacy fragment {legacy_key!r} in YAML: {text!r}"
        )
    # The free-form ``collections:`` key (a list of arbitrary
    # strings, not a list of {name, present} objects) must be
    # absent. We detect it by looking for the standalone line
    # ``  collections:`` (two-space indent) at the top of the
    # preflight_mongo block, NOT the ``baseline_collections:`` key
    # we are contractually allowed to emit.
    for line in text.splitlines():
        # Strip comments.
        bare = line.split("#", 1)[0].rstrip()
        # An indented YAML key like "  collections:" or
        # "collections:" — but NOT "baseline_collections:".
        if bare.endswith(":") and bare.lstrip().startswith("collections:"):
            assert False, (
                f"R1 contract violated: legacy key {bare!r} in YAML: {text!r}"
            )


def test_forbidden_in_serialized_helper_matches_aggregate_text() -> None:
    """The :func:`forbidden_in_serialized` helper must return an
    empty list for a clean R1 aggregate payload — the R1 serializer
    must not silently re-introduce any forbidden token."""
    agg = MongoPreflightAggregate(
        connectivity="success",
        latency_ms=1.0,
        baseline_collections=tuple(
            BaselineCollectionPresence(name=n, present=True)
            for n in P3_BUSINESS_COLLECTIONS
        ),
        unexpected_presence=False,
        warnings=(),
        overall_verdict="pass",
        generated_at="2026-08-04T00:00:00+08:00",
    )
    text = mongo_preflight_aggregate_to_yaml(agg)
    assert forbidden_in_serialized(text) == []


def test_forbidden_in_serialized_helper_detects_synthetic_secrets() -> None:
    """Defensive: the helper must catch synthetic secret fragments
    that a buggy future serializer might re-introduce."""
    synthetic = "MONGODB_HOST=hunter2 MONGODB_PASSWORD=secret"
    found = forbidden_in_serialized(synthetic)
    assert "MONGODB_HOST" in found
    assert "MONGODB_PASSWORD" in found
    assert "password" in found


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
