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
- Database rows

The deletion action must be explicit and confirmed in the UI.