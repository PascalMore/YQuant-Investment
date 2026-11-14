# 共享 `dir` 的迟到完成与 scope reconciliation

适用于：Implement 曾因 document gate 被 block/timeout/gave-up，但在 parent 后补或 dispatcher 重算后又被 claim 并产出新 completed run；同时 Final Review 报告功能通过，却发现文件范围/allowlist 的 minor。

## 结论规则

1. **最新 run 优先于旧状态标签。** 每次 notification 都 `kanban_show`：记录 run 开始时间、parent 文档 gate 完成时间、实际 diff 与测试。`gave_up` 之后仍可能有合法的新 completed run；它既不是自动失败，也不是自动放行。
2. **先冻结 Closeout。** `status=done` 只满足 scheduler parent 条件，不等于 verdict 自洽。若 Review 的 metadata/正文仍有任何未闭合 `minor`，即使写了 `APPROVE`，Closeout 必须 `dependency` block。
3. **不删除正确的测试来满足 allowlist。** 若越界项是正确且必要的测试证据，Principal 要修复 provenance：为每个实际改动指定唯一责任阶段（如已有 F1 test scope 与后续 F4 router scope），并同步 RFC/SPEC/Design 的 allowlist/互引。禁止事后用模糊文字把所有文件都“默认允许”。
4. **仅文档的 scope correction 仍需 fresh Verify + fresh Review。** 其验证包括：精确路径/章节审计、scope ownership 唯一性、`git diff --check`、受影响定向测试和必要的离线全集。新的 Review 必须明说 `0 open blocker/major/minor` 才可 APPROVE。
5. **重接 Closeout。** 给旧 Closeout 添加新的 fresh-review parent 或另建 replacement Closeout；不要让旧 parent `done` 自动推动收口。

## 最小任务图

```text
late completed implementation candidate
        │
Principal scope / allowlist reconciliation (docs only)
        └── fresh Verify (tester)
                └── fresh Review (reviewer, 0 open findings)
                        └── Closeout
```

## 共享树限制

- 对候选 diff 做 path-filtered reconciliation；不执行 `git reset`、`git stash`、`git clean`。
- 报告“功能正确性”和“阶段范围合规性”是两个不同结论；前者 PASS 不能覆盖后者的 open minor。
- `force_refresh`、真实 provider/Mongo/DDL/cron 等未执行时，Closeout 必须明确为 fake-only/离线门禁。
