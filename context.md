# Context

## 当前任务

- Engineering Memory has been initialized for Argus. Future work should start from `AGENTS.md` + `context.md`, then read `.codex-memory.yaml` only for triggered tasks such as bug fixes, architecture changes, shared modules, data schemas, storage/cache, workflows, or refactors.
- Current product focus remains the Argus agent-native research and intelligence toolkit: 160 MCP tools, local/search analysis, scheduling, notifications, Web Dashboard, and research-toolkit adapters.

## 已知问题

- JavaScript rendering now has an optional Crawl4AI runtime adapter through `crawl_url(render_js=True)`, but it requires Crawl4AI and browser dependencies to be installed locally.
- Broad web search can now reuse configured Tavily / Exa / Perplexity / Brave providers through `research_topic` sources such as `web:tavily`; `research_images` provides page-derived image candidates, while a dedicated image-search backend remains a future adapter.
- `download_gallery` requires `gallery-dl` to be installed locally and defaults to dry-run for safety.
- `docs/HANDOFF.md` appears older than README/source for some counts and roadmap status; prefer README and current source when they disagree.

## 最近变更记录

- Enhanced `research_toolkit_health` with a capability matrix that reports ready status, missing API keys/packages/CLIs, setup hints, and attached adapters.
- Added `research_images` to find topic-relevant pages, extract page image candidates, dedupe by image URL, and preserve source page context.
- Added optional Crawl4AI support for `crawl_url(render_js=True)` without adding project dependencies; missing Crawl4AI now returns a clear install hint.
- Extended `research_topic` with optional `web` / `web:<provider>` sources backed by existing AI web search providers, without adding dependencies.
- Initialized Engineering Memory: added project `AGENTS.md`, `.codex-memory.yaml`, and `engineering-memory/` files for project profile, module map, regression map, rules, bug memory, tech debt, and playbooks.
- Filled the initial project profile, architecture module map, regression map, and project inventories from README, `pyproject.toml`, storage schemas, `argus_server/server.py`, and existing tests.
- Added `ResearchToolkitTools` with page crawling, image discovery, safe gallery-dl planning/execution, optional CLI health checks, and cross-source topic research.
- Registered six Research Toolkit MCP tools: `research_toolkit_health`, `crawl_url`, `discover_page_images`, `research_images`, `download_gallery`, and `research_topic`.
- Updated README with the research toolkit MCP tools and open-source adapter roadmap.
- Added unit tests for normal and error paths in the research toolkit.
