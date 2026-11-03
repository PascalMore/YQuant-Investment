# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:05:05Z
- jobId: 49afd815ade9431da53c8a61593e321f
- status: succeeded
- runId: 46
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 457.1470498377874
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -54.97826711425973
- sharpeRatio: 1.8555780909559778
- totalReturn: 54.82954348058635
- totalTrades: 464
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "PUMP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 2.2579767607246986, "alphaAnnualized": 1.6421836292778793, "annualizationFactor": 8766.0, "battingAverage": 0.5011205737337516, "battingStatus": "available", "benchmark": "Crypto:PUMP/USDT@spot", "benchmarkReturnAnnualized": 1.3034077025253803, "beta": 1.4724485901485065, "betaSpread": -0.09334570209580106, "betaStatus": "available", "captureRatio": 1.0199149523863091, "captureStatus": "available", "classification": "exceptional", "correlation": 0.8753855391979712, "correlationStatus": "available", "downBeta": 1.5825511989696146, "downCapture": 1.4011016496244857, "downMarketPeriods": 1107, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 2.103750016354854, "mSquared": 2.1172789865206894, "mSquaredAlpha": 0.8138712839953091, "mSquaredStatus": "available", "observations": 2231, "outperformancePayoffRatio": 1.0613412687935142, "outperformancePeriods": 1118, "portfolioReturnAnnualized": 3.5613844632500795, "rSquared": 0.7662998422369228, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 1.0733103948524605, "treynorRatio": 2.418681702762125, "treynorStatus": "available", "underperformancePeriods": 1099, "upBeta": 1.4892054968738135, "upCapture": 1.4290045222651366, "upMarketPeriods": 1065}
- dataProvenance: {"benchmark": {"bars": 2232, "contentHash": "6a8d7e71c1644b253ecb3e56158a6c0c8dbee769fd04c37c2b9f44b1e138768e", "firstBar": "2026-05-03 00:00:00", "instrument": "Crypto:PUMP/USDT@spot", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "6a8d7e71c1644b253ecb3e56158a6c0c8dbee769fd04c37c2b9f44b1e138768e"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-08-03T23:59:59", "requestedStart": "2026-05-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2256, "contentHash": "597f7b8dc0a6c7e8e2a04927bbb62fe752b49536c7fd04bd3f1db8a67dc4463c", "firstBar": "2026-05-02 00:00:00", "instrument": "Crypto:PUMP/USDT@swap", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "597f7b8dc0a6c7e8e2a04927bbb62fe752b49536c7fd04bd3f1db8a67dc4463c"}], "timeframes": {"1h": [{"bars": 2256, "contentHash": "597f7b8dc0a6c7e8e2a04927bbb62fe752b49536c7fd04bd3f1db8a67dc4463c", "firstBar": "2026-05-02 00:00:00", "instrument": "Crypto:PUMP/USDT@swap", "lastBar": "2026-08-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "597f7b8dc0a6c7e8e2a04927bbb62fe752b49536c7fd04bd3f1db8a67dc4463c"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 36.733251283586355
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-08-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-05-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 464 elements
- equityCurve: 1200 elements
- executions: 933 elements
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
