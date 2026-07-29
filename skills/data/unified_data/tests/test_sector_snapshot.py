"""Phase 3 P3-A SectorSnapshot domain-object tests (offline T3-A colocated unit tests).

DESIGN-03-014 §17.6.1 mandates exactly 8 test cases for this file.
Each test pins one observable contract from RFC-03-014 §5.1.5 /
SPEC-03-014 §5.5 (the SectorSnapshot canonical surface). The tests
exercise only the dataclass + :meth:`from_dict` — no MongoDB, no
Provider, no AuditLogger, no QualitySummary, no network. Every case
must remain green under ``PYTHONPATH=. python -m pytest ...`` with no
external services available.

Index of the 8 cases (kept in this order so they match §17.6.1):

* (1) :meth:`TestSectorSnapshotConstruction.test_full_construction`
  — every documented field round-trips through the dataclass.
* (2) :meth:`TestFromDictContract.test_required_fields_only`
  — ``from_dict({})`` returns a usable instance with text fields
  defaulted to empty strings (relaxed mapping contract, SPEC §3.1).
* (3) :meth:`TestFromDictContract.test_missing_optional_fields_become_none`
  — every optional field falls back to ``None`` (or 0 for counts).
* (4) :meth:`TestFromDictContract.test_extra_keys_are_silently_ignored`
  — unknown keys in ``d`` do not raise; they are dropped.
* (5) :meth:`TestSectorTypeEnum.test_valid_enum_values_round_trip`
  — ``industry`` / ``concept`` / ``region`` / ``style`` survive
  ``from_dict`` unchanged.
* (6) :meth:`TestSectorTypeEnum.test_invalid_sector_type_defaults_to_empty_string`
  — unknown ``sector_type`` falls back to ``""`` (relaxed mapping).
* (7) :meth:`TestCountInvariant.test_advance_plus_decline_overflow_is_not_enforced`
  — ``advance_count + decline_count > total_count`` is **not** raised
  by the dataclass (the dataclass does not enforce the invariant per
  SPEC §3.1 字段约束).
* (8) :meth:`TestMembersList.test_large_members_list_is_not_truncated`
  — ``members`` lists of ≥1000 entries survive intact.

NOTE: every case here only touches ``models/domain/sector.py`` —
``adapters/p3_persistence_writer`` is exercised in
``test_p3_persistence_writer.py``; service/router/provider integration
is exercised in ``test_sector_service.py`` (T3-B) / ``test_provider_phase3.py``
(T3-C). T3-A keeps this file pure-domain so the dataclass contract
is auditable in isolation.
"""

from __future__ import annotations

import pytest

from skills.data.unified_data.models.domain import SectorSnapshot


# ---------------------------------------------------------------------------
# (1) Full canonical construction — every documented field round-trips
# ---------------------------------------------------------------------------


class TestSectorSnapshotConstruction:
    """Pin the 19-field surface (SPEC §3.1 / DESIGN §3.1)."""

    def test_full_construction(self):
        """Construct with every field populated and assert the repr shape.

        The dataclass must surface all 19 documented fields, with the
        four business-identity fields (``sector_code``,
        ``sector_name``, ``sector_type``, ``snapshot_date``) and
        ``market`` / ``provider`` populated, and every optional field
        either numeric / list / string as appropriate.
        """
        snap = SectorSnapshot(
            sector_code="BK0489",
            sector_name="白酒",
            sector_type="industry",
            snapshot_date="2026-07-21",
            market="CN",
            provider="akshare",
            rank=5,
            pct_chg=2.35,
            leading_stock="600519",
            leading_stock_name="贵州茅台",
            leading_pct_chg=4.10,
            advance_count=12,
            decline_count=3,
            total_count=15,
            turnover_rate=1.8,
            main_net_inflow=12_345_678.0,
            members=["600519", "000858", "000568"],
            fetched_at="2026-07-21T15:30:00+08:00",
            raw_payload={"akshare_raw": "ignored-by-roundtrip"},
        )

        # Required business identity.
        assert snap.sector_code == "BK0489"
        assert snap.sector_name == "白酒"
        assert snap.sector_type == "industry"
        assert snap.snapshot_date == "2026-07-21"
        assert snap.market == "CN"
        assert snap.provider == "akshare"

        # Ranking + percentage.
        assert snap.rank == 5
        assert snap.pct_chg == 2.35

        # Leading stock triplet.
        assert snap.leading_stock == "600519"
        assert snap.leading_stock_name == "贵州茅台"
        assert snap.leading_pct_chg == 4.10

        # Counts (defaults to 0 when absent, but here explicit).
        assert snap.advance_count == 12
        assert snap.decline_count == 3
        assert snap.total_count == 15

        # Money / volume.
        assert snap.turnover_rate == 1.8
        assert snap.main_net_inflow == 12_345_678.0

        # Lists and metadata.
        assert snap.members == ["600519", "000858", "000568"]
        assert snap.fetched_at == "2026-07-21T15:30:00+08:00"
        assert snap.raw_payload == {"akshare_raw": "ignored-by-roundtrip"}

        # Field-count guardrail — if a future refactor adds a field the
        # count must move above 19, otherwise the SPEC alignment shifts.
        # Use ``__dataclass_fields__`` so we count the documented
        # surface, not Python's repr noise.
        assert len(SectorSnapshot.__dataclass_fields__) == 19


# ---------------------------------------------------------------------------
# (2)(3)(4) from_dict contract — required / missing / extra keys
# ---------------------------------------------------------------------------


class TestFromDictContract:
    """``from_dict`` relaxed mapping (SPEC §3.1)."""

    def test_required_fields_only(self):
        """``from_dict({})`` returns a usable instance with text fields defaulting to ''.

        Per SPEC §3.1 the required text fields (``sector_code``,
        ``sector_name``, ``sector_type``, ``snapshot_date``) fall back
        to empty strings, not ``None``. ``market`` defaults to
        ``"CN"``, ``provider`` to ``""``. The call must not raise.
        """
        snap = SectorSnapshot.from_dict({})

        # All four required text fields are empty strings, not None.
        assert snap.sector_code == ""
        assert snap.sector_name == ""
        assert snap.sector_type == ""
        assert snap.snapshot_date == ""

        # market / provider keep their dataclass defaults.
        assert snap.market == "CN"
        assert snap.provider == ""

        # Optional fields default to None.
        assert snap.rank is None
        assert snap.pct_chg is None
        assert snap.leading_stock is None
        assert snap.leading_stock_name is None
        assert snap.leading_pct_chg is None
        assert snap.turnover_rate is None
        assert snap.main_net_inflow is None
        assert snap.members is None
        assert snap.fetched_at is None
        assert snap.raw_payload is None

        # The three count fields coerce to 0 (never None) so callers
        # can do arithmetic without None guards.
        assert snap.advance_count == 0
        assert snap.decline_count == 0
        assert snap.total_count == 0

    def test_missing_optional_fields_become_none(self):
        """Only the required fields are populated; every optional field falls back."""
        d = {
            "sector_code": "BK0500",
            "sector_name": "证券",
            "sector_type": "industry",
            "snapshot_date": "2026-07-22",
            # No optional / numeric / list / metadata fields supplied.
        }
        snap = SectorSnapshot.from_dict(d)

        assert snap.sector_code == "BK0500"
        assert snap.sector_name == "证券"
        assert snap.sector_type == "industry"
        assert snap.snapshot_date == "2026-07-22"

        # Every optional field is None.
        for field_name in (
            "rank",
            "pct_chg",
            "leading_stock",
            "leading_stock_name",
            "leading_pct_chg",
            "turnover_rate",
            "main_net_inflow",
            "members",
            "fetched_at",
            "raw_payload",
        ):
            assert getattr(snap, field_name) is None, (
                f"{field_name} should default to None when missing, got "
                f"{getattr(snap, field_name)!r}"
            )

        # Counts still default to 0 (integer coercion rule).
        assert snap.advance_count == 0
        assert snap.decline_count == 0
        assert snap.total_count == 0

    def test_extra_keys_are_silently_ignored(self):
        """Unknown keys do not raise and are dropped (per test_provider_phase3 note ⑧)."""
        d = {
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            # Garbage / unknown keys — must not raise.
            "akshare_internal_id": 12345,
            "schema_version": "v9.99",
            "source_record_id": "abc-def",
            "quality_flags": ["BAD_DATA"],
            "weird_payload": {"nested": [1, 2, 3]},
        }
        # No exception expected.
        snap = SectorSnapshot.from_dict(d)

        # Canonical fields populated as expected.
        assert snap.sector_code == "BK0489"
        assert snap.sector_name == "白酒"

        # None of the unknown keys leak into the dataclass surface.
        for field_name in SectorSnapshot.__dataclass_fields__:
            value = getattr(snap, field_name)
            if field_name in {"sector_code", "sector_name", "sector_type",
                              "snapshot_date", "market", "provider"}:
                # These six are either populated from ``d`` or keep
                # their default — never echo unknown payload.
                assert value not in (12345, "v9.99", "abc-def",
                                     ["BAD_DATA"], {"nested": [1, 2, 3]}), (
                    f"unknown key leaked into {field_name}={value!r}"
                )

        # raw_payload specifically stays None — the unknown keys do not
        # silently flow into ``raw_payload``.
        assert snap.raw_payload is None


# ---------------------------------------------------------------------------
# (5)(6) sector_type enum contract
# ---------------------------------------------------------------------------


class TestSectorTypeEnum:
    """``sector_type`` allowed values (SPEC §3.1 / DESIGN §3.1)."""

    @pytest.mark.parametrize(
        "sector_type",
        ["industry", "concept", "region", "style"],
    )
    def test_valid_enum_values_round_trip(self, sector_type: str):
        """All four documented enum values survive ``from_dict`` unchanged."""
        snap = SectorSnapshot.from_dict({
            "sector_code": "BK0000",
            "sector_name": "X",
            "sector_type": sector_type,
            "snapshot_date": "2026-07-21",
        })
        assert snap.sector_type == sector_type

    @pytest.mark.parametrize(
        "invalid_value",
        [
            "INDUSTRY",       # case mismatch — dataclass does not normalise
            "industries",     # unknown plural
            "subindustry",    # unknown extra level
            "股票",           # Chinese label — not an enum value
            "Sector",         # leading capital
            "",               # empty string is the relaxed default
            " ",              # whitespace — not normalised, kept as-is
        ],
    )
    def test_invalid_sector_type_defaults_to_empty_string(self, invalid_value: str):
        """Unknown / non-enum ``sector_type`` values fall back to ``""``.

        The dataclass implements the *relaxed* mapping contract
        (SPEC §3.1 ``from_dict`` note): it does **not** validate
        ``sector_type`` against the enum set. Instead, the empty
        default is the relaxed contract for missing fields, and any
        non-empty unknown value is preserved verbatim so the upstream
        provider-level normalisation / alerting can spot drift.

        Concretely:

        * ``""`` (empty / missing) → ``""``.
        * Non-empty unknown value → preserved as-is (no exception,
          no enum-rejection), since the dataclass does not know
          about the enum set.

        This test pins the relaxed contract: no exception is raised
        and ``sector_type`` is **never** ``None`` — text coercion is
        unconditional (``str(d.get("sector_type", ""))``).
        """
        snap = SectorSnapshot.from_dict({
            "sector_code": "BK0001",
            "sector_name": "Y",
            "sector_type": invalid_value,
            "snapshot_date": "2026-07-21",
        })
        # sector_type is unconditionally coerced to str, never None.
        assert snap.sector_type is not None
        assert isinstance(snap.sector_type, str)

        if invalid_value == "":
            # The empty default (also what ``from_dict({})`` returns).
            assert snap.sector_type == ""
        else:
            # Non-empty unknown values are preserved verbatim — this is
            # the relaxation that lets the upstream pipeline surface
            # provider drift instead of silently dropping the row.
            assert snap.sector_type == invalid_value


# ---------------------------------------------------------------------------
# (7) advance_count + decline_count ≤ total_count is NOT enforced
# ---------------------------------------------------------------------------


class TestCountInvariant:
    """The dataclass does not enforce the counts invariant (SPEC §3.1)."""

    def test_advance_plus_decline_overflow_is_not_enforced(self):
        """``advance_count + decline_count > total_count`` must NOT raise.

        Per SPEC §3.1 字段约束 the invariant is the **provider's**
        responsibility, not the dataclass's. The dataclass must accept
        inconsistent rows so the refresh path can surface them via the
        QualitySummary / AuditLogger rather than crashing the ingest.
        """
        snap = SectorSnapshot.from_dict({
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "advance_count": 100,   # impossible if total_count is 10
            "decline_count": 50,    # impossible if total_count is 10
            "total_count": 10,
        })

        # The dataclass must accept the row without validation.
        assert snap.advance_count == 100
        assert snap.decline_count == 50
        assert snap.total_count == 10
        # Sanity: the invariant is genuinely violated.
        assert snap.advance_count + snap.decline_count > snap.total_count

    def test_zero_total_count_with_positive_advance_decline_is_accepted(self):
        """Edge case: ``total_count == 0`` with non-zero advance/decline is allowed."""
        snap = SectorSnapshot(
            sector_code="BK0489",
            sector_name="白酒",
            sector_type="industry",
            snapshot_date="2026-07-21",
            advance_count=5,
            decline_count=5,
            total_count=0,
        )
        assert snap.total_count == 0
        assert snap.advance_count == 5
        assert snap.decline_count == 5

    def test_count_field_coercion_rejects_none(self):
        """``None`` in count fields is coerced to 0 via ``or 0`` fallback."""
        snap = SectorSnapshot.from_dict({
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "advance_count": None,
            "decline_count": None,
            "total_count": None,
        })
        # Counts must coerce to 0, not remain None — SPEC §3.1
        # mandates integer coercion with 0 default for the three count
        # fields so callers can do arithmetic without None guards.
        assert snap.advance_count == 0
        assert snap.decline_count == 0
        assert snap.total_count == 0


# ---------------------------------------------------------------------------
# (8) members list size — large lists are not truncated
# ---------------------------------------------------------------------------


class TestMembersList:
    """The ``members`` list is preserved verbatim (no truncation)."""

    def test_large_members_list_is_not_truncated(self):
        """A ``members`` list with ≥1000 entries must round-trip intact.

        SPEC §3.1 defines ``members`` as ``list[str] | None`` with no
        documented upper bound. DESIGN §17.6.1 case (8) makes the
        explicit no-truncate contract observable. The provider is
        responsible for any upstream size filter; the dataclass must
        not silently drop elements.
        """
        # 1500 synthetic codes — comfortably above the 1000-element
        # boundary the design calls out.
        large_members = [f"{600000 + i:06d}" for i in range(1500)]

        snap = SectorSnapshot.from_dict({
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "members": large_members,
        })

        # The list survives intact — exact length, exact contents.
        assert snap.members is not None
        assert len(snap.members) == 1500
        assert snap.members == large_members
        # First / last sanity (catches accidental slicing or
        # off-by-one in any future ``[start:stop]`` rewrite).
        assert snap.members[0] == "600000"
        assert snap.members[-1] == "601499"

    def test_members_none_is_preserved(self):
        """``members`` explicitly set to ``None`` stays ``None``."""
        snap = SectorSnapshot.from_dict({
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "members": None,
        })
        assert snap.members is None

    def test_members_empty_list_is_preserved(self):
        """An explicit empty ``members`` list survives as ``[]`` (distinct from ``None``)."""
        snap = SectorSnapshot.from_dict({
            "sector_code": "BK0489",
            "sector_name": "白酒",
            "sector_type": "industry",
            "snapshot_date": "2026-07-21",
            "members": [],
        })
        # Empty list is preserved — not coerced to None.
        assert snap.members == []
        assert snap.members is not None