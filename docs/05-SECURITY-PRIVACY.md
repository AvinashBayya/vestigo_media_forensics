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
- Never execute uploaded media

## 3. Allowed Milestone 1 inputs

- JPEG
- PNG
- WebP
- TIFF

Video, audio, documents, and archives are out of scope for Milestone 1.

## 4. External-service policy

External services are optional and must be:

- Explicitly enabled by the user
- Permission-gated
- Licence-aware
- Terms-aware
- Clearly labeled in the UI
- Recorded as `EXTERNAL` evidence
- Disabled by default if legal or terms review is pending

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
- Database rows

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