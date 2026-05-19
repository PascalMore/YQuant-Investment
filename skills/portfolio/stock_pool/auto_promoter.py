"""Automatic promotion and demotion rules for the Portfolio stock pool."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .models import PoolZone
from .service import StockPoolService


class StockPoolAutoPromoter:
    """Evaluate stock pool entries and move them between lifecycle zones."""

    ZONE_THRESHOLDS = {
        "scan_to_watch": {"bayesian_min": 0.30, "product_count_min": 2},
        "watch_to_candidate": {"bayesian_min": 0.50, "consensus_min": 0.40},
        "candidate_to_conviction": {
            "bayesian_min": 0.70,
            "product_count_min": 3,
            "crowding_max": "DANGER",
        },
    }

    PROMOTION_PATH = {
        PoolZone.SCAN.value: (PoolZone.WATCH.value, "scan_to_watch"),
        PoolZone.WATCH.value: (PoolZone.CANDIDATE.value, "watch_to_candidate"),
        PoolZone.CANDIDATE.value: (PoolZone.CONVICTION.value, "candidate_to_conviction"),
    }
    DEMOTION_PATH = {
        PoolZone.WATCH.value: (PoolZone.SCAN.value, "scan_to_watch"),
        PoolZone.CANDIDATE.value: (PoolZone.WATCH.value, "watch_to_candidate"),
        PoolZone.CONVICTION.value: (PoolZone.CANDIDATE.value, "candidate_to_conviction"),
    }
    CROWDING_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "DANGER": 3}

    def __init__(
        self,
        stock_pool_service: StockPoolService,
        thresholds: Optional[Dict[str, Dict[str, Any]]] = None,
        actor: str = "system:auto_promoter",
    ) -> None:
        """Initialize with a stock pool service and optional threshold override."""
        self.stock_pool_service = stock_pool_service
        self.thresholds = thresholds or self.ZONE_THRESHOLDS
        self.actor = actor

    def evaluate_and_promote(self, trade_date: str, dry_run: bool = False) -> Dict[str, Any]:
        """Evaluate active entries and promote one zone when rules are satisfied."""
        summary = self._empty_summary(trade_date, dry_run, "promote")
        for record in self._active_records():
            current_zone = record.get("pool_zone")
            if current_zone not in self.PROMOTION_PATH:
                continue
            target_zone, rule_name = self.PROMOTION_PATH[current_zone]
            thresholds = self.thresholds[rule_name]
            if not self.should_promote(record, target_zone, thresholds):
                summary["skipped"] += 1
                continue
            self._append_or_apply(summary, record, target_zone, rule_name, thresholds, dry_run)
        return summary

    def evaluate_and_demote(self, trade_date: str, dry_run: bool = False) -> Dict[str, Any]:
        """Evaluate active entries and demote one zone when rules are no longer satisfied."""
        summary = self._empty_summary(trade_date, dry_run, "demote")
        for record in self._active_records():
            current_zone = record.get("pool_zone")
            if current_zone not in self.DEMOTION_PATH:
                continue
            target_zone, rule_name = self.DEMOTION_PATH[current_zone]
            thresholds = self.thresholds[rule_name]
            if not self.should_demote(record, thresholds):
                summary["skipped"] += 1
                continue
            self._append_or_apply(summary, record, target_zone, rule_name, thresholds, dry_run)
        return summary

    def should_promote(self, record: Dict[str, Any], target_zone: str, thresholds: Dict[str, Any]) -> bool:
        """Return True when a record satisfies the target zone threshold set."""
        metrics = self._metrics(record)
        return self._passes_thresholds(metrics, thresholds)

    def should_demote(self, record: Dict[str, Any], thresholds: Dict[str, Any]) -> bool:
        """Return True when a record fails the threshold set for its current zone."""
        metrics = self._metrics(record)
        return not self._passes_thresholds(metrics, thresholds)

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

    def _passes_thresholds(self, metrics: Dict[str, Any], thresholds: Dict[str, Any]) -> bool:
        if metrics["bayesian"] < float(thresholds.get("bayesian_min", 0)):
            return False
        if "product_count_min" in thresholds and metrics["product_count"] < int(thresholds["product_count_min"]):
            return False
        if "consensus_min" in thresholds and metrics["consensus"] < float(thresholds["consensus_min"]):
            return False
        if "crowding_max" in thresholds:
            current = self.CROWDING_RANK.get(str(metrics["crowding_level"]).upper(), 0)
            maximum = self.CROWDING_RANK.get(str(thresholds["crowding_max"]).upper(), 3)
            if current > maximum:
                return False
        return True

    def _metrics(self, record: Dict[str, Any]) -> Dict[str, Any]:
        reason = record.get("entry_reason") or {}
        metadata = reason.get("metadata") or {}
        sources = [record, reason, metadata]
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

    @staticmethod
    def _empty_summary(trade_date: str, dry_run: bool, action: str) -> Dict[str, Any]:
        return {
            "trade_date": trade_date,
            "action": action,
            "dry_run": dry_run,
            "evaluated_at": datetime.utcnow().isoformat(),
            "matched": 0,
            "changed": 0,
            "skipped": 0,
            "errors": [],
            "items": [],
        }
