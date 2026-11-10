# Vestigo Media Forensics

Vestigo Media Forensics is a local-first media provenance and verification service for OSINT analysts, journalists, researchers, and fact-checkers.

It helps users inspect images and, later, videos; extract technical evidence; detect manipulation signals; check provenance metadata; and organize findings into reviewable evidence—without claiming that a file is definitely real or fake.

**New here, or picking this up from someone else?** Read
[`docs/18-SETUP-AND-HANDOFF.md`](docs/18-SETUP-AND-HANDOFF.md) first: host and WSL2 prerequisites,
the Docker Dev Container, configuration, folder structure, running instructions, troubleshooting,
the project's standing rules, and how another system integrates with Vestigo.

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

### Milestone 4 — C2PA validation and provenance (D20)

- Content Credentials (C2PA) manifests are validated locally with c2pa-python 0.38.1 (c2pa-rs SDK 0.91.3) for images, videos, and audio — no network, no modification of the original
- Four-way outcome: **valid** (hashes and claim signature verify), **invalid**, **unverifiable** (with the recorded reason), or **absent**
- Per manifest: claim generator, signer certificate details, signature time and algorithm, assertion labels, and ingredient count — recorded as written, not verified against any registry
- The validator's raw manifest-store report is kept as an auditable derived file, exported in the evidence package and deleted with the artifact
- Honesty rules: valid never means truthful or trusted (no trust list is configured, and the standing `signingCredential.untrusted` code stays visible); absence proves nothing

### Milestone 4 part 2 — Chain of custody (D21)

- A Chain of custody panel on every artifact page: what Vestigo recorded on this machine since upload — upload, analyses, review changes, exports, duplicate-library changes, and preview creation — merged chronologically, each entry naming the table it came from
- Honest by construction: not a legal chain of custody, nothing about the file before upload, and nothing inferred — actions from before schema revision 0005 that were never recorded do not appear, and the notice says so
- Derived-file lineage: every new derived file records what it was read from (a keyframe-OCR TSV points at its exact keyframe thumbnail); older rows read "source not recorded", never guessed
- `GET /artifacts/{id}/custody`, custody.json in the evidence export package (hashed in the manifest), an append-only custody_events table (Alembic 0005), and custody events counted in deletion

### Milestone 5 — Reverse-image search (D22)

- Manual-first external search: Vestigo opens a provider's plain landing page (no query parameters, nothing evidence-derived) and never uploads media — the analyst downloads the exact subject file and uploads it themselves, under the provider's terms, after a clear sharing warning
- Providers (Google Lens, Bing Visual Search, TinEye, Yandex Images) are all disabled until enabled individually in Settings
- Search subjects: the original image, or a selected video keyframe (its real derived file) — audio is refused and the playable preview is never offered
- Findings come back as analyst-recorded **EXTERNAL leads**: provider, result URL, optional image URL, notes, and the publication date exactly as entered, always labelled analyst-reported and unverified, separate from when the lead was recorded; an earlier result is never called the original source
- Lead creates, edits, and deletes are append-only custody events; leads travel in the evidence report and export package and are deleted and counted with the artifact (Alembic 0006, schema v6)

### Milestone 6 — GEOINT / geo-lite (D23)

- Location **clues**, never claims: a `location_clues` stage (all three media types, on by default) reports GPS coordinates in decimal beside the original as-written strings and hemisphere refs, altitude, GPS and EXIF/container timestamps, camera make/model/orientation, IPTC and XMP place-name fields, and container ISO 6709 locations — each labelled with the tag it came from
- Coordinate ranges are validated; an out-of-range or half-present value is flagged with its reason and kept **exactly as written** — never corrected, normalised, or dropped
- Disagreeing metadata sources are shown side by side; Vestigo never decides which is right, and never extracts place names from OCR text — it points the analyst at the OCR evidence to read for themselves
- Analyst **location candidates**, classified UNVERIFIED: a stated place, a required basis in the analyst's own words, their own assessment label (speculative / possible / likely — never machine-derived), optional validated coordinates, and typed links to supporting evidence of the same artifact
- One opt-in **OpenStreetMap link**, off by default, built in the browser and opened only on click, with a warning that clicking sends those coordinates to openstreetmap.org. No map tiles, no embedded map, no API key, no reverse geocoding, and no coordinates in Vestigo's logs
- Candidate creates, edits, and deletes are append-only custody events; candidates travel in the evidence report and export package and are deleted and counted with the artifact (Alembic 0007, schema v7)

### Pass 1 — Local AI foundation (D24)

Local, optional, and off by default. The runtime is Cactus Compute's, Apache-2.0, CPU-only and tens of megabytes; it is an optional extra (`pip install -e ".[dev,ai]"`) and you stage the engine yourself with `needle fetch --generation 2`. A stock build installs nothing, downloads nothing, and sends nothing — and the backend *cannot* download anything, because `HF_HUB_OFFLINE=1` is forced in-process (D27).

Measured on an i7-1165G7 laptop CPU with no GPU: 0.96 s for the first extraction including engine load, 0.67 s warm, 47 MB RSS. What runs is generation 2. Generation 3 weights (`needle3.cact`) and Whistle are published **without an engine for any platform**, so transcription and model text embeddings report themselves unavailable with that reason and will start working when the vendor publishes one. Nothing is faked in the meantime.

- **AI output is never evidence.** Drafts, transcripts, and indexes live in their own tables, are absent from the evidence report, travel in the export package's separate `ai/` folder with its own "not evidence" README, and are labelled **"AI-generated, unverified — analyst must review"** everywhere
- **Needle structured extraction**: ask a local model for named fields from material you already hold (metadata, OCR text, your notes, a transcript), then accept, edit, or reject **each field** — an edit is stored beside the model's value, never over it, and nothing is ever written back onto metadata or evidence
- **Whistle transcription** (16.9 MB): timestamped local speech-to-text for audio and video, with word-level timing where the model gives it; the model's text is kept verbatim beside your corrections and the original audio is only ever read. *Currently unavailable: it needs the generation 3 engine, which the vendor does not publish — `/ai/status` says so rather than failing on use*
- **Local semantic search and retrieval** over your own notes, OCR text, transcripts, metadata, leads, and location candidates. Questions return the sources themselves: this runtime has no text generation, so Vestigo drafts no prose and says so
- **Staged model files** live in `data/models/`, listed with their size and SHA-256 so a draft names the exact bytes behind it. Drop a `.cact` file in by hand or import it in Settings — both are the same thing, and neither fetches anything
- **Confidence only where the model supplies it** — Vestigo never calculates one
- **Vendor telemetry is forced off** in-process (`NEEDLE_TELEMETRY=0`, `DO_NOT_TRACK=1`, `CACTUS_TELEMETRY=0`) before the runtime can load, asserted by a test; `NEEDLE_API_KEY` is never read, so the vendor's upload-to-their-GPUs fine-tuning is unreachable

### Pass 2 — Deep media forensics (D25)

- **Structure and hidden-data inspection** for every media type: where a format's data ends and exactly how many bytes follow, container inventories (PNG chunks with CRCs verified, JPEG segments, MP4/MOV boxes, RIFF chunks), truncated chunks and impossible sizes, trailing padding, and known file signatures found at non-zero offsets — each placed with its offset and size
- Measurements with their method and no thresholds: whole-file and windowed entropy, LSB balance, chi-square. It never says "steganography detected" and **never says a file is clean** — concealment can be undetectable by these checks, and the limitations say so. Nothing is extracted, carved, or password-attacked; binwalk is optional and only ever used for signature scanning, never extraction
- **Forensic indicators**: JPEG quantisation tables with the quality each implies *for the last save only*, per-channel pixel statistics, declared against decoded dimensions, and video keyframe/packet distributions. Error-level analysis is deliberately **not** implemented, because its output is routinely misread as proof of editing
- **Documents and PDFs** are a first-class media type, parsed in pure Python with no PDF library and no renderer: structure (pages, objects, repeated saves, encryption, signature *presence*, and features like JavaScript or forms as presence counts), provisional text labelled like OCR, and embedded JPEG images copied out **byte for byte**. Vestigo never validates a PDF signature, renders a page, executes anything in a document, or decrypts one
- **Audio** keeps its header-level media info and metadata, gains the structural checks, and can be transcribed locally via Pass 1

### Pass 3 — GEOINT tooling and integration (D26)

- **Coordinate tools** for every coordinate Vestigo already holds (metadata clues and your own candidates): decimal, DMS, DDM, and ISO 6709 notation, plus the great-circle distance and bearing between each pair. Calculation only — no geocoding, no place names, no map tiles, no network. A coordinate flagged invalid stays in the evidence as written and is never used for geometry, and **no location is ever decided**
- Offline map data is used only if you supply a path to your own (`VESTIGO_OFFLINE_MAP_PATH`); Vestigo downloads none
- **Cases** group artifacts under a name you choose. A case is organisation, not evidence: it asserts nothing about its members, every link and unlink lands in the artifact's custody trail, and deleting a case removes only the case and its links — never an artifact or its evidence
- **A read-only integration API**, off by default: `GET /integration/version` (always readable, so an integrator can see the contract and that it is disabled) and `GET /integration/artifacts/{id}/evidence`, returning the evidence report, chain of custody, and cases in one versioned envelope. The surface has **no write route of any kind**, so an external system can never change anything Vestigo holds — enforced by construction, not by a permission check. Import is deliberately absent: evidence leaves Vestigo, it never arrives from outside

## Supported formats and limits

| Media | Formats (detected from the file's bytes) | Limits (environment-set, read-only in Settings) |
|---|---|---|
| Images | JPEG, PNG, WebP, TIFF | 50 MB (`VESTIGO_MAX_UPLOAD_BYTES`), 100 MP (`VESTIGO_MAX_IMAGE_PIXELS`) |
| Videos | MP4, MOV, WebM, MKV, AVI, MPEG-TS, WMV, FLV, 3GP, M4V | 500 MB (`VESTIGO_MAX_VIDEO_UPLOAD_BYTES`), 15 min (`VESTIGO_MAX_VIDEO_DURATION_SECONDS`), 4K per frame (`VESTIGO_MAX_VIDEO_PIXELS`) |
| Documents | PDF | 100 MB (`VESTIGO_MAX_DOCUMENT_UPLOAD_BYTES`) |
| Audio | WAV, MP3, FLAC, OGG, M4A | 200 MB (`VESTIGO_MAX_AUDIO_UPLOAD_BYTES`), 2 h (`VESTIGO_MAX_AUDIO_DURATION_SECONDS`) |

Analysis pipelines (every stage records method, tool, version, timestamps, source, limitations,
errors, and review state):

- `document.v1`: hashes → metadata → PDF structure → provisional text → embedded images → structural checks → duplicate search (byte-identical only)
- `image.v1`: hashes → metadata → location clues → structural checks → forensic indicators → C2PA detection and validation → perceptual hash → OCR → duplicate search
- `video.v1`: hashes → media information (ffprobe) → metadata → C2PA validation → location clues → structural checks → forensic indicators → scene detection → keyframes →
  keyframe perceptual hashes → keyframe OCR (optional, off by default, ≤ 10 frames) → duplicate
  search (keyframes vs. images and other videos' keyframes, including rotated and mirrored variants;
  limit `VESTIGO_MAX_KEYFRAMES`, scene threshold `VESTIGO_SCENE_THRESHOLD`)
- `audio.v1`: hashes → media information → metadata → C2PA validation → location clues (metadata only) → structural checks → duplicate search (byte-identical SHA-256 only —
  no audio content is ever decoded or compared)

Playable previews (videos only, on demand): one re-encoded H.264/AAC viewing copy per artifact,
clearly labelled, excluded from the evidence package, kept until the artifact is deleted.

## Later phases

- Paid or official reverse-image search provider APIs, reverse geocoding, and map tile services (each needs separate approval)

## Tech stack

- Backend: Python 3.11, FastAPI, Uvicorn
- Database: SQLite
- Frontend: React + Vite + TypeScript
- Media tooling: ExifTool, Tesseract OCR, FFmpeg, ffprobe
- Local AI (optional extra `.[ai]`): Cactus Needle (Apache-2.0, CPU-only; engine staged by you, downloads blocked in-process)
- C2PA validation: c2pa-python 0.38.1 (c2pa-rs SDK 0.91.3), entirely local
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
python -m pip install -e ".[dev,ai]"   # drop ,ai to build without the local AI runtime
(cd web && npm ci)
bash scripts/verify-env.sh
```

`verify-env.sh` reports the AI runtime and each engine generation as present or absent without
failing: a container with no local AI is a supported setup. To run a model, stage the engine once —
this is the only step that touches the network, and it is never part of a container build:

```bash
needle fetch --generation 2    # ~14 MB into ~/.cache/cactus-needle/v2/2.0.4/
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
(cd web && npm test)             # frontend tests (Vitest, hermetic: no servers needed)
(cd web && npm run build)        # type check and production build
```

Every test above is hermetic. There is one extra check that drives the real UI against the running
servers, to catch what a hermetic suite cannot: a blank page, a proxy or CORS problem, a failed API
call, or a runtime JavaScript error. Start both servers first, then:

```bash
(cd web && npx vitest run --config browser-acceptance.config.ts)
```

It boots the real router in jsdom at `http://localhost:5180`, so requests take the same path the
browser does (Vite proxy to the backend), with no mocking. It renders the library, settings, upload,
search and not-found pages, asserts no runtime errors were raised, and - given
`VESTIGO_TEST_ARTIFACT=<artifact id>` - renders that artifact's page and checks every evidence panel
is present. It is excluded from `npm test` because it needs the servers up.

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

## Manual test of Pass 3 (coordinates, cases, integration)

1. **Coordinate tools.** Upload `samples/generated/with_metadata.jpg` and analyse it: the Coordinate tools panel shows `51.500000, -0.120000` alongside the DMS, DDM, and ISO 6709 forms. Add a location candidate with coordinates and the panel gains a second point plus the distance and bearing between them.
2. **Nothing invented.** Upload `invalid_location.jpg`: the coordinate stays in the Location clues panel exactly as written, and the Coordinate tools panel does not appear — a flagged value is never used for geometry.
3. **Cases.** In the artifact sidebar, type a case name and click "Create and add this artifact". The Chain of custody panel gains "Added to a case". Remove it and you get "Removed from a case", with the earlier event still there. Delete the case (`DELETE /api/v1/cases/<id>`) and confirm the artifact and its evidence are untouched.
4. **Integration, off.** `curl localhost:8400/api/v1/integration/version` shows `enabled: false` and lists only GET endpoints; requesting evidence returns 409 with the reason.
5. **Integration, on.** Enable "Integration API" in Settings, then `curl localhost:8400/api/v1/integration/artifacts/<id>/evidence`: one envelope with the report, the custody trail, and the artifact's cases. Try `curl -X POST` or `-X DELETE` against it — every write verb is refused by routing itself, and the Chain of custody panel shows no event for your reads.

## Manual test of Pass 2 (structure, forensics, documents)

1. **Appended data.** Build fixtures (`python -m tests.fixtures.make_fixtures`) and upload `samples/generated/png_with_zip.png`: the Structure panel lists the trailing data with its offset and size, plus both ZIP signatures, and frames them as a place to look rather than a conclusion.
2. **A clean file.** Upload `samples/generated/base.jpg`: "Nothing structurally unusual was found" — followed immediately by the statement that this is *not* a finding that the file is clean.
3. **Forensic indicators.** The same image shows its quantisation tables with the quality they imply for the last save, its channel statistics, and decoded-vs-declared dimensions. There is no ELA overlay anywhere, by design.
4. **A PDF.** Upload `samples/generated/document.pdf`: the Document structure panel gives the version, page and object counts and the features present; Text in document shows the provisional text with its amber caveat; Images embedded in the document shows the extracted JPEG — and `sha256sum` of that derived file matches the JPEG the fixture embedded, byte for byte.
5. **Repeated saves and signatures.** Upload `document_updated.pdf`: the panel says the file was saved twice and that this is normal annotation, not tampering. Any document with a signature structure says so *and* that Vestigo does not validate PDF signatures.
6. **Export and deletion** behave as for any evidence: the structural report, extracted text, and extracted images are derived files inside the package, and all are removed with the artifact.

## Manual test of local AI (Pass 1)

Everything below works with local AI **off** except where it says otherwise — that is the point.

1. **Off by default.** Open any artifact: the "AI assistant (drafts, not evidence)" panel shows the AI-generated-unverified label, says nothing here is a finding, reports that vendor telemetry is disabled, and the "Ask the local model" button is disabled with the reason given. `curl localhost:8400/api/v1/ai/status` shows every capability false, `telemetry_disabled: true`, `offline_enforced: true`, and all three models listed with Apache-2.0 and their Hugging Face URLs, `installed: false` — with `runnable` separating "the file is here" from "an engine could load it".
2. **Semantic search with no model at all.** Enable "Semantic search" in Settings. Add a note to an artifact, then press "Index" from the AI panel (or `POST /api/v1/ai/artifacts/<id>/index`). Go to **Search**, search a word from your note: your own record comes back with its source kind and score. Ask a question: the answer section says this runtime has no text-generation model and returns your material exactly as recorded — no invented prose.
3. **Drafts, live (needs the runtime and an engine).** Install the `ai` extra and run `needle fetch --generation 2`. In Settings, leave the draft model as "Use the model the engine carries" and enable "AI drafts". Ask for fields from metadata: each proposed field shows the model's value, its own confidence where given, and Accept / Edit / Reject. Edit one — the model's value stays visible beside yours, and the evidence report is unchanged. Ask for a field the text does not state and you get nothing back for it, with a warning: the engine's own grounding check refuses values it cannot find in the source, and Vestigo reports the refusal instead of hiding it.
4. **Staging a model file.** Settings → Local AI → *Import a model file*, or copy a `.cact` archive into `data/models/`. Either way it appears in the list with its size and digest, and can be chosen for drafts. Try to remove one while a setting points at it: refused, with the field named. Restart the backend — `tmp/` and `trash/` are cleared, your staged model is not.
5. **Transcription says why not.** Enable "Transcription" and press "Transcribe audio locally" on an audio artifact: a 409 explains that the vendor publishes no generation 3 engine. Confirm it left nothing behind — no new derived file under `data/artifacts/<id>/derived/`, and no custody event. A turned-off feature must not write derived evidence on its way to refusing.
6. **Nothing leaks, and nothing is fetched.** Grep the backend log: no prompts, draft values, transcript text, or vectors — only artifact ids and event names. Disconnect the network and generate a draft: it still works from the staged engine. Point the draft model at a path that does not exist: `/ai/status` reports drafts unavailable **and echoes the bad path**, rather than claiming to be ready.
7. **Custody, export, deletion.** The Chain of custody panel gains the AI events (names only). Export the package: `ai/README.txt` says it is not evidence, `ai/drafts.json` and `ai/transcripts.json` hold the material, and `report.json` has none of it. Delete the artifact: the summary counts `ai_drafts`, `transcripts`, and `embedding_chunks`, and all are gone.

## Manual test of location clues (M6)

1. **Coordinates as written.** Upload `samples/generated/with_metadata.jpg` (build fixtures with `python -m tests.fixtures.make_fixtures`): the Location clues panel shows `51.5, -0.12` beside the original `51 deg 30' 0.00" (North)` / `(West)` strings, the IPTC city "Testville", the EXIF date, and the camera fields — each with its tag, and the footer repeating that every value is as written and never proof of where the media was captured.
2. **Southern hemisphere and altitude.** Upload `southern_location.jpg`: `-33.8688, 151.2093`, altitude 58.4 m (Above Sea Level), GPS date/time, and the XMP place tags.
3. **A bad value stays bad.** Upload `invalid_location.jpg`: the coordinate is badged "Unusable value" with "latitude 191.5 is outside ±90", kept exactly as written, and offered no map link; the stage shows as partial.
4. **Absence.** Upload any plain photo: "No location metadata was found. Absence proves nothing."
5. **Video container location.** Upload `video_location.mp4`: coordinates parsed from the container tag, with the tag listed under "Container location tags".
6. **Map link, opt-in.** With the setting off, the panel says external map links are off. Enable "External map links" in Settings (note the warning and OSM terms link) and reload: "Open in OpenStreetMap (external)" appears with its warning; clicking opens a new tab whose URL carries exactly those coordinates. Vestigo loads no tiles and never sends anything by itself.
7. **Candidates.** Record a candidate: place, a basis, an assessment you must choose yourself, optional coordinates, and a tick against a supporting evidence record. It lists as UNVERIFIED with "the analyst's own judgment, not a measurement". Change the assessment → the Chain of custody panel gains "Location candidate edited" naming the field; delete it (two-step) → "Location candidate deleted" with the earlier events intact.
8. **Export and deletion.** An exported package's `report.json` carries both `location_clues` and the candidates, `custody.json` their events; deleting the artifact counts `location_candidates` and removes everything.
9. **Logs.** Grep the backend log: no coordinates anywhere, only artifact ids and event names.

## Manual test of reverse-image search (M5)

1. **Gating.** On a fresh database, open an image artifact: the Reverse-image search panel lists every provider as "enable in Settings". In Settings, tick TinEye (note the terms link and the policy note), save, and reload the artifact: "Open TinEye" appears with upload instructions.
2. **Nothing transmitted.** Click "Open TinEye": a new tab opens on tineye.com with a bare URL — no parameters, nothing about your evidence. The sharing warning sits above the provider links.
3. **Subject download.** Click "Download original image" (or, on an analysed video, pick a keyframe thumbnail first — the playable preview is never offered — then "Download selected keyframe"): the exact file saves as an attachment. Upload it manually on the provider page.
4. **Record a lead.** Fill the form with the result URL and the page's publication date as written. The lead shows EXTERNAL / Unreviewed, "Recorded <now>", and "Publication date (analyst-reported, unverified): <your text>" as separate lines, plus the never-proof-of-origin notice.
5. **Custody trail.** The Chain of custody panel gains lead_recorded; change the lead's review state or notes → lead_updated naming the fields; delete it (two-step confirm) → lead_deleted, with the earlier events still present.
6. **Export and deletion.** An exported package's report.json carries the leads and custody.json their events; deleting the artifact counts external_leads in the summary and removes everything.
7. **Audio.** An audio artifact page has no search panel, and the API refuses audio leads.

## Manual test of the chain of custody (M4B)

1. **Timeline.** Open any artifact: the Chain of custody panel lists the upload and each analysis with its record and file counts, and states it is not a legal chain of custody. Change the review state, exclude the artifact from the duplicate library, or export the evidence package — the timeline gains one factual line per action (reload or switch jobs to refresh after an export).
2. **Lineage.** On a video analysed with keyframe OCR, the lineage tree shows the TSVs indented under the exact keyframe thumbnails they were read from; everything else sits directly under "original upload".
3. **Export.** Unzip an evidence package: `custody.json` is listed in `manifest.json` and `SHA256SUMS`. Export twice — the second package's custody.json contains the first export with its package SHA-256, and never its own.
4. **No invented history.** A no-op library save adds nothing; artifacts analysed before this version show their derived files with "source not recorded".
5. **Deletion.** Delete an artifact: the deletion summary counts its custody events, and they are gone with everything else.

## Manual test of Milestone 4 (C2PA)

1. **Signed media.** Build the fixtures (`python -m tests.fixtures.make_fixtures`, which writes to `samples/generated/`) and upload `samples/generated/c2pa_signed.jpg`, `c2pa_signed.mp4`, or `c2pa_signed.wav`: the Content Credentials panel shows **Valid** with the test signer's details, the assertion labels, the `signingCredential.untrusted` code (no trust list), and the caveat that valid never means truthful.
2. **Tampered copy.** Upload `samples/generated/c2pa_tampered.jpg`: the panel shows **Invalid** with the recorded hash-mismatch code, worded as a finding, not a tampering verdict.
3. **Two manifests.** Upload `samples/generated/c2pa_double.jpg`: the panel lists both manifests with the active one flagged and the ingredient chain counted.
4. **Ordinary media.** Upload any unsigned photo, video, or audio file: the panel shows **Absent** and explains that absence proves nothing.
5. **Audit trail.** Export the evidence package: `manifest_store.json` is inside with a verified hash. Delete the artifact: the raw report is removed with everything else.
6. **Option.** Untick "Content Credentials (C2PA) validation" when uploading a video or audio file (or in Settings defaults): the stage is skipped with a recorded reason.

## Limitations

- Structural findings and forensic measurements are **not verdicts**. Vestigo never reports that hidden data was found, never reports that a file is clean, applies no threshold to any measurement, and does not implement error-level analysis. An implied JPEG quality describes the last save only.
- PDF **signature presence is not signature validity**: certificates and signer trust are never checked. Document text is provisional like OCR, extracted images are stored streams rather than rendered pages, and nothing in a document is rendered, executed, or decrypted.
- Location metadata is a **clue, not a location**: it is read as written, is trivially edited or copied, and never proves where media was captured. Absence proves nothing. Flagged coordinates are kept as written, disagreeing sources are both shown, and no place names are extracted from OCR text. Location candidates are analyst statements (UNVERIFIED) with the analyst's own assessment label — never a machine confidence score, and never a finding that media was captured somewhere.
- A **valid** C2PA / Content Credentials result means the manifest's hashes and claim signature verify — never that the content is truthful, accurate, or unmanipulated. No trust list is configured, so the signer's identity is not established. Absence of C2PA data proves nothing; most media has none and many platforms strip it.
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
│   └── pipeline/         # stage interface, image/video/audio pipelines, job runner
├── web/                  # React + Vite + TypeScript + Tailwind frontend
├── tests/                # pytest suites and test fixtures
├── samples/              # local media for manual testing (gitignored)
└── scripts/              # setup, environment check, dev servers
```

## Development rule

Do not begin implementation from prompts alone. Claude Code must first read all files in `docs/`, produce a build plan, and wait for approval.