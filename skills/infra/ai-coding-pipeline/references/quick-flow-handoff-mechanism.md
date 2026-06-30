# Quick Flow 衔接机制：方案 A 与历史教训

> 本文档是 `SKILL.md` 的补充参考资料，固化 2026-06-30 yinglong 5h44m 卡死事件得出的 class-level 结论。
> 主体决策与三流程对照矩阵见 `SKILL.md` Quick Flow 章节；具体 KB 关键字 / Kanban body 模板见 `references/pipeline.md`。

---

## 1. 衔接机制的根因分类（按"衔接责任归属"）

| 维度 | DB 状态机（`recompute_ready` + `dispatch_once`） | 进程层（orchestrator 主 session + dispatcher spawn） |
|---|---|---|
| Full Flow（7 阶段 6 task） | T1→T2→T3→T4→T5 | Intake 一次性预创建（同步） |
| Quick Flow（5 阶段 4 task） | 0 次 | T1→T2、T2→T3、T3→T4（**每次异步**） |
| Light Flow（3 阶段 2 task） | T1→T2 | Intake→T1（同步） |

**核心结论**：Quick Flow 100% 依赖进程层；Full Flow 100% 不依赖进程层；Light Flow 介于两者之间。
yinglong 卡死 = Quick Flow 进程层全部失效（dispatcher 静默死 + orchestrator 不主动推进）。

## 2. 三种故障源与三流程的可达性矩阵

| 故障源 | Full Flow | Quick Flow | Light Flow |
|---|---|---|---|
| dispatcher watcher 静默死 | ✅ 自动追平（task 都在 DB） | ❌ 永久卡住（next task 未创建） | ✅ 自动追平（T2 已 todo） |
| orchestrator 主 session 静默 | 中（Intake 已完成） | ❌ 致命（3 次串行） | 低（无 background 衔接） |
| worker notification 投递失败 | 低（被动 spawn） | 高（T2-T4 全靠通知触发 create） | 低（Closeout 迟/不显示） |
| 漏判流程级别 | 三层文档兜底 | 13 项自审清单兜底 | 几乎无兜底（Verify 唯一） |
| 衔接总点数（进程层主动） | 0 次 | **3 次** | 1 次 |

## 3. 方案 A：Quick Flow 改为 Intake 一次性预创建 T1-T4

### 核心改动（已落到 RFC-10-004 V1.2 / SPEC-10-004 V1.2 / DESIGN-10-004 V1.2）

- **Intake 阶段**：orchestrator 一次性 `kanban_create` 4 张 task
  - T1 RFC/SPEC/Design：`parents=[]`，status=ready
  - T2 Implement：`parents=[T1]`，status=todo
  - T3 Verify：`parents=[T1, T2]`（或最小 `parents=[T2]`），status=todo
  - T4 Closeout：`parents=[T1, T2, T3]`（或最小 `parents=[T3]`），status=todo
- **衔接机制**：dispatcher 自动 `recompute_ready` + `dispatch_once` 串行 promote+spawn
- **进程层失效保护**：dispatcher 死 N 小时后恢复，自动追平全部任务

### Q-LINK 契约（SPEC-10-004 §13.10，6 条强制项）

| # | 契约 | 状态 | 验证方式 |
|---|---|---|---|
| Q-LINK-001 | Intake 一次性创建 T1/T2/T3/T4 | 必须 | `kanban_show` / task thread 可见 4 个 task id |
| Q-LINK-002 | T1 初始可调度 | 必须 | T1 status=ready 或已 claim 为 running |
| Q-LINK-003 | T2/T3/T4 初始不可调度 | 必须 | status=todo 且存在 parent links |
| Q-LINK-004 | 后续 promote 由 Kanban DB 状态机完成 | 必须 | 前序 done 后无新 task，只发生 todo→ready→running 状态变化 |
| Q-LINK-005 | 前序 done 后临时创建下一张 task | **禁止** | 若 task `created_at` 晚于 parent `completed_at`，Closeout 记录流程缺陷 |
| Q-LINK-006 | orchestrator 主 session / watcher 是唯一衔接机制 | **禁止** | 任何通知丢失不得导致"下一张 task 不存在" |

### P-12 pitfall（DESIGN-10-004 §3.7）

| Pitfall | 描述 | Quick Flow 适用？ | 备注 |
|---|---|---|---|
| P-12 | Quick Flow orchestrator 串行创建风险 | ✅ 已通过预创建消除 | Intake 一次性预创建 T1-T4，避免 watcher/session 断链 |

## 4. yinglong 5h44m 卡死事件复盘（教训归档）

- **现象**：T1 done 01:05，T2 done 01:27，T3 出现 07:11（间隔 5h44m）
- **直接原因**：dispatcher `_kanban_dispatcher_watcher` 在 01:28:20 reap zombie 后**静默死亡**（`asyncio.to_thread(_tick_once)` 永久 hang），gateway 主进程继续运行但不 tick
- **间接原因**：Quick Flow 串行 create 设计让"下一次 create"完全依赖 orchestrator 主 session 的 background notification；yinglong orchestrator 在 01:27 ~ 07:10 之间没有任何动作（state.db 0 新 turn）
- **修复路径**：方案 A 落地（V1.2 三份文档修订），dispatcher 失效后自动追平而非永久停转

## 5. yinglong 同步与双项目一致性

- `skills/infra/ai-coding-pipeline/SKILL.md` 是 yquant / yinglong **共享的 canonical source**（见 SKILL.md 顶部说明）
- 修订 V1.2 后两个项目**同时受益**，不需要在 yinglong 另起流程
- yinglong 报告 `data/yinglong/kanban-dispatcher-investigation-2026-06-30.md` 应在 Closeout 阶段标记为"已被 V1.2 修订 closed by t_7e9b1263 family"

## 6. 决策门禁：orchestrator 判定走 Quick Flow 时必查

在判定走 Quick Flow 之前，**必须**显式核查以下全部条件并写入 task body 顶部：

- [ ] 改动范围 3-8 文件、单模块为主
- [ ] 不涉及核心交易、风控、生产 MongoDB schema 变更
- [ ] 不新增/升级三方依赖
- [ ] 跨模块路径不超过 1 个
- [ ] 用户已明确需求，无需多轮探索

任一不满足 → 升级到 Full Flow；任一为"单文件低风险 bug fix / 注释 / 格式" → 降级到 Light Flow。

## 7. 与方案 B / 方案 C 的对比（背景）

| 方案 | 改动量 | 运行时风险 | 推荐度 |
|---|---|---|---|
| **A 一次性预创建（已落地）** | SKILL.md + pipeline.md + 6 处文档 | 0（与 Full Flow 同源） | ⭐⭐⭐ |
| B 加 pipeline-chain watcher hook | 加 hermes-agent 代码 | 中（多了 1 个 watcher） | ⭐ |
| C 明示 Quick Flow 半自动 + 5min poll timer | 仅 SKILL.md | 高（session 压缩 / inactivity 会让 timer 失效） | ⭐ |

## 8. Cross-reference

- 主 skill：`skills/infra/ai-coding-pipeline/SKILL.md`（Quick Flow 章节 + 三流程定位）
- 阶段门禁：`skills/infra/ai-coding-pipeline/references/pipeline.md`（Quick Flow 章节）
- Kanban body 模板：`skills/infra/ai-coding-pipeline/references/hermes-kanban-orchestration.md`
- RFC：`docs/rfc/10_infra/RFC-10-004-yquant-ai-coding-pipeline-skill-sync.md` V1.2 §12.6 / §12.7
- SPEC：`docs/spec/10_infra/SPEC-10-004-yquant-ai-coding-pipeline-skill-sync.md` V1.2 §13.1 / §13.10
- DESIGN：`docs/design/10_infra/DESIGN-10-004-yquant-ai-coding-pipeline-skill-sync.md` V1.2 §3.1 / §3.6 / §3.7