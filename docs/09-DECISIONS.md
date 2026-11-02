# Decisions

## D1 — Local-first

All media and evidence remain local by default.

## D2 — Evidence over verdicts

The system reports observable signals. It does not decide whether media is true or false.

## D3 — Human approval

Only a human analyst can mark evidence as reviewed, confirmed, or publishable.

## D4 — Simple visible product

The UI remains minimal. Advanced engine capabilities must not clutter the analyst workflow.

## D5 — Milestone 1 is image-only

Video, reverse-image search, GEOINT, satellite imagery, and Vestigo integration are later phases.

## D6 — FFmpeg installed early

FFmpeg and ffprobe are installed during environment setup but are not invoked until the video pipeline is implemented.

## D7 — Ports

- Backend: 8400
- Frontend: 5180

## D8 — External services are gated

External providers must be permission-gated, licence-aware, and clearly labeled.

## D9 — No facial recognition

The system must not perform facial recognition, biometric identification, or automated identity attribution.

## D10 — No offensive security features

No active scanning, exploitation, credential testing, evasion, or stealth functionality.

## D11 — Deletion is complete

Deleting an artifact removes its files, jobs, evidence, and database records.

## D12 — Claude must plan before coding

Claude Code must read all docs and produce a build plan before implementation.