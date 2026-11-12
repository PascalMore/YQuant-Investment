# predict-btc5m-btc-arb 研究报告

> 首份真实数据研究（M2）。本文由 `research.py` 从同一组内存行渲染，与 `proxy-samples.csv`、`comparison.csv` 同源。

## 结论摘要

- 结论：这是一份**降级的代理研究**。共享 Rust 决策核心在真实闭合 OHLC 边界上给出了模型概率，并与方向代理标签配对；没有历史份额盘口、没有官方结算标签，因此没有可执行收益结论。
- 判定分类：证据不足（insufficient-evidence）。
- 影响范围：只支持“原版冻结参数下的粗频 EWMA 概率在该窗口的校准描述”，不支持任何交易、实盘或策略盈利结论。

## 数据与口径声明

- 数据来源：QuantDinger Agent（ohlc-file），market=Crypto，symbol=BTCUSDT，timeframe=5m。
- 市场身份：venue=UNKNOWN，product=UNKNOWN。供应方未返回可验证的交易所与产品证明，不得写成 Binance 现货或任何具体场所。
- 时间范围：2026-11-09T06:00:00Z 至 2026-11-10T06:00:00Z（UTC，半开区间）；预热自 2026-11-09T04:10:00Z 起，as_of=2026-11-10T06:00:00Z。
- 频率：300 秒；实际闭合 bar 309 根，评估边界 288 个。
- 成本假设：UNKNOWN。费用、净份额、价差与延迟均未建模。
- 指标口径：Brier = mean((p_up - 标签)^2)；基准为同标签的恒定 0.5 概率；平价标签单列；样本内为 t<split 且标签可得时刻≤split，样本外为 t≥split 且标签可得时刻<end，跨界样本排除并计数。
- 杠杆与保证金口径：UNKNOWN。本轮无账户权益，不生成权益曲线。

## 证据身份、可用性与执行预算

- fixture：纯软件行为证据，不是真实市场证据，不替代本轮 real-proxy 数值。
- real-proxy：真实闭合 OHLC 与方向代理标签；非真实份额盘口或官方结算标签。
- real-market：未执行；无已验证历史份额盘口和官方结算标签，不能声明真实交易收益。
- 本文从既有结果渲染时仅修订报告表达，非本次重跑研究；报告渲染不代表独立验收通过。
- 历史声明 checked_at_utc=2026-11-10T07:26:33.941278Z；下列 URL 状态仅为当时声明，未重新联网核验，not_verified 不升级。
- 历史来源：{"detail": "read only; a document is not historical data", "status": "200", "url": "https://docs.predict.fun/developers/chainlink-price-markets"}
- 历史来源：{"detail": "read only; a document is not historical data", "status": "200", "url": "https://dev.predict.fun/trading/fees"}
- 历史来源：{"detail": "read only; a document is not historical data", "status": "200", "url": "https://dev.predict.fun/trading/order-lifecycle"}
- 仅本地核查 reviewed_at_utc=2026-11-10T09:12:08.783205Z；historical_command_logs=NOT_CAPTURED。
- 本地可用性/缺口：{"checked_files": ["data/reports/2026-11-10-predict-btc5m-gaps/report.md", "data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-readonly-probe.json", "data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-btc5m-bars.json", "data/reports/2026-11-09-predict-btc5m-intake/evidence/sources.json", "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/src/service/predict_fun.rs"], "gap": "no_verified_history_for_declared_window", "kind": "historical_share_book", "observed": "not_verified", "query_range": ["2026-11-09T06:00:00Z", "2026-11-10T06:00:00Z"]}
- 本地可用性/缺口：{"checked_files": ["data/reports/2026-11-10-predict-btc5m-gaps/report.md", "data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-readonly-probe.json", "data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-btc5m-bars.json", "data/reports/2026-11-09-predict-btc5m-intake/evidence/sources.json", "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/src/service/predict_fun.rs"], "gap": "no_verified_history_for_declared_window", "kind": "market_identity_and_start_price", "observed": "not_verified", "query_range": ["2026-11-09T06:00:00Z", "2026-11-10T06:00:00Z"]}
- 本地可用性/缺口：{"checked_files": ["data/reports/2026-11-10-predict-btc5m-gaps/report.md", "data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-readonly-probe.json", "data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-btc5m-bars.json", "data/reports/2026-11-09-predict-btc5m-intake/evidence/sources.json", "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/src/service/predict_fun.rs"], "gap": "no_verified_history_for_declared_window", "kind": "official_settlement_labels", "observed": "not_verified", "query_range": ["2026-11-09T06:00:00Z", "2026-11-10T06:00:00Z"]}
- 核查文件/范围/hash：{"available_range": "not_verified", "gap": "no_verified_history_for_declared_window", "observation": {"historical_share_book_and_official_labels": "not_verified", "kind": "archived_gap_assessment", "scope": "report sections 2 and 3"}, "path": "data/reports/2026-11-10-predict-btc5m-gaps/report.md", "sha256": "9f903bcb734e8984d91af42c3597c58aedb7991daaeab5bfb0d09498ca57d013"}
- 核查文件/范围/hash：{"available_range": ["2026-11-09T04:30:00+00:00", "2026-11-10T05:25:00+00:00"], "gap": "no_verified_history_for_declared_window", "observation": {"kind": "archived_ohlc_probe", "observed_at": "2026-11-10T13:29:28.974160+08:00", "row_count": 300, "venue_provenance": null}, "path": "data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-readonly-probe.json", "sha256": "c6af173d7e8b50e08da8c623ed2224561cf925aee94a18f6ec223d399513dac5"}
- 核查文件/范围/hash：{"available_range": ["2026-11-09T04:30:00Z", "2026-11-10T05:25:00Z"], "gap": "no_verified_history_for_declared_window", "observation": {"bar_count": 300, "kind": "archived_ohlc_not_share_book"}, "path": "data/reports/2026-11-10-predict-btc5m-gaps/evidence/quantdinger-btc5m-bars.json", "sha256": "289cf3386f2bd1b03fc16d062103b71ba53f9d8b7497af1bd05efe4fef21fc27"}
- 核查文件/范围/hash：{"available_range": "not_verified", "gap": "no_verified_history_for_declared_window", "observation": {"kind": "archived_document_claims", "official": [{"bytes": 321167, "http_status": 200, "retrieved_at": "2026-11-09T12:49:50.257633+08:00", "url": "https://predict.fun/market/btc-updown-5m"}, {"bytes": 109554, "http_status": 200, "retrieved_at": "2026-11-09T12:49:49.822335+08:00", "url": "https://docs.predict.fun/developers/chainlink-price-markets"}, {"bytes": 135365, "http_status": 200, "retrieved_at": "2026-11-09T12:49:49.803349+08:00", "url": "https://dev.predict.fun/trading/fees"}, {"bytes": 122753, "http_status": 200, "retrieved_at": "2026-11-09T12:49:49.818472+08:00", "url": "https://dev.predict.fun/trading/order-lifecycle"}, {"bytes": 132666, "http_status": 200, "retrieved_at": "2026-11-09T12:49:50.055470+08:00", "url": "https://docs.predict.fun/the-basics/predict-fees-and-limits"}, {"bytes": 172710, "http_status": 200, "retrieved_at": "2026-11-09T12:50:36.744333+08:00", "url": "https://dev.predict.fun/concepts/order-book"}, {"bytes": 225279, "http_status": 200, "retrieved_at": "2026-11-09T12:50:36.603417+08:00", "url": "https://dev.predict.fun/trading/cancel-orders"}, {"bytes": 371951, "http_status": 200, "retrieved_at": "2026-11-09T12:50:36.627516+08:00", "url": "https://dev.predict.fun/trading/place-orders"}], "public_api_probe": {"authenticated": false, "endpoint": "GET /v1/series?first=5", "http_status": 401}}, "path": "data/reports/2026-11-09-predict-btc5m-intake/evidence/sources.json", "sha256": "c97066893aee5502116c1426f7c4edda38962cb6866e2c5cda3f4658430f4b13"}
- 核查文件/范围/hash：{"available_range": "not_verified", "gap": "no_verified_history_for_declared_window", "observation": {"current_orderbook_route_present": true, "history_coverage": "not_proven_by_current_book_route", "kind": "public_route_source"}, "path": "skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/src/service/predict_fun.rs", "sha256": "cb9b0ab6f34f950603ad2738185bb03e57e8922589a942a213e9ce3d551bdc20"}

### 原策略冻结参数

| 参数 | 值 |
|---|---|
| min_edge | 0.03 |
| order_usd | 5.0 USDT |
| min_secs_left | 30 |
| vol_floor | 5e-05 |
| half_life_secs | 300.0 |
| min_vol_samples | 20 |

- 预算上限（非实测）：max_pages=2，max_data_requests=50，wall_seconds=1800。
- 完整研究墙钟（commands.json）：request_count=0，qd_request_count=0，document_request_count=0，elapsed_seconds=0.567，research_exit_code=3。
- coverage.elapsed_seconds=0.008 为早期采样，不是完整墙钟；报告重渲染耗时另记，不覆盖原研究耗时。
- 成交/费用/流动性/极端冲击压力测试：本轮不适用，未执行；无真实份额盘口、成交和账户权益。不新增压力模型、场景或数据。

## 假设与未建模项

- 假设：闭合 bar 的 close 是该边界唯一可得的价格；该假设是“闭合立即可得”的代理时钟，不是真实接收时刻。
- 未建模项：轮内价格路径、份额盘口与深度、官方结算规则、费用与净份额、资金费、冲击成本、延迟。

## 限制与不适用范围

- 限制：粗频采样（5m）无法重建 5 分钟轮内波动与入场边际；样本长度短；方向代理标签不是官方结算标签。
- 不适用范围：不可推广到任何其他标的、周期、时期或账户；不可用于实盘就绪判断。

## 结果明细

| 指标 | 数值 | 口径说明 | 原因 |
|---|---|---|---|
| sample_count (IS) | 144 | paired proxy samples in this partition | none |
| tie_count (IS) | 0 | proxy labels that tied | none |
| p_up_mean (IS) | 0.4997163711240713 | mean of the model probability over the samples | proxy_only |
| p_up_min (IS) | 0.49890436648714376 | smallest model probability over the samples | proxy_only |
| p_up_max (IS) | 0.49982725130171191 | largest model probability over the samples | proxy_only |
| sigma_min (IS) | 5.0000000000000002e-05 | smallest per-root-second volatility over the samples | proxy_only |
| sigma_max (IS) | 0.00031711898730187613 | largest per-root-second volatility over the samples | proxy_only |
| brier (IS) | 0.24997683887740946 | mean((p_up - proxy_label)^2) over the samples | proxy_only |
| baseline_brier (IS) | 0.25 | mean((0.5 - proxy_label)^2) over the same samples | proxy_only |
| candidate_count (IS) | N/A | not_applicable | proxy_only |
| trade_count (IS) | N/A | not_applicable | proxy_only |
| net_pnl (IS) | N/A | not_applicable | no_real_account_equity |
| interval_return_pct (IS) | N/A | not_applicable | no_real_account_equity |
| annualized_return_pct (IS) | N/A | not_applicable | no_real_account_equity |
| sharpe (IS) | N/A | not_applicable | no_real_account_equity |
| max_drawdown_pct (IS) | N/A | not_applicable | no_real_account_equity |
| calmar (IS) | N/A | not_applicable | no_real_account_equity |
| turnover_pct (IS) | N/A | not_applicable | no_real_account_equity |
| information_ratio (IS) | N/A | not_applicable | no_real_account_equity |
| sample_count (OOS) | 143 | paired proxy samples in this partition | none |
| tie_count (OOS) | 0 | proxy labels that tied | none |
| p_up_mean (OOS) | 0.49979213675851836 | mean of the model probability over the samples | proxy_only |
| p_up_min (OOS) | 0.49925199905259154 | smallest model probability over the samples | proxy_only |
| p_up_max (OOS) | 0.49982725130171191 | largest model probability over the samples | proxy_only |
| sigma_min (OOS) | 5.0000000000000002e-05 | smallest per-root-second volatility over the samples | proxy_only |
| sigma_max (OOS) | 0.00021650038366830771 | largest per-root-second volatility over the samples | proxy_only |
| brier (OOS) | 0.25001520446485653 | mean((p_up - proxy_label)^2) over the samples | proxy_only |
| baseline_brier (OOS) | 0.25 | mean((0.5 - proxy_label)^2) over the same samples | proxy_only |
| candidate_count (OOS) | N/A | not_applicable | proxy_only |
| trade_count (OOS) | N/A | not_applicable | proxy_only |
| net_pnl (OOS) | N/A | not_applicable | no_real_account_equity |
| interval_return_pct (OOS) | N/A | not_applicable | no_real_account_equity |
| annualized_return_pct (OOS) | N/A | not_applicable | no_real_account_equity |
| sharpe (OOS) | N/A | not_applicable | no_real_account_equity |
| max_drawdown_pct (OOS) | N/A | not_applicable | no_real_account_equity |
| calmar (OOS) | N/A | not_applicable | no_real_account_equity |
| turnover_pct (OOS) | N/A | not_applicable | no_real_account_equity |
| information_ratio (OOS) | N/A | not_applicable | no_real_account_equity |

## 复现命令

```text
# 从项目根执行
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/strategies/predict-btc5m-btc-arb/research.py --ohlc-file /home/pascal/workspace/yquant-investment/data/reports/2026-11-10-predict-btc5m-m2/evidence/ohlc.json --raw-pages-file /home/pascal/workspace/yquant-investment/data/reports/2026-11-10-predict-btc5m-m2/evidence/raw-pages.json --availability-file /home/pascal/workspace/yquant-investment/data/reports/2026-11-10-predict-btc5m-m2/evidence/availability.json --rust-bin /home/pascal/workspace/yquant-investment/skills/trading/auto-trading/prediction-markets/Prediction-Markets-Trading-Bot-Toolkits/target/debug/btc_arb_replay --start-utc 2026-11-09T06:00:00Z --split-utc 2026-11-09T18:00:00Z --end-utc 2026-11-10T06:00:00Z --as-of-utc 2026-11-10T06:00:00Z --frequency-seconds 300 --warmup-prices 21 --initial-capital 200 --max-pages 2 --max-data-requests 50 --wall-seconds 1800 --evidence-dir data/reports/2026-11-10-predict-btc5m-m2/evidence/recovery-01/independent-verify/research --no-publish
```

## 证据分级

| 结论项 | 分级 | 依据 |
|---|---|---|
| 粗频模型概率在窗口内的校准描述 | 可用 | 144 个样本内与 143 个样本外配对，逐样本见 proxy-samples.csv |
| 历史份额盘口与真实入场 | 证据不足 | 无本地历史，官方文档不证明历史可得性 |
| 官方结算标签与真实 PnL | 证据不足 | 无已验证的官方结算标签 |
| 交易所与产品身份 | 证据不足 | 供应方未返回 venue/product 证明 |
| 费用、净份额、延迟 | 不适用 | 本轮无成交，无从测量 |
| 杠杆、保证金回执、网格表 A/B、四折、G/E、35% 阈值 | 不适用 | 本实例不提交 QD 回测，无真实账户权益 |
