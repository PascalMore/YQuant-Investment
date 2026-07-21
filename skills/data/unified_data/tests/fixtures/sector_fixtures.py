"""Sector fixtures for T3-A offline implementation tests (Phase 3 P3-A).

This fixture module provides:

* :class:`SectorSnapshotFixture` — a tiny stand-in dataclass for
  :class:`SectorSnapshot`. The real :class:`SectorSnapshot` lives in
  ``models/domain/sector.py`` (out of T3-A scope) so this fixture
  avoids touching production code while still supplying a
  realistic-shape object for the persistence writer and router
  injection tests.
* :func:`sample_sector_records` — three :class:`SectorSnapshotFixture`
  records covering two sectors / two dates for upsert + overwrite
  assertions.
* :class:`StubAKShareSectorProvider` — a minimal
  :class:`DataProvider`-compatible stub that advertises
  ``sector.snapshot`` and ``sector.ranking`` and returns the fixture
  records. **Not** the production ``AKShareProvider`` — Phase 3
  capability registration with the real provider is *out of T3-A
  scope* (kanban task body explicitly forbids editing
  ``providers/akshare.py``).

The fixture deliberately stays lightweight: no real AKShare call, no
MongoDB DDL, no schema impact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from skills.data.unified_data import DataProvider, Market


@dataclass
class SectorSnapshotFixture:
    """T3-A fixture stand-in for :class:`SectorSnapshot`.

    Field set mirrors the documented Phase 3 ``SectorSnapshot``
    surface (DESIGN-03-014 §3.1) at the level the persistence writer
    actually inspects (``market``, ``sector_code``, ``snapshot_date``,
    plus ``pct_chg``/``rank`` for the ranking flavour). The full
    dataclass lives in ``models/domain/sector.py`` — the fixture
    exists only so T3-A can write tests without forcing a real
    dataclass dependency on the persistence writer.
    """

    sector_code: str
    sector_name: str
    sector_type: str
    snapshot_date: str
    market: str = "CN"
    provider: str = "akshare"
    rank: int | None = None
    pct_chg: float | None = None
    leading_stock: str | None = None
    advance_count: int = 0
    decline_count: int = 0
    total_count: int = 0
    extras: dict[str, Any] = field(default_factory=dict)


def sample_sector_records() -> list[SectorSnapshotFixture]:
    """Return three :class:`SectorSnapshotFixture` records.

    Layout:

    * BK0489 / 2026-07-21 — pct_chg=2.35, rank=5
    * BK0489 / 2026-07-20 — pct_chg=1.10, rank=12
    * BK0500 / 2026-07-21 — pct_chg=-0.50, rank=88

    Tests use these to assert the writer's upsert / overwrite /
    delete behaviour without coupling to the production dataclass.
    """
    return [
        SectorSnapshotFixture(
            sector_code="BK0489",
            sector_name="白酒",
            sector_type="industry",
            snapshot_date="2026-07-21",
            rank=5,
            pct_chg=2.35,
            advance_count=12,
            decline_count=3,
            total_count=15,
        ),
        SectorSnapshotFixture(
            sector_code="BK0489",
            sector_name="白酒",
            sector_type="industry",
            snapshot_date="2026-07-20",
            rank=12,
            pct_chg=1.10,
            advance_count=9,
            decline_count=5,
            total_count=14,
        ),
        SectorSnapshotFixture(
            sector_code="BK0500",
            sector_name="证券",
            sector_type="industry",
            snapshot_date="2026-07-21",
            rank=88,
            pct_chg=-0.50,
            advance_count=4,
            decline_count=18,
            total_count=22,
        ),
    ]


class StubAKShareSectorProvider(DataProvider):
    """In-memory stand-in for AKShare's Phase 3 sector capabilities.

    The real AKShare integration is out of T3-A scope; this stub
    advertises only the two P3-A capabilities and returns the fixture
    records so router-level injection tests can assert the
    internal-first / Step-2 dispatch.

    Knobs (kw-only):

    * ``payload`` — list of dicts returned by :meth:`fetch`. Defaults
      to ``sample_sector_records()`` serialised via ``asdict``.
    * ``raise_on_fetch`` — exception to raise instead of returning
      payload (default ``None``).
    * ``available`` — value of :meth:`is_available` (default
      ``True``).
    * ``capabilities`` — capability set (default
      ``{"sector.snapshot", "sector.ranking"}``).
    """

    def __init__(
        self,
        name: str = "akshare_stub",
        *,
        payload: list[dict] | None = None,
        capabilities: Iterable[str] = (
            "sector.snapshot",
            "sector.ranking",
        ),
        markets: Iterable[Market] = (Market.CN,),
        raise_on_fetch: BaseException | None = None,
        available: bool = True,
    ) -> None:
        self._name = name
        self._capabilities = set(capabilities)
        self._markets = set(markets)
        if payload is None:
            payload = [_asdict(r) for r in sample_sector_records()]
        self._payload = payload
        self._raise = raise_on_fetch
        self._available = available
        self.call_log: list[tuple[str, str, str, dict]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> set[str]:
        return set(self._capabilities)

    @property
    def markets(self) -> set[Market]:
        return set(self._markets)

    def is_available(self) -> bool:
        return self._available

    def fetch(
        self,
        domain: str,
        operation: str,
        security_id: Any,
        **params: Any,
    ) -> Any:
        self.call_log.append(
            (self._name, f"{domain}.{operation}", getattr(security_id, "canonical", "?"), dict(params))
        )
        if self._raise is not None:
            raise self._raise
        return list(self._payload)


def _asdict(record: SectorSnapshotFixture) -> dict:
    """Serialise a :class:`SectorSnapshotFixture` to a plain dict.

    Excludes the ``extras`` placeholder (test-only hook) so the
    round-tripped payload is the minimal shape the persistence writer
    expects.
    """
    return {
        "market": record.market,
        "sector_code": record.sector_code,
        "sector_name": record.sector_name,
        "sector_type": record.sector_type,
        "snapshot_date": record.snapshot_date,
        "provider": record.provider,
        "rank": record.rank,
        "pct_chg": record.pct_chg,
        "leading_stock": record.leading_stock,
        "advance_count": record.advance_count,
        "decline_count": record.decline_count,
        "total_count": record.total_count,
    }


__all__ = [
    "SectorSnapshotFixture",
    "sample_sector_records",
    "StubAKShareSectorProvider",
]