# spy-close-research replay-check（独立 Verify 记录）

- 时间：2026-10-29 23:47-23:53（Asia/Shanghai UTC+08:00），由 yquanttester 独立执行。
- 解释器：/home/pascal/workspace/yquant-investment/.venv/bin/python（Python 3.12.13）。
- QUANTDINGER_BASE_URL=http://127.0.0.1:15000（本轮显式传入；Human 只读公开行情端点，无需 JWT）。

## 两次真实执行命令与退出码

第 1 次：
```text
QUANTDINGER_BASE_URL=http://127.0.0.1:15000 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/spy-close-research/research.py --data-api human
```
- exit 0；输出 rows=252, meanDailyReturn=0.0008887548064189286, stdDailyReturn=0.0079338365858408, annualizedVolatility=0.12594575129256305, first=2024-01-02T14:30:00Z, last=2024-12-31T14:30:00Z。

第 2 次（同命令）：exit 0；上述全部数值与首次逐位一致（允许的报告提取时间字段除外）。

## 一致性与数据身份

- latest.csv sha256：2cb7fac4dba4c48037a9357750ddb0a9b40a93413555bdfd6172b16a9503028e。
- 数据行数：252（≥200 下限满足；周末/节假日按契约不计为缺口）。
- Tester 独立复算（scratch/verify_replay.py，非复用脚本输出）：mean=0.0008887548064189286、std(ddof1)=0.0079338365858408、年化波动=0.12594575129256305，与两次运行及 report.md 一致。
- OHLC 有效性：invalid_bars=0；time 升序且唯一=通过；close>0、volume≥0 全部满足。
- 窗口核对：请求 2024-01-01..2024-12-31，实际首末为 2024-01-02 / 2024-12-31 14:30 UTC（美股交易日语义，符合预期）。

## 结论

replay-check = PASS。两次真实取数（非缓存复用），派生指标完全一致，CSV 校验值在案。
