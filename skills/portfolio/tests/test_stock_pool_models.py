"""Unit tests for stock pool data models."""

import unittest
from datetime import datetime

from skills.portfolio.stock_pool.models import PoolZone, StockPoolEntry, StockPoolSource, validate_patch


class StockPoolModelTest(unittest.TestCase):
    """Validate model normalization and field checks."""

    def test_entry_to_dict_normalizes_enums(self) -> None:
        """StockPoolEntry should serialize enum values and audit metadata."""
        entry = StockPoolEntry(
            stock_code="600519",
            wind_code="600519.SH",
            stock_name="贵州茅台",
            pool_zone="SCAN",
            source="argus",
            entry_reason={"signal_type": "flow", "score": 0.81, "confidence": 0.7, "evidence": ["x"]},
            entry_date=datetime(2026, 5, 19),
            tags=["消费"],
        )

        data = entry.to_dict(actor="tester")

        self.assertEqual(data["pool_zone"], PoolZone.SCAN.value)
        self.assertEqual(data["source"], StockPoolSource.ARGUS.value)
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["audit"]["created_by"], "tester")

    def test_entry_requires_non_empty_reason(self) -> None:
        """Empty entry_reason should be rejected."""
        with self.assertRaises(ValueError):
            StockPoolEntry(
                stock_code="600519",
                wind_code="600519.SH",
                stock_name="贵州茅台",
                pool_zone="SCAN",
                source="argus",
                entry_reason={},
            )

    def test_validate_patch_rejects_invalid_zone(self) -> None:
        """Patch validation should reject unsupported pool zones."""
        with self.assertRaises(ValueError):
            validate_patch({"pool_zone": "FOCUS"})


if __name__ == "__main__":
    unittest.main()
