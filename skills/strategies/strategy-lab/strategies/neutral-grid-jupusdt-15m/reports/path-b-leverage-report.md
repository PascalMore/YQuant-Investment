# neutral-grid-jupusdt-15m — Path B 杠杆口径结论（保证金 1000 / 10x / 名义敞口预算 10000）

- 日期：2026-11-03（Asia/Shanghai）；窗口：2026-08-01 ~ 2026-10-31（15m）
- 杠杆口径：保证金 1000 USDT、交易所杠杆 10x、名义敞口预算 10000 USDT（Path B）
- 证据等级：离线折算（非平台原生 Path B 回测）
- 1x 原始结论见同目录 `agent-backtest.md`（CLI 自动生成，勿手工改写）

## 口径对照

| 指标 | 1x 口径（原始） | Path B 口径（10x） |
|---|---|---|
| 总收益 | +11.03% | +110.29% |
| 最大回撤 | −4.02% | −23.82% |
| 最低权益 | 未单独统计 | 897.32 USDT |
| 峰值名义敞口 | 未单独统计 | 3253.75 USDT |
| 峰值 G/E | 未单独统计 | 2.34x |
| 强平 | 无 | 无 |
| 入场 partial | 0/613 | 0/613 |

## 折算方法与前提

- 本实例为离线折算：由 cap=1000 证据组（runId=33）权益曲线按折算公式映射得到 Path B 权益曲线（折算系数 10×）。
- 证据组回执读回为 `leverageEnabled=false / leverage=1.0`、`initialCapital=1000`（真实 1x 口径）；折算可信性依据见 PUMP 1D 原生 10x 对拍。
- 折算公式：`E_B(t) = 1000 + (1000×10/cap) × (V_A(t) − cap)`，`cap` = 1x 证据组初始资金，`V_A(t)` = 1x 权益曲线。
- 前提一：下单规模只依赖 `starting_cash`（每格预算 = `starting_cash × 1/N`），权益风控全部关闭（`EQUITY_TAKE_PROFIT=0 / STOP_LOSS=0 / TRAILING=False`）；平台杠杆在策略代码之外生效。
- 前提二：入场无 partial（0/613），入场名义主值精确等于 `cap/N`，名义敞口可等比放大 10 倍而不被数量离散截断。
- 前提来源：已在 PUMP 1D 原生 10x 与 A 折算逐点对拍验证（`data/reports/2026-11-03-pathb-probe-pump-1d/report.md`）。

## 局限与未建模项

- 资金费 `fundingMode=not_modeled`；10x 下相对影响为 1x 的 10 倍，实际成本更高。
- 强平路径未被触发（最低权益 897.32 > 0，距爆仓线有余量），该路径未获真实触发验证。
- MDD 在 10x 下放大 10 倍（−23.82%），超出原 spec「≤35%」验收标准，需用户决策。
- 离线折算非原生回测；15m 频率存在平台数量离散化的历史风险，本实例入场 partial=0 故折算成立，但该前提随窗口变化需逐窗复核。
- `config.json` 原含未生效的 `leverage` / `initial_capital` 字段（不被策略消费、也不进入提交参数），已于 2026-11-03 清理；保留 `grid_count` 仅作格数记录，不代表策略读取该键。

## 证据路径

- `data/reports/2026-10-31-neutral-grid-15m-backtest/evidence/JUPUSDT-job.json`（cap=1000 证据组完整 job，runId=33）
- `data/reports/2026-11-03-pathb-probe-pump-1d/report.md`（折算公式与等价性对拍）
- `data/reports/2026-11-03-leverage-pathb-closure/report.md`（6 实例 Path B 口径汇总）
