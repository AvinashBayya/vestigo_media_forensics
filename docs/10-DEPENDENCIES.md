# Dependencies

## Backend — Milestone 1

- Python 3.11
- FastAPI
- Uvicorn
- Pydantic
- pydantic-settings (configuration from `.env`)
- python-multipart (required by FastAPI for file uploads)
- SQLAlchemy
- SQLite
- Pillow
- ExifTool (metadata and C2PA detection)
- Tesseract OCR (English language data only)
- imagehash
- pytest
- httpx

## Backend — Milestone 2

- Alembic (database migrations; decision M2-1). Brings in Mako.

## Frontend — Milestone 1

- React
- React Router
- Vite
- TypeScript
- Axios (upload progress)
- Tailwind CSS

## Frontend tests — Milestone 1

- Vitest
- Testing Library (React, user-event, jest-dom)
- jsdom
- msw (mock API)

## Container tools

- Docker
- Docker Compose
- Dev Containers
- Git

## Backend — Milestone 3

- ffprobe (video validation and media information) and FFmpeg (scene detection and keyframe
  extraction) are required tools from Milestone 3; a missing one degrades /health.
- No new Python dependencies: keyframe hashing and OCR reuse Pillow, imagehash, and Tesseract.
  OpenCV and PyAV, listed earlier as possible video dependencies, were not needed.

## D19

No new dependencies: the added formats, audio support, orientation-aware duplicate search, and
playable previews all use the existing ffmpeg/ffprobe, ExifTool, Pillow, and imagehash toolchain.

## Backend — Milestone 4 (D20)

- `c2pa-python` 0.38.1 (pinned `>=0.38` in `pyproject.toml`), bundling the Rust c2pa-rs SDK 0.91.3.
  Local C2PA manifest reading and validation; no network access. The evidence records the exact
  version string reported at runtime.
- Test fixtures are signed with a throwaway ES256 CA created by `openssl` (already in the
  container); no signing library is a runtime dependency.
- The chain of custody (M4B, D21) added no dependencies: Alembic 0005, SQLite triggers, and the
  existing FastAPI/SQLAlchemy/React toolchain.

## Backend — Milestone 5 (D22)

No new dependencies: the manual-first reverse-image search uses the existing FastAPI/SQLAlchemy/
React toolchain and makes no outbound HTTP requests. Provider-specific SDKs or HTTP clients were
not needed and remain out of scope until a paid/official API integration is separately approved.

## Backend — Milestone 6 (D23)

No new dependencies: location clues come from the ExifTool already installed (read a second time
with numeric output), coordinate validation is a range check in `app/services/location.py`, and the
only map affordance is a plain link built in the browser. The "GEOINT" future-dependency list below
(reverse-geocoding service, map rendering library, coordinate validation utilities) was therefore
not needed; a geocoding service or tile provider would each require separate approval.

## Backend — local AI (D24, made live in D27), an optional extra

Declared as an optional extra, not a dependency: `pip install -e ".[dev,ai]"`. A stock build has
local AI disabled, the suite passes with the extra absent, and the resolvers in
`app/services/ai/__init__.py` return a provider that refuses with a reason rather than degrading
silently. Installing the extra downloads no model and no engine.

- `cactus-needle` (3.2.10), import name `needle`, **Apache-2.0** —
  [github.com/cactus-compute/needle](https://github.com/cactus-compute/needle). Provides tool
  calling, structured extraction, and (where an engine exists) speech-to-text on a CPU engine. It
  pulls in `huggingface_hub`, which is what the offline switch below acts on.
- Engine binaries and model weights, **Apache-2.0**, published separately from the package:
  [Cactus-Compute/needle2](https://huggingface.co/Cactus-Compute/needle2),
  [Cactus-Compute/needle3](https://huggingface.co/Cactus-Compute/needle3),
  [Cactus-Compute/whistle](https://huggingface.co/Cactus-Compute/whistle).
- No GPU, no account, no recurring cost. Vendor telemetry is forced off in-process, and so are
  downloads.

### What can actually run (verified 2026-11-09, linux-x86_64)

The engine and the weights ship from different places, and they are not both published for every
generation. This was checked against the Hub rather than taken from vendor prose:

| Generation | Weights published | Engine published for linux-x86_64 | Runs here |
|---|---|---|---|
| needle2 | `needle2.cact`, 13.7 MB | yes, wheels through 2.0.4 | **yes** |
| needle3 | `needle3.cact`, 35.3 MB | **no** — repo holds weights, a checkpoint and a tokenizer only | no |
| whistle | `whistle.cact`, 16.9 MB | **no** — loads through the generation 3 engine | no |

So Vestigo asks for generation 2 (`DEFAULT_GENERATION`), which gives AI drafts and structured
extraction. Transcription, model text embeddings (`Needle.embed` raises "embeddings require a
Needle 3 model"), and anything else gated on generation 3 report themselves unavailable with that
reason, and start working the moment the vendor publishes a generation 3 engine. Nothing is faked
in the meantime. There is no free-text generation in this runtime at all: `Needle.complete()` with
no tools returns an empty call, so Vestigo drafts no prose answers.

### Staging a model (the only step that touches the network)

Deliberately manual, and never part of a container build:

```bash
python -m pip install -e ".[dev,ai]"   # the runtime
needle fetch --generation 2            # the engine, ~14 MB, into ~/.cache/cactus-needle/v2/2.0.4/
```

`scripts/verify-env.sh` then reports the runtime and each generation's engine as present or absent
without failing, because a container with no local AI is a supported setup. A `.cact` archive can
also be staged per-install: drop it in `data/models/` or import it in Settings, and Vestigo passes
it to the engine as explicit weights.

### Why the backend cannot download anything

`needle/__init__.py` resolves a missing engine or missing weights by fetching them from Hugging Face
*at load time*, and its `_register_download` pings the Hub even when the cache is warm. Relying on a
warm cache would make "the backend makes no outbound request" a hope. So `app/services/ai/runtime.py`
forces `HF_HUB_OFFLINE=1` at import, alongside `NEEDLE_TELEMETRY=0` and `DO_NOT_TRACK=1`, and
`/ai/status` reports `offline_enforced`. Measured: a cold lookup then fails locally in 0.14 s with no
network call, while a staged model still runs. Passing explicit weights skips the Hub ping entirely.

Only those three variables are set. `CACTUS_*` names appear in no version of this package and are
not used; the real ones are `NEEDLE_TELEMETRY`, `DO_NOT_TRACK`, `NEEDLE2_LIB_PATH` /
`NEEDLE3_LIB_PATH`, `NEEDLE_WHISTLE_WEIGHTS`, and `NEEDLE_HF_REPO`. `NEEDLE_API_KEY` and
`OPENROUTER_API_KEY` are the vendor's cloud paths: Vestigo never reads or sets either.

### Measured on the development machine

Intel i7-1165G7, 8 cores, 7.7 GB RAM, no GPU, generation 2 engine, via `NeedleExtractor`:

| | |
|---|---|
| Import of Vestigo's AI modules | 0.07 s |
| First call (engine load + extraction) | 0.96 s |
| Warm extraction, 56-character source | 0.67 s median (0.63–0.69 over 5 runs) |
| Warm extraction, 2,312-character source | 3.76 s median over 3 runs |
| Peak RSS of the process | 47 MB |

Correctness is not claimed from these runs; they establish that the model is usable interactively on
a laptop CPU. The engine is single-model and not thread-safe, so `ENGINE_LOCK` serialises every call.

## Backend — Pass 2 deep forensics (D25)

No new runtime dependency. Structural inspection, PDF parsing, and the forensic measurements are
pure Python (`zlib`, `struct`, `hashlib`) plus the Pillow and numpy already present, and PDF
metadata comes from the ExifTool already required.

- `binwalk` v3 (MIT, [ReFirmLabs/binwalk](https://github.com/ReFirmLabs/binwalk)) is an **optional**
  tool: when it is on PATH the structural stage includes its signature scan, always without
  extraction. Absent is fine and is recorded as such; /health lists it as optional.
- No PDF library, renderer, or rasteriser is used or required, which is why page appearance is never
  reproduced and only stored JPEG streams are extracted.

## Future dependencies

### GEOINT

Done in Milestone 6 with no new dependencies (see above). Still unapproved, should they ever be
wanted: a reverse-geocoding service, a map rendering/tile library.

### C2PA

Done in Milestone 4: `c2pa-python` (see above).

## Explicit exclusions

- Facial recognition
- Biometric identification
- Automated deepfake verdict tools
- Active scanning tools
- Exploitation tools
- Credential-testing tools
- Evasion or stealth tooling