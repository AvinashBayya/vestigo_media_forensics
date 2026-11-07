import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { ARTIFACT_ID, custodyReport } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

async function findPanel() {
  return await screen.findByRole("region", { name: "Chain of custody" });
}

describe("Chain of custody panel", () => {
  it("shows the honesty notice and one factual line per recorded event", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/custody`, () =>
        HttpResponse.json(
          custodyReport({
            events: [
              ...custodyReport().events,
              {
                type: "review_changed",
                at: "2026-11-02T09:01:00.000000Z",
                source_table: "review_events",
                detail: {
                  origin: "artifact",
                  evidence_id: null,
                  stage: null,
                  from_state: "UNREVIEWED",
                  to_state: "IN_REVIEW",
                  notes_changed: true,
                },
              },
              {
                type: "library_changed",
                at: "2026-11-02T09:02:00.000000Z",
                source_table: "custody_events",
                detail: { included_before: true, included_after: false },
              },
              {
                type: "exported",
                at: "2026-11-02T09:03:00.000000Z",
                source_table: "custody_events",
                detail: {
                  job_id: "job_x",
                  package_sha256: "f".repeat(64),
                  original_included: false,
                  file_count: 8,
                  problem_count: 0,
                },
              },
              {
                type: "preview_created",
                at: "2026-11-02T09:04:00.000000Z",
                source_table: "custody_events",
                detail: { sha256: "9".repeat(64), size_bytes: 1024, width: 640, height: 360 },
              },
              {
                type: "lead_recorded",
                at: "2026-11-02T09:05:00.000000Z",
                source_table: "custody_events",
                detail: { lead_id: "lead_x", provider: "TinEye", derived_file_id: "df_x" },
              },
              {
                type: "lead_updated",
                at: "2026-11-02T09:06:00.000000Z",
                source_table: "custody_events",
                detail: { lead_id: "lead_x", fields: ["notes", "review_state"] },
              },
              {
                type: "lead_deleted",
                at: "2026-11-02T09:07:00.000000Z",
                source_table: "custody_events",
                detail: { lead_id: "lead_x", provider: "TinEye" },
              },
              {
                type: "location_candidate_recorded",
                at: "2026-11-02T09:08:00.000000Z",
                source_table: "custody_events",
                detail: {
                  candidate_id: "loc_x",
                  analyst_assessment: "possible",
                  has_coordinates: true,
                  support_count: 2,
                },
              },
              {
                type: "location_candidate_updated",
                at: "2026-11-02T09:09:00.000000Z",
                source_table: "custody_events",
                detail: { candidate_id: "loc_x", fields: ["analyst_assessment"] },
              },
            ],
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const panel = await findPanel();
    await within(panel).findByRole("list", { name: "Custody timeline" });
    expect(panel).toHaveTextContent("not a legal chain of custody");
    expect(panel).toHaveTextContent("no event is ever inferred");

    const timeline = within(panel).getByRole("list", { name: "Custody timeline" });
    const rows = within(timeline).getAllByRole("listitem");
    expect(rows).toHaveLength(12);
    expect(rows[0]).toHaveTextContent("Uploaded");
    expect(rows[0]).toHaveTextContent("harbour.jpg");
    expect(rows[1]).toHaveTextContent("Analysis started");
    expect(rows[1]).toHaveTextContent("image.v1");
    expect(rows[2]).toHaveTextContent("Analysis finished");
    expect(rows[2]).toHaveTextContent("6 evidence records");
    expect(rows[3]).toHaveTextContent("Review changed");
    expect(rows[3]).toHaveTextContent("UNREVIEWED → IN_REVIEW");
    expect(rows[3]).toHaveTextContent("notes changed");
    expect(rows[4]).toHaveTextContent("Duplicate library changed");
    expect(rows[4]).toHaveTextContent("excluded from future duplicate searches");
    expect(rows[5]).toHaveTextContent("Evidence package exported");
    expect(rows[5]).toHaveTextContent("original not included");
    expect(rows[6]).toHaveTextContent("Playable preview created");
    expect(rows[7]).toHaveTextContent("External lead recorded");
    expect(rows[7]).toHaveTextContent("TinEye · from a keyframe");
    expect(rows[8]).toHaveTextContent("External lead edited");
    expect(rows[8]).toHaveTextContent("fields changed: notes, review_state");
    expect(rows[9]).toHaveTextContent("External lead deleted");
    expect(rows[9]).toHaveTextContent("earlier events for this lead remain above");
    expect(rows[10]).toHaveTextContent("Location candidate recorded");
    expect(rows[10]).toHaveTextContent("analyst assessment: possible · with coordinates · 2 supporting item(s)");
    expect(rows[11]).toHaveTextContent("Location candidate edited");
    expect(rows[11]).toHaveTextContent("fields changed: analyst_assessment");
  });

  it("indents the lineage tree under the original and each source file", async () => {
    renderApp(PAGE);

    const panel = await findPanel();
    const lineage = await within(panel).findByRole("list", { name: "Derived-file lineage" });
    const rows = within(lineage).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("original upload");
    expect(rows[1]).toHaveTextContent("metadata.exiftool.json");
    expect(rows[2]).toHaveTextContent("keyframe_ocr.0001.grayscale.tsv");
    // The TSV was read from the ExifTool row's file, so it sits one level deeper.
    expect((rows[1] as HTMLElement).style.paddingLeft).toBe("1rem");
    expect((rows[2] as HTMLElement).style.paddingLeft).toBe("2rem");
    expect(panel).not.toHaveTextContent("source not recorded");
  });

  it("marks pre-M4B rows as source not recorded instead of guessing", async () => {
    const base = custodyReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/custody`, () =>
        HttpResponse.json(
          custodyReport({
            derived_files: [
              { ...base.derived_files[0], source_kind: null, source_derived_file_id: null },
            ],
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const panel = await findPanel();
    await within(panel).findByRole("list", { name: "Derived-file lineage" });
    expect(panel).toHaveTextContent("source not recorded (pre-M4B record)");
  });

  it("shows a load error with retry", async () => {
    // Error on every load (the page refreshes the panel as the report arrives), until Retry works.
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/custody`, () =>
        apiError(500, "INTERNAL_ERROR", "Something broke."),
      ),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    const alertBox = await within(panel).findByRole("alert");
    expect(alertBox).toHaveTextContent("The chain of custody could not be loaded: Something broke.");

    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/custody`, () => HttpResponse.json(custodyReport())),
    );
    await user.click(within(alertBox).getByRole("button", { name: "Retry" }));
    expect(await within(panel).findByRole("list", { name: "Custody timeline" })).toBeInTheDocument();
  });
});
