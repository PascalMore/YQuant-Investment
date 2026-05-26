"""Unit tests for stock pool signal ingestion."""

import unittest
from datetime import datetime

from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService
from skills.portfolio.stock_pool.repository import StockPoolRepository
from skills.portfolio.stock_pool.service import StockPoolService
from skills.portfolio.tests.test_stock_pool_repository import FakeClient


class StockPoolIngestionServiceTest(unittest.TestCase):
    """Validate Argus signal ingestion into the Portfolio stock pool."""

    def setUp(self) -> None:
        """Create ingestion service with an in-memory repository."""
        self.repository = StockPoolRepository(client=FakeClient())
        self.stock_pool_service = StockPoolService(self.repository)
        self.ingestion = StockPoolIngestionService(self.stock_pool_service)
        self.scan_signal = {
            "signal_id": "sig-001",
            "stock_code": "600519",
            "wind_code": "600519.SH",
            "stock_name": "贵州茅台",
            "pool_zone": "SCAN",
            "entry_date": datetime(2026, 5, 19),
            "entry_reason": {"signal_id": "sig-001", "confidence": 0.82},
            "tags": ["argus", "buy"],
            "memo": "institutional flow increased",
        }

    def test_ingest_scan_signal_creates_entry(self) -> None:
        """SCAN Argus signal should create an active stock pool entry."""
        summary = self.ingestion.ingest_signals("argus", [self.scan_signal], actor="tester")
        page = self.stock_pool_service.get_pool(wind_code="600519.SH", source="argus", status="active")

        self.assertEqual(summary["created"], 1)
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(page["items"][0]["pool_zone"], "SCAN")

    def test_upsert_scan_only_skips_non_scan_zones(self) -> None:
        """Default mode should not write WATCH/CANDIDATE/CONVICTION signals."""
        watch_signal = {**self.scan_signal, "signal_id": "sig-002", "wind_code": "000858.SZ", "pool_zone": "WATCH"}

        summary = self.ingestion.ingest_signals("argus", [watch_signal], actor="tester")

        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(self.stock_pool_service.get_pool(source="argus")["items"], [])

    def test_upsert_all_updates_existing_entry(self) -> None:
        """upsert_all should update an existing active source/wind_code record."""
        self.ingestion.ingest_signals("argus", [self.scan_signal], actor="tester")
        updated_signal = {
            **self.scan_signal,
            "pool_zone": "WATCH",
            "entry_reason": {"signal_id": "sig-002", "confidence": 0.9},
            "memo": "stronger evidence",
        }

        summary = self.ingestion.ingest_signals("argus", [updated_signal], mode="upsert_all", actor="tester")
        page = self.stock_pool_service.get_pool(wind_code="600519.SH", source="argus", status="active")

        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(page["items"][0]["pool_zone"], "WATCH")
        self.assertEqual(page["items"][0]["memo"], "stronger evidence")

    def test_map_focus_zone_to_conviction(self) -> None:
        """Legacy Argus FOCUS zone should map to Portfolio CONVICTION."""
        self.assertEqual(self.ingestion.map_argus_zone("focus"), "CONVICTION")

    def test_stock_pool_service_exposes_ingest_signals(self) -> None:
        """StockPoolService should expose the requested ingestion boundary."""
        summary = self.stock_pool_service.ingest_signals("argus", [self.scan_signal], actor="tester")

        self.assertEqual(summary["created"], 1)

    def test_ingest_signals_incremental_writes_fine_grained_audit(self) -> None:
        """Incremental sync should emit entry/promote/demote/exit/update audit actions."""
        previous = [
            {**self.scan_signal, "wind_code": "600001.SH", "stock_code": "600001", "pool_zone": "SCAN"},
            {**self.scan_signal, "wind_code": "600002.SH", "stock_code": "600002", "pool_zone": "CANDIDATE"},
            {**self.scan_signal, "wind_code": "600003.SH", "stock_code": "600003", "pool_zone": "WATCH"},
            {**self.scan_signal, "wind_code": "600004.SH", "stock_code": "600004", "pool_zone": "WATCH"},
        ]
        current = [
            {**previous[0], "pool_zone": "WATCH"},
            {**previous[1], "pool_zone": "WATCH"},
            {**previous[2], "memo": "same zone refreshed"},
            {**self.scan_signal, "wind_code": "600005.SH", "stock_code": "600005", "pool_zone": "SCAN"},
        ]
        for signal in previous:
            self.ingestion.ingest_signals("argus", [signal], mode="upsert_all", actor="seed")

        summary = self.ingestion.ingest_signals_incremental(current, previous, actor="system:argus")
        actions = [audit["action"] for audit in self.repository.audit_collection.docs.values()]

        self.assertEqual(summary["entry"], 1)
        self.assertEqual(summary["promote"], 1)
        self.assertEqual(summary["demote"], 1)
        self.assertEqual(summary["exit"], 1)
        self.assertEqual(summary["update"], 1)
        self.assertIn("entry", actions)
        self.assertIn("promote", actions)
        self.assertIn("demote", actions)
        self.assertIn("exit", actions)
        self.assertIn("update", actions)
        exited = self.stock_pool_service.get_pool(wind_code="600004.SH", source="argus", status="inactive")["items"]
        self.assertEqual(exited[0]["status"], "inactive")


if __name__ == "__main__":
    unittest.main()
