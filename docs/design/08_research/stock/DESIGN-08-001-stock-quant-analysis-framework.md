# DESIGN-08-001: Stock Quant Analysis Framework — 完整详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-12 |
| 最后更新 | 2026-07-12 |
| 来源 RFC | RFC-08-001 |
| 来源 SPEC | SPEC-08-001 |
| 关联 RFC | RFC-03-007（Unified Data Layer）、RFC-10-009（Task Center） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer）、SPEC-10-009（Task Center） |
| 关联 Design | DESIGN-03-007（Unified Data Layer）、DESIGN-10-009（Task Center） |
| 目标模块 | stock framework（`skills/research/stock/`） |

---

## 1. 设计目标与非目标

### 1.1 设计目标

1. **完整设计**：覆盖 stock framework 的总体架构、对象模型、MongoDB 持久化、画像层、策略模型插件层、交叉验证、风险审计、路径推演、组合适配、报告渲染、task_center 接口、文件清单、分阶段实现路线。
2. **分阶段实现**：设计一次到位，实现拆为 Phase 0-7，每 Phase 有独立范围、产物、验收标准和风险。
3. **事实与解释分离**：通用量化画像层只承载客观可校验的量化事实（指标值、分位数、排名）；策略模型插件层只承载主观可调参可回测的解释与评分。两层通过 ModelScore 统一协议耦合。
4. **数据只读消费**：所有数据输入通过 `unified_data.UnifiedDataClient` 获取；不直连 Tushare/AKShare 等底层 provider。
5. **持久化使用 MongoDB**：stock framework 所有新增集合使用 `08_research_stock_*` 前缀，存放在 `tradingagents` 库下。禁止使用 SQLite 作为 stock framework 持久化。
6. **与 task_center 清晰分工**：stock framework 定义业务逻辑（画像构建、模型评分、报告生成）；task_center 负责任务注册、调度、重试、进度追踪。
7. **边界清晰**：不修改 unified_data / task_center / TA-CN / DSA / Argus / portfolio / reports 现有代码和数据。

### 1.2 非目标（本 Design 不做的事）

- 不实现代码（不创建 `skills/research/stock/` 下的 `.py` 文件）。
- 不修改 TA-CN / DSA / unified_data / task_center / Argus / portfolio 现有代码或配置。
- 不创建数据库集合或执行迁移。
- 不设计 cron / systemd / gateway / webhook / 外部推送配置。
- 不写入生产交易集合（`portfolio_position` / `portfolio_trade` / `signal` / `stock_pool`）。
- 不做实盘交易决策。

---

## 2. Design Overrides（相对 RFC/SPEC 的调整）

以下是本 Design 阶段根据 Pascal 最新要求与上游 Design 进展对 RFC/SPEC 的调整，所有修改在此显式列出并说明理由：

| # | 原 RFC/SPEC 表述 | 调整 | 理由 |
|---|---|---|---|
| O1 | SPEC §4 模型文件 `models/{model_id}.py` | 调整为 `models/{model_id}_model.py` | 避免 `models/` 包与模块名冲突（如 `models/value.py` 与 `models/value_v1.py` 可能被误解为值对象） |
| O2 | RFC §5.2 持久化策略未显式限制 SQLite | **禁止 SQLite 作为 stock framework 持久化**，MongoDB 为唯一后端 | Pascal 明确要求；与 unified_data / task_center 的 MongoDB-first 策略一致 |
| O3 | RFC §4.3 列表含 TaskCenterAdapter | 拆分为 `task_center/adapter.py`（注册层）+ 框架内部 `_task_callables.py`（业务 callable 实现） | 清晰分离"注册配置"与"业务执行体" |
| O4 | SPEC §11 MVP 含 Markdown 报告 | MVP 阶段增加 **JSON block** 报告输出（MINIMAL 格式，无 HTML） | JSON 结构是下游系统（DSA / reports 模块）的消费标准，增加成本极低 |
| O5 | SPEC §11 ProfileBuilder 四个维度组 | 明确 MVP Phase 1 至少覆盖**五个**维度组（基本面 / 估值 / 质量 / 成长 / 技术），Phase 2 补齐资金流+情绪 | 五个维度覆盖成长+价值两模型必需的全部评分维度；三个维度不够决策 |
| O6 | RFC §5.2 持久化集合命名 `stock_quant_profile` / `stock_model_score` | 统一调整为 `08_research_stock_*` 前缀（与 `03_data_ud_*`、`10_infra_tc_*` 命名体系一致） | Pascal 要求避免集合冲突；DESIGN-10-009 已确认 `10_infra_tc_*` 前缀，保持一致性 |
| O7 | RFC §4.3 PortfolioFit 目标 | 明确 PortfolioFit **只读** portfolio 模块，输出 `PortfolioFitAdvice` 仅为分析辅助，不修改任何组合数据 | 与 DESIGN-03-007 §11.4 的只读 adapter 一致 |
| O8 | SPEC §12.2 模型单元测试"给定画像 fixture … 字段齐全" | 补充要求：每个模型至少包含 3 个确定性测试用例（buy/hold/avoid 各一），且评分结果必须对人可解释 | 提升测试有效性，避免 0.5 附近全 neutral 的空壳模型 |

---

## 3. 总体架构

### 3.1 分层架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Consumers 消费层                                  │
│  DSA │ Argus │ portfolio │ reports │ strategies │ Hermes cron             │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ 同步调用入口 + ReportBundle JSON
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│               Stock Quant Analysis Framework  (skills/research/stock/)     │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    Report Layer 报告层                                │ │
│  │  ReportRenderer: Markdown / HTML / JSON block                        │ │
│  └────────────▲────────────────────────────────────────────────────────┘ │
│               │                                                           │
│  ┌────────────┴────────────────────────────────────────────────────────┐ │
│  │                   Synthesis Layer 综合层                              │ │
│  │                                                                       │ │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────┐  │ │
│  │  │ CrossValidator  │  │ RiskAuditor      │  │ PathProjector      │  │ │
│  │  │ 多模型交叉验证   │  │ 风险/死亡审计    │  │ 路径推演           │  │ │
│  │  └────────┬────────┘  └────────┬─────────┘  └────────┬───────────┘  │ │
│  │           │                    │                      │               │ │
│  │  ┌────────┴────────────────────┴──────────────────────┴───────────┐  │ │
│  │  │                    PortfolioFit 组合适配                        │  │ │
│  │  │   只读 portfolio → 行业/风格/相关性/集中度/边际风险贡献         │  │ │
│  │  └────────────────────────────────────────────────────────────────┘  │ │
│  └────▲───────────────▲─────────────────────────────▲──────────────────┘ │
│       │               │                             │                     │
│  ┌────┴───────────────┴─────────────────────────────┴──────────────────┐ │
│  │                     Model Plugin Layer 策略模型层                    │ │
│  │                                                                      │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │ │
│  │  │growth_v1 │ │value_v1  │ │quality_v1│ │momentum  │ │dividend  │  │ │
│  │  │ 成长股   │ │ 价值股   │ │ 质量     │ │ _v1 动量 │ │_lowvol_v1│  │ │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │ │
│  │       │            │            │            │            │          │ │
│  │  ┌────┴────────────┴────────────┴────────────┴────────────┴─────┐  │ │
│  │  │         event_driven_v1 (Phase 3, MVP 不含)                   │  │ │
│  │  └───────────────────────────────────────────────────────────────┘  │ │
│  │                                                                      │ │
│  │  统一输入: StockQuantProfile + ModelParams → 统一输出: ModelScore    │ │
│  └────▲─────────────────────────────────────────────────────────────────┘ │
│       │                                                                    │
│  ┌────┴──────────────────────────────────────────────────────────────────┐ │
│  │                     Profile Layer 通用画像层                           │ │
│  │                                                                        │ │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────────┐ │ │
│  │  │ ProfileBuilder  │  │ StockUniverse    │  │ DimensionCalculator   │ │ │
│  │  │ 画像构建编排    │  │ 股票池管理       │  │ 维度指标计算          │ │ │
│  │  └────────┬────────┘  └────────┬─────────┘  └───────────┬───────────┘ │ │
│  │           │                    │                          │             │ │
│  │  ┌────────┴────────────────────┴──────────────────────────┴───────────┐│ │
│  │  │                  StockQuantProfile 画像实体                         ││ │
│  │  │  基本面 │ 成长 │ 估值 │ 质量 │ 技术 │ 资金流 │ 情绪 │ 催化剂      ││ │
│  │  │  风险 │ 组合适配 │ 数据质量 (共 11 个维度组)                       ││ │
│  │  └────────────────────────────────────────────────────────────────────┘│ │
│  └────▲──────────────────────────────────────────────────────────────────┘ │
│       │                                                                    │
│  ┌────┴──────────────────────────────────────────────────────────────────┐ │
│  │                    Data Interface 数据接入                              │ │
│  │  unified_data.UnifiedDataClient（dep → skills/data/unified_data）      │ │
│  │  行情/财务/估值/资金流/新闻/日历/元数据/质量                            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                Task Center Integration 任务中心集成                  │   │
│  │  task_center 注册 / 调度 / 重试 / 进度追踪 (skills/infra/task_center)│   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└───────────┬──────────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      MongoDB (tradingagents) 持久化层                      │
│  08_research_stock_universe                                               │
│  08_research_stock_profile                                                │
│  08_research_stock_model_score                                            │
│  08_research_stock_cross_validation                                       │
│  08_research_stock_risk_audit                                             │
│  08_research_stock_path_projection                                        │
│  08_research_stock_portfolio_fit                                          │
│  08_research_stock_report_snapshot                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 模块目录结构

```
skills/research/stock/
├── __init__.py
├── SKILL.md                              # 模块说明与使用指南
│
├── core/
│   ├── __init__.py
│   ├── entities.py                       # 9 类核心实体 dataclass 定义
│   ├── security_id.py                    # SecurityId 解析与标准化
│   └── exceptions.py                     # 15+ 种异常定义
│
├── profile/
│   ├── __init__.py
│   ├── builder.py                        # ProfileBuilder 编排
│   ├── dimension_calculator.py           # DimensionCalculator 基类
│   ├── dimensions/                       # 11 个维度计算器
│   │   ├── __init__.py
│   │   ├── fundamental.py                # 基本面维度
│   │   ├── growth.py                     # 成长维度
│   │   ├── valuation.py                  # 估值维度
│   │   ├── quality.py                    # 质量维度
│   │   ├── technical.py                  # 技术维度
│   │   ├── capital_flow.py               # 资金流维度（Phase 2）
│   │   ├── sentiment.py                  # 情绪维度（Phase 2）
│   │   ├── catalyst.py                   # 催化剂维度（Phase 3）
│   │   ├── risk_dimension.py             # 风险因子维度
│   │   ├── portfolio_context.py          # 组合上下文维度
│   │   └── data_quality.py               # 数据质量维度
│   └── helpers/
│       ├── __init__.py
│       ├── technical_indicators.py       # 技术指标计算（MA/RSI/MACD 等）
│       ├── financial_ratios.py           # 财务比率派生计算
│       └── percentile.py                 # 分位数、排名工具
│
├── universe/
│   ├── __init__.py
│   ├── registry.py                       # StockUniverse 注册与管理
│   └── scanner.py                        # 股票池扫描与初筛
│
├── models/
│   ├── __init__.py
│   ├── base.py                           # StrategyModel 抽象基类 + ModelParams
│   ├── growth_v1_model.py                # 成长股模型
│   ├── value_v1_model.py                 # 价值股模型
│   ├── quality_v1_model.py               # 质量模型
│   ├── momentum_v1_model.py              # 动量模型
│   ├── dividend_lowvol_v1_model.py       # 红利低波模型
│   ├── event_driven_v1_model.py          # 事件驱动模型（Phase 3）
│   ├── registry.py                       # ModelRegistry 注册/发现
│   └── configs/                          # 模型参数 YAML 配置
│       ├── growth_v1.yaml
│       ├── value_v1.yaml
│       ├── quality_v1.yaml
│       ├── momentum_v1.yaml
│       └── dividend_lowvol_v1.yaml
│
├── synthesis/
│   ├── __init__.py
│   ├── cross_validator.py                # CrossValidator 交叉验证
│   ├── risk_auditor.py                   # RiskAuditor 风险审计
│   ├── path_projector.py                 # PathProjector 路径推演
│   └── portfolio_fit.py                  # PortfolioFit 组合适配
│
├── report/
│   ├── __init__.py
│   ├── renderer.py                       # ReportRenderer (Markdown/JSON/HTML)
│   ├── templates/                        # Jinja2 报告模板
│   │   ├── markdown_report.j2
│   │   ├── html_report.j2
│   │   └── json_report_schema.json
│   └── assets/                           # 报告静态资源
│
├── task_center/
│   ├── __init__.py
│   ├── adapter.py                        # 注册 stock framework 任务到 task_center
│   └── _task_callables.py                # 业务 callable 实现（供 task_center 调用）
│
├── persistence/
│   ├── __init__.py
│   ├── mongo_client.py                   # MongoDB client 封装
│   ├── mongo_schema.py                   # 集合索引定义 + DDL
│   ├── profile_repo.py                   # StockQuantProfile CRUD
│   ├── model_score_repo.py               # ModelScore CRUD
│   ├── risk_audit_repo.py                # RiskAudit CRUD
│   ├── cross_validation_repo.py          # CrossValidationMatrix CRUD
│   ├── path_projection_repo.py           # PathProjection CRUD
│   ├── portfolio_fit_repo.py             # PortfolioFitAdvice CRUD
│   ├── report_repo.py                    # ReportSnapshot CRUD
│   └── universe_repo.py                  # StockUniverse CRUD
│
└── config.py                             # 模块配置加载

tests/research/stock/
├── __init__.py
├── conftest.py                           # pytest fixtures (mongomock + mock unified_data)
├── fixtures/
│   ├── profile_samples.py                # 画像样本 fixture
│   ├── model_score_samples.py            # ModelScore 样本 fixture
│   └── mock_unified_data.py              # Mock UnifiedDataClient
├── test_profile_builder.py
├── test_dimensions/
│   ├── test_fundamental.py
│   ├── test_growth.py
│   ├── test_valuation.py
│   ├── test_quality.py
│   └── test_technical.py
├── test_models/
│   ├── test_base.py
│   ├── test_growth_v1.py
│   ├── test_value_v1.py
│   ├── test_quality_v1.py
│   ├── test_momentum_v1.py
│   └── test_dividend_lowvol_v1.py
├── test_cross_validator.py
├── test_risk_auditor.py
├── test_path_projector.py
├── test_portfolio_fit.py
├── test_report_renderer.py
├── test_universe.py
├── test_task_adapter.py
├── test_persistence/
│   ├── test_profile_repo.py
│   ├── test_model_score_repo.py
│   └── test_mongo_schema.py
└── integration/
    ├── test_full_single_stock_analysis.py
    ├── test_profile_to_score_pipeline.py
    └── test_task_callable_integration.py
```

### 3.3 组件职责矩阵

| 组件 | 职责 | 输入 | 输出 |
|---|---|---|---|
| **ProfileBuilder** | 编排画像构建，依次调用各维度计算器 | SecurityId + as_of + UnifiedDataClient | StockQuantProfile |
| **DimensionCalculator** | 维度组指标的计算基类；子类覆盖 `calculate()` | UnifiedDataClient 领域查询结果 | ProfileDimension |
| **StockUniverse** | 管理股票池，支持按市场/行业/指数/自定义筛选 | universe 配置 | List[SecurityId] |
| **StrategyModel（ABC）** | 策略模型抽象基类，定义 `score(profile, params) → ModelScore` | StockQuantProfile + ModelParams | ModelScore |
| **ModelRegistry** | 模型注册/发现/启用/禁用 | model_id | StrategyModel 实例 |
| **CrossValidator** | 多模型交叉验证，产出共识/冲突/陷阱标注 | List[ModelScore] | CrossValidationMatrix |
| **RiskAuditor** | 风险与死亡审计 | StockQuantProfile + List[ModelScore] | RiskAudit |
| **PathProjector** | 周期阶段判定 + 路径推演 | StockQuantProfile + CrossValidationMatrix | PathProjection |
| **PortfolioFit** | 组合适配分析（只读 portfolio 数据） | PathProjection + 组合上下文 | PortfolioFitAdvice |
| **ReportRenderer** | 报告渲染输出 | 全部上游产物 + format | ReportBundle |
| **TaskCenterAdapter** | 注册 stock framework 任务定义到 task_center | task_center.register_task() | 无 |
| **Persistence Repos (×8)** | MongoDB 集合的 CRUD + 索引管理 | entity 对象 | 持久化读写 |

---

## 4. 边界设计

### 4.1 与 unified_data 的边界

| 维度 | stock framework | unified_data |
|---|---|---|
| 依赖方向 | stock → unified_data（单向） | unified_data 不依赖 stock |
| 接口形式 | `from unified_data.client import UnifiedDataClient` | 见 DESIGN-03-007 §11.4 |
| 禁止 | stock 不直接 import Tushare / AKShare / TaoBao / Finnhub 等 provider | — |
| 数据缺失 | 对应维度 `null` + `data_gaps` 记录，不编造 | 返回 `freshness="empty"` + warnings |
| 缓存/审计 | stock 不管理 unified_data 缓存 | unified_data 自行管理 `03_data_ud_cache_*` 和 `03_data_ud_query_audit` |

**StockQuantProfile 维度与 unified_data 接口的精确映射**：

| Profile 维度组 | unified_data 调用 | Phase |
|---|---|---|
| 基本面 | `client.get_stock_info(sid)` + `client.get_financial_metrics(sid)` | P1 |
| 成长 | `client.get_income_statement(sid)` + 框架内 YoY/多期计算 | P1 |
| 估值 | `client.get_valuation_snapshot(sid)` + `client.get_daily_basic(sid)` | P1 |
| 质量 | `client.get_financial_metrics(sid)` + `client.get_balance_sheet(sid)` + `client.get_cash_flow(sid)` | P1 |
| 技术 | `client.get_kline_daily(sid, limit=250)` + 框架内 MA/MACD/RSI/布林/量能 | P1 |
| 资金流 | `client.get_capital_flow(sid, limit=60)` | P2 |
| 情绪 | `client.get_market_sentiment()` + `client.get_news(sid, limit=20)` | P2 |
| 催化剂 | `client.get_news(sid)` + `client.get_dragon_tiger(sid)` | P3 |
| 风险 | kline_daily 波动率 + 财务排雷指标（框架内计算） | P1/P2 |
| 组合适配 | 只读 portfolio 模块（通过 portfolio adapter） | P4 |
| 数据质量 | `client.get_quality_summary(sid)` + DataResult.warnings | P1 |

### 4.2 与 task_center 的边界

| 维度 | stock framework | task_center |
|---|---|---|
| 依赖方向 | stock → task_center（仅注册任务） | task_center 不依赖 stock（只理解 callable） |
| 注册点 | `stock.task_center.adapter.register_stock_tasks()` | `task_center.registry.TaskRegistry.register_task()` |
| Callable 路径 | `stock.task_center._task_callables:batch_refresh_profiles` 等 | task_center 通过 `callable_path` 动态加载 |
| 调度 | stock 不管理调度 | 见 DESIGN-10-009 §12 六个 stock 任务 |
| 进度上报 | callable 内部通过 task_center ProgressTracker API | task_center 管理 ProgressSnapshot |

**六类注册任务**（与 DESIGN-10-009 §12.1 对齐）：

| 任务 ID | Callable | MVP |
|---|---|---|
| `stock.refresh_quant_profile` | `_task_callables:batch_refresh_profiles` | ✅ P1 |
| `stock.score_strategy_models` | `_task_callables:batch_score_models` | ✅ P1 |
| `stock.generate_stock_report` | `_task_callables:generate_report` | — P3 |
| `stock.batch_scan_universe` | `_task_callables:batch_scan_universe` | — P3 |
| `stock.backfill_model_scores` | `_task_callables:backfill_scores` | — P2 |
| `stock.portfolio_fit_refresh` | `_task_callables:refresh_portfolio_fit` | — P4 |

### 4.3 与 Argus 的边界

- **各管各的**：Argus 管 Smart Money 信号→股票池生命周期（zone 状态机 + bayesian_scoring）；stock framework 管个股通用量化画像 + 多模型评分。
- **只读消费**：画像层"资金流"维度**可**消费 Argus 产出的 Smart Money 持仓变化（只读参考 `portfolio_position` 集合，仅限 `SM001/SM002/SM003/SM004/SM012`），但不介入 Argus 的 zone 状态机、不写入 signal/stock_pool 集合。

### 4.4 与 DSA（daily_stock_analysis）的边界

- **定位不同**：DSA 偏 LLM 单股深度报告（长文分析、买卖点建议）；stock framework 偏结构化量化画像 + 多模型评分。
- **上下游可协作**：
  - DSA → stock：DSA LLM 报告的定性解读（催化剂判断、管理层信号）可作为画像层催化剂维度的输入（Phase 4 adapter）。
  - stock → DSA：ReportBundle 的 `json_block` 可作为 DSA 生成深度报告的输入数据。
- **不修改 DSA 代码**。

### 4.5 与 TA-CN 的边界

- **架构参考，代码不复用**。TA-CN 的多智能体辩论模式仅在设计思路层面参考（CrossValidator 的共识/冲突逻辑），不导入 TA-CN agent 代码。
- TA-CN 集合下的数据全部通过 unified_data adapter 只读消费。

---

## 5. 核心实体模型

以下 9 个实体构成 stock framework 的完整数据模型。所有实体使用 `@dataclass` 定义，MongoDB 持久化通过 persistence repo 层完成序列化/反序列化。

### 5.1 StockUniverse — 股票池

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| universe_id | str | ✅ | 唯一标识，如 `cn_a_share_all`、`hs300`、`zz500` | ✅ |
| name | str | ✅ | 人类可读名称 | ✅ |
| market | str | ✅ | 市场代码（CN / HK / US） | ✅ |
| security_ids | list[str] | ✅ | 成分股 security_id 列表 | ✅ |
| filter_rule | dict\|None | — | 动态筛选规则（如 {"exclude_st": true}） | ✅ |
| parent_universe_id | str\|None | — | 父股票池（如 `cn_a_share_all` → `hs300`） | — |
| refreshed_at | str\|None | — | ISO 8601 最后刷新时间 | ✅ |
| created_at | str | ✅ | ISO 8601 | ✅ |
| updated_at | str | ✅ | ISO 8601 | ✅ |

```python
@dataclass
class StockUniverse:
    universe_id: str
    name: str
    market: str
    security_ids: list[str] = field(default_factory=list)
    filter_rule: dict | None = None
    parent_universe_id: str | None = None
    refreshed_at: str | None = None
    created_at: str = ""
    updated_at: str = ""
```

### 5.2 StockQuantProfile — 通用量化画像

画像层核心实体，承载 11 个维度组的完整事实数据。

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| profile_id | str | ✅ | UUID | ✅ |
| security_id | str | ✅ | 标准化 security_id（如 `CN:600519`） | ✅ |
| as_of | str | ✅ | 截面日期 YYYY-MM-DD | ✅ |
| market | str | ✅ | CN / HK / US | ✅ |
| fundamental | ProfileDimension\|None | — | 基本面维度 | ✅ |
| growth | ProfileDimension\|None | — | 成长维度 | ✅ |
| valuation | ProfileDimension\|None | — | 估值维度 | ✅ |
| quality | ProfileDimension\|None | — | 质量维度 | ✅ |
| technical | ProfileDimension\|None | — | 技术维度 | ✅ |
| capital_flow | ProfileDimension\|None | — | 资金流维度 | — P2 |
| sentiment | ProfileDimension\|None | — | 情绪维度 | — P2 |
| catalyst | ProfileDimension\|None | — | 催化剂维度 | — P3 |
| risk_factors | ProfileDimension\|None | — | 风险因子维度 | ✅ |
| portfolio_context | ProfileDimension\|None | — | 组合上下文维度 | — P4 |
| data_quality | ProfileDimension | ✅ | 数据质量维度 | ✅ |
| build_version | str | ✅ | 框架版本（如 `1.0.0`） | ✅ |
| data_source_version | str | ✅ | unified_data 版本标识 | ✅ |
| build_duration_ms | float | ✅ | 构建耗时（ms） | ✅ |
| warnings | list[str] | — | 构建过程中的警告 | ✅ |
| created_at | str | ✅ | ISO 8601 | ✅ |

```python
@dataclass
class StockQuantProfile:
    profile_id: str
    security_id: str
    as_of: str
    market: str
    fundamental: ProfileDimension | None = None
    growth: ProfileDimension | None = None
    valuation: ProfileDimension | None = None
    quality: ProfileDimension | None = None
    technical: ProfileDimension | None = None
    capital_flow: ProfileDimension | None = None
    sentiment: ProfileDimension | None = None
    catalyst: ProfileDimension | None = None
    risk_factors: ProfileDimension | None = None
    portfolio_context: ProfileDimension | None = None
    data_quality: ProfileDimension = field(default_factory=ProfileDimension)
    build_version: str = ""
    data_source_version: str = ""
    build_duration_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""
```

### 5.3 ProfileDimension — 画像维度

每个维度组的通用结构。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| dimension_name | str | ✅ | 维度组名（fundamental / growth / valuation ...） |
| metrics | dict | ✅ | 指标名→指标值的映射 |
| percentiles | dict | — | 指标名→全市场分位数（0-1）的映射 |
| rankings | dict | — | 指标名→行业/板块排名的映射 |
| summary | str | — | 维度组一句话摘要 |
| tags | list[str] | — | 维度标签（如 `["高增长", "毛利率扩张"]`） |
| data_gaps | list[str] | — | 本维度缺失的数据项列表 |
| source_freshness | str | — | 数据新鲜度标签（见 unified_data FreshnessPolicy） |

```python
@dataclass
class ProfileDimension:
    dimension_name: str = ""
    metrics: dict = field(default_factory=dict)
    percentiles: dict = field(default_factory=dict)
    rankings: dict = field(default_factory=dict)
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    source_freshness: str = "unknown"
```

### 5.4 StrategyModel — 策略模型参数（注册件）

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| model_id | str | ✅ | 唯一标识（`growth_v1` 等） | ✅ |
| name | str | ✅ | 人类可读名称 | ✅ |
| description | str | — | 模型说明 | ✅ |
| version | str | ✅ | 语义版本 | ✅ |
| category | str | ✅ | growth / value / quality / momentum / dividend / event | ✅ |
| enabled | bool | — | 是否启用 | ✅ |
| params_schema | dict | — | 参数 JSON Schema（供验证） | ✅ |
| default_params | dict | — | 默认参数 | ✅ |
| required_dimensions | list[str] | ✅ | 依赖的画像维度组 | ✅ |
| created_at | str | ✅ | ISO 8601 | ✅ |

```python
@dataclass
class StrategyModel:
    model_id: str
    name: str
    version: str
    category: str
    required_dimensions: list[str] = field(default_factory=list)
    description: str = ""
    enabled: bool = True
    params_schema: dict = field(default_factory=dict)
    default_params: dict = field(default_factory=dict)
    created_at: str = ""
```

### 5.5 ModelScore — 单模型评分

统一输出协议，是画像层与综合层的核心耦合接口。

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| score_id | str | ✅ | UUID | ✅ |
| profile_id | str | ✅ | FK → StockQuantProfile | ✅ |
| model_id | str | ✅ | FK → StrategyModel | ✅ |
| security_id | str | ✅ | 冗余（方便查询） | ✅ |
| as_of | str | ✅ | 截面日期 | ✅ |
| score | float | ✅ | 0-100 综合得分 | ✅ |
| rating | str | ✅ | strong_buy / buy / hold / reduce / avoid / na | ✅ |
| confidence | float | ✅ | 置信度 0-1 | ✅ |
| sub_scores | dict | — | 子维度得分 | ✅ |
| strengths | list[str] | — | 优势点（≤5 条） | ✅ |
| weaknesses | list[str] | — | 弱点（≤5 条） | ✅ |
| contradictions | list[str] | — | 自相矛盾处 | ✅ |
| assumptions | list[str] | — | 关键假设 | ✅ |
| data_gaps | list[str] | — | 数据缺口 | ✅ |
| model_version | str | ✅ | 模型版本 | ✅ |
| params_snapshot | dict | ✅ | 本次评分使用的参数快照 | ✅ |
| detail | dict | — | 模型私有明细 | ✅ |
| created_at | str | ✅ | ISO 8601 | ✅ |

```python
@dataclass
class ModelScore:
    score_id: str
    profile_id: str
    model_id: str
    security_id: str
    as_of: str
    score: float = 0.0
    rating: str = "na"
    confidence: float = 0.0
    sub_scores: dict = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    model_version: str = ""
    params_snapshot: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)
    created_at: str = ""
```

### 5.6 CrossValidationMatrix — 交叉验证矩阵

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| cv_id | str | ✅ | UUID | ✅ |
| profile_id | str | ✅ | FK → StockQuantProfile | ✅ |
| security_id | str | ✅ | 冗余 | ✅ |
| as_of | str | ✅ | 截面日期 | ✅ |
| model_count | int | ✅ | 参与验证的模型数量 | ✅ |
| consensus | str | ✅ | bullish / neutral / bearish | ✅ |
| consensus_strength | float | ✅ | 共识强度 0-1（模型一致度） | ✅ |
| score_variance | float | — | 评分方差 | ✅ |
| rating_distribution | dict | ✅ | 各评级计数 `{"buy": 2, "hold": 1}` | ✅ |
| conflicts | list[dict] | — | 冲突列表，每条含 `{model_a, model_b, dimension, description}` | ✅ |
| value_trap | bool | — | 是否疑似价值陷阱 | ✅ |
| value_trap_detail | str\|None | — | 价值陷阱详情 | ✅ |
| growth_trap | bool | — | 是否疑似成长陷阱 | ✅ |
| growth_trap_detail | str\|None | — | 成长陷阱详情 | ✅ |
| momentum_quality_mismatch | bool | — | 动量强但质量弱标注 | — P2 |
| dominant_model | str\|None | — | 主导模型（按置信度+权重选举） | ✅ |
| narrative | str | — | 综合解释文本（面向用户） | ✅ |
| created_at | str | ✅ | ISO 8601 | ✅ |

```python
@dataclass
class CrossValidationMatrix:
    cv_id: str
    profile_id: str
    security_id: str
    as_of: str
    model_count: int = 0
    consensus: str = "neutral"
    consensus_strength: float = 0.0
    score_variance: float = 0.0
    rating_distribution: dict = field(default_factory=dict)
    conflicts: list[dict] = field(default_factory=list)
    value_trap: bool = False
    value_trap_detail: str | None = None
    growth_trap: bool = False
    growth_trap_detail: str | None = None
    momentum_quality_mismatch: bool = False
    dominant_model: str | None = None
    narrative: str = ""
    created_at: str = ""
```

### 5.7 RiskAudit — 风险审计

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| audit_id | str | ✅ | UUID | ✅ |
| profile_id | str | ✅ | FK → StockQuantProfile | ✅ |
| security_id | str | ✅ | 冗余 | ✅ |
| as_of | str | ✅ | 截面日期 | ✅ |
| financial_landmine | list[dict] | — | 财务排雷清单，每项含 `{item, severity, detail}` | ✅ |
| death_audit | list[dict] | — | 死亡审计项，每项含 `{question, answer, risk_level}` | — P2 |
| cognitive_bias | list[str] | — | 识别的认知偏差列表 | — P2 |
| second_order_effect | list[dict] | — | 二阶效应分析 | — P3 |
| info_confidence | float | ✅ | 信息置信度 0-1（数据覆盖率+时效+一致性） | ✅ |
| info_confidence_detail | dict | ✅ | 置信度明细 `{coverage, timeliness, consistency}` | ✅ |
| overall_risk_level | str | ✅ | low / medium / high / critical | ✅ |
| summary | str | ✅ | 一句话风险总结 | ✅ |
| created_at | str | ✅ | ISO 8601 | ✅ |

```python
@dataclass
class RiskAudit:
    audit_id: str
    profile_id: str
    security_id: str
    as_of: str
    financial_landmine: list[dict] = field(default_factory=list)
    death_audit: list[dict] = field(default_factory=list)
    cognitive_bias: list[str] = field(default_factory=list)
    second_order_effect: list[dict] = field(default_factory=list)
    info_confidence: float = 0.0
    info_confidence_detail: dict = field(default_factory=dict)
    overall_risk_level: str = "medium"
    summary: str = ""
    created_at: str = ""
```

### 5.8 PathProjection — 路径推演

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| projection_id | str | ✅ | UUID | — P2 |
| profile_id | str | ✅ | FK → StockQuantProfile | — P2 |
| security_id | str | ✅ | 冗余 | — P2 |
| as_of | str | ✅ | 截面日期 | — P2 |
| cycle_stage | str | — | 周期阶段（recovery / expansion / plateau / contraction / custom） | — P2 |
| cycle_confidence | float | — | 周期判断置信度 0-1 | — P2 |
| expectation_gap | dict | — | 预期差 `{consensus_value, framework_value, gap_direction, gap_magnitude}` | — P2 |
| scenarios | list[dict] | — | 三情景推演 `[{name: "bull", probability, key_variables, target_price}, ...]` | — P2 |
| path_switch_signals | list[dict] | — | 路径切换信号 `[{indicator, current_value, switch_threshold, direction}]` | — P2 |
| narrative | str | — | 面向用户的推演叙述 | — P2 |
| created_at | str | ✅ | ISO 8601 | — P2 |

```python
@dataclass
class PathProjection:
    projection_id: str
    profile_id: str
    security_id: str
    as_of: str
    cycle_stage: str = "unknown"
    cycle_confidence: float = 0.0
    expectation_gap: dict = field(default_factory=dict)
    scenarios: list[dict] = field(default_factory=list)
    path_switch_signals: list[dict] = field(default_factory=list)
    narrative: str = ""
    created_at: str = ""
```

### 5.9 PortfolioFitAdvice — 组合适配

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| fit_id | str | ✅ | UUID | — P4 |
| security_id | str | ✅ | 被评估标的 | — P4 |
| as_of | str | ✅ | 截面日期 | — P4 |
| current_portfolio_size | int | — | 组合持仓数量 | — P4 |
| industry | dict | — | `{l1_code, l1_name, current_weight, post_add_weight}` | — P4 |
| style | dict | — | `{primary_style, secondary_style, style_fit_score}` | — P4 |
| correlation_vs_portfolio | float\|None | — | 与现有组合的加权平均相关性 | — P4 |
| concentration_impact | dict | — | `{current_hhi, post_add_hhi, change}` | — P4 |
| marginal_risk_contribution | float\|None | — | 边际风险贡献 | — P4 |
| recommendation | str | — | favorable / ok / caution / avoid | — P4 |
| summary | str | — | 适配总结 | — P4 |
| created_at | str | ✅ | ISO 8601 | — P4 |

### 5.10 ReportSnapshot — 报告快照

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| report_id | str | ✅ | UUID | ✅ |
| security_id | str | ✅ | 标的 | ✅ |
| as_of | str | ✅ | 截面日期 | ✅ |
| profile_id | str | ✅ | FK → StockQuantProfile | ✅ |
| cv_id | str\|None | — | FK → CrossValidationMatrix | ✅ |
| audit_id | str\|None | — | FK → RiskAudit | ✅ |
| projection_id | str\|None | — | FK → PathProjection | — |
| fit_id | str\|None | — | FK → PortfolioFitAdvice | — |
| formats_generated | list[str] | ✅ | 生成的格式列表（markdown / json / html） | ✅ |
| markdown_content | str\|None | — | Markdown 全文（可存入文件系统替代） | — |
| json_content | dict\|None | — | JSON 结构化 block | ✅ |
| metadata | dict | ✅ | 生成时间、框架版本、模型版本、数据源版本、data_gaps 汇总、免责声明 | ✅ |
| created_at | str | ✅ | ISO 8601 | ✅ |

---

## 6. MongoDB 持久化设计

### 6.1 集合命名与数据库

所有新增集合使用 `08_research_stock_*` 前缀，存放在 `tradingagents` 数据库下，与 TA-CN（无前缀）、unified_data（`03_data_ud_*`）、task_center（`10_infra_tc_*`）物理隔离。

| 集合名 | 实体 | 数据库 | MVP |
|---|---|---|---|
| `08_research_stock_universe` | StockUniverse | tradingagents | ✅ |
| `08_research_stock_profile` | StockQuantProfile | tradingagents | ✅ |
| `08_research_stock_model_def` | StrategyModel | tradingagents | ✅ |
| `08_research_stock_model_score` | ModelScore | tradingagents | ✅ |
| `08_research_stock_cross_validation` | CrossValidationMatrix | tradingagents | ✅ |
| `08_research_stock_risk_audit` | RiskAudit | tradingagents | ✅ |
| `08_research_stock_path_projection` | PathProjection | tradingagents | — |
| `08_research_stock_portfolio_fit` | PortfolioFitAdvice | tradingagents | — |
| `08_research_stock_report_snapshot` | ReportSnapshot | tradingagents | ✅ |

### 6.2 集合详细 Schema

#### 6.2.1 `08_research_stock_universe`

```python
# 集合: 08_research_stock_universe
# 数据库: tradingagents
# 唯一键: {universe_id}
# 索引: {market: 1}, {parent_universe_id: 1}

{
    "_id": ObjectId,
    "universe_id": "cn_a_share_all",
    "name": "全部A股",
    "market": "CN",
    "security_ids": ["CN:600519", "CN:000858", ...],
    "filter_rule": {"exclude_st": true, "exclude_new_listed_days": 60},
    "parent_universe_id": null,
    "refreshed_at": ISODate("2026-07-12T15:30:00Z"),
    "created_at": ISODate("2026-07-12T00:00:00Z"),
    "updated_at": ISODate("2026-07-12T15:30:00Z")
}
```

#### 6.2.2 `08_research_stock_profile`

```python
# 集合: 08_research_stock_profile
# 数据库: tradingagents
# 唯一键: {security_id, as_of}
# 索引: {security_id: 1, as_of: -1}, {as_of: -1}, {market: 1, as_of: -1}
# TTL: 保留 90 天（可选），按 as_of 计算

{
    "_id": ObjectId,
    "profile_id": "uuid-...",
    "security_id": "CN:600519",
    "as_of": "2026-07-12",
    "market": "CN",
    "fundamental": {
        "dimension_name": "fundamental",
        "metrics": {
            "industry_l1": "食品饮料",
            "industry_l2": "白酒",
            "total_mv": 2250000000000,
            "circ_mv": 2250000000000,
            "list_date": "2001-08-27",
            "market_status": "正常"
        },
        "percentiles": {"total_mv": 0.99},
        "summary": "白酒行业龙头，超大盘",
        "tags": ["龙头", "消费", "高市值"],
        "data_gaps": [],
        "source_freshness": "fresh"
    },
    "growth": {
        "dimension_name": "growth",
        "metrics": {
            "revenue_yoy_1y": 0.15,
            "revenue_yoy_3y_cagr": 0.12,
            "net_profit_yoy_1y": 0.18,
            "eps_yoy_1y": 0.17,
            "gross_margin_trend": "up",
            "roe_trend": "stable"
        },
        "percentiles": {"revenue_yoy_1y": 0.72, "net_profit_yoy_1y": 0.75},
        "summary": "中高速成长，毛利率改善",
        "tags": ["稳健成长", "毛利率扩张"],
        "data_gaps": [],
        "source_freshness": "fresh"
    },
    # ... valuation, quality, technical, capital_flow, sentiment, catalyst, risk_factors, portfolio_context
    "data_quality": {
        "dimension_name": "data_quality",
        "metrics": {
            "dimensions_covered": 11,
            "dimensions_with_gaps": 2,
            "total_metrics": 85,
            "missing_metrics": 7,
            "coverage_ratio": 0.92,
            "avg_source_freshness_score": 0.85
        },
        "data_gaps": ["capital_flow", "sentiment"],
        "source_freshness": "mixed"
    },
    "build_version": "0.1.0",
    "data_source_version": "unified_data:0.1.0:ta_cn:daily_sync_20260712",
    "build_duration_ms": 1250.5,
    "warnings": ["资本流动数据不可用 - unified_data 资金流域未部署"],
    "created_at": ISODate("2026-07-12T16:00:00Z")
}
```

#### 6.2.3 `08_research_stock_model_def`

```python
# 集合: 08_research_stock_model_def
# 数据库: tradingagents
# 唯一键: {model_id}
# 索引: {category: 1}, {enabled: 1}

{
    "_id": ObjectId,
    "model_id": "growth_v1",
    "name": "成长股模型 V1",
    "description": "基于成长+质量+估值辅助的成长股评分模型",
    "version": "1.0.0",
    "category": "growth",
    "enabled": true,
    "params_schema": {
        "type": "object",
        "properties": {
            "growth_weight": {"type": "number", "minimum": 0, "maximum": 1},
            "quality_weight": {"type": "number", "minimum": 0, "maximum": 1},
            "valuation_weight": {"type": "number", "minimum": 0, "maximum": 1},
            "min_revenue_growth": {"type": "number"},
            "min_roe": {"type": "number"},
            "max_pe": {"type": "number"}
        }
    },
    "default_params": {
        "growth_weight": 0.5,
        "quality_weight": 0.3,
        "valuation_weight": 0.2,
        "min_revenue_growth": 0.10,
        "min_roe": 0.15,
        "max_pe": 50
    },
    "required_dimensions": ["growth", "quality", "valuation", "risk_factors"],
    "created_at": ISODate("2026-07-12T00:00:00Z")
}
```

#### 6.2.4 `08_research_stock_model_score`

```python
# 集合: 08_research_stock_model_score
# 数据库: tradingagents
# 唯一键: {profile_id, model_id}
# 索引: {security_id: 1, as_of: -1}, {model_id: 1, as_of: -1}, {rating: 1}
# TTL: 保留 90 天

{
    "_id": ObjectId,
    "score_id": "uuid-...",
    "profile_id": "uuid-...",
    "model_id": "growth_v1",
    "security_id": "CN:600519",
    "as_of": "2026-07-12",
    "score": 78.5,
    "rating": "buy",
    "confidence": 0.85,
    "sub_scores": {
        "growth_subscore": 82.0,
        "quality_subscore": 85.0,
        "valuation_subscore": 55.0
    },
    "strengths": ["营收持续双位数增长", "ROE 稳定在 25% 以上", "毛利率连续三年改善"],
    "weaknesses": ["当前 PE 处于历史 80% 分位", "估值不便宜"],
    "contradictions": ["高增长但估值透支 — 若增速放缓 PE 面临双杀风险"],
    "assumptions": ["未来 3 年营收 CAGR 保持 12%+", "茅台酒供不应求格局不变"],
    "data_gaps": [],
    "model_version": "1.0.0",
    "params_snapshot": {"growth_weight": 0.5, "quality_weight": 0.3, "valuation_weight": 0.2, "min_revenue_growth": 0.10},
    "detail": {"growth_score_breakdown": {"revenue_yoy": 18.0, "eps_yoy": 21.0, "gross_margin": 15.0}},
    "created_at": ISODate("2026-07-12T16:01:00Z")
}
```

#### 6.2.5 `08_research_stock_cross_validation`

```python
# 集合: 08_research_stock_cross_validation
# 唯一键: {profile_id}
# 索引: {security_id: 1, as_of: -1}

{
    "_id": ObjectId,
    "cv_id": "uuid-...",
    "profile_id": "uuid-...",
    "security_id": "CN:600519",
    "as_of": "2026-07-12",
    "model_count": 5,
    "consensus": "bullish",
    "consensus_strength": 0.80,
    "score_variance": 142.5,
    "rating_distribution": {"buy": 3, "hold": 1, "avoid": 0, "strong_buy": 1},
    "conflicts": [
        {
            "model_a": "growth_v1",
            "model_b": "value_v1",
            "dimension": "valuation",
            "description": "成长模型认为成长消化估值，价值模型认为 PE 过高"
        }
    ],
    "value_trap": false,
    "value_trap_detail": null,
    "growth_trap": false,
    "growth_trap_detail": null,
    "momentum_quality_mismatch": false,
    "dominant_model": "quality_v1",
    "narrative": "5 个模型中 4 个看多，共识看涨。quality_v1 置信度最高（0.92）。估值分歧是主要冲突 — 成长/质量模型对高 PE 容忍度不同。无价值陷阱或成长陷阱信号。",
    "created_at": ISODate("2026-07-12T16:01:30Z")
}
```

#### 6.2.6 `08_research_stock_risk_audit`

```python
# 集合: 08_research_stock_risk_audit
# 唯一键: {profile_id}
# 索引: {security_id: 1, as_of: -1}, {overall_risk_level: 1}

{
    "_id": ObjectId,
    "audit_id": "uuid-...",
    "profile_id": "uuid-...",
    "security_id": "CN:600519",
    "as_of": "2026-07-12",
    "financial_landmine": [
        {"item": "应收账款异常", "severity": "low", "detail": "应收/营收比 2.3%，行业 5.8%，远低于行业均值"},
        {"item": "商誉占比", "severity": "low", "detail": "商誉/净资产 0.1%，可忽略"},
        {"item": "现金流匹配度", "severity": "low", "detail": "经营现金流/净利润 1.05x，健康"}
    ],
    "death_audit": [],
    "cognitive_bias": ["锚定效应 — 可能锚定历史高估值"],
    "second_order_effect": [],
    "info_confidence": 0.88,
    "info_confidence_detail": {"coverage": 0.92, "timeliness": 0.95, "consistency": 0.78},
    "overall_risk_level": "low",
    "summary": "财务质量健康，未发现排雷信号。信息置信度 88%，unified_data 覆盖完整。主要风险在估值端而非基本面。",
    "created_at": ISODate("2026-07-12T16:01:30Z")
}
```

#### 6.2.7 `08_research_stock_report_snapshot`

```python
# 集合: 08_research_stock_report_snapshot
# 唯一键: {security_id, as_of}
# 索引: {security_id: 1, as_of: -1}

{
    "_id": ObjectId,
    "report_id": "uuid-...",
    "security_id": "CN:600519",
    "as_of": "2026-07-12",
    "profile_id": "uuid-...",
    "cv_id": "uuid-...",
    "audit_id": "uuid-...",
    "projection_id": null,
    "fit_id": null,
    "formats_generated": ["json", "markdown"],
    "markdown_content": null,
    "json_content": {
        "security_id": "CN:600519",
        "as_of": "2026-07-12",
        "profile": {...},
        "scores": [...],
        "cross_validation": {...},
        "risk_audit": {...}
    },
    "metadata": {
        "framework_version": "0.1.0",
        "model_versions": {"growth_v1": "1.0.0", "value_v1": "1.0.0"},
        "data_source_version": "unified_data:0.1.0",
        "data_gaps_summary": ["capital_flow", "sentiment"],
        "disclaimer": "研究辅助，非交易决策。评分基于历史数据，不构成投资建议。",
        "generated_at": ISODate("2026-07-12T16:02:00Z"),
        "generation_duration_ms": 350
    },
    "created_at": ISODate("2026-07-12T16:02:00Z")
}
```

### 6.3 写入触发点精确映射

| 写入操作 | 触发点（文件:函数） | 字段子集 | 写入前校验 | 错误处理 |
|---|---|---|---|---|
| 写入 Profile | `profile/builder.py:ProfileBuilder.build_profile()` | profile 全部字段 | SecurityId 有效性；unified_data 连接可用性；as_of 格式 | unified_data 不可用 → 抛 DataNotAvailableError；返回空 profile + warnings |
| 写入 ModelScore | `models/base.py:StrategyModel.score()` → persist repo | score 全部字段 | profile_id 存在性；score 0-100；rating 合法枚举 | model 异常 → 跳过该模型，记录 model_skipped 事件 |
| 写入 CrossValidation | `synthesis/cross_validator.py:CrossValidator.validate()` | cv 全部字段 | model_count ≥ 2 | 仅 1 个模型可用 → 跳过 CrossValidator，标注为 single_model |
| 写入 RiskAudit | `synthesis/risk_auditor.py:RiskAuditor.audit()` | audit 全部字段 | profile 存在 | 无 profile → 跳过 |
| 写入 ReportSnapshot | `report/renderer.py:ReportRenderer.render()` | report 全部字段 + json_content | 至少 profile 存在 | profile 不存在 → 抛 MissingProfileError |
| 写入 Universe | `universe/registry.py:StockUniverseRegistry.refresh()` | universe 全部字段 | market 合法 | unified_data 不可用 → 复用上次 security_ids |

### 6.4 禁止 SQLite 声明

**stock framework 不使用 SQLite 作为任何持久化后端**。

- 所有新增集合均为 MongoDB 集合（`08_research_stock_*`）。
- 画像构建所需的数据来自 `unified_data.UnifiedDataClient`，后者通过 adapter 读取 TA-CN MongoDB + DSA SQLite（均为只读，不新增写入）。
- 测试环境使用 **mongomock** 或独立测试库（`yquant_test`），禁止写入 `tradingagents` 生产库。
- 文档中提及 SQLite 的唯一场景：说明 DSA 的 `StockDaily` (SQLAlchemy ORM) 是 DSA 既有数据源，由 unified_data 的 `DSASQLiteAdapter` 只读适配，stock framework 不感知此细节。

---

## 7. 画像层设计（Profile Layer）

### 7.1 ProfileBuilder 主流程

```
ProfileBuilder.build_profile(security_id, as_of)
    │
    ├─ 1. 校验 security_id 合法性 → SecurityId 对象
    │
    ├─ 2. 从 unified_data 并行拉取所有维度原始数据
    │      ├─ fundamental: client.get_stock_info(sid) + client.get_financial_metrics(sid)
    │      ├─ growth: client.get_income_statement(sid) [3期] → 框架内 YoY/CAGR
    │      ├─ valuation: client.get_valuation_snapshot(sid)
    │      ├─ quality: client.get_financial_metrics(sid) + balance_sheet + cash_flow
    │      ├─ technical: client.get_kline_daily(sid, limit=250) → 框架内指标计算
    │      ├─ capital_flow: client.get_capital_flow(sid, limit=60) [Phase 2]
    │      ├─ sentiment: client.get_market_sentiment() + news(sid) [Phase 2]
    │      ├─ catalyst: client.get_news(sid) [Phase 3]
    │      ├─ risk_factors: kline 波动率 + 财务排雷指标（框架内）
    │      ├─ portfolio_context: portfolio adapter 只读 [Phase 4]
    │      └─ data_quality: client.get_quality_summary(sid)
    │
    ├─ 3. 各 DimensionCalculator 计算指标、分位数、排名
    │      └─ 数据缺失 → 对应 Dimension 标记 data_gaps + 指标 null
    │
    ├─ 4. 组装 StockQuantProfile
    │
    └─ 5. 写入 08_research_stock_profile + 返回
```

### 7.2 首批维度详细指标

#### 7.2.1 基本面维度（Phase 1）

| 指标 | 来源 | 计算方式 |
|---|---|---|
| industry_l1 / industry_l2 | `get_stock_info(sid)` → IndustryInfo | 直接取值 |
| total_mv / circ_mv | `get_stock_info(sid)` → 市值字段 | 直接取值 |
| market_status | `get_stock_info(sid)` → status | 正常 / ST / *ST / 退市 |
| list_days | `get_stock_info(sid)` → list_date | today - list_date |
| business_profile | `get_stock_info(sid)` → 业务描述 | 直接取值（可为 LLM 总结预留） |

#### 7.2.2 成长维度（Phase 1）

| 指标 | 计算方式 | 注 |
|---|---|---|
| revenue_yoy_1y / 3y_cagr | income_statement 多期营收同比 | 最少 2 期，最优 5 期 |
| net_profit_yoy_1y / 3y_cagr | income_statement 多期净利润同比 | 同上 |
| eps_yoy_1y | 净利润 / 总股本 YoY | |
| gross_margin_trend | 毛利率 3 期对比 → up / stable / down | |
| roe_trend | ROE 3 期对比 → up / stable / down | |

#### 7.2.3 估值维度（Phase 1）

| 指标 | 来源 | 分位数基准 |
|---|---|---|
| pe_ttm / pb_mrq / ps_ttm | `get_valuation_snapshot(sid)` | 历史 5 年分位 + 全市场分位 |
| ev_ebitda | 框架内计算（MV + 净负债）/ EBITDA | 历史 5 年分位 |
| dividend_yield | `get_daily_basic(sid)` | 全市场分位 |

#### 7.2.4 质量维度（Phase 1）

| 指标 | 计算方式 | 排雷阈值 |
|---|---|---|
| roe / roic | 净利润/净资产，NOPAT/投入资本 | — |
| gross_margin / net_margin | 毛利/营收，净利/营收 | 毛利率↓10pp 触发排雷 |
| debt_to_asset | 总负债/总资产 | >70% 触发关注 |
| cashflow_match | 经营现金流/净利润 | <0.5 触发关注 |
| receivables_ratio | 应收/营收 | >行业 2x 触发关注 |
| goodwill_ratio | 商誉/净资产 | >30% 触发关注 |
| inventory_abnormal | 存货增速 vs 营收增速 | 存货增速 > 营收增速 2x 触发关注 |

#### 7.2.5 技术维度（Phase 1）

| 指标 | 计算 | 参数默认值 |
|---|---|---|
| ma_alignment | MA5/MA20/MA60/MA120 排列 → bullish / bearish / mixed | — |
| price_position | (close - MA60_low) / (MA60_high - MA60_low) | 窗口 60 日 |
| rsi_14 | 标准 RSI 计算 | 周期 14 |
| macd_signal | MACD 金叉/死叉/发散 | 12/26/9 |
| bollinger_position | (close - lower) / (upper - lower) | 周期 20，2σ |
| volume_ratio | 5 日均量 / 20 日均量 | — |
| turnover_rate_5d | 5 日平均换手率 | — |

### 7.3 数据质量维度

| 指标 | 计算方式 |
|---|---|
| dimensions_covered | count(d for d in dimensions if d.metrics) |
| dimensions_with_gaps | count(d for d in dimensions if d.data_gaps) |
| coverage_ratio | dimensions_covered / total_dimensions |
| avg_source_freshness_score | 各维度 source_freshness 映射为分数后取平均 |

---

## 8. 策略模型插件层设计

### 8.1 抽象基类协议

```python
# skills/research/stock/models/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ModelParams:
    """模型参数容器，由 configs/{model_id}.yaml 注入"""
    pass

class StrategyModel(ABC):
    """策略模型抽象基类"""

    model_id: str
    name: str
    version: str
    category: str
    required_dimensions: list[str]

    @abstractmethod
    def validate_profile(self, profile: StockQuantProfile) -> list[str]:
        """校验画像是否包含该模型所需的全部维度。返回缺失维度列表。"""
        ...

    @abstractmethod
    def score(self, profile: StockQuantProfile, params: ModelParams) -> ModelScore:
        """核心评分逻辑。输入画像 + 参数 → 输出 ModelScore。"""
        ...

    def explain(self, score: ModelScore) -> str:
        """生成面向用户的评分解释文本。默认调用 strengths/weaknesses/contradictions 拼接。"""
        ...
```

### 8.2 首批评分逻辑概要

| 模型 | 评分公式概要 | buy 触发条件 | avoid 触发条件 |
|---|---|---|---|
| growth_v1 | growth_weight×成长子分 + quality_weight×质量子分 + valuation_weight×估值子分 | score≥70 且 rating≠avoid | revenue_yoy<5% 连续 2 期 |
| value_v1 | valuation_weight×估值子分 + quality_weight×质量子分 + growth_weight×成长子分（辅助） | score≥70 且 PE<min(行业均值,历史25分位) | ROE<5% 或 debt_to_asset>70% |
| quality_v1 | quality 子分×0.6 + growth_stability×0.2 + valuation_ceiling×0.2 | score≥70 且 ROIC>15% | cashflow_match<0.3 或 receivables_ratio>行业3x |
| momentum_v1 | technical 子分×0.5 + flow 子分×0.3 + sentiment 子分×0.2 | score≥70 且 ma_alignment=bullish 且 volume_ratio>1.2 | 连续 3 日主力净流出且 rsi>80 |
| dividend_lowvol_v1 | dividend_stability×0.4 + low_volatility×0.3 + quality×0.2 + valuation×0.1 | score≥70 且 dividend_yield>2.5% 且 beta<0.8 | dividend_yield<1% 或 payout_ratio>100% |
| event_driven_v1 | catalyst 子分×0.5 + sentiment 子分×0.3 + valuation_floor×0.2 | score≥70 且 含 catalyst_score>60 的强催化剂 | catalyst_score<30（无明确催化剂） |

### 8.3 模型注册与发现

```python
# skills/research/stock/models/registry.py

class ModelRegistry:
    """模型注册中心。加载 configs/*.yaml 初始化。"""

    _models: dict[str, StrategyModel] = {}

    @classmethod
    def register(cls, model: StrategyModel) -> None: ...
    @classmethod
    def get(cls, model_id: str) -> StrategyModel: ...
    @classmethod
    def list_enabled(cls) -> list[str]: ...
    @classmethod
    def list_by_category(cls, category: str) -> list[str]: ...
```

模型通过 configs YAML + 代码导入注册，不在数据库中动态注册（StrategyModel 的 MongoDB 集合仅做记录快照和版本历史）。

---

## 9. 综合层设计（Synthesis Layer）

### 9.1 CrossValidator 交叉验证逻辑

```
CrossValidator.validate(scores: List[ModelScore]) → CrossValidationMatrix
    │
    ├─ 1. 计算共识方向
    │      每个模型的 rating 映射为数值（strong_buy=5 ... avoid=0）
    │      加权平均（按 confidence 加权）→ consensus direction
    │
    ├─ 2. 计算共识强度
    │      1 - std(score) / mean(score)（归一化）
    │
    ├─ 3. 冲突检测
    │      两两比较模型：若 rating 差 ≥ 2 且同一维度组评估方向相反 → 记录冲突
    │      重点关注：growth vs value 的估值分歧；quality vs momentum 的风格分歧
    │
    ├─ 4. 陷阱检测
    │      value_trap: value_v1 rating≥buy 且 quality 子分<40 → 疑似
    │      growth_trap: growth_v1 rating≥buy 且 cashflow_match<0.3 → 疑似
    │      momentum_quality_mismatch: momentum_v1 rating≥buy 且 quality_v1 rating≤avoid
    │
    ├─ 5. 主导模型选举
    │      model_score = confidence × model_weight（config 配置）
    │      选出 score 最高的模型为 dominant_model
    │
    └─ 6. 生成 narrative
```

### 9.2 RiskAuditor 审计逻辑

```
RiskAuditor.audit(profile, scores) → RiskAudit
    │
    ├─ 1. 财务排雷 (financial_landmine)
    │      遍历 quality 维度指标与阈值比对
    │      receivables_ratio > threshold → 应收异常
    │      goodwill_ratio > 0.3 → 商誉风险
    │      cashflow_match < 0.3 → 现金流恶化
    │      inventory_abnormal → 存货异常
    │      debt_to_asset > 0.7 → 高负债
    │
    ├─ 2. 信息置信度 (info_confidence)
    │      coverage: coverage_ratio (来自 data_quality 维度)
    │      timeliness: avg source_freshness mapped to 0-1
    │      consistency: 多数据源一致度（来自 unified_data quality_summary）
    │      综合 = coverage×0.4 + timeliness×0.3 + consistency×0.3
    │
    ├─ 3. 认知偏差 (cognitive_bias) [Phase 2]
    │      规则引擎：识别常见偏差模式
    │      - score_variance > 200 → 可能确认偏误（选择性关注有利模型）
    │      - 近期大涨 30%+ 且评分偏乐观 → 近因效应
    │      - volume_ratio > 3 且 mostly bullish → 羊群效应
    │
    └─ 4. 综合风险评级
           landmine count + info_confidence 推导 overall_risk_level
```

### 9.3 PathProjector 路径推演 [Phase 2+]

核心方法：

1. **周期判定**：基于技术维度（price_position / ma_alignment）+ 基本面（营收增速趋势 / ROE 趋势）+ 宏观指标（如有）→ cycle_stage。
2. **预期差分析**：框架评分（ModelScore）与卖方一致预期（如有 unified_data analyst_rating）对比。
3. **三场景推演**：base（延续当前趋势 60%）、bull（核心变量改善 20%）、bear（核心变量恶化 20%），每场景含关键变量变化和目标区间。
4. **路径切换信号**：列出 3-5 个关键观察指标及其切换阈值。

### 9.4 PortfolioFit 组合适配 [Phase 4]

只读 portfolio 数据（通过 portfolio adapter），不写入 production 集合：

1. 获取当前组合所有持仓的 industry / style / correlation。
2. 计算加入标的后：行业集中度 HHI 变化、风格偏离度、组合加权相关性变化。
3. 输出 recommendation：favorable / ok / caution / avoid。

---

## 10. 报告层设计

### 10.1 ReportRenderer 支持格式

| 格式 | MVP | 实现方式 |
|---|---|---|
| **JSON block** | ✅ | 直接序列化全部实体 dict，嵌套在 `ReportSnapshot.json_content` |
| **Markdown** | ✅ | Jinja2 模板渲染 → `ReportSnapshot.markdown_content` 或文件系统 |
| **HTML** | — P3 | Jinja2 模板 + 内联 CSS（参考 investment_framework 风格） |

### 10.2 Markdown 报告结构

```
# {股票名称}（{security_id}）量化分析报告
> 分析日期：{as_of} | 框架版本：{version} | 免责声明：研究辅助，非交易决策

## 1. 量化画像摘要
- 基本面 | 成长 | 估值 | 质量 | 技术 [各一行摘要 + 标签]

## 2. 多模型评分
| 模型 | 评分 | 评级 | 置信度 |
|------|------|------|--------|
[表格]

## 3. 交叉验证
- 共识：{consensus}（强度 {strength}）
- 冲突：[列表]
- 陷阱：[标注]

## 4. 风险审计
- 财务排雷：[清单]
- 信息置信度：{info_confidence}

## 5. 关键假设与风险
[assumptions + weaknesses 汇总]

## 6. 数据说明
- 数据源：unified_data
- 数据缺口：[列表]
- 报告生成时间：{timestamp}
```

### 10.3 JSON Block Schema

JSON 输出为 ReportSnapshot.json_content，包含完整的 profile dict + scores list + cv dict + audit dict + projection dict（如有）+ fit dict（如有）+ metadata。结构稳定后固化为 JSON Schema (`report/templates/json_report_schema.json`)。

---

## 11. Task Center 集成

### 11.1 任务注册

```python
# skills/research/stock/task_center/adapter.py

from task_center.registry import register_task
from task_center.jobs import create_job

def register_stock_tasks():
    register_task(
        task_id="stock.refresh_quant_profile",
        callable_path="stock.task_center._task_callables:batch_refresh_profiles",
        name="批量量化画像刷新",
        module="stock",
        retry_policy_id="default",
        tags=["研究", "画像", "批量"],
    )
    create_job(
        task_id="stock.refresh_quant_profile",
        schedule="3600",
        params={"universe_id": "cn_a_share_all", "max_workers": 4},
        timeout_seconds=10800,
        max_concurrent=1,
    )

    register_task(
        task_id="stock.score_strategy_models",
        callable_path="stock.task_center._task_callables:batch_score_models",
        name="策略模型批量评分",
        module="stock",
        retry_policy_id="default",
        tags=["研究", "评分", "批量"],
    )
    create_job(
        task_id="stock.score_strategy_models",
        schedule="3600",
        params={"universe_id": "cn_a_share_all"},
        timeout_seconds=7200,
        max_concurrent=1,
    )

    # ... stock.generate_stock_report, stock.batch_scan_universe,
    #     stock.backfill_model_scores, stock.portfolio_fit_refresh
```

### 11.2 Callable 实现模板

```python
# skills/research/stock/task_center/_task_callables.py

from task_center.runtime.progress import ProgressTracker

def batch_refresh_profiles(params: dict, execution_id: str) -> dict:
    """
    供 task_center 调用的业务 callable。
    params: {"universe_id": str, "as_of": str | None, "max_workers": int}
    """
    from stock.universe.registry import StockUniverseRegistry
    from stock.profile.builder import ProfileBuilder
    from stock.persistence.profile_repo import ProfileRepo

    universe = StockUniverseRegistry.get(params["universe_id"])
    as_of = params.get("as_of") or _today()
    security_ids = universe.security_ids
    total = len(security_ids)

    tracker = ProgressTracker(execution_id)
    tracker.create_steps([
        {"name": "refresh_profiles", "weight": 1.0}
    ])

    repo = ProfileRepo()
    succeeded = 0
    failed = 0

    for i, sid in enumerate(security_ids):
        try:
            profile = ProfileBuilder.build_profile(sid, as_of)
            repo.upsert(profile)
            succeeded += 1
        except Exception as e:
            failed += 1

        if (i + 1) % 10 == 0:
            tracker.update_progress(f"已处理 {i+1}/{total}，成功 {succeeded}，失败 {failed}")

    return {
        "total": total, "succeeded": succeeded, "failed": failed,
        "universe_id": params["universe_id"], "as_of": as_of
    }
```

---

## 12. Phase 0-7 分阶段实现路线

### Phase 0: Skeleton + Core Entities + Config（预计 1-2 天）

**范围**：
- `skills/research/stock/__init__.py` + `SKILL.md`
- `core/entities.py`（9 类 @dataclass）
- `core/security_id.py`
- `core/exceptions.py`
- `config.py`
- `persistence/mongo_client.py` + `mongo_schema.py`（索引定义）
- `tests/research/stock/conftest.py`（mongomock fixture）
- `tests/research/stock/test_entities.py`

**验收**：所有 dataclass 可实例化；MongoDB 集合索引定义有效；pytest 单测通过。
**测试**：unit test 仅 entities + exceptions + mongo_schema 校验。
**风险**：集合命名与 unified_data / task_center 前缀冲突 → 通过 `08_research_stock_*` 隔离。
**Verify/Review**：✅ Verify by yquanttester；✅ Review by yquantreviewer。

### Phase 1: Profile Layer MVP + 2 Models（预计 3-4 天）

**范围**：
- `profile/builder.py`（ProfileBuilder 完整流程）
- `profile/dimensions/`（fundamental / growth / valuation / quality / technical / risk_factors / data_quality 七个维度计算器）
- `profile/helpers/`（technical_indicators.py / financial_ratios.py / percentile.py）
- `models/base.py`（StrategyModel ABC + ModelParams）
- `models/growth_v1_model.py` + `models/value_v1_model.py`
- `models/registry.py` + `models/configs/growth_v1.yaml` + `models/configs/value_v1.yaml`
- `persistence/profile_repo.py` + `model_score_repo.py` + `model_def_repo.py`
- `universe/registry.py`
- `synthesis/cross_validator.py`
- `synthesis/risk_auditor.py`（仅 financial_landmine + info_confidence）
- `report/renderer.py`（Markdown + JSON）

**验收**：
- 给定 fixture unified_data，ProfileBuilder 输出含 5+ 维度的有效 StockQuantProfile。
- growth_v1 和 value_v1 对同一画像分别输出 ModelScore，rating 不可全为 na。
- CrossValidator 对 2 个模型输出正确 consensus / conflicts。
- RiskAudit financial_landmine 命中至少 2 类已知排雷项。
- Markdown 报告和 JSON block 均可生成。
- 同步调用 `build_profile + score + cross_validate + audit + render` 端到端通过。

**测试**：Unit test 37+：dimensions (7×5=35) + builder + models (3 per model × 2 = 6) + cross_validator (3) + risk_auditor (3) + renderer (2)。Integration test 2。
**风险**：unified_data 接口未就绪 → 使用 mock UnifiedDataClient 覆盖。
**Verify/Review**：✅ Verify by yquanttester；✅ Review by yquantreviewer。

### Phase 2: 资金流/情绪维度 + 3 个模型扩展 + 路径推演（预计 2-3 天）

**范围**：
- `profile/dimensions/capital_flow.py` + `sentiment.py`
- `models/quality_v1_model.py` + `momentum_v1_model.py` + `dividend_lowvol_v1_model.py`
- `synthesis/path_projector.py`
- `persistence/path_projection_repo.py`
- Backfill callable (`_task_callables:backfill_scores`)
- `synthesis/risk_auditor.py` 补充 death_audit + cognitive_bias

**验收**：6 个模型全评分；路径推演出 3 种 scenario；backfill 支持历史回填。
**测试**：Unit test 20+：dimensions (2×5) + models (3×6) + path_projector (3)。
**Verify/Review**：✅ Verify by yquanttester；✅ Review by yquantreviewer。

### Phase 3: 催化剂 + 事件驱动模型 + 批量任务 + HTML 报告（预计 2-3 天）

**范围**：
- `profile/dimensions/catalyst.py`
- `models/event_driven_v1_model.py`
- `task_center/adapter.py` + `_task_callables.py`（三大 MVP 任务注册）
- `report/templates/html_report.j2` + HTML 渲染
- `universe/scanner.py`（批量扫描）

**验收**：7 个模型完整评分；task_center 注册 3 个任务成功；HTML 报告渲染成功。
**测试**：Unit test 10+；Integration test 3（task integration）。
**Verify/Review**：✅ Verify by yquanttester；✅ Review by yquantreviewer。

### Phase 4: 组合适配 + Argus/DSA 边界适配器（预计 2-3 天）

**范围**：
- `synthesis/portfolio_fit.py`
- `persistence/portfolio_fit_repo.py`
- Argus 边界只读 adapter（Smart Money 持仓变化 → 资金流维度增强）
- DSA 边界 adapter（LLM 报告 → 催化剂维度增强）
- `portfolio_fit_refresh` task 注册

**验收**：PortfolioFitAdvice 产出正确；Argus 持仓数据只读消费成功。
**Verify/Review**：✅ Verify by yquanttester；✅ Review by yquantreviewer。

### Phase 5: 完整持久化 + TTL + 跨截面查询（预计 1-2 天）

**范围**：
- persistence repo 全覆盖（8 个集合 CRUD 完整）
- MongoDB TTL 索引验证
- `profile/search.py`（跨 security_id/as_of 查询）
- CLI 入口 `yq stock profile/scores/report`

**验收**：所有集合可写可读；TTL 自动清理验证；CLI 三命令可用。

### Phase 6: 多市场支持 + 回测框架（预计 3-5 天）

**范围**：
- 港股/美股 security_id 支持
- 港股/美股 unified_data provider 接入（Phase 3+）
- 模型回测接口：给定历史画像序列 → 输出历史 ModelScore 序列
- 回测评估（IC / IR / Hit Ratio / 分层回测）

**验收**：港股美股画像可构建；至少 2 个模型可回测并输出评估指标。

### Phase 7: 正式部署 + 运维 + 监控（预计 2-3 天）

**范围**：
- task_center scheduler 守护（Hermes cron → `yq scheduler start`）
- MongoDB 集合部署到 `tradingagents` 生产库
- 健康检查 endpoint
- 运营 Dashboard（与 task_center Dashboard 复用 HTML 看板）

**验收**：生产调度可用；MongoDB 集合创建完成；健康检查通过。

### 核心路径时间线

```
Phase 0:  ██░░░░░░░░░░░░░░  1-2 days
Phase 1:  ██████░░░░░░░░░░  3-4 days  ← MVP 里程碑
Phase 2:  ██████████░░░░░░  2-3 days
Phase 3:  ██████████████░░  2-3 days  ← 完整 7 模型 + task_center
Phase 4:  ████████████████  2-3 days
Phase 5:  █████████████████  1-2 days
Phase 6:  █████████████████  3-5 days
Phase 7:  █████████████████  2-3 days
────────────────────────────────
Total:    ~16-25 days
MVP:      ~4-6  days (Phase 0+1)
```

---

## 13. 文件清单

### 13.1 新增文件（预计 75+）

见 §3.2 模块目录结构中完整列出。代码文件 55+，测试文件 20+。

### 13.2 禁止修改的文件

| 路径 | 原因 |
|---|---|
| `skills/data/unified_data/**` | 归属 unified_data |
| `skills/infra/task_center/**` | 归属 task_center |
| `skills/apps/TradingAgents-CN/**` | TA-CN 不耦合 |
| `skills/research/daily_stock_analysis/**` | DSA 不修改 |
| `skills/research/argus/**` | Argus 不修改 |
| `skills/data/data-pipeline/**` | 数据管道不修改 |
| `skills/data/data_interface/**` | portfolio 数据接口不修改 |
| MongoDB `portfolio_position` / `portfolio_trade` / `signal` / `stock_pool` 集合 | 生产交易数据，绝不写入 |

---

## 14. 测试策略

### 14.1 总则

- **无真实外部数据源默认依赖**：所有测试使用 fixture/mock UnifiedDataClient，不连接 Tushare / AKShare / BaoStock。
- **MongoDB 测试用隔离库**：使用 `mongomock` 或独立测试库 `yquant_test`，**禁止写入 `tradingagents` 生产库**。
- **Fixtures 优先**：创建可复用的画像样本、ModelScore 样本、mock UnifiedDataClient。

### 14.2 测试层次

| 层次 | 覆盖对象 | 工具 | 最低覆盖率 |
|---|---|---|---|
| **Unit** | 实体 / 维度计算器 / 模型 / 交叉验证 / 审计 / 路径 / 适配 / 报告 | pytest + mongomock | ≥80% |
| **Integration** | ProfileBuilder → Model → CrossValidator → RiskAudit → Renderer 全链路 | pytest + mongomock | 3+ 场景 |
| **Smoke** | 端到端 build_profile → 评分 → 报告，覆盖 3 只不同特征股票 | pytest + mongomock | 3 只股票 |

### 14.3 模型测试特殊要求

- 每个策略模型至少包含 **3 个确定性测试用例**（buy / hold / avoid 各一），使用已知 fixture 画像。
- 评分结果必须对人可解释：`assert len(score.strengths) + len(score.weaknesses) > 0`。
- score 范围：0 ≤ score ≤ 100 且不为固定常量（避免空壳模型）。

### 14.4 关键 Fixtures

| Fixture | 路径 | 说明 |
|---|---|---|
| `mock_unified_data_client` | `tests/conftest.py` | 返回固定数据的 Mock UnifiedDataClient |
| `high_growth_profile` | `tests/fixtures/profile_samples.py` | 高成长股画像（如 600519） |
| `value_trap_profile` | `tests/fixtures/profile_samples.py` | 低 PE 但质量恶化的画像 |
| `growth_trap_profile` | `tests/fixtures/profile_samples.py` | 高成长但现金流不匹配的画像 |
| `low_quality_profile` | `tests/fixtures/profile_samples.py` | 含财务排雷信号的画像 |
| `mock_model_scores` | `tests/fixtures/model_score_samples.py` | 5 个模型评分样本 |
| `mongomock_client` | `tests/conftest.py` | mongomock.MongoClient 实例 |

---

## 15. 风险、降级与回滚

| 风险 | 概率 | 影响 | 应对 | 降级 | 回滚 |
|---|---|---|---|---|---|
| unified_data 接口尚未就绪 | 高 | 高 | Phase 0-1 使用 mock client；Phase 3+ 逐步替换为真实 unified_data | 全 mock 模式跑通 MVP 再集成 | 可随时切回 mock |
| task_center 尚未就绪 | 中 | 中 | 框架提供同步调用入口，批量任务延后至 Phase 3 | 同步调用模式 | 无回滚成本（解耦设计） |
| MongoDB 集合与生产集合冲突 | 低 | 中 | `08_research_stock_*` 前缀隔离 | — | 删除前缀集合即可 |
| 策略模型过拟合 fixture | 中 | 中 | 每个模型 3 个不同方向的 fixture 约束；Phase 6 引入回测交叉验证 | 仅以 fixture 验证通过为准，实际效果待回测 | 调整模型参数 YAML |
| 多模型冲突频繁 | 中 | 低 | CrossValidator 输出冲突解释 + dominant_model 选举；使用户可自行判断 | 以 quality_v1 为锚 | 调整模型权重 |
| 画像构建耗时长（全市场 5000+ 只） | 高 | 中 | 批量并行（max_workers 4+）；Phase 3 后由 task_center 增量调度 | 仅 refresh universe 子集（如 hs300） | 降低 universe 规模 |
| unified_data 数据域缺失 | 中 | 低 | data_gaps 协议：对应维度 null + warnings，不阻断流程 | 对应 ModelScore 降 confidence | 无需回滚 |
| LLM 定性输出污染量化评分 | 低 | 中 | LLM 内容仅写入 strengths/weaknesses/assumptions 字段，不入 score 计算 | 纯量化降级模式（LLM 不可用时跳过） | 关闭 LLM 增强开关 |

---

## 16. Open Questions / Pascal 决策点

| # | 问题 | 当前假设 | 决策窗口 |
|---|---|---|---|
| Q1 | 首批模型参数（权重、阈值）是否需要在 Design 阶段给定，还是实现时由 Pascal 调参？ | Design 给定默认值（见 §8.2），实现时 Pascal 可通过 YAML 调参 | Phase 1 启动前 |
| Q2 | 组合适配 PortfolioFit 需要读取的 portfolio 数据范围？（全部持仓 vs 限定产品） | 默认读取全部 Smart Money 产品（SM001/002/003/004/012）+ 自定义组合 | Phase 4 启动前 |
| Q3 | 全市场画像刷新频率？3600s（1h）是默认值还是需调整？ | Design 默认 3600s，实际频率由 task_center Job schedule 配置，Pascal 可随时调整 | Phase 3 task_center 注册时 |
| Q4 | ReportSnapshot 的 Markdown 内容：存入 MongoDB 集合还是文件系统？ | 默认 JSON block 存入 MongoDB；Markdown 存入文件系统 `data/research/stock/{date}/{code}/` | Phase 1 实现时 |
| Q5 | MVP 阶段是否需要 StockUniverse 的管理 UI？ | 不需要，universe 通过代码/YAML 定义 + CLI 命令注册 | Phase 5 CLI 时 |
| Q6 | 是否需要接入恒生聚源 / Wind 等专业金融数据终端作为额外 unified_data provider？ | 不在此框架范围内；归属 unified_data Phase 3+ | unified_data Phase 3 |
| Q7 | 死亡审计（death_audit）的 7+1 问是否需要 LLM 辅助生成？ | Phase 2 先走规则引擎；Phase 4+ 可选 LLM 增强 | Phase 4 |
| Q8 | 报告的 HTML 风格是否复用 investment_framework 的样式？ | 是，参考 `skills/knowledge/investment_framework/` 的排版风格实现 Jinja2 模板 | Phase 3 |

---

## 17. 验收清单

### 设计阶段验收（本 Design）

- [x] Design 文件存在于 `docs/design/08_research/stock/DESIGN-08-001-stock-quant-analysis-framework.md`。
- [x] 明确 stock framework 持久化使用 MongoDB，新增集合前缀 `08_research_stock_*`。
- [x] 文档不把 SQLite 作为 stock framework 的 MVP/默认/生产存储。
- [x] 明确与 unified_data（§4.1, §6.2.2 维度映射）和 task_center（§4.2, §11）的接口边界。
- [x] 明确后续 Phase 0-7 分阶段实现路线，不直接进入代码实现。
- [x] RFC/SPEC 所有约束在本 Design 中得到继承或显式 Override（§2）。
- [x] 包含 18 个任务要求的设计内容（目标/边界/架构/对象模型/持久化/插件协议/画像维度/交叉验证/风险/路径/组合/报告/任务接口/文件清单/分阶段/测试/风险/Open Questions）。

### 后续 Implement 阶段验收（Phase 1）

1. Phase 0 产物：entities.py + mongo_schema.py + conftest.py 单测通过。
2. ProfileBuilder 给定 fixture 可产出含 5+ 维度组的 StockQuantProfile。
3. growth_v1 + value_v1 对同一画像可独立评分，输出差异化 ModelScore（buy / hold / avoid 各不少于 1 个测试用例）。
4. CrossValidator 2 模型交叉验证逻辑正确。
5. RiskAudit financial_landmine 可检测已知排雷项。
6. ReportRenderer 可生成 Markdown 报告和 JSON block。
7. 端到端同步调用 build_profile → score → cross_validate → audit → render 通过。
8. 所有新增 MongoDB 集合使用 `08_research_stock_*` 前缀。
9. 测试不使用生产库 `tradingagents`，使用 mongomock 或 `yquant_test`。
10. 覆盖率 ≥ 80%。

---

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-07-12 | 初始创建：Stock Quant Analysis Framework 完整详细设计 | YQuant-Codex-Principal |

---

## 附录 A：与友军框架的维度对标

基于 `skills/knowledge/stock_analysis/帝国双系统评分报告_20260612.html`（帝国双系统）和 `skills/knowledge/investment_framework/`（Pascal 个人框架）的维度对比：

| 本框架维度 | 帝国双系统对应 | Pascal 框架对应 | 备注 |
|---|---|---|---|
| 基本面 | 基本面数据（行业地位、管理层） | 01_基本面全景 | — |
| 成长 | 成长股引擎·九维中的增长维度 | 01_基本面全景·增长驱动力 | — |
| 估值 | AH Stock Score V3 估值维度 | 02_逻辑攻防与死亡审计·估值 | — |
| 质量 | 成长股引擎·九维中的质量维度 | 01_基本面全景·财务质量评估 | 含排雷 |
| 技术 | AH Stock Score V3 技术维度 | 04_买卖点与执行框架 | — |
| 资金流 | 九维中的机构跟踪 | — | 含北向/主力 |
| 情绪 | 投资系统综合排名中的情绪项 | — | — |
| 催化剂 | 九维中的预期催化 | 01_基本面全景·催化剂日历 | — |
| 风险 | AH Stock Score V3 风险调整 | 02_逻辑攻防与死亡审计 | 死亡审计 |
| 路径推演 | — | 03_投资决策与路径推演 | 概率树/切换信号 |
| 组合适配 | — | 03_中的仓位管理 | 只读适配 |
