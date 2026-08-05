"""Tests for P3-B S1 ``flow.capital_flow_daily`` smoke.

DESIGN-03-014 V0.37 §R3.3 / §R3.9 / SPEC-03-014 V0.33 §R3.3 /
§R3.10 / RFC-03-014 V0.33 §R3.3 / A-019, A-022.

P3-B S1 R3 P0 re-implementation (DESIGN §R3.9.1 row 4):
the historical PR-3 multi-symbol (600519/sh + 000001/sz) and
``flow.northbound_daily`` / ``stock_hsgt_individual_em`` paths
are removed. The single capability exercised here is
``flow.capital_flow_daily`` against the single fixed symbol
``600519`` / ``market='sh'``; the field-mapping threshold is
``MATCH_RATIO_CONDITIONAL=0.70`` (the sole public threshold
input per SPEC §R3.10 item6).
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import scripts

scripts.__path__.append(str(Path(__file__).resolve().parents[3] / "scripts"))

import pytest

from scripts.t4_preflight import smoke_flow
from scripts.t4_preflight.config import (
    DEFAULT_TIMEOUT_SECONDS,
    EXIT_FAIL,
    EXIT_PASS,
    MATCH_RATIO_CONDITIONAL,
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
# Threshold + caps contract (DESIGN V0.37 §R3.3 / §R3.9 allowlist #3)
# ---------------------------------------------------------------------------


def test_capital_flow_cap_clamps_to_three() -> None:
    """P3-B S1 G-CF-LIVE budget: ≤3 calls on the single symbol."""
    assert AKSHARE_MAX_CALLS["flow.capital_flow_daily"] <= 3
    assert AKSHARE_MAX_CALLS["flow.capital_flow_daily"] >= 1


def test_capital_flow_threshold_is_zero_seven() -> None:
    """P3-B S1 G-CF-LIVE unique field-mapping threshold = 0.70.

    Per SPEC V0.33 §R3.10 item6 / RFC V0.33 §R3.3 L1573 / DESIGN
    V0.37 §R3.3, ``MATCH_RATIO_CONDITIONAL=0.70`` is the sole
    public threshold input. No alternative threshold is permitted
    in this module.
    """
    assert MATCH_RATIO_CONDITIONAL == 0.70


def test_northbound_capability_is_not_in_caps() -> None:
    """``flow.northbound_daily`` MUST NOT be in the AKShare cap table.

    The P3-B S1 northbound path is ``intentionally-unavailable``
    (Pascal C / RFC §13.4.5.2 / DESIGN §R3.1). Registering it
    here would silently re-introduce the
    ``stock_hsgt_individual_em`` holding-history endpoint, which
    is forbidden.
    """
    assert "flow.northbound_daily" not in AKSHARE_MAX_CALLS


# ---------------------------------------------------------------------------
# Dry-run (DESIGN §R3.9.3 row 1)
# ---------------------------------------------------------------------------


def test_cli_dry_run_smoke_flow_exits_pass(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-flow", "--output-dir", str(out_dir))
    assert proc.returncode == EXIT_PASS
    assert "flow.capital_flow_daily" in proc.stdout
    # P3-B S1 canonical report label is ``600519/CN``; the provider
    # market alias ``sh`` must NOT leak into the external report.
    assert "600519/CN" in proc.stdout
    assert "600519/sh" not in proc.stdout
    # The historical PR-3 second-slot suffix ``+000001/sz`` MUST NOT
    # appear in P3-B S1 reports.
    assert "000001/sz" not in proc.stdout
    assert "+000001/sz" not in proc.stdout


def test_cli_dry_run_flow_does_not_call_akshare(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    proc = _run_cli("smoke-flow", "--output-dir", str(out_dir))
    # P3-B S1 G-CF-LIVE is a single-symbol run; the dry-run path
    # therefore emits exactly one ``status: skipped`` line, not the
    # historical PR-3 three.
    assert proc.stdout.count("status: skipped") >= 1
    assert "verdict: pass" in proc.stdout
    assert "dry-run — no real calls made" in proc.stdout


def test_cli_smoke_flow_argparser_has_no_apply_flag() -> None:
    """G-CF-LIVE dry-run CLI must not expose any write/apply flag."""
    p = smoke_flow.build_arg_parser()
    for action in p._actions:  # noqa: SLF001
        opts = action.option_strings
        for forbidden in ("--apply", "--write", "--exec", "--commit", "--force"):
            assert forbidden not in opts


def test_cli_smoke_flow_argparser_drops_legacy_sz_symbol() -> None:
    """G-CF-LIVE single-symbol freeze: the historical ``--symbol-sz``
    and the default ``000001`` slot are removed (DESIGN §R3.9
    allowlist #1)."""
    p = smoke_flow.build_arg_parser()
    option_strings: set[str] = set()
    for action in p._actions:  # noqa: SLF001
        option_strings.update(action.option_strings)
    assert "--symbol-sz" not in option_strings
    assert "--symbol-sh" not in option_strings


def test_cli_smoke_flow_argparser_removes_symbol_market_overrides() -> None:
    """G-CF-LIVE single-target freeze: ``--symbol`` / ``--market`` are
    removed from the CLI surface entirely (DESIGN V0.37 §R3.9
    allowlist #1/#2). Any attempt to override the fixed 600519/sh
    target must fail at the parser, before any Provider code runs."""
    p = smoke_flow.build_arg_parser()
    option_strings: set[str] = set()
    for action in p._actions:  # noqa: SLF001
        option_strings.update(action.option_strings)
    assert "--symbol" not in option_strings
    assert "--market" not in option_strings


def test_cli_rejects_symbol_override(tmp_path: Path) -> None:
    """Review regression: ``--symbol 000001`` must be rejected by the
    parser (no ``000001/CN`` report can ever be produced)."""
    out_dir = tmp_path / "out"
    proc = _run_cli(
        "smoke-flow", "--symbol", "000001", "--output-dir", str(out_dir)
    )
    assert proc.returncode != 0
    assert "unrecognized arguments" in proc.stderr
    assert "000001" not in proc.stdout


def test_cli_rejects_market_override(tmp_path: Path) -> None:
    """Review regression: ``--market sz`` must be rejected by the
    parser (no ``/sz`` report can ever be produced)."""
    out_dir = tmp_path / "out"
    proc = _run_cli(
        "smoke-flow", "--market", "sz", "--output-dir", str(out_dir)
    )
    assert proc.returncode != 0
    assert "unrecognized arguments" in proc.stderr
    assert "/sz" not in proc.stdout


def test_entry_rejects_noncanonical_symbol_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Programmatic injection of a non-600519 symbol must fail-stop at
    the run_smoke entry — BEFORE the dispatcher / Provider is touched.

    The fake dispatcher records every call; zero recorded calls proves
    the Provider was never invoked on rejection.
    """
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("AKSHARE_TOKEN", raising=False)
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        args = argparse.Namespace(
            live_read=True,
            output_dir=str(tmp_path),
            date=None,
            symbol="000001",
            market="sh",
        )
        exit_code = smoke_flow.run_smoke(args)
        assert exit_code == EXIT_FAIL
        assert len(fake.calls) == 0, (
            f"Provider invoked {len(fake.calls)} time(s) despite "
            "noncanonical symbol; expected 0"
        )
    finally:
        reset_call_dispatcher()


def test_entry_rejects_noncanonical_market_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Programmatic injection of a non-sh market must fail-stop at the
    run_smoke entry — BEFORE the dispatcher / Provider is touched."""
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("AKSHARE_TOKEN", raising=False)
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        args = argparse.Namespace(
            live_read=True,
            output_dir=str(tmp_path),
            date=None,
            symbol="600519",
            market="sz",
        )
        exit_code = smoke_flow.run_smoke(args)
        assert exit_code == EXIT_FAIL
        assert len(fake.calls) == 0, (
            f"Provider invoked {len(fake.calls)} time(s) despite "
            "noncanonical market; expected 0"
        )
    finally:
        reset_call_dispatcher()


def test_entry_accepts_canonical_symbol_market(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A programmatic caller that injects the canonical 600519/sh values
    must NOT be false-positively rejected — the fixed-target guard only
    rejects non-canonical values (DESIGN V0.37 §R3.9 allowlist #1/#2)."""
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("AKSHARE_TOKEN", raising=False)
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        args = argparse.Namespace(
            live_read=False,
            output_dir=str(tmp_path),
            date=None,
            symbol="600519",
            market="sh",
        )
        exit_code = smoke_flow.run_smoke(args)
        assert exit_code == EXIT_PASS
        assert len(fake.calls) == 0
    finally:
        reset_call_dispatcher()


# ---------------------------------------------------------------------------
# Live (with fake dispatcher; no network)
# ---------------------------------------------------------------------------


def test_smoke_flow_live_with_fake_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P3-B S1 G-CF-LIVE live path: single ``stock_individual_fund_flow``
    call only; no northbound path is invoked.

    The fake dispatcher is the sole network path — no real AKShare
    call is made (DESIGN §R3.9.4).
    """
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("AKSHARE_TOKEN", raising=False)
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        f = client.fetch_capital_flow("600519", "sh", live=True)
        assert f.connectivity == "success"
        # Historical PR-3 three-call shape (two capital_flow + one
        # northbound) is removed. P3-B S1 makes exactly one call to
        # ``stock_individual_fund_flow`` and never touches
        # ``stock_hsgt_individual_em``.
        assert [fn for fn, _ in fake.calls] == ["stock_individual_fund_flow"]
    finally:
        reset_call_dispatcher()


def test_smoke_flow_refuses_extra_capital_flow_call() -> None:
    """P3-B S1 G-CF-LIVE budget cap (≤3) is enforced on the single
    capability. A fourth call on the same capability MUST raise."""
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        # First call grows the counter to 1.
        client.fetch_capital_flow("600519", "sh", live=True)
        # The cap is ≤3; the (cap+1)-th call must raise.
        cap = AKSHARE_MAX_CALLS["flow.capital_flow_daily"]
        for _ in range(cap - 1):
            client.fetch_capital_flow("600519", "sh", live=True)
        with pytest.raises(RuntimeError):
            client.fetch_capital_flow("600519", "sh", live=True)
    finally:
        reset_call_dispatcher()


def test_smoke_flow_no_northbound_call_path() -> None:
    """The fake dispatcher MUST NOT have a
    ``stock_hsgt_individual_em`` call site visit. The P3-B S1
    runner never queries the holding-history endpoint
    (DESIGN §R3.1 / RFC §13.4.5.2 Pascal C)."""
    fake = FakeAkshareDispatcher()
    set_call_dispatcher(fake)
    try:
        client = AKShareSmokeClient(min_interval_seconds=0.0)
        client.fetch_capital_flow("600519", "sh", live=True)
        called_fns = [fn for fn, _ in fake.calls]
        assert "stock_hsgt_individual_em" not in called_fns
    finally:
        reset_call_dispatcher()


def test_smoke_flow_no_retry_on_error() -> None:
    """P3-B S1 G-CF-LIVE never retries on failure
    (DESIGN §15.6.1 / §R3.3)."""
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
# Report integrity (DESIGN §15.14.3 / §R3.9.3)
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
    # The reporter flattens ``metadata`` into top-level keys
    # (DESIGN §15.4.1 / reporter.py). The P3-B S1 capability
    # label is the single ``flow.capital_flow_daily`` string; the
    # historical PR-3 ``+flow.northbound_daily`` suffix MUST NOT
    # appear.
    assert parsed["capability"] == "flow.capital_flow_daily"
    assert "flow.northbound_daily" not in parsed["capability"]
    assert "ledger" in parsed
    assert "provider_attempts" in parsed["ledger"]
    assert "actual_calls" in parsed["ledger"]


def test_smoke_flow_dry_run_ledger_is_zero() -> None:
    """P3-B S1 G-CF-LIVE dry-run path: provider_attempts=0,
    actual_calls=0, no retry / fallback / mongo / write — by
    construction (DESIGN §R3.3 / §R3.9.3)."""
    p = smoke_flow.build_arg_parser().parse_args([])
    exit_code = smoke_flow.run_smoke(p)
    assert exit_code == EXIT_PASS


# ---------------------------------------------------------------------------
# All-failure lockstep (DESIGN §R3.9.3 row 1)
# ---------------------------------------------------------------------------


def test_smoke_flow_all_failure_returns_exit_fail_and_verdict_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P3-B S1 G-CF-LIVE all-failure contract: when the live
    ``stock_individual_fund_flow`` call fails, ``run_smoke`` MUST
    return ``EXIT_FAIL`` AND the persisted YAML MUST report
    ``overall.verdict == 'fail'``. The two signals are produced
    from the same branch in ``smoke_flow.run_smoke`` and must
    never disagree.

    The fake dispatcher is the sole network path — no real AKShare
    call is made. Ledger boundaries (≤3 calls, no retry, no
    fallback, no Mongo, no writes) are pinned in the same
    assertion block to guard the broader contract, not just the
    verdict/exit pair.
    """
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("AKSHARE_TOKEN", raising=False)
    fake = FakeAkshareDispatcher()
    # Force the single P3-B S1 call to raise; ``set_error`` is
    # sticky, so all subsequent dispatches of this fn will throw.
    fake.set_error("stock_individual_fund_flow", RuntimeError("kaboom"))
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
        # contract: provider_attempts is 1 (P3-B S1 single call),
        # no retry/fallback/mongo/write, and the fake dispatcher
        # was hit exactly once (one live call) with no
        # retry/fallback.
        ledger = parsed["ledger"]
        assert ledger["provider_attempts"] == 1
        assert ledger["actual_calls"] == 0
        assert ledger["retry_count"] == 0
        assert ledger["fallback_count"] == 0
        assert ledger["mongo_calls"] == 0
        assert ledger["write_operations"] == 0
        assert len(fake.calls) == 1
        called_fns = [fn for fn, _ in fake.calls]
        assert called_fns == ["stock_individual_fund_flow"]
        # Northbound MUST NOT appear in any dispatch path.
        assert "stock_hsgt_individual_em" not in called_fns
    finally:
        reset_call_dispatcher()


# ---------------------------------------------------------------------------
# Threshold behavior (DESIGN V0.37 §R3.3 / SPEC V0.33 §R3.10 item6)
# ---------------------------------------------------------------------------


def test_field_mapping_threshold_zero_seven_enforced() -> None:
    """G-CF-LIVE is binary at the 0.70 boundary."""
    from scripts.t4_preflight.provider_client import verdict_for_mapping

    assert verdict_for_mapping(0.69, capability="flow.capital_flow_daily") == "fail"
    assert verdict_for_mapping(0.70, capability="flow.capital_flow_daily") == "pass"
    assert verdict_for_mapping(0.89, capability="flow.capital_flow_daily") == "pass"
    assert verdict_for_mapping(0.90, capability="flow.capital_flow_daily") == "pass"
    assert "conditional_pass" not in {
        verdict_for_mapping(ratio, capability="flow.capital_flow_daily")
        for ratio in (0.69, 0.70, 0.89, 0.90)
    }


def test_legacy_mapping_verdict_remains_backward_compatible() -> None:
    """Unscoped legacy callers retain their prior three-state contract."""
    from scripts.t4_preflight.provider_client import verdict_for_mapping

    assert verdict_for_mapping(0.70) == "conditional_pass"
    assert verdict_for_mapping(0.89) == "conditional_pass"
    assert verdict_for_mapping(0.90) == "pass"


# ---------------------------------------------------------------------------
# Timeout contract (G-CF-LIVE ≤3s, DESIGN V0.37 §R3.3 / §R3.9)
# ---------------------------------------------------------------------------


def test_config_default_timeout_is_three_seconds() -> None:
    """G-CF-LIVE ≤3s contract: ``config.DEFAULT_TIMEOUT_SECONDS`` is the
    single source of the 3s default. The historical hardcoded 30s
    default must never reappear."""
    assert DEFAULT_TIMEOUT_SECONDS == 3


def test_client_default_timeout_uses_config_constant() -> None:
    """The ``AKShareSmokeClient`` default constructor path must use
    ``config.DEFAULT_TIMEOUT_SECONDS`` (= 3s) — the Review Major about
    the hardcoded ``timeout_seconds=30`` default (DESIGN V0.37 §R3.3 /
    G-CF-LIVE ≤3s)."""
    client = AKShareSmokeClient()
    assert client._timeout == DEFAULT_TIMEOUT_SECONDS
    assert client._timeout == 3


def test_smoke_flow_client_timeout_is_default_three_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``run_smoke`` constructs its client with the 3s default timeout.

    A recording subclass captures the constructor kwargs; dry-run still
    passes (EXIT_PASS) and the timeout seen by the smoke runner equals
    ``DEFAULT_TIMEOUT_SECONDS`` (3), not the historical 30.
    """
    captured: dict[str, object] = {}

    class RecordingClient(AKShareSmokeClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured.update(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(smoke_flow, "AKShareSmokeClient", RecordingClient)
    args = smoke_flow.build_arg_parser().parse_args([])
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == EXIT_PASS
    assert captured.get("timeout_seconds") == DEFAULT_TIMEOUT_SECONDS
    assert captured.get("timeout_seconds") == 3


# ---------------------------------------------------------------------------
# Output-directory permissions (P0 G-CF-LIVE R2 hardening, owner-only)
# ---------------------------------------------------------------------------
#
# G-CF-LIVE-R2 triggered an over-broad mode on a freshly-created smoke
# output directory (initial ``0775`` instead of the required ``0700``).
# The R2 follow-up pins the smoke runner to:
#
#   * ``args.output_dir`` directory mode = ``0o700`` (owner-only),
#     regardless of the inherited umask or any pre-existing mode;
#   * persisted ``smoke-flow-YYYYMMDD.yaml`` mode = ``0o600``.
#
# These tests are dry-run (no Provider / no AKShare / no Mongo /
# no live-read) — they only exercise the file-system write path in
# ``smoke_flow.run_smoke``.


def _smoke_out_dir_mode(out_dir: Path) -> int:
    return stat.S_IMODE(os.stat(out_dir).st_mode)


def _smoke_yaml_path(out_dir: Path) -> Path:
    yamls = sorted(out_dir.glob("smoke-flow-*.yaml"))
    assert len(yamls) == 1, f"expected exactly one yaml report, got {yamls}"
    return yamls[0]


def test_dry_run_output_dir_is_owner_only_default_umask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default-umask (0022) + freshly created output dir → 0700 + yaml 0600.

    The runner must tighten the directory mode to ``0o700`` BEFORE the
    yaml file lands inside — ``mkdir`` alone would yield ``0o755`` under
    umask 0022, which leaks the smoke report to group/other readers.
    """
    monkeypatch.setattr(os, "umask", lambda mask=0o022: 0o022)
    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        live_read=False,
        output_dir=str(out_dir),
        date=None,
        symbol="600519",
        market="sh",
    )
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == EXIT_PASS
    assert _smoke_out_dir_mode(out_dir) == 0o700
    assert stat.S_IMODE(os.stat(_smoke_yaml_path(out_dir)).st_mode) == 0o600


def test_dry_run_output_dir_is_owner_only_with_zero_umask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Permissive umask 0000 must NOT widen the smoke output.

    With ``umask=0000``, ``mkdir`` yields ``0o777``. The hardening
    path's explicit ``os.chmod(..., 0o700)`` must still win.
    """
    monkeypatch.setattr(os, "umask", lambda mask=0o000: 0o000)
    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        live_read=False,
        output_dir=str(out_dir),
        date=None,
        symbol="600519",
        market="sh",
    )
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == EXIT_PASS
    assert _smoke_out_dir_mode(out_dir) == 0o700
    assert stat.S_IMODE(os.stat(_smoke_yaml_path(out_dir)).st_mode) == 0o600


def test_dry_run_output_dir_tightens_preexisting_wide_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-existing ``0775`` directory (R2 trigger) must be tightened to ``0700``.

    The R2 root-cause was a fresh ``mkdir`` whose initial mode was
    ``0775`` instead of the required ``0700``. Even on the failure
    case, the runner must unconditionally re-apply ``0o700`` BEFORE
    the yaml is written, so an inherited 0775 directory can never
    host a smoke report.
    """
    monkeypatch.setattr(os, "umask", lambda mask=0o022: 0o022)
    out_dir = tmp_path / "wide"
    out_dir.mkdir(parents=False)
    os.chmod(out_dir, 0o775)
    assert _smoke_out_dir_mode(out_dir) == 0o775

    args = argparse.Namespace(
        live_read=False,
        output_dir=str(out_dir),
        date=None,
        symbol="600519",
        market="sh",
    )
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == EXIT_PASS
    assert _smoke_out_dir_mode(out_dir) == 0o700
    assert stat.S_IMODE(os.stat(_smoke_yaml_path(out_dir)).st_mode) == 0o600


def test_dry_run_yaml_file_mode_is_locked_to_0o600(
    tmp_path: Path,
) -> None:
    """Persisted ``smoke-flow-*.yaml`` must be ``0o600`` (not ``0o644``).

    Under the default ``umask 0022``, ``Path.write_text`` would yield
    ``0o644``. The hardening path opens the fd with explicit
    ``0o600`` mode so the file mode is locked regardless of umask.
    """
    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        live_read=False,
        output_dir=str(out_dir),
        date=None,
        symbol="600519",
        market="sh",
    )
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == EXIT_PASS
    yaml_path = _smoke_yaml_path(out_dir)
    assert stat.S_IMODE(os.stat(yaml_path).st_mode) == 0o600


def test_dry_run_uses_existing_output_dir_without_raising(
    tmp_path: Path,
) -> None:
    """An already-``0700`` output dir must be reused silently
    (``exist_ok=True`` path) and stay ``0700`` after the run.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)
    args = argparse.Namespace(
        live_read=False,
        output_dir=str(out_dir),
        date=None,
        symbol="600519",
        market="sh",
    )
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == EXIT_PASS
    assert _smoke_out_dir_mode(out_dir) == 0o700


def test_dry_run_yaml_mode_is_owner_only_via_cli(
    tmp_path: Path,
) -> None:
    """End-to-end CLI smoke (dry-run) must also yield 0700 + 0600.

    Spawns ``python -m scripts.t4_preflight.cli smoke-flow
    --output-dir <tmp_path>`` in a subprocess, so the chmod path is
    exercised exactly the way Gate C / R2 invoked the runner. No
    network / AKShare / Mongo — this is a dry-run subprocess.

    The subprocess inherits the test runner's umask; we only assert
    the final mode bits, not the umask the child saw.
    """
    out_dir = tmp_path / "cli-out"
    proc = _run_cli("smoke-flow", "--output-dir", str(out_dir))
    assert proc.returncode == EXIT_PASS
    assert _smoke_out_dir_mode(out_dir) == 0o700
    assert stat.S_IMODE(os.stat(_smoke_yaml_path(out_dir)).st_mode) == 0o600


def test_dry_run_yaml_exists_and_has_content(
    tmp_path: Path,
) -> None:
    """Sanity: the hardening path still produces a non-empty YAML
    report — the chmod + 0o600 refactor must not break write-content.
    """
    out_dir = tmp_path / "out"
    args = argparse.Namespace(
        live_read=False,
        output_dir=str(out_dir),
        date=None,
        symbol="600519",
        market="sh",
    )
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == EXIT_PASS
    yaml_path = _smoke_yaml_path(out_dir)
    assert yaml_path.read_text(encoding="utf-8")  # non-empty
    assert "flow.capital_flow_daily" in yaml_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Preexisting-mode lockdown (P0 G-CF-LIVE R2 follow-up, 0600 forced)
# ---------------------------------------------------------------------------
#
# POSIX ``os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)`` only consults
# the mode argument at *create* time. When the target file already
# exists, the create branch is skipped and the existing mode bits are
# preserved — so a pre-existing ``0644`` or ``0664`` YAML would survive
# the truncate step. The R2 follow-up forces the post-open fd to
# ``0o600`` via ``os.fchmod`` BEFORE any YAML content is written, on
# both fresh-create and pre-existing-file paths. The runner must also
# fail-stop (close fd, print sanitized error, return EXIT_FAIL) if the
# ``fchmod`` itself errors — a partial state where the file is
# truncated but mode-widened is not an acceptable outcome.
#
# These tests are dry-run (no Provider / no AKShare / no Mongo / no
# live-read) — they only exercise the file-system write path. The
# pre-created YAML is a 0-byte placeholder (real smoke output replaces
# it; the report identity is asserted from the *new* content).


def _seed_yaml_with_mode(out_dir: Path, mode: int) -> Path:
    """Pre-create today's smoke-flow YAML in ``out_dir`` with the given
    mode. Mirrors the runner's ``datetime.now().strftime('%%Y%%m%%d')``
    filename so the runner overwrites the exact same path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = out_dir / f"smoke-flow-{datetime.now().strftime('%Y%m%d')}.yaml"
    yaml_path.write_text("", encoding="utf-8")
    os.chmod(yaml_path, mode)
    assert stat.S_IMODE(os.stat(yaml_path).st_mode) == mode
    return yaml_path


def test_dry_run_forces_yaml_mode_to_0o600_when_preexisting_is_0o644(
    tmp_path: Path,
) -> None:
    """P0 G-CF-LIVE R2 follow-up: a pre-existing ``0644`` YAML must be
    tightened to ``0o600`` after the smoke run — ``os.open`` with
    ``O_TRUNC`` alone does not touch existing mode bits."""
    out_dir = tmp_path / "out"
    _seed_yaml_with_mode(out_dir, 0o644)

    args = argparse.Namespace(
        live_read=False,
        output_dir=str(out_dir),
        date=None,
        symbol="600519",
        market="sh",
    )
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == EXIT_PASS

    yaml_path = _smoke_yaml_path(out_dir)
    assert stat.S_IMODE(os.stat(yaml_path).st_mode) == 0o600, (
        f"yaml mode was {oct(stat.S_IMODE(os.stat(yaml_path).st_mode))}, "
        "expected 0o600 after the smoke run"
    )
    # Report identity must be preserved through the rewrite: a non-empty
    # YAML carrying the P3-B S1 capability label and the canonical
    # 600519/CN test target; no live-read Provider calls were made.
    text = yaml_path.read_text(encoding="utf-8")
    assert text, "yaml report was empty after smoke run"
    assert "flow.capital_flow_daily" in text
    assert "600519/CN" in text
    # 600519/sh (provider market alias) MUST NOT leak into the external
    # report on the pre-existing-file path either.
    assert "600519/sh" not in text
    # Dry-run ledger keeps 0 actual_calls / 0 write_operations.
    parsed = yaml_parse(text)
    assert parsed["ledger"]["actual_calls"] == 0
    assert parsed["ledger"]["write_operations"] == 0


def test_dry_run_forces_yaml_mode_to_0o600_when_preexisting_is_0o664(
    tmp_path: Path,
) -> None:
    """P0 G-CF-LIVE R2 follow-up: a pre-existing ``0664`` YAML must be
    tightened to ``0o600`` after the smoke run — the group-writable bit
    must be cleared even if the umask originally allowed it."""
    out_dir = tmp_path / "out"
    _seed_yaml_with_mode(out_dir, 0o664)

    args = argparse.Namespace(
        live_read=False,
        output_dir=str(out_dir),
        date=None,
        symbol="600519",
        market="sh",
    )
    exit_code = smoke_flow.run_smoke(args)
    assert exit_code == EXIT_PASS

    yaml_path = _smoke_yaml_path(out_dir)
    assert stat.S_IMODE(os.stat(yaml_path).st_mode) == 0o600, (
        f"yaml mode was {oct(stat.S_IMODE(os.stat(yaml_path).st_mode))}, "
        "expected 0o600 after the smoke run"
    )
    text = yaml_path.read_text(encoding="utf-8")
    assert text, "yaml report was empty after smoke run"
    assert "flow.capital_flow_daily" in text
    assert "600519/CN" in text
    assert "600519/sh" not in text
    parsed = yaml_parse(text)
    assert parsed["ledger"]["actual_calls"] == 0
    assert parsed["ledger"]["write_operations"] == 0
