# DESIGN-10-010：DSA 冷启动 24 秒 probe 预算与 `starting → failed` 状态机

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-26 |
| 最后更新 | 2026-07-27 |
| 版本号 | V0.3 |
| 所属模块 | 10_infra（基础设施 / 服务治理） |
| 来源 RFC | RFC-10-010-service-readiness-and-cold-start-governance（V0.3） |
| 来源 SPEC | SPEC-10-010-service-readiness-and-cold-start-governance（V0.3） |
| 适配 Agent | YQuant-Developer-Engineer、YQuant-Test-Engineer、YQuant-Reviewer-Principal |
| 标签 | #infra #readiness #dsa #cold-start #systemd #wsl #design |

## 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-26 | 初始四服务 readiness 设计 | YQuant-Principal |
| V0.2 | 2026-07-27 | DSA endpoint/port 校正到 `127.0.0.1:8888` | YQuant-Principal |
| V0.3 | 2026-07-27 | 收敛为 DSA-only：固定 `14s + 10s = 24s` 预算、MainPID/port/cgroup ready 证据；并澄清 cap 仅约束 deadline 前可完整执行的轮数，`failed` 唯一由 `now >= deadline AND consecutive_failures >= 3` 裁决，deadline 时不启动新 probe；撤销未授权的 TA-CN/Gateway/unit/schema 扩展 | YQuant-Principal |

---

## 1. 结论与范围

### 1.1 结论

本次只修复 DSA 在真实冷启动约 14 秒时被约 10 秒/3 次 probe 提前判为 `failed` 的 false-failed 问题。

实现采用 DSA 专用、有限且可计算的窗口：

```text
DSA cold-start budget = measured API-ready 14s + safety margin 10s = 24s
```

在同一 DSA 启动轮次的 `[0s, 24s)` 内，HTTP、PID、端口或 cgroup 检查失败都只能输出 `starting`；只在窗口到期、仍不满足完整 ready 条件且连续失败阈值已满足时输出 `failed`。任何时刻完整证据满足即输出 `ready`。

本设计落实 RFC §5.3.1/§9.1、SPEC R-004b/R-006、SPEC §3.2.1/§5.4.1/§6.3 的 DSA-only 契约；不改变 TA-CN、Gateway 或全局默认语义。

### 1.2 本卡后续 Implement allowlist（精确且封闭）

| 路径 | 是否允许修改 | 目的 |
|---|---:|---|
| `scripts/service_readiness/readiness_probe.py` | 是 | 新增 DSA 专用预算参数、P-DSA-4 一致性检查及 budget-gated 状态机 |
| `scripts/service_readiness/tests/test_readiness_probe.py` | 是 | 增加/修正 DSA 离线单元、边界、静态 unit 合约测试 |
| `/home/pascal/.config/systemd/user/daily-stock-analysis.service` | 是（仅受控 apply 阶段） | 为现有 DSA `ExecStartPost=-` 接入 DSA 专用参数 |

以下文件和范围均禁止修改、创建、删除、暂存、提交或纳入本任务：

- RFC、SPEC、本 Design 以外的任何 `docs/` 文件；
- `scripts/service_readiness/cold_start_report_schema.json`、`logs/cold-start-report.json`；
- `scripts/service_readiness/` 下除上述脚本与测试外的任何文件；
- 所有 TA-CN/Gateway unit、`start_all.sh`、DSA 应用代码、API endpoint/端口定义；
- `skills/`、`tests/scripts/t4_preflight/`、`scripts/t4_preflight/`、`docs/operations/restart-tradingagents-cn.md`；
- Hermes core/profile/config、cron、数据库 schema、外部消息、交易与任何生产数据路径。

`daily-stock-analysis.service` 当前已经有 `ExecStartPost=-...readiness_probe.py --service DSA --report ...`。因此需要的是**仅替换该行的 DSA 参数**，不是新增第二条 `ExecStartPost`，也不是改动 `ExecStart`、`Type`、`WorkingDirectory`、`Restart`、`RestartSec`、Kill/timeout 参数。

### 1.3 非目标

- 不处理 TA-CN `--no-smoke`、Gateway journal 或四服务 aggregate report。
- 不新增 schema、wrapper、timer、sidecar、auto-restart、kill 或无限重试。
- 不改变 `/health`、`/api/health`、8888 端口、HTTP method 或 canonical aggregate report 的“单服务不写入”语义。
- 不在本卡执行 `daemon-reload`、stop/start/restart 或真实冷启动；真实 S-002a 仅由 Pascal 已授权的受控 apply/verify 阶段执行。

---

## 2. 已核实的输入事实与设计决策

### 2.1 运行时事实

1. DSA 由 `daily-stock-analysis.service` 管理，MainPID 的真实 listener 为 `127.0.0.1:8888`。
2. 同一恢复路径中，journal 的启动至 Uvicorn/API ready 观测约为 14 秒（22:27:02 → 22:27:16）。
3. 现有 probe 的全局默认值是 timeout=10s、interval=5s、max-retries=3、total wait=120s；现有循环在每轮 `starting` 后立即应用连续失败阈值，故可在 API ready 前错误地产生 `failed`。
4. 当前 DSA ready evaluator 只要求 `(P-DSA-1 OR P-DSA-2) AND MainPID alive`，缺少 SPEC 强制的 listener PID/cgroup 归属验证。

### 2.2 固定参数选择

| 参数 | 作用域 | 值 | 决策理由 |
|---|---|---:|---|
| `--dsa-budget-seconds` | DSA-only | `24` | 严格冻结为 `14 + 10`；不得被全局 `total_wait` 缩短 |
| `--timeout` | DSA `ExecStartPost` 调用 | `2` 秒 | 小于 RFC 的 10 秒上限；配合固定 schedule 保证 deadline 前完成最后一次网络检查 |
| `--interval` | DSA `ExecStartPost` 调用 | `2` 秒 | 固定、非指数退避；API-ready 14 秒后仍有可完成的 probe |
| `--max-retries` | DSA `ExecStartPost` 调用 | `3` | 保留既有连续失败阈值含义，但只能在预算耗尽后裁决 |

必须新增 CLI 参数 `--dsa-budget-seconds`，默认值也必须为 `24.0`。该参数仅影响 `--service DSA` 的状态机；TA-CN/Gateway 继续使用既有 `DEFAULT_TOTAL_WAIT`、`DEFAULT_INTERVAL`、`DEFAULT_MAX_RETRIES` 语义。CLI validation：值必须严格大于 0，且只接受 `24.0`（任何其他值以 exit 3 拒绝），防止部署参数将 RFC 冻结预算缩短或无限扩大。

### 2.3 24 秒 schedule 与 off-by-one 规则

令 `t0 = time.monotonic()`，它必须在 probe 进程开始服务 DSA 后只取一次。预算截止点为 `deadline = t0 + 24.0`；使用 monotonic 时间，不使用旧 journal、其他 unit 或前次 probe 时间戳。

每次 DSA probe 的网络上界为 2 秒，轮次起点按固定 cadence 计划为 `0, 4, 8, 12, 16, 20` 秒；即 `timeout + interval = 2 + 2 = 4`。第六次最多在 `t0+22` 结束，随后只 sleep 至 `deadline`，不在 `t >= deadline` 发起第七次 probe。因此：

```text
max completed probes before deadline = floor((24 - 2) / (2 + 2)) + 1 = 6
last probe completes no later than t0 + 22s
final deadline observation = t0 + 24s
```

这保证 API 在约 14 秒 ready 后，至少有 `t=16s` 与 `t=20s` 两次完整 probe 机会；也保证该单服务 `ExecStartPost` 不因 timeout + sleep 溢出 24 秒。

边界规则（必须逐条实现）：

1. probe 仅当轮次开始时 `now < deadline` 才可执行；`now == deadline` 不允许新 probe。
2. 当前轮次只要完整 ready 条件 PASS，立即 `ready`；即使该轮结束时间恰为 deadline 也优先 `ready`。
3. 当前轮次失败且 `now < deadline`，输出 `starting`，携带最后 error、`elapsed_seconds`、累计 `probe_count`；连续失败数增加但**不得**裁决 `failed`。
4. 当 `now >= deadline` 时，必须先做 deadline 裁决，且不得调用 `_probe_round_dsa()` 或发起任何新的网络/systemd probe。若尚未 ready 且 `consecutive_failures >= 3`，输出一次最终 `failed`，`probe_error` 保留最后失败原因（没有具体原因时才使用 `consecutive_failures`）；若连续失败不足 3 次，则输出最终 `starting` 并结束该单服务观察，绝不得伪造 `failed`。
5. `cap=6` 仅表示本固定 cadence 下 **deadline 前最多可排程并完整执行** 的 probe 轮数；它不是 status transition、terminal condition 或 `failed` 的独立触发器。即使已完成第 6 轮，只要 `now < deadline`，状态仍必须是 `starting` 并仅等待 deadline observation；仅规则 4 的 `now >= deadline AND consecutive_failures >= 3` 可裁决 `failed`。
6. 不调用/不依赖全局 `total_wait` 作为 DSA deadline；`--all` 时 DSA 亦遵循此分支。其他 service 现有分支不得改动。

---

## 3. DSA 探针与状态机

### 3.1 DSA ready 证据

单轮收集四项只读证据：

| 编号 | 检查 | PASS | 失败时最后错误示例 |
|---|---|---|---|
| P-DSA-1 | `GET http://127.0.0.1:8888/health` | HTTP 200 | `timeout`、`curl_exit_7`、`http_status_503` |
| P-DSA-2 | 仅 P-DSA-1 FAIL 时 `GET http://127.0.0.1:8888/api/health` | HTTP 200 | 同上 |
| P-DSA-3 | `systemctl --user show ... MainPID` 后 `ps -p <MainPID>` | MainPID 非 0 且存活 | `no_main_pid`、`pid_dead` |
| P-DSA-4 | `MainPID == :8888 listener PID`，且两者均属于 DSA unit cgroup | 三项归属一致 | `listener_not_found`、`listener_pid_mismatch`、`cgroup_mismatch` |

完整 ready 条件固定为：

```text
(P-DSA-1 PASS OR P-DSA-2 PASS)
AND P-DSA-3 PASS
AND P-DSA-4 PASS
```

P-DSA-4 设计：

1. 读取 `MainPID`（重用现有 bounded `systemctl --user show ... --value`）；`0` 或非数字立即失败。
2. 执行只读 `ss -ltnp`，精确匹配 `127.0.0.1:8888` listener；解析其 `pid=<n>`。零 listener → `listener_not_found`；多个不同 PID 或无法唯一解析 → `listener_pid_ambiguous`。
3. listener PID 必须等于 MainPID，否则 `listener_pid_mismatch`。
4. 读取 `/proc/<MainPID>/cgroup` 和 `/proc/<listener_pid>/cgroup`；二者必须相同，且包含 `daily-stock-analysis.service`。否则 `cgroup_mismatch`。
5. `ss`、`systemctl`、`ps` 或 `/proc` 不可用/超时时返回具体 `*_not_found`/`*_timeout`/`cgroup_unreadable`，仍只作为预算内 `starting` 观察。

不得通过“仅端口 bound”或“仅 health=200”返回 ready；不得让另一个进程占用 8888 或代理响应成为 ready 证据。

### 3.2 状态转换

```text
initial
  └─ first DSA probe ── complete ready evidence ──> ready (terminal)
                      └─ any incomplete/failed evidence, elapsed < 24 ──> starting

starting, elapsed < 24
  └─ complete ready evidence ──> ready (terminal)
  └─ otherwise ──> starting (record last error; fixed wait)

starting, elapsed >= 24
  └─ no new probe; first adjudicate deadline observation
      ├─ consecutive_failures >= 3 ──> failed (terminal)
      └─ consecutive_failures < 3 ──> starting (final observation; end service observation)
```

仅有在 `now < deadline` 启动的最后允许轮次可在其完成时直接产生 `ready`，即使该完成时刻恰为 deadline；`now >= deadline` 的 deadline observation 本身不执行新一轮 ready 检查。DSA 不在本次范围定义 `degraded`。预算内出现任何 `curl` error、HTTP 非 200、PID error、listener/cgroup mismatch 或连续失败阈值，均不可成为 `failed` 的提前出口。

每条状态 JSON 沿用既有 schema 字段：`service=DSA`、`status`、`probe`、`probe_http_status`、`probe_error`、`probe_count`、`elapsed_seconds`、`platform_connected=null`、`platform_evidence=null`、`side_effect_free=true`。预算中最后错误不可丢失；最终 failed 应保留它。

### 3.3 实现定位

`probe_service()` 应添加一个仅 DSA 的 helper（推荐名 `_probe_dsa_with_budget(args)`），使 TA-CN/Gateway 的现有 while loop 保持字节级行为等价。该 helper 接收 DSA 参数并：

- 使用 `_probe_round_dsa()`，扩展该 round 加入 P-DSA-4；
- 由 `_evaluate_dsa()` 只在 P-DSA-1/2、P-DSA-3、P-DSA-4 均满足时返回 `ready`；
- 对预算内失败先 emit `starting`；
- 使用 `sleep_seconds = min(interval, max(0, deadline - now))`，绝不睡过 deadline；
- `now >= deadline` 时在调用任何 probe 前裁决：仅 `consecutive_failures >= 3` emit 一次 `failed`；否则 emit 最终 `starting` 并结束该单服务观察；两种分支均不得再次 probe；
- 对 `--service DSA` 和 `--all` 下的 DSA 都调用该 helper。

`--report` 的既有规则不变：`--service --report` 仅 stderr 提示并不写 canonical aggregate report；只有 `--all --report` 可写四服务 report。DSA 单服务 `ExecStartPost` 因而不会产生 aggregate report 写入。

---

## 4. systemd 精确接线（受控 apply 后）

仅将现有 DSA 行改为以下单行；保留开头的 `-`：

```ini
ExecStartPost=-/home/pascal/workspace/yquant-investment/scripts/service_readiness/readiness_probe.py --service DSA --dsa-budget-seconds 24 --timeout 2 --interval 2 --max-retries 3 --report /home/pascal/workspace/yquant-investment/logs/cold-start-report.json
```

含义：

- `-` 保证 readiness 失败是观察结果，不令 Type=simple service 因 ExecStartPost exit code 进入重启循环；
- 该行不改变 DSA 进程启动、停止、重启、端口或环境；
- 该行不接入 TA-CN/Gateway、不新增 `ExecStartPost`、不启用 report 写入；
- Apply 前必须备份该 unit；变更、`daemon-reload`、restart 及真实 S-002a 由 Pascal 明确授权后另行执行。

静态 unit 验证必须确认：恰有一个 DSA `ExecStartPost=-`，参数精确包含 `--service DSA --dsa-budget-seconds 24 --timeout 2 --interval 2 --max-retries 3`，并且保留原有 `ExecStart`、`Type`、`WorkingDirectory`、`Restart`、`RestartSec` 文本。

---

## 5. 测试矩阵与验收

### 5.1 离线单元/边界测试（只修改 colocated 测试文件）

| ID | 场景 | 期望 |
|---|---|---|
| DSA-UT-01 | health=200、PID/listener/cgroup 一致 | 首轮 `ready` |
| DSA-UT-02 | health=200 但 listener PID ≠ MainPID | `[0,24)` 为 `starting`，最终 `failed`；不得 ready |
| DSA-UT-03 | health=200、PID 相同但 cgroup 不属于 unit | 同 DSA-UT-02 |
| DSA-UT-04 | cap=6 已耗尽但 fake monotonic <24 | 状态严格为 `starting`、`probe_count=6`；不得 `failed`，并仅等待 deadline observation |
| DSA-UT-05 | 失败、fake monotonic 进至 24，连续失败=3 | 一次最终 `failed`，携带最后 error |
| DSA-UT-05a | 测试注入使 fake monotonic 进至 24 但连续失败<3 | 最终仍为 `starting`，结束该单服务观察；不得伪造 `failed` 或启动新 probe |
| DSA-UT-06 | 约 t=14 前失败、t=16 probe 全证据 PASS | `ready`，probe_count 落在 5 或更少的合理范围；无 prior failed |
| DSA-UT-07 | deadline 边界：t=24 不启动新 probe | 在任何 `_probe_round_dsa()` 前先做 deadline 裁决；`ss/curl/systemctl` 调用数不超过 6 个计划 round，且 t=24 无新调用 |
| DSA-UT-08 | `--dsa-budget-seconds` 缺省 | 等价 24；不读取全局 total_wait |
| DSA-UT-09 | `--dsa-budget-seconds` 为 23、25、0 或非数 | CLI exit 3 |
| DSA-UT-10 | TA-CN/Gateway 调用原有参数 | 不获得 DSA budget 分支；既有测试继续通过 |
| DSA-UT-11 | `--service DSA --report <canonical>` | 不调用 `_write_report`，stderr 给 skip 提示 |
| DSA-UT-12 | source/static audit | 不含 POST/PUT/DELETE、DB/message/trade/git 写操作；DSA URL 只为 8888 |

### 5.2 静态 unit 验证

测试仅断言 `daily-stock-analysis.service`，不得再要求 TA-CN/Gateway unit 存在或修改。检查精确接线和保留的容错前缀 `ExecStartPost=-`；不执行 `systemctl daemon-reload`。

### 5.3 真实 S-002a（后续受控阶段，非本卡执行）

在 Pascal 明确授权的维护窗口：

1. 保存 unit 当前版本并应用 §4 的唯一行改动；执行 `systemctl --user daemon-reload`。
2. 记录同一轮次 DSA 的启动开始、systemd Started、API ready、MainPID、`:8888` listener PID、两者 cgroup。
3. 执行真实 DSA 冷启动一次；不得重启任意其他服务。
4. 验收：在约 14 秒 API-ready 前输出仅为 `starting`；在 24 秒内 health=200 且 PID/port/cgroup 一致后为 `ready`；不存在 early `failed`。
5. 同时审计 journal/stdout：无 POST、无数据写入、无消息、无交易、无 aggregate report 写入。
6. 若真实 API ready 超过 24 秒、P-DSA-4 不一致或 health 非 200，立即停止后续重启；不循环重试，记录证据并退回 RFC/SPEC 重新裁决。

---

## 6. 回滚、停止规则与风险

### 6.1 停止规则

以下任一事件立即停止 apply 后的后续 restart/验证，不自动重试：真实冷启动超出 24 秒、`:8888` listener PID 与 MainPID 不同、cgroup 不一致、`/health` 和 `/api/health` 均非 200，或发现任何副作用。

### 6.2 回滚

仅恢复 `/home/pascal/.config/systemd/user/daily-stock-analysis.service` 中原始单条 `ExecStartPost`，不修改脚本以外任何生产文件；随后由 Pascal 在独立受控步骤决定是否 `daemon-reload`/restart。绝不以 restart loop、kill、port cleanup、POST 或数据库操作“修复”失败。

### 6.3 残余风险

- 24 秒来自一次约 14 秒的已核实冷启动样本；S-002a 必须重新取证，若正常路径超过预算，只能修订 RFC/SPEC，不能静默扩大参数。
- `ss -ltnp` 的 PID 可见性与 `/proc/<pid>/cgroup` 读取依赖当前 user-systemd 权限；不可读时应保守失败，而不是降级 ready 证据。
- `ExecStartPost=-` 不会阻止 systemd 将服务标为 active；它只提供无副作用观测，不替代应用的健康事实。

---

## 7. Design 验收清单

- [ ] 文档引用 RFC V0.3 与 SPEC V0.3，并且 24 秒公式精确为 `14 + 10`。
- [ ] 后续 allowlist 仅含 `readiness_probe.py`、其 colocated 测试和 DSA user unit。
- [ ] 参数、schedule、deadline 边界、失败阈值和 expected max probe count 均可计算。
- [ ] ready 明确要求 health=200 + MainPID + listener PID + cgroup 一致。
- [ ] `cap=6` 仅约束 deadline 前可完整执行的轮数；预算内（含 cap 已耗尽但未到 deadline）所有错误都为 `starting`，仅 `now >= deadline AND consecutive_failures >= 3` 可 `failed`。
- [ ] `now >= deadline` 在任何新 probe 前裁决；连续失败不足阈值时最终输出 `starting` 并结束该单服务观察。
- [ ] `ExecStartPost=-` 的精确 DSA-only 参数线与单服务不写 aggregate report 语义被保留。
- [ ] 单元、边界、static unit、受控 S-002a、停止与回滚规则完整。
- [ ] 未授权的 TA-CN/Gateway/unit/schema/endpoint/port/自动重启/副作用均未被纳入。
