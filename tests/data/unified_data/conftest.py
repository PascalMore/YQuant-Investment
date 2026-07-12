"""Shared fixtures for unified_data tests.

The fixtures provide a tiny in-memory fake provider and a few reusable
:class:`SecurityId` instances so individual tests can focus on behavior
rather than setup boilerplate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import pytest

from skills.data.unified_data import (
    DataProvider,
    Market,
    ProviderRegistry,
    SecurityId,
    UnifiedDataClient,
    UnifiedDataConfig,
)


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


@pytest.fixture
def fixed_now() -> datetime:
    """A fixed timestamp for deterministic DataResult assertions."""
    return datetime(2026, 7, 13, 0, 0, 0)