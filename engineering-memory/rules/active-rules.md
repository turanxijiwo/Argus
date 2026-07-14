# Active Engineering Rules

Keep this file short. It should contain only high-value rules that prevent recurring bugs.

## Entry Format

```md
### RULE-0001: Short Rule Name

Status: active
Scope: global / module / workflow / API / tests
Applies when:
- Trigger condition 1
- Trigger condition 2

Rule:
- Describe the rule Codex should follow.

Reason:
- Explain why this prevents bugs.

Related patterns:
- Pattern references

Related bugs:
- Bug references
```

## Active Rules

### RULE-0001: Separate Health Execution From Business Readiness

Status: active
Scope: API
Applies when:
- Adding or changing health, status, readiness, or liveness endpoints
- Aggregating required and optional capability checks

Rule:
- Use `success` only for whether the check executed successfully.
- Use explicit `ready` and `status` fields for business readiness.
- Mark every nested check as required or optional, and derive blocking/degraded summaries from those records.
- Liveness-only endpoints must identify their scope and must not claim business readiness.

Reason:
- A constant healthy value or one ambiguous boolean can hide missing configuration/data or make optional integrations look like core outages.

Related patterns:
- None

Related bugs:
- BUG-0014
