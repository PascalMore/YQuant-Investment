# P3-P0 Baseline Drift: Condensed Case Record

## Pattern

A Design amendment treated a 22-field sentiment domain object, its `from_dict()`, canonical stub, fixture, and regression test as pending T3 work. The current shared tree and an independent 792-test regression already proved them complete as offline baseline.

## Corrective sequence

1. Design-only P0 correction reclassified the verified artifacts as existing baseline.
2. T3 scope was reduced to actual gaps: expected field definitions, mirror equivalence, refresh guard semantics, mapping tests, and twin-equivalence tests.
3. A remaining RFC/SPEC P0 checkbox still described the 22-field implementation as “not yet”; this correctly blocked Implement.
4. The right next task was a principal-owned RFC/SPEC amendment, followed by Design consistency review, then Implement.

## Durable lesson

An allowlist is a plan, not proof. Before a developer receives it, every listed artifact needs a current-tree and verification-evidence check. Status changes must be synchronized across all three document layers; Design-only correction is insufficient when RFC/SPEC retain contradictory lifecycle language.

## Non-goals retained

No real Provider/API calls, Mongo access, DDL/DML, refresh happy-path, canary, service restart, or cron activity was implied by the offline baseline.
