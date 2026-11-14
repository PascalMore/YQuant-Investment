# Replacement Verification Chain

## Select the smallest repair path

1. Read the failed Verify, its latest run, pending descendants and exact candidate artifacts before routing work. Preserve the failed run and its reports, handoff and reproduction cases; never overwrite FAIL with PASS.
2. State the smallest remaining delta with failing inputs, expected results and exact code/test paths. If these paths exceed the latest stage allowlist, obtain the necessary scope decision first. A user-approved path-only addition for an existing behavior is not automatically a new architecture phase: update only the affected Design scope, preserve prior stage ownership, and propagate the new document identity. Escalate to contract reconciliation only if public semantics or cross-layer authority changes.
3. Choose the gate carrier before creating tasks. Reuse the original blocked Verify as R2 only when it never passed, R1 evidence stays separate, acceptance semantics remain applicable and recurrence limits permit. Otherwise create a replacement Verify and preserve the old card. Fresh evidence does not require a fresh card ID.
4. Complete the bounded Fix, then run fresh independent verification of the unchanged original reproduction cases plus the original affected acceptance matrix. Passing developer regressions alone cannot close independently demonstrated failures.
5. Add Review only when the original flow requires it. Reuse a never-run pending Review when its scope remains applicable; change its body to identify the current verification round, report and candidate.

```text
Option A — same-card R2:
completed implementation → bounded Fix → original Verify (R2) → existing pending Review
                                         R1 evidence retained

Option B — replacement gate:
historical failed Verify remains blocked
bounded Fix → fresh Verify card → required Review → Closeout
```

## Same-card R2 handoff recipe

1. Freeze the failed report and reproduction cases under the original evidence path; reserve distinct `-r2` report, evidence and handoff paths.
2. Create one scoped Fix with the last completed implementation as parent, not the blocked Verify; the latter would deadlock the repair.
3. Add `hermes kanban link <fix-id> <verify-id>` while Verify is blocked, then replace its body with the R2 scope. Keep prior valid parent edges.
4. Update the pending Review's body to read R2 output and to treat R1 FAIL and prior document hashes as historical evidence. Do not leave the default report pointer aimed only at R1.
5. After Fix completion, inspect its actual delta and handoff before unblocking Verify. Read back exact parents, status and mirrored body after writes; do not equate an edit acknowledgement with a correctly gated graph.
6. Report the actual stage to the user: Fix running, independent verification waiting, production untouched. Reserve completion claims for the corresponding executed gate.

## Reuse a pending Review without a dispatch race

1. Confirm the old Review is still `todo`, has no run, and its scope remains applicable.
2. Add the fresh Verify as a parent before removing the failed Verify parent.
3. Replace stale body references with the current candidate, actual Fix and fresh Verify. Do not remove unrelated valid dependencies for cosmetic graph cleanup.
4. Read back the exact parents and body. The Review must stay gated until the fresh Verify passes.
5. If the Review already ran or its acceptance scope changed, preserve its evidence and use a new Review instead.

An operator-completed activation is not a reason to replay service mutations. Preserve its approved-call evidence and narrow remaining workers to independent read-back before resuming them.

## Failed Review after a valid Verify: replace the gate, not the production plan

1. Keep previously proved findings CLOSED and retain the Verify PASS for its exact candidate and tested scope. Record newly reproduced defects in one closed/open ledger; revoke overall release, not historical facts. A passing suite and a new independent counterexample can both be valid because the suite may omit that lifecycle boundary.
2. After the user approves the complete remaining delta, freeze the bounded candidate's source and test bytes plus a path/hash manifest before editing. Hashes alone cannot reconstruct an uncommitted test baseline for later diff or reverse controls. Keep copies outside collected test roots and never roll back the shared tree to perform a comparison.
3. Create the necessary bounded Fix from the last completed implementation, then fresh Verify and Review gates. Do not make the blocked failed Review a hard parent of its own repair; that would prevent dispatch. Pre-create dependent gates with returned real IDs so completion can advance the chain without another user prompt.
4. Reuse a never-run production or Closeout card when its authorized action and scope are unchanged. Run `hermes kanban link <fresh-review> <pending-card>`, read back that both dependencies are present, then `hermes kanban unlink <failed-review> <pending-card>` and read back the final edge set. Replace its body mirror's stale report/candidate pointers without broadening the production action.
5. Preserve any explicit operator HOLD while changing dependencies. An upstream APPROVE does not supply missing production-window facts or authorize execution automatically. Confirm the card remains blocked, later production edges remain unchanged, and the failed Review retains its evidence and no-rerun note.

## Reuse full Verify evidence without weakening independent Review

1. Have the independent tester execute the original counterexamples, lifecycle controls and the final affected regression matrix after the last relevant edit. Record exact selectors, native exits, log hashes and source/test/contract identities.
2. Before reusing that run, compare the current candidate and relevant execution prerequisites with the recorded identities. Read the raw logs, not only the handoff summary; keep overlapping batches and expected-failure controls separate.
3. Let the reviewer independently execute the original failures plus small controls chosen from uncovered boundaries. Reuse the tester's full matrix only while it still applies, and label execution ownership explicitly. A collection/import error is not a behavioral RED; preserve it, correct only the invocation or fixture preparation, then obtain a real assertion result.
4. If same-basename evidence modules collide during pytest collection, run the relevant evidence selection with `--import-mode=importlib` and a new log/basetemp. Do not edit old reproduction files, remove caches or change production behavior to fix test-module identity.
5. A new counterexample revokes overall release, not already proved facts. Consolidate the remaining closed/open ledger and repair only the approved delta; do not reimplement closed findings or repeat a full suite without a relevant change.

## Stateful data-pipeline boundary checklist

Use this checklist when the repair concerns ingestion, mutable official facts or research availability; do not turn it into a new platform or a mandatory stage for unrelated tasks.

1. **Exercise normal lifecycle transitions before widening probes.** Test initial ingestion → first due selection without manually editing the database → partial nonterminal field fill → final settlement → reconstructed components → replay of the original enumeration → read-only verification. Require incomplete states to remain incomplete. Checking only the initial and terminal states misses legal intermediate records.
2. **Bind each state to the evidence actually available then.** Verify enumeration identity separately from later detail/settlement facts. Require final evidence for final facts, but do not require nonexistent final evidence for a legal pending fill. Reject missing/corrupt referenced raw, identity mismatch and contradictory accepted terminal facts; never repair replay by blindly skipping a different hash.
3. **Test exact normalization through persistence, not only a formatter.** Use distinct low-order values representable by Decimal128, equal trailing-zero forms, negative zero and several Decimal context precisions. Run the real loader and reader digest path: distinct accepted facts must conflict or change the digest, not collapse into idempotent success. Avoid context-rounding normalization and float tolerances.
4. **Verify invariants at the public write entry.** On a fresh fake database, run explicit apply through real orchestration, read back required natural-key indexes, reject duplicate natural keys, repeat apply and reject incompatible index definitions without dropping them. Separately prove import/plan/verify do no DDL; a helper definition or direct helper test does not prove the public path invokes it.
5. **Use mixed scheduling states across repeated bounded calls.** Combine future-due pending, due pending, permanently unavailable dates and unseen dates under both small and normal day budgets. Assert actual progress for unseen dates while the contiguous watermark stays behind gaps; testing one planned batch misses permanent starvation.
6. **Cross batch boundaries deliberately.** Put reversed, repeated or out-of-day rows on opposite sides of a chunk boundary in an archive with valid checksum/CRC. Check the expected member name and full-file ordering/day membership before invalid rows reach writes; valid per-chunk rows do not imply a valid day.
7. **Trace producer-to-reader type failures before changing strict consumers.** When real ingestion writes a derived statistic that later breaks a precise manifest, inspect the stored type and frozen field contract. Fix an allowed producer's representation when appropriate and assert exact database read-back; do not broadly allow floats in financial canonicalization or bypass the reader to make the integration test green.

## Engineering approval to an already-authorized production action

1. Close out the engineering milestone against the approved candidate, then reuse the existing production card and its unchanged authorization. Do not invent a new activation chain or request the same migration scope again.
2. Within the existing authorized scope, perform any permitted read-only plan and effective-resource/action check using the reviewed entry and original connection. Report current source/target counts and sanitized missing actions; do not print credentials or infer privileges from a role name.
3. Distinguish read-only production access from no production activity. After a live read-only plan, report that database reads occurred while DDL/DML, migration, backfill and scheduling have not; an undifferentiated `production NOT_RUN` would hide actual access.
4. If the frozen action requires an operator window fact, ask only for that missing fact. Record the known writer inventory and the limited process/timer observation without claiming all writers are absent. Never manufacture the operator's no-concurrent-submission confirmation or infer it from an engineering APPROVE.
5. Keep the existing production HOLD until the required fact arrives, then execute the reviewed plan/apply/exact-readback sequence in that same card. Read-only preparation and an empty target do not authorize writes; no additional token, signature or global-writer proof is implied.

## Prove a one-line candidate delta

- Record the complete old candidate hash and exact allowed line replacement.
- Verify the installed file contains the expected new condition once. In a read-only in-memory copy, replace it with the old line and require the resulting SHA256 to equal the old candidate hash.
- Independently test the new condition against the regression input. If using a logical model, bind it to the installed guard; a hard-coded old model remains a RED control, not evidence of fixed behavior.
- Report byte identity, structural checks, model behavior, native parsing and production execution as different evidence levels.

## Regression fixture example: isolate same-code rows

When a correction can affect other records sharing a target code, use one mixed DataFrame:

| row | input | required final status | routing requirement |
|---|---|---|---|
| 0 | source code + known OCR name | `auto_corrected` | accepted after exact correction |
| 1 | already-correct target code + correct name | `matched` | accepted without correction |
| 2 | same target code + incompatible name | `pending_review` | excluded by `split_review_rows()` |

Assert the complete vector, not only the intended corrected row:

```python
["auto_corrected", "matched", "pending_review"]
```

This catches target-code-wide writeback that contaminates unrelated rows.

## Closeout wording

Separate:

1. **Delivered**: the exact code/rule/configuration delta now exists.
2. **Evidence**: actual developer, fresh Verify and required Review results for that candidate.
3. **Production status**: which real OCR, database, service or rollout actions were executed, with read-back; what remains untested.

Aggregate positive assertions, links and expected-failure controls separately. Do not call a failed RED assertion a positive PASS or double-count reruns as new coverage. Offline gates do not imply production activation or a cold-boot test.
