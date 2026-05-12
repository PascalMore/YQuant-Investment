---
file_id: ARGUS-05
title: "设计 — 股票池管理与 Web 界面 / Stock Pool Management & Web Interface"
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
  - "ARGUS-04 (信号引擎与评分系统: 六层架构 + 贝叶斯融合)"
  - "EXPERT_PANEL_WG1_WG2 (WG1-D4: REST API 为主通信通道)"
  - "EXPERT_PANEL_WG3_WG4_WG5 (API 与部署工程评审)"
  - "WEB_INTERFACE_SPEC (ARGUS-WEB: 原始界面规格)"
amendment_level: L2
language: "zh-CN / en"
---

# ARGUS-05: 股票池管理与 Web 界面

# ARGUS-05: Stock Pool Management & Web Interface

> **本文件是 RFC-2026-071 ARGUS 百目巨人独立系统 v2.0 的股票池管理规则和完整 Web 界面规格。**
> 覆盖四区动态股票池、周更新与季校准、与 Empire 的推荐接口、Web 界面 8 页面规格、交互规则、API 端点清单。
> 信号引擎与评分详见 ARGUS-04; 高级分析层详见 ARGUS-06。

---

## SS1 四区动态股票池 {#ARGUS-05:four-zone}

### 1.1 四区定义 / Zone Definitions {#ARGUS-05:zone-definitions}

| 区域 Zone | 容量 Cap | 入池条件 Entry | 出池条件 Exit | 与 Empire 映射 |
|:--|:--:|:--|:--|:--|
| **SCAN** | 无限 | 任何 quality_pass 产品的信号 | 30 天无更新 | (不映射) |
| **WATCH** | <= 30 | bayesian >= 0.30 且 product_count >= 2 | score < 0.20 或 KILL 区 | OBSERVE 候选 |
| **CANDIDATE** | <= 15 | bayesian >= 0.50 且 consensus >= 0.40 | score < 0.35 或连续 2 周下降 | OBSERVE / CANDIDATE |
| **CONVICTION** | <= 8 | bayesian >= 0.70 且 product_count >= 3 且 crowding < DANGER | 产品退出或基本面破裂 | CANDIDATE 晋升 |

### 1.2 动态容量机制 (REV-016) {#ARGUS-05:dynamic-capacity}

当市场处于不同状态时，池容量自动调整:

| 市场状态 | WATCH | CANDIDATE | CONVICTION | 触发条件 |
|:--|:--:|:--:|:--:|:--|
| 正常 | 30 | 15 | 8 | 默认 |
| 高波动 | 25 | 12 | 6 | 市场月波动率 > 2x 均值 |
| 极端恐慌 | 20 | 10 | 5 | 沪深 300 月跌幅 > 10% |

容量收缩时，自动将超额标的中 composite_score 最低者降级一区。

### 1.3 两阶段过滤 / Two-Stage Filtering {#ARGUS-05:two-stage-filter}

**阶段一 -- 入池过滤 (Admission Filter)**:
- 标的必须有至少 1 个 quality_pass 产品的信号
- bayesian_posterior >= 区域最低阈值
- 数据完整性检查: 标的有近 5 日行情数据

**阶段二 -- 净化过滤 (Purification Filter)**:
- 拥挤度检查: KILL 区标的不得进入 WATCH 以上
- 矛盾信号检查: 有高信誉产品卖出时降低信号权重
- 流动性检查: 日均成交额 < 5000 万的标的不入 CANDIDATE 以上

### 1.4 升降级路径 / Promotion & Demotion Path {#ARGUS-05:promotion-demotion}

```
SCAN ──[bayesian>=0.30, products>=2]──> WATCH
WATCH ──[bayesian>=0.50, consensus>=0.40]──> CANDIDATE
CANDIDATE ──[bayesian>=0.70, products>=3, crowding<DANGER]──> CONVICTION

CONVICTION ──[产品退出/基本面破裂]──> CANDIDATE
CANDIDATE ──[score<0.35 连续2周]──> WATCH
WATCH ──[score<0.20 或 KILL区]──> SCAN
SCAN ──[30天无更新]──> ARCHIVE (移出池)

任何区域 ──[手动归档 (Web UI)]──> ARCHIVE
```

---

## SS2 周更新与季校准 {#ARGUS-05:weekly-quarterly}

### 2.1 周五六步工作流 (REV-025) / Friday 6-Step Workflow {#ARGUS-05:friday-workflow}

每周五收盘后执行，总预算 120 分钟:

| Step | 步骤 | 耗时 | 操作 |
|:--:|:--|:--:|:--|
| 1 | 数据刷新 | 15 min | 摄取本周 T+1 交易记录 + 持仓快照至 `argus_raw.db` |
| 2 | 信号处理 | 20 min | Layer 2 调仓检测 + Layer 3 三框架信号生成 |
| 3 | 贝叶斯融合 | 15 min | Layer 4 后验更新 + 复合评分 |
| 4 | 两阶段过滤 | 10 min | 入池过滤 + 净化过滤 |
| 5 | 池调整 | 15 min | 升降级执行 + 容量检查 + 归档到期标的 |
| 6 | 输出与推荐 | 45 min | 生成推荐 JSON + 更新 Web 数据 + 触发 Graphify (V2) |

**自动化**: Steps 1~5 由 CLI 脚本自动执行; Step 6 部分需 Claude 会话参与 (推荐文案生成)。

### 2.2 季度校准 / Quarterly Recalibration {#ARGUS-05:quarterly-recal}

季报发布后约 15 天执行:

| 步骤 | 操作 |
|:--|:--|
| 1 | 摄取季报/年报真实持仓 (T0 Tier) |
| 2 | 对比日度估算 vs 真实持仓，计算估算误差 |
| 3 | 检测所有调仓事件 (含隐形重仓: 年报全持仓 vs 季报前十) |
| 4 | 重算 HHI 集中度 |
| 5 | 更新产品信誉 (D2 accuracy 用真实数据校正) |
| 6 | 全池重评分 + 容量检查 |
| 7 | BASE_RATE 季度重估 (INV-12/Kahneman 建议) |

---

## SS3 与 Empire 的推荐接口 {#ARGUS-05:empire-interface}

### 3.1 通信架构 (WG1-D4/D5) {#ARGUS-05:comm-arch}

**主通道**: REST API (ARGUS FastAPI :8001 -> Empire 通过 HTTP GET 读取)
**备用通道**: JSON 文件交换 (故障降级，最多 24 小时延迟)
**核心约束**: Empire 禁止直接访问 ARGUS 数据库文件 (WG1-D6)

```
┌──────────────┐                    ┌──────────────┐
│  ARGUS       │   REST API (:8001) │  Empire V9   │
│  argus.db    │◄──────────────────>│  empire_data  │
│  FastAPI     │   GET /api/v1/...  │  .db         │
│              │   POST /feedback   │  FastAPI     │
│              │                    │  (:8000)     │
│  每日生成:    │   JSON 备用通道     │              │
│  argus_daily │───────────────────>│  读取 JSON   │
│  _brief.json │                    │  (降级模式)   │
└──────────────┘                    └──────────────┘
```

### 3.2 CONVICTION -> Empire 推荐流 {#ARGUS-05:conviction-export}

CONVICTION 区标的自动生成推荐 JSON:

```json
{
  "date": "2026-04-12",
  "source": "ARGUS_v2.0",
  "recommendations": [
    {
      "stock_code": "300274",
      "stock_name": "阳光电源",
      "pool_zone": "CONVICTION",
      "composite_score": 0.82,
      "bayesian_posterior": 0.78,
      "contributing_products": ["中欧1号", "景顺长城2号", "睿远3号"],
      "consensus_strength": 0.72,
      "crowding_zone": "SAFE",
      "confidence_level": "HIGH",
      "checklist_score": "3/5"
    }
  ]
}
```

### 3.3 Claude 桥接 IC 讨论 {#ARGUS-05:claude-bridge}

Claude 在 IC (投资委员会) 讨论中作为 ARGUS 代言人:

| IC 模式 | 触发 | ARGUS 提供 |
|:--|:--|:--|
| IC-FAST (快审) | CONVICTION 区 bayesian >= 0.80 | 信号摘要 + 产品列表 + 共识强度 |
| IC-FULL (全审) | CONVICTION -> HOLDING 升级 | 完整档案: T-1 行为 + 调仓路径 + 拥挤 + 回测历史 |

**Empire 权限**: Empire 对 ARGUS 推荐拥有完全的接受/拒绝权。ARGUS 是情报盟友，不是指令发出者。

---

## SS4 Web 界面总览 {#ARGUS-05:web-overview}

### 4.1 技术栈 / Tech Stack {#ARGUS-05:tech-stack}

| 组件 | 技术选型 | 说明 |
|:--|:--|:--|
| 后端 | Python + FastAPI | ARGUS 独立 FastAPI (:8001) |
| 模板 | Jinja2 | 服务端渲染 HTML |
| 交互 | HTMX | 无 JavaScript 框架，声明式局部更新 |
| 样式 | Pico CSS | 语义化 classless CSS，最小化自定义 |
| 数据库 | SQLite (`argus.db`) | Claude 写 / FastAPI 读 |
| 图表 | Inline SVG | 服务端生成，无前端图表库 |

### 4.2 设计模式: D 混合布局 / D Hybrid Layout {#ARGUS-05:layout}

主要页面采用 D 混合布局: 左侧主内容区 (信号列表 / 池管理 / 产品表) + 右侧边栏 (预警 / 快捷操作)。

```
┌───────────────────────────────────────────────────────────┐
│ [nav] ARGUS 百目巨人  仪表盘 信号 股票池 产品 分析 回测 设置 │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─────────────── main (75%) ──────────┐ ┌── aside (25%) │
│  │                                     │ │               │
│  │  [页面主体内容]                      │ │  [预警卡片]    │
│  │  信号列表 / 池视图 / 产品表          │ │  [快捷操作]    │
│  │                                     │ │  [系统状态]    │
│  │                                     │ │               │
│  └─────────────────────────────────────┘ └───────────────│
├───────────────────────────────────────────────────────────┤
│ [footer] ARGUS v2.0 | argus.db | 数据截至 2026-04-11     │
└───────────────────────────────────────────────────────────┘
```

### 4.3 页面清单 / Page Registry (8 Pages) {#ARGUS-05:page-registry}

| # | 页面名 | URL | 用途 |
|:--:|:--|:--|:--|
| 1 | 仪表盘 Dashboard | `/` | 每日首屏: 信号看板 + 池状态 + 产品排行 + 预警 |
| 2 | 信号详情 Signals | `/signals` | 全量信号历史 + 多维过滤 |
| 3 | 股票池管理 Pool | `/pool` | 四区全景 + 升降级/归档/备注 |
| 4 | 产品档案 Products | `/products/{id}` | 单产品深度: 操作/持仓/胜率/风格 |
| 5 | 个股详情 Stocks | `/stocks/{code}` | 单股全认知: 谁在关注/信号/池状态/共识 |
| 6 | **深度分析 Analysis** | `/analysis` | **V2 新增**: Darwin + 共识方向 + 机会透镜 + 因果链 |
| 7 | 回测仪表盘 Backtest | `/backtest` | 信号精度追踪 + 产品/意图/操作分解 |
| 8 | 系统设置 Settings | `/settings` | 参数只读展示 + 系统状态 + 数据健康 |

---

## SS5 页面规格 {#ARGUS-05:pages}

### 5.1 PAGE 1: 仪表盘 `/` {#ARGUS-05:page-dashboard}

**URL**: `/`
**Purpose**: 用户每日首屏。一目了然: 昨日信号、池状态、产品排行、异常预警。

**Layout**: 四面板 2x2 网格 (Panel A 信号看板 / B 池状态 / C 产品排行 / D 预警)

| Panel | 内容 | 数据源 | HTMX |
|:--|:--|:--|:--|
| A 信号看板 | 信号表: 产品/股票/操作/金额/AUM%/意图/拥挤 | `proc_rebalancing_event` | `load, every 300s` |
| B 池状态 | 四区卡片: 容量+Top-3+今日变动+升降按钮 | `dec_stock_pool` | `load, every 300s` |
| C 产品排行 | Top-5: 信誉+胜率+30日 SVG 趋势线 | `proc_product_profile` | `load` |
| D 预警 | 三类: 矛盾(红)/拥挤(橙)/共识(蓝)+"已知悉" | `dec_consensus` 聚合 | `load, every 300s` |

**变更通知 (REV-036)**:
仪表盘顶部显示"自上次查看以来"的变更摘要:
- 记录用户最后访问时间（浏览器localStorage）
- 对比: 上次访问 vs 当前 argus_stock_pool_history 最新记录
- 显示: "自上次查看，池变动: +2进入 -1归档 ↑1升级"
- 高亮: 所有在上次访问之后变更的行

视觉规则: 买入行浅绿/卖出行浅红, HEAVY 粗体, PROBE 半透明

### 5.2 PAGE 2: 信号详情 `/signals` {#ARGUS-05:page-signals}

**URL**: `/signals`
**Purpose**: 全量信号历史浏览与管理，多维度过滤，日常深度审查。

**Layout**: 过滤器栏 (6 个 HTMX 无刷新过滤: 日期/产品/股票/操作/意图/状态) + 信号表格 (11 列: 日期/产品/股票/操作/金额/AUM%/意图/共识数/拥挤/状态/操作按钮) + 分页 (50 条/页, `hx-push-url`)

**操作按钮**: "已知悉" (ACTIVE 时) | "忽略" (带确认) | "备注" (展开输入框)

### 5.3 PAGE 3: 股票池管理 `/pool` {#ARGUS-05:page-pool}

**URL**: `/pool`
**Purpose**: 四区全景视图，支持升降级、归档、备注。

**Layout**: 池健康摘要栏 (四区容量 + 今日变动 + 到期/矛盾警示) + 四列视图 (每列一个区域, 按 composite_score 降序排列股票卡片)

**股票卡片字段**: 代码+名称 | composite_score | 贡献产品(max 3) | 共识强度 | 拥挤区域 | 本区天数 | 末次信号日

**操作按钮**: 升级 (POST promote, hx-confirm) | 降级 (POST demote, hx-confirm) | 归档 (展开原因输入, reason 必填) | 备注 (展开文本框)

**审计**: 所有操作 `triggered_by='WEB_UI'`，写入 `dec_stock_pool_history`

### 5.4 PAGE 4: 产品档案 `/products/{id}` {#ARGUS-05:page-products}

**URL**: `/products` (列表) / `/products/{product_id}` (详情)
**Purpose**: 单个基金产品深度分析。纯只读。

**列表页**: 产品名 | 规模 | 信誉 | 风格 | 信号数 | 近 30 日胜率

**详情页 5 Sections**: Header (规模/信誉/风格/排名) | A 近期操作 30 天 (日期/股票/操作/金额/意图/盈亏) | B 当前持仓 (股票/持股/市值/权重/日变化) | C 持仓变化趋势 (Top-10 inline SVG 水平柱状图) | D 信号胜率 (5D/10D/20D, 含验证覆盖率) | E 行业分布 (申万一级, Top-10 + "其他")

### 5.5 PAGE 5: 个股详情 `/stocks/{code}` {#ARGUS-05:page-stocks}

**URL**: `/stocks/{stock_code}`
**Purpose**: ARGUS 对单只股票的全部认知汇总。

**5 Sections**: Header (代码/名称/池区域/分数) | A 谁在关注 (产品/操作/方向/金额/权重/信誉, 按信誉降序) | B 信号历史 (日期/来源/类型/方向/分数/状态, 最近 30 条) | C 池状态 (区域/分数/入区日期/天数/完整升级路径时间线) | D 共识情况 + E 拥挤度 | Munger Checklist (V1: 3/5, V2: 5/7)

**特殊**: 不在池中显示 "加入观察" (`POST /api/pool/add-scan`)

### 5.6 PAGE 6: 深度分析 `/analysis` (V2 New) {#ARGUS-05:page-analysis}

**URL**: `/analysis`
**Purpose**: **V2 新增页面**。聚合高级分析层输出: Darwin 时刻、共识方向、机会透镜、因果链。

**4 Sections**: A 达尔文时刻 (Darwin 卡片: 行业/回调/弱手退出/强手加仓/信心度/历史胜率) | B 共识方向引擎 (景气度 gauge + 信念偏移热力图 + 行业柱状图) | C 机会透镜 (Munger Checklist 卡片集, V1: 3 项 / V2: 5 项) | D 因果链 (V1: 占位提示; V2: Timeline 可视化)

详细功能规格见 ARGUS-06。

### 5.7 PAGE 7: 回测仪表盘 `/backtest` {#ARGUS-05:page-backtest}

**URL**: `/backtest`
**Purpose**: 信号精度追踪与统计分析。纯只读。

**Layout**: 总体统计卡片 (6 张: 总信号/5D/10D/20D 胜率/超额/覆盖率) + 4 Sections: A 按产品分解 | B 按意图级别 (验证"重仓更准确"假设) | C 按操作类型 (买入/卖出) | D 月度趋势 (6 月 SVG 折线图, 60% 参考线)

**INV-12 要求**: 同时展示失败案例，校准用户信心。

### 5.8 PAGE 8: 系统设置 `/settings` {#ARGUS-05:page-settings}

**URL**: `/settings`
**Purpose**: 系统状态监控与参数查看。只读展示。

**4 Sections**: A 参数概览 (只读表格, 醒目 CLI-only 提示) | B 系统状态 (DB 大小/导入时间/记录数/产品数) | C 数据健康 (缺失日期/NAV 缺口/完整度, 颜色编码) | D 关于 (版本/RFC/技术栈)

---

## SS6 交互规则 {#ARGUS-05:interaction-rules}

### 6.1 Web 端允许的操作 / Allowed Web Actions {#ARGUS-05:allowed-actions}

| 操作 | 页面 | 写入表 | 审计字段 |
|:--|:--|:--|:--|
| 升级 promote | 仪表盘, 股票池 | `dec_stock_pool.pool_zone` | `_history: action=PROMOTE, triggered_by=WEB_UI` |
| 降级 demote | 仪表盘, 股票池 | `dec_stock_pool.pool_zone` | `_history: action=DEMOTE, triggered_by=WEB_UI` |
| 归档 archive | 股票池 | DELETE `dec_stock_pool` | `_history: action=ARCHIVE, reason=用户输入` |
| 标记已知悉 ack | 仪表盘, 信号 | 信号状态字段 | 时间戳记录 |
| 标记忽略 ignore | 信号 | 信号状态字段 | 时间戳记录 |
| 添加备注 note | 信号, 股票池 | `notes` 字段 | 直接写入 |
| 知悉预警 ack alert | 仪表盘 | 预警状态标记 | 时间戳记录 |
| 加入观察 add-scan | 个股详情 | INSERT `dec_stock_pool` | `_history: action=ENTER` |

### 6.2 Web 端禁止的操作 / Forbidden Web Actions {#ARGUS-05:forbidden-actions}

| 操作 | 原因 | 替代路径 |
|:--|:--|:--|
| 数据导入 | 复杂 ETL 流程 | CLI 脚本 / Claude 会话 |
| 参数变更 (ARG-*) | 影响评分引擎 | CLI / Claude 审慎决策 |
| 评分重算 | 计算密集 | CLI 批量执行 |
| 产品注册/编辑 | 低频操作 | Claude 会话 |
| 池容量变更 | 影响 REV-016 | CLI 配置 |
| 回测触发 | 需指定参数 | CLI 执行 |

### 6.3 确认对话框规则 {#ARGUS-05:confirm-dialogs}

所有状态变更操作 (升级/降级/归档) 使用 `hx-confirm`:
- 文案包含操作对象名称 + 具体动作 (从哪到哪)
- 归档额外要求填写原因 (非空校验)
- 所有写操作返回更新后的 HTML fragment

### 6.4 审计追踪 / Audit Trail {#ARGUS-05:audit-trail}

所有 Web 操作写入 `dec_stock_pool_history`:
- `triggered_by = 'WEB_UI'`
- `reason` 记录操作上下文
- `created_at` 自动记录时间

---

## SS7 API 端点清单 {#ARGUS-05:api-registry}

### 7.1 已有 JSON API (数据查询) {#ARGUS-05:api-json}

| # | 路径 | 方法 | 用途 |
|:--:|:--|:--:|:--|
| 1 | `/api/v1/argus/products` | GET | 产品列表 + 信誉 |
| 2 | `/api/v1/argus/products/{id}/signals` | GET | 产品信号历史 |
| 3 | `/api/v1/argus/products/{id}/profile` | GET | 产品完整画像 |
| 4 | `/api/v1/argus/pool` | GET | 池全区域总览 |
| 5 | `/api/v1/argus/pool/zone/{zone}` | GET | 按区域过滤 |
| 6 | `/api/v1/argus/pool/history` | GET | 池变更审计 |
| 7 | `/api/v1/argus/signals` | GET | 活跃信号 (可按时间框架过滤) |
| 8 | `/api/v1/argus/signals/consensus` | GET | 共识信号 |
| 9 | `/api/v1/argus/leaderboard` | GET | 产品信誉排行 |
| 10 | `/api/v1/argus/accuracy` | GET | 回测精度 |
| 11 | `/api/v1/argus/crowding` | GET | 拥挤度叠加 ARGUS 池 |
| 12 | `/api/v1/argus/ah-divergence` | GET | AH 溢价背离 |
| 13 | `/api/v1/argus/weekly-report` | GET | 周报 (HTMX fragment) |
| 14 | `/api/v1/argus/sse/signals` | GET(SSE) | 实时信号推送 |
| 15 | `/api/v1/argus/recommendations` | GET | CONVICTION 推荐 (Empire 消费) |
| 16 | `/api/v1/argus/feedback` | POST | Empire 反馈通道 |
| 17 | `/api/v1/argus/darwin-events` | GET | 达尔文时刻事件 (V1) |
| 18 | `/api/v1/argus/consensus-direction` | GET | 共识方向 (V1) |

### 7.2 页面渲染端点 (Jinja2 HTML) {#ARGUS-05:api-pages}

| # | 路径 | 方法 | 模板文件 |
|:--:|:--|:--:|:--|
| 19 | `/` | GET | `dashboard.html` |
| 20 | `/signals` | GET | `signals.html` |
| 21 | `/pool` | GET | `pool.html` |
| 22 | `/products` | GET | `products.html` |
| 23 | `/products/{product_id}` | GET | `product_detail.html` |
| 24 | `/stocks/{stock_code}` | GET | `stock_detail.html` |
| 25 | `/analysis` | GET | `analysis.html` |
| 26 | `/backtest` | GET | `backtest.html` |
| 27 | `/settings` | GET | `settings.html` |

### 7.3 HTMX Fragment 端点 (HTML 片段) {#ARGUS-05:api-fragments}

| # | 路径 | 方法 | 返回内容 | 调用页面 |
|:--:|:--|:--:|:--|:--|
| 28 | `/api/dashboard/signals` | GET | 信号面板 fragment | 仪表盘 Panel A |
| 29 | `/api/dashboard/pool` | GET | 池状态面板 fragment | 仪表盘 Panel B |
| 30 | `/api/dashboard/products` | GET | 产品排行面板 fragment | 仪表盘 Panel C |
| 31 | `/api/dashboard/alerts` | GET | 预警面板 fragment | 仪表盘 Panel D |
| 32 | `/api/signals/list` | GET | 信号表格 tbody | 信号页 (含过滤/分页) |
| 33 | `/api/pool/full` | GET | 四列池视图 | 股票池页 |
| 34 | `/api/stocks/{code}/attention` | GET | "谁在关注"表格 | 个股详情 A |
| 35 | `/api/stocks/{code}/signals` | GET | 个股信号历史 | 个股详情 B |
| 36 | `/api/analysis/darwin` | GET | 达尔文事件面板 | 深度分析 A |
| 37 | `/api/analysis/direction` | GET | 共识方向面板 | 深度分析 B |
| 38 | `/api/analysis/opportunity` | GET | 机会透镜面板 | 深度分析 C |

### 7.4 写操作端点 (POST) {#ARGUS-05:api-write}

| # | 路径 | 方法 | 请求体 | 写入表 |
|:--:|:--|:--:|:--|:--|
| 39 | `/api/pool/{id}/promote` | POST | -- | `dec_stock_pool` + `_history` |
| 40 | `/api/pool/{id}/demote` | POST | -- | `dec_stock_pool` + `_history` |
| 41 | `/api/pool/{id}/archive` | POST | `{reason}` | DELETE `_pool` + INSERT `_history` |
| 42 | `/api/pool/{id}/note` | POST | `{note}` | `dec_stock_pool.notes` |
| 43 | `/api/pool/add-scan` | POST | `{stock_code}` | INSERT `dec_stock_pool` + `_history` |
| 44 | `/api/signals/{id}/ack` | POST | -- | 信号状态 |
| 45 | `/api/signals/{id}/ignore` | POST | -- | 信号状态 |
| 46 | `/api/signals/{id}/note` | POST | `{note}` | `dec_signal.notes` |
| 47 | `/api/alerts/{id}/ack` | POST | -- | 预警状态 |

### 7.5 端点汇总 / Endpoint Summary {#ARGUS-05:api-summary}

| 类别 Category | 数量 Count | 说明 |
|:--|:--:|:--|
| JSON API (数据查询 + Empire 接口) | 18 | GET/POST, Claude + Empire 共用 |
| 页面渲染 (Jinja2) | 9 | 含 V2 新增 `/analysis` |
| HTMX Fragment | 11 | 含 V2 新增 3 个分析面板 |
| 写操作 (POST) | 9 | Simple Actions + 审计 |
| **总计 Total** | **47** | |

---

## Jinja2 模板结构 / Template Structure {#ARGUS-05:templates}

`templates/` 目录包含 9 个页面模板 (`base.html` + 8 页面) 和 13 个 fragment 模板 (`fragments/` 子目录: 4 仪表盘面板 + 6 通用组件 + 3 V2 分析面板)。

---

## 变更日志 / Changelog {#ARGUS-05:changelog}

| 版本 | 日期 | 变更内容 |
|:--|:--|:--|
| 2.0.0-draft | 2026-04-12 | 初始 V2.0 草案。从 V1.0 ARGUS-04 重构; 采纳 WG1 独立系统架构 (双库 + REST API 通信); 新增 PAGE 6 深度分析 `/analysis` (共 8 页面); API 端点从 43 增至 47; 动态容量 REV-016; 120 分钟周五工作流 REV-025; 集成 CONVICTION->Empire JSON 推荐流; 升级为产品 (非经理) 视角 |

---

## 签署与认证 / Attestation {#ARGUS-05:attestation}

| 角色 | 签署人 | 状态 | 日期 |
|:--|:--|:--|:--|
| Drafter | Internal Review Board | DRAFTED | 2026-04-12 |
| Reviewer | -- | PENDING | -- |
| Approver | Internal Review Board | PENDING | -- |

---

*ARGUS-05 v2.0.0-draft -- Stock Pool Management & Web Interface*
*RFC-2026-071 ARGUS 百目巨人独立系统*
