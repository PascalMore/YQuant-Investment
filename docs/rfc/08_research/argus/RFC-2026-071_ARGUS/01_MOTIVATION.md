---
file_id: ARGUS-01
title: "动机与系统身份"
rfc_id: RFC-2026-071
doc_status: "DRAFT"
approval_status: "NOT_SUBMITTED"
impl_status: "NOT_STARTED"
version: "2.0.0-draft"
created: "2026-04-12"
drafter: "Internal Review Board"
owner: "Internal Review Board"
depends_on:
  - "ARGUS-000 (INDEX)"
amendment_level: L2
---

# ARGUS-01: 动机与系统身份 {#ARGUS-01:root}

> **本文件为RFC-2026-071的第一章 (Normative)**。
> 包含四个主节: 1 动机 (Why), 2 系统身份 (What), 3 审议历程概要 (How it was validated), 4 核心设计决策摘要。

---

## 1 动机 (Motivation) {#ARGUS-01:motivation}

### 1.1 V8.1聪明钱处理链的三大缺陷 {#ARGUS-01:v81-deficiencies}

Empire V8.1已有聪明钱信号处理链 (`score_smart_money_batch.py` -> `batch_insert` -> `stock_pool_ops.py`), 但存在三个结构性缺陷:

| 编号 | 缺陷 | 当前状态 | 影响 |
|:--:|:--|:--|:--|
| DEF-1 | **无基金经理/产品身份追踪** | 只有聚合信号, 不知道谁在买 | 无法区分优质产品与噪声产品, 信号质量无法溯源 |
| DEF-2 | **固定4D评分 (0-20分)** | 无置信区间, 无衰减, 无学习能力 | 评分体系无法从历史结果自我修正, 长期精度衰减 |
| DEF-3 | **无行为分析** | 只看"买什么", 不看"怎么买" | 无法区分止盈卖出与恐慌卖出, 调仓路径信息丢失 |

**D1**: 三大缺陷的根源在于V8.1将聪明钱视为"聚合信号", 而非"产品级行为"。ARGUS从根本上改变范式: 先追踪产品, 再理解行为, 最后生成信号。

### 1.2 55份源文献的方法论储备 {#ARGUS-01:source-documents}

用户收集了**55份专业文档** (位于 `D:\Private Research OS\基金经理聪明钱交易跟踪\`), 涵盖:

| 领域 | 文档数 | 核心内容 |
|:--|:--:|:--|
| T-1交易分析 | 12 | 基金经理日内交易行为还原, 卖出质量评估, 建仓节奏 |
| 调仓路径跟踪 | 8 | 季报-年报持仓差异, 隐形重仓识别, HHI集中度跟踪 |
| 聪明钱因子构造 | 10 | NHC因子, 主动净买入, ETF份额-净值背离 |
| 拥挤度管理 | 9 | 四层穿透抑制, Hindenburg预兆, 行业/个股分级 |
| 北向资金与AH溢价 | 7 | 北向逐笔数据, 南向配置行为, AH溢价背离信号 |
| 多维跟踪框架 | 5 | 多时间框架融合, 贝叶斯更新, 动态股票池管理 |
| 经理/产品评价体系 | 4 | Active Share, 风格漂移检测, 信誉评估 |

55份文档蕴含的方法论远超V8.1处理能力。V8.1的聚合评分模型无法承载产品级追踪、多时间框架融合、拥挤度穿透等高级功能, 必须设计全新系统。

### 1.3 Graphify知识图谱发现 {#ARGUS-01:graphify-findings}

对55份源文献执行Graphify知识图谱分析, 产出 **150个概念节点 / 188条关系边 / 15个社区 (Louvain聚类)**。

#### God Nodes (超级连接节点)

| 排名 | 节点名称 | 连接边数 | 含义 |
|:--:|:--|:--:|:--|
| 1 | Dynamic Stock Pool Framework | 11 | 连接经理评价、信号融合、拥挤度、池管理、IC决策 |
| 2 | Multi-Dimensional Smart Money Framework | 9 | 连接T-1行为、北向资金、ETF背离、融资流、贝叶斯更新 |

**D2**: Dynamic Stock Pool Framework (11条边) 横跨5个社区, 证明"动态股票池"是连接多领域的枢纽, 要求完整子系统而非在V8.1上打补丁。

#### 关键社区映射

| 社区 | 核心主题 | 节点数 | 映射到ARGUS |
|:--:|:--|:--:|:--|
| C1 | 产品画像与信誉评估 | 18 | 产品信誉引擎 |
| C2 | 调仓路径与隐形重仓 | 14 | 调仓路径检测器 |
| C3 | 聪明钱因子与快信号 | 22 | 信号引擎 (FAST) |
| C4 | 北向资金与微观结构 | 16 | 信号引擎 (FAST/MEDIUM) |
| C5 | 季报持仓分析 | 12 | 信号引擎 (SLOW) |
| C6 | 贝叶斯融合与置信区间 | 10 | 贝叶斯融合 |
| C7 | 动态股票池管理 | 15 | 评分与池管理 |
| C8 | 拥挤度四层穿透 | 13 | 拥挤度集成 (Phase 2) |

15个社区中8个直接映射到ARGUS设计层次, 证明系统架构与源文献方法论高度吻合。

### 1.4 实战部署揭示的四个关键事实 {#ARGUS-01:deployment-facts}

RFC v1.0经TRIDENT审议通过后, 实战部署暴露了四个关键事实, 迫使架构重审:

| 编号 | 事实 | 影响 |
|:--:|:--|:--|
| F-1 | **ARGUS拥有独立数据源和生命周期** -- 跟踪基金产品(如"中欧1号-3.6e"), 数据频率为日度T+1, 与Empire"日线+季报"节奏完全不同 | 数据模型不兼容 |
| F-2 | **ARGUS的输出是情报而非指令** -- "这些顶级产品在买什么" vs "我们要不要买" | 情报盟友关系, 非上下级模块 |
| F-3 | **数据需要三层处理** -- Raw(原始) -> Processed(加工) -> Decision(决策), 嵌入empire_data.db让层界限模糊 | 数据治理困难 |
| F-4 | **独立部署带来运维优势** -- 自己的DB、自己的FastAPI、自己的config, 故障隔离, 独立迭代 | 运维解耦 |

---

## 2 系统身份 (System Identity) {#ARGUS-01:identity}

### 2.1 命名与定位 {#ARGUS-01:naming}

| 属性 | 值 |
|:--|:--|
| 英文名称 | **ARGUS** (Adaptive Rebalancing & General Underlying Surveillance) |
| 中文名称 | **百目巨人** -- 机构智慧资金行为追踪系统 |
| 设计哲学 | "Not what they bought, but how they think." |
| 系统定位 | **独立系统** -- 与Empire V9为"友邦" (Allied Nation) 关系, 非内部器官 |
| 数据库 | `argus.db` (独立SQLite, 非empire_data.db) |
| 数据频率 | 日度T+1全持仓 + 交易记录 + NAV |
| 跟踪维度 | 基金产品 (product), 产品名自带AUM编码 (如3.6e = 36亿) |

### 2.2 七大设计原则 {#ARGUS-01:principles}

| ID | 原则 | 英文 | 说明 |
|:--:|:--|:--|:--|
| AR-P1 | 行为优先于方向 | Behavior over Direction | 买不等于看多, 卖不等于看空, 高频不等于有技术 |
| AR-P2 | 产品优先于股票 | Product over Stock | 先建"优质产品池", 再建"优质股票池" |
| AR-P3 | 日更新周校准 | Daily Update, Weekly Calibration | 日度数据摄入 + 周度评分更新 + 信号校准 |
| AR-P4 | 贝叶斯怀疑 | Bayesian Skepticism | 所有评分带置信区间, Munger怀疑第一 |
| AR-P5 | 拥挤是引力 | Crowding is Gravity | 热信号压制而非放大, 与IL-11拥挤度集成 (Phase 2) |
| AR-P6 | 诚实信号审计 | Honest Signal Audit | 每个预测追踪到结果, 胜率/精度/假阳性率衰减信誉 |
| AR-P7 | 数据源分层信任 | Data Source Trust Hierarchy | T0(实时) > T1(日频) > T2(季报); 权重折扣: T0=1.0, T1=0.85, T2=0.70 |

> AR-P7为TRIDENT Round 3修订 REV-001 新增。快信号依赖T0实时数据, 慢信号依赖T2季报数据, 不区分信任层级会导致贝叶斯融合系统性高估滞后信号。

### 2.3 与Empire的关系定义 {#ARGUS-01:empire-relation}

```text
"友邦关系" (Allied Nations) -- 非 "内脏器官" (Internal Organ)

┌──────────────┐                    ┌──────────────┐
│   ARGUS      │   JSON + Claude    │   Empire V9  │
│   百目巨人    │ =================> │   Empire       │
│              │    情报输出         │              │
│  argus.db    │                    │ empire_data  │
│  :8001       │ <--- Claude读取 -->│  .db :8000   │
│              │    (矛盾检测)       │              │
└──────────────┘                    └──────────────┘
  独立进程                             独立进程
  独立数据库                           独立数据库
  独立config                          独立config
  可独立启停                           可独立启停
```

**关键约束**:
- Empire可以读取ARGUS输出 (JSON文件), 但**不能写入**ARGUS数据库
- ARGUS可以读取Empire持仓状态 (通过Claude bridge), 用于矛盾检测
- 两系统独立部署、独立启停, 一方故障不影响另一方运行

---

## 3 审议历程概要 {#ARGUS-01:review-summary}

### 3.1 Phase 1: 8席三叉戟审议 (v1.0) {#ARGUS-01:trident}

RFC v1.0经过8席专家的三轮审议:

| 席位 | 专家角色 | 代号 |
|:--:|:--|:--:|
| S1 | 量化系统架构师 | ARCH |
| S2 | 公募基金研究总监 | FUND |
| S3 | 另类数据/聪明钱因子研究员 | ALPHA |
| S4 | 风控与拥挤度专家 | RISK |
| S5 | 贝叶斯统计学家 | BAYES |
| S6 | A股微观结构研究员 | MICRO |
| S7 | 私募投资总监 | CIO |
| S8 | 软件工程/DevOps专家 | DEV |

**三轮结果**:

| 轮次 | 类型 | 结果 |
|:--:|:--|:--|
| Round 1 | 技术评审 | 0 HIGH / 5 MEDIUM / 3 LOW, 8项建议 |
| Round 2 | 替代方案对抗 | 5场辩论达成MODIFIED共识, DuckDB降级+KILL区调整 |
| Round 3 | 逐项表决 | 12组件全通过, 0 REJECT, 25项REV修订, 10项RISK |

最终评定: **APPROVED WITH MODIFICATIONS** (信心均值 7.6/10)

25项修订分布: P0 = 6项 (Phase A启动前) / P1 = 9项 (Phase A-B) / P2 = 10项 (Phase C-F)

### 3.2 Phase 2: 30席专家团重审 (v1 -> v2) {#ARGUS-01:expert-panel}

实战部署暴露架构定位偏差后, 召集30席专家团进行架构重审:

| 工作组 | 席数 | 核心职责 |
|:--|:--:|:--|
| WG1 数据库与存储 | 6 | 三层DB架构, 单库vs双库, DuckDB定位, Empire接口 |
| WG2 投资与评分 | 14 | 产品行为方法论, 五种风格产品视角, 信号质量, 诺贝尔经济学家审视 |
| WG3 系统工程 | 6 | 技术栈选型, MVP定义, 数据管道, 部署方案 |
| WG4 AI与智能 | 3 | Code/Claude边界, Daily workflow设计 |
| WG5 投资哲学终审 | 2 | 芒格逆向审查, 简化要求 |

WG2包含三位诺贝尔经济学奖得主:
- **Fama** (有效市场假说) -- 持续挑战alpha预测能力
- **Shiller** (行为金融) -- 支持narrative detection价值
- **Kahneman** (前景理论) -- 警告认知偏差与过度拟合

#### 全体表决

| 选项 | 票数 | 占比 |
|:--|:--:|:--:|
| A: Amendment (修订) | 1 | 3.4% |
| **B: Partial Restructure (部分重构)** | **26** | **89.7%** |
| C: Full Rewrite (全部重写) | 2 | 6.9% |
| D: Defer (延迟) | 0 | 0% |

**B路线以89.7%绝对多数通过**: 保留概念框架和评分方法论, 重写架构/数据库/集成方式。

### 3.3 Phase 3: 8席高级分析专家讨论 {#ARGUS-01:advanced-panel}

在v2基础架构确定后, 8席专题专家对六项高级分析功能进行可行性论证:

| 功能 | 裁决 | 说明 |
|:--|:--:|:--|
| 因果链 (Causal Chain) | V2 | Granger Causality, 需60+交易日数据积累 |
| Graphify知识图谱集成 | V2 | 降维+narrative detection, 需4-8周数据积累 |
| **达尔文时刻 (Darwin Moments)** | **V1** | 规则引擎, 检测高/低信誉产品分歧, 性价比最高 |
| 超级周期猜想 | RESEARCH | 信噪比未验证, 仅作观察面板 |
| **共识方向引擎** | **V1** | 景气度方向仪 + 信念偏移雷达 (盈利预期对齐延至V2) |
| **机会透镜 (Opportunity Lens)** | **V1** | Munger Checklist (3/5项), V2补全 |

---

## 4 核心设计决策摘要 {#ARGUS-01:decisions}

以下8项决策构成v2.0的设计基石, 每项均可溯源到具体辩论和表决:

### D-001: ARGUS为独立系统

| 属性 | 值 |
|:--|:--|
| 决策 | ARGUS独立部署, 拥有自己的数据库/进程/配置, 非Empire子模块 |
| 来源 | 全体表决 B路线 (89.7%), WG1/WG3/WG5共识 |
| 理由 | 独立数据源(日度T+1产品数据), 独立生命周期, 情报输出而非指令执行 |
| 影响 | 独立argus.db, 独立FastAPI进程, 独立端口, 独立config |

### D-002: 三层数据库架构

| 属性 | 值 |
|:--|:--|
| 决策 | Raw(只追加) -> Processed(可更新/可重算) -> Decision(评分/池) |
| 来源 | WG1 Debate WG1-A, DB-04提案 + DB-01/DB-06修订 |
| 理由 | Raw层不变性保证可审计性, Processed层解决数据质量, Decision层承载评分逻辑 |
| 影响 | 表命名前缀 `raw_` / `argus_` (Processed+Decision); 触发器保护层间不变性 |

### D-003: Day 1纯SQLite, DuckDB延迟到Day 2

| 属性 | 值 |
|:--|:--|
| 决策 | MVP阶段不引入DuckDB, 所有查询在SQLite执行 |
| 来源 | WG1 Debate WG1-B, DB-01/DB-02/DB-04共识 |
| 理由 | YAGNI -- top-5产品/日均数百行数据, SQLite窗口函数完全胜任 |
| 触发条件 | P95分析查询延迟 > 500ms, 或 raw表总行数 > 50K, 或 追踪产品 > 20个 |

### D-004: Empire接口 = JSON file + Claude bridge

| 属性 | 值 |
|:--|:--|
| 决策 | ARGUS输出recommendation JSON, Claude在roundtable中解读, 人类决定是否写入Empire |
| 来源 | WG1-C + WG3-C + WG4共识 |
| 理由 | 最低耦合; ARGUS输出是建议而非指令; friction is a feature (Kahneman) |
| 文件格式 | `argus_recommendation_YYYYMMDD.json` |

### D-005: 按产品跟踪, 非按经理

| 属性 | 值 |
|:--|:--|
| 决策 | 核心跟踪维度为基金产品 (product_code), 产品名自带AUM编码 |
| 来源 | WG2讨论, REV-026产品优先原则, 实战数据格式 |
| 理由 | 实际数据源以产品为单位; 同一经理可能管理多个风格不同的产品 |

### D-006: 日度T+1全持仓, 无需HF估算

| 属性 | 值 |
|:--|:--|
| 决策 | 每日获得完整持仓快照和交易记录, 不需要Kalman/Lasso高频估算 |
| 来源 | WG2 + 实战数据揭示 |
| 理由 | v1假设只有季报公开持仓, 需估算日内变化; v2已有日度全持仓, 估算层多余 |
| 影响 | argus_hf_estimate表降级为备用(fallback only) |

### D-007: 技术栈锁定

| 属性 | 值 |
|:--|:--|
| 决策 | Python 3.13 + FastAPI + Jinja2 + HTMX 2.0 + SQLite WAL + Pico CSS |
| 来源 | WG3 Debate WG3-B, 全组一致 |
| 理由 | 零外部服务依赖, 一键启动 (`python main.py`), 与Empire技术栈一致 |
| 排除 | Node.js, React, PostgreSQL, Docker, Streamlit, DuckDB (Day 1) |

### D-008: Code做计算, Claude做解读

| 属性 | 值 |
|:--|:--|
| 决策 | 确定性操作(导入/评分/池管理)由代码执行; 判断性操作(解读/roundtable/矛盾检测)由Claude执行 |
| 来源 | WG4 AI-01/AI-02共识 |
| 理由 | Steps 1-3(导入/处理/评分)可独立运行, 不依赖LLM; Steps 4-5(解读/报告)为增值层 |

---

**[存证]**
ARGUS-01 v2.0.0-draft | 2026-04-12
参考来源: V8.1 smart_money_roundtable.rules.md + 55份源文献 + Graphify图谱(150/188/15) + TRIDENT R1/R2/R3 (8席) + Expert Panel (30席) + Advanced Features Panel (8席)
重构要点: v1的三大缺陷论证保留; 新增实战部署四事实; 系统身份从Empire子模块改为独立友邦; 审议历程扩展至三阶段(三叉戟+专家团+高级分析); 8项核心决策全溯源
SOP完成: 启动-热场-参考-撰写-复查-收尾
