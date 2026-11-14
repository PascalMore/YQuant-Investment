# Auto-decomposition 污染隔离与替代验证

适用：一个已开始或已完成的严格 allowlist 修复卡，被自动 decomposer 擅自改派、重写 body、拆成子卡，或在共享 `dir` 留下未追踪交接目录。

## 风险

- 新 root body 可能要求与原修复相反的行为；不可继续把它当作正式 Implement。
- 自动子卡可能在共享树并发重复修改已落盘代码。
- `git diff --name-only` 不显示未追踪产物；例如 `handoff/` 会逃过普通范围审计。
- 不能因为功能测试通过而忽略编排污染；也不能 reset/stash/clean 或删除未知未追踪目录来制造干净工作树。

## 止损与恢复

1. **取证**：读取被污染 root 与所有子卡的 title/body/assignee/status/runs；记录原卡和新卡的差异。检查精确 worker PID，禁止按 profile 或宽泛 grep kill。
2. **停止扩散**：对正在运行的异常子卡使用 `kanban_block(kind="transient")`，再 TERM/KILL 仅该 task PID。若污染 root 已是 `todo` 且不能 block，冻结其正在运行的 ancestor；不要 unblock 或重新派发其子卡。
3. **保全现场**：运行 `git status --short --untracked-files=all` 与 `git diff --check`；对污染目录只记录路径、不得读/改/删，也不得作为实现或验收证据。
4. **重新取证**：以当前磁盘的受控 allowlist 文件为唯一候选实现，独立重跑定向测试、关键运行时断言、以及离线 dry-run。worker summary 只能作线索。
5. **完成事件不是洗白**：若污染 root 随后显示 `completed`，必须再次 `kanban_show` 核对 events。只要存在自动改派、body/parents 重写或 child 拆分，`done` 仅说明平台接受了某次 run，**不恢复原角色链的合规性**。可接受其磁盘产物作为候选事实，但不得把该 root 或其自动 child 作为正式下游 parent；在 parent-gated child 被自动 promote 前立即 `kanban_block(kind="needs_input")`，并核对/停止该卡的精确 PID。
6. **替代链**：先创建一个 `yquantprincipal` 的 **non-goal-mode、只读 replacement T1**，重核当前 RFC/SPEC/Design 实物、路径范围与冻结契约；其完成 handoff 才是合规新链的唯一 parent。随后从该 replacement T1 新建 Design → Implement → fresh Verify → fresh Review。不要以被污染 root 作 parent，也不要依赖其 completed 状态；也不要把旧下游卡解除后复用。
7. **收口前审计**：Review 需将污染目录列为 hygiene anomaly，明确不混入代码 allowlist；并核验异常子卡没有留下新的受控文件修改。最终 Closeout 只引用 replacement Verify/Review。

## 目标循环/判定服务异常的选型

文档型、一次性、低工具复杂度的 replacement T1 不应使用 `goal_mode=True`：其辅助 judge 的限流/异常可能让本已合格的只读复核反复耗尽 iteration budget，诱发自动重试与错误编排。此类任务使用默认单次 worker，并在 body 写明「完成时只调用一次 `kanban_complete`；不得等待或重试 judge」。需要多轮实现/测试的独立开发卡才使用 goal-mode。

## 任务体预防语句

对高风险 P0 Fix 加入：

```text
禁止自动拆分、改派、重写任务 body 或创建 handoff/交接文件。
若出现自动 decomposition：立即停止，不得修改共享工作树；只记录 task id、子卡 id、PID、未追踪路径，等待 Orchestrator 创建 replacement Verify/Review。
```

## 常见误区

- 不能因为子卡是“只读扫描”就让它继续：它仍可写 handoff 并改变卡依赖图。
- 不能把 `handoff/` 计入原 Implement 越界，也不能无授权删除它。
- 不能将恢复 Verify 挂到 `review-required` 的 blocked Implement；Kanban 不会 promote。应使用可信已完成 parent，同时在 body 固化源码实物审计要求。
