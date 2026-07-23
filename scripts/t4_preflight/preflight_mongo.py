"""PR-1: MongoDB zero-write preflight CLI (DESIGN §15.5 / SPEC §14.2).

Default dry-run: do not instantiate MongoClient, do not connect.
``--live-read`` authorizes the four-step preflight sequence
(ping → list_collections → check P3 → close).

Hard rules:

* No ``--apply`` / ``--write`` / ``--force`` flags.
* No business-data queries (``find`` / ``aggregate`` / ``count``).
* No collection or index creation.
* No secret value/URI in stdout, stderr, or the YAML report.
* Exit code:

  - 0 → success and no unexpected P3 collections.
  - 1 → success but with warnings (e.g. list_collections
        unauthorized, or unexpected P3 collection that Pascal
        already accepted).
  - 2 → connectivity failure (DNS / timeout / auth).
  - 3 → MONGO_URI not declared (no auth, no smoke).
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
from .mongo_client import MongoClientFactory
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
            "pass --live-read to actually ping the server."
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
        "--mongo-uri",
        type=str,
        default=None,
        help=(
            "Override MONGO_URI. When omitted, the value is read "
            "from os.environ at the moment of invocation. The URI "
            "is never emitted in the report."
        ),
    )
    return p


def run_preflight(args: argparse.Namespace) -> int:
    factory = MongoClientFactory()
    result: MongoPreflightResult = factory.run_preflight(
        uri=args.mongo_uri,
        live=args.live_read,
        timeout_seconds=args.timeout,
    )

    # ----- Verdict --------------------------------------------------------
    if not args.live_read:
        exit_code = EXIT_PASS  # dry-run is informational; not a fail
    elif result.connectivity == "skipped":
        # Either MONGO_URI missing or dry-run
        if "MONGO_URI" in (result.warnings[0] if result.warnings else ""):
            exit_code = EXIT_UNAUTHORIZED
        else:
            exit_code = EXIT_PASS
    elif result.connectivity in ("dns_failure", "timeout", "auth_failure"):
        exit_code = EXIT_FAIL
    elif result.p3_collections_found:
        exit_code = EXIT_FAIL  # Pascal must accept
    elif result.collections is None:
        # list_collections failed but ping succeeded → conditional
        exit_code = EXIT_CONDITIONAL
    else:
        exit_code = EXIT_PASS

    # ----- Output ---------------------------------------------------------
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
            "verdict": (
                "pass"
                if exit_code == EXIT_PASS
                else "conditional_pass"
                if exit_code == EXIT_CONDITIONAL
                else "fail"
                if exit_code == EXIT_FAIL
                else "unauthorized"
            ),
        },
    }
    yaml_text = to_yaml(payload)

    out_dir = Path(args.output_dir).expanduser()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"preflight-mongo-{datetime.now().strftime('%Y%m%d')}.yaml"
        out_path.write_text(yaml_text, encoding="utf-8")
    except OSError as exc:
        print(f"preflight-mongo: cannot write report: {exc.__class__.__name__}", file=sys.stderr)
        return 2

    print(yaml_text)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run_preflight(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
