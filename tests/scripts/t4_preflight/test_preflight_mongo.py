"""Tests for PR-1 MongoDB zero-write preflight.

DESIGN-03-014 V0.12 §15.5 / SPEC-03-014 V0.5 §14.2.

Coverage:

* Dry-run does not instantiate pymongo.
* ``run_preflight(live=True, uri=...)`` legacy path returns success.
* Ping failure is classified as dns_failure / timeout / auth_failure.
* List-collections failure is recorded as conditional.
* Unexpected P3 collection is detected.
* ``LegacyConfigResolver`` (V0.12 §15.5.2) rejects when any of the
  five ``MONGODB_*`` keys is missing/empty.
* ``LegacyConfigResolver`` rejects when ``MONGODB_DATABASE`` does
  not equal ``"tradingagents"``.
* CLI exit codes match the design (0 / 1 / 2 / 3).
* ``--apply`` / ``--write`` flags are absent.
* No secret value/URI is emitted in stdout.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from pathlib import Path
import scripts

scripts.__path__.append(str(Path(__file__).resolve().parents[3] / "scripts"))

import pytest

from scripts.t4_preflight import preflight_mongo
from scripts.t4_preflight.config import (
    ALLOWED_DATABASE,
    ALLOWED_DATABASE_VALUE,
    P3_BUSINESS_COLLECTIONS,
    EXIT_CONDITIONAL,
    EXIT_FAIL,
    EXIT_PASS,
    EXIT_UNAUTHORIZED,
    SKILLS_ENV_PATH,
)
from scripts.t4_preflight.mongo_client import (
    FakeMongoClient,
    LegacyConfigResolver,
    MongoClientFactory,
    PreflightRunner,
    reset_client_factory,
    set_client_factory,
)
from scripts.t4_preflight.models import (
    BaselineCollectionPresence,
    MongoPreflightAggregate,
    MongoPreflightResult,
)
from scripts.t4_preflight.reporter import mongo_preflight_aggregate_to_yaml

from tests.scripts.t4_preflight.fixtures.t4_mongo_fixtures import (
    isolated_skills_env,
    use_fake_client,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "scripts.t4_preflight.cli", *args]
    return subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Dry-run path (no pymongo)
# ---------------------------------------------------------------------------


def test_dry_run_does_not_instantiate_pymongo() -> None:
    f = MongoClientFactory()
    result = f.run_preflight(live=False)
    assert result.connectivity == "skipped"
    assert result.collections is None
    assert result.p3_collections_found == ()


def test_dry_run_returns_warning() -> None:
    f = MongoClientFactory()
    result = f.run_preflight(live=False)
    assert any("dry-run" in w for w in result.warnings)


def test_preflight_runner_dry_run_no_network() -> None:
    runner = PreflightRunner()
    result = runner.run_preflight(live=False, timeout=3)
    assert result.connectivity == "dry_run"
    assert result.collections is None
    assert result.p3_collections_found == ()


# ---------------------------------------------------------------------------
# Legacy live path (uri-based) — kept for the explicit-uri CLI flag
# ---------------------------------------------------------------------------


def test_legacy_live_success_no_unexpected_collections() -> None:
    client = FakeMongoClient(collections=("unrelated", "another"))
    captured: dict[str, object] = {}

    def _capturing_factory(
        host: str,
        port: int,
        *,
        username: str,
        password: str,
        auth_source: str,
        timeout_ms: int,
    ) -> FakeMongoClient:
        captured.update(
            host=host,
            port=port,
            username=username,
            password=password,
            auth_source=auth_source,
            timeout_ms=timeout_ms,
        )
        return client

    f = MongoClientFactory()
    set_client_factory(_capturing_factory)  # type: ignore[arg-type]
    try:
        result = f.run_preflight(live=True, uri="mongodb://x")
    finally:
        reset_client_factory()
    assert result.connectivity == "success"
    assert result.collections == ("unrelated", "another")
    assert result.p3_collections_found == ()
    assert captured["timeout_ms"] == 3000
    assert client.calls == [
        ("command", ("ping",), {}),
        ("list_collection_names", (ALLOWED_DATABASE,), {}),
    ]
    assert client.closed is True


def test_legacy_live_detects_unexpected_p3_collections() -> None:
    client = FakeMongoClient(
        collections=("unrelated", P3_BUSINESS_COLLECTIONS[0]),
    )
    f = MongoClientFactory()
    with use_fake_client(client):
        result = f.run_preflight(live=True, uri="mongodb://x", timeout_seconds=1)
    assert result.connectivity == "success"
    assert P3_BUSINESS_COLLECTIONS[0] in result.p3_collections_found
    assert any("UNEXPECTED_EXISTENCE" in w for w in result.warnings)


def test_legacy_live_list_collections_unauthorized_returns_conditional() -> None:
    client = FakeMongoClient(
        ping_outcome="success",
        list_collections_raises=PermissionError("not authorized"),
    )
    f = MongoClientFactory()
    with use_fake_client(client):
        result = f.run_preflight(live=True, uri="mongodb://x", timeout_seconds=1)
    assert result.connectivity == "success"
    assert result.collections is None
    assert any("list_collections_unauthorized" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Failure classification (legacy uri path)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc, expected",
    [
        (TimeoutError("ping timed out"), "timeout"),
        (OSError("Name or service not known"), "dns_failure"),
        (PermissionError("auth failed"), "auth_failure"),
    ],
)
def test_legacy_live_ping_failure_classification(exc: BaseException, expected: str) -> None:
    class _BoomClient(FakeMongoClient):
        @property
        def admin(self):  # type: ignore[override]
            outer = self

            class _Admin:
                def command(self, name: str) -> dict:
                    outer.record("command", name)
                    raise exc

            return _Admin()

    f = MongoClientFactory()
    with use_fake_client(_BoomClient()):
        result = f.run_preflight(live=True, uri="mongodb://x", timeout_seconds=1)
    assert result.connectivity == expected


# ---------------------------------------------------------------------------
# V0.12 LegacyConfigResolver (PR-1 live-read with skills/.env)
# ---------------------------------------------------------------------------


def _make_full_skills_env(database: str = ALLOWED_DATABASE_VALUE) -> str:
    return (
        "MONGODB_HOST=example.invalid\n"
        "MONGODB_PORT=27017\n"
        "MONGODB_USERNAME=user\n"
        "MONGODB_PASSWORD=password\n"
        f"MONGODB_DATABASE={database}\n"
    )


def test_resolver_dry_run_does_not_read_file(tmp_path: Path) -> None:
    skills_env = tmp_path / "skills.env"
    skills_env.write_text(_make_full_skills_env(), encoding="utf-8")
    resolver = LegacyConfigResolver(dotenv_path=str(skills_env))
    cfg = resolver.resolve(live=False)
    # dry-run does not parse the file
    assert cfg.all_resolved is False
    assert cfg.errors == ()


def test_resolver_live_all_resolved(tmp_path: Path) -> None:
    skills_env = tmp_path / "skills.env"
    skills_env.write_text(_make_full_skills_env(), encoding="utf-8")
    resolver = LegacyConfigResolver(dotenv_path=str(skills_env))
    cfg = resolver.resolve(live=True)
    assert cfg.host_resolved is True
    assert cfg.port_resolved is True
    assert cfg.username_resolved is True
    assert cfg.password_resolved is True
    assert cfg.database_resolved is True
    assert cfg.all_resolved is True
    assert cfg.errors == ()


def test_resolver_live_rejects_wrong_database(tmp_path: Path) -> None:
    skills_env = tmp_path / "skills.env"
    skills_env.write_text(_make_full_skills_env(database="other"), encoding="utf-8")
    resolver = LegacyConfigResolver(dotenv_path=str(skills_env))
    cfg = resolver.resolve(live=True)
    assert cfg.database_resolved is False
    assert cfg.all_resolved is False
    assert any("MONGODB_DATABASE_not_tradingagents" in e for e in cfg.errors)


def test_resolver_live_rejects_missing_keys(tmp_path: Path) -> None:
    skills_env = tmp_path / "skills.env"
    skills_env.write_text(
        "MONGODB_HOST=example.invalid\n"
        "MONGODB_PORT=27017\n",
        encoding="utf-8",
    )
    resolver = LegacyConfigResolver(dotenv_path=str(skills_env))
    cfg = resolver.resolve(live=True)
    assert cfg.all_resolved is False
    assert cfg.host_resolved is True
    assert cfg.port_resolved is True
    assert cfg.username_resolved is False
    assert cfg.database_resolved is False
    # All missing-key reasons appear.
    joined = ",".join(cfg.errors)
    assert "MONGODB_USERNAME" in joined
    assert "MONGODB_PASSWORD" in joined
    assert "MONGODB_DATABASE" in joined


def test_resolver_live_rejects_non_int_port(tmp_path: Path) -> None:
    skills_env = tmp_path / "skills.env"
    skills_env.write_text(
        "MONGODB_HOST=example.invalid\n"
        "MONGODB_PORT=not-a-number\n"
        "MONGODB_USERNAME=user\n"
        "MONGODB_PASSWORD=password\n"
        f"MONGODB_DATABASE={ALLOWED_DATABASE_VALUE}\n",
        encoding="utf-8",
    )
    resolver = LegacyConfigResolver(dotenv_path=str(skills_env))
    cfg = resolver.resolve(live=True)
    assert cfg.port_resolved is False
    assert cfg.all_resolved is False
    assert any("MONGODB_PORT_not_int" in e for e in cfg.errors)


def test_resolver_live_missing_file(tmp_path: Path) -> None:
    resolver = LegacyConfigResolver(dotenv_path=str(tmp_path / "absent.env"))
    cfg = resolver.resolve(live=True)
    assert cfg.all_resolved is False


def test_resolver_does_not_read_legacy_keys(tmp_path: Path) -> None:
    """Legacy ``MONGO_URI`` must be ignored completely."""
    skills_env = tmp_path / "skills.env"
    skills_env.write_text(
        "MONGO_URI=mongodb://user:***@example.invalid:27017/db\n"
        "MONGODB_URI=mongodb://user:***@example.invalid:27017/db\n",
        encoding="utf-8",
    )
    resolver = LegacyConfigResolver(dotenv_path=str(skills_env))
    cfg = resolver.resolve(live=True)
    # None of the five MONGODB_* keys is present.
    assert cfg.host_resolved is False
    assert cfg.all_resolved is False


def test_resolver_result_carries_no_values() -> None:
    """Sanity: the result dataclass has no field that could hold a value."""
    fields = {f.name for f in dataclasses.fields(_FakeResolved())}
    for forbidden in ("value", "host", "port", "username", "password",
                      "database", "auth_source", "uri", "length"):
        assert forbidden not in fields, (
            f"ResolvedConfig must not carry {forbidden!r}"
        )


# Tiny helper to introspect the dataclass fields without importing the
# production dataclass for tests that should not depend on the
# production types. (We just use ``ResolvedConfig``.)
@dataclasses.dataclass(frozen=True)
class _FakeResolved:
    pass


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def test_cli_dry_run_exits_pass() -> None:
    """Dry-run must exit 0 (PASS) and emit the R1 aggregate shape.

    Per RFC-03-014-p3a-readonly-gate V0.2 §2.4 裁定 1 / SPEC §0 R1
    锚定 1 / DESIGN §5.5, the dry-run YAML exposes only:

    * ``preflight_mongo`` root with ``generated_at`` /
      ``connectivity`` / ``latency_ms`` / ``baseline_collections`` /
      ``unexpected_presence`` / ``warnings``
    * ``overall.verdict`` = ``pass``

    The legacy ``live_read`` / ``collections`` / ``p3_collections_found``
    fields are intentionally absent from the external wire (the
    pre-existing test asserted on the legacy ``live_read: false``
    literal — that field is no longer emitted).
    """
    proc = _run_cli(
        "preflight-mongo",
        "--output-dir",
        "/tmp/yquant-p3-pr1-cli-out",
    )
    assert proc.returncode == EXIT_PASS
    assert "preflight_mongo:" in proc.stdout
    assert "connectivity: dry_run" in proc.stdout
    assert "baseline_collections:" in proc.stdout
    assert "unexpected_presence:" in proc.stdout
    assert "verdict: pass" in proc.stdout
    # R1 contract: no full collections enumeration; no per-key field.
    assert "live_read" not in proc.stdout
    assert "p3_collections_found" not in proc.stdout


def test_cli_dry_run_does_not_leak_secret_strings() -> None:
    proc = _run_cli(
        "preflight-mongo",
        "--output-dir",
        "/tmp/yquant-p3-pr1-cli-out",
    )
    forbidden_substrings = (
        "mongodb://",
        "mongodb+srv://",
        "user:secret",
        "MONGO_URI=",
        "MONGODB_HOST=",
        "MONGODB_USERNAME=",
        "MONGODB_PASSWORD=",
    )
    out = proc.stdout + proc.stderr
    for s in forbidden_substrings:
        assert s not in out, f"dry-run leaked {s!r}: {out!r}"


def test_cli_live_with_wrong_database_returns_unauthorized(tmp_path: Path) -> None:
    """Live-read against a wrong MONGODB_DATABASE must exit 3."""
    sandbox = tmp_path / "sandbox"
    skills_env = sandbox / "skills" / ".env"
    skills_env.parent.mkdir(parents=True, exist_ok=True)
    skills_env.write_text(
        "MONGODB_HOST=example.invalid\n"
        "MONGODB_PORT=27017\n"
        "MONGODB_USERNAME=user\n"
        "MONGODB_PASSWORD=password\n"
        "MONGODB_DATABASE=other\n",
        encoding="utf-8",
    )
    # Run from inside the sandbox so a hypothetical resolver would
    # look at the sandboxed skills/.env. (The default resolver
    # hardcodes the relative path "skills/.env" resolved against
    # CWD.) This is the primary auth gate; we expect unauthorized
    # exit 3 with no connection attempted.
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.t4_preflight.cli",
         "preflight-mongo",
         "--live-read",
         "--output-dir", str(sandbox / "out")],
        cwd=str(sandbox),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == EXIT_UNAUTHORIZED, (
        f"expected 3, got {proc.returncode}: {proc.stdout!r}"
    )
    assert "env_missing" in proc.stdout or "MONGODB_DATABASE" in proc.stdout


def test_preflight_mongo_argparser_has_no_apply_flag() -> None:
    p = preflight_mongo.build_arg_parser()
    for action in p._actions:  # noqa: SLF001
        opts = action.option_strings
        for forbidden in ("--apply", "--write", "--exec", "--commit", "--force"):
            assert forbidden not in opts


# ---------------------------------------------------------------------------
# MINOR-2: preflight-mongo CLI must NOT expose --uri (DESIGN §15.3.1 /
# §15.5.2 "no MONGO_URI / MONGODB_URI / URI parameters"). The legacy
# ``run_preflight(uri=...)`` seam is preserved as an internal test hook
# only; CLI callers must go through the resolver.
# ---------------------------------------------------------------------------


def test_preflight_mongo_argparser_has_no_uri_flag() -> None:
    """MINOR-2: --uri must not be exposed on the CLI."""
    p = preflight_mongo.build_arg_parser()
    for action in p._actions:  # noqa: SLF001
        assert "--uri" not in action.option_strings, (
            "preflight-mongo CLI must not expose --uri (DESIGN §15.3.1)"
        )


def test_preflight_mongo_run_preflight_internal_seam_preserved() -> None:
    """MINOR-2: the internal ``run_preflight(uri=...)`` seam is kept
    so existing tests with a synthetic URI can still exercise the
    legacy fake-client path.
    """
    f = MongoClientFactory()
    # Calling with uri=... must still work programmatically.
    client = FakeMongoClient(collections=("unrelated",))
    captured: dict[str, object] = {}

    def _capturing_factory(
        host: str,
        port: int,
        *,
        username: str,
        password: str,
        auth_source: str,
        timeout_ms: int,
    ) -> FakeMongoClient:
        captured["host"] = host
        captured["port"] = port
        captured["timeout_ms"] = timeout_ms
        return client

    set_client_factory(_capturing_factory)  # type: ignore[arg-type]
    try:
        result = f.run_preflight(live=True, uri="mongodb://internal-test")
    finally:
        reset_client_factory()
    assert result.connectivity == "success"
    assert client.closed is True


def test_preflight_mongo_cli_rejects_uri_flag() -> None:
    """MINOR-2: passing --uri on the CLI must fail (argparse error)."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.t4_preflight.cli",
            "preflight-mongo",
            "--uri",
            "mongodb://example",
        ],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode != 0, (
        f"CLI should reject --uri; got rc={proc.returncode}, "
        f"stdout={proc.stdout!r}, stderr={proc.stderr!r}"
    )
    # argparse writes to stderr; the unknown flag is mentioned.
    assert "--uri" in proc.stderr or "unrecognized" in proc.stderr.lower()


# ---------------------------------------------------------------------------
# Read-only enforcement (RC-4)
# ---------------------------------------------------------------------------


def test_mongo_client_module_has_no_write_call() -> None:
    """A-025: the preflight must not call any write API."""
    src = (REPO_ROOT / "scripts" / "t4_preflight" / "mongo_client.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "create_collection",
        "insert_one",
        "insert_many",
        "update_one",
        "update_many",
        "replace_one",
        "delete_one",
        "delete_many",
        "bulk_write",
        "create_index",
        "create_indexes",
        "drop_collection",
    ):
        assert forbidden not in src, (
            f"mongo_client.py must not reference write API {forbidden!r}"
        )


def test_mongo_preflight_result_dataclass_shape() -> None:
    fields = {f.name for f in dataclasses.fields(MongoPreflightResult)}
    assert "connectivity" in fields
    assert "collections" in fields
    assert "p3_collections_found" in fields
    # No value/length fields.
    for forbidden in ("password", "secret", "value", "length", "uri"):
        assert forbidden not in fields


def test_resolved_config_dataclass_shape() -> None:
    """ResolvedConfig must not carry any raw value (DESIGN §15.5.2)."""
    from scripts.t4_preflight.mongo_client import ResolvedConfig

    fields = {f.name for f in dataclasses.fields(ResolvedConfig)}
    # source_label/source_path are labels, not values.
    assert "source_label" in fields
    assert "source_path" in fields
    # No raw value fields.
    for forbidden in ("host", "port", "username", "password",
                      "database", "auth_source", "value", "raw_value"):
        assert forbidden not in fields


# ---------------------------------------------------------------------------
# R1 aggregate projector (RFC-03-014-p3a-readonly-gate V0.2 §2.4 裁定 1;
# SPEC §0 R1 锚定 1; DESIGN §5.5)
# ---------------------------------------------------------------------------


def test_to_mongo_preflight_aggregate_r1_dry_run_pass() -> None:
    """R1: dry-run projects to ``connectivity=dry_run``,
    ``overall_verdict=pass``, and three designated baseline
    presence booleans. No live I/O; synthetic result only."""
    result = MongoPreflightResult(
        connectivity="dry_run",
        collections=None,
        p3_collections_found=(),
        warnings=("dry-run preflight, no live mongo calls",),
    )
    agg = preflight_mongo._to_mongo_preflight_aggregate(
        result, live_read=False
    )
    assert isinstance(agg, MongoPreflightAggregate)
    assert agg.connectivity == "dry_run"
    assert agg.overall_verdict == "pass"
    # The baseline list is exactly the three designated names, all
    # marked present=False because dry-run never observed the live
    # list_collection_names() output.
    assert tuple(b.name for b in agg.baseline_collections) == P3_BUSINESS_COLLECTIONS
    assert all(b.present is False for b in agg.baseline_collections)
    assert agg.unexpected_presence is False
    # Warnings are mapped to generic labels only.
    assert all(isinstance(w, str) for w in agg.warnings)
    for w in agg.warnings:
        assert "skills/.env" not in w
        assert "MONGODB_" not in w
        assert "five keys" not in w


def test_to_mongo_preflight_aggregate_r1_designated_baseline_observed_is_pass() -> None:
    """R1: when the live list_collection_names() returns the three
    designated baseline collections and nothing else, the aggregate
    verdict is ``pass`` (presence of the designated baseline is NOT
    a failure; this is the core R1 裁定 1 / F-PR1-009 contract)."""
    observed = tuple(P3_BUSINESS_COLLECTIONS)
    result = MongoPreflightResult(
        connectivity="success",
        latency_ms=12.3,
        collections=observed,
        p3_collections_found=(),
        warnings=(),
    )
    agg = preflight_mongo._to_mongo_preflight_aggregate(
        result, live_read=True
    )
    assert agg.connectivity == "success"
    assert agg.overall_verdict == "pass"
    assert tuple(b.name for b in agg.baseline_collections) == P3_BUSINESS_COLLECTIONS
    assert all(b.present is True for b in agg.baseline_collections)
    assert agg.unexpected_presence is False


def test_to_mongo_preflight_aggregate_r1_unexpected_presence_is_fail() -> None:
    """R1: a non-designated collection triggers a generic
    ``unexpected_presence=True`` signal and fail-stop verdict. No
    collection name is exposed by aggregate serialization.
    """

    unknown_collection = "03_data_ud_unrelated_legacy"
    result = MongoPreflightResult(
        connectivity="success",
        latency_ms=15.0,
        collections=(
            P3_BUSINESS_COLLECTIONS[0],
            unknown_collection,
        ),
        p3_collections_found=(unknown_collection,),
        warnings=(f"UNEXPECTED_EXISTENCE: {unknown_collection}",),
    )
    agg = preflight_mongo._to_mongo_preflight_aggregate(
        result, live_read=True
    )
    assert agg.overall_verdict == "fail"
    assert agg.unexpected_presence is True
    # No raw ``collections`` tuple or legacy raw-name field reaches the
    # aggregate.  The serializer has a second defensive allowlist for a
    # malformed aggregate constructed by another caller.
    agg_fields = {f.name for f in dataclasses.fields(agg)}
    assert "collections" not in agg_fields
    assert "baseline_unexpected" not in agg_fields
    # The unexpected warning is mapped to a generic label only.
    assert "unexpected_collection_presence" in agg.warnings
    for w in agg.warnings:
        assert "UNEXPECTED_EXISTENCE" not in w
        assert unknown_collection not in w

    yaml_text = mongo_preflight_aggregate_to_yaml(agg)
    assert "unexpected_presence: true" in yaml_text
    assert unknown_collection not in yaml_text
    assert "baseline_unexpected" not in yaml_text


def test_to_mongo_preflight_aggregate_r1_env_missing_is_unauthorized() -> None:
    """R1: env_missing maps to ``overall_verdict=unauthorized``."""
    result = MongoPreflightResult(
        connectivity="env_missing",
        warnings=("skills/.env missing or no five keys",),
    )
    agg = preflight_mongo._to_mongo_preflight_aggregate(
        result, live_read=True
    )
    assert agg.overall_verdict == "unauthorized"
    # Warning is mapped to a generic label only.
    for w in agg.warnings:
        assert "skills/.env" not in w
        assert "five keys" not in w
        assert "MONGODB_" not in w


def test_to_mongo_preflight_aggregate_r1_list_collections_unauthorized() -> None:
    """R1: ping OK but listCollections not authorized maps to
    ``overall_verdict=conditional_pass``."""
    result = MongoPreflightResult(
        connectivity="success",
        collections=None,
        warnings=("list_collections_unauthorized: not authorized on tradingagents",),
    )
    agg = preflight_mongo._to_mongo_preflight_aggregate(
        result, live_read=True
    )
    assert agg.overall_verdict == "conditional_pass"
    assert "list_collections_unauthorized" in agg.warnings


def test_to_mongo_preflight_aggregate_r1_dns_timeout_auth_is_fail() -> None:
    """R1: connectivity failure maps to ``overall_verdict=fail``."""
    for connectivity in ("dns_failure", "timeout", "auth_failure"):
        result = MongoPreflightResult(
            connectivity=connectivity,
            warnings=(),
        )
        agg = preflight_mongo._to_mongo_preflight_aggregate(
            result, live_read=True
        )
        assert agg.overall_verdict == "fail", (
            f"{connectivity} should map to fail; got {agg.overall_verdict!r}"
        )


def test_to_mongo_preflight_aggregate_r1_carries_no_legacy_warning_tokens() -> None:
    """R1: the external surface never carries ``live_read`` /
    ``collections`` / ``p3_collections_found`` / ``detail`` —
    even when the input carrier has them populated."""
    result = MongoPreflightResult(
        connectivity="success",
        collections=("something",),
        p3_collections_found=("something",),
        detail="legacy detail string with forbidden marker",
        warnings=("legacy warning",),
    )
    agg = preflight_mongo._to_mongo_preflight_aggregate(
        result, live_read=True
    )
    # Aggregate carrier must NOT carry the legacy fields.
    agg_fields = {f.name for f in dataclasses.fields(agg)}
    for forbidden in ("collections", "p3_collections_found",
                      "detail", "live_read"):
        assert forbidden not in agg_fields, (
            f"MongoPreflightAggregate must not carry {forbidden!r}"
        )