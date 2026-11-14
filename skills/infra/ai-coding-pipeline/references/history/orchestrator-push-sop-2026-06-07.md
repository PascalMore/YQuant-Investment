# 历史归档：2026-06/07 主动推进 SOP

本文全文仅为历史记录（2026-11-14 起），不是当前入口或强制规则，无新任务必读要求；保留事故事实，不按其中配方执行。现行契约见 [canonical SKILL](../../SKILL.md)。

原文件：`skills/infra/ai-coding-pipeline/SKILL.md`。
原章节：details「历史：2026-06/07 主动推进 SOP（全节退役，非当前指令）」。
下方原块按原字节保留；其中相对链接与历史章节号按原文件上下文解释，不作为现行链接或指令。

<!-- ORIGINAL BLOCK BEGIN -->
<details>
<summary>历史：2026-06/07 主动推进 SOP（全节退役，非当前指令）</summary>

以下至 details 结束的 Verify→Review→Closeout 卡链、定时派发/unblock 和旧自审规则全部退役；历史事故事实保留，不执行旧配方。

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

</details>
<!-- ORIGINAL BLOCK END -->
