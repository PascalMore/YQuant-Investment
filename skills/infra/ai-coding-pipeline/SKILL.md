---
name: yquant-ai-coding-pipeline
description: "用于 YQuant 非平凡工程任务的七阶段 AI Coding 流水线：Intake、RFC/SPEC、Design、Implement、Verify、Review、Closeout。"
---

# YQuant AI Coding 流水线

用于 YQuant 的非平凡工程任务，尤其是涉及 RFC/SPEC、设计、代码变更、测试、审查、发布准备、数据模型、API、交易、风控或生产行为的任务。

除非用户明确要求走流水线，否则普通问答、极小拼写修正、只读查询不需要触发本 skill。

## Hermes 执行模型

YQuant 在 Hermes 中使用 **Kanban profile worker** 执行 AI Coding 流水线。

- 本 skill 的源代码、参考文档和维护入口在项目内：`/home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/`。
- `~/.hermes/profiles/*/skills/infra/yquant-ai-coding-pipeline/` 是运行态安装副本，只用于 Hermes profile 加载；长期修改必须先落到项目源目录，再同步到 Hermes profiles。
- 运行态 profile 的模型、fallback、toolsets 等易变配置仍以 `~/.hermes/profiles/<profile>/config.yaml` 为准，项目内只保存路由语义、阶段门禁和可复用 skill 逻辑。
- `YQuant` 是 orchestrator，负责 Intake、创建 Kanban 任务、校验阶段门禁和 Closeout。
- 阶段执行必须通过 `kanban_create` 创建真实任务，并设置 `assignee` 为对应 Hermes profile。
- 不要用 `delegate_task` 承担正式流水线阶段；`delegate_task` 只适合短推理子任务，且默认继承父 profile 的模型，不能按单次调用切到 `yquantprincipal` / `yquantdeveloper` 等 profile。
- 不要只在文本中声明“委派给某 Agent”；没有 `kanban_create` 任务就不算真实委派。
- 任务工作目录必须使用共享项目目录：`workspace_kind="dir"`，`workspace_path="/home/pascal/workspace/yquant-investment"`。

### Hermes Profile 路由

| 阶段 | Hermes assignee profile | 职责 |
|------|--------------------------|------|
| Intake / Closeout | `yquant` | 需求澄清、编排、阶段门禁、最终交付 |
| RFC / SPEC / Design | `yquantprincipal` | RFC/SPEC/Design、架构、接口、数据模型、风险评估 |
| Implement | `yquantdeveloper` | 按已确认 SPEC/DESIGN 做最小范围实现 |
| Verify | `yquanttester` | 独立验证、测试报告、残余风险 |
| Review | `yquantreviewer` | 独立代码审查、风险审查、通过/退回决定 |

### 源目录与运行态同步

修改 AI Coding Pipeline 时，先改项目源目录，再同步到 Hermes profile 运行态：

```bash
for p in yquant yquantprincipal yquantdeveloper yquanttester yquantreviewer; do
  mkdir -p "/home/pascal/.hermes/profiles/$p/skills/infra/yquant-ai-coding-pipeline"
  cp -a /home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/. \
    "/home/pascal/.hermes/profiles/$p/skills/infra/yquant-ai-coding-pipeline/"
done
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

YQuant 创建任务后必须向用户说明任务图、任务 ID、assignee、依赖关系和如何追踪状态。

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

`YQuant Intake -> YQuant-Developer-Engineer Implement -> YQuant-Test-Engineer Verify -> YQuant Closeout`

轻量流程仍必须保留最小 Verify，不能把未验证的实现直接 Closeout。

## 编排顺序

完整流水线固定为：

1. `YQuant`：Intake 需求澄清，确认目标、范围、约束、风险和初步验收标准。
2. `YQuant-Codex-Principal`：RFC/SPEC 编写；当业务语义、接口、数据模型、交易或风控行为发生变化时，先更新相关 RFC，再派生可执行 SPEC。
   - **门禁**：YQuant 在此阶段结束后必须校验 `docs/rfc/` 和 `docs/spec/` 下有对应文件，否则退回。
3. `YQuant-Codex-Principal`：Design 架构设计、详细设计、原型或 UI 设计；定义涉及文件/模块、数据流/控制流、实现顺序、测试、回滚和交接条件。
   - **门禁**：YQuant 在此阶段结束后必须校验 `docs/design/` 下有对应文件，否则退回。
4. `YQuant-Developer-Engineer`：Implement 代码实现，基于已确认的 SPEC/DESIGN 做最小范围修改。
5. `YQuant-Test-Engineer`：Verify 测试验证，按验收标准独立测试。
6. `YQuant-Reviewer-Principal`：Review 独立审查 diff、测试结果，以及实现与 RFC/SPEC/DESIGN 的一致性。
7. `YQuant`：Closeout 收尾，总结变更、验证结果、残余风险和后续事项。

除非用户明确要求跳过某一步，否则完整流水线不得跳过 Verify 和 Review。

### 三层文档强制规则

RFC、SPEC、Design **必须分别产出独立文件**，存放在各自目录下。不允许将 SPEC 或 Design 内容合并到 RFC 中。详细门禁校验规则见 `references/document-layers.md`。

## 强制角色拆分

| 阶段 | Agent | Profile 配置 |
|------|-------|--------------|
| Intake / Closeout | YQuant | `~/.hermes/profiles/yquant/config.yaml` |
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

开始流水线前，YQuant 必须确认：

- 当前 `yquant` profile 已启用 `kanban` toolset。
- Hermes gateway 正在运行；否则 Kanban ready task 不会自动派发。
- 目标 assignee profile 存在：`yquantprincipal`、`yquantdeveloper`、`yquanttester`、`yquantreviewer`。
- `~/.hermes/kanban.db` 能记录任务；若任务没有进入 `tasks` 表，说明没有真实委派。

验证命令：

```bash
python3 skills/common/utils/print_agent_models.py
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect('/home/pascal/.hermes/kanban.db')
print(conn.execute('select count(*) from tasks').fetchone()[0])
PY
```

## 参考资料

- `references/pipeline.md`：阶段门禁、任务目录结构、路由规则。
- `references/document-layers.md`：RFC/SPEC/DESIGN 的职责边界。
- `references/agent-handoff.md`：角色交接内容、交付物和退回条件。
- `references/hermes-kanban-orchestration.md`：Hermes Kanban profile worker 编排规则。
- `references/spec-from-rfc.md`：**SPEC 阶段专用编写手册**——从 RFC 派生 SPEC 时的决策→契约映射模式、12 节章节清单、7 类陷阱（含「不改动清单 P-2」「硬编码版本号 P-3」「向后兼容 P-4」「混淆 SPEC/Design 边界 P-7」）、验证清单与完成回报模板。
- `skills/common/utils/print_agent_models.py`：查看所有 Agent 当前模型/fallback/compression 配置。
