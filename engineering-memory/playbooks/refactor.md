# Refactor Playbook

Use this playbook when changing structure without changing product behavior.

## Before Refactor
- Read architecture decisions.
- Read module map.
- Identify public contracts.
- Identify regression tests.

## Refactor Rules
- Preserve behavior.
- Avoid mixing feature changes with refactor changes.
- Prefer incremental refactors.
- Add tests before risky changes.

## After Refactor
Update:
- `architecture/module-map.md`
- `tests/regression-map.md`
- `tech-debt/debt-register.md`
- `rules/active-rules.md` if a new stable rule emerged
