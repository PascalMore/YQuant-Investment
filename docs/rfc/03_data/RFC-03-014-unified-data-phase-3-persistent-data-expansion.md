# RFC-03-014：Unified Data Phase 3 — 重要持久化扩展（受控分期）

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-20 |
|| 最后更新 | 2026-08-02（V0.20 RFC F6 freshness canonical key 裁定同步：PC-11 冻结解除——Pascal 裁定 `market_sentiment` 为 `sentiment.market_snapshot` 的唯一 canonical freshness key、`sentiment_limit_up_pool` 为 `sentiment.limit_up_pool` 的唯一 canonical key；§P0.6、§P1.9 冻结项同步解除并指向 RFC-03-014-F6 / SPEC-03-014-F6。不动所有已有 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态。） |
|| 版本号 | V0.20 |
| 所属模块 | 03_data（数据层） |
| 依赖 RFC | RFC-03-007（Unified Data Layer 总纲）、RFC-03-011（Phase 2 质量与审计治理） |
| 依赖 SPEC | SPEC-03-007（Unified Data Layer 契约）、SPEC-03-014（Phase 3 持久化扩展契约，本文件对应之 SPEC） |
| 关联 Design | DESIGN-03-007（Unified Data Layer 详细设计），§5.3 重要持久化集合、§7.4 Provider 优先级 |
| 替代 RFC | 无（Phase 3 为首次形式化定义，不替代任何 RFC） |
| AI 适配 | Hermes Kanban profile worker |
| 标签 | #data #unified_data #phase3 #persistence #sector #sentiment #capital_flow |

### 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|---|
| V0.1 | 2026-07-20 | 初始创建。定义 Phase 3 三阶段受控分期方案（P3-A/P3-B/P3-C），给出文档级候选 schema、读写边界、Pascal 授权 Gate 与验收标准。 | YQuant-Principal |
| V0.2 | 2026-07-20 | 修正：Gate 表移除子阶段间硬前置依赖以对齐 §4.2"非严格前置"决策；DataRouter.query() 改为全程只读（Step 4 不写物化/Cache），新增显式 ETLV refresh 路径说明；AuditLogger 声明默认关闭；Phase 1E/Phase 2 明确为计划态契约。 | YQuant-Principal |
| V0.3 | 2026-07-22 | 生产就绪扩展。离线实现（T2 Design V0.6 + T3 Implement）已完成；本版本新增 T4 生产就绪阶段定义：§13 详细规范（只读预检、真实 Provider Smoke、副作用矩阵、Token 最小化、DDL/DML 独立 Gate、停止条件、成功标准）；§6 从旧 T3 实施 Gate 改写为 T4 生产就绪 Gate（PR-G-* 系列）；§9 追加就绪验收标准；§10 落地计划追加 T4 阶段；§5.5 追加生产就绪 FV；§7.4 扩展为完整 Smoke 流程。 | YQuant-Principal |
| V0.4 | 2026-07-22 | 历史更新——**已被 V0.6 替换**。AKShare 无 Token + 复用 Phase 2 MONGO_URI 同步。—— AKShare 为匿名数据源，PR-0 跳过其密钥审计（§6.2），FV-10 改为匿名调用（§5.5），PR-2/PR-3/PR-4 移除 token 消耗语义（§6.2），PR-0 约束仅限 MongoDB 秘密（§6.4），§13.3 审计表移除 AKSHARE_TOKEN 并将 MONGODB_URI 替换为 Phase 2 已验证的 MONGO_URI。V0.6 将此 MONGO_URI 单键来源迁移至 skills/.env 五组件键（MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE），V0.4 的 MONGO_URI 语义视为 superseded。 | YQuant-Principal |
| V0.5 | 2026-07-23 | 修正：清除 §13.1 PR-2/PR-3/PR-4 行「API token 消耗」残留——AKShare 为匿名数据源无 Token，改为「AKShare 匿名 API 调用」；与 SPEC §14.1 对齐。 | YQuant-Principal |
| V0.6 | 2026-07-24 | PR-1 凭证来源契约对齐：MongoDB 连接凭据来源从 MONGO_URI + Hermes profile `.env` 改为复用 Phase 2 skills/.env 五组件键（MONGODB_HOST、MONGODB_PORT、MONGODB_USERNAME、MONGODB_PASSWORD、MONGODB_DATABASE），沿用 PortfolioMongoLoader Phase-2 Mongo 认证语义（组件式构造连接，非 URI）；PR-0 审计表对应更新；移除 Hermes profile `.env` 候选路径；历史 MONGO_URI 描述均标为 superseded。 | YQuant-Principal |
| V0.7 | 2026-07-25 | B1-P3A 轻量更新。§13.6 DDL Gate 序列图后追加「B1-P3A 冻结状态」说明：仅 PR-DDL-P3A 已冻结（权威契约见 DESIGN-03-014 §6.4 V0.13 / SPEC-03-014 §14.6.4 V0.6），PR-DDL-P3B / PR-DDL-P3C 尚未冻结。不动 §13.6 既有 DDL Gate 授权要求 1-5、不动其它章节。 | YQuant-Principal |
| V0.8 | 2026-07-25 | B1-P3B 轻量更新。§13.6 冻结状态说明更新为「PR-DDL-P3A 与 PR-DDL-P3B 均已冻结」（权威契约见 DESIGN-03-014 §6.4/§6.4.bis V0.14 / SPEC-03-014 §14.6.4/§14.6.bis V0.7），PR-DDL-P3C 尚未冻结。不动 §13.6 既有 DDL Gate 授权要求 1-5、不动其它章节。 | YQuant-Principal |
| V0.9 | 2026-07-25 | B1-P3C 轻量更新。§13.6 冻结状态说明更新为「PR-DDL-P3A / PR-DDL-P3B / PR-DDL-P3C 三者均已冻结」（权威契约见 DESIGN-03-014 §6.4/§6.4.bis/§6.4.ter V0.15 / SPEC-03-014 §14.6.4/§14.6.bis/§14.6.ter V0.8），Phase 3 三子阶段 DDL 全部授权。不动 §13.6 既有 DDL Gate 授权要求 1-5、不动其它章节。 | YQuant-Principal |
| V0.10 | 2026-07-26 | B2 实测映射证据冻结。新增 §13.4.5：依据 2026-07-26 B2 一次性只读 smoke 的冻结证据（真实报告只读副本位于 `/tmp/yquant-b2-pr234-20260726/`，不可移动/提交、不可重跑），冻结六项可执行契约——PR-3 `flow.northbound_daily` 实际 endpoint 搭载「北向持股历史」语义而非「北向净流入」（禁止伪装）、PR-4 空返回语义区分与 verdict 边界、PR-2 SSL 网络停止诊断边界、单次 live-read 精确调用预算与零写入边界、T2 实现最小范围。新增 §13.4.5 引用 SPEC §14.4.5（权威可执行契约）与 DESIGN §15.x V0.16（权威设计定义）。不动 §13.6 DDL 冻结状态（三者仍冻结）、不动既有授权范围、不动用户授权。 | YQuant-Principal |
|| V0.11 | 2026-07-26 | **Pascal C+X2 决策同步（Recovery/T2.5）**。§13.4.5.2 PR-3 三选一由 Pascal 2026-07-26 明确选 **C**（当前 Phase 3 不提供 northbound net inflow；`northbound_net_inflow` 保持 None；持股历史不得伪装为净流入；不引入新 endpoint/capability）。§13.4.5.3 PR-4 空返回语义按 **X2** 收敛：reporter 仅保留必要账本字段，移除 `empty_semantics` 分类与 verdict 篡改语义；空返回维持 fail（保守）。删除全部三选一「未选择/阻塞等待 Pascal」失效文本。PR-2 SSL 单变量网络诊断边界与零 live-read 预算不变；§3 domain object 与 §13.6 DDL 冻结状态不变。 | YQuant-Principal |
|| V0.13 | 2026-07-29 | **D1/D2/D3 文档修正同步**。§5.1.5 source_trace 约束从 blanket 子串匹配改为精确 `(ok)` 后缀匹配——不允许 `"ud_materialized(ok)"` 或 `"cache(ok)"` 条目；允许 `"ud_materialized(skipped: ...)"`、`"cache(miss)"`。与 D1 裁定（仲裁：不修改 Router，只改测试断言）对齐。不动 §13.4.5 Pascal C+X2 决策内容、不动 §13.6 DDL 冻结状态、不动既有授权范围。 | YQuant-Principal |
|| V0.16 | 2026-07-30 | **Pascal 22-field MarketSentimentSnapshot canonical 契约裁定同步**。Pascal 裁定 22 字段全市场多维快照（`{market, snapshot_date, snapshot_time}` 唯一键）为 `MarketSentimentSnapshot` 的 canonical 产品 schema，淘汰此前离线 T3-B 实现的 10 字段 `sentiment_type` 聚合模型（`{market, sentiment_type, market_date}` 唯一键）。§5.3 P3-C schema 引用从候选升级为 canonical；§9 A-003 追加 canonical 声明验证；§10 T3 阶段状态标注 10 字段模型已被 superseded；§11 OQ-6 明确 market_temperature 为未决待定（允许 None）。离线存在的 10 字段实现作为 superseded 事实保留，不删除，但任何进一步扩展必须基于 22 字段 canonical 契约。不动 §13.4.5.8-§13.4.5.10 B2/R0 裁决内容、不动 §13.6 DDL 冻结状态、不动既有授权范围。 | YQuant-Principal |
|| V0.17 | 2026-07-30 | **P0 真实 Provider 离线可实现契约冻结**。新增 §P0 完整章节：定义六 capability 精确状态矩阵、真实 Provider 统一接口边界（extract→canonical mapping→validation/provenance→DataResult.source_trace）、P3-A/P3-B/P3-C 逐项映射验收项、P0 vs P1 vs P2 边界依赖、完全副作用矩阵、旧 checkbox 状态纠正到可审计现状。全部真实调用声明为未来授权 smoke/production activation，禁止在离线 Implement/Verify 中触发。不动 §13.4.5 B2/R0/Pascal C+X2 裁决、不动 §13.6 DDL 冻结状态、不动既有授权范围。 | YQuant-Principal |
|  | V0.19 | 2026-07-31 | **P1 受控 Mongo 物化与显式 refresh 的零副作用契约冻结**。新增 §P1 完整章节：P1 覆盖 capability 与集合文档语义、MongoDB-first 离线实现边界（仅 fake/mock/静态审计）、internal-first read/explicit refresh/cache write 边界与默认禁止规则、完全副作用矩阵、授权关口与零 I/O 边界、PC-11 freshness 跨层冻结声明。不动 P0/P1/P2 边界定义、不动已有授权范围、不动所有 ❌ 状态。 | YQuant-Principal |
|  | V0.20 | 2026-08-02 | **F6 freshness canonical key 裁定同步**。Pascal 裁定冻结 `market_sentiment` 为 capability `sentiment.market_snapshot` 的唯一 canonical freshness domain key（TTL=3600），`sentiment_limit_up_pool` 为 capability `sentiment.limit_up_pool` 的唯一 canonical key（TTL=3600）；`sentiment` 不再是 freshness TTL key（仅 capability domain 前缀）；禁止双 key/alias/fallback 造成 freshness 漂移。§P0.6（冻结事实、PC-11、绝对禁止）与 §P1.9（Freshness 跨层冻结项）同步解除并指向 F6 裁定。权威裁定见 `RFC-03-014-F6`，可执行契约见 `SPEC-03-014-F6`。不动 P0/P1/P2 边界定义、不动既有授权范围、不动所有 ❌ 状态。 | YQuant-Principal |
|
---

## 1. 执行摘要

Phase 3 为 Unified Data 新增三个重要持久化集合——板块/行业快照（P3-A）、个股资金流（P3-B）、市场情绪快照（P3-C）——并激活对应的真实外部 Provider（AKShare）进行物化写入。本阶段受控拆分为三个独立子阶段，每子阶段覆盖一个持久化面，禁止一次性部署。Phase 3 不创建 Design（由后续 T2 交付），仅定义分期方案、文档级数据契约、离线实施范围、生产授权 Gate 与验收标准。

> **声明**：本文档中涉及的板块/行业、资金流、情绪数据定义为辅助研究数据范畴。RFC 本身不包含可执行的交易指令或投资建议。所有 domain object 对应的 SPEC-03-014 中强制标注「辅助研究数据，不构成交易指令或投资建议」，该声明通过静态 grep 验证。本 RFC 不主张对共享 worktree 中非本路径文件的修改状态作出事实断言；diff 范围仅限本卡 allowlist。

---

## 2. 背景与动机

### 2.1 现状

| 现状 | 说明 |
|---|---|
| 板块/行业数据虽有 `index_daily_quotes` + `stock_sector_info`（TA-CN 既有），但缺少每日行业/概念排名、领涨股、涨跌家数等聚合快照 | DESIGN-03-007 §5.3.1 列为 New，当前无持久化 |
| 市场情绪数据（涨停/跌停家数、全市场涨跌比、温度指数等）完全无持久化 | DSA `market_review` 为私有内存分析，不对外 |
| 资金流数据（主力净流入、北向、融资融券）完全无持久化 | 多项策略依赖该数据，现有依赖手动作坊 |
| Phase 1D 已验证外部 Provider（Tushare）真实激活链路 | Provider 架构已验证可用，Phase 3 复用到 AKShare 激活 |
| Phase 1E 已定义个股级 `sentiment.stock_score` 契约（正交） | 市场级情绪（P3-C）与个股级情绪（Phase 1E）互补不冲突 |

### 2.2 业务价值

| 能力 | 消费方 | 价值 |
|---|---|---|
| 板块/行业快照 + 排名 | strategies（行业轮动）、reports（每日板块复盘）、researcher（行业表现分析） | 模块化获取每日行业表现，无需自行计算 |
| 个股资金流 | strategies（资金面因子）、researcher（主力资金跟踪）、portfolio（组合归因） | 标准化的资金流时序数据，支持因子研发 |
| 市场情绪快照 | strategies（市场择时）、risk（极端情绪风控）、reporter（每日市场温度） | 量化市场温度的标准化数据源 |

### 2.3 触发原因

Pascal 将板块/情绪/资金流列为 Phase 1D（外部 Provider 激活）后的下一优先域。Phase 1D 已验证「外部 Provider 真实激活」的完整链路，Phase 3 将其经验扩展到 AKShare 数据和全新持久化集合。

### 2.4 命名衔接：Phase 3

| Phase | 名称 | 定位 |
|---|---|---|
| 1D | External Provider Activation（CN 日线） | Tushare 真实调用验证 |
| 1E | Sentiment Minimal Slice | 个股情绪契约先行，无持久化、无真实 API |
| 2 | Quality & Audit Governance | 质量评分、审计日志、Provider 治理（Phase 2 与 Phase 3 独立可并行） |
| **3** | **重要持久化扩展** | **新增三个 03_data_ud_* 物化集合，激活 AKShare 外部 Provider** |
| 4 | 龙虎榜/筹码/热门股票 | 下一阶段持久化 |

Phase 3 与 Phase 2 独立可并行——Phase 2 治理框架在 Phase 3 物化写入时可直接复用 AuditLogger 和 QualityScorer（需 Pascal 授权）。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 将 Phase 3 拆分为 P3-A / P3-B / P3-C 三个可独立授权、独立验证的子阶段
- [ ] 每子阶段覆盖一个持久化集合及其关联的 Provider 激活、domain service、UnifiedDataClient 入口
- [ ] 定义三个候选 collection 的文档级 schema：字段、类型、唯一键、索引建议、禁止字段
- [ ] 定义 DataRouter / UnifiedDataClient / provider / ETLV 读写职责边界
- [ ] 逐项定义 Pascal 授权 Gate：真实 MongoDB 集合/index/schema/DML、外部 API 调用、长期调度、生产 canary
- [ ] 定义测试策略：单元测试 colocated 于 `skills/data/unified_data/tests/`，离线测试仅 mongomock/fake provider
- [ ] 明确所有板块/情绪/资金流数据为辅助研究数据，不构成交易指令或投资建议

### 3.2 非目标（Out of Scope）

- **不创建 Design**（由后续 T2 交付 DESIGN-03-014）
- **不实现代码、不修改现有代码、不修改配置/requirements/SKILL/README/脚本/cron/systemd/gateway/webhook**
- **不读取 `.env` 或凭据**
- **不连接 MongoDB、不执行任何网络/API/provider 调用**
- **不执行 DDL/DML**
- 不覆盖龙虎榜、筹码、热门股票（属 Phase 4）
- 不创建 Task Center Job 集成（属 Phase 5）
- 不修改已有 domain object 的字段签名
- 不修改 TA-CN/DSA/Argus/portfolio/data-pipeline/task_center 代码
- 不解冻 QualitySummary（Phase 2 仍冻结，无 long canary 结论）
- 不是 Phase 1E 的前置或替代；个股级情绪（Phase 1E）与市场级情绪（P3-C）正交

---

## 4. 整体设计

### 4.1 核心设计哲学

Phase 3 受控分期：每子阶段独立授权、独立验证、独立部署。每子阶段仅覆盖一个持久化面及其关联的 Provider 能力集，禁止一次性部署三个集合。internal-first 读取路径（TA-CN 既有 → UD 物化 → Cache → 外部 Provider）不变，新集合通过 LocalMongoAdapter 层读取。

**持久化目标**：本阶段新增的 `03_data_ud_*` 物化集合默认以 **MongoDB（`tradingagents` 库）** 为唯一生产持久化目标。SQLite 仅可用于以下明确限定场景：
- 现有 legacy adapter 的数据源（如 DSA 的 SQLite 路径——**DSA 不是运行时数据源**，不出现在外部 fallback 链）
- 单元测试 / 集成测试中的隔离数据库（如 `mongomock` 或临时 SQLite 替代）
- 离线 fallback（仅当 MongoDB 完全不可达且消费方已通过配置显式授权）
- **禁止**：SQLite 不得作为 Phase 3 正式生产写入目标，不得出现在 `03_data_ud_*` 集合的生产写入路径中。

### 4.2 Phase 3 分解方案

<!-- 假设：以下三阶段拆分已征求 Pascal 意向但未获最终确认；Pascal 在 T2 Design 开始前通过 Gate 确认此方案 -->

| 子阶段 | 持久化集合 | 新增 Capabilities | Provider | 域 |
|---|---|---|---|---|
| **P3-A** | `03_data_ud_market_sector_snapshot` | `sector.snapshot`, `sector.ranking` | AKShare | sector |
| **P3-B** | `03_data_ud_stock_capital_flow` | `flow.capital_flow_daily`, `flow.northbound_daily` | AKShare | flow |
| **P3-C** | `03_data_ud_market_sentiment_snapshot` | `sentiment.market_snapshot`, `sentiment.limit_up_pool` | AKShare | sentiment |

**依赖关系**：P3-A → P3-B → P3-C 为**推荐执行顺序**（先完成板块/行业域，再资金流，最后情绪——风险递增），但不构成严格前置依赖。每子阶段可独立部署。若 Pascal 指定其他顺序，以 Pascal 确认为准。

**禁止方案**：一次性部署所有三个集合为 **FAIL**——违反受控分期原则，退回。

### 4.3 与 Phase 1E 的关系

<!-- 计划态契约：RFC-03-013/SPEC-03-013 为 Phase 1E 文档，非已交付事实 -->

Phase 1E 聚焦个股级 `sentiment.stock_score` 标准化情绪分数（不持久化、不触网络）；P3-C 聚焦市场级情绪聚合（涨停家数、温度指数等）。两者构成完整的情绪数据栈（个股分数 → 市场聚合），**正交、互补、不相互前置**。

**Phase 1E 状态声明**：Phase 1E（RFC-03-013 / SPEC-03-013）当前为计划态契约，尚处 Design 阶段之前，非已交付事实。Phase 1E 尚未进入 Design/Implement 不影响 P3-C 的规划，P3-C 也不等待 Phase 1E 完成。

### 4.4 与 Phase 2 的关系

<!-- 已验证事实：DESIGN-03-007 §9 Quality/Audit 设计；Phase 2 当前仅 03_data_ud_query_audit 受控启用 -->

**AuditLogger 默认关闭**：Phase 2 的 AuditLogger（`03_data_ud_query_audit`）在 Phase 3 中**默认不启用**，不在 Phase 3 的 refresh 写入路径中自动写入。refresh 方法可预留 AuditLogger 调用扩展点（try-pass 模式，不影响主流程），但实际启用需 Pascal 独立授权。QualitySummary 始终冻结，Phase 3 不读写 `03_data_ud_quality_summary`。

**Phase 2 状态声明**：Phase 2（RFC-03-011）当前为计划态契约，非已交付事实。Phase 2 与 Phase 3 独立可并行，Phase 3 不等待 Phase 2。

---

## 5. 详细设计

### 5.1 P3-A：板块/行业快照

#### 5.1.1 业务语义

每日各板块（行业/概念/区域）的聚合快照：涨幅排名、涨跌家数、领涨股、主力资金净流入、成分股列表等。消费方通过 `sector.snapshot`（查询单个板块）和 `sector.ranking`（查询当日板块排名）访问。

<!-- 假设：AKShare 东方财富板块接口可覆盖行业/概念/区域三类板块；待 T3 实施阶段验证 -->

#### 5.1.2 数据维度

| 维度 | 取值 |
|---|---|
| 市场 | CN（A 股） |
| 时间粒度 | 日级（每个交易日收盘后） |
| 板块类型 | industry / concept / region / style |
| 标的 | 板块代码（东方财富行业代码，如 `BK0489`） |

#### 5.1.3 候选 Schema

见 SPEC-03-014 §3.1 精确字段级契约。DESIGN-03-007 §5.3.1 提供字段草稿，SPEC 做最终定义。

#### 5.1.4 External Fallback 链

```python
# 假设：AKShare 是唯一可能的实时数据源；无其他 Provider 提供板块快照
"sector.snapshot": ["akshare"],   # [假设] 仅 AKShare，无 fallback
"sector.ranking": ["akshare"],    # [假设] 同上
```

#### 5.1.5 公共能力级契约

`SectorSnapshot` 的唯一键为 `{market, sector_code, snapshot_date}`（SPEC-03-014 §4.bis.1 / DESIGN-03-014 §3.1）。同一唯一键的重复写入通过 upsert（`update_one` with `$set`）覆盖，不保留历史版本。`SectorSnapshot` 不包含 `schema_version`、`quality_flags` 或 `source_record_id` 字段（DESIGN-03-014 §6.3 裁定不纳入）。可追溯字段仅 `provider` 与 `fetched_at`。

| 维度 | `sector.snapshot` | `sector.ranking` |
|------|-------------------|-------------------|
| **Capability** | `sector.snapshot` | `sector.ranking` |
| **请求参数** | `security_id`（含 market + sector_code 或等价）、`date`（可选，默认最近交易日） | `date`（可选，默认最近交易日）、`sector_type`（可选，默认全部）、`limit`（默认 20） |
| **返回 DataResult.data 类型** | `SectorSnapshot`（单条） | `list[SectorSnapshot]` |
| **空返回语义** | Provider 返回空 DataFrame → `DataResult.success(data=None/is_empty, provider="akshare")`；`source_trace` 不含 `"ud_materialized(ok)"` 或 `"cache(ok)"`（允许 `"ud_materialized(skipped: ...)"`、`"cache(miss)"`） | Provider 返回空 DataFrame → `DataResult.success(data=[], provider="akshare")`；`source_trace` 不含 `"ud_materialized(ok)"` 或 `"cache(ok)"`（允许 `"ud_materialized(skipped: ...)"`、`"cache(miss)"`） |
| **错误语义** | Provider fetch 失败 → `DataResult.error(provider="error", source_trace=["akshare(error: ...)"])` | 同上 |
| **freshness 语义** | query 路径 Step 4 成功 → `freshness="delayed"`（未物化）；物化命中 → `freshness="cached"` | query 路径 Step 4 成功 → `freshness="delayed"`；物化命中 → `freshness="cached"` |
| **查询只读保证** | Zero-Persistence-Write：query 路径不写入物化集合、不写入 Cache、不写入 AuditLogger（SPEC-03-014 §14.5 / DESIGN-03-014 §2.1） | 同上 |
| **source_trace 约束** | query 路径的 `source_trace` 不包含 `"ud_materialized(ok)"` 或 `"cache(ok)"` 条目（允许 `ud_materialized(skipped: ...)`、`cache(miss)`；SPEC-03-014 A-021） | 同上 |
| **TA-CN 覆盖** | ❌ 注册于 `_TA_CN_NOT_COVERED`—不走 TA-CN Step 1（DESIGN-03-014 §4.3） | ❌ 同上 |

**唯一键覆盖规则**：`{market, sector_code, snapshot_date}` 唯一键的后续写入通过 upsert 完整覆盖先前记录，不保留历史版本。如需版本跟踪属 Phase 5+（SPEC-03-014 §4.bis.1 / DESIGN-03-014 §6.1）。

**测试契约**：stub 等价性测试必须断言 `stub_columns.STUB_COLUMNS["sector.snapshot"]` 与 `providers.__init__` 中的孪生定义完全等价（DESIGN-03-014 §4.1 STUB_COLUMNS 双定义约束）。fixture 覆盖 industry + concept 两种板块类型以及正常交易日 + 极端行情两种场景（SPEC-03-014 §8.2）。

### 5.2 P3-B：个股资金流

#### 5.2.1 业务语义

个股级别资金流向数据：主力净流入（大单/超大单/中单/小单）、北向资金、融资融券余额。消费方通过 `flow.capital_flow_daily`（个股日资金流）和 `flow.northbound_daily`（个股北向资金——仅沪/深港通标的，非市场汇总）访问。

<!-- 假设：AKShare 东方财富个股资金流接口可覆盖沪深两市全量标的；待 T3 实施阶段验证 -->

#### 5.2.2 数据维度

| 维度 | 取值 |
|---|---|
| 市场 | CN（A 股） |
| 时间粒度 | 日级（每个交易日） |
| 标的 | 个股（沪深两市），`symbol` + `market` + `trade_date` 构成必需查询维度 |
| 资金分类 | 主力/超大单/大单/中单/小单、北向（个股级）、融资融券 |

#### 5.2.3 候选 Schema

见 SPEC-03-014 §3.2 精确字段级契约。DESIGN-03-007 §5.3.4 提供字段草稿，SPEC 做最终定义。

#### 5.2.4 External Fallback 链

```python
# 假设：AKShare 是主要数据源；无其他免费 Provider 可覆盖相同字段
"flow.capital_flow_daily": ["akshare"],   # [假设]
"flow.northbound_daily": ["akshare"],     # [假设]
```

### 5.3 P3-C：市场情绪快照

#### 5.3.1 业务语义

全市场级别的情绪/温度快照：涨停/跌停家数、全市场上涨/下跌/平盘家数、市场温度、连板股票、热门概念、全市场成交额等。消费方通过 `sentiment.market_snapshot`（市场情绪快照）和 `sentiment.limit_up_pool`（涨停池）访问。

> **Pascal 裁定（2026-07-30）**：`MarketSentimentSnapshot` 采用 **22 字段全市场多维快照**作为 canonical 产品 schema。22 字段定义见 SPEC-03-014 §3.3。唯一键 `{market, snapshot_date, snapshot_time}`。该裁定**取代**此前离线 T3-B 实现的 10 字段 `sentiment_type` 聚合模型（`{market, sentiment_type, market_date}` 唯一键）。所有未来的实盘开发、持久化写入、Provider 映射必须以 22 字段 canonical 契约为准。离线存在的 10 字段实现保留为 superseded 事实，不得作为后续扩展的基础。

<!-- 假设：AKShare 东方财富涨停/跌停接口、大盘接口可覆盖所需字段；市场温度合成为派生值，由 domain service 在 Provider 原始数据上计算 -->

#### 5.3.2 数据维度

| 维度 | 取值 |
|---|---|
| 市场 | CN（A 股） |
| 时间粒度 | 日级（收盘后快照；后续可扩展为盘中多时间点） |
| 标的 | 全市场（不绑定个股） |

#### 5.3.3 Canonical Schema

见 SPEC-03-014 §3.3 精确 22 字段级契约。DESIGN-03-007 §5.3.2 提供字段草稿（已被 canonical 契约取代）。Pascal 裁定（2026-07-30）确认 22 字段全市场多维快照为产品 canonical schema，`{market, snapshot_date, snapshot_time}` 为唯一键。

#### 5.3.4 External Fallback 链

```python
"sentiment.market_snapshot": ["akshare"],  # [假设] 仅 AKShare
"sentiment.limit_up_pool": ["akshare"],    # [假设]
```

### 5.4 读写职责边界

<!-- 事实基线：DESIGN-03-007 §7.4 internal-first + §8.1 LocalMongoAdapter §5.1 命名空间隔离 -->

| 组件 | 读取职责 | 写入职责 |
|---|---|---|
| **DataRouter** | 解析 capability → fallback 链 → 按 internal-first 顺序执行步骤 1-4 | **不写**。Step 4 Provider fetch 成功后仅返回 `DataResult`，不触发物化写入或 Cache 写 |
| **UnifiedDataClient** | 暴露域方法：`get_sector_snapshot()` / `get_sector_ranking()` / `get_capital_flow()` / `get_northbound_flow()` / `get_market_sentiment()` / `get_limit_up_pool()` | **不直接写**；委托给 service 层的显式 refresh 方法（见下方） |
| **Domain Services（sector / flow / sentiment）** | 调用 adapter/Provider 获取原始数据 → 映射 canonical object → DataResult 封装 | **标准 query 路径不写**。仅显式调用的 `refresh_sector_snapshot()` / `refresh_capital_flow()` / `refresh_market_sentiment()` 方法才执行：Provider fetch → 写入 `03_data_ud_*` 物化集合 + CacheManager.put() |
| **Provider（AKShare）** | `fetch(domain, operation, sid, **params)` → 返回 pd.DataFrame | 不写（Provider 无状态） |
| **ETLV Refresh 路径** | 读取物化集合：LocalMongoAdapter | 写入物化集合：仅通过显式 refresh 方法（经 Pascal 授权，见 §6）|

**关键约束**：
- TA-CN adapter 不做 Phase 3 数据的读取——板块/资金流/情绪非 TA-CN 既有集合范围
- DSA 不作为运行时数据源——不实现 DSA adapter、不出现在 external_fallback_chains
- `03_data_ud_*` 物化集合通过 LocalMongoAdapter 读取（internal-first Step 2）
- [待验证] `sector.snapshot` 在 TA-CN Step 1 是否可借用 `index_daily_quotes` 部分数据——若可，则 SectorSnapshot 的主读路径是 TA-CN + LocalMongo，外部 Provider 仅作为补充
- **DataRouter.query() 全程只读**：Step 4 Provider fetch 成功后仅返回 `DataResult.success(data=..., provider="akshare")`，**不**写入物化集合、**不**写入 Cache。物化写入仅发生在**显式调用的 refresh 方法**中（如 `sector_service.refresh_sector_snapshot()`）

### 5.5 后续真实 Provider 待验证的事实状态

| # | 待验证事项 | 所属子阶段 | 验证方式 | 当前假设 |
|---|---|---|---|---|
| FV-1 | AKShare 东方财富板块接口是否支持按行业/概念/区域分类查询 | P3-A | T4 真实 Provider smoke | 假设支持 |
| FV-2 | AKShare 板块接口返回字段与 DESIGN 草稿 schema 的映射可行 | P3-A | T4 真实 Provider smoke | 假设可行 |
| FV-3 | AKShare 个股资金流接口是否覆盖沪深两市全部标的 | P3-B | T4 真实 Provider smoke | 假设覆盖 |
| FV-4 | AKShare 资金流数据中北向资金字段是否对于非沪/深港通标的返回空 | P3-B | T4 真实 Provider smoke | 假设部分标的空 |
| FV-5 | AKShare 涨停/跌停池接口的实时性与准确度 | P3-C | T4 真实 Provider smoke | 假设可用 |
| FV-6 | 市场温度指数合成所需的多个 AKShare 接口是否在同一个交易日内一致 | P3-C | T4 真实 Provider smoke | 假设一致 |
| FV-7 | AKShare 请求频率限制是否足以支撑全量标的一日内批量回填 | P3-B | T4 真实 Provider smoke（限速摸底） | 假设需限速 |
| FV-8 | `sector.snapshot` 数据是否可通过 TA-CN `index_daily_queries` 部分推导 | P3-A | T3 离线验证（非本阶段验证项） | 仅部分覆盖 |
| **FV-9** | 真实 MongoDB `tradingagents` 的连通性、认证方式、读写权限 | P3-A/B/C | T4 只读预检 Step 1 | 未知——需首次连通验证 |
| **FV-10** | AKShare 匿名 API 在运行时环境中是否可调用（无需 token） | P3-A/B/C | T4 真实 Provider smoke | 假设可调用——AKShare 无 token 要求，跳过 PR-0 密钥审计 |
| **FV-11** | AKShare 真实调用输出结构的字段名/类型与离线 fixture 假设的差异 | P3-A/B/C | T4 真实 Provider smoke | 假设差异存在——需映射修正 |
| **FV-12** | 生产 MongoDB 集合 `03_data_ud_*` 在首次 DDL Gate 之前是否存在（意外遗留） | P3-A/B/C | T4 只读预检 Step 2（集合清单检查） | 假设不存在 |

---

## 6. T4 生产就绪授权 Gate

<!-- 事实基线（V0.3 更新）：T3 离线实现（DESIGN-03-014 V0.6 + 工作树中未提交的 Phase 3 代码改动）已完成。当前阶段为 T4 生产就绪：在真实生产环境上执行零写入只读预检与真实 Provider Smoke，验证离线实现与实际环境的连通性、认证、权限和字段映射。 -->

### 6.1 阶段现状与范围

| 维度 | 值 |
|---|---|
| 已完成的阶段 | T1 RFC+SPEC（V0.2）、T2 Design（DESIGN-03-014 V0.6）、T3 离线实现（工作树） |
| 当前阶段 | **T4 生产就绪** |
| T4 包含 | ① 只读预检（§13.2）；② Secret source 证明（§13.3）；③ 真实 Provider Smoke（§13.4）；④ 结论聚合与 DDL Gate 提案 |
| T4 不包含 | 任何 MongoDB DDL/DML 写入、Cache/业务写入、cron/systemd、外部消息/webhook、`.env`/凭据写入或回显、依赖升级、Git commit |
| 授权原则 | 逐项授权、每项独立停止条件、失败即终、**不降级写入、不自动重试** |

### 6.2 T4 授权清单

| Gate ID | 授权内容 | 触发时机 | 影响范围 | 停止条件 | 涉及子阶段 | 执行人 |
|---|---|---|---|---|---|---|
| **PR-0** | **Secret source 审计**：逐候选文件证明 MongoDB 连接凭据（五组件键 `MONGODB_HOST`、`MONGODB_PORT`、`MONGODB_USERNAME`、`MONGODB_PASSWORD`、`MONGODB_DATABASE`，来自 **skills/.env**——复用 Phase 2 PortfolioMongoLoader 认证语义，组件式构造连接，非 URI）的文件存在、可被进程加载、全部五键声明且非空匹配。**不对 AKShare 做 secret/key 审计**——AKShare 为匿名无 token 数据源，PR-0 跳过 AKShare 密钥检查，PR-2/PR-3/PR-4 可直接执行匿名只读 smoke。**禁止输出值、长度、URI、用户名或全路径+键值组合** | T4 起始 | 文件存在性检查、运行时 env 探测（只读） | 候选文件不存在、任意一键缺失/空白、端口无效、数据库名不等于 `tradingagents` → 标记 MongoDB 为「NOT_AUTHORIZED」 | P3-A/B/C | Pascal 或 DevOps |
| **PR-1** | **MongoDB 只读连通预检**：使用 `pymongo.MongoClient` 连接 `tradingagents` 库，ping，列出所有集合（无 filter），验证无 `03_data_ud_market_sector_snapshot` / `03_data_ud_stock_capital_flow` / `03_data_ud_market_sentiment_snapshot` 集合。**不建集合、不读业务数据** | PR-0 pass | 网络 io（<1s）、MongoDB driver 加载 | 连接失败 / 认证拒绝 / 意外发现目标集合已存在 → 停止并记录 | P3-A/B/C | Dev/Agent |
| **PR-2** | **AKShare Provider smoke：`sector.snapshot` + `sector.ranking`** — 单板块代码（`BK0489`），≤3 个交易日窗口，AKShare 匿名只读调用并打印 DataResult key stats（数据量、字段名、前 5 行样例）。**不写入物化集合、不写入 Cache** | PR-1 pass（AKShare smoke 不依赖 PR-0 pass） | AKShare 库加载、API 调用 1-2 次、每小时配额 | API 返回错误 / 字段完全不匹配 / json 解析异常 → 停止；差异仅记录在字段映射报告中 | P3-A | Dev/Agent |
| **PR-3** | **AKShare Provider smoke：`flow.capital_flow_daily` + `flow.northbound_daily`** — 单标的（`600519` / `000001`），≤3 个交易日窗口，AKShare 匿名只读调用 | PR-1 pass（AKShare smoke 不依赖 PR-0 pass；可并行于 PR-2） | AKShare API 调用 2-4 次、每小时配额 | API 失败 / 空返回 / 北向字段缺失 → 停止并记录 | P3-B | Dev/Agent |
| **PR-4** | **AKShare Provider smoke：`sentiment.market_snapshot` + `sentiment.limit_up_pool`** — 单日期，AKShare 匿名只读调用 | PR-1 pass（AKShare smoke 不依赖 PR-0 pass；可并行于 PR-2/PR-3） | AKShare API 调用 2 次、每小时配额 | API 失败 / 核心字段缺失 → 停止并记录 | P3-C | Dev/Agent |
| **PR-DDL-P3A** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_market_sector_snapshot` + 索引** | PR-2 pass + Pascal 独立确认 | MongoDB 元数据写入——集合创建、索引构建 | 写权限不足 / 长时间索引重建 → 停止；schema 版本须与 SPEC-03-014 §3.1 最终版一致 | P3-A | Pascal 手动确认 |
| **PR-DDL-P3B** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_stock_capital_flow` + 索引** | PR-3 pass + Pascal 独立确认 | MongoDB 元数据写入 | 同上 | P3-B | Pascal 手动确认 |
| **PR-DDL-P3C** | **DDL Gate：创建 MongoDB 集合 `03_data_ud_market_sentiment_snapshot` + 索引** | PR-4 pass + Pascal 独立确认 | MongoDB 元数据写入 | 同上 | P3-C | Pascal 手动确认 |
| **PR-CANARY-P3x** | **手动 Canary**：一次 refresh 调用（手动触发，非 cron），写入对应集合，验证 DataResult 返回正常 | 对应 PR-DDL pass + Pascal 确认 | 真实 MongoDB 写入 | 写入失败 / 数据质量异常 → 停止不升级到 cron | P3-A/B/C | Pascal 手动执行 |

**关键约束**：
- PR-1（MongoDB 预检）**不读业务数据**——仅 ping + listCollections 命令。不得对 `stock_basic_info`、`market_quotes` 等 TA-CN 集合做查询。
- PR-2/PR-3/PR-4（Provider smoke）的输出必须**分别记录**连通性、认证、权限、字段映射四方面的观测结论。不得将一次调用结果泛化为全局结论。
- PR-DDL 系列与 PR-smoke 系列**完全解耦**——DDL 是非 PR-smoke 的前置要求，但 smoke 不需要 DDL 已完成。smoke 可先行验证 Provider 连通性，DDL 在 Pascal 确认 schema 最终版后才执行。
- PR-CANARY 系列与 PR-DDL 系列有依赖——先 DDL 才能写。但每个子阶段独立，P3-A 的 canary 不等待 P3-B 的 DDL。
- 同一子阶段的 gate 建议按 **PR-smoke → Pascal 审阅 smoke 结论 → PR-DDL → PR-CANARY** 顺序执行。
- **长期调度（cron/systemd）和 task_center Job 创建仍为独立授权，不在本 T4 范围。**

### 6.3 停止条件（任何一项触发即停止当前序列）

| 触发条件 | 对应 Gate | 后续动作 |
|---|---|---|
| Secret source 候选文件不存在 | PR-0 | 标记对应 Provider 为「NOT_AUTHORIZED」，不执行该 Provider 的 smoke |
| MongoDB 连接失败或认证拒绝 | PR-1 | 不执行 PR-2/PR-3/PR-4（全部需 MongoDB 连通） |
| 集合 `03_data_ud_*` 已意外存在 | PR-1 | 停止——记录集合存在情况，需 Pascal 判断是遗留还是意外 |
| AKShare API 返回错误（非 200 / 空 DataFrame / 解析异常） | PR-2/PR-3/PR-4 | 停止对应 Provider 的后续 smoke |
| 字段映射差异过大（>50% 字段名不匹配） | PR-2/PR-3/PR-4 | 停止——需重新调整 domain object schema 后重试 |
| DDL 写入无权限 | PR-DDL | 停止——需 Pascal 手动授予写权限或换连接串 |
| Canary 写入失败或数据质量异常 | PR-CANARY | 停止——不升级到定时采集 |

### 6.4 禁止绕过

- 不允许在 PR-1（MongoDB 预检）成功前执行 Provider smoke（如果 Provider smoke 需要 MongoDB 连接）。但如果 smoke 设计为纯内存验证（仅打印结果），可与 PR-1 并行——由执行人自主判断风险。
- 在 PR-0（Secret source 审计）通过前，不允许执行依赖密钥的 MongoDB 预检（PR-1）。AKShare Provider smoke（PR-2/PR-3/PR-4）为匿名调用，不依赖 PR-0 pass。
- 不允许跳过 PR-smoke 直接发起 PR-DDL。
- 不允许将 PR-smoke 的连通性结论泛化为「全量标的工作正常」——仅单标的+有限日期结论。
- 不允许将 mock/offline 结果表述为生产验证。
- 不允许在 PR 阶段执行 `refresh_xxx()` 或 `CacheManager.put()` 或 `P3PersistenceWriter.upsert()`。
- **不允许输出 secret 值、长度、URI、用户名或全路径+键值组合。**
- 不允许自动重试失败的 smoke——仅记录结论。

---

## 7. 测试策略

### 7.1 模块单元测试（colocated）

所有单元测试必须位于 `skills/data/unified_data/tests/` 下。根 `tests/` 不新增模块单元测试。

| 测试集 | 覆盖内容 | 子阶段 | 是否需网络 |
|---|---|---|---|
| `test_sector_snapshot.py` | SectorSnapshot canonical object 构造、from_dict()、边界值 | P3-A | 否 |
| `test_sector_service.py` | sector_service.get_sector_snapshot() / get_sector_ranking()（mock provider） | P3-A | 否 |
| `test_capital_flow.py` | CapitalFlowRecord canonical object 构造、资金流符号约定验证 | P3-B | 否 |
| `test_flow_service.py` | flow_service.get_capital_flow() / get_northbound_flow()（mock provider） | P3-B | 否 |
| `test_market_sentiment.py` | MarketSentimentSnapshot canonical object 构造、温度范围验证 | P3-C | 否 |
| `test_sentiment_service.py` | sentiment_service.get_market_snapshot() / get_limit_up_pool()（mock provider） | P3-C | 否 |

### 7.2 Fixture

Fixture 必须 colocated 在 `skills/data/unified_data/tests/fixtures/`。

| Fixture 文件 | 内容 | 子阶段 |
|---|---|---|
| `sector_fixtures.py` | 至少 2 条 SectorSnapshot mock 记录（industry + concept） | P3-A |
| `flow_fixtures.py` | 至少 2 条 CapitalFlowRecord mock 记录（含北向 + 不含北向两种情况） | P3-B |
| `sentiment_fixtures.py` | 至少 2 条 MarketSentimentSnapshot mock 记录（正常交易日 + 极端行情） | P3-C |

### 7.3 离线测试约束

- 仅 mongomock 或 fake provider（纯内存）
- 不做网络请求
- 不做 MongoDB 写入
- provider 返回 fixture 数据

### 7.4 生产 Smoke（T4 独立授权 Gate）

生产 smoke 测试（连接真实 AKShare API，可选连接真实 MongoDB）是 T4 生产就绪阶段的核心交付物，通过 T4 授权 Gate（§6.2：PR-2/PR-3/PR-4）独立授权。不在离线测试阶段执行。

Smoke 测试的详细规程见 §13.4。核心交付物为每 capability 的 smoke 报告，包含：连通性结论、认证状态、字段映射对照表、数据样例、与离线 fixture 的偏差列表。

---

## 8. 备选方案

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **A. P3-A/P3-B/P3-C 受控分期（选定）** | 风险隔离；每阶段可独立回滚；Pascal 逐项授权 | 总交付时间较长 | 符合受控分期原则 |
| **B. Phase 3 一次性部署全部三个集合** | 一次性交付完整 Phase 3 | 风险集中；一个集合的问题阻断全部；违反分期原则 | 拒绝。退回 |
| **C. 跳过板块快照，先做资金流和情绪** | 更直接满足策略和情绪需求 | 但板块/行业快照是资金流分析的上游依赖（板块资金流聚合） | 可作为 Pascal 备选顺序；P3-A 为推荐起始 |
| **D. 使用 data-pipeline ETL 写入而非 service 层直写** | ETL 管道已有写入验证；统一数据流 | 增加跨模块依赖；Phase 3 范围增加 | 留待 Phase 5 task_center 集成时评估 |

---

## 9. 验收标准

### 9.1 功能验收

- [ ] RFC-03-014 与 SPEC-03-014 两份独立文档，计划态且互相交叉引用
- [ ] 每份文档区分「已验证事实」「假设」「待验证」「Pascal 授权 Gate」
- [ ] 三阶段拆分方案（P3-A/P3-B/P3-C）明确定义，每阶段范围互不重叠
- [ ] 每个候选 collection 的文档级 schema 包含：业务语义、时间/市场/标的维度、source/provenance/quality 字段、候选唯一键、只读查询边界、禁止字段、保留/TTL 待决项
- [ ] P3-C MarketSentimentSnapshot 的 canonical 22 字段契约已确认（替代此前 10 字段离线 `sentiment_type` 聚合模型），且在所有三层文档中一致引用
- [ ] DataRouter / UnifiedDataClient / provider / ETLV 读写职责边界精确划分
- [ ] Pascal 授权 Gate 逐项定义，每项包含：动作、集合、样例、影响、停止条件
- [ ] 测试策略：colocated 路径、fixture 设计、离线约束

### 9.2 非功能验收

- [ ] 所有板块/情绪/资金流数据声明为「辅助研究数据，不构成交易指令或投资建议」。该声明通过静态 grep 验证——SPEC-03-014 中所有三份 domain object 的 docstring 均包含此准确措辞。
- [ ] Future provider 待验证事项（FV-1 ~ FV-12）明确列出
- [ ] `git diff --check` exit 0
- [ ] `git diff --name-status` 中本卡 diff 仅含目标 allowlist（一份 RFC）；共享 worktree 中非本路径的其他变更不视为本卡验收项

### 9.3 生产就绪验收（T4 新增）

- [ ] T4 授权 Gate（PR-0 ~ PR-4、PR-DDL-*）逐项定义，每项包含授权内容、触发时机、影响范围、停止条件、执行人
- [ ] Secret source 审计规程定义（§13.3）：逐候选文件可证明存在性 + 可加载性，禁止输出值/长度/URI/用户名
- [ ] 只读预检规程定义（§13.2）：MongoDB ping + 集合清单 + 零业务数据读取
- [ ] 真实 Provider Smoke 规程定义（§13.4）：单标的、≤3 交易日期窗口、零持久化写、输出结构独立记录
- [ ] 副作用矩阵定义（§13.1）：每个 T4 步骤的可能副作用、风险等级、缓解措施
- [ ] 停止条件定义（§6.3）：每 Gate 的独立停止条件、触发信号、后续动作
- [ ] DDL/DML 独立 Gate（PR-DDL-*）定义：与 PR-smoke 解耦、与 PR-CANARY 有依赖、需 Pascal 独立确认

---

## 10. 落地计划

### 10.1 阶段划分

| 阶段 | 阶段编号 | 产出 |
|---|---|---|
| T1 RFC+SPEC | RFC-03-014 + SPEC-03-014（V0.2） | 需求定义、分期方案、契约规范、规划态授权 Gate |
| T2 Design | DESIGN-03-014（V0.6，已完成） | 设计细节、文件清单、测试计划、P3PersistenceWriter 接口 |
| T3 Implement | 离线实现（工作树，已完成但未提交） | 代码实现：domain object、service、provider、adapter、test、fixture |
| **T4 生产就绪** | **本文档 V0.3** | **只读预检、Secret source 证明、真实 Provider Smoke、DDL/DML 独立 Gate** |
| T5 生产部署 | 后续阶段（非本 RFC 范围） | MongoDB DDL、canary、cron/systemd 授权 |
| T6 全量上线 | 后续阶段（非本 RFC 范围） | task_center Job 集成、全量标的数据填充 |

### 10.2 阶段状态表

| 阶段 | 状态 | 说明 |
|---|---|---|
| T1 RFC+SPEC | ✅ 已完成（V0.2） | 经独立 Review T1.4 APPROVE |
| T2 Design | ✅ 已完成（V0.6） | 经多轮 Design Correction（V0.1→V0.6） |
| T3 Implement | ⬜ 子阶段交付（分层状态，见下方） | 分层说明： |
| | ├─ P0：✅ Canonical 契约冻结 | 22 字段 canonical schema、fixture、stub Provider、孪生等价性、refresh 三态守卫 stub — 已冻结 |
| | └─ P1：✅ Fake-only Closeout（F1/F4/F5） | materialized read 代码路径（P3PersistenceWriter / refresh happy-path / Cache 写入）全部通过 mongomock 验证 Closeout。`limit_up_pool` 业务键 `{market, symbol, trade_date}` 与 `sentiment.market_snapshot` 键 `{market, snapshot_date, snapshot_time}` 分离验证通过。读路径 market 隔离（`_p3_filter_for()` 注入 market 参数）已验证 |
| | ⛔ P3-A/B/C real AKShare、real Mongo DDL/DML、real smoke、canary/cron：**尚未完成，需 Pascal 分项授权** |
| | ⛔ `flow.northbound_daily` refresh 维持 Pascal C fail-stop（永不进入 authorized 态） |
| **T4 生产就绪** | **⏸ 待 P1.5/P2 授权后恢复** | 真实 Provider smoke、MongoDB 预检、DDL/DML、canary — 所有 real I/O 步骤均未开始 |
| T5 生产部署 | ⏳ 待规划 | 需 T4 通过后 |
| T6 全量上线 | ⏳ 待规划 | 需 T5 通过后 |

### 10.3 T4 阶段执行路线

建议 T4 阶段按以下步骤执行：

1. **Secret source 审计**（PR-0）：逐候选文件验证存在性 + 可加载性，记录为「AUTHORIZED」或「NOT_AUTHORIZED」
2. **MongoDB 只读预检**（PR-1）：连接 → ping → listCollections → 确认无意外集合
3. **Provider smoke — sector**（PR-2）：单板块、≤3 日窗口，只读调用，记录连通性/字段映射/数据样例
4. **Provider smoke — flow**（PR-3）：单标的、≤3 日窗口，只读调用（可并行于 PR-2）
5. **Provider smoke — sentiment**（PR-4）：单日期，只读调用（可并行于 PR-2/PR-3）
6. **结论聚合**：汇总所有 smoke 结论 → 字段映射差异表 → DDL Gate 提案
7. **Pascal 审阅**：审阅 smoke 结论 → 确认 schema 最终版 → 授权 PR-DDL-*
8. **DDL 执行**（PR-DDL-*）：按子阶段逐项创建集合 + 索引
9. **手动 Canary**（PR-CANARY-*）：单次 refresh，验证写入 + 读取完整链路

---

## 11. 开放问题

- [ ] OQ-1：P3-A/P3-B/P3-C 的执行顺序是否接受推荐顺序（板块 → 资金流 → 情绪）？见 §4.2。
- [ ] OQ-2：`sector.snapshot` 是否可部分通过 TA-CN `index_daily_quotes` 推导，从而降低外部 Provider 依赖？见 §5.4 FV-8。
- [ ] OQ-3：Phase 3 的 AuditLogger 是否复用 Phase 2 的 `03_data_ud_query_audit` 集合？Phase 2 当前仅受控启用 AuditLogger，QualitySummary 冻结。
- [ ] OQ-4：资金流数据是否需要盘中快照（分钟级）？当前仅定义日级。
- [ ] OQ-5：`sector.snapshot` 的 `members` 字段（成分股列表）是否必要？如需要，会长宽规模和更新频率如何？
- [ ] **OQ-6（已同步 Pascal 裁定）**：`market_temperature` 合成公式？Pascal 确认该字段可保持为 `None`，不强制合成，禁止编造公式或虚假填充。留作 Domain Service 内部实现细节，后续可在 Provider 原始数据上派生（第 0 步：先确认 Provider 可用；第 1 步：定义合成公式）。
- [ ] **OQ-7（新增）**：T4 生产就绪 PR-smoke 的执行人是否由当前 Agent 承担，还是需 Pascal 手动执行？PR-2/PR-3/PR-4 标注为「Dev/Agent」，若 Agent 无真实网络/API 权限则降级为 Pascal 手动。
|- [x] **OQ-8（V0.6 更新）**：AKShare 无需 token（已确认为匿名数据源），OQ-8 已解决。PR-0 审计仅覆盖 MongoDB 的五组件键（`MONGODB_HOST`/`PORT`/`USERNAME`/`PASSWORD`/`DATABASE`），来源为 `skills/.env`。V0.4 中使用的 `MONGO_URI` 单键来源已 superseded——复用 Phase 2 PortfolioMongoLoader 组件式构造连接语义。
- [ ] **OQ-9（新增）**：Provider smoke 结论中字段映射差异的阈值如何设定？§6.3 提议 >50% 字段不匹配为停止条件——是否调整？

---

## 12. 参考资料

- DESIGN-03-007（Unified Data Layer 详细设计），§5.3 Phase 3 集合草稿、§7.4 Provider fallback 链、§8.1 internal-first 读取路径
- DESIGN-03-014（Phase 3 受控持久化扩展详细设计，V0.6）—— 离线实现的精确文件矩阵、数据流图、接口契约、P3PersistenceWriter 接口
- RFC-03-013（Phase 1E 情绪数据最小垂直切片）—— Phase 1E 个股情绪与 Phase 3 市场情绪的层级关系
- RFC-03-012（Phase 1D CN 日线真实外部 Provider 激活）—— 外部 Provider 激活模式参考
- RFC-03-011（Phase 2 质量与审计治理）—— AuditLogger / QualitySummary 治理框架
- SPEC-03-014（Phase 3 持久化扩展契约）—— 本 RFC 对应的 SPEC
- `skills/data/unified_data/SKILL.md`—— unified_data 模块入口

---

## 13. 生产就绪 Preflight & Smoke 详细规范（T4 新增）

### 13.1 副作用矩阵

每个 T4 步骤的可能副作用、风险等级与缓解措施：

| 步骤 | 动作 | 可能副作用 | 风险等级 | 缓解措施 |
|---|---|---|---|---|
| PR-0: Secret source 审计 | 检查文件是否存在；`os.environ.get("KEY")` | 无（仅只读探测） | 无风险 | 禁止输出值/长度/URI/用户名；仅记录「存在/不存在」「可加载/不可加载」 |
| PR-1: MongoDB 只读预检 | `MongoClient()` → `admin.command("ping")` → `list_collection_names()` | MongoDB 连接池建立；网络出站流量（~KB） | 低 | 不读业务数据；不建集合；连接超时 < 3s |
| PR-2: sector smoke | `akshare.stock_board_industry_cons_em("BK0489")` | AKShare 匿名 API 调用（1 次/调用）；网络流量（~KB） | 低 | 单代码限量；≤3 日窗口；零持久化写 |
| PR-3: flow smoke | `akshare.stock_individual_fund_flow()` | AKShare 匿名 API 调用（2-4 次）；网络流量（~MB） | 低-中（带宽） | 单标的限量；≤3 日窗口；限速 ≥1s/call |
| PR-4: sentiment smoke | `akshare.stock_zt_pool_em()` / `stock_market_fund_flow()` | AKShare 匿名 API 调用（2 次）；网络流量（~KB） | 低 | 单日期限量 |
| PR-DDL: 集合创建 | `db.create_collection()` + `create_indexes()` | MongoDB 元数据变更——不可逆（drop 可撤销但有代价） | **中**（元数据变更） | Pascal 独立确认；schema 版本与 SPEC 最终版一致；提供 `drop_collection()` 回滚脚本 |
| PR-CANARY: 手动写入 | `P3PersistenceWriter.upsert()` → 真实 MongoDB 写入 | 数据写入——可逆（delete_by_filter 可清理） | 中（数据写入） | 手动触发；单次执行；提供清理脚本；不自动重复 |

**核心原则**：PR-0 到 PR-4 的所有步骤设计为「零持久化副作用」——无集合/索引变更、无 MongoDB 写入、无 Cache 写入、无 cron/systemd 注册。任何步骤观察到异常停止条件时立即终止序列，**不降级为写入操作**。

### 13.2 MongoDB 只读预检规程

**适用 Gate**：PR-1

**步骤**：
1. 从受控 secret source（PR-0 已验证）加载 MongoDB 连接参数
2. 建立 `pymongo.MongoClient`（超时 3s）
3. 执行 `admin.command("ping")` → 记录连通性结论
4. 切换到 `tradingagents` 库 → 执行 `list_collection_names()` → 记录全量集合清单（不包含业务数据内容）
5. 逐一检查集合名中是否包含 `03_data_ud_market_sector_snapshot` / `03_data_ud_stock_capital_flow` / `03_data_ud_market_sentiment_snapshot`
6. **如果任一目标集合存在** → 停止 PR-1，记录该集合的创建元数据（`db[collection].options()`），标注为「UNEXPECTED_EXISTENCE」，需 Pascal 判断处理
7. **如果所有目标集合不存在** → PR-1 通过

**禁止事项**：
- ❌ 查询 `stock_basic_info`、`market_quotes`、`stock_daily_quotes` 等 TA-CN 业务集合的数据
- ❌ 创建或修改任何集合、索引、文档
- ❌ 读代替写（不将此行作为开始写入的借口）
- ❌ 在任意环节打印或记录连接串中的密码

**失败处理**：
- 连接失败 → 记录错误类型（DNS 解析/网络超时/认证拒绝），PR-1 失败。不自动重试
- 认证拒绝 → 区分「用户无权限」和「凭据错误」两种场景，分别记录在结论中
- list_collections 无权限 → 降低期望：仅验证可连接即可，集合检查改为「无法执行，需 Pascal 手动确认」

### 13.3 Secret Source 审计规程

**适用 Gate**：PR-0

**候选 Secret Source**（逐项检查，非穷举、不输出值）：

| 候选路径 | 检查内容 | 验证方法 | 结论 |
|---|---|---|---|---|
| `skills/.env` | 文件存在、可读 | `os.path.isfile() 且 os.access(R_OK)` | 存在/不存在/不可读 |
| `skills/.env` 五组件键 | 五个键均声明且非空——`MONGODB_HOST`、`MONGODB_PORT`、`MONGODB_USERNAME`、`MONGODB_PASSWORD`、`MONGODB_DATABASE` | `os.getenv("MONGODB_HOST")` 等逐一检查 | 全部已声明/缺失 N 个键 |
| Hermes 运行时 env | 五键声明 | `os.getenv(key)` 返回非 None | 已声明/未声明 |
| AKShare 匿名调用 | 无需密钥审计 | —（AKShare 为匿名数据源，无需 token） | 跳过 PR-0 |

**约束**：
- 每条检查仅输出结论（存在/不存在/可加载/不可加载 + 键声明存在/缺失）
- **绝对禁止**：输出值、长度、URI（含 `mongodb://...`、`https://...`）、用户名、全路径+键值组合
- 每个候选 source 独立记录，不归并、不默认降级
- MongoDB skills/.env 五组件键候选 source 全部不存在或键缺失 → 标记 MongoDB 为「NOT_AUTHORIZED」，PR-1（MongoDB 预检）不执行
- AKShare 跳过 PR-0 检查——PR-2/PR-3/PR-4 可独立于 PR-0 直接执行匿名只读 smoke
- PR-0 审计结果由 Pascal 审阅确认后进入 PR-1

### 13.4 真实 Provider Smoke 规程

**适用 Gate**：PR-2（sector）、PR-3（flow）、PR-4（sentiment）

#### 13.4.1 通用规则

| 维度 | 约束 |
|---|---|
| 范围 | 子阶段对应的 capability 各选一（共 6 个 capability） |
| 标的选择 | sector: 单板块代码（推荐 `BK0489`「行业板块」）；flow: 单标的（推荐 `600519` 沪市 + `000001` 深市）；sentiment: 单日期 |
| 日期窗口 | ≤3 个交易日（推荐最近一个完整交易日 + 前两个交易日） |
| 写入 | **零写入**：不写物化集合、不写 Cache、不写 AuditLogger。仅打印/记录到本地文件 |
| API 调用次数 | 每 capability ≤3 次（单标的 × 单日期 × 重试 0 次）。仅成功调用 1 次 + 异常不自动重试 |
| 输出 | 每个 smoke 调用输出一个「capability smoke 报告」（见 §13.4.2） |
| 并行 | PR-2/PR-3/PR-4 相互独立，可并行执行 |

#### 13.4.2 Smoke 报告模板

每 capability 的 smoke 结果必须独立记录为结构化报告，包含：

```yaml
capability: sector.snapshot              # capability 名称
provider: akshare                        # Provider 名
smoke_at: 2026-07-22T03:30:00+08:00      # 实际执行时间（ISO 8601）
stock/代码: BK0489                        # 测试标的
date_range: [2026-07-20, 2026-07-22]     # 请求日期窗口
---
connectivity:
  status: success | failed               # API 连通性结论
  latency_ms: 1234                        # 响应延迟（ms）
  error: null | str                      # 失败时的错误信息
auth:
  status: authorized | unauthorized      # 认证状态
  error: null | str
permissions:
  status: ok | restricted               # 权限状态（是否返回预期数据）
  note: null | str
field_mapping:
  total_expected_fields: 19              # SPEC 定义的字段数
  matched_fields: 18                     # 实际接口返回的匹配字段数
  missing_fields: [field_a, field_b]     # SPEC 有但实际无的字段
  extra_fields: [field_x]                # 实际有但 SPEC 无的字段
  unmatched_types: [field_c → str vs int] # 类型不匹配的字段
data_sample:
  row_count: 15                          # 返回记录数
  sample_rows: 5                         # 前 5 行样例打印
  null_ratio: 0.03                       # 空值占比
vs_fixture:
  deviations:                            # 与离线 fixture 的偏差
    - field: update_date
      fixture_type: str
      actual_type: datetime
      impact: low                        # 偏差影响评估（low/medium/high）
overall:
  verdict: pass | conditional_pass | fail  # 总体评估
  memo: |                               # 自由文本备注
    Sector snapshot data returned successfully.
    Field mapping is 95% compatible with SPEC.
    Remapping needed for: update_date (type change).
```

#### 13.4.3 记录存储

- 所有 smoke 报告写入本地文件（`docs/rfc/03_data/smoke_reports/` 目录），按 capability 命名：`smoke_sector_snapshot_20260722.yaml`
- **不允许写入 MongoDB 或任何持久化存储**
- 报告最终作为附件提供给 Pascal 审阅

#### 13.4.4 失败与偏差处理

| 场景 | 处理 |
|---|---|
| API 返回非 200 或空 DataFrame | 记录错误 → 该 capability 标记为 fail → 停止该子阶段的后续 smoke |
| 认证拒绝（401/403） | 记录错误 → 标记 auth 为 unauthorized → 停止全部 smoke，回查 PR-0 |
| 字段映射完全匹配（≥90% 字段名+类型匹配） | pass → 可直接进入 DDL Gate |
| 字段映射部分匹配（70%-90%） | conditional_pass → 需 Pascal 审阅偏差后决定是否授权 DDL |
| 字段映射匹配度低（<70%） | fail → 停止 → 需更新 domain object schema 后重做 smoke |
| 限流（429） | 记录限流信息 → 标记为 rate_limited → 等待 ≥60s → **不自动重试**（留给 Pascal 判断） |
| 网络超时 | 记录超时 → 标记为 timeout → 不自动重试 |

### 13.4.5 B2 单次只读 smoke 实测映射证据冻结（V0.10 新增）

> **权威引用**：本节为 RFC 层的动机与边界冻结。可执行契约的权威定义在 **SPEC-03-014 §14.4.5（V0.9）**；工具链与映射模式的权威设计定义在 **DESIGN-03-014 §15.x（V0.16）**。如本节与 SPEC/DESIGN 出现差异，以 SPEC/DESIGN 为准。

#### 13.4.5.1 冻结证据来源

| 证据 | 路径 | 性质 |
|---|---|---|
| PR-2 sector smoke 报告 | `/tmp/yquant-b2-pr234-20260726/pr2/smoke-sector-20260726.yaml` | 只读副本，不可移动/提交，不可重跑 |
| PR-3 flow smoke 报告 | `/tmp/yquant-b2-pr234-20260726/pr3/smoke-flow-20260726.yaml` | 同上 |
| PR-4 sentiment smoke 报告 | `/tmp/yquant-b2-pr234-20260726/pr4/smoke-sentiment-20260726.yaml` | 同上 |

**执行约束（本阶段冻结，不得违反）**：
- 本阶段为 Full Flow T1（仅 RFC+SPEC），**不重跑任何 live-read**。本次 B2 已用尽单次 live-read 预算。
- 真实报告仅在 `/tmp/yquant-b2-pr234-20260726/`，只可读取作为映射修正依据，**不得移动、提交、复制到仓库**。
| T2 Design / T3 Implement 阶段的映射修复必须基于本次冻结证据 + AKShare 公开文档 + 离线 fixture，**不得**以「需要再验证」为由重跑 live-read。

#### 13.4.5.8 B2 全 capability 映射裁决总表（本卡明确冻结）

每项 capability 必须有一个明确的三态裁决：**可真实映射（real-mappable）** / **保持线下 stub（offline stub）** / **明确 fail-stop**。不得使用「后续验证」掩盖 B2 冻结事实。

| Capability | B2 实测状态 | AKShareProvider 注册状态 | 映射裁决 | 依据 |
|---|---|---|---|---|
| `sector.snapshot` | SSL 失败（SSLError） | ✅ 已注册（P3-A stub） | **offline stub** — 预期字段集已基于公开文档推断，标注「未 live-read 验证」；仅允许后续单变量网络诊断后重试 live-read | §13.4.5.4 PR-2 |
| `sector.ranking` | SSL 失败（同 endpoint） | ✅ 已注册（P3-A stub） | **offline stub** — 同 sector.snapshot | §13.4.5.4 |
| `flow.capital_flow_daily` | 成功（`stock_individual_fund_flow`，3 次调用均 success） | ❌ 未注册 | **real-mappable** — B2 已验证 endpoint 返回数据；T2/T3 须基于 B2 证据和公开文档定义 expected 字段映射 | §13.4.5.2 PR-3 |
| `flow.northbound_daily` | success 但语义不匹配（持股历史≠净流入） | ❌ 未注册 | **fail-stop（Pascal C）** — capability 保留但 fetch 路径不指向真实 endpoint，`northbound_net_inflow` 恒 None；持股历史仅作辅助参考 | §13.4.5.2 Pascal C |
| `sentiment.market_snapshot` | success 但空返回（row_count=0） | ❌ 未注册 | **offline stub** — 空返回 verdict=fail（X2 保守）；须在交易日的独立 live-read 复验后方可进入 real-mappable | §13.4.5.3 Pascal X2 |
| `sentiment.limit_up_pool` | success 但空返回（row_count=0） | ❌ 未注册 | **offline stub** — 同 market_snapshot | §13.4.5.3 |

**裁决约束**：
- **禁止**将 fail-stop 或 offline stub 的 capability 通过别名/伪装变为 real-mappable。
- **禁止**在未获 Pascal 明确授权前修改裁决（例如将 `flow.northbound_daily` 从 fail-stop 改为 real-mappable）。
- Offline stub 的 capability 可以且应当在 T2/T3 中定义 expected 字段集和 fixture，但**不得**在 Provider 中注册为真实调用路径。

#### 13.4.5.9 Refresh 授权前状态机（B2 冻结）

`refresh_xxx()` 方法在对应 Gate 授权前的行为定义为**「授权前状态机」**，须在三层文档中统一冻结：

| 状态 | 条件 | 行为 | 信令类型 |
|---|---|---|---|
| **未授权（unauthorized）** | `p3_writer=None`（未注入） | `refresh_xxx()` 抛出 `ProviderUnavailableError`，不执行 Provider fetch、不写物化 | 异常（caller 可捕获） |
| **已注入但未实现（injected-not-implemented）** | `p3_writer` 已注入但 refresh happy-path 尚未实现 | `refresh_xxx()` 抛出 `NotImplementedError`，显式声明本阶段不执行写入 | 异常（caller 可捕获） |
| **已授权可写入（authorized）** | Gate 授权后 `p3_writer` 已注入 + refresh 完整实现 | Provider fetch → upsert → 返回 `PersistenceResult` | 正常返回 |

**执行约束**：
- P3-A sector.offline stub：refresh 路径始终在「未授权」或「已注入但未实现」状态——不可在 SSL 诊断未通过前进入「已授权可写入」。
- P3-B `flow.capital_flow_daily`（real-mappable）：refresh 路径可在 T3 实现为「已注入但未实现」或「已授权可写入」，取决于 T3 范围是否包含 refresh 完整实现。
- P3-B `flow.northbound_daily`（fail-stop/C）：refresh 路径**不得**进入「已授权可写入」——`northbound_net_inflow` 恒 None，无数据可写。
- P3-C sentiment（offline stub）：refresh 路径保持在「已注入但未实现」状态直到交易日 live-read 复验。

**零写入边界（B2 冻结，T2/T3 须继承）**：同上 §13.4.5.5。refresh 授权前状态机的所有「未授权」和「未实现」路径均不得执行 Provider fetch 或物化写入。

#### 13.4.5.10 既有实现与冻结契约的冲突清单（本轮修正）

下列冲突由 `git diff --stat` + 代码基线 grep 在 R0 阶段确认。三层文档在此 §13.4.5.10 冻结冲突判定与 developer 修正指令；developer 负责按 SPEC §14.4.5.11 的精确坐标完成代码修复。

##### 冲突 A：`flow_stub.py` 默认 payload 含非 None northbound 字段

| 维度 | 冻结契约要求 | 当前实现 | 冲突 |
|------|------------|---------|------|
| `_build_default_payload()` Record A（600519） | `northbound_*` 恒 None（Pascal C） | `northbound_net_inflow: 250_000.0`, `hold_shares: 9_500_000.0`, `hold_ratio: 7.55` | ❌ 三字段均非 None |
| Record C（000001） | 同上 | 同上（480_000.0 / 4_750_000.0 / 4.2） | ❌ 三字段均非 None |

**根因**：T3-P3B 实现早于 Pascal C 决策。stub fixture 仍反映原始的「沪港通标的填充 northbound」语义。

**修正指令**：Record A 和 C 的 `northbound_net_inflow` / `northbound_hold_shares` / `northbound_hold_ratio` 全部改为 `None`。Record A 的 docstring 行「full bands + northbound + margin populated」改为「full bands + None NB + margin populated」。Record B/D 的 None NB 不变。speculative 字段名称（`northbound_net_inflow` / `northbound_hold_shares` / `northbound_hold_ratio`）保留在 dict key 中（让不关心 northbound 的调用方不受影响），仅值变 None。

##### 冲突 B：`flow_service.py` refresh_capital_flow() 在未授权状态下执行 fetch→upsert

| 维度 | 冻结契约要求 | 当前实现 | 冲突 |
|------|------------|---------|------|
| `p3_writer is not None` 时的 refresh 行为 | `NotImplementedError`（injected-not-implemented） | 直接 fetch→upsert（happy-path） | ❌ 跳过授权前状态机 |
| `northbound_daily` refresh 行为 | `NotImplementedError`（fail-stop 不得进入已授权可写入） | 同一 refresh 方法通过 `self.capability` 固定指向 `flow.capital_flow_daily`，不区分 northbound | ❌ 未提供 northbound 专用的 fail path |

**根因**：T3-P3B 实现了完整的 refresh happy-path 并选择 `p3_writer is not None` 作为守卫，而非授权前状态机三态。

**修正指令**：
- `refresh_capital_flow()` 在 `p3_writer is None` 时保持 `ProviderUnavailableError`（未授权，正确）
- 新增 `_p3_writer is not None and not self._refresh_authorized()` 守卫 → 抛 `NotImplementedError`（已注入但未实现）
- `_refresh_authorized()` 默认返回 `False`（保持未授权），由后续 G-B-2 Gate 授权后改为 `True`
- `northbound_daily` 的 refresh 路径（本卡暂不实现）：在 `FlowService` 中新增显式的 fail path，行为与 unauthorized 一致

##### 冲突 C：`flow.py` / `flow_service.py` 文档字符串仍允许 northbound 字段填充

`CapitalFlowRecord` 的 docstring（`models/domain/flow.py` 第 23-24 行）称 northbound 字段「仅沪/深港通标的」可填充；`FlowService.get_northbound_flow()` 的 docstring（`flow_service.py` 第 256-260 行）仍描述 northbound 字段由 Provider 填充。

**修正指令**：两处 docstring 均须标注「Pascal C: Phase 3 内 `northbound_*` 恒 None。此字段保留类型签名但当前永不填充非 None 值。」

##### 冲突 D：`flow_stub.py` 的 StubFlowProvider 为 `flow.northbound_daily` 返回含非 None northbound 的 payload

`StubFlowProvider.fetch()` 不区分 capability——对 `flow.capital_flow_daily` 和 `flow.northbound_daily` 返回同一 `_payload`。当 router 或 service 查询 `flow.northbound_daily` 时，stub 返回与 capital_flow_daily 相同的记录（含非 None northbound 值）。

**修正指令**：`StubFlowProvider.fetch()` 在 `operation == "northbound_daily"` 时对返回的每个 dict 执行 northbound field → None 过滤（类似 `CapitalFlowRecord.from_northbound_dict` 的投影逻辑），使 stub 行为与查询语义一致。

##### Developer allowlist（本卡最终冻结）

| 路径 | 允许操作 | 约束 |
|------|---------|------|
| `providers/flow_stub.py` | `_build_default_payload()` 中 Record A 和 C `northbound_*` → None；`StubFlowProvider.fetch()` northbound daily 投影过滤；docstring 更新 | 不得改其他 default payload 字段、不得改 `StubFlowProvider` 的 capability 声明、不得改 markets |
| `services/flow_service.py` | 新增 `_refresh_authorized()` 守卫 + `NotImplementedError` 路径；`refresh_capital_flow()` 调用它；`get_northbound_flow()` / 类 docstring 更新 | 不得改 read path（`get_capital_flow`/`get_northbound_flow`）、不得改 `PersistenceResult`、不得改 `_fetch_for_refresh()` |
| `models/domain/flow.py` | `CapitalFlowRecord` docstring 注释更新 | 不得改 dataclass 字段定义、不得改 `from_dict`/`from_northbound_dict`/`to_canonical` |
| 对应的 P3-B fixture / test 文件 | 更新 northbound 字段期望值以匹配恒 None | 不得改非 northbound 字段的测试逻辑 |

**禁止修改路径**：`providers/__init__.py`、`router.py`、`client.py`、`adapters/`、`models/__init__.py`、`models/domain/__init__.py`、`services/__init__.py`、`tests/` 非 P3-B fixture 文件、任何非 P3-B 文件、任何 `.env` / 配置 / 依赖文件。

##### 下层代码验收标准（3 项必测）

1. **Northbound 恒 None 验证**：注册 `StubFlowProvider` → query `flow.northbound_daily` → `DataResult.data` 中每条的 `northbound_net_inflow` / `northbound_hold_shares` / `northbound_hold_ratio` 均为 `None`。query `flow.capital_flow_daily` → 非 northbound 字段正常填充，`northbound_*` 仍可为 None（取决于 source dict）。

2. **Refresh 授权前状态验证**：`FlowService(p3_writer=mock_writer)` → `refresh_capital_flow()` → 抛 `NotImplementedError`（不 fetch、不 upsert）。`FlowService(p3_writer=None)` → 抛 `ProviderUnavailableError`。上述两个测试均不向 `mock_writer` 写入任何记录。

3. **Southbound query 不受影响**：query `flow.capital_flow_daily` 的 `main_net_inflow` / `super_large_net_inflow` 等非 northbound 字段保持原有填充行为。`from_dict` / `from_northbound_dict` 工厂方法不受影响。

**最小 pytest 命令**（从 `PIPELINE_WORKSPACE` 根目录执行）：
```bash
PYTHONPATH=. python -m pytest tests/data/unified_data/ \
  -k "northbound or refresh_capital_flow or capital_flow" \
  -q --tb=short 2>&1 | tail -20
```

#### 13.4.5.2 PR-3 flow.northbound_daily 语义不匹配（关键阻断）

**冻结事实**：
- 调用 endpoint：`akshare.stock_hsgt_individual_em(symbol='600519')`
- 网络层：success（~1131ms），auth=authorized，permissions=ok
- 实际返回 5 行样本（2017-03-16..2017-03-22），实际字段 9 个：
  `持股日期` / `当日收盘价` / `当日涨跌幅` / `持股数量` / `持股市值` / `持股数量占A股百分比` / `今日增持股数` / `今日增持资金` / `今日持股市值变化`
- 现有 expected 列（脚本中）：`date` / `stock` / `northbound_net_inflow` + 8 个资金流字段 = 11 个，matched 0/11，missing=`date` / `stock` / `northbound_net_inflow`。

**语义判定**：该 endpoint 返回的是**北向持股历史（holding history）**，**不是**北向净流入（net inflow）。两者业务语义不同：
- 持股历史：某标的每日的北向持股数量、持股市值、占比、日增减——回答「北向持有多少」。
- 净流入：某标的每日的北向买卖差额——回答「北向今天净买了多少」。

**禁止伪装（硬约束）**：
- 严禁在 T2 Design / T3 Implement 中将 `持股数量` / `持股市值` / `今日增持资金` 等字段别名映射为 `northbound_net_inflow`。
- 严禁在 `CapitalFlowRecord.northbound_net_inflow` 字段中静默填入持股语义的值。
- 严禁在 smoke 报告 / domain object / mapping 文档中把「北向持股历史」表述为「北向净流入」。

**Pascal 决策（2026-07-26）：选 C — 放弃净流入，保留字段占位**

Pascal 已明确选择 **C**：当前 Phase 3 不提供北向净流入数据，`northbound_net_inflow` 字段保持 None，持股历史作为辅助保留。选项 A（分流到正确 endpoint）与选项 B（变更 capability 语义为持股历史）均**未被选择**，本 Phase 3 范围内不执行。

| 选项 | 含义 | 影响 | 状态 |
|---|---|---|---|
| A. 分流到正确 endpoint | 在 AKShare 中寻找真正返回北向净流入的 endpoint（如 `stock_hsgt_fund_flow_summary_sina` / `stock_em_hsgt_north_net_flow_in` 等候选），将 `flow.northbound_daily` 的 fetch 路径指向它；持股历史 endpoint 另立 capability 或丢弃 | 需 T2 在 DESIGN §4.2 / §15.6 重新定义 endpoint 映射；可能需新增 capability（超出本卡范围，需 Pascal 确认） | **未选（Pascal 2026-07-26 明确放弃）** |
| B. 变更 capability 语义 | 将 `flow.northbound_daily` 的语义从「北向净流入」改为「北向持股历史」，对应调整 SPEC §3.2 `CapitalFlowRecord` 的 `northbound_*` 字段定义 | 需回头修订 SPEC §3.2（本卡允许，但须 Pascal 确认）；影响下游消费方契约 | **未选（Pascal 2026-07-26 明确放弃）** |
| **C. Pascal 确认放弃净流入（已选）** | 当前 Phase 3 范围内不提供北向净流入数据，`northbound_net_inflow` 字段保持 None，仅保留持股历史作为辅助 | 最小改动；接受能力缺口 | **✅ Pascal 2026-07-26 已确认选择** |

**C 选项落地约束（硬约束，T2/T3 须遵守）**：
- `flow.northbound_daily` capability **保留**（不从 §3 domain object 或 capability registry 中移除），但其 fetch 路径在当前 Phase 3 **不指向任何真实 endpoint**——`northbound_net_inflow` 恒为 None。
- `CapitalFlowRecord.northbound_net_inflow`（SPEC §3.2）字段定义**不变**（仍为 `float | None = None`），只是当前 Phase 3 永不填充非 None 值。
- 持股历史（B2 返回的 9 个持股字段）作为**辅助参考**，T2/T3 可在 DESIGN 工具链中以参考字段标注，但**不得**将其映射入 `northbound_net_inflow` 或任何 `*_net_inflow` 字段（禁止伪装约束仍然生效）。
- 不引入新 endpoint、新 capability、新 endpoint skeleton（A 选项的候选 endpoint 不在当前 Phase 3 范围）。

#### 13.4.5.3 PR-4 sentiment 空返回语义区分

**冻结事实**：
- 调用 endpoint：`akshare.stock_market_fund_flow()` + `akshare.stock_zt_pool_em(date)`
- 网络层：success（~1525ms），auth=authorized，permissions=ok
- row_count=0，actual_fields=0，matched 0/31，missing=[]（因 actual 为空，无法计算 missing）

**Pascal 决策（2026-07-26）：选 X2 — 空返回语义收敛为保守 fail，移除 empty_semantics 分类**

空返回维持 verdict=fail（保守）。原三分类（无交易日/schema drift/调用异常）的 `empty_semantics` reporter 字段在 X2 下**移除**——reporter 不再输出 `empty_semantics` 分类字段，空返回仅在 memo 中记录观测事实。

| B2 观测事实 | X2 下的 verdict |
|---|---|
| row_count=0 且 actual_fields=0（本次 B2 即此） | **fail**（保守，不进一步细分原因） |
| endpoint 抛异常、返回非 DataFrame、JSON 解析失败 | **fail**（停止该子阶段；记录异常类；不自动重试） |

**本次 B2 判定（按 X2）**：verdict=fail（memo 记录 `matched_ratio=0.00 (0/31); missing=[]; row_count=0; actual_fields=0`）。后续独立 live-read（非本阶段）在交易日复验时，若返回非空数据则按正常字段匹配流程判定；reporter 不再负责区分「无交易日」与「schema drift」的空返回语义。

**X2 落地约束（硬约束，T2/T3 须遵守）**：
- reporter 账本**不输出** `empty_semantics` 字段。
- reporter 账本**不输出** `worktree_changed` 字段（原 X1 候选的 runtime git-worktree 探测被 X2 移除）。
- 空返回 verdict 一律 fail；不引入 verdict 篡改逻辑。
- PR-4 的 expected 字段集仍保留（基于公开文档推断），后续独立 live-read 复验时使用。

#### 13.4.5.4 PR-2 sector SSL 网络停止诊断边界

**冻结事实**：
- 调用 endpoint：`akshare.stock_board_industry_cons_em("BK0489")` ×2 次
- 两调用均 SSLError（`requests.exceptions`），connectivity=failed，latency=null
- auth=authorized（AKShare 匿名，无认证层），permissions=restricted
- verdict=fail，`endpoint_status=endpoint_unreachable`
- memo：「endpoint_unreachable: SSLError: requests.exceptions — egress restriction, not a code defect.」

**判定**：PR-2 的失败为**网络层 egress 限制**（SSL/TLS 握手失败或出口被阻断），**不是代码 defect**，也**不是** mapping 问题。

**边界（硬约束）**：
- 停止 PR-2（sector）子阶段的后续 smoke——不自动重试。
- 禁止将 PR-2 的 SSL 失败与 PR-3/PR-4 的 mapping 修复耦合——三者独立。
- 仅允许后续**单变量网络诊断**（如切换网络出口、验证 AKShare 上游可达性、检查 TLS 版本），且须 Pascal 独立授权，不在本 T1 阶段执行。
- PR-2 的 mapping 修复（expected 字段集）在 T2 须基于 AKShare 公开文档与离线 fixture 推断，**不得**以「需要 live-read 验证」为由阻塞 T2。

#### 13.4.5.5 单次 live-read 精确调用预算与零写入边界

**精确预算（本次 B2 已用尽）**：

| PR | endpoint | 本次实际调用 | 预算上限 | 剩余 |
|---|---|---|---|---|
| PR-2 | `stock_board_industry_cons_em` | 2（均 SSLError） | 2 | 0 |
| PR-3 | `stock_individual_fund_flow` ×2 + `stock_hsgt_individual_em` ×1 | 3（均成功） | 3 | 0 |
| PR-4 | `stock_market_fund_flow` + `stock_zt_pool_em` | 2（均成功但空） | 2 | 0 |

**零写入边界（本次 B2 已遵守，T2 须继承）**：
- 无重试：所有失败仅记录，不自动重试。
- 无 fallback：PR-2 SSL 失败后未切换到其他 endpoint 或 provider。
- 零 Mongo 写入：无集合/索引/文档变更。
- 零 Cache 写入：无 `CacheManager.put()`。
- 零 AuditLogger 写入：无 `03_data_ud_query_audit` 写入。
- 零 DDL：无 `createCollection` / `createIndex`。
- 零 cron/systemd 注册。

**T2 边界**：T2 Design / T3 Implement 不得引入上述任何写入；mapping 修复仅体现在 expected 字段集、endpoint 选择、reporter 账本字段与 fixture/test 中。

#### 13.4.5.6 T2 实现所需最小文件范围

T2 Design（task t_987fde34）须在以下最小范围内体现映射修正，**禁止无关重构**：

| 文件/文档 | 允许的修改 | 禁止的修改 |
|---|---|---|
| `docs/design/03_data/DESIGN-03-014-*.md` §4.2 | AKShare→Canonical 映射模式（endpoint 选择、字段 alias、单位、日期窗口） | domain object 字段定义（属 SPEC §3） |
| `docs/design/03_data/DESIGN-03-014-*.md` §15.x | 工具链：expected 字段集、endpoint 选择逻辑、reporter 账本字段（provider_attempts/实际调用数/retry_count/fallback_count/mongo_calls/write_operations） | DDL 契约（§6.4 系列）；`worktree_changed`/`empty_semantics` 字段（X2 已移除） |
| `scripts/t4_preflight/smoke_flow.py` | `_EXPECTED_FLOW_FIELDS` / `_EXPECTED_NORTHBOUND_FIELDS`、endpoint 选择（§13.4.5.2 C 已选，northbound 恒 None） | 测试框架结构 |
| `scripts/t4_preflight/smoke_sentiment.py` | `_EXPECTED_SENTIMENT_FIELDS` / `_EXPECTED_LIMIT_UP_FIELDS`（空返回 verdict=fail 保守） | 同上 |
| `scripts/t4_preflight/smoke_sector.py` | expected 字段集（基于公开文档推断） | 同上 |
| `scripts/t4_preflight/provider_client.py` | endpoint 选择、空返回保守 fail 标记 | client 安全边界（单次、限速、零写入） |
| `scripts/t4_preflight/reporter.py` / `models.py` | 账本字段（provider_attempts/实际调用数/retry_count/fallback_count/mongo_calls/write_operations） | 脱敏规则（§15.7.2）；`worktree_changed`/`empty_semantics` 字段（X2 已移除） |
| `skills/data/unified_data/tests/fixtures/*` | 对应 fixture 更新以反映真实字段 | fixture 框架 |
| 对应 `test_*.py` | 断言更新 | 测试覆盖范围缩减 |

**禁止修改**：
- SPEC-03-014 §3（domain object 字段定义）——Pascal 已选 C，不采用选项 B，§3 字段定义不变。
- SPEC/RFC 的 DDL 契约（§14.6.x / §6.4.x）。
- `docs/*template*`、生产代码、配置、secrets、Mongo/缓存/调度。

#### 13.4.5.7 T2 验收准则（本卡新增，供 T2 worker 遵循）

T2 Design 完成时须满足：
1. PR-3 `flow.northbound_daily` 按 §13.4.5.2 Pascal 已选的 **C**（northbound_net_inflow 恒 None，不指向真实 endpoint），且在 DESIGN §4.2 / §15.6 显式标注 C 已选与依据；不引入 A/B 选项的 endpoint skeleton。
2. PR-4 空返回语义按 §13.4.5.3 X2 收敛：reporter **不输出** `empty_semantics` 字段，空返回 verdict=fail（保守）。
3. PR-2 的 expected 字段集已基于公开文档推断更新，且明确标注「未 live-read 验证」。
4. 单次 live-read 预算与零写入边界在 DESIGN §15.x 中显式声明，且 T2 未重跑 live-read。
5. smoke 报告账本字段（provider_attempts/实际调用数/retry_count/fallback_count/mongo_calls/write_operations）已在 reporter 定义最小实现；**不包含** `worktree_changed` 与 `empty_semantics`（X2 已移除）。
6. 单元/fixture 测试、离线回归、静态零写入扫描、后续独立 live-read 的验证计划已定义（不在本阶段执行 live-read）。
7. PR-2 SSL 网络诊断仅允许后续单变量网络诊断，未混进 mapping 修复或自动重试。

---

### 13.5 Zero-Persistence-Write 保证

**DataRouter.query() for P3 capabilities** 全程零持久化写：

- Step 1（TA-CN adapter skip）：P3 capability 注册在 `_TA_CN_NOT_COVERED` → 直接跳过，零副作用
- Step 2（P3PersistenceWriter 读）：仅 `get()` 操作——零写
- Step 3（CacheManager 读）：仅 `get()` 操作——零写
- Step 4（外部 Provider fetch）：成功返回 `DataResult.success()`——**不触发 `_materialize()`**，不写 LocalMongoAdapter、不写 Cache、不写 AuditLogger
- 任何 `force_refresh` 参数在 P3 query 路径中均**不产生持久化副作用**——`force_refresh` 仅影响 FreshnessPolicy 判断，不改变写入行为

**显式 refresh 路径**（非 query，属独立 Gate）：
- `refresh_sector_snapshot()` / `refresh_capital_flow()` / `refresh_market_sentiment()` 仅在对应子阶段的 CANARY Gate 授权后执行
- CANARY 之前的任何 refresh 路径调用返回未授权错误，不执行 Provider fetch 和 MongoDB 写入

此保证由 DESIGN-03-014 V0.6 §2.1 读取路径不变形约束强制执行，在 T3 离线实现中通过 capability-level 的 `_materialize()` skip 实现。

### 13.6 DDL/DML 独立 Gate 细则

PR-DDL-* 系列 Gate 与 PR-smoke 系列 Gate 的设计关系：

```
PR-0 (Secret 审计) ──→ PR-1 (MongoDB 预检) ──→ PR-2/3/4 (Smoke)
                                                      │
                                                      ▼
                                              Pascal 审阅 Smoke 报告
                                                      │
                                              §13.4.4 判定 Verdict
                                                      │
                                           ┌──────────┴──────────┐
                                           ▼                     ▼
                                     PASS / CONDITIONAL    FAIL → 停止
                                           │
                                           ▼
                          Pascal 独立确认 schema 最终版
                                           │
                                           ▼
                                     PR-DDL-* (集合创建)
                                           │
                                           ▼
                                     PR-CANARY-* (手动写入)
```

**B1 冻结状态（2026-07-25）**：在上图 PR-DDL-* 节点中，**`PR-DDL-P3A`、`PR-DDL-P3B`、`PR-DDL-P3C` 三者均已冻结**——其 DDL 执行语义、rollback 脚本、audit 字段、失败矩阵、退出码的权威契约见 DESIGN-03-014 §6.4（P3-A，V0.15）/ §6.4.bis（P3-B，V0.15）/ §6.4.ter（P3-C，V0.15）与 SPEC-03-014 §14.6.4（P3-A，V0.8）/ §14.6.bis（P3-B，V0.8）/ §14.6.ter（P3-C，V0.8）。Phase 3 三子阶段 DDL 全部授权。本节既有 Gate 通用要求（1-5）与「DDL 执行人」条文不变。

**DDL Gate 授权要求**（全部满足）：

1. 该子阶段的 PR-smoke verdict 为 `pass` 或 `conditional_pass`（Pascal 已审阅偏差并确认可接受）
2. Pascal 已确认 SPEC-03-014 中对应 schema 的最终版本（包含 smoke 发现的字段映射修正）
3. 提供 `createCollection` + `createIndex` 的精确脚本（索引定义、TTL 策略、验证规则）
4. 提供对应的 `dropCollection` 回滚脚本（作为安全网）
5. Pascal 执行或明确授权执行 DDL

**DDL 执行人**：Pascal 手动执行（或 Pascal 授权的 DevOps）。Agent 不直接执行 DDL。

### 13.7 成功标准

T4 生产就绪阶段在以下全部条件满足时视为完成：

1. **PR-0 通过**：Secret source 逐候选文件审计完成，状态为「AUTHORIZED」
2. **PR-1 通过**：MongoDB 可连接、认证正常、目标集合不存在（或 Pascal 已确认意外存在的集合可接受）
3. **PR-2/PR-3/PR-4 至少通过一个子阶段**：对应的 Provider smoke 报告生成，verdict 为 pass 或 conditional_pass
4. **字段映射差异表**：每个 capability 的字段映射对照表已生成，未映射字段已标注
5. **Pascal 审阅完成**：Pascal 审阅所有 smoke 报告并确认是否可进入 DDL Gate
6. **DDL 提案**：针对通过 smoke 的子阶段，DDL Gate 提案已提交（含精确的集合创建脚本和索引定义）
7. **无未解决的阻断**：§6.3 停止条件表中无未关闭的事项

T4 阶段**不要求**所有三个子阶段同时通过 smoke——单子阶段通过的组合是合法的完成状态（如「P3-A 生产就绪 but P3-B/C 待后续」），取决于 Pascal 的判断。

---

## P0 真实 Provider 离线可实现契约冻结

### P0.1 背景与目标

Phase 3 离线实现（T3 Implement）已在工作树中存在并通过 `792 passed`。但离线实现与真实 Provider 之间存在三类缺口：

| 缺口类型 | 含义 | 涉及 capability |
|---|---|---|
| **A: 文档与代码不一致** | domain object schema、PROVIDER_STUB_COLUMNS、fixture 断言与离线实现之间的字段漂移 | sector.snapshot/ranking、flow.capital_flow_daily、sentiment.market_snapshot/limit_up_pool |
| **B: 真实 Provider 映射缺失** | 离线 stub 的 expected 字段集、endpoint 选择逻辑、映射模式未定义 | 全部六项 |
| **C: 持久化路径未实现** | real Mongo upsert、refresh 三态守卫、internal-first 读取路径 | 全部六项 |
| **D: 测试验证不足** | 端到端 smoke、数据合理性抽样、空返回语义测试 | sentiment、sector |

本 §P0 的唯一目标：**定义可在「不发起任何真实 API/Mongo 调用」前提下实施的真实 Provider 接入契约**。具体来说：

- 定义六 capability 的精确状态：offline 已验证、real Provider 未实现/未注册、real persistence 未执行、refresh 未实现、live smoke 未执行。
- 定义真实 Provider 统一接口边界：extract → canonical mapping → validation/provenance → `DataResult.source_trace`。
- 为每项 capability 冻结真实源映射的验收项、空返回/日期/排序/字段漂移错误语义。
- 明确 P0（本阶段离线实现）与 P1（真实 Mongo DDL/DML/internal-first read/refresh）及 P2（PR-0~PR-4 live smoke/canary）的边界与依赖。
- 写出完全副作用矩阵：本轮允许/禁止的操作及其授权模式。
- 将现有旧 checkbox 状态纠正为可审计现状。

**所有真实 API、MongoDB 调用均属于将来的单次授权 smoke（P2）或 production activation（后续阶段），绝不在 P0 离线 Implement/Verify 中触发。**

### P0.2 六 Capability 精确状态矩阵

| Capability | 离线已验证 | AKShareProvider 注册 | Real fetch 实现 | Real persistence 实现 | Refresh 实现 | Live smoke 执行 |
|---|---|---|---|---|---|---|
| `sector.snapshot` | ✅ stub fixture + 测试 PASS（B2 SSLError） | ✅ P3-A stub（注册，无真实调用路径） | ❌ 未实现（SSL 未诊断通过） | ❌ 未执行 | ❌ 未实现（三态 unauthorized） | ❌ B2 失败（SSLError） |
| `sector.ranking` | ✅ stub fixture + 测试 PASS | ✅ P3-A stub | ❌ 未实现 | ❌ 未执行 | ❌ 未实现 | ❌ B2 失败（同 endpoint） |
| `flow.capital_flow_daily` | ✅ stub fixture + 测试 PASS | ❌ 未注册（代码基线仅含 9 项 capability） | ❌ 未实现（B2 成功但 `_EXPECTED_FLOW_FIELDS` 未对齐） | ❌ 未执行 | ❌ 未实现（refresh 三态 injected-not-implemented） | ✅ B2 成功（`stock_individual_fund_flow`） |
| `flow.northbound_daily` | ✅ stub fixture + 测试 PASS | ❌ 未注册 | ❌ 未实现（Pascal C: 不指向真实 endpoint） | ❌ 未执行 | ❌ fail-stop（northbound 恒 None，永不写入） | ✅ B2 success 但语义不匹配（持股历史≠净流入） |
| `sentiment.market_snapshot` | ✅ 22-field canonical（from_dict/fixture/stub/test 已验证基线） | ❌ 未注册 | ❌ 未实现 | ❌ 未执行 | ❌ 未实现（三态 injected-not-implemented） | ❌ B2 空返回（row_count=0） |
| `sentiment.limit_up_pool` | ✅ 同 market_snapshot（22-field canonical 已验证基线） | ❌ 未注册 | ❌ 未实现 | ❌ 未执行 | ❌ 未实现 | ❌ B2 空返回（同 market_snapshot） |

**状态语义**：
- **离线已验证** = stub fixture 注入后 domain/service 层测试 PASS；
- **AKShareProvider 注册** = `akshare.py` 的 `providers.capabilities` 集合中声明此 capability（非 stub 注册）；
- **Real fetch 实现** = `fetch()` 方法中包含真实 AKShare API 调用路径（含 endpoint 选择、字段映射、错误处理）；
- **Real persistence 实现** = `P3PersistenceWriter.upsert()` 写入真实 MongoDB 的路径已实现并测试；
- **Refresh 实现** = `service.refresh_xxx()` 完整三态守卫 + fetch→upsert 路径已实现；
- **Live smoke 执行** = 真实 API 调用在特权环境中至少成功一次并产出 smoke 报告。

### P0.3 真实 Provider 统一接口边界

任何真实 Provider 接入必须遵循以下四阶段管线，且**所有真实调用仅发生在 future 的授权 smoke 或 production activation**：

```
Step 1: extract
        AKShare / 其他 Provider → pd.DataFrame 或 dict
        约束：仅 AKShare 匿名调用（无 token）；单次调用 ≤3 交易日窗口
        禁止：自动重试、fallback、多 endpoint 组合

Step 2: canonical mapping
        AKShare 字段 → domain object 字段
        约束：以 SPEC-03-014 §3.x 为准；类型转换（str→float/int）、单位统一
        禁止：伪装北向持股历史为净流入（Pascal C）、虚构市场温度公式（OQ-6）

Step 3: validation / provenance
        canonical object 字段校验（类型/范围/必填）+ provenance 记录
        约束：每个映射结果必须标注来源 endpoint、调用参数、映射时间
        禁止：在 offline 阶段执行任何真实 unmapped 字段的内省

Step 4: DataResult.source_trace
        四阶段结果封装为 DataResult.source_trace 条目
        格式：`"akshare(endpoint: <name>, fields: [<mapped_field>], issues: [<deviation>])"`
        约束：source_trace 不含 `"ud_materialized(ok)"` 或 `"cache(ok)"`；允许 `"ud_materialized(skipped: ...)"`、`"cache(miss)"`
```

**离线实现范围**（P0 允许，不会触发真实调用）：
- stub fetch → canonical mapping 的纯函数映射测试（mock AKShare 返回 fixture DataFrame）
- `from_dict()` 类型的松弛映射覆盖所有字段
- `_EXPECTED_*_FIELDS`（STUB_COLUMNS）定义与 `providers/__init__.py` 孪生等价性测试
- Provider endpoint 选择逻辑的文档定义（不激活 endpoint）

**禁止实现范围**（P0 不允许，属 P1/P2）：
- ❌ 真实 `akshare.stock_xxx()` 调用
- ❌ `P3PersistenceWriter.upsert()` 真实 MongoDB 写入
- ❌ `CacheManager.put()` 真实写入
- ❌ `refresh_xxx()` 中的真实 fetch→upsert 路径
- ❌ 任何形式的外网 / API / MongoDB 网络连接

### P0.4 P3-A 映射验收项（sector.snapshot / sector.ranking）

**冻结事实**：B2 实测 SSLError（`requests.exceptions`），真实 endpoint 不可达。Expected 字段集基于 AKShare 公开文档推断，标注「未 live-read 验证」。

| # | 验收项 | 验证方式 | 约束 |
|---|---|---|---|
| PA-1 | `_EXPECTED_SECTOR_SNAPSHOT_FIELDS` 基于 AKShare `stock_board_industry_cons_em` 公开文档定义，且包含至少以下字段：板块代码/名称/类型/日期/涨幅/涨跌家数/领涨股/换手率 | 静态检查 | 不得臆定未在公开文档中出现过的字段名 |
| PA-2 | `_EXPECTED_SECTOR_RANKING_FIELDS` 同上，基于 `stock_board_industry_rank_em` 公开文档定义 | 静态检查 | 同上 |
| PA-3 | sector.snapshot 空返回语义：Provider 返回空 DataFrame → `DataResult.success(data=None/is_empty, provider="akshare")`；`source_trace` 不含 "ud_materialized(ok)" | stub 测试 | 空 ≠ 失败 |
| PA-4 | sector.ranking 空返回语义：空 DataFrame → `DataResult.success(data=[], provider="akshare")` | stub 测试 | 同上 |
| PA-5 | 字段漂移错误处理：unmapped 额外字段静默忽略；缺失字段填 None 或默认值 | `from_dict` 测试 | 不抛 KeyError |
| PA-6 | 按 `snapshot_date` 排序断言：查询返回列表按日期降序排序 | stub fixture 断言 | 日期格式 `YYYY-MM-DD` |
| PA-7 | `_EXPECTED_SECTOR_*_FIELDS` 与 `providers/_stub_columns.py` + `providers/__init__.py` 孪生定义完全等价 | 孪生等价性测试 | DESIGN-03-014 §4.1 约束 |
| PA-8 | STUB_COLUMNS 覆盖 industry + concept 两种板块类型 | fixture 覆盖 | 至少 2 条 fixture 记录 |
| PA-9 | 所有 AKShare Provider 字段映射仅在 STUB_COLUMNS/`_EXPECTED_*_FIELDS` 中定义；**不创建真实 endpoint skeleton** | 静态 grep | `akshare.py` fetch 方法在 P0 中保持 stub |

### P0.5 P3-B 映射验收项（flow.capital_flow_daily / flow.northbound_daily）

**冻结事实**：
- `flow.capital_flow_daily`：B2 成功，`stock_individual_fund_flow` 返回数据；`_EXPECTED_FLOW_FIELDS` 须基于真实返回字段更新。
- `flow.northbound_daily`：B2 success 但语义不匹配（持股历史≠净流入）；Pascal C 确认：northbound 三字段恒 None，不指向真实 endpoint。

| # | 验收项 | 验证方式 | 约束 |
|---|---|---|---|
| PB-1 | `_EXPECTED_FLOW_FIELDS` 基于 B2 冻结证据 + `stock_individual_fund_flow` 公开文档定义，必须包含：`symbol`/`market`/`trade_date`/`main_net_inflow`/`super_large_net_inflow`/`large_net_inflow`/`medium_net_inflow`/`small_net_inflow`/`main_net_inflow_ratio`/`margin_balance` | 静态检查引用 B2 报告 | 不得臆定字段；不低于 10 个 expected 字段 |
| PB-2 | `flow.northbound_daily` 的 `_EXPECTED_NORTHBOUND_FIELDS` 确认三字段恒 None：`northbound_net_inflow: None`、`northbound_hold_shares: None`、`northbound_hold_ratio: None` | 静态检查 | Pascal C：不指向真实 endpoint，不引入 A/B endpoint skeleton |
| PB-3 | 资金流符号约定：所有 `*_net_inflow` 正=净流入、负=净流出 | fixture + 单元测试 | V-SEC-3 |
| PB-4 | 非沪深港通标的的 northbound 字段为 None | stub fixture 断言 | V-SEC-4 |
| PB-5 | `flow_stub._build_default_payload()` Record A/C 三 northbound 字段均为 None（Pascal C 修复） | Python 断言：`assert r.get("northbound_net_inflow") is None` | 4 条记录全部通过 |
| PB-6 | `StubFlowProvider.fetch("flow", "northbound_daily")` 返回列表中每条记录的 northbound 字段过滤为 None | stub 测试 | 投影过滤不影响 capital_flow_daily |
| PB-7 | `flow_service.refresh_capital_flow()` 在 `p3_writer` 非 None 时抛 `NotImplementedError`（injected-not-implemented） | pytest.raises | 不执行 fetch、不 upsert |
| PB-8 | `flow.northbound_daily` refresh 路径在 `FlowService` 中有显式 fail path（`_is_northbound_refresh_disallowed()` 返回 True） | 静态检查 | northbound 永不进入 "authorized" |
| PB-9 | 空返回语义：`flow.capital_flow_daily` 空 DataFrame → `DataResult.success(data=[], provider="akshare")`；`flow.northbound_daily` 空 → 同上 | stub 测试 | 空 ≠ 失败 |
| PB-10 | `_EXPECTED_*_FIELDS` 与 STUB_COLUMNS 孪生等价性通过 | 孪生等价性测试 | DESIGN-03-014 §4.1 |

**绝对禁止**：
- ❌ 将北向持股历史（`持股数量`/`持股市值`/`今日增持资金`）别名映射为 `northbound_net_inflow`。
- ❌ 在 `CapitalFlowRecord.northbound_net_inflow` 中静默填入持股语义的值。
- ❌ 在 smoke/domain object/mapping 文档中把「北向持股历史」表述为「北向净流入」。
- ❌ 引入 A/B 选项的 endpoint skeleton（候选 endpoint 不在此 Phase 3 范围）。

### P0.6 P3-C 映射验收项（sentiment.market_snapshot / sentiment.limit_up_pool）

**冻结事实**：
- `market_snapshot`：B2 空返回，row_count=0。22 字段 canonical schema 已裁定。`market_temperature` 允许 None（OQ-6）。`northbound_net_flow` 无合规来源前为 None。
- `limit_up_pool`：B2 空返回同 market_snapshot。Expected 字段集基于 AKShare 公开文档推断。
- freshness 跨层命名冲突已由 Pascal 裁定冻结 `market_sentiment` canonical key（RFC-03-014-F6 / SPEC-03-014-F6），P0/P1 冻结解除。

| # | 验收项 | 验证方式 | 约束 |
|---|---|---|---|
| PC-1 | `_EXPECTED_SENTIMENT_FIELDS` 基于 AKShare `stock_market_fund_flow` + `stock_zt_pool_em` 公开文档定义；22 字段 canonical 契约为唯一基准 | 静态检查 | 不得引用 10 字段 superseded model 的字段 |
| PC-2 | `_EXPECTED_LIMIT_UP_FIELDS` 基于 `stock_zt_pool_em` 公开文档定义 | 静态检查 | 不臆定 |
| PC-3 | `market_temperature` 在所有 fixture + stub 返回中为 `None`（Pascal OQ-6：不强制合成，禁止编造）| fixture 断言 + `from_dict` 默认值 | 任何非 None 值视为验收 FAIL |
| PC-4 | `northbound_net_flow` 在所有 fixture + stub 返回中为 `None`（无合规来源） | fixture 断言 + `from_dict` 默认值 | 同 |
| PC-5 | 22-field `MarketSentimentSnapshot.from_dict()` 松弛映射覆盖全部 22 字段，无 KeyError | 单元测试 | `frozen=True` 关闭为可修改 dataclass |
| PC-6 | 空返回语义（按 X2）：空 DataFrame → `DataResult.success(data=None, provider="akshare")`；verdict=fail（保守）；不输出 `empty_semantics` 字段 | stub 测试 + reporter 模板检查 | X2 保守 fail |
| PC-7 | `sentiment_service.get_market_sentiment()` 返回 `MarketSentimentSnapshot`（22 字段 canonical 类型） | Python 断言 | 返回类型与 §3.3 一致 |
| PC-8 | `sentiment_service.get_limit_up_pool()` 返回 `list[dict]`（含 symbol/reason/days） | Python 断言 | 与 SPEC §5.1 一致 |
| PC-9 | `refresh_market_sentiment_snapshot()` 三态守卫：`p3_writer=None`→`ProviderUnavailableError`；injected→`NotImplementedError`；authorized→happy-path（当前不在 P0 范围） | pytest.raises | 不执行 fetch/upsert |
| PC-10 | `_EXPECTED_*_FIELDS` 与 STUB_COLUMNS 孪生等价性通过 | 孪生等价性测试 | 同 §P0.4 PA-7 |
| PC-11 | freshness canonical key 已裁定冻结：`market_sentiment` 为 `sentiment.market_snapshot` 唯一 key、`sentiment_limit_up_pool` 为 `sentiment.limit_up_pool` 唯一 key（RFC-03-014-F6） | 断言见 SPEC-03-014-F6 §3.2 C-1~C-6 | 禁止双 key/alias/fallback |

**绝对禁止**：
- ❌ 虚构 `market_temperature` 合成公式或填充非 None 值。
- ❌ 虚构 `northbound_net_flow` 值。
- ❌ 基于 superseded 10 字段模型定义 fixture/expected 字段集。
- ❌ 在 `FreshnessPolicy.DEFAULT_TTLS` 注册 `sentiment` 或引入双 key/alias/fallback（F6 裁定后，见 SPEC-03-014-F6 §3.2）。

### P0.7 P0 vs P1 vs P2 边界与依赖

| 阶段 | 名称 | 包含操作 | 授权模式 | 依赖 |
|---|---|---|---|---|
|| **P0**（已完成） | **离线可实现契约** | 静态代码、fixture、mock Provider、孪生等价性测试、refresh 三态守卫 stub（`NotImplementedError`）、`_EXPECTED_*_FIELDS` 定义、from_dict 松弛映射、端到端离线 smoke（mongomock/fake） | 已通过 Kanban 链完成 | 无外部依赖 |
| **P1**（已完成） | **Fake-only Closeout** | P3PersistenceWriter get/upsert 代码实现（mongomock 验证）、refresh happy-path 编排（mock Provider + mongomock）、CacheManager.put() 调用代码、_is_refresh_authorized() toggle、DataRouter._try_materialized() capability 扩展、northbound_daily fail-stop。**全部仅 mongomock/fake 验证，零真实 I/O** | 已通过 Kanban 链完成（P1 T1→T2→T3→T4→T5→T6） | P0 全部验收通过 |
| **P1.5** | **生产激活** | G-A/B/C-2 Refresh Gate 激活：`_is_refresh_authorized()`→True + refresh happy-path 生产启用 | 逐子阶段 Pascal Gate（G-A/B/C-2）；P1.5 前不得真实激活 | P1 完成 + Pascal 显式确认 |
| **P2** | **真实 Smoke & Canary** | PR-0 Secret 审计、PR-1 MongoDB 只读预检、PR-2/3/4 真实 Provider smoke、PR-DDL-* 集合创建、PR-CANARY-* 手动 canary | 逐 Gate Pascal 授权（PR-0~PR-4、PR-DDL-*、PR-CANARY-*） | P1.5 完成 |

| 操作 | P0 允许 | P1 允许 | P2 允许 |
|---|---|---|---|
| 静态代码/fixture/mock | ✅ | ✅ | ✅ |
| `_EXPECTED_*_FIELDS` 定义 | ✅ | ✅ | ✅ |
| Stub Provider 返回 fixture 数据 | ✅ | ✅ | ✅ |
| 真实 AKShare API 调用 | ❌ 禁止 | ❌ 禁止 | ✅ PR-smoke |
| 真实 Mongo ping/listCollections | ❌ 禁止 | ❌ 禁止 | ✅ PR-1 |
| 真实 Mongo DDL（createCollection/index） | ❌ 禁止 | ❌ 禁止 | ✅ PR-DDL-* |
| 真实 Mongo DML/upsert | ❌ 禁止 | ✅ G-A/B/C-2 后 | ✅ PR-CANARY |
| CacheManager.put() 真实写入 | ❌ 禁止 | ✅ refresh 激活后 | ✅ |
| refresh_xxx() happy-path | ❌ 禁止 | ✅ G-A/B/C-2 后 | ✅ |
| 任意 cron/systemd/调度 | ❌ 禁止 | ❌ 禁止 | ❌ 禁止（Phase 5）|

### P0.8 完全副作用矩阵

| 操作 | 类型 | P0 权限 | 授权模式 | 风险等级 |
|---|---|---|---|---|
| 静态代码编写/修改 | 代码 | ✅ 允许 | Kanban task 自然授权 | 无 |
| Fixture 编写/修改 | 测试 | ✅ 允许 | 同上 | 无 |
| Mock Provider 实现 | 测试 | ✅ 允许 | 同上 | 无 |
| `_EXPECTED_*_FIELDS` / STUB_COLUMNS 定义 | 配置 | ✅ 允许 | 同上 | 低（仅影响 expected 字段集） |
| `from_dict()` 松弛映射 | 代码 | ✅ 允许 | 同上 | 低 |
| refresh 三态守卫（`NotImplementedError`） | 代码 | ✅ 允许 | 同上 | 低 |
| 孪生等价性测试 | 测试 | ✅ 允许 | 同上 | 无 |
| 离线端到端 smoke（mongomock） | 测试 | ✅ 允许 | 同上 | 无 |
| --- | --- | --- | --- | --- |
| **真实 API read（AKShare）** | 网络 I/O | ❌ **禁止** | 仅 P2 PR-smoke | 低（无持久化副作用） |
| **真实 Mongo read（ping/listCollections）** | 网络 I/O | ❌ **禁止** | 仅 P2 PR-1 | 低 |
| **真实 Mongo DDL（createCollection/index）** | Mongo 元数据 | ❌ **禁止** | 仅 P2 PR-DDL-* ± Pascal 确认 | 中 |
| **真实 Mongo DML/upsert** | 数据写入 | ❌ **禁止** | 仅 P1 G-*-2 + P2 PR-CANARY | 中 |
| **CacheManager.put() 真实写入** | 缓存写入 | ❌ **禁止** | 仅 P1 refresh 激活 | 低 |
| **refresh_xxx() happy-path fetch→upsert** | 复合 | ❌ **禁止** | 仅 P1 G-*-2 | 中 |
| **PR-CANARY 手动 recall** | 复合 | ❌ **禁止** | 仅 P2 PR-CANARY-* | 中 |
| **cron/systemd/task_center Job** | 调度 | ❌ **禁止** | 仅 Phase 5 | 高 |
| **外部消息/webhook 推送** | 消息 | ❌ **禁止** | N/A（不在 Phase 3 范围） | 低 |

### P0.9 旧 Checkbox 状态纠正

以下清单列出当前文档各章节中已 superseded 或不再准确的 checkbox/状态声明，以及 P0 纠正后的可审计现状。

| 位置 | 旧声明（不做当前实现事实） | P0 可审计现状 | 纠正动作 |
|---|---|---|---|
| RFC §3.1 Must-Have 全部 checkbox（6 项） | 未勾选 | 前 3 项（三阶段拆分、schema、读写边界）已通过 T2 Design 裁决；后 3 项（Gate、测试策略、辅助研究声明）已部分落实 | 全部标注「✅ 已落实（P0: offline）」或保留未勾选标记为 P0 范围 |
| RFC §9.2 A-015 辅助研究声明 | 未勾选 | 三份 domain object docstring 均已包含「辅助研究数据，不构成交易指令或投资建议」；可通过静态 grep 验证 | 标注「✅ 已验证」 |
| RFC §10.2 阶段状态表 T3 Implement | "Superseded（V0.15 离线实现）" | T3 Implement: 22-field canonical（from_dict/fixture/stub/test）已验证基线；mapping/guard/twin-equivalence 待完成 | 保留 superseded 状态，更新基线事实描述 |
| SPEC §2.1 In Scope 全部 checkbox（19 项） | 未勾选 | P3-A sector domain + service + stub 已离线实现；P3-B flow domain + service + stub 已离线实现；P3-C sentiment 22-field canonical（from_dict/fixture/stub/test 已验证基线）；AKShareProvider 注册、物化集合写入、T4 smoke 均未实现 | P3-A/B 离线已实现项标注「✅ offline only」；P3-C 标注「offline: 22-field canonical（from_dict/fixture/stub/test 已验证基线）, 10-field superseded」；未实现项保持 ❌ |
| SPEC §10 G-A/B/C 系列 Gate | 所有未勾选 | DDL Gate（G-A-1/G-B-1/G-C-1）已冻结（PR-DDL-P3A/P3B/P3C 均已授权）；Provider 首次调用 Gate（G-A-2/G-B-2/G-C-2）未授权；Canary Gate（G-A-3/G-B-3/G-C-3）未授权 | DDL Gate 标注「✅ 已冻结」；其余标注「❌ 未授权（属 P1/P2）」 |
| RFC §5.5 FV-8/FV-11 | 待验证 | FV-8（TA-CN 覆盖）仍待验证；FV-11（AKShare 实际字段差异）B2 已部分验证（仅 flow 成功、sector SSL 失败、sentiment 空返回）| FV-11 更新为「B2 已部分验证，见 §13.4.5」；其余保持 |

**纠正原则**：
1. 旧 checkbox 的「未勾选」状态**不自动等于「未实现」**——部分项已在离线实现中落实。
2. 所有「已勾选」必须能追溯到可执行的代码/测试/文档证据，不依赖口头确认。
3. 「真实 Provider 接入完成」「真实 MongoDB 写入完成」「真实 smoke 完成」在任何离线阶段的 checkbox 中**均不得声称已完成**——此类声明仅允许在 P2 smoke 报告后做出。
| 4. 本 §P0.9 纠正后，后续 Implementation 验收直接引用本节的「可审计现状」，不再引用旧 checkbox 的原始状态。

---

## P1 受控 Mongo 物化与显式 refresh 的零副作用契约冻结

### P1.1 背景与目标

P0 已冻结六 capability 的真实 Provider 离线可实现契约（stub → canonical mapping → validation/provenance → source_trace），但所有持久化路径均保持 stub/NotImplementedError 状态。P1 的目标是在 **离线代码层面** 实现受控 MongoDB 物化（P3PersistenceWriter upsert/read）、显式 refresh happy-path 与 CacheManager.put() 激活的代码路径，且所有路径**仅通过 mongomock/fake 验证，不触发任何真实 I/O**。

P1 不是对 P0 的替代而是扩展——P0 的离线可实现契约（`_EXPECTED_*_FIELDS`、from_dict、孪生等价性测试、空返回语义、refresh 三态守卫 stub）全部保持有效。P1 在此基础上新增受控持久化与显式刷新的代码实现。

**关键边界**：
- P1 实现的 Mongo upsert/read 路径**全部**通过 mongomock 或 FakeDatabase 验证，不出现在真实 MongoDB 连接或 DDL 执行场景中。
- P1 实现的 refresh happy-path 代码**禁止**在离线验证中触发真实 AKShare API 调用——仅通过 mock Provider 验证编排逻辑。
- P1 的 `_is_refresh_authorized()` toggle 可从 `False`（P0 默认）切换为 `True`（P1 授权后），但该 toggle 的**真实激活**（G-A/B/C-2 Gate）属于独立的 P1.5 生产就绪步骤。

### P1.2 P1 覆盖的 Capability 与集合/文档语义

P1 覆盖 P3-A/P3-B/P3-C 全部六个 capability，对应三个 `03_data_ud_*` 集合：

| 子阶段 | 持久化集合 | Capabilities | 文档唯一键 | 写入模式 |
|---|---|---|---|---|
| **P3-A** | `03_data_ud_market_sector_snapshot` | `sector.snapshot`、`sector.ranking` | `{market, sector_code, snapshot_date}` | upsert（`update_one` with `$set`）；同一唯一键的重复写入覆盖，不保留历史版本 |
| **P3-B** | `03_data_ud_stock_capital_flow` | `flow.capital_flow_daily`、`flow.northbound_daily` | `{market, symbol, trade_date}` | upsert（同上）。`northbound_daily` 的 refresh 路径**始终 fail-stop**（`_is_northbound_refresh_disallowed()` 返回 True），永不进入 authorized 态 |
| **P3-C** | `03_data_ud_market_sentiment_snapshot` | `sentiment.market_snapshot` | `{market, snapshot_date, snapshot_time}` | upsert（同上）；MarketSentimentSnapshot 22 字段 canonical 契约为唯一写入 schema |
| | | `sentiment.limit_up_pool` | `{market, symbol, trade_date}` | upsert（同上）；LimitUpPoolRecord 为唯一写入 schema；两个 capability 共存于同一集合（异构文档，异键），写入不冲突。读路径 date-level pool filter 为 `{market, trade_date}`，single-stock 扩展为 `{market, symbol, trade_date}`（详见 F1 amendment `RFC-03-014-F1` 键裁定 + F4 amendment `RFC-03-014-F4` 读 filter 裁定） |
|
|**禁止**：
- 任何旧 10-field `sentiment_type` 聚合模型（`{market, sentiment_type, market_date}` 唯一键）的写入路径——22 字段 canonical 契约是唯一产品 schema。
- 在 P1 离线实现中写入真实 MongoDB 集合（见 §P1.6 副作用矩阵）。

### P1.3 MongoDB-first 离线实现边界

**MongoDB-first 是 P1 的设计目标**，即所有 `03_data_ud_*` 物化集合以 MongoDB（`tradingagents` 库）为唯一生产持久化后端。但 **P1 离线实现阶段** 的约束如下：

| 项目 | P1 离线约束 |
|---|---|
| 数据库后端 | 仅 mongomock / FakeDatabase（P3PersistenceWriter 的 `_assert_fake_db` 拒绝真实 pymongo 连接） |
| SQLite 角色 | 仅用于：现有 legacy adapter 数据源、单元/集成测试隔离数据库、配置显式授权的离线 fallback。**禁止**作为 `03_data_ud_*` 集合的生产写入目标 |
| 连接凭据 | 不在 P1 中读取或验证 MongoDB 连接凭据（skills/.env 五组件键）；
 凭据验证属 P2 PR-0 |
| DDL 执行 | `createCollection` / `createIndex` 代码路径可写（用于未来的 PR-DDL-* Gate），但在 P1 中**不得执行**——仅通过 mock 验证脚本正确性 |

### P1.4 internal-first read、显式 refresh、cache/materialized write 边界

#### P1.4.1 internal-first read 路径

Internal-first 读取路径在 P1 中保持以下顺序，不对设计基线做结构性变更：

```
TA-CN 既有 → P3PersistenceWriter.get()（物化） → CacheManager.get() → 外部 Provider
```

P1 实现的 `P3PersistenceWriter.get()` 方法在所有 P1 测试中通过 mongomock 验证。`DataRouter._try_materialized()` 的 capability 参数 + `P3PersistenceWriter` 注入引用（DESIGN-03-014 §0.4 方案 A 扩展）在 P1 中实现代码路径并通过 mock 验证。

#### P1.4.2 显式 refresh

Refresh 的三态守卫在 P0 中已实现 stub（`NotImplementedError`）。P1 实现 refresh happy-path 代码：`fetch()` → canonical mapping → `P3PersistenceWriter.upsert()` → `CacheManager.put()` → 返回 `PersistenceResult`。

**约束**：
- Refresh **默认禁止**（`_is_refresh_authorized()` 返回 `False`）。P1 实现 happy-path 代码，但该代码路径的激活开关 `_is_refresh_authorized()` 由 Pascal Gate 控制。
- Refresh happy-path 在 P1 验证中**仅通过 mock Provider + mongomock 测试**，不触发真实 AKShare 或 MongoDB 调用。
- `flow.northbound_daily` 的 refresh 路径维持 **fail-stop**（参见 §P1.2 禁止），不实现 happy-path。

#### P1.4.3 CacheManager.put() 写入

`CacheManager.put()` 的写入代码路径在 P1 中实现并通过 mock 验证。但真实 `CacheManager.put()` 调用在 `refresh_xxx()` 中默认不激活——仅在 `_is_refresh_authorized()` 为 True 时才会被调用。

#### P1.4.4 读取不会隐式触发写入

P1 实现必须保证 `DataRouter.query()` 在 P3 capability 上**不会隐式触发任何写入**（无论 `_is_refresh_authorized()` 的值）。Step 4 的自动 `_materialize()` 对 Phase 3 capability **始终跳过**——写入仅通过显式的 `refresh_xxx()` 方法触发。

**禁止**：在 `sector_service.get_sector_snapshot()`、`flow_service.get_capital_flow()`、`sentiment_service.get_market_sentiment()` 等读取方法中写物化、写 Cache 或触发 refresh。

### P1.5 幂等键与 source_trace/provenance

#### P1.5.1 幂等键

三个物化集合的 upsert 使用 §P1.2 定义的业务唯一键（而非 LocalMongoAdapter 的 `materialized_key`）作为 `update_one` 的 filter。同一唯一键的重复 upsert 是幂等的——最后一次调用的 `$set` 覆盖前值。refresh_xxx() 不得因重复调用产生额外副作用。

#### P1.5.2 source_trace 格式

P1 写入后的读取路径在 `DataResult.source_trace` 中附加物化记录条目。格式约束：

| 场景 | source_trace 条目 |
|---|---|
| P3PersistenceWriter 命中（mongomock 验证） | `"ud_materialized(ok)"`（仅当 `_is_refresh_authorized()=True` 且已写入；P1 离线阶段测试中通过 mock 断言验证） |
| P3PersistenceWriter 未命中 | `"ud_materialized(skipped: no match)"` |
| Cache 命中 | `"cache(ok)"` |
| Cache 未命中 | `"cache(miss)"` |
| 外部 Provider fetch 成功 | `"akshare(endpoint: <name>, fields: [...], issues: [...])"` |

**约束**：不允许 `"ud_materialized(ok)"` 或 `"cache(ok)"` 出现在 source_trace 中如果实际并未发生物化写入——这是 D1 裁定的精确 `(ok)` 后缀匹配规则。允许 `"ud_materialized(skipped: ...)"`、`"cache(miss)"`。

#### P1.5.3 错误与降级语义

| 场景 | 行为 |
|---|---|
| P3PersistenceWriter.get() 数据库连接异常（mongomock 模拟） | 抛出异常 → 降级到下一个 fallback 层（Cache → 外部 Provider），异常记入 `DataResult.errors` |
| P3PersistenceWriter.upsert() 异常 | refresh 整体失败 → 返回 `PersistenceResult(failed=N, errors=[...])`；不自动重试 |
| CacheManager.put() 异常 | catch-and-log（同 Phase 1B-B 设计），不阻断 refresh 主要流程 |
| Refresh 过程中 Provider fetch 失败 | refresh 失败 → `PersistenceResult(skipped=N, reason="provider_unavailable")`；不尝试部分 upsert |
| Northbound capability refresh | 始终 fail-stop → `ProviderUnavailableError`（`_is_northbound_refresh_disallowed()=True`） |

### P1.6 完全副作用矩阵

| 操作 | 代码路径实现 | P1 离线验证方式 | 真实激活所需授权 |
|---|---|---|---|
| `P3PersistenceWriter.get()`（mongomock） | ✅ 实现 | pytest + mongomock | 仅 mock 验证，无需授权 |
| `P3PersistenceWriter.upsert()`（mongomock） | ✅ 实现 | pytest + mongomock | 仅 mock 验证，无需授权 |
| `CacheManager.put()`（mock） | ✅ 实现 | unittest.mock | 仅 mock 验证，无需授权 |
| `refresh_xxx()` happy-path 代码 | ✅ 实现 | mock Provider + mongomock | **G-A/B/C-2 Gate**（Pascal 逐子阶段授权） |
| `_is_refresh_authorized()` toggle→True | ✅ 实现 | 通过 fixture 配置测试两种状态 | **G-A/B/C-2 Gate** |
| `_is_northbound_refresh_disallowed()` | ✅ 已实现 | 静态检查 + pytest | **永远不激活**（Pascal C 决策） |
| `DataRouter._try_materialized()` capability 扩展 | ✅ 实现 | pytest + mongomock | 仅 mock 验证，无需授权 |
| 真实 AKShare API 调用 | ❌ 不实现 | N/A | **P2 PR-smoke** |
| 真实 MongoDB ping/listCollections | ❌ 不实现 | N/A | **P2 PR-1** |
| 真实 MongoDB DDL（createCollection/index） | ❌ 不实现 | N/A | **P2 PR-DDL-*** |
| 真实 MongoDB DML/upsert | ❌ 不实现 | N/A | P2 PR-CANARY |
| 真实 CacheManager.put() 写入 | ❌ 不实现 | N/A | P1.5 refresh 激活 + P2 |
| 任意 cron/systemd/调度 | ❌ 不实现 | N/A | Phase 5 |

### P1.7 授权关口

| Gate | 含义 | Pascal 授权时机 | P1 阶段状态 |
|---|---|---|---|
| **G-A/B/C-1** DDL Gate | `createCollection`/`createIndex` 授权 | B1-P3A/B/C 已全部冻结（V0.9） | ✅ 已冻结，不属 P1 范围 |
| **G-A/B/C-2** Refresh Gate | `_is_refresh_authorized()`→True + refresh happy-path 生产激活 | 逐子阶段 Pascal 授权 | ❌ P1 中不激活；仅实现代码路径 |
| **G-A/B/C-3** Canary Gate | 手动 canary 调度授权 | 仅 P2 PR-CANARY | ❌ 不属 P1 范围 |

**关键声明**：P1 离线 Implement 仅实现代码路径并通过 mock 验证。Refresh Gate（G-A/B/C-2）的激活、DDL 执行（PR-DDL-*）和真实 MongoDB 连接均**不属于** P1 离线阶段——它们是独立的 P1.5/P2 生产就绪后续卡。

### P1.8 Zero-I/O 边界

P1 离线 Implement 阶段**不产生任何真实外部副作用**：

- ❌ 不调用真实 AKShare API
- ❌ 不连接真实 MongoDB
- ❌ 不执行 DDL/DML
- ❌ 不写入 Cache/物化到真实服务
- ❌ 不触发 refresh 生产路径
- ❌ 不读取或验证凭据/`.env`
- ❌ 不创建 cron/systemd/调度

P1 的所有测试在 torch/mongomock/fake Provider 环境中执行。任何真实 I/O 的测试必须声明为「仅 P2 可执行」并通过 `pytest.mark.skipif` 或等效条件守卫。

### P1.9 Freshness 跨层冻结项

PC-11（freshness `sentiment` vs `market_sentiment` 命名冲突）在 P1 中保持冻结，**不擅自裁定**：

- 文档中所有 `DEFAULT_TTLS` 键名保持当前代码基线的 `market_sentiment`（磁盘）与 `sentiment`（SPEC §0 术语）分别记录。
- P1 不得为消除命名冲突修改 `freshness.py` 或 `DEFAULT_TTLS` 定义中的键名。
- PC-11 的裁定时机标记为「P3 三层文档 finalize 前，由 Pascal 单独决断」。

> **F6 裁定（2026-08-02，V0.20）**：Pascal 已决断——冻结 `market_sentiment` 为 canonical freshness key（`sentiment_limit_up_pool` 独立并列；`sentiment` 不再作为 TTL key）。本冻结项正式解除。权威裁定见 `RFC-03-014-F6`，可执行契约见 `SPEC-03-014-F6`；运行时 freshness 查表对齐（capability → canonical key，消除 `_DEFAULT_TTL=3600` fallback 巧合）归 F6 Implement 阶段，Design 阶段同步 DESIGN-03-014。

### P1.10 P1 验收标准（Fake-only Closeout ✅）

- [x] P3PersistenceWriter.get()/upsert() 在 mongomock 环境中读取/写入正确的业务集合，使用 §P1.2 定义的唯一键。
- [x] `refresh_xxx()` happy-path：mock Provider + mongomock 全流程 PASS；`_is_refresh_authorized()=True` 时写入 upsert 和 cache；`=False` 时不执行任何写入。
- [x] `northbound_daily` refresh 路径 `_is_northbound_refresh_disallowed()` 返回 True，永不进入 authorized 态。
- [x] `DataRouter._try_materialized()` 在 P3 capability 上返回正确的物化数据（mongomock 环境）。
- [x] 读取方法（`get_sector_snapshot` 等）不触发任何写入——source_trace 不含 `"ud_materialized(ok)"` 或 `"cache(ok)"`。
- [x] 零真实 I/O 声明：全部测试仅使用 mongomock/unittest.mock/fake Provider；无真实 AKShare/MongoDB 调用产生。
- [x] 所有 P0 验收标准（PA-1~PA-9、PB-1~PB-10、PC-1~PC-11）在 P1 代码变更后**继续通过**。
- [x] `git diff --check` 无残留冲突标记；`git diff --name-status` 仅显示两份文档（RFC 与 SPEC）的改动。
