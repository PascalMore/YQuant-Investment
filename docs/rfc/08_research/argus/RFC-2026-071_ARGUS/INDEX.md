---
file_id: ARGUS-000
title: "RFC-2026-071 总控索引"
rfc_id: RFC-2026-071
doc_status: "APPROVED"
approval_status: "ACCEPTED"
impl_status: "PHASE_1_DRAFT"
version: "3.0.0"
created: "2026-04-12"
last_updated: "2026-04-22"
drafter: "Internal Review Board"
owner: "Internal Review Board"
depends_on: []
amendment_level: L2
profile: "technical-rfc"
---

# ARGUS-000: RFC-2026-071 装配总控索引 {#ARGUS-000:root}

> **ARGUS 百目巨人 -- 机构智慧资金行为追踪系统**
> Adaptive Rebalancing & General Underlying Surveillance
> "Not what they bought, but how they think."

---

## 0 v3.0 beta-light 修订说明 (2026-04-22, <sess>) {#ARGUS-000:v3-amendment}

> **本修订不废 DC-2026-013 决议** (v2.0.1 核心 schema + 7 原则 + 架构全票 APPROVED 仍有效).
> **仅修订数据入口机制 + Phase 1-2 实施路径**, v2.0.1 原文全部保留作历史承继.

### 0.1 v3.0 vs v2.0.1 差异总览

| 维度 | v2.0.1 (2026-04-12) | v3.0 (2026-04-22) | 变更原因 |
|:--|:--|:--|:--|
| Schema 13 表 | 全量设计 | **保留全量**, Phase 1 仅实装 3 Raw | user 数据量不够 (n<10 先验不稳定) |
| 数据入口 | Excel 全自动 (`import.py`) + Web upload | **Claude 桌面客户端 + SQL INSERT 模板** | user <sess> 澄清手工录入豁免 |
| Phase 1 实装范围 | 3 Raw 表 + CLI import + Web upload + Dashboard | **仅 3 Raw 表 + 3 SQL 模板 + R11 CLI + mock 冒烟** | 简化 + 符合automated workflow 单 session 节奏 |
| Phase 2-6 计划 | 12+2 周顺序执行 | **Phase 2 延后至 n≥50 条 或 3 个月** (rearm) | 贝叶斯 Beta(2,2) 需 n≥10 收敛 |
| SM00N 匿名化 | 未硬约束 | **schema CHECK + 模板 validation + 触发器** | <sess> 新 precedent |
| R11 gate | 未规定 | **两段式 Python propose + confirm_r11** | <sess> RFC-063 Phase 4 precedent |
| smart_money 表定位 | V8.1 遗产无独立 schema | **ARGUS Raw 层承载** | RFC-065 TRADER_DISCIPLINE 依赖 |

### 0.2 v3.0 推倒清单 (v2.0.1 明文废弃)

| 废弃项 | v2.0.1 位置 | 替代方案 |
|:--|:--|:--|
| REV-033 Excel 列映射配置 | ARGUS-02 §4.1 | Claude 客户端 SQL INSERT 模板 (结构化录入) |
| REV-034 首日初始化 Excel baseline | ARGUS-02 §4.1 / ARGUS-08 Phase 1 | 不再需要 (mock 冒烟 + user 手工录入无首日概念) |
| REV-037 自动备份 argus_daily.py | ARGUS-02 §4.3 | 保留但降级: SQLite 文件 OS 层复制 (Windows Task Scheduler 或手动) |
| ARGUS-08 Phase 1 CLI import 脚本 | ARGUS-08 S1.1 | argus_insert.py (两段式 R11 CLI) |
| ARGUS-08 Phase 1 /upload Web 界面 | ARGUS-08 S1.1 | 延后到 Phase 3+ (若需要) |
| AC-01/AC-02/AC-03/AC-04 Excel 验收 | ARGUS-08 §S3.1 | 替代: AC-v3-01 mock 冒烟 + AC-v3-02 手工录入模板验证 |

### 0.3 v3.0 保留项 (v2.0.1 承继)

- **ARGUS-03 SCHEMA 13 表 + 13 触发器 + 36 索引**: 完全保留, Phase 1 只实装 3 Raw 子集
- **7 设计原则 AR-P1~P7**: 完全保留
- **三层数据库架构 (Raw → Processed → Decision)**: 完全保留
- **技术栈** (Python + FastAPI + HTMX + SQLite + Pico CSS): 完全保留 (但 Phase 1 不用 FastAPI, 仅 CLI)
- **独立子系统"友邦"关系**: 完全保留
- **按产品追踪 D-005** / **日度 T+1 D-006** / **Code/Claude 边界 D-008**: 完全保留

### 0.4 v3.0 Phase 1 beta-light 清单 (<gov-ref> 落地)

| # | 产出 | 状态 |
|:-:|:--|:-:|
| 5c | `argus/schema/schema_argus_raw_mvp.sql` (3 Raw 表 + CHECK SM00N + 触发器) | Phase 1 实装 |
| 5d | `argus/templates/argus_insert_templates.md` (3 套 SQL 模板: product_info / trade / holding) | Phase 1 实装 |
| 5e | `argus/tools/argus_insert.py` (R11 两段式 CLI + mock + selftest) | Phase 1 实装 |
| 5f | `argus/tests/mock_smoke_SM001.md` (冒烟报告) | Phase 1 实装 |
| -- | Processed 6 表 Python 骨架 | **DEFERRED** (rearm n≥50 或 2026-07-22) |
| -- | Decision 2 表 + argus_recommendation JSON | **DEFERRED** (Phase 3+) |
| -- | Web UI (/dashboard, /signals, /pool) | **DEFERRED** (Phase 3+ 若需要) |

---

## 1 文档装配清单 {#ARGUS-000:assembly}

| file_id | 文件名 | 标题 | 状态 | 重要等级 |
|:--|:--|:--|:--:|:--:|
| ARGUS-000 | `INDEX.md` | 总控索引 | DRAFT | CORE |
| ARGUS-01 | `01_MOTIVATION.md` | 动机 + 系统身份 | DRAFT | CORE |
| ARGUS-02 | `02_ARCHITECTURE.md` | 独立架构 + 技术栈 | DRAFT | CORE |
| ARGUS-03 | `03_SCHEMA.md` | 三层数据库Schema | DRAFT | CORE |
| ARGUS-04 | `04_SIGNAL_SCORING.md` | 信号引擎 + 贝叶斯评分 | PLANNED | CORE |
| ARGUS-05 | `05_POOL_WEB.md` | 四区股票池 + Web界面 | PLANNED | CORE |
| ARGUS-06 | `06_ADVANCED_ANALYSIS.md` | 高级分析 (达尔文 + 共识 + 机会) | PLANNED | EXTENDED |
| ARGUS-07 | `07_IMPACT_ALTERNATIVES.md` | 影响评估 + 替代方案 | PLANNED | NORMATIVE |
| ARGUS-08 | `08_MIGRATION_ACCEPTANCE.md` | 迁移计划 + 验收标准 | PLANNED | NORMATIVE |
| ARGUS-APP-A | `APPENDIX/A_PARAMETERS.md` | 参数注册表 | PLANNED | INFORMATIVE |
| ARGUS-APP-B | `APPENDIX/B_RISKS.md` | 风险登记册 | PLANNED | INFORMATIVE |

---

## 2 文档依赖树 {#ARGUS-000:dependency-tree}

```text
ARGUS-000 (INDEX)
 |
 +-- ARGUS-01 (MOTIVATION)
 |    |
 |    +-- V8.1 smart_money_roundtable.rules.md (历史参考)
 |    +-- 55份源文献 (方法论基础)
 |    +-- Graphify知识图谱 (150节点/188边/15社区)
 |    +-- TRIDENT R1/R2/R3 三轮审议 (v1审议记录)
 |    +-- Expert Panel EP-ARGUS-2026-001 (30席重审)
 |
 +-- ARGUS-02 (ARCHITECTURE)
 |    |
 |    +-- ARGUS-01 (系统身份与原则)
 |    +-- Expert Panel WG1 决议 (数据库架构)
 |    +-- Expert Panel WG3 决议 (技术栈)
 |
 +-- ARGUS-03 (SCHEMA)
 |    |
 |    +-- ARGUS-02 (三层数据库架构)
 |    +-- Expert Panel WG1 决议 (表分配)
 |    +-- Expert Panel WG2 决议 (投资评分字段)
 |    +-- DS_01 审计铁律
 |
 +-- ARGUS-04 (SIGNAL_SCORING)
 |    |
 |    +-- ARGUS-03 (Schema定义)
 |    +-- ARGUS-01 (AR-P4 贝叶斯怀疑, AR-P7 数据源分层)
 |    +-- Expert Panel WG2 投资方法论
 |
 +-- ARGUS-05 (POOL_WEB)
 |    |
 |    +-- ARGUS-03 (Schema: argus_stock_pool)
 |    +-- ARGUS-04 (评分输出)
 |    +-- Expert Panel WG3 Web设计
 |
 +-- ARGUS-06 (ADVANCED_ANALYSIS)
 |    |
 |    +-- ARGUS-04 (信号引擎基础)
 |    +-- ARGUS-05 (池状态)
 |    +-- Advanced Features Panel EP-ARGUS-ADV-2026-001
 |
 +-- ARGUS-07 (IMPACT_ALTERNATIVES)
 |    |
 |    +-- ARGUS-02 (架构方案)
 |    +-- Expert Panel WG5 芒格终审
 |
 +-- ARGUS-08 (MIGRATION_ACCEPTANCE)
 |    |
 |    +-- ARGUS-02 ~ ARGUS-06 (全部技术文档)
 |    +-- Expert Panel WG3 MVP定义
 |
 +-- ARGUS-APP-A (PARAMETERS)
 |    +-- ARGUS-04 (评分参数)
 |    +-- ARGUS-05 (池容量参数)
 |
 +-- ARGUS-APP-B (RISKS)
      +-- TRIDENT R3 风险登记 (10项)
      +-- Expert Panel 风险补充
```

---

## 3 系统概览 {#ARGUS-000:overview}

### 3.1 系统身份

| 属性 | 值 |
|:--|:--|
| 英文名称 | ARGUS (Adaptive Rebalancing & General Underlying Surveillance) |
| 中文名称 | 百目巨人 -- 机构智慧资金行为追踪系统 |
| 系统定位 | **独立系统** -- 与Empire V9为"友邦"关系, 非内部模块 |
| 数据库 | `argus.db` (SQLite, 独立于 `empire_data.db`) |
| 技术栈 | Python 3.13 + FastAPI + Jinja2 + HTMX 2.0 + SQLite WAL + Pico CSS |
| 数据频率 | 日度 T+1 (每日全持仓 + 交易记录 + NAV) |
| 跟踪维度 | 按产品 (product), 非按经理 (manager) |
| Empire接口 | JSON file export + Claude bridge (Empire只读, 不写ARGUS) |

### 3.2 核心设计原则

| ID | 原则 | 英文 |
|:--|:--|:--|
| AR-P1 | 行为优先于方向 | Behavior over Direction |
| AR-P2 | 产品优先于股票 | Product over Stock |
| AR-P3 | 日更新周校准 | Daily Update, Weekly Calibration |
| AR-P4 | 贝叶斯怀疑 | Bayesian Skepticism |
| AR-P5 | 拥挤是引力 | Crowding is Gravity |
| AR-P6 | 诚实信号审计 | Honest Signal Audit |
| AR-P7 | 数据源分层信任 | Data Source Trust Hierarchy |

### 3.3 三层数据库架构

```text
┌──────────────────┐    ┌──────────────────────────────┐
│  Raw Layer (4表)  │    │  argus.db                    │
│                  │    │                              │
│ raw_daily_trade  │    │  Processed Layer (6表)        │
│ raw_daily_holding│───>│  argus_product_profile        │
│ raw_product_nav  │    │  argus_rebalancing_event      │
│ raw_product_info │    │  argus_signal                 │
│                  │    │  argus_consensus              │
│  (只追加不修改)    │    │  argus_darwin_event           │
│                  │    │  argus_consensus_direction    │
└──────────────────┘    │                              │
                        │  Decision Layer (2表)         │
                        │  argus_stock_pool             │
                        │  argus_stock_pool_history     │
                        │                              │
                        │  备用 (1表)                    │
                        │  argus_hf_estimate            │
                        └──────────────────────────────┘
```

**总计**: Raw 4表 + Processed 6表 + Decision 2表 + 备用 1表 = **13表** (含2张高级分析表)

---

## 4 审议历史与专家团参考 {#ARGUS-000:review-history}

### 4.1 三叉戟审议 (v1.0 时期)

| 轮次 | 类型 | 结果 |
|:--:|:--|:--|
| Round 1 | 技术评审 (Review) | 0 HIGH / 5 MEDIUM / 3 LOW, 8项建议 |
| Round 2 | 替代方案对抗 (Debate) | 5场辩论全部 MODIFIED 共识 |
| Round 3 | 逐项表决 (Resolution) | 12组件全部通过, 0 REJECT, 25项REV修订, 10项RISK |

最终评定: APPROVED WITH MODIFICATIONS (专家信心均值 7.6/10)

### 4.2 30席专家团重审 (v1 -> v2 转折)

| 文档 | 工作组 | 核心产出 |
|:--|:--|:--|
| `EXPERT_PANEL_WG1_WG2.md` | WG1 数据库 (6席) + WG2 投资 (14席) | 三层DB架构, 产品行为方法论 |
| `EXPERT_PANEL_WG3_WG4_WG5.md` | WG3 工程 (6席) + WG4 AI (3席) + WG5 哲学 (2席) | 技术栈, Code/Claude边界, 芒格终审 |

**全体表决**: B (Partial Restructure) 以 89.7% 绝对多数通过 (26/29票)

### 4.3 高级分析专家讨论 (v2 增强)

| 文档 | 规模 | 核心产出 |
|:--|:--|:--|
| `ADVANCED_FEATURES_DISCUSSION.md` | 8席专题专家 | 6项高级功能裁决 (3项V1, 2项V2, 1项RESEARCH) |

V1纳入: Darwin Moments + Consensus Direction (景气度+信念偏移) + Opportunity Lens (3/5 checklist)

---

## 5 关键设计决策登记 {#ARGUS-000:decisions}

| 决策ID | 来源 | 决策内容 | 理由 |
|:--|:--|:--|:--|
| D-001 | WG全体表决 | ARGUS为独立系统, 非Empire模块 | 独立数据源/生命周期, 情报而非指令 |
| D-002 | WG1-A | 三层数据库: Raw -> Processed -> Decision | 数据不变性 + 可审计性 + 层间隔离 |
| D-003 | WG1-B | Day 1纯SQLite, DuckDB延迟到Day 2 | YAGNI, 当前规模不需要列式分析 |
| D-004 | WG1-C | Empire接口: JSON file + Claude bridge | 最低耦合, Empire不直接访问ARGUS DB |
| D-005 | WG2 | 按产品跟踪而非按经理跟踪 | 实际数据源以产品为单位 |
| D-006 | WG2 | 日度T+1全持仓, 无需HF估算 | 每日已有完整快照, Kalman/Lasso不必要 |
| D-007 | WG3 | Tech stack: Python + FastAPI + HTMX + SQLite | 零外部服务, 一键启动 |
| D-008 | WG4 | Code做计算, Claude做解读 | 确定性操作不依赖LLM |

---

## 6 版本变更日志 {#ARGUS-000:changelog}

| 版本 | 日期 | 关键变更 |
|:--|:--|:--|
| v1.0.0-draft | 2026-04-12 | 初稿; Empire子模块设计; 11表Schema; 双库SQLite+DuckDB; TRIDENT三轮审议通过 |
| v1.0.1 | 2026-04-12 | 整合REV-026~032实战修订; 产品优先原则; 买入/卖出意图分类 |
| **v2.0.0-draft** | **2026-04-12** | **Partial Restructure**: 独立系统重构; 三层DB (Raw 4 + Processed 6 + Decision 2); 纯SQLite (DuckDB deferred); JSON file interface; 技术栈锁定; 高级分析层V1 (Darwin + Consensus + Opportunity) |
| 2.0.1 | 2026-04-12 | REV-033~038: 闭环验证修补——Excel列映射、首日初始化、达尔文数据源、变更通知、备份策略、outcome回填 |
| **3.0.0** | **2026-04-22** | **beta-light 修订 (<sess> <gov-ref>/<gov-ref>)**: 数据入口从 Excel 全自动推倒, 改为 Claude 桌面客户端手工录入 SQL INSERT 模板; Phase 1 范围从 13 表降为 3 Raw 表 (Processed/Decision 延后 n≥50 或 3 个月); 新增 SM00N 匿名化 CHECK + R11 两段式 (propose + confirm_r11); v2.0.1 核心 schema + 7 原则 + DC-013 决议全保留 |

### v1.0.0 -> v2.0.0 变更摘要

**保留**:
- 贝叶斯信誉模型 (Beta分布, 自适应衰减, 信誉冻结)
- 多时间框架信号引擎 (FAST/MEDIUM/SLOW)
- 四区动态股票池 (SCAN/WATCH/CANDIDATE/CONVICTION)
- 七大设计原则 (AR-P1 ~ AR-P7)
- 产品优先原则, 卖出三分类, 后验饱和, 数据源分层

**重写**:
- 系统架构: Empire子模块 -> 独立FastAPI应用
- 数据库: 11表嵌入empire_data.db -> 13表独立argus.db三层架构
- 部署: Empire共享进程 -> 独立Python venv + 独立端口
- 接口: 深度耦合FK -> JSON file exchange + Claude bridge
- 跟踪维度: 基金经理 -> 基金产品

**延迟**:
- DuckDB分析层 (Day 2, 触发条件: P95 > 500ms 或 >50K行 或 >20产品)
- SENTINEL看门狗, SSE推送, IC自动化
- HF持仓估算 (Kalman/Lasso)
- AH溢价背离模块

---

## 7 阅读指引 {#ARGUS-000:reading-guide}

| 读者角色 | 推荐阅读顺序 |
|:--|:--|
| 决策者/审批人 | ARGUS-01 (动机) -> ARGUS-07 (影响) -> INDEX (本文件) |
| 架构师/开发者 | INDEX -> ARGUS-02 (架构) -> ARGUS-03 (Schema) -> ARGUS-04 (引擎) |
| 投研用户 | ARGUS-01 (动机) -> ARGUS-05 (池与界面) -> ARGUS-06 (高级分析) |
| 运维/部署 | ARGUS-02 (架构) -> ARGUS-08 (迁移) -> APP-A (参数) |

---

**[存证]**
ARGUS-000 v2.0.0-draft | 2026-04-12
参考来源: TRIDENT R1/R2/R3 + Expert Panel (30席+8席) + Advanced Features Discussion
重构触发: 30席专家团以89.7%多数决议Partial Restructure (B路线)
SOP完成: 启动-热场-参考-撰写-复查-收尾
