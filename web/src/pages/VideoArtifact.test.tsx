import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { ARTIFACT_ID, DERIVED_KF_1, JOB_ID, jobHistoryItem, videoDetail, videoReport } from "../test/data";
import { renderApp } from "../test/render";
import { API, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

function serveVideo() {
  server.use(
    http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(videoDetail())),
    http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () => HttpResponse.json(videoReport())),
    http.get(`${API}/artifacts/${ARTIFACT_ID}/jobs`, () =>
      HttpResponse.json({ artifact_id: ARTIFACT_ID, jobs: [jobHistoryItem({ pipeline: "video.v1" })] }),
    ),
  );
}

describe("Video artifact page", () => {
  it("shows a playable preview, duration, and the video evidence sections", async () => {
    serveVideo();
    renderApp(PAGE);

    expect(await screen.findByRole("heading", { name: "scenes.mp4" })).toBeInTheDocument();
    expect(screen.getByText(/video\/mp4 .* 640×360 px · 0:09 · uploaded/)).toBeInTheDocument();
    const player = screen.getByLabelText("Preview of scenes.mp4");
    expect(player.tagName).toBe("VIDEO");
    expect(player).toHaveAttribute("controls");
    expect(player).toHaveAttribute("src", `/api/v1/artifacts/${ARTIFACT_ID}/content`);

    const mediaInfo = await screen.findByRole("region", { name: "Media information" });
    expect(mediaInfo).toHaveTextContent("QuickTime / MOV");
    expect(mediaInfo).toHaveTextContent("0:09 (container-reported, not decode-verified)");
    expect(mediaInfo).toHaveTextContent("Video: h264 (High) · 640×360 · 25 fps · yuv420p");
    expect(mediaInfo).toHaveTextContent("Audio: aac · 1 channel (mono) · 44100 Hz");
    expect(mediaInfo).toHaveTextContent("nothing is decoded or transcribed");

    const scenes = screen.getByRole("region", { name: "Scene changes" });
    expect(within(scenes).getByText("0:03")).toBeInTheDocument();
    expect(scenes).toHaveTextContent("score 0.5788");
    expect(scenes).toHaveTextContent("ordinary editing, not a sign of manipulation");

    const keyframes = screen.getByRole("region", { name: "Keyframes" });
    const thumbnails = within(keyframes).getAllByRole("img");
    expect(thumbnails[0]).toHaveAttribute(
      "src",
      `/api/v1/artifacts/${ARTIFACT_ID}/derived/${DERIVED_KF_1}/content`,
    );
    expect(keyframes).toHaveTextContent("first frame");
    expect(keyframes).toHaveTextContent("scene change (0.5788)");
    expect(keyframes).toHaveTextContent("8 of 8 selected frames extracted (limit 40)");

    // Content Credentials are validated for videos too (M4); image-only panels stay absent.
    expect(screen.getByRole("region", { name: "Content Credentials (C2PA)" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Text in image (OCR)" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Perceptual hash" })).not.toBeInTheDocument();
  });

  it("shows keyframe OCR as provisional and lists frame texts", async () => {
    serveVideo();
    renderApp(PAGE);

    const ocr = await screen.findByRole("region", { name: "Text in keyframes (OCR)" });
    expect(ocr).toHaveTextContent("Provisional:");
    expect(ocr).toHaveTextContent("best-effort automatic OCR of 2 sampled keyframes (limit 10)");
    expect(within(ocr).getAllByText("SCENE ONE").length).toBeGreaterThanOrEqual(1); // cleaned + raw
    expect(ocr).toHaveTextContent("Tesseract confidence 96% (the engine's own estimate)");
    expect(ocr).toHaveTextContent("No text was detected in this frame. This does not mean the frame contains no text.");
  });

  it("shows duplicate frame pairs against the matched video", async () => {
    serveVideo();
    const user = userEvent.setup();
    renderApp(PAGE);

    const duplicates = await screen.findByRole("region", { name: "Duplicate search (local library)" });
    expect(within(duplicates).getByRole("link", { name: "recoded.webm" })).toBeInTheDocument();
    expect(duplicates).toHaveTextContent("Video · Similar · distance 2/64");
    await user.click(within(duplicates).getByText("2 matching frame pairs"));
    expect(duplicates).toHaveTextContent("this video at 0:00 ↔ matched video at 0:00 · distance 0/64");
    expect(duplicates).toHaveTextContent(
      "this video at 0:03 ↔ matched video at 0:03.1 · distance 2/64 · rotated 270°",
    );
  });

  it("falls back with a create-preview offer when the browser cannot play the codec", async () => {
    let posted = false;
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () =>
        HttpResponse.json(videoDetail({ mime_type: "video/x-matroska", filename: "scenes.mkv" })),
      ),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () => HttpResponse.json(videoReport())),
      http.post(`${API}/artifacts/${ARTIFACT_ID}/preview`, () => {
        posted = true;
        return HttpResponse.json({
          artifact_id: ARTIFACT_ID,
          sha256: "ab".repeat(32),
          size_bytes: 1234,
          width: 640,
          height: 360,
          created_at: "2026-11-04T09:00:00Z",
        });
      }),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    const player = await screen.findByLabelText("Preview of scenes.mkv");
    player.dispatchEvent(new Event("error"));
    expect(
      await screen.findByText(/This video cannot be played in the browser .* The keyframes below show its content/),
    ).toBeInTheDocument();
    expect(screen.getByText(/not\s+evidence, is left out of the evidence package/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Create playable preview" }));

    const preview = await screen.findByLabelText("Preview of scenes.mkv");
    expect(posted).toBe(true);
    expect(preview).toHaveAttribute("src", `/api/v1/artifacts/${ARTIFACT_ID}/preview/content`);
    expect(screen.getByText(/Playing a re-encoded viewing copy — not the original evidence/)).toBeInTheDocument();
  });

  it("plays an existing viewing copy directly, clearly labelled", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () =>
        HttpResponse.json(videoDetail({ mime_type: "video/x-matroska", filename: "scenes.mkv", has_playable_preview: true })),
      ),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () => HttpResponse.json(videoReport())),
    );
    renderApp(PAGE);

    const player = await screen.findByLabelText("Preview of scenes.mkv");
    expect(player).toHaveAttribute("src", `/api/v1/artifacts/${ARTIFACT_ID}/preview/content`);
    expect(screen.getByText(/re-encoded viewing copy — not the original evidence/)).toBeInTheDocument();
  });

  it("re-runs analysis through the video endpoint", async () => {
    serveVideo();
    let posted: unknown = null;
    server.use(
      http.post(`${API}/analysis/video`, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json({ job_id: JOB_ID, artifact_id: ARTIFACT_ID, status: "queued" }, { status: 202 });
      }),
      http.get(`${API}/analysis/jobs/${JOB_ID}`, () =>
        HttpResponse.json({
          job_id: JOB_ID,
          artifact_id: ARTIFACT_ID,
          pipeline: "video.v1",
          status: "running",
          created_at: "2026-11-04T09:00:00Z",
          started_at: "2026-11-04T09:00:00Z",
          completed_at: null,
          error: null,
          stages: [{ stage: "media_info", status: "running", started_at: null, completed_at: null }],
        }),
      ),
    );
    const user = userEvent.setup();
    renderApp(PAGE);

    await user.click(await screen.findByRole("button", { name: "Run analysis again" }));
    expect(await screen.findByText("Media information")).toBeInTheDocument();
    expect(posted).toEqual({ artifact_id: ARTIFACT_ID });
  });
});
