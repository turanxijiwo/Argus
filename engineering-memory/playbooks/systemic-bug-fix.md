# Systemic Bug Fix Playbook

Use this playbook when fixing bugs, test failures, regressions, or repeated errors.

## Objective
Fix the root cause without creating unrelated rewrites or endless investigation.

## Step 1: Reproduce or Localize
- Identify the failing command, route, test, user action, or log entry.
- If reproduction is impossible, state the strongest observable evidence.

## Step 2: Classify
Classify the issue:
- Local implementation bug
- Interface contract bug
- State flow bug
- Data model/schema bug
- Async lifecycle bug
- Cache/storage bug
- Config/environment bug
- Test coverage gap
- Architecture boundary issue

## Step 3: Trace Impact
Trace only the evidence-backed scope:
- Entry point
- Call chain
- Data flow
- State flow
- Error handling path
- External dependency, if any

## Step 4: Search Similar Patterns
Search the smallest useful scope first:
- Same function/class
- Same module
- Same call chain
- Same data model/API
- Same recurring pattern memory

Avoid broad project rewrites unless evidence shows the issue is systemic.

## Step 5: Choose Fix Scope
- P0: Fix the current failure.
- P1: Fix same-chain and same-module related issues.
- P2: Record similar project-wide patterns unless they are clearly unsafe.
- P3: Create tech-debt entry for future refactor.

## Step 6: Stop Conditions
Stop investigating and implement when:
- Root cause is supported by evidence.
- Affected call chain is identified.
- Same-module and same-chain risks were checked.
- Fix scope is clear and testable.

Stop expanding scope when:
- The next issue is only loosely similar.
- The next fix requires unrelated refactor.
- The issue belongs in tech debt.
- The search is no longer changing the diagnosis.

## Step 7: Implement
Prefer root-cause fixes over symptom patches.
Avoid unrelated cleanup.
Do not mix feature work into bug repair.

## Step 8: Verify
Run targeted tests first.
Run broader tests only if shared modules, APIs, schemas, or state management changed.
Add regression tests when missing.

## Step 9: Update Memory
Update the relevant files under `engineering-memory/`.
Do not store secrets, credentials, user data, or private machine-specific paths.
