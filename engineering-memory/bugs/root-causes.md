# Root Cause Memory

This file tracks root-cause categories, not individual bugs.

## Entry Format

```md
## RC-0001: Short Root Cause Name

Status: active / superseded / deprecated / archived
Category: state / API contract / schema / async lifecycle / cache / config / test gap / architecture boundary
First observed: bug id or short reference
Recurring count: 0
Severity trend: low / medium / high

### Description
Describe the root cause pattern.

### Typical Symptoms
- Symptom 1
- Symptom 2

### Common Triggers
- Trigger 1
- Trigger 2

### Prevention Rule
What should Codex check before editing this kind of code?

### Related Bugs
- Bug references
```

## Root Causes

## RC-0001: Display-Oriented Merged Results Used As Crawl Candidate Source

Status: active
Category: API contract
First observed: BUG-0001
Recurring count: 1
Severity trend: medium

### Description
Merged research results are optimized for ranked presentation and may include useful non-page items such as answer summaries. Workflows that require crawlable pages must not treat the merged list as the only source of URL-bearing candidates.

### Typical Symptoms
- A research workflow succeeds but produces zero crawled documents.
- `skipped_item_count` increases even though the provider returned URL results.
- Low `limit` values expose the issue because non-page items can occupy the visible merged slot.

### Common Triggers
- Web providers return an answer summary plus search results.
- Downstream workflows filter URLs after using a truncated display list.

### Prevention Rule
For page-crawling flows, build the candidate pool from both merged results and successful source raw items before URL filtering and dedupe.

### Related Bugs
- BUG-0001

## RC-0002: Availability-Only Ranking Replaced Query Relevance

Status: active
Category: API contract
First observed: BUG-0002
Recurring count: 1
Severity trend: medium

### Description
Aggregated resource candidates came from sources with different default ordering, but the unified layer ranked only by access status. Downloadable but irrelevant results could therefore outrank an exact requested title.

### Typical Symptoms
- A resource search returns valid files that do not match the requested title.
- A partial source outage changes which source dominates the first page.
- Low result limits hide an exact match that exists further down a source response.

### Common Triggers
- One relevance-oriented source is rate-limited or unavailable.
- Another source defaults to publication-date ordering.
- All surviving candidates share the same access status.

### Prevention Rule
Cross-source resource search must compute local query relevance before truncation and use access status only as a filter or tie-breaker.

### Related Bugs
- BUG-0002

## RC-0003: Semantic Name Collision Across Response Envelope Layers

Status: active
Category: API contract
First observed: BUG-0003
Recurring count: 1
Severity trend: low

### Description
The standard response envelope uses `summary` for operation statistics while the normalized resource payload can also contain summary text under `data.summary`. Code that reasons from field names instead of the envelope contract can write metadata to the wrong layer.

### Typical Symptoms
- Content generation succeeds but runner/model attribution is missing from the consumer payload.
- Metadata appears in top-level operational statistics where downstream workflows do not read it.
- Tests pass for summary text but fail when asserting provenance fields.

### Common Triggers
- A payload domain also uses the word `summary`.
- Metadata is added after a normalization helper has already wrapped the payload.

### Prevention Rule
For standard Argus envelopes, mutate normalized content only through `result["data"]`; reserve top-level `result["summary"]` for operation counts and status statistics, and assert both layers in contract tests.

### Related Bugs
- BUG-0003

## RC-0004: Lexical Containment Checked Before Symlink Resolution

Status: active
Category: architecture boundary
First observed: BUG-0004
Recurring count: 1
Severity trend: high

### Description
Project-local path guards used absolute lexical paths for containment checks. A symlink inside the project could therefore point at an external target while the unresolvable-looking input still shared the project prefix.

### Typical Symptoms
- A supposedly project-local artifact read succeeds through a symlink to an external directory.
- Output validation approves a path whose actual write target is outside the project.
- Handoff code publishes an external target as if it were a project-relative path.

### Common Triggers
- Existing symlink components in artifact or output directories.
- Reusing lexical `abspath`/`commonpath` helpers for security decisions.

### Prevention Rule
Resolve both project root and candidate with `realpath` before `commonpath`, reuse one canonical boundary helper across server call chains, and preserve standalone script behavior when sharing code would add a new import requirement.

### Related Bugs
- BUG-0004

## RC-0005: Derived Health Metric Maintained Separately From Source Records

Status: active
Category: state
First observed: BUG-0005
Recurring count: 1
Severity trend: low

### Description
The capability matrix and its ready-count summary had separate sources of truth. New capabilities updated the matrix but could be omitted from the manual count tuple.

### Typical Symptoms
- A health summary count disagrees with the detailed records returned in the same response.
- Adding a capability requires edits in two distant blocks.

### Common Triggers
- Public capability registration grows over time.
- Aggregate metrics are encoded as hand-maintained parallel lists.

### Prevention Rule
Compute aggregate counts directly from the returned capability dictionary and assert that relationship in tests.

### Related Bugs
- BUG-0005

## RC-0006: Derived Validation Error Took Precedence Over Primary Violation

Status: active
Category: API contract
First observed: BUG-0006
Recurring count: 1
Severity trend: medium

### Description
Layered validation produced both a primary unknown-citation error and a dependent locator-source mismatch. Aggregate error selection looked only for the presence of locator issues, so the dependent error changed the public code.

### Typical Symptoms
- Adding deeper validation changes an established error code for the same malformed input.
- One invalid field creates several issues and the least useful derived issue is reported as primary.

### Common Triggers
- Validation layers depend on identifiers normalized by earlier layers.
- Error selection uses `any()` rather than explicit precedence rules.

### Prevention Rule
Classify errors by primary contract layer and emit a specialized downstream code only when all detected issues belong to that layer.

### Related Bugs
- BUG-0006

## RC-0007: Nested Path Presence Was Mistaken For Type Safety

Status: active
Category: API contract
First observed: BUG-0007
Recurring count: 1
Severity trend: medium

### Description
A nested path read from saved JSON was checked only for truthiness. Shared path helpers were designed for typed public arguments, so a truthy list reached `os.path` and escaped the standard error envelope.

### Typical Symptoms
- A malformed project-local artifact causes an uncaught `TypeError` in path normalization.
- Public parameter tests pass while equivalent nested metadata fails before a structured error can be returned.

### Common Triggers
- Reusing typed API helpers with data loaded from JSON.
- Presence checks such as `if path` standing in for schema validation.

### Prevention Rule
Validate nested path values as non-empty strings at the artifact contract boundary before canonical path resolution; cover malformed JSON types in the owning workflow test.

### Related Bugs
- BUG-0007

## RC-0008: Python Boolean Equality Bypassed JSON Integer Validation

Status: active
Category: schema
First observed: BUG-0008
Recurring count: 1
Severity trend: medium

### Description
JSON booleans deserialize to Python `bool`, which is an `int` subclass. Equality-only coordinate matching can therefore accept `false` as `0` and `true` as `1` unless type validation explicitly excludes booleans.

### Typical Symptoms
- Malformed boolean indexes pass document or range matching.
- A structurally invalid artifact is reported as verified.

### Common Triggers
- Comparing deserialized JSON numbers before schema validation.
- Using `isinstance(value, int)` without excluding `bool`.

### Prevention Rule
For JSON integer coordinates, validate with `isinstance(value, int) and not isinstance(value, bool)` before equality, indexing, or range operations.

### Related Bugs
- BUG-0008

## RC-0009: Coordinate Domain Exceeded Integrity Domain

Status: active
Category: integrity boundary
First observed: BUG-0009
Recurring count: 1
Severity trend: high

### Description
A content fingerprint proved only a bounded comparison-input prefix, while locator coordinates were validated against the larger current source document. The coordinate authority therefore exceeded the domain covered by the integrity proof.

### Typical Symptoms
- A locator beyond `fingerprint.text_chars` is reported as verified.
- Bounded replay can expose text that was not supplied to the comparison.
- A full audit reports no issue even though a claim references unverified source content.

### Common Triggers
- Source documents are longer than the per-source comparison input cap.
- Saved locator metadata is corrupted or intentionally modified after comparison generation.
- Integrity checks and coordinate checks use different length boundaries.

### Prevention Rule
Whenever integrity covers a bounded prefix or slice, every coordinate derived from that proof must be constrained to the same domain before content is replayed or reported as verified.

### Related Bugs
- BUG-0009

## RC-0010: Heterogeneous Source Contracts Collapsed Into Generic Success

Status: active
Category: API contract and status semantics
First observed: BUG-0010
Recurring count: 3
Severity trend: high

### Description
A multi-source or multi-step orchestrator assumed compatible child contracts or treated completion of its fan-out as business success even when every child failed or returned no useful item.

### Typical Symptoms
- Several adapters fail with unsupported argument errors after receiving the same generic option.
- The top-level envelope is successful while merged results are empty.
- Partial source failures disappear or lose structured error codes.
- A downstream analysis tool produces an empty report from the misleading aggregate.

### Common Triggers
- Adding a new provider to an existing fan-out without checking its real method or CLI help.
- Reusing one parameter name across SDK, HTTP, and CLI adapters.
- Returning `_ok` after orchestration without evaluating useful output and source failures.
- Calling child analysis steps without validating the requested mode or containing step exceptions.

### Prevention Rule
Verify each adapter's actual input and output contract, preserve source-scoped diagnostics, and derive aggregate status from both useful output and failed/empty source counts.

### Related Bugs
- BUG-0010
- BUG-0012
- BUG-0013

## RC-0011: Upstream Service Lifecycle Was Not Reconciled With Registration

Status: active
Category: external service lifecycle
First observed: BUG-0011
Recurring count: 1
Severity trend: high

### Description
A permanently retired upstream API remained in the FastMCP registry and local adapter inventory, so an impossible capability continued to look discoverable and its permanent failure was misclassified as transient networking.

### Typical Symptoms
- A registered tool consistently fails against a provider-owned retired domain.
- Official sunset documentation contradicts local readiness claims.
- Tool counts remain stable only because dead capabilities are never removed.

### Common Triggers
- External API shutdowns after initial integration.
- Inventory checks that count decorators without probing business readiness.
- Generic request exception handling that cannot distinguish sunset from outage.

### Prevention Rule
Reconcile public registrations with official provider lifecycle changes; remove or explicitly disable permanently unavailable capabilities and preserve the decision in tests and audit history.

### Related Bugs
- BUG-0011

## RC-0012: Health Semantics Had No Authoritative Contract

Status: active
Category: API contract and derived state
First observed: BUG-0014
Recurring count: 1
Severity trend: high

### Description
Liveness, successful check execution, core business readiness, and optional capability availability were compressed into unrelated `healthy` or `ok` values maintained by separate entrypoints.

### Typical Symptoms
- One endpoint reports healthy while another reports false for the same runtime.
- A missing directory causes the check to disappear instead of reporting not ready.
- Optional services make the whole system look unavailable.
- A process liveness endpoint is mistaken for business readiness.

### Common Triggers
- Health endpoints implemented by separate modules without a shared snapshot.
- Constant status values attached to informational system metadata.
- Aggregate booleans derived only from checks that happened to be present.
- Required and optional dependencies represented with the same boolean.

### Prevention Rule
Use one authoritative readiness snapshot, distinguish execution from readiness, emit records for missing dependencies, mark checks as required or optional, and label liveness-only endpoints explicitly.

### Related Bugs
- BUG-0014

## RC-0013: Layered Persistence Was Collapsed Into One Boolean

Status: active
Category: storage state and API contract
First observed: BUG-0015
Recurring count: 1
Severity trend: high

### Description
A required SQLite write and optional TXT/HTML artifacts shared one success flag, while the optional-artifact request parameter was also used to describe all local persistence.

### Typical Symptoms
- A database file exists while the response says nothing was saved locally.
- Missing optional artifacts are hidden by a successful database write.
- An exception in one persistence layer overwrites the known outcome of another layer.

### Common Triggers
- Reusing one boolean across storage layers with different requirements.
- Naming an optional-artifact flag as if it controls the whole persistence operation.
- Building response notes from request intent instead of observed storage outcomes.

### Prevention Rule
Track each persistence layer independently, derive aggregate state from observed outcomes, and keep compatibility flags subordinate to explicit layer records.

### Related Bugs
- BUG-0015

## RC-0014: Worker Operation Retained A Process-Global SQLite Manager

Status: active
Category: storage lifecycle and concurrency
First observed: BUG-0016
Recurring count: 1
Severity trend: high

### Description
A short-lived FastMCP worker operation borrowed the process-global storage singleton, created a thread-affine SQLite connection, and left cleanup to destruction from another thread.

### Typical Symptoms
- A successful tool response is followed by a SQLite thread-affinity cleanup error.
- A later worker can inherit a connection created by a different worker.
- A project-scoped tool reads from a current-working-directory-relative output path.

### Common Triggers
- Calling a process singleton from `asyncio.to_thread` without an ownership contract.
- Opening SQLite during a read-only operation without deterministic cleanup.
- Treating destructor cleanup as a substitute for operation-scoped lifecycle management.

### Prevention Rule
Create project-bound storage for worker operations and close it in the same thread with `finally`; retain SQLite thread checks and use global managers only where one thread owns their full lifecycle.

### Related Bugs
- BUG-0016

## RC-0015: Independent Metrics Shared One Data-Eligibility Gate

Status: active
Category: derived analytics
First observed: BUG-0017
Recurring count: 1
Severity trend: medium

### Description
Peak and change-rate calculations were placed under the same two-point condition even though a peak is valid for one positive observation and a rate of change is not.

### Typical Symptoms
- Totals and detail rows contain positive observations while a derived peak is zero or absent.
- One-point analysis behaves differently from the equivalent first point in a longer series.

### Common Triggers
- Computing several summary metrics inside one length guard.
- Treating shared input data as proof that every metric has the same minimum sample size.

### Prevention Rule
Define and test the minimum-data requirement for each derived metric independently, including one-point and all-zero series.

### Related Bugs
- BUG-0017

## RC-0016: Undefined Ratios Were Collapsed Into Numeric Zero

Status: active
Category: derived analytics
First observed: BUG-0018
Recurring count: 1
Severity trend: medium

### Description
A zero denominator used numeric zero as a safety fallback, turning an undefined comparison percentage into a valid-looking `+0.0%`.

### Typical Symptoms
- A positive absolute change is paired with a zero relative change.
- Missing baselines are indistinguishable from genuinely unchanged values.

### Common Triggers
- Inline divide-by-zero fallbacks in display metric calculations.
- Formatting sentinel numbers before preserving their semantic meaning.

### Prevention Rule
Use an explicit unavailable value for undefined ratios and retain absolute differences so callers still receive truthful comparison information.

### Related Bugs
- BUG-0018

## RC-0017: The Idempotency Key Was Written After Its Side Effects

Status: active
Category: storage concurrency and idempotency
First observed: BUG-0019
Recurring count: 1
Severity trend: high

### Description
A unique crawl-time record was inserted or replaced only after news/RSS item mutations. Concurrent retries therefore duplicated counters and history before the late unique write collapsed only the visible crawl record.

### Typical Symptoms
- One crawl record exists for a minute while item counters or history rows show two runs.
- An autoincrement ID skips even though the unique-key table exposes one logical record.
- Concurrent workers both report successful persistence for the same operation key.

### Common Triggers
- Scheduled or manually retried work overlaps inside one crawl-time bucket.
- A final upsert is mistaken for transaction-wide idempotency.
- Side-effect tables do not share the operation key's uniqueness constraint.

### Prevention Rule
Claim the unique operation key transactionally before any dependent mutation, treat an existing claim as an idempotent no-op, and roll back the claim with all side effects on failure.

### Related Bugs
- BUG-0019

## RC-0018: A Rate-Limited Source Was Treated As An Unrestricted Endpoint

Status: active
Category: external API availability
First observed: BUG-0020
Recurring count: 1
Severity trend: high

### Description
The arXiv adapter issued every query directly without caching or pacing, despite the source documenting stable daily results and a minimum delay for consecutive calls. HTTP 429 was then collapsed into a generic network error.

### Typical Symptoms
- Repeating an identical public metadata query consumes another upstream request.
- Serial requests fail with the same limit previously attributed only to concurrency.
- A source limit is reported as `NETWORK_ERROR`, hiding retry guidance.

### Common Triggers
- Wrapping a public API with only `raise_for_status()`.
- Assuming no-key means unmetered or stateless.
- Implementing fallback aggregation without first respecting the owning source's usage contract.

### Prevention Rule
Before integrating a rate-limited source, encode its documented cache lifetime and request spacing at the adapter boundary, bound automatic retries, and expose persistent limits with source-specific metadata.

### Related Bugs
- BUG-0020

## RC-0019: Onboarding Examples Drifted From Executable Contracts

Status: active
Category: documentation contract and test gap
First observed: BUG-0021
Recurring count: 1
Severity trend: low

### Description
The quick-start command was maintained as prose without a process-level check against the installed argparse entrypoint, so an unsupported flag remained documented after the executable contract differed.

### Typical Symptoms
- A copy-pasted quick-start command exits during argument parsing.
- The library or in-process tests pass while an external MCP client path remains untested.
- Different language READMEs repeat the same stale invocation.

### Common Triggers
- Updating CLI behavior without scanning onboarding examples.
- Verifying FastMCP registrations only in process.
- Treating a running server process as proof of a successful MCP handshake.

### Prevention Rule
For documented CLI or MCP entrypoints, run the exact command or an equivalent process-level client handshake from outside the project working directory and scan all translated onboarding docs for the same contract.

### Related Bugs
- BUG-0021
