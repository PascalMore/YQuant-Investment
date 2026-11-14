# AI Coding 流水线参考（YQuant / 应龙共享）

现行规则自 2026-11-14 起仅用于后续新任务，旧链按原契约执行、不自动迁移。只有 Full / Light；Quick 入口与专用要求退役。原 Quick 需求按契约明确程度和风险去往 Light 或 Full，不按文件数量分流。

## 阶段总览

| 阶段 | 角色 | Hermes assignee profile | 产出 | 是否允许改代码 |
|---|---|---|---|---|
| 1 Intake | Orchestrator | `yquant` 或 `yinglong`，不另建默认卡 | 明确范围、契约、授权、验收与分流 | 否 |
| 2 RFC/SPEC（Full） | YQuant-Codex-Principal | `yquantprincipal` | 独立 RFC 与 SPEC 文件 | 通常否 |
| 3 Design（Full） | YQuant-Codex-Principal | `yquantprincipal` | 独立 Design 文件 | 否 |
| 4 Implement | YQuant-Developer-Engineer | `yquantdeveloper` | 代码变更、实现记录 | 是 |
| 5 Validate | YQuant-Reviewer-Principal | `yquantreviewer` | 必要测试、消费者/反例审查、验收裁定 | 不改业务实现后自签 |
| 6 Closeout | Orchestrator | 与 Intake 相同，不另建默认卡 | 面向用户的交付摘要 | 否 |

Full：Intake → RFC/SPEC → Design → Implement → Validate → Closeout（四张默认 worker 卡）。Light：Intake → Implement → Validate → Closeout（两张）。`yquanttester` 保留旧任务兼容与必要测试专项，不是默认阶段。

> 查看每个 Agent 当前真实的主模型、fallback 链、compression 配置：
> ```bash
> python3 skills/common/utils/print_agent_models.py
> ```
> 升级模型时**只改 `config.yaml`**，本 skill 不需要同步。

## 任务目录

Kanban 是唯一任务状态源；不强制 pipeline-state.md、任务 body 镜像、逐阶段全文 handoff 或重复 Closeout 报告。小任务只需 Kanban 结论与必要日志；复杂任务保留一份验收报告及原始证据。项目需要过程资料时沿用 `data/tasks/active/YYYY-MM-DD-short-name/`，完成后整体归入 `done/`；结果报告使用 `data/reports/YYYY-MM-DD-short-topic/report.md`。不为仪式新增文件，其他项目遵循自己的 AGENTS。

## 触发分级

### 完整流水线

用户明确要求完整流水线、先 RFC/SPEC/Design 再实现时进入 Full；独立测试与审查由统一 Validate 承担，不再据此拆出两个默认阶段。具体启用按根 AGENTS 与 SKILL 的触发规则。

任务满足以下条件之一但用户未显式要求时，orchestrator 先向用户确认是否走完整流水线：

- 新增核心功能。
- 对现有功能做非平凡改进、优化、重构、升级。
- 修改架构、数据模型、任务调度、报告生成、投资研究、交易相关逻辑。
- 跨多个模块或多个目录的改动。
- 需要新增或修改 RFC、SPEC、Design 文档。
- 存在较高风险，例如数据正确性、回测结果、外部 API、生产脚本、自动化执行。
- 用户要求方案评审、架构设计、独立 review 或测试验证。

### 轻量流程

以下任务默认使用轻量流程，除非用户明确要求完整流水线：

总判据是行为、范围、既有契约和验收已明确且风险可控；下列只是示例，不限单文件。不满足则走 Full，不能靠文件数机械划档。

- 文案、注释、README 小改动。
- 对已有功能的小问题修复。
- 不涉及 RFC/SPEC/Design 变更的优化。
- 单文件低风险 bug fix。
- 格式化、路径修正、模板补充。

轻量流程固定为：

```text
Orchestrator Intake
-> YQuant-Developer-Engineer Implement
-> YQuant-Reviewer-Principal Validate
-> Orchestrator Closeout
```

轻量流程可以不创建任务目录，但必须保留独立 Validate，并在 Kanban 结论说明实际验证结果与缺口。

## 阶段门禁

### Intake
- 输入：用户需求、项目上下文。
- 输出：目标、非目标、约束、风险、开放问题、验收标准。
- 通过条件：明确分流；Full 进入 RFC/SPEC，契约明确且风险可控的 Light 直接进入 Implement。
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
- 输入：Full 的 SPEC/Design；Light 的已确认契约、范围与验收 body。
- 输出：最小范围代码与测试变更。
- 通过条件：实现覆盖计划，且没有无关重构。
- 退回条件：计划缺口导致需要扩大范围，或本地验证无法继续。

### Validate（Full / Light 共用）
- 输入：最终候选 diff、验收契约、开发者自测证据；Full 另核对三份文档完整性与一致性。
- 执行：按影响运行必要实际测试，审查真实消费者、异常/边界/反例、数据合理性、范围归属和授权边界。开发者自测不替代独立验收；具体规则只维护在 [SKILL 统一 Validate](../SKILL.md)。
- 输出：PASS / REVISE、file:line 或行为证据、候选身份（HEAD + 文件清单或 hash）、命令/exit、覆盖与缺口；复杂任务仅一份验收报告及原始证据。
- 通过条件：必需验收实际满足、无阻塞缺陷或未取得的必要授权；未运行不称 PASS。
- 退回条件：偏离契约、真实路径/数据不合理、必需测试缺口、安全/可靠性问题。退回 Implement 最小修复，不改业务实现后自签。
- 复用：既有独立证据只有候选/输入/依赖/条件仍适用才复用；候选变化补跑受影响部分。不因整理日志/报告重复跑，主控不第三遍全量跑。
- 中断：先核对落盘与证据；只缺登记则补登记，未验证则明确缺口再续接。

### Closeout
- 输入：实现结果、验证结果、审查结论。
- 输出：面向用户的摘要、验证说明、风险和后续事项。
- 通过条件：用户能清楚知道改了什么、如何验证、还剩什么风险。

历史：[Quick Flow 阶段参考](history/pipeline-quick-flow-legacy.md) 已退役，仅供审计，非当前指令、无新任务必读要求。

## 路由规则

- RFC/SPEC/Design/架构/API/数据模型：Kanban `assignee="yquantprincipal"`
- 代码实现：Kanban `assignee="yquantdeveloper"`
- 独立验收 Validate（测试验证＋消费者/反例审查＋裁定）：Kanban `assignee="yquantreviewer"`
- 旧任务兼容/必要测试专项（非默认）：Kanban `assignee="yquanttester"`
- Intake 和 Closeout：当前 orchestrator（`yquant` 或 `yinglong`）完成

## Hermes Kanban 执行规则

- 正式流水线阶段必须用 `kanban_create` 创建任务，而不是 `delegate_task`。
- Intake 根据 orchestrator 解析 `PIPELINE_WORKSPACE`：`yquant` 对应 `/home/pascal/workspace/yquant-investment`，`yinglong` 对应 `/home/pascal/workspace/yq-yinglong`。
- 每个任务必须设置 `workspace_kind="dir"` 和解析后的绝对 `workspace_path=PIPELINE_WORKSPACE`。
- 有前置阶段时必须在创建子任务时设置 `parents=[...]`，不要只在正文里写“等待某任务完成”。
- 依次取得真实 id 再创建下游，禁止占位 parent；在 Intake 内完成依赖预建，不必等上游 done。阶段通过且有下游时 complete，不因存在下游 block，不盲目定时 unblock。
- 创建后必须记录返回的 task id；没有 task id 就视为没有真实委派。
- 如果 gateway 没运行，ready task 不会自动执行；记录环境阻塞，由具备明确授权的主控/operator 恢复，不自行重启或绕过拒绝。
- `delegate_task` 可用于短推理、并行代码阅读等临时子任务，但不得替代 profile worker 角色切换。
