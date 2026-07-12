# RFC-03-007：YQuant Unified Data Layer

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-12 |
| 最后更新 | 2026-07-12 |
| 版本号 | V0.1 |
| 所属模块 | 03_data（数据层） |
| 依赖RFC | RFC-03-003（数据架构标准）、RFC-00-001（全局架构） |
| 替代RFC | 无（不替代 RFC-03-003，在其基础上上浮一层） |
| AI适配 | Hermes Kanban profile worker |
| 标签 | #data #架构 #统一数据层 #provider #多源fallback |

### 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-12 | 初始创建，定义 unified_data 全局数据访问层 | YQuant-Codex-Principal |

---


### Design 阶段修订说明（2026-07-12）

根据 Pascal 后续确认，unified_data 新增持久化集合统一使用 MongoDB `03_data_ud_*` 前缀；DSA 既有 SQLite 仅作为只读 legacy source adapter，不作为 unified_data 新增持久化后端。核心既有大表继续优先复用 TA-CN MongoDB schema，不新建 `unified_*` 替代表。

## 1. 执行摘要

YQuant 当前有 **三套独立的数据访问体系**，彼此接口不兼容、能力不共享、安全边界不统一。本 RFC 提出在 `skills/data/unified_data/` 建立一层全局统一数据访问层（Unified Data Layer），以 **SecurityId + DataResult + Provider Capability Registry** 为核心抽象，向上服务量化分析、Argus、Portfolio、Risk、Reports、Strategies 等所有消费方，向下适配 Tushare / AKShare / BaoStock / yfinance / efinance 等多源数据。该层是 **读优先** 的统一访问接口，与现有 `data-pipeline`（ETL 写入管道）正交互补。

---

## 2. 背景与动机

### 2.1 现状痛点

YQuant 的金融数据访问目前分散在三个子系统中，彼此完全独立：

**体系 A — TA-CN DataSourceAdapter（`skills/apps/TradingAgents-CN/app/services/data_sources/`）**
- 基类 `DataSourceAdapter`：定义 `get_stock_list / get_daily_basic / find_latest_trade_date / get_realtime_quotes / get_kline / get_news` 抽象方法
- 管理器 `DataSourceManager`：持有 3 个 adapter（Tushare / AKShare / BaoStock），按优先级排序 + fallback
- 优先级从 MongoDB `datasource_groupings` 集合动态加载
- 局限：只覆盖 A 股行情/基础数据，无财务深度、估值、资金流、日历、元数据等域；接口为 DataFrame 返回，无统一安全标识

**体系 B — DSA DataFetcherManager（`skills/research/daily_stock_analysis/data_provider/`）**
- 基类 `BaseFetcher`：10+ 个 fetcher（Tushare / AKShare / BaoStock / yfinance / efinance / tencent / pytdx / longbridge / finnhub / alphavantage）
- 管理器 `DataFetcherManager`：策略模式，指数退避重试、防封禁流控、熔断器（CircuitBreaker）
- 标准列 `STANDARD_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']`
- 局限：覆盖 A 股 + 港股 + 美股，但接口庞大（3771 行 base.py），无 SecurityId 统一标识，无能力声明机制，无 freshness / quality 策略

**体系 C — data-pipeline + data_interface（`skills/data/`）**
- `data-pipeline`：ETL 管道（Extract → Transform → Validate → Load），主要服务 Smart Money 图片/消息 → MongoDB 写入
- `data_interface`（RFC-03-003 定义）：IReader / IWriter 接口，面向 portfolio 集合读写
- 局限：面向 portfolio 业务数据，不含行情/财务/估值等市场数据访问

**三套体系的交叉问题：**

| 问题 | 影响 |
|---|---|
| 同一个 Tushare token 被三处各自加载 | 凭据管理分散，配额不可控 |
| 同一个 `get_kline` 逻辑在 TA-CN 和 DSA 各写一遍 | 代码重复，行为不一致 |
| 无统一 SecurityId | A 股 `600519` / `SH600519` / `600519.SH` / `sh.600519` 四种格式共存 |
| 无 Provider 能力声明 | 调用方不知道哪个 provider 支持哪个数据域 |
| 无统一 freshness 策略 | 缓存命中规则不一致，可能返回过期数据 |
| 无统一审计 | 数据来源不可追溯 |

### 2.2 业务价值

- **统一入口**：所有消费方通过一个接口获取金融数据，降低认知成本
- **多源容灾**：一个 provider 不可用时自动 fallback 到备用源，提升可用性
- **凭据集中**：Tushare token 等凭据在 unified_data 层统一管理
- **数据可追溯**：每条数据带 provider / fetched_at / quality 元信息
- **渐进迁移**：TA-CN / DSA 后续通过 adapter 模式接入，不破坏现有代码

### 2.3 触发原因

Pascal 要搭建股票量化分析框架，底层统一数据源与接口层需要上升为 YQuant 全局数据能力，路径已确认为 `skills/data/unified_data/`。该层后续需要服务股票量化分析、TA-CN、DSA、Argus、Portfolio、Risk、Reports、Strategies 以及未来新增模块。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义全局统一的 `SecurityId` 模型，覆盖 A 股 / 港股 / 美股 / Crypto / 指数 / 基金
- [ ] 定义标准 `DataResult` 返回结构，包含 data + metadata（provider / fetched_at / quality / freshness）
- [ ] 定义 `DataProvider` 抽象接口，含能力声明（Capability）注册机制
- [ ] 明确数据域接口边界：行情、财务、估值、资金流、新闻、日历、元数据、另类数据
- [ ] 定义多源 fallback 链策略与审计 metadata
- [ ] 定义缓存策略与 MongoDB 优先原则
- [ ] 定义 freshness（数据新鲜度）策略
- [ ] 明确与 `data-pipeline` 的边界（ETL 写入 vs 统一访问）
- [ ] 明确与 `task_center` 的接口边界
- [ ] 明确与 `stock` 量化分析框架的依赖关系
- [ ] 明确 TA-CN / DSA 后续 adapter 迁移边界
- [ ] 定义 MVP 范围与分阶段 roadmap

### 3.2 非目标（Out of Scope）

- [ ] **不做 Design 级设计**：本 RFC 只定义 WHAT 和 WHY，不定义 HOW（文件清单、类图、函数签名等由后续 Design 阶段产出）
- [ ] **不实现代码**：本阶段只产出 RFC + SPEC，不产出任何 `.py` 文件
- [ ] **不修改现有代码**：TA-CN / DSA / data-pipeline / data_interface 现有代码不动
- [ ] **不替代 data-pipeline**：unified_data 不是 ETL 管道的替代品，两者正交
- [ ] **不替代 data_interface**：RFC-03-003 的 IReader/IWriter 继续用于 portfolio 读写
- [ ] **不做实时行情推送**：本阶段只做请求-响应模式，不做 WebSocket / stream 推送
- [ ] **不做数据物理存储设计**：物理 schema、分区、索引策略由后续 Design 决定
- [ ] **不做 provider 性能基准测试**：性能基准是后续优化阶段的事

---

## 4. 整体设计

### 4.1 核心设计哲学

**统一抽象 + Provider 可插拔 + 读优先 + 渐进迁移**：

- 所有消费方通过统一接口访问数据，不直接对接底层 provider
- Provider 以 capability 声明自身能力，access layer 按 capability 路由
- 以读（查询）为主，写入仍走 `data-pipeline` ETL 管道
- 现有 TA-CN / DSA 通过 adapter 逐步接入，不要求一次性重写

### 4.2 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    消费方（Consumers）                            │
│  stock 量化分析 | TA-CN | DSA | Argus | Portfolio | Risk | ...  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 统一接口
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Unified Data Layer（unified_data）                  │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ SecurityId  │  │  DataResult  │  │  Provider Registry     │ │
│  │ 统一标识     │  │  标准返回     │  │  能力声明 + 路由       │ │
│  └─────────────┘  └──────────────┘  └────────────────────────┘ │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────┐ │
│  │ Cache    │ │ Freshness│ │ Fallback  │ │ Quality / Audit  │ │
│  │ MongoDB  │ │ Manager  │ │ Chain     │ │ Metadata         │ │
│  └──────────┘ └──────────┘ └───────────┘ └──────────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Provider 接口
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Providers（数据源适配）                        │
│  Tushare │ AKShare │ BaoStock │ yfinance │ efinance │ ...       │
│  TA-CN Adapter │ DSA Adapter（后续迁移）                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              外部数据源 / MongoDB 缓存                            │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 模块分工

| 模块 | 职责 | 边界 |
|---|---|---|
| `unified_data` | 统一数据访问层：SecurityId、DataResult、Provider Registry、Cache、Fallback、Freshness、Quality、Audit | 只做读访问和路由，不做 ETL 写入 |
| `data-pipeline` | ETL 写入管道：图片/消息/API → Transform → Validate → MongoDB | 只做写入，不做读访问路由 |
| `data_interface` | portfolio 业务数据 IReader/IWriter | 继续 RFC-03-003 定位，与 unified_data 并存 |
| `task_center` | 任务调度与编排 | 调度 unified_data 的定时刷新任务，但不嵌入数据访问逻辑 |
| `stock` | 股票量化分析框架 | 消费 unified_data 的输出，不含数据访问逻辑 |

---

## 5. 核心概念

### 5.1 SecurityId（统一安全标识）

**问题**：当前同一标的有多种代码格式（`600519` / `SH600519` / `600519.SH` / `sh.600519` / `600519.SS`），跨市场更混乱。

**设计**：unified_data 定义一个 `SecurityId` 值对象，作为所有接口的唯一标识：

- 格式：`{market}:{symbol}` 或更细粒度 `{market}:{exchange}:{symbol}`
- 市场：`CN`（A 股）、`HK`（港股）、`US`（美股）、`CRYPTO`、`INDEX`、`FUND`
- 转换层：提供从各种格式（wind_code / tushare_code / yahoo_symbol / 数字代码）到 SecurityId 的双向转换
- 不可变值对象：hashable、comparable

**示例**：
- 贵州茅台：`SecurityId("CN", "600519")`
- 腾讯：`SecurityId("HK", "00700")`
- 苹果：`SecurityId("US", "AAPL")`
- 比特币：`SecurityId("CRYPTO", "BTCUSDT")`
- 沪深300：`SecurityId("INDEX", "000300")`

### 5.2 DataResult（标准返回结构）

每次数据查询返回 `DataResult`，包含数据本体和元信息：

- `data`：数据本体（DataFrame 或 dict list）
- `security_id`：查询的 SecurityId
- `domain`：数据域（market_data / financial / valuation / ...）
- `provider`：实际提供数据的 provider 名称
- `fetched_at`：数据获取时间戳
- `data_date`：数据业务日期（如行情日期）
- `freshness`：新鲜度标签（realtime / delayed / cached / stale）
- `quality_score`：数据质量评分（可选，0-1）
- `source_trace`：来源链（如 fallback 经过的 provider 列表）
- `warnings`：警告信息列表

### 5.3 Provider（数据源抽象）

`DataProvider` 是所有数据源的抽象基类：

- 每个 provider 声明自己支持的 **capability**（数据域 × 操作）
- access layer 按 capability 路由请求到合适的 provider
- provider 不感知彼此，fallback 由上层 Router 管理
- provider 声明自己支持的市场（CN / HK / US / ...）

### 5.4 Capability（能力声明）

Capability 是 provider 自描述的核心机制：

- 格式：`{domain}.{operation}`，如 `market_data.kline_daily`、`financial.income_statement`
- provider 可声明多个 capability
- Registry 维护 `capability → [provider, ...]` 的映射，按优先级排序
- 调用方可指定 provider，也可让 Router 自动选择

### 5.5 Cache（缓存策略）

- **MongoDB 优先**：缓存首选 MongoDB（与现有 portfolio 数据一致）
- 每个数据域定义自己的缓存集合和 TTL
- Cache key 基于 `(security_id, domain, params)` hash
- 缓存命中时仍检查 freshness 策略
- 支持手动强制刷新（bypass cache）

### 5.6 Freshness（新鲜度策略）

不同数据域有不同的新鲜度要求：

| 数据域 | 新鲜度要求 | 缓存 TTL |
|---|---|---|
| 实时行情 | 实时（< 1 分钟） | 不缓存或极短 |
| 日线行情 | 当日收盘后更新 | 收盘前用昨日缓存，收盘后刷新 |
| 财务数据 | 季度更新 | 24h |
| 估值数据 | 日更新 | 12h |
| 资金流 | 日更新 | 12h |
| 新闻 | 近实时 | 1h |
| 日历 | 极少变化 | 7d |
| 元数据 | 极少变化 | 7d |

### 5.7 Fallback（多源容灾）

- 每个 capability 可配置 fallback 链（如 `[tushare → akshare → baostock]`）
- Router 按顺序尝试，记录每次尝试的 provider / 耗时 / 错误
- 全部失败时抛出明确异常（含所有 provider 的错误摘要）
- fallback 决策可配置：按 capability、按市场、按时间段

### 5.8 Quality（数据质量评分）

- 可选维度：完整性（缺失率）、一致性（多源交叉验证）、时效性（fetched_at vs data_date）
- 评分由 provider 或 access layer 计算，写入 DataResult.quality_score
- 消费方可基于 quality_score 做决策（如低于阈值则告警）

### 5.9 Audit（审计元信息）

- 每次查询记录审计 metadata：who / when / what / from_where / how_long
- 审计日志写入 MongoDB 审计集合（只追加，不修改）
- DataResult.source_trace 提供轻量级来源链，便于问题排查

---

## 6. 数据域接口边界

unified_data 覆盖以下数据域（Data Domain），每个域定义独立的查询接口：

| 域编号 | 数据域 | 典型数据 | MVP 覆盖 |
|---|---|---|---|
| D1 | 行情（Market Data） | 日线/周线/分钟 K 线、实时行情、盘口 | ✅ MVP |
| D2 | 财务（Financial） | 利润表、资产负债表、现金流量表 | ✅ MVP |
| D3 | 估值（Valuation） | PE / PB / PS / EV/EBITDA | ✅ MVP |
| D4 | 资金流（Money Flow） | 主力资金、北向资金、龙虎榜 | 下一阶段 |
| D5 | 新闻（News） | 新闻、公告、研报摘要 | 下一阶段 |
| D6 | 日历（Calendar） | 交易日历、财报日历、经济日历 | ✅ MVP |
| D7 | 元数据（Metadata） | 股票列表、行业分类、指数成分 | ✅ MVP |
| D8 | 另类数据（Alternative） | 链上数据、社交媒体情绪、卫星数据 | 未来 |
| D9 | 基金（Fund） | 基金净值、持仓、评级 | 未来 |

**MVP 范围**：D1（行情）+ D2（财务）+ D3（估值）+ D6（日历）+ D7（元数据），覆盖 A 股优先，港股/美股次之。

---

## 7. 与现有模块的边界

### 7.1 与 data-pipeline 的边界

| 维度 | data-pipeline | unified_data |
|---|---|---|
| 方向 | **写入**（Extract → Transform → Validate → Load） | **读取**（Request → Route → Cache/Fetch → Return） |
| 场景 | 图片 OCR、消息解析、API 批量采集入库 | 消费方查询行情/财务/估值等 |
| 输出 | MongoDB 集合 | DataResult |
| 关系 | data-pipeline 写入的数据可被 unified_data 缓存层复用 | |

**原则**：unified_data 不做 ETL，data-pipeline 不做读路由。两者通过 MongoDB 缓存层间接协作。

### 7.2 与 task_center 的边界

| 维度 | task_center | unified_data |
|---|---|---|
| 职责 | 任务调度、依赖编排、定时触发 | 数据访问与路由 |
| 交互 | task_center 可调度 unified_data 的定时刷新任务 | unified_data 不嵌入调度逻辑 |
| 接口 | task_center 通过 Python import 调用 unified_data 的刷新函数 | unified_data 暴露 `refresh(domain, securities, date_range)` 供 task_center 调用 |

### 7.3 与 stock 框架的依赖关系

| 维度 | stock 框架 | unified_data |
|---|---|---|
| 依赖方向 | stock → unified_data（单向） | |
| 调用方式 | stock 通过 `from unified_data import ...` 获取数据 | |
| 禁止 | stock 不直接 import Tushare / AKShare 等 provider 库 | |

### 7.4 TA-CN / DSA 后续 adapter 迁移边界

| 阶段 | 动作 | 风险 |
|---|---|---|
| 阶段 0（本 RFC/SPEC） | 定义 unified_data 接口与抽象，不动 TA-CN / DSA 代码 | 无 |
| 阶段 1（MVP 实现） | 实现 unified_data 核心 + 2-3 个 provider（Tushare / AKShare），不碰 TA-CN / DSA | 低 |
| 阶段 2（后续） | 为 TA-CN DataSourceAdapter 编写 unified_data adapter wrapper | 中 |
| 阶段 3（后续） | 为 DSA DataFetcherManager 编写 unified_data adapter wrapper | 中 |
| 阶段 4（远期） | TA-CN / DSA 内部逐步替换为直接调用 unified_data | 高（需逐模块验证） |

**迁移原则**：先并存后替换，每一步可回滚。

---

## 8. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| 接口过度抽象，增加复杂度 | 中 | 高 | MVP 只覆盖 5 个数据域，不过度设计 | 退回直接调用 provider |
| TA-CN / DSA 迁移工作量超预期 | 高 | 中 | 分阶段迁移，先并存后替换 | 长期保持 adapter wrapper |
| Tushare 配额限制 | 中 | 中 | 多源 fallback，AKShare/BaoStock 兜底 | 降级到免费源 |
| MongoDB 缓存膨胀 | 低 | 中 | 按数据域设置 TTL，定期清理 | 回退到不缓存 |
| SecurityId 转换有遗漏 | 中 | 高 | 覆盖测试 + 真实代码格式采样 | 补充映射表 |
| freshness 策略导致消费方拿到过期数据 | 中 | 高 | 每个域显式 TTL，强制刷新接口 | bypass cache |
| 与 data-pipeline 职责混淆 | 低 | 中 | 本 RFC 明确边界，SPEC 再细化 | — |

---

## 9. 备选方案（Alternatives Considered）

### 9.1 方案 B：扩展现有 data_interface（RFC-03-003）

- **优点**：不新增目录，复用已有 IReader/IWriter
- **缺点**：IReader/IWriter 面向 portfolio 单一场景，无 SecurityId / Capability / Provider 等概念；强行扩展会破坏其简洁性
- **不选原因**：data_interface 的定位是 portfolio 业务数据读写，不适合承载全局市场数据访问

### 9.2 方案 C：直接扩展 TA-CN DataSourceAdapter

- **优点**：TA-CN 已有 3 个 adapter + fallback 逻辑
- **缺点**：TA-CN 是子项目（submodule），不应让全局数据层依赖子项目；且其接口只覆盖 A 股行情
- **不选原因**：依赖方向反了（全局层不应依赖子项目）

### 9.3 方案 D：以 DSA DataFetcherManager 为基础扩展

- **优点**：DSA 已覆盖 A/H/US 三市场、10+ fetcher
- **缺点**：DSA 的 base.py 有 3771 行，接口庞大且耦合 DSA 业务逻辑；无 SecurityId / Capability 抽象
- **不选原因**：同方案 C，依赖方向不对；且 DSA 接口过于庞大，不适合作为全局层基础

---

## 10. 验收标准

### 10.1 本 RFC/SPEC 阶段验收

- [ ] RFC 文件存在于 `docs/rfc/03_data/`，明确业务价值、架构边界、目标/非目标和风险
- [ ] SPEC 文件存在于 `docs/spec/03_data/`，明确可执行、可测试的工程契约
- [ ] 明确 `unified_data` 与 `data-pipeline`、`task_center`、`stock` 的边界
- [ ] 明确后续 Design 分阶段建议
- [ ] 中文输出，专业简洁

### 10.2 后续实现阶段验收（供 Design 参考）

- [ ] unified_data 可被 stock 框架 import 并获取 A 股日线行情
- [ ] Tushare / AKShare 两个 provider 可 fallback
- [ ] SecurityId 可从 wind_code / tushare_code / 数字代码双向转换
- [ ] DataResult 包含 provider / fetched_at / freshness 元信息
- [ ] MongoDB 缓存命中时返回缓存数据 + freshness 标签
- [ ] 审计日志记录每次查询的 provider 链

---

## 11. 后续 Design 分阶段建议

本 RFC/SPEC 批准后，建议 Design 阶段拆分为：

| Design 阶段 | 内容 | 建议文件 |
|---|---|---|
| Design-A：核心抽象 | SecurityId / DataResult / DataProvider / Capability / Registry 的类设计 | `docs/design/03_data/DESIGN-03-007A-*.md` |
| Design-B：行情域 | D1 行情域的 provider 实现、缓存、fallback 设计 | `docs/design/03_data/DESIGN-03-007B-*.md` |
| Design-C：财务/估值域 | D2 财务 + D3 估值的 provider 实现 | `docs/design/03_data/DESIGN-03-007C-*.md` |
| Design-D：日历/元数据域 | D6 日历 + D7 元数据 | `docs/design/03_data/DESIGN-03-007D-*.md` |

也可以合并为一个 Design 文档，视 Design 阶段任务规模决定。

---

## 12. 开放问题（Open Questions）

1. **Crypto 数据源**：是否在 MVP 中纳入 Crypto（如 Binance API），还是推迟到下一阶段？
2. **实时行情深度**：MVP 的实时行情是走免费 API（如腾讯/新浪即时报价），还是只做日线级别？
3. **缓存集合命名**：unified_data 的缓存集合是否加前缀（如 `03_data_03_data_ud_cache_*`）以区分 portfolio 集合？
4. **Provider 凭据统一**：Tushare token 当前分散在多处 `.env`，是否在 unified_data 层强制统一？
5. **SecurityId 持久化**：SecurityId 转换映射是否需要持久化到 MongoDB（如 `security_master` 集合），还是纯内存计算？

这些问题不影响 RFC/SPEC 的批准，可在 Design 阶段决策。

---

## 13. 参考资料（References）

- RFC-03-003：skills/data 数据架构标准（IReader/IWriter 定义）
- RFC-00-001：YQuant 全局架构
- TA-CN 数据源：`skills/apps/TradingAgents-CN/app/services/data_sources/`
- DSA 数据源：`skills/research/daily_stock_analysis/data_provider/`
- data-pipeline：`skills/data/data-pipeline/SKILL.md`
- Pipeline skill：`skills/infra/ai-coding-pipeline/SKILL.md`
