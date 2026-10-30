# Strategy Lab：AI 策略研发与 QuantDinger 使用 Skill

## 1. 定位与首版范围

strategy-lab 是 `strategies` 下的操作型 Skill：让 AI 理解 Pascal 的策略/研究想法，开发或复用必要的 Python 脚本，优先使用 QuantDinger 已有能力，交付可执行脚本和实际结果。不是新的策略研发平台、回测引擎或任务管理系统。

本方案待 Pascal 整体确认；当前仅有本 README 与需求模板，尚未实现 Skill/执行代码，也未运行研究、回测或交易。

目录职责边界（2026-10-30 用户裁定）：`strategy-lab/` 只保留研发工具资产（本 README、
SKILL、`scripts/quantdinger.py`、`templates/`、`tests/`）；每个策略/研究实例放在
`skills/strategies/strategy-lab/strategies/<strategy-id>/`，现有样例为
`skills/strategies/strategy-lab/strategies/spy-ma-smoke/` 与
`skills/strategies/strategy-lab/strategies/spy-close-research/`。

首版保留两类需求：

| 类型 | 最小实现方式 | 交付 |
|---|---|---|
| 交易类 | 复用 QuantDinger 模板、官方生成器、Strategy API V2、回测及适用的参数比较能力；确需新规则时开发 Python | 策略脚本、实际参数、回测结论、QuantDinger 源码/结果关联，平台界面可查 |
| 研究类 | 按问题编写可重跑 Python；优先使用 QuantDinger 的数据和研究接口，平台适用时直接调用 | 研究脚本、数据来源、参数、分析结果与简明报告 |

研究类不强行包装为交易策略。如果 QuantDinger 不提供所需数据，先说明缺口，优先复用项目已有数据能力或用户提供的数据；不为单项研究新建 Provider 框架、数据库或通用模型平台。现有接口不足以回答问题时明确报告限制，不伪造结果。

## 本地运行与测试环境

Pascal 已确认：strategy-lab 的本地 CLI、研究脚本与测试统一使用项目根目录的 `.venv/bin/python`，从 `/home/pascal/workspace/yquant-investment` 执行；其他工作目录须使用该解释器的绝对路径。不依赖 shell 是否激活环境，不使用 Hermes 自带 Python，不新建 strategy-lab venv，不借用 QuantDinger 后端 venv。

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s skills/strategies/strategy-lab/tests -p test_quantdinger.py -v
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/spy-close-research/research.py --data-api human
```

此约定只统一调用环境，不表示测试或业务闭环已通过。策略源码在 QuantDinger 平台沙箱执行时仍由平台管理其运行环境，不能将本地解释器替换到平台服务。

## 1.1 Agent 通道（V1.5）

strategy-lab 除 Human JWT 通道外，新增一条受限的原生 Agent Gateway 通道
（`/api/agent/v1`）。两条通道**互不混用**：一次命令只用一个通道，401/403 一次即停，
不自动切换、不重登、不换凭据绕过。

### 命令示例（不含任何凭据值）

```bash
# 身份前检：返回 agent_name / scopes / markets / instruments / paper_only / 限额
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py agent-whoami

# Agent 异步回测：compile 校验 -> 提交 -> 轮询 job 至终态 -> 写 reports/agent-backtest.md
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py agent-backtest --strategy-dir skills/strategies/strategy-lab/strategies/spy-ma-smoke --start 2024-01-01 --end 2024-12-31 --capital 10000 --commission 0.0005 --slippage 0.0005

# Agent 行情（与 Human 行情共用同一 CLI，显式选择通道）
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py fetch-klines --data-api agent --market USStock --symbol SPY --timeframe 1D
```

凭据由操作者经环境注入（`QUANTDINGER_AGENT_TOKEN`）；环境变量缺失时 CLI 只读
`skills/.env` 中且仅 `QUANT_DINGER_AI_AGENT_TOKEN_MYMQUANT` 一个键作为兜底。
**令牌值不出现在命令行、输出、报告或异常中**，本文档与示例一律不写真实 token。

### 输出字段说明

`agent-whoami`（stdout 单行 JSON，已剔除 `user_id`）：

| 字段 | 含义 |
|---|---|
| `agent_name` | Agent 身份名（如 `MYM_QUANT_AI`） |
| `scopes` | 授权 scope 列表（`R`/`W`/`B` 等） |
| `markets` / `instruments` | 允许的市场与标的范围 |
| `paper_only` | 是否仅模拟盘 |
| `rate_limit_per_min` / `max_order_notional` / `max_daily_notional` | 限流与名义额度 |

`agent-backtest`（stdout 单行 JSON + `<strategy-dir>/reports/agent-backtest.md`）：

| 字段 | 含义 |
|---|---|
| `jobId` / `status` / `kind` / `createdAt` | 提交回执与 job 身份 |
| `runId` | 平台回测 run 标识（来自 Agent job `result.runId`） |
| `idempotentReplay` | 本次是否命中同键重放（`Idempotent-Replayed: true`） |
| `metrics` | Agent 扁平顶层指标（`totalReturn`/`maxDrawdown`/`sharpeRatio`/`annualizedReturn*`/`totalTrades` 等），**不与 Human `data.result` 混读** |
| `context` | 服务端注入字段（`resultStatus`/`dataProvenance`/`executionAssumptions`/`benchmark*`/`diagnostics` 等），照实记录 |
| `sampledArrays` | 网关有界采样的曲线数组长度（不是全量明细） |
| `billing` / `billingStatus` | 202 回执与 job 读回的计费收据；`billingStatus=absent` 表示缺失，**不等于 free** |
| `sourceAssociation` | 恒为「无 sourceId/run 读回关联」；Agent 持久化 run 的 `source_id` 为 NULL 是平台契约差异，不视为失败 |
| `unsupported` | 该通道不可用能力清单（网格 generate、Strategy Evolution、run/sourceId 读回、Agent 交易） |

### 计费前提与矛盾即停

本地实例按操作人 Pascal 2026-10-31 确认「付费已关闭」执行。这是**部署前提声明**，
不是 API 实测，也不泛化到未知远端或可能收费的实例。

- 客户端事后如实记录 billing 收据（`enabled`/`feature`/`cost`/`charged`/`remaining`/`status`）；
  缺失记 `absent`，不推断为 free。
- 出现 `status="charged"`、`charged>0`、HTTP 402，或其他与「付费已关闭」前提矛盾的信号 →
  **立即停止后续提交**，把矛盾证据写进报告，交操作者裁定。
- 不自动付费、不自动重试、不自动退款，也不静默改走 Human 通道绕过。

### 幂等与未知提交

`compile` 与 `backtest.run` 各自使用一枚 `Idempotency-Key`（`uuid4().hex`）。
缺键或键长 >120 字符在客户端发送前即拒发。收到 409（同键异体 / 同键进行中）立即停止 exit2。
提交后网络失败或超时使状态未知时，用**同一把键**重放原请求恰好一次；收到
`Idempotent-Replayed: true` 即视为同一提交并继续轮询既有 jobId；两次都失败则报
outcome-unknown（exit5），禁止用新键盲发新提交。

## 2. 只有三个业务步骤

```text
定义：理解需求，写清目标、规则、参数与验收
  ↓
执行：脚本就绪 → 基准回测/分析 → 自动判断是否进化
      ├─适用：调用 QuantDinger 策略进化 → 核对候选与基准
      └─不适用：保留基准结果并说明原因
  ↓
交付：保存脚本、结果与说明，返回结论和平台关联
```

### 定义

由 YQuant 在策略目录生成简短 `spec.md`，说明原始想法、目标、数据/市场、规则或方法、输出及约束，并明确可调参数、比较目标和计算预算。明确的可配置参数存 `config.json`，spec 解释其含义，不重复维护数值。只有影响正确性或资金语义的关键歧义才询问，不增加常规需求审批。

### 执行

- 先复用 QuantDinger 已有模板、官方生成器、接口或服务，不默认修改其源码，不开发第二套引擎。调用方式以当前实际契约为准，只补完成任务必需的薄脚本，不预设 MCP、SDK 或统一运行时建设。
- 新增或实质修改 Python 逻辑，通过真实 Kanban 委派 `yquantdeveloper`；`yquanttester` 按同一需求独立验证。YQuant 负责定义、派发、调用与结果判断。普通参数调整、官方生成器调用和已有脚本执行不反复派开发卡。
- 具体工程流程沿用项目已批准规则；核心交易/风控、公共接口或架构变化不因名称是“研究脚本”而自动豁免。业务三步不等于三张卡，也不替代正式工程契约。
- 只做任务需要的分析、回测或参数比较，不默认运行全套统计工具。已有验证证据适用时复用；任务预算到达、无合格候选或能力不足时返回事实结论，不无限优化或放宽条件。
- 核对真实数据、市场/时间身份、参数确实被消费、指标口径、成本与用户硬约束。适用的样本外验证不得泄漏；资金费、强平等未建模项要说明，未知不能标通过。

### 执行内置子流程：自动调用原生策略进化

不是另加业务阶段，而是在执行中明确触发、调用、结果处理和停止条件。新交易策略或明确的优化任务，在基准可以正常运行后自动检查；存在已声明且实际生效的可调参数、有明确选优目标且预算允许、用户未禁止优化时，直接触发一次有界原生进化，不等用户另行点击或再次批准。基准无需先盈利，但数据或代码错误应先处理，不能让优化掩盖。

1. **准备与估算：** 保存/选择私有 source，调用 parameter-space 取得真实参数空间；按 spec/config 限定范围与目标，调用 estimate 核对预算。预算不够则在允许范围内收缩搜索，不能擅自加预算或放宽风控。
2. **自动执行：** 通过现有授权接口/原生服务调用 run，按返回 job ID 查询 jobs，复用平台搜索、验证、诊断、进度与历史；不另建优化器或任务系统，不为复用先建设 MCP/SDK。
3. **自动处理结果：** 将候选与基准按一致窗口、成本核对硬约束，先筛选合格项再按预先定义目标比较。候选合格且满足既定选优目标时形成研究推荐；没有改进时仅在基准合格的前提下保留基准，均不合格则报告无合格候选，关键项未知则标证据不足。基准不合格而候选合格时，不因候选收益较低就拒绝合格方案。只补平台未覆盖的必要检查，不把其全部验证重算一遍。
4. **收敛与交付：** 需要正式历史时将最终候选送入原生回测保存；报告给出基准/候选对比、实际推荐参数、未覆盖项及平台 ID。此轮结束，不为追求通过而无限重启进化；平台报错或超预算就返回原因，不自动改策略逻辑。

不适用时正常继续交付并说明原因：纯研究脚本不符合平台契约、没有可调参数、用户只要固定参数结果或显式不优化、已有成熟策略的普通手工/定期执行。研究类仍可按其目标做必要参数比较，但不伪装成交易策略来强用进化功能。

参数空间缺失时先说明；必要的最小参数接线属于 developer/tester 的研发范围，不提前改引擎。修改规则/模型不是调参。自动推荐只作用于本轮研究，不自动覆盖现有运行配置或 Live；上线仍经过 G1/G2。配置不变的日常执行也不启动后台自进化循环。

本节是待实现的自动化约定。目前只核对了官方说明、本机源码与接口声明，未提交真实进化任务，不能称已经实现接入。

### 交付

- 本地保存 spec、参数、实际脚本和结果。结论说明数据来源、关键参数、验证依据及限制；适用时给条件收益区间，不承诺盈利。
- 交易类通过 QuantDinger 原生接口/服务保存私有源码与最终历史回测，核对平台 ID 和页面实际展示；不为展示而创建交易部署。平台已有业务记录直接引用，不复制本地账本。
- 研究类结果直接放本策略 reports；能复用平台研究记录就引用，不能映射时不伪造平台条目，也不为其先开发通用报告页面。

## 3. 开发完成后直接执行

需求和逻辑不变时：**手工/已获准定期触发 → 调用已验证脚本或平台入口 → 更新规定结果**。不重走研发、不重新派开发/测试、不逐次建立档案。

QuantDinger 的常驻策略继续由平台运行，不定时重复创建部署或实例。本地分析可只更新 `reports/latest.csv` 等约定输出；需要历史对比或重要研究结论时才归档。执行成功/失败使用既有平台/任务日志或结果字段，不新建监控系统。

讨论定期执行不授权创建 cron、systemd 或新增长期服务；实际新增调度时另按既有规则确认。

## 4. 一个策略一个目录

```text
skills/strategies/strategy-lab/
├── SKILL.md              # 操作型 Skill
├── README.md             # 本文件
├── scripts/              # 共享工具 CLI（quantdinger.py）
├── templates/            # spec.md 模板
├── tests/                # 离线 unittest
└── strategies/           # 每个策略/研究一个目录
    └── <strategy_id>/
        ├── README.md          # 简要说明、执行方式、平台关联
        ├── spec.md            # 需求与验收
        ├── config.json        # 有可配置参数时使用
        ├── strategy.py        # 实际研究/策略脚本
        └── reports/           # 运行结果、报告、必要支撑材料
```

不增加 version、runs、逐次 manifest、快照或审计目录。研发中间过程默认不全量保存；最终报告保留解释候选选择和验证所必需的摘要。重要结论需要额外证据时就近放 reports，平台可恢复内容只引用。

材料不放项目 data 目录，不覆盖需要保留的重要研究/上线证据。QuantDinger 原生业务事实及交易审计继续由平台维护；省本地目录不等于删除平台审计。正式工程 RFC/SPEC/Design 仍遵循项目 docs 规则。

## 5. 自动化与实盘边界

- 研究、历史回测及预算内参数比较自动执行；获准范围内保存私有源码和研究结果不逐轮审批。
- 研究阶段不绑定实盘凭据、不创建 Live 部署、不发真实订单；不自动改生产配置或开通付费数据。
- 用户要求上线时沿用两个 Gate：**G1 上线前验收 → G2 Pascal 批准明确上线单**。G1 合并策略/风险、账户兼容、适用 Demo 和对账证据，已有证据按影响范围复用；Demo 首次仍需有界授权。
- 批准后仅由既有受控执行系统即时复核并运行。正常获准订单不逐笔审批，越界或未经批准的策略变更重新确认。首版不新增自动实盘部署、风控引擎或订单系统。

## 6. 首版验收与不做事项

用一个交易样例验证：自然语言需求 → 复用/开发 Python → 基准回测 → 满足条件后自动提交原生策略进化并查询终态 → 候选/基准比较及推荐判定 → 最终回测/源码 UI 可查 → 本地报告。另覆盖无可调参数跳过、未改进保留基准、无合格候选或任务失败时如实停止，不自动修改实盘。

用一个研究样例验证：自然语言问题 → Python 脚本 → 真实数据分析 → 保存 reports → 同一脚本可再次执行。研究样例优先从 QuantDinger 实际可提供的数据开始，不把新数据接入作为首版通用框架建设。

两类均需证明未授权时不会触发交易。示例中的网格约束需区分交易所杠杆与 gross exposure、峰值回撤与初始本金亏损；不能因回测结果好就声称运行时限额已经落实。

首版不建设：通用研究引擎、新数据平台、第二套优化器、运行档案系统、强制版本目录、全套统计工具链、自动调度平台、自动实盘部署。出现具体需求后再按最小必要范围扩展。

方案依据：Pascal 本次会话决策及已有 QuantDinger/项目操作约定。当前是待确认的最小功能方案，不是已实现或已验收的能力声明。
