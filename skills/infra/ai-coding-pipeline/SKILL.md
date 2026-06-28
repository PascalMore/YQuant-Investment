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

## 编排顺序

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

## Orchestrator 主动推进规则（2026-06-28 新增）

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

### P-10: 凭据/环境文件可能被工具链遮蔽，验证时看“是否真实可用”而不是看起来已写入

**症状**：worker 或 orchestrator 声称已写入 `.env` / config，但后续 API/Mongo/外部服务 auth 仍失败；文件里出现 `***`、占位字符串或被遮蔽值。

**根因**：Hermes 工具链和日志会保护 `*_PASSWORD`、`*_API_KEY`、`*_SECRET`、`*_TOKEN` 等敏感字段。某些写入/展示路径可能把真实值遮蔽成占位，导致“看起来写了，实际不可用”。

**修复**：
- 不在 skill、task metadata、kanban summary 中记录真实秘密。
- 写入凭据后，用最小泄露方式验证：只打印键名、长度、hash 前缀或直接调用目标服务 smoke test。
- auth 失败时，先检查“值是否仍是占位/遮蔽值”，再排查网络和代码。

**预防**：涉及凭据的实现任务，验收标准必须包含“真实连接 smoke test 或只泄露长度的配置读取测试”，不能只检查文件存在。

## 参考资料

- `references/pipeline.md`：阶段门禁、任务目录结构、路由规则。
- `references/document-layers.md`：RFC/SPEC/DESIGN 的职责边界。
- `references/agent-handoff.md`：角色交接内容、交付物和退回条件。
- `references/hermes-kanban-orchestration.md`：Hermes Kanban profile worker 编排规则。
- `references/spec-from-rfc.md`：**SPEC 阶段专用编写手册**——从 RFC 派生 SPEC 时的决策→契约映射模式、12 节章节清单、7 类陷阱（含「不改动清单 P-2」「硬编码版本号 P-3」「向后兼容 P-4」「混淆 SPEC/Design 边界 P-7」）、验证清单与完成回报模板。
- `skills/common/utils/print_agent_models.py`：查看所有 Agent 当前模型/fallback/compression 配置。
- `references/real-run-journal-2026-06-25.md`：**实跑日志**——2026-06-25 RFC-03-006 流水线从中断点 Design → Implement 推进的真实时序、模型 fallback 观察、worker crash 复盘。Read this before deploying the pipeline for the first time.
