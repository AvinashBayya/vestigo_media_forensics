# Capability Integration Audit and Roadmap (DRAFT)

**Status: draft for approval. Nothing here is implemented, and no dependency has been added.**

Audit of the capabilities proposed for Vestigo beyond Milestone 6, against the project's standing
rules: local-first (D1), evidence over verdicts (D2), human-only sign-off (D3), permission-gated and
clearly-labelled external services (D8, 05 §4), no facial recognition or biometrics (D9), complete
deletion (D11), and every record carrying method, tool, version, timestamps, source, limitations,
errors, and review state (04 §5).

Baseline at audit time: Milestones 1–6 complete and accepted, schema v7
(`0007_m6_location_candidates`), 412 backend / 8 container / 124 frontend tests green, clean tree.

## 0. Identification problem — read this first

Three of the five items cannot be audited as asked, and one input is missing entirely. Rather than
guess, this section states exactly what is unresolved.

| Item | Status |
|---|---|
| **"Any other tools, repositories, models, or services I previously listed"** | **No such list exists in my records.** I searched the repository, all documentation, the decision log, the memory files, and all three session transcripts for this project. There is no prior list of tools, repos, models, or services. The only hits for these names are in your latest message; the `needle` in `app/services/library.py:125` is an unrelated local variable holding search text. If you listed them in another session, another tool, or verbally, please re-send the list. |
| **Needle** | **Unidentified.** A targeted search found no plausible forensics, search, or security project by that name. The only repository literally named `needle` is Embroidermodder's internal tooling (zlib licence), which is clearly not it. Historic candidates exist (MWR's iOS assessment framework "Needle", long archived; a Python HTTP library; a vector-search service), but they are so different from one another that auditing any of them would be invention. **Needs a URL or repo owner.** |
| **Whistle** | **Ambiguous — at least five candidates**, and the two most plausible are each a policy problem rather than a feature: `avwo/whistle` (MIT, Node.js **packet-capture / HTTP-interception proxy** — traffic interception sits beside the §5 prohibitions on covert tracking and evasion, and has no role in analysing a stored artifact), and `0xDAEF0F/whistle` (Rust/Tauri **voice transcription** — directly collides with the standing non-goal "no transcription", restated in D19, D22, and D23). Others: `Selventa/whistle` (Java, biological knowledge modelling), `skycocker/whistle.js` (browser microphone whistle detection), `python-whistle` (PyPI, undescribed). **Needs a URL.** |
| **Cactus** | **Identified, with a documentation conflict** (see §2). |
| **Steganography / hidden-data inspection** | **Fully auditable**; assessed in §1 and recommended as the next milestone. |

Two further notes on scope:

- **Steganography is currently an explicit non-goal** in the approved M5 and M6 plans and in D22/D23.
  Adding it is a deliberate reversal and needs its own decision record saying so; it does not
  silently inherit prior approval.
- Nothing in this audit proposes facial recognition, biometrics, person tracking, covert
  surveillance, authenticity or deepfake verdicts, scraping, or cloud-first processing. Those remain
  refused regardless of which tool offers them.

## 1. Steganography and hidden-data inspection

**Purpose and workflow.** Report *observable structural facts* about a file that are consistent with
concealed or appended data, so an analyst can decide whether to investigate further. The analyst
uploads as today; a new optional stage runs; a panel lists what was found with the method and its
limits. No extraction of suspected payloads, no "hidden data detected" verdict, no "clean" verdict.

**The honesty line this capability must not cross.** Classic steganalysis tools emit statistical
*suspicion scores* (stegdetect's `*`/`**`/`***`). Presenting those as findings would be the first
verdict Vestigo has ever shipped and would contradict D2 and 04 §6. The defensible framing, matching
how C2PA (D20) and location clues (D23) already work:

- **OBSERVED**: bytes after a format's logical end (JPEG EOI, PNG IEND), embedded file signatures,
  container padding, extra streams or unexpected chunk types, unusually large comment or custom
  chunks, declared-vs-actual size mismatches. These are facts about the file's structure.
- **DERIVED**: computed measurements (LSB distribution, chi-square or entropy statistics) reported
  as *numbers with their method*, never thresholded into a conclusion.
- **Never**: "this file contains a hidden message", "steganography detected", "no steganography" —
  and never a confidence score Vestigo invented. Absence of findings proves nothing; ordinary
  cameras, editors, and CMSs append data routinely.

**Inputs / outputs.** Input: the stored original (read-only), as every stage does. Output: a
`hidden_data` evidence section (findings list with offsets, sizes, signature names, measurements) and
the tool's raw output as a derived file, so the finding is auditable and flows into export and
deletion automatically.

**Local vs external.** Fully local, fully offline. No network, no uploads.

**Candidate tools, dependencies, and supply-chain risk.** This is where care is needed: these tools
parse hostile input, which is exactly the attack surface a forensic tool must not widen.

| Tool | Licence | Maintenance | Risk assessment |
|---|---|---|---|
| **binwalk v3** (ReFirmLabs) | MIT (verify `LICENSE` at the pinned version) | Active; rewritten in Rust | **Recommended.** Memory-safe language, maintained, does exactly the signature/entropy scanning that maps to OBSERVED facts. **Extraction (`-e`) must be off**: it writes arbitrary paths from untrusted input (traversal, zip-bomb, resource-exhaustion risk). Signature scanning only. |
| **Pure-Python structural checks** (no dependency) | n/a | n/a | **Recommended alongside.** Trailing-bytes-after-EOI/IEND, chunk inventory, and size mismatches are a few dozen lines against bytes we already read, with no new attack surface and no new dependency. Highest value per risk of anything in this audit. |
| **outguess** | BSD (author states free for any use; per-file licences vary) | Effectively dormant | Deferred. C code parsing untrusted JPEGs; its value is payload *recovery*, which is beyond this scope. |
| **stegdetect** | Open source, licence name unconfirmed | Unmaintained ~20 years | **Not recommended.** Old C parsing hostile media, and its output is precisely the suspicion score we must not present. |
| **zsteg** | **Unverified** (Ruby) | Moderate | Deferred pending licence verification and a Ruby runtime decision; adds a whole language runtime to the image. |
| **stegoveritas** | **Unverified** (Python) | Moderate | Deferred; it is a wrapper that shells out to many of the above, inheriting all their risk at once. |

None of these are installed in the container today (checked), so this requires a Dockerfile change
and a new entry in the tool registry, which already runs tools with argument lists and timeouts and
never executes uploads.

**Privacy and retention.** No new personal data; findings are structural. Raw tool output is a
derived file, deleted with the artifact. Offsets and signature names are safe to log; file content is
not, and must not be (05 §7).

**Evidence model, custody, export, deletion, review.** Identical to every existing stage: one
evidence record with full provenance and limitations, raw output as a derived file with recorded
lineage (D21), automatic inclusion in `report.json` and the export package, automatic deletion and
counting, and the existing per-record review workflow. A `partial` status with a recorded warning
covers "the tool failed on this file" — never silence.

**Test strategy.** Generated fixtures (no committed binaries): a clean JPEG/PNG; the same files with
known bytes appended after EOI/IEND; a file with a ZIP appended (the classic case); an oversized
comment chunk; a truncated file; a file the tool fails on (warning recorded, stage partial). Assert
exact offsets and sizes, assert the absence of verdict words in all strings (the test plan already
has a `VERDICT_WORDS` check to extend), plus the standard export/deletion/custody/migration tests.

**Manual acceptance.** Build fixtures; upload the clean file (panel says nothing was found and that
this proves nothing); upload the appended-ZIP file (panel lists the embedded signature with its
offset and size, labelled as a structural observation with its limitations); export and confirm the
raw output is in the package with a verified hash; delete and confirm it is gone.

**Risks, limitations, non-goals.** Limitations: structural scanning finds containers and appended
data, not well-implemented LSB steganography; statistics are measurements, not evidence of
concealment; false positives are routine. Non-goals for this milestone: payload extraction or
decoding, password or passphrase attacks against stego tools, any form of "cleanliness" claim.

**Recommendation: local-only, opt-in via an analysis option, default ON** (consistent with
`c2pa` and `location_clues`, since it is cheap, offline, and produces honest facts), with
binwalk-based scanning and pure-Python structural checks only. No extraction.

## 2. Local AI capabilities using Cactus

**Identification and the documentation conflict.** The repository `cactus-compute/cactus` is an
on-device inference engine. The two authoritative-looking sources disagree, which matters for a
licence-sensitive decision:

- Its **GitHub README** states **Apache-2.0**, a Python package (`pip install -U cactus-compute`,
  Python 3.9+) and a CLI, and that it "downloads and caches the engine and requested model weights
  on first use".
- Its **documentation site** describes a source-available project **free only for personal, hobby,
  and SMB use**, with hybrid (cloud) inference, custom models, and extra hardware acceleration as
  **paid features**, mobile SDKs (React Native, Flutter, Kotlin), and a move from GGUF to a
  proprietary `.cact` model format.

Before any adoption, the exact `LICENSE` file at a pinned version must be read, along with the model
weights' separate licences (weights are licensed independently of the engine, and some popular ones
forbid commercial use). Vendor benchmark numbers are unverified and should not be repeated in our
docs (the project rule: no figures that do not come from our own reproducible fixtures).

**The harder question: what would local AI legitimately do here?** Vestigo's evidence model forbids
AI captions and descriptions (D22/D23 non-goals), authenticity and deepfake verdicts, and automated
geolocation verdicts — which rules out most of what a vision-language model is normally used for. The
uses that survive the evidence model are narrow and all **non-evidence**:

1. **Analyst drafting assistance** — e.g. proposing wording for an analyst's own notes or a location
   candidate's basis, which the analyst then edits and owns. Output must never be stored as an
   evidence record, never classified OBSERVED/DERIVED, and must be visibly marked as a draft the
   analyst wrote. (D3: only a human marks anything reviewed.)
2. **Local retrieval across the analyst's own library** — embeddings over their own notes and OCR
   text to find related artifacts. Useful, and honest, because the output is a pointer to their own
   material rather than a claim about media.
3. **Explaining existing evidence** in plain language, with the underlying record always shown.

Each of these is a *workflow aid*, not an analysis capability. If the goal is instead
AI-based manipulation or generation detection, that is refused under D2 and the standing non-goals
and is not made acceptable by running locally.

**Inputs / outputs, local vs external.** Local inference, but note that "local" is not automatic: the
first run **downloads engine binaries and model weights from the network** (Hugging Face), and the
docs describe an optional **cloud hybrid mode** that must be provably disabled and tested to be off.
A build that silently falls back to a cloud API would breach D1 and 05 §4.

**Dependencies and system requirements.** A new Python dependency plus downloaded native binaries and
multi-gigabyte weights; practical performance usually wants a GPU or NPU; the dev container currently
has neither configured. Model storage, caching, and cleanup become new state the deletion rules must
cover. This is by far the heaviest item in the audit.

**Security and supply-chain risk — the highest in this audit.** Downloaded native binaries and model
files are executable or parsed code from a third party, fetched at runtime, outside the container
build. That defeats a reproducible, auditable image unless pinned by digest and vendored
deliberately. Model weights are also an untrusted input format. This needs a **separate security
approval**, not a milestone decision record.

**Privacy and retention.** Local inference keeps media local only if hybrid mode is off. Prompts
would contain evidence content (OCR text, notes, coordinates), so nothing may be logged (05 §7), and
any cache of prompts or outputs becomes deletable state tied to the artifact.

**Evidence model, custody, export, review.** The defining rule: **model output is not evidence.** It
must live outside the evidence tables, be excluded from the evidence sections of the export package
(or included only in a clearly separated "analyst drafts, not evidence" area), and never acquire a
classification. If anything is persisted, it needs custody events and deletion coverage like
candidates and leads. Where output does influence an analyst record, provenance must name the model,
version, and quantisation.

**Test strategy.** Hermetic tests must not download models: the inference call sits behind an
interface with a fake in tests. Real-model tests are opt-in, marked, and excluded by default (like
the existing `container` marker). Tests must prove: no network call in the default configuration,
hybrid/cloud mode off, no model output in evidence tables or evidence exports, no prompt content in
logs, caches deleted with the artifact.

**Risks, limitations, non-goals.** Risks: licence ambiguity, supply chain, silent cloud fallback,
scope creep into verdicts, container size and build time, and non-determinism in a tool whose value
is reproducibility. Non-goals: any generated text presented as a finding, any detection claim, any
captioning of media.

**Recommendation: deferred,** pending three things in order — (1) you state which of the narrow
non-evidence use cases you actually want; (2) licence verification of the engine at a pinned version
*and* of the specific weights; (3) a separate security approval covering runtime downloads of native
binaries and weights. If approved later: local-only, opt-in, **default OFF**, with cloud features
compiled out or provably disabled. Note that if the use case is on-device inference for a *phone*
app, Cactus is a reasonable choice but Vestigo is a local desktop service and the fit is poor; for a
Linux x86-64 service, a mainstream local runtime would carry less licence and format risk.

## 3. Needle — blocked on identification

Cannot be audited without a URL or repository owner. When you supply it, the audit will cover the
same dimensions; the questions that will decide it are: does it process the artifact locally, does it
require network access or an account, is its licence compatible with redistribution in this
container, and does its output fit as OBSERVED/DERIVED facts or only as an analyst statement.

## 4. Whistle — blocked on identification, and two candidates are policy conflicts

As above. Flagging now so the decision is explicit: if you mean the **HTTP interception proxy**, it
is a network-traffic tool with no role in analysing a stored artifact, and traffic interception sits
next to the §5 prohibitions — it would need its own justification and security approval rather than a
milestone slot. If you mean the **voice-transcription app**, transcription is a standing non-goal
reaffirmed three times (D19, D22, D23); reversing that is a substantive evidence-model decision
(transcripts are interpretations of audio, and errors in them read as facts), not a tooling choice.

## 5. Proposed milestone sequence

**First: Milestone 7 — Hidden-data and structural inspection** (steganography, honestly framed).
It is local-only, fully offline, additive, needs no GPU or model downloads, fits the existing
evidence model exactly, carries the lowest supply-chain risk (one MIT Rust tool plus pure-Python
checks), and is the only proposed capability that is both well-defined and ready to plan. It
supersedes the steganography non-goal via a new decision record.

**Then: Milestone 8 — Vestigo integration** (the existing roadmap M7: versioned evidence API, case
linking, import/export, permission-aware integration, no direct database writes). Unchanged in
substance; renumbered because hidden-data inspection should land first. It is the last item of the
original roadmap and should not be delayed indefinitely behind new capabilities.

**Grouping.** Group only what shares a risk profile and an evidence shape:

- *Groupable:* binwalk signature scanning + pure-Python structural checks — one stage, one panel,
  one decision record.
- *Keep separate:* payload extraction (if ever wanted) from detection-of-structure; local AI drafting
  from local AI retrieval (different data flows, different storage); anything network-facing from
  anything local.
- *Never grouped with a feature milestone:* a dependency that downloads executables or weights at
  runtime.

**Gating summary.**

| Capability | Local-only | Offline / air-gap capable | GPU | Model download | Large storage | Needs separate security approval |
|---|---|---|---|---|---|---|
| Hidden-data inspection (binwalk + Python) | Yes | Yes (tool in the image) | No | No | No (< 20 MB) | No — a normal milestone decision record |
| Local AI (Cactus or alternative) | Only with cloud mode provably off | Only after weights are vendored into the image | Recommended | **Yes** (GB-scale) | **Yes** | **Yes** |
| Vestigo integration (existing M7/M8) | Yes (local API) | Yes | No | No | No | No, but needs a permission and data-flow review |
| Needle | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown until identified |
| Whistle | Unknown; interception or transcription readings would be | Unknown | Unknown | Unknown | Unknown | **Yes**, under either plausible reading |

**What I need from you to proceed.** (1) Approve or amend the sequence above. (2) Re-send the earlier
list of tools, repos, models, and services — it is not in my records. (3) Give URLs for Needle and
Whistle. (4) For local AI, state which narrow non-evidence use case you want, if any.

## 6. Sources consulted

- Cactus: [GitHub repository](https://github.com/cactus-compute/cactus),
  [documentation site](https://cactuscompute.com/docs/v1.6),
  [Hugging Face write-up](https://huggingface.co/blog/rshemet/cactus-on-device-inference)
- Whistle candidates: [avwo/whistle](https://awesome.ecosyste.ms/projects/github.com%2Favwo%2Fwhistle),
  [0xDAEF0F/whistle](https://awesome.ecosyste.ms/projects/github.com%2F0xdaef0f%2Fwhistle),
  [Selventa/whistle](https://github.com/Selventa/whistle),
  [skycocker/whistle.js](https://github.com/skycocker/whistle.js)
- Steganography tooling: [OutGuess (licence statement)](https://www.provos.org/p/outguess/),
  [outguess and stegdetect downloads](https://provos.org/p/outguess-and-stegdetect-downloads/),
  [binwalk v3 (ReFirmLabs)](https://github.com/ReFirmLabs/binwalk),
  [binwalk licence via MacPorts](https://ports.macports.org/api/v1/ports/binwalk/?format=api),
  [stego-toolkit index](https://awesome.ecosyste.ms/projects/github.com%2FDominicBreuker%2Fstego-toolkit)

Licences marked unverified above must be read from each project's `LICENSE` file at a pinned version
before adoption; `zsteg` and `stegoveritas` licences were not established by this audit.
