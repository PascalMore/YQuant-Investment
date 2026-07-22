"""Market-level sentiment domain service (Phase 3 P3-C content, delivered
under the T3-B kanban task label).

The V0.5 design splits Phase 3 into three independently authorised
sub-stages (DESIGN-03-014 §1.1):

* **P3-A** — `sector.snapshot` / `sector.ranking`
  → ``03_data_ud_market_sector_snapshot``
* **P3-B** — `flow.capital_flow_daily` / `flow.northbound_daily`
  → ``03_data_ud_stock_capital_flow``
* **P3-C** — `sentiment.market_snapshot` / `sentiment.limit_up_pool`
  → ``03_data_ud_market_sentiment_snapshot``

The P3-C sentiment slice was implemented ahead of P3-B (capital flow)
under the T3-B kanban task; the title keeps the original P3-B label
for historical reasons. The capability name and collection routed
through :data:`P3_COLLECTION_BY_CAPABILITY` still resolve to
``sentiment.market_snapshot`` and
``03_data_ud_market_sentiment_snapshot`` per V0.5 §0.4 — the
:attr:`capability` property reflects this verbatim.

Sibling of :class:`SectorService` (P3-A / T3-A) — same shape, same
``DataResult`` contract, different capability.

* **Query path** — :meth:`get_market_sentiment_snapshot` goes
  through the router (standard ``TA-CN → P3 → cache → external``
  chain). Step 1 is skipped via ``_TA_CN_NOT_COVERED``. The service
  never touches the writer on read — keeping the V0.5 §2.1
  internal-first invariant intact.
* **Refresh path** — :meth:`refresh_market_sentiment_snapshot` is
  wired but **not invoked** by T3-B (full happy-path lands in T3-C
  proper, alongside ``sentiment.limit_up_pool``). When ``p3_writer``
  is ``None`` (T3-B default) it raises
  :class:`ProviderUnavailableError` so callers cannot silently lose
  data. When ``p3_writer`` is wired, the method asserts membership
  in :data:`P3_COLLECTION_BY_CAPABILITY` and then explicitly raises
  :class:`NotImplementedError` — intentionally, so T3-C owns the
  full write contract without T3-B silently shipping an incomplete
  implementation. Refresh-path verification is therefore deferred
  to T3-C.

Scope (T3-B kanban task body): offline-only, mongomock or no writer,
no real Provider / AuditLogger / QualitySummary writes. ``adapter``
kwarg is reserved for future cross-validation — unused on the read
path.
"""

from __future__ import annotations

import logging
from typing import Any

from ..adapters import TA_CNMongoAdapter
from ..adapters.p3_persistence_writer import (
    P3_COLLECTION_BY_CAPABILITY,
    P3PersistenceWriter,
)
from ..exceptions import ProviderUnavailableError
from ..models import DataResult, Market, SecurityId
# NOTE: T3-B scope forbids editing ``models/domain/__init__.py`` (the
# Domain Object is intentionally *not* re-exported at the package level
# for P3-B). Import the dataclass directly from its submodule.
from ..models.domain.sentiment import (
    LimitUpPoolRecord,
    MarketSentimentSnapshot,
)
from ..router import DataRouter

logger = logging.getLogger(__name__)


class MarketSentimentService:
    """Market-level sentiment snapshot service (Phase 3 P3-B / T3-B).

    Carries the ``sentiment.market_snapshot`` capability only — the
    sister ``sentiment.limit_up_pool`` capability from V0.5 §2.2
    **is implemented** in T3-C on the same service class.
    ``DOMAIN`` + ``OPERATION`` / ``LIMIT_UP_OPERATION`` = the frozen
    :data:`P3_COLLECTION_BY_CAPABILITY` keys.
    """

    DOMAIN = "sentiment"
    OPERATION = "market_snapshot"
    LIMIT_UP_OPERATION = "limit_up_pool"

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        adapter: TA_CNMongoAdapter | None = None,
        *,
        router: DataRouter | None = None,
        p3_writer: P3PersistenceWriter | None = None,
        audit_logger: Any | None = None,
    ) -> None:
        """Build the service.

        Args:
            adapter: Reserved for future cross-validation. Unused on
                the query path; ``None`` is the offline-only default.
            router: :class:`DataRouter` for the read path. When
                omitted the query raises
                :class:`ProviderUnavailableError`.
            p3_writer: :class:`P3PersistenceWriter` for the refresh
                path. ``None`` keeps refresh opt-in (T3-B scope).
            audit_logger: Reserved — T3-B relies on the writer's
                built-in fail-open audit logger (B.b P0.1 patch).
        """
        self._adapter = adapter
        self._router = router
        self._p3_writer = p3_writer
        self._audit_logger = audit_logger

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def capability(self) -> str:
        """Return the canonical capability string ``"sentiment.market_snapshot"``.

        Composition is ``f"{DOMAIN}.{OPERATION}"`` with
        :attr:`DOMAIN = "sentiment"` and :attr:`OPERATION = "market_snapshot"`,
        matching the key registered in :data:`P3_COLLECTION_BY_CAPABILITY`
        (DESIGN-03-014 §0.4 / §2.1). The string **is** the P3_COLLECTION_BY_CAPABILITY
        key — they must stay in lock-step.
        """
        return f"{self.DOMAIN}.{self.OPERATION}"

    @property
    def limit_up_capability(self) -> str:
        """Return the limit-up pool capability string ``"sentiment.limit_up_pool"``."""
        return f"{self.DOMAIN}.{self.LIMIT_UP_OPERATION}"

    @property
    def router(self) -> DataRouter | None:
        """The router used on the read path (``None`` until injected)."""
        return self._router

    @property
    def p3_writer(self) -> P3PersistenceWriter | None:
        """The P3PersistenceWriter used on the refresh path (``None`` until injected)."""
        return self._p3_writer

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def get_market_sentiment_snapshot(
        self,
        market: str,
        sentiment_type: str,
        market_date: str,
    ) -> DataResult:
        """Look up a single ``MarketSentimentSnapshot`` via the router.

        Mirrors :class:`SectorService.get_sector_*` shape but at the
        market level. The router is the single source of truth on
        the read path; this service never touches the writer here.

        Args:
            market:         Market identifier (e.g. ``"CN"``).
            sentiment_type: Aggregate type (e.g. ``"market_sentiment"``).
            market_date:    Calendar date (``"YYYY-MM-DD"``).

        Returns:
            A :class:`DataResult`. ``provider == "empty"`` when the
            chain has no record; ``provider == "error"`` when every
            candidate failed.

        Raises:
            ProviderUnavailableError: When no router was injected
                (offline-only default — caller must inject).
        """
        if self._router is None:
            raise ProviderUnavailableError(
                "MarketSentimentService has no router wired; pass "
                "`router=...` at construction time to enable reads."
            )
        # The router requires a SecurityId even for market-level
        # queries. We synthesise a placeholder using the
        # ``Market.SENTINEL`` pattern documented in DESIGN-03-014
        # §4.5: ``security_id=None`` is the documented market-level
        # signal, but the router currently still wants *some*
        # SecurityId. Use ``Market.INDEX`` + a composite symbol so
        # downstream tooling has a unique canonical string to log
        # against.
        placeholder_symbol = f"{market}:{sentiment_type}:{market_date}"
        placeholder = SecurityId(market=Market.INDEX, symbol=placeholder_symbol)
        # Surface the market level explicitly in metadata so
        # downstream callers can distinguish "no security_id" from
        # "security_id is a placeholder". The router leaves the
        # DataResult untouched on this path; we add the marker post-hoc.
        result = self._router.query(
            domain=self.DOMAIN,
            operation=self.OPERATION,
            security_id=placeholder,
            market=market,
            params={
                "sentiment_type": sentiment_type,
                "market_date": market_date,
            },
        )
        # Surface the market-level nature of the query in the result
        # itself — ``DataResult`` does not carry a ``metadata`` field
        # in Phase 0 (and adding one is out of T3-B scope), so the
        # signal rides on the existing ``source_trace`` list. The
        # marker is added only when the router did not already record
        # an equivalent entry, so duplicate markers do not accumulate
        # on the hot path. The marker is consumed by the test suite
        # via the acceptance check (test #④).
        marker = "market_level_query(security_id=None)"
        if not result.source_trace or marker not in result.source_trace:
            result.source_trace.append(marker)
        return result

    # ------------------------------------------------------------------
    # Write / refresh path
    # ------------------------------------------------------------------

    def refresh_market_sentiment_snapshot(
        self,
        market: str,
        sentiment_type: str,
        market_date: str,
        *,
        provider: Any | None = None,
    ) -> Any:
        """Refresh path — **reserved for T3-C** (per DESIGN-03-014 §2.1 l.207).

        The contract has two clearly separated failure modes and **both
        are intentional**; T3-B does not silently ship an incomplete
        write-path implementation:

        1. When ``p3_writer`` is ``None`` (T3-B default; offline /
           mongomock-only scope) → raises
           :class:`ProviderUnavailableError`. This keeps the refresh
           path opt-in and prevents callers from accidentally dropping
           data into a missing writer.
        2. When ``p3_writer`` is wired → asserts the capability is
           registered in :data:`P3_COLLECTION_BY_CAPABILITY`, then
           raises :class:`NotImplementedError`. The full happy-path
           (provider fetch → validate → ``self._p3_writer.upsert(...)``
           → return result) lands in T3-C together with
           ``sentiment.limit_up_pool``, where the persistence contract
           can be designed against the actual write workload rather
           than sketched speculatively here.

        Refresh-path verification (test coverage of the write path)
        is therefore deferred to T3-C; T3-B only verifies the read
        path and the two pre-conditions above.

        Args:
            market:         Market identifier.
            sentiment_type: Aggregate type.
            market_date:    Calendar date.
            provider:       Optional external provider. ``None`` falls
                back to the router's external chain.

        Raises:
            ProviderUnavailableError: When ``p3_writer`` not injected
                (T3-B default).
            ValueError: When capability is not registered in
                :data:`P3_COLLECTION_BY_CAPABILITY` (defensive guard
                against a future T3-C capability-map edit silently
                routing writes to the wrong collection).
            NotImplementedError: T3-C owns the refresh happy-path;
                this stub deliberately refuses to ship partial work.
        """
        if self._p3_writer is None:
            raise ProviderUnavailableError(
                "MarketSentimentService has no P3PersistenceWriter "
                "wired; refresh path is opt-in until T3-C."
            )
        # Defensive: capability map is the single source of truth for
        # collection routing. We assert here so a future T3-C tweak
        # fails loudly rather than silently routing to the wrong
        # collection.
        if self.capability not in P3_COLLECTION_BY_CAPABILITY:
            raise ValueError(
                f"capability {self.capability!r} is not registered in "
                "P3_COLLECTION_BY_CAPABILITY"
            )
        # Refresh skeleton — T3-C will:
        #   1. fetch via provider (or router fallback chain)
        #   2. validate / shape into MarketSentimentSnapshot(s)
        #   3. call self._p3_writer.upsert(...) with the right
        #      unique_key set
        #   4. return the resulting UpsertOutcome (or a richer
        #      PersistenceResult dataclass)
        # Returning NotImplemented keeps T3-B honest about the
        # scope without forcing T3-C to redesign the contract.
        raise NotImplementedError(
            "MarketSentimentService.refresh_market_sentiment_snapshot "
            "is reserved for T3-C; T3-B does not exercise the write path."
        )

    # ------------------------------------------------------------------
    # P3-C: limit_up_pool read path
    # ------------------------------------------------------------------

    def get_limit_up_pool(
        self,
        trade_date: str | None = None,
    ) -> DataResult:
        """Look up the limit-up / limit-down pool for a given trading day.

        Routes through ``sentiment.limit_up_pool`` (the router does the
        full internal-first / Step-2 read dance — but P3 capabilities
        skip the Step-2 / Step-3 *write* fan-out per the M1 read-only
        guard). The Router's ``DataResult.data`` carries a
        ``list[dict]`` that maps to :class:`LimitUpPoolRecord` via
        :meth:`LimitUpPoolRecord.from_dict`.

        Args:
            trade_date: Trading day (``"YYYY-MM-DD"``). When ``None``
                the query returns records for the most recent available
                date as determined by the provider.

        Returns:
            A :class:`DataResult` whose ``data`` field is a
            ``list[LimitUpPoolRecord]``-compatible ``list[dict]``.
            ``provider == "empty"`` when the chain has no record;
            ``provider == "error"`` when every candidate failed.

        Raises:
            ProviderUnavailableError: When no router was injected
                (offline-only default — caller must inject).
        """
        if self._router is None:
            raise ProviderUnavailableError(
                "MarketSentimentService has no router wired; pass "
                "`router=...` at construction time to enable reads."
            )
        # Use a market-level placeholder SecurityId — the limit-up pool
        # is a date-based query, not a per-security query.
        placeholder = SecurityId(
            market=Market.INDEX,
            symbol=f"limit_up_pool:{trade_date or 'latest'}",
        )
        params: dict[str, object] = {}
        if trade_date is not None:
            params["trade_date"] = trade_date
        result = self._router.query(
            domain=self.DOMAIN,
            operation=self.LIMIT_UP_OPERATION,
            security_id=placeholder,
            market="CN",
            params=params,
        )
        marker = "date_level_query(security_id=None)"
        if not result.source_trace or marker not in result.source_trace:
            result.source_trace.append(marker)
        return result

    # ------------------------------------------------------------------
    # P3-C: limit_up_pool refresh path
    # ------------------------------------------------------------------

    def refresh_limit_up_pool(
        self,
        *,
        p3_writer: Any | None = None,
    ) -> Any:
        """Refresh path for ``sentiment.limit_up_pool``.

        T3-C offline contract:

        1. When ``p3_writer`` is ``None`` (default) →
           raises :class:`ProviderUnavailableError`. This keeps the
           refresh path opt-in and prevents callers from accidentally
           dropping data into a missing writer.
        2. When ``p3_writer`` is wired → asserts the capability is
           registered in :data:`P3_COLLECTION_BY_CAPABILITY`, then
           raises :class:`NotImplementedError`. The full happy-path
           (provider fetch → validate → upsert → return result)
           is reserved for a future Gate-authorised sub-stage.

        Args:
            p3_writer: :class:`P3PersistenceWriter` for the refresh
                path. ``None`` keeps refresh opt-in (T3-C offline
                scope).

        Raises:
            ProviderUnavailableError: When ``p3_writer`` is ``None``.
            ValueError: When capability is not registered in
                :data:`P3_COLLECTION_BY_CAPABILITY`.
            NotImplementedError: Full happy-path is reserved.
        """
        effective_writer = p3_writer if p3_writer is not None else self._p3_writer
        if effective_writer is None:
            raise ProviderUnavailableError(
                "MarketSentimentService has no P3PersistenceWriter "
                "wired; refresh path for limit_up_pool is opt-in."
            )
        if self.limit_up_capability not in P3_COLLECTION_BY_CAPABILITY:
            raise ValueError(
                f"capability {self.limit_up_capability!r} is not registered in "
                "P3_COLLECTION_BY_CAPABILITY"
            )
        raise NotImplementedError(
            "MarketSentimentService.refresh_limit_up_pool "
            "is offline-scaffold only; full happy-path reserved."
        )


__all__ = ["MarketSentimentService"]