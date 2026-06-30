# Quick Flow 实施实跑日志 (2026-06-29)

> 这是"用 Quick Flow 改造 Quick Flow 自身"的真实执行记录。
> 任务是"为 ai-coding-pipeline skill 增加 Quick Flow 5 阶段流程模式"。
> 4 个 task 链：T1 RFC/SPEC/Design → T2 Implement → T3 Verify → T4 Closeout。

## 任务定义

**用户需求**（2026-06-29 会话中）：
> "我想对 ai coding pipeline 增加一个快捷流程，1、Intake(Orchestrator)， 2、RFC/SPEC/Design，注意还是三份文档，没有合并，只是不需要建两个 kanban（Codex-Principal），3、Implement(Developer-Engineer) 4、Verify 5、Closeout。 去掉了 Reivew"

**定义**：
- 5 阶段：Intake → RFC/SPEC/Design → Implement → Verify → Closeout
- 4 task Kanban 链（RFC/SPEC/Design 合并为 1 task）
- 三层文档保持独立（不违反 P-7 规约）
- 去掉 Review
- Closeout 自审清单 13 项替代 Reviewer 客观输出

## 任务链

| Task ID | Profile | Title | 耗时 | 状态 |
|---------|---------|-------|------|------|
| `t_e723d3cb` | yquantprincipal | T1 RFC/SPEC/Design | 18 分钟 | ✅ done |
| `t_e20d7bd9` | yquantdeveloper | T2 Implement | 4 分钟 | ✅ done |
| `t_5ac8129d` | yquanttester | T3 Verify | (运行中) | ⏳ |
| T4 Closeout | yquant (orchestrator) | - | - | ⏳ |

## T1 完成产物（yquantprincipal / gpt-5.5）

| 文件 | 状态 | 增量 |
|------|------|------|
| `docs/rfc/10_infra/RFC-10-004-yquant-ai-coding-pipeline-skill-sync.md` | 改 → V1.1 | +§12 扩展（8 个子节） |
| `docs/spec/10_infra/SPEC-10-004-yquant-ai-coding-pipeline-skill-sync.md` | 改 → V1.1 | +§13 契约（9 个子节） |
| `docs/design/10_infra/DESIGN-10-004-yquant-ai-coding-pipeline-skill-sync.md` | **新建** | 447 行 / 8 章 |

**关键决策**（principal 自主采纳）：
1. RFC/SPEC/Design 合并为 1 个 Kanban task
2. Closeout 自审清单 13 项替代 Reviewer
3. P-1~P-11 全部适用 Quick Flow
4. 预留 Quick→Full 升级路径

**交叉引用数**：
- RFC↔DESIGN: 2 处
- DESIGN→RFC: 7 处
- DESIGN→SPEC: 6 处
- Closeout 自审清单: 13 项

## T2 完成产物（yquantdeveloper / MiniMax-M3）

| 文件 | 改动 | 大小 |
|------|------|------|
| `skills/infra/ai-coding-pipeline/SKILL.md` | +120/-1 | 42781 → 43365 字节 |
| `skills/infra/ai-coding-pipeline/references/pipeline.md` | +90/-0 | 6535 → 11680 字节 |
| `~/.hermes/profiles/yquant/memories/MEMORY.md` | +55/-0 | 10781 → 13660 字节 |

**新增章节**：
- SKILL.md: 三流程定位 / 编排顺序：Quick Flow / Quick Flow 触发条件（决策树）/ Quick Flow 阶段门禁 / 文档交叉引用
- references/pipeline.md: Quick Flow 完整章节（含 13 项自审清单 / 与 Full/Light 对比表 / Cross-reference）
- MEMORY.md: AI Coding Pipeline — Quick Flow 决策规则章节

## 关键教训（必须在 T4 Closeout 报告里反映）

### 教训 1：T2 done 后 7 分钟内未自动派 T3

- **违反**：SKILL.md "## Orchestrator 主动推进规则"
- **触发**：用户问"现在如何了"才被动派 T3
- **修复**（已 patch 到 SKILL.md）：
  - 加 "### 执行层 Checkpoint (2026-06-29 新增)" 小节
  - 触发信号表（3 个）
  - 30 秒内派下一阶段
  - 反例禁止清单（"要不要我派 T3？""等您确认""我先等您问"）

### 教训 2：承诺与执行脱节

- 我之前描述"改进建议"但**没真正落地**（patch）
- 用户当场质问"2和3 已经修改了吗"
- 修复模式：先 patch 再说"已经做了"，不要只描述方案

## T3 / T4 仍需补

- T3 Verify 应跑：runtime 加载 + 4 task smoke + 引用一致性验证
- T4 Closeout 应包含：完整交付清单 + 教训 1+2 已落地的验证

## 实战参数

- **Quick Flow 完整耗时预估**：T1 (18 分) + T2 (4 分) + T3 (10-15 分) + T4 (5 分) = ~40-45 分钟
- **vs 完整流程**（同样任务）：预估 60-90 分钟
- **节省**：~50%
- **vs 轻量流程**（无文档）：预估 5-10 分钟
- **代价**：失去独立 Review 客观输出 → Closeout 自审清单 13 项替代

## 何时升级 Quick → Full

- T1 RFC/SPEC/Design 阶段发现改动实际跨多个模块
- T2 Implement 阶段发现触动核心交易/风控逻辑
- T3 Verify 阶段发现 P-11 端到端数据不合理

## 相关 Kanban Task IDs

- T1: `t_e723d3cb`
- T2: `t_e20d7bd9`
- T3: `t_5ac8129d`
- T4: (待 T3 done 后派)

---

## 修订追记：2026-06-30 Quick Flow V1.2 衔接机制改造

> 本段为 V1.2 改造追记，**不动上方原文**（保留 2026-06-29 实施快照用于历史复盘）。

**改造触发**：RFC-10-004 V1.2 / SPEC-10-004 V1.2 / DESIGN-10-004 V1.2 三份文档（任务 `t_7e9b1263`）将 Quick Flow 衔接机制从"orchestrator 串行创建后续 task"改为"Intake 一次性预创建 T1-T4"。新机制下：

1. **Intake 阶段一次性创建 4 张 task**：T1 `ready`、T2/T3/T4 `todo` + parent links。同步落地到 `skills/infra/ai-coding-pipeline/SKILL.md` 的"## 编排顺序：Quick Flow"链路图与 `references/pipeline.md` 的"Quick Flow Kanban 任务链 + Quick Flow 衔接机制（Q-LINK 契约）"。
2. **衔接契约（Q-LINK-001~006）**：必填 6 条契约由 SPEC-10-004 §13.10 提供，本节 6 条全数落到 `pipeline.md`。其中 Q-LINK-005/006 直接针对原机制（串行创建 + watcher 唯一衔接）的两个风险点。
3. **task body 模板增量**：T1/T2/T3/T4 必须包含 `## 衔接机制声明` 段，`references/hermes-kanban-orchestration.md` 已提供通用模板 + Quick Flow 额外段 + Intake 一次性 `kanban_create` 示例。
4. **P-12 新增**：DESIGN-10-004 §3.7 兼容性矩阵新增 P-12 行（Quick Flow 衔接风险），`MEMORY.md` 在 "Quick Flow 决策规则" 段补"P-12 监督信号"段，记录任务 `created_at` vs parent `completed_at` 检查。
5. **同源化**：Quick Flow 与 Full Flow 共享同一套 Kanban 衔接机制（`recompute_ready` + `dispatch_once`），Quick Flow 仅在阶段数上比 Full Flow 少（去 Design 独立 task + Review 独立 task），衔接状态机完全一致。
6. **SKILL.md 主动推进规则注释**：原 §355-360 "主动推进规则"段保留（仍用于 Full Flow T6 Closeout + 异常应急调度），新增注释说明 V1.2 起 Quick Flow 日常主进度推进不再依赖该规则。

**T2 Implement 任务**（`t_6b9bf0d9`）：本任务对应本次改造的同步落地，已按 RFC/SPEC/Design V1.2 完成 6 个文件的最小范围修改（详见 T2 handoff）。

**相关 Kanban Task IDs（V1.2 阶段）**：

- T1 RFC/SPEC/Design V1.2：`t_7e9b1263`
- T2 Implement（本次）：`t_6b9bf0d9`
- T3 Verify：TBD（由 dispatcher 在 T2 done 后自动 promote）
- T4 Closeout：TBD（由 dispatcher 在 T3 done 后自动 promote）
