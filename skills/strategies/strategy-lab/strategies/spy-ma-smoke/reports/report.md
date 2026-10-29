# spy-ma-smoke trade report

- generatedAt (UTC): 2026-10-29T15:53:55Z
- classification: failed
- reason: auth.missing

## Budget

- estimateCalls: 0
- estimateShrinks: 0
- evolutionRunLimit: 8
- evolutionRuns: 0
- fullPeriodGroupLimit: 5
- fullPeriodGroups: 0
- internalBacktestRunsReported: None
- outerBacktestJobLimit: 8
- outerBacktestJobs: 0
- relativeUnitsLimit: 8
- wallSecondsLimit: 1200.0
- wallSecondsRemaining: 1170.0

## Limitations and notes

- Stopped before completion; final confirmation incomplete: auth.missing

## Reproduction

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py trade --strategy-dir skills/strategies/strategy-lab/spy-ma-smoke --start 2023-01-01 --end 2025-12-31 --capital 10000.0 --commission 0.0005 --slippage 0.0005 --objective totalReturn --max-drawdown-pct 50.0 --method grid --trials 4 --folds 4 --max-evolution-runs 8 --max-relative-units 8 --wall-seconds 1200.0 --search ma_period:20:80:20
```
