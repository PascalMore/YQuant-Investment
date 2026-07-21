"""P3PersistenceWriter — Phase 3 business-collection persistence (offline T3-A scaffold).

Phase 3 of the Unified Data Layer expands persistence to three business
collections (DESIGN-03-014 §0.4)::

    03_data_ud_market_sector_snapshot
    03_data_ud_stock_capital_flow
    03_data_ud_market_sentiment_snapshot

Each collection is addressed by **business unique keys**
(e.g. ``{market, sector_code, snapshot_date}``), NOT by the single
``materialized_key`` model :class:`LocalMongoAdapter` uses. This module
provides the minimal read/write/delete surface the Router / future
refresh paths need while remaining strictly offline (mongomock only).

Scope guardrails (T3-A, see kanban task body):

* Real MongoDB connections are forbidden — the constructor accepts
  either a :mod:`mongomock` database or a :class:`FakeDatabase` shim.
* No real Provider/API calls.
* No AuditLogger writes.
* No QualitySummary writes.

P0.1 Patch (T3-A P0.1, decision B.b — AuditLogger dry-run fail-open):

* :class:`P3PersistenceWriter` accepts an optional ``audit_logger``
  dependency whose ``.attempt(**kwargs)`` is invoked from
  :meth:`upsert` (post-success + exception path).
* Default behaviour is no-op via the module-local
  :class:`_NoopAuditLogger`; no file / MongoDB write happens unless
  a real logger is explicitly injected.
* Audit calls are wrapped in ``try/except`` so a logger-side failure
  **never** blocks the main refresh path (fail-open). Failures log
  to stderr but the upsert outcome is returned as if no logger was
  configured.
* Audit kwargs are filtered through :data:`_AUDIT_ATTEMPT_ALLOWLIST`
  so callers cannot accidentally pass raw query payloads, secrets,
  or non-deserialisable objects into the audit document.

Interface freeze (V0.5 §0.4):

* :class:`UpsertOutcome` — return value of :meth:`P3PersistenceWriter.upsert`.
* :meth:`P3PersistenceWriter.get` — list[dict] read by filter.
* :meth:`P3PersistenceWriter.upsert` — by unique_key upsert.
* :meth:`P3PersistenceWriter.delete` — filter delete (rollback/stop use).
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

logger = logging.getLogger(__name__)


# Audit ``attempt()`` payload allow-list (T3-A P0.1 / decision B.b).
# Only the six fields below may flow into the audit call. This keeps
# the audit document schema fixed and prevents accidental leakage of
# query payloads / secrets / large objects into the audit sink.
_AUDIT_ATTEMPT_ALLOWLIST: frozenset[str] = frozenset({
    "security_id",
    "domain",
    "operation",
    "outcome",
    "latency_ms",
    "row_count",
})


def _filter_audit_kwargs(**kwargs: Any) -> dict[str, Any]:
    """Return only the allow-listed audit kwargs.

    Non-allow-listed keys are silently dropped. ``None`` values are
    kept (the caller may pass them explicitly to signal "absent").
    Non-string keys are coerced via ``str()`` for forward-compat but
    only recognised string names survive the filter.
    """
    safe: dict[str, Any] = {}
    for key, value in kwargs.items():
        if not isinstance(key, str):
            continue
        if key not in _AUDIT_ATTEMPT_ALLOWLIST:
            logger.debug(
                "P3PersistenceWriter: dropping non-allow-listed audit kwarg %r",
                key,
            )
            continue
        safe[key] = value
    return safe


class _NoopAuditLogger:
    """Default no-op AuditLogger for :class:`P3PersistenceWriter`.

    Implements the contract that ``P3PersistenceWriter`` relies on —
    ``.attempt(**kwargs)`` and ``.record(**kwargs)`` — without
    performing any I/O. Used when no logger is injected so the
    refresh path stays side-effect-free by default (Phase 3-A
    offline / dry-run semantics, decision B.b).

    Real AuditLogger implementations may extend this protocol with
    additional fields, but only the allow-listed subset forwarded by
    :func:`_filter_audit_kwargs` will ever reach the audit sink.
    """

    def attempt(self, **_kwargs: Any) -> None:
        """No-op. Receives allow-listed kwargs (see module docstring)."""
        return None

    def record(self, **_kwargs: Any) -> None:
        """No-op. Reserved for future event-style audit hooks."""
        return None


def _safe_audit_call(
    audit_logger: Any,
    method_name: str,
    **kwargs: Any,
) -> None:
    """Invoke ``audit_logger.method_name(**kwargs)`` with fail-open guard.

    Any exception raised by the audit call is caught and logged to
    stderr. The main refresh path is never affected by audit logger
    failures (DESIGN-03-014 §5.4 P0.1 fail-open contract).

    Args:
        audit_logger: The audit logger instance. ``None`` is a no-op.
        method_name: Name of the method to invoke (``"attempt"`` or
            ``"record"``).
        **kwargs: Audit fields. Filtered through the allow-list.
    """
    if audit_logger is None:
        return
    safe_kwargs = _filter_audit_kwargs(**kwargs)
    method = getattr(audit_logger, method_name, None)
    if method is None or not callable(method):
        # Logger doesn't implement the contract — fail-open: log
        # once to stderr so operators can see the mismatch but do
        # not block the refresh.
        print(
            f"P3PersistenceWriter: audit_logger missing {method_name!r}; "
            f"kwargs={sorted(safe_kwargs)!r}",
            file=sys.stderr,
        )
        return
    try:
        method(**safe_kwargs)
    except Exception as exc:  # noqa: BLE001 — fail-open by design
        print(
            f"P3PersistenceWriter: audit_logger.{method_name}() raised "
            f"{type(exc).__name__}: {exc}; kwargs={sorted(safe_kwargs)!r}",
            file=sys.stderr,
        )
        return

# Capability → collection / business-key mapping (V0.5 §0.4, frozen).
P3_COLLECTION_BY_CAPABILITY: dict[str, str] = {
    "sector.snapshot": "03_data_ud_market_sector_snapshot",
    "sector.ranking": "03_data_ud_market_sector_snapshot",
    "flow.capital_flow_daily": "03_data_ud_stock_capital_flow",
    "flow.northbound_daily": "03_data_ud_stock_capital_flow",
    "sentiment.market_snapshot": "03_data_ud_market_sentiment_snapshot",
    "sentiment.limit_up_pool": "03_data_ud_market_sentiment_snapshot",
}

P3_UNIQUE_KEYS_BY_CAPABILITY: dict[str, frozenset[str]] = {
    "sector.snapshot": frozenset({"market", "sector_code", "snapshot_date"}),
    "sector.ranking": frozenset({"market", "sector_code", "snapshot_date"}),
    "flow.capital_flow_daily": frozenset({"market", "symbol", "trade_date"}),
    "flow.northbound_daily": frozenset({"market", "symbol", "trade_date"}),
    "sentiment.market_snapshot": frozenset({"market", "snapshot_date", "snapshot_time"}),
    "sentiment.limit_up_pool": frozenset({"market", "snapshot_date", "snapshot_time"}),
}


@dataclass
class UpsertOutcome:
    """Return value of :meth:`P3PersistenceWriter.upsert`.

    Fields (V0.5 §0.4 — frozen):

    * ``persisted`` — count of records successfully upserted.
    * ``failed`` — count of records that failed.
    * ``failed_keys`` — list of business-key dicts identifying failed
      records (caller may inspect / log; no rollback semantics — see
      DESIGN-03-014 §5.4.3 note 1).
    * ``errors`` — list of error message strings, parallel-friendly
      with ``failed_keys`` (1:1).
    """

    persisted: int = 0
    failed: int = 0
    failed_keys: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class P3PersistenceWriter:
    """Business-collection reader/writer for Phase 3.

    Construct with a *fake* ``mongo_db``. The shape expected is the
    pymongo ``Database`` protocol (subscript ``db[collection]`` returns
    a collection that supports ``find_one`` / ``find`` /
    ``update_one`` / ``delete_many``) — :mod:`mongomock` and
    :class:`skills.data.unified_data.tests.fixtures.FakeDatabase` both
    satisfy this.

    Args:
        mongo_db: A mongomock ``MongoClient().get_database(...)`` (or
            a shim with the same ``db[name]`` protocol). Real
            ``pymongo.MongoClient`` is forbidden in T3-A — see the
            ``_assert_fake_db`` guard.
        audit_logger: Optional audit logger (T3-A P0.1, decision B.b).
            Must expose ``.attempt(**kwargs)`` (and optionally
            ``.record(**kwargs)``). ``None`` (default) installs the
            module-local :class:`_NoopAuditLogger` so the refresh
            path stays side-effect-free until a real logger is wired
            in. Audit calls are fail-open: a logger-side exception is
            logged to stderr but never propagates back into
            :meth:`upsert`'s caller.
    """

    def __init__(
        self,
        mongo_db: Any,
        audit_logger: Any | None = None,
    ) -> None:
        self._db = mongo_db
        self._assert_fake_db(mongo_db)
        # P0.1 B.b: default to no-op audit logger so the contract is
        # always available; failure of any injected logger is
        # contained by ``_safe_audit_call`` and never propagates.
        self._audit_logger: Any = (
            audit_logger if audit_logger is not None else _NoopAuditLogger()
        )

    @property
    def audit_logger(self) -> Any:
        """Return the audit logger instance (never ``None``).

        Exposed so router-side exception handlers (T3-A P0.1
        contract) can emit a single ``attempt(outcome="exception")``
        when the writer call raises, without needing a separate
        reference. The property always returns a real object —
        either the caller-supplied logger or :class:`_NoopAuditLogger`.
        """
        return self._audit_logger

    # ------------------------------------------------------------------
    # Internal guard — refuse a real pymongo connection
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_fake_db(mongo_db: Any) -> None:
        """Reject real pymongo Database objects.

        mongomock (and our :class:`FakeDatabase`) report class names
        containing ``mongomock`` or ``FakeDatabase``. A real
        ``pymongo.database.Database`` does not — guarding on class
        string keeps the contract honest without an import-time
        dependency on ``pymongo``.
        """
        if mongo_db is None:
            raise TypeError("P3PersistenceWriter requires a mongo_db (mongomock / FakeDatabase).")
        cls_name = type(mongo_db).__name__
        module = type(mongo_db).__module__ or ""
        if "pymongo" in module and "mongomock" not in module:
            raise TypeError(
                "P3PersistenceWriter refuses real pymongo connections "
                "(T3-A offline guard). Pass a mongomock or FakeDatabase."
            )
        if cls_name in {"Database"} and "mongomock" not in module:
            # belt-and-braces: pymongo.database.Database + module 'pymongo.*'
            raise TypeError(
                "P3PersistenceWriter refuses real pymongo connections "
                "(T3-A offline guard)."
            )

    # ------------------------------------------------------------------
    # Collection resolution
    # ------------------------------------------------------------------

    def collection_for(self, capability: str) -> str:
        """Return the canonical collection name for ``capability``.

        Unknown capability raises :class:`ValueError` — callers must
        pass a Phase 3 capability. (V0.5 §0.4 only enumerates 6.)
        """
        try:
            return P3_COLLECTION_BY_CAPABILITY[capability]
        except KeyError as exc:
            raise ValueError(
                f"capability {capability!r} is not a Phase 3 capability"
            ) from exc

    def unique_key_for(self, capability: str) -> frozenset[str]:
        """Return the business unique-key set for ``capability``."""
        try:
            return P3_UNIQUE_KEYS_BY_CAPABILITY[capability]
        except KeyError as exc:
            raise ValueError(
                f"capability {capability!r} is not a Phase 3 capability"
            ) from exc

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def get(
        self,
        collection: str,
        filter: Mapping[str, Any] | None = None,
    ) -> list[dict]:
        """Read records from ``collection`` matching ``filter``.

        Returns an empty list when no record matches. The caller is
        responsible for deserialising each ``dict`` into a domain
        object (e.g. :class:`SectorSnapshot`).
        """
        coll = self._db[collection]
        cursor = coll.find(dict(filter or {}))
        return [dict(doc) for doc in cursor]

    # ------------------------------------------------------------------
    # Write path (refresh only)
    # ------------------------------------------------------------------

    def upsert(
        self,
        collection: str,
        records: Sequence[Mapping[str, Any]],
        unique_key: Iterable[str] | set[str] | frozenset[str],
    ) -> UpsertOutcome:
        """Upsert ``records`` into ``collection`` keyed by ``unique_key``.

        Per-record failure is captured in :class:`UpsertOutcome` — the
        whole call never raises. Behaviour (DESIGN-03-014 §5.4.3):

        * For each record: build filter from ``unique_key`` fields; call
          ``update_one(filter, {"$set": record}, upsert=True)``.
        * On success: increment ``persisted``.
        * On failure: append ``{k: v for k, v in unique_key subset of
          record}`` to ``failed_keys`` and the exception message to
          ``errors``, increment ``failed``.
        * Empty ``records`` → :class:`UpsertOutcome` with all zeros.

        ``unique_key`` is the set of fields that identify a record
        (e.g. ``{"market", "sector_code", "snapshot_date"}``). The
        caller supplies it so the same writer serves all three Phase 3
        collections.

        Audit hook (T3-A P0.1, decision B.b):

        * After the per-record loop completes, ``self._audit_logger``
          receives ``.attempt(...)`` with allow-listed fields
          (``operation``, ``domain``, ``outcome``, ``latency_ms``,
          ``row_count``). ``outcome`` is ``"ok"`` when no per-record
          failure happened, otherwise ``"partial_failure"``.
        * If the **whole call** raises (e.g. ``update_one`` blew up
          unexpectedly outside the per-record guard), the audit call
          fires with ``outcome="exception"`` **before** the original
          exception is re-raised. The audit call itself is wrapped
          in :func:`_safe_audit_call` (fail-open) so a logger
          malfunction cannot mask the upsert failure.
        * Empty ``records`` / empty ``unique_key`` are early returns
          and **do not** fire an audit call (they signal caller-side
          mis-configuration, not refresh activity).
        """
        outcome = UpsertOutcome()
        records_list = list(records)
        if not records_list:
            # Caller-side no-op — no audit emit (nothing to record).
            return outcome

        unique_key_set = set(unique_key)
        if not unique_key_set:
            # Caller-side mis-configuration — also no audit emit.
            outcome.failed = len(records_list)
            outcome.errors.append("unique_key must be a non-empty set of field names")
            return outcome

        started = time.perf_counter()
        try:
            coll = self._db[collection]
            for record in records_list:
                try:
                    if not isinstance(record, Mapping):
                        raise TypeError(
                            f"record must be a Mapping, got {type(record).__name__}"
                        )
                    # Build the business-key filter from the supplied key set.
                    key_filter: dict[str, Any] = {}
                    missing: list[str] = []
                    for key in unique_key_set:
                        if key in record:
                            key_filter[key] = record[key]
                        else:
                            missing.append(key)
                    if missing:
                        raise ValueError(
                            f"record missing unique-key field(s): {sorted(missing)}"
                        )
                    coll.update_one(key_filter, {"$set": dict(record)}, upsert=True)
                except Exception as exc:  # noqa: BLE001 — capture into outcome
                    outcome.failed += 1
                    outcome.failed_keys.append(
                        {k: record.get(k) for k in unique_key_set if k in record}
                    )
                    outcome.errors.append(f"{type(exc).__name__}: {exc}")
                    continue
                outcome.persisted += 1
        except Exception as exc:
            # Catastrophic failure — the whole call could not complete.
            # Audit with ``outcome="exception"`` then re-raise so the
            # refresh path sees the original error. The audit call is
            # fail-open: a logger crash here cannot mask the real
            # exception from the caller.
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            _safe_audit_call(
                self._audit_logger,
                "attempt",
                operation="upsert",
                domain=collection,
                outcome="exception",
                latency_ms=elapsed_ms,
                row_count=outcome.persisted + outcome.failed,
            )
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        outcome_label = "ok" if outcome.failed == 0 else "partial_failure"
        _safe_audit_call(
            self._audit_logger,
            "attempt",
            operation="upsert",
            domain=collection,
            outcome=outcome_label,
            latency_ms=elapsed_ms,
            row_count=outcome.persisted + outcome.failed,
        )
        return outcome

    # ------------------------------------------------------------------
    # Stop / rollback helper
    # ------------------------------------------------------------------

    def delete(
        self,
        collection: str,
        filter: Mapping[str, Any] | None = None,
    ) -> int:
        """Delete records from ``collection`` matching ``filter``.

        Returns the count of deleted records (capped at what the fake
        backend exposes — :mod:`mongomock` returns ``0``; the
        :class:`FakeDatabase` shim returns ``len(pre) - len(post)``).
        An empty / ``None`` filter is rejected to avoid accidental
        full-collection wipes.
        """
        if not filter:
            raise ValueError("delete requires a non-empty filter to prevent full wipes")
        coll = self._db[collection]
        try:
            before = len(coll.find(dict(filter))) if hasattr(coll, "find") else 0
        except Exception:
            before = 0
        result = coll.delete_many(dict(filter))
        # mongomock returns ``DeleteResult`` with ``deleted_count``;
        # the in-test ``FakeDatabase`` shim returns an int directly.
        if hasattr(result, "deleted_count"):
            return int(result.deleted_count)
        if isinstance(result, int):
            # The shim returns ``max(0, before - len(post))`` already,
            # so just trust the int.
            return int(result)
        return before


__all__ = [
    "UpsertOutcome",
    "P3PersistenceWriter",
    "P3_COLLECTION_BY_CAPABILITY",
    "P3_UNIQUE_KEYS_BY_CAPABILITY",
]