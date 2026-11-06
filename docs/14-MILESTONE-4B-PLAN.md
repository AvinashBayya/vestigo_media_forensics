# Milestone 4 (part 2) Build Plan — Chain of Custody and Derived-File Relationships (DRAFT)

**Status: draft — awaiting approval. Nothing below is implemented.**

The C2PA validation and provenance half of Milestone 4 is complete (D20). This plan covers the
remaining roadmap scope: the **chain-of-custody view** and **derived-file relationship tracking**,
on the evidence-first architecture of Milestones 1–3 and D19/D20.

## 0. Proposed decisions

| # | Decision |
|---|---|
| M4B-1 | **Honest definition.** The chain of custody is *what Vestigo recorded on this machine since upload*: upload, analyses, derived files, review changes, exports, preview creation, and duplicate-library changes. It is **not** a legal or forensic chain of custody, it says nothing about the file's history before upload, and it never infers events that were not recorded. |
| M4B-2 | **No invented history.** Actions taken before this feature exists were only partially recorded (upload time, jobs, review events, preview creation have timestamps; exports and duplicate-library toggles left no trace). The timeline shows exactly what each existing table recorded, and the view states that export and library-change recording began with this schema revision. Nothing is backfilled. |
| M4B-3 | **New append-only `custody_events` table** (Alembic 0005, additive) records only the actions that currently leave no trace: evidence-package export (package SHA-256, whether the original was included), duplicate-library include/exclude (before → after), and playable-preview creation or replacement. Upload, analysis jobs, evidence records, and review events stay in their existing tables — the timeline merges all sources at read time, with no duplication. Like `review_events`, the database rejects updates and deletes except the cascade when the artifact is deleted. |
| M4B-4 | **Derived-file lineage.** Two new nullable columns on `derived_files`: `source_kind` (`"original"` or `"derived_file"`) and `source_derived_file_id` (FK to `derived_files.id`). Every new write records its true immediate source — e.g. a keyframe OCR TSV points at the keyframe thumbnail it read; `manifest_store.json` and ExifTool output point at the original. Rows written before 0005 keep NULL, reported as "source not recorded (pre-M4B)", never guessed. |
| M4B-5 | **API.** `GET /artifacts/{id}/custody` returns the merged chronological timeline: typed entries (`uploaded`, `analysis_started`, `analysis_finished`, `derived_file_created`, `review_changed`, `exported`, `library_changed`, `preview_created`), each carrying only recorded facts and naming the table it came from. Derived-file entries in the evidence report gain the two source fields. The evidence package gains `custody.json` (the same timeline, hashed in the manifest like every other file). |
| M4B-6 | **UI.** A "Chain of custody" panel on the artifact page: the timeline oldest-first with type badges and timestamps, plus a derived-file lineage view (original → stage outputs → downstream files, with kind, stage, and SHA-256; pre-M4B rows marked "source not recorded"). Minimal per D4 — no new page, no graphs beyond an indented tree. |
| M4B-7 | **Compatibility.** Alembic 0005 is additive only; v1–v4 databases upgrade in place without data loss; existing API shapes grow optional fields only; evidence records are never rewritten. |

Standing rules (unchanged from previous milestones): no authenticity/manipulation/deepfake verdicts,
no new external services, originals read-only, every evidence output honest about its limits,
background jobs for slow work, small descriptive commits, full backend/migration/API/container/
frontend/lint/type-check/build checks before each major step is committed.

## 1. Scope

| In | Out |
|---|---|
| `custody_events` table + Alembic 0005 (M4B-3) | Reverse-image search (M5), GEOINT (M6), Vestigo integration (M7) |
| Event recording at the export, duplicate-library, and preview code paths | Logging reads/views (only state-changing actions are custody events) |
| Derived-file `source_kind` / `source_derived_file_id` on every new write (M4B-4) | Backfilling lineage for existing rows (M4B-2) |
| `GET /artifacts/{id}/custody`; `custody.json` in the export package (M4B-5) | Any change to existing evidence payloads |
| Chain-of-custody panel + derived-file lineage tree in the UI (M4B-6) | Multi-user attribution (single-analyst tool; events carry no user identity) |
| Tests for every new behaviour; docs + D21 decision record | Automatic deletion, cloud storage |

## 2. Schema — Alembic 0005 (additive)

- `custody_events`: `id`, `artifact_id` (FK, cascade), `event_type` (`exported` / `library_changed`
  / `preview_created`), `detail` (JSON: package sha256 + `original_included` for exports;
  `included` before/after for library changes; preview sha256/dimensions for previews),
  `created_at`. Append-only triggers copied from `review_events`. Index `(artifact_id, created_at)`.
- `derived_files`: add nullable `source_kind` (String 16) and `source_derived_file_id`
  (FK `derived_files.id`, `ondelete="SET NULL"` is wrong here — same-artifact cascade makes it moot;
  plain FK, rows die with the artifact together).
- Upgrade tests: v1→v5 … v4→v5 in place with every row unchanged; new columns NULL on old rows.

## 3. Recording points (backend)

- `exports.py`: after a package streams successfully, insert an `exported` event (package SHA-256,
  `original_included`). A failed export records nothing (nothing left the machine).
- Duplicate-library PATCH: insert `library_changed` with before/after; a no-op change records nothing.
- `previews.py`: insert `preview_created` on create and on replacement.
- `DerivedFiles.write(...)` and `stored_file` consumers: the pipeline context passes the source —
  default `"original"`; the keyframe-OCR stage passes each thumbnail's derived-file id. The stage
  contract (method/tool/limitations) is unchanged.

## 4. API and export

- `GET /artifacts/{id}/custody` → `{ artifact_id, notice, events: [...] }`, oldest first, each event
  `{type, at, source_table, detail}`. The `notice` carries M4B-1's honesty wording and the M4B-2
  recording-start caveat.
- Evidence report: `derived_files` entries gain `source_kind` and `source_derived_file_id`
  (null = not recorded).
- Export package: `custody.json` added and listed in the manifest and `SHA256SUMS`; README.txt
  mentions it. Exporting therefore records an event that the *next* export will include — stated in
  the docs, not hidden.

## 5. Frontend

- `ChainOfCustodyPanel` on the artifact page (all media types): timeline with type badges,
  timestamps, and per-event detail; the honesty notice at the top; loading/empty/error states.
- Derived-file lineage tree inside the panel (or the existing provenance detail): original (name,
  SHA-256) → derived files grouped by job and stage, children indented under their source; pre-M4B
  rows labelled "source not recorded".
- No settings or options change; the view is always available.

## 6. Tests

Backend: append-only enforcement; every recording point (export success vs failure, library toggle
vs no-op, preview create/replace); lineage recorded for keyframe-OCR TSVs (points at the thumbnail)
and for original-sourced files; old rows stay NULL through migration; timeline merge order and
shapes; custody.json in the package with verified hash; deletion removes custody events; API 404s.
Migration: v1–v4 → v5 without data loss.
Frontend: timeline rendering of each event type, honesty notice, lineage tree with a pre-M4B row,
empty/error states.

## 7. Docs and commits

Docs: D21 decision record; roadmap items marked; API spec, evidence model (§12), security/privacy
(deletion list + logging), test plan, README (scope + manual test steps). Suggested commits:
(1) Alembic 0005 + models, (2) recording points + lineage, (3) custody API + export, (4) UI panel,
(5) docs/closure.

## 8. Open questions for approval

1. Should the timeline also list every evidence record creation (it duplicates "analysis finished"
   detail), or keep per-stage detail behind the existing evidence view? **Default: jobs only, stages
   stay in the evidence report.**
2. Is the lineage tree wanted inside the Chain-of-custody panel (default) or as its own panel?
