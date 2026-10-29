# spy-ma-smoke 策略/研究需求

> 交易类样例。按 [DESIGN-06-001 §5.1](../../../../../docs/design/06_strategy/DESIGN-06-001-strategy-lab.md) 冻结，用于验证首版 QuantDinger 接入闭环，不是投资推荐。

## 目标

- 原始想法：验证 AI 能用 QuantDinger 原生模板跑通「私有源码 → 基准回测 → 一次有界原生进化 → 判定 → 最终回测」闭环。
- 类型与目标：交易类；得到一个可读回、可在 UI 查询的源码与回测结论（不保证盈利）。
- 假设或待澄清项：无。标的、窗口、成本、硬约束与预算已由 Design §5.1 冻结。

## 数据、规则与参数

- 标的与数据：USStock / SPY / 1d，long_only，warmup 260 根；原生模板 `strategy_v2_single_ma`，基准为 SPY 自身。窗口 2023-01-01 至 2025-12-31（UTC 日期边界，美股交易日语义；报告须注明使用美股日历）。
- 方法/规则：价格站上均线且无持仓时按 `target_pct` 目标仓位做多；价格跌破均线且有持仓时清仓。
- 参数与约束（`config.json`）：`ma_period=50`（int）、`target_pct=0.95`（percent）。`ma_period` 参与搜索；`target_pct` 固定为 min=max 单行传入，值与源码默认一致。
- QuantDinger 复用：原生模板源码、Strategy API V2 compile/create/detail、原生回测 job、原生 Strategy Evolution。缺口如实列明：无。
- 自动进化设置：
  - 触发条件：存在已声明且源码实际消费的可调参数、有选优目标、预算允许、用户未禁止。
  - 搜索空间：`ma_period` 20..80 step 20（4 个点）；`target_pct` 固定 0.95。
  - 进化 config：`method=grid`、`trials=4`、`folds=4`、`trainRatio=0.7`、`blindRatio=0.15`、`seed=42`、`costMultipliers=[1,2]`、`autoPrune=false`、`monteCarloPaths=100`、`topCandidates=4`。
  - 硬约束：真实市场数据；SPY 无杠杆股票身份；同窗口同成本；`totalReturn`/`sharpeRatio`/`maxDrawdown` 均为有限值；原生 `totalExecutions>0`；全段峰值口径 `maxDrawdown` 绝对值 ≤ 50%。
  - 比较目标：合格项中全段 `totalReturn` 最大者。50% 是约束阈值，不是运行时保证。

## 输出与验收

- 输出：`reports/report.md`（基准/候选/结论、平台 ID、参数、限制、预算、复现命令）与 `reports/comparison.csv`（每行 runId/参数/合格状态/原因）。
- 验收：判定必须落在六分支之一；硬约束只用原生全段读回 run 的 `data.result.maxDrawdown`；原生 `summary.maxDrawdown`（validation 折绝对值均值）另列，不作硬约束。
- 进化判定：基准合格且候选不更优 → 保留基准；基准不合格但候选合格 → 选候选；均不合格 → 无合格候选；关键证据未知 → 证据不足；run failed/cancelled/超预算 → 如实停止并记录诊断。不重试、不改窗口/成本/硬约束以求通过。
- 平台可查：私有 source 需保存并读回（`visibility=private`、`status=draft`、源码一致）；基准/候选/最终 run 需在 `/backtest-center?sourceId=<sourceId>` 可见（由 Verify 阶段页面实查留证）。
- 再次执行：见下方命令，凭据由主控经既有安全机制注入进程环境。

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py trade --strategy-dir skills/strategies/strategy-lab/strategies/spy-ma-smoke --start 2023-01-01 --end 2025-12-31 --capital 10000 --commission 0.0005 --slippage 0.0005 --search ma_period:20:80:20 --objective totalReturn --max-drawdown-pct 50 --method grid --trials 4 --folds 4 --max-evolution-runs 8 --max-relative-units 8 --wall-seconds 1200
```

## 实现边界

- 允许文件：`skills/strategies/strategy-lab/strategies/spy-ma-smoke/`（本样例目录）与 `skills/strategies/strategy-lab/scripts/quantdinger.py`；不得修改 QuantDinger 子模块。
- 计算预算：内部 estimate/actual ≤ 8、relativeUnits ≤ 8、外层持久化回测 job ≤ 8（本样例预计 ≤ 6）、全段复检参数组 ≤ 5、进化 run 恰好 1 次、总墙钟 1200s、单回测 job ≤ 180s、进化 job ≤ 600s、轮询 15s、0 新增付费。
- 结果保留：`reports/` 最新结果即可；不建 runs/version/manifest。
- 禁止：Demo/Live、凭据绑定、实盘发单、付费能力、长期调度、修改生产配置。资金费/强平/gross exposure 等未建模项必须披露，不得默认可通过。
