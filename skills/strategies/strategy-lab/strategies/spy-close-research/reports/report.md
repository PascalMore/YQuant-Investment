# spy-close-research 报告

- extractedAt (Asia/Shanghai): 2026-10-29T23:52:10+0800
- dataApi: human
- endpoint: QuantDinger /api/indicator/kline（底层供应商未由该接口披露）
- market/symbol/timeframe: USStock/SPY/1D
- requestedWindow: 2024-01-01 .. 2024-12-31（UTC 日期边界，美股交易日）
- actualFirstTimeUtc: 2024-01-02T14:30:00Z
- actualLastTimeUtc: 2024-12-31T14:30:00Z
- sampleCount: 252（最小要求 200）

## 统计口径

- 日收益 = 连续交易日 close 比值减 1。
- 均值 = 算术平均；标准差 = 样本标准差（ddof=1）。
- 年化波动率 = 样本标准差 × sqrt(252)。

## 指标

- meanDailyReturn: 0.0008887548
- stdDailyReturn: 0.0079338366
- annualizedVolatility: 0.1259457513
- firstClose: 472.649994
- lastClose: 586.080017
- closeChangePct: 23.998736

## 限制

- 平台未在接口层披露底层数据供应商，来源只写 QuantDinger 实际 endpoint。
- 周末与节假日不构成数据缺口；首末为实际交易日期，未补任何虚拟 bar。
- 数据为平台缓存/历史序列，不代表实时成交。
- 本研究不含任何交易、参数优化或平台研究条目。
- latest.csv 不写提取时间，便于两次运行直接比对。

## 复现

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/spy-close-research/research.py --data-api human
```
