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

## Future dependencies

### Reverse-image search

- Provider-specific SDKs or HTTP clients
- Permission and licence registry

### GEOINT

- Reverse-geocoding service
- Map rendering library
- Coordinate validation utilities

### C2PA

- C2PA validation library or CLI
- Provenance report generator

## Explicit exclusions

- Facial recognition
- Biometric identification
- Automated deepfake verdict tools
- Active scanning tools
- Exploitation tools
- Credential-testing tools
- Evasion or stealth tooling