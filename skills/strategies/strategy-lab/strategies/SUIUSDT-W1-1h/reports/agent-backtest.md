# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:04:30Z
- jobId: 08405582c0864aecb78312266cc0ecee
- status: succeeded
- runId: 44
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 68.75853421932712
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -20.321134092526183
- sharpeRatio: 1.1855096053219734
- totalReturn: 14.23904930185258
- totalTrades: 390
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "SUI/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": -0.7518513660749566, "alphaAnnualized": -0.06889664731355416, "annualizationFactor": 8766.0, "battingAverage": 0.520627802690583, "battingStatus": "available", "benchmark": "Crypto:SUI/USDT@spot", "benchmarkReturnAnnualized": 1.4485498549090823, "beta": 0.52852522372848, "betaSpread": -0.16365609873702447, "betaStatus": "available", "captureRatio": 0.9896724718973683, "captureStatus": "available", "classification": "weak", "correlation": 0.7939974022571435, "correlationStatus": "available", "downBeta": 0.5524119542340797, "downCapture": 0.6177521754948361, "downMarketPeriods": 1108, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": -1.370328780093452, "mSquared": 1.046642176107299, "mSquaredAlpha": -0.40190767880178324, "mSquaredStatus": "available", "observations": 2230, "outperformancePayoffRatio": 0.8650928106307639, "outperformancePeriods": 1161, "portfolioReturnAnnualized": 0.6966984888341258, "rSquared": 0.6304318747910922, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 0.5486649459582121, "treynorRatio": 1.3181934514293714, "treynorStatus": "available", "underperformancePeriods": 1065, "upBeta": 0.38875585549705527, "upCapture": 0.6113723225419513, "upMarketPeriods": 1105}
- dataProvenance: {"benchmark": {"bars": 2231, "contentHash": "6f1086e9e665b62033d13507c946ec2ba3e599a3a324b94771a3659caad5d403", "firstBar": "2026-08-03 00:00:00", "instrument": "Crypto:SUI/USDT@spot", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "6f1086e9e665b62033d13507c946ec2ba3e599a3a324b94771a3659caad5d403"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-11-03T23:59:59", "requestedStart": "2026-08-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2255, "contentHash": "47f38003ddbc6f037f31214e45daa0f02c6293f7ffd6716036030ffbe5a151c4", "firstBar": "2026-08-02 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "47f38003ddbc6f037f31214e45daa0f02c6293f7ffd6716036030ffbe5a151c4"}], "timeframes": {"1h": [{"bars": 2255, "contentHash": "47f38003ddbc6f037f31214e45daa0f02c6293f7ffd6716036030ffbe5a151c4", "firstBar": "2026-08-02 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "47f38003ddbc6f037f31214e45daa0f02c6293f7ffd6716036030ffbe5a151c4"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: -16.66554639314741
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-11-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-08-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 390 elements
- equityCurve: 1200 elements
- executions: 805 elements
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
