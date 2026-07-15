"""Quality 子包 — Phase 2 数据质量评估。

DESIGN-03-011 / SPEC-03-011 范围：纯计算组件，无 I/O 无 MongoDB。

Phase 2 提供的公共符号：

* :class:`QualityScorerConfig` — 评分配置（维度权重、等级阈值、域 TTL）
* :class:`QualityScorer` — 评分入口（接受 DataResult → ScoredResult）
* :class:`ScoredResult` — 评分返回 dataclass
* :class:`QualitySummary` — 质量汇总聚合（mongo_db=None → noop）
"""

from .config import QualityScorerConfig
from .scorer import QualityScorer, ScoredResult
from .summary import QualitySummary

__all__ = [
    "QualityScorerConfig",
    "QualityScorer",
    "ScoredResult",
    "QualitySummary",
]