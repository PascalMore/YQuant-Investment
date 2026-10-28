# SPEC-10-015：Hermes 网关多路复用迁移验收契约

| 项 | 值 |
|---|---|
| 状态 | 已冻结 |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-10-28 |
| 最后更新 | 2026-10-28 |
| 版本号 | V1.1 |
| 来源RFC | RFC-10-015-gateway-multiplex-migration-acceptance |
| 目标模块 | 10_infra（基础设施 / 服务治理） |
| 适配Agent | YQuant-Test-Engineer（独立验证）；实现侧零代码，无 Developer 适配 |

关联文档：
- [RFC V1.1](../../rfc/10_infra/RFC-10-015-gateway-multiplex-migration-acceptance.md)
- [DESIGN V1.1](../../design/10_infra/DESIGN-10-015-gateway-multiplex-migration-acceptance.md)

---

## 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-10-28 | 初始创建：双层就绪判定（F-GWY-1~7）、journal 辅证降级（F-JRN-1）、冷启动 audit unit 引用（F-AUD-1~2）、六项验收标准（F-ACC-a~f）、回归基线记录要求（F-REG-1）、强制约束（F-CON-1~4）；显式声明对 SPEC-10-010 §4.3 / §3.2.3 / §3.2.4 的取代关系 | YQuant-Principal |
| V1.1 | 2026-10-28 | T3 修复：F-JRN-1 外发契约修正——journal 命中 `P-GWY-3J` 只被计算、不写入任何输出字段；`platform_evidence` 唯一来源为 `gateway_state.json` 条目 `updated_at` 经有界脱敏 | YQuant-Principal |

---

## 1. 与 SPEC-10-010 的关系（取代声明）

本 SPEC 显式声明：**SPEC-10-010 §4.3（`platform_connected` 证据匹配规则）、
§3.2.3（Gateway yquant 探针契约）、§3.2.4（Gateway yinglong 探针契约）自本 SPEC
冻结起被本 SPEC §3 的 F-GWY / F-JRN 规格取代**。原因：010 引用的
`hermes-gateway-yquant.service` / `hermes-gateway-yinglong.service` 两个 unit 已于
2026-10-27 从磁盘删除，其前置条件已不可执行。

010 正文本卡不重写；是否在 010 追加一行指针对照另行裁决（RFC 遗留 L2）。
010 的其余章节（DSA / TA-CN 探针、状态 schema、DSA 24 秒预算、allowlist）不受本卡影响。

---

## 2. 功能规格

### 2.1 双层就绪判定（gateway service）

适用对象：`gw-yquant`、`gw-yinglong` 两个 service 条目，均指向同一 unit
`hermes-gateway.service`。profile 键映射固定：gw-yquant→`yquant`、gw-yinglong→`yinglong`。

| 编号 | 行为 | 输入 | 输出 | 错误边界 |
|---|---|---|---|---|
| F-GWY-1 | unit 层判定：目标 unit 必须处于 active | `systemctl --user is-active --quiet hermes-gateway.service` | exit 0 → unit 层 PASS；计入状态机 P-GWY-1 | 非 active（inactive/failed/activating）→ unit 层 FAIL，服务进入 `starting` |
| F-GWY-2 | unit 层判定：MainPID 必须存在且存活 | `systemctl --user show -p MainPID hermes-gateway.service --value` + `ps -p <pid>` | PID 非 0 且 `ps` exit 0 → PASS；计入状态机 P-GWY-2 | PID=0 / 空 / 非数字 → `no_main_pid`；`ps` 非零 → `pid_dead` |
| F-GWY-3 | profile 层判定：`~/.hermes/gateway_state.json` 的 `platforms["<profile>:feishu"].state == "connected"` | 读 gateway_state.json | 条件成立 → profile 层 PASS；计入状态机 P-GWY-3 | 文件缺失/不可读/JSON 非法 → `gateway_state_missing` / `gateway_state_unreadable` / `gateway_state_invalid_json`，profile 层 FAIL（判无证据，不抛异常） |
| F-GWY-4 | 陈旧防护：`platforms["<profile>:feishu"].writer_pid` 必须等于当前 `hermes-gateway.service` 的 MainPID | 同上状态文件条目 + F-GWY-2 的 MainPID | `writer_pid == MainPID` → 证据新鲜 | `writer_pid` 缺失 / 非正整数 / 不等于 MainPID → `platform_writer_pid_missing` / `platform_writer_pid_invalid` / `platform_state_stale`；陈旧记录一律判**无证据**（unknown），绝不判 connected |
| F-GWY-5 | 就绪裁决：`status=ready` ⇔ unit 层 PASS（F-GWY-1 且 F-GWY-2）且 profile 层 PASS（F-GWY-3 且 F-GWY-4） | 各层结果 | `{status: "ready", platform_connected: "confirmed_at_boot"}` | 任一层 FAIL 但 unit 层 PASS → `degraded` / `unknown`；unit 层 FAIL → `starting`（超时后 failed） |
| F-GWY-6 | 陈旧防护优先序：先验 `writer_pid`，后验 `state` 字段 | 同 F-GWY-3/4 | 陈旧时直接判无证据，不读 `state` 值 | 若先读 `state` 后验 PID，会把陈旧 `connected` 误判在线；实现必须保持先 PID 后 state 的顺序（readiness_probe.py `probe_gwy_p3` 实际顺序） |
| F-GWY-7 | 状态文件读取是唯一 per-profile 事实源；不新增其他归因机制 | — | — | 禁止用 journal、进程参数扫描或其他启发式替代 profile 层判定 |

### 2.2 journal 辅证（降级）

| 编号 | 行为 | 输入 | 输出 | 错误边界 |
|---|---|---|---|---|
| F-JRN-1 | unit journal 的 `connected` 匹配仅作辅证：命中行经脱敏（时间戳 + 有界类别）构成 `P-GWY-3J`，**只被计算、不写入任何输出字段**；journal 命中既不是 per-profile 判决的依据，也不是 `platform_evidence` 的来源——`platform_evidence` 是 `gateway_state.json` 条目 `platforms["<profile>:feishu"].updated_at` 经有界脱敏的字符串（含 profile 名，128 字上限）；journal 不参与 per-profile 判决，不得使 ready/degraded 翻转 | `journalctl --since=@<unit_active_ts> _SYSTEMD_USER_UNIT=hermes-gateway.service` | 无对外输出字段（`P-GWY-3J` 仅内部计算）；`platform_evidence` 由 F-GWY-3 路径产出，journal 缺失不影响 F-GWY-5 裁决 | journal 不可读/超时 → 仅影响内部辅证计算（无输出字段受影响）；单 unit journal 无法区分 profile，任何试图以 journal 判定单 profile 就绪的实现均违反本契约 |

### 2.3 冷启动 audit unit 引用

| 编号 | 行为 | 输入 | 输出 | 错误边界 |
|---|---|---|---|---|
| F-AUD-1 | `~/.config/systemd/user/yquant-boot-readiness-audit.service` 的 `Wants=` 与 `After=` 两行必须包含 `hermes-gateway.service`，且**不得**含任何 `hermes-gateway-<profile>.service` 引用 | 读 unit 文件 | 两行均形如 `… daily-stock-analysis.service tradingagents-cn.service hermes-gateway.service` | 出现已删除 unit 引用 → 判 FAIL（引用孤儿 unit 会导致 audit 依赖永不满足） |
| F-AUD-2 | systemd 运行时视图与文件一致 | `systemctl --user show yquant-boot-readiness-audit.service -p Wants -p After` | 读回值与文件两行一致 | 不一致 → 判 FAIL（未 `daemon-reload` 或文件被回退）；本契约只读验证，不授权执行 `daemon-reload` |

### 2.4 六项验收标准

判定所需实测证据（命令 + 实际读数）由 Design §4 承载；本节定义可测标准。
T1 自测与 T2 独立验证必须分开标注来源（见 F-CON-3）。

| 编号 | 验收项 | 通过标准 |
|---|---|---|
| F-ACC-a | default unit + 8 profiles | `systemctl --user show hermes-gateway.service` → `ActiveState=active` 且 `MainPID != 0`；`gateway_state.json` `served_profiles` 恰含 `default, yinglong, yinglongdesigner, yquant, yquantdeveloper, yquantprincipal, yquantreviewer, yquanttester` 共 8 个 |
| F-ACC-b | 双 bot 在线、不串号 | `platforms["yquant:feishu"]` 与 `platforms["yinglong:feishu"]` 均 `state=connected` 且 `writer_pid` = 当前 MainPID；两 profile 各自凭据调用 `bot/v3/info` 返回的 app_id 互不相同（凭据与 app_id 值不得写入任何文档） |
| F-ACC-c | 知识卡片真实点击 E2E | 真实点击「详情」「下一条」后：handler 经 `subprocess.run([sys.executable, handler])` 真实执行；产生导航 JSON（含 `issued_at`/`expires_at`/`entry_ref`/`binding_integrity`）；`review_v2/receipts.jsonl` 新增 txn 且 `action=defer`/`state=deferred`；origin-card-update 映射同步更新；无 `knowledge card handler failed` 告警、无红卡降级 |
| F-ACC-d | 代理 + 真实模型调用 | 网关进程 environ 含 6 个 proxy 变量；api.openai.com 经代理返回 401（到达鉴权层）、example.com 经代理 200、api.minimaxi.com 经 NO_PROXY 直连；yinglong 与 yquant 两侧 `hermes -p <profile> -m gpt-6.1-sol -z …` 真实调用各一次成功（exit 0） |
| F-ACC-e | cron 数量 | `~/.hermes/profiles/yquant/cron/jobs.json` → total=6, enabled=6；`~/.hermes/profiles/yinglong/cron/jobs.json` → total=2, enabled=2 |
| F-ACC-f | WSL 真冷启动 | 重启前后 `/proc/sys/kernel/random/boot_id` 变化（真冷启动，非保活挂住的假重启）；冷启动时序：boot → 双 bot WS connected ≤ 90 秒（实测 85 秒，无 3 分钟盲区）；boot-readiness audit `Result=success` exit 0；journal 唯一 "lock" 命中为 Kafka 客户端无害重试，无 Kanban/systemd 抢锁 |

### 2.5 回归基线记录要求

| 编号 | 行为 | 要求 |
|---|---|---|
| F-REG-1 | 每次涉及 gateway 拓扑或 readiness 探针的变更后，必须记录可复现回归基线 | 至少含：冷启动时序（关键节点时间戳）、unit 状态（ActiveState/MainPID）、`gateway_state.json` 结构（served_profiles + 双 platform 条目）、代理路由（proxy 变量数、直连/代理分流各一例）、模型 fallback 链、探针 `--all` 输出。基线格式参照本卡 Design §5 |

### 2.6 探针实测命令（只读，零副作用）

```
python3 scripts/service_readiness/readiness_probe.py --all --timeout 5 --interval 5 --max-retries 2
```

预期：四服务（DSA / TA-CN / gw-yquant / gw-yinglong）status=ready，exit 0。
不带 `--report` 执行，保证零文件写入。

---

## 3. 强制约束

| 编号 | 约束 |
|---|---|
| F-CON-1 | 零副作用：验收与回归动作只允许读命令（`systemctl --user show`、`journalctl`、读 JSON 文件、探针不带 `--report`）；禁止服务重启/停止、systemd 写操作、生产数据库写入、真实模型调用（配额消耗类证据只允许引用既有一次性实测） |
| F-CON-2 | 只读优先：能读文件/`show` 的不得用写操作验证；`daemon-reload`、`restart` 等不在本契约授权内 |
| F-CON-3 | 区分 T1 自测与 T2 独立验证：引用测试输出必须标注来源；pytest 全集命令固定为 `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy .venv/bin/python -m pytest scripts/service_readiness/tests/ -q`（默认解释器无 pytest 会 exit 1；带代理变量会污染代理作用域测试）。T1 首次 run 3316 iteration budget 超时的记录不得追认为成功 |
| F-CON-4 | 凭据红线：bot token、app_id 明文、代理凭据一律不得写入文档；app_id 只允许以「两个互不相同」的脱敏形式描述。数字必须来自实测，不得编造 |

---

## 4. 依赖与引用

- 来源：RFC-10-015（V1.1）
- 关联 Design：DESIGN-10-015（V1.1，承载全部实测证据）
- 被取代：SPEC-10-010 §4.3、§3.2.3、§3.2.4（见 §1）
- 引用实现：`scripts/service_readiness/readiness_probe.py`（commit `15238e4`）、
  `scripts/service_readiness/tests/test_readiness_probe.py`
- 引用本机配置（只读）：`~/.config/systemd/user/yquant-boot-readiness-audit.service`、
  `~/.hermes/gateway_state.json`、`~/.hermes/profiles/{yquant,yinglong}/cron/jobs.json`

---

## 版本记录

V1.0（2026-10-28）：初始创建（事后归档）。取代声明仅覆盖 010 的 gateway 探针相关章节；
全部数字来自实测，凭据零写入。

V1.1（2026-10-28）：T3 修复（Kanban t_368a7769）。F-JRN-1 修正外发契约：journal 命中
（`P-GWY-3J`）只被内部计算、不写入任何输出字段；`platform_evidence` 的唯一来源是
`gateway_state.json` 条目 `platforms["<profile>:feishu"].updated_at` 经有界脱敏的字符串
（含 profile 名，128 字上限）。判定语义不变（F-GWY-5 不受影响）。
