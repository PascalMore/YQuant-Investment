# skills/research/argus/core/consensus_direction.py
"""Prosperity Gauge + Conviction Radar for ARGUS Phase 4C."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ..config import ARGUS_CONFIG

logger = logging.getLogger(__name__)


class ProsperityGauge:
    """Calculate market prosperity direction based on sector weight changes.
    
    Prosperity delta = Σ(cyclical 30d weight change) - Σ(defensive 30d weight change)
    Signal: BULLISH (>+2pp) / NEUTRAL / DEFENSIVE (<-2pp)
    """
    
    CYCLICAL_CODES = {"801050.SI", "801040.SI", "801030.SI", "801890.SI", "801880.SI"}
    DEFENSIVE_CODES = {"801120.SI", "801150.SI", "801160.SI", "801780.SI"}
    
    # Signal thresholds (pp)
    BULLISH_THRESHOLD = 2.0
    DEFENSIVE_THRESHOLD = -2.0
    
    def __init__(self):
        self.config = ARGUS_CONFIG.get('industry_groups', {})
    
    def calculate(
        self,
        date: str,
        industry_weights: List[Dict]
    ) -> Dict:
        """Calculate prosperity direction for a given date.
        
        Args:
            date: Calculation date (YYYY-MM-DD)
            industry_weights: List of industry weight records from industry_weight_calculator
        
        Returns:
            Dict with prosperity_signal, prosperity_delta, cyclical_weight_delta, defensive_weight_delta
        """
        cyclical_delta = 0.0
        defensive_delta = 0.0
        
        for w in industry_weights:
            sw1_code = w.get('sw1_code', '')
            change_30d = w.get('weight_change_30d') or 0
            
            if sw1_code in self.CYCLICAL_CODES:
                cyclical_delta += change_30d
            elif sw1_code in self.DEFENSIVE_CODES:
                defensive_delta += change_30d
        
        prosperity_delta = cyclical_delta - defensive_delta
        
        # Determine signal
        if prosperity_delta > self.BULLISH_THRESHOLD:
            prosperity_signal = 'BULLISH'
        elif prosperity_delta < self.DEFENSIVE_THRESHOLD:
            prosperity_signal = 'DEFENSIVE'
        else:
            prosperity_signal = 'NEUTRAL'
        
        logger.info(
            f"[ProsperityGauge] {date}: signal={prosperity_signal}, "
            f"delta={prosperity_delta:.2f}pp (cyclical={cyclical_delta:.2f}, defensive={defensive_delta:.2f})"
        )
        
        return {
            'prosperity_signal': prosperity_signal,
            'prosperity_delta': round(prosperity_delta, 4),
            'cyclical_weight_delta': round(cyclical_delta, 4),
            'defensive_weight_delta': round(defensive_delta, 4),
        }


class ConvictionRadar:
    """Calculate sector conviction shifts based on 30d/60d weight changes.
    
    Acceleration = delta_30d - (delta_60d - delta_30d)
    Positive acceleration = conviction rising
    Baseline: 6-month rolling mean (Kahneman recommendation)
    """
    
    def __init__(self):
        pass
    
    def calculate(
        self,
        date: str,
        industry_weights: List[Dict]
    ) -> Dict:
        """Calculate conviction shifts for all sectors.
        
        Args:
            date: Calculation date (YYYY-MM-DD)
            industry_weights: List of industry weight records
        
        Returns:
            Dict with sector_conviction, top_rising_sectors, top_falling_sectors
        """
        sector_conviction = {}
        
        for w in industry_weights:
            sw1_code = w.get('sw1_code', '')
            sw1_name = w.get('sw1_name', '')
            delta_30d = w.get('weight_change_30d')
            delta_60d = w.get('weight_change_60d')
            
            if delta_30d is None:
                continue
            
            # Calculate acceleration if 60d data available
            if delta_60d is not None:
                acceleration = delta_30d - (delta_60d - delta_30d)
            else:
                acceleration = None
            
            sector_conviction[sw1_code] = {
                'sw1_name': sw1_name,
                'delta_30d': round(delta_30d, 4) if delta_30d is not None else None,
                'delta_60d': round(delta_60d, 4) if delta_60d else None,
                'acceleration': round(acceleration, 4) if acceleration is not None else None,
            }
        
        # Sort by delta_30d to find top rising/falling
        sorted_sectors = sorted(
            [(k, v) for k, v in sector_conviction.items() if v.get('delta_30d') is not None],
            key=lambda x: x[1]['delta_30d'],
            reverse=True
        )
        
        top_rising = [s[0] for s in sorted_sectors[:3]]
        top_falling = [s[0] for s in sorted_sectors[-3:]]
        
        logger.info(
            f"[ConvictionRadar] {date}: {len(sector_conviction)} sectors analyzed, "
            f"top_rising={top_rising[:2]}, top_falling={top_falling[-2:]}"
        )
        
        return {
            'sector_conviction': sector_conviction,
            'top_rising_sectors': top_rising,
            'top_falling_sectors': top_falling,
        }


class ConsensusDirectionEngine:
    """Combined Prosperity Gauge + Conviction Radar for Phase 4C."""
    
    def __init__(self):
        self.prosperity_gauge = ProsperityGauge()
        self.conviction_radar = ConvictionRadar()
    
    def calculate_for_date(
        self,
        date: str,
        industry_weights: List[Dict]
    ) -> Dict:
        """Calculate complete consensus direction for a date.
        
        Args:
            date: Calculation date
            industry_weights: Industry weight records
        
        Returns:
            Dict with all consensus direction fields
        """
        prosperity = self.prosperity_gauge.calculate(date, industry_weights)
        conviction = self.conviction_radar.calculate(date, industry_weights)
        
        result = {
            'date': date,
            'prosperity_signal': prosperity['prosperity_signal'],
            'prosperity_delta': prosperity['prosperity_delta'],
            'cyclical_weight_delta': prosperity['cyclical_weight_delta'],
            'defensive_weight_delta': prosperity['defensive_weight_delta'],
            'sector_conviction': conviction['sector_conviction'],
            'top_rising_sectors': conviction['top_rising_sectors'],
            'top_falling_sectors': conviction['top_falling_sectors'],
            'created_at': datetime.now().isoformat(),
        }
        
        logger.info(
            f"[ConsensusDirectionEngine] {date}: prosperity={prosperity['prosperity_signal']}, "
            f"sectors={len(conviction['sector_conviction'])}"
        )
        
        return result
