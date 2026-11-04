import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { KeyframeInfo } from "../api/types";
import { ARTIFACT_ID, JOB_ID, jobHistoryItem, videoDetail, videoReport } from "../test/data";
import { renderApp } from "../test/render";
import { API, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;
const OLD_JOB = "job_55555555555555555555555555555555";

function frame(overrides: Partial<KeyframeInfo>): KeyframeInfo {
  return {
    seq: 1,
    timestamp: 0,
    reason: "first_frame",
    scene_score: null,
    derived_file_id: "df_" + "9".repeat(32),
    width: 640,
    height: 360,
    ...overrides,
  };
}

function serve(frames: KeyframeInfo[], extracted = frames.length) {
  const base = videoReport();
  server.use(
    http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(videoDetail())),
    http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
      HttpResponse.json(
        videoReport({
          keyframes: { ...base.keyframes!, frames, extracted, requested: Math.max(extracted, frames.length) },
        }),
      ),
    ),
  );
}

describe("Keyframes panel", () => {
  it("shows every frame with number, m:ss timestamp, reason, and score", async () => {
    serve([
      frame({ seq: 1, timestamp: 0, reason: "first_frame", derived_file_id: "df_" + "1".repeat(32) }),
      frame({
        seq: 2,
        timestamp: 63.5,
        reason: "scene_change",
        scene_score: 0.82,
        derived_file_id: "df_" + "2".repeat(32),
      }),
      frame({ seq: 3, timestamp: 125.2, reason: "uniform_sample", derived_file_id: "df_" + "3".repeat(32) }),
    ]);
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Keyframes" });
    expect(panel).toHaveTextContent("#1 · 0:00 · first frame");
    expect(panel).toHaveTextContent("#2 · 1:03.5 · scene change (0.82)");
    expect(panel).toHaveTextContent("#3 · 2:05.2 · uniform sample");
    const images = within(panel).getAllByRole("img");
    expect(images).toHaveLength(3);
    expect(images[0]).toHaveAttribute(
      "src",
      `/api/v1/artifacts/${ARTIFACT_ID}/derived/df_${"1".repeat(32)}/content`,
    );
    expect(images[1]).toHaveAccessibleName("Keyframe 2 at 1:03.5");
  });

  it("renders portrait and landscape frames in the same grid", async () => {
    serve([
      frame({ seq: 1, width: 640, height: 360 }),
      frame({ seq: 2, width: 360, height: 640, derived_file_id: "df_" + "4".repeat(32) }),
    ]);
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Keyframes" });
    const images = within(panel).getAllByRole("img");
    expect(images).toHaveLength(2);
    for (const image of images) {
      // Fixed-aspect cells keep tall portrait frames from breaking the grid.
      expect(image.parentElement!.className).toContain("aspect-video");
      expect(image.className).toContain("object-contain");
    }
  });

  it("shows a clear empty state when no keyframes exist", async () => {
    serve([], 0);
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Keyframes" });
    expect(panel).toHaveTextContent("No keyframes were extracted for this analysis.");
    expect(within(panel).queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows an error with retry when a thumbnail fails to load", async () => {
    serve([frame({ seq: 1 })]);
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Keyframes" });
    const image = within(panel).getByRole("img");
    const originalSrc = image.getAttribute("src")!;
    image.dispatchEvent(new Event("error"));

    const alertBox = await within(panel).findByRole("alert");
    expect(alertBox).toHaveTextContent("Thumbnail could not be loaded.");
    await user.click(within(alertBox).getByRole("button", { name: "Retry" }));

    const retried = within(panel).getByRole("img");
    expect(retried).toHaveAttribute("src", `${originalSrc}?r=1`); // cache-busting reload
    expect(panel).toHaveTextContent("#1 · 0:00 · first frame"); // caption stays
  });

  it("keeps keyframes tied to the analysis being viewed when switching jobs", async () => {
    const base = videoReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(videoDetail())),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/jobs`, () =>
        HttpResponse.json({
          artifact_id: ARTIFACT_ID,
          jobs: [
            jobHistoryItem({ pipeline: "video.v1" }),
            jobHistoryItem({ job_id: OLD_JOB, created_at: "2026-11-03T09:00:00Z", pipeline: "video.v1" }),
          ],
        }),
      ),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, ({ request }) => {
        const jobId = new URL(request.url).searchParams.get("job_id") ?? JOB_ID;
        const derived = jobId === OLD_JOB ? "df_" + "a".repeat(32) : "df_" + "b".repeat(32);
        const report = videoReport({
          job_id: jobId,
          keyframes: {
            ...base.keyframes!,
            frames: [frame({ seq: 1, derived_file_id: derived })],
            extracted: 1,
            requested: 1,
          },
        });
        report.job = { ...report.job, job_id: jobId };
        return HttpResponse.json(report);
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Keyframes" });
    expect(within(panel).getByRole("img")).toHaveAttribute(
      "src",
      expect.stringContaining("b".repeat(32)),
    );

    const history = screen.getByRole("region", { name: "Analysis history" });
    await user.click(within(history).getByRole("button", { name: "View this analysis" }));

    const switched = await screen.findByRole("region", { name: "Keyframes" });
    expect(await within(switched).findByRole("img")).toHaveAttribute(
      "src",
      expect.stringContaining("a".repeat(32)),
    );
  });
});
