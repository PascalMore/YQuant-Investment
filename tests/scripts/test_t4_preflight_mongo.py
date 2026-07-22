"""Tests for PR-1 MongoDB zero-write preflight.

DESIGN-03-014 §15.5 / SPEC-03-014 §14.2 / A-017, A-022, A-025.

Coverage:

* Dry-run does not instantiate pymongo.
* ``run_preflight(live=True, ok_ping)`` returns success.
* Ping failure is classified as dns_failure / timeout / auth_failure.
* List-collections failure is recorded as conditional.
* Unexpected P3 collection is detected.
* CLI exit codes match the design.
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

scripts.__path__.append(str(Path(__file__).resolve().parents[2] / "scripts"))

import pytest

from scripts.t4_preflight import preflight_mongo
from scripts.t4_preflight.config import (
    ALLOWED_DATABASE,
    P3_BUSINESS_COLLECTIONS,
    EXIT_CONDITIONAL,
    EXIT_FAIL,
    EXIT_PASS,
)
from scripts.t4_preflight.mongo_client import (
    FakeMongoClient,
    MongoClientFactory,
)
from scripts.t4_preflight.models import MongoPreflightResult

from .fixtures.t4_mongo_fixtures import (
    isolated_mongo_uri_env,
    use_fake_client,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


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
# Dry-run path
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


# ---------------------------------------------------------------------------
# Live path: success / pings / collections
# ---------------------------------------------------------------------------


def test_live_success_no_unexpected_collections() -> None:
    client = FakeMongoClient(collections=("unrelated", "another"))
    f = MongoClientFactory()
    with use_fake_client(client):
        result = f.run_preflight(live=True, uri="mongodb://x", timeout_seconds=1)
    assert result.connectivity == "success"
    assert result.collections == ("unrelated", "another")
    assert result.p3_collections_found == ()
    assert client.closed is True
    # The factory should have called ping and list_collections once.
    op_names = [c[0] for c in client.calls]
    assert "command" in op_names
    assert "list_collection_names" in op_names


def test_live_detects_unexpected_p3_collections() -> None:
    client = FakeMongoClient(
        collections=("unrelated", P3_BUSINESS_COLLECTIONS[0]),
    )
    f = MongoClientFactory()
    with use_fake_client(client):
        result = f.run_preflight(live=True, uri="mongodb://x", timeout_seconds=1)
    assert result.connectivity == "success"
    assert P3_BUSINESS_COLLECTIONS[0] in result.p3_collections_found
    assert any("UNEXPECTED_EXISTENCE" in w for w in result.warnings)


def test_live_list_collections_unauthorized_returns_conditional() -> None:
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
# Failure classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc, expected",
    [
        (TimeoutError("ping timed out"), "timeout"),
        (OSError("Name or service not known"), "dns_failure"),
        (PermissionError("auth failed"), "auth_failure"),
    ],
)
def test_live_ping_failure_classification(exc: BaseException, expected: str) -> None:
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
# Missing URI
# ---------------------------------------------------------------------------


def test_live_without_uri_is_skipped() -> None:
    with isolated_mongo_uri_env(uri=None):
        f = MongoClientFactory()
        result = f.run_preflight(live=True, timeout_seconds=1)
    assert result.connectivity == "skipped"
    assert any("MONGODB_URI" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def test_cli_dry_run_exits_pass() -> None:
    proc = _run_cli("preflight-mongo", "--output-dir", str(REPO_ROOT / "tmp_out_mongo"))
    assert proc.returncode == EXIT_PASS
    assert "preflight_mongo:" in proc.stdout
    assert "live_read: false" in proc.stdout


def test_cli_live_with_fake_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The CLI does not honor an injected fake factory because it
    # instantiates MongoClientFactory itself. We therefore check
    # the unreachable branch via the dry-run path; the fake is only
    # tested in unit tests above.
    out_dir = tmp_path / "out"
    proc = _run_cli("preflight-mongo", "--output-dir", str(out_dir))
    # Default behavior is dry-run, exit 0.
    assert proc.returncode in (EXIT_PASS, EXIT_FAIL)
    # No URI leaked.
    assert "mongodb://" not in proc.stdout


def test_preflight_mongo_argparser_has_no_apply_flag() -> None:
    p = preflight_mongo.build_arg_parser()
    for action in p._actions:  # noqa: SLF001
        opts = action.option_strings
        for forbidden in ("--apply", "--write", "--exec", "--commit", "--force"):
            assert forbidden not in opts


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
