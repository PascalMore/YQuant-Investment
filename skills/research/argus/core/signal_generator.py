# skills/research/argus/core/signal_generator.py
"""Multi-timeframe signal generation engine."""

import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional

from ..config import ARGUS_CONFIG
from .credibility import CredibilityScorer

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generate trading signals from Argus analysis.

    Combines credibility scores, position changes, and consensus
    to produce actionable signals for portfolio management.
    """

    def __init__(self, credibility_scorer: CredibilityScorer = None):
        self.credibility_scorer = credibility_scorer or CredibilityScorer()
        self.config = ARGUS_CONFIG.get('signal', {})
        self.high_confidence = self.config.get('high_confidence', 0.7)
        self.medium_confidence = self.config.get('medium_confidence', 0.5)

    def generate_signals(
        self,
        product_code: str,
        product_name: str,
        position_changes: List[Dict],
        trade_date: str,
        pool_zone: str = 'WATCH',
        darwin_moment: bool = False,
        consensus_direction: str = 'NEUTRAL'
    ) -> List[Dict]:
        """"Generate signals for target stocks.

        Args:
            product_code: Product code
            product_name: Product name
            position_changes: List of position changes
            trade_date: Trade date (持仓快照日，即实际交易日)
            pool_zone: Pool zone classification
            darwin_moment: Whether this is a Darwin moment
            consensus_direction: Consensus direction (BULLISH/BEARISH/NEUTRAL)

        Returns:
            List[Dict]: List of signal dictionaries
        """
        if not position_changes:
            return []

        # Calculate credibility score
        credibility_score = self.credibility_scorer.calculate_score(
            product_code, position_changes
        )

        # Generate signal for each position change
        signals = []
        for pos_change in position_changes:
            signal = self._create_signal(
                product_code=product_code,
                product_name=product_name,
                pos_change=pos_change,
                trade_date=trade_date,
                credibility_score=credibility_score,
                pool_zone=pool_zone,
                darwin_moment=darwin_moment,
                consensus_direction=consensus_direction
            )
            signals.append(signal)

        logger.info(f"[SignalGenerator] Generated {len(signals)} signals for {product_code}")
        return signals

    def _create_signal(
        self,
        product_code: str,
        product_name: str,
        pos_change: Dict,
        trade_date: str,
        credibility_score: float,
        pool_zone: str,
        darwin_moment: bool,
        consensus_direction: str
    ) -> Dict:
        """Create a single signal dictionary."""
        # Determine signal type based on holding ratio change
        change = pos_change.get('holding_ratio_change', 0)
        previous_ratio = pos_change.get('previous_holding_ratio', 0) or 0
        current_ratio = pos_change.get('holding_ratio', 0) or 0
        trade_direction = pos_change.get('trade_direction') or pos_change.get('direction_normalized')

        if change > 0.01:  # >1% increase
            signal_type = 'BUY'
            direction = 'LONG'
        elif change < -0.01:  # >1% decrease
            signal_type = 'SELL'
            direction = 'SHORT'
        else:
            signal_type = 'HOLD'
            direction = 'FLAT'

        # Calculate confidence
        confidence = credibility_score
        rebalancing_event_type = self._infer_rebalancing_event_type(
            signal_type,
            previous_ratio,
            current_ratio,
            trade_direction,
        )
        direction_score = {'BUY': 0.8, 'SELL': -0.8, 'HOLD': 0.0}.get(signal_type, 0.0)
        generated_at = datetime.now()
        wind_code = pos_change.get('asset_wind_code')

        return {
            'signal_id': str(uuid.uuid4()),
            'source': 'argus',
            'version': '1.0.0',
            'product_code': product_code,
            'product_name': product_name,
            'signal_type': signal_type,
            'confidence': round(confidence, 3),
            'direction': direction,
            'direction_score': direction_score,
            'rebalancing_event_type': rebalancing_event_type,
            'pool_zone': pool_zone,
            'trade_date': trade_date,
            'target_stocks': [{
                'stock_code': wind_code.split('.')[0] if wind_code else None,
                'wind_code': wind_code,
                'stock_name': pos_change.get('asset_name'),
                'action': signal_type,
                'holding_ratio_change': pos_change.get('holding_ratio_change', 0),
                'market_value_change': pos_change.get('market_value_change', 0),
            }],
            'reason': f"{product_name} {signal_type.lower()} signal for {pos_change.get('asset_name')}",
            'generated_at': generated_at.isoformat(),
            'valid_until': trade_date,
            'metadata': {
                'credibility_score': credibility_score,
                'crowding_level': 'MEDIUM',  # Would be calculated
                'time_horizon': 'MEDIUM',
                'pool_zone': pool_zone,
                'contributing_products_count': 1,
                'darwin_moment': darwin_moment,
                'consensus_direction': consensus_direction,
                'direction_score': direction_score,
                'rebalancing_event_type': rebalancing_event_type,
            }
        }

    @staticmethod
    def _infer_rebalancing_event_type(
        signal_type: str,
        previous_ratio: float,
        current_ratio: float,
        trade_direction: Optional[str] = None,
    ) -> str:
        """Infer rebalancing event type from holding changes.

        RFC defines 8 event types:
        - NEW_ENTRY: first time holding this stock
        - CONCENTRATED_ADD: large increase (>5pp) indicating concentrated buy
        - HIDDEN_BUILD: detected via annual vs quarterly holdings差异 (needs full holdings data)
        - CONTINUOUS_ADD: normal BUY signal
        - CONSENSUS_ADD: multiple products buying same stock simultaneously (needs multi-product data)
        - HOLD: no significant change
        - PARTIAL_EXIT: normal SELL signal
        - FULL_EXIT: completely sold out

        Note: HIDDEN_BUILD and CONSENSUS_ADD require additional data sources.
        """
        normalized_trade_direction = str(trade_direction or '').upper()
        ratio_change = abs(current_ratio - previous_ratio)

        if previous_ratio <= 0 and current_ratio > 0:
            return 'NEW_ENTRY'
        if current_ratio <= 0 and previous_ratio > 0:
            return 'FULL_EXIT'
        if signal_type == 'BUY' or normalized_trade_direction == 'BUY':
            # CONCENTRATED_ADD: large increase (>5 percentage points)
            if ratio_change > 0.05:
                return 'CONCENTRATED_ADD'
            return 'CONTINUOUS_ADD'
        if signal_type == 'SELL' or normalized_trade_direction == 'SELL':
            return 'PARTIAL_EXIT'
        return 'HOLD'
