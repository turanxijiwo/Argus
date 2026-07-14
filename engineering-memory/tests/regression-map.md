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
- `argus_server/tools/research_runtime.py`
- `argus_server/tools/research_handoff.py`
- `argus_server/tools/research_page.py`
- `argus_server/tools/research_health.py`
- `argus_server/tools/research_crawl.py`
- `argus_server/tools/research_sources.py`
- `argus_server/tools/research_source_ai.py`
- `argus_server/tools/research_topic.py`
- `argus_server/tools/research_images.py`
- `argus_server/tools/research_video.py`
- `argus_server/tools/research_pack.py`
- `argus_server/tools/research_workflow.py`
- `argus_server/tools/research_batch.py`
- `argus_server/tools/research_gallery.py`
- `argus_server/tools/research_render.py`
- `argus_server/tools/research_web.py`
- `argus_server/tools/research_brief.py`
- `argus_server/tools/research_io.py`
- `argus_server/tools/research_review.py`
- `argus_server/tools/research_compare.py`
- `argus_server/tools/research_compare_contract.py`
- `argus_server/tools/research_compare_sources.py`
- `argus_server/tools/research_compare_brief.py`
- `argus_server/tools/research_compare_audit.py`
- `argus_server/tools/research_comparison_artifact.py`
- `argus_server/tools/research_citation.py`
- `argus_server/tools/research_citation_bundle.py`
- `argus_server/tools/research_integrity.py`
- `argus_server/tools/research_locator.py`
- `argus_server/tools/research_locator_evidence.py`
- `argus_server/server.py`

Tests to run:
- `uv run python -m unittest tests.test_research_toolkit`
- `uv run python -m unittest tests.test_research_provider_smoke`
- `uv run python -m unittest tests.test_research_codex_smoke`
- `uv run python -m unittest tests.test_research_crawl_quality_smoke`
- `uv run python -m unittest tests.test_research_openverse_smoke`
- `uv run python -m unittest tests.test_research_video`
- `uv run python -m unittest tests.test_research_artifact_smoke`
- `uv run python -m unittest tests.test_research_artifact_review`
- `uv run python -m unittest tests.test_research_batch_workflow`
- `uv run python -m unittest tests.test_research_batch_handoff_smoke`
- `uv run python -m unittest tests.test_research_probe`
- `uv run python -m unittest tests.test_research_runtime_probe_smoke`
- `uv run python -m unittest tests.test_research_compare`
- `uv run python -m unittest tests.test_research_compare_sources`
- `uv run python -m unittest tests.test_research_compare_locators`
- `uv run python -m unittest tests.test_research_compare_exports`
- `uv run python -m unittest tests.test_research_compare_audit`
- `uv run python -m unittest tests.test_research_locator`
- `uv run python -m unittest tests.test_research_path_safety`
- `uv run python -m unittest tests.test_mcp_registration`
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
- Phase 1 scope must stay explicit in `docs/RESEARCH_TOOLKIT_BOUNDARIES.md`: no new dependencies, no login bypass, optional adapters stay optional, and Phase 2 candidates remain separate.
- Phase 2B Codex-source smoke must distinguish local SDK/state/permission unavailability from Codex research-contract failures and validate the topic-to-workflow chain when available.
- Phase 2B web-provider smoke must skip clearly when no provider key is configured and must validate `research_topic`, `research_pack`, and `research_workflow` when a provider is available.
- Phase 2B public crawl quality smoke must validate fixed public page fixtures, image discovery shape, and a key-free Wikipedia `research_workflow` before treating crawl quality as ready.
- Openverse quality smoke must validate anonymous direct-image URLs, source pages, non-mature filtering, license/attribution metadata, notices, rate-limit metadata, source errors, and no-download behavior with stable exit codes.
- Openverse audio search must remain metadata-only, bounded, non-mature, URL-deduplicated, license-verification-aware, and explicit about rate-limit, timeout, and provider-response failures.
- yt-dlp metadata inspection must remain single-URL and metadata-only, ignore user config and cookies, disable cache/remote components/playlists/downloads, sanitize errors, and never return format, requested-download, thumbnail, subtitle, or temporary media URLs.
- Saved workflows must treat `image:openverse` as an explicit direct-image source, preserve license metadata in JSON/Markdown artifacts, dedupe against page images, and keep Openverse failures source-scoped without changing default sources.
- Workflow/review/batch handoffs and standalone artifact review must distinguish Openverse from page images, report complete-license and verification-required counts, and keep license warnings separate from quality score/ready semantics.
- Phase 2C artifact smoke must verify saved JSON and Markdown outputs are parseable, project-local, structurally readable, and tied to successful workflow documents.
- Phase 2C artifact review must summarize saved research quality without full page-text replay, classify ready/partial/needs-attention artifacts, and preserve warnings for source/page/brief risks.
- Phase 2C batch workflow must run multiple saved workflows, collect project-relative artifact paths, and generate a review report without requiring provider keys or replaying full page text.
- Phase 2D MCP batch workflow must expose the batch saved-workflow loop directly to agents while returning compact summaries and project-relative paths instead of full crawled page text.
- Phase 2E runtime defaults must stay behavior-preserving: session headers, default source selection, max crawl/text limits, and retriable crawl errors should not drift during structure cleanup.
- Phase 2F batch handoff outputs must keep the shared `argus.research.batch.handoff.v1` schema aligned across MCP and script entrypoints, with project-relative artifact paths and script exit codes.
- Phase 2G single-workflow handoff outputs must expose `argus.research.workflow.handoff.v1`, compact readiness/error counts, and project-relative artifact paths without leaking the project root; unsaved workflows must not claim readiness.
- Phase 2H artifact review must validate project-local JSON paths, return compact quality scores/statuses, and avoid replaying saved page text through MCP.
- Phase 2I review handoff chaining must accept `research_workflow.data.handoff`, preserve project-relative paths, and emit `argus.research.review.handoff.v1` with batch-compatible quality fields.
- Phase 2J artifact smoke must execute the public zero-key workflow-to-review chain and require ready review status with matching workflow/review artifact paths.
- Explicit Openverse artifact smoke must validate saved JSON/Markdown license fields and notices plus matching workflow/review handoff counts and warnings without changing the default Wikipedia smoke.
- Phase 2K artifact review must accept batch handoff artifact lists, select only a valid indexed project-relative artifact, and reject missing or out-of-range selections.
- Phase 2L batch handoff smoke must execute two public saved workflows, select a batch artifact by index for review, and require matching batch/review handoff paths.
- Phase 3 optional runtime probe must distinguish installed packages from explicit runtime verification and sanitize Codex configuration or permission failures.
- Phase 3 runtime-probe smoke must return exit code 2 for recognized configuration/permission/install blocks and exit code 3 for unexpected runtime failures.
- Saved Codex smoke must require a ready review handoff whose artifact path matches the saved Codex workflow handoff.
- Resource discovery must preserve book access metadata, merge Project Gutenberg acquisition files, isolate partial academic-source failures, and rank exact paper titles before access-status tie-breakers.
- Project-local research paths must be checked after symlink resolution before reading, writing, or publishing handoff paths.
- Saved-artifact comparisons must reject empty/unknown source IDs, avoid replaying source text, and distinguish source-level traceability from fact verification.
- Locator replay must stay project-local, reject malformed source paths and stale coordinates, cap requests at 10 locators, and cap each excerpt at 240 characters plus 25 words.
- New comparisons must fingerprint only text prefixes actually sent to comparison; verified locator ranges must stay inside those prefixes, old artifacts remain explicitly unverified, mutations fail closed, and JSON booleans never count as integer coordinates.
- Optional CSL-JSON/RIS files must stay project-local, preserve unique CSL IDs, and appear as relative paths in comparison handoffs.
- Full comparison audits must inspect every unique locator used by claims, continue across source failures, preserve legacy unverified status, and never return source or excerpt text.

### Flow: MCP server import and tool registration

Related modules:
- `argus_server/server.py`
- `argus_server/tools/`

Tests to run:
- `uv run python -m unittest tests.test_mcp_registration`
- `uv run python -m unittest discover -s tests`

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
- `uv run python -m unittest tests.test_scheduler`
- Add notification mock tests separately before changing webhook behavior.

Known historical bugs:
- launchd requires capitalized `Hour`, `Minute`, `Day`, `Weekday`, and `Month` keys; lowercase keys can trigger at the wrong cadence.
- A launchd process may be unable to start a project and virtual environment under macOS-protected Desktop storage even when load and kickstart both return zero; distinguish task submission from completed runner execution.

## Bug Regression Tests

### Research toolkit safe gallery output

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Prevents `download_gallery` from accepting output directories outside the project root or option-like/non-HTTP targets.
- Requires gallery-dl execution to ignore user configuration, force the approved destination, separate options from the target, and return a failed envelope for nonzero exits.

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

### Research toolkit Codex source smoke runner

Test file:
- `tests/test_research_codex_smoke.py`

What it protects:
- Keeps the Phase 2B Codex smoke runner independent from commercial provider keys, distinguishes runtime unavailable exit code `2` from contract failure exit code `3`, and requires a URL-bearing topic result plus a successful workflow document before passing.

### Research toolkit public crawl quality smoke runner

Test file:
- `tests/test_research_crawl_quality_smoke.py`

What it protects:
- Keeps the Phase 2B public crawl quality runner repeatable by checking fixed public fixture contracts, page image discovery summaries, and a Wikipedia workflow success contract without provider keys or Codex SDK state.

### Research toolkit Openverse quality smoke runner

Test file:
- `tests/test_research_openverse_smoke.py`

What it protects:
- Keeps anonymous Openverse image search repeatable without downloading media, requires unique non-mature HTTP image/source URLs plus complete license metadata and notices, and distinguishes external unavailability exit code `2` from quality-contract failure exit code `3`.

### Research toolkit Openverse audio adapter

Test file:
- `tests/test_research_audio.py`

What it protects:
- Keeps `audio:openverse` metadata-only and bounded, filters mature or malformed candidates, dedupes preview URLs, omits waveform and alternate-file payloads, preserves license notices and anonymous rate limits, and returns stable invalid-query, timeout, rate-limit, and provider-response errors.
- Keeps `ResearchToolkitTools.research_audio` as a parameter-preserving wrapper and reports the no-key `audio:openverse` source as ready in toolkit health without implying media download.

### Research toolkit Openverse audio MCP smoke runner

Test file:
- `tests/test_research_audio_smoke.py`

What it protects:
- Keeps the real smoke on the registered `research_audio` FastMCP path, requires unique non-mature HTTP audio/source URLs plus license metadata, notices, rate-limit metadata, and verification markers, and rejects waveform, alternate-file, byte, transcript, or lyric fields.
- Distinguishes passing exit code `0`, external unavailability exit code `2`, and malformed nested/provider/MCP/quality contract failure exit code `3` without requesting media downloads or leaking tracebacks.

### Research toolkit saved artifact quality smoke runner

Test file:
- `tests/test_research_artifact_smoke.py`

What it protects:
- Keeps saved `research_workflow` artifacts useful for handoff by checking JSON parseability, Markdown brief structure, project-local paths, successful document evidence, and exit code behavior.
- When `image:openverse` is explicit, enforces the end-to-end saved license contract and workflow/review count-warning alignment while preserving the default Wikipedia path.

### Research toolkit saved artifact review report

Test file:
- `tests/test_research_artifact_review.py`

What it protects:
- Keeps local artifact review useful for batch handoff by summarizing quality status, scores, warnings, key source metadata, unreadable files, and Markdown report output without replaying full crawled page text.
- Keeps Openverse/page image counts, complete-license counts, and explicit verification/incomplete-metadata warnings visible in JSON and Markdown without downgrading otherwise reusable artifacts.

### Research toolkit batch workflow report

Test file:
- `tests/test_research_batch_workflow.py`
- `tests/test_research_toolkit.py`

What it protects:
- Keeps the one-command saved workflow loop reliable by loading query lists, running per-query saved workflows, collecting project-relative artifact paths, and generating a Markdown review report from the local artifact review pipeline.
- Keeps the MCP-facing batch workflow reliable by deduping queries, saving per-query JSON/Markdown artifacts, writing a project-local review report, and rejecting unsafe report paths.
- Keeps MCP and script batch workflow outputs aligned through the shared `handoff` block without replaying full crawled page text.
- Keeps aggregate Openverse/page/license counts and license-warning totals aligned across MCP runs, batch reports, and shared batch handoffs.

### Research toolkit topic image discovery

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Keeps `research_images` tied to topic search results, preserves source page context, dedupes repeated image URLs across pages, and reports source errors without failing the whole response.

### Research workflow Openverse image opt-in

Test file:
- `tests/test_research_toolkit.py`

What it protects:
- Keeps `image:openverse` opt-in additive for saved single and batch workflows, writes license and attribution metadata to JSON/Markdown artifacts, gives direct licensed candidates dedupe priority, and preserves page evidence plus a partial handoff when Openverse is rate-limited.
- Keeps workflow and review handoffs explicit about Openverse/page image counts, complete license metadata, and required manual verification without changing existing readiness rules.

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
- Keeps `summary.ready_capabilities` derived from the returned capability matrix instead of a separately maintained manual list.

### Research toolkit MCP registration surface

Test file:
- `tests/test_mcp_registration.py`

What it protects:
- Keeps all eighteen Research Toolkit tools registered on the FastMCP server, locks `research_audio` to `query` / `limit` / `timeout` and `research_video_metadata` to `url` / `timeout`, preserves normal and structured-error JSON responses, keeps retired `get_crossref_events` absent, and catches accidental changes to the expected 173-tool public surface.
- Starts the STDIO server from a non-project working directory with an explicit project root, discovers all 173 tools and 8 resources, calls both health entrypoints, and rejects an invalid transport before startup.

### Research toolkit yt-dlp metadata boundary

Test file:
- `tests/test_research_video.py`

What it protects:
- Keeps the subprocess command in simulate mode with config, cookies, cache, remote components, playlists, and watched-state updates disabled.
- Keeps output on an explicit metadata allowlist and proves nested format, download, thumbnail, and subtitle URLs are absent.
- Preserves structured missing-install, invalid-URL, timeout, extractor, parse, invalid-response, and unsupported-playlist errors.

### Research resource relevance and partial failure

Test file:
- `tests/test_research_resources.py`
- `tests/test_research_resource_relevance.py`

What it protects:
- Keeps book, paper, and course results in one access-aware schema without bypassing access controls.
- Preserves successful academic results when one source is rate-limited.
- Prevents downloadable but unrelated papers from outranking an exact requested title.

### Research resource read, summary, and artifact workflow

Test file:
- `tests/test_research_resource_workflow.py`

What it protects:
- Selects readable public PDF/HTML/TXT links before resource landing pages and normalizes Jina Reader output into the shared workflow document shape.
- Keeps verified-public access as the default boundary, rejects unverified links without explicit opt-in, and validates project-local output paths before network work.
- Preserves readable documents when Codex summary parsing fails, keeps runner/model attribution in the normalized summary payload, and avoids calling Codex after a read failure.
- Keeps Codex summaries in an ephemeral, deny-all, read-only thread with an empty temporary working directory and explicit untrusted-content instructions.
- Saves paired JSON/Markdown artifacts and emits the shared workflow handoff with project-relative paths.

### Research artifact canonical path boundary

Test file:
- `tests/test_research_path_safety.py`
- `tests/test_research_artifact_review.py`

What it protects:
- Rejects project-local lexical paths whose symlink-resolved targets escape the project root.
- Applies the same canonical boundary to artifact reads, output directories, report writes, and handoff paths.
- Preserves normal canonical project paths and standalone artifact script execution.

### Research saved-artifact comparison, integrity audit, citation exports, and locator replay

Test file:
- `tests/test_research_compare.py`

What it protects:
- Requires 2–6 unique project-local artifacts with readable evidence and caps Codex input per source and in total.
- Enforces known `S1...Sn` citations, requires cited evidence, rejects invalid output, and sanitizes runner failures.
- Keeps source text out of MCP output while preserving compact source metadata, Markdown/JSON artifacts, and comparison handoff readiness.
- Generates bounded artifact locators whose document/character coordinates reconstruct the saved source text, while treating page numbers as optional observed metadata.
- Requires claim locators to exist, belong to cited sources, and span at least two sources for agreement/difference claims.
- Preserves creators and available DOI/arXiv/ISBN metadata in deterministic BibTeX, CSL-JSON, and RIS without inventing unknown fields or journal status for unclassified preprints.
- Replays only requested project-local ranges, enforces request/excerpt bounds, preserves citation metadata, and returns structured errors for unknown locators, unsafe paths, malformed source paths, and stale coordinates.
- Fingerprints each selected document prefix, verifies it before excerpt replay, reports old artifacts as unverified, and rejects content mismatches or malformed fingerprint coordinates.
- Audits all unique locator references used by claims without text replay, aggregates verified/unverified/failed status across sources, and keeps unsafe paths out of returned issues.
- Saves optional project-local CSL-JSON/RIS files with unique CSL IDs and relative handoff paths only when report saving is enabled.

Additional test files:
- `tests/test_research_compare_sources.py`
- `tests/test_research_compare_locators.py`
- `tests/test_research_compare_exports.py`
- `tests/test_research_compare_audit.py`
- `tests/test_research_locator.py`

### BUG-0007: Malformed locator source path must stay in the error envelope

Test file:
- `tests/test_research_locator.py`

What it protects:
- Rejects non-string `artifact_path` values during comparison indexing before they reach filesystem path functions and raise an uncaught `TypeError`.

### BUG-0008: Boolean fingerprint indexes must not equal integer coordinates

Test file:
- `tests/test_research_locator.py`

What it protects:
- Requires fingerprint document indexes to be strict integers, preventing JSON `false` from matching document index `0` through Python numeric equality.

### BUG-0009: Locator ranges must stay inside fingerprint scope

Test file:
- `tests/test_research_locator.py`
- `tests/test_research_compare_audit.py`

What it protects:
- Prevents replay and full audit from accepting a tampered locator that points beyond the hashed comparison-input prefix while remaining inside the current full source document.

### xhs CLI auth status and friendly errors

Test file:
- `tests/test_cli_tools.py`
- `tests/test_social_ops.py`

What it protects:
- Keeps `xhs_auth_status` dependency-safe, ensures xhs cookie/auth failures return `AUTH_STORAGE_UNAVAILABLE` or `AUTH_REQUIRED`, and prevents `xhs_*` SocialOps tools from running business commands before auth is ready.

### BUG-0010: Cross-platform search contract and truthful status

Test file:
- `tests/test_cross_platform.py`

What it protects:
- Keeps Hacker News and all five social CLI search arguments aligned with their actual contracts.
- Preserves CLI error codes plus Reddit Atom rate-limit metadata at the source boundary.
- Requires all-failed and zero-result searches to return failed envelopes while useful mixed-source results remain available as partial.
- Propagates aggregate status and source counts through `narrative_tracking`.

### BUG-0012: Academic aggregate nested failure semantics

Test file:
- `tests/test_external_academic.py`

What it protects:
- Preserves exact arXiv, Semantic Scholar, OpenAlex, and PubMed call contracts and nested envelopes.
- Reports useful mixed-source results as partial with source and paper counts.
- Returns `ALL_SOURCES_FAILED` when every source fails and `NO_RESULTS` when no useful paper remains.
- Converts an unexpected source exception into its nested structured failure instead of escaping the aggregate.

### BUG-0013: AI aggregate nested failure semantics

Test file:
- `tests/test_ai_analytics.py`

What it protects:
- Reports complete and useful partial AI analysis outcomes with explicit step counts.
- Returns `ALL_STEPS_FAILED` when no requested analysis step succeeds while preserving every nested error.
- Contains unexpected child exceptions as `ANALYSIS_ERROR` instead of letting them escape the aggregate.
- Rejects unsupported modes without running deduplication or anomaly detection.

### BUG-0014: System health execution and readiness semantics

Test file:
- `tests/test_system_health.py`

What it protects:
- Keeps successful check execution separate from required business readiness.
- Requires missing configuration and news data to appear as blocking checks instead of disappearing.
- Requires a fresh SQLite file to contain at least one `news_items` record before news data is ready.
- Treats semantic index, RSSHub, social CLI auth verification, AI providers, and notifications as explicit optional degradation checks.
- Contains optional adapter exceptions inside their nested checks.
- Keeps `get_system_status` on the same authoritative readiness snapshot as `system_health` and `system://health`.
- Labels Web `/api/health` as liveness-only without removing its compatible `ok` field.

### Local configuration initialization

Test file:
- `tests/test_config_management.py`
- `tests/test_mcp_registration.py`

What it protects:
- Creates `config/config.yaml` only from a structurally valid project template and preserves the template bytes and comments.
- Never overwrites an existing valid or invalid config; repeated calls are idempotent and explicit about `created=false`.
- Returns structured errors for missing/invalid templates and invalid existing config without creating or replacing the target.
- Keeps the no-argument FastMCP contract registered and the public surface at 173 tools.

### BUG-0015: Crawl persistence response contract

Test file:
- `tests/test_system_crawl_persistence.py`

What it protects:
- Keeps SQLite persistence enabled for default no-argument scheduled crawls while treating `save_to_local` as the legacy switch for optional TXT/HTML snapshots.
- Reports database and snapshot outcomes independently for complete, partial, and failed combinations.
- Prevents missing snapshot files or database exceptions from being hidden behind contradictory compatibility fields or notes.
- Keeps the public FastMCP parameters and defaults unchanged while serializing the explicit persistence record.

### BUG-0016: Semantic rebuild SQLite thread lifecycle

Test file:
- `tests/test_semantic_search.py`

What it protects:
- Prevents semantic rebuild from borrowing the process-global storage manager inside a FastMCP worker thread.
- Requires local storage to resolve against the tool's project root rather than the process working directory.
- Requires same-thread cleanup after both successful date reads and contained read failures.

### BUG-0017 and BUG-0018: Local analytics summary truthfulness

Test file:
- `tests/test_analytics.py`

What it protects:
- Requires a one-day positive topic series to report its actual peak while keeping one-point change at zero.
- Prevents all-zero date ranges from inventing a peak date.
- Preserves normal percentage calculation for nonzero comparison baselines.
- Requires zero-baseline relative change to be explicitly unavailable while preserving the absolute difference.

### Scheduler workflow generation and runner control flow

Test file:
- `tests/test_scheduler.py`

What it protects:
- Generates a two-step crawl-then-index workflow and correctly cased launchd plist without notification steps.
- Rejects tools outside the scheduler whitelist before writing a task.
- Executes crawl before semantic rebuild and writes a successful last-run report.
- Stops before index rebuild when crawl returns a failed envelope.

### BUG-0019: Same-minute SQLite crawl idempotency

Test file:
- `tests/test_sqlite_crawl_idempotency.py`

What it protects:
- Preserves normal news updates across distinct crawl times.
- Makes sequential and two-connection concurrent news retries for one crawl time successful no-ops.
- Prevents duplicate rank history and crawl-count increments.
- Rolls back an invalid crawl claim so a later valid write can proceed.
- Applies the same crawl-time idempotency contract to RSS persistence.

### BUG-0020: arXiv cache, pacing, and rate-limit behavior

Test file:
- `tests/test_external_academic.py`

What it protects:
- Persists successful normalized arXiv responses and reuses them across adapter instances without network access.
- Rejects corrupt or expired cache entries and refreshes them from the source.
- Spaces a short 429 retry by three seconds and attempts it only once.
- Returns persistent or long-window limits as `RATE_LIMITED` without an unbounded sleep.
- Preserves the existing academic aggregate status and source-error contracts.
