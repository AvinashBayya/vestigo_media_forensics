# Vestigo Media Forensics — Master Build Spec

This is the entry point to the docs. Detailed requirements live in docs 01–10; the approved Milestone 1 plan is
`11-BUILD-PLAN.md`; the approved Milestone 2 and 3 plans are `12-MILESTONE-2-PLAN.md` and
`13-MILESTONE-3-PLAN.md`. If this file and docs
01–10 ever disagree, docs 01–10 win.

## 1. Project Goal

Build a local-first media provenance and verification web app that:

- Accepts images (Milestone 1), videos (Milestone 3), and audio files (D19).
- Runs automated, explainable checks and extracts technical evidence.
- Shows the method, tool, version, timestamp, source, limitations, and review state behind every result.
- Leaves conclusions to a human analyst.
- Keeps all data local (SQLite + local files).
- Runs fully inside a Docker Dev Container.

The system reports observable signals. It does **not** determine whether media is authentic, real, fake, or
deceptive (see D2 in `09-DECISIONS.md`).

## 2. Tech Stack

- Backend: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy, SQLite.
- Frontend: React + Vite + TypeScript + Tailwind.
- OCR: Tesseract.
- Metadata and C2PA detection: ExifTool.
- C2PA validation (Milestone 4, D20): c2pa-python 0.38.1 (c2pa-rs SDK 0.91.3), entirely local.
- Video (Milestone 3): ffmpeg / ffprobe for media information, scene detection, keyframes, and
  on-demand playable previews (D19).
- Audio (D19): the same ffprobe / ExifTool toolchain, header-level inspection only — audio is never
  decoded, transcribed, or identified.
- Storage: local filesystem under `data/`.
- DB: SQLite file at `data/app.db`.
- Configuration via `.env` (`VESTIGO_*`); no hardcoded secrets.

## 3. Core Principles

- Evidence over verdicts: report signals, never a truth claim.
- Explainable: every result carries its method, tool, and limitations.
- Human review: only an analyst marks evidence as reviewed.
- Modular: each check is a separate pipeline stage.
- Extensible: new checks can be added without breaking old ones.
- Local-first: no external API calls in the core flow.

## 4. High-Level Architecture

- FastAPI backend on port 8400.
- React frontend on port 5180.
- SQLite DB for artifacts, analysis jobs, and evidence records.
- Local file storage for uploaded media and derived files.
- Pipeline engine that runs stages per media type.

See `02-ARCHITECTURE.md`.

## 5. Users

Milestone 1 is a single-user local tool with no login. The primary user is an OSINT analyst
(see `01-PRODUCT-SPEC.md`). Multi-user authentication is not in Milestone 1.

## 6. Core Entities

- Artifact: an uploaded media file, with hashes, storage path, and review state.
- AnalysisJob: one run of a pipeline against an artifact.
- EvidenceRecord: one stage's observable or derived result, with method, tool, tool version, timestamps,
  source, limitations, errors, classification, and review state.

See `04-EVIDENCE-MODEL.md`.

## 7. Evidence Model (no verdicts)

- Each evidence record has a classification describing where it came from: `OBSERVED`, `DERIVED`, `EXTERNAL`,
  `UNVERIFIED`, or `REVIEWED`. Classification does not change after the record is created.
- Review state (`UNREVIEWED`, `IN_REVIEW`, `REVIEWED`, `FLAGGED`, `ARCHIVED`) is set only by a human analyst.
- There is no REAL / SUSPICIOUS / FAKE / UNKNOWN verdict and no overall confidence score.
- Tool failures are recorded and shown, never hidden.

## 8. Image Pipeline (Milestone 1)

- SHA-256 and MD5 hashing.
- EXIF, XMP, and IPTC metadata extraction.
- C2PA / Content Credentials detection and local validation (validation since Milestone 4, D20).
- Perceptual hash (pHash).
- OCR (English).
- Local duplicate / near-duplicate search.

Output: a structured JSON evidence report. See `11-BUILD-PLAN.md` §6.

## 9. Milestone status

Implemented (see `06-ROADMAP.md` and `09-DECISIONS.md` for the approved details):

- **Milestone 1 — Image foundation** (`image.v1`: hashes, metadata, C2PA detection, pHash, OCR,
  duplicate search). Plan: `11-BUILD-PLAN.md`.
- **Milestone 2 — Analyst workflow** (Library, review workflow and history, evidence export package,
  duplicate-library management, settings, Alembic migrations). Plan: `12-MILESTONE-2-PLAN.md`,
  decisions D15–D16.
- **Milestone 3 — Video foundation** (`video.v1`: hashes, ffprobe media info, metadata, scene
  detection, keyframes, keyframe pHash, optional keyframe OCR, cross-media duplicate search). Plan:
  `13-MILESTONE-3-PLAN.md`, decisions D17–D18.
- **D19 additions**: rotated/mirrored duplicate matching, AVI/MPEG-TS/WMV/FLV/3GP/M4V containers,
  audio artifacts (`audio.v1`: hashes, media info, metadata, byte-identical duplicate search), and
  on-demand playable previews.
- **Milestone 4 — Provenance** (D20, D21): local C2PA manifest validation in all three pipelines
  with a four-way outcome (valid / invalid / unverifiable / absent), per-manifest signer and
  assertion summaries, the raw manifest store as a derived file, and a provenance panel in the UI;
  plus the chain of custody (D21) — an append-only custody_events table, derived-file lineage,
  `GET /artifacts/{id}/custody`, custody.json in the export package, and the Chain of custody panel.

- **Milestone 5 — Reverse-image search** (D22): manual-first external search — a provider registry
  gated by per-provider settings (all off by default), plain landing-page links that transmit
  nothing, subject downloads (original image or a selected keyframe, never the preview), and
  analyst-recorded EXTERNAL leads with custody-trailed edits.

Remaining: GEOINT / geo-lite (M6), Vestigo integration (M7).

## 10. API Contract

Base URL: `http://localhost:8400/api/v1`. Milestone 1 endpoints:

- `GET /health`
- `POST /artifacts/upload`
- `GET /artifacts`
- `GET /artifacts/{artifact_id}`
- `GET /artifacts/{artifact_id}/content`
- `PATCH /artifacts/{artifact_id}/review`
- `DELETE /artifacts/{artifact_id}`
- `POST /analysis/image`
- `GET /analysis/jobs/{job_id}`
- `GET /artifacts/{artifact_id}/evidence` (`?job_id=`, `?download=true`)

Added by Milestones 2–3 and D19 (all additive; details in `03-API-SPEC.md`): bulk and per-record
review with history (`POST /artifacts/review`, `PATCH …/evidence/{id}/review`,
`GET …/review-history`), analysis history (`GET …/jobs`), the evidence package (`GET …/export`),
duplicate-library management (`PATCH …/duplicate-library`, `GET /library/summary`), settings
(`GET`/`PATCH /settings`), video and audio analysis (`POST /analysis/video`, `POST /analysis/audio`),
derived-file content (`GET …/derived/{id}/content`), and playable previews
(`POST`/`GET …/preview`, `GET …/preview/content`).

## 11. Non-Functional Requirements

- All endpoints return JSON (except the original-file preview).
- All errors use one envelope: `{"error": {"code", "message", "details"}}`.
- Long-running analysis runs as an asynchronous job.
- File handling is safe: type checked from content, size and pixel limits, no path traversal, uploads never
  executed.
- Logs never contain image contents, metadata values, OCR text, or credentials.
- Secrets, if any, come from `.env`.

## 12. Testing

- Unit tests for each stage.
- Integration tests for API endpoints.
- Frontend tests for the review UI.
- Test fixtures in `tests/fixtures/` (`samples/` is for manual testing and is gitignored).
- pytest for the backend, Vitest for the frontend.

See `07-TEST-PLAN.md`.

## 13. Milestone 1 Scope (historical — the approved M1 baseline)

- Project skeleton and Dev Container setup.
- Image upload, listing, preview, and deletion.
- The image pipeline in §8, run as an analysis job.
- JSON evidence report and download.
- Artifact-level review state and analyst notes.
- Health check including tool availability.
- Minimal React UI: upload, analysis progress, findings, review, download, delete.
- Core tests.

## 14. Out of Scope (Milestone 1 — historical)

Several items below were later implemented under approved plans: video analysis (M3), audio
artifacts and playable viewing previews (D19). The rest remain excluded until their milestone.

- Verdicts or authenticity scores of any kind.
- Login and multi-user authentication.
- Video analysis.
- ELA and noise analysis.
- Deepfake detection.
- External reverse-image search.
- GEOINT.
- Facial recognition or biometric identification.
- Vestigo integration.
- PDF reports.
- Admin panel.
- Placeholder or stub modules for any of the above.
