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
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from ..adapters import TA_CNMongoAdapter
from ..adapters.p3_persistence_writer import (
    P3_COLLECTION_BY_CAPABILITY,
    P3_UNIQUE_KEYS_BY_CAPABILITY,
    P3PersistenceWriter,
)
from ..exceptions import ProviderUnavailableError, UnifiedDataError
from ..models import DataResult, Market, SecurityId
from ..models.domain.sentiment import (
    LimitUpPoolRecord,
    MarketSentimentSnapshot,
)
from ..router import DataRouter
# OQ-11 / DESIGN-03-014 V0.32 §OQ-11.2.1 — canonical location of
# ``SessionStatus`` and ``CompletedSessionPolicy`` migrates to the
# infra layer (``skills.infra.session_policy``). The service re-
# exports both names so existing module-level imports
# (``from skills.data.unified_data.services.sentiment_service
# import SessionStatus, CompletedSessionPolicy``) keep working
# unchanged. ``SessionPolicyError`` is imported so the validation
# helpers can map adapter failures onto the existing
# ``ProviderUnavailableError`` token without introducing a new
# public error.
from skills.infra.session_policy import (
    SessionStatus as _InfraSessionStatus,
    CompletedSessionPolicy as _InfraCompletedSessionPolicy,
    SessionPolicyError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EOD-1 / EOD-2 / EOD-3 closure (SPEC-03-014 V0.22 §3.3 / DESIGN-03-014 V0.29 §5.3)
# ---------------------------------------------------------------------------
#
# This block defines the canonical EOD validation surface for
# ``sentiment.market_snapshot`` / ``sentiment.limit_up_pool``. It is the
# **only** validation owner on the read or refresh path (DESIGN EOD-1);
# domain / provider / router / caller layers must not duplicate the
# judgement. The validation owner rule and the five stable error codes
# are frozen by SPEC-03-014 V0.22 §3.3 EOD-1~EOD-6 and inherited as-is
# by V0.23 (refresh-signature only).
# ---------------------------------------------------------------------------


# OQ-11 / DESIGN-03-014 V0.32 §OQ-11.2.3: canonical location of
# ``SessionStatus`` and ``CompletedSessionPolicy`` migrates to the
# infra layer (``skills.infra.session_policy``). The service re-
# exports both names via module-level aliases so existing callers
# (and existing tests) that import either symbol from
# ``skills.data.unified_data.services.sentiment_service`` continue
# to work unchanged. Behaviour, value, and identity are preserved:
# ``sentiment_service.SessionStatus is
# skills.infra.session_policy.SessionStatus`` and the four members
# are the same Python objects.
SessionStatus = _InfraSessionStatus
CompletedSessionPolicy = _InfraCompletedSessionPolicy


# Stable error code enum mirrored from SPEC §3.3 EOD-3. The string
# values are stable public tokens — tests and external callers assert
# on them. Renaming or widening the set requires a new SPEC iteration.
CODE_INVALID_DATE_FORMAT = "invalid_date_format"
CODE_INVALID_SNAPSHOT_TIME = "invalid_snapshot_time"
CODE_NOT_TRADING_DAY = "not_trading_day"
CODE_FUTURE_TRADING_DAY = "future_trading_day"
CODE_SESSION_NOT_COMPLETED = "session_not_completed"


class SentimentSessionValidationError(UnifiedDataError):
    """Stable EOD validation error raised by the service layer (SPEC EOD-3).

    Inherits :class:`UnifiedDataError` so consumers can catch either
    the base class or this specific subclass. The ``code`` attribute
    carries one of the five stable canonical codes from
    SPEC §3.3 EOD-3; ``message`` is a human-readable hint.

    No new codes may be added at the service layer — if an additional
    failure mode appears it must graduate through a new SPEC iteration
    first. The error never carries raw query payloads or secrets.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# Canonical ``YYYY-MM-DD`` format pattern. Used by every public ingress
# to fail fast on non-conforming input before any provider fetch,
# writer upsert, or cache put (DESIGN EOD-3 / EOD-5).
_DATE_REGEX = None  # lazy-imported; see :func:_is_canonical_date`.


def _is_canonical_date(date: object) -> bool:
    """Return ``True`` iff ``date`` is a canonical ``YYYY-MM-DD`` string.

    Pure-stdlib check (calendar / datetime are intentionally NOT used
    here so the T3 path stays side-effect-free — the production
    calendar reality is owned by the injected
    :class:`CompletedSessionPolicy`). The check tolerates ``None`` /
    non-string inputs by returning ``False`` so the caller can map to
    ``INVALID_DATE_FORMAT`` uniformly.
    """
    import re

    if not isinstance(date, str):
        return False
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", date))


def _coerce_session_status_to_code(status: SessionStatus) -> str:
    """Map a :class:`SessionStatus` verdict to its stable error code.

    Centralised so all four public ingress points share the same
    mapping table. The mapping is frozen by SPEC §3.3 EOD-3; do not
    alter without a spec update.
    """
    if status == SessionStatus.NOT_A_TRADING_DAY:
        return CODE_NOT_TRADING_DAY
    if status == SessionStatus.FUTURE_TRADING_DAY:
        return CODE_FUTURE_TRADING_DAY
    if status == SessionStatus.SESSION_NOT_COMPLETED:
        return CODE_SESSION_NOT_COMPLETED
    # COMPLETED → caller checks status, not error code.
    raise AssertionError(
        f"_coerce_session_status_to_code called with non-error verdict {status!r}"
    )


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
        completed_session_policy: CompletedSessionPolicy | None = None,
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
            completed_session_policy: Optional EOD session-validation
                seam (SPEC-03-014 V0.22 §3.3 EOD-2). When ``None``
                (default) the service preserves the legacy offline
                stub / defer path (no EOD check is performed). When
                injected, all four public ingress points
                (``get_market_sentiment_snapshot`` /
                ``get_limit_up_pool` / ``refresh_market_sentiment_snapshot`` /
                ``refresh_limit_up_pool``) call
                ``completed_session_policy.session_status(date)``
                **before** any provider fetch / writer upsert / cache
                put, and fail-fast with the stable
                :class:`SentimentSessionValidationError`. T3 forbids
                any implementation from consulting real calendars,
                system clocks, or the network — fakes only.
        """
        self._adapter = adapter
        self._router = router
        self._p3_writer = p3_writer
        self._audit_logger = audit_logger
        self._cache_manager = cache_manager
        # EOD-2 injection seam (SPEC-03-014 V0.22 §3.3). The default
        # ``None`` keeps the pre-T3 / legacy offline stub path intact
        # so existing tests that do not care about EOD validation do
        # not regress. Once a non-``None`` policy is injected all four
        # public ingress points fail-fast on the five stable codes.
        self._completed_session_policy: CompletedSessionPolicy | None = (
            completed_session_policy
        )
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

        EOD-1 / EOD-4 (SPEC V0.22 §3.3): when a
        :class:`CompletedSessionPolicy` is injected via the constructor,
        this method acts as the canonical validation owner —
        :meth:`_validate_eod_market_snapshot` runs **before** any
        provider fetch / writer upsert / cache put and raises
        :class:`SentimentSessionValidationError` on failure. When no
        policy is injected the legacy offline stub path is preserved.

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
            SentimentSessionValidationError: When a
                :class:`CompletedSessionPolicy` is injected and the
                canonical ``snapshot_date`` fails any of the five
                stable EOD checks (invalid format / non-``close``
                time / non-trading-day / future / session-not-completed).
            ProviderUnavailableError: When no router was injected
                (offline-only default — caller must inject).
        """
        # EOD-1 fail-fast (DESIGN §3.3): service-layer is the *only*
        # validation owner. When a policy is injected, the gate runs
        # before the router query (no provider fetch on failure).
        self._validate_eod_market_snapshot(
            snapshot_date=snapshot_date,
            snapshot_time=snapshot_time,
        )
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

        EOD-1 (SPEC V0.22 §3.3): when a
        :class:`CompletedSessionPolicy` is injected, the EOD gate
        runs **before** the three-state guard short-circuits (i.e.
        before any provider fetch / writer upsert / cache put).

        Args:
            snapshot_date: Calendar date (``"YYYY-MM-DD"``).
            snapshot_time: Observation time (``"HH:MM:SS"`` or
                ``"close"``). Defaults to ``"close"``.
            provider: Optional external provider. ``None`` falls back
                to the router's external chain.

        Raises:
            SentimentSessionValidationError: When a
                :class:`CompletedSessionPolicy` is injected and the
                canonical input fails the five-stable-code EOD gate.
                Raised **before** the three-state guard so a forbidden
                ``snapshot_time`` cannot be silently swallowed.
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
        # EOD-1 fail-fast: must run before any provider fetch / writer
        # upsert / cache put. When no policy is injected the helper is
        # a no-op so the legacy offline stub path is preserved.
        self._validate_eod_market_snapshot(
            snapshot_date=snapshot_date,
            snapshot_time=snapshot_time,
        )
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

        EOD-1 (SPEC V0.22 §3.3): when a :class:`CompletedSessionPolicy`
        is injected AND a non-``None`` ``trade_date`` is supplied,
        :meth:`_validate_eod_limit_up_pool` runs first and raises
        :class:`SentimentSessionValidationError` on failure. The
        implicit ``trade_date=None`` latest-available branch (read-only
        exception per SPEC §3.3) is preserved when no policy is
        injected.

        Args:
            trade_date: Trading day (``"YYYY-MM-DD"``). When ``None``
                the query returns records for the most recent available
                date as determined by the provider (legacy stub
                fallback / latest branch).

        Returns:
            A :class:`DataResult` whose ``data`` field is a
            ``list[LimitUpPoolRecord]``-compatible ``list[dict]``.
            ``provider == "empty"`` when the chain has no record;
            ``provider == "error"`` when every candidate failed.

        Raises:
            SentimentSessionValidationError: When a
                :class:`CompletedSessionPolicy` is injected and the
                explicit ``trade_date`` fails any of the four
                date-stable codes (format / non-trading / future /
                session-not-completed). ``INVALID_SNAPSHOT_TIME`` is
                N/A for this capability.
            ProviderUnavailableError: When no router was injected
                (offline-only default — caller must inject).
        """
        # EOD-1 fail-fast (DESIGN §3.3): the read path runs the same
        # gate when a policy is injected AND the caller passed an
        # explicit date. ``trade_date=None`` keeps the legacy
        # latest-available branch (read-only exception per SPEC §3.3).
        self._validate_eod_limit_up_pool(
            trade_date=trade_date,
            explicit=False,
        )
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
        trade_date: str,
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

        EOD-1 (SPEC V0.23 §3.3 Closure-2): ``trade_date`` is a
        **required** positional argument of canonical ``YYYY-MM-DD``
        shape. ``None`` / ``"latest"`` are forbidden at the type
        level — the strict signature raises ``TypeError`` on
        omission. The :meth:`_validate_eod_limit_up_pool` helper
        runs **before** any provider fetch / writer upsert / cache
        put and is the only validation owner. Five stable codes
        apply on this entry (the four date-related ones inherited
        from V0.22 plus the explicit ``INVALID_DATE_FORMAT`` for
        the ``"latest"`` smuggling case).

        The happy path passes the **same** canonical ``trade_date``
        to both the provider ``params`` dictionary and the
        date-scoped cache key inside :meth:`_run_limit_up_pool_refresh`
        so the date is never re-derived from the records after the
        fetch.

        Args:
            trade_date: Canonical ``YYYY-MM-DD`` trading date
                (**required** positional). ``None`` /
                ``"latest"`` are forbidden on this entry per
                SPEC-03-014 V0.23 Closure-2.
            p3_writer: :class:`P3PersistenceWriter` for the refresh
                path. ``None`` keeps refresh opt-in (offline scope).
                When supplied, it overrides the writer wired at
                construction time (forward-compat hook).
            provider: Optional :class:`DataProvider`. ``None`` falls
                back to the router's external chain.

        Raises:
            TypeError: When ``trade_date`` is omitted at the call
                site (the strict signature enforces the
                ``None``/``latest`` ban at the type level).
            SentimentSessionValidationError: When a
                :class:`CompletedSessionPolicy` is injected and the
                supplied canonical ``trade_date`` fails any of the
                four date-stable codes (format / non-trading / future
                / session-not-completed). Raised **before** the
                three-state guard so a forbidden date cannot silently
                fall through to the writer.
            ProviderUnavailableError: When ``p3_writer`` is ``None``.
            ValueError: When capability is not registered in
                :data:`P3_COLLECTION_BY_CAPABILITY`.
            NotImplementedError: When ``_is_refresh_authorized`` is
                ``False``.
        """
        # EOD-1 fail-fast (SPEC V0.23 Closure-2): ``trade_date`` is a
        # required positional argument at the type level; the helper
        # also rejects ``"latest"`` / non-canonical tokens. Runs
        # before any provider fetch / writer upsert / cache put.
        validated_trade_date = self._validate_eod_limit_up_pool(
            trade_date=trade_date,
            explicit=True,
        )
        # ``validated_trade_date`` is the canonical string when a
        # policy is wired; otherwise it is the caller-supplied value
        # when that value is canonical. The helper guarantees
        # non-None here on the explicit path.
        effective_writer = p3_writer if p3_writer is not None else self._p3_writer
        if (
            effective_writer is not None
            and self._is_refresh_authorized(capability=self.limit_up_capability)
        ):
            return self._run_limit_up_pool_refresh(
                p3_writer=effective_writer,
                provider=provider,
                trade_date=validated_trade_date,
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

    # ------------------------------------------------------------------
    # EOD validation helpers (SPEC-03-014 V0.22 §3.3 EOD-1~EOD-6)
    # ------------------------------------------------------------------
    #
    # The two ``_validate_eod_*`` helpers below are the **only**
    # validation owner seam for the four public ingress points. They
    # are no-ops when no ``completed_session_policy`` was injected at
    # construction time — this preserves the legacy offline stub path
    # so existing callers do not regress. Once a policy is injected
    # all four ingress points route through the helpers and fail-fast
    # before any provider fetch / writer upsert / cache put.

    def _validate_eod_market_snapshot(
        self,
        *,
        snapshot_date: str,
        snapshot_time: str,
    ) -> None:
        """Run the EOD gate for :meth:`get_market_sentiment_snapshot`.

        Order is deterministic so the failure code is unique:

        1. ``snapshot_date`` must be a canonical ``YYYY-MM-DD`` →
           ``INVALID_DATE_FORMAT`` (no provider call).
        2. ``snapshot_time`` must equal ``"close"`` →
           ``INVALID_SNAPSHOT_TIME`` (no provider call). This is a
           **service-layer** judgement (``MarketSentimentSnapshot.from_dict``
           stays a permissive parsing seam by design).
        3. When a policy was injected, ``session_status(snapshot_date)``
           must return ``COMPLETED``; any other verdict maps to its
           stable error code (``NOT_TRADING_DAY`` /
           ``FUTURE_TRADING_DAY`` / ``SESSION_NOT_COMPLETED``).
        """
        # Step 1: format check (canonical YYYY-MM-DD).
        if not _is_canonical_date(snapshot_date):
            raise SentimentSessionValidationError(
                code=CODE_INVALID_DATE_FORMAT,
                message=(
                    "snapshot_date must be a canonical YYYY-MM-DD string; "
                    f"got {snapshot_date!r}"
                ),
            )
        # Step 2: snapshot_time must be 'close' (DESIGN EOD-4).
        # ``MarketSentimentSnapshot.from_dict`` keeps the permissive
        # parsing seam — the service layer is the only judge.
        if snapshot_time != "close":
            raise SentimentSessionValidationError(
                code=CODE_INVALID_SNAPSHOT_TIME,
                message=(
                    "snapshot_time must be 'close' on the canonical EOD "
                    f"service path; got {snapshot_time!r}"
                ),
            )
        # Step 3: policy-driven session check.
        if self._completed_session_policy is None:
            return  # legacy offline stub path; preserve behaviour
        # OQ-11 / SPEC EOD-7.4: a production ``CompletedSessionPolicy``
        # may raise ``SessionPolicyError`` (calendar unavailable /
        # out-of-range / naive clock / invalid format). The service
        # layer maps the dependency-unavailable subclasses onto
        # the existing ``ProviderUnavailableError`` token so no new
        # public error code is introduced. The format error is
        # unreachable here (Step 1 already gated it).
        try:
            verdict = self._completed_session_policy.session_status(
                snapshot_date
            )
        except SessionPolicyError as exc:
            raise ProviderUnavailableError(
                f"CompletedSessionPolicy unavailable for "
                f"snapshot_date {snapshot_date!r}: "
                f"clock_source_class={exc.clock_source_class!r}, "
                f"reason={exc.reason!r}"
            ) from exc
        if verdict == SessionStatus.COMPLETED:
            return
        # Non-COMPLETED verdict → raise with the stable error code.
        code = _coerce_session_status_to_code(verdict)
        raise SentimentSessionValidationError(
            code=code,
            message=(
                f"CompletedSessionPolicy rejected snapshot_date "
                f"{snapshot_date!r}: verdict={verdict.value!r}"
            ),
        )

    def _validate_eod_limit_up_pool(
        self,
        *,
        trade_date: str | None,
        explicit: bool,
    ) -> str | None:
        """Run the EOD gate for the limit-up pool ingress points.

        Args:
            trade_date: The caller-supplied trade date (or ``None``).
            explicit: ``True`` for refresh / explicit-date read paths
                (``:refresh_limit_up_pool`` and read with a supplied
                ``trade_date``); ``False`` for
                ``get_limit_up_pool(trade_date=None)`` which is the
                documented **read-only** "latest available" exception
                (SPEC §3.3).

        Returns:
            ``None`` when the helper short-circuited the legacy
            offline path (no policy injected) **or** when the
            exception clause fired (only for the implicit read).
            Otherwise the *normalised* canonical ``YYYY-MM-DD`` string
            is returned so the caller can use it as the
            ``trade_date`` for provider params and the date-scoped
            cache key.
        """
        # Implicit-date read exception (SPEC §3.3): only allowed on the
        # read path with ``trade_date=None`` and no policy injected. If
        # a policy IS injected the explicit read must still validate.
        if trade_date is None:
            if not explicit:
                # Read path with implicit date → legacy latest branch.
                # Return ``None`` to signal "skip the policy check".
                return None
            # Refresh path with implicit date is forbidden
            # (``refresh_limit_up_pool`` never accepts ``None``); the
            # format check below is the only safety net.
            raise SentimentSessionValidationError(
                code=CODE_INVALID_DATE_FORMAT,
                message=(
                    "trade_date must be a canonical YYYY-MM-DD string; "
                    "got None on the explicit-date refresh path"
                ),
            )
        # Step 1: canonical format check.
        if not _is_canonical_date(trade_date):
            raise SentimentSessionValidationError(
                code=CODE_INVALID_DATE_FORMAT,
                message=(
                    "trade_date must be a canonical YYYY-MM-DD string; "
                    f"got {trade_date!r}"
                ),
            )
        # Step 2 (refresh only): also reject the literal ``"latest"``
        # token explicitly so the explicit-date promise holds even
        # for callers that smuggle a non-empty non-canonical token.
        if explicit and trade_date == "latest":
            raise SentimentSessionValidationError(
                code=CODE_INVALID_DATE_FORMAT,
                message=(
                    "trade_date 'latest' is forbidden on the explicit "
                    "refresh path; supply a canonical YYYY-MM-DD"
                ),
            )
        # Step 3: policy-driven session check.
        if self._completed_session_policy is None:
            return trade_date  # legacy offline stub path
        verdict = self._completed_session_policy.session_status(trade_date)
        if verdict == SessionStatus.COMPLETED:
            return trade_date
        code = _coerce_session_status_to_code(verdict)
        raise SentimentSessionValidationError(
            code=code,
            message=(
                f"CompletedSessionPolicy rejected trade_date "
                f"{trade_date!r}: verdict={verdict.value!r}"
            ),
        )

    def _has_eod_policy(self) -> bool:
        """Return ``True`` iff a :class:`CompletedSessionPolicy` is wired.

        Convenience used by the four public ingress points that
        previously had no notion of an EOD seam — letting tests
        detect whether legacy offline behaviour still applies.
        """
        return self._completed_session_policy is not None

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
        trade_date: str | None = None,
    ) -> Any:
        """Happy-path runner for ``sentiment.limit_up_pool``.

        Mirrors :meth:`_run_refresh` but the unique key is the
        per-stock ``{market, symbol, trade_date}`` set (P1.2) and
        the writer is supplied by the caller (the
        :meth:`refresh_limit_up_pool` kwarg overrides the
        constructor-wired one).

        SPEC V0.23 Closure-2 routing:

        * The same canonical ``trade_date`` is forwarded to both the
          Provider params ``{"trade_date": trade_date}`` and the
          date-scoped cache key. The date is **never** re-derived
          from the fetched records.
        * When ``trade_date`` is ``None`` (legacy / pre-V0.23
          callers that bypassed the EOD gate by passing no policy)
          the cache key remains the legacy suffix-less form so
          pre-existing callers do not regress; provider params
          remain empty to mirror the historical contract.
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

        # Forward the canonical trade_date to the Provider when the
        # caller threaded one through (SPEC V0.23 Closure-2).
        fetch_params: dict[str, Any] = {}
        if trade_date is not None:
            fetch_params["trade_date"] = trade_date
        records = self._fetch_for_refresh(
            capability=capability,
            provider=provider,
            params=fetch_params,
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
        # Pass the canonical trade_date through to the date-scoped
        # cache key so the cache entry is date-addressable.
        self._put_cache(capability, records, trade_date, None)
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


__all__ = [
    "MarketSentimentService",
    "SessionStatus",
    "CompletedSessionPolicy",
    "SentimentSessionValidationError",
    "CODE_INVALID_DATE_FORMAT",
    "CODE_INVALID_SNAPSHOT_TIME",
    "CODE_NOT_TRADING_DAY",
    "CODE_FUTURE_TRADING_DAY",
    "CODE_SESSION_NOT_COMPLETED",
]  # noqa: E501