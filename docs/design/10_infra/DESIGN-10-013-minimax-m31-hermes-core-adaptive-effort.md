# DESIGN-10-013：MiniMax M3.1 Hermes core Anthropic adaptive effort

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-10-20 |
| 最后更新 | 2026-10-20 |
| 版本号 | V1.2 |
| 来源 RFC | RFC-10-013-minimax-m31-hermes-core-adaptive-effort |
| 来源 SPEC | SPEC-10-013-minimax-m31-hermes-core-adaptive-effort |
| 目标模块 | 10_infra / hermes-agent core（`agent/anthropic_*`） |
| 流程模式 | Full Flow 补救：原 T1 缺独立 Design，旧 D1 仅历史候选；本次 replacement D2 `t_e0387995` 独立 Design reconciliation → V2 `t_087420b8` 只读 Verify → R2 `t_682914e2` 独立 Review |

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-10-20 | 初始创建：锁定三文件 +85/-9 行级分解、无持久化、补丁应用路径与回滚产物 | YQuant-Codex-Principal |
| V1.1 | 2026-10-20 | 旧 D1 历史候选同步 RFC/SPEC V1.1：核对 minimal 授权、不完整参照、准确统计及历史违规；改为当前候选只读交接，删除丢弃/重建指令；未作正式验收，不回填历史 | YQuant-Codex-Principal |
| V1.2 | 2026-10-20 | replacement D2 最小收尾：同步 RFC/SPEC V1.2 的来源统计、待迁移及正式阶段定位；按 Pascal 最新裁定复用哈希关联的主控真实只读测试结果，不重复 pytest；保留原功能契约，交接至新 V2/R2 只读验证/审查 | YQuant-Codex-Principal |

## 1. 设计摘要

来源固定 upstream PR #127088 head `6f3182249d1e99bfa6e8248c2199dcbfaf94f890`，仅复用必要 Anthropic 生产逻辑与测试而非自研，省略非必要注释 hunk；PR 自身 diff 与本地回移基线不同，不能混同统计，GA 两名为本地测试增强。完整可执行标准补丁为 `minimal-backport.patch`，本地三文件 +85/-9；`materialized-patch.patch` 是不可 git apply 的不完整内容参照，遗漏 endpoints 注释块及两处 docstring-only hunk，不能宣称其 apply-check 通过或完整逐块相等。当前候选已应用、未提交，replacement D2 `t_e0387995` 只修三份正文并只读核对；V2/R2 fresh Verify/Review 只读当前树，不清场、不重放。完整改动对照 minimal 的 hunk 内容（允许位置偏移），两目标函数对照固定 PR head 文本/AST（主控证据见 §7，本 D2 不重跑 AST）。回滚需新的明确范围授权并遵守审批 STOP，不能丢弃工作树或隐式清理其他产物。复用上游仅尽量降低未来冲突面，不保证零冲突。目标 profile 仍待迁移且配置未修改；源码补丁不代表 profile 迁移或线上生效。

旧版 DESIGN §1/§7 已明确授权 minimal 为可执行补丁，T1 `t_4b00d600` handoff metadata 同样记录该决定；T2 `t_dff78d74` 按 DESIGN 选择 minimal 不属于该来源选择未经授权。T2 body 把 materialized 写为唯一来源及 test +65/-3，属 orchestrator 任务书错误；不以此重复追加 GA 两行。两补丁的局部函数内容可对照，不推导整份补丁完整相等。

## 2. 现状分析

- 相关目录：`/home/pascal/workspace/hermes-agent`（目标仓库，工作区）；`agent/`、`tests/agent/`。
- 相关文件（下表为 Implement 前历史干净基线及候选行数；旧 T1 记录 2026-10-20 18:05 CST 复核，不是当前只读核验结果）：

| 文件 | 基线行数 | 改动后行数 | 基线 SHA-256 前缀 |
|---|---|---|---|
| `agent/anthropic_endpoints.py` | 159 | 174 | `d1122d23…` |
| `agent/anthropic_adapter.py` | 849 | 850 | `5def27c4…` |
| `tests/agent/test_minimax_provider.py` | 205 | 265 | `f1183253…` |

- 当前约束：HEAD 保持 `3fecce0a67bf243ef3a4d5d0d4a6eea28422fc37`，工作树已含三文件 M 与既有 `m31-port.patch`，不得要求清空。以 `/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-recovery-20261020/recovery-baseline.json` 对照当前三源、patch 与目标 profile 配置哈希；旧 intake-baseline 仅作历史参照。候选 classifier 已为 `kimi or minimax or (claude and not legacy)`。PR 在 Intake 时未 merged 属历史快照，本次不查询最新状态，来源始终固定 head。
- 兼容性风险：lookalike 型号误匹配（由前缀精确匹配 + 测试反例覆盖）；disable 语义变化仅限 M3.1 匹配请求；非目标模型 35 配置请求形状经 Intake 探针验证不变。

## 3. 方案设计

### 3.1 模块/文件改动（锁定 +85/-9 分配）

| 文件 | +/− | 内容分解（hunk 级，以可执行补丁 minimal-backport.patch 为准） |
|---|---|---|
| `agent/anthropic_endpoints.py` | +15/−0 | 单 hunk：5 行注释、1 行前缀常量、5 行 helper、4 行空行；`_MINIMAX_ADAPTIVE_MODEL_PREFIXES = ("minimax-m3.1", "minimax-m3-1")`；helper 使用 isinstance 守卫、strip+lower+rsplit、前缀等长或 `prefix+"-"` 匹配。materialized 未保留该注释块，不能与它整块相等 |
| `agent/anthropic_adapter.py` | +7/−6 | hunk 1（`@@ -20,8 +20,8 @@` import 块）：`_model_name_is_kimi_family` 与 `_normalize_base_url_text` 之间插入 `_model_name_is_minimax_adaptive`，2 行换 2 行。hunk 2（`@@ -169,8 +169,9 @@` `_supports_adaptive_thinking`）：docstring 1 行换 2 行（加入 MiniMax M3.1 与 `output_config.effort` 契约说明）+ return 行 1 行换 1 行（`or _model_name_is_minimax_adaptive(model)` 插入 kimi 与 claude 分支之间）。hunk 3（`@@ -582,8 +583,8 @@` `_thinking_kwargs`）：docstring-only 修正 2 行换 2 行（adaptive 模型列表加入 MiniMax M3.1；manual 组从 "MiniMax" 改为 "MiniMax M3/M2.x"） |
| `tests/agent/test_minimax_provider.py` | +63/−3 | hunk 1（`@@ -32,12 +32,12 @@`）：`TestMinimaxThinkingSupport` 类 docstring 修正 3 行换 3 行（旧断言"MiniMax 全系 manual、adaptive 仅 Claude 4.6"更新为"M2.x 保留 manual，M3.1 adaptive 契约另行测试"）。hunk 2（`@@ -58,6 +58,66 @@` `TestMinimaxBetaHeaders` 之前插入新类）：类 docstring（adaptive 契约 + 修复前 budget_tokens 失效说明）+ `M31` 元组 5 项（`MiniMax-M3.1-Flash`、`minimax/MiniMax-M3.1-Flash` 两 GA 名称 + upstream 三项）+ `_kwargs` helper + 5 个测试方法（五档直通 / minimal→low / disable 省略 / M3/M2 manual 不变 / lookalike 反例） |

合计 +85/-9，恰 3 个源码/测试文件，按 numstat 而非 stat changed 字段验收（SPEC A-201）；既有未跟踪 `m31-port.patch` 单列保留。test +63/-3 已含两 GA 项，不能再加两行；66 changed 表示 63 additions 与 3 deletions。M31 五字符串乘五档为 25 个内部组合，位于一个五档测试方法内；目标类总计 5 个 pytest 方法，不是 25 个 pytest tests。lookalike 为 10 个字符串反例及 None 边界、6 个正例。表中 hunk 行号来自 minimal 原始上下文，当前 diff 的行号偏移不构成内容偏差。

### 3.2 数据流/控制流

```text
reasoning_config (来自 /reasoning 或 profile 默认)
        │
        ▼
build_anthropic_kwargs(model, messages, tools, max_tokens, reasoning_config, base_url)
        │
        ├─ _supports_adaptive_thinking(model)
        │     ├─ _model_name_is_kimi_family(model)          → 既有分支，不变
        │     ├─ _model_name_is_minimax_adaptive(model)     ★ 新增（本设计唯一控制流变化）
        │     └─ _is_claude_model(model) and not legacy     → 既有分支，不变
        │
        ├─ adaptive 命中：
        │     thinking = {"type": "adaptive"}（无 budget_tokens）
        │     output_config = {"effort": effort}   # effort ∈ low/medium/high/xhigh/max；minimal→low
        │     reasoning_config.enabled=False → 两键全省略（不发 disabled）
        │
        └─ 未命中（M3/M2.x/其他）：既有 manual budget_tokens 路径，逐字节不变
        │
        ▼
POST {base_url} (Anthropic-Messages；M3.1 → api.minimaxi.com/anthropic)
```

### 3.3 接口与数据结构

- 新增：module-level 常量 `_MINIMAX_ADAPTIVE_MODEL_PREFIXES`、函数 `_model_name_is_minimax_adaptive(model: str | None) -> bool`（均位于 `agent/anthropic_endpoints.py`，下划线前缀 = 模块内部 helper，不构成公共 API）。
- 修改：`agent/anthropic_adapter.py` 的 import 块与 `_supports_adaptive_thinking()`（True 集合扩大，签名与布尔语义不变）。
- 废弃：无。
- 数据结构：无新增——仅请求 kwargs 的两个可选键 `thinking` / `output_config` 在 M3.1 命准时取新值。

### 3.4 持久化设计（Persistence Design）

无持久化变更只约束请求构造运行逻辑：内存 kwargs 不新增文件/数据库写入、缓存、跨会话状态或调度行为，既有会话日志机制不变（SPEC V1.2 §4.bis）。不禁止已授权的源码补丁、三份受控文档或各执行者自己的 scratch 测试证据写入；本 D2 只改本三文档并写自己 scratch，fresh Verify/Review 不改项目文件。profile 迁移与 Gateway 重启继续 out-of-scope。

### 3.5 UI/原型设计

无。

## 4. 历史实施与当前补救顺序

历史：旧 T1 `t_4b00d600` 在标为 Full Flow 的一张卡合并 RFC/SPEC/Design，旧 T2 直接 Implement，缺独立 Design，属 orchestrator 编排偏差。历史 Implement 的干净基线/apply-check 只作记录；旧 D1 `t_3a4c326a` 被 auto-decomposer 改写 body/拆卡、未正式验收，V1.1 仅历史候选，旧 Safety hold 继续约束旧卡。本次 replacement D2 `t_e0387995` 独立核对形成正式交接，不回填旧 D1 已完成，不重跑旧卡/其子卡。

旧 T3 `t_cbb5108e` body 要求清理/重放，metadata `baseline_restore_method` 记载 reset 被审批拒绝后 restore 再 apply；旧 T4 `t_7b302fe4` 的 `reset_method_deviation` 也记载 reset 被拒后换 restore/重放。执行者审批绕行与 orchestrator 错误指令均是历史流程违规，备份不使其合规。旧 T4 PASS 不作为本次最终放行依据，新测试 PASS 不洗白历史违规。旧 T3 的 “No data lost” 自报不证明全部历史工作无损，也不能无证据断言另有数据损失；pre-restore diff 即使等于当前 path-filtered diff，仅证明该快照内容恢复。本次补救仅恢复可依赖的当前只读证据。

当前顺序（不重做 Implement）：

1. replacement D2 `t_e0387995` 独立读取三正文、recovery baseline、`old-task-evidence.md` 四旧卡完整正文/metadata、标准补丁与固定 PR 函数证据，逐条最小纠正 F1/F2/F3 并保留既有六组契约；同步三文档 V1.2，形成正式 closed/open handoff。
2. 本 D2 前后直接运行 `sha256sum -c /home/pascal/.hermes/profiles/yquant/cache/scratch/m31-final-20261020/protected-files.sha256`，只读核验 core HEAD、path-filtered diff/numstat、双仓 status；保留全部当前 dirty，不将旧 D1 before/after 证据冒充本次结果。
3. 新 V2 `t_087420b8` 独立只读核验三文档 delta 与 D2/主控证据、保护源码/补丁哈希的关联；哈希与 §5 主控只读验证基线一致时复用真实两文件结果，不重复 pytest，不清空或重放，不重复已完成核验。源码哈希漂移则停止回报，不自动重跑或扩范围。
4. 新 R2 `t_682914e2` 独立审查文档与 V2/主控证据，不重复 pytest；主控真实功能结果、当前只读合规、历史违规保留和线上未验证分别报告，之后交 orchestrator 离线 Closeout 仅汇总、不重复测试，不宣称线上升级。

## 5. 测试策略

- 目标类：5 个 pytest 方法（五档/minimal/disable/legacy/lookalike）；25 是五档方法内部组合数，不是 pytest tests。
- 主控已真实只读执行：在 core 使用现有 `.venv` 运行 `.venv/bin/python -m pytest tests/agent/test_minimax_provider.py tests/agent/test_anthropic_adapter.py -q`，真实结果 `106 passed in 5.45s`，由 Pascal 2026-10-20 最新裁定随任务说明交付，随后保护哈希保持一致。保护源码/补丁哈希与该基线一致时复用；目标类 5 已包含其中，不重复相加，不把旧 T3/T4 PASS 当本次结果，也不声称 D2 自行执行。
- 独立 V2 仅验文档 delta 与证据/哈希关联，R2 审查证据、不重复 pytest，Closeout 汇总、不重复测试。不重复已完成核验；源码哈希漂移则停止回报，不自动重跑或扩范围；不改功能、allowlist、审批 STOP 或历史违规记录。
- 非目标覆盖按 SPEC V1.2 §6 的真实两文件结果及关联证据说明 anthropic/minimax/kimi 路径范围与未覆盖风险，不为重复验收新增测试，不声称未执行的全量回归通过。
- 线上：Intake 7/7 与五档 HTTP 200 仅作历史记录，本次不发送真实端点请求、不重启服务、不迁移 profile；不宣称候选已被线上进程加载或效果已验证。
- 本 D2 只做文档/只读证据核对，不重复主控已完成的测试或核验；不因 V2/R2 证据审查待完成而阻塞 D2 文档交接，也不回填旧 D1 完成。

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| 当前候选与 recovery baseline 漂移 | 只读 HEAD、三源/patch/配置 SHA 核验，保留证据 | 停止回报，不恢复、不手工适配 |
| 历史 apply-check 被误当当前门禁 | 仅 minimal 有历史可应用记录；materialized 是不可 apply 的不完整参照 | 不在当前树执行 apply-check 或重放 |
| diff 超出三文件 allowlist | numstat/path-filtered diff 与状态归属审计；既有 m31-port.patch 单列 | 保留现场并停止；禁止丢弃工作树、整体重建或隐式清理其他产物 |
| 上游后续改写 PR #127088 | 补丁固定 head SHA 并已物化，与上游解耦 | 无需动作 |
| 模型名 lookalike 误匹配 | 精确前缀及字符串/None 边界测试 | 失败停止回报，不在验证阶段改生产逻辑 |
| 需要回滚或处理线上异常 | 当前仅未提交源码候选，线上加载状态未验证；先保留现场与已有产物 | 必须取得新的明确范围授权，限定对象、改动与保留边界；本卡不执行回滚，不提供丢弃/整体重建指令 |
| 审批拒绝或超时 | 立即 STOP，向主控/Pascal 报告 | 不换命令、包装器、执行器或委派完成被拒动作，不降低审批模式或使用 yolo |

共享树禁止 reset/stash/clean/restore/checkout 路径回退、逆向 apply 或重新 apply；任何新的回滚授权也必须遵守审批 STOP，不能把原清理/重放要求当成现行授权。历史备份只可只读比对，不得借它断言所有历史数据无损。

## 7. 交接给 fresh Verify/Review（不重新实施）

- 必须遵守：
  1. 来源固定 PR #127088 head；完整可执行标准补丁路径为 `/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-upstream-comparison-20261020/minimal-backport.patch`。旧 DESIGN 已授权该来源，T2 使用它不属于未经授权的生产改动；materialized 不可 apply，仅不完整内容参照，不能声称其 apply-check 通过或整份逐块相等。
  2. 当前 core 树已应用、未提交；以 recovery baseline 与执行前后只读证据审计，历史干净基线/apply-check 只溯源，禁止清场与重放。源码三文件 +15/-0、+7/-6、+63/-3，合计 +85/-9；test +63 已含 GA 两项；既有 `m31-port.patch` 单列保留。
  3. 只读审计完整 6 个 hunk 的改动内容，按 minimal 对照并允许上下文行号偏移；生产 helper/classifier 由固定 PR git 对象提取后比较文本/AST；GA 两字符串只增测试数据，不重复追加。materialized 缺注释及 docstring hunks，不能作完整审计标准。
  4. 目标 profile 配置仅可读取 SHA，不输出原内容或凭据；禁止修改源码/测试/模板/skill、任何 profile/.env/config，不安装升级依赖，不 git add/commit/push，不重启 Gateway/服务，不做 cron/MCP/数据库/交易操作或外部发送。本 D2 仅本三文档允许写，证据仅各自 profile scratch 或 Kanban handoff；其他 dirty 产物全部保留。
  5. 按 §5 复用与保护源码/补丁哈希关联的主控真实只读结果，报告精确命令、计数、未执行项与残余风险；V2 仅核文档 delta 与证据关联，R2/Closeout 不重复测试。源码哈希漂移则停止回报，不自动重跑或扩范围。任何审批拒绝/超时立即 STOP，不换命令、包装器、执行器或委派绕行；当前发现与文档契约不符则 needs_input block，不能扩大范围或放宽断言以通过。
- 当前只读命令：`git -C /home/pascal/workspace/hermes-agent rev-parse HEAD`、`git -C /home/pascal/workspace/hermes-agent diff --numstat -- agent/anthropic_endpoints.py agent/anthropic_adapter.py tests/agent/test_minimax_provider.py`、相同 path-filter 的 `diff --check`、`git status --short --untracked-files=all`，以及受保护文件的 `sha256sum`；这些均不清空工作树。
- 历史 pre-restore 备份 `/home/pascal/.hermes/profiles/yquantreviewer/cache/scratch/t4-pre-restore-backup.diff` 仅可只读比较当前 path-filtered diff；相等只说明该快照恢复，不证明全部历史工作无损。旧 T4 PASS 不作本次最终放行依据。
- 本次只读证据目录 `/home/pascal/.hermes/profiles/yquant/cache/scratch/m31-final-20261020/`：`old-task-evidence.md` 为四旧卡完整正文/metadata；`function-provenance.md` 为主控从固定 PR git 对象与当前源码生成的函数文本/AST 核验，本 D2 已逐字核对当前 helper/classifier，不声称自行重跑 AST；`protected-files.sha256` 为 11 项清单，D2 前后已核验通过。V2 核对主控测试基线与保护源码/补丁哈希的关联，R2 审查证据，不重复已完成核验。
- replacement D2 `t_e0387995` 文档核对完成即正式 handoff 至新 V2 `t_087420b8` → R2 `t_682914e2`，不因后续待运行而阻塞；旧 D1/其子卡仅历史候选，不回填完成。功能、当前只读合规、历史违规、线上未验证分别报告。
- 同步契约：[RFC-10-013 V1.2](../../rfc/10_infra/RFC-10-013-minimax-m31-hermes-core-adaptive-effort.md) §10 与 [SPEC-10-013 V1.2](../../spec/10_infra/SPEC-10-013-minimax-m31-hermes-core-adaptive-effort.md) §2.bis/§5/§6；无新增功能或额外文档。
