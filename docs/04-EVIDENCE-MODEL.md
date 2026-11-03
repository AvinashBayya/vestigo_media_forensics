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
