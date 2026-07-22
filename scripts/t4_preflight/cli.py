"""Unified T4 preflight & smoke CLI entry point (DESIGN §15.3.1).

Usage::

    python -m scripts.t4_preflight.cli <command> [--live-read] [options]

Commands
========

``audit-secret``
    PR-0: Secret source non-leaking audit.

``preflight-mongo``
    PR-1: MongoDB zero-write preflight.

``smoke-sector``
    PR-2: AKShare sector.snapshot + sector.ranking smoke.

``smoke-flow``
    PR-3: AKShare flow.capital_flow_daily + northbound_daily smoke.

``smoke-sentiment``
    PR-4: AKShare sentiment.market_snapshot + limit_up_pool smoke.

Forbidden flags (DESIGN §15.3.1)
================================

* ``--apply`` / ``--write`` / ``--exec`` / ``--commit`` — no write
  branches.
* ``--force`` / ``--skip-stop`` — no bypass of stop conditions.
* Secret-value flags — secret sources are loaded from the
  environment, never from the command line.

The CLI is intentionally thin. It delegates to the per-command
``main()`` in the corresponding module.
"""

from __future__ import annotations

import argparse
import sys

__all__ = ["build_parser", "main"]


# Commands whose main() functions live in sibling modules.
from . import audit_secret, preflight_mongo, smoke_sector, smoke_flow, smoke_sentiment  # noqa: E402

_COMMANDS: dict[str, object] = {
    "audit-secret": audit_secret,
    "preflight-mongo": preflight_mongo,
    "smoke-sector": smoke_sector,
    "smoke-flow": smoke_flow,
    "smoke-sentiment": smoke_sentiment,
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.t4_preflight.cli",
        description=(
            "T4 Preflight & Smoke toolchain (DESIGN-03-014 §15). "
            "Default dry-run; pass --live-read on subcommands to "
            "actually call the upstream."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name, mod in _COMMANDS.items():
        # Each subparser is added by the module's own build_arg_parser.
        sub.add_parser(
            name,
            help=mod.__doc__.strip().splitlines()[0] if mod.__doc__ else name,  # type: ignore[union-attr]
            add_help=False,
        )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Parse only the command name; defer the rest to the subcommand.
    args, remaining = parser.parse_known_args(argv)
    mod = _COMMANDS[args.command]
    # Delegate to the subcommand's own main(). The subcommand's parser
    # will re-parse `remaining` (which excludes the command name).
    return mod.main(remaining)  # type: ignore[attr-defined]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
