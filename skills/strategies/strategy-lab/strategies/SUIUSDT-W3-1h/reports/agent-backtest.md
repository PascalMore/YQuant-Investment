# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:06:42Z
- jobId: cfd12ff68fa649d7bf3521474e9506f6
- status: succeeded
- runId: 52
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 103.78801370947536
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -17.39423941610876
- sharpeRatio: 1.3898792269413995
- totalReturn: 19.164906714307193
- totalTrades: 307
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "SUI/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 1.5634651626596812, "alphaAnnualized": 1.4729216167917998, "annualizationFactor": 8766.0, "battingAverage": 0.5243168133395091, "battingStatus": "available", "benchmark": "Crypto:SUI/USDT@spot", "benchmarkReturnAnnualized": -0.6226665345315661, "beta": 0.8545874222452028, "betaSpread": 0.03207258642765709, "betaStatus": "available", "captureRatio": 1.074282538701331, "captureStatus": "available", "classification": "exceptional", "correlation": 0.9511657335765332, "correlationStatus": "available", "downBeta": 0.8415380218420092, "downCapture": 0.8187251731192418, "downMarketPeriods": 1108, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 6.625512342111857, "mSquared": 1.0471198077316402, "mSquaredAlpha": 1.6697863422632062, "mSquaredStatus": "available", "observations": 2159, "outperformancePayoffRatio": 1.18558948386826, "outperformancePeriods": 1132, "portfolioReturnAnnualized": 0.9407986281281152, "rSquared": 0.9047162527301846, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 0.2359764923721103, "treynorRatio": 1.100880499336645, "treynorStatus": "available", "underperformancePeriods": 1024, "upBeta": 0.8736106082696663, "upCapture": 0.8795421574772258, "upMarketPeriods": 1038}
- dataProvenance: {"benchmark": {"bars": 2160, "contentHash": "a4e5450b9b362ebacbab72f24c052b6cbe9f8a807636ac05d4707b45b7da9585", "firstBar": "2026-02-03 00:00:00", "instrument": "Crypto:SUI/USDT@spot", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "a4e5450b9b362ebacbab72f24c052b6cbe9f8a807636ac05d4707b45b7da9585"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-05-03T23:59:59", "requestedStart": "2026-02-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2184, "contentHash": "d1672780dd20cf6bf5317df1b9e4beb4eccfc4b8dc0c35b2c8f581a3a6689363", "firstBar": "2026-02-02 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "d1672780dd20cf6bf5317df1b9e4beb4eccfc4b8dc0c35b2c8f581a3a6689363"}], "timeframes": {"1h": [{"bars": 2184, "contentHash": "d1672780dd20cf6bf5317df1b9e4beb4eccfc4b8dc0c35b2c8f581a3a6689363", "firstBar": "2026-02-02 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "d1672780dd20cf6bf5317df1b9e4beb4eccfc4b8dc0c35b2c8f581a3a6689363"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 39.16664524030719
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-05-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-02-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 307 elements
- equityCurve: 1200 elements
- executions: 630 elements
- holdingSnapshots: 600 elements
- liquidationEvents: 0 elements
- logs: 0 elements
- orderLedger: 1430 elements
- protectionEvents: 0 elements
- rebalanceRecords: 800 elements

## Notes

- Agent curve arrays are reported by length only; the gateway samples closedTrades/executions to <=1500 and equity/benchmark curves to <=1200.
- The Agent channel has no sourceId/run read-back route; the persisted run's source_id is NULL by platform contract and is not a failure.
- Unsupported on this channel: grid generate, Strategy Evolution, run/sourceId read-back, agent trading.
