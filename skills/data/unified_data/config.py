"""Configuration dataclass for unified_data.

Phase 0 keeps configuration intentionally tiny: only what the skeleton
needs to wire registry + router together. No MongoDB connection, no
provider-specific credentials — those will live in dedicated modules in
later phases.

The dataclass is deliberately read-only (``frozen=True``) so it can be
shared across threads without defensive copying.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


_DEFAULT_FALLBACK_CHAIN: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UnifiedDataConfig:
    """Minimal configuration for the Phase 0 skeleton.

    Attributes:
        default_fallback_chain: Ordered tuple of provider names used by
            :class:`DataRouter` when a capability does not specify its
            own chain. An empty tuple means "use the registry order".
        capability_fallback_overrides: Optional per-capability override
            for the fallback chain. Keys are capability strings
            (``"market_data.kline_daily"``), values are ordered tuples
            of provider names.
        consumer: Identifier of the calling consumer, propagated into
            audit / metrics in later phases.
    """

    default_fallback_chain: tuple[str, ...] = _DEFAULT_FALLBACK_CHAIN
    capability_fallback_overrides: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    consumer: str = "unified_data"

    def fallback_for(self, capability: str) -> tuple[str, ...]:
        """Return the fallback chain to use for ``capability``.

        Looks up the per-capability override first; falls back to
        :attr:`default_fallback_chain`. The returned tuple may be empty
        if no chain is configured — callers are expected to interpret
        that as "use registry order".
        """
        override = self.capability_fallback_overrides.get(capability)
        if override is not None:
            return tuple(override)
        return self.default_fallback_chain

    @classmethod
    def minimal(cls) -> "UnifiedDataConfig":
        """Return a config with safe defaults and no provider pinning."""
        return cls()