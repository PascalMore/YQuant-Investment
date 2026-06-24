#!/usr/bin/env python3
"""Print current model + fallback + compression config for every YQuant agent.

This is the single source of truth for "which model does each agent run on".
All YQuant skills reference this script instead of hardcoding model names,
so the docs stay valid across model upgrades.

Usage:
    python3 scripts/infra/print_agent_models.py
    python3 scripts/infra/print_agent_models.py --json
    python3 scripts/infra/print_agent_models.py --agent yquant

The script is read-only. To change a model, edit the relevant profile's
config.yaml directly (e.g. ~/.hermes/profiles/yquant/config.yaml), then
re-run this script to verify.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


# Profile → display name. Order is intentional (orchestrator first, then the
# pipeline roles in execution order). Keep in sync with AGENTS.md.
AGENTS: list[tuple[str, str, str]] = [
    ("yquant",            "YQuant (Orchestrator)",   "Intake / Closeout"),
    ("yquantprincipal",   "YQuant-Codex-Principal",  "RFC / SPEC / Design"),
    ("yquantdeveloper",   "YQuant-Developer-Engineer", "Implement"),
    ("yquanttester",      "YQuant-Test-Engineer",    "Verify"),
    ("yquantreviewer",    "YQuant-Reviewer-Principal", "Review"),
]


def _short_provider(p: str) -> str:
    """custom:minimax → custom:minimax (kept verbatim); bare names stay as-is."""
    return p or "?"


def _load_profile(hermes_home: Path, profile: str) -> dict[str, Any] | None:
    path = hermes_home / "profiles" / profile / "config.yaml"
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception as exc:
        return {"_error": f"failed to parse: {exc}"}


def collect(hermes_home: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile, display, role in AGENTS:
        cfg = _load_profile(hermes_home, profile)
        if cfg is None:
            rows.append({
                "agent": profile,
                "display": display,
                "role": role,
                "primary": "(profile not found)",
                "fallbacks": "",
                "compression": "",
                "reasoning": "",
                "_missing": True,
            })
            continue
        if "_error" in cfg:
            rows.append({
                "agent": profile,
                "display": display,
                "role": role,
                "primary": cfg["_error"],
                "fallbacks": "",
                "compression": "",
                "reasoning": "",
                "_error": True,
            })
            continue

        model = cfg.get("model") or {}
        primary = f"{_short_provider(model.get('provider', '?'))}/{model.get('default', '?')}"

        fbs = cfg.get("fallback_providers") or []
        fallback_str = ", ".join(
            f"{_short_provider(fb.get('provider', '?'))}/{fb.get('model', '?')}"
            for fb in fbs
        ) or "(none)"

        aux = (cfg.get("auxiliary") or {}).get("compression") or {}
        compression_str = (
            f"{_short_provider(aux.get('provider', '?'))}/{aux.get('model', '?')}"
            if aux else "(unset)"
        )

        reasoning = (cfg.get("agent") or {}).get("reasoning_effort", "")

        rows.append({
            "agent": profile,
            "display": display,
            "role": role,
            "primary": primary,
            "fallbacks": fallback_str,
            "compression": compression_str,
            "reasoning": reasoning,
        })
    return rows


def render_table(rows: list[dict[str, Any]]) -> str:
    headers = ["Agent", "Role", "Primary", "Fallbacks", "Compression"]
    str_rows = []
    for r in rows:
        str_rows.append([
            r["agent"],
            r["role"],
            r["primary"],
            r["fallbacks"],
            r["compression"],
        ])
    widths = [max(len(h), *(len(row[i]) for row in str_rows)) for i, h in enumerate(headers)]
    sep = "-+-".join("-" * w for w in widths)
    out = []
    out.append(" | ".join(h.ljust(w) for h, w in zip(headers, widths)))
    out.append(sep)
    for row in str_rows:
        out.append(" | ".join(cell.ljust(w) for cell, w in zip(row, widths)))
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print current model + fallback + compression config for every YQuant agent."
    )
    parser.add_argument(
        "--hermes-home",
        default=str(Path.home() / ".hermes"),
        help="Path to Hermes home (default: ~/.hermes).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    parser.add_argument(
        "--agent",
        help="Only show one agent (profile id, e.g. yquant).",
    )
    args = parser.parse_args()

    hermes_home = Path(args.hermes_home)
    if not hermes_home.is_dir():
        print(f"error: hermes home not found: {hermes_home}", file=sys.stderr)
        return 2

    rows = collect(hermes_home)
    if args.agent:
        rows = [r for r in rows if r["agent"] == args.agent]
        if not rows:
            print(f"error: agent profile '{args.agent}' not in known list", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        print(render_table(rows))
        print()
        print(f"Source: {hermes_home}/profiles/<profile>/config.yaml")
        print("To change a model, edit the profile's config.yaml and re-run this script.")

    return 0


if __name__ == "__main__":
    sys.exit(main())