# Setup, Operation, Handoff, and Integration

This is the single document to read before you run, maintain, or integrate Vestigo Media Forensics.
It assumes no prior contact with the project and no knowledge of the conversations that produced it.

Everything here was checked against the code in this repository, not against intentions. Where the
code and an older document disagree, this file says so.

- **Sections 1–3** get a working environment: Windows + WSL2, Docker, the Dev Container.
- **Sections 4–7** run the thing, configure it, and explain where files land.
- **Section 8** is the folder structure.
- **Sections 9–11** are the operational routine: tests, migrations, troubleshooting.
- **Section 12** is the handoff: current state, the rules that must not be broken, known gaps.
- **Section 13** is integration with other systems, including Vestigo and Cognitive / Oak Audit.
- **Section 14** is reference: the full API surface, ports, error envelope.

---

## 1. What this is, in one page

A **local-first media forensics service** for a single analyst on their own machine. You upload an
image, video, audio file, or PDF; it runs a pipeline of analysis stages; it records each result as an
evidence record with its method, tool, tool version, timestamps, source, limitations, and errors; and
it serves a JSON evidence report plus a React review UI.

Shape of the system:

```text
Browser (React, port 5180)
  → FastAPI (port 8400, /api/v1)
  → local file storage (data/)
  → background analysis job (thread pool)
  → pipeline stages (hash, metadata, C2PA, structural, forensics, pHash, OCR, duplicates, …)
  → SQLite evidence records (data/app.db)
  → JSON evidence report → review UI → signed-by-hash evidence package (ZIP)
```

What it deliberately **is not**, and what you must not turn it into without a deliberate decision:

- It issues **no verdicts**. It never reports that a file is manipulated, authentic, clean, or that
  hidden data was found, and it applies no threshold to any measurement. Measurements are reported
  as numbers with their method and limits.
- It makes **no outbound HTTP requests** from the backend. Reverse-image search is manual-first: the
  analyst opens a provider's plain landing page themselves. No media, prompt, embedding, coordinate,
  or evidence is uploaded anywhere.
- It has **no login and no multi-user model**. One analyst, one machine.
- It **deletes nothing automatically**.
- AI output is **never evidence**. It is unverified model output the analyst accepts, edits, or
  rejects, stored and exported separately under `ai/`.
- Location metadata is a **clue, not a location**. C2PA "valid" means hashes and a signature verify,
  never that content is truthful.

These are not stylistic preferences. They are the reason the evidence model is trustworthy, and every
stage, endpoint, and UI panel is written to hold them.

---

## 2. Host prerequisites

### 2.1 Windows 10/11 with WSL2 (the environment this was built in)

This project was developed inside a VS Code Dev Container on WSL2. That is the best-tested path.

**Step 1 — Install WSL2.** In an administrator PowerShell:

```powershell
wsl --install -d Ubuntu
wsl --set-default-version 2
wsl --update
wsl --status            # confirm: default version 2
```

Reboot if asked. Then open Ubuntu once and create your Linux user.

**Step 2 — Install Docker Desktop with the WSL2 backend.**
Download Docker Desktop for Windows, install it, then in **Settings → General** make sure *Use the
WSL 2 based engine* is ticked, and in **Settings → Resources → WSL Integration** enable integration
with your Ubuntu distribution. Verify from inside Ubuntu:

```bash
docker --version
docker run --rm hello-world
```

**Step 3 — Install VS Code on Windows** plus two extensions: **WSL** and **Dev Containers**
(`ms-vscode-remote.remote-wsl`, `ms-vscode-remote.remote-containers`).

**Step 4 — Clone inside the Linux filesystem, not `/mnt/c`.**

```bash
mkdir -p ~/projects && cd ~/projects
git clone https://github.com/<your-account>/vestigo-media-forensics.git
cd vestigo-media-forensics
code .                  # opens VS Code on Windows, attached to WSL
```

Cloning into `/mnt/c/Users/...` works but is markedly slower for the thousands of small file reads
that `npm`, `pytest`, and Vite do, and Windows drive mounts do not carry Linux file modes — which
matters here because `scripts/*.sh` must stay executable and the pipeline writes files it later
checks. Keep the repository on the ext4 side.

**Step 5 — Give WSL2 enough resources.** FFmpeg keyframe extraction and the frontend build are the
heavy steps. Create or edit `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
memory=8GB          # 4GB works; 8GB is comfortable with the frontend build running
processors=4
swap=4GB
```

Then `wsl --shutdown` from PowerShell and reopen. Without this, WSL2 takes a default share of host
RAM that is usually fine, but `npm run build` plus a video analysis at the same time can hit it.

**Disk:** the container image and dependencies are roughly 3–4 GB. Evidence storage grows with what
you analyse: each artifact keeps its original, its derived tool outputs, and any preview. Budget
generously and watch `data/`.

### 2.2 Linux

Install Docker Engine (not just the CLI) and add yourself to the `docker` group, install VS Code and
the Dev Containers extension, then clone and `code .`. Nothing else differs.

### 2.3 macOS

Docker Desktop for Mac plus the Dev Containers extension should work — the base image is published
multi-architecture — but this path is untested here. One known limit: the optional local AI runtime
was only verified on `linux-x86_64`.

### 2.4 Without Docker at all

The Dev Container is a convenience, not a requirement — the application is a plain Python package
plus a Vite app. On a Linux host with Python 3.11 and Node LTS:

```bash
sudo apt-get update
sudo apt-get install -y exiftool tesseract-ocr libtesseract-dev ffmpeg
python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install "c2pa-python>=0.38"     # see §3.4 — not yet declared in pyproject.toml
(cd web && npm ci)
bash scripts/verify-env.sh
```

Python 3.11 specifically: `verify-env.sh` asserts `(3, 11)`, and `pyproject.toml` requires `>=3.11`.

---

## 3. The Docker / Dev Container setup

### 3.1 What the container is

`.devcontainer/devcontainer.json`, in full:

| Key | Value | Why |
|---|---|---|
| `image` | `mcr.microsoft.com/devcontainers/python:3.11` | Python 3.11, Debian base, non-root `vscode` user with passwordless `sudo` |
| `features` | `ghcr.io/devcontainers/features/node:1` (LTS) | Node for the Vite frontend; pinned in `devcontainer-lock.json` to feature 1.7.1 by digest |
| `postCreateCommand` | `bash scripts/post-create.sh` | one-time provisioning, below |
| `forwardPorts` | `8400`, `5180` | labelled "Backend API" and "Frontend UI" in the VS Code Ports view |

There is no Dockerfile and no docker-compose file. The image is used as published; everything else is
installed by the post-create script, so the environment is reproducible from this repository alone.

### 3.2 What `scripts/post-create.sh` installs

Runs **once**, when the container is created (and again on a rebuild):

```bash
sudo apt-get install -y exiftool tesseract-ocr libtesseract-dev ffmpeg
python -m pip install -e ".[dev,ai]"      # drop ",ai" for a build with no local AI runtime
(cd web && npm ci)                        # only if web/package-lock.json exists
bash scripts/verify-env.sh
```

| Tool | Used for | Required? |
|---|---|---|
| ExifTool | EXIF / XMP / IPTC metadata, numeric GPS read, PDF metadata | yes |
| Tesseract OCR (+ `eng`) | image and keyframe OCR, provisional document text | yes |
| FFmpeg | keyframe extraction, scene detection, playable previews | yes (video/audio) |
| ffprobe | container, stream, codec, duration validation | yes (video/audio) |
| binwalk v3 | signature scan inside the structural stage, extraction always disabled | **optional**, not installed by default |
| `c2pa-python` | local C2PA / Content Credentials validation | yes — see §3.4 |
| `cactus-needle` | optional local AI runtime | optional (`.[ai]`) |

The AI extra installs the runtime only. It downloads **no model and no engine** — staging weights is
a separate deliberate step (§6), never a side effect of a container build.

### 3.3 Verifying the environment

```bash
bash scripts/verify-env.sh              # tools only
bash scripts/verify-env.sh --servers    # also checks 8400 and 5180 are answering
```

It prints `ok` / `MISSING` per tool and exits non-zero if anything required is missing. The local-AI
block is informational: a container with **no** runtime and **no** staged engine prints `absent` and
still passes, because that is a correct, supported setup.

```text
Tools:
  ok       python       3.11.x
  ok       node         v26.13.0
  ok       exiftool     12.xx
  ok       tesseract    5.x.x
  ok       ffmpeg       ffmpeg version ...
  ok       ffprobe      ffprobe version ...
  ok       ocr-lang     eng
Local AI (optional):
  ok       runtime      3.2.10
  ok       engine v2    /home/vscode/.cache/cactus-needle/v2/2.0.4/...
  absent   engine v3    stage with: needle fetch --generation 3
All checks passed.
```

### 3.4 One known gap you will hit on a fresh clone

`app/services/c2pa.py` imports `c2pa` at module level, and the analysis pipelines import that module,
so the backend cannot start without it. **`c2pa-python` is not declared in `pyproject.toml`**, even
though `docs/10-DEPENDENCIES.md` states it is pinned there. It is present in the original development
container because it was installed by hand.

Until that is fixed in `pyproject.toml`, a fresh environment needs one extra line:

```bash
python -m pip install "c2pa-python>=0.38"
```

Symptom if you skip it: `ModuleNotFoundError: No module named 'c2pa'` when starting uvicorn or
running `pytest`. `numpy` and `scipy`, which the forensic measurements use, are *not* a gap — they
arrive as transitive dependencies of `imagehash`.

### 3.5 Rebuilding and resetting

| Goal | How |
|---|---|
| Re-run provisioning | Command Palette → **Dev Containers: Rebuild Container** |
| Rebuild from a clean image | **Dev Containers: Rebuild Container Without Cache** |
| Reset dependencies only | `python -m pip install -e ".[dev,ai]"` and `(cd web && npm ci)` |
| Reset all evidence and the database | stop the backend, delete `data/`, restart — it is recreated and migrated from scratch |

Deleting `data/` destroys every artifact, evidence record, custody trail, case, and setting stored in
the database. It is gitignored and never committed, so nothing in git can restore it. Copy it first.

---

## 4. Running it

All commands run **inside the container, from the repository root**.

### 4.1 Backend — port 8400

```bash
scripts/dev-backend.sh
# equivalent: uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8400
```

- Health: <http://localhost:8400/api/v1/health>
- Interactive API docs (Swagger UI): <http://localhost:8400/api/v1/docs>
- OpenAPI JSON: <http://localhost:8400/api/v1/openapi.json>

On startup the backend prepares `data/`, migrates `data/app.db` to the latest schema, sets Pillow's
pixel ceiling from configuration, and recovers jobs that were interrupted by a previous shutdown.

`--host 0.0.0.0` is safe here because it binds inside the container and VS Code forwards the port to
your localhost. **There is no authentication of any kind.** If you ever run this outside a Dev
Container on a machine others can reach, bind `127.0.0.1` and do not forward 8400 publicly.

### 4.2 Frontend — port 5180

In a second terminal:

```bash
scripts/dev-frontend.sh
# equivalent: cd web && npm run dev
```

Open <http://localhost:5180>. Vite proxies `/api` to the backend, so **start the backend first** or
the first page load will show API errors.

### 4.3 First pass through the UI

1. **Upload** a JPEG. With *Automatic analysis after upload* on (the default), analysis starts at
   once; otherwise press Analyse.
2. **Library** (the home page) lists artifacts with status, problems, duplicate matches, and review
   state. Search, filter chips, and sort are all kept in the URL, so a reload restores the view.
3. **Artifact page** shows one panel per evidence section — hashes, metadata, Content Credentials,
   structural, forensic indicators, location, pHash, OCR, duplicates, custody, and the video/audio
   panels where they apply.
4. **Review** each record or the artifact as a whole; notes and state changes are appended to an
   immutable history.
5. **Export** the evidence package: a ZIP whose `manifest.json` and `SHA256SUMS` cover every file,
   with the whole archive's SHA-256 returned in the `X-Vestigo-Export-SHA256` response header.

`README.md` carries detailed manual acceptance walkthroughs per milestone — video, audio, C2PA,
custody, reverse-image search, location clues, Pass 2 panels, Pass 3, and local AI. Use those as
smoke tests after any change.

---

## 5. Configuration

Two layers, deliberately separate.

### 5.1 Environment settings — restart to apply, read-only in the UI

Read from `VESTIGO_*` environment variables or a `.env` file in the repository root. Copy
`.env.example` to `.env` to override. Every setting is optional; the defaults below are the real
defaults from `app/core/config.py`.

| Variable | Default | Meaning |
|---|---|---|
| `VESTIGO_DATA_DIR` | `data` | Root of all storage, including `app.db` |
| `VESTIGO_MAX_UPLOAD_BYTES` | `52428800` (50 MiB) | Image upload ceiling |
| `VESTIGO_MAX_IMAGE_PIXELS` | `100000000` | Pixel ceiling; also sets Pillow's bomb guard |
| `VESTIGO_MAX_VIDEO_UPLOAD_BYTES` | `524288000` (500 MiB) | Video upload ceiling |
| `VESTIGO_MAX_VIDEO_DURATION_SECONDS` | `900` | Container-reported duration ceiling |
| `VESTIGO_MAX_VIDEO_PIXELS` | `8294400` | Frame-size ceiling (3840×2160) |
| `VESTIGO_MAX_KEYFRAMES` | `40` | Keyframes extracted per video (1–500) |
| `VESTIGO_SCENE_THRESHOLD` | `0.3` | FFmpeg scene-change sensitivity (0–1) |
| `VESTIGO_VIDEO_TIMEOUT_SECONDS` | `600` | Per-tool timeout for video work |
| `VESTIGO_MAX_AUDIO_UPLOAD_BYTES` | `209715200` (200 MiB) | Audio upload ceiling |
| `VESTIGO_MAX_AUDIO_DURATION_SECONDS` | `7200` | Audio duration ceiling |
| `VESTIGO_MAX_DOCUMENT_UPLOAD_BYTES` | `104857600` (100 MiB) | PDF upload ceiling |
| `VESTIGO_MAX_MODEL_BYTES` | `1073741824` (1 GiB) | Ceiling on an imported local AI model file |
| `VESTIGO_OFFLINE_MAP_PATH` | `""` | Offline map data *you* supply; nothing is ever downloaded |
| `VESTIGO_PHASH_MAX_DISTANCE` | `10` | Hamming distance for a duplicate match (0–64) |
| `VESTIGO_JOB_MODE` | `thread` | `thread` or `inline` (inline runs analysis synchronously — useful in tests) |
| `VESTIGO_JOB_WORKERS` | `2` | Analysis worker threads |
| `VESTIGO_TOOL_TIMEOUT_SECONDS` | `60` | Default external-tool timeout |
| `VESTIGO_OCR_TIMEOUT_SECONDS` | `120` | Tesseract timeout |
| `VESTIGO_CORS_ORIGINS` | `["http://localhost:5180","http://127.0.0.1:5180"]` | Allowed browser origins — **widen this to let another web app call the API from a browser** |
| `VESTIGO_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

Note the three documented-but-absent entries in `.env.example`: `VESTIGO_MAX_DOCUMENT_UPLOAD_BYTES`,
`VESTIGO_MAX_MODEL_BYTES`, and `VESTIGO_OFFLINE_MAP_PATH` exist in `config.py` and work as
environment variables; the example file predates them.

### 5.2 Analyst settings — stored in the database, editable on the Settings page

`GET /api/v1/settings` returns both layers; `PATCH /api/v1/settings` changes only this one.

| Setting | Default | Meaning |
|---|---|---|
| `default_analysis_options` and the video / audio / document variants | all checks on | Which stages run when none are specified |
| `library_page_size` | `25` | Library page size |
| `auto_analyze_after_upload` | `true` | Start analysis as soon as an upload finishes |
| `enabled_search_providers` | `[]` | Reverse-image providers the analyst has enabled — **all off** |
| `enable_external_map_links` | `false` | Offer a browser-built OpenStreetMap link for coordinates |
| `ai_enabled` | `false` | Local AI drafts |
| `transcription_enabled` | `false` | Local transcription (currently cannot run — §6) |
| `semantic_search_enabled` | `false` | Local semantic index and search |
| `integration_api_enabled` | `false` | The read-only integration surface (§13) |
| `ai_model_path`, `transcription_model_path` | `""` | Explicit local `.cact` model files |

Everything that could reach outside the machine, or produce machine-written text, is **off by
default**. Keep that property.

---

## 6. Local AI (optional, and partly blocked upstream)

The runtime is `cactus-needle` 3.2.10 (Apache-2.0, CPU-only), declared as the optional `.[ai]` extra.
A stock build has no AI dependency at all and the whole test suite passes without it.

**Staging an engine is the only step that touches the network, and it is never part of a build:**

```bash
needle fetch --generation 2     # ~14 MB into ~/.cache/cactus-needle/v2/2.0.4/
```

What actually runs, verified on `linux-x86_64`:

| Capability | State |
|---|---|
| Structured extraction / tool calling (generation 2) | **works** — measured 0.96 s cold, 0.67 s warm, 47 MB peak RSS on an i7-1165G7 |
| needle3 (generation 3 weights) | **cannot run** — the vendor publishes the weights, a checkpoint, and a tokenizer, but no engine for any platform; the pinned 3.3.3 wheel 404s |
| Whistle transcription | **cannot run** — it loads through that same generation 3 engine |
| Model text embeddings | **cannot run** — `Needle.embed` raises "embeddings require a Needle 3 model"; `LocalHashEmbedder` is used instead |
| Free-text generation | **not available** — `complete()` with no tools returns an empty call, so Vestigo drafts no prose |

These are upstream publishing gaps, not hardware limits. The code stays wired and reports the real
reason rather than degrading silently. Re-check the vendor's Hugging Face repositories before
assuming it is still blocked.

Operational facts worth knowing before you touch `app/services/ai/`:

- The runtime downloads missing weights **at load time** and pings the Hub even on a warm cache, so
  `HF_HUB_OFFLINE=1` is forced at import. Passing an explicit `weights=` path skips the ping.
- The engine is single-model and **not thread-safe**; every call holds `ENGINE_LOCK`.
- Real API: `needle.extract(text, schema, weights=, generation=, strict=)` takes an OpenAI-style tool
  schema and returns the plain arguments mapping. `needle.transcribe` returns flat text plus a
  `words` list — there is no `segments` key.
- Real environment variables: `NEEDLE_TELEMETRY`, `DO_NOT_TRACK`, `NEEDLE2_LIB_PATH`,
  `NEEDLE3_LIB_PATH`, `NEEDLE_WHISTLE_WEIGHTS`, `NEEDLE_HF_REPO`. **No `CACTUS_*` variable is read by
  this package.** The CLI is `needle`, not `cactus`.
- `needle platform finetune` uploads to the vendor's GPUs and is never called.
- Imported model files live in `data/models/`, which Storage creates and deliberately excludes from
  the tmp/trash wipe.
- Tests that load a real model are marked `live_model` and excluded by default:
  `python -m pytest -m live_model`. `tests/unit/test_ai_providers.py` covers the adapters with a
  stand-in module, so it runs whether or not the runtime is installed.

---

## 7. Where files live at runtime

`$VESTIGO_DATA_DIR` (default `data/`, gitignored) is the entire state of the system:

```text
data/
├── app.db                              SQLite: artifacts, jobs, evidence, review, custody, cases, settings
├── artifacts/
│   └── art_<32 hex>/
│       ├── original/                   the upload, byte-for-byte, never modified
│       ├── derived/<job_id>/           raw tool output per analysis job (ExifTool JSON, keyframes,
│       │                               C2PA manifest store, binwalk output, PDF images, …)
│       └── preview/preview.mp4         on-demand viewing copy; labelled, and never evidence
├── models/                             local AI model files you imported
├── tmp/                                work area; wiped on startup
└── trash/                              staging for deletion; wiped on startup
```

Nothing is deleted automatically. Deletion is explicit, via the UI or
`DELETE /api/v1/artifacts/{id}`, and removes the files, evidence records, and database rows together.

---

## 8. Repository structure

```text
vestigo-media-forensics/
├── README.md                     capability tour + manual acceptance walkthroughs per milestone
├── pyproject.toml                backend package, dependencies, extras, pytest and ruff config
├── alembic.ini                   developer access to migrations (the app migrates itself at startup)
├── .env.example                  every environment setting with its default
├── .devcontainer/
│   ├── devcontainer.json         image, Node feature, postCreate, forwarded ports
│   └── devcontainer-lock.json    the Node feature pinned by digest
├── scripts/
│   ├── post-create.sh            one-time provisioning
│   ├── verify-env.sh             tool + optional-AI + optional-server checks
│   ├── dev-backend.sh            uvicorn on 8400 with reload
│   └── dev-frontend.sh           Vite on 5180
├── docs/                         specifications, approved plans, and decision records (§12.4)
├── app/                          FastAPI backend
│   ├── main.py                   application factory: CORS, upload limit, error handlers, routers
│   ├── core/
│   │   ├── config.py             VESTIGO_* settings
│   │   ├── database.py           SQLAlchemy engine, reader/writer sessions
│   │   ├── migrations.py         startup migration, with a refusal if the DB is from a newer build
│   │   ├── storage.py            the data/ layout above, path-traversal-safe
│   │   ├── tools.py              external-tool registry and health
│   │   ├── errors.py, logging.py, ids.py, clock.py, container.py
│   ├── api/                      one routes_*.py per area, plus deps.py and upload_limit.py
│   ├── schemas/                  Pydantic request/response contracts (the API's real spec)
│   ├── models/                   SQLAlchemy tables
│   ├── services/                 the work: hashing, metadata, c2pa, structural, forensics, pdf,
│   │                             phash, ocr, duplicates, keyframes, scenes, previews, media_info,
│   │                             location*, geo*, leads, cases, custody, review, library, reports,
│   │                             exports, semantic, transcripts, ai_drafts, ai_models, ai/
│   ├── pipeline/                 stage interface, image/video/audio/document pipelines, job runner
│   └── migrations/versions/      0001 baseline … 0009 cases (schema v9)
├── web/                          React 19 + Vite + TypeScript + Tailwind 4
│   └── src/
│       ├── api/                  axios client and generated-by-hand response types
│       ├── pages/                Library, Artifact, Upload, Settings, SemanticSearch (+ their tests)
│       ├── components/           layout and shared UI
│       │   ├── evidence/         one panel per evidence section
│       │   ├── library/          table, filter bar, bulk review
│       │   └── review/           review context, record review, history, conflicts
│       ├── lib/                  formatting, library URL state, settings context, fetch hook
│       └── test/                 MSW server, render helper, fixtures
├── tests/                        pytest: unit, pipeline, api, db, container, live_ai, fixtures
├── samples/                      local media for manual testing (gitignored except .gitkeep)
└── data/                         runtime state (gitignored; see §7)
```

---

## 9. Tests, lint, and build

All five of these must pass before any commit. That is a project rule, not a suggestion — the suites
pin existing behaviour, and this is evidence software where a silent regression is a correctness
failure.

```bash
python -m pytest                 # backend: unit, pipeline, API, migrations (hermetic)
python -m pytest -m container    # tools, SQLite, and ports 8400/5180 (starts servers if needed)
ruff check app tests             # backend lint
(cd web && npm test)             # frontend: Vitest + MSW (hermetic, no servers needed)
(cd web && npm run build)        # TypeScript type check, then production build
```

Two extra suites are excluded by default and run on purpose:

```bash
python -m pytest -m live_model   # loads a real local AI model; needs the runtime and staged weights
```

```bash
# Drives the real UI against running servers, to catch what a hermetic suite cannot:
# a blank page, a proxy or CORS problem, a failed API call, a runtime JavaScript error.
# Start both servers first.
(cd web && npx vitest run --config browser-acceptance.config.ts)
# Optionally: VESTIGO_TEST_ARTIFACT=<artifact id> to also render that artifact and assert
# every evidence panel is present.
```

`pyproject.toml` sets `addopts = "-m 'not container and not live_model'"`, which is why the plain
`pytest` run is hermetic and fast.

Measured in this container on 2026-11-10, for a baseline to compare against: `pytest` → **505 passed,
14 deselected** (the container and live-model suites) in 13m09s; `npm test` → **163 passed in 23
files**; `ruff check app tests` → clean; `npm run build` → clean.

---

## 10. Database and migrations

- The backend migrates `data/app.db` to the latest schema **when it starts**. There is nothing to run
  by hand in normal use.
- Migrations are **additive**: an older database is upgraded in place and existing rows are not
  rewritten.
- If the database was written by a *newer* build of Vestigo, the backend **refuses to start** and
  leaves it untouched.
- Upgrades run in one transaction. There are **no downgrades** — copy `data/` before moving to a
  build you may need to step back from.
- Current head: `0009_pass3_cases` (schema v9). Baseline `0001_m1_baseline`.

For development, from the repository root:

```bash
alembic current
alembic revision -m "describe the change"
```

Never edit a revision that has been applied anywhere; add a new one. Any new table that holds
evidence or analyst statements must also get export, deletion, custody, and migration coverage — see
§12.3.

---

## 11. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'c2pa'` | `c2pa-python` is missing from `pyproject.toml` (§3.4): `pip install "c2pa-python>=0.38"` |
| Frontend loads but every API call fails | Backend not running, or started after the page. Start 8400 first, then reload 5180 |
| A browser app on another port gets CORS errors | Add its origin to `VESTIGO_CORS_ORIGINS` and restart the backend (§5.1) |
| `/health` reports `degraded` | A required external tool is missing. Run `bash scripts/verify-env.sh`; `tools` in the health response names the one that failed |
| Backend refuses to start, complaining about the schema | `data/app.db` was written by a newer build. Use that build, or move `data/app.db` aside to start fresh |
| Video analysis times out | Raise `VESTIGO_VIDEO_TIMEOUT_SECONDS`, or lower `VESTIGO_MAX_KEYFRAMES`; check WSL2 has enough CPU (§2.1) |
| Upload rejected as the wrong type | Media type comes from the file's **bytes**, never its name or extension. An MP4 with no real video stream is treated as audio, by design |
| `413` on upload | Over `VESTIGO_MAX_*_UPLOAD_BYTES`; the limit middleware rejects before the body is read |
| `409 INTEGRATION_DISABLED` | The integration API is off by default. Enable it in Settings (§13.2) |
| AI panel says unavailable | `ai_enabled` is off, the `.[ai]` extra is not installed, or no engine is staged. The response carries the real reason |
| Transcription will not run whatever you do | Upstream: no generation 3 engine is published (§6) |
| Ports not forwarded in VS Code | Check the Ports view; re-forward 8400 and 5180, or rebuild the container |
| `npm ci` fails after a pull | `web/package-lock.json` changed; delete `web/node_modules` and re-run |
| Dev Container build is very slow on Windows | The repository is probably on `/mnt/c`. Move it into the WSL2 filesystem (§2.1 step 4) |

Logs go to stdout at `VESTIGO_LOG_LEVEL`. Coordinates are deliberately never logged.

---

## 12. Handoff

### 12.1 Where the project stands

Every milestone on the roadmap is implemented. In order, with the decision record that describes
each: M1 image foundation; M2 analyst workflow (D15/D16); M3 video foundation (D17/D18); D19
cross-media search, more formats, audio, previews; M4 C2PA validation (D20); M4 part 2 chain of
custody (D21); M5 reverse-image search (D22); M6 GEOINT / geo-lite (D23); then three consolidated
passes — Pass 1 local AI (D24), Pass 2 deep forensics (D25), Pass 3 GEOINT tooling, cases, and
read-only integration (D26); and D27, which made local AI actually run and corrected what Pass 1 had
assumed about the vendor's API.

Database schema is at v9 (`0009_pass3_cases`).

### 12.2 The evidence model — the thing to understand first

Every analysis result is an evidence record carrying its stage name, status, output, tool, tool
version, start and completion timestamps, errors, limitations, and a classification fixed at creation
and never changed:

| Classification | Meaning |
|---|---|
| `OBSERVED` | Read directly from the artifact's bytes |
| `DERIVED` | Computed by Vestigo from the artifact |
| `EXTERNAL` | Came from outside, recorded by the analyst (e.g. a reverse-image lead) |
| `UNVERIFIED` | An analyst statement, not a finding (e.g. a location candidate) |
| `REVIEWED` | Carries an analyst review decision |

`docs/04-EVIDENCE-MODEL.md` is the authority. Read it before adding a stage.

### 12.3 Rules that must not be broken

These are invariants, enforced by tests and by the shape of the code:

1. **No verdicts.** Report measurements with their method and limits. Never "manipulated",
   "authentic", "clean", or "steganography detected". No thresholds on measurements.
2. **No outbound HTTP from the backend.** Ever. External lookups are the analyst's own action on the
   provider's site.
3. **Everything that reaches outside, or writes machine-generated text, is off by default.**
4. **AI output is not evidence.** It stays in its own records, its own panels, and its own `ai/`
   folder in exports, labelled as unverified model output.
5. **Changes are additive.** Do not remove an existing feature, endpoint, response field, setting,
   fixture, or stored row unless explicitly asked. Migrations upgrade in place.
6. **Custody is append-only**, and records only actions Vestigo can actually observe. A read is not
   a custody event.
7. **Nothing is deleted automatically**, and deletion is complete when it happens: files, evidence,
   and rows together.
8. **Claims need measurement.** Do not state an accuracy or performance figure in any document unless
   it comes from this project's own reproducible fixtures. (The maintainer's manual OCR test scored
   roughly 55% on their own images; that number is deliberately kept out of the docs because it does
   not come from the generated fixtures.)
9. **Five suites green before every commit** (§9).
10. **No facial recognition, biometric identification, person tracking, covert surveillance,
    scraping, CAPTCHA bypass, rate-limit evasion, paid APIs, cloud inference, or cloud storage.**

### 12.4 Where the reasoning is written down

`docs/` is not decoration; it is the project's memory.

| File | What it holds |
|---|---|
| `00-MASTER-SPEC.md` | the whole system in one place |
| `01-PRODUCT-SPEC.md`, `02-ARCHITECTURE.md` | intent and system shape |
| `03-API-SPEC.md` | every endpoint, in prose, with examples |
| `04-EVIDENCE-MODEL.md` | classifications, record structure, report schema |
| `05-SECURITY-PRIVACY.md` | upload safety, allowed inputs, external-service policy, prohibited capabilities, deletion, logging |
| `06-ROADMAP.md`, `17-CONSOLIDATED-CAPABILITY-ROADMAP.md` | what was planned, and the three final passes |
| `07-TEST-PLAN.md` | what is tested and why |
| `09-DECISIONS.md` | **every decision D1…D27 with its reasoning** — read this before reversing anything |
| `10-DEPENDENCIES.md` | each dependency, licence, source, and what it is for |
| `11`–`16` | the approved per-milestone build plans |
| `17-CAPABILITY-INTEGRATION-AUDIT.md` | capability research, licence notes, deferral rationale |
| `18-SETUP-AND-HANDOFF.md` | this document |

### 12.5 Adding an analysis stage

1. Read `docs/04-EVIDENCE-MODEL.md` and an existing stage in `app/services/` for the pattern.
2. Implement the stage interface from `app/pipeline/base.py`; return a `StageResult` with name,
   status, output, tool, tool version, timestamps, errors, limitations, and classification.
3. Register it in the relevant pipeline(s) in `app/pipeline/`, behind an analysis option.
4. Add the section to the evidence report schema in `app/schemas/evidence.py` as an optional field —
   never repurpose or remove an existing one — and bump `schema_version` only when the shape grows.
5. Add an Alembic revision if it needs storage, and cover export, deletion, custody, and migration.
6. Add the UI panel in `web/src/components/evidence/` and wire it into the artifact page.
7. Record the decision in `docs/09-DECISIONS.md`, extend `docs/03-API-SPEC.md` and
   `docs/07-TEST-PLAN.md`, and add manual acceptance steps to `README.md`.

### 12.6 Known gaps, honestly stated

- `c2pa-python` is missing from `pyproject.toml` (§3.4).
- `.env.example` is missing three settings that exist in `config.py` (§5.1).
- needle3, Whistle transcription, and model embeddings cannot run because the vendor publishes no
  engine (§6).
- OCR is best-effort, English only, and explicitly provisional — never a verified transcription.
  Keyframe OCR reads at most 10 sampled frames.
- Audio duplicate search is byte-identical only; no audio content is ever decoded or compared.
- Duplicate search covers only the local library, as it stood when each analysis ran.
- PDF signature **presence** is reported, never signature validity or signer trust. Nothing in a
  document is rendered, executed, or decrypted; extracted images are stored streams, not rendered
  pages.
- Video duration, frame rate, and similar values are container-reported metadata, not decode-verified
  measurements.
- Import of outside evidence is deliberately not implemented.
- `docs/02-ARCHITECTURE.md` still describes video, GEOINT, and reverse-image as future work. They are
  done; the file was not fully revised. Trust the code and `09-DECISIONS.md`.

---

## 13. Integrating Vestigo into another system

### 13.1 The contract

Vestigo exposes a **read-only integration surface**, versioned separately from the evidence report,
**disabled by default**. It has no write operation of any kind — not a guarded one, not an
authenticated one: none exists. An external system can never create, change, re-classify, or delete
an artifact, an evidence record, a review state, or anything else Vestigo holds. That is enforced by
the *absence of the endpoints*, not by a permission check that could be misconfigured.

| | |
|---|---|
| `integration_version` | `1.0` |
| `report_schema_version` | `1.2` |
| Prefix | `/api/v1/integration` |
| Auth | none — localhost trust boundary (§13.6) |
| Writes | none |

### 13.2 Turning it on

Either tick it on the Settings page, or:

```bash
curl -X PATCH http://localhost:8400/api/v1/settings \
  -H 'Content-Type: application/json' \
  -d '{"integration_api_enabled": true}'
```

Until then, evidence reads return `409` with code `INTEGRATION_DISABLED` and a message explaining
how to enable it. `GET /integration/version` is readable either way, so an integrator can discover
that the surface exists and is currently off.

### 13.3 The two endpoints

**`GET /api/v1/integration/version`** — always readable. Use it as your capability handshake.

```json
{
  "integration_version": "1.0",
  "report_schema_version": "1.2",
  "app_version": "0.1.0",
  "schema_revision": "0009_pass3_cases",
  "enabled": true,
  "notice": "Read-only integration view. …",
  "read_only_endpoints": [
    "GET /api/v1/integration/version",
    "GET /api/v1/integration/artifacts/{artifact_id}/evidence"
  ]
}
```

**`GET /api/v1/integration/artifacts/{artifact_id}/evidence`** — one versioned envelope:

```json
{
  "integration_version": "1.0",
  "notice": "Read-only integration view. …",
  "artifact_id": "art_0b9b…",
  "report":  { "schema_version": "1.2", "...": "the evidence report, exactly as Vestigo serves it" },
  "custody": { "...": "the chain of custody recorded on this machine" },
  "cases":   [ { "...": "cases this artifact was put in — organisation, not evidence" } ]
}
```

Optional `?job_id=` selects a specific analysis job; the latest is used otherwise. Reading writes **no
custody event** — Vestigo only records actions it can observe as changes to what it holds.

The report's own sections are nullable and media-specific: image jobs leave the video sections null
and vice versa. Treat every section as optional.

### 13.4 Worked examples

Shell:

```bash
BASE=http://localhost:8400/api/v1
curl -s $BASE/integration/version | jq '{integration_version, report_schema_version, enabled}'
curl -s $BASE/integration/artifacts/art_0b9b.../evidence | jq '.report.hashes'
```

Python, server-side:

```python
import httpx

BASE = "http://localhost:8400/api/v1"

def fetch_evidence(artifact_id: str, job_id: str | None = None) -> dict:
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        version = client.get("/integration/version").raise_for_status().json()
        if version["integration_version"].split(".")[0] != "1":
            raise RuntimeError(f"unsupported contract {version['integration_version']}")
        if not version["enabled"]:
            raise RuntimeError("the analyst has not enabled Vestigo's integration API")
        params = {"job_id": job_id} if job_id else None
        response = client.get(f"/integration/artifacts/{artifact_id}/evidence", params=params)
        if response.status_code == 409:
            raise RuntimeError(response.json()["error"]["message"])
        return response.raise_for_status().json()
```

TypeScript, from a browser app — remember the origin must be in `VESTIGO_CORS_ORIGINS` (§5.1):

```ts
const BASE = "http://localhost:8400/api/v1";

export async function fetchEvidence(artifactId: string) {
  const res = await fetch(`${BASE}/integration/artifacts/${artifactId}/evidence`);
  if (res.status === 409) {
    const { error } = await res.json();
    throw new Error(error.message);   // INTEGRATION_DISABLED
  }
  if (!res.ok) throw new Error(`Vestigo returned ${res.status}`);
  return res.json();
}
```

### 13.5 The other integration path: the evidence package

For anything asynchronous, archival, or across machines, prefer the export instead of a live call:

`GET /api/v1/artifacts/{id}/export` returns a ZIP containing `report.json`, `review.json`,
`custody.json`, `derived/`, optionally `original/`, an `ai/` folder when AI material exists, plus
`manifest.json` and `SHA256SUMS` covering every file. The whole archive's SHA-256 comes back in the
`X-Vestigo-Export-SHA256` response header.

Verify it, every time, before trusting anything inside:

```bash
sha256sum vestigo-evidence-art_….zip      # compare with X-Vestigo-Export-SHA256
unzip -q vestigo-evidence-art_….zip -d pkg && cd pkg && sha256sum -c SHA256SUMS
```

`manifest.json` also lists, under `"problems"`, any recorded file that was missing or whose SHA-256
did not match what was recorded when it was created. Surface those; never swallow them.

Note that the export's own event is recorded *after* the package is built, so it appears in the
*next* export's `custody.json`, not in this one. That is deliberate, not a bug.

### 13.6 Deployment and trust boundary

There is **no authentication**. The trust boundary is the machine.

- Keep the backend on `127.0.0.1` and have consumers run on the same host.
- If a consumer must be on another host, put it behind a reverse proxy that terminates TLS and
  authenticates, on a network you control. Do not expose 8400 to anything else.
- For a browser consumer, add its exact origin to `VESTIGO_CORS_ORIGINS` and restart. The API allows
  `GET`, `POST`, `PATCH`, `DELETE` with `Content-Type`, and exposes `Content-Disposition` and
  `X-Vestigo-Export-SHA256`.
- A server-side consumer needs no CORS change.
- Analysis is a background job. Poll `GET /analysis/jobs/{job_id}` at a human interval; do not hammer
  it, and do not poll the evidence endpoint as a progress check.

### 13.7 Integrating with Vestigo (the parent platform)

Recommended shape:

1. Run this service on the analyst's machine, alongside whatever Vestigo component needs it.
2. Enable `integration_api_enabled`, and call `/integration/version` **once per session** to pin the
   contract. Refuse to proceed on a major-version change rather than guessing.
3. Pull evidence by `artifact_id` through `/integration/artifacts/{id}/evidence`.
4. Mirror it **read-only**, keyed on `artifact_id` plus `report.job_id`. Store
   `integration_version`, `report_schema_version`, and `schema_revision` next to every mirrored
   record, so you can tell later which contract produced it.
5. Never write to `data/app.db`. It is SQLite on disk and therefore physically reachable; treat that
   as off-limits. The schema is migrated at startup by the owning application, custody triggers
   assume append-only writes, and a foreign writer breaks both. If Vestigo needs to *cause* something
   in this service, use the ordinary REST API (§14) as an operator would, deliberately and visibly —
   not the database.
6. Carry classifications and `notice` text through unchanged. If your UI shows an OCR string or a
   forensic measurement, it must still read as provisional and as a measurement. Do not aggregate
   sections into a score, a badge, or a verdict; the model has no such concept and adding one in a
   consumer breaks the guarantee the evidence rests on.
7. Keep AI material visually and structurally separate from evidence, as the export does.

### 13.8 Integrating with Cognitive / Oak Audit

An audit system wants provenance and a trail, not pixels. The useful shape:

1. **Pull, don't push.** Oak Audit calls Vestigo; Vestigo never calls out. That keeps the
   "no outbound HTTP" guarantee intact and leaves the integration auditable from one side.
2. **Anchor on hashes.** `report.hashes` carries the artifact's SHA-256 and MD5 as computed at
   analysis time. Store the SHA-256 as the audit record's identity, and re-verify it against the
   export whenever you take custody of bytes.
3. **Take the whole envelope, and keep it.** `report` + `custody` + `cases`, as received, with
   `integration_version`, `report_schema_version`, `schema_revision`, and your own fetch timestamp.
   An audit trail that reshapes its source cannot be audited.
4. **Prefer the evidence package for anything retained.** It is self-verifying (`manifest.json`,
   `SHA256SUMS`, the archive header hash) and does not depend on the service being up later.
   Record the archive's SHA-256 in the audit record.
5. **Reproduce the caveats verbatim.** Specifically: the custody trail is *not* a legal chain of
   custody — it starts at upload, holds only what this machine observed, and infers nothing. A C2PA
   `valid` result means hashes and a claim signature verify, with **no trust list configured**, so
   the signer's identity is not established. Absence of C2PA data proves nothing. An audit finding
   that drops these caveats misrepresents its source.
6. **Expect `UNVERIFIED`.** Location candidates and analyst statements are *statements*, with the
   analyst's own label (speculative / possible / likely) — never a machine confidence score. Render
   them as attributed statements, never as determinations.
7. **Read-only is the feature.** Oak Audit cannot change a review state, re-classify a record, or
   delete an artifact, and should not want to: an audit system that can edit its evidence is not an
   audit system. If a workflow seems to need a write, the answer is a new approved design in Vestigo,
   recorded in `docs/09-DECISIONS.md` — not a new endpoint bolted on.

### 13.9 Integrator's checklist

- [ ] Handshake on `/integration/version`; refuse on an unknown major version.
- [ ] Handle `409 INTEGRATION_DISABLED` as a normal state with a clear message, not a crash.
- [ ] Treat every report section as optional and media-specific.
- [ ] Preserve `notice` fields, classifications, method, tool, tool version, timestamps,
      limitations, and errors.
- [ ] Never present a measurement as a verdict, and never compute one.
- [ ] Re-verify SHA-256 before trusting exported bytes; surface `manifest.json` `"problems"`.
- [ ] Keep AI material labelled and separate.
- [ ] No writes to the database. No writes through the integration surface — there are none.
- [ ] Poll jobs at a human interval.
- [ ] Record which contract version produced each mirrored record.

---

## 14. Reference

### 14.1 Ports

| Service | Port | Notes |
|---|---|---|
| Backend API | 8400 | `/api/v1`, docs at `/api/v1/docs` |
| Frontend UI | 5180 | Vite dev server, proxies `/api` to 8400 |

### 14.2 API surface

Base: `http://localhost:8400/api/v1`. The live, authoritative version is always
`/api/v1/openapi.json`; `docs/03-API-SPEC.md` is the prose version.

| Area | Endpoints |
|---|---|
| Health | `GET /health` |
| Artifacts | `POST /artifacts/upload` · `GET /artifacts` · `GET /artifacts/{id}` · `DELETE /artifacts/{id}` · `GET /artifacts/{id}/content` · `GET /artifacts/{id}/derived/{derived_file_id}/content` |
| Analysis | `POST /analysis/image` · `/video` · `/audio` · `/document` (202) · `GET /analysis/jobs/{job_id}` · `GET /artifacts/{id}/jobs` |
| Evidence | `GET /artifacts/{id}/evidence` · `GET /artifacts/{id}/custody` · `GET /artifacts/{id}/export` |
| Review | `PATCH /artifacts/{id}/review` · `POST /artifacts/review` (bulk) · `GET /artifacts/{id}/review-history` · `PATCH /artifacts/{id}/evidence/{evidence_id}/review` |
| Library | `GET /library/summary` · `PATCH /artifacts/{id}/duplicate-library` |
| Previews | `POST /artifacts/{id}/preview` · `GET /artifacts/{id}/preview` · `GET /artifacts/{id}/preview/content` |
| External leads (M5) | `GET` / `POST` `/artifacts/{id}/external-leads` · `PATCH` / `DELETE` `…/{lead_id}` · `GET /search/providers` |
| Location (M6) | `GET` / `POST` `/artifacts/{id}/location-candidates` · `PATCH` / `DELETE` `…/{candidate_id}` · `GET /geo/artifacts/{id}/tools` |
| Cases (Pass 3) | `GET` / `POST` `/cases` · `GET` / `PATCH` / `DELETE` `/cases/{case_id}` · `PUT` / `DELETE` `/cases/{case_id}/artifacts/{artifact_id}` |
| Local AI | `GET /ai/status` · drafts `GET` / `POST` / `PATCH` / `DELETE` `/ai/artifacts/{id}/drafts…` · transcripts `…/transcripts…` · index `POST` / `DELETE` `/ai/artifacts/{id}/index` · `GET /ai/search` · `POST /ai/answer` · models `GET /ai/models` · `POST /ai/models/import` · `DELETE /ai/models/{name}` |
| Settings | `GET /settings` · `PATCH /settings` |
| Integration | `GET /integration/version` · `GET /integration/artifacts/{id}/evidence` |

### 14.3 Error envelope

Every error, from any endpoint:

```json
{
  "error": {
    "code": "INTEGRATION_DISABLED",
    "message": "The integration API is turned off. Enable it in Settings …",
    "details": {}
  }
}
```

`code` is a stable enum — switch on it, not on the message. Current values:
`MISSING_FILE`, `EMPTY_FILE`, `FILE_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `INVALID_IMAGE`,
`IMAGE_TOO_LARGE`, `INVALID_VIDEO`, `INVALID_AUDIO`, `AUDIO_TOO_LONG`, `VIDEO_TOO_LONG`,
`VIDEO_RESOLUTION_TOO_LARGE`, `WRONG_MEDIA_TYPE`, `ARTIFACT_NOT_FOUND`, `JOB_NOT_FOUND`,
`EVIDENCE_NOT_FOUND`, `EVIDENCE_RECORD_NOT_FOUND`, `ANALYSIS_IN_PROGRESS`, `VALIDATION_ERROR`,
`NOT_FOUND`, `METHOD_NOT_ALLOWED`, `HTTP_ERROR`, `INTERNAL_ERROR`, `INTERRUPTED`, `REVIEW_CONFLICT`,
`EXPORT_FAILED`, `PREVIEW_FAILED`, `INVALID_DOCUMENT`, `AI_UNAVAILABLE`, `INTEGRATION_DISABLED`.

### 14.4 Health response

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "ok",
  "storage": "ok",
  "tools": {
    "exiftool": { "status": "ok", "version": "…", "used_in": "M1: metadata, C2PA detection" },
    "tesseract": { "status": "ok", "version": "…", "used_in": "M1: OCR", "languages": ["eng"] },
    "binwalk": { "status": "missing", "version": null, "used_in": "Pass 2: signature scan" }
  },
  "checked_at": "2026-11-10T00:00:00Z"
}
```

`status` is `degraded` when a required tool is missing — useful as a readiness probe for an
integrating system before it starts a job.

### 14.5 Supported inputs

| Kind | Formats | Identified by |
|---|---|---|
| Image | JPEG, PNG, WebP, TIFF | byte signature |
| Video | MP4, MOV, WebM, MKV, AVI, MPEG-TS, WMV, FLV, 3GP, M4V | byte signature, then ffprobe |
| Audio | WAV, MP3, FLAC, OGG, M4A | byte signature, then ffprobe; an MP4-family or Ogg file with no real video stream is audio |
| Document | PDF (`%PDF-`) | byte signature; parsed in place, never rendered, executed, or decrypted |

Never by filename or extension. Other document and archive formats are not accepted.

---

## 15. Licence and third-party terms

The repository carries no licence file yet; add one before treating the code as reusable by others.
Third-party components are recorded with their licences and source URLs in `docs/10-DEPENDENCIES.md`
— notably Cactus Needle (Apache-2.0), `c2pa-python` / c2pa-rs, binwalk v3 (MIT), and the standard
FastAPI / React toolchains. Reverse-image search providers are used only by the analyst, manually, on
the providers' own sites under the providers' own terms; Vestigo sends them nothing.
