"""Fixtures for PR-1 MongoDB preflight tests.

DESIGN-03-014 §15.5 / SPEC-03-014 §14.2.

Provides a small in-memory substitute for the live ``pymongo``
client. The substitute is the same :class:`FakeMongoClient` that
the production code uses for its plug-in seam, so tests and
production exercise identical paths.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from scripts.t4_preflight.mongo_client import (
    FakeMongoClient,
    reset_client_factory,
    set_client_factory,
)

__all__ = ["FakeMongoClient", "fake_client_factory", "use_fake_client", "isolated_mongo_uri_env"]


def fake_client_factory(client: FakeMongoClient):
    """Return a callable that always returns ``client``."""

    def _factory(uri: str, *, timeout_ms: int):  # type: ignore[no-untyped-def]
        return client

    return _factory


@contextmanager
def use_fake_client(client: FakeMongoClient) -> Iterator[FakeMongoClient]:
    """Install ``client`` as the active factory for the duration."""
    set_client_factory(fake_client_factory(client))
    try:
        yield client
    finally:
        reset_client_factory()


@contextmanager
def isolated_mongo_uri_env(*, uri: str | None) -> Iterator[None]:
    """Snapshot and set/restore ``MONGODB_URI``.

    Pass ``uri=None`` to clear the env var.
    """
    saved = os.environ.get("MONGODB_URI")
    if uri is None:
        os.environ.pop("MONGODB_URI", None)
    else:
        os.environ["MONGODB_URI"] = uri
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("MONGODB_URI", None)
        else:
            os.environ["MONGODB_URI"] = saved
