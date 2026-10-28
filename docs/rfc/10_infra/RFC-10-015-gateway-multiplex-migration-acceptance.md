# RFC-10-015：Hermes 网关多路复用迁移验收归档

| 项 | 值 |
|---|---|
| 状态 | 已冻结（事后归档） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-10-28 |
| 最后更新 | 2026-10-28 |
| 版本号 | V1.1 |
| 来源 | 主控会话迁移执行记录 + Kanban t_afd21921 |
| 目标模块 | 10_infra（基础设施 / 服务治理） |
| 适配 Agent | YQuant-Developer-Engineer（无，本卡零代码）、YQuant-Test-Engineer（验证） |

关联文档：
- [SPEC V1.1](../../spec/10_infra/SPEC-10-015-gateway-multiplex-migration-acceptance.md)
- [DESIGN V1.1](../../design/10_infra/DESIGN-10-015-gateway-multiplex-migration-acceptance.md)
- 前置契约：RFC/SPEC/DESIGN-10-010（readiness 与冷启动治理）

---

## 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-10-28 | 初始创建：固化 2026-10-27~28 网关多路复用迁移的两类契约变更（双层就绪探针口径、冷启动 audit unit 引用），归档六项验收实测证据、模型/代理配置变更、回滚资产与八项遗留 | YQuant-Principal |
| V1.1 | 2026-10-28 | T3 修复：修正 §1.1 与 D2 的 `platform_evidence` 来源描述（实现为 `gateway_state.json` 条目 `updated_at` 派生；journal 命中 `P-GWY-3J` 只被计算、不进入输出）；遗留披露扩为九项（新增 L9）；L7 DNS 失败计数改为区间口径 | YQuant-Principal |

---

## 1. 背景与原因

2026-10-27 23:56 – 2026-10-28 00:03（Asia/Shanghai），Hermes Gateway 从「每 profile 一个 systemd
user unit」迁移为「单 unit 多路复用」：

- `hermes-gateway.service`（default unit）服务全部 8 个 profile：
  `default, yinglong, yinglongdesigner, yquant, yquantdeveloper, yquantprincipal, yquantreviewer, yquanttester`
- 原 `hermes-gateway-yquant.service` / `hermes-gateway-yinglong.service` 已从磁盘删除
- 临时 `hermes-gateway-migrate-runner.service` oneshot 已创建并清理

迁移产生两类**必须固化的契约变更**（本卡的核心交付）：

### 1.1 变更 1：就绪探针口径（实现已变，SPEC-10-010 §4.3 仍陈旧）

SPEC-10-010 §4.3 仍写：

- 前置条件 `_SYSTEMD_UNIT=hermes-gateway-yquant.service` 或 `hermes-gateway-yinglong.service`
  （两个 unit 已删除）
- 判定依据 = `journalctl --since` 的字符串匹配（`"connected"` / `"session started"` /
  `"platform.*connected"` / `"WebSocket.*connected"`）

实际已改为（见 `scripts/service_readiness/readiness_probe.py`，commit `15238e4`）：

- **unit 层**：`hermes-gateway.service` 的 `ActiveState=active` 且 `MainPID != 0`
- **profile 层**：`~/.hermes/gateway_state.json` 的
  `platforms["<profile>:feishu"].state == "connected"`
- **陈旧防护**：要求 `platforms["<profile>:feishu"].writer_pid` == 当前 `MainPID`
- **journal 降级为辅证**：journal 命中（`P-GWY-3J`）只被计算、不进入任何输出，
  **不参与** per-profile 判决（单 unit journal 无法区分 profile）；`platform_evidence`
  的来源是 `gateway_state.json` 条目 `platforms["<profile>:feishu"].updated_at`
  经有界脱敏，而非 journal

profile 键映射：`<profile>:feishu`，gw-yquant→`yquant`、gw-yinglong→`yinglong`。

### 1.2 变更 2：冷启动 audit unit 依赖引用

`~/.config/systemd/user/yquant-boot-readiness-audit.service` 的 `Wants`/`After`
原引用已删除的 per-profile 双 unit，已改为 `hermes-gateway.service`（各两行）。

### 1.3 证据边界（必须如实声明）

1. **本 RFC 是事后归档**：迁移已发生并已验证；文档不追认迁移中被跳过的门禁，
   也不构成任何新的实施授权。
2. 模型与代理配置变更（yquant config 切换 `gpt-6.1-sol`、统一代理 + NO_PROXY 分流）
   在同一会话完成，本文档一并记录，但属独立于探针契约的配置事实。
3. commit `15238e4` 已确认在 origin/main（`git push` 返回 Everything up-to-date）；
   其后是否有后续推送未知（遗留 L8）。
4. `bot/v3/info` 的 app_id 凭据值不写入任何文档；仅断言两个 app_id 互不相同。

---

## 2. 目标与非目标

### 2.1 目标

1. 将双层就绪判定契约（unit 层 + profile 层 + 陈旧防护 + journal 辅证降级）固化为
   可执行、可测试的 SPEC（`F-GWY-N` 编号规格）。
2. 固化冷启动 audit unit 的引用修正及其验证读回口径（`F-AUD-N`）。
3. 在 Design 中逐项记录六项验收的实测证据（命令 + 实际读数），并明确区分
   T1 自测与 T2 独立验证，形成可复现的回归基线。
4. 记录模型 fallback 链与代理口径的当前状态，供回归对照。
5. 如实披露九项遗留（不粉饰、不追认）。

### 2.2 非目标

1. 不修改任何代码、systemd 配置、cron、生产数据库；不重启任何服务。
2. 不修订 SPEC-10-010 正文（取代关系在 10-015 SPEC 中显式声明；是否回写 010 另行裁决）。
3. 不追认迁移中被跳过的门禁；不为「文档好看」补做任何实施动作。
4. 不发起新的真实模型调用消耗配额（六项验收中的真实调用证据来自迁移会话的一次性实测）。
5. 不把 `probe_count=0` 与 schema `minimum=1` 的既有矛盾在本卡内修复（如实记录为遗留）。

---

## 3. 变更范围

### 3.1 已完成的实现与提交（本卡不重复实现）

| 对象 | 状态 | 位置 |
|---|---|---|
| `scripts/service_readiness/readiness_probe.py` | 已改（commit `15238e4`，已推 origin/main） | 仓库 |
| `scripts/service_readiness/tests/test_readiness_probe.py` | 已改（同 commit） | 仓库 |
| `yquant-boot-readiness-audit.service` 的 `Wants`/`After` 两行 | 已改 | 本机 `~/.config/systemd/user/`（非仓库） |
| `~/.hermes/profiles/yquant/config.yaml` 模型段 | 已改（有备份） | 本机 profile 配置 |
| default drop-in 代理 env | 已统一引用 `~/.config/quantdinger/gateway-proxy-gateway.env`（原 per-profile 两个 env 已删除） | 本机 systemd 配置 |

### 3.2 本卡新增（唯一允许修改的三个文件）

| 文档 | 路径 |
|---|---|
| RFC | `docs/rfc/10_infra/RFC-10-015-gateway-multiplex-migration-acceptance.md`（本文件） |
| SPEC | `docs/spec/10_infra/SPEC-10-015-gateway-multiplex-migration-acceptance.md` |
| Design | `docs/design/10_infra/DESIGN-10-015-gateway-multiplex-migration-acceptance.md` |

三层文档分别独立成文件，不合并；互相以相对链接引用。

---

## 4. 关键决策

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | 双层就绪口径：unit 层判进程（`ActiveState=active` + `MainPID != 0`），profile 层判连接（`gateway_state.json` 的 `platforms["<profile>:feishu"].state`），`writer_pid == 当前 MainPID` 作陈旧防护 | 单 unit journal 无法归因 profile；per-profile 判决只能来自 gateway 状态文件。状态文件在网关宕机期间不刷新，`writer_pid` 防护避免把上一次网关生命周期的陈旧 `connected` 误判为在线 |
| D2 | journal 降级为辅证：命中行只被内部计算（`P-GWY-3J`），不参与 per-profile 判决，也不写入 `platform_evidence`；`platform_evidence` 来自 `gateway_state.json` 条目的 `updated_at`（经有界脱敏） | journal `connected` 行不含 profile 名，两个 profile 会共享同一份证据，无法作为判决依据；「判决依据」与「证据字段来源」分离：判决与字段来源均不依赖 journal |
| D3 | SPEC-10-010 关系：010 §4.3（及 §3.2.3/§3.2.4 的 per-profile unit 引用）被 10-015 SPEC 取代 | 010 引用的两个 unit 已从磁盘删除，其口径已不可执行；不重写 010 正文，避免扩大本卡范围。是否回写 010（建议追加一行指针对照）另行裁决 |
| D4 | 代理口径：统一走代理 + `NO_PROXY` 域名分流（国内模型/飞书/内网直连，OpenAI/Codex/Claude 等海外服务走代理），不按 profile 拆分 | Pascal 已确认；default drop-in 统一引用中性 env 文件，消除 per-profile 重复 |
| D5 | 机器人归属不变：gw-yquant↔`yquant:feishu`、gw-yinglong↔`yinglong:feishu` 映射不变 | 迁移只改 unit 拓扑，不改机器人凭据与消息归属 |

---

## 5. 六项验收结论摘要

实测证据（命令 + 读数）逐项落在本卡 Design；此处仅记结论与证据来源。

| 项 | 内容 | 结论 | 证据来源 |
|---|---|---|---|
| a | default unit + 8 profiles：`hermes-gateway.service` active、`MainPID != 0`、`gateway_state.json` `served_profiles` 恰为 8 个 | 通过 | T1 自测（迁移会话 + 归档会话复核）；实现卡 T2（run 3318）已独立验证探针实现行为（间接佐证） |
| b | 双 bot 在线、app_id 不串号：`yquant:feishu` 与 `yinglong:feishu` 均 connected 且 `writer_pid` = 当前 MainPID；各自凭据调 `bot/v3/info` 返回两个互不相同的 app_id | 通过 | T1 迁移会话实测（app_id 值不入文档）+ T1 归档会话复核 connected/writer_pid |
| c | 知识卡片真实点击 E2E：真实点击「详情」「下一条」产生导航文件、receipts 两条 defer、4 个 card_id 映射更新，无 handler 失败告警、无红卡降级 | 通过 | T1 迁移会话实测 + T1 归档会话复核导航文件与 receipts |
| d | 代理变量 + `gpt-6.1-sol` 真实调用：网关进程含 6 个 proxy 变量；api.openai.com 经代理 401（鉴权正常）、example.com 经代理 200、api.minimaxi.com 经 NO_PROXY 直连；yinglong/yquant 两侧真实调用各成功一次（exit 0） | 通过 | T1 迁移会话一次性实测（不重复消耗配额）+ T1 归档会话复核 config 模型段 |
| e | cron 数量：yquant `total=6 enabled=6`、yinglong `total=2 enabled=2` | 通过 | T1 自测（迁移会话 + 归档会话复核） |
| f | WSL 冷启动：boot_id 变化证实真冷启动；boot → 双 bot 就绪 85 秒（无 3 分钟盲区）；boot-readiness audit Result=success exit 0 | 通过 | T1 迁移会话实测 + T1 归档会话复核 boot_id 与 unit 现状 |

---

## 6. 回滚与遗留指向

- 回滚资产清单（迁移前 drop-in 归档、孤儿资产备份、audit unit 修改前备份及其 SHA256、
  config 修改前备份）与逐项操作边界：见 Design §6。
- 九项遗留（`probe_count=0` 与 schema 矛盾、010 §4.3 陈旧、T1 首次 run 3316 超时、
  T2 流程偏离、adapter 成功路径无日志、`[DIAG]` 日志消失、DNS 解析失败约 400–750 条
  （依统计口径，L7）、事后归档性质、`platform_evidence` 来源描述偏差（V1.1 修正，L9））：
  见 Design §7，逐项如实披露，本卡不修复、不粉饰。

---

## 版本记录

V1.0（2026-10-28）：初始创建（事后归档）。所有数字来自迁移会话实测或归档会话复核，
无编造；凭据、token、app_id 明文一律不入文档。

V1.1（2026-10-28）：T3 修复（Kanban t_368a7769）。修正 §1.1 与 D2 中 `platform_evidence`
来源描述（实现：`gateway_state.json` 条目 `updated_at` 经有界脱敏；journal 命中 `P-GWY-3J`
只被计算、不进入任何输出，判定依据与字段来源均不依赖 journal）；遗留披露扩为九项
（新增 L9 记录本次描述偏差修正）；L7 DNS 失败计数改为区间口径（约 400–750 条，依统计口径）。
