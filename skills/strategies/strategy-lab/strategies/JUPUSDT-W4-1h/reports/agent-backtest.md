# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:06:58Z
- jobId: d323ec5f8f5343fba6583d41b6fe6558
- status: succeeded
- runId: 53
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: -85.27477835202592
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -85.82603495257685
- sharpeRatio: 0.8235352395891979
- totalReturn: -38.586095619952246
- totalTrades: 444
- winRate: 99.77477477477478

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "JUP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 4.715745573730665, "alphaAnnualized": 8.242425936701247, "annualizationFactor": 8766.0, "battingAverage": 0.5002241147467503, "battingStatus": "available", "benchmark": "Crypto:JUP/USDT@spot", "benchmarkReturnAnnualized": -2.3030526675889083, "beta": 2.5313068661441873, "betaSpread": 0.37850792973034153, "betaStatus": "available", "captureRatio": 1.0779690737583778, "captureStatus": "available", "classification": "exceptional", "correlation": 0.8486721080266355, "correlationStatus": "available", "downBeta": 2.324220426443878, "downCapture": 2.479954890603073, "downMarketPeriods": 1099, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 2.1832250210966095, "mSquared": 0.8089043655916826, "mSquaredAlpha": 3.111957033180591, "mSquaredStatus": "available", "observations": 2231, "outperformancePayoffRatio": 1.0793753923209957, "outperformancePeriods": 1116, "portfolioReturnAnnualized": 2.4126929061417566, "rSquared": 0.7202443469423733, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 2.159990623120469, "treynorRatio": 0.9531412166620835, "treynorStatus": "available", "underperformancePeriods": 1110, "upBeta": 2.7027283561742195, "upCapture": 2.6733146763859534, "upMarketPeriods": 1080}
- dataProvenance: {"benchmark": {"bars": 2232, "contentHash": "8a3c7d42560ca66a780731e95234022d4b6aa9a83ea091e5e6e9068513d08c96", "firstBar": "2025-11-03 00:00:00", "instrument": "Crypto:JUP/USDT@spot", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "8a3c7d42560ca66a780731e95234022d4b6aa9a83ea091e5e6e9068513d08c96"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-02-03T23:59:59", "requestedStart": "2025-11-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2256, "contentHash": "d6537b0e970dab7955be7555ec6f715f758ca310de2a031405c0cebd4ddeeadd", "firstBar": "2025-11-02 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "d6537b0e970dab7955be7555ec6f715f758ca310de2a031405c0cebd4ddeeadd"}], "timeframes": {"1h": [{"bars": 2256, "contentHash": "d6537b0e970dab7955be7555ec6f715f758ca310de2a031405c0cebd4ddeeadd", "firstBar": "2025-11-02 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "d6537b0e970dab7955be7555ec6f715f758ca310de2a031405c0cebd4ddeeadd"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 12.21954385604775
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-02-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2025-11-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 444 elements
- equityCurve: 1200 elements
- executions: 933 elements
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
