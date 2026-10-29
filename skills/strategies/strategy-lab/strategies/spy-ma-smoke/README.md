# spy-ma-smoke

Strategy Lab 首版交易接入样例：用 QuantDinger 原生模板 `strategy_v2_single_ma` 在 SPY 上验证
「保存私有源码 → 基准回测 → 一次有界原生进化 → 候选/基准判定 → 最终回测」闭环。

不承诺盈利；本目录只验证接入与判定链路。

本目录是 `skills/strategies/strategy-lab/strategies/` 下的策略实例（2026-10-30 由
`strategy-lab/spy-ma-smoke/` 迁入 `strategy-lab/strategies/spy-ma-smoke/`）；
`strategy-lab/` 根层只保留研发工具（SKILL、README、CLI、templates、tests），
具体实例统一放其 `strategies/` 子目录。

## 目录

- `spec.md`：冻结的需求、参数语义、硬约束与预算。
- `config.json`：`ma_period`、`target_pct` 的实际数值（语义在 spec）。
- `strategy.py`：官方模板 `strategy_v2_single_ma` 的原生 Strategy API V2 源码，由平台沙箱执行，
  不在本地 import 或运行。
- `reports/report.md`、`reports/comparison.csv`：由 `strategy-lab/scripts/quantdinger.py trade` 实际执行生成。

## 执行

凭据由主控经既有安全机制注入进程环境（`QUANTDINGER_BASE_URL`、`QUANTDINGER_JWT`），
本目录不保存任何凭据或平台 ID。

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py trade --strategy-dir skills/strategies/strategy-lab/strategies/spy-ma-smoke --start 2023-01-01 --end 2025-12-31 --capital 10000 --commission 0.0005 --slippage 0.0005 --search ma_period:20:80:20 --objective totalReturn --max-drawdown-pct 50 --method grid --trials 4 --folds 4 --max-evolution-runs 8 --max-relative-units 8 --wall-seconds 1200
```

退出码：`0` 正常业务结果（含 skipped / no-qualified）、`2` 平台或契约失败、`3` 证据不足、
`4` 认证缺失或 401/403、`5` 预算或超时、`64` 参数或本地路径错误。

## 平台 ID 与 UI 查询

执行成功后 `reports/report.md` 记录 `sourceId`、`baselineRunId`、`finalRunId`、`evolutionJobId`。
在 QuantDinger Web 端按下列路径实查（只查询，不点击"应用并保存版本"或部署）：

- 策略源码：`/strategy-ide?sourceId=<sourceId>`
- 回测与指标：`/backtest-center?sourceId=<sourceId>`（在原生历史列表中打开目标 run）
- 进化终态：回测中心内的「策略进化」tab，选择同一 source 后查找本轮 job

当前页面不保证 `?runId=` 深链定位，需在列表中选择目标 run。UI 实查由 Verify 阶段留证
（`reports/ui-check.md`），不能用 API 读回推导页面已显示。

## 已知限制

- 硬约束的全段 MDD 使用原生全段读回 run 的 `data.result.maxDrawdown`（峰值净值口径），
  不使用进化 `summary.maxDrawdown`（validation 折绝对值均值，不含 blind）。
- 原生 fold 是单次回放后按时间切片，不是逐折重训；最终全段复检已包含 blind，
  因此选定参数不再声称存在完全未触碰的独立留出集。
- `executionAssumptions.fundingMode=not_modeled` 必须披露；对无融资的 SPY 现货该资金费项不适用，
  但不因此声称三币合约的敞口/强平限额已落实。
- 硬约束 50% 是判合格阈值，不是运行时保证。
