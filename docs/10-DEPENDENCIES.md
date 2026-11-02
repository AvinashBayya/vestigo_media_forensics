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

## Installed but not used in Milestone 1

- FFmpeg
- ffprobe

These are installed and verified during environment setup. They will be used in Milestone 3 for video metadata, keyframe extraction, and scene detection.

## Future dependencies

### Video

- FFmpeg
- ffprobe
- OpenCV
- PyAV

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