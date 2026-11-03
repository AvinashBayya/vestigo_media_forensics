import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { SettingsResponse } from "../api/types";
import { ARTIFACT_ID, JOB_ID, artifactList, health, listItem, settingsResponse } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

function imageFile() {
  return new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0])], "harbour.jpg", { type: "image/jpeg" });
}

function uploadResponse() {
  return HttpResponse.json(
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
  );
}

describe("SettingsPage", () => {
  it("saves the editable defaults, which the Library then uses", async () => {
    let sent: Record<string, unknown> | null = null;
    let saved: SettingsResponse = settingsResponse();
    const listLimits: string[] = [];
    server.use(
      http.get(`${API}/settings`, () => HttpResponse.json(saved)),
      http.patch(`${API}/settings`, async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        saved = settingsResponse(sent as Partial<SettingsResponse["editable"]>);
        return HttpResponse.json(saved);
      }),
      http.get(`${API}/artifacts`, ({ request }) => {
        listLimits.push(new URL(request.url).searchParams.get("limit") ?? "");
        return HttpResponse.json(artifactList([listItem()]));
      }),
    );
    const user = userEvent.setup();
    renderApp("/settings");

    const form = await screen.findByRole("form", { name: "Defaults" });
    await user.click(within(form).getByRole("checkbox", { name: "Text in image (OCR, English)" }));
    await user.click(within(form).getByRole("checkbox", { name: "Start the analysis automatically after each upload" }));
    await user.selectOptions(within(form).getByRole("combobox", { name: "Artifacts per Library page" }), "50");
    await user.click(within(form).getByRole("button", { name: "Save defaults" }));

    expect(await within(form).findByRole("status")).toHaveTextContent("Saved");
    expect(sent).toEqual({
      default_analysis_options: { metadata: true, c2pa: true, ocr: false, duplicate_search: true },
      library_page_size: 50,
      auto_analyze_after_upload: false,
    });

    await user.click(screen.getByRole("link", { name: "Library" }));
    await screen.findByRole("table");
    expect(listLimits.at(-1)).toBe("50");
  });

  it("shows validation errors from the backend", async () => {
    server.use(
      http.patch(`${API}/settings`, () => apiError(422, "VALIDATION_ERROR", "Request validation failed.")),
    );
    const user = userEvent.setup();
    renderApp("/settings");

    const form = await screen.findByRole("form", { name: "Defaults" });
    await user.click(within(form).getByRole("button", { name: "Save defaults" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Request validation failed.");
  });

  it("shows environment settings, including the duplicate threshold, as read-only", async () => {
    renderApp("/settings");

    const env = await screen.findByRole("region", { name: "Environment" });
    expect(env).toHaveTextContent("Duplicate thresholdpHash Hamming distance ≤ 10 of 64 bits");
    expect(env).toHaveTextContent("Maximum upload size50 MB");
    expect(env).toHaveTextContent("Maximum image size100 megapixels");
    expect(env).toHaveTextContent("Database schema0002_m2_analyst_workflow");
    expect(env).toHaveTextContent("Restart the backend after changing them.");
    expect(within(env).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(env).queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(within(env).queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("lists tool status", async () => {
    const missing = { status: "missing" as const, version: null, used_in: "M1: OCR", languages: null, detail: null };
    server.use(http.get(`${API}/health`, () => HttpResponse.json(health({ status: "degraded", tools: { ...health().tools, tesseract: missing } }))));
    renderApp("/settings");

    const tools = await screen.findByRole("region", { name: "Tools" });
    const row = (await within(tools).findByText("tesseract")).closest("tr")!;
    expect(row).toHaveTextContent("Not installed");
    expect(within(tools).getByText("exiftool").closest("tr")).toHaveTextContent("Available");
  });

  it("shows the duplicate library and storage, with actions", async () => {
    let analysisBody: unknown = null;
    let included: unknown = null;
    let summaryCalls = 0;
    const ref = (id: string, filename: string, indexed: boolean) => ({
      artifact_id: id,
      filename,
      created_at: "2026-11-02T09:00:00Z",
      indexed,
    });
    server.use(
      http.get(`${API}/library/summary`, () => {
        summaryCalls += 1;
        return HttpResponse.json({
          artifact_count: 5,
          indexed_count: 3,
          not_indexed_count: 1,
          excluded_count: summaryCalls === 1 ? 1 : 0,
          not_indexed: [ref(`art_${"1".repeat(32)}`, "new.jpg", false)],
          excluded: summaryCalls === 1 ? [ref(`art_${"2".repeat(32)}`, "test-card.png", true)] : [],
          storage: { original_bytes: 3 * 1024 * 1024, derived_bytes: 512 * 1024 },
        });
      }),
      http.post(`${API}/analysis/image`, async ({ request }) => {
        analysisBody = await request.json();
        return HttpResponse.json({ job_id: JOB_ID, artifact_id: `art_${"1".repeat(32)}`, status: "queued" }, { status: 202 });
      }),
      http.patch(`${API}/artifacts/:id/duplicate-library`, async ({ request }) => {
        included = await request.json();
        return HttpResponse.json({});
      }),
    );
    const user = userEvent.setup();
    renderApp("/settings");

    const section = await screen.findByRole("region", { name: "Duplicate library and storage" });
    await within(section).findByText("new.jpg");
    expect(section).toHaveTextContent("Searchable for duplicates3");
    expect(section).toHaveTextContent("Storage: originals3.0 MB");
    expect(section).toHaveTextContent("Storage: derived files512 KB");

    const notAnalysed = within(section).getByRole("group", { name: "Not analysed yet" });
    await user.click(within(notAnalysed).getByRole("button", { name: "Run analysis" }));
    expect(await within(notAnalysed).findByText("Analysis started")).toBeInTheDocument();
    expect(analysisBody).toEqual({ artifact_id: `art_${"1".repeat(32)}` }); // backend applies saved defaults

    const excluded = within(section).getByRole("group", { name: "Excluded from duplicate search" });
    await user.click(within(excluded).getByRole("button", { name: "Include again" }));
    expect(included).toEqual({ included: true });
    await waitFor(() => expect(within(section).queryByText("test-card.png")).not.toBeInTheDocument());
  });

  it("shows an error with retry if settings cannot be loaded, and the Library falls back to defaults", async () => {
    const listLimits: string[] = [];
    server.use(
      http.get(`${API}/settings`, () => apiError(500, "INTERNAL_ERROR", "Something went wrong on the server.")),
      http.get(`${API}/artifacts`, ({ request }) => {
        listLimits.push(new URL(request.url).searchParams.get("limit") ?? "");
        return HttpResponse.json(artifactList([listItem()]));
      }),
    );
    renderApp("/settings");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Settings could not be loaded.");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();

    renderApp("/");
    await waitFor(() => expect(listLimits).toEqual(["25"]));
  });
});

describe("Settings applied elsewhere", () => {
  it("uploads without analysing when automatic analysis is off", async () => {
    let analysisStarted = false;
    server.use(
      http.get(`${API}/settings`, () => HttpResponse.json(settingsResponse({ auto_analyze_after_upload: false }))),
      http.post(`${API}/artifacts/upload`, uploadResponse),
      http.post(`${API}/analysis/image`, () => {
        analysisStarted = true;
        return HttpResponse.json({}, { status: 202 });
      }),
    );
    const user = userEvent.setup();
    renderApp("/upload");

    expect(await screen.findByText(/Automatic analysis after upload is off/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Checks to run" })).not.toBeInTheDocument();
    await user.upload(screen.getByLabelText(/choose an image/i), imageFile());
    await user.click(screen.getByRole("button", { name: "Upload" }));

    expect(
      await screen.findByText("Uploaded. Analysis was not started because automatic analysis is off in Settings."),
    ).toBeInTheDocument();
    expect(analysisStarted).toBe(false);
  });

  it("starts uploads with the saved default checks", async () => {
    let options: unknown = null;
    server.use(
      http.get(`${API}/settings`, () =>
        HttpResponse.json(
          settingsResponse({ default_analysis_options: { metadata: true, c2pa: false, ocr: false, duplicate_search: true } }),
        ),
      ),
      http.post(`${API}/artifacts/upload`, uploadResponse),
      http.post(`${API}/analysis/image`, async ({ request }) => {
        options = ((await request.json()) as { options: unknown }).options;
        return HttpResponse.json({ job_id: JOB_ID, artifact_id: ARTIFACT_ID, status: "queued" }, { status: 202 });
      }),
    );
    const user = userEvent.setup();
    renderApp("/upload");

    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Text in image (OCR, English)" })).not.toBeChecked());
    expect(screen.getByRole("checkbox", { name: "Content Credentials (C2PA) detection" })).not.toBeChecked();
    await user.upload(screen.getByLabelText(/choose an image/i), imageFile());
    await user.click(screen.getByRole("button", { name: "Upload and analyse" }));

    await waitFor(() => expect(options).toEqual({ metadata: true, c2pa: false, ocr: false, duplicate_search: true }));
  });

  it("uses the saved page size in the Library", async () => {
    const limits: string[] = [];
    server.use(
      http.get(`${API}/settings`, () => HttpResponse.json(settingsResponse({ library_page_size: 10 }))),
      http.get(`${API}/artifacts`, ({ request }) => {
        limits.push(new URL(request.url).searchParams.get("limit") ?? "");
        return HttpResponse.json(artifactList([listItem()]));
      }),
    );
    renderApp("/");
    await screen.findByRole("table");
    expect(limits).toEqual(["10"]); // the first request already used the saved size
  });

  it("re-runs an artifact's analysis with the saved defaults", async () => {
    let body: unknown = null;
    server.use(
      http.post(`${API}/analysis/image`, async ({ request }) => {
        body = await request.json();
        return apiError(409, "ANALYSIS_IN_PROGRESS", "An analysis is already queued or running for this artifact.");
      }),
    );
    const user = userEvent.setup();
    renderApp(`/artifacts/${ARTIFACT_ID}`);

    await user.click(await screen.findByRole("button", { name: "Run analysis again" }));
    expect(await screen.findByText("An analysis is already queued or running for this artifact.")).toBeInTheDocument();
    expect(body).toEqual({ artifact_id: ARTIFACT_ID });
  });
});
