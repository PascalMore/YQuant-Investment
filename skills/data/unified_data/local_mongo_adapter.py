"""Local Mongo adapter for unified_data (Phase 1B-B).

:class:`LocalMongoAdapter` is the persistence-plane component that owns
the Unified Data materialised collections (``03_data_ud_*``). It is
the **Step 2** slot in the ``DataRouter`` internal-first path
(SPEC-03-009 §4.2 / DESIGN-03-009 §3.4.1).

Scope and ownership
-------------------

* **Read-write** on UD's own ``03_data_ud_*`` collections (allow-list
  enforced by ``collection_prefix`` being locked to ``"03_data_ud_"``).
* **Strictly read-only** on TA-CN prefixless collections — enforced by
  the fact that this class never touches a collection whose name does
  not start with the configured prefix.
* All get/put/invalidate operations are **catch-and-log**: failures
  are recorded via :func:`logger.warning` and ``None`` / ``0`` are
  returned. The adapter **never** propagates exceptions to the Router
  (SPEC-03-009 §0.2 / DR-205).

Production vs. testing
----------------------

The adapter accepts an already-constructed Mongo database handle
(``pymongo.database.Database`` in production,
``mongomock.database.Database`` in tests). It does **not** receive a
``mongo_uri`` connection string — that responsibility belongs to the
caller (typically the ``UnifiedDataClient`` factory).

Production collection / index DDL is **out of scope** for Phase 1B-B
(DESIGN-03-009 §6.2). The adapter reads/writes whatever collections
already exist; it does not call ``create_collection`` /
``create_index``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Mapping

from .freshness import FreshnessPolicy
from .models import DataResult, SecurityId

logger = logging.getLogger(__name__)


# Locked at module load — the adapter never writes outside this prefix,
# which keeps the allow-list contract structurally enforced.
_DEFAULT_COLLECTION_PREFIX = "03_data_ud_"

_SCHEMA_VERSION = "1.0"


def _serialize_payload(payload: Any) -> Any:
    """Coerce ``payload`` into a JSON-friendly structure for storage.

    * ``pandas.DataFrame`` → ``DataFrame.to_dict(orient="records")``
      (DESIGN-03-009 §3.5.1).
    * Scalars / ``list[dict]`` / ``dict`` pass through unchanged.
    * Anything else is stored verbatim. The adapter never raises on
      exotic payloads — JSON-friendliness is best-effort.
    """
    to_dict = getattr(payload, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict(orient="records")
        except (TypeError, ValueError):
            # Fall through — store the raw payload rather than raising.
            return payload
    return payload


def _compute_params_hash(params: Mapping[str, Any] | None) -> str:
    """Return the canonical ``params_hash`` (md5-prefixed, 32 chars)."""
    params_str = json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.md5(params_str.encode("utf-8")).hexdigest()[:32]


def _compute_materialized_key(
    security_id: SecurityId,
    domain: str,
    operation: str,
    params: Mapping[str, Any] | None,
) -> str:
    """Return the canonical ``materialized_key`` (sha256-prefixed, 64 chars)."""
    params_str = json.dumps(params or {}, sort_keys=True, default=str)
    raw = f"{security_id}|{domain}|{operation}|{params_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


class LocalMongoAdapter:
    """Materialised-data read/write adapter (Phase 1B-B).

    All operations are catch-and-log; this component never propagates
    an exception to its caller. See module docstring for the full
    ownership / production-rollout contract.
    """

    def __init__(
        self,
        mongo_db: Any,
        collection_prefix: str = _DEFAULT_COLLECTION_PREFIX,
        freshness: FreshnessPolicy | None = None,
    ) -> None:
        # The prefix is treated as a structural invariant — we accept
        # the argument for testability / future extension but normalise
        # it to the locked value. Any caller passing a non-default
        # prefix still gets the locked one. This keeps the allow-list
        # contract unforgeable from outside.
        self._db = mongo_db
        self._prefix = _DEFAULT_COLLECTION_PREFIX
        self._freshness = freshness if freshness is not None else FreshnessPolicy()
        # Touch ``collection_prefix`` so the kw-arg remains in the
        # public signature without affecting runtime behaviour. This
        # silences linters that flag unused kwargs while keeping the
        # SPEC-03-009 §4.2 signature aligned.
        _ = collection_prefix

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None = None,
    ) -> DataResult | None:
        """Return a non-expired materialised :class:`DataResult`, or ``None``.

        Behaviour matrix (SPEC-03-009 §3.2 / LM-102..LM-104):

        * Hit + ``expires_at > now`` → return ``DataResult`` with
          ``provider="ud_materialized"``, ``freshness="cached"``.
        * Hit + ``expires_at <= now`` → return ``None`` (expired
          materialisation is **not** returned, but kept in the
          collection for rebuild).
        * Miss → return ``None``.
        * Any exception → log + return ``None``.
        """
        try:
            collection = self._db[self._prefix + operation]
            doc = collection.find_one(
                {"materialized_key": _compute_materialized_key(
                    security_id, domain, operation, params
                )}
            )
        except Exception as exc:  # catch-and-log (LM-104)
            logger.warning("LocalMongoAdapter.get failed: %s", exc)
            return None

        if doc is None:
            return None

        expires_at = doc.get("expires_at")
        if expires_at is not None:
            now = datetime.utcnow()
            # mongomock stores naive datetimes the same way we write
            # them; if the value comes back tz-aware, strip for compare.
            if getattr(expires_at, "tzinfo", None) is not None:
                expires_at = expires_at.replace(tzinfo=None)
            if expires_at <= now:
                # Expired — do not return (DR-203). Kept in collection.
                return None

        return DataResult(
            data=doc.get("data"),
            security_id=security_id,
            domain=domain,
            operation=operation,
            provider="ud_materialized",
            fetched_at=doc.get("fetched_at") or doc.get("materialized_at") or datetime.utcnow(),
            data_date=doc.get("data_date"),
            freshness="cached",
            source_trace=list(doc.get("source_trace") or []),
            warnings=[],
        )

    def put(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None,
        result: DataResult,
    ) -> None:
        """Persist ``result`` into the ``03_data_ud_{operation}`` collection.

        Upsert mode: the ``materialized_key`` is unique per
        ``(security_id, domain, operation, params)`` tuple. Re-running
        ``put()`` with the same arguments replaces the previous
        document (LM-106).

        Failures are catch-and-log (LM-105 / MW-101). Never raises.
        """
        try:
            collection = self._db[self._prefix + operation]
            materialized_at = datetime.utcnow()
            ttl_seconds = self._freshness.get_ttl(domain)
            expires_at = materialized_at + timedelta(seconds=ttl_seconds)
            document = {
                "materialized_key": _compute_materialized_key(
                    security_id, domain, operation, params
                ),
                "security_id": str(security_id),
                "domain": domain,
                "operation": operation,
                "params_hash": _compute_params_hash(params),
                "data": _serialize_payload(result.data),
                "provider": result.provider,
                "fetched_at": result.fetched_at,
                "data_date": result.data_date,
                "freshness_at_write": result.freshness,
                "source_trace": list(result.source_trace),
                "schema_version": _SCHEMA_VERSION,
                "materialized_at": materialized_at,
                "expires_at": expires_at,
            }
            collection.update_one(
                {"materialized_key": document["materialized_key"]},
                {"$set": document},
                upsert=True,
            )
        except Exception as exc:
            logger.warning("LocalMongoAdapter.put failed: %s", exc)

    def invalidate(
        self,
        security_id: SecurityId | None = None,
        domain: str | None = None,
    ) -> int:
        """Bulk-invalidate materialised documents.

        Combinations (LM-107..LM-110):

        * ``security_id=None`` + ``domain=None`` → delete every
          document across **all** ``03_data_ud_*`` collections.
        * ``security_id`` set → restrict to that security.
        * ``domain`` set → restrict to that domain. The domain filter
          is applied to the document's stored ``domain`` field; the
          ``operation``-keyed collection layout means we still need to
          scan every collection.

        Returns the number of documents deleted. Exceptions are
        catch-and-log (LM-110) and surface as ``0``.
        """
        query: dict[str, Any] = {}
        if security_id is not None:
            query["security_id"] = str(security_id)
        if domain is not None:
            query["domain"] = domain

        total_deleted = 0
        try:
            collection_names = self._db.list_collection_names()
            for coll_name in collection_names:
                if not coll_name.startswith(self._prefix):
                    continue
                # The prefix is structurally ours; the trailing suffix
                # is the operation name. The domain filter (when set)
                # still has to match document content.
                collection = self._db[coll_name]
                if query:
                    result = collection.delete_many(query)
                else:
                    result = collection.delete_many({})
                total_deleted += result.deleted_count
        except Exception as exc:
            logger.warning("LocalMongoAdapter.invalidate failed: %s", exc)
            return 0

        return total_deleted


__all__ = ["LocalMongoAdapter"]