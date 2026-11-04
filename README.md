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

### Milestone 3 — Video foundation

- Video upload (MP4, MOV, WebM, MKV) validated with ffprobe; limits on size, duration, and frame size
- `video.v1` pipeline: hashes, ffprobe media information (container and stream facts as written, audio headers only), ExifTool metadata, scene-change detection, keyframe extraction with a recorded selection policy, keyframe perceptual hashes, optional keyframe OCR (off by default, ≤ 10 frames), and duplicate search
- Duplicate detection across media: videos match re-encoded copies frame for frame, stills match the videos they came from, and vice versa
- Browser playback through the content endpoint (HTTP Range; no transcoding) with a fallback message, keyframe thumbnails, and video evidence panels

See `docs/13-MILESTONE-3-PLAN.md`.

### D19 — Cross-media search, more formats, audio, and viewing previews

- Duplicate search also finds rotated (90/180/270°) and mirrored copies of images and videos, recording how each pair matched
- More video containers: AVI, MPEG-TS, WMV, FLV, plus correct 3GP and M4V labelling
- Audio artifacts (WAV, MP3, FLAC, OGG, M4A): hashes, media information, and metadata through the same pipeline machinery; duplicate search is byte-identical only — no audio is decoded, fingerprinted, or transcribed
- On-demand playable previews: a video the browser cannot play can get a re-encoded viewing copy, clearly labelled, never part of the evidence
- Clearer keyframe and keyframe-OCR panels: per-frame numbers, reasons, statuses, raw OCR output, and honest empty states

## Later phases

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

## Manual test of the Milestone 3 video workflow

1. **Upload a video.** On the Upload page choose an MP4 (or MOV/WebM/MKV) under 500 MB and at most 15 minutes. The checks switch to the video options — keyframe OCR is off by default; tick it if you want text read from frames. Upload; the analysis starts and per-stage progress shows.
2. **Preview and media information.** The artifact page plays the video (seeking works). The header shows the container-reported duration. "Media information" lists the container, duration, video codec/resolution/frame rate, and audio stream facts; nothing is decoded or transcribed.
3. **Scene changes and keyframes.** "Scene changes" lists timestamps with scores. "Keyframes" shows the extracted thumbnails, each with its timestamp and why it was selected (first frame, scene change with score, or even sample).
4. **Keyframe OCR** (if enabled): "Text in keyframes (OCR)" is labelled provisional and lists per-frame text with Tesseract's own confidence.
5. **Duplicates across media.** Re-encode or resize the video (for example export it as WebM) and upload the copy: its duplicates panel lists the original with matching frame pairs ("this video at 0:03 ↔ matched video at 0:03.1"). Take a screenshot of a frame and upload it as an image: its duplicate search finds the video.
6. **Unplayable codecs.** Upload an MKV with a codec your browser refuses: the preview area explains it cannot be played and points to the keyframes.
7. **Review, export, delete.** Review states, per-section review, history, and bulk review work on videos unchanged. "Download evidence package (ZIP)" includes the keyframes, raw ffprobe output, and scene-filter output with verified hashes (check with `sha256sum -c SHA256SUMS`). Deleting the video removes the original, every derived file, all evidence, and its keyframe fingerprints.
8. **Settings.** Default video checks are editable; the video limits (size, duration, frame size, keyframes, scene threshold, ffmpeg timeout) are shown read-only and set with `VESTIGO_*` variables.

## Manual test of the D19 additions

1. **Rotated/mirrored duplicates.** Rotate a library video with `ffmpeg -display_rotation 90 -i in.mp4 -c copy rot.mp4` (or flip it with `-vf hflip`), upload, analyse: the duplicates panel lists the original with each frame pair marked "rotated 270°" or "mirrored". The same works for rotated or mirrored image copies.
2. **More containers.** Upload an AVI, TS, WMV, FLV, or 3GP file: it is classified from its bytes and analysed like any video. Formats browsers refuse show the keyframes and offer a preview (next step).
3. **Playable preview.** Open a video the browser cannot play (for example FFV1 or WMV): the preview box offers "Create playable preview". One click re-encodes a viewing copy and plays it, labelled "re-encoded viewing copy — not the original evidence". The export package never contains it; deleting the artifact removes it.
4. **Audio.** Upload a WAV/MP3/FLAC/OGG/M4A: it plays in the built-in audio player, with media information (codec, channels, sample rate, container-reported duration) and ID3/container metadata as evidence. Upload the identical file again: duplicate search reports "Same file (identical bytes)". Re-encode it (e.g. WAV → MP3) and upload: no match, and the evidence's limitations explain that only byte-identical audio matches.
5. **Keyframes panel.** Every thumbnail caption reads like "#4 · 0:03 · scene change (0.58)"; portrait videos sit cleanly in the grid; a failed thumbnail shows Retry; switching analyses in the history swaps to that run's keyframes.
6. **Keyframe OCR panel.** With OCR enabled, every keyframe has a status row — text beside its thumbnail with confidence ("the engine's own estimate") and expandable raw output, "No text was detected…" for empty frames, the recorded error for failed frames, and "Not analysed — outside the 10-frame OCR limit" for the rest. Disabled OCR shows its skip reason.

## Limitations

- C2PA / Content Credentials are **detected, not validated**. Signatures, certificates, and hash bindings are not checked until Milestone 4 (video C2PA is also Milestone 4).
- OCR is best-effort and English only; its output is provisional, not a verified transcription (D14). Keyframe OCR reads at most 10 sampled frames.
- Duplicate search covers only artifacts in the local library, as it was when each analysis ran. Video matching compares sampled keyframes (including rotated and mirrored variants); content between keyframes is not searched.
- Audio duplicate search is byte-identical only: a re-encoded copy of the same recording will not match, because no audio content is ever decoded or compared.
- A playable preview is a re-encoded viewing copy for the browser, clearly labelled; it is not evidence and is excluded from the evidence package.
- Video duration, frame rate, and similar values are container-reported metadata, not decode-verified measurements. Audio is inspected from stream headers only — no decoding, transcription, or speaker identification.
- Videos are never transcoded; a browser that cannot play a codec shows a fallback message.
- Review conflicts are detected per artifact or record; there is no login, and the service is meant for a single analyst on their own machine.
- Nothing is deleted automatically.

See `docs/11-BUILD-PLAN.md` (Milestone 1), `docs/12-MILESTONE-2-PLAN.md` (Milestone 2), and `docs/13-MILESTONE-3-PLAN.md` (Milestone 3).

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
│   └── pipeline/         # stage interface, image and video pipelines, job runner
├── web/                  # React + Vite + TypeScript + Tailwind frontend
├── tests/                # pytest suites and test fixtures
├── samples/              # local media for manual testing (gitignored)
└── scripts/              # setup, environment check, dev servers
```

## Development rule

Do not begin implementation from prompts alone. Claude Code must first read all files in `docs/`, produce a build plan, and wait for approval.