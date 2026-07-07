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
- `kanban_create(skills=[...])` 只能引用目标 assignee profile 可见的 **canonical/project skill**。不要把 orchestrator 自己 profile-local 的补丁 skill 传给 worker；worker CLI 会在初始化阶段报 `Unknown skill(s)` 并立即 crash，连 `agent.turn_context` 都不会进入。
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
| `yinglong` | `/home/pascal/workspace/yq-yinglong` | 应龙 |

- 只允许上述两个映射；无法确认当前 orchestrator 时必须停止并向用户确认。
- 同一条流水线从 Intake 到 Closeout 必须保持同一个 `PIPELINE_WORKSPACE`。
- 每个 `kanban_create` 都必须显式设置 `workspace_kind="dir"` 和解析后的绝对 `workspace_path`。
- 任务正文必须同时写明目标项目绝对路径，并禁止修改另一个项目。
- worker 以任务传入的 `workspace_path` / `$HERMES_KANBAN_WORKSPACE` 为准，不重新解析 orchestrator。

### 项目约定发现与任务正文固化

Pipeline 是跨项目基础设施，但每个项目的文档目录、模块编号、skill/module 命名、持久化规范和凭据位置可能不同。**Intake 在派第一个 worker 前必须发现并固化目标项目约定**，不能把 YQuant 的目录约定照搬到其他项目。

最低发现步骤：

```bash
cd "$PIPELINE_WORKSPACE"
find docs -maxdepth 3 -type f -name 'README.md' -o -name '*-00-000-*template*.md' 2>/dev/null
find skills -maxdepth 3 -name SKILL.md 2>/dev/null | head -80
find config -maxdepth 2 -type f 2>/dev/null | sort
```

Intake 必须把以下内容写进**每个文档类任务（RFC/SPEC/Design）的 body**，不要只放在 README 或 skill 里：

- 目标项目绝对路径与禁止修改的外部项目路径。
- 文档目录命名规则：`docs/{rfc,spec,design}/...` 的具体子目录。
- 文档文件命名规则：`{TYPE}-{NN}-{XXX}-{short-name}.md` 或目标项目实际规则。
- 本任务交付物的**精确目标路径**，至少给 1 个完整示例。
- 项目私有约束（数据库集合前缀、隐私分级、外部 API mock/real 模式、凭据文件位置等）。

**原则**：worker 优先读 task body；README、模板和 skill 是参考材料，不保证被 worker 主动打开。凡是会影响路径、命名、数据契约或安全边界的约定，都必须在 task body 中显式出现。

### Hermes Profile 路由

| 阶段 | Hermes assignee profile | 职责 |
|------|--------------------------|------|
| Intake / Closeout | 当前 orchestrator：`yquant` 或 `yinglong` | 需求澄清、编排、阶段门禁、最终交付 |
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

**不要把 worker profile（principal/developer/tester/reviewer）的 skill 副本留下**——它们和项目目录的同名 skill 会触发 **Skill name collision**，worker 启动后立刻 crash（exit 1）且不会进入对话循环。

正确策略（2026-06-28 更新）：
- `yquant` 主 profile：**不保留副本**，通过 YQuant 项目 external skills 目录加载本源文件。
- `yinglong` 主 profile：**不保留副本**，`skills.external_dirs` 直接加载本 canonical skill 目录。
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

## 编排顺序：Full Flow

完整流水线固定为：

1. 当前 orchestrator（`yquant` 或 `yinglong`）：Intake 需求澄清，解析并固定 `PIPELINE_WORKSPACE`，确认目标、范围、约束、风险和初步验收标准。
2. `YQuant-Codex-Principal`：RFC/SPEC 编写；当业务语义、接口、数据模型、交易或风控行为发生变化时，先更新相关 RFC，再派生可执行 SPEC。
   - **门禁**：Orchestrator 在此阶段结束后必须校验目标项目 `docs/rfc/` 和 `docs/spec/` 下有对应文件，否则退回。
3. `YQuant-Codex-Principal`：Design 架构设计、详细设计、原型或 UI 设计；定义涉及文件/模块、数据流/控制流、实现顺序、测试、回滚和交接条件。
   - **门禁**：Orchestrator 在此阶段结束后必须校验目标项目 `docs/design/` 下有对应文件，否则退回。
4. `YQuant-Developer-Engineer`：Implement 代码实现，基于已确认的 SPEC/DESIGN 做最小范围修改。
5. `YQuant-Test-Engineer`：Verify 测试验证，按验收标准独立测试。
6. `YQuant-Reviewer-Principal`：Review 独立审查 diff、测试结果，以及实现与 RFC/SPEC/DESIGN 的一致性。
7. 当前 orchestrator：Closeout 收尾，总结变更、验证结果、残余风险和后续事项。

除非用户明确要求跳过某一步，否则完整流水线不得跳过 Verify 和 Review。

## 三流程定位（Full / Quick / Light）

AI Coding Pipeline 当前提供 **三种流程模式**，orchestrator 必须先判定走哪一种，再创建 Kanban 任务链：

| 流程 | 阶段数 | Kanban task 数 | 适用场景 | 是否做三层文档 | 是否有独立 Review |
|---|---|---|---|---|---|
| **Full Flow（完整流程）** | 7 | 6 | 高风险、跨模块、交易/风控、需独立审查 | RFC + SPEC + Design（独立 task） | 是 |
| **Quick Flow（快捷流程）** | 5 | 4 | 中风险、明确需求、改动 3-8 文件、单模块、不触交易/风控 | RFC + SPEC + Design（合并为 1 task） | 否（Closeout 自审替代） |
| **Light Flow（轻量流程）** | 4 | 2 | 单文件低风险 bug fix、注释/格式微调 | 否 | 否 |

三流程**互斥**：一次流水线只能走一种，混用会破坏依赖链和门禁语义。详见 `references/pipeline.md` 的"阶段总览"与下方的 Quick Flow 章节。

> **衔接机制同源度**：Full Flow（衔接 0 次进程层主动）→ **Quick Flow V1.2（衔接 0 次进程层主动，与 Full Flow 同源）** → Light Flow（衔接 1 次进程层主动，Intake 同步）。Quick Flow V1.2 之前是 3 次进程层主动，**2026-06-30 yinglong 5h44m 断链事故后已对齐 Full Flow**。根因分析 + 故障源可达性矩阵 + Q-LINK 契约详见 `references/quick-flow-handoff-mechanism.md`。

## 编排顺序：Quick Flow

Quick Flow 5 阶段（4 个 Kanban task），衔接机制与 Full Flow 同源：Intake 阶段一次性预创建 T1-T4，由 Kanban DB parent links + dispatcher promote 自动衔接，**不依赖 orchestrator 串行调度**（避免 2026-06-30 yinglong 5h44m 断链事故，P-12）。

```text
Intake (orchestrator)  ──►  一次性 kanban_create T1/T2/T3/T4 (含 parents)
   │
   ▼
T1 RFC/SPEC/Design   assignee=yquantprincipal  status=ready    parents=[]           ← dispatcher 立即 claim/spawn
T2 Implement         assignee=yquantdeveloper  status=todo     parents=[T1]        ← T1 done 后由 recompute_ready 自动 promote
T3 Verify            assignee=yquanttester     status=todo     parents=[T1, T2]    ← T2 done 后由 recompute_ready 自动 promote
T4 Closeout          assignee=<orchestrator>   status=todo     parents=[T1, T2, T3] ← T3 done 后由 recompute_ready 自动 promote
```

> 衔接契约（Q-LINK）：详见 `references/pipeline.md` 的 "Quick Flow 衔接机制（Q-LINK 契约）" 章节与 SPEC-10-004 §13.10。

### Quick Flow 阶段定义

1. **Intake**（orchestrator）：需求澄清，判定走 Quick Flow（见下方决策树）。解析 `PIPELINE_WORKSPACE`，固定目标项目，固化目标项目约定。**Intake 必须一次性预创建 T1/T2/T3/T4** 四个 Kanban task，T1 立即 `ready`、T2/T3/T4 `todo` + parents，后续衔接交给 Kanban DB 状态机（`task_links` + `recompute_ready` + `dispatch_once`），不依赖 orchestrator 主 session 或 watcher 持续在线。**禁止**在前序任务 done 后才临时创建下一张 task。
2. **T1 RFC/SPEC/Design（yquantprincipal）**：一个 Kanban task 同时产出 RFC / SPEC / Design 三份独立文档，分别落到 `docs/{rfc,spec,design}/{module}/` 对应路径。三份文档保留三层职责边界，**不得合并章节**。T1 body 必须在顶部显式声明"本任务走 Quick Flow"和 T2/T3/T4 task id。T1 done 后由 dispatcher 自动 promote T2。
3. **T2 Implement（yquantdeveloper）**：基于已确认的 SPEC + Design 做最小范围实现。T3 Verify 不得跳过。T2 done 后由 dispatcher 自动 promote T3。
4. **T3 Verify（yquanttester）**：独立验证 + 端到端 smoke test，**必须做数据合理性抽样**（P-11）。T3 done 后由 dispatcher 自动 promote T4。
5. **T4 Closeout（orchestrator）**：执行 DESIGN-10-004 §3.5 自审清单（**15 项**，含 V1.2 新增的 #1 Intake 一次性预创建 + #2 T2/T3/T4 parent links），逐项 ✅/❌ 标注。**无独立 Reviewer**，自审替代；T4 必须先复核 T1-T4 在 Intake 阶段一次性预创建且 parent links 完整（Q-A-008 / Q-LINK-001~006）。

完整流程 → Quick Flow **不允许降级**（已创建的多余 Kanban task 不会自动消失）。Quick Flow → 完整流程 **可以升级**（T1 已完成则补开独立 Design task；T3 之后追加独立 Review task）。

## Quick Flow 触发条件

orchestrator 在 Intake 阶段执行以下决策树：

```
用户需求到达
   │
   ├─ 涉及 MongoDB 写入 / 核心交易 / 真实资金 / 生产 schema 变更 / 跨 2+ 模块架构?
   │    └─ 是 → Full Flow（独立 Review）
   │
   ├─ 单文件低风险 bug fix / 注释 / 格式化 / 路径修正?
   │    └─ 是 → Light Flow
   │
   ├─ 中风险 + 需求明确 + 改动 3-8 文件 + 单模块 + 不触交易风控 + 不改三方依赖?
   │    ├─ 是 → Quick Flow（5 阶段 4 task，Closeout 自审替代 Review）
   │    └─ 否 → Full Flow
   │
   └─ 用户明确说 "走 Quick Flow / 按快捷流程 / 5 阶段快速"?
        └─ 是 → Quick Flow（覆盖上述判断）
```

### Quick Flow 显式触发词

- "走 Quick Flow"
- "按快捷流程"
- "5 阶段快速"
- "用 Quick 流程"

### Quick Flow 适用场景（必须全部满足）

- 风险等级：中等或以下。
- 需求明确度：用户目标已清晰，无需多轮探索。
- 改动范围：3-8 个文件，单模块为主。
- 不涉及核心交易、风控、生产数据库 schema 变更、跨 2+ 模块架构变更。
- 不新增/升级三方依赖。

### 禁止 Quick Flow 场景（任一命中即升 Full）

- 写入生产 MongoDB 集合（含 `portfolio_position` / `portfolio_trade` / Argus / signal 等）。
- 修改交易执行逻辑、风控规则、回测引擎真实计算路径。
- 跨 2+ 模块的架构变更（涉及多个 `docs/{rfc,spec,design}/{module}/` 子目录）。
- 用户明确要求"独立 review"或"独立测试验证"。
- 凭据相关实现且需要真实外部 API smoke test（按 P-10 仍需要，但应升 Full 以保留独立 Review）。

### Quick → Full 升级时机

T1/T2/T3 任意阶段，orchestrator 若发现：

- 实际风险超出 Quick Flow 边界（如发现需要修改核心交易逻辑）。
- 用户明确要求升 Full。
- T3 Verify 发现需要独立 Reviewer 介入的问题。

**升级操作**：
1. 若 T1 已完成：补开 `T_Design` 独立 task（assignee=yquantprincipal），parents=[T1]。
2. 在 T3 之后追加 `T_Review` task（assignee=yquantreviewer），parents=[T3]。
3. 更新后续 task body 的流程模式声明（把 "Quick Flow" 改为 "Full Flow"）。

### Quick Flow 失败模式（orchestrator 应监控的异常信号）

| 信号 | 含义 | 动作 |
|---|---|---|
| T1 一次迭代产出 RFC + SPEC + Design 但章节结构不完整 | T1 body 最低要求未满足（SPEC §13.2） | 退回 T1 重做 |
| T2 代码改动超出 Design §3.1 预期文件清单 | 实现者越界 | 退回 T2 缩小范围 |
| T3 Verify 漏掉数据合理性抽样（业务字段错配、fixture 全空） | P-11 未落实 | 退回 T3 补跑端到端 smoke |
| T4 Closeout 自审清单某项标注 ❌ 但仍 continue | 自审被敷衍 | 不允许 closeout，补完再 T4 |
| T2/T3 完成后状态变 `blocked` 而非 `done` | P-5 worker 误 block（最常见：`残余风险待确认` ≠ block 理由） | **判定 P-5 决策树**：验收 PASS 但有残余风险 → 直接 `done` + 风险进 `summary`/`metadata.residual_risks`。仅 FAIL 才 block。orchestrator 发现误 block 立刻 `kanban_unblock` + 必要时手动 `kanban_complete` 标 done |

P-1~P-13 pitfalls **在 Quick Flow 中全部继续适用**（DESIGN-10-004 §3.7 兼容性矩阵，含 V1.2 新增的 P-12 orchestrator 串行调度风险 + 2026-07-01 新增的 P-1c worker profile `external_dirs` 必须覆盖目标项目 skills 目录），无例外。

## Quick Flow 阶段门禁

> 衔接机制状态：V1.2 起 Intake 阶段已落地一次性预创建 T1-T4（Q-LINK-001~006），所有阶段门禁**不再依赖 orchestrator 串行调度**；门禁只看 Kanban DB 中各 task 的 status / 产出物 / 验收标准。

| 阶段 | 门禁 | 验证方式 |
|---|---|---|
| T1 RFC/SPEC/Design | 三份文档存在 + 引用关系正确 + 章节结构完整 + T2/T3/T4 task id 已在 T1 body 显式列出 | orchestrator 校验 |
| T2 Implement | 代码编译/语法通过 + 单元测试通过 + parent=[T1] 仍存在 | developer 自检 + tester 验证 |
| T3 Verify | 验收标准全部通过 + 端到端 smoke test 通过 + 数据合理性抽样 + parent=[T1,T2] 仍存在 | tester 报告 |
| T4 Closeout | DESIGN-10-004 §3.5 自审清单 **15 项** 全部 ✅ + 衔接机制自审（Q-A-008 / Q-LINK-001~006）通过 | orchestrator 逐项核查 |

T4 自审清单 **15 项**（含 V1.2 新增 #1 Intake 预创建 + #2 parent links）详见 `references/pipeline.md` 的 Quick Flow 章节。

### Quick Flow 文档交叉引用

- RFC：`docs/rfc/10_infra/RFC-10-004-yquant-ai-coding-pipeline-skill-sync.md` §12（Quick Flow 扩展，背景/动机/触发条件/Kanban 链/Closeout 自审清单 **15 项**）
- SPEC：`docs/spec/10_infra/SPEC-10-004-yquant-ai-coding-pipeline-skill-sync.md` §13（Quick Flow 可执行契约，**§13.1-§13.10**，含 Q-LINK 契约 §13.10）
- Design：`docs/design/10_infra/DESIGN-10-004-yquant-ai-coding-pipeline-skill-sync.md`（§3.1 时序图、§3.2-§3.5 task body 模板、§3.6 orchestrator 改动点、§3.7 **P-1~P-13** 兼容矩阵、§3.8 降级/升级路径）

> **V1.2 衔接机制改造（2026-06-30）**：Quick Flow 的主进度推进已由 Kanban DB 状态机接管（Intake 一次性预创建 T1-T4 + dispatcher `recompute_ready` + `dispatch_once`）。本节"主动推进规则"现在主要用于：① Full Flow 在 Review 后由 orchestrator 创建 T6 Closeout；② Quick Flow 的 Closeout 自审清单触发（Q-A-008 / Q-LINK-001~006）；③ 异常状态下的应急调度（如 worker 卡死、parent link 断裂、需要紧急 Review）。日常 Quick Flow 的"前序 done → 后序 spawn"**不**依赖本节规则，而由 dispatcher 自动完成。

## Orchestrator 主动推进规则（2026-06-28 新增，2026-06-30 注释）

**核心原则**：流水线在用户确认后必须自动推进到下一个决策点，不需要用户反复询问"完成了吗"。

### 推进流程

```
T5 Review 完成
  ↓
Verdict = PASS → 自动创建 T6 Closeout，完成后汇报最终结果
Verdict = REVISE → 先**问用户**："发现 N 个问题（列出概要）需要修，要继续吗？"
  ↓
用户确认"继续" → ⚡ 全程自动化推进（无需用户再问）⚡：
  1. 自动创建 T3'（Implement fix），parents=[T5]
  2. 自动监控 T3' 完成 → 创建 T4'（Verify），parents=[T3']
  3. 自动监控 T4' 完成 → 创建 T5'（Review），parents=[T4']
  4. T5' 完成 → 回到循环顶部（PASS则Closeout，REVISE则再次询问）
  每完成一步立即告知用户"xxx 已完成，已自动启动下一步"
  遇到新的 REVISE → 再次问用户

用户选择"先不改"或"范围太大" → closeout 并记录未解决项
```

### 关键行为变化

| 之前（有问题） | 之后（修复） |
|---|---|
| 任务跑完 → 汇报 → 等用户问"然后呢" → 才动 | 任务跑完 → 汇报 + 启动下一步 |
| REVISE 后等用户问才创建修复任务 | REVISE 后先问用户 → 确认后立即自动创建 |
| 每个阶段都等人催 | 只用问一次，下个决策点再问 |
| 用户被动催促进度 | 用户被主动告知"下一步已启动" |

### 执行层 Checkpoint（2026-06-29 新增）

Orchestrator 在以下任一信号出现时，**必须立即**派下一阶段任务，**不**等用户问：

| 触发信号 | 检测方式 | 动作 |
|---|---|---|
| 收到"Background process completed (exit code 0)" | process notification | 立即 `kanban_show` 该 task → 若有 children 等待 parents → 派 children |
| `kanban_show` 看到 status=done | 主动查询 | 检查 children 关系，自动派 |
| 用户在对话里问"现在如何了 / 进度" | 用户消息 | **先** 派未派的下一阶段，**然后**汇报当前状态（不等用户先问） |

**历史教训（2026-06-29 Quick Flow 实施）**：T2 done 后 7 分钟内未自动派 T3，被用户问"现在如何了"才被动派。违反"主动推进规则"。**修复**：
- 任何"task done"通知到达 → 30 秒内派下一阶段（如有）
- 调度优先级：派 children > 汇报状态
- 写本节强化执行层约束

**反例（禁止）**：
- ❌ "T2 done 了，要不要我派 T3？"（应直接派）
- ❌ "等您确认"（仅在 REVISE/高风险时等）
- ❌ "我先等您问"（违反主动推进）

**worker 误 block 的主动补救**（2026-07-06 新增，与 P-5 联动）：orchestrator 必须监控 T1-T4 task 的 `status='blocked'` 事件。**任何 `blocked` reason 出现以下特征时，立刻按 P-5 决策树判定**：
- "等 T4 启动 + 人类确认是否接受 XXX 限制" → **典型误 block**，残余风险属于 done 的 summary
- "残余 High 风险待拍板" → **典型误 block**，除非风险**真正阻断后续阶段**
- "建议 yquantprincipal/yquantreviewer 介入" → **越权**，worker 不应替 Reviewer 预告

**补救 SOP**：发现误 block 立刻执行 `kanban_unblock(task_id)` + 必要时 `kanban_complete(summary=..., metadata={residual_risks: [...]})` 手动标 done，并在 Closeout 报告里记录事件。

**预防**：编排层派 task 时，**显式在 body 顶部写明 P-5 完成判定**（见 P-5 决策树 § task body 应有的明确指令 段），让 worker 无歧义。

### 不同 REVISE 严重度的处理方式

- **REVISE（high/major 问题）**：必须问用户后再决定是否继续，因为可能涉及范围变更、额外成本或时间投入
- **REVISE（minor 问题，如文档遗漏、命名建议）**：可以直接修，修完汇报"顺手修了 N 个小问题"
- **无法自动判断严重度时**：统一按 major 处理，先问用户

### 三层文档强制规则

RFC、SPEC、Design **必须分别产出独立文件**，存放在各自目录下。不允许将 SPEC 或 Design 内容合并到 RFC 中。详细门禁校验规则见 `references/document-layers.md`。

## 阶段决策同步门禁（用户决策变更时）

**核心原则**：**用户决策在 T1/T2 阶段拍板后，编排层（orchestrator）必须在 T3 Implement 派发前，把这些决策同步到对应阶段的产出物中**。任何 T1/T2 完成后的用户决策变更，必须先评估"是否需要回头修订 T1/T2 文档"，再决定是否放行 T3。

### 判定规则

**问：这条决策是否会让已完成的 RFC / SPEC / Design 章节"不准确"或"遗漏关键设计"？**

- **是** → 触发同步门禁（按下面的处理流程）
- **否** → 直接写进 T3 body（或下一阶段 body），不回头修订

### 决策类型 → 影响范围 → 同步策略

| 决策类型 | 典型例子 | 影响范围 | 必须在 T3 派发前同步到 |
|---|---|---|---|
| **设计类** | 用什么数据库 / 集合命名规范 / 隐私分级模型 / 三方凭据占位 | RFC + SPEC + Design | T1 body（派发时），或 T1/T2 完成后用 `kanban_comment` 同步 |
| **架构类** | 1+N Skill 拆分 / 文件清单 / 阶段门禁 / 模块边界 | SPEC + Design | T2 body（派发时），或 T2 完成后补 `Design §3.x` 章节 + `kanban_comment` |
| **细节类** | CLI 参数命名 / 配置默认值 / 错误码文案 / 函数名 | Design | T3 body 内"实现约束"段；不回头修订 T1/T2 |

### 同步处理流程（编排层责任）

```
用户提决策
   ↓
[决策分类判断] 问：这条决策会不会让已完成的 RFC/SPEC/Design 章节"不准确"？
   ↓
  是 → 同步门禁触发：
       1. 找出该决策影响的所有已完成阶段（T1 已 done？T2 已 done？）
       2. 若 T1/T2 仍在跑：用 `kanban_comment` 通知 worker（"已采纳新决策：xxx，请在文档中体现"）
       3. 若 T1/T2 已 done：编排层直接补章节（patch 文档），并在下一阶段 body 顶部声明"前置决策增补：见 [path]#[section]"
       4. 后续阶段：必须等 T1/T2 补完后才能派发
   ↓
  否 → 直接写进 T3 body，不回头
   ↓
[同步完成后] 才能派 T3（Implement 阶段）
```

### 与 P-1~P-5 的关系

- 这是**编排层行为**的规则，不是 worker 行为——worker 不需要主动检查"用户决策是否同步过"
- 但 worker **必须**在开始工作前 read 编排层的 comment（"前置决策增补"），把这些决策作为输入
- 与 P-5（worker blocked 卡住）正交：P-5 是状态机问题，本规则是"决策追溯"问题

### 历史教训（2026-06-28 应龙 RFC-16-001 案例）

**症状**：T1 worker 在 10:03 done，T2 worker 在 10:24 done。期间用户在 10:30 提出"应龙要有专属 MongoDB，集合名加编号前缀"——这是**设计类决策**，影响 RFC §5 架构、SPEC §4.4 配置、Design §3.x 文件清单。编排层在 T3 派发前**未回头补 T1/T2**，只是把"必须用 yinglong-db"写进 T3 body。结果 T2 Design 文档里 0 次出现 "yinglong/mongo/16_travel_/持有化" 关键词，T5 Review 时会找不到"为什么这样设计"的依据。

**修复（本次）**：
- T2 Design 由编排层直接补 §3.8 持有化层（8 个子节）
- T3 comment 显式引用 §3.8 章节作为设计依据

**预防**：本节规则要求，**任何 T1/T2 完成后的用户决策，必须先回头补 T1/T2 文档，再放行 T3**。

## 文档模板变更守则（2026-06-28 新增）

**核心原则**：**文档模板（RFC/SPEC/Design 模板、3 层 README 模板）属于"全局规约源"，所有项目和所有 worker 都会引用**。模板章节结构的变更必须由 `yquantprincipal` 拍板；编排层（orchestrator）不能直接改。

### 适用文件清单

| 文件 | 路径 |
|---|---|
| RFC 模板 | `docs/rfc/RFC-00-000-rfc-template.md` |
| SPEC 模板 | `docs/spec/SPEC-00-000-spec-template.md` |
| DESIGN 模板 | `docs/design/DESIGN-00-000-design-template.md` |
| 3 层 README | `docs/{rfc,spec,design}/README.md` |

### 变更流程

1. **编排层**发现自己需要改模板时 → **不**直接 `patch` / `write_file` 改
2. **派 Kanban 任务**给 `yquantprincipal`，priority 设为高（如 7），body 写明：
   - 触发原因（哪个流水线/案例暴露了模板缺陷）
   - 建议章节（可选，作为初稿）
   - 明确"可重写"，不要把编排层初稿当定稿
3. **principal 改完后**，编排层需要 `cp` 同步到其他项目（yinglong、yquant 等）的对应路径
4. 任何 `kanban_create` 任务**禁止** body 写"直接 patch <template_path>"——只能写"找 principal 走模板变更流程"

### 编排层可以改的文件

| 可以改 | 不可以改 |
|---|---|
| 某个 RFC-16-001 / SPEC-16-001 / DESIGN-16-001 **具体文档** | 文档**模板**（RFC-00-000 / SPEC-00-000 / DESIGN-00-000） |
| 某个 skill 自己的 SKILL.md | ai-coding-pipeline SKILL.md（只能由 principal 改） |
| 某个具体数据（如某 trip 的 final.md） | 全局配置（`config/*.yaml`） |
| `data/<某 trip>/` 临时产物 | 3 层 README 模板 |

### 历史教训（2026-06-28 应龙 RFC-16-001 案例）

**症状**：T1/T2 完成后用户提"应龙要有专属 MongoDB"，编排层在 T2 Design 已 done 之后**直接 patch 3 个文档模板**（RFC/SPEC/DESIGN），给模板加"持久化"章节。补丁里 RFC 模板的"- 异常降级分支"行被误删，需 `git checkout` 撤回。

**根因**：编排层越界。模板是跨项目、跨 worker 的"规约源"，应当由架构师角色（principal）拍板，编排层只负责"用模板"，不应"改模板"。

**预防**：本守则 + P-7 pitfall + 任何模板变更必须派 principal 任务。

## 强制角色拆分

| 阶段 | Agent | Profile 配置 |
|------|-------|--------------|
| Intake / Closeout | 当前 orchestrator | `~/.hermes/profiles/yquant/config.yaml` 或 `~/.hermes/profiles/yinglong/config.yaml` |
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

- 当前 orchestrator（`yquant` 或 `yinglong`）已启用 `kanban` toolset。
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

## Pitfalls（2026-06-25 / 06-28 实跑后补）

### P-1: Skill name collision 让 worker 永远进不了对话循环

**症状**：dispatcher 60s 内 spawn worker，子进程立即 crash（exit 1），task 状态先 `running` 再 `crashed`，连续两次失败后进入 `blocked` + `gave_up`。`agent.log` 末尾只有：

```
WARNING tools.skills_tool: Skill name collision for '...': 2 candidates — <path-a>; <path-b>
```

**没有 `agent.turn_context` 日志**，意味着 worker 从未进入对话循环。

**根因**：worker 的 `HERMES_HOME` 指向 `~/.hermes/profiles/<worker>/`，但同时也通过 `workspace_path` 看到项目目录里的同名 skill。两个候选被 Hermes 视为冲突，启动时直接退出。

**修复**：删除 4 个 worker profile（`yquantprincipal/developer/tester/reviewer`）的 `skills/infra/yquant-ai-coding-pipeline/` 副本，只保留项目源目录这一份。worker 通过 workspace discovery 自动加载。

**预防**：流水线部署完成后立即跑一次 `find ~/.hermes/profiles -name "SKILL.md" -path "*yquant-ai-coding-pipeline*"`——应该看不到任何 profile 副本；全局检查只应看到项目源目录一份。

### P-1b: `kanban_create(skills=...)` 引用 profile-local skill 会让 worker 初始化失败

**症状**：worker 进程启动后数秒内 crash，task 连续失败后 `blocked/gave_up`。目标 profile 单独 smoke test 成功，但带 `--skills <some-skill>` 后立即退出：

```text
Error: Unknown skill(s): <skill-name>
```

**根因**：`kanban_create(skills=[...])` 是由目标 assignee profile 的 Hermes CLI 解析，不是由 orchestrator 解析。orchestrator 自己可见的 profile-local skill（例如只在当前 profile `~/.hermes/profiles/<orchestrator>/skills/` 下）对 `yquantprincipal` / `yquantdeveloper` 等 worker 不可见。

**修复**：
- 不要把 orchestrator profile-local skill 放进 `skills=[...]`。
- 若内容对流程通用，提升到 canonical project skill（本文件或项目源目录）并删除 profile-local 副本。
- 若内容只是项目私有约束，把它写进 task body；worker 不需要加载该 skill 也能执行。

**诊断命令**：

```bash
hermes -p <assignee> chat -q '只回复 OK'
hermes -p <assignee> chat --skills <skill-a>,<skill-b> -q '只回复 OK'
```

第一条成功、第二条失败时，优先检查 `skills=[...]` 中是否有 worker 不可见的 profile-local skill。

### P-1c: worker profile `external_dirs` 必须覆盖目标项目 skills 目录（2026-07-01 实测）

**症状**（yinglong 5 阶段 4 task 实跑）：worker 进程在 `plugin discovery` 完成后**静默死掉**，无 turn_context、无 tool call、Python 无异常堆栈；dispatcher 60s 后报 `pid not alive` → crash → 2 次后 `gave_up`。日志末尾最后一行是 `Plugin discovery complete: 38 found, 32 enabled`，看似正常但实际已经死。

**表面现象干扰**：tail 看 worker log 会看到 MCP stdio server 报 `BrokenPipeError`（`mcp-stderr.log`），容易误判为 MCP 根因。但 **BrokenPipe 是父进程死后子进程写 stdout 失败的结果，不是 cause**。

**真实根因**：worker profile 的 `config.yaml` 里 `skills.external_dirs` **只指向 orchestrator 项目**（如 `/home/pascal/workspace/yquant-investment/skills`），**目标项目的 skills 没被加入**。当 `kanban_create` 的 `workspace_path` 指向 yinglong 项目、且 `skills=[travel, ...]` 引用 yinglong 的 skill 时：

1. worker 启动时按 `external_dirs` 加载 skills → yinglong 的 skill 找不到
2. hermes_cli 抛 `Unknown skill(s): travel` 异常
3. 异常发生在 MCP stdio 启动后的某个 thread 里，**被 hermes_cli 静默吞掉**
4. 主进程被 watchdog SIGKILL
5. dispatcher 等不到心跳 → crash

**根因复盘**（yinglong 5h44m 类事故的反向版本）：

| 表象 | 真实 |
|------|------|
| MCP server `BrokenPipeError` | **结果**，不是 cause（父进程死后子进程 stdout flush 失败） |
| `pid not alive` 60s 后触发 | 真实，进程确实死 |
| plugin discovery 后无任何日志 | 异常被 hermes_cli 静默吞掉 |
| 任务 2 次连挂 100% 复现 | 根因 100% 在配置层，不是环境/网络 |

**修复**（最低成本）：

```bash
# 给所有 4 个 worker profile 加入目标项目 skills 路径
for p in yquantprincipal yquantdeveloper yquanttester yquantreviewer; do
  cfg="/home/pascal/.hermes/profiles/$p/config.yaml"
  cp "$cfg" "$cfg.bak-$(date +%Y%m%d-%H%M%S)"
  python3 -c "
import yaml
y = yaml.safe_load(open('$cfg'))
ext = y.setdefault('skills', {}).setdefault('external_dirs', [])
target = '/home/pascal/workspace/yq-yinglong/skills'
if target not in ext:
    ext.append(target)
yaml.dump(y, open('$cfg', 'w'), default_flow_style=False, sort_keys=False, allow_unicode=True)
"
done
```

**预防**（Intake 阶段必做，纳入标准化 checklist）：

1. **目标项目 conventions 发现时同步固化 worker profile `external_dirs`**：新项目/新 worker profile 上线前，**必须**把目标项目 skills 目录加到 4 个 worker profile 的 `external_dirs`，不能依赖 `workspace_path` 自动发现。
2. **P-1b 与 P-1c 的关键区别**：
   - P-1b：`kanban_create(skills=...)` 引用了 orchestrator 自己可见但 worker 不可见的 profile-local skill → `Unknown skill` 立即报错退出
   - P-1c：**`skills=[]` 引用的 skill 名确实存在于项目目录**，但**项目目录不在 worker profile 的 `external_dirs` 中** → 异常被静默吞掉，**更难诊断**
3. **诊断命令**（P-1c 比 P-1b 难在"静默"）：

```bash
# Step 1: 检查 worker profile 能否看到目标 skill
hermes -p yquantprincipal chat -q "只回复 OK" --skills <target-skill>
# 输出 "Error: Unknown skill(s): <target-skill>" = P-1c 命中

# Step 2: 看 worker profile 实际加载的 external_dirs
grep -A 3 "external_dirs" ~/.hermes/profiles/<worker>/config.yaml

# Step 3: 确认 worker 进程启动后是否有 turn_context（= 是否进入对话循环）
grep "turn_context" ~/.hermes/profiles/<worker>/logs/agent.log | tail -3
# 没有 turn_context 出现 = P-1c 静默失败典型症状
```

**长期改进方向**（未实施）：dispatcher 在 spawn worker 时**自动**根据 `workspace_path` 把目标项目 skills 路径注入 `HERMES_SKILLS_EXTERNAL_DIRS` 环境变量，避免每个项目都要手改 4 个 worker profile config。

**预防 checklist（Intake 必跑）**：

```bash
# 流水线部署/复用前，对每个 worker profile 跑一次
for p in yquantprincipal yquantdeveloper yquanttester yquantreviewer; do
  for s in $(ls -1 $PIPELINE_WORKSPACE/skills/); do
    if ! hermes -p $p chat -q "ok" --skills $s 2>&1 | grep -q "^Error"; then
      echo "  $p: $s ✓"
    else
      echo "  $p: $s ✗ (P-1c 命中：worker 看不到项目 skill)"
    fi
  done
done
```

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

**观察**（2026-07-06 实测，yinglong V1.2 T3）：yquanttester worker 跑完 T3 验证（单测 43/43 + e2e 3 命令 exit 0 + 数据 7/7 PASS + 性能 3 项达标 + 向后兼容 PASS），**仍用 `review-required:` blocked**，reason 写"等 T4 启动 + 人类确认是否接受 V1.2 fixture 限制 + 残余 High 风险是否阻塞上线"。**等用户拍板 4 天未动，T4 永远不会被 dispatcher 自动 promote**。**这是 P-5 错误行为的教科书级反例**：worker 把"残余风险已知 + 不阻塞后续"误判为"必须 human 拍板"。

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

#### block vs done 决策树（worker 行为约束，2026-07-06 新增）

**核心问题**：worker 跑完验证后，应选 `done` 还是 `blocked`？判定标准：

| 完成情况 | 状态选择 | 理由 |
|---|---|---|
| 验收标准 PASS + 残余风险已知但不阻塞 + 无 Reviewer 子任务 | **`done`** | dispatcher 自动 promote 下一阶段；残余风险写进 `summary` 或 `metadata.residual_risks` |
| 验收标准 FAIL（测试不通过 / 数据错配 / 代码未跑通） | **`blocked`** | 真正阻塞，需 orchestrator 介入修复 |
| 高风险变更需 human 拍板（生产 schema / 凭据 / 跨产品影响） | **`blocked`** | 需人类判断才放行 |
| 已创建 Reviewer 子任务并 `parents` 串联 | **`blocked`** | worker 预告 Reviewer 介入是合法的 |
| **残余 High 风险待 human 拍板**（如真实 e2e 凭证缺失、依赖未验证） | **`done` + 写进 `residual_risks`** | **不构成 block 理由**！除非这个风险**阻断后续阶段** |
| 验收 PASS 但 worker 自己"觉得"需要确认 | **`done`** | worker 替 Reviewer 预告是越权 |

**P-5 黄金法则**：

> **PASS = done（残余风险进 summary/metadata）；FAIL = blocked（写明失败原因 + 哪条验收不达标）。** 两类结果之间不存在中间态。如果 worker 觉得有"需要确认的事"，写进 `summary` 的 "已交付但需确认项" 段，让 Reviewer 阶段或人类在 Closeout 时统一处理。

**判定流程**（worker 写 `kanban_complete` 前的自检）：
1. 跑一遍 task body 列出的验收标准 → 全 PASS？
2. 如果全 PASS → 残余风险是"已知但不阻塞"还是"真正阻塞后续"？
3. 已知不阻塞 → `done` + 风险进 `summary`
4. 真正阻塞 → `blocked` + 写明阻塞原因 + 哪条验收待补
5. 验收 FAIL → `blocked` + 写明哪条 FAIL + 期望值 vs 实际值

**task body 应有的明确指令**（orchestrator 派卡时建议写入）：
```
完成后状态选择：
- 验收标准全 PASS → kanban_complete(status="done", summary=..., metadata={residual_risks: [...]})
- 任何验收 FAIL → kanban_complete(status="blocked", reason="<哪条 FAIL + 期望 vs 实际>")
- 不要因"残余风险待确认"使用 blocked——残余风险属于 done 的 summary/metadata
```

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

### P-6: T1/T2 完成后用户决策变更未回头修订

**症状**（2026-06-28 应龙 RFC-16-001 案例）：用户在 T1 done 后提出"应龙要有专属 MongoDB"——这是影响 RFC §5、SPEC §4.4、Design §3.x 的**设计类决策**。但编排层在 T3 派发时只把决策写进 T3 body，没回头修订 T1/T2。结果 T2 Design 文档里 0 次出现 yinglong-db 关键词，T5 Review 找不到"为什么这样设计"的依据，事实文档与设计依据脱节。

**根因**：编排层把"用户决策"等同于"细节微调"，误判其影响范围。其实判定的标准是**"这条决策会不会让已完成章节不准确"**，而不是"这条决策大不大"。

**预防**：
- 详见本文档"**阶段决策同步门禁（用户决策变更时）**"小节
- 操作上：T1/T2 完成后用户提决策，先问"是否影响已完成的章节"；若影响，必须先回头补章节再放行 T3
- 已 done 阶段由编排层直接补；用 `kanban_comment` 通知下一阶段 worker "前置决策增补在 [path]#[section]"

**P-6 与其他 Pitfalls 的关系**：
- P-1~P-5 都是"运行时坑"（worker crash、fallback 透明、状态机错误等）
- P-6 是"流程坑"——编排层行为问题，不是 worker 问题
- 修复动作是"补文档"，不是"改代码"

### P-7: 编排层越界直接改文档模板

**症状**（2026-06-28 应龙 RFC-16-001 案例）：编排层发现"design 模板没有持久化章节"导致 T2 漏设计，在 T2 已 done 后**直接 patch 3 个文档模板**（RFC/SPEC/DESIGN）。patch 里 RFC 模板的"- 异常降级分支"行被误删，需 `git checkout` 撤回。

**根因**：编排层越界。文档模板是跨项目、跨 worker 的"全局规约源"，章节结构变更应当由架构师角色（principal）拍板，编排层只负责"用模板"，不应"改模板"。编排层视角单一（只看单一项目、单一案例），改出来的章节可能不符合 YQuant 整体风格。

**预防**：
- 详见本文档"**文档模板变更守则**"小节
- 操作上：编排层需要改模板时，**必须**派 Kanban 任务给 `yquantprincipal`（priority 7），body 写明触发原因、建议章节（可选）、明确"可重写"
- `kanban_create` 任务 body 禁止写"直接 patch <template_path>"，只能写"找 principal 走模板变更流程"
- principal 改完后，编排层负责 `cp` 同步到其他项目（yinglong、yquant 等）

**P-7 与 P-6 的区别**：
- P-6：编排层补"已 done 任务的文档"是**允许**的（补救）
- P-7：编排层补"跨任务的模板/全局规约"是**禁止**的（必须委派）
- 简单判定：改**当前流水线实例的产出物** = OK；改**所有流水线实例的规约源** = 不 OK

### P-8: 跨项目复用前必须先发现目标项目命名约定

**症状**：orchestrator 把一个项目的 `docs/{rfc,spec,design}/` 数字域、模块名、文件编号规则照搬到另一个项目，worker 随后按错误路径写 RFC/SPEC/Design；用户需要多轮纠正目录和文件名。

**根因**：pipeline 是通用基础设施，但项目命名是局部约定。worker 不会自动推断目标项目的真实模块/skill 编号，也不一定读取 README。

**修复**：Intake 在派第一个文档任务前必须执行“项目约定发现与任务正文固化”：读取目标项目 docs README、模板、skills/module 目录和 config，并把精确交付路径写入 task body。

**预防**：文档类任务 body 必须给出完整示例，例如：

```text
交付物路径（严格按目标项目约定）：
- docs/rfc/<module-dir>/<RFC-file>.md
- docs/spec/<module-dir>/<SPEC-file>.md
示例：docs/rfc/16_travel/RFC-16-001-travel-planning-ability.md
```

示例只作为目标项目当前约定的展开，不得把某个项目的示例当成跨项目默认值。

### P-9: 中途变更骨架/命名规范时，orchestrator 负责 comment + 兜底搬迁

**症状**：用户在 T1/T2 已经启动后修正文档目录、文件名、模块编号或数据契约。worker 可能已经按旧规则写了一部分产物；如果只在聊天里确认，不通知 worker，后续阶段继续沿用旧规则。

**修复流程**：

```text
1. 立即用 kanban_comment 通知已创建/已 claim 的相关 task：新约定是什么、哪些路径作废。
2. 若 worker 已按旧路径写出产物，orchestrator 负责 mv/rename 兜底，不把纯路径搬迁退回给 worker 重做。
3. 下一阶段 body 顶部写“前置约定变更”，引用新路径和上一阶段修正说明。
4. 若变更会让已完成 RFC/SPEC/Design 内容不准确，触发“阶段决策同步门禁”，先补文档再派实现任务。
```

**预防**：Intake 第一次派任务前，尽量让用户确认“目录/文档命名规范”和“模块编号来源”；但一旦中途变更，状态同步责任在 orchestrator。

### P-10: 凭据/环境文件可能被工具链遮蔽，验证时看"是否真实可用"而不是看起来已写入

**症状**：worker 或 orchestrator 声称已写入 `.env` / config，但后续 API/Mongo/外部服务 auth 仍失败；文件里出现 `***`、占位字符串或被遮蔽值。

**根因**：Hermes 工具链和日志会保护 `*_PASSWORD`、`*_API_KEY`、`*_SECRET`、`*_TOKEN` 等敏感字段。某些写入/展示路径可能把真实值遮蔽成占位，导致"看起来写了，实际不可用"。

**修复**：

- 不在 skill、task metadata、kanban summary 中记录真实秘密。
- 写入凭据后，用最小泄露方式验证：只打印键名、长度、hash 前缀或直接调用目标服务 smoke test。
- auth 失败时，先检查"值是否仍是占位/遮蔽值"，再排查网络和代码。

**预防**：涉及凭据的实现任务，验收标准必须包含"真实连接 smoke test 或只泄露长度的配置读取测试"，不能只检查文件存在。

### P-12: Quick Flow orchestrator 串行创建导致断链

**症状**（2026-06-30 yinglong Travel Pipeline 案例，5h44m 卡死）：Quick Flow T1 done 01:05，T2 done 01:27，T3 出现时间 07:11（间隔 5h44m）。中间 dispatcher `_kanban_dispatcher_watcher` 静默死亡（gateway 主进程继续运行但不 tick），同时 orchestrator 主 session 处于 idle（state.db 0 新 turn）。两条故障叠加导致 T3 永远不会被创建。

**根因**：Quick Flow 原始设计是"前序 done 后由 orchestrator 临时 `kanban_create` 下一张"。这种 100% 依赖进程层的衔接机制在 dispatcher 失效 + orchestrator 不主动调度时**永久停转**——不是 dispatcher 单点，是**进程层全部失效**。

**修复（已落地）**：方案 A — Intake 阶段一次性预创建 T1-T4，T1 ready，T2/T3/T4 todo + parents。后续衔接交给 Kanban DB 状态机（`recompute_ready` + `dispatch_once`）。即便 dispatcher 死 N 小时，恢复后自动追平全部 task，不再依赖 orchestrator 主 session。详见 `references/quick-flow-handoff-mechanism.md` + RFC-10-004 V1.2 §12.6 / SPEC-10-004 V1.2 §13.10 / DESIGN-10-004 V1.2 §3.1 §3.7。

**预防**：
- orchestrator 在判定走 Quick Flow 时，**Intake 阶段必须**一次性 `kanban_create` 4 张 task
- 任一 task 在前序 done 后被临时 `kanban_create`（`task.created_at > parent.completed_at`）→ Closeout 记录 P-12 流程缺陷
- 三流程衔接机制对比：Full Flow 0 次进程层主动、Quick Flow **3 次进程层主动（V1.2 后归零）**、Light Flow 1 次

**与 P-5 的关系**：P-5 是 worker 误用 `review-required:` blocked；P-12 是流程架构层错误。前者补丁式 unblock 即可，后者必须改设计。

### P-27: `kanban_create(parents=[<id>])` 占位符不校验 parent_id 真实存在性 (2026-07-01 实测 + 2026-07-07 同日再犯)

**症状**：orchestrator Intake 阶段用占位符 parents 创建 4 张卡（如全部 `parents=[t1_id]`），期望"先创建 T1 done 后再 create T2/T3/T4"。但 `kanban_create(parents=[...])` **不校验 parent_id 是否真实存在**——所有占位符静默通过。T1 done 时 T2/T3/T4 全部 parents（仅含已存在的 T1_id）满足条件，**3 张 worker 同时被 dispatcher 派发**，T3/T4 看到未改动的代码自审全 FAIL。

**根因（两层）**：
1. **API 设计**：`kanban_create(parents=[...])` 是参数化接收，不强制 parent_id 已存在
2. **task_links 表**：只记录能 resolve 的 parent_id，不可解析的占位符**静默丢弃**

**真实后果（2026-07-07 P34 K合并案例 + 后续 partial-fallback Quick Flow 当日再犯）**：
- 4 task 全部 status=ready 后由 dispatcher 同时 claim/spawn
- T2 (Implement) 唯一可独立跑（基于已有资料）
- T3 (Verify) / T4 (Closeout) **必自我 block**（代码未改）
- 用户必须手动 orchestrator `kanban_block` + 后续 `kanban_link` 补 cascade + `kanban_unblock` 重 spawn

**修复 SOP（已沉淀到 MEMORY.md "P34" 段）**：
1. T3/T4 worker 必自我 block（如 t_c33f24b7 first attempt 的 `P-12 parent link bug` reason）
2. orchestrator 看到 block → 立刻执行：
   - `kanban_link(parent_id=t2_real, child_id=t3)`
   - `kanban_link(parent_id=t2_real, child_id=t4)`
   - `kanban_link(parent_id=t3_real, child_id=t4)`
   - `kanban_unblock(t3)` / `kanban_unblock(t4)`
3. dispatcher 自动重新 dispatch T3/T4 到 worker

**预防（双路径）**：
- **路径 A（推荐）**：Intake 阶段**串行 create 4 张卡**——先 `kanban_create(T1, parents=[])` 等返回 T1_id，再 `kanban_create(T2, parents=[T1_id])` 拿 T2_id，以此类推。**代价**：orchestrator 必须在线（如失联 T3/T4 不会自动派）。
- **路径 B（V1.2 标准）**：Intake 阶段一次性预创建 4 张卡 + 占位符 parents。**前提**：占位符 parent_id 会被静默丢弃，4 task 都默认 parent=T1（仅当 T1 是真的）。**危险**：如果 4 task 不依赖 T2/T3 真 id，全依赖 T1 done，则并发 spawn。T3/T4 必自我 block。

**判定**：当且仅当 T3/T4 真的不依赖中间 task 的产物（如本会话 partial-fallback Quick Flow，4 task 链清晰）时走**路径 A 串行 create**（已在本会话 P34 实战验证）。否则走**路径 B 占位符**（依赖 worker 自我 block + orchestrator unblock SOP）。

**历史教训（同一天犯两次）**：P34 K合并（2026-07-07 上午）+ partial-fallback（2026-07-07 下午）——同一日两次违反 P-27。已记入 MEMORY.md。orchestrator 下一次 Intake 必显式选 A/B 路径并写入 task body。

### P-11: 端到端 smoke test 必须包含"数据合理性校验"，不能只看 Phase 跑通（2026-06-29 应龙 Travel Pipeline 案例）

**症状**：Implement 阶段 worker 把 7 P0 全部产出代码、单测 223 passed、T3 → T4 → T5 都 done。但 orchestrator 直接跑端到端 smoke 时发现：**POI 数据返回了北京景点（故宫/雍和宫/天安门）给"舟山朱家尖 4 日亲子自驾"行程**，因为 POI 聚合没按 destination 过滤；**discovery 反向推荐返回 0 候选**，因为 fixture 过滤逻辑把 8 个目的地全过滤掉了。

**根因**：
- T3 Implement 验收标准只检查"代码可跑 + 测试通过"，**没检查 destination/POI/预算等业务字段是否合理**
- T4 Verify 同样只看测试 PASS，没做端到端 e2e 烟测
- T5 Review 只看 diff 与 SPEC 对齐，没真实跑一次用户场景

**修复**：
- T3 body 必须明确写验收标准包含**端到端 smoke test + 业务合理性 checklist**（如 "destination=舟山时 POI 必须是舟山真实景点，不允许返回北京/广州等地"）
- T4 Verify 必须实际跑一次端到端（init_trip → ... → render_final）并**抽样检查输出是否包含真实业务数据**
- T5 Review 不能只看 diff，**至少抽样读 1 个 final.md 看是否合理**

**预防**：任何"产出数据"的 Pipeline，验收标准必须包含"用真实用户输入跑一次 + 人工或脚本检查输出合理性"。特别是 travel/search/recommend 类任务，光看代码和单测不够。

**真实证据**：`data/memory/16_travel_pipeline-smoke-2026-06-29.md`（yinglong 项目）
## Quick Flow 5 阶段流程模式（2026-06-29 新增 —— 已被 2026-06-30 V1.2 改造取代）

> ⚠️ **历史快照**：本节是 2026-06-29 首次落地 Quick Flow 时的实现日志，**当前流程规则已由 2026-06-30 V1.2 改造取代**：① Intake 必须一次性预创建 T1-T4 全部（不是串行）；② parent links 全链 `[T1]/[T1,T2]/[T1,T2,T3]`（不是简化版 `[T1]/[T2]/[T3]`）；③ Closeout 自审清单 13 → **15 项**（含 #1/#2 Intake 预创建核验）；④ 适用 pitfall P-1~P-11 → **P-1~P-12**（含 V1.2 新增的 P-12 orchestrator 串行调度风险）。本节保留作为历史参考，**不要**当当前规则使用。

> 完整 RFC/SPEC/Design 文档：RFC-10-004 §12 / SPEC-10-004 §13 / DESIGN-10-004（yquant 项目 `docs/` 下 V1.2 版本为准）

**5 阶段 4 task Kanban 链（历史版本，仅供参考）**：
```
T1 RFC/SPEC/Design   (yquantprincipal)   ← 1 task 产 3 份独立文档
T2 Implement         (yquantdeveloper)   parents=[T1]
T3 Verify            (yquanttester)      parents=[T2]
T4 Closeout          (orchestrator)      parents=[T3]
```

**适用边界**：中等风险、明确需求、改动 3-8 文件、单模块、不触交易/风控

**与 Full / Light 区别（历史）**：
- Full Flow (7 阶段 / 6 task)：高风险、跨模块、交易/风控 → 保留独立 Review
- **Quick Flow (5 阶段 / 4 task)**：中风险 → 去掉 Review，以 **Closeout 自审清单 (13 项 → V1.2 已扩 15 项)** 替代
- Light Flow (3 阶段 / 2 task)：单文件低风险 bug fix / 注释 / 格式

**Quick→Full 升级路径**：
- T1 RFC/SPEC/Design 阶段发现改动实际跨模块 → 把 T2 后面的 task 改成 Full 链
- T2 Implement 阶段发现触动交易/风控逻辑 → 升级到 Full Flow 补 Review 阶段
- Orchestrator 应在 T2 任务 body 显式声明升级条件

**失败模式**（Orchestrator 监控信号）：
- T1 done 后 T2 一直 ready 未 claim → 父任务检查失败
- T2 done 后 T3 一直 ready 未 claim → 同上
- 任何 task done 通知到达但 children 24h 内未 promote → 主动 unblock + 记录事件
- T3 Verify 发现 P-11 端到端数据不合理 → 升级到 Full Flow 重新跑

**P-1~P-13 pitfalls 全部适用于 Quick Flow**（2026-07-01 实测新增 P-1c worker profile `external_dirs` 必须覆盖目标项目 skills 目录）

## 参考资料

- `references/pipeline.md`：阶段门禁、任务目录结构、路由规则。
- `references/document-layers.md`：RFC/SPEC/DESIGN 的职责边界。
- `references/agent-handoff.md`：角色交接内容、交付物和退回条件。
- `references/hermes-kanban-orchestration.md`：Hermes Kanban profile worker 编排规则。
- `references/quick-flow-journal-2026-06-29.md`：**Quick Flow 实施实跑日志**（含 T1-T4 task IDs、产物、关键教训）。
- `references/quick-flow-handoff-mechanism.md`：**Quick Flow 衔接机制 class-level 参考**（三流程根因分类 + 故障源可达性矩阵 + 方案 A 落地 + Q-LINK 契约 + P-12 pitfall + yinglong 5h44m 卡死复盘）。orchestrator 判定走 Quick Flow 时必须先读。
- **P-1c 复盘（2026-07-01 yinglong 5 阶段 4 task 实跑）**：worker profile `external_dirs` 不覆盖目标项目 skills 目录时，进程静默 SIGKILL、P-1b 风格的 `Unknown skill` 异常被 hermes_cli 静默吞掉。详见本 SKILL.md §P-1c 段。
- `references/spec-from-rfc.md`：**SPEC 阶段专用编写手册**——从 RFC 派生 SPEC 时的决策→契约映射模式、12 节章节清单、7 类陷阱（含「不改动清单 P-2」「硬编码版本号 P-3」「向后兼容 P-4」「混淆 SPEC/Design 边界 P-7」）、验证清单与完成回报模板。
- `skills/common/utils/print_agent_models.py`：查看所有 Agent 当前模型/fallback/compression 配置。
- `references/real-run-journal-2026-06-25.md`：**实跑日志**——2026-06-25 RFC-03-006 流水线从中断点 Design → Implement 推进的真实时序、模型 fallback 观察、worker crash 复盘。Read this before deploying the pipeline for the first time.
