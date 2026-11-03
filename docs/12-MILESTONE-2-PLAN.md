# Milestone 2 Build Plan — Analyst Workflow (approved)

Approved: 2026-11-03. This is the implementation plan for Milestone 2 (`06-ROADMAP.md`): make evidence
easier to review and manage. Milestone 1 (`11-BUILD-PLAN.md`) is complete. OCR is best-effort provisional
evidence (D14) and is not tuned further in M2.

## 0. Approved decisions

| # | Decision |
|---|---|
| M2-1 | **Migrations use Alembic.** A baseline revision reproduces the Milestone 1 schema exactly; a second revision adds the M2 schema. An existing M1 database (`schema_version` 1, no Alembic table) is upgraded in place without data loss. The application refuses to start if the database revision is newer than it supports. |
| M2-2 | **Per-evidence-record review.** Analysts can set a review state and notes on individual evidence records. Review never changes an evidence record's classification. Artifact-level review stays separate from record-level review. This completes D-7. |
| M2-3 | **Review history keeps full text.** Every review change writes an append-only review event with the complete note text. Events are deleted only when their artifact is deleted. |
| M2-4 | **Archived artifacts are hidden from the Library by default**, behind a "Show archived" filter. |
| M2-5 | **Bulk review** of up to 200 artifacts per request, all-or-nothing on the backend, with explicit confirmation and a clear success or failure result in the UI. |
| M2-6 | **ZIP evidence package**: `report.json`, review data, derived tool outputs, `manifest.json` (SHA-256 and size of every file), the evidence notice, and verification instructions. The original file is included only when the user explicitly selects it (default: not included). Response header `X-Vestigo-Export-SHA256`. No HTML summary and no PDF in M2. |
| M2-7 | **Duplicate-library management**: index status, include/exclude an artifact from *future* duplicate searches, and an "artifacts added since this analysis" re-run hint. Excluded artifacts are skipped by future searches. Existing evidence is never rewritten. A live "duplicate groups" view is deferred. |
| M2-8 | **Settings**: editable defaults for analysis options, Library page size, and automatic analysis after upload, stored in SQLite. The duplicate threshold and all environment settings are read-only in the UI. Search terms, analyst notes, and setting values are never logged. |
| M2-9 | **The Library is the home page (`/`).** Upload moves to `/upload` and stays a prominent primary action in the header and on the Library page. |
| M2-10 | No OCR-text search in M2. |
| M2-11 | No thumbnails in M2. |

Standing rules for M2:

- Implement Milestone 2 only. No video analysis, reverse-image search, GEOINT, facial recognition, ELA,
  deepfake detection, Vestigo integration, multi-user login, cloud storage, or automatic deletion or
  retention.
- No verdicts, authenticity labels, or confidence scores.
- Keep the evidence-first architecture. Every evidence result keeps its method, tool, version,
  timestamps, source, limitations, errors, and review state.
- API changes are additive. Existing fields and endpoints keep their meaning.
- Tests for every new backend and frontend behaviour; the full suite passes before each major step is
  committed.

## 1. Scope

| Area | Delivered |
|---|---|
| Artifact list | Library page: paged table of all artifacts with status indicators. |
| Search and filtering | Search filename, artifact ID, SHA-256/MD5 prefix, and analyst notes. Filter by review state, analysis status, has problems, has duplicate matches, file type, upload date range, and "Show archived". |
| Sorting | Upload date, filename (case-insensitive), size, review state; ascending or descending, with a stable tiebreaker. |
| Status indicators | Analysis status, review state, problem count (failed or partial checks in the latest job), duplicate-match count, artifacts added since the analysis, duplicate-library inclusion. |
| Review workflow | Artifact-level review with conflict detection and history; bulk review; per-evidence-record review. |
| Analyst notes | Per artifact and per evidence record; unsaved-changes warning; full history in review events. |
| Evidence export | JSON report with review data; ZIP evidence package; export of any past job. |
| Duplicate library | Index status (indexed, not analysed, excluded); include/exclude; re-run hint. |
| Error surfacing | Problems summary per artifact, tool-health banner, failed-job reasons, error codes shown alongside messages, retry. |
| Basic local settings | Editable defaults (SQLite), read-only environment and tool versions, storage usage. |
| Empty and loading states | Empty library, no results, not analysed, loading, error with retry. |

Out of scope: everything in the standing rules, and M4 work (C2PA validation, chain-of-custody view,
derived-file relationship tracking).

## 2. Pages and user flows

Header navigation: **Library** (`/`) · **Upload** (`/upload`, primary button) · **Settings**
(`/settings`), plus a tool-health indicator.

| Route | Page |
|---|---|
| `/` | Library: search, filters, sort, table, bulk review, pagination, Upload button. |
| `/upload` | Upload (the M1 upload page). Analysis options default from settings; analysis starts automatically when the "automatic analysis after upload" setting is on. |
| `/artifacts/:id` | Artifact: problems summary, analysis history, evidence sections with per-record review, artifact review with history, export menu, duplicate-library control. |
| `/settings` | Editable defaults, environment (read-only), tools, storage usage, duplicate-library overview. |

Flows:

1. **Triage**: Library → filter "Unreviewed" + "Has problems" → open an artifact → problems summary →
   review sections → set artifact state → back to the list. Filter state lives in the URL.
2. **Find**: search a SHA-256 prefix or part of a filename → open the result.
3. **Bulk**: select rows → "Set review state…" → confirmation naming the count → success or failure
   message.
4. **Record review**: in an evidence section's footer, set that record's state and note.
5. **Export**: export menu → JSON report, or evidence package (ZIP) with an unchecked "Include original
   file" option → any past job.
6. **Duplicates**: the duplicates panel shows "N artifacts added since this analysis — run analysis
   again". Settings lists artifacts without a pHash and excluded artifacts, with actions.
7. **Failure**: a missing tool shows a header banner; the problems summary links to the failed section,
   which shows its error inline.

## 3. API changes (additive, under `/api/v1`)

| Endpoint | Change |
|---|---|
| `GET /artifacts` | Query: `q`, `review_state` (repeatable), `analysis_status` (repeatable; includes `not_analysed`), `has_problems`, `has_duplicates`, `mime_type`, `uploaded_from`, `uploaded_to`, `include_archived` (default true, which keeps the M1 behaviour of listing every artifact; the Library sends false, so archived artifacts are hidden there by default), `sort` (`created_at` · `filename` · `size_bytes` · `review_state`), `order` (`asc` · `desc`), `limit`, `offset`. Items add `latest_job`, `problem_count`, `duplicate_match_count`, `added_since_analysis`, `in_duplicate_library`. Response adds `counts_by_review_state`. Invalid parameters → 422 `VALIDATION_ERROR`. |
| `PATCH /artifacts/{id}/review` | Optional `expected_updated_at`; stale → 409 `REVIEW_CONFLICT` with current values. Writes a review event when state or notes change. |
| `POST /artifacts/review` | Bulk `{artifact_ids (1–200), state}`; all-or-nothing; unknown IDs → 404 listing them. |
| `GET /artifacts/{id}/review-history` | Review events (artifact and record level), newest first. |
| `PATCH /artifacts/{id}/evidence/{evidence_id}/review` | `{state, analyst_notes, expected_updated_at?}`. Classification is never changed. |
| `GET /artifacts/{id}/jobs` | Analysis history: status, times, app version, pipeline, options, problem count. |
| `GET /artifacts/{id}/evidence` | `provenance` adds `analyst_notes` and `review_updated_at`; the report adds `review_history`; `schema_version` becomes `"1.1"`. |
| `GET /artifacts/{id}/export?job_id&include_original` | ZIP evidence package (M2-6). |
| `PATCH /artifacts/{id}/duplicate-library` | `{included}`. Affects future duplicate searches only. |
| `GET /library/summary` | Indexed, not-analysed, and excluded counts and lists; storage bytes (originals, derived); artifact count. |
| `GET /settings`, `PATCH /settings` | `editable` and `environment` groups; patching an environment key → 422. |

New error codes: `REVIEW_CONFLICT`, `EVIDENCE_RECORD_NOT_FOUND`, `EXPORT_FAILED`.

Pipeline change: the `duplicates` stage skips excluded artifacts, records `excluded_count`, and says so in
its method and limitations. This is the only pipeline change in M2.

## 4. Database changes

Schema version 1 → 2, through Alembic (M2-1).

- `artifacts`: `in_duplicate_library BOOLEAN NOT NULL DEFAULT 1`; indexes on `review_state`,
  `original_filename COLLATE NOCASE`, and `size_bytes`.
- `evidence_records`: `analyst_notes TEXT NOT NULL DEFAULT ''`, `review_updated_at` (nullable).
- `review_events` (new, append-only): `id`, `artifact_id` (cascade), `evidence_id` (cascade, nullable),
  `from_state`, `to_state`, `notes_after`, `created_at`.
- `app_settings` (new): `key` (PK), `value_json`, `updated_at`.
- Deletion cascades to the new tables; the deletion summary adds `review_events`.

## 5. Frontend components

- Shared: `useApiResource` (loading / error / retry), `EmptyState`, `Skeleton`, `ErrorState` (message,
  code, Retry), `ReviewBadge`, `ProblemIndicator`, `HealthBanner`, `UnsavedChangesGuard`.
- Library: `LibraryPage` (state in `useSearchParams`), `SearchBox` (debounced), `FilterBar`,
  `SortControl`, `ArtifactTable` (selectable rows), `BulkReviewBar`, `Pagination`.
- Artifact: `ProblemsSummary`, `AnalysisHistory`, `RecordReview` (panel footer), `ReviewPanel` with
  conflict handling and history, `ExportMenu`, `DuplicateLibraryControl`, stale-results hint in
  `DuplicatesPanel`.
- Settings: `SettingsPage` with `EditableSettingsForm`, `EnvironmentSettings`, `ToolStatus`,
  `StorageUsage`, `DuplicateLibraryOverview`.
- Layout: navigation with Upload as the primary action, `HealthBanner`.
- No new frontend dependencies.

## 6. Backend service changes

- `core/database.py`: run Alembic migrations at startup; refuse a newer schema.
- `services/library.py`: list query (filters, escaped search, sort, indicators), library summary,
  duplicate-library include/exclude.
- `services/review.py`: artifact, bulk, and per-record review; conflict checks; review events.
- `services/exports.py`: ZIP built in `tmp/` with the standard library, manifest hashes, streamed, then
  removed. Reads only files recorded in `derived_files` and the artifact's original.
- `services/settings.py`: editable settings with defaults and validation; environment view.
- `services/analysis.py`: job history. `services/reports.py`: record review fields, review history.
- `services/duplicates.py` and `DuplicatesStage`: honour exclusion.
- Logging: never search terms, notes, or setting values (05 §7).

## 7. Test plan

Backend (pytest):

- Migration: an M1 database (frozen M1 schema plus data) upgrades to head with every row intact; a
  fresh database; the baseline revision reproduces the M1 schema; the models match the head revision;
  a newer revision is refused.
- List: each filter alone and combined; search on each field, case-insensitive, `%` and `_` literal;
  each sort both directions with a stable tiebreaker; review-state order; archived hidden by default;
  pagination totals; indicator values; invalid parameters → 422.
- Review: conflict → 409; events only on real changes, with full note text; bulk all-or-nothing and
  limit; per-record review; classification unchanged; history in the report; deletion removes events.
- Export: ZIP contents, manifest hashes re-verified, original only when requested, past jobs, 404s,
  temporary file removed, verdict-wording guard over the export.
- Duplicate library: excluded artifacts skipped and counted; existing evidence unchanged; re-include;
  summary counts.
- Settings: get/patch, validation, persistence, environment keys rejected, defaults applied.
- Job history; logs never contain search terms, notes, or setting values.

Frontend (Vitest, Testing Library, msw): Library URL state, search, filters, sort, pagination, bulk review
with confirmation and result, empty/no-results/loading/error states, indicators; artifact problems
summary, history switching, per-record review, review conflict, unsaved-changes guard, export options,
duplicate-library control, re-run hint; settings load/save/validation and read-only fields; health banner
and backend-unreachable state; Upload at `/upload`.

## 8. Implementation order

Each step is tested and committed before the next.

1. This plan and the M2 decisions.
2. Alembic baseline (M1 schema) and migration tests.
3. M2 schema revision.
4. `GET /artifacts` search, filters, sort, indicators.
5. Library page, navigation (Library at `/`, Upload at `/upload`), shared empty/loading/error components.
6. Review workflow: backend (conflict, events, bulk, per-record), then UI.
7. Job history, problems summary, health banner, error surfacing.
8. Duplicate-library management.
9. Evidence export package.
10. Settings.
11. Empty/loading-state sweep, accessibility pass, docs (03, 04, 07, 09, 10), acceptance, run
    instructions.
