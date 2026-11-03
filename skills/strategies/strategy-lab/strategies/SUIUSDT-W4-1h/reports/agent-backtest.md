# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:07:45Z
- jobId: 061cf7b7633240d799a65bf885e845ba
- status: succeeded
- runId: 56
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: -88.7802927107082
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -60.86551166374321
- sharpeRatio: -0.3765015582448771
- totalReturn: -42.69209204616274
- totalTrades: 445
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "SUI/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 1.7561558016862522, "alphaAnnualized": 3.1723013143346956, "annualizationFactor": 8766.0, "battingAverage": 0.49932765575974897, "battingStatus": "available", "benchmark": "Crypto:SUI/USDT@spot", "benchmarkReturnAnnualized": -2.4151578987639897, "beta": 1.586357319897464, "betaSpread": 0.18361227099226674, "betaStatus": "available", "captureRatio": 1.0528361995838802, "captureStatus": "available", "classification": "exceptional", "correlation": 0.8773698097075732, "correlationStatus": "available", "downBeta": 1.5391016661823056, "downCapture": 1.4992497722505864, "downMarketPeriods": 1142, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": 1.7320873157740435, "mSquared": -0.36447560537455603, "mSquaredAlpha": 2.0506822933894338, "mSquaredStatus": "available", "observations": 2231, "outperformancePayoffRatio": 1.082648943136197, "outperformancePeriods": 1114, "portfolioReturnAnnualized": -0.6590020970777379, "rSquared": 0.7697777829863032, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 1.0138956539275001, "treynorRatio": -0.41541844880214834, "treynorStatus": "available", "underperformancePeriods": 1117, "upBeta": 1.7227139371745723, "upCapture": 1.5784644324433053, "upMarketPeriods": 1076}
- dataProvenance: {"benchmark": {"bars": 2232, "contentHash": "8782be0dcdafb754625385951967356b71a7d9f5f6502bad19fbf1cc95b80e18", "firstBar": "2025-11-03 00:00:00", "instrument": "Crypto:SUI/USDT@spot", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "8782be0dcdafb754625385951967356b71a7d9f5f6502bad19fbf1cc95b80e18"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-02-03T23:59:59", "requestedStart": "2025-11-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2256, "contentHash": "85790c75bfcffc2e5300b0a75dc9028eb93ff192ee0fb7b30b0e31e326ad7d02", "firstBar": "2025-11-02 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "85790c75bfcffc2e5300b0a75dc9028eb93ff192ee0fb7b30b0e31e326ad7d02"}], "timeframes": {"1h": [{"bars": 2256, "contentHash": "85790c75bfcffc2e5300b0a75dc9028eb93ff192ee0fb7b30b0e31e326ad7d02", "firstBar": "2025-11-02 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-02-03 23:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "85790c75bfcffc2e5300b0a75dc9028eb93ff192ee0fb7b30b0e31e326ad7d02"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 9.320331921837258
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-02-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2025-11-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 445 elements
- equityCurve: 1200 elements
- executions: 936 elements
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
