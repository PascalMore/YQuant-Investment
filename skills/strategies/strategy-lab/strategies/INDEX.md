# Strategy Lab 实例索引

本索引登记 `skills/strategies/strategy-lab/strategies/` 下的全部策略/研究实例，服务于「先查再研」：
只登记实例状态、结论摘要与证据路径，不复制报告正文、不新增指标、不重新评价。

生成日期：2026-11-02（Asia/Shanghai UTC+08:00）。实例数量以本目录下实际子目录为准（15 个）。

| 实例 id | 类型 | 状态 | 结论一句话 | 报告/证据路径 |
|---|---|---|---|---|
| `spy-close-research` | 研究类 | 已完成 | 平台真实取数两次重跑结果一致：2024 年 SPY 日收益均值 0.000889、样本标准差 0.007934、年化波动率 0.1259，样本 252 根日线。 | `strategies/spy-close-research/reports/report.md`（附 `reports/replay-check.md`、`reports/latest.csv`） |
| `spy-ma-smoke` | 交易类 | 已完成 | 真实闭环跑通并选定进化候选 `ma_period=80`：全段总收益 +103.53%、年化 +8.63%、最大回撤 −16.65%、夏普 0.83（基准 run20 → 最终 run24，MDD≤50% 硬约束合格）。 | `strategies/spy-ma-smoke/reports/report.md`（附 `reports/comparison.csv`、`reports/agent-backtest.md`） |
| `neutral-grid-four-window-v1` | 研究类 | 未执行 | — | — |
| `neutral-grid-aaveusdt` | 研究类 | 已完成 | 平台原生网格回测跑通：总收益 +13.01%、年化 +13.10%、最大回撤 −9.34%、夏普 1.36，549 笔成交，相对基准信息比率 0.38。 | `strategies/neutral-grid-aaveusdt/reports/agent-backtest.md` |
| `neutral-grid-aaveusdt-5m` | 研究类 | 未执行 | — | — |
| `neutral-grid-aaveusdt-15m` | 研究类 | 未执行 | — | — |
| `neutral-grid-jupusdt` | 研究类 | 已完成 | 平台原生网格回测跑通：总收益 +18.99%、年化 +19.12%、最大回撤 −5.86%、夏普 1.63，608 笔成交，相对基准信息比率 0.23。 | `strategies/neutral-grid-jupusdt/reports/agent-backtest.md` |
| `neutral-grid-jupusdt-5m` | 研究类 | 未执行 | — | — |
| `neutral-grid-jupusdt-15m` | 研究类 | 已完成 | 15m 驱动、初始资金 1000 USDT 的平台回测：窗口内总收益 +11.03%、年化 +52.03%、最大回撤 −4.02%、夏普 3.46，610 笔成交；基准历史不足，未给出信息比率。 | `strategies/neutral-grid-jupusdt-15m/reports/agent-backtest.md` |
| `neutral-grid-pumpusdt` | 研究类 | 已完成 | 平台原生网格回测跑通：总收益 +16.71%、年化 +16.83%、最大回撤 −7.35%、夏普 1.27，715 笔成交；标的基准同期年化 +62.94%，信息比率 −0.40。 | `strategies/neutral-grid-pumpusdt/reports/agent-backtest.md` |
| `neutral-grid-pumpusdt-5m` | 研究类 | 未执行 | — | — |
| `neutral-grid-pumpusdt-15m` | 研究类 | 未执行 | — | — |
| `neutral-grid-suiusdt` | 研究类 | 已完成 | 平台原生网格回测跑通：总收益 +9.34%、年化 +9.40%、最大回撤 −8.99%、夏普 0.73，538 笔成交，相对基准信息比率 0.92。 | `strategies/neutral-grid-suiusdt/reports/agent-backtest.md` |
| `neutral-grid-suiusdt-5m` | 研究类 | 未执行 | — | — |
| `neutral-grid-suiusdt-15m` | 研究类 | 已完成 | 15m 驱动、初始资金 10000 USDT 的平台回测：窗口内总收益 +2.96%、年化 +12.39%、最大回撤 −4.18%、夏普 1.22，452 笔成交，相对基准信息比率 −1.55。 | `strategies/neutral-grid-suiusdt-15m/reports/agent-backtest.md` |

说明：

1. 状态三值口径：`已完成` = 实例目录内存在真实运行报告且其结论可按该报告复现；`未执行` = 实例目录内无报告文件（目录、`spec.md` 或 `config.json` 齐备不等于已执行）；`已被替代` = 已被同族新实例或新契约明确取代（当前无适用实例）。
2. `未执行` 仅指本实例目录内无报告文件；部分实例的历史回测原始证据只保存在 `data/reports/` 下，未登记为实例结论，需要时按该证据目录另行核对；表中数字一律取实例自身报告，聚合报告口径若有差异以实例报告为准。
3. 本索引只登记结论摘要与证据路径，不复制报告内容、不新增指标、不重新评价；各实例的需求、参数与验收口径以各自 `spec.md` 及其引用的 SPEC/Design 为准。
4. 表内路径基准为 `skills/strategies/strategy-lab/`，即 `strategies/<id>/reports/...` 自该基准目录解析。
