# SPEC-10-010：冷启动 Readiness 与无副作用依赖等待治理

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-26 |
| 最后更新 | 2026-07-27 |
| 来源 RFC | RFC-10-010-service-readiness-and-cold-start-governance |
| 目标模块 | 10_infra（基础设施 / 服务治理） |
| 适配 Agent | YQuant-Developer-Engineer, YQuant-Test-Engineer |

---

## 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-26 | 初始创建：定义四项服务只读 probe 契约、A+B allowlist、状态输出 JSON schema、platform_connected 匹配规则、冷启动验收记录 schema、测试矩阵与零副作用规则 | YQuant-Principal |
| V0.2 | 2026-07-27 | T2.1 修订：将 DSA probe 端口从 8000 校正为 8888（§3.2.1），与 live systemd/ss/curl 证据对齐。确凿证据：DSA PID 272 监听 127.0.0.1:8888，8000 为 TA-CN PID 366 | YQuant-Principal |
| V0.3 | 2026-07-27 | T1 冷启动窗口修订：为 DSA 固化 `14s + 10s = 24s` 有限预算、预算内 `starting` 与预算耗尽后的连续失败裁决；限定后续 Design 的服务特定参数 allowlist | YQuant-Principal |

## 1. 需求摘要

本 SPEC 将 RFC-10-010 的冷启动 readiness 治理模型落为可验证的工程契约。核心交付：

1. 四项受治理服务的精确只读 probe 定义（探针 URL、条件、降级阈值）。
2. A+B 分组的文件级 allowlist 及每项候选文件的精确改动授权。
3. 状态输出的精确字段模式与强制约束。
4. `platform_connected` 的 journal 证据匹配规则。
5. TA-CN 冷启动无副作用入口切换契约。
6. 冷启动验收记录的 JSON 模式定义与验证规则。
7. 强制不动文件清单（禁止列表中所有文件）。
8. 测试矩阵：smoke × 4 + 单次冷启动验收记录验证。

**本 SPEC 不进入 Design 级文件清单或实现细节。** 具体实现方案（probe 脚本设计、systemd unit 补丁内容、验收记录生成器实现）由后续 Design 阶段产出。

---

## 2. 范围

### 2.1 In Scope

- [ ] 定义四项服务的只读 probe 契约（URL、method、成功条件、降级条件、超时）。
- [ ] 定义 A+B 文件级 allowlist 及每项候选文件的精确改动授权（只读引用 vs 可增量修改 vs 可新增）。
- [ ] 定义 readiness 状态输出 JSON schema 字段级约束。
- [ ] 定义 `platform_connected` 的 journal 证据匹配规则（unit 过滤 + 字符串匹配 + 时间戳语义）。
- [ ] 定义 TA-CN 冷启动无副作用入口切换契约（强制 `--no-smoke`，禁止做默认 smoke）。
- [ ] 定义冷启动验收记录的 JSON schema。
- [ ] 定义强制不动文件清单（从 RFC §6 禁止候选具象化）。
- [ ] 定义测试矩阵：smoke test × 4（每项服务一次探针验证）+ 单次冷启动验收记录验证。

### 2.2 Out of Scope

- [ ] 不在本次实现 probe 脚本或 systemd unit 修改（T2 Design 产出）。
- [ ] 不在本次实现验收记录生成器。
- [ ] 不在本次修改 TA-CN `start_all.sh`（仅定义入口切换契约，T2 决定实现方式）。
- [ ] 不在本次引入第三方依赖（probe 使用 stdlib + `curl`/`systemctl`/`journalctl` 等已有工具）。
- [ ] 不在本次修改任何现有代码或运行配置。
- [ ] 不在本次新增 systemd timer、cron 或其他调度入口。
- [ ] 不在本次修改 Hermes core、profile config、MongoDB schema、统一数据层、策略、风控、组合、交易执行。

---

## 3. 功能规格

### 3.1 readiness 统一状态模型

| 编号 | 行为 | 输入 | 输出 | 错误/边界 |
|---|---|---|---|---|
| R-001 | 服务进入 `starting` 状态 | systemd unit 标记 active（`systemctl --user is-active <unit> = "active"`） | `{status: "starting", ...}` | 若 `is-active` 返回非 active（inactive/failed/activating），不应进入状态机；DSA 另受 R-004b 的预算窗口约束 |
| R-002 | 首次 probe 全部 PASS | 每项服务的 probe 集合执行 | `{status: "ready", ...}` | 后续 probe 降级时转为 `degraded`（见 R-005） |
| R-003 | 单次 probe 超时 (> 10s) | probe 请求 | `{status: "starting", probe_error: "timeout"}` | 不改变当前 status；继续下次轮询 |
| R-004 | 总等待时间超时（非 Gateway） | 从 unit active 起计 N 秒（Design 定义 N，建议 ≤ 120s） | `{status: 'failed', probe_error: 'total_timeout', elapsed_seconds: N}` | N 必须 ≥ 各项服务 P99 冷启动时间的 1.5 倍 |
| R-004a | 总等待时间超时（Gateway） | 从 unit active 起计 N 秒（Design 定义 N，建议 ≤ 120s）；仅 P-GWY-3（platform_connected）未确认，P-GWY-1/2 正常 | `{status: 'degraded', probe_error: 'total_timeout', elapsed_seconds: N, exit: 0}` | Gateway 进程存活但连接未知时按方案 A 退出 0，降低冷启动风险 |
| R-004b | DSA 冷启动预算 | 从同一 DSA 启动尝试开始计时：`14s` 已测 API-ready 时间 + `10s` 显式安全余量 | `0 ≤ elapsed_seconds < 24` 时 `{status: "starting", probe_error: "<last_error>"}`；首次全 PASS 时 `{status: "ready"}` | 24 秒为固定、有限预算；预算内禁止因 `consecutive_failures` 输出 `failed`；不得无限等待 |
| R-005 | probe 返回降级条件 | 部分 probe PASS，部分 FAIL | `{status: "degraded", probe_error: "<degraded_reason>"}` | 可恢复为 ready（后续 probe 全 PASS）或转为 failed（连续失败） |
| R-006 | 连续 N 次 probe 全部失败 | N 由 Design 定义，建议 N=3 | `{status: "failed", probe_error: "<last_error>"}` | 对 DSA，只有 `elapsed_seconds ≥ 24` 且 `((P-DSA-1 AND P-DSA-2) 均 FAIL OR P-DSA-3 FAIL)` 时，本规则才可裁决 failed；预算内失败只保持 starting |

### 3.2 各服务只读 probe 契约

#### 3.2.1 DSA（`daily-stock-analysis.service`）

| 编号 | 检查项 | 方式 | 成功条件 | 降级条件 (degraded) | 失败条件 (failed) |
|---|---|---|---|---|---|
| P-DSA-1 | HTTP health check | `curl -sf -o /dev/null --max-time 10 http://127.0.0.1:8888/health` | HTTP 200 | — | 非 200 或超时 |
| P-DSA-2 | HTTP API health check (备选) | `curl -sf -o /dev/null --max-time 10 http://127.0.0.1:8888/api/health` | HTTP 200 | — | 非 200 或超时 |
| P-DSA-3 | PID 存活 | `ps -p "$(systemctl --user show -p MainPID daily-stock-analysis.service --value)"` | exit 0 (running) | — | 非零 (not running) |
| P-DSA-4 | MainPID / port / cgroup 一致性 | 只读比对 unit MainPID、`:8888` 监听 PID 与该 unit cgroup 成员 | 三者归属同一 DSA unit；不接受仅端口存在或仅 PID 存活 | — | 监听 PID 不等于 MainPID 或不属于该 unit cgroup |

**readiness 判定条件**：
- ready ← (P-DSA-1 或 P-DSA-2 PASS) AND P-DSA-3 PASS AND P-DSA-4 PASS
- failed ← (P-DSA-1 AND P-DSA-2 均 FAIL) OR P-DSA-3 FAIL OR P-DSA-4 FAIL（均仅在 DSA 预算耗尽后）
- degraded ← 不适用（DSA 无可区分降级条件）

**platform_connected**：不适用（DSA 不连接外部消息平台）。

**DSA 冷启动窗口与状态转换（强制）**：

| 阶段 | 条件 | 必须输出/行为 |
|---|---|---|
| 窗口内 | `0 ≤ elapsed_seconds < 24` 且未满足 ready | `status=starting`；记录最后一次 `probe_error` 与累计 `probe_count`；即使达到连续失败上限也继续固定间隔的只读 probe |
| 窗口内成功 | `elapsed_seconds < 24` 且 `(P-DSA-1 OR P-DSA-2) PASS AND P-DSA-3 PASS`，并确认 MainPID、`127.0.0.1:8888` 监听者与该 unit cgroup 一致 | `status=ready`，停止本次 probe |
| 窗口耗尽后失败 | `elapsed_seconds ≥ 24`、未满足 ready，且达到 DSA 服务特定连续失败上限 | `status=failed, probe_error=<last_error>`，停止本次 probe；不得重启、杀死或等待无限长 |

`24` 秒的计算必须严格为已测 API-ready 边界 `14` 秒加安全余量 `10` 秒。计时必须绑定本次 DSA 启动轮次，不得从旧 journal、其他 unit 或前次 probe 继承；Design 负责选择既有 unit/probe 参数中可观测的实现取值。

#### 3.2.2 TA-CN（`tradingagents-cn.service`）

| 编号 | 检查项 | 方式 | 成功条件 | 降级条件 (degraded) | 失败条件 (failed) |
|---|---|---|---|---|---|
| P-TACN-1 | TCP 端口检查 | `ss -tlnp 2>/dev/null \| grep -q ":8000 "` | exit 0 (port bound) | — | 非零 |
| P-TACN-2 | HTTP readyz | `curl -sf -o /dev/null --max-time 10 http://localhost:8000/api/readyz` | HTTP 200 | — | 非 200 或超时 |
| P-TACN-3 | HTTP health | `curl -sf --max-time 10 http://localhost:8000/api/health` | 返回 JSON 中 `success == true` | `success == false` 但 P-TACN-1 和 P-TACN-4 PASS | 超时或非 200 |
| P-TACN-4 | PID 存活 | `ps -p "$(systemctl --user show -p MainPID tradingagents-cn.service --value)"` | exit 0 (running) | — | 非零 |

**readiness 判定条件**：
- ready ← P-TACN-1 PASS AND P-TACN-2 PASS AND (P-TACN-3 为 success=true OR P-TACN-3 超时但其他两项 PASS) AND P-TACN-4 PASS
- degraded ← P-TACN-1 PASS AND P-TACN-4 PASS BUT P-TACN-3 返回 `success: false` 且 P-TACN-2 FAIL
- failed ← P-TACN-1 FAIL OR P-TACN-4 FAIL（超时后）

**platform_connected**：不适用（TA-CN 是 Web API 服务）。

**冷启动入口约束**：TA-CN 启动时必须使用 `start_all.sh --no-smoke`，禁止在冷启动路径中执行默认的 POST `/api/sync/stock_basics/run`。完整 smoke（含 POST）保留供人工维护使用。Design 阶段可考虑：
- 新增 `start_no_smoke.sh`（内容为 `exec ./start_all.sh --no-smoke`），或
- 修改 systemd unit 的 `ExecStart` 为 `/path/start_all.sh --no-smoke`

#### 3.2.3 Hermes Gateway yquant

| 编号 | 检查项 | 方式 | 成功条件 | 降级条件 (degraded) | 失败条件 (failed) |
|---|---|---|---|---|---|
| P-GWY-1 | systemd unit active | `systemctl --user is-active --quiet hermes-gateway-yquant.service` | exit 0 (active) | — | 非零 |
| P-GWY-2 | PID 存活 | `ps -p "$(systemctl --user show -p MainPID hermes-gateway-yquant.service --value)"` | exit 0 (running) | — | 非零 |
| P-GWY-3 | platform_connected 证据 | 见 §4 `platform_connected` 匹配规则 | journal 中存在 `connected` 匹配行 | `confirmed_at_boot` = 有证据；`unknown` = 无证据但 P-GWY-1 和 P-GWY-2 PASS | — |

**readiness 判定条件**：
- ready ← P-GWY-1 PASS AND P-GWY-2 PASS AND P-GWY-3 为 `confirmed_at_boot`
- degraded ← P-GWY-1 PASS AND P-GWY-2 PASS AND P-GWY-3 为 `unknown`
- failed ← P-GWY-1 FAIL OR P-GWY-2 FAIL（超时后）

#### 3.2.4 Hermes Gateway yinglong

与 §3.2.3 完全一致，仅 service name 替换为 `hermes-gateway-yinglong.service`。

#### 3.2.5 探针执行规则汇总

| 规则 | 值 |
|---|---|
| 单次 probe 超时 | ≤ 10 秒 |
| DSA 轮询间隔 | 由 Design 在服务特定 allowlist 内定义；必须为固定有限值，并使 24 秒窗口内至少可完成一次 API-ready 后 probe |
| DSA 总等待预算 | 固定为 24 秒（`14 + 10`）；不得由全局默认值覆盖或缩短 |
| DSA 连续失败上限（转为 failed） | 由 Design 在服务特定 allowlist 内定义；仅可在 `elapsed_seconds ≥ 24` 后裁决 |
| 其他服务的轮询/总等待/连续失败 | 保持既有服务语义；本次 DSA 修订不授权全局调整 |

---

## 4. 数据与接口契约

### 4.1 readiness 状态输出 JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "title": "ServiceReadinessStatus",
  "type": "object",
  "required": ["service", "status", "probe", "probe_count", "elapsed_seconds", "side_effect_free"],
  "properties": {
    "service": {
      "type": "string",
      "enum": ["DSA", "TA-CN", "gw-yquant", "gw-yinglong"],
      "description": "服务标识"
    },
    "status": {
      "type": "string",
      "enum": ["starting", "ready", "degraded", "failed"],
      "description": "当前 readiness 状态"
    },
    "probe": {
      "type": "string",
      "description": "最后一次 probe 的目标 URL 或检查名称"
    },
    "probe_http_status": {
      "type": ["integer", "null"],
      "description": "HTTP probe 的状态码，非 HTTP probe 时为 null"
    },
    "probe_error": {
      "type": ["string", "null"],
      "description": "最后一次 probe 的错误信息，无错误时为 null"
    },
    "probe_count": {
      "type": "integer",
      "minimum": 1,
      "description": "从 starting 到当前状态的总 probe 次数"
    },
    "elapsed_seconds": {
      "type": "number",
      "minimum": 0,
      "description": "从 unit active 到本次状态的总耗时（秒）"
    },
    "platform_connected": {
      "type": ["string", "null"],
      "enum": ["confirmed_at_boot", "unknown", null],
      "description": "Gateway 连接证据状态（仅 Gateway 适用）"
    },
    "platform_evidence": {
      "type": ["string", "null"],
      "description": "platform_connected 的 journal 证据原文（仅 confirmed_at_boot 时有值）"
    },
    "side_effect_free": {
      "type": "boolean",
      "const": true,
      "description": "标识本探针路径是否为无副作用。必须为 true。"
    }
  }
}
```

### 4.2 冷启动验收记录 JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "title": "ColdStartReport",
  "type": "object",
  "required": ["boot_id", "services", "total_wait_seconds", "side_effect_free"],
  "properties": {
    "boot_id": {
      "type": "string",
      "description": "冷启动标识，可使用 ISO 时间戳或 UUID"
    },
    "services": {
      "type": "array",
      "minItems": 4,
      "maxItems": 4,
      "items": {
        "type": "object",
        "required": ["name", "status", "probe_count", "elapsed", "side_effect_free"],
        "properties": {
          "name": {
            "type": "string",
            "enum": ["DSA", "TA-CN", "gw-yquant", "gw-yinglong"]
          },

          "status": {
            "type": "string",
            "enum": ["ready", "degraded", "failed"]
          },
          "probe_count": {
            "type": "integer",
            "minimum": 1
          },
          "elapsed": {
            "type": "number",
            "minimum": 0,
            "description": "该服务从 unit active 到确认状态的总耗时（秒）"
          },
          "platform_connected": {
            "type": ["string", "null"],
            "enum": ["confirmed_at_boot", "unknown", null]
          },
          "platform_evidence": {
            "type": ["string", "null"]
          },
          "error": {
            "type": ["string", "null"],
            "description": "如果状态为 failed/degraded，记录原因"
          },
          "side_effect_free": {
            "type": "boolean",
            "const": true
          }
        }
      }
    },
    "total_wait_seconds": {
      "type": "number",
      "minimum": 0,
      "description": "从首个 unit active 到最后一项服务就绪的总耗时（秒）"
    },
    "side_effect_free": {
      "type": "boolean",
      "const": true
    }
  }
}
```

> **Canonical report 写入约束**：`--report` 参数仅在 `--all` 模式下写入 canonical 报告路径（`logs/cold-start-report.json`）。`--service --report` 组合禁止写入少于四服务的负载，实现应跳过文件写入并打印警告到 stderr；readiness 主结论（stdout ndJSON + exit code）不受影响。

### 4.3 `platform_connected` 证据匹配规则

**匹配前置条件**：
- `_SYSTEMD_UNIT=hermes-gateway-yquant.service` 或 `_SYSTEMD_UNIT=hermes-gateway-yinglong.service`
- 时间范围：`journalctl --since "@<unit_active_timestamp>"`（仅查本次启动后的日志）

**匹配字符串**（满足任一即认定 connected）：
- `"connected"`（通用连接日志）
- `"session started"`（Telegram 会话启动）
- `"platform.*connected"`（platform 特定连接确认）
- `"WebSocket.*connected"`（WebSocket 连接确认）

**时间戳提取**：从匹配的 journal 行中提取 ISO 时间戳，写入 `platform_evidence`。

**边界处理**：
- 多次匹配：取首次匹配的时间戳。
- 无匹配且超时：标记为 `platform_connected=unknown`。
- journal 完全不可读（权限/轮转）：标记为 `platform_connected=unknown`，`platform_evidence=null`。

### 4.4 zero-side-effect 验证规则

每条 probe 执行前和执行后，必须验证以下断言：

| 断言 | 验证方式 |
|---|---|
| 未执行 POST/PUT/DELETE HTTP 请求 | 审计 probe 脚本中无相关调用 |
| 未修改 MongoDB 集合 | probe 前后 MongoDB 文档计数无增加（可选验证） |
| 未发送飞书/Telegram 消息 | 无相关 API 调用（脚本级审计） |
| 未修改文件系统（除日志追加外） | `find` 特定路径 `-mmin -1` 差异（可选验证） |
| 未执行 `git commit/push/checkout` | 无 git 命令调用 |

---

## 5. A+B allowlist 及文件级改动授权

### 5.1 A 组：user systemd unit（4 个，只读引用）

| 文件 | 类型 | 授权改动 | 禁止 | 说明 |
|---|---|---|---|---|
| `~/.config/systemd/user/daily-stock-analysis.service` | 只读引用 | 不允许修改 | 不允许修改 `ExecStart`、`Type`、`WorkingDirectory` | Design 阶段可能参考其字段值，但不得以本卡名义修改 |
| `~/.config/systemd/user/tradingagents-cn.service` | 只读引用 | 不允许修改 | 同上 | 同上 |
| `~/.config/systemd/user/hermes-gateway-yquant.service` | 只读引用 | 不允许修改 | 同上。特别禁止修改 gateway unit definition overrides | 单位定义 outdated 是独立审计项 |
| `~/.config/systemd/user/hermes-gateway-yinglong.service` | 只读引用 | 不允许修改 | 同上 | 同上 |

**A 组设计原则**：现有 unit 定义是调用的参考输入。systemd 运行配置修改是生产副作用，Implement 前须在 Design 中逐项固化最小变更、回滚、验证和禁止自动重启策略。

### 5.2 B 组：TA-CN 启动入口候选

| 文件 | 类型 | 授权改动 | 说明 |
|---|---|---|---|
| `skills/apps/TradingAgents-CN/start_all.sh` | 仅读 | **不得修改** | 其 `--no-smoke` 参数供启动入口调用。不在本阶段修改脚本。Design 阶段确定是否需要 wrapper。 |

### 5.3 C 组：DSA 扩展候选（仅当现 /health 不足）

| 文件 | 类型 | 授权改动 | 触发条件 | 说明 |
|---|---|---|---|---|
| `skills/research/daily_stock_analysis/api/app.py` | 可增量修改 | 仅允许在现有 health check handler 添加初始化完成标志位检查 | 仅当 Design 阶段调研确认 DSA lifespan 包含阻塞初始化且现 `/health` 在该期间返回 200 时 | 不得修改业务路由、分析流程、报告生成或 API schema。 |

### 5.4 D 组：项目内只读 status/probe helper 候选

| 文件路径（候选） | 类型 | 授权改动 | 说明 |
|---|---|---|---|
| `scripts/service_readiness/`（新目录） | 可新增 | 新增只读 Python 脚本 | 仅当现有入口（B 组）不足以表达 readiness 时。必须满足 §3.2 和 §4.4 的探针与零副作用契约。 |

### 5.4.1 DSA 冷启动窗口的最小实现参数 allowlist

后续 Design/Implement 对本次 false-failed 修复仅可选择下列现有 unit/probe 参数及其**DSA 服务特定**取值：

| 参数类别 | 允许目的 | 明确边界 |
|---|---|---|
| `--max-retries` / 等效连续失败阈值 | 在 24 秒窗口耗尽后才用于最终 failed 裁决 | 预算内不得触发 failed；不得影响 TA-CN 或 Gateway 默认值 |
| `--interval` / 等效固定轮询间隔 | 在有限预算内重复只读 probe | 固定值；必须保证 API-ready 后仍至少有一次 probe 机会；不得指数退避或无限循环 |
| `--timeout` / 单次请求 timeout | 限制一次 GET/PID/端口/cgroup 检查的时长 | 不得超过 RFC 单次 probe 上限 10 秒；不得改变 endpoint 或 HTTP method |
| DSA 总预算/截止时间参数或等效本地常量 | 固化 `24s = 14s + 10s` 的窗口 | 仅 DSA；不得被通用全局默认值缩短；不得扩大为无限等待 |
| DSA `ExecStartPost` 调用参数 | 将上述 DSA 专用参数传入既有单服务 probe | 保持现有 `ExecStartPost=-` 容错策略；不得修改 endpoint、端口、其他服务调用或 `ExecStart`/restart 语义 |

除该表外，Design 不得改变任何全局服务语义；不得新增自动 restart、kill、POST、写数据库、消息发送或交易动作。任何需要超出此 allowlist 的方案必须退回 RFC/SPEC 重新裁决。

### 5.5 强制不动文件清单

以下文件在本任务中绝对禁止创建、修改、删除或纳入任何变更：

```
docs/operations/restart-tradingagents-cn.md       # 已有删除状态
scripts/t4_preflight/smoke_sector.py
tests/scripts/t4_preflight/test_smoke_flow.py
tests/scripts/t4_preflight/test_smoke_sector.py
tests/scripts/t4_preflight/test_smoke_sentiment.py
```

以下范围在本任务中绝对禁止创建、修改、删除或纳入任何变更：

```
skills/data/unified_data/                          # Unified Data 层
skills/strategies/                                 # 策略模块
skills/risk/                                       # 风控模块
skills/portfolio/                                  # 组合管理
skills/reports/                                    # 报告生成
skills/apps/TradingAgents-CN/app/services/         # TA-CN 数据业务路由
skills/apps/TradingAgents-CN/app/routers/          # TA-CN API 路由
skills/research/daily_stock_analysis/src/          # DSA 分析业务
docs/rfc/03_data/                                  # Phase 3 文档
docs/spec/03_data/                                 # Phase 3 文档
docs/design/03_data/                               # Phase 3 文档
docs/design/README.md                              # 全局设计模板
```

---

## 6. 测试矩阵

### 6.1 Smoke test（每项服务一次探针验证）

| 编号 | 场景 | 预置条件 | 操作 | 预期结果 |
|---|---|---|---|---|
| S-001 | DSA 探针 PASS | DSA 正常运行 | 执行 DSA probe 集合（P-DSA-1~4） | 全部 PASS，status=ready |
| S-002 | DSA 探针 FAIL | DSA 未启动 | 执行 DSA probe 集合 | status=starting，探针超时 |
| S-002a | DSA 已测冷启动边界 | 真正 DSA 冷启动；记录同一启动轮次的开始、systemd Started、API ready | 在 API ready 前运行 DSA 单服务 probe | 对约 14 秒 API-ready 路径，24 秒预算内所有失败均为 starting，不得先输出 failed；API ready 后仅 health=200 且 MainPID/端口/cgroup 一致时 ready |
| S-003 | TA-CN 探针 PASS | TA-CN 正常运行 | 执行 TA-CN probe 集合（P-TACN-1~4） | 全部 PASS，status=ready |
| S-004 | TA-CN 探针降级 | TA-CN 运行但 `/api/readyz` 非 200 | 执行 TA-CN probe 集合 | status=degraded（P-TACN-1/4 PASS，P-TACN-2 FAIL） |
| S-005 | Gateway yquant 探针 PASS | Gateway 正常运行且已连接 | 执行 Gateway probe 集合（P-GWY-1~3） | 全部 PASS，platform_connected=confirmed_at_boot |
| S-006 | Gateway yquant 探针降级 | Gateway 正常运行但未连接 | 执行 Gateway probe 集合（P-GWY-1~2 PASS，P-GWY-3 无连接证据） | status=degraded，platform_connected=unknown |
| S-007 | Gateway yinglong 探针 | 同 S-005/S-006 | 同上，service name 替换 | 同 S-005/S-006 |

### 6.2 冷启动验收记录验证

| 编号 | 场景 | 操作 | 预期结果 |
|---|---|---|---|
| V-001 | 正常冷启动（所有服务就绪） | 执行全流程 readiness 等待 | 验收记录 4 services 全部 ready，total_wait_seconds 有值，side_effect_free=true |
| V-002 | 部分服务启动失败 | 模拟某服务 crash | 验收记录中该服务 status=failed，其余服务不受影响 |
| V-003 | Gateway 无连接证据 | 网络不可达 | 对应 Gateway 服务 status=degraded，platform_connected=unknown |
| V-004 | 总等待超时 | 所有服务持续 unready | 超时后所有服务 status=failed，验收记录输出总耗时 |
| V-005 | 零副作用审计 | 执行全流程后检查 | 无 POST/PUT/DELETE 调用，MongoDB 文档计数不变，无外部消息发送 |
| V-006 | TA-CN 冷启动入口 | 使用 `--no-smoke` 启动 | journal 中无 `/api/sync/stock_basics/run` 的 POST 记录 |

### 6.3 probe 边界测试

| 编号 | 场景 | 操作 | 预期结果 |
|---|---|---|---|
| B-001 | probe 超时（> 10s） | 向不存在的端口发请求 | probe_error=timeout，状态不切为 failed（除非连续超时达上限） |
| B-002 | probe 目标不存在（connection refused） | 服务未启动时 probe | probe_error=connection_refused，status 保持 starting |
| B-002a | DSA 预算内连续失败 | 模拟或注入连续失败达到阈值、但 `elapsed_seconds < 24` | 仍输出 `starting`，不得输出 `consecutive_failures` 的最终 failed |
| B-002b | DSA 预算耗尽后连续失败 | 使 DSA 未满足 ready 且 `elapsed_seconds ≥ 24` | 仅在连续失败阈值满足后输出 failed；流程在有限窗口后停止，不无限等待 |
| B-003 | `platform_connected` journal 跨 boot 污染 | 手动注入旧 connected 日志 | 通过 `journalctl --since` 过滤仅本次启动；旧日志不影响判定 |

---

## 7. 强制约束

### 7.1 零副作用红线

Implement 阶段中，以下行为**绝对禁止**：

1. POST/PUT/DELETE HTTP 请求到任何服务。
2. MongoDB/Redis 写操作（插入、更新、删除）。
3. 调用 TA-CN 的 `/api/sync/*` 路径。
4. 调用 Hermes 的 `send_message`、`send_notification`、`send_alert` 等消息推送 API。
5. 执行 `git commit`、`git push`、`git reset --hard`、`git checkout` 等 git 写入操作。
6. 修改 systemd 配置后不恢复原状。
7. 修改 cron 条目。
8. 修改 `.env` 或 profile config。

### 7.2 约束检查清单

评审时必须逐项检查：

- [ ] probe 脚本仅使用 GET 和 TCP 检查。
- [ ] 无 import 或调用任何写入类 lib（`pymongo`、`motor`、`redis`、`httpx` POST client）。
- [ ] 无任何 POST URL 字符串（即使注释中也不出现生产 POST 路径）。
- [ ] systemd unit 修改（如有）在 Design 中附有精确 diff 和回滚指令。
- [ ] `platform_connected` 不使用 `grep -v` 排除模式（避免假阳性）。
- [ ] 验收记录 `side_effect_free` 硬编码为 `true`，不由运行时推断。

---

## 8. 依赖与引用

- **来源**：RFC-10-010-service-readiness-and-cold-start-governance（V0.3）
- **关联 Design**：（尚未创建，T2 使用）DESIGN-10-010-service-readiness-and-cold-start-governance
- **引用文件**：
  - `~/.config/systemd/user/daily-stock-analysis.service`
  - `~/.config/systemd/user/tradingagents-cn.service`
  - `~/.config/systemd/user/hermes-gateway-yquant.service`
  - `~/.config/systemd/user/hermes-gateway-yinglong.service`
  - `skills/apps/TradingAgents-CN/start_all.sh`
  - `skills/apps/TradingAgents-CN/app/routers/health.py`（TA-CN `/api/readyz`、`/api/health`）
  - `skills/research/daily_stock_analysis/api/app.py`（DSA `/health`、`/api/health`）

---

## 9. 附录

### A. 当前 systemd unit 关键属性汇总（只读参考）

| 服务 | Type | ExecStart | WorkingDirectory | Restart | RestartSec |
|---|---|---|---|---|---|
| DSA | simple | `main.py`（via venv python3.12） | `skills/research/daily_stock_analysis/` | always | 30 |
| TA-CN | simple | `start_all.sh` | `skills/apps/TradingAgents-CN/` | always | 30 |
| Gateway yquant | simple | `hermes gateway run --profile yquant` | `~/.hermes/profiles/yquant` | always | 5 |
| Gateway yinglong | simple | `hermes gateway run --profile yinglong` | `~/.hermes/profiles/yinglong` | always | 5 |

### B. TA-CN `start_all.sh` 启动阶段时间估计

| 阶段 | 预计耗时 | 副作用 |
|---|---|---|
| pre-flight（env/settings 验证） | 1-2s | 无 |
| stop（清理残留进程） | 1-3s | 进程 kill |
| spawn backend | 1s | 无 |
| 端口等待（90s 超时） | 5-30s（首次冷启动） | 无 |
| `/openapi.json` 健康检查 | 1-3s | GET（只读） |
| scheduler jobs 校验 | 3-5s | 读日志文件 |
| POST smoke（默认开启） | ~60s（SMOKE_TIMEOUT） | **POST /api/sync/stock_basics/run** |
| 前端启动 | 5-15s | 无 |

冷启动路径必须跳过 "POST smoke" 阶段，使总启动时间从 ~90s 降至 ~30s。
