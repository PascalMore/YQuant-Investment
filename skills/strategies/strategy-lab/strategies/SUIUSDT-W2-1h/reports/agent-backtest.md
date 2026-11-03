# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:05:37Z
- jobId: fcead562fd044907b308b6d451057fda
- status: succeeded
- runId: 48
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: -96.29197645652174
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -78.97385289010514
- sharpeRatio: 0.47323529654777907
- totalReturn: -56.76473643329023
- totalTrades: 308
- winRate: 99.67532467532467

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "SUI/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 2.2826558543841116, "alphaAnnualized": 4.023803041552604, "annualizationFactor": 8766.0, "battingAverage": 0.4997758852532497, "battingStatus": "available", "benchmark": "Crypto:SUI/USDT@spot", "benchmarkReturnAnnualized": -0.8276467514380192, "beta": 3.103732279675217, "betaSpread": -0.5903782770407098, "betaStatus": "available", "captureRatio": 1.0164583034280965, "captureStatus": "available", "classification": "good", "correlation": 0.7964997802165635, "correlationStatus": "available", "downBeta": 3.381730809544869, "downCapture": 3.1424826827327696, "downMarketPeriods": 1108, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 0.9157034691643232, "mSquared": 0.37339381308716935, "mSquaredAlpha": 1.2010405645251887, "mSquaredStatus": "available", "observations": 2231, "outperformancePayoffRatio": 1.03629859056201, "outperformancePeriods": 1115, "portfolioReturnAnnualized": 1.4550091029460925, "rSquared": 0.634411899885034, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 2.492789348572937, "treynorRatio": 0.4687933661270387, "treynorStatus": "available", "underperformancePeriods": 1112, "upBeta": 2.7913525325041593, "upCapture": 3.194202616242724, "upMarketPeriods": 1106}
- dataProvenance: {"benchmark": {"bars": 2232, "contentHash": "8e9c650faa19ed4d8e635ac65839b30d74ccebb70f82fc8ed715d46f3ac7964e", "firstBar": "2026-05-03 00:00:00", "instrument": "Crypto:SUI/USDT@spot", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "8e9c650faa19ed4d8e635ac65839b30d74ccebb70f82fc8ed715d46f3ac7964e"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-08-03T23:59:59", "requestedStart": "2026-05-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2256, "contentHash": "13fac9ab969ca5b743b3a5185eccdc403a2f17adba998f4c1fc3855722718338", "firstBar": "2026-05-02 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "13fac9ab969ca5b743b3a5185eccdc403a2f17adba998f4c1fc3855722718338"}], "timeframes": {"1h": [{"bars": 2256, "contentHash": "13fac9ab969ca5b743b3a5185eccdc403a2f17adba998f4c1fc3855722718338", "firstBar": "2026-05-02 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "13fac9ab969ca5b743b3a5185eccdc403a2f17adba998f4c1fc3855722718338"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: -31.61581408929023
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-08-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-05-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 308 elements
- equityCurve: 1200 elements
- executions: 661 elements
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
