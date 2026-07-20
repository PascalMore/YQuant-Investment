# RFC-03-014：Unified Data Phase 3 — 重要持久化扩展（受控分期）

## 元数据

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-20 |
| 最后更新 | 2026-07-20（V0.2 修正：scope 对齐、MongoDB-first/SQLite 边界、非交易声明精确措辞、API 预算标记待确认） |
| 版本号 | V0.2 |
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
| FV-1 | AKShare 东方财富板块接口是否支持按行业/概念/区域分类查询 | P3-A | T3 实施阶段编写最小 smoke 测试 | 假设支持 |
| FV-2 | AKShare 板块接口返回字段与 DESIGN 草稿 schema 的映射可行 | P3-A | T3 实施阶段验证字段映射 | 假设可行 |
| FV-3 | AKShare 个股资金流接口是否覆盖沪深两市全部标的 | P3-B | T3 实施阶段 smoke 测试 | 假设覆盖 |
| FV-4 | AKShare 资金流数据中北向资金字段是否对于非沪/深港通标的返回空 | P3-B | T3 实施阶段验证 | 假设部分标的空 |
| FV-5 | AKShare 涨停/跌停池接口的实时性与准确度 | P3-C | T3 实施阶段 smoke 测试 | 假设可用 |
| FV-6 | 市场温度指数合成所需的多个 AKShare 接口是否在同一个交易日内一致 | P3-C | T3 实施阶段验证时间戳对齐 | 假设一致 |
| FV-7 | AKShare 请求频率限制是否足以支撑全量标的一日内批量回填 | P3-B | T3 实施阶段压测 | 假设需限速 |
| FV-8 | `sector.snapshot` 数据是否可通过 TA-CN `index_daily_queries` 部分推导 | P3-A | T3 实施阶段验证 TA-CN 覆盖范围 | 仅部分覆盖 |

---

## 6. Pascal 授权 Gate

<!-- 设计原则：T1/T2/T3 离线阶段不含以下副作用；以下 Gate 在 T2 Design 完成后、T3 Implement 开始前由 Pascal 逐项授权 -->

### 6.1 逐项授权清单

| Gate ID | 授权内容 | 触发时机 | 影响范围 | 停止条件 | 子阶段 |
|---|---|---|---|---|---|
| G-A-1 | 创建 MongoDB 集合 `03_data_ud_market_sector_snapshot` + 索引 | T2 Design 完成后，T3 Implement 前 | 新增集合 schema、索引定义 | Pascal 确认 schema 最终版 | P3-A |
| G-A-2 | 启用 AKShare Provider 的 `sector.snapshot` / `sector.ranking` 能力 + 首次实时调用 | T3 实现完成单元测试后 | AKShare API 调用、token 消耗 | 首次 smoke 成功 + Pascal 审核日志 | P3-A |
| G-A-3 | 投入生产 canary：一个交易日的 `sector.snapshot` 定时采集（手动触发，非 cron） | G-A-2 通过后 | 当日板块快照写入物化集合 | 数据质量审核通过、无异常 | P3-A |
|| G-B-1 | 创建 MongoDB 集合 `03_data_ud_stock_capital_flow` + 索引 | 自选（无前置子阶段依赖）；建议 G-A-3 通过后 | 新增集合 schema、索引定义 | Pascal 确认 schema 最终版 | P3-B |
|| G-B-2 | 启用 AKShare Provider 的 `flow.capital_flow_daily` / `flow.northbound_daily` 能力 + 首次实时调用 | T3 实现完成单元测试后 | AKShare API 调用 | 首次 smoke 成功 | P3-B |
|| G-B-3 | 投入生产 canary：一个交易日的个股资金流采集（手动触发，分批限速） | G-B-2 通过后 | 全量标的资金流写入 | 数据质量审核通过 | P3-B |
|| G-C-1 | 创建 MongoDB 集合 `03_data_ud_market_sentiment_snapshot` + 索引 | 自选（无前置子阶段依赖）；建议 G-B-3 通过后 | 新增集合 schema、索引定义 | Pascal 确认 schema 最终版 | P3-C |
|| G-C-2 | 启用 AKShare Provider 的 `sentiment.market_snapshot` / `sentiment.limit_up_pool` 能力 | T3 实现完成单元测试后 | AKShare API 调用 | 首次 smoke 成功 | P3-C |
|| G-C-3 | 投入生产 canary：一个交易日的市场情绪快照采集（手动触发） | G-C-2 通过后 | 当日市场情绪写入 | 数据质量审核通过 | P3-C |

**后续授权：** 长期调度（cron / systemd）和 task_center Job 创建属独立授权，不在 T3 范围。生产 canary 仅支持手动触发。

### 6.2 禁止绕过

- 不允许在 T2 Design 阶段创建集合或写 MongoDB
- 不允许在单元测试阶段调用真实 AKShare API
- 不允许未经 Pascal 确认就启用 cron/systemd 定时采集
- 不允许跳过 canary 直接全量部署

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

### 7.4 生产 Smoke（独立授权 Gate）

生产 smoke 测试（连接真实 MongoDB + 真实 AKShare API）为独立授权 Gate（§6 G-A-2/G-B-2/G-C-2），不在离线测试阶段执行。

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
- [ ] Future provider 待验证事项（FV-1 ~ FV-8）明确列出
- [ ] `git diff --check` exit 0
- [ ] `git diff --name-status` 中本卡 diff 仅含目标 allowlist（两份文档）；共享 worktree 中非本路径的其他变更不视为本卡验收项

---

## 10. 落地计划

### 10.1 阶段划分

| 阶段 | 阶段编号 | 产出 |
|---|---|---|
| T1 RFC+SPEC | 本文档 + SPEC-03-014 | 需求定义、分期方案、契约规范、授权 Gate |
| T2 Design | DESIGN-03-014（后续交付，本 T1 阶段不走 T2） | 设计细节、文件清单、测试计划 |
| T3 Implement | P3-A → P3-B → P3-C（推荐顺序） | 代码实现 |

### 10.2 T2 Design 建议输入

T1 为本阶段 RFC+SPEC。建议 T2 Design 阶段重点关注以下输入：

1. **文件清单**：`skills/data/unified_data/models/domain/sector.py`（SectorSnapshot 追加）、`flow.py`（CapitalFlowRecord 追加）、`sentiment.py`（MarketSentimentSnapshot 追加，与 Phase 1E 的 StockSentimentScore 同文件）、`services/sector_service.py`（扩展）、`services/flow_service.py`（新建）、`services/sentiment_service.py`（扩展）
2. **AKShare Provider 扩展**：在现有 AKShareProvider 的 `capabilities` 集中新增 Phase 3 能力，实现 `fetch()` 方法
3. **LocalMongoAdapter 扩展**：新增 Phase 3 集合的读取方法
4. **CacheManager / FreshnessPolicy**：Phase 3 使用现有缓存基础设施，不需要新增
5. **AuditLogger 对接**：判断是否复用 Phase 2 审计集合（当前 Phase 2 仅 `03_data_ud_query_audit` 受控启用）
6. **MongoDB 集合创建脚本**：`db.createCollection()` + `createIndex()` 脚本，供 Pascal 在 Gate 确认后手动或自动执行

---

## 11. 开放问题

- [ ] OQ-1：P3-A/P3-B/P3-C 的执行顺序是否接受推荐顺序（板块 → 资金流 → 情绪）？见 §4.2。
- [ ] OQ-2：`sector.snapshot` 是否可部分通过 TA-CN `index_daily_quotes` 推导，从而降低外部 Provider 依赖？见 §5.4 FV-8。
- [ ] OQ-3：Phase 3 的 AuditLogger 是否复用 Phase 2 的 `03_data_ud_query_audit` 集合？Phase 2 当前仅受控启用 AuditLogger，QualitySummary 冻结。
- [ ] OQ-4：资金流数据是否需要盘中快照（分钟级）？当前仅定义日级。
- [ ] OQ-5：`sector.snapshot` 的 `members` 字段（成分股列表）是否必要？如需要，会长宽规模和更新频率如何？
- [ ] OQ-6：`market_temperature` 合成公式是否需要在 T2 Design 阶段定义？还是留作 Domain Service 内部实现细节？

---

## 12. 参考资料

- DESIGN-03-007（Unified Data Layer 详细设计），§5.3 Phase 3 集合草稿、§7.4 Provider fallback 链、§8.1 internal-first 读取路径
- RFC-03-013（Phase 1E 情绪数据最小垂直切片）—— Phase 1E 个股情绪与 Phase 3 市场情绪的层级关系
- RFC-03-012（Phase 1D CN 日线真实外部 Provider 激活）—— 外部 Provider 激活模式参考
- RFC-03-011（Phase 2 质量与审计治理）—— AuditLogger / QualitySummary 治理框架
- SPEC-03-014（Phase 3 持久化扩展契约）—— 本 RFC 对应的 SPEC
- `skills/data/unified_data/SKILL.md`—— unified_data 模块入口
