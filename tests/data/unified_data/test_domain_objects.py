"""Tests for Phase 1A canonical domain objects (8 dataclasses).

Each test exercises a ``from_ta_cn_doc()`` mapping against:
    * a fully-populated document
    * an empty / partial document (should yield ``None`` fields, no KeyError)
    * a non-dict input (should raise ``TypeError``)

The mapping rules are documented in DESIGN-03-007 §Phase 1A "字段映射规则".
"""

from __future__ import annotations

import pytest

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


# ---------------------------------------------------------------------------
# RealtimeQuote
# ---------------------------------------------------------------------------


class TestRealtimeQuote:
    def test_full_mapping(self):
        doc = {
            "symbol": "600519",
            "current_price": 1950.5,
            "change": 12.3,
            "change_percent": 0.63,
            "open": 1940.0,
            "high": 1965.0,
            "low": 1938.2,
            "pre_close": 1938.2,
            "volume": 1234567.0,
            "amount": 2.4e9,
            "update_time": "2026-07-13T09:35:00",
        }
        q = RealtimeQuote.from_ta_cn_doc(doc)
        assert q.symbol == "600519"
        assert q.current_price == 1950.5
        assert q.volume == 1234567.0
        assert q.update_time == "2026-07-13T09:35:00"

    @pytest.mark.parametrize(
        "doc,field,expected",
        [
            (
                {"symbol": "000001", "close": 11.55, "pct_chg": 0.43, "timestamp": "2026-07-13"},
                "current_price", 11.55,
            ),
            (
                {"symbol": "000001", "close": 11.55, "pct_chg": 0.43, "timestamp": "2026-07-13"},
                "change_percent", 0.43,
            ),
            (
                {"symbol": "000001", "close": 11.55, "pct_chg": 0.43, "timestamp": "2026-07-13"},
                "update_time", "2026-07-13",
            ),
        ],
    )
    def test_alias_fallbacks(self, doc, field, expected):
        q = RealtimeQuote.from_ta_cn_doc(doc)
        assert getattr(q, field) == expected

    def test_partial_doc(self):
        q = RealtimeQuote.from_ta_cn_doc({"symbol": "600519", "current_price": 100.0})
        assert q.symbol == "600519"
        assert q.current_price == 100.0
        assert q.open is None
        assert q.high is None

    def test_empty_doc(self):
        q = RealtimeQuote.from_ta_cn_doc({})
        assert q.symbol == ""
        assert q.current_price is None

    def test_invalid_input_raises(self):
        with pytest.raises(TypeError):
            RealtimeQuote.from_ta_cn_doc("not a dict")  # type: ignore[arg-type]

    def test_string_numbers_coerced(self):
        q = RealtimeQuote.from_ta_cn_doc({"symbol": "x", "current_price": "12.5"})
        assert q.current_price == 12.5

    def test_invalid_numeric_value_raises_mapping_error(self):
        with pytest.raises(ValueError, match="current_price"):
            RealtimeQuote.from_ta_cn_doc(
                {"symbol": "x", "current_price": "not-a-number"}
            )


# ---------------------------------------------------------------------------
# DailyBar
# ---------------------------------------------------------------------------


class TestDailyBar:
    def test_full_mapping(self):
        doc = {
            "symbol": "600519",
            "trade_date": "20260713",
            "open": 1952.0,
            "high": 1970.0,
            "low": 1948.0,
            "close": 1965.0,
            "pre_close": 1950.5,
            "change": 14.5,
            "pct_chg": 0.74,
            "vol": 1.3e6,
            "amount": 2.55e9,
            "turnover_rate": 0.24,
            "volume_ratio": 1.12,
        }
        bar = DailyBar.from_ta_cn_doc(doc)
        assert bar.symbol == "600519"
        assert bar.trade_date == "20260713"
        assert bar.volume == 1.3e6

    def test_volume_alias(self):
        bar = DailyBar.from_ta_cn_doc({"symbol": "x", "volume": 9.99})
        assert bar.volume == 9.99
        bar2 = DailyBar.from_ta_cn_doc({"symbol": "x", "vol": 8.88})
        assert bar2.volume == 8.88

    def test_partial_doc(self):
        bar = DailyBar.from_ta_cn_doc({"symbol": "x", "trade_date": "20260101"})
        assert bar.open is None
        assert bar.close is None

    def test_invalid_input(self):
        with pytest.raises(TypeError):
            DailyBar.from_ta_cn_doc(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# IndexDailyBar
# ---------------------------------------------------------------------------


class TestIndexDailyBar:
    def test_full_mapping(self):
        doc = {
            "sector_code": "000300",
            "trade_date": "20260713",
            "open": 3865.0,
            "high": 3880.0,
            "low": 3860.0,
            "close": 3875.0,
            "pct_chg": 0.25,
            "volume": 1.6e8,
            "amount": 2.5e11,
            "source": "csi",
        }
        bar = IndexDailyBar.from_ta_cn_doc(doc)
        assert bar.symbol == "000300"
        assert bar.data_source == "csi"
        assert bar.amount == 2.5e11

    @pytest.mark.parametrize(
        "doc,expected_symbol",
        [
            ({"symbol": "000300", "trade_date": "x"}, "000300"),
            ({"code": "801120", "trade_date": "x"}, "801120"),
            ({"sector_code": "abc", "trade_date": "x"}, "abc"),
        ],
    )
    def test_symbol_field_aliases(self, doc, expected_symbol):
        bar = IndexDailyBar.from_ta_cn_doc(doc)
        assert bar.symbol == expected_symbol

    def test_volume_alias(self):
        bar = IndexDailyBar.from_ta_cn_doc({"symbol": "x", "vol": 1.0})
        assert bar.volume == 1.0

    def test_default_data_source(self):
        bar = IndexDailyBar.from_ta_cn_doc({"symbol": "x", "trade_date": "y"})
        assert bar.data_source == ""

    def test_invalid_input(self):
        with pytest.raises(TypeError):
            IndexDailyBar.from_ta_cn_doc(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# FinancialStatement
# ---------------------------------------------------------------------------


@pytest.fixture
def fin_doc() -> dict:
    return {
        "symbol": "600519",
        "report_period": "20251231",
        "currency": "CNY",
        "raw_data": {
            "income_statement": [
                {
                    "end_date": "20251231",
                    "revenue": "130000000000",
                    "net_profit": 50.0e9,
                },
            ],
            "balance_sheet": [],
            "cashflow_statement": [],
        },
    }


class TestFinancialStatement:
    def test_income_statement(self, fin_doc):
        stmt = FinancialStatement.from_ta_cn_doc(fin_doc, "income")
        assert stmt.symbol == "600519"
        assert stmt.report_period == "20251231"
        assert stmt.statement_type == "income"
        assert stmt.items["revenue"] == 1.3e11
        assert stmt.items["net_profit"] == 5.0e10

    def test_empty_list_branch_returns_no_items(self, fin_doc):
        stmt = FinancialStatement.from_ta_cn_doc(fin_doc, "balance")
        assert stmt.items == {}

    def test_selects_latest_statement_by_end_date(self, fin_doc):
        fin_doc["raw_data"]["income_statement"] = [
            {"end_date": "20241231", "revenue": 100.0},
            {"end_date": "20251231", "revenue": 130.0},
        ]
        stmt = FinancialStatement.from_ta_cn_doc(fin_doc, "income")
        assert stmt.items["revenue"] == 130.0

    def test_no_raw_data_branch(self):
        stmt = FinancialStatement.from_ta_cn_doc(
            {"symbol": "x", "report_period": "y"}, "income"
        )
        assert stmt.items == {}

    def test_default_currency(self, fin_doc):
        fin_doc_no_currency = {"symbol": "x", "report_period": "y", "raw_data": {}}
        stmt = FinancialStatement.from_ta_cn_doc(fin_doc_no_currency, "income")
        assert stmt.currency == "CNY"

    @pytest.mark.parametrize(
        "bad_type", ["revenue", "flow", "", "BALANCE", "Income"]
    )
    def test_invalid_statement_type(self, fin_doc, bad_type):
        with pytest.raises(ValueError):
            FinancialStatement.from_ta_cn_doc(fin_doc, bad_type)

    def test_invalid_input(self):
        with pytest.raises(TypeError):
            FinancialStatement.from_ta_cn_doc("oops", "income")  # type: ignore[arg-type]

    def test_items_reject_non_coercible_strings(self, fin_doc):
        fin_doc["raw_data"]["income_statement"][0]["unknown"] = "not-a-number"
        with pytest.raises(ValueError, match="unknown"):
            FinancialStatement.from_ta_cn_doc(fin_doc, "income")


# ---------------------------------------------------------------------------
# NewsItem
# ---------------------------------------------------------------------------


class TestNewsItem:
    def test_full_mapping(self):
        doc = {
            "symbol": "600519",
            "title": "茅台业绩预增",
            "content": "公告内容",
            "source": "上证报",
            "publish_time": "2026-07-12T18:30:00",
            "sentiment": "positive",
            "category": "earnings",
            "importance": "high",
            "url": "https://news.example.com/x",
        }
        item = NewsItem.from_ta_cn_doc(doc)
        assert item.symbol == "600519"
        assert item.importance == "high"

    def test_partial_doc(self):
        item = NewsItem.from_ta_cn_doc({"title": "headline"})
        assert item.symbol is None
        assert item.content is None

    def test_symbol_optional(self):
        item = NewsItem.from_ta_cn_doc({"title": "t", "symbol": None})
        assert item.symbol is None

    def test_invalid_input(self):
        with pytest.raises(TypeError):
            NewsItem.from_ta_cn_doc(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SectorClassification
# ---------------------------------------------------------------------------


class TestSectorClassification:
    def test_full_mapping(self):
        doc = {
            "full_symbol": "600519.SH",
            "classify_system": "SW",
            "l1_code": "801120",
            "l1_name": "食品饮料",
            "l2_code": "801123",
            "l2_name": "白酒",
            "l3_code": "80112310",
            "l3_name": "白酒",
            "datasource": "tushare",
            "update_at": "2026-07-01",
        }
        s = SectorClassification.from_ta_cn_doc(doc)
        assert s.l1_code == "801120"
        assert s.l3_code == "80112310"

    def test_partial_doc(self):
        s = SectorClassification.from_ta_cn_doc(
            {"full_symbol": "x", "classify_system": "SW", "l1_code": "y", "l1_name": "z"}
        )
        assert s.l2_code is None

    def test_default_classify_system(self):
        s = SectorClassification.from_ta_cn_doc(
            {"full_symbol": "x", "l1_code": "y", "l1_name": "z"}
        )
        assert s.classify_system == "SW"

    def test_default_datasource(self):
        s = SectorClassification.from_ta_cn_doc(
            {"full_symbol": "x", "l1_code": "y", "l1_name": "z"}
        )
        assert s.datasource == "tushare"

    def test_invalid_input(self):
        with pytest.raises(TypeError):
            SectorClassification.from_ta_cn_doc(b"bytes")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# StockInfo
# ---------------------------------------------------------------------------


class TestStockInfo:
    def test_full_mapping(self):
        doc = {
            "symbol": "600519",
            "full_symbol": "600519.SH",
            "name": "贵州茅台",
            "industry": "白酒",
            "area": "贵州",
            "total_mv": 2450000000000.0,
            "circ_mv": 2450000000000.0,
            "pe": 28.5,
            "pe_ttm": 26.8,
            "pb": 9.4,
            "pb_mrq": 9.1,
            "roe": 0.30,
            "list_date": "2001-08-27",
            "status": "L",
            "market_info": {"exchange": "SSE", "board": "main"},
        }
        info = StockInfo.from_ta_cn_doc(doc)
        assert info.symbol == "600519"
        assert info.industry == "白酒"
        assert info.total_mv == 2450000000000.0
        assert info.roe == 0.30
        assert info.market_info == {"exchange": "SSE", "board": "main"}

    def test_partial_doc(self):
        info = StockInfo.from_ta_cn_doc({"symbol": "x", "full_symbol": "x.SH", "name": "y"})
        assert info.industry is None
        assert info.pe is None

    def test_invalid_numeric_value_raises_mapping_error(self):
        with pytest.raises(ValueError, match="pe"):
            StockInfo.from_ta_cn_doc(
                {"symbol": "x", "full_symbol": "x.SH", "name": "y", "pe": "bad"}
            )

    def test_invalid_input(self):
        with pytest.raises(TypeError):
            StockInfo.from_ta_cn_doc(0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# IndexInfo
# ---------------------------------------------------------------------------


class TestIndexInfo:
    def test_full_mapping(self):
        doc = {
            "symbol": "000300",
            "full_symbol": "000300.SH",
            "name": "沪深300",
            "fullname": "沪深300指数",
            "market": "CN",
            "publisher": "中证指数有限公司",
            "category": "broad_market",
        }
        info = IndexInfo.from_ta_cn_doc(doc)
        assert info.fullname == "沪深300指数"
        assert info.publisher == "中证指数有限公司"

    def test_partial_doc(self):
        info = IndexInfo.from_ta_cn_doc({"symbol": "x", "full_symbol": "x.SH", "name": "y"})
        assert info.fullname is None

    def test_invalid_input(self):
        with pytest.raises(TypeError):
            IndexInfo.from_ta_cn_doc([])  # type: ignore[arg-type]
