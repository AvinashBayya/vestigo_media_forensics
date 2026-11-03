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

- File without C2PA returns `present: false`
- File with C2PA returns detected status
- Invalid C2PA does not crash pipeline

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

## 5. Container tests

- Backend starts on port 8400
- Frontend starts on port 5180
- ExifTool is available
- Tesseract is available
- FFmpeg is available
- ffprobe is available
- SQLite database initializes correctly