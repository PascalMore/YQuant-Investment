"""Data router for unified_data.

The :class:`DataRouter` is the central piece that turns a query
(``domain``, ``operation``, ``security_id``, ``**params``) into a
:class:`DataResult`. It does so by:

1. Resolving the capability string (``"domain.operation"``).
2. Building an ordered fallback chain from
   :class:`UnifiedDataConfig` (per-capability override → default).
3. Trying providers in order, skipping those that declare the capability
   but are unavailable (:meth:`DataProvider.is_available` returns
   ``False``).
4. Catching per-provider exceptions and recording them in
   ``source_trace`` until either one succeeds or every provider has
   been tried.
5. Wrapping the final outcome in a :class:`DataResult`. If everything
   fails, the router raises :class:`AllProvidersFailedError`.

The router has no I/O of its own — no MongoDB, no HTTP — so it can be
unit-tested purely with fake providers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .config import UnifiedDataConfig
from .exceptions import (
    AllProvidersFailedError,
    ProviderError,
    ProviderUnavailableError,
    UnsupportedCapabilityError,
)
from .models import DataResult, Market, SecurityId
from .provider import DataProvider
from .registry import ProviderRegistry


class DataRouter:
    """Capability-aware query router with fallback support."""

    def __init__(
        self,
        registry: ProviderRegistry,
        config: UnifiedDataConfig | None = None,
    ) -> None:
        self._registry = registry
        self._config = config or UnifiedDataConfig.minimal()

    @property
    def registry(self) -> ProviderRegistry:
        """The provider registry the router queries."""
        return self._registry

    @property
    def config(self) -> UnifiedDataConfig:
        """The active configuration."""
        return self._config

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

        Args:
            domain: Domain name (``"market_data"``, ``"financial"``...).
            operation: Operation within the domain
                (``"kline_daily"``, ``"income_statement"``...).
            security_id: The security being queried.
            provider: Optional name of a specific provider to use. When
                given, the fallback chain is bypassed and the named
                provider is used directly. If it cannot serve the
                request, :class:`AllProvidersFailedError` is raised with
                a single-entry attempt list.
            market: Optional market filter. Defaults to
                ``security_id.market``.
            params: Forwarded to :meth:`DataProvider.fetch`.
            fetched_at: Override for the timestamp recorded on the
                result. Defaults to ``datetime.utcnow()``.

        Returns:
            A :class:`DataResult` from the first provider that succeeds.

        Raises:
            AllProvidersFailedError: When every provider in the chain
                failed.
            ValueError: When ``domain``/``operation`` are malformed
                (the router does not silently coerce them).
        """
        capability = _validate_capability(domain, operation)
        market_enum = self._resolve_market(market, security_id)
        params_dict = dict(params or {})
        ts = fetched_at or datetime.now(timezone.utc).replace(tzinfo=None)

        chain = self._resolve_chain(capability, provider)

        attempts: list[tuple[str, Any]] = []
        trace: list[str] = []
        last_error: BaseException | None = None

        for provider_name in chain:
            provider_obj = self._registry.get(provider_name)
            if provider_obj is None:
                attempts.append((provider_name, "not registered"))
                trace.append(f"{provider_name}(skipped: not registered)")
                continue
            if not provider_obj.supports(capability, market_enum):
                attempts.append(
                    (provider_name, f"does not cover {capability} for {market_enum.value}")
                )
                trace.append(
                    f"{provider_name}(skipped: capability/market mismatch)"
                )
                continue
            if not provider_obj.is_available():
                attempts.append((provider_name, "is_available() returned False"))
                trace.append(f"{provider_name}(skipped: unavailable)")
                continue

            try:
                payload = provider_obj.fetch(
                    domain,
                    operation,
                    security_id,
                    **params_dict,
                )
            except UnsupportedCapabilityError as exc:
                # Defensive: a provider that "supports" via the registry
                # but raised here is recorded and we move on.
                attempts.append((provider_name, exc))
                trace.append(f"{provider_name}(error: {exc})")
                last_error = exc
                continue
            except ProviderUnavailableError as exc:
                attempts.append((provider_name, exc))
                trace.append(f"{provider_name}(unavailable: {exc})")
                last_error = exc
                continue
            except ProviderError as exc:
                attempts.append((provider_name, exc))
                trace.append(f"{provider_name}(error: {exc})")
                last_error = exc
                continue

            trace.append(f"{provider_name}(ok)")
            return DataResult.success(
                data=payload,
                security_id=security_id,
                domain=domain,
                operation=operation,
                provider=provider_name,
                fetched_at=ts,
                source_trace=trace,
            )

        # All providers failed or were skipped. If the only "skipped"
        # entries are unavoidable (no providers in registry / forced
        # provider missing), surface AllProvidersFailedError so callers
        # can decide whether to retry or fall back to a hard-coded path.
        if not attempts:
            # No providers were even considered — registry had nothing.
            raise AllProvidersFailedError(capability=capability, attempts=[])

        raise AllProvidersFailedError(
            capability=capability,
            attempts=attempts,
            message=None,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_chain(
        self,
        capability: str,
        forced_provider: str | None,
    ) -> tuple[str, ...]:
        """Compute the ordered provider-name chain to try."""
        if forced_provider is not None:
            return (forced_provider,)
        override = self._config.fallback_for(capability)
        if override:
            return tuple(override)
        # Fall back to the registry's own ordering for the capability.
        candidates = self._registry.get_providers(capability)
        return tuple(p.name for p in candidates)

    @staticmethod
    def _resolve_market(
        market: Market | str | None,
        security_id: SecurityId,
    ) -> Market:
        if market is None:
            return security_id.market
        if isinstance(market, Market):
            return market
        try:
            return Market(market)
        except ValueError as exc:
            raise ValueError(
                f"Unknown market {market!r}; expected one of "
                f"{[m.value for m in Market]}"
            ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_capability(domain: str, operation: str) -> str:
    """Validate and combine ``domain`` + ``operation`` into a capability."""
    if not isinstance(domain, str) or not domain.strip() or "." in domain:
        raise ValueError(f"domain must be a non-empty string without '.', got {domain!r}")
    if not isinstance(operation, str) or not operation.strip() or "." in operation:
        raise ValueError(
            f"operation must be a non-empty string without '.', got {operation!r}"
        )
    return f"{domain}.{operation}"


__all__ = ["DataRouter"]


_ = (Iterable, Mapping)  # keep typing imports referenced for static checkers