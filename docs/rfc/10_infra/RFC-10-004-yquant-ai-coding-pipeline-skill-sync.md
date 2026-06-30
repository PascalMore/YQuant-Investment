# RFC-10-004：YQuant AI Coding Pipeline Skill 同步与冲突修复

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 已采纳（Accepted） |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-06-27 |
| 最后更新 | 2026-06-30 |
| 版本号 | V1.2 |
| 所属模块 | 10_infra（基础设施 / Hermes Kanban Pipeline） |
| 依赖 RFC | RFC-10-003-infra-architecture |
| 替代 RFC | 无 |
| 适配 AI 工具 | Hermes Agent, Hermes Kanban |
| 标签 | #infra #hermes #kanban #skill #pipeline |

## 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-06-27 | 初始创建，定义 AI Coding Pipeline skill canonical source、运行态副本保留策略与 worker 副本删除策略 | YQuant-Codex-Principal |
| V1.1 | 2026-06-29 | 新增 §12 扩展：Quick Flow 5 阶段流程模式（Intake → RFC/SPEC/Design → Implement → Verify → Closeout） | YQuant-Codex-Principal |
| V1.2 | 2026-06-30 | Quick Flow 衔接机制由 orchestrator 串行创建改为 Intake 一次性预创建 T1-T4，与 Full Flow 同源 | YQuant-Codex-Principal |

## 1. 执行摘要

`yquant-ai-coding-pipeline` skill 同时存在于项目源目录与 worker profile 运行态目录时，Hermes 会把同名 skill 判定为 Ambiguous 并导致 worker 启动崩溃。本 RFC 规定：项目源目录是唯一 canonical source，yquant 主 profile 保留一份运行态副本，4 个 worker profile 不保留同名副本，以消除 Skill name collision 并恢复 Kanban worker 正常启动。

## 2. 背景与动机

### 2.1 现状痛点

- 项目源目录 `/home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/` 与 profile 运行态目录 `~/.hermes/profiles/*/skills/infra/yquant-ai-coding-pipeline/` 曾同时存在同名 skill。
- Worker 启动时 `HERMES_HOME` 指向目标 profile，同时通过 `workspace_path=/home/pascal/workspace/yquant-investment` 发现项目源目录，两个候选 skill 名称相同，触发 `Ambiguous skill name`。
- 运行态 yquant 主 profile 副本包含 2026-06-25 实跑后补的 P-1~P-4 教训与 `real-run-journal-2026-06-25.md`，但项目源目录才是 skill 自身声明的 canonical source。
- 若只删除所有 profile 副本，yquant 主 profile 在 cwd 不在项目目录时可能无法加载该 skill；若保留 worker 副本，则 worker 会继续 collision。

### 2.2 业务影响

- RFC/SPEC/Design/Implement/Verify/Review 流水线无法稳定派发；worker 在进入对话循环前崩溃，任务会被 dispatcher 标记 `crashed`，连续失败后进入 `blocked`。
- Orchestrator 看不到有效阶段产出，流水线自动依赖链失效，增加人工清理 Kanban DB 与重派任务成本。
- 运行态教训未回流到项目源，会造成下一次同步或迁移时再次复现同类事故。

### 2.3 触发原因

2026-06-25 RFC-03-006 流水线实跑中，Round 1 冒烟测试发现 worker 由于同名 skill collision 直接 exit 1。修复时临时删除了 4 个 worker profile 副本并保留 yquant 主 profile 副本，但源目录尚未吸收运行态独有教训与 journal，需要治理为长期规则。

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 项目源 `skills/infra/ai-coding-pipeline/SKILL.md` 吸收运行态独有 P-1~P-4 教训。
- [ ] 项目源 `references/real-run-journal-2026-06-25.md` 存在，内容与 yquant 主 profile 运行态 journal 一致。
- [ ] yquant 主 profile 保留 `skills/infra/yquant-ai-coding-pipeline/` 副本，以支持 cwd 不在项目目录的 orchestrator 场景。
- [ ] `yquantprincipal`、`yquantdeveloper`、`yquanttester`、`yquantreviewer` 4 个 worker profile 不保留同名 skill 副本。
- [ ] `find ~/.hermes/profiles -name "SKILL.md" -path "*yquant-ai-coding-pipeline*"` 只输出 yquant 主 profile 一行。
- [ ] Hermes 加载 `yquant-ai-coding-pipeline` 不再报 Ambiguous，worker 能进入对话循环。

### 3.2 非目标（Out of Scope）

- [ ] 不修改 Hermes core 的 skill discovery / collision 机制。
- [ ] 不修改 Hermes 升级脚本或安装器。
- [ ] 不修改任何 profile `config.yaml` 的模型、fallback、toolsets 配置。
- [ ] 不改变 AI Coding Pipeline 的核心阶段路由、角色分工和 Kanban 创建规则。
- [ ] 不迁移既有 Kanban DB 历史任务或清理历史 crashed run。

## 4. 整体设计

### 4.1 核心设计哲学

把项目源目录作为长期事实源，把 profile 副本降级为 yquant 主 profile 的运行态 cache；worker profile 一律通过共享 workspace 读取项目源，避免同名副本与源目录并存。

### 4.2 架构总览

```text
Canonical source:
  /home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/
    SKILL.md
    references/*.md

Runtime cache kept:
  ~/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline/

Runtime copies forbidden:
  ~/.hermes/profiles/yquantprincipal/skills/infra/yquant-ai-coding-pipeline/
  ~/.hermes/profiles/yquantdeveloper/skills/infra/yquant-ai-coding-pipeline/
  ~/.hermes/profiles/yquanttester/skills/infra/yquant-ai-coding-pipeline/
  ~/.hermes/profiles/yquantreviewer/skills/infra/yquant-ai-coding-pipeline/

Worker discovery:
  HERMES_HOME=~/.hermes/profiles/<worker>/
  workspace_path=/home/pascal/workspace/yquant-investment
  -> load project source skill only
```

### 4.3 模块分工

- 项目源 skill：保存 pipeline 规则、P-1~P-4 教训、journal 引用，是长期维护入口。
- yquant 主 profile 副本：运行态 cache，用于 orchestrator 在非项目 cwd 下仍可加载 pipeline skill。
- worker profile：不保存该 skill 副本，仅通过 `workspace_path` 发现项目源。
- Kanban task body：继续显式传入 `workspace_kind="dir"` 与 `workspace_path="/home/pascal/workspace/yquant-investment"`。

## 5. 详细设计

### 5.1 业务流程（Flow）

1. 读取项目源 SKILL 与 yquant 主 profile 运行态 SKILL，确认差异。
2. 将运行态独有的 2026-06-25 教训合并回项目源：
   - P-1：Skill name collision 让 worker 永远进不了对话循环。
   - P-2：dispatcher 透明跑 fallback 链，任务名义 assignee 与实际模型可能不一致。
   - P-3：Kanban DB 任务 ID 不存在时不能用 `parents=[]` 强行串联。
   - P-4：`workspace_path` 必须用共享项目目录。
3. 将运行态 `references/real-run-journal-2026-06-25.md` 复制到项目源 references。
4. 更新源 SKILL 的同步策略：只同步到 yquant 主 profile，并删除 4 个 worker profile 副本。
5. 删除 worker profile 同名 skill 副本。
6. 运行验收命令，确认只剩 yquant 主 profile 一份副本且模型自检正常。
7. 通过 Hermes skill load / 测试 Kanban worker 验证不再 Ambiguous。

### 5.2 数据模型（Data Model）

本 RFC 不引入业务数据模型。治理对象是文件系统路径集合：

| 实体 | 类型 | 约束 | 说明 |
|---|---|---|---|
| canonical_skill_dir | path | 必须存在 | 项目源目录 |
| orchestrator_runtime_copy | path | 必须存在 | yquant 主 profile 运行态副本 |
| worker_runtime_copy | path | 必须不存在 | 4 个 worker profile 同名副本 |
| real_run_journal | markdown file | 必须存在且 md5 一致 | 2026-06-25 实跑复盘 |

### 5.3 接口契约（API Contract）

本 RFC 不新增程序 API。对运维与 worker 派发的操作契约如下：

```bash
# 验证副本数量
find ~/.hermes/profiles -name "SKILL.md" -path "*yquant-ai-coding-pipeline*"

# 同步项目源到 yquant 主 profile cache
mkdir -p /home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline
cp -a /home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/. \
  /home/pascal/.hermes/profiles/yquant/skills/infra/yquant-ai-coding-pipeline/

# 删除 worker profile 副本
for p in yquantprincipal yquantdeveloper yquanttester yquantreviewer; do
  rm -rf "/home/pascal/.hermes/profiles/$p/skills/infra/yquant-ai-coding-pipeline"
done
```

### 5.4 AI 模型设计

不涉及模型能力变更。P-2 仅要求在高价值任务中观察实际模型 fallback，避免误把 fallback 模型产物当作 primary 模型产物。

## 6. AI 实装规范

### 6.1 必须执行

- 先备份或记录项目源与运行态 SKILL 的 checksum，再合并内容。
- 只修改 `skills/infra/ai-coding-pipeline/` 与本 RFC/SPEC 相关文档。
- 删除 worker profile 副本时只删除 `skills/infra/yquant-ai-coding-pipeline/` 这一目录，不动其他 skill。
- 验证命令输出必须保存在完成 handoff 中。

### 6.2 先询问再执行

- 修改 Hermes core、升级脚本、profile `config.yaml` 或 gateway 配置。
- 删除 yquant 主 profile 运行态副本。
- 改变 pipeline 角色路由或阶段依赖链。

### 6.3 绝对禁止

- 删除 `~/.hermes/profiles/<profile>/skills/` 下无关目录。
- 把 secrets、provider token 或完整 profile config 写入文档。
- 为了通过验收而创建空的 worker profile skill 占位目录。

## 7. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| 合并遗漏运行态教训 | 中 | 中 | diff 源 SKILL 与运行态 SKILL；验收 grep P-1~P-4 | 从 yquant 主 profile 副本重新提取 |
| 删除错 profile 目录 | 低 | 高 | rm 命令写死精确路径，只针对 4 个 worker profile 同名 skill | 从项目源重新同步目标 profile 或恢复备份 |
| yquant 主 profile cwd 不在项目目录时找不到 skill | 中 | 中 | 保留 yquant 主 profile runtime cache | 临时从项目源 cp 到 yquant profile |
| worker profile 仍发生 collision | 中 | 高 | find 验证只剩 yquant 主 profile 一行；测试 worker 启动 | 继续排查其他同名 skill 路径 |
| 运行态 cache 与项目源再次漂移 | 中 | 中 | 文档明确先改项目源，再同步 yquant 主 profile | 后续增加自动同步脚本（另 RFC） |

## 8. 备选方案

### 8.1 删除所有 profile 副本，只保留项目源

优点：最纯粹的单一事实源。缺点：yquant 主 profile 在 cwd 不在项目目录时可能无法加载 pipeline skill。最终不选用。

### 8.2 所有 profile 均保留副本，并改名避免 collision

优点：每个 worker 离线可加载。缺点：需要重命名 skill 或改 task skills，破坏现有调用习惯，并增加同步漂移风险。最终不选用。

### 8.3 修改 Hermes skill discovery 忽略重复

优点：从平台层解决 collision。缺点：涉及 Hermes core 行为变更，风险和范围超过本次修复。最终不选用。

### 8.4 只保留 yquant 主 profile 副本，worker profile 无副本

优点：兼顾 orchestrator 可用性与 worker 无 collision；最小变更；符合 2026-06-25 实跑验证。最终选用。

## 9. 验收标准

### 9.1 功能验收

- `find ~/.hermes/profiles -name "SKILL.md" -path "*yquant-ai-coding-pipeline*"` 只输出 yquant 主 profile 一行。
- 项目源 `SKILL.md` 包含 P-1、P-2、P-3、P-4 四条 Pitfalls。
- 项目源 `references/real-run-journal-2026-06-25.md` 存在且与 yquant 主 profile 运行态 journal md5 一致。
- Hermes 加载该 skill 不再输出 `Ambiguous skill name`。
- `python3 skills/common/utils/print_agent_models.py` 正常输出。
- 一个测试 Kanban worker 能进入对话循环并完成 smoke task。

### 9.2 非功能验收

- 不修改 profile 模型/fallback 配置。
- 不改变 pipeline 核心路由规则。
- 不引入新依赖。
- 不写入 secrets 或 token。

## 10. 落地计划

### 10.1 阶段划分

1. RFC/SPEC：产出本 RFC 与对应 SPEC，定义文件、命令、验收契约。
2. Design：定义精确操作顺序、回滚步骤、验证脚本与 handoff。
3. Implement：合并 SKILL，复制 journal，同步 yquant cache，删除 worker 副本。
4. Verify：运行 find、md5、skill load、model script、worker smoke task。
5. Review：审查 diff、验证输出与 RFC/SPEC/Design 一致性。

### 10.2 任务清单

| 阶段 | 负责人 | 交付物 |
|---|---|---|
| RFC/SPEC | yquantprincipal | RFC-10-004、SPEC-10-004 |
| Design | yquantprincipal | DESIGN-10-004 |
| Implement | yquantdeveloper | SKILL/journal/profile 副本修复 |
| Verify | yquanttester | 验证报告 |
| Review | yquantreviewer | 独立 review 结论 |

## 11. 开放问题

- 是否需要后续新增一个自动同步脚本，避免项目源与 yquant 主 profile cache 再次漂移？本 RFC 不处理。
- Hermes core 是否应支持同名 skill 的优先级策略或去重策略？本 RFC 不处理。

## 12. 扩展：Quick Flow 流程模式

### 12.1 背景与动机

当前 AI Coding Pipeline 提供两种流程模式：
- **完整流程（7 阶段）**：Intake → RFC/SPEC → Design → Implement → Verify → Review → Closeout。适用于高风险、跨模块、涉及交易/风控的非平凡改动。
- **轻量流程（3 阶段）**：Intake → Implement → Verify → Closeout。适用于单文件低风险 bug fix。

实践中发现两种模式的中间存在大量"中风险、明确需求、改动范围 3-8 个文件、需要三层文档但不需独立 Reviewer"的场景。完整流程对这类任务过于冗余（多 1 个 Review 阶段 + 多 1 个 Kanban task），轻量流程又缺少 RFC/SPEC/Design 三层文档保障。Quick Flow 填补这一空缺。

### 12.2 目标与非目标

#### 12.2.1 目标

- 提供 5 阶段流程：Intake → RFC/SPEC/Design → Implement → Verify → Closeout。
- RFC/SPEC/Design 三层文档由一个 Kanban task 产出，保持三层独立但减少 stage count。
- 保留 Verify 作为客观质量屏障——去掉 Review 是合理的，因为 Reviewer 的主要价值（架构一致性审查）在"有完整三层文档 + Verify"场景下可替换为 Closeout 自审清单。
- 与完整流程共享相同的 profile assignee 路由（`yquantprincipal` / `yquantdeveloper` / `yquanttester`）。

#### 12.2.2 非目标

- 不引入"无文档"流程（轻量流程已覆盖）。
- 不合并 Verify + Review 为一个阶段。
- 不改变 P-1~P-11 pitfalls 的核心修复策略。
- 不在 Quick Flow 中引入新的 profile 或角色。

### 12.3 触发条件

Quick Flow 由 orchestrator 在 Intake 阶段基于以下规则自动判定，也可由用户显式指定：

| 维度 | Quick Flow 条件 | 说明 |
|---|---|---|
| 风险等级 | 中等或以下 | 不涉及核心交易、真实资金、生产数据库 schema 变更 |
| 需求明确度 | 需求已明确 | 无需多轮探索性讨论 |
| 改动范围 | 3-8 个文件 / 单模块 | 超 8 文件或跨多模块仍应走完整流程 |
| 影响面 | 非核心数据/风控 | 不修改 `portfolio_position`、交易执行、风控限额 |
| 文档需求 | 需要三层文档 | 需要 RFC/SPEC/Design 但不需要独立 Reviewer |

用户显式触发词："走 Quick Flow"、"按快捷流程"、"5 阶段快速"。

### 12.4 适用边界（仍走完整流程的场景）

以下场景即使文件数 ≤ 8，也必须走完整流程（含 Review）：

- 修改 MongoDB 写入路径（`portfolio_position`、`portfolio_trade`、`stock_pool` 等核心集合）。
- 修改交易/风控逻辑（`risk/`、`trading/` 模块）。
- 修改外部消息发送（cron 报告推送、telegram/email 通知）。
- 新增外部 API 集成或依赖升级。
- 跨 2 个以上模块的架构变更。
- 用户明确要求走完整流程或独立 Review。

### 12.5 与已有流程的关系

| 特征 | 完整流程（Full） | 快捷流程（Quick） | 轻量流程（Light） |
|---|---|---|---|
| 阶段数 | 7 | 5 | 3（实际 4，含 Intake/Closeout） |
| Kanban task 数 | 6 | 4 | 2 |
| RFC/SPEC/Design | 独立文件，分 2 task | 独立文件，1 task 产出 | 无 |
| Verify | 独立 tester | 独立 tester | 独立 tester |
| Review | 独立 reviewer | **无**（以 Closeout 自审替代） | 无 |
| 适用场景 | 高风险、核心逻辑、跨模块 | 中风险、明确需求、≤8 文件 | 单文件 bug fix、文案 |

三层流程由 orchestrator 在 Intake 阶段根据触发条件选定，并在首次 Kanban task body 中显式声明流程模式。

### 12.6 Kanban 任务链

```
T1 RFC/SPEC/Design   assignee=yquantprincipal   (1 task → 3 份文档)
T2 Implement          assignee=yquantdeveloper   parents=[T1]
T3 Verify             assignee=yquanttester      parents=[T2]
T4 Closeout           assignee=<orchestrator>    parents=[T3]
```

任务链创建时机：Quick Flow 的 4 张 Kanban task 必须在 Intake 阶段由 orchestrator 一次性预创建，而不是在前序任务 done 后临时串行创建下一张。创建结果必须满足：

- T1 当下进入 `ready`，由 dispatcher 立即 claim/spawn。
- T2/T3/T4 在同一次 Intake 编排中以 `todo` 状态入库。
- T2 必须设置 `parents=[T1]`。
- T3 必须设置 `parents=[T1, T2]` 或至少 `parents=[T2]`；推荐包含完整上游链以便审计。
- T4 必须设置 `parents=[T1, T2, T3]` 或至少 `parents=[T3]`；推荐包含完整上游链以便 Closeout 读取完整前置产出。
- 后续衔接依赖 Hermes Kanban DB 状态机（`task_links` + `recompute_ready` + `dispatch_once`）自动 promote+spawn，不依赖 orchestrator 主 session 持续存活。

该规则来自 2026-06-30 yinglong Quick Flow 5h44m 卡死事件：当 Quick Flow 由 orchestrator 在每个阶段完成后临时创建下一张 task 时，任何 watcher 静默死亡、主 session 中断或通知丢失都会让链路停在“前序 done 但后序 task 尚不存在”的不可恢复状态。一次性预创建把衔接责任下沉到 Kanban DB 状态机，与完整流程同源。

可执行契约见 SPEC-10-004 §13.1 / §13.10；实现时序图见 DESIGN-10-004 §3.1。

对比完整流程：

```
T1 RFC/SPEC           assignee=yquantprincipal
T2 Design             assignee=yquantprincipal   parents=[T1]
T3 Implement          assignee=yquantdeveloper   parents=[T2]
T4 Verify             assignee=yquanttester      parents=[T3]
T5 Review             assignee=yquantreviewer    parents=[T4]
T6 Closeout           assignee=<orchestrator>    parents=[T5]
```

关键差异：RFC/SPEC/Design 合并为 1 个 Kanban task，去掉了独立的 Design task 和 Review task，节省 2 个 Kanban task；但 Quick Flow 与完整流程一样，必须在 Intake 阶段一次性创建完整依赖链，不能把“创建下一阶段 task”交给进程层主动推进。

### 12.7 Closeout 自审清单（替代 Reviewer）

由于 Quick Flow 无独立 Reviewer，orchestrator 在 Closeout 阶段必须执行自审清单（详见 DESIGN-10-004 §3.6），至少覆盖以下方面：

衔接机制自审：Closeout 首先检查本次 Quick Flow 是否在 Intake 阶段一次性预创建 T1-T4，并确认 T2/T3/T4 的 parent links 均存在。若发现 T2/T3/T4 是在前序 done 后才临时创建，必须记录为流程缺陷；若该缺陷导致阶段延迟或断链，应补充复盘并禁止将该运行作为 Quick Flow 标准样例。

- SPEC 契约与实际实现是否一致。
- 文件改动清单是否符合 Design 预期。
- 验收标准（RFC §9）是否全部通过。
- 风险应对（RFC §7）是否已验证或降级可接受。
- 代码风格和项目约定是否遵守。
- 测试覆盖是否满足 Design §5 要求。
- 是否有遗漏的边缘情况或异常降级路径。
- 三方依赖是否有新增/升级且已记录。
- 文档引用关系是否正确（RFC → SPEC → Design → 实现）。
- Git diff 范围是否在产品边界内且不包含无关改动。
- worker 日志有无异常（fallback、crash、timeout）。

### 12.8 风险与降级

| 风险 | 概率 | 影响 | 应对 | 降级 |
|---|---|---|---|---|
| Closeout 自审不充分，遗漏 Review 级别问题 | 中 | 中 | 自审清单 ≥10 项 + orchestrator 必须执行 | 发现遗漏后补开 Review task |
| Quick Flow 误用于高风险场景 | 低 | 高 | Intake 阶段触发条件硬性检查（§12.3-§12.4） | orchestrator 可在任意阶段升级为完整流程 |
| 三层文档质量因合并 task 而下降 | 中 | 中 | SPEC-10-004 Quick Flow 契约明确三层独立 + 结构完整 | T2 Implement 发现文档不足时退回 T1 |
| orchestrator 串行创建后续 task 导致断链 | 中 | 高 | Intake 一次性预创建 T1-T4，依赖 DB 状态机自动 promote | 若已发生断链，立即补建缺失 task 并记录 P-12 复盘 |

轻量流程（Light Flow）结构上 task 数更少、无三层文档阶段，串行创建风险低一个数量级；但其 Implement→Verify 衔接也应优先采用预创建 parent link，而不是依赖进程层持续在线。

## 13. 参考资料

- `skills/infra/ai-coding-pipeline/SKILL.md`
- `skills/infra/ai-coding-pipeline/references/real-run-journal-2026-06-25.md`
- `skills/infra/ai-coding-pipeline/references/document-layers.md`
- `skills/infra/ai-coding-pipeline/references/spec-from-rfc.md`
- Hermes Kanban worker lifecycle guidance

## 14. 版本修订说明

- 当前版本：V1.2
- 修订日期：2026-06-30
- 修订摘要：Quick Flow 衔接机制由 orchestrator 串行创建后续 task 改为 Intake 一次性预创建 T1-T4，并通过 Kanban DB parent links 与 dispatcher 自动 promote 机制衔接，与 Full Flow 同源。
