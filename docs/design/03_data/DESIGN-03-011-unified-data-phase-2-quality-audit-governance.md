# DESIGN-03-011: Unified Data Phase 2 — 数据质量评估、审计与运行治理 详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-15 |
| 最后更新 | 2026-07-17 |
| 版本号 | V0.3 |
| 来源 RFC | RFC-03-011 |
| 来源 SPEC | SPEC-03-011 |
| 关联 Design | DESIGN-03-007（Unified Data Layer 详细设计 §Phase 2） |
| 关联 SPEC | SPEC-03-007、SPEC-03-009 |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| Phase 1 范围 | **Audit-only**：仅 Query Audit（AuditLogger）；QualitySummary 不注入；quality tier 仅观测不构成业务门禁 |

---

## 0. 基线锚定

本 Design 继承 DESIGN-03-007 的所有基线设计决策，仅新增或细化 Phase 2 范围内的设计。

**不变量**（继承自 SPEC-03-011 §0）：
1. **共享物理数据库**：Unified Data 与 TA-CN 共用 `tradingagents`。不依赖物理库隔离，通过集合前缀逻辑隔离。
2. **Internal-First 读取路径**：TA-CN 既有 → UD 物化 → Query Cache → 外部 Provider。外部刷新失败不阻断内部已有数据读取。
3. **DSA 边界**：DSA 仅在分析/参考中出现；不实现任何 DSA adapter。
4. **Collection Ownership 不可回写**：Unified Data 绝不回写、覆盖或加字段污染 TA-CN 既有无前缀集合。
5. **Task Center 先行**：Phase 2 不依赖 Task Center 调度。
6. **不改动已有公共契约**：不修改 SecurityId、DataResult、Market、DataProvider、FreshnessPolicy 等 Phase 0/1A/1B 的公开 API 签名。DataResult.quality_score 从 None 变为实际值属于字段增强，不影响签名。

**Phase 2 边界声明**：
- ✅ QualityScorer（数据质量评估组件，仅评数据可信度/可用性，不评投资价值）
- ✅ Registry 运行治理（priority + health_state）
- ✅ AuditLogger（追加式审计日志）
- ✅ QualitySummary（质量汇总聚合 — Phase 1 禁用，作为后续架构保留）
- ❌ 不实现 Sector Router capability
- ❌ 不实现 Registry 持久化到 MongoDB
- ❌ 不实现后台质量汇总周期性计算 / 自动 provider 健康检查 / 熔断器
- ❌ 不实现 ML 模型驱动质量评分
- ❌ 不实现 task_center 集成（Phase 5）
- ❌ 不实现 stock framework 集成（Phase 6）
- ❌ 不实现 DSA SQLite adapter
- ⚠️ **质量语义仅观测**（Pascal 已确认）：Phase 1 quality tier 不构成业务门禁，不阻断查询路径，仅用于监控和日志

---

## 1. 组件架构与数据流

### 1.1 组件图

```
DataRouter.query() 现有 Step 1-4 不变
         │
         ▼  DataResult (原始，无 quality_score)
┌──────────────────────────────────────────────┐
│              QualityScorer                    │
│  ┌──────────┬──────────┬──────────┬────────┐ │
│  │ 完整性   │ 时效性   │ 一致性   │ 合理性 │ │
│  └──────────┴──────────┴──────────┴────────┘ │
│  → ScoredResult(quality_score, dim_scores,    │
│                 quality_tier, warnings)        │
└───────────────────┬─────────────────────────┘
                     │ quality_score → DataResult.quality_score
                     │ warnings.append → DataResult.warnings
                     ▼
┌──────────────────────────────────────────────┐
│              AuditLogger                      │
│  → append-only 03_data_ud_query_audit        │
│  (catch-and-log, mongo_db=None → noop)       │
└───────────────────┬──────────────────────────┘
                     │ (内部触发 — Phase 1 禁用)
                     ▼
┌──────────────────────────────────────────────┐
│              QualitySummary (Phase 1 禁用)    │
│  → ⛔ 不写入 03_data_ud_quality_summary
│     （schema/TTL=365 天已确认，供后续启用）
└──────────────────────────────────────────────┘
```

### 1.2 调用时序

```
DataRouter.query()
  ├─ Step 1: TA-CN adapter (internal-first)
  ├─ Step 2: LocalMongoAdapter (物化层)
  ├─ Step 3: CacheManager (查询缓存)
  ├─ Step 4: External fallback chain
  │  (各 Step 内部: 按 priority 排序 → 过滤 health_state)
  │
  └─ return 前:
       ├─ 1. QualityScorer.score(result)         [可选, catch-and-log]
       │   → result.quality_score = scored.quality_score
       │   → result.warnings += scored.warnings
       │   → result.source_trace += ["quality_scored: tier=<tier>, score=<score>"]
       │
       ├─ 2. AuditLogger.log(result, duration_ms, params)  [可选, catch-and-log]
       │   → mongo.03_data_ud_query_audit.insert_one(doc)
       │   (Phase 1 不触发 QualitySummary.update — quality_summary=None)
       │   • params = query() 入口 caller mapping 的浅拷贝快照
       │   • duration_ms = (now - ts) 实际毫秒（非负整数）
       │
       └─ 3. return result
```

---

## 2. 文件清单与类职责

### 2.1 新增文件

| 文件 | 说明 | 类/函数 | 职责 |
|------|------|---------|------|
| `skills/data/unified_data/quality/__init__.py` | quality 子包导出 | `QualityScorer`, `ScoredResult`, `QualityScorerConfig` | 导出 quality 组件 |
| `skills/data/unified_data/quality/scorer.py` | QualityScorer 实现 | `QualityScorer` | 数据质量评估；接受 DataResult + context → ScoredResult |
| | | `ScoredResult` | 返回值 dataclass：quality_score, dimension_scores, quality_tier, warnings |
| | | `_score_completeness(result, domain, operation)` | 完整性评分（含核心字段检查） |
| | | `_score_freshness(result, domain, config, now)` | 时效性评分 |
| | | `_score_consistency(result)` | 来源一致性评分 |
| | | `_score_plausibility(result)` | 异常/合理性评分 |
| | | `_compute_tier(quality_score, thresholds)` | 等级判定 |
| `skills/data/unified_data/quality/config.py` | QualityScorerConfig | `QualityScorerConfig` | 维度权重、等级阈值、域覆盖配置 |
| `skills/data/unified_data/audit/__init__.py` | audit 子包导出 | `AuditLogger` | 导出 audit 组件 |
| `skills/data/unified_data/audit/logger.py` | AuditLogger 实现 | `AuditLogger` | 追加式审计日志；mongo_db=None→noop |
| `skills/data/unified_data/quality/summary.py` | QualitySummary 实现 | `QualitySummary` | 按(domain, security_id, date)聚合质量汇总；mongo_db=None→noop |
| `tests/data/unified_data/test_quality_scorer.py` | QualityScorer 测试 | — | 全部 N1-N12 场景 + 边界 + hard fail |
| `tests/data/unified_data/test_quality_config.py` | QualityScorerConfig 测试 | — | 默认值、域覆盖、domain_overrides 合并 |
| `tests/data/unified_data/test_audit_logger.py` | AuditLogger 测试 | — | AL-101~105 + schema 字段完整性 |
| `tests/data/unified_data/test_quality_summary.py` | QualitySummary 测试 | — | QS-101~105 + upsert 幂等 + get_summary |
| `tests/data/unified_data/test_registry_governance.py` | Registry 治理测试 | — | R1-R9 全部场景 |
| `tests/data/unified_data/test_router_quality.py` | Router 质量填充测试 | — | DR-301~307 + N 场景端到端 |
| `tests/data/unified_data/fixtures/quality_fixtures.py` | 质量测试 fixture | `quality_config_default`, `quality_config_market_data` 等 | 各种评分配置 fixture |

### 2.2 修改的文件

| 文件 | 修改类型 | 改动描述 |
|------|----------|----------|
| `skills/data/unified_data/__init__.py` | 新增导出 | 新增 QualityScorer、ScoredResult、QualityScorerConfig、AuditLogger、QualitySummary |
| `skills/data/unified_data/registry.py` | 新增方法 | 新增 priority/health_state 治理方法 + `get_providers(state_filter=)` 增强 |
| `skills/data/unified_data/router.py` | 参数 + 流程 | `__init__` 新增 quality_scorer, audit_logger 参数；`query()` 返回前评分+审计调用；`_resolve_external_chain` 集成 health_state 过滤 |

### 2.3 禁止修改的文件

Phase 0/1A/1B 的下列文件不因 Phase 2 修改：
- `skills/data/unified_data/models/__init__.py`（DataResult 仅字段值变更，不修改签名）
- `skills/data/unified_data/provider.py`（DataProvider 基类不变）
- `skills/data/unified_data/freshness.py`（FreshnessPolicy 不变）
- `skills/data/unified_data/config.py`（UnifiedDataConfig 不变）
- `skills/data/unified_data/client.py`（UnifiedDataClient 不变）
- `skills/data/unified_data/cache_manager.py`（CacheManager 不变）
- `skills/data/unified_data/local_mongo_adapter.py`（LocalMongoAdapter 不变）
- 任何 Phase 1C 的 03-010 文档

---

## 3. QualityScorer 详细设计

### 3.1 接口

```python
@dataclass(frozen=True, slots=True)
class ScoredResult:
    """QualityScorer.score() 的返回值。"""
    quality_score: float           # [0, 1]
    dimension_scores: dict[str, float]  # {"completeness": 1.0, "freshness": 0.9, ...}
    quality_tier: str              # "direct_use" | "warning" | "degrade" | "reject"
    warnings: list[str]            # 触发告警/降级的具体原因

class QualityScorer:
    def __init__(self, config: QualityScorerConfig | None = None) -> None: ...

    def score(
        self,
        result: DataResult,
        *,
        domain: str | None = None,
        now: datetime | None = None,
    ) -> ScoredResult:
        \"\"\"对 DataResult 进行质量评分。

        内部顺序：completeness → freshness → consistency → plausibility。
        各维度评分函数独立，domain/operation 从 result.capability 提取。
        \"\"\"
        domain = domain or result.domain
        # 从 capability "domain.operation" 提取 operation
        operation = result.capability.split(".")[-1] if result.capability else None

        comp_score, comp_warnings = _score_completeness(result, domain, operation)
        fresh_score, fresh_warnings = _score_freshness(result, domain, self._config, now)
        cons_score, cons_warnings = _score_consistency(result)
        plaus_score, plaus_warnings = _score_plausibility(result)

        dim_scores = {
            "completeness": comp_score,
            "freshness": fresh_score,
            "consistency": cons_score,
            "plausibility": plaus_score,
        }
        dim_warnings = {
            "completeness": comp_warnings,
            "freshness": fresh_warnings,
            "consistency": cons_warnings,
            "plausibility": plaus_warnings,
        }
        return _compute_overall(dim_scores, dim_warnings, self._config, domain)
```

### 3.2 四维度评分规则（冻结设计）

#### 3.2.1 完整性（completeness）— 默认权重 0.35

```python
# Phase 2: 已知 domain/operation 的核心必填字段常量
# Key 格式: "{domain}.{operation}"，Value: 必填字段名集合
# Phase 2 仅覆盖 market_data.kline_daily（close + volume）
# 其他 domain/operation 的深度字段检查属于 Phase 3+
_CORE_FIELDS: dict[str, set[str]] = {
    "market_data.kline_daily": {"close", "volume"},
}


def _score_completeness(
    result: DataResult,
    domain: str | None = None,
    operation: str | None = None,
) -> tuple[float, list[str]]:
    """完整性评分。

    输入信号: DataResult.is_empty(), DataResult.data 字段存在性
    硬失败: is_empty()=True → quality_score=0（全局面硬失败）

    Phase 2 核心字段检查:
    - 已知 domain/operation 的 _CORE_FIELDS 缺失按比例扣分（非 hard fail）
    - 未知 domain/operation → 跳过字段级检查（Phase 3+ 覆盖）
    """
    dim_warnings: list[str] = []

    # 空结果硬失败
    if result.is_empty():
        return 0.0, ["empty result: no usable payload"]

    # 核心必填字段检查（Phase 2：仅已知 domain/operation）
    if domain is not None and operation is not None:
        cap_key = f"{domain}.{operation}"
        required = _CORE_FIELDS.get(cap_key)
        if required is not None and isinstance(result.data, dict):
            missing = {f for f in required
                       if f not in result.data or result.data.get(f) is None}
            if missing:
                total = len(required)
                present = total - len(missing)
                score = present / total
                dim_warnings.append(
                    f"missing required fields: {', '.join(sorted(missing))}"
                )
                # 字段缺失是 degrade，不触发 hard_fail
                return score, dim_warnings

        # list[dict] payload（e.g., daily-bar kline records）
        # 逐条记录检查核心字段；得分 = 所有记录中实际存在的核心字段值数 / 总应存在值数
        # None 和键缺失均视为缺失；非 dict 元素计为 0（不报错，评分自然降低）
        elif required is not None and isinstance(result.data, list):
            if len(result.data) == 0:
                return 1.0, []  # 空列表无记录可校验，视为 schema 完整

            total_expected = len(result.data) * len(required)
            total_present = 0
            missing_fields: set[str] = set()

            for idx, record in enumerate(result.data):
                if not isinstance(record, dict):
                    continue  # 非 dict 元素贡献 0 个 present 值
                for f in required:
                    if f in record and record[f] is not None:
                        total_present += 1
                    else:
                        missing_fields.add(f)

            if total_present < total_expected:
                score = total_present / total_expected
                dim_warnings.append(
                    f"missing required fields: "
                    f"{', '.join(sorted(missing_fields))}"
                )
                return score, dim_warnings

    # 非空 payload + 无已定义核心字段缺失
    return 1.0, []
```

#### 3.2.2 时效性（freshness）— 默认权重 0.30

```python
def _score_freshness(
    result: DataResult,
    domain: str,
    config: QualityScorerConfig,
    now: datetime,
) -> tuple[float, list[str]]:
    """时效性评分。

    输入信号: result.freshness, result.fetched_at, domain → TTL 配置
    硬失败: freshness="stale" 或 "empty" → quality_score=0
            (freshness="empty" 与 completeness 硬失败重叠，由 completeness 兜底)

    评分公式:
        age = now - fetched_at (秒)
        ttl = config.get_ttl_for_domain(domain)

        freshness=realtime → 1.0
        freshness=delayed  → 1.0  (财务/新闻等延迟数据视为预期)
        freshness=cached:
            age <= 0.5*ttl           → 0.9
            0.5*ttl < age <= 0.9*ttl → 0.6 + 0.3*(ttl - age)/(0.5*ttl)
            age > 0.9*ttl            → 0.2
        freshness=stale → 0.0
        freshness=empty → 0.0
    """
```

**域 TTL 默认值（Pascal 决策项 #1）**：

| 域 | TTL 默认值 | 说明 |
|----|-----------|------|
| market_data | 14400（4h） | 日线行情，T+1 的 TTL 可放宽 |
| financial | 86400（24h） | 财务数据发布频率更低 |
| news | 3600（1h） | 新闻时效性高 |
| metadata | 86400（24h） | 基础信息变更频率低 |
| index | 14400（4h） | 同行情 |
| 未匹配域 | 14400（4h） | 兜底 |

> ⚠️ 上述 TTL 值为默认候选值，Design 阶段 Pascal 确认后方可在 Implement 中固化。确认前 Implement 使用这些默认值，但配置必须保留可覆盖接口。

#### 3.2.3 来源一致性（consistency）— 默认权重 0.15

```python
def _score_consistency(result: DataResult) -> tuple[float, list[str]]:
    """来源一致性评分。

    输入信号: result.source_trace（冲突标记字符串）, result.warnings
    硬失败: 无（来源冲突不阻断使用）

    Phase 2 是轻量级一致性检查：只检查 source_trace 中是否有 explicit
    冲突标记（格式 "provider(vs_other:field_diverges)"）。
    跨数据源深度交叉校验（同时取 Tushare + AKShare 逐字段对比）属于 Phase 3+。

    评分逻辑:
        source_trace 不含冲突标记 → 1.0
        source_trace 含已解析冲突 → 0.7
            (冲突标记后紧跟相同 provider 的 "resolved" 标记)
        source_trace 含活跃冲突 → 0.3
            (有冲突标记但无 resolved 标记)
    """
```

#### 3.2.4 异常/合理性（plausibility）— 默认权重 0.20

```python
def _score_plausibility(result: DataResult) -> tuple[float, list[str]]:
    """异常/合理性评分。

    输入信号: result.data 中可检查的数字字段
    硬失败: close ≤ 0 且 domain 为 market_data → quality_score=0

    Phase 2 是轻量级边界检查：
    - market_data 域：检查 close/open/high/low/volume/amount > 0
    - 其他域：暂不检查（返回 1.0，无警告）
    - 深度异常检测（Z-score、IQR、统计分布偏离）属于 Phase 3+

    评分逻辑:
        data 为 None/非标准结构 → 返回 0.5（无法判定）+ warning "unable to validate"
        全部检查通过 → 1.0
        核心字段违反边界 → 0.0（hard fail）
        非核心字段违反边界 → 0.3 + warning
    """
```

### 3.3 总分计算与等级

```python
def _compute_overall(
    dim_scores: dict[str, float],
    dim_warnings: dict[str, list[str]],
    config: QualityScorerConfig,
    domain: str,
) -> tuple[float, str, list[str]]:
    """计算总分、等级与合并 warnings。

    规则:
    1. 任何维度 hard_fail → quality_score = 0.0（hard fail 优先级高于加权平均）
    2. 无 hard_fail → quality_score = sum(weight[d] * score[d])，截断至 [0, 1]
    3. 等级判定使用 config.tier_thresholds

    Hard fail 判定条件：
    - completeness: score=0.0 → hard fail（源于 is_empty()=True 或所有已知核心字段缺失）
    - freshness: stale/empty → hard fail (score=0.0)
    - consistency: 无 hard fail
    - plausibility: 核心字段违反边界 → hard fail (score=0.0)
    """
    hard_fail = any(s == 0.0 for s in dim_scores.values())
    if hard_fail:
        return 0.0, "reject", _flatten_warnings(dim_warnings)

    cfg = config.for_domain(domain)
    total = sum(
        cfg.dimension_weights.get(dim, 0.0) * score
        for dim, score in dim_scores.items()
    )
    total = max(0.0, min(1.0, total))  # 截断

    tier = _compute_tier(total, cfg.tier_thresholds)
    return total, tier, _flatten_warnings(dim_warnings)

def _compute_tier(score: float, thresholds: dict[str, float]) -> str:
    if score >= thresholds.get("direct_use", 0.9):
        return "direct_use"
    if score >= thresholds.get("warning", 0.7):
        return "warning"
    if score >= thresholds.get("degrade", 0.3):
        return "degrade"
    return "reject"
```

### 3.4 QualityScorerConfig 详细设计

```python
@dataclass(frozen=True, slots=True)
class QualityScorerConfig:
    """QualityScorer 配置。所有阈值可被按域覆盖。"""

    # 各维度默认权重（总和=1.0，构造时校验）
    dimension_weights: dict[str, float] = field(default_factory=lambda: {
        "completeness": 0.35,
        "freshness": 0.30,
        "consistency": 0.15,
        "plausibility": 0.20,
    })

    # 等级阈值（全域默认值）
    tier_thresholds: dict[str, float] = field(default_factory=lambda: {
        "direct_use": 0.9,
        "warning": 0.7,
        "degrade": 0.3,
        # < 0.3 → reject
    })

    # 域 TTL（秒），按域配置 freshness 计算中的 TTL 值
    domain_ttl: dict[str, int] = field(default_factory=lambda: {
        "market_data": 14400,
        "financial": 86400,
        "news": 3600,
        "metadata": 86400,
        "index": 14400,
    })

    # 按域的配置覆盖（key = domain name）
    domain_overrides: dict[str, "QualityScorerConfig"] = field(default_factory=dict)

    def for_domain(self, domain: str) -> "QualityScorerConfig":
        """返回指定域的配置。如果有域覆盖则合并，否则返回自身。"""
        override = self.domain_overrides.get(domain)
        if override is not None:
            # 合并：覆盖优先级高于默认
            merged = QualityScorerConfig(
                dimension_weights={**self.dimension_weights, **override.dimension_weights},
                tier_thresholds={**self.tier_thresholds, **override.tier_thresholds},
                domain_ttl={**self.domain_ttl, **override.domain_ttl},
                domain_overrides=override.domain_overrides,  # 域覆盖的域覆盖
            )
            return merged
        return self

    def get_ttl_for_domain(self, domain: str) -> int:
        """返回指定域的 TTL（秒）。未配置时使用默认 14400。"""
        return self.domain_ttl.get(domain, 14400)

    def __post_init__(self) -> None:
        """校验维度权重总和为 1.0（允许 ±0.001 浮点误差）。"""
        total = sum(self.dimension_weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"dimension_weights must sum to 1.0, got {total}"
            )
        # 校验 tier_thresholds 包含必需键
        required = {"direct_use", "warning", "degrade"}
        missing = required - set(self.tier_thresholds.keys())
        if missing:
            raise ValueError(
                f"tier_thresholds missing required keys: {missing}"
            )

    @classmethod
    def minimal(cls) -> "QualityScorerConfig":
        return cls()

### 3.5 行为矩阵（N1-N12 全部场景）

| 场景 | DataResult 特征 | completeness | freshness | consistency | plausibility | quality_score | quality_tier | warnings |
|------|----------------|-------------|-----------|-------------|-------------|---------------|-------------|----------|
| N1 正常 TA-CN 命中 | freshness="delayed", 非空 payload, fresh | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | direct_use | [] |
| N2 缓存命中（新鲜） | freshness="cached", age < 50% TTL | 1.0 | 0.9 | 1.0 | 1.0 | 0.97* | direct_use | [] |
| N3 外部 Provider 实时 | freshness="realtime", 非空 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | direct_use | [] |
| N4 空结果 | is_empty()=True | **0.0** | — | — | — | **0.0** | reject | ["empty result"] |
| N5 过期结果 | freshness="stale" | 1.0 | **0.0** | 1.0 | 1.0 | **0.0** | reject | ["stale data"] |
| N6 空 payload（empty provider） | provider="empty", is_empty()=True | **0.0** | — | — | — | **0.0** | reject | ["empty result"] |
| N7 相邻过期缓存 | freshness="cached", age > 90% TTL | 1.0 | 0.2 | 1.0 | 1.0 | 0.76* | warning | ["cache near expiry"] |
| N8 错误结果 | provider="error" | **0.0** | — | — | — | **0.0** | reject | ["all providers failed"] |
| N9 来源冲突 | source_trace 含冲突标记 | 1.0 | 1.0 | 0.3 | 1.0 | 0.895 | warning | ["source conflict: price divergence"] |
| N10 异常值（close ≤ 0） | data 含 close=0 | 1.0 | 1.0 | 1.0 | **0.0** | **0.0** | reject | ["invalid close value"] |
|| N11 部分字段缺失 | is_empty=False, `data=list[dict]` daily-bar（1 条记录，仅含 close，volume 缺失） | 0.5 | 1.0 | 1.0 | 1.0 | 0.825 | warning | ["missing required fields: volume"] |
| N12 财务数据（较老） | freshness="delayed", age > 6h, domain=financial | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | direct_use | [] |

> `*` 加权分示例基于默认权重 (0.35, 0.30, 0.15, 0.20)。N7: 0.35×1.0 + 0.30×0.2 + 0.15×1.0 + 0.20×1.0 = 0.76。N9: 0.35×1.0 + 0.30×1.0 + 0.15×0.3 + 0.20×1.0 = 0.895（未舍入）。N11: 0.35×0.5 + 0.30×1.0 + 0.15×1.0 + 0.20×1.0 = 0.825。<br>`**` N11 的 completeness=0.5 来自 list[dict] 语义：`data=[{"close": 150.0}]`（1 条记录 × 2 个核心字段 = 2 应存值，实际 1 个 close 存在 → 1/2 = 0.5）。详见 §3.2.1 的 list[dict] 分支。`result_missing_volume` fixture（`data=[{"close": 150.0}]`）是 N11 的典型触发输入。

### 3.6 分域配置覆盖示例（Pascal 决策项 #2）

下列域覆盖在 Implement 阶段作为默认值使用，但 Pascal 可在生产写入确认时修正：

```python
# 在 UnifiedDataClient 或应用层注入时使用：
domain_configs = {
    "market_data": QualityScorerConfig(
        dimension_weights={"completeness": 0.25, "freshness": 0.40, "consistency": 0.15, "plausibility": 0.20},
        domain_ttl={"market_data": 14400},
    ),
    "financial": QualityScorerConfig(
        dimension_weights={"completeness": 0.50, "freshness": 0.10, "consistency": 0.20, "plausibility": 0.20},
        domain_ttl={"financial": 86400},
    ),
    "news": QualityScorerConfig(
        dimension_weights={"completeness": 0.30, "freshness": 0.35, "consistency": 0.15, "plausibility": 0.20},
        domain_ttl={"news": 3600},
    ),
    "metadata": QualityScorerConfig(
        dimension_weights={"completeness": 0.50, "freshness": 0.10, "consistency": 0.20, "plausibility": 0.20},
        domain_ttl={"metadata": 86400},
    ),
}
```

---

## 4. Registry 运行治理详细设计

### 4.1 ProviderRegistry 新增方法

在现有 `skills/data/unified_data/registry.py` 的 `ProviderRegistry` 类中新增：

```python
class ProviderRegistry:
    # ... 现有 Phase 0/1B-A 方法不变（register, unregister, clear, get, list_*,
    #     get_providers, has_capability, set/get_external_fallback_chains）...

    # ------------------------------------------------------------------
    # Phase 2: Priority & Health State
    # ------------------------------------------------------------------

    # 默认优先级值
    _DEFAULT_PRIORITY: int = 100

    def set_priority(self, name: str, priority: int) -> None:
        """设置 provider 的优先级（数值越小越优先）。"""
        if name not in self._providers:
            raise ValueError(f"Provider {name!r} is not registered")
        # _priorities 为 dict[str, int]，__init__ 时初始化
        self._priorities[name] = priority

    def get_priority(self, name: str) -> int:
        """返回 provider 的优先级。未设置时返回 100。"""
        return self._priorities.get(name, self._DEFAULT_PRIORITY)

    def set_health(self, name: str, state: str) -> None:
        """设置 provider 的运行健康状态。

        Args:
            name: provider 名称。
            state: "healthy" | "unhealthy" | "disabled"
        Raises:
            ValueError: provider 未注册或 state 非法。
        """
        if name not in self._providers:
            raise ValueError(f"Provider {name!r} is not registered")
        if state not in ("healthy", "unhealthy", "disabled"):
            raise ValueError(
                f"state must be 'healthy', 'unhealthy', or 'disabled', got {state!r}"
            )
        self._health_states[name] = state

    def get_health(self, name: str) -> str:
        """返回 provider 的健康状态。未设置时返回 'healthy'。"""
        return self._health_states.get(name, "healthy")

    def get_providers(
        self,
        capability: str,
        market: Market | str | None = None,
        state_filter: str | None = None,
    ) -> list[DataProvider]:
        """按 capability + market + 健康状态筛选 provider。

        Args:
            capability: 能力字符串。
            market: 可选市场筛选。
            state_filter: 可选健康状态筛选。
                None → 返回所有注册的（兼容 Phase 0 行为）。
                "healthy" → 仅返回 healthy 的 provider。
                "unhealthy" → 仅返回 unhealthy 的 provider。
                "disabled" → 仅返回 disabled 的 provider。

        返回按 priority 升序排序的列表（priority 相同时保持注册顺序）。
        始终按 priority 稳定排序；当未调用 set_priority 时（全部为默认值 100），
        稳定排序保持注册顺序，实现与 Phase 0 的语义兼容。
        """
        # 获取基础列表（同 Phase 0）
        capability = self._coerce_capability_or_none(capability)
        if capability is None:
            return []
        providers = list(self._by_capability.get(capability, ()))
        if market is not None:
            market_enum = self._coerce_market(market)
            if market_enum is None:
                return []
            providers = [p for p in providers if market_enum in p.markets]

        # 按 state_filter 筛选
        if state_filter is not None:
            providers = [
                p for p in providers
                if self._health_states.get(p.name, "healthy") == state_filter
            ]

        # 按 priority 排序（稳定性保持注册顺序）
        providers.sort(key=lambda p: (
            self._priorities.get(p.name, self._DEFAULT_PRIORITY),
            # 使用插入顺序作为 tiebreaker
            list(self._providers.keys()).index(p.name),
        ))
        return providers

    # 初始化增强：在 __init__ 中增加 _priorities 和 _health_states
    def __init__(self) -> None:
        self._providers: dict[str, DataProvider] = {}
        self._by_capability: dict[str, list[DataProvider]] = {}
        self._external_fallback_chains: dict[str, list[str]] = {}
        # Phase 2 additions
        self._priorities: dict[str, int] = {}       # provider_name → priority
        self._health_states: dict[str, str] = {}    # provider_name → "healthy"|"unhealthy"|"disabled"
```

### 4.2 Router 集成

**`_resolve_external_chain` 增强**：在返回 chain 之前，对 chain 中每个 provider 检查 health_state：

```python
def _resolve_external_chain(self, capability: str) -> list[str]:
    """Resolve the external fallback chain for ``capability``。

    Phase 2 增强：在返回前过滤掉 unhealthy/disabled 的 provider。
    """
    # 原有优先级逻辑不变...
    chain = self._external_chains.get(capability)
    if chain:
        return self._filter_healthy(chain)
    chain = self._registry.get_external_fallback_chain(capability)
    if chain:
        return self._filter_healthy(chain)
    chain = self._config.fallback_for(capability)
    if chain:
        return self._filter_healthy(list(chain))
    providers = self._registry.get_providers(capability, state_filter="healthy")
    return [p.name for p in providers]

def _filter_healthy(self, names: list[str]) -> list[str]:
    """过滤 health_state，healthy 保留，unhealthy/disabled 记录 trace 然后跳过。"""
    healthy = []
    for name in names:
        state = self._registry.get_health(name) if hasattr(self._registry, 'get_health') else "healthy"
        if state == "healthy":
            healthy.append(name)
        # unhealthy/disabled 的 trace 在 _query_external_chain 的 iter 中记录
    return healthy
```

**`_query_external_single` 增强**：在 provider override 分支中检查 health_state：

```python
def _query_external_single(self, provider_name, ...):
    # 在现有 is_available() 检查之前，增加 health_state 检查
    health = self._registry.get_health(provider_name) if hasattr(self._registry, 'get_health') else "healthy"
    if health != "healthy":
        trace.append(f"{provider_name}(health: {health})")
        return self._build_error_result(...)
    # ... 原有流程 ...
```

### 4.3 并发安全

ProviderRegistry 的所有现有方法都是单线程调用（Unified Data Layer 当前设计），Phase 2 的 priority/health_state 方法同样为单线程安全。如果未来引入并发访问，需要加锁。当前不加锁——Phase 3+ 如需并发再引入。

### 4.4 unregister 与 clear 生命周期治理

Phase 2 新增 `_priorities` 和 `_health_states` 字段后，现有 `unregister()` 和 `clear()` 方法的生命周期必须同步更新，防止重注册时残留旧状态。

#### 4.4.1 unregister 更新

```python
def unregister(self, name: str) -> bool:
    \"\"\"Remove the provider named ``name``. Returns whether anything was removed.

    Phase 2 增强：清理 _priorities / _health_states 中该 provider 的残留状态，
    避免重注册时残留旧 priority 或旧 health_state。
    \"\"\"
    provider = self._providers.pop(name, None)
    if provider is None:
        return False
    for capability, providers in list(self._by_capability.items()):
        self._by_capability[capability] = [
            p for p in providers if p.name != name
        ]
        if not self._by_capability[capability]:
            self._by_capability.pop(capability, None)
    # Phase 2: 原子清理 priority 和 health state
    self._priorities.pop(name, None)
    self._health_states.pop(name, None)
    return True
```

**关键语义**：
- cleanup 位置：在确认 provider 存在（`pop` 成功）后、`return True` 前执行。
- unknown name 路径：`_providers.pop(name, None)` 返回 `None` → `return False`，不进入 cleanup（与 Phase 0 行为一致）。
- 重注册语义：`unregister("tushare")` → `register(tushare_2)` → `get_priority("tushare")` 返回 `100`、`get_health("tushare")` 返回 `"healthy"`（旧值已清除）。

#### 4.4.2 clear 更新

```python
def clear(self) -> None:
    \"\"\"Remove every registered provider (test convenience).

    Phase 2 增强：作为完整的 Registry reset，必须同时清除
    _priorities / _health_states，确保 clear → re-register 无残留。
    \"\"\"
    self._providers.clear()
    self._by_capability.clear()
    # Phase 2: 完整 reset priority 和 health state
    self._priorities.clear()
    self._health_states.clear()
```

**关键语义**：
- `clear()` 是完整 Registry reset：所有注册、能力索引、运行治理状态全部清空。
- `clear()` 后任何 `register()` 调用看到的都是全新状态：priority=100、health="healthy"。
- 不影响 `_external_fallback_chains`（Phase 1B-A 的配置层，非 provider 注册状态）。

#### 4.4.3 行为矩阵

| 场景 | 操作序列 | 预期状态 |
|------|----------|----------|
| UC-1 正常 unregister | set_priority("A", 5) → set_health("A", "disabled") → unregister("A") → register(A) | priority=100, health="healthy" |
| UC-2 clear 后重注册 | set_priority("A", 5) → set_health("A", "disabled") → clear() → register(A) | priority=100, health="healthy" |
| UC-3 unregister unknown | unregister("nonexistent") | return False, 无副作用 |
| UC-4 unregister + 其他 provider | register(A) → register(B) → set_priority("A", 5) → unregister("A") → register(A) | A: priority=100, health="healthy"; B: 不受影响 |

---

## 5. AuditLogger 详细设计

### 5.1 接口与实现

```python
class AuditLogger:
    """追加式查询审计日志组件。

    mongo_db=None → noop 模式（不写任何数据，不抛异常）。
    写入采用 catch-and-log 模式。
    """

    def __init__(
        self,
        mongo_db: Any = None,
        collection_name: str = "03_data_ud_query_audit",
        ttl_days: int = 365,
        quality_summary: "QualitySummary | None" = None,
    ) -> None:
        self._mongo_db = mongo_db
        self._collection_name = collection_name
        self._ttl_days = ttl_days
        self._quality_summary = quality_summary

    def log(
        self,
        result: DataResult,
        *,
        consumer: str = "unified_data",
        duration_ms: int = 0,
        params: dict | None = None,
    ) -> None:
        """记录一次查询审计事件。catch-and-log，不抛到调用方。"""
        if self._mongo_db is None:
            return  # noop

        try:
            doc = self._build_document(result, consumer, duration_ms, params)
            self._mongo_db[self._collection_name].insert_one(doc)

            # 内部触发 QualitySummary 更新
            if self._quality_summary is not None:
                self._quality_summary.update(
                    result,
                    quality_score=result.quality_score,
                    quality_tier=_infer_tier_from_score(result.quality_score),
                    now=doc["fetched_at"],
                )
        except Exception as exc:
            logger.warning("AuditLogger.log failed (catch-and-log): %s", exc)
```

### 5.2 审计文档 Schema（已确认）

集合：`tradingagents.03_data_ud_query_audit`

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `_id` | ObjectId | 自动生成 | 主键 |
| `audit_id` | string | UUID v4 | 全局唯一审计事件标识 |
| `security_id` | string | "CN:600519" | SecurityId.canonical |
| `market` | string | "CN" | 市场代码 |
| `capability` | string | "market_data.kline_daily" | domain.operation |
| `consumer` | string | "unified_data" | 调用方标识 |
| `fetched_at` | datetime | ISODate | 查询开始时间（UTC） |
| `duration_ms` | int | 142 | 查询总耗时（毫秒） |
| `provider` | string | "ta_cn_internal" | 最终返回的 provider |
| `source_trace` | list[str] | ["ta_cn_internal(ok)"] | 完整 provider 链 |
| `freshness` | string | "delayed" | 最终 freshness label |
| `quality_score` | float | 0.95 | QualityScorer 输出评分 |
| `quality_tier` | string | "direct_use" | 质量等级 |
| `success` | bool | true | 是否成功获取数据 |
| `error_message` | string\|null | null | 当 provider="error" 时记录错误信息 |
| `params` | dict | {"limit": 120} | 查询参数（不含敏感字段） |
| `quality_warnings` | list[str] | [] | 质量告警列表 |

### 5.3 索引（Pascal 决策项 #3）

候选索引（Implement 使用默认候选值，Pascal 确认后在生产创建）：

```javascript
// 1. TTL 索引（按 fetched_at 过期，Pascal 已确认：365 天）
// CreateIndexOptions: { expireAfterSeconds: 365 * 24 * 3600 }
db.03_data_ud_query_audit.createIndex(
  {"fetched_at": 1},
  {"expireAfterSeconds": 31536000}
)

// 2. 按 security_id 查询（排查特定标的审计记录）
// DDL pending Pascal confirmation
db.03_data_ud_query_audit.createIndex(
  {"security_id": 1, "fetched_at": -1}
)

// 3. 按 capability 聚合查询
// DDL pending Pascal confirmation
db.03_data_ud_query_audit.createIndex(
  {"capability": 1, "fetched_at": -1}
)
```

> ⚠️ Pascal 已确认 TTL=365 天。二级索引设计为候选值。Implement 代码中：
> - `AuditLogger.__init__` 的 `ttl_days` 参数默认 365（Pascal 已确认）
> - 所有索引在 Pascal 确认前**不**在代码/测试/脚本中硬编码 `createIndex`
> - 测试使用 mongomock，mongomock 不支持 TTL 索引（静默忽略）

### 5.4 行为矩阵

| 场景 | mongo_db | 预期行为 | 验证命令 |
|------|----------|----------|----------|
| AL-101 | None | noop，不写 MongoDB，不抛异常 | 调用 log()，assert 无异常 |
| AL-102 | mongomock.Database | 写入 mongomock | 查询 mongomock collection，assert doc 存在 |
| AL-103 | pymongo.Database | 写入生产审计集合 | Production Gate smoke test |
| AL-104 | 写入异常（连接断开） | catch-and-log（logger.warning），不阻断查询返回值 | mock insert_one 抛异常，assert 无异常传播 |
| AL-105 | 写入抛出非预期异常 | catch-and-log（logger.warning + exception），不阻断 | mock insert_one 抛 RuntimeError，assert 无异常传播 |

---

## 6. QualitySummary 详细设计

### 6.1 Phase 1 声明

**QualitySummary 在整个 Phase 1 禁用，不注入到 AuditLogger**（`AuditLogger.__init__` 的 `quality_summary` 参数始终保持 `None`）。以下 schema、TTL 和索引作为后续启用时的已确认值记录在案。

### 6.2 接口与实现（架构保留）

```python
class QualitySummary:
    """按 (domain, security_id, date) 聚合的质量汇总。

    mongo_db=None → noop 模式。
    每次 AuditLogger.log() 写入后触发 upsert。
    """

    def __init__(
        self,
        mongo_db: Any = None,
        collection_name: str = "03_data_ud_quality_summary",
    ) -> None:
        self._mongo_db = mongo_db
        self._collection_name = collection_name

    def update(
        self,
        result: DataResult,
        *,
        quality_score: float | None,
        quality_tier: str | None,
        now: datetime | None = None,
    ) -> None:
        """更新质量汇总。catch-and-log。"""
        if self._mongo_db is None:
            return  # noop

        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        date_str = now.strftime("%Y-%m-%d")
        doc_id = f"{result.domain}:{result.security_id.canonical}:{date_str}"
        provider = result.provider

        try:
            self._mongo_db[self._collection_name].update_one(
                {"_id": doc_id},
                {
                    "$setOnInsert": {
                        "domain": result.domain,
                        "security_id": result.security_id.canonical,
                        "date": date_str,
                    },
                    "$inc": {
                        "query_count": 1,
                        f"provider_distribution.{provider}": 1,
                    },
                    "$set": {
                        "last_updated": now,
                        # min/max 在 upsert 后用 $min/$max
                    },
                    "$min": {"min_quality_score": quality_score if quality_score is not None else 999},
                    "$max": {"max_quality_score": quality_score if quality_score is not None else -1},
                    # avg_quality_score 使用维护的 running sum / count
                },
                upsert=True,
            )

            # 更新 running avg：先读再写（每次都读一次）
            current = self._mongo_db[self._collection_name].find_one({"_id": doc_id})
            if current and current.get("query_count", 0) > 0:
                # 重新计算 avg = sum/count；用 $set 写入避免浮点累积误差
                pass  # 具体实现见 §6.3
        except Exception as exc:
            logger.warning("QualitySummary.update failed (catch-and-log): %s", exc)

    def get_summary(
        self,
        domain: str,
        security_id: SecurityId,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """查询质量汇总。

        Returns:
            匹配的原始 MongoDB 文档列表。无数据时返回 []。
        """
        if self._mongo_db is None:
            return []

        query: dict[str, Any] = {
            "domain": domain,
            "security_id": security_id.canonical,
        }
        date_filter: dict[str, Any] = {}
        if from_date is not None:
            date_filter["$gte"] = from_date
        if to_date is not None:
            date_filter["$lte"] = to_date
        if date_filter:
            query["date"] = date_filter

        return list(
            self._mongo_db[self._collection_name]
            .find(query)
            .sort("date", -1)
        )
```

### 6.3 文档 Schema（已确认 — TTL 已确认）

TTL：365 天（按 `date` 自动过期；Phase 1 不启用，TTL 作为后续启用时的已确认值）

集合：`tradingagents.03_data_ud_quality_summary`

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `_id` | string | "market_data.kline_daily:CN:600519:2026-07-15" | 复合键 = `domain:security_id:date` |
| `domain` | string | "market_data" | 域 |
| `security_id` | string | "CN:600519" | SecurityId.canonical |
| `date` | string | "2026-07-15" | YYYY-MM-DD |
| `query_count` | int | 42 | 当日查询次数 |
| `avg_quality_score` | float | 0.93 | 当日平均质量评分 |
| `min_quality_score` | float | 0.72 | 当日最低质量评分 |
| `max_quality_score` | float | 1.0 | 当日最高质量评分 |
| `provider_distribution` | dict | {"ta_cn_internal": 30, "tushare": 10} | 各 provider 命中次数 |
| `last_updated` | datetime | ISODate | 最后更新时间 |

### 6.4 avg_quality_score 精确计算

**设计选择**：每次 update 时读当前 doc → 计算新 avg = (old_avg * old_count + new_score) / (old_count + 1) → $set avg_quality_score。

**理由**：
- Phase 2 不预设高频查询场景（单查询触发一次 upsert）。
- 精确计算避免浮点累积误差。
- 如果未来 query_count 增长过高，可切换为定期聚合（Phase 3+）。

### 6.5 索引

唯一索引由复合键 `_id` 天然保证。不需要额外唯一索引。

```javascript
// TTL 索引（按 date 过期，Pascal 已确认：365 天）
// Phase 1 不创建（QualitySummary 未启用），作为后续启用时的 DDL
// db.03_data_ud_quality_summary.createIndex(
//   {"date": 1},
//   {"expireAfterSeconds": 365 * 24 * 3600}
// )

// 按 domain + security_id 快速查询质量趋势（可选，Phase 2 默认不创建）
// DDL pending Pascal confirmation
// db.03_data_ud_quality_summary.createIndex(
//   {"domain": 1, "security_id": 1, "date": -1}
// )
```

### 6.6 行为矩阵

| 场景 | mongo_db | 预期行为 |
|------|----------|----------|
| QS-101 | None | noop，不写 MongoDB，不抛异常 |
| QS-102 | mongomock | 写入 mongomock |
| QS-103 | 写入异常 | catch-and-log，不阻断 |
| QS-104 | 批量重复查询 | upsert 幂等，query_count 累加 |
| QS-105 | get_summary 无数据 | 返回 [] |

---

## 7. DataRouter 质量填充集成

### 7.1 构造函数变更

```python
class DataRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        config: UnifiedDataConfig | None = None,
        *,
        ta_cn_adapter: Any = None,
        local_mongo_adapter: Any = None,
        cache_manager: Any = None,
        freshness: FreshnessPolicy | None = None,
        external_fallback_chains: dict[str, list[str]] | None = None,
        # Phase 2 additions:
        quality_scorer: "QualityScorer | None" = None,
        audit_logger: "AuditLogger | None" = None,
    ) -> None:
        # ... 现有初始化逻辑 ...
        self._quality_scorer = quality_scorer
        self._audit_logger = audit_logger
```

**None 默认值语义**：
- `quality_scorer=None` → DataResult.quality_score 保持 None（Phase 0/1A/1B 兼容行为）
- `audit_logger=None` → 不产生审计日志
- 两者均为 None 时，Router 行为完全等同于 Phase 0/1A/1B

### 7.2 query() 尾部增强

```python
def query(self, ...) -> DataResult:
    # ... 现有 Step 1-4 逻辑不变 ...
    result = self._internal_orchestrator(...)

    # Phase 2: QualityScorer 评分
    if self._quality_scorer is not None:
        try:
            scored = self._quality_scorer.score(result, domain=domain)
            result.quality_score = scored.quality_score
            result.warnings = list(result.warnings or []) + scored.warnings
            # 在 source_trace 尾部追加质量评分 trace
            result.source_trace.append(
                f"quality_scored: tier={scored.quality_tier}, score={scored.quality_score}"
            )
        except Exception as exc:
            # QualityScorer 内部异常不阻断查询返回
            logger.warning("QualityScorer.score failed: %s", exc)

    # Phase 2: AuditLogger（catch-and-log）
    if self._audit_logger is not None:
        # ``params`` 是调用方在 :meth:`query` 入口传入的 mapping 的
        # 防御性浅拷贝快照；后续对该 mapping 的变更不会回写到审计记录。
        # ``duration_ms`` 由 ``ts`` (请求起始时间戳) 推导的实耗毫秒，
        # 不再是硬编码 ``0``；详见 :meth:`DataRouter._compute_duration_ms`。
        try:
            self._audit_logger.log(
                result,
                consumer=self._config.consumer,
                duration_ms=self._compute_duration_ms(ts),
                params=dict(params_dict or {}),
            )
        except Exception as exc:
            logger.warning("AuditLogger.log failed: %s", exc)

    return result
```

**Audit 字段契约**（与 `AuditLogger._build_document` 对齐）：

- ``params`` — 来自 :meth:`query` 调用方的 `params` mapping 的浅拷贝快照；保留调用方传入的全部键。审计写入发生在 Step 1-4 完成后，因此 `params` 的取值冻结于查询入口，不受后续 orchestrator 内部变更影响。
- ``duration_ms`` — 非负整数毫秒数。``ts`` 缺失时退化为 ``0``；``ts`` 晚于 ``now``（单调时钟偏移）时同样退化为 ``0``；其余情况取 ``int((now - ts).total_seconds() * 1000)`` 并用 ``max(0, ...)`` 兜底。所有 ``query()`` 出口路径（`provider == "ta_cn_internal"`、显式 `provider=`、`internal-first` 全路径，以及 `error` + `empty_ta_cn` 兜底分支）均经过同一个 :meth:`_enrich_with_quality_and_audit` helper，审计上下文一致。
- ``quality_scorer`` / ``audit_logger`` 为 ``None`` 的 Phase 0/1B 路径保持完全不变；``scorer`` / ``audit`` / ``summary`` 异常继续走 catch-and-log，不影响主查询返回。

### 7.3 查询注入行为矩阵

| 场景 | quality_scorer | audit_logger | 预期行为 |
|------|---------------|--------------|----------|
| DR-301 | None | None | 同 Phase 0/1A/1B，quality_score=None，无审计 |
| DR-302 | QualityScorer | None | DataResult.quality_score 有值，无审计 |
| DR-303 | None | AuditLogger | quality_score=None，审计日志写入 |
| DR-304 | QualityScorer | AuditLogger(real) | 全量：评分 + 审计 + QualitySummary 汇总 |
| DR-305 | QualityScorer | AuditLogger(noop) | 评分 + noop 审计/汇总 |
| DR-306 | QualityScorer + force_refresh | AuditLogger | 跳过 Step 1-3，外部查询仍有评分和审计 |
| DR-307 | QualityScorer + error result | AuditLogger | 评分 0.0 + 审计 success=false |
| DR-308 | QualityScorer 异常 | AuditLogger | quality_score 保持 None，审计正常写入 |
| DR-309 | QualityScorer | AuditLogger 异常 | 评分正常，审计 catch-and-log |

### 7.4 兼容性影响

| 组件 | 影响 | 向后兼容 |
|------|------|----------|
| DataResult.quality_score | 原为 None，现可能为 float | 兼容（None 和 float 均可处理） |
| DataResult.warnings | 原可能为空，现可能包含质量告警 | 兼容（list 结构不变） |
| DataResult.source_trace | 尾部可能追加 "quality_scored: ..." | 兼容（现有消费者读 trace 不受影响） |
| DataRouter.query() 返回值 | 签名不变，返回值语义增强 | 兼容 |
| ProviderRegistry.get_providers() | 新参数 state_filter 有默认值 None | 兼容（不传 = 原有行为） |
| 已有 269 测试 | quality_scorer=None, audit_logger=None | 完全不影响 |

---

## 8. Production Gate 与副作用矩阵

### 8.1 新增集合

| 集合 | 操作 | DDL | DML | Pascal 确认前 |
|------|------|-----|-----|--------------|
| `03_data_ud_query_audit` | insert(append-only) | createIndex x3 | 每次 query 后 insert_one | noop / mongomock only |
| `03_data_ud_quality_summary` | upsert | ⛔ Phase 1 不创建（createIndex 仅在后续 Phase 启用） | 每次 audit 后 update_one（Phase 1 不执行） | noop / mongomock only |

### 8.2 副作用矩阵（Pascal 已确认架构决策）

| 副作用 | 组件 | 影响 | 是否可回滚 | Phase 1 执行状态 |
|--------|------|------|-----------|-----------------|
| MongoDB 集合创建 | AuditLogger | `tradingagents.03_data_ud_query_audit` 创建（TTL=365 天） | 可回滚（drop collection） | 🔲 NOT DEPLOYED（DDL 尚未实施：须经 Implement→Verify→Review→Pascal 逐项授权） |
| MongoDB 索引创建 | AuditLogger | 3 个索引（TTL expireAfterSeconds=31536000 + security_id + capability） | 可回滚（drop index） | 🔲 NOT DEPLOYED（索引创建尚未实施：须经 Implement→Verify→Review→Pascal 逐项授权） |
| 审计日志写入 | AuditLogger | 每次 query 后 insert_one | 不可回滚（已写入数据） | 🔲 NOT IMPLEMENTED（fail-open 策略已确认；写入代码尚未实施：须经 Implement→Verify→Review→Pascal 逐项授权） |
| quality tier 业务影响 | QualityScorer | 仅观测，不构成业务门禁 | 无副作用 | ✅ PLANNED（仅观测，不构成业务门禁） |
| 质量汇总集合创建 | QualitySummary | `tradingagents.03_data_ud_quality_summary` 创建（TTL=365 天） | 可回滚 | ⏳ NOT DEPLOYED（QualitySummary 未启用；回滚策略记录在案） |
| 质量汇总写入 | QualitySummary | 每次 audit 后 upsert（Phase 1 不执行） | 不可回滚 | ❌ NOT IMPLEMENTED（Phase 1 全程禁用） |
| Registry 内存状态变更 | ProviderRegistry | set_health / set_priority | 可回滚（重启恢复默认） | ✅ N/A（纯内存，无需部署） |
| QualityScorer 计算 | QualityScorer | 无持久化 | ✅ 无副作用 | ✅ N/A（纯计算，无需部署） |

### 8.3 Phase 1 默认行为与范围

**Audit-only Phase 1 声明**：

| 组件 | Phase 1 默认行为 | Pascal 确认后（未来 Phase） |
|------|-----------------|----------------------------|
| AuditLogger | `mongo_db=None`（noop），或注入 mongomock.Database。经 Pascal 确认 DDL+smoke 后启用真实写入 | `mongo_db` 指向生产库 |
| QualitySummary | **全程禁用**。`AuditLogger.__init__` 的 `quality_summary` 参数始终保持 `None`。不创建 noop 实例 | `mongo_db` 指向生产库 |
| 集合/索引创建 | **不执行任何 DDL**。代码/测试/脚本中不硬编码 createIndex | 通过独立 MigrationScript 或 rollback-safe 部署脚本创建 |
| 真实 provider smoke | 不执行 | Pascal 确认后可选 |
| quality tier 业务影响 | 仅观测，不构成业务门禁 | 待未来 Phase 决策 |

### 8.4 代码约束

1. `AuditLogger.__init__` / `QualitySummary.__init__` 中 `mongo_db=None` 时必须安全初始化为 noop，不创建任何连接。
2. `log()` / `update()` 在 noop 模式下：不抛异常、不写日志、不创建集合。
3. 全部测试使用 mongomock，不依赖真实 MongoDB。
4. 测试中不创建真实 MongoDB 集合或索引。
5. 所有 Phase 2 新增代码有显式守卫（`mongo_db is None`），确保无 MongoDB 时静默降级为 noop。

### 8.5 MongoDB 权限分层架构与正式命名（Pascal 已确认）

#### 8.5.1 正式命名空间

| 类型 | 正式名称 | 权限范围 |
|------|---------|----------|
| Writer Role | `yquant_ud_audit_writer_role` | `03_data_ud_query_audit` insert-only |
| Reader Role | `yquant_ud_audit_reader_role` | `03_data_ud_query_audit` find-only |
| Writer User | `yquant_ud_audit_writer_user` | 授予 writer role |
| Reader User | `yquant_ud_audit_reader_user` | 授予 reader role |
| DDL Bootstrap | 独立身份（非上述任一运行时账号） | createCollection + createIndex + createRole + createUser |

**命名规则**：所有角色和用户使用 `yquant_ud_audit_*` 前缀，不得使用其他前缀。DDL 脚本内部校验该前缀，不匹配时 fail-fast。

#### 8.5.2 环境变量契约

**DDL 身份**（`audit_rollout.py --apply` 使用，bootstrap 必须）：

| 环境变量 | 强制 | 默认值 | 说明 |
|----------|------|--------|------|
| `YQUANT_UD_AUDIT_DDL_MONGO_URI` | 是 | 无（fail-fast） | DDL 连接 URI |
| `YQUANT_UD_AUDIT_DDL_MONGO_USERNAME` | 是 | 无（fail-fast） | DDL 用户名 |
| `YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD` | 是 | 无（fail-fast） | DDL 密码 |
| `YQUANT_UD_AUDIT_DDL_MONGO_AUTH_DB` | 否 | `admin` | DDL 认证数据库 |

**Writer 身份**（AuditLogger 运行时使用）：

| 环境变量 | 强制 | 默认值 | 说明 |
|----------|------|--------|------|
| `YQUANT_UD_AUDIT_WRITER_MONGO_URI` | 否（noop 可用） | 无 | Writer 连接 URI |
| `YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME` | 否 | 无 | Writer 用户名 |
| `YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD` | 否 | 无 | Writer 密码 |
| `YQUANT_UD_AUDIT_WRITER_MONGO_AUTH_DB` | 否 | `admin` | Writer 认证数据库 |

**Reader 身份**（未来只读查询，Phase 1 不创建）：

| 环境变量 | 强制 | 默认值 | 说明 |
|----------|------|--------|------|
| `YQUANT_UD_AUDIT_READER_MONGO_URI` | 否 | 无 | Reader 连接 URI |
| `YQUANT_UD_AUDIT_READER_MONGO_USERNAME` | 否 | 无 | Reader 用户名 |
| `YQUANT_UD_AUDIT_READER_MONGO_PASSWORD` | 否 | 无 | Reader 密码 |
| `YQUANT_UD_AUDIT_READER_MONGO_AUTH_DB` | 否 | `admin` | Reader 认证数据库 |

**禁止复用规则**：绝对不得复用业务身份（如 `portfolio_*`、`smart_money_*` 使用的数据库用户）作为 audit DDL/writer/reader 身份。runtime writer 与 DDL bootstrap 必须严格分离。

### 8.6 params 字段白名单 — 模块级常量（Pascal 已确认）

- **白名单策略**：`AuditLogger._build_document` 对 `params` 字段采用白名单，仅记录允许的查询参数键。
- **敏感字段丢弃**：凭据（`token`、`api_key`、`secret`、`password`、`credential`）、密钥等默认丢弃，不进入审计文档。
- **实现方式**：白名单定义为 `scripts/unified_data/audit_rollout.py` 的**模块级常量** `ALLOWED_PARAMS: set[str]`，而非构造函数注入。常量在模块加载时固定，初始化后不可变。Implement 阶段固化具体键列表。
- `params` 在审计文档中始终存在（最少为空 JSON 对象 `{}`），不得省略。

### 8.7 写入失败与降级策略（Pascal 已确认）

- **fail-open**：AuditLogger / QualitySummary 写入失败不阻断主查询返回，不重试，不阻塞调用方。
- **本地结构化日志**：写入失败时通过 `logger.warning` 输出，包含失败原因和写入集合名。
- **不接外部告警**：Phase 1 写入失败不接外部告警系统（PagerDuty/短信/Telegram），仅本地日志 + 计数器。外部告警属于 Phase 3+。
- **已写入数据不自动删除**：回滚优先停用注入，已有审计数据保留。

### 8.8 Rollout 策略（Pascal 已确认）

```
第 1 步：DDL（通过 scripts/unified_data/audit_rollout.py --apply）
  - 创建 2 个 custom role：
    · yquant_ud_audit_writer_role（03_data_ud_query_audit insert-only）
    · yquant_ud_audit_reader_role（03_data_ud_query_audit find-only）
  - 创建 2 个 runtime user：
    · yquant_ud_audit_writer_user（授予 writer role）
    · yquant_ud_audit_reader_user（授予 reader role）
  - 创建 03_data_ud_query_audit 集合 + TTL 索引（expireAfterSeconds=31536000）+ 二级索引
  - 使用独立 DDL 身份（YQUANT_UD_AUDIT_DDL_MONGO_* 环境变量），建好即销毁连接
  - 不得创建 03_data_ud_quality_summary（Phase 1 不启用）

第 2 步：真实 smoke
  - 用 writer user（yquant_ud_audit_writer_user）在生产环境写入一条审计记录
  - 用 reader user（yquant_ud_audit_reader_user）立即读取验证 schema
  - 验证 TTL 索引存在且 expireAfterSeconds 正确
  - 验证写入失败不阻断主查询

第 3 步：小范围 Audit-only 金丝雀
  - 在 1–2 个低流量 capability（如 metadata.*）启用 AuditLogger 真实写入
  - 观察 24–48h：写入成功率、延迟、无副作用

第 4 步：观察
  - 金丝雀通过后逐步开放到全部 capability
  - 持续观察 1–2 周，每日检查 audit 数据量和写入延迟
  - 回滚预案：停用 AuditLogger 注入（mongo_db=None），已写入数据保留不删
```

### 8.9 DDL 工具代码契约（audit_rollout.py）

#### 8.9.1 现有实现状态

`scripts/unified_data/audit_rollout.py` 当前已完成 collection + 索引创建（`run_apply` 约 L292-L342），但存在下列已识别的实现缺口，需在 Implement Remediation 阶段修复：

| # | 缺口 | 现有实现 | 需修复方向 |
|---|------|---------|-----------|
| G1 | 无 role/user 创建 | `run_apply()` 无 createRole/createUser | 增加 role/user 创建逻辑（幂等） |
| G2 | role 前缀错误 | 当前硬编码前缀 `ud_audit_writer*` / `ud_audit_reader*` | 改为 `yquant_ud_audit_writer*` / `yquant_ud_audit_reader*` |
| G3 | role 仅校验前缀不创建 | `--writer-role/--reader-role` 仅校验命名前缀 | `--apply` 时须实际创建/校验 role + user |
| G4 | 白名单注入位置 | 无现有白名单实现 | 在模块级添加 `ALLOWED_PARAMS` 常量 |
| G5 | createUser 缺 pwd | `_ensure_user` 接收 `password_env_var` 却不读取；createUser 命令无 `pwd`（真实首次 --apply 对 SCRAM 用户失败）；docstring 声称 fail-fast 但代码未实现 | 仅须 createUser 时读取对应 runtime 密码环境变量作 `createUser.pwd`；缺失/空 fail-fast（退出码 3）；幂等校验路径不读密码；详见 §8.9.5 |

#### 8.9.2 需新增的 role/user 创建函数

```python
# 在 audit_rollout.py 中新增：

WRITER_ROLE_NAME = "yquant_ud_audit_writer_role"
READER_ROLE_NAME = "yquant_ud_audit_reader_role"
WRITER_USER_NAME = "yquant_ud_audit_writer_user"
READER_USER_NAME = "yquant_ud_audit_reader_user"

# 模块级白名单常量（替代构造函数注入）
ALLOWED_PARAMS: set[str] = {
    # Implement 阶段固化具体键
}


def _ensure_write_role(db: Any) -> bool:
    """创建或校验 writer role：对 03_data_ud_query_audit 的 insert-only 权限。

    幂等：role 已存在且权限精确匹配时不重复创建。
    失败：角色已存在但 db / collection / actions / inherited roles / role binding 任一项不匹配 → fail-closed（退出码 4），不 warning-then-continue，不自动 drop/recreate。
    """
    ...


def _ensure_read_role(db: Any) -> bool:
    """创建或校验 reader role：对 03_data_ud_query_audit 的 find-only 权限。"""
    ...


def _ensure_write_user(db: Any) -> bool:
    """创建或校验 writer user：授予 yquant_ud_audit_writer_role。

    createUser 初始密码来源：YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD（§8.9.5）。
    仅当用户不存在须 createUser 时读取该密码；用户已存在仅校验 role binding，不读密码。
    """
    ...


def _ensure_read_user(db: Any) -> bool:
    """创建或校验 reader user：授予 yquant_ud_audit_reader_role。

    createUser 初始密码来源：YQUANT_UD_AUDIT_READER_MONGO_PASSWORD（§8.9.5）。
    仅当用户不存在须 createUser 时读取该密码；用户已存在仅校验 role binding，不读密码。
    """
    ...
```

#### 8.9.3 错误处理

| 场景 | 行为 | 退出码 |
|------|------|--------|
| DDL 凭证缺失（URI/USERNAME/PASSWORD） | fail-fast | 3 |
| 现有 role/user/index 已存在但 db / collection / actions / inherited roles / role binding / TTL / key / order 任一项不精确匹配 | fail-closed：不自动 drop/recreate，不 warning-then-continue；直接 fail-fast | 4 |
| role/user 名称不在 `yquant_ud_audit_*` 命名空间内 | fail-fast | 2 |
| createRole/createUser 抛出权限异常 | fail-fast | 4 |
| 须 createUser（用户不存在）但 runtime 密码环境变量缺失/空 | fail-fast：在 createUser DDL 命令发出前退出 | 3 |
| createUser 命令本身成功，但 user 已存在且 role binding 不匹配 | fail-closed：不得修改/重建用户 | 4 |
| collection/index 操作成功但 role/user 失败 | fail-closed：不声明成功 | 4 |
| dry-run 模式 | 打印预期 role/user/index 操作，零副作用 | 0 |

#### 8.9.4 `--verify` 只读验证范围与退出码

`python scripts/unified_data/audit_rollout.py --verify` 的执行范围：

| 验证项 | 检查内容 | 可选依赖 |
|--------|----------|----------|
| collection | `tradingagents.03_data_ud_query_audit` 是否存在 | 无 |
| 3 个索引 | TTL `fetched_at`（expireAfterSeconds=31536000）、`(security_id, fetched_at)`、`(capability, fetched_at)` — 索引名、键顺序、expireAfterSeconds 精确匹配 | collection 存在 |
| writer role | `yquant_ud_audit_writer_role` 是否存在，privileges 精确匹配（db=tradingagents, collection=03_data_ud_query_audit, actions=[insert]） | 无 |
| reader role | `yquant_ud_audit_reader_role` 是否存在，privileges 精确匹配（db=tradingagents, collection=03_data_ud_query_audit, actions=[find]） | 无 |
| writer user | `yquant_ud_audit_writer_user` 是否存在，授予 writer role | writer role 存在 |
| reader user | `yquant_ud_audit_reader_user` 是否存在，授予 reader role | reader role 存在 |
| QualitySummary | **不得存在** `03_data_ud_quality_summary` 集合（Phase 1 不启用） | 无 |

**退出码**：0=全部通过（含预期不存在项）；1=任一项验证失败；2=argparse 拒绝（`--apply`/`--verify` 互斥冲突或未知参数）；3=凭证缺失；4=运行时错误。

#### 8.9.5 createUser 初始密码传递契约（HIGH-1 修复基线）

本节是 `_ensure_user` createUser pwd 缺口的唯一修复基线，与 RFC §8.4.7、SPEC §8.7 三层一致。Implement 阶段须严格按此实现。

**密码来源映射**：

| 目标 user | `_ensure_user` 的 `password_env_var` 参数值 | createUser.pwd 读取来源 |
|-----------|---------------------------------------------|------------------------|
| `yquant_ud_audit_writer_user` | `YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD` | `os.environ["YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD"]` |
| `yquant_ud_audit_reader_user` | `YQUANT_UD_AUDIT_READER_MONGO_PASSWORD` | `os.environ["YQUANT_UD_AUDIT_READER_MONGO_PASSWORD"]` |

语义：runtime 登录密码 = createUser 初始密码。复用既有 runtime 密码环境变量，不新增 env、不新增 alias/fallback。

**`_ensure_user` 实现契约**（修复后须满足）：

```python
def _ensure_user(
    db: Any,
    *,
    user_name: str,
    roles: list[dict[str, Any]],
    password_env_var: str,
) -> str:
    """幂等创建/校验 custom user；createUser 初始密码按需读取。

    1. 经 DDL bootstrap identity 执行只读 usersInfo 判定用户是否存在（仅读不写，
       不在预检阶段创建/更新 role/user/index/collection）。
    2. 用户不存在 → 读 password_env_var；缺失/空 → raise MissingCredentialError（exit 3）。
       → db.command({"createUser": user_name, "pwd": password, "roles": roles})。
       password 仅在此单条 DDL 命令作用域内存活，执行后丢弃。
    3. 用户已存在 → 不读密码、不轮换、不重设；仅校验 role binding 精确匹配，
       不匹配 raise IdentityPrivilegeMismatch（exit 4），不修改/重建用户。
    """
```

**关键行为断言**（Implement 须实现，Tester 须验证）：

| # | 断言 | 触发条件 | 期望结果 |
|---|------|----------|----------|
| PWD-1 | createUser 命令含 pwd | 用户不存在 + 密码环境变量已设置 | `db.command` 收到的 dict 含 `"pwd"` 键且值非空 |
| PWD-2 | createUser 前读密码 | 用户不存在 | `os.environ.get(password_env_var)` 在 createUser 之前被调用 |
| PWD-3 | 密码缺失不发 createUser | 用户不存在 + 密码环境变量缺失/空 | raise MissingCredentialError，退出码 3；**不发 createUser 写 DDL**。注意：DDL identity 只读 `usersInfo` 存在性预检连接属于合法操作（已在 PWD-1/PWD-2 之前执行），此处禁止的是 createUser 写副作用，而非禁止预检只读连接 |
| PWD-4 | 幂等不读密码 | 用户已存在 | 不读取密码环境变量；仅校验 role binding |
| PWD-5 | role binding 不匹配不重建 | 用户已存在 + role binding 与契约不一致 | raise IdentityPrivilegeMismatch，退出码 4；不 updateUser/dropUser/createUser |
| PWD-6 | 异常无 secret 泄露 | 上述任何异常路径 | 异常消息 / repr 不含 password 值 |

**安全防护**（硬性，DSA 约束）：

- 不得 print / log / return / 持久化 password 值。
- password 变量生命周期限定在 createUser 命令构建与执行的单一作用域。
- 不得出现在 traceback / 异常消息 / 诊断输出。
- DDL bootstrap 密码（`YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD`）与 runtime 密码严格隔离，不交叉引用。

**测试契约**（Tester 须覆盖，fake admin / mongomock）：

| # | 测试场景 | 验证点 |
|---|----------|--------|
| T-PWD-1 | fake admin 须 createUser | 断言 `createUser` 命令含 `pwd` 键且值非空 |
| T-PWD-2 | 密码缺失 + 用户不存在 | 经 DDL identity（或 fake admin）只读 `usersInfo` 确认用户不存在后，runtime pwd 缺失/空 → 退出码 3；不发 `createUser`、不执行任何写 DDL、不创建/不使用 writer/reader runtime identity；无 secret 泄露。允许一次 DDL identity 只读连接用于存在性检查，不属于 runtime 登录或 createUser 写副作用 |
| T-PWD-3 | 用户已存在（幂等） | 不读取密码环境变量；role binding 精确匹配 → "unchanged" |
| T-PWD-4 | 用户已存在 + role binding 不匹配 | 退出码 4；不修改/重建用户 |
| T-PWD-5 | 所有异常路径 | 异常消息 / 日志 / repr 不含 password 值 |

**docs 一致性验证**：RFC §8.4.7、SPEC §8.7、本节三层契约必须一致；docs diff check 仅触及这三份文档。

---

## 9. 测试策略

### 9.1 测试矩阵

| 测试文件 | 测试范围 | fixture | 验证重点 |
|----------|----------|---------|----------|
| `test_quality_scorer.py` | QualityScorer 单元测试 | `quality_config_default`, `quality_config_market_data`, `result_normal`, `result_empty`, `result_stale`, `result_error`, `result_conflict`, `result_anomaly` | N1~N12 全部场景 + hard fail + tier 判定 + 边界 age TTL |
| `test_quality_config.py` | QualityScorerConfig 测试 | 无（直接构造） | 默认值、域覆盖、权重总和 != 1 抛 ValueError、tier_thresholds 缺失键抛 ValueError |
| `test_audit_logger.py` | AuditLogger 测试 | `mongomock_db`, `mock_data_result` | AL-101~105 + schema 字段完整性 + audit_id UUID 唯一性 |
| `test_quality_summary.py` | QualitySummary 测试 | `mongomock_db`, `mock_data_result` | QS-101~105 + upsert 幂等 + get_summary 范围查询 + avg/min/max 正确性 |
| `test_registry_governance.py` | Registry 治理测试 | `cn_maotai`, `fake_providers` | R1~R9 全部场景 + set_priority ValueError + set_health ValueError |
| `test_router_quality.py` | Router 质量填充端到端测试 | `router_quality_scorer`, `router_audit_logger`, `fake_ta_cn_adapter` | DR-301~309 + quality_score 填充 + audit 触发 + Phase 0 兼容 |

### 9.2 Fixture 设计

`tests/data/unified_data/fixtures/quality_fixtures.py` 是 Quality fixture 的唯一权威实现源；顶层 `tests/data/unified_data/conftest.py` 仅通过 `pytest_plugins` 注册该模块，不得重复定义 `fixed_now`、`quality_fixed_now` 或 N1-N12 `result_*` fixture。

```python
# fixtures/quality_fixtures.py

@pytest.fixture
def quality_config_default() -> QualityScorerConfig:
    return QualityScorerConfig()

@pytest.fixture
def quality_config_market_data() -> QualityScorerConfig:
    return QualityScorerConfig(
        dimension_weights={"completeness": 0.25, "freshness": 0.40, "consistency": 0.15, "plausibility": 0.20},
        domain_ttl={"market_data": 14400},
    )

@pytest.fixture
def result_normal(cn_maotai) -> DataResult:
    return DataResult(
        data=[{"close": 150.0, "volume": 1000000}],
        security_id=cn_maotai,
        domain="market_data", operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=datetime.now(timezone.utc),
        freshness="delayed",
    )

@pytest.fixture
def result_empty(cn_maotai) -> DataResult:
    return DataResult(
        data=None,
        security_id=cn_maotai,
        domain="market_data", operation="kline_daily",
        provider="empty",
        fetched_at=datetime.now(timezone.utc),
        freshness="empty",
    )

@pytest.fixture
def result_stale(cn_maotai) -> DataResult:
    return DataResult(
        data=[{"close": 150.0}],
        security_id=cn_maotai,
        domain="market_data", operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=datetime(2020, 1, 1),
        freshness="stale",
    )

@pytest.fixture
def result_error(cn_maotai) -> DataResult:
    return DataResult.error(cn_maotai, "market_data", "kline_daily",
                            "tushare", Exception("API timeout"))

@pytest.fixture
def result_conflict(cn_maotai) -> DataResult:
    return DataResult(
        data=[{"close": 150.0}],
        security_id=cn_maotai,
        domain="market_data", operation="kline_daily",
        provider="tushare",
        fetched_at=datetime.now(timezone.utc),
        freshness="delayed",
        source_trace=["tushare(ok)", "tushare(vs_akshare:price_diverges)"],
    )

@pytest.fixture
def result_anomaly(cn_maotai) -> DataResult:
    return DataResult(
        data=[{"close": 0.0, "volume": 0}],
        security_id=cn_maotai,
        domain="market_data", operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=datetime.now(timezone.utc),
        freshness="delayed",
    )

# N11 专用 fixture：data=list[dict] 格式，1 条记录仅含 close（volume 缺失）
# 触发 completeness=0.5（1/2 核心字段存在），see §3.5 N11
@pytest.fixture
def result_missing_volume(cn_maotai) -> DataResult:
    return DataResult(
        data=[{"close": 150.0}],
        security_id=cn_maotai,
        domain="market_data", operation="kline_daily",
        provider="ta_cn_internal",
        fetched_at=datetime.now(timezone.utc),
        freshness="delayed",
    )

# conftest.py 增强

@pytest.fixture
def mongomock_db():
    """创建一个 mongomock 数据库用于测试 AuditLogger/QualitySummary。"""
    import mongomock
    return mongomock.MongoClient().db

@pytest.fixture
def fake_audit_logger(mongomock_db) -> AuditLogger:
    return AuditLogger(mongo_db=mongomock_db)

@pytest.fixture
def fake_quality_summary(mongomock_db) -> QualitySummary:
    return QualitySummary(mongo_db=mongomock_db)
```

### 9.3 验证命令

```bash
# 快速验证（无质量/审计 — Phase 0/1A/1B 兼容）
PYTHONPATH=. pytest tests/data/unified_data/ -m "not production_gate" -q --tb=short

# 质量相关全量
PYTHONPATH=. pytest tests/data/unified_data/test_quality_scorer.py tests/data/unified_data/test_quality_config.py tests/data/unified_data/test_registry_governance.py tests/data/unified_data/test_router_quality.py -q --tb=short

# 审计相关全量
PYTHONPATH=. pytest tests/data/unified_data/test_audit_logger.py tests/data/unified_data/test_quality_summary.py -q --tb=short

# 全部 Phase 2 测试
PYTHONPATH=. pytest tests/data/unified_data/test_quality_scorer.py tests/data/unified_data/test_quality_config.py tests/data/unified_data/test_audit_logger.py tests/data/unified_data/test_quality_summary.py tests/data/unified_data/test_registry_governance.py tests/data/unified_data/test_router_quality.py -q --tb=short

# 生产 smoke（仅 Pascal 确认后可运行）
# PYTHONPATH=. pytest tests/data/unified_data/test_audit_logger.py tests/data/unified_data/test_quality_summary.py -m "production_gate" -v
```

---

## 10. Pascal 决策项汇总

下列事项在 Design 中声明为候选值，Implement 阶段使用默认值，但必须在生产写入确认前由 Pascal 拍板：

| # | 事项 | 候选值 | 影响组件 | 需要确认的内容 |
|---|------|--------|---------|--------------|
| D1 | 域 TTL 默认值 | market_data=14400, financial=86400, news=3600, metadata=86400, index=14400（秒） | QualityScorer freshness 评分 | 每个域的 TTL 时长是否合理？是否需要额外域？ |
| D2 | 分域配置覆盖 | §3.6 的 4 个域覆盖示例 | QualityScorer 配置 | 权重分配是否合理？是否需要添加/移除域的覆盖？ |
| D3 | 审计集合索引 | §5.3 的 3 个索引（TTL + security_id + capability） | AuditLogger DDL | Pascal 已确认 TTL=365 天。索引策略是否合理？ |
| D4 | 质量汇总集合索引 | §6.4 的 domain+security_id+date 索引 | QualitySummary DDL | 是否需要该索引？查询模式是否满足？ |
| D5 | 生产集合写入确认 | 两个集合（audit + quality_summary）何时启用真实写入 | all | 确认后 Implement 启用 MongoDB 后端；确认前仅 noop/mongomock |

---

## 11. 风险与回滚

### 11.1 风险

| 风险 | 概率 | 影响 | 应对 | 降级策略 |
|------|------|------|------|----------|
| QualityScorer 维度评分主观性强 | 中 | 中 | 所有权重/阈值默认值可配置，Design 明确默认值 | 使用保守无偏权重，Pascal 随时可调整 |
| AuditLogger 写入成为性能瓶颈 | 低 | 高 | catch-and-log 确保不阻断查询；Design 阶段确认写入频率 | 增加采样率（Phase 3+）或降级为 noop |
| TTL 索引频率不匹配 | 中 | 低 | Design 阶段给出候选索引；Pascal 确认后按预期 workload 调整 | 调整 expireAfterSeconds |
| QualitySummary 写入频率过高 | 中 | 低 | 每次 audit trigger 一次 upsert（catch-and-log 保护） | 降低到每 N 次更新一次（Phase 3+） |
| Registry 运行时变更导致不一致 | 低 | 中 | priority/health_state 是瞬态状态，不持久化，重启恢复默认 | 无持久化意味着重启即恢复，无需回滚 |

### 11.2 回滚

1. **AuditLogger**：将 mongo_db 设置为 None → 恢复 noop 模式（丢失前端窗口内的审计记录，不影响查询）
2. **QualitySummary**：将 mongo_db 设置为 None → 恢复 noop 模式（丢失前端窗口内的汇总数据，get_summary 返回 []）
3. **QualityScorer**：从 DataRouter 移除 quality_scorer 参数 → quality_score 恢复为 None（不影响 DataRouter 核心路径）
4. **Registry 治理**：`set_health`/`set_priority` 可独立回滚到默认状态；无持久化，重启即恢复
5. **集合/索引**：drop 集合或索引可回滚 DDL 副作用
6. **整体回滚**：Phase 2 新增文件全在 `quality/` 和 `audit/` 子包内，不与 Phase 0/1A/1B 耦合；删除这两个目录即可回滚全部 Phase 2 代码

### 11.3 容量估算

| 指标 | 估算 | 说明 |
|------|------|------|
| 日查询次数 | ~10,000（初期） | 基于当前交易品种 × 域 × 刷新频率 |
| 每日审计文档大小 | ~10KB/文档 | 含 params 字段的平均大小 |
| 日审计数据量 | ~100MB | 10,000 × 10KB |
| 365 天审计数据量 | ~36GB | 初始阶段，随使用增长可扩展，按 TTL=365 天估算 |
| QualitySummary 文档数 | ~100/天 | 按 (domain, security_id, date) 聚合，非每个 query |
| QualitySummary 总大小 | < 4MB | 100 文档/天 × 365 天 = 36,500 文档 |

---

## 12. 实施顺序（Implement 阶段建议）

| 顺序 | 组件 | 依赖 | 验证 |
|------|------|------|------|
| 0 | DDL 脚本修复（audit_rollout.py） | 无 | test_audit_rollout.py（新增：A1~A10 验收点） |
| 1 | QualityScorerConfig | 无（纯 dataclass） | test_quality_config.py |
| 2 | QualityScorer | QualityScorerConfig | test_quality_scorer.py |
| 3 | ProviderRegistry 治理 | 现有 registry 代码 | test_registry_governance.py |
| 4 | AuditLogger（noop 版） | 无（mongo_db=None 可独立工作） | test_audit_logger.py |
| 5 | QualitySummary（noop 版） | 无（mongo_db=None 可独立工作） | test_quality_summary.py |
| 6 | DataRouter 集成 | 1-5 全部完成 | test_router_quality.py |
| 7 | 生产 MongoDB 后端（Pascal 确认后） | AuditLogger + QualitySummary | production_gate smoke test |

---

## 13. 验收标准

1. **文件存在**：
   - `docs/rfc/03_data/RFC-03-011-unified-data-phase-2-quality-audit-governance.md` ✅
   - `docs/spec/03_data/SPEC-03-011-unified-data-phase-2-quality-audit-governance.md` ✅
   - `docs/design/03_data/DESIGN-03-011-unified-data-phase-2-quality-audit-governance.md` ✅（本文件）

2. **QualityScorer 设计可执行**：
   - score() 返回 ScoredResult ✓
   - 4 维度评分规则已精确给出 ✓（§3.2）
   - 分域 TTL 默认值已给出（Pascal 决策项 D1）✓
   - 分域配置覆盖示例已给出（Pascal 决策项 D2）✓
   - hard fail 条件已精确列出 ✓
   - N1-N12 全部场景行为矩阵 ✓

3. **Registry 治理设计可执行**：
   - priority 排序规则已给出 ✓
   - health_state 状态转换与 skip 规则已给出 ✓
   - R1-R9 行为矩阵 ✓
   - Router 集成方式已给出（§4.2）✓

4. **AuditLogger 设计可执行**：
   - schema 已确认（§5.2）✓
   - 索引候选已给出（Pascal 决策项 D3）✓
   - AL-101~105 行为矩阵 ✓
   - catch-and-log 模式 ✓
   - noop 后端模式 ✓

5. **QualitySummary 设计可执行**：
   - schema 已确认（§6.2）✓
   - upsert 聚合逻辑 ✓
   - avg 计算方式 ✓
   - QS-101~105 行为矩阵 ✓

6. **Router 集成设计可执行**：
   - 构造函数变更 ✓
   - quality_scorer=None 兼容 ✓
   - audit_logger=None 兼容 ✓
   - DR-301~309 行为矩阵 ✓

7. **Production Gate**：
   - 副作用矩阵 ✓（§8.2）
   - Pascal 决策项汇总 ✓（§10）
   - 确认前 noop/mongomock 约束 ✓
   - 索引/DDL 不在代码中硬编码 ✓

8. **测试策略可执行**：
   - 测试文件清单 ✓
   - fixture 设计 ✓
   - 验证命令 ✓

9. **边界声明**：
   - Phase 2 不含 DSA adapter ✓
   - Phase 2 不含 Task Center/Stock Framework/Sector Router ✓
   - 不改动已有公开 API 签名 ✓

---

## 14. 后置验收边界：Developer Acceptance & Production Smoke

### 14.1 Developer Acceptance 验收点

Implement 阶段需要验证以下验收点（Kanban 任务完成条件）：

| # | 验收点 | 验证方式 | 通过条件 |
|---|--------|---------|----------|
| A1 | `audit_rollout.py` role/user 创建 | 单元测试 mock `db.command()` 调用 | `_ensure_write_role` / `_ensure_read_role` / `_ensure_write_user` / `_ensure_read_user` 四函数存在，且 `run_apply` 调用链覆盖 |
| A2 | 命名前缀为 `yquant_ud_audit_*` | grep 检验硬编码字符串 | `WRITER_ROLE_NAME.startswith("yquant_ud_audit")`, `READER_ROLE_NAME.startswith("yquant_ud_audit")` |
| A3 | 权限范围正确 | `createRole` privileges 检查 | writer role 仅含 `{ resource: { db: "tradingagents", collection: "03_data_ud_query_audit" }, actions: ["insert"] }`；reader role 仅含 `["find"]` |
| A4 | 白名单为模块级常量 | grep 检验 | `ALLOWED_PARAMS` 位于模块作用域（无缩进），非 `__init__` 参数 |
| A5 | 拒绝 broad identity | 单元测试 mock | `run_apply` 不调用涉及 `portfolio_*` / `smart_money_*` / `signal_*` / `trade_*` / 缓存集合的 grant 操作 |
| A6a | DDL bootstrap 凭证缺失 fail-fast | `YQUANT_UD_AUDIT_DDL_MONGO_URI`/`USERNAME`/`PASSWORD` 未设置 | 退出码 3，不发起任何 MongoDB 连接（连 DDL bootstrap 连接也不建立） |
| A6b | runtime 密码缺失 + 用户不存在 fail-fast | 经 DDL identity 只读 `usersInfo` 确认用户不存在后，对应 runtime 密码环境变量缺失/空 | 退出码 3；允许一次 DDL identity 只读连接用于 `usersInfo` 存在性预检，但**不发 `createUser`、不执行任何写 DDL、不创建/不使用 writer/reader runtime identity**（与 T-PWD-2 一致） |
| A7 | 未知参数拒绝 fail-fast | `--unknown-flag` | 退出码 2，argparse 报 `unrecognized arguments` |
| A8 | dry-run 零副作用 | `python audit_rollout.py`（无 `--apply`） | 打印计划、退出码 0、不调用任何 MongoDB 连接 |
| A9 | `--apply` 幂等 | 两次连续 `--apply` | 第二次不报错，输出包含 `skipped=[...]` |
| A10 | 全部已有测试（269）不因 DDL 修改而失败 | `pytest tests/data/unified_data/ -m "not production_gate" -q --tb=short` | 0 failed |

### 14.2 Production Smoke 边界

仅在 Pascal 显式授权 DDL+smoke 后方可执行。以下是 smoke 的最小步骤和回滚边界：

#### Smoke 步骤

```bash
# 1. DDL（role/user/index）——执行一次
YQUANT_UD_AUDIT_DDL_MONGO_URI="..." YQUANT_UD_AUDIT_DDL_MONGO_USERNAME="..." YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD="..." \
  python scripts/unified_data/audit_rollout.py \
  --apply

# 2. 验证 DDL 结果
YQUANT_UD_AUDIT_DDL_MONGO_URI="..." YQUANT_UD_AUDIT_DDL_MONGO_USERNAME="..." YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD="..." \
  python scripts/unified_data/audit_rollout.py \
  --verify

# 3. 用 writer user 写入一条审计记录
# （通过 production_gate smoke test）
PYTHONPATH=. MONGODB_URI="..." MONGODB_USERNAME="..." MONGODB_PASSWORD="..." \
  pytest tests/data/unified_data/ -m "production_gate" -v -k "test_audit_logger_prod"

# 4. 用 reader user 读取验证
# （通过 production_gate smoke test）
PYTHONPATH=. MONGODB_URI="..." MONGODB_USERNAME="..." MONGODB_PASSWORD="..." \
  pytest tests/data/unified_data/ -m "production_gate" -v -k "test_audit_logger_read_prod"
```

#### 回滚边界

| 操作 | 回滚命令 | 风险 |
|------|---------|------|
| 已创建 role | `db.dropRole("yquant_ud_audit_writer_role")` / `db.dropRole("yquant_ud_audit_reader_role")` | 无丢失（纯权限） |
| 已创建 user | `db.dropUser("yquant_ud_audit_writer_user")` / `db.dropUser("yquant_ud_audit_reader_user")` | 无丢失（纯权限） |
| 已创建集合 | `db.dropCollection("03_data_ud_query_audit")` | 损失已写入的审计数据 |
| 已创建索引 | `db.03_data_ud_query_audit.dropIndex("name")` | 无丢失（数据完整） |
| 已写入审计数据 | 不可回滚（保留），停用 AuditLogger 注入 | 前端窗口审计数据丢失 |
| 全部回滚 | 删除 `quality/` 和 `audit/` 子包 | 零代码残留 |

---

## 15. router.py 一次性行数豁免记录（Governance Track G2 — 已于 G3 取代）

### 15.1 背景

G1（`t_888eabbe`）已将项目 Python 文件硬上限从 300 行调整为 800 行，并同步了 CLAUDE.md、RFC-03-010、DESIGN-03-010。
Pascal 明确授权本 Phase 2 的 `skills/data/unified_data/router.py`（当前 1115 行）获得一次性、受控豁免，
以继续独立 Verify（T24 replacement）；这不是普遍 >800 行豁免。

> **G3 更新（2026-07-16）**：G3 将项目文件行数硬上限从 800 升级为 1200/2400/3600 四级分级（详见 CLAUDE.md:182 与 §15.6）。router.py 当前约 1195 行处于 ≤1200 常规范围，原 G2 的「下次扩展必须拆分 ≤800」不再是当前强制规则——下一次实质性功能扩展前仅需按 G3「1201–2400 受控扩张」规则操作（在 Design/PR 中说明职责边界、增长原因和拆分触发条件，需独立 Review）。
|
### 15.2 适用对象与范围

| 项目 | 值 |
|------|-----|
| 豁免对象 | `skills/data/unified_data/router.py`（本次 `+151/-17`，变更后 ~1115 行） |
| 豁免范围 | 仅 DataRouter Health + Quality/Audit 集成及 T24 replacement 独立验证所需 diff |
| 本 Design 内引用 | §4.2 Router 集成（health_state 过滤）、§7 DataRouter 质量填充集成 |
| 风险等级 | 低（reader 影响，不暴露外部调用方，不修改已有公共契约） |

### 15.3 边界与约束

1. **不改业务语义**：本次 diff（+151/-17）不改变 DataRouter.query()、_resolve_external_chain、_query_external_single 的输入输出契约。
2. **不借机扩展**：不允许将其他文件（registry.py、quality 子包、audit 子包、config.py 等）也拉入豁免范围。不允许借本次豁免引入超出当前 Phase 2 质量/审计集成范围的功能。
3. **后续治理（G2 原始约束，G3 已生效）**：对 router.py 的下一次实质性功能扩展，须按 G3「1201–2400 受控扩张」规则操作——在 Design/PR 中说明职责边界、增长原因和拆分触发条件，需独立 Review。G3 允许在不超过 2400 行的前提下继续叠加，且不强制拆分。
4. **文档约束**：本豁免记录不影响 Phase 2 的设计契约、行为矩阵（DR-301~309）、兼容性声明、测试策略和验收标准。
5. **测试约束**：不得为凑行数或跳过豁免边界捏造测试结果。所有测试按 §9 现有策略执行。

### 15.4 原始状态核实

豁免判定时 `router.py` 的确认状态：

- 总行数：~1115 行（含 43 行 __init__ + 2 个主 query 方法 + _resolve_external_chain + _query_external_single + 39 行 class + import + docstring + 末尾 footer）
- 本次 diff：+151 / -17（Phase 2：quality_scorer/audit_logger 参数 + 尾部评分/审计调用 + health_state 过滤 + 辅助 _filter_healthy）
- 超限比例（G2 时期计算）：1115 / 800 ≈ 139%（超出 315 行）—— G3 生效后 router.py 当前约 1195 行已进入 ≤1200 常规范围，不再超限
- 超限原因：router.py 本身是 Phase 0 时期按"单文件路由"模式编写的，含 4 个外部查询路径+fallback 链+缓存策略+错误处理，现阶段拆分成本大于收益

> ⚠️ **演化承诺**：当 router.py 的下一次实质性功能变更到来时（Phase 3 或 Sector Router 或新数据通路），建议评估按职责拆分的维护性收益。G3 不强制拆分，但若文件超过 1200 行进入「受控扩张」级别，须遵守对应规则。

### 15.5 治理历史

| 事件 | 时间 | 决策 | 产出 |
|------|------|------|------|
| G1 调整上限 | 2026-07-16 | Python 硬上限 300→800 | CLAUDE.md + RFC-03-010 + DESIGN-03-010 同步 |
| G2 豁免记录 | 2026-07-16 | router.py 一次性豁免 1115 行 | 本 §15 |
| G3 四级分级上线 | 2026-07-16 | 将 800 单阈值升级为 1200/2400/3600 四级分级 | CLAUDE.md:182、本 §15.6 |
| 下次功能扩展前 | TBD | G2 原始约束已由 G3 取代；按 G3 1201–2400 受控扩张规则执行 | 独立 Review |

### 15.6 G3 四级分级规则（当前生效，2026-07-16）

CLAUDE.md:182 同步的四级行数治理政策：

| 范围 | 规则 |
|------|------|
| ≤1200 行：常规范围 | 新建/修改文件可正常演进，仍以职责内聚为目标 |
| 1201–2400 行：受控扩张 | 下一次实质性功能扩展前须在 Design/PR 中说明职责边界、增长原因和拆分触发条件；需要独立 Review |
| 2401–3599 行：架构例外 | 下一次实质性功能扩展前必须有 Principal Design，定义拆分模块/迁移顺序/验证；不得在无设计情况下继续叠加 |
| ≥3600 行：禁止继续扩张 | 必须先完成拆分或取得 Pascal 针对具体文件的明确豁免 |

## 16. 参考资料

- `docs/rfc/03_data/RFC-03-011-unified-data-phase-2-quality-audit-governance.md` — 来源 RFC
- `docs/spec/03_data/SPEC-03-011-unified-data-phase-2-quality-audit-governance.md` — 来源 SPEC
- `docs/design/03_data/DESIGN-03-007-unified-data-layer.md` — Unified Data Layer 详细设计（§Phase 2）
- `docs/spec/03_data/SPEC-03-007-unified-data-layer.md` — 基础契约
- `docs/spec/03_data/SPEC-03-009-unified-data-phase-1b-persistence-plane.md` — Phase 1B-B 契约
- `skills/data/unified_data/registry.py` — 现有 ProviderRegistry
- `skills/data/unified_data/router.py` — 现有 DataRouter
- `skills/data/unified_data/models/__init__.py` — DataResult、SecurityId
- `skills/data/unified_data/quality/` — Phase 2 quality 子包（Implement 后创建）
- `skills/data/unified_data/audit/` — Phase 2 audit 子包（Implement 后创建）
- `tests/data/unified_data/conftest.py` — 现有测试 fixture 基座
