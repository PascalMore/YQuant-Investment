"""unified_data — YQuant Unified Data Layer (Phase 0 skeleton + Phase 1A).

Phase 0 ships the core abstractions: ``SecurityId``, ``DataResult``,
``DataProvider``, ``ProviderRegistry``, ``DataRouter``,
``UnifiedDataClient`` and ``UnifiedDataConfig``.

Phase 1A (DESIGN-03-007 §Phase 1A) adds the TA-CN MongoDB read-only
adapter (``TA_CNMongoAdapter``), eight canonical domain objects under
``skills.data.unified_data.models.domain``, five domain services
under ``skills.data.unified_data.services``, and 14 convenience entry
methods on :class:`UnifiedDataClient`. The TA-CN adapter is read-only:
it never ``insert``/``update``/``delete`` documents and never creates
collections or indexes.

Public surface
--------------

Phase 0 (unchanged):
    SecurityId, Market, DataResult, Capability, FreshnessLabel,
    DataProvider, ProviderRegistry, DataRouter, UnifiedDataClient,
    UnifiedDataConfig

Phase 1A additions:
    TA_CNMongoAdapter (adapters package)
    MarketDataService, FundamentalService, SectorService, EventService,
    MetadataService (services package)
    DailyBar, IndexDailyBar, RealtimeQuote, FinancialStatement,
    NewsItem, SectorClassification, StockInfo, IndexInfo (canonical
    domain objects)

13 (Phase 0) + 1 (TA_CNMongoAdapter) + 5 (services) + 8 (canonical
domain objects) + 1 (FreshnessLabel stays) = same exported set plus
the new Phase 1A symbols.

Phase 0 scope intentionally excludes:
    * MongoDB cache (CacheManager) — Phase 1B
    * FreshnessPolicy / TTL logic — Phase 1B
    * Real provider adapters (Tushare / AKShare / ...) — Phase 1B
    * Audit / quality scoring — Phase 2
    * Production persistence (Phase 1A adapter is read-only)
"""

from .exceptions import (
    AllProvidersFailedError,
    InvalidSecurityIdError,
    ProviderError,
    ProviderUnavailableError,
    UnifiedDataError,
    UnsupportedCapabilityError,
)
from .freshness import FreshnessPolicy
from .models import (
    Capability,
    DataResult,
    FreshnessLabel,
    Market,
    SecurityId,
)
from .models.domain import (
    DailyBar,
    FinancialStatement,
    IndexDailyBar,
    IndexInfo,
    NewsItem,
    RealtimeQuote,
    SectorClassification,
    StockInfo,
)
from .provider import DataProvider
from .registry import ProviderRegistry
from .router import DataRouter
from .adapters import TA_CNMongoAdapter
from .cache_manager import CacheManager
from .local_mongo_adapter import LocalMongoAdapter
from .providers import (
    AKShareProvider,
    BaseExternalProvider,
    FakeKlineClient,
    KlineClient,
    RateLimiter,
    TushareProvider,
)
from .services import (
    EventService,
    FundamentalService,
    MarketDataService,
    MetadataService,
    SectorService,
)
from .audit import AuditLogger
from .client import UnifiedDataClient
from .config import UnifiedDataConfig
from .quality import (
    QualityScorer,
    QualityScorerConfig,
    QualitySummary,
    ScoredResult,
)

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
    # adapters (Phase 1A)
    "TA_CNMongoAdapter",
    # services (Phase 1A)
    "MarketDataService",
    "FundamentalService",
    "SectorService",
    "EventService",
    "MetadataService",
    # canonical domain objects (Phase 1A)
    "DailyBar",
    "IndexDailyBar",
    "RealtimeQuote",
    "FinancialStatement",
    "NewsItem",
    "SectorClassification",
    "StockInfo",
    "IndexInfo",
    # Phase 1B-A
    "FreshnessPolicy",
    "FakeKlineClient",
    "KlineClient",
    "TushareProvider",
    "AKShareProvider",
    "BaseExternalProvider",
    "RateLimiter",
    # Phase 1B-B — persistence + cache plane
    "LocalMongoAdapter",
    "CacheManager",
    # Phase 2 — quality + audit governance (DESIGN-03-011)
    "QualityScorer",
    "QualityScorerConfig",
    "ScoredResult",
    "QualitySummary",
    "AuditLogger",
]
