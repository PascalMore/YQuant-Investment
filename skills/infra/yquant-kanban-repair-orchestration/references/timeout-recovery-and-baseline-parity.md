# 超时恢复与 Git baseline/manifest 一致性门禁

适用：共享工作区、Full Flow、生产 activation 前的实现/Verify/Review 链。

## 1. 超时不是结论

Kanban `timed_out`、`gave_up` 或迟到 timeout 事件均不代表 PASS/FAIL。首先读取该卡完整状态与 runs/comments，再对共享树做路径过滤核验：

- 有无正式 handoff / `kanban_complete` / 可审计 comment；
- allowlist 内是否已有候选产物；
- `git diff --check`、protected paths、关键状态实物是否保持安全值；
- retry 是否已运行，避免重复 worker 覆盖同一共享树。

### 分流

| 情况 | 正确处置 |
|---|---|
| timeout 但已有合规产物、仅缺 handoff | 限缩当前 retry 为只读复核并完成 handoff，禁止重复编辑。 |
| timeout/gave_up 且零结论、零评论、零工作树改动 | 冻结旧卡；创建 replacement Verify，任务只含少量可复现检查并强制 PASS/FAIL。不要盲重试。 |
| 迟到 timeout 出现在已 blocked/review-required 后 | 以任务当前 `status`/`current_run_id` 为准；若无 retry，不得重新派实现。 |
| retry 正在运行 | 通过卡评论缩小为明确的命令、证据和 verdict；不要另起并发 worker。 |

Replacement Verify 仍须独立角色、只读，并明确 inherited dirty 与本卡 allowlist 的归属，禁止将共享树其他工作线误判为越界。

## 2. Review PASS 后的 baseline manifest parity check（强制）

在向用户请求任何 `git add` / `git commit` 授权前，Orchestrator 必须执行一次独立的 **manifest parity check**。这是 Review APPROVE 之后、production activation 之前的额外 Gate。

### 必须比较

1. **文档/授权集合**：RFC/SPEC/DESIGN 中声明的 baseline candidate 与用户将被要求逐路径 `git add` 的集合；
2. **运行时集合**：activation CLI 的 `BASELINE_MANIFEST`（或等价严格 scope manifest）；
3. **实际集合**：当前工作树中命中运行时 manifest 的 dirty paths。

必须证明：在计划 commit 后，所有运行时 manifest 内路径均 clean；否则 activation 会在 scope check 处 fail-stop。

### P0 判定

如果文档只要求提交集合 A，但运行时 manifest 包含集合 A 之外的未提交实现/测试路径，则这是 **P0 Contract-C inconsistency**：

- 不得请求用户按旧集合提交；
- 不得创建 activation 卡或改变 binding；
- 将问题以文件/行号和实际 `git diff --name-only -- <manifest paths>` 证据写入 Review 卡；
- 创建 Principal 文档闭合卡，统一三层文档、runtime manifest 和精确 Git 授权集；
- 该闭合需独立 Review 后才可重新申请 Git 授权。

### Git 授权包格式

授权请求必须逐路径列出：

- 每个 `git add <exact-path>`；禁止 `git add -A`、`git add .`、通配符；
- 单一 commit 的目的、包含范围、不会包含的路径；
- commit 前独立测试/secret scan/manifest parity 结果；
- 回滚边界：不得建议 `restore`、`reset --hard`、`stash`、`clean` 来解决共享树 dirty；
- 此 Git Gate 与 activation、独立 production Verify 凭据授权彼此分离。

## 3. 最小静态行序检查

检查 fail-closed 顺序时，避免字符串搜索匹配注释或函数定义。应匹配实际调用签名或 AST，明确报告调用行号。例如：scope collection 调用行 < 实际 `write_binding(report_dir, True)` 调用行；同时确认失败分支存在实际 `write_binding(report_dir, False)` 调用。注释文本不能作为控制流证据。
