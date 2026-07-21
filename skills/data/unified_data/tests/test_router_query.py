"""Phase 3 P3-A router query tests (offline T3-A scaffold).

T3-A acceptance matrix entries (kanban task body, decision C.a):

| #   | test name                                  | file                |
|-----|--------------------------------------------|---------------------|
| ①   | test_query_path_readonly                   | test_router_query.py |
| ③   | test_try_materialized_capability_dispatch  | test_router_query.py |

Scope (DESIGN-03-014 §2.1 "读取路径不变形约束"):

* Query path stays entirely read-only — ``source_trace`` must not
  contain ``"ud_materialized"`` when no ``local_mongo_adapter`` and
  no ``p3_writer`` are wired in.
* ``_try_materialized`` dispatches by capability:
  * P3 capability + injected ``p3_writer`` → writer's ``get`` is
    consulted; trace records ``"ud_materialized(ok|miss|error)"``.
  * Non-P3 capability → falls back to the ``LocalMongoAdapter`` path
    (unchanged Phase 1B-B behaviour).

No real MongoDB / AKShare / cron / AuditLogger / QualitySummary
writes — strictly offline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import mongomock
import pytest

from skills.data.unified_data import (
    DataRouter,
    Market,
    ProviderRegistry,
    SecurityId,
)
from skills.data.unified_data.adapters.p3_persistence_writer import (
    P3_COLLECTION_BY_CAPABILITY,
    P3PersistenceWriter,
)
from skills.data.unified_data.tests.conftest import FakeProvider


SECTOR_CAP = "sector.snapshot"
SECTOR_COLLECTION = "03_data_ud_market_sector_snapshot"
NON_P3_CAP = "market_data.kline_daily"


def _make_db() -> Any:
    return mongomock.MongoClient().get_database("tradingagents")


# ---------------------------------------------------------------------------
# Test ① — query path is read-only
# ---------------------------------------------------------------------------


class TestQueryPathReadOnly:
    """The standard ``query()`` path never writes to ``ud_materialized``."""

    def test_query_without_persistor_has_no_ud_materialized_trace(self):
        """No ``local_mongo_adapter`` + no ``p3_writer`` → trace stays empty."""
        registry = ProviderRegistry()
        registry.register(
            FakeProvider(
                name="akshare_stub",
                payload=[{"row": 1}],
                capabilities={SECTOR_CAP},
                # Advertise all six Market enum values so any SecurityId
                # market passes the ``supports(capability, market)`` check.
                markets={m for m in Market},
            )
        )
        router = DataRouter(registry=registry)
        sid = SecurityId(market="INDEX", symbol="BK0489")

        result = router.query(
            domain="sector",
            operation="snapshot",
            security_id=sid,
        )

        # Step 4 succeeds; provider reflects the stub.
        assert result.provider == "akshare_stub"
        # The trace records the stub's successful fetch but NOT any
        # ``ud_materialized`` entry — the query path stayed read-only.
        assert "ud_materialized" not in result.source_trace

    def test_query_with_p3_writer_still_readonly_in_query_path(self):
        """Even with ``p3_writer`` injected, ``query()`` does not call ``upsert``.

        The writer is only consulted by Step 2 (read). The query
        path's success path (``_materialize`` / ``_query_external_chain_with_cache``)
        must not touch the writer at all.
        """
        registry = ProviderRegistry()
        registry.register(
            FakeProvider(
                name="akshare_stub",
                payload=[{"row": 1}],
                capabilities={SECTOR_CAP},
                markets={m for m in Market},
            )
        )
        writer = P3PersistenceWriter(_make_db())
        router = DataRouter(registry=registry, p3_writer=writer)
        sid = SecurityId(market="INDEX", symbol="BK0489")

        result = router.query(
            domain="sector",
            operation="snapshot",
            security_id=sid,
        )

        # Provider is the external stub (Step 4 succeeded; Step 2 was
        # a miss because nothing has been written yet).
        assert result.provider == "akshare_stub"
        # The trace contains the miss entry but NO success / write
        # marker — the writer was consulted for read only.
        assert "ud_materialized(miss)" in result.source_trace
        # Writer collection must still be empty — query path did not
        # perform any write.
        assert writer.get(SECTOR_COLLECTION, {}) == []


# ---------------------------------------------------------------------------
# Test ③ — _try_materialized capability dispatch
# ---------------------------------------------------------------------------


class TestTryMaterializedCapabilityDispatch:
    """``_try_materialized`` routes by capability to P3PersistenceWriter
    or LocalMongoAdapter."""

    def test_p3_capability_with_p3_writer_uses_p3_writer(self):
        """``sector.snapshot`` → ``P3PersistenceWriter.get`` (not LocalMongoAdapter)."""
        registry = ProviderRegistry()
        writer = P3PersistenceWriter(_make_db())

        # Pre-populate the writer with one record.
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[
                {
                    "market": "CN",
                    "sector_code": "BK0489",
                    "snapshot_date": "2026-07-21",
                    "pct_chg": 2.35,
                }
            ],
            unique_key={"market", "sector_code", "snapshot_date"},
        )

        router = DataRouter(registry=registry, p3_writer=writer)
        sid = SecurityId(market="INDEX", symbol="BK0489")
        trace: list[str] = []
        ts = datetime.utcnow()

        result = router._try_materialized(
            security_id=sid,
            domain="sector",
            operation="snapshot",
            params={"sector_code": "BK0489"},
            trace=trace,
            ts=ts,
            capability=SECTOR_CAP,
            p3_writer=writer,
        )

        assert result is not None
        assert result.provider == "ud_materialized"
        assert result.freshness == "cached"
        assert "ud_materialized(ok)" in trace
        # The returned data is the row the writer produced.
        assert isinstance(result.data, list)
        assert result.data and result.data[0]["sector_code"] == "BK0489"

    def test_non_p3_capability_falls_back_to_local_mongo_adapter(self):
        """``market_data.kline_daily`` is NOT in the P3 map → LocalMongoAdapter path."""
        from skills.data.unified_data import DataResult, LocalMongoAdapter

        registry = ProviderRegistry()
        db = _make_db()
        local = LocalMongoAdapter(mongo_db=db)
        sid = SecurityId(market="CN", symbol="600519")

        # Pre-populate LocalMongoAdapter (NOT the P3 writer).
        local.put(
            sid,
            "market_data",
            "kline_daily",
            {},
            DataResult(
                data={"close": [1620.0]},
                security_id=sid,
                domain="market_data",
                operation="kline_daily",
                provider="tushare",
                fetched_at=datetime.utcnow(),
                source_trace=["tushare(ok)"],
            ),
        )

        router = DataRouter(
            registry=registry,
            local_mongo_adapter=local,
            p3_writer=P3PersistenceWriter(_make_db()),
        )
        trace: list[str] = []
        ts = datetime.utcnow()

        # NON_P3_CAP must skip the P3 branch even though p3_writer is
        # injected. The capability dispatch test pins this contract.
        result = router._try_materialized(
            security_id=sid,
            domain="market_data",
            operation="kline_daily",
            params={},
            trace=trace,
            ts=ts,
            capability=NON_P3_CAP,
            p3_writer=router._p3_writer,
        )

        assert result is not None
        assert result.provider == "ud_materialized"
        # The data must come from LocalMongoAdapter (the close=1620
        # fixture), not from the P3 writer (which is empty).
        assert result.data == {"close": [1620.0]}
        assert "ud_materialized(ok)" in trace

    def test_p3_capability_without_p3_writer_falls_back_to_local_mongo(self):
        """Defence-in-depth: if the writer is None, P3 capabilities degrade to
        LocalMongoAdapter (preserves Phase 1B-B behaviour for callers
        who forget to wire the writer)."""
        from skills.data.unified_data import LocalMongoAdapter

        registry = ProviderRegistry()
        db = _make_db()
        local = LocalMongoAdapter(mongo_db=db)
        sid = SecurityId(market="INDEX", symbol="BK0489")

        router = DataRouter(registry=registry, local_mongo_adapter=local)
        # No ``p3_writer`` argument — defaults to None.

        trace: list[str] = []
        ts = datetime.utcnow()
        result = router._try_materialized(
            security_id=sid,
            domain="sector",
            operation="snapshot",
            params={"sector_code": "BK0489"},
            trace=trace,
            ts=ts,
            capability=SECTOR_CAP,
            p3_writer=None,
        )

        # LocalMongoAdapter has nothing for this (sid, domain, op,
        # params) tuple either — both layers return None, and the
        # trace records the LocalMongoAdapter miss (P3 branch was
        # skipped entirely because writer was None).
        assert result is None
        assert "ud_materialized(miss)" in trace

    def test_p3_capability_miss_records_miss_in_trace(self):
        """P3 capability + writer injected + empty collection → miss trace."""
        registry = ProviderRegistry()
        writer = P3PersistenceWriter(_make_db())
        router = DataRouter(registry=registry, p3_writer=writer)
        sid = SecurityId(market="INDEX", symbol="BK0489")
        trace: list[str] = []
        ts = datetime.utcnow()

        result = router._try_materialized(
            security_id=sid,
            domain="sector",
            operation="snapshot",
            params={"sector_code": "BK0489"},
            trace=trace,
            ts=ts,
            capability=SECTOR_CAP,
            p3_writer=writer,
        )
        assert result is None
        assert "ud_materialized(miss)" in trace

    def test_p3_capability_force_refresh_records_skip(self):
        """P3 capability + force_refresh=True → ``skipped: force_refresh``."""
        registry = ProviderRegistry()
        writer = P3PersistenceWriter(_make_db())
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[
                {
                    "market": "CN",
                    "sector_code": "BK0489",
                    "snapshot_date": "2026-07-21",
                    "pct_chg": 99.0,
                }
            ],
            unique_key={"market", "sector_code", "snapshot_date"},
        )
        router = DataRouter(registry=registry, p3_writer=writer)
        sid = SecurityId(market="INDEX", symbol="BK0489")
        trace: list[str] = []
        ts = datetime.utcnow()

        result = router._try_materialized(
            security_id=sid,
            domain="sector",
            operation="snapshot",
            params={},
            trace=trace,
            ts=ts,
            force_refresh=True,
            capability=SECTOR_CAP,
            p3_writer=writer,
        )

        assert result is None
        assert "ud_materialized(skipped: force_refresh)" in trace

    def test_p3_writer_exception_records_error_trace(self):
        """A failing writer is caught-and-logged; trace records ``error:``."""
        registry = ProviderRegistry()

        class _BrokenWriter:
            def get(self, collection, filter):
                raise RuntimeError("boom")

            def upsert(self, collection, records, unique_key):
                raise RuntimeError("nope")

        writer = _BrokenWriter()
        router = DataRouter(registry=registry, p3_writer=writer)
        sid = SecurityId(market="INDEX", symbol="BK0489")
        trace: list[str] = []
        ts = datetime.utcnow()

        result = router._try_materialized(
            security_id=sid,
            domain="sector",
            operation="snapshot",
            params={},
            trace=trace,
            ts=ts,
            capability=SECTOR_CAP,
            p3_writer=writer,
        )

        assert result is None
        assert any("ud_materialized(error:" in entry for entry in trace)

    def test_p3_collection_map_constants_are_present(self):
        """Guard against accidental capability-map edits."""
        # These four capabilities are the documented P3-A surface.
        for cap in ("sector.snapshot", "sector.ranking"):
            assert cap in P3_COLLECTION_BY_CAPABILITY
            assert (
                P3_COLLECTION_BY_CAPABILITY[cap]
                == "03_data_ud_market_sector_snapshot"
            )