# Evidence Model

## 1. Purpose

The evidence model ensures that every analysis result is traceable, explainable, and reviewable.

## 2. Core entities

### Artifact

A uploaded media file.

Fields:

- `artifact_id`
- `filename`
- `media_type`
- `size_bytes`
- `sha256`
- `md5`
- `stored_path`
- `created_at`
- `review_state`

### AnalysisJob

A run of one or more analysis stages against an artifact.

Fields:

- `job_id`
- `artifact_id`
- `pipeline`
- `status`
- `started_at`
- `completed_at`
- `error`

### EvidenceRecord

A single observable or derived finding.

Fields:

- `evidence_id`
- `artifact_id`
- `job_id`
- `stage`
- `classification`
- `payload`
- `tool`
- `tool_version`
- `started_at`
- `completed_at`
- `limitations`
- `review_state`

## 3. Evidence classifications

- `OBSERVED` — directly extracted from the file
- `DERIVED` — calculated by the system
- `EXTERNAL` — obtained from an outside service
- `UNVERIFIED` — not yet validated
- `REVIEWED` — approved by a human analyst

## 4. Review states

- `UNREVIEWED`
- `IN_REVIEW`
- `REVIEWED`
- `FLAGGED`
- `ARCHIVED`

### Review (Milestone 2)

- **Artifact review**: one review state and analyst notes for the whole artifact.
- **Record review**: each evidence record has its own review state, analyst notes, and
  `review_updated_at`. Reviewing a record never changes its classification, payload, or anything
  produced by analysis. Artifact and record review are separate.
- **Review events** (`review_events`): every change to a review state or notes, at either level or by
  bulk review, is recorded with its origin (`artifact`, `record`, `bulk`), the states before and after,
  and the complete note text before and after. Events are append-only: the database rejects updates
  and deletes, except when the artifact itself is deleted.

## 5. Required fields

Every evidence record must include:

- Method
- Tool
- Tool version
- Timestamp
- Limitations
- Source of the finding
- Review state

## 6. Anti-fabrication rules

- Do not invent metadata.
- Do not infer facts beyond the available evidence.
- Do not present low-confidence findings as conclusions.
- Do not label a file “authentic” or “fake.”
- Do not hide tool failures.
- Do not silently discard errors.
- Do not claim external-service results are verified without validation.

The implemented system keeps these specific honesty rules:

- Embedded and container metadata is reported **as written**, never as verified truth; it is easy to
  edit, and its absence proves nothing.
- Video and audio **durations are container-reported**, not decode-verified measurements.
- **OCR output is provisional** best-effort text (D14), never a verified transcription.
- **Playable previews are derived viewing copies**, clearly labelled, excluded from the evidence
  package, and never a substitute for the preserved original.
- **Duplicate matches are similarity leads**, not proof of common origin: they say two artifacts look
  alike (or are byte-identical), never which came first or that one was derived from the other.
- **A valid C2PA manifest is a verified signature, not verified truth** (M4, D20): it means the
  covered data has not changed since signing, never that the content is truthful, accurate, or
  unmanipulated, and without a trust list it never establishes who the signer is. Absence of C2PA
  data proves nothing — most media has none and many platforms strip it.
- No stage ever claims authenticity, manipulation, deepfake status, or location. Location
  metadata is reported as clues read from the file (M6, D23); **no stage ever claims a location
  is confirmed**, and any interpretation is an analyst statement, labelled as such.

## 7. Deletion rule

Deleting an artifact must delete:

- Original file
- Derived files
- Analysis jobs
- Evidence records
- Review events
- Database rows

The deletion action must be explicit and confirmed in the UI.

## 8. Evidence packages (Milestone 2)

An exported ZIP evidence package contains the evidence report, the review data and full review
history, the raw tool outputs of one analysis job, and (only on request) the original file. A manifest
lists the SHA-256 and size of every file, and the SHA-256 recorded when each derived file and the
original were stored. A recorded file that is missing or no longer matches is listed as a problem,
never silently left out.

## 9. Video evidence (Milestone 3)

- `media_info` is OBSERVED: container and stream headers reported as written; nothing is decoded,
  and audio is never transcribed or identified (M3-7). The stored `duration_seconds` is the
  container-reported value and is labelled as such, not a decode-verified measurement (M3-8).
- `scene_changes`, `keyframes`, `keyframe_phash`, `keyframe_ocr`, and `duplicates` are DERIVED.
  Keyframes record the selection policy and each frame's reason; extracted frames are re-encoded
  thumbnails stored as derived files, never the originals.
- Keyframe fingerprints (`keyframe_fingerprints`) index the latest successful analysis and are
  deleted with the artifact. Duplicate matches record frame pairs with both sides' timestamps.
- Scene changes are ordinary editing; no stage claims a video is authentic, manipulated, or
  deceptive.

## 10. Audio evidence and viewing previews (D19)

- Audio artifacts carry the same evidence contract through the shared hashes, media-info, and
  metadata stages. Audio duplicate search is byte-identical SHA-256 only, and its limitations state
  plainly that a re-encoded copy of the same recording will not match; no audio content is ever
  decoded or compared.
- Duplicate frame pairs record the orientation (rotation/mirroring) under which they matched.
- A playable preview is a re-encoded viewing copy, not evidence: it is excluded from the evidence
  package, labelled in the UI, and deleted with the artifact. The original is never modified.

## 11. C2PA provenance evidence (Milestone 4, D20)

- The `c2pa` stage runs for images, videos, and audio, and is OBSERVED: it reads and validates the
  file's manifest store locally with c2pa-python and records what the manifests and their
  certificates say, as written. The original file is never modified, and no network is used.
- Every record carries the four-way outcome (`valid` / `invalid` / `unverifiable` / `absent`), the
  SDK's own validation state and grouped validation codes, the exact validator version, and per
  manifest the claim generator, signer certificate details, assertion labels, and ingredient count.
- The validator's raw manifest-store report is a derived file (`manifest_store.json`): auditable,
  exported in the evidence package, and deleted with the artifact.
- Failure semantics: an invalid manifest is a finding (the stage succeeds and records why);
  C2PA data that is detected but unreadable makes the stage `partial` with
  `C2PA_VALIDATION_UNAVAILABLE` and the validator's error. Records made before M4 keep
  `validation_performed: false` and still render as detection-only.

## 12. Chain of custody (Milestone 4 part 2, D21)

- The chain of custody is **what Vestigo recorded on this machine since upload** — never a legal
  chain of custody, never anything about the file before upload, and never inferred or backfilled.
- `custody_events` (append-only, like review events) records only the actions no other table holds:
  evidence-package exports (package SHA-256, whether the original was included), duplicate-library
  changes (before/after; no-ops record nothing), and preview creation. Upload, jobs, evidence, and
  review changes stay in their own tables; `GET /artifacts/{id}/custody` merges all sources at read
  time, one entry per job rather than per stage, each entry naming its source table.
- Every derived file records its source: the original upload, or the exact derived file it was read
  from (a keyframe-OCR TSV points at its keyframe thumbnail). Rows from before revision 0005 have
  no recorded source and are reported as such, never guessed.
- The export package carries `custody.json`, hashed in the manifest like every other file. A
  package is built before its own export event is recorded, so each export appears in the *next*
  package's custody.json; the package README states this.
- Custody events carry no note text (review notes stay in the review history) and no user identity
  (single-analyst tool). Deletion removes them with the artifact and counts them.

## 13. External leads (Milestone 5, D22)

- A lead is an **analyst statement**, classified EXTERNAL: the provider, result URL, optional image
  URL, notes, and any publication date are recorded exactly as entered and never verified by
  Vestigo. `recorded_at` (set by Vestigo) and the analyst-reported publication date are separate
  facts, always labelled apart; an earlier-dated result is a lead about prior appearance, never
  "the original source".
- The lead names its subject: the original image, or the exact keyframe derived file that was
  searched. Audio has no searchable image; the playable preview is never a subject.
- Leads are editable (unlike machine evidence); every create, update, and delete is an append-only
  custody event, so the full history survives edits and deletions. Lead review is a lightweight
  per-lead state starting UNREVIEWED.
- Leads appear in the evidence report (artifact-level, newest first), travel in the export package,
  and are deleted and counted with the artifact.

## 14. Location clues and candidates (Milestone 6, D23)

Machine and analyst work are separate records with different classifications:

- **`location_clues` is OBSERVED**: coordinates, altitude, timestamps, device fields, place-name
  tags, and container location strings, each read **as written** and labelled with the tag it came
  from. Coordinates are additionally shown in decimal degrees for readability, with the original
  strings and hemisphere refs beside them. Sources that disagree are both shown as found; Vestigo
  never reconciles or prioritises them. Coordinate ranges are checked and an out-of-range or
  half-present value is flagged with its reason and kept exactly as written — never corrected,
  normalised, or discarded. Embedded location data is trivially edited and is never proof of where
  media was captured; its absence is normal and proves nothing.
- **Nothing is inferred from content**: no place names are extracted from OCR text and nothing is
  read from audio. The section records only whether the analysis produced OCR text, so the analyst
  reads the visible signs, addresses, and clocks themselves.
- **A location candidate is an analyst statement, classified UNVERIFIED**: the stated place, the
  required basis in the analyst's own words, their required assessment label (speculative /
  possible / likely — their judgment, never machine-derived, never displayed automatically, and
  with no "confirmed" value), any coordinates, and typed references to supporting evidence of the
  same artifact. EXTERNAL stays reserved for provider leads and externally sourced references.
  `recorded_at` is when Vestigo saved the candidate, nothing more.
- Candidates are editable; every create, update, and delete is an append-only custody event (with
  field names only — never coordinates), so the history survives edits and deletions. Review is the
  lightweight per-candidate state starting UNREVIEWED.
- Candidates appear in the evidence report (artifact-level, newest first), travel in the export
  package, and are deleted and counted with the artifact.

## 16. Structure, measurements, and documents (Pass 2, D25)

- **Structural findings are placed facts**: what was found, at which byte offset, and how large.
  Data after a format's end, extra chunks, and embedded signatures all have ordinary causes, and a
  signature match is a byte pattern rather than a file. Vestigo never reports that concealed data
  was found, and never reports that a file is clean - concealment can be undetectable by these
  checks, and the limitations say so.
- **Measurements are numbers with methods**: entropy, LSB balance, chi-square, quantisation tables,
  channel statistics, keyframe spacing. No threshold is applied to any of them, and an implied JPEG
  quality describes the last save only. Error-level analysis is deliberately absent because its
  output is routinely misread as proof of editing.
- **Document structure is what the file declares**, not what it does: page and object counts,
  repeated saves, encryption, and the presence of JavaScript, actions, embedded files, and forms -
  none of which is a finding of wrongdoing. **Signature presence is never signature validity**:
  Vestigo does not check certificates or signer trust.
- **Extracted document text is provisional**, under the same rule as OCR (D14): no font mapping, so
  characters can be wrong, and an empty result never means the page is blank.
- **Extracted embedded images are stored bytes, not renders.** JPEG streams are copied out byte for
  byte; other encodings are counted but not rebuilt, because a re-encoded image is not the stored
  evidence. Vestigo has no PDF renderer, so page appearance is never reproduced.
- Nothing is extracted from a file beyond those stored streams, nothing is carved, and no password
  or passphrase is ever attacked. Originals are only ever read.

## 15. AI output is not evidence (Pass 1, D24)

- **Separate by construction.** Model output lives in `ai_drafts`, `transcripts`, and
  `embedding_chunks`, never in `evidence_records`. It carries no classification, never appears in
  the evidence report, and travels in the export package's `ai/` area with its own README stating
  plainly that it is not evidence. Every surface shows "AI-generated, unverified - analyst must
  review".
- **Provenance is mandatory**: model name, version, quantization, source URL, licence, runtime, and
  the local file it was loaded from, plus timestamps, warnings, errors, and what held material the
  model read.
- **Confidence is the model's or nobody's.** A confidence figure is recorded only when the model
  supplies one, labelled as the model's own estimate. Vestigo never calculates, infers, or displays
  a confidence of its own.
- **The analyst owns every acceptance.** Fields are accepted, edited, or rejected one at a time; an
  edit is stored beside the model's value, never over it; and nothing is ever written back onto
  metadata, evidence, or any existing analyst record. Transcripts keep the model's text verbatim
  beside the analyst's correction, and the original audio is only ever read.
- **Retrieval shows its sources.** A generated answer never stands alone: the analyst's own records
  it drew on are always returned, the answer is labelled, and it is never stored or citable as a
  finding.
- **Custody and deletion**: generation, per-field decisions, edits, indexing, and deletions are
  append-only custody events carrying ids, model names, and field names only - never content. All
  three tables are counted in the deletion summary and cascade with the artifact.

