import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { ARTIFACT_ID, CASES_NOTICE, caseInfo, geoTools } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

describe("Cases control", () => {
  it("states that a case is organisation rather than evidence", async () => {
    renderApp(PAGE);
    const panel = await screen.findByRole("region", { name: "Cases" });
    await within(panel).findByText(/organisation, not evidence/);
    expect(panel).toHaveTextContent("organisation, not evidence");
    expect(panel).toHaveTextContent("never an artifact or its evidence");
  });

  it("adds and removes this artifact, and creates a case around it", async () => {
    const calls: string[] = [];
    let cases = [caseInfo()];
    server.use(
      http.get(`${API}/cases`, () => HttpResponse.json({ notice: CASES_NOTICE, cases })),
      http.put(`${API}/cases/:caseId/artifacts/:artifactId`, ({ params }) => {
        calls.push(`link ${params.caseId}`);
        cases = [caseInfo({ artifact_count: 1, artifacts: [{ artifact_id: ARTIFACT_ID, filename: "harbour.jpg", media_type: "image", added_at: "2026-11-09T09:00:00Z" }] })];
        return HttpResponse.json(cases[0]);
      }),
      http.delete(`${API}/cases/:caseId/artifacts/:artifactId`, ({ params }) => {
        calls.push(`unlink ${params.caseId}`);
        cases = [caseInfo()];
        return HttpResponse.json(cases[0]);
      }),
      http.post(`${API}/cases`, async ({ request }) => {
        const body = (await request.json()) as { name: string };
        calls.push(`create ${body.name}`);
        return HttpResponse.json(caseInfo({ case_id: "case_" + "2".repeat(32), name: body.name }), {
          status: 201,
        });
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Cases" });
    const list = await within(panel).findByRole("list", { name: "Cases" });
    expect(list).toHaveTextContent("Operation Fixture");

    await user.click(within(list).getByRole("button", { name: "Add to case" }));
    await waitFor(() => expect(calls[0]).toContain("link case_"));
    await user.click(await within(panel).findByRole("button", { name: "Remove from case" }));
    await waitFor(() => expect(calls[1]).toContain("unlink case_"));

    const form = within(panel).getByRole("form", { name: "Create a case" });
    await user.type(within(form).getByLabelText("New case name"), "New matter");
    await user.click(within(form).getByRole("button", { name: "Create and add this artifact" }));
    await waitFor(() => expect(calls).toContain("create New matter"));
  });
});

describe("Coordinate tools panel", () => {
  it("shows every notation and says what the numbers are not", async () => {
    server.use(
      http.get(`${API}/geo/artifacts/${ARTIFACT_ID}/tools`, () => HttpResponse.json(geoTools())),
    );
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Coordinate tools" });
    await within(panel).findByRole("list", { name: "Held coordinates" });
    expect(panel).toHaveTextContent("Nothing here determines where media was captured");
    expect(panel).toHaveTextContent("no coordinate is sent anywhere");
    const points = within(panel).getByRole("list", { name: "Held coordinates" });
    expect(points).toHaveTextContent("metadata: EXIF/container GPS");
    expect(points).toHaveTextContent("51.500000, -0.120000");
    expect(points).toHaveTextContent("ISO 6709");
    expect(panel).toHaveTextContent("Vestigo never downloads map data or tiles");
    expect(within(panel).getByText("What these numbers are not")).toBeInTheDocument();
  });

  it("reports the geometry between two held points", async () => {
    server.use(
      http.get(`${API}/geo/artifacts/${ARTIFACT_ID}/tools`, () =>
        HttpResponse.json(
          geoTools({
            points: [
              ...geoTools().points,
              {
                source: "candidate: Near the harbour",
                latitude: 51.51,
                longitude: -0.13,
                formats: {
                  decimal: "51.510000, -0.130000",
                  degrees_minutes_seconds: "51° 30' 36.00\" N 0° 7' 48.00\" W",
                  degrees_decimal_minutes: "51° 30.6000' N 0° 7.8000' W",
                  iso6709: "+51.510000-000.130000/",
                },
                candidate_id: "loc_" + "1".repeat(32),
              },
            ],
            pairs: [
              {
                from_source: "metadata: EXIF/container GPS",
                to_source: "candidate: Near the harbour",
                distance_metres: 1327.5,
                bearing_degrees: 331.2,
              },
            ],
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Coordinate tools" });
    const pairs = await within(panel).findByRole("list", { name: "Distances between points" });
    expect(pairs).toHaveTextContent("1.33 km apart, bearing 331.2°");
    expect(pairs).toHaveTextContent("candidate: Near the harbour");
  });

  it("stays hidden when no coordinates are held", async () => {
    server.use(
      http.get(`${API}/geo/artifacts/${ARTIFACT_ID}/tools`, () =>
        HttpResponse.json(geoTools({ points: [], pairs: [] })),
      ),
    );
    renderApp(PAGE);

    await screen.findByRole("region", { name: "Chain of custody" });
    expect(screen.queryByRole("region", { name: "Coordinate tools" })).not.toBeInTheDocument();
  });

  it("shows a load error with retry", async () => {
    server.use(
      http.get(`${API}/geo/artifacts/${ARTIFACT_ID}/tools`, () =>
        apiError(500, "INTERNAL_ERROR", "Broke."),
      ),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Coordinate tools" });
    const alertBox = await within(panel).findByRole("alert");
    expect(alertBox).toHaveTextContent("Coordinate tools could not load: Broke.");

    server.use(
      http.get(`${API}/geo/artifacts/${ARTIFACT_ID}/tools`, () => HttpResponse.json(geoTools())),
    );
    await user.click(within(alertBox).getByRole("button", { name: "Retry" }));
    expect(await within(panel).findByRole("list", { name: "Held coordinates" })).toBeInTheDocument();
  });
});

describe("Custody labels for Pass 1 and Pass 3 events", () => {
  it("renders AI, index, and case events as factual lines", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/custody`, () =>
        HttpResponse.json({
          artifact_id: ARTIFACT_ID,
          notice: "What Vestigo recorded on this machine.",
          events: [
            {
              type: "ai_draft_generated",
              at: "2026-11-09T09:00:00Z",
              source_table: "custody_events",
              detail: { model: "needle3", source_kind: "metadata", field_names: ["city", "date"] },
            },
            {
              type: "transcript_created",
              at: "2026-11-09T09:01:00Z",
              source_table: "custody_events",
              detail: { model: "whistle", language: "en", segments: 2 },
            },
            {
              type: "embeddings_indexed",
              at: "2026-11-09T09:02:00Z",
              source_table: "custody_events",
              detail: { chunks: 7, model: "vestigo-local-hash" },
            },
            {
              type: "case_linked",
              at: "2026-11-09T09:03:00Z",
              source_table: "custody_events",
              detail: { case_id: "case_x", case_name: "Operation Fixture" },
            },
          ],
          derived_files: [],
        }),
      ),
    );
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Chain of custody" });
    const timeline = await within(panel).findByRole("list", { name: "Custody timeline" });
    const rows = within(timeline).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("AI draft generated");
    expect(rows[0]).toHaveTextContent("needle3 read metadata · fields: city, date");
    expect(rows[1]).toHaveTextContent("Transcript created");
    expect(rows[1]).toHaveTextContent("whistle · en · 2 segment(s)");
    expect(rows[2]).toHaveTextContent("Search index built");
    expect(rows[2]).toHaveTextContent("7 chunk(s) with vestigo-local-hash");
    expect(rows[3]).toHaveTextContent("Added to a case");
    expect(rows[3]).toHaveTextContent("Operation Fixture");
  });
});
