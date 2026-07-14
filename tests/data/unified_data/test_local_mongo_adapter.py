"""Unit tests for ``LocalMongoAdapter`` (Phase 1B-B).

Covers SPEC-03-009 §3.2 (LM-101..LM-110) and DESIGN-03-009 §5.2 (12
UT). All tests use :mod:`mongomock` to avoid real MongoDB I/O.

Test inventory (12 UT):

* UT-LM-001  hit + not expired          → returns DataResult
* UT-LM-002  hit + expired               → returns None
* UT-LM-003  miss                        → returns None
* UT-LM-004  underlying ``find_one`` raises → returns None (no raise)
* UT-LM-005  ``put`` then ``get`` round-trip
* UT-LM-006  ``put`` idempotent on ``materialized_key``
* UT-LM-007  ``invalidate`` clears all materialised docs
* UT-LM-008  ``invalidate(security_id=...)`` filters by security
* UT-LM-009  ``invalidate(domain=...)`` filters by domain
* UT-LM-010  ``expires_at == materialized_at + TTL``
* UT-LM-011  ``collection_prefix`` is locked at the module level
* UT-LM-012  writes only touch the ``03_data_ud_`` collection namespace
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import mongomock
import pytest

from skills.data.unified_data import (
    DataResult,
    FreshnessPolicy,
    Market,
    SecurityId,
)
from skills.data.unified_data.local_mongo_adapter import (
    LocalMongoAdapter,
    _DEFAULT_COLLECTION_PREFIX,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> Any:
    return mongomock.MongoClient().get_database("tradingagents")


def _make_result(
    security_id: SecurityId,
    domain: str,
    operation: str,
    *,
    provider: str = "tushare",
    data: Any = None,
) -> DataResult:
    return DataResult(
        data=data if data is not None else {"close": [100, 101]},
        security_id=security_id,
        domain=domain,
        operation=operation,
        provider=provider,
        fetched_at=datetime.utcnow(),
        source_trace=[f"{provider}(ok)"],
        freshness="delayed",
    )


@pytest.fixture
def db() -> Any:
    return _make_db()


@pytest.fixture
def adapter(db: Any) -> LocalMongoAdapter:
    return LocalMongoAdapter(mongo_db=db)


@pytest.fixture
def fresh_policy() -> FreshnessPolicy:
    """Tiny TTL so test docs expire quickly when needed."""
    return FreshnessPolicy(ttl_overrides={"market_data": 60})


# ---------------------------------------------------------------------------
# UT-LM-001: get — hit + not expired
# ---------------------------------------------------------------------------


class TestLocalMongoAdapterGet:
    # UT-LM-001: get — hit + not expired
    def test_get_hit_not_expired(self, adapter, db, cn_maotai):
        # Seed via put() so the canonical key shape is used.
        sid = cn_maotai
        coll = db[_DEFAULT_COLLECTION_PREFIX + "kline_daily"]
        # Manually craft a doc with a far-future expires_at so it stays
        # in-window for the assertion. We use ``put`` to compute the
        # key, then override the doc's ``expires_at`` via update_one.
        original = _make_result(
            sid, "market_data", "kline_daily", data={"close": [100, 101]}
        )
        adapter.put(sid, "market_data", "kline_daily", {"x": 1}, original)
        coll.update_one(
            {"security_id": str(sid)},
            {"$set": {"expires_at": datetime.utcnow() + timedelta(hours=1)}},
        )
        result = adapter.get(
            sid,
            "market_data",
            "kline_daily",
            {"x": 1},
        )
        assert result is not None
        assert result.provider == "ud_materialized"
        assert result.freshness == "cached"
        assert result.data == {"close": [100, 101]}

    # UT-LM-002: hit but expired
    def test_get_hit_but_expired(self, adapter, db, cn_maotai):
        sid = cn_maotai
        coll = db[_DEFAULT_COLLECTION_PREFIX + "kline_daily"]
        long_ago = datetime.utcnow() - timedelta(hours=24)
        coll.insert_one(
            {
                "materialized_key": "old",
                "security_id": str(sid),
                "domain": "market_data",
                "operation": "kline_daily",
                "data": {"close": [1, 2]},
                "provider": "tushare",
                "fetched_at": long_ago,
                "materialized_at": long_ago,
                "expires_at": long_ago + timedelta(seconds=1),
            }
        )
        result = adapter.get(
            sid, "market_data", "kline_daily", {"start_date": "x"}
        )
        assert result is None

    # UT-LM-003: miss
    def test_get_miss(self, adapter, cn_maotai):
        result = adapter.get(
            cn_maotai, "market_data", "kline_daily", {"start_date": "x"}
        )
        assert result is None

    # UT-LM-004: find_one raises → None (no raise)
    def test_get_exception_returns_none(self, adapter, cn_maotai, monkeypatch):
        def boom(*_args, **_kwargs):
            raise RuntimeError("simulated mongomock failure")

        monkeypatch.setattr(
            "mongomock.collection.Collection.find_one", boom
        )
        # Should NOT raise; should log and return None.
        result = adapter.get(
            cn_maotai, "market_data", "kline_daily", {"x": 1}
        )
        assert result is None


# ---------------------------------------------------------------------------
# UT-LM-005..006: put + idempotence
# ---------------------------------------------------------------------------


class TestLocalMongoAdapterPut:
    def test_put_then_get(self, adapter, cn_maotai):
        sid = cn_maotai
        result = _make_result(sid, "market_data", "kline_daily")
        adapter.put(
            sid,
            "market_data",
            "kline_daily",
            {"start_date": "2026-07-01"},
            result,
        )
        fetched = adapter.get(
            sid,
            "market_data",
            "kline_daily",
            {"start_date": "2026-07-01"},
        )
        assert fetched is not None
        assert fetched.data == {"close": [100, 101]}

    def test_put_idempotent(self, adapter, db, cn_maotai):
        sid = cn_maotai
        first = _make_result(
            sid,
            "market_data",
            "kline_daily",
            data={"close": [1]},
        )
        adapter.put(sid, "market_data", "kline_daily", {"x": 1}, first)
        second = _make_result(
            sid,
            "market_data",
            "kline_daily",
            data={"close": [99]},
        )
        adapter.put(sid, "market_data", "kline_daily", {"x": 1}, second)
        coll = db[_DEFAULT_COLLECTION_PREFIX + "kline_daily"]
        # One doc only (upsert replaced the original).
        assert coll.count_documents({"security_id": str(sid)}) == 1
        fetched = adapter.get(
            sid, "market_data", "kline_daily", {"x": 1}
        )
        assert fetched.data == {"close": [99]}

    # UT-LM-010: expires_at = materialized_at + TTL
    def test_expires_at_calculated(self, adapter, db, cn_maotai, fresh_policy):
        # fresh_policy has market_data TTL = 60s
        adapter = LocalMongoAdapter(
            mongo_db=db, freshness=fresh_policy
        )
        sid = cn_maotai
        result = _make_result(sid, "market_data", "kline_daily")
        adapter.put(sid, "market_data", "kline_daily", {"x": 1}, result)
        coll = db[_DEFAULT_COLLECTION_PREFIX + "kline_daily"]
        doc = coll.find_one({"security_id": str(sid)})
        delta = doc["expires_at"] - doc["materialized_at"]
        assert int(delta.total_seconds()) == 60


# ---------------------------------------------------------------------------
# UT-LM-007..009: invalidate
# ---------------------------------------------------------------------------


class TestLocalMongoAdapterInvalidate:
    def test_invalidate_all(self, adapter, db, cn_maotai):
        sid = cn_maotai
        for op in ("kline_daily", "realtime_quote"):
            coll = db[_DEFAULT_COLLECTION_PREFIX + op]
            coll.insert_one(
                {
                    "materialized_key": f"k-{op}",
                    "security_id": str(sid),
                    "domain": "market_data",
                    "operation": op,
                    "data": {"x": 1},
                }
            )
        # Add a third collection with same key family for thoroughness.
        adapter.put(
            sid,
            "financial",
            "income_statement",
            {"x": 1},
            _make_result(sid, "financial", "income_statement"),
        )
        deleted = adapter.invalidate()
        assert deleted == 3
        # Everything is gone.
        for op in ("kline_daily", "realtime_quote"):
            assert (
                db[_DEFAULT_COLLECTION_PREFIX + op].count_documents({}) == 0
            )
        assert (
            db[_DEFAULT_COLLECTION_PREFIX + "income_statement"]
            .count_documents({})
            == 0
        )

    def test_invalidate_by_security_id(self, adapter, db, cn_maotai, cn_pingan):
        for sid in (cn_maotai, cn_pingan):
            adapter.put(
                sid,
                "market_data",
                "kline_daily",
                {"x": 1},
                _make_result(sid, "market_data", "kline_daily"),
            )
        deleted = adapter.invalidate(security_id=cn_maotai)
        # cn_maotai's doc deleted; cn_pingan still there.
        assert deleted == 1
        coll = db[_DEFAULT_COLLECTION_PREFIX + "kline_daily"]
        assert coll.count_documents({"security_id": str(cn_maotai)}) == 0
        assert coll.count_documents({"security_id": str(cn_pingan)}) == 1

    def test_invalidate_by_domain(self, adapter, db, cn_maotai):
        sid = cn_maotai
        adapter.put(
            sid, "market_data", "kline_daily", {"x": 1},
            _make_result(sid, "market_data", "kline_daily"),
        )
        adapter.put(
            sid, "financial", "income_statement", {"x": 1},
            _make_result(sid, "financial", "income_statement"),
        )
        deleted = adapter.invalidate(domain="market_data")
        assert deleted == 1
        md = db[_DEFAULT_COLLECTION_PREFIX + "kline_daily"]
        fi = db[_DEFAULT_COLLECTION_PREFIX + "income_statement"]
        assert md.count_documents({}) == 0
        assert fi.count_documents({}) == 1


# ---------------------------------------------------------------------------
# UT-LM-011..012: ownership invariants
# ---------------------------------------------------------------------------


class TestLocalMongoAdapterOwnership:
    def test_collection_prefix_locked(self, db):
        # Passing a different prefix is ignored — locked at module level.
        adapter = LocalMongoAdapter(
            mongo_db=db, collection_prefix="some_other_prefix_"
        )
        # Use the real locked prefix.
        assert adapter._prefix == _DEFAULT_COLLECTION_PREFIX

    def test_never_writes_to_non_prefixed(self, adapter, db, cn_maotai):
        # Seed a TA-CN-style (unprefixed) collection; make sure the
        # adapter never touches it during put/get/invalidate.
        ta_cn_coll = db["stock_daily_quotes"]  # no prefix
        ta_cn_coll.insert_one({"symbol": "600519", "close": 1})
        sid = cn_maotai
        result = _make_result(sid, "market_data", "kline_daily")
        adapter.put(sid, "market_data", "kline_daily", {"x": 1}, result)
        adapter.get(sid, "market_data", "kline_daily", {"x": 1})
        adapter.invalidate(security_id=sid)
        # The TA-CN collection remains untouched.
        assert ta_cn_coll.count_documents({}) == 1
        assert ta_cn_coll.find_one({})["symbol"] == "600519"
        assert ta_cn_coll.find_one({}).get("close") == 1


# ---------------------------------------------------------------------------
# FreshnessPolicy keyword tweak + pandas DataFrame serialization
# ---------------------------------------------------------------------------


class TestLocalMongoAdapterSerialization:
    def test_dataframe_payload_serialized(self, adapter, db, cn_maotai):
        # Avoid a hard pandas dependency — duck-type a DataFrame-like
        # object so we exercise the to_dict path.
        class FakeDataFrame:
            def to_dict(self, *, orient):
                assert orient == "records"
                return [{"close": 100}, {"close": 101}]

        sid = cn_maotai
        result = _make_result(
            sid, "market_data", "kline_daily", data=FakeDataFrame()
        )
        adapter.put(sid, "market_data", "kline_daily", {"x": 1}, result)
        coll = db[_DEFAULT_COLLECTION_PREFIX + "kline_daily"]
        doc = coll.find_one({"security_id": str(sid)})
        assert doc["data"] == [{"close": 100}, {"close": 101}]