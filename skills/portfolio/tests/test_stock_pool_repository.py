"""Unit tests for stock pool repository CRUD behavior."""

import unittest
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from bson import ObjectId

from skills.portfolio.stock_pool.repository import StockPoolRepository


class InsertOneResult:
    """Small stand-in for pymongo InsertOneResult."""

    def __init__(self, inserted_id: ObjectId) -> None:
        """Store inserted ID."""
        self.inserted_id = inserted_id


class UpdateResult:
    """Small stand-in for pymongo UpdateResult."""

    def __init__(self, modified_count: int) -> None:
        """Store modified count."""
        self.modified_count = modified_count


class FakeCursor:
    """Minimal pymongo cursor compatible with repository list calls."""

    def __init__(self, docs: List[Dict[str, Any]]) -> None:
        """Initialize cursor with in-memory documents."""
        self.docs = docs

    def sort(self, field: str, direction: int) -> "FakeCursor":
        """Sort documents by one field."""
        self.docs = sorted(self.docs, key=lambda doc: doc[field], reverse=direction < 0)
        return self

    def limit(self, limit: int) -> "FakeCursor":
        """Limit returned documents."""
        self.docs = self.docs[:limit]
        return self

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        """Iterate over cursor documents."""
        return iter(self.docs)


class FakeCollection:
    """In-memory MongoDB collection substitute for repository tests."""

    def __init__(self) -> None:
        """Initialize empty collection."""
        self.docs: Dict[ObjectId, Dict[str, Any]] = {}
        self.indexes: List[Any] = []

    def create_index(self, keys: Any, name: str) -> None:
        """Record requested index creation."""
        self.indexes.append((keys, name))

    def insert_one(self, document: Dict[str, Any]) -> InsertOneResult:
        """Insert one document into memory."""
        inserted_id = ObjectId()
        stored = dict(document)
        stored["_id"] = inserted_id
        self.docs[inserted_id] = stored
        return InsertOneResult(inserted_id)

    def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find one document by ObjectId."""
        doc = self.docs.get(query["_id"])
        return dict(doc) if doc else None

    def find(self, query: Dict[str, Any]) -> FakeCursor:
        """Find documents by exact-match filters and optional _id cursor."""
        def matches(doc: Dict[str, Any]) -> bool:
            for key, value in query.items():
                if key == "_id" and "$lt" in value:
                    if not doc["_id"] < value["$lt"]:
                        return False
                elif doc.get(key) != value:
                    return False
            return True

        return FakeCursor([dict(doc) for doc in self.docs.values() if matches(doc)])

    def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> UpdateResult:
        """Apply a $set update to one document."""
        doc = self.docs.get(query["_id"])
        if not doc:
            return UpdateResult(0)
        for key, value in update["$set"].items():
            target = doc
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        return UpdateResult(1)


class FakeDatabase:
    """In-memory MongoDB database substitute."""

    def __init__(self) -> None:
        """Initialize fake collections."""
        self.collections: Dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        """Return a named collection."""
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]


class FakeClient:
    """In-memory MongoDB client substitute."""

    def __init__(self) -> None:
        """Initialize fake databases."""
        self.databases: Dict[str, FakeDatabase] = {}

    def __getitem__(self, name: str) -> FakeDatabase:
        """Return a named database."""
        self.databases.setdefault(name, FakeDatabase())
        return self.databases[name]


class StockPoolRepositoryTest(unittest.TestCase):
    """Validate repository CRUD behavior with an in-memory client."""

    def setUp(self) -> None:
        """Create a fresh repository for each test."""
        self.repository = StockPoolRepository(client=FakeClient())
        self.record = {
            "stock_code": "600519",
            "wind_code": "600519.SH",
            "stock_name": "贵州茅台",
            "pool_zone": "SCAN",
            "source": "argus",
            "entry_reason": {"signal_type": "flow", "score": 0.8, "confidence": 0.7, "evidence": []},
            "entry_date": datetime(2026, 5, 19),
        }

    def test_create_and_list(self) -> None:
        """Repository should create and list records."""
        record_id = self.repository.create(self.record, actor="tester")
        page = self.repository.list(pool_zone="SCAN", status="active")

        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["id"], record_id)
        self.assertIsNone(page["next_cursor"])

    def test_update_fields(self) -> None:
        """Repository should apply partial updates."""
        record_id = self.repository.create(self.record, actor="tester")
        changed = self.repository.update_fields(record_id, {"memo": "updated", "pool_zone": "WATCH"}, "tester")
        doc = self.repository.get_by_id(record_id)

        self.assertTrue(changed)
        self.assertEqual(doc["memo"], "updated")
        self.assertEqual(doc["pool_zone"], "WATCH")

    def test_deactivate_and_audit(self) -> None:
        """Repository should deactivate records and write audit entries."""
        record_id = self.repository.create(self.record, actor="tester")
        changed = self.repository.deactivate(record_id, datetime(2026, 5, 20), "weak signal", "tester")
        audit_id = self.repository.write_audit(record_id, "deactivate", None, None, "tester")
        doc = self.repository.get_by_id(record_id)

        self.assertTrue(changed)
        self.assertEqual(doc["status"], "inactive")
        self.assertTrue(audit_id)


if __name__ == "__main__":
    unittest.main()
