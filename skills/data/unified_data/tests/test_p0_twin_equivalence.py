"""Phase 3 P0 _EXPECTED_*_FIELDS twin-definition equivalence tests.

This module pins the **byte-level equivalence** between the canonical
``providers/_stub_columns.py`` constants and the legacy twin in
``providers/__init__.py`` for the six Phase-3 capabilities:

* ``_EXPECTED_SECTOR_SNAPSHOT_FIELDS``  (PA-1)
* ``_EXPECTED_SECTOR_RANKING_FIELDS``   (PA-2)
* ``_EXPECTED_FLOW_FIELDS``             (PB-1)
* ``_EXPECTED_NORTHBOUND_FIELDS``       (PB-2)
* ``_EXPECTED_SENTIMENT_FIELDS``        (PC-1)
* ``_EXPECTED_LIMIT_UP_FIELDS``         (PC-2)

DESIGN-03-014 §P0.8.1 #13 requires the twin-definition equivalence so a
future divergence between the canonical source and the legacy mirror
fails loudly at the test layer.

The test does **not** allow partial coverage — every expected-set must
be present in both modules, every entry must match the canonical
ordering (frozen), and a divergence in any of the six sets aborts the
whole module.

All tests are offline: no real MongoDB / AKShare / network access.
"""

from __future__ import annotations

import pytest

from skills.data.unified_data import providers as providers_package
from skills.data.unified_data.providers import _stub_columns


# ---------------------------------------------------------------------------
# Set of expected-set constants the test layer must cover (PA-1 / PA-2 /
# PB-1 / PB-2 / PC-1 / PC-2).  Names match the constants exported by the
# production modules.
# ---------------------------------------------------------------------------

EXPECTED_SET_NAMES = (
    "_EXPECTED_SECTOR_SNAPSHOT_FIELDS",
    "_EXPECTED_SECTOR_RANKING_FIELDS",
    "_EXPECTED_FLOW_FIELDS",
    "_EXPECTED_NORTHBOUND_FIELDS",
    "_EXPECTED_SENTIMENT_FIELDS",
    "_EXPECTED_LIMIT_UP_FIELDS",
)


# ===========================================================================
# Twin-definition presence
# ===========================================================================


class TestExpectedSetPresence:
    """Both modules must declare every one of the six expected-set constants."""

    @pytest.mark.parametrize("name", EXPECTED_SET_NAMES)
    def test_canonical_module_declares(self, name: str) -> None:
        assert hasattr(_stub_columns, name), (
            f"canonical source `providers/_stub_columns.py` must declare "
            f"{name!r} per DESIGN-03-014 §P0.3.3 / §P0.4.3 / §P0.5.3"
        )

    @pytest.mark.parametrize("name", EXPECTED_SET_NAMES)
    def test_twin_module_declares(self, name: str) -> None:
        assert hasattr(providers_package, name), (
            f"legacy twin `providers/__init__.py` must mirror {name!r} "
            f"per DESIGN-03-014 §P0.3.3 / §P0.4.3 / §P0.5.3"
        )


# ===========================================================================
# Byte-level equivalence (frozen order + frozen membership)
# ===========================================================================


class TestExpectedSetTwinEquivalence:
    """The canonical and the twin module must agree on every expected-set.

    Both ordering and membership are pinned. A future divergence must
    fail loudly rather than silently drift the legacy twin.
    """

    @pytest.mark.parametrize("name", EXPECTED_SET_NAMES)
    def test_canonical_and_twin_agree_on_ordered_tuple(self, name: str) -> None:
        canonical_value = getattr(_stub_columns, name)
        twin_value = getattr(providers_package, name)
        # The twin must equal the canonical — including order. We use
        # tuple/list equality so a reorder fails loudly.
        assert canonical_value == twin_value, (
            f"{name} twin-definition mismatch.\n"
            f"  canonical ({type(canonical_value).__name__}): {canonical_value}\n"
            f"  twin      ({type(twin_value).__name__}): {twin_value}"
        )

    @pytest.mark.parametrize("name", EXPECTED_SET_NAMES)
    def test_expected_set_is_indexable_sequence(self, name: str) -> None:
        """The expected-set must support ``__len__`` / ``__getitem__``.

        Both tuples and lists qualify; sets do NOT (they're unordered
        and would defeat the frozen-order contract). The test pins the
        sequence type so a future "let's use a set" refactor fails
        here.
        """
        value = getattr(_stub_columns, name)
        assert hasattr(value, "__getitem__"), (
            f"{name} must be an indexable sequence (tuple or list)"
        )
        assert hasattr(value, "__iter__"), (
            f"{name} must be iterable"
        )
        # ``set`` is excluded: a set cannot preserve field order.
        assert not isinstance(value, set), (
            f"{name} must not be a set — frozen field order is part of "
            f"the canonical contract"
        )


# ===========================================================================
# Per-set content sanity (does NOT depend on provider fetch — purely static)
# ===========================================================================


class TestExpectedSetContentSanity:
    """Static sanity checks on the six expected-sets.

    These tests do not touch the production providers or stub fixtures;
    they only assert content invariants that must hold across the whole
    set of six tuples.
    """

    def test_northbound_set_has_exactly_three_fields(self) -> None:
        """PB-2: ``_EXPECTED_NORTHBOUND_FIELDS`` is exactly 3 fields."""
        northbound = getattr(_stub_columns, "_EXPECTED_NORTHBOUND_FIELDS")
        assert len(northbound) == 3, (
            f"_EXPECTED_NORTHBOUND_FIELDS must have exactly 3 fields "
            f"per PB-2; got {len(northbound)}: {list(northbound)}"
        )

    def test_northbound_set_carries_documented_field_names(self) -> None:
        """PB-2: the three field names match Pascal C fail-stop contract."""
        northbound = set(
            getattr(_stub_columns, "_EXPECTED_NORTHBOUND_FIELDS")
        )
        expected = {
            "northbound_net_inflow",
            "northbound_hold_shares",
            "northbound_hold_ratio",
        }
        assert northbound == expected, (
            f"northbound set mismatch: missing "
            f"{expected - northbound}, extra "
            f"{northbound - expected}"
        )

    def test_flow_set_includes_required_business_key_fields(self) -> None:
        """PB-1: ``_EXPECTED_FLOW_FIELDS`` must include the 10 baseline fields.

        Per SPEC-03-014 V0.18 §P0.4.1 / DESIGN-03-014 V0.25 §P0.4.1, the
        baseline set covers ``symbol``, ``market``, ``trade_date`` and
        the four flow bands (``main_net_inflow``,
        ``super_large_net_inflow``, ``large_net_inflow``,
        ``medium_net_inflow``, ``small_net_inflow``,
        ``main_net_inflow_ratio``, ``margin_balance``) — 10 fields
        minimum.
        """
        flow = set(getattr(_stub_columns, "_EXPECTED_FLOW_FIELDS"))
        required = {
            "symbol",
            "market",
            "trade_date",
            "main_net_inflow",
            "super_large_net_inflow",
            "large_net_inflow",
            "medium_net_inflow",
            "small_net_inflow",
            "main_net_inflow_ratio",
            "margin_balance",
        }
        missing = required - flow
        assert not missing, (
            f"_EXPECTED_FLOW_FIELDS must include the 10 baseline fields "
            f"per PB-1; missing: {sorted(missing)}"
        )

    def test_sector_snapshot_carries_required_baseline_fields(self) -> None:
        """PA-1: ``_EXPECTED_SECTOR_SNAPSHOT_FIELDS`` baseline coverage.

        Per DESIGN-03-014 §P0.3.1 the baseline must include sector
        code / name / type / date / pct_chg / advance / decline /
        leading / turnover.
        """
        snapshot = set(
            getattr(_stub_columns, "_EXPECTED_SECTOR_SNAPSHOT_FIELDS")
        )
        required = {
            "sector_code",
            "sector_name",
            "sector_type",
            "snapshot_date",
            "pct_chg",
            "advance_count",
            "decline_count",
            "leading_stock",
            "turnover_rate",
        }
        missing = required - snapshot
        assert not missing, (
            f"_EXPECTED_SECTOR_SNAPSHOT_FIELDS baseline coverage missing: "
            f"{sorted(missing)}"
        )

    def test_sector_ranking_is_strict_subset_of_sector_snapshot(self) -> None:
        """PA-2: ranking fields must be a subset of the snapshot set.

        The ranking capability (8 columns) is documented as a narrower
        view of the snapshot (12 columns). Pin this so the two
        expected-sets cannot accidentally invert.
        """
        snapshot = set(
            getattr(_stub_columns, "_EXPECTED_SECTOR_SNAPSHOT_FIELDS")
        )
        ranking = set(
            getattr(_stub_columns, "_EXPECTED_SECTOR_RANKING_FIELDS")
        )
        assert ranking.issubset(snapshot), (
            f"_EXPECTED_SECTOR_RANKING_FIELDS must be a subset of "
            f"_EXPECTED_SECTOR_SNAPSHOT_FIELDS; "
            f"ranking-only fields: {ranking - snapshot}"
        )

    def test_sentiment_set_matches_market_sentiment_snapshot_dataclass(self) -> None:
        """PC-1: sentiment expected-set matches the 22-field canonical dataclass.

        Per SPEC-03-014 V0.15 / DESIGN-03-014 V0.23 §3.3, the canonical
        contract is exactly 22 fields. The expected-set must mirror the
        dataclass field set so a divergence breaks the P0 contract.
        """
        from skills.data.unified_data.models.domain.sentiment import (
            MarketSentimentSnapshot,
        )

        dataclass_fields = set(MarketSentimentSnapshot.__dataclass_fields__)
        expected = set(
            getattr(_stub_columns, "_EXPECTED_SENTIMENT_FIELDS")
        )
        assert dataclass_fields == expected, (
            f"sentiment expected-set mismatch with dataclass.\n"
            f"  dataclass has {len(dataclass_fields)} fields: "
            f"{sorted(dataclass_fields)}\n"
            f"  expected has {len(expected)} fields: "
            f"{sorted(expected)}\n"
            f"  dataclass-only: {sorted(dataclass_fields - expected)}\n"
            f"  expected-only:  {sorted(expected - dataclass_fields)}"
        )

    def test_limit_up_set_matches_limit_up_pool_record_dataclass(self) -> None:
        """PC-2: limit-up expected-set matches the ``LimitUpPoolRecord`` dataclass."""
        from skills.data.unified_data.models.domain.sentiment import (
            LimitUpPoolRecord,
        )

        dataclass_fields = set(LimitUpPoolRecord.__dataclass_fields__)
        expected = set(
            getattr(_stub_columns, "_EXPECTED_LIMIT_UP_FIELDS")
        )
        assert dataclass_fields == expected, (
            f"limit-up expected-set mismatch with dataclass.\n"
            f"  dataclass has {len(dataclass_fields)} fields: "
            f"{sorted(dataclass_fields)}\n"
            f"  expected has {len(expected)} fields: "
            f"{sorted(expected)}\n"
            f"  dataclass-only: {sorted(dataclass_fields - expected)}\n"
            f"  expected-only:  {sorted(expected - dataclass_fields)}"
        )

    def test_no_expected_set_references_superseded_sentiment_fields(self) -> None:
        """No expected-set may reference the superseded 10-field model fields.

        Per SPEC-03-014 V0.15 §12.bis.3 the legacy
        ``sentiment_type`` / ``market_date`` / ``score`` /
        ``sample_size`` / ``source`` / ``notes`` / ``metadata`` /
        ``market_date`` field names are superseded by the 22-field
        canonical contract. Pin their absence so a regression cannot
        silently restore the legacy model.
        """
        legacy_names = {
            "sentiment_type",
            "market_date",
            "score",
            "sample_size",
            "source",
            "notes",
            "metadata",
        }
        for name in EXPECTED_SET_NAMES:
            if name == "_EXPECTED_LIMIT_UP_FIELDS":
                # Limit-up pool uses ``provider`` (non-legacy); the
                # other legacy names don't apply. Pin only the
                # specifically-superseded sentiment fields here.
                continue
            value = set(getattr(_stub_columns, name))
            overlap = value & legacy_names
            assert not overlap, (
                f"{name} references superseded 10-field names: "
                f"{sorted(overlap)}"
            )


__all__ = [
    "EXPECTED_SET_NAMES",
    "TestExpectedSetPresence",
    "TestExpectedSetTwinEquivalence",
    "TestExpectedSetContentSanity",
]
