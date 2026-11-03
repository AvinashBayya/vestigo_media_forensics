# Milestone 1 Build Plan (approved)

Approved: 2026-11-02. This is the implementation plan for Milestone 1 (image foundation).
Milestone 2 is planned in `12-MILESTONE-2-PLAN.md`.
Where `00-MASTER-SPEC.md` previously conflicted with docs 01–10, docs 01–10 win; 00 has been updated to match.

## 0. Approved decisions

| # | Decision |
|---|---|
| D-1 | Follow docs 01–10. No REAL/SUSPICIOUS/FAKE/UNKNOWN verdicts, no 0–100 confidence score. Entities are Artifact, AnalysisJob, EvidenceRecord. Endpoints follow 03. No login or multi-user auth in M1. No ELA or noise analysis in M1. |
| D-2 | The Dev Container installs Node LTS through the Dev Container Node feature and installs project dependencies after creation. |
| D-3 | C2PA in M1 is **detection only**, using ExifTool's JUMBF/CBOR groups plus byte-level checks. `c2pa-python` is deferred to M4. Detection is never presented as validation or proof of authenticity. A small, properly licensed public C2PA sample may be committed under `tests/fixtures/`. |
| D-4 | OCR is English only (`eng`). No additional language packages in M1. |
| D-5 | Limits: 50 MB maximum upload; 100 megapixels maximum image size; duplicate threshold pHash Hamming distance ≤ 10 of 64 bits. |
| D-6 | Uploading the same file twice creates a new artifact. Duplicate search reports the earlier artifact as an `exact_file` match. Artifacts are never merged automatically. |
| D-7 | Evidence classification records where evidence came from and never changes. Review state is set only by a human analyst. In M1, review applies to the whole artifact; per-record review is M2. |
| D-8 | Endpoints added beyond 03: `GET /artifacts`, `GET /artifacts/{id}/content`, `PATCH /artifacts/{id}/review`, and `?download=true` on the evidence endpoint. |
| D-9 | Artifacts and evidence are kept until the user explicitly deletes them. No automatic deletion in M1. |

Standing rules for M1:

- Do not implement video analysis, reverse-image search, GEOINT, facial recognition, Vestigo integration, ELA, or deepfake detection.
- Do not create placeholder or stub modules for future features.
- Every evidence result includes method, tool, tool version where applicable, timestamps, source, limitations, errors, and review state.
- Never describe the system as determining whether media is authentic, real, fake, or deceptive.

## 1. Folder structure

```text
vestigo-media-forensics/
├── .devcontainer/devcontainer.json   # Node LTS feature + postCreate installs
├── .env.example                      # all VESTIGO_* settings
├── pyproject.toml
├── app/
│   ├── __init__.py                   # __version__
│   ├── main.py                       # app factory, routers, error handlers, lifespan
│   ├── core/
│   │   ├── config.py                 # pydantic-settings, env prefix VESTIGO_
│   │   ├── database.py               # engine, SQLite pragmas, sessions, init_db
│   │   ├── storage.py                # safe paths, streamed writes, read-only originals, delete via trash/
│   │   ├── logging.py                # allow-listed log fields only (05 §7)
│   │   ├── errors.py                 # AppError, ErrorCode, envelope handlers
│   │   ├── ids.py                    # art_/job_/ev_/df_ IDs + format validation
│   │   └── tools.py                  # locate exiftool/tesseract/ffmpeg/ffprobe, cache versions
│   ├── api/       deps.py  routes_artifacts.py  routes_analysis.py  routes_health.py
│   ├── schemas/   common.py  artifact.py  analysis.py  evidence.py  health.py
│   ├── services/                     # tool wrappers: no DB, no evidence bookkeeping
│   │   ├── validation.py  hashing.py  metadata.py  c2pa.py  phash.py  ocr.py  duplicates.py
│   │   ├── artifacts.py              # create / list / review / delete
│   │   └── reports.py                # evidence records → EvidenceReport
│   ├── pipeline/  base.py  image_pipeline.py  runner.py  jobs.py
│   └── models/    artifact.py  analysis_job.py  evidence_record.py  fingerprint.py  derived_file.py
├── web/                              # React + Vite + TypeScript + Tailwind, port 5180, /api proxy → 8400
├── tests/  conftest.py  fixtures/  unit/  pipeline/  api/  container/
├── scripts/  dev-backend.sh  dev-frontend.sh  verify-env.sh
├── samples/                          # gitignored; manual testing only
└── data/                             # gitignored, created at runtime
    ├── app.db
    ├── artifacts/{id}/original/{id}.{ext}          # read-only (0444)
    ├── artifacts/{id}/derived/{job_id}/{stage}.*   # raw tool output
    ├── tmp/                          # uploads in progress
    └── trash/                        # staging area for all-or-nothing deletion
```

No placeholder modules exist for video, geo, reverse search, or ELA. New checks plug in as new pipeline stages.

## 2. API contract

Base URL `http://localhost:8400/api/v1`. All responses are JSON except `/content`. All errors use the envelope
`{"error": {"code", "message", "details"}}`, including validation errors, unknown routes, and 500s (no stack traces).
Malformed IDs return 404.

| Endpoint | Purpose | Success | Errors |
|---|---|---|---|
| `GET /health` | Service and tool status (§7) | 200 / 503 | — |
| `POST /artifacts/upload` | Multipart field `file` | 201 `ArtifactUploadResponse` | 400 `MISSING_FILE`/`EMPTY_FILE`, 413 `FILE_TOO_LARGE`, 415 `UNSUPPORTED_MEDIA_TYPE`, 422 `INVALID_IMAGE` |
| `GET /artifacts?limit&offset` | List, newest first | 200 `ArtifactList` | — |
| `GET /artifacts/{id}` | Details + latest job | 200 `ArtifactDetail` | 404 `ARTIFACT_NOT_FOUND` |
| `GET /artifacts/{id}/content` | Original bytes for preview (`nosniff`) | 200 `image/*` | 404 |
| `PATCH /artifacts/{id}/review` | Set artifact review state and notes | 200 `ArtifactDetail` | 404, 422 `VALIDATION_ERROR` |
| `DELETE /artifacts/{id}` | Delete original, derived files, jobs, evidence, rows | 200 `DeletionSummary` | 404, 409 `ANALYSIS_IN_PROGRESS` |
| `POST /analysis/image` | Queue the image pipeline | 202 `JobCreated` | 404, 409 `ANALYSIS_IN_PROGRESS` |
| `GET /analysis/jobs/{job_id}` | Job status + per-stage progress | 200 `JobStatusResponse` | 404 `JOB_NOT_FOUND` |
| `GET /artifacts/{id}/evidence?job_id&download` | Evidence report | 200 `EvidenceReport` | 404 `ARTIFACT_NOT_FOUND`/`EVIDENCE_NOT_FOUND`/`JOB_NOT_FOUND` |

Behaviour:

- `/evidence` returns the most recent finished job, or the job named by `job_id`. `download=true` adds
  `Content-Disposition: attachment; filename="vestigo-evidence-{artifact}-{job}.json"`.
- Re-running analysis creates a new job. Old jobs and their evidence are kept.
- At most one queued or running job per artifact. Deleting during a job returns 409.
- The frontend reaches the API through the Vite proxy; backend CORS allows only the configured frontend origin.

## 3. Pydantic schemas

Defined in `app/schemas/`. Request models forbid unknown fields; datetimes are UTC and serialize with `Z`.

- Enums: `MediaType` (image), `ReviewState` (UNREVIEWED, IN_REVIEW, REVIEWED, FLAGGED, ARCHIVED),
  `EvidenceClassification` (OBSERVED, DERIVED, EXTERNAL, UNVERIFIED, REVIEWED), `JobStatus`
  (queued, running, completed, completed_with_errors, failed), `StageStatus` (pending, running, succeeded,
  partial, failed, skipped), `ErrorCode`.
- Artifacts: `ArtifactUploadResponse`, `ReviewInfo`, `ArtifactSummary`, `ArtifactDetail`, `ArtifactList`,
  `ReviewUpdate`, `DeletionSummary`.
- Analysis: `AnalysisOptions` (ocr, duplicate_search, metadata, c2pa; hashes and perceptual hash always run),
  `ImageAnalysisRequest`, `JobCreated`, `StageProgress`, `JobSummary`, `JobStatusResponse`.
- Evidence: `StageError`, `Provenance` (evidence_id, stage, status, classification, method, source, tool,
  tool_version, started_at, completed_at, limitations ≥ 1, errors, review_state) attached to every section;
  `HashesSection`, `MetadataSection`, `C2PASection` (`validation_performed` is always false),
  `PerceptualHashSection`, `OCRSection`, `DuplicateMatch`, `DuplicatesSection`, `EvidenceReport`.

`EvidenceReport` keeps every key from 03 and adds `schema_version`, `notice`, `artifact`, `job`, and per-section
`provenance`. Disabled stages appear with `status: skipped`; failed stages appear with `status: failed` and
their errors. A section is `null` only if the job stopped before reaching that stage.

## 4. SQLite schema

SQLAlchemy 2.0, SQLite at `data/app.db`. Pragmas: `foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`,
`synchronous=NORMAL`. Timestamps are ISO-8601 UTC text. Enum values are enforced in the application layer so
new values (e.g. `video`) don't require SQLite table rebuilds. M1 creates tables with `create_all` and records
`schema_version` in `schema_meta`; Alembic is introduced at the first schema change.

Tables:

- `schema_meta(key, value)`
- `artifacts(id, original_filename, media_type, mime_type, size_bytes, sha256, md5, width, height, stored_path,
  review_state, analyst_notes, review_updated_at, created_at)`
- `analysis_jobs(id, artifact_id → artifacts ON DELETE CASCADE, pipeline, app_version, status, options_json,
  created_at, started_at, completed_at, error_code, error_message)`
- `evidence_records(id, artifact_id, job_id → cascade, stage, status, classification, method, source, tool,
  tool_version, payload_json, errors_json, limitations_json CHECK non-empty, review_state, started_at,
  completed_at, UNIQUE(job_id, stage))`
- `image_fingerprints(artifact_id, algorithm, value_hex, evidence_id, created_at, PK(artifact_id, algorithm))`
- `derived_files(id, artifact_id, job_id, stage, kind, stored_path, sha256, size_bytes, created_at)`

Deletion: move `artifacts/{id}/` into `trash/`, delete the artifact row (cascades) and commit, then remove the
trash directory. If the database step fails, the directory is moved back. `tmp/` and `trash/` are cleared at
startup.

## 5. Pipeline-stage interface

`app/pipeline/base.py`. `AnalysisStage.run(artifact, context) -> StageResult` (02 §4) is implemented once in the
base class; each stage implements `tool()` and `analyze()`. The base class records timestamps, handles
skip-by-option and skip-by-failed-dependency, converts exceptions and timeouts into `FAILED` results with an error
type and message, marks results with warnings as `PARTIAL`, and merges limitations. Every stage class must declare
at least one limitation.

The runner sets the job to `running`, executes stages in order, and saves each evidence record as soon as its
stage finishes. Final status: `completed` (all succeeded or skipped by option), `completed_with_errors` (any
partial or failed), `failed` (runner crashed). Jobs run in an in-process thread pool; job state lives in SQLite.
At startup, `queued` jobs are re-queued and `running` jobs are marked `failed` with `INTERRUPTED`.
`VESTIGO_JOB_MODE=inline` runs jobs synchronously for tests.

## 6. Image pipeline (`image.v1`)

Upload: stream to `tmp/` in 1 MiB chunks while hashing (SHA-256, MD5); enforce 50 MB; reject empty files; detect
type from magic bytes (JPEG, PNG, WebP, TIFF) only; verify with Pillow; enforce 100 MP; move to
`artifacts/{id}/original/{id}.{ext}` and make read-only. The original filename is sanitized and used for display
only.

| # | Stage | Option | Tool | Classification | Output |
|---|---|---|---|---|---|
| 1 | `hashes` | always | hashlib | DERIVED | sha256, md5, match against upload-time values (`INTEGRITY_MISMATCH` on mismatch) |
| 2 | `metadata` | `metadata` | ExifTool | OBSERVED | EXIF, XMP, IPTC, other, composite; raw JSON saved |
| 3 | `c2pa` | `c2pa` | ExifTool JUMBF/CBOR + byte-level check | OBSERVED | presence, manifest labels, decoded claim fields; `validation_performed: false` |
| 4 | `perceptual_hash` | always | imagehash pHash (64-bit) | DERIVED | hex value; updates the fingerprint index |
| 5 | `ocr` | `ocr` | Tesseract (`eng`) | DERIVED | text, mean word confidence (0–1), word count; raw TSV saved |
| 6 | `duplicates` | `duplicate_search` (needs 4) | Hamming scan of the local library | DERIVED | matches with distance, similarity, match type (`exact_file`, `visually_identical`, `near`) |

Subprocesses are called with argument lists (no shell) and timeouts, and only see the generated storage path. Logs
contain IDs, stage, status, error type, and timestamps only.

## 7. Health check

`GET /api/v1/health` returns 03's keys (`status`, `version`, `database`, `storage`) plus `tools` and `checked_at`.
`error` + 503 if the database or storage fails; `degraded` + 200 if ExifTool or Tesseract is missing; FFmpeg and
ffprobe are reported (used from M3) but don't affect M1 status. Tool versions are cached and shared with the
evidence records. `scripts/verify-env.sh` performs the same checks from the shell.

## 8. Test plan

Backend: pytest + httpx `TestClient`, a temporary data directory per test, inline jobs, real ExifTool and Tesseract
(missing tools fail tests rather than skip). Fixtures are generated deterministically by
`tests/fixtures/make_fixtures.py`, plus one committed public C2PA sample. Coverage follows `07-TEST-PLAN.md`, plus:
integrity mismatch, decompression bomb, evidence-completeness invariants for every record, skipped/failed stage
visibility, a guard test that no report key or enum value uses verdict wording, and deletion of fingerprints.
Container tests run with `pytest -m container`.

Frontend: Vitest + Testing Library + msw, covering `07-TEST-PLAN.md` §4 plus the delete confirmation dialog.

## 9. Implementation order

1. Docs + Dev Container (Node LTS feature, postCreate installs, `scripts/verify-env.sh`).
2. Skeleton: `pyproject.toml`, app factory, config, logging, errors, IDs, `/health` (database + storage).
3. Database models and initialization.
4. Storage, validation, upload, list, detail, content.
5. Tool registry and the `tools` section of `/health`; container tests.
6. Pipeline core (base, runner, jobs, analysis endpoints) with the `hashes` stage and evidence invariant tests.
7. `metadata` stage + fixture generator.
8. `perceptual_hash` → fingerprints → `duplicates`.
9. `c2pa` stage.
10. `ocr` stage.
11. Evidence report, download, review update, verdict-wording guard.
12. Deletion.
13. Frontend: upload with progress, job polling, six result panels with provenance footers, review, download,
    delete dialog, tests.
14. Acceptance against 01 §10; README run instructions.
