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

Pass 1 (D24) adds local AI on strict terms: inference runs on this machine, every capability is off
by default, and the third-party runtime's telemetry is forced off in-process
(`NEEDLE_TELEMETRY=0`, `DO_NOT_TRACK=1`, `CACTUS_TELEMETRY=0`) before it can load, asserted by a
test. No media, prompt, embedding, question, or answer is ever transmitted; the backend makes no
outbound request; `NEEDLE_API_KEY` is never read and no fine-tuning entry point exists, so the
vendor's platform fine-tuning (which uploads files to its GPUs) is unreachable. Model weights are
supplied by the analyst as local files; nothing downloads at import.

Milestone 6 (D23) adds one deliberate carve-out to the "nothing evidence-derived" sentence above,
which was written for M5's static provider landing pages: an **opt-in** OpenStreetMap link for
coordinates already on screen. It is off by default, built entirely in the analyst's browser (the
backend never constructs, stores, transmits, or logs a coordinate-bearing URL), opens only on an
explicit click, and carries its own warning that clicking sends those coordinates to
openstreetmap.org. Vestigo loads no map tiles and embeds no map — tiles would transmit coordinates
on every page view, which the covert-tracking prohibition in §5 forbids. Reverse geocoding is not
enabled, and no map service requiring an API key may be added without separate approval.

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
- AI drafts, machine transcripts, and embedding indexes (Pass 1)
- Custody events (append-only until the artifact itself is deleted)
- External leads (M5)
- Location candidates (M6)
- Database rows

Playable previews are kept only as long as their artifact and are removed with it; nothing is
deleted automatically.

## 7. Logging

Logs must not contain:

- Full image contents
- AI prompts, model output, draft field values, transcript text, and embedding vectors (Pass 1)
- Sensitive EXIF data, including GPS coordinates — and, since M6, analyst-entered coordinates,
  location descriptions, and the basis text of location candidates
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