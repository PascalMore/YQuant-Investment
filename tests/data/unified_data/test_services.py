"""Tests for Phase 1A domain services.

Each service is exercised with a :class:`FakeTA_CNMongoAdapter` that
returns either a configured payload, ``None`` / ``[]`` or a raised
exception. The expected ``DataResult`` shape is checked against the
Phase 0 contract (provider / freshness / source_trace).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from skills.data.unified_data import (
    Market,
    ProviderError,
    SecurityId,
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
from skills.data.unified_data.services import (
    EventService,
    FundamentalService,
    MarketDataService,
    MetadataService,
    SectorService,
)

class FakeTA_CNMongoAdapter:
    """Local fake TA-CN adapter for service tests.

    Tests can configure per-method return values via ``set_payload`` /
    ``set_response`` and raise behavior via ``set_exception``. The
    ``call_log`` records every method invocation for assertion.
    No real MongoDB.
    """

    def __init__(self) -> None:
        self._responses: dict[str, object] = {}
        self._exceptions: dict[str, BaseException] = {}
        self.call_log: list[tuple[str, tuple]] = []

    def set_payload(self, method: str, payload: object) -> None:
        self._responses[method] = payload

    def set_response(self, method: str, payload: object) -> None:
        self._responses[method] = payload

    def set_exception(self, method: str, exc: BaseException) -> None:
        self._exceptions[method] = exc

    def set_error(self, method: str, exc: BaseException) -> None:
        self._exceptions[method] = exc

    def _call(self, method: str, *args, **kwargs):
        # Tests inspect call_log[-1] as (name, args). Merge kwargs into
        # args so callers can reconstruct both.
        if kwargs:
            self.call_log.append((method, args + (kwargs,)))
        else:
            self.call_log.append((method, args))
        if method in self._exceptions:
            raise self._exceptions[method]
        if method not in self._responses:
            return None
        return self._responses[method]

    # The adapter methods (signatures only; tests inject payloads).
    # Services call adapter synchronously, so the fake must be sync too.
    # Method names mirror the real TA_CNMongoAdapter.
    def get_stock_info(self, *args, **kwargs):
        return self._call("get_stock_info", *args, **kwargs)

    def get_stock_list(self, *args, **kwargs):
        return self._call("get_stock_list", *args, **kwargs)

    def get_realtime_quotes(self, *args, **kwargs):
        return self._call("get_realtime_quotes", *args, **kwargs)

    def get_daily_bars(self, *args, **kwargs):
        return self._call("get_daily_bars", *args, **kwargs)

    def get_financials(self, *args, **kwargs):
        return self._call("get_financials", *args, **kwargs)

    def get_news(self, *args, **kwargs):
        return self._call("get_news", *args, **kwargs)

    def get_index_info(self, *args, **kwargs):
        return self._call("get_index_info", *args, **kwargs)

    def get_index_list(self, *args, **kwargs):
        return self._call("get_index_list", *args, **kwargs)

    def get_index_daily_bars(self, *args, **kwargs):
        return self._call("get_index_daily_bars", *args, **kwargs)

    def get_stock_sector_info(self, *args, **kwargs):
        return self._call("get_stock_sector_info", *args, **kwargs)

    def get_stocks_by_sector(self, *args, **kwargs):
        return self._call("get_stocks_by_sector", *args, **kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter() -> FakeTA_CNMongoAdapter:
    return FakeTA_CNMongoAdapter()


@pytest.fixture
def market(adapter: FakeTA_CNMongoAdapter) -> MarketDataService:
    return MarketDataService(adapter)


@pytest.fixture
def fundamental(adapter: FakeTA_CNMongoAdapter) -> FundamentalService:
    return FundamentalService(adapter)


@pytest.fixture
def sector_svc(adapter: FakeTA_CNMongoAdapter) -> SectorService:
    return SectorService(adapter)


@pytest.fixture
def event(adapter: FakeTA_CNMongoAdapter) -> EventService:
    return EventService(adapter)


@pytest.fixture
def metadata(adapter: FakeTA_CNMongoAdapter) -> MetadataService:
    return MetadataService(adapter)


@pytest.fixture
def maotai() -> SecurityId:
    return SecurityId(market=Market.CN, symbol="600519")


@pytest.fixture
def hs300() -> SecurityId:
    return SecurityId(market=Market.INDEX, symbol="000300")


def _assert_success(result, domain, operation):
    assert result.succeeded
    assert result.domain == domain
    assert result.operation == operation
    assert result.provider == "ta_cn_adapter"
    assert result.freshness == "delayed"
    assert result.source_trace == ["ta_cn_adapter(ok)"]


def _assert_empty(result, domain, operation):
    assert result.is_empty()
    assert result.freshness == "empty"
    assert result.provider == "empty"
    assert result.source_trace == ["ta_cn_adapter(ok)"]
    assert result.domain == domain
    assert result.operation == operation


def _assert_error(result, domain, operation, msg_substr=None):
    assert result.freshness == "empty"
    assert result.provider == "error"
    assert result.source_trace
    assert any(msg_substr in trace for trace in result.source_trace if msg_substr) or \
        result.warnings, "expected error message in source_trace or warnings"
    assert result.domain == domain
    assert result.operation == operation


# ---------------------------------------------------------------------------
# MarketDataService
# ---------------------------------------------------------------------------


class TestMarketDataService:
    def test_get_realtime_quote_success(self, market, adapter, maotai):
        adapter.set_payload("get_realtime_quotes", {"symbol": "600519", "current_price": 100.0})
        result = market.get_realtime_quote(maotai)
        _assert_success(result, "market_data", "realtime_quote")
        assert isinstance(result.data, RealtimeQuote)
        assert result.data.current_price == 100.0

    def test_get_realtime_quote_empty(self, market, maotai):
        result = market.get_realtime_quote(maotai)
        _assert_empty(result, "market_data", "realtime_quote")

    def test_get_realtime_quote_error(self, market, adapter, maotai):
        adapter.set_error("get_realtime_quotes", ConnectionError("conn refused"))
        result = market.get_realtime_quote(maotai)
        _assert_error(result, "market_data", "realtime_quote", "conn refused")

    def test_get_realtime_quote_mapping_error(self, market, adapter, maotai):
        adapter.set_payload("get_realtime_quotes", "malformed-document")
        result = market.get_realtime_quote(maotai)
        _assert_error(result, "market_data", "realtime_quote", "expects dict")

    def test_get_realtime_quote_unexpected_error_is_not_swallowed(
        self, market, adapter, maotai
    ):
        adapter.set_error("get_realtime_quotes", AssertionError("programming bug"))
        with pytest.raises(AssertionError, match="programming bug"):
            market.get_realtime_quote(maotai)

    def test_get_kline_daily_success(self, market, adapter, maotai):
        adapter.set_payload(
            "get_daily_bars",
            [
                {"symbol": "600519", "trade_date": "20260713", "close": 100.0},
                {"symbol": "600519", "trade_date": "20260710", "close": 99.0},
            ],
        )
        result = market.get_kline_daily(maotai)
        _assert_success(result, "market_data", "kline_daily")
        assert isinstance(result.data, list)
        assert all(isinstance(bar, DailyBar) for bar in result.data)
        assert len(result.data) == 2

    def test_get_kline_daily_empty(self, market, maotai):
        result = market.get_kline_daily(maotai)
        _assert_empty(result, "market_data", "kline_daily")

    def test_get_kline_daily_propagates_filters(self, market, adapter, maotai):
        adapter.set_payload("get_daily_bars", [])
        market.get_kline_daily(maotai, start_date="2026-07-01", end_date="2026-07-31", limit=10)
        name, args = adapter.call_log[-1]
        assert name == "get_daily_bars"
        assert args[-1] == {"start_date": "2026-07-01", "end_date": "2026-07-31", "limit": 10}

    def test_get_kline_daily_error(self, market, adapter, maotai):
        adapter.set_error("get_daily_bars", ProviderError("boom"))
        result = market.get_kline_daily(maotai)
        _assert_error(result, "market_data", "kline_daily", "boom")

    def test_get_index_daily(self, market, adapter, hs300):
        adapter.set_payload(
            "get_index_daily_bars",
            [{"sector_code": "000300", "trade_date": "20260713", "close": 3875.0}],
        )
        result = market.get_index_daily(hs300)
        _assert_success(result, "market_data", "index_daily")
        assert isinstance(result.data[0], IndexDailyBar)

    def test_get_index_daily_empty(self, market, hs300):
        result = market.get_index_daily(hs300)
        _assert_empty(result, "market_data", "index_daily")


# ---------------------------------------------------------------------------
# FundamentalService
# ---------------------------------------------------------------------------


class TestFundamentalService:
    @pytest.fixture
    def fin_payload(self):
        return {
            "symbol": "600519",
            "report_period": "20251231",
            "raw_data": {
                "income_statement": [{"end_date": "20251231", "revenue": 130.0e9}],
                "balance_sheet": [{"end_date": "20251231", "total_assets": 250.0e9}],
                "cashflow_statement": [{"end_date": "20251231", "operating_cash_flow": 60.0e9}],
            },
        }

    def test_income_statement(self, fundamental, adapter, fin_payload, maotai):
        adapter.set_payload("get_financials", fin_payload)
        result = fundamental.get_income_statement(maotai)
        _assert_success(result, "financial", "income_statement")
        assert isinstance(result.data, FinancialStatement)
        assert result.data.items["revenue"] == 130.0e9

    def test_balance_sheet(self, fundamental, adapter, fin_payload, maotai):
        adapter.set_payload("get_financials", fin_payload)
        result = fundamental.get_balance_sheet(maotai)
        # operation name follows the canonical matrix: balance statement -> "balance_statement"
        _assert_success(result, "financial", "balance_statement")
        assert result.data.items["total_assets"] == 250.0e9

    def test_cash_flow(self, fundamental, adapter, fin_payload, maotai):
        adapter.set_payload("get_financials", fin_payload)
        result = fundamental.get_cash_flow(maotai)
        _assert_success(result, "financial", "cashflow_statement")
        assert result.data.items["operating_cash_flow"] == 60.0e9

    def test_empty(self, fundamental, maotai):
        result = fundamental.get_income_statement(maotai)
        _assert_empty(result, "financial", "income_statement")

    def test_invalid_statement_type(self):
        """Exercise the :class:`FundamentalService` guard for invalid types."""
        svc = FundamentalService(FakeTA_CNMongoAdapter())
        with pytest.raises(ValueError):
            svc._get_statement(
                SecurityId(market=Market.CN, symbol="600519"), "invalid", None,
            )

    def test_error(self, fundamental, adapter, maotai):
        adapter.set_error("get_financials", ValueError("decode error"))
        result = fundamental.get_income_statement(maotai)
        _assert_error(result, "financial", "income_statement", "decode error")


# ---------------------------------------------------------------------------
# SectorService
# ---------------------------------------------------------------------------


class TestSectorService:
    def test_get_stock_sector_success(self, sector_svc, adapter, maotai):
        adapter.set_payload(
            "get_stock_sector_info",
            [{"full_symbol": "600519.SH", "classify_system": "SW", "l1_code": "801120", "l1_name": "食品饮料"}],
        )
        result = sector_svc.get_stock_sector(maotai)
        _assert_success(result, "sector", "stock_sector")
        assert isinstance(result.data[0], SectorClassification)

    def test_get_stock_sector_empty_for_non_cn(self, sector_svc):
        hk = SecurityId(market=Market.HK, symbol="00700")
        result = sector_svc.get_stock_sector(hk)
        _assert_empty(result, "sector", "stock_sector")

    def test_get_stock_sector_empty(self, sector_svc, maotai):
        result = sector_svc.get_stock_sector(maotai)
        _assert_empty(result, "sector", "stock_sector")

    def test_get_stocks_by_sector_success(self, sector_svc, adapter):
        adapter.set_payload(
            "get_stocks_by_sector",
            [{"full_symbol": "600519.SH", "classify_system": "SW",
              "l1_code": "801120", "l1_name": "食品饮料"}],
        )
        result = sector_svc.get_stocks_by_sector("801120")
        _assert_success(result, "sector", "stocks_by_sector")
        assert result.security_id.symbol == "801120"

    def test_get_stocks_by_sector_empty(self, sector_svc):
        result = sector_svc.get_stocks_by_sector("999999")
        _assert_empty(result, "sector", "stocks_by_sector")

    def test_get_sector_index_bars(self, sector_svc, adapter):
        adapter.set_payload(
            "get_index_daily_bars",
            [{"sector_code": "801120", "trade_date": "20260713", "close": 5545.0, "pct_chg": 0.85}],
        )
        result = sector_svc.get_sector_index_bars("801120", start_date="2026-07-01", limit=10)
        _assert_success(result, "sector", "sector_index_bars")
        # Adapter receives sector_code; not via SecurityId.
        # SectorService.get_sector_index_bars() forwards via kwargs
        # so the fake's merged log has kwargs as the last positional.
        name, args = adapter.call_log[-1]
        assert name == "get_index_daily_bars"
        assert args[-1] == {"sector_code": "801120", "start_date": "2026-07-01", "end_date": None, "limit": 10}


# ---------------------------------------------------------------------------
# EventService
# ---------------------------------------------------------------------------


class TestEventService:
    def test_get_news_success(self, event, adapter, maotai):
        adapter.set_payload(
            "get_news",
            [
                {"symbol": "600519", "title": "茅台业绩预增", "publish_time": "2026-07-12T18:30:00"},
                {"symbol": "600519", "title": "茅台渠道改革", "publish_time": "2026-07-10T09:00:00"},
            ],
        )
        result = event.get_news(maotai)
        _assert_success(result, "event", "news")
        assert all(isinstance(item, NewsItem) for item in result.data)
        assert len(result.data) == 2

    def test_get_news_empty(self, event, maotai):
        result = event.get_news(maotai)
        _assert_empty(result, "event", "news")


# ---------------------------------------------------------------------------
# MetadataService
# ---------------------------------------------------------------------------


class TestMetadataService:
    def test_get_stock_info_success(self, metadata, adapter, maotai):
        adapter.set_payload(
            "get_stock_info",
            {"symbol": "600519", "full_symbol": "600519.SH", "name": "贵州茅台"},
        )
        result = metadata.get_stock_info(maotai)
        _assert_success(result, "metadata", "stock_info")
        assert isinstance(result.data, StockInfo)
        assert result.data.name == "贵州茅台"

    def test_get_stock_info_empty(self, metadata, maotai):
        result = metadata.get_stock_info(maotai)
        _assert_empty(result, "metadata", "stock_info")

    def test_get_stock_list_success(self, metadata, adapter):
        adapter.set_payload(
            "get_stock_list",
            [
                {"symbol": "000001", "full_symbol": "000001.SZ", "name": "平安银行"},
                {"symbol": "600519", "full_symbol": "600519.SH", "name": "贵州茅台"},
            ],
        )
        result = metadata.get_stock_list()
        _assert_success(result, "metadata", "stock_list")
        assert len(result.data) == 2

    def test_get_stock_list_empty(self, metadata):
        result = metadata.get_stock_list()
        _assert_empty(result, "metadata", "stock_list")

    def test_get_index_info(self, metadata, adapter, hs300):
        adapter.set_payload(
            "get_index_info",
            {"symbol": "000300", "full_symbol": "000300.SH", "name": "沪深300"},
        )
        result = metadata.get_index_info(hs300)
        _assert_success(result, "metadata", "index_info")
        assert isinstance(result.data, IndexInfo)

    def test_get_index_list(self, metadata, adapter):
        adapter.set_payload(
            "get_index_list",
            [
                {"symbol": "000300", "full_symbol": "000300.SH", "name": "沪深300"},
            ],
        )
        result = metadata.get_index_list()
        _assert_success(result, "metadata", "index_list")
        assert result.security_id.symbol == "LIST"

    def test_get_stock_list_propagates_filter(self, metadata, adapter):
        adapter.set_payload("get_stock_list", [])
        metadata.get_stock_list(market="CN", status="L", limit=50)
        name, args = adapter.call_log[-1]
        assert name == "get_stock_list"
        assert args[-1] == {"market": "CN", "status": "L", "limit": 50}
