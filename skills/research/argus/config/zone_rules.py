"""Loader for the unified Argus / Portfolio zone rules YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml


REQUIRED_FIELDS = (
    "version",
    "zones",
    "score_policy",
    "argus_signal_pool",
    "portfolio_transitions",
)
DEFAULT_ZONE_RULES_PATH = Path(__file__).with_name("zone_rules_template.yaml")


def load_zone_rules_config(path: Optional[str | Path] = None) -> Dict[str, Any]:
    """Load and validate unified zone-rule configuration."""
    config_path = Path(path) if path is not None else DEFAULT_ZONE_RULES_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    missing = [field for field in REQUIRED_FIELDS if field not in config]
    if missing:
        raise ValueError(f"zone rules config missing required fields: {', '.join(missing)}")

    zones = config.get("zones") or {}
    if not zones.get("order") or not zones.get("default_zone"):
        raise ValueError("zone rules config requires zones.order and zones.default_zone")

    argus_pool = config.get("argus_signal_pool") or {}
    if not argus_pool.get("entry_rules") or not argus_pool.get("evaluation_order"):
        raise ValueError("zone rules config requires argus_signal_pool.entry_rules and evaluation_order")

    transitions = config.get("portfolio_transitions") or {}
    for field in ("promotion_path", "demotion_path", "promote_rules", "demote_rules", "exit_rules"):
        if field not in transitions:
            raise ValueError(f"zone rules config requires portfolio_transitions.{field}")

    return config


ZONE_RULES_CONFIG = load_zone_rules_config()

