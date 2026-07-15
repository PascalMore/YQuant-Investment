# RFC-03-011：Unified Data Phase 2 — 数据质量评估、审计与运行治理

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-15 |
| 最后更新 | 2026-07-15 |
| 版本号 | V0.1 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-008（Phase 1B-A 查询平面）、RFC-03-009（Phase 1B-B 持久化缓存平面） |
| 依赖 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-009（Phase 1B-B 持久化缓存平面） |
| 依赖 Design | DESIGN-03-007（Unified Data Layer 详细设计） |
| 替代 RFC | 无 |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #quality #audit #governance #phase2 |

---

## 1. 执行摘要

Phase 0/1A/1B 构建了 Unified Data Layer 的核心骨架（SecurityId、DataResult、DataProvider、ProviderRegistry、DataRouter）、TA-CN 只读适配器（8 只读集合 + 14 域入口方法）、外部 Provider（Tushare/AKShare）、以及持久化缓存平面（LocalMongoAdapter、CacheManager、物化与缓存集合）。至此，系统基本具备「获取数据」的能力。

但缺失以下关键治理能力：

- **数据质量不可见**：消费方无法知道返回的数据是实时可信的，还是过期的、不完整的、来自低可靠性源的。
- **数据来源不可审计**：无法追溯「哪个 query 走了哪个 provider 链」「耗时多少」「质量评分如何」。
- **Provider Registry 无运行态治理**：没有健康状态、优先级、动态跳过/降级的运行机制。
- **消费方无质量感知语义**：不知道应当「直接使用」「告警使用」「降级使用」还是「拒绝使用」。

Phase 2 在现有 Unified Data Layer 骨架之上，增加 **QualityScorer**（数据质量评估）、**AuditLogger**（查询审计）、**QualitySummary**（质量汇总 metadata）和 **Registry 运行治理**，补齐数据可信度与可观测性缺口。

---

## 2. 背景与动机

### 2.1 现状问题

| 问题 | 影响 | 举例 |
|------|------|------|
| 无数据质量评分 | 消费方无法区分正常数据与过期/缺失/冲突数据 | 返回的 `DailyBar` 可能是 3 天前的过期数据，但没有 `quality_score` 字段指示 |
| 无查询审计 | 无法追踪谁、在何时、通过什么 provider 链查了什么数据 | 排查「为什么昨天的回测和今天的结果不同」时缺乏 provider 路径记录 |
| Registry 无运行态治理 | provider 的重启/不可用/优先级变更需要代码改部署 | 某 provider token 耗尽，无法动态标记为不可用 |
| 质量感知语义缺失 | 消费方只能自己猜数据是否可用 | 客户端不知道 `freshness="delayed"` 是该直接使用还是需要等刷新 |

### 2.2 现有基础

DataResult 已有 `quality_score: float | None = None` 占位字段（Phase 0），但从未被赋值。source_trace 已有字符串列表，但缺乏结构化元数据。这些 Phase 0 的保留字段现在有了真正的消费者：

- `quality_score`：由 QualityScorer 填充
- `source_trace`：在现有基础上增加质量相关 trace 条目
- `warnings`：由质量阈值触发告警语义

### 2.3 业务价值

1. **数据可信度可见**：每个 DataResult 携带 `quality_score`，消费方按分决策。
2. **来源可追溯**：完整的 query audit 路径，支持排查与合规。
3. **运行态治理**：Provider Registry 支持运行时状态变更（健康/不健康/优先级调整），无需重启。
4. **质量驱动决策**：消费方可按 `direct use / warning / degrade / reject` 语义做数据质量路由。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] **QualityScorer** 组件：评估 DataResult 的数据可信度/可用性，输出 `[0, 1]` 评分。至少覆盖完整性（completeness）、时效性（freshness）、来源冲突/一致性（source conflict/consistency）、异常/合理性（anomaly/plausibility）四个维度。
- [ ] **质量等级语义**：定义 `direct use / warning / degrade / reject` 四级语义与下游行为指引。
- [ ] **AuditLogger** 组件：每次 Router query 写入审计日志（append-only），至少包含 security_id、capability、time、provider_chain、duration、quality_score、consumer。
- [ ] **QualitySummary** 组件：按 `(domain, security_id, date)` 聚合质量汇总，支持快速查询「某标的某域最近质量」。
- [ ] **Registry 运行治理**：在现有 `ProviderRegistry` 基础上增加 `priority` 排序、`health_state` 运行时状态（healthy/unhealthy/disabled）、按 capability+market+state 的筛选治理。
- [ ] **DataRouter query 返回增强**：所有 `query()` 出口的 DataResult 携带 QualityScorer 填充后的 `quality_score`、增强后的 `warnings`、完整的 `source_trace` 结构化 trace。
- [ ] **生产 MongoDB 写入守卫**：真实 audit/quality_summary 集合创建、审计写入、质量汇总写入、真实 provider smoke 均须在 Phase 2 Design 完成后由 Orchestrator 向 Pascal 单独陈述副作用矩阵并取得明确确认。确认前实现仅使用 fake/mongomock/fixture/no-op 或显式禁用的写入后端。

### 3.2 非目标（Non-Goals，明确不做）

- **不评估股票或投资标的的质量**：QualityScorer 只评估「数据本身的可信度/可用性」，不评估投资价值。
- **不创建 Sector Router capability**：Sector 路由不属于 Phase 2 范围。
- **不做 Registry 持久化**：ProviderRegistry 保持纯内存，不持久化到 MongoDB。
- **不做后台调度/自动刷新**：质量汇总的周期性计算、过期 provider 的自动健康检查均属 Phase 3+。
- **不做 task_center 集成**：Phase 5 范围。
- **不做 stock framework 集成**：Phase 6 范围。
- **不做缓存质量评分写入**：质量评分为实时计算值，不持久化到缓存层（QualitySummary 除外）。
- **不改动已有公共契约**：不修改 SecurityId、DataResult、Market、DataProvider、FreshnessPolicy 等 Phase 0/1A/1B 的公开 API 签名，但 DataResult.quality_score 从占位变为实际填充。

### 3.3 成功标准

1. QualityScorer 接受 DataResult + context 参数，返回 `[0, 1]` 评分和每个维度的子分。
2. AuditLogger 记录每次 Router query，包含完整字段。
3. QualitySummary 写入可按 `(domain, security_id)` 查询最近质量。
4. ProviderRegistry 支持运行时修改 provider 的 health_state 和 priority。
5. DataRouter.query() 返回的 DataResult 始终包含 quality_score（error/empty 结果也可能有质量分）。
6. 所有 MongoDB 写入操作有 production gate（Design 阶段 Pascal 确认前仅使用 fake/mongomock）。

---

## 4. 范围

### 4.1 In Scope

| 组件 | 说明 |
|------|------|
| QualityScorer | 数据质量评估组件，计算 `quality_score [0, 1]` + 子维度分数 + quality label |
| QualityScorer 配置 | 维度权重、阈值、硬失败/封顶规则；按域可配置 |
| 质量等级语义 | `direct use / warning / degrade / reject` 四级 |
| AuditLogger | 追加式审计日志写入，记录每次 Router query 的完整路径 |
| QualitySummary | 按 `(domain, security_id, date)` 聚合的质量汇总，支持写入与查询 |
| Registry 运行治理 | priority 排序、health_state（healthy/unhealthy/disabled）、按状态筛选 |
| DataResult 质量填充 | Router query 出口统一走 QualityScorer 评分 |
| production gate | Design 完成后需 Pascal 确认的副作用矩阵（集合创建、索引创建、真实写入） |
| 文档集合规划 | `03_data_ud_query_audit`（append-only，含 TTL）、`03_data_ud_quality_summary`（upsert） |

### 4.2 Out of Scope（不做或者 Phase 3+）

| 项目 | 归属 |
|------|------|
| Sector Router capability | Phase 2 不涉及 |
| Registry 持久化到 MongoDB | 保持纯内存 |
| 后台质量汇总周期性计算 | Phase 3+ |
| 自动 provider 健康检查/熔断 | Phase 3+ |
| QualityScorer 的 ML 模型驱动评分 | Phase 3+ |
| task_center 集成 | Phase 5 |
| stock framework 集成 | Phase 6 |
| DSA SQLite adapter | 不实现 |
| TA-CN 集合回写 | 禁止 |

---

## 5. 术语

| 术语 | 定义 |
|------|------|
| QualityScore | 浮点数 `[0, 1]`，表示数据可信度/可用性。1=完全可信，0=完全不可信 |
| 质量维度（Quality Dimension） | QualityScore 的子成分：完整性、时效性、来源一致性、异常/合理性 |
| 硬失败（Hard Fail） | 某维度得分低于硬阈值时 quality_score 直接为 0（不叠加其他维度分） |
| 封顶（Capping） | 某维度得分高于阈值但不影响总分（用于「源冲突但数据可用」场景） |
| 质量等级（Quality Tier） | 从 quality_score 派生的下游语义：direct use / warning / degrade / reject |
| Audit Event | 每次 Router query 的结构化日志记录 |
| Quality Summary | 按 domain/security/date 聚合的质量汇总快照 |
| Health State | Provider 运行时状态：healthy / unhealthy / disabled |
| Priority | Provider 在同一 capability 链中的排序优先级（数值越小越优先） |

---

## 6. 整体方案

### 6.1 组件架构

```
┌───────────────────────────────────────────────────────────┐
│                      DataRouter.query()                        │
│   (4-step internal-first: TA-CN → 物化 → Cache → 外部)        │
└──────────────────────┬────────────────────────────────────────┘
                       │ DataResult (裸，无 quality_score)
                       ▼
┌──────────────────────────────────────────────┐
│              QualityScorer                    │
│  ┌──────────┬──────────┬──────────┬────────┐ │
│  │ 完整性   │ 时效性   │ 一致性   │ 合理性 │ │
│  └──────────┴──────────┴──────────┴────────┘ │
│  → quality_score [0,1] + 维度子分 + 等级      │
└───────────────────┬─────────────────────────┘
                     │ 增强后的 DataResult (quality_score + warnings)
                     ▼
┌──────────────────────────────────────────────┐
│              AuditLogger                       │
│  → append-only to 03_data_ud_query_audit      │
└──────────────────────────────────────────────┘
                     │ (异步 catch-and-log)
                     ▼
┌──────────────────────────────────────────────┐
│              QualitySummary                    │
│  → upsert to 03_data_ud_quality_summary       │
└──────────────────────────────────────────────┘
```

### 6.2 Registry 运行治理

```
ProviderRegistry (Phase 0/1B-A)

增强项：
  - _priorities: dict[str, int]         # provider_name → priority (default: 100)
  - _health_states: dict[str, str]       # provider_name → "healthy" | "unhealthy" | "disabled"

增长的方法：
  - set_priority(name, priority)         # 运行时调整优先级
  - set_health(name, state)              # 运行时健康状态
  - get_providers(capability, market, state_filter=None)  # 可筛选健康状态

Router 中的使用：
  - Step 4 fallback 链：按 priority 排序 + 过滤 unhealthy/disabled
  - forced-provider 分支：检查 health_state，unhealthy/disabled 返回 error
```

### 6.3 分阶段确认点

Phase 2 涉及生产 MongoDB 写入（audit/quality_summary），必须分两步确认：

**设计阶段（本 RFC/SPEC 产出后）**：
1. Orchestrator 准备生产副作用矩阵（集合名、字段、索引、TTL、写入频率、容量估算、隐私边界）。
2. Pascal 确认以下内容后方可进入 Implement：
   - 集合命名和 schema
   - 索引策略和 TTL 周期
   - 写入失败降级策略
   - 回滚方案
   - 隐私/安全边界

**实现阶段**：
- Pascal 确认前：使用 fake/mongomock/fixture/no-op 写入后端
- Pascal 确认后：进入真实 MongoDB 写入 + 部署

---

## 7. 详细方案

### 7.1 QualityScorer

#### 7.1.1 评分范围

`quality_score: float`，值域 `[0, 1]`。1.0 表示完全可信，0.0 表示完全不可信。

#### 7.1.2 质量维度

至少包含四个维度，每个维度输出子分 `[0, 1]`。总分 = 加权平均（可配置），但硬失败直接归零：

| 维度 | 评估内容 | 输入信号 | 硬失败条件示例 |
|------|----------|----------|---------------|
| 完整性（completeness） | 数据是否包含必要字段，payload 是否为空 | `DataResult.is_empty()`, 必要字段 null 率 | payload 完全为空 |
| 时效性（freshness） | 数据是否在合理时效范围内 | `fetched_at`, `data_date`, `freshness` label | freshness="stale" 或 `age > 2×TTL` |
| 来源一致性（consistency） | 多源数据是否有冲突（质量汇总阶段需要） | `source_trace` 中的冲突标记 | 同一字段来自两个源且值差异 > 阈值 |
| 异常/合理性（plausibility） | 数据值是否在正常范围内 | 字段值 vs 域期望范围 | 收盘价 < 0 |

> **维度具体实现方式（如权重分配、阈值计算公式）属于 Design 范围**，本 RFC 仅定义维度的存在和可配置要求。公式和默认值将在 SPEC §6 中精确给出或声明待定。

#### 7.1.3 质量等级

| 等级 | quality_score 范围 | 下游行为 |
|------|-------------------|----------|
| direct use | ≥ 0.9 | 数据可直接用于投资决策、回测、报表 |
| warning | [0.7, 0.9) | 数据可用，但建议标注「可能需要确认」 |
| degrade | [0.3, 0.7) | 数据可用性受限，降级使用（如仅用于参考，不用于计算仓位） |
| reject | < 0.3 | 数据不可用，应拒绝使用（与 DataResult.error 等价） |

**等级阈值必须可配置（按域可覆盖）**，具体默认值在 SPEC 中定义。

#### 7.1.4 配置

QualityScorer 必须支持：
- 按 domain 配置维度权重（如 `market_data` 域时效性权重更高，`metadata` 域完整性权重更高）
- 按 domain 配置硬失败阈值（如 `market_data` 域 `age > 2×TTL` 硬失败，`news` 域 `age > 24h` 硬失败）
- 按 domain 配置等级阈值覆盖
- 所有配置具有合理默认值，不可配置时使用默认

### 7.2 Registry 运行治理

#### 7.2.1 优先级（Priority）

- 每个 provider 在注册时获得默认优先级 `100`（数值越小越优先）。
- 运行时通过 `set_priority(name, priority)` 调整。
- `get_providers(capability, market)` 时按 priority 升序返回。
- Step 4 外部 Provider 链的解析顺序：`external_fallback_chains[capability]` → `config.fallback_for(capability)` → registry priority 排序。

#### 7.2.2 健康状态（Health State）

- 三个枚举值：`healthy`（默认）、`unhealthy`（provider 不可用，但仍保留注册）、`disabled`（显式禁用，跳过所有检查）。
- 运行时通过 `set_health(name, state)` 切换。
- Router Step 4 检查：`healthy` 才进入 `is_available()` 判断；`unhealthy` 时在 `source_trace` 记录 `{provider_name}(health: unhealthy)` 并跳过；`disabled` 时记录 `{provider_name}(health: disabled)` 并跳过。
- forced-provider 分支：pinned provider 为 `unhealthy`/`disabled` 时返回 `DataResult.error`（不尝试 fallback）。

### 7.3 AuditLogger

#### 7.3.1 审计事件定义

每次 DataRouter.query() 完成时产生一条审计事件。字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `audit_id` | string | UUID，全局唯一 |
| `security_id` | string | SecurityId.canonical |
| `market` | string | 市场代码 |
| `capability` | string | domain.operation |
| `consumer` | string | 调用方标识（来自 UnifiedDataConfig.consumer） |
| `fetched_at` | datetime | 查询开始时间 |
| `duration_ms` | int | 查询总耗时（毫秒） |
| `provider` | string | 最终返回的 provider（"ta_cn_internal"/"tushare"/"error" 等） |
| `source_trace` | list[str] | 完整 provider 链 |
| `freshness` | string | 最终 freshness label |
| `quality_score` | float | QualityScorer 输出评分 |
| `quality_tier` | string | quality_tier 等级（direct use / warning / degrade / reject） |
| `success` | bool | 是否成功获取数据（succeeded 属性） |
| `error_message` | string\|null | 当 provider="error" 时记录错误信息 |
| `params` | dict | 查询参数（不含敏感字段，如凭据） |

#### 7.3.2 存储

- 集合名：`tradingagents.03_data_ud_query_audit`
- 模式：append-only（不 update、不 delete、仅 insert）
- TTL：90 天（按 `fetched_at` 自动过期）
- 索引：`fetched_at`（TTL 索引）、`(security_id, fetched_at)` 复合索引、`(capability, fetched_at)` 复合索引

TTL 具体值（90 天）在 Design 阶段由 Pascal 确认。

#### 7.3.3 写入策略

- **同步**：每次 DataRouter.query() 返回后同步写入（catch-and-log）。写入失败不影响 query 返回值。
- **采样**：不采样——每次 query 都记录（Phase 2 基础要求）。批量/采样策略属于 Phase 3+
- **去重**：不要求审计事件严格去重（append-only 自然重复）。幂等性不在此阶段要求。

### 7.4 QualitySummary

#### 7.4.1 聚合定义

按 `(domain, security_id, date)` 聚合的质量汇总快照。

| 字段 | 类型 | 说明 |
|------|------|------|
| `_id` | string | `{domain}:{security_id}:{date}` 复合键 |
| `domain` | string | 域 |
| `security_id` | string | SecurityId.canonical |
| `date` | string | YYYY-MM-DD |
| `query_count` | int | 当日查询次数 |
| `avg_quality_score` | float | 当日平均质量评分 |
| `min_quality_score` | float | 当日最低质量评分 |
| `max_quality_score` | float | 当日最高质量评分 |
| `provider_distribution` | dict | 各 provider 命中的次数分布 |
| `last_updated` | datetime | 最后更新时间 |

#### 7.4.2 存储

- 集合名：`tradingagents.03_data_ud_quality_summary`
- 模式：upsert（按 `(domain, security_id, date)` 复合键 upsert）
- TTL：不设集合级 TTL（保留历史，无自动过期）
- 索引：`(domain, security_id, date)` 唯一复合索引

#### 7.4.3 写入策略

- 每次 AuditLogger 写入后触发 upsert（catch-and-log）。
- 写入失败不影响 query 返回值。

---

## 8. 生产 MongoDB 副作用矩阵与确认流程

### 8.1 新增集合

| 集合 | 操作 | DDL（集合/索引创建） | DML（写入） |
|------|------|---------------------|------------|
| `03_data_ud_query_audit` | insert（append-only） | Design 阶段 Pascal 确认 | Design 阶段 Pascal 确认写后端 |
| `03_data_ud_quality_summary` | upsert | Design 阶段 Pascal 确认 | Design 阶段 Pascal 确认写后端 |

### 8.2 确认流程

```
RFC/SPEC 批准
    ↓
T2 Design 阶段：Principal 准备生产副作用矩阵
（集合名、字段、索引、TTL、写入频率、容量估算、隐私边界、回滚方案）
    ↓
Orchestrator 向 Pascal 陈述副作用矩阵
    ↓
Pascal 确认 （Yes/No/修正）
    ↓ Yes → T3 Implement（真实 MongoDB 写入路径可用）
    ↓ No/修正 → Design 调整后重述
    ↓
实现阶段：
  - Pascal 确认前：fake / mongomock / no-op / 显式禁用的写后端
  - Pascal 确认后：真实 MongoDB 写入 + 索引创建（通过 MigrationScript 或 rollback-safe 部署）
```

### 8.3 Implement 阶段默认行为（Pascal 确认前）

- `AuditLogger`：默认使用 `noop` 后端（不写入任何 MongoDB），可选注入 `mongomock` 后端用于测试。
- `QualitySummary`：默认使用 `noop` 后端。
- 所有测试使用 `mongomock`，不依赖真实 MongoDB。
- 所有实现代码在生产路径上有 `is_mongo_configured` 守卫（或等价机制），确保无 MongoDB 时静默降级为 no-op。

---

## 9. 对现有组件的影响

| 组件 | 影响 | 向后兼容 |
|------|------|----------|
| DataResult | quality_score 从 `None` 变为实际值 | 兼容—消费者读取 None 或 float 均可 |
| DataRouter.query() | 返回前经过 QualityScorer，输出 audit | 兼容—签名不变，返回值字段含义增强 |
| ProviderRegistry | 新增 priority/health_state 方法 | 兼容—新增方法，已有注册不受影响 |
| FreshnessPolicy | 无影响 | 兼容 |
| LocalMongoAdapter | 无影响 | 兼容 |
| CacheManager | 无影响 | 兼容 |
| Test fixtures | 需补充 quality 相关 fixture | 不影响已有测试 |
| 消费者拦截器（未实现） | Phase 2 不实施拦截器模式 | — |

---

## 10. 风险

| 风险 | 概率 | 影响 | 应对 | 降级策略 |
|------|------|------|------|----------|
| QualityScorer 维度评分主观性强 | 中 | 中 | 所有权重/阈值默认值可配置，Design 阶段声明为「待 Pascal 确认」 | 默认使用保守无偏权重 |
| AuditLogger 写入成为性能瓶颈 | 低 | 高 | catch-and-log 确保不阻断查询；Design 阶段做写入延迟基准测试 | 增加采样率或异步写入（Phase 3+） |
| MongoDB 集合创建未经确认 | 低 | 高 | Production Gate 确保 Pascal 确认前零 DDL | 始终使用 noop 后端 |
| QualitySummary 写入频率过高 | 中 | 低 | 按 query 每次写入（upsert），写入在 catch-and-log 保护下 | 降低写入频率到每 N 次或定期批处理 |
| Registry 运行时变更导致不一致 | 低 | 中 | priority/health_state 是瞬态状态，不持久化，重启后恢复注册时默认 | 无持久化意味着重启即恢复，无需回滚 |

---

## 11. 回滚

1. AuditLogger noop 后端：关闭真实写入，审计日志丢失前进窗口内的记录。
2. QualitySummary noop 后端：关闭质量汇总写入，质量汇总查询返回空。
3. QualityScorer 评估：可独立关闭（quality_score 恢复为 None），不影响 DataRouter 核心路径。
4. Registry 治理增强：`set_health`/`set_priority` 可回滚到默认状态。不上持久化，无脏数据残留。
5. 整个 Phase 2 组件与 Phase 0/1A/1B 零耦合，删除 `quality/`、`audit/` 等新增目录可完全回滚。

---

## 12. 可观测性

| 维度 | 指标 | 手段 |
|------|------|------|
| 质量 | quality_score 分布（按域、按 provider） | AuditLogger 中 quality_score 字段 + QualitySummary 聚合 |
| 审计 | 查询次数、平均耗时、错误率 | AuditLogger + 聚合查询 |
| Provider 健康 | health_state 变更事件 | Registry.health_state 读取 + 日志 |
| 写入失败 | AuditLogger/QualitySummary 写入失败计数 | logger.warning + 计数器 |

---

## 13. 验收标准

1. **文档存在**：
   - `docs/rfc/03_data/RFC-03-011-unified-data-phase-2-quality-audit-governance.md` ✓（本文件）
   - `docs/spec/03_data/SPEC-03-011-unified-data-phase-2-quality-audit-governance.md` 存在

2. **覆盖已确认决策**：
   - QualityScorer 评估数据可信度，不评估投资标的 → §3.2 / §5
   - 评分 `[0, 1]`，至少 4 维度 → §7.1.2
   - concrete use / warning / degrade / reject 等级 → §7.1.3
   - source_trace / query audit / quality metadata 公开契约 → §7.3 / §7.4
   - MongoDB-first；SQLite 不参与 → §4.1 / §8.1
   - 集合命名空间 `03_data_ud_query_audit` / `03_data_ud_quality_summary` → §7.3.2 / §7.4.2
   - Production Gate → §8.2
   - Sector Router 不属于 Phase 2 → §3.2

3. **文档可被下一阶段 Design 无歧义拆解**：
   - QualityScorer 的维度、配置接口、评分流程已定义 → §7.1
   - Registry 的 priority/health_state 方法已定义 → §7.2
   - AuditLogger schema 和写入策略已定义 → §7.3
   - QualitySummary schema 和写入策略已定义 → §7.4
   - Production Gate 流程已定义 → §8.2

4. **明确写出由 Design 固化的边界**：
   - 评分公式/权重 → SPEC §6 中声明默认值或待定
   - TTL 具体值（90 天）→ §7.3.2 声明待 Pascal 确认
   - 索引策略细节 → SPEC §7 给出候选索引

5. **明确禁止在 Pascal 确认生产副作用前创建集合/索引/真实写入** → §8.3

---

## 14. 参考资料

- `docs/rfc/03_data/RFC-03-007-unified-data-layer.md` — Unified Data Layer 总纲
- `docs/spec/03_data/SPEC-03-007-unified-data-layer.md` — Unified Data Layer 契约
- `docs/design/03_data/DESIGN-03-007-unified-data-layer.md` — Unified Data Layer 详细设计
- `docs/spec/03_data/SPEC-03-009-unified-data-phase-1b-persistence-plane.md` — Phase 1B-B 持久化缓存平面契约
- `skills/data/unified_data/` — 现有代码基
- `tests/data/unified_data/` — 现有测试基
