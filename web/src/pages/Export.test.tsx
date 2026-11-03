import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ARTIFACT_ID, JOB_ID } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;
const HASH = "ab".repeat(32);

describe("Evidence export", () => {
  const saved: string[] = [];
  beforeEach(() => {
    saved.length = 0;
    // jsdom has no object URLs and does not navigate on download clicks.
    URL.createObjectURL = vi.fn(() => "blob:package");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(this.download);
    });
  });
  afterEach(() => vi.restoreAllMocks());

  function servePackage(seen: URLSearchParams[]) {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/export`, ({ request }) => {
        seen.push(new URL(request.url).searchParams);
        return new HttpResponse(new Uint8Array([0x50, 0x4b, 3, 4]), {
          headers: {
            "Content-Type": "application/zip",
            "Content-Disposition": `attachment; filename="vestigo-evidence-${ARTIFACT_ID}-${JOB_ID}.zip"`,
            "X-Vestigo-Export-SHA256": HASH,
          },
        });
      }),
    );
  }

  it("downloads the package without the original by default and shows its SHA-256", async () => {
    const seen: URLSearchParams[] = [];
    servePackage(seen);
    const user = userEvent.setup();
    renderApp(PAGE);

    const menu = await screen.findByRole("region", { name: "Export evidence" });
    expect(within(menu).getByRole("link", { name: "Download JSON report" })).toHaveAttribute(
      "href",
      `${API}/artifacts/${ARTIFACT_ID}/evidence?job_id=${JOB_ID}&download=true`,
    );
    expect(within(menu).getByRole("checkbox", { name: "Include the original file" })).not.toBeChecked();
    await user.click(within(menu).getByRole("button", { name: "Download evidence package (ZIP)" }));

    const status = await within(menu).findByRole("status");
    expect(status).toHaveTextContent(`Downloaded vestigo-evidence-${ARTIFACT_ID}-${JOB_ID}.zip.`);
    expect(status).toHaveTextContent(`Package SHA-256: ${HASH}`);
    expect(seen[0].get("job_id")).toBe(JOB_ID);
    expect(seen[0].get("include_original")).toBe("false");
    expect(saved).toEqual([`vestigo-evidence-${ARTIFACT_ID}-${JOB_ID}.zip`]);
  });

  it("includes the original only when chosen", async () => {
    const seen: URLSearchParams[] = [];
    servePackage(seen);
    const user = userEvent.setup();
    renderApp(PAGE);

    const menu = await screen.findByRole("region", { name: "Export evidence" });
    await user.click(within(menu).getByRole("checkbox", { name: "Include the original file" }));
    await user.click(within(menu).getByRole("button", { name: "Download evidence package (ZIP)" }));
    await within(menu).findByRole("status");
    expect(seen[0].get("include_original")).toBe("true");
  });

  it("shows the server's error message when the export fails", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/export`, () =>
        apiError(500, "EXPORT_FAILED", "The evidence package could not be written. No package was created."),
      ),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const menu = await screen.findByRole("region", { name: "Export evidence" });
    await user.click(within(menu).getByRole("button", { name: "Download evidence package (ZIP)" }));
    expect(await within(menu).findByRole("alert")).toHaveTextContent(
      "The evidence package could not be written. No package was created.",
    );
    expect(saved).toEqual([]);
  });
});
