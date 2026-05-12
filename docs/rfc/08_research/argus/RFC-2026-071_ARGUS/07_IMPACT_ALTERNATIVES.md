---
file_id: ARGUS-07
title: "影响分析与替代方案 (Standalone Edition)"
title_en: "Impact Analysis & Alternatives (Standalone Edition)"
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
  - "ARGUS-04 (架构与数据库设计 v2.0)"
  - "ARGUS-05 (信号引擎与评分 v2.0)"
  - "ARGUS-06 (池管理与Web界面 v2.0)"
  - "EXPERT_PANEL_WG3_WG4_WG5.md (30席专家表决: B路线)"
  - "ADVANCED_FEATURES_DISCUSSION.md (高级分析层)"
supersedes: "ARGUS-05 v0.1.0 (archived to _archive_v1/05_IMPACT_ALTERNATIVES.md)"
amendment_level: L2
---

# 07 影响分析与替代方案 (Standalone Edition) {#ARGUS-07:root}

# Impact Analysis & Alternatives (Standalone Edition)

> **V2.0 核心变更**: ARGUS从Empire内部模块重构为完全独立系统 (own DB, own process, own config)。此版本影响分析反映独立架构下的全新影响格局 -- 对Empire的影响从"深度耦合"降至"友邦交换"。
>
> **V2.0 Key Change**: ARGUS restructured from Empire submodule to fully standalone system. Impact profile shifts from "deep coupling" to "diplomatic exchange" with Empire.

---

## S1 影响分析 (Impact Analysis) {#ARGUS-07:impact}

### S1.1 设计原则 (Design Principle) {#ARGUS-07:principle}

ARGUS V2.0遵循30席专家座谈会 (EP-ARGUS-2026-04-12) 以89.7%多数通过的B路线 (Partial Restructure) 决议:

- ARGUS是独立系统, 拥有自己的数据库 (argus.db)、FastAPI进程、配置文件
- 与Empire的关系是"友邦交换" (diplomatic exchange), 不是"内部模块"
- 数据交换通过JSON文件, 不共享数据库文件
- ARGUS即使完全停止运行, Empire不受任何影响

ARGUS V2.0 follows the B-route (Partial Restructure) resolution passed by 89.7% majority at the 30-seat Expert Panel:

- ARGUS is an independent system with its own database (argus.db), FastAPI process, and config
- Relationship with Empire is "diplomatic exchange", not "internal module"
- Data exchange via JSON files; no shared database files
- Empire is completely unaffected even if ARGUS stops running entirely

---

### S1.2 组件影响矩阵 (Component Impact Matrix) {#ARGUS-07:impact-matrix}

| 影响项 / Impact Item | V1.0状态 (旧RFC) | V2.0状态 (Standalone) | V2.0风险 | 说明 / Notes |
|:--|:--|:--|:--:|:--|
| **Empire empire_data.db** | 新增11张argus_*表 | **零影响**: ARGUS使用独立argus.db | NONE | 不再在Empire数据库中创建任何表 / No tables created in Empire DB |
| **Empire FastAPI进程** | 新增18个端点+SSE | **零影响**: ARGUS有自己的FastAPI | NONE | 端口隔离: Empire:8001, ARGUS:8000 |
| **Empire params_config.yaml** | 新增55+参数 | **零影响**: ARGUS有独立config.yaml | NONE | 参数命名空间完全独立 |
| **Empire stock_pool表** | 新增FK引用+PROMOTE写入 | **无直接写入**: 通过JSON推荐 | NONE | ARGUS输出JSON, 人类决定是否纳入Empire |
| **Empire event_log** | 新增ARGUS_SIGNAL类型 | **无直接写入**: 可选JSON导入 | NONE | 如需纳入event_log, 由Claude在roundtable中手动操作 |
| **Empire SENTINEL看门狗** | 新增WD-DYN-001/002 | **不集成**: ARGUS有自己的告警 | NONE | V1不做SENTINEL集成; ARGUS异常告警在自身Web UI展示 |
| **Empire DuckDB分析层** | 新增6个分析视图 | **不涉及**: MVP阶段无DuckDB | NONE | DuckDB在ARGUS积累6个月数据后再评估引入 |
| **Empire IC决策流** | Roundtable 7模块升级 | **JSON输入(可选, additive)** | LOW | IC可选择读取ARGUS的recommendation JSON; 不读取时IC流程不变 |
| **Empire Roundtable** | 模块1~7全面升级 | **Claude桥接(可选, additive)** | LOW | Claude在daily session中可读取ARGUS数据辅助roundtable, 但不是必须 |
| **用户日常工作流** | 深度整合, 改变操作方式 | **纯增量: 新增一个工具** | LOW | 用户多开一个浏览器tab看ARGUS dashboard; 现有工作流不变 |
| **基础设施** | 修改Empire进程+DB+配置 | **+1 SQLite文件 +1 FastAPI进程 +1浏览器tab** | LOW | 增量资源消耗极小; 本地Python venv部署 |

---

### S1.3 不受影响的Empire组件 (Empire Components Not Affected) {#ARGUS-07:no-impact}

以下Empire核心组件在ARGUS V2.0 Standalone架构下**完全不受影响**:

The following Empire core components are **completely unaffected** under ARGUS V2.0 Standalone:

| 组件 / Component | 保证 / Guarantee |
|:--|:--|
| Empire核心交易执行链 (trade_exec.*) | 零代码变更, 零数据变更 |
| NAV账本 (nav_ledger.*) | ARGUS不接触Empire任何表 |
| empire_data.db全部30+张表 | 不新增表、不新增列、不新增FK、不新增触发器 |
| params_config.yaml (196参数) | 不新增参数、不修改参数 |
| SENTINEL看门狗 (WD-STA-*, WD-DYN-*) | 不注册新看门狗 |
| stock_pool + stock_pool_history | 不直接写入, 不新增FK |
| 铁律注册表 (IL-01 ~ IL-11) | 不修改任何铁律 |
| 角色卡系统 (R01-R11) | 不引入新角色 |
| FastAPI端点 (/api/v1/*) | 不新增任何端点 |
| Wind Listener Gate 1-5 | 不修改任何Gate |

> **关键结论 / Key Conclusion**: ARGUS V2.0 Standalone对Empire的影响为**零侵入** (zero intrusion)。Empire可以在完全不知道ARGUS存在的情况下正常运行。这是V1.0架构 (11表+18端点+55参数侵入Empire) 的根本性改善。

---

### S1.4 ARGUS自身基础设施需求 (ARGUS Infrastructure Requirements) {#ARGUS-07:infra}

| 资源 / Resource | 规格 / Spec | 说明 / Notes |
|:--|:--|:--|
| 磁盘: argus.db | ~50MB (首年预估) | 200产品 x 365日 x 50持仓 = ~3.6M行, SQLite轻松应付 |
| 磁盘: 配置+代码 | ~5MB | Python源码 + config.yaml + 模板 |
| 磁盘: 备份 | ~50MB x 30天 | 每日复制argus.db到backup目录 |
| 内存: FastAPI进程 | ~100-200MB | 单用户, 无并发压力 |
| 端口: HTTP | localhost:8000 | 与Empire端口不冲突 |
| Python版本 | 3.11+ | 与Empire一致 |
| 外部依赖 | 零 | 无Docker, 无PostgreSQL, 无Node, 无DuckDB (MVP阶段) |

---

### S1.5 数据交换影响 (Data Exchange Impact) {#ARGUS-07:exchange}

ARGUS与Empire之间唯一的数据交换通道:

The only data exchange channel between ARGUS and Empire:

**方向1: ARGUS -> Empire (推荐)**

```
ARGUS scoring完成 -> 生成 argus_recommendation_YYYYMMDD.json
  -> Claude在daily session中读取
  -> Roundtable讨论
  -> 人类决定是否写入Empire stock_pool
```

- 文件格式: JSON (人类可读)
- 写入位置: ARGUS的output/目录
- Empire读取方式: Claude在session中读取文件 (不是自动化API调用)
- 风险: NONE -- 如果JSON文件不存在或格式错误, Empire不受影响

**方向2: Empire -> ARGUS (持仓, MVP阶段不实现)**

- MVP阶段: Claude在roundtable中手动查看两个系统, 人工判断矛盾
- Phase 5 (如有需要): Empire导出holdings JSON, ARGUS读取做矛盾检测

---

## S2 替代方案 (Alternatives Considered) {#ARGUS-07:alternatives}

以下6项关键设计决策, 记录被采纳方案与被拒绝方案的理由。每项决策经30席专家座谈会辩论并裁决。

Six key design decisions with adopted and rejected alternatives. Each decision debated and resolved at the 30-seat Expert Panel.

---

### D1: 独立系统 vs Empire模块 (Standalone vs Empire Module) {#ARGUS-07:d1}

| 方案 / Option | 描述 / Description | 优点 / Pros | 缺点 / Cons |
|:--|:--|:--|:--|
| **A: Empire子模块** (V1.0设计) | ARGUS作为Empire的ANLZ/RISK/SENS分区模块, 共享empire_data.db | 数据实时共享; 无需跨进程通信; 单一部署 | 11表+18端点+55参数侵入Empire; DuckDB锁竞争(RISK-001); Empire崩溃=ARGUS崩溃; 耦合度极高 |
| **B: 独立系统** (V2.0采纳) | ARGUS拥有独立DB/进程/配置, 通过JSON文件与Empire交换 | 零侵入Empire; 独立失败不影响Empire; 简化部署; 可独立迭代 | JSON交换有延迟; 无实时数据共享; 需维护两个进程 |
| **C: 微服务架构** | ARGUS作为Docker容器, REST API双向通信 | 标准化接口; 可扩展 | 单人项目不需要Docker; 运维复杂度不值得; 敏感数据不应上云 |

**裁决 / Resolution**: **方案B** -- 89.7%专家投票支持。芒格评语: "Simple systems are more reliable than complex ones."

---

### D2: 三层数据库 vs 扁平表 (Three-Layer DB vs Flat Tables) {#ARGUS-07:d2}

| 方案 / Option | 描述 / Description | 优点 / Pros | 缺点 / Cons |
|:--|:--|:--|:--|
| **A: 扁平表设计** | 所有数据放入3-4张宽表 | 简单直观; 查询不需要JOIN | 数据冗余; 难以维护; schema变更影响大 |
| **B: 三层分离** (V2.0采纳) | Raw -> Processed -> Decision三层 | 关注点分离; Raw层保留原始数据可溯源; 每层可独立重建 | 表数量多于扁平方案; 需要管道处理 |
| **C: 11张表** (V1.0设计) | 每个domain一张专用表 | 细粒度控制; 专用索引 | 芒格: "11张表对单人系统是过度工程"; JOIN复杂; 维护成本高 |

**裁决 / Resolution**: **方案B** -- 三层分离, 但每层内表数量精简。ENG-02建议5~7张表 (而非V1.0的11张)。芒格验证: "如果只能有5张表, 留哪5张?" -> products, holdings, signals, pool, history。

---

### D3: 产品维度 vs 经理维度跟踪 (Product-Based vs Manager-Based Tracking) {#ARGUS-07:d3}

| 方案 / Option | 描述 / Description | 优点 / Pros | 缺点 / Cons |
|:--|:--|:--|:--|
| **A: 经理维度** | 以基金经理为核心实体, 聚合其管理的所有产品 | 符合"跟聪明钱"的直觉; 经理是决策者 | 一个经理管多个产品, 行为可能不一致; 经理变动(离职/转岗)导致数据断裂; T+1数据是按产品提供的 |
| **B: 产品维度** (V2.0采纳) | 以基金产品为核心实体, 经理信息作为产品属性 | 与数据源一致(T+1数据按产品); 产品是稳定实体(经理可变); 一对多关系清晰(1产品=1经理, 但1经理可有N产品) | 同一经理的多产品可能被重复计入; 需要去重逻辑 |

**裁决 / Resolution**: **方案B** -- 产品优先 (Product-First), 与三叉戟REV-026一致。经理信息作为产品的元数据字段。去重通过信誉引擎的"有效独立来源数"折算处理。

---

### D4: 日度数据 vs 季度数据 (Daily Data vs Quarterly Data) {#ARGUS-07:d4}

| 方案 / Option | 描述 / Description | 优点 / Pros | 缺点 / Cons |
|:--|:--|:--|:--|
| **A: 季度公开数据** | 基于13F/季报的持仓披露, 每季度更新一次 | 数据免费/公开; 覆盖面广(全部公募基金) | 延迟2-4个月; 信号价值已大幅衰减; Fama: "你看到数据时alpha已经实现了大半" |
| **B: 日度T+1数据** (V2.0采纳) | 数据供应商提供的日度交易+持仓数据 | 时效性最强(T+1); 可检测日内行为变化; 支持FAST层信号 | 数据有成本; 覆盖面有限(仅top-5产品); 芒格: "T+1仍然是事后数据, 经理买入后股价可能已涨3%" |
| **C: 实时Level-2** | 通过Level-2行情反推大单 | 实时性; 无延迟 | 噪声极大; 机构分拆下单难以识别; 数据成本极高; 技术复杂度不适合单人项目 |

**裁决 / Resolution**: **方案B** -- 日度T+1数据为唯一数据源。MVP阶段聚焦top-5产品。芒格的T+1延迟警告记录在案, 通过"ARGUS是望远镜不是自动驾驶"的定位来缓解。

---

### D5: SQLite-Only MVP vs SQLite+DuckDB Day 1 {#ARGUS-07:d5}

| 方案 / Option | 描述 / Description | 优点 / Pros | 缺点 / Cons |
|:--|:--|:--|:--|
| **A: SQLite+DuckDB** (V1.0设计) | SQLite做OLTP, DuckDB做OLAP, Day 1双库并行 | OLAP查询快; 分析视图丰富 | RISK-001锁竞争; 运维复杂; 数据量小时DuckDB优势不明显 |
| **B: SQLite-Only MVP** (V2.0采纳) | SQLite单库, WAL模式, 所有查询直接在SQLite上执行 | 零配置; 零锁竞争; 备份=复制文件; 数据量<360万行/年SQLite轻松应付 | 大数据量下OLAP查询可能变慢; 无列式存储优化 |
| **C: PostgreSQL** | 企业级关系数据库 | 成熟稳定; 丰富的分析函数 | 需要安装/配置/启动服务; 连接池管理; 备份=pg_dump; 单人项目全是overhead |

**裁决 / Resolution**: **方案B** -- SQLite-Only MVP。ENG-06: "当你只有几万行数据时, DuckDB的OLAP优势根本体现不出来。" DuckDB在运行6个月后视数据量评估引入。

---

### D6: Empire接口方式 (Empire Interface Method) {#ARGUS-07:d6}

| 方案 / Option | 描述 / Description | 优点 / Pros | 缺点 / Cons |
|:--|:--|:--|:--|
| **A: JSON文件+Claude桥接** (V2.0采纳) | ARGUS生成JSON推荐文件, Claude在roundtable中读取解读, 人类决策写入Empire | 最简单; 人类可读; 有judgment环节; 低风险 | 非实时; 依赖Claude session做解读 |
| **B: 共享数据库** (V1.0设计) | Empire ATTACH argus.db READ_ONLY | 实时; 零网络开销 | ENG-05强烈反对: Windows上两进程访问同一SQLite有WAL文件锁问题; 违反独立性原则 |
| **C: REST API** | Empire调用ARGUS的API端点 | 标准; 解耦 | 要求两个系统同时运行; ARGUS不运行时Empire拿不到数据 |
| **D: Claude桥接** (无JSON文件) | Claude直接读两个DB, 人工转述 | 灵活; 可加判断 | 依赖Claude session; 非确定性; 无审计日志 |

**裁决 / Resolution**: **方案A** -- JSON文件输出 + Claude桥接解读。AI-01: "ARGUS的输出不是指令, 是建议。建议不需要实时API。" Kahneman: "Friction is a feature -- JSON文件+人类确认提供了必要的决策摩擦。" 备用路径: Phase 5提供REST API查询端点, 但不触发Empire写入。

---

## S3 替代方案决策总结 (Decision Summary) {#ARGUS-07:summary}

| 决策 / Decision | 采纳 / Adopted | 被拒绝 / Rejected | 核心理由 / Key Rationale |
|:--|:--|:--|:--|
| D1: 系统定位 | 独立系统 | Empire模块, 微服务 | 零侵入 > 深度耦合 |
| D2: 数据库设计 | 三层5~7表 | 扁平表, 11表 | 分层溯源 + 芒格简化 |
| D3: 跟踪维度 | 产品维度 | 经理维度 | 数据源一致性, 实体稳定性 |
| D4: 数据频率 | 日度T+1 | 季度, 实时 | 时效性与成本的最优平衡 |
| D5: 数据库选型 | SQLite-Only MVP | SQLite+DuckDB, PostgreSQL | RISK-001消除, 零配置 |
| D6: Empire接口 | JSON+Claude桥接 | 共享DB, REST API | 决策摩擦, 人类判断环节 |

---

## Attestation {#ARGUS-07:attestation}

本文档由Internal Review Board基于以下材料编制:

This document was compiled by the Empire Decision Committee based on:

- EXPERT_PANEL_WG3_WG4_WG5.md: 30席专家座谈会 (89.7% B路线表决)
- EXPERT_PANEL_WG1_WG2.md: 金融理论组+统计方法组讨论
- ADVANCED_FEATURES_DISCUSSION.md: 高级分析层专家讨论
- _archive_v1/05_IMPACT_ALTERNATIVES.md: V1.0影响分析 (已归档, 供对比参考)

V2.0影响分析反映ARGUS独立化后的全新影响格局。V1.0的11表/18端点/55参数侵入Empire的分析不再适用, 已归档至_archive_v1。

---

## Changelog {#ARGUS-07:changelog}

| 版本 / Version | 日期 / Date | 作者 / Author | 变更说明 / Changes |
|:--|:--|:--|:--|
| 0.1.0-draft | 2026-04-12 | Claude (SESSION-008) | V1.0初稿: 作为Empire子模块的影响分析 (已归档) |
| 2.0.0-draft | 2026-04-12 | Internal Review Board | V2.0重写: 独立系统影响分析; 6项设计决策重新裁决; 影响从深度耦合降至零侵入 |

---

**[ATTESTATION]**
ARGUS-07 V2.0.0-draft | RFC-2026-071 | 2026-04-12
Based on: 30-seat Expert Panel (B-route, 89.7%) + WG3 tech stack + WG5 Munger review
SOP: init-context-draft-review-finalize
