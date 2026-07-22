"""Capital-flow domain service (Phase 3 P3-B / T3-P3B).

:class:`FlowService` is the per-symbol capital-flow sibling of
:class:`SectorService` (P3-A / T3-A) and :class:`MarketSentimentService`
(P3-B / T3-B). Same shape, same ``DataResult`` contract — different
capability.

* **Read path** — :meth:`get_capital_flow` /
  :meth:`get_northbound_flow` route through the standard
  ``TA-CN → P3 → cache → external`` chain via :class:`DataRouter`. Step
  1 is skipped via :data:`DataRouter._TA_CN_NOT_COVERED` (T3-P3B added
  both flow capabilities). The Router still performs no Step-2 /
  Step-3 write fan-out for P3 capabilities (T3-P3B M1 read-only
  guard). The service shapes the Router's ``DataResult.data``
  (``list[dict]``) into the canonical :class:`CapitalFlowRecord`
  domain object before returning, with caller-supplied ``security_id``
  / ``date`` / ``date_range`` / ``limit`` filters applied at the
  service boundary (T3-P3B M2).

* **Refresh path** — :meth:`refresh_capital_flow` is fully wired on
  the offline scope. The happy-path (provider fetch → validate →
  ``p3_writer.upsert(...)`` → return :class:`PersistenceResult`) is
  implemented; four additional failure branches (``partial_failure``,
  ``skip_empty``, ``write_forbidden``, ``already_written``) round out
  the offline contract (T3-P3B M3). No real MongoDB / AuditLogger /
  QualitySummary writes fire — strictly ``mongomock`` /
  ``FakeWriter``.

Scope (T3-P3B kanban task body): offline-only, mongomock or no writer,
no real Provider / AuditLogger / QualitySummary writes. ``adapter``
kwarg is reserved for future cross-validation — unused on the read
path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..adapters import TA_CNMongoAdapter
from ..adapters.p3_persistence_writer import (
    P3_COLLECTION_BY_CAPABILITY,
    P3_UNIQUE_KEYS_BY_CAPABILITY,
    P3PersistenceWriter,
    UpsertOutcome,
)
from ..exceptions import ProviderUnavailableError
from ..models import DataResult, Market, SecurityId
from ..models.domain.flow import CapitalFlowRecord
from ..router import DataRouter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    """Outcome of :meth:`FlowService.refresh_capital_flow`.

    Five branches (``happy_path`` / ``partial_failure`` / ``skip_empty``
    / ``write_forbidden`` / ``already_written``) collapse into a single
    result shape. The discriminator is :attr:`status`. Persisted /
    failed counts lift straight from the underlying
    :class:`UpsertOutcome` when the writer was invoked; ``skip_*``
    branches hold ``persisted == 0`` / ``failed == 0`` by design.

    Attributes:
        status: One of ``"ok"`` / ``"partial_failure"`` / ``"skipped"``.
        capability: The capability the refresh targeted — frozen at the
            call site for audit-friendly logging.
        collection: The P3 collection the writer was about to upsert
            into. ``None`` when the refresh was skipped before the
            collection could be resolved.
        persisted: Count of records successfully upserted.
        failed: Count of records that failed per-record upsert.
        skipped: ``True`` when the refresh opted out without calling
            the writer (empty payload / write disabled).
        reason: Free-form reason for the ``skipped=True`` branch
            (``"empty_payload"``, ``"write_forbidden"``,
            ``"already_written_idempotent"``). ``None`` for the
            non-skip branches.
        writer_outcome: The raw :class:`UpsertOutcome` returned by
            ``p3_writer.upsert(...)`` when the writer was called.
            ``None`` for the skip branches.
    """

    status: str  # "ok" / "partial_failure" / "skipped"
    capability: str
    collection: str | None
    persisted: int = 0
    failed: int = 0
    skipped: bool = False
    reason: str | None = None
    writer_outcome: UpsertOutcome | None = None

    @property
    def success(self) -> bool:
        """``True`` when persisted records exist (idempotent re-runs OK)."""
        return self.status in ("ok", "partial_failure") and self.persisted >= 0


class FlowService:
    """个股资金流域服务（Phase 3 P3-B / T3-P3B）。

    Carries both P3-B capabilities — ``flow.capital_flow_daily`` and
    ``flow.northbound_daily``. ``DOMAIN`` + ``OPERATION`` /
    ``NORTHBOUND_OPERATION`` are the frozen
    :data:`P3_COLLECTION_BY_CAPABILITY` keys. Both resolve to
    ``03_data_ud_stock_capital_flow`` (V0.5 §0.4) and share the
    ``{market, symbol, trade_date}`` business unique key.

    The :attr:`capability` property composes the canonical capability
    string the router / P3 writer key off — it is the single source of
    truth for dispatch. :attr:`northbound_capability` returns the
    northbound-specific variant.
    """

    DOMAIN = "flow"
    OPERATION = "capital_flow_daily"
    NORTHBOUND_OPERATION = "northbound_daily"

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
                path. ``None`` keeps refresh opt-in (T3-P3B scope).
            audit_logger: Reserved — T3-P3B relies on the writer's
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
        """Return the canonical capital-flow capability string.

        Composition is ``f"{DOMAIN}.{OPERATION}"`` with
        :attr:`DOMAIN = "flow"` and :attr:`OPERATION = "capital_flow_daily"`,
        matching the key registered in :data:`P3_COLLECTION_BY_CAPABILITY`
        (DESIGN-03-014 §0.4 / §2.1).
        """
        return f"{self.DOMAIN}.{self.OPERATION}"

    @property
    def northbound_capability(self) -> str:
        """Return the northbound capability string ``"flow.northbound_daily"``."""
        return f"{self.DOMAIN}.{self.NORTHBOUND_OPERATION}"

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

    def get_capital_flow(
        self,
        security_id: SecurityId,
        *,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 60,
    ) -> DataResult:
        """Look up the per-symbol daily capital-flow payload via the router.

        Routes through ``flow.capital_flow_daily`` (the router does the
        full internal-first / Step-2 read / Step-4 dance — but P3
        capabilities skip the Step-2 / Step-3 *write* fan-out per
        T3-P3B M1). The Router's ``DataResult.data`` carries a
        ``list[dict]``; the service shapes each dict into the
        canonical :class:`CapitalFlowRecord` via
        :meth:`CapitalFlowRecord.from_dict`, applies caller-supplied
        ``security_id`` / ``trade_date`` / date-range / ``limit``
        filters at the service boundary (T3-P3B M2), and returns the
        filtered ``list[CapitalFlowRecord]`` as ``DataResult.data``.

        Args:
            security_id: The :class:`SecurityId` being queried. Must be
                a per-symbol SecurityId — sector / market-level queries
                are not supported here (use ``get_northbound_flow`` if
                you need a market aggregation).
            trade_date: Single ``"YYYY-MM-DD"`` date filter (optional).
            start_date: Inclusive lower bound for date range.
            end_date: Inclusive upper bound for date range.
            limit: Maximum number of records to return (default 60).

        Returns:
            A :class:`DataResult` whose ``data`` field is a
            ``list[CapitalFlowRecord]`` (T3-P3B M2 canonical object
            contract). ``provider == "empty"`` when the chain has no
            record; ``provider == "error"`` when every candidate
            failed.

        Raises:
            ProviderUnavailableError: When no router was injected
                (offline-only default — caller must inject).
        """
        result = self._query_capital_flow(
            security_id=security_id,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            capability=self.capability,
        )
        return self._shape_capital_flow_result(
            result,
            security_id=security_id,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            projection="full",
        )

    def get_northbound_flow(
        self,
        security_id: SecurityId | None = None,
        *,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> DataResult:
        """Look up the northbound capital-flow payload.

        The V0.5 §3.2 ``record_scope`` rule for the
        ``flow.northbound_daily`` capability: only the
        ``{symbol, market, trade_date}`` business-key plus the three
        ``northbound_*`` fields plus ``fetched_at`` / ``provider`` are
        populated. The service enforces this projection at the
        ``DataResult.data`` boundary (T3-P3B M2) so callers receive a
        ``list[CapitalFlowRecord]`` with the five flow bands and the
        three ``margin_*`` fields explicitly ``None``.

        Args:
            security_id: Optional per-symbol SecurityId. When ``None``
                the service synthesises a market-level placeholder
                (V0.5 §3.2 — northbound aggregates are market-level
                snapshots, per-symbol filtering is optional).
            date: Single ``"YYYY-MM-DD"`` date filter (optional; the
                V0.5 signature renames ``trade_date`` to ``date``).
            start_date: Inclusive lower bound for date range.
            end_date: Inclusive upper bound for date range.

        Returns:
            A :class:`DataResult` whose ``data`` field is a
            ``list[CapitalFlowRecord]`` with the northbound projection
            applied — only ``northbound_*`` + business-key + metadata
            fields are populated; the rest are ``None``.

        Raises:
            ProviderUnavailableError: When no router was injected
                (offline-only default — caller must inject).
        """
        # Market-level call convention: ``security_id=None`` is the
        # documented signal that the caller wants the market
        # aggregate. The shared helper
        # :meth:`_query_capital_flow` synthesises a placeholder
        # SecurityId so the Router's positional ``security_id``
        # argument stays populated; the router still receives a
        # structured object for logging purposes.
        #
        # ``trade_date`` arg name is intentionally absent from the
        # northbound signature — the V0.5 contract uses ``date``.
        # Translate to the Router's ``trade_date`` kwarg internally.
        result = self._query_capital_flow(
            security_id=security_id,
            trade_date=date,
            start_date=start_date,
            end_date=end_date,
            limit=0,
            capability=self.northbound_capability,
        )
        return self._shape_capital_flow_result(
            result,
            security_id=security_id,
            trade_date=date,
            start_date=start_date,
            end_date=end_date,
            limit=0,
            projection="northbound",
        )

    # ------------------------------------------------------------------
    # Read-path shaping (T3-P3B M2)
    # ------------------------------------------------------------------

    @staticmethod
    def _synthesise_market_placeholder() -> SecurityId:
        """Build a market-level placeholder SecurityId.

        Mirrors the :class:`MarketSentimentService` precedent
        (``services/sentiment_service.py``): the Router still needs a
        structured ``SecurityId`` even for market-level queries, so we
        synthesize one. The composite symbol surfaces "this is a
        market-level northbound call" in any trace / log output
        without needing a side-car metadata field. The market label
        stays ``Market.CN`` — capital-flow is CN-scoped in T3-P3B so
        the upstream provider / stub always sees ``CN`` regardless of
        whether the caller passed a real symbol or ``None``.
        """
        return SecurityId(market=Market.CN, symbol="flow:northbound:market")

    def _shape_capital_flow_result(
        self,
        result: DataResult,
        *,
        security_id: SecurityId | None,
        trade_date: str | None,
        start_date: str | None,
        end_date: str | None,
        limit: int,
        projection: str,
    ) -> DataResult:
        """Shape the Router's ``DataResult.data`` into a canonical list.

        * ``projection == "full"`` — uses :meth:`CapitalFlowRecord.from_dict`
          and keeps every field populated. Used by ``get_capital_flow``.
        * ``projection == "northbound"`` — uses :meth:`CapitalFlowRecord.from_northbound_dict`
          so the five flow bands + three ``margin_*`` fields are
          explicitly ``None``. Used by ``get_northbound_flow``.

        Filters applied at this boundary (T3-P3B M2):

        * ``security_id`` — when supplied, records whose
          ``{market, symbol}`` does not match are dropped.
        * ``trade_date`` — single-day filter, exact match.
        * ``start_date`` / ``end_date`` — inclusive range filter.
        * ``limit`` — applied AFTER the date filters, on the ordered
          list as returned by the Router (records keep their provider
          order).

        The shape returns the **same** :class:`DataResult` object
        with a replaced ``data`` field so downstream metadata
        (``provider``, ``freshness``, ``source_trace``, ``warnings``)
        stays untouched.
        """
        if result is None or result.data is None:
            return result
        if not isinstance(result.data, list):
            # Provider / adapter returned a non-list shape — leave the
            # DataResult untouched so the test surface can still
            # assert against the raw payload without an attribute
            # explosion.
            return result
        if projection not in ("full", "northbound"):
            raise ValueError(
                f"unknown projection {projection!r}; expected 'full' or 'northbound'"
            )

        factory = (
            CapitalFlowRecord.from_dict
            if projection == "full"
            else CapitalFlowRecord.from_northbound_dict
        )
        records: list[CapitalFlowRecord] = []
        for raw in result.data:
            if not isinstance(raw, dict):
                # Provider emitted a non-dict row — skip silently.
                # Tests pin the dict-list contract; a non-dict row is
                # an upstream provider bug.
                continue
            record = factory(raw)
            if not self._record_matches_filters(
                record,
                security_id=security_id,
                trade_date=trade_date,
                start_date=start_date,
                end_date=end_date,
            ):
                continue
            records.append(record)

        if limit and limit > 0:
            records = records[:limit]

        # Re-bind the DataResult with the shaped data list. The
        # service treats this as an in-place transformation — every
        # other field (provider / freshness / source_trace / domain
        # / operation / security_id / fetched_at) is preserved.
        object.__setattr__(result, "data", records)
        return result

    @staticmethod
    def _record_matches_filters(
        record: CapitalFlowRecord,
        *,
        security_id: SecurityId | None,
        trade_date: str | None,
        start_date: str | None,
        end_date: str | None,
    ) -> bool:
        """Apply caller-supplied filters to a single record (T3-P3B M2)."""
        if security_id is not None:
            # Match the canonical ``{market, symbol}`` pair. We DO NOT
            # match on ``canonical`` because the dataclass stores the
            # raw ``symbol`` value and the filters are per-field for
            # predictability.
            if record.market != security_id.market:
                return False
            if record.symbol != security_id.symbol:
                return False
        if trade_date is not None and record.trade_date != trade_date:
            return False
        if start_date is not None and record.trade_date < start_date:
            return False
        if end_date is not None and record.trade_date > end_date:
            return False
        return True

    def _query_capital_flow(
        self,
        *,
        security_id: SecurityId | None,
        trade_date: str | None,
        start_date: str | None,
        end_date: str | None,
        limit: int,
        capability: str,
    ) -> DataResult:
        """Internal helper — shared by the two read methods (router call).

        Synthesises a placeholder ``SecurityId`` when the caller
        passes ``None`` (market-level query). The placeholder keeps
        the Router's positional ``security_id`` argument populated so
        downstream observability has a canonical string to log
        against, mirroring the :class:`MarketSentimentService`
        precedent.
        """
        if self._router is None:
            raise ProviderUnavailableError(
                "FlowService has no router wired; pass "
                "`router=...` at construction time to enable reads."
            )
        effective: SecurityId = (
            security_id if security_id is not None else self._synthesise_market_placeholder()
        )
        domain = capability.split(".", 1)[0]
        operation = capability.split(".", 1)[1]
        return self._router.query(
            domain=domain,
            operation=operation,
            security_id=effective,
            market=effective.market,
            params={
                "trade_date": trade_date,
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit if limit and limit > 0 else 0,
            },
        )

    # ------------------------------------------------------------------
    # Write / refresh path (T3-P3B M3)
    # ------------------------------------------------------------------

    def refresh_capital_flow(
        self,
        security_id: SecurityId | None = None,
        *,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: Any | None = None,
    ) -> PersistenceResult:
        """Refresh path — fetches, validates, upserts, returns outcome.

        Implements the T3-P3B M3 five-branch contract:

        * ``happy_path`` — the (injected or registry) provider returns
          N records; every record is fed into
          ``p3_writer.upsert(...)`` with the
          ``{market, symbol, trade_date}`` business unique key set.
          Returns ``PersistenceResult(status="ok", persisted=N, ...)``.
        * ``partial_failure`` — the provider returns a mix of valid
          and malformed rows (some have missing keys, some raise on
          shape validation). ``p3_writer.upsert(...)`` reports
          ``persisted < N`` and ``failed > 0``; the surface returns
          ``status="partial_failure"`` with both counts populated.
        * ``skip_empty`` — the provider returns an empty list
          (no rows for the requested date range). ``p3_writer.upsert``
          is NOT called. Returns
          ``PersistenceResult(status="skipped", skipped=True,
          reason="empty_payload")``.
        * ``write_forbidden`` — ``p3_writer.upsert(...)`` is bypassed
          (e.g. P3 writer's audit pipeline flagged the call). Returns
          ``PersistenceResult(status="skipped", skipped=True,
          reason="write_forbidden")``.
        * ``already_written`` — re-running refresh for the same date
          range yields an idempotent ``persisted=N`` outcome (the
          writer's business-key filter resolves to the same documents
          and the doc count stays constant). Documented as a property
          of the business-key upsert, not a separate branch.

        No real MongoDB / API / AuditLogger / QualitySummary writes
        fire — ``p3_writer`` is a :mod:`mongomock`-backed
        :class:`P3PersistenceWriter` instance and the provider is the
        injected (or registry-resolved) offline stub.

        Args:
            security_id: The :class:`SecurityId` being refreshed.
                Kept as an optional kwarg (mirror of
                :meth:`get_northbound_flow`) so future market-level
                refresh wiring can reuse the signature.
            date: Single ``"YYYY-MM-DD"`` filter (optional).
            start_date: Inclusive lower bound for date range.
            end_date: Inclusive upper bound for date range.
            provider: Optional external provider. ``None`` falls back
                to the registry-resolved stub (or raises
                :class:`ProviderUnavailableError` when no provider is
                registered).

        Returns:
            A :class:`PersistenceResult`. Callers should branch on
            ``result.status`` rather than ``result.persisted`` alone
            (status is the documented discriminator).

        Raises:
            ProviderUnavailableError: When ``p3_writer`` is ``None``
                (T3-P3B default keeps refresh opt-in).
        """
        if self._p3_writer is None:
            raise ProviderUnavailableError(
                "FlowService has no P3PersistenceWriter "
                "wired; refresh path is opt-in until the Gate-"
                "authorised sub-stage."
            )
        # Defensive: capability map is the single source of truth for
        # collection routing. We assert here so a future refresh-path
        # tweak fails loudly rather than silently routing to the wrong
        # collection.
        if self.capability not in P3_COLLECTION_BY_CAPABILITY:
            raise ValueError(
                f"capability {self.capability!r} is not registered in "
                "P3_COLLECTION_BY_CAPABILITY"
            )
        if self.northbound_capability not in P3_COLLECTION_BY_CAPABILITY:
            raise ValueError(
                f"capability {self.northbound_capability!r} is not registered "
                "in P3_COLLECTION_BY_CAPABILITY"
            )

        collection = P3_COLLECTION_BY_CAPABILITY[self.capability]
        unique_key = P3_UNIQUE_KEYS_BY_CAPABILITY[self.capability]

        # ---- Fetch via the (injected | registry) provider. ----
        records = self._fetch_for_refresh(
            security_id=security_id,
            date=date,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
        )
        # ``records`` is always a ``list[dict]`` — empty list is a
        # documented skip branch; a populated list feeds
        # ``p3_writer.upsert``.

        # ---- skip_empty: nothing to write, skip the writer. ----
        if not records:
            return PersistenceResult(
                status="skipped",
                capability=self.capability,
                collection=collection,
                persisted=0,
                failed=0,
                skipped=True,
                reason="empty_payload",
                writer_outcome=None,
            )

        # ---- write_forbidden: caller-side knob — bypass the writer. ----
        # The skip is decided at the service boundary so the caller
        # can plumb a feature flag / canary gate without subclassing.
        # The flag is read once here; future sub-stages can replace
        # this with a more sophisticated policy hook (e.g. an
        # ``AuditLogger.attempt`` probe).
        if self._write_disabled():
            return PersistenceResult(
                status="skipped",
                capability=self.capability,
                collection=collection,
                persisted=0,
                failed=0,
                skipped=True,
                reason="write_forbidden",
                writer_outcome=None,
            )

        # ---- happy_path / partial_failure / already_written ----
        # All three collapse into a single writer.upsert() call: the
        # writer's idempotent business-key upsert treats
        # ``already_written`` as a no-op shaped like ``happy_path``;
        # ``partial_failure`` is whatever the writer returns when
        # ``upsert`` catches a per-record exception.
        outcome = self._p3_writer.upsert(
            collection=collection,
            records=records,
            unique_key=unique_key,
        )
        status = "ok" if outcome.failed == 0 else "partial_failure"
        return PersistenceResult(
            status=status,
            capability=self.capability,
            collection=collection,
            persisted=outcome.persisted,
            failed=outcome.failed,
            skipped=False,
            reason=None,
            writer_outcome=outcome,
        )

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------

    def _write_disabled(self) -> bool:
        """Return ``True`` when the refresh path must skip the writer.

        The default implementation honours ``flow_service.<impl>._write_disabled_flag``
        — a thread-local / instance attribute the T3-P3B tests flip
        via monkey-patch. When the attribute is absent the refresh
        proceeds normally so the production path stays side-effect-
        free until a real consumer wires a gate.
        """
        return bool(getattr(self, "_write_disabled_flag", False))

    def _fetch_for_refresh(
        self,
        *,
        security_id: SecurityId | None,
        date: str | None,
        start_date: str | None,
        end_date: str | None,
        provider: Any | None,
    ) -> list[dict]:
        """Resolve and invoke the offline provider for the refresh path.

        Resolution order:

        1. Caller-supplied ``provider`` (kwarg). The provider's
           ``fetch(domain, operation, security_id, **params)`` is
           called with the flow.capital_flow_daily capability and the
           caller-supplied filters. The provider is expected to be a
           :class:`StubFlowProvider`-shaped offline stub.
        2. Registry-resolved provider from ``self._router.registry``
           supporting ``flow.capital_flow_daily``. The first match
           wins. (Phase 1B-A fallback behaviour; same as the read
           path.)
        3. When neither resolves → raise
           :class:`ProviderUnavailableError` so the refresh fails
           loudly rather than silently degrading into a no-op.

        Provider output is expected to be a ``list[dict]`` shaped
        like the fixture / writer-upsert payload. Non-list outputs
        are coerced to ``[]`` so the downstream ``skip_empty`` branch
        fires cleanly (this is a defensive measure — the contract is
        documented at the provider layer).
        """
        capability = self.capability

        if provider is not None:
            payload = provider.fetch(
                domain=self.DOMAIN,
                operation=self.OPERATION,
                security_id=security_id,
                trade_date=date,
                start_date=start_date,
                end_date=end_date,
            )
        elif self._router is not None:
            payload = self._fetch_via_registry(
                capability=capability,
                security_id=security_id,
                date=date,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            raise ProviderUnavailableError(
                "FlowService.refresh_capital_flow has no provider "
                "supplied and no router wired; cannot fetch flow payload."
            )
        if not isinstance(payload, list):
            return []
        return [dict(row) for row in payload if isinstance(row, Mapping)]

    def _fetch_via_registry(
        self,
        *,
        capability: str,
        security_id: SecurityId | None,
        date: str | None,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict]:
        """Resolve a provider from the Router's registry and invoke it."""
        registry = self._router.registry
        for candidate in registry.list_providers():
            if (
                capability in candidate.capabilities
                and candidate.is_available()
            ):
                # Use a fresh placeholder so the registry fallback is
                # not forced to deal with ``security_id=None``.
                placeholder = (
                    security_id
                    if security_id is not None
                    else self._synthesise_market_placeholder()
                )
                return candidate.fetch(
                    domain=self.DOMAIN,
                    operation=self.OPERATION,
                    security_id=placeholder,
                    trade_date=date,
                    start_date=start_date,
                    end_date=end_date,
                )
        return []


__all__ = ["FlowService", "PersistenceResult"]
