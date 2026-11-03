import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { ARTIFACT_ID, JOB_ID, artifactDetail, evidenceReport, jobStatus } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

describe("Duplicate-library control", () => {
  it("excludes and re-includes the artifact for future searches", async () => {
    const sent: unknown[] = [];
    server.use(
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/duplicate-library`, async ({ request }) => {
        const body = (await request.json()) as { included: boolean };
        sent.push(body);
        return HttpResponse.json(artifactDetail({ in_duplicate_library: body.included }));
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const control = await screen.findByRole("region", { name: "Duplicate search library" });
    expect(control).toHaveTextContent("Included: future duplicate searches of other images compare against this one.");
    expect(control).toHaveTextContent("Evidence already recorded is not changed.");

    await user.click(within(control).getByRole("button", { name: "Exclude from future searches" }));
    expect(await within(control).findByText(/Excluded: future duplicate searches of other images skip this one/)).toBeInTheDocument();
    await user.click(within(control).getByRole("button", { name: "Include in future searches" }));
    expect(await within(control).findByText(/^Included:/)).toBeInTheDocument();
    expect(sent).toEqual([{ included: false }, { included: true }]);
  });

  it("shows an error if the change fails", async () => {
    server.use(
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/duplicate-library`, () =>
        apiError(404, "ARTIFACT_NOT_FOUND", "Artifact not found."),
      ),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const control = await screen.findByRole("region", { name: "Duplicate search library" });
    await user.click(within(control).getByRole("button", { name: "Exclude from future searches" }));
    expect(await within(control).findByRole("alert")).toHaveTextContent("Artifact not found.");
  });
});

describe("Duplicates panel", () => {
  it("says how many artifacts were added since the search, and re-runs the analysis", async () => {
    let started = false;
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(artifactDetail({ added_since_analysis: 2 }))),
      http.post(`${API}/analysis/image`, () => {
        started = true;
        return HttpResponse.json({ job_id: JOB_ID, artifact_id: ARTIFACT_ID, status: "queued" }, { status: 202 });
      }),
      http.get(`${API}/analysis/jobs/${JOB_ID}`, () => HttpResponse.json(jobStatus("running", ["succeeded", "running"]))),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Duplicate search (local library)" });
    expect(panel).toHaveTextContent("2 artifacts were added to the library after this search and were not compared.");
    await user.click(within(panel).getByRole("button", { name: "Run analysis again" }));
    await waitFor(() => expect(started).toBe(true));
  });

  it("shows no hint when nothing was added, and reports excluded artifacts", async () => {
    const base = evidenceReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(evidenceReport({ duplicates: { ...base.duplicates!, excluded_count: 3 } })),
      ),
    );
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Duplicate search (local library)" });
    expect(panel).toHaveTextContent("3 excluded from duplicate search and not compared.");
    expect(panel).not.toHaveTextContent("added to the library after this search");
  });
});
