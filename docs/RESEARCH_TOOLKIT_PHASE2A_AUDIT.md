# Research Toolkit Phase 2A Readiness Audit

Date: 2026-07-08

This audit checks the current local/runtime readiness for Research Toolkit Phase
2 work. It does not add dependencies, does not install optional tools, does not
download media, and does not bypass platform login or browser-session controls.

## Scope

Phase 2A covers:

- FastMCP registration readiness.
- Runtime adapter attachment and optional dependency status.
- Safe public-page crawl smoke.
- Safe `gallery-dl` dry-run smoke.
- Public-source `research_topic` and `research_workflow` smoke.
- Codex SDK and Crawl4AI readiness checks.

It does not cover:

- Authenticated website scraping.
- Media download execution.
- Automatic optional dependency installation.
- Dedicated image-search backend selection.
- Posting, commenting, deleting, or other destructive social actions.

## Current Result

Overall status: ready for Phase 2B Codex-first validation. Commercial
web-provider validation remains optional when a provider API key is available.

| Area | Status | Evidence |
|---|---|---|
| MCP registration | Ready | FastMCP exposes 163 tools and all eight Research Toolkit tools. |
| Built-in HTTP crawl | Ready | `crawl_url("https://example.com")` returned HTTP 200, title, text, and one link. |
| Page image discovery | Ready | `discover_page_images("https://example.com")` completed successfully with zero images, as expected for the page. |
| Public source search | Ready | `research_topic("OpenAI", sources=["wikipedia"], limit=1)` returned one URL-bearing result. |
| Public workflow | Ready | `research_workflow("OpenAI", sources=["wikipedia"], limit=1)` crawled one document, extracted images, and preserved zero source/crawl errors. |
| Markdown brief | Ready | Workflow brief payload contains Markdown `content` and summary reports `brief_included=true`. |
| gallery-dl dry-run | Ready | `download_gallery(..., confirm=False)` returned a dry-run command with project-local `cwd` and `confirm_required=true`. |
| Crawl4AI package | Ready with permission note | Import succeeds; `render_js=True` succeeds outside the sandbox but fails inside the restricted sandbox because Crawl4AI cannot open its database file. |
| Codex SDK source | Ready with permission note | Import succeeds; `research_topic(..., sources=["codex"])` succeeds outside the sandbox and returns one URL-bearing result, but fails inside the restricted sandbox because `~/.codex` sqlite state is read-only. |
| Codex source smoke | Ready with permission note | `scripts/research_codex_smoke.py` returned exit code `0` with one URL-bearing topic result, one successful workflow document, one image, and a Markdown brief when run with approved unsandboxed execution; the same command returns exit code `2` inside the restricted sandbox because `~/.codex` sqlite state is read-only. |
| Tavily / Exa / Perplexity / Brave | Not configured | No web-search provider API env vars are set in the current process. |

## Runtime Health Summary

MCP-attached adapters:

- `external_api_attached=true`
- `local_search_attached=true`
- `ai_search_attached=true`
- `codex_runner_attached=false`

Optional runtime status:

- `crawl4ai`: installed/importable.
- `gallery-dl`: installed on `PATH`.
- `openai-codex`: installed/importable.
- `scrapy`: installed on `PATH`.
- `yt-dlp`: installed on `PATH`.

Configured web-search providers:

- Tavily: not configured.
- Exa: not configured.
- Perplexity: not configured.
- Brave: not configured.

## Permission Notes

The Codex app sandbox restricts writes outside the workspace. Two optional
runtimes need user-level state directories:

- Crawl4AI needs to open its local runtime database/cache.
- OpenAI Codex SDK needs write access to `~/.codex` sqlite state.

Both smokes passed when run with explicit elevated permission. This means the
adapters are locally usable, but browser/Codex runtime checks may require
approved unsandboxed execution in future Codex sessions.

## Next Recommended Work

1. Run `scripts/research_codex_smoke.py` with approved unsandboxed execution in
   Codex sessions to validate the personal Codex source path without commercial
   provider keys.
2. Configure exactly one web-search provider key only if commercial-provider
   validation is needed, then run `scripts/research_provider_smoke.py` against
   `web:<provider>`.
3. Add a small public-page fixture list for repeatable crawl quality checks.
4. Decide whether Crawl4AI should have an explicit
   `--allow-unsandboxed-runtime-check` style helper, so future audits do not
   confuse sandbox permission failures with adapter failures.

## Phase 2B Workflow Examples

`docs/RESEARCH_WORKFLOW_EXAMPLES.md` contains reusable MCP prompts and equivalent
tool arguments for:

- Codex-source research that saves JSON and Markdown artifacts without
  commercial provider keys.
- Wikipedia public-source research that avoids Codex SDK runtime state.
- Optional `web:<provider>` research after a provider key is configured.

## Phase 2B Codex Smoke Entry

Run the smoke from a Codex session after approving unsandboxed execution when
prompted:

```bash
uv run python scripts/research_codex_smoke.py --query "OpenAI research toolkit"
```

The script uses `sources=["codex"]` and does not require Tavily, Exa,
Perplexity, Brave, or another commercial provider key.

Exit codes:

- `0`: Codex source and workflow contract passed.
- `2`: local Codex SDK, state, or permission is unavailable.
- `3`: Codex ran but the returned research chain did not satisfy the expected
  URL/workflow-document contract.

## Phase 2B Provider Smoke Entry

Run the optional provider smoke after setting one provider key in the
environment:

```bash
uv run python scripts/research_provider_smoke.py --provider tavily --query "OpenAI research toolkit"
```

If no provider key is configured, the script exits with code `2` and returns a
JSON payload with `status="skipped"` and `reason="NO_CONFIGURED_PROVIDER"`.

Provider env vars:

- `TAVILY_API_KEY`
- `EXA_API_KEY`
- `PERPLEXITY_API_KEY`
- `BRAVE_API_KEY`
