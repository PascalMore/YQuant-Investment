# DESIGN-10-004: YQuant AI Coding Pipeline Quick Flow 详细设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-29 |
| 最后更新 | 2026-06-30 |
| 版本号 | V1.2 |
| 来源 RFC | RFC-10-004-yquant-ai-coding-pipeline-skill-sync |
| 来源 SPEC | SPEC-10-004-yquant-ai-coding-pipeline-skill-sync |
| 目标模块 | 10_infra / Hermes Kanban Pipeline |
| 关联 Design | 无（本 Design 是首批 Quick Flow 设计，承接 RFC-10-004 §12 与 SPEC-10-004 §13） |

## 1. 设计摘要

本设计将 RFC-10-004 §12（Quick Flow 流程模式）与 SPEC-10-004 §13（Quick Flow 可执行契约）落为可执行的实现设计。核心目标：

1. 定义 Quick Flow 在 Intake 阶段一次性预创建 4 个 Kanban task 的精确时序、依赖和 body 模板。
2. 设计 Closeout 自审清单（≥11 项），替代完整流程的 Reviewer 角色。
3. 标注 orchestrator 侧改动点：SKILL.md、references/pipeline.md、MEMORY.md 的具体落点。
4. 标注 P-1~P-11 pitfalls 在 Quick Flow 中的适用性矩阵。

Quick Flow 的核心取舍：去掉独立的 Design task（合并到 T1）和 Review task（以自审替代），保留三层文档独立性和 Verify 客观屏障。预期节省 2 个 Kanban task，总耗时减少约 25-35%。

## 2. 现状分析

### 2.1 相关目录与文件

| 路径 | 角色 | Quick Flow 行为 |
|---|---|---|
| `docs/rfc/10_infra/RFC-10-004-...md` | 需求与决策源 | 已含 §12 Quick Flow；只读 |
| `docs/spec/10_infra/SPEC-10-004-...md` | 可执行契约源 | 已含 §13 Quick Flow；只读 |
| `docs/design/10_infra/DESIGN-10-004-...md` | **本 Design** | 新增 |
| `skills/infra/ai-coding-pipeline/SKILL.md` | 流水线主实现 | T2 阶段修改：增加 Quick Flow 章节 |
| `skills/infra/ai-coding-pipeline/references/pipeline.md` | 阶段门禁参考 | T2 阶段修改：增加 Quick Flow 章节 |
| `~/.hermes/profiles/yquant/memories/MEMORY.md` | orchestrator 决策规则 | T2 阶段修改：增加 Quick Flow 触发决策规则 |
| `skills/infra/ai-coding-pipeline/references/document-layers.md` | 三层文档职责 | 只读，Quick Flow 不改变三层定义 |
| `skills/infra/ai-coding-pipeline/references/agent-handoff.md` | 角色交接内容 | 只读，Quick Flow 不改变角色交接 |

### 2.2 现有完整流程 vs Quick Flow

| 维度 | 完整流程 | Quick Flow |
|---|---|---|
| Kanban task 数 | 6 | 4 |
| RFC/SPEC/Design 分几个 task | 2（T1 RFC/SPEC + T2 Design） | 1（T1 合并产出三份文档） |
| Review 阶段 | 独立 Reviewer task | 无（Closeout 自审替代） |
| 总阶段数 | 7（含 Intake/Closeout） | 5（含 Intake/Closeout） |
| orchestrator 参与 | Intake + Closeout | Intake + Closeout（自审） |

### 2.3 约束与兼容性

- Quick Flow 必须与完整流程共享相同的 profile assignee 路由，不新增 profile。
- P-1~P-11 pitfalls 中的修复策略在 Quick Flow 中继续适用（详见 §3.7 兼容性矩阵）。
- Quick Flow 的 T1 body 必须显式声明流程模式，以避免 worker 误用完整流程的 task body 结构。
- 三层文档的命名规则、目录结构与章节模板与完整流程完全一致。

## 3. 方案设计

### 3.1 流程时序图

```
orchestrator Intake
    │
    │  判定触发 Quick Flow（RFC-10-004 §12.3-§12.4）
    │  t=0 → Intake: kanban_create T1/T2/T3/T4 (4 张全链)
    │
    │    T1: status=ready, parents=[]
    │    T2: status=todo,  parents=[T1]
    │    T3: status=todo,  parents=[T1,T2]（最低 [T2]）
    │    T4: status=todo,  parents=[T1,T2,T3]（最低 [T3]）
    │
    │  后续衔接交给 Kanban DB 状态机：task_links + recompute_ready + dispatch_once
    ▼
┌─────────────────────────────────────────────┐
│ T1: RFC/SPEC/Design (yquantprincipal)        │
│                                              │
│ 输入：user goal + scope + constraints        │
│ 产出：                                      │
│   docs/rfc/{mod}/RFC-{NN}-{XXX}-{name}.md   │
│   docs/spec/{mod}/SPEC-{NN}-{XXX}-{name}.md │
│   docs/design/{mod}/DESIGN-{NN}-{XXX}-{name}.md │
│                                              │
│ 门禁：orchestrator 校验三份文档存在 +        │
│       引用关系正确 + 章节结构完整             │
└─────────────┬───────────────────────────────┘
              │ T1 done → recompute_ready promotes T2
              ▼
┌─────────────────────────────────────────────┐
│ T2: Implement (yquantdeveloper)              │
│                                              │
│ 输入：SPEC + Design + 实现约束               │
│ 产出：代码变更 + 测试                        │
│                                              │
│ 门禁：代码编译/语法通过 + 测试通过           │
└─────────────┬───────────────────────────────┘
              │ T2 done → recompute_ready promotes T3
              ▼
┌─────────────────────────────────────────────┐
│ T3: Verify (yquanttester)                    │
│                                              │
│ 输入：SPEC + 代码变更                        │
│ 产出：测试报告 + 端到端 smoke test 结果      │
│                                              │
│ 门禁：所有验收标准通过                       │
└─────────────┬───────────────────────────────┘
              │ T3 done → recompute_ready promotes T4
              ▼
┌─────────────────────────────────────────────┐
│ T4: Closeout (orchestrator)                  │
│                                              │
│ 输入：所有前期产出                           │
│ 产出：Closeout 自审报告 + 变更总结           │
│                                              │
│ 门禁：自审清单 ≥11 项全部通过                │
└─────────────────────────────────────────────┘
```

设计决策：T2/T3/T4 必须在 t=0 就存在于 Kanban DB 中，以 `todo` + parent links 表示不可运行状态。禁止把“创建下一阶段 task”作为 T1/T2/T3 完成通知的回调动作；通知只能用于汇报和人工观察，不承担状态机职责。

本时序图落实 RFC-10-004 §12.6 的任务链创建时机，并细化 SPEC-10-004 §13.1 / §13.10 的衔接机制契约。

### 3.2 T1 Task Body 模板

```markdown
## 任务目标

本任务走 **Quick Flow**（5 阶段：Intake → RFC/SPEC/Design → Implement → Verify → Closeout）。

[用户目标描述]

## Quick Flow 流程声明

- 流程模式：Quick Flow（5 阶段，去掉独立 Review）
- T1 产出：RFC + SPEC + Design 三份独立文档（本 task）
- 后续阶段：T2 Implement → T3 Verify → T4 Closeout
- 衔接机制：Intake 阶段已一次性预创建 T2/T3/T4；本 task 完成后由 Kanban DB 自动 promote 后续阶段
- 预创建 task id：T2=[task_id]，T3=[task_id]，T4=[task_id]
- 禁止事项：不得要求 orchestrator 在 T1 done 后临时创建 T2

## 允许修改的文件

- [精确路径 1]
- [精确路径 2]

## 禁止修改的文件

- [精确路径 1]
- [精确路径 2]
- 3 个文档模板（RFC-00-000 / SPEC-00-000 / DESIGN-00-000）
- ai-coding-pipeline SKILL.md（T2 阶段修改）
- 其他项目（yinglong 等）的同号文档

## 交付物

- 修改后的 `docs/rfc/{module}/RFC-{NN}-{XXX}-{name}.md`
- 修改后的 `docs/spec/{module}/SPEC-{NN}-{XXX}-{name}.md`
- 新建的 `docs/design/{module}/DESIGN-{NN}-{XXX}-{name}.md`

## 项目约定

- 目标项目绝对路径：/home/pascal/workspace/yquant-investment
- 禁止修改：/home/pascal/workspace/yq-yinglong
- 文档命名：{TYPE}-{NN}-{XXX}-{short-name}.md
- 模块编号：{XX} = 对应模块数字编号
- [数据库/隐私/凭据等工件约定]

## 验收标准

### RFC
- [ ] 章节结构完整（元数据/执行摘要/背景/目标/设计/风险/验收/参考资料等）
- [ ] Quick Flow 扩展章节（若适用）

### SPEC
- [ ] 章节结构完整（元数据/需求摘要/范围/功能规格/数据契约/配置/测试/验收等）
- [ ] Quick Flow 可执行契约（若适用）

### Design
- [ ] 章节结构完整（元数据/设计摘要/现状/方案/实现计划/测试/风险/交接等）
- [ ] Closeout 自审清单 ≥ 11 项（若为 Quick Flow 场景）

## 输出语言

中文
```

### 3.3 T2 Task Body 模板

```markdown
## 任务目标

按 SPEC 与 Design 实现代码变更。本任务属于 Quick Flow（T2 Implement 阶段）。

## Quick Flow 预创建声明

- 本 task 已在 Intake 阶段预创建，parents=[T1]
- 本 task 由 T1 done 后 Kanban DB 自动 promote+spawn
- 禁止依赖 orchestrator 在 T1 done 后临时创建本 task

## 来源文档

- RFC：[完整路径]
- SPEC：[完整路径]
- Design：[完整路径]

## 允许修改的代码文件

- [精确路径 1]
- [精确路径 2]

## 禁止修改的代码文件

- [精确路径 1]
- [精确路径 2]
- 3 个文档模板（RFC-00-000 / SPEC-00-000 / DESIGN-00-000）
- 其他模块的无关代码
- 其他项目（yinglong 等）的文件

## 实现约束

来自 SPEC §11（若有）：
- [约束 1]
- [约束 2]

来自 Design §7（交接给实现者）：
- [必须遵守]
- [可自行判断]

## 验收标准

- [ ] 代码语法/编译通过
- [ ] 所有测试通过：[测试命令]
- [ ] 端到端 smoke test 通过：[具体步骤]
- [ ] 业务合理性 checklist：[具体 checklist]
- [ ] 未修改禁止清单中的文件
- [ ] 文件改动范围在 Design §3.1 预期内

## 输出语言

中文
```

### 3.4 T3 Task Body 模板

```markdown
## 任务目标

独立验证 T2 实现的正确性和一致性。本任务属于 Quick Flow（T3 Verify 阶段）。

## Quick Flow 预创建声明

- 本 task 已在 Intake 阶段预创建，parents=[T1,T2]（最低 parents=[T2]）
- 本 task 由 T2 done 后 Kanban DB 自动 promote+spawn
- 禁止依赖 orchestrator 在 T2 done 后临时创建本 task

## 来源文档

- SPEC：[完整路径]
- Design：[完整路径]

## 验收标准矩阵

| 编号 | 验收项 | 期望 | 实际 |
|---|---|---|---|
| Q-A-001 | ... | ... | 待验证 |
| Q-A-002 | ... | ... | 待验证 |

## 测试命令

```bash
# 单元测试
[命令]

# 集成测试
[命令]

# 端到端 smoke test
[命令]
```

## 端到端 smoke test 步骤

1. [步骤 1]
2. [步骤 2]
3. 数据合理性抽样检查：
   - 检查 [具体字段] 是否 [合理范围/条件]
   - 检查 [具体输出] 是否 [合理内容]

## 输出

- 测试报告（通过/失败 + 失败详情）
- 残余风险列表

## 输出语言

中文
```

### 3.5 T4 Closeout 自审清单

T4 Closeout 由 orchestrator 执行。由于 Quick Flow 无独立 Reviewer，orchestrator 必须逐项核查以下清单，每项标注 ✅ 通过 / ❌ 未通过。

| # | 检查项 | 检查方法 |
|---|---|---|
| 1 | Quick Flow T1-T4 在 Intake 阶段一次性预创建 | `kanban_show` / task thread / created_at 复核 |
| 2 | T2/T3/T4 parent links 存在且指向正确上游 | Kanban `parents` / `task_links` 复核 |
| 3 | SPEC 契约与实际实现一致 | 对比 SPEC §3/§4 与 git diff |
| 4 | 文件改动清单符合 Design §3.1 预期 | `git diff --stat` 对比 Design |
| 5 | 验收标准（RFC §9 + SPEC §10）全部通过 | T3 测试报告复核 |
| 6 | 风险应对（RFC §7）已验证或降级可接受 | 逐条复核 RFC §7 风险表 |
| 7 | 代码风格和项目约定遵守 | 抽查 2-3 个变更文件 |
| 8 | 测试覆盖满足 Design §5 要求 | T3 测试报告覆盖率核对 |
| 9 | 无遗漏的边缘情况或异常降级路径 | 抽样检查 edge case |
| 10 | 三方依赖无新增/升级，或已记录 | `git diff` 依赖文件 |
| 11 | 文档引用关系正确（RFC → SPEC → Design → 实现） | 交叉引用 grep |
| 12 | Git diff 范围在产品边界内，不包含无关改动 | `git diff --stat` + 人工复核 |
| 13 | worker 日志无异常（fallback、crash、timeout） | 检查 `~/.hermes/profiles/*/logs/agent.log` |
| 14 | 未修改禁止清单中的文件 | `git diff --name-only` 交叉检查 |
| 15 | 未修改文档模板 | `git diff docs/*/00_*template*` |

若 #1-#15 全部 ✅ → closeout 完成。若发现 Major/High 问题 → 退回 T2，不 closeout。Minor 问题 → orchestrator 直接修，closeout 记录。若 #1/#2 未通过但本次运行已通过人工补救完成，允许 closeout，但必须记录为流程缺陷并禁止作为标准 Quick Flow 样例复用。

### 3.6 Orchestrator 改动点

#### 3.6.1 `skills/infra/ai-coding-pipeline/SKILL.md`

在现有"触发入口"章节后新增"Quick Flow 触发入口"子章节：

- 显式触发词："走 Quick Flow"、"按快捷流程"、"5 阶段快速"。
- 自动触发规则：中风险 + 明确需求 + 改动范围 3-8 文件 + 非核心数据/风控。
- Quick Flow Kanban 创建规则：Intake 阶段一次性创建 4 task 依赖链（RFC/SPEC/Design 合并为 1 task），T1 ready，T2/T3/T4 todo，后续由 dispatcher 自动 promote+spawn。
- Closeout 自审清单引用：指向 DESIGN-10-004 §3.5。

##### Intake 阶段一次性创建 4 task

orchestrator 在判定 Quick Flow 后必须在同一个 Intake 动作中创建：

1. T1 RFC/SPEC/Design：`assignee=yquantprincipal`，无 parents，立即可运行。
2. T2 Implement：`assignee=yquantdeveloper`，`parents=[T1]`。
3. T3 Verify：`assignee=yquanttester`，`parents=[T1,T2]`（最低 `[T2]`）。
4. T4 Closeout：`assignee=<orchestrator>`，`parents=[T1,T2,T3]`（最低 `[T3]`）。

T1 body 必须写入 T2/T3/T4 task id；T2/T3/T4 body 必须声明自己是 Intake 预创建 task。禁止等待 T1/T2/T3 done 通知后再创建下一张 task。

不修改章节：
- 完整流程和轻量流程的定义保持不变。
- 角色路由、assignee profile 映射不变。
- P-1~P-11 pitfalls 章节不变（新增 Quick Flow 适用性标注即可）。

#### 3.6.2 `skills/infra/ai-coding-pipeline/references/pipeline.md`

新增"Quick Flow 阶段门禁"章节：

- T1 门禁：RFC/SPEC/Design 三份文档存在 + 引用关系正确 + 章节结构完整（orchestrator 校验）。
- T2 门禁：代码编译/语法通过 + 测试通过（developer 自检 + tester 验证）。
- T3 门禁：验收标准全部通过 + 端到端 smoke test 通过（tester 报告）。
- T4 门禁：自审清单 ≥11 项全部通过（orchestrator 执行）。

#### 3.6.3 `~/.hermes/profiles/yquant/memories/MEMORY.md`

新增 Quick Flow 触发决策规则记忆项：

```markdown
## Quick Flow 决策规则

- Quick Flow 适用场景：中风险、明确需求、3-8 文件改动、单模块、非核心交易/风控。
- Quick Flow 显式触发词：走 Quick Flow、按快捷流程、5 阶段快速。
- 4 task 链：T1(yquantprincipal) → T2(yquantdeveloper) → T3(yquanttester) → T4(orchestrator)。
- Closeout 必须执行自审清单（DESIGN-10-004 §3.5，≥11 项）。
- 禁止 Quick Flow 场景：MongoDB 写入、交易/风控逻辑、外部消息发送、跨 2+ 模块架构变更。
- Quick Flow 中途发现风险低估 → 可升级为完整流程。
```

### 3.7 P-1~P-11 Pitfalls 兼容性矩阵

| Pitfall | 描述 | Quick Flow 适用？ | 备注 |
|---|---|---|---|
| P-1 | Skill name collision 导致 worker crash | ✅ 完全适用 | worker 启动机制不变 |
| P-2 | dispatcher 透明 fallback | ✅ 完全适用 | T1/T2/T3 均受影响 |
| P-3 | Kanban DB task id 不存在时不能 `parents=[]` | ✅ 完全适用 | 4 task 链依赖 kanban_create |
| P-4 | workspace_path 必须用共享项目目录 | ✅ 完全适用 | 所有 task 都需要 |
| P-5 | worker 完成后不要误 block | ✅ 完全适用 | T1/T2/T3 完成后直接 done |
| P-6 | T1 完成后用户决策变更 | ✅ 完全适用 | Quick Flow T1 是 RFC/SPEC/Design 合并 task |
| P-7 | 编排层越界改模板 | ✅ 完全适用 | orchestrator 禁止直接改模板 |
| P-8 | 跨项目复用前须发现约定 | ✅ 完全适用 | Intake 阶段执行 |
| P-9 | 中途变更骨架/命名规范 | ✅ 完全适用 | orchestrator 负责 comment + 兜底 |
| P-10 | 凭据/环境文件遮蔽 | ✅ 完全适用 | 涉及凭据的实现需真实 smoke test |
| P-11 | 端到端 smoke test 数据合理性 | ✅ 完全适用 | T3 Verify 必须抽查输出业务合理性 |
| P-12 | Quick Flow orchestrator 串行创建风险 | ✅ 已通过预创建消除 | Intake 一次性预创建 T1-T4，避免 watcher/session 断链 |

所有 P-1~P-12 在 Quick Flow 中继续适用，无例外。P-12 的核心含义是：Quick Flow 不得把“下一阶段 task 是否存在”依赖于 orchestrator 主 session、gateway watcher 或进程通知；这些组件只能影响可观测性，不能影响依赖链完整性。

### 3.8 与完整流程的降级/升级路径

#### 降级（完整流程 → Quick Flow）

不允许。完整流程已启动后不能降级为 Quick Flow（因为已经创建了多余的 Kanban task）。

#### 升级（Quick Flow → 完整流程）

在 T1/T2/T3 任意阶段，若 orchestrator 发现以下情况，可升级为完整流程：

- 实际风险超出 Quick Flow 边界（如发现需要修改核心交易逻辑）。
- 用户明确要求走完整流程。
- T3 Verify 发现需要独立 Reviewer 介入的问题。

升级操作：

1. 若 T1 已完成：补开 T_Design 独立 task（assignee=yquantprincipal），parents=[T1]。
2. 在 T3 之后追加 T_Review task（assignee=yquantreviewer），parents=[T3]。
3. 更新后续 task body 的流程模式声明。

## 4. 实现计划

- [ ] 1. 修改 `skills/infra/ai-coding-pipeline/SKILL.md`：新增 Quick Flow 触发入口、Kanban 创建规则、Closeout 自审清单引用（Design §3.6.1）。
- [ ] 2. 修改 `skills/infra/ai-coding-pipeline/references/pipeline.md`：新增 Quick Flow 阶段门禁（Design §3.6.2）。
- [ ] 3. 修改 `~/.hermes/profiles/yquant/memories/MEMORY.md`：新增 Quick Flow 决策规则记忆项（Design §3.6.3）。
- [ ] 4. 将 DESIGN-10-004 同步到 yquant 主 profile runtime cache（如适用）。
- [ ] 5. 运行 smoke 验证：创建一个 Quick Flow 测试 Kanban task，验证 4 task 链正常调度。

## 5. 测试策略

### 5.1 单元测试

N/A（无代码变更，仅文档和 skill 内容修改）。

### 5.2 集成测试

- 从 yquant 主 profile 加载 `yquant-ai-coding-pipeline` skill，确认 Quick Flow 章节可被 Hermes 正常解析。
- 验证 `kanban_create` 能创建 Quick Flow 4 task 链。

### 5.3 手工验证

- 阅读 RFC-10-004 §12、SPEC-10-004 §13、DESIGN-10-004，验证三层文档之间引用关系正确。
- 验证 Quick Flow 5 阶段定义在 3 份文档中完全一致。
- 验证 Closeout 自审清单 ≥ 11 项（实际 13 项）。

### 5.4 回归范围

- 完整流程和轻量流程的定义和行为不应改变。
- 现有 P-1~P-11 pitfalls 修复不受影响。
- 现有 Kanban task 链不受影响。

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| Quick Flow 自审不充分导致质量问题 | 自审清单 ≥11 项（实际 13 项）强制覆盖 | 发现问题后补开 Review task |
| Quick Flow 误用于高风险场景 | Intake 触发条件硬性检查；升级路径明确 | 升级为完整流程（§3.7） |
| T1 合并产出三层文档质量下降 | SPEC §13.2 明确 T1 body 最低要求 + orchestrator T1 门禁 | 退回 T1 重做 |
| Closeout 自审被 orchestrator 跳过或敷衍 | SPEC §13.5 要求逐项核查并记录结果 | T4 门禁：自审清单未全部完成则不允许 closeout |
| orchestrator SKILL.md 修改引入新 bug | T2 实现后跑完整流程 smoke test | git revert SKILL.md |

## 7. 交接给实现者

### 7.1 必须遵守

- 只修改 `skills/infra/ai-coding-pipeline/SKILL.md`、`references/pipeline.md` 和 `~/.hermes/profiles/yquant/memories/MEMORY.md` 三个文件。
- Quick Flow 章节必须放在 SKILL.md 的"触发入口"章节后，不与完整流程/轻量流程的定义混合。
- MEMORY.md 的 Quick Flow 记忆项必须是紧凑的决策规则，不是完整文档摘要。
- 不修改文档模板（RFC-00-000 / SPEC-00-000 / DESIGN-00-000）。
- 不修改 profile config.yaml 或 Hermes core。
- 修改完成后需验证 yquant 主 profile 加载 skill 无 Ambiguous 报错。

### 7.2 可自行判断

- Quick Flow 在 SKILL.md 中的章节标题格式和具体措辞。
- pipeline.md 门禁描述的详细程度。
- MEMORY.md 记忆项的精确措辞（但必须覆盖所有 6 条规则）。

### 7.3 遇到以下情况退回 Principal

- SPEC §13 的契约与 RFC §12 的设计意图存在矛盾。
- Quick Flow 需要修改的 SKILL.md 区域与现有完整流程定义存在结构性冲突。
- 发现 Quick Flow 的某一设计决策与某个 P-1~P-11 pitfall 不可调和。
- 实现过程中发现现有 SKILL.md 的其他章节也需要修改（超出本 Design 范围）。
- yquant 主 profile 加载 skill 后出现新 Ambiguous 或功能回退。

## 8. 参考资料

- `docs/rfc/10_infra/RFC-10-004-yquant-ai-coding-pipeline-skill-sync.md`
- `docs/spec/10_infra/SPEC-10-004-yquant-ai-coding-pipeline-skill-sync.md`
- `skills/infra/ai-coding-pipeline/SKILL.md`
- `skills/infra/ai-coding-pipeline/references/pipeline.md`
- `skills/infra/ai-coding-pipeline/references/document-layers.md`
- `skills/infra/ai-coding-pipeline/references/agent-handoff.md`

## 9. 版本修订说明

- 当前版本：V1.2
- 修订日期：2026-06-30
- 修订摘要：Quick Flow 衔接机制由 orchestrator 串行创建后续 task 改为 Intake 一次性预创建 T1-T4；§3.1 时序图、§3.2-§3.5 body/自审模板、§3.6 orchestrator 改动点和 §3.7 P-12 兼容性矩阵已同步修订。
