# DESIGN-10-015：Hermes 网关多路复用迁移验收证据与回归基线

| 项 | 值 |
|---|---|
| 状态 | 已冻结（事后归档） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-10-28 |
| 最后更新 | 2026-10-28 |
| 版本号 | V1.2 |
| 来源RFC | RFC-10-015-gateway-multiplex-migration-acceptance |
| 目标模块 | 10_infra（基础设施 / 服务治理） |
| 适配Agent | YQuant-Test-Engineer（独立验证） |

关联文档：
- [RFC V1.1](../../rfc/10_infra/RFC-10-015-gateway-multiplex-migration-acceptance.md)
- [SPEC V1.1](../../spec/10_infra/SPEC-10-015-gateway-multiplex-migration-acceptance.md)

---

## 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-10-28 | 初始创建：承载六项验收实测证据、双层口径精确实现路径、systemd 两行修正 patch 与验证读回、回归基线、回滚资产与八项遗留 | YQuant-Principal |
| V1.1 | 2026-10-28 | T3 修复：修正 §2.5/§2.6/§5 的 `platform_evidence` 来源描述（状态文件 `updated_at` 派生；journal 命中只被计算、不进入输出）；§4.d 代理地址脱敏；§4.f audit 时序口径明确化；L7 计数区间化；新增 L9 遗留记录本次描述偏差修正 | YQuant-Principal |
| V1.2 | 2026-10-28 | T5 修复：更正 §4.f 中 audit 完成时刻的来源与字段归因——01:47:18 为 systemd `ExecMainExitTimestamp` 字段读数（非「journal 中最后一条 audit ready 输出时刻」）；ready 输出经 `logs/boot-readiness-audit.log` 文件 append、不经 journald（journalctl 检索 0 命中） | YQuant-Principal |

---

## 1. 已核实的运行时事实（T1 归档会话复核，2026-10-28）

以下读数由本卡 T1 在文档归档会话中只读复跑核实（与迁移会话实测一致）：

| 事实 | 实际读数 | 复核命令（只读） |
|---|---|---|
| unit 状态 | `hermes-gateway.service` → `ActiveState=active`、`MainPID=1057` | `systemctl --user show hermes-gateway.service -p ActiveState -p MainPID --value` |
| served_profiles | 恰为 8 个：`default, yinglong, yinglongdesigner, yquant, yquantdeveloper, yquantprincipal, yquantreviewer, yquanttester` | 读 `~/.hermes/gateway_state.json` |
| 双 platform 条目 | `yquant:feishu` → `state=connected, writer_pid=1057`；`yinglong:feishu` → 同 | 同上 |
| audit unit 引用 | `Wants=`/`After=` 两行均含 `hermes-gateway.service`；grep `hermes-gateway-<profile>.service` 命中 0 | `grep -nE '^(Wants\|After)=' ~/.config/systemd/user/yquant-boot-readiness-audit.service` + `grep -cE 'hermes-gateway-[a-z]+\.service'` |
| cron 数量 | yquant `total=6 enabled=6`；yinglong `total=2 enabled=2` | 读 `~/.hermes/profiles/{yquant,yinglong}/cron/jobs.json` |
| 导航文件 | `weekly-review-f744d394265c4733ab14c7df86efdede.json` 存在；`issued_at=2026-10-28T00:03:48+00:00`、`expires_at=2026-10-28T02:03:48+00:00`、含 `binding_integrity`、`entry_ref=2026-10-21-…dfb411-量化底座工程适配与实盘可靠性应分开评价` | 读该 JSON 文件 |
| receipts 末两条 | `txn-000027` @`2026-10-28T00:03:38+00:00`、`txn-000028` @`2026-10-28T00:03:48+00:00`，均 `action=defer` / `state=deferred` | `tail -2 ~/.hermes/profiles/yinglong/state/review_v2/receipts.jsonl` |
| config 模型段 | `model.default=gpt-6.1-sol`、`provider=openai-codex`、`supports_vision: true`；fallback 三条：`custom:minimax/MiniMax-M3.1-Flash` → `zai/glm-5.3-flash` → `deepseek/deepseek-v4-flash` | 读 `~/.hermes/profiles/yquant/config.yaml`（脱敏读取，不打印凭据） |
| audit 备份 SHA256 | `e0649206643e4a85891275f3346a2027170f90bc0d397b5c36729379a0ccf9d7`（原件与备份一致） | `sha256sum ~/.hermes/profiles/yquant/backups/yquant-boot-readiness-audit.service.pre-multiplex-alignment-20261028` |
| commit `15238e4` | `readiness_probe.py` +204 行级改动、`test_readiness_probe.py` +411 行级改动（合计 571 insertions / 44 deletions），已推 origin/main | `git show --stat 15238e4` |
| boot_id | `8801e629-3a21-4047-9284-bb406f5093ff`（与冷启动实测一致） | `cat /proc/sys/kernel/random/boot_id` |

---

## 2. 双层口径的精确实现路径（对应 readiness_probe.py 实际行为）

commit `15238e4` 后的 `scripts/service_readiness/readiness_probe.py`：

1. **unit 常量**：`GW_UNIT = "hermes-gateway.service"`（L58）；迁移说明注释（L52-57）明确
   per-profile 双 unit 已删除。
2. **profile 映射**：`GW_SERVICE_PROFILES = {gw-yquant: yquant, gw-yinglong: yinglong}`（L63-66）；
   状态文件路径 `~/.hermes/gateway_state.json`（L67）。
3. **P-GWY-1**（`probe_gwy_p1`，L298）：`systemctl --user is-active --quiet <unit>`。
4. **P-GWY-2**（`probe_gwy_p2`，L306）：MainPID 复用（网关轮已为陈旧防护解析过 MainPID，
   避免二次 systemctl 查询）+ `ps -p <pid>` 存活检查。
5. **P-GWY-3**（`probe_gwy_p3`，L392）：读 `platforms["<profile>:feishu"]`；判定顺序固定为
   先 `writer_pid`（缺失→`platform_writer_pid_missing`；非正整数→`platform_writer_pid_invalid`；
   ≠当前 MainPID→`platform_state_stale`）后 `state=="connected"`（否则→`platform_not_connected`）。
   陈旧记录一律判**无证据**（unknown），绝不判 connected——状态文件在网关宕机期间不刷新，
   上一次生命周期的陈旧 `connected` 不能冒充在线。判定通过后，以该条目 `updated_at`
   经 `_sanitize_evidence` 合成 `platform_evidence`（L434-436；含 profile 名，128 字上限）
   ——这是 `platform_evidence` 的**唯一来源**。
6. **journal 辅证**（`probe_gwy_journal_connected`，L342）：只查
   `_SYSTEMD_USER_UNIT=hermes-gateway.service` 自 unit active 时刻起的日志；命中行经
   `_sanitize_evidence`（L323，保留时间戳 + 有界类别）构成 `P-GWY-3J`，**只被计算、
   从不进入输出**——`_evaluate_gwy`（L720-729）只取 `results["P-GWY-3"][3]`。
   journal 既不是 per-profile 判定的依据，也不是 `platform_evidence` 的来源。
   实测佐证（T2 独立取证，2026-10-28）：探针输出
   `platform_evidence="2026-10-27T23:46:20.61797 [connected (profile: yquant)]"` 与
   `gateway_state.json` 中该条目 `updated_at=2026-10-27T23:46:20.617977+00:00` 同源
   （ISO+T+微秒格式），而非 journal 的 `2026-10-27 23:46:20` 格式。
7. **状态机**：`_evaluate_gwy`（L720）——ready ⇔ P-GWY-1 ∧ P-GWY-2 ∧ P-GWY-3；
   unit 层 PASS 而 profile 层 FAIL → `degraded/unknown`；unit 层 FAIL → `starting`。
8. **零副作用**：全部为 GET/读命令；`--report` 仅在 `--all` 下写入 canonical 报告路径；
   本次归档复核未带 `--report` 执行。

---

## 3. systemd 两行修正的精确 patch 与验证读回

文件：`~/.config/systemd/user/yquant-boot-readiness-audit.service`（本机配置，非仓库）。

实际 diff（2026-10-28 归档会话 `diff -u` 实测；备份 vs 当前）：

```diff
--- ~/.hermes/profiles/yquant/backups/yquant-boot-readiness-audit.service.pre-multiplex-alignment-20261028
+++ ~/.config/systemd/user/yquant-boot-readiness-audit.service
@@ -1,7 +1,7 @@
 [Unit]
 Description=YQuant four-service boot readiness audit (read-only)
-Wants=daily-stock-analysis.service tradingagents-cn.service hermes-gateway-yquant.service hermes-gateway-yinglong.service
-After=daily-stock-analysis.service tradingagents-cn.service hermes-gateway-yquant.service hermes-gateway-yinglong.service
+Wants=daily-stock-analysis.service tradingagents-cn.service hermes-gateway.service
+After=daily-stock-analysis.service tradingagents-cn.service hermes-gateway.service
```

验证读回（本卡归档会话实测）：

- `grep -nE '^(Wants|After)=' …` → 第 3/4 行均为
  `… daily-stock-analysis.service tradingagents-cn.service hermes-gateway.service`
- `grep -cE 'hermes-gateway-[a-z]+\.service'` → `0`（无孤儿 unit 引用）
- systemd 运行时视图：`systemctl --user show yquant-boot-readiness-audit.service
  -p Wants -p After` 由 T2 独立核验（run 3318）；本卡未重跑（该命令在迁移会话已实测一致）。

---

## 4. 六项验收的逐项实测证据

来源标注约定：**[T1自测-迁移]** = 2026-10-27~28 迁移会话实测；
**[T1复核-归档]** = 本卡归档会话（2026-10-28）只读复跑；
**[T2独立-实现卡]** = 实现卡（readiness 探针对齐）的 tester 独立验证
（run 3318 / comment 3139，verdict PASS），针对探针实现行为；与本卡文档产出的
验证任务（yquanttester）是两回事。
未执行的真实调用类证据只引用 [T1自测-迁移]，本卡未重复消耗配额。

### a. default unit + 8 profiles ✅

- [T1自测-迁移] `systemctl --user show hermes-gateway.service` → `ActiveState=active`,
  `MainPID=1057`；`gateway_state.json` `served_profiles` = 8 个（清单见 §1）。
- [T1复核-归档] 同读数复现（§1 表）。
- [T2独立-实现卡] run 3318 独立验证的是探针**实现行为**（pytest 30 passed +
  systemd 两行补丁独立校验），构成对 a 项的间接佐证；a 项的端到端读数以
  T1 自测/复核为准。

### b. 双 bot 在线、app_id 不串号 ✅

- [T1自测-迁移] `platforms["yquant:feishu"]` / `platforms["yinglong:feishu"]` 均
  `connected, writer_pid=1057`；各自凭据调 `bot/v3/info` → 两个 app_id **互不相同**
  （凭据值不入文档）。
- [T1复核-归档] connected 与 `writer_pid=1057` 复现；app_id 未重新调用。

### c. 知识卡片真实点击 E2E ✅

- [T1自测-迁移] 真实点击「详情」「下一条」（2026-10-28 08:03:48 CST）：
  - adapter 构造期 scoped snapshot 取到 handler → `subprocess.run([sys.executable, handler])` 真实执行；
  - handler 动作词表：`detail`/`next` 属 `_NAVIGATION_ACTIONS`（导航，不执行）；`_EXECUTABLE_ACTIONS` 仅 `reject`；
  - 导航产物：`…/review_v2/navigation/weekly-review-f744d394265c4733ab14c7df86efdede.json`
    （`issued_at=2026-10-28T00:03:48Z`、`expires_at=…T02:03:48Z`、含 `binding_integrity`、
    `entry_ref=2026-10-21-…dfb411-量化底座工程适配与实盘可靠性应分开评价`）；
  - `review_v2/receipts.jsonl` → `txn-000027` @00:03:38、`txn-000028` @00:03:48，
    均 `action=defer` / `state=deferred`；
  - `review_v2/origin-card-update/mappings/` 下 4 个 card_id 映射文件同步更新；
  - **无** adapter `knowledge card handler failed` warning、**无**红卡降级 → 证明 handler 真实执行而非降级。
  - 已知取证盲区：adapter 成功路径无日志（仅异常 warning），故以持久化副作用取证（遗留 L5）。
- [T1复核-归档] 导航文件与 receipts 末两条复现（§1 表）。

### d. 代理变量 + gpt-6.1-sol 真实调用 ✅

- [T1自测-迁移] 网关进程 environ 含 6 个 proxy 变量（`HTTP_PROXY=http://<windows-host>:7897` 等；
  具体主机地址属本机网络拓扑信息，见本机配置文件，不入仓库）；
  api.openai.com 经代理 → HTTP 401（1.28s，到达鉴权层）；example.com 经代理 → HTTP 200；
  api.minimaxi.com 经 NO_PROXY 直连 → HTTP 404（0.37s）；
  `hermes -p yinglong -m gpt-6.1-sol -z "…"` → `CODEX_PROXY_OK`, exit 0；
  yquant 侧同样 → `YQUANT_GPT_OK`, exit 0。
- [T1复核-归档] 仅复核 config 模型段（§1 表）；未重新发起任何模型调用（约束 F-CON-1）。

### e. cron 数量 ✅

- [T1自测-迁移] yquant `total=6, enabled=6`；yinglong `total=2, enabled=2`。
- [T1复核-归档] 同读数复现（§1 表）。

### f. WSL 真冷启动 ✅

- [T1自测-迁移] 重启前 `boot_id=9818633b-…, btime=1793110193`；重启后
  `boot_id=8801e629-3a21-4047-9284-bb406f5093ff, btime=1793123148, uptime 12min`
  → boot_id 变化 = 真冷启动。时序：01:45:40 Windows 保活 runner 触发 → 01:45:45
  PROXY_FAILOPEN 生效 → 01:45:48 WSL 内核启动 → 01:46:14 DSA + TA-CN unit 拉起 →
  01:46:16 hermes-gateway 拉起 → 01:46:26 runner 确认 Redis 6379/6380 监听 →
  01:46:38 boot-readiness audit unit 启动（systemd 实测
  `ExecMainStartTimestamp=2026-10-28 01:46:38 CST`）→
  01:47:13 yinglong:feishu WS connected → 01:47:14 yquant:feishu WS connected →
  01:47:18 audit unit 退出时刻（T5 自测 systemd 四字段：
  `ExecMainStartTimestamp=2026-10-28 01:46:38 CST` /
  `ExecMainExitTimestamp=2026-10-28 01:47:18 CST`（oneshot 类型存在该独立完成
  时刻字段，V1.0/V1.1「无独立完成时刻字段」的表述不成立）/ `Result=success` /
  `ExecMainStatus=0`，exit 0）。
  ready 输出落盘更正：四服务 ready 的 ndJSON 行由探针进程 append 到项目日志文件
  `logs/boot-readiness-audit.log`（T5 实测末行
  `gw-yinglong … "status": "ready"`，文件 mtime 01:47），**不经 journald**——
  `journalctl --user` 检索 `boot-readiness` 为 0 命中；V1.0/V1.1 把 01:47:18
  归因为「journal 中最后一条 audit ready 输出时刻」属来源错误，现更正为
  `ExecMainExitTimestamp` 字段读数。
  boot → 双 bot 就绪 **85 秒**（无 3 分钟盲区）。抢锁检查：journal 唯一 "lock" 命中
  为 Kafka 客户端无害重试日志，无 Kanban/systemd 抢锁。
- [T1复核-归档] 当前 `boot_id=8801e629-…` 复现（§1 表）；未重启服务。

### 探针实跑（T1 复核，2026-10-28 归档会话）

```
python3 scripts/service_readiness/readiness_probe.py --all --timeout 5 --interval 5 --max-retries 2
→ exit=0
DSA:        ready, probe_count=1, /health 200
TA-CN:      ready, probe_count=0, /api/readyz 200   ← probe_count=0（遗留 L1）
gw-yquant:  ready, platform_connected=confirmed_at_boot, probe_count=0（遗留 L1）
gw-yinglong: ready, platform_connected=confirmed_at_boot, probe_count=0（遗留 L1）
```

pytest 全集（区分口径）：

- **T1 自测**（迁移会话）：30 passed in 39.06s（`env -u … .venv/bin/python -m pytest
  scripts/service_readiness/tests/ -q`，全集仅独立执行一次）。
- **T2 独立验证**：run 3318 / comment 3139，verdict PASS；本卡未重复执行全集。

---

## 5. 回归基线（本卡归档会话快照，2026-10-28）

| 维度 | 基线值 |
|---|---|
| 冷启动时序 | boot → 双 bot 就绪 85 秒；关键节点见 §4.f（[T1自测-迁移]） |
| unit 状态 | `hermes-gateway.service` active，MainPID=1057（归档会话读数） |
| gateway_state 结构 | served_profiles 8 个 + `yquant:feishu` / `yinglong:feishu` 双条目（connected + writer_pid=MainPID） |
| `platform_evidence` 来源 | `gateway_state.json` 条目 `platforms["<profile>:feishu"].updated_at` 经有界脱敏（含 profile 名，128 字上限）；journal 命中（`P-GWY-3J`）只被计算、不进入输出——不得误读为 journal 佐证 |
| 代理路由 | 网关进程 6 个 proxy 变量；海外模型服务走代理、国内模型/飞书/内网 NO_PROXY 直连；default drop-in 引用 `~/.config/quantdinger/gateway-proxy-gateway.env` |
| fallback 链 | `gpt-6.1-sol`（openai-codex, supports_vision=true）→ `custom:minimax/MiniMax-M3.1-Flash` → `zai/glm-5.3-flash` → `deepseek/deepseek-v4-flash` |
| 探针输出 | `--all` 四服务 ready，exit 0（§4 探针实跑） |

---

## 6. 回滚资产清单

| 资产 | 路径 | 说明 |
|---|---|---|
| 迁移前 drop-in 归档 | `~/.hermes/profiles/yquant/backups/pre-multiplex-20261027-235611/drop-ins.tgz` | 迁移前 per-profile drop-in 全量归档 |
| 孤儿资产清理前备份 | `~/.hermes/profiles/yquant/backups/post-multiplex-20261028-orphans/` | 含 `hermes-gateway-migrate-runner.service` 与两个旧 drop-in 目录（归档会话 `ls` 确认在） |
| audit unit 修改前备份 | `~/.hermes/profiles/yquant/backups/yquant-boot-readiness-audit.service.pre-multiplex-alignment-20261028` | SHA256 `e06492…ccf9d7`，与修改前原件一致（§1 表） |
| yquant config 修改前备份 | `~/.hermes/profiles/yquant/backups/config.yaml.bak-20261028-011408-pre-gpt-model` | 模型段回滚点 |

回滚操作边界：回滚属生产 systemd/config 写操作，须 Pascal 明确授权后执行；
本卡仅登记资产位置，不执行任何回滚。

---

## 7. 残余风险与遗留（九项，如实披露）

| 编号 | 遗留 | 影响 | 处置建议 |
|---|---|---|---|
| L1 | `probe_count=0` 与状态 schema `minimum=1`（SPEC-10-010 §4.1/§4.2）不一致 | gateway/TA-CN 快速 ready 时 `probe_count=0`，按 010 schema 不合法 | 后续卡片裁决：修 schema（允许 0）或修探针（首检成功记 1）；本卡不修复 |
| L2 | SPEC-10-010 §4.3（及 §3.2.3/§3.2.4）仍写已删除 unit 与 journal 字符串匹配口径 | 文档与实现不一致；以 10-015 SPEC §1 取代声明为准 | 建议在 010 追加一行指针对照（不重写正文）；是否执行另行裁决 |
| L3 | T1 首次 run 3316 iteration budget 超时；完成结果来自 run 3317 | 该 10-015 前置实现卡的首次执行未在预算内完成 | 不得把超时记录追认为成功；仅 run 3317 结果有效 |
| L4 | T2（10-014 流程）曾有辅助只读 Python 命令审批被拒后改用其他只读取证路径 | 流程偏离；功能 PASS 不使偏离合规 | 记录在案；后续单查询模式审批策略由 Pascal 裁决 |
| L5 | adapter 成功路径无日志，仅异常 warning | handler 真实执行只能靠持久化副作用取证，存在取证盲区 | 如需更强证据链，另立卡片在 adapter 成功路径加日志（本卡不做） |
| L6 | adapter 模块路径迁移后旧 `[DIAG]` 日志消失（`hermes_plugins.feishu_platform.adapter` → `hermes_plugins.platforms__feishu__home_8b01f502a535.adapter`） | 依赖 `[DIAG]` 的诊断手段在迁移后失效 | 与 L5 同卡处置或接受现状 |
| L7 | 2026-10-28 07:42 前存在大量 `open.feishu.cn` DNS 解析失败：约 400–750 条（依统计口径不同：journal 行数 / token 出现次数 / profile 日志行数；T2 独立复测——journal `2026-10-27 13:00→2026-10-28 07:42` 为 402 行/1155 token 次、`2026-10-28 00:00→07:42` 为 318 行/903 次、两 profile 日志 gateway.log+errors.log 合计 1233 行且 07:42 前 749 行；T1 迁移会话原始计数 573 的统计口径未能复现，原值保留备考）（现已恢复：07:44:20 后为 0），当时可能导致知识卡片点击「转圈」 | 曾影响点击体验；根因未深究 | 已恢复；若复现，另立卡片排查 DNS 链路 |
| L8 | `15238e4` 之后是否有后续推送未知（该 commit 已确认在 origin/main） | 归档时点快照可能滞后 | 后续涉及 readiness 的卡片须先 `git fetch` 复核 HEAD |
| L9 | V1.0 三份文档（RFC §1.1/D2、SPEC F-JRN-1、DESIGN §2.6/§5）把 `platform_evidence` 描述为「journal 命中行经脱敏写入」，与实现不符：实现中该字段由 `probe_gwy_p3` 以 `gateway_state.json` 条目 `updated_at` 合成（`readiness_probe.py` L434-436），journal 命中（`P-GWY-3J`）只被计算、不进入输出 | 读者可能把 journal 误当 per-profile 判定依据或证据字段来源 | 该冲突此前未在文档披露，由 T2 独立验证（2026-10-28）首次发现；V1.1 已修正全部表述，本行如实记录偏差、不追认 V1.0 表述为当时正确 |

---

## 8. Design 验收清单（checkbox）

- [x] RFC / SPEC / Design 三份独立文件存在，路径与命名符合任务约定
- [x] 三份文档互相引用（RFC↔SPEC↔Design 相对链接有效）
- [x] SPEC 含元数据表、版本历史表、编号功能规格表（F-GWY/F-JRN/F-AUD/F-ACC/F-REG/F-CON）
- [x] Design 含元数据表、版本历史表、实测证据（§1/§4）、回归基线（§5）、回滚资产（§6）、
      残余风险（§7）、验收清单（本节）
- [x] 六项验收在 §4 逐项有实测命令与真实计数，且明确区分 T1 自测 / T1 归档复核 / T2 独立验证
- [x] 九项遗留（L1–L9）全部如实披露
- [x] 无任何凭据、token、app_id 明文（app_id 仅以「互不相同」脱敏形式出现）
- [x] `git status` 仅显示这 3 个新增文件，无其他改动
- [x] 未产生任何副作用（无服务重启、无生产写入、无 git 提交、无 `--report` 报告写入）

---

## 版本记录

V1.0（2026-10-28）：初始创建（事后归档）。全部数字来自 [T1自测-迁移] 或
[T1复核-归档] 的真实读数；T1 首次 run 3316 超时未被追认为成功（L3）；
真实调用类证据（六项 d、c）仅引用迁移会话一次性实测，本卡未重复消耗配额。

V1.1（2026-10-28）：T3 修复（Kanban t_368a7769）。修正 §2.5/§2.6 与 §5 中
`platform_evidence` 来源描述：该字段由 `probe_gwy_p3`（L434-436）以 `gateway_state.json`
条目 `updated_at` 经 `_sanitize_evidence` 合成；journal 命中（`P-GWY-3J`，L707-717）只被
计算、从不进入输出（`_evaluate_gwy` L720-729 只取 `results["P-GWY-3"][3]`）。§4.d 代理
地址脱敏；§4.f audit 时序改为口径明确表述；L7 计数改区间口径；新增 L9 记录本次描述偏差。

V1.2（2026-10-28）：T5 修复（Kanban t_f2ec01e5）。§4.f 中 01:47:18 的来源更正：
该时刻是 systemd oneshot unit 的 `ExecMainExitTimestamp` 字段读数（T5 实测四字段
Start=2026-10-28 01:46:38 CST / Exit=2026-10-28 01:47:18 CST / Result=success /
ExecMainStatus=0），不是「journal 中最后一条 audit ready 输出时刻」——四服务
ready 的 ndJSON 行由探针进程 append 到 `logs/boot-readiness-audit.log`，不经
journald（`journalctl --user` 检索 boot-readiness 为 0 命中）。
