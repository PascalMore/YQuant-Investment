"""Unit tests for IndustryWeightCalculator - 60d baseline support."""

import sys
sys.path.insert(0, '/home/pascal/.openclaw/workspace-yquant')

import unittest
from skills.research.argus.core import IndustryWeightCalculator


class TestIndustryWeightCalculator60d(unittest.TestCase):
    """Test 60d baseline support in IndustryWeightCalculator."""

    def _positions(self, holdings: list) -> list:
        """Build minimal position records."""
        return [
            {
                'product_code': h['product'],
                'asset_wind_code': h['wind'],
                'holding_ratio': h['ratio'],
                'product_name': h.get('name', 'Product'),
            }
            for h in holdings
        ]

    def _weights(self, entries: list) -> list:
        """Build minimal industry-weight records (baseline snapshots)."""
        return [
            {
                'date': e['date'],
                'product_code': e['product'],
                'sw1_code': e['sw1'],
                'sw1_name': e['sw1_name'],
                'weight_pct': e['weight'],
                'product_name': e.get('name', 'Product'),
            }
            for e in entries
        ]

    def _sector_info(self) -> list:
        """Standard SW1 sector mapping for test stocks."""
        return [
            {'asset_wind_code': '600519.SH', 'sw1_code': '801050.SI', 'sw1_name': '食品饮料'},
            {'asset_wind_code': '000858.SZ', 'sw1_code': '801050.SI', 'sw1_name': '食品饮料'},
            {'asset_wind_code': '300776.SZ', 'sw1_code': '801030.SI', 'sw1_name': '基础化工'},
        ]

    # ------------------------------------------------------------------
    # weight_change_60d
    # ------------------------------------------------------------------

    def test_weight_change_60d_calculated_when_baseline_exists(self):
        """60d change should be computed when lookback_60d_weights is provided."""
        positions = self._positions([
            {'product': 'SM001', 'wind': '600519.SH', 'ratio': 0.10},
        ])
        baseline_60d = self._weights([
            {'date': '2026-03-01', 'product': 'SM001', 'sw1': '801050.SI', 'sw1_name': '食品饮料', 'weight': 5.0},
        ])

        records = IndustryWeightCalculator.calculate(
            date='2026-05-01',
            positions=positions,
            sector_info=self._sector_info(),
            lookback_60d_weights=baseline_60d,
        )

        sm001 = next(r for r in records if r['product_code'] == 'SM001' and r['sw1_code'] == '801050.SI')
        self.assertEqual(sm001['weight_change_60d'], 5.0)  # 10% - 5% = 5%
        self.assertTrue(sm001['has_60d_baseline'])

    def test_weight_change_60d_none_when_baseline_missing(self):
        """60d change should be None when the product had no position in that sector 60d ago."""
        positions = self._positions([
            {'product': 'SM001', 'wind': '600519.SH', 'ratio': 0.10},
        ])

        records = IndustryWeightCalculator.calculate(
            date='2026-05-01',
            positions=positions,
            sector_info=self._sector_info(),
            lookback_60d_weights=[],
        )

        sm001 = next(r for r in records if r['product_code'] == 'SM001' and r['sw1_code'] == '801050.SI')
        self.assertIsNone(sm001['weight_change_60d'])
        self.assertFalse(sm001['has_60d_baseline'])

    def test_weight_change_60d_none_for_unknown_sector(self):
        """UNKNOWN sector should always have None for 60d change regardless of baseline."""
        positions = self._positions([
            {'product': 'SM001', 'wind': 'XXXXXX.UN', 'ratio': 0.05},
        ])
        baseline_60d = self._weights([
            {'date': '2026-03-01', 'product': 'SM001', 'sw1': 'UNKNOWN', 'sw1_name': '未映射', 'weight': 5.0},
        ])

        records = IndustryWeightCalculator.calculate(
            date='2026-05-01',
            positions=positions,
            sector_info=[],
            lookback_60d_weights=baseline_60d,
        )

        unk = next(r for r in records if r['sw1_code'] == 'UNKNOWN')
        self.assertIsNone(unk['weight_change_60d'])

    def test_weight_change_60d_none_for_new_sector_exposure(self):
        """When a product enters a new sector (had no 60d baseline there), 60d change is None."""
        positions = self._positions([
            {'product': 'SM001', 'wind': '300776.SZ', 'ratio': 0.08},  # 基础化工 - new exposure
        ])
        # SM001 held 食品饮料 60d ago but not 基础化工
        baseline_60d = self._weights([
            {'date': '2026-03-01', 'product': 'SM001', 'sw1': '801050.SI', 'sw1_name': '食品饮料', 'weight': 8.0},
        ])

        records = IndustryWeightCalculator.calculate(
            date='2026-05-01',
            positions=positions,
            sector_info=self._sector_info(),
            lookback_60d_weights=baseline_60d,
        )

        chem = next(r for r in records if r['sw1_code'] == '801030.SI')
        self.assertIsNone(chem['weight_change_60d'])
        self.assertFalse(chem['has_60d_baseline'])

    def test_both_30d_and_60d_baselines_provided(self):
        """When both 30d and 60d baselines are provided, both deltas should be calculated."""
        positions = self._positions([
            {'product': 'SM001', 'wind': '600519.SH', 'ratio': 0.15},
        ])
        baseline_30d = self._weights([
            {'date': '2026-04-01', 'product': 'SM001', 'sw1': '801050.SI', 'sw1_name': '食品饮料', 'weight': 8.0},
        ])
        baseline_60d = self._weights([
            {'date': '2026-03-01', 'product': 'SM001', 'sw1': '801050.SI', 'sw1_name': '食品饮料', 'weight': 5.0},
        ])

        records = IndustryWeightCalculator.calculate(
            date='2026-05-01',
            positions=positions,
            sector_info=self._sector_info(),
            lookback_30d_weights=baseline_30d,
            lookback_60d_weights=baseline_60d,
        )

        sm001 = next(r for r in records if r['product_code'] == 'SM001' and r['sw1_code'] == '801050.SI')
        self.assertEqual(sm001['weight_change_30d'], 7.0)   # 15 - 8
        self.assertEqual(sm001['weight_change_60d'], 10.0)  # 15 - 5
        self.assertTrue(sm001['has_30d_baseline'])
        self.assertTrue(sm001['has_60d_baseline'])

    def test_unknown_sector_excluded_from_30d_and_60d(self):
        """UNKNOWN sw1_code should be excluded from both 30d and 60d delta calculations."""
        positions = self._positions([
            {'product': 'SM001', 'wind': 'XXXXXX.UN', 'ratio': 0.03},
        ])
        baseline_30d = self._weights([
            {'date': '2026-04-01', 'product': 'SM001', 'sw1': 'UNKNOWN', 'sw1_name': '未映射', 'weight': 3.0},
        ])
        baseline_60d = self._weights([
            {'date': '2026-03-01', 'product': 'SM001', 'sw1': 'UNKNOWN', 'sw1_name': '未映射', 'weight': 2.0},
        ])

        records = IndustryWeightCalculator.calculate(
            date='2026-05-01',
            positions=positions,
            sector_info=[],
            lookback_30d_weights=baseline_30d,
            lookback_60d_weights=baseline_60d,
        )

        unk = next(r for r in records if r['sw1_code'] == 'UNKNOWN')
        self.assertIsNone(unk['weight_change_30d'])
        self.assertIsNone(unk['weight_change_60d'])
        self.assertFalse(unk['has_30d_baseline'])
        self.assertFalse(unk['has_60d_baseline'])

    # ------------------------------------------------------------------
    # acceleration via consensus_direction formula
    # ------------------------------------------------------------------

    def test_acceleration_formula(self):
        """acceleration = delta_30d - (delta_60d - delta_30d)"""
        from skills.research.argus.core.consensus_direction import ConsensusDirectionEngine

        industry_weights = [
            {
                'sw1_code': '801050.SI',
                'sw1_name': '食品饮料',
                'weight_change_30d': 5.0,
                'weight_change_60d': 8.0,
            },
        ]

        result = ConsensusDirectionEngine().calculate_for_date('2026-05-01', industry_weights)
        sector = result['sector_conviction']['801050.SI']

        # delta_30d = 5.0, delta_60d = 8.0
        # acceleration = 5.0 - (8.0 - 5.0) = 5.0 - 3.0 = 2.0
        self.assertEqual(sector['delta_30d'], 5.0)
        self.assertEqual(sector['delta_60d'], 8.0)
        self.assertEqual(sector['acceleration'], 2.0)

    def test_acceleration_with_only_30d_no_60d(self):
        """When 60d is missing but 30d exists, acceleration should be None."""
        from skills.research.argus.core.consensus_direction import ConsensusDirectionEngine

        industry_weights = [
            {
                'sw1_code': '801050.SI',
                'sw1_name': '食品饮料',
                'weight_change_30d': 5.0,
                'weight_change_60d': None,
            },
        ]

        result = ConsensusDirectionEngine().calculate_for_date('2026-05-01', industry_weights)
        sector = result['sector_conviction']['801050.SI']
        self.assertEqual(sector['delta_30d'], 5.0)
        self.assertIsNone(sector['delta_60d'])
        self.assertIsNone(sector['acceleration'])


if __name__ == '__main__':
    unittest.main()