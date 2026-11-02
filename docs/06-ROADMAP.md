# Roadmap

## Milestone 1 — Image foundation

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

Goal: strengthen origin and history analysis.

Scope:

- C2PA validation
- Provenance report
- Chain-of-custody view
- Derived-file relationship tracking

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