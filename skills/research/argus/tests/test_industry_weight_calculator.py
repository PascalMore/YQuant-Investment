"""Unit tests for Argus industry weight aggregation."""

import sys
import unittest

sys.path.insert(0, '/home/pascal/.openclaw/workspace-yquant')

from skills.research.argus.core import IndustryWeightCalculator


class TestIndustryWeightCalculator(unittest.TestCase):
    def test_calculates_sw1_weights_and_baseline_changes(self):
        positions = [
            {'position_date': '2026-05-21', 'product_code': 'SM001', 'asset_wind_code': '600519.SH', 'holding_ratio': 0.08},
            {'position_date': '2026-05-21', 'product_code': 'SM001', 'asset_wind_code': '000858.SZ', 'holding_ratio': 0.04},
            {'position_date': '2026-05-21', 'product_code': 'SM001', 'asset_wind_code': '00700.HK', 'holding_ratio': 0.02},
        ]
        previous_positions = [
            {'date': '2026-05-20', 'product_code': 'SM001', 'sw1_code': '801120.SI', 'sw1_name': '食品饮料', 'weight_pct': 5.0},
        ]
        baseline_30d_positions = [
            {'date': '2026-04-21', 'product_code': 'SM001', 'sw1_code': '801120.SI', 'sw1_name': '食品饮料', 'weight_pct': 10.0},
            {'date': '2026-04-21', 'product_code': 'SM001', 'sw1_code': 'UNKNOWN', 'sw1_name': '未映射', 'weight_pct': 3.0},
        ]
        sector_info = [
            {'full_symbol': '600519.SH', 'l1_code': '801120', 'l1_name': '食品饮料'},
            {'full_symbol': '000858.SZ', 'l1_code': '801120', 'l1_name': '食品饮料'},
        ]

        records = IndustryWeightCalculator.calculate(
            '2026-05-21',
            positions,
            sector_info,
            previous_weights=previous_positions,
            lookback_30d_weights=baseline_30d_positions,
        )
        by_industry = {record['sw1_code']: record for record in records}

        self.assertEqual(by_industry['801120.SI']['weight_pct'], 12.0)
        self.assertEqual(by_industry['801120.SI']['weight_change_1d'], 7.0)
        self.assertEqual(by_industry['801120.SI']['weight_change_30d'], 2.0)
        self.assertEqual(by_industry['801120.SI']['positions_count'], 2)
        self.assertEqual(by_industry['UNKNOWN']['weight_pct'], 2.0)
        self.assertEqual(by_industry['UNKNOWN']['sw1_name'], '未映射')
        self.assertFalse(by_industry['UNKNOWN']['has_30d_baseline'])
        self.assertIsNone(by_industry['UNKNOWN']['weight_change_30d'])

    def test_missing_baselines_are_marked_as_unavailable(self):
        records = IndustryWeightCalculator.calculate(
            '2026-01-05',
            [{'product_code': 'SM001', 'asset_wind_code': '600519.SH', 'holding_ratio': 0.08}],
            [{'full_symbol': '600519.SH', 'sw1_code': '801120.SI', 'sw1_name': '食品饮料'}],
            previous_weights=[],
            lookback_30d_weights=[],
        )

        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]['has_1d_baseline'])
        self.assertFalse(records[0]['has_30d_baseline'])
        self.assertIsNone(records[0]['weight_change_1d'])
        self.assertIsNone(records[0]['weight_change_30d'])

    def test_negative_weight_pct_is_clipped_to_zero(self):
        records = IndustryWeightCalculator.calculate(
            '2026-05-06',
            [{'product_code': 'SM004', 'asset_wind_code': '600519.SH', 'holding_ratio': -0.000008}],
            [{'full_symbol': '600519.SH', 'sw1_code': '801880.SI', 'sw1_name': '有色金属'}],
        )

        self.assertEqual(records[0]['weight_pct'], 0.0)


if __name__ == '__main__':
    unittest.main()
