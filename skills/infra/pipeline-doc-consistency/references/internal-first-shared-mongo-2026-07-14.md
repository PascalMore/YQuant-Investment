# Internal-first × Shared Mongo 文档同步复盘（2026-07-14）

## 场景

YQuant 的 Unified Data × Task Center 在 2026-07-14 同时被 Pascal 升级为新的架构基线，影响 RFC-03-007 / SPEC-03-007 / DESIGN-03-007 + RFC-10-009 / SPEC-10-009 / DESIGN-10-009 共 6 份文档。决策包括：

1. TA-CN 与 Unified Data **共用** TA-CN MongoDB / `tradingagents` 物理库。
2. Unified Data 直接融合 TA-CN 的 DataProvider，并直接读取既有内部数据。
3. Unified Data 的新增物化数据落 `03_data_ud_*`；Task Center 元数据落 `10_infra_tc_*`；TA-CN 既有主集合**只读复用**，禁止 Unified Data 回写或加字段污染。
4. 权威读路径 internal-first：内部 Mongo 数据 → 外部 Provider；DSA / SQLite **不再**作为运行时 fallback 或内部数据源。
5. 三层语义分离：业务资产、可追溯物化数据集、短 TTL query cache。
6. Task Center 最小契约（Task/Job/Execution + 幂等 + 重试 + 审计）必须在 Unified Data 物化写入之前具备。

## 上一轮回检的薄弱点

- 仅仅在 SPEC 顶部加 “Design 阶段修订说明” 是不够的。本轮要求：
  - 正文中那些“外部 Provider → TA-CN Adapter” 这种旧示例路由必须替换；
  - “DSA SQLite 作为末级 fallback” 的整段设计语言必须剔除；
  - “数据写入仍走 data-pipeline” 这类定位陈述需要修订为 “Unified Data 对市场数据具备受控物化能力”。
- 仅在路由器层面讨论 fallback 不够，必须显式声明 “DSA 不实现 adapter，路由不占位”。

## 强制同步项（必须落到 RFC/SPEC/Design 三层）

- TA-CN Mongo 物理库边界与 logical ownership（主集合只读 / UD 物化 / TC 元数据 三类所有权）。
- 读取路径顺序与“全链路失败时返回明确 DataResult 错误语义”。
- “DSA 不实现 adapter / 不引入 SQLite 运行时 fallback” 作为硬约束，列入 In Scope 的反向表达。
- Phase 1B 重排：仅“外部 Provider 查询 + internal-first + 三层语义分离”；DSA adapter 从路线图移除。
- Phase 2 / Task Center MVP 提前：以“最小可物化执行契约”为准入门槛；生产 cron / 长期调度不开。

## 文档一致性检索清单（除 2026-07-12 之外）

新增以下关键词，用于 internal-first 与 shared-mongo 决策的残留扫描：

```text
adapter / 回灌 / 回写 / 字段扩展 / 衍生字段 / ud_freshness_checked_at
fallback / 兜底 / 末级 / legacy / internal source
外部 Provider → 本地 / fallback 链
DSAdapterProvider / StockDaily / SQLiteAdapter
task_center / cron / systemd / register / create_job / 任务调度
shared Mongo / 共享 Mongo / 共用同一份库 / co-located
internal-first / internal source priority
```

并显式核对：

- “shared physical db” 是否在 RFC/SPEC/Design 三层都出现；
- logical ownership（TA-CN 主集合 vs `03_data_ud_*` vs `10_infra_tc_*`）三层一致；
- 读取路径是否已经从 “外部 → 本地” 改为 “内部 → 外部”，是否还有反例；
- legacy / DSA adapter 是否已经从设计语言与路线图中移除，而不是仅被弱化。

## 主控（orchestrator）行为

1. **对话留痕**：Pascal 给 ≥3 条架构级决策后，主控必须用 `kanban_comment` 把全部决策登记到 backward-reference 卡片，**不仅留在对话里**。
2. **派真实任务**：以 `assignee=yquantprincipal`、`workspace_path` 指向项目目录、`parents=` 指向 backward-reference 卡，创建文档同步修订任务；`priority=8`。
3. **门禁守则**：在文档修订任务完成并报告 PASS 之前，禁止：
   - 实现任何代码改动；
   - 真实 MongoDB 写入 / DDL / 集合 / 索引；
   - 创建真实 Task Center Job / Execution；
   - 改动 cron / systemd / gateway / webhook。
4. **三点决策后直接推进**：Pascal 三次确认决策后，主控直接派工，**不需要再次询问“是否继续”**。

## 常见误判

- “DSA 没数据，不能兜底” 视为实现细节：错。这是产品/数据架构决策，必须落到 RFC/SPEC/Design。
- “把 fallback 路由顺序改一下就行”：错。fallback 不存在且读到 “fallback” 必须自然变成 “不允许 fallback”，路由语言随之变化。
- “三层语义分离是 README 风格”：错。物化集合与短 TTL cache 在合同层就有 lineage / freshness / TTL 差异，必须在 SPEC 数据契约层显式表达。
- “Task Center 可以延后到 Phase 5”：错。物化写入依赖 Task Center 最小契约，必须先把 Phase 2（任务执行 + 幂等 + 重试 + 审计）前置。

## 给 Implement 阶段的硬约束（落到任务 body）

- 不允许修改 TA-CN / DSA 子项目代码；不允许新增/删除/修改 MongoDB 集合、索引、schema validator。
- 不允许创建真实 Job / Execution；不允许改动 cron / systemd / webhook。
- 不允许在 shared Mongo 物理库之外另起存储后端。
- 不允许写 TA-CN 既有主集合，不允许为其添加 Unified Data 字段。
- 不允许外部真实 API 调用；外部 Provider 测试仅以 mock / fake / 安全降级形式存在。
- 实现路径必须满足 RFC/SPEC/Design 修订后的 final 版；修订未完成前禁止本阶段任何代码提交。
