import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { AIDraft, Transcript } from "../api/types";
import {
  AI_LABEL,
  ARTIFACT_ID,
  DRAFTS_NOTICE,
  TRANSCRIPTS_NOTICE,
  aiDraft,
  aiStatus,
  artifactDetail,
  transcript,
  videoDetail,
  videoReport,
} from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

async function findPanel() {
  const panel = await screen.findByRole("region", { name: "AI assistant (drafts, not evidence)" });
  await within(panel).findByRole("form", { name: "Ask for a draft" });
  return panel;
}

function serveDrafts(drafts: AIDraft[], enabled = true) {
  server.use(
    http.get(`${API}/ai/status`, () =>
      HttpResponse.json(
        aiStatus({
          runtime_installed: enabled,
          ai_enabled: enabled,
          drafts_available: enabled,
          drafts_unavailable_reason: enabled ? null : "Local AI is turned off.",
        }),
      ),
    ),
    http.get(`${API}/ai/artifacts/${ARTIFACT_ID}/drafts`, () =>
      HttpResponse.json({ artifact_id: ARTIFACT_ID, notice: DRAFTS_NOTICE, label: AI_LABEL, drafts }),
    ),
  );
}

function serveTranscripts(transcripts: Transcript[], enabled = true) {
  server.use(
    http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(videoDetail())),
    http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () => HttpResponse.json(videoReport())),
    http.get(`${API}/ai/status`, () =>
      HttpResponse.json(
        aiStatus({
          runtime_installed: enabled,
          transcription_enabled: enabled,
          transcription_available: enabled,
          transcription_unavailable_reason: enabled ? null : "Transcription is turned off.",
        }),
      ),
    ),
    http.get(`${API}/ai/artifacts/${ARTIFACT_ID}/transcripts`, () =>
      HttpResponse.json({ artifact_id: ARTIFACT_ID, notice: TRANSCRIPTS_NOTICE, transcripts }),
    ),
  );
}

describe("AI assistant panel", () => {
  it("labels everything as unverified draft output, never evidence", async () => {
    serveDrafts([], false);
    renderApp(PAGE);

    const panel = await findPanel();
    expect(panel).toHaveTextContent(AI_LABEL);
    expect(panel).toHaveTextContent("kept apart from the evidence");
    expect(panel).toHaveTextContent("never a finding");
    expect(panel).toHaveTextContent("nothing is written back onto metadata or evidence");
    expect(panel).toHaveTextContent("Vendor telemetry is disabled.");
    // Off by default: the reason is shown and the action is disabled.
    expect(panel).toHaveTextContent("Local AI is turned off.");
    expect(within(panel).getByRole("button", { name: "Ask the local model" })).toBeDisabled();
  });

  it("shows the model's value and only its own confidence", async () => {
    serveDrafts([aiDraft()]);
    renderApp(PAGE);

    const panel = await findPanel();
    const fields = within(panel).getByRole("list", { name: /Fields proposed in/ });
    const rows = within(fields).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("city");
    expect(rows[0]).toHaveTextContent("Testville");
    expect(rows[0]).toHaveTextContent("model's own confidence 72%");
    // No confidence from the model means none is shown or invented.
    expect(rows[1]).toHaveTextContent("no confidence given by the model");
    expect(panel).toHaveTextContent("needle3 · v3 · 2-bit · Apache-2.0");
    expect(panel).toHaveTextContent("The model's stated reasoning (not a finding)");
  });

  it("accepts, edits, and rejects one field at a time", async () => {
    const sent: unknown[] = [];
    serveDrafts([aiDraft()]);
    server.use(
      http.patch(`${API}/ai/artifacts/${ARTIFACT_ID}/drafts/:draftId`, async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json(aiDraft());
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    const fields = within(panel).getByRole("list", { name: /Fields proposed in/ });
    const [city, date] = within(fields).getAllByRole("listitem");

    await user.click(within(city).getByRole("button", { name: "Accept" }));
    await user.click(within(date).getByRole("button", { name: "Reject" }));
    await user.click(within(city).getByRole("button", { name: "Edit" }));
    const box = within(city).getByRole("textbox");
    await user.clear(box);
    await user.type(box, "Harbourtown");
    await user.click(within(city).getByRole("button", { name: "Save my version" }));

    await waitFor(() => expect(sent).toHaveLength(3));
    expect(sent[0]).toEqual({ field: "city", action: "accepted" });
    expect(sent[1]).toEqual({ field: "date", action: "rejected" });
    expect(sent[2]).toEqual({ field: "city", action: "edited", value: "Harbourtown" });
  });

  it("keeps the model's value beside an analyst edit", async () => {
    serveDrafts([
      aiDraft({
        fields: [
          {
            name: "city",
            value: "Testville",
            confidence: null,
            status: "edited",
            edited_value: "Harbourtown",
          },
        ],
      }),
    ]);
    renderApp(PAGE);

    const panel = await findPanel();
    expect(panel).toHaveTextContent("Testville");
    expect(panel).toHaveTextContent("Your version:");
    expect(panel).toHaveTextContent("Harbourtown");
  });

  it("asks the local model with the chosen source and fields", async () => {
    let posted: unknown = null;
    serveDrafts([]);
    server.use(
      http.post(`${API}/ai/artifacts/${ARTIFACT_ID}/drafts`, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(aiDraft(), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    const form = within(panel).getByRole("form", { name: "Ask for a draft" });
    await user.selectOptions(within(form).getByLabelText("Read from"), "ocr_text");
    const fieldNames = within(form).getByLabelText(/Fields to look for/);
    await user.clear(fieldNames);
    await user.type(fieldNames, "city, street");
    await user.click(within(form).getByRole("button", { name: "Ask the local model" }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toEqual({ source_kind: "ocr_text", fields: ["city", "street"] });
  });

  it("shows timestamped transcripts with the machine-generated caveat", async () => {
    serveTranscripts([transcript({ derived_file_id: "df_" + "7".repeat(32) })]);
    renderApp(PAGE);

    const panel = await findPanel();
    expect(panel).toHaveTextContent("potentially inaccurate");
    expect(panel).toHaveTextContent("original audio is unchanged");
    const segments = within(panel).getByRole("list", { name: "Transcript segments" });
    expect(segments).toHaveTextContent("0:00");
    expect(segments).toHaveTextContent("testing one two");
    expect(segments).toHaveTextContent("three");
    expect(panel).toHaveTextContent("whistle · v1 · Apache-2.0");
    expect(panel).toHaveTextContent("from the extracted audio track");
    expect(panel).toHaveTextContent("the model's text above is always kept");
  });

  it("stores an analyst correction without touching the model's text", async () => {
    let patched: unknown = null;
    serveTranscripts([transcript()]);
    server.use(
      http.patch(`${API}/ai/artifacts/${ARTIFACT_ID}/transcripts/:id`, async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json(transcript({ edited_text: "testing 1 2 3" }));
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    const box = within(panel).getByLabelText(/My corrected text/);
    await user.type(box, "testing 1 2 3");
    await user.click(within(panel).getByRole("button", { name: "Save my version" }));

    await waitFor(() => expect(patched).toEqual({ edited_text: "testing 1 2 3" }));
  });

  it("has no transcript section for an image", async () => {
    serveDrafts([]);
    server.use(http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(artifactDetail())));
    renderApp(PAGE);

    const panel = await findPanel();
    expect(within(panel).queryByRole("heading", { name: "Transcripts" })).not.toBeInTheDocument();
  });

  it("shows a load error with retry", async () => {
    server.use(http.get(`${API}/ai/status`, () => apiError(500, "INTERNAL_ERROR", "Broke.")));
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "AI assistant (drafts, not evidence)" });
    const alertBox = await within(panel).findByRole("alert");
    expect(alertBox).toHaveTextContent("The AI assistant could not load: Broke.");

    server.use(http.get(`${API}/ai/status`, () => HttpResponse.json(aiStatus())));
    await user.click(within(alertBox).getByRole("button", { name: "Retry" }));
    expect(await within(panel).findByRole("form", { name: "Ask for a draft" })).toBeInTheDocument();
  });
});
