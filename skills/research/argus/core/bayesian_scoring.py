# skills/research/argus/core/bayesian_scoring.py
"""Minimal Bayesian scoring for Argus signal-pool records."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from ..config import ARGUS_CONFIG


class BayesianScorer:
    """Calculate the Phase 1 Bayesian score from explicit factor inputs."""

    DEFAULT_WEIGHTS = {
        'rebalancing_score': 0.30,
        'product_credibility': 0.25,
        'consensus_score': 0.25,
        'direction_score': 0.20,
    }
    REBALANCING_SCORES = {
        'NEW_ENTRY': 1.0,
        'CONCENTRATED_ADD': 0.9,
        'HIDDEN_BUILD': 0.85,
        'CONTINUOUS_ADD': 0.8,
        'CONSENSUS_ADD': 0.7,
        'HOLD': 0.5,
        'PARTIAL_EXIT': 0.3,
        'FULL_EXIT': 0.1,
    }
    DIRECTION_SCORES = {'BUY': 0.8, 'SELL': -0.8, 'HOLD': 0.0}

    def __init__(
        self,
        config: Optional[Dict] = None,
        product_profiles: Optional[Iterable[Dict]] = None,
    ) -> None:
        self.config = config or ARGUS_CONFIG.get('bayesian_scoring', {})
        self.weights = {**self.DEFAULT_WEIGHTS, **self.config.get('weights', {})}
        self.product_credibility = self._build_product_credibility(product_profiles or [])

    def score_signal_pool_record(self, record: Dict, signals: List[Dict]) -> Dict:
        """Return a scored copy of one signal-pool record."""
        products = record.get('contributing_products') or []
        factors = {
            'rebalancing_score': self._aggregate_signal_factor(signals, self.rebalancing_score_for_signal),
            'product_credibility': self.product_credibility_for_products(products),
            'consensus_score': self.consensus_score(record.get('contributing_products_count', len(products))),
            'direction_score': self._aggregate_signal_factor(signals, self.direction_score_for_signal),
        }
        score = self.calculate(factors)
        return {
            **record,
            'bayesian_score': round(score, 4),
            'bayesian_factors': {key: round(value, 4) for key, value in factors.items()},
        }

    def score_signal_pool_records(self, records: List[Dict], signals: List[Dict]) -> List[Dict]:
        """Score all signal-pool records using the related raw signals."""
        signals_by_stock = defaultdict(list)
        for signal in signals:
            for target in signal.get('target_stocks', []):
                wind_code = target.get('wind_code')
                if wind_code:
                    signals_by_stock[wind_code].append(signal)
        return [
            self.score_signal_pool_record(record, signals_by_stock.get(record.get('wind_code'), []))
            for record in records
        ]

    def calculate(self, factors: Dict[str, float]) -> float:
        raw_score = sum(self.weights[key] * factors.get(key, 0.0) for key in self.weights)
        return max(0.0, min(1.0, raw_score))

    def rebalancing_score_for_signal(self, signal: Dict) -> float:
        event_type = signal.get('rebalancing_event_type') or signal.get('metadata', {}).get('rebalancing_event_type')
        return self.REBALANCING_SCORES.get(event_type, self.REBALANCING_SCORES['HOLD'])

    def direction_score_for_signal(self, signal: Dict) -> float:
        return signal.get('direction_score', self.DIRECTION_SCORES.get(signal.get('signal_type', 'HOLD'), 0.0))

    def product_credibility_for_products(self, product_codes: Iterable[str]) -> float:
        scores = [self.product_credibility.get(code, 0.5) for code in product_codes if code]
        return sum(scores) / len(scores) if scores else 0.5

    @staticmethod
    def consensus_score(product_count: int) -> float:
        if product_count >= 5:
            return 1.0
        if product_count >= 3:
            return 0.7
        if product_count == 2:
            return 0.4
        return 0.2

    @staticmethod
    def _aggregate_signal_factor(signals: List[Dict], factor_func) -> float:
        if not signals:
            return 0.0
        return sum(factor_func(signal) for signal in signals) / len(signals)

    @staticmethod
    def _build_product_credibility(product_profiles: Iterable[Dict]) -> Dict[str, float]:
        credibility = {}
        for profile in product_profiles:
            product_code = profile.get('product_code')
            alpha = profile.get('alpha')
            beta = profile.get('beta')
            if not product_code or product_code in credibility or alpha is None or beta is None:
                continue
            total = float(alpha) + float(beta)
            credibility[product_code] = max(0.0, min(1.0, float(alpha) / total)) if total > 0 else 0.5
        return credibility
