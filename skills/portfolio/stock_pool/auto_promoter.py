"""Automatic promotion and demotion rules for the Portfolio stock pool."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .service import StockPoolService
from skills.research.argus.config.zone_rules import DEFAULT_ZONE_RULES_PATH
from skills.research.argus.core.zone_rule_engine import ZoneRuleEngine


class StockPoolAutoPromoter:
    """Evaluate stock pool entries and move them between lifecycle zones."""

    def __init__(
        self,
        stock_pool_service: StockPoolService,
        thresholds: Optional[Dict[str, Dict[str, Any]]] = None,
        actor: str = "system:auto_promoter",
        zone_rule_engine: Optional[ZoneRuleEngine] = None,
        zone_rules_path: Optional[str | Path] = None,
    ) -> None:
        """Initialize with a stock pool service and YAML-backed zone rule engine."""
        self.stock_pool_service = stock_pool_service
        # Deprecated compatibility argument. Runtime thresholds are owned by ZoneRuleEngine.
        _ = thresholds
        self.actor = actor
        self.zone_rules_path = Path(zone_rules_path or DEFAULT_ZONE_RULES_PATH)
        self.zone_rules_loaded_at = datetime.utcnow()
        self.zone_engine = zone_rule_engine or ZoneRuleEngine.from_yaml(self.zone_rules_path)

    def evaluate_and_promote(self, trade_date: str, dry_run: bool = False) -> Dict[str, Any]:
        """Evaluate active entries and promote one zone when rules are satisfied."""
        summary = self._empty_summary(trade_date, dry_run, "promote")
        for record in self._active_records():
            current_zone = record.get("pool_zone")
            decision = self._eval_promote(record, current_zone)
            if decision is None:
                if self._has_transition_path("promote", current_zone):
                    summary["skipped"] += 1
                continue
            self._append_or_apply(summary, record, decision.target_zone, decision.rule_name, decision.thresholds, dry_run)
        return summary

    def evaluate_and_demote(self, trade_date: str, dry_run: bool = False) -> Dict[str, Any]:
        """Evaluate active entries and demote one zone when rules are no longer satisfied."""
        summary = self._empty_summary(trade_date, dry_run, "demote")
        for record in self._active_records():
            current_zone = record.get("pool_zone")
            decision = self._eval_demote(record, current_zone)
            if decision is None:
                if self._has_transition_path("demote", current_zone):
                    summary["skipped"] += 1
                continue
            self._append_or_apply(summary, record, decision.target_zone, decision.rule_name, decision.thresholds, dry_run)
        return summary

    def _eval_promote(self, record: Dict[str, Any], current_zone: Optional[str]):
        """Evaluate YAML-backed one-step promotion."""
        if not current_zone:
            return None
        decision = self.zone_engine.eval_promote(self._record_for_engine(record, current_zone), current_zone)
        return decision

    def _eval_demote(self, record: Dict[str, Any], current_zone: Optional[str]):
        """Evaluate YAML-backed one-step demotion with hysteresis retention thresholds."""
        if not current_zone:
            return None
        return self.zone_engine.eval_demote(self._record_for_engine(record, current_zone), current_zone)

    def _eval_exit(self, record: Dict[str, Any], current_zone: Optional[str]):
        """Evaluate YAML-backed lifecycle exit."""
        if not current_zone:
            return None
        return self.zone_engine.eval_exit(self._record_for_engine(record, current_zone), current_zone)

    def _has_transition_path(self, action: str, current_zone: Optional[str]) -> bool:
        """Return whether YAML defines an actionable one-step transition for this zone."""
        if not current_zone:
            return False
        try:
            zone = self.zone_engine.normalize_zone(current_zone)
        except ValueError:
            return False

        transitions = self.zone_engine.config["portfolio_transitions"]
        path_key = "promotion_path" if action == "promote" else "demotion_path"
        rules_key = "promote_rules" if action == "promote" else "demote_rules"
        path = transitions[path_key].get(zone)
        if not path:
            return False
        if self.zone_engine.normalize_zone(path["target_zone"]) == zone:
            return False
        rule = transitions[rules_key].get(path["rule"], {})
        return rule.get("demote_when") != "never"

    def should_promote(self, record: Dict[str, Any], target_zone: str, thresholds: Dict[str, Any]) -> bool:
        """Return True when a record satisfies the target zone threshold set."""
        current_zone = record.get("pool_zone")
        decision = self._eval_promote(record, current_zone)
        return decision is not None and decision.target_zone == target_zone

    def should_demote(self, record: Dict[str, Any], thresholds: Dict[str, Any]) -> bool:
        """Return True when a record fails the threshold set for its current zone."""
        return self._eval_demote(record, record.get("pool_zone")) is not None

    def _active_records(self) -> Iterable[Dict[str, Any]]:
        cursor: Optional[str] = None
        while True:
            page = self.stock_pool_service.get_pool(status="active", limit=200, cursor=cursor)
            yield from page["items"]
            cursor = page.get("next_cursor")
            if not cursor:
                break

    def _append_or_apply(
        self,
        summary: Dict[str, Any],
        record: Dict[str, Any],
        target_zone: str,
        rule_name: str,
        thresholds: Dict[str, Any],
        dry_run: bool,
    ) -> None:
        item = {
            "id": record["id"],
            "wind_code": record.get("wind_code"),
            "stock_name": record.get("stock_name"),
            "from_zone": record.get("pool_zone"),
            "target_zone": target_zone,
            "rule": rule_name,
            "metrics": self._metrics(record),
            "thresholds": thresholds,
        }
        summary["items"].append(item)
        summary["matched"] += 1
        if dry_run:
            return
        reason = f"{summary['action']}:{rule_name}"
        if self.stock_pool_service.move_entry(record["id"], target_zone, reason, self.actor):
            summary["changed"] += 1
        else:
            summary["errors"].append({"id": record["id"], "error": "transition_failed"})

    def _metrics(self, record: Dict[str, Any]) -> Dict[str, Any]:
        sources = [record]
        products = self._first(sources, ["contributing_products", "products"], [])
        return {
            "bayesian": self._float(self._first(sources, ["bayesian_score", "bayesian", "score", "confidence"], 0)),
            "product_count": self._int(
                self._first(
                    sources,
                    ["contributing_products_count", "product_count", "products_count"],
                    len(products) if isinstance(products, list) else 0,
                )
            ),
            "consensus": self._float(
                self._first(sources, ["consensus_confidence", "consensus_score", "consensus"], 0)
            ),
            "crowding_level": str(self._first(sources, ["crowding_level", "crowding"], "LOW")).upper(),
        }

    def _record_for_engine(self, record: Dict[str, Any], current_zone: str) -> Dict[str, Any]:
        engine_record = dict(record)
        metrics = self._metrics(record)
        engine_record.setdefault("bayesian_score", metrics["bayesian"])
        engine_record.setdefault("consensus_confidence", metrics["consensus"])
        engine_record.setdefault("crowding_level", metrics["crowding_level"])
        if engine_record.get("contributing_products_count") is None:
            engine_record["contributing_products_count"] = metrics["product_count"]
        if engine_record.get("crowding_level") is None:
            engine_record["crowding_level"] = metrics["crowding_level"]
        return engine_record

    def _rule_source(self) -> Dict[str, Any]:
        try:
            stat = self.zone_rules_path.stat()
            modified_at = datetime.utcfromtimestamp(stat.st_mtime).isoformat()
        except OSError:
            modified_at = None
        return {
            "type": "yaml",
            "path": str(self.zone_rules_path),
            "loaded_at": self.zone_rules_loaded_at.isoformat(),
            "modified_at": modified_at,
            "version": self.zone_engine.config.get("version"),
        }

    @staticmethod
    def _first(sources: Iterable[Dict[str, Any]], keys: List[str], default: Any) -> Any:
        for source in sources:
            for key in keys:
                value = source.get(key)
                if value is not None:
                    return value
        return default

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _empty_summary(self, trade_date: str, dry_run: bool, action: str) -> Dict[str, Any]:
        return {
            "trade_date": trade_date,
            "action": action,
            "dry_run": dry_run,
            "evaluated_at": datetime.utcnow().isoformat(),
            "rule_source": self._rule_source(),
            "matched": 0,
            "changed": 0,
            "skipped": 0,
            "errors": [],
            "items": [],
        }
