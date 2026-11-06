---
name: strategy-lab
description: "YQuant Strategy Lab：按「定义 → 执行 → 交付」三步操作 QuantDinger 原生回测/进化与真实数据研究的最小操作 Skill。"
---

# Strategy Lab

按 [RFC-06-001](../../../docs/rfc/06_strategy/RFC-06-001-strategy-lab.md)、
[SPEC-06-001](../../../docs/spec/06_strategy/SPEC-06-001-strategy-lab.md)、
[DESIGN-06-001](../../../docs/design/06_strategy/DESIGN-06-001-strategy-lab.md)（三文档V1.4；方案C独立Design Gate、T4验证及T5首版签收已通过，详见文末状态与正式报告）
运行的操作型 Skill。本文件是面向 AI 的操作约定，不是 runtime；不建第二套回测引擎、任务系统或 SDK。

## 目录职责边界（2026-10-30 用户裁定）

- `skills/strategies/strategy-lab/`：**只放研发工具资产**——本 SKILL、README、`scripts/quantdinger.py`、
  `templates/strategy-spec.md`、`tests/`。
- `skills/strategies/strategy-lab/strategies/<strategy-id>/`：**每个策略/研究实例一个目录**，
  集中在 `strategy-lab/strategies/` 子目录下。
  现有两个样例为 `skills/strategies/strategy-lab/strategies/spy-ma-smoke/`（交易接入冒烟）与
  `skills/strategies/strategy-lab/strategies/spy-close-research/`（研究取数/重跑），
  均非用户网格策略、不代表可实盘。
- 未来新增策略一律建在 `skills/strategies/strategy-lab/strategies/<strategy-id>/`，
  不得建在 `strategy-lab/` 根层，也不得建在 `skills/strategies/` 直属层。
- `quantdinger.py trade --strategy-dir` 只接受
  `skills/strategies/strategy-lab/strategies/` 的**直接子目录**，拒绝更深嵌套、
  根外目录与符号链接逃逸。

## 本地运行环境（Pascal 已确认）

本地 CLI、研究脚本和单测一律显式使用项目 venv Python 3.12，不依赖 PATH 或环境激活：

- 项目根执行：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python ...`
- 跨目录执行：`PYTHONDONTWRITEBYTECODE=1 /home/pascal/workspace/yquant-investment/.venv/bin/python ...`

不得使用 PATH 中的 python3、Hermes 自带解释器或 QuantDinger 后端 venv；不新建模块 venv、不安装依赖。
该约定只统一本地调用环境；策略 `.py` 源码仍在 QuantDinger 平台沙箱执行，本地不 import、不运行。
历史 run/报告保留其真实旧解释器记录，不追认为项目 venv 结果。

## 目录结构

```
strategy-lab/                     # 只放研发工具资产
├── SKILL.md                  # 本文件
├── README.md                 # 已确认方案（上游文档，不改动）
├── templates/strategy-spec.md  # spec.md 模板（上游文档，不改动）
├── templates/research-report.md  # 研究类报告模板（可编辑）
├── scripts/quantdinger.py    # 单文件薄调用 CLI（trade / fetch-klines / agent-whoami / agent-backtest）
├── tests/test_quantdinger.py # stdlib unittest 离线断言
└── strategies/                # 每个策略/研究一个目录，集中在 strategy-lab 内
    ├── INDEX.md               # 实例索引（登记全部策略/研究实例）
    ├── spy-ma-smoke/          # 交易类示例（README/spec/config/strategy.py/reports）
    └── spy-close-research/    # 研究类示例（README/spec/research.py/reports）
```

每个策略/研究一个目录：`spec.md`（需求冻结）、`config.json`（仅交易参数数值）、
主脚本（`strategy.py` 由平台执行 / `research.py` 本地执行）、`reports/`（最新结果）。
不建 version/runs/manifest/快照目录。

## 业务三步

1. **定义**：在 `skills/strategies/strategy-lab/strategies/<id>/` 写 `spec.md`（目标、数据/市场身份、规则、参数、硬约束、
   比较目标、预算）与交易类 `config.json`（仅可调参数数值）。语义冻结在 spec，不从自然语言现场解析。
2. **执行**：
   - 交易类：`scripts/quantdinger.py trade --strategy-dir <dir> ...` 一次前台顺序流程——
     认证与免费能力预检（public-config 先 JWT 认证，`billing_enabled=false` 才提交）→
     compile → create（显式 `visibility=private`、`status=draft`）→ detail 读回 →
     基准回测（persist=true）→ parameter-space → estimate（超预算只收缩 ≤2 次）→
     恰好一次 evolution run → 候选全段复检（参数组含基准 ≤5）→ 六分支判定 →
     有推荐则最终回测并读回 → 写 `reports/report.md` 与 `reports/comparison.csv`。
   - 研究类：目录内 `research.py` 直接执行；只调用行情读接口，不交易、不进化。
3. **交付**：报告记录 `sourceId`/`runId`/`jobId`、判定分类、限制与复现命令；
   平台侧 UI 实查（`/strategy-ide?sourceId=`、`/backtest-center?sourceId=`）由独立 Verify 完成。
   研究类报告必须包含 [templates/research-report.md](templates/research-report.md) 的核心字段
   （结论摘要、数据与口径声明、假设与未建模项、限制与不适用范围、结果明细、复现命令、证据分级）；
   量化口径（年化周期数、初始资金、成本与未建模项等）必须显式标注，不得沿用默认值而不声明。

## 研究预检（研究类开工前必过）

研究类任务开写脚本、发起取数或提交回测前必须逐项过下表；这是必过门，不是可选参考。预检失败不消耗 job 配额：先缩范围或换通道，不提交、不等报错。

| 检查项 | 判据 | 失败处理 |
|---|---|---|
| 回测窗口 vs 周期上限 | 1m/3m ≤30 天；5m ≤180 天；15m/30m ≤365 天；1H/4H/1D/1W ≤1095 天（表内为默认档基线；实际窗口上限以 compile 返回的 `backtestRangePolicy` 为准，USStock/Forex 可能更窄，如 USStock 5m/15m/30m ≤60 天、Forex 1m ≤7 天） | 先缩窗或改周期，不提交等报错 |
| 标的上市日 vs 窗口起点 | 窗口起点晚于上市日；不足则证据不足 | 改窗口起点或标 insufficient-evidence |
| 通道能力支持 | 网格 generate / Strategy Evolution / run-sourceId 读回 / Agent 交易 在 Agent 通道 unsupported | 声明不支持并换 Human 通道或说明缺口 |
| 数据形态 | 单页 ≤500；第 1 页无 before_time 时平台封顶 300；翻页收敛为 `--max-pages 2`；gate spot 单请求窗口 ≤999 天 | 显式设 `--max-pages 2`；超窗改窗口 |
| 取数连通 | 直连需 `NO_PROXY` 含 `.gateio.ws`；直连不可用时代理须可达 | 先核对 env，再判定数据不可得 |
| 未建模项 | 资金费、强平、成交量单位/适用性 | 必须写入报告局限；未知不得标通过 |
| 杠杆口径 vs 回执读回 | 请求 `leverageEnabled=true` + `leverage=N` → 回执 `executionAssumptions` 必须读回 `initialCapital`（等于请求的初始资金）、`leverageEnabled=true`、`leverage=N`；`initialCapital` 是账户权益（初始投入），保证金为派生量（名义敞口 ÷ leverage），名义敞口 = `initialCapital` × 每格预算占比 × leverage；禁止把 `initialCapital` 调大来假装杠杆 | 不提交；已提交则判证据不足，不判通过 |
| 预算 | 研究数据请求 ≤50、外层持久化回测 job ≤8、墙钟 ≤1800s、folds 固定 4 | 超限先缩范围，不加预算 |
| 交付形态 | spec.md / 可复现脚本 / reports/ / 复现命令 | 缺一不算完成 |

## 自动进化与停止规则（SPEC §5 冻结，不现场改判）

- 跳过：scope=none、无 optimizable 参数、用户显式禁优化、研究类/成熟策略日常执行 →
  不调 run，报告 skipped+原因；基准仍须核对硬约束。
- 判定只落在六分支之一：skipped / baseline-kept / candidate / no-qualified-candidate /
  insufficient-evidence / failed（含超预算）。任何影响结论的 UNKNOWN 优先 insufficient-evidence，
  缺失指标不当 0，不把 `summary.maxDrawdown`（validation 折绝对值均值，不含 blind）当全段 MDD；
  硬约束只认全段读回 run 的 `data.result.maxDrawdown`。
- 停止：run 恰好 1 次，failed/cancelled/workerInterrupted/超预算即停，带
  `progress.failure` 诊断，不自动重试、不换窗口/成本/硬约束求通过。
- 预算上限（可下调不可上调）：trials ≤64、全段复检组 ≤5、外层持久化回测 job ≤8、
  研究数据请求 ≤50、墙钟 ≤1800s、folds 固定 4；estimate 与 actualBacktestRuns 分栏记录。

## 命令与退出码

spy-ma-smoke当前仅按2026-10-30批准的方案C延长至2017-06-01..2025-12-31，warmup260、folds4、
源码/算法/搜索空间/成本/硬约束不变。独立方案C Design Gate完成前主控不执行业务；下方trade命令
只在开始前只读核查该窗口无已有job后使用。若已有job则只读回、禁止重复创建；本次一次性额外
授权最多1个新原生进化job，不把通用每次恰好一次进化规则改成2次。历史旧窗口
2023-01-01..2025-12-31（superseded）的run19与failed job `d249d4846e8e493b8d0d316b340f99de`
（observationRangeTooShort）保留并与新窗口job分列，不重试旧job、不改历史reports/命令。
每轮内部backtestRuns/actualBacktestRuns≤8、relativeUnits≤8、外层持久化回测jobs≤8（预计最多6）、
参数组含基准≤5、墙钟1200s、零新增付费保持；失败/取消/超预算立即停、不自动重试，提交结果未知不重发。

变更样例窗口须用真实观测及原生拆分核验有效四折，不能以自然日或estimate.folds当通过证据。
Design V1.4 §5.1所引C预检真实日末2159条/午夜2158条均有效4折；公开取数不保证进化evaluator
快照相同，真实job仍须核对四折、覆盖与成本。actualBacktestRuns=None为未报告，不推断0。

```text
# 交易类（示例固定值来自 spy-ma-smoke/spec.md；凭据由主控经安全机制注入环境）
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py trade --strategy-dir skills/strategies/strategy-lab/strategies/spy-ma-smoke --start 2017-06-01 --end 2025-12-31 --capital 10000 --commission 0.0005 --slippage 0.0005 --search ma_period:20:80:20 --objective totalReturn --max-drawdown-pct 50 --method grid --trials 4 --folds 4 --max-evolution-runs 8 --max-relative-units 8 --wall-seconds 1200

# 研究类（真实取数，两次执行可重跑比对）
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/spy-close-research/research.py --data-api human
```

退出码：`0` 正常业务结果（含 skipped / no-qualified-candidate）、`2` 平台或契约失败、
`3` 证据不足、`4` 认证缺失或 401/403、`5` 预算或超时、`64` 参数或本地路径错误。

## Agent 通道（V1.5）

原生 Agent Gateway（`/api/agent/v1`）的受限研究通道，与 Human JWT 通道**互不混用**：
一次命令只用一个通道，不自动切换、不重登、不换凭据绕过 401/403。

### 能力矩阵

| 能力 | operation | method + path | 状态 |
|---|---|---|---|
| 身份前检 | `agent_whoami` | GET /api/agent/v1/whoami | 支持（scope R） |
| 行情 | `agent_klines` | GET /api/agent/v1/klines | 支持（scope R，≤2000 根/次） |
| 策略编译校验 | `agent_compile` | POST /api/agent/v1/strategy-sources/compile | 支持（scope W，仅返回 manifest） |
| 异步回测 | `agent_backtest_run` | POST /api/agent/v1/backtest/run | 支持（scope B，202 回执 + jobId） |
| job 读回 | `agent_job` | GET /api/agent/v1/jobs/{jobId} | 支持（scope R，读至终态） |

**unsupported（调用前先说明，不静默跳过、不静默降级）**：网格 generate、Strategy Evolution
全链路、run/sourceId 读回与 history、UI 历史关联、publish/部署/Live、Agent 交易（SCOPE_T/C）。
Agent 网关没有这些路由，不为其扩平台、不建 SDK/MCP。

### 行情取数契约（2026-10-31 实测）

Agent 行情走 `/api/agent/v1/klines` → 平台 `KlineService.get_kline()` → 主源取自
`CRYPTO_PUBLIC_DEFAULT_EXCHANGE`（**不是** `CRYPTO_PUBLIC_KLINE_PRIMARY`，后者只管
`for_public_market` 路径）。本机出口仅 gate.io 可直连，故两个变量都设为 `gate`，
且 `NO_PROXY` 必须含 `.gateio.ws`。

**必须显式 `--max-pages 2`**（或带 `--start/--end`）。原因：

- 第 1 页（无 `before_time`）：任何 limit 都返回 300 根，平台内部把单次返回封顶 300。
- 第 2 页（带 `before_time`）：`limit ≤ 500` 时 HTTP 200（约 0.2s）；`limit ≥ 600` 时**请求挂起**
  直到超时——平台按 `limit+1` 天换算窗口并落到跨所 fallback 链。
- 第 3 页：PUMP 等 2025 年才上市的币，起点早于上市日 → 同样挂起。默认 `max_pages=4` 会一直
  试到 30s HTTP 超时，报 `http.timeout` exit 5。

因此 CLI 侧 `KLINE_PAGE_LIMIT = 500`（Human/Agent 共用单一常量），并用 `--max-pages 2`
收敛翻页次数。实测覆盖：PUMPUSDT 475 根（2025-07-14 起），AAVE/JUP/SUI 各 800 根
（2024-08-23 起），单次耗时 0.3–0.5s。gate spot 单请求窗口上限 999 天（1000 天 → HTTP 400）。

### 命令

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py agent-whoami

# Agent 行情取数（必须显式 --max-pages 2，见下方「行情取数契约」）
QUANTDINGER_BASE_URL=http://127.0.0.1:15000 NO_PROXY=127.0.0.1,localhost \
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py \
  fetch-klines --data-api agent --market Crypto --symbol <SYM> --timeframe 1D --max-pages 2

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py agent-backtest --strategy-dir skills/strategies/strategy-lab/strategies/<id> --start YYYY-MM-DD --end YYYY-MM-DD --capital <number> --commission <ratio> --slippage <ratio> [--leverage-enabled --leverage <1..100>] [--wall-seconds <int>]
```

`agent-backtest` 语义：读 `<strategy-dir>/strategy.py` 与 `config.json` → 一次 compile 校验
（失败即停）→ 一次 backtest 提交（请求体仅白名单字段，禁 `sourceId/persist/strategyId`）→
按 15s 间隔与单调截止轮询 job 至终态 → 报告写入 `<strategy-dir>/reports/agent-backtest.md`。
`--leverage-enabled`（默认关）+ `--leverage`（默认 1，有限 1..100，关闭时必须为 1）在 compile
等任何请求前校验；请求倍数 >1 时要求 compile manifest `leverageAllowed` 严格 True（否则 exit2
且不发 backtest、不占 job 配额），默认/1 沿用旧 manifest 兼容，客户端不乘资本或订单。
`--leverage-enabled` + `--leverage N` 是**唯一**能真正启用平台杠杆的写法；不传这两个参数时
平台**静默按 1 倍执行且不报错**，回执不会给出任何降级提示，因此不得以「提交成功」推断杠杆已生效。
回执读回核对是**必过项**：job 终态后必须读取 `executionAssumptions` 的
`initialCapital`/`leverageEnabled`/`leverage` 并与请求逐项比对，缺失或不可读判 UNKNOWN（证据不足），
**不得用请求参数代替回执**；不一致按契约失败处理，缺失按证据不足处理，两者都不静默放行。
名义敞口 = `initialCapital` × 每格预算占比 × leverage，**只能有一个放大器**：禁止把 `initialCapital`
调大后再乘 leverage（会得到远高于目标的敞口），也禁止同时用放大初始资金和调大每格占比两种方式叠加。
流程实现位于 `scripts/agent_backtest.py`（builder/计费矛盾/Agent 流程三函数抽取），CLI 保留同名
兼容壳并调用时注入依赖；该抽取属本地离线实现，不表示运行中引擎杠杆已验收。
提交后状态未知（网络失败/超时）时以**同一** Idempotency-Key 重放恰好一次；两次均失败 → outcome-unknown、
exit5，禁止盲发新提交。409（同键异体/进行中）→ 立即停止 exit2。

Agent 结果层级与 Human `data.result` **不混读**：Agent 走 job `result` 扁平顶层指标 + `runId`；
Agent 持久化 run 的 `source_id` 为 NULL 是平台契约差异，不视为失败、不声称 UI 历史可见。

### 凭据注入边界

- 唯一 Agent 令牌环境键：`QUANTDINGER_AGENT_TOKEN`（显式注入，优先）。
- 兜底（用户 2026-10-30/31 批准的最小例外）：上述环境变量缺失时，只读 `skills/.env` 中
  **且仅** `QUANT_DINGER_AI_AGENT_TOKEN_MYMQUANT` 一个键，忽略其余行。
- 两项均缺失 → exit4 auth-missing，零网络请求。
- 禁止改写/回写 `.env`，禁止读取其他任何键或整份 `.env`，禁止浏览器登录与浏览器存储读取。
- 令牌值不进 stdout/stderr/异常/报告/argv/测试/fixture；`_scrub` 单独覆盖 `qd_agent_` 令牌形状。
- Human JWT 纪律不变：仅环境变量 `QUANTDINGER_JWT` 注入，CLI 不读 `.env` 找 JWT。

### 计费前提与矛盾即停

本地实例按 Pascal 2026-10-31 确认「付费已关闭」执行（部署前提声明，非 API 实测）。
提交后如实记录 202 回执与 job 读回中的 `billing`（`enabled/feature/cost/charged/remaining/status`）；
billing 缺失记 `absent`，**不推断为 free**。出现 `status:"charged"`、`charged>0`、HTTP 402
或其他与关闭计费前提矛盾的信号 → 停止后续提交并如实报告证据，交操作者裁定；
不自动付费、不自动重试、不自动退款。

## 研究输出表结构标准（2026-11-03 Pascal 裁定；V1.11 2026-11-04 频率参数化与强平价降级修订）

本节是**研究类任务的统一输出格式契约**。任何多窗口/多合约研究都必须产出表 A 与表 B 两种载体，
列名、均值格式与资格判定枚举以本节为准，不得各研究自行发明。列集以 DESIGN-06-002 V1.11 §16.4 为唯一基准。

### 研究参数与频率（V1.11 D5-1）

频率是**研究实例参数，不是系统常量**：换频率（1m/15m/1h/4h/1d）只改实例参数，不改本契约与脚本。
- `build_cells(anchor_utc, frequency_seconds=3600)` 双参数；本轮批次 `frequency=1h`
- Sharpe 年化因子按公式 `K = 365 × (86400 / frequency_seconds)`（1h → 8760）
- **覆盖率预检**（执行前必过，不过则该 cell `insufficient-evidence`）：
  `window_bars ≤ min(venue 单 venue 保留根数, 合约上市以来根数)`。
  Gate swap 实测参考：1m≈6.9 天 / 15m≈104 天 / 1h≈417 天；1h 全年四窗口（365 天）在 Gate 覆盖内。

### 表 A：逐 cell 明细表（每个 合约×窗口 一行；列集 = DESIGN §16.4，21 列）

| 列 | 含义 |
|---|---|
| `task_date` / `anchor_utc` | 研究任务日 / 锚点（`anchor_utc == task_date 的 UTC 午夜`，可程序化核对） |
| `cell_id` | `<CONTRACT>-<Wn>`，全局唯一 |
| `contract` / `window` | 合约标识 / 窗口标识（W1 最新，W4 最旧） |
| `start_utc` / `end_utc` | 窗口半开区间 `[start, end)`，UTC |
| `expected_bars` | 窗口预期 bar 数 = span / frequency_seconds |
| `L` / `U` | 网格下/上界（训练集 min(low)/max(high)） |
| `g_pct` | 对数等距网格间距（%） |
| `N` | 网格数量（格数，不含上下界 → 网格线 = N+1） |
| `margin_return_pct` | 保证金口径**区间累计收益率**（%），覆盖整个窗口，**非年化** |
| `sharpe` | 逐 bar 权益收益的年化夏普（K=365×86400/frequency_seconds，ddof=0，rf=0）。**算术均值口径**：负区间收益仍可为正（μ>0 但 μ−σ²/2<0），高杠杆高波动下严重失真，判定以 `max_drawdown_pct` 为准 |
| `max_drawdown_pct` | 峰值回撤（%） |
| `worst_gross_to_equity` | 窗口内最不利 gross/equity（平台 `grossExposure` 原值，比值语义）；风险判定 G/E 的依据，载体常量 `grid_research.GROSS_TO_EQUITY_COLUMN`，缺值写 `N/A`、不得写 0（2026-11-06 起写入 `cells.csv`，此前的载体无此列） |
| `downward_liquidation_price` | **多头强平预估价格**（MMR 按来源分层获取，见「强平预估价格口径」；全部来源失败时 `N/A`） |
| `upward_liquidation_price` | **空头强平预估价格**（MMR 按来源分层获取，见「强平预估价格口径」；全部来源失败时 `N/A`） |
| `venue_disclosure` | 实际数据 venue 与换源披露（含 benchmark 通道；单 venue 时写 `gate`） |
| `qualification` | 资格判定（见下方枚举） |
| `reason` | 失败/证据不足/数据缺失原因（成功时为空） |

`job_id`/`run_id`/`tool_status`/`research_status` 保留在 evidence 层 JSON（可回溯平台原生记录），不占表 A 契约列位。

**载体 `cells.csv` 实际列（以 `write_cells_csv` 为准，共 31 列）**：上表 21 列中 `venue_disclosure` 落为 `venue`/`market_type`/`settle`/`product`/`native_instrument` 五列，另含 `frequency_seconds`、`status` 与上述 `job_id`/`run_id`/`tool_status`/`research_status` 回溯列；`worst_gross_to_equity` 紧随两列强平价之后。

**载体归档约定（2026-11-04 Pascal 裁定）**：研究完成后必须用既有 `write_cells_csv` / `write_comparison_csv` 产出契约载体 CSV 并随报告归档到 `data/reports/<topic>/evidence/`（`cells.csv` 31 列、`cells-comparison.csv` 14 列）。报告正文中的表是给人读的视图；**契约载体是给用户做分析与决策的数据基准**，两者都必须交付，缺载体视为研究未完成交付。

**缺行规则**：预定义矩阵中的每个 cell 必须出现在表中。缺证据/未执行的 cell 保留占位行，
指标列填 N/A 并在 `reason` 写明原因，**不得丢行、不得留空、不得填 0**。

### 汇总表生成契约（表头与展示样式以代码为准）

表 B 的**列序、中文表头、数值格式、判定符号、脚注**全部固化在
`scripts/grid_research.py`，不允许手工维护：

| 契约位置 | 内容 |
|---|---|
| `TABLE_B_HEADERS` | 列序 + 中文表头（CSV 载体列名 = 该表 key，顺序完全一致） |
| `TABLE_B_FOOTNOTES` | 判定符号说明 + 指标口径说明（报告表下方脚注） |
| `format_summary_value()` | 多窗口格式 `均值(W1/W2/W3/W4)`，缺失窗口显示 `-` |
| `format_grid_params()` | 网格参数格式 `[L,U]:gap%`，多窗口以 ` · ` 分隔 |
| `qualification_symbol()` | 枚举 → 符号（✓ ⚠ ✗ ?） |
| `render_summary_markdown()` | 渲染 Markdown 表 |
| `write_summary_markdown()` | 写 `table-b-summary.md` 副产物 |
| `write_comparison_csv()` | 写 CSV 载体，并在同目录自动生成 `table-b-summary.md` |

**同源约束**：报告表与 CSV 载体由**同一批行**渲染，列序、表头、格式无法漂移。
载体目录固定产出三个文件：

- `cells.csv`（表 A，逐 cell 明细）
- `cells-comparison.csv`（表 B 数据，机器可读枚举）
- `table-b-summary.md`（表 B 展示，符号化 + 脚注）

报告正文中的表 B 应直接引用 `table-b-summary.md` 的内容，不重抄。

### 表 B：合约汇总表（每个合约 一行；列集 = DESIGN §16.4 修订版，14 列）

| 列 | 含义 |
|---|---|
| `contract` | 合约标识 |
| `task_date` | 研究任务日（锚点当日；逐窗边界见表 A） |
| `margin_return_pct` / `sharpe` / `max_drawdown_pct` | 四窗口均值 + 逐窗口值 |
| `downward_liquidation_price` / `upward_liquidation_price` | 强平预估价格（MMR 来源分层，见「强平预估价格口径」；全部来源失败时 `N/A`） |
| `grid_params` | 逐窗口网格参数，格式 `[L,U]:g_pct%` 逗号串联（W1→W4）|
| `grid_count` | 网格数量 N，均值格式 `均值(W1/W2/W3/W4); n/4` |
| `amount_per_grid` | 平均每格挂单金额（USDT），平台成交流 `executions[].notional` 按格等权均值，均值格式同上 |
| `total_pairs` | 网格配对成交总次数（平台 `gridMatchedTradeCount`），均值格式同上 |
| `window_qualifications` | 逐窗口 qualification，格式 `Wn:枚举` 逗号串联（载体 CSV 保留机器可读枚举；报告展示用符号） |
| `qualification` | 资格判定（见下方枚举） |
| `qualification_reasons` | 风险警示原因（中文简述），按窗口 `Wn: 原因` 用分号 `;` 分隔；无警示时为 `N/A`。原因枚举：`杠杆超限(敞口/权益 X > 2.0)`、`回撤超限(X% > 35.0%)` |

**列序（2026-11-04 Pascal 确认的展示表为准，载体 CSV 与报告表必须同序）**：
合约 / 任务日 / 区间收益率% / MDD% / 网格参数[W1→W4] / 网格数量 / 平均每格金额(USDT) /
总配对次数 / Sharpe / 多头强平价 / 空头强平价 / 逐窗判定 / 合约判定 / 风险警示原因。

列序按「收益 → 风险 → 策略规格 → 风险调整指标 → 判定」分组阅读：
区间收益率与 MDD 相邻（收益与回撤同属结果解读），网格三列紧跟 MDD（策略规格），
Sharpe 置于其后（风险调整后的衍生指标）。

**报告展示符号**（Pascal 2026-11-04 裁定，报告表用符号、载体 CSV 保留枚举）：
`✓` = qualified（合格）；`⚠` = risk-breach（风险突破）；`✗` = failed；`?` = insufficient-evidence。
逐窗判定写作 `W1✓ W2⚠ W3✓ W4⚠`（W1→W4）。由 `qualification_symbol()` 统一映射，
枚举未覆盖时落 `?`，不得凭空猜测符号。

**已剔除的冗余列**（2026-11-04 Pascal 裁定）：`anchor_utc`（同 task_date）、
`L`/`U`/`g_pct`/`N`（几何已在 `grid_params` 与 `grid_count` 中）、
`metrics_caliber`（口径说明写在本节正文，不占数据列）。
`METRIC_COLUMNS` 冻结集不变，仅收窄导出行集。

### 多窗口指标格式（四窗口均值 + 逐窗口值）

每个多窗口指标单元格固定为：

```
<均值>(<W1值>/<W2值>/<W3值>/<W4值>); <有效窗口数>/4
```

例：`3.21(3.10/3.55/2.98/3.21); 4/4`

- 均值只对**有效窗口**取算术平均；缺失窗口在括号段保留其原值（N/A 或原因占位）
- 有效窗口数写明分母（`n/4`），缺失不得被静默剔除
- 只有一个有效窗口时均值=该值，但格式仍保留 `/4` 分母

### 平均每格金额口径

- 来源：平台回测产物 `executions[].notional`（成交名义金额），格号由 `client_order_id`
  的 `grid-<n>-` 前缀识别；无格号的订单（如手工单）不计入
- 聚合方式：**格等权** —— 先算每格的挂单金额均值，再对所有成交过的格取均值；
  成交次数多的格不因频次获得额外权重
- 单位 USDT，名义口径（含杠杆放大），非保证金占用
- 跨窗口按四窗口均值 + 逐窗口值展示，格式 `均值(W1/W2/W3/W4); n/4`
- 自洽校验：每格名义 ≈ 名义敞口预算 / N（本批为 10000 / N）

### 强平预估价格口径（2026-11-04 Pascal 裁定：极端单边市场压力测试）

- `downward_liquidation_price` = **单边下跌压力测试预估价**；`upward_liquidation_price` = **单边上涨压力测试预估价**。语义：假设从网格中线空仓状态出发，价格单边运动时网格逐线被动建仓（下跌逐线买入下半区多头格 / 上涨逐线开空上半区空头格），求解权益 ≤ 维持保证金的价格根。**不依赖回测成交与持仓数据**，输入仅为该 cell 冻结几何（L/U/N）+ 资金口径（E0、名义预算）+ MMR/费用
- **MMR 来源分层（优先级从高到低，不得跳序）**：
  1. **平台原生字段**（最高优先级）：`instrumentRulesSnapshot` 未来若带 MMR/强平费字段，直接使用，语义不变
  2. **Binance 公开接口**：`GET https://www.binance.com/bapi/futures/v1/friendly/future/common/brackets?symbol=<SYM>`（官网 Leverage & Margin 参数页同源端点，免签名免 key，curl 直连实测可用 2026-11-04）。取目标合约按持仓名义价值对应档位的 `bracketMaintenanceMarginRate`（含 `cumFastMaintenanceAmount` 速算数），必须记录接口 URL、档位表 `updateTime`、抓取时间并归档证据文件（样例：`data/reports/2026-11-03-neutral-grid-1h-four-window/evidence/binance-mmr-brackets-2026-11-04.md`，实测 JUP/PUMP/AAVE/SUI 第 1 档 MMR 均 1.00%）；档位表会调整，每次研究重新抓取，不复用历史快照数值
  3. **冻结默认梯度**（接口不可达时兜底：网络不通/超时/非 200/响应无 `riskBrackets`）：按持仓名义价值分档——名义 ≤ 20,000 USDT 用 MMR **1.0%**，> 20,000 USDT 用 MMR **1.5%**（对应 Binance 主流小币第 1/2 档实测结构）；使用时 `reason` 标 `default MMR tier (binance unreachable)` 并写入报告假设
- **强平费（close fee）**：与 MMR 同源取用；来源 2/3 均不提供时用 taker 费率 **0.05%**（显式披露），禁止静默置 0
- **旧快照口径废弃**（2026-11-04 Pascal 二次裁定后）：`liquidation_price_range()`/`cross_liquidation` 按 worst 持仓快照求解的历史口径已废弃，不再用于强平价两列；压力测试求解为唯一口径。快照伪影（多头簿负持仓）与压缩快照低估峰值（PUMP W4 54.49 vs 审计 64.77）仅作历史留档
- **worst_gross_to_equity 口径不变**：仍取平台 `grossExposure` 原值（runtime 已是 gross/value 比值），只用于风险判定（杠杆超限），与强平价压力口径分离

### 风险判定阈值（风险包络，判定参数标准）

逐 cell 资格判定用两个数值阈值，冻结在 `grid_research.py` 常量（`RISK_GROSS_TO_EQUITY_LIMIT` / `RISK_DRAWDOWN_LIMIT_PCT`），`cell_qualification()` 自动推导、不手填：

| 阈值 | 当前值 | 语义 |
|---|---|---|
| 敞口/权益（gross/equity） | **2.0**（2026-11-04 Pascal 裁定收紧，原 2.5；严格大于触发） | 窗口审计粒度 `worst_gross_to_equity` > 2.0 → 杠杆超限。分子是双侧名义绝对值之和（不得净额抵销），分母是含浮动盈亏的权益；与交易所 10x 授权上限是两个口径，这是研究风险包络 |
| 最大回撤 MDD | **35%**（严格大于触发） | 结果筛选，不是止损承诺 |

判定顺序：任一数值阈值触发即 `risk-breach`（两阈值"或"关系，原因分列）；指标缺失 → `insufficient-evidence`；作业失败 → `failed`。变更规则：阈值是研究标准语义，修改必须记录裁定人与日期（如本例"Pascal 2026-11-04 收紧 2.5→2.0"），判定属事后重算时回测数据不动，须在报告披露"事后重算、数据未变"；RFC/SPEC 契约文本同步修订另行批量处理。

### 资格判定枚举（qualification）

| 值 | 含义 |
|---|---|
| `qualified` | 全部窗口证据完整、指标齐全、风险约束未破 |
| （合约级判定） | 表 B 合约级 qualification 由窗口级传导：证据缺口先门禁（`insufficient-evidence`）；任一窗口 `failed` → `failed`；任一窗口 `risk-breach` → `risk-breach`；否则 `qualified`。强平价两列无论取值或 N/A，其占位原因**不参与**证据门禁 |
| `insufficient-evidence` | 存在缺证据/缺指标/缺 bar/乘数适用性未知/覆盖率预检不过 |
| `risk-breach` | 观测到风险约束突破（gross/equity > 2.0（2026-11-04 Pascal 裁定收紧，原 2.5）或 drawdown > 35%）。判定与原因由 `cell_qualification()` 从指标**自动推导**（不手填），合约级原因按窗口聚合、分号分隔 |
| `failed` | 执行失败（作业失败、数据不可得、窗口不可达） |

不得新增未定义值（含 `unknown`——占位行用 `insufficient-evidence`，状态缺失一律 `N/A`）。
N/A（未知/缺失）与 0（实测为零）严格区分：前者带原因，后者是有效观测值。

## 研究验收标准与角色分工（2026-11-04 Pascal 裁定）

研究类产出（表 A / 表 B / 载体 CSV / 报告正文）必须过独立验收。分工按**角色职责不同**划分，不为研究场景额外增加角色。

### 角色分工

| 角色 | profile | 职责 | 启用条件 |
|---|---|---|---|
| 实现 | `yquantdeveloper` | 按已冻结契约做最小实现、补测试 | 有代码改动 |
| 研究验收 | `yquanttester` | 独立重算对拍 + 载体同源核对（+ 口径/范围一致性，见下触发条件） | 研究类产出后**必过** |
| 契约复审 | `yquantreviewer` | 只审契约文档与实现/报告三处一致性、审 diff 范围、出通过/退回决定 | **仅**同时满足：改了 `docs/{rfc,spec,design}/` 三层契约 **且** 变更涉及交易/风控语义 |

研究验收归 Light Flow 的 Verify 阶段（单角色 tester），不另开 reviewer 卡。
独立性来自「实现者不是验证者」+「验证者不用实现者的算法」，**不来自角色数量**——同一数值用同法重算两次不构成额外独立性。纯数值研究（换合约/换窗口/加 cell）不触发 reviewer；阈值、展示口径、列序类调整也不触发。

### 验收检查项（3 项，判据必须可证伪）

| # | 检查 | 判据 | 触发条件 |
|---|---|---|---|
| 1 | **独立重算对拍** | 验证者**不使用实现的函数**，用另一条路径重算同一数值；相对差 ≤ 1e-9；判定类列 drift = 0/N | 始终 |
| 2 | **载体同源核对** | 表 A / 表 B / CSV / 正文逐值相等（数值 rel ≤ 1e-12、判定逐格相等、drift=0/N）；列序 == `TABLE_B_HEADERS`；脚注 == `TABLE_B_FOOTNOTES`；均值格须用 `format_summary_value` **重算后**比对，不得用字符串相等代替 | 始终 |
| 3 | **口径/范围一致性** | 实现常量与公式 ↔ SKILL/RFC 冻结条款逐条有代码行号对应；阈值在代码 / SKILL / 报告三处一致；diff 仅落在任务 allowlist 内，无 reset/stash/清理 | 口径、阈值、契约或公式语义变更时 |

原「首次穿越语义专项扫描」「档位固定点自洽」「正文残留扫描」「范围归属审计」等独立检查项**并入上表**：前两项并入第 1 项（扫描即重算的一种实现）、后两项并入第 2/3 项，不单列检查项、不单独计时。

**各场景的落地示例**（不新增检查项，只说明归属哪一项）：

| 场景 | 第 1 项（独立重算） | 第 3 项（口径/范围） |
|---|---|---|
| 网格进化 | 平台 `/api/backtest/get` 直读，逐 run 重算收益/MDD/G/E/破产与判定；按选择规则重算各候选合格窗数与胜者；执行几何用闭式解 + N 枚举双路径 | 选择规则、阈值、默认搜索范围、杠杆兜底档位：代码常量 ↔ 本 SKILL 条款；留出窗口未参与选择（runId 顺序 + 平台 plan 的 blind/fold 边界） |

验收任务书只写**本轮特有**内容：对拍基准数值与容差、证据路径、候选 sha256、本轮是否触发第 3 项。检查项、容差、纪律与结论格式一律引用本节，不在任务书或其他章节复述。

### 对拍基准生成规则

- 基准必须由**非实现者**预先独立算好，把**具体数值 + 容差**写进验收任务书；验收者只负责比对，不现算基准
- 基准必须**双路径交叉**（如闭式解 + 暴力扫描/网格逼近），不能只有一条——单条基准若本身有误，会与实现「一致地错」
- 基准与实现不一致时，先判定是「实现错」还是「基准错」，两者都可能；不得默认以实现为准

### 验收者纪律

1. **只读**：不改实现、不改断言、不重算覆盖已发布数值
2. **只报证据**：发现分歧只记录证据与期望/实际，不动手修（修复另起任务）
3. **指令与数学/验收标准冲突时否决指令并留证说明**——以验收标准为准，不以卡面修法为准

### 结论格式

```
结论：PASS / FAIL（二值）
证据：对拍结果一行 + 同源核对一行（命令 + 输出摘要）
未覆盖：一句话
```

存在未闭合的 FAIL / major 一律 FAIL；PASS = 第 1、2 项通过，且触发了第 3 项时第 3 项亦通过。

## 网格进化标准工作流（2026-11-05 Pascal 裁定）

网格策略的原生进化走**唯一标准化路径**，换合约只改参数、不改代码。本节是该路径的契约。

### 冻结约束（两个同时满足，任一不得单方面放宽）

| 约束 | 含义 | 常量位置 |
|---|---|---|
| gap ∈ [0.45%, 1.5%] | 网格间距（等比模式下的百分比间距） | `scripts/grid_evolution.py::GAP_MIN_PCT/GAP_MAX_PCT` |
| N ∈ [3, 200] | 网格格数 | `scripts/grid_evolution.py::GRID_MIN_COUNT/GRID_MAX_COUNT` |
| 等比（geometric）模式 | 格点按等比分布 | `scripts/grid_evolution.py::GRID_MODE` |

`scripts/grid_evolution.py` 是这两个约束的**唯一事实源**；策略源码生成器、研究脚本与验收都从它取常量，不得各自硬编码。

### 搜索维度

搜索空间固定三项：`grid_lower` / `grid_upper` / `grid_gap_pct`；格数由间距派生，不是搜索维度。`grid_gap_pct` 的采样域就是冻结业务带 [0.45, 1.5]；`grid_lower`/`grid_upper` 的采样区间**默认按固定规则生成**（见下条），确有需要时可用 `--lower-range` / `--upper-range` 覆盖，覆盖须在报告披露。

- **约束求解（间距优先）**：派生格数越出可行窗口时移动间距并披露（`exact` / `gap_raised_to_n_max` / `gap_lowered_to_n_min`），执行间距必落在 [0.45%, 1.5%]、格数必在 [3, 200]；禁止静默钳制。
- **搜索范围按固定规则生成，不人工判断**：默认取平台自己的规则「基准值 × [0.5, 1.5]」（`parameter_space._infer_numeric_range`），20 步。平台只有在 4 个验证折**全部**零成交时才剪枝，单折零成交不会剪掉整个 trial，所以不需要为"避免剪枝"去收窄 L。2026-11-05 曾把 L 上限人工压到 0.0016，结果把合格区域（L≈0.0019）排除在外。
- **平台不做风险约束**：排名就是 `score = oosReturn`；`weights` 只影响展示用的 qualityScore，驱动不传；`@constraint` 只能约束参数之间的关系，不能约束回测结果。G/E、MDD、破产只能在 G5 事后筛选。

### 标准资产

| 文件 | 职责 |
|---|---|
| `scripts/grid_evolution.py` | 约束唯一事实源：可行窗口、`resolve_from_gap`、数组构建、独立复核器 |
| `scripts/grid_evolve_source.py` | 契约无关的策略源码生成器 + 参数声明（`# @param` 与 parameter-space 同源） |
| `scripts/grid_evolve.py` | 标准 CLI（`describe` 干跑 / `run` 正式）：门禁、候选筛选规则、留出窗口 |
| `tests/test_grid_evolution.py` / `test_grid_evolve_source.py` / `test_grid_evolve.py` | 约束语义、生成器与运行时对拍、判定与选择规则 |

### 标准命令

```text
# 干跑（零网络）：基准几何、选择窗口、留出窗口、所需回测数
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/grid_evolve.py describe \
  --contract <SYM> --instrument "Crypto:<SYM>/USDT@swap" --lower <L> --upper <U> --gap-pct <G> \
  --evolve-start <YYYY-MM-DD> --evolve-end <YYYY-MM-DD> \
  --holdout-start <YYYY-MM-DD> --holdout-end <YYYY-MM-DD>

# 正式执行：把 describe 换成 run，并以环境变量注入 QUANTDINGER_JWT
# 可选：--lower-range/--upper-range <min:max:step>（默认基准 ×[0.5,1.5]，20 步）--trials 32 --top 5 --seed 42
#       --leverage 10 --fallback-leverages 8,6,4,3 --capital 1000 --budget 500 --evidence-dir <path>
#       --baseline-dir <基准载体 evidence 目录>（G7 同时写出进化 vs 基准对比表；G1 前校验目录/三载体/该合约行，无效则不发起任何平台调用）
```

进化区间必须是整季度；选择窗口按季度切分并从 W2 起编号（最近一季为 W2），留出窗口固定为 W1。平台把 `endDate` 当作包含当天（进化计划最后一根 K 线是 `evolve_end` 23:00），所以 `--holdout-start` 等于 `--evolve-end` 时会有 1 天重叠，驱动会告警；要彻底隔离，进化期结束日应设为留出期开始日的前一天。

### 流程门禁（任一失败立即停）

| 门禁 | 判据 |
|---|---|
| G1 编译 | 平台 compile 成功并创建私有源码 |
| G2 参数空间 | 恰为 `grid_lower/grid_upper/grid_gap_pct`，且平台读回的 min/max/step 与声明一致 |
| G3 参数生效 | 两个间距在最近选择窗口产生不同回测（收益或配对数不同） |
| G4 原生进化 | evolution job `succeeded`，取平台 top-N 作**候选**；`recommended` / `sampleSufficient` / 剪枝率原样记录 |
| G5 候选筛选 | 每个候选逐个跑全部选择窗口并判定，按下方规则选出胜者 |
| G5b 杠杆兜底 | 仅当 G5 无胜者：同一批候选按 `--fallback-leverages`（默认 8/6/4/3x）逐档降杠杆重判，首个出现胜者的档位即停；候选几何不变 |
| G6 留出检验 | 胜者以其档位杠杆只跑一次 W1，结果只报告，**不回头参与选择** |
| G7 载体生成 | 用胜者 W1（留出）+ W2–W4 已读回的 run 构造 cells（含 G/E、配对数、平均每格金额；强平价由 `grid_stress_liquidation.solve_cell` 按胜者几何求解），`grid_research.regen_carriers` 写出 `cells.csv`/`cells-comparison.csv`/`table-b-summary.md` 到 `--evidence-dir`（四个冻结合约沿用 4 合约载体；其他合约生成单合约载体：cells 4 行、表 B 1 行）；传 `--baseline-dir` 时再由 `compare_table_b` 写 `table-b-evolved-vs-baseline.md`。**不发起新回测**；无胜者时跳过并记录 `g7.skipped` |

### 判定与选择规则（Pascal 2026-11-05 冻结）

- **单窗 qualified**：G/E ≤ 2.0 且 MDD ≤ 35% 且指标齐全（严格大于才算超限；G/E 取 `equityCurve` 中 max |grossExposure|）。
- **候选入选**：qualified 窗口数 ≥ 选择窗口的 50%，且**任何窗口都没有破产**（平台回测 `liquidated=true`）。
- **胜者**：入选候选中选择窗口平均区间收益最高者；无入选者 → 报告「无合格候选」，不放宽约束。
- 平台分数只是候选生成器：`oosCompoundedReturn` 不惩罚破产（权益截断后仍可复利成高分），`robustnessGrade` / `blindPassed` 不得引用为质量证据。
- 极端单边压力测试强平价（`grid_stress_liquidation.py`）只计算并在表 B 披露，不作为候选筛选硬条件。

### 平台契约要点（各自有一次失败教训）

- `context.params` 只在可执行 handler 内可见，平台运行时不调用 `initialize` → 几何在 `handle_data` 开头重建。
- 重建条件只比较已应用参数签名 `(L, U, N)`；**禁止与重建后的浮点数组比较**——`L·exp(span/N·N)` 对约一半组合不逐位等于 U，曾导致每根 K 线都拆网格重置状态（配对 0 笔 vs 正常 1278 笔）。

- `# @param ... range=a:b:c` 只接受定点小数（正则 `-?\d+(\.\d+)?`）：`7.35e-05` 会被读成 `7.35`，整个维度静默坍缩成一个值，进化报 `parameterRangeOutsideDeclaration`。生成器统一输出定点格式，G2 读回比对。
- 平台沙箱的安全内置清单**没有 `getattr`**（compile 报 `strategyV2.apiCallInvalid:getattr:undefinedGlobal`）；跨 bar 状态用模块级全局变量（`global` 重绑定）。

### G/E 由网格下界决定，不由杠杆单独决定

单格名义 = 资金 × 杠杆 / N。价格在中线下方单边下跌时只有多头格成交，峰值敞口约等于「从高点跌到低点穿过的格子数 × 单格名义」。所以 G/E 主要由**下跌段落在网格内的对数跨度占 ln(U/L) 的比例**决定：L 设得高，价格跌破 L 后就不再买入，G/E 被封顶；U/L 越宽，单格越小。2026-11-05 PUMP 实测：同为 10x，L=0.0019 在 W2/W3/W5 的 G/E 为 0.86/1.54/1.45；L=0.0011–0.0013 在同样窗口为 2.1–5.0。

由此有一个取舍：`--lower-range` 压低，平台验证折更容易成交、剪枝更少；但 L 越低，单边下跌时接货越深，G/E 越高。设 `--lower-range` 时两头都要看，**不要只按"验证折不零成交"一个条件去压低 L 的上界**。

### 换合约复用清单

1. 取目标合约冻结基准几何 `L/U/gap`；搜索范围默认按固定规则（基准 ×[0.5, 1.5]，见「搜索维度」），不人工判断
2. `describe` 干跑，核对可行窗口、选择窗口与回测预算
3. `run` 正式执行；证据落 `data/reports/<YYYY-MM-DD>-<topic>/evidence/`
4. 表 A / 表 B 载体由 G7 自动生成（`grid_research.regen_carriers`），传 `--baseline-dir` 时同时生成进化 vs 基准对比表（`compare_table_b`）；不另造格式、不用一次性脚本拼表
5. 报告披露：请求与执行间距、调整类型、平台自报质量项、每个候选的逐窗判定、胜者与留出结果
6. 研究验收：按「研究验收标准与角色分工」执行；本轮改了选择规则、阈值或搜索范围规则时触发第 3 项

## 安全边界

- 凭据仅经进程环境注入：`QUANTDINGER_BASE_URL`（无 /api 后缀）、`QUANTDINGER_JWT`（Human）、
  `QUANTDINGER_AGENT_TOKEN`（Agent）。唯一例外（V1.5，用户批准的最小边界）：Agent 令牌缺失时只读
  `skills/.env` 中且仅 `QUANT_DINGER_AI_AGENT_TOKEN_MYMQUANT` 一个键。不登录、不签 token、
  不回写 .env、不读其他键或整文、不收集浏览器存储；401/403 一次即停，不换 token 绕过。
- HTTP 仅限 CLI 内冻结的 operation 白名单（Design §3.3 表 + 行情两个只读端点）；
  无任意 path/method 透传。禁止 Quick Trade 下单、deployments、credentials、billing、
  `/api/auth/login`、源码 publish/update/delete 等调用路径。
- 策略源码中的 `order_target_percent` 只在平台历史回测沙箱执行，不构成真实下单授权；
  首版交易闭环固定 Human JWT，缺 JWT 如实阻塞，不 mock 替代。
- 报告只存明确业务字段，丢弃 headers/token/password 样式字段；不含凭据、账户或原始 HTTP 响应。
- 研究类在证据不足时必须 fail closed：退出码 3、零业务请求、不产出完成报告；离线自检通过不等于独立 Verify/Review。
- 杠杆请求后必须读回核对：回执 `executionAssumptions` 与请求不一致时按契约失败处理（不得静默放行、
  不得改写请求或用请求值覆盖回执）；回执字段缺失或不可读时按证据不足处理，不得默认判通过、不得用
  请求参数回填回执值。
- 不修改 QuantDinger 子模块、不改部署/配置、不做 Demo/Live 与调度；提交/推送须经 Pascal 授权。

## 维护提示：脚本已达拆分阈值

`scripts/quantdinger.py` 在 V1.5 Agent 增量后已超过 DESIGN §8.9 的 ≤2310 预估、并越过 2400 行
拆分阈值（触发条件①）。拆分（优先 `agent_client.py` 信封/幂等/白名单 与 `judgment.py` 判定）
属独立任务，需先出拆分 Design 并交独立 Review。**后续任何实质扩展前必须先完成拆分**，
不得继续在同一文件叠加能力。

## 状态

- 2026-10-30 首版完成：独立方案C Design Gate run3359 APPROVE；T4独立复验 run3362 PASS，48/48测试、A-001~A-009最终矩阵全部通过；原T4卡已关闭。
- T5原卡 t_6346409a 的完整审查 run3369 发现一项摘要精度Minor，修正后由 reviewer run3371 限定复核，最终 full_verdict=APPROVE、open_findings=0；历史REVISE与流程偏离保留，不追认。
- 真实交易样例已完成私有源码、回测、原生进化、最终回测及平台UI核验；研究样例已完成两次真实取数与复算。以上指接入样例，不表示用户PUMP/HYPE/JUP合约网格已实现，也不表示实盘可用或盈利保证。
- 正式证据：[T4验证报告](../../../data/reports/2026-10-29-strategy-lab-verify/report.md)、[T5签收报告（最终第6节）](../../../data/reports/2026-10-30-strategy-lab-final-review/report.md)。报告位于Git忽略的本地data目录，不代表已提交、推送或远程备份。
- 2026-10-31 Agent 通道 V1.5 完成：T4 真实四步验收 PASS（whoami/行情/compile/backtest，runId=25）、T5 独立审查 APPROVE（open_findings=0）、T6 Closeout PASS（[closeout.md](../../../data/reports/2026-10-30-strategy-lab-agent-token/closeout.md)）。六卡全 done，工程线收口。
- 2026-10-31 行情取数契约实测沉淀（见上方「行情取数契约」节）：CLI 分页上限 500、`--max-pages 2` 纪律、本机 gate.io 直连 env 口径。
- 2026-11-05/06 PUMP W2–W5 v2 网格进化完成（胜者 #5，W1 留出 +56.32% / MDD -16.94% ✓，合格窗 2/4），tester 验收 PASS（`t_427dd408`）；报告 [2026-11-05-pump-evolve-w2w5-v2](../../../data/reports/2026-11-05-pump-evolve-w2w5-v2/report.md)。2026-11-06 起表 A/B 载体与对比表由驱动 G7 自动生成。
- 2026-11-01 起的具体研究任务记录见 `data/tasks/active/2026-11-01-grid-g01-g02/` 与实例 `strategies/neutral-grid-four-window-v1/README.md`——本平台的一次具体研究任务记录，非平台契约。
- 此处仅同步已验收状态，不改变业务契约、代码、样例参数或原始证据；未执行Demo/Live、发单、部署、调度或生产配置变更。
