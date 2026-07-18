"""Unit tests for ``CacheManager`` (Phase 1B-B).

Covers SPEC-03-009 §3.3 (CM-101..CM-109) and DESIGN-03-009 §5.2 (10
UT). All tests use :mod:`mongomock` to avoid real MongoDB I/O.

Test inventory (10 UT):

* UT-CM-001  get hit + not expired         → returns DataResult
* UT-CM-002  get hit + expired             → returns None
* UT-CM-003  get miss                      → returns None
* UT-CM-004  find_one raises               → returns None (no raise)
* UT-CM-005  put then get round-trip
* UT-CM-006  put idempotent on ``cache_key``
* UT-CM-007  invalidate clears all cached docs
* UT-CM-008  invalidate(security_id=...) filters by security
* UT-CM-009  cache_key is deterministic across two put() calls
* UT-CM-010  cache_key is order-independent w.r.t. ``params`` dict
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import mongomock
import pytest

from skills.data.unified_data import (
    DataResult,
    Market,
    SecurityId,
)
from skills.data.unified_data.cache_manager import (
    CacheManager,
    _DEFAULT_COLLECTION_PREFIX,
)


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
def manager(db: Any) -> CacheManager:
    return CacheManager(mongo_db=db)


# ---------------------------------------------------------------------------
# UT-CM-001..004: get
# ---------------------------------------------------------------------------


class TestCacheManagerGet:
    def test_get_hit_not_expired(self, manager, db, cn_maotai):
        sid = cn_maotai
        original = _make_result(sid, "market_data", "kline_daily")
        manager.put(sid, "market_data", "kline_daily", {"x": 1}, original)
        coll = db[_DEFAULT_COLLECTION_PREFIX + "kline_daily"]
        coll.update_one(
            {"security_id": str(sid)},
            {"$set": {"expires_at": datetime.utcnow() + timedelta(hours=1)}},
        )
        result = manager.get(sid, "market_data", "kline_daily", {"x": 1})
        assert result is not None
        assert result.provider == "tushare"
        assert result.freshness == "cached"
        assert result.data == {"close": [100, 101]}

    def test_get_expired(self, manager, db, cn_maotai):
        sid = cn_maotai
        manager.put(
            sid,
            "market_data",
            "kline_daily",
            {"x": 1},
            _make_result(sid, "market_data", "kline_daily"),
        )
        coll = db[_DEFAULT_COLLECTION_PREFIX + "kline_daily"]
        long_ago = datetime.utcnow() - timedelta(hours=24)
        coll.update_one(
            {"security_id": str(sid)},
            {
                "$set": {
                    "expires_at": long_ago,
                    "cached_at": long_ago,
                }
            },
        )
        result = manager.get(sid, "market_data", "kline_daily", {"x": 1})
        assert result is None

    def test_get_miss(self, manager, cn_maotai):
        result = manager.get(cn_maotai, "market_data", "kline_daily", {})
        assert result is None

    def test_get_exception_returns_none(self, manager, cn_maotai, monkeypatch):
        def boom(*_args, **_kwargs):
            raise RuntimeError("simulated")

        monkeypatch.setattr(
            "mongomock.collection.Collection.find_one", boom
        )
        result = manager.get(cn_maotai, "market_data", "kline_daily", {})
        assert result is None


# ---------------------------------------------------------------------------
# UT-CM-005..006: put + idempotence
# ---------------------------------------------------------------------------


class TestCacheManagerPut:
    def test_put_then_get(self, manager, cn_maotai):
        sid = cn_maotai
        result = _make_result(sid, "market_data", "kline_daily")
        manager.put(sid, "market_data", "kline_daily", {"x": 1}, result)
        fetched = manager.get(sid, "market_data", "kline_daily", {"x": 1})
        assert fetched is not None
        assert fetched.data == {"close": [100, 101]}

    def test_put_idempotent(self, manager, db, cn_maotai):
        sid = cn_maotai
        manager.put(
            sid,
            "market_data",
            "kline_daily",
            {"x": 1},
            _make_result(sid, "market_data", "kline_daily", data={"v": 1}),
        )
        manager.put(
            sid,
            "market_data",
            "kline_daily",
            {"x": 1},
            _make_result(sid, "market_data", "kline_daily", data={"v": 2}),
        )
        coll = db[_DEFAULT_COLLECTION_PREFIX + "kline_daily"]
        assert coll.count_documents({"security_id": str(sid)}) == 1
        fetched = manager.get(sid, "market_data", "kline_daily", {"x": 1})
        assert fetched.data == {"v": 2}


# ---------------------------------------------------------------------------
# UT-CM-007..008: invalidate
# ---------------------------------------------------------------------------


class TestCacheManagerInvalidate:
    def test_invalidate_all(self, manager, db, cn_maotai):
        sid = cn_maotai
        manager.put(
            sid, "market_data", "kline_daily", {"x": 1},
            _make_result(sid, "market_data", "kline_daily"),
        )
        manager.put(
            sid, "market_data", "realtime_quote", {"x": 1},
            _make_result(sid, "market_data", "realtime_quote"),
        )
        manager.put(
            sid, "financial", "income_statement", {"x": 1},
            _make_result(sid, "financial", "income_statement"),
        )
        deleted = manager.invalidate()
        assert deleted == 3
        for op in ("kline_daily", "realtime_quote", "income_statement"):
            coll = db[_DEFAULT_COLLECTION_PREFIX + op]
            assert coll.count_documents({}) == 0

    def test_invalidate_by_security_id(self, manager, cn_maotai, cn_pingan):
        for sid in (cn_maotai, cn_pingan):
            manager.put(
                sid, "market_data", "kline_daily", {"x": 1},
                _make_result(sid, "market_data", "kline_daily"),
            )
        deleted = manager.invalidate(security_id=cn_maotai)
        assert deleted == 1
        # cn_pingan survives.
        assert manager.get(cn_pingan, "market_data", "kline_daily", {"x": 1}) is not None


# ---------------------------------------------------------------------------
# UT-CM-009..010: cache-key determinism + order independence
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_cache_key_deterministic(self, manager, cn_maotai):
        sid = cn_maotai
        first = manager._make_cache_key(sid, "market_data", "kline_daily", {"x": 1})
        second = manager._make_cache_key(sid, "market_data", "kline_daily", {"x": 1})
        assert first == second

    def test_cache_key_params_order_independent(self, cn_maotai):
        sid = cn_maotai
        a = CacheManager._make_cache_key(sid, "market_data", "kline_daily", {"a": 1, "b": 2})
        b = CacheManager._make_cache_key(sid, "market_data", "kline_daily", {"b": 2, "a": 1})
        assert a == b

    def test_collection_prefix_locked(self, db):
        manager = CacheManager(
            mongo_db=db, collection_prefix="not_03_data_ud_cache_"
        )
        assert manager._prefix == _DEFAULT_COLLECTION_PREFIX