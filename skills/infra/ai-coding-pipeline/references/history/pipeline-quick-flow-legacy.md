# 历史归档：pipeline Quick Flow 参考

本文全文仅为历史记录（2026-11-14 起），不是当前入口或强制规则，无新任务必读要求；保留事故事实，不按其中配方执行。现行契约见 [canonical SKILL](../../SKILL.md)。

原文件：`skills/infra/ai-coding-pipeline/references/pipeline.md`。
原章节：「历史：Quick Flow（全节退役，非当前指令）」整节，止于路由规则前。
下方原块按原字节保留；其中相对链接与历史章节号按原文件上下文解释，不作为现行链接或指令。

<!-- ORIGINAL BLOCK BEGIN -->
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
<!-- ORIGINAL BLOCK END -->
