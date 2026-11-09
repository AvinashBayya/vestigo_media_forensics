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

## Backend — Pass 1 local AI (D24), optional and analyst-installed

Not declared in `pyproject.toml` and not required to run or test Vestigo: a stock build has local AI
disabled and every test uses fakes. The analyst installs these themselves if they want live
inference.

- `cactus-needle` (3.2.10 at time of writing), import name `needle`, **Apache-2.0** —
  [github.com/cactus-compute/needle](https://github.com/cactus-compute/needle). Provides tool
  calling, structured extraction, and speech-to-text on a CPU engine.
- `cactus-compute` (4.0.1), **Apache-2.0** —
  [github.com/cactus-compute/cactus](https://github.com/cactus-compute/cactus). The inference
  engine; the vendor's documentation site also describes paid tiers for cloud hybrid inference,
  custom models, and extra hardware acceleration, none of which Vestigo uses or can reach.
- Model weights, **Apache-2.0**, supplied as local files by the analyst:
  [Cactus-Compute/needle3](https://huggingface.co/Cactus-Compute/needle3) (2-bit, 8–29 MB) and
  [Cactus-Compute/whistle](https://huggingface.co/Cactus-Compute/whistle) (16.9 MB speech-to-text).
- No GPU, no account, and no recurring cost. Vendor telemetry is forced off in-process (D24).

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