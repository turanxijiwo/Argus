# Module Map

Use this file to map important modules, ownership boundaries, dependencies, and risk level.

## Entry Format

```md
### Module: Short module name

Path:
- `src/...`

Responsibility:
- Describe what this module owns.

Depends on:
- Module/API/service names

Used by:
- Module/API/service names

Risk level:
- low / medium / high / critical

Common failure modes:
- State drift
- Contract mismatch
- Cache invalidation
- Async lifecycle error
- Schema mismatch

Required tests:
- Unit:
- Integration:
- Regression:
```

## Modules

### Module: CLI application and core orchestration

Path:
- `argus/__main__.py`
- `argus/context.py`
- `argus/core/`

Responsibility:
- Load configuration, run crawl/analyze/report/notification modes, coordinate core TrendRadar-derived workflows, and expose the `argus` console script.

Depends on:
- `argus.crawler`, `argus.storage`, `argus.ai`, `argus.notification`, `config/`

Used by:
- Local CLI runs, scheduled jobs, MCP tools that trigger native Argus behavior.

Risk level:
- high

Common failure modes:
- Config/env mismatch
- Storage contract drift
- Notification batching errors
- Time window and once-per-day logic regressions

Required tests:
- Unit: config parsing, schedule/window helpers, analyzer helpers
- Integration: crawl/analyze/push with fixture config and storage
- Regression: notification pairing, retention, once-per-day behavior

### Module: FastMCP server surface

Path:
- `argus_server/server.py`
- `argus_server/tools/`
- `argus_server/services/`
- `argus_server/utils/`

Responsibility:
- Register 165 MCP tools and 8 MCP resources, create shared tool adapters, normalize tool responses, and provide the `argus-mcp` console script.

Depends on:
- `fastmcp`, Argus core/storage modules, all `argus_server.tools` adapters

Used by:
- Claude Code, Cherry Studio, and other MCP clients.

Risk level:
- critical

Common failure modes:
- Tool name or signature changes breaking clients
- Response contract mismatch
- Singleton tool initialization drift
- Optional dependency or environment failure surfacing as opaque MCP errors
- CLI auth/cookie failures leaking raw tracebacks instead of actionable error codes

Required tests:
- Unit: individual tool adapter behavior
- Integration: server import/registration and selected MCP tool smoke tests
- Regression: response shape and error-code stability for public tools

### Module: Storage and data model

Path:
- `argus/storage/`
- `argus_server/services/parser_service.py`
- `argus/storage/schema.sql`
- `argus/storage/rss_schema.sql`
- `argus/storage/ai_filter_schema.sql`

Responsibility:
- Persist and read hotlist, RSS, crawl history, rank history, push records, AI filter records, and optional S3-compatible remote copies.

Depends on:
- SQLite, optional boto3, config/env storage settings

Used by:
- CLI core, MCP data/query/search/analytics tools, web dashboard, exporter, scheduler workflows.

Risk level:
- critical

Common failure modes:
- Schema mismatch
- Deduplication uniqueness drift
- Local/remote backend divergence
- Date/time retention bugs
- Parser assumptions not matching stored rows

Required tests:
- Unit: schema-backed save/read/update behavior
- Integration: local and remote-backend adapter smoke tests with temporary data
- Regression: URL/platform dedupe, RSS push records, AI filter versioning

### Module: Crawling, RSS, and source ingestion

Path:
- `argus/crawler/`
- `argus/crawler/rss/`
- `config/config.example.yaml`
- `config/timeline.yaml`
- `config/frequency_words.txt`

Responsibility:
- Fetch hotlist and RSS/Atom sources, parse source data, and feed normalized data into storage.

Depends on:
- `requests`, `feedparser`, source configs, optional local RSSHub services.

Used by:
- CLI core, trigger-crawl MCP tools, scheduler workflows, dashboard data.

Risk level:
- high

Common failure modes:
- Source format drift
- Network timeout or blocked source
- RSSHub route/cookie failures
- Platform ID/name mismatches

Required tests:
- Unit: parser behavior with fixture payloads
- Integration: source fetch smoke tests where network is explicitly allowed
- Regression: malformed feed handling and platform mapping

### Module: AI, semantic search, alerts, and analysis

Path:
- `argus/ai/`
- `argus_server/tools/ai_enhanced.py`
- `argus_server/tools/ai_analytics.py`
- `argus_server/tools/semantic_search.py`
- `argus_server/tools/alerts.py`
- `argus_server/tools/cross_platform.py`

Responsibility:
- Summarize, translate, deduplicate, detect anomalies, search indexed content, run alert rules, and compare cross-platform narratives.

Depends on:
- LiteLLM and optional AI/search environment variables, jieba, rank-bm25, numpy, storage/query tools.

Used by:
- MCP clients, reports, daily briefs, alerts, dashboard anomaly endpoint.

Risk level:
- high

Common failure modes:
- Missing AI/search keys
- Non-deterministic LLM output
- Index staleness
- Token/cost/timeouts
- Fallback scoring diverging from LLM scoring

Required tests:
- Unit: deterministic normalization, BM25/index behavior, alert rule evaluation
- Integration: AI-disabled and AI-enabled smoke tests
- Regression: anomaly detection edge cases and missing-key error responses

### Module: Research toolkit and external adapters

Path:
- `argus_server/tools/research_toolkit.py`
- `argus_server/tools/research_runtime.py`
- `argus_server/tools/research_handoff.py`
- `argus_server/tools/research_page.py`
- `argus_server/tools/research_health.py`
- `argus_server/tools/research_crawl.py`
- `argus_server/tools/research_sources.py`
- `argus_server/tools/research_source_ai.py`
- `argus_server/tools/research_topic.py`
- `argus_server/tools/research_images.py`
- `argus_server/tools/research_pack.py`
- `argus_server/tools/research_workflow.py`
- `argus_server/tools/research_batch.py`
- `argus_server/tools/research_gallery.py`
- `argus_server/tools/research_render.py`
- `argus_server/tools/research_web.py`
- `argus_server/tools/research_brief.py`
- `argus_server/tools/research_io.py`
- `argus_server/tools/research_review.py`
- `argus_server/tools/external_apis.py`
- `argus_server/tools/cli_tools.py`
- `argus_server/tools/social_ops.py`
- `docs/RESEARCH_TOOLKIT_BOUNDARIES.md`

Responsibility:
- Provide dependency-free page crawling/image discovery entrypoints, runtime defaults/session setup, compact handoff summaries, HTTP crawl orchestration, cross-source topic aggregation, topic-driven image research, full research workflow orchestration, batch saved-workflow orchestration, saved-artifact quality review, capability health matrix reporting, optional Crawl4AI render runtime, source adapter normalization, optional AI-backed web/Codex source adapters, evidence packet construction, workflow document/image scoring helpers, safe gallery-dl wrapping, HTML/URL parsing, research brief rendering, safe project-local research artifact writing, public external API lookup, and optional social CLI wrappers.

Depends on:
- `requests`, optional local CLIs (`gallery-dl`, bili/xhs/twitter/tg/discord), optional local Codex SDK (`openai-codex`), external API availability.

Used by:
- MCP clients and research workflows.

Risk level:
- high

Common failure modes:
- Unsafe output paths
- URL validation gaps
- Optional CLI missing/auth failures
- Optional Codex SDK missing, unavailable, or returning non-JSON output
- External API format drift
- Network timeouts
- Partial packet failures must remain visible without failing successful documents

Required tests:
- Unit: `tests/test_research_toolkit.py`
- Integration: optional CLI dry-run smoke tests when installed
- Regression: invalid URL rejection, output path safety, normalized merged-source shape
- Regression: optional source readiness, missing-SDK errors, and normalized merged-source shape

### Module: Scheduling, notifications, routing, and Feishu bot

Path:
- `argus_server/tools/scheduler.py`
- `argus_server/scheduler_runner.py`
- `argus_server/tools/notification.py`
- `argus_server/tools/router.py`
- `argus_server/tools/daily_brief.py`
- `argus_server/feishu_bot.py`
- `argus/notification/`

Responsibility:
- Create launchd workflow schedules, execute scheduled MCP-like steps, dispatch notifications, route messages, render daily briefs, and handle Feishu reverse-channel events.

Depends on:
- macOS launchd, webhook/env configuration, notification senders, MCP tool adapters.

Used by:
- Automation workflows, daily brief pushes, Feishu group command loop.

Risk level:
- critical

Common failure modes:
- launchd plist key mistakes
- Unsafe or stale workflow files
- Webhook credential/config mismatch
- Duplicate or missed scheduled pushes
- Bot event verification/decryption failure

Required tests:
- Unit: schedule parsing, plist generation, route matching, notification batching
- Integration: dry-run launchd/workflow runner and webhook mock tests
- Regression: Weekday/Hour/Minute plist casing and once-per-day behavior

### Module: Web dashboard and static documentation

Path:
- `argus/web/`
- `docs/index.html`
- `docs/assets/`

Responsibility:
- Serve local Starlette REST/SSE dashboard and static documentation assets.

Depends on:
- Starlette, local storage, AI analytics for anomaly endpoint.

Used by:
- Local browser users and quick operational checks.

Risk level:
- medium

Common failure modes:
- No-data states
- SSE lifecycle errors
- Dashboard assumptions not matching storage rows
- Static docs drifting from source

Required tests:
- Unit: route helper behavior with fixture data
- Integration: Starlette TestClient route checks
- Regression: no-data responses and SSE payload shape
