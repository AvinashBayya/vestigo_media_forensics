import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { ARTIFACT_ID, JOB_ID, OTHER_ARTIFACT_ID, artifactDetail, c2paSection, evidenceReport, jobStatus, provenance } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

function section(name: string) {
  return screen.getByRole("region", { name });
}

describe("ArtifactPage", () => {
  it("renders the analysis result sections", async () => {
    renderApp(PAGE);

    expect(await screen.findByRole("heading", { name: "harbour.jpg" })).toBeInTheDocument();
    for (const name of [
      "File hashes",
      "Content Credentials (C2PA)",
      "Duplicate search (local library)",
      "Text in image (OCR)",
      "Perceptual hash",
      "Embedded metadata",
    ]) {
      expect(section(name)).toBeInTheDocument();
    }
    expect(within(section("File hashes")).getByText("a".repeat(64))).toBeInTheDocument();
    expect(within(section("Perceptual hash")).getByText("eb1c2d708d668e63")).toBeInTheDocument();
    expect(screen.getByText(/does not determine whether the media is authentic/i)).toBeInTheDocument();
  });

  it("renders the metadata section with tabs", async () => {
    const user = userEvent.setup();
    renderApp(PAGE);

    const metadata = await screen.findByRole("region", { name: "Embedded metadata" });
    expect(within(metadata).getByText("Make")).toBeInTheDocument();
    expect(within(metadata).getByText("VestigoTestCam")).toBeInTheDocument();

    await user.click(within(metadata).getByRole("tab", { name: "XMP (2)" }));
    expect(within(metadata).getByText("Fixture title")).toBeInTheDocument();

    await user.click(within(metadata).getByRole("tab", { name: "IPTC (0)" }));
    expect(within(metadata).getByText("No IPTC metadata found.")).toBeInTheDocument();
  });

  it("opens the metadata section on the first group that has tags", async () => {
    const report = evidenceReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json({ ...report, metadata: { ...report.metadata!, exif: {}, xmp: {} } }),
      ),
    );
    renderApp(PAGE);

    const metadata = await screen.findByRole("region", { name: "Embedded metadata" });
    expect(within(metadata).getByRole("tab", { name: "Other (1)" })).toHaveAttribute("aria-selected", "true");
    expect(within(metadata).getByText("FileType")).toBeInTheDocument();
  });

  it("renders the OCR section", async () => {
    renderApp(PAGE);

    const ocr = await screen.findByRole("region", { name: "Text in image (OCR)" });
    expect(within(ocr).getByText("VESTIGO EVIDENCE SAMPLE 2026")).toBeInTheDocument();
    expect(within(ocr).getByText(/Tesseract confidence 91% \(the engine's own estimate\)/)).toBeInTheDocument();
    expect(within(ocr).getByText("Used: Grayscale pass.")).toBeInTheDocument();
    expect(within(ocr).getByText(/its confidence gain was -0.01/)).toBeInTheDocument();
    expect(within(ocr).getByText("Grayscale pass: 4 words, confidence 91% (the engine's own estimate)")).toBeInTheDocument();
    expect(within(ocr).getByText("Threshold pass: 4 words, confidence 90% (the engine's own estimate)")).toBeInTheDocument();
    expect(within(ocr).getByText("Preprocessing")).toBeInTheDocument();
    expect(within(ocr).getByText("Converted to 8-bit greyscale.")).toBeInTheDocument();
    expect(within(ocr).getByText("mode=L")).toBeInTheDocument();
    expect(within(ocr).queryByText("Cleaned text")).not.toBeInTheDocument();
    expect(within(ocr).queryByText(/accura/i)).not.toBeInTheDocument();
  });

  it("labels OCR as provisional and keeps raw text, steps, pass, confidence, limitations and errors visible", async () => {
    const base = evidenceReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            ocr: {
              ...base.ocr!,
              provenance: provenance("ocr", {
                status: "partial",
                tool: "Tesseract",
                tool_version: "5.5.0; Pillow 13.0.0",
                errors: [{ type: "OCR_VARIANT_FAILED", message: "The threshold pass failed." }],
                limitations: ["Confidence is Tesseract's own estimate, not a measured accuracy."],
              }),
            },
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const ocr = await screen.findByRole("region", { name: "Text in image (OCR)" });
    expect(within(ocr).getByText("Provisional:")).toBeInTheDocument();
    expect(within(ocr).getByText(/not a verified transcription/)).toBeInTheDocument();
    expect(within(ocr).getByText("VESTIGO EVIDENCE SAMPLE 2026")).toBeInTheDocument();
    expect(within(ocr).getByText("Converted to 8-bit greyscale.")).toBeInTheDocument();
    expect(within(ocr).getByText("Used: Grayscale pass.")).toBeInTheDocument();
    expect(within(ocr).getByText(/Tesseract confidence 91% \(the engine's own estimate\)/)).toBeInTheDocument();
    expect(within(ocr).getByText("OCR_VARIANT_FAILED")).toBeInTheDocument();
    expect(within(ocr).getByText("Method and limitations (1)")).toBeInTheDocument();
    expect(within(ocr).getByText(/not a measured accuracy/)).toBeInTheDocument();
  });

  it("labels an empty OCR result as provisional too", async () => {
    const base = evidenceReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(evidenceReport({ ocr: { ...base.ocr!, text: "", confidence: null, word_count: 0 } })),
      ),
    );
    renderApp(PAGE);

    const ocr = await screen.findByRole("region", { name: "Text in image (OCR)" });
    expect(within(ocr).getByText("No text detected.")).toBeInTheDocument();
    expect(within(ocr).getByText("Provisional:")).toBeInTheDocument();
  });

  it("shows cleaned OCR text with the raw output kept alongside", async () => {
    const base = evidenceReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            ocr: {
              ...base.ocr!,
              text: "FIELD NOTES\n|\n17 MARCH",
              cleaned_text: "FIELD NOTES\n17 MARCH",
              cleaning: [
                {
                  rule: "remove_symbol_only_lines",
                  description: "Removed lines that contain only symbols or punctuation (no letters or digits).",
                  lines_affected: 1,
                },
              ],
              selected: { variant: "threshold", reason: "The grayscale pass found no words." },
            },
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const ocr = await screen.findByRole("region", { name: "Text in image (OCR)" });
    expect(within(ocr).getByText("Cleaned text")).toBeInTheDocument();
    const boxes = within(ocr).getAllByText((_, element) => element?.tagName === "PRE");
    expect(boxes.map((box) => box.textContent)).toEqual(["FIELD NOTES\n17 MARCH", "FIELD NOTES\n|\n17 MARCH"]);
    expect(within(ocr).getByText("Raw OCR output (unchanged)")).toBeInTheDocument();
    expect(within(ocr).getByText(/Removed lines that contain only symbols or punctuation .* \(1\)/)).toBeInTheDocument();
    expect(within(ocr).getByText("Used: Threshold pass.")).toBeInTheDocument();
  });

  it("shows a failed threshold pass", async () => {
    const base = evidenceReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            ocr: {
              ...base.ocr!,
              candidates: [
                base.ocr!.candidates[0],
                {
                  variant: "threshold",
                  status: "failed",
                  text: null,
                  confidence: null,
                  word_count: null,
                  error: "Tesseract exited with code 1 (boom).",
                },
              ],
              selected: { variant: "grayscale", reason: "The threshold pass failed, so the grayscale pass is used." },
              provenance: provenance("ocr", {
                status: "partial",
                errors: [{ type: "OCR_VARIANT_FAILED", message: "The threshold pass failed." }],
              }),
            },
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const ocr = await screen.findByRole("region", { name: "Text in image (OCR)" });
    expect(within(ocr).getByText("Threshold pass: failed (Tesseract exited with code 1 (boom).)")).toBeInTheDocument();
    expect(within(ocr).getByText("VESTIGO EVIDENCE SAMPLE 2026")).toBeInTheDocument();
  });

  it("renders OCR records made before two-pass OCR", async () => {
    const base = evidenceReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            ocr: {
              ...base.ocr!,
              cleaned_text: null,
              cleaning: [],
              preprocessing: [
                { step: "note", applied: true, description: "Converted to an 8-bit RGB PNG.", parameters: {} },
              ],
              candidates: [],
              selected: null,
            },
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const ocr = await screen.findByRole("region", { name: "Text in image (OCR)" });
    expect(within(ocr).getByText("VESTIGO EVIDENCE SAMPLE 2026")).toBeInTheDocument();
    expect(within(ocr).getByText(/Tesseract confidence 91%/)).toBeInTheDocument();
    expect(within(ocr).getByText("Converted to an 8-bit RGB PNG.")).toBeInTheDocument();
    expect(within(ocr).queryByText(/^Used:/)).not.toBeInTheDocument();
    expect(within(ocr).queryByText("Cleaned text")).not.toBeInTheDocument();
  });

  it("renders the duplicate section", async () => {
    renderApp(PAGE);

    const duplicates = await screen.findByRole("region", { name: "Duplicate search (local library)" });
    expect(within(duplicates).getByRole("link", { name: "harbour-copy.jpg" })).toHaveAttribute(
      "href",
      `/artifacts/${OTHER_ARTIFACT_ID}`,
    );
    expect(within(duplicates).getByText(/Same file \(identical bytes\)/)).toBeInTheDocument();
    expect(within(duplicates).getByText(/Threshold: Hamming distance ≤ 10 of 64 bits/)).toBeInTheDocument();
  });

  it("shows a resized, recompressed copy as a near match", async () => {
    const base = evidenceReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            duplicates: {
              ...base.duplicates!,
              matches: [
                {
                  artifact_id: OTHER_ARTIFACT_ID,
                  filename: "harbour-resized-q60.jpg",
                  available: true,
                  media_type: "image",
                  similarity: 0.9531,
                  distance: 3,
                  match_type: "near",
                  matched_frame_count: null,
                  frame_matches: null,
                },
              ],
            },
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const duplicates = await screen.findByRole("region", { name: "Duplicate search (local library)" });
    expect(within(duplicates).getByRole("link", { name: "harbour-resized-q60.jpg" })).toHaveAttribute(
      "href",
      `/artifacts/${OTHER_ARTIFACT_ID}`,
    );
    expect(within(duplicates).getByText(/Similar · distance 3\/64 · similarity 95%/)).toBeInTheDocument();
    expect(within(duplicates).queryByText(/No match among/)).not.toBeInTheDocument();
  });

  it("says an empty duplicate result covers only the library as it was when the analysis ran", async () => {
    const base = evidenceReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({ duplicates: { ...base.duplicates!, library_size: 0, compared: 0, matches: [] } }),
        ),
      ),
    );
    renderApp(PAGE);

    const duplicates = await screen.findByRole("region", { name: "Duplicate search (local library)" });
    expect(
      within(duplicates).getByText(/No match among the 0 other artifacts that were in the local library when this analysis ran/),
    ).toBeInTheDocument();
    expect(within(duplicates).getByText(/Images added later are not included/)).toBeInTheDocument();
    expect(within(duplicates).getByText(/Run the analysis again to search the current library/)).toBeInTheDocument();
  });

  it("describes pre-M4 C2PA records as detection only", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            c2pa: c2paSection({
              present: true,
              validation_performed: false,
              manifest_labels: ["contentauth:urn:uuid:1234"],
              details: {
                manifests: [
                  {
                    label: "contentauth:urn:uuid:1234",
                    jumbf_type: "(c2ma)",
                    claim: { Claim_generator: "make_test_images/0.16.1" },
                    assertions: ["c2pa.actions"],
                    assertion_data: {},
                    signature_present: true,
                  },
                ],
                active_manifest_label: "contentauth:urn:uuid:1234",
              },
              status: null,
              manifest_count: null,
              validation_codes: null,
              validator: null,
            }),
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const c2pa = await screen.findByRole("region", { name: "Content Credentials (C2PA)" });
    expect(within(c2pa).getByText(/manifest was found in the file/)).toBeInTheDocument();
    expect(within(c2pa).getByText(/not proof that the content is authentic/)).toBeInTheDocument();
    expect(within(c2pa).getByText(/Run the analysis again to validate/)).toBeInTheDocument();
    expect(within(c2pa).getByText("present (not checked)")).toBeInTheDocument();
    expect(within(c2pa).getByText("make_test_images/0.16.1")).toBeInTheDocument();
  });

  it("shows provenance, limitations, failures, and skip reasons", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            ocr: {
              engine: "tesseract",
              languages: ["eng"],
              text: "",
              cleaned_text: null,
              cleaning: [],
              confidence: null,
              word_count: 0,
              preprocessing: [],
              candidates: [],
              selected: null,
              provenance: provenance("ocr", {
                status: "skipped",
                tool_version: null,
                skip_reason: "Disabled by the analysis option 'ocr'.",
              }),
            },
            hashes: {
              sha256: null,
              md5: null,
              matches_upload_record: null,
              provenance: provenance("hashes", {
                status: "failed",
                errors: [{ type: "INTEGRITY_MISMATCH", message: "The stored file no longer matches." }],
              }),
            },
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const ocr = await screen.findByRole("region", { name: "Text in image (OCR)" });
    expect(within(ocr).getByText("Skipped")).toBeInTheDocument();
    expect(within(ocr).getByText(/Disabled by the analysis option 'ocr'/)).toBeInTheDocument();

    const hashes = section("File hashes");
    expect(within(hashes).getByText("Failed")).toBeInTheDocument();
    expect(within(hashes).getByText("This check failed:")).toBeInTheDocument();
    expect(within(hashes).getByText(/The stored file no longer matches/)).toBeInTheDocument();

    const metadata = section("Embedded metadata");
    expect(within(metadata).getByText(/ExifTool 13.25/)).toBeInTheDocument();
    expect(within(metadata).getByText("Limitation of metadata.")).toBeInTheDocument();
    expect(within(metadata).getByText(/Observed — read directly from the file/)).toBeInTheDocument();
  });

  it("lets the analyst change the review state", async () => {
    let received: unknown = null;
    server.use(
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/review`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json(
          artifactDetail({
            review_state: "FLAGGED",
            review: { state: "FLAGGED", analyst_notes: "Check the source.", updated_at: "2026-11-02T10:00:00Z" },
          }),
        );
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    await user.selectOptions(await screen.findByLabelText("Review state"), "FLAGGED");
    await user.type(screen.getByLabelText("Analyst notes"), "Check the source.");
    await user.click(screen.getByRole("button", { name: "Save review" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Saved");
    expect(received).toEqual({
      state: "FLAGGED",
      analyst_notes: "Check the source.",
      expected_updated_at: "2026-11-02T09:00:00.000000Z",
    });
    expect(screen.getByText(/review: Flagged/)).toBeInTheDocument();
  });

  it("shows an error message when the report cannot be loaded", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        apiError(500, "INTERNAL_ERROR", "An internal error occurred."),
      ),
    );
    renderApp(PAGE);

    expect(await screen.findByRole("alert")).toHaveTextContent("An internal error occurred.");
  });

  it("shows a message for an unknown artifact", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => apiError(404, "ARTIFACT_NOT_FOUND", "Artifact not found.")),
    );
    renderApp(PAGE);

    expect(await screen.findByRole("alert")).toHaveTextContent("This artifact does not exist.");
  });

  it("polls a running analysis and then shows the result", async () => {
    let polls = 0;
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () =>
        HttpResponse.json(
          polls < 2
            ? artifactDetail({
                latest_job_status: "running",
                latest_job: { job_id: JOB_ID, status: "running", created_at: "", started_at: "", completed_at: null },
              })
            : artifactDetail(),
        ),
      ),
      http.get(`${API}/analysis/jobs/${JOB_ID}`, () => {
        polls += 1;
        return HttpResponse.json(
          polls < 2
            ? jobStatus("running", ["succeeded", "succeeded", "running"])
            : { ...jobStatus("completed", Array(6).fill("succeeded")), completed_at: "2026-11-02T09:00:05Z" },
        );
      }),
    );
    renderApp(PAGE);

    const progress = await screen.findByRole("region", { name: "Analysis progress" });
    expect(within(progress).getByText("Content Credentials (C2PA)")).toBeInTheDocument();
    expect(within(progress).getAllByText("Done")).toHaveLength(2);
    expect(within(progress).getAllByText("Running")).toHaveLength(2); // the job and its current stage

    expect(await screen.findByRole("region", { name: "File hashes" }, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Analysis progress" })).not.toBeInTheDocument();
  });

  it("asks for confirmation before deleting, then deletes", async () => {
    let deleted = false;
    server.use(
      http.delete(`${API}/artifacts/${ARTIFACT_ID}`, () => {
        deleted = true;
        return HttpResponse.json({
          artifact_id: ARTIFACT_ID,
          original_files: 1,
          derived_files: 3,
          jobs: 1,
          evidence_records: 6,
        });
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    await user.click(await screen.findByRole("button", { name: "Delete artifact" }));
    const dialog = screen.getByRole("dialog", { name: "Delete “harbour.jpg”?" });
    expect(within(dialog).getByText("This cannot be undone.")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(deleted).toBe(false);

    await user.click(screen.getByRole("button", { name: "Delete artifact" }));
    await user.click(screen.getByRole("button", { name: "Delete permanently" }));

    expect(await screen.findByRole("heading", { name: "Library" })).toBeInTheDocument();
    expect(screen.getByText("Deleted “harbour.jpg” and all of its evidence.")).toBeInTheDocument();
    expect(deleted).toBe(true);
  });

  it("links the evidence download to the report's job", async () => {
    renderApp(PAGE);

    const link = await screen.findByRole("link", { name: "Download JSON report" });
    expect(link).toHaveAttribute("href", `${API}/artifacts/${ARTIFACT_ID}/evidence?job_id=${JOB_ID}&download=true`);
  });
});
