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

### Backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8400
```

API:

```text
http://localhost:8400
```

### Frontend

```bash
cd web
npm install
npm run dev -- --port 5180
```

UI:

```text
http://localhost:5180
```

## Repository layout

```text
vestigo-media-forensics/
├── README.md
├── .gitignore
├── .devcontainer/
│   └── devcontainer.json
├── docs/
├── app/
├── web/
├── tests/
├── samples/
└── scripts/
```

## Development rule

Do not begin implementation from prompts alone. Claude Code must first read all files in `docs/`, produce a build plan, and wait for approval.