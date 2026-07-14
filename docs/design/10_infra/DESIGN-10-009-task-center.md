# DESIGN-10-009: YQuant Infra Task Center — 完整详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-12 |
| 最后更新 | 2026-07-14 |
| 来源 RFC | RFC-10-009 |
| 来源 SPEC | SPEC-10-009 |
| 关联 RFC | RFC-03-007（Unified Data Layer）、RFC-08-001（Stock Framework） |
| 关联 SPEC | SPEC-03-007（Unified Data Layer）、SPEC-08-001（Stock Framework） |
| 关联 Design | DESIGN-03-007（Unified Data Layer） |
| 目标模块 | task_center（`skills/infra/task_center/`） |

### 版本历史（Changelog）

| 版本 | 日期 | 变更 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-07-12 | 初始创建，完整详细设计 | YQuant-Codex-Principal |
| V1.1 | 2026-07-14 | 文档同步修订：Pascal 确认 Unified Data × Task Center 共用同一物理 MongoDB `tradingagents`，"物理隔离"措辞改为"命名空间隔离"（与 RFC-10-009 V0.2 / DESIGN-03-007 V3.3 一致） | YQuant-Principal |

---

## 1. 设计目标与非目标

### 1.1 设计目标

1. **完整设计**：覆盖 task_center 的整体架构、实体模型、状态机、存储、调度、执行、进度、重试、CLI/API、Dashboard 边界、unified_data 接口、stock framework 接口、TA-CN/DSA 迁移边界。
2. **分阶段实现**：设计一次到位，实现拆为 Phase 0-7，每 Phase 有独立范围、产物、验收标准和风险。
3. **定位 infra**：task_center 是 YQuant 项目内业务任务中心，不等同于 Hermes Kanban / cron。
4. **不绑定 Redis/Celery/Web**：MVP 以纯 Python + MongoDB 为默认持久化（与 YQuant 现有 `tradingagents` 数据库体系一致），SQLite 仅作为本地单元测试/离线降级选项；不在首期引入 Redis/Celery/Web。
5. **可观测优先**：任务状态、进度、错误、重试、执行历史必须可追踪。
6. **幂等与可恢复**：数据刷新类任务必须支持幂等 key、断点/重试语义、错误保留。
7. **不做生产调度变更**：本 Design 不创建 cron/systemd/gateway/webhook，不执行真实更新任务。
8. **与 unified_data 清晰分工**：task_center 调度任务，unified_data 提供数据刷新 operation / provider / adapter。
9. **与 stock framework 清晰分工**：stock framework 注册画像刷新、模型评分、报告生成任务；task_center 不理解投资逻辑。

### 1.2 非目标（本 Design 不做的事）

- 不实现代码（不创建 `skills/infra/task_center/` 下的 `.py` 文件）。
- 不修改 TA-CN / DSA / unified_data / stock framework / Hermes 现有代码或配置。
- 不创建任何真实任务、cron、systemd、gateway、webhook。
- 不修改数据库 schema，不执行迁移。
- 不做生产级调度部署。

---

## 2. 总体架构

### 2.1 架构分层图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Consumers 消费层                                   │
│  unified_data  │  stock  │  report  │  risk  │  portfolio  │  TA-CN/DSA   │
│  "刷新A股日线"  │ "批量评分"│ "生成报告"│ "风险扫描"│ "持仓检查"    │ "迁移适配"   │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ register_task / trigger_job / query_status
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    Task Center  (skills/infra/task_center/)                │
│                                                                            │
│  ┌───────────────────┐  ┌──────────────────┐  ┌─────────────────────────┐│
│  │ Python API        │  │ CLI (yq task/job │  │ Dashboard (Phase 6+)    ││
│  │ task_center.*     │  │ /exec/scheduler) │  │ Web/HTML 看板           ││
│  └────────┬──────────┘  └────────┬─────────┘  └────────────┬────────────┘│
│           │                      │                          │             │
│  ┌────────┴──────────────────────┴──────────────────────────┴────────────┐│
│  │                        Core Layer 核心层                               ││
│  │                                                                        ││
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────────────┐ ││
│  │  │ TaskRegistry    │  │ StateMachine    │  │ IdempotencyManager     │ ││
│  │  │ (task_id→def)   │  │ (9状态+12转换)   │  │ (幂等key防重复)        │ ││
│  │  └────────┬────────┘  └────────┬────────┘  └────────────┬───────────┘ ││
│  │           │                    │                          │             ││
│  │  ┌────────┴────────────────────┴──────────────────────────┴───────────┐││
│  │  │                      Scheduler 调度层                               │││
│  │  │  ScheduleParser │ SchedulerLoop │ TriggerManager │ ConcurrencyCtrl │││
│  │  │  (cron/interval/ │ (poll+执行)   │ (手动/事件/依赖)│ (max_concurrent)│││
│  │  │   once解析)      │               │                │                │││
│  │  └────────┬────────────────────────────────────────────────────────────┘││
│  │           │                                                              ││
│  │  ┌────────┴────────────────────────────────────────────────────────────┐││
│  │  │                     Executor 执行层                                  │││
│  │  │  InProcessExecutor │ SubprocessExecutor │ AsyncExecutor             │││
│  │  │  (默认，同一进程)   │ (独立进程，Phase 2+) │ (asyncio，Phase 3+)     │││
│  │  └────────┬────────────────────────────────────────────────────────────┘││
│  │           │                                                              ││
│  │  ┌────────┴────────────────────────────────────────────────────────────┐││
│  │  │                     Runtime Services 运行时服务                      │││
│  │  │  ProgressTracker │ RetryManager │ ErrorStore │ HeartbeatMonitor     │││
│  │  │  (Step权重进度)   │ (backoff策略) │ (堆栈保留)  │ (stale检测)         │││
│  │  └────────┬────────────────────────────────────────────────────────────┘││
│  └───────────┼────────────────────────────────────────────────────────────┘│
│              │                                                              │
│  ┌───────────┴────────────────────────────────────────────────────────────┐│
│  │                       Persistence 持久化层                              ││
│  │  StorageBackend (ABC)                                                  ││
│  │  ├── MongoDBBackend (MVP 默认)                                       ││
│  │  └── SQLiteBackend (本地测试/离线降级，可选)                          ││
│  │                                                                        ││
│  │  Tasks / Jobs / Executions / Steps / RetryPolicies / Errors / Events   ││
│  │  / Artifacts / Dependencies / Schedules / ProgressSnapshots            ││
│  └────────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     External Integration 外部集成                          │
│  unified_data tasks │ stock framework tasks │ Hermes cron (optional tick)  │
│  TA-CN adapter      │ DSA adapter           │ Telegram/企业微信 (Phase 6+) │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 模块目录结构

```
skills/infra/task_center/
├── __init__.py
├── SKILL.md                          # 模块说明
│
├── core/
│   ├── __init__.py
│   ├── entities.py                   # 11 类实体 dataclass 定义
│   ├── state_machine.py              # StateMachine（9状态+12转换）
│   ├── registry.py                   # TaskRegistry（注册/注销/查询）
│   ├── idempotency.py                # IdempotencyManager（幂等key）
│   └── exceptions.py                 # 18 种异常定义
│
├── storage/
│   ├── __init__.py
│   ├── backend.py                    # StorageBackend 抽象基类
│   ├── mongo_backend.py              # MongoDBBackend（MVP 默认）
│   ├── mongo_schema.py               # MongoDB 集合索引定义
│   └── sqlite_backend.py             # SQLiteBackend（本地测试/离线降级，可选）
│
├── scheduler/
│   ├── __init__.py
│   ├── schedule_parser.py            # Cron/Interval/Once 解析器
│   ├── scheduler_loop.py             # 主调度循环
│   ├── trigger_manager.py            # 手动/事件/依赖触发
│   └── concurrency_control.py        # 并发控制（max_concurrent）
│
├── executor/
│   ├── __init__.py
│   ├── base.py                       # TaskExecutor 抽象基类
│   ├── in_process.py                 # InProcessExecutor
│   ├── subprocess.py                 # SubprocessExecutor（Phase 2+）
│   └── async_executor.py             # AsyncExecutor（Phase 3+）
│
├── runtime/
│   ├── __init__.py
│   ├── progress.py                   # ProgressTracker（Step权重进度）
│   ├── retry.py                      # RetryManager（backoff策略）
│   ├── error_store.py                # ErrorStore（堆栈保留）
│   └── heartbeat.py                  # HeartbeatMonitor（stale检测）
│
├── api/
│   ├── __init__.py
│   ├── tasks.py                      # Task API（register/unregister/list/get）
│   ├── jobs.py                       # Job API（create/pause/resume/disable）
│   ├── executions.py                 # Execution API（trigger/cancel/retry/list）
│   ├── progress_api.py               # Progress API（get/update/create_steps）
│   └── scheduler_api.py             # Scheduler API（start/stop/status）
│
├── cli.py                            # CLI 入口（yq task/job/exec/scheduler）
│
├── integrations/
│   ├── __init__.py
│   ├── unified_data.py               # unified_data 任务注册适配器
│   ├── stock_framework.py            # stock framework 任务注册适配器
│   ├── ta_cn_adapter.py              # TA-CN 迁移适配器（Phase 7）
│   └── dsa_adapter.py                # DSA 迁移适配器（Phase 7）
│
└── config.py                         # 模块配置加载

tests/infra/task_center/
├── __init__.py
├── conftest.py                       # pytest fixtures
├── test_entities.py
├── test_state_machine.py
├── test_registry.py
├── test_idempotency.py
├── test_schedule_parser.py
├── test_mongo_backend.py
├── test_scheduler_loop.py
├── test_in_process_executor.py
├── test_progress_tracker.py
├── test_retry_manager.py
├── test_error_store.py
├── test_heartbeat.py
├── integration/
│   ├── test_full_register_trigger_flow.py
│   ├── test_retry_and_failure.py
│   ├── test_concurrency.py
│   └── test_idempotency_e2e.py
└── fixtures/
    ├── mock_callable.py
    └── mock_storage.py
```

### 2.3 组件职责矩阵

| 组件 | 职责 | 输入 | 输出 |
|---|---|---|---|
| **TaskRegistry** | 管理 TaskDefinition 的注册/注销/查询/生命周期 | task_id, callable, metadata | TaskDefinition 对象 |
| **StateMachine** | 验证和执行状态转换 | current_status, target_status, context | 新状态 或 抛异常 |
| **IdempotencyManager** | 基于幂等 key 防重复执行 | idempotency_key | True（可执行）/ False（已执行） |
| **ScheduleParser** | 解析 cron/interval/once/manual 调度规则 | schedule 字符串 | Schedule 对象 + next_run_at |
| **SchedulerLoop** | 主调度循环：poll pending → execute → update | 无（后台线程） | Execution 创建与状态更新 |
| **TriggerManager** | 处理手动触发、事件触发、依赖触发 | trigger_type, params | Execution 对象 |
| **ConcurrencyControl** | 限制同 Job 同时运行数 | job_id, max_concurrent | True（允许）/ False（排队） |
| **TaskExecutor（×3）** | 执行 callable，管理 timeout/cancel/heartbeat | Execution + callable | result 或 exception |
| **ProgressTracker** | Step 权重驱动进度计算 | execution_id, steps | progress_percentage |
| **RetryManager** | 退避策略计算、重试判断 | RetryPolicy + error | next_retry_at 或 failed |
| **ErrorStore** | 错误记录保留（含堆栈） | Execution + exception | ErrorRecord |
| **HeartbeatMonitor** | 超时检测、stale 标记 | running executions | stale 状态更新 |
| **StorageBackend** | 所有实体的 CRUD | entity objects | 持久化数据 |
| **CLI** | `yq task/job/exec/scheduler` 命令组 | 命令行参数 | 终端输出（表格/YAML） |
| **Python API** | `task_center.*` 公开函数 | Python 调用 | entity 对象或 None |

---

## 3. 与 Hermes Kanban / cron 的边界

### 3.1 边界对比表

| 维度 | Hermes Kanban | Hermes cron | task_center |
|---|---|---|---|
| **定位** | AI Agent 工作流编排 | AI Agent 定时触发 | **YQuant 业务任务执行管理** |
| **任务粒度** | 流水线阶段（RFC/SPEC/Design 等），跨多个 LLM 推理步 | 单次 Agent 会话（如"生成本日市场报告"） | **业务函数调用**（如"刷新A股日线"） |
| **执行者** | AI Agent（LLM 推理 + 工具调用） | AI Agent | **Python 函数/脚本（无 LLM）** |
| **状态追踪** | Kanban DB 的 task status | cron 系统状态 | task_center Execution 状态机 |
| **重试/进度** | 无（worker crash 由 dispatcher 重调度） | 无 | 内置 RetryManager + ProgressTracker |
| **触发方式** | orchestrator 创建 | 定时 + attach_to_session | cron/interval/once/manual/event/dependency/backfill/dry-run |
| **存储** | `~/.hermes/kanban.db` SQLite | Hermes 内部 cron 系统 | 独立 MongoDB（SQLite 仅本地测试/降级） |
| **典型用途** | "按 AI Coding Pipeline 实现 XXX" | "每天 8:00 生成全球市场报告" | "每天 15:30 刷新 A 股日线行情数据" |

### 3.2 关系

- Hermes cron **可以**作为 task_center 的守护触发器（如 Hermes cron → `yq scheduler start`），但不管理业务任务状态。
- task_center **不依赖** Hermes Kanban 或 cron 来运行，可独立使用。
- 两者是**不同层次**的编排工具：Agent 层 vs 业务层，不应混用或互相替代。
- 后续可考虑 Hermes cron 每 60s 触发一次 `yq scheduler tick` 使 task_center 调度循环得到守护。

---

## 4. 核心实体模型

所有实体使用 `@dataclass` 定义，序列化/反序列化由 StorageBackend 负责。代码层时间字段可使用 ISO 8601 字符串或 `datetime`，MongoDB 持久化层统一转换为 BSON Date/ISODate。

### 4.1 TaskDefinition（任务定义）

Task 的**模板**，描述"做什么"。

| 字段 | 类型 | 必填 | 唯一键 | 说明 | MVP |
|---|---|---|---|---|---|
| `task_id` | str | ✅ | PK | 唯一标识，格式 `[a-z0-9_.-]`，如 `unified_data.daily_kline_cn` | ✅ |
| `name` | str | ✅ | — | 人类可读名称 | ✅ |
| `description` | str | — | — | 任务说明 | ✅ |
| `module` | str | — | FK | 所属模块（`unified_data` / `stock` / `report` / `risk` / `portfolio`） | ✅ |
| `callable_path` | str | ✅ | — | Python callable 路径，如 `unified_data.tasks:refresh_daily_kline_cn` | ✅ |
| `default_params` | dict | — | — | 默认参数 | ✅ |
| `retry_policy_id` | str | — | FK→RetryPolicy | 关联重试策略，默认 `"default"` | ✅ |
| `tags` | list[str] | — | — | 标签列表 | ✅ |
| `created_at` | str | ✅ | — | ISO 8601 | ✅ |
| `updated_at` | str | ✅ | — | ISO 8601 | ✅ |

**生命周期**：注册 → 使用中 → 注销（有活跃 Execution 时拒绝注销）。

```python
@dataclass
class TaskDefinition:
    task_id: str
    name: str
    description: str = ""
    module: str = ""
    callable_path: str = ""
    default_params: dict = field(default_factory=dict)
    retry_policy_id: str = "default"
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
```

### 4.2 JobInstance（任务实例）

Task 的**具体实例**，描述"何时、以什么参数执行"。

| 字段 | 类型 | 必填 | 唯一键 | 说明 | MVP |
|---|---|---|---|---|---|
| `job_id` | str | ✅ | PK | UUID | ✅ |
| `task_id` | str | ✅ | FK→TaskDefinition | 关联 Task | ✅ |
| `schedule` | str | ✅ | — | cron表达式 / interval秒数 / `"once:ISO"` / `"manual"` | ✅ |
| `schedule_type` | str | — | — | 解析得出：`"cron"` / `"interval"` / `"once"` / `"manual"` | ✅ |
| `params` | dict | — | — | 覆盖 Task.default_params 的具体参数 | ✅ |
| `enabled` | bool | — | — | 等价于 status != "disabled" | ✅ |
| `status` | str | — | — | `"enabled"` / `"paused"` / `"disabled"` | ✅ |
| `max_concurrent` | int | — | — | 允许同时运行的 Execution 数（默认 1） | ✅ |
| `timeout_seconds` | int | — | — | 单次执行超时（0=无超时） | ✅ |
| `retry_policy_id` | str\|None | — | FK→RetryPolicy | 覆盖 Task 级别 retry_policy | ✅ |
| `priority` | int | — | — | 排队优先级（越小越优先） | ✅ |
| `idempotency_key_template` | str | — | — | 幂等 key 模板，如 `"{task_id}:{trade_date}"` | — |
| `created_at` | str | ✅ | — | ISO 8601 | ✅ |
| `updated_at` | str | ✅ | — | ISO 8601 | ✅ |

```python
@dataclass
class JobInstance:
    job_id: str
    task_id: str
    schedule: str
    schedule_type: str = ""
    params: dict = field(default_factory=dict)
    enabled: bool = True
    status: str = "enabled"   # enabled / paused / disabled
    max_concurrent: int = 1
    timeout_seconds: int = 3600
    retry_policy_id: str | None = None
    priority: int = 0
    idempotency_key_template: str = ""
    created_at: str = ""
    updated_at: str = ""
```

### 4.3 TaskExecution（执行记录）

Job 每次运行的**具体记录**，描述"结果如何"。由状态机管理生命周期。

| 字段 | 类型 | 必填 | 唯一键 | 说明 | MVP |
|---|---|---|---|---|---|
| `execution_id` | str | ✅ | PK | UUID | ✅ |
| `job_id` | str | ✅ | FK→JobInstance | 关联 Job | ✅ |
| `status` | str | — | — | 状态机管理（9 状态之一） | ✅ |
| `trigger` | str | — | — | `"scheduled"` / `"manual"` / `"event"` / `"dependency"` / `"backfill"` | ✅ |
| `params` | dict | — | — | 本次执行参数快照 | ✅ |
| `idempotency_key` | str | — | Index | 幂等 key，用于防重复 | — |
| `started_at` | str\|None | — | — | ISO 8601 | ✅ |
| `finished_at` | str\|None | — | — | ISO 8601 | ✅ |
| `elapsed_seconds` | float | — | — | 总耗时 | ✅ |
| `progress_percentage` | float | — | — | 0-100 | ✅ |
| `current_step_index` | int | — | — | 当前 Step 索引 | — |
| `result` | str | — | — | 执行结果摘要 | ✅ |
| `retry_count` | int | — | — | 重试次数（初始 0） | ✅ |
| `error_summary` | str | — | — | 最后一次失败摘要 | ✅ |
| `warnings` | list[str] | — | — | 警告列表 | ✅ |
| `created_at` | str | ✅ | — | ISO 8601 | ✅ |
| `updated_at` | str | ✅ | — | ISO 8601 | ✅ |

```python
@dataclass
class TaskExecution:
    execution_id: str
    job_id: str
    status: str = "pending"
    trigger: str = "scheduled"
    params: dict = field(default_factory=dict)
    idempotency_key: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: float = 0.0
    progress_percentage: float = 0.0
    current_step_index: int = 0
    result: str = ""
    retry_count: int = 0
    error_summary: str = ""
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
```

### 4.4 TaskStep（执行步骤）

Execution 内的**子步骤**，描述"做到哪了"。MVP 不含 Step 级进度，Phase 2+ 引入。

| 字段 | 类型 | 必填 | 唯一键 | 说明 | MVP |
|---|---|---|---|---|---|
| `step_id` | str | ✅ | PK | UUID | — |
| `execution_id` | str | ✅ | FK→TaskExecution | 所属 Execution | — |
| `name` | str | ✅ | — | 步骤名称 | — |
| `description` | str | — | — | 步骤说明 | — |
| `index` | int | — | — | 步骤序号（从 0 开始） | — |
| `weight` | float | — | — | 权重（所有 Step 权重和为 1.0） | — |
| `status` | str | — | — | `pending`/`running`/`completed`/`failed`/`skipped` | — |
| `started_at` | str\|None | — | — | ISO 8601 | — |
| `finished_at` | str\|None | — | — | ISO 8601 | — |
| `error_message` | str | — | — | 失败错误信息 | — |
| `data` | dict | — | — | 可选结构化数据（处理行数、耗时等） | — |

```python
@dataclass
class TaskStep:
    step_id: str
    execution_id: str
    name: str
    description: str = ""
    index: int = 0
    weight: float = 0.0
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str = ""
    data: dict = field(default_factory=dict)
```

### 4.5 RetryPolicy（重试策略）

| 字段 | 类型 | 必填 | 唯一键 | 说明 | MVP |
|---|---|---|---|---|---|
| `policy_id` | str | ✅ | PK | 如 `"default"`、`"aggressive"`、`"no_retry"` | ✅ |
| `max_retries` | int | — | — | 最大重试次数 | ✅ |
| `backoff` | str | — | — | `"fixed"` / `"exponential"` / `"linear"` | ✅ |
| `backoff_base_seconds` | int | — | — | 基础退避秒数 | ✅ |
| `backoff_max_seconds` | int | — | — | 最大退避秒数 | ✅ |
| `retry_on_exception_types` | list[str] | — | — | 需重试的异常类型（空=全部重试） | ✅ |
| `no_retry_on_exception_types` | list[str] | — | — | 不重试的异常类型 | ✅ |

```python
@dataclass
class RetryPolicy:
    policy_id: str
    max_retries: int = 3
    backoff: str = "fixed"       # fixed / exponential / linear
    backoff_base_seconds: int = 30
    backoff_max_seconds: int = 300
    retry_on_exception_types: list[str] = field(default_factory=list)
    no_retry_on_exception_types: list[str] = field(default_factory=list)
```

### 4.6 ErrorRecord（错误记录）

| 字段 | 类型 | 必填 | 唯一键 | 说明 | MVP |
|---|---|---|---|---|---|
| `error_id` | str | ✅ | PK | UUID | ✅ |
| `execution_id` | str | ✅ | FK→TaskExecution | 所属 Execution | ✅ |
| `step_id` | str\|None | — | FK→TaskStep | 发生在哪个 Step | — |
| `attempt_number` | int | — | — | 第几次尝试（含重试） | ✅ |
| `error_type` | str | — | — | 异常类型名 | ✅ |
| `error_message` | str | — | — | 异常消息 | ✅ |
| `traceback` | str | — | — | 完整堆栈（截断到 10000 字符） | ✅ |
| `created_at` | str | ✅ | — | ISO 8601 | ✅ |

```python
@dataclass
class ErrorRecord:
    error_id: str
    execution_id: str
    step_id: str | None = None
    attempt_number: int = 1
    error_type: str = ""
    error_message: str = ""
    traceback: str = ""
    created_at: str = ""
```

### 4.7 ProgressSnapshot（进度快照）

用于 CLI/API 查询进度时返回的结构化对象（非持久化实体，由 ProgressTracker 实时计算）。

| 字段 | 类型 | 说明 | MVP |
|---|---|---|---|
| `execution_id` | str | 所属 Execution | ✅ |
| `progress_percentage` | float | 0-100 | ✅ |
| `current_step_name` | str\|None | 当前 Step 名称 | — |
| `current_step_index` | int | 当前 Step 索引 | — |
| `total_steps` | int | Step 总数 | — |
| `completed_steps` | int | 已完成 Step 数 | — |
| `failed_steps` | int | 失败 Step 数 | — |
| `elapsed_seconds` | float | 已耗时 | ✅ |
| `estimated_remaining` | float\|None | 预估剩余秒数 | — |

```python
@dataclass
class ProgressSnapshot:
    execution_id: str
    progress_percentage: float = 0.0
    current_step_name: str | None = None
    current_step_index: int = 0
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    elapsed_seconds: float = 0.0
    estimated_remaining: float | None = None
```

### 4.8 TaskEvent（任务事件）

Execution 生命周期中关键事件的不可变日志（append-only）。

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| `event_id` | str | ✅ | UUID | ✅ |
| `execution_id` | str | ✅ | 所属 Execution | ✅ |
| `event_type` | str | ✅ | `state_change` / `retry_scheduled` / `timeout` / `cancelled` / `progress_update` / `warning` | ✅ |
| `from_status` | str\|None | — | 状态转换前（state_change 时） | ✅ |
| `to_status` | str\|None | — | 状态转换后 | ✅ |
| `message` | str | — | 人类可读描述 | ✅ |
| `metadata` | dict | — | 结构化附加上下文 | ✅ |
| `created_at` | str | ✅ | ISO 8601 | ✅ |

```python
@dataclass
class TaskEvent:
    event_id: str
    execution_id: str
    event_type: str
    from_status: str | None = None
    to_status: str | None = None
    message: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
```

### 4.9 TaskArtifact（任务产物）

Execution 产出的文件/数据引用（如生成的报告路径、导出的 CSV）。

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| `artifact_id` | str | ✅ | UUID | — |
| `execution_id` | str | ✅ | 所属 Execution | — |
| `name` | str | ✅ | 产物名称 | — |
| `type` | str | — | `file` / `data` / `report` / `log` | — |
| `path` | str\|None | — | 文件路径（type=file 时） | — |
| `size_bytes` | int | — | 文件大小 | — |
| `mime_type` | str | — | MIME 类型 | — |
| `created_at` | str | ✅ | ISO 8601 | — |

### 4.10 TaskDependency（任务依赖）

定义 Task 之间的依赖关系（后续任务等待前置任务完成）。

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| `dependency_id` | str | ✅ | UUID | — |
| `task_id` | str | ✅ | 当前 Task | — |
| `depends_on_task_id` | str | ✅ | 前置 Task | — |
| `depends_on_status` | str | — | 需要前置任务达到的状态（默认 `success`） | — |
| `timeout_seconds` | int | — | 等待前置超时（超时后是否跳过） | — |
| `on_timeout` | str | — | `skip` / `fail` | — |
| `created_at` | str | ✅ | ISO 8601 | — |

### 4.11 TaskSchedule（调度配置）

Job 的调度配置的独立实体（与 Job 1:1），便于调度器查询和管理。

| 字段 | 类型 | 必填 | 说明 | MVP |
|---|---|---|---|---|
| `schedule_id` | str | ✅ | UUID | ✅ |
| `job_id` | str | ✅ | 关联 Job | ✅ |
| `schedule_type` | str | ✅ | `cron` / `interval` / `once` / `manual` | ✅ |
| `cron_expression` | str\|None | — | cron 表达式（type=cron 时） | ✅ |
| `interval_seconds` | int\|None | — | 间隔秒数（type=interval 时） | ✅ |
| `once_at` | str\|None | — | 单次执行时间（type=once 时）ISO 8601 | ✅ |
| `timezone` | str | — | 时区，默认 `Asia/Shanghai` | ✅ |
| `next_run_at` | str\|None | — | 下次执行时间 | ✅ |
| `last_run_at` | str\|None | — | 上次执行时间 | ✅ |
| `created_at` | str | ✅ | ISO 8601 | ✅ |
| `updated_at` | str | ✅ | ISO 8601 | ✅ |

---

## 5. 状态机设计

### 5.1 状态定义

| 状态 | 含义 | 触发方式 | MVP |
|---|---|---|---|
| `pending` | 排队等待执行 | Job 被调度触发后，Execution 创建即进入 | ✅ |
| `queued` | 排队中（有 running Execution 达到 max_concurrent） | 并发控制拦截 | ✅ |
| `running` | 正在执行 | 调度器取到 Execution | ✅ |
| `success` | 执行成功（终态） | callable 正常返回 | ✅ |
| `partial_success` | 部分成功（终态） | callable 正常返回但有警告 | ✅ |
| `failed` | 执行失败（终态） | callable 抛异常且重试耗尽或不可重试 | ✅ |
| `retrying` | 等待重试 | callable 抛可重试异常 | ✅ |
| `paused` | 已暂停 | 用户暂停 Job | ✅ |
| `cancelled` | 已取消（终态） | 用户取消 | ✅ |
| `stale` | 已过期 | Execution 超时未完成 | ✅ |
| `blocked` | 被阻塞（等待前置依赖） | 依赖未满足 | — |

### 5.2 合法状态转换表

```python
VALID_TRANSITIONS = {
    "pending":       {"queued", "running", "cancelled"},
    "queued":        {"running", "cancelled"},
    "running":       {"success", "partial_success", "failed", "retrying", "paused", "cancelled", "stale"},
    "success":       set(),               # 终态
    "partial_success": set(),             # 终态
    "failed":        {"running"},         # 手动重试 → 重新 running
    "retrying":      {"running", "failed", "cancelled"},
    "paused":        {"running", "cancelled"},
    "cancelled":     set(),               # 终态
    "stale":         {"running"},         # 手动恢复
    "blocked":       {"pending", "cancelled"},  # Phase 3+
}
```

### 5.3 状态流图

```
                         ┌──────────┐
          Job 调度触发 → │ pending  │
                         └────┬─────┘
                              │ 并发检查
                    ┌─────────┴──────────┐
                    ▼                    ▼
              ┌─────────┐         ┌──────────┐
              │ running │         │ queued   │──→ running (slot free)
              └────┬────┘         └──────────┘
                   │
        ┌──────────┼──────────────────────────┐
        ▼          ▼                          ▼
   success    partial_success           ┌──────────┐
   (终态)     (终态)                    │ retrying │──→ running (backoff done)
                                        └────┬─────┘
                                             │ retries exhausted
                                             ▼
                                        ┌──────────┐
                                        │  failed  │ (终态)
                                        └──────────┘
        ┌──────────┐     ┌──────────┐     ┌──────────┐
        │ paused   │     │cancelled │     │  stale   │
        └────┬─────┘     └──────────┘     └──────────┘
             │ resume        (终态)            (终态，可
             ▼                                 手动重试→running)
        ┌──────────┐
        │ running  │
        └──────────┘
```

### 5.4 失败/重试/取消/暂停语义

**失败处理**：
1. callable 抛异常 → 检查 RetryPolicy。
2. 可重试（retry_count < max_retries 且异常类型匹配）→ `retrying` + 计算 backoff。
3. 不可重试（retry_count >= max_retries 或异常不匹配）→ `failed`（终态）。
4. 每次失败产生 ErrorRecord。

**重试处理**：
1. `retrying` → 等待 backoff 秒 → `running`（重新执行 callable）。
2. retry_count 递增。
3. 用户可在 `retrying` 状态取消执行。

**取消处理**：
1. `pending` / `queued` → `cancelled`（直接标记）。
2. `running` → 依赖 callable 自身的取消检查（如线程 Event/信号）；或超时后标记 `cancelled`。
3. `retrying` → `cancelled`（取消等待中的重试）。
4. MVP 不实现强制 kill 进程。

**暂停处理（Job 级别）**：
1. Job `status="paused"` → 不创建新的 Execution。
2. 已有 `running` Execution 不受影响。
3. `pending` / `queued` Execution 不受影响（保持原状态，等待执行）。

---

## 6. 存储设计

### 6.1 StorageBackend 抽象

```python
from abc import ABC, abstractmethod

class StorageBackend(ABC):
    """所有存储后端的抽象接口"""

    # --- TaskDefinition ---
    @abstractmethod def save_task(self, task: TaskDefinition) -> None: ...
    @abstractmethod def get_task(self, task_id: str) -> TaskDefinition | None: ...
    @abstractmethod def delete_task(self, task_id: str) -> None: ...
    @abstractmethod def list_tasks(self, module: str | None = None,
                                    tags: list[str] | None = None) -> list[TaskDefinition]: ...

    # --- JobInstance ---
    @abstractmethod def save_job(self, job: JobInstance) -> None: ...
    @abstractmethod def get_job(self, job_id: str) -> JobInstance | None: ...
    @abstractmethod def list_jobs(self, task_id: str | None = None,
                                   status: str | None = None) -> list[JobInstance]: ...
    @abstractmethod def get_scheduled_jobs(self) -> list[JobInstance]: ...

    # --- TaskExecution ---
    @abstractmethod def save_execution(self, exec: TaskExecution) -> None: ...
    @abstractmethod def get_execution(self, execution_id: str) -> TaskExecution | None: ...
    @abstractmethod def list_executions(self, job_id: str | None = None,
                                         status: str | None = None,
                                         limit: int = 20, offset: int = 0) -> list[TaskExecution]: ...
    @abstractmethod def count_executions(self, job_id: str | None = None,
                                          status: str | None = None) -> dict[str, int]: ...
    @abstractmethod def get_pending_executions(self) -> list[TaskExecution]: ...
    @abstractmethod def get_running_executions(self) -> list[TaskExecution]: ...

    # --- TaskStep ---
    @abstractmethod def save_step(self, step: TaskStep) -> None: ...
    @abstractmethod def get_steps(self, execution_id: str) -> list[TaskStep]: ...

    # --- ErrorRecord ---
    @abstractmethod def save_error(self, error: ErrorRecord) -> None: ...
    @abstractmethod def get_errors(self, execution_id: str) -> list[ErrorRecord]: ...

    # --- RetryPolicy ---
    @abstractmethod def save_retry_policy(self, policy: RetryPolicy) -> None: ...
    @abstractmethod def get_retry_policy(self, policy_id: str) -> RetryPolicy | None: ...

    # --- TaskEvent ---
    @abstractmethod def save_event(self, event: TaskEvent) -> None: ...
    @abstractmethod def get_events(self, execution_id: str,
                                    limit: int = 100) -> list[TaskEvent]: ...

    # --- TaskArtifact ---
    @abstractmethod def save_artifact(self, artifact: TaskArtifact) -> None: ...
    @abstractmethod def get_artifacts(self, execution_id: str) -> list[TaskArtifact]: ...

    # --- TaskDependency ---
    @abstractmethod def save_dependency(self, dep: TaskDependency) -> None: ...
    @abstractmethod def get_dependencies(self, task_id: str) -> list[TaskDependency]: ...

    # --- TaskSchedule ---
    @abstractmethod def save_schedule(self, schedule: TaskSchedule) -> None: ...
    @abstractmethod def get_schedule(self, job_id: str) -> TaskSchedule | None: ...
    @abstractmethod def get_due_schedules(self, before: str) -> list[TaskSchedule]: ...

    # --- Utility ---
    @abstractmethod def initialize(self) -> None: ...     # 建表/建集合
    @abstractmethod def close(self) -> None: ...
```

### 6.2 MongoDB 集合结构（MVP）

Pascal 已确认 task_center 使用 MongoDB 作为默认持久化，不采用 SQLite 作为 MVP 主存储。所有集合使用 `10_infra_tc_` 前缀，避免与 `03_data_ud_*`、TA-CN 无前缀集合和 Hermes Kanban DB 冲突。JSON 字段使用 MongoDB 原生 dict/list，时间字段使用 ISODate。

```javascript
// ============================================================
// task_center MongoDB Collections (MVP)
// database: tradingagents（可配置）
// prefix: 10_infra_tc_
// ============================================================

// 1) 任务定义
10_infra_tc_tasks: {
  _id: "task_id",
  name: string,
  description: string,
  module: string,
  callable_path: string,
  default_params: object,
  retry_policy_id: string,
  tags: [string],
  enabled: boolean,
  created_at: ISODate,
  updated_at: ISODate
}
indexes: [ {name:1}, {module:1}, {tags:1}, {enabled:1} ]

// 2) Job 实例/调度配置
10_infra_tc_jobs: {
  _id: "job_id",
  task_id: string,
  schedule: string,
  schedule_type: "cron"|"interval"|"once"|"manual"|"event"|"dependency"|"backfill"|"dry_run",
  params: object,
  enabled: boolean,
  status: "enabled"|"disabled"|"paused",
  max_concurrent: int,
  timeout_seconds: int,
  retry_policy_id: string,
  priority: int,
  idempotency_key_template: string,
  created_at: ISODate,
  updated_at: ISODate
}
indexes: [ {task_id:1}, {status:1}, {schedule_type:1}, {priority:-1} ]

// 3) 执行记录
10_infra_tc_executions: {
  _id: "execution_id",
  job_id: string,
  task_id: string,
  status: string,
  trigger: string,
  params: object,
  idempotency_key: string,
  claim_lock: string|null,
  claim_expires_at: ISODate|null,
  started_at: ISODate|null,
  finished_at: ISODate|null,
  elapsed_seconds: double,
  progress_percentage: double,
  current_step_index: int,
  result: object|string|null,
  retry_count: int,
  error_summary: string,
  warnings: [string],
  created_at: ISODate,
  updated_at: ISODate
}
indexes: [ {job_id:1}, {task_id:1}, {status:1}, {started_at:-1}, {idempotency_key:1}, {claim_expires_at:1} ]
unique indexes: [ {idempotency_key:1} partialFilterExpression: {idempotency_key: {$type:"string", $ne:""}} ]

// 4) 步骤进度
10_infra_tc_steps: {
  _id: "step_id",
  execution_id: string,
  name: string,
  description: string,
  step_index: int,
  weight: double,
  status: string,
  started_at: ISODate|null,
  finished_at: ISODate|null,
  error_message: string,
  data: object
}
indexes: [ {execution_id:1}, {execution_id:1, step_index:1} ]

// 5) 重试策略
10_infra_tc_retry_policies: {
  _id: "policy_id",
  max_retries: int,
  backoff: "fixed"|"exponential"|"linear",
  backoff_base_seconds: int,
  backoff_max_seconds: int,
  retry_on_exception_types: [string],
  no_retry_on_exception_types: [string]
}

// 6) 错误记录
10_infra_tc_error_records: {
  _id: "error_id",
  execution_id: string,
  step_id: string|null,
  attempt_number: int,
  error_type: string,
  error_message: string,
  traceback: string,
  created_at: ISODate
}
indexes: [ {execution_id:1}, {created_at:-1}, {error_type:1} ]

// 7) 事件日志
10_infra_tc_events: {
  _id: "event_id",
  execution_id: string,
  event_type: string,
  from_status: string|null,
  to_status: string|null,
  message: string,
  metadata: object,
  created_at: ISODate
}
indexes: [ {execution_id:1}, {event_type:1}, {created_at:-1} ]

// 8) 产物记录
10_infra_tc_artifacts: {
  _id: "artifact_id",
  execution_id: string,
  name: string,
  type: "file"|"url"|"json"|"text",
  path: string|null,
  size_bytes: int,
  mime_type: string,
  created_at: ISODate
}
indexes: [ {execution_id:1}, {type:1} ]

// 9) 依赖关系
10_infra_tc_dependencies: {
  _id: "dependency_id",
  task_id: string,
  depends_on_task_id: string,
  depends_on_status: string,
  timeout_seconds: int,
  on_timeout: "fail"|"skip"|"continue",
  created_at: ISODate
}
indexes: [ {task_id:1}, {depends_on_task_id:1} ]

// 10) 调度计划
10_infra_tc_schedules: {
  _id: "schedule_id",
  job_id: string,
  schedule_type: string,
  cron_expression: string|null,
  interval_seconds: int|null,
  once_at: ISODate|null,
  timezone: string,
  next_run_at: ISODate|null,
  last_run_at: ISODate|null,
  created_at: ISODate,
  updated_at: ISODate
}
indexes: [ {job_id:1}, {next_run_at:1}, {schedule_type:1} ]
unique indexes: [ {job_id:1} ]
```

### 6.3 存储命名建议

| 层级 | 前缀 | 示例 | 说明 |
|---|---|---|---|
| task_center MongoDB | `10_infra_tc_` | `10_infra_tc_tasks`, `10_infra_tc_executions` | MVP 默认持久化 |
| task_center SQLite | `tc_` | `tc_tasks`, `tc_executions` | 本地单元测试/离线降级，可选 |
| unified_data MongoDB | `03_data_ud_` | `03_data_ud_cache_kline_daily` | 独立前缀 |
| TA-CN MongoDB | 无前缀 | `stock_basic_info`, `stock_daily_quotes` | 不改动 |

**关键约束**：
- 不复用 Hermes Kanban DB（`~/.hermes/kanban.db`）。
- 不直接写 TA-CN scheduler/queue/progress 集合。
- 不写 `03_data_ud_*` 数据集合；task_center 只记录任务执行状态。
- MongoDB 默认 database 建议为项目现有 `tradingagents`，但集合必须使用 `10_infra_tc_*` 前缀。
- 测试环境必须使用隔离 database 或 mongomock，禁止测试写生产库。

### 6.4 SQLite 可选降级（非 MVP 主路径）

SQLite 仅保留两种用途：

1. **本地单元测试**：不依赖 MongoDB 服务时，用内存 SQLite 或 fixture 模拟 StorageBackend。
2. **离线降级**：MongoDB 不可用且用户明确选择本地模式时，可临时使用 `data/task_center.db`。

SQLite 不作为生产路径、不作为默认 MVP 存储、不作为后续迁移前置条件；因此不存在 SQLite → MongoDB 的正式迁移要求。

---

## 7. 调度与触发设计

### 7.1 触发类型总览

| 触发类型 | schedule_type | 触发方式 | 说明 | MVP |
|---|---|---|---|---|
| `cron` | `"cron"` | 调度器定时检查 | 标准 cron 表达式 | ✅ |
| `interval` | `"interval"` | 调度器定时检查 | 固定间隔秒数 | ✅ |
| `once` | `"once"` | 指定时间单次 | 执行后 Job 自动 disable | ✅ |
| `manual` | `"manual"` | CLI / Python API | 手动触发，不自动调度 | ✅ |
| `event` | `"event"` | 外部事件 | 事件驱动触发（Phase 3+） | — |
| `dependency` | — | 前置任务完成 | 依赖触发（Phase 3+） | — |
| `backfill` | — | CLI 批量回填 | 一次性批量回填任务 | — |
| `dry_run` | — | CLI | 不实际执行 callable，只输出"将要执行什么" | ✅ |

### 7.2 调度器循环设计

```python
class SchedulerLoop:
    """
    主调度循环，运行在后台线程中。

    循环逻辑：
    1. 每 tick_interval 秒（默认 1s）扫描一次。
    2. 查询 `10_infra_tc_schedules` 中 next_run_at <= now 且 job 状态为 enabled 的记录。
    3. 查询 `10_infra_tc_executions` 中 status=pending/queued 的记录，检查并发上限。
    4. 如果可执行：创建 Execution（pending）→ 提交到 Executor。
    5. 如果达并发上限：Execution 标记为 queued。
    6. 处理 retrying 状态的 Execution：检查 backoff 是否到期 → running。
    7. 检查 running Execution 的 timeout → stale。
    8. 更新 next_run_at。
    """

    def __init__(self, storage: StorageBackend, executor: TaskExecutor,
                 tick_interval: float = 1.0):
        self.storage = storage
        self.executor = executor
        self.tick_interval = tick_interval
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        """启动调度循环（后台线程）"""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止调度循环"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Scheduler tick error: {e}")
            time.sleep(self.tick_interval)

    def _tick(self):
        # 1. 处理到期的调度
        due = self.storage.get_due_schedules(before=now_iso())
        for schedule in due:
            job = self.storage.get_job(schedule.job_id)
            if job and job.status == "enabled":
                self._create_execution(job)

        # 2. 处理排队的 Execution
        for exec in self.storage.get_queued_executions():
            job = self.storage.get_job(exec.job_id)
            if job and self._can_run(job):
                self._transition_execution(exec, "running")
                self.executor.submit(exec, job)

        # 3. 处理 retrying
        for exec in self.storage.get_retrying_executions():
            policy = self._get_retry_policy(exec)
            if self._backoff_expired(exec, policy):
                self._transition_execution(exec, "running")
                self.executor.submit(exec, job)

        # 4. 检查超时
        for exec in self.storage.get_running_executions():
            if self._is_stale(exec):
                self._transition_execution(exec, "stale")
```

### 7.3 ScheduleParser

```python
class ScheduleParser:
    """解析调度规则字符串，计算 next_run_at"""

    @staticmethod
    def parse(schedule: str, timezone: str = "Asia/Shanghai") -> TaskSchedule:
        """
        schedule 格式：
        - "0 15 * * 1-5" → cron
        - "3600" → interval（整数秒）
        - "once:2026-07-15T09:00:00" → once
        - "manual" → manual

        返回 TaskSchedule 对象，含 next_run_at。
        """
```

### 7.4 幂等 key 设计

```python
class IdempotencyManager:
    """
    基于幂等 key 防重复执行。

    使用场景：
    - 数据刷新任务：idempotency_key = "{task_id}:{trade_date}"
    - 如果已存在相同 key 且 status ∈ {success, partial_success} 的 Execution，
      则跳过本次执行。

    如果存在相同 key 且 status = failed，允许重新执行（覆盖）。
    """

    def can_execute(self, idempotency_key: str) -> bool:
        """检查是否可执行（无重复成功记录）"""
        existing = self.storage.get_execution_by_idemp_key(idempotency_key)
        if existing and existing.status in ("success", "partial_success", "running", "pending", "retrying"):
            return False
        return True
```

### 7.5 并发控制

```python
class ConcurrencyControl:
    """
    限制同一 Job 同时运行的 Execution 数量。

    规则：
    - max_concurrent=1：上一个完成后才执行下一个。
    - max_concurrent=N：最多 N 个并行。
    - 超出限制的 Execution 标记为 queued，等待 slot 释放。
    """

    def can_run(self, job: JobInstance) -> bool:
        """检查是否有可用 slot"""
        running_count = self.storage.count_executions(
            job.job_id, status="running"
        )["running"]
        return running_count < job.max_concurrent
```

---

## 8. 执行器设计

### 8.1 TaskExecutor 抽象

```python
from abc import ABC, abstractmethod

class TaskExecutor(ABC):
    """任务执行器抽象基类"""

    @abstractmethod
    def submit(self, execution: TaskExecution, job: JobInstance) -> None:
        """
        提交执行。

        实现负责：
        1. 解析 callable_path → 加载实际函数。
        2. 合并 params（job.params 覆盖 task.default_params）。
        3. 执行前设置 status=running + 记录 TaskEvent。
        4. 执行 callable(params)。
        5. 正常返回 → status=success/partial_success。
        6. 异常 → RetryManager 判断 → retrying 或 failed。
        7. 执行后记录 elapsed_seconds + TaskEvent + ErrorRecord（如有）。
        8. Heartbeat 持续更新 updated_at。
        """
        ...

    @abstractmethod
    def cancel(self, execution_id: str) -> bool:
        """取消执行。返回 True 表示成功取消。"""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """关闭执行器，等待所有执行完成。"""
        ...
```

### 8.2 执行器实现层级

| 执行器 | 说明 | MVP | 实现要点 |
|---|---|---|---|
| **InProcessExecutor** | callable 在当前进程中同步执行 | ✅ | 简单直接，适合短任务；长时间运行会阻塞调度循环，需要用线程包装 |
| **SubprocessExecutor** | callable 在独立 subprocess 中执行（Phase 2+） | — | `subprocess.Popen` + stdout/stderr 捕获；支持超时 kill；适合可能崩溃的任务 |
| **AsyncExecutor** | asyncio 异步执行（Phase 3+） | — | 适合 I/O 密集型任务；需要 callable 是 async 函数 |

**InProcessExecutor 核心设计**：

```python
class InProcessExecutor(TaskExecutor):
    def __init__(self, storage: StorageBackend, retry_mgr: RetryManager,
                 progress: ProgressTracker, error_store: ErrorStore,
                 heartbeat: HeartbeatMonitor):
        self.storage = storage
        self.retry_mgr = retry_mgr
        self.progress = progress
        self.error_store = error_store
        self.heartbeat = heartbeat
        self._running: dict[str, threading.Thread] = {}
        self._cancel_events: dict[str, threading.Event] = {}

    def submit(self, execution: TaskExecution, job: JobInstance):
        thread = threading.Thread(
            target=self._execute,
            args=(execution, job),
            daemon=True
        )
        self._running[execution.execution_id] = thread
        self._cancel_events[execution.execution_id] = threading.Event()
        thread.start()

    def _execute(self, execution: TaskExecution, job: JobInstance):
        try:
            # 更新状态
            self._transition(execution, "running")
            self.heartbeat.register(execution.execution_id)

            # 加载 callable
            callable_fn = self._load_callable(job)

            # 合并参数
            task = self.storage.get_task(job.task_id)
            merged_params = {**task.default_params, **job.params, **execution.params}

            # 执行
            result = callable_fn(**merged_params)

            # 判断部分成功
            if isinstance(result, dict) and result.get("warnings"):
                self._transition(execution, "partial_success",
                                 warnings=result["warnings"])
            else:
                self._transition(execution, "success")
        except Exception as e:
            # 记录错误
            attempt = execution.retry_count + 1
            self.error_store.record(execution.execution_id, e, attempt)

            # 判断重试
            policy = self.retry_mgr.get_policy(execution, job)
            if self.retry_mgr.should_retry(e, execution.retry_count, policy):
                self._transition(execution, "retrying")
                backoff = self.retry_mgr.compute_backoff(
                    execution.retry_count, policy
                )
                # backoff 后在 scheduler loop 中重新提交
            else:
                self._transition(execution, "failed")
        finally:
            self.heartbeat.unregister(execution.execution_id)
            self._running.pop(execution.execution_id, None)
            self._cancel_events.pop(execution.execution_id, None)
```

### 8.3 Timeout / Cancellation / Heartbeat

**Timeout**：
- Job.timeout_seconds 设置超时。
- HeartbeatMonitor 每 30s 检查 running Execution 的 updated_at。
- elapsed > timeout_seconds → 标记 stale。
- MVP 不强制 kill 线程（Python 线程无法安全 kill）。

**Cancellation**：
- InProcessExecutor 使用 `threading.Event` 作为协作式取消信号。
- callable 需要定期检查 `task_center.is_cancelled()` 并自行退出。
- 不在 MVP 中实现强制 kill。

**Heartbeat**：
- callable 执行期间，HeartbeatMonitor 要求每 30s 更新一次 Execution.updated_at。
- 框架提供 `task_center.heartbeat()` 函数供 callable 调用。
- 超时未更新 → stale。

---

## 9. Retry / Backoff / Failure Policy

### 9.1 RetryManager

```python
class RetryManager:
    """
    管理重试决策和退避计算。

    决策流程：
    1. 获取 RetryPolicy（Execution 级 > Job 级 > Task 级 > 默认）。
    2. 检查异常类型是否匹配 retry_on / no_retry_on。
    3. 检查 retry_count < max_retries。
    4. 计算 backoff 延迟。
    """

    def should_retry(self, exception: Exception, retry_count: int,
                     policy: RetryPolicy) -> bool:
        """判断是否应该重试"""
        if policy.max_retries == 0:
            return False
        if retry_count >= policy.max_retries:
            return False

        exc_name = type(exception).__name__

        # no_retry_on 优先
        if policy.no_retry_on_exception_types:
            if any(exc_name == t or issubclass(type(exception), _resolve(t))
                   for t in policy.no_retry_on_exception_types):
                return False

        # retry_on 过滤
        if policy.retry_on_exception_types:
            if not any(exc_name == t or issubclass(type(exception), _resolve(t))
                       for t in policy.retry_on_exception_types):
                return False

        return True

    def compute_backoff(self, retry_count: int, policy: RetryPolicy) -> float:
        """计算退避延迟秒数"""
        if policy.backoff == "fixed":
            return min(policy.backoff_base_seconds, policy.backoff_max_seconds)
        elif policy.backoff == "exponential":
            return min(
                policy.backoff_base_seconds * (2 ** retry_count),
                policy.backoff_max_seconds
            )
        elif policy.backoff == "linear":
            return min(
                policy.backoff_base_seconds * (retry_count + 1),
                policy.backoff_max_seconds
            )
        return 30  # fallback
```

### 9.2 重试策略预置

| policy_id | max_retries | backoff | base_seconds | max_seconds | 用途 |
|---|---|---|---|---|---|
| `default` | 3 | fixed | 30 | 300 | 通用默认 |
| `no_retry` | 0 | fixed | 0 | 0 | 禁止重试 |
| `aggressive` | 5 | exponential | 10 | 600 | 对网络抖动敏感的任务 |
| `data_refresh` | 3 | exponential | 60 | 1800 | 数据刷新（Tushare 限流恢复） |

### 9.3 不可重试异常类型（MVP 预置）

```python
# 这些异常类型在任何重试策略下都不会重试
NON_RETRYABLE_DEFAULTS = [
    "ValueError",        # 参数错误
    "TypeError",         # 类型错误
    "KeyError",          # 数据缺失
    "AttributeError",    # 接口不兼容
    "ImportError",       # 依赖缺失
    "SyntaxError",       # 代码错误
]
```

### 9.4 Poison Task 保护

- 同一 Execution 连续失败 3 次以上（retry_count > 3）且每次失败时间 < 10s → 判定为 poison task。
- Poison task 自动标记 failed，不进入下一次调度。
- Job 级别的 poison task 检测：同一 Job 的最近 10 次 Execution 全部 failed → Job 自动 disable。

---

## 10. Progress / Dashboard / API 边界

### 10.1 ProgressTracker

```python
class ProgressTracker:
    """
    Step 权重驱动进度计算。

    MVP（百分比模式）：
    - callable 调用 update_progress(execution_id, 45.5) 直接设置百分比。
    - get_progress() 返回 ProgressSnapshot。

    Phase 2+（Step 模式）：
    - callable 调用 create_steps(execution_id, steps) 注册步骤。
    - callable 调用 update_step(step_id, status="completed") 更新步骤。
    - 进度 = Σ(completed_step.weight) + running_step.progress_in_step * running_step.weight。
    """

    def update_progress(self, execution_id: str, progress: float) -> None:
        """更新百分比进度（0-100）"""
        exec = self.storage.get_execution(execution_id)
        exec.progress_percentage = max(0.0, min(100.0, progress))
        self.storage.save_execution(exec)

    def get_progress(self, execution_id: str) -> ProgressSnapshot:
        """获取进度快照"""
        exec = self.storage.get_execution(execution_id)
        steps = self.storage.get_steps(execution_id)  # Phase 2+

        snapshot = ProgressSnapshot(
            execution_id=execution_id,
            progress_percentage=exec.progress_percentage,
            elapsed_seconds=exec.elapsed_seconds,
        )

        if steps:
            snapshot.total_steps = len(steps)
            snapshot.completed_steps = sum(1 for s in steps if s.status == "completed")
            snapshot.failed_steps = sum(1 for s in steps if s.status == "failed")
            running_step = next((s for s in steps if s.status == "running"), None)
            if running_step:
                snapshot.current_step_name = running_step.name
                snapshot.current_step_index = running_step.index
            # 预估剩余
            if snapshot.elapsed_seconds > 0 and snapshot.progress_percentage > 0:
                snapshot.estimated_remaining = (
                    snapshot.elapsed_seconds / snapshot.progress_percentage * 100
                    - snapshot.elapsed_seconds
                )

        return snapshot
```

### 10.2 CLI 命令完整定义

```text
yq task
  yq task list                [--module <m>] [--tags <t1,t2>]    表格输出
  yq task info                <task_id>                          YAML 格式详情

yq job
  yq job list                 [--task <task_id>] [--status <s>] 表格输出
  yq job show                 <job_id>                           YAML 格式详情
  yq job create               <task_id> --schedule <s> [--params <json>]
  yq job pause                <job_id>
  yq job resume               <job_id>
  yq job disable              <job_id>
  yq job enable               <job_id>
  yq job run                  <job_id> [--params <json>] [--dry-run]  # 手动触发
  yq job backfill             <job_id> [--start <date>] [--end <date>]

yq exec
  yq exec list                [--job <job_id>] [--status <s>] [--limit <n>] [--offset <n>]
  yq exec show                <execution_id>
  yq exec cancel              <execution_id>
  yq exec retry               <execution_id>
  yq exec progress            <execution_id>
  yq exec events              <execution_id> [--limit <n>]

yq errors
  yq errors list              <execution_id>

yq scheduler
  yq scheduler start          [--blocking]
  yq scheduler stop
  yq scheduler status
  yq scheduler tick            # 手动触发一次调度循环（调试用）
```

**CLI 输出约定**：
- list 命令以表格形式输出（手动对齐或 tabulate）。
- show/info 以 YAML 分节格式输出。
- 状态字段带颜色：running=绿, failed=红, retrying=黄, success=绿, cancelled=灰, stale=橙。
- `--json` 标志转为 JSON 输出。

### 10.3 Python API 完整定义

```python
# ============================================================
# skills/infra/task_center/api/ 公开接口
# ============================================================

# --- Task API (api/tasks.py) ---

def register_task(
    task_id: str,
    callable: Callable,
    *,
    name: str = "",
    description: str = "",
    module: str = "",
    retry_policy_id: str = "default",
    default_params: dict | None = None,
    tags: list[str] | None = None,
) -> TaskDefinition: ...

def unregister_task(task_id: str) -> None: ...
def get_task(task_id: str) -> TaskDefinition: ...
def list_tasks(module: str | None = None, tags: list[str] | None = None) -> list[TaskDefinition]: ...

# --- Job API (api/jobs.py) ---

def create_job(
    task_id: str,
    schedule: str,
    *,
    params: dict | None = None,
    max_concurrent: int = 1,
    timeout_seconds: int = 3600,
    retry_policy_id: str | None = None,
    priority: int = 0,
    idempotency_key_template: str = "",
) -> JobInstance: ...

def get_job(job_id: str) -> JobInstance: ...
def list_jobs(task_id: str | None = None, status: str | None = None) -> list[JobInstance]: ...
def pause_job(job_id: str) -> None: ...
def resume_job(job_id: str) -> None: ...
def disable_job(job_id: str) -> None: ...
def enable_job(job_id: str) -> None: ...

# --- Execution API (api/executions.py) ---

def trigger_job(job_id: str, *, params_override: dict | None = None,
                trigger: str = "manual", dry_run: bool = False) -> TaskExecution: ...
def get_execution(execution_id: str) -> TaskExecution: ...
def list_executions(job_id: str | None = None, status: str | None = None,
                    limit: int = 20, offset: int = 0) -> list[TaskExecution]: ...
def count_executions(job_id: str | None = None, status: str | None = None) -> dict[str, int]: ...
def cancel_execution(execution_id: str) -> None: ...
def retry_execution(execution_id: str) -> TaskExecution: ...
def get_events(execution_id: str, limit: int = 100) -> list[TaskEvent]: ...
def get_errors(execution_id: str) -> list[ErrorRecord]: ...

# --- Progress API (api/progress_api.py) ---

def get_progress(execution_id: str) -> ProgressSnapshot: ...
def update_progress(execution_id: str, progress: float) -> None: ...
def create_steps(execution_id: str, steps: list[dict]) -> list[TaskStep]: ...  # Phase 2+
def update_step(step_id: str, *, status: str | None = None,
                data: dict | None = None) -> TaskStep: ...                     # Phase 2+

# --- Scheduler API (api/scheduler_api.py) ---

def start_scheduler(blocking: bool = False) -> None: ...
def stop_scheduler() -> None: ...
def get_scheduler_status() -> dict: ...

# --- Heartbeat ---

def heartbeat() -> None:
    """callable 内部调用，更新当前 Execution 的 updated_at"""
    ...

def is_cancelled() -> bool:
    """callable 内部调用，检查是否被取消"""
    ...

# --- Retry Policy ---

def register_retry_policy(policy: RetryPolicy) -> RetryPolicy: ...
def get_retry_policy(policy_id: str) -> RetryPolicy: ...
```

### 10.4 Dashboard 边界

**MVP（Phase 3 前）**：只提供 CLI + Python API，不做 Web Dashboard。

**Phase 6（可选）**：简单 HTML Dashboard，内容包括：
- 任务总览卡片：enabled/paused/disabled Job 数。
- 执行状态流：最近 20 条 Execution 状态时间线。
- 失败任务高亮：最近失败的 Execution 列表。
- 数据质量摘要入口（关联 unified_data 的 quality_summary）。
- retry/pause/resume/cancel 操作按钮。
- 不做实时 WebSocket 推送，只做轮询刷新。

---

## 11. 与 unified_data 的接口

引用 `DESIGN-03-007` §10（task_center 接口）。task_center 通过 callable_path 间接调用 unified_data 刷新函数，不直接 import。

### 11.1 数据刷新任务类型清单

| 任务 ID | 名称 | 域 | 调度建议 | 幂等 key | MVP |
|---|---|---|---|---|---|
| `unified_data.daily_kline_cn` | A股日线行情刷新 | market_data | 交易日 15:30（cron） | `daily_kline_cn:{trade_date}` | ✅ |
| `unified_data.realtime_quotes_cn` | 实时行情快照 | market_data | 盘中每5分钟（interval=300） | `realtime_quotes_cn:{snapshot_time}` | — |
| `unified_data.financial_refresh` | 财务数据刷新 | financial | 每周一次（cron） | `financial:{report_period}` | — |
| `unified_data.daily_basic_cn` | A股估值指标刷新 | valuation | 交易日 16:00（cron） | `daily_basic_cn:{trade_date}` | — |
| `unified_data.trading_calendar_refresh` | 交易日历刷新 | calendar | 年初/季初（cron） | `trading_calendar:{year}` | — |
| `unified_data.sector_snapshot_cn` | 板块快照刷新 | sector | 交易日 16:30（cron） | `sector_snapshot_cn:{snapshot_date}` | — |
| `unified_data.sentiment_snapshot_cn` | 市场情绪快照刷新 | sentiment | 交易日 15:30（cron） | `sentiment_snapshot_cn:{snapshot_date}` | — |
| `unified_data.capital_flow_cn` | 资金流刷新 | flow | 交易日 16:00（cron） | `capital_flow_cn:{trade_date}` | — |
| `unified_data.dragon_tiger_cn` | 龙虎榜刷新 | events | 交易日 17:00（cron） | `dragon_tiger_cn:{trade_date}` | — |
| `unified_data.chip_distribution_cn` | 筹码分布刷新 | events | 每周一次（cron） | `chip_cn:{trade_date}` | — |
| `unified_data.quality_summary` | 数据质量汇总 | quality | 每天一次（cron） | `quality:{check_date}` | — |
| `unified_data.audit_cleanup` | 审计日志清理 | audit | 每周一次（cron） | `audit_cleanup:{week}` | — |

### 11.2 任务注册集成模板

```python
# skills/infra/task_center/integrations/unified_data.py

def register_unified_data_jobs():
    """由 unified_data 启动时调用，或在 task_center 启动时加载"""

    # 注册 Task
    register_task(
        task_id="unified_data.daily_kline_cn",
        callable=None,  # 通过 callable_path 延迟加载
        callable_path="unified_data.tasks.refresh_daily_kline:refresh_daily_kline_cn",
        name="A股日线行情刷新",
        module="unified_data",
        retry_policy_id="data_refresh",
        tags=["数据", "日线", "A股"],
    )

    # 创建 Job
    create_job(
        task_id="unified_data.daily_kline_cn",
        schedule="0 15 * * 1-5",  # 工作日 15:00 UTC+8 → cron as 15:00
        idempotency_key_template="daily_kline_cn:{trade_date}",
        timeout_seconds=7200,
        retry_policy_id="data_refresh",
    )

    # ... 其他 11 个任务类似
```

### 11.3 刷新操作接口契约

unified_data 暴露给 task_center 的 callable 必须满足：

1. **返回格式**：`dict` 包含 `{"success": int, "failed": int, "errors": list[str], "warnings": list[str], "elapsed_seconds": float}`
2. **参数接口**：接受 keyword arguments，支持 `date`、`securities` 等业务参数。
3. **幂等性**：同一 `trade_date` 重复调用不产生重复数据。
4. **进度报告**：长时间任务应调用 `task_center.update_progress(execution_id, pct)` 和 `task_center.heartbeat()`。
5. **取消支持**：定期检查 `task_center.is_cancelled()` 并优雅退出。

---

## 12. 与 stock framework 的接口

引用 `SPEC-08-001` §10（task_center 边界）。stock framework 通过 task_center 注册批量任务，但业务逻辑由 stock framework 自己实现。

### 12.1 Stock Framework 任务类型清单

| 任务 ID | 名称 | 说明 | 调度建议 | MVP |
|---|---|---|---|---|
| `stock.refresh_quant_profile` | 批量量化画像刷新 | 刷新全市场或指定 universe 的 StockQuantProfile | interval=3600 或 cron | ✅ |
| `stock.score_strategy_models` | 策略模型批量评分 | 对所有 profile 运行 6 类模型评分 | interval=3600 | ✅ |
| `stock.generate_stock_report` | 单股深度报告生成 | 对指定 security_id 生成 ReportBundle | manual / event | — |
| `stock.batch_scan_universe` | Universe 批量扫描 | 对股票池做全量量化扫描 | interval=86400 | — |
| `stock.backfill_model_scores` | 模型评分回填 | 历史模型评分批量回填 | backfill | — |
| `stock.portfolio_fit_refresh` | 组合适配刷新 | 刷新当前组合所有持仓的 PortfolioFitAdvice | interval=86400 | — |

### 12.2 任务注册集成模板

```python
# skills/infra/task_center/integrations/stock_framework.py

def register_stock_framework_jobs():
    register_task(
        task_id="stock.refresh_quant_profile",
        callable_path="stock.profile_builder:batch_refresh_profiles",
        name="批量量化画像刷新",
        module="stock",
        retry_policy_id="default",
        tags=["研究", "画像", "批量"],
    )
    create_job(
        task_id="stock.refresh_quant_profile",
        schedule="3600",
        timeout_seconds=10800,  # 3h
        max_concurrent=1,
    )

    register_task(
        task_id="stock.score_strategy_models",
        callable_path="stock.model_scorer:batch_score_models",
        name="策略模型批量评分",
        module="stock",
        retry_policy_id="default",
        tags=["研究", "评分", "批量"],
    )
    create_job(
        task_id="stock.score_strategy_models",
        schedule="3600",
        timeout_seconds=7200,
        max_concurrent=1,
    )
```

### 12.3 接口契约

- stock framework 的 callable 不直接访问 `unified_data`，而是通过注入方式获取数据（由 stock framework 内部管理，task_center 不关心）。
- task_center 不理解 ModelScore、Profile 等投资概念，只负责调度和执行。
- stock framework callable 必须满足与 unified_data 相同的接口契约（返回 dict、支持 heartbeat、支持 cancel）。

---

## 13. 与 TA-CN / DSA 的迁移边界

### 13.1 总体策略

**不分阶段直接替换，保持共存参考，后续渐进迁移。**

| 阶段 | 动作 | 风险 |
|---|---|---|
| 阶段 0（当前） | task_center 独立开发，不与 TA-CN 交互 | 无 |
| 阶段 1（MVP 后） | task_center 用于 unified_data / stock 等新模块，TA-CN 保持不变 | 低 |
| 阶段 2（Phase 7） | 为 TA-CN 的 data_sync 类任务编写 adapter，与现有 Redis 队列并存 | 中 |
| 阶段 3（远期） | TA-CN 内部可选替换为 task_center，移除 Redis 队列依赖 | 高 |

### 13.2 TA-CN 现有调度系统分析

| TA-CN 组件 | 路径 | 核心功能 | task_center 可替代 |
|---|---|---|---|
| SchedulerService | `scheduler_service.py` | 基于 APScheduler + MongoDB 的定时任务管理，含暂停/恢复/手动触发/执行历史 | ✅ 核心替代目标 |
| QueueService | `queue_service.py` | 基于 Redis List 的 FIFO 队列，含并发控制和可见性超时 | ✅ 由 ConcurrencyControl + SchedulerLoop 替代 |
| ProgressTracker | `progress/tracker.py` | 基于 Redis 的进度追踪，含动态步骤生成 | ✅ 由 ProgressTracker 替代 |
| TushareSyncService | `tushare_sync_service.py` | Tushare 数据同步 worker | ⚠️ 业务逻辑不变，调度层替代 |
| AKShareSyncService | `akshare_sync_service.py` | AKShare 数据同步 worker | ⚠️ 同上 |
| MultiPeriodSyncService | `multi_period_sync_service.py` | 多周期数据同步 | ⚠️ 同上 |

### 13.3 TA-CN Adapter 设计（Phase 7 参考）

```python
# skills/infra/task_center/integrations/ta_cn_adapter.py

class TA_CNTaskAdapter:
    """
    将 TA-CN 现有的 data_sync 任务包装为 task_center Task。

    策略：
    - 不修改 TA-CN 代码。
    - 通过 callable_path 指向 TA-CN 现有同步函数。
    - task_center 的 Job 与 TA-CN 的 APScheduler Job 并存运行（双写验证阶段）。
    - 验证通过后，TA-CN 侧 disable APScheduler Job。
    """

    @staticmethod
    def register_ta_cn_tasks():
        register_task(
            task_id="ta_cn.sync_tushare_daily",
            callable_path="tradingagents.app.worker.tushare_sync_service:sync_daily",
            name="TA-CN Tushare日线同步",
            module="ta_cn",
            tags=["TA-CN", "数据"],
        )
        # ... 更多 TA-CN 任务
```

### 13.4 DSA 迁移边界

- DSA 日常分析任务（LLM 驱动）不适合 task_center（LLM 推理开销大，应由 Hermes cron 触发）。
- DSA 的数据获取部分（BaseFetcher → 数据写入 SQLite）可通过 task_center adapter 调度。
- 不修改 DSA 现有 GitHub Actions / 调度配置。
- 未来可选：DSA 的报告生成任务注册到 task_center 作为后处理步骤。

---

## 14. 文件清单（后续实现预计新增/修改）

### 新增文件

```
skills/infra/task_center/
├── __init__.py
├── SKILL.md
├── config.py
├── cli.py
├── core/
│   ├── __init__.py
│   ├── entities.py
│   ├── state_machine.py
│   ├── registry.py
│   ├── idempotency.py
│   └── exceptions.py
├── storage/
│   ├── __init__.py
│   ├── backend.py
│   ├── mongo_backend.py
│   ├── mongo_schema.py
│   └── sqlite_backend.py  # optional local/test fallback
├── scheduler/
│   ├── __init__.py
│   ├── schedule_parser.py
│   ├── scheduler_loop.py
│   ├── trigger_manager.py
│   └── concurrency_control.py
├── executor/
│   ├── __init__.py
│   ├── base.py
│   └── in_process.py
├── runtime/
│   ├── __init__.py
│   ├── progress.py
│   ├── retry.py
│   ├── error_store.py
│   └── heartbeat.py
├── api/
│   ├── __init__.py
│   ├── tasks.py
│   ├── jobs.py
│   ├── executions.py
│   ├── progress_api.py
│   └── scheduler_api.py
└── integrations/
    ├── __init__.py
    └── unified_data.py

tests/infra/task_center/
├── __init__.py
├── conftest.py
├── test_entities.py
├── test_state_machine.py
├── test_registry.py
├── test_idempotency.py
├── test_schedule_parser.py
├── test_mongo_backend.py
├── test_scheduler_loop.py
├── test_in_process_executor.py
├── test_progress_tracker.py
├── test_retry_manager.py
├── test_error_store.py
├── fixtures/
│   ├── __init__.py
│   ├── mock_callable.py
│   └── mock_storage.py
└── integration/
    ├── __init__.py
    ├── test_full_register_trigger_flow.py
    ├── test_retry_and_failure.py
    └── test_cli_smoke.py
```

### 不修改的文件（严禁修改清单）

```
skills/apps/TradingAgents-CN/**        # TA-CN 子项目
skills/research/daily_stock_analysis/** # DSA 子系统
skills/data/unified_data/**             # unified_data 模块
skills/research/stock/**                # stock framework
skills/data/data-pipeline/**            # ETL 管道
skills/data/data_interface/**           # Portfolio IReader/IWriter
skills/research/argus/**                # Argus 信号系统
scripts/*.sh                            # 现有 cron 脚本
系统 cron/systemd 配置                   # 守护配置
~/.hermes/kanban.db                     # Hermes Kanban DB
生产 MongoDB tradingagents 数据库        # 现有业务数据
```

---

## 15. 分阶段实现路线

### Phase 0: Skeleton + Core Models + State Machine（预计 1-2 天）

**范围**：
- 11 类实体 dataclass 定义（`core/entities.py`）
- StateMachine（9 状态 + 12 转换 + 非法转换拒绝）
- TaskRegistry（注册/注销/查询）
- IdempotencyManager（幂等 key 检查）
- 18 种异常定义（`core/exceptions.py`）
- 目录结构骨架 + `__init__.py` + `SKILL.md`
- pytest fixture scaffold

**产物**：
- `skills/infra/task_center/core/` 5 个文件
- `skills/infra/task_center/__init__.py`
- `skills/infra/task_center/SKILL.md`
- `tests/infra/task_center/conftest.py` + fixtures

**验收标准**：
- 所有实体 dataclass 构造与字段验证通过。
- StateMachine `VALID_TRANSITIONS` 全部路径测试通过。
- StateMachine 拒绝非法转换（如 success → running）抛 `InvalidStateTransitionError`。
- TaskRegistry register/unregister/list 功能正确。
- IdempotencyManager can_execute 幂等逻辑正确。
- 单元测试覆盖率 ≥ 80%（Phase 0 无外部依赖）。

**风险**：低
**是否需要 Verify/Review**：否（纯模型层无副作用）

---

### Phase 1: MongoDB Storage + CRUD + Events（预计 2-3 天）

**范围**：
- StorageBackend 抽象基类
- MongoDBBackend 完整实现（10 个 `10_infra_tc_*` 集合 + 索引 + CRUD）
- mongo_schema.py（集合/索引初始化、schema version 标记）
- TaskEvent 完整记录（状态变更时自动写入）
- TaskSchedule CRUD
- 预置 4 个默认 RetryPolicy
- 存储层单元测试（CRUD、分页、过滤、索引验证）

**产物**：
- `skills/infra/task_center/storage/` 3 个文件
- `tests/infra/task_center/test_mongo_backend.py`

**验收标准**：
- MongoDBBackend 所有 CRUD 操作通过（Task/Job/Execution/Step/Error/Event/Schedule/RetryPolicy/Artifact/Dependency）。
- list_executions 分页 + 状态过滤正确。
- count_executions 统计正确。
- 并发 claim 使用原子 `find_one_and_update`，不得重复领取同一 Execution。
- MongoDB URI / database / collection prefix 可配置，默认复用项目 `tradingagents` 数据库，集合前缀为 `10_infra_tc_`。
- 单元测试覆盖率 ≥ 70%。

**风险**：中（MongoDB 索引、原子 claim、网络/连接失败、JSON/BSON 序列化）
**是否需要 Verify/Review**：是（涉及持久化，需独立 Verify）

---

### Phase 2: In-Process Executor + Progress + Retry（预计 3-4 天）

**范围**：
- InProcessExecutor 完整实现（callable 加载、参数合并、线程执行、状态转换）
- RetryManager（should_retry + compute_backoff，3 种 backoff 策略）
- ErrorStore（完整堆栈保留，截断 10000 字符）
- HeartbeatMonitor（超时检测 + stale 标记）
- ProgressTracker（百分比模式）
- 协作式取消（threading.Event + is_cancelled() 检查）
- TaskEvent 在状态转换时自动记录

**产物**：
- `skills/infra/task_center/executor/` 2 个文件
- `skills/infra/task_center/runtime/` 4 个文件
- 对应单元测试 4 个文件

**验收标准**：
- 注册 Task → 手动触发 → callable 正常执行 → status=success。
- callable 抛异常 → 自动重试（按 RetryPolicy）→ 重试成功或 failed。
- callable 超时 → HeartbeatMonitor 标记 stale。
- callable 内部调用 heartbeat() 更新 updated_at。
- callable 内部调用 is_cancelled() → 检查取消信号。
- ErrorRecord 包含完整堆栈。
- 集成测试：register → trigger → 异常 → retry → success 端到端通过。

**风险**：中（线程安全、Python 线程限制、callable 隔离）
**是否需要 Verify/Review**：是

---

### Phase 3: CLI/Python API + Manual Trigger + Status List（预计 2-3 天）

**范围**：
- CLI 完整实现（`yq task/job/exec/scheduler/errors` 5 个子命令组，表格/YAML 输出，颜色标注）
- Python API 完整公开接口（`api/` 下 5 个模块）
- ScheduleParser（cron/interval/once 解析 + next_run_at 计算）
- SchedulerLoop（主调度循环 + tick 逻辑）
- TriggerManager（手动触发、参数覆盖、dry-run）
- ConcurrencyControl（max_concurrent）
- `yq scheduler start/stop/status` 交互

**产物**：
- `skills/infra/task_center/cli.py`
- `skills/infra/task_center/scheduler/` 4 个文件
- `skills/infra/task_center/api/` 5 个文件
- `tests/infra/task_center/test_cli_smoke.py`（smoke test）

**验收标准**：
- `yq task list` 输出可读表格。
- `yq job run <job_id>` 手动触发成功。
- `yq exec show <exec_id>` 显示完整执行详情（含 Events）。
- `yq exec cancel <exec_id>` 取消 pending/running 执行。
- `yq scheduler start` 启动调度器，cron Job 在指定时间自动触发。
- `yq scheduler status` 输出运行状态。
- CLI `--json` 标志输出 JSON。

**风险**：中（CLI 输出格式、调度循环稳定性）
**是否需要 Verify/Review**：是

---

### Phase 4: unified_data Refresh Task Integration（预计 2-3 天）

**范围**：
- `integrations/unified_data.py` 适配器
- 12 个 unified_data 刷新任务的 Task 注册 + Job 创建
- 幂等 key 配置（每个任务定义 idempotency_key_template）
- 手动触发验证：通过 task_center CLI 触发 unified_data 日线刷新
- 定时调度验证：cron Job 在指定时间自动触发
- 失败重试验证：模拟 Tushare 不可用 → 重试 → AKShare fallback

**产物**：
- `skills/infra/task_center/integrations/unified_data.py`
- `tests/infra/task_center/integration/test_unified_data_tasks.py`

**验收标准**：
- `yq job run unified_data.daily_kline_cn` 手动触发成功（依赖 unified_data Phase 1 实现）。
- cron 调度在工作日 15:00 自动触发。
- 失败自动重试（数据刷新 RetryPolicy）。
- 幂等 key 防重复执行。

**风险**：中-高（依赖 unified_data Phase 1 完成、Tushare 配额）
**是否需要 Verify/Review**：是

---

### Phase 5: stock framework Task Integration（预计 2-3 天）

**范围**：
- `integrations/stock_framework.py` 适配器
- 6 个 stock framework 任务的 Task 注册 + Job 创建
- batch_scan_universe 长时间任务（3h+）的进度追踪验证
- 手动触发 + 定时调度验证

**产物**：
- `skills/infra/task_center/integrations/stock_framework.py`
- 集成测试

**验收标准**：
- stock.refresh_quant_profile 定时触发成功。
- stock.score_strategy_models 批量评分任务正常完成。
- 长时间任务进度追踪正常（百分比更新）。
- 失败重试逻辑正确。

**风险**：中（依赖 stock framework 实现）
**是否需要 Verify/Review**：是

---

### Phase 6: Optional Features（预计 3-5 天）

**范围**（这些不是必做项，按需选择）：
- SubprocessExecutor（独立进程执行）
- TaskDependency 依赖触发（DAG 编排）
- MongoDBBackend（存储后端切换）
- Step 级进度追踪（create_steps + update_step + 权重计算）
- retrying / stale / partial_success 状态补齐
- Web Dashboard（简单 HTML 看板）
- 通知回调集成（Telegram/企业微信推送）
- 任务注册自动发现（扫描模块的 tasks.py）

**产物**：按选择的子项确定。

**风险**：中-高（功能多，需分批实现）
**是否需要 Verify/Review**：按子项决定。

---

### Phase 7: TA-CN/DSA Gradual Migration Plan（预计 3-5 天文档 + 远期执行）

**范围**：
- `integrations/ta_cn_adapter.py`（TA-CN 任务包装器）
- `integrations/dsa_adapter.py`（DSA 任务包装器）
- 双写验证方案：TA-CN APScheduler 和 task_center 同时运行
- 迁移回滚方案
- 迁移风险矩阵

**产物**：
- `skills/infra/task_center/integrations/ta_cn_adapter.py`
- `skills/infra/task_center/integrations/dsa_adapter.py`
- `docs/design/10_infra/DESIGN-10-009-migration-plan.md`

**验收标准**：
- TA-CN 现有 data_sync 任务可通过 task_center adapter 包装执行。
- 双写期间两边状态一致。
- 回滚方案可操作（re-enable TA-CN APScheduler）。
- 迁移文档完整。

**风险**：高（TA-CN 生产环境变更，需充分验证）
**是否需要 Verify/Review**：是

---

### 实现阶段总览表

| Phase | 名称 | 预计时间 | 核心产物 | 风险 | Verify | Review |
|---|---|---|---|---|---|---|
| 0 | 骨架 + 核心模型 + 状态机 | 1-2 天 | entities.py, state_machine.py | 低 | 否 | 否 |
| 1 | MongoDB 存储 + CRUD + Events | 2-3 天 | mongo_backend.py, mongo_schema.py | 中 | 是 | 是 |
| 2 | In-Process 执行器 + 进度 + 重试 | 3-4 天 | in_process.py, retry.py, progress.py | 中 | 是 | 是 |
| 3 | CLI/Python API + 调度器 | 2-3 天 | cli.py, scheduler_loop.py, api/ | 中 | 是 | 是 |
| 4 | unified_data 集成 | 2-3 天 | integrations/unified_data.py | 中-高 | 是 | 是 |
| 5 | stock framework 集成 | 2-3 天 | integrations/stock_framework.py | 中 | 是 | 是 |
| 6 | 可选特性 | 3-5 天 | SQLite 降级/Subprocess/Step/Dashboard | 中-高 | 按子项 | 按子项 |
| 7 | TA-CN/DSA 迁移规划 | 3-5 天 | ta_cn_adapter.py, dsa_adapter.py | 高 | 是 | 是 |

**总计预计（Phase 0-5 核心）**：12-18 个工作日
**总计预计（含 Phase 6-7）**：18-28 个工作日

---

## 16. 测试策略

### 16.1 单元测试

| 测试文件 | 覆盖内容 | 预计用例数 | 是否需外部资源 |
|---|---|---|---|
| `test_entities.py` | 11 类实体构造、字段验证、序列化 | 22 | 否 |
| `test_state_machine.py` | 9 状态 + 12 转换 + 非法转换拒绝 | 15 | 否 |
| `test_registry.py` | register/unregister/list/get + 重复注册 | 8 | 否 |
| `test_idempotency.py` | 幂等 key 检查、重复执行跳过、不同状态处理 | 6 | 否（mock storage） |
| `test_schedule_parser.py` | cron/interval/once/manual 解析 + next_run_at | 12 | 否 |
| `test_mongo_backend.py` | 全部 CRUD 操作、分页、过滤、索引、原子 claim | 25 | 是（可用 mongomock 或测试库） |
| `test_in_process_executor.py` | callable 执行、参数合并、成功/失败/取消 | 10 | 否 |
| `test_progress_tracker.py` | 百分比更新、ProgressSnapshot 计算 | 6 | 否 |
| `test_retry_manager.py` | should_retry 判断、3 种 backoff 计算、异常匹配 | 12 | 否 |
| `test_error_store.py` | ErrorRecord 构造、堆栈截断 | 4 | 否 |
| `test_heartbeat.py` | 注册/更新/超时检测 | 5 | 否 |
| `test_scheduler_loop.py` | tick 循环、并发控制、retry 恢复 | 8 | 否（mock executor） |
| `test_cli_smoke.py` | CLI 命令输出格式、JSON 模式 | 6 | 否（mock storage） |

### 16.2 集成测试

| 测试文件 | 覆盖内容 | 阶段 |
|---|---|---|
| `test_full_register_trigger_flow.py` | 端到端：register_task → create_job → trigger → 查询 status → success | Phase 2 |
| `test_retry_and_failure.py` | 端到端：trigger → 异常 → retrying → 重试成功 / 重试耗尽 → failed | Phase 2 |
| `test_concurrency.py` | max_concurrent=1 时排队行为、max_concurrent=3 时并行行为 | Phase 3 |
| `test_idempotency_e2e.py` | 幂等 key 防重复执行（同参数两次 trigger 只执行一次） | Phase 4 |
| `test_unified_data_tasks.py` | unified_data 12 个刷新任务注册 + 手动触发集成 | Phase 4 |
| `test_stock_framework_tasks.py` | stock framework 6 个任务注册 + 手动触发集成 | Phase 5 |

### 16.3 Smoke Test

```bash
# Phase 3+ 可执行
yq task list                          # 表格输出可读
yq job create test_task --schedule "0 8 * * *"  # 创建成功
yq job run <job_id> --dry-run         # dry-run 只打印不执行
yq exec show <exec_id>                # 完整详情输出
yq scheduler start                    # 调度器启动
yq scheduler status                   # 显示运行状态
yq scheduler stop                     # 调度器停止
```

### 16.4 测试运行命令

```bash
# 快速验证（无外部依赖）
python -m pytest tests/infra/task_center/ -m "not slow and not network" -v

# 全量测试
python -m pytest tests/infra/task_center/ -v

# 仅单元测试
python -m pytest tests/infra/task_center/ --ignore=tests/infra/task_center/integration -v

# 集成测试
python -m pytest tests/infra/task_center/integration/ -v

# 带覆盖率
python -m pytest tests/infra/task_center/ --cov=skills/infra/task_center --cov-report=term
```

### 16.5 测试原则

- 默认不依赖真实外部数据源（Tushare/AKShare）；MongoDB 存储测试使用测试库或 mongomock/fixture，禁止连接生产库。
- 集成测试使用 fake unified_data callable（返回 mock 数据）。
- MongoDB 测试使用隔离数据库（如 `yquant_test`）或 mongomock；测试结束清理 `10_infra_tc_*` 集合。
- 时间相关测试（cron/backoff）使用 `freezegun` mock 时间。

---

## 17. 风险与回滚

### 17.1 风险矩阵

| 风险 | 概率 | 影响 | 应对方案 | 降级/回滚 |
|---|---|---|---|---|
| **过度抽象复杂化** | 中 | 高 | MVP 只覆盖基础功能（注册/调度/状态/简单进度/基本重试），不做 DAG/分布式/Step | 退回到直接调用函数 |
| **MongoDB 连接/索引配置失败** | 中 | 中 | 初始化时检查连接和索引；存储层 fail-fast；测试使用隔离库 | 临时切换到 SQLite 降级后端或暂停 task_center |
| **调度器进程崩溃后状态丢失** | 中 | 高 | 所有状态持久化在 MongoDB，重启后可恢复；超时未完成的 Execution 自动标记 stale | systemd/cron 守护调度器进程 |
| **与 Hermes cron 定位混淆** | 中 | 中 | §3 明确边界，附带"如何选择"决策树 | 文档交付时包含对比表 |
| **业务 callable 执行超时挂死** | 中 | 中 | HeartbeatMonitor 超时检测 + stale 标记；InProcessExecutor 用线程包装 + timeout join | 手动重试超时任务 |
| **retry storm**：短时间内大量任务同时重试 | 低 | 中 | RetryManager 使用 exponential/linear backoff 散布重试时间 | 设置 max_retries 上限 |
| **duplicate execution**：同一幂等 key 被重复执行 | 低 | 高 | IdempotencyManager 在创建 Execution 前检查 | 依赖数据库唯一索引兜底 |
| **partial success ambiguity**：部分刷新成功但无法确定哪些失败了 | 中 | 中 | Execution.warnings 记录 + ErrorRecord 按 step 记录 | 提供 retry_execution 手动重试 |
| **dashboard/API misleading status**：stale 但实际在执行 | 低 | 中 | HeartbeatMonitor 保守配置（TTL=60s） | CLI 显示 last_heartbeat 时间 |
| **accidental production scheduling**：在开发环境创建了生产级 Job | 低 | 高 | Job 创建时环境检查（dev 模式下 schedule 自动设为 manual） | 手动 disable |
| **误连生产 MongoDB 测试库** | 低 | 高 | 测试配置必须显式使用 test database；生产库写入前二次确认 | 删除测试集合并回滚配置 |
| **callable 不响应 cancel 信号** | 中 | 中 | 文档明确要求 callable 定期检查 `is_cancelled()`；Phase 2+ SubprocessExecutor 可强制 kill | 标记 stale |
| **存储集合污染/脏数据** | 低 | 中 | 所有集合使用 `10_infra_tc_*` 前缀；禁止写 TA-CN/03_data_ud 集合 | 删除 `10_infra_tc_*` 集合即可回滚 |

### 17.2 回滚策略

1. task_center 是**纯新增模块**，与 TA-CN/DSA/unified_data/stock 零耦合，可直接删除 `skills/infra/task_center/` 目录即完全回滚。
2. task_center 使用 `10_infra_tc_*` MongoDB 集合命名空间隔离，删除这些集合不影响任何现有 TA-CN / unified_data / portfolio 数据。
3. 每个 Phase 独立部署，前一个 Phase 有问题不影响后续 Phase 的独立性回滚。
4. 如果已创建的生产级 Job 需要回滚：`yq job disable <job_id>` → 删除对应 `10_infra_tc_*` 记录。

---

## 18. Open Questions / Pascal 决策点

以下问题不影响当前 Design 的完成，但需 Pascal 在后续阶段确认：

| 序号 | 问题 | 建议 | 影响阶段 |
|---|---|---|---|
| Q1 | Step 级进度是否入核心 MVP？ | 建议 Phase 6（可选），MVP 只做百分比。Step 对长任务（如批量评分 5000 只）有用但复杂度高 | Phase 2 vs Phase 6 |
| Q2 | 调度器守护方式？ | 建议 Hermes cron 每 60s `yq scheduler tick`，或 systemd 简单守护 `yq scheduler start` | Phase 3 后 |
| Q3 | 多 Job 并发策略（串行 FIFO vs 有限并发 N）？ | 建议默认 max_concurrent=1（串行 FIFO），Job 级别可配置 | Phase 2 |
| Q4 | 通知回调是否集成？ | 建议 Phase 6 可选集成现有 Telegram/企业微信通道 | Phase 6 |
| Q5 | 任务注册的自动发现机制？ | 建议 Phase 3 后支持自动扫描模块的 `tasks.py`，MVP 手动显式注册 | Phase 3+ |
| Q6 | MongoDB 数据库与连接配置？ | 建议默认复用项目 `tradingagents` 数据库，所有 task_center 集合使用 `10_infra_tc_*` 前缀；测试环境必须使用隔离库 | Phase 1 |
| Q7 | 是否需要在 MVP 支持 SubprocessExecutor？ | 建议 Phase 6，MVP 只用 InProcessExecutor。Subprocess 解决崩溃隔离但增加复杂度 | Phase 2 vs Phase 6 |
| Q8 | SQLite 是否还保留？ | 建议仅作为本地单元测试/离线降级后端，不作为生产或 MVP 主路径 | Phase 1 |

---

## 19. Design Overrides / SPEC 调整

| 序号 | 原 RFC/SPEC 描述 | Design 裁定 | 理由 |
|---|---|---|---|
| DO-1 | SPEC 使用 `Task`/`Job`/`Execution`/`Step` 命名 | 更名为 `TaskDefinition`/`JobInstance`/`TaskExecution`/`TaskStep` | 避免与 Python built-in/常见变量名冲突，更精确 |
| DO-2 | SPEC 定义 6 类实体 | Design 扩展到 11 类实体（增加 ProgressSnapshot/TaskEvent/TaskArtifact/TaskDependency/TaskSchedule） | 满足可观测性和依赖编排需求 |
| DO-3 | STEP 表用 `index` 字段名 | 改为 `step_index` | SQL 保留字冲突 |
| DO-4 | SPEC 定义 9 状态 | Design 增加到 11 状态（增加 queued/blocked），但 blocked 是 Phase 3+ | 更精确表达排队和依赖阻塞语义 |
| DO-5 | SPEC 使用 `tc_*` 前缀 | Pascal 确认改为 MongoDB 默认，统一使用 `10_infra_tc_*` 集合前缀；SQLite 仅作为本地测试/降级可选 | 与 unified_data `03_data_ud_*` 命名空间隔离 |
| DO-6 | SPEC 状态机 `failed → running` 为手动重试 | 确认：手动重试（`retry_execution`）创建新 Execution（clone params），旧 Execution 保持 failed | 更清晰的历史审计 |
| DO-7 | RFC/SPEC 未明确定义 canceled 对 running 的行为 | 裁定：MVP 为协作式取消（callable 检查 `is_cancelled()`）；不强制 kill | Python 线程限制 |
| DO-8 | SPEC 提到 `stale → running` 可手动恢复 | 确认：stale 的 Execution 可通过 `retry_execution` 创建新 Execution 恢复 | 保持历史清晰 |

---

## 20. 交接给实现者

### 必须遵守

- **绝对禁止修改 TA-CN/DSA/unified_data/stock/argus/data-pipeline/Hermes 代码。**
- 所有实体使用 `@dataclass` 定义，不绑定具体存储。
- MongoDB 集合使用 `10_infra_tc_` 前缀，JSON 字段使用 MongoDB 原生 dict/list，时间字段持久化为 ISODate。
- 所有 API 函数签名与本文档定义的接口契约一致。
- 状态转换必须通过 StateMachine 验证，不允许直接修改 status。
- 异常使用 `core/exceptions.py` 定义的异常类型。
- 定时调度器在后台线程运行，不影响主线程。
- 每个 Phase 独立可测，不要求全部 Phase 完成后才能验证。

### 可自行判断

- 函数内部实现细节（非公开 API）。
- 日志级别和文案（建议使用 Python logging，INFO 级别记录状态转换）。
- pytest fixture 设计和 mock 策略。
- CLI 输出格式的具体对齐算法。
- MongoDB client/session 管理细节（建议先单 client 复用，必要时再引入更复杂连接治理）。
- JSON/BSON 序列化/反序列化的具体实现方式。

### 遇到以下情况退回 Principal

- RFC/SPEC 定义与 Design 冲突且无法判断优先级的。
- 需要创建非 `10_infra_tc_` 前缀的 MongoDB 集合，或试图把 task_center 状态写入 TA-CN / `03_data_ud_*` 集合。
- 需要修改 TA-CN/DSA/unified_data/stock 代码才能实现集成功能的。
- 发现 SPEC 实体定义与 Design 严重不一致的。
- 性能瓶颈需要改变架构分层或接口签名的。

---

## 21. 参考资料

- `docs/rfc/10_infra/RFC-10-009-task-center.md` — 需求与架构（642 行）
- `docs/spec/10_infra/SPEC-10-009-task-center.md` — 接口契约（803 行）
- `docs/design/03_data/DESIGN-03-007-unified-data-layer.md` — Unified Data Layer 完整设计（2016 行）
- `docs/spec/03_data/SPEC-03-007-unified-data-layer.md` — Unified Data Layer 接口契约
- `docs/spec/08_research/stock/SPEC-08-001-stock-quant-analysis-framework.md` — Stock Framework 接口契约
- `skills/apps/TradingAgents-CN/app/services/scheduler_service.py` — TA-CN 调度器参考（1158 行）
- `skills/apps/TradingAgents-CN/app/services/queue_service.py` — TA-CN 队列参考
- `skills/apps/TradingAgents-CN/app/services/progress/tracker.py` — TA-CN 进度追踪参考
- `skills/infra/ai-coding-pipeline/SKILL.md` — AI Coding Pipeline 流程规范
