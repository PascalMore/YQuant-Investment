# DESIGN-03-007: YQuant Unified Data Layer — 完整详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal + YQuant-Principal |
| 创建日期 | 2026-07-12 |
| 最后更新 | 2026-07-14 |
| 版本号 | V3.4（T2.5 Sector 边界收敛 Amendment） |
| 来源 RFC | RFC-03-007 |
| 来源 SPEC | SPEC-03-007 |
| 关联 RFC | RFC-10-009（Task Center）、RFC-08-001（Stock Framework） |
| 关联 SPEC | SPEC-10-009（Task Center）、SPEC-08-001（Stock Framework） |
| 目标模块 | unified_data（`skills/data/unified_data/`） |

---

### 版本历史（Changelog）

| 版本 | 日期 | 变更 | 负责人 |
|---|---|---|---|
| V3.0 | 2026-07-13 | Phase 1A 详细设计（T1/T2/T3 交付物） | YQuant-Codex-Principal |
| V3.1 | 2026-07-13 | Phase 1A TA-CN MongoDB 只读集合契约定为 8 个（不实现 DSA SQLite adapter） | YQuant-Codex-Principal |
| V3.2 | 2026-07-14 | Pascal 确认 DO-11/DO-12/DO-13/DO-14/DO-15：§7.4 internal-first、§8.1 新增 LocalMongoAdapter、§5.1 命名空间隔离、§7.2/§13 删除 DSA SQLite fallback | YQuant-Codex-Principal |
| V3.4 | 2026-07-15 | T2.5 Sector 边界收敛 Amendment：Phase 1C 范围从 "index/sector 双路径" 收敛为 "index 双路径"；`stock_sector_info` 的 Router E2E 移出 1C 范围（Pascal 确认 Path A，仅由 Phase 1A direct read 覆盖）。 | YQuant-Principal |
| V3.3 | 2026-07-14 | 文档同步修订（无代码/无生产副作用）：① 删除 §1A.5(原 line 1598) "DSA SQLite adapter — Phase 1B（作为兜底数据源）" 与 §1A.6(原 line 1670) `dsa_sqlite_adapter.py — Phase 1B` 两处遗留措辞；② 删除 §13/§14 测试清单中的 `test_dsa_adapter` / `test_dsa_schema_compat` / `dsa_mock_data.py` fixture（DSA adapter 不实现，不存在对应测试）；③ §4 D04 表格中 DSA 强项列从 "TA-CN + DSA dual read" 修订为 "TA-CN only"（DSA 不作为 unified_data 读取源）；④ 增加 V3.3 同步修订说明。详见 §19 文档同步修订说明（V3.3） | YQuant-Principal |

---

## 1. 设计目标与非目标

### 1.1 设计目标

1. **完整设计**：覆盖 unified_data 整体架构、数据域、schema adapter、provider、cache、quality、persistence、task_center 接口、stock framework 接口。
2. **分阶段实现**：设计一次到位，但实现拆为 Phase 0-7，共 8 个编号阶段；其中 Phase 0 为骨架，Phase 1-7 为业务能力阶段（Phase 1 进一步细分为 1A/1B/1C 三个子阶段）。每 Phase / 子阶段有独立范围、产物、验收标准和风险。
3. **优先复用现有 schema**：TA-CN 核心集合（stock_basic_info / stock_daily_quotes / stock_financial_data / stock_news / index_daily_quotes / stock_sector_info）直接复用，不新建替代表。
4. **代码层 canonical，数据库层 adapter-first**：定义 canonical domain object / dataclass / pydantic model，但数据库读写通过 adapter 走现有集合。
5. **DSA 强项数据允许持久化**：sector / sentiment / capital_flow / dragon_tiger / chip_distribution 等 DSA 强项数据纳入新集合规划，按字段级设计 + 索引建议给出完整 schema；所有 unified_data 新增持久化集合均使用 MongoDB，不使用 SQLite。
6. **迁移最小化**：区分 reuse / extend / new 三类 schema，不含"新建统一表替代旧表"的模糊动作。
7. **边界清晰**：与 task_center、stock framework、data-pipeline、TA-CN、DSA 的接口和依赖方向明确。

### 1.2 非目标（本 Design 不做的事）

- 不实现代码（不创建 `skills/data/unified_data/` 下的 `.py` 文件）。
- 不修改 TA-CN / DSA / Argus / portfolio 现有代码。
- 不创建数据库集合或执行迁移。
- 不设计 cron / systemd / gateway / webhook / 外部推送配置。
- 不做生产 schema 变更。
- 不重构 TA-CN / DSA 现有数据流。

---

## 2. 现状分析

### 2.1 相关目录与现有子系统

| 子系统 | 路径 | 数据存储 | 关键接口 |
|---|---|---|---|
| **TA-CN** | `skills/apps/TradingAgents-CN/` | MongoDB `tradingagents` 库 | DataSourceAdapter / DataSourceManager |
| **DSA** | `skills/research/daily_stock_analysis/` | SQLite（StockDaily）+ MongoDB | DataFetcherManager / BaseFetcher（3771 行） |
| **data-pipeline** | `skills/data/data-pipeline/` | MongoDB（ETL 写入） | Extract → Transform → Validate → Load |
| **data_interface** | `skills/data/` | MongoDB（portfolio 集合） | IReader / IWriter |
| **Argus** | `skills/research/argus/` | MongoDB `tradingagents` 库 | signal / stock_pool / portfolio 集合 |

### 2.2 现有 MongoDB 集合清单（TA-CN 生产库）

从 `TradingAgents-CN/docs/design/stock_data_model_design.md`、`stock_models.py`、`sw_index_daily_service.py` 和 `stock_sector_info_service.py` 确认的生产集合：

| 集合名 | 用途 | 主键/唯一索引 | 关键字段 |
|---|---|---|---|
| `stock_basic_info` | 股票基础信息 | `{symbol, market}` unique | symbol / full_symbol / name / industry / area / total_mv / circ_mv / pe / pb / pe_ttm / pb_mrq / roe / list_date / status / market_info |
| `stock_daily_quotes` | 日线行情 | `{symbol, market, trade_date}` unique | symbol / full_symbol / market / trade_date / open / high / low / close / pre_close / change / pct_chg / vol / amount / turnover_rate / volume_ratio |
| `stock_financial_data` | 财务数据 | `{symbol, market, report_period}` unique | symbol / full_symbol / market / report_period / 三大报表字段（按报告类型分类） |
| `stock_news` | 新闻数据 | — | symbol / title / content / source / publish_time / sentiment |
| `stock_technical_indicators` | 技术指标 | — | symbol / date / 分类指标（trend/oscillator/channel/volume/volatility/custom） |
| `market_quotes` | 实时行情快照 | — | symbol / current_price / change / change_percent / volume / amount / update_time |
| `index_basic_info` | 指数基础信息 | — | symbol / full_symbol / name / market / publisher / category |
| `index_daily_quotes` | 指数/申万行业指数日线 | `{sector_code, trade_date}` 或服务定义唯一键 | sector_code / trade_date / open / high / low / close / pct_chg / volume / amount / source |
| `stock_sector_info` | 个股行业/板块分类映射 | `{full_symbol, classify_system}` unique | full_symbol / classify_system / l1_code / l1_name / l2_code / l2_name / l3_code / l3_name / datasource / update_at |
| `datasource_groupings` | 数据源分组配置 | — | 与 DataSourceManager 优先级绑定 |

### 2.3 DSA 现有模型（SQLite 侧）

| 模型 | 用途 | 关键字段 |
|---|---|---|
| `StockDaily` | 日线数据（SQLAlchemy ORM） | code / trade_date / open / high / low / close / volume / amount / pct_chg / turnover / data_source |
| `StockQuote` (Pydantic) | 实时行情 | stock_code / stock_name / current_price / change / change_percent / open / high / low / prev_close / volume / amount |
| `KLineData` (Pydantic) | K 线数据点 | date / open / high / low / close / volume / amount / change_percent |

### 2.4 现有约束与兼容性风险

1. **TA-CN 集合 `extra = "allow"`**：`stock_basic_info` 等 Pydantic model 使用 `extra = "allow"`，允许存储额外字段。这意味着 unified_data adapter 可以在内存侧把 TA-CN 文档映射为 canonical 对象时安全挂载额外派生字段（仅出现在 UD 的 DataResult / canonical model 上），严禁写入 TA-CN Mongo 文档。**严禁将 UD 派生字段（如 `ud_freshness_checked_at`）写入 TA-CN 既有无前缀集合**（详见 §5.1 / §19.1 不变量 #4）。
2. **DSA 使用 SQLite**：DSA 的日线数据存储在 SQLite，与 TA-CN 的 MongoDB 不同。DSA 不是 Unified Data 的运行时 fallback 或 internal source；Unified Data 不实现 DSA SQLite / `StockDaily` adapter（§5.1 保留 DSA 仅作为分析/参考说明）。Unified Data 的权威读取路径是 internal-first（共享 Mongo 的 TA-CN 既有数据 + Unified Data 自有物化数据 → 外部 Provider），详见 §7.4 / §8.1。
3. **代码格式碎片化**：TA-CN 使用 `symbol`（6位数字）+ `full_symbol`（含后缀），DSA 使用 `normalize_stock_code` 函数。SecurityId 需要统一处理。
4. **同一个 Tushare token 三处加载**：TA-CN、DSA、data-pipeline 各自从不同 `.env` 加载。unified_data 需要统一管理。
5. **集合命名空间隔离（同一物理库）**：TA-CN 集合直接放在 `tradingagents` 库下，无模块前缀。Unified Data 与 TA-CN 共用同一物理数据库 `tradingagents`，逻辑 ownership 通过命名空间前缀隔离：Unified Data 新增物化集合使用 `03_data_ud_*` 前缀，Task Center 元数据使用 `10_infra_tc_*` 前缀。不使用物理库隔离。

---

## 3. 总体架构

### 3.1 分层架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Consumers 消费层                                 │
│  stock framework │ TA-CN │ DSA │ Argus │ portfolio │ reports │ strategies │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ UnifiedDataClient (API Facade)
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     Unified Data Layer  (skills/data/unified_data/)       │
│                                                                           │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │ UnifiedDataClient│  │  DataRouter       │  │  ProviderRegistry       │ │
│  │ (公共查询入口)    │  │  (capability路由) │  │  (注册+查询+优先级)     │ │
│  └────────┬────────┘  └────────┬─────────┘  └────────────┬─────────────┘ │
│           │                    │                          │               │
│  ┌────────┴────────────────────┴──────────────────────────┴─────────────┐ │
│  │                       Domain Services 域服务                          │ │
│  │  market_data │ fundamentals │ valuation │ flow │ sentiment │ sector   │ │
│  │  events │ calendar │ metadata │ quality │ audit                      │ │
│  └────────┬──────────────────────────────────────────────────────────────┘ │
│           │                                                                 │
│  ┌────────┴──────────────────────────────────────────────────────────────┐ │
│  │                     Infrastructure 基础设施                             │ │
│  │  CacheManager │ FreshnessPolicy │ QualityScorer │ AuditLogger          │ │
│  │  (MongoDB缓存) │ (TTL+标签)      │ (评分计算)     │ (查询审计)           │ │
│  └────────┬──────────────────────────────────────────────────────────────┘ │
│           │                                                                 │
│  ┌────────┴──────────────────────────────────────────────────────────────┐ │
│  │                     Schema Adapters 模式适配层                          │ │
│  │  TA-CN Mongo Adapter（共享 tradingagents 库，命名空间隔离）             │ │
│  │  （复用 stock_basic_info / stock_daily_quotes 等 TA-CN 既有集合）       │ │
│  └────────┬────────────────────────────────────────────────────────────────┘ │
└───────────┼────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        Providers 数据源适配层                              │
│  TushareProvider │ AKShareProvider │ YFinanceProvider (P3) │ Finnhub (P3) │
│  （外部 Provider 仅在 internal-first 路径未命中时作为补充源触发）          │
└───────────┬──────────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│              外部数据源 / 共享 MongoDB（tradingagents 库）                  │
│  Tushare │ AKShare │ BaoStock │ yfinance │                                │
│  TA-CN 既有集合（ownership: TA-CN） │ UD 物化集合（03_data_ud_*）          │
│  Task Center 元数据（10_infra_tc_*）│ Query Cache（03_data_ud_cache_*）    │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 模块目录结构

```
skills/data/unified_data/
├── __init__.py
├── SKILL.md                           # 模块说明
│
├── client.py                          # UnifiedDataClient API Facade
│
├── models/
│   ├── __init__.py
│   ├── security_id.py                 # SecurityId 值对象
│   ├── data_result.py                 # DataResult dataclass
│   ├── data_request.py                # DataRequest dataclass
│   ├── capability.py                  # ProviderCapability / CapabilityRegistry
│   ├── provider_attempt.py            # ProviderAttempt dataclass
│   ├── quality.py                     # QualityReport dataclass
│   └── domain/                        # 域模型（canonical objects）
│       ├── __init__.py
│       ├── market_data.py             # RealtimeQuote / DailyBar / KLineData
│       ├── financial.py               # FinancialStatement / FinancialMetric
│       ├── valuation.py               # ValuationSnapshot
│       ├── flow.py                    # CapitalFlowRecord
│       ├── sector.py                  # SectorSnapshot
│       ├── sentiment.py               # MarketSentimentSnapshot
│       ├── dragon_tiger.py            # DragonTigerEvent
│       ├── chip.py                    # ChipDistribution
│       ├── news.py                    # NewsItem
│       ├── calendar.py                # TradingDay / EventCalendar
│       └── metadata.py                # StockInfo / IndexMember
│
├── router/
│   ├── __init__.py
│   ├── data_router.py                 # DataRouter（capability 路由 + fallback）
│   └── provider_registry.py           # ProviderRegistry（注册 + 查询）
│
├── providers/
│   ├── __init__.py
│   ├── base.py                        # DataProvider 抽象基类
│   ├── tushare_provider.py            # TushareProvider
│   ├── akshare_provider.py            # AKShareProvider
│   ├── yfinance_provider.py           # YFinanceProvider (Phase 3)
│   └── finnhub_provider.py            # FinnhubProvider (Phase 3)
│
├── services/
│   ├── __init__.py
│   ├── market_data_service.py         # 行情域服务
│   ├── fundamental_service.py         # 财务域服务
│   ├── valuation_service.py           # 估值域服务
│   ├── flow_service.py                # 资金流域服务
│   ├── sentiment_service.py           # 情绪域服务
│   ├── sector_service.py              # 板块/行业域服务
│   ├── event_service.py               # 事件/催化剂域服务
│   ├── calendar_service.py            # 交易日历服务
│   └── metadata_service.py            # 元数据服务
│
├── cache/
│   ├── __init__.py
│   ├── cache_manager.py               # CacheManager（MongoDB 缓存）
│   └── freshness_policy.py            # FreshnessPolicy
│
├── quality/
│   ├── __init__.py
│   ├── quality_scorer.py              # QualityScorer
│   └── audit_logger.py                # AuditLogger（查询审计）
│
├── adapters/
│   ├── __init__.py
│   └── ta_cn_mongo_adapter.py         # TA-CN MongoDB 只读适配（Phase 1A 已交付）
│
├── tasks/                             # 供 task_center 注册的刷新任务
│   ├── __init__.py
│   ├── refresh_daily_kline.py
│   ├── refresh_realtime_quotes.py
│   ├── refresh_financial.py
│   ├── refresh_sector_snapshot.py
│   ├── refresh_sentiment_snapshot.py
│   ├── refresh_capital_flow.py
│   └── refresh_dragon_tiger.py
│
├── config.py                          # 模块配置加载
└── exceptions.py                      # 模块异常定义
```

### 3.3 组件职责矩阵

| 组件 | 职责 | 输入 | 输出 |
|---|---|---|---|
| **UnifiedDataClient** | 消费方统一入口 | DataRequest | DataResult |
| **DataRouter** | 按 capability 路由到最佳 provider，管理 fallback 链 | DataRequest + Registry | DataResult + ProviderAttempt 链 |
| **ProviderRegistry** | 维护 provider 注册和 capability → [provider] 映射 | Provider 对象 | 查询结果 |
| **Domain Services** | 封装数据域的业务语义，将 canonical object 与 adapter 对接 | DataRequest | canonical domain objects |
| **CacheManager** | MongoDB 缓存读写、TTL 判断、强制刷新 | key + DataResult | 缓存的 DataResult 或 None |
| **FreshnessPolicy** | 按数据域定义 TTL 和新鲜度标签规则 | domain + fetched_at | FreshnessLabel |
| **QualityScorer** | 计算数据质量评分 | data + metadata | quality_score (0-1) |
| **AuditLogger** | 记录每次查询的 provider 链、耗时、结果 | DataResult + trace | 写入审计集合 |
| **Schema Adapters** | 把 TA-CN/DSA/Portfolio 现有集合映射为 canonical objects | 现有集合文档 | canonical domain objects |
| **DataProvider（×N）** | 各数据源的原始数据获取 | DataRequest | pd.DataFrame |

---

## 4. 数据需求覆盖表

下表覆盖股票量化分析所需全部数据类型，标注现有覆盖情况和 unified_data 设计动作。

| 编号 | 数据域 | 股票分析用途 | TA-CN 覆盖 | DSA 覆盖 | 现有数据源 | 现有 Schema 可复用？ | unified_data 设计动作 | MVP 阶段 |
|---|---|---|---|---|---|---|---|---|
| D01 | 股票基础信息/主数据 | security_id 映射、行业分类、市值分类 | ✅ stock_basic_info | ❌ | Tushare/AKShare | ✅ 强复用 | reuse（adapter 读 TA-CN） | Phase 1 |
| D02 | 证券代码标准化 | SecurityId 转换 | ❌ | ⚠️ normalize_stock_code() | — | ❌ | new（canonical SecurityId + 转换映射表） | Phase 0 |
| D03 | 实时行情 | 盘中决策、交易执行辅助 | ✅ market_quotes | ⚠️ StockQuote（仅作分析/参考） | Tushare/AKShare/腾讯/新浪 | ✅ 可复用 | adapter-only（读 TA-CN；DSA 不作为 unified_data 读取源） | Phase 1 |
| D04 | 日线/周线/月线行情 | 技术分析、趋势判断、回测输入 | ✅ stock_daily_quotes | ⚠️ StockDaily (SQLite，仅作分析/参考) | Tushare/AKShare/BaoStock/yfinance | ✅ 强复用 | reuse（adapter 读 TA-CN；DSA 不作为 unified_data 读取源） | Phase 1 |
| D05 | 复权因子 | K 线复权计算 | ❌ | ❌ | Tushare | ❌ | extend（adapter 从 Tushare 获取，缓存到 03_data_ud_cache_adj_factor） | Phase 1 |
| D06 | 财务报表 | 基本面分析、估值计算 | ✅ stock_financial_data | ❌ | Tushare/AKShare | ✅ 强复用 | reuse（adapter 读 TA-CN） | Phase 1 |
| D07 | 财务指标/质量指标 | ROE/ROIC/毛利率/现金流匹配度 | ⚠️ 部分在 stock_basic_info | ⚠️ fundamental_adapter | Tushare/AKShare | ✅ 可复用 | extend（adapter 读 TA-CN + 补充计算） | Phase 1 |
| D08 | 估值数据 | PE/PB/PS/EV-EBITDA/DCF | ⚠️ 部分在 stock_basic_info | ⚠️ 部分在 daily_basic | Tushare/AKShare | ✅ 可复用 | reuse + extend（adapter 读 TA-CN + Tushare daily_basic） | Phase 1 |
| D09 | 技术指标 | 趋势/震荡/通道/成交量/波动率 | ✅ stock_technical_indicators | ❌ | 公式计算 | ✅ 可复用 | adapter-only（读 TA-CN；后续可扩展） | Phase 3 |
| D10 | 板块/行业/概念排名 | 行业轮动、风格判断 | ✅ `stock_sector_info` + `index_daily_quotes` | ⚠️ 部分在 DSA 内存 | Tushare/AKShare/东方财富 | ✅ 强复用 + 可扩展 | reuse（adapter 读 TA-CN 行业映射和行业指数日线；动态排名可后续写入 `03_data_ud_market_sector_snapshot`） | Phase 1/3 |
| D11 | 市场情绪/涨跌停池/热点 | 市场温度、极端情绪检测 | ❌ | ⚠️ DSA market_review | AKShare/东方财富 | ❌ | new（`03_data_ud_market_sentiment_snapshot` 集合） | Phase 3 |
| D12 | 资金流（主力/北向/融资融券） | 资金面分析、Smart Money 跟踪 | ❌ | ❌ | AKShare/东方财富 | ❌ | new（`03_data_ud_stock_capital_flow` 集合） | Phase 3 |
| D13 | 龙虎榜 | 游资动向、极端交易检测 | ❌ | ❌ | AKShare/东方财富 | ❌ | new（`03_data_ud_stock_dragon_tiger_events` 集合） | Phase 4 |
| D14 | 筹码结构 | 持仓分布、成本分析 | ❌ | ❌ | AKShare/东方财富 | ❌ | new（`03_data_ud_stock_chip_distribution` 集合） | Phase 4 |
| D15 | 新闻/公告/资讯 | 事件驱动、情绪分析 | ✅ stock_news | ❌ | Tushare/AKShare/东方财富 | ✅ 强复用 | reuse（adapter 读 TA-CN） | Phase 1 |
| D16 | 社交媒体/舆情 | 散户情绪、舆论热点 | ❌ | ❌ | — | ❌ | future（Phase 6+） | — |
| D17 | 分析师评级/一致预期 | 盈利预测参考 | ❌ | ❌ | AKShare/东方财富 | ❌ | future（Phase 6+） | — |
| D18 | 催化剂/事件日历 | 业绩预告、分红、解禁、股东大会 | ❌ | ❌ | AKShare/Tushare | ❌ | future（Phase 6+） | — |
| D19 | 交易日历 | 交易日判断、数据对齐 | ❌ | ❌ | Tushare/AKShare/exchange_calendar | ❌ | new（03_data_ud_cache_trading_calendar 缓存集合） | Phase 1 |
| D20 | 指数/大盘环境 | 市场基准对比、Beta 计算 | ✅ `index_basic_info` + `index_daily_quotes` | ❌ | Tushare/AKShare | ✅ 强复用 | reuse（adapter 读 TA-CN 指数基础信息与指数日线） | Phase 1 |
| D21 | 组合持仓/适配基础数据 | 组合分析与再平衡 | ❌ | ❌ | portfolio data_interface | ✅ 可复用 | adapter-only（读 IReader） | Phase 2 |
| D22 | 历史分析结果/决策信号 | Argus signal / stock_pool 消费 | — | — | Argus/portfolio 集合 | ✅ 只读 adapter | adapter-only（读 Argus 集合） | Phase 2 |
| D23 | 数据质量/审计 metadata | 质量评分、来源追溯 | ❌ | ❌ | — | ❌ | new（`03_data_ud_query_audit` + `03_data_ud_quality_summary`） | Phase 2 |

---

## 5. Schema 复用与新增策略

### 5.1 强复用 / 不重建（Phase 1）

这些集合通过 **adapter 只读** 方式复用，不在 unified_data 中定义新的写入路径。Pascal 已确认 `index_daily_quotes` 与 `stock_sector_info` 也应纳入强复用层。

**collection ownership 隔离规则（Pascal 确认架构基线）：**

| 类别 | 物理数据库 | 集合前缀 | ownership | Unified Data 读写权限 |
|---|---|---|---|---|
| TA-CN 既有主集合 | `tradingagents` | 无前缀 | TA-CN | **只读复用**（adapter 直接读取，禁止回写/覆盖/加字段污染） |
| Unified Data 物化数据 | `tradingagents` | `03_data_ud_*` | Unified Data | 读写（Phase 1B+ 物化写入） |
| Task Center 元数据 | `tradingagents` | `10_infra_tc_*` | Task Center | 不读写（由 Task Center 模块管理） |
| Query Cache | `tradingagents` | `03_data_ud_cache_*` | Unified Data | 读写下 TTL 缓存（可丢弃，Phase 1B+） |

**关键约束**：Unified Data 与 TA-CN 共用同一物理数据库 `tradingagents`，不使用物理库隔离；逻辑隔离通过集合命名空间前缀实现。Unified Data 绝不回写、覆盖或在 TA-CN 既有无前缀集合中加字段。

强复用集合的精确口径如下：

- **TA-CN MongoDB 只读集合：8 个**（Phase 1A 全覆盖）：`stock_basic_info` / `market_quotes` / `stock_daily_quotes` / `stock_financial_data` / `stock_news` / `index_basic_info` / `index_daily_quotes` / `stock_sector_info`。
- 合计 §5.1 表格 8 行，Phase 1A 全部覆盖。

| 集合名 | 复用方式 | Adapter 类 | 写入方 | unified_data 读路径 |
|---|---|---|---|---|
| `stock_basic_info` | adapter → `StockInfo` canonical | `TA_CNMongoAdapter.get_stock_info()` | TA-CN | `metadata_service.get_stock_list()` |
| `market_quotes` | adapter → `RealtimeQuote` canonical | `TA_CNMongoAdapter.get_realtime_quotes()` | TA-CN | `market_data_service.get_realtime_quote()` |
| `stock_daily_quotes` | adapter → `DailyBar` canonical | `TA_CNMongoAdapter.get_daily_bars()` | TA-CN | `market_data_service.get_kline_daily()` |
| `stock_financial_data` | adapter → `FinancialStatement` canonical | `TA_CNMongoAdapter.get_financials()` | TA-CN | `fundamental_service.get_income_statement()` |
| `stock_news` | adapter → `NewsItem` canonical | `TA_CNMongoAdapter.get_news()` | TA-CN | `event_service.get_news()` |
| `index_basic_info` | adapter → `IndexInfo` canonical | `TA_CNMongoAdapter.get_index_info()` | TA-CN | `metadata_service.get_index_list()` |
| `index_daily_quotes` | adapter → `IndexDailyBar` canonical | `TA_CNMongoAdapter.get_index_daily_bars()` | TA-CN | `market_data_service.get_index_daily()` / `sector_service.get_sector_index_bars()` |
| `stock_sector_info` | adapter → `SectorClassification` canonical | `TA_CNMongoAdapter.get_stock_sector_info()` | TA-CN | `sector_service.get_stock_sector()` / `sector_service.get_stocks_by_sector()` |

**关键约束**：
- TA-CN adapter **只能读取**，不通过 unified_data 路径写入 TA-CN 集合。
- unified_data 自己的数据刷新走 Provider 路径（Tushare → AKShare），成功后写入 `03_data_ud_*` 物化集合（可追溯数据集），并在 `03_data_ud_cache_*` 中更新对应的 Query Cache。所有集合与 TA-CN 主集合在同一物理库 `tradingagents` 中通过命名空间前缀隔离。
- DSA SQLite 不作为运行时数据源；Unified Data 不实现 DSA adapter。DSA 仅供分析/参考用途。

### 5.2 可复用 / 可扩展（Phase 2+）

| 现有 Schema | 扩展方式 | 说明 |
|---|---|---|
| `stock_technical_indicators` | adapter 读取 + unified_data 后续可自行计算补充写入 `03_data_ud_cache_tech_indicator` | 当前 TA-CN 已有技术指标，unified_data 先 adapter 读；后续可扩展自己的计算 |
| `datasource_groupings` | 读取参考配置，不耦合 | unified_data 不依赖 TA-CN 的数据源分组逻辑；独立维护自己的 provider 优先级配置 |

### 5.3 允许新增的重要持久化集合（Phase 3-4）

以下集合是 DSA 强项数据且当前无持久化，允许新增。每个给出字段级设计草稿 + 索引建议 + 唯一键 + raw_payload 策略。

#### 5.3.1 `03_data_ud_market_sector_snapshot` — 板块/行业快照（Phase 3）

```python
# 集合: 03_data_ud_market_sector_snapshot
# 数据库: tradingagents
# 唯一键: {sector_code, snapshot_date}
# 索引: {sector_code: 1, snapshot_date: -1}, {snapshot_date: -1}, {market: 1, snapshot_date: -1}

{
    "_id": ObjectId,
    "sector_code": "BK0489",              # 板块代码（东方财富行业代码）
    "sector_name": "白酒",
    "sector_type": "industry",            # industry / concept / region / style
    "market": "CN",
    "snapshot_date": "2026-07-11",
    "rank": 5,                            # 当日涨幅排名
    "pct_chg": 2.35,                      # 板块涨跌幅 %
    "leading_stock": "600519",            # 领涨股
    "leading_pct_chg": 5.20,
    "advance_count": 18,                  # 上涨家数
    "decline_count": 2,                   # 下跌家数
    "total_count": 20,                    # 成分股总数
    "turnover_rate": 3.5,                 # 板块换手率 %
    "main_net_inflow": 1250000000,        # 主力净流入（元）
    "members": ["600519", "000858", ...], # 成分股列表
    "fetched_at": ISODate,
    "provider": "akshare",
    "raw_payload": {...}                  # 原始 AKShare 返回（可选，用于调试和审计）
}
```

#### 5.3.2 `03_data_ud_market_sentiment_snapshot` — 市场情绪快照（Phase 3）

```python
# 集合: 03_data_ud_market_sentiment_snapshot
# 数据库: tradingagents
# 唯一键: {snapshot_date, snapshot_time}
# 索引: {snapshot_date: -1}, {snapshot_time: -1}

{
    "_id": ObjectId,
    "snapshot_date": "2026-07-11",
    "snapshot_time": "15:00:00",          # 盘中快照时间或 "close"
    "market": "CN",
    "limit_up_count": 45,                 # 涨停家数
    "limit_down_count": 3,                # 跌停家数
    "advance_count": 2850,                # 全市场上涨家数
    "decline_count": 1200,                # 全市场下跌家数
    "flat_count": 350,                    # 平盘家数
    "market_temperature": 65,             # 市场温度 0-100（基于多个指标合成）
    "fear_greed_index": 58,               # 恐贪指数（如可获取）
    "limit_up_pool": ["000001", "600519", ...],  # 涨停股票列表
    "limit_down_pool": ["000002", ...],
    "continuous_limit_up": [              # 连板股票
        {"symbol": "000001", "days": 3, "reason": "业绩预增"}
    ],
    "hot_concepts": ["AI", "机器人", "新能源"],  # 当日热门概念
    "total_turnover": 1250000000000,      # 全市场成交额
    "northbound_net_flow": 5800000000,    # 北向资金净流入
    "fetched_at": ISODate,
    "provider": "akshare",
    "raw_payload": {...}
}
```

#### 5.3.3 `03_data_ud_market_hot_stock_snapshot` — 热门股票快照（Phase 4，P1 可延后）

```python
# 集合: 03_data_ud_market_hot_stock_snapshot
# 数据库: tradingagents
# 唯一键: {snapshot_date, rank}
# 索引: {snapshot_date: -1}, {symbol: 1, snapshot_date: -1}

{
    "_id": ObjectId,
    "snapshot_date": "2026-07-11",
    "symbol": "600519",
    "rank": 1,                            # 热度排名
    "hot_score": 98.5,                    # 热度分数
    "hot_reason": "业绩超预期",            # 热度原因
    "pct_chg": 5.20,                      # 当日涨幅
    "turnover_rate": 4.5,                 # 换手率
    "volume_ratio": 2.3,                  # 量比
    "main_net_inflow": 850000000,         # 主力净流入
    "news_count": 15,                     # 相关新闻数
    "fetched_at": ISODate,
    "provider": "akshare",
    "raw_payload": {...}
}
```

#### 5.3.4 `stock_capital_flow` — 资金流数据（Phase 3）

```python
# 集合: 03_data_ud_stock_capital_flow
# 数据库: tradingagents
# 唯一键: {symbol, trade_date}
# 索引: {symbol: 1, trade_date: -1}, {trade_date: -1}

{
    "_id": ObjectId,
    "symbol": "600519",
    "trade_date": "2026-07-11",
    "main_net_inflow": 850000000,         # 主力净流入（元）
    "super_large_net_inflow": 350000000,  # 超大单净流入
    "large_net_inflow": 500000000,        # 大单净流入
    "medium_net_inflow": -120000000,      # 中单净流入
    "small_net_inflow": -730000000,       # 小单净流入
    "main_net_inflow_ratio": 8.5,         # 主力净流入占比 %
    "northbound_net_inflow": None,        # 北向资金（仅沪/深港通标的）
    "northbound_hold_shares": None,       # 北向持股数
    "northbound_hold_ratio": None,        # 北向持股比例 %
    "margin_buy": None,                   # 融资买入额
    "margin_balance": None,               # 融资余额
    "fetched_at": ISODate,
    "provider": "akshare",
    "raw_payload": {...}
}
```

#### 5.3.5 `03_data_ud_stock_dragon_tiger_events` — 龙虎榜事件（Phase 4）

```python
# 集合: 03_data_ud_stock_dragon_tiger_events
# 数据库: tradingagents
# 唯一键: {symbol, trade_date, rank}
# 索引: {symbol: 1, trade_date: -1}, {trade_date: -1}, {buy_broker: 1}

{
    "_id": ObjectId,
    "symbol": "600519",
    "trade_date": "2026-07-11",
    "reason": "日涨幅偏离值达到7%",        # 上榜原因
    "rank": 1,                            # 龙虎榜排名
    "buy_broker": "中信证券上海分公司",     # 买入席位
    "buy_amount": 250000000,              # 买入金额
    "sell_broker": "机构专用",             # 卖出席位
    "sell_amount": 120000000,              # 卖出金额
    "net_amount": 130000000,              # 净买入
    "buy_seats": [                        # 买入前五席位
        {"broker": "中信证券", "amount": 250000000},
        ...
    ],
    "sell_seats": [                       # 卖出前五席位
        {"broker": "机构专用", "amount": 120000000},
        ...
    ],
    "total_buy": 850000000,               # 总买入
    "total_sell": 620000000,              # 总卖出
    "fetched_at": ISODate,
    "provider": "akshare",
    "raw_payload": {...}
}
```

#### 5.3.6 `03_data_ud_stock_chip_distribution` — 筹码分布（Phase 4）

```python
# 集合: 03_data_ud_stock_chip_distribution
# 数据库: tradingagents
# 唯一键: {symbol, trade_date}
# 索引: {symbol: 1, trade_date: -1}

{
    "_id": ObjectId,
    "symbol": "600519",
    "trade_date": "2026-07-11",
    "avg_cost": 1680.50,                  # 平均持仓成本
    "concentration_90": 12.5,             # 90%筹码集中度（越低越集中）
    "concentration_70": 7.8,              # 70%筹码集中度
    "profit_ratio_90": 65.3,              # 90%筹码获利比例 %
    "profit_ratio_70": 72.1,              # 70%筹码获利比例 %
    "chip_peak_price": 1650.00,           # 筹码峰值价格
    "chip_distribution": [                # 筹码分布区间（可选）
        {"price_range": "1600-1650", "ratio": 15.3},
        {"price_range": "1650-1700", "ratio": 28.5},
        ...
    ],
    "fetched_at": ISODate,
    "provider": "akshare",
    "raw_payload": {...}
}
```

#### 5.3.7 `unified_data_query_audit` — 查询审计日志（Phase 2）

```python
# 集合: 03_data_ud_query_audit
# 数据库: tradingagents
# 唯一键: 无（只追加）
# 索引: {queried_at: -1}, {consumer: 1, queried_at: -1}, {domain: 1, queried_at: -1}
# TTL: 90 天（按 queried_at）

{
    "_id": ObjectId,
    "query_id": "uuid",
    "consumer": "stock_framework",         # 调用方标识
    "domain": "market_data",
    "operation": "kline_daily",
    "security_id": "CN:600519",
    "params_hash": "abc123",              # 参数哈希（避免记录完整参数）
    "provider_chain": ["tushare(ok)"],    # 使用的 provider 链
    "elapsed_ms": 245,
    "cache_hit": false,
    "freshness_label": "delayed",
    "quality_score": 0.95,
    "status": "success",
    "error": null,
    "queried_at": ISODate
}
```

#### 5.3.8 `unified_data_quality_summary` — 数据质量汇总（Phase 2）

```python
# 集合: 03_data_ud_quality_summary
# 数据库: tradingagents
# 唯一键: {domain, security_id, check_date}
# 索引: {check_date: -1}, {domain: 1, check_date: -1}

{
    "_id": ObjectId,
    "domain": "market_data",
    "security_id": "CN:600519",
    "check_date": "2026-07-11",
    "completeness": 0.98,                 # 完整度（非空字段比例）
    "missing_rate": 0.02,                 # 缺失率
    "stale_flag": false,                  # 是否过期
    "source_conflict": false,             # 多源数据是否有冲突
    "abnormal_value_count": 0,            # 异常值数量
    "quality_score": 0.96,                # 综合质量评分 0-1
    "provider": "tushare",
    "last_fetched_at": ISODate,
    "checked_at": ISODate
}
```

#### 5.3.9 `03_data_ud_cache_*` — 缓存集合（Phase 1）

```python
# 集合: 03_data_ud_cache_{domain}（如 03_data_ud_cache_kline_daily, 03_data_ud_cache_financial 等）
# 数据库: tradingagents
# 唯一键: {cache_key}（按 security_id + domain + operation + params_hash）
# 索引: {cache_key: 1}, {cached_at: 1} (TTL 索引)
# TTL: 由 FreshnessPolicy 按域定义

{
    "_id": ObjectId,
    "cache_key": "CN:600519|market_data|kline_daily|abc123",
    "security_id": "CN:600519",
    "domain": "market_data",
    "operation": "kline_daily",
    "params_hash": "abc123",
    "data": {...},                        # 序列化的 DataResult.data（DataFrame → records）
    "provider": "tushare",
    "fetched_at": ISODate,
    "data_date": "2026-07-11",
    "freshness": "cached",
    "quality_score": 0.95,
    "source_trace": ["tushare(ok)"],
    "schema_version": "1.0",
    "cached_at": ISODate                  # TTL 索引字段
}
```

### 5.4 不应新增的大替代表（明确禁止）

以下表名**绝不在 unified_data 中新建**，除非未来有独立的迁移 RFC/SPEC 批准：

- `unified_stock_basic` — 替代 `stock_basic_info`
- `unified_daily_bars` — 替代 `stock_daily_quotes`
- `unified_financials` — 替代 `stock_financial_data`
- `unified_news` — 替代 `stock_news`
- `unified_market_quotes` — 替代 `market_quotes`

**原因**：这些核心数据 TA-CN 已有成熟 schema、已初始化、已接入 Argus/portfolio。新建替代表意味着大规模迁移，风险极高。

---

## 6. Canonical Domain Object 设计

以下为代码层 canonical object（dataclass / Pydantic model）设计草稿。数据库层通过 adapter 映射到现有集合，不要求数据库 schema 与之完全对应。

### 6.1 SecurityId

```python
from dataclasses import dataclass
from enum import Enum

class Market(str, Enum):
    CN = "CN"
    HK = "HK"
    US = "US"
    CRYPTO = "CRYPTO"
    INDEX = "INDEX"
    FUND = "FUND"

@dataclass(frozen=True)
class SecurityId:
    market: Market
    symbol: str

    # 工厂方法
    @classmethod
    def from_wind_code(cls, code: str) -> "SecurityId": ...
    @classmethod
    def from_tushare_code(cls, code: str) -> "SecurityId": ...
    @classmethod
    def from_numeric(cls, code: str, market: Market) -> "SecurityId": ...
    @classmethod
    def from_full_symbol(cls, code: str) -> "SecurityId": ...  # "000001.SZ" → SecurityId(CN, "000001")

    # 转换方法
    def to_wind_code(self) -> str | None: ...
    def to_tushare_code(self) -> str | None: ...
    def to_full_symbol(self) -> str | None: ...  # → "000001.SZ"

    def __str__(self) -> str:
        return f"{self.market.value}:{self.symbol}"
```

**转换映射表**：不持久化到 MongoDB，纯内存计算。核心逻辑参考 DSA 的 `normalize_stock_code()`，补充后缀映射表：

```python
# 内部映射（纯内存）
_EXCHANGE_SUFFIX_MAP = {
    "600000-609999": ".SH",   # 上海主板 60xxxx
    "000000-004999": ".SZ",   # 深圳主板 00xxxx
    "300000-301999": ".SZ",   # 创业板 30xxxx
    "688000-689999": ".SH",   # 科创板 688xxx
    "920000-929999": ".BJ",   # 北交所 92xxxx
    ...
}
```

### 6.2 DataResult

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

FreshnessLabel = Literal["realtime", "delayed", "cached", "stale", "empty"]

@dataclass
class DataResult:
    data: Any                              # pd.DataFrame 或 list[dict]
    security_id: SecurityId
    domain: str
    operation: str
    provider: str
    fetched_at: datetime
    data_date: str | None = None
    freshness: FreshnessLabel = "cached"
    quality_score: float | None = None
    source_trace: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict: ...
    def is_empty(self) -> bool: ...
```

### 6.3 DataRequest

```python
@dataclass
class DataRequest:
    domain: str
    operation: str
    security_id: SecurityId
    params: dict = field(default_factory=dict)
    provider: str | None = None          # 强制指定 provider
    force_refresh: bool = False          # 绕过缓存
    consumer: str = "unknown"            # 调用方标识
```

### 6.4 ProviderCapability

```python
@dataclass(frozen=True)
class ProviderCapability:
    name: str                             # "market_data.kline_daily"
    domain: str                           # "market_data"
    operation: str                        # "kline_daily"
    description: str = ""

    @classmethod
    def from_string(cls, s: str) -> "ProviderCapability": ...
```

### 6.5 ProviderAttempt（每次 provider 尝试的记录）

```python
@dataclass
class ProviderAttempt:
    provider_name: str
    capability: str
    status: Literal["success", "failure", "skipped"]
    elapsed_ms: float
    error: str | None = None
    attempted_at: datetime | None = None
```

### 6.6 QualityReport

```python
@dataclass
class QualityReport:
    completeness: float                   # 0-1 完整度
    missing_rate: float                   # 缺失率
    stale_flag: bool                      # 是否过期
    source_conflict: bool                 # 多源冲突
    abnormal_value_count: int
    quality_score: float                  # 0-1 综合评分
    provider: str
    last_fetched_at: datetime
    warnings: list[str]
```

### 6.7 Domain Models（Canonical Objects）

#### RealtimeQuote

```python
@dataclass
class RealtimeQuote:
    security_id: SecurityId
    current_price: float
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: float | None = None
    amount: float | None = None
    update_time: str | None = None
```

#### DailyBar

```python
@dataclass
class DailyBar:
    security_id: SecurityId
    trade_date: str                       # "YYYY-MM-DD"
    open: float
    high: float
    low: float
    close: float
    pre_close: float | None = None
    change: float | None = None
    pct_chg: float | None = None
    volume: float | None = None
    amount: float | None = None
    turnover_rate: float | None = None
    volume_ratio: float | None = None
    adj_factor: float | None = None       # 复权因子
    data_source: str = ""

    @classmethod
    def from_ta_cn_doc(cls, doc: dict, security_id: SecurityId) -> "DailyBar": ...
```

#### FinancialStatement / FinancialMetric

```python
@dataclass
class FinancialStatement:
    security_id: SecurityId
    report_period: str                    # "2025Q4" 或 "2025-12-31"
    statement_type: Literal["income", "balance", "cashflow"]
    items: dict[str, float]               # 科目名 → 金额
    currency: str = "CNY"

@dataclass
class FinancialMetric:
    security_id: SecurityId
    report_period: str
    roe: float | None = None
    roic: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    debt_to_assets: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    fcf_to_net_income: float | None = None
    receivables_to_revenue: float | None = None
    inventory_to_revenue: float | None = None
    goodwill_to_assets: float | None = None
    revenue_growth_yoy: float | None = None
    eps_growth_yoy: float | None = None
```

#### ValuationSnapshot

```python
@dataclass
class ValuationSnapshot:
    security_id: SecurityId
    trade_date: str
    pe: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    pb_mrq: float | None = None
    ps: float | None = None
    ps_ttm: float | None = None
    ev_ebitda: float | None = None
    total_mv: float | None = None          # 总市值（亿元）
    circ_mv: float | None = None           # 流通市值（亿元）
    pe_percentile_3y: float | None = None   # 3年PE分位
    pe_percentile_5y: float | None = None   # 5年PE分位
```

#### CapitalFlowRecord

```python
@dataclass
class CapitalFlowRecord:
    security_id: SecurityId
    trade_date: str
    main_net_inflow: float | None = None
    main_net_inflow_ratio: float | None = None
    super_large_net_inflow: float | None = None
    large_net_inflow: float | None = None
    medium_net_inflow: float | None = None
    small_net_inflow: float | None = None
    northbound_net_inflow: float | None = None
    northbound_hold_ratio: float | None = None
    margin_balance: float | None = None
```

#### SectorSnapshot

```python
@dataclass
class SectorSnapshot:
    sector_code: str
    sector_name: str
    sector_type: str                       # industry / concept / region / style
    snapshot_date: str
    rank: int | None = None
    pct_chg: float | None = None
    leading_stock: str | None = None
    leading_pct_chg: float | None = None
    advance_count: int = 0
    decline_count: int = 0
    total_count: int = 0
    turnover_rate: float | None = None
    main_net_inflow: float | None = None
    members: list[str] = field(default_factory=list)
```

#### MarketSentimentSnapshot

```python
@dataclass
class MarketSentimentSnapshot:
    snapshot_date: str
    snapshot_time: str
    limit_up_count: int = 0
    limit_down_count: int = 0
    advance_count: int = 0
    decline_count: int = 0
    market_temperature: float | None = None
    total_turnover: float | None = None
    northbound_net_flow: float | None = None
    hot_concepts: list[str] = field(default_factory=list)
```

#### DragonTigerEvent

```python
@dataclass
class DragonTigerEvent:
    security_id: SecurityId
    trade_date: str
    reason: str
    rank: int
    buy_broker: str
    buy_amount: float
    sell_broker: str
    sell_amount: float
    net_amount: float
    total_buy: float
    total_sell: float
    buy_seats: list[dict] = field(default_factory=list)
    sell_seats: list[dict] = field(default_factory=list)
```

#### ChipDistribution

```python
@dataclass
class ChipDistribution:
    security_id: SecurityId
    trade_date: str
    avg_cost: float | None = None
    concentration_90: float | None = None
    concentration_70: float | None = None
    profit_ratio_90: float | None = None
    profit_ratio_70: float | None = None
    chip_peak_price: float | None = None
```

---

## 7. Provider / Adapter 设计

### 7.1 DataProvider 协议

```python
from abc import ABC, abstractmethod

class DataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @property
    @abstractmethod
    def capabilities(self) -> set[str]: ...
    @property
    @abstractmethod
    def markets(self) -> set[Market]: ...
    @abstractmethod
    def is_available(self) -> bool: ...
    @abstractmethod
    def fetch(self, domain: str, operation: str, security_id: SecurityId, **params) -> pd.DataFrame: ...
    def supports(self, capability: str, market: Market) -> bool:
        return capability in self.capabilities and market in self.markets
```

### 7.2 具体 Provider 实现

#### TushareProvider

| 项 | 值 |
|---|---|
| name | `"tushare"` |
| markets | `{CN}` |
| capabilities | `market_data.kline_daily`, `market_data.kline_weekly`, `market_data.kline_monthly`, `market_data.realtime_quote`, `financial.income_statement`, `financial.balance_sheet`, `financial.cash_flow`, `valuation.daily_basic`, `calendar.trading_days`, `calendar.is_trading_day`, `metadata.stock_list`, `metadata.index_members`, `market_data.adj_factor` |
| token 来源 | `TUSHARE_TOKEN` 环境变量 → 统一从 unified_data 配置加载 |
| is_available | token 存在、tushare 可 import、`ts_api.query('stock_basic', limit=1)` 成功 |
| 限流 | 内置 rate limiter：Tushare 免费版 200次/分钟，积分版按等级 |
| 实现参考 | DSA `tushare_fetcher.py`（不直接复用代码，参考其 fetcher 策略） |

#### AKShareProvider

| 项 | 值 |
|---|---|
| name | `"akshare"` |
| markets | `{CN}` |
| capabilities | 同 TushareProvider（作为兜底） |
| is_available | `akshare` 可 import |
| 限流 | 内置简单延迟：`time.sleep(0.5)` 每请求 |

> **注意**：TA-CN MongoDB 集合不作为 DataProvider 注册。它通过 `TA_CNMongoAdapter` 在读取路径中被 internal-first 直接查询（详见 §7.4 / §8.1）。DSA SQLite 不作为运行时数据源，不注册为 provider。

### 7.3 Capability 命名规范

```
{domain}.{operation}

domain 取值：
  market_data / financial / valuation / flow / sentiment / sector /
  news / calendar / metadata / alternative / fund

operation 取值（非穷举）：
  kline_daily / kline_weekly / kline_monthly / realtime_quote / adj_factor
  income_statement / balance_sheet / cash_flow / financial_metrics
  daily_basic / valuation_snapshot / pe_percentile
  capital_flow_daily / capital_flow_minute
  market_snapshot / limit_up_pool
  sector_snapshot / sector_ranking
  dragon_tiger_daily
  chip_distribution_daily
  news_list / news_by_stock
  trading_days / is_trading_day / earnings_calendar
  stock_list / index_list / index_members / industry_members
```

完整列表（MVP 阶段使用，后续按需扩展）：

| Capability | 说明 | MVP Phase |
|---|---|---|
| `market_data.kline_daily` | 日线 K 线 | Phase 1 |
| `market_data.kline_weekly` | 周线 K 线 | Phase 1 |
| `market_data.kline_monthly` | 月线 K 线 | Phase 1 |
| `market_data.realtime_quote` | 实时行情快照 | Phase 1 |
| `market_data.adj_factor` | 复权因子 | Phase 1 |
| `financial.income_statement` | 利润表 | Phase 1 |
| `financial.balance_sheet` | 资产负债表 | Phase 1 |
| `financial.cash_flow` | 现金流量表 | Phase 1 |
| `financial.metrics` | 财务指标（计算） | Phase 1 |
| `valuation.daily_basic` | 每日估值指标 | Phase 1 |
| `valuation.snapshot` | 估值快照（含分位） | Phase 1 |
| `calendar.trading_days` | 交易日历 | Phase 1 |
| `calendar.is_trading_day` | 判断交易日 | Phase 1 |
| `metadata.stock_list` | 股票列表 | Phase 1 |
| `metadata.index_list` | 指数列表 | Phase 1 |
| `metadata.index_members` | 指数成分股 | Phase 1 |
| `metadata.industry_members` | 行业成分股 | Phase 1 |
| `flow.capital_flow_daily` | 个股日资金流 | Phase 3 |
| `flow.northbound_daily` | 北向资金 | Phase 3 |
| `sentiment.market_snapshot` | 市场情绪快照 | Phase 3 |
| `sentiment.limit_up_pool` | 涨停池 | Phase 3 |
| `sector.snapshot` | 板块快照 | Phase 3 |
| `sector.ranking` | 板块排名 | Phase 3 |
| `news.stock_news` | 个股新闻 | Phase 1 |
| `events.dragon_tiger` | 龙虎榜 | Phase 4 |
| `events.chip_distribution` | 筹码分布 | Phase 4 |

### 7.4 Provider 优先级与 Internal-First 读取路径（Pascal 确认架构基线）

> **架构基线（2026-07-14 修订）**：权威读取路径是 **internal-first**。查询时先查共享 Mongo（TA-CN 既有数据 + Unified Data 自有物化数据），内部源未命中时再触发外部 Provider。外部刷新失败不能阻断已有内部数据读取，必须返回明确的 DataResult 缺失/错误语义。

**读取路径分层（internal-first）：**

```
UnifiedDataClient.query()
    │
    ├─ 1. 查共享 Mongo 的 TA-CN 既有集合（TA_CNMongoAdapter 只读）
    │     命中 → 返回 DataResult（provider="ta_cn_internal", freshness="delayed"）
    │
    ├─ 2. 查 Unified Data 自有物化集合（03_data_ud_*）
    │     命中 + 未过期 → 返回 DataResult（provider="ud_materialized", freshness="cached"）
    │
    ├─ 3. 查 Query Cache（03_data_ud_cache_*，短 TTL）
    │     命中 + 未过期 → 返回 DataResult（provider="cache", freshness="cached"）
    │
    └─ 4. 外部 Provider fallback 链执行（Tushare → AKShare）
          命中 → 物化写入 03_data_ud_* + Cache 写入 → 返回 DataResult
          全部失败 → 返回 DataResult.error(...)（freshness="empty", provider="error"）
```

**外部 Provider 配置（仅在 internal-first 路径未命中时触发）：**

```yaml
# config/unified_data.yaml（伪代码 — 具体路径由实现阶段确定）
providers:
  tushare:
    enabled: true
    priority: 100                        # 外部源中最高优先
    rate_limit_rpm: 200
    token_env: "TUSHARE_TOKEN"

  akshare:
    enabled: true
    priority: 80
    request_delay_seconds: 0.5

  yfinance:
    enabled: false                       # Phase 3 启用
    priority: 50

  finnhub:
    enabled: false                       # Phase 3 启用
    priority: 50

# 外部 Provider fallback 链（internal-first 路径全部未命中时使用）
external_fallback_chains:
  "market_data.kline_daily": ["tushare", "akshare"]
  "market_data.realtime_quote": ["tushare", "akshare"]
  "financial.income_statement": ["tushare", "akshare"]
  "financial.balance_sheet": ["tushare", "akshare"]
  "financial.cash_flow": ["tushare", "akshare"]
  "valuation.daily_basic": ["tushare", "akshare"]
  "calendar.trading_days": ["tushare", "akshare"]
  "metadata.stock_list": ["tushare", "akshare"]
  "metadata.index_members": ["tushare", "akshare"]
  "news.stock_news": ["tushare", "akshare"]
  # Phase 3 新增
  "flow.capital_flow_daily": ["akshare"]
  "sentiment.market_snapshot": ["akshare"]
  "sector.snapshot": ["akshare"]
  # Phase 4 新增
  "events.dragon_tiger": ["akshare"]
  "events.chip_distribution": ["akshare"]
```

**与旧设计的关键差异：**
- 旧设计（外部优先）：外部 Provider 优先 → TA-CN adapter 作为低优先级 provider fallback。刷新失败会阻断已有 TA-CN 数据读取。
- 新设计（internal-first）：TA-CN 既有数据 + UD 物化数据优先 → 外部 Provider 仅在 internal 未命中时补充。刷新失败不阻断已有内部数据读取，返回明确 DataResult 错误语义。

### 7.5 Provider 可用性检测

```python
# ProviderRegistry 中的健康检测逻辑

class ProviderRegistry:
    def check_availability(self, provider: DataProvider) -> bool:
        """检测 provider 是否可用，带超时和异常降级"""
        try:
            return provider.is_available()
        except Exception:
            return False

    def get_available_providers(self, capability: str, market: Market) -> list[DataProvider]:
        """按优先级返回当前可用的 provider 列表"""
        all_providers = self.get_providers(capability, market)
        return [p for p in all_providers if self.check_availability(p)]

    def refresh_availability(self):
        """后台周期性刷新可用性（可被 task_center 调度）"""
```

---

## 8. Cache / Persistence / Freshness 设计

### 8.1 缓存与读取架构（internal-first）

> **架构基线**：读取路径是 internal-first，详见 §7.4。以下流程图反映 Pascal 确认后的权威读取顺序。

```
Consumer Request
    │
    ▼
UnifiedDataClient.query()
    │
    ▼
DataRouter.query() — internal-first 路径
    │
    ├─ 1. TA_CNMongoAdapter 查共享 Mongo TA-CN 既有集合
    │     ├─ 命中 → 返回（provider="ta_cn_internal", freshness="delayed"）
    │     └─ 未命中 / 数据域不在 TA-CN 既有集合范围 → 继续
    │
    ├─ 2. LocalMongoAdapter 查 Unified Data 物化集合（03_data_ud_*）
    │     ├─ 命中 + 未过期 → 返回（provider="ud_materialized", freshness="cached"）
    │     └─ 未命中 / 已过期 → 继续
    │
    ├─ 3. CacheManager.get() 查 Query Cache（03_data_ud_cache_*）
    │     ├─ 命中 + 未过期 → 返回（freshness="cached"）
    │     └─ 未命中 / 过期 / force_refresh → 继续
    │
    ├─ 4. 外部 Provider fallback 链执行
    │     ├─ TushareProvider.fetch() → 成功 → 物化写入 03_data_ud_* + CacheManager.put()
    │     ├─ AKShareProvider.fetch() → 成功 → 物化写入 03_data_ud_* + CacheManager.put()
    │     └─ 全部失败 → DataResult.error(...)（freshness="empty", provider="error"）
    │
    └─ 返回 DataResult（含 source_trace 完整记录）
```

**LocalMongoAdapter（新增内部源层）：**

LocalMongoAdapter 是 internal-first 读取路径中的物化数据查询层，负责读取 Unified Data 写入到 `03_data_ud_*` 的物化数据。它与 TA_CNMongoAdapter 的区别：
- `TA_CNMongoAdapter`：只读 TA-CN 既有无前缀集合（ownership: TA-CN）
- `LocalMongoAdapter`：只读/读 Unified Data 自有 `03_data_ud_*` 物化集合（ownership: Unified Data）

两者共用同一物理数据库 `tradingagents`，通过集合命名空间前缀区分 ownership。

### 8.2 CacheManager 实现要点

```python
class CacheManager:
    def __init__(self, mongo_db, collection_prefix="03_data_ud_cache_", freshness: FreshnessPolicy):
        self.db = mongo_db
        self.prefix = collection_prefix
        self.freshness = freshness

    def get(self, security_id: SecurityId, domain: str, operation: str, params: dict) -> DataResult | None:
        cache_key = self._build_key(security_id, domain, operation, params)
        collection = self._collection_name(domain, operation)
        doc = self.db[collection].find_one({"cache_key": cache_key})
        if doc is None:
            return None
        ttl = self.freshness.get_ttl(domain)
        if (datetime.utcnow() - doc["cached_at"]).total_seconds() > ttl:
            return None  # 已过期
        return self._doc_to_result(doc)

    def put(self, security_id, domain, operation, params, result: DataResult):
        cache_key = self._build_key(security_id, domain, operation, params)
        collection = self._collection_name(domain, operation)
        doc = {
            "cache_key": cache_key,
            "security_id": str(security_id),
            "domain": domain,
            "operation": operation,
            "params_hash": hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest(),
            "data": result.to_dict()["data"],
            "provider": result.provider,
            "fetched_at": result.fetched_at,
            "data_date": result.data_date,
            "freshness": result.freshness,
            "quality_score": result.quality_score,
            "source_trace": result.source_trace,
            "schema_version": "1.0",
            "cached_at": datetime.utcnow(),
        }
        self.db[collection].update_one(
            {"cache_key": cache_key},
            {"$set": doc},
            upsert=True
        )

    def _collection_name(self, domain: str, operation: str) -> str:
        """映射到缓存集合名：如 market_data+kline_daily → 03_data_ud_cache_kline_daily"""
        return f"{self.prefix}{operation}"

    def _build_key(self, security_id, domain, operation, params):
        raw = f"{security_id}|{domain}|{operation}|{json.dumps(params, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def invalidate(self, security_id=None, domain=None):
        """批量失效缓存"""
```

**缓存策略**：
- **Read-through**：查询时先读缓存，未命中则走 provider，然后写入缓存。
- **Write-through**：provider fetch 成功后立即写缓存。
- **缓存集合命名**：`03_data_ud_cache_{operation}` 如 `03_data_ud_cache_kline_daily`、`03_data_ud_cache_financial`。
- **缓存隔离**：`03_data_ud_cache_` 前缀确保与 TA-CN/portfolio 集合在同一物理库中通过命名空间隔离。物化数据（`03_data_ud_*` 非缓存）与 Query Cache（`03_data_ud_cache_*`）使用不同子前缀区分语义层级：物化数据可追溯、Query Cache 可丢弃。

### 8.3 FreshnessPolicy

```python
class FreshnessPolicy:
    DEFAULT_TTLS = {
        "market_data": 21600,       # 6h（日线当日收盘后刷新）
        "financial": 86400,         # 24h（季度数据，极少变化）
        "valuation": 43200,         # 12h
        "flow": 43200,              # 12h
        "sentiment": 3600,          # 1h（盘中快照变化快）
        "sector": 21600,            # 6h
        "news": 3600,               # 1h
        "calendar": 604800,         # 7d
        "metadata": 604800,         # 7d
        "events": 86400,            # 24h
    }

    def get_ttl(self, domain: str) -> int:
        return self.DEFAULT_TTLS.get(domain, 3600)

    def label(self, fetched_at, data_date, domain, from_cache) -> FreshnessLabel:
        if not from_cache:
            age = (datetime.utcnow() - fetched_at).total_seconds()
            if age < 60:
                return "realtime"
            if age < 900:  # 15 min
                return "delayed"
            return "cached"  # 来自 provider 但非实时
        # 缓存的数据
        ttl = self.get_ttl(domain)
        age = (datetime.utcnow() - fetched_at).total_seconds()
        if age > ttl:
            return "stale"
        return "cached"
```

### 8.4 增量刷新与批量回填边界

- **增量刷新**：task_center 调度定时任务，每天收盘后调用 `market_data_service.refresh_kline_daily(date=today)` 刷新当日日线。
- **批量回填**：通过 CLI 或一次性 task_center 任务触发，如 `unified_data.refresh_kline_daily(start="2020-01-01", end="2026-06-30")`。批量回填不走 provider fallback（避免大量失败记录），指定单一 provider。
- **缓存失效**：增量刷新完成后，主动调用 `CacheManager.invalidate(domain="market_data")` 失效相关缓存。

---

## 9. Quality / Audit 设计

### 9.1 QualityScorer

```python
class QualityScorer:
    def score(self, data: pd.DataFrame, metadata: dict) -> QualityReport:
        completeness = 1.0 - (data.isna().sum().sum() / (len(data) * len(data.columns)))
        missing_rate = data[["open", "high", "low", "close", "volume"]].isna().any(axis=1).mean()
        stale_flag = metadata.get("stale", False)
        abnormal_count = self._detect_abnormal(data)

        quality_score = (
            completeness * 0.4 +
            (1 - missing_rate) * 0.3 +
            (0.0 if stale_flag else 0.2) +
            (max(0, 1 - abnormal_count / len(data)) if len(data) > 0 else 0) * 0.1
        )

        return QualityReport(
            completeness=completeness,
            missing_rate=missing_rate,
            stale_flag=stale_flag,
            source_conflict=False,
            abnormal_value_count=abnormal_count,
            quality_score=min(quality_score, 1.0),
            provider=metadata.get("provider", "unknown"),
            last_fetched_at=metadata.get("fetched_at"),
            warnings=[],
        )

    def _detect_abnormal(self, df: pd.DataFrame) -> int:
        """检测异常值：pct_chg > 11%、price < 0.01、volume 突变为 0 等"""
        abnormal = 0
        if "pct_chg" in df.columns:
            abnormal += (df["pct_chg"].abs() > 11).sum()  # 非ST股票正常涨跌幅±10%
        if "close" in df.columns:
            abnormal += (df["close"] < 0.01).sum()
        if "volume" in df.columns:
            abnormal += (df["volume"] == 0).sum()
        return abnormal
```

### 9.2 AuditLogger

```python
class AuditLogger:
    def __init__(self, mongo_db, collection="03_data_ud_query_audit"):
        self.collection = mongo_db[collection]

    def log(self, request: DataRequest, result: DataResult | None, attempts: list[ProviderAttempt], error: Exception | None = None):
        try:
            doc = {
                "query_id": str(uuid.uuid4()),
                "consumer": request.consumer,
                "domain": request.domain,
                "operation": request.operation,
                "security_id": str(request.security_id),
                "params_hash": hashlib.md5(json.dumps(request.params, sort_keys=True).encode()).hexdigest(),
                "provider_chain": [f"{a.provider_name}({a.status})" for a in attempts],
                "elapsed_ms": sum(a.elapsed_ms for a in attempts),
                "cache_hit": request.force_refresh == False and any(a.provider_name == "cache" for a in attempts),
                "freshness_label": result.freshness if result else None,
                "quality_score": result.quality_score if result else None,
                "status": "success" if result else "failed",
                "error": str(error) if error else None,
                "queried_at": datetime.utcnow(),
            }
            self.collection.insert_one(doc)
            # 设置 TTL 索引（90天后自动删除）
        except Exception:
            pass  # 审计写入失败不影响查询
```

### 9.3 Quality Summary 生成

- **粒度**：每 domain × security_id × 天一条记录。
- **触发**：缓存写入后异步更新（不阻塞查询）。
- **用途**：供 stock framework 的 `data_quality` 维度读取，也供报告模块展示数据质量。

---

## 10. 与 task_center 的接口

### 10.1 总体边界

| 维度 | task_center | unified_data |
|---|---|---|
| 职责 | 任务注册、调度、状态管理 | 暴露刷新操作和域任务定义 |
| 交互 | task_center 调用 unified_data 的刷新函数 | unified_data 注册 Task → task_center 调度 |
| 依赖 | 不 import unified_data（通过 callable 路径间接调用） | 不 import task_center（通过 tasks/ 模块暴露 callable） |

### 10.2 数据刷新任务类型清单

| 任务 ID | 名称 | 域 | 调度建议 | Phase |
|---|---|---|---|---|
| `unified_data.daily_kline_cn` | A股日线行情刷新 | market_data | 每个交易日 15:30 | Phase 5 |
| `unified_data.realtime_quotes_cn` | 实时行情快照 | market_data | 盘中每5分钟 | Phase 5 |
| `unified_data.financial_refresh` | 财务数据刷新 | financial | 每周一次 | Phase 5 |
| `unified_data.daily_basic_cn` | A股估值指标刷新 | valuation | 每个交易日 16:00 | Phase 5 |
| `unified_data.trading_calendar_refresh` | 交易日历刷新 | calendar | 每年初/季度初 | Phase 5 |
| `unified_data.sector_snapshot_cn` | 板块快照刷新 | sector | 每个交易日 16:30 | Phase 5 |
| `unified_data.sentiment_snapshot_cn` | 市场情绪快照刷新 | sentiment | 每个交易日 15:30 | Phase 5 |
| `unified_data.capital_flow_cn` | 资金流刷新 | flow | 每个交易日 16:00 | Phase 5 |
| `unified_data.dragon_tiger_cn` | 龙虎榜刷新 | events | 每个交易日 17:00 | Phase 5 |
| `unified_data.chip_distribution_cn` | 筹码分布刷新 | events | 每周一次 | Phase 5 |
| `unified_data.quality_summary` | 数据质量汇总 | quality | 每天一次 | Phase 5 |
| `unified_data.audit_cleanup` | 审计日志清理 | audit | 每周一次 | Phase 5 |

### 10.3 任务注册示例

```python
# skills/data/unified_data/tasks/refresh_daily_kline.py
from task_center import register_task

@register_task(
    task_id="unified_data.daily_kline_cn",
    name="A股日线行情刷新",
    description="批量刷新A股日线行情数据（D1）",
    module="unified_data",
    retry_policy_id="data_refresh",
    tags=["数据", "日线", "A股"],
)
def refresh_daily_kline_cn(date: str | None = None, securities: list[str] | None = None):
    """由 task_center 调度执行"""
    from unified_data.services.market_data_service import MarketDataService
    service = MarketDataService()
    return service.batch_refresh_kline_daily(date=date, securities=securities)
```

### 10.4 刷新操作接口

unified_data 暴露给 task_center 调用的核心刷新操作：

```python
# unified_data/tasks/__init__.py 暴露的 callable 集合
# 每个 callable 返回 dict: {"success": int, "failed": int, "errors": list[str], "elapsed_seconds": float}

REFRESH_TASKS = {
    "unified_data.daily_kline_cn": "refresh_daily_kline.refresh_daily_kline_cn",
    "unified_data.realtime_quotes_cn": "refresh_realtime_quotes.refresh_realtime_quotes_cn",
    # ...
}
```

---

## 11. 与 Stock Framework 的接口

### 11.1 总体边界

| 维度 | stock framework | unified_data |
|---|---|---|
| 依赖方向 | stock → unified_data（单向） | |
| 接口形式 | stock 通过 `from unified_data import UnifiedDataClient` 获取数据 | unified_data 不依赖 stock |
| 禁止 | stock 不直接 import Tushare / AKShare 等 provider 库 | |

### 11.2 StockQuantProfile 所需数据域 → unified_data 映射

| Profile 维度组 | unified_data 域 | 调用示例 | 数据缺失处理 |
|---|---|---|---|
| 基本面 | metadata + financial | `client.get_stock_info(sid)` + `client.get_financial_metrics(sid)` | data_gaps 记录 |
| 成长 | financial + valuation | `client.get_income_statement(sid)` + 框架内计算 YoY | data_gaps 记录 |
| 估值 | valuation | `client.get_valuation_snapshot(sid)` | data_gaps + null |
| 质量 | financial | `client.get_financial_metrics(sid)` | data_gaps + null |
| 技术 | market_data | `client.get_kline_daily(sid, limit=250)` | data_gaps + null |
| 资金流 | flow | `client.get_capital_flow(sid, limit=60)` (Phase 3+) | data_gaps 降级 |
| 情绪 | sentiment + news | `client.get_market_sentiment()` + `client.get_news(sid)` (Phase 3+) | data_gaps 降级 |
| 催化剂 | news + calendar | `client.get_news(sid)` + `client.get_earnings_calendar(sid)` | data_gaps 降级 |
| 风险 | market_data + financial | K 线波动率 + 财务排雷指标 | data_gaps 记录 |
| 数据质量 | quality | `client.get_quality_summary(sid)` | 使用 DataResult.quality_score |

### 11.3 数据缺口处理协议

当 unified_data 某个域不可用时，返回的 `DataResult` 标记 `freshness="empty"` 且 `warnings` 包含具体缺口原因。stock framework 收到后：

1. Profile 对应维度标记 `null`。
2. 在 `data_quality` 维度记录 `data_gaps: ["fundamental", "valuation"]`。
3. 所有 ModelScore 的 `data_gaps` 字段列出受影响维度。
4. CrossValidationMatrix 降权处理缺失维度的模型。

**关键原则**：返回 `data_gaps` 而不是编造数据。

### 11.4 UnifiedDataClient API（供 stock framework 使用）

```python
# skills/data/unified_data/client.py

class UnifiedDataClient:
    """消费方统一入口"""

    # === 行情域 ===
    def get_kline_daily(self, security_id, start_date=None, end_date=None, limit=120, adjust="qfq",
                        provider=None, force_refresh=False) -> DataResult: ...
    def get_kline_weekly(self, ...) -> DataResult: ...
    def get_kline_monthly(self, ...) -> DataResult: ...
    def get_realtime_quote(self, security_id) -> DataResult: ...

    # === 财务域 ===
    def get_income_statement(self, security_id, period=None) -> DataResult: ...
    def get_balance_sheet(self, security_id, period=None) -> DataResult: ...
    def get_cash_flow(self, security_id, period=None) -> DataResult: ...
    def get_financial_metrics(self, security_id) -> DataResult: ...

    # === 估值域 ===
    def get_daily_basic(self, security_id, date=None) -> DataResult: ...
    def get_valuation_snapshot(self, security_id) -> DataResult: ...

    # === 日历域 ===
    def get_trading_days(self, market, start_date, end_date) -> DataResult: ...
    def is_trading_day(self, market, date) -> bool: ...

    # === 元数据域 ===
    def get_stock_list(self, market) -> DataResult: ...
    def get_stock_info(self, security_id) -> DataResult: ...
    def get_index_list(self, market) -> DataResult: ...
    def get_index_info(self, index_id) -> DataResult: ...
    def get_index_members(self, index_id) -> DataResult: ...
    def get_industry_members(self, industry_code) -> DataResult: ...

    # === 指数/板块域（读 TA-CN index_basic_info / index_daily_quotes / stock_sector_info）===
    def get_index_daily(self, index_id, start_date=None, end_date=None, limit=120) -> DataResult: ...
    def get_sector_index_bars(self, sector_code, start_date=None, end_date=None, limit=120) -> DataResult: ...
    def get_stock_sector(self, security_id, classify_system=None) -> DataResult: ...
    def get_stocks_by_sector(self, sector_code, classify_system=None) -> DataResult: ...

    # === 新闻域 ===
    def get_news(self, security_id, limit=20) -> DataResult: ...

    # === 资金流（Phase 3+）===
    def get_capital_flow(self, security_id, limit=60) -> DataResult: ...

    # === 情绪/板块（Phase 3+）===
    def get_market_sentiment(self, date=None) -> DataResult: ...
    def get_sector_snapshot(self, sector_code=None, date=None) -> DataResult: ...
    def get_sector_ranking(self, date=None) -> DataResult: ...

    # === 事件（Phase 4+）===
    def get_dragon_tiger(self, security_id=None, date=None) -> DataResult: ...
    def get_chip_distribution(self, security_id) -> DataResult: ...

    # === 质量 ===
    def get_quality_summary(self, security_id, domain=None) -> DataResult: ...

    # === 批量查询 ===
    def batch_get_kline_daily(self, security_ids: list[SecurityId], ...) -> dict[SecurityId, DataResult]: ...
```

---

## 12. 分阶段实现路线

### Phase 0：骨架 + 核心抽象（预计 1-2 天）

**范围**：
- `SecurityId` 值对象 + 转换映射表（内存）
- `DataResult` / `DataRequest` dataclass
- `ProviderCapability` + `ProviderAttempt` dataclass
- `QualityReport` dataclass
- `DataProvider` 抽象基类
- `exceptions.py` 异常体系
- 目录结构骨架 + `__init__.py` + `SKILL.md`
- pytest fixture scaffold

**产物**：
- `skills/data/unified_data/models/` 下 6 个文件
- `skills/data/unified_data/providers/base.py`
- `skills/data/unified_data/exceptions.py`
- `skills/data/unified_data/SKILL.md`
- `tests/unified_data/` 初始测试

**验收标准**：
- SecurityId 构造、转换、相等性测试通过
- DataResult 序列化/反序列化测试通过
- DataProvider 接口可被继承

**风险**：低
**是否需要 Verify/Review**：否（Phase 0 无业务逻辑）

---

### Phase 1：核心读取 Adapter + Provider（预计 4-7 天）

Phase 1 是读优先统一访问层的落地阶段，细分为 1A / 1B / 1C 三个子阶段，严格顺序依赖：
**1A → 1B → 1C**。1A 只做 TA-CN 只读 adapter + 服务层，不引入外部 provider 和缓存，确保最小
可验证骨架先行；1B 在此基础上补齐外部 provider、缓存、新鲜度；1C 完善测试与端到端验收。

---

#### Phase 1A：TA-CN read-only adapter for core A-share + index/sector data（预计 2-3 天）

**范围**：
- TA-CN MongoDB adapter（只读，覆盖 §5.1 强复用层全部 8 个 TA-CN MongoDB 集合）：
  - `stock_basic_info`
  - `market_quotes`（实时行情快照，只读 adapter 映射为 `RealtimeQuote` canonical）
  - `stock_daily_quotes`
  - `stock_financial_data`
  - `stock_news`
  - `index_basic_info`
  - `index_daily_quotes`
  - `stock_sector_info`
- canonical domain objects 对应落地：`StockInfo` / `DailyBar` / `FinancialStatement` / `NewsItem` /
  `IndexInfo` / `IndexDailyBar` / `SectorClassification` / `RealtimeQuote`
- domain services 骨架（方法签名 + TA-CN adapter 调用，暂不接 provider / cache）：
  - `metadata_service`：`get_stock_list()` / `get_stock_info()` / `get_index_list()` / `get_index_info()` / `get_index_members()` / `get_industry_members()`
  - `market_data_service`：`get_kline_daily()` / `get_realtime_quote()` / `get_index_daily()`
  - `fundamental_service`：`get_income_statement()` / `get_balance_sheet()` / `get_cash_flow()`
  - `sector_service`：`get_stock_sector()` / `get_stocks_by_sector()` / `get_sector_index_bars()`
  - `event_service`：`get_news()`
- `UnifiedDataClient` facade：行情 / 财务 / 估值 / 日历 / 元数据 / 新闻 / 指数 / 板块域入口

**Phase 1A 明确不做（留待 Phase 1B/1C 或后续 Phase）**：
- 外部 API 调用（Tushare / AKShare provider 的实时 fetch）— Phase 1B
- `CacheManager` / `FreshnessPolicy` — Phase 1B
- MongoDB 写入或新增集合（Phase 1A adapter 只读，不写任何集合）
- **`DSA SQLite / StockDaily adapter` — 不实现（DSA 不是运行时数据源；本节作为对历史术语的反向澄清）**
- `task_center` 集成 — Phase 5
- stock framework profile/model 集成 — Phase 6

**产物**：
- `skills/data/unified_data/adapters/ta_cn_mongo_adapter.py`
- `skills/data/unified_data/models/domain/` 全部 canonical object 文件（market_data / financial / valuation / sector / news / calendar / metadata）
- `skills/data/unified_data/services/` 5 个服务文件
- `skills/data/unified_data/client.py`（1A 基础版，只接 TA-CN adapter）

**验收标准**：
- 通过 `UnifiedDataClient.get_kline_daily(SecurityId("CN","600519"))` 获取 A 股日线行情，DataResult 包含正确 provider/freshness/source_trace
- 通过 `UnifiedDataClient.get_index_daily()` 读取 `index_daily_quotes`，返回 `IndexDailyBar` canonical
- 通过 `UnifiedDataClient.get_stock_sector()` / `get_stocks_by_sector()` 读取 `stock_sector_info`，返回 `SectorClassification` canonical
- SecurityId 多种格式输入均可正确转换
- 不修改 TA-CN / DSA / Argus / portfolio 任何代码
- 不新增 MongoDB 集合，不写入任何集合
- 单元测试覆盖率 ≥ 60%（TA-CN adapter 映射 + canonical object 转换）

**风险**：低-中（MongoDB 连接、TA-CN 数据可用性）
**是否需要 Verify/Review**：是

---

### Phase 1A 详细设计（T2 交付物 — 供 T3 实现蓝本）

> 以下为 Phase 1A 落地到 T3 实现者所需的精确文件清单、接口签名、字段映射、异常/空值转换、服务→adapter 调用矩阵和测试策略。
> 事实来源：T1 `t_6b116199` final_collection_scope（8 个 TA-CN MongoDB 只读集合）。

#### 1A.1 精确文件清单

Phase 1A 新建/修改文件按目录分组（目录级 + 文件级）：

```
skills/data/unified_data/
├── __init__.py                        [修改] 导出 Phase 1A 公共符号（见 1A.9）
├── client.py                          [修改] 扩展 Phase 0 facade：新增 14 个客户端入口方法
│
├── adapters/
│   ├── __init__.py                    [新建] 导出 TA_CNMongoAdapter
│   └── ta_cn_mongo_adapter.py         [新建] TA-CN 只读 MongoDB adapter（核心）
│
├── models/
│   └── domain/
│       ├── __init__.py                [新建] 导出全部 Phase 1A canonical objects
│       ├── market_data.py             [新建] RealtimeQuote / DailyBar / IndexDailyBar
│       ├── financial.py               [新建] FinancialStatement
│       ├── news.py                    [新建] NewsItem
│       ├── sector.py                  [新建] SectorClassification
│       └── metadata.py                [新建] StockInfo / IndexInfo
│
└── services/
    ├── __init__.py                    [新建] 导出 5 个服务
    ├── market_data_service.py         [新建] get_kline_daily / get_realtime_quote / get_index_daily
    ├── fundamental_service.py         [新建] get_income_statement / get_balance_sheet / get_cash_flow
    ├── sector_service.py              [新建] get_stock_sector / get_stocks_by_sector / get_sector_index_bars
    ├── event_service.py               [新建] get_news
    └── metadata_service.py            [新建] get_stock_list / get_stock_info / get_index_list / get_index_info

tests/data/unified_data/
├── test_ta_cn_mongo_adapter.py        [新建] adapter 字段映射 + 空数据 + 异常
├── test_domain_objects.py             [新建] 8 个 canonical object 构造与边界
├── test_services.py                   [新建] 5 个服务（mock adapter）
├── test_client_phase1a.py             [新建] UnifiedDataClient 1A 入口
└── fixtures/
    ├── __init__.py                    [新建]
    └── ta_cn_mock_docs.py             [新建] 8 集合典型 MongoDB 文档 fixture
```

**明确标注不创建（Phase 1B+ 或明确禁止）：**
- `providers/` — Phase 1A 不创建 provider 目录，无 `ta_cn_adapter.py` provider（Phase 1B 创建 `TA-CNAdapterProvider`）
- `cache/` — Phase 1A 不创建 cache 目录
- **`dsa_sqlite_adapter.py` — 不创建（DSA 不是运行时数据源；不实现任何 DSA adapter；不作为 unified_data 内部读取源、不出现在 `external_fallback_chains`）**
- `portfolio_adapter.py` — Phase 2
- `config/` 下 YAML — Phase 1B
- `tasks/` 目录 — Phase 5

#### 1A.2 TA_CNMongoAdapter 详细设计

**连接注入边界：**
- `TA_CNMongoAdapter` 不自行创建 MongoDB client（pymongo `MongoClient` 或 motor `AsyncIOMotorDatabase`）。
- 构造函数接受一个已初始化的 `db` 句柄（`pymongo.database.Database`），由调用方（`UnifiedDataClient` 工厂或测试 fixture）注入。
- 适配 motor async（生产）与 pymongo sync（测试 fixture）的差异：adapter 暴露**同步接口**签名，内部统一调用 `db[collection].find()/find_one()`；若注入的是 motor async 句柄，由上层在 Phase 1B 统一处理 async 包装。Phase 1A 实现与测试均使用 pymongo sync 句柄，保证 fixture 可用 `mongomock` 或内存 dict 替身。
- **adapter 绝不在构造或读取时自动执行 `create_index`、`create_collection` 或任何写入操作。**

**集合查询接口（8 个方法，与 T1 final_collection_scope 1:1）：**

```python
from __future__ import annotations
from typing import Any
from datetime import datetime

class TA_CNMongoAdapter:
    """TA-CN MongoDB 只读 adapter。

    覆盖 8 个 TA-CN 生产集合，只做 find/find_one，不做写入。
    所有方法返回 list[dict] 或 dict（原始 MongoDB 文档），不做 canonical 映射
    （映射在 domain service 层完成）。返回 None 或空列表表示无数据。
    """

    DATABASE_NAME = "tradingagents"

    def __init__(self, db: Any) -> None:
        """注入已初始化的 pymongo Database 句柄。不做连接、不建索引。"""
        self._db = db

    # ── stock_basic_info ──────────────────────────────────────
    def get_stock_info(self, symbol: str, market: str = "CN") -> dict | None:
        """按 symbol 查询单只股票基础信息。返回原始文档或 None。"""

    def get_stock_list(self, market: str = "CN", status: str = "L",
                       limit: int = 0) -> list[dict]:
        """查询股票列表。status='L' 仅上市。limit=0 表示不限。"""

    # ── market_quotes ─────────────────────────────────────────
    def get_realtime_quotes(self, symbol: str) -> dict | None:
        """查询单只股票实时行情快照。返回原始文档或 None。"""

    # ── stock_daily_quotes ────────────────────────────────────
    def get_daily_bars(self, symbol: str, start_date: str | None = None,
                       end_date: str | None = None, limit: int = 120) -> list[dict]:
        """查询日线行情。start/end 格式 'YYYY-MM-DD'。按 trade_date 降序，limit 条。"""

    # ── stock_financial_data ──────────────────────────────────
    def get_financials(self, symbol: str, report_period: str | None = None) -> dict | None:
        """查询财务数据。report_period 格式 'YYYYMMDD'。返回原始文档或 None。"""

    # ── stock_news ────────────────────────────────────────────
    def get_news(self, symbol: str, limit: int = 20) -> list[dict]:
        """查询个股新闻。按 publish_time 降序。"""

    # ── index_basic_info ──────────────────────────────────────
    def get_index_info(self, symbol: str) -> dict | None:
        """查询单个指数基础信息。"""

    def get_index_list(self, market: str = "CN") -> list[dict]:
        """查询指数列表。"""

    # ── index_daily_quotes ────────────────────────────────────
    def get_index_daily_bars(self, symbol: str | None = None,
                             sector_code: str | None = None,
                             start_date: str | None = None,
                             end_date: str | None = None,
                             limit: int = 120) -> list[dict]:
        """查询指数日线。支持按 symbol（大盘指数）或 sector_code（申万行业指数）查询。"""

    # ── stock_sector_info ─────────────────────────────────────
    def get_stock_sector_info(self, full_symbol: str,
                              classify_system: str | None = None) -> list[dict]:
        """查询个股行业分类。classify_system 默认 'SW'。"""

    def get_stocks_by_sector(self, l1_code: str,
                             classify_system: str = "SW") -> list[dict]:
        """查询某申万一级行业下的全部个股。"""
```

**字段映射规则（8 集合 × canonical object）：**

映射在 domain service 层完成，不在 adapter 层。adapter 返回原始 MongoDB 文档（dict），service 层用 canonical object 的 `from_ta_cn_doc()` 类方法映射。

| 集合 | Canonical Object | from_ta_cn_doc() 映射要点 |
|---|---|---|
| `stock_basic_info` | `StockInfo` | `symbol`→symbol；`full_symbol`→full_symbol；`name`→name；`industry`→industry；`area`→area；`total_mv`→total_mv；`circ_mv`→circ_mv；`pe`/`pe_ttm`/`pb`/`pb_mrq`/`roe`→同名字段；`list_date`→list_date；`status`→status；`market_info`→market_info（透传 dict） |
| `market_quotes` | `RealtimeQuote` | `symbol`→symbol；`current_price`（或 `close`）→current_price；`change`→change；`change_percent`（或 `pct_chg`）→change_percent；`open`/`high`/`low`/`pre_close`/`volume`/`amount`→同名字段；`update_time`（或 `updated_at`/`timestamp`）→update_time |
| `stock_daily_quotes` | `DailyBar` | `symbol`→symbol；`trade_date`→trade_date；`open`/`high`/`low`/`close`/`pre_close`/`change`/`pct_chg`/`vol`→`volume`/`amount`/`turnover_rate`/`volume_ratio`→同名字段。注意：TA-CN 字段名可能为 `vol` 而非 `volume`，映射时 fallback：`doc.get('volume', doc.get('vol'))` |
| `stock_financial_data` | `FinancialStatement` | 外层 `symbol`/`report_period`/`report_type`；财务科目在 `raw_data` 嵌套字典内的 `income_statement`/`balance_sheet`/`cashflow_statement` 列表中，按 `end_date` 降序取最新。`statement_type` 由 service 方法决定（income/balance/cashflow）。科目字段直接透传为 `items: dict[str,float]` |
| `stock_news` | `NewsItem` | `symbol`→symbol；`title`→title；`content`→content；`source`→source；`publish_time`→publish_time；`sentiment`→sentiment；`category`→category；`importance`→importance；`url`→url |
| `index_basic_info` | `IndexInfo` | `symbol`→symbol；`full_symbol`→full_symbol；`name`→name；`fullname`→fullname；`market`→market；`publisher`→publisher；`category`→category |
| `index_daily_quotes` | `IndexDailyBar` | `sector_code`（或 `code`/`symbol`）→symbol；`trade_date`→trade_date；`open`/`high`/`low`/`close`/`pct_chg`/`volume`（或 `vol`）/`amount`→同名字段；`source`→data_source |
| `stock_sector_info` | `SectorClassification` | `full_symbol`→full_symbol；`classify_system`→classify_system；`l1_code`/`l1_name`/`l2_code`/`l2_name`/`l3_code`/`l3_name`→同名字段；`datasource`→datasource；`update_at`→update_at |

**日期输入格式：**
- 所有日期参数统一接受 `'YYYY-MM-DD'` 字符串（如 `'2026-07-13'`）。
- adapter 内部查询 MongoDB 时，将 `'YYYY-MM-DD'` 转为 `'YYYYMMDD'` 格式匹配 TA-CN 集合中 `trade_date` 字段的存储格式（TA-CN 存储为 `'20260713'` 字符串）。
- `report_period` 参数接受 `'YYYYMMDD'`（如 `'20251231'`），与 TA-CN `stock_financial_data.report_period` 存储格式一致。

**字符串字段格式：**
- TA-CN 集合中日期字段（`trade_date`、`report_period`、`publish_time`、`list_date`）存储为字符串（`'YYYYMMDD'` 或 ISO datetime），不做 Python `date`/`datetime` 类型转换，直接透传为 `str`，由 canonical object 保留为 `str` 字段。

**排序 / limit：**
- `stock_daily_quotes`：按 `trade_date` 降序（最新在前），`limit` 条。
- `index_daily_quotes`：按 `trade_date` 降序，`limit` 条。
- `stock_news`：按 `publish_time` 降序，`limit` 条。
- `stock_basic_info` 列表：按 `symbol` 升序，`limit` 条。
- 其他单文档查询不排序。

**空数据 / 连接不可用 / 映射错误的转换规则：**

| 场景 | adapter 行为 | service → DataResult |
|---|---|---|
| 查询返回空列表 / None | 返回 `[]` 或 `None` | `DataResult.success(data=None/[])` → `freshness='empty'`, `provider='empty'` |
| MongoDB 连接异常（`ConnectionFailure` / `ServerSelectionTimeoutError`） | 不捕获，向上抛出 | service 捕获，返回 `DataResult.error(...)` → `freshness='empty'`, `provider='error'`, `source_trace=['ta_cn_adapter(error: ...)]']` |
| 文档字段缺失（`KeyError` / `None`） | adapter 不抛异常（使用 `doc.get(field)`），canonical `from_ta_cn_doc()` 用 `None` 填充 | 正常 `DataResult.success()`，字段为 `None` |
| 映射逻辑异常（`ValueError` / `TypeError`） | `from_ta_cn_doc()` 抛出 | service 捕获，返回 `DataResult.error(...)` |

#### 1A.3 Canonical Domain Object 边界

Phase 1A 新建 8 个 canonical dataclass，均位于 `models/domain/`：

```python
# models/domain/market_data.py
@dataclass
class RealtimeQuote:
    symbol: str
    current_price: float | None
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    pre_close: float | None = None
    volume: float | None = None
    amount: float | None = None
    update_time: str | None = None

@dataclass
class DailyBar:
    symbol: str
    trade_date: str              # 'YYYY-MM-DD'
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    pre_close: float | None = None
    change: float | None = None
    pct_chg: float | None = None
    volume: float | None = None
    amount: float | None = None
    turnover_rate: float | None = None
    volume_ratio: float | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "DailyBar":
        """从 stock_daily_quotes 文档映射。宽松：doc.get(field) 不抛 KeyError。"""

@dataclass
class IndexDailyBar:
    symbol: str
    trade_date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    pct_chg: float | None = None
    volume: float | None = None
    amount: float | None = None
    data_source: str = ""

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "IndexDailyBar": ...
```

```python
# models/domain/metadata.py
@dataclass
class StockInfo:
    symbol: str
    full_symbol: str
    name: str
    industry: str | None = None
    area: str | None = None
    total_mv: float | None = None
    circ_mv: float | None = None
    pe: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    pb_mrq: float | None = None
    roe: float | None = None
    list_date: str | None = None
    status: str | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "StockInfo": ...

@dataclass
class IndexInfo:
    symbol: str
    full_symbol: str
    name: str
    fullname: str | None = None
    market: str | None = None
    publisher: str | None = None
    category: str | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "IndexInfo": ...
```

```python
# models/domain/financial.py
@dataclass
class FinancialStatement:
    symbol: str
    report_period: str           # 'YYYYMMDD'
    statement_type: str          # 'income' / 'balance' / 'cashflow'
    items: dict[str, float]      # 科目名 → 金额
    currency: str = "CNY"

    @classmethod
    def from_ta_cn_doc(cls, doc: dict, statement_type: str) -> "FinancialStatement":
        """从 stock_financial_data 文档映射。doc['raw_data'][statement_type+'_statement']
        是按 end_date 排序的列表，取最新一期。"""
```

```python
# models/domain/news.py
@dataclass
class NewsItem:
    symbol: str | None
    title: str
    content: str | None = None
    source: str | None = None
    publish_time: str | None = None
    sentiment: str | None = None
    category: str | None = None
    importance: str | None = None
    url: str | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "NewsItem": ...
```

```python
# models/domain/sector.py
@dataclass
class SectorClassification:
    full_symbol: str
    classify_system: str
    l1_code: str
    l1_name: str
    l2_code: str | None = None
    l2_name: str | None = None
    l3_code: str | None = None
    l3_name: str | None = None
    datasource: str = "tushare"
    update_at: str | None = None

    @classmethod
    def from_ta_cn_doc(cls, doc: dict) -> "SectorClassification": ...
```

**DataResult 封装（与 Phase 0 契约 100% 兼容）：**

```python
# 在 service 层统一封装
def _wrap_success(self, data, security_id, domain, operation):
    return DataResult.success(
        data=data,
        security_id=security_id,
        domain=domain,
        operation=operation,
        provider="ta_cn_adapter",
        source_trace=["ta_cn_adapter(ok)"],
    )

def _wrap_empty(self, security_id, domain, operation):
    return DataResult.success(
        data=None,
        security_id=security_id,
        domain=domain,
        operation=operation,
        provider="empty",
        source_trace=["ta_cn_adapter(ok)"],
    )

def _wrap_error(self, security_id, domain, operation, error):
    return DataResult.error(
        security_id=security_id,
        domain=domain,
        operation=operation,
        provider="ta_cn_adapter",
        error=error,
    )
```

- 成功非空：`freshness='delayed'`, `provider='ta_cn_adapter'`, `source_trace=['ta_cn_adapter(ok)']`
- 空结果：`freshness='empty'`, `provider='empty'`, `source_trace=['ta_cn_adapter(ok)']`
- MongoDB 不可用：`freshness='empty'`, `provider='error'`, `source_trace=['ta_cn_adapter(error: <msg>)']`

#### 1A.4 服务→adapter 调用流与完整矩阵

每个 service 方法遵循统一调用流：

```
Client API → Service.method(security_id, **params)
  → SecurityId.symbol 提取
  → TA_CNMongoAdapter.get_xxx(symbol, ...) 获取原始文档
  → CanonicalObject.from_ta_cn_doc(doc) 映射
  → DataResult.success/error 封装
  → 返回 DataResult
```

**完整 collection × canonical × service × client 矩阵（以 T1 final_collection_scope 为唯一事实）：**

| # | 集合 | Adapter 方法 | Canonical Object | Service 入口 | Client API |
|---|---|---|---|---|---|
| 1 | `stock_basic_info` | `get_stock_info(symbol)` | `StockInfo` | `metadata_service.get_stock_info(sid)` | `client.get_stock_info(sid)` |
| 2 | `stock_basic_info` | `get_stock_list(market)` | `list[StockInfo]` | `metadata_service.get_stock_list(market)` | `client.get_stock_list(market)` |
| 3 | `market_quotes` | `get_realtime_quotes(symbol)` | `RealtimeQuote` | `market_data_service.get_realtime_quote(sid)` | `client.get_realtime_quote(sid)` |
| 4 | `stock_daily_quotes` | `get_daily_bars(symbol, start, end, limit)` | `list[DailyBar]` | `market_data_service.get_kline_daily(sid, start, end, limit)` | `client.get_kline_daily(sid, ...)` |
| 5 | `stock_financial_data` | `get_financials(symbol, period)` | `FinancialStatement` (type='income') | `fundamental_service.get_income_statement(sid, period)` | `client.get_income_statement(sid, period)` |
| 6 | `stock_financial_data` | `get_financials(symbol, period)` | `FinancialStatement` (type='balance') | `fundamental_service.get_balance_sheet(sid, period)` | `client.get_balance_sheet(sid, period)` |
| 7 | `stock_financial_data` | `get_financials(symbol, period)` | `FinancialStatement` (type='cashflow') | `fundamental_service.get_cash_flow(sid, period)` | `client.get_cash_flow(sid, period)` |
| 8 | `stock_news` | `get_news(symbol, limit)` | `list[NewsItem]` | `event_service.get_news(sid, limit)` | `client.get_news(sid, limit)` |
| 9 | `index_basic_info` | `get_index_info(symbol)` | `IndexInfo` | `metadata_service.get_index_info(sid)` | `client.get_index_info(sid)` |
| 10 | `index_basic_info` | `get_index_list(market)` | `list[IndexInfo]` | `metadata_service.get_index_list(market)` | `client.get_index_list(market)` |
| 11 | `index_daily_quotes` | `get_index_daily_bars(symbol=...)` | `list[IndexDailyBar]` | `market_data_service.get_index_daily(sid, ...)` | `client.get_index_daily(sid, ...)` |
| 12 | `index_daily_quotes` | `get_index_daily_bars(sector_code=...)` | `list[IndexDailyBar]` | `sector_service.get_sector_index_bars(sector_code, ...)` | `client.get_sector_index_bars(sector_code, ...)` |
| 13 | `stock_sector_info` | `get_stock_sector_info(full_symbol)` | `list[SectorClassification]` | `sector_service.get_stock_sector(sid, classify_system)` | `client.get_stock_sector(sid, classify_system)` |
| 14 | `stock_sector_info` | `get_stocks_by_sector(l1_code)` | `list[SectorClassification]` | `sector_service.get_stocks_by_sector(sector_code, classify_system)` | `client.get_stocks_by_sector(sector_code, classify_system)` |

> 注意：`stock_financial_data` 在集合层只有 1 个 adapter 方法 `get_financials()`，但映射为 3 个不同 `statement_type` 的 canonical object 和 3 个 service 入口。这是唯一的多入口集合。

#### 1A.5 测试策略

**三层测试，全部无网络依赖：**

**层 1：纯 fixture unit tests（必须）**

文件：`test_ta_cn_mongo_adapter.py` + `test_domain_objects.py`

- adapter 测试使用 `mongomock`（或内存 dict 替身）注入 db 句柄，预填典型文档。
- 每个 adapter 方法至少 2 个用例：正常文档返回 + 空结果返回。
- 每个 canonical `from_ta_cn_doc()` 至少 1 个用例：字段全部存在 + 部分字段缺失（None 填充不抛异常）。

**层 2：adapter mapping / service / client integration（必须，mock DB）**

文件：`test_services.py` + `test_client_phase1a.py`

- service 测试：注入 mock adapter（FakeTA_CNMongoAdapter），验证 `DataResult` 的 `provider`/`freshness`/`source_trace` 正确性。
- client 测试：注入 mock adapter 到 `UnifiedDataClient`，验证 8 个域入口方法的调用链。
- 覆盖空数据 → `freshness='empty'` 和异常 → `freshness='empty', provider='error'` 两个分支。

**层 3：真实 MongoDB read-only smoke（可选，默认不跑）**

文件：`test_smoke_mongodb.py`（标记 `@pytest.mark.network`）

- 连接真实 `tradingagents` 库，对每个集合执行 `find_one()`。
- **默认跳过**：需用户通过 `--run-network` 或环境变量 `UD_RUN_SMOKE=1` 显式启用。
- 验证 adapter 对真实文档 schema 的兼容性，不做断言（只验证不抛异常）。

**覆盖率目标与测量命令：**

```bash
# Phase 1A 覆盖率测量（仅新增文件）
PYTHONPATH=. pytest tests/data/unified_data \
  --cov=skills.data.unified_data.adapters \
  --cov=skills.data.unified_data.models.domain \
  --cov=skills.data.unified_data.services \
  --cov-report=term-missing \
  --cov-fail-under=60

# Phase 0 回归（不回归）
PYTHONPATH=. pytest tests/data/unified_data -q
```

阈值：**≥ 60%**（与 Phase 1A 验收标准一致）。

**fixture 文件结构（`tests/data/unified_data/fixtures/ta_cn_mock_docs.py`）：**

提供 8 个集合各 1-2 个典型 MongoDB 文档字典，供 unit/integration 测试共用。文档结构基于 TA-CN `stock_models.py` 和 `stock_data_models.py` 的字段定义。

#### 1A.6 回滚方式

Phase 1A 回滚零风险：
1. `git revert` Phase 1A 的全部提交（仅新增 `adapters/`、`models/domain/`、`services/`、修改 `client.py` 和 `__init__.py`）。
2. 无 MongoDB 集合变更、无 schema 变更、无 cron/systemd 变更、无外部依赖变更。
3. Phase 0 的 106 passed 测试不受影响（新增文件不影响已有导入）。

#### 1A.7 残余风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| TA-CN 集合字段名与文档不一致（schema drift） | 中 | 中 | `from_ta_cn_doc()` 使用 `doc.get(field)` 宽松策略；smoke test 验证 |
| `stock_financial_data` 的 `raw_data` 嵌套结构复杂 | 中 | 中 | 映射逻辑容错：取 `raw_data.get(statement_type+'_statement', [])` 列表最新一期 |
| `market_quotes` 字段名 `current_price` vs `close` 不统一 | 中 | 低 | 映射 fallback：`doc.get('current_price', doc.get('close'))` |
| `index_daily_quotes` 中 `sector_code` 字段名不统一（可能为 `code`/`symbol`） | 中 | 低 | adapter 查询支持多字段名 fallback |
| motor async vs pymongo sync 差异 | 低 | 中 | Phase 1A 统一使用 sync pymongo 接口；async 包装属 Phase 1B |

#### 1A.8 IN / OUT 边界

**IN（Phase 1A 交付）：**
- `TA_CNMongoAdapter`（8 个只读查询方法）
- 8 个 canonical domain objects（含 `from_ta_cn_doc()` 映射）
- 5 个 domain services（14 个方法入口）
- `UnifiedDataClient` 扩展（14 个域入口方法）
- 纯 fixture unit tests + mock DB integration tests
- 覆盖率 ≥ 60%

**OUT（Phase 1A 明确不做）**：
- 外部 API provider（Tushare / AKShare）— Phase 1B
- `CacheManager` / `FreshnessPolicy` — Phase 1B
- `LocalMongoAdapter`（物化数据查询）— Phase 1B
- MongoDB 写入 / 集合创建 / 索引创建 — 禁止
- `task_center` 集成 — Phase 5
- stock framework 集成 — Phase 6
- DSA SQLite adapter — **不实现**（DSA 不是运行时数据源）
- 真实 MongoDB smoke test 默认执行 — 可选，默认跳过

---

#### Phase 1B：External Provider + Cache + Freshness（预计 1-2 天）

**范围**：
- `TushareProvider` + `AKShareProvider` 实现（行情/财务/估值/日历/元数据/指数/新闻域）
- `ProviderRegistry` + `DataRouter` 基础版（external fallback 链，internal-first 路径）
- `CacheManager` + `FreshnessPolicy` 基础版（MongoDB `03_data_ud_cache_*` 写入）
- `LocalMongoAdapter`（读取 Unified Data 物化集合 `03_data_ud_*`）
- `UnifiedDataClient` 接入 internal-first 读取路径 + 外部 provider fallback + 缓存层

**产物**：
- `skills/data/unified_data/providers/` 2 个文件（tushare / akshare）
- `skills/data/unified_data/router/` 2 个文件
- `skills/data/unified_data/cache/` 2 个文件
- `skills/data/unified_data/adapters/local_mongo_adapter.py`（物化数据查询）

**验收标准**：
- internal-first 读取路径验证通过：TA-CN 既有数据优先 → UD 物化数据 → Query Cache → 外部 Provider fallback
- Tushare → AKShare 外部 fallback 链验证通过
- 缓存命中时返回 `freshness=cached` 标签，不调 provider
- 缓存写入到 `03_data_ud_cache_*` 集合，前缀隔离正确
- `FreshnessPolicy` 按 domain 自动 TTL 失效
- 外部 Provider 全部失败时返回 `DataResult.error(...)`，不阻断已有内部数据读取

**风险**：中（Tushare token 配额、MongoDB 连接）
**是否需要 Verify/Review**：是

---

#### Phase 1C：端到端验收 + 测试补齐（预计 1-2 天）

**范围**：
- 端到端集成测试：query → cache miss → provider → cache write → return
- 端到端集成测试：query → cache hit → return（不调 provider）
- 端到端集成测试：query → provider fail → fallback → success
- 端到端集成测试：query → all providers fail → `DataResult.error(provider="error", source_trace=[...])`（**Phase 1B-A 起新契约**：Router 对调用方返回错误结果，不抛 `AllProvidersFailedError`；Phase 0 旧基线以 `AllProvidersFailedError` 为出口，仅作历史描述保留）
- 单元测试覆盖率补齐至 ≥ 60%
- index 域端到端覆盖（Phase 1A 的 adapter 读取 + Phase 1B 的 provider 兜底）；`stock_sector_info` 因缺少 canonical Router capability 与已验证的 external fallback，不在 1C Router E2E 范围（仍由 Phase 1A `SectorService` + TA-CN adapter direct read 覆盖）

**产物**：
- `tests/data/unified_data/` 完整测试套件

**验收标准**：
- 上述 4 条端到端路径全部通过
- index_basic_info / index_daily_quotes 的 adapter + provider 双路径覆盖；stock_sector_info 的 Router E2E 不在 1C 范围（仍由 Phase 1A SectorService + TA-CN adapter direct read 覆盖）
- 测试覆盖率 ≥ 60%

**风险**：低
**是否需要 Verify/Review**：是

---

### Phase 2：Provider Registry 增强 + Quality + Audit（预计 2-3 天）

**范围**：
- `ProviderRegistry` 完整实现（优先级、健康检测、后台刷新）
- `DataRouter` 完整 fallback 链
- `QualityScorer` 实现
- `AuditLogger` + `03_data_ud_query_audit` 集合创建
- `03_data_ud_quality_summary` 集合创建
- Cache 失效机制增强
- `unified_data_query_audit` + `unified_data_quality_summary` 集合创建

**产物**：
- `skills/data/unified_data/quality/` 2 个文件（完善）
- `skills/data/unified_data/router/` 增强
- 审计集合 schema 落地

**验收标准**：
- Fallback 链全部 provider 失败时 Router 返回 `DataResult.error(provider="error", source_trace=[...])`（含摘要），**不抛 `AllProvidersFailedError`**（Phase 1B-A 已确认的新对外契约；`AllProvidersFailedError` 保留为内部/历史兼容类型，不作为 1B+/1C 验收主语义）
- 查询审计记录正确写入 `03_data_ud_query_audit`
- QualityScorer 输出合理的 quality_score
- Provider 不可用时自动跳过（不阻塞后续 fallback）

**风险**：中（MongoDB 连接、集合创建需 Pascal 确认）
**是否需要 Verify/Review**：是

---

### Phase 3：重要持久化扩展（预计 3-5 天）

**范围**：
- `03_data_ud_market_sector_snapshot` 集合 + SectorService
- `03_data_ud_market_sentiment_snapshot` 集合 + SentimentService
- `03_data_ud_stock_capital_flow` 集合 + FlowService
- 技术指标计算与 `03_data_ud_cache_tech_indicator` 缓存
- AKShare 对应 fetcher 实现
- `YFinanceProvider` 基础版（港股/美股日线）
- 对应 canonical domain objects

**产物**：
- `skills/data/unified_data/collections/` 新增 3 个 schema 定义文件
- `skills/data/unified_data/services/` 新增 3 个服务
- `skills/data/unified_data/providers/yfinance_provider.py`
- 集合索引创建脚本

**验收标准**：
- sector/sentiment/capital_flow 数据通过 UnifiedDataClient 可查询
- 数据新鲜度标签正确
- raw_payload 策略生效（保留原始数据用于审计）
- MongoDB 集合创建成功，索引生效

**风险**：中-高（集合创建需 Pascal 确认、AKShare 反爬策略、数据量大）
**是否需要 Verify/Review**：是

---

### Phase 4：龙虎榜 + 筹码 + 热门股票（预计 2-3 天）

**范围**：
- `03_data_ud_stock_dragon_tiger_events` 集合 + DragonTigerService
- `03_data_ud_stock_chip_distribution` 集合 + ChipService
- `03_data_ud_market_hot_stock_snapshot` 集合（P1 可延后）

**产物**：
- `skills/data/unified_data/collections/` 新增 3 个 schema 定义文件
- `skills/data/unified_data/services/` 新增 2 个服务

**验收标准**：
- 龙虎榜数据可查询，含买入/卖出席位明细
- 筹码分布数据可查询，含集中度、获利比例
- 与 Phase 3 集合不冲突

**风险**：中（AKShare 接口稳定性）
**是否需要 Verify/Review**：否（低风险业务扩展）

---

### Phase 5：task_center 集成（预计 2-3 天）

**范围**：
- `tasks/` 目录下所有刷新任务 callable
- task_center 注册 Task + 创建 Job
- 增量刷新与批量回填 CLI
- 调度器启动脚本

**产物**：
- `skills/data/unified_data/tasks/` 8 个刷新任务文件
- `scripts/unified_data_scheduler.py`
- task_center 集成配置

**验收标准**：
- 通过 task_center CLI 手动触发日线刷新成功
- 定时调度正常工作
- 刷新完成后缓存自动失效
- 失败自动重试（由 task_center 管理）

**风险**：中（task_center 自身稳定性、Tushare 配额）
**是否需要 Verify/Review**：是

---

### Phase 6：Stock Framework 集成（预计 2-3 天）

**范围**：
- StockQuantProfile Builder 使用 UnifiedDataClient 获取数据
- data_gaps 处理链路端到端验证
- unified_data 性能优化（批量查询、并发）

**产物**：
- stock framework 与 unified_data 的集成代码
- 集成测试用例

**验收标准**：
- ProfileBuilder 从 unified_data 成功获取数据
- 数据域缺失时 data_gaps 正确回传
- 批量查询性能可接受（< 30s for 10 stocks）

**风险**：中（接口适配、性能）
**是否需要 Verify/Review**：是

---

### Phase 7：TA-CN 渐进迁移规划（预计 1 天文档）

**范围**：
- 不实现代码，产出迁移规划文档
- 迁移风险评估
- 回滚方案

**注**：Pascal 已确认（2026-07-14）DSA 不是 unified_data 的运行时数据源，不实现 DSA adapter；本 Phase 7 仅覆盖 TA-CN 单一方向的迁移规划，DSA 不在迁移范围内。DSA 的分析/参考使用维持现有边界，不被本 Phase 约束。

**产物**：
- `docs/design/03_data/DESIGN-03-007-migration-plan.md`

**验收标准**：
- 迁移步骤清晰，每步可回滚
- 风险矩阵完整
- 时间线合理

**风险**：低（仅为文档）
**是否需要 Verify/Review**：否

---

### 实现阶段总览表

| Phase | 名称 | 预计时间 | 风险 | 是否 Verify | 是否 Review |
|---|---|---|---|---|---|
| 0 | 骨架 + 核心抽象 | 1-2 天 | 低 | 否 | 否 |
| 1A | TA-CN read-only adapter（core A-share + index/sector） | 2-3 天 | 低-中 | 是 | 是 |
| 1B | External Provider + Cache + Freshness | 1-2 天 | 中 | 是 | 是 |
| 1C | 端到端验收 + 测试补齐 | 1-2 天 | 低 | 是 | 是 |
| 2 | Provider Registry + Quality + Audit | 2-3 天 | 中 | 是 | 是 |
| 3 | 重要持久化扩展 | 3-5 天 | 中-高 | 是 | 是 |
| 4 | 龙虎榜 + 筹码 + 热门 | 2-3 天 | 中 | 否 | 否 |
| 5 | task_center 集成 | 2-3 天 | 中 | 是 | 是 |
| 6 | Stock Framework 集成 | 2-3 天 | 中 | 是 | 是 |
| 7 | 迁移规划文档 | 1 天 | 低 | 否 | 否 |

Phase 0-7 共 8 个编号阶段（Phase 0 为骨架，Phase 1-7 为业务能力阶段；Phase 1 细分为 1A/1B/1C 三个子阶段）。

**总计预计**：17-28 个工作日

---

## 13. 文件清单（后续实现预计新增/修改）

### 新增文件

```
skills/data/unified_data/
├── __init__.py
├── SKILL.md
├── client.py
├── config.py
├── exceptions.py
├── models/
│   ├── __init__.py
│   ├── security_id.py
│   ├── data_result.py
│   ├── data_request.py
│   ├── capability.py
│   ├── provider_attempt.py
│   ├── quality.py
│   └── domain/
│       ├── __init__.py
│       ├── market_data.py
│       ├── financial.py
│       ├── valuation.py
│       ├── flow.py
│       ├── sector.py
│       ├── sentiment.py
│       ├── dragon_tiger.py
│       ├── chip.py
│       ├── news.py
│       ├── calendar.py
│       └── metadata.py
├── router/
│   ├── __init__.py
│   ├── data_router.py
│   └── provider_registry.py
├── providers/
│   ├── __init__.py
│   ├── base.py
│   ├── tushare_provider.py
│   ├── akshare_provider.py
│   ├── yfinance_provider.py
│   └── finnhub_provider.py
├── services/
│   ├── __init__.py
│   ├── market_data_service.py
│   ├── fundamental_service.py
│   ├── valuation_service.py
│   ├── flow_service.py
│   ├── sentiment_service.py
│   ├── sector_service.py
│   ├── event_service.py
│   ├── calendar_service.py
│   └── metadata_service.py
├── cache/
│   ├── __init__.py
│   ├── cache_manager.py
│   └── freshness_policy.py
├── quality/
│   ├── __init__.py
│   ├── quality_scorer.py
│   └── audit_logger.py
├── adapters/
│   ├── __init__.py
│   ├── ta_cn_mongo_adapter.py
│   └── local_mongo_adapter.py          # Phase 1B: 物化数据查询
├── tasks/
│   ├── __init__.py
│   ├── refresh_daily_kline.py
│   ├── refresh_realtime_quotes.py
│   ├── refresh_financial.py
│   ├── refresh_sector_snapshot.py
│   ├── refresh_sentiment_snapshot.py
│   ├── refresh_capital_flow.py
│   ├── refresh_dragon_tiger.py
│   └── refresh_chip_distribution.py
└── collections/
    ├── __init__.py
    ├── sector_snapshot_schema.py
    ├── sentiment_snapshot_schema.py
    ├── capital_flow_schema.py
    ├── dragon_tiger_schema.py
    ├── chip_distribution_schema.py
    ├── hot_stock_snapshot_schema.py
    ├── query_audit_schema.py
    └── quality_summary_schema.py

tests/unified_data/
├── __init__.py
├── conftest.py
├── test_security_id.py
├── test_data_result.py
├── test_data_request.py
├── test_provider_registry.py
├── test_data_router.py
├── test_cache_manager.py
├── test_freshness_policy.py
├── test_quality_scorer.py
├── test_audit_logger.py
├── test_tushare_provider.py
├── test_akshare_provider.py
├── test_ta_cn_adapter.py
├── test_market_data_service.py
├── test_fundamental_service.py
├── test_client.py
├── fixtures/
│   ├── ta_cn_mock_data.py
│   └── provider_mock_data.py
└── integration/
    ├── test_full_flow.py
    ├── test_fallback.py
    └── test_cache_freshness.py

scripts/
└── unified_data_scheduler.py

config/
└── unified_data.yaml

docs/design/03_data/
└── DESIGN-03-007-migration-plan.md    # Phase 7 产出
```

### 不修改的文件（严禁修改清单）

```
skills/apps/TradingAgents-CN/**        # TA-CN 子项目
skills/research/daily_stock_analysis/**  # DSA 子系统
skills/data/data-pipeline/**            # ETL 管道
skills/data/data_interface/**           # Portfolio IReader/IWriter
skills/research/argus/**                # Argus 信号系统
skills/research/stock/**                # Stock framework（仅通过接口消费）
skills/infra/task_center/**             # Task Center（仅通过接口调度）
```

### 可更新的文件（只读引用、索引、文档）

```
docs/README.md                         # 如需添加设计文档引用
docs/design/03_data/README.md          # 如需添加索引
```

---

## 14. 测试策略

### 14.1 单元测试

| 测试类 | 覆盖内容 | 预计用例数 | 是否需网络 |
|---|---|---|---|
| `test_security_id` | 构造、转换、相等性、边界 | 12 | 否 |
| `test_data_result` | 构造、序列化、freshness 标签 | 8 | 否 |
| `test_data_request` | 构造、参数合并 | 4 | 否 |
| `test_provider_registry` | 注册、查询、重复、capability | 8 | 否 |
| `test_data_router` | 路由、fallback、强制指定 provider | 6 | 否（mock provider） |
| `test_cache_manager` | 读写、TTL、强制刷新、key 生成 | 8 | 否（mock MongoDB） |
| `test_freshness_policy` | TTL 查询、标签计算、自定义 | 6 | 否 |
| `test_quality_scorer` | 完整度、缺失率、异常值检测 | 6 | 否 |
| `test_audit_logger` | 写入、失败降级 | 4 | 否（mock MongoDB） |
| `test_ta_cn_adapter` | 字段映射、空数据处理 | 6 | 否（fixture） |
| `test_domain_models` | 各 canonical object 构造与验证 | 15 | 否 |

### 14.2 合约测试（Adapter Contract Tests）

| 测试 | 内容 | 阶段 |
|---|---|---|
| `test_adapter_contract` | 所有 adapter 实现相同的 `read(domain, operation, security_id) → DataResult` 契约 | Phase 1 |
| `test_provider_contract` | 所有 provider 实现 `fetch(...) → DataFrame` + `is_available()` | Phase 1 |

### 14.3 Fixture 测试（无网络）

| 测试 | 内容 | 阶段 |
|---|---|---|
| `test_full_flow_with_fixtures` | 端到端：SecurityId → DataRequest → Router → Adapter → DataResult | Phase 1 |
| `test_fallback_with_fixtures` | Tushare mock fail → AKShare mock success → result with source_trace | Phase 2 |
| `test_cache_freshness_with_fixtures` | Cache hit → freshness="cached", Cache expired → refetch | Phase 2 |

### 14.4 网络 Smoke 测试（可选）

| 测试 | 内容 | 标记 |
|---|---|---|
| `test_tushare_real` | 真实 Tushare API 调用（限 1 次） | `@pytest.mark.network` |
| `test_akshare_real` | 真实 AKShare API 调用（限 1 次） | `@pytest.mark.network` |
| `test_full_flow_real` | 真实数据获取端到端 | `@pytest.mark.network` |

### 14.5 Schema 兼容性测试

| 测试 | 内容 | 阶段 |
|---|---|---|
| `test_ta_cn_schema_compat` | 验证新 adapter 读取 TA-CN 集合不抛异常，不丢失字段 | Phase 1 |
| `test_no_migration_regression` | 确认 TA-CN 集合未被修改（md5 hash 对比；DSA 集合不计，因不属于 unified_data 范围） | Phase 1 |

### 14.6 测试运行命令

```bash
# 快速验证（无网络）
python -m pytest tests/unified_data/ -m "not network" -v

# 全量测试（含真实 API）
python -m pytest tests/unified_data/ -v

# 合约测试
python -m pytest tests/unified_data/ -k "contract" -v

# Schema 兼容性测试
python -m pytest tests/unified_data/ -k "schema" -v
```

---

## 15. 风险与回滚

| 风险 | 概率 | 影响 | 应对方案 | 降级/回滚 |
|---|---|---|---|---|
| **schema drift**：TA-CN 集合字段在 unified_data 开发期间被修改 | 中 | 高 | adapter 读取时使用 `.get(field, default)` 宽松策略，不做强 schema 校验 | 更新 adapter 映射表，不修改 TA-CN |
| **provider 不可用**：Tushare 配额耗尽或 AKShare 接口变动 | 高 | 中 | 多源 fallback，兜底到 TA-CN adapter；audit 记录 | 切换 provider 优先级配置 |
| **rate limit**：大批量回填触发 Tushare 限流 | 中 | 中 | 内置 rate limiter；批量回填指定单一 provider | 分批执行 + 延长间隔 |
| **数据源冲突**：Tushare 和 AKShare 同一字段数据不一致 | 低 | 中 | QualityScorer 交叉校验 + DataResult.warnings 标注 | 默认信任优先 provider |
| **duplicate writes**：多个 provider 写入同一缓存 key | 低 | 低 | upsert + cached_at 版本号 | 后写覆盖先写 |
| **migration risk**：adapter 读取路径导致 TA-CN/DSA 响应变慢 | 低 | 中 | adapter 只做读取，不做写入；异步 warmup | 关闭 adapter 路径，回退到直接 provider |
| **MongoDB 连接失败** | 中 | 高 | 所有 MongoDB 操作 catch-and-log，不影响查询 | bypass cache，直接走 provider |
| **新集合创建授权** | 低 | 高 | Pascal 确认后再执行集合创建 | — |

**回滚策略**：
1. unified_data 模块与现有 TA-CN/DSA/data-pipeline 零耦合，可直接删除 `skills/data/unified_data/` 目录即完全回滚。
2. 新增的 `03_data_ud_*` 集合也可安全删除，不影响生产数据。
3. 每个 Phase 独立部署，前一个 Phase 有问题不影响后续 Phase 的独立性回滚。

---

## 16. Design Overrides / Pascal 确认更新

以下决策在 RFC/SPEC 中未明确或需要调整，本 Design 做出裁定：

| 序号 | 原 RFC/SPEC 描述 | Design 裁定 | 理由 |
|---|---|---|---|
| DO-1 | SPEC 提到缓存集合名 `03_data_ud_cache_*` | 确认：`03_data_ud_cache_{operation}`，如 `03_data_ud_cache_kline_daily` | 更精确，避免同域不同操作的数据混合 |
| DO-2 | RFC 提到 MongoDB 缓存优先 | 确认：MongoDB 缓存是主缓存，但缓存失败不阻断查询 | 遵守 catch-and-log 原则 |
| DO-3 | SPEC 未明确 TA-CN adapter 的写入权限 | 裁定：adapter 只读，不写 TA-CN 集合 | 保持数据写路径单一 |
| DO-4 | RFC 提到后续 Design 可拆分为 A/B/C/D 四个子设计 | 裁定：合并为一个 Design，但实现拆 7 Phase | Pascal 要求先做完整设计 |
| DO-5 | RFC 未定义 `03_data_ud_cache_*` 集合的 TTL 索引 | 裁定：新增 | 与 FreshnessPolicy 对齐 |
| DO-6 | SPEC 未明确 DSA 强项数据是否持久化 | 裁定：持久化到新 `03_data_ud_*` 集合 | Pascal 确认 DSA 强项数据需纳入 |
| DO-7 | RFC 使用 `{market}:{symbol}` 格式 | 确认沿用 | 与 SPEC SecurityId `__str__` 一致 |
| DO-8 | SPEC 提到 `ta_cn_adapter` 但未定名 | 确认：`TA-CNAdapterProvider` + `TA_CNMongoAdapter` | adapter 层分 provider 和 storage adapter |
| DO-9 | SPEC 未明确 `provider_chain` 在 fallback 时的格式 | 确认：`["tushare(fail)", "akshare(ok)"]` | 简洁可读 |
| DO-10 | SPEC `CacheManager.put()` 返回 None | 确认：与 SPEC 一致，write-through 模式 | 不期待返回值 |
| DO-11 | 原 §7.4 `fallback_chains` 使用外部优先（Tushare → AKShare → ta_cn_adapter） | **修订（2026-07-14 Pascal 确认）**：改为 internal-first（TA-CN 既有 → UD 物化 → Cache → 外部 Provider） | 权威读取路径必须先查内部已有数据，外部刷新失败不阻断内部读取 |
| DO-12 | 原 §5.1 / §8.1 使用「物理隔离」措辞 | **修订（2026-07-14 Pascal 确认）**：改为「命名空间隔离」 | Unified Data 与 TA-CN 共用同一物理库 `tradingagents`，通过集合前缀逻辑隔离 |
| DO-13 | 原 §5.1 / §7.2 / §13 保留 DSA SQLite adapter / `StockDaily` 作为 Phase 1B 兜底 | **修订（2026-07-14 Pascal 确认）**：删除全部 DSA SQLite / StockDaily runtime adapter/fallback 表述 | DSA 不是运行时 fallback / internal source，仅在分析/参考中出现 |
| DO-14 | 原 §8.1 读路径：CacheManager.get() → Provider chain | **修订（2026-07-14 Pascal 确认）**：新增 LocalMongoAdapter 层，读路径变为 TA-CN 既有 → UD 物化 → Cache → 外部 Provider | internal-first 架构需要物化数据查询层 |
| DO-15 | 物化数据与 Query Cache 命名空间未明确区分 | **修订（2026-07-14 Pascal 确认）**：物化数据 = `03_data_ud_*`（可追溯），Query Cache = `03_data_ud_cache_*`（可丢弃短 TTL） | 三层语义分离：TA-CN 既有资产 / UD 可追溯物化 / 可丢弃 cache |

---

## 17. 交接给实现者

### 必须遵守
- **绝对禁止修改 TA-CN/DSA/Argus/portfolio/data-pipeline 代码。**
- 所有 adapter 只读，不写 TA-CN 或 DSA 集合。
- Canonical domain objects 使用 dataclass/Pydantic，不强绑定数据库 schema。
- 缓存字段加 `03_data_ud_cache_` 前缀隔离。
- 审计写入失败不阻断查询（catch-and-log）。
- 遵守 SPEC-03-007 定义的异常体系和错误码。
- 所有新增 MongoDB 集合创建前需 Pascal 确认。

### 可自行判断
- 函数内部实现细节（非公开 API）。
- 日志级别和文案。
- pytest fixture 设计。
- provider 限流具体参数（可按 Tushare 积分等级调整）。
- 缓存 key 生成的具体 hash 算法（只要确定性即可）。

### 遇到以下情况退回 Principal
- RFC/SPEC 定义与 Design 冲突且无法判断优先级的。
- 需要创建非 `ud_` 前缀的集合。
- 需要修改现有 TA-CN/DSA 代码才能实现 adapter 功能的。
- 发现 TA-CN 集合字段与文档严重不一致的。
- 性能瓶颈需要改变架构分层或接口签名的。

---

## 18. 参考资料

- `docs/rfc/03_data/RFC-03-007-unified-data-layer.md` — 需求与架构
- `docs/spec/03_data/SPEC-03-007-unified-data-layer.md` — 接口契约
- `docs/rfc/10_infra/RFC-10-009-task-center.md` — 任务中心需求
- `docs/spec/10_infra/SPEC-10-009-task-center.md` — 任务中心契约
- `docs/rfc/08_research/stock/RFC-08-001-stock-quant-analysis-framework.md` — Stock 框架需求
- `docs/spec/08_research/stock/SPEC-08-001-stock-quant-analysis-framework.md` — Stock 框架契约
- `skills/apps/TradingAgents-CN/docs/design/stock_data_model_design.md` — TA-CN 数据模型设计
- `skills/apps/TradingAgents-CN/app/models/stock_models.py` — TA-CN Pydantic 模型
- `skills/research/daily_stock_analysis/data_provider/base.py` — DSA BaseFetcher（仅分析/参考，不属于 unified_data 读取路径）
- `skills/infra/ai-coding-pipeline/SKILL.md` — 流水线规范

---

## 19. 文档同步修订说明（V3.3，2026-07-14 Pascal 架构基线同步）

本次为文档同步修订（无代码改动、无生产副作用）。仅统一 RFC-03-007 V0.3 / SPEC-03-007 V1.2 / DESIGN-03-007 V3.3 三层文档的措辞与立边界，确保 Pascal 确认的架构基线在三处一致可查。本节为锚点，所有 §X 提及的下列措辞必须以本节为准。

### 19.1 必须保持的不变量（与 §16 DO-11 ~ DO-15 一致）

1. **共享物理数据库**：Unified Data 与 TA-CN 共用 `tradingagents`；不依赖物理库隔离；通过集合命名空间前缀实现 ownership。
2. **Internal-First 读取路径**：TA-CN 既有 → UD 物化 → Query Cache → 外部 Provider；外部刷新失败不阻断内部已有数据读取。
3. **DSA 边界**：DSA 仅在分析/参考中出现；不实现任何 DSA adapter；DSA 不在 `external_fallback_chains` 中。
4. **Collection Ownership 不可回写**：Unified Data 绝不回写、覆盖或加字段污染 TA-CN 既有无前缀集合。
5. **Task Center 先行**：最小 Task/Job/Execution、幂等、重试、执行审计能力在 UD 物化写入前可用；不创建真实 Job、不启用 cron/systemd、长期调度。
6. **三层语义分离**：TA-CN 既有业务资产 / UD 可追溯物化数据集 / 可丢弃短 TTL Query Cache 三者语义与命名空间清晰区分。

### 19.2 V3.3 重点修订项（与历史修订对比）

| 序号 | 历史措辞（V3.2 及以前） | V3.3 修订 | 依据 |
|---|---|---|---|
| 1 | §1A.5 「DSA SQLite adapter — Phase 1B（作为兜底数据源）」 | 「**不实现**（DSA 不是运行时数据源；本节作为对历史术语的反向澄清）」 | DO-13；§16 Override 表 |
| 2 | §1A.6 「`dsa_sqlite_adapter.py` — Phase 1B」 | 「**不创建**（DSA 不是运行时数据源；不实现任何 DSA adapter）」 | DO-13；§16 Override 表 |
| 3 | §4 D03/D04 「adapter 读 TA-CN/DSA」（DSA 双读） | 「adapter 读 TA-CN；DSA 不作为 unified_data 读取源」 | V3.1 + DO-13 联合 |
| 4 | §13 测试清单 `test_dsa_adapter.py` / `dsa_mock_data.py` | 删除（DSA adapter 不实现） | DO-13 |
| 5 | §14.1 单元测试 `test_dsa_adapter` 行 | 删除 | DO-13 |
| 6 | §14.5 Schema 兼容性 `test_dsa_schema_compat` | 删除（验证 DSA adapter 读取 SQLite 不抛异常 — 适配器不存在） | DO-13 |
| 7 | Phase 7「TA-CN / DSA 渐进迁移规划」 | 改为「TA-CN 渐进迁移规划」+ 注明 DSA 不在迁移范围 | DO-13 |
| 8 | §13/§15 风险表中 "TA-CN/DSA 集合未被修改" | 改为 "TA-CN 集合未被修改；DSA 集合不计，因不属于 unified_data 范围" | DO-13 |
| 9 | §15 回滚策略 "unified_data 模块与现有 TA-CN/DSA 零耦合" | 措辞保留（描述模块解耦状态，与新架构兼容） | 措辞无矛盾 |

### 19.3 V3.3 保留措辞（无需修订）

| 序 | 段落 / 章节 | 当前措辞 | 是否需要改 |
|---|---|---|---|
| 1 | §7.4 与 §8.1 整个读取路径描述 | internal-first + LocalMongoAdapter | 已正确，无需改 |
| 2 | §16 DO-11 ~ DO-15 Override 表 | 全部 Pascal 确认基线 | 已正确，无需改 |
| 3 | §5.1 §5.4 关键约束 | 「共用同一物理数据库 `tradingagents`，不使用物理库隔离」 | 已正确，无需改 |
| 4 | §17 必须遵守 | 「绝对禁止修改 TA-CN/DSA/Argus/portfolio/data-pipeline 代码」 | 已正确，无需改 |

### 19.4 V3.3 已知遗留（不在本修订范围）

下列条目为供 Pascal 决策的开放问题，**不在本次修订范围**：

- §1.1 「5. DSA 强项数据允许持久化」：DSA 强项数据（板块/情绪/资金流/龙虎榜/筹码）由 unified_data 写入 `03_data_ud_*` 持久化集合，**不是从 DSA 读取**；措辞中"参考"含义保留，但内含假设需要 Pascal 后续确认是否保留 DSA 设计动作。
- §2.3 「DSA 现有模型（SQLite 侧）」仅为现状描述，作为 unified_data 的对照参考，不构成运行时依赖；与新架构基线兼容。

### 19.5 不在本次修订的副作用

本修订不触发：

- 任何代码改动（`skills/data/unified_data/` 内 `.py` 文件保持当前状态）。
- MongoDB 集合 / 索引 / schema validator 改动。
- 真实 Job 创建、cron / systemd / 长期调度启用。
- TA-CN / DSA / data-pipeline / data_interface / task_center / stock framework / Argus / portfolio 任一子项目代码改动。
- 任何外部 API 调用或真实写入。

## 20. 文档一致性修复说明（V3.4，2026-07-14，Router 全失败对外契约同步）

本次为纯文档一致性修复（无代码改动、无生产副作用），对齐 Phase 1B-A 已确认的架构决策：自 Phase 1B-A 起，`DataRouter` 在所有 Provider 失败时对调用方返回 `DataResult.error(provider="error", source_trace=[...])`，不再以 `AllProvidersFailedError` 作为 Router 主出口，不设兼容开关。本 DESIGN 受影响条目：Phase 1C E2E 验收（§Phase 1C 范围，原 L2145）、Phase 2 fallback 验收标准（§Phase 2 验收标准，原 L2179）。`AllProvidersFailedError` 类保留作内部/历史兼容类型，Phase 0 旧基线以该异常为出口的行为在文档中明确标识为历史描述。Phase 1B-A 的 internal-first 路径与外部 fallback 全失败语义（§7.4 / §8.1，返回 `DataResult.error(...)`，不阻断已有内部数据读取）保持不变，本次仅消除 1C/Phase 2 验收描述与该已确认契约的直接冲突。
