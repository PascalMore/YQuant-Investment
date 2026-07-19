# SPEC-03-011：Unified Data Phase 2 — 数据质量评估、审计与运行治理

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 已授权受控 rollout、尚未执行（Authorized for Controlled Rollout, Not Yet Executed） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-15 |
| 最后更新 | 2026-07-19 |
| 来源 RFC | RFC-03-011 |
| 关联 RFC | RFC-03-007（Unified Data Layer）、RFC-03-009（Phase 1B-B 持久化缓存平面） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-009（Phase 1B-B 持久化缓存平面） |
| 关联 Design | DESIGN-03-011（详细设计）、DESIGN-03-007（Unified Data Layer 详细设计） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |
| 版本号 | V1.0 |
| 本版变更 | V0.3→V1.0: Pascal 任务 t_cf78a4c0（SPEC T2）将已授权 Audit-only Query Audit 生产 rollout 契约精确化为可证伪 SPEC。新增 §9 受控 DDL 工具契约（audit_rollout.py）、§10 生产 Smoke 契约（audit_smoke.py）、§11 停止条件与金丝雀验收标准（§11.1~§11.4）、§12 QualitySummary 不可达性测试与静态扫描要求；解决 RFC §15 的 T2-01~T2-06 全部 6 项待定项（§9 各小节标注）。更新 §8 QualitySummary（Phase 1 冻结）、§10 Production Gate（V1.0 授权状态）。 |
| Phase 1 范围 | **Audit-only**：仅 Query Audit（AuditLogger）；QualitySummary 不注入；quality tier 仅观测不构成业务门禁 |

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
| P2-7 | Production Gate：Pascal 确认前零 DDL/零真实写入 | §13 |
| P2-8 | Sector Router 不属于 Phase 2 | §1.2 |
| P2-9 | `audit_rollout.py` 三大模式：dry-run 零副作用、`--verify` 只读验证、`--apply` 有副作用 DDL | §9 |
| P2-10 | `audit_smoke.py` 两大模式：dry-run 零副作用、`--apply` writer→reader round-trip | §10 |
| P2-11 | 停止条件 SC-01~05：DDL/Smoke/QualitySummary/身份泄露/金丝雀失败率触发的暂停/回滚/紧急停止 | §11.1 |
| P2-12 | 金丝雀验收标准 CV-01~05：写入成功率≥99.5%、p99≤200ms、零阻断、零 QualitySummary 污染、零越权 | §11.2 |
| P2-13 | QualitySummary 禁止令 QS-F1~F5：任何路径不得创建 QS 集合、AuditLogger 防御性断言 `quality_summary is None` | §11.3 |
| P2-14 | QualitySummary 不可达性测试：`pytest.mark.quality_summary_forbidden` 系列测试，验证 QS 集合/索引/写入不可达 | §12 |

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
- [ ] `skills/data/unified_data/tests/test_quality_scorer.py` — QualityScorer 测试
- [ ] `skills/data/unified_data/tests/test_quality_config.py` — 质量配置测试
- [ ] `skills/data/unified_data/tests/test_audit_logger.py` — AuditLogger 测试
- [ ] `skills/data/unified_data/tests/test_quality_summary.py` — QualitySummary 测试
- [ ] `skills/data/unified_data/tests/test_registry_governance.py` — Registry 治理测试
- [ ] `skills/data/unified_data/tests/test_router_quality.py` — Router 质量填充端到端测试
- [ ] `skills/data/unified_data/tests/fixtures/quality_fixtures.py` — 质量测试 fixture

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
        ttl_days: int = 365,            # TTL 周期（Pascal 已确认：365 天）
    ) -> None:
        """构建 AuditLogger。

        Args:
            mongo_db: MongoDB 数据库句柄。None 时 logger 内部不写入任何数据（noop 模式）。
            collection_name: 审计集合名。
            ttl_days: TTL 过期天数（默认 365 天，Pascal 已确认）。DB 层面使用相同的 TTL 索引。
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

> **params 字段**（Pascal 已确认）：采用 params 白名单策略，只记录允许的查询参数键。敏感字段（凭据、令牌、密钥）默认丢弃，不进入审计文档。`params` 在审计文档中始终存在（最少为空 JSON 对象 `{}`），不得省略。

`quality_warnings` 的类型为 `list[str]`，用于保存 QualityScorer 产生的质量告警；没有告警时必须写入合法默认值空列表 `[]`，不得省略字段或写入 `null`。

### 6.3 索引

```javascript
// TTL 索引（按 fetched_at 过期，Pascal 已确认：365 天）
db.03_data_ud_query_audit.createIndex(
  {"fetched_at": 1},
  {"expireAfterSeconds": 365 * 24 * 3600}
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

### 7.1 Phase 1 声明

**QualitySummary 在整个 Phase 1 禁用，不注入到 AuditLogger**（即 `AuditLogger.__init__` 的 `quality_summary` 参数始终保持 `None`）。以下 schema 和 TTL 作为后续启用时的已确认值记录在案。

### 7.2 接口签名

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
TTL：365 天（按 `date` 自动过期；Phase 1 不启用，TTL 作为后续启用时的已确认值）

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
// TTL 索引（按 date 过期，Pascal 已确认：365 天）
// 本索引在 Phase 1 不创建（QualitySummary 未启用），作为后续启用时的 DDL
// db.03_data_ud_quality_summary.createIndex(
//   {"date": 1},
//   {"expireAfterSeconds": 365 * 24 * 3600}
// )

// 主键 upsert（复合键 = "domain:security_id:date"），不需要额外唯一索引
// ⛔ Phase 1 不创建（QualitySummary 未启用），以下索引为后续启用时的 DDL
// 按 domain + security_id 快速查询质量趋势
// db.03_data_ud_quality_summary.createIndex(
//   {"domain": 1, "security_id": 1, "date": -1}
// )
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

## 7.5 QualitySummary 与 AuditLogger 的协调

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

**Phase 1 约束**：QualitySummary **不注入**。`AuditLogger.__init__` 的 `quality_summary` 参数始终为 `None`，`log()` 内部不执行 `QualitySummary.update()`。上述设计作为后续启用的架构保留。

**写入失败策略**（Pascal 已确认）：
- **fail-open**：AuditLogger / QualitySummary 写入失败不阻断主查询返回
- **本地结构化日志**：写入失败时通过 `logger.warning` 输出，包含失败原因和集合名
- **不接外部告警**：Phase 1 写入失败不接 PagerDuty/短信/Telegram 等外部告警
- **已写入数据不自动删除**：回滚优先停用注入，已有数据保留

---

## 8. DDL 工具与身份管理契约

### 8.1 DDL 工具

Phase 2 的 Audit-only 生产 DDL 通过独立受控脚本 `scripts/unified_data/audit_rollout.py` 执行。此脚本的职责范围、约束和行为由以下契约精确限定。

#### 8.1.1 脚本路径与 CLI

| 属性 | 值 |
|------|-----|
| 脚本路径 | `scripts/unified_data/audit_rollout.py` |
| CLI 参数 | 仅 `--apply`（有副作用）和 `--verify`（只读验证）；`database` / `collection` / `writer-role` / `reader-role` 均为模块级固定常量，不得由 CLI 覆盖 |
| 退出码 | 0=成功（dry-run/verify/apply）；1=验证失败；2=范围校验失败（fail-fast）；3=凭证缺失（fail-fast）；4=运行时错误 |

#### 8.1.2 DDL 工具职责

| # | 职责 | 说明 |
|---|------|------|
| D1 | 使用独立 DDL bootstrap 身份 | 读取 `YQUANT_UD_AUDIT_DDL_MONGO_*` 环境变量，不得复用运行时 writer/reader 身份 |
| D2 | 创建/校验 2 custom roles | `yquant_ud_audit_writer_role`（insert-only on `03_data_ud_query_audit`）、`yquant_ud_audit_reader_role`（find-only on `03_data_ud_query_audit`） |
| D3 | 创建/校验 2 runtime users | `yquant_ud_audit_writer_user`（授予 writer role）、`yquant_ud_audit_reader_user`（授予 reader role） |
| D8 | createUser 初始密码传递 | 当须 createUser（目标用户不存在）时，读取对应 runtime 密码环境变量作为 `createUser.pwd`；缺失/空 fail-fast（退出码 3）；幂等校验路径不读密码；详见 §8.7 |
| D4 | 创建/校验集合与索引 | `tradingagents.03_data_ud_query_audit` + 3 索引（TTL fetched_at + 2 个二级索引） |
| D5 | 拒绝 broad identity | 绝对不授予任何其他 collection 的权限，违者 fail-fast |
| D6 | dry-run 缺省 | 未传 `--apply` 时零副作用 |
| D7 | 凭证缺失 fail-fast | 缺少 `YQUANT_UD_AUDIT_DDL_MONGO_URI` / `USERNAME` / `PASSWORD` 时退出码 3 |

### 8.2 正式命名空间

| 类型 | 正式名称 | 权限范围 |
|------|---------|----------|
| Writer Role | `yquant_ud_audit_writer_role` | `03_data_ud_query_audit` insert-only |
| Reader Role | `yquant_ud_audit_reader_role` | `03_data_ud_query_audit` find-only |
| Writer User | `yquant_ud_audit_writer_user` | 授予 writer role |
| Reader User | `yquant_ud_audit_reader_user` | 授予 reader role |
| DDL Bootstrap | 独立身份（非上述任一） | createCollection + createIndex + createRole + createUser |

**命名前缀**：所有角色和用户必须以 `yquant_ud_audit_` 开头。DDL 脚本内部校验前缀，不匹配时 fail-fast（退出码 2）。

### 8.3 环境变量契约

**DDL 身份**（bootstrap 必须）：

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
| `YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD` | 条件强制¹ | 无 | Writer 密码（createUser 初始密码） |
| `YQUANT_UD_AUDIT_WRITER_MONGO_AUTH_DB` | 否 | `admin` | Writer 认证数据库 |

**Reader 身份**（未来只读查询，Phase 1 不创建）：

| 环境变量 | 强制 | 默认值 | 说明 |
|----------|------|--------|------|
| `YQUANT_UD_AUDIT_READER_MONGO_URI` | 否 | 无 | Reader 连接 URI |
| `YQUANT_UD_AUDIT_READER_MONGO_USERNAME` | 否 | 无 | Reader 用户名 |
| `YQUANT_UD_AUDIT_READER_MONGO_PASSWORD` | 条件强制¹ | 无 | Reader 密码（createUser 初始密码） |
| `YQUANT_UD_AUDIT_READER_MONGO_AUTH_DB` | 否 | `admin` | Reader 认证数据库 |

> ¹ **条件强制**：DDL 工具确定须 `createUser`（目标用户尚不存在）时，对应密码成为强制项；缺失/空值在 `createUser` DDL 命令发出前 fail-fast（退出码 3）。用户已存在（幂等校验）时不需要。详见 §8.7。

### 8.4 params 白名单 — 模块级常量

| # | 契约 | 实现约束 |
|---|------|----------|
| W1 | 白名单定义为 `scripts/unified_data/audit_rollout.py` 的模块级常量 `ALLOWED_PARAMS: set[str]` | 不得通过构造函数注入；常量在模块加载时固定 |
| W2 | 只记录白名单中存在的查询参数键 | 不在白名单中的键丢弃 |
| W3 | 敏感字段默认丢弃 | `token`、`api_key`、`secret`、`password`、`credential` 永不进入审计文档 |
| W4 | `params` 在审计文档中始终存在 | 最少为空 JSON 对象 `{}`，不得省略或写入 `null` |

### 8.5 拒绝 broad business identity

- DDL 脚本**禁止**复用任何业务数据库用户（`portfolio`、`smart_money`、`signal`、`trade`、`cache` 等既有业务集合使用的账号）
- runtime writer/reader 权限严格限定为 `03_data_ud_query_audit`
- 违反此规则脚本 fail-fast（退出码 2），硬性约束，不可覆盖

### 8.6 Audit-only 不变量

| 不变量 | 约束 |
|--------|------|
| 单集合 | Phase 1 只操作 `03_data_ud_query_audit`；不得创建 `03_data_ud_quality_summary` |
| 3 索引 | TTL `fetched_at` + `(security_id, fetched_at)` + `(capability, fetched_at)`；索引名、键顺序、expireAfterSeconds 不得擅自修改 |
| Audit-only | 仅记 query audit；QualitySummary 不注入；quality tier 仅观测 |
| `--apply` 副作用 | 只有显式 `--apply` 时执行 DDL；凭证缺失 fail-fast（退出码 3） |

### 8.7 createUser 初始密码传递契约

MongoDB `createUser` 对 SCRAM 用户强制要求 `pwd` 字段。DDL 工具创建 runtime writer/reader user 时必须提供初始密码。本节固化密码来源、消费时机与安全防护契约。

#### 8.7.1 密码来源

复用既有 runtime 密码环境变量（不新增 env、不新增 alias/fallback）：

| 目标 user | createUser.pwd 来源环境变量 |
|-----------|------------------------------|
| `yquant_ud_audit_writer_user` | `YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD` |
| `yquant_ud_audit_reader_user` | `YQUANT_UD_AUDIT_READER_MONGO_PASSWORD` |

语义：runtime 登录密码 = createUser 初始密码。创建出的用户可直接以该密码认证，无需二次配置。

#### 8.7.2 触发与消费契约

| # | 契约 | 实现约束 |
|---|------|----------|
| PWD-C1 | createUser 前 `usersInfo` 判定用户是否存在 | `_ensure_user` 先查再建；`usersInfo` 预检经 DDL bootstrap identity（`YQUANT_UD_AUDIT_DDL_MONGO_*`）执行只读连接，仅读不写，不在预检阶段创建/更新 role/user/index/collection |
| PWD-C2 | 仅须 createUser（用户不存在）时读取密码环境变量，作为 `createUser.pwd` | 密码仅出现在该单条 DDL 命令中 |
| PWD-C3 | 用户已存在（幂等路径）不得读取/轮换/重设密码 | 仅校验 role binding 精确匹配 |
| PWD-C4 | 须 createUser 但密码缺失/空 → fail-fast（退出码 3），在 createUser DDL 发出前 | **禁止的是发出不含 pwd 的 createUser 写 DDL**，而非禁止预检只读连接；DDL identity 的 `usersInfo` 存在性预检连接属于合法操作（与 §8.1 D7 的"DDL bootstrap 凭证缺失→不发起任何连接"互斥，后者是 DDL 自身凭证缺失场景） |
| PWD-C5 | 用户已存在但 role binding 不一致 → fail-closed（退出码 4），不得修改/重建用户 | 与 §8.5、§8.6 一致 |

#### 8.7.3 安全防护（硬性约束）

| # | 防护 | 说明 |
|---|------|------|
| PWD-S1 | 不得打印（print）、记录（logger/log）、返回或持久化 password 值 | 任何输出路径均禁止 |
| PWD-S2 | password 变量生命周期限定在 createUser 命令构建与执行的单一作用域 | 执行后立即丢弃 |
| PWD-S3 | 不得出现在 traceback / 异常消息 / 诊断输出中 | 异常一律用 `repr` 或结构性字段 |
|| PWD-S4 | DDL bootstrap 密码与 runtime 密码严格隔离 | 不得交叉引用 |


---

## 9. 受控 DDL 工具执行契约（audit_rollout.py）

本节解决 RFC §15 的 T2-01（ALLOWED_PARAMS 精确化）、T2-03（AuditLogger 生产 MongoDB client 生命周期）、T2-05（Reader user Phase 1 创建策略）、T2-06（--verify QualitySummary 不存在检查退出码）。

### 9.1 脚本路径与 CLI

| 属性 | 值 |
|------|-----|
| 脚本路径 | `scripts/unified_data/audit_rollout.py` |
| CLI 参数 | 仅 `--apply`（有副作用）和 `--verify`（只读验证）；`database` / `collection` / `writer-role` / `reader-role` 均为模块级固定常量（§8.1.1），**不得由 CLI 覆盖** |
| 退出码 | 0=成功（dry-run/verify/apply）；1=验证失败；2=范围校验失败；3=凭证缺失；4=运行时错误 |

### 9.2 三大模式

#### 9.2.1 dry-run（默认，零副作用）

- 执行 `_validate_targets` 静态校验 database/collection/identity names
- 打印预期执行计划（collection → 3 indexes → 2 roles → 2 users）
- 不加载任何环境变量、不创建 MongoDB 连接、不读取凭证
- 退出码：0

**禁止行为**：dry-run 不得加载或检查运行时 writer/reader 密码环境变量值（仅可在静态校验中检查常量名称）。

#### 9.2.2 `--verify`（只读验证）

- 经 DDL bootstrap 身份（`YQUANT_UD_AUDIT_DDL_MONGO_*`）连接 MongoDB
- 7 项验证（逐项 fail-fast 并报告具体情况）：

| # | 验证项 | 检查内容 | 可选依赖 |
|---|--------|----------|----------|
| V1 | collection | `tradingagents.03_data_ud_query_audit` 是否存在 | 无 |
| V2 | 3 个索引 | TTL `fetched_at`（expireAfterSeconds=31536000）、`(security_id, fetched_at)`、`(capability, fetched_at)` — 索引名、键顺序、expireAfterSeconds 精确匹配 | collection 存在 |
| V3 | writer role | `yquant_ud_audit_writer_role` 是否存在，privileges 精确匹配（db=tradingagents, collection=03_data_ud_query_audit, actions=[insert]），inherited roles 为空 | 无 |
| V4 | reader role | `yquant_ud_audit_reader_role` 是否存在，privileges 精确匹配（actions=[find]），inherited roles 为空 | 无 |
| V5 | writer user | `yquant_ud_audit_writer_user` 是否存在，role binding = `yquant_ud_audit_writer_role @ tradingagents` | writer role 存在 |
| V6 | reader user | `yquant_ud_audit_reader_user` 是否存在，role binding = `yquant_ud_audit_reader_role @ tradingagents` | reader role 存在 |
| V7 | QualitySummary 不存在 | `03_data_ud_quality_summary` 集合不得存在 | 无 |

- 退出码：0=全部通过（含 QualitySummary 预期不存在视为通过）；1=任一项验证失败
- `--verify` 路径**不得**执行任何 DDL 或写入操作

**T2-06 解决**：QualitySummary 不存在检查在 `--verify` 中是**硬性验证项**（与 collection/index/role/user 同级）。集合不存在视为**通过**（退出码 0，被此项计入"验证通过"），集合存在视为**失败**（退出码 1）。

#### 9.2.3 `--apply`（有副作用 DDL）

按序执行（幂等保护、任一步骤失败即停止）：

| 步序 | 操作 | 幂等语义 | 失败后果 |
|------|------|----------|----------|
| 0 | 只读 user 预检：经 DDL identity 执行 `usersInfo` 判定 writer/reader user 是否存在。缺失 user 预检对应密码环境变量 | 仅读不写，不在预检阶段创建/更新任何资源 | 密码缺失 → fail-fast（退出码 3），在 createUser DDL 前退出 |
| 1 | 创建/校验 `03_data_ud_query_audit` 集合（若已存在则静默跳过） | 幂等：`createCollection` 已存在不报错 | 集合创建失败且不存在 → 退出码 4 |
| | 防御性检查：确保 `03_data_ud_quality_summary` 集合**不存在** | 若存在 → 退出码 4，禁止继续 | 退出码 4 |
| 2 | 创建/校验 3 个索引（TTL fetched_at + 两个二级索引），每条索引精确比对 keys/options | 已存在且精确匹配 → skipped；存在但不匹配 → mismatched fail-closed | 索引定义不匹配 → 退出码 4 |
| 3 | 创建/校验 `yquant_ud_audit_writer_role`（insert-only on audit collection） | 已存在且精确匹配 → unchanged；不匹配 fail-closed | 退出码 4 |
| 4 | 创建/校验 `yquant_ud_audit_reader_role`（find-only on audit collection） | 同上 | 同上 |
| 5 | 创建/校验 `yquant_ud_audit_writer_user`（授予 writer role） | 用户不存在 → createUser 含 pwd（见 §8.7）；已存在仅校验 role binding | 密码缺失退出码 3；binding 不匹配退出码 4 |
| 6 | 创建/校验 `yquant_ud_audit_reader_user`（授予 reader role） | 同上 | 同上 |

- 退出码：0=全部成功；2=范围校验失败；3=凭证缺失；4=运行时错误或已存在身份不匹配
- `--apply` 使用**独立 DDL bootstrap 身份**：`YQUANT_UD_AUDIT_DDL_MONGO_URI/USERNAME/PASSWORD`
- 禁止：`--apply` 绝不以任何形式复用 runtime writer/reader 或业务身份

### 9.3 ALLOWED_PARAMS 精确白名单（T2-01 解决）

| 键 | 类型 | 语义 |
|----|------|------|
| `security_id` | string | 标的 canonical 代码 |
| `market` | string | 市场代码 |
| `domain` | string | 域名称 |
| `operation` | string | 域内操作 |
| `start_date` | string | 查询开始日期 YYYY-MM-DD（含） |
| `end_date` | string | 查询结束日期 YYYY-MM-DD（含） |
| `limit` | int | 返回记录数上限 |
| `frequency` | string | 数据频率（daily/weekly/monthly） |
| `provider` | string | 强制指定数据 provider |
| `consumer` | string | 调用方标识 |
| `force_refresh` | bool | 是否强制刷新缓存 |

白名单定义为 `scripts/unified_data/audit_rollout.py` 的模块级常量 `ALLOWED_PARAMS: frozenset[str]`（**不通过构造函数注入**）。`audit/logger.py` 的 `ALLOWED_PARAM_KEYS` 与之一致。敏感字段（`token`、`api_key`、`secret`、`password`、`credential`）不在白名单中，默认丢弃。

### 9.4 静态 allow-list 常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `ALLOWED_DATABASE` | `"tradingagents"` | 唯一允许操作的数据库 |
| `ALLOWED_COLLECTION` | `"03_data_ud_query_audit"` | 唯一允许操作的集合 |
| `FORBIDDEN_COLLECTIONS` | `{"03_data_ud_quality_summary", ...}` | Phase 1 拒绝的集合（含 QualitySummary） |
| `TTL_SECONDS` | `31536000`（365×86400） | TTL 过期秒数 |
| `INDEX_SPECS` | 3 条索引元组 `(name, keys, opts)` | 索引精确定义（§6.3） |
| `WRITER_ROLE_NAME` | `"yquant_ud_audit_writer_role"` | Writer custom role 名称 |
| `READER_ROLE_NAME` | `"yquant_ud_audit_reader_role"` | Reader custom role 名称 |
| `WRITER_USER_NAME` | `"yquant_ud_audit_writer_user"` | Writer runtime user 名称 |
| `READER_USER_NAME` | `"yquant_ud_audit_reader_user"` | Reader runtime user 名称 |
| `ALLOWED_IDENTITY_NAMES` | 上述 4 名称的 `frozenset` | 身份名称精确白名单 |
| `ALLOWED_PARAMS` | 上述 11 键的 `frozenset` | params 白名单（§9.3） |

### 9.5 Reader user Phase 1 创建策略（T2-05 解决）

**决策**：Phase 1 DDL **创建** `yquant_ud_audit_reader_user`（身份预留），即使 Phase 1 不使用 reader 身份执行查询。

**理由**：
- 身份一致性：writer/reader 对等创建，确保 DDL 结果完整可验证。
- 未来兼容：后续 Phase 启用 QualitySummary 或 reader 查询时无需额外 DDL 操作。
- 安全：reader 权限锁定为 `find-only on 03_data_ud_query_audit`，即使存在也无法越界访问其他集合。

**约束**：
- Reader user 的 `createUser` 初始密码同样遵守 §8.7 的密码传递契约。
- Phase 1 代码中 `AuditLogger` 和 `DataRouter` 不使用 reader 身份。

### 9.6 AuditLogger 生产 MongoDB client 生命周期（T2-03 解决）

**决策**：生产 AuditLogger 通过**构造函数注入** `mongo_db` 句柄（`pymongo.database.Database`），不自建 MongoDB client 或连接池。

**理由**：
- 连接池生命周期由应用层（`UnifiedDataClient` 或启动配置）统一管理，AuditLogger 纯消费。
- 各环境的连接池参数（`maxPoolSize`、`serverSelectionTimeoutMS`、`connectTimeoutMS`）由部署配置决定，不在 AuditLogger 代码中硬编码。
- DDL 脚本（`audit_rollout.py`/`audit_smoke.py`）自建短生命周期 client（`serverSelectionTimeoutMS=5000`、`connectTimeoutMS=5000`），用后 `close()`，不与运行时共享。

**测试行为**：测试中注入 `mongomock.database.Database`，不连接真实 MongoDB。

### 9.7 现有实现缺口（Design §8.9.1 引用）

`scripts/unified_data/audit_rollout.py` 在初次编写时尚有 5 个已知缺口（G1~G5，详见 DESIGN-03-011 §8.9.1），均在 Implement Remediation 阶段（task t_445911bf）按 reviewer t_c051239d 意见修复完成。当前实现与本节全部条款一致。

---

## 10. 生产 Smoke 契约（audit_smoke.py）

本节解决 RFC §15 的 T2-02（Smoke event 精确 schema）。

### 10.1 脚本路径与 CLI

| 属性 | 值 |
|------|-----|
| 脚本路径 | `scripts/unified_data/audit_smoke.py` |
| CLI 参数 | 仅 `--apply`（执行 writer→reader round-trip）；不传时默认 dry-run |
| 退出码 | 0=成功（dry-run/apply）；2=范围校验失败；3=凭证缺失；4=运行时错误 |

### 10.2 两大模式

#### 10.2.1 dry-run（默认，零副作用）

- 执行 `_validate_targets` 和 `_validate_event_fields` 静态校验
- 打印预期执行计划（writer insert → reader find_one）
- 不加载任何环境变量、不创建 MongoDB 连接
- 退出码：0

#### 10.2.2 `--apply`（writer→reader round-trip）

| 步序 | 操作 | 前提 | 失败后果 |
|------|------|------|----------|
| 1 | `_validate_targets` 静态校验 database/collection | 无 | 退出码 2 |
| 2 | 构造最小 smoke event（§10.3） | 1 通过 | — |
| 3 | `_validate_event_fields` 字段校验 | 2 通过 | 退出码 4 |
| 4 | 通过 `YQUANT_UD_AUDIT_WRITER_MONGO_*` 凭证打开 writer client | 3 通过 | 凭证缺失退出码 3；运行时退出码 4 |
| 5 | 通过 `YQUANT_UD_AUDIT_READER_MONGO_*` 凭证打开 reader client | 3 通过 | 同上 |
| 6 | writer: `collection.insert_one(event)` | 4~5 通过 | 退出码 4 |
| 7 | reader: `collection.find_one({"_id": inserted_id})` | 6 通过 | 退出码 4 |
| 8 | 验证 fetched_doc.event_type / source 与插入值一致 | 7 通过 | 退出码 4 |
| 9 | 验证 fetched_doc 的字段严格限于 `ALLOWED_EVENT_FIELDS` | 7 通过 | 退出码 4 |
| 10 | 关闭 writer/reader client | 任意 | 不改变退出码 |

### 10.3 Smoke event 精确 schema（T2-02 解决）

| 字段 | 类型 | 值 | 说明 |
|------|------|-----|------|
| `_id` | ObjectId | 自动生成（由 `insert_one` 返回） | MongoDB 主键 |
| `event_type` | string | `"audit_smoke_round_trip"` | 标识该 event 为 smoke round-trip |
| `source` | string | `"audit_smoke_cli"` | 标识该 event 来源为 smoke CLI |
| `fetched_at` | datetime | UTC `datetime`（含 tzinfo） | 满足 TTL 索引的精确 UTC 时间 |

**字段约束**：
- `fetched_at` 必须是 UTC `datetime` 且含 `tzinfo`（`datetime.now(timezone.utc)`），不得使用 naive datetime
- Event **不得**包含 `params`、`account`、`security_id`、`market`、`capability`、`provider`、`consumer`、`audit_id`、`duration_ms`、`quality_score` 等任何业务字段
- Event **不得**包含任何 secret/token/password/credential 字段
- 插入后 reader 读到 doc 后再次验证字段严格属于 `ALLOWED_EVENT_FIELDS`，不匹配 fail-closed

### 10.4 凭证隔离

| 身份 | 环境变量前缀 | 用途 |
|------|-------------|------|
| Writer | `YQUANT_UD_AUDIT_WRITER_MONGO_*` | 插入 smoke event |
| Reader | `YQUANT_UD_AUDIT_READER_MONGO_*` | 读取 smoke event |

writer 与 reader 凭证严格分离（独立 client、独立变量命名空间），不共享、不交叉引用。DDL bootstrap 身份（`YQUANT_UD_AUDIT_DDL_MONGO_*`）不与 runtime writer/reader 身份混用。

### 10.5 安全约束

- 任何函数不得打印 URI/username/password/token。
- pymongo 触达点（client 打开、insert_one、find_one）的异常一律翻译为 `WriterRuntimeError`/`ReaderRuntimeError`（固定脱敏消息，不串联底层 `str(exc)`）。
- `run_apply` 的兜底 `except Exception` 只输出类型名 + 固定脱敏短语，绝不打 `{exc}`。

---

## 11. 停止条件与金丝雀验收标准

本节将 RFC §8.3a 全文精确化为 SPEC 级别可断言条款，并解决 T2-04（verify/smoke 顺序依赖：DDL→verify→smoke→canary 的严格顺序见 §11.4；verify 失败后修复重跑 `--verify` 见 §9.2.2；smoke 可脱离 verify 独立运行但必须满足 DDL 已完成）。

### 11.1 停止条件（SC-01~05）

Rollout 过程中任一条件触发，立即**暂停** rollout，不可继续下一步：

| 条件 | 触发场景 | 检测方式 | 应对 | 恢复条件 |
|------|---------|----------|------|---------|
| SC-01 DDL 失败 | `audit_rollout.py --apply` 任一步骤失败（退出码非 0） | 脚本退出码 != 0 | 停止 rollout，保留已创建工件（集合/索引/role/user），排查失败原因后重新执行 `--apply` | 修复后 `--apply` 幂等通过 |
| SC-02 Smoke 失败 | `audit_smoke.py --apply` writer insert / reader find_one 失败（退出码非 0） | 脚本退出码 != 0 | 停止 rollout，保留已写入 smoke event；排查 writer/reader 身份权限故障，修复后重新 smoke | writer→reader round-trip 通过 |
| SC-03 QualitySummary 越权 | `--verify` 检测到 `03_data_ud_quality_summary` 集合存在 | verify 退出码 1，问题列表含 "QualitySummary collection ... must NOT exist" | **紧急停止**，报告 Pascal；如非恶意创建则 drop 该集合；排查创建来源 | 集合不存在后恢复 |
| SC-04 身份泄露告警 | 脚本输出/日志中出现 URI、password、token 等敏感字段 | 人工检查或自动化日志扫描 | 紧急停止，立即 rotate 暴露的凭据 | 凭据 rotate 完成，重新从 DDL 开始 |
| SC-05 金丝雀写入失败率 > 5% | 金丝雀期间 AuditLogger 写入失败计数 > 查询量的 5% | AuditLogger 内部失败计数器 / `logger.warning` 出现频率 | 暂停 rollout，排查 MongoDB 写入路径（连接池、权限、网络） | 故障修复，金丝雀重新观察 24h |

### 11.2 金丝雀验收标准（CV-01~05）

Canary 期 24-48h 后必须全部满足方可进入全量 rollout：

| 标准 | 阈值 | 测量方式 |
|------|------|---------|
| CV-01 写入成功率 | ≥ 99.5%（失败 ≤ 0.5% 的 AuditLogger.log() 调用） | AuditLogger 内部失败计数器 / `logger.warning` 出现频率 |
| CV-02 p99 写入延迟 | ≤ 200ms | AuditLogger 内部计时（写入 MongoDB 耗时） |
| CV-03 主查询无阻断 | 0 次因 AuditLogger 异常导致的查询失败 | DataRouter.query() catch 层计数 |
| CV-04 无 QualitySummary 污染 | 0 条 `03_data_ud_quality_summary` 集合文档 | `--verify` 或手动 `db.03_data_ud_quality_summary.estimatedDocumentCount()` |
| CV-05 无越权操作 | 0 次对 `portfolio_*` / `smart_money_*` / `signal_*` / `trade_*` 等集合的 insert | 审计日志 + 操作日志交叉验证 |

### 11.3 QualitySummary 禁止令（QS-F1~F5）

不可争议架构约束，任何违反视为越权：

| 约束 | 说明 | 验证方法 |
|------|------|----------|
| QS-F1 | 任何代码路径、测试、脚本、配置均不得创建 `03_data_ud_quality_summary` 集合或相关索引 | `audit_rollout.py --apply` 防御性检查；`--verify` 显式验证不存在 |
| QS-F2 | `AuditLogger.__init__` 的 `quality_summary` 参数在 Phase 1 始终保持 `None`；不得创建 noop 实例 | 审计 logger 初始化时 quality_summary 参数为 None |
| QS-F3 | `AuditLogger.log()` 内部如果监测到 `self._quality_summary is not None` 则必须抛 `RuntimeError`（防御性断言） | 单元测试验证 QualitySummary 注入场景抛 RuntimeError |
| QS-F4 | `audit_rollout.py --apply` 必须显式检查 `03_data_ud_quality_summary` 不存在（若存在则 fail-fast，退出码 4） | 单元测试 mock 集合存在场景 |
| QS-F5 | `audit_rollout.py --verify` 必须确认 `03_data_ud_quality_summary` 不存在（若存在则退出码 1 验证失败） | 单元测试 verify 路径 |

### 11.4 一次性 smoke / canary 契约

| 步骤 | 执行命令 | 验证 | 通过后 |
|------|---------|------|--------|
| Smoke（一次性） | `audit_smoke.py --apply` | writer insert + reader find_one({_id}) round-trip；event 字段仅含 `_id`/`event_type`/`source`/`fetched_at`；不含业务/secret 字段 | 确认 writer/reader 身份可正常读写 |
| Canary（可选，先于全量 rollout） | 在 1-2 个低流量 capability（如 `metadata.*`）启用 AuditLogger 真实写入 | 满足 CV-01~CV-05 后通过 | 逐步开放到全部 capability |

---

## 12. QualitySummary 不可达性测试与静态扫描

### 12.1 测试要求

所有 `03_data_ud_quality_summary` 相关的创建/写入/读取操作在 Phase 1 必须被显式验证为不可达（unreachable）。

| # | 测试 | 范围 | 验证点 |
|---|------|------|--------|
| US-1 | AuditLogger 初始化时 quality_summary 参数始终为 None | `test_audit_logger.py` | `AuditLogger.__init__` 被调用时 `quality_summary` 参数为 None；验证 `_quality_summary is None` 为 True |
| US-2 | AuditLogger.log() 不触发 QualitySummary.update() | `test_audit_logger.py` | mock QualitySummary 实例注入 `AuditLogger` 后，`log()` 调用应抛 `RuntimeError`（QS-F3 防御性断言） |
| US-3 | QualitySummary.update() 未被异常触发 | `test_router_quality.py` | Router 含 AuditLogger 且无 QualitySummary 注入时，`query()` 调用 audit logger 不会触发任何 QS update |
| US-4 | audit_rollout --apply 拒绝 QS 集合存在 | `test_audit_rollout.py` | mock 集合已存在场景，`run_apply()` 退出码 4，打印消息含 "QualitySummary" |
| US-5 | audit_rollout --verify 检查 QS 集合不存在 | `test_audit_rollout.py` | mock 集合不存在场景→退出码 0（通过）；mock 已存在→退出码 1（失败） |
| US-6 | audit_smoke FORBIDDEN_COLLECTIONS 含 QualitySummary | `test_audit_smoke.py` | `FORBIDDEN_COLLECTIONS` 含 `"03_data_ud_quality_summary"`；`_validate_targets` 在 target==QS 时抛 `ScopeViolation` |
| US-7 | 代码搜索审计：任何文件不含 `03_data_ud_quality_summary` 的 create 或 write 代码 | static scan | grep 或 codeql 确认：排除注释/文档后，生产代码无 `03_data_ud_quality_summary` insert/update/upsert/createCollection/createIndex 调用 |

### 12.2 静态扫描要求

| # | 扫描项 | 扫描范围 | 通过条件 |
|---|--------|----------|----------|
| SCAN-1 | 生产代码中 `03_data_ud_quality_summary` 字符串出现次数 | `skills/data/unified_data/` 下的 `.py` 文件（不含 tests/） | 仅 QualitySummary schema 定义（`quality/summary.py`）和 QS 禁止令注释中出现；无 create/insert/update/upsert 调用 |
| SCAN-2 | `createIndex` 或 `create_collection` 在 `03_data_ud_quality_summary` 上的调用 | 全项目 Python 文件 | 0 处 |
| SCAN-3 | `portfolio_*`/`smart_money_*`/`signal_*`/`trade_*`/`cache_*` 在 audit_rollout.py 和 audit_smoke.py 中作为目标出现 | `scripts/unified_data/` 下的 `.py` 文件 | 仅出现在 `FORBIDDEN_COLLECTIONS`/`ALLOWED_IDENTITY_NAMES` 常量或拒绝逻辑中，不出现为可写目标 |

### 12.3 测试运行命令

```bash
# QualitySummary 不可达性测试
PYTHONPATH=. pytest skills/data/unified_data/tests/test_audit_logger.py \
  skills/data/unified_data/tests/test_router_quality.py \
  -k "quality_summary" -v --tb=short

# 静态扫描
grep -rn '03_data_ud_quality_summary' skills/data/unified_data/ --include='*.py' \
  | grep -v 'test_' | grep -v '__pycache__' | grep -v '\.pyc'

# DDL 工具单元测试
PYTHONPATH=. pytest tests/ -k "audit_rollout or audit_smoke" -v --tb=short
```

---

## 13. Production Gate

### 13.1 Phase 1 范围与 Pascal 确认后的行为（已授权未执行）

| 组件 | Phase 1（Audit-only，已授权未执行） | Pascal 确认后（未来 Phase） |
|------|----------------------|----------------------------|
| AuditLogger | `mongo_db=None`（noop 模式），或显式注入 mongomock。Pascal 已授权 DDL+smoke 并有权启用真实写入（但**尚未执行**，须经 Implement→Verify→Review 流水线后按 rollout 策略分步执行） | `mongo_db` 指向生产 `tradingagents` 库 |
| QualitySummary | **全程禁用**。`AuditLogger.__init__` 的 `quality_summary` 参数保持 `None`。不创建 noop 实例。 | `mongo_db` 指向生产库 |
| 集合/索引创建 | Pascal 已授权但**尚未执行**。DDL 通过 `audit_rollout.py --apply` 幂等执行，最终由独立 activation 卡执行 | 同上 |
| 真实 Smoke | Pascal 已授权但**尚未执行**。通过 `audit_smoke.py --apply` 一次性执行（§10） | Pascal 确认后可选 |
| quality tier 业务影响 | **仅观测**：quality tier 不构成业务门禁，不阻断查询路径 | 待未来 Phase 决策 |

### 13.2 Implement 代码约束

所有 Phase 2 新增代码必须经过以下约束验证：

1. `AuditLogger.__init__` / `QualitySummary.__init__` 中 `mongo_db=None` 时必须安全地初始化为 noop，不能假创建连接。
2. `log()` / `update()` 在 noop 模式下不抛异常、不写日志。
3. 所有测试使用 mongomock，不依赖真实 MongoDB。
4. 测试中不创建真实 MongoDB 集合或索引。
5. 实现在 `production_gate` 或等价标志位阻止真实写入。

---

## 14. 兼容性影响扫描

### 14.1 对已有消费者的影响

| 消费者 | 影响 | 向后兼容 |
|--------|------|----------|
| 读取 DataResult.quality_score | 原为 None，现变为 float | 兼容（None 和 float 均可处理） |
| 读取 DataResult.warnings | 原为 []，现可能包含质量告警 | 兼容（list 结构不变） |
| DataRouter.query() 返回值 | 签名不变，返回值字段增强 | 兼容 |
| ProviderRegistry.get_providers() | 新参数 state_filter 有默认值 | 兼容（不传参数 = 原有行为） |
| ProviderRegistry 的其他方法 | 无变化 | 兼容 |

### 14.2 对测试的影响

| 测试 | 影响 | 兼容策略 |
|------|------|----------|
| Phase 0/1A/1B 已有 269 测试 | quality_scorer=None, audit_logger=None | 完全不影响 |
| 已有 router 测试 | quality_score=None 变为 | 现有断言检查 None 不受影响 |
| 已有 registry 测试 | 不调用新增方法 | 不受影响 |

---

## 15. 实现文件与测试目录清单（精确路径）

### 15.1 新增文件

| 文件 | 说明 |
|------|------|
| `skills/data/unified_data/quality/__init__.py` | quality 子包导出 |
| `skills/data/unified_data/quality/scorer.py` | QualityScorer 实现 |
| `skills/data/unified_data/quality/config.py` | QualityScorerConfig |
| `skills/data/unified_data/audit/__init__.py` | audit 子包导出 |
| `skills/data/unified_data/audit/logger.py` | AuditLogger 实现 |
| `skills/data/unified_data/quality/summary.py` | QualitySummary 实现（放在 quality/ 下而非 audit/ 下） |
| `skills/data/unified_data/tests/test_quality_scorer.py` | QualityScorer 单元测试 |
| `skills/data/unified_data/tests/test_quality_config.py` | QualityScorerConfig 测试 |
| `skills/data/unified_data/tests/test_audit_logger.py` | AuditLogger 测试 |
| `skills/data/unified_data/tests/test_quality_summary.py` | QualitySummary 测试 |
| `skills/data/unified_data/tests/test_registry_governance.py` | Registry 治理测试 |
| `skills/data/unified_data/tests/test_router_quality.py` | Router 质量填充端到端测试 |
| `skills/data/unified_data/tests/fixtures/quality_fixtures.py` | 质量测试 fixture（各种评分配置 fixture） |

### 15.2 修改文件

| 文件 | 修改类型 |
|------|----------|
| `skills/data/unified_data/__init__.py` | 新增导出 QualityScorer、ScoredResult、QualityScorerConfig、AuditLogger、QualitySummary |
| `skills/data/unified_data/registry.py` | 新增 priority/health_state 方法 |
| `skills/data/unified_data/router.py` | 构造函数新增 quality_scorer/audit_logger 参数 + query() 尾部评分+审计调用 |
| `skills/data/unified_data/tests/conftest.py` | 可选新增 quality_score fixture |

---

## 16. 无副作用测试与生产 Smoke 的分界

### 16.1 无副作用测试（全部测试均在此范畴）

运行 `PYTHONPATH=. pytest skills/data/unified_data/tests/ -m "not production_gate" -v`

- 全部使用 mongomock
- 全部使用 FakeProvider/FakeTA_CNAdapter
- 不连接真实 MongoDB
- 不调用真实外部 API
- 不创建 MongoDB 集合或索引

### 16.2 生产 Smoke（仅 Pascal 确认后可运行）

通过 `scripts/unified_data/audit_smoke.py --apply` 独立执行（见 §10），而非通过 pytest 触发。

- 需要真实 MongoDB 连接（通过 `YQUANT_UD_AUDIT_WRITER_MONGO_*` / `YQUANT_UD_AUDIT_READER_MONGO_*` 环境变量）
- 读写对象仅限 `tradingagents.03_data_ud_query_audit` 集合
- 使用 `@pytest.mark.production_gate` 标记的测试仅用于单元测试中的 smoke 模块模拟验证

### 16.3 验收命令

```bash
# 快速验证（无质量/审计）
PYTHONPATH=. pytest skills/data/unified_data/tests/ -m "not production_gate" -q --tb=short

# 质量相关全量
PYTHONPATH=. pytest skills/data/unified_data/tests/test_quality_scorer.py skills/data/unified_data/tests/test_quality_config.py skills/data/unified_data/tests/test_registry_governance.py skills/data/unified_data/tests/test_router_quality.py -q --tb=short

# 审计相关全量
PYTHONPATH=. pytest skills/data/unified_data/tests/test_audit_logger.py skills/data/unified_data/tests/test_quality_summary.py -q --tb=short
```

---

## 17. 验收标准

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

9. **DDL 工具（audit_rollout.py）**：
   - dry-run 退出码 0，零副作用
   - `--verify` 退出码 0/1/2/3/4 符合 §9.2.2
   - `--apply` 退出码 0/2/3/4 符合 §9.2.3
   - all static allow-list constants match §9.4
   - `--apply` 幂等：第二次执行输出含 `skipped=[...]` 无故障退出码 0
   - ALLOWED_PARAMS = 11 键（§9.3），初始化后不可变，模块级常量
   - Reader user 在 Phase 1 DDL 中创建（§9.5）
   - QualitySummary 集合存在时 `--apply` 退出码 4 fail-fast
   - QualitySummary 集合存在时 `--verify` 退出码 1
   - `--apply` 使用独立 DDL bootstrap 身份，不混用 runtime 身份

10. **Smoke 工具（audit_smoke.py）**：
    - dry-run 退出码 0，零副作用
    - `--apply` 退出码 0/2/3/4 符合 §10.2
    - smoke event 精确 schema 符合 §10.3
    - writer/reader 凭证严格隔离（§10.4）
    - 安全约束：异常消息不含 URI/password/token（§10.5）

11. **停止条件与金丝雀**：
    - SC-01~05 触发行为可断言（§11.1）
    - CV-01~05 验收阈值可测量（§11.2）
    - QS-F1~F5 禁止令代码已验证（§11.3）

12. **QualitySummary 不可达性**：
    - US-1~US-7 共 7 项测试全部通过（§12.1）
    - SCAN-1~3 静态扫描全部通过（§12.2）

---

## 18. 参考资料

- `docs/rfc/03_data/RFC-03-011-unified-data-phase-2-quality-audit-governance.md`（本 SPEC 来源 RFC）
- `docs/spec/03_data/SPEC-03-007-unified-data-layer.md` — 基础契约
- `docs/spec/03_data/SPEC-03-009-unified-data-phase-1b-persistence-plane.md` — Phase 1B-B 契约
- `docs/design/03_data/DESIGN-03-007-unified-data-layer.md` — 详细设计
- `skills/data/unified_data/` — 现有代码基
- `skills/data/unified_data/models/__init__.py` — DataResult、SecurityId
- `skills/data/unified_data/registry.py` — 现有 ProviderRegistry
- `skills/data/unified_data/router.py` — 现有 DataRouter
