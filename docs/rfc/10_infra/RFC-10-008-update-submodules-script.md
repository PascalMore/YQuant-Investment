# RFC-10-008：通用多 submodule 升级器 update_submodules.py

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-07-09 |
| 版本号 | V2.0 |
| 所属模块 | 10_infra（基础设施 / git submodule 运维自动化） |
| 继承 RFC | 无（独立脚本；设计哲学参考 RFC-10-005 / RFC-10-006 V2） |
| 关联 SPEC | SPEC-10-008-update-submodules-script |
| 关联 Design | DESIGN-10-008-update-submodules-script |
| Full Flow | T1_redo=t_91ffdfe3（重写为 auto-discovery + opt-in） |
| 标签 | #infra #git #submodule #upgrade #ops #auto-discovery #opt-in-override |

## 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-07-08 | 初始版本：manifest-driven（中央 `data/submodules.yaml` 注册表）5 阶段 submodule 升级器 | YQuant-Codex-Principal |
| V1.1 | 2026-07-09 | 中途修订：尝试在 V1.0 文档上 patch auto-discovery，但 upstream 缺失处理、health_check 默认值、opt-in schema 仍残留 V1.0 思路 | YQuant-Codex-Principal |
| **V2.0** | **2026-07-09** | **完整重写**（T1_redo）：取消中央 manifest；明确 upstream 缺失=报错退出不自动 add；health_check 默认 None；opt-in `.update_submodules.yaml` schema 简化为 shell 命令字符串；新增 `--only NAME` 显式过滤（缺名报错不静默 fallback）。与 `upgrade_hermes_agent.py` V2 的「无配置默认 + opt-in 增强」哲学对齐 | YQuant-Codex-Principal |

> **V1.0 已废弃说明**：V1.0 的中央 `data/submodules.yaml` manifest 模式已彻底取消。本 V2.0 文档不保留任何 manifest 章节；凡出现 `data/submodules.yaml` 的地方均为「已废弃」说明。

## 1. 问题陈述

Pascal 维护 yquant-investment 项目下的多个 git submodule。每个 submodule 都是 fork 仓（origin=PascalMore/...）+ upstream 跟踪 + 自己的开发，升级时需要：

1. 从 upstream 拉最新代码
2. 升级安装（pip install）
3. 重启对应 systemd 服务
4. push 到 origin

当前没有统一流程，完全靠手工记忆每个 submodule 的 upstream 地址、venv 路径、systemd 服务名、install 方式。容易遗漏步骤、误操作、服务中断后不知道是哪个 submodule 引起的。

### 1.1 现状痛点

| 痛点 | 影响 |
|---|---|
| 每个 submodule 的 upstream / origin / venv / systemd 信息分散在 MEMORY、脑力记忆和 `.gitmodules` 中，没有机器可读清单 | 新增 submodule 时升级流程要靠人工重新推导 |
| 升级步骤纯手工：fetch → merge → pip install → systemctl restart → push，容易跳步或顺序错 | 升级后忘记 restart 导致旧代码仍在运行；或忘记 push 导致 fork 落后 |
| merge 冲突时没有标准处置流程 | 手忙脚乱，可能误用 --force 或 --abort 丢失工作 |
| 没有审计日志 | 出问题后无法复盘"什么时候升级了什么、结果如何" |
| pip install 破坏性变更（如上游引入 breaking change）没有在 restart 前被捕获 | 服务启动失败，影响线上 |

### 1.2 已知 submodule（截至 2026-07-09）

实测 `.gitmodules` + `git remote -v` + `systemctl --user list-units`：

| .gitmodules section name | path | origin | upstream | systemd service | venv | pip 方式 |
|---|---|---|---|---|---|---|
| `skills/research/daily_stock_analysis` | `skills/research/daily_stock_analysis` | `git@github.com:PascalMore/daily_stock_analysis.git` | `https://github.com/ZhuLinsen/daily_stock_analysis.git` | `daily-stock-analysis.service`（active running） | `.venv`（存在） | `pip install -r requirements.txt` |
| `skills/apps/TradingAgents-CN` | `skills/apps/TradingAgents-CN` | `git@github.com:PascalMore/TradingAgents-CN.git` | `https://github.com/hsliuping/TradingAgents-CN.git` | `tradingagents-cn.service`（active running） | `.venv`（存在） | `pip install -r requirements.txt` |

**V2.0 设计要点**：以上字段**不再需要集中维护**。`name`+`path` 来自 `.gitmodules`；`origin`/`upstream` 来自 `git remote`；`venv`/pip 方式/systemd 由启发式推断（见 §4）。如个别 submodule 有例外，在其仓库根目录放 `.update_submodules.yaml` 覆盖默认即可。

### 1.3 与 upgrade_hermes_agent.py 的区别

`upgrade_hermes_agent.py`（RFC-10-005/006）只处理单个 Hermes Agent repo，有 zip 备份、A+ merge、detached gateway restart 等复杂策略。本 RFC 的 `update_submodules.py` 处理多个 submodule，每个有独立 venv 和 systemd 服务，策略更通用但单 submodule 的备份复杂度更低。

两者共享的设计哲学：**auto-discovery / 启发式默认 / opt-in 覆盖 / dry-run 优先 / subprocess 封装 / 审计日志 / 拒绝 force push**。

## 2. 设计目标

### 2.1 Must-Have

- **自动发现（auto-discovery）**：脚本从 `.gitmodules` 解析所有 submodule 列表；每个 submodule 的 `origin`/`upstream`/venv/pip 方式/systemd 由启发式自动推断（见 §4），**默认不需要任何中央配置文件**。
- **opt-in 覆盖**：若 submodule 仓库根目录存在 `.update_submodules.yaml`，加载并覆盖该 submodule 的启发式字段。**不存在是常态**。
- **支持 `--only NAME` 过滤**：只处理指定 submodule（可多次，`action="append"`），便于"传入参数指定对某一 submodule 升级"。缺名报错退出，**不静默 fallback**。
- **安全默认**：默认 dry-run（只输出计划不执行）；push 阶段必须显式 `--push` 启用；永远拒绝 `--force` push。
- **可观测**：每次运行生成审计日志，记录每个 submodule 每个阶段的命令、exit code、耗时。
- **可恢复**：merge 冲突时自动 `git merge --abort` 并停手报告，不自动 resolve；install/restart 失败时 abort 后续阶段。
- **5 阶段流水线**：fetch → merge → install → restart → push，每阶段可独立跳过（`--skip-merge` / `--skip-install` / `--skip-restart`）。

### 2.2 Should-Have

- `--only NAME` 支持多次（`action="append"`）。
- pre_merge_hooks：merge 前执行自定义命令（如 stash dirty worktree）。
- health_check：restart 后可选 health check（opt-in 提供 shell 命令），失败时 abort push。

### 2.3 Non-Goals

- 不自动 cherry-pick / rebase / drop fork 私有 commit。
- 不修改 `.gitmodules`、不 add/remove submodule。
- 不修改 systemd unit 文件。
- 不修改 submodule 内的业务代码、配置文件、.env。
- 不引入新的第三方依赖（PyYAML optional，须有 stdlib fallback）。
- 不替代 `upgrade_hermes_agent.py`——两者目标不同，独立运行。
- **不自动 `git remote add upstream`**：upstream remote 缺失即报清晰错误退出（见 §4），由人工添加。
- **不维护中央 `data/submodules.yaml`**（V1.0 设计；V2.0 彻底取消）。

## 3. 总体方案

### 3.1 auto-discovery + opt-in override 架构

```text
.gitmodules                 ← submodule 列表（section name + path）
  ↓
parse_submodules()          ← 解析 [submodule "<section-name>"] + path
  ↓
FOR each submodule (cwd = <project_root>/<path>):
  ├─ 启发式推断所有字段
  │   ├─ origin      ← git -C <path> remote get-url origin
  │   ├─ upstream    ← git -C <path> remote get-url upstream
  │   │                  （缺失 → 报清晰错误退出，不自动 add，不回落 origin）
  │   ├─ venv        ← <path>/.venv 存在？→ 用；否则跳过 install 阶段
  │   ├─ pip_install ← <path>/requirements.txt 存在？→ pip install -r；否则跳过 install
  │   ├─ systemd     ← systemctl --user list-units 模糊匹配 <path> 段
  │   └─ health_check← 默认 None；opt-in override 可配
  │
  ├─ 加载 <path>/.update_submodules.yaml（如存在）→ 覆盖启发式字段
  │
  └─ 5 阶段流水线（fetch→merge→install→restart→push）
```

```bash
# 默认（dry-run，所有 submodule，自动发现）
python3 update_submodules.py

# 升级单一 submodule（按 .gitmodules section name 匹配）
python3 update_submodules.py --only daily_stock_analysis --apply --push

# 多个（action="append"）
python3 update_submodules.py --only daily_stock_analysis --only TradingAgents-CN

# 跳过子阶段
python3 update_submodules.py --skip-install
python3 update_submodules.py --skip-restart
python3 update_submodules.py --skip-merge

# dry-run 显式
python3 update_submodules.py --dry-run

# 任意组合
python3 update_submodules.py --only daily_stock_analysis --push --skip-restart
```

### 3.2 5 阶段流水线

```text
┌──────────────────────────────────────────────────────────────────┐
│  对每个 submodule（串行处理）：                                    │
│                                                                    │
│  Phase 1: FETCH                                                    │
│    git fetch upstream <branch>                                     │
│    计算 behind/ahead                                               │
│    behind==0 → 跳过 Phase 2，直接到 Phase 3                        │
│                                                                    │
│  Phase 2: MERGE                                                    │
│    ahead==0 → git merge --ff-only upstream/<branch>                │
│    ahead>0  → git merge upstream/<branch>（merge commit）           │
│    conflict → git merge --abort, ABORT, 报告                       │
│                                                                    │
│  Phase 3: INSTALL                                                  │
│    .venv/bin/pip install <pip_install cmds>                        │
│    exit!=0 → ABORT, 不 restart, 报告                               │
│                                                                    │
│  Phase 4: RESTART                                                  │
│    systemctl --user restart <service>  (或 restart_cmd)            │
│    health_check（opt-in 提供 cmd 时才执行）                         │
│    health_check FAIL → ABORT, 不 push, 报告                        │
│                                                                    │
│  Phase 5: PUSH（仅当 --push 且前面全 PASS）                         │
│    git push origin <branch>  （永远不 --force）                     │
│    exit!=0 → 报告但不 rollback（代码已 merge+install+restart）      │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 核心设计原则

1. **dry-run 是默认**：不带 `--apply` 时只读取 `.gitmodules` + git 状态，输出完整计划，不修改任何 repo/venv/systemd/origin。
2. **零配置运行**：`.gitmodules` 是唯一的 submodule 列表源；其他字段由启发式推断；只有非常规需求才需要 opt-in `.update_submodules.yaml`。
3. **安全顺序**：fetch → merge → install → restart → push。push 永远在最后，只有前面全通过才执行。
4. **abort 不 rollback**：除 merge 冲突会 `git merge --abort` 外，其他阶段失败只 abort 后续阶段，不主动回滚已完成的操作（pip install 不回滚、restart 不回滚）。原因是回滚本身也有风险，应留给人类决策。
5. **串行处理**：submodule 之间串行执行，不并行。一个 submodule 失败不影响后续 submodule 的处理（除非 `--fail-fast`）。
6. **upstream 缺失=硬错误**：upstream remote 不存在时**报清晰错误退出该 submodule**，不自动 `git remote add`，不回落 origin。这是 V2.0 与 V1.1 的关键差异——自动 add remote 是隐性副作用，违背 dry-run 安全哲学。
7. **opt-in override 不阻塞**：单个 submodule 的 `.update_submodules.yaml` 加载/校验失败只 warning 跳过该 override（不影响其他 submodule），回落到启发式默认。

## 4. auto-discovery 字段来源

脚本对每个 submodule 按以下顺序确定每个字段：

| 字段 | 启发式默认 | opt-in 覆盖 | 覆盖规则 |
|---|---|---|---|
| `name` | `.gitmodules [submodule "<name>"]` 的 section 名 | — | 不可覆盖（来自 .gitmodules） |
| `path` | `.gitmodules` 的 `path = ...` | — | 不可覆盖（来自 .gitmodules） |
| `origin` | `git -C <path> remote get-url origin` | `origin: <url>` | 字符串覆盖 |
| `upstream` | `git -C <path> remote get-url upstream` | `upstream: <url>` | 字符串覆盖 |
| `branch` | 远端 HEAD 指向分支（fallback `main`） | `branch: <name>` | 字符串覆盖 |
| `venv` | `<path>/.venv` 存在 → `.venv`；否则 None（**跳过 install 阶段**） | `venv: <rel-path-or-null>` | 字符串覆盖；null=跳过 install |
| `pip_install_cmd` | `<path>/requirements.txt` 存在 → `["install", "-r", "requirements.txt"]`；否则 None（**跳过 install 阶段**） | `pip_install: [...]` 或 null | list 覆盖；null=跳过 install |
| `pre_merge_hooks` | `[]` | `pre_merge_hooks: [<cmd>...]` | list 替换 |
| `systemd_service` | `systemctl --user list-units --type=service --no-legend` 模糊匹配 path 段（取最长 match） | `systemd_service: <name-or-null>` | 字符串覆盖；null=跳过 restart |
| `health_check` | **None**（默认不检查） | `health_check: <shell-cmd-string>` | **字符串覆盖**（shell 命令；非空时 Phase 4 后执行） |
| `skip_push` | `false`（默认仍走 `--push` 开关） | `skip_push: true` | 布尔覆盖（极少用） |
| `notes` | `""` | `notes: <text>` | 字符串覆盖 |

### 4.1 upstream 缺失处理（V2.0 关键决策）

| 场景 | 行为 | 理由 |
|---|---|---|
| upstream remote 存在 | 正常 fetch | — |
| upstream remote 缺失 + opt-in `.update_submodules.yaml` 提供 `upstream` | **报清晰错误退出该 submodule**：提示人工 `git -C <path> remote add upstream <url>` | 自动 add remote 是隐性副作用；且 opt-in 配置可能是错的，盲目 add 会污染 repo |
| upstream remote 缺失 + 无 opt-in | **报清晰错误退出该 submodule** | 同上 |

**错误信息样例**：
```
ERROR: submodule "daily_stock_analysis" 缺少 upstream remote。
  当前 remotes: origin
  请手动执行: git -C skills/research/daily_stock_analysis remote add upstream <upstream-url>
  或在 skills/research/daily_stock_analysis/.update_submodules.yaml 中声明 upstream URL
```

> **与 V1.1 的差异**：V1.1 会自动 `git remote add upstream <url>`（opt-in 提供时）。V2.0 取消此行为——自动修改 git config 是隐性副作用，违背「dry-run 默认 + 不修改 repo 元数据」原则。Pascal 需要时手动 add 即可。

### 4.2 health_check 默认行为（V2.0 关键决策）

| 配置来源 | health_check 值 | Phase 4 行为 |
|---|---|---|
| 默认（无 opt-in） | `None` | restart 后**不执行** health check，直接进入 push（如启用） |
| opt-in `health_check: "curl -sf http://localhost:8000/health"` | 该 shell 命令字符串 | restart 后执行该命令；exit!=0 → ABORT push |
| opt-in `health_check: "systemctl --user is-active --quiet daily-stock-analysis.service"` | 该 shell 命令字符串 | 同上 |

> **与 V1.1 的差异**：V1.1 默认 `{type: systemd_active, timeout: 15}` 并轮询 `systemctl is-active`。V2.0 默认 None——是否做 health check 由 Pascal 通过 opt-in 显式声明（shell 命令字符串），更灵活且不预设检查方式。

## 5. 风险评估

| 风险 | 概率 | 影响 | 应对 | 降级 |
|---|---:|---:|---|---|
| merge 冲突 | 高（daily-stock-analysis fork 领先 200+ commit） | 中 | 自动 `git merge --abort` + 报告，不自动 resolve | 人工解决后 `--resume-after-merge` |
| pip install 破坏性变更 | 中 | 高（服务启动失败） | install 后 restart；opt-in health_check 可捕获 | 人工回滚 pip / 从 venv 恢复 |
| restart 导致服务中断 | 中 | 中 | opt-in health_check 确认恢复；restart 前记录 pre-restart HEAD | 人工 systemctl --user restart 旧版本 |
| push 误覆盖 origin | 低 | 高 | 永远不 --force；push 只在前面全 PASS 后执行 | git reflog 恢复 origin |
| systemd 模糊匹配误中（重名） | 低 | 中 | match 取最长 path 段；dry-run 输出 systemd 推断结果供审查 | 显式 opt-in `.update_submodules.yaml` 修 |
| `.update_submodules.yaml` 格式错误 | 低 | 低 | warning 跳过该 override，回落启发式 | 人工修正 |
| 启发式推断 wrong（venv 路径非 .venv） | 低 | 低 | dry-run 显示推断结果；opt-in override 可改 | 显式 opt-in 修 |
| upstream remote 缺失 | 低 | 低 | 报清晰错误退出，不自动 add | 人工 `git remote add` |
| 并发升级多个 submodule 资源竞争 | 低 | 低 | 串行处理，不并行 | N/A |

## 6. auto-discovery vs manifest-driven 权衡

| 维度 | auto-discovery + opt-in（V2.0 本方案） | manifest-driven（V1.0 已废弃） |
|---|---|---|
| 新增 submodule | 0 配置（push 到 .gitmodules 即可） | 改 YAML |
| 字段来源 | 启发式 + 显式 override | 全部手动填写 |
| 灵活性 | 99% 场景无需任何配置；特殊场景 opt-in 覆盖 | 全部场景手动维护 |
| 错误风险 | 启发式误判风险低（dry-run 暴露） | YAML 格式错误 + 字段填写遗漏 |
| 复杂度 | 启发式逻辑一次性写好；opt-in schema 简单 | YAML loader + schema 校验 |
| 审计 | 审计日志 + opt-in YAML 进 submodule 仓库 diff | 中央 YAML 进 yquant diff |
| 与 V2 协同 | 与 `upgrade_hermes_agent.py` V2「无配置默认 + opt-in」哲学一致 | manifest 风格与 V2 不一致 |

**结论**：auto-discovery + opt-in 显著优于集中 manifest。`.gitmodules` 已经是 submodule 列表的权威源，再造一个并行注册表是双源不一致风险；其他字段启发式已覆盖 99% 场景，剩余 1% opt-in 解决。这也是 V1.0 → V2.0 的根本动机。

## 7. 与 upgrade_hermes_agent.py V2 的协同

| 维度 | update_submodules.py | upgrade_hermes_agent.py V2 |
|---|---|---|
| 目标 | yquant-investment 下的 git submodule | Pascal fork 的 hermes-agent repo |
| 配置源 | auto-discovery + `.update_submodules.yaml` opt-in | 默认无配置；`data/hermes_patches.yaml` opt-in |
| 备份策略 | git merge --abort + pre-merge HEAD 记录 | zip + stash + manifest 四重锚点 |
| install | `.venv/bin/pip install -r requirements.txt` | uv editable → pip editable fallback |
| restart | `systemctl --user restart <service>` | detached gateway helper |
| push | `git push origin <branch>`（不 --force） | `git push origin main`（不 --force） |
| upstream 缺失 | 报错退出，不自动 add | N/A（单 repo，upstream 固定） |
| 共享模式 | CommandResult dataclass、redact()、dry-run 默认安全、审计日志、auto-discovery+opt-in 设计哲学 | 同左 |

**共享代码**：update_submodules.py 可直接复用 upgrade_hermes_agent.py 的 `CommandResult` dataclass、`run_cmd()` subprocess 封装、`redact()` 脱敏函数和 `_load_yaml_subset()` YAML loader 模式。具体复用方式见 DESIGN-10-008 §3.8。

两脚本独立运行，互不依赖。update_submodules.py 不 import upgrade_hermes_agent.py（避免循环依赖），而是复制必要的 helper 函数或提取到共享 utils（T2 实现者可自行判断）。

## 8. 验收标准（T1 文档层）

- [x] RFC/SPEC/Design 三层文档分别落在 `docs/rfc/10_infra/`、`docs/spec/10_infra/`、`docs/design/10_infra/`。
- [x] RFC 引用 SPEC，SPEC 引用 Design。
- [x] V2.0 取消中央 `data/submodules.yaml`；改用 auto-discovery + opt-in override（见 §3.1、§4）。
- [x] §4 字段来源表完整，含 upstream 缺失=报错退出、health_check 默认 None。
- [x] CLI 完整参数 + safety 护栏（含 `--only` 支持 `action="append"`，缺名报错）。
- [x] 与 upgrade_hermes_agent.py V2 协同明确（不重复实现）。
- [x] opt-in `.update_submodules.yaml` schema 简化为 shell 命令字符串（health_check）。

## 9. 开放问题

- `--resume-after-merge` 的实现深度：V1 可只支持"跳过 fetch+merge，从 install 开始"；完整的 checkpoint 恢复留后续。
- 是否把 opt-in `.update_submodules.yaml` 纳入 submodule 仓库 commit：推荐 commit 到 Pascal 的 fork（origin），upstream 仓库不接受 Pascal 的私有配置。
- `--only NAME` 匹配语义：当前 `.gitmodules` section 名是 path-based（如 `skills/research/daily_stock_analysis`），而用户习惯用短名（`daily_stock_analysis`）。SPEC §4 / Design §3.x 定义匹配规则（section name 精确匹配 + path basename 后缀匹配，详见 SPEC）。

## 10. 参考资料

- `scripts/upgrade/upgrade_hermes_agent.py` V2（数据结构和风格参考；设计哲学同源）
- `data/hermes_patches.yaml`（opt-in manifest 风格参考；**但本任务不做中央 manifest**）
- `docs/{rfc,spec,design}/10_infra/10-006-hermes-upgrade-script-v2.md`（3 文档模板；opt-in 设计哲学参考）
- `docs/{rfc,spec,design}/10_infra/10-005-hermes-auto-upgrade.md`（V1 安全升级主线）
- `.gitmodules`（submodule 列表源；auto-discovery 的输入）
- `~/.config/systemd/user/daily-stock-analysis.service`
- `~/.config/systemd/user/tradingagents-cn.service`
- `/home/pascal/workspace/yquant-investment/skills/infra/ai-coding-pipeline/SKILL.md`（设计约束）
- `/home/pascal/workspace/yquant-investment/skills/infra/sanity-check/`（6 模板；git_state_check 最相关）
