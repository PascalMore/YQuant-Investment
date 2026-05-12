---
file_id: ARGUS-02
title: "独立架构与技术栈"
rfc_id: RFC-2026-071
doc_status: "AMENDED"
approval_status: "ACCEPTED"
impl_status: "PHASE_1_DRAFT"
version: "3.0.0"
created: "2026-04-12"
last_updated: "2026-04-22"
drafter: "Internal Review Board"
owner: "Internal Review Board"
depends_on:
  - "ARGUS-000 (INDEX)"
  - "ARGUS-01 (动机与身份)"
amendment_level: L2
---

# ARGUS-02: 独立架构与技术栈 {#ARGUS-02:root}

> **本文件为RFC-2026-071的第二章 (Normative)**。
> 定义ARGUS作为独立系统的架构设计、技术栈选型、三层数据库架构、部署方案、Empire接口协议和DuckDB Day 2规划。

---

## 0 v3.0 beta-light 修订说明 (2026-04-22, <sess>) {#ARGUS-02:v3-amendment}

> **v3.0 仅修订数据入口机制**, 不动三层数据库架构 / 技术栈 / 独立部署 / Empire 接口协议.

### 0.1 v3.0 推倒项 (v2.0.1 明文废弃)

- **§4.1 Excel 列映射规则**: 汇总.xlsx (7列) + 产品持仓.xlsx (6列) + 列映射配置 → 废弃. 替代: Claude 桌面客户端 SQL INSERT 模板 (见 ARGUS-08 v3.0 Phase 1).
- **§7 Daily Workflow Step 1 DATA IMPORT**: "读取今日 Excel 文件" → 改为 "user 通过 Claude 桌面客户端触发 SQL INSERT (文字/照片源)".
- **REV-034 首日初始化**: Excel baseline 首日规则废弃. 替代: user 任意日录入即可, 无首日概念.
- **REV-037 argus_daily.py 自动备份**: 降级保留. 替代: SQLite 文件 OS 层手动复制 (user 按需).

### 0.2 v3.0 保留项

- **§1 友邦关系模型** + **§2 技术栈** (Python + FastAPI + Jinja2 + HTMX + SQLite + Pico CSS) + **§3 三层数据库架构** + **§5 Empire 接口 (JSON + Claude bridge)** + **§6 DuckDB Day 2 规划**: **完全保留**.
- Phase 1 beta-light 不用 FastAPI (仅 CLI + SQL), **Phase 3+ rearm 时启用 Web UI**.

### 0.3 v3.0 数据入口新规 (替代 §4.1)

```
Phase 1 数据入口流程 (v3.0 beta-light):

1. user 收到聪明钱情报 (多种渠道, 含定性记录与定量持仓数据)
2. 在 Claude Windows 桌面客户端打开 session
3. 触发 SQL INSERT 模板 (argus_insert_templates.md 3 套模板)
4. Claude 调用 argus_insert.py CLI (两段式 propose → user R11 confirm → INSERT)
5. 触发器强制 SM00N 匿名化 + DS_01 审计轨迹
6. query 验证入库

与 v2.0.1 差异: 无 Excel 解析, 无 Web upload, 无 CLI 批量 import.
structured 程度: 仍是结构化 (SQL 表 + CHECK + 触发器), 仅入口手工.
```

详见 ARGUS-08 v3.0 Phase 1.

---

## 1 系统定位: 独立 vs 模块 {#ARGUS-02:positioning}

### 1.1 v1 vs v2 架构对比

| 维度 | v1.0 (Empire子模块) | v2.0 (独立系统) |
|:--|:--|:--|
| 数据库 | 嵌入 `empire_data.db` (argus_*表) | 独立 `argus.db` |
| 进程 | Empire FastAPI内部模块加载 | 独立FastAPI进程 |
| 端口 | 共享Empire端口 | 独立端口 (默认 :8001) |
| 配置 | Empire params_config.yaml | 独立 argus_config.yaml |
| V9分区 | ANLZ + RISK + SENS 三分区部署 | 无分区, 单一独立应用 |
| 模块ID | `anlz.argus_core` 等 | 不适用 |
| DuckDB | 分析加速缓存 (Day 1) | Day 2预留 (触发条件后引入) |
| Empire通信 | 同库FK引用 + stock_pool_ops | JSON file + Claude bridge |
| 数据频率 | 日线+季报 (Empire节奏) | 日度T+1 (独立节奏) |
| 跟踪维度 | 基金经理 (manager_id) | 基金产品 (product_code) |
| 故障影响 | ARGUS故障可能影响Empire | 互不影响 |

### 1.2 友邦关系模型

```text
"友邦" (Allied Nations) -- 两个独立主权实体的情报交换

                ┌─────────────────────────────────────┐
                │         Claude Bridge Layer          │
                │   (读取双方数据, 做解读+矛盾检测)      │
                └────────┬─────────────────┬───────────┘
                         │                 │
                    情报输出(JSON)      持仓读取(JSON)
                         │                 │
                         v                 v
┌────────────────────────┐   ┌────────────────────────┐
│      ARGUS 百目巨人      │   │      Empire V9     │
│                        │   │                        │
│  argus.db              │   │  empire_data.db        │
│  localhost:8001        │   │  localhost:8000        │
│  argus_config.yaml     │   │  params_config.yaml    │
│                        │   │                        │
│  输出:                  │   │  输入:                  │
│  argus_recommendation  │──>│  Claude roundtable     │
│  _YYYYMMDD.json        │   │  -> 人类决策           │
│                        │   │  -> stock_pool_ops     │
└────────────────────────┘   └────────────────────────┘
  独立启停                     独立启停
  独立备份                     独立备份
  独立迭代                     独立迭代
```

**约束**:
- C-01: Empire**只读**ARGUS输出, 不能写入ARGUS数据库
- C-02: ARGUS**只读**Empire持仓, 通过Claude session人工查看
- C-03: 两系统独立启停, 一方不可用时另一方正常运行
- C-04: 数据交换通过文件系统(JSON)而非网络(REST API)实现 (MVP阶段)

---

## 2 技术栈 {#ARGUS-02:tech-stack}

### 2.1 选型总表

| 层级 | 选型 | 版本 | 理由 | 来源 |
|:--|:--|:--|:--|:--|
| 语言 | Python | 3.13+ | 唯一语言, 与Empire一致 | WG3一致 |
| Web框架 | FastAPI | 0.115+ | async + OpenAPI自动文档 | WG3一致 |
| 模板引擎 | Jinja2 | 3.1+ | FastAPI原生支持, 服务端渲染 | WG3一致 |
| 前端交互 | HTMX | 2.0+ (CDN) | 零build, 局部刷新 | WG3一致 |
| CSS框架 | Pico CSS | 2.0+ (CDN) | Classless, 零CSS代码 | WG3一致 |
| 图表 | Chart.js | 4.x (CDN) | Phase 2引入 | WG3 |
| 数据库 | SQLite | 3.45+ (WAL) | 单文件, 零配置 | WG1/WG3一致 |
| Excel解析 | openpyxl | 3.1+ | Python标准Excel库 | WG3 |
| 配置 | YAML (PyYAML) | 6.0+ | 与Empire一致 | WG3 |
| 测试 | pytest + httpx | -- | FastAPI推荐AsyncClient | WG3 |

### 2.2 明确排除

| 技术 | 排除理由 | 来源 |
|:--|:--|:--|
| Node.js | 单语言项目不需要第二语言 | WG3一致 |
| React | 4页dashboard不需要SPA复杂度 | WG3 ENG-03 |
| PostgreSQL | 单用户/单机/单进程, SQLite足够 | WG3一致 |
| Docker | 单人使用, 不需要容器化 | WG3 ENG-05 |
| Streamlit | 控制粒度不够, 无法定制路由和API | WG3 ENG-03 |
| DuckDB (Day 1) | YAGNI, 当前规模不需要 | WG1-B决议 |
| nginx | FastAPI自带开发服务器 | WG3 ENG-05 |

### 2.3 一键启动

```bash
# 安装 (一次性)
git clone <argus-repo>
cd argus
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 启动 (每次)
python main.py
# -> ARGUS running at http://localhost:8001
```

总依赖: FastAPI + uvicorn + Jinja2 + openpyxl + PyYAML + httpx (测试)。无需数据库服务器, 无需前端build, 无需Docker。

---

## 3 三层数据库架构 {#ARGUS-02:three-layer-db}

### 3.1 架构总览

```text
┌─────────────────────────────────────────────────────────────┐
│                        argus.db                             │
│                    (单一SQLite文件)                           │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Raw Layer (原始层)  --  4 tables                    │    │
│  │                                                     │    │
│  │  raw_daily_trade      每日交易记录                    │    │
│  │  raw_daily_holding    每日全持仓快照                   │    │
│  │  raw_product_nav      每日NAV                        │    │
│  │  raw_product_info     产品元数据                      │    │
│  │                                                     │    │
│  │  规则: 只INSERT不UPDATE (触发器保护)                   │    │
│  │        raw_product_info例外 (元信息可变更)             │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │ (层间转换: 清洗/标准化/去重)        │
│                         v                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Processed Layer (加工层)  --  6 tables              │    │
│  │                                                     │    │
│  │  argus_product_profile     产品画像+信誉(贝叶斯)      │    │
│  │  argus_rebalancing_event   调仓路径事件               │    │
│  │  argus_signal              多时间框架信号              │    │
│  │  argus_consensus           多产品共识事件              │    │
│  │  argus_darwin_event        达尔文时刻检测              │    │
│  │  argus_consensus_direction 景气度+信念偏移             │    │
│  │                                                     │    │
│  │  规则: 可更新, 可重算, 计算型                          │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │ (层间转换: 评分/池管理/决策)        │
│                         v                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Decision Layer (决策层)  --  2 tables               │    │
│  │                                                     │    │
│  │  argus_stock_pool           四区动态股票池             │    │
│  │  argus_stock_pool_history   池变更审计轨迹             │    │
│  │                                                     │    │
│  │  规则: 可升降级, 有审计轨迹                            │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  备用 (Fallback)  --  1 table                       │    │
│  │                                                     │    │
│  │  argus_hf_estimate          高频估算 (仅备用)         │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 层边界规则

| 规则ID | 规则 | 强制方式 |
|:--|:--|:--|
| LB-01 | Raw层数据只追加不修改 (raw_product_info例外) | BEFORE UPDATE/DELETE触发器 RAISE(ABORT) |
| LB-02 | 数据流单向: Raw -> Processed -> Decision | 代码约束 + Code Review |
| LB-03 | Decision层变更不能反向影响Raw/Processed层 | 无反向FK; 代码约束 |
| LB-04 | 层间转换必须记录 (日志/指标) | 应用层logging |
| LB-05 | Processed/Decision可重算: 删除后从Raw重新生成 | 重算脚本设计 |

### 3.3 单库设计理由

v1设计为双库 (`argus_raw.db` + `argus.db`), WG1-A辩论后推荐双库方案。但v2最终采用**单库设计**, 理由:

1. **简洁性**: SQLite核心优势是single-file deployment, 拆分为两个文件增加运维复杂度
2. **事务一致性**: 层间转换在同一WAL中, 质量检查点更可靠 (DB-06论点)
3. **规模适配**: top-5产品/日均数百行, 写入冲突概率极低, 无需物理隔离
4. **触发器保护**: Raw层不变性通过BEFORE UPDATE/DELETE触发器强制, 无需文件级隔离
5. **Day 2可拆分**: 如果规模增长需要, 可随时将Raw层拆分到独立文件, Schema不变

### 3.4 SQLite配置

```sql
-- argus.db PRAGMA配置
PRAGMA journal_mode = WAL;          -- Write-Ahead Logging
PRAGMA synchronous = NORMAL;        -- 平衡安全与性能
PRAGMA cache_size = -8000;          -- 约8MB cache
PRAGMA foreign_keys = ON;           -- 强制外键约束
PRAGMA busy_timeout = 5000;         -- 5秒等待锁
PRAGMA temp_store = MEMORY;         -- 临时表在内存中
PRAGMA mmap_size = 268435456;       -- 256MB memory-mapped I/O
```

---

## 4 部署架构 {#ARGUS-02:deployment}

### 4.1 本地单进程部署

```text
┌──────────────────────────────────────────────────────┐
│  Local Machine (用户工作站)                            │
│                                                      │
│  ┌──────────────────┐    ┌──────────────────┐        │
│  │  ARGUS Process   │    │  Empire Process  │        │
│  │  (FastAPI)       │    │  (FastAPI)       │        │
│  │  :8001           │    │  :8000           │        │
│  │                  │    │                  │        │
│  │  serves:         │    │  serves:         │        │
│  │  - Web UI (HTML) │    │  - API           │        │
│  │  - API (JSON)    │    │  - Web UI        │        │
│  │  - Static files  │    │                  │        │
│  └────────┬─────────┘    └────────┬─────────┘        │
│           │                       │                  │
│           v                       v                  │
│  ┌──────────────┐        ┌──────────────┐            │
│  │  argus.db    │        │ empire_data  │            │
│  │  (SQLite)    │        │ .db (SQLite) │            │
│  └──────────────┘        └──────────────┘            │
│                                                      │
│  ┌──────────────────────────────────────────┐        │
│  │  Shared Output Directory                 │        │
│  │  ./output/                               │        │
│  │    argus_recommendation_20260412.json     │        │
│  │    argus_recommendation_20260411.json     │        │
│  └──────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────┘
```

### Excel列映射规则 {#ARGUS-02:excel-mapping}

导入脚本必须支持以下列映射配置（基于实际生产数据格式）:

**汇总.xlsx (买卖记录)**:
| Excel列 | 字段 | Raw表字段 | 示例 |
|:--|:--|:--|:--|
| A (序号) | 行号 | 不导入 | 7 |
| B (资产代码) | 产品资产代码 | product_code | 80PF210477 |
| C (产品名称) | 产品名+规模 | product_name + aum_scale | 中欧1号-3.6e → name="中欧1号", aum=3.6 |
| D (Wind代码) | 股票代码 | wind_code | 603259.SH |
| E (资产名称) | 股票名称 | stock_name | 药明康德 |
| F (变化比例) | 操作类型 | change_type | 新买入/清仓/加仓/减仓 |
| G (变化金额) | 交易金额 | change_amount | 3001860.00 |

**产品持仓.xlsx (全持仓快照)**:
| Excel列 | 字段 | Raw表字段 |
|:--|:--|:--|
| A (截止日期) | 快照日期 | snapshot_date |
| B (Wind代码) | 股票代码 | wind_code |
| C (资产名称) | 股票名称 | stock_name |
| D (数量) | 持股数量 | shares |
| E (市值) | 持仓市值 | market_value |
| F (变化) | 变化标记 | change_flag |

**产品名称解析规则**: `{名称}-{规模}{单位}` → 分隔符为最后一个`-`，`e`=亿元。如"中欧1号-3.6e" → product_name="中欧1号", aum_scale=3.6

**列映射可配置**: 存储在`argus_config.yaml`的`import.column_mapping`节，允许用户在Excel格式变化时调整而不改代码。

### 4.2 代码结构

```text
argus/
  main.py                  # FastAPI entry point, uvicorn启动
  config.py                # YAML配置管理
  db/
    schema.py              # DDL定义 + 初始化函数
    connection.py          # SQLite连接管理
    models.py              # Pydantic数据模型
  pipeline/
    importer.py            # Excel -> Raw tables
    processor.py           # Raw -> Processed (清洗/标准化)
    scoring.py             # 信号评分引擎
    credibility.py         # 贝叶斯信誉更新
    pool.py                # 四区池管理
    darwin.py              # 达尔文时刻检测
    consensus.py           # 共识方向引擎
  web/
    routes.py              # FastAPI路由
    templates/             # Jinja2 + HTMX模板
      base.html
      home.html            # 信号总览
      pool.html            # 股票池
      products.html        # 产品列表
      history.html         # 历史记录
    static/
      pico.min.css         # (或CDN引用)
      htmx.min.js          # (或CDN引用)
  exchange/
    empire_bridge.py       # JSON output生成
  tests/
    test_scoring.py        # 评分引擎100%覆盖
    test_importer.py
    test_pool.py
  argus_config.yaml        # 运行时参数配置
  requirements.txt
```

### 备份策略 {#ARGUS-02:backup}

**每日备份 (REV-037)**:
- Step 1 (数据导入) 执行前，自动备份: `cp argus.db backups/argus_{YYYYMMDD}.db`
- 保留最近30天备份，超期自动清理
- 备份目录: `argus_data/backups/`
- 备份脚本集成在 `argus_daily.py` 的第一步
- 完整恢复: `cp backups/argus_{date}.db argus.db` + 重启FastAPI

### 4.3 数据备份

```text
备份策略: SQLite文件复制
频率: 每日 (可用Windows Task Scheduler自动化)
方式: copy argus.db -> backup/argus_YYYYMMDD.db
保留: 最近30天日备份 + 每月1号月备份(永久保留)
```

---

## 5 与 Empire 的接口 {#ARGUS-02:empire-interface}

### 5.1 ARGUS -> Empire (推荐输出)

**主路径: JSON file + Claude解读**

ARGUS每次scoring完成后, 生成推荐文件:

```text
文件名: argus_recommendation_YYYYMMDD.json
位置: ./output/
```

JSON结构:

```json
{
  "date": "2026-04-12",
  "version": "2.0.0",
  "generated_at": "2026-04-12T08:35:00",
  "conviction_pool": [
    {
      "stock_code": "603799.SH",
      "stock_name": "华友钴业",
      "pool_zone": "CONVICTION",
      "composite_score": 0.78,
      "bayesian_posterior": 0.72,
      "contributing_products": ["产品A", "产品B"],
      "direction": "BUY",
      "signal_count": 4,
      "days_in_zone": 12,
      "checklist": {
        "darwin_moment": true,
        "prosperity_bullish": true,
        "conviction_rising": true
      }
    }
  ],
  "candidate_pool": [...],
  "new_signals_today": [...],
  "alerts": [...]
}
```

**使用流程**:
1. ARGUS daily pipeline自动生成JSON
2. Claude在daily session中读取JSON
3. Claude做roundtable解读分析
4. 人类决定是否将推荐写入Empire stock_pool
5. (可选) Claude通过stock_pool_ops.py写入Empire

### 5.2 Empire -> ARGUS (持仓反馈)

**MVP阶段**: 不做自动化接口。矛盾检测由Claude在roundtable中人工完成(同时查看两个系统数据库)。

**Phase 3**: 如有需要, Empire导出 `empire_holdings_YYYYMMDD.json`, ARGUS读取后做矛盾检测。

### 5.3 接口约束

| 约束ID | 约束 | 理由 |
|:--|:--|:--|
| IF-01 | Empire不直接访问argus.db文件 | 防止跨系统数据污染 (WG1 DB-01) |
| IF-02 | ARGUS不直接访问empire_data.db文件 | 同上 |
| IF-03 | 数据交换仅通过JSON文件或Claude session | 解耦彻底, 接口可版本化 |
| IF-04 | ARGUS推荐不自动写入Empire | Friction is a feature (Kahneman) |
| IF-05 | JSON文件带版本号和时间戳 | 防止读取过期数据 |

---

## 6 DuckDB Day 2规划 {#ARGUS-02:duckdb-day2}

### 6.1 引入触发条件

DuckDB**不在**MVP (Day 1) 中引入。当以下任一条件触发时, 启动DuckDB评估:

| 指标 | 阈值 | 监控方式 |
|:--|:--|:--|
| 分析查询P95延迟 | > 500ms | FastAPI中间件记录 |
| raw_daily_holding总行数 | > 50,000行 | 季度检查 |
| 追踪产品数量 | > 20个 | 配置变更时检查 |

### 6.2 预留接口

为Day 2平滑迁移, Day 1的设计包含以下预留:

| 预留项 | 说明 |
|:--|:--|
| 日期格式 | 所有日期字段使用 `TEXT` ISO 8601 (`YYYY-MM-DD`), DuckDB可直接推断为DATE |
| 分析视图 | 在argus.db中预定义SQLite视图, 使用ANSI SQL窗口函数语法 |
| 配置开关 | `argus_config.yaml` 预留 `DUCKDB_ENABLED: false` 开关 |
| 查询抽象 | 分析查询通过函数封装, Day 2切换时仅修改底层实现 |

### 6.3 Day 2架构 (预览)

```text
Day 2 架构 (触发条件满足后):

  argus.db (SQLite)
       |
       | ATTACH (READ_ONLY)
       v
  argus_analytics.duckdb (DuckDB)
       |
       +-- v_product_rolling_accuracy    产品滚动胜率
       +-- v_signal_bayesian_fusion      多时间框架融合
       +-- v_consensus_heatmap           行业x产品共识热力图
       +-- v_darwin_event_backtest       达尔文事件回测统计
       +-- v_direction_timeseries        景气度方向时序
       +-- v_opportunity_matrix          机会矩阵
```

DuckDB通过 `ATTACH 'argus.db' AS argus (TYPE sqlite, READ_ONLY)` 零拷贝读取SQLite数据, 提供6个分析视图。FastAPI在检测到 `DUCKDB_ENABLED: true` 时, 将分析查询路由到DuckDB, 其余查询仍走SQLite。

---

## 7 Daily Workflow架构 {#ARGUS-02:daily-workflow}

```text
每日工作流 (Steps 1-3 无需LLM, Steps 4-5 需要Claude):

Step 1: DATA IMPORT (Code, 确定性)
  ├─ 读取今日Excel文件 (交易+持仓+NAV)
  ├─ 解析、校验、写入Raw tables
  └─ 输出导入报告 (行数/异常数)

Step 2: PROCESSING (Code, 确定性)
  ├─ Raw -> Processed: 清洗、去重、标准化
  ├─ 更新产品画像 (argus_product_profile)
  ├─ 计算调仓路径事件 (argus_rebalancing_event)
  └─ 更新产品信誉 (贝叶斯Beta更新)

Step 3: SCORING + DECISION (Code, 确定性)
  ├─ 运行信号引擎 (FAST/MEDIUM/SLOW)
  ├─ 贝叶斯融合
  ├─ 达尔文时刻检测
  ├─ 共识方向更新
  ├─ 池管理 (晋升/降级/清除)
  └─ 输出 argus_recommendation.json

Step 4: INTERPRETATION (Claude, 判断性)
  ├─ 读取recommendation JSON
  ├─ 对比昨日变化
  ├─ 生成daily brief (自然语言)
  └─ [可选] 运行roundtable

Step 5: ALERT (Code + Claude)
  ├─ 矛盾检测 (ARGUS vs Empire)
  └─ 异常检测 (信号量暴增/暴跌)
```

**关键设计**: Steps 1-3可独立运行, 可用Windows Task Scheduler定时执行 (`python argus_daily.py`)。即使Claude不在线, ARGUS的scoring照常运行。Steps 4-5为增值层。

---

**[存证]**
ARGUS-02 v2.0.0-draft | 2026-04-12
参考来源: Expert Panel WG1 (DB架构决议) + WG3 (技术栈+部署) + WG4 (Code/Claude边界) + WG5 (简化要求)
重构要点: 从Empire子模块到独立系统; 三层单库SQLite; DuckDB Day 2预留; JSON+Claude接口; 一键启动部署
SOP完成: 启动-热场-参考-撰写-复查-收尾
