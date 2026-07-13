"""Tests for TA_CNMongoAdapter.

Phase 1A acceptance targets:
    * 12 read methods cover 8 TA-CN collections and return raw documents
    * Date inputs ``YYYY-MM-DD`` ↔ ``YYYYMMDD`` round-trip
    * Empty results / missing collections return ``None`` / ``[]``
    * Constructor does not auto-create collections or indexes
    * Sort orders match the Phase 1A matrix

All tests run against an in-memory :class:`FakeDatabase` from
``tests.data.unified_data.fixtures.fake_mongo`` — no network, no real
MongoDB.
"""

from __future__ import annotations

import pytest

from skills.data.unified_data import TA_CNMongoAdapter
from skills.data.unified_data.adapters import ta_cn_mongo_adapter as adapter_module

from .fixtures import FakeDatabase
from .fixtures.ta_cn_mock_docs import (
    INDEX_BASIC_INFO_HS300,
    INDEX_DAILY_QUOTES_HS300,
    MARKET_QUOTES_MAOTAI,
    STOCK_BASIC_INFO_MAOTAI,
    STOCK_BASIC_INFO_PINGAN,
    STOCK_DAILY_QUOTES_MAOTAI,
    STOCK_NEWS_MAOTAI,
    STOCK_SECTOR_INFO_MAOTAI,
    make_populated_database,
    stock_financial_data_maotai,
    stock_sector_maotai_alt_system,
    stock_sector_pingan,
    sw_industry_daily_quotes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db() -> FakeDatabase:
    return make_populated_database()


@pytest.fixture
def adapter(db: FakeDatabase) -> TA_CNMongoAdapter:
    return TA_CNMongoAdapter(db)


@pytest.fixture
def empty_adapter() -> TA_CNMongoAdapter:
    return TA_CNMongoAdapter(FakeDatabase())


# ---------------------------------------------------------------------------
# Construction contract
# ---------------------------------------------------------------------------


class TestAdapterConstruction:
    def test_database_name_constant(self):
        assert TA_CNMongoAdapter.DATABASE_NAME == "tradingagents"

    def test_collection_name_constants(self):
        expected = {
            "COLLECTION_STOCK_BASIC_INFO": "stock_basic_info",
            "COLLECTION_MARKET_QUOTES": "market_quotes",
            "COLLECTION_STOCK_DAILY_QUOTES": "stock_daily_quotes",
            "COLLECTION_STOCK_FINANCIAL_DATA": "stock_financial_data",
            "COLLECTION_STOCK_NEWS": "stock_news",
            "COLLECTION_INDEX_BASIC_INFO": "index_basic_info",
            "COLLECTION_INDEX_DAILY_QUOTES": "index_daily_quotes",
            "COLLECTION_STOCK_SECTOR_INFO": "stock_sector_info",
        }
        actual = {
            name: value
            for name, value in vars(TA_CNMongoAdapter).items()
            if name.startswith("COLLECTION_")
        }
        assert actual == expected

    def test_does_not_create_collections_or_indexes(self):
        class ReadOnlyCollection:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def find_one(self, query):
                self.calls.append("find_one")
                return None

            def find(self, query):
                self.calls.append("find")
                return FakeDatabase()["empty"].find({})

        class ReadOnlyDatabase:
            def __init__(self) -> None:
                self.collections: dict[str, ReadOnlyCollection] = {}
                self.created = False

            def __getitem__(self, name):
                return self.collections.setdefault(name, ReadOnlyCollection())

            def create_collection(self, *args, **kwargs):
                self.created = True
                raise AssertionError("adapter must not create collections")

        db = ReadOnlyDatabase()
        adapter = TA_CNMongoAdapter(db)
        adapter.get_stock_info("600519")
        adapter.get_stock_list()
        adapter.get_realtime_quotes("600519")
        adapter.get_daily_bars("600519")
        adapter.get_financials("600519")
        adapter.get_news("600519")
        adapter.get_index_info("000300")
        adapter.get_index_list()
        adapter.get_index_daily_bars(symbol="000300")
        adapter.get_stock_sector_info("600519.SH")
        adapter.get_stocks_by_sector("801120")

        assert not db.created
        assert db.collections
        assert all(
            set(collection.calls) <= {"find", "find_one"}
            for collection in db.collections.values()
        )

    def test_module_does_not_export_write_helpers(self):
        forbidden = {
            "insert", "update", "delete", "replace_one", "create_index",
            "create_collection", "drop", "bulk_write",
        }
        exported = set(getattr(adapter_module, "__all__", [])) | set(
            name for name in vars(adapter_module.TA_CNMongoAdapter)
            if not name.startswith("_")
        )
        assert forbidden.isdisjoint(exported)


# ---------------------------------------------------------------------------
# stock_basic_info
# ---------------------------------------------------------------------------


class TestStockBasicInfo:
    def test_get_stock_info(self, adapter):
        doc = adapter.get_stock_info("600519")
        assert doc is not None
        assert doc["symbol"] == "600519"
        assert doc["name"] == "贵州茅台"

    def test_get_stock_info_respects_market(self, adapter):
        assert adapter.get_stock_info("600519", market="CN") is not None
        assert adapter.get_stock_info("600519", market="US") is None

    def test_get_stock_info_empty(self, adapter, db):
        # Drop the only matching doc.
        db["stock_basic_info"]._docs.clear()
        assert adapter.get_stock_info("600519") is None

    def test_get_stock_info_empty_symbol(self, adapter):
        assert adapter.get_stock_info("") is None
        assert adapter.get_stock_info(None) is None

    def test_get_stock_list_default(self, adapter):
        result = adapter.get_stock_list()
        symbols = [doc["symbol"] for doc in result]
        # Ascending by symbol per Phase 1A spec.
        assert symbols == sorted(symbols)
        assert "600519" in symbols
        assert "000001" in symbols

    def test_get_stock_list_filter_status(self, adapter):
        # All fixture docs have status="L"; ask for status="D" → empty.
        assert adapter.get_stock_list(status="D") == []

    def test_get_stock_list_with_limit(self, adapter):
        result = adapter.get_stock_list(limit=2)
        assert len(result) == 2

    def test_get_stock_list_empty_status_no_filter(self, adapter):
        # status="" disables the filter and returns everything.
        result = adapter.get_stock_list(status="")
        assert len(result) >= 3


# ---------------------------------------------------------------------------
# market_quotes
# ---------------------------------------------------------------------------


class TestMarketQuotes:
    def test_get_realtime_quotes(self, adapter):
        doc = adapter.get_realtime_quotes("600519")
        assert doc is not None
        assert doc["current_price"] == 1950.50

    def test_get_realtime_quotes_empty(self, adapter):
        assert adapter.get_realtime_quotes("999999") is None

    def test_get_realtime_quotes_empty_symbol(self, adapter):
        assert adapter.get_realtime_quotes("") is None
        assert adapter.get_realtime_quotes(None) is None


# ---------------------------------------------------------------------------
# stock_daily_quotes
# ---------------------------------------------------------------------------


class TestStockDailyQuotes:
    def test_get_daily_bars_returns_all_for_symbol(self, adapter):
        result = adapter.get_daily_bars("600519")
        dates = [doc["trade_date"] for doc in result]
        # Descending per Phase 1A spec.
        assert dates == sorted(dates, reverse=True)
        assert len(result) == len(STOCK_DAILY_QUOTES_MAOTAI)

    def test_get_daily_bars_default_limit(self, adapter):
        result = adapter.get_daily_bars("600519")
        assert isinstance(result, list)

    def test_get_daily_bars_custom_limit(self, adapter):
        result = adapter.get_daily_bars("600519", limit=1)
        assert len(result) == 1

    def test_get_daily_bars_date_range_yyyymm_dash(self, adapter):
        result = adapter.get_daily_bars("600519", start_date="2026-07-11", end_date="2026-07-13")
        dates = [doc["trade_date"] for doc in result]
        assert dates == ["20260713", "20260711"]

    @pytest.mark.parametrize(
        "field,value",
        [
            ("start_date", "20260711"),
            ("start_date", "2026/07/11"),
            ("start_date", "2026-02-30"),
            ("end_date", "2026-7-11"),
        ],
    )
    def test_get_daily_bars_rejects_noncanonical_dates(self, adapter, field, value):
        with pytest.raises(ValueError, match=field):
            adapter.get_daily_bars("600519", **{field: value})

    def test_get_daily_bars_unknown_symbol(self, adapter):
        assert adapter.get_daily_bars("000000") == []

    @pytest.mark.parametrize("limit", [-1, 1.5, "10", True])
    def test_get_daily_bars_rejects_invalid_limit(self, adapter, limit):
        with pytest.raises(ValueError, match="limit"):
            adapter.get_daily_bars("600519", limit=limit)


# ---------------------------------------------------------------------------
# stock_financial_data
# ---------------------------------------------------------------------------


class TestStockFinancialData:
    def test_get_financials(self, adapter):
        doc = adapter.get_financials("600519")
        assert doc is not None
        assert doc["symbol"] == "600519"
        assert "raw_data" in doc
        assert "income_statement" in doc["raw_data"]

    def test_get_financials_with_period(self, adapter):
        doc = adapter.get_financials("600519", report_period="20251231")
        assert doc is not None
        assert doc["report_period"] == "20251231"

    def test_get_financials_wrong_period(self, adapter):
        assert adapter.get_financials("600519", report_period="20240601") is None

    @pytest.mark.parametrize(
        "period", ["2025-12-31", "20251301", "20250230", 20251231]
    )
    def test_get_financials_rejects_invalid_report_period(self, adapter, period):
        with pytest.raises(ValueError, match="report_period"):
            adapter.get_financials("600519", report_period=period)

    def test_get_financials_empty(self, adapter):
        assert adapter.get_financials("999999") is None

    def test_get_financials_empty_symbol(self, adapter):
        assert adapter.get_financials("") is None


# ---------------------------------------------------------------------------
# stock_news
# ---------------------------------------------------------------------------


class TestStockNews:
    def test_get_news_descending(self, adapter):
        docs = adapter.get_news("600519")
        times = [doc["publish_time"] for doc in docs]
        assert times == sorted(times, reverse=True)

    def test_get_news_limit(self, adapter):
        docs = adapter.get_news("600519", limit=1)
        assert len(docs) == 1

    def test_get_news_default_limit(self, adapter):
        docs = adapter.get_news("600519")
        assert len(docs) <= 20

    def test_get_news_unknown_symbol(self, adapter):
        assert adapter.get_news("999999") == []


# ---------------------------------------------------------------------------
# index_basic_info
# ---------------------------------------------------------------------------


class TestIndexBasicInfo:
    def test_get_index_info(self, adapter):
        doc = adapter.get_index_info("000300")
        assert doc["name"] == INDEX_BASIC_INFO_HS300["name"]

    def test_get_index_info_missing(self, adapter):
        assert adapter.get_index_info("999999") is None

    def test_get_index_list(self, adapter):
        result = adapter.get_index_list()
        codes = [doc["symbol"] for doc in result]
        assert "000300" in codes
        assert "000905" in codes

    def test_get_index_list_empty_symbol(self, adapter):
        assert adapter.get_index_info("") is None
        assert adapter.get_index_info(None) is None


# ---------------------------------------------------------------------------
# index_daily_quotes
# ---------------------------------------------------------------------------


class TestIndexDailyQuotes:
    def test_get_index_daily_bars_by_sector_code(self, adapter):
        docs = adapter.get_index_daily_bars(sector_code="000300")
        assert all(doc["sector_code"] == "000300" for doc in docs)
        # Descending by trade_date.
        dates = [doc["trade_date"] for doc in docs]
        assert dates == sorted(dates, reverse=True)

    def test_get_index_daily_bars_by_symbol_with_sector_code_match(self, adapter):
        docs = adapter.get_index_daily_bars(symbol="000300")
        assert len(docs) == 2

    def test_get_index_daily_bars_sw_industry(self, adapter):
        docs = adapter.get_index_daily_bars(sector_code="801120")
        assert len(docs) == 1
        assert docs[0]["source"] == "sw"

    @pytest.mark.parametrize("alias", ["code", "symbol"])
    def test_get_index_daily_bars_sector_code_supports_aliases(
        self, adapter, db, alias
    ):
        db["index_daily_quotes"].add(
            {alias: "801999", "trade_date": "20260713", "close": 123.0}
        )
        docs = adapter.get_index_daily_bars(sector_code="801999")
        assert len(docs) == 1
        assert docs[0][alias] == "801999"

    def test_get_index_daily_bars_date_range(self, adapter):
        docs = adapter.get_index_daily_bars(sector_code="000300", start_date="2026-07-13")
        dates = [doc["trade_date"] for doc in docs]
        assert dates == ["20260713"]

    def test_get_index_daily_bars_unknown_sector(self, adapter):
        assert adapter.get_index_daily_bars(sector_code="999999") == []


# ---------------------------------------------------------------------------
# stock_sector_info
# ---------------------------------------------------------------------------


class TestStockSectorInfo:
    def test_get_stock_sector_info_default_system(self, adapter):
        docs = adapter.get_stock_sector_info("600519.SH")
        # Two classification systems exist for Maotai in fixtures.
        assert len(docs) == 2
        codes = [doc["l1_code"] for doc in docs]
        assert "801120" in codes

    def test_get_stock_sector_info_filter_system(self, adapter):
        docs = adapter.get_stock_sector_info("600519.SH", classify_system="SW")
        assert len(docs) == 1
        assert docs[0]["l1_code"] == "801120"

    def test_get_stock_sector_info_empty_full_symbol(self, adapter):
        assert adapter.get_stock_sector_info("") == []
        assert adapter.get_stock_sector_info(None) == []

    def test_get_stock_sector_info_nonexistent(self, adapter):
        assert adapter.get_stock_sector_info("999999.SH") == []

    def test_get_stocks_by_sector(self, adapter):
        # Both Maotai and Pingan belong to two different L1 sectors; only
        # Maotai belongs to 801120 in the SW classification.
        result = adapter.get_stocks_by_sector("801120")
        full_symbols = [doc["full_symbol"] for doc in result]
        assert "600519.SH" in full_symbols

    def test_get_stocks_by_sector_empty_code(self, adapter):
        assert adapter.get_stocks_by_sector("") == []
