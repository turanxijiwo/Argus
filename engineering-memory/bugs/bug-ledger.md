# Bug Ledger

Append one entry per meaningful bug. Keep entries short but structured.

## Entry Format

```md
## BUG-0001: Short Bug Title

Date: 2026-01-01
Severity: P0 / P1 / P2 / P3
Status: open / fixed / verified / superseded
Area:
Tags:

### Symptom
What failed?

### Reproduction / Trigger
How did it appear?

### Root Cause
What actually caused it?

### Affected Chain
Entry point → module → function → data/state/API → output.

### Fix
What changed?

### Tests Added / Updated
- Test file:
- Test case:

### Prevention
What rule or design adjustment prevents recurrence?

### Related Files
- `path/to/file`

### Follow-up
Any tech debt or architecture task created?
```

## Bugs

## BUG-0001: Web Answer Crowded Out Page Candidate

Date: 2026-07-07
Severity: P1
Status: verified
Area: Research Toolkit
Tags: source-normalization, workflow, web-search

### Symptom
`research_images`, `research_pack`, and `research_workflow` could return success with zero pages/documents when called with `sources=["web:<provider>"]` and `limit=1`, even though the web provider returned a real URL result.

### Reproduction / Trigger
A web search adapter response containing both an answer summary with no URL and one URL result caused `research_topic.merged` to keep only the answer at `limit=1`.

### Root Cause
`normalize_web_search` intentionally emitted the answer summary first with a high score, while downstream page workflows built candidates only from the truncated `research_topic.merged` list instead of also checking source raw items.

### Affected Chain
`research_topic` -> `normalize_web_search` -> truncated `merged` -> `page_candidates` -> `research_images` / `research_pack` / `research_workflow`.

### Fix
Added a source-aware candidate pool that starts with merged results and then appends successful source raw items before URL filtering and dedupe.

### Tests Added / Updated
- Test file: `tests/test_research_toolkit.py`
- Test cases: `test_research_images_uses_web_result_when_answer_has_no_url_at_limit_one`, `test_research_pack_uses_web_result_when_answer_has_no_url_at_limit_one`, `test_research_workflow_uses_web_result_when_answer_has_no_url_at_limit_one`

### Prevention
When a downstream flow requires URL-bearing pages, build candidates from the full successful source item set, not only from display-oriented merged results.

### Related Files
- `argus_server/tools/research_sources.py`
- `argus_server/tools/research_toolkit.py`
- `tests/test_research_toolkit.py`

### Follow-up
None.

## BUG-0002: Open PDF Availability Outranked Exact Paper Title

Date: 2026-07-11
Severity: P1
Status: verified
Area: Research Resource Discovery
Tags: ranking, academic-search, partial-failure

### Symptom
An exact search for `Attention Is All You Need` returned unrelated recent arXiv papers ahead of the requested paper when Semantic Scholar was rate-limited.

### Reproduction / Trigger
The real `find_research_resource(..., resource_type="paper", access="open")` smoke returned three downloadable PDFs, but none was the requested title.

### Root Cause
The arXiv adapter used its default submitted-date ordering with a broad raw query, while the unified layer ranked only by access status. Once all candidates were downloadable, source order decided the result.

### Affected Chain
`find_research_resource` -> `_search_papers` -> `search_arxiv` -> normalized resources -> access-only sort -> truncated response.

### Fix
The paper path now sends an arXiv title query with relevance sorting, and the shared resource ranker scores normalized titles against the user query before applying access as a tie-breaker.

### Tests Added / Updated
- Test file: `tests/test_research_resource_relevance.py`
- Test case: `test_exact_paper_title_is_ranked_first_and_sent_as_title_query`

### Prevention
Resource discovery must rank query relevance before convenience attributes such as download availability, while preserving access filters as explicit user intent.

### Related Files
- `argus_server/tools/research_resources.py`
- `argus_server/tools/research_resource_normalize.py`
- `tests/test_research_resource_relevance.py`

### Follow-up
None.

## BUG-0003: Codex Summary Attribution Stored In Envelope Statistics

Date: 2026-07-11
Severity: P2
Status: verified
Area: Research Resource Workflow
Tags: response-envelope, codex, summary

### Symptom
The resource workflow returned valid summary text but omitted the injected runner or real Codex model attribution from `data.summary`.

### Reproduction / Trigger
The successful PDF workflow test expected `data.summary.runner == "injected"` and raised `KeyError` even though summary generation succeeded.

### Root Cause
`normalize_codex_summary_payload` returns envelope statistics under top-level `summary` and the normalized content under `data`. The attribution code confused those layers and wrote `runner`/`model` into the envelope statistics.

### Affected Chain
`research_resource_workflow` -> `run_codex_summary` -> `normalize_codex_summary_payload` -> workflow `summary` payload.

### Fix
Both injected-runner and real-SDK paths now write `runner` and `model` into the normalized `data` payload.

### Tests Added / Updated
- Test file: `tests/test_research_resource_workflow.py`
- Test case: `test_reads_public_pdf_and_generates_codex_summary`

### Prevention
When a helper returns the standard Argus envelope, inspect and test the distinction between top-level operational statistics and the normalized `data` contract before adding metadata.

### Related Files
- `argus_server/tools/research_codex_summary.py`
- `tests/test_research_resource_workflow.py`

### Follow-up
None.

## BUG-0004: Research Artifact Paths Allowed Symlink Escapes

Date: 2026-07-11
Severity: P1
Status: verified
Area: Research Toolkit artifact safety
Tags: path-validation, symlink, artifact, handoff

### Symptom
A path that appeared to be inside the project could read or write outside it when an intermediate project directory was a symlink to an external directory.

### Reproduction / Trigger
A temporary project containing `linked -> external-directory` allowed `review_research_artifact("linked/artifact.json")` to read the external JSON and allowed `resolve_output_dir(..., "linked/output")` to approve an external write target.

### Root Cause
Research path guards compared lexical `abspath` values with `commonpath` but did not canonicalize symlinks with `realpath` before enforcing the project-root boundary.

### Affected Chain
Artifact review / workflow save / batch report / handoff path / artifact smoke scripts -> lexical containment helper -> file read, write, or published relative path.

### Fix
Added one canonical project-path resolver for server modules, applied it to artifact reads, output directories, batch reports, and handoffs, and updated standalone script helpers to perform the same `realpath` containment check without losing direct script execution.

### Tests Added / Updated
- Test file: `tests/test_research_path_safety.py`
- Test cases: symlink output rejection, artifact read rejection, handoff suppression, and normal canonical path acceptance
- Test file: `tests/test_research_artifact_review.py`
- Test case: `test_write_report_rejects_symlink_escape`

### Prevention
Any project-local read or write boundary must compare canonical root and target paths after symlink resolution; lexical path normalization alone is insufficient.

### Related Files
- `argus_server/tools/research_io.py`
- `argus_server/tools/research_review.py`
- `argus_server/tools/research_handoff.py`
- `argus_server/tools/research_batch.py`
- `scripts/research_artifact_review.py`
- `scripts/research_artifact_smoke.py`
- `scripts/research_batch_workflow.py`

### Follow-up
None.

## BUG-0005: Research Health Ready Count Drifted From Capability Matrix

Date: 2026-07-11
Severity: P2
Status: verified
Area: Research Toolkit health
Tags: derived-state, capability-matrix, health

### Symptom
`research_toolkit_health` reported 13 ready capabilities while 15 returned capability entries had `can_use_now == true`.

### Reproduction / Trigger
Comparing `summary.ready_capabilities` with a count over `data.capabilities.values()` exposed a difference of two after resource discovery and resource workflow capabilities were added.

### Root Cause
The summary count used a separately maintained tuple of booleans that omitted two capability entries, so the derived value drifted as the public matrix grew.

### Affected Chain
`research_toolkit_health` -> capability matrix construction -> manual ready tuple -> summary count.

### Fix
The ready count is now computed directly from the returned capability dictionary.

### Tests Added / Updated
- Test file: `tests/test_research_toolkit.py`
- Test case: `test_toolkit_health_reports_missing_optional_capabilities`

### Prevention
Derived health metrics must be calculated from their owning capability records, not from a duplicate manually ordered list.

### Related Files
- `argus_server/tools/research_health.py`
- `tests/test_research_toolkit.py`

### Follow-up
None.

## BUG-0006: Locator Validation Masked Invalid Citation Error

Date: 2026-07-11
Severity: P2
Status: verified
Area: Research comparison contract
Tags: error-precedence, citation, locator, compatibility

### Symptom
An unknown source citation that previously returned `INVALID_CITATIONS` was reclassified as `INVALID_EVIDENCE_LOCATORS` after locator validation was added.

### Reproduction / Trigger
`test_rejects_unknown_citations` changed an agreement citation from `S2` to unknown `S9`; the remaining `S2:L1` locator then also produced a derived source-mismatch issue, and the locator error code won.

### Root Cause
The error selector chose the locator code when any locator issue existed, even when that locator issue was downstream of a primary missing or unknown citation violation.

### Affected Chain
Codex comparison payload -> claim citation normalization -> locator-source validation -> aggregate error-code selection.

### Fix
`INVALID_EVIDENCE_LOCATORS` is now used only when every validation issue is locator-specific; citation, statement, and shape violations retain the existing `INVALID_CITATIONS` contract.

### Tests Added / Updated
- Test file: `tests/test_research_compare.py`
- Test case: `test_rejects_unknown_citations`
- Test file: `tests/test_research_compare_locators.py`
- Test cases: unknown locator, source mismatch, and insufficient cross-source locator coverage

### Prevention
Primary contract violations must take precedence over dependent validation errors when preserving public error-code compatibility.

### Related Files
- `argus_server/tools/research_compare_contract.py`
- `tests/test_research_compare.py`
- `tests/test_research_compare_locators.py`

### Follow-up
None.

## BUG-0007: Malformed Locator Source Path Escaped Error Envelope

Date: 2026-07-11
Severity: P2
Status: verified
Area: Research locator resolver
Tags: path-validation, type-safety, error-envelope

### Symptom
A comparison source whose non-empty `artifact_path` was a JSON list caused `research_resolve_locators` to raise `TypeError` instead of returning an Argus error envelope.

### Reproduction / Trigger
A project-local comparison artifact with `artifact_path: ["source.json"]` passed the presence check and reached `os.path.isabs` through `resolve_project_path`.

### Root Cause
The new comparison index validated path truthiness but not its string type before handing nested artifact metadata to the shared filesystem boundary.

### Affected Chain
`research_resolve_locators` -> comparison source index -> source artifact load -> `resolve_project_path` -> uncaught `TypeError`.

### Fix
Comparison indexing now requires canonical `S1...Sn` source IDs and non-empty string artifact paths before any filesystem call.

### Tests Added / Updated
- Test file: `tests/test_research_locator.py`
- Test case: `test_rejects_non_string_source_artifact_path`

### Prevention
Nested JSON path metadata must be type-validated before reuse by helpers whose public callers are normally type-checked.

### Related Files
- `argus_server/tools/research_locator.py`
- `tests/test_research_locator.py`

### Follow-up
None.

## BUG-0008: Boolean Fingerprint Index Matched Document Zero

Date: 2026-07-11
Severity: P2
Status: verified
Area: Research comparison content integrity
Tags: json-types, fingerprint, validation

### Symptom
A fingerprint document entry with JSON `false` as `document_index` was accepted as the fingerprint for document `0`.

### Reproduction / Trigger
The regression test replaced a generated fingerprint's integer index with `False`; locator replay returned success instead of `INVALID_CONTENT_FINGERPRINT`.

### Root Cause
Fingerprint selection compared values with `==` before strict type validation. In Python, `bool` is an `int` subclass and `False == 0`.

### Affected Chain
Saved comparison fingerprint -> `verify_document_fingerprint` document selection -> locator integrity result.

### Fix
Fingerprint document selection now requires `_is_int(document_index)` before comparing it with the requested document index.

### Tests Added / Updated
- Test file: `tests/test_research_locator.py`
- Test case: `test_rejects_boolean_fingerprint_document_index`

### Prevention
JSON numeric coordinates must use strict integer validation that explicitly excludes booleans before equality or range checks.

### Related Files
- `argus_server/tools/research_integrity.py`
- `tests/test_research_locator.py`

### Follow-up
None.

## BUG-0009: Locator Escaped Fingerprinted Comparison Prefix

Date: 2026-07-11
Severity: P1
Status: verified
Area: Research comparison content integrity
Tags: fingerprint-scope, locator, evidence-boundary

### Symptom
A tampered locator could point beyond the text prefix used and fingerprinted for comparison while still being accepted as verified and replayable from the longer current source document.

### Reproduction / Trigger
A source fingerprint covered characters `0:13`, while a locator referenced characters `14:31` in the same document. The source prefix hash matched, and both locator validation and the full comparison audit returned verified.

### Root Cause
Fingerprint verification returned the covered `text_chars`, but locator validation checked coordinates only against the full current source length and never constrained `end_char` to the verified fingerprint scope.

### Affected Chain
Saved comparison locator -> shared locator evidence validation -> bounded replay and full no-text comparison audit.

### Fix
The shared locator validator now rejects verified locator ranges whose `end_char` exceeds the fingerprint's `text_chars`, returning `STALE_LOCATOR` with `outside_fingerprint_scope`. Legacy artifacts without fingerprints remain explicitly unverified and compatible.

### Tests Added / Updated
- Test file: `tests/test_research_locator.py`
- Test case: `test_rejects_locator_outside_fingerprinted_prefix`
- Test file: `tests/test_research_compare_audit.py`
- Test case: `test_reports_locator_outside_fingerprinted_prefix`

### Prevention
Coordinate validation must use the same bounded text domain as the integrity proof; validating against a larger current document can authorize content the fingerprint never covered.

### Related Files
- `argus_server/tools/research_integrity.py`
- `argus_server/tools/research_locator_evidence.py`
- `argus_server/tools/research_locator.py`
- `argus_server/tools/research_compare_audit.py`

### Follow-up
None.

## BUG-0010: Cross-Platform Search Reported Success Without Useful Results

Date: 2026-07-14
Severity: P0
Status: verified
Area: Cross-platform aggregation
Tags: source-contract, status-envelope, cli, rate-limit

### Symptom
`universal_search("OpenAI")` returned `success=true` with no merged items while multiple default sources had actually failed. `narrative_tracking` reused the same result and therefore also presented unusable collection as success.

### Reproduction / Trigger
The default call sent an unsupported Hacker News keyword, reused a generic `--limit` option across incompatible social CLIs, received blocked Reddit JSON responses, and then unconditionally wrapped the empty aggregate with `_ok`.

### Root Cause
Heterogeneous source contracts were treated as interchangeable, and the aggregate response encoded execution completion rather than whether any useful result existed. Source-specific error codes and rate-limit diagnostics were also discarded by CLI branches.

### Affected Chain
FastMCP or scheduler call -> `CrossPlatformTools.universal_search` -> `_fetch_source` adapters -> normalized aggregate -> `narrative_tracking`.

### Fix
Each adapter now uses its actual query arguments; Hacker News normalization accepts Algolia fields; Reddit uses anonymous Atom RSS with dynamic rate metadata; CLI error codes are preserved; and aggregate results distinguish complete, partial, empty, and failed states.

### Tests Added / Updated
- Test file: `tests/test_cross_platform.py`
- Coverage: HN arguments/normalization, five CLI contracts and error envelopes, Reddit success/rate limiting, all-failed/empty/partial aggregates, and narrative status propagation.

### Prevention
Adapter orchestration must validate each source's real contract and derive top-level success from useful business output, while retaining source-scoped failures for partial results.

### Related Files
- `argus_server/tools/cross_platform.py`
- `argus_server/server.py`
- `tests/test_cross_platform.py`
- `docs/TOOL_AVAILABILITY_AUDIT.md`

### Follow-up
Apply the same nested-failure audit separately to aggregate AI and academic tools.

## BUG-0011: Retired Crossref Event Data Remained Publicly Registered

Date: 2026-07-14
Severity: P0
Status: verified
Area: External API and FastMCP surface
Tags: upstream-sunset, registration, inventory, error-classification

### Symptom
`get_crossref_events` remained discoverable as a public MCP tool even though every call targeted a permanently retired API and returned a misleading `NETWORK_ERROR`.

### Reproduction / Trigger
A real `source="wikipedia", rows=1` call failed after 7.7 seconds with an SSL EOF from `api.eventdata.crossref.org`. Crossref's official documentation states that the Event Data public API was sunset on 2026-04-23.

### Root Cause
The public tool registry and inventory had no lifecycle reconciliation for upstream services. A permanent provider shutdown was therefore left behind as an apparently retryable network adapter.

### Affected Chain
FastMCP registration -> `get_crossref_events` -> `ExternalAPITools.get_crossref_events` -> retired Crossref Event Data endpoint.

### Fix
Removed the FastMCP registration, dead adapter method, endpoint reference, and CLI listing; updated current tool inventories from 173 to 172 and external API inventories from 54 to 53 while preserving the historical audit result.

### Tests Added / Updated
- Test file: `tests/test_mcp_registration.py`
- Test case: `test_retired_crossref_events_tool_is_not_registered`

### Prevention
Permanent upstream shutdowns must be represented by removing or explicitly disabling the public capability, not by retaining a tool that reports generic network failure.

### Related Files
- `argus_server/server.py`
- `argus_server/tools/external_apis.py`
- `tests/test_mcp_registration.py`
- `docs/TOOL_AVAILABILITY_AUDIT.md`

### Follow-up
Evaluate Crossref beta Data Citations only as a separate dataset-citation capability; it is not a replacement for social and web mentions.

## BUG-0012: Academic Aggregate Hid Failed Sources Behind Success

Date: 2026-07-14
Severity: P0
Status: verified
Area: External academic API aggregation
Tags: partial-failure, status-envelope, academic-search, rate-limit

### Symptom
`search_all_academic("OpenAI", per_source=1)` returned `success=true` and three papers while Semantic Scholar returned `RATE_LIMITED`; the top level exposed neither partial status nor failed-source counts.

### Reproduction / Trigger
A real four-source call succeeded for arXiv, OpenAlex, and PubMed but failed for Semantic Scholar. The aggregator counted only successful source items and unconditionally returned `_ok`.

### Root Cause
The fan-out treated orchestration completion as complete business success and did not derive aggregate status from nested source envelopes or useful paper output. This is another occurrence of RC-0010.

### Affected Chain
FastMCP `search_all_academic` -> `ExternalAPITools.search_all_academic` -> arXiv / Semantic Scholar / OpenAlex / PubMed envelopes.

### Fix
Preserved all nested source envelopes, added per-source paper counts and complete/partial/empty/failed summaries, kept useful partial results successful, and returned structured failures for all-source failure or zero useful papers.

### Tests Added / Updated
- Test file: `tests/test_external_academic.py`
- Coverage: complete, partial, exception/all-failed, all-empty, and partial-without-results paths.

### Prevention
Multi-source search success must be derived from useful output plus nested source state, never from fan-out completion alone.

### Related Files
- `argus_server/tools/external_apis.py`
- `argus_server/server.py`
- `tests/test_external_academic.py`
- `docs/TOOL_AVAILABILITY_AUDIT.md`

### Follow-up
Fix `analyze_with_ai` separately; it is a different module and call chain with the same known status risk.

## BUG-0013: AI Aggregate Hid Failed Analysis Steps Behind Success

Date: 2026-07-14
Severity: P0
Status: verified
Area: AI analysis aggregation
Tags: partial-failure, status-envelope, exception-boundary, scheduler

### Symptom
`analyze_with_ai(mode="full")` returned `success=true` even when semantic deduplication returned `AUTH_REQUIRED` and anomaly detection returned `NO_LOCAL_DATA`. Unsupported modes also returned successful empty envelopes.

### Reproduction / Trigger
A real no-key, no-history call returned both nested failures under a successful top-level envelope. A forced anomaly exception escaped the aggregate instead of becoming a nested error.

### Root Cause
The method treated invocation completion as business success, unconditionally returned `_ok`, and neither validated the mode nor contained child-step exceptions. This is the third occurrence of RC-0010's aggregate-status failure pattern.

### Affected Chain
FastMCP and scheduler -> `AIAnalyticsTools.analyze_with_ai` -> `semantic_deduplicate` / `detect_anomaly` envelopes.

### Fix
Validated modes, contained step exceptions, preserved nested envelopes, added step counts and complete/partial/failed status, and returned `ALL_STEPS_FAILED` when no analysis step succeeded.

### Tests Added / Updated
- Test file: `tests/test_ai_analytics.py`
- Coverage: complete, partial, exception/all-failed, single-step failure, single-step success, and invalid-mode paths.

### Prevention
Multi-step tools must derive their top-level status from nested step outcomes and must contain unexpected child exceptions at the step boundary.

### Related Files
- `argus_server/tools/ai_analytics.py`
- `argus_server/server.py`
- `tests/test_ai_analytics.py`
- `docs/TOOL_AVAILABILITY_AUDIT.md`

### Follow-up
Health-check readiness semantics were completed in BUG-0014. Split the oversized AI analytics module only in a dedicated architecture task recorded as DEBT-0006.

## BUG-0014: Health Entrypoints Confused Liveness, Execution, And Readiness

Date: 2026-07-14
Severity: P0
Status: verified
Area: System health and readiness
Tags: health-contract, readiness, liveness, missing-checks, dependency-status

### Symptom
`get_system_status` always returned `health="healthy"` with no news data, while `system_health` returned a successful envelope with `ok=false` because optional RSSHub and semantic-index checks failed. Missing configuration and a missing news directory were not represented consistently, and Web `/api/health` exposed only an ambiguous `ok=true`.

### Reproduction / Trigger
A real FastMCP probe returned `get_system_status.health="healthy"` and no latest record, while `system_health` omitted `news_data`, reported only four checks, and returned `summary.ok=false`. The Web endpoint simultaneously returned only liveness `ok=true`.

### Root Cause
Each entrypoint defined health independently without an explicit contract. One path hard-coded healthy, another reduced present checks into one boolean while omitting absent paths, and the Web path did not identify itself as liveness-only.

### Affected Chain
FastMCP `get_system_status` / `system_health` and `system://health`, Feishu status display, plus Web `/api/health` liveness.

### Fix
Made `HealthTools.system_health` the authoritative readiness snapshot, injected it into `SystemManagementTools`, added required/optional checks for configuration, data, index, RSSHub, disk, social CLIs, AI providers, notifications, tasks, and alerts, and labeled Web health as liveness-only.

### Tests Added / Updated
- Test file: `tests/test_system_health.py`
- Coverage: missing required setup, empty-news databases, optional degradation, child-check exception containment, shared system status readiness, and Web liveness scope.

### Prevention
Health APIs must reserve `success` for check execution, expose explicit readiness, classify nested checks as required or optional, and derive summaries from those records.

### Related Files
- `argus_server/tools/telemetry.py`
- `argus_server/tools/system.py`
- `argus_server/server.py`
- `argus/web/app.py`
- `tests/test_system_health.py`
- `docs/TOOL_AVAILABILITY_AUDIT.md`

### Follow-up
Implement the P1 configuration initialization workflow separately. Split telemetry and readiness collection only in the dedicated task recorded as DEBT-0007.

## BUG-0015: Crawl Persistence Layers Shared One Misleading Success Flag

Date: 2026-07-14
Severity: P1
Status: verified
Area: Crawl persistence and FastMCP response contract
Tags: persistence, sqlite, snapshots, response-contract, scheduler

### Symptom
With `save_to_local=False`, SQLite was successfully written while `summary.saved_to_local` was false. With snapshots requested, both TXT and HTML could be missing while the response claimed the output folder had been saved.

### Reproduction / Trigger
A fake storage backend returning true from `save_news_data` reproduced the database-write/false-summary contradiction. Returning no TXT or HTML paths reproduced `saved_files={}` together with a successful output-folder note.

### Root Cause
`_persist_crawl_data` collapsed the required SQLite write and optional TXT/HTML snapshots into one `save_success` boolean. `_build_crawl_response` then combined that value with `save_to_local`, even though the parameter only gated snapshots.

### Affected Chain
FastMCP or scheduler `trigger_crawl` -> `SystemManagementTools.trigger_crawl` -> `LocalStorageBackend` SQLite and snapshot methods -> crawl response.

### Fix
Preserved the public signature and default SQLite write, split database and snapshot outcomes into explicit persistence records, derived complete/partial/failed state from both layers, and made compatibility fields, files, errors, and notes agree.

### Tests Added / Updated
- Test file: `tests/test_system_crawl_persistence.py`
- Coverage: database-only default, complete snapshots, partial snapshots, database exception with successful snapshots, and unchanged FastMCP parameters/serialization.

### Prevention
Multi-layer persistence must report each layer independently; a request flag for optional artifacts must not be used to infer whether required storage succeeded.

### Related Files
- `argus_server/tools/system.py`
- `argus_server/server.py`
- `tests/test_system_crawl_persistence.py`
- `docs/TOOL_AVAILABILITY_AUDIT.md`

### Follow-up
Run the first controlled persistent crawl only after explicit project configuration initialization; no broader storage refactor is required for this fix.

## BUG-0016: Semantic Rebuild Closed A Worker SQLite Connection From The Main Thread

Date: 2026-07-14
Severity: P1
Status: verified
Area: Semantic search and SQLite lifecycle
Tags: sqlite, thread-lifecycle, storage-manager, semantic-index, fastmcp

### Symptom
`semantic_index_rebuild` returned a valid 255-document index, then process shutdown logged that the SQLite connection was created in one thread and closed from another.

### Reproduction / Trigger
A real FastMCP rebuild ran through `asyncio.to_thread`, created the local connection in that worker, and left the process-global manager for main-thread destruction. The first run consistently emitted the SQLite thread-affinity error after its success response.

### Root Cause
`SemanticSearchTools.rebuild` used the process-global `get_storage_manager()` for an operation-scoped read and never cleaned it up in the worker. It also relied on the current working directory instead of its resolved project root.

### Affected Chain
FastMCP `semantic_index_rebuild` -> `asyncio.to_thread` -> `SemanticSearchTools.rebuild` -> global `StorageManager` -> local SQLite connection -> main-thread destructor.

### Fix
Constructed a project-bound local `StorageManager` for each rebuild, disabled irrelevant snapshot capabilities, and closed it in a `finally` block immediately after date reads in the same worker thread.

### Tests Added / Updated
- Test file: `tests/test_semantic_search.py`
- Coverage: successful rebuild and failed date read both reject the global singleton and require same-thread cleanup.

### Prevention
Worker-thread operations that open SQLite must own and close operation-scoped connections in the same thread; do not disable SQLite thread checks to hide lifecycle errors.

### Related Files
- `argus_server/tools/semantic_search.py`
- `tests/test_semantic_search.py`
- `docs/TOOL_AVAILABILITY_AUDIT.md`

### Follow-up
Audit the separate FastMCP tools recorded in DEBT-0009 with runtime evidence before changing their storage lifecycle.

## BUG-0017: Single-Day Trend Hid Its Real Peak

Date: 2026-07-14
Severity: P1
Status: verified
Area: Local trend analytics
Tags: summary-consistency, peak, single-day, fastmcp

### Symptom
A real one-day `analyze_topic_trend` call returned 10 total mentions but `peak_count=0` and `peak_time=null`.

### Reproduction / Trigger
The 2026-07-14 AI dataset reproduced the contradiction through FastMCP; a focused one-day parser fixture failed on the old implementation.

### Root Cause
Peak calculation was nested under the two-or-more-points condition required only by change-rate calculation, so every single-point series was assigned an artificial zero peak.

### Affected Chain
FastMCP `analyze_topic_trend` -> `AnalyticsTools.analyze_topic_trend_unified` -> `get_topic_trend_analysis` -> summary metrics.

### Fix
Calculated the peak independently whenever a positive count exists, retained zero change for one point, and kept `peak_time=null` for all-zero ranges.

### Tests Added / Updated
- Test file: `tests/test_analytics.py`
- Coverage: one-day positive peak and multi-day all-zero range.

### Prevention
Do not share an eligibility gate between metrics with different minimum-data requirements.

## BUG-0018: Zero Comparison Baseline Was Reported As No Growth

Date: 2026-07-14
Severity: P1
Status: verified
Area: Local period comparison
Tags: summary-consistency, percentage, zero-baseline, fastmcp

### Symptom
Comparing an empty prior day with 255 current records returned an absolute change of 255 but `count_change_percent="+0.0%"`.

### Reproduction / Trigger
A real FastMCP comparison between 2026-07-13 and 2026-07-14 reproduced the misleading percentage; the focused zero-baseline helper regression failed before the fix.

### Root Cause
The divide-by-zero fallback collapsed an undefined relative percentage into numeric zero and formatted it as a valid measured change.

### Affected Chain
FastMCP `compare_periods` -> `AnalyticsTools.compare_periods` -> `_compare_overview` -> overview metrics.

### Fix
Preserved normal percentage calculation for nonzero baselines and returned `N/A` when the baseline is zero while retaining the absolute change.

### Tests Added / Updated
- Test file: `tests/test_analytics.py`
- Coverage: nonzero baseline percentage and zero-baseline unavailable percentage.

### Prevention
Represent mathematically undefined ratios explicitly instead of converting them into valid-looking zero values.

## BUG-0019: Same-Minute Crawl Retries Mutated SQLite Twice

Date: 2026-07-14
Severity: P1
Status: verified
Area: SQLite crawl persistence
Tags: sqlite, concurrency, idempotency, crawl-history, rss

### Symptom
Two temporary Codex automation runs completed in the same minute. `crawl_records` retained one `17-58` row, but `rank_history` contained 612 rows for only 306 unique news items and affected news `crawl_count` values were incremented twice.

### Reproduction / Trigger
A minute-level acceptance automation created two independent FastMCP runs. Both called `trigger_crawl` with the same `crawl_time`; direct SQLite checks found 306 duplicate groups with exactly two identical ranks and no rank conflicts.

### Root Cause
News and RSS storage mutated item state before writing their unique crawl record. The final `INSERT OR REPLACE` collapsed the visible crawl record but could not undo duplicate history rows or counters already written by concurrent workers.

### Affected Chain
Codex automation or repeated scheduler call -> FastMCP `trigger_crawl` -> local/remote storage backend -> `SQLiteStorageMixin` news or RSS save -> item/history mutation -> late crawl-record replacement.

### Fix
Claim the unique crawl-time slot before any item mutation, return a successful no-op when another writer already owns it, update the claimed record after processing, and roll back failed transactions. The same contract now protects news and RSS storage.

### Tests Added / Updated
- Test file: `tests/test_sqlite_crawl_idempotency.py`
- Coverage: distinct crawl times, sequential same-minute retry, two-connection concurrent retry, failed-claim rollback, and RSS retry idempotency.

### Data Repair
Backed up the affected database, removed 306 exact duplicate `17-58` rank rows, corrected 255 extra item counters, retained 359 news rows, and verified zero duplicate groups plus `PRAGMA integrity_check=ok`.

### Prevention
Use an existing unique operation key as an atomic claim before side effects; never rely on a final replace/upsert to make earlier mutations idempotent.

## BUG-0020: arXiv Requests Ignored The Source's Cache And Pacing Contract

Date: 2026-07-14
Severity: P1
Status: verified
Area: External academic API
Tags: arxiv, cache, rate-limit, retry, fastmcp

### Symptom
The initial real availability audit received HTTP 429 from both concurrent and serial arXiv calls. The adapter retried no requests, cached no successful response, and converted every HTTP failure into `NETWORK_ERROR`.

### Reproduction / Trigger
The old adapter called the official Atom endpoint for every invocation. A later real title query succeeded, proving intermittent rather than permanent failure, while source review confirmed there was still no cache, request spacing, or 429 branch.

### Root Cause
The adapter treated a rate-limited public metadata service like an unrestricted stateless endpoint. It did not implement arXiv's documented guidance to wait three seconds between repeated calls and cache identical query results for a day.

### Affected Chain
FastMCP `search_arxiv`, `search_all_academic`, or `find_research_resource` -> `ExternalAPITools.search_arxiv` -> official Atom API.

### Fix
Added a validated 24-hour project-local response cache keyed by normalized request parameters, per-instance serialized three-second request pacing, one retry for short or unspecified 429 windows, non-blocking handling for long windows, and explicit `RATE_LIMITED` metadata for persistent limits.

### Tests Added / Updated
- Test file: `tests/test_external_academic.py`
- Coverage: cross-instance cache reuse, corrupt and expired cache fallback, successful paced retry, persistent rate limiting, and long retry windows without blocking.

### Real Verification
The official title query returned `Attention Is All You Need` and stored one cache entry. A fresh process whose network method was forced to raise returned the same paper from disk, and the registered FastMCP tool independently reported a cache hit.

### Prevention
Implement documented source pacing and cache semantics at the adapter boundary, and preserve rate-limit responses as source availability diagnostics rather than generic network failures.

## BUG-0021: Quick Start Documented An Unsupported Crawl Flag

Date: 2026-07-14
Severity: P2
Status: verified
Area: CLI and MCP onboarding
Tags: cli, documentation, mcp, cross-project, regression

### Symptom
Both quick-start READMEs instructed users to run `.venv/bin/argus --now`, but the installed CLI rejected that flag with exit code 2.

### Reproduction / Trigger
Running the documented command produced `argus: error: unrecognized arguments: --now`. Reading the parser confirmed that a one-off crawl is the no-argument command, and a repository-wide search found the stale flag only in `README.md` and `README-EN.md`.

### Root Cause
The onboarding examples drifted from the argparse entrypoint and were not covered by a process-level CLI/MCP acceptance check.

### Affected Chain
README quick start -> installed `argus` console script -> `argus.__main__.main` argument parsing.

### Fix
Replaced the unsupported flag with the real no-argument crawl command, documented a cross-project MCP command with an explicit project root, and synchronized the English MCP inventory.

### Tests Added / Updated
- Test file: `tests/test_mcp_registration.py`
- Coverage: STDIO initialization from a non-project working directory, 173-tool/8-resource discovery, both health tool calls, and invalid transport rejection.

### Real Verification
A generic FastMCP client started Argus outside the repository, listed 173 tools and 8 resources, and called `system_health`. An independent ephemeral `codex exec` run then recorded successful `research_toolkit_health` and `system_health` MCP calls from `/private/tmp`.

### Prevention
Keep documented entrypoint examples aligned with real CLI help and retain a process-level STDIO acceptance test that starts outside the repository.

## BUG-0022: Gallery Wrapper Did Not Enforce Its Output Boundary

Date: 2026-07-14
Severity: P1
Status: verified
Area: Research media download adapter
Tags: gallery-dl, subprocess, config-isolation, output-boundary, error-envelope

### Symptom
`download_gallery(confirm=True)` accepted option-like targets, loaded the user's default gallery-dl configuration, and returned `success=true` when gallery-dl exited nonzero.

### Reproduction / Trigger
The old dry-run accepted `target="--config-create"`; a mocked gallery-dl exit with return code 2 was wrapped as successful. Repository scanning found only the gallery and video research adapters start subprocesses, and the video adapter already validates HTTP URLs and ignores user configuration.

### Root Cause
The wrapper treated a project-local working directory as a complete process boundary. It did not validate the target contract, isolate external configuration, force the destination in argv, terminate option parsing, or map process status to the Argus envelope.

### Affected Chain
FastMCP `download_gallery` -> `ResearchToolkitTools.download_gallery` -> `research_gallery.download_gallery` -> gallery-dl subprocess.

### Fix
Restricted targets to HTTP/HTTPS URLs, added `--config-ignore`, forced `--directory` to the resolved project-local path, inserted `--` before the target, and converted nonzero exits into `DOWNLOAD_FAILED` responses.

### Tests Added / Updated
- Test file: `tests/test_research_toolkit.py`
- Coverage: safe dry-run command, option-like target rejection, isolated successful execution, and nonzero process failure.

### Verification
All 46 Research Toolkit tests and all 265 project tests passed. Syntax compilation and source/wheel builds succeeded, and a real installed gallery-dl probe returned `DOWNLOAD_FAILED` with process exit code 64 for an unsupported HTTP target.

### Prevention
Subprocess wrappers must validate positional input, isolate user configuration, encode filesystem boundaries in the child argv, terminate option parsing, and derive the public envelope from the real process exit status.

## BUG-0023: Crawler URL Validation Did Not Enforce A Public-Network Boundary

Date: 2026-07-14
Severity: P1
Status: verified
Area: Research web crawling
Tags: ssrf, redirects, dns, crawl4ai, codex-sandbox

### Symptom
`crawl_url` accepted loopback and link-local targets, and a public page could redirect either the built-in HTTP client or the Crawl4AI browser toward private services.

### Reproduction / Trigger
The old HTTP path attempted `http://127.0.0.1` directly and followed redirects automatically. A fake public 302 to `http://169.254.169.254/latest/meta-data` returned success, and a simulated Crawl4AI request to the same target was continued rather than aborted.

### Root Cause
The crawler treated HTTP URL syntax as network authorization. Neither transport resolved and classified destination addresses at the request boundary, and the HTTP client delegated the redirect chain to `requests` without per-hop inspection.

### Affected Chain
FastMCP `crawl_url` -> `ResearchToolkitTools.crawl_url` -> `crawl_page_url` -> built-in `fetch_html` or `crawl_url_with_crawl4ai`.

### Fix
Added shared public-address validation, disabled automatic HTTP redirects, validated each bounded redirect before requesting it, and installed a Crawl4AI page route guard for navigation and subresource requests. Codex hostname-derived virtual DNS addresses remain usable only inside `CODEX_SANDBOX`; explicit reserved-range IP targets stay blocked.

### Tests Added / Updated
- Test file: `tests/test_research_web_security.py`
- Coverage: public success, loopback rejection before request, public-to-link-local redirect rejection, Crawl4AI request abort, explicit Codex virtual-address rejection, and Codex virtual-DNS hostname compatibility.

### Verification
All 55 targeted Research Toolkit/runtime tests and all 271 project tests passed. Syntax compilation and source/wheel builds succeeded. A real public crawl returned HTTP 200 and `Example Domain`, while real loopback and link-local targets both returned `UNSAFE_URL`.

### Prevention
Treat URL syntax, destination authorization, and redirect traversal as separate contracts. Every transport must validate each actively requested HTTP target, including browser redirects and subresources.

## BUG-0024: Reddit Availability Claim Had No Adapter Fallback

Date: 2026-07-15
Severity: P1
Status: verified
Area: External community API
Tags: reddit, atom, fallback, rate-limit, documentation-drift

### Symptom
`search_reddit` returned `NETWORK_ERROR` because Reddit rejected the anonymous JSON endpoint with HTTP 403, although the availability report claimed an Atom fallback was already implemented.

### Reproduction / Trigger
A live `r/programming/new` JSON request returned 403. The corresponding public Atom feed returned HTTP 200 with 25 entries, and source history showed that `search_reddit` had remained JSON-only since the initial commit.

### Root Cause
The cross-platform aggregate had a separate Atom implementation, but the public `search_reddit` adapter never received the documented fallback. Documentation completion was mistaken for adapter completion.

### Affected Chain
FastMCP `search_reddit` and Research Toolkit `reddit:<subreddit>` -> `ExternalAPITools.search_reddit` -> Reddit JSON/Atom transports.

### Fix
Preserved the rich JSON path when available and added a bounded public Atom fallback for JSON 403/429 responses. Atom results keep unavailable score, ratio, and comment fields as null, expose the transport, and return structured rate-limit and parse failures.

### Tests Added / Updated
- Test file: `tests/test_external_reddit.py`
- Coverage: JSON success, JSON 403 to Atom success, and Atom 429 diagnostics.

### Verification
All three focused regressions and syntax checks pass. A live adapter call fell back to Atom and returned two current `r/programming` posts with `transport=reddit_atom`.

### Prevention
Availability reports must be backed by a public adapter test or real probe; a fallback implemented in a sibling aggregate does not prove the registered tool has the same behavior.

## BUG-0025: Provider Credential Guidance Was Not Connected To Requests

Date: 2026-07-15
Severity: P1
Status: verified-with-live-auth-pending
Area: External provider authentication
Tags: github, semantic-scholar, openalex, reliefweb, credentials, documentation-drift

### Symptom
Argus told users to configure provider credentials, but GitHub, Semantic Scholar, OpenAlex, and ReliefWeb requests did not read or transmit those values. A configured key would therefore have had no effect.

### Reproduction / Trigger
Four credential-placement regressions failed against the previous implementation. A repository scan found four GitHub REST call sites plus the three provider adapters, while real no-key probes reproduced GitHub and ReliefWeb authentication blocks and Semantic Scholar shared-rate limiting.

### Root Cause
Authentication guidance was added to errors and documentation without making credential placement part of the transport contract. Each adapter constructed requests independently, so the missing wiring affected every documented provider in that group.

### Affected Chain
FastMCP GitHub, Semantic Scholar, OpenAlex, and ReliefWeb tools -> `ExternalAPITools` provider methods -> `requests` transports. Academic and cross-source aggregate tools consume the same provider envelopes.

### Fix
Added centralized GitHub headers for all four call sites, provider-specific Semantic Scholar and OpenAlex key placement, and ReliefWeb appname environment fallback. Missing credentials remain distinct from rejected credentials, anonymous requests stay available where supported, and OpenAlex request exceptions no longer expose query-string keys.

### Tests Added / Updated
- Test file: `tests/test_external_auth.py`
- Coverage: all GitHub call sites, provider-specific credential placement, ReliefWeb argument precedence, missing credentials, and rejected credentials without secret leakage.

### Verification
All five credential regressions pass. Real no-key probes return `AUTH_REQUIRED` for GitHub code and ReliefWeb, `RATE_LIMITED` for Semantic Scholar, and an exact OpenAlex paper with `authenticated=false`. Authenticated live probes remain pending until the user configures regular provider credentials.

### Prevention
Any documented credential must have a transport-level regression proving its exact header or parameter placement, plus a failure-path assertion that secrets cannot appear in public errors.

## BUG-0026: xhs Business Commands Could Not Write Their Sandbox Runtime Cache

Date: 2026-07-15
Severity: P1
Status: verified
Area: Social CLI runtime isolation
Tags: xhs, codex-sandbox, cookies, cache, subprocess, runtime-home

### Symptom
The user's xhs login was valid and the bare CLI could search successfully, but `CLIToolsAdapter.run_xhs("search", ...)` returned `AUTH_STORAGE_UNAVAILABLE` inside Codex.

### Reproduction / Trigger
An unsandboxed `xhs status` refreshed the user's normal Chrome login and returned an authenticated profile. The bare read-only search returned current notes, while the same Argus adapter call failed when xhs attempted to write token and note-index caches under `~/.xiaohongshu-cli`.

### Root Cause
The adapter treated xhs login storage and mutable command runtime state as one directory. Codex could read the user's saved login but could not write the adjacent cache files, so a valid account was misclassified as unavailable authentication.

### Affected Chain
FastMCP `run_xhs`, `xhs_auth_status`, xhs social tools, and cross-platform xhs source -> `CLIToolsAdapter._exec` -> xhs subprocess -> user-level cookie and cache directory.

### Fix
Each adapter now creates a private process temporary HOME, copies the existing saved login only when needed, restricts the runtime directory and cookie file to `0700` and `0600`, and lets xhs write its mutable caches there. The runtime is removed when the adapter exits; no credential or cache enters the repository.

### Tests Added / Updated
- Test file: `tests/test_cli_tools.py`
- Coverage: private writable runtime HOME and cookie permissions on success, plus a missing-login error that does not start the subprocess.

### Verification
All six CLI adapter tests and all 20 related CLI/social/cross-platform tests pass. Syntax checks pass. A real Codex-sandboxed Argus search returned 20 current xhs notes after the fix.

### Prevention
Authenticated CLI wrappers must separate read-only user credentials from writable runtime state and prove the actual sandboxed business command, not only an auth-status command.

## BUG-0027: xhs Social Wrappers Targeted Stale CLI Flags

Date: 2026-07-15
Severity: P1
Status: verified
Area: Social CLI command contracts
Tags: xhs, click, argument-contract, social-ops, documentation-drift

### Symptom
The installed xhs CLI and login were usable, but `xhs_feed(limit=3)` failed before making a business request with `No such option '--limit'`.

### Reproduction / Trigger
A real Argus feed call reproduced the Click parser error. Comparing all 11 xhs social wrappers with xhs 0.6.4 `--help` showed 9 stale contracts: six read commands passed unsupported limits, comment and post used renamed flags, and confirmed delete omitted the CLI's noninteractive `--yes` flag.

### Root Cause
The social wrappers assumed a common `--limit` and older write-option vocabulary instead of pinning each MCP wrapper to the installed CLI command contract. Unit tests asserted the same stale argv, so they protected drift rather than compatibility.

### Affected Chain
Eleven FastMCP xhs social tools -> `SocialOpsTools` -> `CLIToolsAdapter.run_xhs` -> xhs 0.6.4 Click commands. Nine wrappers required correction; like and favorite already matched.

### Fix
Mapped each wrapper to the installed command options, retained MCP `limit` compatibility through bounded local slicing when upstream has no limit, used `--num` for notifications, and corrected comment, post, and delete arguments. Existing auth preflight, parameter checks, and confirmation gates remain intact.

### Tests Added / Updated
- Test file: `tests/test_social_ops.py`
- Coverage: all six read-command argv contracts and local limits, all three corrected confirmed-write argv contracts, auth blocking, confirmation blocking, and invalid input.

### Verification
All seven social regressions and 30 related CLI/social/cross-platform/MCP tests pass. Syntax checks pass. Feed, hot, own notes, notifications, favorites, and comments each returned real data through the corrected wrappers. No write operation was executed.

### Prevention
CLI wrapper tests must derive expected argv from the installed command help or source and include one real read-only business probe; tests that merely mirror wrapper literals do not detect contract drift.

## BUG-0028: Discord Self-Bot Adapter Was Advertised As Installable

Date: 2026-07-15
Severity: P1
Status: verified
Area: External CLI policy boundary
Tags: discord, self-bot, user-token, policy, capability-status

### Symptom
Argus reported Discord as a merely missing optional CLI and recommended installing `kabi-discord-cli`, whose documented authentication extracts and automates a normal Discord user token.

### Reproduction / Trigger
The previous `run_discord` path returned `NOT_INSTALLED` with an install hint, `check_cli_auth` treated Discord like the four supported CLIs, and system health listed the package without a policy status. Discord's official support policy explicitly prohibits automating normal user accounts.

### Root Cause
The original integration checked package availability and command shape without validating the upstream platform's authorization model. A third-party package was therefore treated as usable even though its required credential flow violated the service policy.

### Affected Chain
FastMCP `run_discord`, cross-platform Discord source, CLI auth summary, and system health -> `CLIToolsAdapter` / telemetry -> `kabi-discord-cli` user-token automation.

### Fix
Kept the public MCP name for compatibility but made every Discord adapter call return `POLICY_UNSUPPORTED` before process discovery or launch. Auth and health output now mark the entry unsupported, omit the install package, and point to application-owned Discord Bot or OAuth2 integration instead.

### Tests Added / Updated
- Test files: `tests/test_cli_tools.py`, `tests/test_system_health.py`
- Coverage: no subprocess starts for Discord, auth status contains no install hint, and health reports `policy_unsupported` with no package.

### Verification
The three focused regressions pass, including the previously failing `NOT_INSTALLED` and missing-health-field cases.

### Prevention
External integrations must validate the provider's permitted authentication model before advertising an install command; personal use does not make a prohibited user-token automation path supported.

## BUG-0029: Bilibili Social Wrappers Targeted Stale CLI Arguments

Date: 2026-07-15
Severity: P1
Status: verified
Area: Social CLI command contracts
Tags: bilibili, click, argument-contract, social-ops, missing-regression

### Symptom
All nine Bilibili social MCP tools were publicly registered, but five read wrappers passed a guessed `--limit` option and the dynamic write wrappers used argument forms that do not match bilibili-cli 0.6.2.

### Reproduction / Trigger
New exact-argv tests failed against the previous implementation: every read wrapper emitted `--limit`, dynamic post emitted `--text`, and dynamic delete omitted the upstream noninteractive `--yes`. The official 0.6.2 command source confirms the supported options and positional arguments.

### Root Cause
The Bilibili wrappers had no tests at all and reused a presumed common limit vocabulary instead of each Click command's actual contract. This is the second occurrence of RC-0024 after the xhs wrapper drift.

### Affected Chain
Nine FastMCP Bilibili social tools -> `SocialOpsTools` -> `CLIToolsAdapter.run_bilibili` -> bilibili-cli 0.6.2 commands. The generic cross-platform search already uses the supported `-n` alias.

### Fix
Mapped `my-dynamics`, `history`, and `hot` to bounded `--max`; removed unsupported options from `following` and `feed`; applied bounded local response slicing; corrected dynamic post to positional text and confirmed delete to `--yes`. Like and triple were already correct.

### Tests Added / Updated
- Test file: `tests/test_social_ops.py`
- Coverage: all five read wrappers and result limits, both interaction wrappers, both confirmed write contracts, confirmation blocking, and invalid identifier short-circuiting.

### Verification
All four Bilibili regression groups pass against the official 0.6.2 source contract. After the approved user-level installation, generic public search, generic hot, and `bili_hot(limit=2)` each returned two real items through Argus. `bili status` returns `not_authenticated`, so account reads and writes remain conditional on normal user login and no write was executed.

### Prevention
Do not mark a CLI capability verified from source and mocks alone; install the declared version after approval and execute at least one safe public read through the full Argus path.

## BUG-0030: Interactive CLI Inherited MCP Standard Input

Date: 2026-07-15
Severity: P1
Status: verified
Area: External CLI subprocess boundary
Tags: telegram, subprocess, stdin, mcp-stdio, authentication

### Symptom
The installed Telegram CLI entered a phone-number prompt during `tg status`, while the shared Argus subprocess wrapper inherited its parent's standard input.

### Reproduction / Trigger
A real `tg status --yaml` reached `Please enter your phone (or bot token)`. Source inspection showed `CLIToolsAdapter._exec` passed `input=None` without setting `stdin`, so subprocess inherited the FastMCP stdio transport. A regression then failed with a missing `stdin` keyword before the fix.

### Root Cause
The generic wrapper treated absence of explicit input as permission to inherit ambient stdin. That assumption is unsafe for agent-facing CLI subprocesses because an upstream command can introduce an interactive prompt during authentication or confirmation.

### Affected Chain
FastMCP `check_cli_auth` and all four supported generic CLI tools -> `CLIToolsAdapter._exec` -> external Click/Telethon subprocess. Repository scanning found no other subprocess wrapper on this interactive authentication call chain.

### Fix
Defaulted external CLI subprocess stdin to `subprocess.DEVNULL`. Callers that intentionally pass `input_text` still use subprocess `input`, preserving explicit confirmation support without exposing MCP protocol input.

### Tests Added / Updated
- Test file: `tests/test_cli_tools.py`
- Coverage: Telegram status receives `DEVNULL` and returns its structured authentication error; explicit input text remains available and never combines with `stdin`.

### Verification
Both new regressions and all ten CLI adapter tests pass. A real Argus `run_telegram("status", timeout=10)` call returned structured `auth_error` in 0.14 seconds without prompting or timing out.

### Prevention
Agent-facing subprocess wrappers must close ambient stdin by default and open it only for explicitly modeled input; real auth probes must include the unconfigured path because that is where third-party CLIs often prompt.

## BUG-0031: Twitter And Telegram MCP Help Advertised Stale Arguments

Date: 2026-07-15
Severity: P2
Status: verified
Area: External CLI MCP descriptions
Tags: twitter, telegram, click, documentation-contract, mcp

### Symptom
The generic Twitter and Telegram tools were callable, but their MCP descriptions recommended unsupported Twitter argument forms and overstated Telegram local-cache behavior.

### Reproduction / Trigger
The installed twitter-cli 0.8.5 help rejected or omitted `--latest`, `feed --following`, `user --likes`, and `user --tweets`; the supported forms are `search -t latest`, `feed -t following`, `likes`, and `user-posts`. Installed kabi-tg-cli 0.6.0 help confirmed `history -n`, sync limits, and export format/output options.

### Root Cause
The exposed MCP help text had not been reconciled with the pinned installed CLI versions. Runtime code was a generic argument pass-through, so stale documentation could make an otherwise available tool fail during argument parsing.

### Affected Chain
FastMCP tool discovery -> `run_twitter` / `run_telegram` descriptions -> agent-selected argv -> `CLIToolsAdapter` -> installed Click command parser. Cross-platform Twitter/Telegram search already used supported arguments.

### Fix
Replaced stale Twitter forms with the installed 0.8.5 commands, corrected Telegram 0.6.0 examples, and clarified that local search is offline while synchronization remains subject to Telegram limits.

### Tests Added / Updated
- No new behavior test was needed for a description-only correction.
- Existing `tests/test_mcp_registration.py`, `tests/test_cross_platform.py`, and `tests/test_cli_tools.py` confirm registration and runtime call paths still load.

### Verification
The exact installed command help was executed for all documented subcommands. A repository scan found the removed argument forms only in the audit's historical note; 27 MCP/CLI/cross-platform tests and syntax checks pass.

### Prevention
After installing or upgrading an external CLI, reconcile both executable wrappers and agent-visible MCP descriptions against the installed help before calling the integration ready.

## BUG-0032: GDELT Rate Limits Were Reported As Network Errors

Date: 2026-07-15
Severity: P2
Status: verified
Area: External API availability classification
Tags: gdelt, rate-limit, http-429, error-envelope

### Symptom
Two real GDELT requests returned HTTP 429, but `search_gdelt` exposed both as `NETWORK_ERROR`, hiding the source's actual availability condition.

### Reproduction / Trigger
The current-state audit reproduced persistent 429 responses. A focused regression then returned `NETWORK_ERROR` because `raise_for_status()` raised before the adapter inspected the response status.

### Root Cause
The GDELT adapter caught every `RequestException` under one generic code and discarded status-specific metadata. No-key public access had been treated as if transport failure and provider throttling were equivalent.

### Affected Chain
FastMCP `search_gdelt` -> `ExternalAPITools.search_gdelt` -> `_get` -> `raise_for_status`. A module scan found many generic HTTP wrappers, but no other currently failing provider had the same repeated GDELT call-chain evidence.

### Fix
Classified HTTP 429 before `raise_for_status()`, returned `RATE_LIMITED` with source metadata, and preserved `Retry-After` only when the provider supplies it. Persistent limits are not retried automatically.

### Tests Added / Updated
- Test file: `tests/test_external_gdelt.py`
- Coverage: normal article normalization and a 429 response with `Retry-After` metadata.

### Verification
Both regressions pass. A real post-fix GDELT probe still received the upstream limit but returned `RATE_LIMITED`; no `Retry-After` value was invented when the response omitted it.

### Prevention
Inspect status codes before broad request-exception normalization, preserve provider retry metadata, and do not equate anonymous/no-key access with unlimited access.

## BUG-0033: YouTube RSS Failure Was Treated As Channel Absence

Date: 2026-07-15
Severity: P1
Status: verified
Area: External YouTube channel metadata
Tags: youtube, rss, yt-dlp, metadata-only, fallback

### Symptom
`get_youtube_channel` returned `NOT_FOUND` or `NETWORK_ERROR` for valid channel IDs because YouTube RSS returned 404 or SSL failures, even though metadata-only yt-dlp could list the same public channel.

### Reproduction / Trigger
Two known channel IDs and one channel ID resolved from a real public video failed through RSS. A manual no-cookie/no-download yt-dlp flat-playlist probe returned the channel's public video, proving that entity existence and RSS transport availability had been conflated.

### Root Cause
The adapter used one transport as both data source and existence oracle. Its 404 branch returned immediately, so a valid channel could not use an already installed, policy-compatible metadata transport.

### Affected Chain
FastMCP `get_youtube_channel` -> `ExternalAPITools.get_youtube_channel` -> YouTube RSS. Repository scanning found no other channel-listing implementation; `research_video_metadata` intentionally handles only one video and rejects playlists.

### Fix
Kept RSS as the primary transport and added a separate strict channel helper in `research_video.py`. RSS dependency failure, 404, request/parse error, or empty output now falls back to yt-dlp flat-playlist for a validated UC channel ID and 1–30 entries. The helper ignores user config, cookies, browser cookies, cache, remote components, stdin, and downloads, then allowlists only public watch-page metadata.

### Tests Added / Updated
- Test files: `tests/test_external_youtube.py`, `tests/test_research_video.py`
- Coverage: RSS primary success, 404 fallback success, dual-source failure, invalid public limit, strict channel ID validation, flat-playlist command safety, and direct-media URL exclusion.

### Verification
All 14 YouTube/existing video regressions pass. A real FastMCP valid-channel call fell back from RSS `NOT_FOUND` and returned one titled video with `downloaded_media=false` and `cookies_used=false`.

### Prevention
Do not infer resource absence from one optional transport failure. Keep fallbacks policy-compatible, metadata-only, bounded, independently normalized, and explicit in response provenance.
