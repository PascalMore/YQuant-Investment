# RFC-06-001: Strategy Lab — AI 操作 QuantDinger 的最小 Skill

## 元数据（Metadata）

| 项 | 值 |
|---|---|
| 状态 | 已采纳 |
| 作者 | YQuant-Codex-Principal |
| 创建日期 | 2026-10-29 |
| 最后更新 | 2026-10-31 |
| 版本 | V1.5（Agent Token 接入增量：费用条款修订、Agent 异步 job/result 与持久化读回契约；待独立 Gate，非整体验收） |
| 所属模块 | strategy |
| 依赖RFC | 无 |
| 替代RFC | 无 |
| AI适配 | Hermes Kanban（yquant-ai-coding-pipeline Full Flow） |
| 标签 | #策略 #AI实装 #接口 #安全 |

## 1. 执行摘要（Executive Summary）

在 `skills/strategies/strategy-lab/` 下新增一个操作型 Skill，让 AI 按「定义 → 执行 → 交付」三步使用 QuantDinger 现有能力完成交易策略研发与研究分析：优先复用模板/官方生成器/Strategy API V2/原生回测与 Strategy Evolution，不建新平台、引擎、SDK 或任务系统。成功标准：一个真实交易样例（保存私有源码 → 基准原生回测 → 自动触发一次有界原生进化 → 候选/基准判定 → 最终回测与源码在 QuantDinger UI 可查）与一个真实研究样例（平台真实数据 → Python 分析 → reports 输出 → 同脚本可重跑）均通过独立验证。

## 2. 背景与动机（Background & Motivation）

- 现状痛点：QuantDinger 已具备 Strategy API V2、原生回测与 Strategy Evolution 能力，但缺少 AI 操作约定；每次策略/研究任务都要人工重新探索接口、口径与边界。
- 业务价值：把 Pascal 已确认的 README 方案固化为可执行契约，后续策略研发从「每次手工摸索」变为「按 Skill 定义→执行→交付」。
- 触发原因：需求驱动。Pascal 已确认 `skills/strategies/strategy-lab/README.md` 方案并要求走 AI Coding Pipeline（见 `data/tasks/active/2026-10-29-strategy-lab/intake.md`）。

## 3. 目标与非目标（Goals & Non-Goals）

### 3.1 必须目标（Must-Have）

- [ ] 可加载的 SKILL.md 与最小可执行脚本；父 `skills/strategies/SKILL.md` 入口能路由到 strategy-lab。
- [ ] 交易样例闭环：私有源码保存 → 基准原生回测 → 自动判定进化适用性 → 一次有界原生进化（parameter-space → estimate → run → jobs 终态）→ 先硬约束后同口径比较 → 最终原生回测，源码与回测结果在 UI 可查。
- [ ] V1.5 Agent 接入：按 §5.6 完成 Agent Token 身份核验、行情/编译/异步回测的最小真实接入；Agent 与 Human 双入口并存，语义按 §5.3/§5.6 契约，不混用认证。
- [ ] 研究样例闭环：真实平台数据 → 可重跑 Python 分析 → reports 输出；不伪造交易条目。
- [ ] 进化覆盖全部判定分支：跳过、无改进且基准合格、基准不合格但候选合格、均不合格、关键证据未知、任务失败/超预算停止。
- [ ] 安全边界：研究阶段不发单、不建 Live/部署、不写生产 DB；实盘保持 G1 自动验收 + G2 Pascal 单批准。

### 3.2 非目标（Out of Scope）

- [ ] 不做新策略研发平台、第二套回测引擎、优化器、任务引擎、数据平台、运行档案系统（version/runs/manifest/强制快照均不建）。
- [ ] 不为接入新建 SDK/MCP/统一运行时；只允许最薄 HTTP 调用脚本。
- [ ] 不做自动实盘部署、风控引擎、订单系统、定时调度平台。
- [ ] 不修改 QuantDinger 子模块源码（只读核实）。
- [ ] 不把网格示例的全部金融建模功能扩成首版引擎；网格例子仅用于约束语义验证。

## 4. 整体设计（Overall Design）

### 4.1 核心设计哲学

复用优先：QuantDinger 已有的能力直接调用，只补「完成任务必需的薄脚本」；AI 的价值在定义与判定，不在重建平台。

### 4.2 架构总览

```text
YQuant（Orchestrator，业务三步）
  定义：strategy-lab/strategies/<id>/spec.md + config.json
  执行：
    薄调用层（最小 HTTP 脚本，Design 阶段固化 allowlist）
      ├─ Agent Gateway /api/agent/v1（token，scope R/W/B）
      └─ Human Web API（JWT login_required）
          ├─ /api/strategy-evolution/*（仅此入口，Agent 网关无对应路由）
          └─ /api/backtest/*、/api/strategies/script-sources/*、/api/strategies/verify
    QuantDinger 子模块（只读复用，不修改）
  交付：<id>/reports/ + 平台 ID 读回验证
```

### 4.3 模块分工

- strategy-lab Skill：需求定义（spec.md/config.json）、执行编排、结果判定与交付；不含常驻服务。
- QuantDinger 平台：源码库（qd_script_sources，私有）、回测（V2 执行模型、持久化 run）、进化（qd_agent_jobs, kind=strategy_evolution）、行情/研究数据接口。事实以平台为准，本地不复制账本。
- YQuant 工程流程：新增/实质修改 Python 经 `yquantdeveloper` 实现、`yquanttester` 独立验证；普通参数调整与官方生成器调用不重复派卡。

## 5. 详细设计（Detailed Design）

### 5.1 业务流程（Flow）

触发条件：用户提出策略研发或研究需求，YQuant 在 `strategy-lab/strategies/<strategy_id>/` 生成 spec.md（含目标、数据/市场身份、规则、参数、硬约束、比较目标、计算预算）与 config.json（仅可调参数数值）。

核心处理逻辑（交易类）：
1. 就绪：编译/校验源码（compile/verify 返回 manifest 与 backtestRangePolicy）→ 保存私有 source → 读回验证（detail 按 id 读回）。Human create 的 private/draft 只是服务默认值，客户端必须显式发送 visibility=private、status=draft，并核对读回值及源码一致，不能依赖平台强制覆盖。
2. 基准：提交原生回测 job（persist）→ 轮询终态 → 按 runId 读回结果，取全段口径（totalReturn/maxDrawdown/annualizedReturn 等）。入口按 §5.3 矩阵：Agent 模式走 `POST /api/agent/v1/backtest/run` + `GET /jobs/{jobId}`（判定以 job result 为准）；需 UI 历史/sourceId 闭环时走 Human 显式兼容路径并标注认证切换。
3. 自动进化判定：存在已声明且实际生效的可调参数（parameter-space scope=declared/riskExecution）、有选优目标、预算允许、用户未禁止 → 直接触发一次有界进化；否则走跳过分支并说明原因。
4. 进化执行：parameter-space 取真实空间 → 按 spec/config 限定范围与目标 → estimate 核对预算（超了先收缩，不擅自加预算）→ run 一次 → 轮询 jobs 终态；失败/取消/超预算即停止并带诊断报告。
5. 判定：候选证据（进化 result）先核对适用证据，涉及全段口径的硬约束只用原生全段回测判定（summary.maxDrawdown 仅为 validation/OOS 折回撤绝对值平均，不含 blind、不是全段 MDD，不据此先淘汰全段候选）；合格项按预定义目标同口径比较。原生搜索的 blind 独立证据另列；后续全段复检已包含 blind，最终选参不得再称有完全未触碰的独立留出集。
6. 交付：推荐候选（或保留基准/无合格候选/证据不足）→ 最终回测 persist → runId 与 source 在 UI 读回核实 → 本地报告。

正常分支：上述 1-6 全部成功，产出推荐结论与平台 ID。
异常降级分支：401/403（凭据缺失/失效）、源码编译失败、数据或范围超限（BacktestRangeLimitError）、job failed/cancelled/陈旧（workerInterrupted）、超预算 —— 均如实停止并报告原因与诊断，不静默降级为 mock，不自动重启进化循环。

进化判定分支语义（冻结，与 engine 实现字段对应）：
- 跳过：parameter-space scope=none、参数固定、研究类不适配、成熟策略日常执行。
- 无改进且基准合格：候选同口径比较不优于合格基准 → 保留基准。
- 基准不合格但候选合格：不因候选绝对收益较低而拒绝合格方案，可选候选。
- 均不合格：报告无合格候选。
- 关键证据未知：全段口径/资金费等未建模项无法核实 → 标证据不足（平台 executionAssumptions.fundingMode=not_modeled 必须如实披露）。
- 失败或超预算：停止，报告 progress.failure 诊断与实际消耗。

研究类：定义问题 → 平台真实数据（Agent /klines 分页等）→ Python 分析 → reports/ 输出 → 同一脚本可再次执行；QuantDinger 数据缺口如实列明，优先复用项目已有数据能力，不为单项研究建 Provider 框架。

### 5.2 数据模型（Data Model）

本地文件约定（无 version/runs/manifest）：

| 路径 | 内容 | 约束 |
|---|---|---|
| `strategy-lab/strategies/<id>/README.md` | 简要说明、执行方式、平台关联 | 简短 |
| `strategy-lab/strategies/<id>/spec.md` | 需求、参数语义、硬约束、预算、验收 | 按 templates/strategy-spec.md |
| `strategy-lab/strategies/<id>/config.json` | 可调参数实际数值 | 只存数值，语义在 spec |
| `strategy-lab/strategies/<id>/strategy.py` 或 `research.py` | 交易/研究主脚本 | 每目录一个主脚本 |
| `strategy-lab/strategies/<id>/reports/` | 运行结果、报告、支撑材料 | 直接落此目录 |

平台侧实体（引用不复制）：qd_script_sources（私有源码）、回测 run 仓库（runId/结果/数据溯源 dataProvenance/执行假设 executionAssumptions）、qd_agent_jobs（kind=strategy_evolution 与 Agent 模式 kind=backtest：jobId/status/progress/result/error/billing/agent_token_id/idempotency_key）。事实以平台为准，本地不复制账本。

### 5.3 接口契约（API Contract）

双入口矩阵（已对当前源码核实）：

| 能力 | 首选入口 | 备用/说明 |
|---|---|---|
| 源码保存/读取 | Agent `POST/GET /api/agent/v1/strategy-sources`（W/R，该入口强制 private+draft） | Human `/api/strategies/script-sources/create|detail`（JWT；服务仅默认 private/draft，客户端显式发送并精确读回）；首版按 SPEC F-001 / Design §3.3 固定 Human 同 owner 闭环，不实现入口混用 |
| 编译/校验 | Human `/api/strategies/script-sources/compile`（返回 manifest+backtestRangePolicy）、`/api/strategies/verify` | Agent `/api/agent/v1/strategy-sources/compile`（仅 manifest） |
| 基准/最终回测 | Agent `POST /api/agent/v1/backtest/run`（SCOPE_B 异步 202+jobId；字段白名单 `_BACKTEST_FIELDS` 不含 sourceId/persist，persist 恒 true）→ `GET /api/agent/v1/jobs/{jobId}` 轮询终态 → 从 job `result` 取 `runId` 与指标 | Human `POST /api/backtest/jobs`（带 sourceId 关联）→ `GET /api/backtest/jobs/{id}` → `GET /api/backtest/get?runId=`、`GET /api/backtest/history?sourceId=`；Agent 无 run/sourceId 读回路由（backtests.py 仅 POST），需要 UI 历史/sourceId 闭环时才用 Human 并显式标注认证切换 |
| 原生进化 | 仅 Human `/api/strategy-evolution/*`（JWT）：`GET parameter-space?sourceId=`、`POST estimate`、`POST run`(202+jobId)、`GET jobs/{jobId}`、`GET jobs?sourceId=`、`POST jobs/{jobId}/cancel` | Agent 网关当前无对应路由（agent_v1 目录核实）；不得为其新建 SDK/MCP，缺 JWT 时如实阻塞 |
| 行情/研究数据 | Agent `GET /api/agent/v1/klines|price|markets`（R，klines 单次 ≤2000 根，before_time 回翻分页） | Human 同类接口；factor-research 可选 |

关键请求/响应语义：Human 信封 `{code:1,msg,data}` 成功、`{code:0,msg,data}` 失败（400/404/500）；Agent 信封 `{code:0,message,data}` 成功、`{code:<httpcode>,message,details,retriable,data:null}` 失败（agent_v1 `_helpers.py`），两套信封不得混读。进化 run 返回 202+jobId，终态 succeeded/failed/cancelled，failed 时 progress.failure 含 messageKey/dominantReason/reasonCounts/actualBacktestRuns；estimate 返回 backtestRuns/relativeUnits/resourceTier/trials/minimumRecommendedTrials/sampleSufficient/walkForwardMode=singlePass。parameterSpace 行必须落在声明范围内（parameterNotDeclared/parameterRangeOutsideDeclaration/parameterStepInvalid 拒绝）；config 合法域：method∈{tpe,grid,random}，tpe trials≥24，folds 4-10，blindRatio 0-0.3。回测范围受 backtestRangePolicy（按市场/周期）约束。

Agent 异步回测（`POST /api/agent/v1/backtest/run`）请求仅接受白名单字段 `code/startDate/endDate/initialCapital/commission/slippage/leverageEnabled/leverage/params/instrumentRulesSnapshotId`（`_BACKTEST_FIELDS`，agent_v1/backtests.py:28-32）；未知字段 400，不接受 sourceId/persist/strategyId（persist 恒为服务端默认 true）。SCOPE_B 的 W/B 非GET调用（含 compile）要求 `Idempotency-Key` 头（≤120 字符）：缺失 400、同 key 不同请求体 409、同 key 请求进行中 409、同 key 同请求重放返回已存响应并带 `Idempotent-Replayed: true` 头（agent_auth.py:661-712）。客户端在收到 202 后以 `GET /api/agent/v1/jobs/{jobId}`（SCOPE_R）轮询至终态 `succeeded/failed/cancelled`；提交状态未知（超时/断连）时必须先用同一 Idempotency-Key 重放原请求或读回 job，不得盲目重发新提交。

进化实际 wire 字段为 `summary.selectionObjective="oosCompoundedReturn"` 与 `selection.objective="oosCompoundedReturn"`；原生 trial.score 按 validation 折收益复利排序。`summary.maxDrawdown` 只取 validation 折回撤绝对值平均（无 validation 时源码兜底100），不含 blind；`summary.blindReturn/blindPassed` 单列，不是全段 MDD。全段硬约束只认读回 run 的 `data.result.maxDrawdown`，单次回放切片不能称逐折重新训练。源码依据为 `statistics.py:27-55`、`engine.py:219-265`，详见 SPEC §4 / Design §2、§3.4。

认证：JWT 7 天有效且单客户端（token_version），仅从既有安全入口获取，经环境变量注入脚本，日志与输出脱敏；agent token 仅当 Pascal 已签发时使用。任何写平台动作（建源码、run 进化、回测 job）必须读回精确目标验证。

Agent 模式费用条款（V1.5 修订，取代 V1.1 引入的 Human-only 提交前计费门禁）：本地实例按操作人 Pascal 2026-10-31 明确确认「本地部署的 quantdinger 付费已关闭」执行，Agent 模式不再要求提交前费用证明——不要求 Human JWT 预检 `GET /api/settings/public-config`、不要求 Agent 计费接口、不要求管理员登录或费用证明文件；旧 Human-only 前检条款仅作为 V1.4 历史事实保留，不影响历史验收证据。该确认是操作人部署前提声明，不是 API 实测结论，也不泛化到未知远端或可能收费的其他实例；预算上限与无付费授权边界仍然全部保留。运行时判据：Agent 回测提交时服务端在创建 job 的事务内调用 `consume_in_transaction`（agent_jobs.py:120-135），billing 关闭或 feature cost=0 时返回 `status:"free"`、`charged:0` 且不扣积分（billing_service.py:662-701）；提交 202 响应与 job 读回中的 `billing` 对象（`enabled/feature/cost/charged/remaining/status`）是该次提交的实际计费收据。客户端契约：提交后如实记录 `billing.status/charged`；若实际响应出现 `status:"charged"`、`charged>0`、HTTP402 或任何与「已关闭计费」前提矛盾的信号，如实报告并停止后续提交，不自动付费、不自动重试、不自动请求退款，也不就同一问题再次要求独立免费证明。

### 5.4 预算与停止约束

单任务预算写入 spec.md，允许覆盖但不得提高首版安全上限：trials ≤ 64、全段复检参数组（含基准）≤ 5、外层持久化回测 job 总数 ≤ 8（V1.5 起按通道无关计数：Human `POST /api/backtest/jobs` 与 Agent `POST /api/agent/v1/backtest/run` 的持久化提交合并计入）、研究数据 API 调用 ≤ 50、墙钟 ≤ 30 分钟。上述上限可下调；folds 固定4（平台下限4与首版安全上限4的交集），不能降3或升5。若任务要求folds<4则停止，不依赖平台静默夹值。estimate 超预算仅降 trials/缩声明内空间，最多收缩2次重估；不能降folds、加预算或放宽硬约束。

内部回放预算与外层 jobs 分栏：`estimate.backtestRuns/relativeUnits` 是估计，`result.summary.actualBacktestRuns`（失败时 `progress.failure.actualBacktestRuns`）是内部实际计数；内部 analysis_only/persist=false 回放不计外层持久化 job。内部上限按 Design §3.5 显式声明，首版样例内部回放/relativeUnits上限均8；外层最多6（基准1+去重候选最多4+最终1），仍受总上限8。样例4个grid点、costMultipliers=[1,2]、blindRatio=0.15、universeSize=1，估算 `4+(2-1)+1=6`、relativeUnits=6，不乘folds；actual 未返回不能写实耗6。estimate.isUpperBound=false，客户端截止/取消不保证远端强杀。到预算或失败即停止，不无限轮转或后台自进化。

### 5.5 方案 C：spy-ma-smoke 窗口修订（2026-10-30）

Pascal 已批准仅将该交易接入样例窗口改为 2017-06-01..2025-12-31；旧窗口 2023-01-01..2025-12-31 已 superseded，仅作历史。warmup260、folds4、源码/算法、参数与搜索空间、成本和硬约束均不变。真实行情预检的 2159 条（日末）/2158 条（午夜）经原生拆分均为有效4折；这不是进化 evaluator 快照或真实闭环通过证明，执行要求见 SPEC V1.4 §8.1、Design V1.4 §5.1。

通用每次执行恰好一次进化的规则不变。此次仅对修订窗口追加一次性、最多1个新进化 job 的授权；旧 failed job 保留并计入历史，不重试、不清零。开始前若新窗口已有 job，只读回、不重复创建；失败/取消/超预算即停，不自动重试。每轮内部回放/relativeUnits≤8、外层持久化回测jobs≤8、参数组含基准≤5、墙钟1200s、零新增付费均不变，不形成普遍“两次进化”额度。

本次仅同步文档，沿用 T4 `t_baaaef0b` 与 T5 `t_6346409a`；独立方案 C Design Gate 完成前不执行业务，不重建任务图、不扩展 CLI 或平台。

### 5.6 V1.5 Agent Token 接入增量（2026-10-31）

Pascal 授权通过既有 `skills/.env` 精确环境键 `QUANT_DINGER_AI_AGENT_TOKEN_MYMQUANT` 接入原生 Agent Gateway，把正常业务操作从 browser_exec/Human JWT 依赖转为 Agent 优先的受限研究通道。本节是增量语义，不改变 V1.4 的业务目标、预算与历史证据。

- 身份与能力：whoami 已实测 HTTP200，实际身份 `MYM_QUANT_AI`，scopes=`B,N,R,T,W`，`paper_only=true`，market/instrument=`*`，限流 60 次/分钟；旧严格大小写探针 exit3 是名称不匹配，不是鉴权失败。N/T 能力本任务不使用、不扩权；paper_only 与 token 权限不证明免费（费用语义见 §5.3）。
- 通道定位：Agent 优先的受限研究通道（身份/行情/编译/异步回测），Human 显式兼容但不混用认证；缺失能力（网格 generate、Strategy Evolution、run/sourceId 读回）如实 unsupported，不静默改走 Human/Browser，不为其扩平台。
- Agent 回测 job/result 契约（源码核验 agent_jobs.py / backtest_jobs.py / agent_v1/jobs.py）：提交 `POST /api/agent/v1/backtest/run` 202 返回 `{job_id,status:"queued",kind:"backtest",created_at[,billing]}`（`_job_receipt`，agent_jobs.py:215-222）；job 行终态 `succeeded/failed/cancelled`，`GET /jobs/{jobId}` 返回 `job_id/user_id/agent_token_id/kind/status/request/result/error/progress/created_at/started_at/finished_at`（含 billing 时附加 `billing` 键）。成功 job 的 `result` 由 `{**result, "runId": run_id}` 组成（backtest_jobs.py:58-80）；指标为扁平顶层键（runtime.py:2057-2109），关键项 `totalReturn/maxDrawdown/maxDrawdownPeakEquity/maxDrawdownTroughEquity/maxDrawdownPeakTime/maxDrawdownTroughTime/winRate/sharpeRatio/annualizedReturn` 及 `annualizedReturnAvailable/annualizedReturnCapped`；服务端还会注入 `resultStatus/dataProvenance/executionAssumptions/benchmark*/excessReturn/benchmarkRelativeMetrics/diagnostics`（service.py:280-434）。失败 job `error` 为截断文本（≤6000 字符），`result` 仅在计费退费场景携带 `billing`（agent_jobs.py:449-454）；失败自动退费在终态切换的同一事务完成。`result` 内的回测曲线类数组在交付前经 `compact_backtest_result` 有界采样（closedTrades/executions ≤1500、equityCurve/benchmarkCurve ≤1200 等，storage.py:361-389），报告不得把采样数组当全量明细。
- Agent 持久化读回差异（与 Human 通道的关键不同）：`persist` 恒 true（服务端默认），run 落盘 `qd_strategy_backtest_runs` 且 `source_id` 取 `payload["__source_id"]`（backtest_jobs.py:58-80）；但 Agent 入口字段白名单不含 sourceId、不注入 `__source_id`，因此 Agent 模式持久化 run 的 `source_id` 为 NULL，不产生 Human 通道的 sourceId→run UI 历史关联。Agent 网关没有 run 读回或 history 路由（agent_v1/backtests.py 仅 `POST /backtest/run`；agent_v1/__init__.py 挂载清单无对应模块）。因此：Agent 模式的结果判定以 job `result` 为准；「UI 历史可查/sourceId 读回闭环」仅在 Human 显式兼容路径（JWT + `GET /api/backtest/get?runId=`、`GET /api/backtest/history?sourceId=`）可用，混合使用时必须显式标注认证切换，且不承诺 Agent 具备 Human 的全部关联/持久化能力。
- 兼容与安全保留：显式 token 保护、精确绑定/注入、权限与市场/标的预检（不白名单即 403）、幂等、预算、unsupported 前置解释、错误如实披露、48 项既有回归保留、真实最小 smoke 不缺证。本节为 RFC/SPEC 层契约；实现文件 allowlist 由 T2 Design 冻结。

## 6. AI 实装规范（AI Implementation Rules）

### 6.1 必须执行

- 每个平台写动作后读回验证（source detail / job / runId）。
- 全段硬约束只能用全段原生回测结果判定；进化分窗口径证据必须标注口径。
- 报告保留：数据来源、参数实际消费证据、成本假设、未建模项、平台 ID、复现命令。
- 真实验收与 fixture/可断言负分支测试分开陈述；mock 不得冒充接入验收。

### 6.2 先询问再执行

- 需要 agent token 签发、凭据新增、任何 Live/Demo 动作、调度变更 → 停下询问 Pascal。
- spec.md 之外的语义变更 → 回到本 RFC 修订。

### 6.3 绝对禁止

- 硬编码凭据、绕认证、读取输出 secrets。
- 修改 QuantDinger 子模块源码；自动覆盖运行配置或 Live；未经授权 commit/push。
- 把一次回放后切窗的 fold 结果冒称逐折重新训练；把平均分窗 drawdown 冒称全段最大回撤。

## 7. 风险与应对（Risks & Mitigations）

| 风险 | 概率 | 影响 | 应对方案 | 降级策略 |
|---|---|---|---|---|
| JWT 单客户端/7 天失效导致脚本 401 | 中 | 中 | 脚本把 401 报告为阻塞，不重试绕过 | 提示刷新既有会话凭据 |
| Agent 网关无进化路由 | 已确认 | 中 | 用 Human JWT 入口；无凭据则阻塞并披露 | UI 人工执行 + 结果读回 |
| Agent 模式无 sourceId/run 读回路由，UI 历史关联缺失 | 已确认 | 中 | 判定以 Agent job result 为准；需 UI 闭环时走 Human 显式兼容并标注认证切换 | 报告保留 jobId/runId 供人工 UI 查询 |
| 「关闭计费」前提与实际 billing 响应矛盾 | 低 | 高 | 按 §5.3 客户端契约如实记录 billing 并停止后续提交 | 报告矛盾证据，交 Pascal 裁定，不自动付费/重试/退款 |
| 进化统计口径误读（分窗 vs 全段） | 中 | 高 | SPEC 冻结判定语义：硬约束以全段回测为准 | 候选阶段仅作初筛并标注 |
| 回测数据范围超限 | 中 | 低 | compile 返回 backtestRangePolicy，先核对再提交 | 缩短窗口或换周期 |
| 资金费/强平未建模误判通过 | 中 | 高 | fundingMode=not_modeled 相关合约标证据不足，不判通过 | 仅现货/无资金费标的判合格 |
| 超预算/长任务 | 中 | 中 | estimate 预检 + 墙钟上限 + jobs 终态必查 | 收缩搜索或停止报告 |

## 8. 备选方案（Alternatives Considered）

- 自建策略研发平台/任务引擎：能力重复 QuantDinger 已有实现，维护成本高，不选用。
- 为进化新建 Agent 网关路由或 MCP：平台当前未提供，属子模块源码修改，违反最小接入，不选用。
- 全部走 UI 人工操作：不可自动化、不可重跑，仅作为无凭据时的降级说明，不作为方案。

## 9. 验收标准（Acceptance Criteria）

### 9.1 功能验收

- 三份契约文档（本 RFC、SPEC-06-001、DESIGN-06-001）独立非空且互引有效；与已确认 README 逐条一致；无未决核心语义留给 Developer。
- 原生能力结论（接口/权限/口径）均有当前源码依据（SPEC §4 契约表 + 源码路径）；Agent job/result 层级与持久化读回差异按 §5.6 与 SPEC §4 对应源码可断言。
- V1.5 Agent 接入：Agent Token 身份核验（whoami）、行情取数、原生编译、一次异步回测 job 到终态并从 result 判定指标，均为真实验证；billing 收据如实记录且无矛盾信号，或矛盾时已按 §5.3 契约停止并披露。
- 交易样例：真实私有源码与回测在 UI 可查（runId 读回）、自动进化达到终态并有结果判定、六种判定分支语义在文档可断言。
- 研究样例：真实数据、reports 落盘、同一脚本第二次执行成功。
- 负分支（无参数跳过、失败、超预算、401、幂等冲突 409、计费矛盾信号）以可断言方式验证，不伪造。

### 9.2 非功能验收

- 文件范围不越界（仅允许清单内路径）；path-scoped `git diff --check` 干净。
- 凭据零出现在文档、代码、日志与报告；未授权交易调用路径列明不可达。
- 真实验收不被 fixture 替代；auth/平台能力缺失时准确披露阻塞。
- 历史运行证据（V1.4 及之前）不被本轮修订追认或改写；页眉版本状态与实际签收事实分离陈述。

## 10. 落地计划（Implementation Plan）

### 10.1 阶段划分

Full Flow：T1 本 RFC/SPEC → T2 Design（文件 allowlist、薄调用入口、真实 API/auth 映射、验证样例）→ 主控 Design Gate → Implement → 独立 Verify → 独立 Review → Closeout。本卡仅文档阶段。

### 10.2 任务清单

- T2 Design（yquantprincipal）：冻结脚本文件 allowlist 与验证样例清单。
- Implement/Verify/Review（developer/tester/reviewer）：按 SPEC §5-§6 执行真实验收。

## 11. 开放问题（Open Questions）

- 运行前提（非未决业务语义）：Design §3.3 已固定 `QUANTDINGER_BASE_URL` / `QUANTDINGER_JWT` 进程接口，可选研究入口使用既有 `QUANTDINGER_AGENT_TOKEN`（V1.5 实际环境键为 skills/.env 的 `QUANT_DINGER_AI_AGENT_TOKEN_MYMQUANT`，绑定实例身份 MYM_QUANT_AI，注入边界由 T2 Design 冻结）。主控经现有安全机制注入；V1.5 最小例外为 CLI 进程内按精确键名读取 `skills/.env` 中唯一 Agent 键 `QUANT_DINGER_AI_AGENT_TOKEN_MYMQUANT`（仅当环境变量 `QUANTDINGER_AGENT_TOKEN` 未注入时启用，注入边界由 T2 Design 冻结），仍禁止读取其他任何键或整份 .env、禁止回写 .env、禁止输出到 stdout/stderr/异常/报告/argv/测试/fixture、禁止自动登录与收集浏览器 token；Human JWT 纪律不变（仍仅走环境变量 `QUANTDINGER_JWT`，CLI 不读 .env 找 JWT），主控不经浏览器、不收集浏览器 token；免费开关按操作人 2026-10-31「本地实例已关闭计费」前提执行（§5.3），真实业务/UI 与 V1.5 Agent 接入本身未验收。前提缺失阻断真实执行，不阻断离线实现，不请求新 token。
- strategy-lab reports 是否纳入 git 提交由 Closeout 阶段 Pascal 决定，本文档不预设。

## 12. 参考资料（References）

- 需求基准：`skills/strategies/strategy-lab/README.md`、`skills/strategies/strategy-lab/templates/strategy-spec.md`、`data/tasks/active/2026-10-29-strategy-lab/intake.md`。
- 契约细化：[SPEC-06-001 V1.5](../../spec/06_strategy/SPEC-06-001-strategy-lab.md)（功能规格、验收标准、持久化契约）；[DESIGN-06-001 V1.5](../../design/06_strategy/DESIGN-06-001-strategy-lab.md)（精确 allowlist、调用映射、预算与验证样例，Agent 接入实现边界见 DESIGN §8；当前 RFC/SPEC/Design 契约版本统一 V1.5，Agent 增量见 RFC §5.6 与 DESIGN §8）。V1.1 的 closure ledger 五项事实保留；当前 V1.5 仅增量 Agent Token 接入契约与费用条款修订，不改变 V1.4 通用业务目标与历史证据。
- 源码依据（只读核实，QuantDinger 子模块当前 HEAD）：`app/openapi/register.py`（进化蓝图挂载 /api/strategy-evolution）、`app/routes/strategy_evolution.py`、`app/services/strategy_evolution/{service,engine,statistics,models,parameter_space,evaluator}.py`、`app/routes/backtest_center.py`、`app/routes/script_source_routes.py`、`app/routes/strategy.py`（verify）、`app/utils/auth.py`、`app/utils/agent_auth.py`、`app/utils/agent_jobs.py`、`app/services/backtest_limits.py`、`app/services/billing_service.py`、`app/services/strategy_v2/{service,runtime,storage}.py`、`app/routes/agent_v1/{__init__,strategy_sources,backtests,jobs,markets,research,_helpers,health}.py`；Vue：`QuantDinger-Vue/src/views/backtest-center/StrategyEvolution.vue`、`src/api/strategy.js`；文档：`docs/agent/README.md`、`docs/agent/agent-openapi.json`、`docs/trading/STRATEGY_DEV_GUIDE.md`、`docs/trading/LIVE_TRADING_SAFETY.md`。

## 版本记录（Changelog）

| 版本 | 日期 | 更新内容 | 负责人 |
|---|---|---|---|
| V1.0 | 2026-10-29 | 初始创建：双入口矩阵、进化判定分支、预算与停止约束 | YQuant-Codex-Principal |
| V1.1 | 2026-10-29 | 纠正 Human 默认私有性、实际 wire 字段、validation 回撤均值与 blind 分离、folds 固定4及双计数预算；追加15000/15080主控探测与JWT前置，保留早先探测历史；同步SPEC/Design | YQuant-Codex-Principal |
| V1.2 | 2026-10-30 | 按 Pascal 明确裁定将策略/研究实例移到 skills/strategies/<strategy-id>/；同步当前路径清单与本地守卫，不改业务、预算或冻结安全边界 | YQuant |
| V1.3 | 2026-10-30 | Pascal纠正最终实例根为 skills/strategies/strategy-lab/strategies/<strategy-id>/；取代V1.2直属目录方案，仅同步路径、守卫与导入，不改业务/预算/安全门禁 | YQuant |
| V1.4 | 2026-10-30 | 方案 C：仅延长 spy-ma-smoke 至2017-06-01..2025-12-31，追加该窗口最多1个进化job；保留失败历史及每轮原预算，待独立Gate/真实验证 | YQuant-Codex-Principal |
| V1.5 | 2026-10-31 | Agent Token 接入增量（t_b3832b43）：按 Pascal 2026-10-31「本地实例已关闭计费」裁定修订 §5.3 费用条款（免 Human JWT public-config 前检，billing 收据事后如实记录+矛盾即停，旧门禁仅作 V1.4 历史事实）；新增 §5.6 Agent job/result 指标层级、幂等语义与 Agent 持久化读回差异契约（无 sourceId 注入、无 run 读回路由）；同步入口矩阵首选项、风险表、验收标准与开放问题；双入口矩阵与历史验收证据不变，待独立 Gate。2026-10-31 跨层对齐修正（t_5509aca5）：保持版本号 V1.5 不变，修正 RFC §11 与 DESIGN §8.3 的 .env 表述一致（skills/.env 精确单键 QUANT_DINGER_AI_AGENT_TOKEN_MYMQUANT 兜底），DESIGN §8.3 补冻结单一凭据解析口径 | YQuant-Codex-Principal |

## V1.3 最终目录裁定（2026-10-30，取代 V1.2 目录方案）

当前唯一有效实例位置为 `skills/strategies/strategy-lab/strategies/<strategy-id>/`。两个验证样例分别是 `skills/strategies/strategy-lab/strategies/spy-close-research/` 与 `skills/strategies/strategy-lab/strategies/spy-ma-smoke/`；二者不是用户网格策略、不代表可上线。strategy-lab 根层保留 SKILL、README、scripts、templates、tests，并由 strategies 子目录集中容纳具体实例。不得在 strategy-lab 根层或 skills/strategies 直属层留下这两个实例的副本或兼容 symlink。

V1.2 的直属目录位置已被本节替代，其版本记录保留作历史，不作为当前执行指令。此前已搬文件直接从现场继续收口，不能重建或覆盖已有 reports；历史报告命令/结论与数据逐字保留。CLI 路径守卫仅接受上述实例根的直接子目录，拒绝根外、更深嵌套和 symlink 逃逸。V1.3 当时只调整目录、必要路径/导入与命令，不改策略、算法、API、预算、认证或交易逻辑；目录裁定仍有效，当前 RFC/SPEC/Design 契约版本统一 V1.5（本节保留 V1.4 表述仅作历史事实），样例窗口以 §5.5 为准。

用户要求继续 T4 的请求保留；目录迁移只做离线验证，不等于解除既有安全暂停或真实业务通过。T4 的凭据传递与诊断拒绝须先按已批准边界纠正，禁止恢复已删除的明文 JWT 文件、禁止重跑被拒辅助诊断；不新增实盘/部署授权。
