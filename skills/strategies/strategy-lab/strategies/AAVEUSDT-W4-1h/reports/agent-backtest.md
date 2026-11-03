# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:07:29Z
- jobId: 131afa036f95453096ff2cca151dc2e5
- status: succeeded
- runId: 55
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: -82.23776092524817
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -56.361988800571304
- sharpeRatio: -0.40845652087276435
- totalReturn: -35.584166611162985
- totalTrades: 379
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "AAVE/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 1.3875805885225525, "alphaAnnualized": 2.293135460528654, "annualizationFactor": 8766.0, "battingAverage": 0.5132227700582699, "battingStatus": "available", "benchmark": "Crypto:AAVE/USDT@spot", "benchmarkReturnAnnualized": -1.9999341228281933, "beta": 1.452792350342779, "betaSpread": 0.16428025214216602, "betaStatus": "available", "captureRatio": 1.046071864736247, "captureStatus": "available", "classification": "exceptional", "correlation": 0.8478643246290778, "correlationStatus": "available", "downBeta": 1.3790864308364714, "downCapture": 1.4195323462393885, "downMarketPeriods": 1109, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 1.561988754394177, "mSquared": -0.35737572246699967, "mSquaredAlpha": 1.6425584003611937, "mSquaredStatus": "available", "observations": 2231, "outperformancePayoffRatio": 1.0241882160576203, "outperformancePeriods": 1145, "portfolioReturnAnnualized": -0.612353534305641, "rSquared": 0.7188739129787222, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 0.8883422397370143, "treynorRatio": -0.42150107285542854, "treynorStatus": "available", "underperformancePeriods": 1085, "upBeta": 1.5433666829786374, "upCapture": 1.484932848484057, "upMarketPeriods": 1109}
- dataProvenance: {"benchmark": {"bars": 2232, "contentHash": "1d38688bfbf04eecc82c79a9cf69716580531411369018b1158a02879b855586", "firstBar": "2025-11-03 00:00:00", "instrument": "Crypto:AAVE/USDT@spot", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "1d38688bfbf04eecc82c79a9cf69716580531411369018b1158a02879b855586"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-02-03T23:59:59", "requestedStart": "2025-11-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2256, "contentHash": "ba1a424123844306a1e40c05d704a72091cd2fa339944194a1ad9152c1210dc5", "firstBar": "2025-11-02 00:00:00", "instrument": "Crypto:AAVE/USDT@swap", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "ba1a424123844306a1e40c05d704a72091cd2fa339944194a1ad9152c1210dc5"}], "timeframes": {"1h": [{"bars": 2256, "contentHash": "ba1a424123844306a1e40c05d704a72091cd2fa339944194a1ad9152c1210dc5", "firstBar": "2025-11-02 00:00:00", "instrument": "Crypto:AAVE/USDT@swap", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "ba1a424123844306a1e40c05d704a72091cd2fa339944194a1ad9152c1210dc5"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 9.899255196837018
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-02-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2025-11-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 379 elements
- equityCurve: 1200 elements
- executions: 797 elements
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
