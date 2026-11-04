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
