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
