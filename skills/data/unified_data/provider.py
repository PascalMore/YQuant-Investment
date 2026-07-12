"""Abstract data provider interface.

A :class:`DataProvider` is the unit of pluggability in unified_data: every
concrete source (Tushare, AKShare, a TA-CN adapter, a fake provider in
tests, ...) implements this protocol. Providers declare what they can do
via :attr:`capabilities` and what markets they cover via :attr:`markets`,
and they expose a single :meth:`fetch` method that performs the actual
request.

Phase 0 intentionally omits:
    * Rate limiting / circuit breakers
    * Caching (handled by CacheManager in Phase 1)
    * Retry policy (handled by DataRouter in Phase 1)

These belong to specific Provider implementations, which are not part of
Phase 0.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .exceptions import UnsupportedCapabilityError
from .models import Market, SecurityId


class DataProvider(ABC):
    """Abstract base class for all unified_data providers.

    Subclasses must implement :attr:`name`, :attr:`capabilities`,
    :attr:`markets`, :meth:`is_available` and :meth:`fetch`. The default
    :meth:`supports` helper combines capability + market checks and is
    rarely overridden.
    """

    # ------------------------------------------------------------------
    # Identity & metadata
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable, lowercase identifier for the provider.

        Used as the registry key and as the value of
        ``DataResult.provider``. Implementations should return a short
        snake_case string (``"tushare"``, ``"akshare"``,
        ``"ta_cn_adapter"``...).
        """

    @property
    @abstractmethod
    def capabilities(self) -> set[str]:
        """Set of capability strings (``"domain.operation"``) this provider
        can serve."""

    @property
    @abstractmethod
    def markets(self) -> set[Market]:
        """Set of markets this provider covers."""

    # ------------------------------------------------------------------
    # Capability / availability checks
    # ------------------------------------------------------------------

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` if the provider can currently serve requests.

        Implementations should be cheap to call (no network round-trip):
        the typical check is "do I have the required credential / is the
        dependency importable". Network-level probing belongs to a
        higher-level health check, not here.
        """

    def supports(self, capability: str, market: Market | str) -> bool:
        """Return ``True`` when this provider can serve ``capability`` for ``market``."""
        try:
            market_enum = market if isinstance(market, Market) else Market(market)
        except ValueError:
            return False
        return capability in self.capabilities and market_enum in self.markets

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        **params: Any,
    ) -> Any:
        """Fetch data for ``security_id`` under the given capability.

        Implementations must:
            * Raise :class:`UnsupportedCapabilityError` if the requested
              capability is not in :attr:`capabilities`.
            * Raise :class:`ProviderUnavailableError` when the provider
              cannot serve the request right now.
            * Raise :class:`ProviderError` for any other internal
              failure.

        Returns a payload (``pd.DataFrame`` in production providers, but
        the protocol allows any type so tests can pass plain dicts).
        """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _assert_capability(self, domain: str, operation: str) -> str:
        """Validate that the provider serves ``"domain.operation"``."""
        capability = f"{domain}.{operation}"
        if capability not in self.capabilities:
            raise UnsupportedCapabilityError(
                f"Provider {self.name!r} does not declare capability {capability!r}"
            )
        return capability