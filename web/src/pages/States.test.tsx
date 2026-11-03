import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { ARTIFACT_ID, JOB_ID, artifactDetail, artifactList, jobStatus, listItem } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

describe("Empty and loading states", () => {
  it("offers to analyse an artifact that has not been analysed", async () => {
    let body: unknown = null;
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () =>
        HttpResponse.json(
          artifactDetail({
            latest_job: null,
            latest_job_status: null,
            problem_count: null,
            duplicate_match_count: null,
            added_since_analysis: null,
          }),
        ),
      ),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/jobs`, () => HttpResponse.json({ artifact_id: ARTIFACT_ID, jobs: [] })),
      http.post(`${API}/analysis/image`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ job_id: JOB_ID, artifact_id: ARTIFACT_ID, status: "queued" }, { status: 202 });
      }),
      http.get(`${API}/analysis/jobs/${JOB_ID}`, () => HttpResponse.json(jobStatus("running", ["running"]))),
    );
    const user = userEvent.setup();
    renderApp(`/artifacts/${ARTIFACT_ID}`);

    const empty = (await screen.findByText("This image has not been analysed yet")).parentElement!;
    expect(empty).toHaveTextContent("Analysis uses the default checks from Settings.");
    expect(screen.queryByRole("region", { name: "Export evidence" })).not.toBeInTheDocument();
    await user.click(within(empty).getByRole("button", { name: "Run analysis" }));
    await waitFor(() => expect(body).toEqual({ artifact_id: ARTIFACT_ID }));
  });

  it("shows recent uploads with loading, error, and retry", async () => {
    let calls = 0;
    server.use(
      http.get(`${API}/artifacts`, () => {
        calls += 1;
        return calls === 1
          ? apiError(503, "HTTP_ERROR", "The backend responded with status 503.")
          : HttpResponse.json(artifactList([listItem({ filename: "recent.jpg" })]));
      }),
    );
    const user = userEvent.setup();
    renderApp("/upload");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Recent uploads could not be loaded.");
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "recent.jpg" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View the Library" })).toHaveAttribute("href", "/");
  });
});
