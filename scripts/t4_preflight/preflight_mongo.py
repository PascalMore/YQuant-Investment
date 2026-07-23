"""PR-1: MongoDB zero-write preflight CLI (DESIGN V0.12 §15.5 / SPEC §14.2).

Default dry-run: do not instantiate MongoClient, do not connect.
``--live-read`` authorizes the four-step preflight sequence:

1. Resolve the five ``MONGODB_*`` keys via
   :class:`LegacyConfigResolver` from ``skills/.env``.
2. Build a MongoClient with the resolved components
   (``host``, ``port``, ``username``, ``password``, ``authSource``).
3. ``admin.command("ping")`` — connectivity.
4. ``db.list_collection_names()`` — enumerate, plus P3-collection
   presence check.

Hard rules:

* No ``--apply`` / ``--write`` / ``--force`` flags.
* No business-data queries (``find`` / ``aggregate`` / ``count``).
* No collection or index creation.
* No secret value/URI in stdout, stderr, or the YAML report.
* ``MONGODB_DATABASE`` must equal ``"tradingagents"`` (DESIGN
  §15.3 cross-stage rule). Any other value → NOT_AUTHORIZED
  exit 3, no connection.
* ``authSource`` always equals ``MONGODB_DATABASE`` key value.
* No fallback to ``MONGO_URI``, ``MONGODB_URI``, ``./.env``,
  ``~/.hermes/...`` or any other source.

Exit codes (DESIGN §15.5.4 / §15.8):

* 0 → success and no unexpected P3 collections (PASS).
* 1 → ping OK but ``list_collections`` not authorized
      (CONDITIONAL PASS).
* 2 → connectivity failure (DNS / timeout / auth).
* 3 → ``MONGODB_DATABASE`` not equal ``tradingagents`` or any
      of the five keys missing/empty (NOT_AUTHORIZED).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TIMEOUT_SECONDS,
    EXIT_CONDITIONAL,
    EXIT_FAIL,
    EXIT_PASS,
    EXIT_UNAUTHORIZED,
)
from .mongo_client import PreflightRunner
from .models import MongoPreflightResult
from .reporter import to_yaml

__all__ = ["build_arg_parser", "run_preflight", "main"]


_CST = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(tz=_CST).replace(microsecond=0).isoformat()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scripts.t4_preflight.cli preflight-mongo",
        description=(
            "PR-1: Zero-write MongoDB preflight. Default dry-run; "
            "pass --live-read to actually resolve MONGODB_* keys and "
            "ping tradingagents. MONGODB_DATABASE must equal "
            "'tradingagents'."
        ),
    )
    p.add_argument("--live-read", action="store_true", default=False)
    p.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="YAML report output directory.",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Server-selection timeout in seconds.",
    )
    p.add_argument(
        "--uri",
        type=str,
        default=None,
        help=(
            "Legacy/explicit URI override. When omitted (the default "
            "for PR-1 live-read), the resolver reads the five "
            "MONGODB_* keys from skills/.env and builds the client "
            "component-wise. No MONGO_URI / MONGODB_URI / URI "
            "fallback is performed."
        ),
    )
    return p


def _verdict_for(
    live: bool,
    result: MongoPreflightResult,
) -> tuple[int, str]:
    """Map a :class:`MongoPreflightResult` to (exit_code, verdict_str).

    Implements DESIGN §15.5.4 / §15.8.
    """
    if not live:
        return EXIT_PASS, "pass"  # dry-run is informational

    if result.connectivity == "env_missing":
        return EXIT_UNAUTHORIZED, "unauthorized"
    if result.connectivity == "dry_run":
        return EXIT_PASS, "pass"
    if result.connectivity in ("dns_failure", "timeout", "auth_failure"):
        return EXIT_FAIL, "fail"
    if result.p3_collections_found:
        return EXIT_FAIL, "fail"
    if result.collections is None:
        # ping succeeded but listCollections failed
        return EXIT_CONDITIONAL, "conditional_pass"
    return EXIT_PASS, "pass"


def run_preflight(args: argparse.Namespace) -> int:
    """Execute the PR-1 preflight and emit a sanitized YAML report."""
    runner = PreflightRunner()

    if args.live_read:
        if args.uri is not None:
            # Explicit-uri override path (legacy test seam).
            from .mongo_client import MongoClientFactory

            factory = MongoClientFactory()
            result = factory.run_preflight(
                uri=args.uri,
                live=True,
                timeout_seconds=args.timeout,
            )
        else:
            result = runner.run_preflight(live=True, timeout=args.timeout)
    else:
        # Dry-run: still run through PreflightRunner so the report
        # shape matches. PreflightRunner.run_preflight(live=False)
        # returns connectivity="dry_run" without touching the file.
        result = runner.run_preflight(live=False, timeout=args.timeout)

    exit_code, verdict_str = _verdict_for(args.live_read, result)

    payload = {
        "preflight_mongo": {
            "generated_at": _now_iso(),
            "live_read": bool(args.live_read),
            "connectivity": result.connectivity,
            "latency_ms": result.latency_ms,
            "collections": list(result.collections) if result.collections else None,
            "p3_collections_found": list(result.p3_collections_found),
            "warnings": list(result.warnings),
            "detail": result.detail,
        },
        "overall": {
            "verdict": verdict_str,
        },
    }
    yaml_text = to_yaml(payload)

    out_dir = Path(args.output_dir).expanduser()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"preflight-mongo-{datetime.now().strftime('%Y%m%d')}.yaml"
        out_path.write_text(yaml_text, encoding="utf-8")
    except OSError as exc:
        print(
            f"preflight-mongo: cannot write report: {exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 2

    print(yaml_text)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_preflight(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())