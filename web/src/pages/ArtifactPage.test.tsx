import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { ARTIFACT_ID, JOB_ID, OTHER_ARTIFACT_ID, artifactDetail, evidenceReport, jobStatus, provenance } from "../test/data";
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

  it("describes C2PA results as detection only", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            c2pa: {
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
              provenance: provenance("c2pa"),
            },
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const c2pa = await screen.findByRole("region", { name: "Content Credentials (C2PA)" });
    expect(within(c2pa).getByText(/manifest was found in the file/)).toBeInTheDocument();
    expect(within(c2pa).getByText(/not proof that the content is authentic/)).toBeInTheDocument();
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
              confidence: null,
              word_count: 0,
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
    expect(received).toEqual({ state: "FLAGGED", analyst_notes: "Check the source." });
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

    expect(await screen.findByRole("heading", { name: "Analyse an image" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Deleted “harbour.jpg” and all of its evidence.");
    expect(deleted).toBe(true);
  });

  it("links the evidence download to the report's job", async () => {
    renderApp(PAGE);

    const link = await screen.findByRole("link", { name: "Download evidence (JSON)" });
    expect(link).toHaveAttribute("href", `${API}/artifacts/${ARTIFACT_ID}/evidence?job_id=${JOB_ID}&download=true`);
  });
});
