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

* **Refresh path** — :meth:`refresh_capital_flow` is **reserved** under
  the P3-B three-state guard (T3-P3B M3). Two terminal states, both
  exceptions: ``p3_writer is None`` → :class:`ProviderUnavailableError`;
  writer wired → :class:`NotImplementedError`. Both paths execute
  **zero** ``provider.fetch`` / **zero** ``writer.upsert`` (no real
  MongoDB / AuditLogger / QualitySummary writes — strictly
  ``mongomock`` / ``FakeWriter``). The five-branch offline contract
  (``happy_path`` / ``partial_failure`` / ``skip_empty`` /
  ``write_forbidden`` / ``already_written``) is deferred to a future
  Gate-authorised sub-stage (T3-P3B M5) and is NOT yet wired.

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

    **Currently unreachable** under P3-B T3-Implement — ``refresh_capital_flow``
    always raises ``NotImplementedError`` when a writer is wired and
    ``ProviderUnavailableError`` when no writer is wired. This shape is
    retained for the future Gate-authorised sub-stage (T3-P3B M5) where
    the five-branch offline contract (``happy_path`` / ``partial_failure`` /
    ``skip_empty`` / ``write_forbidden`` / ``already_written``) collapse into a single result shape. The discriminator is :attr:`status`. Persisted /
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
                path. ``None`` keeps refresh opt-in (T3-P3B scope).
            audit_logger: Reserved — T3-P3B relies on the writer's
                built-in fail-open audit logger (B.b P0.1 patch).
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
        # :class:`SectorService` contract; the static
        # ``_is_northbound_refresh_disallowed`` guard above stays
        # hard-wired so ``flow.northbound_daily`` is **never**
        # activated).
        self._refresh_authorized: bool = False

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
        ``flow.northbound_daily`` capability intersects the P3-B
        fail-stop contract from RFC-03-014 §13.4.5.10 R0 conflict C:
        the projection factory
        :meth:`CapitalFlowRecord.from_northbound_dict` forces every
        payload field — the five flow bands (``main_net_inflow``,
        ``super_large_net_inflow``, ``large_net_inflow``,
        ``medium_net_inflow``, ``small_net_inflow``), the ratio field
        (``main_net_inflow_ratio``), the three ``margin_*`` fields,
        AND **all three** ``northbound_*`` fields
        (``northbound_net_inflow``, ``northbound_hold_shares``,
        ``northbound_hold_ratio``) — to be explicitly ``None``,
        regardless of what the upstream source dict carries. Only the
        ``{symbol, market, trade_date}`` business key and the
        ``fetched_at`` / ``provider`` metadata are read from the dict.

        Callers of this method therefore receive a
        ``list[CapitalFlowRecord]`` whose three ``northbound_*``
        fields are **always** ``None`` under P3-B T3-Implement — the
        service does not populate / fill them. The full V0.5 §3.2
        projection is applied at the ``DataResult.data`` boundary
        (T3-P3B M2).

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
            ``list[CapitalFlowRecord]`` with the P3-B fail-stop
            northbound projection applied — only the
            ``{symbol, market, trade_date}`` business key plus
            ``fetched_at`` / ``provider`` metadata are populated.
            Every payload field, **including all three**
            ``northbound_*`` fields, is explicitly ``None``. No
            northbound projection currently populates these fields;
            ``from_northbound_dict`` enforces the fail-stop in the
            constructor.

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
        """Refresh path — three-state guard (P0) + happy-path (P1).

        The P0 contract pinned the two terminal states (no writer →
        :class:`ProviderUnavailableError`; wired writer →
        :class:`NotImplementedError`). P1 widens the contract with
        an **authorised** state that walks the full happy-path
        (DESIGN §P1.5.2):

        1. ``p3_writer is None`` → :class:`ProviderUnavailableError`.
        2. writer wired but ``_is_refresh_authorized`` is ``False``
           → :class:`NotImplementedError` (the default state — the
           P0 contract stays intact for every existing test).
        3. authorised → fetch via Provider → upsert via writer →
           :class:`PersistenceResult` (mocks + mongomock in P1;
           real MongoDB lives in P1.5 / P2 only).

        The ``flow.northbound_daily`` capability is **never**
        authorised — :meth:`_is_northbound_refresh_disallowed`
        short-circuits the flag. Northbound callers should use
        :meth:`refresh_northbound_flow` which always returns a
        ``PersistenceResult(status='skipped', ...)``.

        Both path-2 and path-3 execute **zero** ``provider.fetch``
        and **zero** ``writer.upsert`` outside the happy-path
        branches. The :class:`PersistenceResult` shape and its
        five-branch semantics exist in the codebase as a forward
        reference for M5 only — they are reachable today via the
        authorised state.

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
            A :class:`PersistenceResult` (P1.5 / P2 reachable; under
            the default-deny state both paths raise instead).

        Raises:
            ProviderUnavailableError: When ``p3_writer`` is ``None``
                (P3-B default keeps refresh opt-in).
            NotImplementedError: When ``p3_writer`` is wired but
                ``_is_refresh_authorized`` is ``False`` (the P0
                default-deny default).
        """
        # P1 widening: when the per-instance toggle is on, walk the
        # full happy-path. The flow below is **the same** code that
        # the P0 static guard used to short-circuit; the gate just
        # moved one ``raise`` up so an authorised build can reach
        # the writer.upsert call.
        if self._p3_writer is not None and self._is_refresh_authorized(
            capability=self.capability
        ):
            return self._run_refresh(
                security_id=security_id,
                date=date,
                start_date=start_date,
                end_date=end_date,
                provider=provider,
                capability=self.capability,
            )
        if self._p3_writer is None:
            raise ProviderUnavailableError(
                "FlowService has no P3PersistenceWriter "
                "wired; refresh path is opt-in until the Gate-"
                "authorised sub-stage."
            )
        # P3-B three-state refresh guard: a wired writer but no
        # Gate-authorised sub-stage → NotImplementedError. This
        # prevents any provider.fetch or writer.upsert from firing
        # until the per-instance ``_refresh_authorized`` flag is
        # flipped to ``True`` (P0 contract — preserved verbatim).
        raise NotImplementedError(
            "FlowService.refresh_capital_flow is gated behind the "
            "per-instance ``_refresh_authorized`` flag (P1 default-"
            "deny); call ``enable_refresh()`` or wait for the "
            "Gate-authorised sub-stage to flip the toggle."
        )

    def refresh_northbound_flow(
        self,
        security_id: SecurityId | None = None,
        *,
        date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: Any | None = None,
    ) -> PersistenceResult:
        """Refresh path for ``flow.northbound_daily`` — always fail-stop.

        P3-B fail-stop contract (PB-7 / Pascal C). The method never
        reads from a provider and never writes to a writer; it
        returns a :class:`PersistenceResult` with
        ``status='skipped'`` and ``reason='northbound_refresh_disallowed (Pascal C)'``.
        The :class:`PersistenceResult` shape is identical to the
        happy-path return value so callers can treat the two
        branches uniformly.

        The companion guard :meth:`_is_northbound_refresh_disallowed`
        is the static source of truth; this method exists so callers
        who reach for ``refresh_<capability>`` get a deterministic
        skipped result instead of a raised exception.

        Args:
            security_id: Optional :class:`SecurityId`. **Not
                consulted** — the fail-stop branch fires before the
                filter is applied.
            date / start_date / end_date: All optional. **Not
                consulted** — same reason.
            provider: Optional external provider. **Not consulted**.

        Returns:
            A :class:`PersistenceResult` with
            ``status='skipped'`` /
            ``reason='northbound_refresh_disallowed (Pascal C)'``.
        """
        collection = P3_COLLECTION_BY_CAPABILITY.get(
            self.northbound_capability, "03_data_ud_stock_capital_flow"
        )
        return PersistenceResult(
            status="skipped",
            capability=self.northbound_capability,
            collection=collection,
            persisted=0,
            failed=0,
            skipped=True,
            reason="northbound_refresh_disallowed (Pascal C)",
            writer_outcome=None,
        )

    def _run_refresh(
        self,
        *,
        security_id: SecurityId | None,
        date: str | None,
        start_date: str | None,
        end_date: str | None,
        provider: Any | None,
        capability: str,
    ) -> PersistenceResult:
        """Happy-path shared by :meth:`refresh_capital_flow` and
        :meth:`refresh_limit_up_pool` (mirrored by the sentiment
        service's own helper).

        Branches:

        * ``records == []`` → ``status='skipped'`` /
          ``reason='empty_payload'`` (P3-B ``skip_empty``).
        * ``self._write_disabled()`` → ``status='skipped'`` /
          ``reason='write_forbidden'`` (P3-B ``write_forbidden``).
        * otherwise → ``writer.upsert`` → ``status='ok'`` /
          ``status='partial_failure'`` per
          :class:`UpsertOutcome` counts.
        """
        # P3 capability map defensive guard — fails loudly on
        # capability-map edits that would silently route writes to
        # the wrong collection.
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
                capability=capability,
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
                capability=capability,
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
        # Step 4: CacheManager.put (catch-and-log, mock-only in P1).
        self._put_cache(capability, records, security_id, date)
        status = "ok" if outcome.failed == 0 else "partial_failure"
        return PersistenceResult(
            status=status,
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
        security_id: SecurityId | None,
        date: str | None,
    ) -> None:
        """P1 Step 4: write refresh results into CacheManager (catch-and-log).

        Per SPEC §P1.5.2.bis: failure does NOT block the refresh main path.
        The cache write is mock-only in P1 — ``cache_manager`` defaults to
        ``None`` and is injected only in authorised tests.

        Cache key format: ``flow:capital_flow:{symbol}:{trade_date}``
        where ``symbol`` comes from ``security_id.symbol`` and
        ``trade_date`` from the single ``date`` kwarg.
        """
        if self._cache_manager is None:
            return
        symbol = security_id.symbol if security_id else ""
        td = date or ""
        cache_key = f"flow:capital_flow:{symbol}:{td}"
        try:
            self._cache_manager.put(cache_key, records)
        except Exception:
            logger.warning(
                "FlowService._put_cache: CacheManager.put failed "
                "(non-blocking, capability=%r)",
                capability,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_northbound_refresh_disallowed() -> bool:
        """PB-7 fail-stop guard — return ``True`` unconditionally.

        Per the P3-B three-state contract, ``flow.northbound_daily``
        refresh is **permanently disallowed** regardless of any
        configuration / construction kwargs. The guard is hard-coded
        (no env var, no override) so the northbound path can never
        silently transition to ``"authorized"`` in any code path.

        Returns:
            ``True`` always. Static method — no ``self`` access is
            required to express the invariant.

        See Also:
            :meth:`_is_refresh_authorized` — companion guard that
            always denies the ``flow.northbound_daily`` capability
            even when the writer is wired.
        """
        return True

    def _is_refresh_authorized(self, *, capability: str) -> bool:
        """PB-8 fail-stop guard — return ``False`` for northbound capability.

        P1 widened the static contract into an instance method that
        reads the per-instance ``_refresh_authorized`` flag. Two
        layers of guard still pin the contract:

        1. ``flow.northbound_daily`` is **always** ``False`` — the
           static northbound check short-circuits before the flag
           is consulted so a future ``enable_refresh()`` call cannot
           silently activate the northbound path.
        2. For every other capability the result mirrors the
           per-instance flag (``False`` by default — default-deny).

        Args:
            capability: The P3 capability the refresh targets
                (e.g. ``"flow.capital_flow_daily"`` /
                ``"flow.northbound_daily"``).

        Returns:
            ``False`` for ``"flow.northbound_daily"``; for every
            other capability the per-instance
            ``_refresh_authorized`` flag (default ``False``).
        """
        # PB-8: northbound capability is never authorised.
        if capability == "flow.northbound_daily":
            return False
        return bool(self._refresh_authorized)

    def enable_refresh(self) -> None:
        """Flip the per-instance refresh authorisation to ``True``.

        Convenience hook for the P1.5 / P2 production activation
        sub-stage (and for the unit-test fixture setup). The flag is
        intentionally per-instance so test isolation does not
        require a class-level reset. Production activation is gated
        by the Pascal Gate per P1.10 (G-B-2). The static
        ``_is_northbound_refresh_disallowed`` guard is unaffected —
        northbound refresh remains disallowed regardless of this
        toggle.
        """
        self._refresh_authorized = True

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
