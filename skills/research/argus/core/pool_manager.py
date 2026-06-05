# skills/research/argus/core/pool_manager.py
"""Four-zone stock pool management."""

import logging
from typing import List, Dict, Set, Optional

from ..config import ARGUS_CONFIG
from .zone_rule_engine import DEFAULT_ZONE_RULE_ENGINE, ZoneRuleEngine

logger = logging.getLogger(__name__)


class PoolManager:
    """Manage the four-zone stock pool: SCAN/WATCH/CANDIDATE/CONVICTION.
    
    Zone definitions:
    - CONVICTION: High confidence, multi-product consensus
    - CANDIDATE: Medium confidence, some consensus
    - WATCH: Low confidence, needs monitoring
    - SCAN: New signals, under evaluation
    """
    
    ZONES = ['SCAN', 'WATCH', 'CANDIDATE', 'CONVICTION']
    
    def __init__(self, zone_rule_engine: Optional[ZoneRuleEngine] = None):
        # DEPRECATED: pool_zones migrated to config/zone_rules_template.yaml.
        # Kept as an unused compatibility hook for rollback-era callers.
        self.config = ARGUS_CONFIG.get('pool_zones', {})
        self.zone_rule_engine = zone_rule_engine or DEFAULT_ZONE_RULE_ENGINE
    
    def classify_stock(
        self,
        wind_code: str,
        stock_name: str,
        confidence: float,
        contributing_products: List[str],
        darwin_moment: bool = False
    ) -> str:
        """Classify a stock into a pool zone.
        
        Args:
            wind_code: Stock wind code
            stock_name: Stock name
            confidence: Signal confidence score
            contributing_products: List of product codes contributing to signal
            darwin_moment: Whether this is a Darwin moment
        
        Returns:
            str: Pool zone (SCAN/WATCH/CANDIDATE/CONVICTION)
        """
        # DEPRECATED compatibility path: legacy callers still pass `confidence`
        # instead of a full bayesian signal-pool record. Zone thresholds and
        # Darwin floor semantics now live in config/zone_rules_template.yaml.
        darwin_confidence = 1.0 if darwin_moment else None
        decision = self.zone_rule_engine.classify_initial_zone({
            'bayesian_score': confidence,
            'consensus_confidence': confidence,
            'contributing_products_count': len(contributing_products),
            'contributing_products': contributing_products,
            'darwin_moment': darwin_moment,
            'darwin_confidence': darwin_confidence,
        })
        return decision.target_zone or 'SCAN'
    
    def update_pool(
        self,
        current_pool: Dict[str, Set[str]],
        new_signals: List[Dict]
    ) -> Dict[str, Set[str]]:
        """Update pool with new signals.
        
        Args:
            current_pool: Current pool state {zone: {wind_codes}}
            new_signals: List of new signals
        
        Returns:
            Dict[str, Set[str]]: Updated pool state
        """
        # Initialize if empty
        if not current_pool:
            current_pool = {zone: set() for zone in self.ZONES}
        
        for signal in new_signals:
            for target in signal.get('target_stocks', []):
                wind_code = target.get('wind_code')
                confidence = signal.get('confidence', 0)
                products = [signal.get('product_code')]
                darwin = signal.get('metadata', {}).get('darwin_moment', False)
                
                zone = self.classify_stock(
                    wind_code,
                    target.get('stock_name'),
                    confidence,
                    products,
                    darwin
                )
                
                # Add to new zone, remove from others
                for z in self.ZONES:
                    current_pool[z].discard(wind_code)
                current_pool[zone].add(wind_code)
        
        logger.info(f"[PoolManager] Pool updated: {', '.join(f'{z}={len(s)}' for z, s in current_pool.items())}")
        return current_pool
    
    def get_pool_summary(self, pool: Dict[str, Set[str]]) -> Dict[str, int]:
        """Get pool summary counts.
        
        Args:
            pool: Pool state
        
        Returns:
            Dict[str, int]: Zone counts
        """
        return {zone: len(stocks) for zone, stocks in pool.items()}
