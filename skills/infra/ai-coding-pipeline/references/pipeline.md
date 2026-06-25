# YQuant AI Coding 流水线参考

## 阶段总览

| 阶段 | 角色 | Hermes assignee profile | 产出 | 是否允许改代码 |
|---|---|---|---|---|
| 1 Intake | YQuant | `yquant` | `00-intake.md` 或简短需求澄清摘要 | 否 |
| 2 RFC/SPEC | YQuant-Codex-Principal | `yquantprincipal` | RFC 更新、`docs/spec/*.md` 或 `02-spec.md` | 通常否 |
| 3 Design | YQuant-Codex-Principal | `yquantprincipal` | `docs/design/*.md`、`03-design.md`、`04-implementation-plan.md` | 否 |
| 4 Implement | YQuant-Developer-Engineer | `yquantdeveloper` | 代码变更、实现记录 | 是 |
| 5 Verify | YQuant-Test-Engineer | `yquanttester` | 测试、`05-test-report.md` | 仅测试/夹具 |
| 6 Review | YQuant-Reviewer-Principal | `yquantreviewer` | `06-review.md` 或审查意见 | 否 |
| 7 Closeout | YQuant | `yquant` | `07-closeout.md`、面向用户的交付摘要 | 否 |

> 查看每个 Agent 当前真实的主模型、fallback 链、compression 配置：
> ```bash
> python3 skills/common/utils/print_agent_models.py
> ```
> 升级模型时**只改 `config.yaml`**，本 skill 不需要同步。

## 任务目录

非平凡工程任务的运行记录属于过程性数据，优先由 Hermes Kanban task/comment/run 保存。需要项目内可读归档时，放在 `data/tasks/` 下：

```text
data/tasks/active/YYYY-MM-DD-short-name/
  00-intake.md
  01-rfc-link.md
  02-spec.md
  03-design.md
  04-implementation-plan.md
  05-test-report.md
  06-review.md
  07-closeout.md
```

模板放在：

```text
data/tasks/templates/ai-coding-pipeline-run.md
```

完成后移动到 `data/tasks/done/`。小型机械修改可以跳过任务目录，但最终输出仍必须包含验证说明。

## 触发分级

### 完整流水线

用户明确要求 AI Coding Pipeline、RFC/SPEC/Design/Implement/Verify/Review/Closeout、先设计后实现、独立测试或独立审查时，直接进入完整流水线。

任务满足以下条件之一但用户未显式要求时，YQuant 先向用户确认是否走完整流水线：

- 新增核心功能。
- 对现有功能做非平凡改进、优化、重构、升级。
- 修改架构、数据模型、任务调度、报告生成、投资研究、交易相关逻辑。
- 跨多个模块或多个目录的改动。
- 需要新增或修改 RFC、SPEC、Design 文档。
- 存在较高风险，例如数据正确性、回测结果、外部 API、生产脚本、自动化执行。
- 用户要求方案评审、架构设计、独立 review 或测试验证。

### 轻量流程

以下任务默认使用轻量流程，除非用户明确要求完整流水线：

- 文案、注释、README 小改动。
- 对已有功能的小问题修复。
- 不涉及 RFC/SPEC/Design 变更的优化。
- 单文件低风险 bug fix。
- 格式化、路径修正、模板补充。

轻量流程固定为：

```text
YQuant Intake
-> YQuant-Developer-Engineer Implement
-> YQuant-Test-Engineer Verify
-> YQuant Closeout
```

轻量流程可以不创建任务目录，但必须保留最小 Verify，并在 Closeout 中说明验证结果或无法验证的原因。

## 阶段门禁

### Intake
- 输入：用户需求、项目上下文。
- 输出：目标、非目标、约束、风险、开放问题、验收标准。
- 通过条件：范围足够清楚，可以进入 RFC/SPEC。
- 退回条件：核心目标、数据源、权限、交易/风控含义或生产影响不清楚。

### RFC/SPEC
- 输入：Intake 结果和相关 `docs/rfc`。
- 输出：必要的 RFC 更新和可执行 SPEC。
- 通过条件：每条需求都有可测试的验收标准。
- 退回条件：RFC 与系统约束冲突，或验收标准不可测试。

### Design
- 输入：RFC/SPEC 和现有代码结构。
- 输出：涉及文件/模块、实现顺序、测试计划、回滚/降级方案。
- 通过条件：实现者无需自行发明架构即可执行。
- 退回条件：新增依赖、Schema 变更、外部接口变更或交易/风控语义变更未获确认。

### Implement
- 输入：SPEC、DESIGN、实现计划。
- 输出：最小范围代码与测试变更。
- 通过条件：实现覆盖计划，且没有无关重构。
- 退回条件：计划缺口导致需要扩大范围，或本地验证无法继续。

### Verify
- 输入：代码变更和验收标准。
- 输出：测试报告，包含命令、结果、覆盖范围和缺口。
- 通过条件：关键测试通过，失败项有明确处置。
- 退回条件：核心验收失败，或环境阻塞且没有替代证明。
- 边界：默认只做验证和测试相关补充，不修改业务实现；如需修复实现，退回 Implement。

### Review
- 输入：diff、RFC/SPEC/DESIGN、测试报告。
- 输出：按严重程度排序的审查意见。
- 通过条件：无阻塞问题；残余风险已明确说明。
- 退回条件：实现偏离 SPEC、关键测试缺口、安全/可靠性/交易/风控问题。
- 边界：高严重度或阻塞问题必须退回 Implement；低严重度问题由 YQuant 判断是否继续 Closeout。

### Closeout
- 输入：实现结果、验证结果、审查结论。
- 输出：面向用户的摘要、验证说明、风险和后续事项。
- 通过条件：用户能清楚知道改了什么、如何验证、还剩什么风险。

## 路由规则

- RFC/SPEC/Design/架构/API/数据模型：Kanban `assignee="yquantprincipal"`
- 代码实现：Kanban `assignee="yquantdeveloper"`
- 测试验证：Kanban `assignee="yquanttester"`
- 独立审查：Kanban `assignee="yquantreviewer"`
- Intake 和 Closeout：`YQuant` 主 profile 自己完成

## Hermes Kanban 执行规则

- 正式流水线阶段必须用 `kanban_create` 创建任务，而不是 `delegate_task`。
- 每个任务必须设置 `workspace_kind="dir"` 和 `workspace_path="/home/pascal/workspace/yquant-investment"`。
- 有前置阶段时必须在创建子任务时设置 `parents=[...]`，不要只在正文里写“等待某任务完成”。
- 创建后必须记录返回的 task id；没有 task id 就视为没有真实委派。
- 如果 gateway 没有运行，ready task 不会自动执行；先启动或恢复 Hermes gateway。
- `delegate_task` 可用于短推理、并行代码阅读等临时子任务，但不得替代 profile worker 角色切换。
