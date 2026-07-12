"""Tests for SecurityId, DataResult, Capability (models module).

Phase 0 acceptance targets:
    * SecurityId: construction, normalization, canonical form, illegal input rejected
    * DataResult: success / empty / error behavior + serialization
    * Capability: domain.operation round-trip and validation
"""

from __future__ import annotations

from datetime import datetime

import pytest

from skills.data.unified_data import (
    Capability,
    DataResult,
    InvalidSecurityIdError,
    Market,
    SecurityId,
)


# ---------------------------------------------------------------------------
# SecurityId — construction & canonical form
# ---------------------------------------------------------------------------


class TestSecurityIdConstruction:
    def test_construction_from_enum(self, cn_maotai):
        assert cn_maotai.market is Market.CN
        assert cn_maotai.symbol == "600519"

    def test_construction_from_string_market(self):
        sid = SecurityId(market="CN", symbol="600519")
        # The string is normalized to Market.CN
        assert sid.market is Market.CN

    def test_canonical_property(self, cn_maotai):
        assert cn_maotai.canonical == "CN:600519"

    def test_str_matches_canonical(self, cn_maotai):
        assert str(cn_maotai) == "CN:600519"
        assert str(cn_maotai) == cn_maotai.canonical

    def test_unknown_market_raises(self):
        with pytest.raises(InvalidSecurityIdError):
            SecurityId(market="ZZ", symbol="600519")

    def test_non_string_market_raises(self):
        with pytest.raises(InvalidSecurityIdError):
            SecurityId(market=42, symbol="600519")

    def test_empty_symbol_raises(self):
        with pytest.raises(InvalidSecurityIdError):
            SecurityId(market=Market.CN, symbol="")

    def test_whitespace_symbol_raises(self):
        with pytest.raises(InvalidSecurityIdError):
            SecurityId(market=Market.CN, symbol="   ")

    def test_non_string_symbol_raises(self):
        with pytest.raises(InvalidSecurityIdError):
            SecurityId(market=Market.CN, symbol=123)

    def test_symbol_is_stripped(self):
        sid = SecurityId(market=Market.CN, symbol="  600519  ")
        assert sid.symbol == "600519"


class TestSecurityIdEquality:
    def test_equal_when_market_and_symbol_match(self):
        a = SecurityId(market=Market.CN, symbol="600519")
        b = SecurityId(market=Market.CN, symbol="600519")
        assert a == b
        assert hash(a) == hash(b)

    def test_hashable_for_set_and_dict_keys(self):
        a = SecurityId(market=Market.CN, symbol="600519")
        b = SecurityId(market=Market.CN, symbol="600519")
        c = SecurityId(market=Market.HK, symbol="00700")
        s = {a, b, c}
        assert len(s) == 2
        d = {a: "maotai", c: "tencent"}
        assert d[b] == "maotai"

    def test_inequality_when_market_differs(self):
        cn = SecurityId(market=Market.CN, symbol="600519")
        hk = SecurityId(market=Market.HK, symbol="600519")
        assert cn != hk

    def test_frozen_rejects_mutation(self, cn_maotai):
        with pytest.raises((AttributeError, Exception)):
            cn_maotai.symbol = "000001"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SecurityId — factories
# ---------------------------------------------------------------------------


class TestSecurityIdFactories:
    @pytest.mark.parametrize(
        "code,expected_market,expected_symbol",
        [
            ("600519.SH", Market.CN, "600519"),
            ("000001.SZ", Market.CN, "000001"),
            ("688001.SH", Market.CN, "688001"),
            ("920001.BJ", Market.CN, "920001"),
            ("00700.HK", Market.HK, "00700"),
            ("AAPL.US", Market.US, "AAPL"),
        ],
    )
    def test_from_wind_code_valid(self, code, expected_market, expected_symbol):
        sid = SecurityId.from_wind_code(code)
        assert sid.market is expected_market
        assert sid.symbol == expected_symbol

    @pytest.mark.parametrize(
        "code",
        ["600519", "600519.XY", "", ".SH", "600519.", "600519.SH.extra"],
    )
    def test_from_wind_code_invalid(self, code):
        with pytest.raises(InvalidSecurityIdError):
            SecurityId.from_wind_code(code)

    def test_from_tushare_code_alias(self):
        a = SecurityId.from_tushare_code("600519.SH")
        b = SecurityId.from_full_symbol("600519.SH")
        assert a == b

    def test_from_numeric(self):
        sid = SecurityId.from_numeric("600519", Market.CN)
        assert sid.market is Market.CN
        assert sid.symbol == "600519"

    def test_from_numeric_accepts_string_market(self):
        sid = SecurityId.from_numeric("AAPL", "US")
        assert sid.market is Market.US

    def test_from_numeric_empty_raises(self):
        with pytest.raises(InvalidSecurityIdError):
            SecurityId.from_numeric("", Market.CN)

    def test_from_wind_code_none_raises(self):
        with pytest.raises(InvalidSecurityIdError):
            SecurityId.from_wind_code(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SecurityId — conversions
# ---------------------------------------------------------------------------


class TestSecurityIdConversion:
    @pytest.mark.parametrize(
        "symbol,expected",
        [
            ("600519", "600519.SH"),  # Shanghai main board
            ("601318", "601318.SH"),
            ("688981", "688981.SH"),  # STAR board
            ("000001", "000001.SZ"),  # Shenzhen main board
            ("300750", "300750.SZ"),  # ChiNext
            ("920001", "920001.BJ"),  # Beijing
        ],
    )
    def test_to_wind_code_a_share(self, symbol, expected):
        sid = SecurityId(market=Market.CN, symbol=symbol)
        assert sid.to_wind_code() == expected
        assert sid.to_tushare_code() == expected
        assert sid.to_full_symbol() == expected

    @pytest.mark.parametrize("symbol", ["999999", "12345678", "ABCDEF"])
    def test_to_wind_code_returns_none_for_unknown_a_share(self, symbol):
        sid = SecurityId(market=Market.CN, symbol=symbol)
        assert sid.to_wind_code() is None

    def test_to_wind_code_hk_us(self):
        assert SecurityId(Market.HK, "00700").to_wind_code() == "00700.HK"
        assert SecurityId(Market.US, "AAPL").to_wind_code() == "AAPL.US"

    @pytest.mark.parametrize("market", [Market.CRYPTO, Market.INDEX, Market.FUND])
    def test_to_wind_code_unsupported_market(self, market):
        sid = SecurityId(market=market, symbol="X")
        assert sid.to_wind_code() is None

    def test_round_trip_cn(self):
        original = SecurityId(Market.CN, "600519")
        restored = SecurityId.from_wind_code(original.to_wind_code())
        assert restored == original

    def test_round_trip_hk_us(self):
        for market, symbol, code in [
            (Market.HK, "00700", "00700.HK"),
            (Market.US, "AAPL", "AAPL.US"),
        ]:
            original = SecurityId(market, symbol)
            assert original.to_wind_code() == code
            assert SecurityId.from_wind_code(code) == original


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------


class TestCapability:
    def test_construction(self):
        cap = Capability(domain="market_data", operation="kline_daily")
        assert cap.name == "market_data.kline_daily"

    def test_str(self):
        cap = Capability(domain="market_data", operation="kline_daily")
        assert str(cap) == "market_data.kline_daily"

    def test_from_string(self):
        cap = Capability.from_string("financial.income_statement")
        assert cap.domain == "financial"
        assert cap.operation == "income_statement"

    @pytest.mark.parametrize(
        "value",
        ["", "no_dot", "too.many.dots", None, 123],
    )
    def test_from_string_invalid(self, value):
        with pytest.raises(ValueError):
            Capability.from_string(value)  # type: ignore[arg-type]

    def test_construction_rejects_dot_in_domain(self):
        with pytest.raises(ValueError):
            Capability(domain="a.b", operation="c")

    def test_construction_rejects_empty_domain(self):
        with pytest.raises(ValueError):
            Capability(domain="", operation="c")

    def test_frozen(self):
        cap = Capability(domain="x", operation="y")
        with pytest.raises((AttributeError, Exception)):
            cap.domain = "z"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DataResult
# ---------------------------------------------------------------------------


class TestDataResultSuccess:
    def test_success_non_empty(self, cn_maotai):
        result = DataResult.success(
            data=[{"close": 100.0}],
            security_id=cn_maotai,
            domain="market_data",
            operation="kline_daily",
            provider="tushare",
        )
        assert result.provider == "tushare"
        assert result.freshness == "delayed"
        assert result.succeeded
        assert not result.is_empty()
        assert result.source_trace == ["tushare(ok)"]
        assert result.warnings == []

    def test_success_with_explicit_source_trace(self, cn_maotai):
        result = DataResult.success(
            data={"rows": 10},
            security_id=cn_maotai,
            domain="market_data",
            operation="kline_daily",
            provider="akshare",
            source_trace=["tushare(fail)", "akshare(ok)"],
        )
        assert result.source_trace == ["tushare(fail)", "akshare(ok)"]

    def test_success_uses_provided_fetched_at(self, cn_maotai, fixed_now):
        result = DataResult.success(
            data=[1, 2, 3],
            security_id=cn_maotai,
            domain="market_data",
            operation="kline_daily",
            provider="tushare",
            fetched_at=fixed_now,
        )
        assert result.fetched_at == fixed_now

    def test_success_records_warnings(self, cn_maotai):
        result = DataResult.success(
            data=[1, 2],
            security_id=cn_maotai,
            domain="market_data",
            operation="kline_daily",
            provider="tushare",
            warnings=["close is null for 3 rows"],
        )
        assert "close is null for 3 rows" in result.warnings


class TestDataResultEmpty:
    @pytest.mark.parametrize("payload", [None, [], (), {}, set()])
    def test_empty_payload_yields_empty_result(self, cn_maotai, payload):
        result = DataResult.success(
            data=payload,
            security_id=cn_maotai,
            domain="market_data",
            operation="kline_daily",
            provider="tushare",
        )
        assert result.freshness == "empty"
        assert result.provider == "empty"
        assert result.is_empty()
        assert not result.succeeded

    def test_dataframe_empty_attribute(self, cn_maotai):
        """A pandas DataFrame with ``.empty == True`` is also treated as empty."""
        try:
            import pandas as pd
        except ImportError:  # pragma: no cover — pandas should be present in CI
            pytest.skip("pandas not installed")

        result = DataResult.success(
            data=pd.DataFrame(),
            security_id=cn_maotai,
            domain="market_data",
            operation="kline_daily",
            provider="tushare",
        )
        assert result.freshness == "empty"


class TestDataResultError:
    def test_error_factory(self, cn_maotai, fixed_now):
        result = DataResult.error(
            security_id=cn_maotai,
            domain="market_data",
            operation="kline_daily",
            provider="tushare",
            error="rate limited",
            fetched_at=fixed_now,
        )
        assert result.provider == "error"
        assert result.freshness == "empty"
        assert "rate limited" in result.warnings
        assert result.is_empty()

    def test_error_factory_with_exception(self, cn_maotai):
        exc = ValueError("boom")
        result = DataResult.error(
            security_id=cn_maotai,
            domain="market_data",
            operation="kline_daily",
            provider="akshare",
            error=exc,
        )
        assert "boom" in " ".join(result.warnings)


class TestDataResultSerialization:
    def test_to_dict_includes_all_fields(self, cn_maotai, fixed_now):
        result = DataResult.success(
            data={"close": 100},
            security_id=cn_maotai,
            domain="market_data",
            operation="kline_daily",
            provider="tushare",
            fetched_at=fixed_now,
            source_trace=["tushare(ok)"],
            warnings=["minor"],
        )
        d = result.to_dict()
        assert d["security_id"] == "CN:600519"
        assert d["domain"] == "market_data"
        assert d["operation"] == "kline_daily"
        assert d["provider"] == "tushare"
        assert d["fetched_at"] == fixed_now.isoformat()
        assert d["freshness"] == "delayed"
        assert d["source_trace"] == ["tushare(ok)"]
        assert d["warnings"] == ["minor"]
        assert d["data"] == {"close": 100}

    def test_to_dict_passes_dataframe_through(self, cn_maotai):
        """DataResult.to_dict does not auto-convert; caller decides format."""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")

        df = pd.DataFrame({"close": [100, 101]})
        result = DataResult.success(
            data=df,
            security_id=cn_maotai,
            domain="market_data",
            operation="kline_daily",
            provider="tushare",
        )
        d = result.to_dict()
        assert d["data"] is df