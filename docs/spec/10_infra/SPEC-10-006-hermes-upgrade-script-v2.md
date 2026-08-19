# SPEC-10-006：Hermes Agent 自动升级脚本 V2

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-08-20 |
| 版本号 | V2.2 |
| 来源 RFC | RFC-10-006-hermes-upgrade-script-v2 |
| 继承 SPEC | SPEC-10-005-hermes-auto-upgrade, SPEC-10-006 V2.0, V2.1 |
| 关联 Design | DESIGN-10-006-hermes-upgrade-script-v2 |
| 目标模块 | 10_infra / Hermes 运维自动化 |

## 1. 需求摘要

本 SPEC 将 RFC-10-006 V2.1 的传输韧性增量需求落为可执行、可测试的工程契约，并完整继承 SPEC-10-005（V1.0）的安全升级主线与 SPEC-10-006 V2.0 的 feature-branch/patch-manifest 能力。

V2.1 不做主线重写，只在 3 个函数位置做增量替换：

1. **`fetch_remotes()`**：target-aware fetch（移除隐式 `--tags`） + `run_fetch_with_transport_policy()` 包装器（3 次 attempt 状态机）。
2. **`protect_local_commits()`**：从 `push origin main` 改为 `push origin <state.branch>` + 可达性先检。
3. **`print_dry_run()`** / **manifest 写入**：新增 fetch attempt 计划描述与 `fetch_attempts` 数组。

所有非 fetch 阶段（merge/install/restart/push）不会获得自动重试能力。

## 2. 范围

### 2.1 In Scope

- 修改 `scripts/upgrade/upgrade_hermes_agent.py`：
  - `fetch_remotes()` 变为 target-aware + 调用 retry wrapper。
  - 新增 `classify_git_transport_failure(stderr)` 纯函数。
  - 新增 `run_fetch_with_transport_policy()` 带 3 次 attempt 状态机。
  - 修改 `protect_local_commits()` 分支感知 push。
- manifest 新增 `fetch_attempts` 数组。
- `--dry-run` 扩展输出 fetch plan（target-aware 命令 + 是否含 HTTP/1.1 fallback）。
- 更新 `docs/rfc/10_infra/RFC-10-006-hermes-upgrade-script-v2.md`。
- 更新 `docs/spec/10_infra/SPEC-10-006-hermes-upgrade-script-v2.md`。
- 新增/更新测试覆盖错误分类、retry 状态机、branch-aware protect、dry-run 零网络。

### 2.2 Out of Scope（不重复 V2.0 out of scope）

- 不修改 `/home/pascal/workspace/hermes-agent/**` 源码。
- 不修改 Hermes profile config、`.env`、`auth.json`、MCP、provider/model/fallback、gateway platform 配置或 systemd unit。
- 不修改 `data/hermes_patches.yaml`。
- 不新增第三方依赖。
- 不实现任何 fetch 之外的自动重试（merge/install/restart/push）。
- 不写入 git config（`--global`/`--system`/`--local`）。
- 不改变代理环境变量（`http_proxy`/`https_proxy`/`no_proxy`）。
- 不引入 `http.postBuffer`、`http.lowSpeedLimit`、`http.lowSpeedTime` 配置。

### 2.3 V2.1 新 In Scope 明确列表

| 项 | 类型 | 路径/位置 |
|---|---|---|
| `classify_git_transport_failure` | 新增函数 | `scripts/upgrade/upgrade_hermes_agent.py` |
| `run_fetch_with_transport_policy` | 新增函数 | 同上 |
| `fetch_remotes()` V2.0 → V2.1 重写 | 修改 | 同上 |
| `protect_local_commits()` V2.0 → V2.1 修改 | 修改 | 同上 |
| `print_dry_run()` 扩展 | 修改 | 同上 |
| manifest `fetch_attempts` 写入 | 新增逻辑 | 同上 |
| `FETCH_ATTEMPT_DELAYS` 常量 | 新增 | 同上级作用域 |
| V2.1 新增测试用例 | 新增 | `tests/scripts/test_upgrade_hermes_agent_v2.py` |
| 更新 RFC/SPEC | 修改 | `docs/rfc/10_infra/`, `docs/spec/10_infra/` |

## 3. 功能规格

### 3.1 V2.0 已有功能（保留不变）

| 编号 | 行为 | 章节 |
|---|---|---|
| F2-001 | CLI 参数解析（`--branch`, `--preserve-features`, `--patches-manifest`） | SPEC-10-006 V2.0 §3 |
| F2-002 | branch 允许列表检查 | 同上 |
| F2-003 | feature branch 保护计划 | 同上 |
| F2-004 | feature branch push | 同上 |
| F2-005 | patches manifest 读取 | 同上 |
| F2-006 | patch schema 校验 | 同上 |
| F2-007 | upstream patch 核对 | 同上 |
| F2-008 | dry-run V2 输出 | 同上 |
| F2-009 | V1 兼容性 | 同上 |
| F2-010 | manifest 审计扩展（patch_statuses） | 同上 |

### 3.2 V2.1 新增功能

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| F2-011 | **Target-aware fetch 命令构造** | remote + target + `fetch_all_tags`（boolean） | `list[str]` 命令参数 | 默认 `--no-tags upstream <branch>`；显式 tag target 使用 `upstream refs/tags/<tag>:refs/tags/<tag>` |
| F2-012 | **瞬态错误分类** | `subprocess.stderr` | `"transient"` / `"permanent"` / `"non_transport"` | 纯函数；大小写不敏感模式匹配；空 stderr 返回 `"non_transport"` |
| F2-013 | **有限重试 fetch** | remote + target + `git` command | `CommandResult` | 总 attempt ≤ 3；成功后立即返回；最终失败 emit `UpgradeError` |
| F2-014 | **Manifest fetch attempt 审计** | attempt 元数据 | manifest `fetch_attempts[]` | 不记录代理 URL、凭证、未脱敏 stderr |
| F2-015 | **分支感知保护 push** | `state.branch`, `state.pre_head` | push 结果 | 当前分支名用于 push target，不可用 `main` 代表 |
| F2-016 | **Dry-run 零网络传输** | `config.dry_run` | 打印计划 | 不 sleep、不 fetch、不 merge、不 push |

### 3.3 F2-011 Target-aware fetch 命令构造

**输入**：
- `remote: str`（如 `"origin"`, `"upstream"`）
- `target: str`（如 `"main"`, `"v2026.7.1"`，去除 remote 前缀后）
- `fetch_all_tags: bool`（该参数为 static False；保留参数而非常量以便未来 Escape hatch，见 RFC §7 "不实现"）

**输出**：`list[str]` 命令参数，如 `["fetch", "--no-tags", "upstream", "main"]` 或 `["fetch", "upstream", "refs/tags/v2026.7.1:refs/tags/v2026.7.1"]`。

**构造规则**：

| target 特征 | 命令 |
|---|---|
| 非 tag（bare branch name / ref，如 `main`） | `git fetch --no-tags <remote> <target>` |
| 含 `refs/tags/` 前缀（调用方已解析为 tag） | `git fetch <remote> <target>:<target>`（不追加 `--no-tags`，已精确） |
| 调用方通过 `is_tag` 明确判定 | `git fetch <remote> refs/tags/<target>:refs/tags/<target>` |

**设计理由**：

- `--no-tags` 阻止 Git 隐式跟随 tag 链，减少不必要的 packfile 传输。这对代理环境有利，因为 tag 数据在纯 branch 升级场景中不用于解析 `--version` 目标。
- Tag target 场景使用精确 refspec，只拉取被请求的 tag。
- 保留 `fetch_all_tags` 参数为 static `False` 而非移除，避免后续需要时做大范围重构。

### 3.4 F2-012 瞬态错误分类（classify_git_transport_failure）

函数签名：

```python
def classify_git_transport_failure(stderr: str, stdout: str = "") -> str:
    """Return 'transient' | 'permanent' | 'non_transport'."""
```

分类表（大小写不敏感匹配，优先级由上至下）：

| 优先级 | 模式（`re.search`，`re.IGNORECASE`） | 返回分类 |
|---|---|---|
| 1 | `repository not found` 或 `` could not find `repo`/`` | `permanent` |
| 2 | `authentication failed` | `permanent` |
| 3 | `access denied` 或 `permission denied` | `permanent` |
| 4 | `host key verification failed` | `permanent` |
| 5 | `certificate verification failed` | `permanent` |
| 6 | `fatal: couldn't find remote ref` | `permanent` |
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

实现约束：

- 使用单一预编译 `re.compile(patterns, re.IGNORECASE)` 循环，不引入外部依赖。
- `permanent` 模式优先级高于 `transient`，避免某条 stderr 同时命中两个分类时误判。
- 不将 stdlib `http.client` / `urllib` 错误纳入；所有输入来自 git subprocess 输出。
- 测试必须覆盖表内每条模式和 1 条不匹配的随机字符串。

### 3.5 F2-013 有限重试 fetch（run_fetch_with_transport_policy）

签名：

```python
def run_fetch_with_transport_policy(
    remote: str,
    target: str,
    *,
    repo: Path,
    manifest: dict,
    verbose: bool = False,
    timeout: Optional[int] = 300,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> CommandResult:
```

参数：
- `remote`：git remote 名。
- `target`：fetch 目标 branch/tag 名（不含 remote 前缀）。
- `repo`：git repo 路径。
- `manifest`：当前升级 manifest dict（写入 `fetch_attempts`）。
- `verbose`：`--verbose` 开关。
- `timeout`：每个 attempt 的超时秒数。
- `sleep_fn`：可注入的 sleep 函数（测试中用 `lambda _: None` 跳过等待）。

**Attempt 序列**：

| attempt | 前提 | 命令 | sleep 前 |
|---|---|---|---|
| 1（normal） | 总是 | `git fetch --no-tags <remote> <target>` | 否 |
| 2（retry） | attempt 1 分类为 `transient` | `git fetch --no-tags <remote> <target>` | 是，2s |
| 3（fallback） | attempt 2 分类为 `transient` | `git -c http.version=HTTP/1.1 fetch --no-tags <remote> <target>` | 是，5s |

任何 attempt 返回 exit code 0 → 立即返回该 `CommandResult`，不继续剩余 attempt。

**Attempt 元数据写入**：

每个 attempt 执行后（无论成功/失败），向 `manifest.setdefault("fetch_attempts", [])` 追加：

```python
{
    "remote": remote,
    "target": target,
    "attempt": attempt_number,
    "transport": transport_label,  # "default" 或 "http/1.1-fallback"
    "exit_code": result.exit_code,
    "failure_class": failure_class if exit_code != 0 else None,
    "retry_delay_seconds": next_delay if attempt < 3 and exit_code != 0 else None,
}
```

3 次 attempt 全部失败后：`raise UpgradeError("fetch", "...", next_steps=[...])`。

**`UpgradeError.next_steps` 消息**：

```
fetch 已达上限 3 次 (场景: {'normal'|'backoff-retry'|'http/1.1-fallback'}):
  - 所有 attempt 已记录到 manifest <manifest_path>
  - 手动重试命令: git fetch --no-tags <remote> <target>
  - 若确认是代理/TLS 问题，可临时尝试: git -c http.version=HTTP/1.1 fetch --no-tags <remote> <target>
  - 备份路径: <backup_zip>
```

**不可重试场景**：

- attempt 1 分类为 `permanent` → 立即 `raise UpgradeError("fetch", "永久错误: ...")`，不重试、不 sleep。
- attempt 1 分类为 `non_transport` → 立即 fail-stop（该分类不属于 fetch 层可处理的错误）。
- 非 fetch 阶段（merge/install/restart/push）出现任何错误 → 使用现有 V1.0 fail-stop 逻辑，永不重试。

**特殊拒绝场景（fail-fast，无需 attempt1）：**

| 场景 | 前置检测 | 行为 |
|---|---|---|
| remote 名无效 | `git remote get-url <remote>` 失败 | 立即 `UpgradeError`，不尝试 fetch |
| target 为空 | `not target` | `UpgradeError("fetch", "target 为空")` |
| dry-run 模式 | `config.dry_run` | 只打印 fetch 命令（含 HTTP/1.1 计划），不执行任何 attempt |

### 3.6 F2-014 Manifest fetch attempt 审计

**新增字段**：`manifest["fetch_attempts"]`（list，每个 attempt 一个 dict）。

每个 attempt 的 schema：

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---|---|---|
| `remote` | string | 是 | `"upstream"` | git remote 名 |
| `target` | string | 是 | `"main"` | fetch 目标（不含 remote 前缀） |
| `attempt` | int | 是 | `1` | attempt 序号（1-based） |
| `transport` | string | 是 | `"default"` 或 `"http/1.1-fallback"` |
| `exit_code` | int | 是 | `0` / `128` | git 命令 exit code |
| `failure_class` | string/null | 否 | `"transient"` | exit != 0 时的分类；exit=0 时为 `null` |
| `retry_delay_seconds` | int/null | 否 | `2` | 下一次重试前 sleep 的秒数（仅为下次 attempt 的退避） |

**安全规则**：

- 不得在 `fetch_attempts` 中写入 `proxy` URL、`http_proxy`/`https_proxy` 值、git credential、token 或 access token。
- 现有 `redact()` 函数已对 `commands` 数组做脱敏；`fetch_attempts` 因仅存储结构化元数据，不应包含原始 stderr。stderr 摘要仍然通过已有的 `commands[]` 中的 `stderr_tail` 记录（已脱敏）。
- `failure_class` 只是分类标签（`"transient"` / `"permanent"` / `"non_transport"`），不包含原始错误内容。

**已有 manifest 字段不变**：`commands[]` 继续记录每个 git 命令的完整 cmd/cwd/exit_code/stdout_tail/stderr_tail（均经 `redact()`）。

### 3.7 F2-015 分支感知保护 push

**当前代码位置**：`protect_local_commits()` in `scripts/upgrade/upgrade_hermes_agent.py:1231-1256`。

**V2.1 重写后的行为**：

```
def protect_local_commits(config, state, plan, manifest):
    if not plan.local_commits_need_protection:
        return

    cmd_log = manifest.setdefault("commands", [])
    head = state.pre_head
    branch = state.branch  # V2.1 新增：使用 state.branch

    # Step 1: 检查 HEAD 是否已在 origin/<branch> 可达
    if origin_main_sha:  # V2.0 保持了 origin fetch 的结果
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
                           next_steps=[f"手动 push: git -C {config.repo} push -u origin {branch}",
                                       "检查 SSH/HTTPS 认证与 fork 权限。"])
    log_ok(f"本地 commit 已保护至 origin/{branch}。")
```

**与 V2.0 的关键差异**：

| 行为 | V2.0 | V2.1 |
|---|---|---|
| push target | `"origin"`, `"main"` | `"origin"`, `state.branch` |
| push 可选 `-u` | 无 | 添加 `-u` 设置 upstream |
| force push | 无 | 无（保持不变） |
| 可达性检查 | 误用 `_is_ancestor(pre_head, pre_head)` 始终 true | 正确检查 `origin/<branch>` |
| 消息 | "已保护至 origin" | "已保护至 origin/{branch}" |
| feature branch 保护 | 不保护（只 push main） | 按 branch 保护 |
| `--preserve-features` 交互 | 分开 S0.5 | protect_local_commits 也按 branch 保护 |

### 3.8 F2-016 Dry-run 零网络

在 `print_dry_run()` 中输出 fetch 计划时：

| 原 V2.0 行为 | V2.1 行为 |
|---|---|
| 不展示 fetch 命令细节 | 展示 target-aware fetch 命令和 retry plan |
| 不区分 tag/branch fetch | 明确输出 `--no-tags ... main` 或 `refs/tags/...` |
| 不展示 fallback | 输出 "如果瞬态失败, 将退避重试后 fallback 至 HTTP/1.1" |
| — | 输出 "此 dry-run 不发送网络请求、不 sleep、不修改 git ref" |

**强制规则**（不仅默认行为，是契约）：
- `--dry-run` 模式下，`run_fetch_with_transport_policy()` 必须检查 `config.dry_run` 并在第一时间返回（打印计划、不调用 subprocess、不调用 `sleep_fn`）。
- `fetch_remotes()` 必须在 entry 处检查 `config.dry_run` 并跳转到 `print_dry_run_fetch_plan()`。
- `protect_local_commits()` 在 dry-run 中只打印计划，不执行 push。

### 3.9 F2-016b Dry-run merge_mode 分类与 behind-upstream 显示（V2.2 增量）

**背景**：2026-08-20 实战升级（v0.19.0 → v0.20.4，4277 commits）发现两个 dry-run 输出瑕疵：

1. **`print_dry_run()` merge_mode 漏判"target 是 head 祖先"分支**——`head == target` 和 `head is ancestor of target` 两条分支覆盖了 `ff-only` 与"head 与 target 完全无关"，但当 `target is ancestor of head`（HEAD 已包含 target，例如手工 merge 之后）时，dry-run 错误显示 `merge_mode: merge`，与 `classify_git_relation()` 真实逻辑（返回 `already-up-to-date`）不一致。
2. **dry-run 不显示 HEAD 与 upstream/main 的真实差距**——`hermes --version` 的 "Up to date" 对 fork 失明（只对比 origin/main，不看 upstream；P-5 陷阱），用户从脚本输出看不到真实 commit 距离。

**新增契约（F2-016b）**：

- **F2-016b-1**：`print_dry_run()` 在 resolve target 后必须做三分支判断，与 `classify_git_relation()` 逻辑对齐：
  - `head == target_sha` → `already-up-to-date`
  - `head is ancestor of target_sha` → `ff-only`
  - `target_sha is ancestor of head` → `already-up-to-date  (HEAD 已含 target)` ← V2.2 新增
  - 其他（diverged）→ `merge`
- **F2-016b-2**：当 `config.version_ref == "upstream/main"` 时，dry-run 必须额外显示 `behind upstream/main: N commit(s)`（使用 `git rev-list --count HEAD..upstream/main`），其中 `N=0` 标注"HEAD 已追平 upstream"，`N>0` 时附带"truth source；--version 自报不可信"提示以对抗 P-5 陷阱。tag/branch target 不显示此字段（无对比意义）。
- **F2-016b-3**：`behind_upstream` 计算必须 best-effort，rev-list 失败时降级为 `(无法读取，本地无 upstream/main 引用)`，不阻塞 dry-run。

**不引入**：新增第三方依赖、git config 写入、auto retry、auto push。

## 4. 数据与接口契约

### 4.1 新增/修改常量

| 名称 | 值 | 类型 | 说明 |
|---|---|---|---|
| `FETCH_MAX_ATTEMPTS` | `3` | int | 单个 fetch 的最大 attempt 次数 |
| `FETCH_RETRY_DELAYS` | `[2, 5]` | list[int] | attempt 1→2 的退避秒数, attempt 2→3 的退避秒数 |
| `FETCH_TIMEOUT` | `300` | int | 每个 fetch attempt 的超时秒数（继承 V1.0） |

### 4.2 新增函数签名

```python
def classify_git_transport_failure(stderr: str, stdout: str = "") -> str:
    """Return 'transient' | 'permanent' | 'non_transport'."""
    ...

def build_fetch_command(remote: str, target: str, *,
                        fetch_all_tags: bool = False) -> tuple[list[str], str]:
    """Return (cmd_args, transport_label).
    transport_label is 'default' or 'http/1.1-fallback'.
    """
    ...

def run_fetch_with_transport_policy(
    remote: str, target: str, *,
    repo: Path, manifest: dict,
    verbose: bool = False,
    timeout: Optional[int] = 300,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> CommandResult:
    """Execute fetch with target-aware command, classified retry, audit."""
    ...
```

### 4.3 fetch_remotes() V2.1 调用流

```python
def fetch_remotes(config, manifest, target_ref):
    # Step A: resolve remote + target from target_ref
    remote_for_ref, bare_target = _parse_remote_target(target_ref)

    # Step B: fetch origin main (unchanged from V1.0)
    run_fetch_with_transport_policy(
        "origin", "main",
        repo=config.repo, manifest=manifest,
        verbose=config.verbose,
    )

    # Step C: fetch upstream with policy, target-aware
    if remote_for_ref == "upstream":
        run_fetch_with_transport_policy(
            "upstream", bare_target,
            repo=config.repo, manifest=manifest,
            verbose=config.verbose,
        )
    else:
        # target does not start with a known remote: fetch default
        run_fetch_with_transport_policy(
            "upstream", target_ref.split("/", 1)[-1] if "/" in target_ref else target_ref,
            repo=config.repo, manifest=manifest,
            verbose=config.verbose,
        )
```

### 4.4 UpgradeConfig 增量

无新增字段。V2.1 通过现有 `UpgradeConfig` 字段工作，无新 CLI 参数。

### 4.5 Git ref 操作安全契约

| 操作 | 允许在 fetch 函数内 | 允许在保护函数内 | 允许在 merge 函数内 |
|---|---|---|---|
| `git fetch`（只读） | 是 | 否 | 否 |
| `git merge` | 否 | 否 | 是 |
| `git push` | 否 | 是 | 否 |
| `git rev-parse` | 是 | 是 | 是 |
| `git merge-base` | 否 | 是 | 是 |
| `git -c http.version=HTTP/1.1` | 仅 attempt 3 | 否 | 否 |

## 5. 行为契约（用户决策 → 代码层映射）

| V2.1 决策 | SPEC 落地点 | 章节 |
|---|---|---|
| 只 retry fetch，不 retry merge/install/restart/push | F2-013 attempt 限 3 + 非 fetch 行为不变 | §3.5, §2.2 |
| 仅瞬态错误可重试 | F2-012 classifier | §3.4 |
| tag 不再是隐式依赖 | F2-011 默认 `--no-tags` | §3.3 |
| HTTP/1.1 是 command-local fallback | F2-013 attempt 3 的 `-c http.version=HTTP/1.1`；不写 config | §3.5, §2.2 |
| 分支保护推送到当前分支 | F2-015 `push -u origin <state.branch>` | §3.7 |
| Dry-run 不发网络 | F2-016 + §3.5 dry-run guard | §3.8 |
| Manifest records 只记结构化元数据，不记原始 stderr | F2-014 安全规则 | §3.6 |

## 6. 文件改动清单

### 6.1 新增文件

无。

### 6.2 修改文件

| 文件 | 变更说明 |
|---|---|
| `scripts/upgrade/upgrade_hermes_agent.py` | 新增 `classify_git_transport_failure`, `build_fetch_command`, `run_fetch_with_transport_policy`；重写 `fetch_remotes()`；重写 `protect_local_commits()`；扩展 `print_dry_run()`；新增 `fetch_attempts` 写入 |
| `tests/scripts/test_upgrade_hermes_agent_v2.py` | 新增 V2.1 测试用例（见 §8 测试要求） |
| `docs/rfc/10_infra/RFC-10-006-hermes-upgrade-script-v2.md` | V2.0 → V2.1 更新 |
| `docs/spec/10_infra/SPEC-10-006-hermes-upgrade-script-v2.md` | V2.0 → V2.1 更新 |
| `docs/design/10_infra/DESIGN-10-006-hermes-upgrade-script-v2.md` | T2 Design 阶段创建（适配 V2.1） |

### 6.3 明确不改（V2.0 清单 + V2.1 新增）

- `docs/rfc/RFC-00-000-rfc-template.md`
- `docs/spec/SPEC-00-000-spec-template.md`
- `docs/design/DESIGN-00-000-design-template.md`
- `data/hermes_patches.yaml`
- `/home/pascal/workspace/hermes-agent/**`
- `~/.hermes/profiles/**/config.yaml`
- `~/.hermes/profiles/**/.env`
- `~/.hermes/auth.json` 或任意 token/auth 文件
- Hermes gateway systemd/platform 配置
- YQuant 投研、交易、风控、数据管道、报告业务代码
- 任何 `.gitconfig`（`--global`/`--system`/`--local`）
- `~/.bashrc`, `~/.zshrc`, `/etc/environment`, `/etc/profile`

### 6.4 部署与运行注意事项

- V2.1 无新第三方依赖，`import time` 已是现有标准库引用。
- 修改不改变 `upgrade_hermes_agent.py` 的入口点与 CLI 接口兼容性。
- V2.0 `data/hermes_patches.yaml` 维持不变（路径、schema、内容）。

## 7. 副效应矩阵

```text
+------------------------+----------+----------+----------+----------+----------+
| 活动 \ 副效应           | 写网络   | 写磁盘   | 写Git   | 写配置   | 写代理   |
+------------------------+----------+----------+----------+----------+----------+
| fetch (attempt 1)      | 是       | 是       | 是(fetch)| 否       | 否       |
| fetch (attempt 2 retry)| 是       | 是       | 是(fetch)| 否       | 否       |
| fetch (attempt 3 H/1.1)| 是       | 是       | 是(fetch)| 否(acl)  | 否       |
| classify stderr        | 否       | 否       | 否       | 否       | 否       |
| manifest fetch_attempts| 否       | 是       | 否       | 否       | 否       |
| branch protect push    | 是       | 否       | 是(push) | 否       | 否       |
| dry-run fetch plan     | 否       | 否       | 否       | 否       | 否       |
+------------------------+----------+----------+----------+----------+----------+
```

注意：
- 所有 `http.version` 覆写是 `git -c http.version=HTTP/1.1` 命令参数级，**不是** `git config` 写入。
- `attempt 3` 写入的网络流量与 attempt 1/2 相同，但使用 HTTP/1.1 协议而非 HTTP/2。
- `classify` 是纯 Python 字符串匹配，无 I/O 副效应。

## 8. 测试要求

### 8.1 V2.1 新增测试

| 编号 | 类型 | 命令/方法 | 断言 |
|---|---|---|---|
| V2.1-UT-001 | classify: 每一条 transient 模式 | 单元测试构造匹配 stderr 输入 | `"transient"` |
| V2.1-UT-002 | classify: 每一条 permanent 模式 | 单元测试构造匹配 stderr 输入 | `"permanent"` |
| V2.1-UT-003 | classify: 空/不匹配 | `classify("")`, `classify("some random message")` | `"non_transport"` |
| V2.1-UT-004 | classify: permanent 优先于 transient | stderr 同时包含 auth 和 TLS 错误 | `"permanent"` |
| V2.1-UT-005 | build_fetch_command: 默认 branch | `build_fetch_command("upstream", "main")` | `["fetch", "--no-tags", "upstream", "main"]` |
| V2.1-UT-006 | build_fetch_command: tag target | `build_fetch_command("upstream", "v2026.7.1")` | `["fetch", "upstream", "refs/tags/v2026.7.1:refs/tags/v2026.7.1"]` |
| V2.1-UT-007 | run_fetch_policy: 正常单 attempt | mock `run_cmd` 返回 exit=0 | 仅 1 次 attempt, result.exit=0, no retry |
| V2.1-UT-008 | run_fetch_policy: transient → retry → OK | mock 1→128(transient), 2→0 | 2 次 attempt, 第 2 次成功, manifest 含 2 条 |
| V2.1-UT-009 | run_fetch_policy: transient → retry → transient → HTTP/1.1 → OK | mock 1→128, 2→128, 3→0 | 3 次 attempt, 第 3 次 transport="http/1.1-fallback" |
| V2.1-UT-010 | run_fetch_policy: transient → retry → transient → HTTP/1.1 → fail | mock 3×128 | 3 次 attempt, 最终 `UpgradeError` |
| V2.1-UT-011 | run_fetch_policy: permanent → fail-stop | mock 1→128(permanent) | 仅 1 次 attempt, 立即 `UpgradeError` |
| V2.1-UT-012 | run_fetch_policy: non_transport → fail-stop | mock 1→128(non_transport) | 仅 1 次 attempt, 立即 `UpgradeError` |
| V2.1-UT-013 | run_fetch_policy: dry-run 不发网络 | `config.dry_run=True`, mock 不调用 run_cmd | 输出 plan 但无 subprocess 调用, no sleep_fn call |
| V2.1-UT-014 | run_fetch_policy: sleep_fn 可注入 | 提供 `lambda s: None`, 检测被调用 | transient 时调用 sleep_fn(2) + sleep_fn(5) |
| V2.1-UT-015 | manifest fetch_attempts 结构 | 验证 manifest 产出 | 字段名、类型、必填符合 §3.6 表 |
| V2.1-UT-016 | protect_local_commits: feature branch | temp repo feature-branch, mock head 不在 origin/<branch> | `push -u origin <feature-branch>` 被调用 |
| V2.1-UT-017 | protect_local_commits: main branch | temp repo main, mock head 不在 origin/main | `push -u origin main` 被调用（等价 V2.0） |

### 8.3 V2.2 新增测试（F2-016b）

| 编号 | 类型 | 输入 | 断言 |
|---|---|---|---|
| V2.2-UT-001 | dry-run merge_mode: target is ancestor of head | HEAD 含 1 个本地 commit，target 是其祖先 | 输出含 `merge_mode: already-up-to-date  (HEAD 已含 target)`，**不含** `merge_mode: merge` |
| V2.2-UT-002 | dry-run merge_mode: head is ancestor of target | upstream 5 commit 领先，HEAD 未拉取 | 输出 `merge_mode: ff-only` |
| V2.2-UT-003 | dry-run merge_mode: diverged | local + upstream 各 1 commit 独立推进 | 输出 `merge_mode: merge` |
| V2.2-UT-004 | behind upstream: 已追平 | HEAD 领先 upstream 3 commit | 输出 `behind upstream/main: 0  (HEAD 已追平 upstream)` |
| V2.2-UT-005 | behind upstream: 落后 | upstream 5 commit 领先，HEAD 未拉取 | 输出 `behind upstream/main: 5 commit(s)`，含 `truth source` 提示 |
| V2.2-UT-006 | behind upstream: tag target 不显示 | `version_ref=v2026.7.1` | 输出**不包含** `behind upstream/main` |
| V2.1-UT-018 | protect_local_commits: HEAD 已在 origin | mock merge-base 返回 0 | skip push |
| V2.1-UT-019 | fetch_remotes: target-aware 集成 | temp bare repo, 检查远程 fetch 命令参数 | `--no-tags upstream main` 出现在命令日志 |
| V2.1-REG-001 | V1 regression | `pytest tests/scripts/test_upgrade_hermes_agent.py` | 全部通过 |
| V2.1-REG-002 | V2.0 regression | `pytest tests/scripts/test_upgrade_hermes_agent_v2.py` | 全部通过（新测试不破坏旧测试） |
| V2.1-SMOKE-001 | dry-run 默认不联网 | `--dry-run --no-restart --no-push` | exit 0，输出含 fetch plan + "不发网络" |
| V2.1-SMOKE-002 | dry-run 显示 fetch 命令 | 同上，检查 stdout | 出现 `--no-tags upstream main` 和 `HTTP/1.1 fallback` |
| V2.1-SMOKE-003 | `--version v2026.7.1` dry-run | `--dry-run --no-restart --no-push --version v2026.7.1` | 输出 `refs/tags/v2026.7.1` 而非 `--no-tags` |

### 8.2 不可自动化验证项

- 真实 WSL 代理环境下，`fetch_remotes()` 瞬态错误分类 + retry + HTTP/1.1 fallback 的端到端成功率。对应真实升级验证需 Pascal 手工批准。
- 进入 production `protect_local_commits()` 真实 push origin。Tester 阶段用 temp repo 模拟。
- `fetch_attempts` 在真实 manifest JSON 文件中的写入可读性。

### 8.3 测试命令

```bash
# 从 yquant-investment repo 根目录
cd /home/pascal/workspace/yquant-investment

# V1.0 + V2.0 + V2.1 测试
python3 -m pytest tests/scripts/test_upgrade_hermes_agent.py tests/scripts/test_upgrade_hermes_agent_v2.py -v

# 语法检查
python3 -m py_compile scripts/upgrade/upgrade_hermes_agent.py

# Dry-run smoke
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push

# Python 单元测试单文件（V2.1 新增 classify）
python3 -m pytest tests/scripts/test_upgrade_hermes_agent_v2.py -v -k "V2.1-UT-001 or V2.1-UT-002"
```

## 9. 验收标准

| 编号 | 验收项 | 验证方式 | 对应测试 |
|---|---|---|---|
| A2.1-001 | classifier 覆盖表内所有 transient/permanent 模式 | 参数化测试 | V2.1-UT-001, 002 |
| A2.1-002 | classifier permanent 优先于 transient | stderr 混合输入 | V2.1-UT-004 |
| A2.1-003 | build_fetch_command 正确区分 branch/tag | 单元测试 | V2.1-UT-005, 006 |
| A2.1-004 | run_fetch_policy 成功路径 1 次 attempt | mock exit=0 | V2.1-UT-007 |
| A2.1-005 | run_fetch_policy transient 重试 ≤3 次 | mock 瞬态错误 | V2.1-UT-008~010 |
| A2.1-006 | run_fetch_policy permanent 立即 fail-stop | mock 永久错误 | V2.1-UT-011 |
| A2.1-007 | run_fetch_policy dry-run 不发网络 | mock run_cmd 不调用 | V2.1-UT-013 |
| A2.1-008 | manifest fetch_attempts 结构正确 | 字段验证 | V2.1-UT-015 |
| A2.1-009 | protect_local_commits 推当前 branch | temp repo 验证 | V2.1-UT-016, 017 |
| A2.1-010 | protect_local_commits 可达跳过 | mock merge-base | V2.1-UT-018 |
| A2.1-011 | V1.0 测试回归通过 | 全量 V1 测试 | V2.1-REG-001 |
| A2.1-012 | V2.0 测试回归通过 | 全量 V2 测试 | V2.1-REG-002 |
| A2.1-013 | Dry-run smoke 无网络副效应 | 手动运行 smoke | V2.1-SMOKE-001 |
| A2.1-014 | 不新增第三方依赖 | `git diff requirements/* pyproject.toml` | Review |
| A2.1-015 | 不触碰禁止文件 | `git diff --name-only` | Review |
| A2.1-016 | 无 git config 写入 | 代码审查 | Review |
| A2.1-017 | 无代理环境变量修改 | 代码审查 | Review |

## 10. 错误契约

### 10.1 fetch 阶段错误

| 错误情形 | 检测方式 | 处理方式 | 是否阻塞 |
|---|---|---|---|
| remote 名无效/不存在 | `git remote get-url <remote>` exit!=0 | `UpgradeError`, fail-stop | 是 |
| target 为空字符串 | `not target` | `UpgradeError` | 是 |
| attempt 1 exit!=0, classified `permanent` | classify(stderr) == "permanent" | `UpgradeError`, fail-stop | 是 |
| attempt 1 exit!=0, classified `non_transport` | classify(stderr) == "non_transport" | `UpgradeError`, fail-stop | 是 |
| attempt 1 exit!=0, classified `transient` | classify(stderr) == "transient" | 进入 retry | 否（直到全部尝试完） |
| attempt 2 exit!=0, classified `transient` | classify(stderr) == "transient" | 进入 HTTP/1.1 fallback | 否（直到全部尝试完） |
| attempt 3 exit!=0 | 任意分类 | `UpgradeError`, fail-stop | 是 |
| 3 次 attempt 全部 exit!=0 | 始终 | `UpgradeError` with next_steps | 是 |
| `--dry-run` 模式 | `config.dry_run` | 打印计划，不执行 subprocess | 否 |

### 10.2 保护阶段错误

| 错误情形 | 检测方式 | 处理方式 | 是否阻塞 |
|---|---|---|---|
| origin remote 不存在 | `git remote get-url origin` fail | `UpgradeError`, fail-stop | 是 |
| push 失败 (non-fast-forward / auth) | `git push` exit!=0 | `UpgradeError`, fail-stop | 是 |
| `--dry-run` 模式 | `config.dry_run` | 打印计划，不执行 push | 否 |
| HEAD 已在 `origin/<branch>` 可达 | `merge-base --is-ancestor` exit=0 | skip push | 否 |

## 11. 交付物检查清单

| 项 | 路径 | 本阶段交付 |
|---|---|---|
| RFC V2.1 | `docs/rfc/10_infra/RFC-10-006-hermes-upgrade-script-v2.md` | ✅ 本文件 |
| SPEC V2.1 | `docs/spec/10_infra/SPEC-10-006-hermes-upgrade-script-v2.md` | ✅ 本文件 |
| Design V2.1 | `docs/design/10_infra/DESIGN-10-006-hermes-upgrade-script-v2.md` | T2 Design 阶段 |
| 脚本修改 | `scripts/upgrade/upgrade_hermes_agent.py` | T3 Implement |
| 测试修改 | `tests/scripts/test_upgrade_hermes_agent_v2.py` | T3/T4 |
| Smoke 验证 | 终端命令 | T3/T4 |

## 12. 风险与未解决问题

| 风险 | 缓解 | 归属 |
|---|---|---|
| classifier 漏标新的 Git 错误模式，该模式实际上是瞬态的 | 本版本覆盖已知证据的所有模式；新模式可通过后续小版本补充 | Tester/Review |
| HTTP/1.1 fallback 可能在某些 proxy 上更加不稳定 | 仅作为第 3 次 fallback，不影响前 2 次正常路径；如果 HTTP/1.1 也失败，结果与之前一样 | Tester |
| 过多的 fetch attempt 让升级总时长增加至 ~15 分钟（300s×3 + 7s backoff） | 正常场景仅 1 次 attempt（~5 分钟）；瞬态场景增加至 ~15 分钟，但比重新完整升级（~20 分钟 + 备份/merge/install）快 | Pascal/Operator |
| branch-aware protect 函数被误用于 detached HEAD | `state.branch` 为 None/"" 时，skip push | Developer |
| `build_fetch_command` 需要确认 target 是否为 tag | 实现使用简单启发式：target 含 `v` 或 `V` 开头 + 数字 → tag path；无效 tag fetch 将在 attempt 1 后由 classifier 处理 | Developer/Closeout |

未解决问题：
- `build_fetch_command` 中，是否使用正则还是简单 `target.startswith(("v", "V")) and any(ch.isdigit() for ch in target)` 来判定 tag？本 SPEC 不做硬性限制，由 Design 和 Implement 阶段决定最小可实现方案。Tester 需验证 tag 和非 tag 两路径。
- 如果用户自定义 remote 名不是 `upstream`/`origin` 而是 `upsteam` 拼写错误，fetch 依然失败。这个问题不解决，因为拼写错误属于 operator 错误，不应被 retry 掩盖。
