# RFC-10-010：冷启动 Readiness 与无副作用依赖等待治理

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 草稿（Draft） |
| 作者 | YQuant-Principal |
| 创建日期 | 2026-07-26 |
| 最后更新 | 2026-07-26 |
| 版本号 | V0.1 |
| 所属模块 | 10_infra（基础设施 / 服务治理） |
| 依赖RFC | RFC-10-003（infra 架构）、RFC-10-008（submodule 升级器） |
| 关联SPEC | SPEC-10-010-service-readiness-and-cold-start-governance |
| 替代RFC | 无 |
| AI适配 | Hermes Kanban profile worker（yquantprincipal → yquantdeveloper → yquanttester → yquantreviewer） |
| 标签 | #infra #readiness #cold-start #systemd #service-governance #wsl |

## 版本历史（Changelog）

| 版本号 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V0.1 | 2026-07-26 | 初始创建：定义冷启动 readiness 状态模型、四服务探针哲学、无副作用依赖等待约束与验收准则 | YQuant-Principal |

---

## 1. 执行摘要

当前 YQuant 的四项关键服务（DSA、TA-CN、Hermes Gateway yquant、Hermes Gateway yinglong）在系统冷启动（WSL 开机或 systemd --user 重启）时，均依赖 `systemd Type=simple` active 状态作为"可用"信号。实测表明 `active` 早于真实可就绪约 37-56 秒，且 `network-online.target` 在 WSL user-systemd 下不构成外部网络/飞书就绪证据。未建立统一 readiness 模型导致依赖等待不可靠、启动顺序无契约可循、降级状态不可观测。

本 RFC 定义统一的四状态模型（`starting` / `ready` / `degraded` / `failed`）、每项服务的只读探针语义和零副作用的依赖等待治理边界。目标是以最小变更面（不新增平行 wrapper、不修改 Hermes core、不涉及统一数据层/策略/风控/组合/交易执行），使 Design/Implement 阶段能以现有 user-systemd unit 和既有启动入口实现可控、可观测的冷启动编排。

---

## 2. 背景与动机

### 2.1 现状痛点

#### 2.1.1 systemd Type=simple active 的 readiness 鸿沟

四项服务的 systemd unit 均使用 `Type=simple`（见当前 unit 定义）：

- **DSA**（`daily-stock-analysis.service`）：`ExecStart=.venv/bin/python3.12 main.py`，FastAPI 应用在 uvicorn 绑定端口后 systemd 即标记 active，但应用内部可能仍在完成首次数据加载、模型初始化或前端的 `_check_frontend_assets_consistency` 检查。
- **TA-CN**（`tradingagents-cn.service`）：`ExecStart=start_all.sh`，脚本本身包含多阶段启动流程（pre-flight → graceful stop → spawn backend → 端口等待 → `/openapi.json` 健康检查 → scheduler jobs 校验 → smoke → frontend），systemd 在 start_all.sh 启动后即标记 active，但真实就绪需等完整个脚本周期。
- **Hermes Gateway yquant/yinglong**：`ExecStart=hermes gateway run`，`gateway status` 只证明进程运行，平台连接（Telegram/飞书/Lark）需要额外的 `connected` 信号。

**实测数据**：Type=simple active 到本地服务可就绪的时间差约 37-56 秒（基于 TA-CN `start_all.sh` 的 `BACKEND_STARTUP_TIMEOUT=90` 和 DSA 的 FastAPI lifespan 初始化耗时）。

#### 2.1.2 network-online.target 的 WSL 局限

当前所有 unit 的 `After=network-online.target` 在 WSL user-systemd 下不构成外部网络/飞书就绪证据。WSL 的 `network-online.target` 在 Windows 宿主网络栈初始化后即触发，不等待外部可达性。因此依赖该 target 做冷启动顺序编排不可靠。

#### 2.1.3 依赖等待的无契约现状

- 服务间无显式 readiness 查询契约：DSA 的 cron 报告依赖 TA-CN 的数据就绪，但触发时间基于硬编码 cron，而非 readiness 信号。
- 无统一降级状态：服务异常（如 MongoDB 连接失败、飞书 API 不可达）时只有 `active` 或 `inactive` 二元状态，中间态不可见。
- 启动日志分散：没有中心化的启动确认记录（unit started → local ready → gateway connected → 总等待时间）。

### 2.2 为什么不直接修复

- `Type=notify` 要求服务进程实现 systemd 通知协议，对 Python 应用侵入大且需引入 `systemd-python` 或 sd_notify 封装 —— 不在本 RFC 范围内。
- `ExecStartPost` + 轮询脚本可绕过 readiness 鸿沟，但须精确限定为只读 GET/TCP/probe，不得引入 POST/写库/同步 side effect。
- 修正 Hermes core 的 gateway status 语义或 unit definition 过时问题是独立审计项，本 RFC 不得顺带处理。

### 2.3 业务价值

- **减少人工干预**：冷启动后服务自动等待真实就绪，不再需要 Pascal 手动 `curl` 验证或 `journalctl -f` 盯着日志。
- **启动顺序可靠**：下游依赖（如 cron 报告）有可查询的 readiness 状态，不再依赖硬编码等待秒数。
- **状态可观测**：统一状态输出字段使 Dashboard 或告警系统能区分"启动中"和"可就绪"。
- **零副作用保障**：依赖等待路径严格约束为只读探针，排除冷启动时无意触发的 POST sync、写库、消息推送。

---

## 3. 目标与非目标

### 3.1 必须目标（Must-Have）

- [ ] 定义并暴露真实 readiness 统一状态模型：`starting` / `ready` / `degraded` / `failed`。
- [ ] `systemd active`、PID 存活或端口监听均不能单独作为 ready 证据。
- [ ] 对四项受治理服务分别定义只读 probe、成功/降级条件及 `platform_connected` 语义。
- [ ] 使用现有 user-systemd unit 和既有启动入口实现无副作用的依赖等待，不新增平行 wrapper、无限循环、自动级联重启、POST sync、写库、交易、飞书消息或其他外部副作用。
- [ ] 每项 probe 必须是 GET/TCP/status-only，零 POST、零 Mongo 写、零同步、零飞书消息、零交易。
- [ ] 单次冷启动验收记录必须包含：unit started → local ready → Gateway 首次连接证据 → 总等待时间 → 次数 → 最后错误 → 零副作用证据。

### 3.2 非目标（Out of Scope）

- [ ] 不修改系统级 systemd 配置（`/etc/systemd/`）、Windows/WSL 全局启动配置（`/etc/wsl.conf`、`/mnt/c/` 启动脚本）、Hermes profile config 或 cron。
- [ ] 不修改 Hermes core 代码（gateway status 语义、unit definition 过时、platform connection 协议）。
- [ ] 不修改 Unified Data（`03_data`）、策略（`strategies/`）、风控（`risk/`）、组合（`portfolio/`）、交易执行（`execution/`）、DSA 分析/报告业务逻辑（`daily_stock_analysis/`）或 TA-CN 数据业务路由与 scheduler sync 逻辑。
- [ ] 不修改 TA-CN `start_all.sh` 的默认路径（其 POST `/api/sync/stock_basics/run` 是冷启动时必须避开的生产副作用，由启动入口切换为无副作用模式来处理）。
- [ ] 不新增平行 wrapper 脚本、无限制等待循环、自动级联重启或外部 sidecar。
- [ ] 不清理、覆盖、暂存、提交或纳入当前工作树已有的无关变更（`docs/operations/restart-tradingagents-cn.md` 删除状态、`scripts/t4_preflight/` 和 `tests/scripts/t4_preflight/` 下的 smoke 文件）。
- [ ] 不改统一数据模型、MongoDB schema、TA-CN 业务代码、Hermes gateway 插件或 provider 配置。

---

## 4. 整体设计

### 4.1 核心设计哲学

**真实就绪 > 进程活跃**：服务的可服务性（readiness）由应用层语义决定，而非操作系统进程状态或端口监听。四项服务的 readiness 定义各不相同，但共享统一状态模型对外暴露。

**零副作用探针**：所有 readiness probe 必须是只读操作。冷启动依赖等待路径不允许触发任何业务逻辑、数据写入、外部消息或状态变更。

**最小侵入**：优先复用服务已有的 health endpoint（如 TA-CN 的 `/api/readyz`、DSA 的 `/health`），仅在现有端点无法表达 readiness 时才考虑在项目内新增只读 status/probe helper。

**渐进增强**：本 RFC 只定义状态模型和探针语义，Design 阶段决定实现载体（systemd `ExecStartPre`/`ExecStartPost`、shell wrapper、Python helper、HealthCheck 脚本等），Implement 阶段落地。

### 4.2 状态模型

```
                    +-----------+
                    |  starting |
                    +-----+-----+
                          |
                    probe 判定
                   /    |    \
                  v     v     v
            +-------+ +-------+ +-------+
            | ready | |degraded| |failed |
            +-------+ +-------+ +-------+
                |         |
                +---->----+  (degraded 可恢复为 ready 或转为 failed)
                |         |
                +----<----+  (ready 进入 degraded 当 probe 降级条件触发)
```

| 状态 | 定义 | 转换规则 |
|---|---|---|
| `starting` | 服务进程已启动，正在完成初始化或依赖就绪检查。systemd active 但真实可用性尚未确认。 | 进入此状态的时机：systemd Type=simple 标记 active 之后，首次 probe 成功之前。超时 → `failed`。 |
| `ready` | 服务已完全就绪，可正常处理请求。所有 probe 条件均满足。 | 由 `starting` 转换而来（首次 probe 全 PASS）。可转换到 `degraded`（部分 probe 降级）或 `failed`（全部失败）。 |
| `degraded` | 服务运行中，但部分功能不可用或性能下降（如外部 API 不可达、依赖服务离线）。核心请求可处理，非核心功能受限。 | 由 `ready` 或 `starting` 转换而来。可恢复为 `ready`，也可转为 `failed`。 |
| `failed` | 服务无法对外提供服务。probe 持续失败超过超时阈值。 | 最终状态。需 systemd restart 或人工介入恢复。 |

### 4.3 受治理服务与边界

#### 4.3.1 DSA（`daily-stock-analysis.service`）

- **已有端点**：`/health`（返回 `status: "ok"` + timestamp）。
- **当前局限**：`/health` 返回的是简单静态响应，不反映应用内部初始化状态（如数据加载、子模块就绪）。
- **readiness 判定**：必须证明以下条件全部满足：
  1. HTTP 200 on `/health`（或 `/api/health`）。
  2. 应用进程已完成 lifespan 初始化（当前 DSA 的 FastAPI lifespan 不含阻塞操作，仅 `_check_frontend_assets_consistency` 是文件系统检查）。
- **降级条件**：若 `/health` 返回非 200 或超时。
- **platform_connected**：DSA 不直接连接外部消息平台，不适用。

#### 4.3.2 TA-CN（`tradingagents-cn.service`）

- **已有端点**：`/api/readyz`（返回 `{"ready": true}`）、`/api/health`（返回服务状态 + 版本）、`/health`。
- **当前局限**：`start_all.sh` 默认路径会执行 POST `/api/sync/stock_basics/run`（端到端 smoke），这是冷启动时必须避开的副作用。
- **readiness 判定**：必须证明以下条件全部满足：
  1. HTTP 200 on `/api/readyz`（优先使用该端点，语义即为 readiness probe）。
  2. HTTP 200 on `/api/health` 作为辅助验证。
  3. 端口 `:8000` 已绑定（`ss -tlnp`）。
  4. 进程 PID 存活。
- **降级条件**：`/api/readyz` 返回非 200 但 `/api/health` 返回 200（应用运行但未就绪）；或 `/api/health` 返回 `{"success": false}`。
- **platform_connected**：TA-CN 是 Web API 服务，不直接连接外部消息平台，不适用。
- **冷启动入口**：必须使用 `--no-smoke` 或等效机制跳过默认的 smoke POST。

#### 4.3.3 Hermes Gateway yquant

- **已有检查手段**：`systemctl --user is-active hermes-gateway-yquant.service`（只证明进程 active，不证明 gateway 可用）；`gateway status`（只证明进程运行，不证明平台连接）。
- **readiness 判定**：必须证明以下条件全部满足：
  1. systemd unit 状态为 active。
  2. gateway 进程 PID 存活（`ps -p` 或 `systemctl --user show` PID）。
  3. 本次启动后的 journal 中出现 `platform_connected` 证据（每条 platform 的 connected log 行）。
- **降级条件**：进程 active 但 `platform_connected` 证据缺失（标记为 `platform_connected=unknown`）。
- **`platform_connected` 语义**：
  - `confirmed_at_boot`：本次启动后的 journal 中明确存在 `connected` 日志行（表示该 gateway 实例的 platform 连接已确认）。
  - `unknown`：journal 中无本次启动的 `connected` 证据且 probe 超时。
  - 冷启动验收记录必须在首次 probe 通过后记录 `platform_connected` 的具体值及其 journal 来源。
- **不得顺带修改**：Gateway unit definition outdated 是独立审计项，不得在本任务刷新。

#### 4.3.4 Hermes Gateway yinglong

- **与 yquant 的区别**：`ExecStart` 中 `--profile yinglong`，`WorkingDirectory` 为 `~/.hermes/profiles/yinglong`。
- **其余判定规则、降级条件、`platform_connected` 语义与 Hermes Gateway yquant 完全一致**。

### 4.4 零副作用探针契约

所有 probe 必须遵守以下约束：

| 约束 | 说明 |
|---|---|
| HTTP Method | 仅允许 GET |
| 传输层 | 允许 TCP 端口检查（`ss -tlnp`） |
| 状态查询 | 允许 systemd/shell 只读状态查询（`systemctl --user is-active`、`ps`、`journalctl --since`） |
| 禁止行为 | POST/PUT/DELETE、MongoDB 写操作、数据同步、飞书/Telegram 消息推送、交易执行、文件修改、env 写入、cron 变更 |
| 超时 | 单次 probe 超时 ≤ 10 秒；总体依赖等待超时由 Design 定义 |
| 重试 | 允许固定间隔轮询，不得使用无限制回退或指数退避（避免冷启动时无限等待） |

---

## 5. 详细设计

### 5.1 冷启动业务流程

```text
[WSL 开机 / systemd --user restart]
         │
         ▼
[systemd 并行启动 4 个 Type=simple unit]
         │
         ▼  (unit active 但服务未就绪)
[进入 starting 状态]
         │
         ├── DSA:     等待 /health 200 + 初始化完成
         ├── TA-CN:   等待 /api/readyz 200 + 端口绑定（跳过 smoke）
         ├── Gateway yquant:  等待 active + platform_connected 证据
         └── Gateway yinglong: 等待 active + platform_connected 证据
         │
         ▼  (超时时间到 或 所有 probe PASS)
[就绪确认]
         │
         ├── 全部 PASS → ready
         ├── 部分 PASS → degraded（记录降级细节）
         └── 全部 FAIL → failed（记录错误）
         │
         ▼
[记录验收结果 → 退出 / 通知]
```

### 5.2 状态输出最低字段

每项服务的 readiness 状态输出（无论以文件、stdout 或 journal 形式）必须包含以下字段：

| 字段 | 类型 | 说明 | 约束 |
|---|---|---|---|
| `service` | string | 服务标识 | DSA / TA-CN / gw-yquant / gw-yinglong |
| `status` | string | 当前 readiness 状态 | starting / ready / degraded / failed |
| `probe` | string | 最后一次 probe 目标 | URL 或检查名 |
| `probe_http_status` | int \| null | HTTP probe 的状态码 | null 表示非 HTTP probe |
| `probe_error` | string \| null | 最后一次 probe 的错误消息 | null 表示无错误 |
| `probe_count` | int | 从 starting 到当前状态的总 probe 次数 | ≥ 1 |
| `elapsed_seconds` | float | 从 unit active 到本次状态的总耗时 | |
| `platform_connected` | string | Gateway 连接证据状态（仅 Gateway 适用） | confirmed_at_boot / unknown / null |
| `side_effect_free` | boolean | 标识是否零副作用路径 | 必须为 true |

### 5.3 超时与错误语义

| 场景 | 行为 |
|---|---|
| 单次 probe 超时（> 10s） | 记录 `probe_error=timeout`，`status` 不变仍为 `starting`，继续下次轮询 |
| 连续 N 次 probe 失败 | 标记为 `failed`，记录 `probe_error`，停止等待（Design 定义 N 值） |
| 总等待超时（Design 定义） | 标记为 `failed`，记录 `elapsed_seconds`，输出最终状态 |
| probe 返回非 200 但有辅助证明服务可用（如端口存活） | 标记为 `degraded`，记录降级原因 |
| `platform_connected` 首次确认 | 记录确认证据的 journal 时间戳，`platform_connected=confirmed_at_boot` |

### 5.4 冷启动验收记录格式

单次冷启动完成后必须输出一条结构化验收记录（stdout 或 file），包含以下字段：

```
cold-start-report:
  boot_id: <UUID 或 timestamp>
  services:
    - name: DSA
      unit_active_at: <timestamp>
      local_ready_at: <timestamp>
      status: ready
      probe_count: 3
      elapsed: 42.5
    - name: TA-CN
      unit_active_at: <timestamp>
      local_ready_at: <timestamp>
      status: ready
      probe_count: 5
      elapsed: 51.2
    - name: gw-yquant
      unit_active_at: <timestamp>
      local_ready_at: <timestamp>
      platform_connected: confirmed_at_boot
      platform_evidence: "2026-07-26T08:15:23.456Z gateways/worker.py telethon session connected"
      probe_count: 8
      elapsed: 65.0
    - name: gw-yinglong
      unit_active_at: <timestamp>
      local_ready_at: <timestamp>
      platform_connected: unknown
      probe_count: 10
      elapsed: 70.0
      error: "no platform_connected evidence found in 70s"
  total_wait_seconds: 70.0
  side_effect_free: true
```

---

## 6. A+B allowlist 候选

本 RFC 确定以下允许修改/新增的文件候选范围（精确到文件级）。所有候选进入 SPEC-10-010 的 allowlist 进一步细化。

### A 组：user systemd unit（4 个，只读引用）

1. `~/.config/systemd/user/daily-stock-analysis.service`
2. `~/.config/systemd/user/tradingagents-cn.service`
3. `~/.config/systemd/user/hermes-gateway-yquant.service`
4. `~/.config/systemd/user/hermes-gateway-yinglong.service`

**作用**：为现有 unit 添加只读 probe 相关配置（如 `ExecStartPost` 调用 probe 脚本），不修改 `ExecStart`、`Type` 或其他运行语义。

### B 组：TA-CN 启动入口

- `skills/apps/TradingAgents-CN/start_all.sh`

**作用**：确保冷启动路径使用 `--no-smoke` 参数，跳过 POST `/api/sync/stock_basics/run`。不得修改 `start_all.sh` 的默认行为（完整 smoke 保留供人工使用）。

### C 组：DSA 代码（仅当现有 `/health` 无法表达 readiness 时）

- `skills/research/daily_stock_analysis/api/app.py`

**作用**：如果调研发现现有 `/health` 端点的静态返回无法区分"应用已初始化"和"应用正在启动"，可在此文件扩展现有 health check handler，添加初始化完成标志位的检查。不得修改任何业务路由或分析流程。

### D 组：项目内只读 status/probe helper

- `scripts/` 或 `skills/` 下一文件

**作用**：仅当现有启动入口（systemd unit、start_all.sh）无法满足探针需求时，新增一个项目内的只读 Python 脚本。该脚本必须是零副作用（只读 GET/TCP/file check），不得引入第三方依赖，不得持久化状态。

**禁止候选**：以下模块在本 RFC 中明确排除，不得出现在 allowlist 中：

- `docs/operations/`（已有删除状态的 `restart-tradingagents-cn.md` 不得纳入）
- `skills/data/unified_data/`（Unified Data 层）
- `skills/strategies/`、`skills/risk/`、`skills/portfolio/`、`skills/reports/`
- `skills/apps/TradingAgents-CN/app/services/`（数据业务路由）
- `skills/apps/TradingAgents-CN/app/routers/`（API 路由）
- `skills/research/daily_stock_analysis/src/`（DSA 分析业务）
- Hermes core（`/home/pascal/workspace/hermes-agent/`）
- Hermes profile config（`~/.hermes/profiles/yquant/`、`~/.hermes/profiles/yinglong/`）
- 当前工作树的无关变更文件

---

## 7. 风险与应对

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| TA-CN `start_all.sh` 默认路径含 POST sync，冷启动时误触发 | 高 | 高 — 生产数据写入副作用 | 冷启动入口强制使用 `--no-smoke` 参数；Design 阶段验证是否需新增独立冷启动入口脚本 | 人工审核每次冷启动记录验收报告的 `side_effect_free` 字段 |
| Gateway `platform_connected` 证据在 journal 中不可靠（日志级别、轮转、跨 boot） | 中 | 中 — `platform_connected` 回退为 unknown | 使用 `journalctl --since` + 精确 log 匹配；若 journal 证据不可用则标记 unknown 而非假阳性 confirmed | 由 Pascal 手动确认首次连接 |
| DSA `/health` 端点不足以表达真实 readiness | 中 | 低 — 状态退化而非不可用 | 现端点至少证明 `status: "ok"`，降级为 degraded 而非 blocked；允许 C 组扩展 | 保持当前 /health 定义不变，degraded 状态下人工确认 |
| WSL 环境差异导致 probe 路径不一致 | 低 | 中 — 跨环境不可复现 | 所有 probe 设计为路径无关（通过相对路径或 systemd WorkingDirectory）；不依赖 WSL 特有命令 | 在 Design 中注明 WSL 特定假设及其检测保护 |
| systemd 运行配置修改引入生产副作用 | 低 | 高 — 意外的自动重启或配置漂移 | Design 阶段逐项固化最小变更、回滚、验证和禁止自动重启策略 | 先在 staging/systemd --user test 环境验证 |

---

## 8. 备选方案

### 8.1 方案 A（推荐）：只读 probe + 现有 systemd unit

- **思路**：不改变 systemd `Type=simple`，通过在 `ExecStartPost` 中调用项目内只读 probe 脚本来确认 readiness。
- **优点**：变更面最小、回滚简单、不需要修改服务代码、不依赖第三方库。
- **缺点**：`ExecStartPost` 的执行结果不影响 systemd 的 active 状态（仍需要外部观察者来消费 readiness 输出）。
- **选择原因**：与"最小侵入"哲学一致，完全在现有基础设施内完成。

### 8.2 方案 B：Type=notify 改造

- **思路**：将服务改为 `Type=notify`，在服务进程中实现 sd_notify 协议。
- **优点**：systemd 原生支持 readiness 通知。
- **缺点**：需要在四个服务的 Python 进程中都嵌入 sd_notify 调用（DSA、TA-CN 后端、两个 gateway），侵入大；Python sd_notify 在 WSL 上的行为不可预期；Hermes gateway 是第三方代码不可修改。
- **放弃原因**：侵入过大，且 WSL user-systemd 对 sd_notify 的支持有限。

### 8.3 方案 C：外部 sidecar 健康检查器

- **思路**：新增一个独立服务，轮询所有受治理服务的端口和 HTTP 端点，统一输出 readiness 仪表盘。
- **优点**：解耦检查逻辑和业务服务。
- **缺点**：新增平行 wrapper 服务违背"不新增平行 wrapper"约束；需要独立部署和维护；冷启动时的鸡生蛋问题（检查器本身何时就绪）。
- **放弃原因**：不必要的复杂性。

---

## 9. 验收标准

### 9.1 功能验收

1. 四项受治理服务各有明确的只读 probe 定义，状态输出包含最低字段集。
2. 冷启动验收记录输出格式符合 §5.4 定义，含所有要求字段。
3. `platform_connected` 对于 Gateway 服务可区分 `confirmed_at_boot` 和 `unknown`。
4. TA-CN 冷启动入口跳过 POST smoke（使用 `--no-smoke` 或等效机制）。
5. 探针均无 POST/PUT/DELETE、无 Mongo 写、无同步、无飞书消息、无交易。

### 9.2 非功能验收

1. 单次 probe 超时 ≤ 10 秒。
2. 验收记录的 `side_effect_free` 字段（每次冷启动执行）值为 `true`。
3. 四次服务的总等待时间在验收记录中可查询，单位秒。
4. Design 阶段输出文件级变更清单时，无 allowlist 以外的文件被标记为待修改。
5. 仅新建 `docs/rfc/10_infra/RFC-10-010-*.md` 和 `docs/spec/10_infra/SPEC-10-010-*.md` 两文件，不修改任何现有文件。

### 9.3 边界条件

| 条件 | 期望行为 |
|---|---|
| 所有服务正常启动 | 所有状态为 ready，验收记录完整 |
| 某个服务启动失败（如 internal server error） | 该服务状态为 failed，其余服务不受影响 |
| Gateway journal 中无本次 boot 的 connected 证据 | `platform_connected=unknown`，服务自己状态为 degraded |
| 总等待时间超时 | 标记为 failed，输出已确认的就绪部分 |
| 启动后手动重启部分服务 | 不影响本次 cold-start 验收记录（只记录首次冷启动） |

---

## 10. 落地计划

### 10.1 阶段划分

| 阶段 | 内容 | 预期产物 |
|---|---|---|
| T1 — RFC/SPEC（本卡） | 定义状态模型、探针语义、零副作用约束、A+B allowlist | RFC-10-010 + SPEC-10-010 |
| T2 — Design | 细化实现方案：probe 脚本设计、systemd unit 最小变更、启动入口切换路径、验收记录生成方式 | DESIGN-10-010 |
| T3 — Implement | 按 Design 实现所有文件变更 | implement 完成 + unit test |
| T4 — Verify | 全流程冷启动 smoke 测试，验证零副作用和 readiness 状态输出 | verify report |
| T5 — Review | 独立审查变更文件、side-effect 轨迹、验收记录 | review sign-off |

### 10.2 本卡任务清单（已由 Pascal 授权推进）

- [x] 上下文调研：四服务的 systemd unit 定义、health endpoint、启动流程
- [x] 定义统一状态模型、转换规则、最低输出字段
- [x] 定义每项服务的 probe 目标和成功/降级条件
- [x] 定义 `platform_connected` 语义
- [x] 定义零副作用探针契约
- [ ] （由本卡交付）RFC + SPEC 两文件，相互引用，职责边界清晰
- [ ] Design 阶段票（由下一 kanban card 接手）

---

## 11. 开放问题

1. **TA-CN 冷启动入口**：现有 `start_all.sh` 支持 `--no-smoke` 参数。Design 阶段需确认是否需要新增独立脚本（如 `start_no_smoke.sh`）而非依赖参数。倾向：复用 `start_all.sh --no-smoke` 以减少文件变更。
2. **DSA health endpoint 扩展必要性**：当前 `/health` 返回简单静态响应。Design 阶段需调研 DSA 的 FastAPI lifespan 事件中是否存在足够长的阻塞操作（如首次数据加载），决定是否需要扩展。
3. **Gateway journal 连接证据的精确匹配模式**：`journalctl --since` + `grep "connected"` 可能产生误配。Design 阶段需确定 `_UNIT=hermes-gateway-yquant.service` 过滤和精确字符串匹配规则。
4. **验收记录载体**：写入标准日志文件（如 `logs/cold-start-report.json`）、发出 journal 结构化日志、或写入 MongoDB 集合？设计阶段权衡。

---

## 12. 参考资料

- [systemd.service(5) — Type=simple vs Type=notify](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)
- [systemd.service(5) — ExecStartPost=](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#ExecStartPost=)
- [Kubernetes Container Probes (readinessProbe / livenessProbe concept)](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#container-probes)
- WSL user-systemd 限制：当前 unit After=network-online.target 在 WSL 下不等外部可达性
- TA-CN `start_all.sh` 退出码表：0=完全成功 / 11=pre-flight 失败 / 31=端口未 listen / 41=health 失败 / 61=smoke 失败
