# spy-close-research 策略/研究需求

> 研究类样例。按 [DESIGN-06-001 §5.2](../../../../../docs/design/06_strategy/DESIGN-06-001-strategy-lab.md) 冻结，
> 只做统计，不输出模拟交易或伪造平台研究条目。

## 目标

- 原始想法：给出 2024 年 SPY 日收盘的日收益均值、日收益标准差、年化波动率与窗口首末收盘变化。
- 类型与目标：研究类；产出一份可复算的统计结果与数据来源标注。
- 假设或待澄清项：无。窗口、方法、预算已冻结。

## 数据、规则与参数

- 标的与数据：USStock / SPY / 1D。数据来源为 QuantDinger 平台实际 endpoint：
  优先显式 Human `/api/indicator/kline`；可由已签发 R token 时显式选 Agent `/api/agent/v1/klines`。
  源码未透传实际上游供应商，来源写「QuantDinger <实际 endpoint>，底层供应商未由接口披露」，不冒称某供应商。
- 方法/规则：
  - 分页游标取 `2025-01-01T00:00:00Z` 的 unix 秒，从 end 向前翻页；Human 每页 ≤1000，Agent 每页 ≤2000。
  - 返回 time 解析为 UTC，按请求窗口过滤、去重、升序；下一页游标用最早 time 严格递减，重复/无进展即停。
  - 日收益 = 连续交易日 close 比值减 1；均值 = 算术平均；标准差 = 样本标准差（ddof=1）；
    年化波动率 = 样本标准差 × sqrt(252)。三项均在报告注明定义。
- 参数与约束：窗口固定 2024-01-01..2024-12-31；至少 200 条有效日线，`close>0`，OHLC 有限且
  `high≥max(open,close,low)`、`low≤min(open,close,high)`、`volume≥0`；周末/节假日不视为缺口，
  首末交易日期与任何缺失列明，不补虚假 bar。
- QuantDinger 复用：平台行情接口。缺口如实列明：无。
- 自动进化设置：研究类不适用，不调用任何进化或回测接口。

## 输出与验收

- 输出：`reports/latest.csv`（标准化真实窗口 OHLCV，不写提取时间）与 `reports/report.md`
  （统计、来源、时间、限制、复现命令及重跑说明）。
- 验收：两次运行都真实取数，每次 ≤4 个数据请求、≤180s，两次合计 ≤8 次；第二次不得用第一次 CSV 冒充接入。
  两次退出 0、数据行与派生指标一致（允许报告提取时间不同）；若平台事后数据修订导致差异，记录真实差异及原因，
  不得伪装一致。
- 进化判定：不适用。
- 平台可查：不强行伪造平台研究条目。
- 再次执行：见下方命令。

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/spy-close-research/research.py --data-api human
```

## 实现边界

- 允许文件：本目录与 `skills/strategies/strategy-lab/scripts/quantdinger.py`。
- 计算预算：单次运行 ≤4 个数据请求、≤180s；两次合计 ≤8 个请求。
- 结果保留：`reports/latest.csv` 与 `reports/report.md` 保留最新一次；不建 runs/version/manifest。
- 禁止：Demo/Live、凭据绑定、付费能力、长期调度、生产配置变更；不得在失败后悄悄改用 fixture 数据。
