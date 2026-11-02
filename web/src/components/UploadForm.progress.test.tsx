import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderApp } from "../test/render";

const uploadArtifact = vi.hoisted(() => vi.fn());

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  uploadArtifact,
}));

describe("UploadForm progress", () => {
  it("shows upload progress while the file is sent", async () => {
    uploadArtifact.mockImplementation((_file: File, onProgress: (percent: number) => void) => {
      onProgress(42);
      return new Promise(() => {}); // still uploading
    });
    const user = userEvent.setup();
    renderApp("/");

    await user.upload(
      screen.getByLabelText(/choose an image/i),
      new File([new Uint8Array([1, 2, 3])], "big.png", { type: "image/png" }),
    );
    await user.click(screen.getByRole("button", { name: "Upload and analyse" }));

    const bar = await screen.findByRole("progressbar", { name: "Upload progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByText("Uploading… 42%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload and analyse" })).toBeDisabled();
  });
});
