# Consolidated Capability Roadmap — Three Implementation Passes

**Status: approved plan, implementation in progress.** Supersedes the fragmented per-capability
deferral in `17-CAPABILITY-INTEGRATION-AUDIT.md` (kept for its licence research and risk notes).

Baseline: Milestones 1–6 complete, schema v7 (`0007_m6_location_candidates`), 412 backend / 8
container / 124 frontend tests green. Context: a student's local-first, zero-recurring-cost
prototype. The user handles third-party licences, terms, and deployment approvals; this plan records
licence names and source URLs and preserves evidence integrity.

## 0. The toolchain, identified

All three named tools are from the same vendor, Cactus Compute, and the stack is coherent, tiny, and
CPU-only — far lighter than a typical local-AI stack.

| Name | What it actually is | Licence | Source | Install | Size |
|---|---|---|---|---|---|
| **Cactus** | On-device inference engine (Cactus Kernels / Graph / Engine) | Apache-2.0 (per repo README; the vendor docs site also describes paid tiers for hybrid cloud inference, custom models, and extra hardware acceleration — we use none of those) | [github.com/cactus-compute/cactus](https://github.com/cactus-compute/cactus) | `pip install cactus-compute` (4.0.1) | engine binary |
| **Needle** | Automation model + C++ engine: tool calling and structured extraction. Embeddings and ASR need the generation 3 engine, which the vendor does not publish - see D27 | Apache-2.0 | [github.com/cactus-compute/needle](https://github.com/cactus-compute/needle), weights [Cactus-Compute/needle3](https://huggingface.co/Cactus-Compute/needle3) | `pip install cactus-needle` (3.2.10), `import needle` | 8–29 MB |
| **Whistle** | Speech-to-text model running on the Needle engine; word-level timestamps with probabilities, keyword biasing, 7 languages claimed (sources disagree; EN/DE/FR confirmed) | Apache-2.0 | weights [Cactus-Compute/whistle](https://huggingface.co/Cactus-Compute/whistle) | same package | 16.9 MB |

Verified API surface (from the published package documentation):

- Tool calling: `@needle.tool` decorator; `needle.Needle(tools=[...]).run(prompt)`; each turn returns
  `function_calls`, `reasoning`, and **`confidence`** — so confidence is *model-provided* and may be
  recorded as such; Vestigo never invents one.
- Structured extraction: declare a shape and pass messy text; implemented in practice as a
  schema-shaped tool call.
- ASR: `needle.transcribe(path, word_timestamps=True, keywords=[...], language=...)` returning text,
  language, time-to-first-token and decode rate; `needle.Whistle()` for the object interface and
  `embed(audio)`; `needle.stream(chunks)` for live audio (not used here).
- Text embeddings: documented as a capability but **not clearly exposed in the Python API** (only
  `Whistle.embed(audio)` and a C-level `needle_embed`). Pass 1 therefore puts embeddings behind an
  adapter with a dependency-free local fallback, so semantic search works today and upgrades to
  Needle text vectors the moment that API is confirmed.
- Model weights load from a local `.cact` path (`--model needle3.cact`), so **manual import and
  air-gapped operation are supported**; `needle build --platform …` fetches engine and weights.

### Two hard constraints found during research — designed around, not ignored

1. **Telemetry is ON by default in the Needle binary.** It is disabled with `NEEDLE_TELEMETRY=0` and
   `DO_NOT_TRACK=1`. Vestigo sets both in-process before the runtime is ever imported, exposes them
   in the health/settings view, and a test asserts the invariant. Without this, the default build
   would breach "no automatic upload" and "no silent cloud fallback".
2. **`needle platform finetune` uploads files to Cactus GPUs** and needs `NEEDLE_API_KEY`. Vestigo
   never calls it, never reads that variable, and the local-only runtime wrapper exposes no
   fine-tuning entry point at all.

### One gated step

Installing and executing third-party packages is blocked by this environment's external-code policy.
Everything in Pass 1 is therefore built so that **the architecture, storage, custody, export,
deletion, review, UI, and the entire test suite work without the dependency installed**: the real
`needle`-backed provider is implemented but inactive until `cactus-needle` is installed and the
feature is enabled in Settings. Live-model tests are marked `live_model` and excluded by default, the
same way `container` tests already are. Nothing downloads at import time, ever.

## 1. Architecture decisions (made once, applied across all three passes)

- **AI output is never evidence.** It lives in its own tables (`ai_drafts`, `transcripts`,
  `embedding_chunks`), never in `evidence_records`, and carries no OBSERVED/DERIVED classification.
  Every surface labels it **"AI-generated, unverified — analyst must review."** Exports place it in a
  clearly separated `ai/` area, never inside the evidence sections.
- **Providers behind adapters.** `app/services/ai/` defines small protocols — `TextGenerator`,
  `FieldExtractor`, `Transcriber`, `TextEmbedder` — with a `needle` implementation, a
  dependency-free `local` implementation where honest (embeddings), and a `disabled` default that
  returns a clear "not configured" error. Tests use fakes; no network, no weights.
- **Everything is opt-in and default-off**, per capability, in Settings: `ai_enabled`,
  `transcription_enabled`, `semantic_search_enabled`, plus `ai_model_path` / `ai_runtime` settings
  for manual model import. Zero cost, zero network in the default configuration.
- **Model provenance is recorded on every AI artifact**: model name, version, quantisation, source
  URL, licence, runtime, plus timestamps, duration, warnings, errors, and the source-material
  lineage (which artifact, which evidence record, which audio stream).
- **Custody for analyst-visible AI actions**: generation, acceptance, edit, rejection, and deletion
  of drafts and transcripts write append-only custody events, like leads (D22) and candidates (D23).
  Content never enters custody details or logs — only ids, model names, and field names.
- **Additive migrations only**, one per pass: `0008` (Pass 1), `0009` (Pass 2), `0010` (Pass 3), each
  bumping `schema_version` and tested from v1 upward without data loss.
- **No verdicts anywhere.** Structural findings and measurements only; the existing `VERDICT_WORDS`
  test guard is extended to the new sections.

## 2. Pass 1 — Local intelligence foundation — **complete** (2026-11-07, D24, schema 0008)

| Commit | Contents |
|---|---|
| 1 | **Runtime and model management.** `app/services/ai/` adapters; telemetry kill-switch; `GET /ai/status` (runtime present, model present, flags, telemetry off); model registry recording name/version/quantisation/source/licence/runtime; manual import by path plus optional explicit download; cache listing and deletion. Settings: `ai_enabled` (off), `ai_model_path`, `ai_runtime`. |
| 2 | **Needle structured extraction.** `ai_drafts` table (Alembic 0008): `kind`, `source` (OCR text / notes / metadata / document), extracted fields as JSON with model-provided confidence where present, status `proposed`/`accepted`/`edited`/`rejected`, model provenance, timestamps. API to generate a draft, then accept / edit / reject **per field**. Never writes to metadata or evidence. Custody-trailed. |
| 3 | **Whistle transcription.** `transcripts` table: timestamped segments with word-level timing where available, language, duration, model provenance, warnings/errors, `source` (the artifact's audio, or a video's audio track extracted with the existing ffmpeg to a derived file so lineage is explicit), status and analyst edits. Opt-in per analysis and per artifact; originals never touched. Exported under `ai/transcripts/`. |
| 4 | **Embeddings, semantic search, RAG.** `embedding_chunks` table over notes, OCR text, transcripts, and selected metadata; `GET /search/semantic`; question answering that **always** returns the source artifacts and evidence records it drew on, with the generated answer visibly separated and never storable as evidence. Indexes are derived data, deleted with the artifact and rebuildable. |
| 5 | **UI integration.** An "Assistant (AI drafts)" panel per artifact (drafts with per-field accept/edit/reject), a transcript panel with editing and the machine-generated label, a semantic-search page with answer-plus-sources, and Settings for enablement, model import, cache, and the telemetry indicator. |
| 6 | **Tests and docs.** Hermetic fakes throughout; marked `live_model` tests for the real runtime; export/deletion/custody/migration coverage; D24 decision record; README and test-plan updates. |

## 3. Pass 2 — Deep media forensics — **complete** (2026-11-09, D25; no migration needed)

- **Hidden-data and structural inspection**: a `structural` stage for images, video, audio,
  documents, and archives — trailing data after a format's logical end, embedded file signatures with
  offsets and sizes, unexpected or oversized chunks, padding, declared-vs-actual size mismatches,
  plus entropy, LSB distribution, and chi-square **as measurements with their method**. binwalk v3
  (MIT, [ReFirmLabs/binwalk](https://github.com/ReFirmLabs/binwalk)) for signature scanning with
  **extraction disabled** (`-e` writes attacker-controlled paths), alongside pure-Python checks that
  need no dependency. Raw output stored as a derived file. No payload extraction, no password
  cracking, and never "steganography detected" or "file is clean".
- **Advanced image and video forensics**: local indicators and measurements only — JPEG quantisation
  tables and recompression indicators, double-quantisation statistics, PRNU-style noise measures
  where cheap, frame-level continuity measures for video — each reported as a number with its method
  and limits. No manipulation or authenticity verdicts.
- **Document and PDF analysis**: text, metadata, page images, embedded files, signature *presence*
  (structure, not trust), object and JavaScript/embedded-action inventory as structural facts, OCR
  where needed, page-level provenance and derived-file lineage. Upload support for PDF and common
  document types extends the existing byte-sniffing validator.
- **Audio analysis**: metadata, duration, codec, channels, sample rate, embedded artifacts and
  structural indicators, plus Whistle transcription from Pass 1. Originals and derived outputs stay
  separate. No authenticity verdicts.

## 4. Pass 3 — GEOINT and integrations — **complete** (2026-11-09, D26, schema 0009)

- **GEOINT tool integrations**: builds on D23 — richer local geospatial handling, optional **offline
  map data** (locally stored tiles or a vector file the analyst supplies; nothing fetched
  automatically), coordinate-format conversions, distance and proximity helpers between an artifact's
  clues and analyst candidates, and the existing candidate/supporting-evidence/review workflow. No
  automatic determination of a location, and no coordinates or media sent anywhere by default.
- **Optional external integrations**: only ones explicitly requested later, each permission-gated,
  default-off, with explicit-action-plus-warning UX, recording only in-app observable actions.
- **Final integration hardening** (the original roadmap M7): a versioned evidence API, case linking,
  import/export, permission-aware integration, no direct database writes by external integrations,
  and complete custody, export, deletion, and migration coverage.

## 5. Standing non-goals across all passes

No paid APIs, cloud inference, cloud storage, or cloud transcription. No silent cloud fallback. No
automatic upload of media, prompts, embeddings, or evidence. No scraping, CAPTCHA bypass, or
rate-limit evasion. No facial recognition, biometric identification, person tracking, or covert
surveillance. No authenticity, deepfake, or geolocation verdicts. No AI output presented as a
finding. No fine-tuning that uploads data.

## 6. Verification applied to every pass

Backend, container, frontend, lint, type-check, and production-build checks before each commit;
additive migrations tested from schema v1 through the new version without data loss; export,
deletion, custody, and review coverage for every new record type; manual acceptance instructions at
the end of each pass.
