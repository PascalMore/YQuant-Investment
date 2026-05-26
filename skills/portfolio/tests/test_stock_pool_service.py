"""Unit tests for stock pool service workflows."""

import unittest
from datetime import datetime

from skills.portfolio.stock_pool.repository import StockPoolRepository
from skills.portfolio.stock_pool.service import StockPoolService
from skills.portfolio.tests.test_stock_pool_repository import FakeClient


class StockPoolServiceTest(unittest.TestCase):
    """Validate service logic and audit side effects."""

    def setUp(self) -> None:
        """Create a service backed by an in-memory repository."""
        self.repository = StockPoolRepository(client=FakeClient())
        self.service = StockPoolService(self.repository)
        self.record = {
            "stock_code": "600519",
            "wind_code": "600519.SH",
            "stock_name": "贵州茅台",
            "pool_zone": "SCAN",
            "source": "argus",
            "entry_reason": {"signal_type": "flow", "score": 0.8, "confidence": 0.7, "evidence": []},
            "entry_date": datetime(2026, 5, 19),
        }

    def test_create_entry_writes_audit(self) -> None:
        """Creating an entry should also write an audit event."""
        record_id = self.service.create_entry(self.record, actor="tester")
        audits = list(self.repository.audit_collection.docs.values())

        self.assertTrue(record_id)
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["action"], "entry")

    def test_update_entry_writes_audit(self) -> None:
        """Updating an entry should persist changes and audit the before/after state."""
        record_id = self.service.create_entry(self.record, actor="tester")
        changed = self.service.update_entry(record_id, {"memo": "research note"}, actor="tester")
        audits = list(self.repository.audit_collection.docs.values())

        self.assertTrue(changed)
        self.assertEqual(self.repository.get_by_id(record_id)["memo"], "research note")
        self.assertEqual(audits[-1]["action"], "update")

    def test_request_zone_transition_creates_pending_request(self) -> None:
        """Zone transition should create a pending request without changing pool_zone."""
        record_id = self.service.create_entry(self.record, actor="tester")
        request_id = self.service.request_zone_transition(record_id, "WATCH", "more evidence", "tester")
        doc = self.repository.get_by_id(record_id)

        self.assertTrue(request_id)
        self.assertEqual(doc["pool_zone"], "SCAN")
        self.assertEqual(doc["pending_transition"]["target_zone"], "WATCH")
        self.assertEqual(doc["pending_transition"]["approval_status"], "pending")


if __name__ == "__main__":
    unittest.main()
