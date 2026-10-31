# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-10-31T04:00:07Z
- jobId: 0542681694d2496691f969491ac7625b
- status: succeeded
- runId: 29
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 19.1227921681589
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -5.855900202872732
- sharpeRatio: 1.6346216522244164
- totalReturn: 18.994454825646635
- totalTrades: 608
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "JUP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 0.1981203728687402, "annualizationFactor": 365.25, "benchmark": "Crypto:JUP/USDT@spot", "benchmarkReturnAnnualized": -0.01695910464528665, "classification": "weak", "frequency": "1d", "informationRatio": 0.2274431115514761, "observations": 363, "portfolioReturnAnnualized": 0.18116126822345358, "status": "available", "trackingErrorAnnualized": 0.8710766024844001}
- dataProvenance: {"benchmark": {"bars": 364, "contentHash": "cee4cf6e24235100c6e10988b0d616c3a83c3bb84356f6a2890d6fae55e0b41f", "firstBar": "2025-11-01 00:00:00", "instrument": "Crypto:JUP/USDT@spot", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "cee4cf6e24235100c6e10988b0d616c3a83c3bb84356f6a2890d6fae55e0b41f"}, "frequencies": ["1d"], "frequency": "1d", "kind": "market", "requestedEnd": "2026-10-31T23:59:59", "requestedStart": "2025-11-01T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 368, "contentHash": "4e5bb7d8a3e6fb740e30eaca7c1d72cdab94a3d98bdcbc67bdf74f5a2b18e04a", "firstBar": "2025-10-28 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "4e5bb7d8a3e6fb740e30eaca7c1d72cdab94a3d98bdcbc67bdf74f5a2b18e04a"}], "timeframes": {"1d": [{"bars": 368, "contentHash": "4e5bb7d8a3e6fb740e30eaca7c1d72cdab94a3d98bdcbc67bdf74f5a2b18e04a", "firstBar": "2025-10-28 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "4e5bb7d8a3e6fb740e30eaca7c1d72cdab94a3d98bdcbc67bdf74f5a2b18e04a"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 55.58403613064663
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1d", "endDate": "2026-10-31", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1d"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 1.0, "leverageEnabled": false, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2025-11-01", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 364 elements
- closedTrades: 608 elements
- equityCurve: 364 elements
- executions: 1222 elements
- holdingSnapshots: 364 elements
- liquidationEvents: 0 elements
- logs: 0 elements
- orderLedger: 1500 elements
- protectionEvents: 0 elements
- rebalanceRecords: 363 elements

## Notes

- Agent curve arrays are reported by length only; the gateway samples closedTrades/executions to <=1500 and equity/benchmark curves to <=1200.
- The Agent channel has no sourceId/run read-back route; the persisted run's source_id is NULL by platform contract and is not a failure.
- Unsupported on this channel: grid generate, Strategy Evolution, run/sourceId read-back, agent trading.
