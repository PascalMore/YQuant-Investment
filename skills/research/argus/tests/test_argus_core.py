# skills/research/argus/tests/test_argus_core.py
"""Unit tests for Argus core modules."""

import sys
sys.path.insert(0, '/home/pascal/.openclaw/workspace-yquant')

import unittest
from skills.research.argus.core import (
    CredibilityScorer,
    SignalGenerator,
    PoolManager,
    RebalancingDetector,
    DarwinDetector,
    ConsensusEngine,
    BayesianScorer,
)


class TestCredibilityScorer(unittest.TestCase):
    """Test credibility scoring."""
    
    def setUp(self):
        self.scorer = CredibilityScorer()
    
    def test_high_conviction(self):
        """Test high conviction positions."""
        position_changes = [
            {'asset_wind_code': '600519.SH', 'holding_ratio_change': 0.05},
            {'asset_wind_code': '000858.SZ', 'holding_ratio_change': 0.03},
        ]
        score = self.scorer.calculate_score('SM001', position_changes)
        self.assertGreater(score, 0.6)
    
    def test_no_data(self):
        """Test neutral score when no data."""
        score = self.scorer.calculate_score('SM001', [])
        self.assertEqual(score, 0.5)
    
    def test_confidence_levels(self):
        """Test confidence level labels."""
        self.assertEqual(self.scorer.get_confidence_level(0.9), 'HIGH')
        self.assertEqual(self.scorer.get_confidence_level(0.7), 'MEDIUM')
        self.assertEqual(self.scorer.get_confidence_level(0.5), 'LOW')
        self.assertEqual(self.scorer.get_confidence_level(0.2), 'NONE')


class TestPoolManager(unittest.TestCase):
    """Test pool management."""
    
    def setUp(self):
        self.manager = PoolManager()
    
    def test_conviction_zone(self):
        """Test conviction zone classification."""
        zone = self.manager.classify_stock(
            '600519.SH', '贵州茅台', 0.85, ['SM001', 'SM002', 'SM003'], False
        )
        self.assertEqual(zone, 'CONVICTION')
    
    def test_scan_zone(self):
        """Test scan zone classification."""
        zone = self.manager.classify_stock(
            '600519.SH', '贵州茅台', 0.2, ['SM001'], False
        )
        self.assertEqual(zone, 'SCAN')

    def test_darwin_zone_is_candidate_minimum(self):
        """Darwin moment stocks should be promoted to CANDIDATE at minimum."""
        zone = self.manager.classify_stock(
            '600519.SH', '贵州茅台', 0.2, ['SM001'], True
        )
        self.assertEqual(zone, 'CANDIDATE')
    
    def test_pool_update(self):
        """Test pool update with signals."""
        current_pool = {zone: set() for zone in PoolManager.ZONES}
        # Use WATCH zone: single product, 0.55 confidence meets 0.45 threshold
        signals = [{
            'product_code': 'SM001',
            'confidence': 0.55,
            'target_stocks': [{'wind_code': '600519.SH', 'stock_name': '贵州茅台'}],
            'metadata': {'darwin_moment': False}
        }]
        updated = self.manager.update_pool(current_pool, signals)
        self.assertIn('600519.SH', updated['WATCH'])


class TestRebalancingDetector(unittest.TestCase):
    """Test rebalancing detection."""
    
    def setUp(self):
        self.detector = RebalancingDetector()
    
    def test_detect_rebalancing(self):
        """Test rebalancing event detection."""
        current = [
            {'asset_wind_code': '600519.SH', 'asset_name': '贵州茅台', 'holding_ratio': 0.10},
            {'asset_wind_code': '000858.SZ', 'asset_name': '五粮液', 'holding_ratio': 0.08},
        ]
        previous = [
            {'asset_wind_code': '600519.SH', 'asset_name': '贵州茅台', 'holding_ratio': 0.05},
            {'asset_wind_code': '000858.SZ', 'asset_name': '五粮液', 'holding_ratio': 0.08},
        ]
        events = self.detector.detect_rebalancing(current, previous)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['wind_code'], '600519.SH')
        self.assertEqual(events[0]['direction'], 'BUY')


class TestDarwinDetector(unittest.TestCase):
    """Test Darwin sector action calculations."""

    def setUp(self):
        self.detector = DarwinDetector()

    def test_sector_action_skips_missing_30d_change(self):
        """Missing weight_change_30d should not be treated as a new add."""
        records = [
            {
                'date': '2026-05-29',
                'product_code': 'SM001',
                'sw1_code': '801050.SI',
                'weight_change_30d': None,
            },
            {
                'date': '2026-05-29',
                'product_code': 'SM002',
                'sw1_code': '801050.SI',
                'weight_change_30d': -1.5,
            },
        ]

        net_action = self.detector._get_sector_net_action(
            ['SM001', 'SM002'],
            '801050.SI',
            records,
            '2026-05-29',
        )
        add_count = self.detector._count_sector_adds(
            ['SM001'],
            '801050.SI',
            records,
            '2026-05-29',
        )

        self.assertEqual(net_action, -1.5)
        self.assertEqual(add_count, 0)

    def test_sector_action_uses_weight_change_30d(self):
        """Normal 30-day changes should sum and count positive adds."""
        records = [
            {
                'date': '2026-05-29',
                'product_code': 'SM001',
                'sw1_code': '801050.SI',
                'weight_change_30d': 2.0,
            },
            {
                'date': '2026-05-29',
                'product_code': 'SM002',
                'sw1_code': '801050.SI',
                'weight_change_30d': -0.5,
            },
            {
                'date': '2026-05-29',
                'product_code': 'SM003',
                'sw1_code': '801050.SI',
                'weight_change_30d': 1.25,
            },
        ]

        self.assertEqual(
            self.detector._get_sector_net_action(['SM001', 'SM002', 'SM003'], '801050.SI', records, '2026-05-29'),
            2.75,
        )
        self.assertEqual(
            self.detector._count_sector_adds(['SM001', 'SM002', 'SM003'], '801050.SI', records, '2026-05-29'),
            2,
        )


class TestConsensusEngine(unittest.TestCase):
    """Test consensus calculation."""
    
    def setUp(self):
        self.engine = ConsensusEngine()
    
    def test_consensus_reached(self):
        """Test consensus calculation."""
        signals = [
            {'product_code': 'SM001', 'signal_type': 'BUY', 'confidence': 0.8,
             'target_stocks': [{'wind_code': '600519.SH'}]},
            {'product_code': 'SM002', 'signal_type': 'BUY', 'confidence': 0.75,
             'target_stocks': [{'wind_code': '600519.SH'}]},
            {'product_code': 'SM003', 'signal_type': 'BUY', 'confidence': 0.7,
             'target_stocks': [{'wind_code': '600519.SH'}]},
        ]
        consensus = self.engine.calculate_consensus(signals)
        self.assertIn('600519.SH', consensus)
        self.assertEqual(consensus['600519.SH']['direction'], 'BUY')
        self.assertEqual(consensus['600519.SH']['count'], 3)


class TestBayesianScorer(unittest.TestCase):
    """Test Phase 1 Bayesian scoring."""

    def test_calculates_weighted_score_from_four_factors(self):
        scorer = BayesianScorer(product_profiles=[
            {'product_code': 'SM001', 'alpha': 8, 'beta': 2},
            {'product_code': 'SM002', 'alpha': 3, 'beta': 7},
        ])
        record = {
            'wind_code': '600519.SH',
            'contributing_products': ['SM001', 'SM002'],
            'contributing_products_count': 2,
            'confidence': 0.8,
        }
        signals = [
            {'product_code': 'SM001', 'signal_type': 'BUY', 'direction_score': 0.8, 'rebalancing_event_type': 'NEW_ENTRY'},
            {'product_code': 'SM002', 'signal_type': 'BUY', 'direction_score': 0.8, 'rebalancing_event_type': 'CONTINUOUS_ADD'},
        ]

        scored = scorer.score_signal_pool_record(record, signals)

        self.assertGreaterEqual(scored['bayesian_score'], 0)
        self.assertLessEqual(scored['bayesian_score'], 1)
        self.assertAlmostEqual(scored['bayesian_factors']['product_credibility'], 0.55)
        self.assertNotEqual(scored['bayesian_score'], scored['confidence'])

    def test_scoring_does_not_emit_weight_change_30d(self):
        """Signal-pool records should not persist industry 30-day weight changes."""
        scorer = BayesianScorer()
        record = {
            'wind_code': '600519.SH',
            'contributing_products': ['SM001'],
            'contributing_products_count': 1,
            'weight_change_30d': 2.5,
        }

        scored = scorer.score_signal_pool_record(record, [])

        self.assertNotIn('weight_change_30d', scored)

    def test_defaults_missing_product_profile_to_neutral_credibility(self):
        scorer = BayesianScorer()
        self.assertEqual(scorer.product_credibility_for_products(['UNKNOWN']), 0.5)


if __name__ == '__main__':
    unittest.main()
