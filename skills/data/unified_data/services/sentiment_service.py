"""Market-level sentiment domain service (Phase 3 P3-C canonical).

The V0.5 design splits Phase 3 into three independently authorised
sub-stages (DESIGN-03-014 §1.1):

* **P3-A** — ``sector.snapshot`` / ``sector.ranking``
  → ``03_data_ud_market_sector_snapshot``
* **P3-B** — ``flow.capital_flow_daily`` / ``flow.northbound_daily``
  → ``03_data_ud_stock_capital_flow``
* **P3-C** — ``sentiment.market_snapshot`` / ``sentiment.limit_up_pool``
  → ``03_data_ud_market_sentiment_snapshot``

The P3-C sentiment slice was originally implemented ahead of P3-B
(capital flow) under the T3-B kanban task label; the title kept the
original P3-B label for historical reasons. As of V0.23 / RFC V0.16 /
SPEC V0.15, the canonical contract for :class:`MarketSentimentSnapshot`
is the **22-field full-market multi-dimensional snapshot** with unique
key ``{market, snapshot_date, snapshot_time}`` — Pascal ratified this
on 2026-07-30.

Sibling of :class:`SectorService` (P3-A / T3-A) — same shape, same
``DataResult`` contract, different capability.

* **Query path** — :meth:`get_market_sentiment_snapshot` goes through
  the router (standard ``TA-CN → P3 → cache → external`` chain).
  Step 1 is skipped via ``_TA_CN_NOT_COVERED``. The service never
  touches the writer on read — keeping the V0.5 §2.1 internal-first
  invariant intact. The signature uses ``snapshot_date`` /
  ``snapshot_time`` (no ``sentiment_type`` — that field is no longer
  part of the canonical contract).
* **Refresh path** — :meth:`refresh_market_sentiment_snapshot` is
  wired but **not invoked** (full happy-path lands in a Gate-authorised
  sub-stage, alongside ``sentiment.limit_up_pool``). When
  ``p3_writer`` is ``None`` (default) it raises
  :class:`ProviderUnavailableError` so callers cannot silently lose
  data. When ``p3_writer`` is wired, the method asserts membership in
  :data:`P3_COLLECTION_BY_CAPABILITY` and then explicitly raises
  :class:`NotImplementedError` — intentionally, so the future
  Gate-authorised sub-stage owns the full write contract without
  silently shipping an incomplete implementation. Refresh-path
  verification is therefore deferred.

Scope: offline-only, mongomock or no writer, no real Provider /
AuditLogger / QualitySummary writes. ``adapter`` kwarg is reserved for
future cross-validation — unused on the read path.
"""

from __future__ import annotations

import logging
from typing import Any

from ..adapters import TA_CNMongoAdapter
from ..adapters.p3_persistence_writer import (
    P3_COLLECTION_BY_CAPABILITY,
    P3_UNIQUE_KEYS_BY_CAPABILITY,
    P3PersistenceWriter,
)
from ..exceptions import ProviderUnavailableError
from ..models import DataResult, Market, SecurityId
from ..models.domain.sentiment import (
    LimitUpPoolRecord,
    MarketSentimentSnapshot,
)
from ..router import DataRouter

logger = logging.getLogger(__name__)


class MarketSentimentService:
    """Market-level sentiment snapshot service (Phase 3 P3-C canonical).

    Carries the ``sentiment.market_snapshot`` capability only — the
    sister ``sentiment.limit_up_pool`` capability from V0.5 §2.2
    **is implemented** on the same service class.
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
        cache_manager: Any | None = None,
    ) -> None:
        """Build the service.

        Args:
            adapter: Reserved for future cross-validation. Unused on
                the query path; ``None`` is the offline-only default.
            router: :class:`DataRouter` for the read path. When
                omitted the query raises
                :class:`ProviderUnavailableError`.
            p3_writer: :class:`P3PersistenceWriter` for the refresh
                path. ``None`` keeps refresh opt-in.
            audit_logger: Reserved — relies on the writer's built-in
                fail-open audit logger.
            cache_manager: P1 Step-4 cache write target
                (DESIGN §P1.5.2.bis); ``None`` skips the cache write.
        """
        self._adapter = adapter
        self._router = router
        self._p3_writer = p3_writer
        self._audit_logger = audit_logger
        self._cache_manager = cache_manager
        # P1 refresh-path three-state guard: the per-instance
        # ``_refresh_authorized`` flag defaults to ``False``
        # (default-deny). Tests / Pascal Gate flip it to ``True`` to
        # exercise the happy-path (mirrors the
        # :class:`SectorService` and :class:`FlowService` contract).
        self._refresh_authorized: bool = False

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
    # Read path — canonical 22-field schema
    # ------------------------------------------------------------------

    def get_market_sentiment_snapshot(
        self,
        snapshot_date: str,
        snapshot_time: str = "close",
    ) -> DataResult:
        """Look up a single ``MarketSentimentSnapshot`` via the router.

        Mirrors :class:`SectorService.get_sector_*` shape but at the
        market level. The router is the single source of truth on
        the read path; this service never touches the writer here.

        The signature uses the **22-field canonical contract** keys:
        ``snapshot_date`` + ``snapshot_time`` (no ``sentiment_type`` —
        that field was part of the superseded T3-B 10-field offline
        schema).

        Args:
            snapshot_date: Calendar date the snapshot covers
                (``"YYYY-MM-DD"``). Part of the unique key
                ``{market, snapshot_date, snapshot_time}``.
            snapshot_time: Observation time (``"HH:MM:SS"`` or
                ``"close"``). Defaults to ``"close"``. Part of the
                unique key.

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
        # queries. Synthesise a placeholder using the
        # ``Market.INDEX`` pattern documented in DESIGN-03-014 §4.5:
        # ``security_id=None`` is the documented market-level signal,
        # but the router currently still wants *some* SecurityId.
        # Use ``Market.INDEX`` + a composite symbol so downstream
        # tooling has a unique canonical string to log against.
        placeholder_symbol = f"CN:{snapshot_date}:{snapshot_time}"
        placeholder = SecurityId(market=Market.INDEX, symbol=placeholder_symbol)
        # Surface the market level explicitly in source_trace so
        # downstream callers can distinguish "no security_id" from
        # "security_id is a placeholder". The router leaves the
        # DataResult untouched on this path; we add the marker post-hoc.
        result = self._router.query(
            domain=self.DOMAIN,
            operation=self.OPERATION,
            security_id=placeholder,
            market="CN",
            params={
                "snapshot_date": snapshot_date,
                "snapshot_time": snapshot_time,
            },
        )
        marker = "market_level_query(security_id=None)"
        if not result.source_trace or marker not in result.source_trace:
            result.source_trace.append(marker)
        return result

    # ------------------------------------------------------------------
    # Write / refresh path
    # ------------------------------------------------------------------

    def refresh_market_sentiment_snapshot(
        self,
        snapshot_date: str,
        snapshot_time: str = "close",
        *,
        provider: Any | None = None,
    ) -> Any:
        """Refresh path — three-state guard (P0) + happy-path (P1).

        P0 pinned the two terminal states
        (``p3_writer is None`` → :class:`ProviderUnavailableError`,
        writer wired → :class:`NotImplementedError`). P1 widens
        with an **authorised** state that walks the 22-field
        canonical happy-path:

        1. ``p3_writer is None`` → :class:`ProviderUnavailableError`.
        2. writer wired but ``_is_refresh_authorized`` is ``False``
           → :class:`NotImplementedError` (default-deny; P0 contract
           preserved).
        3. authorised → fetch via Provider → upsert via writer
           using the ``{market, snapshot_date, snapshot_time}``
           business unique key (V0.23 §3.3).

        The 22-field canonical contract is the **only** persistence
        schema. Legacy 10-field ``sentiment_type`` / ``market_date``
        schemas are forbidden by P1.2 — the writer.upsert call
        refuses records missing the canonical key fields.

        Args:
            snapshot_date: Calendar date (``"YYYY-MM-DD"``).
            snapshot_time: Observation time (``"HH:MM:SS"`` or
                ``"close"``). Defaults to ``"close"``.
            provider: Optional external provider. ``None`` falls back
                to the router's external chain.

        Raises:
            ProviderUnavailableError: When ``p3_writer`` not injected
                (default).
            ValueError: When capability is not registered in
                :data:`P3_COLLECTION_BY_CAPABILITY` (defensive guard
                against a future capability-map edit silently routing
                writes to the wrong collection).
            NotImplementedError: The Gate-authorised sub-stage owns
                the refresh happy-path; this stub deliberately refuses
                to ship partial work. P1 widens the guard to a
                per-instance ``_refresh_authorized`` flag.
        """
        if self._p3_writer is not None and self._is_refresh_authorized(
            capability=self.capability
        ):
            return self._run_refresh(
                snapshot_date=snapshot_date,
                snapshot_time=snapshot_time,
                provider=provider,
                capability=self.capability,
            )
        if self._p3_writer is None:
            raise ProviderUnavailableError(
                "MarketSentimentService has no P3PersistenceWriter "
                "wired; refresh path is opt-in until Gate authorisation."
            )
        # Defensive: capability map is the single source of truth for
        # collection routing. We assert here so a future tweak fails
        # loudly rather than silently routing to the wrong collection.
        if self.capability not in P3_COLLECTION_BY_CAPABILITY:
            raise ValueError(
                f"capability {self.capability!r} is not registered in "
                "P3_COLLECTION_BY_CAPABILITY"
            )
        # P1 widening: instead of unconditionally refusing, raise
        # ``NotImplementedError`` only when the per-instance flag is
        # still ``False``. The flag defaults to ``False`` so the P0
        # contract is preserved for every existing test.
        if not self._refresh_authorized:
            raise NotImplementedError(
                "MarketSentimentService.refresh_market_sentiment_snapshot "
                "is gated behind the per-instance ``_refresh_authorized`` "
                "flag (P1 default-deny); call ``enable_refresh()`` or "
                "wait for the Gate-authorised sub-stage to flip the toggle."
            )
        # Unreachable: the early return above covers the authorised
        # branch. ``NotImplementedError`` is the only path that
        # reaches here. Keep a defensive fallback raise so a future
        # guard edit cannot silently drop the gate.
        raise NotImplementedError(
            "MarketSentimentService.refresh_market_sentiment_snapshot "
            "is reserved for Gate-authorised sub-stage; happy-path "
            "ownership is deferred."
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
        provider: Any | None = None,
    ) -> Any:
        """Refresh path for ``sentiment.limit_up_pool`` — three-state guard (P1).

        Three branches:

        1. ``p3_writer is None`` → :class:`ProviderUnavailableError`.
        2. writer wired but ``_is_refresh_authorized`` is ``False``
           → :class:`NotImplementedError` (default-deny; P0 contract
           preserved).
        3. authorised → fetch via Provider → upsert via writer
           using the ``{market, symbol, trade_date}`` business
           unique key (V0.5 §2.2).

        Args:
            p3_writer: :class:`P3PersistenceWriter` for the refresh
                path. ``None`` keeps refresh opt-in (offline scope).
                When supplied, it overrides the writer wired at
                construction time (forward-compat hook).
            provider: Optional :class:`DataProvider`. ``None`` falls
                back to the router's external chain.

        Raises:
            ProviderUnavailableError: When ``p3_writer`` is ``None``.
            ValueError: When capability is not registered in
                :data:`P3_COLLECTION_BY_CAPABILITY`.
            NotImplementedError: When ``_is_refresh_authorized`` is
                ``False``.
        """
        effective_writer = p3_writer if p3_writer is not None else self._p3_writer
        if (
            effective_writer is not None
            and self._is_refresh_authorized(capability=self.limit_up_capability)
        ):
            return self._run_limit_up_pool_refresh(
                p3_writer=effective_writer,
                provider=provider,
            )
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
        if not self._refresh_authorized:
            raise NotImplementedError(
                "MarketSentimentService.refresh_limit_up_pool is "
                "gated behind the per-instance ``_refresh_authorized`` "
                "flag (P1 default-deny); call ``enable_refresh()`` or "
                "wait for the Gate-authorised sub-stage to flip the toggle."
            )
        # Defensive fallback — the early return above covers the
        # authorised branch.
        raise NotImplementedError(
            "MarketSentimentService.refresh_limit_up_pool "
            "is offline-scaffold only; full happy-path reserved."
        )

    # ------------------------------------------------------------------
    # P1 refresh-path three-state guard helpers
    # ------------------------------------------------------------------

    def _is_refresh_authorized(self, *, capability: str) -> bool:
        """Return ``True`` only when the per-instance toggle is on.

        Mirrors the :class:`SectorService` /
        :class:`FlowService` contract. The default value is ``False``
        — every :class:`MarketSentimentService` instance ships
        default-deny. Both ``sentiment.market_snapshot`` and
        ``sentiment.limit_up_pool`` capabilities share the same
        per-instance flag — the Gate-authorised sub-stage flips the
        flag once and both methods are activated together.
        """
        return bool(self._refresh_authorized)

    def enable_refresh(self) -> None:
        """Flip the per-instance refresh authorisation to ``True``.

        Convenience hook for the P1.5 / P2 production activation
        sub-stage (and for the unit-test fixture setup). The flag is
        intentionally per-instance so test isolation does not
        require a class-level reset. Production activation is gated
        by the Pascal Gate per P1.10 (G-C-2).
        """
        self._refresh_authorized = True

    def _fetch_for_refresh(
        self,
        *,
        capability: str,
        provider: Any | None,
        params: dict[str, Any],
    ) -> list[dict]:
        """Resolve a Provider for the refresh path and fetch its payload.

        Mirrors :meth:`FlowService._fetch_for_refresh` — caller-supplied
        ``provider`` wins; otherwise the router's registry supplies
        the first available candidate. Non-list outputs coerce to
        ``[]`` so the downstream ``skip_empty`` branch fires
        cleanly.
        """
        domain, _, operation = capability.partition(".")
        if provider is not None:
            payload = provider.fetch(domain, operation, **params)
        elif self._router is not None:
            return self._fetch_via_registry(capability, params)
        else:
            raise ProviderUnavailableError(
                f"MarketSentimentService.{capability!r} refresh has no "
                "provider supplied and no router wired; cannot fetch "
                "payload."
            )
        if not isinstance(payload, list):
            return []
        return [dict(row) for row in payload if isinstance(row, dict)]

    def _fetch_via_registry(
        self, capability: str, params: dict[str, Any]
    ) -> list[dict]:
        """Resolve a Provider from the router registry and invoke ``fetch``."""
        registry = getattr(self._router, "registry", None)
        if registry is None:
            return []
        for candidate in registry.list_providers():
            if capability in candidate.capabilities and candidate.is_available():
                domain, _, operation = capability.partition(".")
                return candidate.fetch(domain, operation, **params)
        return []

    def _run_refresh(
        self,
        *,
        snapshot_date: str,
        snapshot_time: str,
        provider: Any | None,
        capability: str,
    ) -> Any:
        """22-field canonical happy-path runner for ``sentiment.market_snapshot``.

        Steps:

        1. Capability map defensive guard (fails loudly on edits).
        2. Fetch via Provider; coerce to ``list[dict]``.
        3. Empty payload → ``PersistenceOutcome(status='skipped',
           reason='empty_response')``.
        4. Otherwise call ``writer.upsert`` with the canonical
           ``{market, snapshot_date, snapshot_time}`` unique key
           (P1.2 schema). The writer's idempotent business-key
           upsert overwrites in place.
        5. Map the writer's :class:`UpsertOutcome` into a
           :class:`PersistenceOutcome` for the caller.
        """
        from .flow_service import PersistenceResult  # local import — same package

        if capability not in P3_COLLECTION_BY_CAPABILITY:
            raise ValueError(
                f"capability {capability!r} is not registered in "
                "P3_COLLECTION_BY_CAPABILITY"
            )
        if capability not in P3_UNIQUE_KEYS_BY_CAPABILITY:
            raise ValueError(
                f"capability {capability!r} is missing a unique-key "
                "definition in P3_UNIQUE_KEYS_BY_CAPABILITY"
            )

        collection = P3_COLLECTION_BY_CAPABILITY[capability]
        unique_key = P3_UNIQUE_KEYS_BY_CAPABILITY[capability]

        records = self._fetch_for_refresh(
            capability=capability,
            provider=provider,
            params={
                "snapshot_date": snapshot_date,
                "snapshot_time": snapshot_time,
            },
        )
        if not records:
            return PersistenceResult(
                status="skipped",
                capability=capability,
                collection=collection,
                persisted=0,
                failed=0,
                skipped=True,
                reason="empty_response",
                writer_outcome=None,
            )
        outcome = self._p3_writer.upsert(
            collection=collection,
            records=records,
            unique_key=unique_key,
        )
        # Step 4: CacheManager.put (catch-and-log, mock-only in P1).
        self._put_cache(capability, records, snapshot_date, snapshot_time)
        return PersistenceResult(
            status="ok" if outcome.failed == 0 else "partial_failure",
            capability=capability,
            collection=collection,
            persisted=outcome.persisted,
            failed=outcome.failed,
            skipped=False,
            reason=None,
            writer_outcome=outcome,
        )

    def _run_limit_up_pool_refresh(
        self,
        *,
        p3_writer: Any,
        provider: Any | None,
    ) -> Any:
        """Happy-path runner for ``sentiment.limit_up_pool``.

        Mirrors :meth:`_run_refresh` but the unique key is the
        per-stock ``{market, symbol, trade_date}`` set (P1.2) and
        the writer is supplied by the caller (the
        :meth:`refresh_limit_up_pool` kwarg overrides the
        constructor-wired one).
        """
        from .flow_service import PersistenceResult  # local import — same package

        capability = self.limit_up_capability
        if capability not in P3_COLLECTION_BY_CAPABILITY:
            raise ValueError(
                f"capability {capability!r} is not registered in "
                "P3_COLLECTION_BY_CAPABILITY"
            )
        if capability not in P3_UNIQUE_KEYS_BY_CAPABILITY:
            raise ValueError(
                f"capability {capability!r} is missing a unique-key "
                "definition in P3_UNIQUE_KEYS_BY_CAPABILITY"
            )

        collection = P3_COLLECTION_BY_CAPABILITY[capability]
        unique_key = P3_UNIQUE_KEYS_BY_CAPABILITY[capability]

        records = self._fetch_for_refresh(
            capability=capability,
            provider=provider,
            params={},
        )
        if not records:
            return PersistenceResult(
                status="skipped",
                capability=capability,
                collection=collection,
                persisted=0,
                failed=0,
                skipped=True,
                reason="empty_response",
                writer_outcome=None,
            )
        outcome = p3_writer.upsert(
            collection=collection,
            records=records,
            unique_key=unique_key,
        )
        # Step 4: CacheManager.put (catch-and-log, mock-only in P1).
        self._put_cache(capability, records, None, None)
        return PersistenceResult(
            status="ok" if outcome.failed == 0 else "partial_failure",
            capability=capability,
            collection=collection,
            persisted=outcome.persisted,
            failed=outcome.failed,
            skipped=False,
            reason=None,
            writer_outcome=outcome,
        )

    # ------------------------------------------------------------------
    # P1 Step 4: Cache write (catch-and-log)
    # ------------------------------------------------------------------

    def _put_cache(
        self,
        capability: str,
        records: list[dict],
        snapshot_date: str | None,
        snapshot_time: str | None,
    ) -> None:
        """P1 Step 4: write refresh results into CacheManager (catch-and-log).

        Per SPEC §P1.5.2.bis: failure does NOT block the refresh main path.
        The cache write is mock-only in P1 — ``cache_manager`` defaults to
        ``None`` and is injected only in authorised tests.

        Cache key formats:
        - ``sentiment.market_snapshot`` → ``sentiment:market_snapshot:{snapshot_date}``
        - ``sentiment.limit_up_pool`` → ``sentiment:limit_up_pool:{snapshot_date}``
        """
        if self._cache_manager is None:
            return
        sd = snapshot_date or ""
        if capability == "sentiment.market_snapshot":
            cache_key = f"sentiment:market_snapshot:{sd}"
        elif capability == "sentiment.limit_up_pool":
            cache_key = f"sentiment:limit_up_pool:{sd}"
        else:
            logger.warning(
                "MarketSentimentService._put_cache: unknown capability %r — skipping",
                capability,
            )
            return
        try:
            self._cache_manager.put(cache_key, records)
        except Exception:
            logger.warning(
                "MarketSentimentService._put_cache: CacheManager.put failed "
                "(non-blocking, capability=%r)",
                capability,
                exc_info=True,
            )


__all__ = ["MarketSentimentService"]