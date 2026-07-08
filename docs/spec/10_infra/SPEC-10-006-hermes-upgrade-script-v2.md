# SPEC-10-006：Hermes Agent 自动升级脚本 V2

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-07-08 |
| 来源 RFC | RFC-10-006-hermes-upgrade-script-v2 |
| 继承 SPEC | SPEC-10-005-hermes-auto-upgrade |
| 关联 Design | DESIGN-10-006-hermes-upgrade-script-v2 |
| 目标模块 | 10_infra / Hermes 运维自动化 |
| Quick Flow | T1=t_5b0e9e89, T2=t_5beea5d8, T3=t_fa87e65b, T4=t_3d1b2331 |

## 1. 需求摘要

本 SPEC 将 RFC-10-006 的 V2 增量需求落为可执行、可测试的工程契约，并继承 RFC-10-005 / SPEC-10-005 / DESIGN-10-005 的安全升级主线。V1.0（RFC/SPEC/DESIGN-10-005）已实现 Hermes Agent 安全升级主线：main 分支、upstream/main、zip/stash/manifest、A+ merge、install/verify、detached restart、push origin。V2 不重写主线，只新增 3 类能力：

1. 用 `--branch BRANCH` 替代硬编码 main-only 检查，默认仍为 `main`，保证向后兼容。
2. 用 `--preserve-features` 在升级前保护当前 feature branch 上的本地 commit。
3. 用 `data/hermes_patches.yaml` + `--patches-manifest PATH` 结构化追踪 Pascal fork 私有 patch，并在升级后/干跑中做 upstream 包含性核对。

## 2. 范围

### 2.1 In Scope

- 修改 `scripts/upgrade/upgrade_hermes_agent.py`，新增 V2 CLI 参数、数据结构和流程插入点。
- 新增 `data/hermes_patches.yaml`，schema version 为 2，初始包含 `feishu-markdown-table`。
- 新增 `tests/scripts/test_upgrade_hermes_agent_v2.py`，覆盖 V2 参数、manifest、branch、preserve-features、patch 核对。
- 保持 `tests/scripts/test_upgrade_hermes_agent.py` V1.0 测试全量通过。
- 更新/新增三层文档 RFC/SPEC/Design-10-006。

### 2.2 Out of Scope

- 不自动 rebase/cherry-pick/drop Pascal fork 私有 patch。
- 不修改 `/home/pascal/workspace/hermes-agent/**` 源码；脚本运行时由 git 升级产生的目标 repo 变更不属于本项目代码修改。
- 不修改 Hermes profile config、`.env`、`auth.json`、MCP、provider/model/fallback、gateway platform 配置或 systemd unit。
- 不执行真实 gateway restart 或真实 origin push 作为 T3 Verify 默认动作。
- 不新增第三方依赖；若使用 PyYAML，必须视为 optional，并提供标准库 fallback 或简化 YAML 子集解析。

## 3. 功能规格

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F2-001 | CLI 参数解析 | `--branch`, `--preserve-features`, `--patches-manifest` | `UpgradeConfig` 新字段 | 参数类型错误 exit 2 |
| F2-002 | branch 允许列表 | 当前 git branch + `--branch` | S0 inspect 通过/失败 | 默认 `--branch main`，行为等同 V1.0 |
| F2-003 | feature branch 保护计划 | `--preserve-features`, branch, local-only commits | stdout / manifest 摘要 | dry-run 不 push |
| F2-004 | feature branch push | real-run + `--preserve-features` | `git push -u origin <branch>` exit code | push 失败 warning，不 force push |
| F2-005 | patches manifest 读取 | `--patches-manifest PATH` | `PatchesManifest` | 缺失/格式错 warning，不阻塞升级 |
| F2-006 | patch schema 校验 | YAML/JSON-like 数据 | dataclass list | 必填字段缺失 warning，不阻塞 |
| F2-007 | upstream patch 核对 | repo + manifest + upstream ref | list[`PatchStatus`] | best-effort，不自动改写 manifest |
| F2-008 | dry-run V2 输出 | V2 参数组合 | 完整计划 + no mutation 声明 | 不 fetch/stash/merge/install/restart/push |
| F2-009 | V1 兼容 | 不带 V2 参数 | 与 V1.0 等价 | V1 测试必须全过 |
| F2-010 | manifest 审计扩展 | patch/check 结果 | upgrade manifest 增加 `patch_statuses` | 不记录 secrets |

## 4. 数据与接口契约

### 4.1 CLI 参数契约

| 参数 | 类型 | 默认 | 行为 | 与 V1.0 关系 |
|---|---|---|---|---|
| `--branch BRANCH` | string | `main` | 指定 S0 允许的当前工作分支；当前分支必须等于该值 | 默认等同 V1.0 main-only |
| `--preserve-features` | flag | false | 在 S0 后新增 S0.5，保护当前 branch 上 local-only commits | 默认不启用 |
| `--patches-manifest PATH` | path/null | null | 读取 Pascal fork 私有 patch 清单并做核对 | 默认不启用 |

说明：

- `--branch` 不是升级目标；升级目标仍由 V1.0 的 `--version` 控制，默认 `upstream/main`。
- `--branch fix/feishu-table-card` 表示“允许当前 repo 正在该分支上运行 inspect/dry-run/计划”，不是把 upstream merge 到该分支。
- 真实升级路径如需从 feature branch 切回 main，应由实现明确输出计划；不得隐式丢弃当前 branch commit。

### 4.2 `UpgradeConfig` 增量字段

在 SPEC-10-005 §4.3 的基础上新增：

```text
branch: str = "main"
preserve_features: bool = False
patches_manifest: Optional[Path] = None
```

V1 字段保持不变：

```text
repo: Path
version_ref: str
backup_dir: Path
dry_run: bool
restart: bool
push: bool
rollback_manifest: Optional[Path]
yes: bool
verbose: bool
hermes_bin: Path
```

### 4.3 Patch manifest 文件契约

路径：`data/hermes_patches.yaml`。

最小 schema：

```yaml
schema_version: 2
patches:
  - id: feishu-markdown-table
    title: "fix(feishu): render markdown tables via interactive card"
    commit: "4d3a9661c"
    branch: "fix/feishu-table-card"
    upstream_pr: null
    upstream_merged: false
    file_globs:
      - "plugins/platforms/feishu/adapter.py"
    notes: "interactive card 替代 plain text 降级"
```

字段契约：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | int/string | 是 | V2 推荐 `2`；读取端必须接受 `1` 作为兼容输入 |
| `patches` | list | 是 | patch 条目数组，可为空 |
| `patches[].id` | string | 是 | 稳定 ID，kebab-case |
| `patches[].title` | string | 是 | 人类可读标题 |
| `patches[].commit` | string | 是 | Pascal fork 上的 commit SHA，可短 SHA |
| `patches[].branch` | string | 是 | patch 所在 Pascal fork 分支 |
| `patches[].upstream_pr` | string/null | 否 | 若已提 PR，记录 PR URL 或编号 |
| `patches[].upstream_merged` | bool | 是 | 人工/Closeout 维护的状态 |
| `patches[].file_globs` | list[string] | 是 | patch 影响文件，用于 best-effort diff 检查 |
| `patches[].notes` | string | 否 | 背景说明 |

### 4.4 Dataclass 契约

```text
@dataclass(frozen=True)
class PatchEntry:
    id: str
    title: str
    commit: str
    branch: str
    upstream_pr: Optional[str]
    upstream_merged: bool
    file_globs: list[str]
    notes: str = ""

@dataclass
class PatchesManifest:
    schema_version: int
    patches: list[PatchEntry]

@dataclass
class PatchStatus:
    id: str
    upstream_merged_manifest: bool
    upstream_contains_commit: bool
    upstream_contains_patch_id: bool
    status: Literal["merged", "possibly-merged", "pending", "unknown"]
    reason: str
```

`PatchStatus` 判定规则：

| 条件 | status | 说明 |
|---|---|---|
| `upstream_merged=true` | `merged` | manifest 已人工确认，脚本只复述 |
| upstream 可达 `commit` | `merged` | commit SHA 已在 upstream ref 可达；少见但可判定 |
| patch-id 或 file diff best-effort 命中 | `possibly-merged` | 可能已合入，需 T4/人类复核 |
| 无命中且 manifest 未标 merged | `pending` | 仍作为 Pascal fork 私有 patch 观察 |
| 检查命令失败/manifest 不完整 | `unknown` | 输出 warning，不阻塞升级 |

## 5. 行为契约

### 5.1 S0 branch 检查

V1 行为：

```text
if current_branch != "main": fail
```

V2 行为：

```text
allowed_branch = config.branch  # default main
if current_branch != allowed_branch:
    fail inspect with next_steps:
      - 当前分支是 X，本次允许分支是 Y
      - 若确实要在 X 上检查，传 --branch X
      - 若要执行默认升级，切回 main
```

验收：

- 不带 `--branch` 且当前非 main：仍失败，向后兼容 V1.0 安全默认。
- 带 `--branch fix/feishu-table-card` 且当前分支匹配：S0 不因 main-only 失败。
- `--branch` 指定不存在的分支时，若当前分支不等于该值应失败；脚本不应 silent fallback。

### 5.2 S0.5 preserve-features

触发条件：`config.preserve_features is True`。

行为：

1. 读取当前 branch、HEAD、dirty files、local-only commits。
2. 若 detached HEAD：warning，跳过 push，继续后续流程或 dry-run 计划。
3. 若缺 origin remote：warning，跳过 push，继续后续流程或 dry-run 计划。
4. 若 dry-run：输出将执行 `git push -u origin <branch>`，但不执行。
5. 若 real-run：执行 `git push -u origin <branch>`，不得 force push；失败为 warning + next steps，不直接做 destructive 操作。

注意：

- `--preserve-features` 是“先保护证据”，不是“自动 merge feature branch 到 main”。
- 若当前 branch 是 main，仍可输出 main 已由 V1 A+ 策略保护；不重复做无意义 push 也可接受。

### 5.3 Patch manifest 读取与核对

触发条件：`config.patches_manifest is not None`。

读取行为：

- 文件不存在：warning，返回 empty manifest 或跳过；exit code 不变。
- schema_version 为 1：接受并按字段缺省补齐。
- schema_version 为 2：按本 SPEC 校验。
- YAML 解析失败：warning，跳过核对；不得中断升级。

核对行为：

1. 对每个 `PatchEntry`，先看 `upstream_merged`。
2. 若 false，尝试检查 `commit` 是否可由 `upstream_ref` 到达。
3. 若不可达，使用 `file_globs` 做 best-effort：可比较 `git show <commit> -- <glob>` 与 upstream 对应文件，或用 `git patch-id --stable` 判定等价 patch。
4. 输出 `PatchStatus` 列表到 stdout；真实执行可写入升级 manifest 的 `patch_statuses` 字段。
5. 默认不改写 `data/hermes_patches.yaml`，避免脚本自动做治理决策。

### 5.4 Dry-run 行为

V2 dry-run 在 SPEC-10-005 §4.7 基础上新增输出：

- 当前 branch 与 `--branch` 是否匹配。
- 若 `--preserve-features`：S0.5 计划，包括是否会 push 当前 branch。
- 若 `--patches-manifest`：manifest 路径、读取结果、patch status 摘要。
- 明确声明：dry-run 未修改 repo、venv、gateway、origin、patch manifest。

### 5.5 错误契约

| 错误情形 | 检测方式 | 处理方式 | 是否阻塞 |
|---|---|---|---|
| 当前 branch != `--branch` | S0 inspect | exit 1，给出 `--branch` 或 checkout 建议 | 是 |
| detached HEAD + preserve | `git branch --show-current` 空 | warning，跳过 feature push | 否 |
| origin remote 缺失 + preserve | `git remote get-url origin` | warning，输出手动处理 | 否 |
| feature push 失败 | `git push -u origin <branch>` exit != 0 | warning，输出手动 push | 否，除非后续 destructive 操作需要保护 |
| patches manifest 缺失 | path exists false | warning，跳过 | 否 |
| patches manifest 格式错误 | parse/schema fail | warning，跳过 | 否 |
| patch 核对命令失败 | git show/patch-id fail | PatchStatus=`unknown` | 否 |
| V1 主线备份/merge/install/verify 失败 | 继承 SPEC-10-005 | 按 V1 失败契约 | 是 |

## 6. 文件改动清单

### 6.1 新增

- `docs/rfc/10_infra/RFC-10-006-hermes-upgrade-script-v2.md`
- `docs/spec/10_infra/SPEC-10-006-hermes-upgrade-script-v2.md`
- `docs/design/10_infra/DESIGN-10-006-hermes-upgrade-script-v2.md`
- `data/hermes_patches.yaml`
- `tests/scripts/test_upgrade_hermes_agent_v2.py`

注意：当前项目 `.gitignore` 忽略 `/data/`，因此 Closeout 若要把 `data/hermes_patches.yaml` 纳入最终 commit，必须使用 `git add -f data/hermes_patches.yaml` 或另行确认迁移路径；本 SPEC 不要求修改 `.gitignore`。

### 6.2 修改

- `scripts/upgrade/upgrade_hermes_agent.py`

### 6.3 明确不改

- `docs/rfc/RFC-00-000-rfc-template.md`
- `docs/spec/SPEC-00-000-spec-template.md`
- `docs/design/DESIGN-00-000-design-template.md`
- `/home/pascal/workspace/hermes-agent/**`
- `~/.hermes/profiles/**/config.yaml`
- `~/.hermes/profiles/**/.env`
- `~/.hermes/auth.json` 或任意 token/auth 文件
- Hermes gateway systemd/platform 配置
- YQuant 投研、交易、风控、数据管道、报告业务代码

## 7. 测试要求

| 编号 | 类型 | 命令/方法 | 断言 |
|---|---|---|---|
| V2-UT-001 | CLI help | `python3 scripts/upgrade/upgrade_hermes_agent.py --help` | 输出包含 3 个新参数 |
| V2-UT-002 | branch config | 直接构造 args/config | `branch` 默认 main，可被覆盖 |
| V2-UT-003 | branch override | temp repo 当前 branch=`fix/feishu-table-card` | `--branch fix/feishu-table-card --dry-run` 不因 main-only 失败 |
| V2-UT-004 | preserve dry-run | temp repo + `--preserve-features --dry-run` | 输出 S0.5/push 计划，不执行 push |
| V2-UT-005 | manifest v2 parse | `data/hermes_patches.yaml` | 读出 1 个 `feishu-markdown-table` |
| V2-UT-006 | manifest v1 compat | 构造 schema_version=1 | 可读并补齐缺省字段 |
| V2-UT-007 | manifest missing | 指向不存在路径 | warning，不阻塞 |
| V2-UT-008 | patch status | mock git 命令 | 返回 merged/possibly-merged/pending/unknown |
| V2-REG-001 | V1 regression | `pytest tests/scripts/test_upgrade_hermes_agent.py` | 全部通过 |
| V2-REG-002 | V2 tests | `pytest tests/scripts/test_upgrade_hermes_agent_v2.py` | ≥3 个新增测试通过 |
| V2-SMOKE-001 | dry-run 默认 | `--dry-run --no-restart --no-push` | exit 0，V1 行为不变 |
| V2-SMOKE-002 | dry-run branch | `--dry-run --no-restart --no-push --branch fix/feishu-table-card` | 在匹配分支时 exit 0 |
| V2-SMOKE-003 | dry-run preserve | `--dry-run --no-restart --no-push --preserve-features` | exit 0，输出 S0.5 |
| V2-SMOKE-004 | dry-run patches | `--dry-run --no-restart --no-push --patches-manifest data/hermes_patches.yaml` | exit 0，输出 patch 核对报告 |

T3 Verify 必须执行：

```bash
cd /home/pascal/workspace/yquant-investment
python3 -m pytest tests/scripts/test_upgrade_hermes_agent.py tests/scripts/test_upgrade_hermes_agent_v2.py -v
python3 scripts/upgrade/upgrade_hermes_agent.py --help
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push --preserve-features
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push --patches-manifest data/hermes_patches.yaml
```

若真实当前 Hermes repo 不在 `fix/feishu-table-card`，`--branch fix/feishu-table-card` smoke 可用 temp repo 或 mock 验证，不要求切换真实 repo。

## 8. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A2-001 | 三层文档存在且交叉引用正确 | `test -f` + grep RFC/SPEC/DESIGN-10-006 |
| A2-002 | `data/hermes_patches.yaml` 存在且含 `feishu-markdown-table` | 读取 manifest |
| A2-003 | help 显示新参数 | V2-UT-001 |
| A2-004 | 默认 V1.0 行为不变 | V2-REG-001 + V2-SMOKE-001 |
| A2-005 | `--branch` 能覆盖 main-only 检查 | V2-UT-003 |
| A2-006 | `--preserve-features` dry-run 不 push 但输出计划 | V2-UT-004 / V2-SMOKE-003 |
| A2-007 | patch manifest 缺失/错误不阻塞 | V2-UT-007 |
| A2-008 | patch 核对输出状态而不自动改写 manifest | V2-UT-008 + git diff |
| A2-009 | 不新增依赖 | git diff dependency files |
| A2-010 | 不触碰禁止文件 | git diff --name-only |

## 9. Quick Flow / Q-LINK 契约

| Q-LINK | 契约 | SPEC 落点 |
|---|---|---|
| Q-LINK-001 | T1-T4 一次性预创建 | 元数据列出 T1/T2/T3/T4 task id |
| Q-LINK-002 | T1 产出三层独立文档 | §6 文件清单 |
| Q-LINK-003 | T2/T3/T4 parent links 自动推进 | 元数据 + task body |
| Q-LINK-004 | T2 只按 SPEC/DESIGN 实现，不修改 T1 文档 | §6.3 不改清单 |
| Q-LINK-005 | T3 独立验证 + 数据合理性抽样 | §7 测试要求 |
| Q-LINK-006 | T4 15 项自审 | RFC §6 / T4 body |

## 10. 风险与未解决问题

| 风险 | 缓解 | 归属 |
|---|---|---|
| `--branch` 与 `--version` 语义混淆 | help、RFC、SPEC 明确分离 | Developer/Reviewer |
| PyYAML 不可用 | 实现标准库 fallback 或简化 parser；不新增依赖 | Developer |
| patch-id 判定误报 | status 使用 `possibly-merged`，不自动改写 manifest | Tester/Closeout |
| preserve push 失败但后续升级继续 | warning 清晰输出；如后续步骤会破坏本地 commit，仍按 V1 保护规则阻塞 | Developer/Reviewer |
| 真实 branch smoke 影响工作区 | T3 使用 temp repo/mock，不切真实 Hermes repo | Tester |

未解决问题：

- `PatchStatus.upstream_contains_patch_id` 的最小实现可在 Design 中选择 `git patch-id --stable` 或文件 diff 子集；若实现成本过高，可先只做 commit reachability + file_globs existence，并把 patch-id 留为后续增强。
- 是否在 T4 Closeout 自动更新 `data/hermes_patches.yaml` 的 `upstream_merged`：本 SPEC 默认不自动更新。
