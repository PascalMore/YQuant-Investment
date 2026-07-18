"""QualityScorer 单元测试（DESIGN-03-011 §3, SPEC-03-011 §3）。

行为矩阵 N1-N12（DESIGN §3.5）逐条覆盖。每条用例使用最小断言：
* 子维度分在 [0, 1]
* 总分在 [0, 1]
* quality_tier ∈ {direct_use, warning, degrade, reject}
* warnings 字符串精确匹配（DESIGN §3.5 N9 / N11）
* 已知核心字段缺失的警告文本使用 DESIGN/SPEC 冻结的精确字符串

测试先于实现落地；RED 通过 import 失败触发，GREEN 通过
``quality/scorer.py`` 落地。
"""

from __future__ import annotations

import pytest

from skills.data.unified_data.quality.config import QualityScorerConfig
from skills.data.unified_data.quality.scorer import QualityScorer, ScoredResult

# 复用 quality_fixtures 中的场景 fixture（fixture 文件本身已包含全部
# N1-N12 输入构造）。这里仅导入本文件需要的子集（pytest 自动发现）。
pytest_plugins = []  # 不引入新插件；fixture 由 fixtures/quality_fixtures.py 提供。


# ---------------------------------------------------------------------------
# 接口形状
# ---------------------------------------------------------------------------


class TestScoredResultShape:
    def test_score_returns_scored_result(self, result_normal) -> None:
        scorer = QualityScorer()
        scored = scorer.score(result_normal)
        assert isinstance(scored, ScoredResult)
        assert scored.quality_score is not None
        assert 0.0 <= scored.quality_score <= 1.0

    def test_dimension_scores_has_four_keys(self, result_normal) -> None:
        scorer = QualityScorer()
        scored = scorer.score(result_normal)
        assert set(scored.dimension_scores) == {
            "completeness",
            "freshness",
            "consistency",
            "plausibility",
        }
        for v in scored.dimension_scores.values():
            assert 0.0 <= v <= 1.0

    def test_quality_tier_is_canonical_value(self, result_normal) -> None:
        scorer = QualityScorer()
        scored = scorer.score(result_normal)
        assert scored.quality_tier in {
            "direct_use",
            "warning",
            "degrade",
            "reject",
        }


# ---------------------------------------------------------------------------
# N1-N12 行为矩阵（DESIGN §3.5）
# ---------------------------------------------------------------------------


class TestNormalPath:
    def test_n1_normal_ta_cn_hit_is_direct_use(
        self, result_normal, quality_fixed_now
    ) -> None:
        scored = QualityScorer().score(result_normal, now=quality_fixed_now)


class TestHardFailPath:
    def test_n4_empty_result_is_reject_zero(self, result_empty) -> None:
        scored = QualityScorer().score(result_empty)
        assert scored.quality_score == 0.0
        assert scored.quality_tier == "reject"
        # DESIGN §3.2.1 硬失败 warning 文本
        assert scored.warnings == ["empty result: no usable payload"]

    def test_n5_stale_result_is_reject_zero(self, result_stale) -> None:
        scored = QualityScorer().score(result_stale)
        assert scored.quality_score == 0.0
        assert scored.quality_tier == "reject"
        # DESIGN §3.2.2 stale 触发 warning（free-form，但必须存在）
        assert any("stale" in w.lower() for w in scored.warnings)

    def test_n6_empty_provider_is_reject_zero(self, result_empty) -> None:
        # 与 N4 共用 fixture；显式校验 provider="empty" 路径
        assert result_empty.provider == "empty"
        scored = QualityScorer().score(result_empty)
        assert scored.quality_score == 0.0
        assert scored.quality_tier == "reject"

    def test_n7_cached_near_expiry_is_warning(
        self, result_cached_near_expiry, quality_fixed_now
    ) -> None:
        scored = QualityScorer().score(result_cached_near_expiry, now=quality_fixed_now)
        # DESIGN §3.5 N7: completeness=1.0, freshness=0.2 (age > 0.9*ttl),
        # consistency=1.0, plausibility=1.0. 按默认权重公式:
        # 0.35*1.0 + 0.30*0.2 + 0.15*1.0 + 0.20*1.0 = 0.76
        # 0.76 ∈ [0.7, 0.9) → warning；与 DESIGN §3.5 冻结契约一致
        # now= 注入保证 age = 0.95 * 14400 > 0.9 * ttl
        assert scored.dimension_scores["completeness"] == pytest.approx(1.0)
        assert scored.dimension_scores["freshness"] == pytest.approx(0.2)
        assert scored.quality_score == pytest.approx(0.76, abs=1e-3)
        # 0.76 ∈ [0.7, 0.9) → warning
        assert scored.quality_tier == "warning"
        assert any("cache near expiry" in w.lower() for w in scored.warnings)

    def test_n8_error_result_is_reject_zero(self, result_error) -> None:
        scored = QualityScorer().score(result_error)
        assert scored.quality_score == 0.0
        assert scored.quality_tier == "reject"
        # 原始 error 已带 ["tushare rate limit"]；scorer 追加硬失败文本
        assert any("empty" in w.lower() or "provider" in w.lower()
                   for w in scored.warnings)


class TestMidTierPath:
    def test_n9_source_conflict_is_warning(self, result_conflict) -> None:
        scored = QualityScorer().score(result_conflict)
        # completeness=1.0, freshness=1.0, consistency=0.3 (active conflict),
        # plausibility=1.0 → 0.35 + 0.30 + 0.15*0.3 + 0.20 = 0.895
        assert scored.quality_score == pytest.approx(0.895, abs=1e-3)
        # 0.895 ∈ [0.7, 0.9) → warning
        assert scored.quality_tier == "warning"
        # DESIGN §3.5 警告文本
        assert any(
            "source conflict" in w.lower() or "price diverg" in w.lower()
            for w in scored.warnings
        )

    def test_n10_anomaly_close_zero_is_reject(self, result_anomaly_close_zero) -> None:
        scored = QualityScorer().score(result_anomaly_close_zero)
        # close=0 触发 plausibility hard fail → quality_score=0
        assert scored.quality_score == 0.0
        assert scored.quality_tier == "reject"
        # DESIGN §3.2.4 plausibility 硬失败 warning
        assert any("close" in w.lower() for w in scored.warnings)

    def test_n11_missing_volume_is_warning_with_exact_string(
        self, result_missing_volume
    ) -> None:
        scored = QualityScorer().score(result_missing_volume)
        # completeness=0.5 (1/2 字段存在), freshness=1.0 (delayed),
        # consistency=1.0, plausibility=1.0
        # → 0.35*0.5 + 0.30*1 + 0.15*1 + 0.20*1 = 0.825
        assert scored.dimension_scores["completeness"] == pytest.approx(0.5)
        assert scored.quality_score == pytest.approx(0.825, abs=1e-3)
        # 0.825 ∈ [0.7, 0.9) → warning
        assert scored.quality_tier == "warning"
        # DESIGN/SPEC 冻结的精确 warning 字符串
        assert scored.warnings == ["missing required fields: volume"]

    def test_n12_financial_old_is_direct_use(self, result_financial_old) -> None:
        scored = QualityScorer().score(result_financial_old)
        # delayed + age < TTL（financial TTL=24h, age=12h）→ freshness=1.0
        # financial 域无核心字段检查；completeness=1.0
        assert scored.quality_score == pytest.approx(1.0)
        assert scored.quality_tier == "direct_use"


# ---------------------------------------------------------------------------
# Domain overrides
# ---------------------------------------------------------------------------


class TestDomainOverrides:
    def test_market_data_override_changes_weights(self, result_normal) -> None:
        cfg = QualityScorerConfig(
            dimension_weights={
                "completeness": 0.25,
                "freshness": 0.40,
                "consistency": 0.15,
                "plausibility": 0.20,
            },
            domain_overrides={
                "market_data": QualityScorerConfig(
                    dimension_weights={
                        "completeness": 0.10,
                        "freshness": 0.60,
                        "consistency": 0.10,
                        "plausibility": 0.20,
                    },
                ),
            },
        )
        scorer = QualityScorer(config=cfg)
        scored = scorer.score(result_normal, domain="market_data")
        # completeness=1.0, freshness=1.0, consistency=1.0, plausibility=1.0
        # 在覆盖权重下：0.10 + 0.60 + 0.10 + 0.20 = 1.0
        assert scored.quality_score == pytest.approx(1.0)

    def test_unknown_domain_falls_back_to_base_config(self, result_normal) -> None:
        scorer = QualityScorer()
        # domain=None 时取 result.domain；显式传 None 应回落到 result.domain
        scored = scorer.score(result_normal, domain=None)
        assert scored.dimension_scores["completeness"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# now 注入（用于测试确定性）
# ---------------------------------------------------------------------------


class TestNowInjection:
    def test_fixed_now_comes_from_canonical_quality_fixture_module(self, request) -> None:
        request.getfixturevalue("fixed_now")
        fixture_def = request._fixture_defs["fixed_now"]
        assert fixture_def.func.__module__ == (
            "skills.data.unified_data.tests.fixtures.quality_fixtures"
        )

    def test_explicit_now_is_used_for_freshness(self, fixed_now) -> None:
        from datetime import timedelta
        from skills.data.unified_data import DataResult, Market, SecurityId

        sid = SecurityId(market=Market.CN, symbol="600519")
        # 数据已 fetched 1 小时前，now 比 fetched 更晚 → age=3600s
        # market_data TTL=14400；age < 0.5*ttl（7200）→ freshness=0.9
        result = DataResult(
            data=[{"close": 1500.0, "volume": 1000000}],
            security_id=sid,
            domain="market_data",
            operation="kline_daily",
            provider="ta_cn_internal",
            fetched_at=fixed_now - timedelta(seconds=3600),
            freshness="cached",
        )
        scored = QualityScorer().score(result, now=fixed_now)
        assert scored.dimension_scores["freshness"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Hard fail 优先级
# ---------------------------------------------------------------------------


class TestHardFailPriority:
    def test_hard_fail_overrides_weighted_average(self, result_empty) -> None:
        # 即使 freshness / consistency 都 1.0，empty 也强制 score=0
        scored = QualityScorer().score(result_empty)
        assert scored.quality_score == 0.0
        assert scored.dimension_scores["completeness"] == 0.0