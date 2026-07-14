"""Cache manager for unified_data (Phase 1B-B).

:class:`CacheManager` is the short-TTL Query Cache layer
(``03_data_ud_cache_*``). It is the **Step 3** slot in the
``DataRouter`` internal-first path (SPEC-03-009 §4.3 / DESIGN-03-009
§3.4.2).

Scope and ownership
-------------------

* **Read-write** on UD's own ``03_data_ud_cache_*`` collections
  (allow-list enforced by ``collection_prefix`` being locked to
  ``"03_data_ud_cache_"``).
* **Never** touches any other collection. The locked prefix keeps the
  allow-list contract unforgeable from outside the module.
* All get/put/invalidate operations are **catch-and-log** — same
  contract as :class:`LocalMongoAdapter` (CM-104 / CM-108). Cache
  issues never block a query.

Deterministic cache keys
------------------------

The cache key is the sha256-prefixed hash of
``"{security_id}|{domain}|{operation}|{json.dumps(params,
sort_keys=True)}"``. ``sort_keys=True`` makes the hash independent of
input dict ordering (UT-CM-010).

Production vs. testing
----------------------

Like :class:`LocalMongoAdapter`, the manager accepts a ready Mongo
database handle (``pymongo`` in production, ``mongomock`` in tests).
It does **not** receive a ``mongo_uri`` connection string — that
responsibility belongs to the caller.

Phase 1B-B does **not** call ``create_collection`` / ``create_index``
(DESIGN-03-009 §6.2). Production rollout is gated on Pascal
approval.
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


# Locked at module load — the manager never writes outside this prefix.
_DEFAULT_COLLECTION_PREFIX = "03_data_ud_cache_"


def _compute_params_hash(params: Mapping[str, Any] | None) -> str:
    """md5-prefixed (32 chars) hash of the serialised params dict."""
    params_str = json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.md5(params_str.encode("utf-8")).hexdigest()[:32]


def _serialize_payload(payload: Any) -> Any:
    """Coerce ``payload`` into a JSON-friendly structure for storage.

    Mirrors :func:`LocalMongoAdapter._serialize_payload` — same
    DataFrame → ``to_dict(orient="records")`` policy (DESIGN-03-009
    §3.5.2). Lives independently here because the cache module must
    not depend on the materialisation module (separation of concerns).
    """
    to_dict = getattr(payload, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict(orient="records")
        except (TypeError, ValueError):
            return payload
    return payload


class CacheManager:
    """Short-TTL Query Cache (Phase 1B-B).

    All operations are catch-and-log; cache issues never block the
    Router. See module docstring for the full contract.
    """

    def __init__(
        self,
        mongo_db: Any,
        collection_prefix: str = _DEFAULT_COLLECTION_PREFIX,
        freshness: FreshnessPolicy | None = None,
    ) -> None:
        self._db = mongo_db
        # Structural invariant — see LocalMongoAdapter for rationale.
        self._prefix = _DEFAULT_COLLECTION_PREFIX
        self._freshness = freshness if freshness is not None else FreshnessPolicy()
        _ = collection_prefix  # keep kw-arg in public signature

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def _make_cache_key(
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None = None,
    ) -> str:
        """Return the canonical cache key (sha256-prefixed, 32 chars).

        Deterministic for identical ``(security_id, domain, operation,
        params)`` tuples; ``params`` is JSON-serialised with
        ``sort_keys=True`` so dict ordering does not affect the key.
        """
        params_str = json.dumps(params or {}, sort_keys=True, default=str)
        raw = f"{security_id}|{domain}|{operation}|{params_str}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def get(
        self,
        security_id: SecurityId,
        domain: str,
        operation: str,
        params: Mapping[str, Any] | None = None,
    ) -> DataResult | None:
        """Return a non-expired cached :class:`DataResult`, or ``None``.

        Behaviour matrix (CM-102..CM-104):

        * Hit + ``expires_at > now`` → return ``DataResult`` with
          ``freshness="cached"`` and the **original** ``provider``
          (Query Cache does not re-stamp the source).
        * Hit + ``expires_at <= now`` → return ``None``.
        * Miss → return ``None``.
        * Any exception → log + return ``None``.
        """
        try:
            collection = self._db[self._prefix + operation]
            cache_key = self._make_cache_key(
                security_id, domain, operation, params
            )
            doc = collection.find_one({"cache_key": cache_key})
        except Exception as exc:
            logger.warning("CacheManager.get failed: %s", exc)
            return None

        if doc is None:
            return None

        expires_at = doc.get("expires_at")
        if expires_at is not None:
            now = datetime.utcnow()
            if getattr(expires_at, "tzinfo", None) is not None:
                expires_at = expires_at.replace(tzinfo=None)
            if expires_at <= now:
                return None

        return DataResult(
            data=doc.get("data"),
            security_id=security_id,
            domain=domain,
            operation=operation,
            provider=doc.get("provider") or "cache",
            fetched_at=doc.get("fetched_at") or doc.get("cached_at") or datetime.utcnow(),
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
        """Persist ``result`` into the ``03_data_ud_cache_{operation}`` collection.

        Upsert mode: the ``cache_key`` is unique per ``(security_id,
        domain, operation, params)`` tuple. Re-running ``put()`` with
        the same arguments replaces the previous document (CM-106).

        Failures are catch-and-log (CM-105 / MW-101). Never raises.
        """
        try:
            collection = self._db[self._prefix + operation]
            cached_at = datetime.utcnow()
            ttl_seconds = self._freshness.get_ttl(domain)
            expires_at = cached_at + timedelta(seconds=ttl_seconds)
            document = {
                "cache_key": self._make_cache_key(
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
                "source_trace": list(result.source_trace),
                "cached_at": cached_at,
                "expires_at": expires_at,
            }
            collection.update_one(
                {"cache_key": document["cache_key"]},
                {"$set": document},
                upsert=True,
            )
        except Exception as exc:
            logger.warning("CacheManager.put failed: %s", exc)

    def invalidate(
        self,
        security_id: SecurityId | None = None,
        domain: str | None = None,
    ) -> int:
        """Bulk-invalidate cached documents (CM-107/108).

        Combinations:

        * Both ``None`` → delete every document across **all**
          ``03_data_ud_cache_*`` collections.
        * ``security_id`` set → restrict to that security.
        * ``domain`` set → restrict to that domain (matched against the
          stored ``domain`` field; the ``operation``-keyed collection
          layout means we still scan every cache collection).

        Returns the number of documents deleted. Exceptions are
        catch-and-log and surface as ``0``.
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
                collection = self._db[coll_name]
                if query:
                    result = collection.delete_many(query)
                else:
                    result = collection.delete_many({})
                total_deleted += result.deleted_count
        except Exception as exc:
            logger.warning("CacheManager.invalidate failed: %s", exc)
            return 0

        return total_deleted


__all__ = ["CacheManager"]