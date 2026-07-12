"""Consumer-facing facade for unified_data.

:class:`UnifiedDataClient` is what every consumer (stock framework, TA-CN
adapter, Argus, portfolio, ...) is expected to use. It owns a
:class:`ProviderRegistry` and a :class:`DataRouter`, and exposes a thin
``query`` method that simply forwards to the router.

Phase 0 keeps the facade tiny on purpose: the convenience helpers
(``get_kline_daily``, ``get_stock_list``, ...) belong to later phases once
the underlying services exist.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .config import UnifiedDataConfig
from .models import DataResult, Market, SecurityId
from .provider import DataProvider
from .registry import ProviderRegistry
from .router import DataRouter


class UnifiedDataClient:
    """Facade that ties the registry and the router together."""

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        config: UnifiedDataConfig | None = None,
    ) -> None:
        self._registry = registry if registry is not None else ProviderRegistry()
        self._config = config or UnifiedDataConfig.minimal()
        self._router = DataRouter(self._registry, self._config)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def registry(self) -> ProviderRegistry:
        """The underlying provider registry."""
        return self._registry

    @property
    def config(self) -> UnifiedDataConfig:
        """The active configuration."""
        return self._config

    @property
    def router(self) -> DataRouter:
        """The underlying data router (exposed for advanced use)."""
        return self._router

    def register_provider(self, provider: DataProvider) -> None:
        """Register ``provider`` with the underlying registry."""
        self._registry.register(provider)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        domain: str,
        operation: str,
        security_id: SecurityId,
        *,
        provider: str | None = None,
        market: Market | str | None = None,
        params: Mapping[str, Any] | None = None,
        fetched_at: datetime | None = None,
    ) -> DataResult:
        """Route ``security_id`` to a provider and return a DataResult.

        See :meth:`DataRouter.query` for the full semantics. This method
        exists purely as a stable entry point for consumers that prefer
        to depend on the client object rather than the router directly.
        """
        return self._router.query(
            domain,
            operation,
            security_id,
            provider=provider,
            market=market,
            params=params,
            fetched_at=fetched_at,
        )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def with_providers(
        cls,
        providers: list[DataProvider],
        config: UnifiedDataConfig | None = None,
    ) -> "UnifiedDataClient":
        """Build a client pre-populated with ``providers``.

        Providers are registered in the given order, which becomes the
        fallback order when no explicit chain is configured.
        """
        client = cls(config=config)
        for provider in providers:
            client.register_provider(provider)
        return client


__all__ = ["UnifiedDataClient"]