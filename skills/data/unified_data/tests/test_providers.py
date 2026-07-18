"""Unit tests for the Phase 1B-A external provider stubs.

Covers DESIGN-03-008 §4.2 (Provider matrix — TP-001..TP-007 + AK-001..AK-006).
The two concrete providers — :class:`TushareProvider` and
:class:`AKShareProvider` — are stub-only in 1B-A. These tests assert
the surface that consumers depend on (name / capability set / market /
availability / stub fetch behaviour) without ever making a network
call.
"""

from __future__ import annotations

import pytest

from skills.data.unified_data.exceptions import UnsupportedCapabilityError
from skills.data.unified_data.models import Market, SecurityId
from skills.data.unified_data.models.domain.market_data import DailyBar
from skills.data.unified_data.providers import (
    STUB_COLUMNS,
    AKShareProvider,
    TushareProvider,
    stub_dataframe_for,
)
from skills.data.unified_data.providers.kline_client import FakeKlineClient


# ---------------------------------------------------------------------------
# TushareProvider
# ---------------------------------------------------------------------------


class TestTushareProvider:
    def test_tushare_name(self):
        """TP-101: stable identifier — always ``"tushare"``."""
        assert TushareProvider().name == "tushare"

    def test_tushare_capabilities(self):
        """TP-102: 13-capability set per SPEC-03-008 §4.5."""
        caps = TushareProvider().capabilities
        assert len(caps) == 13
        # Spot-check both common capabilities and the AKShare-excluded ones.
        assert "market_data.kline_daily" in caps
        assert "valuation.daily_basic" in caps
        assert "metadata.index_members" in caps
        assert "financial.income_statement" in caps

    def test_tushare_markets(self):
        """TP-103: Tushare is A-share (CN) only in 1B-A."""
        assert TushareProvider().markets == {Market.CN}

    def test_tushare_available_token(self, monkeypatch):
        """TP-104: token present and tushare importable ⇒ available."""
        monkeypatch.setenv("TUSHARE_TOKEN", "fake-token-for-test")
        # Inject a fake ``tushare`` module so the availability check
        # passes regardless of whether the optional distribution is
        # actually installed in this environment.
        import sys
        import types

        fake_module = types.ModuleType("tushare")
        monkeypatch.setitem(sys.modules, "tushare", fake_module)
        assert TushareProvider().is_available() is True

    def test_tushare_unavailable_no_token(self, monkeypatch):
        """TP-104: missing/empty token ⇒ unavailable, never raises."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        assert TushareProvider().is_available() is False

    def test_tushare_fetch_kline_daily_activated(self, cn_maotai):
        """TP-105: Phase 1D — kline_daily returns list[DailyBar] (not stub DF).

        Inject a FakeKlineClient with a Tushare-style fixture; verify
        the mapping produces a valid DailyBar.
        """
        import pandas as pd

        fixture = pd.DataFrame({
            "ts_code": ["600519.SH", "600519.SH"],
            "trade_date": ["20260713", "20260714"],
            "open": [1600.0, 1610.0],
            "high": [1620.0, 1625.0],
            "low": [1590.0, 1600.0],
            "close": [1615.0, 1620.0],
            "pre_close": [1595.0, 1615.0],
            "change": [20.0, 5.0],
            "pct_chg": [1.25, 0.31],
            "vol": [50000.0, 55000.0],
            "amount": [800000.0, 890000.0],
        })
        client = FakeKlineClient(dataframe=fixture)
        provider = TushareProvider(http_client=client)
        result = provider.fetch("market_data", "kline_daily", cn_maotai)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(b, DailyBar) for b in result)
        assert result[0].symbol == "600519"
        assert result[0].trade_date == "20260713"

    def test_tushare_fetch_stub_weekly(self, cn_maotai):
        """TP-105: non-kline_daily capability (kline_weekly) still returns stub DataFrame."""
        import pandas as pd

        provider = TushareProvider()
        result = provider.fetch("market_data", "kline_weekly", cn_maotai)
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == STUB_COLUMNS["market_data.kline_weekly"]

    def test_tushare_fetch_unsupported(self):
        """TP-106: undeclared capability raises ``UnsupportedCapabilityError``."""
        provider = TushareProvider()
        sector_index_id = SecurityId(market=Market.CN, symbol="SW_LEVEL1")
        with pytest.raises(UnsupportedCapabilityError):
            provider.fetch("metadata", "sector_classification", sector_index_id)


# ---------------------------------------------------------------------------
# AKShareProvider
# ---------------------------------------------------------------------------


class TestAKShareProvider:
    def test_akshare_name(self):
        """AK-101: stable identifier — always ``"akshare"``."""
        assert AKShareProvider().name == "akshare"

    def test_akshare_capabilities(self):
        """AK-102: 7-capability subset (AKShare does not expose the full set)."""
        caps = AKShareProvider().capabilities
        assert len(caps) == 7
        # ``adj_factor``, the three financial statements, ``index_members`` and
        # ``stock_news`` must NOT appear (Design §3.3.6).
        assert "market_data.kline_daily" in caps
        assert "valuation.daily_basic" in caps
        assert "market_data.adj_factor" not in caps
        assert "financial.income_statement" not in caps
        assert "news.stock_news" not in caps

    def test_akshare_markets(self):
        """AK-103: AKShare is A-share (CN) only in 1B-A."""
        assert AKShareProvider().markets == {Market.CN}

    def test_akshare_available_import(self, monkeypatch):
        """AK-104: ``import akshare`` succeeds ⇒ available."""
        import sys
        import types

        fake_module = types.ModuleType("akshare")
        monkeypatch.setitem(sys.modules, "akshare", fake_module)
        assert AKShareProvider().is_available() is True

    def test_akshare_unavailable_import(self, monkeypatch):
        """AK-104: ``import akshare`` fails ⇒ unavailable."""
        import sys

        # Drop any cached import + block the next import attempt.
        monkeypatch.delitem(sys.modules, "akshare", raising=False)
        monkeypatch.setitem(
            sys.modules, "akshare", None  # Python treats ``None`` as import failure
        )
        assert AKShareProvider().is_available() is False

    def test_akshare_fetch_kline_daily_activated(self, cn_maotai):
        """AK-105: Phase 1D — kline_daily returns list[DailyBar] (not stub DF)."""
        import pandas as pd

        fixture = pd.DataFrame({
            "日期": ["2026-07-13"],
            "开盘": [1600.0],
            "最高": [1620.0],
            "最低": [1590.0],
            "收盘": [1615.0],
            "涨跌额": [20.0],
            "涨跌幅": [1.25],
            "成交量": [5000000.0],
            "成交额": [800000000.0],
            "换手率": [0.45],
        })
        client = FakeKlineClient(dataframe=fixture)
        provider = AKShareProvider(http_client=client)
        result = provider.fetch("market_data", "kline_daily", cn_maotai)
        assert isinstance(result, list)
        assert len(result) == 1
        assert all(isinstance(b, DailyBar) for b in result)
        assert result[0].trade_date == "20260713"


# ---------------------------------------------------------------------------
# Stub helpers (cross-provider sanity)
# ---------------------------------------------------------------------------


class TestStubDataframe:
    def test_stub_dataframe_unknown_capability_defaults(self):
        """Unknown capabilities fall back to the ``["data"]`` schema."""
        df = stub_dataframe_for("does.not.exist")
        assert list(df.columns) == ["data"]
        assert len(df) == 0
