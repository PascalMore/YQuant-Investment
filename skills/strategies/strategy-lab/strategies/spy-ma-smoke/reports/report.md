# spy-ma-smoke trade report

- generatedAt (UTC): 2026-10-30T04:22:50Z
- classification: candidate
- reason: qualifiedCandidateSelected
- baselineRunId: 20
- evolutionJobId: ed7d09e76a484028acd330969bff1190
- finalRunId: 24
- jobIds: ["dc86af40e2924d659dbfd8f9975df7ac", "bb9de6e3657445b0b8bdaf4ae9b6e804", "a634ef7a7be44f168c2cce2aedd695bf", "82cc28199cf64cc08462b6ab92c6dd07", "1f3f1e06caeb41b1a58205898e68fb60"]
- runIds: [21, 22, 23]
- sourceId: 4
- recommendedParams: {"ma_period": 80, "target_pct": 0.95}
- estimate: {"backtestRuns": 6, "folds": 4, "isUpperBound": false, "relativeUnits": 6, "shrinks": 0}

## Checks

- baseline: PASS (allChecksPassed)

## Budget

- estimateCalls: 1
- estimateShrinks: 0
- evolutionRunLimit: 8
- evolutionRuns: 1
- fullPeriodGroupLimit: 5
- fullPeriodGroups: 4
- internalBacktestRunsReported: 6
- outerBacktestJobLimit: 8
- outerBacktestJobs: 5
- relativeUnitsLimit: 8
- wallSecondsLimit: 1200.0
- wallSecondsRemaining: 1063.6

## Limitations and notes

- Native OOS/blind evidence: {"selection": {"blindPassed": true, "blindUsedForSelection": false, "objective": "oosCompoundedReturn", "overfitControl": "chronologicalWalkForward", "recommended": true}, "summary": {"actualBacktestRuns": 6, "availableChecks": 4, "bestScore": 19.5219, "blindActivity": 29.0, "blindPassed": true, "blindReturn": 3.1529781195476225, "candidateAttempts": 4, "completedTrials": 3, "constraintRejectedTrials": 0, "coveragePercent": 100.0, "decayRate": 0.0, "duplicateTrials": 0, "elapsedSeconds": 10.83, "evaluatedTrials": 4, "maxDrawdown": 6.4249, "minimumRecommendedTrials": 4, "oosReturn": 19.5219, "oosSharpe": 1.1958, "overfitRejectedTrials": 1, "positiveValidationFolds": 3, "profitableFoldRate": 75.0, "prunedTrials": 1, "recommended": true, "requestedTrials": 4, "robustnessGrade": "C", "robustnessScore": 52.51, "sampleSufficient": true, "searchSpaceSize": 4, "selectionObjective": "oosCompoundedReturn", "totalChecks": 4, "validationFolds": 4}, "validation": {"costStress": [{"activity": 29.0, "commission": 0.0005, "drawdown": -8.789800273377235, "multiplier": 1.0, "return": 3.1529781195476225, "returnDelta": 0.0, "samples": 323.0, "sharpe": 0.30704619929211957, "slippage": 0.0005, "trades": 14.0, "valid": 1.0, "winRate": 35.714285714285715}, {"activity": 29.0, "commission": 0.001, "drawdown": -9.77581463983106, "multiplier": 2.0, "return": 0.5402970751679614, "returnDelta": -2.612681, "samples": 323.0, "sharpe": 0.09200032362776606, "slippage": 0.001, "trades": 14.0, "valid": 1.0, "winRate": 21.428571428571427}], "deflatedSharpe": {"available": true, "benchmarkSharpe": 0.029497, "kurtosis": 7.586079, "observations": 849, "observedSharpe": 0.044412, "probability": 0.666837, "skew": -0.253966}, "monteCarlo": {"available": true, "drawdownPercentiles": {"1": -27.3476, "25": -16.5108, "5": -22.2191, "50": -12.9835, "75": -10.2946, "95": -7.7775, "99": -5.3565}, "effectiveBlockSize": 5, "lossProbability": 0.08, "observations": 849, "paths": 100, "percentiles": {"1": -7.9002, "25": 11.0071, "5": -4.5241, "50": 25.4028, "75": 40.4835, "95": 64.3855, "99": 86.0228}, "requestedBlockSize": 5, "terminalReturns": [{"count": 1, "value": -19.5702}, {"count": 0, "value": -14.8968}, {"count": 0, "value": -10.2233}, {"count": 6, "value": -5.5498}, {"count": 4, "value": -0.8763}, {"count": 7, "value": 3.7971}, {"count": 5, "value": 8.4706}, {"count": 8, "value": 13.1441}, {"count": 10, "value": 17.8176}, {"count": 7, "value": 22.491}, {"count": 12, "value": 27.1645}, {"count": 10, "value": 31.838}, {"count": 3, "value": 36.5114}, {"count": 4, "value": 41.1849}, {"count": 4, "value": 45.8584}, {"count": 5, "value": 50.5319}, {"count": 3, "value": 55.2053}, {"count": 3, "value": 59.8788}, {"count": 3, "value": 64.5523}, {"count": 2, "value": 69.2258}, {"count": 0, "value": 73.8992}, {"count": 1, "value": 78.5727}, {"count": 0, "value": 83.2462}, {"count": 2, "value": 87.9196}], "uniqueTerminalReturns": 100}, "pbo": {"available": true, "logits": [-1.09861, -1.09861, -1.09861, -1.09861, -1.09861, -1.09861], "medianLogit": -1.098612, "probability": 1.0, "samples": 6}}}
- Native summary.maxDrawdown is validation-fold mean, not the full-period MDD constraint.
- Folds reuse one replay sliced in time, not per-fold retraining; full-period selection leaves no untouched holdout.
- Source: QuantDinger full-period data.result; fundingMode=not_modeled is disclosed and only inapplicable for verified unlevered direct equity.
- Turnover and information ratio: not provided/verified; no fabricated zero values.

## Reproduction

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python skills/strategies/strategy-lab/scripts/quantdinger.py trade --strategy-dir skills/strategies/strategy-lab/strategies/spy-ma-smoke --source-id 4 --start 2017-06-01 --end 2025-12-31 --capital 10000.0 --commission 0.0005 --slippage 0.0005 --objective totalReturn --max-drawdown-pct 50.0 --method grid --trials 4 --folds 4 --max-evolution-runs 8 --max-relative-units 8 --wall-seconds 1200.0 --search ma_period:20:80:20
```
