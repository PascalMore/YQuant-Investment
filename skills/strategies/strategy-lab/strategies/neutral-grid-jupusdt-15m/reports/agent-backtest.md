# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-10-31T05:42:42Z
- jobId: b557d3835ce14b789d606bcbafb91d2a
- status: succeeded
- runId: 32
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 52.02953342457144
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -4.020240435970113
- sharpeRatio: 3.462184756033466
- totalReturn: 11.028710162117061
- totalTrades: 610
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "JUP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": null, "annualizationFactor": 8766.0, "benchmark": "Crypto:JUP/USDT@spot", "benchmarkReturnAnnualized": null, "classification": null, "frequency": "1h", "informationRatio": null, "observations": 0, "portfolioReturnAnnualized": null, "status": "insufficient_history", "trackingErrorAnnualized": null}
- dataProvenance: {"benchmark": null, "frequencies": ["15m"], "frequency": "15m", "kind": "market", "requestedEnd": "2026-10-31T23:59:59", "requestedStart": "2026-08-01T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 8854, "contentHash": "1ba105ad89503298d61f443d1b47248098a96c0aa84088bdc4179dd77f8c3af4", "firstBar": "2026-07-31 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-10-31 05:15:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "1ba105ad89503298d61f443d1b47248098a96c0aa84088bdc4179dd77f8c3af4"}], "timeframes": {"15m": [{"bars": 8854, "contentHash": "1ba105ad89503298d61f443d1b47248098a96c0aa84088bdc4179dd77f8c3af4", "firstBar": "2026-07-31 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-10-31 05:15:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "1ba105ad89503298d61f443d1b47248098a96c0aa84088bdc4179dd77f8c3af4"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 11.028710162117061
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "15m", "endDate": "2026-10-31", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["15m"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 1.0, "leverageEnabled": false, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-08-01", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 0 elements
- closedTrades: 610 elements
- equityCurve: 1200 elements
- executions: 1223 elements
- holdingSnapshots: 600 elements
- liquidationEvents: 0 elements
- logs: 0 elements
- orderLedger: 1500 elements
- protectionEvents: 0 elements
- rebalanceRecords: 800 elements

## Notes

- Agent curve arrays are reported by length only; the gateway samples closedTrades/executions to <=1500 and equity/benchmark curves to <=1200.
- The Agent channel has no sourceId/run read-back route; the persisted run's source_id is NULL by platform contract and is not a failure.
- Unsupported on this channel: grid generate, Strategy Evolution, run/sourceId read-back, agent trading.
