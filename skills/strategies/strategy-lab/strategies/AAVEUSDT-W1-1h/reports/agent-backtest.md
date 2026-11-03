# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-11-03T23:04:14Z
- jobId: 38ba938025394d839d311ce76cd492fa
- status: succeeded
- runId: 43
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 22.746927996558856
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -28.75675996712401
- sharpeRatio: 0.658745790654815
- totalReturn: 5.352195332104692
- totalTrades: 342
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "AAVE/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": -1.2852786197246073, "alphaAnnualized": -0.3841540856734648, "annualizationFactor": 8766.0, "battingAverage": 0.5058295964125561, "battingStatus": "available", "benchmark": "Crypto:AAVE/USDT@spot", "benchmarkReturnAnnualized": 1.6221436393564586, "beta": 0.4444853635719713, "betaSpread": -0.2499178702713562, "betaStatus": "available", "captureRatio": 0.9653941176495463, "captureStatus": "available", "classification": "weak", "correlation": 0.720886030133157, "correlationStatus": "available", "downBeta": 0.539746361069545, "downCapture": 0.5017121653249861, "downMarketPeriods": 1118, "dualBetaStatus": "available", "frequency": "1h", "informationRatio": -2.2106618886218348, "mSquared": 0.5463425943693923, "mSquaredAlpha": -1.0758010449870663, "mSquaredStatus": "available", "observations": 2230, "outperformancePayoffRatio": 0.9016973346991026, "outperformancePeriods": 1128, "portfolioReturnAnnualized": 0.3368650196318514, "rSquared": 0.5196766684411429, "riskFreeRate": 0.0, "riskFreeRateSource": "default_zero", "status": "available", "trackingErrorAnnualized": 0.581399908479841, "treynorRatio": 0.7578765179684168, "treynorStatus": "available", "underperformancePeriods": 1101, "upBeta": 0.2898284907981888, "upCapture": 0.48434997315795825, "upMarketPeriods": 1102}
- dataProvenance: {"benchmark": {"bars": 2231, "contentHash": "41bfa2d6fef80efd3b5e7f552d6b903e4d7585874aab3ce32815919fc1263018", "firstBar": "2026-08-03 00:00:00", "instrument": "Crypto:AAVE/USDT@spot", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "41bfa2d6fef80efd3b5e7f552d6b903e4d7585874aab3ce32815919fc1263018"}, "frequencies": ["1h"], "frequency": "1h", "kind": "market", "requestedEnd": "2026-11-03T23:59:59", "requestedStart": "2026-08-03T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 2255, "contentHash": "11394417cbdb5cff7f0e93cbc653f0678e5d9670993223dd362d783fcb386472", "firstBar": "2026-08-02 00:00:00", "instrument": "Crypto:AAVE/USDT@swap", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "11394417cbdb5cff7f0e93cbc653f0678e5d9670993223dd362d783fcb386472"}], "timeframes": {"1h": [{"bars": 2255, "contentHash": "11394417cbdb5cff7f0e93cbc653f0678e5d9670993223dd362d783fcb386472", "firstBar": "2026-08-02 00:00:00", "instrument": "Crypto:AAVE/USDT@swap", "lastBar": "2026-11-03 22:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "11394417cbdb5cff7f0e93cbc653f0678e5d9670993223dd362d783fcb386472"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: -33.096775367895304
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1h", "endDate": "2026-11-03", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1h"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 10.0, "leverageEnabled": true, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-08-03", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Leverage read-back

- requested: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- readBack: initialCapital=1000.0, leverageEnabled=true, leverage=10.0
- verdict: consistent

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 342 elements
- equityCurve: 1200 elements
- executions: 710 elements
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
