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
