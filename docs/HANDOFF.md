# Argus Project Handoff

Last updated: 2026-07-10

This is the durable project handoff. Start new engineering sessions by reading
`AGENTS.md`, then `context.md`, then only the source and tests relevant to the
current task. Use `.codex-memory.yaml` for workflow, shared-module, architecture,
storage, schema, auth, refactor, or bug-fix work.

## Current State

- Branch: `feature/intelligence-toolkit`.
- Runtime: Python 3.12+ with `uv`.
- MCP surface: 166 FastMCP tools and 8 resources.
- Research Toolkit: 11 public MCP tools.
- Verification baseline: 87 tests passing and `uv build` successful.
- Current delivery report: `docs/RESEARCH_TOOLKIT_PHASE2_DELIVERY_AUDIT.md`.

## Primary Commands

```bash
uv run python -m unittest discover -s tests
uv build
uv run python scripts/research_crawl_quality_smoke.py
uv run python scripts/research_artifact_smoke.py
uv run python scripts/research_batch_handoff_smoke.py
uv run python -c 'from argus_server.server import _get_tools; print(_get_tools()["research"].research_runtime_probe())'
```

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

All saved paths must remain inside the Argus project. Handoff responses use
project-relative paths and avoid replaying full crawled page text.

## Runtime Notes

- Public HTTP and Wikipedia paths are ready without API keys.
- Crawl4AI, gallery-dl, yt-dlp, Scrapy, and openai-codex are installed locally.
- Commercial web providers are inactive until a Tavily, Exa, Perplexity, or
  Brave API key is configured.
- The Codex SDK package is installed, but the current user-level Codex config
  uses unsupported reasoning effort `ultra`; Argus does not modify global Codex
  settings.
- `research_runtime_probe` is the explicit check for Crawl4AI/Codex runtime
  compatibility; normal health reports package and CLI readiness only.
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
