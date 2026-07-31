"""P3-A Sector Provider activation tests — offline, fake-transport only.

Covers DESIGN-03-014-p3a §5.1 UT-SA-201..215 and SPEC-03-014 §5.3
offline test coverage (F-048..F-053):

* endpoint selection (snapshot → name_em + filter; ranking → name_em
  full) — via :class:`FakeSectorClient` call_log.
* canonical field mapping (Chinese columns → SectorSnapshot fields).
* empty-set semantics (empty DataFrame → empty result, no raise).
* exception handling (SSLError / ConnectionError / TimeoutError /
  ProviderError injected via FakeSectorClient → surfaced to the
  Router/consumer as trace entries; the provider propagates
  Provider*Error per the SectorClient contract).
* sector_type routing (industry / concept / unsupported).
* stub path regression (no injected client → 0-row stub DataFrame).
* snapshot filtering (multi-board fixture → single board).
* call_log verification.
* snapshot_date injection (params["date"] preferred; fetch date fallback).
* 禁止编造 (total_count / main_net_inflow / members → None).

Every test is fully offline: no real AKShare call, no network, no
MongoDB, no environment reads.
"""

from __future__ import annotations

import datetime
from typing import Any

import pandas as pd
import pytest

from skills.data.unified_data.exceptions import ProviderError, ProviderUnavailableError
from skills.data.unified_data.models import Market, SecurityId
from skills.data.unified_data.models.domain.sector import SectorSnapshot
from skills.data.unified_data.providers import STUB_COLUMNS
from skills.data.unified_data.providers.akshare import (
    AKShareProvider,
    SECTOR_RANKING_CAPABILITY,
    SECTOR_SNAPSHOT_CAPABILITY,
)
from skills.data.unified_data.providers.sector_client import (
    AKShareSectorClient,
    FakeSectorClient,
)
from skills.data.unified_data.tests.fixtures.sector_activation_fixtures import (
    _default_industry_ranking_df,
    _empty_ranking_df,
)


CN_MAOTAI = SecurityId(market=Market.CN, symbol="600519")


def _provider_with_client(
    *,
    ranking_df: pd.DataFrame | None = None,
    snapshot_df: pd.DataFrame | None = None,
    exception: BaseException | None = None,
) -> tuple[AKShareProvider, FakeSectorClient]:
    """Build an AKShareProvider with an injected FakeSectorClient."""
    client = FakeSectorClient(
        ranking_df=ranking_df,
        snapshot_df=snapshot_df,
        exception=exception,
    )
    provider = AKShareProvider(sector_client=client)
    return provider, client


# ===================================================================
# UT-SA-201 / UT-SA-202 — success paths
# ===================================================================


class TestSectorSnapshotSuccess:
    def test_snapshot_success_path_returns_list_of_dicts(self):
        """UT-SA-201: injected industry fixture → fetch snapshot returns
        SectorSnapshot-compatible list[dict] with correct single row."""
        fixture = _default_industry_ranking_df()
        provider, client = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "snapshot", CN_MAOTAI,
            sector_code="BK0489", sector_type="industry", date="2026-07-21",
        )

        assert isinstance(result, list)
        assert len(result) == 1
        record = result[0]
        assert record["sector_code"] == "BK0489"
        assert record["sector_name"] == "白酒"
        assert record["sector_type"] == "industry"
        assert record["snapshot_date"] == "2026-07-21"
        assert record["market"] == "CN"
        assert record["provider"] == "akshare"
        assert record["rank"] == 1
        assert record["pct_chg"] == 3.21
        assert record["advance_count"] == 18
        assert record["decline_count"] == 2
        assert record["leading_stock"] == "贵州茅台"
        assert record["leading_pct_chg"] == 5.67
        assert record["turnover_rate"] == 2.35
        # 禁止编造
        assert record["total_count"] is None
        assert record["main_net_inflow"] is None
        assert record["leading_stock_name"] is None
        assert record["members"] is None
        assert record["fetched_at"] is not None
        assert "raw_payload" in record

        # Round-trips through the canonical dataclass.
        snap = SectorSnapshot.from_dict(record)
        assert snap.sector_code == "BK0489"
        assert snap.snapshot_date == "2026-07-21"

        # The client was called exactly once with the right args.
        assert len(client.call_log) == 1
        assert client.call_log[0]["method"] == "snapshot"
        assert client.call_log[0]["sector_code"] == "BK0489"
        assert client.call_log[0]["sector_type"] == "industry"

    def test_ranking_success_path_returns_list_of_dicts(self):
        """UT-SA-202: injected industry fixture → fetch ranking returns
        list[dict] for every board."""
        fixture = _default_industry_ranking_df()
        provider, client = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "ranking", CN_MAOTAI,
            sector_type="industry", date="2026-07-21",
        )

        assert isinstance(result, list)
        assert len(result) == 5
        codes = {r["sector_code"] for r in result}
        assert codes == {"BK0489", "BK0473", "BK1036", "BK0438", "BK0733"}

        # Ranking shape is the narrow 8-column subset.
        first = result[0]
        assert set(first.keys()) >= {
            "sector_code", "sector_name", "sector_type", "snapshot_date",
            "rank", "pct_chg", "advance_count", "decline_count",
            "market", "provider",
        }
        # Ranking rows do NOT carry snapshot-only fields.
        assert "turnover_rate" not in first
        assert "leading_stock" not in first
        assert "total_count" not in first
        assert "main_net_inflow" not in first

        # Round-trips through the canonical dataclass.
        snaps = [SectorSnapshot.from_dict(r) for r in result]
        assert all(s.snapshot_date == "2026-07-21" for s in snaps)

        assert len(client.call_log) == 1
        assert client.call_log[0]["method"] == "ranking"
        assert client.call_log[0]["sector_type"] == "industry"


# ===================================================================
# UT-SA-203 — snapshot filtering
# ===================================================================


class TestSectorSnapshotFiltering:
    def test_snapshot_filters_multi_board_fixture(self):
        """UT-SA-203: 5-board fixture → snapshot BK0489 returns exactly 1."""
        fixture = _default_industry_ranking_df()
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "snapshot", CN_MAOTAI, sector_code="BK0489",
        )
        assert len(result) == 1
        assert result[0]["sector_code"] == "BK0489"

    def test_snapshot_missing_board_returns_empty(self):
        """Snapshot for an unknown sector_code → empty list (no raise)."""
        fixture = _default_industry_ranking_df()
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "snapshot", CN_MAOTAI, sector_code="BK9999",
        )
        assert isinstance(result, list)
        assert result == []


# ===================================================================
# UT-SA-204 — field mapping correctness
# ===================================================================


class TestSectorFieldMapping:
    def test_chinese_columns_map_to_canonical_fields(self):
        """UT-SA-204: Chinese column names → canonical English fields."""
        fixture = _default_industry_ranking_df()
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "ranking", CN_MAOTAI, sector_type="industry",
            date="2026-07-21",
        )
        by_code = {r["sector_code"]: r for r in result}

        assert by_code["BK0473"]["sector_name"] == "证券"
        assert by_code["BK0473"]["rank"] == 5
        assert by_code["BK0473"]["pct_chg"] == 1.45
        assert by_code["BK1036"]["advance_count"] == 42
        assert by_code["BK1036"]["decline_count"] == 33
        assert by_code["BK0438"]["pct_chg"] == -0.50

    def test_string_numeric_coercion_tolerated(self):
        """F-029: string numeric cells ('3.21%') coerce via _safe_float."""
        from skills.data.unified_data.providers.akshare import (
            _safe_float,
            _safe_int,
        )

        assert _safe_float("3.21%") == 3.21
        assert _safe_float("1,234.50") == 1234.5
        assert _safe_float("abc") is None
        assert _safe_float(None) is None
        assert _safe_int("18") == 18
        assert _safe_int("18.9") == 18
        assert _safe_int("abc") == 0
        assert _safe_int(None) == 0

    def test_missing_optional_column_does_not_raise(self):
        """F-026 / A-DRIFT-3: expected column missing → None/0, no KeyError."""
        fixture = _default_industry_ranking_df().drop(columns=["换手率", "领涨股票-涨跌幅"])
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "snapshot", CN_MAOTAI, sector_code="BK0489",
        )
        assert len(result) == 1
        assert result[0]["turnover_rate"] is None
        assert result[0]["leading_pct_chg"] is None

    def test_extra_unmapped_columns_silently_ignored(self):
        """F-025 / A-DRIFT-2: unmapped columns (最新价/涨跌额/总市值) ignored."""
        fixture = _default_industry_ranking_df()
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "snapshot", CN_MAOTAI, sector_code="BK0489",
        )
        record = result[0]
        # No canonical key leaks the unmapped AKShare columns.
        assert "最新价" not in record
        assert "涨跌额" not in record
        assert "总市值" not in record

    def test_required_text_fields_empty_skips_row(self):
        """F-028: row with empty sector_code / sector_name is skipped."""
        fixture = _default_industry_ranking_df()
        fixture.loc[len(fixture)] = [
            99, "", "", 1.0, 0.0, 0.0, 1.0, 0.0, 0, 0, "", 0.0,
        ]
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "ranking", CN_MAOTAI, sector_type="industry",
        )
        assert len(result) == 5  # the blank row is dropped


# ===================================================================
# UT-SA-205 — empty-set handling
# ===================================================================


class TestSectorEmptySet:
    def test_snapshot_empty_dataframe_returns_empty_list(self):
        """UT-SA-205: FakeSectorClient returns empty DataFrame → []."""
        provider, _ = _provider_with_client(ranking_df=_empty_ranking_df())

        result = provider.fetch(
            "sector", "snapshot", CN_MAOTAI, sector_code="BK0489",
        )
        assert isinstance(result, list)
        assert result == []

    def test_ranking_empty_dataframe_returns_empty_list(self):
        provider, _ = _provider_with_client(ranking_df=_empty_ranking_df())

        result = provider.fetch(
            "sector", "ranking", CN_MAOTAI, sector_type="industry",
        )
        assert isinstance(result, list)
        assert result == []


# ===================================================================
# UT-SA-206..208 — exception handling
# ===================================================================


class TestSectorExceptions:
    @pytest.mark.parametrize(
        ("exc", "exc_type"),
        [
            (ConnectionError("connection reset"), ProviderUnavailableError),
            (TimeoutError("timed out"), ProviderUnavailableError),
            (ProviderError("API internal error"), ProviderError),
            (ProviderUnavailableError("quota"), ProviderUnavailableError),
        ],
    )
    def test_client_exception_propagates(self, exc, exc_type):
        """UT-SA-206/207/208: SSLError/ConnectionError/TimeoutError
        injected via FakeSectorClient propagate as Provider*Error so the
        Router surfaces them via source_trace."""
        provider, _ = _provider_with_client(exception=exc)

        with pytest.raises(exc_type):
            provider.fetch("sector", "snapshot", CN_MAOTAI, sector_code="BK0489")

    def test_ssl_error_classified_as_provider_unavailable(self):
        """SSLError (subclass of OSError, not ConnectionError) is a
        connection-level failure the Router must treat as unavailable."""
        import ssl

        provider, _ = _provider_with_client(exception=ssl.SSLError("certificate verify failed"))
        with pytest.raises(ProviderUnavailableError):
            provider.fetch("sector", "snapshot", CN_MAOTAI, sector_code="BK0489")

    def test_unsupported_sector_type_raises_provider_error(self):
        """UT-SA-211: sector_type='region' → ProviderError (only
        industry / concept supported by the client)."""
        provider, _ = _provider_with_client(ranking_df=_default_industry_ranking_df())

        with pytest.raises(ProviderError, match="unsupported sector_type"):
            provider.fetch(
                "sector", "ranking", CN_MAOTAI, sector_type="region",
            )


# ===================================================================
# UT-SA-209 / UT-SA-210 — sector_type routing
# ===================================================================


class TestSectorTypeRouting:
    def test_industry_routing_recorded_in_call_log(self):
        """UT-SA-209: sector_type=industry flows to the client."""
        fixture = _default_industry_ranking_df()
        provider, client = _provider_with_client(ranking_df=fixture)

        provider.fetch(
            "sector", "ranking", CN_MAOTAI, sector_type="industry",
        )
        assert client.call_log[0]["sector_type"] == "industry"

    def test_concept_routing_recorded_in_call_log(self):
        """UT-SA-210: sector_type=concept flows to the client (endpoint
        routing decision is at client layer — industry/concept share the
        Provider mapping path)."""
        fixture = _default_industry_ranking_df()
        provider, client = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "ranking", CN_MAOTAI, sector_type="concept",
        )
        assert isinstance(result, list)
        assert len(result) == 5
        assert client.call_log[0]["sector_type"] == "concept"


# ===================================================================
# UT-SA-212 — stub path regression (no injected client)
# ===================================================================


class TestSectorStubPathRegression:
    def test_snapshot_without_client_returns_stub_dataframe(self):
        """UT-SA-212: no injected SectorClient → sector.snapshot returns
        the canonical 0-row stub DataFrame (backward compatible)."""
        provider = AKShareProvider()
        result = provider.fetch("sector", "snapshot", CN_MAOTAI, sector_code="BK0489")
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == STUB_COLUMNS["sector.snapshot"]
        assert len(result) == 0

    def test_ranking_without_client_returns_stub_dataframe(self):
        provider = AKShareProvider()
        result = provider.fetch("sector", "ranking", CN_MAOTAI, sector_type="industry")
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == STUB_COLUMNS["sector.ranking"]
        assert len(result) == 0


# ===================================================================
# UT-SA-213 — lazy client construction semantics
# ===================================================================


class TestSectorLazyClient:
    def test_sector_client_not_constructed_on_init(self):
        """UT-SA-213: sector_client=None → no client constructed during
        __init__ (no akshare import, no I/O)."""
        provider = AKShareProvider()
        assert provider._sector_client is None

    def test_injected_client_used_as_is(self):
        """The injected FakeSectorClient is used without re-construction."""
        fixture = _default_industry_ranking_df()
        client = FakeSectorClient(ranking_df=fixture)
        provider = AKShareProvider(sector_client=client)
        assert provider._sector_client is client

    def test_akshare_sector_client_lazy_import(self, monkeypatch):
        """AKShareSectorClient defers the SDK import until _call_name_em.

        Construction must not import akshare; the import happens inside
        the method. We assert the module imports without touching the
        SDK by checking construction succeeds and the endpoint name
        constants exist.
        """
        client = AKShareSectorClient(timeout=5.0)
        assert client._INDUSTRY_FN_NAME == "stock_board_industry_name_em"
        assert client._CONCEPT_FN_NAME == "stock_board_concept_name_em"


# ===================================================================
# UT-SA-214 — snapshot_date injection
# ===================================================================


class TestSectorSnapshotDate:
    def test_params_date_preferred(self):
        """UT-SA-214: params['date'] wins over fetch date."""
        fixture = _default_industry_ranking_df()
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "snapshot", CN_MAOTAI,
            sector_code="BK0489", date="2026-07-21",
        )
        assert result[0]["snapshot_date"] == "2026-07-21"

    def test_fetch_date_fallback(self):
        """UT-SA-214: no params['date'] → today's date is used."""
        fixture = _default_industry_ranking_df()
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "snapshot", CN_MAOTAI, sector_code="BK0489",
        )
        assert result[0]["snapshot_date"] == datetime.date.today().isoformat()


# ===================================================================
# UT-SA-215 — no fabrication verification
# ===================================================================


class TestSectorNoFabrication:
    def test_snapshot_forbidden_fields_stay_none(self):
        """UT-SA-215: total_count / main_net_inflow / leading_stock_name /
        members are all None — name_em does not return them and T3 does
        not call cons_em."""
        fixture = _default_industry_ranking_df()
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "snapshot", CN_MAOTAI, sector_code="BK0489",
        )
        record = result[0]
        assert record["total_count"] is None
        assert record["main_net_inflow"] is None
        assert record["leading_stock_name"] is None
        assert record["members"] is None


# ===================================================================
# SectorClient / mapping unit tests
# ===================================================================


class TestFakeSectorClientBehaviour:
    def test_fake_snapshot_derives_from_ranking(self):
        """snapshot_df=None → derive from ranking_df by sector_code."""
        fixture = _default_industry_ranking_df()
        client = FakeSectorClient(ranking_df=fixture)

        df = client.get_sector_snapshot(sector_code="BK0473")
        assert len(df) == 1
        assert df.iloc[0]["板块名称"] == "证券"

    def test_fake_snapshot_explicit_snapshot_df(self):
        fixture = _default_industry_ranking_df()
        snapshot = fixture[fixture["板块代码"] == "BK1036"]
        client = FakeSectorClient(ranking_df=fixture, snapshot_df=snapshot)

        df = client.get_sector_snapshot(sector_code="BK9999")
        assert len(df) == 1  # explicit snapshot_df wins over filter
        assert df.iloc[0]["板块代码"] == "BK1036"

    def test_fake_no_ranking_returns_empty(self):
        client = FakeSectorClient()
        assert client.get_sector_ranking().empty
        assert client.get_sector_snapshot(sector_code="BK0489").empty

    def test_fake_records_call_log(self):
        client = FakeSectorClient(ranking_df=_default_industry_ranking_df())
        client.get_sector_ranking(sector_type="industry")
        client.get_sector_snapshot(sector_code="BK0489", sector_type="industry")
        assert [c["method"] for c in client.call_log] == ["ranking", "snapshot"]
        assert client.call_log[1]["sector_code"] == "BK0489"


class TestAkShareSectorClientUnsupportedType:
    def test_unsupported_type_raises_without_sdk(self, monkeypatch):
        """Unsupported sector_type raises ProviderError before any SDK
        access — safe to test without akshare installed."""
        client = AKShareSectorClient()
        with pytest.raises(ProviderError, match="unsupported sector_type"):
            client._call_name_em("region")


class TestMappingFunctionDirect:
    def test_mapping_direct_returns_expected_records(self):
        """Direct mapping function check — schema-drift tolerance."""
        from skills.data.unified_data.providers.akshare import (
            _akshare_name_em_df_to_sector_dicts,
        )

        fixture = _default_industry_ranking_df()
        rows = _akshare_name_em_df_to_sector_dicts(
            fixture,
            capability=SECTOR_SNAPSHOT_CAPABILITY,
            snapshot_date="2026-07-21",
            sector_type="industry",
        )
        assert len(rows) == 5
        # No duplicate keys; no NaN coercion issues.
        for row in rows:
            assert isinstance(row["pct_chg"], float) or row["pct_chg"] is None

    def test_mapping_empty_df_returns_empty(self):
        from skills.data.unified_data.providers.akshare import (
            _akshare_name_em_df_to_sector_dicts,
        )

        rows = _akshare_name_em_df_to_sector_dicts(
            _empty_ranking_df(),
            capability=SECTOR_RANKING_CAPABILITY,
            snapshot_date="2026-07-21",
            sector_type="industry",
        )
        assert rows == []


# ===================================================================
# Ranking ordering / data reasonableness (P-11 sanity)
# ===================================================================


class TestSectorDataReasonableness:
    def test_ranking_rows_preserve_source_order(self):
        """The fixture is pre-sorted by 排名 (name_em returns ranked
        order). The mapping must preserve the source row order so the
        service-side pct_chg-desc sort remains consistent."""
        fixture = _default_industry_ranking_df()
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "ranking", CN_MAOTAI, sector_type="industry",
        )
        ranks = [r["rank"] for r in result]
        assert ranks == [1, 5, 12, 45, 88]
        assert all(r["pct_chg"] > r["decline_count"] * -100 for r in result)  # sanity range

    def test_snapshot_date_reasonableness(self):
        """snapshot_date is a YYYY-MM-DD string (business-date sanity)."""
        fixture = _default_industry_ranking_df()
        provider, _ = _provider_with_client(ranking_df=fixture)

        result = provider.fetch(
            "sector", "snapshot", CN_MAOTAI,
            sector_code="BK0489", date="2026-07-21",
        )
        assert result[0]["snapshot_date"] == "2026-07-21"
        # Format check: exactly YYYY-MM-DD.
        parsed = datetime.date.fromisoformat(result[0]["snapshot_date"])
        assert parsed.year == 2026


# ===================================================================
# Router-level integration — source_trace / zero-write / empty semantics
# ===================================================================


class TestSectorRouterIntegration:
    """Full offline chain: AKShareProvider + FakeSectorClient →
    DataRouter → DataResult. Verifies source_trace discipline, zero
    persistence writes, and empty semantics (SPEC F-030..F-038)."""

    def _router(self, client: FakeSectorClient, monkeypatch: Any):
        """Build a DataRouter with AKShareProvider registered and
        is_available() forced True."""
        import sys
        import types

        if "akshare" not in sys.modules:
            monkeypatch.setitem(sys.modules, "akshare", types.ModuleType("akshare"))

        from skills.data.unified_data import DataRouter, ProviderRegistry

        registry = ProviderRegistry()
        provider = AKShareProvider(sector_client=client)
        registry.register(provider)
        # No ta_cn_adapter: skip Step 1 (TA-CN) entirely.
        return DataRouter(registry)

    def test_snapshot_success_trace_contains_ok(self, monkeypatch):
        """F-030 success: provider='akshare', trace ends with akshare(ok),
        data is a list of canonical dicts."""
        fixture = _default_industry_ranking_df()
        client = FakeSectorClient(ranking_df=fixture)
        router = self._router(client, monkeypatch)

        result = router.query(
            "sector", "snapshot", CN_MAOTAI,
            params={"sector_code": "BK0489", "date": "2026-07-21"},
        )

        assert result.provider == "akshare"
        assert "akshare(ok)" in result.source_trace
        assert not result.is_empty()
        data = result.data
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["sector_code"] == "BK0489"
        # Read path is strictly read-only — no materialized/cache marker.
        assert "ud_materialized(ok)" not in result.source_trace
        assert "cache(ok)" not in result.source_trace

    def test_ranking_success_trace_contains_ok(self, monkeypatch):
        fixture = _default_industry_ranking_df()
        client = FakeSectorClient(ranking_df=fixture)
        router = self._router(client, monkeypatch)

        result = router.query(
            "sector", "ranking", CN_MAOTAI,
            params={"sector_type": "industry", "date": "2026-07-21"},
        )

        assert result.provider == "akshare"
        assert "akshare(ok)" in result.source_trace
        assert not result.is_empty()
        assert isinstance(result.data, list)
        assert len(result.data) == 5

    def test_empty_result_is_empty_success(self, monkeypatch):
        """F-030/F-032: empty DataFrame → success(is_empty) — NOT error,
        NOT retried, no failure trace."""
        client = FakeSectorClient(ranking_df=_empty_ranking_df())
        router = self._router(client, monkeypatch)

        result = router.query(
            "sector", "snapshot", CN_MAOTAI, params={"sector_code": "BK9999"},
        )
        assert result.provider == "akshare"
        assert result.is_empty()
        assert "akshare(ok)" in result.source_trace
        assert "ud_materialized(ok)" not in result.source_trace

    def test_client_error_produces_error_trace(self, monkeypatch):
        """F-033..F-038: client exception → DataResult.error with the
        provider error entry in source_trace."""
        client = FakeSectorClient(
            ranking_df=_default_industry_ranking_df(),
            exception=ProviderError("API internal error"),
        )
        router = self._router(client, monkeypatch)

        result = router.query(
            "sector", "snapshot", CN_MAOTAI, params={"sector_code": "BK0489"},
        )
        assert result.provider == "error"
        assert result.is_empty()
        trace_strs = " ".join(result.source_trace)
        assert "akshare(error: API internal error)" in trace_strs

    def test_ssl_error_produces_unavailable_trace(self, monkeypatch):
        """F-033: SSLError → akshare(unavailable: ...) trace entry."""
        import ssl

        client = FakeSectorClient(
            ranking_df=_default_industry_ranking_df(),
            exception=ssl.SSLError("certificate verify failed"),
        )
        router = self._router(client, monkeypatch)

        result = router.query(
            "sector", "ranking", CN_MAOTAI, params={"sector_type": "industry"},
        )
        assert result.provider == "error"
        assert result.is_empty()
        trace_strs = " ".join(result.source_trace)
        assert "akshare(unavailable: akshare sector API unavailable)" in trace_strs
