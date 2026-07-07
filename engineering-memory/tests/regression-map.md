# Regression Test Map

Map bugs and critical flows to tests so Codex knows what to run after related changes.

## Critical Flow Entry Format

```md
### Flow: Short flow name

Related modules:
- `src/...`

Tests to run:
- `tests/...`

Known historical bugs:
- Bug references
```

## Bug Regression Entry Format

```md
### Bug reference or short bug title

Test file:
- `tests/...`

What it protects:
- Describe the regression risk.
```

## Critical Flow Tests

### Flow: Research toolkit crawl and source normalization

Related modules:
- `argus_server/tools/research_toolkit.py`
- `argus_server/tools/research_page.py`
- `argus_server/tools/research_health.py`
- `argus_server/tools/research_crawl.py`
- `argus_server/tools/research_sources.py`
- `argus_server/tools/research_source_ai.py`
- `argus_server/tools/research_topic.py`
- `argus_server/tools/research_images.py`
- `argus_server/tools/research_pack.py`
- `argus_server/tools/research_workflow.py`
- `argus_server/tools/research_gallery.py`
- `argus_server/tools/research_render.py`
- `argus_server/tools/research_web.py`
- `argus_server/tools/research_brief.py`
- `argus_server/tools/research_io.py`
- `argus_server/server.py`

Tests to run:
- `uv run python -m unittest tests.test_research_toolkit`
- `uv run python -m unittest discover -s tests`

Known historical bugs:
- Invalid non-HTTP URLs must be rejected.
- `render_js=True` must either use the optional Crawl4AI adapter or return a clear missing-install error.
- Gallery downloads must not write outside the project output area.
- Dry-run behavior must require explicit confirmation before executing gallery-dl.
- Cross-source topic research must normalize source names and merged result shape.
- Topic-driven image research must dedupe image URLs and preserve source page context.
- Topic-driven evidence packets must crawl page candidates and preserve page-level crawl errors.
- One-call research workflows must preserve source/page errors, retry only retriable crawl failures, keep exports inside the project directory, and write valid JSON/Markdown artifacts when requested.
- Page-crawling research flows must still find URL-bearing source items when a web provider answer summary has no URL and occupies the top merged slot at low limits.
- Optional `web:<provider>` research sources must preserve provider errors and normalize answer/result/citation shapes when configured.
- Optional `codex` research source must preserve missing-SDK errors and normalize JSON SDK/runner output into the same merged result shape.
- Research toolkit health must clearly report ready capabilities, missing setup, API key status, and attached adapters.

### Flow: MCP server import and tool registration

Related modules:
- `argus_server/server.py`
- `argus_server/tools/`

Tests to run:
- No dedicated automated test is mapped yet.
- Use a targeted import/registration smoke check before changing tool registration.

Known historical bugs:
- Public MCP surface is large and client-facing; tool names, signatures, and response shapes are regression-sensitive.

### Flow: CLI adapter auth and envelope normalization

Related modules:
- `argus_server/tools/cli_tools.py`
- `argus_server/tools/social_ops.py`
- `argus_server/server.py`

Tests to run:
- `uv run python -m unittest tests.test_cli_tools`
- `uv run python -m unittest tests.test_social_ops`
- `uv run python -m unittest discover -s tests`

Known historical bugs:
- xhs CLI cookie or login failures can emit raw tracebacks; MCP responses must return actionable auth/storage error codes instead.
- `xhs_*` SocialOps tools must not run business commands when auth is not ready, while confirm gates must still short-circuit first.

### Flow: Storage-backed data retrieval

Related modules:
- `argus/storage/`
- `argus_server/services/parser_service.py`
- `argus_server/tools/data_query.py`
- `argus_server/tools/search_tools.py`

Tests to run:
- No dedicated automated test is mapped yet.
- Add temporary SQLite fixture tests when changing schemas, storage backends, parser service, or query/search tools.

Known historical bugs:
- URL/platform dedupe, RSS feed/item uniqueness, crawl history, and AI filter versioning are schema-sensitive.

### Flow: Scheduler and notification automation

Related modules:
- `argus_server/tools/scheduler.py`
- `argus_server/scheduler_runner.py`
- `argus_server/tools/notification.py`
- `argus/notification/`

Tests to run:
- No dedicated automated test is mapped yet.
- Add dry-run plist/workflow and notification mock tests before changing launchd or webhook behavior.

Known historical bugs:
- launchd requires capitalized `Hour`, `Minute`, `Day`, `Weekday`, and `Month` keys; lowercase keys can trigger at the wrong cadence.

## Bug Regression Tests

### Research toolkit safe gallery output

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Prevents `download_gallery` from accepting output directories outside the project root and preserves safe dry-run behavior.

### Research toolkit invalid URL handling

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Prevents `crawl_url` from fetching unsupported schemes such as `file://`.

### Research toolkit optional Crawl4AI rendering

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Keeps `crawl_url(render_js=True)` dependency-optional: missing Crawl4AI returns `NOT_INSTALLED`, while Crawl4AI results normalize back into the standard title/text/links/images response shape.

### Research toolkit source merge shape

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Keeps `research_topic` merged results normalized across Hacker News and Wikipedia adapters.

### Research toolkit optional web search source

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Keeps optional `web:<provider>` sources normalized through the existing AI web search adapter and preserves adapter-unavailable errors without failing the whole research topic response.

### Research toolkit optional Codex SDK source

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Keeps optional `codex` source dependency-optional: injected runner output normalizes into merged research results, while missing `openai-codex` returns `NOT_INSTALLED` without failing the whole `research_topic` response.

### Research toolkit topic image discovery

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Keeps `research_images` tied to topic search results, preserves source page context, dedupes repeated image URLs across pages, and reports source errors without failing the whole response.

### Research toolkit evidence pack generation

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Keeps `research_pack` tied to topic search page candidates, crawls page text into structured documents, and preserves page-level crawl errors without failing the whole response.

### Research toolkit web answer page candidate fallback

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Keeps `research_images`, `research_pack`, and `research_workflow` crawling URL-bearing web results when a provider answer summary has no URL and would otherwise occupy the only merged slot at `limit=1`.

### Research toolkit capability health matrix

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Keeps `research_toolkit_health` useful for MCP clients by reporting immediate readiness, missing optional setup, configured web providers, and attached adapters.

### xhs CLI auth status and friendly errors

Test file:
- `tests/test_cli_tools.py`
- `tests/test_social_ops.py`

What it protects:
- Keeps `xhs_auth_status` dependency-safe, ensures xhs cookie/auth failures return `AUTH_STORAGE_UNAVAILABLE` or `AUTH_REQUIRED`, and prevents `xhs_*` SocialOps tools from running business commands before auth is ready.
