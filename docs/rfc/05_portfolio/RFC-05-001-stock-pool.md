# RFC-05-001: Portfolio 股票池数据模型与 CRUD

## 元数据（Metadata）
| 项 | 值 |
|---|---|
| 状态 | 草稿 |
| 作者 | YQuant |
| 创建日期 | 2026-05-19 |
| 最后更新 | 2026-05-26 |
| 所属模块 | portfolio |
| 依赖RFC | RFC-08-001-argus-integration, RFC-08-002-argus-signal-interface |
| 替代RFC | docs/rfc/portfolio-stock-pool.md 的 Phase 1 实装切片 |
| AI适配 | OpenClaw / Claude Code / Codex |
| 标签 | #portfolio #stock-pool #mongodb #crud #webui |

## 1. 执行摘要
Portfolio 股票池提供 research 信号、人工研究结论与组合管理之间的候选资产管理层。Phase 1 以 MongoDB 为存储，落地四区股票池的基础数据模型、CRUD 服务和审计追踪，不直接触发交易或调仓。

## 2. 业务背景
当前 Argus、researcher、人工录入与因子扫描可以产生股票候选信号，但 portfolio 侧缺少统一入口来沉淀候选股、跟踪研究状态、记录入池证据和审计变更。股票池的业务价值在于把“发现信号”转化为“可管理的研究对象”，为后续组合构建、风控和复盘提供可追溯数据。

股票池只表达研究优先级和证据状态，不表达买卖指令。任何从股票池到交易执行的动作必须经过后续组合管理、风控和人工审批流程。

## 3. 四区定义
| 区域 | pool_zone | 含义 | 典型进入条件 | 典型动作 |
|---|---|---|---|---|
| 扫描池 | SCAN | 系统或人工首次发现的低验证度标的 | 因子扫描、新闻事件、Argus 弱信号 | 去重、补充基础信息、等待更多证据 |
| 观察池 | WATCH | 已具备初步研究价值，需要持续跟踪 | 信号分数提升、人工标记、事件持续发酵 | 加标签、补 memo、设置复核节奏 |
| 候选池 | CANDIDATE | 可进入深入研究或组合讨论的标的 | 多来源证据一致、置信度中高 | 研究建模、估值、风险预算测算 |
| 重点池 | CONVICTION | 高置信度重点跟踪标的 | 多维证据强、研究结论明确 | 进入组合候选、强化风控与复盘 |

## 4. 增量同步与审计
Portfolio 股票池通过 `StockPoolIngestionService.ingest_signals_incremental(current_signals, previous_signals, actor)` 消费 Argus 日度四区池快照，对比相邻两个交易日的 `argus_signal_pool`，将研究侧的状态变化同步到 `05_portfolio_stock_pool`，并在 `05_portfolio_stock_pool_audit` 写入精细化审计。

### 4.1 数据流
```text
08_research_argus_signal_pool(date = T-1)
08_research_argus_signal_pool(date = T)
        |
        v
StockPoolIngestionService.ingest_signals_incremental()
        |
        +--> 05_portfolio_stock_pool
        +--> 05_portfolio_stock_pool_audit
```

Phase 5 接在 Argus daily processor 的 Consensus Direction 阶段之后执行：先写入当天 `08_research_argus_signal_pool`，再读取上一交易日快照，与当天快照做 diff。生产执行 actor 固定为 `system:argus`。

### 4.2 增量同步规则
| Diff | Portfolio 动作 | Audit action | 说明 |
|---|---|---|---|
| 今日有、昨日无 | 创建 active entry | `entry` | 股票进入池子 |
| 昨日有、今日无 | 置为 inactive | `exit` | 股票退出池子 |
| 今日 zone 高于昨日 zone | 更新 `pool_zone` 与字段 | `promote` | zone 升级 |
| 今日 zone 低于昨日 zone | 更新 `pool_zone` 与字段 | `demote` | zone 降级 |
| zone 不变但字段变化 | 更新字段 | `update` | 同区字段刷新 |
| 无变化 | 跳过 | 无 | 不写审计，避免噪音 |

zone 顺序为 `SCAN < WATCH < CANDIDATE < CONVICTION`。Argus 旧字段 `FOCUS` 在 Portfolio 侧映射为 `CONVICTION`。

### 4.3 Audit action 类型
| Action | 触发来源 | 说明 |
|---|---|---|
| `entry` | 用户手动 / Argus 增量 | 股票进入池子 |
| `promote` | AutoPromoter / Argus 增量 | zone 升级 |
| `demote` | AutoPromoter / Argus 增量 | zone 降级 |
| `exit` | Argus 增量 | 股票退出池子 |
| `update` | 用户/系统 | 同区字段更新 |
| `request_transition` | 用户 | 申请待审批，保留现有审批语义 |

`create_entry()` 的创建审计使用 `entry`，不再使用旧的 `create`。`request_transition` 仍只表示用户申请，不直接改 `pool_zone`。

### 4.4 actor 字段规范
| actor | 来源 |
|---|---|
| `user:xxx` | 用户手动操作 |
| `system:argus` | Argus 日度增量同步 |
| `system:auto_promoter` | 自动升级任务 |
| `system:argus_backfill` | 历史审计回补 |

所有系统写入必须带明确 actor，避免把日度同步、自动升级和历史回补混在同一审计来源中。

### 4.5 历史回补脚本设计
`skills/portfolio/stock_pool/backfill_audit.py` 用于从历史 `08_research_argus_signal_pool` 重建 Portfolio audit：
- 输入：`--start-date`、`--end-date`、可选 `--database`。
- 处理：按交易日顺序读取每天 `argus_signal_pool`，从第二天开始对比相邻两天，调用 `ingest_signals_incremental(current, previous, actor="system:argus_backfill")`。
- 输出：每个日期的 entry/promote/demote/exit/update/skipped 计数与总汇总。
- 约束：不修改数据模型；不触碰 `request_transition`；不改变 AutoPromoter 定时配置。

## 5. 数据模型
### 5.1 Collection: 05_portfolio_stock_pool
| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| _id | ObjectId | 是 | MongoDB 主键 |
| stock_code | string | 是 | 本地股票代码，如 600519 |
| wind_code | string | 是 | Wind 统一代码，如 600519.SH |
| stock_name | string | 是 | 股票名称 |
| pool_zone | enum | 是 | SCAN/WATCH/CANDIDATE/CONVICTION |
| source | enum | 是 | argus/manual/researcher/factor_scan/news/other |
| entry_reason | object | 是 | signal_type、score、confidence、evidence 等入池证据 |
| entry_date | datetime | 是 | 入池时间 |
| exit_date | datetime/null | 否 | 出池时间 |
| status | enum | 是 | active/inactive |
| tags | string[] | 否 | 研究标签 |
| memo | string | 否 | 人工备注 |
| audit | object | 是 | created_at、updated_at、created_by、updated_by |
| pending_transition | object/null | 否 | 待审批迁移请求，Phase 3 完成 approve/reject |

### 5.2 Collection: 05_portfolio_stock_pool_audit
| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| _id | ObjectId | 是 | 审计记录 ID |
| pool_id | string | 是 | 05_portfolio_stock_pool 记录 ID |
| action | string | 是 | entry/promote/demote/exit/update/request_transition |
| before | object/null | 否 | 变更前快照 |
| after | object/null | 否 | 变更后快照 |
| actor | string | 是 | 操作者 |
| created_at | datetime | 是 | 审计时间 |

### 5.3 索引
\`\`\`javascript
db.getCollection("05_portfolio_stock_pool").createIndex({ pool_zone: 1, status: 1 }, { name: "idx_stock_pool_zone_status" });
db.getCollection("05_portfolio_stock_pool").createIndex({ wind_code: 1 }, { name: "idx_stock_pool_wind_code" });
db.getCollection("05_portfolio_stock_pool").createIndex({ source: 1, entry_date: -1 }, { name: "idx_stock_pool_source_entry_date" });
db.getCollection("05_portfolio_stock_pool").createIndex({ status: 1, entry_date: -1 }, { name: "idx_stock_pool_status_entry_date" });
db.getCollection("05_portfolio_stock_pool_audit").createIndex({ pool_id: 1, created_at: -1 }, { name: "idx_stock_pool_audit_pool_created" });
\`\`\`

## 6. API 接口
Phase 1 不创建 HTTP 路由；\`skills/portfolio/stock_pool/api.py\` 只提供 FastAPI 依赖注入函数，供 TradingAgents-CN 或其他上层应用挂载路由时复用。

### 6.1 Repository
- \`list(pool_zone, source, status, wind_code, limit, cursor) -> dict\`：按条件分页查询股票池。
- \`create(record, actor) -> str\`：创建股票池记录。
- \`update_fields(record_id, patch, actor) -> bool\`：局部更新。
- \`deactivate(record_id, exit_date, reason, actor) -> bool\`：置为 inactive 并写出池原因。
- \`write_audit(pool_id, action, before, after, actor) -> str\`：写审计记录。

### 6.2 Service
- \`get_pool(...)\`：查询股票池。
- \`create_entry(record, actor)\`：校验并创建记录，同时写审计。
- \`update_entry(record_id, patch, actor)\`：读取 before，更新字段，写审计。
- \`request_zone_transition(record_id, target_zone, reason, actor)\`：创建待审批迁移请求；Phase 3 再实现 approve/reject。

## 7. 流转规则
- 允许的区域序列为 SCAN → WATCH → CANDIDATE → CONVICTION，也允许降级或退回，但所有跨区变更必须保留审计。
- Phase 1 的 \`request_zone_transition\` 只记录申请，不直接修改 \`pool_zone\`。
- inactive 记录不可发起迁移；需要重新进入股票池时创建新的 active 生命周期。
- \`deactivate\` 必须记录 \`exit_date\` 和出池原因。
- 同一 \`wind_code\` 可保留多条历史记录；上层聚合视图按 active 记录与最新 entry_date 展示。

## 8. WebUI 方案
WebUI 由 TradingAgents-CN 承载，Portfolio 模块提供数据与服务依赖：
- 四列看板：SCAN、WATCH、CANDIDATE、CONVICTION。
- 顶部过滤器：来源、状态、Wind 代码、标签、入池时间。
- 卡片字段：股票名称、Wind 代码、来源、分数、置信度、标签、最近更新时间。
- 详情抽屉：entry_reason 证据、memo、审计时间线、待审批迁移状态。
- 拖拽跨区：仅调用 \`request_zone_transition\` 创建申请，不直接改区。
- inactive 标的默认隐藏，可通过状态过滤查看历史。

## 9. 验收标准
- 新增 stock_pool 模块具备模型、repository、service、api 四层文件。
- MongoDB 连接默认指向 \`172.25.240.1:27017/tradingagents\`。
- 单元测试覆盖模型字段验证、repository CRUD、service 审计与迁移申请逻辑。
- 测试命令 \`python3 -m unittest discover -s skills/portfolio/tests -v\` 通过。

## 版本记录（Changelog）
| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-05-19 | Phase 1 数据模型与 CRUD RFC 初稿 | YQuant |
| V1.1 | 2026-05-26 | 新增 Argus 增量同步与精细化审计设计 | YQuant |
