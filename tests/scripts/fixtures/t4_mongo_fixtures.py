"""Fixtures for PR-1 MongoDB preflight tests.

DESIGN-03-014 V0.12 §15.5 / SPEC-03-014 V0.5 §14.2.

Provides a small in-memory substitute for the live ``pymongo``
client. The substitute is the same :class:`FakeMongoClient` that
the production code uses for its plug-in seam, so tests and
production exercise identical paths.

The factory signature follows the V0.12 five-component contract
(host / port / username / password / authSource) rather than a
URI string. ``fake_client_factory`` ignores every parameter
except the chosen client.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from scripts.t4_preflight.mongo_client import (
    FakeMongoClient,
    reset_client_factory,
    set_client_factory,
)

__all__ = ["FakeMongoClient", "fake_client_factory", "use_fake_client", "isolated_skills_env"]


def fake_client_factory(client: FakeMongoClient):
    """Return a callable that always returns ``client``."""

    def _factory(
        host: str,
        port: int,
        *,
        username: str,
        password: str,
        auth_source: str,
        timeout_ms: int,
    ):  # type: ignore[no-untyped-def]
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
def isolated_skills_env(
    *,
    contents: str | None,
    path: Path,
) -> Iterator[Path]:
    """Snapshot/restore a sandbox ``skills/.env`` at ``path``.

    Pass ``contents=None`` to delete the file. Returns the
    ``Path`` to the parent directory so the resolver can be
    pointed at it.
    """
    target = path
    had_file = target.exists()
    saved: bytes | None = None
    if had_file:
        saved = target.read_bytes()
    if contents is None:
        if target.exists():
            target.unlink()
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
    try:
        yield target.parent
    finally:
        if contents is None:
            if target.exists():
                target.unlink()
        if saved is not None and not target.exists():
            target.write_bytes(saved)
