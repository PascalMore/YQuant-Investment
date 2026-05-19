"""Service layer for Portfolio stock pool workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import PoolZone, StockPoolStatus, validate_patch
from .repository import StockPoolRepository


class StockPoolService:
    """Business service for stock pool queries, mutations, and transition requests."""

    def __init__(self, repository: StockPoolRepository) -> None:
        """Initialize service with a stock pool repository dependency."""
        self.repository = repository

    def get_pool(
        self,
        pool_zone: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        wind_code: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a filtered page of stock pool records."""
        return self.repository.list(
            pool_zone=pool_zone,
            source=source,
            status=status,
            wind_code=wind_code,
            limit=limit,
            cursor=cursor,
        )

    def create_entry(self, record: Dict[str, Any], actor: str) -> str:
        """Create a stock pool entry and write a matching audit event."""
        pool_id = self.repository.create(record, actor)
        after = self.repository.get_by_id(pool_id)
        self.repository.write_audit(pool_id, "create", None, after, actor)
        return pool_id

    def update_entry(self, record_id: str, patch: Dict[str, Any], actor: str) -> bool:
        """Update a stock pool entry and audit the before/after state."""
        before = self.repository.get_by_id(record_id)
        if before is None:
            return False
        changed = self.repository.update_fields(record_id, validate_patch(patch), actor)
        if changed:
            after = self.repository.get_by_id(record_id)
            self.repository.write_audit(record_id, "update", before, after, actor)
        return changed

    def move_entry(self, record_id: str, target_zone: str, reason: str, actor: str) -> bool:
        """Move an entry to another zone immediately and write an audit event."""
        before = self.repository.get_by_id(record_id)
        if before is None:
            return False
        changed = self.repository.transition_zone(record_id, PoolZone(target_zone).value, reason, actor)
        if changed:
            after = self.repository.get_by_id(record_id)
            self.repository.write_audit(record_id, "auto_transition", before, after, actor)
        return changed

    def get_audit_history(self, record_id: str, limit: int = 100) -> Dict[str, Any]:
        """Return audit history for a stock pool record."""
        return self.repository.list_audit(record_id, limit=limit)

    def get_capacity(self) -> Dict[str, Any]:
        """Return active stock pool capacity by zone."""
        return self.repository.capacity_by_zone()

    def request_zone_transition(self, record_id: str, target_zone: str, reason: str, actor: str) -> str:
        """Create a pending zone transition request without approving the change."""
        before = self.repository.get_by_id(record_id)
        if before is None:
            raise ValueError(f"Stock pool record not found: {record_id}")
        if before.get("status") != StockPoolStatus.ACTIVE.value:
            raise ValueError("Only active stock pool entries can request zone transitions")

        request_id = str(uuid4())
        transition = {
            "request_id": request_id,
            "from_zone": before.get("pool_zone"),
            "target_zone": PoolZone(target_zone).value,
            "reason": reason,
            "requested_by": actor,
            "requested_at": datetime.utcnow(),
            "approval_status": "pending",
        }
        changed = self.repository.update_fields(record_id, {"pending_transition": transition}, actor)
        if not changed:
            raise ValueError(f"Failed to create transition request for record: {record_id}")
        after = self.repository.get_by_id(record_id)
        self.repository.write_audit(record_id, "request_transition", before, after, actor)
        return request_id

    def ingest_signals(
        self,
        source: str,
        signals: List[Dict[str, Any]],
        mode: str = "upsert_scan_only",
        actor: str = "system:argus",
    ) -> Dict[str, Any]:
        """Ingest external research signals through the stock pool ingestion service."""
        from .ingestion import StockPoolIngestionService

        return StockPoolIngestionService(self).ingest_signals(source, signals, mode, actor)
