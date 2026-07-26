# DESIGN-10-010：冷启动 Readiness 与无副作用依赖等待治理 — 实现设计

## 元数据

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-26 |
| 最后更新 | 2026-07-26 |
| 版本号 | V0.1 |
| 所属模块 | 10_infra（基础设施 / 服务治理） |
| 来源 RFC | RFC-10-010-service-readiness-and-cold-start-governance（V0.1） |
| 来源 SPEC | SPEC-10-010-service-readiness-and-cold-start-governance（V0.1） |
| 适配 Agent | YQuant-Developer-Engineer（Implement）、YQuant-Test-Engineer（Verify）、YQuant-Reviewer-Principal（Review） |
| 标签 | #infra #readiness #cold-start #systemd #service-governance #wsl #design |

## 版本历史

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-26 | 初始创建：冻结 probe 脚本设计与契约、systemd unit 最小变更、TA-CN 冷启动入口、DSA health 裁决、测试与验证方案、零副作用审计方法 | YQuant-Principal |

---

## 1. 设计与实现决策总结

### 1.1 全局决策

| 决策 | 选择 | 理由 |
|---|---|---|
| Probe 实现语言 | Python 3.12（stdlib），不引入第三方依赖 | 项目中各服务均使用 Python 3.12，stdlib + 系统命令（curl/ss/journalctl）可覆盖所有 probe 需求 |
| Probe 输出格式 | JSON，写本地文件 + stdout | SPEC §4.1 JSON schema 是契约；本地文件可供后续验证脚本消费；stdout 可供 systemd journal 捕获 |
| ExecStartPost 处理 | 使用 `-` 前缀（`ExecStartPost=-`）使失败不触发 restart | Type=simple 下 ExecStartPost 非零退出会标记 unit 为 failed，与 Restart=always 组合会引发重启循环；`-` 前缀使退出码被忽略 |
| TA-CN 冷启动入口 | 修改 `tradingagents-cn.service` 的 `ExecStart`，追加 `--no-smoke`，不新增 wrapper | `start_all.sh` 原生支持 `--no-smoke`（已确认）；wrapper 增加无需的文件变更 |
| DSA `/health` 扩展 | **不扩展**。现状 `/health` 静态响应 + FastAPI lifespan 语义已足够表达 readiness | FastAPI lifespan 在 uvicorn 绑定端口前完成 `yield`；因此 `/health` 200 等价于 lifespan 完成 + 应用可服务。无需增加初始化标志位 |
| Cold-start 报告载体 | 文件：`logs/cold-start-report.json`（项目根下 logs 目录） | 文件持久化易消费、易审计、不影响现有日志流。不写入 MongoDB 避免写库副作用 |
| Probe 调用图 | 单入口 Python 脚本接收 `--service`/`--all` 参数，内部按服务分派 probe 函数 | 单一入口便于测试和审计追踪；`--all` 模式用于一次冷启动全检 |

### 1.2 文件级 allowlist（Implement 阶段允许修改/新增的完整清单）

| 组 | 文件 | 操作 | 变更内容 |
|---|---|---|---|
| A | `~/.config/systemd/user/daily-stock-analysis.service` | 增量修改 | 追加 `ExecStartPost=-` 行调用 probe 脚本 |
| A | `~/.config/systemd/user/tradingagents-cn.service` | 增量修改 | 修改 `ExecStart` 追加 `--no-smoke`；追加 `ExecStartPost=-` 行 |
| A | `~/.config/systemd/user/hermes-gateway-yquant.service` | 增量修改 | 追加 `ExecStartPost=-` 行调用 probe 脚本 |
| A | `~/.config/systemd/user/hermes-gateway-yinglong.service` | 增量修改 | 追加 `ExecStartPost=-` 行调用 probe 脚本 |
| D | `scripts/service_readiness/readiness_probe.py` | **新建** | 主 probe 脚本（见 §3 详细契约） |
| D | `scripts/service_readiness/cold_start_report_schema.json` | **新建** | Cold-start 报告 JSON schema，供验证用（不可执行） |
| — | `logs/cold-start-report.json` | 运行时生成 | cold-start 验收记录输出（非源代码，.gitignore 候选） |

**Implement 阶段禁止修改**（除 allowlist 外）：RFC §6 禁止候选、SPEC §5.5 强制不动文件清单中的所有文件。特别重申：
- `docs/operations/restart-tradingagents-cn.md`（D 状态）、`scripts/t4_preflight/` 下所有文件、`tests/scripts/t4_preflight/` 下所有文件
- `skills/data/unified_data/`、`skills/strategies/`、`skills/risk/`、`skills/portfolio/`、`skills/reports/`
- `skills/apps/TradingAgents-CN/app/services/`、`skills/apps/TradingAgents-CN/app/routers/`（除只读引用）
- `skills/research/daily_stock_analysis/src/`（DSA 分析业务）
- Hermes core、Hermes profile config、cron、MongoDB schema、`docs/rfc/03_data/`、`docs/spec/03_data/`、`docs/design/03_data/`、`docs/design/README.md`

---

## 2. 只读发现 — 事实记录与差异裁决

### 2.1 四服务 systemd unit 现状

| 服务 | unit 路径 | Type | ExecStart | WorkingDirectory | Restart | RestartSec | 端口 |
|---|---|---|---|---|---|---|---|
| DSA | `daily-stock-analysis.service` | simple | `.venv/bin/python3.12 main.py` | `.../daily_stock_analysis` | always | 30 | 8000（默认） |
| TA-CN | `tradingagents-cn.service` | simple | `start_all.sh` | `.../TradingAgents-CN` | always | 30 | 8000（BACKEND_PORT） |
| Gateway yquant | `hermes-gateway-yquant.service` | simple | `python -m hermes_cli.main --profile yquant gateway run` | `~/.hermes/profiles/yquant` | always | 5 | 无固定端口（Hermes gRPC/HTTP） |
| Gateway yinglong | `hermes-gateway-yinglong.service` | simple | `python -m hermes_cli.main --profile yinglong gateway run` | `~/.hermes/profiles/yinglong` | always | 5 | 无固定端口（Hermes gRPC/HTTP） |

注意：DSA 与 TA-CN 均默认绑定 8000 端口——这是历史共存问题，不在本任务范围内修改。若需同时启用两服务，需人工确认端口错开。

### 2.2 DSA 端口裁决（SPEC §3.2.1 与「127.0.0.1:8888」差异）

**结论**：SPEC 中 `localhost:8000` 正确，`127.0.0.1:8888` 是无历史残留配置的误记。

证据链：
- `server.py` L52：`uvicorn.run("server:app", host="0.0.0.0", port=8000)` — 入口硬编码 8000
- `src/config.py` L1099：`webui_port: int = 8000` — 配置默认值 8000
- `src/core/config_registry.py` L3172-3188：`WEBUI_PORT` 默认值 `"8000"`
- `main.py` `parse_arguments()` L386：`--port` 默认值说明为 `WEBUI_PORT`（未配置时 8000）
- 全项目搜索 `8888`：Python 源码中无任何 8888 或 127.0.0.1:8888 的端口配置引用（仅在 .env 中有可能的历史配置，但非当前代码基线）

**结论**：DSA probe 目标为 `http://localhost:8000/health` 和 `http://localhost:8000/api/health`，无需修正 SPEC。

### 2.3 TA-CN health 端点验证

TA-CN `app/main.py` L788：
```python
app.include_router(health.router, prefix="/api", tags=["health"])
```

`app/routers/health.py` 中各端点的实际路径：
- `@router.get("/health")` → **`/api/health`** — 返回 `{"success": true, "data": {"status": "ok", "version": "...", "timestamp": ..., "service": "TradingAgents-CN API"}, "message": "服务运行正常"}`
- `@router.get("/healthz")` → **`/api/healthz`** — 返回 `{"status": "ok"}`
- `@router.get("/readyz")` → **`/api/readyz`** — 返回 `{"ready": true}`

**结论**：SPEC P-TACN-2（`/api/readyz` → `{"ready": true}` → HTTP 200）和 P-TACN-3（`/api/health` → JSON `success == true`）的正确性已确认。

### 2.4 TA-CN `--no-smoke` 可用性确认

**结论**：`start_all.sh` 原生支持 `--no-smoke`（L39），可直接被 unit ExecStart 调用。无需新增 wrapper。

### 2.5 DSA `/health` 扩展必要性裁决

DSA `api/app.py` L226-294 的 `app_lifespan` 分析：
- `RuntimeSchedulerService.reconcile_from_config()` — 轻量 sync 调用
- `_schedule_stock_index_background_refresh()` — 使用 `asyncio.create_task`，不阻塞 lifespan 的 `yield`
- `_check_frontend_assets_consistency()` — 仅文件系统检查
- 以上均在 uvicorn 调用 lifespan 期间完成。FastAPI 契约保证：**lifespan 的 `yield` 完成前，uvicorn 不会接受请求**。因此 `/health` 200 等价于 lifespan+应用就绪。

**结论**：**不扩展 DSA `/health`**。当前静态 `{"status": "ok", "timestamp": "..."}` 已充分表达 readiness。SPEC P-DSA-1 和 P-DSA-2 的现有 probe 定义即可。

### 2.6 Gateway unit definition outdated 审计

审计对象：`hermes-gateway-yquant.service` 的 `ExecStart`。

```ini
ExecStart=/home/pascal/workspace/hermes-agent/venv/bin/python -m hermes_cli.main --profile yquant gateway run
```

当前 format 为 `hermes_cli.main --profile <name> gateway run`。此为 Hermes Agent 的 canonical CLI 入口格式，已确认在 WSL 上可用。未发现明确 "outdated" 证据——ExecStart 路径和参数与当前 Hermes 版本匹配。**本任务中不做修改**，保留独立审计项标记（若未来 Hermes 更新改变 CLI 签名，由升级脚本 `scripts/upgrade_hermes_submodule.sh` 或专人处理）。

### 2.7 Gateway `platform_connected` journal 匹配先验知识

未执行 `journalctl` 实时读取（本任务禁止 live-read 外呼），但依据 gateway codebase 中 `gateway/session.py` 的日志模式，SPEC §4.3 的匹配规则——"connected"、"session started"、"platform.*connected"、"WebSocket.*connected"——覆盖了 gateway 的主要连接日志路径。

### 2.8 Gateway 无固定端口

Gateway yquant/yinglong 无 HTTP 服务端口（非 Web API 服务），因此 probe 不包含 TCP 端口检查。readiness 判定依赖 systemd unit active + PID 存活 + journal platform_connected 证据三条。

---

## 3. `readiness_probe.py` — 详细契约

### 3.1 文件定位

```
scripts/service_readiness/readiness_probe.py
```

### 3.2 CLI 接口

```
usage: readiness_probe.py [-h] (--service {DSA,TA-CN,gw-yquant,gw-yinglong} | --all)
                           [--timeout TIMEOUT] [--interval INTERVAL]
                           [--max-retries MAX_RETRIES] [--report REPORT_PATH]
                           [--boot-id BOOT_ID]

Probe a YQuant service or all services for readiness.

options:
  -h, --help            show this help message and exit
  --service {DSA,TA-CN,gw-yquant,gw-yinglong}
                        Service to probe (mutually exclusive with --all)
  --all                 Probe all 4 services sequentially
  --timeout TIMEOUT     Per-probe timeout in seconds (default: 10)
  --interval INTERVAL   Poll interval in seconds (default: 5)
  --max-retries MAX_RETRIES
                        Max consecutive failures before marking failed (default: 3)
  --report REPORT_PATH  Path to append cold-start report JSON (optional)
  --boot-id BOOT_ID     Boot identifier for the report (default: auto from timestamp)
```

### 3.3 Exit codes

| Exit code | Meaning |
|---|---|
| 0 | All probed services ready (or degraded for Gateway with unknown platform) |
| 1 | One or more services in `failed` state |
| 2 | Probe timeout — at least one service timed out |
| 3 | Invalid arguments |
| ≥10 | Internal error (unexpected exception) |

### 3.4 stdout 输出契约

每轮 probe 输出一条 JSON（ndJSON 格式），遵循 SPEC §4.1 schema。每次 probe 迭代输出一行。末行是最终状态。

```json
{"service": "DSA", "status": "starting", "probe": "P-DSA-1", "probe_http_status": null, "probe_error": null, "probe_count": 1, "elapsed_seconds": 0.5, "platform_connected": null, "side_effect_free": true}
{"service": "DSA", "status": "ready", "probe": "P-DSA-1", "probe_http_status": 200, "probe_error": null, "probe_count": 1, "elapsed_seconds": 0.5, "platform_connected": null, "side_effect_free": true}
```

**注**：`probe_count` 从 1 开始计数，每轮 probe 迭代（重试前）自增 1。`elapsed_seconds` 从脚本首次 probe 该服务起计时。

### 3.5 调用图

```
readiness_probe.py
├── main()
│   ├── parse_args()
│   ├── if --all:
│   │   └── for service in [DSA, TA-CN, gw-yquant, gw-yinglong]:
│   │       └── probe_one_service(service, args)
│   └── else:
│       └── probe_one_service(service, args)
│
├── probe_one_service(service, args)
│   ├── if DSA:
│   │   ├── probe_p_dsa_1()    # curl http://localhost:8000/health
│   │   ├── probe_p_dsa_2()    # curl http://localhost:8000/api/health (fallback)
│   │   ├── probe_p_dsa_3()    # ps -p $(systemctl show MainPID)
│   │   └── evaluate_dsa(p1, p2, p3, elapsed)
│   ├── if TA-CN:
│   │   ├── probe_p_tacn_1()   # ss -tlnp | grep :8000
│   │   ├── probe_p_tacn_2()   # curl http://localhost:8000/api/readyz
│   │   ├── probe_p_tacn_3()   # curl http://localhost:8000/api/health → success == true?
│   │   ├── probe_p_tacn_4()   # ps -p $(systemctl show MainPID)
│   │   └── evaluate_tacn(p1..p4, elapsed)
│   └── if gw-yquant / gw-yinglong:
│       ├── probe_p_gwy_1()    # systemctl is-active --quiet
│       ├── probe_p_gwy_2()    # ps -p $(systemctl show MainPID)
│       ├── probe_p_gwy_3()    # journalctl match for platform_connected
│       └── evaluate_gwy(p1..p3, elapsed)
│
├── probe_p_dsa_1()
│   └── subprocess.run(["curl", "-sf", "-o", "/dev/null",
│                       "--max-time", str(timeout),
│                       "http://localhost:8000/health"])
│       return (exit_code==0, http_status or null)
├── probe_p_dsa_2()
│   └── same but "http://localhost:8000/api/health"
├── probe_p_dsa_3()
│   └── subprocess.run(["ps", "-p", main_pid])
│       where main_pid = subprocess.check_output(
│           ["systemctl", "--user", "show", "-p", "MainPID",
│            "daily-stock-analysis.service", "--value"])
│       return (exit_code==0, None)
│
├── probe_p_tacn_1()
│   └── subprocess.run(["ss", "-tlnp"], capture_output=True)
│       → check ":8000 " in stdout
├── probe_p_tacn_2()
│   └── subprocess.run(["curl", "-sf", "-o", "/dev/null",
│                       "--max-time", str(timeout),
│                       "http://localhost:8000/api/readyz"])
├── probe_p_tacn_3()
│   └── subprocess.run(["curl", "-sS", "--max-time", str(timeout),
│                       "http://localhost:8000/api/health"],
│                      capture_output=True, text=True)
│       → parse JSON, check .success == True
├── probe_p_tacn_4()
│   └── same as probe_p_dsa_3() but "tradingagents-cn.service"
│
├── probe_p_gwy_X(unit_name)
│   ├── p_gwy_1:
│   │   subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit_name])
│   ├── p_gwy_2:
│   │   subprocess.run(["ps", "-p", main_pid])  # main_pid from systemctl show
│   └── p_gwy_3:
│       → subprocess.run(["journalctl", "--since", f"@{unit_active_ts}",
│                        "_SYSTEMD_UNIT=" + unit_name, "--output=short-iso",
│                        "--no-pager"], capture_output=True, text=True)
│       → apply matching rules (SPEC §4.3):
│         regex: r"(connected|session started|platform.*connected|WebSocket.*connected)"
│       → return (matched_bool, timestamp_or_null, evidence_or_null)
│
├── evaluate_dsa(results, elapsed)
│   → implements SPEC §3.2.1 readiness judgment
├── evaluate_tacn(results, elapsed)
│   → implements SPEC §3.2.2 readiness judgment
└── evaluate_gwy(results, elapsed)
    → implements SPEC §3.2.3 readiness judgment
```

### 3.6 权限

- 运行用户：pascal（systemd --user 的 owner，该用户对自身 unit 有 systemctl/journalctl/ps 读权限）
- 不需要 root/sudo
- `journalctl --since` + `_SYSTEMD_UNIT=` 过滤在 user 上下文中可用（用户只可见自己的 unit journal）

### 3.7 超时与重试

| 参数 | 默认值 | 说明 |
|---|---|---|
| 单次 probe 超时 | 10s | 由 curl `--max-time` 保证；TCP 检查瞬时可忽略 |
| 轮询间隔 | 5s | 前后 probe 迭代的 sleep 间隔 |
| 连续失败上限 | 3 | 连续 3 次全部 probe FAIL → 标记为 `failed` 并停止轮询 |
| 总等待超时 | 120s | 从首次 probe 起计；超时后所有未 ready 服务标记为 `failed` |
| 降级等待上限 | 120s | Gateway 在 `platform_connected=unknown` 下持续等待至总超时 |

**特殊规则**：Gateway 的 `platform_connected` 不参与「连续失败上限」计数。P-GWY-1/2 PASS 但 P-GWY-3 为 `unknown` 时，状态为 `degraded` 而非 `failed`，继续等待至总超时。

### 3.8 临时文件 / 日志落点

| 路径 | 用途 | 清理 |
|---|---|---|
| `logs/cold-start-report.json` | Cold-start 验收记录（最终产物） | 每次冷启动覆盖；手动清理 |
| stdout（ndJSON） | 实时 probe 状态行 | 随进程结束释放 |
| stderr | 错误日志 | 系统 journal 捕获 |

**无临时文件写入**。所有中间状态通过 stdout（ndJSON）流式输出，不上盘。

### 3.9 脱敏

- 所有 stdout/stderr 输出不含 API key、token、MongoDB URI、环境变量值
- 命令行参数中不含任何敏感信息（只有 service name、端口、unit name、时间戳）
- `journalctl` 输出中不包含消息正文，仅检查 `connected` 等通用日志模式

### 3.10 失败语义

| 失败源 | 行为 |
|---|---|
| `curl` 命令不存在 | 打印错误到 stderr，exit 10 |
| `systemctl` 不可用 | 打印错误到 stderr，exit 11 |
| 所有服务的 total_timeout | 输出最终 failed 状态 JSON，exit 2 |
| 部分服务 ready + 部分 failed | 输出混合状态，exit 1 |
| 报告文件不可写（`--report` 指定路径） | 打印警告到 stderr，继续无文件输出（不致命） |
| 意外的 Python 异常 | 打印 traceback 到 stderr，exit 99 |

---

## 4. 4-state 状态转换细节

### 4.1 全局状态机

```
         +-----------+
         |  starting |  ← systemd active 但 probe 未确认
         +-----+-----+
               |
         首次 probe
         /    |    \
        v     v     v
   +-------+ +-------+ +-------+
   | ready | |degraded| |failed |  ← probe 判定
   +-------+ +-------+ +-------+
       |         |         |
       +---->----+         |   degraded 恢复为 ready（后续 probe PASS）
       |         |         |
       +----<----+         |   ready 进入 degraded（部分 probe 降级）
       |         |         |
       +---------+-------->+   ← 转为 failed（连续失败达上限或总超时）
```

### 4.2 各服务状态转换表

#### DSA

| 当前状态 | 条件 | 下一状态 |
|---|---|---|
| starting | P-DSA-1 PASS AND P-DSA-3 PASS | ready |
| starting | P-DSA-1 FAIL AND P-DSA-2 FAIL OR P-DSA-3 FAIL（连续 < 3 次） | starting（继续轮询） |
| starting | total_timeout | failed |
| starting | 连续 3 次全部 FAIL | failed |
| ready | 后续 probe 全部 PASS | ready（不变） |
| ready | P-DSA-1 单次 FAIL 但 P-DSA-2 PASS | ready（降级不适用，DSA 无 degraded） |

#### TA-CN

| 当前状态 | 条件 | 下一状态 |
|---|---|---|
| starting | P-TACN-1 PASS AND P-TACN-2 PASS AND P-TACN-3 success=true AND P-TACN-4 PASS | ready |
| starting | P-TACN-1 PASS AND P-TACN-4 PASS BUT P-TACN-3 返回 success=false 且 P-TACN-2 FAIL | degraded |
| starting | P-TACN-1 FAIL OR P-TACN-4 FAIL（连续 < 3 次） | starting（继续轮询） |
| starting | total_timeout 且 P-TACN-1 FAIL 或 P-TACN-4 FAIL | failed |
| starting | 连续 3 次 P-TACN-1 FAIL 或 P-TACN-4 FAIL | failed |
| ready | 后续 probe 全部 PASS | ready |
| ready | P-TACN-3 返回 success=false 但 P-TACN-1/4 PASS | degraded |
| degraded | 后续 probe 全部 PASS | ready |
| degraded | P-TACN-1/4 FAIL | failed |

#### Gateway yquant / yinglong

| 当前状态 | 条件 | 下一状态 |
|---|---|---|
| starting | P-GWY-1 PASS AND P-GWY-2 PASS AND P-GWY-3 confirmed_at_boot | ready |
| starting | P-GWY-1 PASS AND P-GWY-2 PASS AND P-GWY-3 unknown（无连接证据） | degraded |
| starting | P-GWY-1 FAIL OR P-GWY-2 FAIL（连续 < 3 次） | starting |
| starting | total_timeout 且 P-GWY-1/2 一直 FAIL | failed |
| ready | P-GWY-1/2 PASS 但 P-GWY-3 在后续轮询中变为 unknown（journal 证据不可逆？见下注） | degraded（不可逆降级） |
| degraded | 后续 P-GWY-3 变为 confirmed_at_boot | ready（恢复） |

**注**：journal 是一条生产一次的有序流。一旦 `platform_connected` 证据出现后就 `confirmed_at_boot`，不可能在相同 boot 中「消失」。因此 `ready → degraded` 的转换理论上不会因 P-GWY-3 状态变化而触发。但如果系统时间异常、journal 轮转或跨 boot 边界，应处理为 `degraded` 保守降级。

### 4.3 probe 顺序与依赖

每个服务的 probe 按顺序执行：

1. **TCP/port check**（DSA/TA-CN 适用，Gateway 跳过）— 最轻量，快速失败
2. **systemd is-active**（Gateway 适用）— 轻量状态查询
3. **PID 存活** — 确认进程还在
4. **HTTP GET health** — 服务级 readiness 检查
5. **journal platform_connected**（Gateway 适用）— 最重，最后执行

同一服务内按此顺序执行可快速失败。例如 TA-CN：若端口未绑定则无需发起 HTTP 请求。

---

## 5. systemd unit 变更设计

### 5.1 设计原则

- **不修改** `Type`、`WorkingDirectory`、`Restart`、`RestartSec`、`KillMode`、`KillSignal`、`TimeoutStopSec`
- **不新增**平行 wrapper、无限等待循环、自动级联重启、外部 sidecar
- ExecStartPost 使用 `-` 前缀，确保 probe 失败不影响 service active 状态
- ExecStartPost 调用绝对路径的 probe 脚本，确保 systemd PATH 独立
- TA-CN 的 ExecStart 修改：仅追加一个参数，不改变脚本调用方式

### 5.2 DSA unit diff

```diff
 [Service]
 Type=simple
 WorkingDirectory=/home/pascal/workspace/yquant-investment/skills/research/daily_stock_analysis
 ExecStart=/home/pascal/workspace/yquant-investment/skills/research/daily_stock_analysis/.venv/bin/python3.12 main.py
+ExecStartPost=-/home/pascal/workspace/yquant-investment/scripts/service_readiness/readiness_probe.py \
+    --service DSA \
+    --report /home/pascal/workspace/yquant-investment/logs/cold-start-report.json
 Restart=always
 RestartSec=30
```

**理由**：`ExecStartPost` 在 DSA 进程 fork 后立即运行 probe 脚本。脚本轮询 `/health` 直到服务就绪（或超时），将状态写入 cold-start report。`-` 前缀使 systemd 忽略 probe 退出码，避免重启循环。

### 5.3 TA-CN unit diff

```diff
 [Service]
 Type=simple
 WorkingDirectory=/home/pascal/workspace/yquant-investment/skills/apps/TradingAgents-CN
-ExecStart=/home/pascal/workspace/yquant-investment/skills/apps/TradingAgents-CN/start_all.sh
+ExecStart=/home/pascal/workspace/yquant-investment/skills/apps/TradingAgents-CN/start_all.sh --no-smoke
+ExecStartPost=-/home/pascal/workspace/yquant-investment/scripts/service_readiness/readiness_probe.py \
+    --service TA-CN \
+    --report /home/pascal/workspace/yquant-investment/logs/cold-start-report.json
 ExecStop=/home/pascal/workspace/yquant-investment/skills/apps/TradingAgents-CN/stop_all.sh
```

**理由**：
- `start_all.sh --no-smoke` 跳过 POST `/api/sync/stock_basics/run`，将冷启动时间从 ~90s 降至 ~30s（SPEC 附录 B）
- `ExecStartPost` probe 确认 TA-CN 后端 API readiness
- 不新增 `start_no_smoke.sh` wrapper，因为 `start_all.sh` 原生支持该参数

### 5.4 Gateway yquant unit diff

```diff
 [Service]
 Type=simple
 ExecStart=/home/pascal/workspace/hermes-agent/venv/bin/python -m hermes_cli.main --profile yquant gateway run
+ExecStartPost=-/home/pascal/workspace/yquant-investment/scripts/service_readiness/readiness_probe.py \
+    --service gw-yquant \
+    --report /home/pascal/workspace/yquant-investment/logs/cold-start-report.json
 WorkingDirectory=/home/pascal/.hermes/profiles/yquant
```

### 5.5 Gateway yinglong unit diff

```diff
 [Service]
 Type=simple
 ExecStart=/home/pascal/workspace/hermes-agent/venv/bin/python -m hermes_cli.main --profile yinglong gateway run
+ExecStartPost=-/home/pascal/workspace/yquant-investment/scripts/service_readiness/readiness_probe.py \
+    --service gw-yinglong \
+    --report /home/pascal/workspace/yquant-investment/logs/cold-start-report.json
 WorkingDirectory=/home/pascal/.hermes/profiles/yinglong
```

### 5.6 变更安全性说明

- **daemon-reload 时机**：Implement 阶段修改 unit 文件后，必须由 Pascal 确认后执行 `systemctl --user daemon-reload`（该操作是生产副作用，Design 和 Verify 阶段默认不执行）
- **restart 时机**：Implement 完成后，由 Pascal 手动或单独的受控操作执行逐 service restart
- **rollback**：恢复原 unit 文件内容 → `systemctl --user daemon-reload` → `systemctl --user restart <unit>`
- **冲突处理**：4 个 unit 各增加 ExecStartPost，无相互依赖；可单独启用/回滚单个服务

---

## 6. DSA `/health` 扩展 — 最终裁决

**不扩展**。最终理由：

1. FastAPI lifespan 语义保证 `yield` 完成前 uvicorn 不接受请求，因此 `/health` 200 等价于应用初始化完成。
2. 当前 DSA lifespan 中无阻塞操作——`_check_frontend_assets_consistency` 是文件系统检查（< 100ms），`reconcile_from_config` 是轻量 sync，`_schedule_stock_index_background_refresh` 是 `asyncio.create_task` 非阻塞。
3. DSA `/health` 返回 `{"status": "ok", "timestamp": "..."}`，已明确表达应用可达。
4. 若未来 DSA 增加阻塞初始化（如首次数据加载从 0 开始），再通过 C 组路径扩展。

---

## 7. Gateway `platform_connected` journal 匹配实现细节

### 7.1 journalctl 命令

```python
import subprocess
import re
from datetime import datetime

def probe_platform_connected(unit_name: str, unit_active_at: datetime) -> tuple:
    """Return (matched, timestamp_iso, evidence_text)"""
    since_ts = int(unit_active_at.timestamp())
    cmd = [
        "journalctl", "--since", f"@{since_ts}",
        "_SYSTEMD_UNIT=" + unit_name,
        "--output=short-iso", "--no-pager"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return (False, None, None)

    patterns = re.compile(
        r"(connected|session started|platform.*connected|WebSocket.*connected)",
        re.IGNORECASE
    )
    for line in result.stdout.splitlines():
        match = patterns.search(line)
        if match:
            # Extract ISO timestamp from short-iso format
            # Example: "2026-07-26T08:15:23+0800 hostname ..."
            ts = line[:25].strip()  # first ~25 chars = timestamp
            return (True, ts, line.strip())
    return (False, None, None)
```

### 7.2 时间戳提取

`journalctl --output=short-iso` 输出的首列格式为 `2026-07-26T08:15:23+0800`。提取前 25 字符即可获得 ISO 时间戳。

### 7.3 边界处理

| 场景 | 行为 |
|---|---|
| 首次匹配到 connected | 记录为 `confirmed_at_boot`，提取时间戳和证据行 |
| 多次匹配 | 取首次匹配的时间戳 |
| 无匹配且总超时 | `platform_connected=unknown`，`platform_evidence=null` |
| journalctl 命令失败（权限/轮转） | 捕获异常，标记为 `unknown` |
| unit_active_at 无法获取 | 使用脚本启动时间作为 `--since` 基准 |

### 7.4 跨 boot 污染防护

`journalctl --since @<unit_active_timestamp>` 确保只查询该组 unit 本次启动后的日志。由于 `--since` 基于时间戳过滤，跨 boot 的旧日志会被排除。但需注意：
- 若系统时钟在两次 boot 间未回跳，`--since` 足以隔离
- 若系统时钟异常回跳至过去，可能出现假阳性。WSL 环境下系统时钟通常与 Windows 宿主同步，回跳概率极低。不作为边界覆盖

---

## 8. 冷启动验证方案

### 8.1 离线单元测试

**目标**：验证 `readiness_probe.py` 各 probe 函数的输入输出契约，不依赖实际服务运行。

| 编号 | 测试路径 | 方式 | 预期 |
|---|---|---|---|
| UT-1 | DSA probe 函数模拟 curl 200 | mock subprocess 返回 exit 0 | probe 返回 PASS |
| UT-2 | DSA probe 函数模拟 curl 超时 | mock subprocess 超时异常 | probe 返回 timeout |
| UT-3 | TA-CN readyz probe 模拟 200 | mock curl 200 | P-TACN-2 PASS |
| UT-4 | TA-CN health probe 模拟 success=true | mock JSON 响应 `{"success": true, "data": {"status": "ok"}}` | P-TACN-3 PASS |
| UT-5 | TA-CN health probe 模拟 success=false | mock JSON 响应 `{"success": false}` | P-TACN-3 degraded 条件 |
| UT-6 | Gateway platform_connected 匹配 | mock journalctl 输出含 connected 行 | matched=True |
| UT-7 | Gateway platform_connected 无匹配 | mock journalctl 输出为空 | matched=False |
| UT-8 | 状态机 DSA starting→ready | 模拟所有 probe PASS | status=ready |
| UT-9 | 状态机 DSA starting→failed（超时） | 模拟连续超时达上限 | status=failed |
| UT-10 | 状态机 TA-CN starting→degraded | 模拟 P-TACN-1/4 PASS 但 P-TACN-2 FAIL, P-TACN-3 success=false | status=degraded |
| UT-11 | 状态机 Gateway starting→degraded（unknown） | 模拟 P-GWY-1/2 PASS, P-GWY-3 无匹配 | status=degraded, platform_connected=unknown |
| UT-12 | 状态机 Gateway degraded→ready（恢复） | 后续轮询 P-GWY-3 匹配 | status=ready, platform_connected=confirmed_at_boot |
| UT-13 | 报告文件写入 | `--report` 指定合法路径 | 文件存在且 JSON 有效 |
| UT-14 | 报告文件不可写 | `--report` 指定不可写路径 | 打印警告到 stderr，继续无文件输出 |
| UT-15 | `--service` 无效值 | 传入非法 service name | exit 3，打印 usage |
| UT-16 | `--all` 输出顺序 | 启动 "--all" mode | 4 services 依次输出，每服务先 starting 再终态 |

测试文件路径：`tests/scripts/service_readiness/test_readiness_probe.py`

### 8.2 服务级 smoke 测试

对应 SPEC §6.1 测试矩阵 S-001 至 S-007。在已运行的服务上执行 probe 脚本验证：

| 编号 | 命令 | 预期 |
|---|---|---|
| S-001 | `python readiness_probe.py --service DSA --timeout 5` | status=ready 或 status=starting（若 DSA 未运行） |
| S-002 | `python readiness_probe.py --service TA-CN --timeout 5` | status=ready 或 status=starting |
| S-003 | `python readiness_probe.py --service gw-yquant --timeout 10` | status=ready/degraded（取决于 Gateway 连接状态） |
| S-004 | `python readiness_probe.py --service gw-yinglong --timeout 10` | 同上 |
| S-005 | `python readiness_probe.py --all --timeout 10` | 4 services 全部输出终态 |

### 8.3 一次受控冷启动验证

**前置条件**：Implement 完成 + `systemctl --user daemon-reload` + Pascal 确认可重启固定服务。

**步骤**：
1. 记录当前 services 状态：`systemctl --user status daily-stock-analysis tradingagents-cn hermes-gateway-yquant hermes-gateway-yinglong`
2. 重启目标服务（由 Pascal 执行）：`systemctl --user restart <unit>`
3. 等待启动完成
4. 检查 cold-start report：`cat /home/pascal/workspace/yquant-investment/logs/cold-start-report.json`
5. 验证 JSON schema 符合 SPEC §4.2
6. 验证 `side_effect_free: true` 对所有服务成立
7. 验证所有 4 services 均出现且 status 非空
8. 验证 `total_wait_seconds` 有值
9. 由 Pascal 确认无 POST sync 触发：`grep "POST /api/sync/stock_basics/run" logs/backend.log` → 不应有匹配
10. 验证 journal 中无 POST smoke 记录：`journalctl --since "1 minute ago" _SYSTEMD_UNIT=tradingagents-cn.service | grep -i "smoke"` → 应为 `(no matches)` 或 `(--no-smoke) 跳过端到端 smoke`

### 8.4 零副作用审计方法

| 审计项 | 方法 | 阻断条件 |
|---|---|---|
| 脚本调用链 | 代码审查确认 `readiness_probe.py` 中无 POST/PUT/DELETE | 存在任何非 GET/TCP/journal 写操作的调用 |
| import 审计 | 审查 Python import 无 `pymongo`、`motor`、`redis`、`httpx`、`requests` | 存在上述 import |
| 命令审计 | 审查 subprocess.run 无 `git commit/push`、`curl -X POST` | 存在写操作命令 |
| journal 证据 | 完成冷启动后检查 `tradingagents-cn` unit journal 中无 POST smoke | 存在 POST `/api/sync/stock_basics/run` |
| 报告字段 | 审查 cold-start 报告所有 `side_effect_free` 值为 `true` | 任一服务 `side_effect_free` 为 `false` 或缺失 |

### 8.5 失败 / 回滚流程

| 场景 | 操作 |
|---|---|
| Probe 脚本报错 | 查看 stderr/traceback；修复后重新运行，无需重启服务 |
| ExecStartPost 错误导致服务标记为 failed | 检查 probe 脚本；修复后执行 `systemctl --user reset-failed <unit>` 再 restart |
| 某 unit 修改后启动失败 | `systemctl --user status <unit>` 查看 journal；恢复原 unit 文件 → `daemon-reload` → restart |
| Cold-start 报告 schema 不匹配 | 调整 probe 脚本输出字段 → 下次 ExecStartPost 自动更正 |
| POST smoke 被意外触发（side-effect 违规） | 立即停止服务；确认 --no-smoke 已生效；回滚 unit 修改 → 调查根因 |

---

## 9. RFC/SPEC 实质冲突与修正路径

### 9.1 发现：无实质冲突

经完整只读发现，RFC-10-010 和 SPEC-10-010 的四项服务定义、状态模型、probe 契约、零副作用约束、A+B allowlist 均与当前代码基线一致。以下为核查细节：

| 检查项 | RFC | SPEC | 代码基线 | 裁决 |
|---|---|---|---|---|
| DSA 端口 | 未硬编码（隐含 8000） | localhost:8000 | 8000（server.py, config default） | 一致 |
| DSA `/health` | 简单静态响应 | HTTP 200 | `{"status": "ok", "timestamp": "..."}` | 一致 |
| TA-CN `/api/readyz` | `/api/readyz` | `/api/readyz` | `@router.get("/readyz")` under prefix `/api` | 一致 |
| TA-CN `/api/health` | `success == true` | `success == true` | `{"success": true, "data": {"status": "ok"}}` | 一致 |
| TA-CN `--no-smoke` | 需使用 | 冷启动入口强制 | `start_all.sh --no-smoke`（L39） | 一致 |
| Gateway ExecStart | hermes gateway run | 同左 | `python -m hermes_cli.main --profile yquant gateway run` | 一致 |
| Gateway journal 匹配 | connected / session started / platform connected / WebSocket connected | 同左 | gateway/session.py 日志模式一致 | 一致 |
| Gateway unit definition | 不修改 | 同左 | 未发现明确 outdated 证据 | 一致（保留 tag） |

### 9.2 发现：SPEC 中 JDBC/ODBC 表遗漏

SPEC §4.3 的 `platform_connected` 匹配规则中，匹配字符串表使用了 Markdown 行而非正式表格（JDBC/ODBC 风格）。这不是实质冲突，但为保持文档一致性，建议在 Implement 前的 SPEC 修订中补充为：

```
| 匹配字符串 | 语义 | 来源 |
|---|---|---|
| `connected` | 通用连接日志 | gateway worker |
| `session started` | Telegram 会话启动 | telethon session |
| `platform.*connected` | 特定 platform 连接确认 | platform registry |
| `WebSocket.*connected` | WebSocket 连接确认 | WebSocket handler |
```

**修正路径**：Implement 开始前，由同一 worker 在 SPEC-10-010 的 §4.3 补充该表格，触发独立 review。

### 9.3 发现：ExecStartPost 使用注意事项

RFC §8.1 提出 ExecStartPost 方案，但需补充系统级行为约束——**Type=simple 下 ExecStartPost 非零退出会使 unit 标记为 failed**。本 Design 已通过 `-` 前缀解决。建议在 SPEC §3.2.5 探针执行规则汇总中补充一行：

```
| ExecStartPost 退出码 | 必须使用 `-` 前缀忽略失败；否则 Restart=always 会引发重启循环 |
```

**修正路径**：Implement 开始前，由同一 worker 在 SPEC-10-010 的 §3.2.5 追加该行。

### 9.4 修正优先级

上述两项修正为非致命不一致（Design 已通过决策规避），但建议在 Implement 前完成，降低后续维护者的认知成本。

---

## 10. 生产副作用分级

| 级别 | 操作 | 执行阶段 | 负责人 |
|---|---|---|---|
| **L0** — 无副作用 | 创建 probe 脚本文件；运行离线单元测试；代码审查 | Design + Verify + Review | YQuant-Dev + YQuant-Test + YQuant-Review |
| **L1** — 本地只读 | 在已运行的服务上执行 probe 脚本（GET only）；验证 stdout JSON 输出 | Verify | YQuant-Test |
| **L2** — 配置变更 | 修改 ~/.config/systemd/user/ 下的 unit 文件；执行 `systemctl --user daemon-reload` | Implement → Pascal 确认 → 执行 | Pascal（手动） |
| **L3** — 服务重启 | 对单个服务执行 `systemctl --user restart <unit>` | Implement 完成 → 冷启动验证 | Pascal（手动） |
| **L4** — 全服务冷启动 | 同时重启 4 个 unit 验证冷启动报告 | 集成验证 | Pascal（手动） |

**Design 阶段和 Verify 阶段默认不执行 L2/L3/L4 操作**。Implement 完成后，由 Pascal 在受控窗口内手工执行。

---

## 11. 交付物清单

| 文件 | 类型 | 状态 |
|---|---|---|
| `docs/design/10_infra/DESIGN-10-010-service-readiness-and-cold-start-governance.md` | Design 文档 | **本文件** |
| `scripts/service_readiness/readiness_probe.py` | Python 脚本 | Implement 创建 |
| `scripts/service_readiness/cold_start_report_schema.json` | JSON schema | Implement 创建 |
| `~/.config/systemd/user/daily-stock-analysis.service`（修改版） | systemd unit | Implement 修改 |
| `~/.config/systemd/user/tradingagents-cn.service`（修改版） | systemd unit | Implement 修改 |
| `~/.config/systemd/user/hermes-gateway-yquant.service`（修改版） | systemd unit | Implement 修改 |
| `~/.config/systemd/user/hermes-gateway-yinglong.service`（修改版） | systemd unit | Implement 修改 |
| `tests/scripts/service_readiness/test_readiness_probe.py` | pytest 测试 | Implement 创建 |

---

## 12. 验收条件

| 编号 | 条件 | 验证方式 |
|---|---|---|
| AC-1 | Design 文件单独存在、完整引用 RFC/SPEC、文件 allowlist 精确到路径 | 文件存在检查 + `git diff --check` |
| AC-2 | DSA 端口/health 契约冲突已明确裁决 | §2.2 和 §6 的最终结论 |
| AC-3 | TA-CN cold-start 入口有唯一确定性方案 | §1.1 决策表 + §5.3 unit diff |
| AC-4 | 4-state 转换表完整覆盖每项服务的 starting→ready/degraded/failed | §4.2 |
| AC-5 | Gateway journal 匹配有精确实现代码 | §7.1 |
| AC-6 | 离线单元测试覆盖 16 个场景 | §8.1 测试矩阵 |
| AC-7 | 零副作用审计方法明确 | §8.4 |
| AC-8 | 失败/回滚流程清晰 | §8.5 |
| AC-9 | RFC/SPEC 实质冲突已核查并列明修正路径 | §9 |
| AC-10 | 生产副作用分级明确 | §10 |
| AC-11 | 无新文件超出 1 个 Design 文档 + 2 个脚本 + 1 个 schema + 1 个测试文件 + 4 个 unit 修改 | §1.2 allowlist |
| AC-12 | 无修改：强制不动文件清单（SPEC §5.5）中的任一文件 | 文件存在性确认 |
