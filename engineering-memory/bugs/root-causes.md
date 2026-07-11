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
