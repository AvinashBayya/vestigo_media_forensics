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

## D13 — OCR preprocessing: two Tesseract passes, conservative selection

OCR stays Tesseract, English only, local. Preprocessing uses Pillow only (no OpenCV, no new
dependencies) and works on copies; the original upload is never modified, and the prepared images
are stored only as derived files.

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
