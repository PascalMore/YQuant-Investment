---
file_id: ARGUS-APP-A
title: "参数注册表 (Standalone MVP Edition)"
title_en: "Parameter Registry (Standalone MVP Edition)"
rfc_id: RFC-2026-071
doc_status: DRAFT
approval_status: NOT_SUBMITTED
impl_status: NOT_STARTED
version: "2.0.0-draft"
created: "2026-04-12"
last_updated: "2026-04-12"
drafter: "Internal Review Board"
owner: "Internal Review Board"
depends_on:
  - "ARGUS-05 (信号引擎与评分 v2.0)"
  - "ARGUS-06 (池管理与Web界面 v2.0)"
  - "EXPERT_PANEL_WG3_WG4_WG5.md (芒格: 68参数->20~25 MVP)"
  - "ADVANCED_FEATURES_DISCUSSION.md (达尔文+共识方向参数)"
supersedes: "ARGUS-APP-A v0.1.0 (archived as A_PARAMETER_REGISTRY.md, 68 params)"
amendment_level: L2
---

# 附录A: 参数注册表 (Standalone MVP Edition) {#ARGUS-APP-A:root}

# Appendix A: Parameter Registry (Standalone MVP Edition)

> **V2.0 核心变更**: V1.0注册表含68个参数 (含三叉戟Round 2/3扩展)。V2.0遵循芒格简化原则和WG3 MVP定义, 精简至约50个参数。移除的参数: HF估算 (ARG-049~051), DuckDB配置 (ARG-055~057), 数据源分层 (ARG-052~054), 北向资金 (ARG-059~061), NHC Regime (ARG-062), 融资余额拥挤度 (ARG-063), AH共线性 (ARG-066)。新增: 达尔文时刻 (ARG-046~049) 和共识方向 (ARG-050~053) 参数。
>
> **V2.0 Key Change**: Reduced from 68 to ~50 params. Removed HF estimation, DuckDB config, data source tiering, northbound, NHC regime, margin crowding, AH collinearity. Added Darwin moment and consensus direction params.

**修改级别定义 / Amendment Level Definitions**:

- **L1**: 用户可自行调整, 无需审批 / User-adjustable, no approval needed
- **L2**: 需IC审批后修改 / Requires IC approval
- **L3**: 需专家组审批后修改 / Requires expert panel approval

**配置位置 / Config Location**: `argus/config.yaml` 的 `parameters:` 命名空间

---

## S1 产品质量阈值 (Product Quality Thresholds) {#ARGUS-APP-A:quality}

产品 (基金) 进入ARGUS跟踪范围的最低质量要求。基于产品的3年业绩指标。

Minimum quality requirements for products (funds) to enter ARGUS tracking universe.

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-001 | QUALITY_SHARPE_STOCK | 0.8 | L2 | 1.0 | 纯股票型产品入选Sharpe门槛(3年) / Stock fund min Sharpe (3Y) |
| ARG-002 | QUALITY_SHARPE_MIXED | 0.7 | L2 | 1.0 | 偏股混合型产品入选Sharpe门槛(3年) / Mixed fund min Sharpe (3Y) |
| ARG-003 | QUALITY_CALMAR_MIN | 0.5 | L2 | 1.0 | 最低Calmar比率(3年) / Min Calmar ratio (3Y) |
| ARG-004 | QUALITY_MAX_DRAWDOWN | -0.30 | L2 | 1.0 | 最大回撤阈值(3年, 超此不合格) / Max drawdown threshold (3Y) |
| ARG-005 | QUALITY_AUM_TIER_S | 100.0 | L1 | 1.0 | S级(超大型)AUM下限(亿元) / S-tier AUM floor (100M CNY) |
| ARG-006 | QUALITY_AUM_TIER_A | 50.0 | L1 | 1.0 | A级(大型)AUM下限; B=[10,50), C=[1,10), U=未知 |

---

## S2 贝叶斯评分 (Bayesian Scoring) {#ARGUS-APP-A:bayesian}

Beta分布参数和信誉更新机制。核心引擎参数, 修改需谨慎。

Beta distribution parameters and credibility update mechanism.

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-007 | CREDIBILITY_ALPHA_INIT | 2.0 | L3 | 1.0 | Beta分布初始alpha; Beta(2,2) -> credibility=0.5 |
| ARG-008 | CREDIBILITY_BETA_INIT | 2.0 | L3 | 1.0 | Beta分布初始beta |
| ARG-009 | CREDIBILITY_DECAY_BASE | 0.97 | L2 | 1.0 | 自适应衰减基础值; 低波动期使用此值 (REV-007) |
| ARG-010 | CREDIBILITY_DECAY_VOL_COEFF | 0.07 | L2 | 1.0 | 衰减波动率系数; decay=base-coeff*min(vol/threshold,1) (REV-007) |
| ARG-011 | BASE_RATE_ALPHA | 0.10 | L3 | 1.0 | 先验基准率P(stock is alpha); REV-013从0.15下调至0.10 |
| ARG-012 | POSTERIOR_SATURATION_THRESHOLD | 0.92 | L2 | 1.0 | 后验饱和阈值; >0.92新信号LR递减 (REV-014) |
| ARG-013 | CREDIBILITY_DECAY_DAYS | 90 | L2 | 1.0 | 无新证据触发衰减的天数 |
| ARG-014 | CREDIBILITY_FREEZE_REDEMPTION_PCT | 0.30 | L2 | 1.0 | 信誉冻结触发: 申赎率>30%冻结更新 (REV-008) |

---

## S3 复合评分权重 (Composite Scoring Weights) {#ARGUS-APP-A:weights}

composite_score的四维权重。V2.0保留V1.0的W1~W3, 将W4从"高频趋势"改为"信念方向", 因HF估算已被deferred。

Composite score weights. W4 changed from "HF trend" to "conviction direction" since HF estimation is deferred.

> **校准要求**: Phase 5前须完成基于历史数据的网格搜索 (步长0.05), 以IC和Rank IC为优化目标, 输出推荐权重及置信区间 (REV-024)。

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-015 | SCORE_W1_REBALANCE | 0.30 | L3 | 1.0 | 调仓强度权重 / Rebalancing intensity weight |
| ARG-016 | SCORE_W2_MANAGER | 0.25 | L3 | 1.0 | 经理质量权重 / Manager quality weight |
| ARG-017 | SCORE_W3_CONSENSUS | 0.25 | L3 | 1.0 | 共识度权重 / Consensus weight |
| ARG-018 | SCORE_W4_DIRECTION | 0.20 | L3 | 2.0 | 信念方向权重 (V2.0改: 原HF趋势 -> 信念方向) / Conviction direction weight |

---

## S4 池容量与阈值 (Pool Capacity & Thresholds) {#ARGUS-APP-A:pool}

四区动态池的容量上限和晋升/降级阈值。V2.0简化: 移除拥挤度动态容量调整 (deferred), 使用固定容量。

Four-zone pool capacity and promotion/demotion thresholds. V2.0 uses fixed capacity (crowding-based dynamic adjustment deferred).

### S4.1 池容量 (Pool Capacity) {#ARGUS-APP-A:pool-cap}

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-019 | CAP_SCAN | 100 | L1 | 2.0 | SCAN区容量上限 (V2.0新增, 宽松限制) |
| ARG-020 | CAP_WATCH | 30 | L2 | 1.0 | WATCH区容量上限 |
| ARG-021 | CAP_CANDIDATE | 15 | L2 | 1.0 | CANDIDATE区容量上限 |
| ARG-022 | CAP_CONVICTION | 8 | L2 | 1.0 | CONVICTION区容量上限 |

### S4.2 晋升阈值 (Promotion Thresholds) {#ARGUS-APP-A:pool-promote}

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-023 | THRESHOLD_WATCH_ENTRY | 0.30 | L2 | 1.0 | WATCH入池最低bayesian分 |
| ARG-024 | THRESHOLD_CANDIDATE_ENTRY | 0.50 | L2 | 1.0 | CANDIDATE入池最低bayesian分; 同时要求共识>=ARG-037 |
| ARG-025 | THRESHOLD_CONVICTION_ENTRY | 0.70 | L2 | 1.0 | CONVICTION入池最低bayesian分; 经理>=ARG-026, 风格>=ARG-038 |
| ARG-026 | THRESHOLD_CONVICTION_MIN_MANAGERS | 3 | L2 | 1.0 | CONVICTION入池最少经理数 |

### S4.3 降级/清除阈值 (Demotion/Expiry Thresholds) {#ARGUS-APP-A:pool-demote}

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-027 | THRESHOLD_WATCH_EXIT | 0.20 | L2 | 1.0 | WATCH出池bayesian阈值 (低于此降级) |
| ARG-028 | THRESHOLD_CANDIDATE_EXIT | 0.35 | L2 | 1.0 | CANDIDATE出池bayesian阈值; 或连续N周下降 |
| ARG-029 | THRESHOLD_WATCH_MIN_MANAGERS | 2 | L2 | 1.0 | WATCH入池最少经理数 |

---

## S5 拥挤度压制 (Crowding Suppression) {#ARGUS-APP-A:crowding}

V2.0 MVP阶段拥挤度为简化版: 仅SAFE/CAUTION/DANGER三级, 移除KILL区的复杂拆分 (deferred)。

V2.0 MVP: simplified 3-level crowding (SAFE/CAUTION/DANGER). KILL zone split deferred.

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-030 | CROWDING_SAFE_MULTIPLIER | 1.00 | L2 | 1.0 | SAFE区信号乘数: 无压制 |
| ARG-031 | CROWDING_CAUTION_MULTIPLIER | 0.80 | L2 | 1.0 | CAUTION区信号乘数: 轻度压制 |
| ARG-032 | CROWDING_DANGER_MULTIPLIER | 0.50 | L2 | 1.0 | DANGER区信号乘数: 中度压制 |

> **V2.0简化说明**: V1.0的KILL区 (ARG-034/034A/034B, 硬压制+动量豁免) 和拥挤度动态容量调整 (ARG-022/023) 在V2.0 MVP中被deferred。Phase 5回测结果显示需要四层穿透时再引入。

---

## S6 信号时序 (Signal Timing) {#ARGUS-APP-A:timing}

信号过期和不活跃清除参数。

Signal expiry and inactivity cleanup parameters.

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-033 | SIGNAL_EXPIRY_FAST | 10 | L1 | 1.0 | FAST层信号过期天数(交易日) |
| ARG-034 | SIGNAL_EXPIRY_MEDIUM | 30 | L1 | 1.0 | MEDIUM层信号过期天数(交易日) |
| ARG-035 | SIGNAL_EXPIRY_SLOW | 90 | L1 | 1.0 | SLOW层信号过期天数(日历日) |
| ARG-036 | SCAN_INACTIVITY_EXPIRY | 30 | L1 | 1.0 | SCAN区不活跃清除天数: 30日无更新自动清除 |

---

## S7 过滤 (Filtering) {#ARGUS-APP-A:filtering}

池晋升和信号质量过滤参数。

Pool promotion and signal quality filtering parameters.

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-037 | FILTER_CONSENSUS_MIN | 0.40 | L2 | 1.0 | CANDIDATE入池最低共识强度 |
| ARG-038 | FILTER_STYLE_DIVERSITY_MIN | 2 | L2 | 1.0 | CONVICTION入池最少风格种类数 (REV-015) |
| ARG-039 | FILTER_WEEKLY_DECLINE_MAX | 2 | L1 | 1.0 | CANDIDATE出池: 连续N周评分下降则降级 |
| ARG-040 | HIGH_CONVICTION_MANAGER_COUNT | 5 | L2 | 1.0 | 高确信共识最少经理数: >=5位同向信号 |

---

## S8 T-1行为权重 (T-1 Behavior Weights) {#ARGUS-APP-A:t1}

T-1日行为分析的五维权重。REV-010调整后的值。

Five-dimension T-1 behavior analysis weights. Post REV-010 adjustment.

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-041 | T1_WEIGHT_SELL_QUALITY | 0.30 | L2 | 1.0 | 卖出质量权重 (含三分类: 止盈/止损/再平衡, REV-009) |
| ARG-042 | T1_WEIGHT_STYLE_FIDELITY | 0.25 | L2 | 1.0 | 风格忠诚权重 |
| ARG-043 | T1_WEIGHT_BUILD_RHYTHM | 0.20 | L2 | 1.0 | 建仓节奏权重 |
| ARG-044 | T1_WEIGHT_RISK_CONTROL | 0.15 | L2 | 1.0 | 风控能力权重; REV-010从0.10上调至0.15 |
| ARG-045 | T1_WEIGHT_MARKET_ADAPT | 0.10 | L2 | 1.0 | 市场适应权重; REV-010从0.15下调至0.10 |

---

## S9 达尔文时刻检测 (Darwin Moment Detection) -- NEW {#ARGUS-APP-A:darwin}

V2.0新增。基于ADVANCED_FEATURES_DISCUSSION.md的INCLUDE_V1裁决, 达尔文时刻检测器纳入MVP Phase 4。

New in V2.0. Darwin moment detector included in MVP Phase 4 per INCLUDE_V1 ruling.

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-046 | DARWIN_SECTOR_DROP_THRESHOLD | -0.10 | L2 | 2.0 | 触发条件: 行业20日跌幅阈值 (10%) / Sector 20-day drop threshold |
| ARG-047 | DARWIN_HIGH_CRED_THRESHOLD | 0.70 | L2 | 2.0 | 高信誉产品界定: credibility > 此值 / High-credibility product threshold |
| ARG-048 | DARWIN_LOW_CRED_THRESHOLD | 0.50 | L2 | 2.0 | 低信誉产品界定: credibility < 此值 / Low-credibility product threshold |
| ARG-049 | DARWIN_SYSTEMIC_FILTER | -0.08 | L2 | 2.0 | 系统性风险过滤: 沪深300同期跌>8%时降权 (芒格建议) / Systemic risk filter: CSI300 drop >8% downgrades confidence |

---

## S10 共识方向引擎 (Consensus Direction Engine) -- NEW {#ARGUS-APP-A:consensus}

V2.0新增。V1阶段实现景气度方向和信念偏移; 盈利预期对齐deferred至V2。

New in V2.0. V1 implements prosperity direction and conviction shift; EPS alignment deferred.

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-050 | DIRECTION_BULLISH_DELTA | 2.0 | L2 | 2.0 | 景气度BULLISH阈值: cyclical_weight_delta > +2pp / Bullish threshold |
| ARG-051 | DIRECTION_DEFENSIVE_DELTA | -2.0 | L2 | 2.0 | 景气度DEFENSIVE阈值: delta < -2pp / Defensive threshold |
| ARG-052 | CONVICTION_SHIFT_LOOKBACK_30D | 30 | L1 | 2.0 | 信念偏移短期回看天数 / Short-term conviction shift lookback |
| ARG-053 | CONVICTION_SHIFT_BASELINE_MONTHS | 6 | L1 | 2.0 | 信念偏移基准期(月); Kahneman建议避免锚定 / Baseline period for shift (Kahneman anti-anchoring) |

---

## S11 性能预算 (Performance Budget) {#ARGUS-APP-A:perf}

系统运行时间约束。

System runtime constraints.

| 参数ID | 参数名 | 默认值 | 级别 | 引入版本 | 说明 |
|:--|:--|:--|:--:|:--|:--|
| ARG-054 | WEEKLY_WORKFLOW_WARNING_MIN | 5 | L1 | 2.0 | 周更新WARNING阈值(分钟); V2.0从90分钟大幅降低(独立系统更快) |
| ARG-055 | WEEKLY_WORKFLOW_CRITICAL_MIN | 10 | L2 | 2.0 | 周更新CRITICAL阈值(分钟); 超时需排查 |

---

## S12 参数汇总统计 (Parameter Summary) {#ARGUS-APP-A:summary}

| 分组 / Group | 参数范围 / Range | 数量 / Count | 级别分布 / Level Distribution |
|:--|:--|:--:|:--|
| 产品质量阈值 | ARG-001 ~ ARG-006 | 6 | L1: 2, L2: 4 |
| 贝叶斯评分 | ARG-007 ~ ARG-014 | 8 | L2: 5, L3: 3 |
| 复合评分权重 | ARG-015 ~ ARG-018 | 4 | L3: 4 |
| 池容量 | ARG-019 ~ ARG-022 | 4 | L1: 1, L2: 3 |
| 晋升阈值 | ARG-023 ~ ARG-026 | 4 | L2: 4 |
| 降级/清除阈值 | ARG-027 ~ ARG-029 | 3 | L2: 3 |
| 拥挤度压制 | ARG-030 ~ ARG-032 | 3 | L2: 3 |
| 信号时序 | ARG-033 ~ ARG-036 | 4 | L1: 4 |
| 过滤 | ARG-037 ~ ARG-040 | 4 | L1: 1, L2: 3 |
| T-1行为权重 | ARG-041 ~ ARG-045 | 5 | L2: 5 |
| 达尔文时刻 (NEW) | ARG-046 ~ ARG-049 | 4 | L2: 4 |
| 共识方向 (NEW) | ARG-050 ~ ARG-053 | 4 | L1: 2, L2: 2 |
| 性能预算 | ARG-054 ~ ARG-055 | 2 | L1: 1, L2: 1 |
| **总计 / Total** | ARG-001 ~ ARG-055 | **55** | L1: 11, L2: 36, L3: 8 |

### V1.0 -> V2.0 参数映射 (Parameter Migration Map) {#ARGUS-APP-A:migration}

| V1.0参数 | V2.0状态 | 说明 |
|:--|:--|:--|
| ARG-001 ~ ARG-018 | **保留** (编号不变) | 核心评分参数, 完整保留 |
| ARG-019 ~ ARG-030 | **重新编号** | 池参数重组, V2.0为ARG-019~029 |
| ARG-031 ~ ARG-034B | **简化** -> ARG-030~032 | KILL区拆分(034A/034B)和动量豁免deferred |
| ARG-035 ~ ARG-043 | **重新编号** -> ARG-033~040 | 共识/过期/过滤参数保留, 编号调整 |
| ARG-044 ~ ARG-048 | **保留** -> ARG-041~045 | T-1行为权重, 编号调整 |
| ARG-049 ~ ARG-051 | **DEFERRED** | HF估算 (Kalman/Lasso) 在MVP中不实现 |
| ARG-052 ~ ARG-054 | **DEFERRED** | 数据源分层 (T0/T1/T2权重折扣) |
| ARG-055 ~ ARG-057 | **DEFERRED** | DuckDB配置 (MVP不使用DuckDB) |
| ARG-058 | **已合并** | 波动率阈值合并入ARG-010 |
| ARG-059 ~ ARG-062 | **DEFERRED** | 北向资金+NHC Regime |
| ARG-063 | **DEFERRED** | 融资余额拥挤度 |
| ARG-064 ~ ARG-065 | **简化** -> ARG-054~055 | 性能预算, 阈值大幅降低(独立系统更快) |
| ARG-066 | **DEFERRED** | AH共线性折扣 |
| -- | **NEW** ARG-046~049 | 达尔文时刻检测参数 |
| -- | **NEW** ARG-050~053 | 共识方向引擎参数 |

---

## Attestation {#ARGUS-APP-A:attestation}

本附录由Internal Review Board基于以下材料编制:

This appendix was compiled by the Empire Decision Committee based on:

- A_PARAMETER_REGISTRY.md (V1.0, 68参数, 已归档): 参数定义和默认值基线
- EXPERT_PANEL_WG3_WG4_WG5.md: 芒格终审 "如果只能有5张表" + WG3 "20~25个MVP参数" 建议
- ADVANCED_FEATURES_DISCUSSION.md: 达尔文时刻参数 (INV-13量化分析师框架) + 共识方向参数 (INV-13景气度方向仪)
- EXPERT_PANEL_WG1_WG2.md: 贝叶斯评分参数REV-007/010/013/014修订

V2.0从68参数精简至55参数 (净减少13), 同时新增8个达尔文/共识方向参数。移除的15个参数为DuckDB、HF估算、北向资金等deferred功能。

---

## Changelog {#ARGUS-APP-A:changelog}

| 版本 / Version | 日期 / Date | 作者 / Author | 变更说明 / Changes |
|:--|:--|:--|:--|
| 0.1.0-draft | 2026-04-12 | Claude (SESSION-008) | V1.0初稿: 68参数完整注册表 (已归档为A_PARAMETER_REGISTRY.md) |
| 2.0.0-draft | 2026-04-12 | Internal Review Board | V2.0重写: 55参数MVP注册表; 移除HF/DuckDB/NHC/AH参数; 新增达尔文+共识方向参数; 重新编号 |

---

**[ATTESTATION]**
ARGUS-APP-A V2.0.0-draft | RFC-2026-071 | 2026-04-12
Based on: V1.0 68-param registry + Munger simplification + WG3 MVP + Darwin/Consensus features
SOP: init-context-draft-review-finalize
