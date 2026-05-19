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
        return {
            "signal_id": signal.get("signal_id"),
            "signal_type": signal.get("signal_type"),
            "confidence": signal.get("confidence"),
            "reason": signal.get("reason", ""),
            "metadata": signal.get("metadata", {}),
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
