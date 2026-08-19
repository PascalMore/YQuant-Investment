# DESIGN-10-006：Hermes Agent 自动升级脚本 V2 — Git 传输韧性增强

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-08-20 |
| 版本号 | **V2.2** |
| 来源 RFC | RFC-10-006-hermes-upgrade-script-v2 |
| 来源 SPEC | SPEC-10-006-hermes-upgrade-script-v2 |
| 继承 Design | DESIGN-10-005-hermes-auto-upgrade, DESIGN-10-006 V2.0, V2.1 |
| 目标脚本 | `scripts/upgrade/upgrade_hermes_agent.py` |
| 流水线 | T1=t_8228a098, T2=t_ec0d709a, T3=t_cf586d51, T4=待创建, T5=待创建, T6=待创建 |

## 1. 版本历史

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V2.0 | 2026-07-08 | 基础 V2 设计：feature-branch、patch-manifest、branch override | YQuant-Codex-Principal |
| V2.1 | 2026-07-30 | 增补 Git 传输韧性增强：target-aware fetch、classified retry、HTTP/1.1 fallback、manifest fetch_attempts audit、branch-aware protect push、dry-run 零网络 | YQuant-Codex-Principal |
| V2.2 | 2026-08-20 | Dry-run 输出正确性增量（`print_dry_run()` 三分支 merge_mode + behind-upstream 真实差距显示），对抗 `hermes --version` 在 fork 上失明的 P-5 陷阱 | YQuant-Principal |

## 2. 设计摘要

V2.1 在 V2.0 的安全升级主线之上做增量增强，不重写现有状态机。目标是让 Hermes 自动升级脚本在有代理/WSL 网络不稳定环境下仍能弹性完成 fetch。

V2.2 是 V2.1 之后的 dry-run 输出正确性增量，**只动 `print_dry_run()` 函数内部**，不动 fetch/merge/install/restart/push 任何状态机。

**核心设计理念**：
1. **只动 fetch**：所有修改集中在 3 个函数 `fetch_remotes()` / `protect_local_commits()` / `print_dry_run()` 及 2 个新增函数 `classify_git_transport_failure()` / `run_fetch_with_transport_policy()`。
2. **命令级隔离**：所有 HTTP/1.1 fallback 通过 `git -c http.version=HTTP/1.1` 实现，不写任何 git config。
3. **有限脆弱**：最多 3 次 attempt，非瞬态错误立即 fail-stop，不掩盖真正问题。
4. **可审计**：每次 attempt 的结构化元数据写入 manifest，不存原始 stderr 或 secret。
5. **V2.2 新增：dry-run 显示与真实逻辑对齐**：merge_mode 三分支分类必须与 `classify_git_relation()` 输出一致；behind upstream/main 显示作为 `--version` 失明时的 truth source。

### 2.1 精确文件矩阵（T3 Implement 允许的修改范围）

| 文件 | 操作 | 说明 |
|---|---|---|
| `scripts/upgrade/upgrade_hermes_agent.py` | 修改 | 3 个现有函数替换 + 2 个新增函数 + 2 个新常量 |
| `tests/scripts/test_upgrade_hermes_agent.py` | 不改（全量回归） | V1.0 测试必须不因 signature 变化而失败 |
| `tests/scripts/test_upgrade_hermes_agent_v2.py` | 修改 | 新增 V2.1 测试用例（见 §9） |
| `docs/rfc/10_infra/RFC-10-006-hermes-upgrade-script-v2.md` | 不改（已由 T1 完成） | — |
| `docs/spec/10_infra/SPEC-10-006-hermes-upgrade-script-v2.md` | 不改（已由 T1 完成） | — |
| `docs/design/10_infra/DESIGN-10-006-hermes-upgrade-script-v2.md` | 修改 | 本文件 |

**不可碰**的 P0 Unified Data dirty files（当前 `git status` 中的 dirty 文件，非本任务范围）。

### 2.2 V2.1 不修改 V2.0 内容

- `UpgradeConfig` 不新增字段（复用现有字段工作，无新 CLI 参数）
- `build_parser()` 不新增参数
- `config_from_args()` 不新增映射
- `upgrade()` 主流程状态机结构不变
- `data/hermes_patches.yaml` schema 不变
- `inspect_repo()` 的 branch 检查逻辑不变

## 3. 现状代码锚点与改动概览

### 3.1 修改函数清单

| 位置 | 函数 | 当前 V2.0 行为 | V2.1 改为 |
|---|---|---|---|
| :1129 | `fetch_remotes()` | 硬编码 `--tags`，失败直接 exit 1 | 改为调用 `run_fetch_with_transport_policy()`，target-aware + retry |
| :1231 | `protect_local_commits()` | 硬编码 `push origin main` | 改为 `push -u origin <state.branch>`，加 reachability 先检 |
| :1544 | `print_dry_run()` | 展示 fetch 步骤含 `--tags` | 增加 target-aware fetch plan、retry plan、HTTP/1.1 fallback 说明、\"不发网络\"声明 |

### 3.2 新增常量

| 名称 | 值 | 类型 | 引入位置 |
|---|---|---|---|
| `FETCH_MAX_ATTEMPTS` | `3` | `int` | 脚本文件顶层面板常量区（约 :40-70） |
| `FETCH_RETRY_DELAYS` | `[2, 5]` | `list[int]` | 同上 |
| `FETCH_TIMEOUT` | `300` | `int` | 继承 V1.0，不新增（已有 `timeout=300` 用法） |

### 3.3 新增函数

| 函数 | 签名 | 设计章节 |
|---|---|---|
| `classify_git_transport_failure(stderr, stdout="")` | `-> str` | §4 |
| `build_fetch_command(remote, target, *, fetch_all_tags=False)` | `-> tuple[list[str], str]` | §5 |
| `run_fetch_with_transport_policy(remote, target, *, repo, manifest, verbose=False, timeout=300, sleep_fn=time.sleep)` | `-> CommandResult` | §6 |

## 4. classify_git_transport_failure — 纯函数错误分类器

### 4.1 函数签名

```python
def classify_git_transport_failure(stderr: str, stdout: str = "") -> str:
    """Return 'transient' | 'permanent' | 'non_transport'.

    Pure function: no I/O, no side effects. Input is git subprocess stderr.
    """
```

### 4.2 分类表（优先级由上至下，`re.search` + `re.IGNORECASE`）

| 优先级 | 模式 | 分类 |
|---|---|---|
| 1 | `repository not found` 或 `could not find` + `repo` | `permanent` |
| 2 | `authentication failed` | `permanent` |
| 3 | `access denied` 或 `permission denied` | `permanent` |
| 4 | `host key verification failed` | `permanent` |
| 5 | `certificate verification failed` | `permanent` |
| 6 | `couldn't find remote ref` | `permanent` |
| 7 | `gnutls recv error` | `transient` |
| 8 | `ssl_error_syscall` | `transient` |
| 9 | `tls connection was non-properly terminated` | `transient` |
| 10 | `rpc failed` | `transient` |
| 11 | `early eof` | `transient` |
| 12 | `invalid index-pack output` | `transient` |
| 13 | `the remote end hung up unexpectedly` | `transient` |
| 14 | `unexpected disconnect` + `sideband packet` | `transient` |
| 15 | `connection reset by peer` | `transient` |
| 16 | `connection refused` | `transient` |
| 17 | `could not resolve host` | `transient` |
| 18 | `transfer closed` + `expected` | `transient` |
| 19 | 其他非空 stderr | `non_transport` |
| 20 | 空 stderr | `non_transport` |

### 4.3 实现约束

1. **permanent 优先**：模式 1-6 在 transient 模式 7-18 之前匹配，避免 stderr 同时含 auth 和 TLS 错误时误判为 transient。
2. **单一预编译 Pattern**：用 `re.compile(patterns, re.IGNORECASE)` 以枚举方式循环匹配，不引入外部依赖。
3. **边界可证伪性**：
   - 输入 `""` → `"non_transport"`
   - 输入随机不匹配字符串如 `"merge conflict in file.txt"` → `"non_transport"`
   - 输入 `"fatal: authentication failed\nGnuTLS recv error (-110)"` → `"permanent"`（永久优先）
4. **测试覆盖率**：每条模式至少 1 条单元测试（见 §9 UT-001~004）。

## 5. build_fetch_command — Target-aware fetch 命令构造器

### 5.1 函数签名

```python
def build_fetch_command(remote: str, target: str, *,
                        fetch_all_tags: bool = False) -> tuple[list[str], str]:
    """Return (cmd_args, transport_label).

    transport_label is 'default' or (with -c overlay) 'http/1.1-fallback'.
    This function does NOT include the -c http.version=HTTP/1.1 prefix;
    that is applied at the call site for attempt 3 only.
    """
```

### 5.2 构造规则

| target 特征 | 返回命令 | transport_label |
|---|---|---|
| 非 tag（纯 branch name / ref，如 `main`, `fix/foo`） | `["fetch", "--no-tags", remote, target]` | `"default"` |
| 含数字版本号模式如 `v2026.7.1`（启发式：`target.startswith(("v","V")) and any(ch.isdigit() for ch in target)`） | `["fetch", remote, f"refs/tags/{target}:refs/tags/{target}"]` | `"default"` |
| `fetch_all_tags=True`（仅用作 future escape hatch，当前 static False） | `["fetch", "--tags", remote, target]` | `"default"` |

### 5.3 设计理由

- `--no-tags` 阻止 Git 隐式跟随 tag 链。纯 branch 升级场景不需要 tag 数据，减少 packfile 体积可降低代理下触发传输错误的概率。
- Tag target 使用精确 refspec `refs/tags/<tag>:refs/tags/<tag>`，只拉取特定 tag。
- 启发式判定 tag：`v`/`V` 开头 + 数字字符。该判定允许未来对 tag 目标（如 `v2026.7.1`）使用精确 refspec。注意：无效 tag 会在 attempt 1 后由 `classify_git_transport_failure` 捕获（`couldn't find remote ref` → `permanent`），不会无限重试。
- 函数返回裸命令参数。attempt 3 的 `-c http.version=HTTP/1.1` 前缀由 `run_fetch_with_transport_policy` 在调用 `git()` 前注入（§6.4）。

## 6. run_fetch_with_transport_policy — 三次attempt 状态机

### 6.1 函数签名

```python
def run_fetch_with_transport_policy(
    remote: str,
    target: str,
    *,
    repo: Path,
    manifest: dict,
    verbose: bool = False,
    timeout: int = 300,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> CommandResult:
    """Execute fetch with target-aware command, classified retry, and audit.

    Returns the first CommandResult with exit_code=0.
    On final failure, raises UpgradeError with next_steps.
    """
```

### 6.2 三次 attempt 状态机

```
                      ┌──────────────────────┐
                      │   Attempt 1 (normal)  │
                      │  build_fetch_command  │
                      │  git(...) with base   │
                      └──────────┬───────────┘
                                 │ exit_code
                        ┌───────┴───────┐
                    0   │               │  !=0
                 ┌──────▼───┐           │
                 │  return   │   classify(stderr)
                 │  success  │           │
                 └──────────┘    ┌──────┴──────┐
                                 │              │
                        ┌────────▼──┐   ┌──────▼──────┐
                        │ transient │   │ permanent / │
                        │           │   │ non_transport│
                        └─────┬─────┘   └──────┬──────┘
                              │                 │
                     sleep(2) │           ┌─────▼────┐
                     ┌────────▼──────┐    │ UpgradeError
                     │ Attempt 2     │    │ fail-stop  │
                     │ (backoff)     │    └────────────┘
                     │ base command  │
                     └────────┬──────┘
                              │ exit_code
                        ┌─────┴──────┐
                    0   │            │ !=0
                 ┌──────▼───┐        │
                 │  return   │ classify(stderr)
                 │  success  │        │
                 └──────────┘   ┌─────┴─────┐
                                │           │
                        ┌──────▼──┐   ┌─────▼──────┐
                        │ transient│   │ permanent /│
                        └────┬─────┘   │ non_trans  │
                              │         └─────┬──────┘
                     sleep(5) │               │
                     ┌────────▼──────────┐    │
                     │ Attempt 3 (H/1.1) │    │
                     │ -c http.version=  │    │
                     │   HTTP/1.1        │    │
                     │ + base command    │    │
                     └────────┬──────────┘    │
                              │ exit_code     │
                        ┌─────┴──────┐        │
                    0   │            │ !=0    │
                 ┌──────▼───┐   ┌────▼────┐  │
                 │  return   │   │Upgrade  │  │
                 │  success  │   │Error    │  │
                 └──────────┘   │ exhausted│  │
                                └─────────┘  │
                              ┌──────────────┘
                              ▼
                      fail-stop (previously
                      classified permanent
                      or non_transport)
```

**关键行为**：
- 任何 attempt exit=0 → 立即返回，不继续后续 attempt
- Attempt 1 → 2 之间 sleep `FETCH_RETRY_DELAYS[0]` = 2 秒
- Attempt 2 → 3 之间 sleep `FETCH_RETRY_DELAYS[1]` = 5 秒
- Attempt 3 注入 `-c http.version=HTTP/1.1` 命令前缀
- dry-run 模式（`manifest` 内无 `config` 引用；实际上在 `fetch_remotes()` 入口检查 `config.dry_run`，跳过整个函数）

### 6.3 命令构造（attempt 3 的 -c 注入）

```python
def _build_attempt_command(base_args: list[str], attempt: int, verbose: bool) -> list[str]:
    """Wrap base_args with -c http.version=HTTP/1.1 for attempt 3."""
    if attempt >= 3:
        return ["-c", "http.version=HTTP/1.1"] + base_args
    return base_args
```

**实现注意**：`git()` 函数现有签名 `git(args: list[str], ...)`。attempt 3 需传递 `["-c", "http.version=HTTP/1.1", "fetch", "--no-tags", "upstream", "main"]` 作为 `args`。检查 `git()` 实现是否兼容 `-c` 参数在最前面；`git -c key=val <cmd>` 语法支持 `-c` 在任何位置（包括命令前），这是标准 git 语义。

### 6.4 git() 调用时的 -c 前缀处理

`git()` 函数（现有，约 :200-230）通过 `subprocess.run` 调用：

```python
def git(args: list[str], *, repo, manifest, verbose, timeout=300, check=False) -> CommandResult:
    cmd = ["git"] + args  # 直接拼接
```

`git -c http.version=HTTP/1.1 fetch ...` → `cmd = ["git", "-c", "http.version=HTTP/1.1", "fetch", ...]` → 直接 w/ `subprocess.run` 无需修改 `git()` 函数本身。`-c` 参数是 git 标准语义，出现在 `args` 中的第一个位置是完全合法的。

### 6.5 失败后的 UpgradeError 构造

```python
def _raise_fetch_exhausted(remote, target, manifest_path, backup_zip):
    raise UpgradeError(
        "fetch",
        f"fetch 已达上限 {FETCH_MAX_ATTEMPTS} 次 (remote={remote}, target={target})",
        next_steps=[
            f"所有 attempt 已记录到 manifest {manifest_path}",
            f"手动重试: git fetch --no-tags {remote} {target}",
            f"若确认是代理/TLS 问题: git -c http.version=HTTP/1.1 fetch --no-tags {remote} {target}",
            f"备份路径: {backup_zip}",
        ],
    )
```

## 7. protect_local_commits — 分支感知保护 push

### 7.1 V2.1 重写版

```python
def protect_local_commits(config: UpgradeConfig, state: RepoState,
                          plan: GitPlan, manifest: dict) -> None:
    """S5 protect: 根据 state.branch 而非 main 做 reachability 检查和 push。"""
    if not plan.local_commits_need_protection:
        return

    cmd_log = manifest.setdefault("commands", [])
    head = state.pre_head
    branch = state.branch  # V2.1: 使用 state.branch 而非硬编码 "main"

    # Step 1: 检查 HEAD 是否已在 origin/<branch> 可达
    # 使用 git merge-base --is-ancestor HEAD origin/<branch>
    r = git(["merge-base", "--is-ancestor", head, f"origin/{branch}"],
            repo=config.repo, manifest=cmd_log, verbose=config.verbose)
    if r.exit_code == 0:
        log_info(f"HEAD 已在 origin/{branch} 可达，无需额外保护 push。", config)
        return

    # Step 2: push 当前分支
    log_info(f"本地存在未保护的 commit，执行保护性 push origin {branch}...", config)
    r = git(["push", "-u", "origin", branch], repo=config.repo,
            manifest=cmd_log, verbose=config.verbose, timeout=120)
    if r.exit_code != 0:
        add_manifest_error(manifest, "protect", "push_failed",
                           f"保护性 push origin {branch} 失败: {redact(r.stderr)[:300]}")
        raise UpgradeError("protect",
                           f"保护性 push origin {branch} 失败",
                           next_steps=[
                               f"手动 push: git -C {config.repo} push -u origin {branch}",
                               "检查 SSH/HTTPS 认证与 fork 权限。",
                           ])
    log_ok(f"本地 commit 已保护至 origin/{branch}。")
```

### 7.2 与 V2.0 的关键差异

| 行为 | V2.0 | V2.1 |
|---|---|---|
| push target | `"origin"`, `"main"` | `"origin"`, `state.branch` |
| push 可选 `-u` | 无 | 添加 `-u` 设置 upstream |
| force push | 无 | 无（保持不变） |
| 可达性检查 | 先做 `_is_ancestor(pre_head, pre_head)` = 始终 true 的自检，再做 `origin/main` | 直接 `origin/<branch>` |
| feature branch 保护 | 只 push main，不保护 feature | 保护当前分支 |
| 消息 | "已保护至 origin" | "已保护至 origin/{branch}" |
| 空 branch 处理 | 无 | `state.branch` 为空/None → `_is_ancestor` 正常失败 → push 失败 → 合理 fail-stop |

### 7.3 特殊场景处理

- **detached HEAD**：`state.branch` 为 `None` 或 `""`。`merge-base HEAD origin/None` 会失败（exit != 0），然后 `push -u origin` 也会失败。这是合理的 fail-stop 行为。detached HEAD 应通过 `inspect_repo()` 在上游被阻止，不应到达 S5。
- **`--preserve-features` 交互**：V2.0 的 S0.5 `preserve_feature_branch_if_requested()` 已在 S1 前做了一次 push。S5 的 `protect_local_commits()` 是第二道防线，仅在 `local_commits_need_protection` 为 True 时触发（由 classify 阶段判断）。S0.5 push 成功 → 本函数可达性检查发现 HEAD 已在 `origin/<branch>` → skip push，无重复 push。
- **main 分支**：`state.branch == "main"` → `push -u origin main`，行为与 V2.0 等价（添加 `-u` 是兼容的增强）。

## 8. fetch_remotes V2.1 — 重写调用链

### 8.1 重写后代码

```python
def fetch_remotes(config: UpgradeConfig, manifest: dict, target_ref: str) -> None:
    """S3 fetch: target-aware fetch with transport resilience policy."""
    cmd_log = manifest.setdefault("commands", [])

    if config.dry_run:
        # dry-run: fetch_remotes 不是干活的入口；upgrade() 中 dry-run 走 print_dry_run 快速路径
        # 但作为安全垫，这里也直接返回。
        return

    # Step A: 解析 target_ref 中的 remote prefix
    remote_for_ref = None
    bare_target = target_ref
    if "/" in target_ref:
        candidate_remote = target_ref.split("/", 1)[0]
        r = git(["remote"], repo=config.repo, manifest=cmd_log, verbose=config.verbose)
        remotes = [x.strip() for x in r.stdout.splitlines() if x.strip()]
        if candidate_remote in remotes:
            remote_for_ref = candidate_remote
            bare_target = target_ref.split("/", 1)[1]

    # Step B: fetch origin main (沿用 V1.0 行为，但不重试：origin 是本地 fork)
    r = git(["fetch", "origin", "main"], repo=config.repo, manifest=cmd_log,
            verbose=config.verbose, timeout=300)
    if r.exit_code != 0:
        add_manifest_error(manifest, "fetch", "fetch_origin_failed",
                           f"fetch origin main 失败: {redact(r.stderr)[:300]}")
        raise UpgradeError("fetch", "fetch origin main 失败",
                           next_steps=["检查网络/SSH 认证。"])

    # Step C: fetch upstream target with transport resilience policy
    run_fetch_with_transport_policy(
        "upstream", bare_target,
        repo=config.repo, manifest=manifest,
        verbose=config.verbose,
    )
```

### 8.2 设计决策

1. **origin fetch 不包 retry**：origin 是 Pascal fork，同机或同局域网的 SSH/HTTPS 访问稳定性远高于 GitHub upstream。如果 origin fetch 都失败，升级应立刻 fail-stop。
2. **dry-run 提前返回**：V2.0 的 `upgrade()` 在 S3 前已通过 `print_dry_run()` 输出并 return。本条只是做双保险。
3. **upstream fetch 一律走 retry wrapper**：无论 target 是 main 还是 tag，都通过 `run_fetch_with_transport_policy` 执行。

## 9. print_dry_run V2.1 — Dry-run 输出增强

### 9.1 增量修改

在现有 V2.0 `print_dry_run()` 基础上，修改以下位置：

**Step 4 (fetch) 输出**（原有 :1607）：

```python
# V2.0:
print(f"  4. git fetch origin main + fetch upstream --tags")

# V2.1:
print(f"  4. git fetch origin main (无重试)")
if _is_tag_target(config.version_ref):
    print(f"     git fetch upstream {config.version_ref} (精确 tag refspec)")
else:
    print(f"     git fetch upstream --no-tags {_bare_target(config.version_ref)}")
print(f"     -> 瞬态失败时有限重试 (最多3次, 退避2s+5s, 第3次 HTTP/1.1 fallback)")
print(f"     此 dry-run 不发送网络请求、不 sleep、不修改 git ref")
```

**新增断言末尾**：

```python
print("  声明: dry-run 未发送网络请求、未 sleep、未修改 git ref。")
```

### 9.2 Dry-run 零网络契约

dry-run 模式下 `run_fetch_with_transport_policy()` **不可被调用**。验证方式：
- `fetch_remotes()` 入口检查 `config.dry_run` → return（见 §8.1）
- `protect_local_commits()` 在 `print_dry_run()` 内不执行（dry-run 在 S3 前已返回）
- 任何 subprocess（git fetch / git push）不应在 `--dry-run` 中出现

### 9.3 V2.2 增量：merge_mode 三分支分类 + behind-upstream 显示

**位置**：`scripts/upgrade/upgrade_hermes_agent.py::print_dry_run()` 内，约 1835-1895 行。

**9.3.1 merge_mode 三分支分类修复**

V2.1 仅做了两分支（`head == target` / `head is ancestor of target`），漏了"target 是 head 祖先"。V2.2 补全：

```python
# V2.2 三分支（与 classify_git_relation() 对齐）
if head == target_sha:
    print(f"     => merge_mode: already-up-to-date")
elif _is_ancestor(config.repo, head, target_sha, [], config.verbose):
    print(f"     => merge_mode: ff-only  (git merge --ff-only {target_sha})")
elif _is_ancestor(config.repo, target_sha, head, [], config.verbose):  # V2.2 新增
    print(f"     => merge_mode: already-up-to-date  (HEAD 已含 target)")
else:
    print(f"     => merge_mode: merge    (本地有自有 commit，A+ 策略)")
```

**9.3.2 behind-upstream 显示**

`hermes --version` 在 fork 上对 upstream 失明（P-5 陷阱）。在 dry-run 中显式输出 `HEAD..upstream/main` 的 commit 距离，作为 truth source：

```python
# V2.2: compute HEAD..upstream/main gap (only meaningful when target is upstream/main)
behind_upstream = -1
if config.version_ref == "upstream/main":
    r_behind = git(["rev-list", "--count", "HEAD..upstream/main"],
                   repo=config.repo, verbose=config.verbose)
    if r_behind.exit_code == 0:
        try:
            behind_upstream = int(r_behind.stdout.strip())
        except ValueError:
            behind_upstream = -1

# 紧跟 local-only commits 列表之后打印
if config.version_ref == "upstream/main":
    if behind_upstream == 0:
        print(f"  behind upstream/main: 0  (HEAD 已追平 upstream)")
    elif behind_upstream > 0:
        print(f"  behind upstream/main: {behind_upstream} commit(s)  "
              f"(--version 自报 'Up to date' 不可信；本字段为 truth source)")
    else:
        print(f"  behind upstream/main: (无法读取，本地无 upstream/main 引用)")
```

**约束**：
- 不自动 fetch（dry-run 零网络）。若本地无 `upstream/main` ref，`behind_upstream=-1` 显示 `(无法读取)`。
- 只在 `version_ref=upstream/main` 时计算（tag/branch target 不显示，对比无意义）。
- 不引入 retry / 不引入 git config 写入。

## 10. Manifest fetch_attempts 增量写入

### 10.1 写入位置

`run_fetch_with_transport_policy()` 内，每次 attempt 执行后（success 或 fail）：

```python
def _record_fetch_attempt(manifest, remote, target, attempt_num, transport_label,
                           exit_code, failure_class, retry_delay):
    attempts = manifest.setdefault("fetch_attempts", [])
    entry = {
        "remote": remote,
        "target": target,
        "attempt": attempt_num,
        "transport": transport_label,  # "default" | "http/1.1-fallback"
        "exit_code": exit_code,
    }
    if exit_code != 0:
        entry["failure_class"] = failure_class  # "transient" | "permanent" | "non_transport"
    else:
        entry["failure_class"] = None
    if retry_delay is not None:
        entry["retry_delay_seconds"] = retry_delay
    attempts.append(entry)
```

### 10.2 Schema（7 字段，2 可选）

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---|---|---|
| `remote` | string | 是 | `"upstream"` | git remote 名 |
| `target` | string | 是 | `"main"` | fetch 目标（不含 remote 前缀） |
| `attempt` | int | 是 | `1` | attempt 序号（1-based） |
| `transport` | string | 是 | `"default"` 或 `"http/1.1-fallback"` | 传输层标识 |
| `exit_code` | int | 是 | `0` / `128` | git 命令 exit code |
| `failure_class` | string/null | 否 | `"transient"` | exit != 0 时的分类；exit = 0 时为 `null` |
| `retry_delay_seconds` | int/null | 否 | `2` | sleep 秒数；仅记录前次 attempt 的退避 |

### 10.3 安全规则

- 不记录 `proxy` URL、`http_proxy`/`https_proxy`、git credential、token、access token
- `failure_class` 仅含分类标签，不含原始错误文本
- 原始 stderr 摘要继续通过 `commands[].stderr_tail` 记录（现有 `redact()` 已脱敏）

### 10.4 manifest 示例

```json
{
  "fetch_attempts": [
    {
      "remote": "upstream",
      "target": "main",
      "attempt": 1,
      "transport": "default",
      "exit_code": 128,
      "failure_class": "transient",
      "retry_delay_seconds": null
    },
    {
      "remote": "upstream",
      "target": "main",
      "attempt": 2,
      "transport": "default",
      "exit_code": 0,
      "failure_class": null,
      "retry_delay_seconds": 2
    }
  ]
}
```

## 11. 副效应矩阵

| 活动 | 写网络 | 写磁盘 | 写 Git | 写 git config | 写 proxy env |
|---|---|---|---|---|---|
| fetch attempt 1 (normal) | 是 | 是 | 是(fetch) | 否 | 否 |
| fetch attempt 2 (retry) | 是 | 是 | 是(fetch) | 否 | 否 |
| fetch attempt 3 (HTTP/1.1) | 是 | 是 | 是(fetch) | 否(命令级 -c) | 否 |
| classify_git_transport_failure | 否 | 否 | 否 | 否 | 否 |
| build_fetch_command | 否 | 否 | 否 | 否 | 否 |
| manifest fetch_attempts 写入 | 否 | 是 | 否 | 否 | 否 |
| branch-aware protect push | 是 | 否 | 是(push) | 否 | 否 |
| dry-run fetch plan | 否 | 否 | 否 | 否 | 否 |

## 12. 实现计划（T3 Implement 执行）

### 12.1 实施顺序

1. **新增常量**（~40-70 行面板区）：`FETCH_MAX_ATTEMPTS = 3`, `FETCH_RETRY_DELAYS = [2, 5]`
2. **新增 `classify_git_transport_failure()`**：纯函数，枚举 20 条模式，单分支 `re.search` 循环。插入位置：`fetch_remotes()` 之前（约 :1129 前）。
3. **新增 `build_fetch_command()`**：target-aware 命令构造。插入位置：`classify_git_transport_failure()` 之后。
4. **新增 `run_fetch_with_transport_policy()`**：三次 attempt 状态机。插入位置：`build_fetch_command()` 之后。
5. **重写 `fetch_remotes()`**（:1129-1161）：替换为调用 `run_fetch_with_transport_policy()` + origin fetch 保留。
6. **重写 `protect_local_commits()`**（:1231-1256）：branch-aware push。
7. **增量修改 `print_dry_run()`**（:1544-1637）：修改 step 4 输出，增加 retry plan 说明。

### 12.2 需要配合的测试修改（T3/T4）

见 SPEC §8 测试表格（V2.1-UT-001~019, V2.1-REG-001~002, V2.1-SMOKE-001~003）。

### 12.3 无需修改的现有代码

- `git()` 函数（:200-230）：不修改。`-c` 参数作为 `args` 列表元素传入即可工作。
- `CommandResult` dataclass：不修改。
- `UpgradeConfig`：不新增字段。
- `RepoState`：不修改。
- `GitPlan`：不修改。
- `upgrade()` 主流程（:1650+）：不修改（S3 `fetch_remotes` 的内核被替换但接口不变）。

## 13. 验证策略

### 13.1 离线单元测试（T3/T4 自动化）

| 类型 | 方法 | 覆盖范围 |
|---|---|---|
| classify 参数化 | `pytest.mark.parametrize` 逐条测试 | 所有 20 条模式（包括空/不匹配） |
| build_fetch_command | 对比 return 值与预期 `list[str]` | branch/tag/tag heuristic 路径 |
| run_fetch_policy | mock `git()` 返回模拟 exit_code/stderr | 成功/transient/permanent/non_transport/dry-run 路径 |
| manifest fetch_attempts | 检查 `manifest["fetch_attempts"]` | 字段完整/无 secret |
| protect_local_commits | temp git repo 模拟 origin | main/feature/branch/detached 路径 |

### 13.2 temporary-bare-repo 集成测试

`temporary-bare-repo` 验证（无需网络）：
1. 创建 temp bare repo 模拟 `upstream`
2. clone temp repo + commit → push → 测试 fetch 命令参数
3. 验证 `--no-tags` 期望行为（bare repo 无 tag 时命令仍正确）

### 13.3 真实 E2E（Activation 阶段）

以下验证不属于 T3/T4，属于 **Review PASS 后 Pascal 逐项授权的 Activation**：

| 操作 | 需 Pascal 确认 | 方法 |
|---|---|---|
| 真实 fetch upstream | 是 | 首次在 test branch 手动 `--dry-run`，再实际执行一次 |
| 真实 merge/install/restart | 是 | 选择合适时间窗口 |
| Feishu 推送验证 | 是 | 检查 manifest 能否被 Feishu 机器人解析 |

### 13.4 验证命令

```bash
# 语法检查
cd /home/pascal/workspace/yquant-investment
python3 -m py_compile scripts/upgrade/upgrade_hermes_agent.py

# V1 + V2 + V2.1 全量测试
python3 -m pytest tests/scripts/test_upgrade_hermes_agent.py tests/scripts/test_upgrade_hermes_agent_v2.py -v

# 分类器专项
python3 -m pytest tests/scripts/test_upgrade_hermes_agent_v2.py -v -k "classify"

# Fetch policy 专项
python3 -m pytest tests/scripts/test_upgrade_hermes_agent_v2.py -v -k "fetch_policy or build_fetch"

# Protect 专项
python3 -m pytest tests/scripts/test_upgrade_hermes_agent_v2.py -v -k "protect"

# Dry-run smoke
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push --version v2026.7.1

# Tag dry-run
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push --version upstream/main
```

## 14. 风险与应对

| 风险 | 概率 | 影响 | 应对 | 降级 |
|---|---|---|---|---|
| `-c http.version=HTTP/1.1` 在某些 WSL/proxy 上不兼容 | 低 | 中 | attempt 3 是最后 fallback，不影响正常路径；HTTP/1.1 也失败 = 用户手动处理 | 人工 `git fetch` 后重跑 |
| classifier 漏标新瞬态错误模式 | 中 | 中 | 漏标 → `non_transport` → fail-stop。operator 根据 `commands[].stderr_tail` 手动判断 | 后续小版本补充模式 |
| branch-aware protect push 误触 non-fast-forward | 低 | 高 | 无 `--force` 参数。`git push -u origin <branch>` 默认拒绝 non-ff（除非 `receive.denyNonFastForwards`=false） | 用户手动 resolve |
| fetch retry 把 ~15 分钟的时间投入全花在 3 次 attempt 上 | 中 | 低 | 正常路径仅 1 次 attempt（~5 分钟）。3 次全部失败也比重新完整升级快 | 用户 `CTRL+C` 后手动 retry |
| `build_fetch_command` tag heuristic 对非 `v*` tag 无法识别 | 中 | 低 | heuristic 失败 → tag 被当作 branch 名 → `--no-tags upstream <tag>` → Git 可能 resolve 失败 → classifier 返回 `couldn't find remote ref` → permanent → fail-stop | 用户可明确使用 `refs/tags/<tag>` 格式 |

## 15. 交接给 T3 Implement（yquantdeveloper）

### 15.1 T3 允许修改的文件（Allowlist）

| 文件 | 允许操作 | 说明 |
|---|---|---|
| `scripts/upgrade/upgrade_hermes_agent.py` | ✅ 修改 | 仅 §3.1 所列 3 个现有函数 + 2 个新增函数 + 2 个新增常量 |
| `tests/scripts/test_upgrade_hermes_agent_v2.py` | ✅ 修改 | 新增 V2.1 测试用例，不破坏现有 V2.0 测试 |
| `tests/scripts/test_upgrade_hermes_agent.py` | ❌ 不改 | 全量回归，V1.0 测试不能因为 V2.1 的 signature 变化而失败 |

### 15.2 T3 禁止操作

- 禁止修改/删除三层文档（RFC/SPEC/Design）
- 禁止修改模板文件
- 禁止修改 `.gitignore`、`pyproject.toml`、`requirements/*`、`Makefile`
- 禁止修改 `data/hermes_patches.yaml`
- 禁止修改 Hermes profile / auth / MCP / systemd 配置
- 禁止修改 `/home/pascal/workspace/hermes-agent/**` 源码
- 禁止对真实 Hermes repo 执行 `git push` / `git merge` / `pip install` / `restart`
- 禁止修改 V1.0 / V2.0 测试的断言语义
- 禁止引入新第三方依赖（包括不写入 `requirements/` 或 `pyproject.toml` 的隐式依赖）

### 15.3 T3 可自行判断

- `build_fetch_command` 中的 tag heuristic 是否用 `startswith` + `any(ch.isdigit())` 或更简单的 `target.startswith(("v", "V"))` + 后续 `re.search(r"\d", target)`。两者等价，选更简洁的。
- `git()` 函数是否需要额外处理 `-c` 参数（应不需要，git 语义支持 `-c` 在任意位置）。
- `_build_attempt_command` 辅助函数是作为 `run_fetch_with_transport_policy` 的内部函数，还是单独顶层函数。推荐：简单内部 helper 函数 + 单行逻辑。

### 15.4 遇到以下情况退回 T2 Principal

- 发现需要修改 `upgrade()` 主流程控制结构（S0-S9 顺序不变假设不成立）
- 发现需要使用 `http.postBuffer`、`http.lowSpeedLimit`、`http.lowSpeedTime` 配置
- 发现需要新增第三方 Python 依赖
- 发现需要修改 Hermes profile / 系统环境变量 / systemd
- 发现 V1.0 或 V2.0 测试因 V2.1 修改而必须大改（signature 兼容问题优先调整本设计，而非由 Implement 大改测试）

## 16. 自检检查表（Design Gate PASS）

- [x] RFC、SPEC、Design 三层路径一致（`10_infra/` 前缀，`DESIGN-10-006` 版本 V2.1）
- [x] Design 仅写入 `docs/design/10_infra/DESIGN-10-006-hermes-upgrade-script-v2.md`，未触碰其他文件
- [x] 每种错误分类（transient / permanent / non_transport）均有可证伪的示例（边界输入 → 明确输出）
- [x] 每个 fetch attempt 的 command 构造给出了精确的 `list[str]` 断言
- [x] Manifest `fetch_attempts` schema 明确 7 字段，红线字段（secret/credential/proxy）已被排除
- [x] `protect_local_commits` 的 push 行为精确到 `["push", "-u", "origin", branch]`，无 force push
- [x] dry-run 零网络契约：`fetch_remotes()` 入口检查 `config.dry_run` → return，不调用 `run_fetch_with_transport_policy`
- [x] 所有 blocking / major / minor 风险已闭合或记录剩余风险
- [x] T3 allowlist 和 forbidden list 明确列出
- [x] T3 退回条件明确（4 种情形）

## 17. 开放问题

无。本设计所有实现决策已闭合至代码级精确度。
