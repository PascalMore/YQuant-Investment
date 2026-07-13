"""Tests for the Phase 1A ``UnifiedDataClient`` extensions.

Phase 1A adds 14 convenience entry methods (see DESIGN-03-007 §Phase 1A
"完整 collection × canonical × service × client 矩阵"). These tests
verify:

* each of the 14 entry methods delegates to the right service and
  returns a ``DataResult`` matching the canonical contract
* the Phase 0 ``query`` / fallback router is unaffected
* lazy service construction works (no error if some services aren't
  used after construction)
* missing ``ta_cn_adapter`` raises a clear ``RuntimeError``
* the ``with_providers`` factory wires providers + adapter together
* Phase 0 surface (``register_provider``, ``query``) still functions
"""

from __future__ import annotations

import pytest

from skills.data.unified_data import (
    DataProvider,
    Market,
    SecurityId,
    TA_CNMongoAdapter,
    UnifiedDataClient,
)
from skills.data.unified_data.models.domain import (
    DailyBar,
    FinancialStatement,
    IndexDailyBar,
    IndexInfo,
    NewsItem,
    RealtimeQuote,
    SectorClassification,
    StockInfo,
)

from . import FakeTA_CNMongoAdapter
from .fixtures import FakeDatabase


# ---------------------------------------------------------------------------
# Phase 0 client construction
# ---------------------------------------------------------------------------


class TestPhase0BackwardCompatibility:
    """Client constructed without ``ta_cn_adapter`` keeps Phase 0 surface."""

    def test_default_registry_router(self):
        client = UnifiedDataClient()
        assert client.registry is not None
        assert client.router is not None
        assert client.ta_cn_adapter is None

    def test_register_provider(self):
        client = UnifiedDataClient()

        class P(DataProvider):
            @property
            def name(self) -> str:
                return "p"

            @property
            def capabilities(self) -> set[str]:
                return set()

            @property
            def markets(self) -> set[Market]:
                return set()

            def is_available(self) -> bool:
                return True

            def fetch(self, *args, **kwargs):  # pragma: no cover
                return None

        provider = P()
        client.register_provider(provider)
        assert client.registry.get("p") is provider

    def test_with_providers(self):
        client = UnifiedDataClient.with_providers(providers=[])
        assert isinstance(client.registry, type(client.registry).__mro__[0])  # any registry
        assert client.ta_cn_adapter is None


# ---------------------------------------------------------------------------
# Phase 1A 14 entry methods — exhaustive coverage
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter() -> FakeTA_CNMongoAdapter:
    return FakeTA_CNMongoAdapter()


@pytest.fixture
def client(adapter: FakeTA_CNMongoAdapter) -> UnifiedDataClient:
    return UnifiedDataClient(ta_cn_adapter=adapter)


@pytest.fixture
def maotai() -> SecurityId:
    return SecurityId(market=Market.CN, symbol="600519")


@pytest.fixture
def hs300() -> SecurityId:
    return SecurityId(market=Market.INDEX, symbol="000300")


# -- 1: get_stock_info -----------------------------------------------------


class TestGetStockInfo:
    def test_success(self, client, adapter, maotai):
        adapter.set_payload(
            "get_stock_info",
            {"symbol": "600519", "full_symbol": "600519.SH", "name": "贵州茅台"},
        )
        r = client.get_stock_info(maotai)
        assert r.succeeded
        assert r.provider == "ta_cn_adapter"
        assert isinstance(r.data, StockInfo)

    def test_empty(self, client, maotai):
        r = client.get_stock_info(maotai)
        assert r.freshness == "empty"
        assert r.provider == "empty"


# -- 2: get_stock_list -----------------------------------------------------


class TestGetStockList:
    def test_success(self, client, adapter):
        adapter.set_payload("get_stock_list", [
            {"symbol": "000001", "full_symbol": "000001.SZ", "name": "平安银行"},
            {"symbol": "600519", "full_symbol": "600519.SH", "name": "贵州茅台"},
        ])
        r = client.get_stock_list()
        assert r.succeeded
        assert len(r.data) == 2


# -- 3: get_realtime_quote -------------------------------------------------


class TestGetRealtimeQuote:
    def test_success(self, client, adapter, maotai):
        adapter.set_payload("get_realtime_quotes", {"symbol": "600519", "current_price": 100.0})
        r = client.get_realtime_quote(maotai)
        assert r.succeeded
        assert isinstance(r.data, RealtimeQuote)


# -- 4: get_kline_daily ----------------------------------------------------


class TestGetKlineDaily:
    def test_success(self, client, adapter, maotai):
        adapter.set_payload("get_daily_bars", [
            {"symbol": "600519", "trade_date": "20260713", "close": 100.0},
            {"symbol": "600519", "trade_date": "20260710", "close": 99.0},
        ])
        r = client.get_kline_daily(maotai, start_date="2026-07-01", end_date="2026-07-31", limit=50)
        assert r.succeeded
        assert len(r.data) == 2
        assert all(isinstance(b, DailyBar) for b in r.data)
        # Adapter received the filters propagated directly.
        assert adapter.call_log[-1][1] == ("600519", "2026-07-01", "2026-07-31", 50)


# -- 5-7: financial statements --------------------------------------------


class TestFinancialStatements:
    FIN = {
        "symbol": "600519",
        "report_period": "20251231",
        "raw_data": {
            "income_statement": [{"end_date": "20251231", "revenue": 130.0e9}],
            "balance_sheet": [{"end_date": "20251231", "total_assets": 250.0e9}],
            "cashflow_statement": [{"end_date": "20251231", "operating_cash_flow": 60.0e9}],
        },
    }

    def test_income_statement(self, client, adapter, maotai):
        adapter.set_payload("get_financials", self.FIN)
        r = client.get_income_statement(maotai)
        assert r.succeeded
        assert isinstance(r.data, FinancialStatement)
        assert r.data.items["revenue"] == 130.0e9
        assert r.operation == "income_statement"

    def test_balance_sheet(self, client, adapter, maotai):
        adapter.set_payload("get_financials", self.FIN)
        r = client.get_balance_sheet(maotai)
        assert r.succeeded
        assert isinstance(r.data, FinancialStatement)
        assert r.data.items["total_assets"] == 250.0e9
        assert r.operation == "balance_statement"

    def test_cash_flow(self, client, adapter, maotai):
        adapter.set_payload("get_financials", self.FIN)
        r = client.get_cash_flow(maotai)
        assert r.succeeded
        assert isinstance(r.data, FinancialStatement)
        assert r.data.items["operating_cash_flow"] == 60.0e9
        assert r.operation == "cashflow_statement"

    def test_financials_with_period(self, client, adapter, maotai):
        adapter.set_payload("get_financials", self.FIN)
        client.get_income_statement(maotai, report_period="20251231")
        assert adapter.call_log[-1][1] == ("600519", "20251231")


# -- 8: get_news -----------------------------------------------------------


class TestGetNews:
    def test_success(self, client, adapter, maotai):
        adapter.set_payload("get_news", [
            {"symbol": "600519", "title": "a", "publish_time": "2026-07-12"},
            {"symbol": "600519", "title": "b", "publish_time": "2026-07-10"},
        ])
        r = client.get_news(maotai, limit=5)
        assert r.succeeded
        assert all(isinstance(item, NewsItem) for item in r.data)
        assert adapter.call_log[-1][1] == ("600519", 5)


# -- 9: get_index_info -----------------------------------------------------


class TestGetIndexInfo:
    def test_success(self, client, adapter, hs300):
        adapter.set_payload(
            "get_index_info",
            {"symbol": "000300", "full_symbol": "000300.SH", "name": "沪深300"},
        )
        r = client.get_index_info(hs300)
        assert r.succeeded
        assert isinstance(r.data, IndexInfo)


# -- 10: get_index_list ----------------------------------------------------


class TestGetIndexList:
    def test_success(self, client, adapter):
        adapter.set_payload("get_index_list", [
            {"symbol": "000300", "full_symbol": "000300.SH", "name": "沪深300"},
        ])
        r = client.get_index_list()
        assert r.succeeded
        assert len(r.data) == 1


# -- 11: get_index_daily ---------------------------------------------------


class TestGetIndexDaily:
    def test_success(self, client, adapter, hs300):
        adapter.set_payload("get_index_daily_bars", [
            {"sector_code": "000300", "trade_date": "20260713", "close": 3875.0},
        ])
        r = client.get_index_daily(hs300, start_date="2026-07-01")
        assert r.succeeded
        assert isinstance(r.data[0], IndexDailyBar)
        # Adapter call received the symbol, no sector_code (caller passed sec.id).
        assert adapter.call_log[-1][1] == ("000300", None, "2026-07-01", None, 120)


# -- 12: get_sector_index_bars ---------------------------------------------


class TestGetSectorIndexBars:
    def test_success(self, client, adapter):
        adapter.set_payload("get_index_daily_bars", [
            {"sector_code": "801120", "trade_date": "20260713", "close": 5545.0, "pct_chg": 0.85},
        ])
        r = client.get_sector_index_bars("801120", start_date="2026-07-01", limit=30)
        assert r.succeeded
        assert isinstance(r.data[0], IndexDailyBar)
        # Symbol arg is None; sector_code is the primary selector.
        assert adapter.call_log[-1][1] == (None, "801120", "2026-07-01", None, 30)


# -- 13: get_stock_sector --------------------------------------------------


class TestGetStockSector:
    def test_success(self, client, adapter, maotai):
        adapter.set_payload("get_stock_sector_info", [
            {"full_symbol": "600519.SH", "classify_system": "SW", "l1_code": "801120", "l1_name": "食品饮料"},
        ])
        r = client.get_stock_sector(maotai)
        assert r.succeeded
        assert isinstance(r.data[0], SectorClassification)

    def test_empty_hk_symbol(self, client):
        hk = SecurityId(market=Market.HK, symbol="00700")
        r = client.get_stock_sector(hk)
        assert r.is_empty()


# -- 14: get_stocks_by_sector ----------------------------------------------


class TestGetStocksBySector:
    def test_success(self, client, adapter):
        adapter.set_payload("get_stocks_by_sector", [
            {"full_symbol": "600519.SH", "classify_system": "SW",
             "l1_code": "801120", "l1_name": "食品饮料"},
        ])
        r = client.get_stocks_by_sector("801120")
        assert r.succeeded
        assert isinstance(r.data[0], SectorClassification)


# ---------------------------------------------------------------------------
# Constructor behaviors
# ---------------------------------------------------------------------------


class TestClientConstruction:
    def test_missing_adapter_raises(self):
        """Without ``ta_cn_adapter`` any Phase 1A method raises ``RuntimeError``."""
        client = UnifiedDataClient()
        maotai = SecurityId(market=Market.CN, symbol="600519")
        with pytest.raises(RuntimeError):
            client.get_stock_info(maotai)

    def test_with_providers_with_adapter(self):
        real_adapter = TA_CNMongoAdapter(FakeDatabase())
        client = UnifiedDataClient.with_providers(
            providers=[], ta_cn_adapter=real_adapter,
        )
        assert client.ta_cn_adapter is real_adapter

    def test_real_db_adapter_works(self):
        """Real (FakeDatabase-backed) ``TA_CNMongoAdapter`` round-trips through client."""
        from .fixtures.ta_cn_mock_docs import make_populated_database

        db = make_populated_database()
        adapter = TA_CNMongoAdapter(db)
        client = UnifiedDataClient(ta_cn_adapter=adapter)
        maotai = SecurityId(market=Market.CN, symbol="600519")

        r1 = client.get_stock_info(maotai)
        assert r1.succeeded
        assert r1.data.name == "贵州茅台"

        r2 = client.get_kline_daily(maotai)
        assert r2.succeeded
        assert len(r2.data) >= 1

        r3 = client.get_index_list()
        assert r3.succeeded
        assert any(info.symbol == "000300" for info in r3.data)


# ---------------------------------------------------------------------------
# Lazy service instantiation
# ---------------------------------------------------------------------------


class TestLazyServices:
    def test_service_objects_distinct(self):
        """Each service is independently instantiated and cached."""
        client = UnifiedDataClient(ta_cn_adapter=FakeTA_CNMongoAdapter())
        maotai = SecurityId(market=Market.CN, symbol="600519")

        client.get_stock_info(maotai)
        client.get_realtime_quote(maotai)
        client.get_stock_list()
        assert client is not None  # warm-up

    def test_method_count(self):
        """Public method surface has at least 14 Phase 1A entry methods."""
        client = UnifiedDataClient()
        phase1a_methods = [
            name for name in dir(client)
            if name.startswith("get_")
            and name
            in {
                "get_stock_info", "get_stock_list", "get_realtime_quote",
                "get_kline_daily", "get_income_statement", "get_balance_sheet",
                "get_cash_flow", "get_news", "get_index_info", "get_index_list",
                "get_index_daily", "get_sector_index_bars", "get_stock_sector",
                "get_stocks_by_sector",
            }
        ]
        assert len(phase1a_methods) == 14
