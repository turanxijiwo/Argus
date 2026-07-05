# Codex Project Operating Rules

## Core Principle
Codex should act as a project engineer, not a patch generator.

For normal feature work, keep context lightweight. Read only this file and the directly relevant source files unless the task touches shared architecture, tests, state, data models, APIs, or bug repair.

## Argus Project Snapshot
Argus is a Python 3.12+ news aggregation and analysis toolkit with a FastMCP server, Starlette web dashboard, SQLite-backed local storage, optional S3-compatible remote storage, launchd scheduling, and notification integrations.

Primary commands:
- Test: `uv run python -m unittest discover -s tests`
- Build: `uv build`
- Lint/typecheck: no dedicated project command is configured yet; use targeted syntax checks plus tests until one is added.

## Project Inventories
Keep these inventories current when the matching surface changes. Do not duplicate full tool lists here; link or summarize the owning file.

API and MCP surface:
- `argus_server/server.py` registers 162 FastMCP tools and 8 MCP resources.
- `argus/web/app.py` exposes dashboard routes: `/`, `/api/health`, `/api/latest`, `/api/trending`, `/api/anomalies`, `/api/dates`, `/api/stream`.
- `argus_server/feishu_bot.py` exposes `/`, `/health`, and `POST /feishu/event`.

Pages and UI:
- `argus/web/app.py` owns the single HTML Starlette dashboard.
- `docs/index.html` with `docs/assets/` owns the static documentation site.

Data models:
- `argus/storage/schema.sql` owns hotlist news tables and crawl/rank history.
- `argus/storage/rss_schema.sql` owns RSS feed, item, crawl, and push records.
- `argus/storage/ai_filter_schema.sql` owns AI filter tags, results, and analyzed-news records.

Environment variables:
- Config/runtime: `CONFIG_PATH`, `GITHUB_ACTIONS`, `DOCKER_CONTAINER`, `STORAGE_RETENTION_DAYS`.
- AI/search: `AI_API_KEY`, `AI_MODEL`, `AI_API_BASE`, `AI_TEMPERATURE`, `AI_MAX_TOKENS`, `AI_TIMEOUT`, `TAVILY_API_KEY`, `EXA_API_KEY`, `PERPLEXITY_API_KEY`, `BRAVE_API_KEY`, `ARGUS_CODEX_MODEL`.
- Storage: `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`.
- Notifications and bot: `FEISHU_WEBHOOK_URL`, `FEISHU_SECRET`, `DINGTALK_WEBHOOK_URL`, `BARK_URL`, `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_VERIFICATION_TOKEN`, `FEISHU_ENCRYPT_KEY`, `FEISHU_BOT_HOST`, `FEISHU_BOT_PORT`.
- External CLI: `DISCORD_TOKEN`, `ARGUS_VAULT`, and `PATH` entries for optional CLI tools.

## Context Budget Policy
Do not load the entire engineering memory by default.

Default context:
- `AGENTS.md`
- `context.md`
- Directly relevant source files
- Directly relevant tests

Triggered context only when needed:
- `.codex-memory.yaml`
- A small number of relevant memory files listed by that index

Never read the full `engineering-memory/` directory unless explicitly requested.

## Triggered Memory Read
Read `.codex-memory.yaml` and the relevant memory files only when the task involves:
- Bug fixes
- Test failures
- Repeated errors
- Shared utilities
- State management
- API contracts
- Data schemas
- Authentication / permissions
- Storage / cache / database logic
- Workflow orchestration
- Architecture changes
- Refactoring
- Performance regressions

## Systemic Bug Fix Protocol
Do not immediately patch a bug.

Before editing code, produce a short diagnosis:
1. Symptom
2. Reproduction path or observed trigger
3. Root cause hypothesis
4. Affected call chain
5. Related modules and files
6. Similar patterns in the codebase
7. Risk of regression
8. Proposed fix scope

Classify the impact scope:
- P0: Current failing behavior must be fixed now.
- P1: Same call chain / same module / same data structure must be checked now.
- P2: Similar project-wide patterns should be scanned and recorded, not broadly rewritten unless necessary.
- P3: Architecture debt should be recorded as follow-up work, not mixed into the current fix unless blocking.

After diagnosis, apply the smallest systemic fix that removes the root cause without causing unrelated rewrites.

## Stop Conditions
Do not enter an endless investigation loop.

Stop investigation and implement when:
- The root cause is supported by code, logs, failing tests, or a reproducible path.
- The affected call chain is identified.
- Related same-module risks have been checked.
- A safe fix scope is defined.

Stop expanding scope when:
- The issue is only similar by name but not by data flow or contract.
- The fix would require unrelated refactoring.
- The issue belongs in `engineering-memory/tech-debt/debt-register.md`.
- The investigation would touch more than the current module plus directly connected callers/consumers without evidence.

## Bug Fix Exit Criteria
A bug fix is not complete until Codex reports:
1. What was fixed
2. Why this addresses the root cause
3. What related paths were checked
4. What tests were added or updated
5. What tests were run
6. What risks remain
7. Whether a follow-up tech-debt or architecture task was created

## Memory Update Policy
After any bug fix, test failure resolution, architecture change, or repeated issue:
- Append to `engineering-memory/bugs/bug-ledger.md`
- Update `engineering-memory/bugs/root-causes.md` if a new root cause appears
- Update `engineering-memory/bugs/recurring-patterns.md` if the same pattern appears more than twice
- Update `engineering-memory/tests/regression-map.md` if a regression test is added or changed
- Update `engineering-memory/tech-debt/debt-register.md` if unresolved systemic debt remains
- Update `context.md` with the latest project status when product code, tests, architecture, or active risks changed

If a lesson becomes stable and broadly useful, promote it into:
- `engineering-memory/rules/active-rules.md`

If a rule becomes outdated, move it to:
- `engineering-memory/rules/deprecated-rules.md`

## Context.md Policy
`context.md` is the short project handoff file. Keep it concise and current. It should summarize current goals, active work, recent meaningful changes, architecture snapshot, and known risk areas. Do not store secrets, private machine paths, customer data, or long bug history in `context.md`.

## Memory Hygiene
Keep memory concise and useful.

- Do not duplicate long bug details across multiple files.
- Convert repeated bug logs into root causes, patterns, and rules.
- Keep `active-rules.md` short and high value.
- Archive or deprecate outdated rules.
- Run the memory compaction procedure when memory becomes noisy.

## Guardrails
- Do not expand a bug fix into a broad refactor unless the root cause cannot be fixed safely otherwise.
- Do not rewrite unrelated modules.
- Do not hide unresolved risks.
- Do not delete historical memory unless replacing it with a clearer superseding rule.
- Prefer adding regression tests over relying only on manual reasoning.
- Do not store secrets, API keys, credentials, customer data, or private machine paths in engineering memory.

## Final Response Format for Bug Fixes
When completing a bug fix, summarize:

```md
## Diagnosis

## Root Cause

## Fix Applied

## Related Impact Checked

## Tests Run

## Memory Updated

## Remaining Risks / Follow-ups
```
