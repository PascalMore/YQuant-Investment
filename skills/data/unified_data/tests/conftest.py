"""Shared fixtures for the colocated Unified Data test suite.

All fixture definitions (SecurityId fixtures, FakeProvider, FakeTA_CNAdapter,
FakeTA_CNMongoAdapter, and factory fixtures) live here for unit and E2E tests.
"""

from __future__ import annotations

from typing import Any, Iterable

import pytest

from skills.data.unified_data import (
    DataProvider,
    Market,
    ProviderRegistry,
    SecurityId,
    TA_CNMongoAdapter,
    UnifiedDataClient,
    UnifiedDataConfig,
)

pytest_plugins = ("skills.data.unified_data.tests.fixtures.quality_fixtures",)

# ---------------------------------------------------------------------------
# SecurityId fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cn_maotai() -> SecurityId:
    """SecurityId for 贵州茅台 (600519.SH)."""
    return SecurityId(market=Market.CN, symbol="600519")


@pytest.fixture
def cn_pingan() -> SecurityId:
    """SecurityId for 中国平安 (000001.SZ)."""
    return SecurityId(market=Market.CN, symbol="000001")


@pytest.fixture
def hk_tencent() -> SecurityId:
    """SecurityId for 腾讯 (00700.HK)."""
    return SecurityId(market=Market.HK, symbol="00700")


@pytest.fixture
def us_aapl() -> SecurityId:
    """SecurityId for Apple (AAPL)."""
    return SecurityId(market=Market.US, symbol="AAPL")


# ---------------------------------------------------------------------------
# Fake providers
# ---------------------------------------------------------------------------


class FakeProvider(DataProvider):
    """Configurable in-memory provider used across router tests.

    Behavior knobs (all kw-only):
        * ``payload``           — value returned by :meth:`fetch`
        * ``raise_on_fetch``    — exception to raise on :meth:`fetch`
        * ``available``         — value of :meth:`is_available`
        * ``capabilities``      — set of capability strings
        * ``markets``           — set of :class:`Market` values
        * ``call_log``          — list to which each invocation appends
                                  ``(method, capability, market, params)``
    """

    def __init__(
        self,
        name: str,
        *,
        payload: Any = None,
        capabilities: Iterable[str] = (),
        markets: Iterable[Market] = (),
        raise_on_fetch: BaseException | None = None,
        available: bool = True,
        call_log: list[tuple[str, str, str, dict]] | None = None,
    ) -> None:
        self._name = name
        self._payload = payload
        self._capabilities = set(capabilities)
        self._markets = set(markets)
        self._raise = raise_on_fetch
        self._available = available
        self.call_log = call_log if call_log is not None else []

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> set[str]:
        return set(self._capabilities)

    @property
    def markets(self) -> set[Market]:
        return set(self._markets)

    def is_available(self) -> bool:
        return self._available

    def fetch(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        **params: Any,
    ) -> Any:
        self.call_log.append(
            (self._name, f"{domain}.{operation}", security_id.canonical, dict(params))
        )
        if self._raise is not None:
            raise self._raise
        return self._payload


# ---------------------------------------------------------------------------
# Convenience factories
# ---------------------------------------------------------------------------


@pytest.fixture
def make_provider():
    """Return a factory that builds :class:`FakeProvider` instances."""

    def _factory(name: str = "fake", **kwargs: Any) -> FakeProvider:
        return FakeProvider(name=name, **kwargs)

    return _factory


@pytest.fixture
def fresh_registry() -> ProviderRegistry:
    """Empty provider registry, isolated per-test."""
    return ProviderRegistry()


@pytest.fixture
def fresh_client() -> UnifiedDataClient:
    """Empty client with default config."""
    return UnifiedDataClient()


# ---------------------------------------------------------------------------
# Phase 1B-A: FakeTA_CNAdapter
# ---------------------------------------------------------------------------
# DESIGN-03-008 §4.1: the internal-first router tests need a configurable
# stand-in for the real TA_CNMongoAdapter. The fake records every call
# in ``call_log`` so tests can assert on routing behaviour, exposes
# ``collections`` for canned Mongo-like payloads, and supports both an
# exception injection knob and a "covered capability" knob for boundary
# tests.


class FakeTA_CNAdapter:
    """Configurable TA-CN adapter substitute used by the internal-first tests.

    Behaviour knobs (all kw-only):

    * ``collections``  — ``dict[str, list[dict]]`` mimicking the eight
      ``COLLECTION_*`` collections the real adapter queries.
    * ``raise_on_query`` — exception instance to raise on every method
      invocation. ``None`` disables the injection.
    * ``covered_capabilities`` — optional override of the default
      "covers every method-map capability" behaviour. When supplied,
      capabilities outside the override cause the fake to return
      ``None`` (the Router reads that as "not covered").
    """

    def __init__(
        self,
        *,
        collections: dict | None = None,
        raise_on_query: BaseException | None = None,
        covered_capabilities: set | None = None,
    ) -> None:
        # Local import to avoid pulling ``DataRouter`` into the test
        # conftest while half the rest of the suite still relies on the
        # module-level imports above. The constant is a class-level dict
        # so reading it via the class (rather than an instance) keeps the
        # fake aligned with future map edits.
        from skills.data.unified_data.router import DataRouter

        self._collections: dict = collections or {}
        self._raise = raise_on_query
        # ``None`` means: cover every capability the Router's map knows.
        # An explicit ``set`` means: cover exactly that set (useful for
        # negative-coverage tests).
        self._covered: set | None = covered_capabilities
        self._method_map = DataRouter._TA_CN_CAPABILITY_METHOD_MAP
        self.call_log: list[str] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, capability: str) -> str | None:
        """Return the adapter method name for ``capability`` if covered."""
        method_name = self._method_map.get(capability)
        if method_name is None:
            return None
        if self._covered is not None and capability not in self._covered:
            return None
        return method_name

    def _maybe_raise_or_return(
        self,
        coll_name: str,
        symbol: str | None = None,
        *,
        single: bool = False,
    ) -> list | dict | None:
        """Return canned docs for ``coll_name`` filtered by ``symbol``.

        Raises the injected exception when configured. Returns ``None``
        for single-object queries with no match (so the Router reports
        an "empty" payload), or ``[]`` for collection-style queries.
        """
        if self._raise is not None:
            raise self._raise
        docs = list(self._collections.get(coll_name, []))
        if symbol is not None:
            docs = [d for d in docs if d.get("symbol") == symbol]
        if single:
            return docs[0] if docs else None
        return docs

    # ------------------------------------------------------------------
    # TA-CN 11 read methods (mirrors TA_CNMongoAdapter signature)
    # ------------------------------------------------------------------

    def get_daily_bars(self, symbol, start_date=None, end_date=None, limit=120):
        self.call_log.append("get_daily_bars")
        return self._maybe_raise_or_return("stock_daily_quotes", symbol)

    def get_realtime_quotes(self, symbol):
        self.call_log.append("get_realtime_quotes")
        return self._maybe_raise_or_return("market_quotes", symbol, single=True)

    def get_financials(self, symbol, report_period=None):
        self.call_log.append("get_financials")
        return self._maybe_raise_or_return(
            "stock_financial_data", symbol, single=True
        )

    def get_stock_list(self, market="CN", status="L", limit=0):
        self.call_log.append("get_stock_list")
        return self._maybe_raise_or_return("stock_basic_info")

    def get_stock_info(self, symbol, market="CN"):
        self.call_log.append("get_stock_info")
        return self._maybe_raise_or_return(
            "stock_basic_info", symbol, single=True
        )

    def get_index_list(self, market="CN"):
        self.call_log.append("get_index_list")
        return self._maybe_raise_or_return("index_basic_info")

    def get_index_info(self, symbol):
        self.call_log.append("get_index_info")
        return self._maybe_raise_or_return(
            "index_basic_info", symbol, single=True
        )

    def get_index_daily_bars(
        self, symbol=None, sector_code=None, start_date=None, end_date=None, limit=120
    ):
        self.call_log.append("get_index_daily_bars")
        return self._maybe_raise_or_return("index_daily_quotes")

    def get_news(self, symbol, limit=20):
        self.call_log.append("get_news")
        return self._maybe_raise_or_return("stock_news")


@pytest.fixture
def fake_ta_cn_adapter():
    """Empty-data ``FakeTA_CNAdapter`` covering every known capability."""
    return FakeTA_CNAdapter(collections={})


@pytest.fixture
def fake_ta_cn_with_kline(cn_maotai):
    """``FakeTA_CNAdapter`` pre-populated with one daily bar for ``cn_maotai``."""
    return FakeTA_CNAdapter(
        collections={
            "stock_daily_quotes": [
                {
                    "symbol": cn_maotai.symbol,
                    "trade_date": "20260713",
                    "open": 1600,
                    "close": 1620,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# FakeTA_CNMongoAdapter
# ---------------------------------------------------------------------------
# A configurable mock that subclasses TA_CNMongoAdapter so test code can
# inject per-method payloads/errors without hitting a real MongoDB.


class FakeTA_CNMongoAdapter(TA_CNMongoAdapter):
    """Mock adapter that lets each test override exactly one method.

    Each non-overridden method returns ``None`` / ``[]`` (the "empty"
    signal); tests call :meth:`set_payload` or :meth:`set_error` to
    configure per-method behavior, then assert the *correct* provider /
    freshness / ``source_trace`` wrapping occurred.

    Usage::

        adapter = FakeTA_CNMongoAdapter()
        adapter.set_payload("get_realtime_quotes", {"current_price": 1.0})
        result = client.get_realtime_quote(sid)
    """

    def __init__(self) -> None:
        super().__init__(db={})
        self._payloads: dict[str, Any] = {}
        self._errors: dict[str, BaseException] = {}
        self.call_log: list[tuple[str, tuple]] = []

    def set_payload(self, method: str, value: Any) -> None:
        self._payloads[method] = value

    def set_error(self, method: str, exc: BaseException) -> None:
        self._errors[method] = exc

    def _log(self, name: str, args: tuple) -> Any:
        self.call_log.append((name, args))
        if name in self._errors:
            raise self._errors[name]
        return self._payloads.get(name)

    # -- stock_basic_info --
    def get_stock_info(self, symbol, market="CN"):  # type: ignore[override]
        return self._log("get_stock_info", (symbol, market))

    def get_stock_list(self, market="CN", status="L", limit=0):  # type: ignore[override]
        return self._log("get_stock_list", (market, status, limit))

    # -- market_quotes --
    def get_realtime_quotes(self, symbol):  # type: ignore[override]
        return self._log("get_realtime_quotes", (symbol,))

    # -- stock_daily_quotes --
    def get_daily_bars(self, symbol, start_date=None, end_date=None, limit=120):  # type: ignore[override]
        return self._log("get_daily_bars", (symbol, start_date, end_date, limit))

    # -- stock_financial_data --
    def get_financials(self, symbol, report_period=None):  # type: ignore[override]
        return self._log("get_financials", (symbol, report_period))

    # -- stock_news --
    def get_news(self, symbol, limit=20):  # type: ignore[override]
        return self._log("get_news", (symbol, limit))

    # -- index_basic_info --
    def get_index_info(self, symbol):  # type: ignore[override]
        return self._log("get_index_info", (symbol,))

    def get_index_list(self, market="CN"):  # type: ignore[override]
        return self._log("get_index_list", (market,))

    # -- index_daily_quotes --
    def get_index_daily_bars(  # type: ignore[override]
        self, symbol=None, sector_code=None, start_date=None, end_date=None, limit=120,
    ):
        return self._log(
            "get_index_daily_bars", (symbol, sector_code, start_date, end_date, limit),
        )

    # -- stock_sector_info --
    def get_stock_sector_info(self, full_symbol, classify_system=None):  # type: ignore[override]
        return self._log("get_stock_sector_info", (full_symbol, classify_system))

    def get_stocks_by_sector(self, l1_code, classify_system="SW"):  # type: ignore[override]
        return self._log("get_stocks_by_sector", (l1_code, classify_system))
