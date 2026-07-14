# Argus Project Handoff

Last updated: 2026-07-14

This is the durable project handoff. Start new engineering sessions by reading
`AGENTS.md`, then `context.md`, then only the source and tests relevant to the
current task. Use `.codex-memory.yaml` for workflow, shared-module, architecture,
storage, schema, auth, refactor, or bug-fix work.

## Current State

- Branch: `feature/intelligence-toolkit`.
- Runtime: Python 3.12+ with `uv`.
- MCP surface: 173 FastMCP tools and 8 resources.
- Research Toolkit: 18 public MCP tools, including key-free `research_audio` and metadata-only `research_video_metadata`.
- Verification baseline: 262 tests passing and `uv build` successful.
- Historical Phase 2 delivery report: `docs/RESEARCH_TOOLKIT_PHASE2_DELIVERY_AUDIT.md`.

## Primary Commands

```bash
uv run python -m unittest discover -s tests
uv build
uv run python scripts/research_crawl_quality_smoke.py
uv run python scripts/research_artifact_smoke.py
uv run python scripts/research_batch_handoff_smoke.py
uv run python scripts/research_runtime_probe_smoke.py
uv run python scripts/research_audio_smoke.py
uv run python -m unittest tests.test_research_video
```

## Cross-Project MCP

Use an explicit project root so a client launched from another repository keeps
Argus configuration, data, indexes, and artifacts inside the Argus project:

```bash
codex mcp add argus -- /absolute/path/to/Argus/.venv/bin/python \
  -m argus_server.server \
  --project-root /absolute/path/to/Argus
```

The current host has this user-level registration enabled. Acceptance was run
from outside the repository with both a generic FastMCP client and ephemeral
`codex exec`; each initialized the STDIO server, and the Codex run called
`research_toolkit_health` plus `system_health` successfully. Other machines
must register their own absolute project path.

## Research Toolkit Flow

```text
research_topic / public sources
  -> research_workflow
  -> JSON + Markdown artifacts
  -> workflow handoff
  -> research_review_artifact
  -> review handoff
```

For multiple queries:

```text
research_batch_workflow
  -> artifact_paths[] + Markdown review report
  -> batch handoff
  -> research_review_artifact(artifact_index=N)
```

For comparison and bounded evidence replay:

```text
saved resource artifacts
  -> research_compare_artifacts
  -> comparison JSON + SHA-256 source/locator registry
  -> optional project-local CSL-JSON/RIS files (save_citations=True)
  -> research_audit_comparison(all used locator IDs, no evidence text)
  -> verified / unverified / failed integrity summary
  -> research_resolve_locators(1-10 locator IDs)
  -> verified excerpts capped at 240 characters and 25 words each
```

All saved paths must remain inside the Argus project. Handoff responses use
project-relative paths and avoid replaying full crawled page text. Locator
resolution and full comparison audit are local and key-free; comparison generation itself uses Codex.
Comparisons created before source fingerprints were introduced remain readable,
but audit and locator responses identify their integrity as unverified.

## Runtime Notes

- `initialize_config` validates `config/config.example.yaml`, creates the default
  config only when missing, and never overwrites an existing valid or invalid file.
- `trigger_crawl` always attempts the core SQLite write. Its legacy
  `save_to_local` parameter requests additional TXT/HTML snapshots, and the response
  reports database and snapshot persistence independently.
- The ignored real project config now exists and is byte-identical to the template.
  Real crawl cycles have persisted 509 items across all 11 configured platforms
  and six crawl records; `get_latest_news` reads them back successfully.
- The local BM25 index contains 509 documents and 2,656 terms. A real `AI` query
  returned three readable positive-score results after the latest rebuild.
- The active Codex workspace automation runs the no-notification crawl-before-index
  cycle every two hours. Its first real cycle passed all crawl, index, backup, and
  semantic-probe gates; native launchd remains blocked by Desktop folder access.
- `search_arxiv` stores successful normalized responses for 24 hours under ignored
  `output/cache/arxiv/`, spaces uncached requests by at least three seconds per
  adapter instance, retries short 429 responses once, and preserves persistent or
  long limits as `RATE_LIMITED` with retry metadata.
- Semantic rebuild uses a project-bound operation-scoped storage manager and closes
  SQLite in the same worker thread; the original cross-thread cleanup error is fixed.
- Required health checks now pass with `ready=true` and `status=degraded`. The
  template Feishu webhook is still a placeholder and is currently misclassified
  as configured, but notifications are intentionally out of scope at the user's
  request. Do not configure or send them unless that priority changes.
- Public HTTP and Wikipedia paths are ready without API keys.
- Openverse image and audio metadata search is ready without API keys; no media
  is downloaded and returned license metadata still requires independent review.
- Crawl4AI, gallery-dl, yt-dlp, Deno, Scrapy, and openai-codex are installed locally.
- `research_video_metadata` uses yt-dlp in metadata-only mode for one public URL;
  it ignores config and cookies, disables downloads and remote components, and
  omits formats, download payloads, thumbnails, subtitles, and direct media URLs.
- Commercial web providers are inactive until a Tavily, Exa, Perplexity, or
  Brave API key is configured.
- The Codex SDK and current user-level configuration have been runtime-verified
  with `research_runtime_probe`; the backup made before the authorized config
  update remains outside the repository.
- `research_runtime_probe` is the explicit check for Crawl4AI/Codex runtime
  compatibility; normal health reports package and CLI readiness only.
- `system_health`, `get_system_status`, and `system://health` share one readiness
  snapshot. Top-level `success` means the check executed; `ready` and `status`
  distinguish required business readiness from optional degraded capabilities.
- Web `/api/health` is liveness-only and intentionally returns `ready=null`.
- Xiaohongshu requires normal manual login. No authentication bypass or
  unsupported cookie refresh is implemented.

## Source Of Truth

- Project rules and inventories: `AGENTS.md`.
- Short active status: `context.md`.
- Product overview and tool groups: `README.md`.
- Research usage examples: `docs/RESEARCH_WORKFLOW_EXAMPLES.md`.
- Phase 2 evidence and remaining risks:
  `docs/RESEARCH_TOOLKIT_PHASE2_DELIVERY_AUDIT.md`.
- Regression-sensitive flows: `engineering-memory/tests/regression-map.md`.

Do not restore old tool counts, credential paths, machine-specific process IDs,
or completed historical batches into this handoff.
