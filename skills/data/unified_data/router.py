"""Data router for unified_data.

The :class:`DataRouter` is the central piece that turns a query
(``domain``, ``operation``, ``security_id``, ``**params``) into a
:class:`DataResult`.

Phase 1B-A orchestration (SPEC-03-008 §4.3)
--------------------------------------------
1. **Provider override short-circuit** — when ``provider`` is supplied
   the Router dispatches directly:

   * ``provider == "ta_cn_internal"`` — Step 1 only. No external
     fallback.
   * ``provider`` is a known external name (``"tushare"`` /
     ``"akshare"``) — that single provider only, no chain.

2. **Internal-first four-step query** (default when no ``provider``
   override):

   * **Step 1 (TA-CN adapter)** — invoked only when
     ``self._ta_cn_adapter is not None`` AND the capability is one
     :data:`DataRouter._TA_CN_CAPABILITY_METHOD_MAP` covers AND
     ``force_refresh`` is ``False``. The Router consults the
     ``_TA_CN_NOT_COVERED`` frozenset first for the explicit "not
     covered" cases, then the method map for the "covered" cases.
     Outcomes:

     - Adapter returns a non-empty payload → ``DataResult.success``,
       ``provider="ta_cn_internal"``.
     - Adapter returns ``None`` / empty list AND the capability is in
       the method map → ``DataResult(provider="empty",
       freshness="empty")`` (no external fallback — TA-CN owns the
       capability, the data just is not present for this symbol).
     - Capability is in ``_TA_CN_NOT_COVERED`` (or missing from the
       method map) → ``None`` (Router proceeds to Step 4).
     - Adapter raises any exception → ``None`` plus a
       ``"ta_cn_internal(error: ...)"`` trace entry (Router proceeds
       to Step 4).

   * **Step 2 / Step 3** — Phase 1B-B slots (``local_mongo_adapter`` /
     ``cache_manager``). Always skipped in 1B-A — the constructor
     accepts the parameters for API stability but they must be
     ``None``.

   * **Step 4 (external fallback chain)** — try each provider in order:

     - Resolved from ``self._external_chains[capability]`` →
       ``self._config.fallback_for(capability)`` → registry insertion
       order.
     - Each candidate is checked for ``is_available()`` then
       ``fetch()``. Per-provider errors (``ProviderError`` /
       ``ProviderUnavailableError`` / ``UnsupportedCapabilityError``)
       are caught and recorded in ``source_trace``.

3. **Failure handling** — when every provider has been tried the
   Router returns :meth:`DataResult.error` (``provider="error"``)
   instead of raising :class:`AllProvidersFailedError`. This is the
   documented Phase 0 → 1B-A behaviour change (SPEC-03-008 §3.1
   "关键语义变更"). Callers that previously caught
   ``AllProvidersFailedError`` should now assert on the
   ``DataResult.provider == "error"`` branch.

The Router performs **no I/O of its own** beyond the adapter /
provider calls it orchestrates, so it can be unit-tested purely with
fake providers (and a fake ``TA_CNMongoAdapter`` for Step 1).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .config import UnifiedDataConfig
from .exceptions import (
    AllProvidersFailedError,
    ProviderError,
    ProviderUnavailableError,
    UnsupportedCapabilityError,
)
from .freshness import FreshnessPolicy
from .models import DataResult, Market, SecurityId
from .provider import DataProvider
from .registry import ProviderRegistry

logger = logging.getLogger(__name__)


class DataRouter:
    """Capability-aware query router with internal-first orchestration."""

    # ------------------------------------------------------------------
    # Phase 1B-A: TA-CN capability mapping
    # ------------------------------------------------------------------
    # ``capability → adapter_method_name``. The Router invokes the named
    # method on the injected ``TA_CNMongoAdapter`` (Phase 1A delivery)
    # when the capability is supported by TA-CN. The mapping is the
    # **hardcoded** cross-reference between SPEC-03-008 §4.4
    # capabilities and the 11 read methods the adapter exposes.
    _TA_CN_CAPABILITY_METHOD_MAP: dict[str, str] = {
        "market_data.kline_daily": "get_daily_bars",
        "market_data.realtime_quote": "get_realtime_quotes",
        "financial.income_statement": "get_financials",
        "financial.balance_sheet": "get_financials",
        "financial.cash_flow": "get_financials",
        "metadata.stock_list": "get_stock_list",
        "metadata.stock_info": "get_stock_info",
        "metadata.index_list": "get_index_list",
        "metadata.index_info": "get_index_info",
        "market_data.index_daily": "get_index_daily_bars",
        "news.stock_news": "get_news",
    }

    # TA-CN does not cover these capabilities — they are routed directly
    # to Step 4. Listed explicitly (SPEC-03-008 §4.4) so the Router can
    # answer "does TA-CN cover this?" with an O(1) membership check
    # instead of relying on a negative lookup against the method map.
    _TA_CN_NOT_COVERED: frozenset[str] = frozenset(
        {
            "market_data.kline_weekly",
            "market_data.adj_factor",
            "valuation.daily_basic",
            "calendar.trading_days",
            "calendar.is_trading_day",
            "metadata.index_members",
        }
    )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        registry: ProviderRegistry,
        config: UnifiedDataConfig | None = None,
        *,
        ta_cn_adapter: Any = None,
        local_mongo_adapter: Any = None,  # Phase 1B-B slot — always None in 1B-A
        cache_manager: Any = None,  # Phase 1B-B slot — always None in 1B-A
        freshness: FreshnessPolicy | None = None,
        external_fallback_chains: dict[str, list[str]] | None = None,
    ) -> None:
        """Build the router.

        Args:
            registry: The :class:`ProviderRegistry` used for Steps 4
                and the forced-provider branch.
            config: Optional :class:`UnifiedDataConfig`. The
                ``fallback_for(capability)`` value is used as the
                second-priority chain source.
            ta_cn_adapter: Optional TA-CN read-only adapter (Phase 1A
                delivery). ``None`` keeps the router on a Phase 0
                external-fallback-only behaviour.
            local_mongo_adapter: Phase 1B-B slot — must be ``None`` in
                1B-A.
            cache_manager: Phase 1B-B slot — must be ``None`` in 1B-A.
            freshness: Optional :class:`FreshnessPolicy`. Defaults to
                a fresh instance when omitted.
            external_fallback_chains: Optional per-capability chain
                overrides; takes priority over ``config`` and registry
                order.
        """
        self._registry = registry
        self._config = config or UnifiedDataConfig.minimal()
        self._ta_cn_adapter = ta_cn_adapter
        # Phase 1B-B: LocalMongoAdapter (Step 2) and CacheManager (Step 3)
        # are now active slots. ``None`` (the default) means "skip this
        # step" — the ``is not None`` guards inside ``query()`` /
        # ``_try_materialized`` / ``_try_cache`` short-circuit cleanly.
        # 1B-A's two ValueError guards were removed in 1B-B; see
        # SPEC-03-009 §4.1 and DESIGN-03-009 §3.4.3.
        self._local_mongo_adapter = local_mongo_adapter
        self._cache_manager = cache_manager
        self._freshness = freshness if freshness is not None else FreshnessPolicy()
        # Defensive copy of the chain overrides.
        self._external_chains: dict[str, list[str]] = {
            key: list(names) for key, names in (external_fallback_chains or {}).items()
        }

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def registry(self) -> ProviderRegistry:
        """The provider registry the router queries."""
        return self._registry

    @property
    def config(self) -> UnifiedDataConfig:
        """The active configuration."""
        return self._config

    @property
    def ta_cn_adapter(self) -> Any:
        """The TA-CN read-only adapter used for Step 1, or ``None``."""
        return self._ta_cn_adapter

    @property
    def freshness(self) -> FreshnessPolicy:
        """The freshness policy used to compute ``DataResult.freshness``."""
        return self._freshness

    # ------------------------------------------------------------------
    # Query
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

        See module docstring for the full orchestration rules. The
        ``DataResult.error`` branch (``provider == "error"``) replaces
        the Phase 0 ``AllProvidersFailedError`` raise.

        Args:
            domain: Domain name (``"market_data"``, ``"financial"``…).
            operation: Operation within the domain.
            security_id: The security being queried.
            provider: Optional explicit provider override.
            force_refresh: When ``True`` skip Step 1 (TA-CN) and any
                future cache layer. Has no effect when ``provider``
                already pins the source.
            market: Optional market filter. Defaults to
                ``security_id.market``.
            params: Forwarded to :meth:`DataProvider.fetch`.
            fetched_at: Override for the timestamp recorded on the
                result. Defaults to ``datetime.utcnow()``.

        Returns:
            A :class:`DataResult`. ``provider == "error"`` indicates
            every candidate failed; no exception is raised.

        Raises:
            ValueError: When ``domain`` / ``operation`` are malformed
                (the router does not silently coerce them).
        """
        capability = _validate_capability(domain, operation)
        # Surface malformed ``market`` eagerly — Phase 0 behaviour.
        self._resolve_market(market, security_id)
        params_dict = dict(params or {})
        ts = fetched_at or datetime.now(timezone.utc).replace(tzinfo=None)

        # ---- Branch 1: provider == "ta_cn_internal" → Step 1 only ----
        if provider == "ta_cn_internal":
            return self._query_ta_cn(security_id, capability, params_dict, ts)

        # ---- Branch 2: provider is a known external name → single
        # provider, no chain ----
        if provider is not None:
            return self._query_external_single(
                provider, security_id, capability, params_dict, ts
            )

        # ---- Branch 3: internal-first full path ----
        trace: list[str] = []
        domain, _, operation = capability.partition(".")
        empty_ta_cn: DataResult | None = None
        if (
            not force_refresh
            and self._ta_cn_adapter is not None
            and capability not in self._TA_CN_NOT_COVERED
            and capability in self._TA_CN_CAPABILITY_METHOD_MAP
        ):
            ta_cn_result = self._try_ta_cn(
                security_id, capability, params_dict, trace, ts
            )
            if ta_cn_result is not None:
                if ta_cn_result.provider != "empty":
                    # Real TA-CN hit — short-circuit.
                    return ta_cn_result
                # Empty TA-CN result: proceed to Step 2/3/4. Save it
                # as final fallback if everything else fails.
                empty_ta_cn = ta_cn_result
            # ta_cn_result is None when TA-CN does not cover the
            # capability or raised an exception. trace already
            # records the (skipped | error) entry.

        # Step 2 / Step 3 are the Phase 1B-B persistence-cache plane
        # (LocalMongoAdapter / CacheManager). Both default to ``None`` —
        # the ``is not None`` guards skip the step entirely when no
        # component is wired in, preserving 1B-A behaviour for the
        # existing Phase 0 / 1B-A / 1B-A test suites.
        # We pass the local trace along so a ``ta_cn_internal(error:
        # ...)`` entry survives into the final DataResult (Design
        # §4.2 DR-109).
        result = self._query_external_chain_with_cache(
            security_id,
            capability,
            domain,
            operation,
            params_dict,
            ts,
            inherited_trace=trace,
            force_refresh=force_refresh,
        )
        if result.provider == "error" and empty_ta_cn is not None:
            # Everything failed, return the empty TA-CN result instead
            # of pure "error" (SPEC-03-008 §4.3).
            return empty_ta_cn
        return result

    # ------------------------------------------------------------------
    # Step 1: TA-CN
    # ------------------------------------------------------------------

    def _try_ta_cn(
        self,
        security_id: SecurityId,
        capability: str,
        params: dict,
        trace: list[str],
        ts: datetime,
    ) -> DataResult | None:
        """Attempt Step 1 against the TA-CN adapter.

        Returns:
            * A :class:`DataResult` (success or empty) when TA-CN owns
              the capability — caller short-circuits.
            * ``None`` when the capability is not covered OR the
              adapter raised — caller proceeds to Step 4.
        """
        method_name = self._TA_CN_CAPABILITY_METHOD_MAP.get(capability)
        if method_name is None:
            # Defensive: should already have been filtered by caller,
            # but guard against future map edits.
            trace.append(f"ta_cn_internal(skipped: not covered)")
            return None

        adapter_method = getattr(self._ta_cn_adapter, method_name, None)
        if adapter_method is None:
            trace.append(
                f"ta_cn_internal(skipped: adapter missing {method_name})"
            )
            return None

        domain, _, operation = capability.partition(".")
        try:
            raw = adapter_method(security_id.symbol, **self._adapter_kwargs(params))
        except Exception as exc:
            trace.append(f"ta_cn_internal(error: {exc})")
            return None

        # TA-CN covered the capability but returned no data → empty
        # DataResult, do NOT fall back to external (SPEC-03-008 §4.3).
        if raw is None or (isinstance(raw, list) and not raw):
            trace.append("ta_cn_internal(empty)")
            return DataResult(
                data=None,
                security_id=security_id,
                domain=domain,
                operation=operation,
                provider="empty",
                fetched_at=ts,
                freshness="empty",
                source_trace=list(trace),
                warnings=[],
            )

        trace.append("ta_cn_internal(ok)")
        freshness_label = self._freshness.label(
            ts, _data_date_signal(raw), domain, False
        )
        return DataResult(
            data=raw,
            security_id=security_id,
            domain=domain,
            operation=operation,
            provider="ta_cn_internal",
            fetched_at=ts,
            source_trace=list(trace),
            freshness=freshness_label,
        )

    def _query_ta_cn(
        self,
        security_id: SecurityId,
        capability: str,
        params: dict,
        ts: datetime,
    ) -> DataResult:
        """``provider == "ta_cn_internal"`` branch.

        Always Step 1 only. Returns ``DataResult.error`` when no adapter
        is injected, the capability is not covered, or the adapter
        raises.
        """
        domain, _, operation = capability.partition(".")
        trace: list[str] = []
        if self._ta_cn_adapter is None:
            trace.append("ta_cn_internal(skipped: adapter not configured)")
            return self._build_error_result(
                security_id, domain, operation, ts, trace
            )
        if (
            capability in self._TA_CN_NOT_COVERED
            or capability not in self._TA_CN_CAPABILITY_METHOD_MAP
        ):
            trace.append(f"ta_cn_internal(skipped: not covered)")
            return self._build_error_result(
                security_id, domain, operation, ts, trace
            )
        result = self._try_ta_cn(security_id, capability, params, trace, ts)
        if result is not None:
            return result
        return self._build_error_result(security_id, domain, operation, ts, trace)

    @staticmethod
    def _adapter_kwargs(params: dict) -> dict:
        """Pick the kwargs the TA-CN adapter accepts from ``params``.

        Phase 1A's TA-CN adapter methods accept a fixed set of keyword
        arguments; anything else is silently dropped to keep the Router
        a thin facade.
        """
        allowed = {
            "start_date",
            "end_date",
            "limit",
            "report_period",
            "market",
            "status",
        }
        return {k: v for k, v in params.items() if k in allowed}

    # ------------------------------------------------------------------
    # Step 2 / Step 3 / materialization (Phase 1B-B)
    # ------------------------------------------------------------------

    def _try_materialized(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None,
        trace: list[str],
        ts: datetime,
        force_refresh: bool = False,
    ) -> DataResult | None:
        """Step 2: consult :class:`LocalMongoAdapter`.

        Returns:
            * A :class:`DataResult` with ``provider="ud_materialized"``,
              ``freshness="cached"`` on a non-expired hit.
            * ``None`` otherwise (miss / expired / component disabled /
              error).

        The underlying adapter already catches its own exceptions
        (LM-104), so this wrapper is defensive only — it logs and
        returns ``None`` if anything escapes the adapter.

        Trace behaviour (DR-213):
            * ``adapter is None`` → trace records
              ``"ud_materialized(skipped: no adapter)"`` so callers
              can see the Step 2 component was not wired in.
            * ``force_refresh=True`` → trace records
              ``"ud_materialized(skipped: force_refresh)"``. The
              two skip reasons are kept distinct: a missing adapter
              and an explicit force-refresh are different signals.
            * Adapter miss / hit / error → trace records the
              canonical outcome.
        """
        if self._local_mongo_adapter is None:
            # Adapter slot not wired in — record the skip reason
            # explicitly per DR-213 so downstream observability
            # can distinguish "no Step 2 component" from a miss.
            trace.append("ud_materialized(skipped: no adapter)")
            return None
        if force_refresh:
            trace.append("ud_materialized(skipped: force_refresh)")
            return None
        try:
            cached = self._local_mongo_adapter.get(
                security_id, domain, operation, params
            )
        except Exception as exc:
            logger.warning("LocalMongoAdapter.get failed in router: %s", exc)
            trace.append(f"ud_materialized(error: {exc})")
            return None
        if cached is not None:
            trace.append("ud_materialized(ok)")
            return cached
        trace.append("ud_materialized(miss)")
        return None

    def _try_cache(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None,
        trace: list[str],
        ts: datetime,
        force_refresh: bool = False,
    ) -> DataResult | None:
        """Step 3: consult :class:`CacheManager`.

        Returns:
            * A :class:`DataResult` with ``freshness="cached"`` and the
              **original** ``provider`` on a non-expired hit.
            * ``None`` otherwise (miss / expired / component disabled /
              error).

        Trace behaviour (DR-214):
            * ``manager is None`` → trace records
              ``"cache(skipped: no manager)"`` so callers can see
              the Step 3 component was not wired in.
            * ``force_refresh=True`` → trace records
              ``"cache(skipped: force_refresh)"``. The two skip
              reasons are kept distinct: a missing manager and an
              explicit force-refresh are different signals.
            * Adapter miss / hit / error → trace records the
              canonical outcome.
        """
        if self._cache_manager is None:
            # Manager slot not wired in — record the skip reason
            # explicitly per DR-214 so downstream observability
            # can distinguish "no Step 3 component" from a miss.
            trace.append("cache(skipped: no manager)")
            return None
        if force_refresh:
            trace.append("cache(skipped: force_refresh)")
            return None
        try:
            cached = self._cache_manager.get(
                security_id, domain, operation, params
            )
        except Exception as exc:
            logger.warning("CacheManager.get failed in router: %s", exc)
            trace.append(f"cache(error: {exc})")
            return None
        if cached is not None:
            trace.append("cache(ok)")
            return cached
        trace.append("cache(miss)")
        return None

    def _materialize(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None,
        result: DataResult,
    ) -> None:
        """Persist ``result`` into the persistence and cache layers.

        Synchronous, catch-and-log (MW-101..MW-104). Failure of either
        write does not affect ``result`` or its callers. Used only when
        Step 4 produced a successful external result.
        """
        if self._local_mongo_adapter is not None:
            try:
                self._local_mongo_adapter.put(
                    security_id, domain, operation, params, result
                )
            except Exception as exc:
                logger.warning("LocalMongoAdapter.put failed in router: %s", exc)
        if self._cache_manager is not None:
            try:
                self._cache_manager.put(
                    security_id, domain, operation, params, result
                )
            except Exception as exc:
                logger.warning("CacheManager.put failed in router: %s", exc)

    def _query_external_chain_with_cache(
        self,
        security_id: SecurityId,
        capability: str,
        domain: str,
        operation: str,
        params: dict,
        ts: datetime,
        inherited_trace: list[str] | None,
        force_refresh: bool = False,
    ) -> DataResult:
        """Run Step 2 → Step 3 → Step 4 with the cache layer wired in.

        When ``force_refresh=True`` Step 2 (materialised) and Step 3
        (query cache) are skipped — the caller wants a fresh result
        from the external chain. Materialisation still happens after a
        successful external fetch, so the next normal query can hit
        the fresh data.

        Kept as a dedicated helper (rather than inlined into ``query``)
        so that the orchestrator's main branch stays readable and so
        the cache behaviour can be tested in isolation when needed.
        The signature accepts the already-parsed ``(domain,
        operation)`` pair to avoid recomputing ``capability.partition``.
        """
        trace: list[str] = (
            list(inherited_trace) if inherited_trace is not None else []
        )

        # Step 2 (UD materialised). The helper self-manages the
        # ``force_refresh`` trace (``(skipped: force_refresh)``) and
        # returns ``None`` without calling ``LocalMongoAdapter.get()``.
        materialized = self._try_materialized(
            security_id, domain, operation, params, trace, ts,
            force_refresh=force_refresh,
        )
        if materialized is not None:
            return materialized

        # Step 3 (short-TTL query cache). Same self-managed
        # ``force_refresh`` behaviour as Step 2.
        cached = self._try_cache(
            security_id, domain, operation, params, trace, ts,
            force_refresh=force_refresh,
        )
        if cached is not None:
            return cached

        # Step 4 (external fallback chain).
        external_result = self._query_external_chain(
            security_id, capability, params, ts, inherited_trace=trace
        )
        if external_result.provider not in ("error", "empty"):
            # Persist a successful external hit into both the
            # materialised layer (Step 2 source) and the cache
            # (Step 3 source). ``_materialize`` is catch-and-log;
            # any failure is swallowed and the caller still sees the
            # external result unchanged.
            self._materialize(
                security_id, domain, operation, params, external_result
            )
        return external_result

    # ------------------------------------------------------------------
    # Step 4: external fallback
    # ------------------------------------------------------------------

    def _query_external_single(
        self,
        provider_name: str,
        security_id: SecurityId,
        capability: str,
        params: dict,
        ts: datetime,
    ) -> DataResult:
        """``provider`` pin against a single external provider.

        No fallback chain — failure produces ``DataResult.error``
        directly.
        """
        domain, _, operation = capability.partition(".")
        trace: list[str] = []
        provider_obj = self._registry.get(provider_name)
        if provider_obj is None:
            trace.append(f"{provider_name}(skipped: not registered)")
            return self._build_error_result(security_id, domain, operation, ts, trace)
        if not provider_obj.supports(capability, security_id.market):
            trace.append(
                f"{provider_name}(skipped: capability/market mismatch)"
            )
            return self._build_error_result(security_id, domain, operation, ts, trace)
        if not provider_obj.is_available():
            trace.append(f"{provider_name}(skipped: unavailable)")
            return self._build_error_result(security_id, domain, operation, ts, trace)
        result_data = self._attempt_provider_fetch(
            provider_obj, domain, operation, security_id, params, trace
        )
        if result_data is None:
            return self._build_error_result(security_id, domain, operation, ts, trace)
        trace.append(f"{provider_name}(ok)")
        freshness_label = self._freshness.label(
            ts, _data_date_signal(result_data), domain, False
        )
        # NOTE: we bypass ``DataResult.success`` here because its
        # ``**kwargs`` design conflicts with ``DataResult``'s explicit
        # ``freshness`` field (passing both raises "multiple values for
        # keyword argument"). Constructing directly keeps the field
        # names consistent with the dataclass.
        return DataResult(
            data=result_data,
            security_id=security_id,
            domain=domain,
            operation=operation,
            provider=provider_name,
            fetched_at=ts,
            source_trace=list(trace),
            freshness=freshness_label,
        )

    def _query_external_chain(
        self,
        security_id: SecurityId,
        capability: str,
        params: dict,
        ts: datetime,
        inherited_trace: list[str] | None = None,
    ) -> DataResult:
        """Step 4: try every candidate in the resolved chain.

        ``inherited_trace`` (optional) lets the caller pre-seed
        ``source_trace`` with entries from a prior Step — e.g. a
        ``ta_cn_internal(error: ...)`` entry that should survive into
        the final DataResult.

        Failure modes (priority order):

        * No chain resolved (registry empty) → ``DataResult.error``,
          ``source_trace=[]``.
        * Every candidate unavailable → ``DataResult.error`` with a
          warning ``"all external providers unavailable"``.
        * Every candidate fails on ``fetch()`` → ``DataResult.error``
          with a warning ``"all external providers failed"``.
        """
        domain, _, operation = capability.partition(".")
        # Reuse the inherited trace when provided so callers can stitch
        # earlier steps (TA-CN exception) into the final result.
        trace: list[str] = list(inherited_trace) if inherited_trace is not None else []
        chain_names = self._resolve_external_chain(capability)
        if not chain_names:
            return self._build_error_result(security_id, domain, operation, ts, trace)

        primary_failed = False
        saw_unavailable = False
        first_provider_name: str | None = None
        # Capture any TA-CN failure trace that was inherited from
        # Step 1 — when the external chain eventually succeeds we still
        # need to surface that degradation to the caller via
        # ``warnings`` (DESIGN-03-008 §4.2 DR-101).
        inherited_ta_cn_warnings = _lift_ta_cn_failure_warnings(inherited_trace)
        for name in chain_names:
            provider_obj = self._registry.get(name)
            if provider_obj is None:
                trace.append(f"{name}(skipped: not registered)")
                continue
            if not provider_obj.supports(capability, security_id.market):
                trace.append(
                    f"{name}(skipped: capability/market mismatch)"
                )
                continue
            if not provider_obj.is_available():
                trace.append(f"{name}(skipped: unavailable)")
                first_provider_name = first_provider_name or name
                saw_unavailable = True
                continue
            first_provider_name = first_provider_name or name
            result_data = self._attempt_provider_fetch(
                provider_obj, domain, operation, security_id, params, trace
            )
            if result_data is not None:
                trace.append(f"{name}(ok)")
                freshness_label = self._freshness.label(
                    ts, _data_date_signal(result_data), domain, False
                )
                return DataResult(
                    data=result_data,
                    security_id=security_id,
                    domain=domain,
                    operation=operation,
                    provider=name,
                    fetched_at=ts,
                    source_trace=list(trace),
                    freshness=freshness_label,
                    warnings=list(inherited_ta_cn_warnings),
                )
            primary_failed = True

        return self._build_error_result(
            security_id,
            domain,
            operation,
            ts,
            trace,
            all_unavailable=saw_unavailable and not primary_failed,
            # Per Design §4.2 DR-106/107 the final error result tags
            # the failure with ``provider == "error"`` so callers can
            # detect the branch from a single field. The original
            # provider names survive in ``source_trace``.
            primary_provider=None,
        )

    def _resolve_external_chain(self, capability: str) -> list[str]:
        """Resolve the external fallback chain for ``capability``.

        Priority (per SPEC-03-008 §4.1 / §4.2):

        1. Constructor-injected ``external_fallback_chains`` (also
           accessible via ``self._registry.get_external_fallback_chain``).
        2. :class:`UnifiedDataConfig` per-capability override
           (``config.fallback_for(capability)``).
        3. Registry insertion order for the capability.
        """
        chain = self._external_chains.get(capability)
        if chain:
            return list(chain)
        chain = self._registry.get_external_fallback_chain(capability)
        if chain:
            return list(chain)
        chain = self._config.fallback_for(capability)
        if chain:
            return list(chain)
        providers = self._registry.get_providers(capability)
        return [p.name for p in providers]

    @staticmethod
    def _attempt_provider_fetch(
        provider_obj: DataProvider,
        domain: str,
        operation: str,
        security_id: SecurityId,
        params: dict,
        trace: list[str],
    ) -> Any | None:
        """Call ``provider.fetch`` and translate exceptions into trace.

        Returns the raw payload on success or ``None`` on every failure
        path. Trace is mutated in place with the canonical outcome
        string (``"<name>(error: ...)"`` / ``"<name>(unavailable: ...)"``).
        """
        name = provider_obj.name
        try:
            return provider_obj.fetch(domain, operation, security_id, **params)
        except UnsupportedCapabilityError as exc:
            trace.append(f"{name}(error: {exc})")
            return None
        except ProviderUnavailableError as exc:
            trace.append(f"{name}(unavailable: {exc})")
            return None
        except ProviderError as exc:
            trace.append(f"{name}(error: {exc})")
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_error_result(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        ts: datetime,
        trace: list[str],
        *,
        all_unavailable: bool = False,
        primary_provider: str | None = None,
    ) -> DataResult:
        """Build a uniform ``DataResult.error``.

        The ``warnings`` field is filled with a single-line summary so
        callers can detect "no provider even registered" (empty
        warnings) vs "every candidate was unavailable" (warning
        ``"all external providers unavailable"``) vs "every
        candidate errored" (warning ``"all external providers
        failed"``).
        """
        warning: str
        if not trace:
            warning = "no providers registered"
        elif all_unavailable:
            warning = "all external providers unavailable"
        else:
            warning = "all external providers failed"
        # Construct directly so callers can preserve an empty trace
        # (e.g. "no provider even registered"). ``DataResult.error``
        # treats an empty ``source_trace`` as falsy and substitutes a
        # synthetic entry, which would mask the empty-chain signal we
        # want to expose.
        return DataResult(
            data=None,
            security_id=security_id,
            domain=domain,
            operation=operation,
            provider=primary_provider or "error",
            fetched_at=ts,
            source_trace=list(trace),
            freshness="empty",
            warnings=[warning],
        )

    @staticmethod
    def _resolve_market(
        market: Market | str | None,
        security_id: SecurityId,
    ) -> Market:
        if market is None:
            return security_id.market
        if isinstance(market, Market):
            return market
        try:
            return Market(market)
        except ValueError as exc:
            raise ValueError(
                f"Unknown market {market!r}; expected one of "
                f"{[m.value for m in Market]}"
            ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_capability(domain: str, operation: str) -> str:
    """Validate and combine ``domain`` + ``operation`` into a capability."""
    if not isinstance(domain, str) or not domain.strip() or "." in domain:
        raise ValueError(f"domain must be a non-empty string without '.', got {domain!r}")
    if not isinstance(operation, str) or not operation.strip() or "." in operation:
        raise ValueError(
            f"operation must be a non-empty string without '.', got {operation!r}"
        )
    return f"{domain}.{operation}"


def _data_date_signal(payload: Any) -> str | None:
    """Best-effort signal that ``payload`` carries a usable data date.

    For Phase 1B-A the Router only needs a boolean-ish signal: when the
    payload is ``None`` / empty list / empty dict / empty DataFrame we
    pass ``None`` so :meth:`FreshnessPolicy.label` short-circuits to
    ``"empty"``. Anything else passes the string ``"non-empty"`` so
    ``label`` computes the usual ``realtime`` / ``delayed`` branch.
    """
    if payload is None:
        return None
    if isinstance(payload, list):
        return None if not payload else "non-empty"
    if isinstance(payload, dict):
        return None if not payload else "non-empty"
    # pandas DataFrame — duck-type the empty check so we do not require
    # a hard pandas import in this module's hot path.
    empty_attr = getattr(payload, "empty", None)
    if empty_attr is True:
        return None
    return "non-empty"


def _lift_ta_cn_failure_warnings(inherited_trace: list[str] | None) -> list[str]:
    """Convert a TA-CN failure trace entry into user-visible warnings.

    ``_query_external_chain`` accepts an optional ``inherited_trace``
    that the caller pre-seeded with the Step 1 outcome. When the
    inherited entry records a TA-CN error we want the eventual
    successful external result to also carry that signal in
    ``DataResult.warnings`` so callers can detect that the data was
    served by an external provider rather than the primary TA-CN source
    (DESIGN-03-008 §4.2 DR-101).

    Two warnings are emitted so tests / callers can use either the
    short marker (``"ta_cn_internal"``) or the detailed reason. Tests
    assert on the short marker; humans / logs typically want the
    detailed one.
    """
    if not inherited_trace:
        return []
    if not any("ta_cn_internal(error" in entry for entry in inherited_trace):
        return []
    return [
        "ta_cn_internal",
        next(
            entry
            for entry in inherited_trace
            if "ta_cn_internal(error" in entry
        ),
    ]


__all__ = ["DataRouter"]


# ``AllProvidersFailedError`` is intentionally re-exported via the
# exceptions module — keeping the name reachable from router consumers
# that still import it for compatibility, even though Phase 1B-A
# itself never raises it. The import is left referenced to avoid an
# "unused import" lint while still documenting the contract.
_ = (Iterable, Mapping, AllProvidersFailedError)  # noqa: F841