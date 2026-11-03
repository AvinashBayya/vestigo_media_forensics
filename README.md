# Vestigo Media Forensics

Vestigo Media Forensics is a local-first media provenance and verification service for OSINT analysts, journalists, researchers, and fact-checkers.

It helps users inspect images and, later, videos; extract technical evidence; detect manipulation signals; check provenance metadata; and organize findings into reviewable evidence—without claiming that a file is definitely real or fake.

## Core principles

- Local-first: media and analysis results remain on the user’s machine.
- Evidence over verdicts: the system reports observable signals, not definitive truth claims.
- Human review: analysts approve conclusions and publications.
- Explainability: every result shows method, tool, timestamp, limitations, and review state.
- Simple interface: powerful engine, minimal user-facing workflow.
- No overclaiming: no automatic “deepfake detector” or “truth engine” claims.

## Current scope

### Milestone 1 — Image foundation

- Image upload
- SHA-256 and MD5 hashing
- EXIF/XMP/IPTC metadata extraction
- C2PA / Content Credentials detection
- Perceptual hash generation
- OCR text extraction
- Local duplicate-image search
- JSON evidence output
- Minimal upload-and-review UI

Milestone 1 is image-only. FFmpeg and ffprobe are installed during environment setup but are not invoked until the video pipeline is implemented.

### Milestone 2 — Analyst workflow

- Library home page: search (filename, notes, artifact ID, hash prefix), filters, sorting, status indicators
- Review workflow: artifact and per-evidence-record review, bulk review, conflict detection, full review history
- Analysis history and a problems summary for failed or partial checks
- ZIP evidence package with a SHA-256 manifest
- Duplicate-library management: exclude or include artifacts for future searches, "added since analysis" hint
- Settings: default checks, automatic analysis after upload, Library page size; environment settings shown read-only
- Database migrations with Alembic (Milestone 1 databases are upgraded in place)

See `docs/12-MILESTONE-2-PLAN.md`.

## Later phases

- Video metadata, keyframe extraction, scene detection, and audio inspection
- Reverse-image search integrations
- GEOINT / geo-lite analysis
- C2PA validation and provenance reporting
- Chain-of-custody view and derived-file relationships (Milestone 4)
- Optional Vestigo integration through a versioned evidence API

## Tech stack

- Backend: Python 3.11, FastAPI, Uvicorn
- Database: SQLite
- Frontend: React + Vite + TypeScript
- Media tooling: ExifTool, Tesseract OCR, FFmpeg, ffprobe
- Container: Docker Dev Container

## Ports

| Service  | Port |
|----------|------|
| Backend API | 8400 |
| Frontend UI | 5180 |

## Run inside Dev Container

All commands run inside the Dev Container, from the repository root.

### First-time setup

Rebuilding the container runs `scripts/post-create.sh`, which installs ExifTool, Tesseract, and FFmpeg, then the Python and web dependencies. To install the project dependencies by hand:

```bash
python -m pip install -e ".[dev]"
(cd web && npm ci)
bash scripts/verify-env.sh
```

### Backend (port 8400)

```bash
scripts/dev-backend.sh
# same as: uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8400
```

- Health: http://localhost:8400/api/v1/health
- Interactive API docs: http://localhost:8400/api/v1/docs

### Frontend (port 5180)

In a second terminal:

```bash
scripts/dev-frontend.sh
# same as: cd web && npm run dev
```

Open http://localhost:5180. The frontend proxies `/api` to the backend, so start the backend first.

### Data and configuration

- Uploads, raw tool output, and the SQLite database are stored under `data/` (gitignored). Nothing is deleted automatically; delete artifacts from the UI or with `DELETE /api/v1/artifacts/{id}`.
- Environment settings are read from `VESTIGO_*` environment variables or a `.env` file. See `.env.example` for every setting and its default. They are shown read-only on the Settings page; restart the backend after changing them.
- Analyst defaults (checks to run, automatic analysis after upload, Library page size) are edited on the Settings page and stored in the database.

### Database migrations

The backend migrates `data/app.db` to the latest schema when it starts (Alembic). A Milestone 1 database is upgraded in place; existing rows are not rewritten. If the database was written by a newer version of Vestigo, the backend refuses to start and leaves it unchanged. Upgrades run in one transaction; there are no downgrades, so copy `data/` first if you may need to go back to an older version.

For developers, `alembic current` and `alembic revision -m "…"` work from the repository root against `$VESTIGO_DATA_DIR/app.db`. Never edit a revision that has been applied; add a new one.

### Tests

```bash
python -m pytest                 # backend unit, pipeline, API, and migration tests
python -m pytest -m container    # tools, SQLite, and ports 8400/5180 (starts servers if needed)
ruff check app tests             # backend lint
(cd web && npm test)             # frontend tests (Vitest)
(cd web && npm run build)        # type check and production build
```

## Manual test of the Milestone 2 workflow

With both servers running, open http://localhost:5180.

1. **Library.** The home page lists artifacts with analysis status, problems, duplicate matches, and review state. Try the search box (part of a filename, a SHA-256 prefix of 8+ characters), the review-state chips, "Has problems", and the column headers. Reload the page: the view is kept in the URL. Archived artifacts appear only with "Show archived".
2. **Upload.** Click Upload, choose an image, and upload. With default settings the analysis starts and the artifact page shows progress.
3. **Duplicates.** Upload a resized or re-saved copy of an image already in the Library. Its duplicates panel lists the original. Open the original: its panel says "1 artifact was added to the library after this search"; click "Run analysis again" and the copy appears.
4. **Problems and history.** If a check fails or has warnings, the yellow problems summary links to it. "Analysis history" lists every run; "View this analysis" opens an earlier one.
5. **Review.** Set the artifact's review state and notes and save. Open "Review history" to see the change with full notes. In any evidence section, "Review this section" saves a review for that record only.
6. **Conflict.** Open the same artifact in two tabs, save a review in one, then save in the other: the second tab keeps your text and offers "Use the saved review" or "Save my version over it".
7. **Unsaved changes.** Type a note without saving and click Library: you are asked before leaving.
8. **Bulk review.** In the Library, tick several rows, choose a state, click "Apply…", and confirm. A message says how many changed. Each artifact's review history shows a "Bulk change" entry.
9. **Export.** On an artifact page, "Download evidence package (ZIP)" saves the package and shows its SHA-256. Compare with `sha256sum <file>.zip`, unzip, and run `sha256sum -c SHA256SUMS`. Tick "Include the original file" to add the upload.
10. **Duplicate library.** "Exclude from future searches" on an artifact page, then analyse a copy of it: no match, and the duplicates panel says one artifact was excluded. Settings lists excluded and not-analysed artifacts.
11. **Settings.** Change the default checks, turn off automatic analysis, set 10 artifacts per page, and save. The Library uses 10 rows; uploads no longer start an analysis. The duplicate threshold and limits are shown read-only.

## Limitations

- C2PA / Content Credentials are **detected, not validated**. Signatures, certificates, and hash bindings are not checked until Milestone 4.
- OCR is best-effort and English only; its output is provisional, not a verified transcription (D14).
- Duplicate search covers only artifacts in the local library, as it was when each analysis ran. Earlier results are not updated when artifacts are added or excluded; run the analysis again.
- Review conflicts are detected per artifact or record; there is no login, and the service is meant for a single analyst on their own machine.
- Nothing is deleted automatically.

See `docs/11-BUILD-PLAN.md` (Milestone 1) and `docs/12-MILESTONE-2-PLAN.md` (Milestone 2).

## Repository layout

```text
vestigo-media-forensics/
├── README.md
├── pyproject.toml
├── .env.example
├── .devcontainer/
│   └── devcontainer.json
├── alembic.ini           # developer access to database migrations
├── docs/                 # specifications and the approved build plans
├── app/                  # FastAPI backend
│   ├── api/              # routes and request-level middleware
│   ├── core/             # config, database, storage, tools, errors, logging
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── services/         # tool wrappers, library, review, export, settings, reports
│   ├── migrations/       # Alembic revisions (0001 = Milestone 1 baseline)
│   └── pipeline/         # stage interface, image pipeline, job runner
├── web/                  # React + Vite + TypeScript + Tailwind frontend
├── tests/                # pytest suites and test fixtures
├── samples/              # local media for manual testing (gitignored)
└── scripts/              # setup, environment check, dev servers
```

## Development rule

Do not begin implementation from prompts alone. Claude Code must first read all files in `docs/`, produce a build plan, and wait for approval.