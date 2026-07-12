# SPEC-08-001: Stock Quant Analysis Framework

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿 |
| 作者 | YQuant Principal |
| 创建日期 | 2026-07-12 |
| 最后更新 | 2026-07-12 |
| 所属模块 | research/stock |
| 对应 RFC | RFC-08-001-stock-quant-analysis-framework |
| 依赖 SPEC | SPEC-03-007-unified-data-layer（并行规划中）、SPEC-10-009-task-center（并行规划中） |
| 标签 | #研究 #量化 #股票 #插件 #契约 |

## 1. 目标与范围

本 SPEC 把 RFC-08-001 的架构边界落地为可执行、可测试的工程契约，覆盖：

1. 通用量化画像层 `StockQuantProfile` 的维度清单与数据来源约束。
2. 策略模型插件层的统一输入输出协议 `ModelScore`。
3. 首批六类策略模型的职责定义与评分要点。
4. 多模型交叉验证矩阵 `CrossValidationMatrix` 的字段语义。
5. 风险审计 `RiskAudit`、路径推演 `PathProjection`、组合适配 `PortfolioFitAdvice` 的字段语义。
6. 报告输出 `ReportBundle` 的格式契约。
7. 与 `unified_data` / `task_center` / Argus / DSA / TA-CN 的边界与交互契约。
8. MVP 范围、验收标准、测试要求与后续 Design 拆分建议。

本 SPEC 不给出 Design 级文件清单、类签名、数据结构字节级定义、目录内每个文件的内容。这些归 Design 阶段。

## 2. 目录与模块边界

| 路径 | 职责 | 本 SPEC 是否细化 |
|---|---|---|
| `skills/research/stock/` | 本框架工程目录 | 是（模块级） |
| `skills/data/unified_data/` | 标准数据访问层（外部依赖） | 否，归属 SPEC-03-007 |
| `skills/infra/task_center/` | 任务注册与调度（外部依赖） | 否，归属 SPEC-10-009 |
| `skills/research/daily_stock_analysis/` | DSA LLM 深度报告（可复用上游/下游） | 否，只定义边界 |
| `skills/research/argus/` | Smart Money 信号→股票池（边界邻居） | 否，只定义边界 |
| `skills/apps/TradingAgents-CN/` | 多智能体分析（参考，不复用代码） | 否 |

## 3. 通用量化画像层 StockQuantProfile

### 3.1 维度清单

画像层按"维度组 → 指标项"两级组织。每个指标项必须可从 `unified_data` 获取或由框架内公式计算，不允许直接调用底层数据源。

| 维度组 | 指标项（语义，非穷举） | 数据来源（unified_data 域） |
|---|---|---|
| 基本面 | 行业 / 市值 / 公司画像 / 商业模式 / 护城河标签 / 管理层标签 | 元数据 + 财务 |
| 成长 | 营收增速 / 净利润增速 / EPS 增速 / 毛利率趋势 / ROE 趋势 / 分业务增速 / 一致预期增速 | 财务 + 估值 |
| 估值 | PE / PB / PS / EV/EBITDA / DCF / 相对估值 / 历史分位 / 一致预期 PE | 估值 + 行情 |
| 质量 | ROE / ROIC / 毛利率 / 净利率 / 资产负债率 / 现金流匹配度 / 应收账款异常 / 存货异常 / 商誉占比 | 财务 |
| 技术 | 趋势状态 / 价格位置 / 均线排列 / 量能分析 / 筹码结构 / 支撑阻力 / 动量 | 行情 |
| 资金流 | 主力净流入 / 北向 / 融资融券 / 大单 / Smart Money 持仓变化（来自 Argus 边界） | 资金流 + Argus 边界 |
| 情绪 | 新闻情绪 / 社交热度 / 分析师评级 / 一致预期 / 换手率 | 新闻 + 估值 |
| 催化剂 | 近期事件 / 业绩催化 / 政策催化 / 行业催化 / 管理层信号 | 新闻 + 日历 |
| 风险 | 财务排雷指标 / 估值泡沫 / 波动率 / Beta / 流动性 | 财务 + 行情 |
| 组合适配 | 行业归属 / 风格归属 / Beta / 相关性 / 集中度贡献 | 行情 + 元数据 |
| 数据质量 | 缺失率 / 异常值比例 / 时效性 / 来源置信度 | unified_data quality metadata |

### 3.2 画像层契约约束

- 所有指标必须带 `as_of` 截面日期与 `data_source` 标注。
- 任一指标缺失时填写 `null` 并在 `data_quality` 维度记录，不允许编造。
- 指标计算必须可复现：同 `security_id` + `as_of` + `unified_data` 版本下结果一致。
- 画像层不做主观评分，只产出事实值与分位数、排名等客观衍生量。

### 3.3 画像层与 unified_data 的边界

- 画像层只调用 `unified_data` 的语义级数据域接口（行情 / 财务 / 估值 / 资金流 / 新闻 / 日历 / 元数据）。
- 不在画像层内直连 Tushare / AKShare / BaoStock / Finnhub / Yahoo 等数据源。
- `unified_data` 某域不可用时，画像层对应维度整体标记 `data_gaps`，不阻断其他维度。

## 4. 策略模型插件层

### 4.1 统一输入输出协议 ModelScore

每个策略模型插件必须实现统一协议，输入 `StockQuantProfile + 模型参数`，输出 `ModelScore`。

ModelScore 字段（语义级）：

| 字段 | 类型 | 说明 |
|---|---|---|
| model_id | string | 模型唯一标识，如 `growth_v1`、`value_v1` |
| security_id | string | 被评分标的 |
| as_of | date | 评分截面 |
| score | float | 量化综合得分，0~1 或 0~100，由模型自定标尺 |
| rating | enum | 评级：strong_buy / buy / hold / reduce / avoid / na |
| confidence | float | 置信度 0~1，反映数据完整度与模型自评 |
| strengths | list[string] | 优势点，可含 LLM 定性解读 |
| weaknesses | list[string] | 弱点 |
| contradictions | list[string] | 自相矛盾处（如高增长但现金流恶化） |
| assumptions | list[string] | 关键假设 |
| data_gaps | list[string] | 数据缺口 |
| model_version | string | 模型版本，用于可追溯 |
| detail | dict | 模型私有明细（子维度分、中间量），供 CrossValidator 和报告使用 |

### 4.2 首批策略模型定义

| 模型 | model_id | 核心评分维度 | 典型输出特征 |
|---|---|---|---|
| 成长股 | growth_v1 | 成长 + 质量 + 估值（辅助） + 催化剂 | 高成长 + 高 ROE + 合理估值 → buy |
| 价值股 | value_v1 | 估值 + 质量 + 基本面 | 低 PE/PB + 健康 ROIC + 安全边际 → buy |
| 质量 | quality_v1 | 质量 + 成长（稳定性） + 估值（辅助） | 高 ROIC + 稳定毛利率 + 现金流匹配 → buy |
| 动量 | momentum_v1 | 技术 + 资金流 + 情绪 | 趋势向上 + 量能配合 + 资金流入 → buy |
| 红利低波 | dividend_lowvol_v1 | 质量（分红持续性） + 技术（低波动） + 估值 | 稳定分红 + 低波动 + 合理估值 → buy |
| 事件驱动 | event_driven_v1 | 催化剂 + 情绪 + 估值（安全边际） | 明确催化剂 + 预期差 + 估值未透支 → buy |

### 4.3 插件实现契约

- 每个模型一个独立模块，文件命名 `models/{model_id}.py`（具体路径归 Design）。
- 模型参数通过配置注入，不在代码中硬编码阈值。
- 模型不得直接访问 `unified_data`，只消费 `StockQuantProfile`。
- 模型异常必须被框架捕获并降级为 `model_skipped`，不得崩溃整个流程。
- 模型必须可独立回测：给定历史画像序列，输出历史 ModelScore 序列。

## 5. 多模型交叉验证 CrossValidationMatrix

CrossValidator 消费 `List[ModelScore]`，输出 `CrossValidationMatrix`。

字段（语义级）：

| 字段 | 说明 |
|---|---|
| consensus | 多模型共识方向（bullish / neutral / bearish）与共识强度 |
| conflicts | 冲突列表，每条含冲突模型对、冲突维度、冲突描述 |
| value_trap | 是否疑似价值陷阱（低估值但质量恶化 / 成长崩塌） |
| growth_trap | 是否疑似成长陷阱（高成长但现金流不支撑 / 估值透支） |
| momentum_quality_mismatch | 动量强但质量弱标注 |
| dominant_model | 主导模型建议（按置信度 + 模型权重选举） |
| narrative | 面向用户的综合解释文本 |

## 6. 风险审计 RiskAudit

RiskAuditor 在画像 + 评分基础上产出：

| 字段 | 说明 |
|---|---|
| financial_landmine | 财务排雷清单：应收异常 / 存货异常 / 商誉 / 关联交易 / 审计意见 / 现金流恶化 |
| death_audit | 死亡审计：业务模式失效 / 护城河崩塌 / 管理层诚信 / 监管 / 竞争格局恶化 |
| cognitive_bias | 认知偏差标注：锚定 / 确认偏误 / 近因效应 / 羊群效应 |
| second_order_effect | 二阶效应：供应链传导 / 汇率 / 利率 / 政策连锁 |
| info_confidence | 信息置信度：数据源覆盖 / 时效 / 一致性 / 是否依赖单一来源 |

## 7. 路径推演 PathProjection

| 字段 | 说明 |
|---|---|
| cycle_stage | 周期阶段判定（复苏 / 扩张 / 滞胀 / 衰退，或行业定制阶段） |
| expectation_gap | 预期差分析（一致预期 vs 框架判断） |
| probability_tree | 概率树：乐观 / 基准 / 悲观情景及概率、关键变量 |
| path_switch_signals | 路径切换信号：哪些指标变化会改变结论 |

## 8. 组合适配 PortfolioFitAdvice

| 字段 | 说明 |
|---|---|
| industry | 行业归属与集中度影响 |
| style | 风格归属（成长 / 价值 / 质量 / 动量 / 防御） |
| correlation | 与现有持仓的相关性 |
| concentration | 加仓后集中度变化 |
| marginal_risk_contribution | 边际风险贡献 |

PortfolioFit 只读组合上下文，不修改 portfolio 模块数据。

## 9. 报告输出 ReportBundle

| 字段 | 说明 |
|---|---|
| markdown | Markdown 全文 |
| html | HTML 全文（可复用 investment_framework 模板风格） |
| json_block | 结构化 JSON，含画像 + 全部 ModelScore + CrossValidationMatrix + RiskAudit + PathProjection + PortfolioFitAdvice |
| metadata | 生成时间、框架版本、模型版本、数据源版本、data_gaps 汇总 |

报告必须标注"研究辅助，非交易决策"。

## 10. 与外部模块的边界与交互契约

### 10.1 与 unified_data
- 只消费语义级数据域接口，不直连数据源。
- 消费 `unified_data` 的 quality / freshness / audit metadata，用于画像层数据质量维度。

### 10.2 与 task_center
- 通过 `task_center` 注册三类任务：`profile_refresh`（批量画像刷新）、`model_score`（模型评分批处理）、`report_generate`（报告生成）。
- 框架提供同步调用入口；`task_center` 不可用时批量能力降级，单股分析不受影响。
- 不在框架内重复实现调度、队列、重试、状态机。

### 10.3 与 Argus
- 边界：Argus 管 Smart Money 信号→股票池生命周期；本框架管个股通用量化画像 + 多模型评分。
- 交互：画像层"资金流"维度可消费 Argus 产出的信号 / 持仓变化（只读），但不介入 Argus 的 zone 状态机。

### 10.4 与 DSA（daily_stock_analysis）
- 边界：DSA 偏 LLM 单股深度报告；本框架偏结构化量化画像 + 多模型评分。
- 交互：DSA 可作为本框架报告渲染的下游（消费 ReportBundle.json_block 生成深度报告），或作为上游（DSA 产出的定性解读作为画像层催化剂维度的输入）。
- 不修改 DSA 现有代码。

### 10.5 与 TA-CN
- 只作为架构参考，不复用代码。
- 多智能体辩论模式可在后续版本作为 CrossValidator 的可选策略，不在 MVP 范围。

## 11. MVP 范围

MVP 必须包含：

1. ProfileBuilder 基本面 + 估值 + 质量 + 技术 四个维度组（其余维度 data_gaps 降级）。
2. growth_v1 + value_v1 两个首批模型。
3. CrossValidator 基础版（consensus + conflicts + value_trap + growth_trap）。
4. RiskAudit 基础版（financial_landmine + info_confidence）。
5. Markdown 报告输出。
6. 同步调用入口（不依赖 task_center）。

MVP 不包含：PathProjection、PortfolioFit、HTML/JSON 报告、事件驱动模型、task_center 集成、与 Argus/DSA adapter。

## 12. 测试与验收要求

### 12.1 画像层测试
- 给定 fixture 数据，ProfileBuilder 输出确定性画像。
- 某数据域缺失时，对应维度 null + data_gaps 记录正确。
- 同输入重复调用结果一致。

### 12.2 模型插件测试
- 每个模型独立测试：给定画像 fixture，输出 ModelScore 字段齐全。
- 模型异常被捕获，不崩溃主流程。
- 模型可独立回测（历史画像序列 → 历史 ModelScore 序列）。

### 12.3 交叉验证测试
- 多模型一致时 consensus 正确。
- 多模型冲突时 conflicts 列表正确。
- value_trap / growth_trap / momentum_quality_mismatch 标注正确。

### 12.4 风险审计测试
- fixture 含已知财务雷点时，financial_landmine 命中。
- info_confidence 随数据缺失率下降。

### 12.5 报告输出测试
- Markdown / HTML / JSON block 三种格式可生成。
- 报告含"研究辅助，非交易决策"标注。
- metadata 含框架版本、模型版本、数据源版本。

### 12.6 边界测试
- unified_data 不可用时降级路径正确。
- task_center 不可用时同步调用仍可用。
- Argus / DSA 边界不被越过（不写入对方集合，不修改对方代码）。

## 13. 约束与禁止事项

### 13.1 Design 阶段补充约束（MongoDB-only）

- stock framework 新增持久化必须使用 MongoDB。
- 新增集合统一使用 `08_research_stock_*` 前缀，避免与 `03_data_ud_*`、`10_infra_tc_*`、TA-CN 无前缀集合冲突。
- 禁止使用 SQLite 作为 MVP / 默认 / 生产存储。
- SQLite 只可作为外部 legacy source 事实存在，例如 DSA 既有 SQLite；stock framework 不直接读取/写入 SQLite，相关兼容由 unified_data 消化。
- 禁止写入 `portfolio_position` / `portfolio_trade` / `signal` / `stock_pool` 等生产决策集合。

- 不在框架内直接管理底层数据源。
- 不在框架内重建调度器 / 队列 / 状态机。
- 不修改 unified_data / task_center / Argus / DSA / TA-CN 现有代码。
- 不写入生产交易集合（portfolio_position / portfolio_trade / signal / stock_pool 等）。
- 不给出实盘交易决策。
- 不硬编码数据源凭据、模型名、端口。
- 不把 LLM 定性输出伪装成量化评分。

## 14. 后续 Design 拆分建议

建议 Design 阶段拆为以下子设计：

1. StockQuantProfile 数据结构设计（字段级 schema + 计算公式 + 分位数算法）。
2. 策略模型插件协议设计（基类接口 + 参数注入 + 版本管理 + 回测接口）。
3. CrossValidator 设计（冲突检测规则 + 主导模型选举 + 陷阱识别逻辑）。
4. RiskAudit / PathProjection / PortfolioFit 设计。
5. ReportBundle 模板设计（Markdown / HTML / JSON block schema）。
6. task_center 集成设计（任务注册协议 + 批量执行 + 结果回传）。
7. 与 Argus / DSA 边界 adapter 设计。

Design 阶段必须等待 unified_data / task_center 的 Design 产出后再固化字段级绑定，当前以语义级引用为主。

## 15. 验收标准（对应任务卡）

- RFC/SPEC 文件存在，路径分别在 `docs/rfc/08_research/stock/` 与 `docs/spec/08_research/stock/`。
- 明确通用量化画像层与策略模型插件层的职责、关系与业务使用方式。
- 明确 `stock` 框架依赖 `unified_data` 与 `task_center`，但不内建底层数据源/任务中心。
- SPEC 不进入 Design 级文件清单。
- 中文输出，专业简洁。

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-07-12 | 初始创建：Stock Quant Analysis Framework SPEC | YQuant Principal |
