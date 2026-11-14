# Capability-scoped repair for a shared helper

Use after independent Verify finds that a new capability's strict contract conflicts with a shared helper's legacy output states.

1. Scan the helper definition, every call site, dependent exit-code branch, and test assertion before editing.
2. Classify the change:
   - Global contract migration → Principal amendment + expanded allowlist + all consumer updates.
   - Capability-local contract → preserve the helper's default legacy behavior and add a backward-compatible explicit `capability`/scope parameter (or an approved local adapter).
3. The new capability call site must pass scope explicitly. Test both:
   - the new threshold boundary and prohibited state; and
   - the unchanged default behavior used by sibling capabilities.
4. Do not globally remove a state such as `conditional_pass` merely to satisfy one capability if sector/sentiment/other existing paths still explicitly use it.
5. After Fix, create fresh independent Verify and Review; the original Verify FAIL remains evidence.

Example shape:

```python
def verdict_for_mapping(matched_ratio: float, *, capability: str | None = None) -> str:
    if capability == "new.capability":
        return "pass" if matched_ratio >= 0.70 else "fail"
    # legacy behavior for existing callers
```

This is a compatibility-preserving semantic isolation pattern, not a new provider/client abstraction.