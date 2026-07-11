# Architecture Decisions

Record real architecture decisions only. Do not keep placeholder ADRs as if they were project history.

## Entry Format

```md
## ADR-0001: Short Decision Title

Date: 2026-01-01
Status: active | superseded | deprecated | archived
Area: module-or-system-area

Context:
Decision:
Consequences:
Alternatives Considered:
Supersedes:
Superseded By:
Related Bugs / Rules:
```

## Active Decisions

## ADR-0001: Compare Saved Artifacts With Structurally Validated Source IDs

Date: 2026-07-11
Status: active
Area: Research Toolkit comparison workflow

Context:
Multi-resource comparison needs traceability without re-crawling sources, replaying full document text through MCP, or presenting model-generated citations as independently verified facts.

Decision:
`research_compare_artifacts` consumes 2–6 project-local saved JSON artifacts, gives each source a stable `S1...Sn` ID, runs Codex in the existing ephemeral read-only deny-all boundary, and rejects missing or unknown source IDs. Comparison output uses a dedicated `argus.research.comparison.handoff.v1` schema. Citation validation is explicitly source-level and structural.

Consequences:
Comparisons are reproducible from saved inputs, compact at the MCP boundary, and cannot silently invent source IDs. Fine-grained page/paragraph locators and independent fact verification remain separate future capabilities.

Alternatives Considered:
Re-crawling every source during comparison was rejected because it adds network drift and repeats access work. Treating free-form model citations as valid was rejected because it weakens traceability. Reusing the workflow handoff schema was rejected because comparison claim/citation counts have different readiness semantics.

Supersedes:
None.

Superseded By:
None.

Related Bugs / Rules:
- BUG-0004
