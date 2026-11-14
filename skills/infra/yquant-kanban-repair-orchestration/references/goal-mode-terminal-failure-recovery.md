# Goal-mode terminal failure recovery

适用：共享 `dir` 工作区的 Implement/Fix worker 已写入候选改动，但因 `kanban_complete` judge 内部失败、或 `Iteration budget exhausted` 结束，卡片没有正常 `done`。

## 原则

- 这不是通过，也不能据此自动重跑同一 Implement。
- 先以当前工作树与真实测试校准候选；禁止 reset/stash/clean。
- 不把 worker 自报的测试数字作为结论；Orchestrator 或独立 tester 必须复跑。
- 若候选满足基本静态与测试门槛，直接进入新的独立 Verify；不要连续创建同角色 replacement Implement 卡造成共享树竞态。

## 固定流程

1. `kanban_show`：记录最后 run、judge/iteration 错误、worker handoff 与已有评论。
2. 只读盘点：`git status --short --untracked-files=all`、allowlist-filtered diff、`git diff --check`。
3. 复跑原卡最小完整离线测试；必要时做一条负向/反证测试，不能只看套件总数。
4. 静态审计输出边界：数据模型字段、serializer、CLI/stdout 和 handoff 是否存在从内部 detail 到外部输出的路径。遇到 P0/P1 违规，先创建最小 Fix；不创建 Verify。
5. 若完成定义满足：
   - 将旧 goal-mode 卡以 `needs_input` 或 `dependency` 固定为“implementation complete but terminal judge unavailable”，避免自动 unchanged replay；
   - 新建 tester Verify，parent 指向最后一个已完成的文档/契约卡，而非 blocked Implement；
   - Verify body 必须声明：它接管共享树候选、不得写文件、不得重放任何受限 live gate。
6. Verify PASS 后仍需独立 Review；Closeout 仅依赖新的 Verify/Review，不依赖 timed-out/blocked Implement 的状态。

## 常见陷阱

- **误将部分实现视为可用**：即使 `diff --check` 与本地套件 PASS，仍要审计 external projection。典型缺陷：内部集合枚举被直接放到 aggregate DTO 后，测试未覆盖陌生名称泄露。
- **用 transient block 冻结 goal-mode 卡**：goal-mode 可能只接受 `needs_input` / `dependency`；根据工具约束选择允许的 block kind，并写清“避免共享树重复修改”。
- **只测 sanitizer helper**：负向测试必须覆盖实际 serializer/CLI output，而非孤立 helper。
- **意外重放 live gate**：Verify 只能 mock/synthetic/离线；被保护的一次性 Provider 调用必须等 Verify+Review 后用独立 continuation 运行。

## 交接最小字段

- 当前候选文件与 allowlist 归属；
- 真实测试命令及计数；
- 未验证的 external paths / residual risks；
- live I/O、PR/provider budget 是否为零；
- 旧卡为何冻结、新 Verify 卡为何不以其为 parent。
