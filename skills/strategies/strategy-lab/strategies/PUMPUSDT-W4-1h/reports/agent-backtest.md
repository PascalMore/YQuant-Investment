# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:07:13Z
- jobId: 022df04cb3404d6fa8b1f0d78d8e4453
- status: succeeded
- runId: 54
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: -26.855978624958627
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -97.83906263558539
- sharpeRatio: 2.2884608569015397
- totalReturn: -7.650894756404913
- totalTrades: 894
- winRate: 91.61073825503355

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "PUMP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 12.781432892688642, "alphaAnnualized": 13.241548495649049, "annualizationFactor": 8766.0, "battingAverage": 0.529359031824294, "battingStatus": "available", "benchmark": "Crypto:PUMP/USDT@spot", "benchmarkReturnAnnualized": -1.277707206776921, "beta": 1.3601103605896305, "betaSpread": -0.27264575390046175, "betaStatus": "available", "captureRatio": 1.052247962771141, "captureStatus": "available", "classification": "exceptional", "correlation": 0.37315248422125136, "correlationStatus": "available", "downBeta": 1.1433900749015, "downCapture": 1.6467878790550636, "downMarketPeriods": 1117, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 2.724571572633749, "mSquared": 3.1560996385887723, "mSquaredAlpha": 4.433806845365694, "mSquaredStatus": "available", "observations": 2231, "outperformancePayoffRatio": 1.0298010692531163, "outperformancePeriods": 1181, "portfolioReturnAnnualized": 11.503725685911721, "rSquared": 0.13924277648049124, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 4.691171639999633, "treynorRatio": 8.457935487620773, "treynorStatus": "available", "underperformancePeriods": 1044, "upBeta": 0.8707443210010383, "upCapture": 1.732829190851899, "upMarketPeriods": 1077}
- dataProvenance: {"benchmark": {"bars": 2232, "contentHash": "4d89cd09bccc7f7a5cab1e1b07ccf38d08359ab5118742ce3fb0d0440388105c", "firstBar": "2025-11-03 00:00:00", "instrument": "Crypto:PUMP/USDT@spot", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "4d89cd09bccc7f7a5cab1e1b07ccf38d08359ab5118742ce3fb0d0440388105c"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-02-03T23:59:59", "requestedStart": "2025-11-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2256, "contentHash": "13d214e662018ae05683c4f04a5feb273c890f83780b8664a3868127d9cbe40e", "firstBar": "2025-11-02 00:00:00", "instrument": "Crypto:PUMP/USDT@swap", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "13d214e662018ae05683c4f04a5feb273c890f83780b8664a3868127d9cbe40e"}], "timeframes": {"1h": [{"bars": 2256, "contentHash": "13d214e662018ae05683c4f04a5feb273c890f83780b8664a3868127d9cbe40e", "firstBar": "2025-11-02 00:00:00", "instrument": "Crypto:PUMP/USDT@swap", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "13d214e662018ae05683c4f04a5feb273c890f83780b8664a3868127d9cbe40e"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 35.61652520559508
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-02-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2025-11-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 894 elements
- equityCurve: 1200 elements
- executions: 1500 elements
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
