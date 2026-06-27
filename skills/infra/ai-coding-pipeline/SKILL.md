---
name: yquant-ai-coding-pipeline
description: "用于 YQuant 或应龙项目非平凡工程任务的七阶段 AI Coding 流水线：Intake、RFC/SPEC、Design、Implement、Verify、Review、Closeout。"
---

# AI Coding 流水线（YQuant / 应龙共享）

用于 YQuant 或应龙项目的非平凡工程任务，尤其是涉及 RFC/SPEC、设计、代码变更、测试、审查、发布准备、数据模型、API、交易、风控或生产行为的任务。

除非用户明确要求走流水线，否则普通问答、极小拼写修正、只读查询不需要触发本 skill。

## Hermes 执行模型

本流水线在 Hermes 中使用 **Kanban profile worker** 执行。

- 本 skill 的源代码、参考文档和维护入口在项目内：`/home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/`。
- 不再维护 `~/.hermes/profiles/*/skills/infra/yquant-ai-coding-pipeline/` 运行态副本；长期修改只落到项目源目录，worker 通过 `workspace_path` 发现项目源 skill。
- 运行态 profile 的模型、fallback、toolsets 等易变配置仍以 `~/.hermes/profiles/<profile>/config.yaml` 为准，项目内只保存路由语义、阶段门禁和可复用 skill 逻辑。
- 当前入口 profile 是 orchestrator，负责 Intake、解析目标工作目录、创建 Kanban 任务、校验阶段门禁和 Closeout。
- 阶段执行必须通过 `kanban_create` 创建真实任务，并设置 `assignee` 为对应 Hermes profile。
- 不要用 `delegate_task` 承担正式流水线阶段；`delegate_task` 只适合短推理子任务，且默认继承父 profile 的模型，不能按单次调用切到 `yquantprincipal` / `yquantdeveloper` 等 profile。
- **历史教训（2026-06-25 RFC-03-006 案例）**：`delegate_task` **不在 Kanban DB 创建 task 记录**，会导致后续阶段 `parents=[前阶段 task_id]` 无法设置，pipeline 自动串联中断。所有流水线阶段必须用 `kanban_create` 派任务，每个阶段设置 `parents`，dispatcher 才能自动 promote。详见 `references/real-run-journal-2026-06-25.md` 关键观察 6。
- **SPEC §3 文件清单必须精确到目录层级**（2026-06-25 教训）：不能写“新建 `providers/` 子包”这种模糊描述，要写“在 `scripts/extractors/providers/` 下新建 10 个文件”。否则 Implement worker 可能写到错的目录层级。详见 `references/real-run-journal-2026-06-25.md` 关键观察 7。
- 不要只在文本中声明“委派给某 Agent”；没有 `kanban_create` 任务就不算真实委派。
- 任务工作目录必须使用下面“项目上下文解析”得到的共享项目目录；禁止 worker 根据自身 profile 名推断项目。

### 项目上下文解析

Intake 开始时必须根据当前 orchestrator profile 解析一次 `PIPELINE_WORKSPACE`：

| Orchestrator profile | `PIPELINE_WORKSPACE` | 项目名称 |
|---|---|---|
| `yquant` | `/home/pascal/workspace/yquant-investment` | YQuant |
| `yingyong` | `/home/pascal/workspace/yq-yinglong` | 应龙 |

- 只允许上述两个映射；无法确认当前 orchestrator 时必须停止并向用户确认。
- 同一条流水线从 Intake 到 Closeout 必须保持同一个 `PIPELINE_WORKSPACE`。
- 每个 `kanban_create` 都必须显式设置 `workspace_kind="dir"` 和解析后的绝对 `workspace_path`。
- 任务正文必须同时写明目标项目绝对路径，并禁止修改另一个项目。
- worker 以任务传入的 `workspace_path` / `$HERMES_KANBAN_WORKSPACE` 为准，不重新解析 orchestrator。

### Hermes Profile 路由

| 阶段 | Hermes assignee profile | 职责 |
|------|--------------------------|------|
| Intake / Closeout | 当前 orchestrator：`yquant` 或 `yingyong` | 需求澄清、编排、阶段门禁、最终交付 |
| RFC / SPEC / Design | `yquantprincipal` | RFC/SPEC/Design、架构、接口、数据模型、风险评估 |
| Implement | `yquantdeveloper` | 按已确认 SPEC/DESIGN 做最小范围实现 |
| Verify | `yquanttester` | 独立验证、测试报告、残余风险 |
| Review | `yquantreviewer` | 独立代码审查、风险审查、通过/退回决定 |

### 源目录与运行态同步

AI Coding Pipeline skill 的 **canonical source 只有项目源目录一份**：

```text
/home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/
```

修改 AI Coding Pipeline 时，只改项目源目录。不要再维护 `~/.hermes/profiles/*/skills/infra/yquant-ai-coding-pipeline/` 运行态副本；否则项目源和 profile 副本会再次漂移，并触发或掩盖 skill collision 问题。

清理 profile 副本：

```bash
rm -rf /home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline
for p in yquantprincipal yquantdeveloper yquanttester yquantreviewer; do
  rm -rf "/home/pascal/.hermes/profiles/$p/skills/infra/yquant-ai-coding-pipeline"
done
```

**不要把 worker profile（principal/developer/tester/reviewer）的 skill 副本留下**——它们和项目源目录的同名 skill 会触发 **Skill name collision**，worker 启动后立刻 crash（exit 1）且不会进入对话循环。

正确策略（2026-06-28 更新）：
- `yquant` 主 profile：**不保留副本**，通过 YQuant 项目 external skills 目录加载本源文件。
- `yingyong` 主 profile：**不保留副本**，`skills.external_dirs` 直接加载本 canonical skill 目录。
- 4 个 worker profile（principal/developer/tester/reviewer）：**不要放副本**，通过 `workspace_path` 发现项目源目录。

部署后立即验证（应该只看到项目源目录一份）：

```bash
find /home/pascal/.hermes/profiles /home/pascal/workspace/yquant-investment \
  -name "SKILL.md" -path "*ai-coding-pipeline*"
```

### Kanban 创建规则

完整流程必须创建依赖链：

```text
T1 RFC/SPEC       assignee=yquantprincipal
T2 Design         assignee=yquantprincipal   parents=[T1]
T3 Implement      assignee=yquantdeveloper   parents=[T2]
T4 Verify         assignee=yquanttester      parents=[T3]
T5 Review         assignee=yquantreviewer    parents=[T4]
```

轻量流程必须创建依赖链：

```text
T1 Implement      assignee=yquantdeveloper
T2 Verify         assignee=yquanttester      parents=[T1]
```

每个 `kanban_create` 的 body 必须包含：

- 用户目标和当前阶段。
- 相关文件、目录、RFC/SPEC/DESIGN 路径。
- 允许修改的范围和禁止事项。
- 明确交付物。
- 验收标准。
- 需要运行的测试或可接受的替代验证。
- 输出语言要求：中文。

Orchestrator 创建任务后必须向用户说明目标项目、任务图、任务 ID、assignee、依赖关系和如何追踪状态。

## 触发入口

### 显式触发

用户明确提到以下表达时，必须启用完整 AI Coding 流水线：

- “走 AI Coding Pipeline”
- “按流水线执行”
- “按 RFC/SPEC/Design/Implement/Verify/Review/Closeout 流程”
- “先写 RFC/SPEC/Design，再实现”
- “需要独立测试和审查”

### 自动触发

用户没有显式要求，但任务满足以下条件之一时，先向用户确认是否走完整流水线：

- 新增核心功能。
- 对现有功能做非平凡改进、优化、重构、升级。
- 修改架构、数据模型、任务调度、报告生成、投资研究、交易相关逻辑。
- 跨多个模块或多个目录的改动。
- 需要新增或修改 RFC、SPEC、Design 文档。
- 存在较高风险，例如数据正确性、回测结果、外部 API、生产脚本、自动化执行。
- 用户要求“方案评审”“架构设计”“独立 review”“测试验证”。

### 轻量触发

以下任务默认不走完整流水线，除非用户明确要求：

- 文案、注释、README 小改动。
- 对已有功能的小问题修复。
- 不涉及 RFC/SPEC/Design 变更的优化。
- 单文件低风险 bug fix。
- 格式化、路径修正、模板补充。

轻量流程为：

`Orchestrator Intake -> YQuant-Developer-Engineer Implement -> YQuant-Test-Engineer Verify -> Orchestrator Closeout`

轻量流程仍必须保留最小 Verify，不能把未验证的实现直接 Closeout。

## 编排顺序

完整流水线固定为：

1. 当前 orchestrator（`yquant` 或 `yingyong`）：Intake 需求澄清，解析并固定 `PIPELINE_WORKSPACE`，确认目标、范围、约束、风险和初步验收标准。
2. `YQuant-Codex-Principal`：RFC/SPEC 编写；当业务语义、接口、数据模型、交易或风控行为发生变化时，先更新相关 RFC，再派生可执行 SPEC。
   - **门禁**：Orchestrator 在此阶段结束后必须校验目标项目 `docs/rfc/` 和 `docs/spec/` 下有对应文件，否则退回。
3. `YQuant-Codex-Principal`：Design 架构设计、详细设计、原型或 UI 设计；定义涉及文件/模块、数据流/控制流、实现顺序、测试、回滚和交接条件。
   - **门禁**：Orchestrator 在此阶段结束后必须校验目标项目 `docs/design/` 下有对应文件，否则退回。
4. `YQuant-Developer-Engineer`：Implement 代码实现，基于已确认的 SPEC/DESIGN 做最小范围修改。
5. `YQuant-Test-Engineer`：Verify 测试验证，按验收标准独立测试。
6. `YQuant-Reviewer-Principal`：Review 独立审查 diff、测试结果，以及实现与 RFC/SPEC/DESIGN 的一致性。
7. 当前 orchestrator：Closeout 收尾，总结变更、验证结果、残余风险和后续事项。

除非用户明确要求跳过某一步，否则完整流水线不得跳过 Verify 和 Review。

### 三层文档强制规则

RFC、SPEC、Design **必须分别产出独立文件**，存放在各自目录下。不允许将 SPEC 或 Design 内容合并到 RFC 中。详细门禁校验规则见 `references/document-layers.md`。

## 强制角色拆分

| 阶段 | Agent | Profile 配置 |
|------|-------|--------------|
| Intake / Closeout | 当前 orchestrator | `~/.hermes/profiles/yquant/config.yaml` 或 `~/.hermes/profiles/yingyong/config.yaml` |
| RFC / SPEC / Design | YQuant-Codex-Principal | `~/.hermes/profiles/yquantprincipal/config.yaml` |
| Implement | YQuant-Developer-Engineer | `~/.hermes/profiles/yquantdeveloper/config.yaml` |
| Verify | YQuant-Test-Engineer | `~/.hermes/profiles/yquanttester/config.yaml` |
| Review | YQuant-Reviewer-Principal | `~/.hermes/profiles/yquantreviewer/config.yaml` |

**模型与 fallback 不写在本 skill 里**——它们是易变事实，每次模型升级都会变化。查询当前实际配置：

```bash
python3 skills/common/utils/print_agent_models.py
```

> ✅ **原则：升级模型时只改 `config.yaml`，skill 不动。** 改完跑一次上面的脚本自检，确认输出与你的预期一致。

除非用户明确覆盖流水线规则，否则 `Implement`、`Verify`、`Review` 必须由不同角色承担。

## 运行态自检

开始流水线前，orchestrator 必须确认：

- 当前 orchestrator（`yquant` 或 `yingyong`）已启用 `kanban` toolset。
- Hermes gateway 正在运行；否则 Kanban ready task 不会自动派发。
- 目标 assignee profile 存在：`yquantprincipal`、`yquantdeveloper`、`yquanttester`、`yquantreviewer`。
- `~/.hermes/kanban.db` 能记录任务；若任务没有进入 `tasks` 表，说明没有真实委派。
- **只保留项目源目录的 skill，4 个 worker profile 不放同名副本**（避免 Skill name collision 导致 worker 启动崩溃）。

验证命令：

```bash
python3 skills/common/utils/print_agent_models.py
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect('/home/pascal/.hermes/kanban.db')
print(conn.execute('select count(*) from tasks').fetchone()[0])
PY
```

## Pitfalls（2026-06-25 实跑后补）

### P-1: Skill name collision 让 worker 永远进不了对话循环

**症状**：dispatcher 60s 内 spawn worker，子进程立即 crash（exit 1），task 状态先 `running` 再 `crashed`，连续两次失败后进入 `blocked` + `gave_up`。`agent.log` 末尾只有：

```
WARNING tools.skills_tool: Skill name collision for '...': 2 candidates — <path-a>; <path-b>
```

**没有 `agent.turn_context` 日志**，意味着 worker 从未进入对话循环。

**根因**：worker 的 `HERMES_HOME` 指向 `~/.hermes/profiles/<worker>/`，但同时也通过 `workspace_path` 看到项目目录里的同名 skill。两个候选被 Hermes 视为冲突，启动时直接退出。

**修复**：删除 4 个 worker profile（`yquantprincipal/developer/tester/reviewer`）的 `skills/infra/yquant-ai-coding-pipeline/` 副本，只保留项目源目录这一份。worker 通过 workspace discovery 自动加载。

**预防**：流水线部署完成后立即跑一次 `find ~/.hermes/profiles -name "SKILL.md" -path "*yquant-ai-coding-pipeline*"`——应该看不到任何 profile 副本；全局检查只应看到项目源目录一份。

### P-2: dispatcher 透明跑 fallback 链，任务名义 assignee 与实际模型可能不一致

**症状**：`kanban_create(assignee="yquantprincipal")` 派出的 task 实际由 zai/glm-5.2 甚至 MiniMax-M3 完成。task summary 看似完成，但内容质量反映的是 fallback 模型的能力上限，不是 yquantprincipal 的设计意图。

**根因**：dispatcher spawn worker 时设置 `HERMES_HOME=~/.hermes/profiles/<assignee>/`，worker 加载该 profile 的 `config.yaml`。**`config.yaml` 的 `fallback_providers` 是 worker 进程内透明的**：gpt-5.5 失败 → 切 zai → 切 minimax，全程 worker 不报错，task 状态正常变 done。

**观察命令**：

```bash
grep -E "Fallback activated|API call.*model=" \
  ~/.hermes/profiles/<worker>/logs/agent.log | grep "<session_id>"
```

**预防**：高价值任务（RFC/SPEC/Design/Review）派发后监控 worker 日志，确认 primary 模型跑通而非 fallback。如果 gpt-5.5 不可达，先排查 chatgpt.com 网络 / OAuth 凭证，再考虑降级策略（要么换模型，要么先改 `fallback_providers` 把 zai 移到第一位作为暂时妥协）。

### P-3: Kanban DB 任务 ID 不存在时不能 "parents=[]" 强行串联

**症状**：旧 RFC/SPEC 是用文本声明 + `delegate_task` 做的（没有 kanban task），想派 Design 任务并设 `parents=[<SPEC 的 task id>]` 会失败——因为那个 task id 从来没存在过。

**修复**：用 C3 方案——在 Design 任务 body 里**显式引用 SPEC 文件路径**（如 `docs/spec/03_data/SPEC-03-006-*.md`），不依赖 parent task 链路。Design 阶段自己读 SPEC 文件来保证一致性。**不要**为了“补建 parent”创建空的 SPEC 幽灵任务。

### P-4: workspace_path 必须用共享项目目录

**症状**：worker 在自己 profile 的 state.db 目录下工作，不会自动访问项目源目录，导致找不到 skill / RFC / SPEC 文件。

**正确姿势**：

```python
kanban_create(
    ...,
    workspace_kind="dir",
    workspace_path=PIPELINE_WORKSPACE,
)
```

不要用 `workspace_kind="scratch"` 或留空——会丢失共享项目目录上下文。

### P-5: Worker 完成后必须 unblock parent（不阻塞下一阶段）

**症状**：T3 / T4 / T5 阶段 worker 完成后主动调用 `kanban_complete(..., result="review-required: ...")`，状态变为 `blocked` 等 YQuant（orchestrator）来 unblock。但 YQuant 不会自动监控 blocked 状态，pipeline 在这一步**卡住**：下一阶段（T4 / T5 / Closeout）永远等不到 promote。

**观察**（2026-06-27 实战）：T3' 修复完后 worker blocked 26 分钟无人 unblock，T4' 一直 `todo`，用户问"为什么慢"才暴露问题。

**修复**（worker 行为约束）：

1. **worker 完成后应直接 `kanban_complete(..., summary=...)` 并 `status="done"`，不要 `review-required:` 标记 blocked**。**Reviewer 阶段本身就是独立 review**——不需要 worker 替 reviewer 预告。

2. **仅在以下情况用 `review-required:` blocked**：
   - 任务真的有非阻塞风险需要 YQuant 即时拍板（如生产配置变更、跨产品影响）
   - 已在子任务里创建 Reviewer 任务并 parents 串联

3. **YQuant（orchestrator）侧的补救路径**：发现某个任务 `blocked` 但无后续任务在跑时，可以直接 `kanban_unblock(task_id)`，dispatcher 会重新 claim 并完成。但**这只是补丁**，根因是 worker 误用 blocked。

4. **P-5 健康检查**：流水线中如发现任何任务连续 10 分钟处于 `blocked` 且 heartbeat 缺失，主动 unblock + 在 T5 closeout 报告里记录事件。

**预防**：完整流程跑完后，YQuant 在 T5 closeout 阶段应**主动**核对：
- T1-T5 状态全部 `done`？
- 没有遗留 `blocked` / `running` 但无 heartbeat 的孤儿任务？
- 如果有，立刻 unblock 或归档。

**与 P-2 的关系**：worker 也会因 dispatcher 透明 fallback 跑错模型而 hidden 失败，状态可能误标 `done`。P-5 关注**状态机正确**；P-2 关注**完成的内容质量**。两者都需要监控。

**建议每阶段预期耗时**（基于 2026-06-25 / 06-27 实战均值）：

| 阶段 | 典型耗时 | 主要耗时点 |
|---|---|---|
| T1 RFC/SPEC | 5-10 分钟 | yquantprincipal LLM 推理 |
| T2 Design | 5-10 分钟 | yquantprincipal LLM 推理 |
| T3 Implement | 5-15 分钟 | yquantdeveloper LLM + 测试运行 |
| T4 Verify | **5-15 分钟** | yquanttester 跑测试集 + dry-run 验证 |
| T5 Review | 5-10 分钟 | yquantreviewer LLM 推理 |

> **异常长耗时（如 T4 > 30 分钟）通常说明**：worker 卡在某个测试用例 / LLM 推理 hang / 模型 fallback 慢。可以 `kanban_list status=running` 查 PID + `process(action='poll')` 看 heartbeat 时间。

## 参考资料

- `references/pipeline.md`：阶段门禁、任务目录结构、路由规则。
- `references/document-layers.md`：RFC/SPEC/DESIGN 的职责边界。
- `references/agent-handoff.md`：角色交接内容、交付物和退回条件。
- `references/hermes-kanban-orchestration.md`：Hermes Kanban profile worker 编排规则。
- `references/spec-from-rfc.md`：**SPEC 阶段专用编写手册**——从 RFC 派生 SPEC 时的决策→契约映射模式、12 节章节清单、7 类陷阱（含「不改动清单 P-2」「硬编码版本号 P-3」「向后兼容 P-4」「混淆 SPEC/Design 边界 P-7」）、验证清单与完成回报模板。
- `skills/common/utils/print_agent_models.py`：查看所有 Agent 当前模型/fallback/compression 配置。
- `references/real-run-journal-2026-06-25.md`：**实跑日志**——2026-06-25 RFC-03-006 流水线从中断点 Design → Implement 推进的真实时序、模型 fallback 观察、worker crash 复盘。Read this before deploying the pipeline for the first time.
