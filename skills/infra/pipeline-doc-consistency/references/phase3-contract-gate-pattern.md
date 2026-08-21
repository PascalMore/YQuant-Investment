# Phase 3 Contract-Gate Pattern (2026-07-22)

## Trigger

Apply when Full Flow Review finds a mismatch between an implemented public contract and the canonical RFC/SPEC/Design, particularly around return objects, status/error semantics, or persistence boundaries.

## Durable procedure

1. Freeze the Review as `REVISE`; record precise `file:line` and canonical-section evidence.
2. Do not re-promote or rerun the same Review merely to obtain a different verdict when no code, test, or canonical-document artifact changed.
3. Route the disagreement to a Principal Contract Gate. It must choose one direction:
   - implementation is wrong: repair implementation/tests to the canonical document; or
   - implementation is accepted: amend the canonical Design, plus RFC/SPEC whenever they define the old shape normatively.
4. Principal handoff must name the chosen canonical shape, amended sections, compatibility impact, and downstream assertions.
5. Create a new bounded Implement → independent Verify → independent Review chain. Pre-adjudication Review results are historical evidence only and cannot close the new gate.
6. Do not close out while any blocker/major/minor remains unresolved or merely “downgraded” by a reviewer without a principal-backed canonical decision.

## Status reporting

Always distinguish:

- offline implementation/test acceptance;
- pipeline contract closeout; and
- production readiness/activation.

A green offline suite does not mean production-complete. Explicitly state whether real providers, MongoDB DDL/DML/indexes, credentials, cron/canary, and external writes were intentionally excluded.

## Anti-patterns

- A later reviewer changes `REVISE` to `PASS` without an intervening artifact or principal adjudication.
- `git diff --check` or regression green is treated as proof that a public contract conflict is resolved.
- Public docstrings or test-module explanations are not corrected after a return type or refresh contract changes.
