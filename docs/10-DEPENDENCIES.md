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

## Future dependencies

### Reverse-image search

- Provider-specific SDKs or HTTP clients
- Permission and licence registry

### GEOINT

- Reverse-geocoding service
- Map rendering library
- Coordinate validation utilities

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