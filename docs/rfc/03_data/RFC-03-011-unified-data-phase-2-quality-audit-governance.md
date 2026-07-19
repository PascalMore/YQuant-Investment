# RFC-03-011：Unified Data Phase 2 — 数据质量评估、审计与运行治理

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Pascal 已授权受控 rollout、尚未执行（Authorized for Controlled Rollout, Not Yet Executed） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-15 |
| 最后更新 | 2026-07-19 |
| 版本号 | V1.0 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-008（Phase 1B-A 查询平面）、RFC-03-009（Phase 1B-B 持久化缓存平面） |
| 依赖 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-009（Phase 1B-B 持久化缓存平面） |
| 依赖 Design | DESIGN-03-007（Unified Data Layer 详细设计） |
| 替代 RFC | 无 |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #quality #audit #governance #phase2 |
| 本版变更 | V0.3→V1.0: Pascal（任务 t_3f5a944c / 2026-07-19）授权 Phase 2 Audit-only Query Audit 生产 rollout。状态从"草稿"提升为"已授权受控 rollout、尚未执行"。新增 §6.4 授权事件记录；更新 §8.1 副作用矩阵状态栏；新增 §8.3a 停止条件与金丝雀验收标准；标记 §16 T2 SPEC 待定项。 |

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
|  → upsert to 03_data_ud_quality_summary
│  （Phase 1 禁用：不注入 QualitySummary，TTL=365 天作为后续确认值）
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

|> **设计阶段（本 RFC/SPEC 产出后）**：
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

### 6.4 授权事件记录（V0.3→V1.0：Pascal 已授权受控 rollout）

**授权事件**（2026-07-19，Pascal 任务 t_3f5a944c）：

| 维度 | 内容 |
|------|------|
| 授权范围 | Phase 2 Audit-only Query Audit 生产 rollout |
| 授权操作 | DDL（集合/索引创建）、AuditLogger 真实写入、一次 writer→reader smoke、一次可选金丝雀查询 |
| 授权边界 | 仅 `tradingagents.03_data_ud_query_audit`；仅该集合的 3 个既定索引（含 `fetched_at` TTL=365 天） |
| 身份隔离 | 独立三身份：DDL/bootstrap（bootstrap 级权限）、runtime writer（`insert` only）、runtime reader（`find` only）；不得复用业务身份 |
| 确认的设计文档 | DESIGN-03-011 §8.5（命名空间与环境变量契约）、§8.6（params 白名单模块级常量）、§8.7（fail-open / 写入失败策略）、§8.8（4 步 rollout 策略）、§8.9（DDL 工具代码契约 + createUser 初始密码传递） |
| 已实现脚本 | `scripts/unified_data/audit_rollout.py`（DDL 工具，含 role/user 创建、索引精确比对、QualitySummary 禁用校验） |
| | `scripts/unified_data/audit_smoke.py`（smoke CLI：writer insert + reader find_one round-trip，不含 secret / 业务字段） |

| 明确未授权 / 禁止 | 约束 |
|-------------------|------|
| `03_data_ud_quality_summary` 集合/index/write/injection | Phase 1 全程禁用 |
| `portfolio_*`、Smart Money、signal、trade、cache、TA-CN 既有集合 | 权限或操作均不涉及 |
| 业务数据回填、外部 Provider 调用、cron/systemd/gateway/webhook/外部推送 | 不在本授权范围内 |
| Git 提交 | 须在独立 Commit 阶段执行 |
| 输出/记录 token、密码、URI、用户名或连接串 | 硬性安全约束 |

**当前执行状态**：上述授权已由 Pascal 签署但**尚未执行**。DDL、smoke、金丝雀、全量 rollout 均需要 Implement→Verify→Review 流水线完成后由 Pascal 显式按步骤执行（详见 §8.6 rollout 策略）。本 RFC 及其派生 SPEC/Design 的状态已从"计划/草稿"升级为"已授权但未执行"。

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
- TTL：365 天（按 `fetched_at` 自动过期，Pascal 已确认）
- 索引：`fetched_at`（TTL 索引，`expireAfterSeconds` = 365 × 86400）、`(security_id, fetched_at)` 复合索引、`(capability, fetched_at)` 复合索引

TTL 值（365 天）已由 Pascal 确认。

#### 7.3.3 写入策略

- **同步**：每次 DataRouter.query() 返回后同步写入（catch-and-log）。写入失败不影响 query 返回值。
- **采样**：不采样——每次 query 都记录（Phase 2 基础要求）。批量/采样策略属于 Phase 3+
- **去重**：不要求审计事件严格去重（append-only 自然重复）。幂等性不在此阶段要求。
- **params 字段**（Pascal 已确认）：采用 params 白名单策略，只记录允许的查询参数键。敏感字段（凭据、令牌、密钥）默认丢弃，不进入审计文档。具体白名单在 Implement 阶段固化。

#### 7.3.4 写入失败策略（Pascal 已确认）

- **fail-open**：`AuditLogger` 写入失败不阻断主查询返回，不重试，不阻塞调用方。
- **本地结构化日志**：写入失败时通过 `logger.warning` 输出本地日志，包含失败原因和写入集合名。
- **不接外部告警**：Phase 1 写入失败不接外部告警系统（PagerDuty/短信/Telegram），仅本地日志 + 计数器。外部告警属于 Phase 3+。
- **已写入数据不自动删除**：回滚优先停用注入，已有审计数据保留。

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
- TTL：365 天（按 `date` 自动过期；Phase 1 不启用，TTL 作为后续启用时的已确认值）
- 索引：`(domain, security_id, date)` 唯一复合索引

#### 7.4.3 写入策略

- 每次 AuditLogger 写入后触发 upsert（catch-and-log）。
- 写入失败不影响 query 返回值。

---

## 8. 生产 MongoDB 副作用矩阵与确认流程

### 8.1 新增集合与执行状态

| 集合 | 操作 | DDL（集合/索引创建） | DML（写入） | V1.0 执行状态 |
|------|------|---------------------|------------|--------------|
| `03_data_ud_query_audit` | insert（append-only） | Pascal 已确认：TTL 索引 expireAfterSeconds=31536000 + 2 二级索引 | 仅 AuditLogger 写入 | 🔶 AUTHORIZED NOT EXECUTED（Pascal 已授权受控 rollout；DDL 与写入代码已实现，须经 Implement→Verify→Review 流水线，由 Pascal 显式按 rollout 策略分步执行） |
| `03_data_ud_quality_summary` | upsert | Pascal 已确认：TTL=365 天 | QualitySummary 不注入 | ❌ FORBIDDEN Phase 1（TTL=365 天仅作为后续启用时的已确认值记录在案；任何创建该集合/索引/写入的行为均属越权） |

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

### 8.3 Phase 1 实现阶段默认行为与范围

**Audit-only Phase 1 声明**（Pascal 已确认）：
- 第一阶段仅只记 query audit；不注入 QualitySummary；不让 quality tier 影响业务行为（质量语义仅观测，不构成业务门禁）。
- `AuditLogger`：默认使用 `noop` 后端（不写入任何 MongoDB），可选注入 `mongomock` 后端用于测试。经 Pascal 确认后启用真实 MongoDB 写入。
- `QualitySummary`：**整个 Phase 1 不注入**（包括 noop 实例也不创建）。其在 `AuditLogger.__init__` 中的参数始终保持 `None`。其 TTL=365 天作为后续启用时的已确认值记录在案。
- 所有测试使用 `mongomock`，不依赖真实 MongoDB。
- 所有实现代码在生产路径上有 `is_mongo_configured` 守卫（或等价机制），确保无 MongoDB 时静默降级为 no-op。

### 8.3a 停止条件与金丝雀验收标准（本授权事件的不可争议需求）

下列条件构成 rollout 过程中必须检查的暂停/回滚/禁止条件，SPEC 和 Design 必须无歧义实现：

#### 8.3a.1 停止条件（任一触发立即暂停 rollout，不可继续下一步）

| 条件 | 触发场景 | 应对 | 恢复条件 |
|------|---------|------|---------|
| SC-01 DDL 失败 | `audit_rollout.py --apply` 任一步骤失败（退出码非 0） | 停止 rollout，保留已创建工件（集合/索引/role/user），排查失败原因后重新执行 `--apply` | 修复后 `--apply` 幂等通过 |
| SC-02 Smoke 失败 | `audit_smoke.py --apply` writer insert 或 reader find_one 失败 | 停止 rollout，保留已写入 smoke event；排查 writer/reader 身份权限故障，修复后重新 smoke | writer→reader round-trip 通过 |
| SC-03 QualitySummary 越权 | `--verify` 检测到 `03_data_ud_quality_summary` 集合存在 | **紧急停止**，报告 Pascal；如非恶意创建则 drop 该集合；排查创建来源 | 集合不存在后恢复 |
| SC-04 身份泄露告警 | 脚本输出/日志中出现 URI、password、token 等敏感字段 | 紧急停止，立即 rotate 暴露的凭据 | 凭据 rotate 完成，重新从 DDL 开始 |
| SC-05 金丝雀写入失败率 > 5% | 金丝雀期间 AuditLogger 写入失败计数 > 查询量的 5% | 暂停 rollout，排查 MongoDB 写入路径（连接池、权限、网络） | 故障修复，金丝雀重新观察 24h |

#### 8.3a.2 金丝雀验收标准（canary 期 24-48h 后必须全部满足方可进入全量 rollout）

| 标准 | 阈值 | 测量方式 |
|------|------|---------|
| CV-01 写入成功率 | ≥ 99.5%（失败 ≤ 0.5% 的 AuditLogger.log() 调用） | AuditLogger 内部失败计数器 / `logger.warning` 出现频率 |
| CV-02 p99 写入延迟 | ≤ 200ms | AuditLogger 内部计时（写入 MongoDB 耗时） |
| CV-03 主查询无阻断 | 0 次因 AuditLogger 异常导致的查询失败 | DataRouter.query() catch 层计数 |
| CV-04 无 QualitySummary 污染 | 0 条 `03_data_ud_quality_summary` 集合文档 | `--verify` 或手动 `db.03_data_ud_quality_summary.estimatedDocumentCount()` |
| CV-05 无越权操作 | 0 次对 `portfolio_*` / `smart_money_*` / `signal_*` / `trade_*` 等集合的 insert | 审计日志 + 操作日志交叉验证 |

#### 8.3a.3 QualitySummary 禁止令（不可争议架构约束）

| 约束 | 说明 |
|------|------|
| QS-F1 | 任何代码路径、测试、脚本、配置均不得创建 `03_data_ud_quality_summary` 集合或相关索引 |
| QS-F2 | `AuditLogger.__init__` 的 `quality_summary` 参数在 Phase 1 始终保持 `None`，不得创建 noop 实例 |
| QS-F3 | `AuditLogger.log()` 内部如果监测到 `self._quality_summary is not None` 则必须抛 `RuntimeError`（防御性断言） |
| QS-F4 | `audit_rollout.py --apply` 必须显式检查 `03_data_ud_quality_summary` 不存在（若存在则 fail-fast，退出码 2） |
| QS-F5 | `audit_rollout.py --verify` 必须确认 `03_data_ud_quality_summary` 不存在（若存在则退出码 1 验证失败） |

#### 8.3a.4 一次性 smoke / canary 契约

| 步骤 | 执行命令 | 验证 | 通过后 |
|------|---------|------|--------|
| Smoke（一次性） | `audit_smoke.py --apply` | writer insert + reader find_one({_id}) round-trip；event 字段仅含 `_id`/`event_type`/`source`/`fetched_at`；不含业务/secret 字段 | 确认 writer/reader 身份可正常读写 |
| Canary（可选） | 在 1-2 个低流量 capability（如 `metadata.*`）启用 AuditLogger 真实写入 | 满足 CV-01~CV-05 后通过 | 逐步开放到全部 capability |

### 8.4 DDL 工具职责与最小权限身份契约（Pascal 已确认）

#### 8.4.1 DDL 工具职责

DDL 工具（`scripts/unified_data/audit_rollout.py`）是独立的受控部署脚本，仅由 Pascal 在 rollout 时显式执行。其职责严格限定为：

1. 使用**独立的 DDL bootstrap 身份**（非 runtime writer/reader 身份）连接 MongoDB
2. **创建或校验** 2 个 custom role + 2 个 runtime user：
   - Role `yquant_ud_audit_writer_role` → 对 `tradingagents.03_data_ud_query_audit` 的 insert-only 权限
   - Role `yquant_ud_audit_reader_role` → 对 `tradingagents.03_data_ud_query_audit` 的 find-only 权限
   - User `yquant_ud_audit_writer_user` → 授予 writer role
   - User `yquant_ud_audit_reader_user` → 授予 reader role
3. 创建或校验 `tradingagents.03_data_ud_query_audit` 集合与 3 个索引（TTL fetched_at + 2 个二级索引）
4. **不得**授予任何其他 collection 的权限，包括但不限于 `portfolio_*`、`smart_money_*`、`signal_*`、`trade_*`、缓存集合、TA-CN 既有集合
5. **不得**创建 `03_data_ud_quality_summary` 集合或相关索引（Phase 1 不启用）
6. `--apply` 参数才有副作用；缺省时 dry-run（零副作用）
7. 缺少 DDL 凭证环境变量时 fail-fast，不得静默降级

#### 8.4.2 命名空间

| 类型 | 正式名称 | 权限范围 |
|------|---------|----------|
| Writer Role | `yquant_ud_audit_writer_role` | `03_data_ud_query_audit` insert-only |
| Reader Role | `yquant_ud_audit_reader_role` | `03_data_ud_query_audit` find-only |
| Writer User | `yquant_ud_audit_writer_user` | 授予 writer role |
| Reader User | `yquant_ud_audit_reader_user` | 授予 reader role |
| DDL Bootstrap | 独立身份（非上述任一运行时账号） | `03_data_ud_query_audit` createCollection + createIndex，`admin` 级别 createRole/createUser |

**命名规则**：所有角色和用户使用 `yquant_ud_audit_*` 前缀，不得使用其他前缀。DDL 脚本内部校验前缀，拒绝不匹配的名称。

#### 8.4.3 环境变量契约

所有 MongoDB 连接凭据通过**显式环境变量**传递，不得硬编码在脚本中，不得打印或持久化。

**DDL 身份**（bootstrap 使用）：

| 环境变量 | 说明 | 强制 | 默认值 |
|----------|------|------|--------|
| `YQUANT_UD_AUDIT_DDL_MONGO_URI` | DDL 连接 URI | 是 | 无（fail-fast） |
| `YQUANT_UD_AUDIT_DDL_MONGO_USERNAME` | DDL 用户名 | 是 | 无（fail-fast） |
| `YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD` | DDL 密码 | 是 | 无（fail-fast） |
| `YQUANT_UD_AUDIT_DDL_MONGO_AUTH_DB` | DDL 认证数据库 | 否 | `admin` |

**Writer 身份**（AuditLogger 运行时使用）：

| 环境变量 | 说明 | 强制 | 默认值 |
|----------|------|------|--------|
| `YQUANT_UD_AUDIT_WRITER_MONGO_URI` | Writer 连接 URI | 否（noop 模式不要求） | 无 |
| `YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME` | Writer 用户名 | 否 | 无 |
| `YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD` | Writer 密码 | 条件强制¹ | 无 |
| `YQUANT_UD_AUDIT_WRITER_MONGO_AUTH_DB` | Writer 认证数据库 | 否 | `admin` |

**Reader 身份**（未来只读查询使用，Phase 1 不创建）：

| 环境变量 | 说明 | 强制 | 默认值 |
|----------|------|------|--------|
| `YQUANT_UD_AUDIT_READER_MONGO_URI` | Reader 连接 URI | 否 | 无 |
| `YQUANT_UD_AUDIT_READER_MONGO_USERNAME` | Reader 用户名 | 否 | 无 |
| `YQUANT_UD_AUDIT_READER_MONGO_PASSWORD` | Reader 密码 | 条件强制¹ | 无 |
| `YQUANT_UD_AUDIT_READER_MONGO_AUTH_DB` | Reader 认证数据库 | 否 | `admin` |

**禁止规则**：绝对不得复用业务身份（如 `portfolio_*`、`smart_money_*` 使用的数据库用户）作为 audit DDL/writer/reader 身份。runtime writer 与 DDL bootstrap 必须严格分离。

> ¹ **条件强制**：当 DDL 工具确定须 `createUser`（目标用户尚不存在）时，`YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD` / `YQUANT_UD_AUDIT_READER_MONGO_PASSWORD` 成为强制项；缺失或空值在 `createUser` DDL 命令发出前 fail-fast（退出码 3）。用户已存在（幂等校验）时不需要该密码。详见 §8.4.7。

#### 8.4.4 params 白名单：模块级常量

params 白名单定义为模块级常量 `ALLOWED_PARAMS: set[str]`（位于 `scripts/unified_data/audit_rollout.py`），而非构造函数注入。Implement 阶段固化具体键列表，初始化后不可变。白名单策略：

- 只记录白名单中存在的查询参数键
- 敏感字段（token、api_key、secret、password、credential）默认丢弃
- `params` 在审计文档中始终存在（最少为空 JSON 对象 `{}`），不得省略

#### 8.4.5 拒绝 broad business identity 规则

- DDL 脚本**禁止**复用任何现有业务数据库用户（`portfolio`、`smart_money`、`signal`、`trade`、`cache` 等既有业务集合使用的账号）
- runtime writer/reader 的权限范围严格限定为 `03_data_ud_query_audit` 集合
- 违反此规则时脚本 fail-fast（退出码 2）
- 此规则为硬性架构约束，不得通过任何配置覆盖

#### 8.4.6 脚本路径与 CLI

- **脚本路径**：`scripts/unified_data/audit_rollout.py`
- **CLI 接口**：仅 `--apply`（执行 DDL）和 `--verify`（只读验证）；`database` / `collection` / `writer-role` / `reader-role` 均为模块级固定常量，不得由 CLI 覆盖
- **退出码**：0=成功（dry-run/verify/apply），1=验证失败，2=范围校验失败，3=凭证缺失，4=运行时错误

#### 8.4.7 createUser 初始密码传递契约（Pascal 已确认）

MongoDB `createUser` 命令对 SCRAM 用户强制要求 `pwd` 字段。DDL 工具在创建 runtime writer/reader user 时，必须提供初始密码。本契约以最小安全方式固化该密码的来源、消费与防护规则，作为修复实现的唯一基线。

**密码来源**：复用既有 runtime 密码环境变量（不新增 env、不新增 alias/fallback）：

- writer user → `YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD`
- reader user → `YQUANT_UD_AUDIT_READER_MONGO_PASSWORD`

使创建出的用户可直接以该密码认证（runtime 登录密码 = createUser 初始密码），无需二次配置。

**触发与消费**：

1. `_ensure_user` 先通过 DDL bootstrap identity 执行只读 `usersInfo` 判定目标用户是否存在。该预检连接使用 `YQUANT_UD_AUDIT_DDL_MONGO_*` 凭证（非 runtime writer/reader 身份），仅读不写；不在预检阶段创建/更新 role/user/index/collection。
2. 仅当用户**不存在**（须 createUser）时，读取对应 runtime 密码环境变量，将其作为 `createUser.pwd` 传入该单条 DDL 命令。
3. 用户**已存在**（幂等路径）时，**不得读取、不得轮换、不得重设**密码；仅校验 role binding 精确匹配。

**缺失/空处理**：当须 createUser 且对应密码环境变量缺失或为空字符串时 → fail-fast（退出码 3），**在 `createUser` DDL 命令发出之前**退出。注意：DDL bootstrap identity 的只读 `usersInfo` 存在性预检连接属于合法操作，不受此约束影响；此处禁止的是**发出不含 pwd 的 createUser 写 DDL**，而非禁止预检只读连接。

**用户不匹配处理**：用户已存在但 role binding 与契约不一致 → fail-closed（退出码 4），**不得修改、不得重建用户**。

**安全防护**（硬性约束）：

- 不得打印（print）、记录（logger/log）、返回或持久化 password 值。
- password 变量生命周期限定在 `createUser` 命令构建与执行的单一作用域内，执行后立即丢弃。
- 不得出现在任何 traceback、异常消息或诊断输出中。
- DDL bootstrap 密码（`YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD`）与 runtime 密码严格隔离，不得交叉引用。

**不变量保持**：本契约不影响 Audit-only、3 indexes、QualitySummary 禁止、dry-run 零副作用等既有不变量。

### 8.5 单集合 + 3 索引 + Audit-only 不变量

| 不变量 | 说明 | 约束 |
|--------|------|------|
| 单集合 | Phase 1 只操作 `03_data_ud_query_audit` | 不得创建 `03_data_ud_quality_summary` |
| 3 索引 | TTL `fetched_at` + `(security_id, fetched_at)` + `(capability, fetched_at)` | 索引名、键顺序、TTL expireAfterSeconds 不得擅自修改 |
| Audit-only | 仅记 query audit，不注入 QualitySummary | quality tier 仅观测，不构成业务门禁 |
| `--apply` 有副作用 | 只有显式 `--apply` 时执行 DDL；缺省 dry-run | 凭证缺失 fail-fast（退出码 3） |

### 8.6 Rollout 策略（Pascal 已确认）

```
第 1 步：DDL
  - 创建 03_data_ud_query_audit 集合 + TTL 索引（expireAfterSeconds=365×86400）+ 二级索引
  - ⛔ 不得创建 03_data_ud_quality_summary（Phase 1 Audit-only 不启用）
  - 使用独立 DDL 账号，建好即销毁连接

第 2 步：真实 smoke
  - 在生产环境用真实 AuditLogger 写入一条审计记录 → 立即读取验证 schema
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
   - direct use / warning / degrade / reject 等级 → §7.1.3
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
   - TTL 具体值（365 天，Pascal 已确认）→ §7.3.2
   - 索引策略细节 → SPEC §7 给出候选索引

|

---

## 14. 后置验收边界：DDL 工具 Developer Acceptance & Production Smoke

### 14.1 Developer Acceptance 验收点（DDL 工具修复）

Implement 修复 `scripts/unified_data/audit_rollout.py` 的角色/用户创建缺口时，须验证以下验收点：

| # | 验收点 | 验证方式 | 通过条件 |
|---|--------|---------|----------|
| A1 | role/user 创建函数存在 | 单元测试 mock `db.command()` | `_ensure_write_role` / `_ensure_read_role` / `_ensure_write_user` / `_ensure_read_user` 四函数存在且 `run_apply` 调用链覆盖 |
| A2 | 命名前缀为 `yquant_ud_audit_*` | grep 检验硬编码字符串 | `WRITER_ROLE_NAME` / `READER_ROLE_NAME` / `WRITER_USER_NAME` / `READER_USER_NAME` 均以 `yquant_ud_audit_` 开头 |
| A3 | 权限范围正确 | `createRole` privileges 检查 | writer role 仅含 `{resource: {db: "tradingagents", collection: "03_data_ud_query_audit"}, actions: ["insert"]}`；reader role 仅含 `["find"]` |
| A4 | 白名单为模块级常量 | grep 检验 | `ALLOWED_PARAMS` 定义在模块作用域（无类/函数缩进），非构造函数参数 |
| A5 | 拒绝 broad identity | 单元测试 mock | `run_apply` 不调用涉及 `portfolio_*` / `smart_money_*` / `signal_*` / `trade_*` / 缓存集合的 grant 操作 |
| A6a | DDL bootstrap 凭证缺失 fail-fast | `YQUANT_UD_AUDIT_DDL_MONGO_URI`/`USERNAME`/`PASSWORD` 未设置 | 退出码 3，不发起任何 MongoDB 连接（连 DDL bootstrap 连接也不建立） |
| A6b | runtime 密码缺失 + 用户不存在 fail-fast | 经 DDL identity 只读 `usersInfo` 确认用户不存在后，对应 runtime 密码环境变量缺失/空 | 退出码 3；允许一次 DDL identity 只读连接用于 `usersInfo` 存在性预检，但**不发 `createUser`、不执行任何写 DDL、不创建/不使用 writer/reader runtime identity** |
| A7 | 范围校验 fail-fast | `--unknown-flag` | 退出码 2（argparse 拒绝未知参数），无需进一步检查 |
| A8 | dry-run 零副作用 | `python audit_rollout.py`（无 `--apply`） | 打印计划、退出码 0、不调用 MongoDB 连接 |
| A9 | `--apply` 幂等 | 两次连续 `--apply` | 第二次不报错，输出含 `skipped=[...]` |
| A10 | 全部已有测试不因修改而失败 | `pytest skills/data/unified_data/tests/ -m "not production_gate" -q --tb=short` | 0 failed |

### 14.2 Production Smoke 边界

仅在 Pascal 显式授权 DDL+smoke 后方可执行。

**Smoke 步骤（最小集）：**

```bash
# 1. DDL（role/user/index/collection）
YQUANT_UD_AUDIT_DDL_MONGO_URI="..." YQUANT_UD_AUDIT_DDL_MONGO_USERNAME="..." YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD="..." \
  python scripts/unified_data/audit_rollout.py --apply

# 2. 验证 DDL 结果
YQUANT_UD_AUDIT_DDL_MONGO_URI="..." YQUANT_UD_AUDIT_DDL_MONGO_USERNAME="..." YQUANT_UD_AUDIT_DDL_MONGO_PASSWORD="..." \
  python scripts/unified_data/audit_rollout.py --verify

# 3. Writer user 写入一条审计记录
# （通过 production_gate smoke test）
PYTHONPATH=. YQUANT_UD_AUDIT_WRITER_MONGO_URI="..." YQUANT_UD_AUDIT_WRITER_MONGO_USERNAME="..." \
  YQUANT_UD_AUDIT_WRITER_MONGO_PASSWORD="..." \
  pytest skills/data/unified_data/tests/ -m "production_gate" -v -k "test_audit_logger_prod"

# 4. Reader user 读取验证（通过 production_gate smoke test）
```

**回滚边界：**

| 操作 | 回滚命令 | 风险 |
|------|---------|------|
| 已创建 role | `db.dropRole("yquant_ud_audit_writer_role")` / `db.dropRole("yquant_ud_audit_reader_role")` | 无丢失（纯权限） |
| 已创建 user | `db.dropUser("yquant_ud_audit_writer_user")` / `db.dropUser("yquant_ud_audit_reader_user")` | 无丢失（纯权限） |
| 已创建集合 | `db.dropCollection("03_data_ud_query_audit")` | 损失已写入审计数据 |
| 已创建索引 | `db.03_data_ud_query_audit.dropIndex(...)` | 无丢失（数据完整） |
| 已写入审计数据 | 不可回滚（保留），停用 AuditLogger 注入 | 前端窗口数据丢失 |
| 全部回滚 | 删除 `quality/` 和 `audit/` 子包 | 零代码残留 |

---

## 15. 本 RFC 无法单独决定的 T2 SPEC 待定项

下列项目在 RFC 层次存在多解或依赖具体环境约束，必须由 T2 SPEC 精确化后方可进入 Implement：

| # | 待定项 | RFC 当前约束 | 需 SPEC 精确化内容 |
|---|--------|-------------|-------------------|
| T2-01 | `ALLOWED_PARAMS` 精确白名单 | §8.4.4 定义为模块级常量 `set[str]`，但未列出具体键（仅声明"Implement 阶段固化"） | SPEC 须列出 `ALLOWED_PARAMS` 的精确键集合，说明每个键的语义与类型约束。当前 `audit_rollout.py` 已实现 11 键（`security_id`/`market`/`domain`/`operation`/`start_date`/`end_date`/`limit`/`frequency`/`provider`/`consumer`/`force_refresh`），SPEC 须确认该列表与 Design 的 AuditLogger 白名单一致。 |
| T2-02 | Smoke event 精确 schema | §8.3a.4 约定字段限 `_id`/`event_type`/`source`/`fetched_at`，但未定义 `event_type` 和 `source` 的值域与含义 | SPEC 须固化 smoke event 的 `event_type` 和 `source` 精确值（当前 `audit_smoke.py` 实现为 `"audit_smoke_round_trip"` / `"audit_smoke_cli"`），以及 `fetched_at` 精确格式（UTC 含 tzinfo vs naive datetime） |
| T2-03 | AuditLogger 生产 MongoDB client 生命周期 | §7.3.3 仅定义写入策略（同步 catch-and-log），未指定 client 的创建方式（单例 vs 每次创建）、连接池大小、超时配置、重连行为 | SPEC 须定义：AuditLogger 生产 MongoDB client 的生命周期契约（延迟创建 vs 预初始化）、默认连接池参数、空闲超时、异常重连策略。Implementation 可自行决定默认值，但在 SPEC 中记录 decision rationale。 |
| T2-04 | `--verify` 与 smoke 的顺序与依赖关系 | §8.6 rollout 策略暗示 DDL→Smoke→Canary 的顺序，但未定义 verify 在流程中的精确位置和失败时回退策略 | SPEC 须定义 rollout 步骤间的精确依赖关系：verify 是否必须 smoke 前置、verify 失败后的恢复路径（自动重试 vs 人工介入）、smoke 是否能脱离 verify 独立运行 |
| T2-05 | Reader user 的 Phase 1 创建策略 | §8.4.1 要求"创建或校验" reader user，但 §8.4.3 reader 环境变量表标注"Phase 1 不创建" | SPEC 须确认 reader user 是否在 Phase 1 DDL 中创建。存在两种合理选择：(A) 创建 reader user（预留身份，即使 Phase 1 不使用）；(B) 不创建 reader user（Phase 1 未授权 reader 写操作）。建议规格化选择并记录理由。 |
| T2-06 | `--verify` 检查 `03_data_ud_quality_summary` 不存在时的退出码 | §8.3a.3 QS-F4/QS-F5 声明 `--apply` fail-fast 退出码 2、`--verify` 退出码 1，但未定义退出码的精确兜底路径（如 QS 集合不存在时的验证通过 vs verify 跳过） | SPEC 须固化 `--verify` 对 QualitySummary 不存在性检查的精确行为：是通过（退出码 0，预期不存在被视为通过）还是跳过（不检查 QS 集合）。当前 Design §8.9.4 `--verify` 验证范围中列明 QualitySummary 不得存在且此项通过=0。 |

> **决策原则**：以上 6 个待定项均不得由 Implement 自行判定。Implement 必须先完成 SPEC，经 Design 固化后，Pascal 确认再进入代码实现。

## 16. 参考资料

- `docs/rfc/03_data/RFC-03-007-unified-data-layer.md` — Unified Data Layer 总纲
- `docs/spec/03_data/SPEC-03-007-unified-data-layer.md` — Unified Data Layer 契约
- `docs/design/03_data/DESIGN-03-007-unified-data-layer.md` — Unified Data Layer 详细设计
- `docs/spec/03_data/SPEC-03-009-unified-data-phase-1b-persistence-plane.md` — Phase 1B-B 持久化缓存平面契约
- `skills/data/unified_data/` — 现有代码基
- `skills/data/unified_data/tests/` — 现有测试基
