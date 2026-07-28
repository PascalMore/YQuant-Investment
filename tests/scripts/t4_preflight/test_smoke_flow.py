"""Tests for PR-3 flow smoke.

DESIGN-03-014 §15.6 / SPEC-03-014 §14.4 / A-019, A-022.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import scripts

scripts.__path__.append(str(Path(__file__).resolve().parents[3] / "scripts"))

import pytest

from scripts.t4_preflight import smoke_flow
from scripts.t4_preflight.config import (
    EXIT_CONDITIONAL,
    EXIT_FAIL,
    EXIT_PASS,
)
from scripts.t4_preflight.provider_client import (
    AKSHARE_MAX_CALLS,
    AKShareSmokeClient,
    set_call_dispatcher,
    reset_call_dispatcher,
)
from scripts.t4_preflight.reporter import yaml_parse

from tests.scripts.t4_preflight.fixtures.t4_akshare_fixtures import FakeAkshareDispatcher

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
# Dry-run
# ---------------------------------------------------------------------------


def test_cli_dry_run_smoke_flow_exits_pass(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-flow", "--output-dir", str(out_dir))
    assert proc.returncode == EXIT_PASS
    assert "flow" in proc.stdout
    assert "600519/sh+000001/sz" in proc.stdout


def test_cli_dry_run_flow_does_not_call_akshare(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-flow", "--output-dir", str(out_dir))
    assert proc.stdout.count("status: skipped") >= 3
    assert "verdict: pass" in proc.stdout


def test_cli_smoke_flow_argparser_has_no_apply_flag() -> None:
    p = smoke_flow.build_arg_parser()
    for action in p._actions:  # noqa: SLF001
        opts = action.option_strings
        for forbidden in ("--apply", "--write", "--exec", "--commit", "--force"):
            assert forbidden not in opts


# ---------------------------------------------------------------------------
# Live (with fake dispatcher)
# ---------------------------------------------------------------------------


def test_smoke_flow_live_with_fake_dispatcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("AKSHARE_TOKEN", raising=False)
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        f_sh = client.fetch_capital_flow("600519", "sh", live=True)
        f_sz = client.fetch_capital_flow("000001", "sz", live=True)
        nb = client.fetch_northbound_flow("600519", live=True)
        assert f_sh.connectivity == "success"
        assert f_sz.connectivity == "success"
        assert nb.connectivity == "success"
        assert [fn for fn, _ in fake.calls] == [
            "stock_individual_fund_flow",
            "stock_individual_fund_flow",
            "stock_hsgt_individual_em",
        ]
    finally:
        reset_call_dispatcher()


def test_smoke_flow_refuses_extra_call() -> None:
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        client.fetch_capital_flow("600519", "sh", live=True)
        client.fetch_capital_flow("000001", "sz", live=True)
        client.fetch_northbound_flow("600519", live=True)
        with pytest.raises(RuntimeError):
            client.fetch_capital_flow("600519", "sh", live=True)
    finally:
        reset_call_dispatcher()


def test_smoke_flow_no_retry_on_error() -> None:
    fake = FakeAkshareDispatcher()
    fake.set_error("stock_individual_fund_flow", RuntimeError("kaboom"))
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        f = client.fetch_capital_flow("600519", "sh", live=True)
        assert f.connectivity == "error"
        assert sum(1 for fn, _ in fake.calls if fn == "stock_individual_fund_flow") == 1
    finally:
        reset_call_dispatcher()


# ---------------------------------------------------------------------------
# Report integrity
# ---------------------------------------------------------------------------


def test_smoke_flow_yaml_has_all_six_sections(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-flow", "--output-dir", str(out_dir))
    text = proc.stdout
    for section in (
        "connectivity:",
        "auth:",
        "permissions:",
        "field_mapping:",
        "data_sample:",
        "vs_fixture:",
        "ledger:",
    ):
        assert section in text
    parsed = yaml_parse(text)
    assert "capability" in parsed
    assert "ledger" in parsed
    assert "provider_attempts" in parsed["ledger"]
    assert "actual_calls" in parsed["ledger"]


def test_smoke_flow_caps_match_design() -> None:
    assert AKSHARE_MAX_CALLS["flow.capital_flow_daily"] == 2
    assert AKSHARE_MAX_CALLS["flow.northbound_daily"] == 1


# ---------------------------------------------------------------------------
# PR-3 all-failure contract: exit code / report verdict / ledger stay in lockstep
# ---------------------------------------------------------------------------


def test_smoke_flow_all_failure_returns_exit_fail_and_verdict_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR-3 contract: when every live AKShare call fails, ``run_smoke`` MUST
    return ``EXIT_FAIL`` AND the persisted YAML MUST report
    ``overall.verdict == 'fail'``. The two signals are produced from the
    same branch in ``smoke_flow.run_smoke`` (line 267-299) and must never
    disagree. Historical PR-3 evidence once showed ``verdict=fail`` paired
    with parent ``exit_code=0``; this regression test pins the lockstep.

    The fake dispatcher is the sole network path — no real AKShare call
    is made. Ledger boundaries (≤3 calls, no retry, no fallback, no
    Mongo, no writes) are pinned in the same assertion block to guard
    the broader contract, not just the verdict/exit pair.
    """
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("AKSHARE_TOKEN", raising=False)
    fake = FakeAkshareDispatcher()
    # Force every PR-3 call to raise; ``set_error`` is sticky, so all
    # three subsequent dispatches will throw RuntimeError("kaboom").
    fake.set_error("stock_individual_fund_flow", RuntimeError("kaboom"))
    fake.set_error("stock_hsgt_individual_em", RuntimeError("kaboom"))
    set_call_dispatcher(fake)
    try:
        args = smoke_flow.build_arg_parser().parse_args(
            ["--live-read", "--output-dir", str(tmp_path)]
        )
        exit_code = smoke_flow.run_smoke(args)

        # (1) Return value MUST equal EXIT_FAIL.
        assert exit_code == EXIT_FAIL, (
            f"run_smoke returned {exit_code}, expected EXIT_FAIL={EXIT_FAIL}"
        )

        # (2) Persisted YAML MUST report overall.verdict == 'fail'.
        report_path = next(tmp_path.glob("smoke-flow-*.yaml"))
        parsed = yaml_parse(report_path.read_text(encoding="utf-8"))
        assert parsed["overall"]["verdict"] == "fail", (
            f"overall.verdict was {parsed['overall']['verdict']!r}, "
            f"expected 'fail'"
        )

        # (3) Ledger boundaries stay consistent with the existing
        # contract: provider_attempts caps at 3, no retry/fallback/mongo/
        # write, and the fake dispatcher was hit exactly 3 times (one
        # per live call) with no retry/fallback.
        ledger = parsed["ledger"]
        assert ledger["provider_attempts"] == 3
        assert ledger["actual_calls"] == 0
        assert ledger["retry_count"] == 0
        assert ledger["fallback_count"] == 0
        assert ledger["mongo_calls"] == 0
        assert ledger["write_operations"] == 0
        assert len(fake.calls) == 3
        called_fns = [fn for fn, _ in fake.calls]
        assert called_fns == [
            "stock_individual_fund_flow",
            "stock_individual_fund_flow",
            "stock_hsgt_individual_em",
        ]
    finally:
        reset_call_dispatcher()
