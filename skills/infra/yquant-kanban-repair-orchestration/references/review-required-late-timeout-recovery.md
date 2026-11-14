# Review-required 阻塞后的迟到 timeout 事件

## 适用场景
YQuant Full Flow 的 Implement 卡已按代码审查规则写入 handoff，并以 `review-required` 进入 `blocked`；随后 Kanban/dispatcher 又投递 `timed out; will retry` 类通知。

## 核心规则
- `blocked` 的实际任务状态、当前/历史 run 状态和共享工作树实物优先于迟到通知文本。
- 不得仅因 timeout 通知重试、unblock 或重建同一 Implement 卡；先 `kanban_show` 核验是否存在新的 run、候选变更是否稳定、是否已进入独立 Verify。
- 若状态仍是 `blocked`、无新 run、候选 diff 稳定：把 timeout 标记为迟到 lifecycle 事件，保持 T3 冻结，继续独立 T4 Verify。
- 若 dispatcher 实际创建新的 retry：立即审计其是否写入；在不影响已有候选的前提下冻结/阻断重复实现，并保留原始 handoff 作为证据。

## 最小核验集（只读）
1. `kanban_show(T3)`：检查 `status`、runs、events、review-required comment。
2. `kanban_show(T4)`：检查独立 Verify 是否已创建、是否已经开始。
3. 仅对 T3 allowlist 做 `git status --short` / `git diff --name-only` / `git diff --check`。
4. 读取 `binding_state.json`，确认 `enabled` 未因离线修复流程改变。
5. 对 protected paths（例如 Gate-3 baseline 候选、prod repository、文档）做路径过滤状态检查；共享树其他 dirty 不作为 T3 越界证据。

## 交接原则
独立 Verify 可以以已完成的 Design 为依赖、在任务正文中引用被 blocked 的 Implement 卡和其候选 allowlist；不要把 blocked Implement 误当作已 merged，也不要让其阻断独立的只读验证。Verify 与 Review 仍须明确：Git baseline、production activation、独立生产凭据验证是后续隔离 Gate。

## 本次验证样本（2026-08-03）
Gate-4 P0 修复中，Implement 卡 `t_13c46b56` 已因 review-required 处于 `blocked`，随后出现 timeout 通知。复核显示无新 run，5-file allowlist 稳定、binding 仍 false；因此没有重试实现，而是创建独立 T4 Verify。此为流程恢复模式，不是对任何具体卡号的长期依赖。
