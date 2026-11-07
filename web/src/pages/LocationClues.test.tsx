import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { LocationCandidateCreate, LocationCandidateUpdate, LocationCluesSection } from "../api/types";
import {
  ARTIFACT_ID,
  LOCATION_NOTICE,
  evidenceReport,
  locationCandidate,
  locationClues,
  settingsResponse,
} from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

async function findPanel() {
  const panel = await screen.findByRole("region", { name: "Location clues" });
  await within(panel).findByRole("form", { name: "Record a location candidate" });
  return panel;
}

function serveClues(section: LocationCluesSection | null, mapEnabled = false) {
  server.use(
    http.get(`${API}/settings`, () =>
      HttpResponse.json(settingsResponse({ enable_external_map_links: mapEnabled })),
    ),
    http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
      HttpResponse.json(evidenceReport({ location_clues: section })),
    ),
  );
}

describe("Location clues panel", () => {
  it("shows decimal coordinates beside the as-written strings with the honesty wording", async () => {
    serveClues(locationClues());
    renderApp(PAGE);

    const panel = await findPanel();
    const coordinates = within(panel).getByRole("list", { name: "Coordinates" });
    expect(coordinates).toHaveTextContent("51.5, -0.12");
    expect(coordinates).toHaveTextContent("As written:");
    expect(coordinates).toHaveTextContent("(North)");
    expect(coordinates).toHaveTextContent("(West)");

    expect(panel).toHaveTextContent("Altitude: 58.4 m (Above Sea Level)");
    expect(panel).toHaveTextContent("IPTC:City");
    expect(panel).toHaveTextContent("Testville");
    expect(panel).toHaveTextContent("EXIF:DateTimeOriginal");
    expect(panel).toHaveTextContent("VestigoTestCam");
    expect(panel).toHaveTextContent("read as written in the file");
    expect(panel).toHaveTextContent("never proof of where the media was captured");
    // OCR text is pointed at, never interpreted.
    expect(panel).toHaveTextContent("This analysis produced OCR text");
    expect(within(panel).getByRole("link", { name: /does not interpret that text/ })).toBeInTheDocument();
  });

  it("flags an unusable coordinate and keeps it as written", async () => {
    serveClues(
      locationClues({
        coordinates: [
          {
            source: "EXIF/container GPS",
            latitude: 191.5,
            longitude: null,
            latitude_as_written: "191 deg 30' 0.00\" (North)",
            longitude_as_written: null,
            valid: false,
            problem: "latitude 191.5 is outside ±90; only one of latitude/longitude is present",
          },
        ],
        altitude_meters: null,
      }),
      true,
    );
    renderApp(PAGE);

    const panel = await findPanel();
    expect(panel).toHaveTextContent("Unusable value");
    expect(panel).toHaveTextContent("outside ±90");
    expect(panel).toHaveTextContent("the value is kept exactly as written");
    expect(panel).toHaveTextContent("191 deg 30");
    // No map link for a value that cannot be trusted as a coordinate.
    expect(within(panel).queryByRole("link", { name: /OpenStreetMap/ })).not.toBeInTheDocument();
  });

  it("explains that absence proves nothing", async () => {
    serveClues(
      locationClues({
        coordinates: [],
        text_clues: [],
        altitude_meters: null,
        timestamps: [],
        device: [],
        ocr_available: false,
      }),
    );
    renderApp(PAGE);

    const panel = await findPanel();
    expect(panel).toHaveTextContent("No location metadata was found. Absence proves nothing");
    expect(panel).toHaveTextContent("No OCR text was produced for this analysis.");
  });

  it("hides the OpenStreetMap link while external map links are off", async () => {
    serveClues(locationClues(), false);
    renderApp(PAGE);

    const panel = await findPanel();
    expect(within(panel).queryByRole("link", { name: /OpenStreetMap/ })).not.toBeInTheDocument();
    expect(panel).toHaveTextContent("External map links are off.");
  });

  it("offers a client-built OpenStreetMap link with the coordinate warning once enabled", async () => {
    serveClues(locationClues(), true);
    renderApp(PAGE);

    const panel = await findPanel();
    const link = await within(panel).findByRole("link", { name: "Open in OpenStreetMap (external)" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    const href = link.getAttribute("href")!;
    expect(href.startsWith("https://www.openstreetmap.org/?")).toBe(true);
    expect(href).toContain("mlat=51.5");
    expect(href).toContain("mlon=-0.12");
    expect(panel).toHaveTextContent("Opening the map sends these coordinates to openstreetmap.org");
  });

  it("records a candidate with the analyst's required assessment and basis", async () => {
    let posted: LocationCandidateCreate | null = null;
    serveClues(locationClues());
    server.use(
      http.post(`${API}/artifacts/${ARTIFACT_ID}/location-candidates`, async ({ request }) => {
        posted = (await request.json()) as LocationCandidateCreate;
        return HttpResponse.json(locationCandidate(), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    expect(panel).toHaveTextContent(LOCATION_NOTICE.slice(0, 60));
    const form = within(panel).getByRole("form", { name: "Record a location candidate" });

    await user.type(within(form).getByLabelText(/Place, as you would state it/), "Near the harbour");
    await user.type(within(form).getByLabelText(/Basis/), "IPTC city tag plus a visible sign");
    await user.selectOptions(within(form).getByLabelText(/Your assessment/), "possible");
    await user.type(within(form).getByLabelText(/^Latitude/), "51.5");
    await user.type(within(form).getByLabelText(/^Longitude/), "-0.12");
    await user.click(within(form).getByRole("button", { name: "Record candidate" }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted).toEqual({
      description: "Near the harbour",
      basis: "IPTC city tag plus a visible sign",
      analyst_assessment: "possible",
      latitude: 51.5,
      longitude: -0.12,
    });
  });

  it("shows candidates as UNVERIFIED analyst judgments and edits them", async () => {
    let patched: LocationCandidateUpdate | null = null;
    let deleted = false;
    serveClues(locationClues());
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/location-candidates`, () =>
        HttpResponse.json({
          artifact_id: ARTIFACT_ID,
          notice: LOCATION_NOTICE,
          candidates: [
            locationCandidate({
              latitude: 51.5,
              longitude: -0.12,
              analyst_assessment: "likely",
              supports: [{ type: "evidence_record", id: "ev_" + "4".repeat(32) }],
            }),
          ],
        }),
      ),
      http.patch(`${API}/artifacts/${ARTIFACT_ID}/location-candidates/:id`, async ({ request }) => {
        patched = (await request.json()) as LocationCandidateUpdate;
        return HttpResponse.json(locationCandidate({ analyst_assessment: "speculative" }));
      }),
      http.delete(`${API}/artifacts/${ARTIFACT_ID}/location-candidates/:id`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    const list = await within(panel).findByRole("list", { name: "Location candidates" });
    const row = within(list).getAllByRole("listitem")[0];
    expect(row).toHaveTextContent("UNVERIFIED");
    expect(row).toHaveTextContent("Near the harbour, Testville");
    expect(row).toHaveTextContent("Analyst assessment: likely (the analyst's own judgment, not a measurement)");
    expect(row).toHaveTextContent("Recorded");
    expect(row).toHaveTextContent("Basis:");
    expect(row).toHaveTextContent("Supported by: evidence record");

    await user.selectOptions(within(row).getByRole("combobox", { name: "Assessment:" }), "speculative");
    expect(patched).toEqual({ analyst_assessment: "speculative" });

    await user.click(within(row).getByRole("button", { name: "Delete candidate" }));
    expect(deleted).toBe(false); // the first click only asks
    await user.click(within(row).getByRole("button", { name: "Confirm delete" }));
    expect(deleted).toBe(true);
  });

  it("refreshes the chain of custody after a candidate changes", async () => {
    let custodyCalls = 0;
    serveClues(locationClues());
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/custody`, () => {
        custodyCalls += 1;
        return HttpResponse.json({ artifact_id: ARTIFACT_ID, notice: "n", events: [], derived_files: [] });
      }),
      http.post(`${API}/artifacts/${ARTIFACT_ID}/location-candidates`, () =>
        HttpResponse.json(locationCandidate(), { status: 201 }),
      ),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await findPanel();
    const before = custodyCalls;
    const form = within(panel).getByRole("form", { name: "Record a location candidate" });
    await user.type(within(form).getByLabelText(/Place, as you would state it/), "Somewhere");
    await user.type(within(form).getByLabelText(/Basis/), "A sign");
    await user.selectOptions(within(form).getByLabelText(/Your assessment/), "speculative");
    await user.click(within(form).getByRole("button", { name: "Record candidate" }));

    await waitFor(() => expect(custodyCalls).toBeGreaterThan(before));
  });

  it("shows a load error with retry", async () => {
    serveClues(locationClues());
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/location-candidates`, () =>
        apiError(500, "INTERNAL_ERROR", "Something broke."),
      ),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Location clues" });
    const alertBox = await within(panel).findByRole("alert");
    expect(alertBox).toHaveTextContent("The location candidates could not be loaded: Something broke.");

    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/location-candidates`, () =>
        HttpResponse.json({ artifact_id: ARTIFACT_ID, notice: LOCATION_NOTICE, candidates: [] }),
      ),
    );
    await user.click(within(alertBox).getByRole("button", { name: "Retry" }));
    expect(
      await within(panel).findByRole("form", { name: "Record a location candidate" }),
    ).toBeInTheDocument();
  });
});
