---
file_id: ARGUS-06
title: "设计 — 高级分析能力 / Advanced Analytical Capabilities"
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
  - "ARGUS-04 (信号引擎与评分: 六层架构 + 贝叶斯融合 + 共识检测)"
  - "ARGUS-05 (股票池管理 + Web 界面: /analysis 页面)"
  - "ADVANCED_FEATURES_DISCUSSION (8席专家讨论: 六大高级分析层)"
  - "EXPERT_PANEL_WG1_WG2 (WG2 投资理论基础)"
amendment_level: L2
language: "zh-CN / en"
roadmap_scope: "V1 (Darwin + Consensus Direction + Opportunity Lens) / V2 (Causal Chain + Graphify) / V3 (Super Cycle)"
---

# ARGUS-06: 高级分析能力

# ARGUS-06: Advanced Analytical Capabilities

> **本文件是 RFC-2026-071 ARGUS 百目巨人独立系统 v2.0 的高级分析层规格。**
> 覆盖 V1 交付 (达尔文时刻 + 共识方向引擎 + 机会透镜)、V2 路线图 (因果链 + Graphify 集成)、V3 研究方向 (超级周期猜想)。
> 核心信号引擎详见 ARGUS-04; Web 界面详见 ARGUS-05 (SS5.6 `/analysis` 页面)。

---

## SS1 达尔文时刻检测 (V1) {#ARGUS-06:darwin}

### 1.1 概念定义 / Concept {#ARGUS-06:darwin-concept}

"达尔文时刻" (Darwinian Moment) 是市场自然选择信号: 当某板块经历显著回调时，弱势资金 (低信誉产品) 选择离场，而强势资金 (高信誉产品) 选择坚守甚至加仓。这种分歧标志着"优胜劣汰"正在发生 -- 投机性持仓被清除，深度研究驱动的持仓被保留。

**专家裁决**: INCLUDE_V1 -- 检测逻辑简单、数据需求可满足、回测成本低，V1 性价比最高的高级功能。

### 1.2 检测算法 (Deterministic Pipeline) {#ARGUS-06:darwin-algorithm}

```
darwin_detector(date) -> list[DarwinEvent]:

  FOR EACH sector IN SW_LEVEL1_SECTORS:

    # Step 1: 扫描行业回调
    drawdown_20d = calc_sector_drawdown(sector, date, window=20)
    IF drawdown_20d >= -0.10:
      CONTINUE  # 跌幅不足, 跳过

    # Step 2: 系统性风险过滤 (芒格建议)
    market_drawdown = calc_index_drawdown("000300.SH", date, window=20)
    is_systemic = (market_drawdown < -0.08)

    # Step 3: 按信誉分组
    weak_products   = products WHERE credibility < 0.50
    strong_products = products WHERE credibility > 0.70

    # Step 4: 计算行业内净行为 (20日)
    weak_action   = net_sector_weight_change(weak_products, sector, 20d)
    strong_action = net_sector_weight_change(strong_products, sector, 20d)

    # Step 5: 分歧检测
    IF weak_action < 0 AND strong_action >= 0:
      # 弱手撤退, 强手坚守或加仓

      strength = normalize(
        abs(weak_action) * strong_action * count_adds(strong_products, sector)
      )

      confidence = strength * (0.70 IF is_systemic ELSE 1.00)
      # 系统性风险时打 7 折

      EMIT DarwinEvent(
        sector, date, drawdown_20d,
        is_systemic, weak_action, strong_action,
        strength, confidence
      )
```

**数据源需求 (REV-035)**:
达尔文检测器需要以下外部数据:
- 申万一级行业指数日涨跌幅: Tushare `index_daily(ts_code='8xxxxx.SI')`
- 若Tushare不可用: 从raw_daily_holding聚合计算行业持仓权重变化作为代理指标
- MVP阶段: 优先使用持仓聚合方式（零外部依赖），Tushare为增强

### 1.3 触发条件 / Trigger Conditions {#ARGUS-06:darwin-triggers}

三个条件必须同时满足:

| # | 条件 | 阈值 | 数据来源 |
|:--:|:--|:--|:--|
| 1 | 行业回调 | 申万一级行业指数 20 日跌幅 >= 10% | 外部 (Wind/AKShare) |
| 2 | 弱手撤退 | credibility < 0.5 产品在该行业净卖出 | `dec_product_credibility` + `proc_holding` |
| 3 | 强手坚守 | credibility > 0.7 产品在该行业净持平或净买入 | 同上 |

**强手加仓强化** (INV-02): 强势产品主动加仓 (HEAVY/SEQUENTIAL) 时信号强度上调 1.3x。

### 1.4 数据库设计: `argus_darwin_event` {#ARGUS-06:darwin-table}

```sql
CREATE TABLE argus_darwin_event (
    event_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_code       TEXT    NOT NULL,        -- 申万一级行业代码
    sector_name       TEXT    NOT NULL,        -- 行业名称
    trigger_date      TEXT    NOT NULL,        -- 触发日期 (YYYY-MM-DD)
    drawdown_20d      REAL    NOT NULL,        -- 行业 20 日回撤 (负数)
    is_systemic       INTEGER NOT NULL DEFAULT 0,  -- 是否系统性下跌
    market_drawdown   REAL,                    -- 沪深 300 同期回撤
    weak_net_action   REAL    NOT NULL,        -- 弱手净行为 (负=减仓)
    strong_net_action REAL    NOT NULL,        -- 强手净行为 (正=加仓)
    strong_add_count  INTEGER NOT NULL,        -- 强手中主动加仓的产品数
    strength          REAL    NOT NULL
                      CHECK (strength BETWEEN 0 AND 1),
    confidence        REAL    NOT NULL
                      CHECK (confidence BETWEEN 0 AND 1),
    outcome_30d       REAL,   -- 触发后 30 日行业超额收益 (事后填入)
    outcome_60d       REAL,   -- 触发后 60 日
    outcome_90d       REAL,   -- 触发后 90 日
    status            TEXT    NOT NULL DEFAULT 'ACTIVE'
                      CHECK (status IN ('ACTIVE','CONFIRMED',
                                        'INVALIDATED','EXPIRED')),
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_darwin_sector ON argus_darwin_event(sector_code);
CREATE INDEX idx_darwin_date   ON argus_darwin_event(trigger_date);
```

### 1.5 Web 展示: Darwin 卡片 + 时间线 {#ARGUS-06:darwin-web}

在 `/analysis` 页面 Section A 展示 (参照 ARGUS-05 SS5.6 Prototype E):

**Darwin 事件卡片结构**:

```
┌──────────────────────────────────────────────────────┐
│ [闪电图标]  达尔文时刻: 有色金属           2026-04-08  │
│                                                      │
│  行业回调: -12.3% (20日)   系统性: 否                 │
│  弱手行为: -2.1pp (3产品减仓)                          │
│  强手行为: +0.8pp (2产品加仓, 1产品持平)               │
│  信心度: 0.74 | 强度: 0.68                            │
│                                                      │
│  历史同类事件: 过去3年共6次, 60日胜率: 67%              │
│  [芒格警告: 若为系统性下跌, 信心度打7折]               │
│                                                      │
│  [查看涉及标的]  [查看历史事件]                         │
└──────────────────────────────────────────────────────┘
```

**时间线视图**: 按月份展示达尔文事件触发时间点，标注行业名称和后续收益 (事后填入)。

**Outcome自动回填 (REV-038)**:
- 每日Step 3结束后，检查所有status='ACTIVE'且trigger_date超过30天的darwin_event
- 自动计算: 触发日起30天板块涨跌幅
- 填入: outcome_return_pct, outcome_tag (CORRECT=板块反弹>5% / INCORRECT=继续下跌 / NEUTRAL=波动<5%)
- 更新达尔文置信度参数（类似产品信誉的贝叶斯更新）

### 1.6 历史验证方法论 / Historical Validation {#ARGUS-06:darwin-validation}

**回测框架** (INV-13 提出):

| 步骤 | 操作 |
|:--|:--|
| 1 | 收集 2020-2025 年所有满足触发条件的事件 |
| 2 | 计算事件后 30/60/90 日行业超额收益 (vs 沪深 300) |
| 3 | 统计 median excess return, t-test p-value |
| 4 | 目标: 60 日 median excess return 显著为正 (p < 0.05) |

**预期指标** (INV-13 估算):

| 指标 | 估算值 |
|:--|:--:|
| 年均触发次数 | 4~6 次 |
| 预期胜率 (60 日超额 > 0) | 55%~65% |
| 系统性 false positive | ~30% (芒格过滤可去除) |
| 加入"强手加仓"条件后胜率 | 65%~75% |

### 1.7 False Positive 缓解 (芒格系统性风险过滤) {#ARGUS-06:darwin-false-positive}

**Munger Filter**: 当沪深 300 同期 20 日跌幅 > 8% 时，判定为系统性下跌:
- 达尔文事件仍然记录 (数据完整性)
- `is_systemic = 1` 标记
- `confidence *= 0.70` (置信度打 7 折)
- Web 界面显示黄色警告: "此事件发生在系统性下跌期间，信心度已降低"

**Kahneman 幸存者偏差缓解**: 历史事件列表中 CONFIRMED 和 INVALIDATED 同等权重展示。

---

## SS2 共识方向引擎 (V1) {#ARGUS-06:consensus-direction}

### 2.1 概念定义 / Concept {#ARGUS-06:direction-concept}

共识方向引擎从产品的集体交易行为中推断两个维度的市场共识方向:
- **景气度方向** (Prosperity Direction): 经济周期位置判断 -- 产品在周期性行业与防御性行业之间的仓位迁移
- **信念偏移** (Conviction Shift): 月度行业权重变化的方向和速度 -- 机构对各行业确信度的动态演变

**专家裁决**: INCLUDE_V1 (景气度方向 + 信念偏移) / INCLUDE_V2 (盈利预期对齐, 需外部 EPS 数据)

### 2.2 景气度方向仪 / Prosperity Gauge {#ARGUS-06:prosperity-gauge}

**行业分组**:

| 组别 | 包含行业 (申万一级) |
|:--|:--|
| 周期组 (Cyclical) | 有色金属、钢铁、基础化工、机械设备、汽车 |
| 防御组 (Defensive) | 食品饮料、医药生物、公用事业、银行 |

**计算公式**:

```
prosperity_score = SUM(cyclical_weight_change) - SUM(defensive_weight_change)

其中:
  weight_change = 产品在该行业的 30 日持仓权重变化 (pp)
  SUM 跨所有追踪产品

三级信号:
  BULLISH:    prosperity_score > +2.0 pp
  NEUTRAL:    -2.0 pp <= prosperity_score <= +2.0 pp
  DEFENSIVE:  prosperity_score < -2.0 pp
```

**Web 展示**: `/analysis` Section B -- 半圆 gauge (DEFENSIVE ~ BULLISH)，服务端 inline SVG。

### 2.3 信念偏移雷达 / Conviction Shift Radar {#ARGUS-06:conviction-radar}

每周计算各申万一级行业的权重变化矩阵:

```
FOR EACH sector IN SW_LEVEL1_SECTORS:
  delta_30d = avg_weight_now - avg_weight_30d_ago
  delta_60d = avg_weight_now - avg_weight_60d_ago

  acceleration = delta_30d - (delta_60d - delta_30d)
  # 正向加速 = conviction rising
  # 正向减速 = topping
  # 负向加速 = conviction collapsing

基准: 6 个月滚动均值 (INV-12/Kahneman 建议, 避免锚定效应)
```

**Web 展示**: 行业 x 时间热力图 (红=增持, 蓝=减持) + 行业权重柱状图。

### 2.4 数据库参考 / Database Reference {#ARGUS-06:direction-table}

共识方向数据存入 `dec_consensus` 表的扩展字段:

| 字段 | 类型 | 说明 |
|:--|:--|:--|
| `direction_type` | TEXT | 'PROSPERITY' / 'CONVICTION_SHIFT' |
| `prosperity_score` | REAL | 景气度分数 (正=周期, 负=防御) |
| `prosperity_signal` | TEXT | 'BULLISH' / 'NEUTRAL' / 'DEFENSIVE' |
| `sector_deltas` | TEXT (JSON) | 各行业 30d/60d 权重变化 |
| `measurement_date` | TEXT | 计算日期 |

### 2.5 盈利预期对齐 (V2, 依赖外部 EPS 数据) {#ARGUS-06:eps-alignment}

**V2 设计预留**: 待接入 Wind EPS consensus 数据后:
- 对每笔买入标注 "领先" (在分析师上调前) 或 "跟随" (在分析师上调后)
- 领先买入比例高的产品获得 D4 (独立性) 加分
- **Fama 警告**: 因果方向可能相反 (产品重仓 -> 分析师跟进)，须谨慎解读

---

## SS3 机会透镜 (V1) {#ARGUS-06:opportunity-lens}

### 3.1 概念定义 / Concept {#ARGUS-06:lens-concept}

Opportunity Lens 将多个分析层输出汇聚为统一的机会发现工具。采纳芒格教授和 Kahneman 教授建议: 放弃复合评分方案，采用 **Munger 5-Question Checklist** -- 简单等权清单在预测准确性上常优于复杂加权模型 (Dawes, 1979)。

**设计哲学**: 5 个 YES 比一个 composite score 更有说服力。人类决策者看清单比看 0.73 这样的数字更能做出好判断。

### 3.2 Munger 五问清单 / Five-Question Checklist {#ARGUS-06:munger-checklist}

对每只进入 CANDIDATE 或 CONVICTION 区的标的生成清单:

| # | 问题 | 数据来源 | V1/V2 |
|:--:|:--|:--|:--:|
| Q1 | 强产品正在买入? Strong product buying? | `proc_rebalancing_event` + `dec_product_credibility` | V1 |
| Q2 | 不拥挤? Not crowded? | `dec_stock_pool.crowding_zone` != DANGER/KILL | V1 |
| Q3 | 达尔文信号? Darwin signal? | `argus_darwin_event` 该行业 90 日内有事件 | V1 |
| Q4 | 共识方向对齐? Consensus aligned? | `dec_consensus.prosperity_signal` 与标的行业匹配 | V1 |
| Q5 | 无矛盾卖出? No contradictory sells? | 无高信誉产品在该标的卖出 | V1 |

**V2 扩展** (V1 基础上追加):

| # | 问题 | 数据来源 | V2 |
|:--:|:--|:--|:--:|
| Q6 | 因果链证据? Causal chain evidence? | `argus_causal_chain` | V2 |
| Q7 | 图谱共识形成? Graph consensus? | `argus_graph_cluster` | V2 |

### 3.3 评分与展示 / Score & Display {#ARGUS-06:lens-scoring}

```
checklist_score = count(YES answers) / total_questions

V1: score = N / 5  (0, 1, 2, 3, 4, 5)
V2: score = N / 7  (0 ~ 7)
```

**Web 展示 -- Checklist Card**:

```
┌──────────────────────────────────────────────────────┐
│ 华友钴业 (603799)  |  CANDIDATE  |  2026-04-11       │
│ ──────────────────────────────────────────────────── │
│ [x] Q1 强产品买入: 中欧1号(heavy)+景顺2号(normal)     │
│ [x] Q2 不拥挤: SAFE 区                               │
│ [x] Q3 达尔文信号: 有色金属 03-28 触发                │
│ [x] Q4 共识方向: 周期组权重 +3.2pp (BULLISH)          │
│ [ ] Q5 无矛盾卖出: 鹏华4号近期减仓 -0.5%             │
│ ──────────────────────────────────────────────────── │
│ Checklist: 4/5  |  结论: 强信号, 但有一产品减仓       │
└──────────────────────────────────────────────────────┘
```

### 3.4 集成位置 / Integration Points {#ARGUS-06:lens-integration}

- **个股详情页** `/stocks/{code}`: Checklist 面板嵌入 Section C 下方
- **深度分析页** `/analysis`: Section C 展示所有 CANDIDATE/CONVICTION 标的的 Checklist 卡片集合
- **推荐 JSON**: `checklist_score` 字段包含在 CONVICTION 推荐中 (见 ARGUS-05 SS3.2)

---

## SS4 因果链检测 (V2 路线图) {#ARGUS-06:causal-chain}

### 4.1 概念定义 / Concept {#ARGUS-06:chain-concept}

因果链分析从产品交易序列中提取有方向性的先后关系: 不是"谁买了什么" (Layer 3 已解决)，而是"谁先买，谁跟买，价格何时响应"。

**专家裁决**: INCLUDE_V2 -- 统计框架成熟，需 60+ 交易日数据积累。Phase E+ 实现。

### 4.2 检测算法草案 / Algorithm Sketch {#ARGUS-06:chain-algorithm}

```
causal_chain_detector(weekly):

  Step 1: Event Extraction
    - 扫描 proc_rebalancing_event, 提取 action=BUY
    - 按 stock_code 分组, 按 trade_date ASC 排序
    - 过滤: 同一 stock_code 在 10 日窗口内 >= 2 不同产品买入

  Step 2: Sequence Construction
    - 构建 (product_id, trade_date, intent, amount_pct) 序列
    - 标注每节点 credibility

  Step 3: Price Response Verification
    - 取序列末尾后 5 日标的收益率
    - 减去行业基准收益率 = excess_return

  Step 4: Statistical Validation (Fama/Kahneman Filter)
    - 构建 null distribution: 随机打乱日期 1000 次, 重算 excess
    - 真实 excess 在 null 中 percentile > 95% -> 通过
    - p_value = 1 - percentile / 100

  Step 5: Confidence Scoring
    confidence = 0.4 * avg_credibility
              + 0.3 * (1 - p_value)
              + 0.2 * intent_strength
              + 0.1 * sequence_consistency
```

### 4.3 数据库设计: `argus_causal_chain` {#ARGUS-06:chain-table}

```sql
CREATE TABLE argus_causal_chain (
    chain_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code        TEXT    NOT NULL,
    stock_name        TEXT    NOT NULL,
    detection_date    TEXT    NOT NULL,  -- YYYY-MM-DD
    chain_start       TEXT    NOT NULL,  -- 序列起始日
    chain_end         TEXT    NOT NULL,  -- 序列末笔交易日
    chain_length      INTEGER NOT NULL,  -- 参与产品数
    chain_sequence    TEXT    NOT NULL,  -- JSON array
    price_response    REAL,              -- 链后 5 日超额收益 (%)
    confidence        REAL    NOT NULL
                      CHECK (confidence BETWEEN 0 AND 1),
    p_value           REAL    NOT NULL
                      CHECK (p_value BETWEEN 0 AND 1),
    status            TEXT    NOT NULL DEFAULT 'ACTIVE'
                      CHECK (status IN ('ACTIVE','CONFIRMED',
                                        'INVALIDATED','EXPIRED')),
    notes             TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_chain_stock ON argus_causal_chain(stock_code);
CREATE INDEX idx_chain_date  ON argus_causal_chain(detection_date);
CREATE INDEX idx_chain_conf  ON argus_causal_chain(confidence DESC);
```

### 4.4 Anti-Spurious Causality Measures (Fama/Kahneman) {#ARGUS-06:chain-anti-spurious}

**四重过滤** (专家团集体要求):

| # | 过滤器 | 提出者 | 实现方式 |
|:--:|:--|:--|:--|
| 1 | 共同信息源去重 | Fama | 链中产品均在重大事件后 48h 内买入 -> 标记 COMMON_INFO |
| 2 | 随机基准对比 | Fama | Permutation test p-value, p > 0.05 标灰显示 |
| 3 | 样本量门槛 | Fama | 同标的至少 3 次独立检测才标为"可靠模式" |
| 4 | 确认偏差缓解 | Kahneman | 同时展示"反面证据" -- 多产品序列后价格未涨的案例 |

**芒格警告**: 因果链被市场发现后信号自我毁灭。须监控滚动胜率衰减。

### 4.5 Web 展示: Timeline Visualization {#ARGUS-06:chain-web}

在 `/analysis` Section D 展示 (V2 启用后):

```
华友钴业 (603799) | 因果链 #127 | confidence: 0.73 | p-value: 0.031

Day 1        Day 2        Day 3              Day 5
  |            |            |                  |
  [A]-------->[C]-------->[B]                [+6.2%]
  heavy       normal      normal             超额收益
  cred:0.82   cred:0.65   cred:0.71

统计检验: 随机基准下此超额收益出现概率 3.1% (p=0.031)
Fama 警告: 此链可能反映共同信息源而非真实因果
```

**Target**: V1 稳定后 (Phase E+) 实现

---

## SS5 Graphify 集成 (V2 路线图) {#ARGUS-06:graphify}

### 5.1 概念定义 / Concept {#ARGUS-06:graphify-concept}

将 ARGUS 交易数据周期性输入 Graphify 知识图谱系统，利用图论算法 (社区发现、中心性分析、路径查找) 发现跨产品、跨行业隐含关联。

**核心价值**: 降维 -- 把 200 个标的压缩为 5~8 个主题集群 (INV-13)。

**专家裁决**: INCLUDE_V2 -- 技术成熟，需 V1 数据积累 4~8 周。

### 5.2 触发频率与增量策略 {#ARGUS-06:graphify-schedule}

| 维度 | 方案 |
|:--|:--|
| 运行频率 | 每周五收盘后 (与 ARGUS 周度更新同步); 月末全量重建 |
| 触发条件 | ARGUS 数据更新完成 -> 导出三元组 -> 调用 Graphify pipeline |
| 增量策略 | 周度=增量 (仅新增本周交易边); 月度=全量 (含权重衰减) |

### 5.3 数据到三元组映射 / Entity-Relation Mapping {#ARGUS-06:graphify-mapping}

**Entity Types**:

| 实体类型 | 属性 | 来源 |
|:--|:--|:--|
| PRODUCT | id, name, credibility, style_label | `proc_product_profile` |
| STOCK | code, name, sector, industry | 行情数据 |
| SECTOR | code, name | 申万分类 |
| SIGNAL | signal_id, type, direction, score | `dec_signal` |
| DARWIN_EVENT | event_id, sector, date, confidence | `argus_darwin_event` |
| CONSENSUS | type, strength, products | `dec_consensus` |

**Relation Types**:

| 关系 | 格式 | 权重来源 |
|:--|:--|:--|
| HOLDS | (product, stock, weight, date) | `proc_holding` |
| BUYS | (product, stock, intent, amount, date) | `proc_rebalancing_event` |
| SELLS | (product, stock, amount, date) | `proc_rebalancing_event` |
| BELONGS_TO | (stock, sector) | 行业分类 |
| UPSTREAM_OF | (sector, sector) | 产业链静态数据 |

### 5.4 可发现的四种模式 / Four Discoverable Patterns {#ARGUS-06:graphify-patterns}

| 模式 | 算法 | 说明 |
|:--|:--|:--|
| 产业链共识 Supply Chain Consensus | Louvain/Leiden | 多产品沿同一产业链布局 |
| 隐性同行 Hidden Peers | Jaccard Similarity | 持仓高度重叠的股票对 |
| 信念桥梁 Conviction Bridge | Betweenness Centrality | 连接多集群的高中心性标的 |
| 叙事迁移 Narrative Shift | 时序图谱对比 | 新兴/衰退/稳定集群 (Shiller) |

### 5.5 存储: `argus_graph_cluster` {#ARGUS-06:graphify-table}

```sql
CREATE TABLE argus_graph_cluster (
    cluster_id      TEXT    PRIMARY KEY,  -- "C1-2026W15"
    snapshot_week   TEXT    NOT NULL,     -- ISO 周 (2026-W15)
    theme_label     TEXT    NOT NULL,     -- Claude 生成主题标签
    product_ids     TEXT    NOT NULL,     -- JSON array
    stock_codes     TEXT    NOT NULL,     -- JSON array
    sector_codes    TEXT    NOT NULL,     -- JSON array
    strength        REAL    NOT NULL
                    CHECK (strength BETWEEN 0 AND 1),
    trend           TEXT    NOT NULL
                    CHECK (trend IN ('GROWING','STABLE',
                                     'FADING','NEW','GONE')),
    node_count      INTEGER NOT NULL,
    edge_count      INTEGER NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_cluster_week ON argus_graph_cluster(snapshot_week);
```

**Target**: V1 数据积累 4~8 周后实施

---

## SS6 超级周期猜想 (V3 研究方向) {#ARGUS-06:super-cycle}

### 6.1 概念定义 / Concept (No Implementation Commitment) {#ARGUS-06:supercycle-concept}

超级周期猜想试图回答: 能否从机构交易模式中检测多年期大周期的起点? 当多个高质量产品在相近时间窗口内同时对一个此前被忽视的行业建立初始头寸 (probe 级别)，可能标志着新产业周期萌芽。

**专家裁决**: RESEARCH_NEEDED -- 概念有吸引力但信噪比未验证。V2 仅作为观察面板纳入，不作为信号源。V3 视研究进展决定。

### 6.2 专家团研究要求 / Expert Panel Requirements {#ARGUS-06:supercycle-requirements}

| 专家 | 核心观点 |
|:--|:--|
| INV-10 Fama | 信噪比约 1:2.7; 每 2~3 年仅 1 个 true positive; 统计推断无法达 95% 置信度 |
| INV-02 价值型 | 最早可检测 Phase 2 (确认期); Phase 2 与常规轮动几乎不可区分 |
| INV-11 Shiller | 仅交易数据不够，需 narrative 数据; Graphify 新兴社区检测可辅助 |

**提升信噪比的过滤条件** (约至 1:0.8): 风格差异 >= 2 种 + 行业 6 月内无主要持有 + 连续 2+ 周建仓

### 6.3 芒格最终裁决 / Munger Final Verdict {#ARGUS-06:supercycle-verdict}

芒格定性: research question, not engineering question。不要让系统做判断，让系统做展示。

**V3 启动条件**: (1) ARGUS 运行满 2 年 (2) V1/V2 稳定 (3) 回测信噪比 >= 1:1

**V2 过渡方案**: Web 新增 "Emerging Themes" 观察卡片 -- 展示近 30 日"多产品新建仓"行业列表。不生成信号，仅注意力引导。复用 `proc_holding`，无需新表。

---

## 功能路线图总览 / Feature Roadmap Summary {#ARGUS-06:roadmap}

| 功能 | 版本 | 数据需求 | 算法成熟度 | 专家裁决 |
|:--|:--:|:--|:--:|:--|
| 达尔文时刻 | **V1** | 行业指数 (外部) + 产品持仓 (内部) | HIGH | INCLUDE_V1 |
| 共识方向引擎 | **V1** | 纯内部数据 | HIGH | INCLUDE_V1 |
| 机会透镜 (3/5 checklist) | **V1** | V1 各层输出 | HIGH | INCLUDE_V1 |
| 因果链检测 | **V2** | 60+ 交易日内部数据 | HIGH | INCLUDE_V2 |
| Graphify 集成 | **V2** | 4~8 周内部数据积累 | HIGH | INCLUDE_V2 |
| 机会透镜 (5/7 checklist) | **V2** | V2 各层输出 | HIGH | INCLUDE_V2 |
| 盈利预期对齐 | **V2** | 外部 EPS consensus | MEDIUM | INCLUDE_V2 |
| 超级周期猜想 | **V3** | 2+ 年运行数据 | LOW | RESEARCH_NEEDED |

---

## 变更日志 / Changelog {#ARGUS-06:changelog}

| 版本 | 日期 | 变更内容 |
|:--|:--|:--|
| 2.0.0-draft | 2026-04-12 | 初始 V2.0 草案。整合 8 席专家讨论 (EP-ARGUS-ADV-2026-001) 六大高级分析层成果; 达尔文时刻含检测算法伪代码 + 表设计 + 芒格系统性风险过滤; 共识方向引擎含景气度仪 + 信念偏移雷达 (Kahneman 基准修正); 机会透镜采纳 Munger Checklist 方案 (弃用 composite score); 因果链含四重 anti-spurious 过滤 (Fama/Kahneman); Graphify 含四种可发现模式 + 表设计; 超级周期明确为 V3 研究方向 (芒格裁决) |

---

## 签署与认证 / Attestation {#ARGUS-06:attestation}

| 角色 | 签署人 | 状态 | 日期 |
|:--|:--|:--|:--|
| Drafter | Internal Review Board | DRAFTED | 2026-04-12 |
| Reviewer | -- | PENDING | -- |
| Approver | Internal Review Board | PENDING | -- |

---

*ARGUS-06 v2.0.0-draft -- Advanced Analytical Capabilities*
*RFC-2026-071 ARGUS 百目巨人独立系统*
