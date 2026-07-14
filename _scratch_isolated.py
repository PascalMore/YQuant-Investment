"""Scratch test to reproduce df.empty failure."""
import pandas as pd
import pytest

from skills.data.unified_data.models import DataResult, SecurityId, Market


@pytest.fixture
def cn_maotai():
    return SecurityId(market=Market.CN, symbol="600519")


def test_dataframe_empty_attribute(cn_maotai):
    try:
        import pandas as pd  # noqa
    except ImportError:
        pytest.skip("pandas not installed")

    result = DataResult.success(
        data=pd.DataFrame(),
        security_id=cn_maotai,
        domain="market_data",
        operation="kline_daily",
        provider="tushare",
    )
    assert result.freshness == "empty", f"got {result.freshness!r}"
