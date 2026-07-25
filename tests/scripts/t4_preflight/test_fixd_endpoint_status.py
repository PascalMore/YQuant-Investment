"""B0 Fix D — endpoint_status YAML serialization contract tests.

DESIGN-03-014 §15.7.1 / SPEC-03-014 §14.4.2.

The four contract cases pinned by ``t_32a9e927``:

1. Pure-local fake ``ProxyError`` on both PR-2 calls → YAML carries
   ``metadata.endpoint_status: endpoint_unreachable``, the memo
   mentions network / egress restriction, call count == 2.
2. Pure-local fake ``ConnectionError`` on both PR-2 calls → same as
   case 1.
3. Generic ``RuntimeError`` on both PR-2 calls → YAML MUST NOT carry
   ``endpoint_status: endpoint_unreachable`` and the memo MUST NOT
   claim "egress restriction"; call count == 2.
4. Snapshot call network-fails but ranking call succeeds → the smoke
   MUST NOT mislabel the entire endpoint as unreachable (no
   ``endpoint_status`` field); call count == 2.

In addition, ``smoke_report_to_yaml`` itself is exercised directly
to verify it never emits ``endpoint_status: null`` when the
metadata key is absent (dry-run / success path noise-free check).

No real HTTP, no Mongo/DB writes, no AKShare imports. Pure-local
``FakeAkshareDispatcher`` only.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import scripts

scripts.__path__.append(str(Path(__file__).resolve().parents[3] / "scripts"))

# B0 Fix D — provider_client classifies failures by
# ``exc.__class__.__name__``. To stay portable across environments
# we construct ad-hoc exception classes whose ``__name__`` is the
# canonical label that provider_client keys off. ``type()`` is used
# because a plain ``class Foo(Exception): __name__ = "X"`` body
# does NOT override the implicit ``__name__`` set by the class
# statement; mutating ``Foo.__name__`` after the class statement
# does, but constructing via ``type()`` is cleaner. The classes are
# declared module-level so they are reusable across tests.
_ProxyError = type("ProxyError", (Exception,), {})
_ConnectionError = type("ConnectionError", (Exception,), {})


from scripts.t4_preflight import smoke_sector
from scripts.t4_preflight.models import (
    AuthResult,
    ConnectionResult,
    DataSampleResult,
    FieldMappingResult,
    FixtureDeviationResult,
    OverallVerdict,
    PermissionResult,
    SmokeReport,
)
from scripts.t4_preflight.provider_client import (
    set_call_dispatcher,
    reset_call_dispatcher,
)
from scripts.t4_preflight.reporter import smoke_report_to_yaml, yaml_parse

from tests.scripts.t4_preflight.fixtures.t4_akshare_fixtures import (
    FakeAkshareDispatcher,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _build_args(tmp_path: Path, live: bool = True) -> argparse.Namespace:
    """Build an args namespace mirroring ``smoke-sector`` CLI defaults."""
    return argparse.Namespace(
        live_read=live,
        output_dir=str(tmp_path / "out"),
        symbol="BK0489",
        date="2026-07-22",
    )


def _read_report_yaml(out_dir: Path) -> str:
    """Read the single ``smoke-sector-YYYYMMDD.yaml`` written by run_smoke."""
    files = list(out_dir.glob("smoke-sector-*.yaml"))
    assert files, f"no smoke-sector-*.yaml under {out_dir}"
    assert len(files) == 1, f"multiple smoke-sector yamls under {out_dir}: {files}"
    return files[0].read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Reporter-level contract (no run_smoke involved)
# ---------------------------------------------------------------------------


def test_reporter_emits_endpoint_status_when_metadata_has_it() -> None:
    """When metadata carries ``endpoint_status``, the YAML does too."""
    report = SmokeReport(
        metadata={
            "capability": "sector.snapshot+sector.ranking",
            "provider": "akshare",
            "endpoint_status": "endpoint_unreachable",
        },
        connectivity=ConnectionResult(status="failed"),
        auth=AuthResult(status="authorized"),
        permissions=PermissionResult(status="restricted"),
        field_mapping=FieldMappingResult(total_expected_fields=6, matched_fields=0),
        data_sample=DataSampleResult(row_count=0),
        vs_fixture=FixtureDeviationResult(()),
        overall=OverallVerdict(
            verdict="fail",
            memo="endpoint_unreachable: blocked — egress restriction",
        ),
    )
    text = smoke_report_to_yaml(report)
    parsed = yaml_parse(text)
    assert parsed["endpoint_status"] == "endpoint_unreachable"
    assert "endpoint_status:" in text
    # Sanitizer is unaffected; the literal value is not a secret.
    assert "endpoint_unreachable" in text


def test_reporter_omits_endpoint_status_when_metadata_lacks_it() -> None:
    """Dry-run / success / generic RuntimeError paths must not emit
    ``endpoint_status: null``."""
    report = SmokeReport(
        metadata={"capability": "sector.snapshot", "provider": "akshare"},
        connectivity=ConnectionResult(status="skipped"),
        auth=AuthResult(status="skipped"),
        permissions=PermissionResult(status="skipped"),
        field_mapping=FieldMappingResult(total_expected_fields=0, matched_fields=0),
        data_sample=DataSampleResult(row_count=0),
        vs_fixture=FixtureDeviationResult(()),
        overall=OverallVerdict(verdict="pass", memo="dry-run"),
    )
    text = smoke_report_to_yaml(report)
    parsed = yaml_parse(text)
    assert "endpoint_status" not in parsed
    assert "endpoint_status" not in text


# ---------------------------------------------------------------------------
# Integration: run_smoke with injected fake dispatcher
# ---------------------------------------------------------------------------


def _set_snapshot_error(fake: FakeAkshareDispatcher, exc: BaseException) -> None:
    """Make the snapshot call raise ``exc``; ranking keeps canned fixture."""
    fake.set_error("stock_board_industry_cons_em", exc)


def _set_both_errors(fake: FakeAkshareDispatcher, exc: BaseException) -> None:
    """Make BOTH snapshot and ranking calls raise ``exc``."""
    fake.set_error("stock_board_industry_cons_em", exc)
    fake.set_error("stock_board_industry_name_em", exc)


def _set_ranking_success_after_snapshot_error(
    fake: FakeAkshareDispatcher, exc: BaseException
) -> None:
    """Snapshot raises; ranking returns the canned success fixture."""
    _set_snapshot_error(fake, exc)
    # ranking remains on the canned fixture → connectivity="success"


# ---------------------------------------------------------------------------
# Case 1 + 2: both calls fail with network-class error
# ---------------------------------------------------------------------------


def test_run_smoke_proxy_error_marks_endpoint_unreachable(tmp_path: Path) -> None:
    """PR-2 + PR-2 ranking both raise ProxyError → endpoint_unreachable."""
    fake = FakeAkshareDispatcher()
    _set_both_errors(fake, _ProxyError("HTTPSConnectionPool blocked"))
    set_call_dispatcher(fake)
    try:
        exit_code = smoke_sector.run_smoke(_build_args(tmp_path, live=True))
    finally:
        reset_call_dispatcher()

    # PR-2 makes exactly two PR-2 calls; the dispatcher records both.
    assert len(fake.calls) == 2
    assert exit_code == 2  # EXIT_FAIL

    text = _read_report_yaml(tmp_path / "out")
    parsed = yaml_parse(text)
    assert parsed["endpoint_status"] == "endpoint_unreachable"
    # Memo must surface the network / egress clue.
    assert "egress" in parsed["overall"]["memo"].lower()
    assert "endpoint_unreachable" in parsed["overall"]["memo"].lower()


def test_run_smoke_connection_error_marks_endpoint_unreachable(tmp_path: Path) -> None:
    """Same as above but the dispatcher raises requests.ConnectionError."""
    fake = FakeAkshareDispatcher()
    # requests.exceptions.ConnectionError has class name "ConnectionError"
    # which is the deterministic class label used by provider_client.
    _set_both_errors(fake, _ConnectionError("Connection refused"))
    set_call_dispatcher(fake)
    try:
        exit_code = smoke_sector.run_smoke(_build_args(tmp_path, live=True))
    finally:
        reset_call_dispatcher()

    assert len(fake.calls) == 2
    assert exit_code == 2

    text = _read_report_yaml(tmp_path / "out")
    parsed = yaml_parse(text)
    assert parsed["endpoint_status"] == "endpoint_unreachable"
    assert "egress" in parsed["overall"]["memo"].lower()


# ---------------------------------------------------------------------------
# Case 3: generic RuntimeError → must NOT mislabel as endpoint_unreachable
# ---------------------------------------------------------------------------


def test_run_smoke_runtime_error_does_not_mark_endpoint_unreachable(
    tmp_path: Path,
) -> None:
    """Generic RuntimeError on both calls → no endpoint_status, no
    'egress restriction' wording (it's a code defect, not a network
    block)."""
    fake = FakeAkshareDispatcher()
    _set_both_errors(fake, RuntimeError("kaboom"))
    set_call_dispatcher(fake)
    try:
        exit_code = smoke_sector.run_smoke(_build_args(tmp_path, live=True))
    finally:
        reset_call_dispatcher()

    assert len(fake.calls) == 2
    assert exit_code == 2

    text = _read_report_yaml(tmp_path / "out")
    parsed = yaml_parse(text)
    # Field must be absent (NOT null, NOT "endpoint_unreachable").
    assert "endpoint_status" not in parsed
    # And the literal string must not appear anywhere in the YAML.
    assert "endpoint_status" not in text
    # Memo must not pretend this is a network issue.
    assert "egress" not in parsed["overall"]["memo"].lower()
    assert "endpoint_unreachable" not in parsed["overall"]["memo"].lower()
    # But the verdict is still "fail" — the smoke correctly rejects.
    assert parsed["overall"]["verdict"] == "fail"


# ---------------------------------------------------------------------------
# Case 4: snapshot network-fails but ranking succeeds → no global label
# ---------------------------------------------------------------------------


def test_run_smoke_partial_network_failure_does_not_blanket_label(
    tmp_path: Path,
) -> None:
    """Snapshot raises ProxyError but ranking succeeds → the smoke MUST
    NOT blanket-label the overall verdict / memo as endpoint
    unreachable, AND MUST NOT emit ``metadata.endpoint_status`` as a
    field at all. The freeze design uses the ``else`` branch (matched
    ratio memo) for this case so the human-readable verdict stays
    honest about what actually failed; B0 Fix E adds a hard contract
    that ``endpoint_status`` is only present when the live-read ran
    AND all calls failed with ProxyError/ConnectionError — partial
    failure (any_success=True) is the negative case that must keep
    the field absent (NOT null, NOT set). See B0 Review MAJOR-1 Fix E.

    Call count is still 2 (snapshot + ranking) — the cap is not
    touched.
    """
    fake = FakeAkshareDispatcher()
    _set_ranking_success_after_snapshot_error(fake, _ProxyError("blocked"))
    set_call_dispatcher(fake)
    try:
        smoke_sector.run_smoke(_build_args(tmp_path, live=True))
    finally:
        reset_call_dispatcher()

    # PR-2 still made both calls (snapshot + ranking).
    assert len(fake.calls) == 2

    text = _read_report_yaml(tmp_path / "out")
    parsed = yaml_parse(text)
    # The human-readable memo MUST NOT claim "endpoint_unreachable" or
    # "egress restriction" — the ranking call succeeded, so the smoke
    # verdict must reflect a partial / mapping-based outcome, not a
    # blanket network-block claim.
    memo = parsed["overall"]["memo"].lower()
    assert "endpoint_unreachable" not in memo
    assert "egress" not in memo
    # Field-level contract (B0 Fix E / Fix F): the metadata MUST NOT
    # carry ``endpoint_status`` at all on a partial-failure path —
    # mirroring the Case 3 RuntimeError assertion above. This is the
    # blind-spot the original Case 4 missed: a single network failure
    # on snapshot with a successful ranking would otherwise emit
    # ``endpoint_status: endpoint_unreachable`` and confuse reviewers
    # into thinking the whole endpoint is blocked.
    assert "endpoint_status" not in parsed
    assert "endpoint_status" not in text


# ---------------------------------------------------------------------------
# Case 5: dry-run CLI path must never carry endpoint_status
# ---------------------------------------------------------------------------


def test_dry_run_cli_yaml_omits_endpoint_status(tmp_path: Path) -> None:
    """Dry-run does not touch the network; the YAML must not invent an
    ``endpoint_status`` field. Mirrors the live-read path's contract
    on the absence side."""
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "-m",
        "scripts.t4_preflight.cli",
        "smoke-sector",
        "--output-dir",
        str(tmp_path / "out"),
    ]
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env={"PYTHONPATH": ".", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "endpoint_status" not in proc.stdout

    text = _read_report_yaml(tmp_path / "out")
    assert "endpoint_status" not in text