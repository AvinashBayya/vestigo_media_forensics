import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { ExternalLeadCreate, ExternalLeadUpdate } from "../api/types";
import {
  ARTIFACT_ID,
  DERIVED_KF_1,
  DERIVED_KF_2,
  JOB_ID,
  jobHistoryItem,
  LEADS_NOTICE,
  artifactDetail,
  externalLead,
  searchProviders,
  videoDetail,
  videoReport,
} from "../test/data";
import { renderApp } from "../test/render";
import { API, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

async function findPanel() {
  const panel = await screen.findByRole("region", { name: "Reverse-image search (external)" });
  await within(panel).findByRole("heading", { name: "Providers" }); // loaded, not the spinner
  return panel;
}

function serveLeads(leads = [externalLead()]) {
  server.use(
    http.get(`${API}/artifacts/${ARTIFACT_ID}/external-leads`, () =>
      HttpResponse.json({ artifact_id: ARTIFACT_ID, notice: LEADS_NOTICE, leads }),
    ),
  );
}

describe("Reverse-image search panel", () => {
  it("shows the sharing warning and gates providers on their Settings toggle", async () => {
    server.use(http.get(`${API}/search/providers`, () => HttpResponse.json(searchProviders(["tineye"]))));
    renderApp(PAGE);

    const panel = await findPanel();
    expect(panel).toHaveTextContent("sharing that media with the external service");
    expect(panel).toHaveTextContent("Vestigo cannot observe or record what happens after a provider page opens");

    const open = within(panel).getByRole("link", { name: "Open TinEye" });
    expect(open).toHaveAttribute("href", "https://tineye.com/"); // plain landing page, no parameters
    expect(open).toHaveAttribute("target", "_blank");
    expect(open).toHaveAttribute("rel", "noopener noreferrer");

    expect(within(panel).queryByRole("link", { name: "Open Google Lens" })).not.toBeInTheDocument();
    expect(panel).toHaveTextContent("Google Lens — enable in Settings");

    const download = within(panel).getByRole("link", { name: "Download original image" });
    expect(download).toHaveAttribute("href", `/api/v1/artifacts/${ARTIFACT_ID}/content?download=true`);
  });

  it("offers only real keyframes as video subjects and records the selected one", async () => {
    let posted: ExternalLeadCreate | null = null;
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () =>
        HttpResponse.json(videoDetail({ has_playable_preview: true })),
      ),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () => HttpResponse.json(videoReport())),
      http.post(`${API}/artifacts/${ARTIFACT_ID}/external-leads`, async ({ request }) => {
        posted = (await request.json()) as ExternalLeadCreate;
        return HttpResponse.json(externalLead({ derived_file_id: posted.derived_file_id ?? null }), {
          status: 201,
        });
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    const subjects = within(panel).getByRole("group", { name: /Search subject/ });
    const options = within(subjects).getAllByRole("radio");
    expect(options).toHaveLength(2); // exactly the analysis's keyframes - the preview is never offered
    expect(panel).not.toHaveTextContent(/preview/i);

    // The lead cannot be recorded until the searched keyframe is chosen.
    const record = within(panel).getByRole("button", { name: "Record lead" });
    expect(record).toBeDisabled();
    expect(panel).toHaveTextContent("Select the searched keyframe first.");

    await user.click(within(subjects).getByRole("radio", { name: /Keyframe 2/ }));
    const download = within(panel).getByRole("link", { name: "Download selected keyframe" });
    expect(download).toHaveAttribute(
      "href",
      `/api/v1/artifacts/${ARTIFACT_ID}/derived/${DERIVED_KF_2}/content?download=true`,
    );

    const form = within(panel).getByRole("form", { name: "Record an external lead" });
    await user.type(within(form).getByLabelText("Provider"), "TinEye");
    await user.type(within(form).getByLabelText("Result page URL"), "https://example.org/results/42");
    await user.type(
      within(form).getByLabelText(/Publication date as shown on the page/),
      "around 2019, per page footer",
    );
    await user.click(record);

    expect(posted).toEqual({
      provider: "TinEye",
      result_url: "https://example.org/results/42",
      claimed_published_at: "around 2019, per page footer",
      derived_file_id: DERIVED_KF_2,
    });
    expect(DERIVED_KF_1).not.toBe(DERIVED_KF_2);
  });

  it("shows leads with honest labels and the recorded-vs-claimed separation", async () => {
    serveLeads([
      externalLead({
        image_url: "https://example.org/image.jpg",
        claimed_published_at: "2019-05-01 (page claim)",
        notes: "Found on a news site.",
      }),
    ]);
    renderApp(PAGE);

    const panel = await findPanel();
    const list = await within(panel).findByRole("list", { name: "External leads" });
    const row = within(list).getAllByRole("listitem")[0];
    expect(row).toHaveTextContent("EXTERNAL");
    expect(row).toHaveTextContent("TinEye");
    expect(row).toHaveTextContent("Recorded");
    expect(row).toHaveTextContent("Publication date (analyst-reported, unverified): 2019-05-01 (page claim)");
    expect(panel).toHaveTextContent("never proof of the original source");
    expect(within(row).getByRole("link", { name: "https://example.org/results/42" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
  });

  it("updates review state and deletes a lead after confirmation", async () => {
    let patched: ExternalLeadUpdate | null = null;
    let deleted = false;
    serveLeads();
    server.use(
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/external-leads/:leadId`, async ({ request }) => {
        patched = (await request.json()) as ExternalLeadUpdate;
        return HttpResponse.json(externalLead({ review_state: "REVIEWED" }));
      }),
      http.delete(`${API}/artifacts/${ARTIFACT_ID}/external-leads/:leadId`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    const list = await within(panel).findByRole("list", { name: "External leads" });
    await user.selectOptions(within(list).getByRole("combobox", { name: "Review:" }), "REVIEWED");
    expect(patched).toEqual({ review_state: "REVIEWED" });

    await user.click(within(list).getByRole("button", { name: "Delete lead" }));
    expect(deleted).toBe(false); // first click only asks
    await user.click(within(list).getByRole("button", { name: "Confirm delete" }));
    expect(deleted).toBe(true);
  });

  it("is absent for audio artifacts", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () =>
        HttpResponse.json(
          artifactDetail({ filename: "tone.wav", media_type: "audio", mime_type: "audio/wav" }),
        ),
      ),
    );
    renderApp(PAGE);

    await screen.findByRole("region", { name: "Chain of custody" });
    expect(
      screen.queryByRole("region", { name: "Reverse-image search (external)" }),
    ).not.toBeInTheDocument();
  });
});

describe("Reverse-image search panel integration", () => {
  it("refreshes the chain of custody after a lead is recorded", async () => {
    let custodyCalls = 0;
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/custody`, () => {
        custodyCalls += 1;
        return HttpResponse.json({ artifact_id: ARTIFACT_ID, notice: "n", events: [], derived_files: [] });
      }),
      http.post(`${API}/artifacts/${ARTIFACT_ID}/external-leads`, () =>
        HttpResponse.json(externalLead(), { status: 201 }),
      ),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    const before = custodyCalls;
    const form = within(panel).getByRole("form", { name: "Record an external lead" });
    await user.type(within(form).getByLabelText("Provider"), "TinEye");
    await user.type(within(form).getByLabelText("Result page URL"), "https://example.org/results/42");
    await user.click(within(form).getByRole("button", { name: "Record lead" }));

    // The custody panel refetches, so the new lead_recorded event can appear.
    await waitFor(() => expect(custodyCalls).toBeGreaterThan(before));
  });

  it("drops a selected keyframe that is not in the viewed analysis", async () => {
    const OLD_JOB = "job_55555555555555555555555555555555";
    const base = videoReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(videoDetail())),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/jobs`, () =>
        HttpResponse.json({
          artifact_id: ARTIFACT_ID,
          jobs: [
            jobHistoryItem({ pipeline: "video.v1" }),
            jobHistoryItem({ job_id: OLD_JOB, created_at: "2026-11-03T09:00:00Z", pipeline: "video.v1" }),
          ],
        }),
      ),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, ({ request }) => {
        const jobId = new URL(request.url).searchParams.get("job_id") ?? JOB_ID;
        if (jobId !== OLD_JOB) return HttpResponse.json(videoReport());
        // The earlier analysis has a different keyframe set.
        const report = videoReport({
          job_id: OLD_JOB,
          keyframes: {
            ...base.keyframes!,
            frames: [
              {
                seq: 1,
                timestamp: 0,
                reason: "first_frame",
                scene_score: null,
                derived_file_id: "df_" + "f".repeat(32),
                width: 640,
                height: 360,
              },
            ],
            extracted: 1,
            requested: 1,
          },
        });
        report.job = { ...report.job, job_id: OLD_JOB };
        return HttpResponse.json(report);
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    const subjects = within(panel).getByRole("group", { name: /Search subject/ });
    await user.click(within(subjects).getByRole("radio", { name: /Keyframe 2/ }));
    expect(within(panel).getByRole("button", { name: "Record lead" })).toBeEnabled();

    // View the earlier analysis: its keyframes don't include the selection, so it self-heals.
    const history = screen.getByRole("region", { name: "Analysis history" });
    await user.click(within(history).getByRole("button", { name: "View this analysis" }));

    const switched = await screen.findByRole("region", { name: "Reverse-image search (external)" });
    const record = await within(switched).findByRole("button", { name: "Record lead" });
    expect(record).toBeDisabled();
    expect(switched).toHaveTextContent("Select the searched keyframe first.");
    for (const radio of within(switched).getAllByRole("radio")) {
      expect(radio).not.toBeChecked();
    }
  });
});
