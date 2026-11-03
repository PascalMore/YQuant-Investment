# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:04:49Z
- jobId: 37fbaf5477b3435790ec72cf8b5809d7
- status: succeeded
- runId: 45
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 211.72940657318966
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -56.1562735097606
- sharpeRatio: 1.5169345988240845
- totalReturn: 33.55785288676447
- totalTrades: 505
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "JUP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 1.7484429706559774, "alphaAnnualized": 1.4703366550871506, "annualizationFactor": 8766.0, "battingAverage": 0.5257731958762887, "battingStatus": "available", "benchmark": "Crypto:JUP/USDT@spot", "benchmarkReturnAnnualized": 0.8134618131011406, "beta": 1.3418799888203834, "betaSpread": -0.06283187846350513, "betaStatus": "available", "captureRatio": 1.01585360722367, "captureStatus": "available", "classification": "exceptional", "correlation": 0.8045755168068024, "correlationStatus": "available", "downBeta": 1.4059346193520958, "downCapture": 1.3001913287539082, "downMarketPeriods": 1108, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 1.6475421279357716, "mSquared": 1.5360880872910236, "mSquaredAlpha": 0.722626274189883, "mSquaredStatus": "available", "observations": 2231, "outperformancePayoffRatio": 0.9624888280118712, "outperformancePeriods": 1173, "portfolioReturnAnnualized": 2.561904783757118, "rSquared": 0.6473417622449331, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 1.0612432550338642, "treynorRatio": 1.909190691493381, "treynorStatus": "available", "underperformancePeriods": 1051, "upBeta": 1.3431027408885907, "upCapture": 1.320804051395594, "upMarketPeriods": 1065}
- dataProvenance: {"benchmark": {"bars": 2232, "contentHash": "7ac4c193ec2236d4eb429bc17c808b659a9396993135370273acdb75f2602be3", "firstBar": "2026-05-03 00:00:00", "instrument": "Crypto:JUP/USDT@spot", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "7ac4c193ec2236d4eb429bc17c808b659a9396993135370273acdb75f2602be3"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-08-03T23:59:59", "requestedStart": "2026-05-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2256, "contentHash": "74f52596bbd85cc7310ccec6837280c8ff2c39c5f0e8f6ee8448d72e079efffd", "firstBar": "2026-05-02 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "74f52596bbd85cc7310ccec6837280c8ff2c39c5f0e8f6ee8448d72e079efffd"}], "timeframes": {"1h": [{"bars": 2256, "contentHash": "74f52596bbd85cc7310ccec6837280c8ff2c39c5f0e8f6ee8448d72e079efffd", "firstBar": "2026-05-02 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "74f52596bbd85cc7310ccec6837280c8ff2c39c5f0e8f6ee8448d72e079efffd"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 25.608992408764465
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-08-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-05-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 505 elements
- equityCurve: 1200 elements
- executions: 1033 elements
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
