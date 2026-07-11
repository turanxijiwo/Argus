# Technical Debt Register

Record systemic issues that should not be mixed into unrelated bug fixes.

## Entry Format

```md
## DEBT-0001: Short Debt Title

Date: 2026-01-01
Status: open / in_progress / resolved / archived
Severity: low / medium / high / critical
Area:
Related bugs:
- Bug references
Related patterns:
- Pattern references

### Problem
Describe the debt.

### Why Not Fixed Now
Explain why this was not included in the current task.

### Risk
What may happen if this remains unresolved?

### Proposed Resolution
Describe a safe future task.

### Exit Criteria
How do we know this debt is resolved?
```

## Technical Debt

## DEBT-0001: Optional Runtime Health Is Package-Level

Date: 2026-07-10
Status: resolved
Severity: low
Area: Research Toolkit optional adapters
Related bugs:
- None
Related patterns:
- Optional runtime readiness

### Problem
`research_toolkit_health` reports the Codex source as ready when the
`openai-codex` package is importable, but a real SDK run can still fail while
loading incompatible user-level Codex configuration. The 2026-07-10 delivery
audit observed `model_reasoning_effort = "ultra"` being rejected by the
installed SDK parser, which accepts values through `xhigh`.

### Why Not Fixed Now
The incompatible value is in user-level Codex configuration outside Argus.
Argus must not silently rewrite global settings, and running a Codex thread as
part of every health check would be slow and stateful.

### Risk
Agents may interpret package availability as end-to-end Codex source readiness.

### Proposed Resolution
Implemented through `research_runtime_probe`, which performs explicit
verification and returns sanitized configuration or permission errors without
changing user state.

### Exit Criteria
- Health output distinguishes package detection from a successful runtime probe.
- The probe has deterministic tests for configuration failures and error sanitization.
- No global Codex configuration is modified by Argus.

## DEBT-0002: PDF-Native Page Boundaries Are Not Preserved

Date: 2026-07-11
Status: open
Severity: medium
Area: Research comparison evidence locators
Related bugs:
- None
Related patterns:
- Evidence traceability

### Problem
Jina Reader markdown can preserve headings and report a document's total page count without emitting a marker for each source PDF page. Argus can therefore guarantee saved-artifact document/character locators and often section/paragraph context, but cannot always map those ranges back to original PDF page numbers.

### Why Not Fixed Now
The current project has no PDF-native extraction dependency or adapter that preserves page boundaries. Adding one would be a separate dependency and ingestion-path decision rather than a safe extension of the saved-artifact comparison contract.

### Risk
Users may expect a publication citation to include a PDF page even when the extracted artifact does not contain enough information to prove it.

### Proposed Resolution
Add an optional PDF-native extraction adapter that records page boundaries during resource reading, then propagate verified page numbers into the existing locator schema.

### Exit Criteria
- PDF artifacts retain page-boundary metadata during ingestion.
- Every emitted page locator is reproducible against the original PDF.
- Section/paragraph/character fallback remains available for HTML and page-less text.

## DEBT-0003: Locator Replay Does Not Bind Source Content

Date: 2026-07-11
Status: open
Severity: medium
Area: Research comparison evidence integrity
Related bugs:
- None
Related patterns:
- Evidence traceability

### Problem
Comparison locators store source artifact paths plus document and character coordinates, but no source-content digest. The resolver detects missing text and invalid ranges, yet cannot detect an in-place source edit when the coordinates remain valid.

### Why Not Fixed Now
Adding fingerprints changes the comparison artifact contract and needs a compatibility policy for existing saved comparisons. The bounded replay tool can be useful safely without mixing that schema migration into its first release.

### Risk
A source artifact edited after comparison could return different text for the same locator while still passing coordinate validation.

### Proposed Resolution
Store deterministic document or selected-input SHA-256 fingerprints on new comparison sources and verify them during locator replay. Preserve read compatibility for older artifacts while clearly reporting that their content integrity is unverified.

### Exit Criteria
- New comparison artifacts include deterministic source-content fingerprints.
- Locator replay rejects fingerprint mismatches with a stable structured error.
- Existing comparison artifacts remain readable and explicitly report missing integrity metadata.
