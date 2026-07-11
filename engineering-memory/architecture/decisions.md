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
Multi-resource comparison needs traceability and citation exchange without re-crawling sources, replaying full document text through MCP, or presenting model-generated citations as independently verified facts.

Decision:
`research_compare_artifacts` consumes 2–6 project-local saved JSON artifacts, gives each source a stable `S1...Sn` ID and each bounded evidence unit a stable `S1:L1` locator, runs Codex in the existing ephemeral read-only deny-all boundary, and rejects missing, unknown, or source-mismatched IDs. Locators resolve to saved artifact document/character coordinates and retain section/page metadata only when explicitly extractable. Existing normalized identifiers generate DOI/arXiv/ISBN metadata plus BibTeX, CSL-JSON, and RIS without inventing missing fields. `research_resolve_locators` accepts one saved comparison and at most 10 locator IDs, rereads only referenced project-local source artifacts, revalidates source/document/range metadata, and returns excerpts capped at 240 characters and 25 words each. Comparison output uses `argus.research.comparison.handoff.v1`.

Consequences:
Comparisons remain compact at the MCP boundary and cannot silently invent source or locator IDs. Agents can explicitly request a small amount of cited evidence and import references without receiving full artifacts. Locator metadata exposes coordinates by default, while replay is separately bounded and key-free. Source-content fingerprints, PDF-native page boundaries, and independent fact verification remain separate future capabilities.

Alternatives Considered:
Re-crawling every source during comparison was rejected because it adds network drift and repeats access work. Returning full source text with comparison or locator responses was rejected because it defeats compact handoff boundaries. Treating free-form model citations as valid was rejected because it weakens traceability. Reusing the workflow handoff schema was rejected because comparison claim/citation counts have different readiness semantics.

Supersedes:
None.

Superseded By:
None.

Related Bugs / Rules:
- BUG-0004
- BUG-0007
