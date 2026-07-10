# Technical Debt Register

Record systemic issues that should not be mixed into unrelated bug fixes.

## Entry Format

```md
## DEBT-0001: Short Debt Title

Date: 2026-01-01
Status: open / in_progress / resolved / archived
Severity: low / medium / high / critical
Area:
Related bugs:
- Bug references
Related patterns:
- Pattern references

### Problem
Describe the debt.

### Why Not Fixed Now
Explain why this was not included in the current task.

### Risk
What may happen if this remains unresolved?

### Proposed Resolution
Describe a safe future task.

### Exit Criteria
How do we know this debt is resolved?
```

## Technical Debt

## DEBT-0001: Optional Runtime Health Is Package-Level

Date: 2026-07-10
Status: open
Severity: low
Area: Research Toolkit optional adapters
Related bugs:
- None
Related patterns:
- Optional runtime readiness

### Problem
`research_toolkit_health` reports the Codex source as ready when the
`openai-codex` package is importable, but a real SDK run can still fail while
loading incompatible user-level Codex configuration. The 2026-07-10 delivery
audit observed `model_reasoning_effort = "ultra"` being rejected by the
installed SDK parser, which accepts values through `xhigh`.

### Why Not Fixed Now
The incompatible value is in user-level Codex configuration outside Argus.
Argus must not silently rewrite global settings, and running a Codex thread as
part of every health check would be slow and stateful.

### Risk
Agents may interpret package availability as end-to-end Codex source readiness.

### Proposed Resolution
Distinguish `installed` from `runtime_verified` in optional adapter health, and
add an explicit opt-in runtime probe that returns configuration and permission
errors without changing user state.

### Exit Criteria
- Health output distinguishes package detection from a successful runtime probe.
- The probe has deterministic tests for configuration and permission failures.
- No global Codex configuration is modified by Argus.
