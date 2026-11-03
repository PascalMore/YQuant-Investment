# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T15:26:47Z
- jobId: 09f86037731e4c899434177273d174d5
- status: succeeded
- runId: 40
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 1821.8705230300088
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -23.89711494248803
- sharpeRatio: 3.790617985052677
- totalReturn: 110.52842384997751
- totalTrades: 626
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "JUP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 1.6024786745754234, "alphaAnnualized": 3.3365063356031848, "annualizationFactor": 8766.0, "battingAverage": 0.513819664703217, "battingStatus": "available", "benchmark": "Crypto:JUP/USDT@spot", "benchmarkReturnAnnualized": 1.712114817231301, "beta": -0.0127986999329262, "betaSpread": 0.13368156950412052, "betaStatus": "available", "captureRatio": -0.7407755859229543, "captureStatus": "available", "classification": "exceptional", "correlation": -0.015475874438579347, "correlationStatus": "available", "downBeta": -0.08830954130202642, "downCapture": -0.053764875013380405, "downMarketPeriods": 1080, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 1.1966839734060193, "mSquared": 4.00792525513997, "mSquaredAlpha": 2.295810437908669, "mSquaredStatus": "available", "observations": 2207, "outperformancePayoffRatio": 0.9829059128386488, "outperformancePeriods": 1134, "portfolioReturnAnnualized": 3.3145934918067246, "rSquared": 0.0002395026896386736, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 1.3390993028965077, "treynorRatio": -258.9789204510946, "treynorStatus": "available", "underperformancePeriods": 1073, "upBeta": 0.0453720282020941, "upCapture": 0.03982770679011128, "upMarketPeriods": 1074}
- dataProvenance: {"benchmark": {"bars": 2208, "contentHash": "2b1a69011705f2187c7f0e954a6fccccb07458659c9d9f924ab899231bbc6256", "firstBar": "2026-08-01 00:00:00", "instrument": "Crypto:JUP/USDT@spot", "lastBar": "2026-10-31 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "2b1a69011705f2187c7f0e954a6fccccb07458659c9d9f924ab899231bbc6256"}, "frequencies": ["15m"], "frequency": "15m", "kind": "market", "requestedEnd": "2026-10-31T23:59:59", "requestedStart": "2026-08-01T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 8928, "contentHash": "0237227a0fe9247ee013ea742dea5141554e2284cba34530cd82a08e32b316e2", "firstBar": "2026-07-31 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-10-31 23:45:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "0237227a0fe9247ee013ea742dea5141554e2284cba34530cd82a08e32b316e2"}], "timeframes": {"15m": [{"bars": 8928, "contentHash": "0237227a0fe9247ee013ea742dea5141554e2284cba34530cd82a08e32b316e2", "firstBar": "2026-07-31 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-10-31 23:45:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "0237227a0fe9247ee013ea742dea5141554e2284cba34530cd82a08e32b316e2"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 75.68231013097753
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "15m", "endDate": "2026-10-31", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["15m"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-08-01", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 626 elements
- equityCurve: 1200 elements
- executions: 1269 elements
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
