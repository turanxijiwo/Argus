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
