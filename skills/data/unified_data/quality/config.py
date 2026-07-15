"""QualityScorer 配置模型 (DESIGN-03-011 §3.4).

继承 SPEC-03-011 §3.4 契约；纯 dataclass，无 I/O，无 MongoDB。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# 默认 TTL（秒）。Pascal 决策项 #1：Implement 使用以下候选值，
# Pascal 确认前可通过 domain_ttl 覆盖；不存在覆盖时按以下表查表。
_DEFAULT_DOMAIN_TTL: dict[str, int] = {
    "market_data": 14400,  # 4h
    "financial": 86400,    # 24h
    "news": 3600,          # 1h
    "metadata": 86400,     # 24h
    "index": 14400,        # 4h
}

# TTL 兜底值。未知域 → 14400（4h），与 SPEC §3.2.2 一致。
_FALLBACK_TTL: int = 14400

# 权重总和容忍度（spec: ±0.001）。
_WEIGHT_SUM_TOLERANCE: float = 0.001

# 等级阈值必填键。
_REQUIRED_TIER_KEYS: frozenset[str] = frozenset(
    {"direct_use", "warning", "degrade"}
)


@dataclass(frozen=True, slots=True)
class QualityScorerConfig:
    """QualityScorer 配置。所有阈值可被按域覆盖。

    详见 DESIGN-03-011 §3.4 / SPEC-03-011 §3.4。
    """

    # 各维度默认权重（总和=1.0，构造时校验）
    dimension_weights: dict[str, float] = field(default_factory=lambda: {
        "completeness": 0.35,
        "freshness": 0.30,
        "consistency": 0.15,
        "plausibility": 0.20,
    })

    # 等级阈值（全域默认值；< degrade → reject）
    tier_thresholds: dict[str, float] = field(default_factory=lambda: {
        "direct_use": 0.9,
        "warning": 0.7,
        "degrade": 0.3,
    })

    # 按域 TTL（秒）。未列出的域走 ``get_ttl_for_domain`` 的兜底。
    domain_ttl: dict[str, int] = field(
        default_factory=lambda: dict(_DEFAULT_DOMAIN_TTL)
    )

    # 按域的配置覆盖。key = 域 name。
    domain_overrides: dict[str, "QualityScorerConfig"] = field(
        default_factory=dict
    )

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        total = sum(self.dimension_weights.values())
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(
                f"dimension_weights must sum to 1.0 (±0.001), got {total}"
            )
        missing = _REQUIRED_TIER_KEYS - set(self.tier_thresholds.keys())
        if missing:
            raise ValueError(
                f"tier_thresholds missing required keys: {sorted(missing)}"
            )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_ttl_for_domain(self, domain: str) -> int:
        """返回指定域的 TTL（秒）。未配置时使用默认 14400。"""
        return self.domain_ttl.get(domain, _FALLBACK_TTL)

    def for_domain(self, domain: str) -> "QualityScorerConfig":
        """返回指定域的配置。如果有域覆盖则合并，否则返回自身。

        返回 ``self``（不是副本）便于消费方无需防御性检查。
        合并策略：override 的字段覆盖默认值；未在 override 中出现的字段
        沿用本配置。
        """
        override = self.domain_overrides.get(domain)
        if override is None:
            return self
        # 合并：覆盖优先级高于默认。
        return QualityScorerConfig(
            dimension_weights={
                **self.dimension_weights,
                **override.dimension_weights,
            },
            tier_thresholds={
                **self.tier_thresholds,
                **override.tier_thresholds,
            },
            domain_ttl={**self.domain_ttl, **override.domain_ttl},
            domain_overrides=override.domain_overrides,
        )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def minimal(cls) -> "QualityScorerConfig":
        return cls()


__all__ = ["QualityScorerConfig"]