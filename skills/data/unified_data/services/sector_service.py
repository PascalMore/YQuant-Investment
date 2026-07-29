"""Sector / index classification domain service (Phase 1A) and
P3-A snapshot / ranking service (Phase 3).

The service exposes two surfaces:

* **Phase 1A (TA-CN MongoDB read-only)** — three methods wrapping
  the ``stock_sector_info`` and ``index_daily_quotes`` TA-CN
  collections:

  * ``get_stock_sector``     — list of ``SectorClassification`` for a stock
  * ``get_stocks_by_sector`` — list of ``SectorClassification`` for an L1 sector
  * ``get_sector_index_bars`` — list of ``IndexDailyBar`` (申万行业指数路径)

* **Phase 3 P3-A (router-mediated)** — two methods routing through
  the DataRouter's external-fallback chain (SPEC-03-014 §5.5 /
  DESIGN-03-014 §17.3):

  * ``get_sector_snapshot(sector_code, date=None)`` — single
    ``SectorSnapshot`` (or ``None`` for empty).
  * ``get_sector_ranking(date=None, sector_type=None, limit=20)`` —
    ``list[SectorSnapshot]`` sorted by ``pct_chg`` desc with
    ``None pct_chg`` at the end and ``sector_code`` asc as the
    tiebreaker (DESIGN §17.3.3).

Note: ``get_sector_index_bars`` accepts ``sector_code`` directly instead
of a :class:`SecurityId` (the data model here is sector, not security).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..adapters import TA_CNMongoAdapter
from ..exceptions import ProviderUnavailableError
from ..models import DataResult, Market, SecurityId
from ..models.domain import IndexDailyBar, SectorClassification, SectorSnapshot
from . import SERVICE_ERRORS, wrap_empty, wrap_error, wrap_success

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..router import DataRouter

logger = logging.getLogger(__name__)


# Sort key: None pct_chg sinks to the end, then pct_chg desc,
# then sector_code asc, then sector_name asc as the final
# tiebreaker. ``SectorSnapshot`` is the canonical domain object
# returned by the router on the read path; the provider fetch
# returns ``list[dict]`` which the service maps to dataclass
# instances before sorting. The fourth tier (sector_name asc)
# is the stability requirement of DESIGN §17.3.3 — records that
# share pct_chg AND sector_code are deterministically ordered
# by their Chinese display name.
def _sector_ranking_key(record: SectorSnapshot) -> tuple[int, float, str, str]:
    """Return a sort key for ``SectorSnapshot`` ranking.

    Tuple layout (DESIGN-03-014 §17.3.3):

    1. ``0`` when ``pct_chg`` is numeric, ``1`` when it is ``None`` —
       pushes the empty ``pct_chg`` records to the end of the result
       regardless of the other fields' values.
    2. ``-pct_chg`` so larger values sort first (descending).
    3. ``sector_code`` (ascending) as the deterministic tiebreaker
       — two records with the same ``pct_chg`` always come out in the
       same order.
    4. ``sector_name`` (ascending) as the final stability tiebreaker
       — records sharing both ``pct_chg`` and ``sector_code`` are
       ordered by their Chinese display name (e.g. ``"白酒"`` < ``"证券"``).
    """
    sector_name = record.sector_name or ""
    if record.pct_chg is None:
        return (1, 0.0, record.sector_code, sector_name)
    return (0, -float(record.pct_chg), record.sector_code, sector_name)


class SectorService:
    """板块/行业域服务（Phase 1A — TA-CN MongoDB 只读 / Phase 3 P3-A — router 只读）。

    Construction signature is frozen at T3-A + D3 replacement:
    ``__init__(self, adapter, router: DataRouter | None = None)`` —
    no setter, no lazy attribute. ``adapter`` is required (Phase 1A
    regression guard, T3-A); ``router`` is the P3-A read-path
    dependency, defaulting to ``None`` so offline / Phase 1A-only
    callers keep working. The P3-A ``get_sector_snapshot`` /
    ``get_sector_ranking`` methods raise
    :class:`ProviderUnavailableError` when ``router is None``.

    Offline / T3-B scope: the router is the **only** dependency on
    Phase 3 infrastructure. No real MongoDB / AKShare / cron side
    effects. Provider registration, STUB_COLUMNS wiring, the
    ``UnifiedDataClient`` facade, and the persistence refresh path
    are out of T3-B scope and remain for T3-C.
    """

    DOMAIN = "sector"
    # Operation names — compose the capability string
    # ``f"{DOMAIN}.{OPERATION}"`` at the router boundary. These
    # match the SPEC-03-014 §5.5 / DESIGN-03-014 §17.4.1 capability
    # contract. T3-C owns the AKShare provider registration against
    # these strings; T3-B only references them.
    OPERATION_SNAPSHOT = "snapshot"
    OPERATION_RANKING = "ranking"

    def __init__(
        self,
        adapter: TA_CNMongoAdapter,
        router: "DataRouter | None" = None,
    ) -> None:
        self._adapter = adapter
        # P3-A router is wired at construction time. ``None`` is the
        # offline default — the snapshot / ranking methods will raise
        # ``ProviderUnavailableError`` until a router is injected.
        # Duck-typed intentionally (matches the test suite's fake
        # routers that don't subclass :class:`DataRouter`).
        self._router = router

    # ------------------------------------------------------------------
    # P3-A router wiring (read-only attribute)
    # ------------------------------------------------------------------

    @property
    def router(self) -> "DataRouter | None":
        """The DataRouter used on the P3-A read path (``None`` until injected).

        Read-only view: D3 removed the setter so callers cannot
        mutate the router post-construction. The router is wired
        via the ``router`` constructor kwarg; offline callers pass
        ``router=None`` and the snapshot / ranking methods raise
        :class:`ProviderUnavailableError`.
        """
        return self._router

    @property
    def capability_snapshot(self) -> str:
        """The canonical ``sector.snapshot`` capability string."""
        return f"{self.DOMAIN}.{self.OPERATION_SNAPSHOT}"

    @property
    def capability_ranking(self) -> str:
        """The canonical ``sector.ranking`` capability string."""
        return f"{self.DOMAIN}.{self.OPERATION_RANKING}"

    # ------------------------------------------------------------------
    # P3-A: get_sector_snapshot
    # ------------------------------------------------------------------

    def get_sector_snapshot(
        self,
        sector_code: str,
        date: str | None = None,
        *,
        security_id: SecurityId | None = None,
    ) -> DataResult:
        """Return a single :class:`SectorSnapshot` via the router.

        The router walks the internal-first path (Step 1 / 2 / 3
        skipped — ``sector.snapshot`` is in ``_TA_CN_NOT_COVERED`` per
        SPEC §5.5) and the external-fallback chain at Step 4. The
        returned ``DataResult.data`` is one :class:`SectorSnapshot`
        when the provider yields a record, or ``None`` when the
        provider yields an empty payload (``is_empty=True`` per
        Phase 0 contract). Errors propagate as
        ``DataResult(provider="error")``; the service never re-raises.

        Args:
            sector_code: Sector identifier (e.g. ``"BK0489"``). A
                blank value is treated as an empty query — the
                router receives a placeholder ``SecurityId`` and the
                provider decides what to return.
            date: Optional trading-day selector (``"YYYY-MM-DD"``).
                ``None`` lets the provider pick the most recent
                available snapshot.
            security_id: Optional :class:`SecurityId` for log
                correlation. When ``None`` the service builds a
                placeholder ``SecurityId(market=Market.INDEX,
                symbol=sector_code)`` so the router can record a
                canonical id without inventing one itself.

        Returns:
            A :class:`DataResult` whose ``data`` is a
            :class:`SectorSnapshot` (success) or ``None`` (empty).

        Raises:
            ProviderUnavailableError: When no router is wired
                (``router is None``). The service refuses to dispatch
                without an explicit router to keep the P3-A path
                opt-in.
        """
        if self._router is None:
            raise ProviderUnavailableError(
                "SectorService has no router wired; pass a DataRouter "
                "via the `router` constructor kwarg to enable "
                "get_sector_snapshot()."
            )
        domain = self.DOMAIN
        operation = self.OPERATION_SNAPSHOT
        # Use the caller's SecurityId when provided; otherwise build
        # a placeholder. Sectors are CN-specific (申万 / 东方财富 are
        # A-share / CN markets) so the placeholder carries the CN
        # market — the router then matches it against AKShare-style
        # providers registered for ``Market.CN``.
        placeholder = security_id or SecurityId(
            market=Market.CN, symbol=sector_code
        )
        params: dict[str, Any] = {}
        if date is not None:
            params["date"] = date
        params["sector_code"] = sector_code

        try:
            result = self._router.query(
                domain=domain,
                operation=operation,
                security_id=placeholder,
                params=params,
            )
        except Exception as exc:  # noqa: BLE001 — service contract: never re-raise
            # The router's ``_attempt_provider_fetch`` only catches
            # ``ProviderError`` / ``ProviderUnavailableError`` /
            # ``UnsupportedCapabilityError`` from the provider's
            # ``fetch`` path. Any other exception (e.g. a stub raising
            # a bare ``RuntimeError``) propagates out of ``query`` and
            # would normally surface as a 500. The service-level
            # contract (this method's docstring) is to return
            # ``DataResult(provider="error")`` instead, preserving the
            # original provider name in ``source_trace`` so callers can
            # still attribute the failure. ``DataResult.error`` rebuilds
            # the object with ``provider == "error"``,
            # ``freshness == "empty"`` and ``data is None``, satisfying
            # the T3-B ``is_empty`` contract.
            return DataResult.error(
                security_id=placeholder,
                domain=domain,
                operation=operation,
                provider=self._provider_label_for(exc),
                error=exc,
                source_trace=self._trace_for_exception(exc, capability=self.capability_snapshot),
            )
        # Map the raw payload to a ``SectorSnapshot`` (or ``None``)
        # so the contract is stable for callers — the router's
        # ``DataResult.data`` is whatever the provider yielded (a
        # ``dict``, a single-element list, ``[]`` for empty, etc.)
        # and we normalise it here.
        if result.is_empty():
            # Empty result — surface a ``data=None`` payload
            # regardless of what the router set, so consumers see
            # a consistent shape.
            result.data = None
        elif result.data is not None:
            coerced = self._coerce_snapshot(result.data)
            result.data = coerced
        return result

    # ------------------------------------------------------------------
    # P3-A: get_sector_ranking
    # ------------------------------------------------------------------

    def get_sector_ranking(
        self,
        date: str | None = None,
        sector_type: str | None = None,
        limit: int = 20,
        *,
        security_id: SecurityId | None = None,
    ) -> DataResult:
        """Return a sorted ``list[SectorSnapshot]`` ranking.

        The router walks the internal-first path (Step 1 / 2 / 3
        skipped — ``sector.ranking`` is in ``_TA_CN_NOT_COVERED`` per
        SPEC §5.5) and the external-fallback chain at Step 4. The
        returned list is sorted by ``pct_chg`` desc; ties are broken
        by ``sector_code`` asc; ``None pct_chg`` records are pushed
        to the end of the result (DESIGN §17.3.3). Invalid
        ``sector_type`` values are passed through to the provider
        verbatim — the provider decides whether to accept or reject
        them (DESIGN §17.3.2 four-dim boundary table). Non-positive
        ``limit`` values are silently rewritten to ``20``.

        Args:
            date: Optional trading-day selector (``"YYYY-MM-DD"``).
                ``None`` lets the provider pick the most recent
                available snapshot.
            sector_type: Optional sector-type filter (one of
                ``"industry"``, ``"concept"``, ``"region"``,
                ``"style"`` per SPEC §3.1). Invalid values are
                passed through untouched; the provider decides.
            limit: Maximum number of records to return. ``<= 0``
                values are silently rewritten to ``20`` (DESIGN
                §17.3.2). The service does not post-truncate — the
                cap is forwarded to the router so the provider
                controls the work.
            security_id: Optional :class:`SecurityId` for log
                correlation. When ``None`` the service builds a
                placeholder so the router can record a canonical id
                without inventing one.

        Returns:
            A :class:`DataResult` whose ``data`` is a
            ``list[SectorSnapshot]`` (success) or ``[]`` (empty).

        Raises:
            ProviderUnavailableError: When no router is wired.
        """
        if self._router is None:
            raise ProviderUnavailableError(
                "SectorService has no router wired; pass a DataRouter "
                "via the `router` constructor kwarg to enable "
                "get_sector_ranking()."
            )
        domain = self.DOMAIN
        operation = self.OPERATION_RANKING
        # Use a date-typed placeholder so the router can record a
        # canonical id. We don't have a single sector_code here — the
        # ranking query is multi-sector — but the underlying provider
        # is CN-specific so the placeholder carries Market.CN.
        composite_symbol = (
            f"sector_ranking:{date or 'latest'}:{sector_type or 'all'}"
        )
        placeholder = security_id or SecurityId(
            market=Market.CN, symbol=composite_symbol
        )
        # DESIGN §17.3.2: ``limit <= 0`` → silently rewrite to 20.
        effective_limit = limit if limit > 0 else 20
        params: dict[str, Any] = {"limit": effective_limit}
        if date is not None:
            params["date"] = date
        if sector_type is not None:
            params["sector_type"] = sector_type

        try:
            result = self._router.query(
                domain=domain,
                operation=operation,
                security_id=placeholder,
                params=params,
            )
        except Exception as exc:  # noqa: BLE001 — mirrors snapshot contract
            return DataResult.error(
                security_id=placeholder,
                domain=domain,
                operation=operation,
                provider=self._provider_label_for(exc),
                error=exc,
                source_trace=self._trace_for_exception(
                    exc, capability=self.capability_ranking
                ),
            )
        if result.succeeded and result.data is not None:
            records = self._coerce_ranking(result.data)
            # Stable sort: ``sorted`` is stable in CPython, so the
            # tiebreaker order is deterministic. Re-emit a list so
            # downstream code receives the same type regardless of
            # whether the provider yielded a tuple / generator.
            ordered = sorted(records, key=_sector_ranking_key)
            result.data = ordered
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _candidate_provider_names(self, capability: str) -> list[str]:
        """Return candidate provider names for ``capability`` from the router.

        The roster comes from the router's public
        :attr:`registry` (``ProviderRegistry.list_providers()``) and
        filters by ``capability in provider.capabilities`` so the
        helper returns names in registry insertion order — the same
        order the router walks when no explicit external chain is
        configured (DESIGN-03-014 §4.1 / SPEC-03-008 §4.1). The
        lookup is duck-typed so fakes that lack ``list_providers``
        degrade to ``[]`` without raising — the trace then collapses
        to a capability-level entry, which still records the failure
        in :attr:`DataResult.warnings`.
        """
        registry = getattr(self._router, "registry", None)
        if registry is None:
            return []
        list_providers = getattr(registry, "list_providers", None)
        if not callable(list_providers):
            return []
        try:
            providers = list_providers() or []
        except Exception:  # noqa: BLE001 — defensive: never raise from a helper
            return []
        names: list[str] = []
        for entry in providers:
            caps = getattr(entry, "capabilities", None)
            if not isinstance(caps, (set, frozenset, list, tuple)):
                continue
            if capability not in caps:
                continue
            name = getattr(entry, "name", None)
            if isinstance(name, str):
                names.append(name)
        return names

    def _provider_label_for(self, exc: BaseException) -> str:
        """Return the ``provider`` label for :meth:`DataResult.error`.

        The label is informational only — :meth:`DataResult.error`
        rewrites the final ``provider`` field to ``"error"`` regardless
        of what we pass here. We use the first candidate provider
        name when one exists (so the resulting ``source_trace`` keeps
        the original provider attribution), and fall back to the
        fully-qualified capability string otherwise.
        """
        for capability in (self.capability_snapshot, self.capability_ranking):
            for name in self._candidate_provider_names(capability):
                return name
        return f"{self.DOMAIN}.unknown"

    def _trace_for_exception(
        self, exc: BaseException, *, capability: str
    ) -> list[str]:
        """Build a ``source_trace`` for an unwrapped router exception.

        Each registered provider that could have answered
        ``capability`` contributes one ``"<name>(error: <exc>)"``
        entry so callers can attribute the failure without scanning
        ``warnings``. When the registry is unreachable the trace
        collapses to a single capability-level entry —
        ``"<capability>(error: <exc>)"``.
        """
        candidate_names = self._candidate_provider_names(capability)
        msg = f"{type(exc).__name__}: {exc}"
        if candidate_names:
            return [f"{name}(error: {msg})" for name in candidate_names]
        return [f"{capability}(error: {msg})"]

    @staticmethod
    def _coerce_snapshot(payload: Any) -> SectorSnapshot | None:
        """Coerce a single provider record to a :class:`SectorSnapshot`.

        Accepts:

        * A :class:`SectorSnapshot` (pass-through).
        * A ``dict`` (mapped via ``SectorSnapshot.from_dict``).
        * A ``list`` / ``tuple`` — for ``sector.snapshot`` the
          contract is a single record, but providers may yield a
          single-element list. The first element is taken; an empty
          list / tuple collapses to ``None`` so ``is_empty`` surfaces
          the empty result.

        Returns ``None`` for unrecognised shapes — callers rely on
        ``is_empty`` to surface the failure to consumers.
        """
        if isinstance(payload, SectorSnapshot):
            return payload
        if isinstance(payload, dict):
            return SectorSnapshot.from_dict(payload)
        if isinstance(payload, (list, tuple)):
            if not payload:
                return None
            first = payload[0]
            if isinstance(first, SectorSnapshot):
                return first
            if isinstance(first, dict):
                return SectorSnapshot.from_dict(first)
        # Provider yielded an unexpected shape — let the empty
        # signal propagate rather than raising in the service.
        return None

    @staticmethod
    def _coerce_ranking(payload: Any) -> list[SectorSnapshot]:
        """Coerce a provider ranking payload to ``list[SectorSnapshot]``.

        Accepts a list / tuple of dicts or :class:`SectorSnapshot`
        instances. Empty / non-list payloads become ``[]`` so the
        caller can rely on ``list`` semantics at the ``result.data``
        boundary.
        """
        if payload is None:
            return []
        if not isinstance(payload, (list, tuple)):
            return []
        coerced: list[SectorSnapshot] = []
        for entry in payload:
            if isinstance(entry, SectorSnapshot):
                coerced.append(entry)
            elif isinstance(entry, dict):
                coerced.append(SectorSnapshot.from_dict(entry))
            # Skip unrecognised entries — empty list / dict
            # signals propagate through ``is_empty``.
        return coerced

    # ------------------------------------------------------------------
    # Phase 1A: TA-CN MongoDB read-only methods
    # ------------------------------------------------------------------

    def get_stock_sector(
        self,
        security_id: SecurityId,
        classify_system: str | None = "SW",
    ) -> DataResult:
        """返回 ``list[SectorClassification]``、空或错误结果。

        ``full_symbol`` 由 adapter 通过 ``SecurityId.to_full_symbol()``
        推导；非 CN 市场 ``full_symbol`` 可能为 ``None``，此情形直接返回
        空结果。
        """
        domain = self.DOMAIN
        operation = "stock_sector"
        full_symbol = security_id.to_full_symbol()
        if not full_symbol:
            return wrap_empty(security_id, domain, operation)
        try:
            docs = self._adapter.get_stock_sector_info(
                full_symbol,
                classify_system=classify_system,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        if not docs:
            return wrap_empty(security_id, domain, operation)
        try:
            records = [SectorClassification.from_ta_cn_doc(doc) for doc in docs]
        except SERVICE_ERRORS as exc:
            return wrap_error(security_id, domain, operation, exc)
        return wrap_success(records, security_id, domain, operation)

    def get_stocks_by_sector(
        self,
        sector_code: str,
        classify_system: str = "SW",
        security_id: SecurityId | None = None,
    ) -> DataResult:
        """返回某申万一级行业下的全部 ``SectorClassification`` 记录。

        调用方一般传入 ``security_id=None``；为保持与其它 service 相同
        的 ``SecurityId`` 入参契约，这里允许可选 ``security_id`` 用于
        日志关联，但底层查询只依赖 ``sector_code``。
        """
        domain = self.DOMAIN
        operation = "stocks_by_sector"
        # Use a placeholder SecurityId for non-security results.
        placeholder = security_id or SecurityId(market="INDEX", symbol=sector_code)
        try:
            docs = self._adapter.get_stocks_by_sector(
                sector_code,
                classify_system=classify_system,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        if not docs:
            return wrap_empty(placeholder, domain, operation)
        try:
            records = [SectorClassification.from_ta_cn_doc(doc) for doc in docs]
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        return wrap_success(records, placeholder, domain, operation)

    def get_sector_index_bars(
        self,
        sector_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> DataResult:
        """返回某申万行业指数的日线 ``list[IndexDailyBar]``、空或错误结果。"""
        domain = self.DOMAIN
        operation = "sector_index_bars"
        placeholder = SecurityId(market="INDEX", symbol=sector_code)
        try:
            docs = self._adapter.get_index_daily_bars(
                sector_code=sector_code,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        if not docs:
            return wrap_empty(placeholder, domain, operation)
        try:
            bars = [IndexDailyBar.from_ta_cn_doc(doc) for doc in docs]
        except SERVICE_ERRORS as exc:
            return wrap_error(placeholder, domain, operation, exc)
        return wrap_success(bars, placeholder, domain, operation)


__all__ = ["SectorService"]
