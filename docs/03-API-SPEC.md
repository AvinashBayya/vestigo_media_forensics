# API Specification

## Base URL

```text
http://localhost:8400/api/v1
```

## General rules

- All responses use JSON.
- Errors use a consistent error envelope.
- Analysis is asynchronous for large files.
- Every artifact has a stable ID.
- Every analysis result is linked to its artifact and job.

## Health

### `GET /health`

Response:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "ok",
  "storage": "ok"
}
```

## Artifacts

### `POST /artifacts/upload`

Uploads an image.

Request:

```text
multipart/form-data
file: binary
```

Response:

```json
{
  "artifact_id": "art_123",
  "filename": "example.jpg",
  "size_bytes": 1048576,
  "media_type": "image",
  "created_at": "2026-11-02T09:00:00Z"
}
```

### `GET /artifacts/{artifact_id}`

Returns artifact metadata and current analysis status.

### `DELETE /artifacts/{artifact_id}`

Deletes the artifact, associated files, evidence records, and database rows.

## Analysis

### `POST /analysis/image`

Starts the Milestone 1 image-analysis pipeline.

Request:

```json
{
  "artifact_id": "art_123",
  "options": {
    "ocr": true,
    "duplicate_search": true,
    "metadata": true,
    "c2pa": true
  }
}
```

Response:

```json
{
  "job_id": "job_456",
  "artifact_id": "art_123",
  "status": "queued"
}
```

### `GET /analysis/jobs/{job_id}`

Returns job status and stage progress.

### `GET /artifacts/{artifact_id}/evidence`

Returns the complete evidence report.

## Evidence report shape

```json
{
  "artifact_id": "art_123",
  "job_id": "job_456",
  "created_at": "2026-11-02T09:01:00Z",
  "hashes": {
    "sha256": "...",
    "md5": "..."
  },
  "metadata": {
    "exif": {},
    "xmp": {},
    "iptc": {}
  },
  "c2pa": {
    "present": false,
    "details": {}
  },
  "perceptual_hash": {
    "algorithm": "pHash",
    "value": "..."
  },
  "ocr": {
    "engine": "tesseract",
    "text": "...",
    "confidence": 0.0
  },
  "duplicates": [
    {
      "artifact_id": "art_789",
      "similarity": 0.94,
      "distance": 6
    }
  ],
  "review": {
    "state": "UNREVIEWED",
    "analyst_notes": ""
  }
}
```

## Review state values

- `UNREVIEWED`
- `IN_REVIEW`
- `REVIEWED`
- `FLAGGED`
- `ARCHIVED`

## Error format

```json
{
  "error": {
    "code": "UNSUPPORTED_MEDIA_TYPE",
    "message": "Only image files are supported in Milestone 1.",
    "details": {}
  }
}
```