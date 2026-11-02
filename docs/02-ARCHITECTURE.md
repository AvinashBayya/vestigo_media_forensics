# Architecture

## 1. System shape

Vestigo Media Forensics is a local-first service with:

- FastAPI backend
- SQLite database
- Local file storage
- React + Vite frontend
- Background job pipeline
- Pluggable analysis stages

## 2. High-level flow

```text
Browser
  → FastAPI upload endpoint
  → local storage
  → analysis job
  → pipeline stages
  → SQLite evidence records
  → JSON evidence report
  → React review UI
```

## 3. Backend structure

```text
app/
├── main.py
├── core/
│   ├── config.py
│   ├── database.py
│   ├── storage.py
│   └── logging.py
├── api/
│   ├── routes_artifacts.py
│   ├── routes_analysis.py
│   └── routes_health.py
├── schemas/
│   ├── artifact.py
│   ├── analysis.py
│   └── evidence.py
├── services/
│   ├── hashing.py
│   ├── metadata.py
│   ├── c2pa.py
│   ├── phash.py
│   ├── ocr.py
│   └── duplicates.py
├── pipeline/
│   ├── base.py
│   ├── image_pipeline.py
│   └── runner.py
└── models/
    ├── artifact.py
    ├── analysis_job.py
    └── evidence_record.py
```

## 4. Pipeline model

Each analysis stage must implement a common interface:

```python
class AnalysisStage:
    name: str
    media_type: str

    def run(self, artifact, context) -> StageResult:
        ...
```

Each `StageResult` must include:

- Stage name
- Status
- Output data
- Tool used
- Tool version
- Started at
- Completed at
- Errors
- Limitations
- Evidence classification

## 5. Milestone 1 image pipeline

```text
upload
→ validate file
→ store original
→ calculate SHA-256 and MD5
→ extract EXIF / XMP / IPTC
→ detect C2PA / Content Credentials
→ generate perceptual hash
→ run OCR
→ search local duplicates
→ persist evidence
→ return report
```

## 6. Future video pipeline

The video pipeline is planned for Milestone 3.

It will use:

- ffprobe for container, stream, codec, duration, and technical metadata
- ffmpeg for keyframe extraction
- ffmpeg for scene-change detection
- audio inspection where applicable

FFmpeg and ffprobe are installed in the Dev Container from the beginning, but Milestone 1 does not invoke them.

## 7. Future GEOINT module

GEOINT will be a separate, opt-in analysis module.

Initial geo-lite capabilities may include:

- EXIF GPS extraction
- Coordinate validation
- Reverse geocoding through an approved local or external service
- Map preview
- Terrain, infrastructure, and landmark clues
- Analyst notes and confidence labels

It must never automatically claim a location is confirmed.

## 8. Future reverse-image module

Reverse-image search will be permission-gated and evidence-producing.

Each external lookup must record:

- Provider
- Query type
- Request timestamp
- Result URL
- Match score or rank, if available
- Licence or terms reference
- Analyst review state

If legal or terms review is pending, the provider must be registered as `UNVERIFIED` and disabled by default.

## 9. Storage rules

- Original uploads are preserved.
- Derived files are stored separately.
- Database records reference files; they do not embed large binary media.
- Users can delete an artifact and its associated files, evidence, and database records.
- No silent retention beyond the user’s configured local retention policy.

## 10. API base

```text
http://localhost:8400/api/v1
```