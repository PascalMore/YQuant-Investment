# RFC-10-013：MiniMax M3.1 Hermes core Anthropic adaptive effort 回移

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-10-20 |
| 最后更新 | 2026-10-20 |
| 版本号 | V1.2 |
| 所属模块 | 10_infra（基础设施 / hermes-agent core 供应商适配层） |
| 依赖 RFC | RFC-10-005-hermes-auto-upgrade（升级链路背景；本 RFC 不修改其内容） |
| 替代 RFC | 无 |
| 关联 SPEC | docs/spec/10_infra/SPEC-10-013-minimax-m31-hermes-core-adaptive-effort.md |
| 关联 Design | docs/design/10_infra/DESIGN-10-013-minimax-m31-hermes-core-adaptive-effort.md |
| 流程模式 | Full Flow 补救：原 T1 缺独立 Design，旧 D1 仅历史候选；本次 replacement D2 `t_e0387995` 独立 Design reconciliation → V2 `t_087420b8` 只读 Verify → R2 `t_682914e2` 独立 Review |
| AI 适配 | Hermes Kanban（yquantprincipal → yquantdeveloper → yquanttester → yquantreviewer） |
| 标签 | #infra #hermes-agent #anthropic #minimax #effort #backport |

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-10-20 | 初始创建：选 B，固定 upstream PR #127088 head 6f3182249d1e99bfa6e8248c2199dcbfaf94f890 的 Anthropic 子集，三文件 +85/-9 | YQuant-Codex-Principal |
| V1.1 | 2026-10-20 | 旧 D1 历史候选：同步 SPEC/DESIGN V1.1，纠正补丁来源、统计、当前候选/只读边界与历史流程违规记录；未作正式验收，不回填历史阶段 | YQuant-Codex-Principal |
| V1.2 | 2026-10-20 | replacement D2 最小收尾：区分固定 PR 与本地回移统计、profile 待迁移事实、旧 D1 候选与本次正式阶段；按 Pascal 最新裁定复用哈希关联的主控真实只读测试结果，不重复 pytest；同步 SPEC/DESIGN V1.2，功能契约不变 | YQuant-Codex-Principal |

## 1. 执行摘要（Executive Summary）

Hermes Agent core 的历史干净基线 HEAD `3fecce0a67bf243ef3a4d5d0d4a6eea28422fc37` 只对 Claude/Kimi 做 adaptive thinking 判定，MiniMax M3.1 系落入手工 budget_tokens 路径；Intake 记录该字段不映射到 effort，导致 `/reasoning` 档位失效。核心方案仍为选 B——采用 upstream PR #127088 head `6f3182249d1e99bfa6e8248c2199dcbfaf94f890` 的 Anthropic-side 子集。当前树已应用、未提交，本地三文件 +85/-9；可执行标准补丁为 `minimal-backport.patch`，其中 test +63/-3 已包含 `MiniMax-M3.1-Flash` 与 `minimax/MiniMax-M3.1-Flash` 两项 GA 数据，不再额外增加两行。replacement D2 `t_e0387995` 仅纠正文档并核对证据；最终功能与合规放行须由后续 V2/R2 fresh 只读 Verify/Review 判定，旧 D1 候选及旧 T4 PASS 不作为依据。

## 2. 背景与动机（Background & Motivation）

### 2.1 现状痛点

Intake 计划将 YQuant 各 Hermes profile 迁移到 MiniMax M3.1 系（目标为经 `https://api.minimaxi.com/anthropic` 的 Anthropic-Messages 端点）；本次目标配置仍未修改，不表示当前各 profile 已使用 M3.1。该端点契约为 `thinking.type=adaptive` + `output_config.effort ∈ {low, medium, high, xhigh, max}`，默认 `max`，发送 `thinking: {"type": "disabled"}` 返回 HTTP 400。历史未打补丁的 `_supports_adaptive_thinking()` 只覆盖 Claude/Kimi，M3.1 因而落入手工 `budget_tokens` 路径；当前候选已补入 M3.1 判定。本 D2 不迁移 profile、不重启 Gateway；源码补丁不等于 profile 迁移或线上进程已加载候选。

### 2.2 upstream 状态核验（2026-10-20 Intake 历史快照，非本次实时查询）

- upstream main 快照 `300a3977ed7a2409b0ba152f1ba54458b0263815` 与 latest release v0.22.2（2026-10-15）的判定均无 M3.1 分支。
- PR #127088（M3.1 Anthropic adaptive/effort + OpenAI 路由 + 文档）与 PR #141412（模型目录 + OpenAI none→low）经 GitHub API 两次查询均为 open、merged=false；不以非空 merge_commit_sha 误判已合并，Git ancestry 检查显示两个 PR head 均非 main 祖先。
- 固定 PR #127088 head 的 Anthropic 子集与本地回移使用不同基线，不将 PR 自身 diff 的统计混同为本地三文件 +85/-9，也不以 PR 整包统计限定本地 allowlist。本地仅复用必要生产逻辑与测试，省略非必要注释 hunk；两 GA 名称是本地测试增强。生产 helper/classifier 与固定 head 的函数文本/AST 一致，完整本地改动以 minimal 标准补丁为准（见 §4.1）。

### 2.3 业务价值与触发原因

effort 档位是 V2 profile 方案（Developer=high、Tester/Reviewer=medium、压缩任务=low、辅助视觉=medium）的成本与质量旋钮；若计划迁移到 M3.1 却未修复该路径，请求会落到服务端默认 max，而不是所选 effort；这不是当前各 profile 成本或配置状态的结论。触发原因：风险驱动 + 成本驱动。上游修复已存在且经隔离探针验证（7/7 线上场景通过、35 个非目标请求形状不变），自研实现没有增量价值。

## 3. 目标与非目标（Goals & Non‑Goals）

### 3.1 必须目标（Must‑Have）

- [ ] G1：采用选 B——生产逻辑原样复用 PR #127088 head `6f3182249d1e99bfa6e8248c2199dcbfaf94f890` 的 Anthropic-side 修复（AST 级一致），落地为 `agent/anthropic_endpoints.py`（+15/-0）、`agent/anthropic_adapter.py`（+7/-6）两个生产文件。
- [ ] G2：M3.1 触发器 `_model_name_is_minimax_adaptive` 精确识别 `minimax-m3.1` / `minimax-m3-1` 前缀（含点号/横杠拼写与 vendor 前缀），不误吞 M3/M3.10/M31 等近似名称。
- [ ] G3：M3.1 进入既有 adaptive 分支后，wire 契约为 `thinking.type=adaptive` + `output_config.effort` 五档 low/medium/high/xhigh/max；`minimal→low` 映射；disable → 不发 `thinking`、不发 `output_config`；legacy manual 模型（M3/M2.x、legacy Claude）行为逐字节不变。
- [ ] G4：`tests/agent/test_minimax_provider.py`（+63/-3）保留 upstream 五个测试方法，仅将测试数据元组扩入 GA 名称 `MiniMax-M3.1-Flash` 与 `minimax/MiniMax-M3.1-Flash`；全部测试在 hermes-agent 仓库内通过。
- [ ] G5：来源固定 PR head，完整改动以 `minimal-backport.patch` 为可执行标准补丁（§4.1）；`materialized-patch.patch` 仅为不完整内容参照。源码 diff 超出三文件 allowlist 即 FAIL；既有 `m31-port.patch` 单列为背景产物并保留。

以上 checkbox 为待 fresh Verify/Review 判定的验收目标，不表示当前仍待重新实现。五模型字符串乘五档为 25 个内部组合，目标类仅 5 个 pytest 方法；test +63 已包含 GA 两项，`diff --stat` 的 66 changed 是 +63/-3，而非 66 additions。

### 3.2 非目标（Out of Scope，绝对不引入）

- [ ] `agent/reasoning_effort.py`（PR 内 MINIMAX_M31_EFFORTS tuple；Anthropic-only 路径不使用）。
- [ ] `plugins/model-providers/minimax/__init__.py`（OpenAI-compat 路由）。
- [ ] `plugins/model-providers/custom/__init__.py`（none→low OpenAI-compat 处理）。
- [ ] `website/docs/user-guide/configuration.md`（上游文档注记）。
- [ ] `tests/plugins/model_providers/test_minimax_profile.py`（OpenAI-compat 测试）。
- [ ] 整包 cherry-pick PR #127088 或采用 PR #141412；不整仓升级、不新增 provider、不换端点、不升级 SDK、不改 CLI/transport/辅助客户端/MCP。
- [ ] 与 Hermes profile / MCP / cron / 配置 / 数据库 / 交易相关的任何文件；V2 profile 档位配置迁移与 gateway 重启均不在本 RFC 范围（后者为独立人工动作）。
- [ ] 不修改 RFC-10-005/10-006 及其后续 SPEC/DESIGN；不修改 hermes-agent 之外的任何仓库代码。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

零自研、确定性回移：来源固定 PR #127088 head `6f3182249d1e99bfa6e8248c2199dcbfaf94f890`，完整可执行标准补丁为 `minimal-backport.patch`（历史基线上有 apply-check 记录）。`materialized-patch.patch` 使用临时路径/裸头，是不可 git apply 的不完整内容参照，遗漏 endpoints 注释及 docstring-only 内容；不得宣称其 apply-check 通过或与标准补丁完整逐块相等。生产函数按固定 PR head 做函数文本/AST 核对，完整改动按 minimal 的 hunk 内容核对（允许位置偏移）。选择上游是为尽量降低未来冲突面，不保证零冲突。当前候选已应用，本次及后续 fresh Verify/Review 均不得清场或重放补丁。

### 4.2 架构总览

改动只落在 Anthropic-Messages 请求构造链的模型判定点，一行分支扩展：

```text
/reasoning 配置 (reasoning_config)
        │
        ▼
build_anthropic_kwargs (agent/anthropic_adapter.py)
        │
        ├─ _supports_adaptive_thinking(model)
        │       ├─ _model_name_is_kimi_family(model)            （不变）
        │       ├─ _model_name_is_minimax_adaptive(model)       ★ 新增分支
        │       └─ _is_claude_model(model) and not legacy       （不变）
        │       │
        │       ├─ True  → thinking={"type":"adaptive"} + output_config={"effort": …}
        │       └─ False → 既有 manual budget_tokens 路径（逐字节不变）
        ▼
POST https://api.minimaxi.com/anthropic (Anthropic-Messages)
```

### 4.3 模块分工

| 模块（hermes-agent 内路径） | 职责 | 本 RFC 改动 |
|---|---|---|
| `agent/anthropic_endpoints.py` | 端点/模型族判定 helpers | 新增 `_MINIMAX_ADAPTIVE_MODEL_PREFIXES` 常量与 `_model_name_is_minimax_adaptive()` |
| `agent/anthropic_adapter.py` | Anthropic 请求 kwargs 构造 | 导入新 helper；`_supports_adaptive_thinking()` 加入 M3.1 分支；docstring 更新 |
| `tests/agent/test_minimax_provider.py` | MiniMax 供应商测试 | 新增 `TestMinimaxM31AdaptiveEffort`（五档/minimal/disable/legacy/lookalike 五法） |

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

- 触发条件：规范化后模型名等于 `minimax-m3.1` / `minimax-m3-1`，或以该前缀加 `-` 开头（大小写/空白/vendor 前缀容忍）；不是任意字符串前缀匹配，M3.10 不匹配。
- 核心处理逻辑：`reasoning_config.effort` 直通 `output_config.effort`（`minimal` 映射 `low`，其余五档原样）；`reasoning_config.enabled=False` 时省略 `thinking` 与 `output_config` 两个字段（省略是 M3.1 唯一接受的"关"）；`enabled=True` 时 `thinking={"type": "adaptive"}` 且不含 `budget_tokens`。
- 正常分支：五档均产生 HTTP 200（已由 Intake 隔离探针在真实端点验证）。
- 异常降级分支：无新增错误路径——匹配失败自动落回既有 manual 路径，行为与改动前逐字节一致。

### 5.2 数据模型（Data Model）

无数据实体。本改动是请求形状（wire format）分支，不引入字段持久化、状态或 schema。

### 5.2bis 持久化策略（Persistence Strategy）

无持久化变更仅指请求构造运行逻辑：内存 kwargs 不新增落盘、数据库写入或跨会话状态，既有会话日志机制不受影响。不禁止已授权的源码补丁、三份受控文档或各执行者自身 scratch 测试证据写入；本 D2 只允许修改本三文档并写自己的 scratch。profile 迁移与 Gateway 重启继续 out-of-scope。

### 5.3 接口契约（API Contract）

对外接口不变（`build_anthropic_kwargs` 签名与返回类型不变）；wire 契约详见 SPEC-10-013 V1.2 §3/§4：启用时 M3.1 使用 `thinking.type=adaptive` 与 `output_config.effort`；disable 时两字段全省略，禁止发送服务端拒绝的 disabled 值。这不是宣称补丁前每次 disable 都发送 disabled。非目标模型请求形状不变是兼容性要求；35 个非目标配置一致为 Intake 历史探针证据，不冒充本次验证。

### 5.4 AI 模型设计（如有）

不适用：本 RFC 本身就是模型接入层的修复，不涉及新模型选型或特征工程。

## 6. AI 实装规范（AI Implementation Rules）

### 6.1 必须执行

- 当前只读核对以 recovery-baseline.json、保护清单与本 D2 前后核验交接为准（见 DESIGN-10-013 V1.2 §7）；旧 D1 证据仅作历史参照，保留已应用的源码、测试与 `m31-port.patch`，不重做 Implement。
- 单指令只做一件事；所有变更保留可追溯记录（diff、测试输出）。

### 6.2 先询问再执行

- 当前候选与 recovery baseline 不符或需任何回滚：停止回报，必须取得新的明确范围授权；历史 apply-check 不授权当前重放或回滚。

### 6.3 绝对禁止

- 手工改写生产函数体；引入 §3.2 文件；修改 profile/MCP/cron/配置/数据库/交易；修改 10-005/10-006。共享树禁止 reset/stash/clean/restore/checkout 路径回退、逆向 apply 或重新 apply，禁止隐式清理其他产物。审批拒绝或超时立即 STOP，不得换命令、包装器、执行器或委派完成被拒动作，不得降低审批模式或使用 yolo。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| PR #127088 后续被上游改写或关闭 | 中 | 低 | 来源固定 head SHA 与 minimal 标准补丁，不依赖分支最新状态 | 本次仅只读核对，不重新应用 |
| 当前候选与 recovery baseline 漂移 | 低 | 中 | HEAD/SHA-256 与 path-filtered diff 核验 | 保留现场，停止并回报，不自动恢复 |
| 模型名误匹配（lookalike 型号进入 adaptive 分支） | 低 | 中 | 精确前缀；10 个字符串反例及 None 边界 | 如失败停止回报，改动或回滚需新授权 |
| disable 契约影响调用方 | 低 | 低 | 仅 M3.1 分类扩展；非目标形状由 fresh 验证 | 依 DESIGN §6 取得新授权，不自动回退 |
| 上游 CI 状态未知（check-runs 0 个） | 中 | 低 | 不宣称上游全绿；以本仓定向测试 + 独立 Verify 为准 | 同上 |

## 8. 备选方案（Alternatives Considered）

- 备选 1（已选，选 B）：采用 PR #127088 固定 head 的 Anthropic 子集。优点：复用上游、最小 diff、尽量降低未来冲突面，不保证零冲突。缺点：Intake 时 PR 未 merged，需维护固定来源。最终采用。
- 备选 2：整包 cherry-pick PR #127088。优点：与上游完全同步。缺点：引入 OpenAI-compat 路由与文档，违反本任务 Anthropic-only 边界。不采用。
- 备选 3：采用 PR #141412（模型目录 + none→low）。优点：选择器展示完整。缺点：作用于 OpenAI 路径与目录展示，本地路由为 anthropic_messages 且显式填模型 ID，无增量价值。不采用。
- 备选 4：等 upstream merge 后升级。优点：零维护。缺点：merge 时间不可控，延后计划迁移到 M3.1 时所需的 effort 支持。不采用。
- 备选 5：自研等价实现。优点：无。缺点：与上游产生不必要分叉，违反"与上游修改一致"的既定决策。不采用。

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收

- 五档 effort 在 M3.1（含 GA 名称）上产生 `output_config={"effort": …}` 且 `thinking.type=adaptive`、无 `budget_tokens`（SPEC A-101）。
- `minimal→low` 映射；disable → 不含 `thinking`/`output_config`（SPEC A-102/A-103）。
- lookalike 名称（M3/M31/M3.10/minimax-m30 等 10 例）不匹配；vendor 前缀/日期后缀匹配（SPEC A-105）。
- M3/M2.x legacy manual 不变（SPEC A-104）；Claude/Kimi 等非目标回归（SPEC A-106）。

### 9.2 非功能验收

- 源码允许清单：hermes-agent 内恰 3 文件 +85/-9（SPEC A-201），既有 `m31-port.patch` 背景产物单列保留；YQuant 仓库仅三份文档（SPEC A-202）。
- 定向测试采用主控已真实只读执行的两文件结果（106 passed in 5.45s）；保护源码/补丁哈希与该验证基线一致时复用，不重复 pytest。V2 仅验文档 delta、证据与哈希关联，R2 审查证据，Closeout 汇总；源码哈希漂移则停止回报，不自动重跑或扩范围。三文件源码 diff 与既有 `m31-port.patch` 背景产物分开归属，不清理 dirty（SPEC A-203/A-204）。
- 本三件套不修改 RFC/SPEC/DESIGN 10-005、10-006 及其后续（SPEC A-202/A-205a）。

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

原流程标为 Full Flow，却由 T1 `t_4b00d600` 合并产出 RFC/SPEC/Design，直接衔接 T2 Implement，缺少独立 Design，是 orchestrator 编排偏差。旧 D1 `t_3a4c326a` 经 auto-decomposer 改写 body/拆出子卡，未完成正式验收；其 V1.1 正文仅为历史候选，不回填为 D1 已完成。2026-10-20 本次 replacement D2 `t_e0387995` 独立核对并最小收尾，正式交接至新 V2 `t_087420b8` → R2 `t_682914e2`；只读验证当前候选，不重跑旧 D1/其子卡、不重新实现。

### 10.2 任务清单

| 阶段 | 角色 | 工作区 | 交付 |
|---|---|---|---|
| 旧 T1 `t_4b00d600` | yquantprincipal | yquant-investment | 合并三件套；DESIGN §1/§7 及 handoff 已授权 minimal 为可执行补丁 |
| 旧 T2 `t_dff78d74` | yquantdeveloper | hermes-agent | 按 DESIGN 使用 minimal；body 误写 materialized 唯一来源和 test +65/-3，属 orchestrator 任务书错误，不是该来源选择未经授权 |
| 旧 T3 `t_cbb5108e` | yquanttester | hermes-agent | 任务书要求清理/重放；metadata 记录 reset 被拒后 restore，再 apply，属历史流程违规 |
| 旧 T4 `t_7b302fe4` | yquantreviewer | hermes-agent | 同样记录 reset 被拒后改用 restore/重放；旧 PASS 不作为本次最终放行依据 |
| 旧 D1 `t_3a4c326a` | yquantprincipal | yquant-investment | auto-decomposer 改写/拆卡，未正式验收；V1.1 仅历史候选，旧 Safety hold 继续约束旧卡 |
| replacement D2 `t_e0387995` | yquantprincipal | yquant-investment | 本次独立核对并最小纠正三正文至 V1.2；核心源与配置只读哈希，正式 handoff，不回填旧 D1 |
| fresh V2 `t_087420b8` → R2 `t_682914e2` | yquanttester → yquantreviewer | hermes-agent | V2 独立只读核对文档 delta 与证据/哈希关联，R2 审查证据；哈希一致时复用主控两文件真实结果，均不重复 pytest，Closeout 仅汇总；不迁移配置、不宣称线上升级 |

旧 T3 的 `baseline_restore_method` 与旧 T4 的 `reset_method_deviation` 均记录审批拒绝后换 restore 完成回退；orchestrator 错误清理/重放指令也负有责任。备份不使审批绕行合规；旧 T3 的 “No data lost” 自报不足以证明所有历史工作未丢失，也无证据断言另有数据损失。pre-restore diff 即便等于当前 path-filtered diff，也只证明该快照内容恢复。新测试 PASS 不洗白历史违规，本次补救仅恢复可依赖的当前只读证据。

## 11. 开放问题（Open Questions）

需求与范围无新待裁定项；功能、当前只读合规与最终放行尚待 V2/R2 fresh Verify/Review，不等于本 D2 未决需求。历史违规保留；线上加载状态未验证；profile 迁移与 Gateway 重启仍不属本 RFC。

## 12. 参考资料（References）

- upstream PR #127088（head `6f3182249d1e99bfa6e8248c2199dcbfaf94f890`）：M3.1 Anthropic adaptive/effort 修复。
- 不完整内容参照（不可 apply）：`/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-implementation-20261020/materialized-patch.patch`。
- 可执行标准补丁：`/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-upstream-comparison-20261020/minimal-backport.patch`（历史 apply-check 记录，不授权本次重放）。
- upstream 对照报告：同目录 `upstream-comparison.md`；验证明细 `exact-upstream-verification-run.txt`、`probe-results.json`、`verification-summary.json`。
- MiniMax adaptive thinking 契约：https://platform.minimax.io/docs/guides/text-generation#thinking
- Intake 基线：`/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-implementation-20261020/intake-baseline.json`。
- 当前候选基线与四份旧卡完整快照：`/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-recovery-20261020/` 下 `recovery-baseline.json`、`t_4b00d600.json`、`t_dff78d74.json`、`t_cbb5108e.json`、`t_7b302fe4.json`。
- 本次只读证据：`/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-final-20261020/` 下 `old-task-evidence.md`（四旧卡完整正文/metadata）、`function-provenance.md`（主控固定 PR 函数文本/AST 核验）、`protected-files.sha256`（11 项保护清单）；本 D2 核对当前函数文本与清单，不声称重跑 AST。
- 同步契约：[SPEC-10-013 V1.2](../../spec/10_infra/SPEC-10-013-minimax-m31-hermes-core-adaptive-effort.md)、[DESIGN-10-013 V1.2](../../design/10_infra/DESIGN-10-013-minimax-m31-hermes-core-adaptive-effort.md)。
