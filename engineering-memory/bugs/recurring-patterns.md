# Recurring Bug Patterns

Promote a pattern here when a similar issue appears more than twice or when one severe issue reveals a systemic risk.

## Entry Format

```md
## PATTERN-0001: Short Pattern Name

Status: active / superseded / deprecated / archived
Scope: local / chain / module / cross_module / architecture
Severity: P0 / P1 / P2 / P3
Related root cause: root-cause reference
Related bugs:
- Bug references

### Pattern
Describe the recurring engineering pattern.

### Detection Hints
Codex should search for:
- Keyword/API/type/function names
- Similar logic shape
- Similar data flow
- Similar state lifecycle

### Required Checks Before Fixing
- Check call chain
- Check all consumers
- Check tests
- Check contracts

### Preferred Fix Strategy
Describe the systemic fix.

### Avoid
Describe fixes that only patch symptoms.
```

## Patterns

## PATTERN-0001: Generic CLI Arguments Reused Across Incompatible Tools

Status: active
Scope: module
Severity: P1
Related root cause: RC-0010
Related bugs:
- BUG-0010

### Pattern
Five social CLI adapters received the same `--limit` convention even though their installed command contracts differed or exposed no limit flag.

### Detection Hints
Codex should search for:
- CLI fan-out branches that construct similar argument arrays
- Repeated option names such as `--limit`, `-n`, or `--json`
- Adapter calls whose tests mock responses without asserting command arguments

### Required Checks Before Fixing
- Read each CLI's local help or owning adapter documentation.
- Check every sibling branch in the same fan-out.
- Assert exact command arguments and structured failures in tests.
- Re-run at least one non-destructive real source probe.

### Preferred Fix Strategy
Keep source-specific argument construction explicit and cover all sibling adapters in one table-driven regression test.

### Avoid
Do not infer CLI compatibility from similarly named operations or declare readiness from registration alone.

## PATTERN-0002: Fan-Out Completion Reported As Business Success

Status: active
Scope: cross_module
Severity: P0
Related root cause: RC-0010
Related bugs:
- BUG-0010
- BUG-0012
- BUG-0013

### Pattern
An aggregate tool invokes every source or analysis step and then returns success because orchestration completed, even though nested envelopes show failures or no useful business output.

### Detection Hints
Codex should search for:
- Unconditional `_ok` calls after multiple child responses
- Aggregates that never inspect nested `success`, error codes, or useful item counts
- Downstream consumers that rely only on the top-level `success` field
- Child calls that can raise outside a source- or step-scoped error envelope

### Required Checks Before Fixing
- Reproduce complete, partial, all-failed, and empty outcomes where they apply.
- Check the directly consuming scheduler, workflow, or analysis layer.
- Preserve nested envelopes and existing useful partial results.
- Add an unexpected child-exception regression.

### Preferred Fix Strategy
Derive top-level status from useful output and nested failures, keep partial results successful when they remain useful, return a structured failure when no useful child succeeds, and contain exceptions at each child boundary.

### Avoid
Do not infer business success from loop completion or discard nested errors while flattening aggregate output.
