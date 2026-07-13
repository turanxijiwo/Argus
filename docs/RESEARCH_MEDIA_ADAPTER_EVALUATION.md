# Research Media Adapter Evaluation

Date: 2026-07-13

## Scope

Choose the next maintained, no-API-key media or course adapter for Argus. This
evaluation does not add dependencies, product code, downloads, authenticated
access, or a new MCP tool.

## Decision

Implement Openverse audio search next, using the source name
`audio:openverse`. Keep it metadata-only and no-download by default.

Defer Internet Archive to a later broad-media metadata source. Keep `yt-dlp`
as an optional known-URL metadata adapter rather than a search backend. Keep
course discovery on the current official-page Codex path until a documented,
stable consumer API is confirmed.

## Evidence

### Openverse audio

Official evidence:

- The [Openverse API](https://api.openverse.org/) exposes anonymous
  `GET /v1/audio/` search with query, source, license, category, length, and
  mature-content filters.
- Openverse documents images and audio as its available public media types in
  [Made with Openverse](https://docs.openverse.org/api/reference/made_with_ov.html).
- The [Openverse terms](https://docs.openverse.org/terms_of_service.html)
  require rate-limit compliance, prohibit catalog scraping and limit bypass,
  require applicable attribution, and state that license metadata must be
  independently verified.

Real anonymous probe on 2026-07-13:

- Query: `birdsong`, `page_size=2`, `mature=false`.
- HTTP 200 with 240 reported matches.
- Both sampled results included a direct preview URL, source landing page,
  creator, provider, license, license URL, attribution, duration, file type,
  file size, and `mature=false`.
- Observed limits were 20 requests/minute and 200 requests/day. These values
  are runtime observations, not constants; Argus must preserve response
  headers and handle `429` plus `Retry-After`.

Fit with Argus:

- Reuses the existing Openverse image safety and license contract.
- Uses the existing `requests` dependency and research session.
- Provides topic search rather than requiring a known URL.
- Needs no account, browser session, API key, media download, or new package.

### Internet Archive

Official evidence:

- The [developer portal](https://archive.org/developers/) covers public item
  and file metadata for texts, audio, video, images, software, and other media.
- The [Advanced Search](https://archive.org/advancedsearch.php) surface returns
  JSON and can select fields such as `identifier`, `title`, `creator`,
  `licenseurl`, and `mediatype`.
- The [Item Metadata API](https://archive.org/developers/md-read.html) returns
  item and file metadata from `GET /metadata/{identifier}`.
- The [automated access guide](https://archive.org/developers/bots.html)
  requires a descriptive User-Agent, honoring `429` and `Retry-After`, delays
  for bulk work, caching, and bounded concurrency.

Real probe on 2026-07-13:

- Advanced search for `title:(birdsong) AND mediatype:(audio)` returned HTTP
  200, 274 matches, and the requested metadata fields.
- The two sampled items included `licenseurl`, but the public schema permits
  optional and uploader-defined metadata. Search success alone therefore does
  not prove open file access or reusable rights.

Decision:

- Good later source for broad media discovery and metadata enrichment.
- Requires a two-step search and item-metadata flow, explicit User-Agent,
  access-state normalization, and license/access warnings before it can feed a
  download or reading workflow safely.

### yt-dlp

Official evidence:

- The [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
  supports `--simulate` and JSON metadata output without downloading media.
- The project has active 2026 releases in its
  [release history](https://github.com/yt-dlp/yt-dlp/releases).
- The [external JavaScript guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
  documents the runtime now needed for reliable YouTube extraction.

Real local probes on 2026-07-13:

- Installed version: `2026.07.04`.
- The historical yt-dlp test video was unavailable.
- A public MIT OpenCourseWare YouTube URL returned title, duration, ID, and
  canonical URL in simulation mode without downloading media.
- The same successful probe warned that no supported JavaScript runtime was
  available and that YouTube extraction without one is deprecated.

Decision:

- Keep as an optional extractor for a user-supplied public URL.
- Do not treat it as a general search source.
- Do not read browser cookies, bypass authentication or geography, download
  media/subtitles, or enable execution hooks by default.

### Course discovery

[MIT OpenCourseWare](https://ocw.mit.edu/pages/get-started/) provides more than
2,500 freely browsable courses and an official
[search page](https://ocw.mit.edu/search/). The official materials reviewed for
this decision did not expose a documented external consumer API contract for
course search. This is an inference from the reviewed sources, not proof that
no internal endpoint exists.

Decision:

- Keep current Codex-backed official-page discovery.
- Do not bind Argus to an undocumented site-internal search endpoint.
- Reassess MIT Learn or another course catalog only when its public access,
  authentication, rate limits, and response contract are officially documented.

## Openverse Audio Contract

The first implementation should:

- Query only the documented Openverse API endpoint.
- Request `mature=false`, cap results, and avoid deep pagination.
- Return metadata only: title, preview URL, landing page, creator, provider,
  license, license URL, attribution, duration, file type, file size, and rank.
- Mark every result `license_verification_required=true`.
- Preserve the existing Openverse provider and license notices.
- Preserve anonymous rate-limit metadata and source-scoped timeout, network,
  HTTP, invalid-response, and rate-limit errors.
- Skip malformed, mature, or non-HTTP candidates and deduplicate URLs.
- Never fetch waveform, alternate files, audio bytes, transcripts, or lyrics.

## Delivery Slices

1. Add the focused `audio:openverse` adapter and normal/error contract tests
   without changing the public MCP surface.
2. Expose a `research_audio` MCP tool in a separate public-surface task, then
   update health, registration count, inventories, examples, and smoke tests.
3. Consider Internet Archive metadata-only discovery after the Openverse audio
   contract is stable.
4. Consider `yt-dlp` known-URL metadata enrichment only after runtime health and
   no-cookie/no-download boundaries have dedicated tests.
