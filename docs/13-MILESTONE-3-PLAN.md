# Milestone 3 Build Plan — Video Foundation (approved)

Approved: 2026-11-04. This is the implementation plan for Milestone 3 (`06-ROADMAP.md`): responsible
local video analysis on the evidence-first architecture built in Milestones 1–2. The ffmpeg and
ffprobe command designs below were verified against the installed FFmpeg 7.1.5 before approval, as
were the duplicate-detection measurements.

## 0. Approved decisions

| # | Decision |
|---|---|
| M3-1 | **Containers**: MP4, MOV, WebM, MKV, detected from the file's bytes (`ftyp` box; EBML header). No AVI or 3GP. |
| M3-2 | **Limits**, all environment-overridable and read-only in the Settings UI: 500 MB upload, 900 s duration, 8,294,400 pixels (4K) per frame, 40 keyframes, scene threshold 0.3, 600 s per ffmpeg run. |
| M3-3 | **Keyframe OCR is off by default.** The analyst enables it per analysis. When enabled it runs on at most 10 selected keyframes, using the existing D13 two-pass OCR unchanged, with its provisional labelling, raw output, preprocessing details, confidence, limitations, and errors. No OCR tuning in this milestone (D14 stands). |
| M3-4 | **Cross-media duplicate search.** Video analyses search image fingerprints and other videos' keyframe fingerprints; image analyses also search video keyframe fingerprints. The image duplicates stage's method and limitations texts change for new evidence records only; existing evidence records are never rewritten. |
| M3-5 | **ExifTool metadata stage is included for videos** (QuickTime/Matroska creation time, device tags, GPS where present), stating that metadata is as written in the container and may be edited or absent. |
| M3-6 | **No transcoding.** Browser-playable videos preview through the existing content endpoint with HTTP Range; others show a clear fallback message. |
| M3-7 | **Audio**: ffprobe stream metadata only. No audio decoding, transcription, speaker identification, or voice analysis. |
| M3-8 | **Duration** is stored and displayed as the container-reported value and labelled in evidence as container-reported metadata, not a decode-verified measurement. |

Standing rules for M3:

- Implement Milestone 3 only. No facial recognition, speaker identification, audio transcription,
  deepfake detection, manipulation verdicts, authenticity claims, reverse-image search, GEOINT,
  Vestigo integration, multi-user login, cloud storage, or automatic deletion. No ELA, no video
  transcoding, no C2PA validation.
- ffprobe for media information; ffmpeg for scene detection and keyframe extraction. Subprocesses
  use argument lists with timeouts and never execute uploads.
- The original video is preserved read-only; derived files are stored separately and included in
  deletion and export.
- Analysis runs as background jobs with visible per-stage progress.
- Every evidence result includes method, tool, tool version, timestamps, source, limitations,
  errors, and review state. No verdicts or confidence scores.
- Schema changes go through Alembic revision 0003; upgrades from schema v1 and v2 to v3 are tested
  without data loss.
- Backend, migration, API, container, frontend, lint, type-check, and production-build checks run
  before each major step is committed. Small, descriptive commits.

## 1. Scope

| In | Out |
|---|---|
| Video upload (M3-1) with validation and limits (M3-2) | Everything in the standing rules above |
| `video.v1` pipeline: hashes, ffprobe media info, ExifTool metadata, scene detection, keyframe extraction, keyframe pHash, optional keyframe OCR, duplicate search | C2PA on video (M4), ELA, transcoding |
| Keyframe fingerprint index; duplicates across videos and images (M3-4) | Audio analysis beyond stream metadata (M3-7) |
| Video evidence report sections; minimal video UI | OCR tuning (D14) |
| Alembic 0003; tests for every new behaviour | |

## 2. Upload and validation

`POST /artifacts/upload` is unchanged in shape; type comes from bytes only:

1. Stream to `tmp/` while hashing; the upload middleware and stream cap use the video limit, and the
   image limit is still enforced once the file sniffs as an image.
2. Sniff: `ftyp` at offset 4 → MP4/MOV family; EBML `1A 45 DF A3` → WebM/MKV; existing image
   signatures unchanged; anything else → 415 `UNSUPPORTED_MEDIA_TYPE`.
3. Validate with ffprobe (JSON, tool timeout): must parse, contain at least one video stream, and be
   within the duration and per-frame pixel limits. A truncated MP4 fails ffprobe cleanly (verified).
4. Store read-only under `original/`.

New environment settings: `VESTIGO_MAX_VIDEO_UPLOAD_BYTES` (500 MB), `VESTIGO_MAX_VIDEO_DURATION_SECONDS`
(900), `VESTIGO_MAX_VIDEO_PIXELS` (8,294,400), `VESTIGO_MAX_KEYFRAMES` (40), `VESTIGO_SCENE_THRESHOLD`
(0.3), `VESTIGO_VIDEO_TIMEOUT_SECONDS` (600).

New error codes: `INVALID_VIDEO`, `VIDEO_TOO_LONG`, `VIDEO_RESOLUTION_TOO_LARGE`, `WRONG_MEDIA_TYPE`.

## 3. Storage layout

```
artifacts/{id}/original/{id}.mp4                       read-only, preserved
artifacts/{id}/derived/{job_id}/
  media_info.ffprobe.json                              raw ffprobe output
  scene_changes.ffmpeg.txt                             raw filter output
  keyframes.0001_t0.000.jpg …                          longest side ≤ 1920 px, JPEG q=2
  keyframe_ocr.0001.grayscale.tsv …                    OCR raw output per analysed frame
```

Bounded by the keyframe cap (≈ ≤ 25 MB of derived files per analysis). Deletion, trash/restore,
export, and the storage summary cover these without structural change.

## 4. API changes (additive)

| Endpoint | Change |
|---|---|
| `POST /artifacts/upload` | Accepts the four video containers; `media_type: "video"`. |
| `POST /analysis/video` (new) | `{artifact_id, options?}`; options `metadata`, `scene_detection`, `keyframe_ocr` (default **false**, M3-3), `duplicate_search`. Hashes, media info, keyframes, and keyframe pHash always run. Omitted `options` use the saved video defaults from Settings. Wrong media type → 422 `WRONG_MEDIA_TYPE`, likewise for `POST /analysis/image` on a video. |
| `GET /artifacts/{id}/derived/{derived_file_id}/content` (new) | Serves a derived file belonging to that artifact (keyframe thumbnails), with the same protective headers as `/content`. |
| `GET /artifacts`, `GET /artifacts/{id}` | Summaries add nullable `duration_seconds`; the `mime_type` filter accepts video MIME types. |
| Evidence report | `schema_version` `"1.2"`: nullable `media_info`, `scene_changes`, `keyframes`, `keyframe_ocr` sections. The video duplicate stage is also named `duplicates` with a top-level `matches` array, so Library indicators work unchanged; `DuplicateMatch` gains optional `matched_frame_count` and `frame_matches`. |
| M2 features | Review, history, export, deletion, duplicate-library include/exclude, settings — unchanged; they cover video artifacts and the new stages automatically. |

## 5. Database changes

Alembic `0003_m3_video_foundation` (`schema_version` 3), additive only:

- `artifacts`: add `duration_seconds REAL NULL` (container-reported, M3-8).
- New `keyframe_fingerprints`: PK `(artifact_id, algorithm, frame_seq)`; `timestamp_seconds`,
  `value_hex`, `evidence_id` (FK cascade), `derived_file_id` (FK cascade), `created_at`. Holds the
  latest successful analysis's hashes; replaced on re-analysis; deleted with the artifact.
- Upgrades from v1 and v2 are tested in place with all rows intact.

## 6. Pipeline `video.v1`

| # | Stage | Option | Tool | Class | Output |
|---|---|---|---|---|---|
| 1 | `hashes` | always | hashlib | DERIVED | Existing stage, media type parameterised |
| 2 | `media_info` | always | ffprobe | OBSERVED | Container, container-reported duration, video streams (codec, profile, dimensions, frame rate, bit rate), audio streams (codec, channels, sample rate) — metadata inspection only (M3-7). Limitations: values are as written and editable; duration is not decode-verified |
| 3 | `metadata` | `metadata` | ExifTool | OBSERVED | Existing stage reused (M3-5) |
| 4 | `scene_changes` | `scene_detection` | ffmpeg | DERIVED | `[{time, score}]` + threshold. Limitations: content-difference metric; gradual transitions may be missed; a cut is not evidence of manipulation |
| 5 | `keyframes` | always (uses 4 when present) | ffmpeg | DERIVED | Frames per §8 with timestamp and selection reason; display-matrix autorotation applies |
| 6 | `keyframe_phash` | always (needs 5) | imagehash | DERIVED | pHash per keyframe; updates the keyframe fingerprint index |
| 7 | `keyframe_ocr` | `keyframe_ocr` (default off) | Tesseract | DERIVED | D13 OCR on ≤ 10 evenly spaced selected keyframes (M3-3) |
| 8 | `duplicates` | `duplicate_search` (needs 6) | Vestigo | DERIVED | Keyframe hashes vs image fingerprints and other videos' keyframes at the existing threshold 10; per-artifact grouping with frame pairs; SHA-256 exact match; exclusions honoured (M3-4) |

The image pipeline's `duplicates` stage also searches the keyframe index (M3-4); its method and
limitations texts change for new records only.

## 7. Verified command designs (FFmpeg 7.1.5)

| Purpose | Command | Verified |
|---|---|---|
| Validation + media info | `ffprobe -v error -print_format json -show_format -show_streams FILE` | Full stream/format JSON; truncated file → exit 1 |
| Scene detection | `ffmpeg -v error -i FILE -vf "select='gt(scene,0.3)',metadata=print:file=OUT" -f null -` | Both cuts of a 3-scene fixture found (scores 0.58, 0.82) in 0.15 s; none in a static clip |
| Keyframe extraction | `ffmpeg -v error -ss T -i FILE -frames:v 1 -vf "scale='min(1920,iw)':-2" -q:v 2 OUT.jpg` | ~0.12 s/frame; autorotates display-matrix video |
| Rotation fixture | `ffmpeg -display_rotation 90 -i IN -c copy OUT` | Writes a real Display Matrix |

Measured duplicate behaviour: keyframes of a copy re-encoded to WebM at half resolution differ by
0–4 bits from the original's; frames of different scenes differ by ~28. The existing threshold of 10
needs no change.

## 8. Keyframe selection policy

1. Candidates: the first decodable frame (always) + one frame per scene change.
2. Fewer than 8 → add evenly spaced frames up to 8 (fewer for very short clips), skipping within
   0.25 s of an existing candidate.
3. More than the cap (40) → keep the first frame plus the highest-scoring scene changes.
4. Each frame records `{seq, timestamp, reason: first_frame | scene_change (score) | uniform_sample}`.
5. OCR (when enabled) uses an evenly spaced subset of ≤ 10 selected keyframes; pHash uses all.

## 9. UI changes

- Upload: video types accepted, per-type limits shown, video option list (OCR off by default),
  `/analysis/video` used.
- Artifact page (video): `<video controls preload="metadata">` via `/content` (Range supported) with
  a fallback message for unplayable codecs (M3-6); duration in the header; panels for media info,
  scene changes, keyframes (thumbnail grid with timestamps and reasons), keyframe OCR (provisional
  label), and frame-pair duplicate matches. Problems summary, history, per-record review, and export
  unchanged.
- Library: duration shown for videos; file-type filter gains video types.
- Settings: editable default video analysis options; video limits read-only in the environment
  section.

## 10. Test plan

Fixtures generated deterministically with ffmpeg `lavfi` (no committed binaries): 3-scene MP4 with
audio and drawn text; static MP4; half-resolution WebM re-encode (Opus audio — AAC cannot be carried
in WebM); MKV and MOV remuxes; `-display_rotation 90` video; video without audio; audio-only file
(rejected); truncated MP4; over-duration and over-resolution clips against lowered test limits; an
HTML file named `.mp4`.

- Upload/validation: each format and rejection, per-type size caps, read-only original.
- media_info values; scene detection exact on the fixtures; keyframe policy (first frame, fallback,
  cap, dedupe, reasons); pHash index written and replaced; OCR reads the drawn text when enabled and
  is skipped by default; duplicates: re-encoded copy matches (d ≤ 4), static does not, image↔video
  both directions, exclusions, SHA-256 exact; evidence completeness and verdict-wording guard over
  the new stages; `WRONG_MEDIA_TYPE`; derived-content endpoint scoping.
- Migration: v1→v3 and v2→v3 in place without data loss; models match head; fresh install.
- Deletion and export: keyframes, fingerprints, and video evidence removed with the artifact; the
  export package carries keyframes with verified hashes.
- Container: ffmpeg and ffprobe become required tools.
- Frontend: video upload, each new panel, preview fallback, duplicates with frame pairs, Library
  duration and filter, video defaults in Settings.
- Performance: the full pipeline on the 9 s fixture stays within ordinary test time.

## 11. Implementation order

1. This plan; decisions D17.
2. Alembic 0003 + models + migration tests.
3. Video validation and upload + tests.
4. `video.v1` skeleton: hashes + `media_info` + `POST /analysis/video` + report sections + fixtures + tests.
5. `scene_changes` + tests.
6. `keyframes` + derived-content endpoint + tests.
7. `keyframe_phash` + fingerprint index + tests.
8. `keyframe_ocr` + tests.
9. `duplicates` (video, and the image-side extension) + tests.
10. Frontend: upload, video panels, Library, Settings.
11. Docs (00/03/04/05/07/09/10, README), acceptance run, manual test instructions.
