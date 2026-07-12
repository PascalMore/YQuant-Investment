"""unified_data — YQuant Unified Data Layer (Phase 0 skeleton).

This package defines the *core abstractions* for the unified data layer
specified in RFC-03-007 / SPEC-03-007 / DESIGN-03-007. Phase 0 ships only
the skeleton: no provider adapters, no MongoDB persistence, no external
API calls. Subsequent phases (Phase 1+) will add real providers.

Public surface (Phase 0):

    SecurityId        -- immutable cross-market security identifier
    Market            -- enumeration of supported markets
    DataResult        -- standard data return value with metadata
    DataProvider      -- abstract base class for data sources
    Capability        -- value object describing a provider capability
    ProviderRegistry  -- in-memory registry of providers
    DataRouter        -- routes a query through a fallback chain
    UnifiedDataClient -- consumer-facing facade
    UnifiedDataConfig -- minimal configuration dataclass

Exceptions (see ``exceptions`` module):

    UnifiedDataError          -- base class
    InvalidSecurityIdError    -- bad market / symbol input
    UnsupportedCapabilityError-- provider lacks capability
    ProviderUnavailableError  -- provider cannot serve the request
    ProviderError             -- provider raised an internal error
    AllProvidersFailedError   -- every provider in the chain failed

Phase 0 scope intentionally excludes:
    * MongoDB cache (CacheManager)
    * FreshnessPolicy / TTL logic
    * Real provider adapters (Tushare / AKShare / ...)
    * Audit / quality scoring
    * Production persistence

Anything beyond the abstractions listed above belongs to a later phase.
"""

from .exceptions import (
    AllProvidersFailedError,
    InvalidSecurityIdError,
    ProviderError,
    ProviderUnavailableError,
    UnifiedDataError,
    UnsupportedCapabilityError,
)
from .models import (
    Capability,
    DataResult,
    FreshnessLabel,
    Market,
    SecurityId,
)
from .provider import DataProvider
from .registry import ProviderRegistry
from .router import DataRouter
from .client import UnifiedDataClient
from .config import UnifiedDataConfig

__all__ = [
    # exceptions
    "UnifiedDataError",
    "InvalidSecurityIdError",
    "UnsupportedCapabilityError",
    "ProviderUnavailableError",
    "ProviderError",
    "AllProvidersFailedError",
    # models
    "SecurityId",
    "Market",
    "DataResult",
    "Capability",
    "FreshnessLabel",
    # core abstractions
    "DataProvider",
    "ProviderRegistry",
    "DataRouter",
    "UnifiedDataClient",
    "UnifiedDataConfig",
]