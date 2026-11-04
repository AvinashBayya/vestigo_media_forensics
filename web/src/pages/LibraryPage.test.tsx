import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, delay, http } from "msw";
import { describe, expect, it } from "vitest";

import type { ArtifactList } from "../api/types";
import { artifactList, listItem } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

/** Serves `respond` for GET /artifacts and records each request's query parameters. */
function captureList(respond: (params: URLSearchParams) => ArtifactList | Response = () => artifactList([])) {
  const requests: URLSearchParams[] = [];
  server.use(
    http.get(`${API}/artifacts`, ({ request }) => {
      const params = new URL(request.url).searchParams;
      requests.push(params);
      const result = respond(params);
      return result instanceof Response ? result : HttpResponse.json(result);
    }),
  );
  return {
    requests,
    last: () => requests[requests.length - 1],
  };
}

describe("LibraryPage", () => {
  it("is the home page, with Upload as the primary action", async () => {
    captureList();
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Library" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Library" })).toHaveAttribute("href", "/");
    expect(within(nav).getByRole("link", { name: "Library" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/settings");
    expect(within(nav).getByRole("link", { name: "Upload" })).toHaveAttribute("href", "/upload");
    expect(screen.getAllByRole("link", { name: "Upload an image" })[0]).toHaveAttribute("href", "/upload");
  });

  it("lists artifacts with their status indicators", async () => {
    captureList(() =>
      artifactList([
        listItem({ filename: "harbour.jpg", problem_count: 2, duplicate_match_count: 1, added_since_analysis: 3 }),
        listItem({
          filename: "never.png",
          latest_job: null,
          latest_job_status: null,
          problem_count: null,
          duplicate_match_count: null,
          added_since_analysis: null,
          review_state: "FLAGGED",
          in_duplicate_library: false,
        }),
      ]),
    );
    renderApp("/");

    const table = await screen.findByRole("table");
    const [, harbour, never] = within(table).getAllByRole("row");
    expect(within(harbour).getByRole("link", { name: "harbour.jpg" })).toHaveAttribute("href", expect.stringMatching(/^\/artifacts\/art_/));
    expect(within(harbour).getByText("Completed")).toBeInTheDocument();
    expect(within(harbour).getByText("2 problems")).toBeInTheDocument();
    expect(within(harbour).getByText("1 match")).toBeInTheDocument();
    expect(within(harbour).getByText("3 added since search")).toBeInTheDocument();
    expect(within(harbour).getByText("Unreviewed")).toBeInTheDocument();
    expect(within(never).getByText("Not analysed")).toBeInTheDocument();
    expect(within(never).getByText("Not searched")).toBeInTheDocument();
    expect(within(never).getByText("Flagged")).toBeInTheDocument();
    expect(within(never).getByText("Excluded from duplicate search")).toBeInTheDocument();
    expect(screen.getByText("Showing 1–2 of 2 artifacts")).toBeInTheDocument();
  });

  it("shows a video's duration and filters by video type", async () => {
    const list = captureList((params) =>
      artifactList(
        params.getAll("mime_type").includes("video/mp4")
          ? [listItem({ filename: "scenes.mp4", mime_type: "video/mp4", media_type: "video", duration_seconds: 9 })]
          : [
              listItem({ filename: "scenes.mp4", mime_type: "video/mp4", media_type: "video", duration_seconds: 9 }),
              listItem({ filename: "harbour.jpg" }),
            ],
      ),
    );
    const user = userEvent.setup();
    renderApp("/");

    const table = await screen.findByRole("table");
    const row = within(table).getByRole("link", { name: "scenes.mp4" }).closest("tr")!;
    expect(row).toHaveTextContent("Video · 0:09");

    await user.selectOptions(screen.getByRole("combobox", { name: "File type" }), "video/mp4");
    await waitFor(() => expect(list.last().getAll("mime_type")).toEqual(["video/mp4"]));
    expect(within(screen.getByRole("table")).queryByText("harbour.jpg")).not.toBeInTheDocument();
  });

  it("hides archived artifacts by default and sends the default query", async () => {
    const list = captureList(() => artifactList([listItem()]));
    renderApp("/");
    await screen.findByRole("table");

    const params = list.last();
    expect(params.get("include_archived")).toBe("false");
    expect(params.get("sort")).toBe("created_at");
    expect(params.get("order")).toBe("desc");
    expect(params.get("limit")).toBe("25");
    expect(params.get("offset")).toBe("0");
    expect(params.has("q")).toBe(false);
  });

  it("searches after the analyst stops typing", async () => {
    const list = captureList(() => artifactList([listItem()]));
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("table");
    const before = list.requests.length;

    await user.type(screen.getByRole("searchbox", { name: "Search" }), "harbour");

    await waitFor(() => expect(list.last().get("q")).toBe("harbour"));
    expect(list.requests.length - before).toBe(1); // one request, not one per keystroke
  });

  it("filters by review state, archive, analysis, problems, duplicates, type, and dates", async () => {
    const list = captureList((params) => {
      const items = [listItem()];
      return artifactList(items, {
        counts_by_review_state: { UNREVIEWED: 4, IN_REVIEW: 1, REVIEWED: 2, FLAGGED: 3, ARCHIVED: 5 },
        total: params.has("review_state") ? 3 : 10,
      });
    });
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("table");

    const flagged = screen.getByRole("button", { name: "Flagged (3)" });
    await user.click(flagged);
    await waitFor(() => expect(list.last().getAll("review_state")).toEqual(["FLAGGED"]));
    expect(flagged).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("checkbox", { name: /Show archived/ }));
    await waitFor(() => expect(list.last().get("include_archived")).toBe("true"));
    expect(screen.getByRole("checkbox", { name: "Show archived (5)" })).toBeChecked();

    await user.selectOptions(screen.getByRole("combobox", { name: "Analysis" }), "in_progress");
    await waitFor(() => expect(list.last().getAll("analysis_status")).toEqual(["queued", "running"]));

    await user.click(screen.getByRole("checkbox", { name: "Has problems" }));
    await user.click(screen.getByRole("checkbox", { name: "Has duplicate matches" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "File type" }), "image/png");
    await waitFor(() => {
      expect(list.last().get("has_problems")).toBe("true");
      expect(list.last().get("has_duplicates")).toBe("true");
      expect(list.last().getAll("mime_type")).toEqual(["image/png"]);
    });

    await user.type(screen.getByLabelText("Uploaded from"), "2026-11-01");
    await user.type(screen.getByLabelText("Uploaded to"), "2026-11-02");
    await waitFor(() => {
      expect(list.last().get("uploaded_from")).toBe(new Date(2026, 10, 1, 0, 0, 0, 0).toISOString());
      expect(list.last().get("uploaded_to")).toBe(new Date(2026, 10, 2, 23, 59, 59, 999).toISOString());
    });

    await user.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
    await waitFor(() => {
      const params = list.last();
      expect(params.has("review_state")).toBe(false);
      expect(params.get("include_archived")).toBe("false");
      expect(params.has("analysis_status")).toBe(false);
      expect(params.has("uploaded_from")).toBe(false);
    });
  });

  it("sorts by clicking column headers", async () => {
    const list = captureList(() => artifactList([listItem()]));
    const user = userEvent.setup();
    renderApp("/");
    const table = await screen.findByRole("table");

    expect(within(table).getByRole("columnheader", { name: /Uploaded/ })).toHaveAttribute("aria-sort", "descending");
    await user.click(within(table).getByRole("button", { name: /File/ }));
    await waitFor(() => expect(list.last().get("sort")).toBe("filename"));
    expect(list.last().get("order")).toBe("asc");
    expect(within(screen.getByRole("table")).getByRole("columnheader", { name: /File/ })).toHaveAttribute("aria-sort", "ascending");

    await user.click(within(screen.getByRole("table")).getByRole("button", { name: /File/ }));
    await waitFor(() => expect(list.last().get("order")).toBe("desc"));

    await user.click(within(screen.getByRole("table")).getByRole("button", { name: /Size/ }));
    await waitFor(() => expect(list.last().get("sort")).toBe("size_bytes"));
    await user.click(within(screen.getByRole("table")).getByRole("button", { name: /Review/ }));
    await waitFor(() => expect(list.last().get("sort")).toBe("review_state"));
  });

  it("pages through results", async () => {
    const list = captureList((params) => {
      const offset = Number(params.get("offset"));
      return artifactList([listItem({ filename: `row-${offset}.jpg` })], { total: 30, offset });
    });
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByText("row-0.jpg");
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("row-25.jpg")).toBeInTheDocument();
    expect(list.last().get("offset")).toBe("25");
    expect(screen.getByText("Showing 26–30 of 30 artifacts")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("restores the view from the URL", async () => {
    const list = captureList(() => artifactList([listItem()], { total: 60 }));
    renderApp("/?q=harbour&review=FLAGGED&review=IN_REVIEW&status=failed&archived=1&sort=filename&order=asc&page=2");
    await screen.findByRole("table");

    const params = list.last();
    expect(params.get("q")).toBe("harbour");
    expect(params.getAll("review_state")).toEqual(["FLAGGED", "IN_REVIEW"]);
    expect(params.getAll("analysis_status")).toEqual(["failed"]);
    expect(params.get("include_archived")).toBe("true");
    expect(params.get("sort")).toBe("filename");
    expect(params.get("order")).toBe("asc");
    expect(params.get("offset")).toBe("25");
    expect(screen.getByRole("searchbox", { name: "Search" })).toHaveValue("harbour");
    expect(screen.getByRole("button", { name: /Flagged/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Analysis" })).toHaveValue("failed");
  });

  it("shows an empty Library with an upload action", async () => {
    captureList(() => artifactList([]));
    renderApp("/");

    expect(await screen.findByText("No artifacts yet")).toBeInTheDocument();
    const empty = screen.getByText("No artifacts yet").parentElement!;
    expect(within(empty).getByRole("link", { name: "Upload an image" })).toHaveAttribute("href", "/upload");
  });

  it("shows when nothing matches, with a way to clear filters", async () => {
    const list = captureList((params) => artifactList(params.has("q") ? [] : [listItem({ filename: "kept.jpg" })]));
    const user = userEvent.setup();
    renderApp("/?q=nothing");

    expect(await screen.findByText("No artifacts match")).toBeInTheDocument();
    const empty = screen.getByText("No artifacts match").parentElement!;
    await user.click(within(empty).getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("kept.jpg")).toBeInTheDocument();
    expect(list.last().has("q")).toBe(false);
  });

  it("shows a loading state before the first page arrives", async () => {
    server.use(
      http.get(`${API}/artifacts`, async () => {
        await delay(100);
        return HttpResponse.json(artifactList([listItem({ filename: "late.jpg" })]));
      }),
    );
    renderApp("/");

    expect(screen.getByRole("status", { name: "Loading the Library" })).toBeInTheDocument();
    expect(await screen.findByText("late.jpg")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Loading the Library" })).not.toBeInTheDocument();
  });

  it("shows errors with their code and retries", async () => {
    let calls = 0;
    server.use(
      http.get(`${API}/artifacts`, () => {
        calls += 1;
        return calls === 1
          ? apiError(500, "INTERNAL_ERROR", "Something went wrong on the server.")
          : HttpResponse.json(artifactList([listItem({ filename: "back.jpg" })]));
      }),
    );
    const user = userEvent.setup();
    renderApp("/");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The Library could not be loaded.");
    expect(alert).toHaveTextContent("Something went wrong on the server.");
    expect(alert).toHaveTextContent("Error code: INTERNAL_ERROR");
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("back.jpg")).toBeInTheDocument();
  });

  it("explains when the backend cannot be reached", async () => {
    server.use(http.get(`${API}/artifacts`, () => HttpResponse.error()));
    renderApp("/");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reach the Vestigo backend. Check that it is running on port 8400.");
    expect(alert).toHaveTextContent("NETWORK_ERROR");
  });
});
