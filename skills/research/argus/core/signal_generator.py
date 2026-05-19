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
        pool_zone: str = 'WATCH',
        darwin_moment: bool = False,
        consensus_direction: str = 'NEUTRAL'
    ) -> List[Dict]:
        """Generate signals for target stocks.
        
        Args:
            product_code: Product code
            product_name: Product name
            position_changes: List of position changes
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
        credibility_score: float,
        pool_zone: str,
        darwin_moment: bool,
        consensus_direction: str
    ) -> Dict:
        """Create a single signal dictionary."""
        # Determine signal type based on holding ratio change
        change = pos_change.get('holding_ratio_change', 0)
        
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
            'pool_zone': pool_zone,
            'trade_date': generated_at.strftime('%Y-%m-%d'),
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
            'valid_until': generated_at.strftime('%Y-%m-%d'),
            'metadata': {
                'credibility_score': credibility_score,
                'crowding_level': 'MEDIUM',  # Would be calculated
                'time_horizon': 'MEDIUM',
                'pool_zone': pool_zone,
                'contributing_products_count': 1,
                'darwin_moment': darwin_moment,
                'consensus_direction': consensus_direction,
            }
        }
