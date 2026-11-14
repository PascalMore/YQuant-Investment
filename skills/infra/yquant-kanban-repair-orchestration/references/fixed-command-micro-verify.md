# Fixed-command micro Verify after Kanban iteration-budget timeout

## Trigger

Use this only when a read-only Implement reconciliation or independent Verify has timed out for **iteration budget / agent-loop reasons**, not due to a reproducible test or contract failure, and the orchestrator has already independently calibrated the candidate working-tree artifact.

## Preconditions

1. Freeze each old auto-retrying card with `kanban_block(kind="transient")`; add a durable comment naming its timeout and replacement.
2. Confirm by real commands: exact allowlist including untracked files, staged-empty status, `git diff --check`, compilation of new Python files, and the targeted test count.
3. Preserve the old cards as audit history. Do not call them PASS and do not mutate/reset the shared tree.
4. A regular Verify card may have a completed Design parent directly. Its body must explicitly say it verifies a timeout-resident **candidate artifact**, not a formally completed Implement card.

## Replacement design

Create one tester-owned micro-card. Keep its body short enough to fit one response. It must require the tester's first response to run exactly these four kinds of checks:

1. Targeted pytest command (the same candidate test set, independently rerun).
2. `git diff --check` plus syntax/compile checks for untracked new Python files.
3. Exact seven-or-N path status audit plus staged audit.
4. A short local static-assertion script for the critical prohibited dependencies/default injection path.

No document rereads, architecture restatement, broad repository scans, real clocks/calendars, network, Provider, Mongo, cache, or production actions.

## Verdict gate

- **PASS** only if all four commands ran successfully and the tester records real test count, exact candidate scope, staged status, static-check count, and `production_injection=false` / zero side effects.
- **FAIL** on any failed command, scope mismatch, prohibited dependency, or real-I/O behavior. Block with evidence; do not repair.
- After PASS, create a separately assigned reviewer card. It still must report `open_blocker=0`, `open_major=0`, and `open_minor=0` before Closeout.

## Anti-patterns

- Repeating a long reconciliation/Verify card after it already exhausted its iteration budget.
- Treating timeout as either code failure or verification PASS.
- Letting a developer perform the independent Verify.
- Creating a third developer reconciliation when the candidate is already calibrated and needs independent test evidence, not another handoff narrative.
