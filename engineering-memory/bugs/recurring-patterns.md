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

## PATTERN-0003: External CLI Authentication Prompt Reached Agent Stdio

Status: active
Scope: module
Severity: P1
Related root cause: RC-0026
Related bugs:
- BUG-0030

### Pattern
An optional external CLI adds a prompt on its unauthenticated path, and a generic subprocess wrapper inherits the agent transport's standard input.

### Detection Hints
Codex should search for:
- `subprocess.run` or `Popen` without `stdin` or explicit `input`
- Login, status, confirmation, phone, OTP, or password prompts
- MCP servers using stdio transport
- Tests that mock only authenticated command output

### Required Checks Before Fixing
- Run the real unconfigured status/auth command without entering credentials.
- Trace the parent transport and every subprocess caller.
- Preserve intentionally modeled input paths.
- Assert both default-closed stdin and explicit-input behavior.

### Preferred Fix Strategy
Close stdin at the shared subprocess boundary and require callers to opt into bounded explicit input.

### Avoid
Do not rely only on timeout handling: a child that reads protocol bytes may corrupt the session before the timeout fires.

## PATTERN-0004: Installed CLI Contract Drifted From Wrapper Or MCP Help

Status: active
Scope: module
Severity: P1
Related root cause: RC-0024
Related bugs:
- BUG-0027
- BUG-0029
- BUG-0031

### Pattern
An external Click CLI changes or never supported an argument, while project wrappers, tests, or agent-visible MCP descriptions keep a guessed or older command form.

### Detection Hints
Codex should search for:
- Every wrapper call to the installed binary
- MCP docstrings and README examples containing CLI flags
- Tests that assert project literals without evidence from installed help
- Shared option assumptions such as `--limit`, `--latest`, or `--following`

### Required Checks Before Fixing
- Pin and install the approved package version.
- Execute help for every documented or wrapped subcommand.
- Compare wrapper argv, MCP descriptions, aggregate adapters, and tests.
- Run at least one safe real read through the full Argus path.

### Preferred Fix Strategy
Keep command-specific argv explicit, preserve public limits through local slicing only when necessary, and update runtime wrappers and exposed help in the same verified change.

### Avoid
Do not treat a successful package import, auth probe, or mocked adapter as proof that documented business commands are callable.

## PATTERN-0005: Public API Rate Limits Collapsed Into Transport Errors

Status: active
Scope: module
Severity: P1
Related root cause: RC-0018
Related bugs:
- BUG-0020
- BUG-0024
- BUG-0032

### Pattern
A public no-key endpoint returns HTTP 429, but the adapter's broad request exception path labels it as a network failure and drops retry/fallback metadata.

### Detection Hints
Codex should search for:
- `raise_for_status()` followed by a broad `RequestException`
- Providers documented or observed to return 429
- Missing `Retry-After`, cache, pacing, or fallback fields
- Audit records where repeated serial probes fail identically

### Required Checks Before Fixing
- Reproduce or mock a normal success and a real provider-shaped 429.
- Check the provider's caching, pacing, and retry guidance.
- Preserve source-specific metadata without exposing request secrets.
- Avoid broad retries when the limit is persistent or unspecified.

### Preferred Fix Strategy
Classify rate limits at the provider boundary, preserve dynamic retry metadata, and add caching, pacing, bounded retry, or a legal fallback only when supported by provider behavior.

### Avoid
Do not relabel every request failure as rate limiting or hammer a persistent 429 with automatic retries.
