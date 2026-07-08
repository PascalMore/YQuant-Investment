# DESIGN-10-006：Hermes Agent 自动升级脚本 V2

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-07-08 |
| 来源 RFC | RFC-10-006-hermes-upgrade-script-v2 |
| 来源 SPEC | SPEC-10-006-hermes-upgrade-script-v2 |
| 继承 Design | DESIGN-10-005-hermes-auto-upgrade |
| 目标脚本 | `scripts/upgrade/upgrade_hermes_agent.py` |
| Quick Flow | T1=t_5b0e9e89, T2=t_5beea5d8, T3=t_fa87e65b, T4=t_3d1b2331 |

## 1. 设计摘要

本 Design 将 RFC/SPEC-10-006 的 V2 增量契约落为可实现的脚本修改方案。V1.0 已有脚本采用单文件标准库实现，并包含 `UpgradeConfig`、`RepoState`、`GitPlan`、`inspect_repo()`、`upgrade()`、`build_parser()`、`print_dry_run()` 等结构。V2 只做局部扩展，不重构主流程。

核心改动：

1. `UpgradeConfig` 增加 `branch`、`preserve_features`、`patches_manifest`。
2. `build_parser()` 增加 `--branch`、`--preserve-features`、`--patches-manifest`。
3. `inspect_repo()` 将硬编码 `branch != "main"` 改为 `branch != config.branch`。
4. `upgrade()` 在 S0 inspect 后插入 S0.5 `preserve_feature_branch_if_requested()`。
5. `upgrade()` 在 target resolve/merge 后或 dry-run 中插入 `run_patch_manifest_check_if_requested()`。
6. 新增 patch manifest dataclass、读取函数、best-effort 核对函数与 V2 测试。

设计目标是“最小可审计增量”：避免大范围重构 V1.0，避免引入新依赖，避免在 T2 阶段触碰真实 Hermes repo 或 gateway。

## 2. 现状代码锚点

### 2.1 V1.0 关键结构

| 位置 | 当前行为 | V2 处理 |
|---|---|---|
| `UpgradeConfig` (`scripts/upgrade/upgrade_hermes_agent.py:51-63`) | repo/version/dry-run/restart/push/rollback 等 | 增加 3 个字段 |
| `inspect_repo()` (`:403-491`) | 校验 git repo/remotes/branch/install_method/dirty/local-only | branch 检查改为配置驱动 |
| `print_dry_run()` (`:1080-1144`) | 输出 V1 计划 | 增加 branch/preserve/patch manifest 信息 |
| `upgrade()` (`:1152-1258`) | S0-S9 主流程 | S0 后插入 S0.5；merge/verify 前后插入 patch check |
| `build_parser()` (`:1416-1451`) | V1 参数 | 增加 V2 参数 |
| `config_from_args()` (`:1458-1469`) | args -> UpgradeConfig | 映射 V2 字段 |
| `tests/scripts/test_upgrade_hermes_agent.py` | V1 单测/集成测试 | 保持不改或仅因签名变化做兼容最小修正 |

### 2.2 关键限制对应代码

- main-only 限制：`inspect_repo()` 中 `if branch != "main"`。
- local-only commit 保护：`inspect_repo()` 与 `protect_local_commits()` 主要围绕 `upstream/main..HEAD`、`origin/main`。
- 无 patch manifest：当前无 `data/hermes_patches.yaml`，无 `PatchEntry` / `PatchesManifest`。

## 3. 方案设计

### 3.1 精确文件清单（≤ 6 文件）

T2 Implement 允许新增/修改以下文件，其他文件默认禁止：

1. 修改：`scripts/upgrade/upgrade_hermes_agent.py`
2. 新增：`tests/scripts/test_upgrade_hermes_agent_v2.py`
3. 新增：`data/hermes_patches.yaml`（T1 已创建；T2 只在 schema 必要时校验，不应随意改内容）
4. 新增：`docs/rfc/10_infra/RFC-10-006-hermes-upgrade-script-v2.md`（T1）
5. 新增：`docs/spec/10_infra/SPEC-10-006-hermes-upgrade-script-v2.md`（T1）
6. 新增：`docs/design/10_infra/DESIGN-10-006-hermes-upgrade-script-v2.md`（本文件）

T2 不应修改三层文档；若发现本 Design 与代码现实冲突，使用 `kanban_block` 退回 Principal，而不是自行扩大范围。

注意：项目 `.gitignore` 当前忽略 `/data/`。因此 `data/hermes_patches.yaml` 虽是本任务要求的交付物，但 T4 Closeout 若需要把它纳入 commit，必须显式使用 `git add -f data/hermes_patches.yaml`，或由 orchestrator 另行确认是否迁移到非 ignored 配置路径。本设计不修改 `.gitignore`，避免扩大文件清单。

### 3.2 数据结构设计

在 V1.0 dataclass 区域新增：

```python
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
    status: str  # merged | possibly-merged | pending | unknown
    reason: str
```

`UpgradeConfig` 新增字段：

```python
branch: str = "main"
preserve_features: bool = False
patches_manifest: Optional[Path] = None
```

实现注意：若当前 Python 版本/项目风格不使用 `list[str]` 以外的新 typing，不引入 `typing.Literal` 也可接受；status 用 string 常量即可。

### 3.3 CLI 设计

`build_parser()` 新增：

```python
p.add_argument("--branch", type=str, default="main",
               help="允许执行 inspect/upgrade 的当前 git 分支 (默认: main)")
p.add_argument("--preserve-features", action="store_true",
               help="升级前 best-effort push 当前 feature branch 到 origin 以保护本地 commit")
p.add_argument("--patches-manifest", type=Path, default=None,
               help="Pascal fork 私有 patch 清单路径，例如 data/hermes_patches.yaml")
```

`config_from_args()` 映射对应字段。

`validate_args()` 约束：

- rollback 模式不接受 `--preserve-features`、`--patches-manifest`；若 `--branch` 不是默认 `main` 也应视为冲突或明确忽略并提示。推荐保持简单：rollback 只接受默认 branch。
- `--patches-manifest` 可以是不存在路径；读取阶段 warning，不在参数阶段失败。

### 3.4 S0 branch 检查改造

当前：

```python
if branch != "main":
    raise UpgradeError(...)
```

改为：

```python
allowed = config.branch
if branch != allowed:
    raise UpgradeError(
        "inspect",
        f"当前分支为 '{branch}'，本次允许分支为 '{allowed}'。",
        next_steps=[
            f"如需在当前分支执行检查: --branch {branch}",
            f"如需默认升级: git -C {repo} checkout {allowed}",
        ],
    )
```

向后兼容：默认 `allowed == "main"`，因此不带新参数时仍保持 V1.0 安全默认。

### 3.5 S0.5 preserve feature branch

新增函数：

```python
def preserve_feature_branch_if_requested(config: UpgradeConfig, state: RepoState, manifest: dict) -> None:
    if not config.preserve_features:
        return
    branch = state.branch
    if not branch:
        log_warn("--preserve-features: detached HEAD，跳过 feature branch push。")
        manifest["preserve_features_status"] = "skipped-detached-head"
        return
    if config.dry_run:
        print(f"  [S0.5] dry-run: would run git push -u origin {branch}")
        manifest["preserve_features_status"] = "planned-dry-run"
        return
    r = git(["push", "-u", "origin", branch], repo=config.repo, manifest=manifest.setdefault("commands", []), verbose=config.verbose)
    if r.exit_code == 0:
        manifest["preserve_features_status"] = "ok"
    else:
        log_warn(f"--preserve-features: git push -u origin {branch} 失败，继续但请人工确认。")
        manifest["preserve_features_status"] = "warn-push-failed"
```

插入点：`upgrade()` 中 S0 inspect 成功、dry-run short-circuit 之前。这样 dry-run 的 S0.5 信息可进入 `print_dry_run()`；真实执行则在 backup/merge 前保护 feature branch。

安全边界：

- 禁止 force push。
- push 失败不直接执行 destructive 操作；但后续 V1 的 `protect_local_commits()` 若判断未保护仍可阻塞。
- 若当前 branch 是 main，可以允许 push main，也可以输出 “main 由 V1 origin 保护逻辑处理”；二者都可接受，建议减少重复 push。

### 3.6 Patch manifest 解析设计

优先策略：不新增依赖。实现函数必须先尝试可选 PyYAML，失败时使用受控 fallback：

```python
def _load_yaml_subset(path: Path) -> dict:
    try:
        import yaml  # optional, do not add dependency
    except Exception:
        return parse_simple_patches_yaml(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
```

fallback 只需支持本项目 manifest 子集：顶层 `schema_version`、`patches` 列表、字符串/null/bool、`file_globs` 字符串列表。若 fallback 无法解析，返回 warning/unknown，不阻塞升级。不得引入新依赖到项目 dependency 文件。

新增函数：

```python
def load_patches_manifest(path: Path) -> PatchesManifest:
    data = _load_yaml_subset(path)
    schema = int(data.get("schema_version", 1))
    patches = []
    for item in data.get("patches", []) or []:
        patches.append(PatchEntry(...))
    return PatchesManifest(schema_version=schema, patches=patches)
```

缺失/错误包装函数：

```python
def load_patches_manifest_safe(path: Optional[Path]) -> Optional[PatchesManifest]:
    if path is None: return None
    if not path.exists(): log_warn(...); return None
    try: return load_patches_manifest(path)
    except Exception as exc: log_warn(...); return None
```

### 3.7 Patch upstream 核对设计

最小可实现版本分两层：

1. commit reachability：
   - `git merge-base --is-ancestor <patch.commit> <upstream_ref>`；成功则 `merged`。
   - 若 commit 不存在或不可达，不失败。
2. patch-id best-effort（可选但推荐）：
   - `git show <patch.commit> -- <file_globs...> | git patch-id --stable` 得到 patch id；
   - 对 upstream ref 相关 history 或目标文件 diff 做有限比较；若成本过高，返回 `pending` 并 reason 说明 “patch-id check not implemented”。

建议 T2 先实现稳定的最小版本：commit reachability + manifest flag + file_globs 存在性检查。若 `upstream_merged=false` 且 commit 不可达，则 status=`pending`；如果 file_globs 无法读取则 status=`unknown`。

函数签名：

```python
def verify_patches_against_upstream(repo: Path, manifest: PatchesManifest, upstream_ref: str, *, cmd_manifest=None, verbose=False) -> list[PatchStatus]:
    ...
```

集成函数：

```python
def run_patch_manifest_check_if_requested(config: UpgradeConfig, manifest: dict, upstream_ref: str) -> None:
    pm = load_patches_manifest_safe(config.patches_manifest)
    if not pm:
        manifest["patch_statuses"] = []
        return
    statuses = verify_patches_against_upstream(config.repo, pm, upstream_ref, cmd_manifest=manifest.setdefault("commands", []), verbose=config.verbose)
    manifest["patch_statuses"] = [asdict(s) for s in statuses]
    print_patch_statuses(statuses)
```

插入点：

- dry-run：`print_dry_run()` 末尾可做读取 + best-effort 本地 refs 检查；若需要 fetch 才能判断，输出 `unknown-before-fetch`。
- real-run：`resolve_target_ref()` 后、`push_origin_if_enabled()` 前均可；推荐 merge/verify 后执行，使用已 fetch 的 upstream refs。

### 3.8 主流程插入

V2 `upgrade()` 控制流：

```text
S0 inspect_repo
S0.5 preserve_feature_branch_if_requested  # new
if dry_run: print_dry_run  # includes V2 info
S1 backup
S2 stash
S3 fetch
resolve target
S4 classify
S5 protect local commits
S6 merge
S6.5 patch manifest check if requested  # new; non-blocking
S7 install + verify
S8 restart
S9 push
```

若实现者认为 patch 核对应在 S9 push 后输出，也可接受；但不得影响“验证失败不 push”的 V1 安全顺序。

### 3.9 Dry-run 输出设计

在 V1 dry-run 输出基础上增加：

```text
branch allowed: <config.branch>
branch match: yes/no
preserve_features: enabled/disabled
patches_manifest: <path or disabled>
patches: <N loaded / skipped / warning>
声明: dry-run 未修改 repo、venv、gateway、origin、patch manifest。
```

若 `--preserve-features` 启用，计划步骤中新增：

```text
0.5 git push -u origin <branch>  (dry-run only; not executed)
```

若 `--patches-manifest` 启用，计划步骤中新增：

```text
6.5 patch manifest check -> best-effort upstream containment report
```

### 3.10 测试设计

新增 `tests/scripts/test_upgrade_hermes_agent_v2.py`。建议直接 import script module，复用 V1 测试 helper 风格。

必须覆盖：

1. `test_help_contains_v2_args`
2. `test_config_from_args_defaults_branch_main`
3. `test_config_from_args_branch_override`
4. `test_load_patches_manifest_v2_schema`
5. `test_load_patches_manifest_v1_backcompat`
6. `test_missing_patches_manifest_safe_returns_none_or_empty`
7. `test_branch_arg_overrides_main_check`：用 temp repo 在 `fix/feishu-table-card` 分支，`UpgradeConfig(branch="fix/feishu-table-card")` 调 `inspect_repo()` 不抛 main-only。
8. `test_branch_mismatch_fails_with_next_steps`
9. `test_preserve_features_dry_run_does_not_push`：mock `git()` 或在 dry-run 路径断言 manifest status。
10. `test_patch_status_pending_when_commit_not_in_upstream`

V1 回归必须运行：

```bash
python3 -m pytest tests/scripts/test_upgrade_hermes_agent.py tests/scripts/test_upgrade_hermes_agent_v2.py -v
```

### 3.11 回滚与降级

- 若 V2 参数实现破坏 V1 测试，优先回滚 `UpgradeConfig`/parser 的签名兼容问题。
- 若 YAML fallback 复杂度过高，允许 T2 将 `load_patches_manifest_safe()` 对无 PyYAML 环境降级为 warning + skip，但必须保留 `data/hermes_patches.yaml` 与后续增强 TODO；T3 需记录残余风险。
- 若 patch-id 判定实现不稳定，允许只实现 commit reachability + pending/unknown，不阻塞 T2；不得输出虚假的 “merged”。

## 4. 实现计划

1. 修改 `UpgradeConfig`、parser、config mapping、rollback 参数冲突校验。
2. 改造 `inspect_repo()` main-only 为 `config.branch`。
3. 新增 patch dataclasses 与 YAML safe loader/fallback。
4. 新增 `preserve_feature_branch_if_requested()` 并接入 `upgrade()` / dry-run 输出。
5. 新增 patch manifest check 函数并接入 dry-run/real-run。
6. 新增 `tests/scripts/test_upgrade_hermes_agent_v2.py`。
7. 跑 V1 + V2 pytest，修正兼容问题。
8. 跑 4 个 dry-run smoke，确认 no mutation 声明与输出。

## 5. 验证策略

### 5.1 自动化命令

```bash
cd /home/pascal/workspace/yquant-investment
python3 -m py_compile scripts/upgrade/upgrade_hermes_agent.py
python3 -m pytest tests/scripts/test_upgrade_hermes_agent.py tests/scripts/test_upgrade_hermes_agent_v2.py -v
python3 scripts/upgrade/upgrade_hermes_agent.py --help
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push --preserve-features
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push --patches-manifest data/hermes_patches.yaml
```

`--branch fix/feishu-table-card` 的真实 dry-run 如果当前 Hermes repo 不在该分支，不应强行切换真实 repo；使用 temp repo/mocked repo 测试即可。

### 5.2 数据合理性抽样（P-11）

T3 必须读取真实 `data/hermes_patches.yaml`，断言：

- schema_version == 2；
- patches 数量 ≥ 1；
- 存在 `id=feishu-markdown-table`；
- commit == `4d3a9661c`；
- file_globs 包含 `plugins/platforms/feishu/adapter.py`；
- patch 核对输出不应把未知状态伪报为 merged。

### 5.3 手工审查点

- `git diff --name-only` 不应出现禁止文件。
- dependency 文件无变化。
- V1.0 默认 help/dry-run 行为仍可读。
- 所有真实 push/restart 仍默认可通过 `--no-push` / `--no-restart` 跳过；T3 不执行真实副作用。

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| parser/config 新字段导致旧测试构造 `UpgradeConfig` 失败 | 给 dataclass 新字段设置默认值；必要时调整测试 fixture | 回滚 dataclass 签名或补默认值 |
| YAML fallback 不完整 | 只支持本 manifest 子集；解析失败 warning | skip patch check，不阻塞升级 |
| `--preserve-features` 在真实环境 push 错分支 | 使用当前 branch，禁止 force；dry-run 先展示 | 手动删除远端分支或忽略；不影响本地 |
| patch status 误判 merged | 只在 commit 可达或 manifest 已标 merged 时输出 merged；其他用 pending/unknown | T4 人工复核 |
| 触碰真实 Hermes repo/gateway | T2/T3 只跑 dry-run/temp repo/mock；禁止真实 restart/push | 停止并退回 Principal/主控 |

## 7. 交接给实现者

### 7.1 必须遵守

- 严格限制在 §3.1 文件清单内。
- 不修改三层文档、模板、Hermes profile、真实 Hermes repo。
- 不新增依赖；PyYAML optional，不可写入 dependency 文件。
- 不自动改写 `data/hermes_patches.yaml` 的 `upstream_merged`。
- V1 测试必须全过；V2 测试至少覆盖 SPEC §7 的新增行为。
- 任何真实 push/restart/merge 到 `/home/pascal/workspace/hermes-agent` 都需要 Pascal 或主控明确确认；T2 不做。

### 7.2 可自行判断

- patch-id best-effort 是否在本轮实现；若不实现，必须输出 pending/unknown，不得声称 merged。
- YAML fallback 的实现深度；只要真实 `data/hermes_patches.yaml` 可读且无新依赖即可。
- 是否把 patch statuses 写入 upgrade manifest；推荐写入，但不影响主升级安全。

### 7.3 遇到以下情况退回 Principal

- 需要新增第三方依赖。
- 需要改变 RFC-10-005 的 push/restart/rollback 主安全顺序。
- 需要修改文档模板或 AI Coding Pipeline skill。
- 需要真实操作 `/home/pascal/workspace/hermes-agent` 进行 destructive 验证。
- 发现 `--branch` 语义需要从“允许当前分支”升级为“自动 checkout/merge 到指定分支”。

## 8. 验收标准映射

| SPEC 验收 | Design 覆盖 |
|---|---|
| A2-001 三层文档 | 本文件 + RFC/SPEC-10-006 |
| A2-002 patch manifest | §3.6 / §5.2 |
| A2-003 help 新参数 | §3.3 / §5.1 |
| A2-004 V1 兼容 | §3.4 / §3.10 / §5.1 |
| A2-005 branch override | §3.4 / §3.10 |
| A2-006 preserve dry-run | §3.5 / §3.9 |
| A2-007 manifest 缺失/错误不阻塞 | §3.6 / §3.11 |
| A2-008 patch status 不自动改写 | §3.7 |
| A2-009 不新增依赖 | §3.6 / §7.1 |
| A2-010 不触碰禁止文件 | §3.1 / §7.1 |

## 9. Quick Flow / Q-LINK 自洽性

| Q-LINK | Design 落点 |
|---|---|
| Q-LINK-001 | 元数据列出 T1-T4，一次性预创建 |
| Q-LINK-002 | §3.1 明确三层独立文档 |
| Q-LINK-003 | T2/T3/T4 task body 通过 parents 串联 |
| Q-LINK-004 | §7.1 禁止 T2 修改 T1 文档 |
| Q-LINK-005 | §5.2 数据合理性抽样 |
| Q-LINK-006 | T4 Closeout body 执行 15 项自审 |
