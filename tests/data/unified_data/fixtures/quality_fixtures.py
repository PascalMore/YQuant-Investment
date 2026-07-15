"""QualityScorer 测试专用 fixture。

与 conftest.py 中 FakeProvider / FakeTA_CNAdapter 风格一致；本文件聚焦
QualityScorer 及其衍生组件（AuditLogger / QualitySummary / Router 集成）
所需的可复现输入。

DESIGN-03-011 §9.2 列举的 fixture 本文件全部覆盖。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skills.data.unified_data import DataResult, Market, SecurityId
from skills.data.unified_data.quality.config import QualityScorerConfig


# ---------------------------------------------------------------------------
# SecurityId helpers (复用 conftest 中的 cn_maotai 即可，这里仅放 Quality
# 专用 fixture。)
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_now() -> datetime:
    """通用 DataResult 测试的确定性时间锚点。"""
    return datetime(2026, 7, 13, 0, 0, 0)


@pytest.fixture
def quality_fixed_now() -> datetime:
    """Quality 场景的确定性时间锚点（2026-07-15 12:00:00 UTC）。"""
    return datetime(2026, 7, 15, 12, 0, 0)


# ---------------------------------------------------------------------------
# QualityScorerConfig
# ---------------------------------------------------------------------------


@pytest.fixture
def quality_config_default() -> QualityScorerConfig:
    """默认配置（权重 0.35/0.30/0.15/0.20，TTL 表完整）。"""
    return QualityScorerConfig()


@pytest.fixture
def quality_config_market_data() -> QualityScorerConfig:
    """DESIGN §3.6 的 market_data 域覆盖示例。"""
    return QualityScorerConfig(
        dimension_weights={
            "completeness": 0.25,
            "freshness": 0.40,
            "consistency": 0.15,
            "plausibility": 0.20,
        },
        domain_ttl={"market_data": 14400},
    )


# ---------------------------------------------------------------------------
# DataResult fixtures — N1..N12 场景（DESIGN §3.5）
# ---------------------------------------------------------------------------


def _make_security_id() -> SecurityId:
    return SecurityId(market=Market.CN, symbol="600519")


@pytest.fixture
def result_normal(fixed_now: datetime) -> DataResult:
    """N1：TA-CN 命中，正常 delayed。"""
    return DataResult(
        data=[{"close": 1500.0, "volume": 1000000}],
        security_id=_make_security_id(),
        domain="market_data",
        operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=fixed_now,
        freshness="delayed",
    )


@pytest.fixture
def result_cached_fresh(fixed_now: datetime) -> DataResult:
    """N2：cached，年龄 < 0.5 TTL。"""
    fetched = fixed_now - timedelta(seconds=3600)  # 1h ago
    return DataResult(
        data=[{"close": 1500.0, "volume": 1000000}],
        security_id=_make_security_id(),
        domain="market_data",
        operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=fetched,
        freshness="cached",
    )


@pytest.fixture
def result_realtime(fixed_now: datetime) -> DataResult:
    """N3：外部 Provider 实时返回。"""
    return DataResult(
        data=[{"close": 1500.0, "volume": 1000000}],
        security_id=_make_security_id(),
        domain="market_data",
        operation="kline_daily",
        provider="tushare",
        fetched_at=fixed_now,
        freshness="realtime",
    )


@pytest.fixture
def result_empty(fixed_now: datetime) -> DataResult:
    """N4 / N6：空 payload（empty provider）。"""
    return DataResult(
        data=None,
        security_id=_make_security_id(),
        domain="market_data",
        operation="kline_daily",
        provider="empty",
        fetched_at=fixed_now,
        freshness="empty",
    )


@pytest.fixture
def result_stale(fixed_now: datetime) -> DataResult:
    """N5：过期结果。"""
    return DataResult(
        data=[{"close": 1500.0}],
        security_id=_make_security_id(),
        domain="market_data",
        operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=fixed_now - timedelta(days=10),
        freshness="stale",
    )


@pytest.fixture
def result_cached_near_expiry(fixed_now: datetime) -> DataResult:
    """N7：cached，年龄 > 0.9 TTL（临近过期）。"""
    fetched = fixed_now - timedelta(seconds=int(14400 * 0.95))
    return DataResult(
        data=[{"close": 1500.0, "volume": 1000000}],
        security_id=_make_security_id(),
        domain="market_data",
        operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=fetched,
        freshness="cached",
    )


@pytest.fixture
def result_error(fixed_now: datetime) -> DataResult:
    """N8：错误结果（provider="error"）。"""
    return DataResult.error(
        _make_security_id(),
        "market_data",
        "kline_daily",
        "tushare",
        Exception("tushare rate limit"),
        fetched_at=fixed_now,
    )


@pytest.fixture
def result_conflict(fixed_now: datetime) -> DataResult:
    """N9：来源冲突（活跃冲突标记）。

    DESIGN §3.5 N9 预期 quality_score=0.895，对应 completeness=1.0；
    因此 data 必须同时含 close 和 volume 两个核心字段。
    """
    return DataResult(
        data=[{"close": 1500.0, "volume": 1000000}],
        security_id=_make_security_id(),
        domain="market_data",
        operation="kline_daily",
        provider="tushare",
        fetched_at=fixed_now,
        freshness="delayed",
        source_trace=[
            "tushare(ok)",
            "tushare(vs_akshare:price_diverges)",
        ],
    )


@pytest.fixture
def result_anomaly_close_zero(fixed_now: datetime) -> DataResult:
    """N10：异常值（close=0）。"""
    return DataResult(
        data=[{"close": 0.0, "volume": 1000000}],
        security_id=_make_security_id(),
        domain="market_data",
        operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=fixed_now,
        freshness="delayed",
    )


@pytest.fixture
def result_missing_volume(fixed_now: datetime) -> DataResult:
    """N11：list[dict] daily-bar，volume 缺失（completeness=0.5）。

    DESIGN §3.5 footnote 锚点。警告文本精确为
    ``"missing required fields: volume"``。
    """
    return DataResult(
        data=[{"close": 1500.0}],
        security_id=_make_security_id(),
        domain="market_data",
        operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=fixed_now,
        freshness="delayed",
    )


@pytest.fixture
def result_financial_old(fixed_now: datetime) -> DataResult:
    """N12：财务数据，较老。"""
    fetched = fixed_now - timedelta(hours=12)
    return DataResult(
        data={"revenue": 1_000_000, "net_income": 200_000},
        security_id=_make_security_id(),
        domain="financial",
        operation="income_statement",
        provider="ta_cn_internal",
        fetched_at=fetched,
        freshness="delayed",
    )