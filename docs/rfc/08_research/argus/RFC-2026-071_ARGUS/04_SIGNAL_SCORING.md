---
file_id: ARGUS-04
title: "设计 — 信号引擎与评分系统 / Signal Engine & Scoring System"
rfc_id: RFC-2026-071
doc_status: DRAFT
approval_status: "NOT_SUBMITTED"
impl_status: "NOT_STARTED"
version: "2.0.0-draft"
created: "2026-04-12"
last_updated: "2026-04-12"
drafter: "Internal Review Board"
owner: "Internal Review Board"
depends_on:
  - "ARGUS-02 (双库架构: argus_raw.db + argus.db, 13张表)"
  - "ARGUS-03 (产品注册与数据摄取管道)"
  - "EXPERT_PANEL_WG1_WG2 (30席专家团决议: REV-007~015)"
  - "EXPERT_PANEL_WG3_WG4_WG5 (信号引擎与API工程评审)"
amendment_level: L2
language: "zh-CN / en"
---

# ARGUS-04: 信号引擎与评分系统

# ARGUS-04: Signal Engine & Scoring System

> **本文件是 RFC-2026-071 ARGUS 百目巨人独立系统 v2.0 的核心分析引擎规格。**
> 覆盖六层数据流架构、产品画像与信誉、T-1 交易行为分析、多时间框架信号引擎、贝叶斯融合评分、共识检测。
> 股票池管理与 Web 界面详见 ARGUS-05; 高级分析层详见 ARGUS-06。

---

## SS1 六层数据流架构 {#ARGUS-04:six-layer}

### 1.1 架构概览 / Architecture Overview {#ARGUS-04:six-layer-overview}

ARGUS 采用六层管道架构，从底层产品建模逐层向上汇聚至风险集成输出。每层有明确的输入/输出契约。V2.0 架构反映独立系统定位 -- ARGUS 自有 FastAPI (:8001) 提供读取服务。

```
┌═══════════════════════════════════════════════════════════════════┐
│                   ARGUS 六层数据流架构 v2.0                       │
│              Six-Layer Data Pipeline (Standalone)                 │
├═══════════════════════════════════════════════════════════════════┤
│                                                                   │
│  Layer 6: 拥挤与风险集成 (Crowding & Risk Integration)            │
│  ├─ 拥挤度数据融合 (外部数据源)                                    │
│  ├─ 四级执行乘数 (SAFE=1.0x / CAUTION=0.8x / DANGER=0.5x        │
│  │   / KILL: emotional 0.2x, institutional 0.35x)                │
│  └─ SENTINEL WD-DYN-001/002 动态看门狗                            │
│  ▲                                                                │
│  │                                                                │
│  Layer 5: 共识与跨市场 (Consensus & Cross-Market)                 │
│  ├─ 多产品对齐 (>=5 products = high conviction)                   │
│  ├─ 风格多样性要求 (REV-015: >=2 style_labels)                    │
│  └─ AH 溢价背离 + 南北向资金                                      │
│  ▲                                                                │
│  │                                                                │
│  Layer 4: 评分与股票池 (Scoring & Pool Management)                │
│  ├─ 贝叶斯融合评分 (替代 V8.1 固定 4D 评分)                       │
│  ├─ composite = w1*rebalancing + w2*product + w3*consensus        │
│  │              + w4*hf_trend                                     │
│  └─ 四区动态池: SCAN -> WATCH -> CANDIDATE -> CONVICTION          │
│  ▲                                                                │
│  │                                                                │
│  Layer 3: 多时间框架信号 (Multi-Timeframe Signal Engine)          │
│  ├─ FAST  (daily):  聪明钱因子 / 主动净买入 / 北向大额             │
│  ├─ MEDIUM(weekly): 融资流 / ETF / 研究关注度                      │
│  └─ SLOW  (weekly/monthly agg): 持仓趋势 / 行业轮动 / HHI        │
│  ▲                                                                │
│  │                                                                │
│  Layer 2: 调仓路径检测 (Rebalancing Path Detector)                │
│  ├─ 事件分类: NEW_ENTRY / CONTINUOUS_ADD / CONCENTRATED_ADD       │
│  │   / CONSENSUS_ADD / PARTIAL_EXIT / FULL_EXIT / HIDDEN_BUILD   │
│  ├─ 隐形重仓识别 (年报全持仓 vs 季报前十)                          │
│  └─ HHI 集中度跟踪                                                │
│  ▲                                                                │
│  │                                                                │
│  Layer 1: 产品画像引擎 (Product Profile Engine)                   │
│  ├─ 质量评估 (五维: alpha / accuracy / behavior / independence    │
│  │   / style consistency)                                        │
│  ├─ 贝叶斯信誉 Beta(alpha, beta) + 自适应衰减 (REV-007)          │
│  └─ T-1 行为分析 (5 维度: 见 SS3)                                  │
│                                                                   │
├───────────────────────────────────────────────────────────────────┤
│  Data Layer (below pipeline):                                     │
│  argus_raw.db (Raw) ──ATTACH──> argus.db (Processed + Decision)  │
│  FastAPI :8001 reads argus.db; Claude writes argus.db             │
└═══════════════════════════════════════════════════════════════════┘
```

### 1.2 层间数据契约 / Inter-Layer Data Contracts {#ARGUS-04:layer-contracts}

| Layer | 输入 Input | 输出 Output | 目标表 Target Table |
|:--:|:--|:--|:--|
| L1 | `raw_daily_snapshot`, `raw_daily_trade`, `raw_nav_history` | 产品画像指标、信誉分 | `proc_product_profile`, `dec_product_credibility` |
| L2 | `proc_holding` (清洗后持仓) | 调仓路径事件 | `proc_rebalancing_event` |
| L3 | L2 事件 + 外部数据 (聪明钱因子、北向、融资) | 多时间框架信号 | `dec_signal` |
| L4 | L1 信誉 + L3 信号 | 贝叶斯后验 + 复合评分 | `dec_stock_pool` |
| L5 | L4 池 + 多产品交叉 | 共识事件 | `dec_consensus` |
| L6 | L5 共识 + 外部拥挤度 | 拥挤调整后最终评分 | `dec_stock_pool.crowding_*` 字段 |

### 1.3 数据源信任分级 / Data Source Trust Tiers (AR-P7) {#ARGUS-04:trust-tiers}

| Tier | 数据类型 | 信任权重 | 来源 |
|:--:|:--|:--:|:--|
| T0 | 季报/年报真实持仓 | 1.00 | 基金公司法定披露 |
| T1 | 日度 T+1 交易记录 + 全持仓快照 | 0.85 | Wind / 数据供应商 |
| T2 | 聪明钱因子 / 北向流 / 融资余额 | 0.70 | 市场行情数据 |

---

## SS2 产品画像与信誉 {#ARGUS-04:product-profile}

### 2.1 产品质量评估框架 / Product Quality Framework {#ARGUS-04:quality-framework}

**V2.0 关键变更**: ARGUS 跟踪"基金产品"(fund product) 而非"基金经理"。产品名称自带 AUM 编码 (如"中欧1号-3.6e" = 36 亿)，日度 T+1。

**五维产品评分框架** (来源: WG2 INV-01 提案 + 全组评议):

| # | 维度 Dimension | 权重 Weight | 评估内容 | 更新频率 |
|:--:|:--|:--:|:--|:--|
| D1 | 选股 Alpha | 30% | 扣除 市场/规模/价值/动量 四因子后残差 alpha (INV-13) | 季度 |
| D2 | 信号准确率 Accuracy | 25% | 贝叶斯 credibility, 分 regime 统计 (INV-11) | 每次信号验证 |
| D3 | 行为质量 Behavior | 20% | T-1 行为分析五维度综合分 (见 SS3) | 月度 |
| D4 | 信号独立性 Independence | 15% | 主动交易与同行相关性 -- 越独立越有价值 (INV-09) | 月度 |
| D5 | 风格一致性 Style Consistency | 10% | 方法论稳定性 (非持仓分布稳定性, INV-03/05 修订) | 季度 |

**综合信誉计算 / Composite Credibility**:

```
credibility = 0.30 * D1_alpha_score
            + 0.25 * D2_accuracy_score
            + 0.20 * D3_behavior_score
            + 0.15 * D4_independence_score
            + 0.10 * D5_style_score

每个维度归一化至 [0, 1]
```

**Fama 统计验证要求 (INV-10)**: 启动第一年用等权 (各 20%)，积累数据后用回归分析确定最优权重。优化目标: 综合信誉与未来 6 个月信号准确率的相关系数。任意两维度相关系数 > 0.7 时需合并或重新定义。

### 2.2 贝叶斯信誉模型 Beta(alpha, beta) {#ARGUS-04:bayesian-credibility}

D2 维度使用 Beta 分布建模产品信号准确率:

```
初始先验: Beta(alpha=2, beta=2) => credibility = 0.50
每次信号正确 (is_correct=1): alpha += 1
每次信号错误 (is_correct=0): beta  += 1

点估计:  credibility = alpha / (alpha + beta)
置信区间: CI_95 = 1.96 * sqrt(alpha*beta / ((alpha+beta)^2 * (alpha+beta+1)))
```

**存储**: `dec_product_credibility` 表 -- `product_id`, `alpha`, `beta`, `credibility`, `ci_95`, `updated_at`

### 2.3 自适应衰减 (REV-007) {#ARGUS-04:adaptive-decay}

长期无新信号验证的产品信誉应向中性回归，防止历史红利永久固化:

```
每 90 天无新验证证据:
  alpha *= DECAY_FACTOR  (默认 0.95)
  beta  *= DECAY_FACTOR  (默认 0.95)
  => credibility 不变，但 CI 扩大 (信心降低)

高波动期 (市场月度波动率 > 2x 历史均值):
  DECAY_FACTOR = 0.90 (加速衰减, INV-11 建议)
```

**Regime-Conditional Accuracy (INV-11/Shiller 建议)**: 分别统计牛市、震荡市、熊市中的准确率。当前 regime 对应的准确率调制 D2 分数，防止牛市中所有多头都"准确"的假象。

### 2.4 信誉冻结机制 (REV-008) {#ARGUS-04:credibility-freeze}

当产品出现以下异常状况时，信誉评分冻结 (不参与信号权重计算):

| 触发条件 | 冻结期 | 恢复条件 |
|:--|:--|:--|
| 产品更换核心投资人员 | 90 天 | 新团队有 >= 10 条验证信号 |
| AUM 急剧变动 (> 50%) | 60 天 | AUM 稳定 2 个月 |
| 数据源中断 > 5 个交易日 | 中断期间 + 10 天 | 数据恢复且通过质量检查 |
| 信誉 CI_95 > 0.20 | 直至 CI 收窄 | CI_95 <= 0.20 |

冻结期间产品标记为 `credibility_frozen = 1`，其信号仍记录但不参与贝叶斯融合评分。

### 2.5 质量门槛 (适配产品) {#ARGUS-04:quality-thresholds}

| 参数 ID | 参数名 | 默认值 | 说明 |
|:--|:--|:--:|:--|
| ARG-001 | `QUALITY_SHARPE_STOCK` | 0.8 | 纯股票型产品 Sharpe 3Y 门槛 |
| ARG-002 | `QUALITY_SHARPE_MIXED` | 0.7 | 混合型产品 Sharpe 3Y 门槛 |
| ARG-003 | `QUALITY_CALMAR_MIN` | 0.5 | Calmar 3Y 最低要求 |
| ARG-004 | `QUALITY_MAX_DRAWDOWN` | -0.35 | 最大回撤上限 |
| ARG-005 | `QUALITY_PASS_REQUIRED` | 3/4 | 至少通过 4 项中的 3 项 |

---

## SS3 T-1 交易行为分析 {#ARGUS-04:t1-behavior}

### 3.1 五维度评估框架 / Five-Dimension Behavior Assessment {#ARGUS-04:t1-five-dimensions}

T-1 行为分析从产品的日度交易记录中提取行为模式，评估其作为情报来源的行为可靠性。

| # | 维度 | 权重 | 评估内容 | REV 修订 |
|:--:|:--|:--:|:--|:--|
| B1 | 卖出质量 Sell Quality | 30% | 止盈/止损比、卖出时机、处置效应指标 | REV-009 |
| B2 | 风格忠诚 Style Fidelity | 25% | 交易模式与声明风格的一致性 | -- |
| B3 | 建仓节奏 Build Rhythm | 20% | 分步建仓 vs 一次性建仓模式 | -- |
| B4 | 市场适应 Market Adaptation | 15% | 不同市场环境下的行为调整能力 | -- |
| B5 | 风控质量 Risk Control | 10% | 止损纪律、集中度控制 | -- |

**行为综合分**: `behavior_score = 0.30*B1 + 0.25*B2 + 0.20*B3 + 0.15*B4 + 0.10*B5`

**存储**: `proc_product_profile.t1_behavior_score` + 五维度明细字段

### 3.2 REV-009 卖出三分类 / Sell Tri-Classification {#ARGUS-04:sell-tri-class}

每笔卖出事件根据盈亏回溯 (REV-031 `pnl_tag`) 分为三类:

| 类别 | 条件 | 信号含义 | B1 加分 |
|:--|:--|:--|:--:|
| PROFIT_TAKE | 卖出价 > 买入均价 | 主动获利了结 | +0.1 |
| STOP_LOSS | 卖出价 < 买入均价 * 0.92 | 止损离场 | +0.05 (有纪律) |
| BREAKEVEN | 其余情况 | 持平出局 | 0 |

**处置效应指标 (INV-12/Kahneman 建议)**: 对每产品计算 `avg_profit_take_pct` / `avg_stop_loss_pct` 比值。比值 < 0.5 (即止盈远小于止损) 表明受处置效应影响严重，B1 权重下调 0.8x。

**卖出速度补充字段 (INV-08 建议)**: `sell_speed` = 清仓耗时天数。单日清仓的 STOP_LOSS 为最强看空信号。

### 3.3 REV-010 权重调整 / Weight Adjustment by Style {#ARGUS-04:weight-adjustment}

不同风格产品的理想行为模式不同，五维度权重按风格调整:

| 风格 | B1 卖出 | B2 风格 | B3 建仓 | B4 适应 | B5 风控 |
|:--|:--:|:--:|:--:|:--:|:--:|
| VALUE | 25% | 30% | 25% | 10% | 10% |
| GROWTH | 30% | 20% | 15% | 25% | 10% |
| BALANCED | 30% | 25% | 20% | 15% | 10% |
| THEMATIC | 25% | 15% | 15% | 30% | 15% |
| CONTRARIAN | 20% | 30% | 20% | 15% | 15% |

### 3.4 买入意图分类 / Buy Intent Classification {#ARGUS-04:buy-intent}

每笔买入事件根据金额占 AUM 比例和连续性分为四类:

| 意图级别 | 条件 | 信号强度 | 视觉样式 |
|:--|:--|:--:|:--|
| **HEAVY** (重仓) | 单笔 > 3% AUM | 1.0 | 整行粗体 |
| **NORMAL** (常规) | 单笔 1%~3% AUM | 0.6 | 正常显示 |
| **PROBE** (试探) | 单笔 < 1% AUM | 0.3 | 透明度 0.6 |
| **SEQUENTIAL** (连续) | 同一标的连续 >= 3 个交易日买入 | 0.9 | 特殊标记 |

**INV-02 价值型建议**: 对价值型产品，SEQUENTIAL 信号比 HEAVY 更可靠 -- 连续买入表明经过深思熟虑的分步建仓。

**INV-03 成长型建议**: 对成长型产品，首次买入新板块的时点比个股 HEAVY 更有价值 -- 板块切换信号优先于个股信号。

---

## SS4 多时间框架信号引擎 {#ARGUS-04:mtf-engine}

### 4.1 三框架概览 / Three-Timeframe Overview {#ARGUS-04:mtf-overview}

| 框架 | 频率 | 信号维度 | 数据源 Tier | 信号过期 |
|:--|:--|:--|:--:|:--|
| **FAST** | 日度 | 聪明钱因子分位、主动净买入、北向大额 | T2 (0.70) | 10 天 |
| **MEDIUM** | 周度 | 融资流、ETF 流、研究关注度 | T2 (0.70) | 30 天 |
| **SLOW** | 周度/月度聚合 | 持仓趋势、行业轮动、HHI、共识演化 | T1 (0.85) | 90 天 |

**可靠性排序**: SLOW > MEDIUM > FAST (长周期信号更可靠，因数据源 Tier 更高)

### 4.2 FAST 框架 (日度) / FAST Frame (Daily) {#ARGUS-04:fast-frame}

| 信号维度 | 计算方法 | 阈值 | REV |
|:--|:--|:--|:--|
| 聪明钱因子分位 | 标的的聪明钱因子在全市场的百分位 | > 80th = BULLISH | -- |
| 主动净买入 | 产品当日主动买入金额 - 主动卖出金额 | > 0 且占 AUM > 0.5% | -- |
| 北向大额 (NHC) | 北向资金单日净买入绝对值 | **REV-012 动态阈值**: 按近 60 日北向总额的 P90 计算，替代固定 1 亿 | REV-012 |

**REV-012 动态阈值详解**: 北向大额信号的触发阈值不再固定为 1 亿元，而是每 60 个交易日重新计算:

```
NHC_THRESHOLD = percentile(abs(northbound_daily_net_buy), 90, window=60)
触发条件: abs(daily_net_buy) > NHC_THRESHOLD
```

### 4.3 MEDIUM 框架 (周度) / MEDIUM Frame (Weekly) {#ARGUS-04:medium-frame}

| 信号维度 | 计算方法 | 信号方向 |
|:--|:--|:--|
| 融资流 | 融资余额 5 日变化 / 自由流通市值 | 正向 = BULLISH |
| ETF 流 | 行业 ETF 份额 5 日变化 | 正向 = BULLISH |
| 研究关注度 | 卖方研究报告 30 日发布数量 | 高于 P75 = 关注上升 |

### 4.4 SLOW 框架 (周度/月度聚合) -- REV-032 {#ARGUS-04:slow-frame}

**REV-032**: SLOW 框架从纯季度更新升级为周度/月度聚合，充分利用日度 T+1 全持仓数据。

| 信号维度 | 计算方法 | 聚合周期 | 信号含义 |
|:--|:--|:--|:--|
| 持仓趋势 | 产品在标的上的持仓权重 30/60 日变化 | 月度 | 持续增持 = BULLISH |
| 行业轮动 | 申万一级行业权重月度变化矩阵 | 月度 | 周期/防御切换 |
| HHI 集中度 | 产品持仓 Herfindahl 指数变化 | 月度 | 集中度上升 = 信念增强 |
| 共识演化 | 多产品在同一标的的权重变化方向一致性 | 周度 | 方向一致 = 共识形成 |

### 4.5 信号存储与生命周期 / Signal Storage & Lifecycle {#ARGUS-04:signal-lifecycle}

**存储**: `dec_signal` 表

**信号状态流转**:

```
ACTIVE ──[用户点击"已知悉"]──> ACKNOWLEDGED
ACTIVE ──[超过过期天数]──> EXPIRED
ACTIVE/ACKNOWLEDGED ──[回测引擎: 方向正确]──> CONFIRMED
ACTIVE/ACKNOWLEDGED ──[回测引擎: 方向错误]──> INVALIDATED
```

---

## SS5 贝叶斯融合 {#ARGUS-04:bayesian-fusion}

### 5.1 似然比模型 / Likelihood Ratio Model {#ARGUS-04:likelihood-ratio}

ARGUS 使用贝叶斯似然比更新替代 V8.1 的固定 4D 评分。对每只标的，维护一个"该标的具有超额收益 (alpha)" 的后验概率。

```
先验: P(stock_has_alpha) = BASE_RATE  (REV-013: 默认 0.10)

每个新信号 s_i 产生似然比 LR_i:
  LR_i = P(observe s_i | alpha) / P(observe s_i | no alpha)

LR_i 的计算依赖于:
  (a) 来源产品信誉: credibility (高信誉产品的信号 LR 更高)
  (b) 信号时间框架: SLOW > MEDIUM > FAST
  (c) 当前拥挤度区域: KILL 区信号 LR 被压制
  (d) 买入意图强度: HEAVY > SEQUENTIAL > NORMAL > PROBE

贝叶斯更新:
  posterior = prior * LR_i / (prior * LR_i + (1 - prior))
```

### 5.2 REV-013 基准率 / BASE_RATE {#ARGUS-04:base-rate}

| 参数 ID | 参数名 | 默认值 | 说明 |
|:--|:--|:--:|:--|
| ARG-006 | `BASE_RATE` | 0.10 | 任意标的具有 alpha 的先验概率 |

**Kahneman 校准建议 (INV-12)**: 每季度用 bootstrap 方法重新估计 BASE_RATE，不固定为 0.10。计算方法: 过去 12 个月所有进入 WATCH+ 区域标的中，最终 CONFIRMED 的比例。

### 5.3 REV-014 后验饱和 / Posterior Saturation {#ARGUS-04:posterior-saturation}

| 参数 ID | 参数名 | 默认值 | 说明 |
|:--|:--|:--:|:--|
| ARG-007 | `POSTERIOR_CAP` | 0.92 | 后验概率上限，防止过度自信 |

```
posterior = min(bayesian_update_result, POSTERIOR_CAP)
```

**Rationale**: 即使最强的信号组合也不应产生 > 0.92 的确信度。保留 8% 的"我们可能错了"空间 (芒格怀疑原则 AR-P4)。

### 5.4 拥挤度压制乘数 / Crowding Suppression Multipliers {#ARGUS-04:crowding-suppression}

当标的处于不同拥挤度区域时，信号的似然比 LR 被乘以对应乘数:

| 拥挤区域 | 乘数 | REV | 说明 |
|:--|:--:|:--|:--|
| SAFE | 1.00 | -- | 无压制 |
| CAUTION | 0.80 | -- | 轻度压制 |
| DANGER | 0.50 | -- | 中度压制 |
| KILL (emotional) | 0.20 | KILL split | 情绪驱动的拥挤 -- 重度压制 |
| KILL (institutional) | 0.35 | KILL split | 机构驱动的拥挤 -- 中重度压制 |

**KILL 拆分逻辑**: KILL 区不再统一使用 0.2x。当拥挤主要由散户/游资驱动 (emotional) 时使用 0.2x; 当拥挤由机构集体配置驱动 (institutional) 时使用 0.35x。判断依据: 机构持仓占比 > 60% 时为 institutional KILL。

### 5.5 复合评分 / Composite Score {#ARGUS-04:composite-score}

最终入池评分综合四个维度:

```
composite_score = ARG-W1 * rebalancing_intensity
                + ARG-W2 * product_quality
                + ARG-W3 * consensus_strength
                + ARG-W4 * hf_trend_alignment

默认权重:
  ARG-W1 = 0.30 (调仓强度)
  ARG-W2 = 0.25 (产品质量)
  ARG-W3 = 0.25 (共识强度)
  ARG-W4 = 0.20 (高频趋势)
```

---

## SS6 共识检测 {#ARGUS-04:consensus}

### 6.1 共识定义 / Consensus Definition {#ARGUS-04:consensus-definition}

当多个独立产品在一定时间窗口内对同一标的表现出方向一致的交易行为时，触发共识事件。

| 共识级别 | 条件 | consensus_strength |
|:--|:--|:--|
| 弱共识 | 2~3 个产品同方向 | 0.20 ~ 0.40 |
| 中共识 | 3~4 个产品同方向 | 0.40 ~ 0.60 |
| 强共识 | >= 4 个产品同方向 | 0.60 ~ 0.80 |
| **高确信** | **>= 5 个产品同方向** | **0.80+** |

### 6.2 REV-015 风格多样性要求 / Style Diversity Requirement {#ARGUS-04:style-diversity}

**问题**: 同一家基金公司的多个产品买入同一标的不构成独立共识 (INV-09 提出)。同风格产品的共识可能是信息级联而非独立判断。

**要求**: 高确信共识 (>= 5 products) 必须满足:
- 至少 2 种不同 `style_label` (如 VALUE + GROWTH)
- 产品来源 >= 2 家不同基金公司
- 建仓时间不完全同步 (不是全部在同一天买入)

```
style_diversity = count(DISTINCT style_label) / count(products)
独立性要求: style_diversity >= 0.40
```

### 6.3 共识反转预警 / Consensus Reversal Warning (INV-11/Shiller) {#ARGUS-04:consensus-reversal}

当共识强度极高且价格已大幅上涨时，系统生成反转预警:

```
IF consensus_strength >= 0.80
   AND stock_return_since_consensus_start > 30%
THEN:
   Generate CAUTION signal (非 BULLISH 加强)
   Alert: "极端共识可能标志趋势末端"
```

### 6.4 共识存储 / Consensus Storage {#ARGUS-04:consensus-storage}

**存储**: `dec_consensus` 表

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| `stock_code` | TEXT | 标的代码 |
| `product_ids` | TEXT (JSON) | 参与产品 ID 列表 |
| `product_count` | INTEGER | 产品数量 |
| `style_count` | INTEGER | 风格类别数 (REV-015) |
| `consensus_type` | TEXT | ACCUMULATE / REDUCE / POSITION_OVERLAP |
| `strength` | REAL | 0~1 |
| `high_conviction` | INTEGER | 1 = >= 5 products 且通过 REV-015 |
| `detection_date` | TEXT | 检测日期 |

---

## 参数注册表摘要 / Parameter Registry Summary {#ARGUS-04:param-summary}

本文件涉及 23 个可调参数 (ARG-001 ~ ARG-019 + ARG-W1~W4)。关键参数:

| ID | 参数名 | 默认值 | 章节 |
|:--|:--|:--:|:--:|
| ARG-001~005 | Quality thresholds (Sharpe/Calmar/Drawdown/Pass) | 0.8/0.7/0.5/-0.35/3of4 | SS2.5 |
| ARG-006 | `BASE_RATE` | 0.10 | SS5.2 |
| ARG-007 | `POSTERIOR_CAP` | 0.92 | SS5.3 |
| ARG-W1~W4 | Composite weights (rebal/product/consensus/hf) | 0.30/0.25/0.25/0.20 | SS5.5 |
| ARG-008~009 | Decay factors (normal/high-vol) | 0.95/0.90 | SS2.3 |
| ARG-010~012 | Signal expiry (FAST/MEDIUM/SLOW) | 10d/30d/90d | SS4.1 |
| ARG-013~014 | Conviction thresholds (products/diversity) | 5/0.40 | SS6 |
| ARG-015~019 | Crowding multipliers (SAFE~KILL) | 1.0/0.8/0.5/0.2/0.35 | SS5.4 |

完整参数定义见 APPENDIX/A_PARAMETER_REGISTRY.md。

---

## 变更日志 / Changelog {#ARGUS-04:changelog}

| 版本 | 日期 | 变更内容 |
|:--|:--|:--|
| 2.0.0-draft | 2026-04-12 | 初始 V2.0 草案。从 V1.0 ARGUS-03 重构为独立系统架构; 采纳 WG1 双库决议 (argus_raw.db + argus.db); 采纳 WG2 五维产品评分框架 (INV-01 提案); 集成 REV-007~015 全部修订; 新增 KILL 拆分 (emotional/institutional); 新增处置效应指标 (INV-12); 新增 regime-conditional accuracy (INV-11); 产品画像替代经理画像 |

---

## 签署与认证 / Attestation {#ARGUS-04:attestation}

| 角色 | 签署人 | 状态 | 日期 |
|:--|:--|:--|:--|
| Drafter | Internal Review Board | DRAFTED | 2026-04-12 |
| Reviewer | -- | PENDING | -- |
| Approver | Internal Review Board | PENDING | -- |

---

*ARGUS-04 v2.0.0-draft -- Signal Engine & Scoring System*
*RFC-2026-071 ARGUS 百目巨人独立系统*
