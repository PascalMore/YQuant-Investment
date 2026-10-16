# SPEC-10-008：通用多 submodule 升级器 update_submodules.py

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-10-16 |
| 版本号 | V2.1（分支映射契约修订，非脚本发布号） |
| 来源 RFC | [RFC-10-008 V2.1](../../rfc/10_infra/RFC-10-008-update-submodules-script.md) |
| 关联 Design | [DESIGN-10-008](../../design/10_infra/DESIGN-10-008-update-submodules-script.md)（本次待 T2 修订） |
| 目标模块 | 10_infra / git submodule 运维自动化 |
| Full Flow | 本次 T1=t_5c700339 → T2=t_12bc9198；历史 T1_redo=t_91ffdfe3（auto-discovery + opt-in） |

## 版本记录

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V2.0 | 2026-07-09 | auto-discovery + opt-in 基础契约；历史单分支模式 | YQuant-Codex-Principal |
| V2.1 | 2026-10-16 | t_5c700339：双分支、legacy 优先级、ref 规范化、unknown/fail、目标校验、resume/skip 与 A-BM 验收；未实现，待 T2 Design | YQuant-Codex-Principal |

## 0. 适用优先级与交付边界

本次仅修订来源/目标分支契约。§3.4–§3.8、§8.1 优先于历史单分支算法/示例；非分支行为仍按本文和 SPEC-10-012 执行。关联 DESIGN-10-008 尚待独立 T2 同步，不能用其旧单 branch 模板覆盖本次契约。

已完成的 OctoBot 源码接入与 v2.2.0 install_exclude/诊断不是待实现功能；只修复分支映射与来源计数假通过，不增加 CLI、中央 manifest、第三方依赖或发布步骤。本卡不写 Design/代码。历史 §2.1 的“新增脚本/测试”是原始交付记录，本轮是增量修订；不得据此重复创建升级器或扩大范围。

## 1. 需求摘要

本 SPEC 将 RFC-10-008 的 **auto-discovery + opt-in override** 多 submodule 升级器落为可执行、可测试的工程契约。脚本 `scripts/upgrade/update_submodules.py` 对 yquant-investment 下任意 git submodule 执行 5 阶段流水线（fetch → merge → install → restart → push），**默认无需任何中央配置文件**；submodule 列表从 `.gitmodules` 解析，其余字段由启发式自动推断；每个 submodule 仓库根目录的 `.update_submodules.yaml` 可覆盖默认（opt-in）。默认 dry-run 安全模式。V2.1 独立表达 upstream 来源与本地/origin 目标，保留旧 branch 配置语义，不将来源查询失败当作 0/0。

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
| `branch` | `.gitmodules branch` → 当前子仓分支 → origin HEAD → `main` | `branch: <name>` | 本地/origin 目标；显式旧配置给来源同名兜底（§3.5） |
| `upstream_branch` | 独立 upstream 默认发现（§3.5） | `upstream_branch: <name>` | 来源；不改变目标；优先于旧 branch 来源兜底 |
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
branch: <string>           # 本地/origin 目标；未设 upstream_branch 时保留旧同名来源
upstream_branch: <string>  # 可选来源覆盖；例 branch: main + upstream_branch: master
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
| `branch` | string | 非空合法分支名，允许 §3.6 的 origin/heads 表示 | 缺失按 §3.5；显式非法按 §3.6 失败 |
| `upstream_branch` | string | 非空合法分支名，允许 §3.6 的 upstream/heads 表示 | 缺失按 §3.5；显式非法按 §3.6 失败 |
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

### 3.4 分支实体与兼容语义（V2.1）

| 项目 | 含义 | 不变量 |
|---|---|---|
| `branch` | 目标本地分支，也是 origin 目标分支 | fetch/merge 不再无条件读取它；push 只推该分支 |
| `upstream_branch` | 来源分支，规范化后不含 remote 前缀 | fetch 来源为 upstream 的该分支；merge/比较绑定其对应来源提交 |
| 当前 HEAD 分支 | 子仓实际检出的本地分支 | 必须是符号分支且精确等于 branch；不自动切换 |
| 来源比较 | 来源相对当前 HEAD 的 behind/ahead | 两个非负整数且命令成功才可信；未知不是零 |

旧 opt-in 文件无须迁移：仅显式 `branch: develop` 时，两端仍为 develop；仅显式 `branch: origin/main` 时，规范化为 main，两端仍为 main。这是 legacy 兼容，不会自动改为 upstream 默认。需要异名且显式设目标时，可额外写 `upstream_branch: master`（来源 master、目标 main）；新增字段仍在 schema_version 1 内，不新增配置文件或 schema 版本。未设 branch、只设 upstream_branch 时目标继续自动发现。配置声明须在发现/覆盖链路中保留“是否显式提供 branch”的语义，不能把自动算出的 branch 误作 legacy 显式来源。

### 3.5 发现与覆盖优先级

目标从高到低选择首个可用值：

1. 有效 opt-in `branch`。
2. 主仓 `.gitmodules` 中该 submodule section 的 `branch`（按 section 身份而非 basename 读取）；该值是 fork 更新目标，不是 upstream 来源。值为 `.` 时解析为主仓当前符号分支；主仓 detached/查询失败则该 submodule 失败，不 fallback。字段缺失才进入下一优先级；显式空值、非法 ref 或读取错误应诊断失败，不静默当作未配置。
3. 子仓当前检出的本地符号分支；不把 detached 的 SHA 当分支名。
4. cached origin HEAD 规范化后的分支。
5. 历史目标兜底 main。此兜底只是候选，不能创建分支；仍须通过 §3.7。

来源独立从高到低选择：

1. 有效 opt-in `upstream_branch`。
2. 若 opt-in 显式提供有效 `branch`，用规范化后的 legacy branch 值（同名兼容）。
3. cached upstream HEAD 指向的分支。
4. 只读查询 upstream 远端 HEAD 得到的分支（允许 remote show 或等价只读查询；不能 fetch/set-head）。
5. 若上两项未得到可用名称，依次探测已有 upstream/main、upstream/develop、upstream/master 的 commit ref，取首个存在者；查询失败须有诊断，使用缓存时标明证据为缓存。
6. 均不可用：来源 unresolved，该 submodule fail。不得盲猜 main，不回落 origin/目标；显式来源不存在时也不静默改选其他来源。

“可用名称”须通过 §3.6；远端返回 `(unknown)`、HEAD、空值不算分支。cached HEAD 可解析到名称但其 commit 缓存缺失时不另选分支：apply 对该来源 fetch，dry-run 按 §3.8 报 unknown。来源选择不受 `.gitmodules branch` 或子仓当前分支影响（显式 legacy branch 兼容除外）。日志须能识别最终来源、目标及来源是显式/默认/缓存，不强制新增审计表或输出格式。

### 3.6 输入规范化边界

- 目标 branch 接受裸分支名（main、feature/x）、`refs/heads/<name>`、`origin/<name>`、`refs/remotes/origin/<name>`；只剥离完整且匹配角色的一个前缀。来源 upstream_branch 对应接受裸名、`refs/heads/<name>`、`upstream/<name>`、`refs/remotes/upstream/<name>`。
- 旧 branch 的 origin 前缀先按目标角色规范化，再将裸名作为 legacy 来源兜底；不把 `origin/main` 原样传给 upstream fetch。自动发现得到的 ref 也须按所属 remote 规范化，不能把 upstream/master 用作目标。
- 保留分支路径全部层级：origin/feature/x → feature/x；不按最后一个 `/` 截取。普通 feature/x 不作 remote 前缀处理。不支持把任意 remote 前缀当别名：目标中的 upstream/main、来源中的 origin/main、完整 refs/remotes 下其他 remote、refs/tags/... 均拒绝；origin/upstream 在本接口是保留 remote 命名空间。
- 去除输入外层空白后必须非空且为合法本地分支名；HEAD、空 suffix、以 `-` 开头、非法 ref 表达式（如 main..x、main~1、通配符）失败。HEAD 不作为本地分支目标；禁止把 SHA 当来源提交覆盖。不得静默清洗内部字符或修复错误名称。
- 可解析 opt-in 中显式给出 branch/upstream_branch 但值为 null、空串、非字符串、错误 remote 或非法 ref：该 submodule fail，指出字段/原因，不按“字段缺失”忽略。这是仅对两项分支选择输入的必要窄化；文件本身无法加载/schema 失败仍保留既有 warning+启发式回落，其他字段规则不变。无需安装依赖或写 Git config 即可校验。

### 3.7 目标一致性、跳过与恢复

- 所有模式在任何 fetch/merge/hook/install/restart/push 写操作前，确认目标本地分支存在且当前符号 HEAD 精确等于 branch。detached、HEAD 读取失败、目标缺失或不匹配：该 submodule fail/CLI exit 1，诊断含目标和当前状态；Git refs/HEAD/index/worktree/配置及远端均不变化。
- 不 checkout/switch、reset、创建/重建本地分支、不建立 detached HEAD；`--force-dirty` 仅保留既有 dirty 许可，不能绕过本条。apply 的既有 dirty-worktree 检查仍保留。
- `--skip-merge`：仍 fetch/检查来源比较，只跳过 merge；fetch/ref/计数失败仍停止后续阶段，不借 skip 规避错误。`--skip-install`/`--skip-restart` 保留原跳过行为，不改变两端映射。
- `--resume-after-merge`：继续表示人为完成 merge 后跳过 fetch+merge，从 install 开始；不要求证明 upstream 已合入、不新增 checkpoint。仍核验目标一致性；无需为跳过的 fetch/merge 强制查询来源或要求缓存，不报告 behind=0/最新。若 push 启用，仍只推目标 branch。显式分支输入非法仍失败，resume 不能绕过输入错误。
- push 仅在原有 `--push` 且未被前序失败中止、且非 skip_push 时启用；不 force，不推来源同名分支。执行 push 前须确保 HEAD 仍在目标（包括 hook 后）；执行 merge 前同样不得合入已被 hook 切换的错误分支。检查失败中止，不自动恢复外部/hook 已改变的状态。

### 3.8 来源 ref、未知比较与只读 dry-run

| 场景 | 必须行为 | 后续阶段/状态 |
|---|---|---|
| apply fetch 成功且本轮来源 commit、计数可用 | 来源为 upstream_branch，比较本轮实际取得的 commit 与 HEAD；不得把 fetch 前旧缓存当最新 | 已知 behind=0 才跳 merge；其余原 merge 策略不变 |
| apply fetch 失败、来源不可解析、rev-list 非零或计数非法 | 明确 fail；不得将空输出/解析错误转成 0/0 | 停止该 submodule 后续阶段，CLI exit 1；不影响其他项，除非 fail-fast |
| dry-run 来源 commit 缓存与计数均可用 | 不执行 fetch；显示 source/target、behind/ahead，注明 cached/not fetched | 可给出原有五阶段计划；仅为计划 PASS，不证明远端最新 |
| dry-run 缺 commit 缓存、rev-list 失败、计数非法或来源未解析 | detail 明确 unknown/无法判定与原因；数值不伪造为 0 | fetch phase fail、overall fail、CLI exit 1；merge/install/restart/push 不作为可执行通过计划，停止该 submodule |
| resume 跳过来源阶段 | fetch/merge 为 skip，比较未执行 | 不能声称 up-to-date，允许按 §3.7 继续 |

有效计数必须恰为两个非负整数。cached ref 不是网络最新证据；远端 HEAD 查询成功也不等于本地已有该来源 commit。apply 获取来源后若默认 refspec 不更新 remote-tracking ref，仍必须比较/合入本轮实际 fetch 的来源提交，不能沿用陈旧引用；具体 Git ref 实现交 Design。

dry-run 禁止 fetch/merge/push/checkout/reset、remote set-head/add、写 Git config/refs/index/FETCH_HEAD 或执行 pre_merge_hooks/pip/restart/health_check；只读远端查询可用，但查询失败必须可见且不得伪造新鲜状态。默认审计日志为既有例外（位于 repo 外），传 `--no-audit` 时本次 CLI 不产生审计文件。不能只靠 git status 断言零副作用，后续验证应比较 Git 状态与缓存/配置/远端 refs。

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
git fetch upstream <upstream_branch>
git rev-list --left-right --count upstream/<upstream_branch>...HEAD
```

输出：behind count（upstream 领先）和 ahead count（fork 领先）。此处为逻辑命令模板；本轮 fetch 的实际来源绑定与失败/unknown 行为按 §3.8，不能因该模板读到旧缓存。

决策：
- behind == 0：跳过 Phase 2（merge），直接到 Phase 3（install）。原因：upstream 无新 commit，无需 merge。
- behind > 0：进入 Phase 2。

错误处理：
- `git fetch` 失败（网络/upstream URL 错）：warning 跳过该 submodule，不阻塞其他 submodule。
- **upstream remote 不存在**：**报清晰错误退出该 submodule**（不自动 `git remote add`，不回落 origin）。错误信息提示人工 add 或 opt-in 配置。见 RFC §4.1。

### 5.2 Phase 2: MERGE

```text
ahead == 0: git merge --ff-only upstream/<upstream_branch>
ahead > 0:  git merge upstream/<upstream_branch>
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

以下为 V2.0 历史非分支推断参考；其中 parse_origin_head 单字段分支行已被 §3.4–§3.6 取代，不是本次实现方案。函数级设计留给 T2。

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

本规则仅用于 §3.8 定义的成功且合法的已知计数；解析失败/缓存缺失不得进入下方的 behind=0 分支。

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

### 8.1 本次分支映射验收矩阵（A-BM）

本矩阵是后续 Implement/独立 Verify 的验收输入，不表示本卡已运行功能测试。

| 编号 | Given/When | Then（必要断言） |
|---|---|---|
| A-BM-001 | 无 opt-in，upstream main、本地 main、origin main | 来源 main、目标 main；原同名五阶段语义保留 |
| A-BM-002 | 无 opt-in，upstream master、本地/origin main，upstream 增加提交 | 本地 main 前进；只更新 fixture origin/main，origin/master 不创建；HEAD 始终 main |
| A-BM-003 | 无 opt-in，upstream develop、本地/origin main | fetch/merge develop，push main，origin/develop 不创建 |
| A-BM-004 | 旧 opt-in 仅 branch: develop，当前 develop，upstream 默认 master | 两端均 develop；来源不擅改默认 master；旧文件无需迁移 |
| A-BM-005 | 显式 branch: origin/main + upstream_branch: upstream/master | 最终目标 main、来源 master；新增字段贯穿加载/覆盖/运行结果，不被丢弃 |
| A-BM-006 | 仅 upstream_branch: develop，.gitmodules branch main、当前 main | 来源 develop、目标 main；schema_version 1 无需变化 |
| A-BM-007 | 无 opt-in 的真实 OctoBot（仅只读 dry-run，禁 apply） | source master、target main；有缓存比较也标 cached；push 计划仅 origin main；无任何子仓 yaml/refs/gitlink 改变 |
| A-BM-008 | target override、.gitmodules branch、当前分支、origin HEAD 故意冲突 | 依 §3.5 优先级选目标；不匹配当前则 fail，不降级改选当前或 upstream |
| A-BM-009 | .gitmodules 无 branch；当前 topic、origin HEAD main | 目标 topic；来源仍独立；移除当前符号 HEAD 后即 detached 拒绝，不自动跟随 origin |
| A-BM-010 | .gitmodules branch=.；主仓当前 main 或 detached | 前者目标 main；后者 fail 且无副作用 |
| A-BM-011 | 来源 cached HEAD、远端 HEAD、main/develop/master 缓存依次缺失 | 严格按 §3.5 次序；远端失败有诊断；全部缺失 unresolved/fail，不借目标 main 假通过 |
| A-BM-012 | 裸 feature/x、匹配 remote 前缀及 refs/heads 表示 | 保留完整 feature/x；legacy origin/main 的来源兜底为 main；不生成 origin/origin/main 等命令 |
| A-BM-013 | branch/upstream_branch 显式 null/空/非字符串/非法 ref/错误 remote | 字段错误可诊断、该项 fail；不静默忽略；其他 opt-in 非分支兼容不变 |
| A-BM-014 | dry-run 已选 source，但缓存 ref 缺失，或 rev-list 非零/空/负值/多余 token | unknown，phase/overall fail、exit 1；绝非 behind=0 或 up-to-date；无 fetch/写 Git/后续执行 |
| A-BM-015 | apply 显式来源远端不存在；或 fetch 成功但来源比较失败 | fail，后续 merge/install/restart/push 不执行；不存在来源不得 fallback；前者不改变本地 HEAD/目标远端 |
| A-BM-016 | dry-run/apply 目标与当前分支不符、目标不存在或 detached；含 force-dirty | fetch/hook 等写操作前拒绝；HEAD/refs/index/worktree/config/远端不变 |
| A-BM-017 | 正确目标下 skip-merge 或 resume-after-merge | 前者仍校验 fetch/比较且只跳 merge；后者不 fetch/merge、不要求来源缓存，继续原 install/restart/目标 push；错误目标仍拒绝 |
| A-BM-018 | 有可信缓存的干净 dry-run --push --no-audit | 源/目标计划正确，明确未 fetch；HEAD/全部 refs/index/config/FETCH_HEAD/worktree/远端不变，不运行 hook/install/restart/health |
| A-BM-019 | fetch 成功但 remote-tracking ref 不自动更新；hook 改变当前分支 | 前者只合入本轮来源提交、不用陈旧缓存；后者 merge/push 前发现不匹配并停止，不合错分支 |
| A-BM-020 | 原安装排除/诊断、dirty、默认不 push、禁 force、冲突 abort、fail-fast、互斥与 only | 原行为测试无回归；只调整旧测试中错误单分支优先级/缺 ref 假 PASS 预期，不能删掉原覆盖 |

功能证据至少包括隔离本地 bare Git 的 main→main、master→main、develop→main 真实 fetch/merge/push 链路（仅 fixture 允许），另有错误目标/缺 ref/零写 dry-run 覆盖；不能仅 mock 命令字符串或仅 normalize origin/main 作为完整兼容证据。所有 fixture 写操作在当前 profile TMPDIR/scratch，remote 不可指向 GitHub 或生产路径；不安装依赖、不运行机器人/交易/真实服务。

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

以下为历史基础验证命令；本次实际安全命令集由 T2 Design 定义，真实 OctoBot 仅 `--dry-run --only OctoBot --skip-install --skip-restart --no-audit`（需要 push 计划时可附 --push）。不执行真实升级/fetch/merge/checkout/reset/push；不以此授权全仓 apply 或产生默认 /tmp 审计。保留原有测试全量覆盖，并增加 §8.1 验收。

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
| 来源/目标发现失败或目标不符 | 按 §3.5–§3.8 诊断并停手，不把目标 main 当来源 fallback | Developer |
| PyYAML 不可用 | stdlib fallback（复用 V2 `_load_yaml_subset` 模式） | Developer |
| health_check 默认 None 导致服务异常未被发现 | Pascal 按需通过 opt-in 配置 health_check cmd | Closeout 记录残余风险 |

未解决问题：
- `--resume-after-merge` 是否需要 checkpoint 文件：V1 可简单实现为"跳过 fetch+merge"。
- 启发式 systemd 匹配算法的"最长 path 段 match"是否足够：T3 可加更多 fixture 验证。
- `--only` 匹配是否需要支持 glob（如 `--only daily_*`）：V2.0 不支持，留后续。
