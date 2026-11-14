# Shared-dir baseline loss and stale-worker containment

## Trigger
Use when a shared `dir` Kanban tree loses previously verified, **uncommitted** RFC/SPEC/Design edits (for example, files revert to HEAD versions) while an old Implement is still queued or running.

## Evidence-first procedure
1. Compare current document versions/required section anchors against the last independent Verify handoff. Treat the **current files** as source of truth; a prior PASS is historical evidence only.
2. Check `git status --short`, path-filtered diffs, mtimes, and exact worker PID command lines. Never infer the actor or use `git restore` yourself to "fix" it.
3. Immediately block every old Implement using the vanished contract. A blocked task can still be auto-promoted after parents complete, so re-check task status and process liveness.
4. If a matching worker continues writing after blocking, terminate only the verified exact task PIDs (TERM, then KILL if needed); record task id/PID/evidence in the Kanban comment. Do not kill broad profile processes.
5. Preserve remaining dirty files; no reset/stash/clean. They are unverified candidates, not a replacement baseline.
6. Rebuild the baseline serially as separate RFC → SPEC → Design cards. Do not reconstruct missing Design from a worker summary or let code proceed against stale in-memory handoff text.
7. After the reconstructed Design independently passes, run a Principal scope-reconciliation if partial code introduced an allowlist ambiguity; then create a **replacement** Implement, Verify, Review chain. Never revive the old Implement.

## Completion standard
The recovery is not complete until current on-disk RFC/SPEC/Design versions and anchors are independently verified together. Only then may code execution resume; no production Gate authorization carries over from the lost baseline.

## Notes
- A clean `git diff --check` does not reveal deleted uncommitted documents or untracked files.
- `kanban_block` changes board status but may not stop already spawned workers; process verification is required.
