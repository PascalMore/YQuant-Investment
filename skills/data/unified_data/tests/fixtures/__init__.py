"""Shared test fixtures package for unified_data Phase 1A.

Importable sub-modules and re-exports:

* :mod:`.ta_cn_mock_docs` — 8 collections worth of MongoDB-shaped docs
* :class:`FakeDatabase` / :class:`FakeCollection` / :class:`FakeCursor`
  — in-memory ``db`` substitute implementing the minimal
  ``db[collection].find / find_one / sort`` protocol expected by
  ``TA_CNMongoAdapter``.

The Mongo substitute is consolidated directly into this package
``__init__`` so the T2 file plan's single-fixture entry point remains
the canonical location (no extra ``fake_mongo`` module).
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator


class FakeCollection:
    """A drop-in Mongo collection backed by an external list of dicts.

    The constructor accepts an optional ``storage`` argument that points
    at the canonical backing list. When supplied, every operation
    reads/writes to that same list, so test code that mutates the list
    via :attr:`_docs` (or via the collection directly) observes changes
    from every other handle too.

    If ``storage`` is not provided the collection falls back to a fresh
    private list, matching the standalone-construction style.
    """

    def __init__(
        self,
        docs: Iterable[dict] | None = None,
        *,
        storage: list[dict] | None = None,
    ) -> None:
        if storage is None:
            self._docs: list[dict] = list(docs or [])
        else:
            self._docs = storage

    @property
    def docs(self) -> list[dict]:
        """Direct access to the backing list (for mutation / inspection)."""
        return self._docs

    def add(self, doc: dict) -> None:
        """Append a document (test-only)."""
        self._docs.append(dict(doc))

    # ------------------------------------------------------------------
    # Query surface used by the adapter
    # ------------------------------------------------------------------

    def find_one(self, query: dict) -> dict | None:
        for doc in self._docs:
            if self._match(doc, query):
                return dict(doc)
        return None

    def find(self, query: dict) -> "FakeCursor":
        matched = [dict(doc) for doc in self._docs if self._match(doc, query)]
        return FakeCursor(matched)

    # ------------------------------------------------------------------
    # Filter logic
    # ------------------------------------------------------------------

    @staticmethod
    def _match(doc: dict, query: dict) -> bool:
        if not query:
            return True
        for key, expected in query.items():
            if key == "$or":
                if not any(FakeCollection._match(doc, branch) for branch in expected):
                    return False
                continue
            if not FakeCollection._field_matches(doc, key, expected):
                return False
        return True

    @staticmethod
    def _field_matches(doc: dict, key: str, expected: Any) -> bool:
        actual = doc.get(key)
        if isinstance(expected, dict):
            # Operator dict ({$gte, $lte, $eq, ...}); we only need
            # $gte/$lte for current tests.
            for op, bound in expected.items():
                if op == "$gte" and not (actual is not None and actual >= bound):
                    return False
                if op == "$lte" and not (actual is not None and actual <= bound):
                    return False
                if op == "$eq" and actual != bound:
                    return False
                if op == "$gt" and not (actual is not None and actual > bound):
                    return False
                if op == "$lt" and not (actual is not None and actual < bound):
                    return False
                if op == "$ne" and actual == bound:
                    return False
                if op == "$in":
                    if not isinstance(bound, (list, tuple, set)):
                        return False
                    if actual not in bound:
                        return False
            return True
        return actual == expected


class FakeCursor:
    """A minimal Mongo cursor with ``.sort()`` chained iteration."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs
        self._sort_spec: list[tuple[str, int]] | None = None

    def sort(self, spec: list[tuple[str, int]] | tuple[str, int]) -> "FakeCursor":
        if isinstance(spec, tuple):
            spec = [spec]
        self._sort_spec = list(spec)
        return self

    def __iter__(self) -> Iterator[dict]:
        docs = list(self._docs)
        if self._sort_spec:
            for field, direction in reversed(self._sort_spec):
                docs.sort(key=lambda d: d.get(field), reverse=(direction == -1))
        return iter(docs)


class FakeDatabase:
    """A drop-in ``pymongo.database.Database`` for tests.

    Accepts a mapping ``{collection_name: [docs, ...]}`` at construction.
    Collections added later via ``add_collection`` mirror the same
    behaviour. ``__getitem__`` returns a :class:`FakeCollection`; this
    is exactly the contract the adapter uses via ``db[name]``.
    """

    def __init__(self, docs_by_collection: dict[str, list[dict]] | None = None) -> None:
        self._collections: dict[str, list[dict]] = {}
        if docs_by_collection:
            for name, docs in docs_by_collection.items():
                self._collections[name] = list(docs)

    def add_collection(self, name: str, docs: Iterable[dict] | None = None) -> FakeCollection:
        self._collections[name] = list(docs or [])
        return FakeCollection(storage=self._collections[name])

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self._collections:
            self._collections[name] = []
        return FakeCollection(storage=self._collections[name])


__all__ = [
    "FakeCollection",
    "FakeCursor",
    "FakeDatabase",
]
