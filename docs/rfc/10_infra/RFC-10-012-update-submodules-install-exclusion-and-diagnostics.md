# RFC-10-012：update_submodules install 排除与诊断优化

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-10-06 |
| 最后更新 | 2026-10-06 |
| 版本号 | V1.1 |
| 所属模块 | 10_infra（基础设施 / git submodule 运维自动化） |
| 依赖RFC | RFC-10-008-update-submodules-script（V2.0，本 RFC 为其增量修订） |
| 替代RFC | 无 |
| 关联 SPEC | docs/spec/10_infra/SPEC-10-012-update-submodules-install-exclusion-and-diagnostics.md |
| 关联 Design | docs/design/10_infra/DESIGN-10-012-update-submodules-install-exclusion-and-diagnostics.md |
| Full Flow | Quick Flow T1=t_c1e60718（T2=Implement, T3=Verify, T4=Closeout） |
| AI适配 | Hermes Kanban（yquantprincipal → yquantdeveloper → yquanttester） |
| 标签 | #infra #git #submodule #upgrade #ops #pip #diagnostics |

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-10-06 | 初始创建：install_exclude（P1）、classify_pip_failure sample 二次选择（P2）、daily_stock_analysis opt-in 配置（P3） | YQuant-Codex-Principal |
| V1.1 | 2026-10-06 | t_13d22c5e 勘误：A-104 两组规范化、hits 去重保序；补明根副本引用重定位、requirement 选项保留及全路径清理；不新增递归排除或设计阶段 | YQuant-Codex-Principal |

## 1. 执行摘要（Executive Summary）

2026-10-06 daily_stock_analysis 升级实战暴露三个运维痛点：临时排除单个包需手改 requirements、pip 失败诊断被 yanked 警告行遮蔽、daily_stock_analysis 缺少 systemd/health_check opt-in 配置。本 RFC 以增量修订（脚本 v2.1.0 → v2.2.0）落地三项优化：opt-in `install_exclude` 包级排除、`classify_pip_failure` 诊断样本优先含包名+版本约束的行、新建 `skills/research/daily_stock_analysis/.update_submodules.yaml`。成功标准：SPEC-10-012 全部验收项 PASS，2026-10-06 真实 pip 报错文本的回归测试通过。

## 2. 背景与动机（Background & Motivation）

### 2.1 实战案例（2026-10-06）

审计日志 `/tmp/update_submodules_audit_20261006_121344.md`（真实记录）：

```
- Phase install: fail — pip install 失败 (missing_dependency):
  ERROR: Ignored the following yanked versions: 0.2.2, 0.2.3, 0.2.4, 0.2.5, 0.2.6
  | hint: 包名/版本约束在 PyPI 上无匹配。检查 requirements.txt 平台 marker 或与上游 release notes。
- ABORT reason: （同上）
```

真实根因：`skills/research/daily_stock_analysis/requirements.txt` 中
`longbridge>=4.0.5,<5; platform_system != "Linux" or python_version >= "3.12"`
在当前 WSL 环境解析出 `No matching distribution found for longbridge<5,>=4.0.5`（4.x wheel 需 manylinux_2_39，本机 glibc 不满足；见该文件 L22-23 注释）。诊断样本被 stderr 中先出现的 `ERROR: Ignored the following yanked versions` 行遮蔽，操作者无法从 audit 日志直接看到包名与版本约束。

### 2.2 三项需求动机

| 编号 | 需求 | 动机 |
|---|---|---|
| P1 | install 阶段 opt-in `install_exclude`（包名列表） | 平台性不兼容（如 longbridge 4.x manylinux_2_39）在单个 submodule 内是长期已知状态。目前唯一手段是手改 submodule 内 requirements.txt——会被 upstream merge 冲突化且破坏"不改 submodule 内业务文件"边界。需要 opt-in、声明式、可审计的排除通道 |
| P2 | `classify_pip_failure` sample 优先含包名+版本约束的行 | 现实现（update_submodules.py:943-951）取**首个**命中行；pip stderr 中 `ERROR: Ignored the following yanked versions` 先于 `No matching distribution found for <pkg><specs>` 出现，导致 audit 样本不含根因行 |
| P3 | daily_stock_analysis opt-in 配置 | 该 submodule 的 systemd service 名 `daily-stock-analysis` 与健康端点 `http://127.0.0.1:8888/health` 目前只存在于人工记忆；heuristics 只模糊匹配 unit 名，health_check 默认 None（update_submodules.py:561），Phase 4 从不真正验证服务可用性 |

### 2.3 业务价值

- 升级失败的可诊断性：audit 一眼看到"哪个包、什么约束、为什么无匹配"。
- 平台性排除声明式化：不改 requirements、不产生 merge 冲突、audit 显式记录 degraded 状态。
- daily_stock_analysis 升级闭环：restart 后真实 health check，把"服务起没起来"从人工 ping 变为流水线门禁。

触发原因：风险驱动 + 实战复盘（2026-10-06 升级 abort 事件）。

## 3. 目标与非目标（Goals & Non‑Goals）

### 3.1 必须目标（Must‑Have）

- [ ] P1：opt-in `.update_submodules.yaml` 新增 `install_exclude: list[str]`；命中时 Phase 3 过滤 requirements 对应行（整行锚定该包，保留注释与其他行）；audit 记录 `install (excluded: <pkgs>): OK (degraded)`。
- [ ] P2：`classify_pip_failure` 的 sample 选取在命中行集合内优先选择含包名+版本约束的行（如 `No matching distribution found for longbridge<5,>=4.0.5`），不再被 yanked 警告行遮蔽。
- [ ] P3：新建 `skills/research/daily_stock_analysis/.update_submodules.yaml`（schema_version: 1 / systemd_service: daily-stock-analysis / health_check: `curl -fsS --max-time 5 http://127.0.0.1:8888/health`），走既有 merge_override 机制生效。
- [ ] 脚本 `__version__` 升 2.2.0；`tests/scripts/test_update_submodules.py` 补充回归测试（fixture 使用 2026-10-06 audit 真实 pip 报错文本）。

### 3.2 非目标（Out of Scope）

- [ ] 不改 5 阶段流水线结构（fetch → merge → install → restart → push）。
- [ ] 不改 merge 冲突 `git merge --abort` 逻辑。
- [ ] 不改 push 默认行为（默认不 push、永不 --force）。
- [ ] 不改失败分类六类集合（missing_dependency / platform_incompatible / resolution_conflict / network_error / source_build_error / other）及其 pattern 顺序——P2 只改 sample 选取，不改分类判定。
- [ ] 不改文档模板（docs/*-00-000-*.md）。
- [ ] 不新增第三方依赖（保持单文件标准库 + PyYAML optional）。
- [ ] 不处理 requirements 行续行（反斜杠折行）语法——见 SPEC §8 开放问题。
- [ ] 不新增递归排除嵌套 requirements/constraints 中的包；排除范围仍为 pip 命令直接引用的根文件，必要引用重定位只恢复原解析目标（SPEC §4.2 / DESIGN §3.4）。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

延续 RFC-10-008 V2.0 的「启发式默认 + opt-in 增强」：三项能力全部 opt-in 或无行为变化的诊断增强，任何 submodule 不放配置文件时脚本行为与 v2.1.0 完全一致。

### 4.2 架构总览

```text
.update_submodules.yaml (opt-in)
   │  validate_override / merge_override（既有机制，扩 1 个字段）
   ▼
SubmoduleConfig.install_exclude: tuple[str, ...] = ()
   │
   ├─► phase_install: 若非空 → requirements 行过滤（临时文件）→ pip install -r <filtered>
   │        └─ 成功且发生排除 → audit detail "install (excluded: ...): OK (degraded)"
   │
   └─► classify_pip_failure: 分类不变；sample 在命中行集合内做"包名+版本约束优先"二次选择
```

### 4.3 模块分工

- `scripts/upgrade/update_submodules.py`：唯一代码改动点。`SubmoduleConfig` 加字段、`validate_override`/`merge_override`/`_replace_config` 透传、`phase_install` 过滤、`classify_pip_failure` sample 二次选择。
- `tests/scripts/test_update_submodules.py`：新增 UT-020 起回归用例。
- `skills/research/daily_stock_analysis/.update_submodules.yaml`：P3 数据文件（内容与落盘策略见 DESIGN §3.6）。

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

- 触发条件：Phase 3 install 执行且该 submodule 的 `install_exclude` 非空（P1）；或 pip install exit_code != 0（P2）。
- P1 核心处理逻辑：
  1. 将 `pip_install_cmd` 中 `-r <path>`（含 `--requirement` 长选项及等号形式）直接引用的每个根 requirements 文件生成独立过滤副本，同名根文件不覆盖（SPEC F-002 / §4.2）；
  2. 根副本中相对 -r/-c 引用仅重定位至原文件目录下的解析目标；嵌套原件由 pip 继续读取，不递归复制/排除。pip 命令保留 requirement 选项（`--requirement=` 不得丢失），路径指向副本；临时目录在本次 phase_install 所有退出路径清理（DESIGN §3.4）；
  3. pip 成功且发生排除 → detail 记 `install (excluded: <pkgs>): OK (degraded)`，阶段状态仍为 pass（降级非失败）；
  4. `install_exclude` 非空但 pip 命令中无 `-r` 引用 → warning，排除不做（degraded 语义不成立，不做静默假装）。
- P1 异常降级分支：过滤后 requirements 为空 → 仍执行（pip 将报 "no requirements"类错误走既有失败路径）；临时文件写失败 → 记 fail（环境问题，不静默回退为不过滤执行，避免把本应排除的包装进环境）。
- P2 核心处理逻辑：分类 pattern 首匹配不变；确定分类后，在该分类命中的行集合内按 SPEC F-004 的优先规则选 sample；无更优行时回落现行为（首个命中行）。
- P3：yaml 经 `load_optin_override` → `validate_override` → `merge_override` 既有链路生效；`health_check` 为非空 shell 字符串时 Phase 4 在 restart + wait_for_active 之后执行，失败 abort push（既有语义，RFC-10-008 §6.6）。

### 5.2 数据模型（Data Model）

| 字段 | 类型 | 说明 | 约束 |
|---|---|---|---|
| `SubmoduleConfig.install_exclude` | `tuple[str, ...]` | 需从 requirements 过滤的包名列表 | 默认空 tuple；元素经 PEP 503 规范化比较（大小写、`-`/`_`/`.` 等价） |
| opt-in `install_exclude` | `list[str]`（YAML） | 同上，声明侧 | 非法类型 → warning 丢弃该字段（沿用 opt-in 字段约束风格，见 SPEC F-001） |

### 5.2bis 持久化策略（Persistence Strategy）

无新增持久化需求。涉及的两类落盘均为既有机制：audit 日志（`--audit-dir`，默认 /tmp，Markdown 文本，L0 公开运维信息）；P1 过滤根副本为临时文件（`tempfile` 临时目录，可由 TMPDIR 指定；一次 phase_install 生命周期，在所有退出路径清理；仅 requirements 保留行及必要引用重定位，不含敏感数据）。`install_exclude` 与 `.update_submodules.yaml` 的持久化位置在 submodule 仓库内，生命周期随该仓库，无隐私分级问题（L0）。

### 5.3 接口契约（API Contract）

- CLI 面不变：不新增、不修改任何 CLI 参数（`install_exclude` 仅经 opt-in 文件声明）。
- 函数签名变化：
  - `SubmoduleConfig` 新增 frozen 字段 `install_exclude: tuple[str, ...] = ()`；
  - `classify_pip_failure(text: str) -> tuple[str, str]` 签名与返回类型不变，仅 sample 选取策略增强；
  - `phase_install(state: SubmoduleState, *, dry_run: bool) -> PhaseResult` 签名不变，内部读 `state.config.install_exclude`。
- 详约见 SPEC-10-012 §3/§4；文件级实现见 DESIGN-10-012 §3。

## 6. AI实装规范（AI Implementation Rules）

### 6.1 必须执行

- 单指令只做一件事，使用相对路径；改动严格限定在约束允许的文件清单内。
- `SubmoduleConfig` 为 frozen dataclass：新增字段必须同步更新 `discover_submodule`（默认值）、`_replace_config`（透传），并核对全部构造点。
- P2 改动不得改变分类结果，只允许改变 sample 字符串；用 2026-10-06 真实文本做回归断言。
- 每项行为变化补单元测试（UT-020+，沿用既有测试文件风格）。
- 本轮仅既有三文档勘误及预创建 Fix-2/Verify-2/Closeout-2 链，不自动拆卡。Fix-2 代码 allowlist 仅 `scripts/upgrade/update_submodules.py` 与 `tests/scripts/test_update_submodules.py`；禁止子模块/生产配置变更、commit/push/reset/stash/clean、真实依赖安装、升级 apply、服务重启、数据库或调度变更；c27720fa 与共享树其他差异原样保留。P3 历史落盘计划不构成本轮授权（SPEC §7）。

### 6.2 先询问再执行

- 发现必须改动约束清单外的文件才能实现（视为设计缺陷，退回 Principal）。
- 需要动 requirements 过滤语义之外的 pip 参数改写（如 `--index-url`）。

### 6.3 绝对禁止

- 修改 5 阶段结构、merge abort、push 默认行为。
- 在过滤实现中使用子串包含匹配（必须行首锚定包名，防止误伤注释或含该子串的其他包）。
- 把被排除包静默装入环境（临时文件写失败必须 fail，不许降级为不过滤执行）。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| 过滤误伤（注释行/含同子串包名被删） | 中 | 高（环境缺依赖） | 行首锚定 + PEP 503 规范化 + 选项行/注释行跳过；SPEC F-002 given/then 逐例测试 | audit `excluded` 列表与过滤行数回显，人工可核对 |
| 被排除包恰为运行必需 → 服务 health check 失败 | 中 | 中 | degraded 仅发生在 opt-in 声明后；Phase 4 health_check 门禁兜底（P3 配置后每日_stock_analysis 必检） | 移除 yaml 中 install_exclude 即恢复全量安装 |
| P3 yaml untracked 导致 apply 撞 dirty_worktree 拒跑 | 高（若不处理） | 中 | DESIGN §3.6 规定 yaml 必须提交进 origin fork 或加入 `.git/info/exclude`，禁止留 untracked | `--force-dirty`（应急，不推荐常态化） |
| P2 优先规则在未知 pip 输出形态下选错行 | 低 | 低（仅诊断文本） | 规则为"优先"非"独占"，无更优行回落现行为；回归 fixture 用真实文本 | sample 错误不影响分类与 abort 行为 |

## 8. 备选方案（Alternatives Considered）

- 备选一：`--exclude-pkg` CLI 参数（会话级排除）。优点：无需配置文件。否决：排除是单 submodule 的长期平台事实（manylinux 约束），放 CLI 每次都要人记参数，且 cron/自动化场景无法传递；与 opt-in 配置哲学相悖。
- 备选二：直接改 daily_stock_analysis requirements.txt 加注释/删除行。否决：submodule 内文件会在下次 upstream merge 冲突化，违反"不改 submodule 内业务文件"运维边界，且无 audit 可见性。
- 备选三：P2 用"最后命中行"替代"优先含包名行"。否决：pip 输出顺序无稳定契约，最后行可能是 summary；显式内容特征（包名+版本约束）比位置启发更稳健。

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收

- 正常场景：install_exclude 命中 requirements 中的行（含带 marker 行），过滤后 pip 成功，audit 记录 degraded；未配置 install_exclude 的 submodule 行为零变化。
- 异常输入覆盖：声明包全部未命中根文件时，不报错且 audit 列出 miss；混合 hit+miss 未定义项只记录（SPEC §8）；pip 命令无 `-r`（warning + no-op）；源缺失或副本写失败 → install fail。清理矩阵覆盖源缺失/写失败/pip 失败/成功/dry-run（SPEC A-108）。
- 边界条件覆盖：requirements 注释/选项行（只有相对 -r/-c 引用允许必要重定位）；pip 分离及等号 requirement 参数保留选项；多根副本不覆盖；本地 pip parser 实际解析嵌套引用。`Long_Bridge`/`long-bridge`/`long.bridge` 规范化为 `long-bridge`；`longbridge`/`LONGBRIDGE` 规范化为 `longbridge`，两组不等价（SPEC A-104）；排除 `bridge` 不得命中 `longbridge`。hits 为原始命中包名去重保序。
- P2：2026-10-06 真实 stderr 文本分类仍为 `missing_dependency`，sample 变为含 `longbridge` + 版本约束的行。
- P3：yaml 加载后 `merge_override` 产出 `systemd_service="daily-stock-analysis"`、`health_check="curl -fsS --max-time 5 http://127.0.0.1:8888/health"`；schema 破损时回落启发式。

### 9.2 非功能验收

- 稳定性：`tests/scripts/test_update_submodules.py` 全量通过，既有 UT-001~UT-019 无回归。
- 兼容性：不配置任何 yaml 时，v2.2.0 与 v2.1.0 dry-run 输出逐字节一致（新增字段不打印）。
- 安全：过滤临时文件位于 tempfile 所选临时目录，phase_install 所有退出路径清理；不引入网络、凭证或 shell=True。

逐条可测契约见 SPEC-10-012 §5（A-100 系列）；实现与测试设计见 DESIGN-10-012。

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

Quick Flow（本卡 T1 文档已产出）：
- T2 Implement（yquantdeveloper）：按 DESIGN §3 文件清单实现 + UT-020+ 用例，`__version__=2.2.0`，落盘 P3 yaml（含 dirty 规避，见 DESIGN §3.6）。
- T3 Verify（yquanttester）：跑全量 `tests/scripts/test_update_submodules.py`，对照 SPEC A-100 系列逐项核验。
- T4 Closeout。

本轮替代链：t_13d22c5e Doc-Fix-2（仅本三文档）→ t_c4fc6a2a Fix-2（仅脚本/现有测试）→ t_743f1d89 独立 Verify-2 → t_7e416326 Closeout-2。旧 t_b5d45087 的 FAIL 保留，不解除重跑；历史 80/80 不代表三缺陷已闭合。此链仅离线修复验收，未授权生产部署；DSA 历史全量 15 失败与生产 health 端点均不得称已通过。

### 10.2 任务清单

| 任务 | 负责 | 说明 |
|---|---|---|
| RFC/SPEC/DESIGN-10-012 三层文档 | Principal（本卡，已完成） | 本文档及 §元数据 所引两份 |
| update_submodules.py 三项实现 + 版本号 | yquantdeveloper | DESIGN §3.1 文件级清单 |
| UT-020+ 回归测试 | yquantdeveloper | DESIGN §5 用例名与 fixture |
| 全量验证 | yquanttester | SPEC §5 A-100 系列 |

## 11. 开放问题（Open Questions）

- [ ] requirements 行续行（行尾反斜杠折行）是否纳入过滤语义：当前排除在范围外（SPEC §8 记录）；daily_stock_analysis requirements 现无折行，触发时再议。
- [ ] `install_exclude` 是否未来需要支持带版本约束的精确排除（如 `longbridge>=4`）：当前按包名全排除，未出现需求。
- [ ] 混合 hit+miss 附加审计文本：只记录旧 Closeout 的未定义项（SPEC §8），本轮不新增契约。

## 12. 参考资料（References）

- RFC-10-008-update-submodules-script（V2.0）：docs/rfc/10_infra/RFC-10-008-update-submodules-script.md
- SPEC-10-008-update-submodules-script：docs/spec/10_infra/SPEC-10-008-update-submodules-script.md
- DESIGN-10-008-update-submodules-script：docs/design/10_infra/DESIGN-10-008-update-submodules-script.md
- 2026-10-06 audit 实录：/tmp/update_submodules_audit_20261006_121344.md
- scripts/upgrade/update_submodules.py（v2.1.0 基线）
