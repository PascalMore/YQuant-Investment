# 文档 Gate 恢复中的状态竞态与阈值对齐

适用：共享 `dir` 工作树中，RFC/SPEC/Design 尚未提交、出现 timeout / 文档回退 / P0 契约修正，且旧下游卡可能被 dispatcher 重新 claim。

## 已验证的恢复顺序

1. **以磁盘为准**：对每层读取版本号、R3 章节锚点、`git status --short`、path-filtered diff 与 `git diff --check`。历史 handoff 只作审计背景。
2. **发现公开阈值冲突时先停止下游**：例如文档写 `>50% mismatch`，但冻结常量/Design 表示匹配率 `<70% fail-stop`。先冻结 SPEC/Design/Implement，创建 Principal-only P0 纠正；不得让旧 worker 把错误阈值传播。
3. **P0 修正必须全文扫描同类活跃语义**：分别检查 metadata/changelog（可保留历史叙述）与正文/活跃 Gate（必须无旧阈值）。明确唯一公开规则，例如 `match_ratio >= 0.70` 才可继续。
4. **状态通知不是事实源**：`blocked` 后仍可能收到迟到 `timed_out`，或旧 worker 已在 block 前被 claim。每条旧卡通知均重新执行：查看当前 card status + 最新 runs/events；检查精确 worker PID；检查当前 diff。
5. **worker 仍写共享树时只杀精确任务 PID**：先 TERM，仍在才 KILL；不得按 profile 或宽泛命令行匹配。随后再次检查 `git status` 与 `git diff --check`。
6. **不要复用旧下游卡**：P0 后建立新的、父链明确的下游文档/实现卡；旧卡作为审计证据保持 blocked。若其已有候选文档，新的 P0 卡只能在当前权威上游下接管、校验并做最小修正。

## 任务 body 最小要求

- 指定唯一可写文件，明确禁止 reset/stash/clean/commit 与真实 I/O。
- 写明当前权威版本，禁止依赖丢失/未提交的旧版本或半成品 Python diff。
- 对阈值类修正，列出正文扫描范围、唯一常量/契约输入、活跃语义的精确形式。
- P0 完成后的 Design 必须将当前 dirty 代码列为“待 Implement 在 allowlist 内重新实现/独立验证”，不能把它当作完成证据。

## 用户侧表达

报告应区分：
- 旧卡 timeout/blocked 是编排审计事件，不是产品 PASS/FAIL；
- 当前磁盘文档是否已对齐；
- 仍未发生的 Provider/Mongo/DDL/DML/服务动作；
- 活跃 replacement 卡与旧卡的明确关系。
