"""Draft interfaces for a future unified Argus / Portfolio zone rule engine.

This file is documentation-only. It is not imported by runtime code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ZoneMetrics:
    """Normalized metrics consumed by zone classification and transition rules."""

    confidence: float = 0.0
    bayesian_score: float = 0.0
    contributing_products_count: int = 0
    consensus_confidence: float = 0.0
    crowding_level: str = "LOW"
    crowding_score: float = 0.0
    darwin_moment: bool = False
    darwin_confidence: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ZoneDecision:
    """Decision emitted by the zone rule engine."""

    current_zone: Optional[str]
    target_zone: str
    action: str
    rule_name: str
    passed: bool
    reason: str
    metrics: Dict[str, Any]
    thresholds: Dict[str, Any]


@dataclass(frozen=True)
class ScorePolicy:
    """Score field preference for a rule context."""

    primary: str
    fallback: List[str] = field(default_factory=list)
    missing_default: float = 0.0


@dataclass(frozen=True)
class ZoneRulesConfig:
    """Typed runtime representation of zone rule YAML."""

    zone_order: List[str]
    aliases: Dict[str, str]
    score_policies: Dict[str, ScorePolicy]
    argus_initial_rules: Dict[str, Dict[str, Any]]
    portfolio_thresholds: Dict[str, Dict[str, Any]]
    promotion_path: Dict[str, Dict[str, str]]
    demotion_path: Dict[str, Dict[str, str]]
    crowding_rank: Dict[str, int]
    darwin_override: Dict[str, Any]


class ZoneRuleEngine:
    """Pure rule engine shared by PoolManager, daily_processor, and auto_promoter."""

    def __init__(self, config: ZoneRulesConfig) -> None:
        self.config = config
        self.zone_rank = {zone: idx for idx, zone in enumerate(config.zone_order)}

    @classmethod
    def from_yaml(cls, path: str) -> "ZoneRuleEngine":
        """Load YAML, validate schema, and construct an engine."""
        raise NotImplementedError

    @classmethod
    def from_argus_config(cls, argus_config: Dict[str, Any]) -> "ZoneRuleEngine":
        """Build an engine from existing ARGUS_CONFIG during Phase 1 migration."""
        raise NotImplementedError

    def extract_metrics(self, record: Dict[str, Any]) -> ZoneMetrics:
        """Normalize a signal-pool or stock-pool record into ZoneMetrics."""
        raise NotImplementedError

    def classify_initial_zone(self, metrics: ZoneMetrics) -> ZoneDecision:
        """Classify a new Argus signal-pool record. The result may jump zones."""
        raise NotImplementedError

    def classify_signal_pool_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy of an Argus signal-pool record with pool_zone and decision metadata."""
        decision = self.classify_initial_zone(self.extract_metrics(record))
        return {
            **record,
            "pool_zone": decision.target_zone,
            "zone_decision": {
                "action": decision.action,
                "rule_name": decision.rule_name,
                "reason": decision.reason,
                "metrics": decision.metrics,
                "thresholds": decision.thresholds,
            },
        }

    def evaluate_transition(self, current_zone: str, metrics: ZoneMetrics) -> ZoneDecision:
        """Evaluate one-step Portfolio promotion or demotion for an active entry."""
        raise NotImplementedError

    def zone_delta_action(self, previous_zone: Optional[str], current_zone: str) -> Optional[str]:
        """Return promote/demote/update/None using the configured zone order."""
        if previous_zone is None:
            return "update"
        previous = self.normalize_zone(previous_zone)
        current = self.normalize_zone(current_zone)
        if previous == current:
            return None
        previous_rank = self.zone_rank[previous]
        current_rank = self.zone_rank[current]
        return "promote" if current_rank > previous_rank else "demote"

    def normalize_zone(self, zone: str) -> str:
        """Normalize aliases and validate supported zone values."""
        normalized = str(zone).upper()
        normalized = self.config.aliases.get(normalized, normalized)
        if normalized not in self.zone_rank:
            raise ValueError(f"Unsupported pool zone: {zone}")
        return normalized

