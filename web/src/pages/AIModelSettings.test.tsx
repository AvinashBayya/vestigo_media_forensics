import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { aiModels, aiStatus, managedModel, settingsResponse } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

function modelFile() {
  return new File([new Uint8Array([1, 2, 3, 4])], "needle2.cact", { type: "application/octet-stream" });
}

describe("local AI model settings", () => {
  it("says where to put a model file when none is staged", async () => {
    renderApp("/settings");
    expect(await screen.findByText(/\/workspace\/data\/models/)).toBeInTheDocument();
    expect(screen.getByText(/None yet/)).toBeInTheDocument();
  });

  it("lists a staged file with its measured size and digest", async () => {
    server.use(http.get(`${API}/ai/models`, () => HttpResponse.json(aiModels({ models: [managedModel()] }))));
    renderApp("/settings");

    const list = await screen.findByRole("list", { name: "Staged model files" });
    expect(within(list).getByText("needle2.cact")).toBeInTheDocument();
    expect(within(list).getByText("13.74 MB")).toBeInTheDocument();
    expect(within(list).getByText(/^a{12}…$/)).toBeInTheDocument();
  });

  it("offers a staged file as the model for drafts", async () => {
    let sent: Record<string, unknown> | null = null;
    server.use(
      http.get(`${API}/ai/models`, () => HttpResponse.json(aiModels({ models: [managedModel()] }))),
      http.patch(`${API}/settings`, async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(settingsResponse());
      }),
    );
    renderApp("/settings");

    // Both pickers offer the staged file; wait for it, then choose in the drafts one.
    expect(await screen.findAllByRole("option", { name: /needle2\.cact/ })).toHaveLength(2);
    const picker = screen.getByLabelText("Model for drafts");
    await userEvent.selectOptions(picker, "/workspace/data/models/needle2.cact");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent!.ai_model_path).toBe("/workspace/data/models/needle2.cact");
  });

  it("keeps an empty path as a real choice, not a blank", async () => {
    renderApp("/settings");
    const picker = await screen.findByLabelText("Model for drafts");
    expect(within(picker).getByRole("option", { name: /engine carries/i })).toBeInTheDocument();
  });

  it("imports a file the analyst already has, and nothing is downloaded", async () => {
    // Reading the multipart body back is not available here (request.formData() throws inside msw's
    // undici in this environment), so this asserts the observable part: one local multipart POST.
    const posts: string[] = [];
    server.use(
      http.post(`${API}/ai/models/import`, ({ request }) => {
        posts.push(request.headers.get("content-type") ?? "");
        return HttpResponse.json(managedModel(), { status: 201 });
      }),
    );
    renderApp("/settings");

    const input = await screen.findByLabelText(/Import a model file/);
    await userEvent.upload(input, modelFile());

    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatch(/^multipart\/form-data/);
  });

  it("surfaces a refused import instead of silently dropping it", async () => {
    server.use(
      http.post(`${API}/ai/models/import`, () =>
        apiError(415, "UNSUPPORTED_MEDIA_TYPE", "A model file must end in .cact."),
      ),
    );
    renderApp("/settings");

    const input = await screen.findByLabelText(/Import a model file/);
    await userEvent.upload(input, modelFile());
    expect(await screen.findByRole("alert")).toHaveTextContent("must end in .cact");
  });

  it("will not offer to remove a file a setting still points at", async () => {
    server.use(
      http.get(`${API}/ai/models`, () =>
        HttpResponse.json(aiModels({ models: [managedModel({ configured_for: ["ai_model_path"] })] })),
      ),
    );
    renderApp("/settings");

    const list = await screen.findByRole("list", { name: "Staged model files" });
    expect(within(list).getByText("in use")).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "Remove" })).toBeDisabled();
  });

  it("separates a model being present from a model being able to run", async () => {
    renderApp("/settings");
    const known = await screen.findByRole("list", { name: "Known models" });
    expect(within(known).getByText(/needle2/)).toBeInTheDocument();
    // Generation 3 weights are published without an engine, so the UI says so rather than implying it works.
    expect(within(known).getByText(/needle3/)).toBeInTheDocument();
    expect(
      within(known).getAllByText(/cannot run here/).length,
    ).toBeGreaterThan(0);
    expect(
      within(known).getAllByText(/publishes no generation 3 engine/).length,
    ).toBeGreaterThan(0);
  });

  it("states that the backend cannot download a model", async () => {
    renderApp("/settings");
    expect(await screen.findByText(/Downloads are blocked in this process/)).toBeInTheDocument();
  });

  it("reports an engine that is staged", async () => {
    server.use(
      http.get(`${API}/ai/status`, () =>
        HttpResponse.json(
          aiStatus({
            engine_available: true,
            engine_path: "/home/vscode/.cache/cactus-needle/v2/2.0.4/libneedle.so",
            engine_unavailable_reason: null,
          }),
        ),
      ),
    );
    renderApp("/settings");
    expect(await screen.findByText(/generation 2 engine is staged/)).toBeInTheDocument();
  });
});
