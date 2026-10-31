# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-10-31T03:49:45Z
- jobId: acebd0c543f5424f87692e631973ed77
- status: succeeded
- runId: 26
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 9.398580651146226
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -8.994310506598113
- sharpeRatio: 0.7252570121450364
- totalReturn: 9.338061301531964
- totalTrades: 538
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "SUI/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": 0.7047886298104421, "annualizationFactor": 365.25, "benchmark": "Crypto:SUI/USDT@spot", "benchmarkReturnAnnualized": -0.6056417477151177, "classification": "good", "frequency": "1d", "informationRatio": 0.9236583489695479, "observations": 363, "portfolioReturnAnnualized": 0.09914688209532438, "status": "available", "trackingErrorAnnualized": 0.7630403932327561}
- dataProvenance: {"benchmark": {"bars": 364, "contentHash": "1ce7cbac2eaec7d2ee88c43ab1f8a48cefb4aa5e30d75c87063bb21634ed6f1b", "firstBar": "2025-11-01 00:00:00", "instrument": "Crypto:SUI/USDT@spot", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "1ce7cbac2eaec7d2ee88c43ab1f8a48cefb4aa5e30d75c87063bb21634ed6f1b"}, "frequencies": ["1d"], "frequency": "1d", "kind": "market", "requestedEnd": "2026-10-31T23:59:59", "requestedStart": "2025-11-01T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 368, "contentHash": "8b2f3c549a083ecf277d552b120497c7b883bac692fc3a39acf9c180be343bbc", "firstBar": "2025-10-28 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "8b2f3c549a083ecf277d552b120497c7b883bac692fc3a39acf9c180be343bbc"}], "timeframes": {"1d": [{"bars": 368, "contentHash": "8b2f3c549a083ecf277d552b120497c7b883bac692fc3a39acf9c180be343bbc", "firstBar": "2025-10-28 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "8b2f3c549a083ecf277d552b120497c7b883bac692fc3a39acf9c180be343bbc"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 71.30444785653197
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1d", "endDate": "2026-10-31", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1d"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 1.0, "leverageEnabled": false, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2025-11-01", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 364 elements
- closedTrades: 538 elements
- equityCurve: 364 elements
- executions: 1100 elements
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
