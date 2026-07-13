# Research Toolkit Phase 1 Boundaries

> Historical Phase 1 contract. The current Phase 2 surface is documented in
> `RESEARCH_TOOLKIT_PHASE2_DELIVERY_AUDIT.md`.
> Phase 2 now also gives `research_images` a built-in anonymous
> `image:openverse` source; the page-first statements below remain the Phase 1
> baseline rather than the current default.

This document keeps the Research Toolkit scope explicit so later work does not
drift into unrelated crawling, account automation, or dependency installation.

## Phase 1 Goal

Phase 1 makes the Research Toolkit usable as an agent-native personal research
surface without adding project dependencies or bypassing platform login
mechanisms.

Completion means:
- The eight public MCP tools are registered and test-covered.
- The core workflow can search, crawl page candidates, extract image candidates,
  preserve source/page errors, render a Markdown brief, and optionally save JSON
  and Markdown artifacts inside the project directory.
- Capability and error responses explain missing optional setup clearly.
- Tests and Engineering Memory cover the regression-sensitive surfaces.
- Future real data source and browser-session work is listed as a later phase.

## Public MCP Surface

The public Research Toolkit surface is exactly these eight tools:

- `research_toolkit_health`
- `crawl_url`
- `discover_page_images`
- `research_images`
- `research_pack`
- `research_workflow`
- `download_gallery`
- `research_topic`

Do not add, rename, or remove public Research Toolkit MCP tools in Phase 1
without updating `README.md`, `AGENTS.md`, `context.md`, the regression map, and
the MCP registration smoke test.

## Built-In Capabilities

These capabilities work with the current project dependencies:

- `crawl_url` fetches HTTP/HTTPS pages and extracts title, description, text,
  links, and image candidates.
- `discover_page_images` extracts image candidates from page HTML without
  downloading media.
- `research_topic` normalizes results from attached Argus adapters such as local
  news search and public external API adapters.
- `research_images` finds topic pages first, then extracts image candidates while
  preserving source page context.
- `research_pack` builds structured evidence packets from topic pages and keeps
  source/page errors visible.
- `research_workflow` combines topic search, page crawl, image extraction,
  retry accounting, Markdown brief rendering, and optional project-local JSON
  and Markdown artifact export.
- `download_gallery` is always safe by default: without `confirm=True`, it only
  returns a dry-run plan.
- `research_toolkit_health` reports built-in readiness, optional tool status,
  configured web providers, and attached adapters.

## Optional Runtime Adapters

These adapters are allowed in Phase 1 only when already installed or configured
by the user. They must stay optional and must return clear setup errors when
missing.

| Adapter | Used by | Setup signal | Phase 1 behavior |
|---|---|---|---|
| Tavily / Exa / Perplexity / Brave | `research_topic`, `research_images`, `research_pack`, `research_workflow` | `TAVILY_API_KEY`, `EXA_API_KEY`, `PERPLEXITY_API_KEY`, or `BRAVE_API_KEY` | Reuse existing AI web search provider adapters through `web:<provider>` sources. |
| Codex SDK | `research_topic`, `research_workflow` | `openai-codex` Python package or injected runner; optional `ARGUS_CODEX_MODEL` | Return strict normalized JSON results, or `NOT_INSTALLED` / `PARSE_ERROR` / runner errors. |
| Crawl4AI | `crawl_url(render_js=True)`, `research_workflow(render_js=True)` | `crawl4ai` Python package and local browser setup | Return rendered page extraction when available, otherwise `NOT_INSTALLED` with install hint. |
| gallery-dl | `download_gallery` | `gallery-dl` executable on `PATH` | Return a safe dry-run plan by default; execute only with `confirm=True` and project-local output. |
| Existing social CLIs | Non-Research SocialOps tools | User-installed CLIs and normal manual login | Report missing/expired auth clearly; never bypass login or auto-refresh cookies. |

## Explicit Non-Goals For Phase 1

Do not include these in Phase 1:

- Adding new project dependencies.
- Installing optional tools automatically.
- Bypassing Xiaohongshu or other platform login, cookies, rate limits, or access
  controls.
- Using the user's browser session to scrape authenticated sites.
- Building a dedicated image-search backend.
- Downloading media by default.
- Running destructive or posting actions without explicit `confirm=True`.
- Replacing existing Argus data/search modules with the Research Toolkit.

## Error And Safety Contracts

Phase 1 tools should keep these contracts stable:

- Invalid or unsupported URLs fail before network work.
- Unsafe output paths fail before search, crawl, or download work.
- Missing optional CLIs/packages/API keys return actionable setup errors.
- Source failures are stored in `source_errors`.
- Page crawl failures are stored on individual document/page entries.
- `web:<provider>` answer summaries without URLs must not hide URL-bearing raw
  source items from page-crawling workflows.
- Saved artifacts stay under the project root.

## Verification Gates

Run these before calling Phase 1 Research Toolkit work complete:

```bash
uv run python -m py_compile argus_server/server.py argus_server/tools/research_toolkit.py argus_server/tools/research_*.py
uv run python -m unittest tests.test_mcp_registration
uv run python -m unittest tests.test_research_toolkit
uv run python -m unittest discover -s tests
git diff --check
```

At Phase 1 completion, the expected public MCP tool count was `163`, with all
eight Research Toolkit tools present. The current Phase 2 surface intentionally
extends that baseline.

## Phase 2 Candidate Work

Future work can be considered only after Phase 1 is complete and verified:

- Real provider smoke tests for configured Tavily / Exa / Perplexity / Brave.
- Local Crawl4AI installation verification and browser dependency diagnostics.
- Optional browser-session research through an explicit user-approved tool path.
- Dedicated image-search backend selection after API/license/rate-limit review.
  Completed later with the anonymous `image:openverse` source, including
  attribution metadata, license-verification warnings, and rate-limit errors.
- SearXNG or other metasearch adapter evaluation.
- Deeper media tooling around `gallery-dl` and `yt-dlp`, still dry-run by
  default.
