# Timeout Candidate Reconciliation

Use when an Implement card times out with no structured handoff but leaves candidate files in a shared `dir` workspace.

## Decision rule

Do **not** replay the original card solely because it is re-queued. First preserve it as timeout evidence and independently calibrate the live tree.

## Minimal recovery sequence

1. Read the latest run: distinguish iteration-budget timeout from a test failure.
2. Freeze the old card with a concise timeout reason; add a comment after calibration with real commands/results.
3. Build the allowlist from the approved Design. Audit both tracked diffs **and untracked files**; `git diff --name-only` alone misses new files.
4. Run the narrow approved test set and syntax/diff checks. Candidate files are not evidence of correctness until this runs.
5. If the candidate is in-scope and tests pass, create a short **T3R reconciliation/handoff** card:
   - parent = last completed Design task, not the timed-out task;
   - no source edits allowed;
   - repeat the scope/static checks and one narrow test run;
   - complete only as a *candidate handoff* for fresh independent Verify.
6. If calibration fails, create a minimal Fix-N → fresh Verify-N → fresh Review-N chain. Do not reuse the timed-out task or its downstream gates.

## Required report facts

- timeout type and old-card status;
- exact allowlist count, including untracked candidate files;
- staged status;
- real command and pass/fail count;
- production side effects explicitly not executed;
- replacement task id(s).

## Shared-workspace safety

Never reset, stash, restore, or clean shared files during calibration. Other dirty paths are background unless they match the approved allowlist.
