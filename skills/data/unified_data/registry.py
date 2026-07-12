"""Provider registry for unified_data.

The :class:`ProviderRegistry` is an in-memory mapping from capability to
the list of providers that declare that capability, plus a name → provider
map for O(1) lookup. Phase 0 keeps it deliberately simple:

* No MongoDB persistence — providers live as long as the Python process.
* No background health checks — ``is_available()`` is queried on demand.
* No priority configuration beyond insertion order.

Subsequent phases will add configuration-driven priority, availability
caching, and provider lifecycle hooks.
"""

from __future__ import annotations

from .models import Market
from .provider import DataProvider


class ProviderRegistry:
    """In-memory registry of :class:`DataProvider` instances.

    Capabilities and provider names are normalized at registration time
    so that ``get_providers("market_data.kline_daily")`` always returns
    a list in registration order regardless of how the underlying set
    was constructed.
    """

    def __init__(self) -> None:
        self._providers: dict[str, DataProvider] = {}
        self._by_capability: dict[str, list[DataProvider]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, provider: DataProvider) -> None:
        """Register ``provider`` under its :attr:`DataProvider.name`.

        Raises ``ValueError`` if a provider with the same name is already
        registered. Capabilities listed by the provider are added to the
        capability index; overlapping capabilities across providers are
        allowed (that's how fallback chains are built).
        """
        name = self._coerce_name(provider)
        if name in self._providers:
            raise ValueError(
                f"Provider named {name!r} is already registered; "
                "use a different name or call unregister() first"
            )
        self._providers[name] = provider
        for capability in provider.capabilities:
            capability = self._coerce_capability(capability)
            self._by_capability.setdefault(capability, []).append(provider)

    def unregister(self, name: str) -> bool:
        """Remove the provider named ``name``. Returns whether anything was removed."""
        provider = self._providers.pop(name, None)
        if provider is None:
            return False
        for capability, providers in list(self._by_capability.items()):
            self._by_capability[capability] = [
                p for p in providers if p.name != name
            ]
            if not self._by_capability[capability]:
                self._by_capability.pop(capability, None)
        return True

    def clear(self) -> None:
        """Remove every registered provider (test convenience)."""
        self._providers.clear()
        self._by_capability.clear()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, name: str) -> DataProvider | None:
        """Return the provider named ``name`` or ``None`` if absent."""
        return self._providers.get(name)

    def list_providers(self) -> list[DataProvider]:
        """Return every registered provider, in insertion order."""
        return list(self._providers.values())

    def list_provider_names(self) -> list[str]:
        """Return every registered provider name, in insertion order."""
        return list(self._providers.keys())

    def list_capabilities(self) -> set[str]:
        """Return the set of all capabilities declared by any provider."""
        return set(self._by_capability.keys())

    def get_providers(
        self,
        capability: str,
        market: Market | str | None = None,
    ) -> list[DataProvider]:
        """Return providers that serve ``capability`` (and ``market`` if given).

        The returned list is in registration order; the caller is free
        to apply priority, filtering or fallback logic on top of it.

        If ``market`` is provided, providers that do not cover it are
        removed from the result. Unknown capability / market returns
        an empty list — never raises.
        """
        capability = self._coerce_capability_or_none(capability)
        if capability is None:
            return []
        providers = list(self._by_capability.get(capability, ()))
        if market is None:
            return providers
        market_enum = self._coerce_market(market)
        if market_enum is None:
            return []
        return [p for p in providers if market_enum in p.markets]

    def has_capability(
        self,
        capability: str,
        market: Market | str | None = None,
    ) -> bool:
        """Return ``True`` if any registered provider can serve the request."""
        return bool(self.get_providers(capability, market))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_name(provider: DataProvider) -> str:
        name = getattr(provider, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Provider must expose a non-empty string name, got {name!r}"
            )
        return name

    @staticmethod
    def _coerce_capability(capability: object) -> str:
        if not isinstance(capability, str) or not capability.strip():
            raise ValueError(
                f"capability must be a non-empty string, got {capability!r}"
            )
        if capability.count(".") != 1:
            raise ValueError(
                f"capability must look like 'domain.operation', got {capability!r}"
            )
        return capability

    @staticmethod
    def _coerce_capability_or_none(capability: object) -> str | None:
        if capability is None:
            return None
        try:
            return ProviderRegistry._coerce_capability(capability)
        except ValueError:
            return None

    @staticmethod
    def _coerce_market(market: Market | str) -> Market | None:
        if isinstance(market, Market):
            return market
        try:
            return Market(market)
        except ValueError:
            return None


__all__ = ["ProviderRegistry"]