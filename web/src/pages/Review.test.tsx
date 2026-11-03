import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { ReviewEvent } from "../api/types";
import { ARTIFACT_ID, artifactDetail, artifactList, evidenceReport, listItem, provenance } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;
const SAVED_AT = "2026-11-02T10:00:00.000000Z";

function conflict(current: { state: string; analyst_notes: string; updated_at: string | null }) {
  return HttpResponse.json(
    { error: { code: "REVIEW_CONFLICT", message: "This review was changed elsewhere.", details: { current } } },
    { status: 409 },
  );
}

function event(overrides: Partial<ReviewEvent>): ReviewEvent {
  return {
    event_id: `rve_${Math.random().toString(16).slice(2).padEnd(32, "0")}`,
    origin: "artifact",
    evidence_id: null,
    stage: null,
    job_id: null,
    from_state: "UNREVIEWED",
    to_state: "IN_REVIEW",
    notes_before: "",
    notes_after: "",
    created_at: SAVED_AT,
    ...overrides,
  };
}

describe("Artifact review", () => {
  it("keeps the analyst's text when the review changed elsewhere, and resolves either way", async () => {
    const bodies: Record<string, unknown>[] = [];
    let calls = 0;
    server.use(
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/review`, async ({ request }) => {
        bodies.push((await request.json()) as Record<string, unknown>);
        calls += 1;
        if (calls === 1) return conflict({ state: "FLAGGED", analyst_notes: "From the other tab.", updated_at: SAVED_AT });
        return HttpResponse.json(
          artifactDetail({ review: { state: "REVIEWED", analyst_notes: "My notes.", updated_at: "2026-11-02T11:00:00Z" } }),
        );
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    await user.selectOptions(await screen.findByLabelText("Review state"), "REVIEWED");
    await user.type(screen.getByLabelText("Analyst notes"), "My notes.");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save review" }));

    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("This review was changed elsewhere since you opened it. Nothing was saved.");
    expect(notice).toHaveTextContent("Saved review: Flagged");
    expect(notice).toHaveTextContent("Saved notes: From the other tab.");
    expect(screen.getByLabelText("Analyst notes")).toHaveValue("My notes.");

    await user.click(within(notice).getByRole("button", { name: "Save my version over it" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved");
    expect(bodies[1]).toEqual({ state: "REVIEWED", analyst_notes: "My notes.", expected_updated_at: SAVED_AT });
  });

  it("can replace the form with the saved review after a conflict", async () => {
    server.use(
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/review`, () =>
        conflict({ state: "FLAGGED", analyst_notes: "From the other tab.", updated_at: SAVED_AT }),
      ),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    await user.type(await screen.findByLabelText("Analyst notes"), "Mine");
    await user.click(screen.getByRole("button", { name: "Save review" }));
    await user.click(await screen.findByRole("button", { name: "Use the saved review" }));

    expect(screen.getByLabelText("Analyst notes")).toHaveValue("From the other tab.");
    expect(screen.getByLabelText("Review state")).toHaveValue("FLAGGED");
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
  });

  it("asks before leaving with unsaved review changes", async () => {
    const user = userEvent.setup();
    renderApp(PAGE);

    await user.type(await screen.findByLabelText("Analyst notes"), "Half-written note");
    await user.click(screen.getByRole("link", { name: "Library" }));

    const dialog = await screen.findByRole("dialog", { name: "Leave without saving?" });
    await user.click(within(dialog).getByRole("button", { name: "Stay on this page" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Analyst notes")).toHaveValue("Half-written note");

    await user.click(screen.getByRole("link", { name: "Library" }));
    await user.click(await screen.findByRole("button", { name: "Leave without saving" }));
    expect(await screen.findByRole("heading", { name: "Library" })).toBeInTheDocument();
  });

  it("leaves without asking when nothing is unsaved", async () => {
    const user = userEvent.setup();
    renderApp(PAGE);
    await screen.findByLabelText("Analyst notes");

    await user.click(screen.getByRole("link", { name: "Library" }));
    expect(await screen.findByRole("heading", { name: "Library" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the review history with full notes, and reloads it after saving", async () => {
    let historyRequests = 0;
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/review-history`, () => {
        historyRequests += 1;
        return HttpResponse.json({
          artifact_id: ARTIFACT_ID,
          events: [
            event({ origin: "bulk", from_state: "IN_REVIEW", to_state: "FLAGGED", notes_before: "kept", notes_after: "kept" }),
            event({ origin: "record", stage: "ocr", to_state: "REVIEWED", notes_after: "OCR misread the date." }),
            event({ notes_before: "First draft.", notes_after: "Second draft." }),
          ],
        });
      }),
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/review`, () => HttpResponse.json(artifactDetail())),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    await user.click(await screen.findByText("Review history (3)"));
    expect(screen.getByText("Bulk change: In review → Flagged")).toBeInTheDocument();
    expect(screen.getByText("Evidence: Text in image (OCR): Unreviewed → Reviewed")).toBeInTheDocument();
    expect(screen.getByText("OCR misread the date.")).toBeInTheDocument();
    expect(screen.getByText("Second draft.")).toBeInTheDocument();
    expect(screen.getByText("First draft.")).toBeInTheDocument(); // under "Previous notes"
    expect(screen.queryByText("kept")).not.toBeInTheDocument(); // notes unchanged by the bulk change

    const before = historyRequests;
    await user.selectOptions(screen.getByLabelText("Review state"), "IN_REVIEW");
    await user.click(screen.getByRole("button", { name: "Save review" }));
    await waitFor(() => expect(historyRequests).toBe(before + 1));
  });
});

describe("Evidence record review", () => {
  it("reviews one section without touching the artifact review", async () => {
    let body: Record<string, unknown> | null = null;
    let artifactReviewCalls = 0;
    server.use(
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/evidence/ev_hashes/review`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          evidence_id: "ev_hashes",
          artifact_id: ARTIFACT_ID,
          job_id: "job_x",
          stage: "hashes",
          classification: "DERIVED",
          review_state: "FLAGGED",
          analyst_notes: "Hash differs from the source's copy.",
          review_updated_at: SAVED_AT,
        });
      }),
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/review`, () => {
        artifactReviewCalls += 1;
        return HttpResponse.json(artifactDetail());
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const hashes = await screen.findByRole("region", { name: "File hashes" });
    expect(within(hashes).getByText("Your review of this section:")).toBeInTheDocument();
    await user.click(within(hashes).getByRole("button", { name: "Review this section" }));
    const form = within(hashes).getByRole("form", { name: "Review of hashes" });
    await user.selectOptions(within(form).getByLabelText("Review state"), "FLAGGED");
    await user.type(within(form).getByLabelText("Notes on this section"), "Hash differs from the source's copy.");
    await user.click(within(form).getByRole("button", { name: "Save section review" }));

    expect(await within(hashes).findByText("Hash differs from the source's copy.")).toBeInTheDocument();
    expect(within(hashes).getByText("Flagged")).toBeInTheDocument();
    expect(body).toEqual({ state: "FLAGGED", analyst_notes: "Hash differs from the source's copy.", expected_updated_at: null });
    expect(artifactReviewCalls).toBe(0);
    expect(screen.getByLabelText("Review state", { selector: "form:not([aria-label]) select" })).toHaveValue("UNREVIEWED");
  });

  it("shows an earlier section review and handles conflicts", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            hashes: {
              ...evidenceReport().hashes!,
              provenance: provenance("hashes", { review_state: "IN_REVIEW", analyst_notes: "Checking.", review_updated_at: SAVED_AT }),
            },
          }),
        ),
      ),
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/evidence/ev_hashes/review`, () =>
        conflict({ state: "REVIEWED", analyst_notes: "Done elsewhere.", updated_at: "2026-11-02T12:00:00Z" }),
      ),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const hashes = await screen.findByRole("region", { name: "File hashes" });
    expect(within(hashes).getByText("Checking.")).toBeInTheDocument();
    expect(within(hashes).getByText("In review")).toBeInTheDocument();
    await user.click(within(hashes).getByRole("button", { name: "Edit review" }));
    await user.click(within(hashes).getByRole("button", { name: "Save section review" }));

    const notice = await within(hashes).findByRole("alert");
    expect(notice).toHaveTextContent("Saved notes: Done elsewhere.");
    await user.click(within(notice).getByRole("button", { name: "Use the saved review" }));
    expect(within(hashes).getByLabelText("Notes on this section")).toHaveValue("Done elsewhere.");
  });
});

describe("Bulk review", () => {
  const rows = () => [
    listItem({ artifact_id: `art_${"a".repeat(32)}`, filename: "a.jpg" }),
    listItem({ artifact_id: `art_${"b".repeat(32)}`, filename: "b.jpg", review_state: "REVIEWED" }),
    listItem({ artifact_id: `art_${"c".repeat(32)}`, filename: "c.jpg" }),
  ];

  it("asks for confirmation, then reports what changed", async () => {
    let body: unknown = null;
    let listRequests = 0;
    server.use(
      http.get(`${API}/artifacts`, () => {
        listRequests += 1;
        return HttpResponse.json(artifactList(rows()));
      }),
      http.post(`${API}/artifacts/review`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          state: "REVIEWED",
          updated: [`art_${"a".repeat(32)}`],
          unchanged: [`art_${"b".repeat(32)}`],
        });
      }),
    );
    const user = userEvent.setup();
    renderApp("/");

    await user.click(await screen.findByRole("checkbox", { name: "Select a.jpg" }));
    await user.click(screen.getByRole("checkbox", { name: "Select b.jpg" }));
    const bar = screen.getByRole("region", { name: "Bulk review" });
    expect(bar).toHaveTextContent("2 artifacts selected");

    await user.click(within(bar).getByRole("button", { name: "Apply…" }));
    let dialog = screen.getByRole("dialog", { name: "Set 2 artifacts to Reviewed?" });
    expect(dialog).toHaveTextContent("Analyst notes are not changed.");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(body).toBeNull();

    await user.click(within(bar).getByRole("button", { name: "Apply…" }));
    dialog = screen.getByRole("dialog", { name: "Set 2 artifacts to Reviewed?" });
    const before = listRequests;
    await user.click(within(dialog).getByRole("button", { name: "Set to Reviewed" }));

    expect(await screen.findByText("Set 1 artifact to Reviewed. 1 was already Reviewed.")).toBeInTheDocument();
    expect(body).toEqual({ artifact_ids: [`art_${"a".repeat(32)}`, `art_${"b".repeat(32)}`], state: "REVIEWED" });
    expect(screen.queryByRole("region", { name: "Bulk review" })).not.toBeInTheDocument();
    await waitFor(() => expect(listRequests).toBeGreaterThan(before));
  });

  it("selects the whole page and shows a clear failure", async () => {
    server.use(
      http.get(`${API}/artifacts`, () => HttpResponse.json(artifactList(rows()))),
      http.post(`${API}/artifacts/review`, () =>
        apiError(404, "ARTIFACT_NOT_FOUND", "1 of the selected artifacts no longer exist. Nothing was changed."),
      ),
    );
    const user = userEvent.setup();
    renderApp("/");

    await user.click(await screen.findByRole("checkbox", { name: "Select all on this page" }));
    expect(screen.getByRole("region", { name: "Bulk review" })).toHaveTextContent("3 artifacts selected");
    await user.selectOptions(screen.getByRole("combobox", { name: "Set review state to" }), "ARCHIVED");
    await user.click(screen.getByRole("button", { name: "Apply…" }));
    await user.click(screen.getByRole("button", { name: "Set to Archived" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Bulk review failed. 1 of the selected artifacts no longer exist. Nothing was changed.",
    );
    expect(screen.getByRole("region", { name: "Bulk review" })).toHaveTextContent("3 artifacts selected");
  });
});
