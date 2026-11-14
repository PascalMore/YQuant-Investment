# 历史归档：P-27 占位 parent 事故

本文全文仅为历史记录（2026-11-14 起），不是当前入口或强制规则，无新任务必读要求；保留事故事实，不按其中配方执行。现行契约见 [canonical SKILL](../../SKILL.md)。

原文件：`skills/infra/ai-coding-pipeline/SKILL.md`。
原章节：details「P-27 历史事故（旧占位 parent 路径 B 已废止，非当前指令）」。
下方原块按原字节保留；其中相对链接与历史章节号按原文件上下文解释，不作为现行链接或指令。

<!-- ORIGINAL BLOCK BEGIN -->
<details>
<summary>P-27 历史事故（旧占位 parent 路径 B 已废止，非当前指令）</summary>

以下至 details 结束的 A/B 选择和“否则走占位符”全部退役；不得执行其中修复配方，也不据其推断当前工具仍有相同行为。

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

</details>
<!-- ORIGINAL BLOCK END -->
