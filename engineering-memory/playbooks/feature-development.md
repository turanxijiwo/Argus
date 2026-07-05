# Feature Development Playbook

Use this playbook for normal feature work.

## Principles
- Keep context lightweight.
- Do not read full memory unless the feature touches high-risk areas.
- Prefer small, testable changes.

## Before Editing
Check:
- Existing similar feature
- Module ownership
- Related tests
- API/data contracts

## During Editing
- Avoid changing unrelated behavior.
- Preserve existing architecture decisions.
- Update tests for new behavior.

## After Editing
Report:
- Files changed
- Behavior added
- Tests run
- Risks
- Whether memory update is needed
