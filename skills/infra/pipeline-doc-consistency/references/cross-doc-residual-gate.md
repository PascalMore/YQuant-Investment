# Cross-Doc Residual Gate — Worked Example

Session: 2026-07-17. Subject: Unified Data Phase 2 Rollout → Audit-only minimum-privilege contract (RFC/SPEC/DESIGN-03-011 + `scripts/unified_data/audit_rollout.py`).

This file captures two recurring failure modes that survived multiple remediation rounds and the recovery workflow the orchestrator used to close them. The SKILL.md body now encodes the rules; this file is the concrete transcript / checklist a future agent can copy.

## Failure Mode A — Cross-doc token residual

What happened:

1. The CLI surface for `audit_rollout.py` was simplified to `--apply` / `--verify` only; `database` / `collection` / `writer-role` / `reader-role` were declared module-level fixed constants that must not be CLI-overridable.
2. A docs-only follow-up (`Docs-R3.1`, `t_44de7277`) correctly replaced `--database=wrong` → `--unknown-flag` in RFC §14.1 A7.
3. Independent reviewer was forced to spot that DESIGN §16 A7 and DESIGN §8.9.4 (`--verify` exit-code caption) **still** referenced `--database=wrong` / `--database` as live CLI inputs. RFC and DESIGN were now internally inconsistent; the previous layered remediation could not be reported as PASS.

Tokens that recurred in this lineage:

| Token | Where it kept surviving | Acceptable replacement |
| --- | --- | --- |
| `--database=wrong` | RFC §14.1 A7 → DESIGN §16 A7 + §8.9.4 exit-code caption | `--unknown-flag` (probe argparse rejection → exit 2) |
| `范围校验失败（--database 不在 allow-list）` | DESIGN §8.9.4 | `name-space / collection / privileges 不在范围` (TTL/keys/order precision + role/user prefix `yquant_ud_audit_*`) |
| `--writer-role/--reader-role` | DESIGN §12 G3 governance table | declared as module-level fixed constants only; never as CLI args |

Recovery workflow:

1. Search all three layer files with a single, strict grep — do not rely on per-layer grep chains.
2. Expand the offending `Docs-R3.x` card's allowlist, or create a narrowly scoped follow-up (`Docs-R3.2`) whose body explicitly lists the cross-doc residual `file:line` evidence and whose `parents` link back to the previous `Docs-R3.x` so the chain stays linear.
3. Require an independent reviewer (different worker profile) to sign off the cross-doc residual — never the same worker that produced the layer-patch.
4. Record the `file:line` evidence into a `kanban_comment` on both the previous and current card so downstream Implement / Verify tasks inherit the constraint.

Concrete search snippet used at audit time:

```bash
for p in \
  docs/rfc/03_data/RFC-03-011-unified-data-phase-2-quality-audit-governance.md \
  docs/spec/03_data/SPEC-03-011-unified-data-phase-2-quality-audit-governance.md \
  docs/design/03_data/DESIGN-03-011-unified-data-phase-2-quality-audit-governance.md; do
  grep -nE -- '--database|--collection|--writer-role|--reader-role|\[BLOCKED\]' "$p" || true
done
```

## Failure Mode B — `done`/`timed_out` while shared worktree still has partial diff

What happened:

1. `t_886d4c1d` (Replacement Implement → migrate `audit_rollout.py` to the unique `YQUANT_UD_AUDIT_*` namespace) hit `Iteration budget exhausted (60/60)` after producing a structurally sound but only partially complete diff.
2. The diff already had 65 occurrences of `YQUANT_UD_AUDIT_*` and 0 of `UD_DDL_MONGO_*`, but **still had 19 occurrences of `UD_AUDIT_WRITER_MONGO_*` and 16 of `UD_AUDIT_READER_MONGO_*`**.
3. 39 audit-rollout tests passed against the partial state — non-independent evidence that the contract was satisfied.
4. The orchestrator did NOT accept the partial state as PASS. It instead:
   - ran `py_compile` (PASS), `pytest tests/scripts/test_audit_rollout.py -q` (39 passed) and a per-prefix `grep -c` against the two staged files;
   - recorded the per-prefix counts in `kanban_comment(t_886d4c1d, comment_id=256)`;
   - emitted continuation constraints: DDL already migrated, finish WRITER / READER groups; restore 0 for the three legacy prefixes; re-run py_compile + targeted pytest + unified-data regression + diff-check + CLI dry-run + `--apply` missing-credential fail-fast; do NOT touch real Mongo / `--apply` / secrets / push;
   - let the dispatcher retry on the existing card rather than unblocking or relabeling.

Concrete audit commands used:

```bash
# Sanity: code still compiles and the targeted test file stays green.
python -m py_compile scripts/unified_data/audit_rollout.py
PYTHONPATH=. pytest tests/scripts/test_audit_rollout.py -q --tb=short

# Per-prefix legacy-vs-new residue on the actual staged files (allowlist scope).
for p in 'UD_DDL_MONGO_' 'UD_AUDIT_WRITER_MONGO_' 'UD_AUDIT_READER_MONGO_' 'YQUANT_UD_AUDIT_'; do
  printf '%-35s ' "$p"
  grep -o "$p" scripts/unified_data/audit_rollout.py tests/scripts/test_audit_rollout.py 2>/dev/null | wc -l
done

# And a unified diff to confirm what actually changed vs the previous commit.
git diff --unified=0 -- scripts/unified_data/audit_rollout.py tests/scripts/test_audit_rollout.py
```

Decision rules observed:

- **Retry is OK** when the partial diff is structurally sound and the next run can finish without ripping up what already passed.
- **Replace is required** when the parent task is already REVISE'd (or any block has been placed on its gate) before the impl starts — that path keeps the original card as audit evidence and creates a new card with a real, satisfiable parent.
- **Never** promote a timed-out / partial task to PASS via its own self-reported test count or self-stated CLI run. Independent verification is mandatory.
- **Never** roll a retry's failure into a justification for silently loosening production gating. Production `--apply` / DDL / secrets wait for an explicit Pascal authorization regardless of how many retries happened.

## Audit checklist (copy-paste ready)

```text
[ ] git status --untracked-files=all                    (snapshot taken at audit moment)
[ ] git diff --name-status                              (must equal allowlist only)
[ ] git diff --check                                    (clean)
[ ] per-prefix grep -c on each staged file              (forbidden tokens == 0)
[ ] cross-doc grep across all three layer docs         (no residual in other layers)
[ ] independent pytest run against the staged files
[ ] CLI dry-run + --apply missing-credential fail-fast (no real Mongo)
[ ] kanban_comment on the previous card + this card    (file:line evidence)
[ ] reviewer card parented on this card                (independence preserved)
[ ] production action explicitly NOT claimed as done   (waiting on Pascal authorization)
```
