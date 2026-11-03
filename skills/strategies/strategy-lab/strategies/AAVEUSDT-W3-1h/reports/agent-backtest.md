# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:06:27Z
- jobId: a1ddab22d1b349d2aab1133ac5859b54
- status: succeeded
- runId: 51
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 87.46047561935725
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -32.73940498331852
- sharpeRatio: 1.1513840452217006
- totalReturn: 16.738904680679646
- totalTrades: 360
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "AAVE/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 2.0007992222390074, "alphaAnnualized": 1.9509613666510774, "annualizationFactor": 8766.0, "battingAverage": 0.5178323297823066, "battingStatus": "available", "benchmark": "Crypto:AAVE/USDT@spot", "benchmarkReturnAnnualized": -0.9759416161080253, "beta": 0.9489335686014917, "betaSpread": 0.06444880235447181, "betaStatus": "available", "captureRatio": 1.0766738389064612, "captureStatus": "available", "classification": "exceptional", "correlation": 0.8832904439818077, "correlationStatus": "available", "downBeta": 0.8987995114656341, "downCapture": 0.9336324209725846, "downMarketPeriods": 1102, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 4.768995388963353, "mSquared": 0.9539623846079046, "mSquaredAlpha": 1.92990400071593, "mSquaredStatus": "available", "observations": 2159, "outperformancePayoffRatio": 1.1036984102691947, "outperformancePeriods": 1118, "portfolioReturnAnnualized": 1.024857606130982, "rSquared": 0.7802020084295789, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 0.41954312366695856, "treynorRatio": 1.0800098553172535, "treynorStatus": "available", "underperformancePeriods": 1041, "upBeta": 0.9632483138201059, "upCapture": 1.005217602816086, "upMarketPeriods": 1047}
- dataProvenance: {"benchmark": {"bars": 2160, "contentHash": "2f1cd8059c8c474da30a02fbaef91c4022b65bca5f544d12d842d5bf9c1003b7", "firstBar": "2026-02-03 00:00:00", "instrument": "Crypto:AAVE/USDT@spot", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "2f1cd8059c8c474da30a02fbaef91c4022b65bca5f544d12d842d5bf9c1003b7"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-05-03T23:59:59", "requestedStart": "2026-02-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2184, "contentHash": "aa48fa142c46dfe9c75abd31c8d115f04c2e25618222566057cb127428145fdc", "firstBar": "2026-02-02 00:00:00", "instrument": "Crypto:AAVE/USDT@swap", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "aa48fa142c46dfe9c75abd31c8d115f04c2e25618222566057cb127428145fdc"}], "timeframes": {"1h": [{"bars": 2184, "contentHash": "aa48fa142c46dfe9c75abd31c8d115f04c2e25618222566057cb127428145fdc", "firstBar": "2026-02-02 00:00:00", "instrument": "Crypto:AAVE/USDT@swap", "lastBar": "2026-05-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "aa48fa142c46dfe9c75abd31c8d115f04c2e25618222566057cb127428145fdc"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 44.49107281867964
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-05-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-02-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 360 elements
- equityCurve: 1200 elements
- executions: 741 elements
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
