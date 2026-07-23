"""Tests for PR-4 sentiment smoke.

DESIGN-03-014 §15.6 / SPEC-03-014 §14.4 / A-020, A-022.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import scripts

scripts.__path__.append(str(Path(__file__).resolve().parents[2] / "scripts"))

import pytest

from scripts.t4_preflight import smoke_sentiment
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
# Dry-run
# ---------------------------------------------------------------------------


def test_cli_dry_run_smoke_sentiment_exits_pass(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-sentiment", "--output-dir", str(out_dir))
    assert proc.returncode == EXIT_PASS
    assert "sentiment" in proc.stdout


def test_cli_dry_run_sentiment_does_not_call_akshare(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-sentiment", "--output-dir", str(out_dir))
    assert proc.stdout.count("status: skipped") >= 3
    assert "verdict: pass" in proc.stdout


def test_cli_smoke_sentiment_argparser_has_no_apply_flag() -> None:
    p = smoke_sentiment.build_arg_parser()
    for action in p._actions:  # noqa: SLF001
        opts = action.option_strings
        for forbidden in ("--apply", "--write", "--exec", "--commit", "--force"):
            assert forbidden not in opts


# ---------------------------------------------------------------------------
# Live (with fake dispatcher)
# ---------------------------------------------------------------------------


def test_smoke_sentiment_live_with_fake_dispatcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("AKSHARE_TOKEN", raising=False)
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        market = client.fetch_market_sentiment("2026-07-22", live=True)
        pool = client.fetch_limit_up_pool("2026-07-22", live=True)
        assert market.connectivity == "success"
        assert pool.connectivity == "success"
        assert [fn for fn, _ in fake.calls] == [
            "stock_market_fund_flow",
            "stock_zt_pool_em",
        ]
    finally:
        reset_call_dispatcher()


def test_smoke_sentiment_refuses_extra_call() -> None:
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        client.fetch_market_sentiment("2026-07-22", live=True)
        client.fetch_limit_up_pool("2026-07-22", live=True)
        with pytest.raises(RuntimeError):
            client.fetch_market_sentiment("2026-07-22", live=True)
    finally:
        reset_call_dispatcher()


def test_smoke_sentiment_no_retry_on_error() -> None:
    fake = FakeAkshareDispatcher()
    fake.set_error("stock_zt_pool_em", RuntimeError("kaboom"))
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        pool = client.fetch_limit_up_pool("2026-07-22", live=True)
        assert pool.connectivity == "error"
        assert sum(1 for fn, _ in fake.calls if fn == "stock_zt_pool_em") == 1
    finally:
        reset_call_dispatcher()


# ---------------------------------------------------------------------------
# Report integrity
# ---------------------------------------------------------------------------


def test_smoke_sentiment_yaml_has_all_six_sections(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-sentiment", "--output-dir", str(out_dir))
    text = proc.stdout
    for section in (
        "connectivity:",
        "auth:",
        "permissions:",
        "field_mapping:",
        "data_sample:",
        "vs_fixture:",
    ):
        assert section in text
    parsed = yaml_parse(text)
    assert "capability" in parsed


def test_smoke_sentiment_caps_match_design() -> None:
    assert AKSHARE_MAX_CALLS["sentiment.market_snapshot"] == 1
    assert AKSHARE_MAX_CALLS["sentiment.limit_up_pool"] == 1
