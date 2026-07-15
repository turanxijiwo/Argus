# Technical Debt Register

Record systemic issues that should not be mixed into unrelated bug fixes.

## Entry Format

```md
## DEBT-0001: Short Debt Title

Date: 2026-01-01
Status: open / in_progress / resolved / archived
Severity: low / medium / high / critical
Area:
Related bugs:
- Bug references
Related patterns:
- Pattern references

### Problem
Describe the debt.

### Why Not Fixed Now
Explain why this was not included in the current task.

### Risk
What may happen if this remains unresolved?

### Proposed Resolution
Describe a safe future task.

### Exit Criteria
How do we know this debt is resolved?
```

## Technical Debt

## DEBT-0001: Optional Runtime Health Is Package-Level

Date: 2026-07-10
Status: resolved
Severity: low
Area: Research Toolkit optional adapters
Related bugs:
- None
Related patterns:
- Optional runtime readiness

### Problem
`research_toolkit_health` reports the Codex source as ready when the
`openai-codex` package is importable, but a real SDK run can still fail while
loading incompatible user-level Codex configuration. The 2026-07-10 delivery
audit observed `model_reasoning_effort = "ultra"` being rejected by the
installed SDK parser, which accepts values through `xhigh`.

### Why Not Fixed Now
The incompatible value is in user-level Codex configuration outside Argus.
Argus must not silently rewrite global settings, and running a Codex thread as
part of every health check would be slow and stateful.

### Risk
Agents may interpret package availability as end-to-end Codex source readiness.

### Proposed Resolution
Implemented through `research_runtime_probe`, which performs explicit
verification and returns sanitized configuration or permission errors without
changing user state.

### Exit Criteria
- Health output distinguishes package detection from a successful runtime probe.
- The probe has deterministic tests for configuration failures and error sanitization.
- No global Codex configuration is modified by Argus.

## DEBT-0002: PDF-Native Page Boundaries Are Not Preserved

Date: 2026-07-11
Status: open
Severity: medium
Area: Research comparison evidence locators
Related bugs:
- None
Related patterns:
- Evidence traceability

### Problem
Jina Reader markdown can preserve headings and report a document's total page count without emitting a marker for each source PDF page. Argus can therefore guarantee saved-artifact document/character locators and often section/paragraph context, but cannot always map those ranges back to original PDF page numbers.

### Why Not Fixed Now
The current project has no PDF-native extraction dependency or adapter that preserves page boundaries. Adding one would be a separate dependency and ingestion-path decision rather than a safe extension of the saved-artifact comparison contract.

### Risk
Users may expect a publication citation to include a PDF page even when the extracted artifact does not contain enough information to prove it.

### Proposed Resolution
Add an optional PDF-native extraction adapter that records page boundaries during resource reading, then propagate verified page numbers into the existing locator schema.

### Exit Criteria
- PDF artifacts retain page-boundary metadata during ingestion.
- Every emitted page locator is reproducible against the original PDF.
- Section/paragraph/character fallback remains available for HTML and page-less text.

## DEBT-0003: Locator Replay Does Not Bind Source Content

Date: 2026-07-11
Status: resolved
Severity: medium
Area: Research comparison evidence integrity
Related bugs:
- None
Related patterns:
- Evidence traceability

### Problem
Comparison locators store source artifact paths plus document and character coordinates, but no source-content digest. The resolver detects missing text and invalid ranges, yet cannot detect an in-place source edit when the coordinates remain valid.

### Why Not Fixed Now
Adding fingerprints changes the comparison artifact contract and needs a compatibility policy for existing saved comparisons. The bounded replay tool can be useful safely without mixing that schema migration into its first release.

### Risk
A source artifact edited after comparison could return different text for the same locator while still passing coordinate validation.

### Proposed Resolution
Store deterministic document or selected-input SHA-256 fingerprints on new comparison sources and verify them during locator replay. Preserve read compatibility for older artifacts while clearly reporting that their content integrity is unverified.

### Resolution
Implemented `comparison_input_v1` SHA-256 fingerprints for each selected document prefix. Locator replay verifies matching fingerprints before returning excerpts, emits `SOURCE_CONTENT_MISMATCH` on mutation, and reports older fingerprint-free comparisons as unverified.

### Exit Criteria
- New comparison artifacts include deterministic source-content fingerprints.
- Locator replay rejects fingerprint mismatches with a stable structured error.
- Existing comparison artifacts remain readable and explicitly report missing integrity metadata.

## DEBT-0004: Cross-Platform Tool Module Mixes Source Adapters And Aggregation

Date: 2026-07-14
Status: mitigated
Severity: medium
Area: Cross-platform aggregation
Related bugs:
- BUG-0010
Related patterns:
- PATTERN-0001

### Problem
`argus_server/tools/cross_platform.py` is 753 lines and combines source-specific HTTP/CLI calls, item normalization, aggregate status derivation, sentiment scoring, and narrative ranking in one module.

### Why Not Fixed Now
BUG-0010 required a focused contract and truthfulness repair. Splitting the module at the same time would broaden the regression surface and violate the single-issue maintenance boundary.

### Risk
Future source changes can accidentally reuse incompatible arguments, drop structured diagnostics, or alter aggregate status while editing an unrelated branch.

### Proposed Resolution
In a dedicated refactor, move source fetch/normalization logic behind small internal modules while preserving the public `CrossPlatformTools` methods and current response envelopes.

### Exit Criteria
- `CrossPlatformTools.universal_search` and `narrative_tracking` keep their public signatures and tested envelopes.
- Source-specific arguments and structured failures remain covered by `tests/test_cross_platform.py`.
- HTTP/CLI adapters, normalization, and aggregate analysis no longer share one oversized module.

## DEBT-0005: External API Providers Share One Oversized Module

Date: 2026-07-14
Status: open
Severity: medium
Area: External API adapters
Related bugs:
- BUG-0012
Related patterns:
- None

### Problem
`argus_server/tools/external_apis.py` is 3,110 lines and combines more than fifty provider adapters with multi-source academic orchestration.

### Why Not Fixed Now
BUG-0012 required a focused response-contract fix. Splitting all providers would broaden the regression surface and mix architecture work into a single bug repair.

### Risk
Provider-specific transport changes and aggregate status logic can become coupled, making source failures harder to isolate and test.

### Proposed Resolution
In a dedicated refactor, group provider adapters by domain and keep `ExternalAPITools` as a compatibility facade with unchanged public methods and envelopes.

### Exit Criteria
- Existing `ExternalAPITools` public method signatures remain compatible.
- Provider modules have focused tests for request and normalization contracts.
- Academic fan-out status tests remain green through the compatibility facade.

## DEBT-0006: AI Analytics Mixes LLM, Storage, And Aggregate Orchestration

Date: 2026-07-14
Status: open
Severity: medium
Area: AI analysis tools
Related bugs:
- BUG-0013
Related patterns:
- PATTERN-0002

### Problem
`argus_server/tools/ai_analytics.py` is 493 lines and combines LLM configuration and semantic deduplication, storage-backed anomaly detection, and multi-step aggregate status orchestration.

### Why Not Fixed Now
BUG-0013 required a focused response-contract repair. Splitting the module would broaden the regression surface and mix architecture work into one bug fix.

### Risk
Provider configuration, storage query behavior, and aggregate status semantics can become coupled, making future failures harder to isolate and test.

### Proposed Resolution
In a dedicated refactor, separate semantic deduplication, anomaly detection, and orchestration behind the existing `AIAnalyticsTools` compatibility facade.

### Exit Criteria
- Existing `AIAnalyticsTools` public method signatures and envelopes remain compatible.
- Semantic deduplication and anomaly detection have focused module-level tests.
- `tests/test_ai_analytics.py` remains green through the compatibility facade.

## DEBT-0007: Telemetry And Readiness Collection Share One Oversized Module

Date: 2026-07-14
Status: open
Severity: medium
Area: Health monitoring and telemetry
Related bugs:
- BUG-0014
Related patterns:
- None

### Problem
`argus_server/tools/telemetry.py` is 448 lines and combines telemetry persistence/statistics, tracing decoration, and comprehensive system-readiness collection.

### Why Not Fixed Now
BUG-0014 required one authoritative health contract and focused consumer wiring. Extracting telemetry and health classes simultaneously would broaden the regression surface beyond the P0 semantic repair.

### Risk
Changes to telemetry storage can affect readiness behavior, and adding new health checks can make an unrelated tracing module harder to maintain.

### Proposed Resolution
Move readiness collection and its check helpers into a focused internal module while preserving `HealthTools`, the FastMCP tool/resource envelopes, and dependency injection contracts.

### Exit Criteria
- `HealthTools.system_health` keeps its public envelope and required/optional semantics.
- Telemetry storage and tracing tests remain independent from readiness tests.
- `tests/test_system_health.py` and telemetry regressions remain green through the compatibility facade.

## DEBT-0008: System Tools Mix Status, Crawl Persistence, Rendering, And Version Checks

Date: 2026-07-14
Status: open
Severity: medium
Area: System management tools
Related bugs:
- BUG-0014
- BUG-0015
Related patterns:
- None

### Problem
`argus_server/tools/system.py` is 640 lines and combines health/status adaptation, crawl configuration and execution, layered persistence reporting, HTML rendering, and remote version checks.

### Why Not Fixed Now
BUG-0015 required a focused persistence-contract repair. Splitting the module at the same time would broaden the regression surface and mix architecture work into a single bug fix.

### Risk
Changes to crawl persistence can affect unrelated status or version behavior, while the oversized module makes response-contract ownership harder to identify.

### Proposed Resolution
In a dedicated refactor, move crawl orchestration/persistence, HTML rendering, and version checks into focused internal modules while preserving `SystemManagementTools` as the compatibility facade.

### Exit Criteria
- `trigger_crawl`, `get_system_status`, and `check_version` keep their public signatures and envelopes.
- `tests/test_system_crawl_persistence.py` and `tests/test_system_health.py` remain green through the facade.
- Crawl persistence status no longer shares a module with HTML rendering or version transport logic.

## DEBT-0009: Other FastMCP Tools Still Borrow The Global Storage Manager

Date: 2026-07-14
Status: open
Severity: medium
Area: FastMCP storage lifecycle
Related bugs:
- BUG-0016
Related patterns:
- None

### Problem
`daily_brief.py`, `exporter.py`, `ai_analytics.py`, and `safety.py` still call `get_storage_manager()` from methods that can run through FastMCP worker threads. They share the mechanism that caused BUG-0016, but no cross-thread failure has yet been reproduced in those separate workflows.

### Why Not Fixed Now
BUG-0016 had direct runtime evidence in semantic rebuild and a bounded call chain. Rewriting four unrelated workflows without reproducing their connection ownership would violate the evidence-driven scope boundary.

### Risk
A tool may reuse a SQLite connection created by another worker or defer cleanup to a different thread, producing intermittent failures in a long-lived MCP server.

### Proposed Resolution
Probe each workflow separately under its real FastMCP entrypoint, identify whether it opens SQLite, and replace the global manager with project-bound operation-scoped ownership only where the failure is reproduced.

### Exit Criteria
- Each listed FastMCP workflow has a thread-lifecycle regression or evidence that it does not retain SQLite connections.
- Any operation-scoped SQLite manager is closed in its owning worker thread.
- Public tool signatures and response envelopes remain unchanged.

## DEBT-0010: Launchd Cannot Enter A Desktop-Hosted Argus Workspace

Date: 2026-07-14
Status: open
Severity: high
Area: Local scheduling runtime
Related bugs:
- None
Related patterns:
- None

### Problem
A real user LaunchAgent loads and accepts `kickstart`, but its project-local virtual-environment Python stalls during CPython path initialization before `scheduler_runner.main()` when Argus is hosted under macOS-protected Desktop storage. No log or last-run report is produced.

### Why Not Fixed Now
The operating system access boundary cannot be bypassed safely in project code. Granting broad protected-folder access or moving the user's workspace is an explicit user/environment decision, while changing the runner to a copied home-directory runtime would be a separate deployment architecture.

### Mitigation Verified
The local Codex workspace automation `argus` completed a real no-notification crawl-before-index cycle from the current Desktop workspace. All 11 platforms succeeded, SQLite and the 359-document index aligned, the semantic probe returned readable results, and no tracked files or notifications changed. Native launchd remains unsupported in this location.

### Risk
`schedule_task` and `run_scheduled_task` can report successful launchctl submission even though no workflow step executes, so unattended collection appears configured but silently produces no new data.

### Proposed Resolution
For this personal Codex workflow, prefer a Codex workspace automation that runs the verified scheduler runner without notification steps. Alternative resolutions are an explicit protected-folder permission grant or deliberate project relocation followed by a fresh launchd acceptance pass. Consider adding completion-status polling to the scheduler API separately.

### Exit Criteria
- The selected unattended runtime enters the project and produces a first log plus last-run report.
- The report shows crawl before index rebuild, no notification step, and no failed platform.
- SQLite crawl history advances and semantic index document count matches local news history.
- Temporary acceptance services, task files, and processes are removed after verification.

## DEBT-0011: Video Metadata Module Mixes Single-Item And Channel Commands

Date: 2026-07-15
Status: open
Severity: low
Area: Research video metadata adapter
Related bugs:
- BUG-0033
Related patterns:
- None

### Problem
`argus_server/tools/research_video.py` is 403 lines and now owns two separate yt-dlp command contracts, process error handling, safety metadata, and single-video/channel normalization.

### Why Not Fixed Now
BUG-0033 required one bounded legal fallback for an already failing public tool. Splitting the module during the availability repair would broaden scope and make safety parity harder to verify.

### Risk
Future yt-dlp option changes could drift between the single-video and flat-playlist paths, especially around config, cookies, cache, remote components, stdin, and sanitized errors.

### Proposed Resolution
In a dedicated refactor, extract shared metadata-only process options/execution and keep separate single-video and channel normalizers while preserving current public schemas.

### Exit Criteria
- Both command paths share one tested no-config/no-cookie/no-download/no-stdin process boundary.
- `argus.research.video.metadata.v1` and `argus.research.video.channel.v1` remain unchanged.
- `tests/test_research_video.py`, `tests/test_external_youtube.py`, and the real single-video/channel probes remain green.
