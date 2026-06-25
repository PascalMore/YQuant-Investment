# Hermes Kanban 编排规则

YQuant AI Coding Pipeline 在 Hermes 中使用 Kanban profile worker，而不是 OpenClaw `agentId` 或 Hermes `delegate_task`。

## 配置来源

AI Coding Pipeline 的源目录是：

```text
/home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/
```

Hermes profile 下的目录：

```text
~/.hermes/profiles/<profile>/skills/infra/yquant-ai-coding-pipeline/
```

只是运行态安装副本。修改流水线规则、参考文档、脚本或模板时，必须先改项目源目录，再同步到各 profile。不要直接把长期变更只留在 `~/.hermes/profiles/`，否则迁移到新 Hermes 机器时会丢失。

例外：模型、fallback、toolsets、credential pool 等 profile 运行参数仍以 `~/.hermes/profiles/<profile>/config.yaml` 为准。

历史遗留的 `~/.hermes/profiles/yquant/skills/infra/yquant-delegation-mechanics/` 是迁移排查期间创建的运行态记录，不是项目 source of truth。其有效结论已经合并到本 skill；不要再把该目录作为新的长期规则来源。

## 为什么不用 delegate_task

`delegate_task` 会创建当前 profile 下的临时子 agent：

- 子 agent 默认继承父 profile 的模型、fallback、工具面。
- 单次调用不能指定 `profile=yquantprincipal`。
- prompt 中写“你是 yquantprincipal”只是语义提示，不会切换 profile。
- 适合短推理和并行阅读，不适合 RFC/SPEC/Design/Implement/Verify/Review 这种角色化流水线。

## 正式委派方式

YQuant 必须通过 `kanban_create` 创建任务：

```python
kanban_create(
    title="RFC/SPEC: <short task name>",
    assignee="yquantprincipal",
    body="<完整任务上下文、交付物、验收标准>",
    workspace_kind="dir",
    workspace_path="/home/pascal/workspace/yquant-investment",
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
    workspace_path="/home/pascal/workspace/yquant-investment",
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

- `yquant` profile 必须启用 `kanban` toolset。
- Hermes gateway 必须运行，dispatcher 才会自动 pick up ready task。
- 目标 profile 必须存在于 `~/.hermes/profiles/`。
- 被分派的 worker 会自动加载 `kanban-worker`；YQuant 自定义 pipeline skill 应安装到需要理解流水线的 profile。

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
