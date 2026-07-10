# Research Workflow Examples

This guide shows repeatable MCP prompts for `research_workflow` and
`research_batch_workflow`. The examples focus on personal, non-commercial
research, keep all saved artifacts inside the Argus project directory, and do
not require commercial search-provider keys when using the `codex` source.

## Codex Source Workflow

Use this prompt in an MCP client connected to Argus:

```text
Use Argus research_workflow to research "AI agent browser automation safety".
Use only the codex source. Crawl at most 2 pages. Keep each page to 3000
characters. Keep up to 3 images per page. Include a Markdown brief. Save both
the JSON packet and Markdown brief under output/research/codex.
```

Equivalent tool arguments:

```json
{
  "query": "AI agent browser automation safety",
  "sources": ["codex"],
  "limit": 2,
  "timeout": 20,
  "max_chars_per_page": 3000,
  "images_per_page": 3,
  "render_js": false,
  "retries": 1,
  "include_brief": true,
  "save": true,
  "save_brief": true,
  "output_dir": "output/research/codex"
}
```

Expected result fields to inspect:

- `success`: `true` means the workflow completed. Individual source or page
  failures may still be recorded in the payload.
- `summary.document_count`: number of page candidates processed.
- `summary.crawl_error_count`: number of failed page crawls.
- `summary.image_count`: number of image candidates retained.
- `summary.brief_included`: whether `data.brief.content` is present.
- `summary.saved` and `summary.brief_saved`: whether JSON and Markdown files
  were written.
- `data.artifact.path`: saved JSON packet path.
- `data.brief.artifact.path`: saved Markdown brief path.
- `data.source_errors`: source-level failures, including Codex SDK or parsing
  errors.
- `data.documents[].error`: page-level crawl failures.

Every single workflow also returns a compact `data.handoff` block:

```json
{
  "schema": "argus.research.workflow.handoff.v1",
  "entrypoint": "mcp",
  "ready": true,
  "status": "ready",
  "query": "OpenAI",
  "artifact_path": "output/research/public/research-OpenAI-YYYYMMDDTHHMMSSZ.json",
  "brief_path": "output/research/public/research-OpenAI-YYYYMMDDTHHMMSSZ.md",
  "document_count": 1,
  "successful_document_count": 1,
  "crawl_error_count": 0,
  "source_error_count": 0,
  "image_count": 3,
  "output_dir": "output/research/public"
}
```

Use `artifact_path` first when handing the result to a later agent, then read
`brief_path` for the concise narrative. `ready` is true only when the JSON
artifact exists, at least one document succeeded, and no source or page errors
are present. Paths are project-relative and are `null` when the workflow was
run without saving artifacts.

The `research_review_artifact` tool accepts either `artifact_path` or the
previous workflow's `data.handoff` object. Its response uses the same compact
quality fields as batch review and includes a new
`argus.research.review.handoff.v1` block for the next agent step.

It also accepts a batch `handoff`; use `artifact_index` to select one entry
from `artifact_paths` (the first saved artifact is index `0`).

`scripts/research_artifact_smoke.py` also verifies this direct workflow-to-review
handoff chain against the public Wikipedia source without a provider key.

Saved file names use this shape:

```text
output/research/codex/research-AI-agent-browser-automation-safety-YYYYMMDDTHHMMSSZ.json
output/research/codex/research-AI-agent-browser-automation-safety-YYYYMMDDTHHMMSSZ.md
```

## Public Source Workflow

Use this prompt when you want a key-free public-source workflow without Codex
SDK runtime state:

```text
Use Argus research_workflow to research "OpenAI". Use the wikipedia source.
Crawl 1 page, include a Markdown brief, and save JSON plus Markdown artifacts
under output/research/public.
```

Equivalent tool arguments:

```json
{
  "query": "OpenAI",
  "sources": ["wikipedia"],
  "limit": 1,
  "timeout": 20,
  "max_chars_per_page": 3000,
  "images_per_page": 3,
  "render_js": false,
  "retries": 1,
  "include_brief": true,
  "save": true,
  "save_brief": true,
  "output_dir": "output/research/public"
}
```

## Optional Provider Workflow

Use this only after configuring one provider key such as `TAVILY_API_KEY`,
`EXA_API_KEY`, `PERPLEXITY_API_KEY`, or `BRAVE_API_KEY`:

```text
Use Argus research_workflow to research "open source web research agents".
Use web:tavily. Crawl at most 2 pages. Save JSON and Markdown artifacts under
output/research/provider.
```

Equivalent tool arguments:

```json
{
  "query": "open source web research agents",
  "sources": ["web:tavily"],
  "limit": 2,
  "timeout": 20,
  "max_chars_per_page": 3000,
  "images_per_page": 3,
  "render_js": false,
  "retries": 1,
  "include_brief": true,
  "save": true,
  "save_brief": true,
  "output_dir": "output/research/provider"
}
```

## Safety Notes

- Keep `output_dir` under the project root. Absolute paths outside Argus return
  `UNSAFE_OUTPUT_DIR` before search or crawl work begins.
- Leave `render_js=false` unless Crawl4AI is installed and the session has
  permission to use its browser/runtime cache.
- `sources=["codex"]` may require approved unsandboxed execution in Codex
  sessions because the local Codex SDK writes user-level state under `~/.codex`.
- `research_workflow` preserves partial failures. Check `source_errors` and
  `documents[].error` before trusting the brief.
- The workflow records evidence snippets and links. It should not be used to
  copy full copyrighted articles or bypass authenticated website access.

## Artifact Quality Smoke

Use this smoke when changing artifact export, Markdown rendering, or handoff
docs:

```bash
uv run python scripts/research_artifact_smoke.py
```

The default command runs `research_workflow` with `sources=["wikipedia"]`,
`save=True`, and `save_brief=True`, then validates:

- JSON and Markdown artifact metadata exists.
- Saved paths stay inside the Argus project directory.
- JSON can be parsed and contains query, sources, documents, a successful
  document, and brief content.
- Markdown has frontmatter, `type: argus-research-brief`, a research title, key
  sources, minimum readable length, and the Argus generated marker.

Default saved artifacts go under `output/research/artifact-smoke/`, which is a
runtime output directory ignored by git.

Exit codes:

- `0`: JSON and Markdown artifact checks passed.
- `2`: Research Toolkit import/runtime was unavailable.
- `3`: the workflow ran but saved artifact quality checks failed.

Current local result:

- `scripts/research_artifact_smoke.py` returned exit code `0`.
- Saved JSON and Markdown artifacts were written under
  `output/research/artifact-smoke/`.
- The saved JSON was parseable, stayed project-local, and contained one
  successful document.
- The saved Markdown brief included frontmatter, key sources, and the Argus
  generated marker.

## Artifact Review Report

Use this report when you have one or more saved JSON artifacts and want a quick
quality/readability summary without re-running crawls:

```bash
uv run python scripts/research_artifact_review.py --format markdown --write-report output/research/artifact-reviews/latest-review.md
```

By default the review scans the latest saved JSON files under `output/research/`.
You can also review explicit artifacts:

```bash
uv run python scripts/research_artifact_review.py --artifact output/research/artifact-smoke/research-OpenAI-YYYYMMDDTHHMMSSZ.json
```

The report summarizes:

- `ready` / `partial` / `needs_attention` / `unreadable` quality status.
- A 0-100 score based on successful documents, source/page errors, brief length,
  available evidence text, and source metadata.
- Warnings such as `source_errors_present`, `page_errors_present`,
  `missing_brief`, `short_brief`, or `low_evidence_text`.
- Key source titles, URLs, text length, link count, and image count.
- Source and page error summaries without printing full page text.

Exit codes:

- `0`: report generated and all reviewed JSON artifacts were readable.
- `2`: no artifacts were found or the review input was unavailable.
- `3`: at least one reviewed artifact was unreadable, or report writing failed.

Current local result:

- `scripts/research_artifact_review.py --format markdown --write-report output/research/artifact-reviews/latest-review.md` returned exit code `0`.
- The generated report reviewed one artifact with average score `100.0`, status
  `ready`, and no warnings.

## Batch Workflow And Review

Use this prompt in an MCP client when you want Argus itself to batch several
saved workflows and return a compact handoff:

```text
Use Argus research_batch_workflow for "OpenAI" and "AI safety". Use only the
wikipedia source. Crawl 1 page per query, save artifacts under
output/research/batch, and write the batch review report to
output/research/artifact-reviews/batch-review.md.
```

Equivalent tool arguments:

```json
{
  "queries": ["OpenAI", "AI safety"],
  "sources": ["wikipedia"],
  "limit": 1,
  "timeout": 20,
  "max_chars_per_page": 1500,
  "images_per_page": 5,
  "render_js": false,
  "retries": 1,
  "output_dir": "output/research/batch",
  "report_path": "output/research/artifact-reviews/batch-review.md"
}
```

The MCP response includes per-query counts, quality status, project-relative
artifact paths, review status counts, and the report path. It does not return
full crawled page text, so it is safer to hand off between agent steps.

Both the MCP tool and the standalone script include a compact `handoff` block:

```json
{
  "schema": "argus.research.batch.handoff.v1",
  "entrypoint": "mcp",
  "ready": true,
  "query_count": 2,
  "successful_workflow_count": 2,
  "failed_workflow_count": 0,
  "artifact_count": 2,
  "artifact_paths": ["output/research/batch/research-OpenAI-YYYYMMDDTHHMMSSZ.json"],
  "brief_paths": ["output/research/batch/research-OpenAI-YYYYMMDDTHHMMSSZ.md"],
  "review_report": "output/research/artifact-reviews/batch-review.md",
  "status_counts": {"ready": 2},
  "average_score": 100.0,
  "output_dir": "output/research/batch",
  "exit_code": null
}
```

For MCP responses, `exit_code` is `null`; for the standalone script, it is the
actual process exit code. The shared handoff block is the preferred field for
chaining follow-up review steps because it contains no full crawled page text.

The standalone script remains useful from a terminal. Use this command when you
want one local run to execute saved research workflows and then produce a review
report:

```bash
uv run python scripts/research_batch_workflow.py --query "OpenAI" --query "AI safety"
```

The default source is `wikipedia`, so the command does not require commercial
provider keys or Codex SDK state. Saved artifacts go under
`output/research/batch/`, and the Markdown review report is written to
`output/research/artifact-reviews/batch-review.md`.

For a reusable query list:

```text
OpenAI
AI safety
browser automation agents
```

Run:

```bash
uv run python scripts/research_batch_workflow.py --queries-file queries.txt
```

The batch summary reports:

- Per-query artifact and Markdown brief paths.
- Per-query document, image, source-error, and crawl-error counts.
- Review status counts and average score.
- Review report write status.

All artifact paths in the printed summary are project-relative, so the handoff
output does not expose local machine paths.

Exit codes:

- `0`: all workflows succeeded, artifacts were readable, and the review report
  was written.
- `2`: Research Toolkit import/runtime was unavailable.
- `3`: query input, workflow, artifact review, or report writing failed.

Current local result:

- MCP `research_batch_workflow` with `queries=["OpenAI", "AI safety"]` and
  `sources=["wikipedia"]` returned success, wrote
  `output/research/artifact-reviews/batch-review.md`, returned
  `handoff.schema == "argus.research.batch.handoff.v1"`, and scored both
  artifacts `ready` with average score `100.0`.
- `scripts/research_batch_workflow.py --query "OpenAI" --query "AI safety"` returned exit code `0`.
- Two JSON artifacts and two Markdown briefs were saved under
  `output/research/batch/`.
- The generated review report scored both artifacts `ready` with average score
  `100.0`.
