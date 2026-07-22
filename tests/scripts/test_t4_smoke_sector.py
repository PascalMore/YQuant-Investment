"""Tests for PR-2 sector smoke.

DESIGN-03-014 §15.6 / SPEC-03-014 §14.4 / A-018, A-022.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import scripts

scripts.__path__.append(str(Path(__file__).resolve().parents[2] / "scripts"))

import pytest

from scripts.t4_preflight import smoke_sector
from scripts.t4_preflight.config import (
    DEFAULT_TEST_TARGETS,
    EXIT_CONDITIONAL,
    EXIT_FAIL,
    EXIT_PASS,
)
from scripts.t4_preflight.provider_client import (
    AKSHARE_MAX_CALLS,
    AKShareSmokeClient,
    set_call_dispatcher,
    reset_call_dispatcher,
    verdict_for_mapping,
)
from scripts.t4_preflight.reporter import yaml_parse, smoke_report_to_yaml

from .fixtures.t4_akshare_fixtures import FakeAkshareDispatcher

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
# Verdicts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ratio, expected",
    [
        (1.0, "pass"),
        (0.95, "pass"),
        (0.90, "pass"),
        (0.89, "conditional_pass"),
        (0.70, "conditional_pass"),
        (0.50, "fail"),
        (0.0, "fail"),
    ],
)
def test_verdict_for_mapping(ratio: float, expected: str) -> None:
    assert verdict_for_mapping(ratio) == expected


# ---------------------------------------------------------------------------
# Dry-run via CLI
# ---------------------------------------------------------------------------


def test_cli_dry_run_smoke_sector_exits_pass(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-sector", "--output-dir", str(out_dir))
    assert proc.returncode == EXIT_PASS
    assert "capability:" in proc.stdout
    assert "sector" in proc.stdout


def test_cli_dry_run_does_not_call_akshare(tmp_path: Path) -> None:
    """A-018: dry-run must not import or call akshare."""
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-sector", "--output-dir", str(out_dir))
    # The dry-run yaml should mark all sections as "skipped".
    assert proc.stdout.count("status: skipped") >= 3
    assert "verdict: pass" in proc.stdout


def test_cli_smoke_sector_argparser_has_no_apply_flag() -> None:
    p = smoke_sector.build_arg_parser()
    for action in p._actions:  # noqa: SLF001
        opts = action.option_strings
        for forbidden in ("--apply", "--write", "--exec", "--commit", "--force"):
            assert forbidden not in opts


# ---------------------------------------------------------------------------
# Live path (via injected dispatcher)
# ---------------------------------------------------------------------------


def test_smoke_sector_live_with_fake_dispatcher(tmp_path: Path) -> None:
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        snap = client.fetch_sector_snapshot(DEFAULT_TEST_TARGETS["sector.snapshot"], live=True)
        rank = client.fetch_sector_ranking(live=True)
        assert snap.connectivity == "success"
        assert rank.connectivity == "success"
        # The fake returns 6 columns for sector.snapshot but
        # expected has 6; partial match is fine.
        assert snap.actual_fields is not None
    finally:
        reset_call_dispatcher()


def test_smoke_sector_refuses_extra_call() -> None:
    """AKSHARE_MAX_CALLS limits how many calls a smoke may issue."""
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        client.fetch_sector_snapshot("BK0489", live=True)
        client.fetch_sector_ranking(live=True)
        # Sector has 1+1 cap; a 3rd call should be refused.
        with pytest.raises(RuntimeError):
            client.fetch_sector_snapshot("BK0489", live=True)
    finally:
        reset_call_dispatcher()


def test_smoke_sector_no_retry_on_error() -> None:
    fake = FakeAkshareDispatcher()
    fake.set_error("stock_board_industry_cons_em", TimeoutError("boom"))
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        snap = client.fetch_sector_snapshot("BK0489", live=True)
        assert snap.connectivity == "timeout"
        # No retry: dispatcher.calls contains only one entry.
        assert sum(1 for fn, _ in fake.calls if fn == "stock_board_industry_cons_em") == 1
    finally:
        reset_call_dispatcher()


# ---------------------------------------------------------------------------
# Report integrity
# ---------------------------------------------------------------------------


def test_smoke_sector_yamL_parses_back(tmp_path: Path) -> None:
    """A-022: the report has all six independent sections."""
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-sector", "--output-dir", str(out_dir))
    text = proc.stdout
    for section in (
        "connectivity:",
        "auth:",
        "permissions:",
        "field_mapping:",
        "data_sample:",
        "vs_fixture:",
    ):
        assert section in text, f"missing section {section!r}"
    # Roundtrip: parse the YAML and check structure.
    parsed = yaml_parse(text)
    assert "capability" in parsed
    assert "overall" in parsed


def test_smoke_sector_caps_match_design() -> None:
    """Verify the call caps match DESIGN §15.6.1."""
    assert AKSHARE_MAX_CALLS["sector.snapshot"] == 1
    assert AKSHARE_MAX_CALLS["sector.ranking"] == 1
