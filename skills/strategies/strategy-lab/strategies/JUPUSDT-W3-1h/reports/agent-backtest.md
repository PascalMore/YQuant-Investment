# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:05:55Z
- jobId: ce313cfd0d204a41ae6e40cfac382d07
- status: succeeded
- runId: 49
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 180.6848445791259
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -27.210499868828542
- sharpeRatio: 1.7712865301358032
- totalReturn: 28.941573688277767
- totalTrades: 373
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "JUP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 1.2093283698539659, "alphaAnnualized": 1.2301470009745448, "annualizationFactor": 8766.0, "battingAverage": 0.5233904585456229, "battingStatus": "available", "benchmark": "Crypto:JUP/USDT@spot", "benchmarkReturnAnnualized": 0.09288154842563474, "beta": 0.7758582681548701, "betaSpread": -0.023076100943913325, "betaStatus": "available", "captureRatio": 1.055470679582306, "captureStatus": "available", "classification": "exceptional", "correlation": 0.8887734298815657, "correlationStatus": "available", "downBeta": 0.7734440599901921, "downCapture": 0.7667352878011756, "downMarketPeriods": 1059, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 3.1303295971372838, "mSquared": 1.4917280939050712, "mSquaredAlpha": 1.3988465454794365, "mSquaredStatus": "available", "observations": 2159, "outperformancePayoffRatio": 1.0005724869549404, "outperformancePeriods": 1130, "portfolioReturnAnnualized": 1.3022099182796005, "rSquared": 0.7899182096634424, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 0.3863262101728547, "treynorRatio": 1.6784121169147155, "treynorStatus": "available", "underperformancePeriods": 1016, "upBeta": 0.7503679590462787, "upCapture": 0.8092666152752418, "upMarketPeriods": 1030}
- dataProvenance: {"benchmark": {"bars": 2160, "contentHash": "28214c21347d4fb912e7cb34248f2b552a66ff6b7d6b787b7764f25e3110f76b", "firstBar": "2026-02-03 00:00:00", "instrument": "Crypto:JUP/USDT@spot", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "28214c21347d4fb912e7cb34248f2b552a66ff6b7d6b787b7764f25e3110f76b"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-05-03T23:59:59", "requestedStart": "2026-02-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2184, "contentHash": "e23dcfcce6600bae74873624ea148181b657a6563e062b6d65a533891058be3a", "firstBar": "2026-02-02 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "e23dcfcce6600bae74873624ea148181b657a6563e062b6d65a533891058be3a"}], "timeframes": {"1h": [{"bars": 2184, "contentHash": "e23dcfcce6600bae74873624ea148181b657a6563e062b6d65a533891058be3a", "firstBar": "2026-02-02 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "e23dcfcce6600bae74873624ea148181b657a6563e062b6d65a533891058be3a"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 35.178360157277766
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-05-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-02-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 373 elements
- equityCurve: 1200 elements
- executions: 756 elements
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
