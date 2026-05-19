"""Unit tests for Argus to Portfolio subscriber conversion."""

import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, "/home/pascal/.openclaw/workspace-yquant")

from skills.portfolio.tests.test_stock_pool_repository import FakeClient
from skills.research.argus.argus_portfolio_subscriber import ArgusPortfolioSubscriber


class ArgusPortfolioSubscriberTest(unittest.TestCase):
    """Validate MongoDB signal reads and Portfolio payload conversion."""

    def setUp(self) -> None:
        """Create a subscriber backed by an in-memory MongoDB substitute."""
        self.client = FakeClient()
        self.subscriber = ArgusPortfolioSubscriber(client=self.client)
        self.collection = self.subscriber.collection
        self.signal = {
            "signal_id": "sig-001",
            "source": "argus",
            "version": "1.0.0",
            "product_code": "SM001",
            "product_name": "JS-001",
            "signal_type": "BUY",
            "confidence": 0.82,
            "direction": "LONG",
            "target_stocks": [
                {
                    "wind_code": "600519.SH",
                    "stock_name": "贵州茅台",
                    "action": "BUY",
                    "holding_ratio_change": 0.023,
                    "market_value_change": 520000,
                }
            ],
            "reason": "institutional flow increased",
            "generated_at": "2026-05-19T08:00:00",
            "valid_until": "2026-05-19",
            "metadata": {"pool_zone": "SCAN", "credibility_score": 0.82},
        }
        self.collection.insert_one(self.signal)

    def test_get_latest_signals_filters_by_date_confidence_and_zone(self) -> None:
        """Latest signal query should apply date, confidence, and zone filters."""
        self.collection.insert_one({**self.signal, "signal_id": "sig-002", "confidence": 0.5})

        signals = self.subscriber.get_latest_signals("2026-05-19", min_confidence=0.7, pool_zone="SCAN")

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["signal_id"], "sig-001")

    def test_to_portfolio_ingest_payload_skips_non_scan_in_scan_only_mode(self) -> None:
        """upsert_scan_only should only emit SCAN payloads."""
        watch_signal = {**self.signal, "signal_id": "sig-003", "metadata": {"pool_zone": "WATCH"}}

        payload = self.subscriber.to_portfolio_ingest_payload([self.signal, watch_signal])

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["wind_code"], "600519.SH")
        self.assertEqual(payload[0]["pool_zone"], "SCAN")
        self.assertEqual(payload[0]["entry_reason"]["signal_id"], "sig-001")

    def test_get_stock_signals_filters_recent_mentions(self) -> None:
        """Stock lookup should return recent signals mentioning the requested Wind code."""
        old_signal = {
            **self.signal,
            "signal_id": "sig-old",
            "generated_at": (datetime.utcnow() - timedelta(days=20)).isoformat(),
        }
        self.collection.insert_one(old_signal)

        signals = self.subscriber.get_stock_signals("600519.SH", days=7, min_confidence=0.7)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["signal_id"], "sig-001")


if __name__ == "__main__":
    unittest.main()
