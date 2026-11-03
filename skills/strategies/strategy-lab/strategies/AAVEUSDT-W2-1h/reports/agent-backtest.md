# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:05:21Z
- jobId: 249ba6fa4fb74f16a187b3ba7a21080f
- status: succeeded
- runId: 47
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 132.25769145002428
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -51.01527516157262
- sharpeRatio: 1.335240711724593
- totalReturn: 23.920056970417637
- totalTrades: 202
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "AAVE/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 1.0577019636407186, "alphaAnnualized": 1.0175435352260012, "annualizationFactor": 8766.0, "battingAverage": 0.528014343343792, "battingStatus": "available", "benchmark": "Crypto:AAVE/USDT@spot", "benchmarkReturnAnnualized": 0.3099263667354219, "beta": 1.129574094768774, "betaSpread": -0.02688937097704236, "betaStatus": "available", "captureRatio": 1.0328422622269853, "captureStatus": "available", "classification": "exceptional", "correlation": 0.876492029073774, "correlationStatus": "available", "downBeta": 1.2542144959152965, "downCapture": 0.9976158105329012, "downMarketPeriods": 1114, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 2.0992583732100494, "mSquared": 1.0612100046040276, "mSquaredAlpha": 0.7512836378686056, "mSquaredStatus": "available", "observations": 2231, "outperformancePayoffRatio": 0.9577098428107818, "outperformancePeriods": 1178, "portfolioReturnAnnualized": 1.3676283303761405, "rSquared": 0.7682382770298615, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 0.5038455376140049, "treynorRatio": 1.2107468971799469, "treynorStatus": "available", "underperformancePeriods": 1049, "upBeta": 1.2273251249382542, "upCapture": 1.0303797705842093, "upMarketPeriods": 1099}
- dataProvenance: {"benchmark": {"bars": 2232, "contentHash": "457d0a49928d0346b6cf1897bcfc6859e09adb4a636192d2d3d5fb9dabca394c", "firstBar": "2026-05-03 00:00:00", "instrument": "Crypto:AAVE/USDT@spot", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "457d0a49928d0346b6cf1897bcfc6859e09adb4a636192d2d3d5fb9dabca394c"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-08-03T23:59:59", "requestedStart": "2026-05-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2256, "contentHash": "4cd1cacd37362c430eb18a376ef9e35905afeb21956be650c2313766fdacd91f", "firstBar": "2026-05-02 00:00:00", "instrument": "Crypto:AAVE/USDT@swap", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "4cd1cacd37362c430eb18a376ef9e35905afeb21956be650c2313766fdacd91f"}], "timeframes": {"1h": [{"bars": 2256, "contentHash": "4cd1cacd37362c430eb18a376ef9e35905afeb21956be650c2313766fdacd91f", "firstBar": "2026-05-02 00:00:00", "instrument": "Crypto:AAVE/USDT@swap", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "4cd1cacd37362c430eb18a376ef9e35905afeb21956be650c2313766fdacd91f"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 24.071359250417647
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-08-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-05-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 202 elements
- equityCurve: 1200 elements
- executions: 412 elements
- holdingSnapshots: 600 elements
- liquidationEvents: 0 elements
- logs: 0 elements
- orderLedger: 962 elements
- protectionEvents: 0 elements
- rebalanceRecords: 800 elements

## Notes

- Agent curve arrays are reported by length only; the gateway samples closedTrades/executions to <=1500 and equity/benchmark curves to <=1200.
- The Agent channel has no sourceId/run read-back route; the persisted run's source_id is NULL by platform contract and is not a failure.
- Unsupported on this channel: grid generate, Strategy Evolution, run/sourceId read-back, agent trading.
