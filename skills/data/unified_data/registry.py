"""Provider registry for unified_data.

The :class:`ProviderRegistry` is an in-memory mapping from capability to
the list of providers that declare that capability, plus a name → provider
map for O(1) lookup. Phase 2 governance (DESIGN-03-011 §4.1, §4.4) adds
per-provider ``priority`` and ``health`` state, and ``unregister`` /
``clear`` reset that state so re-registration starts from defaults.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from .models import Market
from .provider import DataProvider


class ProviderRegistry:
    """In-memory registry of :class:`DataProvider` instances.

    Capabilities and provider names are normalized at registration time
    so ``get_providers`` returns a list in registration order when all
    priorities equal the default.

    Phase 1B-A: :attr:`_external_fallback_chains` overrides the external
    fallback chain per capability (``set_external_fallback_chains`` /
    ``get_external_fallback_chain``); the Router resolves its chain in
    priority ``external_fallback_chains[capability] → config
    .fallback_for(capability) → registry insertion order``.

    Phase 2 (DESIGN-03-011 §4.1, §4.4): ``set_priority`` / ``set_health``
    manage per-provider ``priority`` (default 100) and ``health`` (default
    ``"healthy"``); ``get_providers`` sorts by ``(priority,
    insertion_order)`` and applies the optional ``state_filter`` (``None``
    preserves Phase 0 behaviour); ``unregister`` and ``clear`` atomically
    reset ``_priorities`` and ``_health_states`` so re-registering the same
    name starts from defaults (SPEC §4.3 P2-U1/P2-U2).
    ``_external_fallback_chains`` is configuration state and is left
    untouched by ``clear``.
    """

    _DEFAULT_PRIORITY: int = 100
    _ALLOWED_HEALTH_STATES: frozenset[str] = frozenset(
        {"healthy", "unhealthy", "disabled"}
    )

    def __init__(self) -> None:
        self._providers: dict[str, DataProvider] = {}
        self._by_capability: dict[str, list[DataProvider]] = {}
        self._external_fallback_chains: dict[str, list[str]] = {}
        self._priorities: dict[str, int] = {}
        self._health_states: dict[str, str] = {}

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
        """Remove the provider named ``name``. Returns whether anything was removed.

        同步清理 ``_priorities`` / ``_health_states`` 中该 provider 的残留
        状态（DESIGN §4.4.1）。
        """
        provider = self._providers.pop(name, None)
        if provider is None:
            return False
        for capability, providers in list(self._by_capability.items()):
            self._by_capability[capability] = [
                p for p in providers if p.name != name
            ]
            if not self._by_capability[capability]:
                self._by_capability.pop(capability, None)
        self._priorities.pop(name, None)
        self._health_states.pop(name, None)
        return True

    def clear(self) -> None:
        """Remove every registered provider (test convenience).

        Phase 2 reset: also clears ``_priorities`` / ``_health_states`` so
        re-registering the same name returns to defaults (SPEC §4.3 P2-U2,
        DESIGN §4.4.2). ``_external_fallback_chains`` is configuration
        state, not registration state, and is left untouched.
        """
        self._providers.clear()
        self._by_capability.clear()
        self._priorities.clear()
        self._health_states.clear()

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
        state_filter: str | None = None,
    ) -> list[DataProvider]:
        """Return providers that serve ``capability`` (and ``market`` if given).

        始终按 ``(priority, insertion_order)`` 稳定排序：当所有 provider
        都使用默认 priority（100）时，注册顺序与原 Phase 0 行为一致，
        不会因引入排序而偷换调用方语义（DESIGN §4.1）。

        Phase 2 增强：可选 ``state_filter`` —— ``"healthy"`` /
        ``"unhealthy"`` / ``"disabled"``，先按状态过滤再按上述顺序输出；
        ``None`` 保持 Phase 0 兼容（即不过滤状态）。

        If ``market`` is provided, providers that do not cover it are
        removed from the result. Unknown capability / market returns
        an empty list — never raises.
        """
        capability = self._coerce_capability_or_none(capability)
        if capability is None:
            return []
        providers = list(self._by_capability.get(capability, ()))
        if market is not None:
            market_enum = self._coerce_market(market)
            if market_enum is None:
                return []
            providers = [p for p in providers if market_enum in p.markets]
        if state_filter is not None:
            providers = [
                p for p in providers
                if self._health_states.get(p.name, "healthy") == state_filter
            ]
        # 稳定排序：按 priority 升序，同 priority 时保持注册顺序
        provider_order = {name: idx for idx, name in enumerate(self._providers)}
        providers.sort(
            key=lambda p: (
                self._priorities.get(p.name, self._DEFAULT_PRIORITY),
                provider_order.get(p.name, 0),
            )
        )
        return providers

    def has_capability(
        self,
        capability: str,
        market: Market | str | None = None,
    ) -> bool:
        """Return ``True`` if any registered provider can serve the request."""
        return bool(self.get_providers(capability, market))

    # ------------------------------------------------------------------
    # Phase 2: Priority & Health State
    # ------------------------------------------------------------------

    def set_priority(self, name: str, priority: int) -> None:
        """设置 provider 的优先级（数值越小越优先）。

        未知 provider → ValueError（fail-fast，不静默忽略）。
        """
        if name not in self._providers:
            raise ValueError(f"Provider {name!r} is not registered")
        self._priorities[name] = priority

    def get_priority(self, name: str) -> int:
        """返回 provider 的优先级。未设置时返回 _DEFAULT_PRIORITY (100)。"""
        return self._priorities.get(name, self._DEFAULT_PRIORITY)

    def set_health(self, name: str, state: str) -> None:
        """设置 provider 的运行健康状态。

        Args:
            name: provider 名称。
            state: ``"healthy"`` / ``"unhealthy"`` / ``"disabled"``。

        Raises:
            ValueError: provider 未注册或 state 非法。
        """
        if name not in self._providers:
            raise ValueError(f"Provider {name!r} is not registered")
        if state not in self._ALLOWED_HEALTH_STATES:
            raise ValueError(
                f"state must be 'healthy', 'unhealthy', or 'disabled', got {state!r}"
            )
        self._health_states[name] = state

    def get_health(self, name: str) -> str:
        """返回 provider 的健康状态。未设置时返回 ``"healthy"``。"""
        return self._health_states.get(name, "healthy")

    # ------------------------------------------------------------------
    # Phase 1B-A: external fallback chain overrides
    # ------------------------------------------------------------------

    def set_external_fallback_chains(
        self,
        chains: Mapping[str, Sequence[str]],
    ) -> None:
        """Inject the ``external_fallback_chains`` configuration.

        ``chains`` maps ``capability → ordered provider name list``.
        Replaces any previously stored chains. Unknown capability
        strings are accepted (the Router will simply ignore them when
        no provider ever claims the capability).

        Args:
            chains: A mapping from capability string to an ordered
                sequence of provider names. Each sequence is copied
                so later caller-side mutations cannot affect the
                stored configuration.
        """
        self._external_fallback_chains = {
            key: list(names) for key, names in chains.items()
        }

    def get_external_fallback_chain(self, capability: str) -> list[str]:
        """Return the explicit external fallback chain for ``capability``.

        Returns ``[]`` when no chain has been configured for the
        capability — callers are expected to treat that as
        "fall back to the next priority level".
        """
        return list(self._external_fallback_chains.get(capability, []))

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