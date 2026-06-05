# skills/research/argus/tests/test_argus_phase2_acceptance.py
"""Phase 2 acceptance tests for the Argus daily pipeline."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, '/home/pascal/.openclaw/workspace-yquant')

from skills.research.argus.cli.daily_processor import (
    _build_previous_signal_pool_map,
    _build_stock_pool_records,
    _merge_previous_signal_pool_records,
    _write_json_output,
    process_date,
)
from skills.research.argus.core import PoolManager


class FakeReader:
    def __init__(self, positions, trades, signal_pool=None):
        self.positions = positions
        self.trades = trades
        self.signal_pool = signal_pool or []

    def read(self, date, **kwargs):
        collection_name = kwargs.get('collection_name')
        if collection_name == 'portfolio_position':
            return [p for p in self.positions if p['position_date'] == date]
        if collection_name == 'portfolio_trade':
            return [t for t in self.trades if t['trade_date'] == date]
        if collection_name == '08_research_argus_signal_pool':
            return [p for p in self.signal_pool if p['date'] == date]
        return []


class FakeWriter:
    def __init__(self):
        self.credential_scores = []
        self.signals = []
        self.stock_pool = []
        self.industry_weights = []
        self.darwin_events = []
        self.consensus_direction = []
        self.indexes_ensured = False

    def ensure_argus_indexes(self):
        self.indexes_ensured = True

    def write_argus_credential_scores(self, data):
        self.credential_scores.extend(data)
        return len(data)

    def write_argus_signals(self, data):
        self.signals.extend(data)
        return len(data)

    def write_argus_stock_pool(self, data):
        self.stock_pool.extend(data)
        return len(data)

    def write_argus_signal_pool(self, data):
        return self.write_argus_stock_pool(data)

    def write_argus_industry_weights(self, data):
        self.industry_weights.extend(data)
        return len(data)

    def write_argus_darwin_events(self, data):
        self.darwin_events.extend(data)
        return len(data)

    def write_argus_consensus_direction(self, data):
        self.consensus_direction.extend(data)
        return len(data)


class FakeStockPoolIngestion:
    def __init__(self):
        self.calls = []

    def ingest_signals_incremental(self, current_signals, previous_signals, actor):
        self.calls.append(
            {
                'current_signals': current_signals,
                'previous_signals': previous_signals,
                'actor': actor,
            }
        )
        return {'entry': len(current_signals), 'previous': len(previous_signals)}


class FakeCollection:
    """Small in-memory collection with the find subset used by daily_processor."""

    def __init__(self, records):
        self.records = records

    def find(self, query, projection=None):
        """Return records matching date and wind_code predicates."""
        date_query = query.get('date', {})
        date_lt = date_query.get('$lt') if isinstance(date_query, dict) else None
        exact_date = date_query if isinstance(date_query, str) else None
        wind_codes = set(query.get('wind_code', {}).get('$in', []))
        matched = [
            record
            for record in self.records
            if (date_lt is None or record.get('date') < date_lt)
            and (exact_date is None or record.get('date') == exact_date)
            and (not wind_codes or record.get('wind_code') in wind_codes)
        ]
        if projection is None:
            return matched
        return [
            {
                key: value
                for key, value in record.items()
                if key != '_id' and projection.get(key, 1)
            }
            for record in matched
        ]


class FakeDB:
    """Map collection names to FakeCollection instances."""

    def __init__(self, records):
        self.collection = FakeCollection(records)

    def __getitem__(self, name):
        return self.collection


class TestArgusPhase2Acceptance(unittest.TestCase):
    def test_phase2_end_to_end_pipeline_writes_three_raw_tables(self):
        positions = [
            {'position_date': '2026-03-10', 'product_code': 'SM001', 'asset_wind_code': '600519.SH', 'asset_name': '贵州茅台', 'holding_ratio': 0.02, 'market_value': 200000},
            {'position_date': '2026-03-10', 'product_code': 'SM002', 'asset_wind_code': '600519.SH', 'asset_name': '贵州茅台', 'holding_ratio': 0.03, 'market_value': 300000},
            {'position_date': '2026-03-11', 'product_code': 'SM001', 'asset_wind_code': '600519.SH', 'asset_name': '贵州茅台', 'holding_ratio': 0.08, 'market_value': 800000},
            {'position_date': '2026-03-11', 'product_code': 'SM002', 'asset_wind_code': '600519.SH', 'asset_name': '贵州茅台', 'holding_ratio': 0.07, 'market_value': 700000},
            {'position_date': '2026-03-11', 'product_code': 'SM003', 'asset_wind_code': '000858.SZ', 'asset_name': '五粮液', 'holding_ratio': 0.04, 'market_value': 400000},
        ]
        trades = [
            {'trade_date': '2026-03-11', 'product_code': 'SM001', 'asset_wind_code': '600519.SH', 'asset_name': '贵州茅台', 'direction': 'BUY', 'amount': 600000},
        ]
        writer = FakeWriter()
        ingestion = FakeStockPoolIngestion()
        previous_signal_pool = [
            {'date': '2026-03-10', 'wind_code': '600519.SH', 'stock_name': '贵州茅台', 'pool_zone': 'SCAN'}
        ]

        with tempfile.TemporaryDirectory() as output_dir:
            results = process_date(
                '2026-03-11',
                reader=FakeReader(positions, trades, previous_signal_pool),
                writer=writer,
                output_dir=Path(output_dir),
                write_mongo=True,
                stock_pool_ingestion=ingestion,
            )
            payload = json.loads(Path(results['output_file']).read_text(encoding='utf-8'))

        self.assertTrue(writer.indexes_ensured)
        self.assertEqual(results['products_processed'], 3)
        self.assertEqual(results['signals_generated'], 3)
        self.assertEqual(results['credential_scores_written'], 3)
        self.assertEqual(results['signals_written'], 3)
        self.assertEqual(results['stock_pool_written'], 2)
        self.assertTrue(all(record['date'] == '2026-03-11' for record in writer.credential_scores))
        self.assertTrue(all(record['date'] == '2026-03-11' for record in writer.signals))
        self.assertTrue(all(record['date'] == '2026-03-11' for record in writer.stock_pool))
        self.assertTrue(all(0 <= record['bayesian_score'] <= 1 for record in writer.stock_pool))
        self.assertTrue(any(record['bayesian_score'] != record['confidence'] for record in writer.stock_pool))
        self.assertTrue(all('weight_change_30d' not in record for record in writer.stock_pool))
        self.assertTrue(all('crowding_level' in signal['metadata'] for signal in writer.signals))
        self.assertTrue(all('rebalancing_event_type' in signal for signal in writer.signals))
        self.assertTrue(all('direction_score' in signal for signal in writer.signals))
        self.assertEqual(ingestion.calls[0]['actor'], 'system:argus')
        self.assertEqual(ingestion.calls[0]['previous_signals'], previous_signal_pool)
        self.assertEqual(results['portfolio_stock_pool_sync']['entry'], 2)
        self.assertEqual(payload['date'], '2026-03-11')
        self.assertIn('crowding', payload)
        self.assertIn('stock_pool', payload)

    def test_phase2_pipeline_handles_1000_products_in_memory(self):
        positions = [
            {
                'position_date': '2026-03-11',
                'product_code': f'SM{i:04d}',
                'asset_wind_code': f'{600000 + (i % 50):06d}.SH',
                'asset_name': f'Stock{i % 50}',
                'holding_ratio': 0.02 + (i % 5) * 0.005,
                'market_value': 100000 + i,
            }
            for i in range(1000)
        ]
        writer = FakeWriter()

        with tempfile.TemporaryDirectory() as output_dir:
            results = process_date(
                '2026-03-11',
                reader=FakeReader(positions, []),
                writer=writer,
                output_dir=Path(output_dir),
                write_mongo=True,
            )

        self.assertEqual(results['products_processed'], 1000)
        self.assertEqual(results['signals_generated'], 1000)
        self.assertEqual(results['credential_scores_written'], 1000)
        self.assertEqual(results['signals_written'], 1000)
        self.assertEqual(results['stock_pool_written'], 50)

    def test_previous_signal_pool_merge_keeps_exits_and_latest_stock_records(self):
        """Previous-date exits should survive while current stocks use latest per-stock records."""
        previous_date_records = [
            {'date': '2026-05-01', 'wind_code': '000001.SZ', 'pool_zone': 'WATCH'},
            {'date': '2026-05-01', 'wind_code': '600519.SH', 'pool_zone': 'SCAN'},
        ]
        per_stock_latest = [
            {'date': '2026-04-29', 'wind_code': '600519.SH', 'pool_zone': 'CANDIDATE'},
        ]

        merged = _merge_previous_signal_pool_records(previous_date_records, per_stock_latest)
        by_code = {record['wind_code']: record for record in merged}

        self.assertEqual(set(by_code), {'000001.SZ', '600519.SH'})
        self.assertEqual(by_code['000001.SZ']['pool_zone'], 'WATCH')
        self.assertEqual(by_code['600519.SH']['date'], '2026-04-29')
        self.assertEqual(by_code['600519.SH']['pool_zone'], 'CANDIDATE')

    def test_build_previous_signal_pool_map_handles_holiday_gap(self):
        """A stock missing on previous_date should use its older latest record."""
        reader = FakeReader([], [])
        reader.db = FakeDB([
            {'date': '2026-04-28', 'wind_code': '600519.SH', 'pool_zone': 'SCAN'},
            {'date': '2026-04-30', 'wind_code': '600519.SH', 'pool_zone': 'WATCH'},
            {'date': '2026-05-05', 'wind_code': '000001.SZ', 'pool_zone': 'WATCH'},
        ])

        previous = _build_previous_signal_pool_map(
            reader,
            current_date='2026-05-06',
            fallback_previous_date='2026-05-05',
            current_signal_pool=[
                {'date': '2026-05-06', 'wind_code': '600519.SH', 'pool_zone': 'CANDIDATE'},
            ],
        )

        self.assertEqual(len(previous), 1)
        self.assertEqual(previous[0]['wind_code'], '600519.SH')
        self.assertEqual(previous[0]['date'], '2026-04-30')
        self.assertEqual(previous[0]['pool_zone'], 'WATCH')

    def test_json_output_includes_top_level_consensus_direction(self):
        consensus_direction = {'date': '2026-05-29', 'prosperity_signal': 'BULLISH'}

        with tempfile.TemporaryDirectory() as output_dir:
            output_file = _write_json_output(
                '2026-05-29',
                signals=[],
                consensus={},
                crowding={},
                stock_pool_records=[],
                results={},
                output_dir=Path(output_dir),
                consensus_direction=consensus_direction,
            )
            payload = json.loads(output_file.read_text(encoding='utf-8'))

        self.assertEqual(payload['consensus_direction'], consensus_direction)

    def test_stock_pool_classification_uses_same_day_sector_darwin_event(self):
        """A sector-level Darwin event should affect today's zone classification."""
        records = _build_stock_pool_records(
            date_to_process='2026-05-29',
            signals=[
                {
                    'product_code': 'SM001',
                    'confidence': 0.2,
                    'target_stocks': [{'wind_code': '600519.SH', 'stock_name': '贵州茅台'}],
                    'metadata': {'darwin_moment': False},
                }
            ],
            consensus={},
            crowding={},
            pool_manager=PoolManager(),
            wind_to_sw1={'600519.SH': '801120.SI'},
            darwin_events=[
                {
                    'date': '2026-05-29',
                    'sw1_code': '801120.SI',
                    'confidence': 0.8,
                }
            ],
        )

        self.assertEqual(records[0]['pool_zone'], 'CANDIDATE')
        self.assertTrue(records[0]['darwin_moment'])
        self.assertEqual(records[0]['darwin_event_id'], '2026-05-29_801120.SI')


if __name__ == '__main__':
    unittest.main()
