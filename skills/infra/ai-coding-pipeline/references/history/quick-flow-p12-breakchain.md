# 历史归档：P-12 Quick Flow 断链

本文全文仅为历史记录（2026-11-14 起），不是当前入口或强制规则，无新任务必读要求；保留事故事实，不按其中配方执行。现行契约见 [canonical SKILL](../../SKILL.md)。

原文件：`skills/infra/ai-coding-pipeline/SKILL.md`。
原章节：「P-12: Quick Flow orchestrator 串行创建导致断链（历史）」整节，止于 P-27 前。
下方原块按原字节保留；其中相对链接与历史章节号按原文件上下文解释，不作为现行链接或指令。

<!-- ORIGINAL BLOCK BEGIN -->
### P-12: Quick Flow orchestrator 串行创建导致断链（历史）

> 本条整节为历史记录，Q-LINK/Quick 专用要求不再生效。现行 Full/Light 均在创建时引用已返回的真实 parent id；依赖自动推进，但 dispatcher 停机仍需按授权恢复，不能声称 DB 自行执行 worker。

**症状**（2026-06-30 yinglong Travel Pipeline 案例，5h44m 卡死）：Quick Flow T1 done 01:05，T2 done 01:27，T3 出现时间 07:11（间隔 5h44m）。中间 dispatcher `_kanban_dispatcher_watcher` 静默死亡（gateway 主进程继续运行但不 tick），同时 orchestrator 主 session 处于 idle（state.db 0 新 turn）。两条故障叠加导致 T3 永远不会被创建。

**根因**：Quick Flow 原始设计是"前序 done 后由 orchestrator 临时 `kanban_create` 下一张"。这种 100% 依赖进程层的衔接机制在 dispatcher 失效 + orchestrator 不主动调度时**永久停转**——不是 dispatcher 单点，是**进程层全部失效**。

**修复（已落地）**：方案 A — Intake 阶段一次性预创建 T1-T4，T1 ready，T2/T3/T4 todo + parents。后续衔接交给 Kanban DB 状态机（`recompute_ready` + `dispatch_once`）。即便 dispatcher 死 N 小时，恢复后自动追平全部 task，不再依赖 orchestrator 主 session。详见 `references/quick-flow-handoff-mechanism.md` + RFC-10-004 V1.2 §12.6 / SPEC-10-004 V1.2 §13.10 / DESIGN-10-004 V1.2 §3.1 §3.7。

**预防**：
- orchestrator 在判定走 Quick Flow 时，**Intake 阶段必须**一次性 `kanban_create` 4 张 task
- 任一 task 在前序 done 后被临时 `kanban_create`（`task.created_at > parent.completed_at`）→ Closeout 记录 P-12 流程缺陷
- 三流程衔接机制对比：Full Flow 0 次进程层主动、Quick Flow **3 次进程层主动（V1.2 后归零）**、Light Flow 1 次

**与 P-5 的关系**：P-5 是 worker 误用 `review-required:` blocked；P-12 是流程架构层错误。前者补丁式 unblock 即可，后者必须改设计。
<!-- ORIGINAL BLOCK END -->
