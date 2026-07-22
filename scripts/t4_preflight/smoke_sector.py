"""PR-2: AKShare sector.snapshot + sector.ranking smoke CLI.

DESIGN-03-014 §15.6 / SPEC-03-014 §14.4 / RFC-03-014 §13.4.

Default dry-run: does not import akshare, does not call it.
``--live-read`` authorizes the two-call sector smoke:

  1. ``akshare.stock_board_industry_cons_em(BK0489)``
  2. ``akshare.stock_board_industry_name_em()``

Both calls are bounded by ``config.AKSHARE_MAX_CALLS``; the client
will refuse a third call. The result is a :class:`SmokeReport`
serialized to YAML via the Sanitizer.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import (
    AKSHARE_MAX_CALLS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TEST_TARGETS,
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
    default_target,
    verdict_for_mapping,
)
from .reporter import smoke_report_to_yaml

__all__ = ["build_arg_parser", "run_smoke", "main"]


_CST = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(tz=_CST).replace(microsecond=0).isoformat()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scripts.t4_preflight.cli smoke-sector",
        description=(
            "PR-2: AKShare sector.snapshot + sector.ranking smoke. "
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
        "--symbol",
        type=str,
        default=DEFAULT_TEST_TARGETS["sector.snapshot"],
        help="Sector code (e.g. BK0489).",
    )
    p.add_argument(
        "--date",
        type=str,
        default=None,
        help="ISO date used for the smoke metadata. Defaults to today.",
    )
    return p


# Expected fields for sector.snapshot per SPEC-03-014 §3.1 (P3-A).
# Kept minimal and forward-compatible with downstream mapping.
_EXPECTED_SECTOR_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "sector_code",
    "sector_name",
    "snapshot_date",
    "close",
    "pct_chg",
    "turnover",
)

_EXPECTED_SECTOR_RANKING_FIELDS: tuple[str, ...] = (
    "sector_code",
    "sector_name",
    "pct_chg",
)


def run_smoke(args: argparse.Namespace) -> int:
    client = AKShareSmokeClient()

    snapshot = client.fetch_sector_snapshot(args.symbol, live=args.live_read)
    ranking = client.fetch_sector_ranking(live=args.live_read)

    snapshot_fields = list(snapshot.actual_fields or [])
    ranking_fields = list(ranking.actual_fields or [])

    if args.live_read and snapshot.connectivity == "success" and snapshot.actual_fields:
        fm_snap = FieldMapper.compare(
            actual_fields=snapshot_fields,
            expected_fields=list(_EXPECTED_SECTOR_SNAPSHOT_FIELDS),
        )
    else:
        fm_snap = FieldMappingResult(
            total_expected_fields=len(_EXPECTED_SECTOR_SNAPSHOT_FIELDS),
            matched_fields=0,
        )

    if args.live_read and ranking.connectivity == "success" and ranking.actual_fields:
        fm_rank = FieldMapper.compare(
            actual_fields=ranking_fields,
            expected_fields=list(_EXPECTED_SECTOR_RANKING_FIELDS),
        )
    else:
        fm_rank = FieldMappingResult(
            total_expected_fields=len(_EXPECTED_SECTOR_RANKING_FIELDS),
            matched_fields=0,
        )

    # Combine the two field mappings into one report.
    total_expected = fm_snap.total_expected_fields + fm_rank.total_expected_fields
    matched = fm_snap.matched_fields + fm_rank.matched_fields
    field_mapping = FieldMappingResult(
        total_expected_fields=total_expected,
        matched_fields=matched,
        missing_fields=fm_snap.missing_fields + fm_rank.missing_fields,
        extra_fields=fm_snap.extra_fields + fm_rank.extra_fields,
        type_mismatches=(),
    )

    # Connectivity / auth / permissions — all derived from the two
    # calls but reported independently.
    any_success = (
        snapshot.connectivity == "success" or ranking.connectivity == "success"
    )
    any_error = (
        snapshot.connectivity in ("error", "timeout", "rate_limited")
        or ranking.connectivity in ("error", "timeout", "rate_limited")
    )

    if args.live_read:
        if any_error and not any_success:
            connectivity = ConnectionResult(
                status="failed",
                latency_ms=None,
                error=snapshot.error or ranking.error,
            )
        else:
            avg_latency = (
                ((snapshot.latency_ms or 0) + (ranking.latency_ms or 0)) / 2
                if (snapshot.latency_ms and ranking.latency_ms)
                else snapshot.latency_ms or ranking.latency_ms
            )
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

    sample_rows = (
        tuple(snapshot.sample or ())
        if snapshot.sample
        else tuple(ranking.sample or ())
    )
    data_sample = DataSampleResult(
        row_count=len(sample_rows),
        sample_rows=sample_rows,
        null_ratio=0.0,
    )

    if not args.live_read:
        overall = OverallVerdict(verdict="pass", memo="dry-run — no real calls made")
        exit_code = EXIT_PASS
    elif any_error and not any_success:
        overall = OverallVerdict(
            verdict="fail",
            memo=(snapshot.error or ranking.error or "AKShare call failed"),
        )
        exit_code = EXIT_FAIL
    else:
        verdict = verdict_for_mapping(field_mapping.matched_ratio)
        overall = OverallVerdict(
            verdict=verdict,
            memo=(
                f"matched_ratio={field_mapping.matched_ratio:.2f} "
                f"({matched}/{total_expected}); "
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

    date_label = args.date or datetime.now(tz=_CST).date().isoformat()

    report = SmokeReport(
        metadata={
            "capability": "sector.snapshot+sector.ranking",
            "provider": "akshare",
            "smoke_at": _now_iso(),
            "test_target": args.symbol,
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
        out_path = out_dir / f"smoke-sector-{datetime.now().strftime('%Y%m%d')}.yaml"
        out_path.write_text(yaml_text, encoding="utf-8")
    except OSError as exc:
        print(f"smoke-sector: cannot write report: {exc.__class__.__name__}", file=sys.stderr)
        return 2

    print(yaml_text)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_smoke(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
