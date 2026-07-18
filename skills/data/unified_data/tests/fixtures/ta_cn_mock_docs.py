"""Sample TA-CN MongoDB documents for Phase 1A tests.

Each constant below is one typical document from the matching TA-CN
collection. Fixture builders return either a single doc or a list of
docs as the test requires.

The shapes mirror the production collections referenced in
DESIGN-03-007 §Phase 1A "字段映射规则". Date fields use ``"YYYYMMDD"``
strings; numeric fields use float-compatible values; nested financial
documents carry three lists under ``raw_data``.
"""

from __future__ import annotations

from copy import deepcopy

# ---------------------------------------------------------------------------
# stock_basic_info
# ---------------------------------------------------------------------------

STOCK_BASIC_INFO_MAOTAI: dict = {
    "symbol": "600519",
    "full_symbol": "600519.SH",
    "market": "CN",
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


STOCK_BASIC_INFO_PINGAN: dict = {
    "symbol": "000001",
    "full_symbol": "000001.SZ",
    "market": "CN",
    "name": "平安银行",
    "industry": "银行",
    "area": "深圳",
    "total_mv": 250000000000.0,
    "circ_mv": 250000000000.0,
    "pe": 5.3,
    "pb": 0.55,
    "roe": 0.10,
    "list_date": "1991-04-03",
    "status": "L",
}


def stock_basic_info_list() -> list[dict]:
    """Return a 3-doc sample list for ``stock_basic_info``."""
    third = {
        "symbol": "688981",
        "full_symbol": "688981.SH",
        "market": "CN",
        "name": "中芯国际",
        "industry": "半导体",
        "area": "上海",
        "total_mv": 500000000000.0,
        "circ_mv": 100000000000.0,
        "status": "L",
    }
    return [
        deepcopy(STOCK_BASIC_INFO_PINGAN),
        deepcopy(STOCK_BASIC_INFO_MAOTAI),
        third,
    ]


# ---------------------------------------------------------------------------
# market_quotes
# ---------------------------------------------------------------------------

MARKET_QUOTES_MAOTAI: dict = {
    "symbol": "600519",
    "current_price": 1950.50,
    "change": 12.30,
    "change_percent": 0.63,
    "open": 1940.00,
    "high": 1965.00,
    "low": 1938.20,
    "pre_close": 1938.20,
    "volume": 1234567.0,
    "amount": 2400000000.0,
    "update_time": "2026-07-13T09:35:00",
}


def market_quotes_with_close_fallback() -> dict:
    """Variant that uses ``close`` / ``pct_chg`` instead of the primary aliases."""
    return {
        "symbol": "000001",
        "close": 11.55,
        "change": 0.05,
        "pct_chg": 0.43,
        "open": 11.50,
        "high": 11.62,
        "low": 11.49,
        "pre_close": 11.50,
        "volume": 800000.0,
        "amount": 9230000.0,
        "timestamp": "2026-07-13T09:35:01",
    }


# ---------------------------------------------------------------------------
# stock_daily_quotes (3 trading days for limit / sort coverage)
# ---------------------------------------------------------------------------

STOCK_DAILY_QUOTES_MAOTAI = [
    {
        "symbol": "600519",
        "trade_date": "20260710",
        "open": 1920.0,
        "high": 1945.0,
        "low": 1918.0,
        "close": 1938.20,
        "pre_close": 1925.0,
        "change": 13.20,
        "pct_chg": 0.69,
        "vol": 1.0e6,
        "amount": 1.94e9,
        "turnover_rate": 0.18,
        "volume_ratio": 1.05,
    },
    {
        "symbol": "600519",
        "trade_date": "20260711",
        "open": 1940.0,
        "high": 1965.0,
        "low": 1938.20,
        "close": 1950.50,
        "pre_close": 1938.20,
        "change": 12.30,
        "pct_chg": 0.63,
        "vol": 1.23e6,
        "amount": 2.4e9,
        "turnover_rate": 0.22,
        "volume_ratio": 1.10,
    },
    {
        "symbol": "600519",
        "trade_date": "20260713",
        "open": 1952.0,
        "high": 1970.0,
        "low": 1948.0,
        "close": 1965.00,
        "pre_close": 1950.50,
        "change": 14.50,
        "pct_chg": 0.74,
        "vol": 1.3e6,
        "amount": 2.55e9,
        "turnover_rate": 0.24,
        "volume_ratio": 1.12,
    },
]


# ---------------------------------------------------------------------------
# stock_financial_data
# ---------------------------------------------------------------------------

def stock_financial_data_maotai() -> dict:
    """Return a 2025Q4 financial doc with three statement lists."""
    return {
        "symbol": "600519",
        "full_symbol": "600519.SH",
        "market": "CN",
        "report_period": "20251231",
        "report_type": "annual",
        "currency": "CNY",
        "raw_data": {
            "income_statement": [
                {
                    "end_date": "20251231",
                    "revenue": 130000000000.0,
                    "net_profit": 50000000000.0,
                    "operating_cost": 25000000000.0,
                    "gross_profit": 105000000000.0,
                },
            ],
            "balance_sheet": [
                {
                    "end_date": "20251231",
                    "total_assets": 250000000000.0,
                    "total_liabilities": 50000000000.0,
                    "equity": 200000000000.0,
                },
            ],
            "cashflow_statement": [
                {
                    "end_date": "20251231",
                    "operating_cash_flow": 60000000000.0,
                    "investing_cash_flow": -10000000000.0,
                    "financing_cash_flow": -25000000000.0,
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# stock_news
# ---------------------------------------------------------------------------

STOCK_NEWS_MAOTAI = [
    {
        "symbol": "600519",
        "title": "贵州茅台发布2025年年度业绩预增公告",
        "content": "公司预计2025年净利润同比增长约15%。",
        "source": "上证报",
        "publish_time": "2026-07-12T18:30:00",
        "sentiment": "positive",
        "category": "earnings",
        "importance": "high",
        "url": "https://news.example.com/maotai/2025-annual",
    },
    {
        "symbol": "600519",
        "title": "茅台渠道改革持续推进",
        "content": "数字化营销占比提升至25%。",
        "source": "证券时报",
        "publish_time": "2026-07-10T09:00:00",
        "sentiment": "neutral",
        "category": "operations",
        "url": "https://news.example.com/maotai/distribution",
    },
]


# ---------------------------------------------------------------------------
# index_basic_info
# ---------------------------------------------------------------------------

INDEX_BASIC_INFO_HS300: dict = {
    "symbol": "000300",
    "full_symbol": "000300.SH",
    "name": "沪深300",
    "fullname": "沪深300指数",
    "market": "CN",
    "publisher": "中证指数有限公司",
    "category": "broad_market",
}


INDEX_BASIC_INFO_CSI500: dict = {
    "symbol": "000905",
    "full_symbol": "000905.SH",
    "name": "中证500",
    "fullname": "中证500指数",
    "market": "CN",
    "publisher": "中证指数有限公司",
    "category": "broad_market",
}


# ---------------------------------------------------------------------------
# index_daily_quotes
# ---------------------------------------------------------------------------

INDEX_DAILY_QUOTES_HS300 = [
    {
        "sector_code": "000300",
        "trade_date": "20260711",
        "open": 3850.0,
        "high": 3870.0,
        "low": 3845.0,
        "close": 3865.5,
        "pct_chg": 0.4,
        "volume": 1.5e8,
        "amount": 2.3e11,
        "source": "csi",
    },
    {
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
    },
]


def sw_industry_daily_quotes(sector_code: str = "801120") -> list[dict]:
    """申万行业指数日线（示例用）。"""
    return [
        {
            "sector_code": sector_code,
            "trade_date": "20260713",
            "open": 5500.0,
            "high": 5560.0,
            "low": 5480.0,
            "close": 5545.0,
            "pct_chg": 0.85,
            "volume": 5.0e7,
            "amount": 4.5e10,
            "source": "sw",
        },
    ]


# ---------------------------------------------------------------------------
# stock_sector_info
# ---------------------------------------------------------------------------

STOCK_SECTOR_INFO_MAOTAI: dict = {
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


def stock_sector_pingan() -> dict:
    return {
        "full_symbol": "000001.SZ",
        "classify_system": "SW",
        "l1_code": "801780",
        "l1_name": "银行",
        "l2_code": "801782",
        "l2_name": "股份制银行",
        "datasource": "tushare",
        "update_at": "2026-07-01",
    }


def stock_sector_maotai_alt_system() -> dict:
    """Alternative classification system (e.g. 中证) for the same stock."""
    return {
        "full_symbol": "600519.SH",
        "classify_system": "CSI",
        "l1_code": "100100",
        "l1_name": "主要消费",
        "l2_code": "100101",
        "l2_name": "食品饮料",
        "datasource": "tushare",
        "update_at": "2026-06-15",
    }


# ---------------------------------------------------------------------------
# Convenience: full populate mapping
# ---------------------------------------------------------------------------


def make_populated_database():
    """Return a :class:`FakeDatabase` pre-populated with the canonical sample docs."""
    from . import FakeDatabase  # local import to avoid cycles

    db = FakeDatabase(
        {
            "stock_basic_info": stock_basic_info_list(),
            "market_quotes": [MARKET_QUOTES_MAOTAI, market_quotes_with_close_fallback()],
            "stock_daily_quotes": [deepcopy(doc) for doc in STOCK_DAILY_QUOTES_MAOTAI],
            "stock_financial_data": [stock_financial_data_maotai()],
            "stock_news": [deepcopy(doc) for doc in STOCK_NEWS_MAOTAI],
            "index_basic_info": [INDEX_BASIC_INFO_HS300, INDEX_BASIC_INFO_CSI500],
            "index_daily_quotes": [
                *[deepcopy(doc) for doc in INDEX_DAILY_QUOTES_HS300],
                *sw_industry_daily_quotes(),
            ],
            "stock_sector_info": [
                STOCK_SECTOR_INFO_MAOTAI,
                stock_sector_pingan(),
                stock_sector_maotai_alt_system(),
            ],
        },
    )
    return db


__all__ = [
    "STOCK_BASIC_INFO_MAOTAI",
    "STOCK_BASIC_INFO_PINGAN",
    "stock_basic_info_list",
    "MARKET_QUOTES_MAOTAI",
    "market_quotes_with_close_fallback",
    "STOCK_DAILY_QUOTES_MAOTAI",
    "stock_financial_data_maotai",
    "STOCK_NEWS_MAOTAI",
    "INDEX_BASIC_INFO_HS300",
    "INDEX_BASIC_INFO_CSI500",
    "INDEX_DAILY_QUOTES_HS300",
    "sw_industry_daily_quotes",
    "STOCK_SECTOR_INFO_MAOTAI",
    "stock_sector_pingan",
    "stock_sector_maotai_alt_system",
    "make_populated_database",
]
