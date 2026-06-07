"""Unit tests for stock pool signal ingestion."""

import unittest
from datetime import datetime

from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService, StockPoolTransitionPipeline
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
            "consensus_confidence": 0.74,
            "contributing_products": ["SM001", "SM002"],
            "contributing_products_count": 2,
            "crowding_level": "MEDIUM",
            "crowding_score": 0.42,
            "darwin_moment": True,
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
        self.assertEqual(page["items"][0]["bayesian_score"], 0.82)
        self.assertEqual(page["items"][0]["crowding_level"], "MEDIUM")
        self.assertEqual(page["items"][0]["crowding_score"], 0.42)
        self.assertEqual(page["items"][0]["consensus_confidence"], 0.74)
        self.assertEqual(page["items"][0]["contributing_products"], ["SM001", "SM002"])
        self.assertEqual(page["items"][0]["contributing_products_count"], 2)
        self.assertNotIn("weight_change_30d", page["items"][0])
        self.assertTrue(page["items"][0]["darwin_moment"])
        entry_reason = page["items"][0]["entry_reason"]
        self.assertEqual(entry_reason["trigger"], "new_entry")
        self.assertIsNone(entry_reason["from_zone"])
        self.assertEqual(entry_reason["to_zone"], "SCAN")
        self.assertIn("New entry", entry_reason["reason"])
        self.assertNotIn("metrics", entry_reason)

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
            "bayesian_score": 0.9,
            "contributing_products": ["SM001", "SM002", "SM003"],
            "contributing_products_count": 3,
            "memo": "stronger evidence",
        }

        summary = self.ingestion.ingest_signals("argus", [updated_signal], mode="upsert_all", actor="tester")
        page = self.stock_pool_service.get_pool(wind_code="600519.SH", source="argus", status="active")

        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(page["items"][0]["pool_zone"], "WATCH")
        self.assertEqual(page["items"][0]["memo"], "stronger evidence")
        self.assertEqual(page["items"][0]["entry_reason"]["trigger"], "new_entry")
        self.assertEqual(page["items"][0]["bayesian_score"], 0.9)
        self.assertEqual(page["items"][0]["contributing_products"], ["SM001", "SM002", "SM003"])
        self.assertEqual(page["items"][0]["contributing_products_count"], 3)

    def test_map_focus_zone_to_conviction(self) -> None:
        """Legacy Argus FOCUS zone should map to Portfolio CONVICTION."""
        self.assertEqual(self.ingestion.map_argus_zone("focus"), "CONVICTION")

    def test_stock_pool_service_exposes_ingest_signals(self) -> None:
        """StockPoolService should expose the requested ingestion boundary."""
        summary = self.stock_pool_service.ingest_signals("argus", [self.scan_signal], actor="tester")

        self.assertEqual(summary["created"], 1)

    def test_ingest_signals_incremental_preserves_existing_zone(self) -> None:
        """Incremental sync refreshes metrics but keeps stock_pool zone authoritative."""
        previous = [
            {**self.scan_signal, "wind_code": "600001.SH", "stock_code": "600001", "pool_zone": "SCAN"},
            {**self.scan_signal, "wind_code": "600002.SH", "stock_code": "600002", "pool_zone": "CANDIDATE"},
            {**self.scan_signal, "wind_code": "600003.SH", "stock_code": "600003", "pool_zone": "WATCH"},
            {**self.scan_signal, "wind_code": "600004.SH", "stock_code": "600004", "pool_zone": "WATCH"},
        ]
        current = [
            {**previous[0], "pool_zone": "WATCH", "bayesian_score": 0.9},
            {**previous[1], "pool_zone": "WATCH", "bayesian_score": 0.1},
            {**previous[2], "memo": "same zone refreshed"},
            {
                **self.scan_signal,
                "wind_code": "600005.SH",
                "stock_code": "600005",
                "pool_zone": "SCAN",
                "bayesian_score": 0.6,
                "consensus_confidence": 0.45,
                "darwin_moment": False,
            },
        ]
        for signal in previous:
            self.ingestion.ingest_signals("argus", [signal], mode="upsert_all", actor="seed")

        summary = self.ingestion.ingest_signals_incremental(current, previous, actor="system:argus")
        actions = [audit["action"] for audit in self.repository.audit_collection.docs.values()]

        self.assertEqual(summary["entry"], 1)
        self.assertEqual(summary["promote"], 0)
        self.assertEqual(summary["demote"], 0)
        self.assertEqual(summary["exit"], 1)
        self.assertEqual(summary["update"], 3)
        self.assertIn("entry", actions)
        self.assertIn("update", actions)
        updated = self.stock_pool_service.get_pool(wind_code="600001.SH", source="argus", status="active")["items"][0]
        self.assertEqual(updated["pool_zone"], "SCAN")
        self.assertEqual(updated["bayesian_score"], 0.9)
        missing = self.stock_pool_service.get_pool(wind_code="600004.SH", source="argus", status="active")["items"][0]
        self.assertTrue(missing["missing_from_signal_pool"])
        entry = self.stock_pool_service.get_pool(wind_code="600005.SH", source="argus", status="active")["items"][0]
        self.assertEqual(entry["pool_zone"], "CANDIDATE")

    def test_transition_pipeline_dry_run_classifies_from_stock_pool_zone(self) -> None:
        """Dry-run should report one-step transitions without mutating records."""
        seeded = [
            {**self.scan_signal, "wind_code": "600011.SH", "stock_code": "600011", "pool_zone": "SCAN"},
            {**self.scan_signal, "wind_code": "600012.SH", "stock_code": "600012", "pool_zone": "WATCH"},
            {**self.scan_signal, "wind_code": "600013.SH", "stock_code": "600013", "pool_zone": "WATCH"},
            {**self.scan_signal, "wind_code": "600014.SH", "stock_code": "600014", "pool_zone": "WATCH"},
        ]
        for signal in seeded:
            self.ingestion.ingest_signals("argus", [signal], mode="upsert_all", actor="seed")

        current = [
            {**seeded[0], "pool_zone": "SCAN", "bayesian_score": 0.4, "consensus_confidence": 0.25},
            {**seeded[1], "pool_zone": "WATCH", "bayesian_score": 0.2, "consensus_confidence": 0.05},
            {**seeded[2], "pool_zone": "CONVICTION", "bayesian_score": 0.3, "consensus_confidence": 0.2},
        ]
        pipeline = StockPoolTransitionPipeline(self.ingestion)

        summary = pipeline.run_incremental_transition(current, seeded, actor="system:argus", dry_run=True)
        by_code = {item["wind_code"]: item for item in summary["items"]}

        self.assertEqual(summary["promote"], 1)
        self.assertEqual(summary["demote"], 1)
        self.assertEqual(summary["retain"], 1)
        self.assertEqual(summary["exit"], 1)
        self.assertEqual(by_code["600011.SH"]["target_zone"], "WATCH")
        self.assertEqual(by_code["600012.SH"]["target_zone"], "SCAN")
        self.assertIsNone(by_code["600014.SH"]["target_zone"])
        unchanged = self.stock_pool_service.get_pool(wind_code="600011.SH", source="argus", status="active")["items"][0]
        self.assertEqual(unchanged["pool_zone"], "SCAN")


if __name__ == "__main__":
    unittest.main()
