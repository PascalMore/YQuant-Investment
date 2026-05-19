"""MongoDB repository for Portfolio stock pool records."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from pymongo import MongoClient

from .models import PoolZone, StockPoolEntry, validate_patch


DEFAULT_MONGO_URI = "mongodb://myq:6812345@172.25.240.1:27017/"
DEFAULT_DATABASE = "tradingagents"
STOCK_POOL_COLLECTION = "portfolio_stock_pool"
AUDIT_COLLECTION = "portfolio_stock_pool_audit"


class StockPoolRepository:
    """Repository encapsulating MongoDB persistence for stock pool data."""

    def __init__(
        self,
        client: Optional[MongoClient] = None,
        mongo_uri: str = DEFAULT_MONGO_URI,
        database: str = DEFAULT_DATABASE,
    ) -> None:
        """Initialize repository with an existing client or default MongoDB URI."""
        self.client = client or MongoClient(mongo_uri)
        self.db = self.client[database]
        self.collection = self.db[STOCK_POOL_COLLECTION]
        self.audit_collection = self.db[AUDIT_COLLECTION]
        self.ensure_indexes()

    def ensure_indexes(self) -> None:
        """Create idempotent MongoDB indexes required by the stock pool."""
        self.collection.create_index([("pool_zone", 1), ("status", 1)], name="idx_stock_pool_zone_status")
        self.collection.create_index([("wind_code", 1)], name="idx_stock_pool_wind_code")
        self.collection.create_index([("source", 1), ("entry_date", -1)], name="idx_stock_pool_source_entry_date")
        self.collection.create_index([("status", 1), ("entry_date", -1)], name="idx_stock_pool_status_entry_date")
        self.audit_collection.create_index(
            [("pool_id", 1), ("created_at", -1)],
            name="idx_stock_pool_audit_pool_created",
        )

    def list(
        self,
        pool_zone: Optional[str] = None,
        source: Optional[str] = None,
        status: Optional[str] = None,
        wind_code: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List stock pool entries using filters and ObjectId cursor pagination."""
        query: Dict[str, Any] = {}
        if pool_zone:
            query["pool_zone"] = pool_zone
        if source:
            query["source"] = source
        if status:
            query["status"] = status
        if wind_code:
            query["wind_code"] = wind_code
        if cursor:
            query["_id"] = {"$lt": ObjectId(cursor)}

        page_size = max(1, min(limit, 200))
        docs = list(self.collection.find(query).sort("_id", -1).limit(page_size + 1))
        items = [self._serialize(doc) for doc in docs[:page_size]]
        next_cursor = str(docs[page_size]["_id"]) if len(docs) > page_size else None
        return {"items": items, "next_cursor": next_cursor, "limit": page_size}

    def create(self, record: Dict[str, Any], actor: str) -> str:
        """Create a stock pool record and return its inserted ID."""
        entry = record if isinstance(record, StockPoolEntry) else StockPoolEntry.from_dict(record)
        document = entry.to_dict(actor=actor)
        now = datetime.utcnow()
        document.setdefault("audit", {})
        document["audit"].update({"created_at": now, "updated_at": now, "created_by": actor, "updated_by": actor})
        result = self.collection.insert_one(document)
        return str(result.inserted_id)

    def get_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one stock pool record by ID."""
        doc = self.collection.find_one({"_id": ObjectId(record_id)})
        return self._serialize(doc) if doc else None

    def update_fields(self, record_id: str, patch: Dict[str, Any], actor: str) -> bool:
        """Apply a partial update to a stock pool record."""
        update = validate_patch(patch)
        update["audit.updated_at"] = datetime.utcnow()
        update["audit.updated_by"] = actor
        result = self.collection.update_one({"_id": ObjectId(record_id)}, {"$set": update})
        return result.modified_count > 0

    def transition_zone(self, record_id: str, target_zone: str, reason: str, actor: str) -> bool:
        """Move an active stock pool record to another lifecycle zone."""
        patch = validate_patch(
            {
                "pool_zone": target_zone,
                "pending_transition": None,
                "last_transition_reason": reason,
                "last_transition_at": datetime.utcnow(),
            }
        )
        patch["audit.updated_at"] = datetime.utcnow()
        patch["audit.updated_by"] = actor
        result = self.collection.update_one({"_id": ObjectId(record_id)}, {"$set": patch})
        return result.modified_count > 0

    def deactivate(self, record_id: str, exit_date: datetime, reason: str, actor: str) -> bool:
        """Mark a stock pool record inactive and store an exit reason."""
        patch = {
            "status": "inactive",
            "exit_date": exit_date,
            "exit_reason": reason,
            "audit.updated_at": datetime.utcnow(),
            "audit.updated_by": actor,
        }
        result = self.collection.update_one({"_id": ObjectId(record_id)}, {"$set": patch})
        return result.modified_count > 0

    def write_audit(
        self,
        pool_id: str,
        action: str,
        before: Optional[Dict[str, Any]],
        after: Optional[Dict[str, Any]],
        actor: str,
    ) -> str:
        """Write one stock pool audit event and return its ID."""
        result = self.audit_collection.insert_one(
            {
                "pool_id": pool_id,
                "action": action,
                "before": before,
                "after": after,
                "actor": actor,
                "created_at": datetime.utcnow(),
            }
        )
        return str(result.inserted_id)

    def list_audit(self, pool_id: str, limit: int = 100) -> Dict[str, Any]:
        """Return recent audit events for one stock pool record."""
        page_size = max(1, min(limit, 200))
        docs = list(
            self.audit_collection.find({"pool_id": pool_id})
            .sort("created_at", -1)
            .limit(page_size)
        )
        return {"items": [self._serialize(doc) for doc in docs], "limit": page_size}

    def capacity_by_zone(self) -> Dict[str, Any]:
        """Return active record counts by stock pool zone."""
        counts = {zone.value: 0 for zone in PoolZone}
        for doc in self.collection.find({"status": "active"}):
            zone = doc.get("pool_zone")
            if zone in counts:
                counts[zone] += 1
        return {"zones": counts, "total": sum(counts.values())}

    @staticmethod
    def _serialize(document: Dict[str, Any]) -> Dict[str, Any]:
        """Convert MongoDB ObjectId fields to strings for API/service callers."""
        serialized = dict(document)
        serialized["id"] = str(serialized.pop("_id"))
        return serialized
