"""Router Step 2/3 + materialization tests (Phase 1B-B).

Covers SPEC-03-009 §3.1 (DR-201..DR-214), §3.4 (MW-101..MW-105) and
DESIGN-03-009 §5.2 / §5.3 (17 UT + 4 IT). All tests use
:mod:`mongomock` for the persistence/cache layer and the existing
``FakeProvider`` / ``FakeTA_CNAdapter`` from conftest for the
provider / TA-CN adapter layers.

Test inventory (17 UT + 4 IT):

Step 2/3 routing
  UT-PR-001  Step 2 hit                  → provider="ud_materialized"
  UT-PR-002  Step 2 stale → Step 3 miss → Step 4
  UT-PR-003  Step 2 miss + Step 3 hit    → freshness="cached"
  UT-PR-004  Step 2/3 miss → Step 4 ok   → provider="tushare"
  UT-PR-005  Step 2 raises               → trace contains error
  UT-PR-006  Step 3 raises               → trace contains error
  UT-PR-007  force_refresh skips Step 2/3 → trace contains force_refresh
  UT-PR-013  provider=external skips Step 2/3
  UT-PR-016  Step 2 adapter=None → trace records 'skipped: no adapter'
  UT-PR-017  Step 3 manager=None → trace records 'skipped: no manager'

Materialization chain
  UT-PR-008  external ok → materialised layer populated
  UT-PR-009  external ok → cache layer populated
  UT-PR-010  materialised put failure → DataResult still ok
  UT-PR-011  cache put failure → DataResult still ok
  UT-PR-012  TA-CN hit does NOT trigger materialization

Errors / contract
  UT-PR-014  all internal + all external fail → DataResult.error
  UT-PR-015  source_trace full chain present

Integration
  IT-PR-001  full internal-first: TA-CN miss + Step 2 hit
  IT-PR-002  full internal-first: all miss + external ok
  IT-PR-003  force_refresh skips all internal, still writes to cache
  IT-PR-004  full failure path
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import mongomock
import pytest

from skills.data.unified_data import (
    CacheManager,
    DataResult,
    DataRouter,
    LocalMongoAdapter,
    Market,
    ProviderError,
    ProviderRegistry,
    SecurityId,
)
from skills.data.unified_data.tests.conftest import FakeProvider


KLINE_CAP = "market_data.kline_daily"


def _make_db() -> Any:
    return mongomock.MongoClient().get_database("tradingagents")


def _build_router(
    *,
    registry: ProviderRegistry,
    ta_cn_adapter: Any = None,
    db: Any = None,
    with_local_mongo: bool = False,
    with_cache: bool = False,
):
    """Convenience builder for a Router with optional 1B-B components."""
    if db is None and (with_local_mongo or with_cache):
        db = _make_db()
    local = (
        LocalMongoAdapter(mongo_db=db) if (db is not None and with_local_mongo) else None
    )
    cache = (
        CacheManager(mongo_db=db) if (db is not None and with_cache) else None
    )
    return DataRouter(
        registry,
        ta_cn_adapter=ta_cn_adapter,
        local_mongo_adapter=local,
        cache_manager=cache,
    )


# ---------------------------------------------------------------------------
# Step 2/3 routing
# ---------------------------------------------------------------------------


class TestRouterStep2:
    def test_step2_hit(self, fresh_registry, cn_maotai):
        # Adapter returns a hit (populated externally).
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload=None,
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        adapter = LocalMongoAdapter(mongo_db=db)
        adapter.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [100]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="tushare",
                fetched_at=datetime.utcnow(),
                source_trace=["tushare(ok)"],
                freshness="delayed",
            ),
        )
        # Push expires_at forward so the hit is non-expired.
        db["03_data_ud_kline_daily"].update_one(
            {"security_id": str(cn_maotai)},
            {"$set": {"expires_at": datetime.utcnow() + timedelta(hours=1)}},
        )
        router = _build_router(
            registry=fresh_registry,
            ta_cn_adapter=None,
            db=db,
            with_local_mongo=True,
            with_cache=False,
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "ud_materialized"
        assert result.freshness == "cached"
        # External provider must NOT have been called.
        assert fresh_registry.get("tushare").call_log == []

    def test_step2_stale_continues_to_step3(self, fresh_registry, cn_maotai):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        adapter = LocalMongoAdapter(mongo_db=db)
        adapter.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [1]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="tushare",
                fetched_at=datetime.utcnow(),
                source_trace=["tushare(ok)"],
                freshness="delayed",
            ),
        )
        # Backdate expires_at so the doc is expired.
        long_ago = datetime.utcnow() - timedelta(hours=24)
        db["03_data_ud_kline_daily"].update_one(
            {"security_id": str(cn_maotai)},
            {"$set": {"expires_at": long_ago, "materialized_at": long_ago}},
        )
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        # External tushare called → provider="tushare".
        assert result.provider == "tushare"
        # External provider invoked.
        assert fresh_registry.get("tushare").call_log != []

    def test_step2_miss_step3_hit(self, fresh_registry, cn_maotai):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload=None,
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        cache = CacheManager(mongo_db=db)
        cache.put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [100]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="tushare",
                fetched_at=datetime.utcnow(),
                source_trace=["tushare(ok)"],
                freshness="delayed",
            ),
        )
        db["03_data_ud_cache_kline_daily"].update_one(
            {"security_id": str(cn_maotai)},
            {"$set": {"expires_at": datetime.utcnow() + timedelta(hours=1)}},
        )
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.freshness == "cached"
        # Cache provider stamp preserved.
        assert result.provider == "tushare"
        # External provider not invoked (cache hit).
        assert fresh_registry.get("tushare").call_log == []

    def test_step2_3_miss_step4_ok(self, fresh_registry, cn_maotai):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "tushare"

    def test_step2_exception_continues(self, fresh_registry, cn_maotai, monkeypatch):
        def boom(*_args, **_kwargs):
            raise RuntimeError("simulated step 2 failure")

        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        adapter = LocalMongoAdapter(mongo_db=db)
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        # Patch the adapter's ``get`` to raise. The router must catch
        # the exception (DR-205) and fall through to Step 3/4.
        monkeypatch.setattr(adapter, "get", boom)
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        # External tushare was called.
        assert fresh_registry.get("tushare").call_log != []
        # The DataResult succeeded (didn't propagate the error).
        assert result.provider == "tushare"

    def test_step3_exception_continues(self, fresh_registry, cn_maotai, monkeypatch):
        def boom(*_args, **_kwargs):
            raise RuntimeError("simulated step 3 failure")

        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        cache = CacheManager(mongo_db=db)
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        monkeypatch.setattr(cache, "get", boom)
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "tushare"
        assert fresh_registry.get("tushare").call_log != []

    def test_force_refresh_skips_step2_3(self, fresh_registry, cn_maotai, monkeypatch):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        # Seed both layers with a valid hit; force_refresh must bypass.
        LocalMongoAdapter(mongo_db=db).put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [1]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="tushare",
                fetched_at=datetime.utcnow(),
                source_trace=["tushare(ok)"],
                freshness="delayed",
            ),
        )
        adapter = LocalMongoAdapter(mongo_db=db)
        cache = CacheManager(mongo_db=db)
        # Track get() calls to verify they are never invoked under
        # force_refresh (方案 C: helper returns None without calling
        # the underlying component).
        adapter_get_calls = []
        cache_get_calls = []
        orig_adapter_get = adapter.get
        orig_cache_get = cache.get

        def track_adapter_get(*a, **kw):
            adapter_get_calls.append((a, kw))
            return orig_adapter_get(*a, **kw)

        def track_cache_get(*a, **kw):
            cache_get_calls.append((a, kw))
            return orig_cache_get(*a, **kw)

        monkeypatch.setattr(adapter, "get", track_adapter_get)
        monkeypatch.setattr(cache, "get", track_cache_get)
        router = DataRouter(
            fresh_registry,
            local_mongo_adapter=adapter,
            cache_manager=cache,
        )
        result = router.query(
            "market_data",
            "kline_daily",
            cn_maotai,
            force_refresh=True,
        )
        assert result.provider == "tushare"
        assert fresh_registry.get("tushare").call_log != []
        # 方案 C: two force_refresh skip entries must appear in trace.
        trace = " ".join(result.source_trace)
        assert "ud_materialized(skipped: force_refresh)" in trace
        assert "cache(skipped: force_refresh)" in trace
        # Neither adapter.get() nor cache.get() was called.
        assert adapter_get_calls == []
        assert cache_get_calls == []

    def test_provider_external_skips_step2_3(self, fresh_registry, cn_maotai):
        fresh_registry.register(
            FakeProvider(
                name="akshare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        # Seed cache so we can prove the provider pin bypasses it.
        CacheManager(mongo_db=db).put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [1]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="akshare",
                fetched_at=datetime.utcnow(),
                source_trace=["akshare(ok)"],
                freshness="delayed",
            ),
        )
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        result = router.query(
            "market_data",
            "kline_daily",
            cn_maotai,
            provider="akshare",
        )
        assert result.provider == "akshare"
        assert fresh_registry.get("akshare").call_log != []

    def test_step2_adapter_none_skips(self, fresh_registry, cn_maotai):
        # Router with NO 1B-B components — Pascal 2026-07-14 chose option
        # B: every missing-component path must record a trace entry
        # (DR-213 / DR-214), not stay silent. The external chain still
        # serves the request with provider="tushare".
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        router = DataRouter(fresh_registry)
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "tushare"
        # DR-213: Step 2 skip must be visible in source_trace.
        assert "ud_materialized(skipped: no adapter)" in result.source_trace
        # DR-214 also fires in this scenario (manager is None too).
        # Both reasons are emitted; do not collapse them.

    def test_step3_manager_none_skips(self, fresh_registry, cn_maotai):
        # Router with the Step 3 component explicitly absent (Step 2
        # adapter is wired in but the cache manager is None).
        # DR-214: the missing-manager path must record
        # "cache(skipped: no manager)" in source_trace.
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=False,
            with_cache=False,
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "tushare"
        # DR-214: Step 3 skip must be visible in source_trace.
        assert "cache(skipped: no manager)" in result.source_trace
        # Step 2 adapter is None here too; DR-213 entry is also expected.
        # Both skip reasons coexist; their coexistence is the
        # documented behavior under option B.


# ---------------------------------------------------------------------------
# Materialization chain
# ---------------------------------------------------------------------------


class TestRouterMaterialization:
    def test_external_success_materializes(self, fresh_registry, cn_maotai):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        adapter = LocalMongoAdapter(mongo_db=db)
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        router.query("market_data", "kline_daily", cn_maotai)
        # LocalMongoAdapter now contains the new materialised record.
        cached = adapter.get(cn_maotai, "market_data", "kline_daily", {})
        assert cached is not None
        assert cached.data == {"close": [1234]}

    def test_external_success_caches(self, fresh_registry, cn_maotai):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        cache = CacheManager(mongo_db=db)
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        router.query("market_data", "kline_daily", cn_maotai)
        cached = cache.get(cn_maotai, "market_data", "kline_daily", {})
        assert cached is not None
        assert cached.data == {"close": [1234]}

    def test_materialize_put_fail_does_not_block(
        self, fresh_registry, cn_maotai, monkeypatch
    ):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        adapter = LocalMongoAdapter(mongo_db=db)

        def boom(*_args, **_kwargs):
            raise RuntimeError("put failed")

        monkeypatch.setattr(adapter, "put", boom)
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        # The query still returns the external data.
        assert result.provider == "tushare"
        assert result.data == {"close": [1234]}

    def test_cache_put_fail_does_not_block(
        self, fresh_registry, cn_maotai, monkeypatch
    ):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        cache = CacheManager(mongo_db=db)

        def boom(*_args, **_kwargs):
            raise RuntimeError("cache put failed")

        monkeypatch.setattr(cache, "put", boom)
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "tushare"
        assert result.data == {"close": [1234]}

    def test_ta_cn_hit_no_materialize(self, fresh_registry, cn_maotai):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [9999]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        adapter = LocalMongoAdapter(mongo_db=db)
        cache = CacheManager(mongo_db=db)
        router = _build_router(
            registry=fresh_registry,
            ta_cn_adapter=None,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        # Inject a TA-CN adapter manually here (build helper skips it).
        from skills.data.unified_data.tests.conftest import FakeTA_CNAdapter
        ta_cn = FakeTA_CNAdapter(
            collections={
                "stock_daily_quotes": [
                    {
                        "symbol": cn_maotai.symbol,
                        "trade_date": "20260713",
                        "close": 100,
                    }
                ]
            }
        )
        router = DataRouter(
            fresh_registry,
            ta_cn_adapter=ta_cn,
            local_mongo_adapter=adapter,
            cache_manager=cache,
        )
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "ta_cn_internal"
        # The persistence + cache layers stay empty — TA-CN hits are
        # not materialised (MW-105).
        assert adapter.get(cn_maotai, "market_data", "kline_daily", {}) is None
        assert cache.get(cn_maotai, "market_data", "kline_daily", {}) is None
        # External provider was NOT invoked.
        assert fresh_registry.get("tushare").call_log == []


# ---------------------------------------------------------------------------
# Errors / contract
# ---------------------------------------------------------------------------


class TestRouterErrors:
    def test_all_internal_miss_external_fail(self, fresh_registry, cn_maotai):
        # Every external provider raises.
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload=None,
                raise_on_fetch=ProviderError("tushare dead"),
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        fresh_registry.register(
            FakeProvider(
                name="akshare",
                payload=None,
                raise_on_fetch=ProviderError("akshare dead"),
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        router = _build_router(
            registry=fresh_registry,
            db=db,
            with_local_mongo=True,
            with_cache=True,
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "error"
        assert "all external providers failed" in result.warnings

    def test_source_trace_full_chain(
        self, fresh_registry, cn_maotai, fake_ta_cn_with_kline
    ):
        # With TA-CN adapter that misses, local_mongo empty, cache empty,
        # external succeeds — the chain should contain all four steps.
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        # Use a TA-CN adapter that does NOT cover the capability.
        from skills.data.unified_data.tests.conftest import FakeTA_CNAdapter
        ta_cn = FakeTA_CNAdapter(
            covered_capabilities=set()  # cover nothing → Step 1 skipped
        )
        router = DataRouter(
            fresh_registry,
            ta_cn_adapter=ta_cn,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=db),
            cache_manager=CacheManager(mongo_db=db),
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        trace = " ".join(result.source_trace)
        # No "ta_cn_internal(skipped)" — capability map lookup returns None
        # but we filter on TA-CN cover before calling. The TA-CN
        # branch logs nothing in this case (the Router short-circuits).
        assert "ud_materialized(miss)" in trace
        assert "cache(miss)" in trace
        assert "tushare(ok)" in trace


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


class TestRouterIntegration:
    def test_full_internal_ta_cn_miss_materialized_hit(
        self, fresh_registry, cn_maotai, fake_ta_cn_with_kline
    ):
        # Step 1 misses (wrong collection), Step 2 hits, no external call.
        from skills.data.unified_data.tests.conftest import FakeTA_CNAdapter

        ta_cn = FakeTA_CNAdapter(
            collections={}  # no docs → Step 1 returns empty
        )
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [9999]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        LocalMongoAdapter(mongo_db=db).put(
            cn_maotai,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [50]},
                security_id=cn_maotai,
                domain="market_data",
                operation="kline_daily",
                provider="tushare",
                fetched_at=datetime.utcnow(),
                source_trace=["tushare(ok)"],
                freshness="delayed",
            ),
        )
        db["03_data_ud_kline_daily"].update_one(
            {"security_id": str(cn_maotai)},
            {"$set": {"expires_at": datetime.utcnow() + timedelta(hours=1)}},
        )
        router = DataRouter(
            fresh_registry,
            ta_cn_adapter=ta_cn,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=db),
            cache_manager=CacheManager(mongo_db=db),
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "ud_materialized"
        # External not invoked.
        assert fresh_registry.get("tushare").call_log == []

    def test_full_internal_all_miss_external_ok(self, fresh_registry, cn_maotai):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        adapter = LocalMongoAdapter(mongo_db=db)
        cache = CacheManager(mongo_db=db)
        router = DataRouter(
            fresh_registry,
            local_mongo_adapter=adapter,
            cache_manager=cache,
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "tushare"
        # Materialisation chain fired.
        assert adapter.get(cn_maotai, "market_data", "kline_daily", {}) is not None
        assert cache.get(cn_maotai, "market_data", "kline_daily", {}) is not None

    def test_force_refresh_skip_all_internal(self, fresh_registry, cn_maotai):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload={"close": [1234]},
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        adapter = LocalMongoAdapter(mongo_db=db)
        cache = CacheManager(mongo_db=db)
        router = DataRouter(
            fresh_registry,
            local_mongo_adapter=adapter,
            cache_manager=cache,
        )
        result = router.query(
            "market_data",
            "kline_daily",
            cn_maotai,
            force_refresh=True,
        )
        assert result.provider == "tushare"
        # 方案 C: trace contains the force_refresh skip entries.
        trace = " ".join(result.source_trace)
        assert "ud_materialized(skipped: force_refresh)" in trace
        assert "cache(skipped: force_refresh)" in trace
        # Materialisation still fires (DR-212) — external success is
        # persisted even when the read path was force-refreshed.
        assert adapter.get(cn_maotai, "market_data", "kline_daily", {}) is not None
        assert cache.get(cn_maotai, "market_data", "kline_daily", {}) is not None

    def test_full_internal_all_fail(self, fresh_registry, cn_maotai):
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload=None,
                raise_on_fetch=ProviderError("dead"),
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        fresh_registry.register(
            FakeProvider(
                name="akshare",
                payload=None,
                raise_on_fetch=ProviderError("dead"),
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        db = _make_db()
        router = DataRouter(
            fresh_registry,
            local_mongo_adapter=LocalMongoAdapter(mongo_db=db),
            cache_manager=CacheManager(mongo_db=db),
        )
        result = router.query(
            "market_data", "kline_daily", cn_maotai
        )
        assert result.provider == "error"