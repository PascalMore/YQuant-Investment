"""T4 MongoDB zero-write preflight client (PR-1).

DESIGN-03-014 V0.12 §15.5 / SPEC-03-014 V0.5 §14.2 / RFC-03-014 V0.6 §13.2.

This module provides two layers:

1. ``LegacyConfigResolver`` (DESIGN §15.5.2) — the sanctioned way
   for the PR-1 preflight to obtain MongoDB connection parameters.
   It reads ``skills/.env`` via :func:`dotenv.dotenv_values` (NOT
   :func:`dotenv.load_dotenv`, to avoid polluting ``os.environ``)
   and resolves the five ``MONGODB_*`` keys. There is no fallback
   to ``MONGO_URI``, ``MONGODB_URI``, ``./.env``, ``~/.hermes/...``,
   or any other source. Missing keys or a ``MONGODB_DATABASE``
   value other than ``"tradingagents"`` abort the resolver with
   ``NOT_AUTHORIZED`` semantics (no client is constructed).

2. ``MongoClientFactory`` — the historical layer that older tests
   and dry-run paths still rely on. It accepts an explicit ``uri``
   (test seam) and uses :func:`pymongo.MongoClient` to create a
   single client. Fake substitutes are installed via
   :func:`set_client_factory`.

The factory also exposes a hard operation cap
(``PREFLIGHT_MAX_OPERATIONS``) so a runaway preflight can never
exceed the design-specified call budget.

Public read-only operations allowed (DESIGN §15.5.1):

* ``admin.command("ping")`` — connectivity
* ``db.list_collection_names()`` — collection enumeration
* ``db[collection].options()`` — only when a target collection is
  unexpectedly present
* ``client.close()`` — cleanup

The factory intentionally does NOT import :mod:`pymongo` at module
load time. The pymongo import is deferred to the first live call so
that dry-run invocations never need pymongo installed. Tests can
substitute a fake client via :func:`set_client_factory`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Protocol

from .config import (
    ALLOWED_DATABASE,
    ALLOWED_DATABASE_VALUE,
    MONGODB_FIVE_KEYS,
    P3_BUSINESS_COLLECTIONS,
    PREFLIGHT_MAX_OPERATIONS,
    SKILLS_ENV_PATH,
)
from .models import MongoPreflightResult

__all__ = [
    # Legacy layer (kept for tests and dry-run)
    "MongoClientFactory",
    "set_client_factory",
    "reset_client_factory",
    "FakeMongoClient",
    # DESIGN V0.12 layer (PR-1 live-read)
    "LegacyConfigResolver",
    "ResolvedConfig",
    "PreflightRunner",
    "AuthFiveTuple",
]


# ---------------------------------------------------------------------------
# Legacy layer: plug-in seam + fake client
# ---------------------------------------------------------------------------


class _PymongoClient(Protocol):
    def __getitem__(self, db: str) -> Any: ...
    def close(self) -> None: ...
    def admin(self) -> Any: ...


class _ClientFactory(Protocol):
    def __call__(self, host: str, port: int, *, username: str, password: str,
                 auth_source: str, timeout_ms: int) -> _PymongoClient: ...


# Default factory: defer the pymongo import so dry-run does not
# require it. Tests can override this via set_client_factory.
def _default_factory(
    host: str,
    port: int,
    *,
    username: str,
    password: str,
    auth_source: str,
    timeout_ms: int,
) -> _PymongoClient:
    import pymongo  # type: ignore[import-not-found]  # noqa: F401

    return pymongo.MongoClient(  # type: ignore[no-any-return]
        host=host,
        port=port,
        username=username,
        password=password,
        authSource=auth_source,
        serverSelectionTimeoutMS=timeout_ms,
    )


_client_factory: _ClientFactory = _default_factory


def set_client_factory(factory: _ClientFactory) -> None:
    """Override the pymongo client factory (test seam)."""
    global _client_factory
    _client_factory = factory


def reset_client_factory() -> None:
    """Reset to the default factory."""
    global _client_factory
    _client_factory = _default_factory


class FakeMongoClient:
    """In-memory MongoDB stand-in for unit tests.

    Implements the same surface the factory uses:
    ``[db]``, ``admin``, ``close``. ``list_collection_names`` and
    ``options`` are recorded so the test can assert what was queried.
    The ``ping`` result is configurable via ``ping_outcome``.

    This class is *only* used by tests; production code never
    instantiates it directly.

    .. note::
        The factory signature moved from a single ``uri`` string to a
        five-component tuple in PR-1 V0.12. ``FakeMongoClient``
        records the call so tests can assert the connection
        parameters are correct.
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
        self.connection_params: dict[str, Any] = {}
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
# Legacy factory (kept for backward compatibility / dry-run / explicit-uri tests)
# ---------------------------------------------------------------------------


class MongoClientFactory:
    """MongoDB preflight client factory (legacy + five-component).

    Behavior depends on the call:

    * ``run_preflight(live=False)`` — dry-run; returns a
      ``"skipped"`` ``MongoPreflightResult`` without touching the
      network. No pymongo import.
    * ``run_preflight(live=True, uri=...)`` — legacy path; uses the
      ``uri`` string directly via the installed factory. Kept so
      existing tests that pre-canned a fake URI still work.
    * ``run_preflight(live=True, uri=None)`` — DESIGN V0.12 path;
      resolves the five ``MONGODB_*`` keys from
      ``LegacyConfigResolver`` and constructs a MongoClient
      component-wise.

    All callers must go through :func:`run_preflight`. The factory
    itself only knows how to *create* a client; the preflight method
    enforces the operation cap and the read-only whitelist.
    """

    def create_preflight_client(
        self,
        host: str,
        port: int,
        *,
        username: str,
        password: str,
        auth_source: str,
        timeout_seconds: int = 3,
    ) -> _PymongoClient:
        """Create a client with a short server-selection timeout."""
        return _client_factory(
            host,
            port,
            username=username,
            password=password,
            auth_source=auth_source,
            timeout_ms=timeout_seconds * 1000,
        )

    def run_preflight(
        self,
        *,
        uri: str | None = None,
        live: bool = False,
        timeout_seconds: int = 3,
    ) -> MongoPreflightResult:
        """Run the preflight sequence (DESIGN §15.5.2).

        Two live modes:

        * ``uri`` provided — legacy path; the string is passed
          through to the installed client factory as a host name.
          Tests install a fake factory for this branch.
        * ``uri`` is ``None`` — DESIGN V0.12 path; delegates to
          :class:`LegacyConfigResolver` + :class:`PreflightRunner`.

        Any network call returns a structured
        :class:`MongoPreflightResult` whose connectivity field is
        one of ``success / dns_failure / timeout / auth_failure /
        skipped / env_missing``.
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

        # Decide which live path to use.
        if uri is not None:
            return _legacy_uri_preflight(uri, timeout_seconds)
        # New (V0.12) path: resolve five keys, then run PreflightRunner.
        resolver = LegacyConfigResolver()
        runner = PreflightRunner(resolver)
        return runner.run_preflight(live=True, timeout=timeout_seconds)


def _legacy_uri_preflight(uri: str, timeout_seconds: int) -> MongoPreflightResult:
    """Legacy path: callers pass an explicit URI string.

    Tests install a fake factory via :func:`set_client_factory` to
    simulate ping/list_collections outcomes. Real pymongo is *not*
    required for this branch — the legacy ``_default_factory``
    accepts any URI, but tests always substitute the fake.
    """
    import time as _time

    client = _client_factory(
        uri,
        0,
        username="",
        password="",
        auth_source="",
        timeout_ms=timeout_seconds * 1000,
    )
    try:
        t0 = _time.perf_counter()
        try:
            client.admin.command("ping")  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 — classify below
            return _classify_ping_failure(exc)

        latency_ms = (_time.perf_counter() - t0) * 1000.0

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
# DESIGN V0.12 §15.5.2 — LegacyConfigResolver + PreflightRunner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedConfig:
    """Five-component resolver result (DESIGN §15.5.2).

    Holds boolean conclusions for each key plus an aggregated
    ``all_resolved`` flag. Never carries the raw values.

    The string fields only label the source (constant) — no values,
    no lengths, no URIs.
    """

    source_label: str = "phase2_skills_env"
    source_path: str = SKILLS_ENV_PATH
    host_resolved: bool = False
    port_resolved: bool = False
    username_resolved: bool = False
    password_resolved: bool = False
    database_resolved: bool = False
    all_resolved: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthFiveTuple:
    """Five-component MongoDB connection parameters.

    Carries the actual values for client construction only.
    MUST NEVER be serialized or printed. Held in-memory only.
    """

    host: str
    port: int
    username: str
    password: str
    auth_source: str

    def as_factory_kwargs(self) -> dict[str, Any]:
        """Convert to kwargs for the installed client factory."""
        return {
            "username": self.username,
            "password": self.password,
            "auth_source": self.auth_source,
        }


class LegacyConfigResolver:
    """Phase-2 ``skills/.env`` five-component resolver (DESIGN §15.5.2).

    Single responsibility: read ``skills/.env`` via
    :func:`dotenv.dotenv_values` and resolve the five
    ``MONGODB_*`` keys. No fallback to ``MONGO_URI``,
    ``MONGODB_URI``, ``./.env``, ``~/.hermes/profiles/...``, or
    :func:`dotenv.load_dotenv`.

    Dry-run (``live=False``) only checks file existence + readable;
    it never reads file contents.

    Live (``live=True``) reads file contents (no env pollution),
    validates each key, and returns a ``ResolvedConfig`` with
    boolean conclusions. ``MONGODB_DATABASE`` is also checked
    against ``ALLOWED_DATABASE_VALUE`` (= ``"tradingagents"``) —
    any other value aborts with ``NOT_AUTHORIZED`` semantics.
    """

    def __init__(self, dotenv_path: str = SKILLS_ENV_PATH) -> None:
        if not dotenv_path:
            raise ValueError("dotenv_path must be explicit, not empty")
        self._dotenv_path = dotenv_path
        self._resolved: ResolvedConfig | None = None
        # AuthFiveTuple is held only after resolve(live=True) passes.
        # It is never serialized, logged, or printed.
        self._auth: AuthFiveTuple | None = None
        self._client: Any = None

    # --- Resolver --------------------------------------------------------

    def resolve(self, *, live: bool = False) -> ResolvedConfig:
        """Resolve the five ``MONGODB_*`` keys.

        ``live=False`` (dry-run): only checks file existence +
        readable. Returns ``ResolvedConfig(all_resolved=False)``.

        ``live=True``: parses the file via ``dotenv_values()``,
        verifies each key is non-empty, ``MONGODB_PORT`` parses as
        ``int``, ``MONGODB_DATABASE`` equals ``"tradingagents"``.
        Returns a ``ResolvedConfig`` with all booleans; values are
        not stored in the result.
        """
        if not live:
            exists = os.path.isfile(self._dotenv_path)
            readable = os.access(self._dotenv_path, os.R_OK) if exists else False
            errors: tuple[str, ...] = ()
            if not exists:
                errors = ("file_not_found",)
            elif not readable:
                errors = ("file_not_readable",)
            cfg = ResolvedConfig(
                source_label="phase2_skills_env",
                source_path=self._dotenv_path,
                host_resolved=False,
                port_resolved=False,
                username_resolved=False,
                password_resolved=False,
                database_resolved=False,
                all_resolved=False,
                errors=errors,
            )
            self._resolved = cfg
            return cfg

        # live-read path
        try:
            from dotenv import dotenv_values
        except ImportError:
            cfg = ResolvedConfig(
                source_label="phase2_skills_env",
                source_path=self._dotenv_path,
                errors=("python_dotenv_not_importable",),
            )
            self._resolved = cfg
            return cfg

        # Local, side-effect-free parse.
        parsed = dotenv_values(self._dotenv_path)

        host_raw = parsed.get("MONGODB_HOST", "") or ""
        port_raw = parsed.get("MONGODB_PORT", "") or ""
        username_raw = parsed.get("MONGODB_USERNAME", "") or ""
        password_raw = parsed.get("MONGODB_PASSWORD", "") or ""
        db_raw = parsed.get("MONGODB_DATABASE", "") or ""

        errors_list: list[str] = []

        host_ok = bool(host_raw)
        if not host_ok:
            errors_list.append("MONGODB_HOST_missing_or_empty")

        port_ok = bool(port_raw)
        port_value = 0
        if port_ok:
            try:
                port_value = int(port_raw)
            except (TypeError, ValueError):
                port_ok = False
                errors_list.append("MONGODB_PORT_not_int")

        username_ok = bool(username_raw)
        if not username_ok:
            errors_list.append("MONGODB_USERNAME_missing_or_empty")

        password_ok = bool(password_raw)
        if not password_ok:
            errors_list.append("MONGODB_PASSWORD_missing_or_empty")

        db_present = bool(db_raw)
        db_value_ok = (
            db_present and db_raw.strip().lower() == ALLOWED_DATABASE_VALUE
        )
        if db_present and not db_value_ok:
            errors_list.append("MONGODB_DATABASE_not_tradingagents")
        elif not db_present:
            errors_list.append("MONGODB_DATABASE_missing_or_empty")

        all_ok = host_ok and port_ok and username_ok and password_ok and db_value_ok

        cfg = ResolvedConfig(
            source_label="phase2_skills_env",
            source_path=self._dotenv_path,
            host_resolved=host_ok,
            port_resolved=port_ok,
            username_resolved=username_ok,
            password_resolved=password_ok,
            database_resolved=db_value_ok,
            all_resolved=all_ok,
            errors=tuple(errors_list),
        )
        self._resolved = cfg

        if all_ok:
            # Hold the values in-memory for ``build_client`` only.
            # Not logged, not serialized, not printed.
            self._auth = AuthFiveTuple(
                host=str(host_raw),
                port=int(port_value),
                username=str(username_raw),
                password=str(password_raw),
                auth_source=str(db_raw),
            )

        return cfg

    # --- Client construction --------------------------------------------

    def build_client(self, *, live: bool = False, timeout: int = 3):
        """Construct a MongoClient from the resolved config.

        ``live=False`` → ``None``.

        ``live=True`` → a real :class:`pymongo.MongoClient` is
        constructed from the five-component tuple with
        ``authSource`` derived directly from the
        ``MONGODB_DATABASE`` key value. If the resolver has not
        yet passed, ``resolve(live=True)`` is run first. If
        resolution still fails, ``None`` is returned.
        """
        if not live:
            return None

        if self._client is not None:
            return self._client

        if self._resolved is None or not self._resolved.all_resolved:
            cfg = self.resolve(live=True)
            if not cfg.all_resolved:
                return None

        assert self._auth is not None, (
            "AuthFiveTuple missing after successful resolve"
        )
        import pymongo

        self._client = pymongo.MongoClient(
            host=self._auth.host,
            port=self._auth.port,
            username=self._auth.username,
            password=self._auth.password,
            authSource=self._auth.auth_source,  # = MONGODB_DATABASE value
            serverSelectionTimeoutMS=timeout * 1000,
        )
        return self._client

    def close(self) -> None:
        """Close the constructed client (idempotent)."""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None
                self._auth = None
                self._resolved = None


class PreflightRunner:
    """MongoDB zero-write preflight runner (DESIGN §15.5.2).

    Encapsulates the three-step preflight:

    1. Resolve the five ``MONGODB_*`` keys.
    2. ``admin.command("ping")`` — connectivity.
    3. ``list_collection_names()`` — enumerate, plus P3-collection
       presence check.

    All steps are read-only. No DDL/DML is issued.
    """

    def __init__(self, resolver: LegacyConfigResolver | None = None) -> None:
        self.resolver = resolver or LegacyConfigResolver()

    def run_preflight(
        self,
        *,
        live: bool = False,
        timeout: int = 3,
    ) -> MongoPreflightResult:
        """Execute the preflight sequence.

        ``live=False``: returns a ``"dry_run"`` result without
        touching the network.

        ``live=True``: resolves the config, builds the client,
        pings, then lists collections. Returns the appropriate
        :class:`MongoPreflightResult` based on the observed
        connectivity outcome.
        """
        if not live:
            return MongoPreflightResult(
                connectivity="dry_run",
                latency_ms=None,
                collections=None,
                p3_collections_found=(),
                warnings=("dry-run: config not resolved",),
                detail=None,
            )

        cfg = self.resolver.resolve(live=True)
        if not cfg.all_resolved:
            joined = ",".join(cfg.errors)
            return MongoPreflightResult(
                connectivity="env_missing",
                latency_ms=None,
                collections=None,
                p3_collections_found=(),
                warnings=(f"skills/.env five keys not all resolved: {joined}",),
                detail=None,
            )

        import time as _time

        t0 = _time.perf_counter()
        client = self.resolver.build_client(live=True, timeout=timeout)
        if client is None:
            return MongoPreflightResult(
                connectivity="env_missing",
                latency_ms=None,
                collections=None,
                p3_collections_found=(),
                warnings=("Failed to build client from resolved config",),
                detail=None,
            )

        try:
            try:
                client.admin.command("ping")
            except Exception as exc:  # noqa: BLE001 — classify below
                return _classify_ping_failure(
                    exc, latency_ms=(_time.perf_counter() - t0) * 1000.0
                )

            latency_ms = (_time.perf_counter() - t0) * 1000.0

            try:
                db = client[ALLOWED_DATABASE]
                cols = db.list_collection_names()
            except Exception as exc:  # noqa: BLE001
                return MongoPreflightResult(
                    connectivity="success",
                    latency_ms=latency_ms,
                    collections=None,
                    p3_collections_found=(),
                    warnings=(
                        f"list_collections_unauthorized: {exc.__class__.__name__}",
                    ),
                    detail=None,
                )

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
            self.resolver.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_ping_failure(
    exc: BaseException,
    *,
    latency_ms: float | None = None,
) -> MongoPreflightResult:
    """Map an exception to one of the documented failure categories."""
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()
    if "config" in name or "config" in msg or "dnss" in msg or "nodelist" in msg or "name resolution" in msg:
        connectivity = "dns_failure"
    elif "timeout" in name or "timed out" in msg or "networktimeout" in name or "serverselection" in name:
        connectivity = "timeout"
    elif "auth" in name or "auth" in msg or "unauthorized" in msg or "credentials" in msg:
        connectivity = "auth_failure"
    else:
        connectivity = "dns_failure"  # safest fallback per DESIGN §15.5.4

    base = MongoPreflightResult(
        connectivity=connectivity,
        latency_ms=latency_ms,
        collections=None,
        p3_collections_found=(),
        warnings=(f"{exc.__class__.__name__}",),
        detail=None,
    )
    # Trim the warning to the class name only — never the message.
    return replace(base, warnings=(f"{exc.__class__.__name__}",))