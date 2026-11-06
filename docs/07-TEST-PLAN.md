# Test Plan

## 1. Testing principles

- Test observable behavior.
- Test failure paths.
- Test evidence completeness.
- Test deletion.
- Do not test unsupported capabilities as if they exist.

## 2. Backend tests

### Upload tests

- Valid JPEG upload succeeds
- Valid PNG upload succeeds
- Valid WebP upload succeeds
- Valid TIFF upload succeeds
- Unsupported file type is rejected
- Oversized file is rejected
- Empty file is rejected
- Filename path traversal is prevented

### Hashing tests

- SHA-256 is calculated
- MD5 is calculated
- Same file produces same hashes
- Different files produce different hashes

### Metadata tests

- EXIF is extracted
- XMP is extracted
- IPTC is extracted
- Missing metadata returns empty structure
- Corrupt metadata does not crash pipeline

### C2PA tests

- File without C2PA returns `present: false` (and, since M4, `status: "absent"`)
- File with C2PA returns detected status
- Invalid C2PA does not crash pipeline
- Milestone 4 validation tests are in §9

### pHash tests

- pHash is generated
- Identical images produce same hash
- Similar images produce close hashes
- Duplicate search returns expected matches

### OCR tests

- Image with clear text produces extracted text
- Image without text returns empty result (blank image and a textured image with no text)
- OCR failure is recorded, not hidden
- Word recovery is measured against the single-pass behaviour before D13
  (`python -m tests.fixtures.measure_ocr`). Improvement is asserted only where the gain is stable;
  elsewhere the tests assert no regression:
  - clean rendered text: no regression
  - screenshot-style text, including light-on-dark title bar and button text: improvement
  - low-resolution text: no regression; upscaling applied and recorded
  - stylised, noisy, low-contrast text: improvement, through the threshold pass
- Pass selection rule, at and either side of each limit
- Cleaning removes only symbol-only lines and whitespace, never a line containing a letter or digit;
  raw text stays in `text`; every rule that changed the text is recorded
- Upscale factor limits, threshold output and parameters, orientation and transparency handling
- Original upload is unchanged; grayscale and threshold images and both TSVs are stored as derived files
- Threshold pass failure makes the stage `partial` with `OCR_VARIANT_FAILED`; grayscale pass failure
  fails the stage
- API returns `cleaned_text`, `preprocessing`, `candidates`, and `selected`; OCR records made before
  two-pass OCR still render

### Evidence tests

- Every stage creates an evidence record
- Every record includes tool and timestamp
- Every record includes limitations
- Failed stage is visible in evidence output

### Deletion tests

- Deleting artifact removes original file
- Deleting artifact removes derived files
- Deleting artifact removes evidence records
- Deleting artifact removes database rows

## 3. API tests

- `GET /health` returns 200
- `POST /artifacts/upload` returns artifact ID
- `POST /analysis/image` returns job ID
- `GET /analysis/jobs/{job_id}` returns status
- `GET /artifacts/{artifact_id}/evidence` returns report
- Invalid artifact ID returns 404
- Invalid job ID returns 404

## 4. Frontend tests

- Upload form accepts image
- Upload shows progress
- Analysis result renders
- Metadata section renders
- OCR section renders: cleaned text with the raw output alongside, the pass used and why, each pass's
  result or error, and preprocessing steps; OCR records made before two-pass OCR still render
- Duplicate section renders
- Review state can be changed
- Error message displays correctly

## 5. Milestone 2 tests (analyst workflow)

Backend:

- Migrations: the Alembic baseline reproduces the frozen Milestone 1 schema
  (`tests/fixtures/m1_schema.sql`); the models match the head revision; a Milestone 1 database with
  data in every table upgrades in place with every row unchanged; a failed upgrade changes nothing; a
  newer revision, or an unknown database without history, is refused.
- Library: each filter and search field, literal `%` and `_`, Unicode case folding, every sort in both
  directions with stable ties, pagination, invalid parameters, and indicator values.
- Review: events with full notes, no-op saves, conflicts, bulk all-or-nothing and the 200 limit,
  record review leaves classification unchanged, history, append-only events enforced by the
  database, deletion removes events, notes never logged.
- Analysis history; duplicate-library exclusion (skipped and counted, evidence never rewritten,
  re-include); library summary.
- Evidence package: contents, manifest and `SHA256SUMS` re-verified, original only on request,
  earlier jobs, missing or changed derived files reported, errors, temporary file removed, no verdict
  wording.
- Settings: defaults, partial updates persisted across restarts, validation, environment keys
  rejected, invalid stored values ignored, defaults applied to analyses, values not logged.
- Access logs redact query strings.

Frontend:

- Library: URL state, search, filters, sort, pagination, indicators, empty / no-results / loading /
  error states, bulk review with confirmation and result.
- Artifact: review conflicts, unsaved-changes guard, review history, record review, problems summary,
  analysis history, export (with the package SHA-256), duplicate-library control and re-run hint,
  load errors with retry, not-analysed state.
- Settings page and saved defaults (upload, Library page size, re-run); health banner.

## 6. Milestone 3 tests (video foundation)

Backend:

- Upload and validation: each container classified from its bytes (WebM by codec profile), MOV by
  ftyp brand, rotated and audio-less videos accepted, audio-only and truncated files rejected,
  per-type size caps, duration and resolution limits, read-only originals, Range requests.
- Migrations: v1 and v2 databases upgrade to v3 in place without data loss; keyframe fingerprints
  cascade and enforce their foreign keys.
- media_info values match the fixtures (codec, dimensions, frame rate, audio facts, rotation);
  raw ffprobe output stored.
- Scene detection finds exactly the fixture's cuts and nothing in a static clip; threshold
  recorded; parsing unit-tested.
- Keyframe policy: first frame always, scene frames with scores, uniform fill, dedupe window,
  cap keeps highest scores, end margin; rotated frames extracted upright; failed extractions are
  warnings, never silent.
- Keyframe pHash per frame; index replaced on re-analysis and deleted with the artifact; a
  half-resolution VP9 re-encode hashes within the threshold frame for frame.
- Keyframe OCR off by default; when enabled reads the drawn scene text on an evenly spaced subset
  (≤ 10), stores per-frame TSVs, and records frame failures.
- Duplicates across media: re-encoded video found with same-scene frame pairs; a still finds the
  video it came from and vice versa; unrelated videos do not match; exact-file, exclusion, and
  Library indicators hold; image-to-image matches keep their Milestone 1 shape.
- WRONG_MEDIA_TYPE on both analysis endpoints; derived-content endpoint scoped to its artifact.
- Video deletion removes originals, derived files, evidence, and fingerprints; the export package
  carries keyframes and raw tool output with verified hashes.

Frontend: video upload flow with the video checks (keyframe OCR off by default), video playback
with a codec fallback, media info / scene changes / keyframes / keyframe OCR / keyframe hash
panels, duplicate frame pairs, Library durations and video type filter, video defaults in
Settings, and the read-only video limits.

## 7. D19 tests (cross-media search, formats, audio, previews)

- Rotated (display-matrix) and mirrored video copies match their original with the orientation
  recorded; rotated and mirrored image copies match both ways; upright matches keep reporting as
  upright and image-to-image keeps the Milestone 1 shape; no new false matches; the keyframe index
  stays canonical.
- Each new container classified from bytes with the right stored extension; AVI and MPEG-TS run the
  full pipeline (TS pins ExifTool's minor advisory as a surfaced warning); a TS remux matches its
  MP4 original.
- Audio: each format classified; the audio pipeline runs exactly hashes, media info, metadata, and
  duplicates; a byte-identical copy matches and a re-encode does not (with the limitation saying
  so); exclusion honoured; limits enforced; endpoint guards in all directions; Library filters and
  deletion.
- Previews: created capped and H.264-playable with Range; idempotent; original untouched read-only;
  refused for non-videos; failures leave nothing; deleted and counted with the artifact; never in
  the evidence package; storage counted separately. Migrations v1–v3 → v4 without data loss.
- Frontend: audio upload flow and player; preview create/swap flow with the viewing-copy label;
  keyframe captions, orientations, empty, error+retry, and per-job keyframes; per-frame OCR status,
  no-text wording, failure rows, disabled state, raw output.

## 8. Milestone 4 tests (C2PA validation and provenance, D20)

Validation unit tests (locally signed fixtures from a throwaway test CA, plus one real public
Content Credentials sample):

- The validator version string names the exact library and SDK versions.
- A validly signed JPEG, MP4, and WAV each return `status: "valid"` with the signer's certificate
  details, assertion labels, and the standing `signingCredential.untrusted` failure code (no trust
  list) — surfaced, never hidden.
- A byte-tampered signed file returns `invalid` with the hash-mismatch code recorded.
- A re-signed file with an ingredient chain reports both manifests and the active one.
- A file without C2PA data returns `absent`; an unsupported container returns `unverifiable` with
  the validator's error.

End-to-end API tests:

- Valid signed media analysed through each pipeline (image, video, audio) reports the full
  validated section, and the honesty limitations are present on every record.
- The raw manifest store is a derived file: served by the derived-content endpoint, included in the
  evidence package, and removed by deletion with everything else.
- Disabling the `c2pa` option skips the stage with a recorded skip reason (video and audio).
- Original files are byte-identical before and after analysis.
- Pre-M4 records (`validation_performed: false`) still render.

Frontend:

- The provenance panel shows all four states with their badges and caveats (valid ≠ truthful,
  absence proves nothing), signer details marked recorded-as-written, failure codes, the validator
  version, and renders on image, video, and audio pages; pre-M4 records render as detection-only.
- The `c2pa` check appears in the upload options and settings defaults for video and audio.

## 9. Milestone 4 part 2 tests (chain of custody, D21)

Backend:

- custody_events is append-only (updates and deletes rejected by triggers) until the artifact's
  cascade delete; v1/v2 databases upgrade in place to schema_version 5 with every row unchanged;
  derived-file source columns are NULL on pre-0005 rows and foreign-key-checked on new ones.
- Every recording point: a successful export records the package SHA-256 and original_included
  (and each export appears in the next package's custody.json, never its own); the library toggle
  records before/after and a no-op save records nothing; preview creation records once and the
  idempotent path records nothing.
- Lineage: keyframe-OCR TSVs point at the exact keyframe thumbnail they read; every other derived
  file records "original".
- The custody timeline merges upload, jobs (with evidence and derived-file counts), review changes
  (note text never included), and custody events chronologically, each entry naming its source
  table; invalid and unknown artifact ids return 404.
- custody.json is in the export package with a verified hash; deletion removes custody events and
  counts them in the deletion summary.

Frontend: the panel shows the honesty notice, one factual line per event type, the indented
lineage tree, "source not recorded" for pre-0005 rows, and a load error with retry.

## 10. Container tests

- Backend starts on port 8400
- Frontend starts on port 5180
- ExifTool is available
- Tesseract is available
- FFmpeg is available
- ffprobe is available
- SQLite database initializes correctly