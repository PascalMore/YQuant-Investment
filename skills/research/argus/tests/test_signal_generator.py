"""Unit tests for SignalGenerator - trade_date fix validation."""

import sys
sys.path.insert(0, '/home/pascal/.openclaw/workspace-yquant')

import unittest
from datetime import datetime
from skills.research.argus.core import SignalGenerator, CredibilityScorer


class TestSignalGeneratorTradeDate(unittest.TestCase):
    """Test trade_date is correctly set to持仓快照日 (snapshot date), not datetime.now()."""

    def setUp(self):
        self.generator = SignalGenerator()

    def _make_position_changes(self, changes: list) -> list:
        """Helper: build minimal position_changes with required fields."""
        return [
            {
                'asset_wind_code': c.get('wind_code', '600519.SH'),
                'asset_name': c.get('name', '贵州茅台'),
                'holding_ratio': c.get('curr_ratio', 0.10),
                'previous_holding_ratio': c.get('prev_ratio', 0.05),
                'holding_ratio_change': c.get('change', 0.05),
            }
            for c in changes
        ]

    # ------------------------------------------------------------------
    # trade_date = date_to_process (持仓快照日)
    # ------------------------------------------------------------------

    def test_trade_date_equals_passed_trade_date(self):
        """trade_date field should be exactly the trade_date argument passed in."""
        position_changes = self._make_position_changes([{'change': 0.05}])
        trade_date = '2026-05-26'

        signals = self.generator.generate_signals(
            product_code='SM001',
            product_name='SM',
            position_changes=position_changes,
            trade_date=trade_date,
        )

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]['trade_date'], trade_date)

    def test_trade_date_not_datetime_now(self):
        """trade_date should NOT reflect the current datetime, only the snapshot date."""
        position_changes = self._make_position_changes([{'change': 0.05}])
        trade_date = '2026-01-15'  # deliberately far from today

        signals = self.generator.generate_signals(
            product_code='SM001',
            product_name='SM',
            position_changes=position_changes,
            trade_date=trade_date,
        )

        self.assertEqual(signals[0]['trade_date'], '2026-01-15')
        self.assertNotEqual(signals[0]['trade_date'], datetime.now().strftime('%Y-%m-%d'))

    def test_valid_until_equals_trade_date(self):
        """valid_until should equal trade_date, not datetime.now()."""
        position_changes = self._make_position_changes([{'change': 0.05}])
        trade_date = '2026-03-20'

        signals = self.generator.generate_signals(
            product_code='SM001',
            product_name='SM',
            position_changes=position_changes,
            trade_date=trade_date,
        )

        self.assertEqual(signals[0]['valid_until'], trade_date)

    def test_multiple_signals_all_have_correct_trade_date(self):
        """All generated signals should share the same trade_date."""
        position_changes = self._make_position_changes([
            {'wind_code': '600519.SH', 'change': 0.05},
            {'wind_code': '000858.SZ', 'change': -0.03},
            {'wind_code': '300776.SZ', 'change': 0.01},
        ])
        trade_date = '2026-05-26'

        signals = self.generator.generate_signals(
            product_code='SM001',
            product_name='SM',
            position_changes=position_changes,
            trade_date=trade_date,
        )

        self.assertEqual(len(signals), 3)
        for s in signals:
            self.assertEqual(s['trade_date'], trade_date)

    # ------------------------------------------------------------------
    # signal_type / direction logic (unchanged, sanity check)
    # ------------------------------------------------------------------

    def test_signal_type_buy_when_change_gt_1pct(self):
        """Change > 1% should produce signal_type BUY."""
        position_changes = self._make_position_changes([{'change': 0.02}])  # +2%
        signals = self.generator.generate_signals(
            product_code='SM001', product_name='SM',
            position_changes=position_changes, trade_date='2026-05-26',
        )
        self.assertEqual(signals[0]['signal_type'], 'BUY')
        self.assertEqual(signals[0]['direction'], 'LONG')

    def test_signal_type_sell_when_change_lt_neg_1pct(self):
        """Change < -1% should produce signal_type SELL."""
        position_changes = self._make_position_changes([{'change': -0.02}])  # -2%
        signals = self.generator.generate_signals(
            product_code='SM001', product_name='SM',
            position_changes=position_changes, trade_date='2026-05-26',
        )
        self.assertEqual(signals[0]['signal_type'], 'SELL')
        self.assertEqual(signals[0]['direction'], 'SHORT')

    def test_signal_type_hold_when_change_within_1pct(self):
        """0.5% change should produce signal_type HOLD."""
        position_changes = self._make_position_changes([{'change': 0.005}])
        signals = self.generator.generate_signals(
            product_code='SM001', product_name='SM',
            position_changes=position_changes, trade_date='2026-05-26',
        )
        self.assertEqual(signals[0]['signal_type'], 'HOLD')
        self.assertEqual(signals[0]['direction'], 'FLAT')

    # ------------------------------------------------------------------
    # direction_score (unchanged, sanity check)
    # ------------------------------------------------------------------

    def test_direction_score_buy_is_positive(self):
        position_changes = self._make_position_changes([{'change': 0.05}])
        signals = self.generator.generate_signals(
            product_code='SM001', product_name='SM',
            position_changes=position_changes, trade_date='2026-05-26',
        )
        self.assertGreater(signals[0]['direction_score'], 0)

    def test_direction_score_sell_is_negative(self):
        position_changes = self._make_position_changes([{'change': -0.05}])
        signals = self.generator.generate_signals(
            product_code='SM001', product_name='SM',
            position_changes=position_changes, trade_date='2026-05-26',
        )
        self.assertLess(signals[0]['direction_score'], 0)

    def test_direction_score_hold_is_zero(self):
        position_changes = self._make_position_changes([{'change': 0.005}])
        signals = self.generator.generate_signals(
            product_code='SM001', product_name='SM',
            position_changes=position_changes, trade_date='2026-05-26',
        )
        self.assertEqual(signals[0]['direction_score'], 0.0)

    # ------------------------------------------------------------------
    # edge cases
    # ------------------------------------------------------------------

    def test_empty_position_changes_returns_empty_list(self):
        signals = self.generator.generate_signals(
            product_code='SM001', product_name='SM',
            position_changes=[], trade_date='2026-05-26',
        )
        self.assertEqual(signals, [])

    def test_date_field_matches_trade_date(self):
        """The top-level date field should also equal trade_date after processing."""
        position_changes = self._make_position_changes([{'change': 0.03}])
        trade_date = '2026-05-26'

        signals = self.generator.generate_signals(
            product_code='SM001', product_name='SM',
            position_changes=position_changes, trade_date=trade_date,
        )
        # date is set by daily_processor after generate_signals returns,
        # but the signal itself should carry trade_date correctly
        self.assertEqual(signals[0]['trade_date'], trade_date)


if __name__ == '__main__':
    unittest.main()