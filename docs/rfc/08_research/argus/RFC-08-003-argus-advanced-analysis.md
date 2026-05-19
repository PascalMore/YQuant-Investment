# RFC-08-003：Argus Phase 4 深度分析规范详细设计

## 元数据（Metadata）
| 项 | 值 |
|---|---|
| RFC ID | RFC-08-003 |
| 标题 | Argus Phase 4 深度分析规范详细设计 |
| 状态 | Draft |
| 作者 | YQuant |
| Owner | YQuant / 08_research |
| 创建日期 | 2026-05-19 |
| 最后更新 | 2026-05-19 |
| 版本号 | V0.1 |
| 所属模块 | 08_research（投研分析）/ argus |
| 依赖RFC | RFC-08-001-argus-integration, RFC-08-002-argus-signal-interface, RFC-2026-071_ARGUS/05_POOL_WEB, RFC-2026-071_ARGUS/06_ADVANCED_ANALYSIS |
| 适配AI工具 | OpenClaw、Claude Code、Codex |
| 标签 | #argus #advanced-analysis #darwin #consensus #munger-checklist #MongoDB |

### 版本历史（Changelog）
| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-05-19 | 初始创建。定义 Phase 4 深度分析层的功能规格、MongoDB schema、Python API、WebUI 规格和验收标准 | YQuant |

## 1. 执行摘要
Phase 4 将 Argus 从“可查询的机构资金行为数据库”升级为“可判断的单股深度分析系统”。本阶段不替代 Portfolio 的组合决策，也不直接生成交易指令，而是在 Phase 2 的标准化 Argus 信号和 Phase 3 的自动规则引擎之上，形成面向单只股票的深度分析视图：

1. Darwin 时刻检测：识别行业回调中弱手退出、强手坚守或加仓的自然选择时刻。
2. 共识方向引擎：汇总多产品对同一股票的方向、权重和拥挤折扣，给出可解释的共识置信度。
3. Munger Checklist：用 5 项等权清单评估机会质量，避免用单一复合分数制造虚假精确感。

Phase 4 的输出写入 MongoDB 集合 `tradingagents.08_research_argus_deep_analysis`，供 WebUI 的 `/analysis` 页面和 `/stocks/{wind_code}` 个股详情页读取，并为 Phase 5 回测提供结构化事件样本。

## 2. 业务背景
### 2.1 当前阶段的问题
Phase 1 已完成 CRUD 能力，Phase 2 已完成 Argus 信号到 Portfolio 的标准接口，Phase 3 已完成自动规则引擎。系统已经能回答“哪些产品买了什么”“哪些股票进入哪个池区”“当前有哪些规则命中”，但仍缺少三个判断能力：

| 问题 | 当前能力 | Phase 4 目标 |
|---|---|---|
| 市场环境判断 | 能看到个股和产品行为 | 能识别行业回调中的强弱资金分化 |
| 多产品共识判断 | 能统计信号数量 | 能计算方向、权重、拥挤折扣后的共识置信度 |
| 机会质量判断 | 能输出 composite score | 能用简单清单说明为什么值得看、哪里仍有疑点 |

### 2.2 Phase 4 解决的问题
Phase 4 的核心是把“信号列表”转换为“投资研究上下文”：

- 从单笔信号升级为事件：识别 Darwin 时刻，解释行业压力下谁在撤退、谁在承担风险。
- 从产品行为升级为共识方向：对同一股票跨产品聚合，避免把单一产品动作误读为系统性机会。
- 从分数升级为清单：用 Munger 5 项 checklist 让人类决策者看到证据、缺口和反面信息。
- 从当下快照升级为可回测样本：每次分析输出保留 evidence 和后续 outcome 字段，供 Phase 5 校准胜率。

### 2.3 设计原则
| 原则 | 说明 |
|---|---|
| 行为证据优先 | 所有判断必须能追溯到产品交易、持仓、行业回撤或历史事件 |
| 简单模型优先 | Phase 4 不引入黑盒 ML；先使用确定性规则和可解释评分 |
| 置信度克制 | 样本不足、系统性下跌、拥挤过高时必须降置信度 |
| 研究辅助定位 | 输出用于研究和组合讨论，不直接代表买卖建议 |
| 可回测闭环 | 每类事件必须保存检测时间、证据和后续收益，支持 Phase 5 评估 |

## 3. 功能规格
### 3.1 Darwin 时刻检测
#### 3.1.1 概念定义
Darwin 时刻是市场自然选择信号：某行业经历显著回调时，低信誉产品减仓退出，高信誉产品坚守或加仓，说明投机性资金被清洗，而更高置信度资金愿意承受短期波动。

#### 3.1.2 事件类型（event_type）
| event_type | 定义 | 触发条件 |
|---|---|---|
| `SECTOR_DRAWDOWN` | 行业回调 | 申万一级行业 20 日回撤 <= -10% |
| `WEAK_HAND_EXIT` | 弱手退出 | credibility < 0.50 的产品在该行业 20 日净减仓 |
| `STRONG_HAND_HOLD` | 强手坚守 | credibility >= 0.70 的产品在该行业 20 日净持平或小幅增持 |
| `STRONG_HAND_ADD` | 强手加仓 | credibility >= 0.70 的产品在该行业 20 日净增持，且出现 HEAVY/SEQUENTIAL 意图 |
| `CROWDING_REVERSAL` | 拥挤逆转 | 原高拥挤标的或行业出现产品分化，crowding_zone 从 DANGER/KILL 降至 WATCH/SAFE |
| `SYSTEMIC_STRESS` | 系统性压力标记 | 沪深300 20 日回撤 <= -8%，不单独构成正向事件，只作为降权标签 |

一个 Darwin 分析记录可包含多个 `event_type`，但必须至少包含 `SECTOR_DRAWDOWN`，并同时满足弱手退出和强手坚守/加仓之一，才可输出 `darwin_signal=true`。

#### 3.1.3 检测算法
```text
detect(date, sector_code=None, lookback_days=20):

1. 扫描行业 20 日回撤
   sector_drawdown_20d <= -10% 才进入候选

2. 计算系统性风险
   market_drawdown_20d <= -8% 时标记 SYSTEMIC_STRESS

3. 按产品信誉分组
   weak_products: credibility < 0.50
   strong_products: credibility >= 0.70

4. 聚合行业净行为
   weak_net_action = sum(weak product sector weight change)
   strong_net_action = sum(strong product sector weight change)

5. 判定事件类型
   weak_net_action < 0 触发 WEAK_HAND_EXIT
   strong_net_action >= 0 触发 STRONG_HAND_HOLD
   strong_net_action > 0 且有 HEAVY/SEQUENTIAL 触发 STRONG_HAND_ADD

6. 计算强度和置信度
   raw_strength = normalize(abs(weak_net_action) * max(strong_net_action, 0.01) * log1p(strong_product_count))
   confidence = raw_strength * data_quality_factor * systemic_discount
```

#### 3.1.4 confidence 计算
| 因子 | 规则 |
|---|---|
| `strength` | 弱手撤退幅度、强手增持幅度、强手产品数量的归一化结果 |
| `data_quality_factor` | 行业映射、持仓快照、交易记录完整度；默认 0.6-1.0 |
| `systemic_discount` | 非系统性下跌为 1.0；系统性下跌为 0.70 |
| `strong_add_bonus` | 出现 HEAVY/SEQUENTIAL 强手加仓时 `strength *= 1.30`，封顶 1.0 |
| `sample_penalty` | 强手产品数 < 2 或弱手产品数 < 2 时 `confidence *= 0.80` |

置信度分层：
| confidence | 等级 | 展示 |
|---|---|---|
| >= 0.75 | HIGH | 高置信 Darwin 事件 |
| 0.55-0.75 | MEDIUM | 中置信，需结合清单 |
| 0.35-0.55 | LOW | 观察事件 |
| < 0.35 | INSUFFICIENT | 不输出为有效事件，仅保留审计记录 |

#### 3.1.5 evidence 字段
`evidence` 必须是可审计 JSON，对应每次判断的输入摘要：

```json
{
  "sector": {"code": "801050.SI", "name": "有色金属", "drawdown_20d": -0.123},
  "market": {"index_code": "000300.SH", "drawdown_20d": -0.041, "is_systemic": false},
  "weak_hands": {
    "product_count": 3,
    "net_action_pp": -2.1,
    "products": [{"product_code": "P001", "credibility": 0.42, "delta_weight_pp": -0.8}]
  },
  "strong_hands": {
    "product_count": 2,
    "net_action_pp": 0.8,
    "products": [{"product_code": "P101", "credibility": 0.82, "intent": "HEAVY", "delta_weight_pp": 0.5}]
  },
  "data_quality": {"position_coverage": 0.96, "sector_mapping_coverage": 0.99}
}
```

#### 3.1.6 history_win_rate
`history_win_rate` 是同类事件在历史窗口内的胜率，用于展示而非直接替代当前置信度。

| 字段 | 定义 |
|---|---|
| `history_window_months` | 默认 36 个月 |
| `history_sample_count` | 满足相同 sector/event_type/confidence_bucket 的事件数量 |
| `win_definition` | 事件后 60 日行业相对沪深300超额收益 > 0 |
| `history_win_rate` | win_count / sample_count |
| `history_median_excess_return_60d` | 同类事件 60 日超额收益中位数 |
| `history_reliability` | sample_count < 5 为 LOW，5-20 为 MEDIUM，>20 为 HIGH |

样本不足时：`history_win_rate=null`，WebUI 显示“历史样本不足”，不得用 0% 或 50% 代填。

### 3.2 共识方向引擎
#### 3.2.1 概念定义
共识方向引擎用于回答：多产品对同一股票是否形成同向判断，以及这个共识是否因为过度拥挤而需要打折。它聚合 Phase 2 的 `argus_signal` 和 Phase 3 的规则引擎输出，生成单股维度的 `consensus_score`。

#### 3.2.2 输入信号标准化
每个产品对股票的信号先转换为标准方向权重：

| 输入 | direction | base_direction_weight |
|---|---|---|
| BUY / ADD / INCREASE | LONG | +1.0 |
| SELL / REDUCE | SHORT | -1.0 |
| HOLD / NO_CHANGE | FLAT | 0.0 |
| HEAVY BUY | LONG | +1.3 |
| PROBE BUY | LONG | +0.6 |
| SEQUENTIAL BUY | LONG | +1.2 |

产品信誉作为乘数：`weighted_direction = base_direction_weight * credibility_score`。

#### 3.2.3 direction_weight
`direction_weight` 表示同一股票跨产品后的净方向：

```text
direction_weight = sum(weighted_direction_i * recency_decay_i) / sum(abs(weighted_direction_i) * recency_decay_i)
```

| direction_weight | consensus_direction |
|---|---|
| >= +0.30 | BULLISH |
| -0.30 到 +0.30 | NEUTRAL |
| <= -0.30 | BEARISH |

`recency_decay_i = exp(-days_since_signal / 20)`，默认半衰期约 14 个交易日。

#### 3.2.4 crowding_discount
拥挤度不是共识本身，而是共识可交易性的折扣。计算规则：

| crowding_zone | crowding_discount | 含义 |
|---|---:|---|
| SAFE | 1.00 | 共识未拥挤 |
| WATCH | 0.90 | 轻微拥挤 |
| DANGER | 0.65 | 过度拥挤，信号降权 |
| KILL | 0.35 | 拥挤过高，仅保留观察 |
| UNKNOWN | 0.80 | 数据不足，保守降权 |

#### 3.2.5 consensus_score
`consensus_score` 是方向一致性、产品质量、样本数量和拥挤折扣后的置信度：

```text
agreement = abs(direction_weight)
product_quality = weighted_avg(credibility_score, abs(base_direction_weight))
breadth = min(1.0, log1p(unique_product_count) / log1p(5))
freshness = weighted_avg(recency_decay, abs(weighted_direction))

raw_consensus = 0.35 * agreement
              + 0.30 * product_quality
              + 0.20 * breadth
              + 0.15 * freshness

consensus_score = raw_consensus * crowding_discount
```

输出字段：
| 字段 | 类型 | 说明 |
|---|---|---|
| `consensus_direction` | Enum | BULLISH / BEARISH / NEUTRAL |
| `consensus_score` | Float | 0-1，拥挤折扣后的最终分数 |
| `direction_weight` | Float | -1 到 +1，净方向 |
| `crowding_discount` | Float | 0-1，拥挤折扣 |
| `unique_product_count` | Int | 参与产品数 |
| `high_credibility_count` | Int | credibility >= 0.70 的产品数 |
| `contradiction_count` | Int | 与主方向相反的产品数 |
| `evidence` | Object | 产品贡献明细 |

#### 3.2.6 判定规则
| 条件 | 输出 |
|---|---|
| `unique_product_count < 2` | `consensus_direction=NEUTRAL`, `consensus_score<=0.40` |
| `contradiction_count >= high_credibility_count` | 强制降为 `NEUTRAL` 或 `LOW_CONFIDENCE` |
| `crowding_zone=KILL` | `consensus_score *= 0.35`，WebUI 显示拥挤警示 |
| `consensus_score >= 0.70` 且 `direction=BULLISH` | 可作为 CANDIDATE/CONVICTION 的正向证据 |
| `consensus_score >= 0.70` 且 `direction=BEARISH` | 作为降级或风险提示证据 |

### 3.3 Munger Checklist
#### 3.3.1 设计定位
Munger Checklist 是 Phase 4 的最终机会评估层。它不追求复杂加权总分，而是用 5 个等权问题汇总“质量、管理层、成长空间、估值、强手信号”五类证据。每项输出 `YES/NO/UNKNOWN`，并保留证据。

#### 3.3.2 5 项定义
| 项 | 名称 | 核心问题 | 数据来源 |
|---|---|---|---|
| Q1 | 护城河（Moat） | 公司是否具备可持续竞争优势或行业龙头特征？ | 行业分类、财务质量因子、毛利率/ROE 分位、人工标签 |
| Q2 | 管理层（Management） | 管理层是否稳定、资本配置是否可信？ | 公司治理数据、公告事件、分红/回购/股权激励、人工标签 |
| Q3 | 成长空间（Growth Runway） | 行业和公司是否仍有足够增长空间？ | 营收/利润增速、行业景气度、分析师一致预期、主题集群 |
| Q4 | 估值（Valuation） | 当前估值是否未透支增长预期？ | PE/PB/PS/EV-EBITDA 分位、PEG、历史分位 |
| Q5 | 强手信号（Strong Hand Signal） | 高信誉产品是否在买入、坚守，且无明显拥挤或矛盾卖出？ | Darwin、Consensus、Argus signals、crowding_zone |

#### 3.3.3 评分规则
每项 checklist 输出：
| answer | score | 规则 |
|---|---:|---|
| YES | 1.0 | 数据支持该项为正向证据 |
| UNKNOWN | 0.5 | 数据不足或证据混合 |
| NO | 0.0 | 数据明确不支持或存在反向证据 |

总分：
```text
checklist_score = sum(item_score) / 5
checklist_yes_count = count(answer == YES)
```

分层：
| checklist_score | verdict | 含义 |
|---|---|---|
| >= 0.80 且 Q5=YES | STRONG_OPPORTUNITY | 机会质量高，适合进入深度研究或 IC 讨论 |
| 0.60-0.80 | WATCH_CLOSELY | 有多项正向证据，但仍需补充关键确认 |
| 0.40-0.60 | MIXED | 证据混合，仅观察 |
| < 0.40 | REJECT | 暂不构成机会 |
| 任一关键数据质量低 | INSUFFICIENT_DATA | 数据不足，禁止给出强判断 |

#### 3.3.4 单项判定建议
| 项 | YES 示例规则 | NO 示例规则 |
|---|---|---|
| Q1 护城河 | ROE/毛利率处于行业前 30%，或人工标注为龙头/平台型公司 | 财务质量行业后 40%，且无人工正向标签 |
| Q2 管理层 | 无重大治理负面，分红/回购/激励记录稳定 | 重大治理风险、财务造假、频繁高管异常变动 |
| Q3 成长空间 | 行业景气度 BULLISH，收入/利润增速高于行业中位数 | 行业景气度 DEFENSIVE/衰退，增长持续低于行业 |
| Q4 估值 | 估值低于自身 5 年 60% 分位，且 PEG 合理 | 估值处于 90% 以上分位且盈利下修 |
| Q5 强手信号 | consensus_score >= 0.65，或 90 日内所在行业有 Darwin 事件且强手加仓 | 高信誉产品卖出、crowding_zone=KILL 或 consensus_direction=BEARISH |

#### 3.3.5 verdict 输出规范
`verdict` 必须同时包含机器可读枚举和人类可读解释：

```json
{
  "verdict": "WATCH_CLOSELY",
  "verdict_reason": "5项中3项为YES；强手信号明确，但估值处于历史较高分位，需等待估值或业绩确认。",
  "checklist_score": 0.7,
  "yes_count": 3,
  "unknown_count": 1,
  "no_count": 1
}
```

## 4. 数据模型：MongoDB Schema
### 4.1 集合定义
| 项 | 值 |
|---|---|
| Database | `tradingagents` |
| Collection | `08_research_argus_deep_analysis` |
| 写入方 | Argus Phase 4 深度分析任务 |
| 读取方 | Argus WebUI、Portfolio research view、Phase 5 backtest |
| 粒度 | `analysis_date + wind_code` 单股单日一条主记录，行业级 Darwin 事件可作为 `scope=SECTOR` 记录 |
| 唯一键 | `analysis_date + scope + wind_code + sector_code`，其中 STOCK 记录要求 `wind_code` 非空 |

### 4.2 Document Schema
```json
{
  "_id": "ObjectId",
  "schema_version": "1.0.0",
  "analysis_id": "argus-deep-20260519-603799.SH",
  "analysis_date": "2026-05-19",
  "scope": "STOCK | SECTOR",
  "wind_code": "603799.SH",
  "stock_name": "华友钴业",
  "sector_code": "801050.SI",
  "sector_name": "有色金属",
  "pool_zone": "SCAN | WATCH | CANDIDATE | CONVICTION | ARCHIVE | NONE",

  "darwin": {
    "darwin_signal": true,
    "event_types": ["SECTOR_DRAWDOWN", "WEAK_HAND_EXIT", "STRONG_HAND_ADD"],
    "confidence": 0.74,
    "confidence_level": "HIGH | MEDIUM | LOW | INSUFFICIENT",
    "strength": 0.68,
    "trigger_date": "2026-05-19",
    "lookback_days": 20,
    "sector_drawdown_20d": -0.123,
    "market_drawdown_20d": -0.041,
    "is_systemic": false,
    "weak_net_action_pp": -2.1,
    "strong_net_action_pp": 0.8,
    "strong_add_count": 2,
    "history_win_rate": 0.67,
    "history_sample_count": 6,
    "history_window_months": 36,
    "history_median_excess_return_60d": 0.052,
    "history_reliability": "LOW | MEDIUM | HIGH",
    "evidence": {}
  },

  "consensus": {
    "consensus_direction": "BULLISH | BEARISH | NEUTRAL",
    "consensus_score": 0.72,
    "direction_weight": 0.64,
    "crowding_zone": "SAFE | WATCH | DANGER | KILL | UNKNOWN",
    "crowding_discount": 1.0,
    "unique_product_count": 4,
    "high_credibility_count": 2,
    "contradiction_count": 1,
    "freshness": 0.83,
    "agreement": 0.64,
    "product_quality": 0.76,
    "evidence": {
      "contributing_products": [
        {
          "product_code": "P101",
          "product_name": "示例产品",
          "signal_date": "2026-05-18",
          "direction": "LONG",
          "intent": "HEAVY",
          "credibility_score": 0.82,
          "direction_contribution": 1.066
        }
      ]
    }
  },

  "munger_checklist": {
    "checklist_version": "phase4-v1",
    "items": [
      {"key": "moat", "label": "护城河", "answer": "YES", "score": 1.0, "evidence": ["ROE 处于行业前30%"], "data_quality": "HIGH"},
      {"key": "management", "label": "管理层", "answer": "UNKNOWN", "score": 0.5, "evidence": ["治理数据暂未接入"], "data_quality": "LOW"},
      {"key": "growth_runway", "label": "成长空间", "answer": "YES", "score": 1.0, "evidence": ["行业景气度 BULLISH"], "data_quality": "MEDIUM"},
      {"key": "valuation", "label": "估值", "answer": "NO", "score": 0.0, "evidence": ["PE 位于5年90%分位以上"], "data_quality": "MEDIUM"},
      {"key": "strong_hand_signal", "label": "强手信号", "answer": "YES", "score": 1.0, "evidence": ["consensus_score=0.72"], "data_quality": "HIGH"}
    ],
    "checklist_score": 0.7,
    "yes_count": 3,
    "unknown_count": 1,
    "no_count": 1,
    "verdict": "WATCH_CLOSELY",
    "verdict_reason": "强手信号明确，但估值偏贵且管理层数据不足。"
  },

  "phase_links": {
    "source_signal_ids": ["uuid-v4"],
    "source_rule_ids": ["rule-001"],
    "portfolio_ingest_ids": [],
    "backtest_event_id": null
  },

  "outcome_tracking": {
    "status": "PENDING | MATURED",
    "return_30d": null,
    "excess_return_30d": null,
    "return_60d": null,
    "excess_return_60d": null,
    "return_90d": null,
    "excess_return_90d": null,
    "outcome_tag": "WIN | LOSS | NEUTRAL | PENDING"
  },

  "data_quality": {
    "overall_score": 0.88,
    "position_coverage": 0.96,
    "trade_coverage": 0.91,
    "sector_mapping_coverage": 0.99,
    "price_coverage": 0.95,
    "warnings": []
  },

  "created_at": "2026-05-19T21:50:00+08:00",
  "updated_at": "2026-05-19T21:50:00+08:00",
  "created_by": "argus_phase4"
}
```

### 4.3 字段约束
| 字段 | 约束 |
|---|---|
| `analysis_date` | 必填，YYYY-MM-DD |
| `scope` | 必填，枚举：STOCK / SECTOR |
| `wind_code` | `scope=STOCK` 时必填 |
| `sector_code` | 必填；个股记录来自行业映射，行业记录为事件行业 |
| `darwin.confidence` | 0-1 |
| `consensus.consensus_score` | 0-1 |
| `consensus.direction_weight` | -1 到 1 |
| `munger_checklist.items` | 必须包含 5 项，key 固定 |
| `munger_checklist.verdict` | STRONG_OPPORTUNITY / WATCH_CLOSELY / MIXED / REJECT / INSUFFICIENT_DATA |
| `data_quality.overall_score` | 0-1 |

### 4.4 索引建议
```javascript
db["08_research_argus_deep_analysis"].createIndex(
  { analysis_date: -1, scope: 1, wind_code: 1, sector_code: 1 },
  { unique: true, name: "uk_deep_analysis_daily_target" }
)

db["08_research_argus_deep_analysis"].createIndex(
  { wind_code: 1, analysis_date: -1 },
  { name: "idx_deep_analysis_stock_date" }
)

db["08_research_argus_deep_analysis"].createIndex(
  { sector_code: 1, "darwin.trigger_date": -1 },
  { name: "idx_deep_analysis_sector_darwin" }
)

db["08_research_argus_deep_analysis"].createIndex(
  { "consensus.consensus_score": -1, analysis_date: -1 },
  { name: "idx_deep_analysis_consensus_score" }
)

db["08_research_argus_deep_analysis"].createIndex(
  { "munger_checklist.verdict": 1, "munger_checklist.checklist_score": -1 },
  { name: "idx_deep_analysis_checklist" }
)
```

## 5. 接口设计：Python API 签名
### 5.1 DarwinDetector
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Mapping, Sequence

DarwinEventType = Literal[
    "SECTOR_DRAWDOWN", "WEAK_HAND_EXIT", "STRONG_HAND_HOLD",
    "STRONG_HAND_ADD", "CROWDING_REVERSAL", "SYSTEMIC_STRESS",
]
ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]

@dataclass(frozen=True)
class DarwinEvent:
    analysis_date: date
    sector_code: str
    sector_name: str
    event_types: list[DarwinEventType]
    confidence: float
    confidence_level: ConfidenceLevel
    strength: float
    sector_drawdown_20d: float
    market_drawdown_20d: float | None
    is_systemic: bool
    weak_net_action_pp: float
    strong_net_action_pp: float
    strong_add_count: int
    history_win_rate: float | None
    history_sample_count: int
    history_reliability: Literal["LOW", "MEDIUM", "HIGH"]
    evidence: dict

class DarwinDetector:
    """Detect sector-level Darwin moments from Argus product behavior."""

    def __init__(
        self,
        mongo_client,
        database: str = "tradingagents",
        position_collection: str = "portfolio_position",
        trade_collection: str = "portfolio_trade",
        product_profile_collection: str = "08_research_argus_product_profile",
        deep_analysis_collection: str = "08_research_argus_deep_analysis",
        sector_drawdown_threshold: float = -0.10,
        market_systemic_threshold: float = -0.08,
        weak_credibility_threshold: float = 0.50,
        strong_credibility_threshold: float = 0.70,
    ) -> None:
        ...

    def detect(
        self,
        analysis_date: date,
        sector_code: str | None = None,
        lookback_days: int = 20,
        history_window_months: int = 36,
        persist: bool = False,
    ) -> list[DarwinEvent]:
        """Detect Darwin events for all sectors or one sector."""

    def detect_for_stock(
        self,
        wind_code: str,
        analysis_date: date,
        lookback_days: int = 20,
        history_window_months: int = 36,
    ) -> DarwinEvent | None:
        """Return the latest sector Darwin event relevant to a stock."""

    def calculate_history_win_rate(
        self,
        sector_code: str,
        event_types: Sequence[DarwinEventType],
        as_of_date: date,
        window_months: int = 36,
        horizon_days: int = 60,
    ) -> Mapping[str, float | int | str | None]:
        """Calculate historical win rate for comparable Darwin events."""

    def to_document(self, event: DarwinEvent) -> dict:
        """Convert DarwinEvent to the darwin sub-document for MongoDB."""
```

### 5.2 ConsensusEngine
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Sequence

ConsensusDirection = Literal["BULLISH", "BEARISH", "NEUTRAL"]
CrowdingZone = Literal["SAFE", "WATCH", "DANGER", "KILL", "UNKNOWN"]

@dataclass(frozen=True)
class ProductSignalContribution:
    product_code: str
    product_name: str | None
    signal_id: str
    signal_date: date
    direction: Literal["LONG", "SHORT", "FLAT"]
    intent: str | None
    credibility_score: float
    base_direction_weight: float
    recency_decay: float
    direction_contribution: float

@dataclass(frozen=True)
class ConsensusResult:
    wind_code: str
    stock_name: str | None
    analysis_date: date
    consensus_direction: ConsensusDirection
    consensus_score: float
    direction_weight: float
    crowding_zone: CrowdingZone
    crowding_discount: float
    unique_product_count: int
    high_credibility_count: int
    contradiction_count: int
    agreement: float
    product_quality: float
    freshness: float
    evidence: dict

class ConsensusEngine:
    """Calculate stock-level consensus direction across products."""

    def __init__(
        self,
        mongo_client,
        database: str = "tradingagents",
        signal_collection: str = "08_research_argus_signal",
        product_profile_collection: str = "08_research_argus_product_profile",
        stock_pool_collection: str = "08_research_argus_stock_pool",
        deep_analysis_collection: str = "08_research_argus_deep_analysis",
        recency_halflife_days: int = 14,
        min_products: int = 2,
    ) -> None:
        ...

    def calculate_for_stock(
        self, wind_code: str, analysis_date: date, lookback_days: int = 30, persist: bool = False
    ) -> ConsensusResult:
        """Calculate consensus for one stock."""

    def calculate_batch(
        self,
        analysis_date: date,
        wind_codes: Sequence[str] | None = None,
        lookback_days: int = 30,
        min_consensus_score: float | None = None,
        persist: bool = False,
    ) -> list[ConsensusResult]:
        """Calculate consensus for a stock universe."""

    def normalize_signal_direction(self, signal: dict, wind_code: str) -> ProductSignalContribution:
        """Normalize one Argus signal into a signed product contribution."""

    def calculate_crowding_discount(self, crowding_zone: CrowdingZone) -> float:
        """Return crowding discount by zone."""

    def to_document(self, result: ConsensusResult) -> dict:
        """Convert ConsensusResult to the consensus sub-document for MongoDB."""
```

### 5.3 MungerChecklistEvaluator
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Mapping

ChecklistAnswer = Literal["YES", "NO", "UNKNOWN"]
ChecklistVerdict = Literal[
    "STRONG_OPPORTUNITY", "WATCH_CLOSELY", "MIXED", "REJECT", "INSUFFICIENT_DATA",
]
DataQuality = Literal["HIGH", "MEDIUM", "LOW"]

@dataclass(frozen=True)
class ChecklistItem:
    key: Literal["moat", "management", "growth_runway", "valuation", "strong_hand_signal"]
    label: str
    answer: ChecklistAnswer
    score: float
    evidence: list[str]
    data_quality: DataQuality

@dataclass(frozen=True)
class MungerChecklistResult:
    wind_code: str
    stock_name: str | None
    analysis_date: date
    items: list[ChecklistItem]
    checklist_score: float
    yes_count: int
    unknown_count: int
    no_count: int
    verdict: ChecklistVerdict
    verdict_reason: str

class MungerChecklistEvaluator:
    """Evaluate stock opportunity quality with an equal-weight 5-item checklist."""

    def __init__(
        self,
        mongo_client,
        database: str = "tradingagents",
        deep_analysis_collection: str = "08_research_argus_deep_analysis",
        fundamentals_collection: str | None = None,
        valuation_collection: str | None = None,
        governance_collection: str | None = None,
    ) -> None:
        ...

    def evaluate(
        self,
        wind_code: str,
        analysis_date: date,
        darwin: Mapping | None = None,
        consensus: Mapping | None = None,
        persist: bool = False,
    ) -> MungerChecklistResult:
        """Evaluate all 5 checklist items for one stock."""

    def evaluate_batch(
        self,
        analysis_date: date,
        wind_codes: list[str] | None = None,
        pool_zones: list[str] | None = None,
        persist: bool = False,
    ) -> list[MungerChecklistResult]:
        """Evaluate checklist for candidate stocks or an explicit universe."""

    def evaluate_moat(self, wind_code: str, analysis_date: date) -> ChecklistItem:
        """Evaluate sustainable competitive advantage."""

    def evaluate_management(self, wind_code: str, analysis_date: date) -> ChecklistItem:
        """Evaluate management and governance quality."""

    def evaluate_growth_runway(self, wind_code: str, analysis_date: date) -> ChecklistItem:
        """Evaluate growth runway and industry prosperity."""

    def evaluate_valuation(self, wind_code: str, analysis_date: date) -> ChecklistItem:
        """Evaluate valuation reasonableness."""

    def evaluate_strong_hand_signal(
        self,
        wind_code: str,
        analysis_date: date,
        darwin: Mapping | None,
        consensus: Mapping | None,
    ) -> ChecklistItem:
        """Evaluate Argus strong-hand evidence."""

    def make_verdict(self, items: list[ChecklistItem]) -> tuple[ChecklistVerdict, str]:
        """Convert item scores into final verdict and explanation."""

    def to_document(self, result: MungerChecklistResult) -> dict:
        """Convert checklist result to the munger_checklist sub-document for MongoDB."""
```

### 5.4 编排接口
```python
class DeepAnalysisService:
    """Orchestrate Darwin, consensus and checklist analysis."""

    def run_for_stock(
        self,
        wind_code: str,
        analysis_date: date,
        persist: bool = True,
    ) -> dict:
        """Generate one stock-level deep analysis document."""

    def run_daily(
        self,
        analysis_date: date,
        universe: list[str] | None = None,
        persist: bool = True,
    ) -> list[dict]:
        """Generate daily deep analysis documents for pool stocks."""
```

## 6. WebUI 规格
### 6.1 页面入口
| 页面 | URL | 说明 |
|---|---|---|
| 深度分析页 | `/analysis` | Phase 4 主页面，聚合 Darwin、共识方向、Munger Checklist |
| 个股详情页 | `/stocks/{wind_code}` | 嵌入单股 deep analysis 摘要 |
| API | `GET /api/v1/argus/deep-analysis` | 按日期、股票、行业、verdict 查询 |
| API | `GET /api/v1/argus/deep-analysis/{wind_code}` | 查询单股最新深度分析 |

### 6.2 `/analysis` 页面布局
采用 RFC-2026-071_ARGUS/05_POOL_WEB 的 D Hybrid Layout：主内容区 75%，右侧边栏 25%。

```text
┌───────────────────────────────────────────────────────────┐
│ nav: ARGUS 百目巨人 | 仪表盘 信号 股票池 产品 分析 回测 设置 │
├───────────────────────────────────────────────────────────┤
│ main                                                      │
│  A. Darwin 时刻                                           │
│  B. 共识方向引擎                                          │
│  C. Munger Checklist 机会卡片                             │
│                                                           │
│ aside                                                     │
│  筛选器：日期/行业/池区/verdict/confidence                 │
│  数据健康：覆盖率/样本数/最新更新时间                       │
│  风险提示：系统性下跌/拥挤/样本不足                         │
└───────────────────────────────────────────────────────────┘
```

### 6.3 组件说明
#### A. Darwin 时刻卡片
展示行业级事件，按 confidence 降序。

字段：
- 行业名称、触发日期、event_type badges
- 行业 20 日回撤、沪深300 20 日回撤
- 弱手净行为、强手净行为、强手加仓产品数
- confidence、history_win_rate、history_sample_count
- 系统性风险提示
- 操作：查看涉及标的、查看历史事件

#### B. 共识方向面板
展示股票级共识结果。

组件：
- 共识排行榜：`wind_code`、股票名、pool_zone、consensus_direction、consensus_score、direction_weight、crowding_discount
- 方向条：从 BEARISH 到 BULLISH 的水平条，标记 `direction_weight`
- 产品贡献展开行：展示 contributing_products 和 contradiction_count
- 拥挤警示：DANGER/KILL 用风险色，但不隐藏记录

#### C. Munger Checklist 机会卡片
展示 CANDIDATE/CONVICTION 和高 `consensus_score` 股票。

卡片字段：
- 股票代码、名称、池区、verdict
- 5 项 checklist，使用 YES/NO/UNKNOWN 状态
- checklist_score、yes_count、verdict_reason
- 数据质量提示
- 链接：进入 `/stocks/{wind_code}`

示例：
```text
华友钴业 603799.SH | CANDIDATE | WATCH_CLOSELY
[YES] 护城河        ROE/毛利率行业前列
[UNKNOWN] 管理层    治理数据未接入
[YES] 成长空间      行业景气度 BULLISH
[NO] 估值           PE 位于5年90%分位
[YES] 强手信号      consensus_score=0.72，强手加仓2个产品
Checklist: 3.5/5 | 结论：强手信号明确，但估值偏贵
```

### 6.4 筛选与排序
| 控件 | 规则 |
|---|---|
| 日期选择 | 默认最新 analysis_date |
| 行业筛选 | 支持申万一级行业 |
| 池区筛选 | SCAN/WATCH/CANDIDATE/CONVICTION |
| verdict 筛选 | STRONG_OPPORTUNITY/WATCH_CLOSELY/MIXED/REJECT/INSUFFICIENT_DATA |
| confidence 筛选 | Darwin confidence >= 阈值 |
| 排序 | 默认 `munger_checklist.checklist_score desc, consensus.consensus_score desc` |

### 6.5 交互和降级
- 页面只读，不提供直接买卖、调仓或写 Portfolio 的按钮。
- 数据为空时显示“暂无深度分析结果”，并显示最近一次 Phase 4 任务状态。
- 样本不足不隐藏，必须展示 `history_sample_count` 和 `history_reliability`。
- `data_quality.overall_score < 0.60` 时，卡片顶部显示数据质量警示。

## 7. 与其他 Phase 的关系
### 7.1 数据流
```text
Phase 1 CRUD
  提供 portfolio_position / portfolio_trade / product profile 基础读写
      ↓
Phase 2 Signal Interface
  生成 08_research_argus_signal，完成 Argus -> Portfolio 标准信号
      ↓
Phase 3 Rule Engine
  自动执行入池、升降级、拥挤、矛盾信号等规则
      ↓
Phase 4 Deep Analysis
  对单股和行业生成 Darwin / Consensus / Munger Checklist 分析
      ↓
Phase 5 Backtest
  使用 deep_analysis 的事件样本和 outcome_tracking 验证胜率、超额收益和失效模式
```

### 7.2 Phase 2 信号到 Phase 4 分析
| Phase 2 字段 | Phase 4 用途 |
|---|---|
| `signal_type` | 转换为 LONG/SHORT/FLAT 方向 |
| `confidence` | 作为产品信号强度输入 |
| `target_stocks` | 聚合单股共识 |
| `metadata.credibility_score` | 共识方向权重和强手定义 |
| `metadata.pool_zone` | Munger Checklist 和 WebUI 筛选 |
| `metadata.crowding_level` | crowding_discount |

### 7.3 Phase 4 到 Phase 5 回测
Phase 4 必须写入以下回测必要字段：
- `analysis_date`
- `wind_code`
- `sector_code`
- `darwin.event_types`
- `darwin.confidence`
- `consensus.consensus_direction`
- `consensus.consensus_score`
- `munger_checklist.verdict`
- `munger_checklist.checklist_score`
- `outcome_tracking`

Phase 5 负责回填：
- `return_30d/60d/90d`
- `excess_return_30d/60d/90d`
- `outcome_tag`
- 按 event_type、verdict、confidence bucket 统计胜率和收益分布。

### 7.4 模块边界
| 模块 | 权责 |
|---|---|
| Argus Phase 4 | 生成研究判断和证据，不做组合权重 |
| Portfolio | 决定是否消费信号、如何进入股票池或组合 |
| Strategy | 使用 Phase 4 样本开发可回测策略 |
| Risk | 对拥挤、系统性风险和行业集中度做独立限制 |
| WebUI | 只读展示和筛选，不绕过后端规则写入决策 |

## 8. 验收标准
### 8.1 Darwin 时刻检测验收用例
| 用例ID | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| DA-001 | 行业回调不足 | sector_drawdown_20d=-8% | 不输出有效 Darwin 事件 |
| DA-002 | 行业回调 + 弱手退出 + 强手加仓 | sector_drawdown_20d=-12%，weak_net_action<0，strong_net_action>0 | 输出 `SECTOR_DRAWDOWN/WEAK_HAND_EXIT/STRONG_HAND_ADD`，confidence > 0 |
| DA-003 | 系统性下跌 | market_drawdown_20d=-10% | event_types 包含 `SYSTEMIC_STRESS`，confidence 打 0.70 折 |
| DA-004 | 强手产品数量不足 | strong_product_count=1 | 输出 LOW 或 MEDIUM，触发 sample_penalty |
| DA-005 | 历史样本不足 | comparable events < 5 | `history_win_rate=null` 或 reliability=LOW，WebUI 不显示伪精确胜率 |
| DA-006 | 证据可追溯 | 任意有效事件 | `evidence.weak_hands.products` 和 `evidence.strong_hands.products` 非空 |

### 8.2 共识方向引擎验收用例
| 用例ID | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| CE-001 | 单产品信号 | 仅 1 个产品 BUY | `consensus_direction=NEUTRAL` 或 `consensus_score<=0.40` |
| CE-002 | 多产品同向买入 | 3 个高信誉产品 BUY | `BULLISH`，`direction_weight>0.30`，`consensus_score>=0.65` |
| CE-003 | 高信誉矛盾卖出 | 2 BUY + 2 高信誉 SELL | `contradiction_count>=2`，共识降为 NEUTRAL 或分数显著降低 |
| CE-004 | 拥挤 KILL | BULLISH 但 `crowding_zone=KILL` | `crowding_discount=0.35`，WebUI 显示拥挤警示 |
| CE-005 | 时效衰减 | 30 天前信号 vs 当日信号 | 旧信号贡献低于新信号 |
| CE-006 | 贡献明细 | 任意共识输出 | `evidence.contributing_products` 包含 product_code、credibility、direction_contribution |

### 8.3 Munger Checklist 验收用例
| 用例ID | 场景 | 输入 | 期望结果 |
|---|---|---|---|
| MC-001 | 五项齐全 | 基本面、估值、Argus 数据均存在 | 输出 5 个固定 key 的 checklist items |
| MC-002 | 数据不足 | governance 数据未接入 | management 项为 UNKNOWN，score=0.5，data_quality=LOW |
| MC-003 | 强机会 | 4 项 YES 且 strong_hand_signal=YES | verdict=STRONG_OPPORTUNITY |
| MC-004 | 估值否决但信号强 | Q5=YES，valuation=NO | verdict 不高于 WATCH_CLOSELY，verdict_reason 提示估值风险 |
| MC-005 | 强手负信号 | consensus_direction=BEARISH 或 KILL | strong_hand_signal=NO |
| MC-006 | 可解释输出 | 任意 checklist | 每项 evidence 至少 1 条，verdict_reason 非空 |

### 8.4 MongoDB Schema 验收用例
| 用例ID | 场景 | 期望结果 |
|---|---|---|
| DB-001 | upsert 单股深度分析 | `analysis_date + scope + wind_code + sector_code` 唯一，不重复插入 |
| DB-002 | 字段范围校验 | confidence、consensus_score、checklist_score 均在 0-1 |
| DB-003 | 查询最新单股分析 | `wind_code + analysis_date desc` 索引可命中 |
| DB-004 | 查询高分机会 | `munger_checklist.verdict + checklist_score` 索引可命中 |
| DB-005 | outcome 回填 | Phase 5 可按 `analysis_id` 更新 outcome_tracking，不改写原始 evidence |

### 8.5 WebUI 验收用例
| 用例ID | 场景 | 期望结果 |
|---|---|---|
| UI-001 | 打开 `/analysis` | 默认展示最新 analysis_date 的三大模块 |
| UI-002 | Darwin 卡片 | 显示 event_type、confidence、history_win_rate 或样本不足 |
| UI-003 | 共识面板 | 支持按 consensus_score 排序，展开贡献产品 |
| UI-004 | Checklist 卡片 | 显示 5 项 YES/NO/UNKNOWN 和 verdict_reason |
| UI-005 | 数据质量低 | `overall_score<0.60` 时显示警示 |
| UI-006 | 只读约束 | 页面无直接交易、调仓或写 portfolio 的按钮 |

## 9. 风险与限制
### 9.1 置信度不足
- 多产品同向不等于正确，只代表机构行为一致。
- `consensus_score` 是研究置信度，不是收益概率。
- 强手信誉来自历史行为，可能在风格漂移或市场 regime change 中失效。

缓解：
- 明确展示 product_count、contradiction_count 和 evidence。
- Phase 5 必须按时间窗口回测分层胜率。
- WebUI 不允许隐藏失败案例和低置信记录。

### 9.2 历史数据稀疏
Darwin 事件年均触发次数有限，按行业和事件类型切分后样本可能很少。样本不足时强行给胜率会制造虚假确定性。

缓解：
- `history_sample_count < 5` 时显示样本不足。
- history_win_rate 不作为 confidence 的硬输入，只作为展示和后续校准。
- Phase 5 使用滚动窗口和置信区间，而非单点胜率。

### 9.3 行业映射误差
股票行业分类、产品持仓行业聚合可能因行业映射缺失或变化而偏离真实暴露。

缓解：
- 保存 `sector_mapping_coverage`。
- 行业映射低于阈值时降低 `data_quality_factor`。
- 保留映射版本，便于回测复现。

### 9.4 拥挤信号的双重含义
拥挤可能代表强共识，也可能代表交易风险。Phase 4 使用 `crowding_discount` 降低可交易性置信度，但不否认基本面共识存在。

缓解：
- 分开展示 `direction_weight` 和 `crowding_discount`。
- KILL 区不删除记录，只降低分数并显示风险。

### 9.5 Munger Checklist 外部数据依赖
护城河、管理层、成长空间、估值需要财务、治理、估值数据。若外部数据未接入，Checklist 会出现 UNKNOWN 项。

缓解：
- UNKNOWN 计 0.5 且降低 data_quality。
- 首版允许 Q1-Q4 使用可替代数据或人工标签，但必须标注来源。
- Q5 强手信号可由 Argus 内部数据稳定生成。

### 9.6 非投资建议约束
Phase 4 输出是研究辅助，不是交易建议。任何 STRONG_OPPORTUNITY 都不能绕过 Portfolio、Risk 和人工 IC。

缓解：
- 文档、API 和 WebUI 使用“opportunity/research/view”语义，不使用“buy/sell recommendation”。
- 不提供下单按钮。
- 与 Portfolio 的写入仍通过 Phase 2/3 的标准接口和规则约束。

## 10. 非目标
- 不实现因果链检测和 Graphify 集成；二者保留为后续 Phase。
- 不直接修改 Portfolio 持仓或交易计划。
- 不以 LLM 替代确定性计算；LLM 只能用于解释摘要或 IC 文案。
- 不承诺 `verdict` 与未来收益单调对应，必须由 Phase 5 回测验证。

## 11. 交付清单
| 交付项 | 路径/接口 |
|---|---|
| RFC 文档 | `docs/rfc/08_research/argus/RFC-08-003-argus-advanced-analysis.md` |
| MongoDB 集合 | `tradingagents.08_research_argus_deep_analysis` |
| 核心类 | `DarwinDetector`, `ConsensusEngine`, `MungerChecklistEvaluator` |
| WebUI 页面 | `/analysis`, `/stocks/{wind_code}` deep analysis section |
| API | `GET /api/v1/argus/deep-analysis`, `GET /api/v1/argus/deep-analysis/{wind_code}` |
| 验收测试 | DA/CE/MC/DB/UI 用例集 |

