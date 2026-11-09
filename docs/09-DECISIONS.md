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

## D24 — Pass 1: local intelligence foundation (Cactus, Needle, Whistle)

Implemented 2026-11-07 (plan `17-CONSOLIDATED-CAPABILITY-ROADMAP.md`). The three named tools are all
Cactus Compute's, all Apache-2.0, CPU-only and tens of megabytes: **Cactus** (inference engine,
`pip install cactus-compute`), **Needle** (tool calling, structured extraction, embeddings, ASR
host; `pip install cactus-needle`, `import needle`, weights
`huggingface.co/Cactus-Compute/needle3`) and **Whistle** (16.9 MB speech-to-text on the Needle
engine, weights `huggingface.co/Cactus-Compute/whistle`). Licence names and source URLs are recorded
in the roadmap and in every stored artifact's provenance; the user handles licence and deployment
approval.

- **AI output is never evidence.** It lives in `ai_drafts`, `transcripts`, and `embedding_chunks`
  (Alembic 0008, schema_version 8, additive), never in `evidence_records`, carries no
  OBSERVED/DERIVED classification, is absent from the evidence report, and travels in the export
  package's separate `ai/` area with its own README stating it is not evidence. Every surface shows
  "AI-generated, unverified - analyst must review".
- **Telemetry is killed, not trusted.** The Needle binary ships telemetry enabled; Vestigo forces
  `NEEDLE_TELEMETRY=0`, `DO_NOT_TRACK=1`, and `CACTUS_TELEMETRY=0` at import, before any provider
  can load the runtime, and a test asserts the invariant. Nothing reads `NEEDLE_API_KEY` and no
  fine-tuning entry point exists, so the vendor's upload-to-their-GPUs path is unreachable.
- **Default-off, dependency-free.** Three opt-in settings (`ai_enabled`, `transcription_enabled`,
  `semantic_search_enabled`) plus optional local model paths. Capabilities sit behind protocols with
  Needle-backed providers, a dependency-free deterministic embedder, and a disabled default that
  refuses with an actionable reason; a stock build installs nothing, downloads nothing, and the
  whole suite runs with fakes. Requesting AI while it is off returns 409 `AI_UNAVAILABLE` naming the
  reason.
- **Confidence only where the model gives it.** Needle returns its own `confidence`; it is recorded
  as the model's estimate and shown as such. Vestigo never calculates or infers one, and the UI says
  "no confidence given by the model" when there is none.
- **Drafts** propose named fields from held material (metadata, OCR text, analyst notes, a
  transcript), recording the evidence record read as lineage. The analyst accepts, edits, or rejects
  **each field**; an edit is stored beside the model's value, never over it, and nothing is ever
  written back onto metadata or evidence (a test pins the evidence report unchanged).
- **Transcripts** are machine-generated, unverified, and derived: timestamped segments with
  word-level timing where the model supplies it, the model's text kept verbatim beside any analyst
  correction, the original audio only ever read, and a video's audio track extracted with ffmpeg to
  a derived file so the lineage is explicit.
- **Semantic search** indexes only the analyst's own text (notes, record notes, OCR output,
  transcripts, selected metadata, their leads and candidates) with the producing model recorded per
  chunk, so indexes are never mixed. Answers always return their sources; a drafted answer appears
  only when a local generator exists, is labelled, is never stored, and never becomes evidence. When
  none exists, the material is returned with a notice saying why.
- **Custody, deletion, logs.** Generation, per-field decisions, transcript edits, indexing, and
  deletions write append-only custody events carrying ids, model names, and field names only - never
  content. All three tables are counted in the deletion summary and cascade with the artifact.
  Nothing AI-related is logged beyond the artifact id.
- **Known limitation, stated rather than hidden.** The published Python API exposes audio embeddings
  but no confirmed text-embedding call, so semantic search uses Vestigo's own deterministic
  embedder, which matches shared wording rather than meaning. Swapping in Needle text vectors is a
  change in one resolver, because every chunk records its model.

## D25 — Pass 2: deep media forensics

Implemented 2026-11-09 (plan `17-CONSOLIDATED-CAPABILITY-ROADMAP.md`). Four capabilities, all local,
all reporting observable facts and measurements rather than conclusions. No new runtime dependency
was added: everything is pure Python plus the ExifTool, ffprobe, and Pillow the project already has.

- **Structural and hidden-data inspection** (`structural`, optional, default on, images/video/audio/
  documents). Reports where a format's data logically ends and exactly how many bytes follow,
  container inventories (PNG chunks with CRCs verified, JPEG segments, MP4/MOV boxes, RIFF chunks),
  truncated chunks, impossible box sizes, declared sizes past the end of the file, missing end
  markers, trailing padding runs, and known file signatures at non-zero offsets. Measurements:
  whole-file entropy, highest-entropy 4 KiB window, and for images the LSB ones-ratio and a
  chi-square statistic. **No thresholds and no verdicts**: it never reports "steganography detected"
  and never reports a file as clean, and the limitations say both. A signature hit is a byte pattern
  and a place to look, not a file. Nothing is extracted, carved, decoded, or password-attacked;
  binwalk is optional and used for signature scanning only, never with `-e`, because extraction
  writes attacker-controlled paths. A container Vestigo does not parse structurally is a scope note,
  not a partial result.
- **Forensic indicators** (`forensic_indicators`, DERIVED). Images: every JPEG quantisation table
  with the IJG quality its values imply, per-channel pixel statistics, and declared against decoded
  dimensions. Video: keyframe spacing and packet-size distributions from ffprobe. The limitations
  state that an implied quality describes the **last save only**, that these numbers move with any
  re-save or platform processing and stay unremarkable in heavily edited files, and that no
  threshold separating "edited" from "original" exists anywhere in Vestigo. **Error-level analysis
  is deliberately not implemented** and the method text says so: its output is routinely misread as
  proof of editing.
- **Document and PDF analysis** (`document.v1`, new `document` media type, PDF sniffed from
  `%PDF-`, own 100 MB limit). Parsed in pure Python with no PDF library and no renderer:
  `pdf_structure` (OBSERVED) reports version, object and page counts, `%%EOF`/`startxref` markers so
  incremental saves are visible, declared encryption and linearisation, signature-dictionary count,
  and presence counts for JavaScript, automatic actions, embedded files, forms, object streams, and
  URI actions — with the limitations stating that none of these is wrongdoing, that repeated saves
  are ordinary annotation rather than tampering, and that **Vestigo never validates a PDF signature,
  checks a certificate, or reports a document as signed and valid**. `pdf_text` (DERIVED) extracts
  provisional text from Tj/TJ operators via zlib, labelled under the OCR honesty rule (D14): no font
  mapping, so characters can be wrong or missing, operator order is not reading order, and an empty
  result does not mean the page is blank. `pdf_images` copies JPEG-compressed embedded images out
  **byte for byte** as derived files (a test pins them identical to the embedded original); other
  encodings are counted but not extracted, because rebuilding them would mean re-encoding and a
  re-encoded image is not the stored evidence. These are embedded images, never rendered pages.
  Document duplicates are byte-identical only. Nothing in a PDF is rendered, executed, or decrypted,
  and no password is attacked.
- **Audio analysis** is complete without new stages: media info already reports duration, codec,
  channels, and sample rate from headers; metadata covers ID3 and container tags; the new
  `structural` stage covers embedded artifacts and structural indicators; and transcription comes
  from Pass 1 (D24). No authenticity verdicts anywhere.

No migration was needed: `media_type` is an unconstrained column, and every new section is an
evidence record with its raw output kept as a derived file, so export, custody, and deletion cover
them with no new wiring.

## D26 — Pass 3: GEOINT tooling and integration hardening

Implemented 2026-11-09 (plan `17-CONSOLIDATED-CAPABILITY-ROADMAP.md`). Completes the three-pass
programme. No new runtime dependency; Alembic 0009 (schema_version 9) is additive.

- **Local geospatial tooling** (`GET /geo/artifacts/{id}/tools`). Gathers every coordinate Vestigo
  already holds - machine-read location clues (D23) and the analyst's own candidates - and reports
  each in decimal, DMS, DDM, and ISO 6709, plus the great-circle distance and initial bearing
  between every pair. Calculation only: no geocoding, no place names, no map tiles, no network. A
  coordinate the location stage flagged as out of range stays in the evidence exactly as written but
  is never used for geometry, and a candidate without coordinates is skipped. Offline map data is
  reported only when the analyst has configured a path to their own
  (`VESTIGO_OFFLINE_MAP_PATH`); Vestigo never downloads any. The limitations state that a
  reformatted coordinate is the same coordinate, that distances are spherical geometry rather than
  travelled distance, that proximity confirms nothing, and that **Vestigo never decides a location**.
- **Cases** (`cases`, `case_artifacts`). A case is a name, notes, and a set of artifacts:
  organisation, not evidence. It carries no classification and asserts nothing about its members - a
  test pins every evidence section byte-identical after linking. Linking and unlinking write
  `case_linked` / `case_unlinked` custody events on the artifact, so its own trail shows which cases
  it was put in; re-linking an existing member records nothing. **Deleting a case removes only the
  case and its links**, never an artifact or its evidence; deleting an artifact removes only its
  links and leaves the case and its other members intact. The evidence report gains an
  artifact-level `cases` list and `DeletionSummary` gains `case_links`.
- **The integration surface** (`/integration`). `GET /integration/version` is always readable, so an
  integrator can discover the contract and that it is disabled; it reports the integration version
  (1.0), the report schema version, the app version, the schema revision, and every endpoint
  offered. `GET /integration/artifacts/{id}/evidence` returns one versioned envelope: the evidence
  report exactly as Vestigo serves it, the chain of custody, and the artifact's cases.
- **"No direct database writes by external integrations" is enforced by construction**, not by a
  permission check that could be misconfigured: the integration surface has no write route at all,
  which a test confirms by finding every write verb refused by routing itself. It is off by default
  (`integration_api_enabled`), and evidence reads return 409 `INTEGRATION_DISABLED` with the reason
  until the analyst enables it. **Reading writes nothing** - no custody event is recorded for a read,
  because Vestigo records only actions that change what it holds.
- **Import** is deliberately not implemented. Vestigo has no endpoint by which an external system can
  put data in, and adding one would mean accepting evidence Vestigo did not observe - which the
  evidence model cannot honestly represent. Evidence leaves through the export package and the
  read-only integration view; it never arrives from outside.

## D27 - Local AI made live, and the three things that turned out not to exist (2026-11-09)

Pass 1 built the whole local AI surface and never ran it: `cactus-needle` was optional and absent, so
`NeedleExtractor.extract` and `NeedleTranscriber.transcribe` had never once been executed and their
call shapes were guesses from vendor prose. This pass installed the runtime, checked it, and wired
what is real. Three of those guesses were wrong in ways worth recording, because each had been
written up as if it worked.

**The call shapes were wrong.** `needle.extract(text, schema, weights=, generation=, strict=)` takes
an OpenAI-style tool schema and returns the plain arguments mapping; it does not take a list of field
names. `needle.transcribe` returns flat text plus a `words` list of `{start, end, probability}` and
has no `segments` key, so the old adapter would have produced a single segment stamped 0.0 and
silently discarded every word timing. Both adapters now match the installed package, and the model
path is finally passed through as `weights=` - before, it was computed for provenance and dropped, so
configuring a model changed what Vestigo *recorded* and not what it *loaded*.

**Generation 3 cannot run at all.** The engine binary and the weights are published separately, and
`Cactus-Compute/needle3` holds only weights, a checkpoint and a tokenizer: there is no engine wheel
or platform folder for any platform, and the version the package pins (3.3.3) 404s. Whistle loads
through that same generation 3 engine, so transcription is blocked by the same gap. Generation 2 has
a published engine and runs: 0.96 s for the first call, 0.67 s warm, 47 MB RSS on an i7 laptop CPU
with no GPU. So `DEFAULT_GENERATION = 2`, generation 3 stays wired and reports itself unavailable
with the real reason, and it will start working when the vendor publishes an engine. **A model being
installed and a model being runnable are reported separately** (`installed` and `runnable` on
`/ai/status`), because the common case here is weights present and engine absent, and calling that
either "installed" or "missing" would be a lie in one direction or the other.

**There is no text generation and no text embedding.** `Needle.complete()` with no tools returns an
empty call, so Vestigo drafts no prose answers: `semantic.answer` now returns the analyst's own
material and says that is what it did, and the unreachable drafting branch and its `ANSWER_LABEL`
are deleted rather than left as code that cannot run. `Needle.embed(text)` exists but raises
"embeddings require a Needle 3 model", so `LocalHashEmbedder` stays - now for a verified reason
rather than an assumption, with the reason in the resolver's docstring.

**Downloads are blocked rather than avoided.** `needle/__init__.py` fetches a missing engine or
missing weights from Hugging Face at load time, and pings the Hub even on a warm cache ("a warm cache
still counts as a use of the model"). D24's claim that the backend makes no outbound request was
therefore a hope about cache state. `HF_HUB_OFFLINE=1` is now forced at import beside the telemetry
switches, `/ai/status` reports `offline_enforced`, and the behaviour is measured: a cold lookup fails
locally in 0.14 s with no network call while a staged model still runs. The telemetry set was also
corrected - `CACTUS_TELEMETRY` is read by no version of this package, so setting it was theatre;
`NEEDLE_TELEMETRY=0` and `DO_NOT_TRACK=1` are the switches that exist.

**Model files are managed, not typed from memory.** `data/models/` is created by `Storage` and
deliberately excluded from the tmp/trash wipe, so a restart cannot eat the weights. `GET /ai/models`
scans it, `POST /ai/models/import` copies a file the analyst already has, and `DELETE` removes one -
refused while a setting still points at it. A directory scan is the contract, so dropping a `.cact`
file in by hand works identically; the endpoint is a convenience, not a gate. Names are validated
rather than normalised: a filename with a directory part is refused instead of quietly renamed, which
follows the same rule as coordinates in D26. Settings keeps both fields and gains a picker, and a
configured path that does not resolve now reports the feature **unavailable with the bad path
echoed**, where before a typo read as "available" and failed on first use.

**Two fixed defects found on the way.** Transcription resolved its provider early but refused late,
after `_prepare_audio` had already run ffmpeg, written a WAV and committed a `DerivedFile` row - so a
turned-off feature left derived evidence and a custody event behind for work that never happened. It
now refuses first. And `/ai/status` and `semantic.py` were reading a private `_reason` attribute off
providers; `unavailable_reason` is now part of the provider protocol.

**Tests now cover the adapters twice over.** `tests/unit/test_ai_providers.py` injects a stand-in
module under the runtime's import name, so the mapping and error handling run on every machine
whether or not the package is installed - code that previously had no coverage at all. A `live_model`
marker (`pytest -m live_model`, excluded from the default run beside `container`) exercises the real
library against real weights, which is where an upstream change in those call shapes will surface.
The claim in the old docs that such tests existed was untrue when written; it is true now.
