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
from .freshness import FreshnessPolicy
from .models import DataResult, Market, SecurityId
from .provider import DataProvider
from .registry import ProviderRegistry
from .router import DataRouter
from .adapters import TA_CNMongoAdapter
from .services import (
    EventService,
    FlowService,
    FundamentalService,
    MarketDataService,
    MetadataService,
    PersistenceResult,
    SectorService,
)
# Phase 3 P3-B (T3-B): market sentiment service is a sibling of
# SectorService but at the market level (no TA-CN surface). The import
# stays local (mirrors the T3-B precedent) so the package-level
# ``__all__`` does not need to widen in the T3-B allowlist.
from .services.sentiment_service import MarketSentimentService


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
        freshness: FreshnessPolicy | None = None,
        external_fallback_chains: dict[str, list[str]] | None = None,
        p3_writer: Any | None = None,
    ) -> None:
        self._registry = registry if registry is not None else ProviderRegistry()
        self._config = config or UnifiedDataConfig.minimal()
        self._ta_cn_adapter = ta_cn_adapter
        # Phase 1B-A: the Router now takes the TA-CN adapter, the
        # freshness policy and the per-capability external chain
        # overrides. When ``ta_cn_adapter`` is None the Router
        # transparently degrades to a Phase 0 external-fallback-only
        # router.
        self._router = DataRouter(
            self._registry,
            self._config,
            ta_cn_adapter=ta_cn_adapter,
            freshness=freshness,
            external_fallback_chains=external_fallback_chains,
            # Phase 3 P3-B (T3-P3B): the optional P3 writer is
            # forwarded to the router so its read path can consult
            # it as a read cache (M1 read-only guard still prevents
            # the writer from being mutated on the read path).
            p3_writer=p3_writer,
        )
        self._market_data_service: MarketDataService | None = None
        self._fundamental_service: FundamentalService | None = None
        self._sector_service: SectorService | None = None
        self._event_service: EventService | None = None
        self._metadata_service: MetadataService | None = None
        # Phase 3 P3-B (T3-B): market sentiment service is a separate
        # lazy attribute. We keep the ``None`` default so the rest of
        # the existing service surface keeps its old behaviour. The
        # service is wired against the existing router + the
        # optional ``p3_writer`` (None in T3-B; T3-C injects one).
        self._sentiment_service: MarketSentimentService | None = None
        # Phase 3 P3-B (T3-P3B): per-symbol capital-flow service is a
        # separate lazy attribute. We keep the ``None`` default so the
        # rest of the existing service surface keeps its old behaviour.
        # The service is wired against the existing router + the
        # optional ``p3_writer`` (None in T3-P3B; future Gate-authorised
        # sub-stages inject one).
        self._flow_service: FlowService | None = None
        # Phase 3 P3-B (T3-P3B): keep a private reference to the
        # optionally-injected writer so the lazy service loader can
        # forward it without forcing callers to plumb both the
        # client and the writer separately.
        self._p3_writer = p3_writer

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
        force_refresh: bool = False,
        market: Market | str | None = None,
        params: Mapping[str, Any] | None = None,
        fetched_at: datetime | None = None,
    ) -> DataResult:
        """Route ``security_id`` to a provider and return a DataResult.

        See :meth:`DataRouter.query` for the full semantics. This method
        exists purely as a stable entry point for consumers that prefer
        to depend on the client object rather than the router directly.

        ``force_refresh`` is a Phase 1B-A addition: when ``True`` the
        Router skips Step 1 (TA-CN) and any future cache layer. The
        parameter is keyword-only and defaults to ``False`` so the
        signature stays backward-compatible with Phase 0 / 1A callers.
        """
        return self._router.query(
            domain,
            operation,
            security_id,
            provider=provider,
            force_refresh=force_refresh,
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

    # Phase 3 P3-B (T3-B): lazy ``MarketSentimentService`` loader.
    #
    # Deliberately **not** gated behind ``_require_ta_cn`` — sentiment
    # has no TA-CN surface so the TA-CN adapter is optional (the
    # service accepts ``adapter=None``). The router is the *only*
    # required dependency; it is wired against the registry the
    # client already owns. When ``ta_cn_adapter`` was injected we
    # forward it (future-proofing — T3-C may use it for sector-breadth
    # cross-checks); when it was not we pass ``None``.
    def _get_sentiment_service(self) -> MarketSentimentService:
        if self._sentiment_service is None:
            self._sentiment_service = MarketSentimentService(
                adapter=self._ta_cn_adapter,
                router=self._router,
                p3_writer=self._p3_writer,
            )
        return self._sentiment_service

    # Phase 3 P3-B (T3-P3B): lazy ``FlowService`` loader.
    #
    # Deliberately **not** gated behind ``_require_ta_cn`` — capital-flow
    # has no TA-CN surface so the TA-CN adapter is optional (the
    # service accepts ``adapter=None``). The router is the *only*
    # required dependency; it is wired against the registry the client
    # already owns. When ``ta_cn_adapter`` was injected we forward it
    # (future-proofing — future Gate-authorised sub-stages may use it
    # for cross-validation); when it was not we pass ``None``. The
    # ``p3_writer`` is forwarded from the optional client kwarg so
    # ``refresh_capital_flow`` has a writer available without callers
    # having to build a FlowService by hand.
    def _get_flow_service(self) -> FlowService:
        if self._flow_service is None:
            self._flow_service = FlowService(
                adapter=self._ta_cn_adapter,
                router=self._router,
                p3_writer=self._p3_writer,
                # ``audit_logger`` defaults to ``None`` for T3-P3B.
            )
        return self._flow_service

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
    # Phase 3 P3-B entry methods (DESIGN-03-014 §5.2 + SPEC-03-014 §5.1)
    # ------------------------------------------------------------------

    # P3-B.1 — get_capital_flow (per-symbol daily flow)
    def get_capital_flow(
        self,
        security_id: SecurityId,
        *,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 60,
    ) -> DataResult:
        """Return per-symbol capital-flow rows for ``security_id``.

        Routes through ``flow.capital_flow_daily`` via the standard
        internal-first chain. ``DataResult.data`` is a
        ``list[CapitalFlowRecord]`` (T3-P3B M2 canonical object
        contract — shaped at the service boundary).

        The read path is read-only; explicit refresh is via
        ``flow_service.refresh_capital_flow(...)`` (T3-P3B reserves
        the write path for a Gate-authorised sub-stage).
        """
        return self._get_flow_service().get_capital_flow(
            security_id,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    # P3-B.2 — get_northbound_flow (market-level northbound)
    def get_northbound_flow(
        self,
        security_id: SecurityId | None = None,
        *,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> DataResult:
        """Return northbound capital-flow rows.

        Routes through ``flow.northbound_daily``. The canonical
        projection (V0.5 §3.2 ``record_scope``) is enforced at the
        service boundary: the only populated fields on the returned
        :class:`CapitalFlowRecord`s are ``{symbol, market,
        trade_date}`` business-key + ``northbound_*`` + ``fetched_at``
        + ``provider``; the rest are ``None``. ``security_id`` is
        optional — a ``None`` value triggers a market-level query
        (placeholder synthesised at the service layer, matching the
        :class:`MarketSentimentService` precedent).
        """
        return self._get_flow_service().get_northbound_flow(
            security_id=security_id,
            date=date,
            start_date=start_date,
            end_date=end_date,
        )

    # P3-B.3 — refresh_capital_flow (write path) facade
    def refresh_capital_flow(
        self,
        security_id: SecurityId | None = None,
        *,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: Any | None = None,
    ) -> PersistenceResult:
        """Refresh ``flow.capital_flow_daily`` via the offline writer.

        T3-P3B M3 happy-path: provider fetch → validate →
        ``p3_writer.upsert(...)`` → return :class:`PersistenceResult`.
        No real MongoDB / API / AuditLogger / QualitySummary writes
        fire — strictly ``mongomock`` /
        :class:`P3PersistenceWriter` only.

        Returns:
            A :class:`PersistenceResult` whose ``status`` field is
            one of ``"ok"``, ``"partial_failure"``, ``"skipped"``.

        Raises:
            ProviderUnavailableError: When ``p3_writer`` is not
                injected (offline default).
        """
        return self._get_flow_service().refresh_capital_flow(
            security_id=security_id,
            date=date,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
        )

    # ------------------------------------------------------------------
    # Phase 3 P3-C entry methods (DESIGN-03-014 section 4.5 / SPEC-03-014 section 5.1)
    # ------------------------------------------------------------------

    # P3-C.1 -- get_limit_up_pool (date-level limit-up pool)
    def get_limit_up_pool(
        self,
        trade_date: str | None = None,
    ) -> DataResult:
        """Return the limit-up / limit-down pool for a given trading day.

        Routes through ``sentiment.limit_up_pool`` via the standard
        internal-first chain. ``DataResult.data`` is a ``list[dict]``
        shaped exactly like ``LimitUpPoolRecord.from_dict`` accepts.

        The read path is read-only; explicit refresh is via
        ``sentiment_service.refresh_limit_up_pool(...)`` (offline
        scaffold only for T3-C).
        """
        return self._get_sentiment_service().get_limit_up_pool(
            trade_date=trade_date,
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
        freshness: FreshnessPolicy | None = None,
        external_fallback_chains: dict[str, list[str]] | None = None,
        p3_writer: Any | None = None,
    ) -> "UnifiedDataClient":
        """Build a client pre-populated with ``providers``.

        Providers are registered in the given order, which becomes the
        fallback order when no explicit chain is configured.
        Optionally attach a Phase 1A ``ta_cn_adapter`` to enable the
        domain-specific entry methods, a Phase 1B-A ``freshness``
        policy and / or ``external_fallback_chains`` overrides, or a
        Phase 3 P3 P3PersistenceWriter for the refresh path.
        """
        client = cls(
            config=config,
            ta_cn_adapter=ta_cn_adapter,
            freshness=freshness,
            external_fallback_chains=external_fallback_chains,
            p3_writer=p3_writer,
        )
        for provider in providers:
            client.register_provider(provider)
        return client


__all__ = ["UnifiedDataClient"]
