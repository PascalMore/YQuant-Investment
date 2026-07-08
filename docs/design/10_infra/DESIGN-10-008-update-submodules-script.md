# DESIGN-10-008：通用多 submodule 升级器 update_submodules.py

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-07-09 |
| 版本号 | V2.0 |
| 来源 RFC | RFC-10-008-update-submodules-script (V2.0) |
| 来源 SPEC | SPEC-10-008-update-submodules-script (V2.0) |
| 目标脚本 | `scripts/upgrade/update_submodules.py` |
| Full Flow | T1_redo=t_91ffdfe3（重写为 auto-discovery + opt-in） |

## 1. 设计摘要

本 Design 将 RFC-10-008 V2.0 / SPEC-10-008 V2.0 的 **auto-discovery + opt-in override** 多 submodule 升级器落为可实现的脚本方案。脚本采用单文件标准库实现，复用 `upgrade_hermes_agent.py` V2 的 `CommandResult` dataclass、`run_cmd()` subprocess 封装、`redact()` 脱敏和 `_load_yaml_subset()` stdlib YAML fallback 模式，但不 import 该脚本（避免耦合），而是复制必要的 helper 函数。

**核心改动（V2.0 重写，T1_redo）**：

1. **不**新增 `data/submodules.yaml`（V1.0 彻底取消）。
2. 新增 `scripts/upgrade/update_submodules.py`（单文件，标准库，~500 行）。
3. 新增 `tests/scripts/test_update_submodules.py`（~200 行）。
4. 三层文档 RFC/SPEC/Design-10-008（V2.0 已重写）。
5. **新增** opt-in 覆盖：每个 submodule 仓库根目录可放 `.update_submodules.yaml` 覆盖启发式字段（**不**是项目级配置；由各 submodule 自行决定）。
6. **V2.0 关键修正**：
   - upstream remote 缺失 → **报清晰错误退出**，不自动 `git remote add`，不回落 origin。
   - health_check 默认 **None**（不预设 systemd_active 轮询）；opt-in 提供 **shell 命令字符串**。
   - opt-in schema 移除 `systemd_scope`/`restart_cmd`（systemd 固定 `--user`）；新增 `skip_push`。

## 2. 现状代码锚点（参考源）

### 2.1 从 upgrade_hermes_agent.py 复用的模式

| 模式 | V2 位置 | update_submodules.py 复用方式 |
|---|---|---|
| `CommandResult` dataclass | `:70-77` | 复制（同结构：cmd/cwd/exit_code/stdout/stderr） |
| `run_cmd()` subprocess 封装 | `:237-286` | 复制并简化（去掉 upgrade-specific manifest 记录逻辑，改为 audit-specific） |
| `redact()` 脱敏 | `:211-224` | 复制（相同 secret patterns） |
| `_load_yaml_subset()` YAML loader | `:313-500` | 复制 fallback parser，适配 opt-in `.update_submodules.yaml` schema |
| log/log_info/log_warn/log_ok/log_err | `:160-179` | 复制 |

### 2.2 不复用的部分

- `UpgradeConfig` / `RepoState` / `GitPlan` — Hermes-specific，不适用。
- `inspect_repo()` / `upgrade()` / `protect_local_commits()` — Hermes-specific 状态机。
- zip 备份 / detached restart / A+ merge — submodule 场景不需要。
- **`load_manifest()` 集中式 manifest 加载** — V1.0 设计；V2.0 取消，改为 `.gitmodules` 解析 + 启发式 + opt-in override。

### 2.3 新增代码模式（V2.0）

| 模式 | 用途 |
|---|---|
| `parse_gitmodules(project_root: Path) -> list[tuple[str, Path]]` | 解析 `.gitmodules` 的 `[submodule "<name>"]` section |
| `discover_submodule(name: str, path: Path, project_root: Path) -> SubmoduleConfig` | 启发式推断所有字段（origin/upstream/branch/venv/pip/systemd/health） |
| `load_optin_override(submodule_path: Path) -> Optional[dict]` | 加载 `<path>/.update_submodules.yaml`（如存在） |
| `merge_override(base: SubmoduleConfig, override: dict) -> SubmoduleConfig` | 将 opt-in 字段合并到启发式基线 |
| `match_systemd_unit(submodule_path: Path) -> Optional[str]` | systemctl --user list-units 模糊匹配 path 段 |
| `parse_origin_head(path: Path) -> Optional[str]` | `git -C <path> symbolic-ref refs/remotes/origin/HEAD` 推断 branch |

## 3. 方案设计

### 3.1 精确文件清单（2 个新代码文件 + 3 个文档重写）

T2 Implement 允许新增以下文件，其他文件默认禁止：

1. 新增：`scripts/upgrade/update_submodules.py`（~500 行）
2. 新增：`tests/scripts/test_update_submodules.py`（~200 行）
3. 文档（T1_redo 已重写，T2 不修改）：`docs/rfc/10_infra/RFC-10-008-update-submodules-script.md`
4. 文档（T1_redo 已重写，T2 不修改）：`docs/spec/10_infra/SPEC-10-008-update-submodules-script.md`
5. 文档（T1_redo 已重写，T2 不修改）：`docs/design/10_infra/DESIGN-10-008-update-submodules-script.md`

**T2 不应新增 `data/submodules.yaml`**（V1.0 已彻底取消）。

**T2 不应修改三层文档以外的任何文件**：不修改 `.gitmodules`、submodule 内部、systemd unit、业务代码、upgrade_hermes_agent.py、.gitignore。

T2 不应修改三层文档；若发现本 Design 与代码现实冲突，使用 `kanban_block` 退回 Principal。

### 3.2 5 阶段时序图（V2.0：auto-discovery + opt-in override）

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ update_submodules.py [--apply] [--push] [--only NAME...]                │
│                                                                          │
│  PARSE .gitmodules → list of (name, path)                                │
│                                                                          │
│  FOR each (name, path) [filtered by --only if specified]:               │
│    ┌─────────────────────────────────────────────────────────────┐      │
│    │  1. HEURISTIC DISCOVERY (cwd = project_root)                │      │
│    │     discover_submodule(name, path, project_root) → config    │      │
│    │       ├─ origin      = git remote get-url origin             │      │
│    │       ├─ upstream    = git remote get-url upstream           │      │
│    │       │                (缺失 → config.upstream=None,         │      │
│    │       │                 Phase 1 报错退出，不自动 add)          │      │
│    │       ├─ branch      = parse_origin_head() or "main"         │      │
│    │       ├─ venv        = ".venv" if exists else None          │      │
│    │       ├─ pip_install = ["install","-r","requirements.txt"]  │      │
│    │       │                if requirements.txt exists            │      │
│    │       ├─ systemd_service = match_systemd_unit()              │      │
│    │       ├─ health_check = None  (V2.0 默认)                    │      │
│    │       └─ skip_push   = False                                │      │
│    │                                                              │      │
│    │  2. OPT-IN OVERRIDE (cwd = <path>)                          │      │
│    │     load_optin_override(<path>) → Optional[dict]            │      │
│    │     if loaded: merge_override(config, override)             │      │
│    │     if failed: warn + fall back to heuristic                │      │
│    │                                                              │      │
│    │  3. SubmoduleState init                                      │      │
│    │                                                              │      │
│    │  unless --resume-after-merge:                                │      │
│    │    Phase 1: FETCH                                            │      │
│    │      if config.upstream is None:                             │      │
│    │        ERROR "upstream remote missing, git remote add ..."   │      │
│    │        ABORT submodule (不自动 add)                          │      │
│    │      git fetch upstream <branch>                             │      │
│    │      compute behind/ahead                                    │      │
│    │      if behind==0: skip Phase 2                              │      │
│    │                                                              │      │
│    │    unless --skip-merge:                                      │      │
│    │    (and behind > 0)                                          │      │
│    │      Phase 2: MERGE                                          │      │
│    │        run pre_merge_hooks                                   │      │
│    │        ahead==0 → git merge --ff-only upstream/<branch>      │      │
│    │        ahead>0  → git merge upstream/<branch>                │      │
│    │        conflict → git merge --abort → ABORT submodule        │      │
│    │                                                              │      │
│    │  unless --skip-install:                                      │      │
│    │    Phase 3: INSTALL                                          │      │
│    │      skip if venv=None or pip_install=None                   │      │
│    │      <venv>/bin/pip install <pip_install args>               │      │
│    │      exit!=0 → ABORT submodule                               │      │
│    │                                                              │      │
│    │  unless --skip-restart:                                      │      │
│    │    Phase 4: RESTART                                          │      │
│    │      skip if systemd_service=None                            │      │
│    │      systemctl --user restart <service>                      │      │
│    │      if config.health_check (opt-in shell cmd):              │      │
│    │        sh -c <health_check cmd>                              │      │
│    │        exit!=0 → ABORT push                                  │      │
│    │      (health_check=None → SKIP, V2.0 默认)                   │      │
│    │                                                              │      │
│    │    if --push and skip_push!=True and all above PASS:         │      │
│    │      Phase 5: PUSH                                           │      │
│    │        git push origin <branch> (never --force)             │      │
│    │        exit!=0 → report but no rollback                      │      │
│    │                                                              │      │
│    │  RECORD PipelineResult                                       │      │
│    └─────────────────────────────────────────────────────────────┘      │
│    if --fail-fast and this submodule FAILED: BREAK                      │
│                                                                          │
│  WRITE audit log /tmp/update_submodules_audit_<ts>.md                   │
│  PRINT summary table                                                     │
│  EXIT 0 if all PASS, exit 1 if any FAIL                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.3 数据结构

```python
@dataclass(frozen=True)
class SubmoduleConfig:
    """单个 submodule 的运行时配置（启发式 + opt-in merge 后）。"""
    name: str
    path: Path
    origin: Optional[str]
    upstream: Optional[str]          # None = 缺失，Phase 1 报错退出
    branch: str
    venv: Optional[Path]             # None = 跳过 install
    pip_install_cmd: Optional[tuple[str, ...]]  # None = 跳过 install; 不含 "pip" 前缀
    pre_merge_hooks: tuple[str, ...]
    systemd_service: Optional[str]   # None = 跳过 restart
    health_check: Optional[str]      # None = 不检查（V2.0 默认）; shell 命令字符串
    skip_push: bool                  # opt-in 级别跳过 push（极少用）
    notes: str
    config_source: str  # "heuristic" | "heuristic+opt-in" | "opt-in-only"（用于 audit）


@dataclass
class CommandResult:
    """复用 V2 模式：5 字段，no logic。"""
    cmd: list
    cwd: Optional[str]
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class SubmoduleState:
    config: SubmoduleConfig
    abs_path: Path
    pre_head: Optional[str]
    behind: int
    ahead: int
    upstream_ref: str


@dataclass
class PhaseResult:
    phase: str  # "fetch" | "merge" | "install" | "restart" | "push"
    status: str  # "pass" | "fail" | "skip" | "abort"
    exit_code: Optional[int]
    duration_sec: float
    detail: str


@dataclass
class PipelineResult:
    name: str
    config_source: str
    phases: list  # list[PhaseResult]
    overall: str  # "pass" | "fail"
    abort_reason: Optional[str]
```

**注**：V1.0 的 `Manifest` / `SubmodulesManifest` 类**已删除**（V2.0 取消中央 manifest 注册表）。V1.1 的 `systemd_scope`/`restart_cmd` 字段**已移除**（systemd 固定 `--user`）。

### 3.4 关键函数签名

```python
def parse_gitmodules(project_root: Path) -> list[tuple[str, Path]]:
    """解析 .gitmodules 的 [submodule "<name>"] sections。
    返回 [(name, rel_path), ...]，name 与 .gitmodules section 名完全一致。
    """


def discover_submodule(name: str, path: Path, project_root: Path) -> SubmoduleConfig:
    """启发式推断所有字段（origin/upstream/branch/venv/pip/systemd/health）。
    cwd = project_root；后续 git 命令自动 -C <path> 切换。
    upstream 缺失时 config.upstream=None（Phase 1 报错，不在此处 raise）。
    health_check 默认 None（V2.0）。
    """


def load_optin_override(submodule_path: Path) -> Optional[dict]:
    """加载 <submodule_path>/.update_submodules.yaml。
    文件不存在 → None（常态）。
    YAML 解析失败 → warning + None（回落启发式）。
    schema 校验失败 → warning + None（回落启发式）。
    """


def merge_override(base: SubmoduleConfig, override: dict) -> SubmoduleConfig:
    """每个字段独立合并：override 中存在的字段覆盖 base，未指定的保留。
    config_source 根据覆盖比例标记为 "heuristic+opt-in" / "opt-in-only"。
    health_check 覆盖为 shell 命令字符串（V2.0）。
    """


def match_systemd_unit(submodule_path: Path) -> Optional[str]:
    """systemctl --user list-units --type=service --no-legend 中模糊匹配 path 段。
    取最长 match（避免 'analysis' 匹配 'data-analysis' 之类过短匹配）。
    无 match → None（启动 restart 阶段 SKIP）。
    """


def parse_origin_head(submodule_path: Path) -> Optional[str]:
    """git -C <path> symbolic-ref refs/remotes/origin/HEAD → 提取 branch 名。
    失败 → None（fallback "main"）。
    """


def load_yaml(path: Path) -> dict:
    """YAML 加载：优先 PyYAML（optional），fallback 到 stdlib 子集解析。
    复用 upgrade_hermes_agent.py V2 的 _load_yaml_subset() 模式。
    """


def validate_override(raw: dict) -> Optional[dict]:
    """校验 .update_submodules.yaml schema（V2.0）。
    返回 validated dict 或 None（schema 错误）。
    health_check 必须是 string 或 null（不再是 dict）。
    """


def run_cmd(cmd: list, *, cwd: Optional[str] = None, check: bool = False,
            capture: bool = True, env: Optional[dict] = None,
            audit_phases: Optional[list] = None,
            verbose: bool = False, timeout: Optional[int] = None) -> CommandResult:
    """统一执行外部命令。禁止 shell=True。"""


def phase_fetch(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 1: fetch upstream。
    config.upstream is None → ABORT（报清晰错误，不自动 add）。
    """


def phase_merge(state: SubmoduleState, *, dry_run: bool) -> PhaseResult: ...
def phase_install(state: SubmoduleState, *, dry_run: bool) -> PhaseResult: ...
def phase_restart(state: SubmoduleState, *, dry_run: bool) -> PhaseResult:
    """Phase 4: restart + health_check（opt-in cmd 时）。
    health_check=None → SKIP（V2.0 默认）。
    health_check=cmd → sh -c cmd; exit!=0 → ABORT push。
    """


def phase_push(state: SubmoduleState, *, dry_run: bool) -> PhaseResult: ...


def process_submodule(name: str, path: Path, project_root: Path, *,
                      skip_merge: bool = False, skip_install: bool = False,
                      skip_restart: bool = False,
                      resume_after_merge: bool = False,
                      do_push: bool = False,
                      dry_run: bool = True) -> PipelineResult: ...


def filter_by_only(submodules: list, only_names: list) -> list:
    """按 --only 过滤。
    匹配规则：section name 精确匹配 或 path basename 后缀匹配。
    缺名 → exit 1（不静默 fallback）。
    """


def main():
    """argparse → parse .gitmodules → filter by --only →
    serial process → audit log → summary."""
```

### 3.5 subprocess 封装（CommandResult + run_cmd）

复用 V2 模式，简化 manifest 参数为 audit purposes：

实现要点：
- `subprocess.run()` with `shell=False`，`text=True`，`check=False`。
- `FileNotFoundError` → exit_code=127。
- `subprocess.TimeoutExpired` → exit_code=124。
- 记录 cmd/cwd/exit_code + stdout/stderr 尾部（redact 后）到 audit_phases。
- **health_check 执行用 `sh -c <cmd>`**（opt-in 提供的 shell 命令字符串；不走 run_cmd 的 shell=False，而是显式 `["sh", "-c", cmd]`）。

### 3.6 错误处理决策树（V2.0）

```text
错误发生
  │
  ├─ Phase 1 upstream remote 缺失（config.upstream is None）
  │   ├─ V2.0：报清晰错误退出该 submodule
  │   │   错误信息：
  │   │     submodule "<name>" 缺少 upstream remote.
  │   │       当前 remotes: <list>
  │   │       请手动执行: git -C <path> remote add upstream <url>
  │   │       或在 <path>/.update_submodules.yaml 中声明 upstream URL
  │   ├─ 不自动 git remote add（V2.0 关键决策）
  │   ├─ 不回落 origin
  │   └─ --fail-fast → BREAK
  │
  ├─ Phase 1 fetch 失败（网络/upstream URL 错）
  │   ├─ warning, ABORT 该 submodule, 继续其他
  │   └─ --fail-fast → BREAK
  │
  ├─ Phase 2 merge 冲突
  │   ├─ 检测 conflict markers (UU/AA/DD in git status)
  │   │   → git merge --abort
  │   │   → ABORT 该 submodule, 记录 pre_head, 输出 "手动解决后 --resume-after-merge"
  │   ├─ 非 conflict 的 merge 失败 → ABORT, 记录 stderr
  │   └─ --fail-fast → BREAK
  │
  ├─ Phase 3 pip install 失败
  │   ├─ venv 不存在 → SKIP（不是 ABORT；记 reason="venv_missing"）
  │   ├─ pip_install 为 None → SKIP
  │   ├─ pip exit!=0 → ABORT, 记录 stderr_tail
  │   └─ --fail-fast → BREAK
  │
  ├─ Phase 4 restart 失败
  │   ├─ systemd_service=None → SKIP
  │   ├─ systemctl exit!=0 → ABORT push, 记录 stderr
  │   ├─ health_check=None → SKIP health check（V2.0 默认）
  │   ├─ health_check=cmd 且 exit!=0 → ABORT push, "health check 失败"
  │   └─ --fail-fast → BREAK
  │
  ├─ Phase 5 push 失败
  │   ├─ non-fast-forward → 报告但不 rollback（不 --force）
  │   └─ 网络错误 → 报告但不 rollback
  │
  └─ .update_submodules.yaml 加载/校验失败
      └─ warning + 回落启发式（不阻塞该 submodule）
```

### 3.7 边界场景（V2.0）

| 场景 | 检测 | 处理 |
|---|---|---|
| submodule 缺 upstream remote | `git remote` 不含 "upstream" | **报清晰错误退出该 submodule**（V2.0；不自动 add）。错误信息含 `git remote add` 提示 |
| `.update_submodules.yaml` 不存在 | `path / ".update_submodules.yaml"` 不存在 | 常态；直接用启发式 |
| `.update_submodules.yaml` 格式错误 | YAML 解析失败或 schema 校验失败 | warning + 回落启发式；不阻塞该 submodule |
| health_check 未配置 | config.health_check is None | Phase 4 health check SKIP（V2.0 默认） |
| health_check 配置为 shell cmd | config.health_check is str | `sh -c <cmd>`; exit!=0 → ABORT push |
| 缺 systemd service | 启发式无匹配 + opt-in 无声明 | 跳过 Phase 4，记 SKIP |
| dirty worktree | Phase 1 前检查 `git status --porcelain` | dry-run 输出 warning；apply 时若 `pre_merge_hooks` 含 stash 命令则执行；否则 warning 继续但 merge 可能失败 |
| 缺 venv | 启发式 venv 探测为 None | Phase 3 SKIP（不是 ABORT），继续 restart/push |
| 缺 requirements.txt | 启发式 pip_install 探测为 None | Phase 3 SKIP（不是 ABORT） |
| submodule path 不存在 | 启发式 phase_fetch 失败 | warning + ABORT 该 submodule |
| `--only` 指定不存在的 name | `.gitmodules` 无匹配 name | exit 1 报错（**不**静默 fallback；SPEC §4.1） |
| `--only` 短名匹配 | path basename 后缀匹配 | 匹配成功（如 `--only daily-stock-analysis` 匹配 `skills/research/daily_stock_analysis`） |
| `--only` 多次 | `action="append"` | 累积所有 names |
| `--apply` 与 `--dry-run` 同时传 | argparse 互斥组 | exit 2 |
| `--skip-merge` 与 `--resume-after-merge` 同时传 | argparse 互斥组 | exit 2 |
| 启发式 systemd 模糊匹配误中（重名） | 模糊匹配取最长 path 段 | dry-run 输出推断结果供审查；opt-in YAML 可修正 |
| `skip_push: true` in opt-in | config.skip_push=True | Phase 5 SKIP，即使 `--push` 启用 |

### 3.8 与 V2 upgrade 共享的代码

本脚本**不 import** `upgrade_hermes_agent.py`（避免跨脚本耦合）。共享的 helper 通过复制实现：

| 共享代码 | 复用方式 | 理由 |
|---|---|---|
| `CommandResult` dataclass | 复制（同结构） | 5 字段，无逻辑，复制成本 < import 成本 |
| `run_cmd()` | 复制并简化 | V2 版本有 upgrade-specific manifest 参数，本脚本改为 audit_phases |
| `redact()` + secret patterns | 复制 | 相同脱敏需求 |
| `_load_yaml_subset()` | 复制 fallback parser | 适配 opt-in `.update_submodules.yaml` schema（与 V2 patches schema 同源） |
| log helpers | 复制 | 相同输出风格 |

**替代方案（T2 可选）**：如果实现者判断复制代码会导致维护漂移，可在 `scripts/upgrade/` 下提取 `common.py` 共享模块。但 V2.0 推荐保持单文件 `update_submodules.py`，避免扩大文件清单。提取共享模块属于后续重构，不在本 Design 范围。

## 4. 实现计划

1. 复制 `CommandResult`、`run_cmd()`、`redact()`、`_load_yaml_subset()` 相关 helper 到 `update_submodules.py`。
2. 实现 5 个 dataclass：`SubmoduleConfig` / `SubmoduleState` / `PhaseResult` / `PipelineResult` / `CommandResult`。
3. 实现发现层：`parse_gitmodules()` / `discover_submodule()` / `load_optin_override()` / `merge_override()` / `match_systemd_unit()` / `parse_origin_head()`。
4. 实现 `filter_by_only()`（section name 精确匹配 + path basename 后缀匹配；缺名 exit 1）。
5. 实现 5 阶段函数：`phase_fetch()` / `phase_merge()` / `phase_install()` / `phase_restart()` / `phase_push()`。
6. 实现 `process_submodule()` 串联 5 阶段（含启发式 + opt-in override merge）。
7. 实现 `main()`：argparse → parse .gitmodules → filter --only → serial process → audit log → summary。
8. 写测试 `tests/scripts/test_update_submodules.py`（19+ 用例覆盖 SPEC §9）。
9. 跑 pytest + dry-run smoke。

## 5. 验证策略

### 5.1 自动化命令

```bash
cd /home/pascal/workspace/yquant-investment
python3 -m py_compile scripts/upgrade/update_submodules.py
python3 -m pytest tests/scripts/test_update_submodules.py -v
python3 scripts/upgrade/update_submodules.py --help
python3 scripts/upgrade/update_submodules.py --dry-run
python3 scripts/upgrade/update_submodules.py --dry-run --only daily-stock-analysis
python3 scripts/upgrade/update_submodules.py --dry-run --only nonexistent  # 期望 exit 1
```

### 5.2 数据合理性抽样（P-11）

T3 必须从真实 `.gitmodules` 解析 + 启发式推断，断言：
- `.gitmodules` 至少含 `skills/research/daily_stock_analysis` + `skills/apps/TradingAgents-CN` 2 个 section。
- `discover_submodule()` 对两者返回非空 `origin` / `upstream`（upstream remote 真实存在）。
- `daily-stock-analysis` 启发式推断 venv=".venv" + pip_install 非空 + systemd_service 含 "daily-stock-analysis" 子串。
- `tradingagents-cn` 启发式推断 venv=".venv" + pip_install 非空 + systemd_service 含 "tradingagents-cn" 子串。
- **health_check 默认 None**（V2.0）：无 opt-in 时 config.health_check is None。
- 创建一个含 `.update_submodules.yaml`（`health_check: "systemctl --user is-active --quiet x.service"`）的临时 submodule fixture，验证 `load_optin_override()` 正确加载且 `merge_override()` 应用 override（health_check 变为该 cmd 字符串）。

### 5.3 手工审查点

- `git diff --name-only` 不应出现禁止文件（submodule 内部、systemd unit、业务代码、upgrade_hermes_agent.py、.gitmodules、.gitignore）。
- 确认**不**存在 `data/submodules.yaml`（V1.0 取消）。
- dependency 文件无变化。
- dry-run 输出可读，包含每个 submodule 的 5 阶段计划 + config_source（heuristic / heuristic+opt-in）。
- **upstream remote 缺失时报清晰错误**（mock/temp repo 验证；不自动 add）。
- `--only nonexistent` 退出 1 报错（不静默 fallback）。
- `--apply` 不带 `--push` 时执行到 Phase 4 但不 push。
- 永远不出现 `--force` 参数。
- **health_check=None 时不执行任何 health check 命令**（V2.0 默认）。

## 6. 风险、降级与回滚

| 风险 | 应对 | 降级/回滚 |
|---|---|---|
| merge 冲突频繁 | 自动 abort + 报告 | 人工解决后 `--resume-after-merge` |
| pip 破坏 venv | opt-in health_check 捕获 | 人工重建 venv |
| restart 中断服务 | opt-in health_check 确认恢复 | 人工 `systemctl --user restart` |
| push 覆盖 origin | 永远不 --force | git reflog 恢复 |
| 启发式 systemd 模糊匹配误中 | dry-run 暴露；opt-in YAML 修正 | opt-in override |
| 启发式 branch 推断失败 | fallback `main`；opt-in YAML 修正 | opt-in override |
| `.update_submodules.yaml` 格式错误 | warning 回落启发式 | 人工修正 YAML |
| YAML fallback 不完整 | 只支持 override schema 子集 | skip，warning |
| 触碰真实 submodule 内部文件 | T2/T3 只跑 dry-run/mock/temp repo | 停止退回 Principal |
| **upstream 缺失被误判**（实际存在但 get-url 失败） | 错误信息含当前 remotes 列表，便于诊断 | 人工检查 git remote |
| **health_check 默认 None 导致异常未发现** | Pascal 按需 opt-in 配置 | Closeout 记录残余风险 |

## 7. 交接给实现者

### 7.1 必须遵守

- 严格限制在 §3.1 文件清单内（2 个新代码文件 + 3 个文档已由 T1_redo 重写）。
- **不**新增 `data/submodules.yaml`（V1.0 已彻底取消）。
- 不修改三层文档、模板、upgrade_hermes_agent.py、systemd unit、submodule 内部文件、.gitmodules、.gitignore。
- 不新增依赖；PyYAML optional，不可写入 dependency 文件。
- 永远不接受 `--force` 参数。
- `--only` 用 `action="append"`，缺名 exit 1（不静默 fallback）。
- dry-run 是默认，`--apply` 才真正执行。
- **upstream remote 缺失时报清晰错误退出**（不自动 `git remote add`）。
- **health_check 默认 None**；opt-in 提供 shell 命令字符串时才执行。
- systemd 固定 `--user` scope（V2.0 移除 systemd_scope/restart_cmd 字段）。
- 任何真实 restart / push 需要人工确认；T2 不执行真实副作用。
- 复制 helper 而非 import upgrade_hermes_agent.py。

### 7.2 可自行判断

- `--resume-after-merge` 的实现深度（推荐 V1 只跳过 fetch+merge）。
- 是否提取 `scripts/upgrade/common.py` 共享模块（推荐 V2.0 不提取，保持单文件）。
- audit 日志的具体 Markdown 格式细节（只要包含 SPEC §7 的关键字段）。
- 启发式 systemd 模糊匹配的具体算法（推荐"最长 path 段 match"，实现者可微调）。

### 7.3 遇到以下情况退回 Principal

- 需要新增第三方依赖。
- 需要修改 `.gitmodules` 或 systemd unit 文件。
- 需要修改 submodule 内部文件。
- 需要修改 RFC/SPEC/Design-10-008 文档。
- 发现 5 阶段流水线顺序需要调整（如 push 需要在 restart 前）。
- 发现 auto-discovery 启发式算法根本不可行（如 systemctl 模糊匹配严重误判且 opt-in 不够用）。
- 发现 upstream 缺失时自动 add 反而更合理（需 Principal 重新评估 V2.0 决策）。

## 8. 验收标准映射

| SPEC 验收 | Design 覆盖 |
|---|---|
| A-001 三层文档 | 本文件 + RFC/SPEC-10-008 |
| A-002 不存在 `data/submodules.yaml` | §3.1 / §5.3 |
| A-003 help 全部参数 | §3.2 + SPEC §4 |
| A-004 dry-run no mutation | §3.2 / §5.1 |
| A-005 dry-run 输出计划 | §3.2 |
| A-006 apply 不 push（无 --push） | §3.2 Phase 5 条件 |
| A-007 behind=0 跳过 merge | §3.2 Phase 2 条件 |
| A-008 merge 冲突 abort | §3.6 决策树 |
| A-009 pip 失败 abort | §3.6 决策树 |
| A-010 health_check 失败 abort push | §3.6 决策树（opt-in cmd 时） |
| A-011 永远不 --force | §3.2 Phase 5 / §7.1 |
| A-012 --only 过滤 + 可重复 | §3.2 FILTER 步骤 + §3.4 `filter_by_only()` + §3.7 |
| A-013 --only 缺名 exit 1 | §3.7 |
| A-014 互斥参数 exit 2 | §3.7 边界场景 |
| A-015 audit 日志生成 | §3.2 WRITE audit log |
| A-016 不新增依赖 | §3.8 / §7.1 |
| A-017 不触碰禁止文件 | §3.1 / §7.1 |
| A-018 opt-in override 覆盖字段 | §3.4 `merge_override()`（health_check 为 shell cmd 字符串） |
| A-019 opt-in 失败回落启发式 | §3.7 边界场景 |
| A-020 启发式 systemd 模糊匹配 | §3.4 `match_systemd_unit()` |
| **A-021** upstream 缺失报错退出 | §3.6 决策树 / §3.7 / §7.1 |
| **A-022** health_check 默认 None | §3.3 SubmoduleConfig / §3.6 / §3.7 / §5.2 |
