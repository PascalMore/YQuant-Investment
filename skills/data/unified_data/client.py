"""Consumer-facing facade for unified_data.

:class:`UnifiedDataClient` is what every consumer (stock framework, TA-CN
adapter, Argus, portfolio, ...) is expected to use. It owns a
:class:`ProviderRegistry` and a :class:`DataRouter`, and exposes a thin
``query`` method that simply forwards to the router.

Phase 1A extensions
-------------------
The facade additionally accepts a :class:`TA_CNMongoAdapter` and exposes
14 domain-specific entry methods (see DESIGN-03-007 §Phase 1A "14 行
完整 collection × canonical × service × client 矩阵"). These methods
delegate to the five domain services (``MarketDataService``,
``FundamentalService``, ``SectorService``, ``EventService``,
``MetadataService``) and return :class:`DataResult` instances.

The Phase 1A entry methods are independent of the provider registry /
fallback router — they bypass both and use the injected adapter
directly. This keeps Phase 0 ``query`` semantics unchanged while adding
the Phase 1A convenience surface for consumers that already hold a
``TA_CNMongoAdapter``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .config import UnifiedDataConfig
from .models import DataResult, Market, SecurityId
from .provider import DataProvider
from .registry import ProviderRegistry
from .router import DataRouter
from .adapters import TA_CNMongoAdapter
from .services import (
    EventService,
    FundamentalService,
    MarketDataService,
    MetadataService,
    SectorService,
)


class UnifiedDataClient:
    """Facade that ties the registry, the router and the Phase 1A
    domain services together.
    """

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        config: UnifiedDataConfig | None = None,
        *,
        ta_cn_adapter: TA_CNMongoAdapter | None = None,
    ) -> None:
        self._registry = registry if registry is not None else ProviderRegistry()
        self._config = config or UnifiedDataConfig.minimal()
        self._router = DataRouter(self._registry, self._config)
        self._ta_cn_adapter = ta_cn_adapter
        self._market_data_service: MarketDataService | None = None
        self._fundamental_service: FundamentalService | None = None
        self._sector_service: SectorService | None = None
        self._event_service: EventService | None = None
        self._metadata_service: MetadataService | None = None

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

    @property
    def ta_cn_adapter(self) -> TA_CNMongoAdapter | None:
        """The Phase 1A TA-CN MongoDB adapter (read-only) or ``None``."""
        return self._ta_cn_adapter

    def register_provider(self, provider: DataProvider) -> None:
        """Register ``provider`` with the underlying registry."""
        self._registry.register(provider)

    # ------------------------------------------------------------------
    # Query (Phase 0 surface — unchanged)
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
    # Phase 1A domain services — lazy construction
    # ------------------------------------------------------------------

    def _require_ta_cn(self) -> TA_CNMongoAdapter:
        if self._ta_cn_adapter is None:
            raise RuntimeError(
                "UnifiedDataClient was constructed without a TA_CNMongoAdapter; "
                "pass `ta_cn_adapter=...` to enable Phase 1A domain methods."
            )
        return self._ta_cn_adapter

    def _market_data(self) -> MarketDataService:
        if self._market_data_service is None:
            self._market_data_service = MarketDataService(self._require_ta_cn())
        return self._market_data_service

    def _fundamental(self) -> FundamentalService:
        if self._fundamental_service is None:
            self._fundamental_service = FundamentalService(self._require_ta_cn())
        return self._fundamental_service

    def _sector(self) -> SectorService:
        if self._sector_service is None:
            self._sector_service = SectorService(self._require_ta_cn())
        return self._sector_service

    def _event(self) -> EventService:
        if self._event_service is None:
            self._event_service = EventService(self._require_ta_cn())
        return self._event_service

    def _metadata(self) -> MetadataService:
        if self._metadata_service is None:
            self._metadata_service = MetadataService(self._require_ta_cn())
        return self._metadata_service

    # ------------------------------------------------------------------
    # Phase 1A entry methods — 14 total (DESIGN-03-007 §Phase 1A 完整矩阵)
    # ------------------------------------------------------------------

    # 1. stock_basic_info / StockInfo
    def get_stock_info(self, security_id: SecurityId) -> DataResult:
        return self._metadata().get_stock_info(security_id)

    # 2. stock_basic_info / list[StockInfo]
    def get_stock_list(
        self,
        market: str = "CN",
        status: str = "L",
        limit: int = 0,
    ) -> DataResult:
        return self._metadata().get_stock_list(market=market, status=status, limit=limit)

    # 3. market_quotes / RealtimeQuote
    def get_realtime_quote(self, security_id: SecurityId) -> DataResult:
        return self._market_data().get_realtime_quote(security_id)

    # 4. stock_daily_quotes / list[DailyBar]
    def get_kline_daily(
        self,
        security_id: SecurityId,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> DataResult:
        return self._market_data().get_kline_daily(
            security_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    # 5. stock_financial_data / FinancialStatement (income)
    def get_income_statement(
        self,
        security_id: SecurityId,
        report_period: str | None = None,
    ) -> DataResult:
        return self._fundamental().get_income_statement(security_id, report_period)

    # 6. stock_financial_data / FinancialStatement (balance)
    def get_balance_sheet(
        self,
        security_id: SecurityId,
        report_period: str | None = None,
    ) -> DataResult:
        return self._fundamental().get_balance_sheet(security_id, report_period)

    # 7. stock_financial_data / FinancialStatement (cashflow)
    def get_cash_flow(
        self,
        security_id: SecurityId,
        report_period: str | None = None,
    ) -> DataResult:
        return self._fundamental().get_cash_flow(security_id, report_period)

    # 8. stock_news / list[NewsItem]
    def get_news(
        self,
        security_id: SecurityId,
        limit: int = 20,
    ) -> DataResult:
        return self._event().get_news(security_id, limit=limit)

    # 9. index_basic_info / IndexInfo
    def get_index_info(self, security_id: SecurityId) -> DataResult:
        return self._metadata().get_index_info(security_id)

    # 10. index_basic_info / list[IndexInfo]
    def get_index_list(self, market: str = "CN") -> DataResult:
        return self._metadata().get_index_list(market=market)

    # 11. index_daily_quotes / list[IndexDailyBar] (market index path)
    def get_index_daily(
        self,
        security_id: SecurityId,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> DataResult:
        return self._market_data().get_index_daily(
            security_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    # 12. index_daily_quotes / list[IndexDailyBar] (sector path)
    def get_sector_index_bars(
        self,
        sector_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> DataResult:
        return self._sector().get_sector_index_bars(
            sector_code,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    # 13. stock_sector_info / list[SectorClassification]
    def get_stock_sector(
        self,
        security_id: SecurityId,
        classify_system: str | None = "SW",
    ) -> DataResult:
        return self._sector().get_stock_sector(
            security_id,
            classify_system=classify_system,
        )

    # 14. stock_sector_info / list[SectorClassification]
    def get_stocks_by_sector(
        self,
        sector_code: str,
        classify_system: str = "SW",
    ) -> DataResult:
        return self._sector().get_stocks_by_sector(
            sector_code,
            classify_system=classify_system,
        )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def with_providers(
        cls,
        providers: list[DataProvider],
        config: UnifiedDataConfig | None = None,
        *,
        ta_cn_adapter: TA_CNMongoAdapter | None = None,
    ) -> "UnifiedDataClient":
        """Build a client pre-populated with ``providers``.

        Providers are registered in the given order, which becomes the
        fallback order when no explicit chain is configured.
        Optionally attach a Phase 1A ``ta_cn_adapter`` to enable the
        domain-specific entry methods.
        """
        client = cls(config=config, ta_cn_adapter=ta_cn_adapter)
        for provider in providers:
            client.register_provider(provider)
        return client


__all__ = ["UnifiedDataClient"]
