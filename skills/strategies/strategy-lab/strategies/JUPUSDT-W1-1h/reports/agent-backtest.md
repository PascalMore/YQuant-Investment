# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:03:14Z
- jobId: a7069d0571a2476f91dbc32680b1a1c5
- status: succeeded
- runId: 41
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 335.72711477826533
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -15.869220310470078
- sharpeRatio: 3.5911826862250673
- totalReturn: 45.415619303120195
- totalTrades: 534
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "JUP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 0.048047316893767664, "alphaAnnualized": 1.107661042998967, "annualizationFactor": 8766.0, "battingAverage": 0.5080717488789238, "battingStatus": "available", "benchmark": "Crypto:JUP/USDT@spot", "benchmarkReturnAnnualized": 1.5192720460048255, "beta": 0.30255168658461984, "betaSpread": -0.030180514350526932, "betaStatus": "available", "captureRatio": 1.1022131460828588, "captureStatus": "available", "classification": "weak", "correlation": 0.7069255620672419, "correlationStatus": "available", "downBeta": 0.27275076951225397, "downCapture": 0.3313298103916458, "downMarketPeriods": 1094, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 0.06195681617382582, "mSquared": 3.6621118661193517, "mSquaredAlpha": 2.142839820114526, "mSquaredStatus": "available", "observations": 2230, "outperformancePayoffRatio": 0.9632310732496112, "outperformancePeriods": 1133, "portfolioReturnAnnualized": 1.567319362898593, "rSquared": 0.49974375030408585, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 0.7754968679953839, "treynorRatio": 5.180335897616072, "treynorStatus": "available", "underperformancePeriods": 1089, "upBeta": 0.24257025516172703, "upCapture": 0.36519607270281296, "upMarketPeriods": 1083}
- dataProvenance: {"benchmark": {"bars": 2231, "contentHash": "13216cefaa1e5c617794933f86c83ee366fa742a3f974e4523e0c5ade8552f93", "firstBar": "2026-08-03 00:00:00", "instrument": "Crypto:JUP/USDT@spot", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "13216cefaa1e5c617794933f86c83ee366fa742a3f974e4523e0c5ade8552f93"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-11-03T23:59:59", "requestedStart": "2026-08-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2255, "contentHash": "b49c7c03680a3214509d6d54faeb5c167cf59d53e2a1c9985ab163abde60d1e0", "firstBar": "2026-08-02 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "b49c7c03680a3214509d6d54faeb5c167cf59d53e2a1c9985ab163abde60d1e0"}], "timeframes": {"1h": [{"bars": 2255, "contentHash": "b49c7c03680a3214509d6d54faeb5c167cf59d53e2a1c9985ab163abde60d1e0", "firstBar": "2026-08-02 00:00:00", "instrument": "Crypto:JUP/USDT@swap", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "b49c7c03680a3214509d6d54faeb5c167cf59d53e2a1c9985ab163abde60d1e0"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 16.483179901120184
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-11-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-08-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 534 elements
- equityCurve: 1200 elements
- executions: 1088 elements
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
