# Hermes Kanban 编排规则

AI Coding Pipeline 在 Hermes 中使用 Kanban profile worker，而不是 OpenClaw `agentId` 或 Hermes `delegate_task`。

## 配置来源

AI Coding Pipeline 的源目录是：

```text
/home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/
```

Hermes profile 下不得保留本技能副本。`yquant` 和各 worker 通过 YQuant 项目 external skills 目录加载；`yinglong` 的 `skills.external_dirs` 直接引用上述 canonical skill 目录。修改流水线规则时只改这一份源文件。

例外：模型、fallback、toolsets、credential pool 等 profile 运行参数仍以 `~/.hermes/profiles/<profile>/config.yaml` 为准。

历史遗留的 `~/.hermes/profiles/yquant/skills/infra/yquant-delegation-mechanics/` 是迁移排查期间创建的运行态记录，不是项目 source of truth。其有效结论已经合并到本 skill；不要再把该目录作为新的长期规则来源。

## 为什么不用 delegate_task

`delegate_task` 会创建当前 profile 下的临时子 agent：

- 子 agent 默认继承父 profile 的模型、fallback、工具面。
- 单次调用不能指定 `profile=yquantprincipal`。
- prompt 中写“你是 yquantprincipal”只是语义提示，不会切换 profile。
- 适合短推理和并行阅读，不适合 RFC/SPEC、Design、Implement、Validate 这种正式角色化流水线。

## 项目上下文

创建第一个任务前由 orchestrator 固定 `PIPELINE_WORKSPACE`：

- `yquant` → `/home/pascal/workspace/yquant-investment`
- `yinglong` → `/home/pascal/workspace/yq-yinglong`

后续所有任务必须复用同一绝对路径。Worker 使用任务传入的 workspace，不能根据
`yquantprincipal` 等 worker profile 名反推项目。

## 正式委派方式

Orchestrator 必须通过 `kanban_create` 创建任务：

```python
kanban_create(
    title="RFC/SPEC: <short task name>",
    assignee="yquantprincipal",
    body="<完整任务上下文、交付物、验收标准>",
    max_runtime_seconds=3600,
    workspace_kind="dir",
    workspace_path=PIPELINE_WORKSPACE,
    skills=["yquant-ai-coding-pipeline"],
)
```

如果任务有前置阶段，创建时设置 `parents`：

```python
design = kanban_create(
    title="Design: <short task name>",
    assignee="yquantprincipal",
    body="<基于 RFC/SPEC 输出 DESIGN>",
    max_runtime_seconds=3600,
    parents=[spec_task_id],
    workspace_kind="dir",
    workspace_path=PIPELINE_WORKSPACE,
    skills=["yquant-ai-coding-pipeline"],
)
```

## 标准任务图

完整流程：

```text
T1 RFC/SPEC  -> yquantprincipal
T2 Design    -> yquantprincipal, parents=[T1]
T3 Implement -> yquantdeveloper, parents=[T2]
T4 Validate  -> yquantreviewer, parents=[T3]
```

轻量流程：

```text
T1 Implement -> yquantdeveloper
T2 Validate  -> yquantreviewer, parents=[T1]
```

Intake / Closeout 由主控承担，不另建默认 worker。后续新任务只用 Full / Light：Quick 已退役，原 Quick 请求按契约是否已明确、风险是否可控分流，不按文件数。Full 保留 RFC/SPEC 与 Design 两阶段、三份独立文件；旧任务继续原契约，不自动迁移。

### 真实依赖与创建参数

- 在同一 Intake 内按依赖顺序调用工具：先创建上游、读取返回真实 `task_id`，再创建下游并传该真实 id。创建后 `kanban_show` 读回 exact task 的 parents；禁止占位 parent、幽灵 parent、未定义 id 或靠 worker 自我 block 修链。
- T1/T2 是上图符号，不是可直接传入的 id。不要等待上游执行 done 才创建后续任务；预建下游由 dispatcher 随真实依赖自动推进。
- RFC/SPEC、Design：60m/1；Implement：75m/1；Validate（`yquantreviewer`）：60m/1。tester 45m/1 只用于旧任务/必要专项，不是默认阶段。参数是任务预算，不修改运行 profile 配置。
- `kanban_create` 的墙钟参数使用当前工具 schema 的 `max_runtime_seconds`（60m 对应 3600，75m 对应 4500）；重试上限按实际支持的创建接口设置。若当前工具不暴露该参数，写明需主控核实实际值，不得谎称 body 文本已配置调度器。
- 卡面授权与 runtime 许可须同时满足；拒绝后停止相关动作，不换工具/路径重放。环境或必要授权不足时明确 block，不自行启动 gateway。
- Kanban 是唯一状态源；不强制 state/body 镜像或全文 handoff；小任务 Kanban 结论＋必要日志，复杂任务一份验收报告＋原始证据。

## 任务正文模板

通用模板：

```text
阶段：<RFC/SPEC | Design | Implement | Validate>
模式：<Full | Light>；旧任务按原契约，不自动迁移
预算：<实际 max-runtime / max-retries；若接口未暴露，说明待核实项>
项目：<绝对 workspace；禁止跨项目>
用户目标：<原始目标摘要>
当前上下文：<已确认范围、非目标、风险>
相关路径：
- <path>

输入材料：
- <RFC/SPEC/DESIGN/task id/comment 摘要>

允许修改：
- <paths or none>

禁止事项：
- 不扩大范围
- 不读取或输出密钥
- 不改无关文件

交付物：
- <文件、diff、必要日志或验收结论；不强制重复 handoff/report>

验收标准：
- <可验证条目>
- Validate 按统一规则独立测试＋消费者/反例审查＋裁定；记录候选身份、命令/exit、覆盖和未验证项，未测不得称 PASS
- 实现自测不替代 Validate；既有独立证据适用时复用，不因整理日志/报告重复跑，主控不第三遍全量跑

输出要求：
- 使用中文
- 满足本阶段验收且有预建下游：kanban_complete(summary=..., metadata=...)
- 仅需同卡 review：kanban_request_review；不与已有下游重复
- 真实缺验收/环境/必要授权：kanban_block(reason=..., kind=...)
- 不因存在下游 block，不定时盲目 unblock
- 预算中断先核对已落盘产物/证据；只缺登记则补登记，不重跑或补写 PASS
```

统一 Validate 的完整规则见 [SKILL](../SKILL.md)，Full/Light 使用同一份。

## 历史：Quick Flow 任务模板（全节退役）

<details>
<summary>仅保留旧示例，不是新任务创建入口</summary>

以下至 details 结束的四卡/Q-LINK、占位、先建下游、`.id` 返回值和调用时机断言均为历史，不作为当前 API 保证或操作指令；现行只用上方真实依赖规则。

历史 Quick Flow 曾要求额外的衔接机制声明：

```text
衔接机制声明：
- 流程模式：Quick Flow（5 阶段 4 task）
- 本 task 在 Intake 阶段一次性预创建，[ready|todo]，parents=[...]
- 后续衔接由 Kanban DB 状态机（task_links + recompute_ready + dispatch_once）自动完成
- 禁止依赖 orchestrator 在前序任务 done 后临时创建本 task
- 预创建关联 task id：
  - T1 = <task_id>
  - T2 = <task_id>
  - T3 = <task_id>
  - T4 = <task_id>
```

T1 body 必须显式列出 T2/T3/T4 task id；T2/T3/T4 body 必须显式声明自己是 Intake 预创建 task 并指向 T1 文档路径。

### Quick Flow Intake 一次性创建示例

> ⚠️ **常见错误**：下面第 1 版草稿曾在 T1 body 里引用 `t2_id/t3_id/t4_id`、在 T2 body 里引用 `t1_id`——变量未定义就引用，会在 Python 运行时炸出 `NameError`，或更阴险地在动态拼接时产生 NaN/空字符串。正确策略是**两阶段创建**：(a) 创建 T1 占位 + T2/T3/T4 一次性预创建，(b) 用 `kanban_comment` 把 T2/T3/T4 id 回填到 T1 的可见处。

```python
# Intake 阶段一次性预创建 4 张 task (5 阶段 4 task 全链)
PIPELINE_WORKSPACE = "/home/pascal/workspace/yquant-investment"

# === Phase 1: 创建 T1 占位（不知道下游 id，先用占位字符串）===
PLACEHOLDER = "<filled in phase 2 after T2/T3/T4 created>"

t1 = kanban_create(
    title="T1 RFC/SPEC/Design: <short task name>",
    assignee="yquantprincipal",
    body=(
        "## 流程模式\n本任务走 Quick Flow（5 阶段 4 task）。\n\n"
        "## 衔接机制声明\n"
        f"- T2 task id: {PLACEHOLDER}\n"
        f"- T3 task id: {PLACEHOLDER}\n"
        f"- T4 task id: {PLACEHOLDER}\n"
        "- 本 task 完成后由 dispatcher 自动 promote T2。\n\n"
        "## 用户目标 / 范围 / 交付物 / 验收标准（同通用模板）"
    ),
    workspace_kind="dir",
    workspace_path=PIPELINE_WORKSPACE,
)
t1_id = t1.id  # 保存本任务的 id（Python 内变量，供 Kanban 内部使用）

# === Phase 2: 一次性预创建 T2/T3/T4，引用 t1_id 作为 parent ===
t2_id = kanban_create(
    title="T2 Implement: <short task name>",
    assignee="yquantdeveloper",
    body=(
        "## 流程模式\nQuick Flow T2 Implement。\n\n"
        "## 衔接机制声明\n"
        "- 本 task 在 Intake 阶段预创建，parents=[T1]\n"
        "- 由 T1 done 后 Kanban DB 状态机自动 promote\n"
        "- 禁止依赖 orchestrator 在 T1 done 后临时创建本 task\n\n"
        "## 来源文档 / 允许修改 / 禁止事项 / 验收标准（同通用模板）"
    ),
    parents=[t1_id],
    workspace_kind="dir",
    workspace_path=PIPELINE_WORKSPACE,
).id

t3_id = kanban_create(
    title="T3 Verify: <short task name>",
    assignee="yquanttester",
    body=(
        "## 流程模式\nQuick Flow T3 Verify。\n\n"
        "## 衔接机制声明\n"
        "- 本 task 在 Intake 阶段预创建，parents=[T1, T2]\n"
        "- 由 T2 done 后 Kanban DB 状态机自动 promote\n"
        "- 禁止依赖 orchestrator 在 T1/T2 done 后临时创建本 task\n\n"
    ),
    parents=[t1_id, t2_id],
    workspace_kind="dir",
    workspace_path=PIPELINE_WORKSPACE,
).id

t4_id = kanban_create(
    title="T4 Closeout: <short task name>",
    assignee="<orchestrator>",
    body=(
        "## 流程模式\nQuick Flow T4 Closeout。\n\n"
        "## 衔接机制声明\n"
        "- 本 task 在 Intake 阶段预创建，parents=[T1, T2, T3]\n"
        "- 由 T3 done 后 Kanban DB 状态机自动 promote\n"
        "- 执行 DESIGN-10-004 §3.5 15 项自审清单\n\n"
    ),
    parents=[t1_id, t2_id, t3_id],
    workspace_kind="dir",
    workspace_path=PIPELINE_WORKSPACE,
).id

# === Phase 3: 回填 T1 的衔接机制声明（task body 是 readonly，所以用 comment 通道）===
kanban_comment(
    task_id=t1_id,
    body=(
        f"## Intake 回填：4 task 全链创建完成\n\n"
        f"- T1 (RFC/SPEC/Design): {t1_id}\n"
        f"- T2 (Implement): {t2_id}\n"
        f"- T3 (Verify): {t3_id}\n"
        f"- T4 (Closeout): {t4_id}\n\n"
        f"T1 body 的占位字符串将由 Reviewer/Verify 阶段从本 comment 读取。"
    ),
)
```

**关键差异**：

- ❌ 错误：直接 `f"- T2 task id: {t2_id}"` 在 `t1` 创建之前 → 变量未定义，运行时炸
- ✅ 正确：先创建 T1 占位（body 写 `PLACEHOLDER`），再创建 T2/T3/T4，最后用 `kanban_comment` 通道回填 id

**Q-LINK-001~006 一致性保证**：

- Q-LINK-001 (4 tasks 一次性预创建)：phase 1+2 是同一个 `kanban_create` 调用的相邻语句，没有任何"等 X done 后再 create Y"的间隙。
- Q-LINK-003 (T2/T3/T4 todo + parents)：phase 2 创建时 parent 已存在（`t1_id` 等 Python 内变量），parent links 在 DB 端就是合法的。
- Q-LINK-005 (no late_create)：4 个 task 的 `created_at` 都由一次性调用产生，**不会**发生在前序 done 之后才创建的 late_create。
- 不会"重复创建 T1"——因为 phase 1 只调一次 `kanban_create` 赋给 `t1` + `t1_id`，phase 2 用 `t1_id` 作为 parent（不会再调 `kanban_create`）。

**API 调用约定**：Hermes Kanban 工具/示例一致返回带 `"task_id"` 键的 dict，所以读 id 用：

```python
t1_id = t1["task_id"]                  # 已创建的 task 对象
t2_id = kanban_create(...).id          # 短路访问 .id（项目内封装）
t2_id = kanban_create(...)["task_id"]  # 或显式 key
```

**两种写法等价**——按项目内既有封装偏好任选其一；不要再写"phase 4 最后再调一次创建 T1"之类的反模式。

> **关键约束**：四个 `kanban_create` 必须在同一个 Intake 动作内完成（允许的例外：先创建 T2/T3/T4 拿到 id，再创建 T1 并把 id 填进 body）。T2/T3/T4 通过 `parents` 保持 `todo` 状态，由 dispatcher 自动 promote。任何在前序 done 后才创建下一张 task 的行为都是 V1.2 Q-LINK-005 禁止的。

</details>

## 运行态要求

- 当前 orchestrator（`yquant` 或 `yinglong`）必须启用 `kanban` toolset。
- Hermes gateway 必须运行，dispatcher 才会自动 pick up ready task。
- 目标 profile 必须存在于 `~/.hermes/profiles/`。
- 被分派的 worker 会自动加载 `kanban-worker`；本 pipeline skill 始终从 canonical source 加载，不安装 profile 副本。

## 验证方式

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect('/home/pascal/.hermes/kanban.db')
for row in conn.execute(
    "select id,title,assignee,status from tasks order by created_at desc limit 10"
):
    print(row)
PY
```

如果没有 task 记录，说明没有发生真实委派。
