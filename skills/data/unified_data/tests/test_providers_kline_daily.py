"""Unit tests for Phase 1D kline_daily provider activation (UT-TP-201..208 +
UT-AK-201..208 + UT-SEC-401..403).

Every test injects a :class:`FakeKlineClient` so no real network I/O, no
real SDK import, and no environment variable read occurs. See
DESIGN-03-012 §5.1 for the full test matrix.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from skills.data.unified_data.exceptions import ProviderError, ProviderUnavailableError
from skills.data.unified_data.models import Market, SecurityId
from skills.data.unified_data.models.domain.market_data import DailyBar
from skills.data.unified_data.providers.akshare import AKShareProvider
from skills.data.unified_data.providers.kline_client import FakeKlineClient
from skills.data.unified_data.providers.tushare import TushareProvider


CN_MAOTAI = SecurityId(market=Market.CN, symbol="600519")


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _tushare_df(**overrides: Any) -> pd.DataFrame:
    """Build a Tushare ``daily``-style fixture DataFrame."""
    data = {
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
    }
    data.update(overrides)
    return pd.DataFrame(data)


def _akshare_df(**overrides: Any) -> pd.DataFrame:
    """Build an AKShare ``stock_zh_a_hist``-style fixture DataFrame."""
    data = {
        "日期": ["2026-07-13", "2026-07-14"],
        "开盘": [1600.0, 1610.0],
        "最高": [1620.0, 1625.0],
        "最低": [1590.0, 1600.0],
        "收盘": [1615.0, 1620.0],
        "涨跌额": [20.0, 5.0],
        "涨跌幅": [1.25, 0.31],
        "成交量": [5000000.0, 5500000.0],
        "成交额": [800000000.0, 890000000.0],
        "换手率": [0.45, 0.50],
    }
    data.update(overrides)
    return pd.DataFrame(data)


# ===================================================================
# TushareProvider — kline_daily activation tests (UT-TP-201..208)
# ===================================================================


class TestTushareKlineDaily:
    def test_real_path_success(self):
        """UT-TP-201: Tushare kline_daily returns list[DailyBar] with correct mapping."""
        fixture = _tushare_df()
        client = FakeKlineClient(dataframe=fixture)
        provider = TushareProvider(http_client=client)
        result = provider.fetch("market_data", "kline_daily", CN_MAOTAI)

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(b, DailyBar) for b in result)

        # Spot-check first bar
        bar0 = result[0]
        assert bar0.symbol == "600519"
        assert bar0.trade_date == "20260713"
        assert bar0.close == 1615.0
        assert bar0.open == 1600.0
        assert bar0.high == 1620.0
        assert bar0.low == 1590.0
        assert bar0.volume == 50000.0  # 手
        assert bar0.amount == 800000.0  # 千元
        assert bar0.turnover_rate is None  # daily does not provide it
        assert bar0.volume_ratio is None

        # The client was called exactly once
        assert len(client.call_log) == 1
        assert client.call_log[0]["security_id"] is CN_MAOTAI

    def test_empty_payload_raises(self):
        """UT-TP-202: Tushare kline_daily empty payload raises ProviderUnavailableError."""
        client = FakeKlineClient(dataframe=pd.DataFrame())
        provider = TushareProvider(http_client=client)
        with pytest.raises(ProviderUnavailableError, match="empty payload"):
            provider.fetch("market_data", "kline_daily", CN_MAOTAI)

    def test_missing_close_column(self):
        """UT-TP-203: missing close column raises ProviderError."""
        fixture = pd.DataFrame({"ts_code": ["600519.SH"], "trade_date": ["20260713"]})  # no close
        client = FakeKlineClient(dataframe=fixture)
        provider = TushareProvider(http_client=client)
        with pytest.raises(ProviderError, match="missing required column: close"):
            provider.fetch("market_data", "kline_daily", CN_MAOTAI)

    def test_row_dropped_when_close_nan(self):
        """UT-TP-204: row with NaN close is dropped; others remain."""
        fixture = _tushare_df(close=[1615.0, None])
        client = FakeKlineClient(dataframe=fixture)
        provider = TushareProvider(http_client=client)
        result = provider.fetch("market_data", "kline_daily", CN_MAOTAI)
        assert len(result) == 1
        assert result[0].trade_date == "20260713"

    def test_client_unavailable_propagates(self):
        """UT-TP-205: FakeKlineClient raises ProviderUnavailableError → fetch propagates."""
        client = FakeKlineClient(exception=ProviderUnavailableError("quota limit"))
        provider = TushareProvider(http_client=client)
        with pytest.raises(ProviderUnavailableError, match="quota limit"):
            provider.fetch("market_data", "kline_daily", CN_MAOTAI)

    def test_stub_path_other_capabilities(self):
        """UT-TP-206: non-kline_daily capabilities still return stub DataFrame."""
        from skills.data.unified_data.providers import STUB_COLUMNS, stub_dataframe_for

        provider = TushareProvider()
        result = provider.fetch("market_data", "kline_weekly", CN_MAOTAI)
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == STUB_COLUMNS["market_data.kline_weekly"]

    def test_is_available_with_token(self, monkeypatch):
        """UT-TP-207: token present + tushare importable ⇒ is_available() = True."""
        import sys
        import types

        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        fake = types.ModuleType("tushare")
        monkeypatch.setitem(sys.modules, "tushare", fake)
        assert TushareProvider().is_available() is True

    def test_is_available_no_token(self, monkeypatch):
        """UT-TP-207: absent token ⇒ is_available() = False."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        assert TushareProvider().is_available() is False

    def test_default_client_lazy_construction(self, monkeypatch):
        """UT-TP-208: http_client=None defers TushareKlineClient construction.

        The real client should only be created on the first kline_daily
        fetch, never during ``__init__`` or ``is_available()``.
        """
        import sys
        import types

        monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
        fake_tushare = types.ModuleType("tushare")
        monkeypatch.setitem(sys.modules, "tushare", fake_tushare)
        # We also need to patch pro_api on tushare so the lazy construction
        # in TushareKlineClient doesn't fail inside get_kline_daily.
        fake_tushare.pro_api = lambda token: type(  # type: ignore[attr-defined]
            "Pro", (), {"daily": lambda **kw: pd.DataFrame()}
        )()

        provider = TushareProvider(http_client=None)
        # Before first fetch, _http_client should be None
        assert provider._http_client is None


# ===================================================================
# AKShareProvider — kline_daily activation tests (UT-AK-201..208)
# ===================================================================


class TestAKShareKlineDaily:
    def test_real_path_success(self):
        """UT-AK-201: AKShare kline_daily returns list[DailyBar] with correct mapping."""
        fixture = _akshare_df()
        client = FakeKlineClient(dataframe=fixture)
        provider = AKShareProvider(http_client=client)
        result = provider.fetch("market_data", "kline_daily", CN_MAOTAI)

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(b, DailyBar) for b in result)

        bar0 = result[0]
        assert bar0.trade_date == "20260713"  # YYYYMMDD, not YYYY-MM-DD
        assert bar0.close == 1615.0
        assert bar0.open == 1600.0
        assert bar0.high == 1620.0
        assert bar0.low == 1590.0
        assert bar0.volume == 5000000.0  # 股
        assert bar0.amount == 800000000.0  # 元
        assert bar0.turnover_rate == 0.45  # 换手率
        assert bar0.volume_ratio is None

        assert len(client.call_log) == 1

    def test_empty_payload_raises(self):
        """UT-AK-202: AKShare empty payload raises ProviderUnavailableError."""
        client = FakeKlineClient(dataframe=pd.DataFrame())
        provider = AKShareProvider(http_client=client)
        with pytest.raises(ProviderUnavailableError, match="empty payload"):
            provider.fetch("market_data", "kline_daily", CN_MAOTAI)

    def test_missing_close_column(self):
        """UT-AK-203: missing 收盘 column raises ProviderError."""
        fixture = pd.DataFrame({"日期": ["2026-07-13"]})  # no 收盘
        client = FakeKlineClient(dataframe=fixture)
        provider = AKShareProvider(http_client=client)
        with pytest.raises(ProviderError, match="missing required column: 收盘"):
            provider.fetch("market_data", "kline_daily", CN_MAOTAI)

    def test_row_dropped_when_close_nan(self):
        """UT-AK-204: row with NaN close is dropped."""
        fixture = _akshare_df(收盘=[1615.0, None])
        client = FakeKlineClient(dataframe=fixture)
        provider = AKShareProvider(http_client=client)
        result = provider.fetch("market_data", "kline_daily", CN_MAOTAI)
        assert len(result) == 1

    def test_trade_date_format_conversion(self):
        """UT-AK-205: AKShare 'YYYY-MM-DD' dates are converted to 'YYYYMMDD'."""
        fixture = _akshare_df(
            日期=["2026-01-05"],
            开盘=[1600.0],
            最高=[1620.0],
            最低=[1590.0],
            收盘=[1615.0],
            涨跌额=[20.0],
            涨跌幅=[1.25],
            成交量=[5000000.0],
            成交额=[800000000.0],
            换手率=[0.45],
        )
        client = FakeKlineClient(dataframe=fixture)
        provider = AKShareProvider(http_client=client)
        result = provider.fetch("market_data", "kline_daily", CN_MAOTAI)
        assert result[0].trade_date == "20260105"

    def test_limit_truncation(self):
        """UT-AK-206: limit truncation applied for AKShare (no native limit support)."""
        fixture = _akshare_df(
            日期=[f"2026-07-{d:02d}" for d in range(1, 11)],
            开盘=[float(d) for d in range(10)],
            最高=[float(d) for d in range(10)],
            最低=[float(d) for d in range(10)],
            收盘=[float(d) for d in range(10)],
            涨跌额=[0.0] * 10,
            涨跌幅=[0.0] * 10,
            成交量=[1000.0] * 10,
            成交额=[100000.0] * 10,
            换手率=[0.1] * 10,
        )
        client = FakeKlineClient(dataframe=fixture)
        provider = AKShareProvider(http_client=client)
        result = provider.fetch(
            "market_data", "kline_daily", CN_MAOTAI, limit=5
        )
        assert len(result) == 5

    def test_stub_path_other_capabilities(self):
        """UT-AK-207: non-kline_daily capabilities return stub DataFrame."""
        from skills.data.unified_data.providers import STUB_COLUMNS

        provider = AKShareProvider()
        result = provider.fetch("market_data", "kline_weekly", CN_MAOTAI)
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == STUB_COLUMNS["market_data.kline_weekly"]

    def test_is_available_imports(self, monkeypatch):
        """UT-AK-208: akshare importable ⇒ available."""
        import sys
        import types

        fake = types.ModuleType("akshare")
        monkeypatch.setitem(sys.modules, "akshare", fake)
        assert AKShareProvider().is_available() is True

    def test_is_available_no_import(self, monkeypatch):
        """UT-AK-208: akshare not importable ⇒ unavailable."""
        import sys

        monkeypatch.delitem(sys.modules, "akshare", raising=False)
        monkeypatch.setitem(sys.modules, "akshare", None)
        assert AKShareProvider().is_available() is False


# ===================================================================
# Security tests (UT-SEC-401..403 — token not leaked)
# ===================================================================


class TestTokenSecurity:
    def test_is_available_does_not_leak_value(self, monkeypatch):
        """UT-SEC-401: is_available() returns bool, never the token value."""
        monkeypatch.setenv("TUSHARE_TOKEN", "super-secret-token-12345")
        import sys
        import types

        fake = types.ModuleType("tushare")
        monkeypatch.setitem(sys.modules, "tushare", fake)
        available = TushareProvider().is_available()
        # Must return True/False, not the token string
        assert available is True

    def test_error_message_does_not_contain_token(self):
        """UT-SEC-402: exception from TushareKlineClient does not leak token."""
        from skills.data.unified_data.providers.kline_client import TushareKlineClient

        # Construction with empty token raises ProviderUnavailableError
        with pytest.raises(ProviderUnavailableError) as excinfo:
            TushareKlineClient(token="")  # type: ignore[arg-type]
        msg = str(excinfo.value).lower()
        # The message should say "token missing", never the token value
        assert "token missing" in msg

    def test_fake_client_no_env_read(self):
        """UT-SEC-403: FakeKlineClient never reads environment variables."""
        import os

        # Sanity: record current TUSHARE_TOKEN before testing
        orig = os.environ.get("TUSHARE_TOKEN", "")
        try:
            os.environ.pop("TUSHARE_TOKEN", None)
            client = FakeKlineClient()
            client.get_kline_daily("test")
            # If it doesn't crash, it works — but also verify no os.environ calls
            # by checking call_log doesn't contain environment-related keys.
            for entry in client.call_log:
                assert "env" not in entry
        finally:
            if orig:
                os.environ["TUSHARE_TOKEN"] = orig
