# Claude Code Build Prompts

## Prompt 1 — Read and plan

```text
Read docs/00-MASTER-BUILD-SPEC.md first, then all other docs.

This project runs in a Docker Dev Container. All commands run inside the container.

Backend port: 8400
Frontend port: 5180

Do not write code yet.

Produce:
1. Folder structure
2. API contract
3. Pydantic schemas
4. SQLite schema
5. Pipeline-stage interface
6. Image pipeline
7. Health-check design
8. Test plan
9. Milestone 1 implementation order
10. Open questions

Wait for approval.
```

## Prompt 2 — Build Milestone 1

```text
Implement Milestone 1 only.

Scope:
- FastAPI backend
- SQLite database
- Image upload
- SHA-256 and MD5 hashing
- EXIF, XMP, IPTC metadata extraction
- C2PA / Content Credentials detection
- Perceptual hash generation
- OCR using Tesseract
- Local duplicate-image search
- JSON evidence output
- Minimal React + Vite frontend
- Health check
- Core tests

Rules:
- Backend runs on port 8400.
- Frontend runs on port 5180.
- Do not implement video analysis.
- Do not implement external reverse-image search.
- Do not implement GEOINT.
- Do not implement facial recognition.
- Do not claim a file is authentic or fake.
- Every evidence result must include method, tool, timestamp, and limitations.
- Do not stub or delete planned future modules unless I explicitly ask.
- Write tests for upload, hashing, metadata, C2PA, pHash, OCR, duplicates, evidence, and deletion.

Wait for my approval before implementing.
```

## Prompt 3 — Build frontend

```text
Build the minimal React + Vite frontend.

Requirements:
- Port 5180
- Upload image
- Show analysis progress
- Show hashes
- Show metadata
- Show C2PA status
- Show pHash
- Show OCR text
- Show duplicate matches
- Show evidence JSON download
- Show review state
- Keep UI simple and analyst-friendly

Do not add complex dashboards, advanced filters, or unsupported features.
```

## Prompt 4 — Add tests

```text
Add backend and API tests for Milestone 1.

Cover:
- Upload validation
- Hashing
- Metadata extraction
- C2PA detection
- pHash
- OCR
- Duplicate search
- Evidence output
- Job status
- Artifact deletion
- Health endpoint

Use pytest. Ensure all tests pass inside the Dev Container.
```