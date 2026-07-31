"""Historical sector ranking offline fixtures — RFC-03-015 T3.

Provides explicit expected universe + candidate-row factories for the
``sector.ranking_history`` offline tests. **No SW L1 full table** — the
universe here only proves build/validation logic correctness and does
not represent the production universe (H-049u; Gate-1 authoritative
verification).

All fixtures are pure data / mongomock construction — zero real I/O.
"""

from __future__ import annotations

from typing import Any, Iterable

import mongomock

from skills.data.unified_data.adapters.historical_ranking_writer import (
    HistoricalRankingWriter,
)

# dataset / 交易日常量（fixture 内显式，非生产常量）。
DATASET = "sw2021_ta_cn"
TRADE_DATE = "2026-07-13"
PREV_TRADE_DATE = "2026-07-10"

# 显式 expected universe（3 个申万风格代码 + 中文名，仅测试用）。
EXPECTED_SECTOR_CODES: frozenset[str] = frozenset({"801120", "801780", "801080"})


def _sector_row(
    sector_code: str,
    sector_name: str,
    close: float,
    pre_close: float,
) -> dict[str, Any]:
    """Build a candidate row with close/pre_close (pct_chg computed later)."""
    return {
        "sector_code": sector_code,
        "sector_name": sector_name,
        "close": close,
        "pre_close": pre_close,
    }


def make_valid_ranking_rows() -> list[dict[str, Any]]:
    """Three valid rows covering EXPECTED_SECTOR_CODES exactly.

    Computed pct_chg (close-to-pre_close):

    * 801780 银行     (3100.0 / 3050.0) -> +1.6393…  rank 1
    * 801120 食品饮料 (5545.0 / 5498.16) -> +0.8519…  rank 2
    * 801080 电子     (4200.0 / 4300.0)  -> -2.3255…  rank 3
    """
    return [
        _sector_row("801120", "食品饮料", 5545.0, 5498.16),
        _sector_row("801780", "银行", 3100.0, 3050.0),
        _sector_row("801080", "电子", 4200.0, 4300.0),
    ]


def make_tie_break_rows() -> list[dict[str, Any]]:
    """Two rows with identical pct_chg (both +100.0%) to pin the tiebreak.

    sector_code ASC must put 801010 before 801020 at the same pct_chg.
    """
    return [
        _sector_row("801020", "测试B", 3000.0, 1500.0),
        _sector_row("801010", "测试A", 2000.0, 1000.0),
    ]


def make_incomplete_rows() -> list[dict[str, Any]]:
    """Rows missing one expected sector (observed ⊊ expected)."""
    return make_valid_ranking_rows()[:-1]


def make_duplicate_rows() -> list[dict[str, Any]]:
    """Rows containing a duplicated sector_code (801120 twice)."""
    rows = make_valid_ranking_rows()
    rows.append(_sector_row("801120", "食品饮料重复", 5600.0, 5400.0))
    return rows


def make_extra_code_rows() -> list[dict[str, Any]]:
    """Rows containing a sector_code outside the expected universe."""
    rows = make_valid_ranking_rows()
    rows.append(_sector_row("801999", "测试多余", 1000.0, 990.0))
    return rows


def make_invalid_close_rows() -> list[dict[str, Any]]:
    """Rows where one expected sector has an illegal close (None)."""
    rows = make_valid_ranking_rows()
    rows[0]["close"] = None
    return rows


def make_zero_pre_close_rows() -> list[dict[str, Any]]:
    """Rows where one expected sector has pre_close == 0 (division guard)."""
    rows = make_valid_ranking_rows()
    rows[0]["pre_close"] = 0
    return rows


def make_empty_rows() -> list[dict[str, Any]]:
    """Zero valid rows: every candidate is missing close/pre_close."""
    return [
        {"sector_code": "801120", "sector_name": "食品饮料"},
        {"sector_code": "801780", "sector_name": "银行"},
        {"sector_code": "801080", "sector_name": "电子"},
    ]


def make_fully_complete_docs(
    rows: Iterable[dict[str, Any]] | None = None,
    *,
    dataset: str = DATASET,
    trade_date: str = TRADE_DATE,
) -> list[dict[str, Any]]:
    """Convert candidate rows into 9-field collection docs (with updated_at).

    Used to seed the mongomock collection directly (simulating a
    previously materialized formal ranking).
    """
    docs: list[dict[str, Any]] = []
    for i, row in enumerate(
        rows if rows is not None else make_valid_ranking_rows(), start=1
    ):
        close = float(row["close"])
        pre_close = float(row["pre_close"])
        docs.append(
            {
                "dataset": dataset,
                "trade_date": trade_date,
                "sector_code": row["sector_code"],
                "sector_name": row["sector_name"],
                "pct_chg": (close - pre_close) / pre_close * 100,
                "rank": i,
                "close": close,
                "pre_close": pre_close,
                "updated_at": "2026-07-31T19:30:00.000000",
            }
        )
    return docs


def make_mongomock_db(
    docs: Iterable[dict[str, Any]] | None = None,
    *,
    collection: str = HistoricalRankingWriter.COLLECTION,
) -> Any:
    """Build a fresh mongomock db, optionally pre-seeded with docs."""
    db = mongomock.MongoClient().get_database("unified_data_test")
    if docs:
        db[collection].insert_many(list(docs))
    return db


def make_writer(db: Any | None = None) -> HistoricalRankingWriter:
    """Build a writer over a fresh mongomock db (or the injected one)."""
    return HistoricalRankingWriter(db if db is not None else make_mongomock_db())


__all__ = [
    "DATASET",
    "PREV_TRADE_DATE",
    "TRADE_DATE",
    "EXPECTED_SECTOR_CODES",
    "make_valid_ranking_rows",
    "make_tie_break_rows",
    "make_incomplete_rows",
    "make_duplicate_rows",
    "make_extra_code_rows",
    "make_invalid_close_rows",
    "make_zero_pre_close_rows",
    "make_empty_rows",
    "make_fully_complete_docs",
    "make_mongomock_db",
    "make_writer",
]
