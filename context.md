# Context

## 当前任务

- Build the first dependency-free version of an Argus research toolkit for Codex-driven information gathering.
- Keep the original GitHub project public and continue development on a feature branch.

## 已知问题

- JavaScript rendering is not implemented in the built-in crawler; it should be added through an approved Crawl4AI adapter.
- Broad web/image search still needs an approved search backend such as SearXNG, Brave, Tavily, or Firecrawl.
- `download_gallery` requires `gallery-dl` to be installed locally and defaults to dry-run for safety.

## 最近变更记录

- Added `ResearchToolkitTools` with page crawling, image discovery, safe gallery-dl planning/execution, optional CLI health checks, and cross-source topic research.
- Registered five new MCP tools: `research_toolkit_health`, `crawl_url`, `discover_page_images`, `download_gallery`, and `research_topic`.
- Updated README with the research toolkit MCP tools and open-source adapter roadmap.
- Added unit tests for normal and error paths in the research toolkit.
