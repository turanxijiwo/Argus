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
`research_compare_artifacts` consumes 2–6 project-local saved JSON artifacts, gives each source a stable `S1...Sn` ID and each bounded evidence unit a stable `S1:L1` locator, runs Codex in the existing ephemeral read-only deny-all boundary, and rejects missing, unknown, or source-mismatched IDs. Locators resolve to saved artifact document/character coordinates and retain section/page metadata only when explicitly extractable. Every document prefix actually passed to comparison receives a `comparison_input_v1` SHA-256 fingerprint, and verified locator ranges must end inside that fingerprint's `text_chars` scope. Existing normalized identifiers generate DOI/arXiv/ISBN metadata plus BibTeX, CSL-JSON, and RIS without inventing missing fields; `save=True, save_citations=True` also writes project-local CSL-JSON/RIS files and adds relative handoff paths. `research_comparison_artifact.py` owns project-local comparison/source loading and source/locator indexing for both consumers. `research_audit_comparison` validates every unique locator actually used by saved comparison claims and returns only compact per-source status and issues, never evidence text. `research_resolve_locators` accepts one saved comparison and at most 10 locator IDs, revalidates the same source/document/range/fingerprint metadata, and returns excerpts capped at 240 characters and 25 words each. Comparisons without fingerprints remain readable but explicitly unverified. Comparison output uses `argus.research.comparison.handoff.v1`, including integrity-audit readiness fields.

Consequences:
Comparisons remain compact at the MCP boundary and cannot silently invent source or locator IDs. Agents can audit all used evidence coordinates without receiving source text, then explicitly request only a small amount of cited evidence when needed. A successful audit operation can still report `status=failed` when integrity issues are found; legacy artifacts report `unverified`. Fingerprints prove consistency with saved comparison input, not truth; PDF-native page boundaries and independent fact verification remain separate future capabilities.

Alternatives Considered:
Re-crawling every source during comparison was rejected because it adds network drift and repeats access work. Returning full source text with comparison or locator responses was rejected because it defeats compact handoff boundaries. Treating free-form model citations as valid was rejected because it weakens traceability. Reusing the workflow handoff schema was rejected because comparison claim/citation counts have different readiness semantics.

Supersedes:
None.

Superseded By:
None.

Related Bugs / Rules:
- BUG-0004
- BUG-0007
- BUG-0008
- BUG-0009

## ADR-0002: Prefer Openverse Audio For The Next No-Key Media Adapter

Date: 2026-07-13
Status: active
Area: Research Toolkit external media adapters

Context:
Argus needs a maintained no-key media source that fits its agent-native research workflows without adding dependencies, downloading media, using browser credentials, or weakening license and access controls. Openverse audio, Internet Archive metadata, `yt-dlp`, and official course catalogs were evaluated against the existing Openverse image and resource-discovery contracts.

Decision:
Implement a metadata-only `audio:openverse` adapter before other media candidates. Use only the documented API, preserve anonymous rate-limit metadata, require independent license verification, exclude mature or malformed results, and do not fetch media bytes, waveforms, alternate files, transcripts, or lyrics. Defer Internet Archive to a later broad-media metadata adapter with explicit User-Agent, access-state, and optional-license handling. Keep `yt-dlp` optional for user-supplied public URL metadata, not search, and do not use cookies, authentication bypasses, geography bypasses, downloads, subtitles, or execution hooks by default. Keep course discovery on official-page search until a documented consumer API contract is confirmed.

Consequences:
The next adapter reuses a proven provider, error model, attribution warning, and no-download posture while adding a genuinely new media type. Anonymous limits and third-party license accuracy remain external risks. Internet Archive and `yt-dlp` remain useful later but need different contracts and should not be mixed into the first audio change.

Alternatives Considered:
Internet Archive was not selected first because search metadata does not by itself prove open file access or reusable rights. `yt-dlp` was not selected as a search source because it is URL-driven, site-specific, and increasingly depends on extra JavaScript runtime support for YouTube. A dedicated course API was deferred because the reviewed official course materials did not establish a stable external no-key search contract.

Supersedes:
None.

Superseded By:
None.

Related Bugs / Rules:
None.
