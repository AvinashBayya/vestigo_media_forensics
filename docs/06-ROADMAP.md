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

Goal: add permission-gated external lookups.

Scope:

- Provider registry
- Permission gates
- Licence and terms tracking
- Result normalization
- Evidence recording
- Analyst review workflow

## Milestone 6 — GEOINT / geo-lite

Goal: add location-context analysis without overclaiming.

Scope:

- EXIF GPS extraction
- Coordinate validation
- Map preview
- Reverse geocoding
- Terrain and landmark clues
- Analyst confidence labels

## Milestone 7 — Vestigo integration

Goal: connect to Vestigo through a versioned evidence API.

Scope:

- Evidence API
- Case linking
- Import/export
- Permission-aware integration
- No direct database writes