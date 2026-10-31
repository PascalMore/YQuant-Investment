# Strategy Lab agent backtest report

- generatedAt (UTC): 2026-10-31T03:59:35Z
- jobId: 2c736dcfa77f44438b85678228b7eb92
- status: succeeded
- runId: 27
- kind: backtest
- idempotentReplay: False
- billing: present
- sourceAssociation: none: agent channel has no sourceId/run read-back route

## Metrics (Agent flat job result)

- annualizedReturn: 16.82593359413348
- annualizedReturnAvailable: true
- annualizedReturnCapped: false
- maxDrawdown: -7.349840412529063
- sharpeRatio: 1.2745490776462725
- totalReturn: 16.714068257855462
- totalTrades: 715
- winRate: 99.72027972027972

## Server injected context

- benchmark: {"exchange_id": "", "instrument_id": "", "market": "Crypto", "market_type": "spot", "symbol": "PUMP/USDT"}
- benchmarkRelativeMetrics: {"activeReturnAnnualized": -0.46555933427831325, "annualizationFactor": 365.25, "benchmark": "Crypto:PUMP/USDT@spot", "benchmarkReturnAnnualized": 0.6293649879190704, "classification": "weak", "frequency": "1d", "informationRatio": -0.40299439347610394, "observations": 363, "portfolioReturnAnnualized": 0.16380565364075697, "status": "available", "trackingErrorAnnualized": 1.1552501519004859}
- dataProvenance: {"benchmark": {"bars": 364, "contentHash": "2bb574b572575c9a9b2fc8dd8f125a85493b0b04321a528ab741711c994f8650", "firstBar": "2025-11-01 00:00:00", "instrument": "Crypto:PUMP/USDT@spot", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "2bb574b572575c9a9b2fc8dd8f125a85493b0b04321a528ab741711c994f8650"}, "frequencies": ["1d"], "frequency": "1d", "kind": "market", "requestedEnd": "2026-10-31T23:59:59", "requestedStart": "2025-11-01T00:00:00", "source": "system_market_data_router", "symbols": [{"bars": 368, "contentHash": "439fe1c72f7b6986547f5aa53727728a4976e13f869224776d37b2d7bc37f247", "firstBar": "2025-10-28 00:00:00", "instrument": "Crypto:PUMP/USDT@swap", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "439fe1c72f7b6986547f5aa53727728a4976e13f869224776d37b2d7bc37f247"}], "timeframes": {"1d": [{"bars": 368, "contentHash": "439fe1c72f7b6986547f5aa53727728a4976e13f869224776d37b2d7bc37f247", "firstBar": "2025-10-28 00:00:00", "instrument": "Crypto:PUMP/USDT@swap", "lastBar": "2026-10-30 00:00:00", "snapshotFormat": "strategy-v2-ohlcv-json-gzip-v1", "snapshotId": "439fe1c72f7b6986547f5aa53727728a4976e13f869224776d37b2d7bc37f247"}]}}
- diagnostics: {"sourceControlled": true, "symbolsRequested": 1, "symbolsSkipped": [], "symbolsUsed": 1, "universeId": null}
- excessReturn: 27.096288571855464
- executionAssumptions: {"barClosePolicy": "closed_bars_only", "commission": 0.0005, "corporateActionsMode": "venue_price_series", "cryptoRebalanceToleranceQuote": 10.0, "drivingFrequency": "1d", "endDate": "2026-10-31", "engineVersion": "quantdinger-strategy-api-v2", "exchangeEquityProducts": [], "fillRule": "scheduled_current_open_or_signal_next_open", "frequencies": ["1d"], "fundingMode": "not_modeled", "higherTimeframePolicy": "completed_before_driving_bar_close", "initialCapital": 1000.0, "intrabarMode": "conservative", "leverage": 1.0, "leverageEnabled": false, "preFillValuationRule": "explicit_fill_or_current_open_then_last_completed_close-v1", "protectionRule": "gap_open_then_intrabar_trigger", "slippage": 0.0005, "startDate": "2025-11-01", "subLotClosePolicy": "reconcile_up_to_10_quote_with_cash_and_fees"}
- resultStatus: "completed_trades"

## Sampled arrays (gateway bounded sample, not the full series)

- benchmarkCurve: 364 elements
- closedTrades: 715 elements
- equityCurve: 364 elements
- executions: 1420 elements
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
