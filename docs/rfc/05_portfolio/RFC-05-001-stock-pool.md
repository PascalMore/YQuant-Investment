# RFC-05-001: Portfolio 股票池数据模型与 CRUD

## 元数据（Metadata）
| 项 | 值 |
|---|---|
| 状态 | 草稿 |
| 作者 | YQuant |
| 创建日期 | 2026-05-19 |
| 最后更新 | 2026-05-19 |
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

## 4. 数据模型
### 4.1 Collection: portfolio_stock_pool
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

### 4.2 Collection: portfolio_stock_pool_audit
| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| _id | ObjectId | 是 | 审计记录 ID |
| pool_id | string | 是 | portfolio_stock_pool 记录 ID |
| action | string | 是 | create/update/deactivate/request_transition |
| before | object/null | 否 | 变更前快照 |
| after | object/null | 否 | 变更后快照 |
| actor | string | 是 | 操作者 |
| created_at | datetime | 是 | 审计时间 |

### 4.3 索引
\`\`\`javascript
db.portfolio_stock_pool.createIndex({ pool_zone: 1, status: 1 }, { name: "idx_stock_pool_zone_status" });
db.portfolio_stock_pool.createIndex({ wind_code: 1 }, { name: "idx_stock_pool_wind_code" });
db.portfolio_stock_pool.createIndex({ source: 1, entry_date: -1 }, { name: "idx_stock_pool_source_entry_date" });
db.portfolio_stock_pool.createIndex({ status: 1, entry_date: -1 }, { name: "idx_stock_pool_status_entry_date" });
db.portfolio_stock_pool_audit.createIndex({ pool_id: 1, created_at: -1 }, { name: "idx_stock_pool_audit_pool_created" });
\`\`\`

## 5. API 接口
Phase 1 不创建 HTTP 路由；\`skills/portfolio/stock_pool/api.py\` 只提供 FastAPI 依赖注入函数，供 TradingAgents-CN 或其他上层应用挂载路由时复用。

### 5.1 Repository
- \`list(pool_zone, source, status, wind_code, limit, cursor) -> dict\`：按条件分页查询股票池。
- \`create(record, actor) -> str\`：创建股票池记录。
- \`update_fields(record_id, patch, actor) -> bool\`：局部更新。
- \`deactivate(record_id, exit_date, reason, actor) -> bool\`：置为 inactive 并写出池原因。
- \`write_audit(pool_id, action, before, after, actor) -> str\`：写审计记录。

### 5.2 Service
- \`get_pool(...)\`：查询股票池。
- \`create_entry(record, actor)\`：校验并创建记录，同时写审计。
- \`update_entry(record_id, patch, actor)\`：读取 before，更新字段，写审计。
- \`request_zone_transition(record_id, target_zone, reason, actor)\`：创建待审批迁移请求；Phase 3 再实现 approve/reject。

## 6. 流转规则
- 允许的区域序列为 SCAN → WATCH → CANDIDATE → CONVICTION，也允许降级或退回，但所有跨区变更必须保留审计。
- Phase 1 的 \`request_zone_transition\` 只记录申请，不直接修改 \`pool_zone\`。
- inactive 记录不可发起迁移；需要重新进入股票池时创建新的 active 生命周期。
- \`deactivate\` 必须记录 \`exit_date\` 和出池原因。
- 同一 \`wind_code\` 可保留多条历史记录；上层聚合视图按 active 记录与最新 entry_date 展示。

## 7. WebUI 方案
WebUI 由 TradingAgents-CN 承载，Portfolio 模块提供数据与服务依赖：
- 四列看板：SCAN、WATCH、CANDIDATE、CONVICTION。
- 顶部过滤器：来源、状态、Wind 代码、标签、入池时间。
- 卡片字段：股票名称、Wind 代码、来源、分数、置信度、标签、最近更新时间。
- 详情抽屉：entry_reason 证据、memo、审计时间线、待审批迁移状态。
- 拖拽跨区：仅调用 \`request_zone_transition\` 创建申请，不直接改区。
- inactive 标的默认隐藏，可通过状态过滤查看历史。

## 8. 验收标准
- 新增 stock_pool 模块具备模型、repository、service、api 四层文件。
- MongoDB 连接默认指向 \`172.25.240.1:27017/tradingagents\`。
- 单元测试覆盖模型字段验证、repository CRUD、service 审计与迁移申请逻辑。
- 测试命令 \`python3 -m unittest discover -s skills/portfolio/tests -v\` 通过。

## 版本记录（Changelog）
| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-05-19 | Phase 1 数据模型与 CRUD RFC 初稿 | YQuant |
