# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-10-31T03:44:23Z
- jobId: c12559f9c2e141999cc964be3eb6d953
- status: succeeded
- runId: 25
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 6.665383218790737
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -19.26889858586759
- sharpeRatio: 0.664349510037239
- totalReturn: 73.99366094264195
- totalTrades: 61
- winRate: 34.42622950819672

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "USStock:SPY", "market": "USStock", "market_type": "", "symbol": "SPY"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": -0.08420501695365375, "annualizationFactor": 252.0, "benchmark": "USStock:SPY", "benchmarkReturnAnnualized": 0.15451101978620244, "classification": "weak", "frequency": "1d", "informationRatio": -0.5559701492709499, "observations": 2158, "portfolioReturnAnnualized": 0.0703060028325487, "status": "available", "trackingErrorAnnualized": 0.15145600364349193}
- dataProvenance: {"benchmark": {"bars": 2499, "contentHash": "df7ba91f5e2ed2a50a49fa96d8b79a7295ddda028c87d50db8dda1393e7f5bd4", "firstBar": "2016-01-26 05:00:00", "instrument": "USStock:SPY", "lastBar": "2025-12-31 05:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "df7ba91f5e2ed2a50a49fa96d8b79a7295ddda028c87d50db8dda1393e7f5bd4"}, "frequencies": ["1d"], "frequency": "1d", "kind": "market", "requestedEnd": "2025-12-31T23:59:59", "requestedStart": "2017-06-01T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2499, "contentHash": "df7ba91f5e2ed2a50a49fa96d8b79a7295ddda028c87d50db8dda1393e7f5bd4", "firstBar": "2016-01-26 05:00:00", "instrument": "USStock:SPY", "lastBar": "2025-12-31 05:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "df7ba91f5e2ed2a50a49fa96d8b79a7295ddda028c87d50db8dda1393e7f5bd4"}], "timeframes": {"1d": [{"bars": 2499, "contentHash": "df7ba91f5e2ed2a50a49fa96d8b79a7295ddda028c87d50db8dda1393e7f5bd4", "firstBar": "2016-01-26 05:00:00", "instrument": "USStock:SPY", "lastBar": "2025-12-31 05:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "df7ba91f5e2ed2a50a49fa96d8b79a7295ddda028c87d50db8dda1393e7f5bd4"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: -148.27059821615805
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1d", "endDate": "2025-12-31", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1d"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 10000.0, "intrabarMode": "conservative", "leverage": 1.0, "leverageEnabled": false, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2017-06-01", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 61 elements
- equityCurve: 1200 elements
- executions: 123 elements
- holdingSnapshots: 600 elements
- liquidationEvents: 0 elements
- logs: 0 elements
- orderLedger: 123 elements
- protectionEvents: 0 elements
- rebalanceRecords: 123 elements

## Notes

- Agent curve arrays are reported by length only; the gateway samples closedTrades/executions to <=1500 and equity/benchmark curves to <=1200.
- The Agent channel has no sourceId/run read-back route; the persisted run's source_id is NULL by platform contract and is not a failure.
- Unsupported on this channel: grid generate, Strategy Evolution, run/sourceId read-back, agent trading.
