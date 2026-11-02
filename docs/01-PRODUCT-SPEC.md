# Product Specification

## 1. Product name

Vestigo Media Forensics

## 2. Product type

Standalone local-first media provenance, verification, and OSINT enrichment service.

## 3. Primary user

OSINT analyst.

## 4. Supporting users

- Journalists
- Fact-checkers
- Researchers
- Editors
- PR and communications teams

## 5. Problem

Analysts need to inspect images and videos quickly, understand where they came from, identify signs of editing or reuse, extract useful text and metadata, and preserve evidence in a reviewable form.

Existing tools are often fragmented, cloud-dependent, overconfident, or unsuitable for careful evidence work.

## 6. Product promise

Vestigo Media Forensics helps users answer:

- What technical information does this file contain?
- Does it contain camera, software, location, timestamp, or provenance metadata?
- Does it contain C2PA / Content Credentials?
- Has it been edited, re-saved, or derived from another image?
- Are there visually similar images already in the local case library?
- What readable text appears in the image?
- What evidence can be preserved for review?

It does **not** claim to determine whether media is true, authentic, or deceptive.

## 7. MVP workflow

1. Analyst uploads an image.
2. System calculates hashes.
3. System extracts metadata.
4. System checks for C2PA / Content Credentials.
5. System generates a perceptual hash.
6. System performs OCR.
7. System searches the local library for visually similar images.
8. System produces a structured evidence report.
9. Analyst reviews findings and updates the review state.

## 8. MVP non-goals

The first working version must not include:

- Video analysis
- External reverse-image search
- Satellite imagery analysis
- Facial recognition
- Biometric identification
- Automated deepfake verdicts
- Cloud storage
- Multi-user authentication
- Vestigo database integration
- Active network scanning
- Exploitation or credential-testing tools

## 9. User-facing simplicity

The UI should focus on:

- Upload
- Analysis progress
- Key findings
- Metadata
- Duplicate matches
- OCR text
- Evidence download
- Review status

Advanced capabilities can exist in the backend, but should not clutter the primary analyst workflow.

## 10. Success criteria for Milestone 1

- A user can upload an image from the browser.
- The backend returns a structured JSON evidence report.
- The UI displays hashes, metadata, C2PA status, pHash, OCR text, and duplicate matches.
- All core tests pass.
- The system runs locally inside the Dev Container.
- No unsupported capability is presented as implemented.