# skills/research/argus/core/industry_weight_calculator.py
"""Industry weight aggregation for Argus portfolio positions."""

from collections import defaultdict
from datetime import datetime
import logging
from typing import Dict, Iterable, List, Optional, Tuple


UNKNOWN_SW1_CODE = 'UNKNOWN'
UNKNOWN_SW1_NAME = '未映射'

logger = logging.getLogger(__name__)


class IndustryWeightCalculator:
    """Aggregate product stock positions into SW level-1 industry weights."""

    CYCLICAL_SECTORS = ['801050.SI', '801040.SI', '801030.SI', '801890.SI', '801880.SI']
    DEFENSIVE_SECTORS = ['801120.SI', '801150.SI', '801160.SI', '801780.SI']

    @classmethod
    def calculate(
        cls,
        date: str,
        positions: List[Dict],
        sector_info: List[Dict],
        previous_weights: Optional[List[Dict]] = None,
        lookback_30d_weights: Optional[List[Dict]] = None,
        lookback_60d_weights: Optional[List[Dict]] = None,
        previous_positions: Optional[List[Dict]] = None,
        baseline_30d_positions: Optional[List[Dict]] = None,
        baseline_60d_positions: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """Calculate industry weights and 1d/30d/60d changes.

        holding_ratio is stored as NAV ratio, so industry weight is the direct
        sum of position ratios multiplied by 100. Baselines are expected to be
        previously persisted industry-weight records; position baseline kwargs
        are accepted only for backward-compatible tests and local callers.
        """
        sector_lookup = cls._build_sector_lookup(sector_info)
        current, unmapped_count = cls._aggregate(positions, sector_lookup)
        if unmapped_count:
            logger.warning("[IndustryWeightCalculator] %s unmapped positions on %s", unmapped_count, date)

        baseline_1d = (
            cls._weights_lookup(previous_weights)
            if previous_weights is not None
            else cls._aggregate(previous_positions or [], sector_lookup)[0]
        )
        baseline_30d = (
            cls._weights_lookup(lookback_30d_weights)
            if lookback_30d_weights is not None
            else cls._aggregate(baseline_30d_positions or [], sector_lookup)[0]
        )
        baseline_60d = (
            cls._weights_lookup(lookback_60d_weights)
            if lookback_60d_weights is not None
            else cls._aggregate(baseline_60d_positions or [], sector_lookup)[0]
        )

        keys = set(current) | set(baseline_1d) | set(baseline_30d) | set(baseline_60d)

        records = []
        for product_code, sw1_code in sorted(keys):
            key = (product_code, sw1_code)
            current_item = current.get(key, {})
            weight_pct = current_item.get('weight_pct', 0.0)
            baseline_1d_weight = baseline_1d.get(key, {}).get('weight_pct', 0.0)
            baseline_30d_weight = baseline_30d.get(key, {}).get('weight_pct', 0.0)
            baseline_60d_weight = baseline_60d.get(key, {}).get('weight_pct', 0.0)
            has_1d_baseline = key in baseline_1d
            has_30d_baseline = key in baseline_30d and sw1_code != UNKNOWN_SW1_CODE
            has_60d_baseline = key in baseline_60d and sw1_code != UNKNOWN_SW1_CODE
            product_name = (
                current_item.get('product_name')
                or baseline_1d.get(key, {}).get('product_name')
                or baseline_30d.get(key, {}).get('product_name')
                or baseline_60d.get(key, {}).get('product_name')
                or ''
            )

            records.append({
                'date': date,
                'product_code': product_code,
                'product_name': product_name,
                'sw1_code': sw1_code,
                'sw1_name': (
                    current_item.get('sw1_name')
                    or baseline_1d.get(key, {}).get('sw1_name')
                    or baseline_30d.get(key, {}).get('sw1_name')
                    or baseline_60d.get(key, {}).get('sw1_name')
                    or UNKNOWN_SW1_NAME
                ),
                'weight_pct': round(weight_pct, 4),
                'weight_change_1d': round(weight_pct - baseline_1d_weight, 4) if has_1d_baseline else None,
                'weight_change_30d': round(weight_pct - baseline_30d_weight, 4) if has_30d_baseline else None,
                'weight_change_60d': round(weight_pct - baseline_60d_weight, 4) if has_60d_baseline else None,
                'positions_count': current_item.get('positions_count', 0),
                'has_1d_baseline': has_1d_baseline,
                'has_30d_baseline': has_30d_baseline,
                'has_60d_baseline': has_60d_baseline,
                'source': 'portfolio_position',
                'created_at': datetime.now().isoformat(),
            })
        return records

    @classmethod
    def _aggregate(cls, positions: Iterable[Dict], sector_lookup: Dict[str, Tuple[str, str]]) -> Tuple[Dict[Tuple[str, str], Dict], int]:
        grouped: Dict[Tuple[str, str], Dict] = defaultdict(lambda: {
            'weight_pct': 0.0,
            'positions_count': 0,
            'sw1_name': UNKNOWN_SW1_NAME,
            'product_name': '',
        })
        unmapped_count = 0
        for position in positions:
            product_code = position.get('product_code')
            if not product_code:
                continue

            sw1_code, sw1_name = cls._resolve_sector(position, sector_lookup)
            if sw1_code == UNKNOWN_SW1_CODE:
                unmapped_count += 1
            item = grouped[(product_code, sw1_code)]
            # holding_ratio is already 股票持仓市值 / 产品净资产, so industry
            # exposure is the direct cross-stock sum in percentage points.
            item['weight_pct'] += float(position.get('holding_ratio') or 0) * 100
            item['positions_count'] += 1
            item['sw1_name'] = sw1_name
            item['product_name'] = position.get('product_name') or position.get('portfolio_name') or item['product_name']
        return dict(grouped), unmapped_count

    @staticmethod
    def _weights_lookup(records: Optional[Iterable[Dict]]) -> Dict[Tuple[str, str], Dict]:
        lookup = {}
        for record in records or []:
            product_code = record.get('product_code')
            sw1_code = record.get('sw1_code')
            if not product_code or not sw1_code:
                continue
            lookup[(product_code, sw1_code)] = {
                'weight_pct': float(record.get('weight_pct') or 0),
                'sw1_name': record.get('sw1_name') or UNKNOWN_SW1_NAME,
                'product_name': record.get('product_name') or '',
            }
        return lookup

    @classmethod
    def _resolve_sector(cls, position: Dict, sector_lookup: Dict[str, Tuple[str, str]]) -> Tuple[str, str]:
        wind_code = position.get('asset_wind_code') or position.get('wind_code') or position.get('full_symbol')
        if wind_code:
            sector = sector_lookup.get(wind_code) or sector_lookup.get(str(wind_code).split('.')[0])
            if sector:
                return sector
        return UNKNOWN_SW1_CODE, UNKNOWN_SW1_NAME

    @staticmethod
    def _build_sector_lookup(sector_info: Iterable[Dict]) -> Dict[str, Tuple[str, str]]:
        lookup = {}
        for item in sector_info or []:
            sw1_code = IndustryWeightCalculator._normalize_sw1_code(
                item.get('sw1_code') or item.get('l1_code') or item.get('sector_code')
            )
            sw1_name = item.get('sw1_name') or item.get('l1_name') or item.get('sector_name')
            if not sw1_code or not sw1_name:
                continue
            sector = (sw1_code, sw1_name)
            for key in (
                item.get('full_symbol'),
                item.get('asset_wind_code'),
                item.get('wind_code'),
                item.get('symbol'),
                item.get('code'),
            ):
                if key:
                    lookup[str(key)] = sector
                    lookup[str(key).split('.')[0]] = sector
        return lookup

    @staticmethod
    def _normalize_sw1_code(sw1_code: Optional[str]) -> Optional[str]:
        if not sw1_code:
            return None
        sw1_code = str(sw1_code)
        return f'{sw1_code}.SI' if sw1_code.isdigit() and len(sw1_code) == 6 else sw1_code