# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:03:58Z
- jobId: 5aded2b96ba54444b18c7df53fbb66a0
- status: succeeded
- runId: 42
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 1462.3498089107136
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -10.18129568016648
- sharpeRatio: 5.652720856053983
- totalReturn: 101.22762748978498
- totalTrades: 989
- winRate: 97.67441860465115

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "PUMP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": -1.0139244285368831, "alphaAnnualized": 2.223222303918389, "annualizationFactor": 8766.0, "battingAverage": 0.4928251121076233, "battingStatus": "available", "benchmark": "Crypto:PUMP/USDT@spot", "benchmarkReturnAnnualized": 3.892846980983236, "beta": 0.1684372007764741, "betaSpread": -0.04143372679546341, "betaStatus": "available", "captureRatio": 1.2477580539706747, "captureStatus": "available", "classification": "weak", "correlation": 0.4586651785628729, "correlationStatus": "available", "downBeta": 0.15736586791844406, "downCapture": 0.17812571881599112, "downMarketPeriods": 1075, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": -0.8182393337692512, "mSquared": 7.839488666988816, "mSquaredAlpha": 3.9466416860055804, "mSquaredStatus": "available", "observations": 2230, "outperformancePayoffRatio": 0.999847555330329, "outperformancePeriods": 1099, "portfolioReturnAnnualized": 2.8789225524463533, "rSquared": 0.2103737460261121, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 1.2391538596246663, "treynorRatio": 17.09196388431348, "treynorStatus": "available", "underperformancePeriods": 1129, "upBeta": 0.11593214112298066, "upCapture": 0.2222578002719687, "upMarketPeriods": 1132}
- dataProvenance: {"benchmark": {"bars": 2231, "contentHash": "9a0765950f57daef8eb464ffb029faf4959b487604d3046063df8681b0f1ac5a", "firstBar": "2026-08-03 00:00:00", "instrument": "Crypto:PUMP/USDT@spot", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "9a0765950f57daef8eb464ffb029faf4959b487604d3046063df8681b0f1ac5a"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-11-03T23:59:59", "requestedStart": "2026-08-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2255, "contentHash": "76e4fba0ea968d3a5114e092c33a3c511c5f24150c712cec5fd5013d72cbcf95", "firstBar": "2026-08-02 00:00:00", "instrument": "Crypto:PUMP/USDT@swap", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "76e4fba0ea968d3a5114e092c33a3c511c5f24150c712cec5fd5013d72cbcf95"}], "timeframes": {"1h": [{"bars": 2255, "contentHash": "76e4fba0ea968d3a5114e092c33a3c511c5f24150c712cec5fd5013d72cbcf95", "firstBar": "2026-08-02 00:00:00", "instrument": "Crypto:PUMP/USDT@swap", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "76e4fba0ea968d3a5114e092c33a3c511c5f24150c712cec5fd5013d72cbcf95"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: -9.680589713215014
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-11-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-08-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 989 elements
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
