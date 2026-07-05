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

No recurring patterns have been recorded yet.
