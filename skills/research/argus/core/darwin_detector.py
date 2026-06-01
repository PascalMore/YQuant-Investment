# skills/research/argus/core/darwin_detector.py
"""Darwin moment detection - Phase 4B implementation."""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from ..config import ARGUS_CONFIG

logger = logging.getLogger(__name__)


# SW Level 1 industry codes
SW_LEVEL1_CODES = [
    "801010.SI", "801030.SI", "801040.SI", "801050.SI", "801080.SI",
    "801110.SI", "801120.SI", "801130.SI", "801140.SI", "801150.SI",
    "801160.SI", "801170.SI", "801180.SI", "801200.SI", "801210.SI",
    "801230.SI", "801710.SI", "801720.SI", "801730.SI", "801740.SI",
    "801750.SI", "801760.SI", "801770.SI", "801780.SI", "801790.SI",
    "801880.SI", "801890.SI", "801950.SI", "801960.SI", "801970.SI",
    "801980.SI",
]

SW_NAME_MAP = {
    "801010.SI": "农林牧渔", "801030.SI": "基础化工", "801040.SI": "钢铁",
    "801050.SI": "有色金属", "801080.SI": "电子", "801110.SI": "家用电器",
    "801120.SI": "食品饮料", "801130.SI": "纺织服饰", "801140.SI": "轻工制造",
    "801150.SI": "医药生物", "801160.SI": "公用事业", "801170.SI": "交通运输",
    "801180.SI": "房地产", "801200.SI": "商贸零售", "801210.SI": "社会服务",
    "801230.SI": "综合", "801710.SI": "建筑材料", "801720.SI": "建筑装饰",
    "801730.SI": "电力设备", "801740.SI": "国防军工", "801750.SI": "计算机",
    "801760.SI": "传媒", "801770.SI": "通信", "801780.SI": "银行",
    "801790.SI": "非银金融", "801880.SI": "汽车", "801890.SI": "机械设备",
    "801950.SI": "煤炭", "801960.SI": "石油石化", "801970.SI": "环保",
    "801980.SI": "美容护理",
}

CSI300_CODE = "000300.SH"


class DarwinDetector:
    """Detect Darwin moments based on sector drawdown and product credibility divergence.
    
    Darwin moments occur when:
    - SW sector 20-day drawdown >= 10%
    - Weak products (credibility below daily 20th percentile) net sell
    - Strong products (credibility above daily 80th percentile) net hold/add
    - At least 2 strong products show hold/add
    
    Systemic filter: CSI300 20-day drawdown > 8% → confidence *= 0.70
    """
    
    def __init__(self):
        self.config = ARGUS_CONFIG.get('darwin', {})
        self.drawdown_threshold = self.config.get('drawdown_threshold', 0.10)  # 10%
        self.systemic_threshold = self.config.get('systemic_threshold', 0.08)   # 8%
        self.min_strong_add = self.config.get('min_strong_add', 2)
    
    def detect_for_date(
        self,
        date: str,
        index_quotes: List[Dict],
        credential_scores: List[Dict],
        industry_weights: List[Dict],
    ) -> List[Dict]:
        """Detect Darwin events for a given date.
        
        Args:
            date: Detection date (YYYY-MM-DD)
            index_quotes: Index daily quotes (from index_daily_quotes)
            credential_scores: Product credibility scores (from 08_research_argus_credential_score)
            industry_weights: Industry weight records (from 08_research_argus_industry_weight)
        
        Returns:
            List[Dict]: Darwin events detected
        """
        logger.info(f"[DarwinDetector] Starting Darwin detection for {date}")
        
        # Build index price lookup for 20d drawdown calculation
        index_lookup = self._build_index_lookup(index_quotes)
        
        # Get CSI300 20d drawdown for systemic filter
        csi300_drawdown = self._calc_index_drawdown(index_lookup, CSI300_CODE, date, window=20)
        
        # Build product credibility map and derive daily dynamic thresholds.
        credibility_map = {}
        for score_record in credential_scores:
            product_code = score_record.get('product_code')
            credibility_score = score_record.get('credibility_score')
            if not product_code or credibility_score is None:
                continue
            try:
                credibility_map[product_code] = float(credibility_score)
            except (TypeError, ValueError):
                continue
        if len(credibility_map) < 3:
            logger.info(
                "[DarwinDetector] Skip %s: only %d valid product credibility scores",
                date,
                len(credibility_map),
            )
            return []
        weak_threshold = self._percentile(list(credibility_map.values()), 0.20)
        strong_threshold = self._percentile(list(credibility_map.values()), 0.80)
        
        # Separate products into weak/strong groups
        weak_products = [p for p, c in credibility_map.items() if c < weak_threshold]
        strong_products = [p for p, c in credibility_map.items() if c > strong_threshold]
        
        logger.info(
            f"[DarwinDetector] Products: {len(weak_products)} weak (cred<20th={weak_threshold:.4f}), "
            f"{len(strong_products)} strong (cred>80th={strong_threshold:.4f})"
        )
        
        darwin_events = []
        
        for sw1_code in SW_LEVEL1_CODES:
            # Step 1: Calculate sector 20d drawdown
            sector_drawdown = self._calc_index_drawdown(index_lookup, sw1_code, date, window=20)
            
            if sector_drawdown is None or sector_drawdown >= -self.drawdown_threshold:
                continue  # 跌幅不足10%或数据不足，跳过
            
            # Step 2: Check if systemic
            is_systemic = csi300_drawdown < -self.systemic_threshold if csi300_drawdown is not None else False
            
            # Step 3: Calculate net actions
            weak_action = self._get_sector_net_action(weak_products, sw1_code, industry_weights, date, window=20)
            strong_action = self._get_sector_net_action(strong_products, sw1_code, industry_weights, date, window=20)
            strong_add_count = self._count_sector_adds(strong_products, sw1_code, industry_weights, date, window=20)
            
            # Step 4: Divergence detection
            if weak_action < 0 and strong_action >= 0 and strong_add_count >= self.min_strong_add:
                # Calculate confidence
                confidence = min(1.0, abs(weak_action) * max(0, strong_action) * strong_add_count * 0.1)
                
                if is_systemic:
                    confidence *= 0.70
                
                event = {
                    'date': date,
                    'sw1_code': sw1_code,
                    'sw1_name': SW_NAME_MAP.get(sw1_code, sw1_code),
                    'drawdown_20d': round(sector_drawdown, 4) if sector_drawdown else None,
                    'market_drawdown': round(csi300_drawdown, 4) if csi300_drawdown else None,
                    'is_systemic': is_systemic,
                    'weak_net_action': round(weak_action, 4),
                    'strong_net_action': round(strong_action, 4),
                    'strong_add_count': strong_add_count,
                    'confidence': round(confidence, 4),
                    'status': 'ACTIVE',
                    'created_at': datetime.now().isoformat(),
                }
                darwin_events.append(event)
                logger.warning(
                    f"[DarwinDetector] Darwin detected: {sw1_code}({event['sw1_name']}) "
                    f"drawdown={sector_drawdown:.2%}, weak_action={weak_action:.3f}, "
                    f"strong_action={strong_action:.3f}, strong_adds={strong_add_count}, "
                    f"confidence={confidence:.3f}, systemic={is_systemic}"
                )
        
        logger.info(f"[DarwinDetector] Detected {len(darwin_events)} Darwin events for {date}")
        return darwin_events
    
    def _build_index_lookup(self, index_quotes: List[Dict]) -> Dict[str, Dict[str, float]]:
        """Build index price lookup by code and date.
        
        Returns:
            {code: {date: close_price}}
        """
        lookup = {}
        for q in index_quotes:
            code = q.get('full_symbol') or q.get('code', '')
            date = q.get('trade_date')
            close = q.get('close')
            if code and date:
                if code not in lookup:
                    lookup[code] = {}
                lookup[code][date] = close
        return lookup

    def _percentile(self, values: List[float], quantile: float) -> float:
        """Return a linearly interpolated percentile for non-empty values."""
        sorted_values = sorted(values)
        if len(sorted_values) == 1:
            return sorted_values[0]

        position = (len(sorted_values) - 1) * quantile
        lower = int(position)
        upper = min(lower + 1, len(sorted_values) - 1)
        fraction = position - lower
        return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction
    
    def _build_weight_lookup(self, industry_weights: List[Dict]) -> Dict[str, Dict[str, float]]:
        """Build industry weight lookup by product, sector, and date.
        
        Returns:
            {(product_code, sw1_code, date): weight_pct}
        """
        lookup = {}
        for w in industry_weights:
            key = (w.get('product_code'), w.get('sw1_code'), w.get('date'))
            weight = w.get('weight_pct', 0)
            if key[0] and key[1] and key[2]:
                lookup[key] = weight
        return lookup
    
    def _calc_index_drawdown(
        self,
        index_lookup: Dict[str, Dict[str, float]],
        code: str,
        date: str,
        window: int = 20
    ) -> Optional[float]:
        """Calculate index drawdown over window days.
        
        Returns:
            Drawdown as negative percentage, or None if insufficient data
        """
        dates = sorted(index_lookup.get(code, {}).keys())
        if not dates or date not in dates:
            return None
        
        current_idx = dates.index(date)
        if current_idx < window:
            return None
        
        start_date = dates[current_idx - window]
        start_price = index_lookup[code].get(start_date)
        end_price = index_lookup[code].get(date)
        
        if start_price is None or end_price is None:
            return None
        
        if start_price <= 0:
            return None
        
        return (end_price - start_price) / start_price
    
    def _get_sector_net_action(
        self,
        products: List[str],
        sw1_code: str,
        industry_weight_records: List[Dict],
        date: str,
        window: int = 20
    ) -> float:
        """Calculate net action from precomputed 30-day industry weight changes.

        IndustryWeightCalculator already emits weight_change_30d using the
        correct trading baseline. Missing product-sector changes are skipped
        instead of treated as zero, because zero would falsely convert an
        unknown baseline into a hold/add signal.
        
        Returns:
            Net weight change (sum of individual product changes)
        """
        if not products or not sw1_code:
            return 0.0

        weight_change_lookup = self._build_weight_change_30d_lookup(industry_weight_records, date)
        net_action = 0.0
        for product in products:
            weight_change = weight_change_lookup.get((product, sw1_code))
            if weight_change is None:
                continue
            net_action += weight_change

        return net_action
    
    def _count_sector_adds(
        self,
        products: List[str],
        sw1_code: str,
        industry_weight_records: List[Dict],
        date: str,
        window: int = 20
    ) -> int:
        """Count products with positive precomputed 30-day sector changes.

        Products without weight_change_30d are skipped so missing baseline data
        cannot be interpreted as a new position or add.
        
        Returns:
            Count of products with positive weight change
        """
        if not products or not sw1_code:
            return 0

        weight_change_lookup = self._build_weight_change_30d_lookup(industry_weight_records, date)
        add_count = 0
        for product in products:
            weight_change = weight_change_lookup.get((product, sw1_code))
            if weight_change is not None and weight_change > 0:
                add_count += 1

        return add_count

    def _build_weight_change_30d_lookup(
        self,
        industry_weight_records: List[Dict],
        date: str,
    ) -> Dict[tuple, float]:
        """Build (product_code, sw1_code) -> weight_change_30d for one date."""
        lookup = {}
        for record in industry_weight_records or []:
            if record.get('date') != date:
                continue
            product_code = record.get('product_code')
            sw1_code = record.get('sw1_code')
            weight_change = record.get('weight_change_30d')
            if not product_code or not sw1_code or weight_change is None:
                continue
            lookup[(product_code, sw1_code)] = float(weight_change)
        return lookup
    
    def detect_darwin_moment(self, positions: List[Dict], all_products_positions: List[List[Dict]]) -> bool:
        """Backward-compatible stub for old Darwin detection API.
        
        Real Darwin detection happens in Phase 4B via detect_for_date().
        This stub returns False to defer detection to Phase 4B.
        """
        return False
