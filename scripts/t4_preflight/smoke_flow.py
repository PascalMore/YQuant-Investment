"""PR-3 → P3-B S1 R3 P0: flow.capital_flow_daily smoke CLI.

DESIGN-03-014 V0.37 §R3.3 / §R3.9 / SPEC-03-014 V0.33 §R3.3 /
§R3.10 / RFC-03-014 V0.33 §R3.3.

P3-B S1 R3 P0 re-implementation (DESIGN V0.37 §R3.9.1 row 1):

The historical PR-3 shape (two-symbol expansion plus a dedicated
northbound slot) is removed. The single capability this runner
exercises is ``flow.capital_flow_daily`` against the single fixed
symbol ``600519`` / ``market='sh'`` (DESIGN §R3.3 / §R3.9
allowlist #1 / #2).

Default dry-run. ``--live-read`` authorizes up to three AKShare
calls on the single ``600519/sh`` slot:

  1. ``akshare.stock_individual_fund_flow(stock='600519', market='sh')``
  2. (optional) follow-up call on the same symbol — bounded by the
     ``config.AKSHARE_MAX_CALLS['flow.capital_flow_daily'] <= 3`` cap
  3. (optional) follow-up call on the same symbol — same bound

The three-call cap is enforced by ``config.AKSHARE_MAX_CALLS``.

Field mapping (DESIGN V0.37 §R3.3 / §R3.9.3):

* ``flow.capital_flow_daily`` expected field set is the P3-B
  canonical expected subset — 9 items (日期、股票代码、收盘价、
  涨跌幅 + 主力/超大单/大单/中单/小单净流入-净额, see
  :data:`_EXPECTED_FLOW_FIELDS`). This is the smoke mapping /
  fixture contract subset, NOT the complete AKShare
  ``stock_individual_fund_flow`` upstream schema (13 columns, no
  股票代码 column).
* The unique field-mapping threshold is
  ``MATCH_RATIO_CONDITIONAL=0.70``
  (``<70% fail-stop / ≥70% 才可通过`` per RFC V0.33 §R3.3 L1573 /
  SPEC V0.33 §R3.3 L2385 / §R3.9 item1 L2448 / §R3.10 item6 L2466).
  No alternative threshold is permitted.

Northbound path (DESIGN §R3.1 / RFC §13.4.5.2 Pascal C):

* ``flow.northbound_daily`` is ``intentionally-unavailable`` and
  the runner never queries the holding-history endpoint. The
  previous northbound call path is removed; the capability
  persists in the registry (DataRouter unchanged) but no AKShare
  call is ever made for it via this runner.

Ledger block (DESIGN §15.14.3):

Every report carries the six-field ``LedgerBlock`` —
``provider_attempts``, ``actual_calls``, ``retry_count``,
``fallback_count``, ``mongo_calls``, ``write_operations``. T3 X2
scope (Pascal 2026-07-26): the four ``*_count`` fields stay at 0.
Empty returns are surfaced through ``OverallVerdict.verdict`` /
``OverallVerdict.memo``.

Output identity (DESIGN §R3.3 / §R3.9):

* ``metadata.capability`` is the single label
  ``flow.capital_flow_daily``.
* ``metadata.test_target`` is ``600519/CN`` (the single fixed
  symbol + market).
* ``metadata.test_target`` does NOT carry the historical PR-3
  second-slot suffix (removed).

Output directory permissions (P0 G-CF-LIVE R2 hardening):

* ``args.output_dir`` is created if missing and unconditionally
  tightened to mode ``0o700`` (owner-only) BEFORE any report is
  written, so an inherited over-permissive umask or a pre-existing
  ``0775`` directory (the R2 trigger) cannot leak the smoke output.
  The tightening is enforced in-Python (``os.chmod``), not by a
  shell ``umask`` or post-hoc chmod.
* The persisted ``smoke-flow-YYYYMMDD.yaml`` is opened with
  ``os.open(..., 0o600)`` so the file mode is locked to ``0600``
  regardless of the process umask. A leading ``0o600`` mode is
  passed to ``os.open`` together with ``O_CREAT|O_WRONLY|O_TRUNC``,
  closing the file descriptor before the ``Path.write_text`` call
  that ``write_text`` would otherwise create with default mode.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TEST_TARGETS,
    DEFAULT_TIMEOUT_SECONDS,
    DRY_RUN_DATE_RANGE,
    EXIT_FAIL,
    EXIT_PASS,
)
from .models import (
    AuthResult,
    ConnectionResult,
    DataSampleResult,
    FieldMappingResult,
    FixtureDeviationResult,
    LedgerBlock,
    OverallVerdict,
    PermissionResult,
    SmokeReport,
)
from .provider_client import (
    AKShareSmokeClient,
    FieldMapper,
    preflight_metadata,
    verdict_for_mapping,
)
from .reporter import smoke_report_to_yaml

__all__ = ["build_arg_parser", "run_smoke", "main"]


_CST = timezone(timedelta(hours=8))

#: Canonical fixed test target (DESIGN V0.37 §R3.9 allowlist #1/#2).
#: The P3-B S1 G-CF-LIVE freeze is the single ``600519`` symbol
#: paired with internal ``market='sh'``; the external report label
#: is ``600519/CN``. Any other value is rejected before any
#: Provider call (SPEC V0.33 §R3.3 / §R3.10 item6).
_FIXED_SYMBOL: str = DEFAULT_TEST_TARGETS["flow.capital_flow_daily"]
_FIXED_MARKET: str = "sh"


def _now_iso() -> str:
    return datetime.now(tz=_CST).replace(microsecond=0).isoformat()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scripts.t4_preflight.cli smoke-flow",
        description=(
            "P3-B S1: AKShare flow.capital_flow_daily smoke (single 600519/sh). "
            "Default dry-run; pass --live-read to actually call AKShare. "
            "The test target is fixed to 600519/sh (DESIGN V0.37 §R3.9 "
            "allowlist #1/#2); --symbol/--market overrides are forbidden."
        ),
    )
    p.add_argument("--live-read", action="store_true", default=False)
    p.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
    )
    p.add_argument(
        "--date",
        type=str,
        default=None,
        help="ISO date used for smoke metadata.",
    )
    return p


# P3-B S1 R3 P0 G-CF-LIVE matching-input field set for
# ``flow.capital_flow_daily`` — 9 zh column names (日期、股票代码、
# 收盘价、涨跌幅 + 主力/超大单/大单/中单/小单净流入-净额).
#
# (a) These 9 zh names are this tool's G-CF-LIVE *matching input
#     contract*: the exact names fed into
#     ``FieldMapper.compare`` / the ``MATCH_RATIO_CONDITIONAL=0.70``
#     decision (config.py) — NOT a doc-frozen canonical field
#     mapping.
# (b) The authoritative doc anchor is the DESIGN §4.2.2 / §15.14.1
#     ``flow.capital_flow_daily`` inferred mapping table: canonical
#     English names (``main_net_inflow`` / ``super_large_net_inflow``
#     etc.), includes ratio/margin rows, no 收盘价/涨跌幅, no
#     ``-净额`` suffix, NOT live-read verified. The mapping input
#     mirrors the zh column names AKShare actually returns; canonical
#     materialization uses the DESIGN inferred table instead.
# (c) "13 columns, no 股票代码 column" is an akshare 1.17.54 static
#     source fact (stock_fund_em.py static check); the DESIGN table
#     only treats 股票代码 as the inferred ``symbol`` source column.
# All 净额 columns are positive=net-inflow (DESIGN §3
# ``CapitalFlowRecord`` 正=净流入). The historical PR-3 expected set
# was 8 fabricated English names (date / close / pct_chg /
# *_net_inflow) that the upstream never exposes — that was the
# schema-mismatch source for PR-3.
_EXPECTED_FLOW_FIELDS: tuple[str, ...] = (
    "日期",
    "股票代码",
    "收盘价",
    "涨跌幅",
    "主力净流入-净额",
    "超大单净流入-净额",
    "大单净流入-净额",
    "中单净流入-净额",
    "小单净流入-净额",
)


def run_smoke(args: argparse.Namespace) -> int:
    # Unbypassable fixed target (DESIGN V0.37 §R3.9 allowlist #1/#2).
    # The CLI parser no longer exposes --symbol/--market, but a
    # programmatic caller could still inject a Namespace carrying
    # noncanonical values. Fail-stop BEFORE any Provider call — we
    # never canonicalize silently and never emit a report for a
    # non-600519/sh target (SPEC V0.33 §R3.3 / §R3.10 item6).
    symbol = getattr(args, "symbol", _FIXED_SYMBOL)
    market = getattr(args, "market", _FIXED_MARKET)
    if symbol != _FIXED_SYMBOL or market != _FIXED_MARKET:
        print(
            "smoke-flow: refusing non-canonical test target "
            f"symbol={symbol!r} market={market!r}; "
            f"single fixed target is {_FIXED_SYMBOL}/{_FIXED_MARKET} "
            "(DESIGN V0.37 §R3.9 allowlist #1/#2).",
            file=sys.stderr,
        )
        return EXIT_FAIL

    client = AKShareSmokeClient(timeout_seconds=DEFAULT_TIMEOUT_SECONDS)

    flow = client.fetch_capital_flow(
        _FIXED_SYMBOL, _FIXED_MARKET, live=args.live_read
    )

    if args.live_read and flow.connectivity == "success" and flow.actual_fields:
        field_mapping = FieldMapper.compare(
            actual_fields=list(flow.actual_fields),
            expected_fields=list(_EXPECTED_FLOW_FIELDS),
        )
    else:
        field_mapping = FieldMappingResult(
            total_expected_fields=len(_EXPECTED_FLOW_FIELDS),
            matched_fields=0,
        )

    any_error = flow.connectivity in ("error", "timeout", "rate_limited")

    if args.live_read:
        if any_error:
            connectivity = ConnectionResult(
                status="failed",
                latency_ms=None,
                error=flow.error,
            )
        else:
            connectivity = ConnectionResult(
                status="success" if flow.connectivity == "success" else "failed",
                latency_ms=flow.latency_ms,
                error=None,
            )
        auth = AuthResult(status="authorized", error=None)
        permissions = PermissionResult(
            status="ok" if flow.connectivity == "success" else "restricted",
            note=None,
        )
    else:
        connectivity = ConnectionResult(status="skipped")
        auth = AuthResult(status="skipped")
        permissions = PermissionResult(status="skipped")

    sample_rows: tuple = ()
    if flow.sample:
        sample_rows = tuple(flow.sample)
    data_sample = DataSampleResult(
        row_count=len(sample_rows),
        sample_rows=sample_rows,
        null_ratio=0.0,
    )

    # Ledger block (DESIGN §15.14.3 最小实现 / §R3.9).
    # G-CF-LIVE freeze: provider-attempts / actual-calls reflect the
    # single-symbol live-read path (one ``stock_individual_fund_flow``
    # call per invocation; the historical PR-3 three-call shape with
    # northbound is removed). Retry / fallback / mongo / write counts
    # are fixed at 0 in the P3-B S1 no-retry / no-fallback /
    # zero-write scope.
    if args.live_read:
        provider_attempts = 1
        actual_calls = 1 if flow.connectivity == "success" else 0
    else:
        provider_attempts = 0
        actual_calls = 0
    ledger = LedgerBlock(
        provider_attempts=provider_attempts,
        actual_calls=actual_calls,
        retry_count=0,
        fallback_count=0,
        mongo_calls=0,
        write_operations=0,
    )

    if not args.live_read:
        overall = OverallVerdict(verdict="pass", memo="dry-run — no real calls made")
        exit_code = EXIT_PASS
    elif any_error:
        overall = OverallVerdict(
            verdict="fail", memo=flow.error or "AKShare call failed"
        )
        exit_code = EXIT_FAIL
    else:
        verdict = verdict_for_mapping(
            field_mapping.matched_ratio,
            capability="flow.capital_flow_daily",
        )
        memo = (
            f"matched_ratio={field_mapping.matched_ratio:.2f} "
            f"({field_mapping.matched_fields}/{field_mapping.total_expected_fields}); "
            f"missing={list(field_mapping.missing_fields)}"
        )
        overall = OverallVerdict(verdict=verdict, memo=memo)
        exit_code = EXIT_PASS if verdict == "pass" else EXIT_FAIL

    date_label = args.date or datetime.now(tz=_CST).date().isoformat()

    report = SmokeReport(
        metadata={
            "capability": "flow.capital_flow_daily",
            "provider": "akshare",
            "smoke_at": _now_iso(),
            "test_target": f"{_FIXED_SYMBOL}/CN",
            "date_range": [date_label, date_label],
            "preflight": preflight_metadata(
                capabilities=("flow.capital_flow_daily",),
                test_symbol=DEFAULT_TEST_TARGETS["flow.capital_flow_daily"],
                date_range=DRY_RUN_DATE_RANGE,
            ),
        },
        connectivity=connectivity,
        auth=auth,
        permissions=permissions,
        field_mapping=field_mapping,
        data_sample=data_sample,
        vs_fixture=FixtureDeviationResult(()),
        overall=overall,
        ledger=ledger,
    )

    yaml_text = smoke_report_to_yaml(report)
    out_dir = Path(args.output_dir).expanduser()
    try:
        # P0 G-CF-LIVE R2 hardening: create the directory if missing,
        # then unconditionally tighten its mode to 0o700 (owner-only)
        # BEFORE any report file lands inside. This defends against
        # an inherited permissive umask (e.g. 0022 yielding 0755/0775)
        # and against a pre-existing directory whose mode was already
        # over-broad (the R2 0775 trigger). The chmod is in-Python
        # (``os.chmod``), so it does not depend on a shell umask or
        # on a post-hoc chmod wrapper that the runner might forget.
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(out_dir, 0o700)
        except OSError as exc:
            print(
                f"smoke-flow: cannot chmod output_dir to 0700: "
                f"{exc.__class__.__name__}",
                file=sys.stderr,
            )
            return 2
        out_path = out_dir / f"smoke-flow-{datetime.now().strftime('%Y%m%d')}.yaml"
        # Open with explicit 0o600 so a fresh-create YAML starts at
        # 0600 regardless of the process umask. ``Path.write_text``
        # would otherwise create the file with default mode
        # (``0o666 & ~umask``), which an umask of 0022 widens to
        # 0o644 — leaking the smoke report to group/other readers.
        #
        # However, ``os.open(..., O_CREAT|O_TRUNC, 0o600)`` only honours
        # the 0o600 mode at *create* time: when the target file already
        # exists, the create branch is skipped and the existing mode bits
        # are preserved. A pre-existing 0644 or 0664 YAML would therefore
        # keep its group/other-readable bits after the truncate step
        # (verified by the regression test_dry_run_forces_yaml_mode_to_0o600_*
        # cases). To close that gap, the runner must also force the
        # post-open fd to ``0o600`` via ``os.fchmod`` BEFORE any YAML
        # content is written. If ``fchmod`` fails we close the fd, print
        # a sanitized error, return EXIT_FAIL, and do NOT write the
        # YAML — a partially-truncated, mode-widened file is not an
        # acceptable outcome. ``os.fdopen`` then wraps the fd and closes
        # it on ``with`` exit (both success and exception paths).
        try:
            fd = os.open(
                out_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
        except OSError as exc:
            print(
                f"smoke-flow: cannot open report: {exc.__class__.__name__}",
                file=sys.stderr,
            )
            return 2
        try:
            os.fchmod(fd, 0o600)
        except OSError as exc:
            os.close(fd)
            print(
                "smoke-flow: cannot force report mode to 0600: "
                f"{exc.__class__.__name__}",
                file=sys.stderr,
            )
            return 2
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(yaml_text)
    except OSError as exc:
        print(f"smoke-flow: cannot write report: {exc.__class__.__name__}", file=sys.stderr)
        return 2

    print(yaml_text)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_smoke(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
