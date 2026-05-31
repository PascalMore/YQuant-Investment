"""Unit tests for stock_pool exit detection fix.

Tests that verify:
1. ingest_signals_incremental correctly detects exit when a stock leaves the pool
2. daily_processor passes the full previous pool (not filtered) to enable exit detection
3. Holiday gap scenario doesn't break exit detection
"""
import unittest
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any


class FakeCursor:
    def __init__(self, docs: List[Dict]):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, n):
        return self

    def skip(self, n):
        return self

    def __iter__(self):
        return iter(self._docs)

    def __len__(self):
        return len(self._docs)


class FakeCollection:
    def __init__(self, docs: List[Dict] | Dict | None = None):
        self._docs = docs if isinstance(docs, list) else (docs if docs is not None else [])

    def find(self, query: Dict, projection: Dict | None = None) -> FakeCursor:
        """Match docs against query (query is a dict with optional $in, $lt, $lte, $gte, $gt)."""
        results = []
        for doc in self._docs:
            if isinstance(doc, dict):
                match = True
                for key, val in query.items():
                    if key not in doc:
                        match = False
                        break
                    doc_val = doc[key]
                    if isinstance(val, dict):
                        # Handle operators
                        for op, op_val in val.items():
                            if op == '$in':
                                if doc_val not in op_val:
                                    match = False
                                    break
                            elif op == '$lt':
                                if not (doc_val < op_val):
                                    match = False
                                    break
                            elif op == '$lte':
                                if not (doc_val <= op_val):
                                    match = False
                                    break
                            elif op == '$gte':
                                if not (doc_val >= op_val):
                                    match = False
                                    break
                            elif op == '$gt':
                                if not (doc_val > op_val):
                                    match = False
                                    break
                            elif op == '$eq':
                                if doc_val != op_val:
                                    match = False
                                    break
                    else:
                        if doc_val != val:
                            match = False
                            break
                if match:
                    results.append(doc)
            else:
                match = False
        return FakeCursor(results)

    def insert_one(self, doc: Dict) -> MagicMock:
        self._docs.append(doc)
        m = MagicMock()
        m.inserted_id = doc.get('_id', 'fake_id')
        return m

    def update_one(self, query: Dict, update: Dict, upsert: bool = False) -> MagicMock:
        m = MagicMock()
        m.matched_count = 0
        m.modified_count = 0
        m.upserted_id = None
        for doc in self._docs:
            match = True
            for key, val in query.items():
                if doc.get(key) != val:
                    match = False
                    break
            if match:
                m.matched_count = 1
                if '$set' in update:
                    doc.update(update['$set'])
                    m.modified_count = 1
                elif '$setOnInsert' in update:
                    doc.update(update['$setOnInsert'])
                    m.modified_count = 1
                break
        if upsert and m.matched_count == 0:
            new_doc = dict(query)
            if '$set' in update:
                new_doc.update(update['$set'])
            elif '$setOnInsert' in update:
                new_doc.update(update['$setOnInsert'])
            self._docs.append(new_doc)
            m.upserted_id = new_doc.get('_id', 'fake_upsert_id')
            m.matched_count = 1
            m.modified_count = 1
        return m

    def delete_one(self, query: Dict) -> MagicMock:
        m = MagicMock()
        m.deleted_count = 0
        for i, doc in enumerate(self._docs):
            match = True
            for key, val in query.items():
                if doc.get(key) != val:
                    match = False
                    break
            if match:
                self._docs.pop(i)
                m.deleted_count = 1
                break
        return m

    def count_documents(self, query: Dict) -> int:
        return len(list(self.find(query)))


class FakeDB:
    def __init__(self):
        self._collections: Dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]

    def __setitem__(self, name: str, value) -> None:
        self._collections[name] = value

    def __getattr__(self, name: str) -> FakeCollection:
        return self[name]


class TestIngestSignalsExitDetection(unittest.TestCase):
    """Test that ingest_signals_incremental correctly detects exit actions."""

    def test_exit_detected_when_stock_leaves_pool(self):
        """Stock in previous but not in current → action=exit."""
        from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService
        from skills.portfolio.stock_pool.repository import StockPoolRepository
        from skills.portfolio.stock_pool.service import StockPoolService

        # Setup fake DB
        fake_db = FakeDB()
        fake_db['05_portfolio_stock_pool'] = FakeCollection([
            # Stock exists as active in stock_pool
            {'wind_code': '601918.SH', 'pool_zone': 'WATCH', 'status': 'active', 'product_code': 'TEST_PRODUCT'}
        ])
        fake_db['05_portfolio_stock_pool_audit'] = FakeCollection([])

        def fake_repo():
            r = StockPoolRepository(database='tradingagents')
            r.db = fake_db
            return r

        service = StockPoolService(repository=fake_repo())
        ingestion = StockPoolIngestionService(service)

        # Previous: stock was in signal_pool on 2026-01-05
        previous_signals = [
            {'date': '2026-01-05', 'wind_code': '601918.SH', 'pool_zone': 'WATCH',
             'product_code': 'TEST_PRODUCT', 'score': 0.5, 'confidence': 0.8}
        ]
        # Current: stock is NOT in signal_pool on 2026-01-06 (it left)
        current_signals: List[Dict] = []

        summary = ingestion.ingest_signals_incremental(
            current_signals=current_signals,
            previous_signals=previous_signals,
            actor='test',
        )

        self.assertEqual(summary.get('exit', 0), 1,
            f"Expected exit=1 but got {summary}. Audit records: {list(fake_db['05_portfolio_stock_pool_audit']._docs)}")

        # Verify exit audit record
        audit_records = list(fake_db['05_portfolio_stock_pool_audit'].find({}))
        exit_records = [r for r in audit_records if r.get('action') == 'exit']
        self.assertEqual(len(exit_records), 1)
        self.assertEqual(exit_records[0].get('after', {}).get('wind_code'), '601918.SH')

        # Verify stock_pool status updated to exit
        pool_records = list(fake_db['05_portfolio_stock_pool'].find({'wind_code': '601918.SH'}))
        self.assertEqual(len(pool_records), 1)
        self.assertEqual(pool_records[0].get('status'), 'exit')

    def test_no_exit_when_stock_stays(self):
        """Stock in both previous and current → no exit."""
        from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService
        from skills.portfolio.stock_pool.repository import StockPoolRepository
        from skills.portfolio.stock_pool.service import StockPoolService

        fake_db = FakeDB()
        fake_db['05_portfolio_stock_pool'] = FakeCollection([
            {'wind_code': '0700.HK', 'pool_zone': 'WATCH', 'status': 'active', 'product_code': 'TEST_PRODUCT'}
        ])
        fake_db['05_portfolio_stock_pool_audit'] = FakeCollection([])

        def fake_repo():
            r = StockPoolRepository(database='tradingagents')
            r.db = fake_db
            return r

        service = StockPoolService(repository=fake_repo())
        ingestion = StockPoolIngestionService(service)

        previous_signals = [
            {'date': '2026-01-05', 'wind_code': '0700.HK', 'pool_zone': 'WATCH',
             'product_code': 'TEST_PRODUCT', 'score': 0.5, 'confidence': 0.8}
        ]
        current_signals = [
            {'date': '2026-01-06', 'wind_code': '0700.HK', 'pool_zone': 'WATCH',
             'product_code': 'TEST_PRODUCT', 'score': 0.6, 'confidence': 0.85}
        ]

        summary = ingestion.ingest_signals_incremental(
            current_signals=current_signals,
            previous_signals=previous_signals,
            actor='test',
        )

        self.assertEqual(summary.get('exit', 0), 0)
        audit_records = list(fake_db['05_portfolio_stock_pool_audit'].find({}))
        exit_records = [r for r in audit_records if r.get('action') == 'exit']
        self.assertEqual(len(exit_records), 0)

    def test_exit_not_duplicated_if_already_exited(self):
        """Stock already exited should not produce another exit record."""
        from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService
        from skills.portfolio.stock_pool.repository import StockPoolRepository
        from skills.portfolio.stock_pool.service import StockPoolService

        fake_db = FakeDB()
        fake_db['05_portfolio_stock_pool'] = FakeCollection([
            {'wind_code': '601918.SH', 'pool_zone': 'WATCH', 'status': 'exit', 'product_code': 'TEST_PRODUCT'}
        ])
        fake_db['05_portfolio_stock_pool_audit'] = FakeCollection([])

        def fake_repo():
            r = StockPoolRepository(database='tradingagents')
            r.db = fake_db
            return r

        service = StockPoolService(repository=fake_repo())
        ingestion = StockPoolIngestionService(service)

        previous_signals = [
            {'date': '2026-01-05', 'wind_code': '601918.SH', 'pool_zone': 'WATCH',
             'product_code': 'TEST_PRODUCT', 'score': 0.5, 'confidence': 0.8}
        ]
        current_signals: List[Dict] = []

        summary = ingestion.ingest_signals_incremental(
            current_signals=current_signals,
            previous_signals=previous_signals,
            actor='test',
        )

        # Stock was already exited, should not produce another exit action
        self.assertEqual(summary.get('exit', 0), 0)


class TestBuildPreviousSignalPoolMapVsFullPool(unittest.TestCase):
    """Test that _build_previous_signal_pool_map was the source of the exit bug."""

    def test_build_previous_signal_pool_map_filters_out_leaving_stocks(self):
        """Demonstrate the bug: _build_previous_signal_pool_map only returns stocks in current."""
        from skills.research.argus.cli.daily_processor import _build_previous_signal_pool_map

        # Simulate: stock 601918.SH was in signal_pool on 2026-01-05 but NOT on 2026-01-06
        fake_db = FakeDB()
        fake_db['08_research_argus_signal_pool'] = FakeCollection([
            # Previous date (2026-01-05)
            {'date': '2026-01-05', 'wind_code': '601918.SH', 'pool_zone': 'WATCH', 'product_code': 'TEST_PRODUCT'},
            {'date': '2026-01-05', 'wind_code': '0700.HK', 'pool_zone': 'WATCH', 'product_code': 'TEST_PRODUCT'},
            # Current date (2026-01-06) - 601918.SH is GONE, only 0700.HK remains
            {'date': '2026-01-06', 'wind_code': '0700.HK', 'pool_zone': 'WATCH', 'product_code': 'TEST_PRODUCT'},
        ])

        class FakeReader:
            def __init__(self, db):
                self.db = db
            def read(self, date, collection_name):
                return list(self.db['08_research_argus_signal_pool'].find({'date': date}))

        reader = FakeReader(fake_db)

        # Current signals only have 0700.HK (601918.SH left)
        current_signal_pool = [
            {'date': '2026-01-06', 'wind_code': '0700.HK', 'pool_zone': 'WATCH', 'product_code': 'TEST_PRODUCT'}
        ]

        # _build_previous_signal_pool_map filters to only stocks in current_signal_pool
        result = _build_previous_signal_pool_map(
            reader, '2026-01-06', '2026-01-06', current_signal_pool
        )
        result_wind_codes = {r['wind_code'] for r in result}

        # 601918.SH is NOT in the result even though it WAS in previous date
        self.assertNotIn('601918.SH', result_wind_codes,
            "BUG: _build_previous_signal_pool_map filtered out 601918.SH (it left the pool)")
        # 0700.HK is in the result (it stayed)
        self.assertIn('0700.HK', result_wind_codes)

    def test_full_previous_pool_includes_leaving_stocks(self):
        """Using full previous pool (not filtered) includes stocks that left."""
        fake_db = FakeDB()
        fake_db['08_research_argus_signal_pool'] = FakeCollection([
            {'date': '2026-01-05', 'wind_code': '601918.SH', 'pool_zone': 'WATCH', 'product_code': 'TEST_PRODUCT'},
            {'date': '2026-01-05', 'wind_code': '0700.HK', 'pool_zone': 'WATCH', 'product_code': 'TEST_PRODUCT'},
            {'date': '2026-01-06', 'wind_code': '0700.HK', 'pool_zone': 'WATCH', 'product_code': 'TEST_PRODUCT'},
        ])

        class FakeReader:
            def __init__(self, db):
                self.db = db
            def read(self, date, collection_name):
                return list(self.db['08_research_argus_signal_pool'].find({'date': date}))

        reader = FakeReader(fake_db)

        # Full previous pool includes BOTH 0700.HK and 601918.SH
        full_previous = reader.read('2026-01-05', '08_research_argus_signal_pool')
        full_wind_codes = {r['wind_code'] for r in full_previous}

        self.assertIn('601918.SH', full_wind_codes,
            "Full pool correctly includes 601918.SH (leaving stock)")
        self.assertIn('0700.HK', full_wind_codes)


class TestDailyProcessorExitPath(unittest.TestCase):
    """Test that daily_processor passes full previous pool to enable exit detection."""

    def test_daily_processor_passes_full_previous_pool(self):
        """Verify process_date passes previous_signal_pool (full), not filtered version."""
        # This is tested by checking the actual code path:
        # The fix changed ingest_signals_incremental(previous_signals=previous_signal_pool)
        # where previous_signal_pool = reader.read(previous_date, ...)
        # This test documents the expected behavior

        # The previous buggy code was:
        #   previous_signal_pool_per_stock = _build_previous_signal_pool_map(...)
        #   ingest_signals_incremental(previous_signals=previous_signal_pool_per_stock, ...)
        #
        # The fix is:
        #   ingest_signals_incremental(previous_signals=previous_signal_pool, ...)
        #
        # This test just verifies the variable name used is the full pool
        import ast
        import inspect
        from skills.research.argus.cli import daily_processor

        source = inspect.getsource(daily_processor.process_date)
        tree = ast.parse(source)

        # Find the ingest_signals_incremental call
        found_ingest_call = False
        uses_full_pool = False
        uses_filtered_pool = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if hasattr(node.func, 'attr') and node.func.attr == 'ingest_signals_incremental':
                    found_ingest_call = True
                    for keyword in node.keywords:
                        if keyword.arg == 'previous_signals':
                            src = ast.unparse(keyword.value)
                            if 'previous_signal_pool_per_stock' in src:
                                uses_filtered_pool = True
                            elif 'previous_signal_pool' in src:
                                uses_full_pool = True

        self.assertTrue(found_ingest_call, "ingest_signals_incremental call not found in process_date")
        self.assertTrue(uses_full_pool, "Expected ingest_signals_incremental to use previous_signal_pool (full)")
        self.assertFalse(uses_filtered_pool, "Should NOT use previous_signal_pool_per_stock (filtered)")


class TestHolidayGapWithExit(unittest.TestCase):
    """Test exit detection works correctly even with holiday gap scenarios."""

    def test_exit_detection_with_holiday_gap(self):
        """Stock leaves pool after a holiday gap: exit should still be detected."""
        from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService
        from skills.portfolio.stock_pool.repository import StockPoolRepository
        from skills.portfolio.stock_pool.service import StockPoolService

        fake_db = FakeDB()
        fake_db['05_portfolio_stock_pool'] = FakeCollection([
            {'wind_code': '0883.HK', 'pool_zone': 'WATCH', 'status': 'active', 'product_code': 'TEST_PRODUCT'}
        ])
        fake_db['05_portfolio_stock_pool_audit'] = FakeCollection([])

        def fake_repo():
            r = StockPoolRepository(database='tradingagents')
            r.db = fake_db
            return r

        service = StockPoolService(repository=fake_repo())
        ingestion = StockPoolIngestionService(service)

        # Holiday gap scenario:
        # 2026-04-30: stock was in signal_pool (WATCH)
        # [May 1-5: holiday gap, no records]
        # 2026-05-06: stock NOT in signal_pool (left after holiday)
        previous_signals = [
            {'date': '2026-04-30', 'wind_code': '0883.HK', 'pool_zone': 'WATCH',
             'product_code': 'TEST_PRODUCT', 'score': 0.5, 'confidence': 0.8}
        ]
        current_signals: List[Dict] = []  # Stock left the pool

        summary = ingestion.ingest_signals_incremental(
            current_signals=current_signals,
            previous_signals=previous_signals,
            actor='test',
        )

        self.assertEqual(summary.get('exit', 0), 1,
            f"Expected exit=1 for stock leaving after holiday gap, got {summary}")
        audit_records = list(fake_db['05_portfolio_stock_pool_audit'].find({}))
        exit_records = [r for r in audit_records if r.get('action') == 'exit']
        self.assertEqual(len(exit_records), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)