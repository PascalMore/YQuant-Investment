"""Unit tests for stock pool automatic zone transitions."""

import unittest
from datetime import datetime

from skills.portfolio.stock_pool.auto_promoter import StockPoolAutoPromoter
from skills.portfolio.stock_pool.repository import StockPoolRepository
from skills.portfolio.stock_pool.service import StockPoolService
from skills.portfolio.tests.test_stock_pool_repository import FakeClient


class StockPoolAutoPromoterTest(unittest.TestCase):
    """Validate automatic promotion and demotion decisions."""

    def setUp(self) -> None:
        """Create an in-memory stock pool service."""
        self.repository = StockPoolRepository(client=FakeClient())
        self.service = StockPoolService(self.repository)
        self.promoter = StockPoolAutoPromoter(self.service)

    def _create(self, zone: str, metrics: dict) -> str:
        record = {
            "stock_code": "600519",
            "wind_code": f"600519.{zone}",
            "stock_name": "贵州茅台",
            "pool_zone": zone,
            "source": "argus",
            "entry_reason": {
                "reason": f"New entry: 600519.{zone}",
                "trigger": "new_entry",
                "from_zone": None,
                "to_zone": zone,
            },
            "entry_date": datetime(2026, 5, 19),
            **metrics,
        }
        return self.service.create_entry(record, actor="tester")

    def test_promote_scan_to_watch_dry_run(self) -> None:
        """Dry-run promotion should return matches without mutating records."""
        record_id = self._create(
            "SCAN",
            {"bayesian_score": 0.35, "contributing_products_count": 2},
        )

        result = self.promoter.evaluate_and_promote("2026-05-19", dry_run=True)

        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["items"][0]["target_zone"], "WATCH")
        self.assertEqual(self.repository.get_by_id(record_id)["pool_zone"], "SCAN")

    def test_promote_changes_zone_and_audits(self) -> None:
        """Non-dry-run promotion should move the record and audit the transition."""
        record_id = self._create(
            "WATCH",
            {"bayesian_score": 0.55, "contributing_products_count": 2, "consensus_confidence": 0.44},
        )

        result = self.promoter.evaluate_and_promote("2026-05-19", dry_run=False)

        self.assertEqual(result["changed"], 1)
        self.assertEqual(self.repository.get_by_id(record_id)["pool_zone"], "CANDIDATE")
        audits = list(self.repository.audit_collection.docs.values())
        self.assertEqual(audits[-1]["action"], "auto_transition")

    def test_demote_when_current_zone_threshold_fails(self) -> None:
        """A record below its current-zone threshold should move down one zone."""
        record_id = self._create(
            "CONVICTION",
            {"bayesian_score": 0.62, "contributing_products_count": 3, "crowding_level": "LOW"},
        )

        result = self.promoter.evaluate_and_demote("2026-05-19", dry_run=False)

        self.assertEqual(result["changed"], 1)
        self.assertEqual(self.repository.get_by_id(record_id)["pool_zone"], "CANDIDATE")

    def test_candidate_to_conviction_requires_products(self) -> None:
        """Candidate promotion should require the configured product count."""
        self._create(
            "CANDIDATE",
            {"bayesian_score": 0.8, "contributing_products_count": 2, "crowding_level": "LOW"},
        )

        result = self.promoter.evaluate_and_promote("2026-05-19", dry_run=True)

        self.assertEqual(result["items"], [])
        self.assertEqual(result["skipped"], 1)

    def test_uses_yaml_thresholds_instead_of_legacy_thresholds(self) -> None:
        """SCAN promotion should follow YAML 0.35/1 thresholds, not legacy 0.30/2."""
        self._create(
            "SCAN",
            {"bayesian_score": 0.34, "contributing_products_count": 2, "consensus_confidence": 0.34},
        )
        self._create(
            "SCAN",
            {"bayesian_score": 0.35, "contributing_products_count": 1, "consensus_confidence": 0.20},
        )

        result = self.promoter.evaluate_and_promote("2026-05-19", dry_run=True)

        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["items"][0]["metrics"]["product_count"], 1)
        self.assertEqual(result["items"][0]["thresholds"]["bayesian_min"], 0.35)
        self.assertEqual(result["items"][0]["thresholds"]["product_count_min"], 1)
        self.assertIn("zone_rules_template.yaml", result["rule_source"]["path"])

    def test_missing_product_count_does_not_fallback_to_rule_minimum(self) -> None:
        """Missing product counts should be evaluated as missing data, not auto-filled thresholds."""
        self._create(
            "WATCH",
            {"bayesian_score": 0.60, "consensus_confidence": 0.45},
        )

        result = self.promoter.evaluate_and_promote("2026-05-19", dry_run=True)

        self.assertEqual(result["matched"], 0)
        self.assertEqual(result["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
