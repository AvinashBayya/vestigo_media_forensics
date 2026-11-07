# Security and Privacy

## 1. Local-first rule

Media files, analysis results, and evidence records remain on the user’s machine by default.

No cloud upload is required for Milestone 1.

## 2. Upload safety

The backend must:

- Validate file type
- Enforce maximum upload size
- Generate safe storage names
- Prevent path traversal
- Store originals separately from derived files
- Reject unsupported or dangerous file types
- Enforce video duration, frame-size, and keyframe limits
- Never execute uploaded media (ffprobe and ffmpeg run with argument lists and timeouts)
- A playable preview re-encodes the stored original locally with ffmpeg, on demand only; the output
  stays on the user's machine and the original is never modified
- C2PA validation (Milestone 4) runs entirely locally with the c2pa-python library: no network
  access, no trust-list download, and the original is only ever read — C2PA data is never added,
  removed, or rewritten

## 3. Allowed inputs

Images (Milestone 1): JPEG, PNG, WebP, TIFF.
Videos (Milestone 3, extended by D19): MP4, MOV, WebM, MKV, AVI, MPEG-TS, WMV, FLV, 3GP, M4V —
validated with ffprobe after byte sniffing; a video stream with readable dimensions and a
container-reported duration within the limits is required.
Audio (D19): WAV, MP3, FLAC, OGG, M4A — validated with the same ffprobe pass; header-level
inspection only, never decoding, transcription, or speaker identification.

Documents and archives are not accepted.

## 4. External-service policy

External services are optional and must be:

- Explicitly enabled by the user
- Permission-gated
- Licence-aware
- Terms-aware
- Clearly labeled in the UI
- Recorded as `EXTERNAL` evidence
- Disabled by default if legal or terms review is pending

Milestone 5 (D22) implements this policy manual-first: every search provider is disabled until the
analyst enables it in Settings; Vestigo only opens the provider's plain landing page (no query
parameters, nothing evidence-derived) and never uploads media — the analyst does, knowingly, on the
provider's own site under its terms. The backend makes no outbound HTTP requests. Automated
scraping, CAPTCHA bypass, browser automation, rate-limit evasion, and automatic uploads are
prohibited; paid or official provider APIs each require separate approval.

## 5. Prohibited capabilities

The system must not include:

- Facial recognition
- Biometric identification
- Automated identity attribution
- Covert tracking
- Credential testing
- Exploitation
- Active scanning
- Evasion
- Proxy rotation for evading platform controls
- Automated deepfake verdicts

## 6. Data deletion

Users must be able to delete:

- An artifact
- Its original file
- Derived files
- Analysis jobs
- Evidence records
- Review events
- Fingerprint index rows (image and keyframe)
- Its playable preview, when one was created
- Custody events (append-only until the artifact itself is deleted)
- External leads (M5)
- Database rows

Playable previews are kept only as long as their artifact and are removed with it; nothing is
deleted automatically.

## 7. Logging

Logs must not contain:

- Full image contents
- Sensitive EXIF data
- API keys
- User credentials
- Library search terms (query strings are redacted from access logs)
- Analyst notes
- Setting values

Logs may contain:

- Artifact ID
- Job ID
- Stage name
- Status
- Error type
- Timestamps