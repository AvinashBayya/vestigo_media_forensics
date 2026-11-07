# Roadmap

## Milestone 1 — Image foundation

**Status: complete** (approved plan `11-BUILD-PLAN.md`).

Goal: reliable local image-analysis API and minimal UI.

Scope:

- Image upload
- SHA-256 and MD5 hashing
- EXIF, XMP, and IPTC metadata extraction
- C2PA / Content Credentials detection
- Perceptual hash generation
- OCR
- Local duplicate search
- JSON evidence output
- Minimal upload-and-review UI
- Health check
- Core tests

FFmpeg and ffprobe are installed and verified during setup but are not invoked in Milestone 1.

## Milestone 2 — Analyst workflow

**Status: complete** (approved plan `12-MILESTONE-2-PLAN.md`, decisions D15–D16).

Goal: make evidence easier to review and manage.

Scope:

- Artifact list
- Search and filter
- Review states
- Analyst notes
- Evidence export
- Duplicate-library management
- Error surfacing
- Basic settings

## Milestone 3 — Video foundation

**Status: complete**, closed 2026-11-06 after a documentation reconciliation pass (approved plan
`13-MILESTONE-3-PLAN.md`, decisions D17–D18), including the approved D19 additions: rotated and
mirrored duplicate matching, the AVI/MPEG-TS/WMV/FLV/3GP/M4V containers, audio artifacts with
byte-identical duplicate search, and on-demand playable previews.

Goal: add responsible video analysis.

Scope:

- Video upload
- ffprobe metadata
- Container and stream inspection
- Keyframe extraction
- Scene-change detection
- Audio metadata inspection
- Video evidence report

## Milestone 4 — Provenance

**Status: complete** (2026-11-06, decisions D20 and D21). C2PA validation and provenance evidence
first (D20), then the chain-of-custody view and derived-file relationship tracking (D21, approved
plan `14-MILESTONE-4B-PLAN.md`): an append-only custody_events table, derived-file lineage columns,
the merged custody timeline API, custody.json in the export package, and the Chain of custody panel.

Goal: strengthen origin and history analysis.

Scope:

- C2PA validation — **done** (D20)
- Provenance report — **done** (D20; the evidence report's C2PA section)
- Chain-of-custody view — **done** (D21)
- Derived-file relationship tracking — **done** (D21)

## Milestone 5 — Reverse-image search

**Status: complete** (2026-11-07, decision D22, approved plan `15-MILESTONE-5-PLAN.md`), as a
manual-first workflow: Vestigo never transmits media — it opens plain provider landing pages,
serves the subject file for a manual upload, and records what the analyst found as custody-trailed
EXTERNAL leads.

Goal: add permission-gated external lookups.

Scope:

- Provider registry — **done** (static registry: Google Lens, Bing Visual Search, TinEye, Yandex Images)
- Permission gates — **done** (per-provider Settings toggles, all disabled by default)
- Licence and terms tracking — **done** (each provider's terms linked in Settings and the panel)
- Result normalization — **done** as analyst-recorded leads with fixed fields, stored as entered
- Evidence recording — **done** (EXTERNAL leads in the report, export, custody, and deletion)
- Analyst review workflow — **done** (lightweight per-lead review state)

Paid or official provider API integrations were explicitly deferred: each needs its own approval.

## Milestone 6 — GEOINT / geo-lite

**Status: complete** (2026-11-07, decision D23, approved plan `16-MILESTONE-6-PLAN.md`): machine
location *clues* read as written, analyst location candidates classified UNVERIFIED with their own
assessment labels, and one opt-in OpenStreetMap link built client-side. No stage claims a location.

Goal: add location-context analysis without overclaiming.

Scope:

- EXIF GPS extraction — **done** (plus XMP/IPTC place tags and container ISO 6709 locations)
- Coordinate validation — **done** (ranges checked per value; invalid values flagged, never corrected)
- Map preview — **done** as an opt-in external link, off by default, built in the browser; no tiles,
  no embedded map, no API key
- Reverse geocoding — **not enabled** (an external lookup service; needs its own approval)
- Terrain and landmark clues — **not started** (terrain analysis is explicitly out of scope; visible
  landmarks are for the analyst to read in the OCR evidence and record as a candidate's basis)
- Analyst confidence labels — **done** as analyst assessments (speculative / possible / likely),
  always the analyst's own judgment and never machine-derived

## Milestone 7 — Vestigo integration

Goal: connect to Vestigo through a versioned evidence API.

Scope:

- Evidence API
- Case linking
- Import/export
- Permission-aware integration
- No direct database writes