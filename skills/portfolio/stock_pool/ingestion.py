"""Signal ingestion service for Portfolio stock pool entries."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import PoolZone
from .service import StockPoolService
from skills.research.argus.core.zone_rule_engine import DEFAULT_ZONE_RULE_ENGINE, ZoneRuleEngine


ARGUS_TO_PORTFOLIO_ZONE = {
    "SCAN": "SCAN",
    "WATCH": "WATCH",
    "CANDIDATE": "CANDIDATE",
    "CONVICTION": "CONVICTION",
    "FOCUS": "CONVICTION",
}
INGEST_MODES = {"upsert_all", "upsert_scan_only", "dry_run"}
ZONE_RANK = {
    PoolZone.SCAN.value: 0,
    PoolZone.WATCH.value: 1,
    PoolZone.CANDIDATE.value: 2,
    PoolZone.CONVICTION.value: 3,
}
INCREMENTAL_UPDATE_FIELDS = (
    "tags",
    "memo",
    "source_project",
    "entry_reason",
)
STOCK_POOL_METRIC_FIELDS = (
    "bayesian_score",
    "crowding_level",
    "crowding_score",
    "consensus_confidence",
    "contributing_products",
    "contributing_products_count",
    "darwin_moment",
    "missing_from_signal_pool",
)


class StockPoolIngestionService:
    """Consume external research signals through the stock pool service boundary."""

    def __init__(self, stock_pool_service: StockPoolService) -> None:
        """Initialize ingestion with an existing StockPoolService."""
        self.stock_pool_service = stock_pool_service
        self.zone_engine = DEFAULT_ZONE_RULE_ENGINE

    def ingest_signals(
        self,
        source: str,
        signals: List[Dict[str, Any]],
        mode: str = "upsert_scan_only",
        actor: str = "system:argus",
    ) -> Dict[str, Any]:
        """Upsert signal-derived stock pool entries and return an ingestion summary."""
        if mode not in INGEST_MODES:
            raise ValueError(f"Unsupported ingestion mode: {mode}")

        summary: Dict[str, Any] = {
            "source": source,
            "mode": mode,
            "received": len(signals),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
            "items": [],
        }
        for signal in signals:
            try:
                record = self._normalize_record(source, signal, classify_initial=False)
                if mode == "upsert_scan_only" and record["pool_zone"] != PoolZone.SCAN.value:
                    summary["skipped"] += 1
                    continue
                if mode == "dry_run":
                    summary["items"].append({"action": "dry_run", "wind_code": record["wind_code"]})
                    continue
                self._upsert_record(record, actor, summary)
            except (KeyError, ValueError) as exc:
                summary["errors"].append({"signal": signal.get("signal_id"), "error": str(exc)})
                summary["skipped"] += 1
        return summary

    def ingest_signals_incremental(
        self,
        current_signals: List[Dict[str, Any]],
        previous_signals: List[Dict[str, Any]],
        actor: str,
        event_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync Argus signal-pool deltas into Portfolio stock pool with fine-grained audit.
        
        Args:
            current_signals: Today's argus_signal_pool records
            previous_signals: Yesterday's argus_signal_pool records
            actor: Who performed the action (e.g., 'system:argus', 'system:argus_backfill')
            event_date: The date of the data (from current_signals[0]['date']), used as audit event_date
        """
        # Extract event_date from current signals if not provided
        if not event_date and current_signals:
            event_date = current_signals[0].get('date')
        
        summary: Dict[str, Any] = {
            "source": "argus",
            "mode": "incremental",
            "current": len(current_signals),
            "previous": len(previous_signals),
            "entry": 0,
            "promote": 0,
            "demote": 0,
            "exit": 0,
            "update": 0,
            "skipped": 0,
            "errors": [],
            "items": [],
        }

        current_by_code = self._normalize_signal_map(current_signals, summary, "current")
        previous_by_code = self._normalize_signal_map(previous_signals, summary, "previous")

        for wind_code in sorted(set(current_by_code) | set(previous_by_code)):
            current = current_by_code.get(wind_code)
            previous = previous_by_code.get(wind_code)
            try:
                if current and not previous:
                    self._apply_entry(current, actor, summary, event_date)
                elif previous and not current:
                    self._apply_exit(previous, actor, summary, event_date)
                elif current and previous:
                    self._apply_existing_delta(current, previous, actor, summary, event_date)
            except (KeyError, ValueError) as exc:
                summary["errors"].append({"wind_code": wind_code, "error": str(exc)})
                summary["skipped"] += 1
        return summary

    def map_argus_zone(self, argus_zone: str) -> str:
        """Map an Argus lifecycle zone to a Portfolio stock pool zone."""
        normalized = str(argus_zone).upper()
        if normalized not in ARGUS_TO_PORTFOLIO_ZONE:
            raise ValueError(f"Unsupported Argus pool zone: {argus_zone}")
        return ARGUS_TO_PORTFOLIO_ZONE[normalized]

    def _normalize_record(
        self,
        source: str,
        signal: Dict[str, Any],
        classify_initial: bool = True,
    ) -> Dict[str, Any]:
        zone = signal.get("pool_zone") or (signal.get("metadata") or {}).get("pool_zone") or "SCAN"
        record = dict(signal)
        record["source"] = source
        record.setdefault("source_project", source)
        record["stock_code"] = record.get("stock_code") or str(record["wind_code"]).split(".")[0]
        record.setdefault("tags", [])
        record.setdefault("memo", "")
        self._apply_stock_pool_metrics(record)
        if classify_initial:
            record["pool_zone"] = self.zone_engine.classify_initial_zone(record).target_zone
        else:
            record["pool_zone"] = self.map_argus_zone(zone) if source == "argus" else PoolZone(zone).value
        if not self._is_structured_entry_reason(record.get("entry_reason")):
            record["entry_reason"] = self._build_entry_reason(record, "new_entry", None, record["pool_zone"])
        return record

    @staticmethod
    def _is_structured_entry_reason(value: Any) -> bool:
        """Return True when entry_reason already follows the new structured schema."""
        return (
            isinstance(value, dict)
            and isinstance(value.get("reason"), str)
            and value.get("trigger") in {"promote", "demote", "new_entry", "update", "exit"}
        )

    @staticmethod
    def _build_entry_reason(
        record: Dict[str, Any],
        trigger: str,
        from_zone: Optional[str],
        to_zone: Optional[str],
    ) -> Dict[str, Any]:
        """Build a machine-readable, human-readable stock pool transition reason."""
        reason = StockPoolIngestionService._entry_reason_text(
            record.get("wind_code", ""),
            trigger,
            from_zone,
            to_zone,
            record,
        )
        return {
            "reason": reason,
            "trigger": trigger,
            "from_zone": from_zone,
            "to_zone": to_zone,
        }

    @staticmethod
    def _entry_reason_metrics(record: Dict[str, Any]) -> Dict[str, Any]:
        """Extract stock pool metrics from a signal-pool record."""
        old_reason = record.get("entry_reason") if isinstance(record.get("entry_reason"), dict) else {}
        product_candidates = (
            record.get("contributing_products"),
            old_reason.get("contributing_products"),
        )
        products = next((value for value in product_candidates if isinstance(value, list)), [])
        product_count = (
            (len(products) if isinstance(products, list) else 0)
            or record.get("contributing_products_count")
            or (record.get("contributing_products") if isinstance(record.get("contributing_products"), int) else 0)
            or old_reason.get("contributing_products_count")
            or 0
        )
        return {
            "bayesian_score": StockPoolIngestionService._float(
                record.get("bayesian_score")
                or old_reason.get("bayesian_score")
                or record.get("confidence")
                or old_reason.get("confidence")
            ),
            "consensus_confidence": StockPoolIngestionService._float(
                record.get("consensus_confidence")
                or old_reason.get("consensus_confidence")
                or record.get("consensus_score")
                or old_reason.get("consensus_score")
            ),
            "crowding_level": str(
                record.get("crowding_level")
                or old_reason.get("crowding_level")
                or "LOW"
            ).upper(),
            "crowding_score": StockPoolIngestionService._float(
                record.get("crowding_score")
                or old_reason.get("crowding_score")
            ),
            "contributing_products": products,
            "contributing_products_count": StockPoolIngestionService._int(product_count),
            "darwin_moment": bool(
                record.get("darwin_moment")
                or old_reason.get("darwin_moment")
                or (record.get("metadata") or {}).get("darwin_moment")
            ),
            "missing_from_signal_pool": bool(record.get("missing_from_signal_pool", False)),
        }

    @staticmethod
    def _apply_stock_pool_metrics(record: Dict[str, Any]) -> Dict[str, Any]:
        """Write extracted metrics to stock_pool top-level fields."""
        metrics = StockPoolIngestionService._entry_reason_metrics(record)
        products = metrics.get("contributing_products") or []
        product_count = StockPoolIngestionService._int(metrics.get("contributing_products_count"))
        top_level_metrics = {
            "bayesian_score": metrics["bayesian_score"],
            "crowding_level": metrics["crowding_level"],
            "crowding_score": metrics["crowding_score"],
            "consensus_confidence": metrics["consensus_confidence"],
            "contributing_products": products,
            "contributing_products_count": product_count,
            "darwin_moment": metrics["darwin_moment"],
            "missing_from_signal_pool": metrics["missing_from_signal_pool"],
        }
        record.update(top_level_metrics)
        return top_level_metrics

    @staticmethod
    def _entry_reason_text(
        wind_code: str,
        trigger: str,
        from_zone: Optional[str],
        to_zone: Optional[str],
        record: Dict[str, Any],
    ) -> str:
        metrics = StockPoolIngestionService._entry_reason_metrics(record)
        score = metrics["bayesian_score"]
        crowding = metrics["crowding_level"]
        product_count = metrics["contributing_products_count"]
        reason = (
            f"{wind_code} bayesian={score:.2f}, "
            f"crowding={crowding}, contributing_products={product_count}"
        )
        if trigger == "exit":
            return "Exit: no supporting products or crowding maxed"
        if trigger == "new_entry":
            return f"New entry: {reason}"
        if trigger == "promote":
            return f"Promote: {from_zone}→{to_zone}: {reason}"
        if trigger == "demote":
            return f"Demote: {from_zone}→{to_zone}: {reason}"
        return f"Update: {wind_code} metrics refreshed, bayesian={score:.2f}, crowding={crowding}"

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

    def _upsert_record(self, record: Dict[str, Any], actor: str, summary: Dict[str, Any]) -> None:
        existing = self.stock_pool_service.get_pool(
            wind_code=record["wind_code"],
            source=record["source"],
            status="active",
            limit=1,
        )["items"]
        if existing:
            record_id = existing[0]["id"]
            patch = {
                "pool_zone": record["pool_zone"],
                "entry_reason": record["entry_reason"],
                "tags": record.get("tags", []),
                "memo": record.get("memo", ""),
                "source_project": record.get("source_project"),
                **{field_name: record.get(field_name) for field_name in STOCK_POOL_METRIC_FIELDS},
            }
            self.stock_pool_service.update_entry(record_id, patch, actor)
            summary["updated"] += 1
            summary["items"].append({"action": "updated", "id": record_id, "wind_code": record["wind_code"]})
            return

        record_id = self.stock_pool_service.create_entry(record, actor)
        summary["created"] += 1
        summary["items"].append({"action": "created", "id": record_id, "wind_code": record["wind_code"]})

    def _normalize_signal_map(
        self,
        signals: List[Dict[str, Any]],
        summary: Dict[str, Any],
        label: str,
    ) -> Dict[str, Dict[str, Any]]:
        records: Dict[str, Dict[str, Any]] = {}
        for signal in signals:
            try:
                record = self._normalize_record("argus", signal, classify_initial=True)
                records[record["wind_code"]] = record
            except (KeyError, ValueError) as exc:
                summary["errors"].append({"dataset": label, "signal": signal.get("signal_id"), "error": str(exc)})
                summary["skipped"] += 1
        return records

    def _apply_entry(self, record: Dict[str, Any], actor: str, summary: Dict[str, Any], event_date: Optional[str] = None) -> None:
        existing = self._active_record(record["wind_code"])
        if existing:
            # The Portfolio stock_pool zone is authoritative for existing records.
            # Incremental ingestion only refreshes metrics and clears a stale
            # missing marker; state transitions run in StockPoolTransitionPipeline.
            zone_action = "update"
            record["entry_reason"] = self._build_entry_reason(
                record,
                zone_action,
                existing.get("pool_zone"),
                existing.get("pool_zone"),
            )
            patch = self._changed_field_patch(existing, record, include_zone=False)
            self._apply_record_update(existing["id"], record, zone_action, actor, summary, patch, event_date=event_date)
            return
        record["entry_reason"] = self._build_entry_reason(record, "new_entry", None, record.get("pool_zone"))
        record_id = self.stock_pool_service.create_entry(record, actor, event_date=event_date)
        summary["entry"] += 1
        summary["items"].append({"action": "entry", "id": record_id, "wind_code": record["wind_code"]})

    def _apply_exit(self, record: Dict[str, Any], actor: str, summary: Dict[str, Any], event_date: Optional[str] = None) -> None:
        existing = self._active_record(record["wind_code"])
        if not existing:
            summary["skipped"] += 1
            summary["items"].append({"action": "skip_exit_missing", "wind_code": record["wind_code"]})
            return
        entry_reason = self._build_entry_reason(
            record,
            "exit",
            existing.get("pool_zone"),
            None,
        )
        changed = self.stock_pool_service.update_entry(
            existing["id"],
            {"entry_reason": entry_reason, "missing_from_signal_pool": True},
            actor,
            audit_action="update",
            event_date=event_date,
        )
        summary["exit"] += 1
        summary["items"].append(
            {
                "action": "mark_missing_from_signal_pool" if changed else "missing_already_marked",
                "id": existing["id"],
                "wind_code": record["wind_code"],
            }
        )

    def _apply_existing_delta(
        self,
        current: Dict[str, Any],
        previous: Dict[str, Any],
        actor: str,
        summary: Dict[str, Any],
        event_date: Optional[str] = None,
    ) -> None:
        existing = self._active_record(current["wind_code"])
        if not existing:
            current["entry_reason"] = self._build_entry_reason(current, "new_entry", None, current.get("pool_zone"))
            record_id = self.stock_pool_service.create_entry(current, actor, event_date=event_date)
            summary["entry"] += 1
            summary["items"].append({"action": "entry", "id": record_id, "wind_code": current["wind_code"]})
            return

        action = "update"
        current["entry_reason"] = self._build_entry_reason(
            current,
            action,
            existing.get("pool_zone"),
            existing.get("pool_zone"),
        )
        patch = self._changed_field_patch(existing, current, include_zone=False)

        self._apply_record_update(existing["id"], current, action, actor, summary, patch, event_date=event_date)

    def _apply_record_update(
        self,
        record_id: str,
        record: Dict[str, Any],
        action: str,
        actor: str,
        summary: Dict[str, Any],
        patch: Dict[str, Any] | None = None,
        event_date: Optional[str] = None,
    ) -> None:
        # If caller passed a patch, use it. Otherwise compute from DB.
        existing_record = self.stock_pool_service.repository.get_by_id(record_id) or {}
        computed_patch = self._changed_field_patch(existing_record, record, include_zone=False)
        patch = patch if patch is not None else computed_patch
        if not patch:
            summary["skipped"] += 1
            summary["items"].append({"action": "no_change", "id": record_id, "wind_code": record["wind_code"]})
            return
        if self.stock_pool_service.update_entry(record_id, patch, actor, audit_action=action, event_date=event_date):
            summary[action] += 1
            summary["items"].append({"action": action, "id": record_id, "wind_code": record["wind_code"]})

    def _active_record(self, wind_code: str) -> Dict[str, Any] | None:
        items = self.stock_pool_service.get_pool(
            wind_code=wind_code,
            source="argus",
            status="active",
            limit=1,
        )["items"]
        return items[0] if items else None

    @staticmethod
    def _zone_delta_action(previous_zone: str | None, current_zone: str) -> str | None:
        """Determine audit action from zone transition.

        Args:
            previous_zone: Previous zone (or None if stock had no prior signal_pool record,
                          which can happen after holiday gaps - stock existed in stock_pool
                          but not in previous_signal_pool for that date)
            current_zone: Current zone

        Returns:
            'promote' if current_rank > previous_rank,
            'demote' if current_rank < previous_rank,
            None if previous_zone is None (unknown) or no change — caller must
                resolve by querying stock_pool directly.
        """
        if previous_zone is None or previous_zone not in ZONE_RANK:
            return None  # Unknown — caller should check stock_pool zone
        if current_zone not in ZONE_RANK:
            return "update"
        previous_rank = ZONE_RANK[previous_zone]
        current_rank = ZONE_RANK[current_zone]
        if current_rank > previous_rank:
            return "promote"
        if current_rank < previous_rank:
            return "demote"
        return None

    @staticmethod
    def _changed_field_patch(
        existing: Dict[str, Any],
        record: Dict[str, Any],
        include_zone: bool,
    ) -> Dict[str, Any]:
        field_names = ("pool_zone", *INCREMENTAL_UPDATE_FIELDS) if include_zone else INCREMENTAL_UPDATE_FIELDS
        field_names = (*field_names, *STOCK_POOL_METRIC_FIELDS)
        return {
            field_name: record.get(field_name)
            for field_name in field_names
            if existing.get(field_name) != record.get(field_name)
        }


class StockPoolTransitionPipeline:
    """Run Argus signal ingestion followed by Portfolio stock_pool state transitions."""

    def __init__(
        self,
        ingestion_service: StockPoolIngestionService,
        zone_rule_engine: Optional[ZoneRuleEngine] = None,
    ) -> None:
        self.ingestion_service = ingestion_service
        self.stock_pool_service = ingestion_service.stock_pool_service
        self.zone_engine = zone_rule_engine or DEFAULT_ZONE_RULE_ENGINE

    def run_incremental_transition(
        self,
        current_signals: List[Dict[str, Any]],
        previous_signals: List[Dict[str, Any]],
        actor: str = "system:argus",
        event_date: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Sync metrics, then execute one-step zone transitions from current stock_pool state."""
        if not event_date and current_signals:
            event_date = current_signals[0].get("date")

        ingestion_summary = None
        if not dry_run:
            ingestion_summary = self.ingestion_service.ingest_signals_incremental(
                current_signals=current_signals,
                previous_signals=previous_signals,
                actor=actor,
                event_date=event_date,
            )

        summary: Dict[str, Any] = {
            "source": "argus",
            "mode": "incremental_transition",
            "dry_run": dry_run,
            "current": len(current_signals),
            "previous": len(previous_signals),
            "ingestion": ingestion_summary,
            "entry": 0 if ingestion_summary is None else ingestion_summary.get("entry", 0),
            "exit": 0,
            "promote": 0,
            "demote": 0,
            "retain": 0,
            "update": 0,
            "skipped": 0,
            "errors": [],
            "items": [],
        }

        current_by_code = self._normalized_map(current_signals, summary, "current")
        previous_by_code = self._normalized_map(previous_signals, summary, "previous")
        new_entry_ids = self._new_entry_ids(ingestion_summary)
        for record in self._active_records():
            if record["id"] in new_entry_ids:
                summary["items"].append(
                    {
                        "action": "entry_initial_zone",
                        "id": record["id"],
                        "wind_code": record.get("wind_code"),
                        "target_zone": record.get("pool_zone"),
                    }
                )
                continue
            try:
                transition_record = self._record_for_transition(record, current_by_code, previous_by_code)
                decision = self.zone_engine.classify_transition(transition_record, record.get("pool_zone", "SCAN"))
                self._append_or_apply(summary, record, transition_record, decision, actor, event_date, dry_run)
            except (KeyError, ValueError) as exc:
                summary["errors"].append({"wind_code": record.get("wind_code"), "error": str(exc)})
                summary["skipped"] += 1
        return summary

    def _normalized_map(
        self,
        signals: List[Dict[str, Any]],
        summary: Dict[str, Any],
        label: str,
    ) -> Dict[str, Dict[str, Any]]:
        normalize_summary = {"errors": [], "skipped": 0}
        records = self.ingestion_service._normalize_signal_map(signals, normalize_summary, label)
        summary["errors"].extend(normalize_summary["errors"])
        summary["skipped"] += normalize_summary["skipped"]
        return records

    @staticmethod
    def _new_entry_ids(ingestion_summary: Optional[Dict[str, Any]]) -> set[str]:
        if not ingestion_summary:
            return set()
        return {
            item["id"]
            for item in ingestion_summary.get("items", [])
            if item.get("action") == "entry" and item.get("id")
        }

    def _active_records(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            page = self.stock_pool_service.get_pool(
                source="argus",
                status="active",
                limit=200,
                cursor=cursor,
            )
            records.extend(page["items"])
            cursor = page.get("next_cursor")
            if not cursor:
                return records

    @staticmethod
    def _record_for_transition(
        record: Dict[str, Any],
        current_by_code: Dict[str, Dict[str, Any]],
        previous_by_code: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        transition_record = dict(record)
        wind_code = record.get("wind_code")
        if wind_code in current_by_code:
            for field_name in STOCK_POOL_METRIC_FIELDS:
                transition_record[field_name] = current_by_code[wind_code].get(field_name)
            transition_record["missing_from_signal_pool"] = False
        elif wind_code in previous_by_code:
            transition_record["missing_from_signal_pool"] = True
        return transition_record

    def _append_or_apply(
        self,
        summary: Dict[str, Any],
        record: Dict[str, Any],
        transition_record: Dict[str, Any],
        decision: Any,
        actor: str,
        event_date: Optional[str],
        dry_run: bool,
    ) -> None:
        action = "retain" if decision.action == "update" and decision.target_zone == record.get("pool_zone") else decision.action
        item = {
            "action": action,
            "id": record["id"],
            "wind_code": record.get("wind_code"),
            "from_zone": record.get("pool_zone"),
            "target_zone": decision.target_zone,
            "rule": decision.rule_name,
            "metrics": decision.metrics,
            "thresholds": decision.thresholds,
        }
        summary["items"].append(item)
        if dry_run:
            summary[action] += 1
            return

        if action == "exit":
            reason = StockPoolIngestionService._entry_reason_text(
                record.get("wind_code", ""),
                "exit",
                record.get("pool_zone"),
                None,
                transition_record,
            )
            if self.stock_pool_service.deactivate_entry(record["id"], reason, actor, audit_action="exit", event_date=event_date):
                summary["exit"] += 1
            else:
                summary["errors"].append({"id": record["id"], "error": "exit_failed"})
            return

        if action in {"promote", "demote"}:
            entry_reason = StockPoolIngestionService._build_entry_reason(
                transition_record,
                action,
                record.get("pool_zone"),
                decision.target_zone,
            )
            patch = {
                "pool_zone": decision.target_zone,
                "entry_reason": entry_reason,
                "missing_from_signal_pool": False,
            }
            if self.stock_pool_service.update_entry(record["id"], patch, actor, audit_action=action, event_date=event_date):
                summary[action] += 1
            else:
                summary["errors"].append({"id": record["id"], "error": f"{action}_failed"})
            return

        self.stock_pool_service.repository.write_audit(
            record["id"],
            "retain",
            record,
            record,
            actor,
            event_date=event_date,
        )
        summary["retain"] += 1
