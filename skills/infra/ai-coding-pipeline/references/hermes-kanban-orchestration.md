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

统一 Validate 的完整规则见 [SKILL 统一 Validate](../SKILL.md#unified-validate)，Full/Light 使用同一份。

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
