# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:06:11Z
- jobId: 9b552e3f675342698986bb2791693b59
- status: succeeded
- runId: 50
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 158.45113063934215
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -31.73737779737037
- sharpeRatio: 1.3857161359556593
- totalReturn: 26.347226638840993
- totalTrades: 468
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "PUMP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 2.3983251576276756, "alphaAnnualized": 2.5375452982753153, "annualizationFactor": 8766.0, "battingAverage": 0.523853635942566, "battingStatus": "available", "benchmark": "Crypto:PUMP/USDT@spot", "benchmarkReturnAnnualized": -0.6862482533827595, "beta": 1.202871395244177, "betaSpread": -0.015282974893707557, "betaStatus": "available", "captureRatio": 1.0606695491985867, "captureStatus": "available", "classification": "exceptional", "correlation": 0.9319084433959409, "correlationStatus": "available", "downBeta": 1.1558171800125323, "downCapture": 1.2162330802735328, "downMarketPeriods": 1077, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 4.909631921678543, "mSquared": 1.3264085662999265, "mSquaredAlpha": 2.012656819682686, "mSquaredStatus": "available", "observations": 2159, "outperformancePayoffRatio": 1.0750619885378248, "outperformancePeriods": 1131, "portfolioReturnAnnualized": 1.712076904244916, "rSquared": 0.8684533468726456, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 0.48849388220690027, "treynorRatio": 1.423324979722685, "treynorStatus": "available", "underperformancePeriods": 1017, "upBeta": 1.1405342051188248, "upCapture": 1.2900213929741366, "upMarketPeriods": 1023}
- dataProvenance: {"benchmark": {"bars": 2160, "contentHash": "7d2eeca64bb48f6ad6fd9f2040106221a118d5a214de40295967f5fd68424d60", "firstBar": "2026-02-03 00:00:00", "instrument": "Crypto:PUMP/USDT@spot", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "7d2eeca64bb48f6ad6fd9f2040106221a118d5a214de40295967f5fd68424d60"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-05-03T23:59:59", "requestedStart": "2026-02-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2184, "contentHash": "2a1a9ba99c41dc8ed7c6f6e17f10f3c390f71e382990eac4df05c24173449665", "firstBar": "2026-02-02 00:00:00", "instrument": "Crypto:PUMP/USDT@swap", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "2a1a9ba99c41dc8ed7c6f6e17f10f3c390f71e382990eac4df05c24173449665"}], "timeframes": {"1h": [{"bars": 2184, "contentHash": "2a1a9ba99c41dc8ed7c6f6e17f10f3c390f71e382990eac4df05c24173449665", "firstBar": "2026-02-02 00:00:00", "instrument": "Crypto:PUMP/USDT@swap", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "2a1a9ba99c41dc8ed7c6f6e17f10f3c390f71e382990eac4df05c24173449665"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 50.896870542841
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-05-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-02-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 468 elements
- equityCurve: 1200 elements
- executions: 958 elements
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
