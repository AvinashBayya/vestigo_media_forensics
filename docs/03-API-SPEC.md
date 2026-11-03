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
    "languages": ["eng"],
    "text": "...",
    "cleaned_text": null,
    "cleaning": [],
    "confidence": 0.0,
    "word_count": 0,
    "preprocessing": [],
    "candidates": [],
    "selected": null
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

## OCR section

OCR runs Tesseract twice on prepared copies of the image (decision D13). The original file is never
modified.

| Field | Meaning |
|---|---|
| `text` | Raw Tesseract text of the selected pass, unchanged apart from removing surrounding whitespace and the page separator. |
| `cleaned_text` | The same text after cosmetic cleaning, or `null` when cleaning changed nothing. Cleaning removes only lines that contain no letters or digits, trailing whitespace, and repeated blank lines. |
| `cleaning` | One entry per cleaning rule that changed the text: `rule`, `description`, `lines_affected`. |
| `confidence` | Mean of Tesseract's per-word confidence for the selected pass, 0-1. The engine's own estimate, not a measured accuracy. `null` when no words were found. |
| `word_count` | Words found by the selected pass. |
| `preprocessing` | Every step, applied or not: `step`, `applied`, `description`, `parameters`. Steps: `first_frame`, `exif_orientation`, `flatten_transparency`, `grayscale`, `upscale` (`factor`, `resample`, `max_factor`, `target_longest_side`, `input_size`, `output_size`), `adaptive_threshold` (`method`, `window_radius_px`, `offset`, `polarity`, `applies_to`). |
| `candidates` | Both passes, `grayscale` then `threshold`: `variant`, `status` (`succeeded` or `failed`), `text`, `confidence`, `word_count`, `error`. |
| `selected` | `{ "variant": "grayscale" \| "threshold", "reason": "..." }`: which pass supplied `text`, and why. |

Derived files for the OCR stage (listed in `provenance.derived_files`): `ocr_input_grayscale`,
`tesseract_tsv_grayscale`, `ocr_input_threshold`, and `tesseract_tsv_threshold`. A failed pass has no
TSV.

If the threshold pass fails and the grayscale pass succeeds, the stage status is `partial` with an
`OCR_VARIANT_FAILED` error. If the grayscale pass fails, the stage fails.

Records made before two-pass OCR return `cleaned_text: null`, empty `cleaning` and `candidates`,
`selected: null`, and their stored preprocessing notes as steps named `note`.

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