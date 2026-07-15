# SPEC-03-011：Unified Data Phase 2 — 数据质量评估、审计与运行治理

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-15 |
| 最后更新 | 2026-07-15 |
| 来源 RFC | RFC-03-011 |
| 关联 RFC | RFC-03-007（Unified Data Layer）、RFC-03-009（Phase 1B-B 持久化缓存平面） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-009（Phase 1B-B 持久化缓存平面） |
| 关联 Design | DESIGN-03-007（Unified Data Layer 详细设计） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |
| 版本号 | V0.1 |

---

## 0. 基线锚定

本 SPEC 继承 SPEC-03-007 / SPEC-03-009 的全部基线条款，仅新增或修正 Phase 2 范围内的契约。以下基线条款对本 SPEC 具有同等约束力：

- **共享物理数据库**：Unified Data 与 TA-CN 共用 `tradingagents`。不依赖物理库隔离，通过集合前缀逻辑隔离。
- **Internal-First 读取路径**：TA-CN 既有 → UD 物化 → Query Cache → 外部 Provider。外部刷新失败不阻断内部已有数据读取。
- **DSA 边界**：DSA 仅在分析/参考中出现；不实现任何 DSA adapter。
- **Collection Ownership 不可回写**：Unified Data 绝不回写、覆盖或加字段污染 TA-CN 既有无前缀集合。
- **Task Center 先行**：Phase 2 不依赖 Task Center 调度。

### 0.1 本 SPEC 独立契约

以下条款为本 SPEC 独有，不依赖上游 SPEC 的 Phase 0/1A/1B 清单：

| # | 条款 | 本 SPEC 落点 |
|---|------|-------------|
| P2-1 | QualityScorer 只评数据质量，不评投资质量 | §1.2、§4 |
| P2-2 | 评分 `[0, 1]`，至少 4 维度，权重/阈值可配置 | §3、§4 |
| P2-3 | 等级语义 direct use / warning / degrade / reject | §3.3 |
| P2-4 | source_trace / audit / quality metadata 为公开契约 | §6、§7、§8 |
| P2-5 | MongoDB-first；SQLite 仅 test/offline/legacy read-only | §0（继承基线） |
| P2-6 | 集合命名 `03_data_ud_query_audit` / `03_data_ud_quality_summary` | §6、§7 |
| P2-7 | Production Gate：Pascal 确认前零 DDL/零真实写入 | §9 |
| P2-8 | Sector Router 不属于 Phase 2 | §1.2 |

### 0.2 三项冻结门禁（Implement 放行前置条件）

T2 Design 必须将以下三项变为精确实现设计。**若任一项仍存多解，必须列为需要 Pascal 在生产写入确认前拍板的事项，不能由 Implement 自行判定**：

1. **分域评分规则**：日线/行情、财务、新闻、指数等域的维度权重、配置来源、适用范围；不得以单一通用阈值替代所有域。
2. **硬失败与降级阈值**：何时 `quality_score=0`、何时封顶、何时只告警；覆盖 stale、核心字段缺失、来源冲突和异常值。
3. **审计与质量汇总持久化方案**：`03_data_ud_query_audit` / `03_data_ud_quality_summary` 的字段、唯一键、索引、TTL/保留期、写入失败降级、回滚，以及生产副作用矩阵。

---

## 1. 需求摘要

Phase 2 在现有 Unified Data Layer 骨架之上，新增 5 个组件/能力：

1. **QualityScorer** — 数据质量评估。接受 `DataResult` + context，输出 `quality_score [0, 1]` + 子维度分 + quality tier。
2. **Quality等级语义** — `direct use` / `warning` / `degrade` / `reject` 四级，消费方按等级决定行为。
3. **AuditLogger** — 追加式查询审计。每次 `DataRouter.query()` 完成后写入审计日志。
4. **QualitySummary** — 按 `(domain, security_id, date)` 聚合的质量汇总，支持快速查询。
5. **Registry 运行治理** — priority 排序、health_state 运行时切换、按状态筛选。

全部组件在 Pascal 确认生产写入前使用 fake/mongomock/fixture/no-op 后端验证。

---

## 2. 范围

### 2.1 In Scope

- [ ] `skills/data/unified_data/quality/scorer.py` — QualityScorer 实现
- [ ] `skills/data/unified_data/quality/config.py` — 质量维度配置模型
- [ ] `skills/data/unified_data/quality/__init__.py` — quality 子包导出
- [ ] `skills/data/unified_data/audit/logger.py` — AuditLogger 实现
- [ ] `skills/data/unified_data/audit/__init__.py` — audit 子包导出
- [ ] `skills/data/unified_data/quality/summary.py` — QualitySummary 组件
- [ ] `skills/data/unified_data/registry.py` — ProviderRegistry 增强（priority + health_state）
- [ ] `skills/data/unified_data/router.py` — DataRouter.query() 质量填充 + 审计触发
- [ ] `tests/data/unified_data/test_quality_scorer.py` — QualityScorer 测试
- [ ] `tests/data/unified_data/test_quality_config.py` — 质量配置测试
- [ ] `tests/data/unified_data/test_audit_logger.py` — AuditLogger 测试
- [ ] `tests/data/unified_data/test_quality_summary.py` — QualitySummary 测试
- [ ] `tests/data/unified_data/test_registry_governance.py` — Registry 治理测试
- [ ] `tests/data/unified_data/test_router_quality.py` — Router 质量填充端到端测试
- [ ] `tests/data/unified_data/fixtures/quality_fixtures.py` — 质量测试 fixture

### 2.2 Out of Scope（Phase 2 不做）

- [ ] ❌ 不做 Sector Router capability
- [ ] ❌ 不做 Registry 持久化到 MongoDB
- [ ] ❌ 不做后台质量汇总周期性计算 / 自动 provider 健康检查 / 熔断器
- [ ] ❌ 不做 ML 模型驱动质量评分
- [ ] ❌ 不做 task_center 集成
- [ ] ❌ 不做 stock framework 集成
- [ ] ❌ 不实现 DSA SQLite adapter
- [ ] ❌ 不修改 TA-CN 子项目代码
- [ ] ❌ 不修改 Phase 0/1A/1B 公开 API 签名（DataResult.quality_score 从 None 变为实际值属于增强，不影响签名）
- [ ] ❌ 不实现生产者/消费者拦截器模式
- [ ] ❌ 不修改 SecurityId、Market、DataProvider、FreshnessPolicy、UnifiedDataConfig、UnifiedDataClient 的公开契约

---

## 3. QualityScorer 契约

### 3.1 接口签名

```python
class QualityScorer:
    """数据质量评估器。

    接受 DataResult + 上下文，输出 quality_score [0,1] + 子维度分 + quality tier。
    所有维度评分规则可配置（按 domain 覆盖）。
    纯计算组件，无 I/O 无 MongoDB。
    """

    def __init__(
        self,
        config: QualityScorerConfig | None = None,
    ) -> None:
        """构建 QualityScorer。

        Args:
            config: QualityScorerConfig 实例。默认使用 QualityScorerConfig() 全部默认值。
        """

    def score(
        self,
        result: DataResult,
        *,
        domain: str | None = None,
        now: datetime | None = None,
    ) -> ScoredResult:
        """对 DataResult 进行质量评分。

        Args:
            result: 待评分的 DataResult（来自 DataRouter.query 的原始输出）。
            domain: 覆盖评分的域。为 None 时从 result.domain 推断。
            now: 覆盖当前时间（用于测试确定性）。为 None 时使用 datetime.now(timezone.utc)。

        Returns:
            ScoredResult，包含 quality_score、dimension_scores、quality_tier、warnings。
        """

class ScoredResult:
    """QualityScorer.score() 的返回值。

    这是 DataResult 的质量元数据增强包，不替换 DataResult 本身。
    """
    quality_score: float              # [0, 1]
    dimension_scores: dict[str, float]  # "completeness" → [0, 1], "freshness" → [0, 1], ...
    quality_tier: str                 # "direct_use" | "warning" | "degrade" | "reject"
    warnings: list[str]               # 触发告警/降级的具体原因
```

### 3.2 质量维度评分规范

#### 3.2.1 完整性（completeness）

| 维度 | 输入信号 | 评分逻辑 | 硬失败条件 |
|------|----------|----------|-----------|
|| completeness | DataResult.is_empty(), DataResult.data 字段存在性 | `is_empty()=True` → 0.0；**Phase 2 已知 domain/operation 核心必填字段缺失数/总必填字段数**（例如 `market_data.kline_daily` 需 `close`, `volume`）；未知 domain/operation 跳过字段级检查 | `is_empty()=True`（score=0） |
|
|> **关于 `list[dict]` payload（如 daily-bar 行情）**：对于 `data=list[dict]` 格式，`_score_completeness` 会逐条记录检查核心字段。得分 = 所有记录中实际存在的核心字段值数 /（记录数 × 核心字段数）。例如 `data=[{"close": 150.0}]`（1 条记录，应有 close+volume=2 值，实有 1 值）→ completeness=0.5。空列表 `[]` 视为 schema 完整（无记录可校验），得分 1.0。详见 DESIGN-03-011 §3.2.1。

默认权重：0.35（详见 §3.4 配置）

#### 3.2.2 时效性（freshness）

| 维度 | 输入信号 | 评分逻辑 | 硬失败条件 |
|------|----------|----------|-----------|
| freshness | DataResult.freshness, fetched_at, domain | freshness=realtime → 1.0；freshness=delayed → 1.0；freshness=cached → 0.9（近 TTL 内）/ 0.6（近 TTL 边界）；freshness=stale → 0.0 | freshness=stale（score=0） |
| | | | freshness=empty（score=0，属于 completeness 硬失败重叠） |

具体公式：

```
age = now - fetched_at  (秒)
ttl = config.get_ttl(domain)

if freshness == "empty":   score = 0.0
if freshness == "stale":   score = 0.0
if freshness == "realtime": score = 1.0
if freshness == "delayed":  score = 1.0
if freshness == "cached":
    if age <= 0.5 * ttl:   score = 0.9
    if 0.5 * ttl < age <= 0.9 * ttl: score = 0.6 + 0.3 * (ttl - age) / (0.5 * ttl)
    if age > 0.9 * ttl:    score = 0.2  # 临近过期
```

默认权重：0.30

#### 3.2.3 来源一致性（consistency）

| 维度 | 输入信号 | 评分逻辑 | 硬失败条件 |
|------|----------|----------|-----------|
| consistency | DataResult.source_trace, DataResult.warnings（是否有冲突警告） | source_trace 无冲突标记 → 1.0；有冲突但已解决 → 0.7；有活跃冲突 → 0.3 | 无硬失败（来源冲突不阻断使用，但 warn） |

> **Phase 2 的 consistency 评分逻辑是轻量级的**：只检查 source_trace 中是否有 explicit 冲突标记字符串（如 `tushare(vs_akshare:price_diverges)`）。**跨数据源的深度一致性交叉校验（如同时取 Tushare 和 AKShare 的日线然后逐字段对比）属于 Phase 3+**，不在 Phase 2 强制要求。

默认权重：0.15

#### 3.2.4 异常/合理性（plausibility）

| 维度 | 输入信号 | 评分逻辑 | 硬失败条件 |
|------|----------|----------|-----------|
| plausibility | DataResult.data 中可检查的数字字段 | 核心字段过值域检查：close/volume > 0、pct_chg 合理范围 → 通过=1.0 未通过=0.0 | close ≤ 0 且 domain 为 market_data（score=0） |

> **Phase 2 的 plausibility 是轻量级边界检查**：检查 `data` 中已知数字字段（close/open/high/low/volume/amount）是否 > 0（对应 market_data 域）或 pct_chg 是否在合理范围（如 [-100, 100]）。深度异常检测（统计分布偏离、Z-score、IQR）属于 Phase 3+。

默认权重：0.20

### 3.3 总分与等级

#### 3.3.1 总分

```
quality_score = sum(weight[d] * score[d] for d in dimensions)
```

但如果有任何维度触发 hard_fail，则 `quality_score = 0.0`（hard fail 优先级高于加权平均）。

#### 3.3.2 等级

| 等级 | quality_score 范围 | 枚举值 | 下游行为 |
|------|-------------------|--------|----------|
| direct use | `≥ 0.9` | `"direct_use"` | 直接使用；类似 `freshness="realtime"` 或 `"delayed"` 的结果 |
| warning | `[0.7, 0.9)` | `"warning"` | 数据可用，消费方应记录告警或标注「需确认」 |
| degrade | `[0.3, 0.7)` | `"degrade"` | 数据可用性受限，降级使用（仅参考，不用于计算仓位/交易决策） |
| reject | `< 0.3` | `"reject"` | 数据不可用，应拒绝使用；与 DataResult.error / empty 等价 |

**等级阈值为默认值（可配置、可域覆盖）。**

### 3.4 配置接口

```python
@dataclass(frozen=True, slots=True)
class QualityScorerConfig:
    """QualityScorer 配置。所有阈值可被按域覆盖。"""

    # 各维度默认权重（总和=1.0）
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

    # 按域的配置覆盖（key = domain name）
    domain_overrides: dict[str, "QualityScorerConfig"] = field(default_factory=dict)
    # 示例：
    # domain_overrides = {
    #     "market_data": QualityScorerConfig(
    #         dimension_weights={"completeness": 0.25, "freshness": 0.40, "consistency": 0.15, "plausibility": 0.20},
    #     ),
    #     "metadata": QualityScorerConfig(
    #         dimension_weights={"completeness": 0.50, "freshness": 0.10, "consistency": 0.20, "plausibility": 0.20},
    #     ),
    # }

    def for_domain(self, domain: str) -> "QualityScorerConfig":
        """返回指定域的配置。如果有域覆盖则合并，否则返回自身。"""
```

### 3.5 完整行为矩阵

| 场景 | DataResult 特征 | 预期 quality_score | quality_tier | warnings |
|------|----------------|-------------------|-------------|----------|
| N1 正常 TA-CN 命中 | freshness="delayed", 非空 payload, fresh | ~0.95 | direct_use | [] |
| N2 缓存命中（新鲜） | freshness="cached", age < 50% TTL | ~0.90 | direct_use | [] |
| N3 外部 Provider 实时 | freshness="realtime", 非空 | ~1.0 | direct_use | [] |
| N4 空结果 | is_empty()=True | 0.0 | reject | ["empty result"] |
| N5 过期缓存命中 | freshness="stale" | 0.0 | reject | ["stale data"] |
| N6 空 payload（empty provider） | provider="empty", is_empty()=True | 0.0 | reject | ["empty result"] |
| N7 相邻过期缓存 | freshness="cached", age > 90% TTL | 0.76 | warning | ["cache near expiry"] |
| N8 错误结果 | provider="error" | 0.0 | reject | ["all providers failed"] |
| N9 来源冲突 | source_trace 含冲突标记 | depends on other dims | warning 或 degrade | ["source conflict: price divergence"] |
| N10 异常值（close ≤ 0） | data 含 close=0 | 0.0（hard fail） | reject | ["invalid close value"] |
|| N11 部分字段缺失 | `data=list[dict]` daily-bar，volume 缺失（如 `[{"close": 150.0}]`） | ~0.825（completeness=0.5 × 0.35 + 其他维度 1.0） | warning | ["missing required fields: volume"] |
| N12 财务数据（较老） | freshness="delayed", age > 6h | ~0.8-0.9（财务域时效性占较低） | warning 或 direct_use | []（正常） |

---

## 4. Registry 运行治理契约

### 4.1 现有 ProviderRegistry 增强

在现有 `skills/data/unified_data/registry.py` 中新增方法，不修改已有方法的签名或行为。

```python
class ProviderRegistry:
    # ... 现有 Phase 0/1B-A 方法不变 ...

    # ------------------------------------------------------------------
    # Phase 2: Priority & Health State
    # ------------------------------------------------------------------

    def set_priority(self, name: str, priority: int) -> None:
        """设置 provider 的优先级（数值越小越优先）。

        Args:
            name: provider 名称。
            priority: 优先级值（默认 100）。
        Raises:
            ValueError: provider 未注册。

        优先级不影响已注册的 _by_capability 顺序；
        影响 get_providers() 排序和 Router 的 fallback 链解析。
        """

    def get_priority(self, name: str) -> int:
        """返回 provider 的优先级。未设置时返回 100。"""

    def set_health(self, name: str, state: str) -> None:
        """设置 provider 的运行健康状态。

        Args:
            name: provider 名称。
            state: "healthy" | "unhealthy" | "disabled"
        Raises:
            ValueError: provider 未注册或 state 非法。

        状态变更不影响注册表结构，只影响 Router 在 Step 4 中的筛选。
        """

    def get_health(self, name: str) -> str:
        """返回 provider 的健康状态。未设置时返回 "healthy"。"""

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
            state_filter: 可选健康状态筛选。None 表示不过滤（返回所有注册的）。

        返回按 priority 升序排序的列表（priority 相同时保持注册顺序）。
        """
```

### 4.2 优先级与健康状态行为矩阵

| 场景 | 配置 | Router Step 4 行为 |
|------|------|-------------------|
| R1 默认优先级 | 未调用 set_priority | 按注册顺序（如 Phase 0/1B） |
| R2 自定义优先级 | tushare=10, akshare=20 | tushare 优先于 akshare |
| R3 优先级相同 | 两者 priority=100 | 按注册顺序（Phase 0 兼容） |
| R4 健康 provider | health="healthy" | 正常进入 is_available() 判断 |
| R5 不健康 provider | health="unhealthy" | trace 记录 `{name}(health: unhealthy)`，跳过 |
| R6 禁用 provider | health="disabled" | trace 记录 `{name}(health: disabled)`，跳过 |
| R7 全部不健康 | 所有 provider unhealthy | 返回 DataResult.error（同全部 unavailable） |
| R8 forced provider 不健康 | provider="tushare", health="unhealthy" | 返回 DataResult.error（不尝试 fallback） |
| R9 混合场景 | tushare healthy(pri=10), akshare unhealthy(pri=20) | 尝试 tushare → 跳过 akshare → 若 tushare 失败则 error |

### 4.3 unregister 与 clear 生命周期契约

Phase 2 新增的 `_priorities` 和 `_health_states` 字段受现有 `unregister()` / `clear()` 方法的生命周期管理，不得在重注册时残留旧值。

| # | 契约 | 验证 |
|---|------|------|
| P2-U1 | `unregister(name)` 成功（返回 `True`）时，原子清理：provider registration、capability index、`_priorities[name]`、`_health_states[name]`。 | unregister → re-register same name → 检查 defaults (priority=100, health="healthy") |
| P2-U2 | `clear()` 作为完整 Registry reset：清理 providers、capability index、整个 `_priorities`、整个 `_health_states`。 | clear → re-register same name → 检查 defaults (priority=100, health="healthy") |
| P2-U3 | unknown/unregistered name 的 `set_priority()` / `set_health()` / `unregister()` 行为与现有契约一致：均抛 `ValueError`；不允许静默忽略或为不存在 name 创建条目。 | unregister("nonexistent") → False（不抛异常，同 Phase 0）；set_priority/set_health nonexistent → ValueError |

---

## 5. DataRouter 查询质量填充契约

### 5.1 路由增强

`DataRouter.query()` 现有返回路径不变，在返回前增加：

```python
def query(self, ...) -> DataResult:
    # ... 现有 Step 1-4 逻辑不变 ...
    result = self._internal_orchestrator(...)
    
    # Phase 2: QualityScorer 评分 + AuditLogger
    if self._quality_scorer is not None:
        scored = self._quality_scorer.score(result, domain=domain)
        result.quality_score = scored.quality_score
        result.warnings = list(result.warnings or []) + scored.warnings
    
    # Phase 2: AuditLogger（catch-and-log）
    if self._audit_logger is not None:
        self._audit_logger.log(result, duration_ms=...)
        # QualitySummary 由 AuditLogger 内部触发
    
    return result
```

### 5.2 DataRouter 构造函数增强

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
        # ... 现有构造逻辑不变 ...
        self._quality_scorer = quality_scorer
        self._audit_logger = audit_logger
```

**None 默认值语义**：quality_scorer=None 时，`DataResult.quality_score` 保持 None（即 Phase 0/1A/1B 兼容行为）。audit_logger=None 时，不产生审计日志。实现不得因 quality_scorer/audit_logger 为 None 而改变 Router 核心查询行为。

### 5.3 查询注入行为矩阵

| 场景 | quality_scorer | audit_logger | 预期行为 |
|------|---------------|--------------|----------|
| DR-301 | None | None | 同 Phase 0/1A/1B，quality_score=None，无审计 |
| DR-302 | QualityScorer | None | DataResult.quality_score 有值，无审计 |
| DR-303 | None | AuditLogger | quality_score=None，审计日志写入 |
| DR-304 | QualityScorer | AuditLogger（real） | 全量：评分 + 审计 + QualitySummary 汇总 |
| DR-305 | QualityScorer | AuditLogger（noop） | 评分 + noop 审计/汇总 |
| DR-306 | QualityScorer + force_refresh | AuditLogger | 跳过 Step 2/3，外部查询仍有评分和审计 |
| DR-307 | QualityScorer + error result | AuditLogger | 评分（0.0）+ 审计 success=false |

---

## 6. AuditLogger 契约

### 6.1 接口签名

```python
class AuditLogger:
    """追加式查询审计日志组件。

    每次 DataRouter.query() 完成后被调用。写入 03_data_ud_query_audit 集合。
    写入采用 catch-and-log 模式，失败不阻断查询。
    """

    def __init__(
        self,
        mongo_db: Any = None,           # 生产或 mongomock Database；None=noop
        collection_name: str = "03_data_ud_query_audit",
        ttl_days: int = 90,              # TTL 周期（Design 阶段 Pascal 确认）
    ) -> None:
        """构建 AuditLogger。

        Args:
            mongo_db: MongoDB 数据库句柄。None 时 logger 内部不写入任何数据（noop 模式）。
            collection_name: 审计集合名。
            ttl_days: TTL 过期天数（默认 90 天）。DB 层面使用相同的 TTL 索引。
        """

    def log(
        self,
        result: DataResult,
        *,
        consumer: str = "unified_data",
        duration_ms: int = 0,
        params: dict | None = None,
    ) -> None:
        """记录一次查询审计事件。

        Args:
            result: 查询结果 DataResult。
            consumer: 消费方标识（来自 UnifiedDataConfig.consumer）。
            duration_ms: 查询总耗时（毫秒）。
            params: 查询参数（不含敏感字段）。
        """
```

### 6.2 审计文档 schema

集合：`tradingagents.03_data_ud_query_audit`

```json
{
  "_id": ObjectId,
  "audit_id": "uuid-string",
  "security_id": "CN:600519",
  "market": "CN",
  "capability": "market_data.kline_daily",
  "consumer": "unified_data",
  "fetched_at": ISODate("2026-07-15T10:00:00Z"),
  "duration_ms": 142,
  "provider": "ta_cn_internal",
  "source_trace": ["ta_cn_internal(ok)"],
  "freshness": "delayed",
  "quality_score": 0.95,
  "quality_tier": "direct_use",
  "success": true,
  "error_message": null,
  "params": {"limit": 120},
  "quality_warnings": []
}
```

`quality_warnings` 的类型为 `list[str]`，用于保存 QualityScorer 产生的质量告警；没有告警时必须写入合法默认值空列表 `[]`，不得省略字段或写入 `null`。

### 6.3 索引

```javascript
// TTL 索引（按 fetched_at 过期，90 天）
db.03_data_ud_query_audit.createIndex(
  {"fetched_at": 1},
  {"expireAfterSeconds": 90 * 24 * 3600}
)

// 按 security_id 查询（排查特定标的的审计记录）
db.03_data_ud_query_audit.createIndex(
  {"security_id": 1, "fetched_at": -1}
)

// 按 capability 聚合查询
db.03_data_ud_query_audit.createIndex(
  {"capability": 1, "fetched_at": -1}
)
```

### 6.4 行为矩阵

| 场景 | mongo_db | 预期行为 |
|------|----------|----------|
| AL-101 | None | noop，不写 MongoDB，不抛异常 |
| AL-102 | mongomock.Database | 写入 mongomock，不依赖真实 MongoDB |
| AL-103 | pymongo.Database | 写入生产审计集合 |
| AL-104 | 写入异常（连接断开） | catch-and-log（logger.warning），不阻断查询返回值 |
| AL-105 | 写入抛出非预期异常 | catch-and-log（logger.warning + logger.exception），不阻断 |

---

## 7. QualitySummary 契约

### 7.1 接口签名

```python
class QualitySummary:
    """按 (domain, security_id, date) 聚合的质量汇总。

    每次 AuditLogger.log() 写入后触发 upsert。写入采用 catch-and-log 模式。
    """

    def __init__(
        self,
        mongo_db: Any = None,           # None=noop
        collection_name: str = "03_data_ud_quality_summary",
    ) -> None:
        ...

    def update(
        self,
        result: DataResult,
        *,
        quality_score: float | None,
        quality_tier: str | None,
        now: datetime | None = None,
    ) -> None:
        """更新质量汇总。

        Args:
            result: 查询结果 DataResult。
            quality_score: QualityScorer 评分。
            quality_tier: 质量等级。
            now: 覆盖当前时间（测试用）。

        按 (domain, security_id, date) 复合键 upsert：
        - date = now.date() (YYYY-MM-DD)
        - query_count += 1
        - avg_quality_score = running average
        - min/max 酌情更新
        - provider_distribution[result.provider] += 1
        - last_updated = now
        """

    def get_summary(
        self,
        domain: str,
        security_id: SecurityId,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """查询质量汇总。

        Args:
            domain: 域名称。
            security_id: 标的。
            from_date: 起始日期 YYYY-MM-DD（含）。为 None 则不限。
            to_date: 截止日期 YYYY-MM-DD（含）。为 None 则不限。

        Returns:
            匹配的 QualitySummary 文档列表。
        """
```

### 7.2 文档 schema

集合：`tradingagents.03_data_ud_quality_summary`

```json
{
  "_id": "market_data.kline_daily:CN:600519:2026-07-15",
  "domain": "market_data",
  "security_id": "CN:600519",
  "date": "2026-07-15",
  "query_count": 42,
  "avg_quality_score": 0.93,
  "min_quality_score": 0.72,
  "max_quality_score": 1.0,
  "provider_distribution": {
    "ta_cn_internal": 30,
    "tushare": 10,
    "akshare": 2
  },
  "last_updated": ISODate("2026-07-15T18:30:00Z")
}
```

### 7.3 索引

```javascript
// 主键 upsert（复合键 = "domain:security_id:date"），不需要额外唯一索引
// 按 domain + security_id 快速查询质量趋势
db.03_data_ud_quality_summary.createIndex(
  {"domain": 1, "security_id": 1, "date": -1}
)
```

### 7.4 行为矩阵

| 场景 | mongo_db | 预期行为 |
|------|----------|----------|
| QS-101 | None | noop，不写 MongoDB，不抛异常 |
| QS-102 | mongomock | 写入 mongomock |
| QS-103 | 写入异常 | catch-and-log，不阻断 |
| QS-104 | 批量重复查询 | upsert 幂等，query_count 累加 |
| QS-105 | get_summary 无数据 | 返回 [] |

---

## 8. QualitySummary 与 AuditLogger 的协调

```python
# DataRouter.query() 返回前的 Phase 2 流程：

# 1. QualityScorer 评分（如有）
if self._quality_scorer is not None:
    scored = self._quality_scorer.score(result)
    result.quality_score = scored.quality_score
    result.warnings = list(result.warnings or []) + scored.warnings

# 2. AuditLogger 写入（如有 + catch-and-log）
if self._audit_logger is not None:
    self._audit_logger.log(result, consumer=..., duration_ms=..., params=...)
    # 3. QualitySummary 由 AuditLogger 内部触发
    # (AuditLogger.log() 内部调用 QualitySummary.update())
```

**设计选择**：QualitySummary 的更新由 AuditLogger 触发，而非分别从 Router 调用两次。这样 Router 对 Phase 2 只有一个调用点（`audit_logger.log()`），Router 不直接依赖 QualitySummary 组件。

---

## 9. Production Gate

### 9.1 Pascal 确认前 Implement 的默认行为

| 组件 | Pascal 确认前 | Pascal 确认后 |
|------|--------------|--------------|
| AuditLogger | `mongo_db=None`（noop 模式），或显式注入 mongomock | `mongo_db` 指向生产 `tradingagents` 库 |
| QualitySummary | `mongo_db=None`（noop 模式），或显式注入 mongomock | `mongo_db` 指向生产库 |
| 集合/索引创建 | 不执行任何 DDL（不在代码/测试/脚本中硬编码 createIndex） | 通过 rollback-safe 部署脚本创建 |
| 真实 provider smoke | 不执行 | Design 阶段 Pascal 确认后可选 |

### 9.2 Implement 代码约束

所有 Phase 2 新增代码必须经过以下约束验证：

1. `AuditLogger.__init__` / `QualitySummary.__init__` 中 `mongo_db=None` 时必须安全地初始化为 noop，不能假创建连接。
2. `log()` / `update()` 在 noop 模式下不抛异常、不写日志。
3. 所有测试使用 mongomock，不依赖真实 MongoDB。
4. 测试中不创建真实 MongoDB 集合或索引。
5. 实现在 `production_gate` 或等价标志位阻止真实写入。

---

## 10. 兼容性影响扫描

### 10.1 对已有消费者的影响

| 消费者 | 影响 | 向后兼容 |
|--------|------|----------|
| 读取 DataResult.quality_score | 原为 None，现变为 float | 兼容（None 和 float 均可处理） |
| 读取 DataResult.warnings | 原为 []，现可能包含质量告警 | 兼容（list 结构不变） |
| DataRouter.query() 返回值 | 签名不变，返回值字段增强 | 兼容 |
| ProviderRegistry.get_providers() | 新参数 state_filter 有默认值 | 兼容（不传参数 = 原有行为） |
| ProviderRegistry 的其他方法 | 无变化 | 兼容 |

### 10.2 对测试的影响

| 测试 | 影响 | 兼容策略 |
|------|------|----------|
| Phase 0/1A/1B 已有 269 测试 | quality_scorer=None, audit_logger=None | 完全不影响 |
| 已有 router 测试 | quality_score=None 变为 | 现有断言检查 None 不受影响 |
| 已有 registry 测试 | 不调用新增方法 | 不受影响 |

---

## 11. 实现文件与测试目录清单（精确路径）

### 11.1 新增文件

| 文件 | 说明 |
|------|------|
| `skills/data/unified_data/quality/__init__.py` | quality 子包导出 |
| `skills/data/unified_data/quality/scorer.py` | QualityScorer 实现 |
| `skills/data/unified_data/quality/config.py` | QualityScorerConfig |
| `skills/data/unified_data/audit/__init__.py` | audit 子包导出 |
| `skills/data/unified_data/audit/logger.py` | AuditLogger 实现 |
| `skills/data/unified_data/quality/summary.py` | QualitySummary 实现（放在 quality/ 下而非 audit/ 下） |
| `tests/data/unified_data/test_quality_scorer.py` | QualityScorer 单元测试 |
| `tests/data/unified_data/test_quality_config.py` | QualityScorerConfig 测试 |
| `tests/data/unified_data/test_audit_logger.py` | AuditLogger 测试 |
| `tests/data/unified_data/test_quality_summary.py` | QualitySummary 测试 |
| `tests/data/unified_data/test_registry_governance.py` | Registry 治理测试 |
| `tests/data/unified_data/test_router_quality.py` | Router 质量填充端到端测试 |
| `tests/data/unified_data/fixtures/quality_fixtures.py` | 质量测试 fixture（各种评分配置 fixture） |

### 11.2 修改文件

| 文件 | 修改类型 |
|------|----------|
| `skills/data/unified_data/__init__.py` | 新增导出 QualityScorer、ScoredResult、QualityScorerConfig、AuditLogger、QualitySummary |
| `skills/data/unified_data/registry.py` | 新增 priority/health_state 方法 |
| `skills/data/unified_data/router.py` | 构造函数新增 quality_scorer/audit_logger 参数 + query() 尾部评分+审计调用 |
| `tests/data/unified_data/conftest.py` | 可选新增 quality_score fixture |

---

## 12. 无副作用测试与生产 Smoke 的分界

### 12.1 无副作用测试（全部测试均在此范畴）

运行 `PYTHONPATH=. pytest tests/data/unified_data/ -m "not production_gate" -v`

- 全部使用 mongomock
- 全部使用 FakeProvider/FakeTA_CNAdapter
- 不连接真实 MongoDB
- 不调用真实外部 API
- 不创建 MongoDB 集合或索引

### 12.2 生产 Smoke（仅 Pascal 确认后可运行）

运行 `PYTHONPATH=. pytest tests/data/unified_data/ -m "production_gate" -v`

- 需要真实 MongoDB 连接（`MONGODB_URI` 环境变量）
- 需要真实写入到 `03_data_ud_query_audit` / `03_data_ud_quality_summary` 集合
- 使用 `@pytest.mark.production_gate` 标记

### 12.3 验收命令

```bash
# 快速验证（无质量/审计）
PYTHONPATH=. pytest tests/data/unified_data/ -m "not production_gate" -q --tb=short

# 质量相关全量
PYTHONPATH=. pytest tests/data/unified_data/test_quality_scorer.py tests/data/unified_data/test_quality_config.py tests/data/unified_data/test_registry_governance.py tests/data/unified_data/test_router_quality.py -q --tb=short

# 审计相关全量
PYTHONPATH=. pytest tests/data/unified_data/test_audit_logger.py tests/data/unified_data/test_quality_summary.py -q --tb=short
```

---

## 13. 验收标准

1. **文件存在**：
   - `docs/rfc/03_data/RFC-03-011-unified-data-phase-2-quality-audit-governance.md`
   - `docs/spec/03_data/SPEC-03-011-unified-data-phase-2-quality-audit-governance.md`

2. **QualityScorer**：
   - `score()` 返回 `ScoredResult`，包含 `quality_score`、`dimension_scores`、`quality_tier`、`warnings`
   - 4 维度评分均实现：completeness、freshness、consistency、plausibility
   - 子分与总分匹配权重配置
   - hard fail 时 quality_score 置 0
   - 空 data/error 结果评分 0.0
   - 正常结果评分 ≥ 0.9

3. **QualityScorerConfig**：
   - 默认权重总和 = 1.0
   - 等级阈值默认值合理（direct_use ≥ 0.9, warning ≥ 0.7, degrade ≥ 0.3）
   - 按域覆盖功能正常

4. **Registry 治理**：
   - `set_priority()` / `get_priority()` 正常工作
   - `set_health()` / `get_health()` 正常工作
   - `get_providers(state_filter=)` 正确按状态筛选
   - 返回列表按 priority 升序

5. **AuditLogger**：
   - `mongo_db=None` 时 noop
   - `mongo_db=mongomock` 时写入 audit 集合
   - document 包含全部必填字段（§6.2）
   - 写入异常 catch-and-log 不抛到调用方

6. **QualitySummary**：
   - `mongo_db=None` 时 noop
   - upsert 按 `(domain, security_id, date)` 复合键
   - `get_summary()` 返回正确范围的数据

7. **Router 质量填充**：
   - quality_scorer=None → quality_score 保持 None
   - quality_scorer 注入 → quality_score 有值
   - audit_logger 注入 → 审计日志写入
   - Phase 0/1A/1B 已有 269 测试不因 Phase 2 修改而失败

8. **Production Gate**：
   - 所有 MongoDB 写入组件有 mongo_db=None 时的安全 noop 路径
   - 测试中无真实 MongoDB 连接或 DDL

---

## 14. 参考资料

- `docs/rfc/03_data/RFC-03-011-unified-data-phase-2-quality-audit-governance.md`（本 SPEC 来源 RFC）
- `docs/spec/03_data/SPEC-03-007-unified-data-layer.md` — 基础契约
- `docs/spec/03_data/SPEC-03-009-unified-data-phase-1b-persistence-plane.md` — Phase 1B-B 契约
- `docs/design/03_data/DESIGN-03-007-unified-data-layer.md` — 详细设计
- `skills/data/unified_data/` — 现有代码基
- `skills/data/unified_data/models/__init__.py` — DataResult、SecurityId
- `skills/data/unified_data/registry.py` — 现有 ProviderRegistry
- `skills/data/unified_data/router.py` — 现有 DataRouter
