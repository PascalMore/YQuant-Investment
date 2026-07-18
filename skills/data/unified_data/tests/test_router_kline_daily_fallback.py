"""Router fallback integration tests for kline_daily (UT-DR-301..309 + IT-001..004).

These tests verify that the Router orchestrates the internal-first and
external fallback chains correctly when ``kline_daily`` providers return
real ``list[DailyBar]`` payloads (via injected FakeKlineClient), raise
exceptions, or are unavailable.

See DESIGN-03-012 §5.1 / §5.2 for the full matrix.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from skills.data.unified_data import (
    DataResult,
    ProviderRegistry,
    ProviderUnavailableError,
    SecurityId,
    UnifiedDataClient,
)
from skills.data.unified_data.tests.conftest import FakeTA_CNAdapter, FakeProvider

from skills.data.unified_data.providers.kline_client import FakeKlineClient
from skills.data.unified_data.providers.tushare import TushareProvider
from skills.data.unified_data.providers.akshare import AKShareProvider
from skills.data.unified_data.models import Market
from skills.data.unified_data.models.domain.market_data import DailyBar

KLINE_CAP = "market_data.kline_daily"
CN_MAOTAI = SecurityId(market=Market.CN, symbol="600519")


# ---------------------------------------------------------------------------
# Helper — make TushareProvider / AKShareProvider is_available() = True
# ---------------------------------------------------------------------------
# TushareProvider requires both ``TUSHARE_TOKEN`` env var and the optional
# ``tushare`` package. AKShareProvider only requires the optional ``akshare``
# package. Neither package is installed in the test environment, so we
# monkeypatch both the env var and a fake module into ``sys.modules``.


def _make_tushare_available(monkeypatch: Any) -> None:
    """Set up the environment so TushareProvider.is_available() returns True."""
    import sys
    import types

    monkeypatch.setenv("TUSHARE_TOKEN", "test-token-for-router-test")
    if "tushare" not in sys.modules:
        fake = types.ModuleType("tushare")
        monkeypatch.setitem(sys.modules, "tushare", fake)


def _make_akshare_available(monkeypatch: Any) -> None:
    """Set up the environment so AKShareProvider.is_available() returns True."""
    import sys
    import types

    if "akshare" not in sys.modules:
        fake = types.ModuleType("akshare")
        monkeypatch.setitem(sys.modules, "akshare", fake)


def _make_both_available(monkeypatch: Any) -> None:
    """Make both providers available."""
    _make_tushare_available(monkeypatch)
    _make_akshare_available(monkeypatch)


# ---------------------------------------------------------------------------
# Helper — build a real-looking kline_daily DataFrame for FakeKlineClient
# ---------------------------------------------------------------------------


def _daily_df() -> pd.DataFrame:
    """One-row kline_daily fixture."""
    return pd.DataFrame(
        {
            "ts_code": ["600519.SH"],
            "trade_date": ["20260713"],
            "open": [1600.0],
            "high": [1620.0],
            "low": [1590.0],
            "close": [1615.0],
            "pre_close": [1595.0],
            "change": [20.0],
            "pct_chg": [1.25],
            "vol": [50000.0],
            "amount": [800000.0],
        }
    )


def _akshare_daily_df() -> pd.DataFrame:
    """One-row AKShare-style kline_daily fixture."""
    return pd.DataFrame(
        {
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
        }
    )


# ===================================================================
# Router — kline_daily fallback tests (UT-DR-301..309)
# ===================================================================


class TestRouterKlineDaily:
    def test_ta_cn_hit_external_not_called(self, cn_maotai, fresh_registry):
        """UT-DR-301: TA-CN returns data, no external provider called."""
        fake_ta_cn = FakeTA_CNAdapter(collections={
            "stock_daily_quotes": [
                {"symbol": "600519", "trade_date": "20260713", "open": 1600.0, "close": 1615.0}
            ]
        })
        # Register both providers — they should never be reached.
        fresh_registry.register(
            FakeProvider(
                name="tushare",
                payload="should-not-be-called",
                capabilities={KLINE_CAP},
                markets={Market.CN},
            )
        )
        from skills.data.unified_data import DataRouter
        router = DataRouter(fresh_registry, ta_cn_adapter=fake_ta_cn)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "ta_cn_internal"
        assert fake_ta_cn.call_log == ["get_daily_bars"]

    def test_ta_cn_not_covered_tushare_ok(self, cn_maotai, fresh_registry, monkeypatch):
        """UT-DR-302: TA-CN not covered → tushare (FakeKlineClient) succeeds."""
        _make_tushare_available(monkeypatch)
        fake_ta_cn = FakeTA_CNAdapter(
            collections={}, covered_capabilities=set()
        )
        fixture = _daily_df()
        tushare_client = FakeKlineClient(dataframe=fixture)
        tushare_provider = TushareProvider(http_client=tushare_client)
        fresh_registry.register(tushare_provider)
        from skills.data.unified_data import DataRouter
        router = DataRouter(fresh_registry, ta_cn_adapter=fake_ta_cn)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "tushare"
        assert len(tushare_client.call_log) == 1

    def test_tushare_fails_akshare_fallback(self, cn_maotai, fresh_registry, monkeypatch):
        """UT-DR-303: tushare raises → akshare fallback."""
        _make_both_available(monkeypatch)
        fake_ta_cn = FakeTA_CNAdapter(
            collections={}, covered_capabilities=set()
        )
        tushare_client = FakeKlineClient(
            exception=ProviderUnavailableError("tushare quota limit")
        )
        akshare_fixture = _akshare_daily_df()
        akshare_client = FakeKlineClient(dataframe=akshare_fixture)
        tushare_provider = TushareProvider(http_client=tushare_client)
        akshare_provider = AKShareProvider(http_client=akshare_client)
        fresh_registry.register(tushare_provider)
        fresh_registry.register(akshare_provider)
        from skills.data.unified_data import DataRouter
        router = DataRouter(fresh_registry, ta_cn_adapter=fake_ta_cn)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "akshare"
        # verify trace has both
        trace_strs = " ".join(result.source_trace)
        assert "tushare" in trace_strs
        assert "akshare" in trace_strs

    def test_both_fail(self, cn_maotai, fresh_registry, monkeypatch):
        """UT-DR-304: both providers raise → error result."""
        _make_both_available(monkeypatch)
        tushare_client = FakeKlineClient(
            exception=ProviderUnavailableError("tushare down")
        )
        akshare_client = FakeKlineClient(
            exception=ProviderUnavailableError("akshare down")
        )
        fresh_registry.register(
            TushareProvider(http_client=tushare_client)
        )
        fresh_registry.register(
            AKShareProvider(http_client=akshare_client)
        )
        from skills.data.unified_data import DataRouter
        # No ta_cn_adapter: skip Step 1 (TA-CN) entirely so the test
        # isolates the external chain without TA-CN empty wrapping.
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error"
        assert result.is_empty

    def test_both_empty_payload(self, cn_maotai, fresh_registry, monkeypatch):
        """UT-DR-305: both providers return empty → error result (freshness=empty)."""
        _make_both_available(monkeypatch)
        empty_client = FakeKlineClient(dataframe=pd.DataFrame())
        fresh_registry.register(
            TushareProvider(http_client=empty_client)
        )
        empty_client2 = FakeKlineClient(dataframe=pd.DataFrame())
        fresh_registry.register(
            AKShareProvider(http_client=empty_client2)
        )
        from skills.data.unified_data import DataRouter
        # No ta_cn_adapter: skip Step 1 (TA-CN) entirely.
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error"
        assert result.is_empty
        trace_strs = " ".join(result.source_trace)
        assert "empty payload" in trace_strs

    def test_both_unavailable(self, cn_maotai, fresh_registry, monkeypatch):
        """UT-DR-306: both providers is_available=False → error result."""
        # This test intentionally leaves providers unavailable.
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        import sys
        monkeypatch.delitem(sys.modules, "akshare", raising=False)
        monkeypatch.setitem(sys.modules, "akshare", None)
        fresh_registry.register(TushareProvider())
        fresh_registry.register(AKShareProvider())
        from skills.data.unified_data import DataRouter
        # No ta_cn_adapter: skip Step 1 (TA-CN) entirely so the test
        # isolates the external-chain unavailable path.
        router = DataRouter(fresh_registry)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "error"
        assert any("skipped" in e for e in result.source_trace)

    def test_forced_tushare(self, cn_maotai, fresh_registry, monkeypatch):
        """UT-DR-307: provider='tushare' pins tushare, no fallback."""
        _make_tushare_available(monkeypatch)
        fake_ta_cn = FakeTA_CNAdapter(
            collections={}, covered_capabilities=set()
        )
        fixture = _daily_df()
        client = FakeKlineClient(dataframe=fixture)
        fresh_registry.register(
            TushareProvider(http_client=client)
        )
        from skills.data.unified_data import DataRouter
        router = DataRouter(fresh_registry, ta_cn_adapter=fake_ta_cn)
        result = router.query(
            "market_data", "kline_daily", cn_maotai, provider="tushare"
        )
        assert result.provider == "tushare"
        assert len(client.call_log) == 1

    def test_force_refresh_skips_ta_cn(self, cn_maotai, fresh_registry, monkeypatch):
        """UT-DR-308: force_refresh=True skips TA-CN and goes to external."""
        _make_tushare_available(monkeypatch)
        fake_ta_cn = FakeTA_CNAdapter(collections={
            "stock_daily_quotes": [
                {"symbol": "600519", "trade_date": "20260713", "close": 2000}
            ]
        })
        fixture = _daily_df()
        client = FakeKlineClient(dataframe=fixture)
        fresh_registry.register(
            TushareProvider(http_client=client)
        )
        from skills.data.unified_data import DataRouter
        router = DataRouter(fresh_registry, ta_cn_adapter=fake_ta_cn)
        result = router.query(
            "market_data", "kline_daily", cn_maotai, force_refresh=True
        )
        assert result.provider == "tushare"
        # TA-CN was never called
        assert fake_ta_cn.call_log == []

    def test_quality_score_none(self, cn_maotai, fresh_registry, monkeypatch):
        """UT-DR-309: DataResult.quality_score is None (Phase 1D)."""
        _make_tushare_available(monkeypatch)
        fake_ta_cn = FakeTA_CNAdapter(
            collections={}, covered_capabilities=set()
        )
        fixture = _daily_df()
        client = FakeKlineClient(dataframe=fixture)
        fresh_registry.register(
            TushareProvider(http_client=client)
        )
        from skills.data.unified_data import DataRouter
        router = DataRouter(fresh_registry, ta_cn_adapter=fake_ta_cn)
        result = router.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "tushare"
        # Phase 1D: quality_score is always None
        assert getattr(result, "quality_score", None) is None
        assert getattr(result, "scored_result", None) is None


# ===================================================================
# Integration tests (IT-001..004)
# ===================================================================


class TestKlineDailyIntegration:
    def test_it_001_ta_cn_hit(self, cn_maotai):
        """IT-001: client.query(kline_daily) → TA-CN hit → no external called."""
        from skills.data.unified_data import DataRouter

        fake_ta_cn = FakeTA_CNAdapter(collections={
            "stock_daily_quotes": [{"symbol": "600519", "trade_date": "20260713", "close": 1615.0}]
        })
        client = UnifiedDataClient(
            registry=ProviderRegistry(),
            ta_cn_adapter=fake_ta_cn,
        )
        result = client.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "ta_cn_internal"
        assert fake_ta_cn.call_log == ["get_daily_bars"]

    def test_it_002_forced_tushare(self, cn_maotai, monkeypatch):
        """IT-002: client.query(kline_daily, provider='tushare') → FakeKlineClient → list[DailyBar]."""
        _make_tushare_available(monkeypatch)
        provider_registry = ProviderRegistry()
        fixture = _daily_df()
        client_fake = FakeKlineClient(dataframe=fixture)
        provider_registry.register(
            TushareProvider(http_client=client_fake)
        )
        client = UnifiedDataClient.with_providers(
            providers=[TushareProvider(http_client=client_fake)],
        )
        result = client.query(
            "market_data", "kline_daily", cn_maotai, provider="tushare"
        )
        assert result.provider == "tushare"
        assert isinstance(result.data, list)
        assert len(result.data) == 1
        assert isinstance(result.data[0], DailyBar)

    def test_it_003_force_refresh(self, cn_maotai, monkeypatch):
        """IT-003: client.query(kline_daily, force_refresh=True) → skips TA-CN → tushare."""
        _make_tushare_available(monkeypatch)
        provider_registry = ProviderRegistry()
        fixture = _daily_df()
        client_fake = FakeKlineClient(dataframe=fixture)
        provider_registry.register(
            TushareProvider(http_client=client_fake)
        )
        client = UnifiedDataClient.with_providers(
            providers=[TushareProvider(http_client=client_fake)],
        )
        result = client.query(
            "market_data", "kline_daily", cn_maotai, force_refresh=True
        )
        assert result.provider == "tushare"

    def test_it_004_fallback_tushare_fail_akshare_ok(self, cn_maotai, monkeypatch):
        """IT-004: tushare fails → akshare fallback → list[DailyBar] + warnings."""
        _make_both_available(monkeypatch)
        provider_registry = ProviderRegistry()
        tushare_client = FakeKlineClient(
            exception=ProviderUnavailableError("tushare quota")
        )
        akshare_fixture = _akshare_daily_df()
        akshare_client = FakeKlineClient(dataframe=akshare_fixture)
        provider_registry.register(
            TushareProvider(http_client=tushare_client)
        )
        provider_registry.register(
            AKShareProvider(http_client=akshare_client)
        )
        client = UnifiedDataClient.with_providers(
            providers=[
                TushareProvider(http_client=tushare_client),
                AKShareProvider(http_client=akshare_client),
            ],
        )
        result = client.query("market_data", "kline_daily", cn_maotai)
        assert result.provider == "akshare"
        assert isinstance(result.data, list)
        assert len(result.data) == 1
        assert isinstance(result.data[0], DailyBar)
        # Warnings should contain ta_cn_internal since TA-CN was skipped
        trace_strs = " ".join(result.source_trace)
        assert "tushare" in trace_strs
        assert "akshare" in trace_strs
