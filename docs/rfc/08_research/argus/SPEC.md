# Argus Unified Zone Rule SPEC

Status: Phase 1 and Phase 2 implemented; Phase 3 pending.

## Unified Configuration

`skills/research/argus/config/zone_rules_template.yaml` is the single source of truth for Argus signal-pool initial classification and Portfolio stock-pool transitions. Runtime code loads it through `skills.research.argus.config.zone_rules.load_zone_rules_config()` and consumes it through `ZoneRuleEngine`.

Required top-level fields are `version`, `zones`, `score_policy`, `argus_signal_pool`, and `portfolio_transitions`.

## Zone Classification

Initial Argus classification uses `bayesian_score` as the primary score after Bayesian scoring has completed:

| Zone | Bayesian | Products | Consensus | Crowding |
| --- | ---: | ---: | ---: | --- |
| `CONVICTION` | `>= 0.75` | `>= 3` | `>= 0.60` | `<= HIGH` |
| `CANDIDATE` | `>= 0.55` | `>= 2` | `>= 0.40` | `<= DANGER` |
| `WATCH` | `>= 0.35` | `>= 1` | `>= 0.20` | no limit |
| `SCAN` | residual | residual | residual | no limit |

`SCAN` is an unconditional residual zone. A high score that fails product, consensus, or crowding gates falls through to the next matching rule.

## Darwin Ordering

Darwin sector events are detected before signal-pool records are built. The `darwin_moment`, `darwin_confidence`, and `darwin_event_id` fields are attached before Bayesian scoring, then preserved during Bayesian scoring and zone classification.

Darwin override is floor-only: when `darwin_moment=True` and the guard passes (`bayesian_score >= 0.45` or `darwin_confidence >= 0.70`), the record is floored to `CANDIDATE`. Darwin never forces `CONVICTION`; regular `CONVICTION` thresholds must still pass.

## Daily Computation Order

The daily processor order is now:

```text
signals -> consensus -> crowding -> build signal-pool records -> BayesianScorer -> ZoneRuleEngine.classify_initial_zone() -> write
```

This replaces the old confidence-based pre-Bayesian classification and ensures all Argus and Portfolio zone decisions share the same `bayesian_score` thresholds.

## Portfolio Transitions

Portfolio transitions are one-step per run:

| Promotion | Bayesian | Products | Consensus | Crowding |
| --- | ---: | ---: | ---: | --- |
| `SCAN -> WATCH` | `>= 0.35` | `>= 1` | `>= 0.20` | no limit |
| `WATCH -> CANDIDATE` | `>= 0.55` | `>= 2` | `>= 0.40` | `<= DANGER` |
| `CANDIDATE -> CONVICTION` | `>= 0.75` | `>= 3` | `>= 0.60` | `<= HIGH` |

Demotion uses independent retention thresholds, not promotion thresholds. This hysteresis reduces churn around zone boundaries:

| Current Zone | Retention | Demote Target |
| --- | --- | --- |
| `WATCH` | Bayesian `>= 0.25`, products `>= 1`, consensus `>= 0.10` | `SCAN` |
| `CANDIDATE` | Bayesian `>= 0.48`, products `>= 1`, consensus `>= 0.30`, crowding `<= DANGER` | `WATCH` |
| `CONVICTION` | Bayesian `>= 0.68`, products `>= 2`, consensus `>= 0.50`, crowding `<= HIGH` | `CANDIDATE` |

`exit` is lifecycle inactive and is triggered only by `missing_from_current_signal_pool`. It is not a demotion to `SCAN`.

## Implementation Status

Phase 1: implemented. `PoolManager` and `StockPoolAutoPromoter` now depend on `ZoneRuleEngine`, which reads YAML-backed thresholds.

Phase 2: implemented. `daily_processor.py` scores signal-pool records with `BayesianScorer` before zone classification.

Phase 3: pending. Remaining follow-up is broader runtime migration and regression validation across historical daily runs and Portfolio ingestion audit diffs.

