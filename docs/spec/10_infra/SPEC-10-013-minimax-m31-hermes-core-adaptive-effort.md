# SPEC-10-013：MiniMax M3.1 Hermes core Anthropic adaptive effort

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-10-20 |
| 最后更新 | 2026-10-20 |
| 版本号 | V1.2 |
| 来源 RFC | RFC-10-013-minimax-m31-hermes-core-adaptive-effort |
| 目标模块 | 10_infra / hermes-agent core（`agent/anthropic_*`） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer, YQuant-Reviewer-Principal |
| 流程模式 | Full Flow 补救：原 T1 缺独立 Design，旧 D1 仅历史候选；本次 replacement D2 `t_e0387995` 独立 Design reconciliation → V2 `t_087420b8` 只读 Verify → R2 `t_682914e2` 独立 Review |

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-10-20 | 初始创建：选 B 回移 PR #127088 Anthropic 子集，三文件 +85/-9，GA 测试数据增强 | YQuant-Codex-Principal |
| V1.1 | 2026-10-20 | 旧 D1 历史候选同步 RFC/DESIGN V1.1：纠正可执行补丁来源、统计、历史/当前验收与授权边界；未作正式验收，不回填历史阶段 | YQuant-Codex-Principal |
| V1.2 | 2026-10-20 | replacement D2 最小收尾：同步 RFC/DESIGN V1.2 的来源统计、待迁移及正式阶段定位；按 Pascal 最新裁定复用哈希关联的主控真实只读测试结果，不重复 pytest；功能与文件 allowlist 不变 | YQuant-Codex-Principal |

## 1. 需求摘要

为 Anthropic-Messages 请求构造引入 M3.1 adaptive effort，来源固定 upstream PR #127088 head `6f3182249d1e99bfa6e8248c2199dcbfaf94f890` 的必要 Anthropic 生产逻辑与测试，省略非必要注释 hunk；PR 自身 diff 不等于本地回移统计。当前本地候选已应用、未提交：endpoints +15/-0、adapter +7/-6、test +63/-3，合计 +85/-9；test 已包含本地增强 `MiniMax-M3.1-Flash` 与 `minimax/MiniMax-M3.1-Flash` 两 GA 名称，不再另加两行。完整可执行标准补丁为 `minimal-backport.patch`；`materialized-patch.patch` 不可 git apply，仅是不完整内容参照，不宣称其 apply-check 通过或完整逐块相等。M3.1 使用既有 adaptive 分支、disable 省略两字段，legacy manual 不变。replacement D2 `t_e0387995` 只修正文档并只读核对当前证据，之后 V2/R2 fresh Verify/Review 不清理或重放候选；目标 profile 仍待迁移，配置未修改，源码补丁不等于线上生效。

## 2. 范围

### 2.1 In Scope（allowlist，恰 3 文件 +85/-9）

- [ ] `agent/anthropic_endpoints.py`（+15/-0）：新增 `_MINIMAX_ADAPTIVE_MODEL_PREFIXES = ("minimax-m3.1", "minimax-m3-1")` 常量与 `_model_name_is_minimax_adaptive()` helper，与 PR #127088 head AST 一致。
- [ ] `agent/anthropic_adapter.py`（+7/-6）：import 块加入 `_model_name_is_minimax_adaptive`；`_supports_adaptive_thinking()` 增加 `or _model_name_is_minimax_adaptive(model)` 分支；docstring 同步为 "Kimi/Moonshot 与 MiniMax M3.1 系实现 adaptive 契约（`output_config.effort`）"。
- [ ] `tests/agent/test_minimax_provider.py`（+63/-3）：新增 `TestMinimaxM31AdaptiveEffort`（5 个测试方法），类 docstring 与断言同 upstream；测试数据元组 M31 扩入两 GA 名称（共五项：两 GA + upstream 三项 Preview/vendor-Preview/基础）。

此清单描述已应用候选的范围与待 fresh 验收要求，不是重新实现指令。五模型字符串乘五档 = 25 个内部组合，集中在一个五档测试方法内；目标类总共 5 个 pytest 方法，不是 25 个 pytest tests。test +63 已含 GA 两项，`diff --stat` 的 66 changed = +63/-3，不能记为 66 additions。

### 2.2 Out of Scope（绝对不引入）

- [ ] `agent/reasoning_effort.py`（PR 内 MINIMAX_M31_EFFORTS tuple；Anthropic-only 路径不使用）。
- [ ] `plugins/model-providers/minimax/__init__.py`（OpenAI-compat 路由）。
- [ ] `plugins/model-providers/custom/__init__.py`（none→low OpenAI-compat 处理）。
- [ ] `website/docs/user-guide/configuration.md`（上游文档注记）。
- [ ] `tests/plugins/model_providers/test_minimax_profile.py`（OpenAI-compat 测试）。
- [ ] §2.1 外的源码变更禁止；既有未跟踪 `m31-port.patch` 是 recovery baseline 已记录的背景产物，须单列并保留，不等于新增源码变更；不得清理其他 dirty 产物。
- [ ] profile / MCP / cron / config.yaml / 数据库 / 交易相关变更。
- [ ] RFC/SPEC/DESIGN 10-005、10-006 及其后续文档的任何修改。

## 2.bis 目标仓库与基线

| 项 | 值 |
|---|---|
| 目标仓库 | `/home/pascal/workspace/hermes-agent`（当前已应用、未提交候选；fresh Verify/Review 只读） |
| 基线 HEAD | `3fecce0a67bf243ef3a4d5d0d4a6eea28422fc37`（历史与 recovery HEAD 相同，不表示工作树干净） |
| 历史干净基线 | `/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-implementation-20261020/intake-baseline.json` 的 `core_files`，只作 Implement 前历史记录 |
| 当前候选基线 | `/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-recovery-20261020/recovery-baseline.json`：三源 SHA-256、core HEAD/status/numstat、patch SHA 与目标 profile 配置 SHA |
| 可执行标准补丁 | `/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-upstream-comparison-20261020/minimal-backport.patch`；来源为固定 PR head，历史 apply-check 不作为本次重新 apply 的授权 |
| 不完整内容参照 | `/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-implementation-20261020/materialized-patch.patch`；临时路径/裸头，遗漏 endpoints 注释与 docstring-only 内容，不可 apply，不可完整逐块对等 |
| YQuant 仓库 | 本三件套落地于 `/home/pascal/workspace/yquant-investment`；本流水线在 YQuant 仓库内只新增这三份文档 |

### 2.bis.1 历史记录与当前只读核验

历史 Implement 前核验为 HEAD、三源哈希与 intake baseline 相等及 status 干净；minimal 的历史 apply-check 记录仅供溯源，不是当前树的前置门禁，不得清场重现。当前执行以下只读核验：

1. core HEAD、三源 SHA-256、既有 `m31-port.patch` SHA 与 recovery baseline 对照；目标 profile config 只读哈希，不输出配置或凭据。
2. 核对 path-filtered `git diff --numstat` 与 `git diff --check`，分别记录三文件源码 diff 和 `m31-port.patch` 背景产物；YQuant 三文档的受控变动不算代码越界。
3. V2 独立只读核验文档 delta 及证据/哈希关联，R2 审查证据；保护源码/补丁哈希与主控真实只读测试基线一致时复用 §6 结果，不重复 pytest，Closeout 仅汇总。本 D2 已独立核对当前正文、`old-task-evidence.md` 与 recovery baseline，并前后直接核验 `m31-final-20261020/protected-files.sha256` 的 11 项，真实结果已进入本卡 handoff，不重复已完成核验；旧 D1 before/after 证据仅作历史参照，不冒充本次核验或独立 Verify。上述新证据完整目录见 RFC V1.2 §12。源码哈希漂移则停止回报，不自动重跑或扩范围。
4. 不符或无法核验时保留现场、停止回报；禁止擅自恢复、手工适配、隐式清理。任何回滚需新的明确范围授权，并遵守审批 STOP。

### 2.bis.2 历史责任与本次补救定位

四份旧卡完整快照位于 recovery baseline 同目录，本次可读正文/metadata 见 RFC §12 的 `old-task-evidence.md`。T1 `t_4b00d600` 在标为 Full Flow 的单卡合并 RFC/SPEC/Design，缺少独立 Design，属 orchestrator 编排偏差；旧 D1 `t_3a4c326a` 被 auto-decomposer 改写 body/拆卡、未正式验收，V1.1 仅历史候选，旧 Safety hold 继续约束旧卡。本次 replacement D2 `t_e0387995` 独立 Design reconciliation 正式交接至 V2 `t_087420b8` → R2 `t_682914e2`，不回填旧 D1 完成、不重跑旧卡/其子卡。旧 DESIGN §1/§7 与 T1 handoff 已授权 minimal，因此 T2 `t_dff78d74` 按 DESIGN 使用 minimal 不属于该来源选择未经授权；T2 body 的 materialized 唯一来源及 test +65/-3 是 orchestrator 任务书错误，不能据此另加 GA 两行。

旧 T3 `t_cbb5108e` body 要求清理/重放，metadata `baseline_restore_method` 记录 reset 被拒后 restore 再 apply；旧 T4 `t_7b302fe4` 的 `reset_method_deviation` 同样记录 reset 审批被拒后改用 restore/重放。责任包括 orchestrator 错误指令与执行者审批绕行，不得改称合规。旧 T4 PASS 不作为本次最终放行依据；新测试 PASS 不洗白历史违规。旧 T3 的 “No data lost” 自报不证明全部历史工作无损，也不得无证据断言另有损失；pre-restore diff 与当前 path-filtered diff 即便相等，仅证明该快照内容恢复。本次补救只恢复可依赖的当前只读证据。

## 3. 功能规格（固定契约）

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F-101 | M3.1 触发器 | model 字符串（`MiniMax-M3.1-Flash`、`minimax/MiniMax-M3.1-Flash`、`MiniMax-M3.1` 等） | `_model_name_is_minimax_adaptive()` → True | strip+lower+`rsplit("/",1)` 规范化后，模型名等于前缀或以 `前缀+"-"` 开头（前缀集 `minimax-m3.1` / `minimax-m3-1`）；非 str/空串 → False |
| F-101a | lookalike 反例 | `MiniMax-M3`、`MiniMax-M3-Flash`、`MiniMax-M31`、`minimax-m30`、`MiniMax-M3.10`、`minimax-m3.11-Flash`、`minimax-m3-10`、`minimax-m3-1x`、`not-minimax-m3.1`、`""`、`None` | 全部 False | 前缀必须整体等长或以 `prefix+"-"` 开头；`M31`/`M3.10`/`m30` 不被 `m3.1` 吞并 |
| F-102 | 五档 effort 直通 | reasoning_config `{enabled:True, effort:low/medium/high/xhigh/max}` | `output_config={"effort":<档位>}`；`thinking={"type":"adaptive"}`；`thinking` 无 `budget_tokens` | 五档逐档断言，覆盖 GA 名称（含 vendor 前缀） |
| F-103 | minimal 映射 | `{enabled:True, effort:"minimal"}` | `output_config={"effort":"low"}` | 不落回服务端默认 max |
| F-104 | disable 语义 | `{enabled:False}` | 请求 kwargs 不含 `thinking`，不含 `output_config` | 禁止发送 `disabled`（M3.1 端点返回 HTTP 400）；省略是唯一接受的"关" |
| F-105 | legacy manual 不变 | model ∈ {MiniMax-M3、M2.x、legacy Claude}，任意 reasoning_config | 请求形状与改动前逐字节一致（manual budget_tokens 路径） | 非目标模型 35 配置形状不变（Intake 探针证据） |
| F-106 | Claude/Kimi 不变 | Claude 全系 / Kimi 模型，任意 reasoning_config | 请求形状不变 | 分支顺序 kimi→minimax→claude，短路语义保留 |

## 4. 数据与接口契约

- 数据实体：无——本变更是请求构造期分支，不新增数据实体、状态或 schema。
- 接口/函数：`build_anthropic_kwargs` 签名与返回类型不变；新增 module-level helper `_model_name_is_minimax_adaptive(model: str | None) -> bool`；`_supports_adaptive_thinking(model: str) -> bool` 布尔语义不变，True 集合扩大（加入 M3.1 系）。
- 兼容性约束：非目标模型请求形状不变；M3.1 disable 时两字段省略，不能发送端点拒绝的 disabled 值；不宣称补丁前每次 disable 都发送 disabled。本补丁改变分类，不新增 disable 实现。
- 幂等性/审计要求：纯函数、请求构造期无状态、可重复调用；变更可追溯性由 diff allowlist（§2.1）与测试（§6）承担，不新增审计写入路径。

## 4.bis 持久化契约

无持久化变更仅限请求构造运行逻辑：内存 kwargs 不新增落盘、DB 或跨会话状态，既有会话日志机制不变；不禁止已授权的源码补丁、三份受控文档或各执行者自身 scratch 测试证据。本 D2 只改三文档并写自己 scratch；fresh Verify/Review 不改项目文件。profile 迁移、Gateway 重启、DB/cron/调度操作继续 out-of-scope。

## 5. 验收标准

### 5.1 功能验收

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-101 | 五档 effort 直通（含 GA 名称与 vendor 前缀） | pytest：`TestMinimaxM31AdaptiveEffort::test_m31_sends_the_requested_effort`（hermes-agent 仓库内真实执行） |
| A-102 | minimal→low 映射 | pytest：`test_m31_minimal_maps_to_low_not_the_max_default` |
| A-103 | disable → 两字段全省略 | pytest：`test_m31_thinking_off_is_never_sent_as_a_disable` |
| A-104 | legacy manual（M3/M2.x）不变 | pytest：`test_m3_and_m2_keep_manual_thinking` |
| A-105 | lookalike 10 字符串反例及 None 均 False，6 正例 True | pytest：`test_lookalikes_do_not_match` |
| A-106 | 非目标模型（Claude/Kimi/GLM 等）形状不变 | 既有 anthropic/minimax/kimi 相关测试全量无回归（§6 回归范围） |
| A-201 | 当前源码 diff 恰为三文件 +85/-9 | `git diff --numstat --` 三文件：+15/-0、+7/-6、+63/-3；`--stat` 仅辅助 |
| A-201a | adapter 行级变化 = import + 分支 + docstring 三处 | `git diff` 审计对照 DESIGN §3.1 行级分解 |
| A-202 | YQuant 仓库内只新增三份文档，不动 10-005/10-006 | `git status` 审计 |
| A-203 | 当前只读核验与历史 Implement 证据区分 | §2.bis.1 的 recovery 对照与前后保护哈希；历史干净基线/apply-check 仅溯源，不清场重放 |
| A-204 | 已有 dirty 产物完整保留且无新越界变动 | `git status --short --untracked-files=all` 与 recovery status 对照：三文件 M + 既有 m31-port.patch，分开归属 |
| A-205 | 禁止手工拼凑生产代码 | 当前 diff 的改动内容对照 minimal 标准补丁；materialized 仅有限内容参照，不要求完整逐块相等（DESIGN §7） |
| A-205a | YQuant 仓库其他文件未被改动 | `git -C /home/pascal/workspace/yquant-investment status --short` 只含三份新文档 |

### 5.2 上游一致性验收

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-301 | 两个目标生产函数与固定 PR head 文本/AST 一致 | 只读 `git show SHA:path` 与当前源提取 helper/classifier 核对；完整改动对照 minimal hunk 内容，不比较 materialized 完整性 |
| A-301a | 测试类唯一增强 = GA 两名称 | 对照 `upstream-functions.json` 的 `upstream_test_class` vs `proposed_test_class`，差异仅元组两成员 |
| A-301b | 历史补丁可应用性记录准确 | 仅记录 minimal 在历史干净基线的 apply-check；materialized 不可 apply，本次不执行 apply-check/重新 apply |
| A-301c | 当前候选漂移处置 | recovery 哈希/diff 不符 → 停止回报，保留现场，不自动清理/恢复或适配 |

### 5.3 非功能验收

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-206 | 定向测试在 hermes-agent 仓库内真实执行（非声称） | 复用 §6 主控真实只读 pytest 输出（含用例计数），核对保护源码/补丁哈希关联，不重复 pytest |
| A-207 | hermes-agent 验证前后状态和保护哈希不变 | 与 recovery baseline 对照；既有 m31-port.patch 保留，不误算新增源码变更 |
| A-208 | hermes-agent 内三文件 allowlist 之外的文件不受影响；YQuant 仓库仅三份新文档例外 | 双仓 `git status` 审计 |

## 6. 测试要求

- 单元测试：`tests/agent/test_minimax_provider.py` 全量，含目标类 5 个 pytest 方法；五模型乘五档的 25 仅是方法内部组合数。
- 当前真实只读验证基线：主控已在 core 使用现有 `.venv` 执行 `.venv/bin/python -m pytest tests/agent/test_minimax_provider.py tests/agent/test_anthropic_adapter.py -q`，真实输出为 `106 passed in 5.45s`（Pascal 2026-10-20 最新裁定随任务说明交付，随后保护哈希保持一致）。保护源码/补丁哈希与该基线一致时直接复用此结果；不是把旧 T3/T4 历史 PASS 当新 PASS，也不是声称 D2 自行执行。目标类 5 个方法已含于 106，不重复相加。
- 独立 V2 仅验文档 delta 及证据/保护源码与补丁哈希关联，R2 审查其证据而不重复 pytest；Closeout 汇总而不重复测试。不重复已完成核验；若源码哈希漂移则停止回报，不自动重跑或扩范围。功能、allowlist、审批 STOP 与历史违规记录不变。
- 回归覆盖按上述真实两文件结果及关联证据说明 anthropic/minimax/kimi 等非目标路径覆盖与未覆盖项，不为重复验收新增测试；旧 T3 的 293 项记录只作历史参考，不冒充本次全量执行。
- 集成/线上：Intake 7/7 线上场景及五档 HTTP 200 仅为历史证据；本次补救不发送真实端点请求、不做服务重启或 profile 迁移，线上加载/效果未验证。
- 本次报告分别给出主控真实功能证据、当前只读合规、历史违规保留、线上未验证；旧 T4 PASS 不替代新 V2 文档/证据核对或 R2 审查。

## 7. 实现约束

- 禁止事项：改写生产/测试；引入 §2.2 文件；修改 profile/MCP/cron/config.yaml/数据库/交易；修改外仓代码（本 D2 仅三份文档例外）；修改 10-005/10-006 或任何补丁产物。共享树禁止 reset/stash/clean/restore/checkout 路径回退、逆向 apply、重新 apply 与隐式清理其他产物。
- 依赖限制：不新增/升级任何依赖、SDK、provider、端点；不改 CLI、transport、辅助客户端、MCP。
- 性能/安全/风控约束：请求构造无新增 I/O；模型名规范化只影响判定，不改写发给服务端的 model 字符串；按 §2.bis.1 只读核验并保留证据。尽量降低未来冲突面，不保证零冲突。
- 交接按 DESIGN-10-013 V1.2 §7：只读当前候选；任何回滚须新明确范围授权。审批拒绝或超时立即 STOP，不得换命令、包装器、执行器或委派完成被拒动作，不降低审批模式、不使用 yolo。历史 apply-check/apply 命令不再作为当前执行指令。

## 8. 开放问题

无新需求裁定项；当前候选的功能/只读合规及最终放行仍由 fresh Verify/Review 决定，不回填历史。profile 迁移与 Gateway 重启继续 out-of-scope，源码已应用不代表线上进程已加载。

同步依据：[RFC-10-013 V1.2](../../rfc/10_infra/RFC-10-013-minimax-m31-hermes-core-adaptive-effort.md) §10 历史责任与 replacement 链；[DESIGN-10-013 V1.2](../../design/10_infra/DESIGN-10-013-minimax-m31-hermes-core-adaptive-effort.md) §3/§6/§7 当前核对与回滚授权。版本与本 SPEC 同步。
