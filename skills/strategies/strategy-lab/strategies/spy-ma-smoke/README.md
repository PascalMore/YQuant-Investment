# spy-ma-smoke

Strategy Lab 首版交易接入样例：用 QuantDinger 原生模板 `strategy_v2_single_ma` 在 SPY 上验证
「保存私有源码 → 基准回测 → 一次有界原生进化 → 候选/基准判定 → 最终回测」闭环。

不承诺盈利；本目录只验证接入与判定链路。

当前冻结契约为 [DESIGN-06-001 V1.4 §5.1](../../../../../docs/design/06_strategy/DESIGN-06-001-strategy-lab.md)
及本目录 `spec.md`（2026-10-30方案C）：窗口仅延长至2017-06-01..2025-12-31，
warmup260、folds4、源码/算法/搜索空间/成本/硬约束不变；待独立Gate与真实验证。

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

下方命令不是可任意重跑的授权。独立方案C Design Gate完成前不执行业务；主控开始前须只读核查
新窗口已有job，存在则只读回、禁止重复创建。Pascal仅为该修订窗口一次性额外授权最多1个
新原生进化job；每轮内部回放/relativeUnits≤8、外层持久化回测jobs≤8（预计最多6）、参数组
含基准≤5、墙钟1200s、零新增付费不变；失败/取消/超预算立即停，不自动重试，提交结果未知不重发。

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py trade --strategy-dir skills/strategies/strategy-lab/strategies/spy-ma-smoke --start 2017-06-01 --end 2025-12-31 --capital 10000 --commission 0.0005 --slippage 0.0005 --search ma_period:20:80:20 --objective totalReturn --max-drawdown-pct 50 --method grid --trials 4 --folds 4 --max-evolution-runs 8 --max-relative-units 8 --wall-seconds 1200
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

- 旧2023-01-01..2025-12-31窗口已superseded：历史基准run19成功、进化job
  `d249d4846e8e493b8d0d316b340f99de` failed（observationRangeTooShort）分列保留，不重试旧job，
  不重写旧reports/命令。新窗口job须另列，旧基准不作新窗口同口径证据；通用每次恰好一次进化
  规则不变，不把本次额外授权变成普遍2次额度。
- Design §5.1所引真实预检：日末2159条/午夜2158条经原生拆分均有效4折。变更窗口须用
  真实观测与原生拆分核验四折，自然日或estimate.folds不作通过证据；公开预检不保证evaluator
  快照相同，实际job仍须核对四折、覆盖与成本。actualBacktestRuns=None表示未报告，不代表0。
- 本次仅文档同步、未真实重跑；沿用现有T4/T5，不代表T4/T5通过，不改CLI/测试或平台。

- 硬约束的全段 MDD 使用原生全段读回 run 的 `data.result.maxDrawdown`（峰值净值口径），
  不使用进化 `summary.maxDrawdown`（validation 折绝对值均值，不含 blind）。
- 原生 fold 是单次回放后按时间切片，不是逐折重训；最终全段复检已包含 blind，
  因此选定参数不再声称存在完全未触碰的独立留出集。
- `executionAssumptions.fundingMode=not_modeled` 必须披露；对无融资的 SPY 现货该资金费项不适用，
  但不因此声称三币合约的敞口/强平限额已落实。
- 硬约束 50% 是判合格阈值，不是运行时保证。
