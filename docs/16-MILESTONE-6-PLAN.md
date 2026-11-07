# Milestone 6 Build Plan — GEOINT / Geo-Lite (DRAFT)

**Status: draft — awaiting approval. Nothing below is implemented.**

Location-context analysis without overclaiming, on the evidence-first architecture of Milestones
1–5. Machine output is **location clues** — observable facts recorded as written — and everything
interpretive is an **analyst statement**, labelled as such. No stage ever claims media was taken at
a location; the architecture rule stands: *it must never automatically claim a location is
confirmed* (02-ARCHITECTURE §7).

## 1. Current-state audit (verified against the code, 2026-11-07)

- **GPS reaches the report only as raw text.** The metadata stage runs ExifTool without numeric
  output (`app/services/metadata.py:14`), so coordinates arrive as print-converted DMS strings
  (`51 deg 30' 0.00" N`) scattered through the `exif`/`composite` tag dumps; nothing parses,
  validates, or converts them, and the stage's own limitation says "Milestone 1 performs no
  location analysis" (`app/pipeline/image_pipeline.py:104`). The existing fixture already embeds
  GPS 51.5 N / 0.12 W and IPTC City "Testville" (`tests/fixtures/make_fixtures.py:185-206`).
- **IPTC/XMP location tags pass through as written** under their group names (City, Sub-location,
  Country, photoshop:*, Iptc4xmpCore) but are never aggregated or surfaced as location data.
- **Video/audio location is effectively invisible**: `media_info.summarize()` drops `format.tags`
  and `stream.tags`, so `com.apple.quicktime.location.ISO6709` and `creation_time` never reach the
  media_info payload; ExifTool does capture QuickTime/Matroska tags into the metadata "other"
  section as raw strings.
- **Timestamps**: EXIF dates and container creation dates appear only as generic tag rows; nothing
  collects the location-relevant ones side by side. OCR (image and keyframe) already exposes raw
  and cleaned text that can carry visible signs/place names — no code parses places out of it.
- **The analyst-record pattern is proven**: external leads (D22) give the exact template —
  editable rows, custody-trailed create/update/delete, lightweight review, exactly-as-entered
  storage, report/export/deletion integration — to clone for location candidates.
- **No map or geo dependency exists** in either package manifest, and the backend makes zero
  outbound HTTP requests. A map link would embed coordinates in its URL — evidence-derived — which
  the current security wording ("no query parameters, nothing evidence-derived", written for M5's
  landing pages) does not cover; it needs an explicit amendment if approved.
- Baseline: schema v6 (`0006_m5_external_leads`), 393/8/114 tests green, clean tree.

## 2. Proposed decisions

| # | Decision |
|---|---|
| M6-1 | **Honest framing.** Machine output is a `location_clues` evidence section: facts recorded as written (OBSERVED where copied from the file, DERIVED where computed, e.g. decimal conversion and range validation), with limitations stating that embedded location data is easy to edit, absence proves nothing, and presence never proves where media was captured. Interpretation lives only in analyst-entered **location candidates**, always labelled analyst-reported and unverified. The evidence-model capstone is restated, not weakened: no stage claims a location is confirmed. |
| M6-2 | **`location_clues` stage** in all three pipelines (image.v1, video.v1, audio.v1 — audio usually yields "none found", but the machinery is identical and honest), behind a new option `location_clues` (default **on**, like `c2pa`). The stage runs its own ExifTool read with numeric output (`-n`) and records: decimal latitude/longitude with hemisphere refs, the original as-written strings alongside, altitude (+ above/below sea level ref), GPS date/time stamps, EXIF DateTimeOriginal/CreateDate and QuickTime/Matroska creation dates (each labelled as-written), camera Make/Model/Software/Orientation, ISO 6709 location strings parsed where present (QuickTime), and an aggregated list of location-named text tags (IPTC City/Sub-location/Province-State/Country, XMP photoshop and Iptc4xmpCore fields) exactly as written with their group names — disagreements shown side by side, never reconciled. Raw ExifTool output stored as a derived file. |
| M6-3 | **Coordinate validation, not correction**: latitude within ±90, longitude within ±180, refs consistent. Out-of-range or malformed values are recorded as written and flagged `invalid` — never discarded, never fixed, never guessed. |
| M6-4 | **No NLP, no invented clues.** The stage does not extract place names from OCR text or free-text fields — that would be inference presented as observation. Instead the section records whether OCR text exists for this analysis, and the panel points the analyst at the OCR panels to review visible signs, addresses, and timestamps themselves. |
| M6-5 | **Location candidates are analyst statements** in a new `location_candidates` table (Alembic 0007, schema_version 7, additive, `loc_` id prefix), cloned from the external-lead pattern: `description` (required — the place as the analyst would state it), optional decimal `latitude`/`longitude` (range-validated on input), required `basis` (why the analyst thinks so), optional `notes`, an **analyst assessment** label (`speculative` / `possible` / `likely`, default `speculative` — explicitly the analyst's own judgment, never a machine score; no numeric confidence anywhere), lightweight `review_state` starting UNREVIEWED, `created_at`/`updated_at`. Classification fixed **UNVERIFIED** (an analyst hypothesis: not machine-observed, not from an external service). |
| M6-6 | **Supporting evidence attachments.** A candidate carries a `supports` list of typed references — `{type: "evidence_record" \| "derived_file" \| "external_lead", id}` — each validated to exist and belong to the same artifact, plus free-text support notes. The UI renders them as links to the referenced panel/content. Nothing is inferred from them. |
| M6-7 | **Custody-trailed edits**, exactly like leads: `location_candidate_recorded` / `location_candidate_updated` (changed field names only) / `location_candidate_deleted`; no-op saves record nothing; a deleted candidate's history stays in the trail. Candidates flow into the evidence report (artifact-level list), the export package (report.json; events in custody.json), and the deletion summary, and cascade-delete with the artifact. |
| M6-8 | **Map: one explicit, gated external link — no embedded map.** A new boolean setting `enable_external_map_links` (default **false**) in Settings with OpenStreetMap's terms linked. When enabled AND valid coordinates exist, the panel shows "Open in OpenStreetMap (external)" built **entirely client-side** (the backend never sees or logs the URL), opening `openstreetmap.org/?mlat=…&mlon=…` in a new tab with `noopener noreferrer`. Its own distinct warning — not the M5 text — states plainly: *clicking sends these coordinates to openstreetmap.org in the URL*. No tiles, no iframe, no auto-loading (tiles would silently transmit coordinates on every page view — covert-tracking territory), no API key. 05-SECURITY-PRIVACY §4 gets a conscious carve-out sentence: an external map link embeds the coordinates the analyst is looking at, only behind the dedicated toggle and warning, only on click. |
| M6-9 | **Reverse geocoding is deferred** (it is an external lookup service; the roadmap keeps it in scope for a later pass, each service needing its own approval like paid search APIs). The analyst reaches the same end via the gated map link. |
| M6-10 | **Privacy of coordinates.** GPS coordinates and candidate fields are sensitive: they never appear in backend logs (only artifact/candidate ids do, matching the leads service), never in access logs, and the stage/service code is tested for that. No outbound HTTP from the backend, ever. |
| M6-11 | **Refused / out of scope** (restating your boundaries): no facial recognition, biometrics, person tracking, covert surveillance, automated geolocation verdicts, satellite-imagery or terrain analysis, shadow/solar positioning, social-media intelligence, AI captions, transcription, steganography, scraping/CAPTCHA/rate-limit evasion, automatic uploads, cloud processing, Vestigo integration, or multi-user login. |

Standing rules as in every milestone: local-first; additive migration only; existing evidence never
rewritten; small descriptive commits; full backend, container, frontend, lint, type-check, and
production-build checks before each major step is committed.

## 3. UX

One **"Location clues"** panel on every artifact page (all media types), two clearly separated
parts:

- **Machine section** (from the `location_clues` evidence section): coordinates shown in both
  decimal and the original as-written form, validity flag, altitude, GPS timestamp next to the
  EXIF/container dates ("all as written in the file — easy to edit, not verified"), camera
  make/model/software/orientation, the location-named text tags grouped by source family, and the
  OCR pointer ("OCR text exists for this analysis — review it for visible signs, addresses, and
  timestamps"). Empty state: "No location metadata was found. Absence proves nothing — most
  workflows strip it." The gated OSM link appears here when enabled and coordinates are valid.
- **Analyst section**: location candidates — create form (description, optional lat/lon, basis,
  assessment select labelled "Analyst assessment (your judgment, not a measurement)", notes,
  supporting-evidence picker listing this artifact's evidence records / derived files / external
  leads), and the candidate list with UNVERIFIED badge, assessment label, "Recorded <date>" /
  "edited <date>", review select, notes edit, and two-step delete — mirroring the leads UI.

Settings gains the `enable_external_map_links` toggle with its own warning copy and the OSM terms
link. Upload form and Settings defaults gain the `location_clues` check for all three media types.

## 4. API

- Evidence report: new per-job `location_clues` section (with full provenance like every stage) and
  a new artifact-level `location_candidates` list (like `external_leads`). Both additive;
  `schema_version` of the report stays 1.2.
- `GET /artifacts/{id}/location-candidates` (newest first, with the honesty notice),
  `POST` (201), `PATCH /{candidate_id}` (fields, assessment, review state; explicit null rejected
  422 on required fields, same as leads), `DELETE` (204).
- `SettingsUpdate`/`EditableSettings` gain `enable_external_map_links: bool = False` and the
  analysis options models gain `location_clues: bool = True`.
- `DeletionSummary` gains `location_candidates`.
- No map endpoint exists: the OSM URL is built in the browser from report data it already has.

## 5. Database migration (Alembic 0007, additive only)

`location_candidates`: `id` String(40) PK (`loc_`), `artifact_id` FK cascade, `description`
String(500), `latitude`/`longitude` nullable Float (validated on input; stored as given),
`basis` Text, `notes` Text, `analyst_assessment` String(16), `supports` JSON (validated list of
typed refs), `review_state` String(16), `created_at`, `updated_at` nullable; composite index
`(artifact_id, created_at)`. No append-only triggers (editable rows; custody is the audit).
`schema_meta` → '7'; downgrade raises, as always. v1–v6 databases upgrade in place with every row
unchanged (tested).

## 6. Tests

- **Backend**: stage output against the existing GPS fixture (51.5 N / 0.12 W decimal conversion
  correct, Testville surfaced from IPTC) plus new fixtures — a southern/western-hemisphere image, a
  malformed/out-of-range GPS image (flagged invalid, kept as written), a video with
  `-metadata location=+51.5000-000.1200/` (ISO 6709 parsed), XMP-only location tags, and media with
  none (absence wording); option off → skipped with reason; raw ExifTool output stored as a derived
  file; coordinates absent from captured logs. Candidates: CRUD, validation (ranges, explicit-null
  422, extra fields, 404s), `supports` refs must exist and belong to the artifact (404/422
  otherwise), custody events incl. no-op rule and trail-after-delete, report/export/custody.json/
  deletion flow, assessment values constrained.
- **Migrations**: v1–v6 → v7 in place without data loss; table shape, FK, cascade.
- **Frontend**: machine section rendering (decimal + as-written, invalid flag, as-written labels,
  OCR pointer, honest empty state); OSM link only when the toggle is on AND coordinates valid, with
  the coordinate-sharing warning and correct `rel`/`target` (and never any tile/iframe); candidate
  form and list with the UNVERIFIED badge and analyst-assessment labelling; supports links; review
  and two-step delete; custody refetch after candidate actions; Settings toggle off by default;
  upload-form option.
- **Container**: unchanged (ExifTool already present).

## 7. Manual acceptance walkthrough

1. Upload the GPS fixture image: the Location clues panel shows 51.5, −0.12 (decimal) beside the
   original DMS strings, "as written, not verified", IPTC City "Testville", camera fields, and the
   EXIF dates next to the GPS timestamp. The map link is absent.
2. Enable "External map links" in Settings (note the warning and OSM terms link). The panel now
   offers "Open in OpenStreetMap (external)"; clicking it opens a new tab whose URL carries exactly
   those coordinates — the warning said it would.
3. Upload a plain image: "No location metadata was found. Absence proves nothing."
4. Upload the ISO 6709 video fixture: coordinates parsed from the container tag, labelled with
   their source; keyframe OCR pointer shown when OCR ran.
5. Record a location candidate ("Near Trafalgar Square", basis citing the IPTC city + a supporting
   evidence record): it lists as UNVERIFIED / speculative / "analyst-reported, unverified", with
   the support linked. Edit the assessment → custody gains `location_candidate_updated` naming the
   field; delete (two-step) → `location_candidate_deleted` with earlier events intact.
6. Export: report.json carries the location_clues section and the candidates; custody.json their
   events. Delete the artifact: `location_candidates` counted, everything gone.
7. Grep the backend log from this session: no coordinates anywhere.

## 8. Commit sequence

1. `feat(db)`: Alembic 0007 + `LocationCandidate` model + migration tests.
2. `feat(pipeline)`: `location_clues` stage (ExifTool numeric read, validation, ISO 6709, text
   tags), option wiring, report section, fixtures + backend tests.
3. `feat(api)`: candidate CRUD with custody events, supports validation, report/export/deletion
   integration + tests.
4. `feat(web)`: Location clues panel (machine section + candidates) + tests.
5. `feat(web)`: Settings map-link toggle, gated OSM link with its warning, upload-form option +
   tests.
6. `docs`: D23 decision record, roadmap, master spec, API spec, evidence model §14 (+ the
   location-capstone restatement), security/privacy §4 carve-out + logging note + deletion list,
   test plan §11, dependencies (none added), README scope + manual walkthrough.

## 9. Open questions for approval

1. **Candidate classification**: fixed `UNVERIFIED` (analyst hypothesis) as proposed, or reuse
   `EXTERNAL` for symmetry with leads despite candidates not coming from an external service?
   **Default: UNVERIFIED.**
2. **Analyst assessment labels**: `speculative` / `possible` / `likely` (no "confirmed" — only the
   review workflow can mark anything reviewed, and nothing should read as a verdict). Accept, or
   different words? **Default: as proposed.**
3. **The OSM map link (M6-8)**: include behind the dedicated toggle + warning + §4 carve-out, or
   drop the map entirely from this milestone (the coordinates are still shown for manual use)?
   **Default: include, gated.**
4. **Audio**: run the clues stage on audio too (cheap, honest "none found", consistent), or exclude
   audio from M6 entirely? **Default: include.**
