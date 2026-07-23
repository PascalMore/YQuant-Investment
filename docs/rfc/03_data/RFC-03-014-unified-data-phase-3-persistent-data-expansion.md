# RFC-03-014：Unified Data Phase 3 — 重要持久化扩展（受控分期）

## 元数据

| 项 | 值 |
|---|----|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-20 |
| 最后更新 | 2026-07-24（V0.6 PR-1 凭证来源契约对齐：MongoDB 连接凭据来源从 MONGO_URI + Hermes profile `.env` 改为复用 Phase 2 skills/.env 五组件键；PR-0 审计目标从 MONGO_URI 改为 MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE 五键；移除 Hermes profile `.env` 候选路径） |
| 版本号 | V0.6 |
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
|| V0.3 | 2026-07-22 | 生产就绪扩展。离线实现（T2 Design V0.6 + T3 Implement）已完成；本版本新增 T4 生产就绪阶段定义：§13 详细规范（只读预检、真实 Provider Smoke、副作用矩阵、Token 最小化、DDL/DML 独立 Gate、停止条件、成功标准）；§6 从旧 T3 实施 Gate 改写为 T4 生产就绪 Gate（PR-G-* 系列）；§9 追加就绪验收标准；§10 落地计划追加 T4 阶段；§5.5 追加生产就绪 FV；§7.4 扩展为完整 Smoke 流程。 | YQuant-Principal |
||| V0.4 | 2026-07-22 | 历史更新——**已被 V0.6 替换**。AKShare 无 Token + 复用 Phase 2 MONGO_URI 同步。—— AKShare 为匿名数据源，PR-0 跳过其密钥审计（§6.2），FV-10 改为匿名调用（§5.5），PR-2/PR-3/PR-4 移除 token 消耗语义（§6.2），PR-0 约束仅限 MongoDB 秘密（§6.4），§13.3 审计表移除 AKSHARE_TOKEN 并将 MONGODB_URI 替换为 Phase 2 已验证的 MONGO_URI。V0.6 将此 MONGO_URI 单键来源迁移至 skills/.env 五组件键（MONGODB_HOST/PORT/USERNAME/PASSWORD/DATABASE），V0.4 的 MONGO_URI 语义视为 superseded。 | YQuant-Principal |
||| V0.5 | 2026-07-23 | 修正：清除 §13.1 PR-2/PR-3/PR-4 行「API token 消耗」残留——AKShare 为匿名数据源无 Token，改为「AKShare 匿名 API 调用」；与 SPEC §14.1 对齐。 | YQuant-Principal |
||| V0.6 | 2026-07-24 | PR-1 凭证来源契约对齐：MongoDB 连接凭据来源从 MONGO_URI + Hermes profile `.env` 改为复用 Phase 2 skills/.env 五组件键（MONGODB_HOST、MONGODB_PORT、MONGODB_USERNAME、MONGODB_PASSWORD、MONGODB_DATABASE），沿用 PortfolioMongoLoader Phase-2 Mongo 认证语义（组件式构造连接，非 URI）；PR-0 审计表对应更新；移除 Hermes profile `.env` 候选路径；历史 MONGO_URI 描述均标为 superseded。 | YQuant-Principal |

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

<!-- 假设：AKShare 东方财富涨停/跌停接口、大盘接口可覆盖所需字段；市场温度合成为派生值，由 domain service 在 Provider 原始数据上计算 -->

#### 5.3.2 数据维度

| 维度 | 取值 |
|---|---|
| 市场 | CN（A 股） |
| 时间粒度 | 日级（收盘后快照；后续可扩展为盘中多时间点） |
| 标的 | 全市场（不绑定个股） |

#### 5.3.3 候选 Schema

见 SPEC-03-014 §3.3 精确字段级契约。DESIGN-03-007 §5.3.2 提供字段草稿，SPEC 做最终定义。

#### 5.3.4 External Fallback 链

```python
"sentiment.market_snapshot": ["akshare"],  # [假设] 仅 AKShare
"sentiment.limit_up_pool": ["akshare"],    # [假设]
```

### 5.4 读写职责边界

<!-- 事实基线：DESIGN-03-007 §7.4 internal-first + §8.1 LocalMongoAdapter §5.1 命名空间隔离 -->

|| 组件 | 读取职责 | 写入职责 |
||---|---|---|
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
|| **PR-0** | **Secret source 审计**：逐候选文件证明 MongoDB 连接凭据（五组件键 `MONGODB_HOST`、`MONGODB_PORT`、`MONGODB_USERNAME`、`MONGODB_PASSWORD`、`MONGODB_DATABASE`，来自 **skills/.env**——复用 Phase 2 PortfolioMongoLoader 认证语义，组件式构造连接，非 URI）的文件存在、可被进程加载、全部五键声明且非空匹配。**不对 AKShare 做 secret/key 审计**——AKShare 为匿名无 token 数据源，PR-0 跳过 AKShare 密钥检查，PR-2/PR-3/PR-4 可直接执行匿名只读 smoke。**禁止输出值、长度、URI、用户名或全路径+键值组合** | T4 起始 | 文件存在性检查、运行时 env 探测（只读） | 候选文件不存在、任意一键缺失/空白、端口无效、数据库名不等于 `tradingagents` → 标记 MongoDB 为「NOT_AUTHORIZED」 | P3-A/B/C | Pascal 或 DevOps |
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
| T3 Implement | ✅ 已完成 | 工作树含未提交的 Phase 3 改动 |
| **T4 生产就绪** | **▶ 当前阶段** | **本 T1 RFC 更新定义** |
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
- [ ] OQ-6：`market_temperature` 合成公式是否需要在 T2 Design 阶段定义？还是留作 Domain Service 内部实现细节？
- [ ] **OQ-7（新增）**：T4 生产就绪 PR-smoke 的执行人是否由当前 Agent 承担，还是需 Pascal 手动执行？PR-2/PR-3/PR-4 标注为「Dev/Agent」，若 Agent 无真实网络/API 权限则降级为 Pascal 手动。
||- [x] **OQ-8（V0.6 更新）**：AKShare 无需 token（已确认为匿名数据源），OQ-8 已解决。PR-0 审计仅覆盖 MongoDB 的五组件键（`MONGODB_HOST`/`PORT`/`USERNAME`/`PASSWORD`/`DATABASE`），来源为 `skills/.env`。V0.4 中使用的 `MONGO_URI` 单键来源已 superseded——复用 Phase 2 PortfolioMongoLoader 组件式构造连接语义。
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

||| 候选路径 | 检查内容 | 验证方法 | 结论 |
|---|---|---|---|---|
||| `skills/.env` | 文件存在、可读 | `os.path.isfile() 且 os.access(R_OK)` | 存在/不存在/不可读 |
||| `skills/.env` 五组件键 | 五个键均声明且非空——`MONGODB_HOST`、`MONGODB_PORT`、`MONGODB_USERNAME`、`MONGODB_PASSWORD`、`MONGODB_DATABASE` | `os.getenv("MONGODB_HOST")` 等逐一检查 | 全部已声明/缺失 N 个键 |
||| Hermes 运行时 env | 五键声明 | `os.getenv(key)` 返回非 None | 已声明/未声明 |
||| AKShare 匿名调用 | 无需密钥审计 | —（AKShare 为匿名数据源，无需 token） | 跳过 PR-0 |

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
