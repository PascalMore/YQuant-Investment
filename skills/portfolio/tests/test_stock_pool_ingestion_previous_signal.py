"""Unit tests for stock pool ingestion previous-signal handling.

Validates fixes for holiday-gap scenarios in the stock_pool audit pipeline:

1. _zone_delta_action handles previous_zone=None (KeyError fix)
2. _build_previous_signal_pool_map correctly finds each stock's last existing date
   in signal_pool rather than using the naive "previous calendar trading day".
3. daily_processor and backfill_audit produce consistent audit actions for the
   same signal_pool data across holiday gaps.
"""

import unittest
from datetime import datetime
from typing import Any, Dict, List

from bson import ObjectId

from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService
from skills.portfolio.stock_pool.repository import StockPoolRepository
from skills.portfolio.stock_pool.service import StockPoolService


# ---------------------------------------------------------------------------
# Fake MongoDB components
# ---------------------------------------------------------------------------


class InsertOneResult:
    def __init__(self, inserted_id: ObjectId) -> None:
        self.inserted_id = inserted_id


class UpdateResult:
    def __init__(self, modified_count: int) -> None:
        self.modified_count = modified_count


def _dotted_get(doc: Dict[str, Any], path: str) -> Any:
    """Navigate a dotted path in a dict, returning None if any segment is absent."""
    val = doc
    for part in path.split("."):
        if not isinstance(val, dict):
            return None
        val = val.get(part)
        if val is None:
            return None
    return val


class FakeCursor:
    """In-memory cursor that mimics pymongo's cursor API.

    Supports chained: sort(field, -1|1), limit(n), skip(n)
    Sort handles dotted paths; missing fields sort last (stable sort).
    """

    def __init__(self, docs: List[Dict[str, Any]]) -> None:
        self.docs = docs

    def sort(self, field: str, direction: int = 1) -> "FakeCursor":
        def key(doc: Dict[str, Any]) -> tuple:
            val = _dotted_get(doc, field)
            if val is None:
                return (1,)  # missing sorts last
            if isinstance(val, (int, float)):
                return (0, -val) if direction < 0 else (0, val)
            return (0, str(val))

        self.docs = sorted(self.docs, key=key)
        return self

    def limit(self, n: int) -> "FakeCursor":
        self.docs = self.docs[:n]
        return self

    def skip(self, n: int) -> "FakeCursor":
        self.docs = self.docs[n:]
        return self

    def __iter__(self) -> Any:
        return iter(self.docs)


class FakeCollection:
    """In-memory MongoDB collection stub for unit tests.

    Implements the subset of the pymongo API actually used:
    - insert_one, find_one, find(query?, projection?), update_one($set),
      delete_many, distinct(field, query?), create_index
    - find() returns FakeCursor (chained sort/limit/skip)
    """

    def __init__(self) -> None:
        self.docs: Dict[ObjectId, Dict[str, Any]] = {}
        self.indexes: List[Any] = []

    def create_index(self, keys: Any, name: str) -> None:
        self.indexes.append((keys, name))

    def insert_one(self, document: Dict[str, Any]) -> InsertOneResult:
        oid = ObjectId()
        stored = dict(document)
        stored["_id"] = oid
        self.docs[oid] = stored
        return InsertOneResult(oid)

    def find_one(self, query: Dict[str, Any]) -> Dict[str, Any] | None:
        if "_id" in query:
            doc = self.docs.get(query["_id"])
            return dict(doc) if doc else None
        for doc in self.docs.values():
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(
        self,
        query: Dict[str, Any] | None = None,
        projection: Dict[str, Any] | None = None,
    ) -> FakeCursor:
        if query is None:
            query = {}
        docs = [dict(d) for d in self.docs.values() if self._matches(d, query)]
        if projection is not None:
            excluded = {k for k, v in projection.items() if v == 0}
            has_inclusion = any(v == 1 for v in projection.values())
            pruned = []
            for doc in docs:
                pdoc = {k: v for k, v in doc.items() if k not in excluded}
                if has_inclusion:
                    pdoc = {k: v for k, v in pdoc.items() if k in projection or k == "_id"}
                pruned.append(pdoc)
            docs = pruned
        return FakeCursor(docs)

    def _matches(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        for key, value in query.items():
            if key == "_id":
                if isinstance(value, dict) and "$lt" in value:
                    if not doc["_id"] < value["$lt"]:
                        return False
                elif doc["_id"] != value:
                    return False
            elif isinstance(value, dict):
                if "$in" in value and doc.get(key) not in value["$in"]:
                    return False
                elif key == "date":
                    ds = str(doc.get("date") or "")
                    if "$lt" in value and not ds < value["$lt"]:
                        return False
                    if "$lte" in value and not ds <= value["$lte"]:
                        return False
                    if "$gte" in value and not ds >= value["$gte"]:
                        return False
                    if "$gt" in value and not ds > value["$gt"]:
                        return False
            elif doc.get(key) != value:
                return False
        return True

    def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> UpdateResult:
        for d in self.docs.values():
            if self._matches(d, query):
                for k, v in update.get("$set", {}).items():
                    target = d
                    for part in k.split(".")[:-1]:
                        target = target.setdefault(part, {})
                    target[k.split(".")[-1]] = v
                return UpdateResult(1)
        return UpdateResult(0)

    def delete_many(self, query: Dict[str, Any]) -> None:
        to_del = [k for k, v in self.docs.items() if self._matches(v, query)]
        for k in to_del:
            del self.docs[k]

    def distinct(self, field: str, query: Dict[str, Any] | None = None) -> List[Any]:
        results: set = set()
        for doc in self.docs.values():
            if query and not self._matches(doc, query):
                continue
            v = doc.get(field)
            if v is not None:
                results.add(v)
        return list(results)


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: Dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]


class FakeClient:
    def __init__(self) -> None:
        self.databases: Dict[str, FakeDatabase] = {}

    def __getitem__(self, name: str) -> FakeDatabase:
        self.databases.setdefault(name, FakeDatabase())
        return self.databases[name]


# ---------------------------------------------------------------------------
# Test data – a holiday-gap scenario (五一假期 gap)
# ---------------------------------------------------------------------------
# 2026-04-30 (交易日): 0883.HK=WATCH, 0700.HK=WATCH
# [05-01~05-05: 假期gap，无signal_pool记录]
# 2026-05-06 (交易日): 0883.HK=CANDIDATE, 0700.HK=WATCH, 0999.HK=SCAN (new)

_HOLIDAY_GAP_SIGNALS: Dict[str, List[Dict[str, Any]]] = {
    "2026-04-30": [
        {
            "wind_code": "0883.HK", "stock_code": "0883", "stock_name": "中国海洋石油",
            "pool_zone": "WATCH", "bayesian_score": 0.65, "bayesian_factors": {},
            "confidence": 0.70, "consensus_confidence": 0.68, "consensus_direction": "BUY",
            "contributing_products": ["SM003"], "contributing_products_count": 1,
            "crowding_score": 0.50, "crowding_level": "MEDIUM", "darwin_moment": False,
        },
        {
            "wind_code": "0700.HK", "stock_code": "0700", "stock_name": "腾讯控股",
            "pool_zone": "WATCH", "bayesian_score": 0.72, "bayesian_factors": {},
            "confidence": 0.75, "consensus_confidence": 0.70, "consensus_direction": "BUY",
            "contributing_products": ["SM003", "SM004"], "contributing_products_count": 2,
            "crowding_score": 0.45, "crowding_level": "LOW", "darwin_moment": False,
        },
    ],
    "2026-05-06": [
        {
            "wind_code": "0883.HK", "stock_code": "0883", "stock_name": "中国海洋石油",
            "pool_zone": "CANDIDATE", "bayesian_score": 0.7067, "bayesian_factors": {},
            "confidence": 0.718, "consensus_confidence": 0.7005, "consensus_direction": "BUY",
            "contributing_products": ["SM003", "SM004", "SM012"], "contributing_products_count": 3,
            "crowding_score": 0.5518, "crowding_level": "MEDIUM", "darwin_moment": False,
        },
        {
            "wind_code": "0700.HK", "stock_code": "0700", "stock_name": "腾讯控股",
            "pool_zone": "WATCH", "bayesian_score": 0.71, "bayesian_factors": {},
            "confidence": 0.74, "consensus_confidence": 0.69, "consensus_direction": "BUY",
            "contributing_products": ["SM003"], "contributing_products_count": 1,
            "crowding_score": 0.46, "crowding_level": "LOW", "darwin_moment": False,
        },
        {
            "wind_code": "0999.HK", "stock_code": "0999", "stock_name": "邮储银行",
            "pool_zone": "SCAN", "bayesian_score": 0.55, "bayesian_factors": {},
            "confidence": 0.60, "consensus_confidence": 0.55, "consensus_direction": "BUY",
            "contributing_products": ["SM001"], "contributing_products_count": 1,
            "crowding_score": 0.30, "crowding_level": "LOW", "darwin_moment": False,
        },
    ],
}


def _seed_signal_pool(fc: FakeCollection, signals: Dict[str, List[Dict[str, Any]]]) -> None:
    """Seed signal_pool FakeCollection with holiday-gap test data."""
    for date_str, records in signals.items():
        for record in records:
            fc.insert_one({"date": date_str, **record})


def _stock_pool_insert(
    fc: FakeCollection,
    wind_code: str,
    pool_zone: str,
    source: str = "argus",
) -> None:
    """Insert an active stock_pool record so _active_record() finds it."""
    fc.insert_one({
        "stock_code": wind_code.split(".")[0],
        "wind_code": wind_code,
        "stock_name": "测试股票",
        "pool_zone": pool_zone,
        "source": source,
        "status": "active",
        "entry_date": datetime(2026, 4, 30),
        "entry_reason": {"bayesian_score": 0.65},
        "tags": [],
        "memo": "",
    })


def _audit_wind_code(r: Dict[str, Any]) -> str:
    """Extract wind_code from an audit record, checking 'after' first."""
    after = r.get("after")
    if after:
        return after.get("wind_code", "?")
    return r.get("wind_code", "?")


# ---------------------------------------------------------------------------
# Test 1: _zone_delta_action None / invalid previous_zone handling
# ---------------------------------------------------------------------------

class TestZoneDeltaActionNoneHandling(unittest.TestCase):
    """_zone_delta_action must handle None (holiday-gap case) without KeyError."""

    def setUp(self) -> None:
        self.repository = StockPoolRepository(client=FakeClient())
        self.svc = StockPoolService(self.repository)
        self.ingestion = StockPoolIngestionService(self.svc)

    def test_none_previous_zone_returns_update(self) -> None:
        self.assertEqual(self.ingestion._zone_delta_action(None, "CANDIDATE"), "update")

    def test_watch_to_candidate_returns_promote(self) -> None:
        self.assertEqual(self.ingestion._zone_delta_action("WATCH", "CANDIDATE"), "promote")

    def test_candidate_to_watch_returns_demote(self) -> None:
        self.assertEqual(self.ingestion._zone_delta_action("CANDIDATE", "WATCH"), "demote")

    def test_same_zone_returns_none(self) -> None:
        self.assertIsNone(self.ingestion._zone_delta_action("WATCH", "WATCH"))

    def test_invalid_previous_zone_returns_update(self) -> None:
        self.assertEqual(self.ingestion._zone_delta_action("UNKNOWN", "WATCH"), "update")

    def test_invalid_current_zone_reraises_keyerror(self) -> None:
        with self.assertRaises(KeyError):
            self.ingestion._zone_delta_action("WATCH", "NOTAZONE")


# ---------------------------------------------------------------------------
# Test 2: _build_previous_signal_pool_map holiday-gap handling
# ---------------------------------------------------------------------------

class TestBuildPreviousSignalPoolMap(unittest.TestCase):
    """_build_previous_signal_pool_map must find the last existing signal_pool date
    per stock, not just the previous calendar trading day (which may be a gap)."""

    def setUp(self) -> None:
        self.client = FakeClient()
        _seed_signal_pool(
            self.client["tradingagents"]["08_research_argus_signal_pool"],
            _HOLIDAY_GAP_SIGNALS,
        )

    def test_finds_date_before_holiday_gap(self) -> None:
        """For 0883.HK on 2026-05-06, must find 2026-04-30 (not 2026-05-05)."""
        from skills.research.argus.cli.daily_processor import _build_previous_signal_pool_map

        class FakeReader:
            db: FakeDatabase

            def __init__(self, c: FakeClient) -> None:
                self.db = c["tradingagents"]

        reader = FakeReader(self.client)
        current = _HOLIDAY_GAP_SIGNALS["2026-05-06"]

        result = _build_previous_signal_pool_map(
            reader=reader,
            current_date="2026-05-06",
            fallback_previous_date="2026-05-05",
            current_signal_pool=current,
        )

        # Only 0883.HK and 0700.HK have prior records; 0999.HK is new on 2026-05-06
        wind_codes = {r["wind_code"] for r in result}
        self.assertEqual(wind_codes, {"0883.HK", "0700.HK"})

        prev_0883 = next(r for r in result if r["wind_code"] == "0883.HK")
        self.assertEqual(prev_0883["pool_zone"], "WATCH")
        self.assertEqual(prev_0883["date"], "2026-04-30")

    def test_new_stock_not_in_previous(self) -> None:
        """0999.HK appears only on 2026-05-06, must NOT appear in previous pool."""
        from skills.research.argus.cli.daily_processor import _build_previous_signal_pool_map

        class FakeReader:
            db: FakeDatabase

            def __init__(self, c: FakeClient) -> None:
                self.db = c["tradingagents"]

        reader = FakeReader(self.client)
        current = _HOLIDAY_GAP_SIGNALS["2026-05-06"]

        result = _build_previous_signal_pool_map(
            reader=reader,
            current_date="2026-05-06",
            fallback_previous_date="2026-05-05",
            current_signal_pool=current,
        )

        wind_codes = {r["wind_code"] for r in result}
        self.assertNotIn("0999.HK", wind_codes)


# ---------------------------------------------------------------------------
# Test 3: ingest_signals_incremental holiday-gap with pre-seeded stock_pool
# ---------------------------------------------------------------------------

class TestIngestSignalsIncrementalHolidayGap(unittest.TestCase):
    """With stock_pool pre-seeded (so _active_record finds existing records),
    holiday-gap previous_signals must yield correct audit actions:
    - 0883.HK WATCH→CANDIDATE = promote
    - 0700.HK WATCH→WATCH = update or no_change
    - 0999.HK new = entry
    """

    def setUp(self) -> None:
        self.client = FakeClient()
        self.repository = StockPoolRepository(client=self.client)
        self.svc = StockPoolService(self.repository)
        self.ingestion = StockPoolIngestionService(self.svc)

        pool_coll = self.client["tradingagents"]["05_portfolio_stock_pool"]
        _stock_pool_insert(pool_coll, "0883.HK", "WATCH")
        _stock_pool_insert(pool_coll, "0700.HK", "WATCH")

    def test_watch_to_candidate_is_promote(self) -> None:
        previous = _HOLIDAY_GAP_SIGNALS["2026-04-30"]
        current = _HOLIDAY_GAP_SIGNALS["2026-05-06"]

        self.ingestion.ingest_signals_incremental(
            current_signals=current,
            previous_signals=previous,
            actor="test",
        )

        promote_audit = next(
            (a for a in self.repository.audit_collection.docs.values()
             if _audit_wind_code(a) == "0883.HK" and a.get("action") == "promote"),
            None,
        )
        all_actions = [
            (a.get("action"), _audit_wind_code(a))
            for a in self.repository.audit_collection.docs.values()
        ]
        self.assertIsNotNone(
            promote_audit,
            f"0883.HK promote not found. All (action, wind_code): {all_actions}",
        )

    def test_watch_to_watch_is_update_or_no_change(self) -> None:
        previous = _HOLIDAY_GAP_SIGNALS["2026-04-30"]
        current = _HOLIDAY_GAP_SIGNALS["2026-05-06"]

        self.ingestion.ingest_signals_incremental(
            current_signals=current,
            previous_signals=previous,
            actor="test",
        )

        actions = {
            a.get("action")
            for a in self.repository.audit_collection.docs.values()
            if _audit_wind_code(a) == "0700.HK"
        }
        self.assertTrue(
            actions & {"update", "no_change"},
            f"0700.HK expected update/no_change, got {actions}",
        )

    def test_new_stock_is_entry(self) -> None:
        previous = _HOLIDAY_GAP_SIGNALS["2026-04-30"]
        current = _HOLIDAY_GAP_SIGNALS["2026-05-06"]

        summary = self.ingestion.ingest_signals_incremental(
            current_signals=current,
            previous_signals=previous,
            actor="test",
        )

        self.assertEqual(summary["entry"], 1)
        entry_audit = next(
            (a for a in self.repository.audit_collection.docs.values()
             if _audit_wind_code(a) == "0999.HK" and a.get("action") == "entry"),
            None,
        )
        self.assertIsNotNone(entry_audit)


# ---------------------------------------------------------------------------
# Test 4: daily_processor vs backfill_audit consistency (real MongoDB)
# ---------------------------------------------------------------------------

class TestDailyProcessorVsBackfillAuditConsistency(unittest.TestCase):
    """Compare audit actions from the daily_processor path
    (_build_previous_signal_pool_map + ingest_signals_incremental) against
    backfill_audit (zip adjacent signal_pool dates) for the same holiday-gap
    data. Both must produce identical audit actions per stock.

    Uses a dedicated test database to avoid interfering with production data.
    """

    TEST_DB = "test_stock_pool_consistency_v4"

    @classmethod
    def setUpClass(cls) -> None:
        import pymongo

        cls.mongo_client = pymongo.MongoClient(
            "mongodb://myq:6812345@172.25.240.1:27017/"
        )
        cls.mongo_client.drop_database(cls.TEST_DB)
        cls.db = cls.mongo_client[cls.TEST_DB]

        coll = cls.db["08_research_argus_signal_pool"]
        for date_str, records in _HOLIDAY_GAP_SIGNALS.items():
            for record in records:
                coll.insert_one({"date": date_str, **record})

        pool_coll = cls.db["05_portfolio_stock_pool"]
        for wind_code, pool_zone in [("0883.HK", "WATCH"), ("0700.HK", "WATCH")]:
            pool_coll.insert_one({
                "stock_code": wind_code.split(".")[0],
                "wind_code": wind_code,
                "stock_name": "测试股票",
                "pool_zone": pool_zone,
                "source": "argus",
                "status": "active",
                "entry_date": datetime(2026, 4, 30),
                "entry_reason": {"bayesian_score": 0.65},
                "tags": [],
                "memo": "",
            })

    @classmethod
    def tearDownClass(cls) -> None:
        cls.mongo_client.drop_database(cls.TEST_DB)
        cls.mongo_client.close()

    def setUp(self) -> None:
        self.db["05_portfolio_stock_pool_audit"].delete_many({})

    def test_daily_processor_and_backfill_audit_produce_same_actions(self) -> None:
        """Both approaches must yield identical audit actions per stock."""
        from skills.portfolio.stock_pool.backfill_audit import backfill_audit
        from skills.portfolio.stock_pool.ingestion import StockPoolIngestionService
        from skills.portfolio.stock_pool.repository import StockPoolRepository
        from skills.portfolio.stock_pool.service import StockPoolService
        from skills.research.argus.cli.daily_processor import _build_previous_signal_pool_map

        target_date = "2026-05-06"

        # ---- Approach 1: backfill_audit (zip adjacent signal_pool dates) ----
        backfill_audit("2026-04-30", target_date, database=self.TEST_DB)
        backfill_records = list(self.db["05_portfolio_stock_pool_audit"].find())
        backfill_actions = {r["after"]["wind_code"]: r["action"] for r in backfill_records}

        # ---- Reset for approach 2 ----
        self.db["05_portfolio_stock_pool_audit"].delete_many({})

        # ---- Approach 2: daily_processor path (uses _build_previous_signal_pool_map) ----
        current_signals = list(
            self.db["08_research_argus_signal_pool"].find({"date": target_date})
        )

        prev_map = _build_previous_signal_pool_map(
            reader=self.db,  # type: ignore
            current_date=target_date,
            fallback_previous_date="2026-05-05",
            current_signal_pool=current_signals,
        )

        ingestion = StockPoolIngestionService(
            StockPoolService(StockPoolRepository(database=self.TEST_DB))
        )
        ingestion.ingest_signals_incremental(
            current_signals=current_signals,
            previous_signals=prev_map,
            actor="test",
        )

        daily_records = list(self.db["05_portfolio_stock_pool_audit"].find())
        daily_actions = {r["after"]["wind_code"]: r["action"] for r in daily_records}

        self.assertEqual(
            set(backfill_actions.keys()), set(daily_actions.keys()),
            f"Different stocks audited: backfill={set(backfill_actions)} vs daily={set(daily_actions)}",
        )
        for wind_code in backfill_actions:
            self.assertEqual(
                backfill_actions[wind_code], daily_actions[wind_code],
                f"{wind_code}: backfill={backfill_actions[wind_code]} vs daily={daily_actions[wind_code]}",
            )

    def test_0883HK_is_promote_not_update(self) -> None:
        """0883.HK (WATCH→CANDIDATE) must be 'promote', not 'update'."""
        from skills.portfolio.stock_pool.backfill_audit import backfill_audit

        backfill_audit("2026-04-30", "2026-05-06", database=self.TEST_DB)
        records = list(
            self.db["05_portfolio_stock_pool_audit"].find({"after.wind_code": "0883.HK"})
        )

        self.assertGreater(len(records), 0, "0883.HK must have audit records")
        promote_count = sum(1 for r in records if r["action"] == "promote")
        update_count = sum(1 for r in records if r["action"] == "update")
        self.assertEqual(
            promote_count, 1,
            f"0883.HK must have exactly 1 promote, got {promote_count} promote + {update_count} update",
        )


if __name__ == "__main__":
    unittest.main()