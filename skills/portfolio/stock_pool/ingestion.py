"""Signal ingestion service for Portfolio stock pool entries."""

from __future__ import annotations

from typing import Any, Dict, List

from .models import PoolZone
from .service import StockPoolService


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
    "source_detail",
    "source_project",
    "source_signal_id",
    "entry_reason",
)


class StockPoolIngestionService:
    """Consume external research signals through the stock pool service boundary."""

    def __init__(self, stock_pool_service: StockPoolService) -> None:
        """Initialize ingestion with an existing StockPoolService."""
        self.stock_pool_service = stock_pool_service

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
                record = self._normalize_record(source, signal)
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

    def _normalize_record(self, source: str, signal: Dict[str, Any]) -> Dict[str, Any]:
        zone = signal.get("pool_zone") or (signal.get("metadata") or {}).get("pool_zone") or "SCAN"
        record = dict(signal)
        record["pool_zone"] = self.map_argus_zone(zone) if source == "argus" else PoolZone(zone).value
        record["source"] = source
        record.setdefault("source_project", source)
        record.setdefault("source_detail", signal.get("source_detail"))
        record.setdefault("source_signal_id", signal.get("source_signal_id") or signal.get("signal_id"))
        record["stock_code"] = record.get("stock_code") or str(record["wind_code"]).split(".")[0]
        record.setdefault("tags", [])
        record.setdefault("memo", "")
        if not record.get("entry_reason"):
            record["entry_reason"] = self._entry_reason_from_signal(signal)
        return record

    @staticmethod
    def _entry_reason_from_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
        """Build a rich entry_reason with all metrics from the signal."""
        return {
            "reason": signal.get("reason", ""),
            "bayesian_score": signal.get("bayesian_score") or signal.get("confidence") or 0,
            "consensus_confidence": signal.get("consensus_confidence") or 0,
            "contributing_products": signal.get("contributing_products") or [],
            "contributing_products_count": signal.get("contributing_products_count") or 0,
            "crowding_score": signal.get("crowding_score") or 0,
            "crowding_level": signal.get("crowding_level") or "LOW",
        }

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
                "source_detail": record.get("source_detail"),
                "source_project": record.get("source_project"),
                "source_signal_id": record.get("source_signal_id"),
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
                record = self._normalize_record("argus", signal)
                records[record["wind_code"]] = record
            except (KeyError, ValueError) as exc:
                summary["errors"].append({"dataset": label, "signal": signal.get("signal_id"), "error": str(exc)})
                summary["skipped"] += 1
        return records

    def _apply_entry(self, record: Dict[str, Any], actor: str, summary: Dict[str, Any], event_date: Optional[str] = None) -> None:
        existing = self._active_record(record["wind_code"])
        if existing:
            # Stock was in stock_pool before; compute correct zone action
            zone_action = self._zone_delta_action(
                existing.get("pool_zone"),
                record.get("pool_zone"),
            ) or "update"
            self._apply_record_update(existing["id"], record, zone_action, actor, summary, event_date=event_date)
            return
        record_id = self.stock_pool_service.create_entry(record, actor, event_date=event_date)
        summary["entry"] += 1
        summary["items"].append({"action": "entry", "id": record_id, "wind_code": record["wind_code"]})

    def _apply_exit(self, record: Dict[str, Any], actor: str, summary: Dict[str, Any], event_date: Optional[str] = None) -> None:
        existing = self._active_record(record["wind_code"])
        if not existing:
            summary["skipped"] += 1
            summary["items"].append({"action": "skip_exit_missing", "wind_code": record["wind_code"]})
            return
        reason = f"Argus signal pool exit: {record['wind_code']}"
        if self.stock_pool_service.deactivate_entry(existing["id"], reason, actor, audit_action="exit", event_date=event_date):
            summary["exit"] += 1
            summary["items"].append({"action": "exit", "id": existing["id"], "wind_code": record["wind_code"]})

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
            record_id = self.stock_pool_service.create_entry(current, actor, event_date=event_date)
            summary["entry"] += 1
            summary["items"].append({"action": "entry", "id": record_id, "wind_code": current["wind_code"]})
            return

        action = self._zone_delta_action(previous["pool_zone"], current["pool_zone"])
        if action is None:
            # previous_zone was None (holiday gap) — resolve against stock_pool zone.
            # Stock was already in stock_pool, so compare stock_pool zone with current zone.
            stock_pool_zone = existing.get("pool_zone")
            action = self._zone_delta_action(stock_pool_zone, current["pool_zone"]) or "update"
        patch = self._changed_field_patch(existing, current, include_zone=True)

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
        computed_patch = self._changed_field_patch(
            existing_record,
            record,
            include_zone=True,
        )
        patch = patch if patch is not None else computed_patch
        # Force-include pool_zone when zone actually changed in the record vs DB.
        # This handles: (a) promote/demote where zone changed, (b) update where zone changed
        # but computed_patch was empty because other fields were the same.
        rec_zone = record.get("pool_zone")
        db_zone = existing_record.get("pool_zone")
        if rec_zone and db_zone and rec_zone != db_zone and "pool_zone" not in patch:
            patch["pool_zone"] = rec_zone
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
        return {
            field_name: record.get(field_name)
            for field_name in field_names
            if existing.get(field_name) != record.get(field_name)
        }
