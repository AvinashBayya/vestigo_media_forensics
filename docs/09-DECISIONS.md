# Decisions

## D1 — Local-first

All media and evidence remain local by default.

## D2 — Evidence over verdicts

The system reports observable signals. It does not decide whether media is true or false.

## D3 — Human approval

Only a human analyst can mark evidence as reviewed, confirmed, or publishable.

## D4 — Simple visible product

The UI remains minimal. Advanced engine capabilities must not clutter the analyst workflow.

## D5 — Milestone 1 is image-only

Video, reverse-image search, GEOINT, satellite imagery, and Vestigo integration are later phases.

## D6 — FFmpeg installed early

FFmpeg and ffprobe are installed during environment setup but are not invoked until the video pipeline is implemented.

## D7 — Ports

- Backend: 8400
- Frontend: 5180

## D8 — External services are gated

External providers must be permission-gated, licence-aware, and clearly labeled.

## D9 — No facial recognition

The system must not perform facial recognition, biometric identification, or automated identity attribution.

## D10 — No offensive security features

No active scanning, exploitation, credential testing, evasion, or stealth functionality.

## D11 — Deletion is complete

Deleting an artifact removes its files, jobs, evidence, and database records.

## D12 — Claude must plan before coding

Claude Code must read all docs and produce a build plan before implementation.

## D13 — OCR preprocessing is complete. The measured OCR result is approximately 55% on the current test set.

Decision:
- Accept current OCR as best-effort, English-only, local OCR for Milestone 1.
- Do not continue tuning OCR now.
- Do not add OpenCV, external OCR APIs, cloud OCR, additional languages, or new OCR engines.
- Ensure the UI clearly labels OCR output as provisional and shows Tesseract confidence as the engine's own estimate.
- Ensure raw OCR output, preprocessing steps, selected pass, confidence, limitations, and errors remain visible in the evidence report.
- Add a decision record to docs/09-DECISIONS.md:
  "OCR is best-effort in Milestone 1. OCR output is provisional evidence, not a verified transcription. Further OCR tuning is deferred."

Then commit the documentation update with:
"docs: record OCR as best-effort provisional evidence for Milestone 1"

After that, stop. Do not begin Milestone 2 until I approve.

- **Pass A (grayscale):** upright, greyscale, and upscaled with Lanczos by the largest whole-number
  factor up to 3x that keeps the longest side at or below 2000 px.
- **Pass B (threshold):** pass A's image after a local-mean adaptive threshold (window radius 15 px
  times the upscale factor; a pixel becomes black when it is more than 20 grey levels darker than
  its local mean).
- **Selection:** pass B is used only if it raises mean Tesseract confidence by at least 0.05 and
  keeps at least 80% of pass A's words, or, when pass A finds no words, if its mean confidence is at
  least 0.70. Otherwise pass A is used. The word-count condition stops thresholding from "winning"
  by dropping hard words, such as light-on-dark text, which raises average confidence.
- Both passes, every preprocessing step and its parameters, and the reason for the selection are
  recorded in evidence. If pass B fails the stage is `partial` (`OCR_VARIANT_FAILED`); if pass A
  fails the stage fails. Each pass has the existing OCR timeout, so OCR takes up to about twice as
  long.
- **Cleaning** is cosmetic and separate: `text` keeps the raw output; `cleaned_text` removes only
  lines without any letter or digit, trailing whitespace, and repeated blank lines.

Selection relies on Tesseract's confidence, which is the engine's own estimate and not a measured
accuracy. No accuracy claim is made in the UI or in evidence.

### Measured word recovery

Generated test images, "before" being the single Tesseract pass used before this decision
(`python -m tests.fixtures.measure_ocr`, Tesseract 5.5.0, Pillow 13.0.0). Results were identical
across repeated runs.

| Image | Expected words | Before | After | Confidence before → after | Pass used | Upscale |
|---|---|---|---|---|---|---|
| Clean rendered text | 4 | 4 | 4 | 0.95 → 0.95 | grayscale | 1x |
| Screenshot-style text | 11 | 9 | 11 | 0.92 → 0.96 | grayscale | 2x |
| Low-resolution text (8 px) | 5 | 0 | 5 | none → 0.57 | grayscale | 3x |
| Stylised, noisy, low-contrast text | 4 | 0 | 4 | none → 0.86 | threshold | 2x |
| Blank image | 0 | 0 | 0 | none → none | grayscale | 3x |
| Textured image, no text | 0 | 0 | 0 | none → none | grayscale | 3x |
| Low-resolution text (9 px, not a test fixture) | 5 | 5 | 4 | 0.82 → 0.91 | grayscale | 3x |

These are six generated images, not a benchmark, and do not establish an accuracy figure. Tests
assert improvement only where the gain held across upscale factors (screenshot and noisy text);
for clean and low-resolution text they assert no regression. The 9 px row is a measured
regression: upscaling read "4821" as "4822" while confidence went up. The 8 px gain is therefore not
treated as stable, and the OCR limitations tell analysts to check numbers and names against the
image.

## D14 — OCR is best-effort provisional evidence in Milestone 1

OCR is best-effort in Milestone 1. OCR output is provisional evidence, not a verified transcription.
Further OCR tuning is deferred.

- OCR remains Tesseract, English only, local, with the D13 preprocessing as implemented.
- Not added in Milestone 1: OpenCV, external or cloud OCR services, additional languages, or other
  OCR engines.
- The UI labels OCR output as provisional (including when no text is detected) and shows Tesseract
  confidence as the engine's own estimate, never as accuracy.
- The evidence report keeps the raw OCR text, preprocessing steps and parameters, the selected pass
  and the reason for it, confidence, limitations, and errors.

## D15 — Milestone 2 scope and decisions

Milestone 2 (Analyst Workflow) follows the approved plan in `12-MILESTONE-2-PLAN.md`, decisions
M2-1 to M2-11. In summary: Alembic migrations with in-place upgrade of Milestone 1 databases;
per-evidence-record review that never changes classification; append-only review history with full
note text; archived artifacts hidden by default; bulk review limited to 200 artifacts, all-or-nothing;
a ZIP evidence package with a SHA-256 manifest (original only on request; no HTML or PDF);
duplicate-library include/exclude that affects future searches only; editable defaults with the
duplicate threshold read-only; the Library as the home page; no OCR-text search and no thumbnails.

## D16 — Milestone 2 implementation notes

Details settled while implementing D15, recorded so later work keeps them:

- `GET /artifacts` keeps `include_archived=true` as its default so existing clients see every artifact;
  the Library sends `false`.
- Library search matches artifact IDs only for ID-like terms (`art_…` or 8+ hex characters), so a
  search for `_` does not match every `art_` ID. Case folding is Unicode-aware through a
  `vestigo_casefold` SQL function.
- Query strings are redacted from uvicorn access logs, because they carry search terms.
- Review conflicts are detected only when the client sends `expected_updated_at`; the Library and
  artifact pages always send it. A save that changes nothing writes no event.
- The duplicates stage's `library_size` now counts the artifacts actually searched; excluded artifacts
  are counted in `excluded_count`.
- The evidence package adds `SHA256SUMS` alongside `manifest.json` for `sha256sum -c`, and the UI shows
  the package SHA-256 after download.
- Settings that are security limits or affect recorded evidence (the duplicate threshold) stay in the
  environment and are read-only in the UI.
- The frontend uses a React Router data router so the unsaved-changes guard can block navigation.


## D17 — Milestone 3 scope and decisions

Milestone 3 (Video Foundation) follows the approved plan in `13-MILESTONE-3-PLAN.md`, decisions
M3-1 to M3-8. In summary: MP4/MOV/WebM/MKV only, detected from bytes; limits of 500 MB, 15 minutes,
4K per frame, 40 keyframes, scene threshold 0.3, and a 600 s ffmpeg timeout, all environment-set and
read-only in the UI; keyframe OCR off by default and capped at 10 frames when enabled, reusing D13
OCR unchanged; duplicate search spans images and video keyframes in both directions, changing stage
method texts for new records only; the existing ExifTool metadata stage runs on videos; no
transcoding (browser playback via the content endpoint with Range, with a fallback message); audio
is inspected through ffprobe stream metadata only; duration is stored and labelled as
container-reported. ffprobe provides media information; ffmpeg provides scene detection and keyframe
extraction. No facial recognition, speaker identification, transcription, deepfake detection,
verdicts, ELA, or C2PA validation.

## D18 — Milestone 3 implementation notes

Details settled while implementing D17, recorded so later work keeps them:

- An EBML upload is classified as WebM only when every stream fits the WebM codec profile
  (VP8/VP9/AV1 video, Vorbis/Opus audio); otherwise it is Matroska. MP4 vs MOV comes from the
  ftyp major brand.
- The upload stream cap is the video limit; the image limit is re-checked once the file sniffs as
  an image. ffprobe validation ignores attached-picture "video" streams (cover art).
- The video duplicate stage is also named `duplicates`, so the Library's match indicators, filters,
  and "added since analysis" cover videos with no changes. Matching pairs each query hash with its
  best counterpart (at most one pair per query frame); image-to-image matches keep the Milestone 1
  payload shape with null frame fields.
- Keyframe OCR stores raw TSVs per analysed frame and pass but not the prepared pass images (the
  keyframe thumbnails themselves are stored); the stage method says so.
- Job history reports each job's options exactly as recorded, since image and video option sets
  differ.
- Evidence contract clarification pinned by tests: `tool_version` is null only for records whose
  stage never invoked its tool (skipped stages).
- pHash pairs flat-field frames with same-position text across different scenes (a coarse-structure
  measure); the duplicate tests document this rather than hiding it.

## D19 — Cross-media search, more formats, audio, and viewing previews

Approved 2026-11-04 as one pass, all additive; nothing existing was removed or reshaped.

- **Rotated and mirrored duplicate matching.** The pHash stages also hash each image and keyframe
  under the seven non-upright dihedral orientations (rotations are counter-clockwise); duplicate
  search compares the query's variants against the canonical indexes and records
  `rotation_degrees`/`mirrored` per frame pair. Upright wins ties, image-to-image upright matches
  keep the Milestone 1 payload shape, and the threshold stays 10 (correct orientations measured at
  0–4; wrong orientations at 26+).
- **Containers.** AVI, MPEG-TS, WMV/ASF, and FLV are sniffed by byte signature (the sniff window is
  512 bytes for the three TS sync positions), and MP4-family brands label 3GP/3G2 and M4V honestly.
  ExifTool's minor MPEG-TS advisory is surfaced as a metadata warning, never hidden.
- **Audio, integrated.** WAV, MP3, FLAC, OGG, and M4A are accepted; one ffprobe run at upload
  decides video vs audio (no real video stream → audio for audio-capable families; cover art does
  not count). `audio.v1` reuses the existing hashes, media-info, and metadata stages; its duplicate
  search is byte-identical SHA-256 only — no audio decoding, fingerprinting, transcription, or
  speaker identification — and the evidence says a re-encoded copy will not match. Limits:
  VESTIGO_MAX_AUDIO_UPLOAD_BYTES (200 MB), VESTIGO_MAX_AUDIO_DURATION_SECONDS (7200 s).
- **Playable previews (amends M3-6).** On demand only, a video the browser cannot play can get one
  re-encoded H.264/AAC viewing copy (longest side ≤ 1280, bounded by the video timeout), stored
  read-only in `playable_previews` (Alembic 0004, schema_version 4). A preview is a viewing aid,
  not evidence: labelled as such in the UI, excluded from the evidence package, counted separately
  in storage and deletion summaries, and deleted with the artifact. The original is only ever read.
- **Keyframe and OCR panel clarity.** Keyframe captions carry number, timestamp, and the exact
  selection reason; fixed-aspect cells handle portrait and landscape; thumbnails get an inline
  error with retry and an explicit empty state. The keyframe OCR panel shows a per-frame status for
  every keyframe (ran / text found with the raw output expandable / failed with the recorded error /
  outside the OCR limit), keeps the provisional (D14) labelling prominent, and words an empty result
  as "no text was detected", never "the frame contains no text".


## D20 — Milestone 4: local C2PA validation and provenance evidence

Implemented 2026-11-06. The `c2pa` stage validates manifests instead of only detecting them, and it
runs for images, videos, and audio (a new optional `c2pa` stage in `video.v1` and `audio.v1`,
default on).

- **Validator.** `c2pa-python` 0.38.1, which bundles the Rust c2pa-rs SDK 0.91.3. Validation is
  entirely local: no trust list is configured and no network is used. The evidence records the exact
  validator version string (`c2pa-python 0.38.1 (c2pa-rs 0.91.3)`).
- **Four-way outcome.** Every record carries a Vestigo summary `status`: `valid` (hashes and claim
  signature verify), `invalid` (data present but a check failed), `unverifiable` (data detected or
  claimed but the validator could not read it, e.g. an unsupported container — recorded with the
  validator's own error), or `absent`. The SDK's own `validation_state` and its grouped validation
  codes (success / informational / failure) are stored verbatim.
- **Honesty rules.** `valid` never means truthful, accurate, or unmanipulated, and without a trust
  list it never establishes the signer's identity (the standing `signingCredential.untrusted` code
  is surfaced, not hidden). Absence is normal and proves nothing. An invalid manifest is a finding,
  not a stage failure; detected-but-unreadable C2PA data makes the stage `partial` with
  `C2PA_VALIDATION_UNAVAILABLE`. Manifest names and certificate fields are recorded as written.
- **Evidence.** Per manifest: claim generator, title, signer certificate issuer / common name /
  serial / time / algorithm, assertion labels, and ingredient count, plus the manifest count and
  active manifest. The validator's full manifest-store report is stored as a derived file
  (`manifest_store.json`), so it is exported in the evidence package and deleted with the artifact
  like any other derived evidence.
- **Compatibility.** The report section grew additively; `validation_performed` stays `false` on
  records made before M4 and the UI renders those as detection-only with a pointer to re-run. The
  image stage keeps its byte-level and ExifTool detection alongside validation. No schema migration
  was needed (payloads and derived files reuse the v4 schema).
- **Fixtures.** Test media is signed by a throwaway OpenSSL ES256 CA built in
  `tests/fixtures/make_fixtures.py` (valid JPEG/MP4/WAV, a two-manifest chain, and a byte-tampered
  copy), plus one real public Content Credentials sample. Originals are never modified by analysis;
  signing happens only in the fixture builder.

## D21 — Milestone 4 part 2: chain of custody and derived-file lineage

Implemented 2026-11-06 (approved plan `14-MILESTONE-4B-PLAN.md`, decisions M4B-1…7 confirmed by the
user, including: timeline granularity is jobs and major actions, never per-stage records; the
lineage tree lives inside the Chain of custody panel).

- **Honest definition.** The chain of custody is what Vestigo recorded on this machine since
  upload. It is not a legal chain of custody, says nothing about the file before upload, and never
  infers or backfills events: exports and duplicate-library changes made before revision 0005 were
  not recorded anywhere and do not appear — the notice says so.
- **Schema (Alembic 0005, schema_version 5, additive).** `custody_events` is append-only (database
  triggers, cascade-delete with the artifact) and records only the three actions that previously
  left no trace: evidence-package export (package SHA-256, original_included, counts),
  duplicate-library changes (before/after; a no-op save records nothing), and preview creation
  (once; the idempotent path records nothing). `derived_files` gains nullable `source_kind` and
  `source_derived_file_id`; keyframe-OCR TSVs point at the exact keyframe thumbnail they read,
  everything else records "original", and pre-0005 rows stay NULL ("source not recorded").
- **API.** `GET /artifacts/{id}/custody` merges upload, jobs (started/finished with evidence and
  derived-file counts), review changes (states and whether notes changed; note text stays in the
  review history), and custody events into one chronological timeline, each entry naming its source
  table, plus every derived file with its lineage. The export package gains `custody.json`, hashed
  in the manifest; a package is built before its own export event is recorded, so each export
  appears in the next package's custody.json (stated in the README inside the package).
- **UI.** One Chain of custody panel on the artifact page (no separate page): notice, timeline,
  and the indented lineage tree. `DeletionSummary` counts `custody_events`; deletion removes them.

## D22 — Milestone 5: reverse-image search, manual-first

Implemented 2026-11-07 (approved plan `15-MILESTONE-5-PLAN.md`, decisions M5-1…9 confirmed by the
user with the proposed defaults: the four initial providers, editable custody-trailed leads, and
lightweight lead review).

- **Manual-first, nothing transmitted.** Vestigo opens a provider's plain landing page in a new tab
  (https, no query parameters, nothing evidence-derived, `noopener noreferrer`), shows manual-upload
  instructions and the provider's terms link, and serves the exact subject file as a download
  (`?download=true` on the content endpoints, protective headers unchanged). The backend makes no
  outbound HTTP requests. No prefilled search links: no listed provider officially accepts a URL the
  tool can supply (a localhost path is not public). A sharing warning precedes every provider link,
  and the UI states that Vestigo cannot observe or record anything after the page opens.
- **Providers, disabled by default** (05 §4): Google Lens, Bing Visual Search, TinEye, Yandex
  Images, in a static code registry; enabled individually via the `enabled_search_providers`
  setting, validated against registry keys for API updates and stored values alike. Paid or
  official provider APIs each need their own approval.
- **Search subjects** (M5-2): the original image, or one selected video keyframe (its real derived
  file, kind `keyframe_jpeg`). Audio is refused; the playable preview is never offered or
  substituted.
- **Leads are analyst statements** stored in `external_leads` (Alembic 0006, schema_version 6,
  additive): provider, result URL, optional image URL, notes, and the claimed publication date
  exactly as entered — always labelled analyst-reported and unverified, distinct from
  `recorded_at`. Classification is fixed EXTERNAL; review is the lightweight `review_state`
  starting UNREVIEWED. Nothing ever calls the earliest result "the original source".
- **Custody-trailed edits.** Leads are editable; every create, update (changed field names only),
  and delete writes an append-only custody event (`lead_recorded` / `lead_updated` /
  `lead_deleted`); no-op saves record nothing, and a deleted lead's history stays in the trail.
  Leads flow into the evidence report (artifact-level `external_leads`), the export package
  (report.json; events in custody.json), and the deletion summary, and cascade-delete with the
  artifact.
- **Refused capabilities**: automated scraping, CAPTCHA bypass, browser automation, rate-limit
  evasion, automatic media uploads.

## D23 — Milestone 6: GEOINT / geo-lite, clues not claims

Implemented 2026-11-07 (approved plan `16-MILESTONE-6-PLAN.md`, decisions M6-1…11 confirmed by the
user with the proposed defaults: UNVERIFIED classification, speculative/possible/likely assessment
labels, the gated OpenStreetMap link, and audio included).

- **Machine clues, read as written.** A new `location_clues` stage (optional, default on) runs in
  all three pipelines. Two ExifTool passes give numeric values and the as-written strings:
  coordinates are reported in decimal beside the originals (hemisphere refs applied from the signed
  Composite pair, or from the raw EXIF pair plus its refs), with altitude and its reference,
  location-relevant timestamps, device/orientation fields, and the location-named IPTC/XMP text
  fields — each labelled with the tag it came from. Container location tags (QuickTime/Matroska
  ISO 6709) are recorded as written and parsed when readable, in raw or ExifTool-normalised form.
  Sources that disagree are both shown; nothing is reconciled or prioritised. OBSERVED
  classification; raw ExifTool output kept as a derived file.
- **Validation, never correction.** Latitude within ±90 and longitude within ±180 are checked per
  value; out-of-range or half-present pairs are flagged with the reason and kept exactly as
  written, making the stage `partial` with `LOCATION_VALUE_UNUSABLE`. Nothing is dropped, fixed, or
  normalised.
- **No inference from content.** No place names are extracted from OCR text and nothing is inferred
  from audio: the section records only whether the analysis produced OCR text, and the UI points the
  analyst at it. Audio runs the same metadata-only reader; no audio is decoded.
- **Analyst interpretation is separate and labelled.** `location_candidates` (Alembic 0007,
  schema_version 7, additive, `loc_` prefix) holds the analyst's stated place, required basis,
  required assessment label (speculative / possible / likely — their own judgment, never derived or
  displayed automatically, and deliberately without a "confirmed" value), optional range-validated
  coordinate pair, notes, and typed references to supporting evidence of the same artifact
  (evidence records, derived files, external leads — each checked to exist and belong to it).
  Classification is fixed **UNVERIFIED**: an analyst interpretation of Vestigo-held evidence, with
  EXTERNAL reserved for provider leads and externally sourced references. Lightweight review starts
  UNREVIEWED.
- **Custody and lifecycle.** Create, update (changed field names only), and delete write append-only
  custody events (`location_candidate_recorded` / `_updated` / `_deleted`); no-op saves record
  nothing; custody details carry no coordinates, only whether any were given. Candidates flow into
  the evidence report, export package, custody.json, and deletion summary, and cascade-delete with
  the artifact.
- **The only external map affordance** is an opt-in OpenStreetMap link (`enable_external_map_links`,
  default false). The URL is built entirely in the browser — the backend never constructs, stores,
  transmits, or logs a coordinate-bearing URL — and opens in a new tab on click, with its own
  warning that clicking sends those coordinates to openstreetmap.org. No tiles, no iframe, no
  auto-loading, no API key, no other map provider. Reverse geocoding is **not** enabled in this
  milestone. This is a deliberate carve-out from the M5 wording in 05 §4 ("no query parameters,
  nothing evidence-derived"), which was written for static provider landing pages.
- **Privacy.** Coordinates are sensitive EXIF (05 §7): they never appear in backend logs, which a
  test enforces across record, edit, and delete. The backend makes no outbound HTTP request.
- **Refused in this milestone**: facial recognition, biometrics, person tracking, covert
  surveillance, automated geolocation verdicts, satellite imagery, terrain analysis, shadow/solar
  positioning, advanced geolocation automation, social-media intelligence, AI captions,
  transcription, steganography, scraping, CAPTCHA or rate-limit evasion, cloud-first processing,
  Vestigo integration, multi-user login, and cloud storage.
