import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { AnalysisOptions } from "../api/types";
import { ARTIFACT_ID, JOB_ID } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

function imageFile(name = "harbour.jpg", type = "image/jpeg") {
  return new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], name, { type });
}

describe("UploadPage", () => {
  it("accepts an image and enables upload", async () => {
    const user = userEvent.setup();
    renderApp("/upload");

    const submit = screen.getByRole("button", { name: "Upload and analyse" });
    expect(submit).toBeDisabled();

    await user.upload(screen.getByLabelText(/choose an image/i), imageFile());

    expect(screen.getByText("harbour.jpg")).toBeInTheDocument();
    expect(submit).toBeEnabled();
  });

  it("rejects unsupported files before uploading", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/upload");

    await user.upload(screen.getByLabelText(/choose an image/i), imageFile("notes.txt", "text/plain"));

    expect(screen.getByRole("alert")).toHaveTextContent("Only JPEG, PNG, WebP, and TIFF images are supported.");
    expect(screen.getByRole("button", { name: "Upload and analyse" })).toBeDisabled();
  });

  it("uploads, starts analysis with the chosen options, and opens the artifact", async () => {
    let sentOptions: AnalysisOptions | null = null;
    server.use(
      http.post(`${API}/artifacts/upload`, () =>
        HttpResponse.json(
          {
            artifact_id: ARTIFACT_ID,
            filename: "harbour.jpg",
            size_bytes: 4,
            media_type: "image",
            mime_type: "image/jpeg",
            sha256: "a".repeat(64),
            created_at: "2026-11-02T09:00:00Z",
          },
          { status: 201 },
        ),
      ),
      http.post(`${API}/analysis/image`, async ({ request }) => {
        sentOptions = ((await request.json()) as { options: AnalysisOptions }).options;
        return HttpResponse.json({ job_id: JOB_ID, artifact_id: ARTIFACT_ID, status: "queued" }, { status: 202 });
      }),
    );
    const user = userEvent.setup();
    renderApp("/upload");

    await user.upload(screen.getByLabelText(/choose an image/i), imageFile());
    await user.click(screen.getByLabelText(/text in image/i));
    await user.click(screen.getByRole("button", { name: "Upload and analyse" }));

    expect(await screen.findByRole("heading", { name: "harbour.jpg" })).toBeInTheDocument();
    expect(sentOptions).toEqual({ metadata: true, c2pa: true, ocr: false, duplicate_search: true });
  });

  it("shows the backend's error message when the upload is rejected", async () => {
    server.use(
      http.post(`${API}/artifacts/upload`, () =>
        apiError(415, "UNSUPPORTED_MEDIA_TYPE", "Only JPEG, PNG, WebP, and TIFF images are supported in Milestone 1."),
      ),
    );
    const user = userEvent.setup();
    renderApp("/upload");

    await user.upload(screen.getByLabelText(/choose an image/i), imageFile());
    await user.click(screen.getByRole("button", { name: "Upload and analyse" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only JPEG, PNG, WebP, and TIFF images are supported in Milestone 1.",
    );
    expect(screen.getByRole("button", { name: "Upload and analyse" })).toBeEnabled();
  });

  it("lists recent uploads", async () => {
    server.use(
      http.get(`${API}/artifacts`, () =>
        HttpResponse.json({
          items: [
            {
              artifact_id: ARTIFACT_ID,
              filename: "harbour.jpg",
              media_type: "image",
              mime_type: "image/jpeg",
              size_bytes: 2048,
              created_at: "2026-11-02T09:00:00Z",
              review_state: "FLAGGED",
              latest_job_status: "completed",
            },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        }),
      ),
    );
    renderApp("/upload");

    expect(await screen.findByRole("link", { name: "harbour.jpg" })).toHaveAttribute("href", `/artifacts/${ARTIFACT_ID}`);
    expect(screen.getByText("Flagged")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
  });

  it("states that the system does not decide authenticity", () => {
    renderApp("/upload");
    expect(screen.getByText(/does not determine whether media is authentic/i)).toBeInTheDocument();
  });
});
