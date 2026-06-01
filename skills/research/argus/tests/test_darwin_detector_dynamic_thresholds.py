"""Unit tests for Darwin detector dynamic credibility thresholds."""

import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, '/home/pascal/.openclaw/workspace-yquant')

from skills.research.argus.core.darwin_detector import CSI300_CODE, DarwinDetector


TARGET_DATE = '2026-05-29'
SECTOR_CODE = '801010.SI'


def _quotes(code: str, start_price: float, end_price: float) -> list:
    start = date(2026, 5, 1)
    records = []
    for offset in range(21):
        trade_date = (start + timedelta(days=offset)).isoformat()
        close = start_price if offset == 0 else end_price
        if trade_date == TARGET_DATE:
            close = end_price
        records.append({'full_symbol': code, 'trade_date': trade_date, 'close': close})
    records[-1]['trade_date'] = TARGET_DATE
    return records


class TestDarwinDetectorDynamicThresholds(unittest.TestCase):
    def test_returns_empty_when_fewer_than_three_valid_products(self):
        detector = DarwinDetector()

        events = detector.detect_for_date(
            TARGET_DATE,
            index_quotes=_quotes(SECTOR_CODE, 100.0, 85.0),
            credential_scores=[
                {'product_code': 'P1', 'credibility_score': 0.2},
                {'product_code': 'P2', 'credibility_score': 0.8},
            ],
            industry_weights=[],
        )

        self.assertEqual(events, [])

    def test_uses_daily_20th_and_80th_percentiles_for_weak_and_strong_groups(self):
        detector = DarwinDetector()
        credentials = [
            {'product_code': 'P1', 'credibility_score': 0.10},
            {'product_code': 'P2', 'credibility_score': 0.20},
            {'product_code': 'P3', 'credibility_score': 0.30},
            {'product_code': 'P4', 'credibility_score': 0.40},
            {'product_code': 'P5', 'credibility_score': 0.50},
            {'product_code': 'P6', 'credibility_score': 0.60},
            {'product_code': 'P7', 'credibility_score': 0.70},
            {'product_code': 'P8', 'credibility_score': 0.80},
            {'product_code': 'P9', 'credibility_score': 0.90},
            {'product_code': 'P10', 'credibility_score': 1.00},
        ]
        industry_weights = [
            {'date': TARGET_DATE, 'product_code': 'P1', 'sw1_code': SECTOR_CODE, 'weight_change_30d': -1.0},
            {'date': TARGET_DATE, 'product_code': 'P2', 'sw1_code': SECTOR_CODE, 'weight_change_30d': -2.0},
            {'date': TARGET_DATE, 'product_code': 'P9', 'sw1_code': SECTOR_CODE, 'weight_change_30d': 1.0},
            {'date': TARGET_DATE, 'product_code': 'P10', 'sw1_code': SECTOR_CODE, 'weight_change_30d': 1.5},
        ]

        events = detector.detect_for_date(
            TARGET_DATE,
            index_quotes=_quotes(SECTOR_CODE, 100.0, 85.0) + _quotes(CSI300_CODE, 100.0, 96.0),
            credential_scores=credentials,
            industry_weights=industry_weights,
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['sw1_code'], SECTOR_CODE)
        self.assertEqual(events[0]['weak_net_action'], -3.0)
        self.assertEqual(events[0]['strong_net_action'], 2.5)
        self.assertEqual(events[0]['strong_add_count'], 2)


if __name__ == '__main__':
    unittest.main()
