import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { ARTIFACT_ID, JOB_ID, artifactDetail, evidenceReport, health, jobHistoryItem, provenance } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;
const OLD_JOB = "job_44444444444444444444444444444444";

describe("Problems summary", () => {
  it("lists failed and partial checks with their first error, linking to the section", async () => {
    const base = evidenceReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            ocr: {
              ...base.ocr!,
              provenance: provenance("ocr", {
                status: "failed",
                errors: [{ type: "TOOL_TIMEOUT", message: "tesseract did not finish within 120 seconds." }],
              }),
            },
            metadata: {
              ...base.metadata!,
              provenance: provenance("metadata", {
                status: "partial",
                errors: [
                  { type: "EXIFTOOL_WARNING", message: "Bad IFD0 directory." },
                  { type: "EXIFTOOL_WARNING", message: "Second warning." },
                ],
              }),
            },
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const summary = await screen.findByRole("region", { name: "Problems in this analysis" });
    expect(summary).toHaveTextContent("2 problems in this analysis");
    expect(within(summary).getByRole("link", { name: "Text in image (OCR)" })).toHaveAttribute("href", "#section-ocr");
    expect(summary).toHaveTextContent("tesseract did not finish within 120 seconds. (TOOL_TIMEOUT)");
    expect(within(summary).getByRole("link", { name: "Embedded metadata" })).toHaveAttribute("href", "#section-metadata");
    expect(summary).toHaveTextContent("Bad IFD0 directory. (EXIFTOOL_WARNING) and 1 more");
    expect(document.getElementById("section-ocr")).toHaveAccessibleName("Text in image (OCR)");
  });

  it("is not shown when every check succeeded", async () => {
    renderApp(PAGE);
    await screen.findByRole("region", { name: "File hashes" });
    expect(screen.queryByRole("region", { name: "Problems in this analysis" })).not.toBeInTheDocument();
  });

  it("explains a job that stopped", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/jobs`, () =>
        HttpResponse.json({
          artifact_id: ARTIFACT_ID,
          jobs: [
            jobHistoryItem({
              status: "failed",
              problem_count: 1,
              error: {
                code: "INTERRUPTED",
                message: "The service restarted while this analysis was running. Run it again.",
                details: {},
              },
            }),
          ],
        }),
      ),
    );
    renderApp(PAGE);

    const summary = await screen.findByRole("region", { name: "Problems in this analysis" });
    expect(summary).toHaveTextContent(
      "The analysis stopped: The service restarted while this analysis was running. Run it again. (INTERRUPTED)",
    );
    const history = screen.getByRole("region", { name: "Analysis history" });
    expect(history).toHaveTextContent("(INTERRUPTED)");
    expect(within(history).getByText("1 problem")).toBeInTheDocument();
  });
});

describe("Analysis history", () => {
  it("opens an earlier analysis and returns to the latest", async () => {
    const requestedJobs: (string | null)[] = [];
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/jobs`, () =>
        HttpResponse.json({
          artifact_id: ARTIFACT_ID,
          jobs: [
            jobHistoryItem(),
            jobHistoryItem({ job_id: OLD_JOB, created_at: "2026-11-01T09:00:00Z", status: "completed_with_errors", problem_count: 2 }),
          ],
        }),
      ),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, ({ request }) => {
        const jobId = new URL(request.url).searchParams.get("job_id");
        requestedJobs.push(jobId);
        const report = evidenceReport({ job_id: jobId ?? JOB_ID });
        if (jobId === OLD_JOB) report.job = { ...report.job, job_id: OLD_JOB, created_at: "2026-11-01T09:00:00Z" };
        return HttpResponse.json(report);
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const history = await screen.findByRole("region", { name: "Analysis history" });
    await within(history).findByText("Shown below"); // once the latest report has loaded
    const [latest, earlier] = within(history).getAllByRole("listitem");
    expect(latest).toHaveTextContent("latest");
    expect(latest).toHaveTextContent("Shown below");
    expect(earlier).toHaveTextContent("2 problems");

    await user.click(within(earlier).getByRole("button", { name: "View this analysis" }));
    expect(await screen.findByText(/You are viewing an earlier analysis/)).toBeInTheDocument();
    expect(requestedJobs.at(-1)).toBe(OLD_JOB);

    await user.click(screen.getByRole("button", { name: "View the latest analysis" }));
    await waitFor(() => expect(screen.queryByText(/You are viewing an earlier analysis/)).not.toBeInTheDocument());
    expect(requestedJobs.at(-1)).toBe(JOB_ID);
  });
});

describe("Load errors", () => {
  it("shows the error code and retries", async () => {
    let calls = 0;
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => {
        calls += 1;
        return calls === 1
          ? apiError(500, "INTERNAL_ERROR", "Something went wrong on the server.")
          : HttpResponse.json(artifactDetail());
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This artifact could not be loaded.");
    expect(alert).toHaveTextContent("Error code: INTERNAL_ERROR");
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "harbour.jpg" })).toBeInTheDocument();
  });
});

describe("Health banner", () => {
  it("is hidden when everything is available", async () => {
    renderApp("/");
    await screen.findByRole("heading", { name: "Library" });
    expect(screen.queryByRole("alert", { name: "Service status" })).not.toBeInTheDocument();
  });

  it("explains missing Milestone 1 tools but not video tools", async () => {
    const missing = { status: "missing" as const, version: null, used_in: "x", languages: null, detail: null };
    server.use(
      http.get(`${API}/health`, () =>
        HttpResponse.json(health({ status: "degraded", tools: { ...health().tools, tesseract: missing, ffmpeg: missing } })),
      ),
    );
    renderApp("/");

    const banner = await screen.findByRole("alert", { name: "Service status" });
    expect(banner).toHaveTextContent("tesseract is not installed: OCR will be recorded as failed.");
    expect(banner).not.toHaveTextContent("ffmpeg");
  });

  it("reports a database failure (HTTP 503)", async () => {
    server.use(http.get(`${API}/health`, () => HttpResponse.json(health({ status: "error", database: "error" }), { status: 503 })));
    renderApp("/");
    expect(await screen.findByRole("alert", { name: "Service status" })).toHaveTextContent(
      "The database is unavailable or at the wrong schema version.",
    );
  });

  it("reports an unreachable backend", async () => {
    server.use(http.get(`${API}/health`, () => HttpResponse.error()));
    renderApp("/");
    expect(await screen.findByRole("alert", { name: "Service status" })).toHaveTextContent(
      "The Vestigo backend cannot be reached. Check that it is running on port 8400.",
    );
  });
});
