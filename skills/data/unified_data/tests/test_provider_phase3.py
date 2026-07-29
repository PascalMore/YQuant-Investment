"""Phase 3 P3-A AKShareProvider sector-capability tests (T3-C-B, offline).

This module covers the Phase 3 P3-A additions to ``AKShareProvider`` —
the two new capabilities ``sector.snapshot`` and ``sector.ranking``,
plus the STUB_COLUMNS twin-definition equivalence that the upstream
T3-C-A Repair-R2 Review froze (SPEC-03-014 §4.3, DESIGN-03-014 §17.4.2).

What this test suite asserts (all offline — no real AKShare, no
network, no MongoDB):

* ``AKShareProvider.capabilities`` declares the two P3-A capabilities
  alongside the existing Phase 1D 7-capability subset. The set is the
  union of SPEC-03-008 §4.5 + DESIGN-03-014 §17.4.1; no Phase 1D
  capability is regressed, and no extra capability leaks in.
* :meth:`fetch` for ``sector.snapshot`` returns a ``pd.DataFrame`` whose
  ``columns`` list is exactly the SPEC-03-014 §4.3 frozen 12-column
  set, in the exact order documented by ``_stub_columns.STUB_COLUMNS``.
* :meth:`fetch` for ``sector.ranking`` returns a ``pd.DataFrame``
  whose ``columns`` list is exactly the SPEC-03-014 §4.3 frozen
  8-column set, in the exact order documented by
  ``_stub_columns.STUB_COLUMNS``.
* The DataFrame has zero rows on the offline stub path — the contract
  is purely schema-level (DESIGN-03-014 §17.4.2 / §17.1).
* Parameter mapping is permissive: ``sector_code``, ``date``,
  ``sector_type``, ``limit`` and arbitrary ``**params`` are accepted
  without raising (the offline stub does not consume them; T4 is the
  real call path owner).
* Empty / "agreed" exception boundaries are honoured: an undeclared
  capability raises ``UnsupportedCapabilityError``; the two declared
  P3-A capabilities return an empty DataFrame (not a raised
  exception) — the caller (Router / SectorService) decides how to
  interpret the empty payload via ``DataResult.is_empty``.
* STUB_COLUMNS twin-definition equivalence between
  ``providers/_stub_columns.py`` (canonical) and
  ``providers/__init__.py`` (legacy twin) holds for both P3-A
  capabilities — the only ``changed_files`` payload from the T3-C-A
  Repair-R2 deliverable.

What this test suite explicitly does **not** do:

* Make a real AKShare API call (PR-2 smoke is T4's responsibility).
* Touch MongoDB / mongomock / persistence writer / CacheManager
  (those are owned by ``test_sector_service`` and ``test_router_p3_*``).
* Round-trip a ``SectorSnapshot`` dataclass (the column contract is
  capability-specific 12/8, narrower than the dataclass field set —
  SPEC §3.1 / DESIGN §3.1).
"""

from __future__ import annotations

import pandas as pd
import pytest

from skills.data.unified_data.exceptions import UnsupportedCapabilityError
from skills.data.unified_data.models import Market, SecurityId
from skills.data.unified_data.providers import (
    STUB_COLUMNS,
    AKShareProvider,
    stub_dataframe_for,
)
import skills.data.unified_data.providers as providers_package
from skills.data.unified_data.providers import _stub_columns
from skills.data.unified_data.providers.akshare import (
    KLINE_DAILY_CAPABILITY,
    SECTOR_RANKING_CAPABILITY,
    SECTOR_SNAPSHOT_CAPABILITY,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cn_maotai() -> SecurityId:
    """A CN SecurityId — sector capabilities ignore the symbol but the
    provider signature requires one."""
    return SecurityId(market=Market.CN, symbol="600519")


@pytest.fixture
def akshare_provider() -> AKShareProvider:
    """An AKShareProvider instance with no caller-injected ``http_client`` —
    the sector route does not touch the kline client, but constructing
    the provider with default knobs is part of the public API."""
    return AKShareProvider()


# ---------------------------------------------------------------------------
# §1. Capability set
# ---------------------------------------------------------------------------


class TestAKShareProviderCapabilitiesPhase3:
    """Capability registration per DESIGN-03-014 §17.4.1."""

    def test_capabilities_declares_sector_snapshot(self, akshare_provider):
        """``sector.snapshot`` must be in the capability set."""
        caps = akshare_provider.capabilities
        assert SECTOR_SNAPSHOT_CAPABILITY in caps
        # Sanity-check the literal name to defend against constant drift.
        assert "sector.snapshot" in caps

    def test_capabilities_declares_sector_ranking(self, akshare_provider):
        """``sector.ranking`` must be in the capability set."""
        caps = akshare_provider.capabilities
        assert SECTOR_RANKING_CAPABILITY in caps
        # Sanity-check the literal name to defend against constant drift.
        assert "sector.ranking" in caps

    def test_capabilities_preserves_phase_1d_seven(self, akshare_provider):
        """Phase 1D 7-capability subset must NOT regress.

        These seven capabilities come from SPEC-03-008 §4.5 and have
        been declared since Phase 1B-A / 1D. The P3-A addition may not
        remove any of them.
        """
        caps = akshare_provider.capabilities
        phase_1d_required = {
            "market_data.kline_daily",
            "market_data.kline_weekly",
            "market_data.realtime_quote",
            "valuation.daily_basic",
            "calendar.trading_days",
            "calendar.is_trading_day",
            "metadata.stock_list",
        }
        assert phase_1d_required.issubset(caps)

    def test_capabilities_count_is_seven_plus_two(self, akshare_provider):
        """The full capability set is Phase 1D 7 + Phase 3 P3-A 2 = 9."""
        caps = akshare_provider.capabilities
        # AKShare does not expose adj_factor / 3 financial statements /
        # index_members / stock_news (Design §3.3.6), so 9 is the upper
        # bound. The P3-A addition must not regress this count.
        assert len(caps) == 9

    def test_capability_constants_match_string_literals(self):
        """The module-level constants and string literals must agree.

        Guards against a regression where the capability set is updated
        but the constant is left behind (or vice versa).
        """
        assert SECTOR_SNAPSHOT_CAPABILITY == "sector.snapshot"
        assert SECTOR_RANKING_CAPABILITY == "sector.ranking"
        assert KLINE_DAILY_CAPABILITY == "market_data.kline_daily"


# ---------------------------------------------------------------------------
# §2. fetch route — column schema (the core T3-C-B deliverable)
# ---------------------------------------------------------------------------


class TestAKShareProviderSectorFetchSchema:
    """``fetch`` returns a DataFrame whose columns match the frozen
    SPEC-03-014 §4.3 contract, in the exact documented order."""

    def test_fetch_sector_snapshot_returns_12_column_dataframe(
        self, akshare_provider, cn_maotai
    ):
        """``sector.snapshot`` → 12 columns, in canonical order, 0 rows."""
        result = akshare_provider.fetch(
            "sector", "snapshot", cn_maotai
        )
        assert isinstance(result, pd.DataFrame)
        expected = STUB_COLUMNS["sector.snapshot"]
        assert list(result.columns) == expected
        assert len(result.columns) == 12
        assert len(result) == 0  # schema-only contract — no row content

    def test_fetch_sector_ranking_returns_8_column_dataframe(
        self, akshare_provider, cn_maotai
    ):
        """``sector.ranking`` → 8 columns, in canonical order, 0 rows."""
        result = akshare_provider.fetch(
            "sector", "ranking", cn_maotai
        )
        assert isinstance(result, pd.DataFrame)
        expected = STUB_COLUMNS["sector.ranking"]
        assert list(result.columns) == expected
        assert len(result.columns) == 8
        assert len(result) == 0  # schema-only contract — no row content

    def test_fetch_sector_snapshot_column_order_matches_stub_columns(
        self, akshare_provider, cn_maotai
    ):
        """Column order is exactly the frozen SPEC §4.3 sequence.

        The expected order (12 entries):

        1. sector_code
        2. sector_name
        3. sector_type
        4. snapshot_date
        5. rank
        6. pct_chg
        7. leading_stock
        8. advance_count
        9. decline_count
        10. total_count
        11. turnover_rate
        12. main_net_inflow
        """
        result = akshare_provider.fetch(
            "sector", "snapshot", cn_maotai
        )
        expected_order = [
            "sector_code",
            "sector_name",
            "sector_type",
            "snapshot_date",
            "rank",
            "pct_chg",
            "leading_stock",
            "advance_count",
            "decline_count",
            "total_count",
            "turnover_rate",
            "main_net_inflow",
        ]
        assert list(result.columns) == expected_order

    def test_fetch_sector_ranking_column_order_matches_stub_columns(
        self, akshare_provider, cn_maotai
    ):
        """Column order is exactly the frozen SPEC §4.3 sequence.

        The expected order (8 entries):

        1. sector_code
        2. sector_name
        3. sector_type
        4. snapshot_date
        5. rank
        6. pct_chg
        7. advance_count
        8. decline_count
        """
        result = akshare_provider.fetch(
            "sector", "ranking", cn_maotai
        )
        expected_order = [
            "sector_code",
            "sector_name",
            "sector_type",
            "snapshot_date",
            "rank",
            "pct_chg",
            "advance_count",
            "decline_count",
        ]
        assert list(result.columns) == expected_order

    def test_fetch_sector_columns_use_canonical_names_not_19_column_union(
        self, akshare_provider, cn_maotai
    ):
        """The contract is the narrow 12/8 — NOT the 19-column SectorSnapshot
        dataclass field union.

        This is the historical T3-C-A regression guard. The 19-column
        dataclass field union (which includes ``market``, ``provider``,
        ``fetched_at``, ``leading_pct_chg``, ``members``, ``main_net_inflow_ratio``
        etc.) must NOT leak into the capability-specific column schema.
        Specifically::

            sector.snapshot = 12 columns  (NO market / provider / fetched_at / etc.)
            sector.ranking  =  8 columns  (NO market / provider / fetched_at / etc.)
        """
        snapshot_cols = list(
            akshare_provider.fetch("sector", "snapshot", cn_maotai).columns
        )
        ranking_cols = list(
            akshare_provider.fetch("sector", "ranking", cn_maotai).columns
        )
        for forbidden in ("market", "provider", "fetched_at"):
            assert forbidden not in snapshot_cols, (
                f"sector.snapshot leaked forbidden dataclass column {forbidden!r}"
            )
            assert forbidden not in ranking_cols, (
                f"sector.ranking leaked forbidden dataclass column {forbidden!r}"
            )


# ---------------------------------------------------------------------------
# §3. fetch route — parameter mapping
# ---------------------------------------------------------------------------


class TestAKShareProviderSectorParameterMapping:
    """``fetch`` accepts the documented parameter surface without raising.

    T3-C-B is offline: the stub does not consume
    ``sector_code`` / ``date`` / ``sector_type`` / ``limit`` — T4 is
    the real call path owner. The provider's job here is to validate
    the capability and forward kwargs without exploding on
    parameter-shape differences from upstream callers.
    """

    def test_fetch_sector_snapshot_accepts_empty_params(
        self, akshare_provider, cn_maotai
    ):
        """Calling without ``**params`` returns the canonical schema."""
        result = akshare_provider.fetch(
            "sector", "snapshot", cn_maotai
        )
        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) == 12

    def test_fetch_sector_ranking_accepts_empty_params(
        self, akshare_provider, cn_maotai
    ):
        """Calling without ``**params`` returns the canonical schema."""
        result = akshare_provider.fetch(
            "sector", "ranking", cn_maotai
        )
        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) == 8

    def test_fetch_sector_snapshot_accepts_documented_kwargs(
        self, akshare_provider, cn_maotai
    ):
        """``sector_code`` / ``date`` / arbitrary kwargs are accepted
        without raising (DESIGN §17.3.1 / SPEC §5.5 parameter surface).

        The stub does not consume them; this test only verifies the
        provider does not raise on the parameter surface.
        """
        result = akshare_provider.fetch(
            "sector",
            "snapshot",
            cn_maotai,
            sector_code="BK0489",
            date="2026-07-21",
        )
        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) == 12

    def test_fetch_sector_ranking_accepts_documented_kwargs(
        self, akshare_provider, cn_maotai
    ):
        """``date`` / ``sector_type`` / ``limit`` / arbitrary kwargs are
        accepted without raising (DESIGN §17.3.1)."""
        result = akshare_provider.fetch(
            "sector",
            "ranking",
            cn_maotai,
            date="2026-07-21",
            sector_type="industry",
            limit=20,
        )
        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) == 8


# ---------------------------------------------------------------------------
# §4. Empty / "agreed" exception boundaries
# ---------------------------------------------------------------------------


class TestAKShareProviderSectorAgreedBoundaries:
    """The empty / agreed-exception contract for the two P3-A capabilities."""

    def test_fetch_sector_snapshot_empty_dataframe_does_not_raise(
        self, akshare_provider, cn_maotai
    ):
        """Empty payload → empty DataFrame, NOT a raised exception.

        The kline_daily path raises ``ProviderUnavailableError`` on empty
        payload because that path is the real AKShare call path. The
        sector stub path is offline-only and follows the **stub path**
        boundary: an empty (0-row) DataFrame is returned, and the
        caller (Router / SectorService) wraps it as
        ``DataResult.success(data=None, is_empty=True, ...)``.

        Regression guard: the sector stub path must NOT be conflated
        with the kline_daily empty-handling rule.
        """
        result = akshare_provider.fetch(
            "sector", "snapshot", cn_maotai
        )
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_fetch_sector_ranking_empty_dataframe_does_not_raise(
        self, akshare_provider, cn_maotai
    ):
        """Empty payload → empty DataFrame, NOT a raised exception."""
        result = akshare_provider.fetch(
            "sector", "ranking", cn_maotai
        )
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_fetch_undeclared_capability_raises_unsupported(
        self, akshare_provider, cn_maotai
    ):
        """An undeclared capability raises ``UnsupportedCapabilityError``.

        This is the "agreed" boundary that guards the capability
        whitelist — even on the sector stub path, an undeclared
        ``sector.something_else`` is rejected at the provider layer.
        """
        with pytest.raises(UnsupportedCapabilityError):
            akshare_provider.fetch(
                "sector", "not_a_real_capability", cn_maotai
            )


# ---------------------------------------------------------------------------
# §5. STUB_COLUMNS twin-definition equivalence (DESIGN-03-014 §17.4.2)
# ---------------------------------------------------------------------------


class TestStubColumnsTwinDefinitionEquivalence:
    """The canonical ``_stub_columns.STUB_COLUMNS`` and the legacy twin
    in ``providers/__init__.STUB_COLUMNS`` must agree on every
    P3-A capability. This is the byte-level equivalence the upstream
    T3-C-A Repair-R2 Review froze and the cross-file safety net
    Design §17.4.2 requires."""

    def test_canonical_has_p3a_capabilities(self):
        """Canonical ``_stub_columns.STUB_COLUMNS`` carries both P3-A entries."""
        assert "sector.snapshot" in _stub_columns.STUB_COLUMNS
        assert "sector.ranking" in _stub_columns.STUB_COLUMNS

    def test_twin_has_p3a_capabilities(self):
        """Legacy twin ``providers.__init__.STUB_COLUMNS`` carries both P3-A entries."""
        assert "sector.snapshot" in providers_package.STUB_COLUMNS
        assert "sector.ranking" in providers_package.STUB_COLUMNS

    def test_canonical_and_twin_agree_on_sector_snapshot(self):
        """Byte-level equivalence for ``sector.snapshot``."""
        assert (
            _stub_columns.STUB_COLUMNS["sector.snapshot"]
            == providers_package.STUB_COLUMNS["sector.snapshot"]
        )

    def test_canonical_and_twin_agree_on_sector_ranking(self):
        """Byte-level equivalence for ``sector.ranking``."""
        assert (
            _stub_columns.STUB_COLUMNS["sector.ranking"]
            == providers_package.STUB_COLUMNS["sector.ranking"]
        )

    def test_sector_snapshot_twin_columns_match_provider_fetch(self, akshare_provider, cn_maotai):
        """End-to-end equivalence: provider.fetch result.columns ==
        twin STUB_COLUMNS entry == canonical STUB_COLUMNS entry."""
        fetched_cols = list(
            akshare_provider.fetch("sector", "snapshot", cn_maotai).columns
        )
        canonical_cols = _stub_columns.STUB_COLUMNS["sector.snapshot"]
        twin_cols = providers_package.STUB_COLUMNS["sector.snapshot"]
        assert fetched_cols == canonical_cols == twin_cols

    def test_sector_ranking_twin_columns_match_provider_fetch(self, akshare_provider, cn_maotai):
        """End-to-end equivalence: provider.fetch result.columns ==
        twin STUB_COLUMNS entry == canonical STUB_COLUMNS entry."""
        fetched_cols = list(
            akshare_provider.fetch("sector", "ranking", cn_maotai).columns
        )
        canonical_cols = _stub_columns.STUB_COLUMNS["sector.ranking"]
        twin_cols = providers_package.STUB_COLUMNS["sector.ranking"]
        assert fetched_cols == canonical_cols == twin_cols


# ---------------------------------------------------------------------------
# §6. Stub dataframe factory sanity (DESIGN §17.4.2)
# ---------------------------------------------------------------------------


class TestStubDataframeFactorySanity:
    """``stub_dataframe_for`` returns a 0-row DataFrame with the
    canonical 12 / 8 column set, defensively against the provider
    being bypassed or refactored."""

    def test_stub_dataframe_for_sector_snapshot_shape(self):
        df = stub_dataframe_for("sector.snapshot")
        assert isinstance(df, pd.DataFrame)
        assert df.shape == (0, 12)

    def test_stub_dataframe_for_sector_ranking_shape(self):
        df = stub_dataframe_for("sector.ranking")
        assert isinstance(df, pd.DataFrame)
        assert df.shape == (0, 8)

    def test_stub_dataframe_for_sector_snapshot_columns(self):
        df = stub_dataframe_for("sector.snapshot")
        assert list(df.columns) == STUB_COLUMNS["sector.snapshot"]

    def test_stub_dataframe_for_sector_ranking_columns(self):
        df = stub_dataframe_for("sector.ranking")
        assert list(df.columns) == STUB_COLUMNS["sector.ranking"]