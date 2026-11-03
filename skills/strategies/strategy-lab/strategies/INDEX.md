# Strategy Lab 实例索引

本索引登记 `skills/strategies/strategy-lab/strategies/` 下的全部策略/研究实例，服务于「先查再研」：
只登记实例状态、结论摘要与证据路径，不复制报告正文、不新增指标、不重新评价。

生成日期：2026-11-02（Asia/Shanghai UTC+08:00）。实例数量以本目录下实际子目录为准（15 个）。

| 实例 id | 类型 | 状态 | 结论一句话 | 报告/证据路径 | Path B 口径（10x） |
|---|---|---|---|---|---|
| `spy-close-research` | 研究类 | 已完成 | 平台真实取数两次重跑结果一致：2024 年 SPY 日收益均值 0.000889、样本标准差 0.007934、年化波动率 0.1259，样本 252 根日线。 | `strategies/spy-close-research/reports/report.md`（附 `reports/replay-check.md`、`reports/latest.csv`） | — |
| `spy-ma-smoke` | 交易类 | 已完成 | 真实闭环跑通并选定进化候选 `ma_period=80`：全段总收益 +103.53%、年化 +8.63%、最大回撤 −16.65%、夏普 0.83（基准 run20 → 最终 run24，MDD≤50% 硬约束合格）。 | `strategies/spy-ma-smoke/reports/report.md`（附 `reports/comparison.csv`、`reports/agent-backtest.md`） | — |
| `neutral-grid-four-window-v1` | 研究类 | 未执行 | — | — | — |
| `neutral-grid-aaveusdt` | 研究类 | 已完成 | 平台原生网格回测跑通：总收益 +13.01%、年化 +13.10%、最大回撤 −9.34%、夏普 1.36，549 笔成交，相对基准信息比率 0.38。 | `strategies/neutral-grid-aaveusdt/reports/agent-backtest.md` | +130.13% / MDD −63.17% ｜ 离线折算 |
| `neutral-grid-aaveusdt-5m` | 研究类 | 未执行 | — | — | — |
| `neutral-grid-aaveusdt-15m` | 研究类 | 未执行 | — | — | — |
| `neutral-grid-jupusdt` | 研究类 | 已完成 | 平台原生网格回测跑通：总收益 +18.99%、年化 +19.12%、最大回撤 −5.86%、夏普 1.63，608 笔成交，相对基准信息比率 0.23。 | `strategies/neutral-grid-jupusdt/reports/agent-backtest.md` | +189.94% / MDD −33.73% ｜ 离线折算 |
| `neutral-grid-jupusdt-5m` | 研究类 | 未执行 | — | — | — |
| `neutral-grid-jupusdt-15m` | 研究类 | 已完成 | 15m 驱动、初始资金 1000 USDT 的平台回测：窗口内总收益 +11.03%、年化 +52.03%、最大回撤 −4.02%、夏普 3.46，610 笔成交；基准历史不足，未给出信息比率。 | `strategies/neutral-grid-jupusdt-15m/reports/agent-backtest.md` | +110.53% / MDD −23.90% / 夏普 3.79 ｜ **原生实测 runId=40** |
| `neutral-grid-pumpusdt` | 研究类 | 已完成 | 平台原生网格回测跑通：总收益 +16.71%、年化 +16.83%、最大回撤 −7.35%、夏普 1.27，715 笔成交；标的基准同期年化 +62.94%，信息比率 −0.40。 | `strategies/neutral-grid-pumpusdt/reports/agent-backtest.md` | +167.07% / MDD −51.78% ｜ 原生实测 runId=39 |
| `neutral-grid-pumpusdt-5m` | 研究类 | 未执行 | — | — | — |
| `neutral-grid-pumpusdt-15m` | 研究类 | 未执行 | — | — | — |
| `neutral-grid-suiusdt` | 研究类 | 已完成 | 平台原生网格回测跑通：总收益 +9.34%、年化 +9.40%、最大回撤 −8.99%、夏普 0.73，538 笔成交，相对基准信息比率 0.92。 | `strategies/neutral-grid-suiusdt/reports/agent-backtest.md` | +93.38% / MDD −55.78% ｜ 离线折算 |
| `neutral-grid-suiusdt-5m` | 研究类 | 未执行 | — | — | — |
| `neutral-grid-suiusdt-15m` | 研究类 | 已完成 | 15m 驱动、初始资金 10000 USDT 的平台回测：窗口内总收益 +2.96%、年化 +12.39%、最大回撤 −4.18%、夏普 1.22，452 笔成交，相对基准信息比率 −1.55。 | `strategies/neutral-grid-suiusdt-15m/reports/agent-backtest.md` | +29.61% / MDD −28.37% ｜ 离线折算 |

说明：

1. 状态三值口径：`已完成` = 实例目录内存在真实运行报告且其结论可按该报告复现；`未执行` = 实例目录内无报告文件（目录、`spec.md` 或 `config.json` 齐备不等于已执行）；`已被替代` = 已被同族新实例或新契约明确取代（当前无适用实例）。
2. `未执行` 仅指本实例目录内无报告文件；部分实例的历史回测原始证据只保存在 `data/reports/` 下，未登记为实例结论，需要时按该证据目录另行核对；表中数字一律取实例自身报告，聚合报告口径若有差异以实例报告为准。
3. 本索引只登记结论摘要与证据路径，不复制报告内容、不新增指标、不重新评价；各实例的需求、参数与验收口径以各自 `spec.md` 及其引用的 SPEC/Design 为准。
4. 表内路径基准为 `skills/strategies/strategy-lab/`，即 `strategies/<id>/reports/...` 自该基准目录解析。
5. 「Path B 口径（10x）」列是**独立杠杆口径**的登记，不覆盖原 1x 结论：1x 结论（收益、回撤、成交数）本身有效且继续有效，Path B 只是同策略在保证金 1000 USDT、交易所杠杆 10x、名义敞口预算 10000 USDT 下的另一组数字。证据等级分两类：**原生实测**＝平台真实以 `leverageEnabled=true / leverage=10` 提交并读回断言通过的回测（当前 `neutral-grid-pumpusdt` runId=39、`neutral-grid-jupusdt-15m` runId=40）；**离线折算**＝由 1x 权益曲线按 `E_B(t) = 1000 + (1000×10/cap) × (V_A(t) − cap)` 映射得到，**非平台原生 Path B 回测**，其前提（入场无 partial、名义按比例放大、权益风控关闭）已在 PUMP 1D 上被原生对拍实证，其余标的属外推。逐实例报告路径为 `strategies/<id>/reports/path-b-leverage-report.md`（1x 原始回执 `agent-backtest.md` 由 CLI 自动生成并覆盖，勿手工改写）。
