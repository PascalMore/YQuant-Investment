# RFC-10-009：YQuant 通用任务中心（Task Center）

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-12 |
| 最后更新 | 2026-07-12 |
| 版本号 | V0.1 |
| 所属模块 | 10_infra（基础设施） |
| 依赖RFC | RFC-10-003（infra 架构）、RFC-10-004（AI Coding Pipeline） |
| 关联RFC | RFC-03-007（Unified Data Layer） |
| 替代RFC | 无 |
| AI适配 | Hermes Kanban profile worker |
| 标签 | #infra #任务调度 #状态机 #进度追踪 #通用基础 |

### 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-12 | 初始创建，定义通用任务中心 | YQuant-Codex-Principal |

---


### Design 阶段修订说明（2026-07-12）

Pascal 明确要求 task_center 使用 MongoDB，不使用 SQLite 作为 MVP / 默认 / 生产存储。因此本 RFC 中原先的 “SQLite 优先 / MongoDB 可选” 已修订为：

- MongoDB 是默认持久化后端；
- 所有 task_center 新增集合使用 `10_infra_tc_*` 前缀；
- SQLite 仅作为本地单元测试 / 离线降级选项；
- 不复用 Hermes Kanban SQLite DB，不写 TA-CN / `03_data_ud_*` 集合。

## 1. 执行摘要

YQuant 当前的任务执行散落在三套独立的调度模式中：TA-CN 的 APScheduler + Redis Queue、系统 cron/systemd 定时脚本、以及开发阶段的临时 ad-hoc 脚本。缺少一个统一的任务注册、执行、状态追踪、错误处理和进度看板的通用中心。

本 RFC 提出在 `skills/infra/task_center/` 建立一套**纯 Python 通用任务中心**，以 Task → Job → Execution → Step 四层实体模型为核心，提供任务注册、定时调度、手动触发、进度追踪、错误重试、执行历史和暂停/恢复/取消等通用能力，作为 YQuant 所有业务模块的**唯一任务编排层**。任务中心向上服务 unified_data 的数据刷新、stock 框架的批量评分、report 的报告生成、risk 的风险扫描等所有业务模块；向下自管理持久化（MongoDB 优先，统一使用 `10_infra_tc_*` 集合前缀；SQLite 仅作为本地测试/离线降级选项），不强制绑定 Redis / Celery 等外部中间件。

---

## 2. 背景与动机

### 2.1 现状痛点

YQuant 的任务执行当前分散在以下三套模式中：

**模式 A — TA-CN APScheduler + Redis Queue（`skills/apps/TradingAgents-CN/app/services/`）**

- `scheduler_service.py`：基于 APScheduler 的定时任务管理，含任务列表查询、暂停/恢复、手动触发、执行历史
- `queue_service.py`：基于 Redis List 的 FIFO 队列，含并发控制（用户级/全局级）、可见性超时、过期任务回收
- `progress/tracker.py`：基于 Redis 的进度追踪器，支持动态步骤生成、权重驱动进度计算、时间预估
- 执行历史写入 `scheduler_executions` 和 `scheduler_history` 两个 MongoDB 集合
- 局限：强绑定 Redis + MongoDB + Web 运行环境；任务定义依赖 APScheduler 框架运行时注入；无法被其他模块独立复用

**模式 B — 系统 cron/systemd 定时脚本（`scripts/` 目录 + cron/systemd 配置）**

- `auto_push.sh`、`daily_review.py`、`global_market_report.py`、`smart_money_report.py` 等独立脚本
- 通过 crontab / systemd timer 定时触发
- 局限：无任务看板，失败只靠日志排查；状态、进度、历史不可查询；不同脚本的调度配置分散在系统级别，缺乏统一管理

**模式 C — 开发阶段 ad-hoc 脚本与手动执行**

- 数据回补、特定因子刷新、一次性分析任务等通过命令行手动触发
- 执行结果无结构化记录，只能靠终端输出判断
- 局限：不可追溯、不可复现、无法自动化

**交叉问题：**

| 问题 | 影响 |
|---|---|
| 三种任务模式无统一抽象 | 新增任务时不知道走哪种模式，标准不一致 |
| 无统一任务看板 | Pascal 无法一眼看到"哪些任务在跑、哪些失败了" |
| 无统一状态机 | TA-CN 的 status 定义（running/success/failed/missed）与 cron 脚本的 exit code + 日志模式不兼容 |
| 进度不可见 | cron 脚本完全没有进度追踪，TA-CN 的进度追踪绑定 Redis，其他模块无法复用 |
| 错误处理不统一 | TA-CN 有重试与过期任务回收，cron 脚本完全靠人工介入 |
| 任务定义分散 | 任务元数据（trigger、策略、重试规则）分散在 APScheduler 代码、crontab 文件、MongoDB `datasource_groupings` 等各处 |

### 2.2 业务价值

- **统一入口**：所有业务模块（unified_data、stock、report、risk、portfolio）通过一个任务中心注册和执行任务
- **任务看板**：Pascal 能从单一 CLI/接口看到所有任务的状态、进度、错误原因，无需在多处排查
- **可追溯**：每次执行记录结构化持久化，支持事后审计和问题复盘
- **可恢复**：失败任务可重试，运行中任务可取消，暂停任务可恢复
- **通用性**：不绑定任何具体业务数据或中间件，各模块按需注册任务
- **渐进接入**：现有 TA-CN 和 cron 脚本可逐步迁移，不要求一次性切换

### 2.3 触发原因

Pascal 要在 unified_data（数据刷新）、stock 量化分析框架（批量评分/报告生成）、report 模块（定时报告）、risk 模块（定时扫描）等场景中使用统一的任务管理能力。后续 cron 脚本和 TA-CN 的任务调度可逐步收敛到 task_center，减少碎片化。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义 Task → Job → Execution → Step 四层实体模型
- [ ] 定义任务中心在 YQuant 整体架构中的位置（infra 层，服务所有上层业务模块）
- [ ] 定义标准状态机：pending / running / success / partial_success / failed / retrying / paused / cancelled / stale
- [ ] 支持任务注册（代码/配置级别，非 UI 填表）
- [ ] 支持定时调度（cron / interval / 单次延迟）
- [ ] 支持手动触发（带参数覆盖）
- [ ] 支持进度追踪（Step 级别，权重驱动）
- [ ] 支持重试策略（max_retries / backoff / retry_on_error_types）
- [ ] 支持执行历史（查询、分页、统计）
- [ ] 支持任务暂停/恢复/取消
- [ ] 明确任务中心与 Hermes Kanban / cron 的边界
- [ ] 明确任务中心与 `unified_data` 的交互方式（任务中心调用 unified_data 的刷新接口）
- [ ] 明确任务中心与 `stock` 框架的交互方式（stock 批量任务注册为 task_center Job）
- [ ] 明确任务中心与 TA-CN 现有 scheduler/queue 的关系（长期收敛，短期并存）
- [ ] 定义 MVP 范围与分阶段 roadmap
- [ ] 定义存储方案：MongoDB 为默认持久化后端，集合前缀 `10_infra_tc_*`；SQLite 仅作为本地测试/离线降级选项

### 3.2 非目标（Out of Scope）

- [ ] **不做 Design 级设计**：本 RFC 只定义 WHAT 和 WHY，不定义 HOW（具体文件清单、类图、函数签名等由后续 Design 阶段产出）
- [ ] **不实现代码**：本阶段只产出 RFC + SPEC，不产出任何 `.py` 文件
- [ ] **不修改 TA-CN 现有代码**：TA-CN 的 scheduler/queue/progress 保持不动
- [ ] **不绑定 Redis / Celery / RabbitMQ**：MVP 用纯 Python + MongoDB 持久化实现，不引入外部消息队列；SQLite 仅作本地测试/离线降级
- [ ] **不做分布式执行**：任务中心在当前进程内执行，不做跨机器的 worker 调度
- [ ] **不做 Web Dashboard**：MVP 只提供 CLI 接口和 Python API，不产出 Web UI
- [ ] **不做实时告警推送**：告警和推送走现有 Telegram/企业微信通知通道，不在任务中心内实现推送逻辑
- [ ] **不替代 Hermes Kanban / cron**：Hermes 是 AI Agent 工作流编排；task_center 是业务任务执行管理。两者层次不同
- [ ] **不替代 systemd / cron 守护**：任务中心的调度器自身需要被守护（可作为 cron/systemd 的注册任务），守护能力不在本 RFC 范围内

---

## 4. 整体设计

### 4.1 核心设计哲学

**四层实体 + 单一调度器 + 纯 Python 进程内执行 + MongoDB 持久化优先**：

- 四层实体（Task → Job → Execution → Step）从抽象到具体，职责逐层递减
- Task 是**任务定义**（是什么、怎么做），Job 是**任务实例**（什么时候做、用什么参数），Execution 是**执行记录**（结果如何），Step 是**执行步骤**（做到哪了）
- 调度器在进程内运行（Python `sched` 或简单 sleep-poll 循环），不依赖外部消息队列
- 所有状态和日志写入 MongoDB `10_infra_tc_*` 集合，与 `03_data_ud_*` 和 TA-CN 无前缀集合物理隔离
- Python API 是主要操作界面，CLI 是辅助入口

### 4.2 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│          消费方（业务模块）                                       │
│  unified_data  │  stock  │  report  │  risk  │  portfolio  │  ... │
│  "刷新A股日线" │ "批量评分"│ "生成报告"│ "风险扫描"│ "持仓检查"   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 注册 Task / 查询状态 / 触发 Execution
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Task Center（通用基础层）                            │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ Task     │  │ Job      │  │ Execution    │  │ Step       │  │
│  │ 任务定义  │  │ 任务实例  │  │ 执行记录      │  │ 执行步骤   │  │
│  │ 描述     │  │ 触发类型  │  │ 状态+结果    │  │ 进度+权重  │  │
│  │ 执行函数  │  │ 参数+调度 │  │ 耗时+重试    │  │ 错误详情   │  │
│  └──────────┘  └──────────┘  └──────────────┘  └────────────┘  │
│                                                                  │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ Scheduler│  │ RetryPolicy  │  │ StateMachine             │   │
│  │ 定时/延迟 │  │ max_retries  │  │ pending→running→success   │   │
│  │ 手动触发  │  │ backoff 策略 │  │   ↕ retrying→failed      │   │
│  │ 暂停/恢复 │  │ 错误匹配     │  │   ↕ paused/cancelled     │   │
│  └──────────┘  └──────────────┘  └──────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐ │
│  │ 持久化（MongoDB默认）│  │ CLI 接口（`yq task list\|run\|...`）│ │
│  │ 10_infra_tc_*集合   │  │ Python API（`from task_center`）  │ │
│  │ tasks/jobs/execs等  │  │                                   │ │
│  └──────────────────────┘  └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│           外部依赖（可选）                                        │
│  MongoDB（默认）│ SQLite（本地降级）│ 通知通道（Telegram/企业微信）│
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 模块分工

| 模块 | 职责 | 边界 |
|---|---|---|
| `task_center` | 任务注册、调度、状态机、进度、重试、历史、暂停/恢复/取消、持久化 | 通用基础，不绑定任何业务数据源或领域逻辑 |
| `unified_data` | 统一数据访问：行情/财务/估值等数据的查询与路由 | 调用 task_center 注册定时刷新任务；不自行实现调度 |
| `stock` | 股票量化分析框架：因子计算、模型评分、报告生成 | 将批量任务注册到 task_center；不自行实现任务状态管理 |
| `report` | 报告生成模块 | 通过 task_center 定时生成报告；不自行管理 cron 调度 |
| `risk` | 风险扫描模块 | 通过 task_center 定时运行风险扫描 |
| `portfolio` | 组合管理模块 | 通过 task_center 定时检查持仓与再平衡 |
| Hermes Kanban/cron | AI Agent 工作流编排与定时任务 | 和 task_center 是不同层次：Agent 层 vs 业务层 |

---

## 5. 核心概念

### 5.1 Task（任务定义）

Task 是**任务模板**，描述"做什么"：

- `task_id`：唯一标识（如 `unified_data.daily_kline_cn`、`stock.batch_score`）
- `name`：人类可读名称
- `description`：任务说明
- `module`：所属模块（`unified_data` / `stock` / `report` / `risk` / `portfolio`）
- `callable`：执行函数引用（Python callable 路径，如 `unified_data.tasks:refresh_daily_kline_cn`）
- `default_params`：默认参数（dict）
- `tags`：标签列表（`["数据", "日线", "A股"]`）
- `retry_policy`：默认重试策略引用
- `created_at` / `updated_at`

**注册方式**：代码级别注册（Python 装饰器或函数调用），不是 Web UI 填表。

```python
# 示例伪代码 — 具体 API 由 SPEC/Design 定义
from task_center import register_task

@register_task(
    task_id="unified_data.daily_kline_cn",
    name="A股日线行情刷新",
    description="批量刷新A股日线行情数据（D1）",
    module="unified_data",
    retry_policy="default",
    tags=["数据", "日线", "A股"]
)
def refresh_daily_kline_cn(date: str, securities: list[str] | None = None):
    ...
```

### 5.2 Job（任务实例）

Job 是 Task 的**具体实例**，描述"何时、以什么参数执行"：

- `job_id`：唯一标识（UUID 或 `{task_id}.{suffix}`）
- `task_id`：关联的 Task
- `schedule`：调度规则（cron 表达式 / interval 秒数 / `once` 单次 / `manual` 仅手动触发）
- `params`：覆盖 Task 默认参数的具体参数
- `enabled`：是否启用（暂停时设为 False）
- `max_concurrent`：允许同时运行的 Execution 数量上限（默认 1）
- `timeout_seconds`：单次执行超时
- `retry_policy`：覆盖 Task 级别的重试策略（可选）
- `priority`：优先级（同类 Job 的执行排队顺序，数字越小越优先）
- `created_at` / `updated_at`

**调度规则支持三种模式**：

| 模式 | 示例 | 说明 |
|---|---|---|
| `cron` | `"0 7 * * 1-5"` | 标准 cron 表达式，工作日 7:00 AM |
| `interval` | `3600`（秒） | 固定间隔，每 3600 秒执行一次 |
| `once` | `"2026-07-15T09:00:00"` | 单次延迟执行 |
| `manual` | — | 仅手动触发，不自动调度 |

### 5.3 Execution（执行记录）

Execution 是 Job 每次运行的**具体记录**，描述"结果如何"：

- `execution_id`：唯一标识（UUID）
- `job_id`：关联的 Job
- `status`：当前状态（由状态机管理）
- `trigger`：触发方式（`scheduled` / `manual`）
- `params`：本次执行使用的参数（快照，不随 Job 参数变更而变化）
- `started_at` / `finished_at`：开始/结束时间
- `elapsed_seconds`：总耗时
- `progress_percentage`：进度百分比（0-100）
- `current_step_index`：当前执行到的 Step 索引
- `result`：执行结果（success 时为"完成"，failed 时为"失败原因"）
- `retry_count`：重试次数（初始为 0）
- `error_summary`：错误摘要（最后一次失败的原因，human-readable）
- `created_at` / `updated_at`

### 5.4 Step（执行步骤）

Step 是 Execution 内的**子步骤**，描述"做到哪了"：

- `step_id`：唯一标识
- `execution_id`：所属 Execution
- `name`：步骤名称（如"下载行情数据"、"清洗数据"、"写入缓存"）
- `description`：步骤说明
- `index`：步骤序号（从 0 开始）
- `weight`：权重（所有 Step 权重之和为 1，用于计算整体进度）
- `status`：步骤状态（`pending` / `running` / `completed` / `failed` / `skipped`）
- `started_at` / `finished_at`
- `error_message`：失败错误信息
- `data`：可选携带的结构化数据（如处理行数、耗时等）

### 5.5 RetryPolicy（重试策略）

- `policy_id`：标识
- `max_retries`：最大重试次数
- `backoff`：退避策略（`fixed` 固定间隔 / `exponential` 指数退避 / `linear` 线性退避）
- `backoff_base_seconds`：基础退避秒数
- `backoff_max_seconds`：最大退避秒数
- `retry_on_exception_types`：需重试的异常类型列表（为空则重试所有异常）
- `no_retry_on_exception_types`：不重试的异常类型列表

### 5.6 ErrorRecord（错误记录）

Execution 每次失败时产生一条 ErrorRecord：

- `error_id`：唯一标识
- `execution_id`：所属 Execution
- `attempt_number`：第几次尝试（含重试）
- `error_type`：异常类型名称
- `error_message`：异常消息
- `traceback`：完整堆栈
- `step_index`：发生在哪个 Step（可选）
- `created_at`

---

## 6. 状态机

### 6.1 状态定义

| 状态 | 含义 | 触发方式 |
|---|---|---|
| `pending` | 排队等待执行 | Job 被调度触发后，Execution 创建即进入 pending |
| `running` | 正在执行 | 调度器从队列取到 Execution 后开始执行 |
| `success` | 执行成功 | callable 正常返回（无异常） |
| `partial_success` | 部分成功 | callable 正常返回但带有警告或部分数据缺失 |
| `failed` | 执行失败 | callable 跑出异常且重试次数已用尽或不可重试 |
| `retrying` | 等待重试 | callable 抛出可重试异常，重试次数未达上限 |
| `paused` | 已暂停 | 用户在 Job 级别暂停，排队的 Execution 不执行 |
| `cancelled` | 已取消 | 用户在 Execution 或 Job 级别取消 |
| `stale` | 已过期 | Execution 超过 timeout 未完成（超时后端标记） |

### 6.2 状态转换

```
                    ┌─────────┐
                    │ pending │ ←── Job 被调度触发
                    └────┬────┘
                         │ 调度器取到
                         ▼
                    ┌─────────┐         ┌──────────────┐
         ┌──────────│ running │────────▶│ retrying     │
         │ 暂停     └────┬────┘ 可重试   │ (等待退避后)  │
         ▼               │   异常      └──────┬───────┘
    ┌─────────┐          │                    │ 退避结束
    │ paused  │          │                    ▼
    └────┬────┘          │               ┌─────────┐
         │ 恢复          │               │ running │（重新执行）
         ▼               │               └─────────┘
    ┌─────────┐          │
    │ running │（继续执行）│
    └─────────┘          │
                         │ 正常返回
                         ▼
              ┌──────────────────┐
              │ success          │
              │ / partial_success│
              └──────────────────┘

    ┌─────────┐    用户取消
    │ running │──────────────────▶  ┌───────────┐
    │ pending │                     │ cancelled │
    └─────────┘                     └───────────┘

    ┌─────────┐    不可重试异常     ┌─────────┐
    │ running │───────────────────▶│ failed  │
    │ retrying│（重试耗尽）         └─────────┘
    └─────────┘

    ┌─────────┐    超时未完成       ┌─────────┐
    │ running │───────────────────▶│ stale   │
    └─────────┘                     └─────────┘
```

### 6.3 Job 级别状态

Job 本身有独立的状态控制，影响 Execution 的创建和执行：

| Job 状态 | 含义 |
|---|---|
| `enabled` | 正常调度 |
| `paused` | 暂停调度（已创建的 Execution 不受影响，但不创建新的） |
| `disabled` | 禁用（不接受任何调度和手动触发） |

切换 `paused` → `enabled` 不会自动补跑暂停期间遗漏的调度。

---

## 7. API / CLI / Dashboard 边界

### 7.1 Python API（主要操作界面）

```python
# 任务注册
task_center.register_task(task_id, callable, ...)

# Job 管理
task_center.create_job(task_id, schedule, params, ...)
task_center.pause_job(job_id)
task_center.resume_job(job_id)
task_center.enable_job(job_id)
task_center.disable_job(job_id)

# 手动触发
task_center.trigger_job(job_id, params_override=None)

# 查询
task_center.list_tasks(module=None, tags=None)
task_center.list_jobs(task_id=None, status=None)
task_center.get_execution(execution_id)
task_center.list_executions(job_id=None, status=None, limit=20)
task_center.list_errors(execution_id=None, limit=20)

# 执行控制
task_center.cancel_execution(execution_id)
task_center.retry_execution(execution_id)  # 重跑失败的 Execution

# 进度
task_center.get_progress(execution_id)

# 生命周期
task_center.start_scheduler()   # 启动调度器（阻塞或后台线程）
task_center.stop_scheduler()
```

### 7.2 CLI 接口（辅助入口）

CLI 通过 `python -m task_center.cli` 或项目级命令入口暴露：

```
yq task list                  # 列出所有注册的任务定义
yq task info <task_id>        # 查看任务详情
yq job list [--task <id>]     # 列出所有 Job 及其状态
yq job pause <job_id>         # 暂停 Job
yq job resume <job_id>        # 恢复 Job
yq job run <job_id> [--params] # 手动触发
yq exec list [--job <id>] [--status <s>]  # 列出执行记录
yq exec show <exec_id>        # 查看执行详情（含 Steps）
yq exec cancel <exec_id>      # 取消执行
yq exec retry <exec_id>       # 重试失败执行
yq progress <exec_id>         # 查看执行进度
yq errors <exec_id>           # 查看错误记录
yq scheduler start            # 启动调度器
yq scheduler stop             # 停止调度器
yq scheduler status           # 查看调度器状态
```

### 7.3 Dashboard 边界

MVP 不产出 Web Dashboard。后续 Phase 3 可考虑在现有项目终端或简单 HTML 中展示任务看板，但不是在本次 RFC 范围内。

---

## 8. 与现有基建的明确边界

### 8.1 与 Hermes Kanban / cron 的边界（关键）

这是最容易被混淆的边界，需要写得非常明确：

| 维度 | Hermes Kanban | Hermes cron | task_center |
|---|---|---|---|
| **定位** | AI Agent 工作流编排 | AI Agent 定时触发 | **业务任务执行管理** |
| **任务粒度** | 流水线阶段（RFC/SPEC/Design/Implement 等），跨多个 LLM 推理步 | 单次 Agent 会话（如"生成本日市场报告"） | 业务函数调用（如"刷新A股日线"） |
| **执行者** | AI Agent（多个 LLM 推理步 + 工具调用） | AI Agent | **Python 函数/脚本（无 LLM）** |
| **状态追踪** | Kanban DB 的 task status | cron 系统状态 | task_center Execution 状态 |
| **重试/进度** | 无重试（worker crash 由 dispatcher 重调度） | 无 | 内置重试策略 + Step 级进度 |
| **触发方式** | orchestrator 主动创建 | 定时 + `attach_to_session` | 定时 / interval / 手动触发 / 单次延迟 |
| **典型用途** | "按 AI Coding Pipeline 实现 XXX" | "每天 8:00 生成全球市场报告" | "每天 15:30 刷新 A 股日线行情数据" |

**关系**：
- Hermes cron **可以**调用 task_center 的 CLI（如 `hermes cron → yq scheduler start`），但 Hermes cron 本身不管理业务任务状态
- task_center **不依赖** Hermes Kanban 或 cron 来运行，可独立使用
- 两者是**不同层次**的编排工具，不应混用或互相替代

### 8.2 与 unified_data 的边界

| 维度 | task_center | unified_data |
|---|---|---|
| 职责 | 任务调度、状态管理 | 数据访问与路由 |
| 交互方式 | task_center **调用** unified_data 的刷新函数 | unified_data 暴露 `refresh(domain, ...)` 供 task_center 调用 |
| 依赖方向 | 无依赖（task_center 不 import unified_data）；task_center 通过 callable 路径间接调用 | unified_data 注册刷新 Task 到 task_center（由业务模块在启动时注册） |

**典型协作流**：

```
unified_data 模块启动
  → 调用 task_center.register_task("unified_data.daily_kline_cn", callable=refresh_daily_kline_cn)
  → 调用 task_center.create_job("unified_data.daily_kline_cn", schedule="0 15 * * 1-5", params={...})
  → 此后 task_center 在每个交易日 15:00 自动调用 refresh_daily_kline_cn()
  → unified_data 自身不写任何调度逻辑
```

### 8.3 与 stock 框架的边界

| 维度 | task_center | stock 框架 |
|---|---|---|
| 职责 | 任务调度 | 量化分析（因子、评分、报告） |
| 交互方式 | task_center 调用 stock 的分析函数 | stock 注册批量分析任务到 task_center |

**典型协作流**：

```
stock 模块启动
  → task_center.register_task("stock.batch_score", callable=run_batch_scoring)
  → task_center.create_job("stock.batch_score", schedule=3600, params={...})
  → 每 3600 秒 task_center 调用 run_batch_scoring() 做批量评分
  → stock 不自行管理定时循环
```

### 8.4 与 TA-CN 现有调度/队列的关系

| 阶段 | 动作 | 风险 |
|---|---|---|
| 阶段 0（本 RFC/SPEC） | 定义 task_center 接口，不动 TA-CN 代码 | 无 |
| 阶段 1（MVP 实现） | 实现 task_center 核心，用于 unified_data / stock 等新模块 | 低 |
| 阶段 2（后续） | 为 TA-CN 的 data_sync 类任务编写 task_center adapter，与现有 Redis 队列并存 | 中 |
| 阶段 3（远期） | TA-CN 内部替换为 task_center，移除 Redis 队列依赖 | 高（需逐服务验证） |

**迁移原则**：先并存后替换，每一步可回滚。

---

## 9. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| 过度抽象导致包太复杂 | 中 | 高 | MVP 只覆盖基础功能（注册/调度/状态/简单进度），不做复杂特性 | 退回到直接调用函数 |
| MongoDB 连接/索引/原子 claim 配置错误 | 中 | 中 | 初始化时检查 MongoDB 连接与索引；claim 使用原子 find_one_and_update | 临时切换到 SQLite 降级后端或暂停 task_center |
| 调度器进程崩溃后状态丢失 | 中 | 高 | 所有状态持久化在 MongoDB，重启后可恢复；超时未完成的 Execution 自动标记为 stale | systemd/cron 守护调度器进程 |
| 与 Hermes cron 定位混淆 | 中 | 中 | 本 RFC §8.1 明确边界 | 文档交付时附带"如何选择"决策树 |
| TA-CN 迁移阻力 | 中 | 中 | 分阶段迁移，长期并存 | 长期保持 adapter 模式 |
| 业务 callable 执行超时 | 中 | 中 | Job 级别 timeout_seconds + execution 级别 stale 标记 | 手动重试超时任务 |
| 任务注册泛滥（各模块随意注册） | 低 | 中 | 注册时校验 task_id 命名规范，提供 `list_tasks` 总览 | 任务注册表定期审查 |

---

## 10. 备选方案（Alternatives Considered）

### 10.1 方案 B：直接扩展 TA-CN 现有调度器

- **优点**：已有 APScheduler + Redis Queue + MongoDB 进度追踪，功能覆盖较全
- **缺点**：强绑定 Redis + MongoDB，无法被其他模块独立复用；接口为 Web API 设计，不适用纯 Python CLI；与 TA-CN 业务逻辑耦合
- **不选原因**：TA-CN 是子项目（submodule），不应让全局基础层依赖子项目；且 Redis 依赖在 Pascal 的轻量部署环境下不必要

### 10.2 方案 C：统一使用 Hermes cron 替代

- **优点**：Hermes cron 已提供定时触发能力，无额外代码
- **缺点**：Hermes cron 每次触发是一次全新 Agent 会话（LLM 推理开销大），不适合高频短任务（如 3600 秒间隔的股票评分）；无内置进度追踪、重试策略、任务看板；Hermes 是外部工具，任务状态不留在 YQuant 项目内
- **不选原因**：非业务场景（AI Agent 工作流）与业务场景（数据刷新/因子计算）层次不同，强绑会导致 LLM 成本爆炸和状态丢失

### 10.3 方案 D：使用 Celery / Dramatiq 等分布式任务队列

- **优点**：工业级任务队列，成熟稳定
- **缺点**：引入 Redis / RabbitMQ 作为 Broker；配置复杂，对 Pascal 的个人部署过重；分布式 worker 在单机场景下没有意义
- **不选原因**：MVP 阶段不需要分布式，纯 Python + MongoDB 已满足 YQuant 的统一持久化要求，SQLite 仅保留为本地降级

### 10.4 方案 E：使用 Prefect / Dagster / Airflow

- **优点**：强大的 DAG 编排、可视化 Dashboard、丰富的集成
- **缺点**：重型框架，Web UI + 数据库 + scheduler + executor 多组件部署；学习曲线陡峭；对个人量化系统过量
- **不选原因**：过度工程化，不符合 MVP 轻量原则

---

## 11. 验收标准

### 11.1 本 RFC/SPEC 阶段验收

- [ ] RFC 文件存在于 `docs/rfc/10_infra/RFC-10-009-*.md`，明确业务价值、架构边界、风险
- [ ] SPEC 文件存在于 `docs/spec/10_infra/SPEC-10-009-*.md`，明确可执行、可测试的工程契约
- [ ] 明确 task_center 与 Hermes Kanban/cron、unified_data、stock 框架、TA-CN 的边界
- [ ] 明确四层实体模型（Task/Job/Execution/Step）与状态机
- [ ] 明确后续 Design 分阶段建议
- [ ] 中文输出，专业简洁

### 11.2 后续实现阶段验收（供 Design 参考）

- [ ] task_center 可被 `from skills.infra.task_center import ...` 导入
- [ ] 注册一个 Task、创建一个 Job、手动触发一次执行、查询执行状态和结果
- [ ] 定时 Job 在指定时间自动触发
- [ ] 执行失败后按重试策略自动重试
- [ ] Step 级别进度在 CLI 和 Python API 中可见
- [ ] 执行历史可查询、分页、按状态过滤
- [ ] Job 暂停/恢复后调度行为正确
- [ ] 执行取消后状态正确标记
- [ ] MongoDB 持久化在所有查询中一致，且 `10_infra_tc_*` 集合初始化和索引校验通过
- [ ] CLI `yq task list` / `yq job list` / `yq exec show` 可正常输出

---

## 12. 落地计划

### 12.1 阶段划分

| 阶段 | 内容 | 建议文件 |
|---|---|---|
| 阶段 0：RFC/SPEC | 本 RFC + SPEC | `docs/rfc/10_infra/RFC-10-009-*.md` + `docs/spec/10_infra/SPEC-10-009-*.md` |
| 阶段 1：Design | 四层实体类设计、调度器/状态机/存储层/CLI 详细设计 | `docs/design/10_infra/DESIGN-10-009-*.md`（可拆分 A/B/C 子阶段） |
| 阶段 2：MVP 实现 | Task/Job/Execution/Step 实体 + 调度器 + CLI + MongoDB 存储（`10_infra_tc_*`） | `skills/infra/task_center/` 目录 |
| 阶段 3：业务接入 | unified_data 注册刷新任务、stock 注册评分任务、report/risk 接入 | 各业务模块 + task_center adapter |
| 阶段 4：TA-CN 收敛 | TA-CN data_sync 类任务迁移到 task_center | adapter + 迁移 script |
| 阶段 5：增强 | Web Dashboard（可选）、分布式 worker（可选）、SQLite 离线降级完善 | 按需 |

### 12.2 MVP 最小范围

- Task 注册 + Job 创建 + 手动触发
- 定时调度（cron + interval）
- 状态机（pending/running/success/failed/cancelled）
- 简单进度（百分比，非 Step 级）
- 重试（max_retries + fixed backoff）
- 执行历史（查询/分页）
- 暂停/恢复/取消
- MongoDB 持久化（`10_infra_tc_*` 集合）
- Python API + CLI
- **不包含**：Step 级别进度追踪、Web Dashboard、TA-CN 迁移、SQLite 降级完善

---

## 13. 后续 Design 拆分建议

| Design 子阶段 | 建议内容 |
|---|---|
| Design-A | 四层实体模型（Task/Job/Execution/Step）的 dataclass 定义 + 状态机实现 + MongoDB 集合/索引结构 |
| Design-B | 调度器设计：cron/interval/once 解析 + 轮询循环 + 并发控制 |
| Design-C | CLI 接口完整命令定义 + Python API 函数签名 |
| Design-D | 业务接入示例：unified_data 刷新任务的注册与配置模板 |

可合并为一份 Design 文档，也可按子阶段拆分。

---

## 14. 开放问题（Open Questions）

1. **Step 级别进度是否入 MVP？**：Step 对长任务（如批量评分 5000 只股票）很有用，但实现复杂度高。建议 MVP 只做百分比，Phase 3 加 Step。
2. **调度器守护方式？**：调度器进程需要被 systemd 或 Hermes cron 守护。是否在 Design 阶段明确推荐的守护方式？
3. **执行并发策略？**：多个 Job 同时到达时，是否串行排队（FIFO）还是允许有限并发（如 N=3）？
4. **通知集成？**：任务完成/失败后是否应该支持回调通知（如 Telegram message）？如果是，是否复用现有通知通道？
5. **任务注册的发现机制？**：Task 注册是手动在代码中显式调用 `register_task()`，还是支持自动发现（扫描 `tasks.py` 等约定文件）？

这些问题不影响 RFC/SPEC 的批准，可在 Design 阶段决策。

---

## 15. 参考资料（References）

- RFC-10-003：Infra 架构（`docs/rfc/10_infra/RFC-10-003-infra-architecture.md`）
- RFC-10-004：AI Coding Pipeline skill sync（`docs/rfc/10_infra/RFC-10-004-yquant-ai-coding-pipeline-skill-sync.md`）
- RFC-03-007：Unified Data Layer（`docs/rfc/03_data/RFC-03-007-unified-data-layer.md`）
- SPEC-03-007：Unified Data Layer 可执行契约（`docs/spec/03_data/SPEC-03-007-unified-data-layer.md`）
- TA-CN 调度器：`skills/apps/TradingAgents-CN/app/services/scheduler_service.py`
- TA-CN 队列：`skills/apps/TradingAgents-CN/app/services/queue_service.py`
- TA-CN 进度：`skills/apps/TradingAgents-CN/app/services/progress/tracker.py`
- Pipeline skill：`skills/infra/ai-coding-pipeline/SKILL.md`
- Hermes Kanban/cron 参考（不作为技术耦合，仅作边界对比）
