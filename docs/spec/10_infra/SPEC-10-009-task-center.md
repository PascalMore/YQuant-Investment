# SPEC-10-009：YQuant 通用任务中心（Task Center）

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-12 |
| 最后更新 | 2026-07-12 |
| 来源 RFC | RFC-10-009 |
| 目标模块 | task_center（通用任务中心） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |
| 关联 RFC | RFC-10-003（infra 架构）、RFC-10-004（AI Coding Pipeline）、RFC-03-007（Unified Data Layer） |

---


## 0. Design 阶段修订说明（2026-07-12）

Pascal 明确要求 task_center 使用 MongoDB，不使用 SQLite 作为 MVP / 默认 / 生产存储。因此本 SPEC 中所有持久化契约以 MongoDB 为准：

- 默认数据库建议复用项目 `tradingagents`；
- 所有 task_center 集合统一使用 `10_infra_tc_*` 前缀；
- SQLite 仅可作为本地单元测试 / 离线降级选项；
- 实现阶段不得先实现 SQLite 再迁移 MongoDB；Phase 1 即应实现 MongoDBBackend。

## 1. 需求摘要

本 SPEC 将 RFC-10-009 中描述的"通用任务中心"落到具体的实体字段定义、数据契约、状态机转换规则、接口签名和测试矩阵。核心交付物：

1. Task / Job / Execution / Step / RetryPolicy / ErrorRecord 六类实体的字段级定义与约束。
2. 状态机完整转换规则：9 种状态 + 12 条合法转换路径。
3. Python API 接口签名：register_task、create_job、trigger_job、cancel_execution 等 20+ 个公共方法。
4. CLI 命令完整定义：`yq task/job/exec/scheduler` 四个子命令组。
5. 持久化契约：MongoDB 集合结构与索引契约，集合前缀 `10_infra_tc_*`；SQLite 仅作为本地测试/离线降级选项。
6. 测试矩阵：单元测试 18 项 + 集成测试 5 项 + smoke test 3 项。

**本 SPEC 不进入 Design 级文件清单。** 具体文件结构、类图、实现细节由后续 Design 阶段产出。

---

## 2. 范围

### 2.1 In Scope

- [ ] Task 实体：定义 task_id / name / callable 路径 / retry_policy / 注册与生命周期。
- [ ] Job 实体：定义 schedule 规则、params 覆盖、enabled/paused 状态、timeout。
- [ ] Execution 实体：定义状态机字段、进度百分比、触发方式、重试计数。
- [ ] Step 实体：定义 step 级进度追踪、权重计算、错误关联。
- [ ] RetryPolicy 实体：定义 max_retries / backoff 策略 / 异常匹配。
- [ ] ErrorRecord 实体：定义错误详情、堆栈、所属 Execution 和 Step。
- [ ] 状态机：9 种状态 + 完整转换规则 + 非法转换拒绝。
- [ ] 调度器：cron / interval / once / manual 四种触发模式。
- [ ] Python API：register_task、create_job、trigger_job、cancel_execution、retry_execution 等公共接口。
- [ ] CLI 接口：`yq task list|info`、`yq job list|pause|resume|run`、`yq exec list|show|cancel|retry`、`yq scheduler start|stop|status`。
- [ ] 持久化：MongoDB 集合（`10_infra_tc_tasks` / `10_infra_tc_jobs` / `10_infra_tc_executions` / `10_infra_tc_steps` / `10_infra_tc_retry_policies` / `10_infra_tc_error_records` 等）+ 索引定义。
- [ ] 单元测试：实体构造、状态机转换、调度规则解析、API 方法行为。
- [ ] 集成测试：端到端注册→创建→触发→状态查询→重试→历史。
- [ ] Smoke test：CLI 命令输出可读性、MongoDB 隔离库集合初始化、并发触发不丢任务。

### 2.2 Out of Scope

- [ ] 不在本次产出 Design 级文件清单（类图、模块文件树、函数实现细节）。
- [ ] 不在本次实现 Redis/Celery 等分布式后端；MongoDB 是 MVP 默认持久化后端。
- [ ] 不在本次实现 Step 级进度追踪的完整 UI 展示（Phase 3）。
- [ ] 不在本次实现分布式 worker 执行模式。
- [ ] 不在本次实现 Web Dashboard。
- [ ] 不在本次修改 TA-CN / Hermes Kanban / cron / unified_data 现有代码。
- [ ] 不在本次实现任务依赖 DAG 编排。
- [ ] 不在本次实现通知回调（Telegram/企业微信推送）。
- [ ] 不在本次新增第三方 Python 依赖（MVP 仅使用 stdlib + 项目已有的依赖）。

---

## 3. 功能规格

### 3.1 Task 注册与管理

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| TSK-001 | 注册 Task | `task_id="unified_data.daily_kline_cn"`, `callable=<function>`, `module="unified_data"` | Task 对象持久化到 MongoDB `10_infra_tc_tasks` 集合 | task_id 重复抛 `TaskAlreadyExistsError`；callable 不可引用抛 `ValueError` |
| TSK-002 | 查询所有 Task | 无 | `list[Task]` | 无注册任务时返回空列表 |
| TSK-003 | 按 module 过滤 Task | `module="unified_data"` | 仅返回该模块的 Task | module 不存在时返回空列表 |
| TSK-004 | 按 tag 过滤 Task | `tags=["数据", "A股"]` | 匹配任一 tag 的 Task | tag 不存在时返回空列表 |
| TSK-005 | 注销 Task | `task_id="unified_data.daily_kline_cn"` | 移除 Task 及其所有关联 Job/Execution/Step/ErrorRecord | task_id 不存在抛 `TaskNotFoundError`；有活跃 Execution 时抛 `TaskHasActiveExecutionsError` |
| TSK-006 | task_id 命名校验 | `task_id="invalid id"` | 拒绝注册 | 只允许 `[a-z0-9_.-]`；必须以字母开头 |

### 3.2 Job 创建与生命周期

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| JOB-001 | 创建 Job | `task_id`, `schedule="0 15 * * 1-5"`, `params={}` | Job 对象持久化，调度器接收到 | task_id 不存在抛 `TaskNotFoundError`；cron 格式错误抛 `InvalidScheduleError` |
| JOB-002 | 创建仅手动触发的 Job | `schedule="manual"` | Job 创建但不加入调度循环 | 手动 Job 不会被调度器自动触发 |
| JOB-003 | 暂停 Job | `job_id` | Job 状态 → `paused` | 已是 paused 状态，操作幂等（不报错） |
| JOB-004 | 恢复 Job | `job_id` | Job 状态 → `enabled` | 已是 enabled 状态，操作幂等 |
| JOB-005 | 禁用 Job | `job_id` | Job 状态 → `disabled`，已有排队的 Execution 取消 | disabled 状态禁止任何触发（含手动） |
| JOB-006 | 更新 Job 参数 | `job_id`, `params={new_params}` | Job.params 更新，下次执行使用新参数 | 有 running Execution 时参数不覆盖当次执行 |
| JOB-007 | 更新 Job 调度规则 | `job_id`, `schedule="0 8 * * *"` | Job.schedule 更新 | 有 pending Execution 时，下一次执行使用新规则 |
| JOB-008 | 查询 Job 下的 Execution | `job_id`, `status=None`, `limit=20` | `list[Execution]` | 无 Execution 时返回空列表 |

### 3.3 调度器触发

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| SCH-001 | cron 触发 | Job.schedule=`"0 15 * * 1-5"` | 每周一至周五 15:00 创建 Execution → pending | 调度器暂停时不创建 |
| SCH-002 | interval 触发 | Job.schedule=3600 | 每隔 3600 秒创建一次 Execution | 上次执行尚未完成时行为取决于 Job.max_concurrent（默认跳过） |
| SCH-003 | once 触发 | Job.schedule=`"2026-07-15T09:00:00"` | 指定时间执行一次，执行后 Job 自动 disable | 指定时间已过抛 `InvalidScheduleError` |
| SCH-004 | manual 触发 | `trigger_job(job_id)` | 立即创建 Execution → pending → running | Job 被 disabled 时抛 `JobDisabledError` |
| SCH-005 | 手动触发时覆盖参数 | `trigger_job(job_id, params_override={...})` | Execution 使用覆盖参数执行 | 覆盖参数与 Task 默认参数合并（覆盖优先） |
| SCH-006 | 并发控制 | Job.max_concurrent=1，已有 running Execution | 新创建 Execution 保持 pending 排队 | 前一个完成后再执行下一个 |

### 3.4 执行与状态机

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| EXC-001 | pending → running | 调度器取到 pending Execution | 执行 callable | 无 |
| EXC-002 | running → success | callable 正常返回 | status=success，finished_at 记录，elapsed_seconds 计算 | result 字段写"完成" |
| EXC-003 | running → partial_success | callable 正常返回但有 warnings | status=partial_success，warnings 记录 | result 字段写警告摘要 |
| EXC-004 | running → failed（不可重试） | callable 抛不可重试异常或 retry_count >= max_retries | status=failed，error_summary 记录 | 产生 ErrorRecord |
| EXC-005 | running → retrying | callable 抛可重试异常且 retry_count < max_retries | status=retrying，等待 backoff 后自动恢复为 running | 重试前 backoff 秒数按策略计算 |
| EXC-006 | retrying → running | backoff 等待结束 | 重新执行 callable | retry_count + 1 |
| EXC-007 | running/pending → cancelled | 用户调用 cancel_execution | status=cancelled | running 中的取消依赖 callable 自身的取消检查；无内置强制 kill |
| EXC-008 | pending → cancelled | Job 被 disable，pending Execution 取消 | status=cancelled | — |
| EXC-009 | running → stale | elapsed > Job.timeout_seconds | status=stale，后台监控线程标记 | 不强制 kill 进程，仅标记状态 |
| EXC-010 | 非法状态转换 | 如 success → running | 抛 `InvalidStateTransitionError` | 只允许合法转换路径 |

### 3.5 进度追踪

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| PRG-001 | 更新进度百分比 | `execution_id`, `progress=45.5` | Execution.progress_percentage = 45.5 | 超出 0-100 范围 clamp 到边界 |
| PRG-002 | 查询进度 | `execution_id` | `{"progress": 45.5, "current_step": None, "elapsed": 120.3}` | 无进度记录时 progress=0 |
| PRG-003 | Step 进度计算 | Steps 权重分别为 [0.3, 0.5, 0.2]，前两步完成 | progress = 0.3 + 0.5 = 80% | 权重和必须等于 1.0 |
| PRG-004 | Step 状态变更 | `step_id`, `status="completed"` | Step.status 更新，Execution 进度重算 | Step 不存在抛 `StepNotFoundError` |

### 3.6 重试策略

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| RTY-001 | fixed backoff | backoff="fixed", base=30s, max_retries=3 | 每次失败后等待 30s 重试 | 3 次后标记 failed |
| RTY-002 | exponential backoff | backoff="exponential", base=10s, max=300s | 等待 10s → 20s → 40s → 80s → ...（上限 300s） | — |
| RTY-003 | linear backoff | backoff="linear", base=30s, max=300s | 等待 30s → 60s → 90s → ...（上限 300s） | — |
| RTY-004 | 按异常类型匹配 | `retry_on=["ConnectionError", "TimeoutError"]` | 仅匹配的异常触发重试 | 不匹配的异常直接标记 failed |
| RTY-005 | 排除异常类型 | `no_retry_on=["ValueError"]` | ValueError 不重试 | 其他异常走正常重试逻辑 |
| RTY-006 | max_retries=0 | 不重试 | 首次失败直接标记 failed | — |

### 3.7 执行历史与错误记录

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| HIS-001 | 查询 Execution 历史 | `job_id`, `limit=20`, `offset=0` | 最近 20 条 Execution（按 started_at 降序） | 无 Execution 时返回空列表 |
| HIS-002 | 按状态过滤 | `status="failed"` | 仅返回 failed 的 Execution | — |
| HIS-003 | 统计 Execution | `job_id` | `{total: 150, success: 130, failed: 15, cancelled: 5}` | — |
| ERR-001 | 查询错误记录 | `execution_id` | 该 Execution 的所有 ErrorRecord（按 attempt_number） | 无错误时返回空列表 |
| ERR-002 | 错误记录包含堆栈 | 异常发生 | ErrorRecord.traceback 保留完整 traceback | traceback 截断到 10000 字符 |

---

## 4. 数据与接口契约

### 4.1 Task

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

@dataclass
class Task:
    task_id: str                      # 唯一标识，只允许 [a-z0-9_.-]，以字母开头
    name: str                          # 人类可读名称
    description: str = ""              # 任务说明
    module: str = ""                   # 所属模块（unified_data / stock / report / risk / portfolio）
    callable_path: str = ""            # callable 的 Python 路径，如 "unified_data.tasks:refresh_daily_kline_cn"
    default_params: dict = field(default_factory=dict)
    retry_policy_id: str = "default"   # 关联的 RetryPolicy.policy_id
    tags: list[str] = field(default_factory=list)
    created_at: str = ""               # ISO 8601
    updated_at: str = ""               # ISO 8601
```

### 4.2 Job

```python
from dataclasses import dataclass, field
from typing import Literal, Optional

JobStatus = Literal["enabled", "paused", "disabled"]

@dataclass
class Job:
    job_id: str                        # UUID
    task_id: str                       # FK → Task.task_id
    schedule: str                      # cron 表达式 / interval 秒数(int) / "once:ISO_DATETIME" / "manual"
    schedule_type: str = ""            # 由 schedule 解析得出："cron" / "interval" / "once" / "manual"
    params: dict = field(default_factory=dict)  # 覆盖 Task.default_params
    enabled: bool = True               # 等价于 status != "disabled"；paused 时 enabled=True
    status: JobStatus = "enabled"
    max_concurrent: int = 1            # 允许同时运行的 Execution 数
    timeout_seconds: int = 3600        # 单次执行超时（0 表示无超时）
    retry_policy_id: str | None = None # 覆盖 Task 级别 retry_policy
    priority: int = 0                  # 排队优先级（越小越优先）
    created_at: str = ""
    updated_at: str = ""
```

### 4.3 Execution

```python
from dataclasses import dataclass, field
from typing import Literal, Optional

ExecutionStatus = Literal[
    "pending", "running", "success", "partial_success",
    "failed", "retrying", "paused", "cancelled", "stale"
]
TriggerType = Literal["scheduled", "manual"]

@dataclass
class Execution:
    execution_id: str                  # UUID
    job_id: str                        # FK → Job.job_id
    status: ExecutionStatus = "pending"
    trigger: TriggerType = "scheduled"
    params: dict = field(default_factory=dict)  # 本次执行的参数快照
    started_at: str | None = None      # ISO 8601
    finished_at: str | None = None
    elapsed_seconds: float = 0.0
    progress_percentage: float = 0.0   # 0-100
    current_step_index: int = 0
    result: str = ""                   # success 时为"完成"，failed 时为失败原因
    retry_count: int = 0
    error_summary: str = ""            # 最后一次失败的人类可读摘要
    warnings: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
```

### 4.4 Step

```python
from dataclasses import dataclass, field
from typing import Literal, Optional

StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]

@dataclass
class Step:
    step_id: str                       # UUID
    execution_id: str                  # FK → Execution.execution_id
    name: str                          # 步骤名称
    description: str = ""
    index: int = 0                     # 步骤序号（从 0 开始）
    weight: float = 0.0               # 权重（所有 Step 权重和应为 1.0）
    status: StepStatus = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str = ""
    data: dict = field(default_factory=dict)  # 可选结构化数据
```

### 4.5 RetryPolicy

```python
from dataclasses import dataclass, field
from typing import Literal

BackoffStrategy = Literal["fixed", "exponential", "linear"]

@dataclass
class RetryPolicy:
    policy_id: str                     # 如 "default"、"aggressive"、"no_retry"
    max_retries: int = 3
    backoff: BackoffStrategy = "fixed"
    backoff_base_seconds: int = 30
    backoff_max_seconds: int = 300
    retry_on_exception_types: list[str] = field(default_factory=list)   # 空的 = 所有异常重试
    no_retry_on_exception_types: list[str] = field(default_factory=list)
```

### 4.6 ErrorRecord

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ErrorRecord:
    error_id: str                      # UUID
    execution_id: str                  # FK → Execution.execution_id
    step_id: str | None = None         # FK → Step.step_id（可选）
    attempt_number: int = 1
    error_type: str = ""               # 异常类名，如 "ConnectionError"
    error_message: str = ""
    traceback: str = ""                # 完整堆栈
    created_at: str = ""
```

### 4.7 状态机转换规则

```python
# 合法转换表
VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending":       {"running", "cancelled"},
    "running":       {"success", "partial_success", "failed", "retrying", "paused", "cancelled", "stale"},
    "success":       set(),  # 终态
    "partial_success": set(),  # 终态
    "failed":        {"running"},      # 手动重试 → 重新 running
    "retrying":      {"running", "failed", "cancelled"},
    "paused":        {"running", "cancelled"},
    "cancelled":     set(),  # 终态
    "stale":         {"running"},      # 手动恢复
}

# 非法转换示例
# "success" → "running": InvalidStateTransitionError
# "cancelled" → "pending": InvalidStateTransitionError
```

### 4.8 Python API 接口签名

```python
# -------------------------------------------------------------------------
# skills/infra/task_center/api.py（伪代码，具体路径由 Design 决定）
# -------------------------------------------------------------------------

from typing import Optional, Callable

# --- Task 管理 ---

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
) -> Task: ...

def unregister_task(task_id: str) -> None: ...

def get_task(task_id: str) -> Task: ...

def list_tasks(
    module: str | None = None,
    tags: list[str] | None = None,
) -> list[Task]: ...

# --- Job 管理 ---

def create_job(
    task_id: str,
    schedule: str,                    # cron / interval(秒) / "once:ISO" / "manual"
    *,
    params: dict | None = None,
    max_concurrent: int = 1,
    timeout_seconds: int = 3600,
    retry_policy_id: str | None = None,
    priority: int = 0,
) -> Job: ...

def get_job(job_id: str) -> Job: ...

def list_jobs(
    task_id: str | None = None,
    status: str | None = None,
) -> list[Job]: ...

def pause_job(job_id: str) -> None: ...
def resume_job(job_id: str) -> None: ...
def disable_job(job_id: str) -> None: ...
def enable_job(job_id: str) -> None: ...

# --- 手动触发 ---

def trigger_job(
    job_id: str,
    *,
    params_override: dict | None = None,
) -> Execution: ...

# --- 执行控制 ---

def get_execution(execution_id: str) -> Execution: ...

def list_executions(
    job_id: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Execution]: ...

def count_executions(
    job_id: str | None = None,
    status: str | None = None,
) -> dict[str, int]: ...             # {total, success, failed, ...}

def cancel_execution(execution_id: str) -> None: ...
def retry_execution(execution_id: str) -> Execution: ...

# --- 进度 ---

def get_progress(execution_id: str) -> dict: ...
    # returns {"progress_percentage": float, "current_step_name": str|None,
    #          "elapsed_seconds": float, "estimated_remaining": float|None}

def update_progress(execution_id: str, progress: float) -> None: ...

def create_steps(
    execution_id: str,
    steps: list[dict],                # [{name, description, weight}, ...]
) -> list[Step]: ...

def update_step(step_id: str, *, status: str | None = None, data: dict | None = None) -> Step: ...

# --- 调度器生命周期 ---

def start_scheduler(blocking: bool = False) -> None: ...
def stop_scheduler() -> None: ...
def get_scheduler_status() -> dict: ...  # {running: bool, active_jobs: int, queue_size: int}

# --- 错误查询 ---

def get_errors(execution_id: str) -> list[ErrorRecord]: ...

# --- 重试策略管理 ---

def register_retry_policy(policy: RetryPolicy) -> RetryPolicy: ...
def get_retry_policy(policy_id: str) -> RetryPolicy: ...
```

### 4.9 CLI 命令契约

```text
yq task
  yq task list                [--module <m>] [--tags <t1,t2>]
  yq task info                <task_id>

yq job
  yq job list                 [--task <task_id>] [--status <s>]
  yq job show                 <job_id>
  yq job create               <task_id> --schedule <s> [--params <json>]
  yq job pause                <job_id>
  yq job resume               <job_id>
  yq job disable              <job_id>
  yq job enable               <job_id>
  yq job run                  <job_id> [--params <json>]   # 手动触发

yq exec
  yq exec list                [--job <job_id>] [--status <s>] [--limit <n>]
  yq exec show                <execution_id>
  yq exec cancel              <execution_id>
  yq exec retry               <execution_id>
  yq exec progress            <execution_id>

yq errors
  yq errors list              <execution_id>

yq scheduler
  yq scheduler start          [--blocking]
  yq scheduler stop
  yq scheduler status
```

**CLI 输出格式约定**：

- 所有 list 命令以表格形式输出（`tabulate` 或手动对齐）
- `show` / `info` 命令以 YAML 或分节格式输出
- 状态字段带颜色标注（如 running=绿色、failed=红色、retrying=黄色）
- 错误命令输出 `--json` 标志时转为 JSON 输出

---

## 5. 持久化契约

### 5.1 存储接口抽象

task_center 的存储后端通过 `StorageBackend` 抽象定义，MVP 实现 MongoDB 后端；SQLite 仅作为本地测试/离线降级选项：

```python
from abc import ABC, abstractmethod

class StorageBackend(ABC):
    # Task CRUD
    @abstractmethod def save_task(self, task: Task) -> None: ...
    @abstractmethod def get_task(self, task_id: str) -> Task | None: ...
    @abstractmethod def delete_task(self, task_id: str) -> None: ...
    @abstractmethod def list_tasks(self, module: str | None, tags: list[str] | None) -> list[Task]: ...

    # Job CRUD
    @abstractmethod def save_job(self, job: Job) -> None: ...
    @abstractmethod def get_job(self, job_id: str) -> Job | None: ...
    @abstractmethod def list_jobs(self, task_id: str | None, status: str | None) -> list[Job]: ...

    # Execution CRUD
    @abstractmethod def save_execution(self, exec: Execution) -> None: ...
    @abstractmethod def get_execution(self, execution_id: str) -> Execution | None: ...
    @abstractmethod def list_executions(self, job_id: str | None, status: str | None,
                                        limit: int, offset: int) -> list[Execution]: ...
    @abstractmethod def count_executions(self, job_id: str | None, status: str | None) -> dict[str, int]: ...

    # Step CRUD
    @abstractmethod def save_step(self, step: Step) -> None: ...
    @abstractmethod def get_steps(self, execution_id: str) -> list[Step]: ...

    # Error CRUD
    @abstractmethod def save_error(self, error: ErrorRecord) -> None: ...
    @abstractmethod def get_errors(self, execution_id: str) -> list[ErrorRecord]: ...

    # RetryPolicy CRUD
    @abstractmethod def save_retry_policy(self, policy: RetryPolicy) -> None: ...
    @abstractmethod def get_retry_policy(self, policy_id: str) -> RetryPolicy | None: ...
```

### 5.2 MongoDB 集合结构（MVP）

```javascript
// MVP MongoDB collections, database configurable, default: tradingagents
// prefix: 10_infra_tc_

10_infra_tc_tasks            // Task definitions
10_infra_tc_jobs             // Job schedule/config instances
10_infra_tc_executions       // Execution records and status
10_infra_tc_steps            // Optional step progress
10_infra_tc_retry_policies   // Retry policies
10_infra_tc_error_records    // Error records and tracebacks
10_infra_tc_events           // State transition / lifecycle events
10_infra_tc_artifacts        // Execution artifacts
10_infra_tc_dependencies     // Task dependencies
10_infra_tc_schedules        // Parsed schedules and next_run_at

// Required indexes include status, task_id/job_id, next_run_at, created_at,
// and a partial unique index on idempotency_key when present.
```

### 5.3 MongoDB 主路径与 SQLite 降级边界

MongoDB 是 MVP / 默认 / 生产持久化主路径；SQLite 仅用于本地单元测试或离线降级，不作为 MVP / 默认 / 生产存储。实现时不得要求先落 SQLite 再迁移 MongoDB。MongoDB 存储规则：

- `task_id`、`job_id`、`execution_id` 作为 `_id`
- JSON 字段（`default_params`、`params`、`tags`、`warnings`）在 MongoDB 中存储为原生 dict/list
- `created_at`、`updated_at`、`started_at`、`finished_at` 存储为 ISODate
- 集合命名：`10_infra_tc_tasks`、`10_infra_tc_jobs`、`10_infra_tc_executions`、`10_infra_tc_steps`、`10_infra_tc_retry_policies`、`10_infra_tc_error_records`

---

## 6. 错误码与异常

| 异常 | 含义 | 触发场景 |
|---|---|---|
| `TaskAlreadyExistsError` | task_id 重复 | register_task 时 task_id 已存在 |
| `TaskNotFoundError` | Task 不存在 | get_task / unregister_task 时 task_id 不存在 |
| `TaskHasActiveExecutionsError` | 有活跃执行 | unregister_task 时存在非终态 Execution |
| `InvalidScheduleError` | 调度规则格式错误 | 创建 Job 时 cron 格式不合法 / once 日期已过 |
| `JobNotFoundError` | Job 不存在 | get_job / trigger_job 时 job_id 不存在 |
| `JobDisabledError` | Job 已禁用 | trigger_job 时 Job.status = "disabled" |
| `ExecutionNotFoundError` | Execution 不存在 | get_execution 时 execution_id 不存在 |
| `InvalidStateTransitionError` | 非法状态转换 | 执行状态转换不在 VALID_TRANSITIONS 中 |
| `StepNotFoundError` | Step 不存在 | update_step 时 step_id 不存在 |
| `StorageError` | 存储后端异常 | MongoDB 连接失败 / 写入失败 / 索引缺失 / 原子 claim 失败 |
| `SchedulerAlreadyRunningError` | 调度器已在运行 | start_scheduler 时调度器已启动 |

---

## 7. 不改动清单（Out of Scope — 禁止修改）

| 路径 | 理由 |
|---|---|
| `skills/apps/TradingAgents-CN/**` | TA-CN 是子项目，本阶段只定义边界 |
| `skills/data/unified_data/**` | 独立 RFC/SPEC 线，task_center 只定义接口边界 |
| `skills/research/stock/**` | 独立 RFC/SPEC 线，消费方不在此阶段修改 |
| `scripts/*.sh`、`scripts/*.py` | 现有 cron 脚本不在此阶段替换 |
| 系统 cron/systemd 配置 | 守护方式在 Design 阶段再定义 |
| 生产 TA-CN / unified_data / portfolio 集合 | 仅允许写 `10_infra_tc_*` task_center 集合，不碰现有业务集合 |
| Hermes Kanban / cron / gateway 配置 | 不在此范围 |

---

## 8. 测试矩阵

### 8.1 单元测试

| 测试编号 | 测试目标 | 覆盖功能 |
|---|---|---|
| UT-001 | Task 构造与字段校验 | TSK-001, TSK-006 |
| UT-002 | task_id 命名规则拒绝非法字符 | TSK-006 |
| UT-003 | Job 构造与 schedule 三种格式解析 | JOB-001, JOB-002 |
| UT-004 | Execution 构造与默认值 | — |
| UT-005 | 状态机合法转换全部路径 | EXC-001 ~ EXC-010 |
| UT-006 | 状态机拒绝非法转换 | EXC-010 |
| UT-007 | RetryPolicy fixed backoff 计算 | RTY-001 |
| UT-008 | RetryPolicy exponential backoff 计算 | RTY-002 |
| UT-009 | RetryPolicy 异常类型匹配 | RTY-004, RTY-005 |
| UT-010 | Step 权重进度计算 | PRG-003 |
| UT-011 | ErrorRecord 构造与字段 | ERR-002 |
| UT-012 | register_task / unregister_task | TSK-001, TSK-005 |
| UT-013 | create_job / pause_job / resume_job / disable_job | JOB-001, JOB-003 ~ JOB-006 |
| UT-014 | trigger_job 手动触发 | SCH-004, SCH-005 |
| UT-015 | cancel_execution 取消 | EXC-007 |
| UT-016 | retry_execution 重试 | — |
| UT-017 | list_executions 查询与分页 | HIS-001, HIS-002 |
| UT-018 | count_executions 统计 | HIS-003 |

### 8.2 集成测试

| 测试编号 | 测试目标 |
|---|---|
| IT-001 | 端到端：register_task → create_job → trigger_job → 查询 status → success |
| IT-002 | 端到端：trigger_job 参数覆盖 → 验证 Execution 使用覆盖参数 |
| IT-003 | 端到端：callable 抛异常 → retrying → 重试成功 → success |
| IT-004 | 端到端：callable 抛异常 → 重试耗尽 → failed + ErrorRecord |
| IT-005 | 状态查询：running 中 update_progress → get_progress 返回正确值 |

### 8.3 Smoke Test

| 测试编号 | 测试目标 |
|---|---|
| SM-001 | `yq task list` 输出可读的表格 |
| SM-002 | `yq exec show <id>` 输出完整执行详情 |
| SM-003 | MongoDB 隔离库中 `10_infra_tc_*` 集合与索引在首次初始化后可见 |

---

## 9. 向后兼容

- 本 SPEC 新建 `skills/infra/task_center/`，不修改任何现有代码，**无破坏性变更**。
- MongoDB 集合使用 `10_infra_tc_*` 前缀并与既有业务集合隔离；SQLite 仅作为本地测试/离线降级选项。
- 现有 TA-CN / unified_data / stock / 系统 cron 不受影响。
- task_center 是**纯新增模块**，不与现有任何模块冲突。

---

## 10. MVP 范围与分阶段 Roadmap

### 10.1 MVP（RFC/SPEC 批准后第一步实现）

- Task 注册 + Job 创建 + 定时调度（cron + interval）+ 手动触发
- 状态机（pending/running/success/failed/cancelled）
- 简单进度（百分比，非 Step 级）
- 重试（max_retries + fixed backoff）
- 执行历史（查询/分页/统计）
- 暂停/恢复/取消
- MongoDB 持久化（`10_infra_tc_*` 集合）
- Python API 核心方法 + CLI 基本命令
- 单元测试 + 集成测试 + smoke test

### 10.2 Phase 2

- Step 级进度追踪（完整 create_steps + update_step）
- retrying / stale / partial_success 三状态补齐
- 多个 Job 并发执行（max_concurrent > 1）
- CLI `yq errors list` 和 `yq exec progress` 完整实现

### 10.3 Phase 3

- 业务接入：unified_data / stock / report / risk 注册第一批任务
- 任务注册自动发现（扫描模块的 tasks.py）
- CLI 输出增强（颜色、进度条、JSON 输出模式）

### 10.4 Phase 4（远期）

- SQLite 离线降级完善
- TA-CN data_sync 任务迁移
- Web Dashboard（独立或嵌入式）
- 通知回调集成

---

## 11. 验收标准

- [ ] SPEC 文件存在于 `docs/spec/10_infra/SPEC-10-009-*.md`，明确可执行、可测试的工程契约
- [ ] SPEC 不进入 Design 级文件清单（无类图、无模块文件树、无函数实现细节）
- [ ] 六类实体（Task/Job/Execution/Step/RetryPolicy/ErrorRecord）字段定义完整
- [ ] 状态机 9 状态 + 转换规则完整
- [ ] Python API 接口签名覆盖所有 Must-Have 功能
- [ ] CLI 命令契约覆盖所有操作入口
- [ ] 持久化契约（MongoDB 集合结构 + 索引 + SQLite 本地降级边界）
- [ ] 测试矩阵覆盖单元/集成/smoke 三个层次
- [ ] 不改动清单明确
- [ ] 中文输出，专业简洁

---

## 12. 后续 Design 拆分建议

| Design 子阶段 | 建议内容 |
|---|---|
| Design-A | 六类实体的 dataclass 定义 + 状态机实现 + StorageBackend 抽象 + MongoDBBackend 完整设计 |
| Design-B | 调度器设计：ScheduleParser + Scheduler 轮询循环 + 并发控制 + 超时管理 |
| Design-C | CLI 完整实现设计 + Python API 公开接口设计 |
| Design-D | SQLite 本地降级设计 + MongoDB Schema 兼容性 |

可合并为一份 Design 文档，也可按子阶段拆分。

---

## 13. 开放问题

（继承自 RFC §14，Design 阶段决策）

1. Step 级进度是否入 MVP？
2. 调度器守护方式（systemd / Hermes cron / 其他）？
3. 多 Job 并发策略（串行 FIFO vs 有限并发 N）？
4. 通知回调是否集成现有通道？
5. 任务注册的自动发现机制？

---

## 14. 参考资料

- RFC-10-009：`docs/rfc/10_infra/RFC-10-009-task-center.md`
- RFC-10-003：Infra 架构
- RFC-10-004：AI Coding Pipeline skill sync
- RFC-03-007：Unified Data Layer
- SPEC-03-007：Unified Data Layer 可执行契约
- TA-CN 调度器：`skills/apps/TradingAgents-CN/app/services/scheduler_service.py`
- TA-CN 队列：`skills/apps/TradingAgents-CN/app/services/queue_service.py`
- TA-CN 进度：`skills/apps/TradingAgents-CN/app/services/progress/tracker.py`
- Pipeline skill：`skills/infra/ai-coding-pipeline/SKILL.md`
