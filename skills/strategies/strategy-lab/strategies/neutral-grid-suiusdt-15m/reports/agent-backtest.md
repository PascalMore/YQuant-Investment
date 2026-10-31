# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-10-31T06:45:56Z
- jobId: f380de784bae4fc49f6056f3d6ba3bd4
- status: succeeded
- runId: 38
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 12.387151784832
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -4.179343919412137
- sharpeRatio: 1.2198960826452654
- totalReturn: 2.961149048480838
- totalTrades: 452
- winRate: 100.0

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "SUI/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": -1.3606002616880084, "annualizationFactor": 8766.0, "benchmark": "Crypto:SUI/USDT@spot", "benchmarkReturnAnnualized": 1.4792650957795568, "classification": "weak", "frequency": "1h", "informationRatio": -1.5548605014449686, "observations": 2188, "portfolioReturnAnnualized": 0.11866483409154861, "status": "available", "trackingErrorAnnualized": 0.8750625927043426}
- dataProvenance: {"benchmark": {"bars": 2189, "contentHash": "c53bb435e700ba34edfe2b10bd8958e6730b3ad11793195f4740b1630c9e39d3", "firstBar": "2026-08-01 00:00:00", "instrument": "Crypto:SUI/USDT@spot", "lastBar": "2026-10-31 04:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "c53bb435e700ba34edfe2b10bd8958e6730b3ad11793195f4740b1630c9e39d3"}, "frequencies": ["15m"], "frequency": "15m", "kind": "market", "requestedEnd": "2026-10-31T23:59:59", "requestedStart": "2026-08-01T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 8859, "contentHash": "132fcd21bdae4149bcf5f7e6743671bf09ce611eae29c7cb12c21aeaae0747a2", "firstBar": "2026-07-31 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-10-31 06:30:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "132fcd21bdae4149bcf5f7e6743671bf09ce611eae29c7cb12c21aeaae0747a2"}], "timeframes": {"15m": [{"bars": 8859, "contentHash": "132fcd21bdae4149bcf5f7e6743671bf09ce611eae29c7cb12c21aeaae0747a2", "firstBar": "2026-07-31 00:00:00", "instrument": "Crypto:SUI/USDT@swap", "lastBar": "2026-10-31 06:30:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "132fcd21bdae4149bcf5f7e6743671bf09ce611eae29c7cb12c21aeaae0747a2"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: -28.04206826651916
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "15m", "endDate": "2026-10-31", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["15m"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 10000.0, "intrabarMode": "conservative", "leverage": 1.0, "leverageEnabled": false, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2026-08-01", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 1200 elements
- closedTrades: 452 elements
- equityCurve: 1200 elements
- executions: 929 elements
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
