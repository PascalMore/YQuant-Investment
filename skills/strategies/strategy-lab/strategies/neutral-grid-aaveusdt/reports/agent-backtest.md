# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-10-31T03:59:51Z
- jobId: 808356ad67354a77bf4e17122c2909bf
- status: succeeded
- runId: 28
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 13.098380032854184
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -9.335603654266789
- sharpeRatio: 1.3593355462697434
- totalReturn: 13.012656648680455
- totalTrades: 549
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "AAVE/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 0.30997771468412855, "annualizationFactor": 365.25, "benchmark": "Crypto:AAVE/USDT@spot", "benchmarkReturnAnnualized": -0.18247400968952465, "classification": "acceptable", "frequency": "1d", "informationRatio": 0.3835715409311261, "observations": 363, "portfolioReturnAnnualized": 0.12750370499460387, "status": "available", "trackingErrorAnnualized": 0.8081353322815678}
- dataProvenance: {"benchmark": {"bars": 364, "contentHash": "e18e436b71896676e652f074e40e0c5ac4dc9e2c7d810a3169d4f67e5f2513e2", "firstBar": "2025-11-01 00:00:00", "instrument": "Crypto:AAVE/USDT@spot", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "e18e436b71896676e652f074e40e0c5ac4dc9e2c7d810a3169d4f67e5f2513e2"}, "frequencies": ["1d"], "frequency": "1d", "kind": "market", "requestedEnd": "2026-10-31T23:59:59", "requestedStart": "2025-11-01T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 368, "contentHash": "20ca4c034cb50c3596d76eb70cbecaa71a7a29c015d8c9793fd1c0445bd5c3f9", "firstBar": "2025-10-28 00:00:00", "instrument": "Crypto:AAVE/USDT@swap", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "20ca4c034cb50c3596d76eb70cbecaa71a7a29c015d8c9793fd1c0445bd5c3f9"}], "timeframes": {"1d": [{"bars": 368, "contentHash": "20ca4c034cb50c3596d76eb70cbecaa71a7a29c015d8c9793fd1c0445bd5c3f9", "firstBar": "2025-10-28 00:00:00", "instrument": "Crypto:AAVE/USDT@swap", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "20ca4c034cb50c3596d76eb70cbecaa71a7a29c015d8c9793fd1c0445bd5c3f9"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 55.15025980668046
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1d", "endDate": "2026-10-31", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1d"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 1.0, "leverageEnabled": false, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2025-11-01", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 364 elements
- closedTrades: 549 elements
- equityCurve: 364 elements
- executions: 1108 elements
- holdingSnapshots: 364 elements
- liquidationEvents: 0 elements
- logs: 0 elements
- orderLedger: 1500 elements
- protectionEvents: 0 elements
- rebalanceRecords: 363 elements

## Notes

- Agent curve arrays are reported by length only; the gateway samples closedTrades/executions to <=1500 and equity/benchmark curves to <=1200.
- The Agent channel has no sourceId/run read-back route; the persisted run's source_id is NULL by platform contract and is not a failure.
- Unsupported on this channel: grid generate, Strategy Evolution, run/sourceId read-back, agent trading.
