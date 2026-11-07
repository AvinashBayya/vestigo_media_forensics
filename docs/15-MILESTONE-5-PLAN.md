# Milestone 5 Build Plan — Reverse-Image Search (approved)

Approved: 2026-11-06 with the proposed defaults (the four initial providers; editable,
custody-trailed leads; lightweight lead review). Implemented: 2026-11-07 (decision record in
`09-DECISIONS.md` D22).

Analyst-assisted external image search on the evidence-first architecture of Milestones 1–4.
Manual provider workflows only: Vestigo never transmits media anywhere; the analyst does, knowingly,
in their own browser.

## 1. Current-state audit

- **No external-search functionality exists.** The `EXTERNAL` evidence classification has been in
  the enum since Milestone 1 but nothing uses it; there is no provider code and the backend makes
  no outbound HTTP requests at all (its only subprocesses are the local tools).
- The security policy (05 §4) already governs this milestone: external services must be explicitly
  enabled, permission-gated, licence/terms-aware, clearly labelled, recorded as EXTERNAL, and
  disabled by default.
- Building blocks in place: original content endpoint and derived-file (keyframe) content endpoint
  (both inline-only today — no attachment download); keyframes with `derived_file_id` per frame in
  the evidence report; append-only `custody_events` (D21) whose `event_type` is a free string, so
  new event types need no migration; artifact-level review and the export package; cascade deletion
  with a counting summary; additive settings.
- Playable previews are a separate table and are already excluded from evidence; the search subject
  picker must never offer them.

## 2. Proposed decisions

| # | Decision |
|---|---|
| M5-1 | **Manual-first, nothing transmitted automatically.** Vestigo offers: the provider's public landing page (opened in a new tab), written instructions for uploading there manually, and a download of the exact subject file. Opening a provider page sends no media and no artifact data — the link is the provider's plain landing URL, with no identifiers, no query parameters derived from evidence, and `rel="noopener noreferrer"`. No prefilled search links: no listed provider officially accepts a URL our tool can give it (a localhost/container path is not a publicly accessible URL), so none are promised. |
| M5-2 | **Search subjects**: an uploaded image (the original), or one selected keyframe of a video (its real derived file). Audio has no searchable image and is refused. The playable preview is never offered or substituted — the picker lists only originals and keyframe derived files. |
| M5-3 | **Provider registry, disabled by default** (05 §4). A static in-code registry — initially Google Lens, Bing Visual Search, TinEye, Yandex Images — each with key, name, landing URL, terms URL, and manual-upload instructions. Every provider is disabled until the analyst enables it in Settings (`enabled_search_providers`, a new additive editable setting validated against registry keys). The UI explains, before any page is opened, that uploading the image to a provider shares it with that external service under that provider's terms. |
| M5-4 | **Leads are analyst statements, not machine observations.** A recorded lead stores: provider, result page URL, image URL (optional), analyst-reported publication date (optional, stored as given and always labelled *claimed, unverified*), notes, the source artifact, the selected keyframe where applicable, and `recorded_at` (set by Vestigo). Classification is fixed `EXTERNAL`; review state starts `UNREVIEWED`. The recorded-at date and any claimed publication date are separate fields and are never conflated; nothing ever calls the earliest result "the original source". |
| M5-5 | **Only observable actions are recorded.** Custody gains `lead_recorded`, `lead_updated` (names of changed fields only), and `lead_deleted`. Opening a provider page happens in the analyst's browser and completing a search happens on the provider's site — the backend cannot observe either, so neither is recorded, and the custody notice is extended to say so. Content downloads are plain GETs and stay unrecorded. |
| M5-6 | **Storage: additive Alembic 0006** (`schema_version` 6). New `external_leads` table: `id` (new `lead_` prefix), `artifact_id` (FK, cascade), `derived_file_id` (nullable FK — the searched keyframe), `provider` (free text; the registry drives the open-page UX, not what the analyst may record), `result_url`, `image_url` (nullable), `claimed_published_at` (nullable, free text as reported), `notes`, `review_state` (default UNREVIEWED), `created_at`, `updated_at` (nullable). Leads are analyst-editable records (unlike machine evidence), so no append-only triggers — edits and deletions are themselves recorded in the append-only custody trail. Existing evidence records are never touched. |
| M5-7 | **API.** `GET /search/providers` (registry + enabled flags + the sharing notice); `POST /artifacts/{id}/external-leads`; `GET /artifacts/{id}/external-leads` (newest first); `PATCH /artifacts/{id}/external-leads/{lead_id}` (fields, notes, review state); `DELETE …/{lead_id}`. The evidence report gains an additive artifact-level `external_leads` list (like `review_history`), so leads land in the export package's `report.json` automatically, and lead custody events land in `custody.json`. `DeletionSummary` adds `external_leads`. Both content endpoints gain `?download=true` (Content-Disposition attachment, same protective headers) for the subject download. |
| M5-8 | **UI.** One "Reverse-image search (external)" panel on image and video artifact pages: subject picker (original, or the viewed analysis's keyframes with thumbnails), the sharing warning, the enabled providers as open-in-new-tab buttons with their instructions (disabled providers point to Settings), a Download button for the subject, the lead entry form, and the recorded leads list — each lead labelled EXTERNAL / review state, "Recorded <date>" separated from "Publication date (analyst-reported, unverified)", with the standing limitation that an earlier result is not proof of origin. Settings gains a providers section with per-provider toggles and the policy note. |
| M5-9 | **Out of scope / refused**: automated scraping, CAPTCHA bypass, browser automation, rate-limit evasion, automatic media uploads, paid or official provider APIs (each needs its own approval), GEOINT, steganography, transcription, AI-generation detection, Vestigo integration. |

Standing rules as in every milestone: local-first; evidence-first with honest limitations; additive
migration only; no existing evidence rewritten; small descriptive commits; full backend, container,
frontend, lint, type-check, and production-build checks before each major step is committed.

## 3. Privacy and evidence limitations (recorded in the UI and docs)

- Uploading an image to a provider shares that media with an external service under its terms;
  Vestigo cannot delete it there. The warning appears before any provider page is opened.
- A lead is what the analyst says they found: URLs and dates are recorded as written, unverified.
- `recorded_at` is when Vestigo saved the lead; `claimed_published_at` is the analyst's reading of
  the provider page. They are different facts and are labelled as such.
- An earlier-dated result is a lead about prior appearance, never proof of the original source.
- Opening a provider page proves nothing about whether a search was performed or what it returned.

## 4. Tests

- **Backend**: registry listing and the enabled-flag gate; settings validation rejects unknown
  provider keys; lead CRUD with field validation (URL shapes, lengths), 404s, and audio refusal for
  keyframe subjects that do not belong to the artifact; custody `lead_recorded`/`lead_updated`
  (changed-field names only)/`lead_deleted`; the evidence report's `external_leads` section;
  `report.json` in the export carrying leads and `custody.json` carrying their events; deletion
  cascading leads and counting them; `download=true` sets attachment with the honest filename and
  keeps the protective headers.
- **Migrations**: v1/v2 databases upgrade in place to `schema_version` 6 with every row unchanged;
  the new table's FKs and defaults; models match the head revision (existing test).
- **Frontend**: subject picker (image original; video keyframes; preview never offered; audio shows
  why not); provider buttons appear only when enabled, with the warning and instructions; download
  links; lead form validation and submission; the leads list's EXTERNAL label, review control, and
  the recorded-vs-claimed date separation; Settings toggles round-trip.
- **Container**: unchanged (no new tools).

## 5. Manual acceptance walkthrough

1. Settings → enable TinEye and Google Lens; the policy note is shown. Reload an image artifact:
   the search panel lists both, each with instructions; other providers say "enable in Settings".
2. Click a provider: a new tab opens on the provider's landing page; nothing was uploaded (verify:
   no media request leaves Vestigo — the link is the plain landing URL).
3. Download the subject; upload it manually on the provider page; find a result.
4. Record the lead with the result URL and a claimed publication date. The list shows it as
   EXTERNAL / UNREVIEWED with "Recorded today" and "Publication date (analyst-reported,
   unverified)" as separate lines.
5. For a video: pick a keyframe in the panel (thumbnails; the playable preview is absent), download
   it, record a lead — the lead shows which keyframe it came from.
6. The Chain of custody panel gains `lead_recorded`; edit the lead → `lead_updated` naming the
   fields; delete it → `lead_deleted`, with the earlier events still present (append-only).
7. Export the package: `report.json` contains the leads; `custody.json` contains their events.
8. Delete the artifact: the summary counts `external_leads`; everything is gone.

## 6. Commit sequence

1. `feat(db)`: Alembic 0006 + `ExternalLead` model + migration tests.
2. `feat(api)`: provider registry, `GET /search/providers`, `enabled_search_providers` setting.
3. `feat(api)`: lead CRUD with custody events, report section, export and deletion integration,
   `download=true` on the content endpoints; backend tests.
4. `feat(web)`: search panel (subjects, providers, warning, download, lead form and list) + tests.
5. `feat(web)`: Settings provider toggles + tests.
6. `docs`: D22 decision record, roadmap, API spec, evidence model, security/privacy, test plan,
   README with the manual walkthrough.

## 7. Open questions for approval

1. Registry contents: are Google Lens, Bing Visual Search, TinEye, and Yandex Images the right
   initial four? (Any can be dropped; adding one later is a one-line registry change.)
2. May the analyst edit a recorded lead (with every edit in the custody trail), or should leads be
   immutable with delete-and-re-record as the only correction? **Default: editable, custody-trailed.**
3. Should the lead's review use the existing review-events machinery (schema change to allow
   lead references) or the lighter review state + custody trail proposed here? **Default: lighter.**
