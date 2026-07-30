# RFC-10-006：Hermes Agent 自动升级脚本 V2

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | Accepted |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-07-08 |
| 最后更新 | 2026-07-30 |
| 版本号 | V2.1 |
| 所属模块 | 10_infra（基础设施 / Hermes 运维自动化） |
| 继承 RFC | RFC-10-005-hermes-auto-upgrade |
| 关联 SPEC | SPEC-10-006-hermes-upgrade-script-v2 |
| 关联 Design | DESIGN-10-006-hermes-upgrade-script-v2 |
| 标签 | #infra #hermes #upgrade #ops #transport-resilience |

## 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V2.1 | 2026-07-30 | 增补 Git 传输韧性增强：target-aware fetch、分类瞬态错误有限重试、HTTP/1.1 命令级 fallback、manifest audit、feature-branch 保护修正、dry-run 零网络 | YQuant-Codex-Principal |
| V2.0 | 2026-07-08 | 在 RFC-10-005 V1.0 基础上新增非 main 分支、feature commit 保护、Pascal fork 私有 patch manifest 核对 | YQuant-Codex-Principal |

## 1. 问题陈述

### 1.1 V2.0 已解决的限制

RFC-10-005 已定义并落地 `scripts/upgrade/upgrade_hermes_agent.py` V1.0：默认在 `/home/pascal/workspace/hermes-agent` 的 `main` 分支上，从 `upstream/main` 升级，升级前创建 zip/stash/manifest，验证成功后再 restart/push。

V2.0（2026-07-08）在 V1.0 基础上解决了 3 个限制：

1. **强制 main 分支** → 新增 `--branch` 参数允许 feature branch。
2. **本地未推送 commit 保护不显式** → 新增 `--preserve-features` 在升级前保护当前 branch。
3. **私有 patch 缺少机器可读追踪** → 新增 `data/hermes_patches.yaml` + `--patches-manifest` 核对。

### 1.2 V2.1 新增限制：Git 传输在代理环境下缺乏韧性

2026-07-30 的真实升级运行暴露了一个新的限制。即使 WSL Git 已正确配置代理（`http(s)_proxy=172.25.240.1:7897`），`git ls-remote upstream main` 也曾成功，但 `git fetch upstream main --tags` 仍发生：

- `GnuTLS recv error (-110)`
- `early EOF`
- `invalid index-pack output`

当前脚本（V2.0）对 fetch 失败的处理是一次性失败并 exit 1，不区分：

- **瞬态传输错误**（GnuTLS/EOF/index-pack/SSL/TLS reset）——可能通过有限重试或协议降级恢复；
- **永久错误**（认证失效、无效 ref、权限验证）——重试也无意义。

此外，当前 fetch 使用了 `--tags`，即使目标只是 `upstream/main`，这在代理环境下增大了传输包体积，提高了触发传输错误的概率。

### 1.3 影响

- 一次瞬态网络错误即可阻塞整个升级，留给 operator 的下一步只有"手动 retry 或检查网络"。
- 重跑整条升级链（备份、stash、fetch、classify、merge、install...）比重试 fetch 一步的代价高得多。
- 没有审计记录表明 fetch 做了几次尝试、最终用了什么传输方式，operator 无法判断"是否达到协议降级边界"。

### 1.4 Feature branch 保护语义仍需修正

当前 `protect_local_commits()` (`scripts/upgrade/upgrade_hermes_agent.py:1231-1256`) 在 feature branch 上始终执行 `git push origin main`，无论当前 HEAD 是否被该 push 覆盖。在 feature branch 上，`push origin main` 成功并不保护 feature branch 的 commit。

## 2. 设计目标

### 2.1 Must-Have

本 RFC 在 V2.0 上述安全升级主线之上做 V2.1 增量增强，6 条不可突破契约：

1. **Target-aware fetch**：默认 `--version upstream/main` 时仅 fetch `upstream main --no-tags`，明确 tags 不是隐式依赖；显式 tag target 只 fetch 所请求 tag/ref。
2. **分类瞬态失败有限重试**：常规一次 → 退避重试一次 → `git -c http.version=HTTP/1.1` fallback 一次，总上限 3；不写 global/system/local git config，不改变代理环境变量。
3. **仅 fetch 可自动重试**：merge/install/restart/push 永不自动重试。认证、权限、证书验证、无效 remote/ref 非瞬态失败 fail-stop。
4. **Manifest fetch attempt 审计**：新增脱敏的 fetch attempt 信息；不记录代理 URL、凭证或未脱敏 stderr。
5. **Feature branch 保护修正**：按当前分支验证可达性/protective push，不 force push；不在 feature branch 上仅 `push origin main` 后声称 HEAD 已保护。
6. **Dry-run 零网络**：默认 dry-run 不发网络、不 sleep、不写 Git ref。

### 2.2 Non-Goals

- 不修改 Hermes Agent upstream 源码。
- 不修改 Hermes profile/config/env/auth/MCP/systemd。
- 不引入新第三方依赖。
- 不自动 retry merge/install/restart/push。
- 不改变 V2.0 已有 `--branch`、`--preserve-features`、`--patches-manifest` 行为和默认值。
- 不关闭用户代理或修改 `/etc/environ` / `/etc/profile`。
- 不实现 `http.postBuffer`、`http.lowSpeedLimit` 等非传输错误相关配置的自动设置。

## 3. 总体方案

### 3.1 增量修改位置

V2.1 不重写 V2.0 主状态机，只在 Git 传输相关函数中做增量替换：

```
V2.0 主状态机（不变）
  ├─ S0 inspect repo（不变）
  ├─ S0.5 preserve feature branch（不变）
  ├─ S1 backup（不变）
  ├─ S2 stash（不变）
  ├─ S3 fetch remotes（替换为 target-aware + retry wrapper）
  ├─ S4 classify（不变）
  ├─ S5 protect（修正分支判断）
  ├─ S6 merge（不变）
  ├─ S7 install（不变）
  ├─ S8 verify（不变）
  ├─ S9 restart（不变）
  ├─ S10 push（不变）
  └─ S11 rollback（不变）
```

### 3.2 核心设计原则

1. **目标感知**：只 fetch 完成 `--version` 目标所需的最小 ref，减少不必要的传输量。
2. **瞬态友好**：仅对 Git 协议层瞬态错误做有限重试，不重试语法/权限/认证类错误；非瞬态错误必须 fail-stop。
3. **命令级隔离**：所有 HTTP/1.1 fallback 通过 `git -c http.version=HTTP/1.1 fetch ...` 命令参数实现，不写持久配置。
4. **仅 fetch 可自动恢复**：所有 Git 写操作（merge/push）和环境变更（install/restart）都必须由操作人工决定 retry。
5. **可审计**：每次 fetch attempt 的远程、目标、次数、传输协议、exit code、错误分类都记录到 manifest，但不保存敏感信息。

### 3.3 Retry 状态机

```
                      ┌──────────────┐
                      │  Attempt 1   │  (常规环境/代理)
                      │ normal       │
                      └──────┬───────┘
                             │
                     ┌───────▼───────┐
                     │  exit_code    │
                     │  == 0?        │
                     └───┬───────┬───┘
                    Yes  │       │  No
                     ┌───▼──┐    │
                     │ done │    │ classify(stderr)
                     └──────┘    │
                                 ├─────────────────┬─────────────────┐
                                 │                 │                 │
                          transient          permanent       non_transport
                                 │                 │                 │
                          ┌──────▼──────┐         │                 │
                          │ Attempt 2   │         │  fail-stop      │  fail-stop
                          │ retry       │         │  (auth/perm/    │  (merge error/
                          │ (backoff)   │         │   invalid ref)  │   internal)
                          └──────┬──────┘         │                 │
                                 │                 │                 │
                          ┌──────▼───────┐        │                 │
                          │  exit_code   │        │                 │
                          │  == 0?       │        │                 │
                          └───┬──────┬───┘        │                 │
                         Yes  │      │  No        │                 │
                          ┌───▼──┐   │             │                 │
                          │ done │   │ classify() │                 │
                          └──────┘   │             │                 │
                                     │  transient  │                 │
                              ┌──────▼──────┐      │                 │
                              │ Attempt 3   │      │                 │
                              │ HTTP/1.1    │      │                 │
                              │ fallback    │      │                 │
                              └──────┬──────┘      │                 │
                                     │              │                 │
                              ┌──────▼───────┐     │                 │
                              │  exit_code   │     │                 │
                              │  == 0?       │     │                 │
                              └───┬──────┬───┘     │                 │
                             Yes  │      │  No     │                 │
                              ┌───▼──┐   │         │                 │
                              │ done │   │   fail-stop (exhausted)   │
                              └──────┘   │         │                 │
                                         ▼         ▼                 ▼
                                    [ERR] fetch failed after 3 attempts
                                        manifest records all attempts
                                UpgradeError with next_steps hint
```

- `classify(stderr)` 是纯函数：输入 git stderr，返回 `transient` / `permanent` / `non_transport`。
- Attempt 1→2 之间的退避：初次 2s，后续 5s（dry-run 不 sleep，只打印计划）。
- Attempt 3 额外注入 `-c http.version=HTTP/1.1` 参数。
- 任何 attempt 成功后立即返回，不等待剩余重试。
- 三次 attempt 失败后 emit `UpgradeError`，manifest 包含所有 attempt 详情。

## 4. 核心数据与状态定义

### 4.1 错误分类器契约

纯函数，输入 git subprocess 的 `stderr`（和可选的 `stdout`），输出分类：

| 分类 | 匹配模式（大小写不敏感） | 含义 | 是否重试 |
|---|---|---|---|
| `transient` | `rpc failed` | HTTP/协议层 RPC 失败 | 是 |
| `transient` | `gnutls recv error` | TLS 连接读取异常 | 是 |
| `transient` | `ssl_error_syscall` | OpenSSL 系统调用错误 | 是 |
| `transient` | `tls connection was non-properly terminated` | TLS 非正常关闭 | 是 |
| `transient` | `early eof` | 准备传输时连接关闭 | 是 |
| `transient` | `unexpected disconnect while reading sideband packet` | Git 协议 sideband 连接中断 | 是 |
| `transient` | `invalid index-pack output` | 数据包损坏（通常因传输中断） | 是 |
| `transient` | `connection reset by peer` | 对端重置连接 | 是 |
| `transient` | `connection refused` | 连接被拒绝（可能 proxy 临时不可用） | 是 |
| `transient` | `could not resolve host` | 临时 DNS 解析失败 | 是 |
| `transient` | `fatal: the remote end hung up unexpectedly` | 远端意外断开 | 是 |
| `transient` | `error: --stat` / `transfer closed` 伴随 `expected` | 传输字节数与预期不符 | 是 |
| `permanent` | `authentication failed` | 认证/凭据错误 | 否 |
| `permanent` | `access denied` / `permission denied` | 权限错误 | 否 |
| `permanent` | `repository not found` | 仓库不存在或无访问权限 | 否 |
| `permanent` | `fatal: couldn't find remote ref` | 无效 remote ref | 否 |
| `permanent` | `host key verification failed` | SSH 指纹不匹配 | 否 |
| `permanent` | `certificate verification failed` | 证书验证失败 | 否 |
| `permanent` | `unable to access` + `could not resolve host` 以外的网络错误 | 不可达（非临时 DNS） | 否 |
| `non_transport` | 其他（如 merge conflict、git 损坏） | 非 fetch 相关 | 否 |

### 4.2 Fetch attempt 审计记录

每次 fetch attempt 在 manifest `commands` 数组外新增独立 `fetch_attempts` 数组：

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
      "exit_code": 128,
      "failure_class": "transient",
      "retry_delay_seconds": 2
    },
    {
      "remote": "upstream",
      "target": "main",
      "attempt": 3,
      "transport": "http/1.1-fallback",
      "exit_code": 0,
      "failure_class": null,
      "retry_delay_seconds": 5
    }
  ]
}
```

- `transport` 取值：`"default"`（环境决定的 HTTP/2 或 HTTP/1.1）或 `"http/1.1-fallback"`。
- `failure_class`：`null` 表示成功，否则为 `"transient"` / `"permanent"` / `"non_transport"`。
- `retry_delay_seconds`：仅下一次重试前实际 sleep 的秒数；成功 attempt 的该字段为 `null`。
- 必须对 `stderr` 做脱敏（沿用现有 `redact()`）再写入 commands 摘要；不代表整个 stderr 进入 fetch_attempts。

### 4.3 Feature branch 保护修正契约

当前 `protect_local_commits()` 行为（V2.0）：

| 场景 | V2.0 行为 |
|---|---|
| 分支 = main | `git push origin main`（正确） |
| 分支 = feature-branch | `git push origin main`（错误：不保护 feature HEAD） |

V2.1 修正后行为：

| 场景 | 判定 | 行为 |
|---|---|---|
| HEAD 在 `origin/<branch>` 可达 | `git merge-base --is-ancestor HEAD origin/<branch>` | skips push，输出"已保护" |
| HEAD 不可达，`--preserve-features` 已启用 | `state.branch` 已知 | `git push -u origin <branch>`（非 force） |
| HEAD 不可达，未启用 `--preserve-features` | `state.branch` 已知 | `git push -u origin <branch>`（main 旧行为保留） |
| 任一种 push 失败 | exit != 0 | fail-stop，输出手动 push 命令 |

## 5. SPEC 概要

完整契约见 `docs/spec/10_infra/SPEC-10-006-hermes-upgrade-script-v2.md`。V2.1 新增/修改的关键规格：

| 编号 | 行为 | V2.0 状态 | V2.1 变更 |
|---|---|---|---|
| F2-011 | Target-aware fetch | 默认 `--tags` 全量 fetch | 默认 `--no-tags`，仅含目标 branch 或指定 tag |
| F2-012 | 分类 fetch 重试 | 无重试 | 3 次：normal → retry → HTTP/1.1 fallback |
| F2-013 | 瞬态错误分类 | 无 | 纯函数 classifier，narrow 模式匹配 |
| F2-014 | Manifest fetch attempt | 无 | `fetch_attempts` 数组 |
| F2-015 | 修正 branch 保护 | 硬编码 `push origin main` | 按当前分支验证可达性并 push 正确分支 |
| F2-016 | Dry-run 零网络 | 仅 skip 实际命令 | 明确声明不发网络、不 sleep、不写 ref |

## 6. 风险与应对

| 风险 | 概率 | 影响 | 应对 | 降级 |
|---|---|---|---:|---:|---|
| 瞬态重试掩盖真正问题（如 token 过期 → 重试 3 次后仍失败） | 中 | 中 | narrow classifier + max 3 次限制；fail-stop 输出明确 next_steps | operator 看到 3 次失败后判断为永久错误 |
| 重复 fetch 消耗更多时间 | 低 | 低 | 仅最多 3 次，backoff ≤5s；每次 attempt 独立 300s timeout | 用户可用 `--verbose` 观察每次 attempt |
| `http.version=HTTP/1.1` 导致慢速传输 | 中 | 低 | 仅作为最后的 fallback；不影响正常路径 | 正常路径仍使用系统默认 HTTP 版本 |
| classifier 漏标新瞬态错误模式 | 中 | 中 | 已涵盖 2026-07-30 失效的已知模式；新模式可通过后续小版本补充 | 漏标 = fail-stop，用户手动 retry |
| 分支保护修正对 main 分支产生副作用 | 低 | 高 | main 默认 `--branch main`，`push -u origin main` 行为等价 = V2.0 | Review 覆盖 main/feature 两场景测试 |
| `--patches-manifest` 中的 `upstream_pr` 字段误含 token | 低 | 中 | 字段是 PR URL/编号，不含 token；manifest 读取不走 redact 不影响 | Review 确认字段语义 |

## 7. 验收标准

### 7.1 T1 文档验收（本阶段）

- [x] RFC & SPEC 独立存在、版本号一致、互引用正确。
- [x] 明确 IN/OUT 边界：仅 Git fetch 相关修改，不触及 merge/install/restart/push retry。
- [x] 状态机图清晰表达 3 次 attempt 的决策路径。
- [x] 错误分类表覆盖已知瞬态与永久模式，使用 narrow/evidence-based 匹配。
- [x] Feature-branch 保护修正有分支感知的明确判定规则。
- [x] Manifest fetch_attempts schema 不包含代理 URL、凭证或未脱敏 stderr。
- [x] Dry-run 零网络、不 sleep、不写 Git ref 的声明明确。

### 7.2 T2/T3 实体验收（后续阶段）

- `classify_git_transport_failure(stderr)` 纯函数：单元测试覆盖分类表中所有 mode。
- `--dry-run --no-restart --no-push --version upstream/main`：输出 fetch 计划（仅 `upstream main --no-tags`），不发网络，不 sleep。
- `--dry-run --version upstream/v2026.7.1`：输出仅 fetch 该 tag 的计划。
- fetch 正常时仅一次 attempt，不 attempt 2/3。
- fetch 瞬态错误时，manifest 包含最多 3 次 `fetch_attempts`。
- fetch `permanent` 错误（如 `repository not found`）立即 fail-stop，不重试。
- `protect_local_commits()` 在 feature branch 上 push 当前 branch 而非 `main`。
- V1.0 和 V2.0 现有测试全量通过。

## 8. 开放问题

- classifier 如果遇到未知错误模式，是否默认归为 `permanent` 还是 `non_transport`？本 RFC 默认归为 `non_transport`（fail-stop），后续可根据运行反馈放宽。
- `fetch_attempts` 中的 `retry_delay_seconds` 是否需要在 finally 字段也写入 manifest？本 RFC 只在前一次 attempt 字段中记录，下游可组合计算总耗时。
- 是否需要在 `UpgradeConfig` 中新增 `--max-fetch-attempts` 覆盖 3 的上限？本 RFC 不加，保持简单；后续如果发现需要调节，可通过 V2.2 增量添加。

## 9. 参考资料

- `docs/rfc/10_infra/RFC-10-005-hermes-auto-upgrade.md`
- `docs/spec/10_infra/SPEC-10-005-hermes-auto-upgrade.md`
- `docs/rfc/10_infra/RFC-00-000-rfc-template.md`
- `scripts/upgrade/upgrade_hermes_agent.py`（尤其是 `fetch_remotes()` 和 `protect_local_commits()`）
- 2026-07-30 升级 manifest（`/tmp/hermes-upgrade-20260730-224109.json`）
- `.hermes/plans/2026-07-30_225320-hermes-upgrade-transport-resilience.md`
- Hermes Agent docs: `https://hermes-agent.nousresearch.com/docs/`
