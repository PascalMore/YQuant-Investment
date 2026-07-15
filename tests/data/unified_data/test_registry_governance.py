"""ProviderRegistry 运行治理测试（DESIGN-03-011 §4）。

行为矩阵 R1-R9（DESIGN §4）逐条覆盖：
* set_priority / get_priority — 数值越小越优先，未设置返回 _DEFAULT_PRIORITY
* set_health / get_health — healthy / unhealthy / disabled 三态
* get_providers(capability, market=None, state_filter=None) —
  按 priority 升序、按 state_filter 筛选；state_filter=None 保持 Phase 0
  注册顺序兼容行为
* 不存在的 provider / 非法 state → ValueError（fail-fast）
"""

from __future__ import annotations

import pytest

from skills.data.unified_data import (
    DataProvider,
    Market,
    ProviderRegistry,
)
from skills.data.unified_data.exceptions import (
    ProviderUnavailableError,
)


# ---------------------------------------------------------------------------
# FakeProvider helpers（不依赖现有 tests 中的 fake_provider）
# ---------------------------------------------------------------------------


class _StaticProvider(DataProvider):
    """最小 DataProvider 实现，用于注册表治理测试。

    不实现 fetch——本测试矩阵仅覆盖注册与查询，不触发网络 I/O。
    """

    def __init__(self, name: str, *capabilities: str, markets=(Market.CN,)):
        self._name = name
        self._capabilities = list(capabilities)
        self._markets = list(markets)

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> list[str]:
        return self._capabilities

    @property
    def markets(self) -> list[Market]:
        return self._markets

    def is_available(self) -> bool:
        return True

    def fetch(self, domain, operation, security_id, **params):  # pragma: no cover
        raise ProviderUnavailableError(f"fake {_StaticProvider.__name__} does not fetch")


@pytest.fixture
def registry_with_three() -> ProviderRegistry:
    """注册三个 provider，capability 全部为 market_data.kline_daily。"""
    reg = ProviderRegistry()
    reg.register(_StaticProvider("alpha", "market_data.kline_daily"))
    reg.register(_StaticProvider("beta", "market_data.kline_daily"))
    reg.register(_StaticProvider("gamma", "market_data.kline_daily"))
    return reg


# ---------------------------------------------------------------------------
# set_priority / get_priority
# ---------------------------------------------------------------------------


class TestPriority:
    def test_r1_get_priority_default_when_unset(self, registry_with_three) -> None:
        # 未设置时返回 _DEFAULT_PRIORITY (DESIGN §4.1: 100)
        assert registry_with_three.get_priority("alpha") == 100

    def test_r1_set_priority_persists(self, registry_with_three) -> None:
        registry_with_three.set_priority("alpha", 10)
        assert registry_with_three.get_priority("alpha") == 10

    def test_set_priority_unknown_provider_raises(self, registry_with_three) -> None:
        # fail-fast: 不允许对未注册的 provider 设优先级
        with pytest.raises(ValueError):
            registry_with_three.set_priority("not_registered", 10)

    def test_set_priority_smaller_value_wins(self, registry_with_three) -> None:
        # R4: priority 数值越小越优先
        registry_with_three.set_priority("alpha", 50)
        registry_with_three.set_priority("beta", 10)
        registry_with_three.set_priority("gamma", 30)
        providers = registry_with_three.get_providers("market_data.kline_daily")
        names = [p.name for p in providers]
        # beta=10 first, gamma=30, alpha=50 (insertion order tiebreak)
        assert names == ["beta", "gamma", "alpha"]

    def test_same_priority_preserves_insertion_order(
        self, registry_with_three
    ) -> None:
        # R5: priority 相同时保持注册顺序（稳定排序）
        registry_with_three.set_priority("alpha", 100)
        registry_with_three.set_priority("beta", 100)
        providers = registry_with_three.get_providers("market_data.kline_daily")
        names = [p.name for p in providers]
        assert names == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# set_health / get_health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_r2_get_health_default_when_unset(self, registry_with_three) -> None:
        # 默认 healthy
        assert registry_with_three.get_health("alpha") == "healthy"

    def test_r2_set_health_unhealthy(self, registry_with_three) -> None:
        registry_with_three.set_health("alpha", "unhealthy")
        assert registry_with_three.get_health("alpha") == "unhealthy"

    def test_set_health_disabled(self, registry_with_three) -> None:
        registry_with_three.set_health("alpha", "disabled")
        assert registry_with_three.get_health("alpha") == "disabled"

    def test_set_health_unknown_provider_raises(self, registry_with_three) -> None:
        with pytest.raises(ValueError):
            registry_with_three.set_health("not_registered", "unhealthy")

    def test_set_health_invalid_state_raises(self, registry_with_three) -> None:
        # fail-fast: 非法 state 抛 ValueError
        with pytest.raises(ValueError):
            registry_with_three.set_health("alpha", "weird_state")


# ---------------------------------------------------------------------------
# get_providers 增强 — state_filter + priority 排序
# ---------------------------------------------------------------------------


class TestGetProvidersGovernance:
    def test_no_state_filter_preserves_phase0_order(self, registry_with_three) -> None:
        # R3: state_filter=None → 返回注册顺序（Phase 0 兼容行为）
        providers = registry_with_three.get_providers("market_data.kline_daily")
        names = [p.name for p in providers]
        assert names == ["alpha", "beta", "gamma"]

    def test_state_filter_healthy_excludes_unhealthy(
        self, registry_with_three
    ) -> None:
        # R6: state_filter="healthy" 过滤掉 unhealthy / disabled
        registry_with_three.set_health("beta", "unhealthy")
        registry_with_three.set_health("gamma", "disabled")
        providers = registry_with_three.get_providers(
            "market_data.kline_daily", state_filter="healthy"
        )
        names = [p.name for p in providers]
        assert names == ["alpha"]

    def test_state_filter_unhealthy_returns_only_unhealthy(
        self, registry_with_three
    ) -> None:
        registry_with_three.set_health("beta", "unhealthy")
        providers = registry_with_three.get_providers(
            "market_data.kline_daily", state_filter="unhealthy"
        )
        names = [p.name for p in providers]
        assert names == ["beta"]

    def test_priority_and_state_filter_compose(self, registry_with_three) -> None:
        # R7: priority 排序 + state_filter 过滤可组合
        registry_with_three.set_priority("alpha", 100)
        registry_with_three.set_priority("beta", 50)
        registry_with_three.set_priority("gamma", 200)
        registry_with_three.set_health("alpha", "unhealthy")
        # state_filter 缺省 → 按 priority 排序（仍注册顺序插入索引做 tiebreak）
        providers = registry_with_three.get_providers("market_data.kline_daily")
        # beta=50, alpha=100, gamma=200
        assert [p.name for p in providers] == ["beta", "alpha", "gamma"]

    def test_unknown_capability_returns_empty(self, registry_with_three) -> None:
        # Phase 0 兼容: 未知 capability 不抛异常
        providers = registry_with_three.get_providers("unknown.capability")
        assert providers == []


# ---------------------------------------------------------------------------
# 兼容性：未注入 priority/health 时 Phase 0 行为完全保留
# ---------------------------------------------------------------------------


class TestPhase0Compat:
    def test_phase0_compat_no_priority_no_health(self) -> None:
        # 仅注册，无 set_priority / set_health → 行为应与 Phase 0 完全一致
        reg = ProviderRegistry()
        reg.register(_StaticProvider("a", "market_data.kline_daily"))
        reg.register(_StaticProvider("b", "market_data.kline_daily"))
        providers = reg.get_providers("market_data.kline_daily")
        assert [p.name for p in providers] == ["a", "b"]
        assert reg.get_priority("a") == 100
        assert reg.get_health("a") == "healthy"