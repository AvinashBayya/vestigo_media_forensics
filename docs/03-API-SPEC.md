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

Uploads an image, video, or audio file. The type comes from the file's bytes, never its name:

- Images: JPEG, PNG, WebP, TIFF.
- Videos: MP4, MOV, WebM, MKV, AVI, MPEG-TS, WMV, FLV, 3GP, M4V (`media_type: "video"`).
- Audio: WAV, MP3, FLAC, OGG, M4A (`media_type: "audio"`; an MP4-family or Ogg file without a real
  video stream is audio).

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

If `options` is omitted, the default analysis options saved in Settings are used (Milestone 2).

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
    "validation_performed": true,
    "status": "absent",
    "validation_state": null,
    "manifest_count": 0,
    "active_manifest": null,
    "manifests": [],
    "validation_codes": {"success": [], "informational": [], "failure": []},
    "validator": "c2pa-python 0.38.1 (c2pa-rs 0.91.3)",
    "validator_error": null,
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

## Milestone 2 endpoints (analyst workflow)

All additive; Milestone 1 requests and responses keep their meaning. See `12-MILESTONE-2-PLAN.md`.

### `GET /artifacts` — search, filters, sorting

All query parameters are optional; unknown parameters return 422 `VALIDATION_ERROR` (values are not
echoed).

| Parameter | Meaning |
|---|---|
| `q` | Case-insensitive (Unicode) substring of the filename or analyst notes (artifact or evidence record). ID-like terms (`art_…` or 8+ hex characters) also match the artifact ID and SHA-256/MD5 prefixes. `%` and `_` are literal. Max 200 characters. |
| `review_state` | Repeatable. |
| `analysis_status` | Repeatable: `queued`, `running`, `completed`, `completed_with_errors`, `failed`, `not_analysed`. |
| `has_problems`, `has_duplicates` | Latest job has failed/partial checks; latest duplicate search found matches. |
| `mime_type` | Repeatable: `image/jpeg`, `image/png`, `image/webp`, `image/tiff`. |
| `uploaded_from`, `uploaded_to` | Inclusive; ISO-8601 with a timezone. |
| `include_archived` | Default `true` (Milestone 1 behaviour). The Library sends `false`; asking for `review_state=ARCHIVED` always includes them. |
| `sort`, `order` | `created_at` (default, `desc`), `filename` (case-insensitive), `size_bytes`, `review_state` (evidence-model order). Ties: newest upload, then ID. |
| `limit`, `offset` | 1–200 (default 50); ≥ 0. |

Each item adds `latest_job`, `problem_count` (failed or partial stages in the latest job, plus one if
the job failed; `null` if never analysed), `duplicate_match_count` (`null` if the latest job has no
duplicate-search result), `added_since_analysis` (library artifacts uploaded after that search;
`null` without a result), and `in_duplicate_library`. The response adds `counts_by_review_state`,
which ignores the review-state and archive filters. `GET /artifacts/{id}` returns the same fields.

### Review

| Endpoint | Behaviour |
|---|---|
| `PATCH /artifacts/{id}/review` | Optional `expected_updated_at`: if the review changed since, 409 `REVIEW_CONFLICT` with `details.current`. Saving without a change writes nothing. |
| `POST /artifacts/review` | Bulk: `{"artifact_ids": [...1–200], "state": "..."}`. All or nothing: any missing ID returns 404 `ARTIFACT_NOT_FOUND` with `details.missing`, and nothing changes. Response: `state`, `updated`, `unchanged`. Notes are not changed. |
| `PATCH /artifacts/{id}/evidence/{evidence_id}/review` | One evidence record: `{state, analyst_notes, expected_updated_at?}` (`null` = never reviewed). Never changes classification or payload. 404 `EVIDENCE_RECORD_NOT_FOUND`; 409 `REVIEW_CONFLICT`. |
| `GET /artifacts/{id}/review-history` | Append-only review events, newest first: `origin` (`artifact`, `record`, `bulk`), `from_state`, `to_state`, full `notes_before` and `notes_after`, `created_at`, and `stage`/`job_id` for record events. |

The evidence report becomes `schema_version` `"1.1"`: each section's `provenance` adds
`analyst_notes` and `review_updated_at`, and the report adds `review_history`. The duplicates section
adds `excluded_count`.

### Analysis history

`GET /artifacts/{id}/jobs`: every job, newest first, with `pipeline`, `app_version`, `options`,
job-level `error` (e.g. `INTERRUPTED`), and `problem_count`.

### Evidence package

`GET /artifacts/{id}/export?job_id=&include_original=false` returns a ZIP for the latest finished job
or `job_id`: `report.json`, `review.json`, `derived/…`, `original/…` (only with
`include_original=true`), `manifest.json` (SHA-256 and size of every file; recorded hashes; a
`problems` list for recorded files that are missing or changed), `SHA256SUMS`, and `README.txt` (the
evidence notice and how to verify). Header `X-Vestigo-Export-SHA256` is the ZIP's SHA-256. Errors:
404 as for the evidence report, 409 `ANALYSIS_IN_PROGRESS`, 500 `EXPORT_FAILED`.

### Duplicate library

| Endpoint | Behaviour |
|---|---|
| `PATCH /artifacts/{id}/duplicate-library` | `{"included": false}` excludes the artifact from future duplicate searches (perceptual and byte-identical); `true` includes it again. Recorded evidence is never rewritten. Returns the artifact detail. |
| `GET /library/summary` | `artifact_count`, `indexed_count`, `not_indexed_count`, `excluded_count`, the newest 100 not-indexed and excluded artifacts, and `storage` (`original_bytes`, `derived_bytes`). |

The duplicates stage records `excluded_count`; `library_size` counts the artifacts actually searched.

### Settings

| Endpoint | Behaviour |
|---|---|
| `GET /settings` | `editable` (`default_analysis_options`, `library_page_size` 10/25/50/100, `auto_analyze_after_upload`), `environment` (read-only: limits, `duplicate_threshold`, timeouts, OCR languages, workers, data folder, version, schema revision), `updated_at`. |
| `PATCH /settings` | Any subset of the editable settings. Environment keys (e.g. `phash_max_distance`, `duplicate_threshold`) return 422 asking to set them in `.env`. |

New error codes: `REVIEW_CONFLICT`, `EVIDENCE_RECORD_NOT_FOUND`, `EXPORT_FAILED`.

## Milestone 3 endpoints (video foundation)

All additive. See `13-MILESTONE-3-PLAN.md`.

### Upload

`POST /artifacts/upload` also accepts MP4, MOV, WebM, and MKV videos (M3-1), detected from the
file's bytes. After sniffing, ffprobe must parse the file and find a video stream with readable
dimensions and a container-reported duration within the limits. Summaries carry
`duration_seconds` (container-reported, M3-8; null for images). New error codes: `INVALID_VIDEO`,
`VIDEO_TOO_LONG`, `VIDEO_RESOLUTION_TOO_LARGE`, and `WRONG_MEDIA_TYPE` (an analysis endpoint used
on the other media type).

### `POST /analysis/video`

Queues the `video.v1` pipeline. Options: `metadata`, `c2pa` (default **true**, M4/D20),
`scene_detection`, `keyframe_ocr` (default **false**, M3-3), `duplicate_search`. Hashes, media info, keyframes, and keyframe
perceptual hashes always run. Omitted `options` use the saved `default_video_analysis_options`.

### `GET /artifacts/{id}/derived/{derived_file_id}/content`

Serves a derived file (for example a keyframe thumbnail) for display, only for the artifact that
owns it, typed by its recorded kind, with the content endpoint's protective headers.

### Evidence report 1.2 — video sections (null for image jobs)

| Section | Content |
|---|---|
| `media_info` | Container and per-stream facts exactly as ffprobe read them: format, container-reported duration, video codec/profile/dimensions/frame rate/bit rate/pixel format/display rotation, and audio codec/channels/sample rate from headers only (M3-7). |
| `scene_changes` | ffmpeg scene-filter results: threshold and `[{time, score}]`. |
| `keyframes` | The selection policy, counts, and per frame its timestamp, selection reason (`first_frame`, `scene_change` with score, `uniform_sample`), thumbnail `derived_file_id`, and dimensions. |
| `keyframe_phash` | 64-bit pHash per keyframe. |
| `keyframe_ocr` | Per analysed frame (≤ 10, evenly spaced): the D13 OCR detail (raw and cleaned text, confidence, passes, selection), labelled provisional (D14). |

`duplicates` is shared by both pipelines. `DuplicateMatch` adds `media_type`,
`matched_frame_count`, and `frame_matches` (each query hash's best counterpart with both sides'
keyframe timestamps); these are null for image-to-image and byte-identical matches. Image
duplicate searches also cover video keyframes, and vice versa (M3-4).

### Settings

`editable` adds `default_video_analysis_options`; `environment` adds the read-only video limits
(`max_video_upload_bytes`, `max_video_duration_seconds`, `max_video_pixels`, `max_keyframes`,
`scene_threshold`, `video_timeout_seconds`).

## D19 additions (cross-media search, formats, audio, previews)

- **Upload** also accepts AVI, MPEG-TS, WMV, FLV videos (3GP/3G2 and M4V now labelled correctly)
  and WAV, MP3, FLAC, OGG, M4A audio (`media_type: "audio"`, dimensions null, duration
  container-reported). New error codes: `INVALID_AUDIO`, `AUDIO_TOO_LONG`, `PREVIEW_FAILED`.
- **`POST /analysis/audio`** queues `audio.v1` (hashes, media info, metadata, byte-identical
  duplicate search, plus C2PA validation since M4); options `{metadata, c2pa,
  duplicate_search}`; saved defaults in
  `default_audio_analysis_options`. Audio duplicate matching is SHA-256 only, by design.
- **Duplicate matches**: `frame_matches` entries add `rotation_degrees` (counter-clockwise) and
  `mirrored`, recording the orientation under which the pair matched; 0/false is an upright match.
- **Previews**: `POST /artifacts/{id}/preview` creates (idempotently) a re-encoded viewing copy for
  a video; `GET …/preview` returns its facts; `GET …/preview/content` streams it with Range. The
  copy is not evidence and never appears in the export package. `ArtifactDetail` adds
  `has_playable_preview`; `DeletionSummary` adds `preview_files`; the library summary's storage
  adds `preview_bytes`. Non-videos are refused with `WRONG_MEDIA_TYPE`.
- **Settings environment** adds `max_audio_upload_bytes` and `max_audio_duration_seconds`.

## Milestone 4 — C2PA validation (D20)

The `c2pa` evidence section is shared by all three pipelines (`details` holds the image pipeline's
detection results and is empty for video and audio). Since M4 it carries the local validation
outcome:

- `validation_performed` — `false` only on records made before M4 (detection only).
- `status` — Vestigo's summary: `valid` | `invalid` | `unverifiable` | `absent`. `valid` means the
  manifest's hashes and claim signature verify for the data they cover — never that the content is
  truthful or the signer trusted (no trust list is configured).
- `validation_state` — the SDK's own state, as reported.
- `manifest_count`, `active_manifest`, and `manifests` — per manifest: `label`, `title`,
  `claim_generator`, `signature_issuer`, `signature_common_name`, `signature_cert_serial`,
  `signature_time`, `signature_algorithm`, `assertion_labels`, `ingredient_count`. All recorded as
  written, not verified against any registry.
- `validation_codes` — the validator's codes for the active manifest, grouped `success` /
  `informational` / `failure` (the standing `signingCredential.untrusted` appears for every signer
  because no trust list is configured).
- `validator` — the exact validator version (`c2pa-python 0.38.1 (c2pa-rs 0.91.3)`).
- `validator_error` — the recorded reason when `status` is `unverifiable`.

The validator's raw manifest-store report is stored as a derived file (`manifest_store.json`),
served by the derived-content endpoint, included in the evidence package, and deleted with the
artifact. Detected-but-unreadable C2PA data makes the stage `partial` with warning code
`C2PA_VALIDATION_UNAVAILABLE`; an invalid manifest is a finding, not a stage failure.

## Milestone 4 part 2 — Chain of custody (D21)

### `GET /artifacts/{artifact_id}/custody`

The chain of custody Vestigo recorded on this machine since upload, merged chronologically at read
time from the existing tables plus `custody_events` — nothing duplicated, inferred, or backfilled.
Response: `{artifact_id, notice, events, derived_files}`.

- `events`: `{type, at, source_table, detail}`, oldest first. Types: `uploaded` (filename, media
  type, size, SHA-256), `analysis_started` / `analysis_finished` per job (pipeline, status,
  evidence-record and derived-file counts; one entry per job, never per stage), `review_changed`
  (origin, states, whether notes changed — the note text stays in the review history), `exported`
  (package SHA-256, `original_included`, counts), `library_changed` (before/after), and
  `preview_created` (the viewing copy's hash and dimensions). Exports and library changes from
  before schema revision 0005 were never recorded and do not appear; the `notice` says so.
- `derived_files`: every derived file with `source_kind` (`"original"`, `"derived_file"`, or null
  for pre-0005 rows, reported as "source not recorded") and `source_derived_file_id` (a
  keyframe-OCR TSV points at the exact keyframe thumbnail it read).

The evidence export package gains `custody.json` (the same report), hashed in `manifest.json` and
`SHA256SUMS`. A package is built before its own export event is recorded, so each export appears in
the next package's custody.json. `DeletionSummary` adds `custody_events`; the table is append-only
(database triggers) and cascade-deletes with the artifact.

## Milestone 5 — Reverse-image search (D22)

### `GET /search/providers`

The static provider registry (Google Lens, Bing Visual Search, TinEye, Yandex Images) with each
provider's name, plain landing URL (https, no query parameters, nothing evidence-derived), terms
URL, manual-upload instructions, and `enabled` flag. The response `notice` is the sharing warning.
Providers are enabled through the editable setting `enabled_search_providers` (registry keys only,
validated and deduplicated; all off by default). The backend never contacts a provider.

### External leads

- `GET /artifacts/{id}/external-leads` — the analyst-recorded leads, newest first, with a notice
  stating that leads are unverified analyst statements and an earlier result is never proof of the
  original source.
- `POST /artifacts/{id}/external-leads` (201) — body: `provider`, `result_url` (http/https, stored
  exactly as entered), optional `image_url`, `claimed_published_at` (free text, as entered),
  `notes`, and `derived_file_id`. Subject rules: an image lead omits `derived_file_id`; a video
  lead must name a real keyframe (`keyframe_jpeg`) of that artifact; audio is refused with
  `WRONG_MEDIA_TYPE`.
- `PATCH /artifacts/{id}/external-leads/{lead_id}` — any subset of the fields plus `review_state`
  (lightweight lead review). Each actual change is a `lead_updated` custody event naming the
  changed fields; a no-op save records nothing.
- `DELETE /artifacts/{id}/external-leads/{lead_id}` (204) — the deletion itself stays in the
  custody trail (`lead_deleted`).

A lead answers with `lead_id`, the stored fields, fixed `classification: "EXTERNAL"`,
`review_state` (starting UNREVIEWED), `recorded_at` (when Vestigo saved it — not a publication
date), and `updated_at`. The evidence report gains an artifact-level `external_leads` list, which
also places leads in the export package's `report.json`; their custody events appear in
`custody.json`. `DeletionSummary` adds `external_leads`.

### Content downloads

Both `GET /artifacts/{id}/content` and `GET /artifacts/{id}/derived/{derived_file_id}/content`
take `download=true` to answer as an attachment (honest filename, protective headers unchanged),
so the analyst can save the exact subject file for a manual provider upload.

## Milestone 6 — Location clues and candidates (D23)

### Evidence report: `location_clues` (per job, null when the stage did not run)

Machine-read clues, all as written: `coordinates` (each with `source`, decimal `latitude`/
`longitude`, `latitude_as_written`/`longitude_as_written` including hemisphere refs, `valid`, and
`problem` when flagged), `altitude_meters` with `altitude_as_written` and `altitude_reference`,
`text_clues` / `timestamps` / `device` / `iso6709` (each `{tag, value}`), and `ocr_available` —
true when this analysis produced OCR text for the analyst to read. Vestigo never interprets that
text, never reconciles disagreeing sources, and never corrects a flagged coordinate. The stage is
`partial` with `LOCATION_VALUE_UNUSABLE` when a coordinate is out of range or half present. The
analysis options gain `location_clues` (default **true**) for all three media types.

### Location candidates

- `GET /artifacts/{id}/location-candidates` — newest first, with the honesty notice.
- `POST /artifacts/{id}/location-candidates` (201) — body: `description`, `basis`, and
  `analyst_assessment` (`speculative` | `possible` | `likely`) are **required**; optional
  `latitude`/`longitude` (range-validated, and must be given together), `notes`, and `supports`
  (`[{type: "evidence_record" | "derived_file" | "external_lead", id}]`, each checked to exist and
  belong to this artifact, else 404).
- `PATCH /artifacts/{id}/location-candidates/{candidate_id}` — any subset plus `review_state`;
  explicit null is rejected 422 on the required fields, and coordinates change or clear as a pair.
- `DELETE /artifacts/{id}/location-candidates/{candidate_id}` (204).

A candidate answers with `candidate_id`, the stored fields, fixed `classification: "UNVERIFIED"`,
`review_state` (starting UNREVIEWED), `recorded_at` (when Vestigo saved it) and `updated_at`.
Creates, updates, and deletes write `location_candidate_recorded` / `_updated` (changed field names)
/ `_deleted` custody events, which carry no coordinates. The evidence report gains an artifact-level
`location_candidates` list (so they travel in the export package's `report.json`), and
`DeletionSummary` gains `location_candidates`.

### Settings

`editable` gains `enable_external_map_links` (default **false**). Vestigo exposes no map endpoint:
when the flag is on, the artifact page builds an OpenStreetMap link in the browser, so the backend
never constructs, stores, transmits, or logs a coordinate-bearing URL. Reverse geocoding is not
offered.

## Pass 1 — Local AI (D24)

All local, all off by default. Nothing downloads at import, and the backend makes no outbound
request. Asking for AI work while a capability is off returns **409 `AI_UNAVAILABLE`** with the
reason and the fix.

### `GET /ai/status`

Runtime availability, the three analyst switches, what is unavailable and why, the telemetry state
(`NEEDLE_TELEMETRY=0`, `DO_NOT_TRACK=1`, `CACTUS_TELEMETRY=0`, forced in-process), the standing AI
label and limitations, and the known models with licence, source URL, quantization, and whether a
local file is in place.

### Drafts — `/ai/artifacts/{id}/drafts`

`GET` lists them newest first with the label and notice. `POST` (201) takes `source_kind`
(`metadata` | `ocr_text` | `analyst_notes` | `transcript`) and `fields` (1–25 names) and returns the
proposed fields with the model's own `confidence` where it supplied one, its `reasoning`, warnings,
and full model provenance. `PATCH /{draft_id}` takes `{field, action, value?}` where action is
`accepted` | `edited` | `rejected` — `value` is required for an edit and refused otherwise, and the
model's value is always kept beside it. `DELETE /{draft_id}` (204). Drafts never appear in the
evidence report and are never written back onto metadata or evidence.

### Transcripts — `/ai/artifacts/{id}/transcripts`

`GET` lists them with the machine-generated notice. `POST` (201) takes an optional `language` and
transcribes the artifact's audio locally — for a video, ffmpeg extracts the audio track to a derived
file first, so the lineage is explicit; images are refused with `WRONG_MEDIA_TYPE`. The response
carries timestamped `segments` (with word-level timing and the model's probabilities where
available), the model's `text` verbatim, `edited_text`, language, duration, warnings, review state,
and model provenance. `PATCH /{transcript_id}` takes `edited_text` and/or `review_state`; the
model's text is never overwritten. `DELETE /{transcript_id}` (204) leaves the extracted audio as a
derived file of its analysis.

### Semantic search — `/ai/artifacts/{id}/index`, `/ai/search`, `/ai/answer`

`POST …/index` rebuilds that artifact's index from the analyst's own held text and reports the chunk
count, model, and sources; `DELETE …/index` drops it. `GET /ai/search?q=&limit=` ranks indexed
chunks and returns the analyst's own records as pointers with a score. `POST /ai/answer` takes
`{question, artifact_ids?}` and **always** returns `sources`; `answer` is present only when a local
generator is available, is labelled, and is never stored or turned into an evidence record.

### Settings and deletion

`editable` gains `ai_enabled`, `transcription_enabled`, `semantic_search_enabled`, `ai_model_path`,
and `transcription_model_path` (all off or empty). `DeletionSummary` gains `ai_drafts`,
`transcripts`, and `embedding_chunks`. The export package gains a separated `ai/` area
(`README.txt`, `drafts.json`, `transcripts.json`); `report.json` stays free of AI material.

## Pass 2 — Structure, forensic indicators, and documents (D25)

### New evidence sections (per job, null when the stage did not run)

- `structural`: `container`, `file_size`, `logical_end`, `trailing_bytes`, `findings` (each with
  `kind`, `offset`, `size`, `detail`), the declared `inventory`, `measurements` (each with `name`,
  `value`, `method`, `note`), `notes` (how far parsing reached), `warnings`, and `binwalk_ran`.
  Never a verdict: it reports neither "steganography detected" nor that a file is clean.
- `forensic_indicators`: `quantization_tables` (with `implied_quality` for the last save only),
  `channel_statistics`, `decoded_*` against `declared_*` dimensions with `dimensions_match`, and
  `video_statistics` (keyframe spacing and packet-size distributions). DERIVED, no thresholds.
- `pdf_structure`, `pdf_text`, `pdf_images` for documents — see below.

### Documents

Upload accepts PDFs sniffed from `%PDF-` as `media_type: "document"`, limited by
`VESTIGO_MAX_DOCUMENT_UPLOAD_BYTES` (100 MB); a file whose header version cannot be read is refused
with `INVALID_DOCUMENT`. `POST /analysis/document` queues `document.v1` (hashes, metadata,
pdf_structure, pdf_text, pdf_images, structural, duplicates), each stage individually optional via
`default_document_analysis_options`. Using the wrong analysis endpoint returns `WRONG_MEDIA_TYPE`
in both directions.

- `pdf_structure` (OBSERVED): `pdf_version`, `object_count`, `page_count`, `eof_markers`,
  `startxref_markers`, `incremental_updates`, `encrypted`, `markers` (presence counts for
  JavaScript, actions, embedded files, forms, object streams, URI actions), `signature_count`,
  `linearized`. Signature presence only — Vestigo never validates a PDF signature.
- `pdf_text` (DERIVED): provisional `text` with `character_count`, `streams_read`,
  `streams_skipped`, `streams_failed`. Not a verified transcription.
- `pdf_images` (OBSERVED): `images` (index, encoding, size, dimensions, `derived_file_id`) and
  `extracted`. JPEG streams are copied byte for byte; other encodings are counted only.

### Settings

`editable` gains `default_document_analysis_options`; the image, video, and audio option sets gain
`structural` and (image/video) `forensic_indicators`. `environment` gains
`max_document_upload_bytes`.

## Pass 3 — Coordinate tools, cases, and integration (D26)

### `GET /geo/artifacts/{artifact_id}/tools`

Every coordinate Vestigo holds for the artifact - machine-read clues and the analyst's own
candidates - each in `decimal`, `degrees_minutes_seconds`, `degrees_decimal_minutes`, and `iso6709`,
plus `pairs` giving the great-circle `distance_metres` and `bearing_degrees` between every pair.
Calculation only: no geocoding, no place names, no tiles, no network. A coordinate flagged invalid by
the location stage is never used for geometry. `offline_map_available` reflects
`VESTIGO_OFFLINE_MAP_PATH`, which the analyst supplies; Vestigo downloads no map data.

### Cases

`GET /cases`, `POST /cases` (201), `GET|PATCH /cases/{case_id}`, `DELETE /cases/{case_id}` (204),
and `PUT|DELETE /cases/{case_id}/artifacts/{artifact_id}` to add or remove a member. A case is
organisation, not evidence. Linking and unlinking write `case_linked` / `case_unlinked` custody
events on the artifact; re-linking an existing member records nothing. Deleting a case removes only
the case and its links. The evidence report gains an artifact-level `cases` list, and
`DeletionSummary` gains `case_links`.

### Integration (read-only, off by default)

- `GET /integration/version` — always readable: the integration version, report schema version, app
  version, schema revision, whether it is enabled, and every endpoint offered (all GETs).
- `GET /integration/artifacts/{artifact_id}/evidence` — one versioned envelope containing the
  evidence report, the chain of custody, and the artifact's cases. Returns 409
  `INTEGRATION_DISABLED` until the analyst sets `integration_api_enabled`.

The surface has **no write route of any kind**, so an external system can never create, change,
re-classify, or delete anything Vestigo holds. Reading records no custody event. Import is
deliberately absent: evidence leaves Vestigo, it never arrives from outside.

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