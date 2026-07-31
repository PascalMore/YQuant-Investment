"""AKShare Chinese-column DataFrame fixtures for P3-A sector activation tests.

Provides two factories that build DataFrames mirroring the exact
column structure of ``ak.stock_board_industry_name_em()`` — verified
via ``inspect.getsource`` (DESIGN-03-014-p3a §2.2). Columns are the
12 frozen Chinese names::

    排名, 板块名称, 板块代码, 最新价, 涨跌额, 涨跌幅,
    总市值, 换手率, 上涨家数, 下跌家数, 领涨股票, 领涨股票-涨跌幅

These fixtures never perform I/O and never import the real AKShare
SDK. They exist so that :class:`FakeSectorClient` and the canonical
mapping tests can consume realistic-shape Chinese-column data.
"""

from __future__ import annotations

import pandas as pd


# The exact 12-column order returned by stock_board_industry_name_em().
# Verified via inspect.getsource — frozen by the AKShare source code.
_INDUSTRY_COLUMNS = [
    "排名",
    "板块名称",
    "板块代码",
    "最新价",
    "涨跌额",
    "涨跌幅",
    "总市值",
    "换手率",
    "上涨家数",
    "下跌家数",
    "领涨股票",
    "领涨股票-涨跌幅",
]


def _default_industry_ranking_df() -> pd.DataFrame:
    """Return a 5-row DataFrame simulating ``name_em()`` industry ranking.

    Covers real board codes:

    * BK0489 白酒 (rank 1, pct_chg 3.21)
    * BK0473 证券 (rank 5, pct_chg 1.45)
    * BK1036 半导体 (rank 12, pct_chg 0.82)
    * BK0438 煤炭 (rank 45, pct_chg -0.50)
    * BK0733 农牧饲渔 (rank 88, pct_chg -2.10)

    Column names and order match the AKShare source exactly.
    """
    data = {
        "排名": [1, 5, 12, 45, 88],
        "板块名称": ["白酒", "证券", "半导体", "煤炭", "农牧饲渔"],
        "板块代码": ["BK0489", "BK0473", "BK1036", "BK0438", "BK0733"],
        "最新价": [12345.67, 8901.23, 5678.90, 2345.67, 1234.56],
        "涨跌额": [384.56, 126.78, 46.12, -11.78, -26.45],
        "涨跌幅": [3.21, 1.45, 0.82, -0.50, -2.10],
        "总市值": [
            5_678_900_000_000.0,
            3_456_700_000_000.0,
            2_345_600_000_000.0,
            1_234_500_000_000.0,
            678_900_000_000.0,
        ],
        "换手率": [2.35, 1.78, 3.12, 0.95, 1.45],
        "上涨家数": [18, 25, 42, 6, 3],
        "下跌家数": [2, 24, 33, 28, 35],
        "领涨股票": ["贵州茅台", "东方财富", "中芯国际", "中国神华", "牧原股份"],
        "领涨股票-涨跌幅": [5.67, 4.12, 3.89, 1.23, 0.45],
    }
    return pd.DataFrame(data, columns=_INDUSTRY_COLUMNS)


def _empty_ranking_df() -> pd.DataFrame:
    """Return an empty DataFrame with the same 12-column structure."""
    return pd.DataFrame(columns=_INDUSTRY_COLUMNS)


__all__ = [
    "_default_industry_ranking_df",
    "_empty_ranking_df",
]
