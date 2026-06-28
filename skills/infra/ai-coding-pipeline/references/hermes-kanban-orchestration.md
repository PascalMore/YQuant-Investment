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
- 适合短推理和并行阅读，不适合 RFC/SPEC/Design/Implement/Verify/Review 这种角色化流水线。

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
T4 Verify    -> yquanttester, parents=[T3]
T5 Review    -> yquantreviewer, parents=[T4]
```

轻量流程：

```text
T1 Implement -> yquantdeveloper
T2 Verify    -> yquanttester, parents=[T1]
```

## 任务正文模板

```text
阶段：<RFC/SPEC | Design | Implement | Verify | Review>
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
- <文件、diff、测试报告或 review 结论>

验收标准：
- <可验证条目>

输出要求：
- 使用中文
- 完成后调用 kanban_complete，阻塞时调用 kanban_block
```

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
