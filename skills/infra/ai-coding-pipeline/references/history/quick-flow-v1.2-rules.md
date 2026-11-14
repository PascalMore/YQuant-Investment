# 历史归档：Quick Flow V1.2 编排、触发与门禁

本文全文仅为历史记录（2026-11-14 起），不是当前入口或强制规则，无新任务必读要求；保留事故事实，不按其中配方执行。现行契约见 [canonical SKILL](../../SKILL.md)。

原文件：`skills/infra/ai-coding-pipeline/SKILL.md`。
原章节：「历史：Quick Flow 编排、触发与门禁（全节退役）」及其 V1.2 details。
下方原块按原字节保留；其中相对链接与历史章节号按原文件上下文解释，不作为现行链接或指令。

<!-- ORIGINAL BLOCK BEGIN -->
## 历史：Quick Flow 编排、触发与门禁（全节退役）

<details>
<summary>V1.2 历史规则，非当前入口或强制要求</summary>

以下至 details 结束的触发词、Q-LINK、四卡链、自审替代 Reviewer 等要求仅解释旧任务，不适用于新任务。新任务不加载此节作执行指令。

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

</details>
<!-- ORIGINAL BLOCK END -->
