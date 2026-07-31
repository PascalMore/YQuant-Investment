"""T3D — End-to-end Router P3 internal-first materialized read.

P1 Recovery T3D (kanban ``t_619c10b7``) wires the
``P3PersistenceWriter`` already landed by T3-A / T3-B into the full
``DataRouter.query()`` orchestration and proves it end-to-end.

Scope (DESIGN-03-014 §0.4 / §2.1; SPEC-03-014 §537-546 / RFC-03-014
§240-251):

* For each of the six P3 capabilities (``sector.snapshot`` /
  ``sector.ranking`` / ``flow.capital_flow_daily`` /
  ``flow.northbound_daily`` / ``sentiment.market_snapshot`` /
  ``sentiment.limit_up_pool``), pre-populate the writer with a known
  record through the documented business unique key, then call
  ``router.query()``. The router must short-circuit at
  ``_try_materialized`` and return
  ``DataResult(provider="ud_materialized", freshness="cached")``
  with the persisted row(s) — **without** ever invoking the
  external fallback chain.
* Trace discipline: ``source_trace`` must contain exactly one
  ``"ud_materialized(ok)"`` entry — no incidental
  ``"ud_materialized(miss)"`` / ``"ud_materialized(error: ...)"`` /
  ``"ud_materialized(skipped: ...)"`` noise.
* Non-P3 capability sanity guard: a non-P3 capability with the same
  ``p3_writer`` injected must fall through to ``LocalMongoAdapter``
  (Phase 1B-B behaviour preserved).
* P3 writer is **read-only on the query path** — the writer
  collection must NOT receive any upsert during the query
  (T3-P3B M1 invariant).

No real MongoDB / AKShare / cron / AuditLogger / QualitySummary
writes — strictly offline (mongomock + FakeProvider).
"""

from __future__ import annotations

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
    P3PersistenceWriter,
)
from skills.data.unified_data.tests.conftest import FakeProvider


# The six P3 capabilities covered by the materialized-read integration.
P3_CAPABILITIES: tuple[str, ...] = (
    "sector.snapshot",
    "sector.ranking",
    "flow.capital_flow_daily",
    "flow.northbound_daily",
    "sentiment.market_snapshot",
    "sentiment.limit_up_pool",
)


# ---------------------------------------------------------------------------
# Collection + business unique key constants (per V0.5 §0.4 / §P3-C)
# ---------------------------------------------------------------------------

SECTOR_COLLECTION = "03_data_ud_market_sector_snapshot"
SECTOR_UNIQUE_KEY = frozenset({"market", "sector_code", "snapshot_date"})

FLOW_COLLECTION = "03_data_ud_stock_capital_flow"
FLOW_UNIQUE_KEY = frozenset({"market", "symbol", "trade_date"})

SENTIMENT_COLLECTION = "03_data_ud_market_sentiment_snapshot"
SENTIMENT_UNIQUE_KEY = frozenset({"market", "snapshot_date", "snapshot_time"})

# Per-stock business unique key for the ``sentiment.limit_up_pool``
# capability, sharing ``SENTIMENT_COLLECTION`` with the market-level
# ``sentiment.market_snapshot`` capability. Two capabilities, same
# collection, *different* business unique keys (RFC-03-014-F1 /
# DESIGN-03-014-F1 §2.1 / SPEC-03-014-F1 §2.2). The writer treats
# these as independent documents — upserts under either key coexist
# in the collection without conflict.
LIMIT_UP_POOL_UNIQUE_KEY = frozenset({"market", "symbol", "trade_date"})


# A non-P3 capability used as the regression baseline.
NON_P3_CAPABILITY = "market_data.kline_daily"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> Any:
    """Fresh in-memory mongomock database (offline scaffold)."""
    return mongomock.MongoClient().get_database("tradingagents")


def _make_writer() -> P3PersistenceWriter:
    """Fresh ``P3PersistenceWriter`` backed by mongomock."""
    return P3PersistenceWriter(_make_db())


def _build_router_with_spy(
    *,
    writer: P3PersistenceWriter,
    capability: str,
    security_id: SecurityId,
) -> tuple[DataRouter, FakeProvider]:
    """Build a Router wired with a P3 writer + a spy external provider.

    The spy provider advertises ``capability`` and a unique name so
    the test can assert it was **never** invoked during the
    materialized-read path. If the router ever calls into the
    external fallback chain (Step 4), the spy's ``call_log`` will
    grow (assert via ``len(spy.call_log)``).
    """
    registry = ProviderRegistry()
    spy = FakeProvider(
        name=f"{capability}_spy",
        payload={"row": "external-fallback-should-not-fire"},
        capabilities={capability},
        markets={security_id.market},
    )
    registry.register(spy)
    router = DataRouter(
        registry=registry,
        p3_writer=writer,
    )
    return router, spy


# ---------------------------------------------------------------------------
# Per-capability happy-path: router.query() returns ud_materialized(ok)
# ---------------------------------------------------------------------------


class TestRouterInternalFirstMaterializedRead:
    """End-to-end proof that ``router.query()`` short-circuits at
    ``_try_materialized`` when the writer has the row."""

    def test_sector_snapshot_returns_ud_materialized(self):
        """``sector.snapshot`` → materialized hit, no external call."""
        writer = _make_writer()
        record = {
            "market": "CN",
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "pct_chg": 2.35,
            "rank": 5,
        }
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[record],
            unique_key=SECTOR_UNIQUE_KEY,
        )
        sid = SecurityId(market=Market.INDEX, symbol="BK0489")
        router, spy = _build_router_with_spy(
            writer=writer,
            capability="sector.snapshot",
            security_id=sid,
        )

        result = router.query(
            domain="sector",
            operation="snapshot",
            security_id=sid,
            market="CN",
            params={
                "sector_code": "BK0489",
                "snapshot_date": "2026-07-21",
            },
        )

        # The contract: materialized hit, no fallback chain invoked.
        assert result.provider == "ud_materialized", (
            f"expected router.query to short-circuit at Step 2 for a "
            f"P3 capability; got provider={result.provider!r}"
        )
        assert result.freshness == "cached"
        assert len(spy.call_log) == 0, (
            "external fallback chain must NOT fire when materialized "
            "read returned a hit; spy saw {} call(s)".format(len(spy.call_log))
        )
        # Trace discipline: exactly one (ok) entry, no (miss) / (error) /
        # (skipped) noise. The P3 hit is observable end-to-end.
        ok_entries = [e for e in result.source_trace if "ud_materialized(ok)" in e]
        assert len(ok_entries) == 1, (
            f"expected exactly one ud_materialized(ok); trace={result.source_trace}"
        )
        miss_entries = [
            e for e in result.source_trace
            if "ud_materialized" in e and "(ok)" not in e
        ]
        assert miss_entries == [], (
            f"P3 hit must not emit any miss/error/skip entry; "
            f"trace={result.source_trace}"
        )
        # The returned data is the row the writer produced — proves
        # the row flowed through the router, not through a stub.
        assert isinstance(result.data, list)
        assert result.data and result.data[0]["sector_code"] == "BK0489"
        assert result.data[0]["pct_chg"] == 2.35

    def test_sector_ranking_returns_ud_materialized(self):
        """``sector.ranking`` → materialized hit (shares collection)."""
        writer = _make_writer()
        record = {
            "market": "CN",
            "sector_code": "BK0500",
            "sector_name": "证券",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "pct_chg": -0.50,
            "rank": 88,
        }
        writer.upsert(
            collection=SECTOR_COLLECTION,
            records=[record],
            unique_key=SECTOR_UNIQUE_KEY,
        )
        sid = SecurityId(market=Market.CN, symbol="sector_ranking:2026-07-21:all")
        router, spy = _build_router_with_spy(
            writer=writer,
            capability="sector.ranking",
            security_id=sid,
        )

        result = router.query(
            domain="sector",
            operation="ranking",
            security_id=sid,
        )

        assert result.provider == "ud_materialized"
        assert result.freshness == "cached"
        assert len(spy.call_log) == 0
        assert "ud_materialized(ok)" in result.source_trace
        assert isinstance(result.data, list)
        assert result.data and result.data[0]["sector_code"] == "BK0500"

    def test_flow_capital_flow_daily_returns_ud_materialized(self):
        """``flow.capital_flow_daily`` → materialized hit."""
        writer = _make_writer()
        record = {
            "market": "CN",
            "symbol": "600519",
            "trade_date": "2026-07-21",
            "main_net_inflow": 12_345_678.0,
            "main_net_inflow_pct": 1.23,
            "retail_net_inflow": -2_000_000.0,
            "provider": "flow_stub",
        }
        writer.upsert(
            collection=FLOW_COLLECTION,
            records=[record],
            unique_key=FLOW_UNIQUE_KEY,
        )
        sid = SecurityId(market=Market.CN, symbol="600519")
        router, spy = _build_router_with_spy(
            writer=writer,
            capability="flow.capital_flow_daily",
            security_id=sid,
        )

        result = router.query(
            domain="flow",
            operation="capital_flow_daily",
            security_id=sid,
        )

        assert result.provider == "ud_materialized"
        assert result.freshness == "cached"
        assert len(spy.call_log) == 0
        assert "ud_materialized(ok)" in result.source_trace
        assert isinstance(result.data, list)
        assert result.data and result.data[0]["symbol"] == "600519"
        assert result.data[0]["main_net_inflow"] == 12_345_678.0

    def test_flow_northbound_daily_returns_ud_materialized(self):
        """``flow.northbound_daily`` → materialized hit (shares flow coll)."""
        writer = _make_writer()
        record = {
            "market": "CN",
            "symbol": "flow:northbound:market",
            "trade_date": "2026-07-21",
            "main_net_inflow": 0.0,
            "northbound_net_flow": 5_000_000.0,
            "provider": "northbound_stub",
        }
        writer.upsert(
            collection=FLOW_COLLECTION,
            records=[record],
            unique_key=FLOW_UNIQUE_KEY,
        )
        # ``sentiment_service._placeholder_security_id`` documents the
        # ``Market.CN`` + composite symbol pattern for market-level
        # northbound; the router only inspects ``market`` / ``symbol``
        # for log correlation, the writer routes by business-key
        # filter regardless.
        sid = SecurityId(market=Market.CN, symbol="flow:northbound:market")
        router, spy = _build_router_with_spy(
            writer=writer,
            capability="flow.northbound_daily",
            security_id=sid,
        )

        result = router.query(
            domain="flow",
            operation="northbound_daily",
            security_id=sid,
        )

        assert result.provider == "ud_materialized"
        assert result.freshness == "cached"
        assert len(spy.call_log) == 0
        assert "ud_materialized(ok)" in result.source_trace
        assert isinstance(result.data, list)
        assert result.data and result.data[0]["northbound_net_flow"] == 5_000_000.0

    def test_sentiment_market_snapshot_returns_ud_materialized(self):
        """``sentiment.market_snapshot`` → materialized hit."""
        writer = _make_writer()
        record = {
            "market": "CN",
            "snapshot_date": "2026-07-21",
            "snapshot_time": "close",
            "limit_up_count": 42,
            "limit_down_count": 8,
            "advance_count": 3250,
            "decline_count": 1500,
            "flat_count": 250,
            "market_temperature": None,
            "northbound_net_flow": None,
            "provider": "sentiment_stub",
        }
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[record],
            unique_key=SENTIMENT_UNIQUE_KEY,
        )
        # ``sentiment_service.get_market_sentiment_snapshot`` uses
        # ``Market.INDEX`` + composite symbol placeholder.
        placeholder_symbol = "CN:2026-07-21:close"
        sid = SecurityId(market=Market.INDEX, symbol=placeholder_symbol)
        router, spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.market_snapshot",
            security_id=sid,
        )

        result = router.query(
            domain="sentiment",
            operation="market_snapshot",
            security_id=sid,
            market="CN",
            params={
                "snapshot_date": "2026-07-21",
                "snapshot_time": "close",
            },
        )

        assert result.provider == "ud_materialized"
        assert result.freshness == "cached"
        assert len(spy.call_log) == 0
        assert "ud_materialized(ok)" in result.source_trace
        assert isinstance(result.data, list)
        assert result.data and result.data[0]["limit_up_count"] == 42

    def test_sentiment_limit_up_pool_returns_ud_materialized(self):
        """``sentiment.limit_up_pool`` → materialized hit (LimitUpPoolRecord).

        RFC-03-014-F1 / DESIGN-03-014-F1: ``sentiment.limit_up_pool`` is
        a *per-stock* capability sharing the
        ``03_data_ud_market_sentiment_snapshot`` collection with
        ``sentiment.market_snapshot``. Its canonical business unique key
        is ``{market, symbol, trade_date}`` (matching
        ``LimitUpPoolRecord``), not
        ``{market, snapshot_date, snapshot_time}``. This test therefore
        upserts a ``LimitUpPoolRecord``-shaped row through the per-stock
        key and reads it back via the ``sentiment.limit_up_pool``
        capability — proving the documented contract rather than the
        previous (incorrect) MarketSentimentSnapshot-shaped payload.
        """
        writer = _make_writer()
        record = {
            "market": "CN",
            "symbol": "600519",
            "trade_date": "2026-07-21",
            "status": "limit_up",
            "limit_up_time": "09:30:05",
            "last_price": 150.25,
            "pct_chg": 10.0,
            "provider": "limit_up_stub",
            # Minimal fields — the row proves the upsert/get round-trip
            # under the canonical per-stock business unique key.
        }
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[record],
            unique_key=LIMIT_UP_POOL_UNIQUE_KEY,
        )
        placeholder_symbol = "limit_up_pool:2026-07-21"
        sid = SecurityId(market=Market.INDEX, symbol=placeholder_symbol)
        router, spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.limit_up_pool",
            security_id=sid,
        )

        result = router.query(
            domain="sentiment",
            operation="limit_up_pool",
            security_id=sid,
            market="CN",
            params={"trade_date": "2026-07-21"},
        )

        assert result.provider == "ud_materialized"
        assert result.freshness == "cached"
        assert len(spy.call_log) == 0
        assert "ud_materialized(ok)" in result.source_trace
        assert isinstance(result.data, list)
        assert result.data and result.data[0]["symbol"] == "600519"
        assert result.data[0]["trade_date"] == "2026-07-21"


# ---------------------------------------------------------------------------
# F4 cross-market / cross-date negative isolation (RFC-03-014-F4 §3 / SPEC §5.1)
# ---------------------------------------------------------------------------


class TestF4MaterializedReadMarketDateIsolation:
    """F4 (SPEC-03-014-F4 §5.1 C-3 / C-4): the materialized-read filter
    MUST isolate by ``market`` AND ``trade_date``. Cross-market and
    cross-date rows MUST NOT leak into a CN/date query result.

    Without the F4 amendment (DESIGN-03-014-F4 §2.3), the filter was
    only ``{"trade_date": "..."}`` so any same-date record — irrespective
    of market — leaked into the result.
    """

    def test_cross_market_negative_isolation_returns_only_cn(
        self,
    ):
        """C-3: CN/date query does NOT leak US/HK/INDEX rows."""
        writer = _make_writer()
        # Seed rows for three markets + same trade_date.
        rows = [
            {"market": "CN", "symbol": "600519",
             "trade_date": "2026-07-21", "status": "limit_up"},
            {"market": "US", "symbol": "AAPL",
             "trade_date": "2026-07-21", "status": "limit_up"},
            {"market": "HK", "symbol": "00700",
             "trade_date": "2026-07-21", "status": "limit_up"},
            {"market": "INDEX", "symbol": "BK0001",
             "trade_date": "2026-07-21", "status": "limit_up"},
        ]
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=rows,
            unique_key=LIMIT_UP_POOL_UNIQUE_KEY,
        )
        placeholder_symbol = "limit_up_pool:2026-07-21"
        sid = SecurityId(market=Market.INDEX, symbol=placeholder_symbol)
        router, spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.limit_up_pool",
            security_id=sid,
        )

        result = router.query(
            domain="sentiment",
            operation="limit_up_pool",
            security_id=sid,
            market="CN",
        )

        assert result.provider == "ud_materialized"
        assert isinstance(result.data, list)
        # Only CN row must surface — US/HK/INDEX must NOT leak.
        assert len(result.data) == 1, (
            f"expected only CN row, got {result.data}"
        )
        assert result.data[0]["market"] == "CN"
        assert result.data[0]["symbol"] == "600519"
        # Spy must not have fired — writer short-circuited the chain.
        assert len(spy.call_log) == 0

    def test_cross_date_negative_isolation_returns_only_target_date(
        self,
    ):
        """C-4: CN/date query does NOT leak rows from other trade_dates."""
        writer = _make_writer()
        rows = [
            {"market": "CN", "symbol": "600519",
             "trade_date": "2026-07-20", "status": "limit_up"},
            {"market": "CN", "symbol": "600519",
             "trade_date": "2026-07-21", "status": "limit_up"},
            {"market": "CN", "symbol": "600519",
             "trade_date": "2026-07-22", "status": "limit_up"},
        ]
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=rows,
            unique_key=LIMIT_UP_POOL_UNIQUE_KEY,
        )
        placeholder_symbol = "limit_up_pool:2026-07-21"
        sid = SecurityId(market=Market.INDEX, symbol=placeholder_symbol)
        router, spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.limit_up_pool",
            security_id=sid,
        )

        result = router.query(
            domain="sentiment",
            operation="limit_up_pool",
            security_id=sid,
            market="CN",
            params={"trade_date": "2026-07-21"},
        )

        assert result.provider == "ud_materialized"
        assert isinstance(result.data, list)
        # Only 2026-07-21 row must surface.
        assert len(result.data) == 1
        assert result.data[0]["trade_date"] == "2026-07-21"
        assert len(spy.call_log) == 0

    def test_market_snapshot_and_limit_up_pool_coexist_on_same_collection(
        self,
    ):
        """C-5: market_snapshot and limit_up_pool share the collection.

        Each capability uses its own business unique key. The router
        must consult the writer with a filter that scopes to the
        requested capability — neither rows leak into the other's
        query result.
        """
        writer = _make_writer()
        # Market-snapshot row keyed by {market, snapshot_date, snapshot_time}
        market_snapshot_row = {
            "market": "CN",
            "snapshot_date": "2026-07-21",
            "snapshot_time": "15:00:00",
            "market_temperature": 72.5,
        }
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[market_snapshot_row],
            unique_key=SENTIMENT_UNIQUE_KEY,
        )
        # Limit-up-pool row keyed by {market, symbol, trade_date}
        limit_up_pool_row = {
            "market": "CN",
            "symbol": "600519",
            "trade_date": "2026-07-21",
            "status": "limit_up",
            "last_price": 150.25,
        }
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[limit_up_pool_row],
            unique_key=LIMIT_UP_POOL_UNIQUE_KEY,
        )

        # 1) market_snapshot query — must see only the snapshot row.
        snapshot_sid = SecurityId(
            market=Market.INDEX,
            symbol="market_snapshot:2026-07-21:15:00:00",
        )
        snapshot_router, snapshot_spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.market_snapshot",
            security_id=snapshot_sid,
        )
        snapshot_result = snapshot_router.query(
            domain="sentiment",
            operation="market_snapshot",
            security_id=snapshot_sid,
            market="CN",
            params={
                "snapshot_date": "2026-07-21",
                "snapshot_time": "15:00:00",
            },
        )
        assert snapshot_result.provider == "ud_materialized"
        assert isinstance(snapshot_result.data, list)
        assert len(snapshot_result.data) == 1
        # market_snapshot row has snapshot_date — limit_up_pool row does not.
        assert "snapshot_date" in snapshot_result.data[0]
        assert "status" not in snapshot_result.data[0]
        assert snapshot_result.data[0]["market"] == "CN"
        assert len(snapshot_spy.call_log) == 0

        # 2) limit_up_pool query — must see only the pool row.
        pool_sid = SecurityId(
            market=Market.INDEX,
            symbol="limit_up_pool:2026-07-21",
        )
        pool_router, pool_spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.limit_up_pool",
            security_id=pool_sid,
        )
        pool_result = pool_router.query(
            domain="sentiment",
            operation="limit_up_pool",
            security_id=pool_sid,
            market="CN",
            params={"trade_date": "2026-07-21"},
        )
        assert pool_result.provider == "ud_materialized"
        assert isinstance(pool_result.data, list)
        assert len(pool_result.data) == 1
        # limit_up_pool row has 'status' — market_snapshot row does not.
        assert pool_result.data[0]["status"] == "limit_up"
        assert pool_result.data[0]["symbol"] == "600519"
        assert "snapshot_date" not in pool_result.data[0]
        assert len(pool_spy.call_log) == 0

    def test_writer_receives_market_in_filter_for_limit_up_pool(
        self,
    ):
        """Spy on writer.get: filter must include ``market``.

        C-1 (SPEC §5.1): the materialized-read filter for a P3 query
        MUST include ``market``. We capture the call via a spy on
        ``P3PersistenceWriter.get`` and assert the filter shape.
        """
        from unittest.mock import patch

        writer = _make_writer()
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[{
                "market": "CN",
                "symbol": "600519",
                "trade_date": "2026-07-21",
                "status": "limit_up",
            }],
            unique_key=LIMIT_UP_POOL_UNIQUE_KEY,
        )
        placeholder_symbol = "limit_up_pool:2026-07-21"
        sid = SecurityId(market=Market.INDEX, symbol=placeholder_symbol)
        router, _spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.limit_up_pool",
            security_id=sid,
        )

        captured_filters: list[dict] = []
        original_get = writer.get

        def capturing_get(collection, filter_, *args, **kwargs):
            captured_filters.append(dict(filter_))
            return original_get(collection, filter_, *args, **kwargs)

        with patch.object(writer, "get", side_effect=capturing_get):
            router.query(
                domain="sentiment",
                operation="limit_up_pool",
                security_id=sid,
                market="CN",
                params={"trade_date": "2026-07-21"},
            )

        # At least one get() call must have carried market + trade_date.
        assert captured_filters, "writer.get was never invoked"
        matched = [
            f for f in captured_filters
            if f.get("market") == "CN"
            and f.get("trade_date") == "2026-07-21"
        ]
        assert matched, (
            f"expected a filter with market='CN' and trade_date, "
            f"saw {captured_filters}"
        )


# ---------------------------------------------------------------------------
# Regression: writer is read-only on the query path (T3-P3B M1)
# ---------------------------------------------------------------------------


class TestQueryPathDoesNotWriteToWriter:
    """The router must NOT call ``writer.upsert`` during query (T3-P3B
    M1 invariant). The materialized read is a *consultation* — no
    incidental write fan-out, no ``refresh`` triggered by read."""

    def test_query_with_p3_writer_does_not_upsert(self):
        writer = _make_writer()
        sid = SecurityId(market=Market.CN, symbol="600519")
        router, _spy = _build_router_with_spy(
            writer=writer,
            capability="flow.capital_flow_daily",
            security_id=sid,
        )

        # Run several queries back-to-back. The writer collection must
        # remain empty — read path must never trigger an upsert.
        for _ in range(3):
            result = router.query(
                domain="flow",
                operation="capital_flow_daily",
                security_id=sid,
            )
            # The miss path returns to Step 4 (the spy) — but the
            # writer must still not receive any upsert.
            assert result.provider != "error"

        # Sanity: writer collection empty.
        assert writer.get(FLOW_COLLECTION, {}) == []

    def test_force_refresh_query_does_not_upsert(self):
        """``force_refresh=True`` on a P3 capability must also stay
        read-only — no upsert, no external write fan-out."""
        writer = _make_writer()
        sid = SecurityId(market=Market.CN, symbol="600519")
        registry = ProviderRegistry()
        spy = FakeProvider(
            name="flow_spy",
            payload={"row": "force-refresh-result"},
            capabilities={"flow.capital_flow_daily"},
            markets={sid.market},
        )
        registry.register(spy)
        router = DataRouter(registry=registry, p3_writer=writer)

        result = router.query(
            domain="flow",
            operation="capital_flow_daily",
            security_id=sid,
            force_refresh=True,
        )

        # External fallback fired (force_refresh bypasses Step 2),
        # but writer still untouched.
        assert len(spy.call_log) == 1
        assert result.provider == "flow_spy"
        assert writer.get(FLOW_COLLECTION, {}) == []


# ---------------------------------------------------------------------------
# Regression: non-P3 capability ignores p3_writer (Phase 1B-B preserved)
# ---------------------------------------------------------------------------


class TestNonP3CapabilityIgnoresP3Writer:
    """Non-P3 capability with ``p3_writer`` injected must fall through to
    the external chain — the writer is not consulted and the result
    carries the external provider's name (not ``ud_materialized``)."""

    def test_kline_daily_with_p3_writer_skips_p3_branch(self):
        registry = ProviderRegistry()
        registry.register(
            FakeProvider(
                name="kline_stub",
                payload={"close": [1.0]},
                capabilities={NON_P3_CAPABILITY},
                markets={Market.CN},
            )
        )
        writer = _make_writer()
        # Pre-populate the writer with a row that *would* match if the
        # capability dispatch were wrong. The router must NOT consult
        # the writer — the spy stub still wins.
        writer.upsert(
            collection="03_data_ud_kline_daily",
            records=[{"market": "CN", "symbol": "600519", "trade_date": "2026-07-21",
                       "close": [999.0]}],
            unique_key={"market", "symbol", "trade_date"},
        )
        router = DataRouter(registry=registry, p3_writer=writer)
        sid = SecurityId(market=Market.CN, symbol="600519")

        result = router.query(
            domain="market_data",
            operation="kline_daily",
            security_id=sid,
        )

        # Non-P3 → external stub wins; writer was NOT consulted.
        assert result.provider == "kline_stub"
        assert result.data == {"close": [1.0]}


# ---------------------------------------------------------------------------
# Trace & result contract invariants
# ---------------------------------------------------------------------------


class TestMaterializedReadTraceContract:
    """The materialized read emits a deterministic trace contract."""

    def test_materialized_hit_emits_exactly_one_ok_entry(self):
        writer = _make_writer()
        writer.upsert(
            collection=FLOW_COLLECTION,
            records=[
                {
                    "market": "CN",
                    "symbol": "600519",
                    "trade_date": "2026-07-21",
                    "main_net_inflow": 1.0,
                }
            ],
            unique_key=FLOW_UNIQUE_KEY,
        )
        sid = SecurityId(market=Market.CN, symbol="600519")
        router, _spy = _build_router_with_spy(
            writer=writer,
            capability="flow.capital_flow_daily",
            security_id=sid,
        )

        result = router.query(
            domain="flow",
            operation="capital_flow_daily",
            security_id=sid,
        )

        # Trace must contain the (ok) marker exactly once, no miss /
        # skip / error noise. The router only consulted the writer.
        trace_str = " | ".join(result.source_trace)
        assert "ud_materialized(ok)" in trace_str
        assert "ud_materialized(miss)" not in trace_str
        assert "ud_materialized(error" not in trace_str
        assert "ud_materialized(skipped" not in trace_str

    def test_materialized_miss_emits_miss_not_ok(self):
        """Empty writer → ``ud_materialized(miss)`` → fallback chain."""
        writer = _make_writer()
        sid = SecurityId(market=Market.CN, symbol="600519")
        registry = ProviderRegistry()
        spy = FakeProvider(
            name="flow_fallback_spy",
            payload={"row": "fallback-fired"},
            capabilities={"flow.capital_flow_daily"},
            markets={sid.market},
        )
        registry.register(spy)
        router = DataRouter(registry=registry, p3_writer=writer)

        result = router.query(
            domain="flow",
            operation="capital_flow_daily",
            security_id=sid,
        )

        # No row in writer → Step 2 miss → Step 4 external chain.
        assert result.provider == "flow_fallback_spy"
        assert len(spy.call_log) == 1
        # Trace records the miss (not the ok).
        assert "ud_materialized(miss)" in result.source_trace


# ---------------------------------------------------------------------------
# F4 amendment — materialized-read filter must isolate by market/date
# ---------------------------------------------------------------------------


class TestMaterializedReadMarketDateIsolation:
    """F4 amendment (SPEC-03-014-F4 §5.1 C-3 / C-4 / C-5; RFC-03-014-F4).

    The ``sentiment.limit_up_pool`` materialized-read filter must
    include ``market`` so a same-day CN query does not leak records
    belonging to other markets (HK / US / INDEX). The same
    isolation must apply to ``trade_date``: a query for
    2026-07-21 must not return records from 2026-07-22. The
    dual-capability coexistence (C-5) — ``sentiment.market_snapshot``
    and ``sentiment.limit_up_pool`` share a collection but use
    different business keys — must continue to work after the filter
    gains a ``market`` field.
    """

    def test_cross_market_query_returns_only_target_market_rows(self):
        """CN query MUST NOT return HK / US / INDEX rows (C-3).

        Three pools are upserted into the same collection with
        distinct ``market`` values. A CN/date query returns only the
        CN rows; HK/US/INDEX records are filtered out at the
        materialized-read layer.
        """
        writer = _make_writer()
        base_record = {
            "symbol": "limit_up_placeholder",
            "trade_date": "2026-07-21",
            "status": "limit_up",
            "limit_up_time": "09:30:05",
            "last_price": 100.0,
            "pct_chg": 10.0,
            "provider": "stub",
        }
        cn_record = {**base_record, "market": "CN", "symbol": "600519"}
        hk_record = {**base_record, "market": "HK", "symbol": "00700"}
        us_record = {**base_record, "market": "US", "symbol": "AAPL"}
        # Use the INDEX placeholder security_id semantics so the
        # writer business-key collision is forced to be
        # distinguished only by ``market``.
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[cn_record, hk_record, us_record],
            unique_key=LIMIT_UP_POOL_UNIQUE_KEY,
        )

        sid = SecurityId(
            market=Market.INDEX, symbol="limit_up_pool:2026-07-21"
        )
        router, spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.limit_up_pool",
            security_id=sid,
        )

        result = router.query(
            domain="sentiment",
            operation="limit_up_pool",
            security_id=sid,
            market="CN",
            params={"trade_date": "2026-07-21"},
        )

        # Hit the writer — and ONLY the CN rows come back.
        assert result.provider == "ud_materialized"
        assert "ud_materialized(ok)" in result.source_trace
        assert len(spy.call_log) == 0, (
            "external fallback chain must NOT fire; writer has CN row"
        )
        assert isinstance(result.data, list)
        markets_returned = {row["market"] for row in result.data}
        symbols_returned = {row["symbol"] for row in result.data}
        assert markets_returned == {"CN"}, (
            f"filter leaked cross-market rows: got markets={markets_returned}"
        )
        assert symbols_returned == {"600519"}, (
            f"filter leaked HK/US symbols: got symbols={symbols_returned}"
        )

    def test_cross_date_query_returns_only_target_date_rows(self):
        """Date filter MUST isolate by ``trade_date`` (C-4)."""
        writer = _make_writer()
        record_2026_07_21 = {
            "market": "CN",
            "symbol": "600519",
            "trade_date": "2026-07-21",
            "status": "limit_up",
            "limit_up_time": "09:30:05",
            "last_price": 100.0,
            "pct_chg": 10.0,
            "provider": "stub",
        }
        record_2026_07_22 = {
            "market": "CN",
            "symbol": "600519",
            "trade_date": "2026-07-22",
            "status": "limit_up",
            "limit_up_time": "09:30:05",
            "last_price": 101.0,
            "pct_chg": 10.0,
            "provider": "stub",
        }
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[record_2026_07_21, record_2026_07_22],
            unique_key=LIMIT_UP_POOL_UNIQUE_KEY,
        )

        sid = SecurityId(
            market=Market.INDEX, symbol="limit_up_pool:2026-07-21"
        )
        router, spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.limit_up_pool",
            security_id=sid,
        )

        result = router.query(
            domain="sentiment",
            operation="limit_up_pool",
            security_id=sid,
            market="CN",
            params={"trade_date": "2026-07-21"},
        )

        assert result.provider == "ud_materialized"
        assert len(spy.call_log) == 0
        assert isinstance(result.data, list)
        dates_returned = {row["trade_date"] for row in result.data}
        assert dates_returned == {"2026-07-21"}, (
            f"filter leaked cross-date rows: got dates={dates_returned}"
        )

    def test_market_snapshot_and_limit_up_pool_dual_key_coexistence(self):
        """Two capabilities sharing one collection must coexist (C-5).

        ``sentiment.market_snapshot`` keys by
        ``{market, snapshot_date, snapshot_time}`` while
        ``sentiment.limit_up_pool`` keys by
        ``{market, symbol, trade_date}``. After F4, both filters
        carry ``market`` — proving the new filter shape does not
        break the dual-capability contract.
        """
        writer = _make_writer()
        # market_snapshot row keyed by snapshot_date / snapshot_time
        market_snapshot_row = {
            "market": "CN",
            "snapshot_date": "2026-07-21",
            "snapshot_time": "15:00:00",
            "pct_chg": 1.5,
            "provider": "snapshot_stub",
        }
        # limit_up_pool row keyed by symbol / trade_date (same date)
        limit_up_pool_row = {
            "market": "CN",
            "symbol": "600519",
            "trade_date": "2026-07-21",
            "status": "limit_up",
            "limit_up_time": "09:30:05",
            "last_price": 150.25,
            "pct_chg": 10.0,
            "provider": "limit_up_stub",
        }
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[market_snapshot_row],
            unique_key=SENTIMENT_UNIQUE_KEY,
        )
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[limit_up_pool_row],
            unique_key=LIMIT_UP_POOL_UNIQUE_KEY,
        )

        # ---- market_snapshot read: filter is {market, snapshot_date,
        # snapshot_time}; must NOT return the limit_up_pool row.
        ms_sid = SecurityId(market=Market.CN, symbol="600519")
        ms_router, ms_spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.market_snapshot",
            security_id=ms_sid,
        )
        ms_result = ms_router.query(
            domain="sentiment",
            operation="market_snapshot",
            security_id=ms_sid,
            market="CN",
            params={"snapshot_date": "2026-07-21"},
        )
        assert ms_result.provider == "ud_materialized"
        assert len(ms_spy.call_log) == 0
        assert isinstance(ms_result.data, list)
        assert len(ms_result.data) == 1
        assert ms_result.data[0].get("snapshot_time") == "15:00:00"
        assert "symbol" not in ms_result.data[0], (
            "market_snapshot read leaked limit_up_pool row by symbol"
        )

        # ---- limit_up_pool read: filter is {market, trade_date}; must
        # NOT return the market_snapshot row.
        lup_sid = SecurityId(
            market=Market.INDEX, symbol="limit_up_pool:2026-07-21"
        )
        lup_router, lup_spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.limit_up_pool",
            security_id=lup_sid,
        )
        lup_result = lup_router.query(
            domain="sentiment",
            operation="limit_up_pool",
            security_id=lup_sid,
            market="CN",
            params={"trade_date": "2026-07-21"},
        )
        assert lup_result.provider == "ud_materialized"
        assert len(lup_spy.call_log) == 0
        assert isinstance(lup_result.data, list)
        assert len(lup_result.data) == 1
        assert lup_result.data[0].get("symbol") == "600519"
        assert "snapshot_time" not in lup_result.data[0], (
            "limit_up_pool read leaked market_snapshot row by snapshot_time"
        )

    def test_writer_receives_market_in_filter_on_limit_up_pool(self):
        """Spy on ``writer.get`` to assert the filter carries ``market``.

        SPEC-03-014-F4 §5.1 C-1 / §5.3 — the writer is called with
        ``filter={"market": "CN", "trade_date": "..."}`` rather than
        ``{"trade_date": "..."}`` alone. Captures the call directly.
        """
        writer = _make_writer()
        record = {
            "market": "CN",
            "symbol": "600519",
            "trade_date": "2026-07-21",
            "status": "limit_up",
            "limit_up_time": "09:30:05",
            "last_price": 100.0,
            "pct_chg": 10.0,
            "provider": "stub",
        }
        writer.upsert(
            collection=SENTIMENT_COLLECTION,
            records=[record],
            unique_key=LIMIT_UP_POOL_UNIQUE_KEY,
        )

        # Capture the filter passed to ``writer.get``.
        captured: dict[str, Any] = {}

        original_get = writer.get

        def capture_get(collection, filter_, *args, **kwargs):
            captured["collection"] = collection
            captured["filter"] = dict(filter_)
            return original_get(collection, filter_, *args, **kwargs)

        writer.get = capture_get  # type: ignore[method-assign]

        sid = SecurityId(
            market=Market.INDEX, symbol="limit_up_pool:2026-07-21"
        )
        router, _spy = _build_router_with_spy(
            writer=writer,
            capability="sentiment.limit_up_pool",
            security_id=sid,
        )

        result = router.query(
            domain="sentiment",
            operation="limit_up_pool",
            security_id=sid,
            market="CN",
            params={"trade_date": "2026-07-21"},
        )

        # End-to-end: writer was consulted with the right filter.
        assert result.provider == "ud_materialized"
        assert captured["collection"] == SENTIMENT_COLLECTION
        assert captured["filter"] == {
            "market": "CN",
            "trade_date": "2026-07-21",
        }, (
            f"writer received unexpected filter: {captured['filter']!r}; "
            "F4 requires market to be present"
        )
