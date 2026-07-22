"""PR-4: AKShare sentiment.market_snapshot + limit_up_pool smoke CLI.

DESIGN-03-014 §15.6 / SPEC-03-014 §14.4 / RFC-03-014 §13.4.

Default dry-run. ``--live-read`` authorizes up to two AKShare calls:

  1. ``akshare.stock_market_fund_flow()``
  2. ``akshare.stock_zt_pool_em(date)``
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import (
    DEFAULT_OUTPUT_DIR,
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
    OverallVerdict,
    PermissionResult,
    SmokeReport,
)
from .provider_client import (
    AKShareSmokeClient,
    FieldMapper,
    verdict_for_mapping,
)
from .reporter import smoke_report_to_yaml

__all__ = ["build_arg_parser", "run_smoke", "main"]


_CST = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(tz=_CST).replace(microsecond=0).isoformat()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scripts.t4_preflight.cli smoke-sentiment",
        description=(
            "PR-4: AKShare sentiment.market_snapshot + limit_up_pool smoke. "
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
        "--date",
        type=str,
        default=None,
        help="ISO date used for the smoke (e.g. 2026-07-22).",
    )
    return p


_EXPECTED_SENTIMENT_FIELDS: tuple[str, ...] = (
    "date",
    "market_temperature",
    "limit_up_count",
    "limit_down_count",
    "northbound_net_inflow",
)

_EXPECTED_LIMIT_UP_FIELDS: tuple[str, ...] = (
    "date",
    "code",
    "name",
    "consecutive_limit_up_days",
)


def run_smoke(args: argparse.Namespace) -> int:
    date_label = args.date or datetime.now(tz=_CST).date().isoformat()
    client = AKShareSmokeClient()
    market = client.fetch_market_sentiment(date_label, live=args.live_read)
    pool = client.fetch_limit_up_pool(date_label, live=args.live_read)

    if args.live_read and market.connectivity == "success" and market.actual_fields:
        fm_market = FieldMapper.compare(
            actual_fields=list(market.actual_fields),
            expected_fields=list(_EXPECTED_SENTIMENT_FIELDS),
        )
    else:
        fm_market = FieldMappingResult(
            total_expected_fields=len(_EXPECTED_SENTIMENT_FIELDS),
            matched_fields=0,
        )

    if args.live_read and pool.connectivity == "success" and pool.actual_fields:
        fm_pool = FieldMapper.compare(
            actual_fields=list(pool.actual_fields),
            expected_fields=list(_EXPECTED_LIMIT_UP_FIELDS),
        )
    else:
        fm_pool = FieldMappingResult(
            total_expected_fields=len(_EXPECTED_LIMIT_UP_FIELDS),
            matched_fields=0,
        )

    field_mapping = FieldMappingResult(
        total_expected_fields=fm_market.total_expected_fields + fm_pool.total_expected_fields,
        matched_fields=fm_market.matched_fields + fm_pool.matched_fields,
        missing_fields=fm_market.missing_fields + fm_pool.missing_fields,
        extra_fields=fm_market.extra_fields + fm_pool.extra_fields,
        type_mismatches=(),
    )

    all_calls = [market, pool]
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

    if not args.live_read:
        overall = OverallVerdict(verdict="pass", memo="dry-run — no real calls made")
        exit_code = EXIT_PASS
    elif any_error and not any_success:
        overall = OverallVerdict(verdict="fail", memo=connectivity.error or "AKShare call failed")
        exit_code = EXIT_FAIL
    else:
        verdict = verdict_for_mapping(field_mapping.matched_ratio)
        overall = OverallVerdict(
            verdict=verdict,
            memo=(
                f"matched_ratio={field_mapping.matched_ratio:.2f} "
                f"({field_mapping.matched_fields}/{field_mapping.total_expected_fields}); "
                f"missing={list(field_mapping.missing_fields)}"
            ),
        )
        exit_code = (
            EXIT_PASS
            if verdict == "pass"
            else EXIT_CONDITIONAL
            if verdict == "conditional_pass"
            else EXIT_FAIL
        )

    report = SmokeReport(
        metadata={
            "capability": "sentiment.market_snapshot+sentiment.limit_up_pool",
            "provider": "akshare",
            "smoke_at": _now_iso(),
            "test_target": date_label,
            "date_range": [date_label, date_label],
        },
        connectivity=connectivity,
        auth=auth,
        permissions=permissions,
        field_mapping=field_mapping,
        data_sample=data_sample,
        vs_fixture=FixtureDeviationResult(()),
        overall=overall,
    )

    yaml_text = smoke_report_to_yaml(report)
    out_dir = Path(args.output_dir).expanduser()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"smoke-sentiment-{datetime.now().strftime('%Y%m%d')}.yaml"
        out_path.write_text(yaml_text, encoding="utf-8")
    except OSError as exc:
        print(f"smoke-sentiment: cannot write report: {exc.__class__.__name__}", file=sys.stderr)
        return 2

    print(yaml_text)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_smoke(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
