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

## 10. Milestone 5 tests (reverse-image search, D22)

Backend:

- Registry listing: all four providers, disabled by default, plain https landing URLs with no query
  parameters; enabling via settings round-trips; unknown provider keys are rejected with nothing
  changed (for API updates and stored values alike).
- Leads: recorded exactly as entered (claimed date never parsed), EXTERNAL and UNREVIEWED by
  default; subject rules (image leads omit the derived file, video leads require a real keyframe of
  that artifact, non-keyframe files and foreign files rejected, audio refused); URL and field
  validation; 404s.
- Custody: lead_recorded / lead_updated (changed field names only) / lead_deleted; no-op saves
  record nothing; the trail survives the lead's deletion.
- Integration: leads in the evidence report and the export package's report.json, their events in
  custody.json, deletion cascading and counting them.
- Downloads: `download=true` answers as an attachment with the honest filename and the protective
  headers kept, byte-identical to the inline response.
- Migrations: v1/v2 databases upgrade in place to schema_version 6 with every row unchanged; the
  external_leads table shape, FK validation, and cascade.

Frontend: the sharing warning and the cannot-observe note; provider links only when enabled (new
tab, noopener, plain URL) and "enable in Settings" otherwise; the keyframe-only subject picker with
the preview never offered and recording blocked until a keyframe is chosen; the recorded payload;
lead rows with EXTERNAL, "Recorded" vs "Publication date (analyst-reported, unverified)", and the
never-proof-of-origin notice; review select and two-step delete; the panel absent on audio pages;
Settings toggles off by default with the policy note.

## 11. Milestone 6 tests (GEOINT / geo-lite, D23)

Backend:

- Clues from the GPS fixture: decimal conversion with the hemisphere ref applied (51.5 / −0.12), the
  as-written strings and refs kept beside it, IPTC city, EXIF dates, and camera fields each with
  their tag; the southern/eastern fixture (−33.8688 / 151.2093) with altitude, its reference, GPS
  date/time, and XMP place tags; the out-of-range fixture flagged with its reason, kept exactly as
  written, and making the stage `partial` with `LOCATION_VALUE_UNUSABLE`; a video's container
  location tag parsed and recorded as written; media with no location producing empty lists and no
  warnings; audio running the same metadata-only reader; `ocr_available` true only when the
  analysis produced OCR text, with no place names ever extracted from it; limitations and the raw
  ExifTool derived file; the option switched off giving a skipped record.
- Candidates: recorded as entered with fixed UNVERIFIED classification and UNREVIEWED review; the
  assessment required and constrained to speculative / possible / likely (no "confirmed", no
  numbers); field and coordinate validation (ranges, pairs, empty strings, extra fields, 404s);
  supports must exist and belong to the same artifact (another artifact's evidence, unknown ids,
  wrong-prefix ids, and unknown types all refused), including an external lead as support; edits
  custody-trailed with field names only, no-op saves recording nothing, explicit nulls rejected,
  coordinates cleared as a pair, and the trail surviving deletion; candidates in the report, the
  export package's report.json, custody.json, and the deletion summary; coordinates and analyst
  words never reaching the logs across record, edit, and delete.
- Settings: `enable_external_map_links` off by default, toggleable, non-boolean rejected.
- Migrations: v1–v6 databases upgrade in place to schema_version 7 with every row unchanged; the
  `location_candidates` table shape with and without coordinates, FK validation, and cascade.

Frontend: decimal coordinates beside the as-written strings with the as-written and
disagreement wording; a flagged value badged, explained, kept, and never mapped; the
absence-proves-nothing empty state; the OCR pointer; the OpenStreetMap link absent while the
setting is off and, once on, client-built with `mlat`/`mlon`, `noopener`, and its own
coordinate-sharing warning; the candidate form requiring place, basis, and an explicitly chosen
assessment, and the payload it sends; candidate rows showing UNVERIFIED and "the analyst's own
judgment, not a measurement" with basis, supports, review and assessment edits, and a two-step
delete; the custody panel labelling the three candidate events and refetching after a candidate
change; the error/retry path; the Settings map toggle off by default with its warning copy.

## 12. Pass 1 tests (local AI foundation, D24)

Every test runs with fakes: nothing installs the runtime, downloads weights, or reaches the network.

Backend:

- Runtime: the telemetry variables are forced in-process and reported by `/ai/status`;
  `NEEDLE_API_KEY` is never present; every capability is off by default with an actionable reason;
  the label and limitations are served; the known models carry Apache-2.0 and their Hugging Face
  sources with `installed: false`; enabling a capability without the runtime names
  `pip install -e ".[dev,ai]"`; a configured path that does not resolve reports the capability
  unavailable and echoes the bad path; the disabled provider refuses every capability. The Needle
  adapters run against a stand-in module in `tests/unit/test_ai_providers.py` on every machine, and
  against real weights under `pytest -m live_model` (excluded by default, beside `container`).
- Drafts: refused with 409 `AI_UNAVAILABLE` while AI is off; model provenance and the model's own
  confidence recorded (and `null` left alone when the model gives none); the model actually reads the
  held material; per-field accept / edit / reject with the model's value kept beside an edit; an edit
  requiring a value and the other actions refusing one; unknown field 404; custody events carrying
  field names but no content; **the evidence report byte-identical after accepting an edit**.
- Transcripts: images refused; segments, word timing, language, duration, and model provenance
  stored; the analyst's correction kept beside the model's verbatim text; custody for create, edit,
  and delete; a video's audio track extracted to a derived file and served.
- Semantic search: refused until enabled; indexing covers notes, OCR text, metadata, and the
  analyst's own candidates; search ranks their notes; answers always carry sources, draft no prose
  without a generator, and change no stored evidence; scoping to chosen artifacts; the index
  rebuildable, clearable, custody-trailed, counted, and deleted with the artifact.
- Export and deletion: `ai/` area with its README and `drafts.json`, `report.json` free of AI
  material, and all three tables counted in the deletion summary.
- Migrations: v1–v7 databases upgrade in place to schema_version 8 with every row unchanged; table
  shapes, the SET NULL on evidence deletion, and the cascade.

Frontend: the panel's AI label and never-a-finding wording; the model's confidence shown as its own
and "no confidence given by the model" where absent; per-field accept/edit/reject payloads; the
model's value kept beside an analyst edit; the draft request payload; timestamped transcripts with
the machine-generated caveat, model provenance, and the extracted-audio source; a correction that
does not overwrite; no transcript section for an image; the search page's local-only wording,
matches with their source kind and score, answers always showing "Sources - read these", the
no-generator path returning material instead of prose, the empty-index explanation, and errors with
retry; Settings switches off by default with the local-only wording.

## 13. Pass 2 tests (deep media forensics, D25)

- Structural: a clean file reporting no findings while refusing to call itself clean; bytes after a
  JPEG's EOI located and sized; an appended ZIP showing as trailing data plus both its signatures
  with PNG chunk CRCs verified; an oversized comment segment; image LSB measurements carrying their
  method and caveat; video box and audio RIFF inventories; an unparsed container recorded as a scope
  note with the stage still succeeding; the raw report kept as a derived file; the option switched
  off; the original bytes unchanged; and a guard that no verdict language reaches the findings while
  the limitations do name those claims to deny them.
- Forensic indicators: quantisation tables with an implied quality in range; a non-JPEG saying
  tables do not apply while still measuring pixels; channel statistics and decoded dimensions;
  video keyframe and packet distributions; the absence of ELA and of verdict language; DERIVED
  classification; the option switched off.
- Documents: PDF upload typed as `document`; the document.v1 stage list; structure facts with the
  signature and incremental-save honesty wording; JavaScript, open-action, and form markers as
  presence counts; provisional text with non-text streams skipped rather than failed; an image-only
  document explaining that the pages are not blank; an embedded JPEG extracted **byte-identical** to
  the original and served; byte-identical-only duplicates with a re-saved copy not matching;
  endpoint guards both ways; per-stage options; and the original file and its served bytes
  unchanged.
- Frontend: all three panels' wording and data, the document page end to end, the signature and
  repeated-save explanations, the empty-text path, and the feature list as presence counts.

## 14. Pass 3 tests (GEOINT tooling and integration, D26)

- Coordinate tooling: each notation for the same point including southern/eastern hemispheres;
  distance and bearing against known values (London-Sydney, due north, due east, zero); held clues
  and analyst candidates listed with their source and the geometry between them; a flagged
  coordinate excluded from geometry while staying in the evidence as written; candidates without
  coordinates skipped; offline map absent unless configured; unknown artifact refused.
- Cases: grouping that leaves every evidence section byte-identical; custody events for link and
  unlink with re-linking recording nothing; deleting a case leaving the artifact and its evidence
  intact; deleting an artifact removing only its links and counting `case_links`; name and null
  validation; 404s.
- Integration: the version endpoint readable while disabled and listing only GETs; evidence refused
  with 409 `INTEGRATION_DISABLED` until enabled; the versioned envelope carrying report, custody,
  and cases; reading writing no custody event and changing no evidence; **every write verb refused
  by routing itself**.
- Migrations: v1-v8 databases upgrade in place to schema_version 9 with every row unchanged.
- Frontend: the cases control's wording and its link/unlink/create calls; the coordinate panel's
  notations, geometry, hidden-when-empty behaviour, and error/retry; the custody timeline's labels
  for every Pass 1 and Pass 3 event.

## 15. Container tests

- Backend starts on port 8400
- Frontend starts on port 5180
- ExifTool is available
- Tesseract is available
- FFmpeg is available
- ffprobe is available
- SQLite database initializes correctly