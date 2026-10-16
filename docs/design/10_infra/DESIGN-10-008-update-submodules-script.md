# DESIGN-10-008：通用多 submodule 升级器 update_submodules.py

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-10-16 |
| 版本号 | V2.1（分支映射增量设计，非脚本发布号） |
| 来源 RFC | [RFC-10-008 V2.1](../../rfc/10_infra/RFC-10-008-update-submodules-script.md) |
| 来源 SPEC | [SPEC-10-008 V2.1](../../spec/10_infra/SPEC-10-008-update-submodules-script.md) |
| 目标脚本 | `scripts/upgrade/update_submodules.py` |
| Full Flow | 本次 T1=t_5c700339 → T2=t_12bc9198 → T3=t_47f13df1；历史 T1_redo=t_91ffdfe3 |

## 版本记录

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V2.0 | 2026-07-09 | auto-discovery + opt-in 原始实现设计 | YQuant-Codex-Principal |
| V2.1 | 2026-10-16 | t_12bc9198：按 RFC/SPEC V2.1 定义双分支透传、目标校验、本轮 fetch commit 绑定、unknown/fail、隔离 Git 验证与 G3 边界；仅设计，未实现 | YQuant-Codex-Principal |

## 0. 本次适用优先级与阶段边界

本次为已有 v2.2.0 的最小增量设计，不重新开发升级器。以 RFC-10-008 §0–§0.1、SPEC-10-008 §3.4–§3.8 / §8.1 为需求来源；本文件 §3.1、§3.9、§4、§5.1、§7、§8.1 为当前实现输入，优先于历史单 branch 算法/示例/旧数据结构。其余历史非分支设计保留作背景，运行基线以现有源码和 DESIGN-10-012 为准，不授权复制 helper、重做 install/restart 或改发现之外的业务逻辑。

- 本卡只改本 Design，及 DESIGN-10-012 的一条必要交叉说明；不改 RFC/SPEC、代码、测试、配置或任何 submodule。共享 main 的四份既有 RFC/SPEC 差异属于 T1，不得清理或计入本卡修改。
- OctoBot 源码 submodule 已接入；主仓 HEAD 为 `042e55b2ce54af2186353f6f50aa3524ce39d5fe`，子仓 main/HEAD 与 gitlink 为 `c45fdc2c95c5bd3d649251fa90c327e2e8f86b00`。无新 yaml 即发现 master→main 是待实现目标，不是已完成能力。
- 原五阶段、默认 dry-run/不 push、非 force、dirty 拒跑、冲突 abort、skip/fail-fast、install_exclude/诊断保留。不新增 CLI/中央 manifest/依赖/长期服务/发布步骤；脚本 `__version__=2.2.0` 本轮不变。
- 主控 2026-10-16 T2 放行说明已裁定：既有普通 push 执行失败仍可能 overall=pass，是本轮 scope 外残余，不能扩展为通用失败聚合改造。本设计仅保证本次分支输入/目标校验/来源比较失败 overall=fail、CLI exit 1；不把既有 push 汇总问题说成已修复。
- 全部 Implement、独立 Verify、独立 Review PASS 前不得宣称修复可用；真实 apply/push、安装/重启和服务/数据库变更均未获授权。

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

### 3.1 本次精确 allowlist（取代旧“新增脚本”清单）

| 阶段 | 允许写入路径 | 限制 |
|---|---|---|
| T2 Design | `docs/design/10_infra/DESIGN-10-008-update-submodules-script.md` | 仅增量设计，保留非分支历史 |
| T2 Design | `docs/design/10_infra/DESIGN-10-012-update-submodules-install-exclusion-and-diagnostics.md` | 仅必要的一条分支优先级/兼容交叉说明 |
| T3 Implement | `scripts/upgrade/update_submodules.py` | 修改现有文件；具体函数见 §3.9，不重写升级器 |
| T3 Implement | `tests/scripts/test_update_submodules.py` | 仅旧断言/fixture/API 必要兼容调整，保留原覆盖 |
| T3 Implement | `tests/scripts/test_update_submodules_branch_mapping.py` | 新建分支用例与本地 Git fixture，少于 1200 行 |

`tests/scripts/test_auto_push_submodule_order.py` 为只读回归输入，不允许修改。四份 RFC/SPEC 的 T1 既有差异不是 T3 编辑许可；T3 不改任何文档。禁止修改主仓 `.gitmodules`、全部 gitlink、全部子仓文件（包括 yaml、Git config/refs）、其他模块、`skills/strategies/README.md`、`upgrade_hermes_agent.py`、依赖声明、Hermes 核心/profile、其他项目、systemd/cron/数据库/凭据/交易配置。不 push/reset/stash/clean 共享树，不切换主仓 main；本卡不 commit，T3 仅按其任务卡的明确许可精确 stage/本地提交（或留给 Closeout），不提交无关差异；策略 README 仅 Review PASS 后由 Closeout 按其授权处理。

隔离测试运行文件可创建在当前 profile `$TMPDIR`/scratch；它们不是新增项目模块。所有 fixture remote 必须是该隔离目录内本地 bare 路径，不能指向 GitHub、真实子仓或其他生产目录。

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

### 3.9 V2.1 双分支增量（当前实现设计）

#### 3.9.1 真实基线与函数改动

以下行号为 2026-10-16 读取的 v2.2.0 基线，不是新增代码位置。

| 现有落点 | 本轮最小修改 |
|---|---|
| `SubmoduleConfig` :105；`discover_submodule` :521；`_replace_config` :678 | frozen config 末尾加 `upstream_branch: Optional[str] = None`，两构造点透传；原 branch 改为仅目标语义；install_exclude 原样透传 |
| `normalize_remote_branch` :386；`parse_origin_head` :414 | 复用并收紧角色前缀/合法名校验，保留完整分支路径；origin HEAD 仅服务目标 fallback |
| `_discover_branch` :467；`_detect_upstream_default_branch` :425 | 前者只选目标，后者只选来源；不再用 upstream 默认作为目标 |
| `validate_override` :575；`load_optin_override` :615；`merge_override` :636 | 白名单保留 upstream_branch；明确分支输入错误与 YAML/schema 加载错误的不同；branch-only legacy 同名兜底 |
| `SubmoduleState` :136；`phase_fetch` :949；`_parse_rev_count` :989 | behind/ahead 可为 None；来源比较失败不返回 0/0；apply 保存本轮 FETCH_HEAD 的 commit SHA |
| `phase_merge` :1025；`process_submodule` :1388 | 目标前置校验、hook 后 merge 前与 push 前复核、来源/错误透传和 resume 短路；移除 :1404–1407 的冗余单 branch 补丁 |

无需修改 `parse_gitmodules` 的 `list[tuple[str, Path]]` 返回形状；按 section 身份另读目标 branch 即可。`run_cmd`、YAML parser、`phase_install` 及其过滤/清理、pip 分类、`phase_restart`、`phase_push` 的原非 force 推送命令、CLI parser、only 匹配、审计结构均不重构。process 用现有 `log_info` 输出来源/目标/证据及 fetch/merge/push 的 PhaseResult.detail，不用默认静默的 `log`；确保 `--no-audit` 且不带 verbose 也能看到分支/unknown/推送计划，不扩展安装/重启输出。`write_audit` 已原样呈现 detail，无需新输出模型。

#### 3.9.2 加载、覆盖与 dataclass 全链路

`process_submodule` 改为先 `load_optin_override`，再 `discover_submodule`，随后沿用 `merge_override`；仅给 discover 增加可选 keyword `override=None`、`resolve_source=True`。正常路径传 validated override 和 `resolve_source=not resume_after_merge`；原三位置参数调用仍有效。这样高优先级 override 可直接取代低优先级发现，不会因未使用的 .gitmodules branch 或 upstream 默认解析失败而误拒绝。

1. `validate_override` 先维持已有文件/schema 失败回落规则，再以键是否存在（不是 truthy）检查 branch/upstream_branch。可解析但显式 null/空/非字符串/非法 ref 应抛带字段名的 `ValueError`；`load_optin_override` 的既有 YAML 加载捕获不能吞掉这个分支错误。只对这两个字段窄化，不改其他字段/schema_version 兼容性。
2. validated dict 保留两个键及其规范化值；字典 membership 就是“显式配置”证据，不新增配置 schema 或持久化 provenance。discover 的目标选择先看 `branch in override`；来源先看 upstream_branch，再看显式 legacy branch，最后独立探测。自动算出的 cfg.branch 不能充当显式 legacy branch。
3. `merge_override` 保留现有非分支字段逻辑；有 upstream_branch 时单独覆盖来源；否则仅在 override 显式有 branch 时，将其规范化裸名也赋给 upstream_branch。`_replace_config` 增加该字段，防止后续 cfg.path 绝对化或其他 replace 丢失来源。config_source 原值域不变；选择时 log 标明 target/source 及 opt-in、legacy、.gitmodules、current、cached HEAD、remote HEAD 或 cached candidate。
4. 正常来源 unresolved 为 cfg.upstream_branch=None，交 phase_fetch fail；resume 不发现/不校验来源缓存，但仍校验显式两个字段及目标。state 初始化 behind/ahead=None、upstream_ref=""，代表未比较；已有直接构造已知整数的测试仍可使用。
5. process 只捕获本分支解析/目标校验产生的 ValueError，形成现有 PhaseResult/PipelineResult 的 fail（含字段/target/current/原因），不让单项错误崩溃全 CLI；其他 submodule 继续，fail-fast 按已有整体结果工作。不是通用异常框架。

#### 3.9.3 发现优先级与规范化

- 目标：有效显式 branch > `.gitmodules` 对应 section branch > 子仓 `git symbolic-ref --quiet --short HEAD` > cached origin HEAD > main 候选。给 `_discover_branch` 增加必要的 name/project_root keyword 上下文；通过 `git config --file <root>/.gitmodules --get submodule.<section-name>.branch` 只读获取配置（argv 单项保留完整 section）。exit 1 且无值才是缺失；显式空值、其他错误失败。`.` 仅在 .gitmodules 入口用主仓 symbolic HEAD 展开，主仓 detached 即 fail；不扫描 basename，不改 .gitmodules。已选目标校验失败不降级。
- 来源：显式 upstream_branch > 显式 branch 的 legacy 裸名 > cached upstream HEAD > 只读 remote HEAD > 已有 upstream/main、upstream/develop、upstream/master commit。复用 `_detect_upstream_default_branch`；保留 `remote show upstream` 时给该命令局部 `LC_ALL=C` 环境以稳定现有解析（不写配置），失败/unknown 有诊断，再探测缓存。cached HEAD 已得合法名称但 commit 不在本地时仍选它，不改选候选；没有任何合法来源则 unresolved，不从目标/origin fallback。
- `normalize_remote_branch(ref, remote=...)` 只剥一个匹配 `refs/remotes/<remote>/`、`<remote>/` 或 `refs/heads/` 前缀。外层 strip 后保留 feature/x 全层级；裸名、同角色表示等价。剥离后仍有保留 origin/upstream 或 refs 命名空间、错误 remote、refs/tags、HEAD、`(unknown)`、空 suffix、以 `-` 开头、完整 SHA object id 或非法 ref 表达式均拒绝，不递归剥前缀或修复内部字符。用只读 `git check-ref-format refs/heads/<name>` 校验，另显式拒绝上述不允许项；不通过 `--branch` 展开历史 checkout 表达式。
- normalize 对自动探测的非名称返回 None/诊断，继续允许的来源候选；显式配置的 normalize None 升为字段错误。源/目标角色不能互借前缀；旧 `branch: origin/main` 先按目标得到 main，再提供 legacy 同名来源。schema_version 仍 1。

#### 3.9.4 目标安全与 skip/resume

新增一个小型只读 helper（建议 `_validate_target_branch`，返回错误或抛 ValueError），复用 run_cmd 检查 `refs/heads/<branch>` 可解析为 commit，且 `symbolic-ref --quiet --short HEAD` 成功并精确等于 branch。process 在任何 fetch/hook/install/restart/push 写操作前调用，错误直接 fail/exit 1；dirty 的既有 apply 检查仍保留，force-dirty 不能绕过目标检查。所有模式均不 checkout/switch/reset/创建分支。

phase_merge 在执行 hooks 后、调用 git merge 前再次调用该 helper；失败走现有 merge fail→aborted 路径。process 在真正/计划 push 前复核，失败记录 push fail 且令 aborted=True，以保证本次目标安全错误 overall fail；正常 push 执行失败的历史汇总路径不改。hook/外部已改变状态不自动恢复，报告即停手。

`--skip-merge` 仍进入 fetch/比较，来源未知不得运行后续；`--resume-after-merge` 跳过来源发现/比较和 fetch/merge（detail 明确未比较，不写 behind=0/latest），保留目标检查后按原流程 install/restart/可选目标 push。跳过 install/restart 或 skip_push 均不改变双分支选择。无新 checkpoint、锁或激活阶段。

#### 3.9.5 fetch、比较与 merge 的精确绑定

apply 的内部 argv 使用单一明确来源 heads ref，避免远端同名 tag 或自定义 tracking refspec 使来源含混：

```text
git fetch upstream refs/heads/<upstream_branch>
git rev-parse --verify FETCH_HEAD^{commit}
git rev-list --left-right --count <本轮来源commit-SHA>...HEAD
ahead==0: git merge --ff-only <同一来源commit-SHA>
ahead>0:  git merge --no-ff <同一来源commit-SHA>
git push origin <branch>
```

fetch exit 非零立即 fail，不读取旧 FETCH_HEAD。成功后立即解析 FETCH_HEAD commit，将 SHA 存到现有 state.upstream_ref；比较/merge 均用该 SHA，后续 hooks 不会通过改 tracking ref 或 FETCH_HEAD 偷换来源。源名称仍在日志/detail 中显示；没有必要强制重写 upstream tracking ref、创建临时 refs 或修改 remote.fetch。保留现有 ahead>0 的 --no-ff、冲突收集/abort 行为。

`_parse_rev_count` 只接受恰好两个非负十进制整数；空/负/多 token/非法值抛 ValueError。phase_fetch 必须同时检查 rev-parse/rev-list exit code，错误清空/保留 None，不把失败输出喂作可信数值；只有来源 commit 和计数都成功才设置 state.behind/ahead，返回 pass。phase_merge 对 None 也拒绝，known behind=0 才 skip。

dry-run 不执行以上 fetch。只解析 `refs/remotes/upstream/<upstream_branch>^{commit}`，比较其 SHA 与 HEAD；detail 显示 source/target、cached/not fetched、behind/ahead 和正确 fetch/merge/push 计划。cached behind=0 的 skip 文案必须说明只是缓存比较，不能声称远端最新；修正现有 `git --ff-only ...` 错误 dry-run 文案为完整 `git merge --ff-only ...`。有名称无缓存/计数失败/unresolved：fetch fail、detail `unknown/无法判定`，overall fail、CLI exit 1，后续不生成通过计划、不执行写操作。沿用已有 aborted 控制流即可，不新增“unknown”枚举或结果框架。

#### 3.9.6 隔离 Git fixture 与直接回归

新增测试集中在 `tests/scripts/test_update_submodules_branch_mapping.py`，沿现有 importlib 动态加载方式，不在旧文件叠加大测试框架。测试分两组：参数化解析/优先级/错误分支单测，及真正调用升级器 process/CLI 的本地 bare E2E。只有 systemd 探测、安装/重启和刻意的命令失败用替身；核心 fetch/merge/push 不 mock。

fixture 位于 `$TMPDIR` 下 pytest basetemp：upstream.git（bare）、origin.git（bare）、seed（普通工作仓）、project（main 主仓）及 project/child（main 子仓）。seed 建共同祖先 C0，分别推 upstream/<source> 与 origin/main，设 bare HEAD，child 从 origin 克隆并配置本地 upstream；主仓 .gitmodules 写 section/path/branch=main。child 不放 yaml。seed 在 source 增加唯一新文件提交 C1，推至本地 upstream。测试在调用升级器前断言所有 remote 的解析路径都位于 fixture 根，单命令限制本地 file 协议、使用隔离 HOME/空全局及系统 Git 配置、测试身份环境变量、无交互和命令超时；不改全局 Git 配置或生产仓。安装/重启始终 skip/替身，不能执行真实 pip/service/机器人。

- 参数化 source=main/master/develop，目标 main：调用 process（apply=True 对应 dry_run=False，do_push=True，skip_install/skip_restart=True），再读回 child 符号 HEAD、HEAD commit、目标 bare refs。必须 main 前进到 C1，origin/main=C1，origin/master 或 origin/develop 不创建；本地也不创建来源同名分支。比较内容中的 C1 文件，不只验 overall 或命令字符串。
- stale ref 变体：C0 tracking 缓存保留，remote.fetch 只覆盖其他分支（配置仅 fixture 内）；fetch source 后断言 merge 的是 C1 而不是 upstream/<source> 的 C0，证明 FETCH_HEAD SHA 绑定有效。
- reject 变体：目标错分支/缺失/detached，含 force-dirty、skip/resume；进入升级器前后 Git 状态完整快照相等，fetch/hook/install/restart/push 均无调用。来源不存在则 fetch fail、HEAD/origin refs 不变；不承诺失败 fetch 的 FETCH_HEAD/对象缓存零变化。
- unknown/dry-run 变体：有来源名称无 commit 缓存、rev-list 非零/非法计数；以及可信缓存正常计划。dry-run --push --no-audit 前后快照相等，不允许偷偷 fetch 来“修好”缓存。允许的只读远端查询失败须可见。
- hook 切换 fixture 分支：merge 前或 push 前拒绝；错误 merge/push 不执行，不要求撤销 hook 自己的切换。resume 无来源缓存可继续目标 push，另断言 fetch/merge 未调用且未输出 latest/0 比较结论。

零写快照至少覆盖 HEAD 符号值/commit、全部 refs、index bytes、Git config bytes、FETCH_HEAD 有无及 bytes、tracked/untracked 工作树内容和 bare 远端 refs；status 单独不足。hook 测试把 hook 自身变化与升级器拒绝后的无进一步写入分开断言。不引入通用快照工具模块，只在新测试文件实现所需 fixture helper。

旧测试只按以下必要点兼容：`TestUpstreamDefaultBranch.test_discover_branch_priority` 改为目标优先级且来源独立断言；`TestProcessSubmodule.test_process_pass_with_upstream` / `TestAuditLog.test_audit_log_generated` 当前无真实 upstream 缓存、却期待 PASS，应补本地可比较 fixture 或改为 unknown/fail 并保留成功路径；涉及直接 state/新校验的测试补正确目标/来源。`_make_project` 的 GitHub 字符串只作旧 URL 解析测试输入；凡会联网的发现调用在测试中替身或改用本地 bare，绝不能真 fetch/push 这些 URL。所有 install_exclude/Fix-2/诊断/默认 CLI/dirty/冲突/only/fail-fast 覆盖保留。

#### 3.9.7 G3 受控增长与不拆分理由

实际脚本 1722 行、旧测试 1917 行，均为 1201–2400 受控区。脚本职责仍是单一升级 CLI 的发现/覆盖/五阶段；增长仅来自双分支选择、必要只读校验与错误计数处理，不新增其他功能。旧测试职责是原升级器与安装/诊断回归，增长仅来自既有 fixture/断言兼容；新分支覆盖另置新文件并少于 1200 行。本流水线已有独立 Review，不额外派卡。

实现后必须记录实际行数：预计不越过 2400；若会进入 2401–3599，须先退回 Principal 定义拆分模块/顺序/验证，不无设计继续叠加；达到 3600 则禁止扩张或取得 Pascal 针对具体文件豁免。即使未跨档，未来实质性扩展引入独立职责/无法局部测试时亦为重新评估拆分的触发点，不借本轮做无关模块拆分。

## 4. 本次实现顺序

1. 在 §3.1 的新测试文件先表达分支映射/unknown/目标拒绝直接回归，使用本地 bare；只调整必要旧断言。
2. 增加 upstream_branch 字段并贯穿 validate/load/discover/merge/_replace_config，收紧 normalize，分离来源与目标发现。
3. 在现有 process/merge 中接入目标校验与 skip/resume 短路；phase_fetch 绑定本轮来源 SHA、严格计数、诚实 dry-run；不触碰 install/restart。
4. 执行 §5.1 全部定向/旧回归/只读 OctoBot 命令及快照，交真实结果给独立 Verify/Review。功能测试全 PASS 不是本卡已执行事实。

## 5. 验证策略

### 5.1 本次 Implement / Verify 命令与 expected

以下是待实现后运行的命令，不是本卡已通过的测试。使用各执行 profile 已提供的 TMPDIR，不安装依赖；所有 pytest 临时 Git/编译缓存均写该目录。新文件中的真实 Git E2E 测试名约定含 `local_bare`，避免定向命令零选中误通过。

```bash
cd /home/pascal/workspace/yquant-investment
: "${TMPDIR:?current profile scratch required}"
TEST_ROOT="$(mktemp -d "$TMPDIR/submodule-branch-mapping.XXXXXX")"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$TEST_ROOT/pycache" GIT_OPTIONAL_LOCKS=0
python3 -m py_compile scripts/upgrade/update_submodules.py
python3 -m pytest -p no:cacheprovider tests/scripts/test_update_submodules_branch_mapping.py -v --basetemp="$TEST_ROOT/targeted"
python3 -m pytest -p no:cacheprovider tests/scripts/test_update_submodules_branch_mapping.py -k local_bare -v --basetemp="$TEST_ROOT/local-bare"
python3 -m pytest -p no:cacheprovider tests/scripts/test_update_submodules.py tests/scripts/test_auto_push_submodule_order.py -v --basetemp="$TEST_ROOT/legacy"
python3 scripts/upgrade/update_submodules.py --help
python3 scripts/upgrade/update_submodules.py --dry-run --only OctoBot --skip-install --skip-restart --no-audit
python3 scripts/upgrade/update_submodules.py --dry-run --only OctoBot --skip-install --skip-restart --no-audit --push
git diff --check
```

pytest/编译/help/diff 期望 exit 0；local_bare 至少包含三种 source 参数化及 stale tracking 实例，不得只有 mock。独立 Verify 需重跑并报告实际 collected/passed/failed/skipped，不沿用主控旧 92 passed 作为本轮证据。新旧完整命令共同覆盖 A-BM-020，不跑全项目的无关/生产集成测试。

真实 OctoBot 仅两条 dry-run，预期显示 source=master、target=main、cached/not fetched，push 计划仅 origin main；有缓存与合法计数则 exit 0（只代表计划），若现场缓存缺失则必须 unknown/exit 1 并记录原因，不能为得到 PASS 而 fetch。运行前后按 §3.9.6 快照核对子仓/主仓 gitlink，确认 yaml 原本不存在且仍未新增、Git 状态不变。需要详细计划可加既有 --verbose，不改 CLI；不得执行真实 --apply/fetch/merge/checkout/reset/push/install/restart，也不执行历史全仓默认审计命令。

### 5.2 历史 V2.0 数据抽样（保留背景，本次由 §3.9.6 与 §8.1 取代）

本节不是重新探测/操作 DSA 或 TradingAgents-CN 的要求；本轮只跑上述允许的旧测试及 OctoBot 只读命令，不按历史机器环境强制增加验证任务。

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
| 来源/目标推断失败或 HEAD 不符 | 按 §3.9 fail/unknown，不借目标 fallback 来源、不自动切换 | 人工检查后另行授权，不修改子仓配置来掩盖缺陷 |
| `.update_submodules.yaml` 格式错误 | warning 回落启发式 | 人工修正 YAML |
| YAML fallback 不完整 | 只支持 override schema 子集 | skip，warning |
| 触碰真实 submodule 内部文件 | T2/T3 只跑 dry-run/mock/temp repo | 停止退回 Principal |
| **upstream 缺失被误判**（实际存在但 get-url 失败） | 错误信息含当前 remotes 列表，便于诊断 | 人工检查 git remote |
| **health_check 默认 None 导致异常未发现** | Pascal 按需 opt-in 配置 | Closeout 记录残余风险 |

本次回滚仅涉及未来获准提交的脚本/测试代码提交：由主控在确认后回退该提交，重新执行旧/新回归；不要求改变服务、venv、数据库、子仓配置、gitlink 或任何远端分支。本卡不 commit，T3 的本地提交以其卡片明确许可为准；两阶段均不自行 revert/reset/stash/clean。上表历史运行期处置不是本次执行许可。此前已有的普通 push 失败 overall 汇总缺陷仍为残余，实际验收必须读回 fixture origin refs，不能仅凭 overall PASS 宣称分支同步成功。

## 7. 交接给实现者

### 7.1 本次必须遵守

- 严格按 §3.1 的阶段 allowlist；复用当前脚本/helper，不复制重做、不引入 common.py/框架/中央 manifest/CLI/依赖/服务操作。
- 按 §3.9 的来源/目标/legacy/目标校验/本轮来源 commit 绑定实施，原 install_exclude/Fix-2/诊断与五阶段不回退；默认 dry-run/不 push/禁 force 保留。
- 只在本地隔离 fixture apply/fetch/merge/push；真实 OctoBot 仅 §5.1 dry-run，不能修改任何子仓 yaml 或 refs。共享 main 不清理/提交他人无关差异，T3 本地提交范围以其卡片明确授权为准。
- handoff 列实际修改文件、测试命令/计数/结果、行数、未验证项与残余；自测不是独立 Verify，不宣称全链兼容已经验收或已发布。
- 本卡完成后交主控核对三层文档再放行已有 Implement；不额外派卡，不用后续未授权生产动作阻塞已完成设计。

### 7.2 可自行判断

仅限必要内部 helper 命名/位置、错误文案与新测试文件内 fixture helper 布置。resume 语义、发现顺序、allowlist、来源绑定及非分支行为已冻结，不授权加 checkpoint、改 systemd 算法或抽公共模块。

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

### 8.1 本次 A-BM-001–020 的实现/测试映射

以下是待运行验收映射，不是 PASS 报告。除真实 OctoBot 只读抽样和旧覆盖外，均置于新分支测试文件；不扩展到无关用例或增加阶段。

| SPEC 编号 | Design 落点与必要断言 | 验证 |
|---|---|---|
| A-BM-001 | §3.9.3/§3.9.5 同名 main，来源与目标 main | local_bare 参数化 E2E |
| A-BM-002 | §3.9.6 master→main，C1 到本地 main 和 origin/main，不创建 master | local_bare 参数化 E2E，读回 refs/HEAD/内容 |
| A-BM-003 | §3.9.6 develop→main，origin/develop 不创建 | local_bare 参数化 E2E |
| A-BM-004 | §3.9.2 显式旧 branch: develop，覆盖上游默认 master，两端仍 develop | opt-in 加载/合并/来源选择单测 |
| A-BM-005 | branch: origin/main + upstream_branch: upstream/master，cfg 最终 main/master，replace 不丢字段 | YAML 两解析路径及字段透传单测 |
| A-BM-006 | 仅 upstream_branch: develop，目标按 .gitmodules main | 加载/发现/覆盖单测，schema 仍 1 |
| A-BM-007 | §5.1 真实 OctoBot 无新 yaml，master→main，只有正确 push 计划 | 真实只读 dry-run 两命令及前后快照 |
| A-BM-008 | §3.9.3 目标 override > .gitmodules > current > origin > main，已选不降级 | 优先级参数化，失败无写 |
| A-BM-009 | 无 .gitmodules branch 则 topic current 优先 origin/main；detached 不能借 origin 通过 | 目标发现/拒绝单测与快照 |
| A-BM-010 | .gitmodules branch=. 展开主仓 main，主仓 detached/读取失败则拒绝 | 本地主仓 fixture |
| A-BM-011 | cached upstream HEAD > remote HEAD > main/develop/master commit 缓存，失败诊断、不借目标兜底 | 探测序列/诊断单测，缓存名称无 commit 不改选 |
| A-BM-012 | §3.9.3 裸名/匹配前缀/refs/heads 规范化、feature/x 完整、legacy 裸名 | 参数化 normalize 与命令断言 |
| A-BM-013 | 显式 null/空/非字符串/非法/错误 remote 字段失败，不吞为 warning 回落 | validate/load/process 失败单测 |
| A-BM-014 | §3.9.5 dry-run 缺缓存及 rev-list 非零/空/负/额外 token 为 unknown/fail/exit 1 | 参数化计数与 CLI 测试、无后续写 |
| A-BM-015 | apply 来源不存在/fetch 后解析或计数失败，中止后续；不另选来源 | 本地 bare 缺来源与命令失败替身 |
| A-BM-016 | §3.9.4 dry-run/apply 错误目标/缺目标/detached/force-dirty，零写拒绝 | 本地 fixture 完整快照及命令记录 |
| A-BM-017 | skip-merge 仍检查来源，resume 不查询来源缓存且 push 目标；错误目标不能跳过 | skip/resume 参数化与调用断言 |
| A-BM-018 | 缓存可比较 dry-run --push --no-audit，只读且明确未 fetch | 完整快照、禁写命令记录与计划断言 |
| A-BM-019 | §3.9.5 FETCH_HEAD SHA 合入 C1 而非旧缓存；hook 切分支后禁止 merge/push | local_bare stale ref 变体与 hook fixture |
| A-BM-020 | 非分支原能力不回退，错误单 branch/无 ref PASS 的旧测试最小调整 | §5.1 新旧回归，auto_push 只读测试，diff 审查 |

设计完成条件：本表覆盖 SPEC 的 20 项、两份 Design 差异在 allowlist、相对引用/Markdown/`git diff --check` 通过，RFC/SPEC/代码/测试/.gitmodules/gitlink/真实子仓未变。本卡仅报告上述文档自检；功能验收必须由后继 Implement 自测、独立 Verify 和 Review 各自执行。
