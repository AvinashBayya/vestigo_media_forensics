# Vestigo Media Forensics — Master Build Spec

## 1. Project Goal

Build a local-first media forensics web app that:

- Accepts images, videos, and (later) documents.
- Runs automated forensic checks.
- Produces a clear verdict: REAL / SUSPICIOUS / FAKE / UNKNOWN.
- Shows evidence for every claim.
- Keeps all data local (SQLite + local files).
- Runs fully inside a Docker dev container.

## 2. Tech Stack

- Backend: Python 3.11, FastAPI, Pydantic v2, SQLite, SQLAlchemy.
- Frontend: React + Vite + TypeScript + Tailwind.
- OCR: Tesseract.
- Metadata: ExifTool.
- Media: ffmpeg / ffprobe.
- Auth: JWT (email + password).
- Storage: local filesystem under `data/`.
- DB: SQLite file at `data/app.db`.

## 3. Core Principles

- Evidence-first: every verdict must link to concrete evidence.
- Explainable: no black-box "AI says fake" without reasons.
- Modular: each check is a separate pipeline stage.
- Extensible: new checks can be added without breaking old ones.
- Local-first: no external API calls required for core flow.

## 4. High-Level Architecture

- FastAPI backend on port 8400.
- React frontend on port 5180.
- SQLite DB for users, assets, analyses, findings.
- Local file storage for uploaded media.
- Pipeline engine that runs checks per media type.

## 5. User Roles

- Guest: can view landing page, sign up, log in.
- User: can upload media, run analysis, view results.
- Admin (later): can manage users, view system stats.

## 6. Core Entities

- User: id, email, hashed_password, created_at.
- Asset: id, user_id, file_path, file_type, original_filename, size_bytes, sha256, created_at.
- Analysis: id, asset_id, status, verdict, confidence, started_at, finished_at, error.
- Finding: id, analysis_id, check_name, severity, score, summary, details_json.
- Report: id, analysis_id, generated_at, format (json/pdf later).

## 7. Verdict Model

- REAL: high confidence authentic.
- SUSPICIOUS: some signs of manipulation or inconsistency.
- FAKE: strong evidence of manipulation or synthetic origin.
- UNKNOWN: not enough signal or check failed.

Each verdict has:
- confidence (0–100)
- list of findings with severity and explanation.

## 8. Image Pipeline (v1)

Checks:
- EXIF metadata presence and consistency.
- C2PA / Content Credentials detection (if present).
- ELA (Error Level Analysis) style heuristic.
- Noise / compression inconsistency (basic).
- Duplicate / near-duplicate detection via perceptual hash.
- Reverse-image-search placeholder (no external call in v1).

Output:
- verdict + confidence + findings.

## 9. Video Pipeline (v1)

Checks:
- ffprobe metadata (codec, duration, resolution, bitrate).
- Frame sampling.
- Per-frame basic checks (blur, compression artifacts).
- Audio track presence and basic stats.
- Deepfake heuristic placeholders (face-count, temporal inconsistency later).

Output:
- verdict + confidence + findings.

## 10. Geo-lite (v1)

- If EXIF GPS exists:
  - Reverse geocode via local offline dataset or placeholder.
  - Show map placeholder (no external map API in v1).
  - Cross-check GPS vs file timestamps.

## 11. API Contract (v1)

Base URL: http://localhost:8400/api/v1

- POST /auth/register
- POST /auth/login
- GET /auth/me
- POST /assets/upload
- GET /assets
- GET /assets/{id}
- POST /analyses/{asset_id}/run
- GET /analyses/{id}
- GET /analyses/{id}/findings
- GET /analyses/{id}/report
- GET /health

## 12. Non-Functional Requirements

- All endpoints return JSON.
- All errors have consistent shape.
- All long-running tasks are async-friendly.
- All file handling is safe (no path traversal).
- All secrets via .env, never hardcoded.

## 13. Testing

- Unit tests for each check.
- Integration tests for API endpoints.
- Sample media in `samples/` for testing.
- Use pytest.

## 14. Milestone 1 Scope

- Project skeleton.
- Auth (register/login/me).
- Asset upload + listing.
- Basic image pipeline (EXIF + hash + ELA-lite).
- Analysis record + findings.
- Health check.
- Minimal React UI: login, upload, results page.

## 15. Out of Scope (v1)

- Real deepfake detection models.
- External reverse image search APIs.
- PDF report generation.
- Admin panel.
- Multi-user roles beyond basic user.