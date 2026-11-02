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

## Later phases

- Video metadata, keyframe extraction, scene detection, and audio inspection
- Reverse-image search integrations
- GEOINT / geo-lite analysis
- C2PA validation and provenance reporting
- Case management and evidence export
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
- Settings are read from `VESTIGO_*` environment variables or a `.env` file. See `.env.example` for every setting and its default.

### Tests

```bash
python -m pytest                 # backend unit, pipeline and API tests
python -m pytest -m container    # tools, SQLite, and ports 8400/5180 (starts servers if needed)
ruff check app tests             # backend lint
(cd web && npm test)             # frontend tests (Vitest)
(cd web && npm run build)        # type check and production build
```

## Milestone 1 limitations

- C2PA / Content Credentials are **detected, not validated**. Signatures, certificates, and hash bindings are not checked until Milestone 4.
- OCR uses English language data only.
- Duplicate search covers only artifacts in the local library.
- Review state applies to a whole artifact; per-evidence-record review is planned for Milestone 2.
- There is no login. The service is meant for a single analyst on their own machine.

See `docs/11-BUILD-PLAN.md` for the approved Milestone 1 plan.

## Repository layout

```text
vestigo-media-forensics/
├── README.md
├── pyproject.toml
├── .env.example
├── .devcontainer/
│   └── devcontainer.json
├── docs/                 # specifications and the approved build plan
├── app/                  # FastAPI backend
│   ├── api/              # routes and request-level middleware
│   ├── core/             # config, database, storage, tools, errors, logging
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── services/         # tool wrappers and artifact/report logic
│   └── pipeline/         # stage interface, image pipeline, job runner
├── web/                  # React + Vite + TypeScript + Tailwind frontend
├── tests/                # pytest suites and test fixtures
├── samples/              # local media for manual testing (gitignored)
└── scripts/              # setup, environment check, dev servers
```

## Development rule

Do not begin implementation from prompts alone. Claude Code must first read all files in `docs/`, produce a build plan, and wait for approval.