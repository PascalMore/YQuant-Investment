# SPEC-10-008：通用多 submodule 升级器 update_submodules.py

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-07-09 |
| 来源 RFC | RFC-10-008-update-submodules-script (V2.0) |
| 关联 Design | DESIGN-10-008-update-submodules-script |
| 目标模块 | 10_infra / git submodule 运维自动化 |
| Full Flow | T1_redo=t_91ffdfe3（重写为 auto-discovery + opt-in） |

## 1. 需求摘要

本 SPEC 将 RFC-10-008 V2.0 的 **auto-discovery + opt-in override** 多 submodule 升级器落为可执行、可测试的工程契约。脚本 `scripts/upgrade/update_submodules.py` 对 yquant-investment 下任意 git submodule 执行 5 阶段流水线（fetch → merge → install → restart → push），**默认无需任何中央配置文件**；submodule 列表从 `.gitmodules` 解析，其余字段由启发式自动推断；每个 submodule 仓库根目录的 `.update_submodules.yaml` 可覆盖默认（opt-in）。默认 dry-run 安全模式。

## 2. 范围

### 2.1 In Scope

- 新增 `scripts/upgrade/update_submodules.py`，标准库实现，不引入新依赖。
- 新增 `tests/scripts/test_update_submodules.py`，覆盖 .gitmodules 解析、启发式发现、opt-in override 加载、5 阶段逻辑、CLI 参数、dry-run 行为。
- 三层文档 RFC/SPEC/Design-10-008（V2.0 已重写）。
- **不**新增 `data/submodules.yaml`（V1.0 取消）；opt-in `.update_submodules.yaml` 由各 submodule 仓库自行决定是否提供。

### 2.2 Out of Scope

- 不修改 `.gitmodules`。
- 不修改 systemd unit 文件。
- 不修改 submodule 内部任何文件（业务代码、requirements.txt、.env、配置）。
- 不执行真实 restart / push 作为 T3 Verify 默认动作（除非显式批准）。
- 不自动 cherry-pick / rebase / drop fork 私有 commit。
- 不新增第三方依赖；PyYAML optional，必须有 stdlib fallback。
- 不 import `upgrade_hermes_agent.py`（避免耦合；复制必要的 helper）。
- **不**自动 `git remote add upstream`（V2.0 关键决策；upstream 缺失即报错退出）。
- **不**在 yquant-investment 仓库下维护任何中央 submodule 配置（V1.0 `data/submodules.yaml` 已取消）。

## 3. auto-discovery 字段来源 + opt-in override schema

### 3.1 auto-discovery 字段来源

submodule 列表从项目根 `.gitmodules` 解析。每个 submodule 的字段按 RFC §4 表确定：

| 字段 | 启发式默认 | opt-in 覆盖 | 覆盖规则 |
|---|---|---|---|
| `name` | `.gitmodules` section 名 | — | 不可覆盖 |
| `path` | `.gitmodules` `path = ...` | — | 不可覆盖 |
| `origin` | `git -C <path> remote get-url origin` | `origin: <url>` | 字符串覆盖 |
| `upstream` | `git -C <path> remote get-url upstream`（**缺失→报错退出**，不回落 origin） | `upstream: <url>` | 字符串覆盖 |
| `branch` | 远端 HEAD（fallback `main`） | `branch: <name>` | 字符串覆盖 |
| `venv` | `<path>/.venv` 存在 → `.venv`；否则 None（跳过 install） | `venv: <rel-path-or-null>` | 字符串覆盖；null 跳过 install |
| `pip_install_cmd` | `<path>/requirements.txt` 存在 → `["install", "-r", "requirements.txt"]`；否则 None（跳过 install） | `pip_install: [...]` 或 null | list 覆盖；null 跳过 install |
| `pre_merge_hooks` | `[]` | `pre_merge_hooks: [...]` | list 替换 |
| `systemd_service` | `systemctl --user list-units` 模糊匹配 `<path>` 段；无 → None | `systemd_service: <name-or-null>` | 字符串覆盖；null 跳过 restart |
| `health_check` | **None**（默认不检查） | `health_check: <shell-cmd-string>` | **字符串覆盖**（shell 命令；非空时 Phase 4 后执行） |
| `skip_push` | `false` | `skip_push: true` | 布尔覆盖（极少用） |
| `notes` | `""` | `notes: <text>` | 字符串覆盖 |

### 3.2 opt-in `.update_submodules.yaml` 完整 schema

**位置**：submodule 仓库根目录下，文件名 `.update_submodules.yaml`。**不存在是常态**；存在则按以下 schema 解析并覆盖该 submodule 的所有启发式字段。

```yaml
# 所在位置：<submodule-repo-root>/.update_submodules.yaml
# 所有字段均可选；未列出的字段沿用启发式默认
schema_version: 1          # int，必填，当前 1
origin: <string>           # 覆盖 origin remote URL
upstream: <string>         # 覆盖 upstream remote URL（仅覆盖配置值，不触发自动 git remote add）
branch: <string>           # 覆盖跟踪分支
venv: <string|null>        # 覆盖 venv 相对路径；null 跳过 install
pip_install:               # 覆盖 pip install 参数（不含 "install" 前缀）
  - "-r"
  - "requirements.txt"
pre_merge_hooks:           # merge 前执行命令（cwd = submodule 根）
  - "git stash push -u -m pre-update"
systemd_service: <string|null>  # 覆盖 systemd service；null 跳过 restart
health_check: <string|null>     # shell 命令字符串；非空时 Phase 4 后执行，exit!=0 abort push
skip_push: false                # 极少用；默认仍走 --push 开关
notes: <string>                 # Pascal 备注
```

### 3.3 opt-in 字段约束

| 字段 | 类型 | 校验规则 | 缺失/错误行为 |
|---|---|---|---|
| `schema_version` | int/string | 可转为 int；接受 "1" 或 1 | warning 跳过整个 override |
| `origin` | string | 合法 git URL | 保留启发式 |
| `upstream` | string | 合法 git URL | 保留启发式（**不触发自动 git remote add**） |
| `branch` | string | 合法 git ref | 保留启发式 |
| `venv` | string/null | 相对路径或 null | 保留启发式 |
| `pip_install` | list/null | list 元素是字符串 | 保留启发式 |
| `pre_merge_hooks` | list[string] | 可为空 | 保留启发式 |
| `systemd_service` | string/null | 合法 unit 名 | 保留启发式 |
| `health_check` | string/null | shell 命令字符串 | 保留启发式（None） |
| `skip_push` | bool | true/false | 保留启发式（false） |
| `notes` | string | 任意 | 保留启发式 |

> **V2.0 与 V1.1 schema 差异**：
> - `health_check`：V1.1 是 `{type, timeout, url?}` dict；V2.0 改为 **shell 命令字符串**（更灵活，不预设检查方式）。
> - 移除 `systemd_scope`、`restart_cmd`（V1.1 字段）——systemd 固定 `--user`；如需自定义 restart，用 `pre_merge_hooks` 或后续增强。
> - 新增 `skip_push`（opt-in 级别跳过 push，极少用）。

## 4. CLI 完整参数

```text
python3 scripts/upgrade/update_submodules.py [OPTIONS]
```

| 参数 | 类型 | 默认 | 行为 |
|---|---|---|---|
| `--only NAME` | string (action="append"，可多次) | 全部 | 只处理指定 name 的 submodule；**缺名报错 exit 1（不静默 fallback）** |
| `--push` | flag | false | 启用 Phase 5 push（默认不 push） |
| `--apply` | flag | false | 实际执行（默认 dry-run）。不带 `--apply` 时永远只输出计划 |
| `--dry-run` | flag | true（隐式） | 显式 dry-run（与不带 `--apply` 等价） |
| `--skip-merge` | flag | false | 跳过 Phase 2（merge），直接从 install 开始 |
| `--skip-install` | flag | false | 跳过 Phase 3（install） |
| `--skip-restart` | flag | false | 跳过 Phase 4（restart） |
| `--resume-after-merge` | flag | false | 跳过 Phase 1+2（fetch+merge），从 install 开始 |
| `--fail-fast` | flag | false | 任一 submodule 失败时立即停止 |
| `--verbose` | flag | false | 输出每条命令的 stdout/stderr |
| `--no-audit` | flag | false | 不写审计日志文件 |

### 4.1 `--only NAME` 匹配语义

`.gitmodules` 的 section 名是 path-based（如 `skills/research/daily_stock_analysis`），而用户习惯用短名（`daily_stock_analysis`）。匹配规则：

1. **精确匹配** section name：`--only skills/research/daily_stock_analysis` → 匹配。
2. **path basename 后缀匹配**：`--only daily_stock_analysis` → 匹配 path `skills/research/daily_stock_analysis`（basename 一致）。
3. **大小写敏感**（与 `.gitmodules` 一致）。
4. **缺名报错 exit 1**：`--only nonexistent` → 报错退出，**不静默 fallback 到全部**。

### 4.2 safety 护栏

- `--apply` 与 `--dry-run` 互斥（同时传则报错 exit 2）。
- `--apply` 与 `--push` 同时使用才真正 push；`--apply` 不带 `--push` 时只到 Phase 4。
- `--force` 不存在（不接受任何 force 参数）。
- `--skip-merge` 与 `--resume-after-merge` 互斥（同时传报错 exit 2）。
- `--only NAME` 缺名时 exit 1 报错（不静默 fallback）。
- `--only` 用 `action="append"` 支持多次：`--only foo --only bar` 处理 foo + bar。

## 5. 5 阶段命令模板

每个阶段对每个 submodule 串行执行。cwd 均为 submodule 根目录（已由 `path` 解析到绝对路径）。

### 5.1 Phase 1: FETCH

```text
git fetch upstream <branch>
git rev-list --left-right --count upstream/<branch>...HEAD
```

输出：behind count（upstream 领先）和 ahead count（fork 领先）。

决策：
- behind == 0：跳过 Phase 2（merge），直接到 Phase 3（install）。原因：upstream 无新 commit，无需 merge。
- behind > 0：进入 Phase 2。

错误处理：
- `git fetch` 失败（网络/upstream URL 错）：warning 跳过该 submodule，不阻塞其他 submodule。
- **upstream remote 不存在**：**报清晰错误退出该 submodule**（不自动 `git remote add`，不回落 origin）。错误信息提示人工 add 或 opt-in 配置。见 RFC §4.1。

### 5.2 Phase 2: MERGE

```text
ahead == 0: git merge --ff-only upstream/<branch>
ahead > 0:  git merge upstream/<branch>
```

决策与错误处理：
- `--ff-only` 成功：记录 fast-forward SHA。
- merge 成功（merge commit）：记录 merge commit SHA。
- merge 冲突（exit != 0 且 stderr 含 conflict）：
  1. `git merge --abort`（清理冲突状态）
  2. 记录 pre-merge HEAD SHA
  3. ABORT 该 submodule 后续阶段
  4. 输出报告："merge 冲突，已 abort，请手动解决后 --resume-after-merge"
  5. 不阻塞其他 submodule

`pre_merge_hooks`：
- 在 merge 前执行。典型用途：stash dirty worktree。
- 每个命令 cwd=submodule 根，exit != 0 则 warning 但不 abort（hooks 失败不阻塞 merge）。

### 5.3 Phase 3: INSTALL

```text
<venv>/bin/pip install <pip_install args>
```

例如：
```text
.venv/bin/pip install -r requirements.txt
```

错误处理：
- pip exit != 0：ABORT 该 submodule 后续阶段（不 restart，不 push）。
- venv 不存在或 pip_install 为 None：SKIP 整个 Phase 3（不是 abort，是 skip；继续 restart/push 阶段）。
- dry-run：输出计划命令，不执行。

### 5.4 Phase 4: RESTART

```text
systemd_service != null:
  systemctl --user restart <service>

systemd_service == null:
  跳过 restart 阶段
```

health_check（restart 后，仅当 opt-in 提供 cmd 时）：
```text
health_check != null:
  sh -c <health_check cmd>
  exit 0 → PASS
  exit != 0 → FAIL → ABORT push

health_check == null:
  跳过（V2.0 默认行为）
```

错误处理：
- restart 命令 exit != 0：ABORT，不 push。
- health_check FAIL：ABORT，不 push。输出 "服务重启但 health check 失败，请人工检查"。
- dry-run：输出计划命令，不执行。

### 5.5 Phase 5: PUSH

仅当 `--push` 启用、`skip_push` 未设为 true、且前面全 PASS。

```text
git push origin <branch>
```

安全护栏：
- **永远不 `--force`**。即使 push 失败（non-fast-forward），也只报告，不自动 force。
- push 失败：报告但不 rollback（代码已 merge+install+restart，rollback 也有风险）。
- dry-run：输出计划命令，不执行。

### 5.6 跨阶段 ABORT 规则

| 触发 ABORT 的阶段 | ABORT 范围 | 是否阻塞其他 submodule |
|---|---|---|
| Phase 1 fetch 失败 | 该 submodule Phase 2-5 全跳过 | 否（除非 `--fail-fast`） |
| Phase 1 upstream 缺失 | 该 submodule Phase 2-5 全跳过 | 否 |
| Phase 2 merge 冲突 | 该 submodule Phase 3-5 全跳过 | 否 |
| Phase 3 pip 失败 | 该 submodule Phase 4-5 全跳过 | 否 |
| Phase 4 restart/health 失败 | 该 submodule Phase 5 跳过 | 否 |
| Phase 5 push 失败 | 仅该 push 失败 | 否 |

## 6. 关键算法

### 6.1 .gitmodules 解析

```text
# 解析 .gitmodules 得到 [(name, path), ...]
# .gitmodules 格式：每个 [submodule "<name>"] section 含 path = <rel-path>
# name = section 名（如 "skills/research/daily_stock_analysis"）
```

### 6.2 启发式字段推断

```text
def discover_submodule(name, path, project_root):
    config = SubmoduleConfig(name=name, path=path)
    config.origin = run_cmd(["git", "-C", path, "remote", "get-url", "origin"]).stdout.strip()
    # upstream：缺失=报错退出（不回落 origin）
    upstream_result = run_cmd(["git", "-C", path, "remote", "get-url", "upstream"])
    if upstream_result.exit_code != 0 or not upstream_result.stdout.strip():
        config.upstream = None  # 标记缺失，后续 Phase 1 报错
    else:
        config.upstream = upstream_result.stdout.strip()
    config.branch = parse_origin_head(path) or "main"
    config.venv = ".venv" if (path / ".venv").exists() else None
    config.pip_install_cmd = ["install", "-r", "requirements.txt"] if (path / "requirements.txt").exists() else None
    config.systemd_service = match_systemd_unit(path)  # 模糊匹配 path 段
    config.health_check = None  # V2.0 默认 None
    config.skip_push = False
    config.notes = ""
    return config
```

### 6.3 opt-in override 加载

```text
override_path = path / ".update_submodules.yaml"
if override_path.exists():
    try:
        raw = load_yaml(override_path)
        validated = validate_override(raw)
        config = merge_override(config, validated)  # 每个字段独立合并
    except Exception as e:
        log_warn(f".update_submodules.yaml 加载失败: {e}, 沿用启发式")
```

### 6.4 merge 冲突检测

```text
merge_result = run_cmd(["git", "merge", merge_ref], cwd=submodule_path)
if merge_result.exit_code != 0:
    status = run_cmd(["git", "status", "--porcelain"], cwd=submodule_path)
    has_conflict = any line in status.stdout starts with "UU" or "AA" or "DD"
    if has_conflict:
        run_cmd(["git", "merge", "--abort"], cwd=submodule_path)
        abort_this_submodule(reason="merge_conflict", pre_merge_head=pre_head)
    else:
        abort_this_submodule(reason="merge_error", stderr=merge_result.stderr)
```

### 6.5 behind/ahead 0/0 自动跳过 merge

```text
behind, ahead = parse_rev_list_count(revlist_result.stdout)
if behind == 0:
    log("behind=0, skip merge phase")
    skip_phase_2 = True
else:
    skip_phase_2 = False
```

### 6.6 health_check（opt-in 提供 cmd 时）

```text
restart_result = do_restart(...)
if restart_result.exit_code != 0:
    abort(phase=4, reason="restart_failed")
    return

if config.health_check:  # V2.0：None 时跳过
    hc_result = run_cmd(["sh", "-c", config.health_check], cwd=submodule_path)
    if hc_result.exit_code != 0:
        abort(phase=4, reason="health_check_failed", stderr=hc_result.stderr)
        return
# only reach here if restart + health PASS → proceed to push
```

### 6.7 upstream remote 缺失（V2.0 关键算法）

```text
if config.upstream is None:
    # V2.0：报清晰错误退出，不自动 add
    log_err(
        f'submodule "{name}" 缺少 upstream remote.\n'
        f'  当前 remotes: {list_remotes(path)}\n'
        f'  请手动执行: git -C {path} remote add upstream <upstream-url>\n'
        f'  或在 {path}/.update_submodules.yaml 中声明 upstream URL'
    )
    abort_this_submodule(reason="upstream_missing")
    return
```

## 7. audit 日志格式

路径：`/tmp/update_submodules_audit_<YYYYMMDD_HHMMSS>.md`

格式（Markdown）：

```markdown
# update_submodules audit <timestamp>

## Config
- mode: dry-run / apply
- push: enabled / disabled
- only: [name1, name2] / null
- skip_merge: true / false
- skip_install: true / false
- skip_restart: true / false
- fail_fast: true / false

## Summary
| submodule | config_source | fetch | merge | install | restart | push | result |
|---|---|---|---|---|---|---|---|
| daily-stock-analysis | heuristic | OK | SKIP(behind=0) | OK | OK | SKIP | PASS |
| tradingagents-cn | heuristic | ERROR(upstream_missing) | SKIP | SKIP | SKIP | SKIP | FAIL |

## Details

### daily-stock-analysis (skills/research/daily_stock_analysis)
- Config: origin=git@github.com:PascalMore/... | upstream=https://github.com/ZhuLinsen/... | venv=.venv | systemd=daily-stock-analysis.service | health_check=None
- Phase 1 FETCH: `git fetch upstream main` → exit 0 (2.3s)
  - behind=0, ahead=203
- Phase 2 MERGE: SKIPPED (behind=0)
- Phase 3 INSTALL: `.venv/bin/pip install -r requirements.txt` → exit 0 (15.2s)
- Phase 4 RESTART: `systemctl --user restart daily-stock-analysis.service` → exit 0
  - health_check: SKIPPED (None)
- Phase 5 PUSH: SKIPPED (--push not enabled)
- RESULT: PASS
```

## 8. 验收标准

| 编号 | 验收项 | 验证方式 |
|---|---|---|
| A-001 | 三层文档存在且交叉引用正确 | `test -f` + grep RFC/SPEC/DESIGN-10-008 |
| A-002 | **不**存在 `data/submodules.yaml`（V1.0 取消） | `test ! -f data/submodules.yaml` |
| A-003 | `--help` 显示全部 CLI 参数（含 `--only` 可重复、`--skip-install`） | 执行 help |
| A-004 | `--dry-run`（默认）从 `.gitmodules` 解析 + 启发式推断，不修改任何 repo/venv/systemd/origin | dry-run 后 git status 干净 |
| A-005 | `--dry-run` 输出每个 submodule 的 5 阶段计划 | stdout 检查 |
| A-006 | `--apply` 不带 `--push` 时执行到 Phase 4 但不 push | git log origin 无变化 |
| A-007 | behind=0 自动跳过 merge 阶段 | dry-run 输出 SKIP |
| A-008 | merge 冲突时 `git merge --abort` + 报告 | mock/temp repo |
| A-009 | pip install 失败时 abort restart+push | mock |
| A-010 | health_check 失败时 abort push（opt-in 提供 cmd 时） | mock |
| A-011 | 永远不 --force push | 代码审查 + 测试 |
| A-012 | `--only NAME` 只处理指定 submodule（可多次 `action="append"`） | dry-run 输出 |
| A-013 | `--only` 缺名报错 exit 1 | CLI 测试 |
| A-014 | `--apply` 与 `--dry-run` 互斥报错 exit 2 | CLI 测试 |
| A-015 | audit 日志文件生成 | 检查 /tmp/ |
| A-016 | 不新增依赖 | git diff dependency files |
| A-017 | 不触碰禁止文件（submodule 内部、systemd unit、业务代码、.gitmodules） | git diff --name-only |
| A-018 | opt-in `.update_submodules.yaml` 覆盖字段成功（含 health_check shell cmd） | 单元测试 + 集成测试 |
| A-019 | opt-in 加载失败时回落启发式 | mock YAML 错误 |
| A-020 | 启发式推断 systemd_service 模糊匹配正确 | 单元测试 |
| A-021 | **upstream remote 缺失时报清晰错误退出该 submodule，不自动 add** | mock/temp repo |
| A-022 | **health_check 默认 None（无 opt-in 时不执行）** | dry-run 输出 health_check=None |

## 9. 测试要求

| 编号 | 类型 | 命令/方法 | 断言 |
|---|---|---|---|
| UT-001 | CLI help | `--help` | 输出含 `--only` (可重复), `--push`, `--apply`, `--dry-run`, `--skip-merge`, `--skip-install`, `--skip-restart`, `--resume-after-merge` |
| UT-002 | .gitmodules 解析 | 含 2 个 submodule 的 fixture | 返回 2 个 SubmoduleConfig，name 正确 |
| UT-003 | 启发式 venv 推断 | fixture 含/不含 `.venv` | 推断正确 |
| UT-004 | 启发式 pip_install 推断 | fixture 含/不含 `requirements.txt` | 推断正确 |
| UT-005 | 启发式 systemd 推断 | mock systemctl list-units | 模糊匹配 path 段正确 |
| UT-006 | opt-in 覆盖 venv | fixture 含 `.update_submodules.yaml` | override 生效 |
| UT-007 | opt-in 加载失败回落 | fixture YAML 格式错 | warning + 沿用启发式 |
| UT-008 | behind=0 跳过 merge | mock rev-list 返回 "0\t203" | Phase 2 SKIP |
| UT-009 | merge 冲突 abort | temp repo 制造冲突 | `git merge --abort` 被调用，result=FAIL |
| UT-010 | pip 失败 abort | mock pip exit 1 | Phase 4-5 ABORTED |
| UT-011 | health_check FAIL abort push | opt-in 提供 health_check cmd，mock exit 1 | Phase 5 ABORTED |
| UT-012 | health_check None 跳过 | 无 opt-in | Phase 4 health_check SKIP |
| UT-013 | `--only` 过滤（短名） | `--only daily-stock-analysis` | 只处理 1 个 submodule |
| UT-014 | `--only` 多次 | `--only foo --only bar` | 处理 foo + bar |
| UT-015 | `--only` 缺名报错 | `--only nonexistent` | exit 1 |
| UT-016 | dry-run no mutation | dry-run 前后 git status | 无变化 |
| UT-017 | `--apply` + `--dry-run` 互斥 | 同时传 | exit 2 |
| UT-018 | **upstream 缺失报错** | temp repo 无 upstream remote | ABORT 该 submodule，不自动 add，错误信息含 `git remote add` 提示 |
| UT-019 | audit 日志生成 | dry-run | `/tmp/update_submodules_audit_*.md` 存在 |

T3 Verify 必须执行：

```bash
cd /home/pascal/workspace/yquant-investment
python3 -m py_compile scripts/upgrade/update_submodules.py
python3 -m pytest tests/scripts/test_update_submodules.py -v
python3 scripts/upgrade/update_submodules.py --help
python3 scripts/upgrade/update_submodules.py --dry-run
python3 scripts/upgrade/update_submodules.py --dry-run --only daily-stock-analysis
python3 scripts/upgrade/update_submodules.py --dry-run --only nonexistent  # 期望 exit 1
```

## 10. 风险与未解决问题

| 风险 | 缓解 | 归属 |
|---|---|---|
| merge 冲突频繁（daily-stock-analysis fork 领先 200+） | 自动 abort + 报告，不自动 resolve | Developer/Reviewer |
| pip 破坏性变更导致 venv 损坏 | install 后 restart；opt-in health_check 可捕获 | Tester/Closeout |
| 启发式 systemd 模糊匹配误中 | dry-run 输出推断结果供审查；opt-in override 可改 | Developer |
| 启发式 branch 推断失败 | fallback `main`；opt-in override 可改 | Developer |
| PyYAML 不可用 | stdlib fallback（复用 V2 `_load_yaml_subset` 模式） | Developer |
| health_check 默认 None 导致服务异常未被发现 | Pascal 按需通过 opt-in 配置 health_check cmd | Closeout 记录残余风险 |

未解决问题：
- `--resume-after-merge` 是否需要 checkpoint 文件：V1 可简单实现为"跳过 fetch+merge"。
- 启发式 systemd 匹配算法的"最长 path 段 match"是否足够：T3 可加更多 fixture 验证。
- `--only` 匹配是否需要支持 glob（如 `--only daily_*`）：V2.0 不支持，留后续。
