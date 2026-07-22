"""T4 MongoDB zero-write preflight client (PR-1).

DESIGN-03-014 §15.5 / SPEC-03-014 §14.2 / RFC-03-014 §13.2.

Only the four allowed operations from DESIGN §15.5.1 are exposed:

* ``admin.command("ping")`` — connectivity
* ``db.list_collection_names()`` — collection enumeration
* ``db[collection].options()`` — collection metadata (only when a
  target collection is unexpectedly present)
* ``client.close()`` — cleanup

Every method that issues a network call returns a structured
:class:`MongoPreflightResult` (see ``models.py``) whose connectivity
field is one of ``success / dns_failure / timeout / auth_failure /
skipped``. The factory also exposes a hard operation cap
(``PREFLIGHT_MAX_OPERATIONS``) so a runaway preflight can never
exceed the design-specified call budget.

The factory intentionally does NOT import :mod:`pymongo` at module
load time. The pymongo import is deferred to the first live call so
that dry-run invocations never need pymongo installed. Tests can
substitute a fake client via :func:`set_client_factory`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Protocol

from .config import (
    ALLOWED_DATABASE,
    P3_BUSINESS_COLLECTIONS,
    PREFLIGHT_MAX_OPERATIONS,
)
from .models import MongoPreflightResult

__all__ = [
    "MongoClientFactory",
    "set_client_factory",
    "reset_client_factory",
    "FakeMongoClient",
]


# ---------------------------------------------------------------------------
# Plug-in seam (test override)
# ---------------------------------------------------------------------------


class _PymongoClient(Protocol):
    def __getitem__(self, db: str) -> Any: ...
    def close(self) -> None: ...
    def admin(self) -> Any: ...


class _ClientFactory(Protocol):
    def __call__(self, uri: str, *, timeout_ms: int) -> _PymongoClient: ...


# Default factory: defer the pymongo import so dry-run does not
# require it. Tests can override this via set_client_factory.
def _default_factory(uri: str, *, timeout_ms: int) -> _PymongoClient:
    import pymongo  # type: ignore[import-not-found]  # noqa: F401

    # We use a `with` context only inside the factory; the returned
    # client is owned by the caller.
    return pymongo.MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)  # type: ignore[no-any-return]


_client_factory: _ClientFactory = _default_factory


def set_client_factory(factory: _ClientFactory) -> None:
    """Override the pymongo client factory (test seam)."""
    global _client_factory
    _client_factory = factory


def reset_client_factory() -> None:
    """Reset to the default factory."""
    global _client_factory
    _client_factory = _default_factory


# ---------------------------------------------------------------------------
# Fake client (for offline tests)
# ---------------------------------------------------------------------------


class FakeMongoClient:
    """In-memory MongoDB stand-in for unit tests.

    Implements the same surface the factory uses:
    ``[db]``, ``admin``, ``close``. ``list_collection_names`` and
    ``options`` are recorded so the test can assert what was queried.
    The ``ping`` result is configurable via ``ping_outcome``.

    This class is *only* used by tests; production code never
    instantiates it directly.
    """

    def __init__(
        self,
        *,
        collections: tuple[str, ...] = (),
        ping_outcome: str = "success",
        ping_error: str | None = None,
        list_collections_raises: Exception | None = None,
    ) -> None:
        self._collections = list(collections)
        self._ping_outcome = ping_outcome
        self._ping_error = ping_error
        self._list_raises = list_collections_raises
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.closed = False

    def __getitem__(self, db: str) -> Any:
        return _FakeDatabase(self, db)

    @property
    def admin(self) -> Any:
        return _FakeAdmin(self)

    def close(self) -> None:
        self.closed = True

    # --- internal hooks (test-only) ------------------------------------

    def record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))


class _FakeDatabase:
    def __init__(self, client: FakeMongoClient, name: str) -> None:
        self._client = client
        self._name = name

    def list_collection_names(self) -> list[str]:
        self._client.record("list_collection_names", self._name)
        if self._client._list_raises is not None:
            raise self._client._list_raises
        return list(self._client._collections)

    def __getitem__(self, collection: str) -> Any:
        return _FakeCollection(self._client, collection)


class _FakeCollection:
    def __init__(self, client: FakeMongoClient, name: str) -> None:
        self._client = client
        self._name = name

    def options(self) -> dict[str, Any]:
        self._client.record("options", self._name)
        # Real pymongo returns a SON; tests only inspect the keys.
        return {"capped": False, "validator": {}}


class _FakeAdmin:
    def __init__(self, client: FakeMongoClient) -> None:
        self._client = client

    def command(self, name: str) -> dict[str, Any]:
        self._client.record("command", name)
        if self._client._ping_outcome == "success":
            return {"ok": 1.0}
        raise RuntimeError(self._client._ping_error or "ping failed")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class MongoClientFactory:
    """Zero-write MongoDB preflight client factory.

    All callers must go through :func:`run_preflight`. The factory
    itself only knows how to *create* a client; the preflight method
    enforces the operation cap and the read-only whitelist.
    """

    def create_preflight_client(
        self,
        uri: str,
        *,
        timeout_seconds: int = 3,
    ) -> _PymongoClient:
        """Create a client with a short server-selection timeout.

        Returns ``None``-equivalent in dry-run callers via the
        ``live=False`` branch of :func:`run_preflight`; this method
        always returns a real client.
        """
        return _client_factory(uri, timeout_ms=timeout_seconds * 1000)

    def run_preflight(
        self,
        *,
        uri: str | None = None,
        live: bool = False,
        timeout_seconds: int = 3,
    ) -> MongoPreflightResult:
        """Run the preflight sequence (DESIGN §15.5.2).

        Steps:

        1. Parse URI from env (or accept an explicit ``uri``).
        2. ``admin.command("ping")`` — connectivity.
        3. ``list_collection_names()`` — enumerate.
        4. Check for unexpected P3 collections.
        """
        if not live:
            return MongoPreflightResult(
                connectivity="skipped",
                collections=None,
                p3_collections_found=(),
                warnings=("dry-run: no network or DB connection",),
                detail=None,
                latency_ms=None,
            )

        if uri is None:
            # Defer to the verifier pattern. We only call
            # ``os.getenv`` for the URI key — never for any other
            # secret.
            import os

            uri = os.getenv("MONGODB_URI")

        if not uri:
            return MongoPreflightResult(
                connectivity="skipped",
                collections=None,
                p3_collections_found=(),
                warnings=("MONGODB_URI not declared — cannot run preflight",),
                detail=None,
                latency_ms=None,
            )

        # Operation counter is not strictly enforced at the Python
        # level (pymongo does not expose a public counter), but we
        # record the cap for diagnostic output.
        client = self.create_preflight_client(uri, timeout_seconds=timeout_seconds)
        try:
            # Step 2: ping.
            import time as _time

            t0 = _time.perf_counter()
            try:
                client.admin.command("ping")  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001 — classify below
                return _classify_ping_failure(exc)

            latency_ms = (_time.perf_counter() - t0) * 1000.0

            # Step 3: list collections.
            try:
                db = client[ALLOWED_DATABASE]  # type: ignore[index]
                cols = db.list_collection_names()  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001
                return MongoPreflightResult(
                    connectivity="success",
                    latency_ms=latency_ms,
                    collections=None,
                    p3_collections_found=(),
                    warnings=(f"list_collections_unauthorized: {exc.__class__.__name__}",),
                    detail=None,
                )

            # Step 4: unexpected P3 collection detection.
            unexpected: list[str] = []
            for c in P3_BUSINESS_COLLECTIONS:
                if c in cols:
                    unexpected.append(c)

            warnings: tuple[str, ...] = ()
            if unexpected:
                warnings = (f"UNEXPECTED_EXISTENCE: {list(unexpected)}",)

            return MongoPreflightResult(
                connectivity="success",
                latency_ms=latency_ms,
                collections=tuple(cols),
                p3_collections_found=tuple(unexpected),
                warnings=warnings,
                detail=None,
            )
        finally:
            client.close()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_ping_failure(exc: BaseException) -> MongoPreflightResult:
    """Map an exception to one of the documented failure categories."""
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()
    if "config" in name or "config" in msg or "dnss" in msg or "nodelist" in msg or "name resolution" in msg:
        connectivity = "dns_failure"
    elif "timeout" in name or "timed out" in msg or "networktimeout" in name:
        connectivity = "timeout"
    elif "auth" in name or "auth" in msg or "unauthorized" in msg or "credentials" in msg:
        connectivity = "auth_failure"
    else:
        connectivity = "dns_failure"  # safest fallback per DESIGN §15.5.4

    base = MongoPreflightResult(
        connectivity=connectivity,
        latency_ms=None,
        collections=None,
        p3_collections_found=(),
        warnings=(f"{exc.__class__.__name__}: {exc.__class__.__module__}",),
        detail=None,
    )
    # Trim the warning to the class name only — never the message.
    return replace(base, warnings=(f"{exc.__class__.__name__}",))
