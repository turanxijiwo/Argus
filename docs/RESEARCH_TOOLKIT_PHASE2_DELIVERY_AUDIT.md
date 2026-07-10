# Research Toolkit Phase 2 Delivery Audit

Date: 2026-07-10

> Historical Phase 2 delivery baseline: 165 FastMCP tools and 10 Research
> Toolkit tools. Phase 3 later added `research_runtime_probe`; use `context.md`
> and `docs/HANDOFF.md` for the current surface.

## Verdict

Research Toolkit Phase 2 is ready for personal, agent-driven research using
built-in HTTP crawling and public sources. Saved single and batch workflows,
Markdown briefs, artifact review, and all three handoff schemas are verified.

Optional commercial web providers remain unconfigured. The installed Codex SDK
is currently blocked by incompatible user-level Codex configuration; this does
not affect the built-in or Wikipedia paths.

## Delivered Surface

- FastMCP: 165 tools and 8 resources.
- Research Toolkit: 10 public MCP tools.
- Single workflow schema: `argus.research.workflow.handoff.v1`.
- Batch workflow schema: `argus.research.batch.handoff.v1`.
- Review schema: `argus.research.review.handoff.v1`.
- Saved outputs: project-local JSON evidence packets and Markdown briefs.
- Review inputs: direct artifact path, single-workflow handoff, or batch
  handoff plus `artifact_index`.

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| Full unit/regression suite | Ready | 87 tests passed. |
| Package build | Ready | `argus-6.6.1` sdist and wheel built successfully. |
| MCP registration | Ready | Tests require 165 total tools and all 10 Research Toolkit tools. |
| Public crawl quality | Ready | Both fixed public fixtures and one Wikipedia workflow passed; exit code 0. |
| Crawl4AI rendering | Ready | `https://example.com` rendered successfully with Crawl4AI 0.9.0. |
| Single artifact handoff | Ready | JSON/Markdown saved, review handoff matched, score 100; exit code 0. |
| Batch artifact handoff | Ready | Two artifacts ready, indexed review path matched, score 100; exit code 0. |
| gallery-dl safety | Ready | Installed adapter returned dry-run mode with `confirm_required=true`. |
| Commercial web providers | Not configured | Provider smoke returned `NO_CONFIGURED_PROVIDER`. |
| Codex SDK source | Blocked by user config | SDK rejected global reasoning effort `ultra`; installed parser accepts through `xhigh`. |

## Reproduction Commands

```bash
uv run python -m unittest discover -s tests
uv build
uv run python scripts/research_crawl_quality_smoke.py
uv run python scripts/research_artifact_smoke.py
uv run python scripts/research_batch_handoff_smoke.py
uv run python scripts/research_codex_smoke.py --query "OpenAI research toolkit"
uv run python scripts/research_provider_smoke.py --query "OpenAI research toolkit"
```

## Supported Personal Workflows

1. Search public/local sources and normalize results with `research_topic`.
2. Crawl evidence pages and extract images with `research_pack` or
   `research_images`.
3. Generate and save one JSON/Markdown packet with `research_workflow`.
4. Run several saved packets and a review report with
   `research_batch_workflow`.
5. Pass either workflow handoff directly to `research_review_artifact`.
6. Select one batch artifact for focused review with `artifact_index`.

## Remaining Risks

- The health matrix detects whether optional packages are installed; it does
  not prove that user-level runtime configuration is compatible.
- Tavily, Exa, Perplexity, and Brave need their respective API keys before
  provider smokes can run.
- Crawl4AI and Codex SDK may need approved access to user-level cache/state
  directories in restricted Codex sessions.
- Image research currently extracts candidates from discovered pages; there is
  no dedicated image-search backend.
- Xiaohongshu access still requires normal manual login. Argus does not bypass
  authentication or refresh cookies outside the CLI's supported flow.

## Codex Configuration Note

The audit did not modify global Codex settings. The installed SDK reported that
`model_reasoning_effort = "ultra"` is invalid and listed `xhigh` as its highest
accepted value. OpenAI's model documentation also documents `xhigh` reasoning
effort for Codex models:

- https://developers.openai.com/api/docs/models/gpt-5.2-codex

After the user-level configuration is corrected by the user, rerun
`scripts/research_codex_smoke.py` to promote the Codex source from blocked to
runtime-verified.

## Phase 2 Exit Decision

Core Phase 2 is accepted. Future work should be treated as Phase 3 and should
focus on optional runtime probes, provider activation, or a dedicated
image-search adapter rather than expanding the core handoff contract.
