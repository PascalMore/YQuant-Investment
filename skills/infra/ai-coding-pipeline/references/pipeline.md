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

## 历史：Quick Flow（全节退役，非当前指令）

<details>
<summary>保留 V1.2 Quick 规则用于解释旧任务</summary>

以下至 details 结束的 Quick 入口、Q-LINK、强制自审及旧 Full/Light 对比全部退役，不用于新任务。现行只看上方阶段总览和统一 Validate，不执行旧操作配方。

Quick Flow 曾是中等流程模式（5 阶段 4 task）；以下记录当时定义。

### Quick Flow Kanban 任务链

任务链**创建时机**：Intake 阶段由 orchestrator 一次性预创建 T1/T2/T3/T4，T1 `ready`、T2/T3/T4 `todo` + parent links。后续衔接由 Kanban DB 状态机接管，与 Full Flow 同源。

```text
T1 RFC/SPEC/Design   assignee=yquantprincipal  status=ready    parents=[]           创建时机：Intake
T2 Implement         assignee=yquantdeveloper  status=todo     parents=[T1]        创建时机：Intake
T3 Verify            assignee=yquanttester     status=todo     parents=[T1, T2]    创建时机：Intake（最低 parents=[T2]）
T4 Closeout          assignee=<orchestrator>   status=todo     parents=[T1, T2, T3] 创建时机：Intake（最低 parents=[T3]）
```

T1 done → dispatcher `recompute_ready` promote T2 → ... → T4。每个 task 的初始 status 与 parent 详见 SPEC-10-004 §13.1 / §13.10。

### Quick Flow 衔接机制（Q-LINK 契约）

Quick Flow 的阶段衔接必须满足以下契约（来源 SPEC-10-004 §13.10，V1.2 起强制）：

| 编号 | 契约 | 必须 / 禁止 | 验证方式 |
|---|---|---|---|
| Q-LINK-001 | Intake 一次性创建 T1/T2/T3/T4 | 必须 | `kanban_show` / task thread 中可见 4 个 task id；T2/T3/T4 `created_at` 应接近 T1 |
| Q-LINK-002 | T1 初始可调度 | 必须 | T1 status=`ready` 或已被 claim 为 `running` |
| Q-LINK-003 | T2/T3/T4 初始不可调度 | 必须 | T2/T3/T4 status=`todo` 且存在 parent links |
| Q-LINK-004 | 后续 promote 由 Kanban DB 状态机完成 | 必须 | 前序 done 后无需新建 task，只发生 `todo→ready→running` 状态变化 |
| Q-LINK-005 | 前序 done 后临时创建下一张 task | 禁止 | 若 task `created_at` 晚于 parent `completed_at`，Closeout 记录流程缺陷 |
| Q-LINK-006 | orchestrator 主 session / watcher 是唯一衔接机制 | 禁止 | 任何通知丢失不得导致"下一张 task 不存在" |

### Quick Flow 与 Full Flow 同源度

Quick Flow 与 Full Flow 共享同一套 Kanban 衔接机制：`recompute_ready`（parent done 后自动 promote 子 task）+ `dispatch_once`（每个 ready task 只 spawn 一次）。Quick Flow 去掉的只是 Design 独立 task 和 Review 独立 task；衔接状态机和 parent links 完全一致。Light Flow 也建议采用 Intake 一次性预创建 Implement→Verify（task 数更少，断链风险低一个数量级但仍存在）。

### Quick Flow 适用边界

**适用**：中风险 + 明确需求 + 改动 3-8 文件 + 单模块 + 不触交易/风控 + 不改三方依赖。
**禁止**：MongoDB 生产写入、交易/风控逻辑、跨 2+ 模块架构、用户明确要独立 Review、凭据相关+真实 API smoke。

完整决策树与升级路径详见 `SKILL.md` 的 "## Quick Flow 触发条件" 章节。

### Quick Flow 阶段门禁

#### T1 RFC/SPEC/Design（orchestrator 校验）

- 三份文档均存在：`docs/rfc/{module}/RFC-*.md`、`docs/spec/{module}/SPEC-*.md`、`docs/design/{module}/DESIGN-*.md`。
- 三份文档的章节结构完整（RFC 元数据/执行摘要/背景/目标/设计/风险/验收/参考资料；SPEC 元数据/需求摘要/范围/功能规格/数据契约/配置/测试/验收；Design 元数据/设计摘要/现状/方案/实现计划/测试/风险/交接）。
- 引用关系正确（RFC → SPEC → Design 交叉引用 grep 通过）。
- T1 body 顶部显式声明"本任务走 Quick Flow"。

#### T2 Implement（developer 自检 + tester 验证）

- 代码编译/语法通过。
- 单元测试通过。
- 文件改动范围在 Design §3.1 预期内（`git diff --stat` 对比）。
- 未修改禁止清单中的文件（3 个模板、其他模块代码、其他项目）。
- 端到端 smoke test 通过（业务数据合理性抽样）。

#### T3 Verify（tester 报告）

- 验收标准（SPEC §10 + RFC §9）全部通过。
- 测试命令与断言列表执行通过。
- 端到端 smoke test 步骤全部通过，**含数据合理性抽样**（P-11）。
- 残余风险列表已记录。

#### T4 Closeout（orchestrator 逐项执行）

见下方 "Quick Flow Closeout 自审清单（**15 项**）"——以 DESIGN-10-004 §3.5 为单一事实源，与 SKILL.md Quick Flow 阶段门禁一致。

### Quick Flow Closeout 自审清单（**15 项**）

T4 Closeout 由 orchestrator 执行。由于 Quick Flow 无独立 Reviewer，orchestrator 必须逐项核查以下清单，每项标注 ✅ 通过 / ❌ 未通过。**15 项全部 ✅ 才允许 closeout**。

| # | 检查项 | 检查方法 |
|---|---|---|
| 1 | **Quick Flow T1-T4 在 Intake 阶段一次性预创建**（Q-LINK-001 / Q-LINK-002） | `kanban_show` / task thread / created_at 复核 |
| 2 | **T2/T3/T4 初始 todo + 完整 parent links**（Q-LINK-003） | `kanban_show` parent field 复核 |
| 3 | SPEC 契约与实际实现一致 | 对比 SPEC §3/§4 与 `git diff` |
| 4 | 文件改动清单符合 Design §3.1 预期 | `git diff --stat` 对比 Design |
| 5 | 验收标准（RFC §9 + SPEC §10）全部通过 | T3 测试报告复核 |
| 6 | 风险应对（RFC §7）已验证或降级可接受 | 逐条复核 RFC §7 风险表 |
| 7 | 代码风格和项目约定遵守 | 抽查 2-3 个变更文件 |
| 8 | 测试覆盖满足 Design §5 要求 | T3 测试报告覆盖率核对 |
| 9 | 无遗漏的边缘情况或异常降级路径 | 抽样检查 edge case |
| 10 | 三方依赖无新增/升级，或已记录 | `git diff` 依赖文件 |
| 11 | 文档引用关系正确（RFC → SPEC → Design → 实现） | 交叉引用 grep |
| 12 | Git diff 范围在产品边界内，不包含无关改动 | `git diff --stat` + 人工复核 |
| 13 | worker 日志无异常（fallback、crash、timeout） | 检查 `~/.hermes/profiles/*/logs/agent.log` |
| 14 | 未修改禁止清单中的文件 | `git diff --name-only` 交叉检查 |
| 15 | 未修改文档模板 | `git diff docs/*/00_*template*` |

**注**：本清单相对 V1.1 多了 2 项（#1/#2）以核验 V1.2 新引入的 Intake 一次性预创建契约（Q-LINK-001~006）。如果某些 Check Flow 不含 Q-LINK 契约（极少见），可以跳过 #1/#2 并在 closeout 报告里说明。

**结果处置**：
- 15 项全部 ✅ → closeout 完成。
- 发现 Major/High 问题 → 退回 T2，不 closeout。
- Minor 问题（文档遗漏、命名建议）→ orchestrator 直接修，closeout 记录。

### Quick Flow 与 Full Flow / Light Flow 的差异

| 维度 | Full Flow | Quick Flow | Light Flow |
|---|---|---|---|
| 阶段数 | 7 | 5 | 4 |
| Kanban task 数 | 6 | 4 | 2 |
| RFC/SPEC/Design 分几个 task | 2（RFC/SPEC + Design） | 1（三份合并产出） | 0（无 RFC/SPEC/Design） |
| 独立 Reviewer | 是 | 否（Closeout 自审替代） | 否 |
| 端到端 smoke test 数据合理性 | 必须 | 必须（P-11） | 不强制 |
| 触发的失败模式监控点 | **P-1~P-12 全集** | **P-1~P-12 全集**（DESIGN-10-004 §3.7；含 P-12 orchestrator 串行调度） | 只监控 P-1 / P-2 / P-5 |

### Cross-reference

- SKILL.md：`## 编排顺序：Full Flow` / `## 三流程定位（Full / Quick / Light）` / `## 编排顺序：Quick Flow` / `## Quick Flow 触发条件` / `## Quick Flow 阶段门禁`
- RFC：`docs/rfc/10_infra/RFC-10-004-yquant-ai-coding-pipeline-skill-sync.md` §12（Quick Flow 扩展）
- SPEC：`docs/spec/10_infra/SPEC-10-004-yquant-ai-coding-pipeline-skill-sync.md` §13（Quick Flow 可执行契约，**§13.1-§13.10**，含 Q-LINK 契约 §13.10）
- Design：`docs/design/10_infra/DESIGN-10-004-yquant-ai-coding-pipeline-skill-sync.md`（§3.1 时序图 / §3.2-§3.6 task body 与 orchestrator 改动点 / §3.7 P-1~P-12 兼容性矩阵 / §3.8 降级升级）

</details>

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
