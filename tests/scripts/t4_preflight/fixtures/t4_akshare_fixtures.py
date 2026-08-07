"""Fixtures for PR-2/3/4 AKShare smoke tests.

DESIGN-03-014 §15.6 / SPEC-03-014 §14.4.

Provides canned AKShare responses in the form of plain
``list[dict]`` and ``pandas.DataFrame`` substitutes. The
``FakeAkshareDispatcher`` returns these canned responses based on
the function name passed to ``provider_client._dispatcher``.
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = [
    "FakeAkshareDispatcher",
    "sector_snapshot_fixture",
    "sector_ranking_fixture",
    "flow_daily_fixture",
    "market_sentiment_fixture",
    "limit_up_pool_fixture",
]


def sector_snapshot_fixture() -> list[dict[str, Any]]:
    return [
        {
            "板块代码": "BK0489",
            "板块名称": "酿酒行业",
            "最新价": 12345.6,
            "涨跌幅": 1.23,
            "总市值": 9.99e11,
            "换手率": 0.5,
        },
    ]


def sector_ranking_fixture() -> list[dict[str, Any]]:
    return [
        {"板块代码": "BK0489", "板块名称": "酿酒行业", "涨跌幅": 1.23},
        {"板块代码": "BK0002", "板块名称": "煤炭行业", "涨跌幅": -0.45},
    ]


def flow_daily_fixture() -> list[dict[str, Any]]:
    """P3-B S1 ``flow.capital_flow_daily`` fixture.

    The 9 zh fields here (日期、股票代码、收盘价、涨跌幅 + 主力/
    超大单/大单/中单/小单净流入-净额) are this tool's G-CF-LIVE
    *matching-input contract*: the exact names fed into
    ``FieldMapper.compare`` / the ``MATCH_RATIO_CONDITIONAL=0.70``
    decision — NOT a doc-frozen canonical field mapping. The
    authoritative (inferred, NOT live-read verified) canonical
    table is DESIGN §4.2.2 / §15.14.1 ``flow.capital_flow_daily``
    (English names ``main_net_inflow`` etc., includes ratio/margin,
    no 收盘价/涨跌幅, no ``-净额`` suffix). This 9-field set is a
    matching-input subset, not the complete upstream
    ``stock_individual_fund_flow`` schema (akshare 1.17.54 static:
    13 columns, no 股票代码 column; the DESIGN table lists
    股票代码 only as the inferred ``symbol`` source column). The
    historical PR-3 fixture used a fabricated ``stock`` / ``code`` /
    ``northbound`` shape — that was the schema-mismatch source for
    PR-3, and the shape is no longer registered.
    """
    return [
        {
            "日期": "2026-07-22",
            "股票代码": "600519",
            "收盘价": 1680.5,
            "涨跌幅": 0.85,
            "主力净流入-净额": 1.2e8,
            "超大单净流入-净额": 8.0e7,
            "大单净流入-净额": 4.0e7,
            "中单净流入-净额": -3.0e7,
            "小单净流入-净额": -9.0e7,
        },
    ]


def market_sentiment_fixture() -> list[dict[str, Any]]:
    return [
        {"日期": "2026-07-22", "主力净流入": 5.0e8, "超大单净流入": 3.0e8, "大单净流入": 2.0e8},
    ]


def limit_up_pool_fixture() -> list[dict[str, Any]]:
    return [
        {"代码": "600000", "名称": "浦发银行", "涨跌幅": 10.0, "连板数": 1, "封单金额": 1.0e7},
    ]


_FIXTURE_BY_FN: dict[str, Callable[[], list[dict[str, Any]]]] = {
    "stock_board_industry_cons_em": sector_snapshot_fixture,
    "stock_board_industry_name_em": sector_ranking_fixture,
    "stock_individual_fund_flow": flow_daily_fixture,
    "stock_market_fund_flow": market_sentiment_fixture,
    "stock_zt_pool_em": limit_up_pool_fixture,
}


class FakeAkshareDispatcher:
    """Fake dispatcher for :mod:`scripts.t4_preflight.provider_client`.

    Construct with a custom mapping or default to the canned
    fixtures. Tests can call :func:`set_response` to override the
    return value for a specific function.
    """

    def __init__(
        self,
        *,
        mapping: dict[str, Callable[[], Any]] | None = None,
    ) -> None:
        self._mapping: dict[str, Callable[[], Any]] = dict(mapping or _FIXTURE_BY_FN)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def set_response(self, fn_name: str, response: Any) -> None:
        """Override the canned response for ``fn_name``."""
        self._mapping[fn_name] = lambda r=response: r

    def set_error(self, fn_name: str, exc: BaseException) -> None:
        """Configure ``fn_name`` to raise ``exc`` on next call."""
        self._mapping[fn_name] = self._raise_factory(exc)

    @staticmethod
    def _raise_factory(exc: BaseException):
        def _raise(*args, **kwargs):  # pragma: no cover - tested
            raise exc

        return _raise

    def __call__(self, fn_name: str, **kwargs: Any) -> Any:
        self.calls.append((fn_name, dict(kwargs)))
        factory = self._mapping.get(fn_name)
        if factory is None:
            raise AttributeError(f"akshare has no attribute {fn_name!r}")
        return factory()
