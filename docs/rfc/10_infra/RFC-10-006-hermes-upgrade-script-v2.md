# RFC-10-006：Hermes Agent 自动升级脚本 V2

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-07-08 |
| 版本号 | V2.0 |
| 所属模块 | 10_infra（基础设施 / Hermes 运维自动化） |
| 继承 RFC | RFC-10-005-hermes-auto-upgrade |
| 关联 SPEC | SPEC-10-006-hermes-upgrade-script-v2 |
| 关联 Design | DESIGN-10-006-hermes-upgrade-script-v2 |
| Quick Flow | T1=t_5b0e9e89, T2=t_5beea5d8, T3=t_fa87e65b, T4=t_3d1b2331 |
| 标签 | #infra #hermes #upgrade #ops #quick-flow |

## 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V2.0 | 2026-07-08 | 在 RFC-10-005 V1.0 基础上新增非 main 分支、feature commit 保护、Pascal fork 私有 patch manifest 核对 | YQuant-Codex-Principal |

## 1. 问题陈述

RFC-10-005 已定义并落地 `scripts/upgrade/upgrade_hermes_agent.py` V1.0：默认在 `/home/pascal/workspace/hermes-agent` 的 `main` 分支上，从 `upstream/main` 升级，升级前创建 zip/stash/manifest，验证成功后再 restart/push。V1.0 已覆盖“安全升级主线”，但在 v0.16.0 → v0.18.0 的真实使用中暴露 3 个限制。

### 1.1 限制一：强制 main 分支导致 feature branch 场景不可运行

现状来自 RFC-10-005 §5.1 / SPEC-10-005 §7：V1.0 `inspect_repo()` 在 S0 强制要求当前分支为 `main`。代码位置为 `scripts/upgrade/upgrade_hermes_agent.py:413-421`：

```text
branch = git branch --show-current
if branch != "main": raise UpgradeError("inspect", "本脚本只支持在 main 分支执行")
```

具体场景：Pascal fork 正在 `fix/feishu-table-card` 等 feature branch 上保留飞书 markdown 表格修复；此时运行 dry-run 或升级计划会在 S0 直接失败，无法继续做只读检查，也无法先保护 feature branch。

影响：

- 操作者必须手动 stash、手动切回 main，再重跑升级脚本；流程容易遗漏当前 feature branch 上的本地 commit。
- V1.0 的 dry-run 无法作为“任意当前状态检查器”使用，降低升级前诊断价值。
- 与 RFC-10-005 §2.3 “降低误删风险、提高运维确定性”的目标不完全一致。

复现路径：

```bash
git -C /home/pascal/workspace/hermes-agent checkout fix/feishu-table-card
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push
# 当前 V1.0：inspect 阶段报错，只支持 main
```

### 1.2 限制二：本地未推送 commit 的保护动作不够显式

RFC-10-005 §5.1/§5.2 已要求检测 local-only commits，并在 A+ merge 前保护本地 commit；但 V1.0 的保护语义主要绑定在 `main` 分支和 `origin/main` 上。对于 feature branch 上的本地 commit，V1.0 不会在进入 main 升级前自动 `git push -u origin <feature-branch>`，用户仍需手动判断是否已推送。

具体场景：

- 当前分支为 `fix/feishu-table-card`；
- 分支上包含未推送 commit，例如飞书交互卡片修复；
- 用户希望先把该分支推到 Pascal fork 作为证据，再回到 main 执行升级。

影响：

- local commit 的保护依赖人工记忆，不符合 RFC-10-005 §4.1 “保守、安全、可回滚”的设计哲学。
- 一旦用户误切分支、误 reset 或 merge 失败，feature branch 上的私有修复恢复成本增加。

复现路径：

```bash
git -C /home/pascal/workspace/hermes-agent checkout -b fix/example
# 产生本地 commit，但未 git push -u origin fix/example
python3 scripts/upgrade/upgrade_hermes_agent.py --dry-run --no-restart --no-push
# 当前 V1.0：先因非 main 失败；不会输出 feature branch push 保护计划
```

### 1.3 限制三：Pascal fork 私有 patch 缺少机器可读追踪

RFC-10-005 §2.1 记录当时本地 HEAD 包含 Pascal fork 的飞书 markdown 表格修复，但该信息没有被沉淀为脚本可读取的 manifest。当前私有 patch 主要靠 MEMORY 或人工上下文追踪，例如 commit `4d3a9661c` 的飞书表格修复。

具体场景：升级到新的 upstream/main 后，需要判断：

- upstream 是否已接纳同等修复；
- Pascal fork 上的 patch 是否仍需保留；
- 哪些文件可能受 patch 影响；
- 是否存在 upstream 合并后可移除的 fork-local patch。

影响：

- 每次升级都要靠人工记忆确认 patch 状态，容易漏查。
- Review/Closeout 无法基于结构化数据判断 “upstream 已包含 / 仍需观察”。
- 与 RFC-10-005 §2.3 “输出审计日志，方便复盘升级过程”的目标不完全一致。

复现路径：

```bash
# 升级完成后想检查 upstream/main 是否已包含 feishu table patch
# 当前 V1.0：没有 data/hermes_patches.yaml 或等价 manifest 可读
# 只能人工 git log / git diff / 记忆检索
```

## 2. 设计目标

本 RFC 在 RFC-10-005 的安全升级主线之上做 V2 增量增强，目标是让升级脚本能在真实 fork 工作流中更安全地处理 feature branch 与私有 patch。

### 2.1 Must-Have

- 支持通过 `--branch BRANCH` 指定允许检查/执行的当前分支；默认仍为 `main`，保持 RFC-10-005 V1.0 行为不变。
- 支持 `--preserve-features`：在升级前新增 S0.5 保护步骤，列出当前分支、dirty files、local-only commits，并在可行时 `git push -u origin <branch>` 保护 feature branch。
- 新增 `data/hermes_patches.yaml`，维护 Pascal fork 私有 patch 清单，初始包含 `feishu-markdown-table` 条目。
- 支持 `--patches-manifest PATH`：升级后或 dry-run 中读取 patch 清单，并对 upstream 是否已包含 patch 做 best-effort 核对。
- 保持 V1.0 默认用法向后兼容：不带新参数时仍要求 `main`，仍使用 RFC-10-005 的备份、stash、A+ merge、install、verify、restart、push 顺序。
- 新增测试覆盖参数解析、branch override、patch manifest schema、patch 核对、preserve-features dry-run 行为。

### 2.2 Should-Have

- patch manifest 支持 schema version，以便后续追加 upstream PR、文件 glob、核对策略等字段。
- manifest 缺失或格式错误时不阻塞升级主线，只输出 warning；真实升级安全性不能依赖该文件。
- patch 核对结果进入升级 manifest / stdout 摘要，便于 T3 Verify 和 T4 Closeout 审查。

### 2.3 Non-Goals

- 不自动 cherry-pick、rebase 或删除 Pascal fork 私有 patch。
- 不自动创建 upstream PR，也不调用 GitHub API 修改 PR 状态。
- 不改变 RFC-10-005 的真实 gateway restart / push origin 安全边界。
- 不修改 Hermes profile config、secrets、auth、MCP 或 systemd unit。
- 不引入新的第三方依赖；若运行环境已有 PyYAML 可使用，否则必须有标准库 fallback 或简化解析方案。

## 3. 总体方案

V2 保持 RFC-10-005 的主状态机，只在 3 个位置做增量插入：

```text
S0 inspect repo
  ├─ V1: branch 必须是 main
  └─ V2: branch 必须等于 --branch（默认 main）；不匹配则失败并给出下一步

S0.5 preserve feature branch（新增，可选）
  ├─ 仅当 --preserve-features 启用
  ├─ 若当前 branch 非 detached 且存在 origin
  ├─ dry-run: 输出 git push -u origin <branch> 计划
  └─ real-run: best-effort push 当前 branch；失败 warning，不直接破坏 repo

S5/S9 patch manifest check（新增，可选）
  ├─ 仅当 --patches-manifest PATH 提供
  ├─ 读取 data/hermes_patches.yaml
  ├─ 对每个 patch 核对 upstream_ref 是否已包含同等变更
  └─ 输出 PatchStatus；默认不自动改写 manifest 文件
```

核心设计原则：

1. **向后兼容优先**：默认参数路径仍等同 V1.0。`--branch` 只是把 “main-only” 变成可配置的允许分支，不改变升级目标仍为 `--version/upstream/main`。
2. **保护先于升级**：feature branch push 发生在真实 fetch/merge/install 之前；dry-run 必须展示计划但不写远端。
3. **patch 核对不阻塞主升级**：patch manifest 是审计与提醒，不是升级安全前置条件；格式错误和缺失不能导致安全升级主线失败。
4. **不自动语义合并**：若 upstream 似乎已包含 patch，脚本最多输出状态；是否从 manifest 移除或从 fork 删除 patch 由 T4 Closeout/人类决定。

## 4. SPEC 概要

完整契约见 `docs/spec/10_infra/SPEC-10-006-hermes-upgrade-script-v2.md`。关键用户可见接口：

| 参数 | 作用 | 默认值 | 兼容性 |
|---|---|---|---|
| `--branch BRANCH` | 指定本次允许的当前工作分支，替代硬编码 main-only | `main` | 默认等同 V1.0 |
| `--preserve-features` | 在升级前保护当前 feature branch local commits | `false` | 默认不启用 |
| `--patches-manifest PATH` | Pascal fork 私有 patch 清单路径 | `None`；建议 `data/hermes_patches.yaml` | 缺失不阻塞 |

新增数据文件：

```text
data/hermes_patches.yaml
```

初始条目追踪飞书 markdown 表格修复：

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

## 5. DESIGN 概要

完整设计见 `docs/design/10_infra/DESIGN-10-006-hermes-upgrade-script-v2.md`。文件改动限制为 6 个：

1. `scripts/upgrade/upgrade_hermes_agent.py`：新增参数、dataclass、S0.5、patch 核对。
2. `tests/scripts/test_upgrade_hermes_agent_v2.py`：新增 V2 测试。
3. `data/hermes_patches.yaml`：私有 patch manifest。
4. `docs/rfc/10_infra/RFC-10-006-hermes-upgrade-script-v2.md`：本 RFC。
5. `docs/spec/10_infra/SPEC-10-006-hermes-upgrade-script-v2.md`：V2 SPEC。
6. `docs/design/10_infra/DESIGN-10-006-hermes-upgrade-script-v2.md`：V2 Design。

## 6. Quick Flow 与 Q-LINK 契约

本任务走 Quick Flow，T1 在本卡完成 RFC/SPEC/Design 与 patch manifest，后续由预创建 parent links 自动推进：

| Q-LINK | 契约 | 本任务落点 |
|---|---|---|
| Q-LINK-001 | Intake 阶段一次性预创建 T1-T4 | T1=t_5b0e9e89, T2=t_5beea5d8, T3=t_fa87e65b, T4=t_3d1b2331 |
| Q-LINK-002 | T1 产出 RFC/SPEC/Design 三层独立文档 | 本 RFC + 对应 SPEC/DESIGN |
| Q-LINK-003 | T2/T3/T4 使用 parent links 自动 promote | T2 parents=[T1], T3 parents=[T1,T2], T4 parents=[T1,T2,T3] |
| Q-LINK-004 | T2 不得修改 T1 文档，除非发现阻塞性矛盾 | T2 body 已禁止修改三层文档 |
| Q-LINK-005 | T3 必须独立验证且包含数据合理性抽样 | T3 body 要求真实 `data/hermes_patches.yaml` e2e 核对 |
| Q-LINK-006 | T4 Closeout 执行 15 项自审 | T4 body 已列出 15 项清单 |

## 7. 风险与应对

| 风险 | 概率 | 影响 | 应对 | 降级 |
|---|---:|---:|---|---|
| `--branch` 被误解为升级目标分支 | 中 | 中 | 文档和 help 明确：升级目标仍由 `--version` 控制，`--branch` 仅是允许当前工作分支 | 保持默认 main 行为 |
| `--preserve-features` push 失败 | 中 | 中 | warning + 输出手动 push 命令；不做 force push | 用户手动 `git push -u origin <branch>` |
| patch manifest YAML 解析失败 | 中 | 低 | warning 不阻塞；测试覆盖缺失/格式错误 | 跳过 patch 核对 |
| upstream 是否包含 patch 的判定不完美 | 高 | 中 | 标为 best-effort；只输出状态，不自动删除 patch | T4/人类复核 git diff/PR |
| 新参数破坏 V1.0 默认路径 | 低 | 高 | V1 测试全量回归；默认参数必须仍要求 main | 回滚到 V1.0 行为 |
| 新增依赖导致环境不一致 | 中 | 中 | 不新增依赖；PyYAML 仅作为可选，必须有 fallback | 使用简化 YAML 子集解析 |

## 8. 验收标准

### 8.1 T1 文档验收

- [x] RFC/SPEC/Design 三层文档分别落在 `docs/rfc/10_infra/`、`docs/spec/10_infra/`、`docs/design/10_infra/`。
- [x] 每层文档均引用 RFC-10-005 / SPEC-10-005 / DESIGN-10-005 的对应限制与继承关系。
- [x] DESIGN 文件清单 ≤ 6 个文件。
- [x] Q-LINK-001~006 全部出现且自洽。
- [x] `data/hermes_patches.yaml` 初始 schema 与 `feishu-markdown-table` 条目存在。

### 8.2 T2/T3 实体验收

- `python3 scripts/upgrade/upgrade_hermes_agent.py --help` 显示 `--branch`、`--preserve-features`、`--patches-manifest`。
- V1.0 现有测试 `tests/scripts/test_upgrade_hermes_agent.py` 全部通过。
- 新增 `tests/scripts/test_upgrade_hermes_agent_v2.py` 至少 3 个 V2 用例通过。
- 以下 dry-run 组合成功且不修改 repo/venv/gateway/origin：
  - 默认 V1.0 兼容路径；
  - `--branch fix/feishu-table-card`；
  - `--preserve-features`；
  - `--patches-manifest data/hermes_patches.yaml`。
- manifest 缺失/格式错误为 warning 不阻塞；无效 branch 为明确错误。
- git diff 不触碰 Hermes profile config、secrets、auth、gateway systemd unit、投资/交易/风控业务逻辑。

## 9. 开放问题

- patch “upstream 已包含” 的 best-effort 判定采用 `git patch-id`、文件 diff 子集、还是 commit SHA/PR metadata，Design 阶段给出最小可实现方案；Review 可要求后续增强。
- `data/hermes_patches.yaml` 是否在后续 Closeout 中自动把 `upstream_merged=false` 改成 true：本 RFC 默认不自动改写，由 T4/人类决定。
- 是否后续将 `--preserve-features` 设为默认启用：本 RFC 不做该变更，避免破坏 V1.0 默认行为。

## 10. 参考资料

- `docs/rfc/10_infra/RFC-10-005-hermes-auto-upgrade.md`
- `docs/spec/10_infra/SPEC-10-005-hermes-auto-upgrade.md`
- `docs/design/10_infra/DESIGN-10-005-hermes-auto-upgrade.md`
- `scripts/upgrade/upgrade_hermes_agent.py`
- `tests/scripts/test_upgrade_hermes_agent.py`
- `docs/rfc/10_infra/RFC-10-004-yquant-ai-coding-pipeline-skill-sync.md`
- `docs/spec/10_infra/SPEC-10-004-yquant-ai-coding-pipeline-skill-sync.md`
- `docs/design/10_infra/DESIGN-10-004-yquant-ai-coding-pipeline-skill-sync.md`
