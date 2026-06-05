"""Unified zone classification and transition rules for Argus and Portfolio."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ..config.zone_rules import ZONE_RULES_CONFIG, load_zone_rules_config


@dataclass(frozen=True)
class ZoneMetrics:
    """Normalized metrics consumed by zone rules."""

    bayesian_score: float = 0.0
    consensus_confidence: float = 0.0
    contributing_products_count: int = 0
    crowding_level: str = "LOW"
    darwin_moment: bool = False
    darwin_confidence: Optional[float] = None
    missing_from_signal_pool: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ZoneDecision:
    """Rule decision emitted by the zone rule engine."""

    target_zone: Optional[str]
    rule_name: str
    reason: str
    metrics: Dict[str, Any]
    thresholds: Dict[str, Any]
    action: str = "update"
    passed: bool = True


class ZoneRuleEngine:
    """Pure rule engine shared by Argus initial classification and Portfolio transitions."""

    CROWDING_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "DANGER": 3}

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = dict(config)
        zones = self.config["zones"]
        self.zone_order = [str(zone).upper() for zone in zones["order"]]
        self.default_zone = str(zones.get("default_zone", "SCAN")).upper()
        self.aliases = {str(k).upper(): str(v).upper() for k, v in zones.get("legacy_aliases", {}).items()}
        self.zone_rank = {zone: index for index, zone in enumerate(self.zone_order)}
        self.crowding_rank = {
            **self.CROWDING_RANK,
            **{str(k).upper(): int(v) for k, v in self.config.get("crowding", {}).get("rank", {}).items()},
        }

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ZoneRuleEngine":
        """Create an engine from a YAML file."""
        return cls(load_zone_rules_config(path))

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "ZoneRuleEngine":
        """Create an engine from an already-loaded config mapping."""
        return cls(config)

    def classify_initial_zone(self, metrics: ZoneMetrics | Mapping[str, Any]) -> ZoneDecision:
        """Classify an Argus signal-pool record using direct-target entry rules."""
        normalized = self._normalize_metrics(metrics)
        rules = self.config["argus_signal_pool"]["entry_rules"]
        for rule_name in self.config["argus_signal_pool"]["evaluation_order"]:
            rule = rules[rule_name]
            if rule.get("condition") == "otherwise" or self._passes_rule(normalized, rule):
                decision = self._decision(rule.get("target_zone", self.default_zone), rule_name, normalized, rule, "initial")
                return self._apply_darwin_floor(decision, normalized)
        return self._decision(self.default_zone, "default", normalized, {}, "initial")

    def classify_transition(self, metrics: ZoneMetrics | Mapping[str, Any], current_zone: str) -> ZoneDecision:
        """Evaluate exit, then one-step promote, then one-step demote."""
        exit_decision = self.eval_exit(metrics, current_zone)
        if exit_decision is not None:
            return exit_decision
        promote_decision = self.eval_promote(metrics, current_zone)
        if promote_decision is not None:
            return promote_decision
        demote_decision = self.eval_demote(metrics, current_zone)
        if demote_decision is not None:
            return demote_decision
        normalized = self._normalize_metrics(metrics)
        zone = self.normalize_zone(current_zone)
        return ZoneDecision(
            target_zone=zone,
            rule_name="retain",
            reason=f"retain:{zone}",
            metrics=self._metrics_dict(normalized),
            thresholds={},
            action="update",
            passed=False,
        )

    def eval_promote(self, metrics: ZoneMetrics | Mapping[str, Any], current_zone: str) -> Optional[ZoneDecision]:
        """Return a promotion decision when the next-zone rule passes."""
        zone = self.normalize_zone(current_zone)
        path = self.config["portfolio_transitions"]["promotion_path"].get(zone)
        if not path:
            return None
        target_zone = self.normalize_zone(path["target_zone"])
        if target_zone == zone:
            return None
        rule_name = path["rule"]
        rule = self.config["portfolio_transitions"]["promote_rules"][rule_name]
        normalized = self._normalize_metrics(metrics)
        if not self._passes_rule(normalized, rule):
            return None
        return self._decision(target_zone, rule_name, normalized, rule, "promote")

    def eval_demote(self, metrics: ZoneMetrics | Mapping[str, Any], current_zone: str) -> Optional[ZoneDecision]:
        """Return a demotion decision when the current-zone retention rule fails."""
        zone = self.normalize_zone(current_zone)
        path = self.config["portfolio_transitions"]["demotion_path"].get(zone)
        if not path:
            return None
        target_zone = self.normalize_zone(path["target_zone"])
        if target_zone == zone:
            return None
        rule_name = path["rule"]
        rule = self.config["portfolio_transitions"]["demote_rules"][rule_name]
        if rule.get("demote_when") == "never":
            return None
        normalized = self._normalize_metrics(metrics)
        if self._passes_rule(normalized, rule):
            return None
        return self._decision(target_zone, rule_name, normalized, rule, "demote")

    def eval_exit(self, metrics: ZoneMetrics | Mapping[str, Any], current_zone: str) -> Optional[ZoneDecision]:
        """Return an exit decision when the record is missing from the current signal pool."""
        zone = self.normalize_zone(current_zone)
        normalized = self._normalize_metrics(metrics)
        if not normalized.missing_from_signal_pool:
            return None
        rule = self.config["portfolio_transitions"]["exit_rules"].get(zone, {})
        return ZoneDecision(
            target_zone=None,
            rule_name=f"exit_{zone.lower()}",
            reason=rule.get("condition", "missing_from_current_signal_pool"),
            metrics=self._metrics_dict(normalized),
            thresholds=rule,
            action="exit",
        )

    def normalize_zone(self, zone: str) -> str:
        """Normalize legacy aliases and validate supported zones."""
        normalized = self.aliases.get(str(zone).upper(), str(zone).upper())
        if normalized not in self.zone_rank:
            raise ValueError(f"Unsupported pool zone: {zone}")
        return normalized

    def extract_metrics(self, record: Mapping[str, Any]) -> ZoneMetrics:
        """Normalize a raw signal-pool or stock-pool record into ZoneMetrics."""
        products = self._first(record, ("contributing_products", "products"), [])
        product_count_default = len(products) if isinstance(products, list) else 0
        bayesian = self._float(self._first(record, ("bayesian_score", "bayesian", "score", "confidence"), 0.0))
        return ZoneMetrics(
            bayesian_score=bayesian,
            consensus_confidence=self._float(
                self._first(record, ("consensus_confidence", "consensus_score", "consensus", "confidence"), bayesian)
            ),
            contributing_products_count=self._int(
                self._first(
                    record,
                    ("contributing_products_count", "product_count", "products_count"),
                    product_count_default,
                )
            ),
            crowding_level=str(self._first(record, ("crowding_level", "crowding"), "LOW")).upper(),
            darwin_moment=self._bool(self._first(record, ("darwin_moment", "metadata.darwin_moment"), False)),
            darwin_confidence=self._optional_float(
                self._first(record, ("darwin_confidence", "metadata.darwin_confidence"), None)
            ),
            missing_from_signal_pool=self._bool(self._first(record, ("missing_from_signal_pool",), False)),
            raw=dict(record),
        )

    def _apply_darwin_floor(self, decision: ZoneDecision, metrics: ZoneMetrics) -> ZoneDecision:
        override = self.config["argus_signal_pool"].get("darwin_override", {})
        if not override.get("enabled") or not metrics.darwin_moment:
            return decision
        floor_zone = self.normalize_zone(override.get("min_zone", "CANDIDATE"))
        max_forced_zone = self.normalize_zone(override.get("max_forced_zone", floor_zone))
        if self.zone_rank[decision.target_zone or self.default_zone] >= self.zone_rank[floor_zone]:
            return decision
        if not self._passes_darwin_guard(metrics, override.get("score_guard", {})):
            return decision
        target_zone = floor_zone if self.zone_rank[floor_zone] <= self.zone_rank[max_forced_zone] else max_forced_zone
        return ZoneDecision(
            target_zone=target_zone,
            rule_name="darwin_override",
            reason=f"darwin_floor:{target_zone}",
            metrics=decision.metrics,
            thresholds=override,
            action=decision.action,
        )

    def _passes_darwin_guard(self, metrics: ZoneMetrics, guard: Mapping[str, Any]) -> bool:
        checks = []
        if guard.get("bayesian_min") is not None:
            checks.append(metrics.bayesian_score >= float(guard["bayesian_min"]))
        if guard.get("darwin_confidence_min") is not None:
            checks.append((metrics.darwin_confidence or 0.0) >= float(guard["darwin_confidence_min"]))
        return any(checks) if guard.get("operator", "all") == "any" else all(checks)

    def _passes_rule(self, metrics: ZoneMetrics, rule: Mapping[str, Any]) -> bool:
        if rule.get("bayesian_min") is not None and metrics.bayesian_score < float(rule["bayesian_min"]):
            return False
        if rule.get("bayesian_max") is not None and metrics.bayesian_score > float(rule["bayesian_max"]):
            return False
        if (
            rule.get("product_count_min") is not None
            and metrics.contributing_products_count < int(rule["product_count_min"])
        ):
            return False
        if (
            rule.get("product_count_max") is not None
            and metrics.contributing_products_count > int(rule["product_count_max"])
        ):
            return False
        if rule.get("consensus_min") is not None and metrics.consensus_confidence < float(rule["consensus_min"]):
            return False
        if rule.get("crowding_max") is not None:
            current = self.crowding_rank.get(str(metrics.crowding_level).upper(), 0)
            maximum = self.crowding_rank.get(str(rule["crowding_max"]).upper(), max(self.crowding_rank.values()))
            if current > maximum:
                return False
        return True

    def _decision(
        self,
        target_zone: str,
        rule_name: str,
        metrics: ZoneMetrics,
        thresholds: Mapping[str, Any],
        action: str,
    ) -> ZoneDecision:
        return ZoneDecision(
            target_zone=self.normalize_zone(target_zone),
            rule_name=rule_name,
            reason=f"{action}:{rule_name}",
            metrics=self._metrics_dict(metrics),
            thresholds=dict(thresholds),
            action=action,
        )

    def _normalize_metrics(self, metrics: ZoneMetrics | Mapping[str, Any]) -> ZoneMetrics:
        return metrics if isinstance(metrics, ZoneMetrics) else self.extract_metrics(metrics)

    @staticmethod
    def _metrics_dict(metrics: ZoneMetrics) -> Dict[str, Any]:
        return {key: value for key, value in asdict(metrics).items() if key != "raw"}

    @staticmethod
    def _first(record: Mapping[str, Any], keys: tuple[str, ...], default: Any) -> Any:
        for key in keys:
            source: Any = record
            for part in key.split("."):
                if not isinstance(source, Mapping) or part not in source:
                    source = None
                    break
                source = source[part]
            if source is not None:
                return source
        return default

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _optional_float(cls, value: Any) -> Optional[float]:
        return None if value is None else cls._float(value)

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "y"}
        return bool(value)


DEFAULT_ZONE_RULE_ENGINE = ZoneRuleEngine.from_config(ZONE_RULES_CONFIG)

