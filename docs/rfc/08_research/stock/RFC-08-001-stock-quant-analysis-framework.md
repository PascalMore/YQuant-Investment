# RFC-08-001: Stock Quant Analysis Framework

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿 |
| 作者 | YQuant Principal |
| 创建日期 | 2026-07-12 |
| 最后更新 | 2026-07-12 |
| 所属模块 | research/stock |
| 依赖 RFC | 无（规划期引用 `unified_data` RFC-03-007、`task_center` RFC-10-009，两者并行规划中，以路径引用为主，不硬依赖具体内容） |
| 替代 RFC | 无 |
| AI 适配 | Hermes Kanban worker |
| 标签 | #架构 #研究 #量化 #股票 #插件 #数据 |


### Design 阶段修订说明（2026-07-12）

Pascal 明确要求 stock framework 持久化使用 MongoDB，不使用 SQLite 作为 MVP / 默认 / 生产存储。后续 Design 已将新增集合统一命名为 `08_research_stock_*`，并明确：

- stock framework 不直接依赖 SQLite；
- 如 DSA 侧存在 SQLite，那只是外部 legacy source，由 unified_data adapter 消化；
- stock framework 不写 `portfolio_position` / `portfolio_trade` / `signal` / `stock_pool` 等生产决策集合。

## 1. 执行摘要（Executive Summary）

在 YQuant 中建立一套通用的股票量化分析框架（`skills/research/stock/`），以"通用量化画像层 + 策略模型插件层"双层结构，对个股进行多维度、可解释、可验证的量化评估。框架只消费 `unified_data` 提供的标准数据接口，不直接管理底层数据源；批量任务通过 `task_center` 注册与调度。框架定位为"研究与分析辅助"，不产生自动交易决策。成功标准：任意一只股票输入后，系统可在统一协议下产出含基本面、成长、估值、质量、技术、资金流、情绪等多维度的量化画像、多模型交叉验证结果、风险审计和路径推演报告。

## 2. 背景与动机（Background & Motivation）

### 2.1 现状痛点
- YQuant 已有 DSA（daily_stock_analysis）、Argus、TA-CN 等多套分析能力，但分析维度、数据接口、评分协议、风险口径彼此不统一，无法横向比较，也无法插件化扩展。
- 缺少一致的"股票量化画像"事实层：同一只股票在不同子系统里的基本面/成长/估值结论可能矛盾，没有统一的交叉验证机制。
- 投资决策辅助依赖人工拼接数据，缺少可复用的多模型共识 / 冲突识别能力。
- 现有 Argus 偏向 Smart Money 信号→股票池的生命周期管理，DSA 偏向 LLM 单股深度报告，两者都不能直接覆盖"通用量化画像 + 多策略模型评分 + 组合适配"这条主链路。

### 2.2 业务价值
- 将 Pascal 个人投资哲学（长期成长、价值投资、组合分散）沉淀为可执行、可回测、可验证的量化模型集合，而不是每次都从零拼接。
- 统一画像层让不同策略模型在同一份"事实"上打分，结论可横向比较、可解释、可审计。
- 插件化策略模型使新增"成长股""价值股""红利低波"等模型只改配置和模型插件，不动公共层。
- 多模型交叉验证天然暴露"价值陷阱""成长陷阱""高动量但质量弱"等常见投资认知偏差。

### 2.3 触发原因
- 需求驱动：Pascal 要求建立通用股票量化分析框架并支持多套策略模型。
- 架构驱动：`unified_data` 与 `task_center` 正在并行规划，本框架必须明确与它们的依赖边界，避免再次出现子系统各自维护数据源的局面。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）
- [ ] 定义通用量化画像层 `StockQuantProfile`，覆盖基本面、成长、估值、质量、技术、资金流、情绪、催化剂、风险、组合适配、数据质量等维度。
- [ ] 定义策略模型插件层，首批支持 Growth / Value / Quality / Momentum / DividendLowVol / EventDriven 六类模型，并以统一输入输出协议暴露。
- [ ] 定义统一输出协议：`ModelScore`（rating / confidence / strengths / weaknesses / contradictions / assumptions / data_gaps）。
- [ ] 提供多模型交叉验证矩阵，输出共识、冲突和价值/成长/质量陷阱标注。
- [ ] 提供风险审计（财务排雷、死亡审计、认知偏差、二阶效应、信息置信度）。
- [ ] 提供路径推演（周期阶段、预期差、概率树、路径切换信号）。
- [ ] 提供组合适配建议（行业 / 风格 / 相关性 / 集中度 / 边际风险贡献）。
- [ ] 支持 Markdown / HTML / JSON block 三种报告输出。
- [ ] 通过 `task_center` 注册"批量画像刷新""模型评分""报告生成"等任务，通过 `unified_data` 消费标准数据。
- [ ] 明确与 TA-CN / DSA / Argus 的复用边界，避免重复造轮子。

### 3.2 非目标（Out of Scope）
- [ ] 不做自动交易决策、不下买卖单、不直连交易所。
- [ ] 不内建底层数据源采集与清洗（归属 `unified_data`）。
- [ ] 不内建通用任务调度器（归属 `task_center`）。
- [ ] 不替代 Argus 的信号→股票池生命周期管理；Argus 继续负责 Smart Money 信号侧。
- [ ] 不替代 DSA 的 LLM 单股深度报告；DSA 可作为本框架的报告渲染上游或下游消费者。
- [ ] 不在本 RFC/SPEC 阶段产出 Design 级文件清单、类签名、数据结构字节级定义。
- [ ] 不修改生产数据库、cron、gateway、外部推送配置。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学
**事实与解释分离**：通用量化画像层只承载"客观、可校验、可复现"的量化事实（指标值、比率、时间序列、排名、分位数）；策略模型插件层只承载"主观、可调参、可回测"的解释与评分。两层通过统一协议耦合，策略模型可独立替换、增减、回测，而不触碰公共事实层。

### 4.2 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                    YQuant Stock Quant Framework                   │
│                  skills/research/stock/                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │   报告输出层  ReportRenderer                                 │ │
│  │   Markdown / HTML / JSON block                               │ │
│  └────────────▲────────────────────────────────────────────────┘ │
│               │                                                   │
│  ┌────────────┴────────────────────────────────────────────────┐ │
│  │   综合层  Synthesizer                                        │ │
│  │   多模型交叉验证 / 风险审计 / 路径推演 / 组合适配            │ │
│  └────▲───────────────▲───────────────────────────▲────────────┘ │
│       │               │                           │               │
│  ┌────┴────┐   ┌──────┴───────┐          ┌────────┴────────┐     │
│  │ 画像层  │   │ 策略模型层    │          │  task_center    │     │
│  │ Profile │   │ Model Plugins │          │  批量/调度入口  │     │
│  │ (事实)  │   │ (解释/评分)   │          │                 │     │
│  └────▲────┘   └──────▲───────┘          └─────────────────┘     │
│       │               │                                           │
│       └───────┬───────┘                                           │
│               │                                                   │
│  ┌────────────┴────────────────────────────────────────────────┐ │
│  │   unified_data  (标准数据访问层)                              │ │
│  │   行情 / 财务 / 估值 / 资金流 / 新闻 / 日历 / 元数据          │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

数据自下而上：`unified_data` → 画像层（事实） → 策略模型层（评分） → 综合层（交叉验证 + 风险 + 路径 + 组合） → 报告层。
任务编排通过 `task_center` 从侧面驱动"批量画像刷新""模型评分""报告生成"。

### 4.3 模块分工

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| ProfileBuilder | 构建通用量化画像 | unified_data 标准接口 | StockQuantProfile |
| ModelPlugin（×N） | 单策略模型评分 | StockQuantProfile + 模型参数 | ModelScore |
| CrossValidator | 多模型交叉验证 | List[ModelScore] | CrossValidationMatrix |
| RiskAuditor | 风险与死亡审计 | StockQuantProfile + ModelScore | RiskAudit |
| PathProjector | 路径推演 | StockQuantProfile + CrossValidationMatrix | PathProjection |
| PortfolioFit | 组合适配 | PathProjection + 组合上下文 | PortfolioFitAdvice |
| ReportRenderer | 报告渲染 | 全部上游产物 | Markdown/HTML/JSON |
| TaskCenterAdapter | 任务注册与调度 | task_center 注册协议 | 执行结果回传 |

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

**单股分析主流程**

1. 触发条件：用户请求、批量任务、定时刷新、外部信号触发。
2. ProfileBuilder 从 `unified_data` 拉取标准数据，构建 `StockQuantProfile`（事实层）。
3. 启用的策略模型插件并行读取画像，各自输出 `ModelScore`。
4. CrossValidator 汇总所有 ModelScore，产出共识 / 冲突 / 陷阱标注矩阵。
5. RiskAuditor 在画像 + 评分基础上做财务排雷、死亡审计、认知偏差、二阶效应、信息置信度审计。
6. PathProjector 做周期阶段判定、预期差分析、概率树推演、路径切换信号识别。
7. PortfolioFit 结合组合上下文给出行业 / 风格 / 相关性 / 集中度 / 边际风险贡献建议。
8. ReportRenderer 渲染 Markdown / HTML / JSON block。

**异常降级分支**
- `unified_data` 某数据域缺失：画像层对应维度标记 `data_gaps`，模型层该维度不参与评分或降权，不阻断整体流程。
- 某策略模型插件异常：跳过该模型，在 CrossValidator 中标注 `model_skipped`，其他模型继续。
- 全部模型异常：返回仅含画像 + 数据质量告警的降级报告。
- `task_center` 不可用：框架仍可被同步调用，批量能力暂时不可用。

### 5.2 数据模型（Data Model）

核心实体（语义级，字段级定义归 Design 阶段）：

| 实体 | 说明 | 关键字段（语义） |
|---|---|---|
| StockQuantProfile | 通用量化画像（事实层） | security_id / as_of / 基本面 / 成长 / 估值 / 质量 / 技术 / 资金流 / 情绪 / 催化剂 / 风险 / 组合适配 / 数据质量 |
| ModelScore | 单模型评分（解释层） | model_id / rating / confidence / score / strengths / weaknesses / contradictions / assumptions / data_gaps |
| CrossValidationMatrix | 多模型交叉验证 | consensus / conflicts / value_trap / growth_trap / momentum_quality_mismatch |
| RiskAudit | 风险审计 | financial_landmine / death_audit / cognitive_bias / second_order_effect / info_confidence |
| PathProjection | 路径推演 | cycle_stage / expectation_gap / probability_tree / path_switch_signals |
| PortfolioFitAdvice | 组合适配 | industry / style / correlation / concentration / marginal_risk_contribution |
| ReportBundle | 报告输出 | markdown / html / json_block / metadata |

### 5.2bis 持久化策略（Persistence Strategy）

| 数据类别 | 存储介质 | 命名规则 | 生命周期 | 隐私级别 |
|---|---|---|---|---|
| StockQuantProfile 产物 | MongoDB（由 unified_data / reports 模块管理）或文件缓存 | 库 `yquant_research`，集合 `stock_quant_profile` | 按交易日快照，保留 N 天滚动 | L1（公开行情+公开财务） |
| ModelScore 历史 | MongoDB | 集合 `stock_model_score` | 按交易日快照 | L1 |
| 报告产物 | 文件系统 + 可选 MongoDB | `data/research/stock/{date}/{code}/` | 滚动保留 | L1 |
| 任务执行记录 | 由 task_center 管理 | task_center 规范 | task_center 规范 | L1 |

边界：本框架不自行管理数据源凭据、不写入交易集合（portfolio_position / portfolio_trade 等），不修改 Argus / signal / stock_pool 集合。如需写入研究类集合，走独立集合命名，不与生产交易集合混用。

### 5.3 接口契约（API Contract）

语义级接口（参数与返回结构归 Design 阶段细化）：

| 接口 | 输入 | 输出 |
|---|---|---|
| build_profile(security_id, as_of) | 股票标识 + 日期 | StockQuantProfile |
| score(model_id, profile, params) | 模型 id + 画像 + 参数 | ModelScore |
| cross_validate(scores) | 多模型评分列表 | CrossValidationMatrix |
| audit_risk(profile, scores) | 画像 + 评分 | RiskAudit |
| project_path(profile, matrix) | 画像 + 交叉验证 | PathProjection |
| fit_portfolio(projection, portfolio_ctx) | 路径推演 + 组合上下文 | PortfolioFitAdvice |
| render_report(bundle, fmt) | 全部产物 + 格式 | ReportBundle |
| register_task_center() | 无 | 注册批量任务类型 |

错误码（语义级）：
- DATA_GAP：某数据域缺失，降级处理。
- MODEL_ERROR：某模型异常，跳过。
- PROFILE_FAIL：画像构建失败（如 security_id 无法解析）。
- RENDER_FAIL：渲染失败。

### 5.4 AI 模型设计（如有）
- 策略模型插件可调用 LLM 做定性解释（如"催化剂解读""管理层信号解读"），但评分核心仍以量化指标为主。
- LLM 调用通过项目既有 provider 配置，不在本框架内硬编码模型名。
- 所有 LLM 产出必须可回溯到输入画像与 prompt 版本。

## 6. AI 实装规范（AI Implementation Rules）

### 6.1 必须执行
- 模型插件按统一协议实现，单文件单模型，命名语义化。
- 所有评分必须可追溯到输入指标和参数版本。
- 核心评分逻辑补充单元测试。

### 6.2 先询问再执行
- 新增策略模型、修改统一输出协议、变更与 unified_data / task_center 的接口边界。

### 6.3 绝对禁止
- 硬编码数据源凭据、模型名、端口。
- 在本框架内直接写入生产交易集合。
- 把 LLM 定性输出伪装成量化评分。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| unified_data 接口尚未稳定，画像层频繁返工 | 高 | 高 | 本框架只依赖语义级接口，字段级绑定推迟到 Design | 数据域缺失时降级为 data_gaps |
| 策略模型过拟合历史数据 | 中 | 高 | 强制样本内/外回测、参数敏感性分析、过拟合检测 | 标注过拟合风险并降权 |
| 多模型冲突频繁导致结论不可用 | 中 | 中 | CrossValidator 提供冲突解释与主模型选举规则 | 以质量/估值模型为锚 |
| 与 Argus / DSA 职责重叠 | 中 | 中 | 明确边界：Argus 管信号池，DSA 管 LLM 深度报告，本框架管通用画像+多模型评分 | 通过 adapter 复用而非复制 |
| LLM 定性输出污染量化评分 | 中 | 中 | 定性输出与量化评分隔离，定性只进 strengths/weaknesses | 纯量化降级模式 |
| task_center 未就绪导致批量能力缺失 | 中 | 低 | 同步调用仍可用 | 批量任务延后 |

## 8. 备选方案（Alternatives Considered）

1. 把画像和模型评分合并到一个"超级模型"中。否决原因：违反事实/解释分离，无法独立回测和替换模型。
2. 直接复用 Argus 的 bayesian_scoring 作为唯一评分引擎。否决原因：Argus 评分面向 Smart Money 信号池生命周期，不覆盖基本面/成长/估值/质量等个股量化维度。
3. 把框架放在 DSA 内部作为子模块。否决原因：DSA 偏 LLM 单股深度报告，框架需要通用化、插件化、多市场，耦合过紧。
4. 不建独立框架，直接在 portfolio/risk 模块里做。否决原因：组合与风控是下游消费者，把研究逻辑塞进去会造成职责混乱。

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收
- RFC 与 SPEC 文件存在，路径分别在 `docs/rfc/08_research/stock/` 与 `docs/spec/08_research/stock/`。
- RFC 明确业务价值、目标/非目标、架构边界、投资决策边界和风险。
- SPEC 明确可执行、可测试的工程契约，但不进入 Design 级文件清单。
- 明确通用量化画像层与策略模型插件层的职责、关系与业务使用方式。
- 明确 `stock` 框架依赖 `unified_data` 与 `task_center`，但不内建底层数据源/任务中心。
- 中文输出，专业简洁。

### 9.2 非功能验收
- 架构边界清晰，与 unified_data / task_center / Argus / DSA / TA-CN 无职责重叠。
- 后续 Design 可基于本 RFC/SPEC 独立展开。

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

| 阶段 | 范围 | 前置 |
|---|---|---|
| Phase 0（本 RFC/SPEC） | 业务边界 + 工程契约 | 无 |
| Phase 1 Design | 数据结构、文件清单、接口签名、模型插件协议 | unified_data / task_center RFC/SPEC 就绪或路径引用确认 |
| Phase 2 MVP Implement | ProfileBuilder + 1~2 个首批模型 + CrossValidator + Markdown 报告 | Phase 1 Design 确认 |
| Phase 3 扩展 | 补齐 6 类模型 + RiskAudit + PathProjector + PortfolioFit + HTML/JSON 报告 | Phase 2 验证通过 |
| Phase 4 集成 | task_center 注册、unified_data 联调、与 Argus/DSA 边界 adapter | Phase 3 验证通过 |

### 10.2 任务清单
后续按阶段单独建 Kanban 任务，不在本 RFC/SPEC 内展开。

## 11. 开放问题（Open Questions）

1. `unified_data` 和 `task_center` 的 RFC/SPEC 尚在并行规划中，本框架的接口字段级绑定需等其 Design 阶段后再固化；当前以语义级引用为主。
2. 首批六类策略模型的默认参数集（权重、阈值）需要 Pascal 在 Design 阶段确认或提供历史回测基准。
3. 组合适配需要的"组合上下文"是实时读取 portfolio 模块还是快照传入，待 Design 阶段确认。
4. 是否需要支持多市场（A/H/美股）统一 security_id 映射，取决于 unified_data 的 SecurityId 设计。

## 12. 参考资料（References）

- 项目规则：`AGENTS.md`、`CLAUDE.md`、`MEMORY.md`、`TOOLS.md`
- Pipeline skill：`skills/infra/ai-coding-pipeline/SKILL.md`
- 投资框架模板：`skills/knowledge/investment_framework/01~04_*.html`
- 友军评分框架：`skills/knowledge/stock_analysis/帝国双系统评分报告_20260612.html`
- DSA 能力：`skills/research/daily_stock_analysis/SKILL.md` 及 `src/services/`、`src/core/backtest_engine.py`
- TA-CN 架构：`skills/apps/TradingAgents-CN/docs/design/stock_analysis_system_design.md`
- Argus 能力：`skills/research/argus/core/signal_generator.py`、`zone_rule_engine.py`、`bayesian_scoring.py`
- 关联并行 RFC：`docs/rfc/03_data/`（unified_data）、`docs/rfc/10_infra/`（task_center）

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-07-12 | 初始创建：Stock Quant Analysis Framework RFC | YQuant Principal |
