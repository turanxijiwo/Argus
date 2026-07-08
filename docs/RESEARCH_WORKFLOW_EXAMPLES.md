# Research Workflow Examples

This guide shows repeatable MCP prompts for `research_workflow`. The examples
focus on personal, non-commercial research, keep all saved artifacts inside the
Argus project directory, and do not require commercial search-provider keys when
using the `codex` source.

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
