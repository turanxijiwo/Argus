# Context

## 当前任务

- Engineering Memory has been initialized for Argus. Future work should start from `AGENTS.md` + `context.md`, then read `.codex-memory.yaml` only for triggered tasks such as bug fixes, architecture changes, shared modules, data schemas, storage/cache, workflows, or refactors.
- Current product focus remains the Argus agent-native research and intelligence toolkit: 164 MCP tools, local/search analysis, scheduling, notifications, Web Dashboard, and research-toolkit adapters.
- Latest implementation step: added `argus_server/tools/research_handoff.py` so MCP and script batch workflows both expose the shared `argus.research.batch.handoff.v1` handoff block.

## 已知问题

- JavaScript rendering now has an optional Crawl4AI runtime adapter through `crawl_url(render_js=True)`, but it requires Crawl4AI and browser dependencies to be installed locally.
- Broad web search can now reuse configured Tavily / Exa / Perplexity / Brave providers through `research_topic` sources such as `web:tavily`; optional local Codex SDK research is available through the `codex` source when `openai-codex` is installed; `research_images` provides page-derived image candidates, while a dedicated image-search backend remains a future adapter.
- `research_pack` uses `research_topic` page candidates and built-in `crawl_url`; source/page failures are preserved in the response instead of failing the whole packet.
- `research_workflow` can save JSON and Markdown research artifacts under a project-local output directory; unsafe output paths are rejected before search/crawl work starts.
- `web:<provider>` answer summaries are useful in `research_topic.merged`, but page-crawling workflows must build candidates from both merged results and source raw items because answers can have no URL.
- xhs CLI access still requires normal manual Xiaohongshu login; Argus reports expired/unavailable auth clearly, preflights `xhs_*` tools before business commands, and does not attempt to bypass login or auto-refresh cookies.
- Codex SDK responses must return JSON for `research_topic(sources=["codex"])`; invalid JSON returns `PARSE_ERROR`, and missing SDK returns `NOT_INSTALLED`.
- `download_gallery` requires `gallery-dl` to be installed locally and defaults to dry-run for safety.
- Phase 2A audit found Crawl4AI and Codex SDK are installed and usable with approved unsandboxed execution, but both can fail inside the restricted Codex sandbox because they need user-level state/cache writes.
- No Tavily / Exa / Perplexity / Brave API keys are configured in the current runtime; `web:<provider>` smoke remains optional, while `scripts/research_codex_smoke.py` is the primary no-provider-key smoke path.
- `scripts/research_codex_smoke.py` exits with code 2 for Codex SDK/state/permission unavailability and code 3 for Codex research-contract failures; the approved unsandboxed smoke currently passes with one URL-bearing topic result and one successful workflow document.
- `scripts/research_provider_smoke.py` exits with code 2 and `NO_CONFIGURED_PROVIDER` when no provider key is configured; with a key, it validates `research_topic`, `research_pack`, and `research_workflow` against the chosen `web:<provider>` source.
- `scripts/research_crawl_quality_smoke.py` exits with code 0 only when both public crawl fixtures and the public Wikipedia workflow pass; the current local smoke passes with two fixture pages, one successful Wikipedia workflow document, five images, and a Markdown brief.
- `docs/RESEARCH_WORKFLOW_EXAMPLES.md` is now the preferred handoff for running saved JSON + Markdown research workflows from an MCP client.
- `scripts/research_artifact_smoke.py` saves artifacts under ignored `output/research/artifact-smoke/` and verifies JSON parseability, Markdown brief structure, project-local paths, successful documents, and readable handoff fields; the current local smoke passes with one successful document and Markdown/JSON artifacts saved.
- `scripts/research_artifact_review.py` scans saved JSON artifacts under `output/research/` or explicit paths, scores readability/reuse quality, summarizes key documents and warnings, and can write a Markdown review report under ignored output paths; the current local review report is ready with score 100 and no warnings.
- `scripts/research_batch_workflow.py` runs one or more saved workflows, stores artifacts under ignored `output/research/batch/`, prints project-relative artifact paths, and writes `output/research/artifact-reviews/batch-review.md` through the local artifact review pipeline; the current local batch for OpenAI and AI safety passes with two ready artifacts and average score 100.
- The MCP `research_batch_workflow` tool now exposes batch saved-workflow execution to agents directly, dedupes query lists, saves per-query JSON/Markdown artifacts, writes a compact review report, and returns only counts plus project-relative paths; the current local MCP batch for OpenAI and AI safety passes with two ready artifacts and average score 100.
- `research_runtime.py` now owns Research Toolkit session headers, max HTML/text limits, retriable crawl error defaults, and automatic workflow source selection; this is a structure-only split from `research_toolkit.py`.
- MCP and script batch workflows now share `handoff.schema == "argus.research.batch.handoff.v1"` with entrypoint, readiness, artifact/brief paths, review report, status counts, average score, output dir, and process exit code when applicable; current local MCP and script batch runs both pass with two ready artifacts and average score 100.
- `docs/HANDOFF.md` appears older than README/source for some counts and roadmap status; prefer README and current source when they disagree.

## 最近变更记录

- Added the shared Research Toolkit batch handoff block for both MCP and terminal batch outputs, plus tests that lock the schema and script exit-code field.
- Split Research Toolkit runtime defaults/session setup into `research_runtime.py` so `research_toolkit.py` stays below the project 300-line reminder threshold while preserving behavior.
- Added MCP `research_batch_workflow`, `argus_server/tools/research_batch.py`, and registration/tool tests for direct agent-facing batch saved workflow execution.
- Added `scripts/research_batch_workflow.py` and tests for one-command saved workflow batch execution plus artifact review report generation.
- Added `scripts/research_artifact_review.py` and tests for local saved-artifact readability reports across one or more `research_workflow` JSON files.
- Added `scripts/research_artifact_smoke.py` and tests so saved `research_workflow` JSON + Markdown artifacts have a repeatable quality gate.
- Added `scripts/research_crawl_quality_smoke.py` and tests for repeatable public-page crawl/image/workflow quality checks without provider keys or Codex SDK state.
- Added `docs/RESEARCH_WORKFLOW_EXAMPLES.md` with MCP prompts, equivalent tool arguments, saved artifact fields, and safety notes for `research_workflow`.
- Added `docs/RESEARCH_TOOLKIT_PHASE2A_AUDIT.md` with current MCP registration, public crawl/workflow, gallery-dl dry-run, Crawl4AI, Codex SDK, and web-provider readiness results.
- Added `scripts/research_codex_smoke.py` and unit tests so Phase 2B can validate `research_topic` and `research_workflow` with `sources=["codex"]` without commercial provider keys.
- Added `scripts/research_provider_smoke.py` and unit tests so Phase 2B web-provider smoke has a repeatable command and deterministic skip behavior when no API key is configured.
- Added the Research Toolkit Phase 1 boundary document covering built-in capabilities, optional runtime adapters, explicit non-goals, safety/error contracts, verification gates, and Phase 2 candidate work.
- Added an MCP registration smoke test for the Research Toolkit public tool surface, covering the 163-tool FastMCP count and the eight expected research tools.
- Split Research Toolkit optional AI-backed source adapters into `research_source_ai.py` for web provider and Codex SDK normalization, reducing `research_sources.py` to dispatcher/local-source/page-candidate responsibilities.
- Reviewed the split Research Toolkit surface, removed unused private source-normalization wrappers from `research_toolkit.py`, and updated the server health-tool docstring to include `research_workflow`.
- Refactored Research Toolkit page crawl/image discovery entrypoints into `research_page.py` while preserving `crawl_url`, `discover_page_images`, invalid URL handling, and optional Crawl4AI behavior.
- Refactored Research Toolkit cross-source topic aggregation into `research_topic.py` while preserving the public `research_topic` method, default sources, per-source errors, and merged result ordering.
- Refactored Research Toolkit full workflow orchestration into `research_workflow.py` while preserving the public `research_workflow` method, retry behavior, brief rendering, and artifact export shape.
- Refactored Research Toolkit topic-driven image research into `research_images.py` while preserving the public `research_images` method and response shape.
- Refactored Research Toolkit evidence packet construction into `research_pack.py` while preserving the public `research_pack` method and response shape.
- Refactored Research Toolkit HTTP crawl orchestration into `research_crawl.py` for built-in HTTP response shaping, parser delegation, and page retry handling.
- Refactored Research Toolkit health helpers into `research_health.py` for optional CLI/package status, web-search provider readiness, and capability matrix construction.
- Refactored Research Toolkit Crawl4AI render helpers into `research_render.py` for optional JavaScript rendering import/runtime/timeout handling.
- Refactored Research Toolkit gallery helpers into `research_gallery.py` for safe `gallery-dl` dry-run/execution and project-local media output handling.
- Refactored Research Toolkit workflow helpers into `research_workflow.py` for crawled document construction and image confidence scoring.
- Fixed a Research Toolkit edge case where `web:<provider>` answer summaries without URLs could occupy the only merged slot at `limit=1`, leaving `research_images`, `research_pack`, and `research_workflow` with no page candidates.
- Refactored Research Toolkit source adapters into `research_sources.py` for local/news, external API, web provider, Codex SDK, page-candidate, and source-error normalization.
- Refactored Research Toolkit web helpers into `research_web.py` for URL validation, HTML parsing, HTTP fetch normalization, and Crawl4AI result formatting.
- Enhanced `research_workflow` with deterministic Markdown brief rendering and optional `.md` artifact export alongside the JSON evidence packet.
- Refactored Research Toolkit helper code into `research_brief.py` for Markdown rendering and `research_io.py` for project-local JSON/Markdown artifact writing.
- Added `research_workflow` MCP tool as a high-level research pipeline with automatic source selection, per-page crawl retries, image candidate extraction from crawled pages, and optional JSON artifact export.
- Enhanced `research_toolkit_health` with a capability matrix that reports ready status, missing API keys/packages/CLIs, setup hints, and attached adapters.
- Added `xhs_auth_status` MCP tool and normalized xhs CLI cookie/auth tracebacks into `AUTH_STORAGE_UNAVAILABLE` or `AUTH_REQUIRED`.
- Added an auth preflight guard for `xhs_*` SocialOps tools so missing/expired login blocks before running feed/comment/post/delete commands; `confirm=True` gates still short-circuit before auth checks.
- Added `research_pack` MCP tool to search a topic, crawl candidate pages, and return structured evidence documents with source/page errors.
- Added optional `research_topic` source `codex`, backed by an injected runner in tests or runtime `openai-codex` SDK when installed; it normalizes strict JSON results into the existing merged research shape.
- Added `research_images` to find topic-relevant pages, extract page image candidates, dedupe by image URL, and preserve source page context.
- Added optional Crawl4AI support for `crawl_url(render_js=True)` without adding project dependencies; missing Crawl4AI now returns a clear install hint.
- Extended `research_topic` with optional `web` / `web:<provider>` sources backed by existing AI web search providers, without adding dependencies.
- Initialized Engineering Memory: added project `AGENTS.md`, `.codex-memory.yaml`, and `engineering-memory/` files for project profile, module map, regression map, rules, bug memory, tech debt, and playbooks.
- Filled the initial project profile, architecture module map, regression map, and project inventories from README, `pyproject.toml`, storage schemas, `argus_server/server.py`, and existing tests.
- Added `ResearchToolkitTools` with page crawling, image discovery, safe gallery-dl planning/execution, optional CLI health checks, and cross-source topic research.
- Registered eight Research Toolkit MCP tools: `research_toolkit_health`, `crawl_url`, `discover_page_images`, `research_images`, `research_pack`, `research_workflow`, `download_gallery`, and `research_topic`.
- Updated README with the research toolkit MCP tools and open-source adapter roadmap.
- Added unit tests for normal and error paths in the research toolkit.
