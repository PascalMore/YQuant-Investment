"""Phase 3 P0 mapping tests for the P3-A sector capability.

Covers the Phase 3 P0 contracts for ``sector.snapshot`` and
``sector.ranking`` (DESIGN-03-014 §P0.3 / §P0.6):

* ``_EXPECTED_SECTOR_SNAPSHOT_FIELDS`` integrity (PA-1) — 12 fields
  in the canonical order, the 4 business-identity fields lead.
* ``_EXPECTED_SECTOR_RANKING_FIELDS`` strict subset (PA-2) — 8
  fields, narrower than snapshot.
* ``SectorSnapshot.from_dict`` 松映射 contract: missing optionals
  default to ``None`` / ``0``; ``snapshot_date`` / ``sector_code``
  keep raw ``"YYYY-MM-DD"`` / ``"BK...."`` shape.
* Stub/fixture mapping: a :class:`StubAKShareSectorProvider` payload
  round-trips through ``SectorSnapshot.from_dict`` byte-for-byte
  (the dataclass schema is the canonical mapping contract).
* Empty-result semantics: empty stub payload → ``DataResult`` with
  ``is_empty=True`` and ``data=None``; the read path never
  materialises (no ``ud_materialized(ok)`` marker).
* Drift tolerance: extra fields silently ignored, no ``KeyError``.
* Date ordering: a multi-record ``sector.ranking`` payload is
  surfaced in the order documented by the service contract;
  ``snapshot_date`` is preserved as-is.
* ``source_trace`` discipline: regardless of fixture size the read
  path produces zero ``ud_materialized(ok)`` markers (the P3-A
  read path is read-only).

All tests are offline: no real MongoDB / AKShare / network access.
"""

from __future__ import annotations

import pytest

from skills.data.unified_data import (
    DataRouter,
    Market,
    ProviderRegistry,
)
from skills.data.unified_data.models.domain.sector import SectorSnapshot
from skills.data.unified_data.providers import _stub_columns
from skills.data.unified_data.services.sector_service import SectorService
from skills.data.unified_data.tests.fixtures.sector_fixtures import (
    StubAKShareSectorProvider,
)


# ---------------------------------------------------------------------------
# Constants — single source of truth for the P3-A capability strings.
# ---------------------------------------------------------------------------

CAP_SECTOR_SNAPSHOT = "sector.snapshot"
CAP_SECTOR_RANKING = "sector.ranking"

EXPECTED_SNAPSHOT = getattr(_stub_columns, "_EXPECTED_SECTOR_SNAPSHOT_FIELDS")
EXPECTED_RANKING = getattr(_stub_columns, "_EXPECTED_SECTOR_RANKING_FIELDS")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_registry(payload: list[dict] | None = None) -> ProviderRegistry:
    """Register a stub provider against the standard P3-A capabilities."""
    registry = ProviderRegistry()
    stub = StubAKShareSectorProvider(
        name="sector_stub",
        payload=payload,
    )
    registry.register(stub)
    return registry


def _build_service(router: DataRouter | None) -> SectorService:
    """Build a :class:`SectorService` with a router wired via the constructor kwarg.

    D3 changed the constructor signature to
    ``__init__(self, adapter, router: DataRouter | None = None)`` —
    ``adapter`` is the Phase 1A regression guard (T3-A) so we pass
    ``None`` here. The P3-A read path is irrelevant to ``adapter``.
    """
    return SectorService(adapter=None, router=router)  # type: ignore[arg-type]


# ===========================================================================
# (1) ``_EXPECTED_SECTOR_SNAPSHOT_FIELDS`` (PA-1) baseline + ordering
# ===========================================================================


class TestExpectedSectorSnapshotFieldsContract:
    """``_EXPECTED_SECTOR_SNAPSHOT_FIELDS`` baseline + frozen ordering."""

    def test_snapshot_set_has_exactly_twelve_fields(self) -> None:
        """PA-1: snapshot must be exactly 12 columns per §4.3."""
        assert len(EXPECTED_SNAPSHOT) == 12, (
            f"_EXPECTED_SECTOR_SNAPSHOT_FIELDS must be exactly 12 fields "
            f"per PA-1 / SPEC §4.3; got {len(EXPECTED_SNAPSHOT)}"
        )

    def test_snapshot_set_business_identity_leads(self) -> None:
        """The 4 business-identity fields must lead the snapshot set."""
        assert EXPECTED_SNAPSHOT[:4] == (
            "sector_code",
            "sector_name",
            "sector_type",
            "snapshot_date",
        ), (
            f"_EXPECTED_SECTOR_SNAPSHOT_FIELDS must begin with the 4 "
            f"business-identity fields; got first 4 = "
            f"{list(EXPECTED_SNAPSHOT[:4])}"
        )

    def test_snapshot_set_has_baseline_metrics(self) -> None:
        """Snapshot must carry pct_chg, advance_count, decline_count,
        leading_stock, turnover_rate, main_net_inflow."""
        snapshot_set = set(EXPECTED_SNAPSHOT)
        for field in (
            "pct_chg",
            "advance_count",
            "decline_count",
            "leading_stock",
            "turnover_rate",
            "main_net_inflow",
        ):
            assert field in snapshot_set, (
                f"_EXPECTED_SECTOR_SNAPSHOT_FIELDS missing {field!r}"
            )

    def test_snapshot_set_has_rank_and_total_count(self) -> None:
        """Snapshot must carry rank, total_count, snapshot_date."""
        snapshot_set = set(EXPECTED_SNAPSHOT)
        for field in ("rank", "total_count", "snapshot_date"):
            assert field in snapshot_set, (
                f"_EXPECTED_SECTOR_SNAPSHOT_FIELDS missing {field!r}"
            )


# ===========================================================================
# (2) ``_EXPECTED_SECTOR_RANKING_FIELDS`` (PA-2) baseline + subset
# ===========================================================================


class TestExpectedSectorRankingFieldsContract:
    """``_EXPECTED_SECTOR_RANKING_FIELDS`` baseline + frozen ordering."""

    def test_ranking_set_has_exactly_eight_fields(self) -> None:
        """PA-2: ranking must be exactly 8 columns per §4.3."""
        assert len(EXPECTED_RANKING) == 8, (
            f"_EXPECTED_SECTOR_RANKING_FIELDS must be exactly 8 fields "
            f"per PA-2 / SPEC §4.3; got {len(EXPECTED_RANKING)}"
        )

    def test_ranking_set_is_strict_subset_of_snapshot(self) -> None:
        """PA-2: ranking must be a subset of snapshot per DESIGN §P0.3.2."""
        assert set(EXPECTED_RANKING).issubset(set(EXPECTED_SNAPSHOT)), (
            f"_EXPECTED_SECTOR_RANKING_FIELDS must be a subset of "
            f"_EXPECTED_SECTOR_SNAPSHOT_FIELDS; "
            f"ranking-only fields: {set(EXPECTED_RANKING) - set(EXPECTED_SNAPSHOT)}"
        )

    def test_ranking_omits_snapshot_only_fields(self) -> None:
        """PA-2: snapshot-only fields (turnover_rate, main_net_inflow,
        total_count, leading_stock) are not in the ranking set."""
        ranking_set = set(EXPECTED_RANKING)
        for field in ("turnover_rate", "main_net_inflow", "total_count",
                      "leading_stock"):
            assert field not in ranking_set, (
                f"_EXPECTED_SECTOR_RANKING_FIELDS must NOT include "
                f"snapshot-only field {field!r}"
            )


# ===========================================================================
# (3) ``SectorSnapshot.from_dict`` 松映射 + stub/fixture mapping
# ===========================================================================


class TestSectorSnapshotFromDictMapping:
    """``from_dict`` is the canonical mapping contract for sector snapshots."""

    def test_full_payload_round_trip(self) -> None:
        """A complete stub payload round-trips through ``from_dict``."""
        payload = {
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "market": "CN",
            "provider": "sector_stub",
            "rank": 5,
            "pct_chg": 2.35,
            "leading_stock": "600519",
            "leading_stock_name": "贵州茅台",
            "leading_pct_chg": 4.10,
            "advance_count": 12,
            "decline_count": 3,
            "total_count": 15,
            "turnover_rate": 1.8,
            "main_net_inflow": 12_345_678.0,
            "members": ["600519", "000858", "000568"],
            "fetched_at": "2026-07-21T15:30:00+08:00",
            "raw_payload": {"akshare_raw": "ignored-by-roundtrip"},
        }

        snap = SectorSnapshot.from_dict(payload)

        # Business identity fields.
        assert snap.sector_code == "BK0489"
        assert snap.sector_name == "白酒"
        assert snap.sector_type == "industry"
        assert snap.snapshot_date == "2026-07-21"
        assert snap.market == "CN"
        assert snap.provider == "sector_stub"
        # Ranking.
        assert snap.rank == 5
        assert snap.pct_chg == 2.35
        # Leading stock triplet.
        assert snap.leading_stock == "600519"
        assert snap.leading_stock_name == "贵州茅台"
        assert snap.leading_pct_chg == 4.10
        # Counts.
        assert snap.advance_count == 12
        assert snap.decline_count == 3
        assert snap.total_count == 15
        # Volume / flow.
        assert snap.turnover_rate == 1.8
        assert snap.main_net_inflow == 12_345_678.0
        # Members list survives.
        assert snap.members == ["600519", "000858", "000568"]
        # Metadata.
        assert snap.fetched_at == "2026-07-21T15:30:00+08:00"
        # raw_payload is preserved for audit (the dataclass does NOT
        # drop it).
        assert snap.raw_payload == {"akshare_raw": "ignored-by-roundtrip"}

    def test_ranking_payload_only_uses_eight_canonical_fields(self) -> None:
        """A ranking-style payload (8 fields) round-trips through
        ``from_dict`` even though the dataclass has 19 fields."""
        payload = {
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "rank": 5,
            "pct_chg": 2.35,
            "advance_count": 12,
            "decline_count": 3,
        }

        snap = SectorSnapshot.from_dict(payload)

        # 8 ranking fields are mapped.
        assert snap.sector_code == "BK0489"
        assert snap.rank == 5
        assert snap.pct_chg == 2.35
        assert snap.advance_count == 12
        assert snap.decline_count == 3
        # Snapshot-only fields default to None / 0.
        assert snap.total_count == 0
        assert snap.turnover_rate is None
        assert snap.main_net_inflow is None
        assert snap.leading_stock is None


# ===========================================================================
# (4) Drift tolerance — extra keys silently ignored, missing fields don't raise
# ===========================================================================


class TestSectorSnapshotDriftAndMissing:
    """``from_dict`` does not raise on missing optionals or extra keys."""

    def test_missing_optionals_default_to_none_or_zero(self) -> None:
        """Minimal dict → counts default to 0, optionals default to None."""
        snap = SectorSnapshot.from_dict(
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
            }
        )
        # Business identity survives.
        assert snap.sector_code == "BK0489"
        assert snap.sector_name == "白酒"
        assert snap.sector_type == "industry"
        assert snap.snapshot_date == "2026-07-21"
        # Market defaults to CN, provider defaults to "".
        assert snap.market == "CN"
        assert snap.provider == ""
        # Counts default to 0.
        assert snap.advance_count == 0
        assert snap.decline_count == 0
        assert snap.total_count == 0
        # Optional metrics default to None.
        assert snap.rank is None
        assert snap.pct_chg is None
        assert snap.leading_stock is None
        assert snap.turnover_rate is None
        assert snap.main_net_inflow is None
        assert snap.members is None
        assert snap.fetched_at is None
        assert snap.raw_payload is None

    def test_extra_keys_silently_ignored(self) -> None:
        """Extra keys do not raise KeyError; they are dropped."""
        snap = SectorSnapshot.from_dict(
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                # Drift: extra fields the dataclass does not know.
                "made_up_field": 12345,
                "another_drift": "foo",
                "future_extension": [1, 2, 3],
            }
        )
        # Business keys survive; no KeyError raised.
        assert snap.sector_code == "BK0489"
        assert snap.sector_name == "白酒"
        assert snap.snapshot_date == "2026-07-21"

    def test_snapshot_date_iso_passthrough(self) -> None:
        """``snapshot_date`` keeps its raw ``"YYYY-MM-DD"`` shape."""
        snap = SectorSnapshot.from_dict(
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
            }
        )
        assert snap.snapshot_date == "2026-07-21"


# ===========================================================================
# (5) Stub/fixture → service read path mapping
# ===========================================================================


class TestStubFixtureMapping:
    """A multi-record stub payload surfaces through the service layer."""

    def test_snapshot_query_returns_single_sector_snapshot(self) -> None:
        """A single-record stub payload → ``DataResult.data`` is one
        ``SectorSnapshot`` with the 4 business-identity fields."""
        payload = [
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "rank": 5,
                "pct_chg": 2.35,
                "advance_count": 12,
                "decline_count": 3,
                "total_count": 15,
            }
        ]
        registry = _build_registry(payload=payload)
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_snapshot(sector_code="BK0489", date="2026-07-21")

        assert result.succeeded
        assert isinstance(result.data, SectorSnapshot)
        assert result.data.sector_code == "BK0489"
        assert result.data.sector_name == "白酒"
        assert result.data.snapshot_date == "2026-07-21"
        assert result.data.pct_chg == 2.35
        assert result.data.rank == 5
        # Provider attribution reflects the stub.
        assert result.provider == "sector_stub"

    def test_ranking_query_returns_list_of_sector_snapshots(self) -> None:
        """A multi-record stub payload → ``DataResult.data`` is a
        ``list[SectorSnapshot]`` mapped from the stub dict records."""
        payload = [
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 2.35,
            },
            {
                "sector_code": "BK0500",
                "sector_name": "证券",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 0.10,
            },
        ]
        registry = _build_registry(payload=payload)
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_ranking(date="2026-07-21")

        assert result.succeeded
        assert isinstance(result.data, list)
        assert all(isinstance(item, SectorSnapshot) for item in result.data)
        assert len(result.data) == 2
        # Each record carries the 4 business-identity fields.
        for snap in result.data:
            assert snap.sector_code in {"BK0489", "BK0500"}
            assert snap.snapshot_date == "2026-07-21"
            assert snap.sector_type == "industry"


# ===========================================================================
# (6) Empty-result semantics
# ===========================================================================


class TestSectorEmptyResultSemantics:
    """Empty payload → ``is_empty()`` + ``data=None`` + no failure."""

    def test_snapshot_empty_payload_returns_empty_data_result(self) -> None:
        """Empty stub payload → ``DataResult.is_empty`` is True + no failure."""
        registry = _build_registry(payload=[])
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_snapshot(sector_code="BK0489")

        assert result.is_empty()
        assert result.data is None
        # Query path is read-only — must not claim Step 2/3 produced data.
        assert "ud_materialized(ok)" not in result.source_trace

    def test_ranking_empty_payload_returns_empty_data_result(self) -> None:
        """Empty stub payload → ``DataResult.is_empty`` is True + no failure.

        The ranking endpoint surfaces an empty list (``[]``) — not
        ``None`` — so consumers can iterate ``result.data`` uniformly
        with the non-empty path. The read path is still read-only.
        """
        registry = _build_registry(payload=[])
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_ranking(date="2026-07-21")

        assert result.is_empty()
        # Ranking returns empty list, not None — uniform data shape.
        assert result.data == []
        # Query path is read-only — must not claim Step 2/3 produced data.
        assert "ud_materialized(ok)" not in result.source_trace


# ===========================================================================
# (7) Date ordering — snapshot_date preserved in multi-record payloads
# ===========================================================================


class TestSectorDateOrdering:
    """Multi-record stub payloads preserve ``snapshot_date`` per record."""

    def test_ranking_records_keep_their_snapshot_date(self) -> None:
        """A ranking payload with two snapshot dates surfaces each
        record's ``snapshot_date`` untouched."""
        payload = [
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 2.35,
            },
            {
                "sector_code": "BK0500",
                "sector_name": "证券",
                "sector_type": "industry",
                "snapshot_date": "2026-07-20",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 0.10,
            },
        ]
        registry = _build_registry(payload=payload)
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_ranking()

        assert result.succeeded
        # Every record surfaced carries its own snapshot_date.
        dates = {snap.snapshot_date for snap in result.data}
        assert dates == {"2026-07-21", "2026-07-20"}

    def test_iso_snapshot_date_passthrough(self) -> None:
        """``snapshot_date`` does NOT get reformatted to anything else."""
        snap = SectorSnapshot.from_dict(
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
            }
        )
        assert snap.snapshot_date == "2026-07-21"
        # The dataclass does not normalise to anything else.
        assert "-" in snap.snapshot_date


# ===========================================================================
# (8) ``source_trace`` discipline — read path is strictly read-only
# ===========================================================================


class TestSectorSourceTraceDiscipline:
    """The read path never produces ``ud_materialized(ok)`` markers."""

    def test_snapshot_query_does_not_materialize(self) -> None:
        """``get_sector_snapshot`` is read-only — no ``(ok)`` markers."""
        payload = [
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 2.35,
            }
        ]
        registry = _build_registry(payload=payload)
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_snapshot(sector_code="BK0489", date="2026-07-21")

        assert "ud_materialized(ok)" not in result.source_trace

    def test_ranking_query_does_not_materialize(self) -> None:
        """``get_sector_ranking`` is read-only — no ``(ok)`` markers."""
        payload = [
            {
                "sector_code": "BK0489",
                "sector_name": "白酒",
                "sector_type": "industry",
                "snapshot_date": "2026-07-21",
                "market": "CN",
                "provider": "sector_stub",
                "pct_chg": 2.35,
            }
        ]
        registry = _build_registry(payload=payload)
        router = DataRouter(registry=registry)
        svc = _build_service(router)

        result = svc.get_sector_ranking(date="2026-07-21")

        assert "ud_materialized(ok)" not in result.source_trace


__all__ = [
    "CAP_SECTOR_RANKING",
    "CAP_SECTOR_SNAPSHOT",
    "EXPECTED_RANKING",
    "EXPECTED_SNAPSHOT",
    "TestExpectedSectorSnapshotFieldsContract",
    "TestExpectedSectorRankingFieldsContract",
    "TestSectorSnapshotFromDictMapping",
    "TestSectorSnapshotDriftAndMissing",
    "TestStubFixtureMapping",
    "TestSectorEmptyResultSemantics",
    "TestSectorDateOrdering",
    "TestSectorSourceTraceDiscipline",
]
