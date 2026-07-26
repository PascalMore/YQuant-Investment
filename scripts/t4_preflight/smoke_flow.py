"""PR-3: AKShare flow.capital_flow_daily + northbound_daily smoke CLI.

DESIGN-03-014 §15.6 / SPEC-03-014 §14.4 / RFC-03-014 §13.4.

Default dry-run. ``--live-read`` authorizes up to three AKShare calls:

  1. ``akshare.stock_individual_fund_flow(stock='600519', market='sh')``
  2. ``akshare.stock_individual_fund_flow(stock='000001', market='sz')``
  3. ``akshare.stock_hsgt_individual_em(symbol='600519')``

The three-call cap is enforced by ``config.AKSHARE_MAX_CALLS``.

B2 mapping fix (2026-07-26, DESIGN §4.2.1 / §15.14.1):
- ``flow.capital_flow_daily`` expected field set is re-anchored to the
  actual AKShare ``stock_individual_fund_flow`` upstream schema (8
  fields — zh names, all positive=net-inflow per SPEC §3.2 footnote).
- ``flow.northbound_daily`` expected field set is re-anchored to the
  **北向持股历史** schema returned by ``stock_hsgt_individual_em``
  (B2 observed 9 zh columns: 持股日期 / 当日收盘价 / 当日涨跌幅 /
  持股数量 / 持股市值 / 持股数量占A股百分比 / 今日增持股数 /
  今日增持资金 / 今日持股市值变化). The previous
  ``("date", "stock", "northbound_net_inflow")`` set was a
  fabricated English schema that the upstream never exposes — root
  cause of the B2 0/11 mapping mismatch.

C decision (2026-07-26, RFC §13.4.5.2 + Pascal direction):
``northbound_net_inflow`` MUST remain ``None`` in this Phase 3
implementation. The endpoint's actual payload is the holding-history
schema; mapping any of its columns (持股数量 / 持股市值 /
今日增持资金) to ``northbound_net_inflow`` is explicitly forbidden
(DESIGN §4.2.1 row 631-633). The capability retains its registry
entry but emits ``northbound_*=None`` for the net-inflow field. The
holding columns are surfaced as extra_fields in the smoke report
(memo annotation) but never projected onto the canonical
``CapitalFlowRecord.northbound_net_inflow`` slot.

Ledger block (DESIGN §15.14.3):
Every report carries the six-field ``LedgerBlock`` — provider_attempts,
actual_calls, retry_count, fallback_count, mongo_calls,
write_operations. T3 X2 scope (Pascal 2026-07-26): the four
``*_count`` fields stay at 0. Worktree probing and empty-semantics
classification are not part of the ledger; ``worktree_changed`` /
``empty_semantics`` were removed from ``LedgerBlock`` (see
``scripts/t4_preflight.models``). Empty returns are surfaced through
``OverallVerdict.verdict`` / ``OverallVerdict.memo`` instead.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TEST_TARGETS,
    DRY_RUN_DATE_RANGE,
    EXIT_CONDITIONAL,
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


def _now_iso() -> str:
    return datetime.now(tz=_CST).replace(microsecond=0).isoformat()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scripts.t4_preflight.cli smoke-flow",
        description=(
            "PR-3: AKShare flow.capital_flow_daily + northbound_daily smoke. "
            "Default dry-run; pass --live-read to actually call AKShare."
        ),
    )
    p.add_argument("--live-read", action="store_true", default=False)
    p.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
    )
    p.add_argument(
        "--symbol-sh",
        type=str,
        default="600519",
        help="Shanghai test symbol.",
    )
    p.add_argument(
        "--symbol-sz",
        type=str,
        default="000001",
        help="Shenzhen test symbol.",
    )
    p.add_argument(
        "--date",
        type=str,
        default=None,
        help="ISO date used for smoke metadata.",
    )
    return p


# B2-aligned expected field set for ``flow.capital_flow_daily``.
# Re-anchored to the actual ``stock_individual_fund_flow`` upstream
# schema (8 zh columns). Previously asserted 8 fabricated English
# names (date / close / pct_chg / *_net_inflow) that the upstream
# never exposes — that was the schema-mismatch source for PR-3.
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

# B2-aligned expected field set for ``flow.northbound_daily``.
# Re-anchored to the actual ``stock_hsgt_individual_em`` upstream
# schema (北向持股历史, 9 zh columns). Per Pascal's 2026-07-26 C
# decision this capability does NOT expose ``northbound_net_inflow``;
# the field remains ``None`` in ``CapitalFlowRecord`` (see
# :class:`CapitalFlowRecord.from_northbound_dict`).
_EXPECTED_NORTHBOUND_FIELDS: tuple[str, ...] = (
    "持股日期",
    "当日收盘价",
    "当日涨跌幅",
    "持股数量",
    "持股市值",
    "持股数量占A股百分比",
    "今日增持股数",
    "今日增持资金",
    "今日持股市值变化",
)


def run_smoke(args: argparse.Namespace) -> int:
    client = AKShareSmokeClient()

    flow_sh = client.fetch_capital_flow(args.symbol_sh, "sh", live=args.live_read)
    flow_sz = client.fetch_capital_flow(args.symbol_sz, "sz", live=args.live_read)
    nb = client.fetch_northbound_flow(args.symbol_sh, live=args.live_read)

    if args.live_read and flow_sh.connectivity == "success" and flow_sh.actual_fields:
        fm_flow = FieldMapper.compare(
            actual_fields=list(flow_sh.actual_fields),
            expected_fields=list(_EXPECTED_FLOW_FIELDS),
        )
    else:
        fm_flow = FieldMappingResult(
            total_expected_fields=len(_EXPECTED_FLOW_FIELDS),
            matched_fields=0,
        )

    if args.live_read and nb.connectivity == "success" and nb.actual_fields:
        fm_nb = FieldMapper.compare(
            actual_fields=list(nb.actual_fields),
            expected_fields=list(_EXPECTED_NORTHBOUND_FIELDS),
        )
    else:
        fm_nb = FieldMappingResult(
            total_expected_fields=len(_EXPECTED_NORTHBOUND_FIELDS),
            matched_fields=0,
        )

    field_mapping = FieldMappingResult(
        total_expected_fields=fm_flow.total_expected_fields + fm_nb.total_expected_fields,
        matched_fields=fm_flow.matched_fields + fm_nb.matched_fields,
        missing_fields=fm_flow.missing_fields + fm_nb.missing_fields,
        extra_fields=fm_flow.extra_fields + fm_nb.extra_fields,
        type_mismatches=(),
    )

    all_calls = [flow_sh, flow_sz, nb]
    any_success = any(c.connectivity == "success" for c in all_calls)
    any_error = any(c.connectivity in ("error", "timeout", "rate_limited") for c in all_calls)

    if args.live_read:
        if any_error and not any_success:
            connectivity = ConnectionResult(
                status="failed",
                latency_ms=None,
                error=next((c.error for c in all_calls if c.error), None),
            )
        else:
            latencies = [c.latency_ms for c in all_calls if c.latency_ms is not None]
            avg_latency = sum(latencies) / len(latencies) if latencies else None
            connectivity = ConnectionResult(
                status="success" if any_success else "failed",
                latency_ms=avg_latency,
                error=None,
            )
        auth = AuthResult(status="authorized", error=None)
        permissions = PermissionResult(
            status="ok" if any_success else "restricted",
            note=None,
        )
    else:
        connectivity = ConnectionResult(status="skipped")
        auth = AuthResult(status="skipped")
        permissions = PermissionResult(status="skipped")

    sample_rows: tuple = ()
    for c in all_calls:
        if c.sample:
            sample_rows = tuple(c.sample)
            break
    data_sample = DataSampleResult(
        row_count=len(sample_rows),
        sample_rows=sample_rows,
        null_ratio=0.0,
    )

    # Ledger block (DESIGN §15.14.3 最小实现).
    # Provider-attempts / actual-calls reflect the live-read path:
    # 2 × capital_flow + 1 × northbound = up to 3 network round-trips.
    # Retry / fallback / mongo / write counts are fixed at 0 in T3
    # X2 scope. Worktree probing is opt-in and is NOT called from the
    # dry-run path (Pascal X2). PR-3 row_count > 0 by design; any
    # empty-return semantics are surfaced via ``OverallVerdict``.
    if args.live_read:
        provider_attempts = 3  # up to 3 live calls per AKSHARE_MAX_CALLS
        actual_calls = sum(
            1 for c in all_calls if c.connectivity == "success"
        )
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
    elif any_error and not any_success:
        overall = OverallVerdict(verdict="fail", memo=connectivity.error or "AKShare call failed")
        exit_code = EXIT_FAIL
    else:
        verdict = verdict_for_mapping(field_mapping.matched_ratio)
        # C-decision annotation: PR-3 endpoint payload is holding-history;
        # ``northbound_net_inflow`` is NEVER populated from any holding
        # column. Reviewers should not interpret a low matched_ratio for
        # the northbound segment as a missing net-inflow — it is the
        # holding-schema being mapped against a net-inflow-shaped
        # expected set (or vice versa).
        memo = (
            f"matched_ratio={field_mapping.matched_ratio:.2f} "
            f"({field_mapping.matched_fields}/{field_mapping.total_expected_fields}); "
            f"missing={list(field_mapping.missing_fields)}"
        )
        if nb.connectivity == "success" and nb.actual_fields:
            # PR-3 B2 confirm: actual upstream returns the 9 holding
            # fields; ``northbound_net_inflow`` is intentionally absent
            # in Phase 3 (Pascal C decision 2026-07-26).
            memo += (
                "; NOTE: PR-3 endpoint returns 北向持股历史 (9 zh columns); "
                "northbound_net_inflow is intentionally None per Pascal's C decision "
                "(DESIGN §4.2.1 / RFC §13.4.5.2)."
            )
        overall = OverallVerdict(verdict=verdict, memo=memo)
        exit_code = (
            EXIT_PASS
            if verdict == "pass"
            else EXIT_CONDITIONAL
            if verdict == "conditional_pass"
            else EXIT_FAIL
        )

    date_label = args.date or datetime.now(tz=_CST).date().isoformat()

    report = SmokeReport(
        metadata={
            "capability": "flow.capital_flow_daily+flow.northbound_daily",
            "provider": "akshare",
            "smoke_at": _now_iso(),
            "test_target": f"{args.symbol_sh}/sh+{args.symbol_sz}/sz",
            "date_range": [date_label, date_label],
            "preflight": preflight_metadata(
                capabilities=(
                    "flow.capital_flow_daily",
                    "flow.northbound_daily",
                ),
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
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"smoke-flow-{datetime.now().strftime('%Y%m%d')}.yaml"
        out_path.write_text(yaml_text, encoding="utf-8")
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
