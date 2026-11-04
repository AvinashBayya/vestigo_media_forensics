import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { KeyframeOCRFrame } from "../api/types";
import { ARTIFACT_ID, provenance, videoDetail, videoReport } from "../test/data";
import { renderApp } from "../test/render";
import { API, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

function ocrFrame(overrides: Partial<KeyframeOCRFrame>): KeyframeOCRFrame {
  return {
    seq: 1,
    timestamp: 0,
    text: "",
    cleaned_text: null,
    cleaning: [],
    confidence: null,
    word_count: 0,
    preprocessing: [],
    candidates: [],
    selected: { variant: "grayscale", reason: "r" },
    ...overrides,
  };
}

function serveOCR(frames: KeyframeOCRFrame[], options: { errors?: { type: string; message: string }[] } = {}) {
  const base = videoReport();
  const keyframes = {
    ...base.keyframes!,
    requested: 4,
    extracted: 4,
    frames: [1, 2, 3, 4].map((seq) => ({
      seq,
      timestamp: (seq - 1) * 3,
      reason: "uniform_sample",
      scene_score: null,
      derived_file_id: `df_${String(seq).repeat(32)}`,
      width: 640,
      height: 360,
    })),
  };
  server.use(
    http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(videoDetail())),
    http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
      HttpResponse.json(
        videoReport({
          keyframes,
          keyframe_ocr: {
            engine: "tesseract",
            languages: ["eng"],
            frame_limit: 3,
            analyzed: frames.length,
            frames,
            provenance: provenance("keyframe_ocr", {
              status: options.errors?.length ? "partial" : "succeeded",
              errors: options.errors ?? [],
            }),
          },
        }),
      ),
    ),
  );
}

describe("Keyframe OCR clarity", () => {
  it("shows a prominent provisional warning and a status row for every keyframe", async () => {
    serveOCR([
      ocrFrame({
        seq: 1,
        text: "CAPTION HERE",
        cleaned_text: "CAPTION HERE",
        confidence: 0.91,
        word_count: 2,
      }),
      ocrFrame({ seq: 2, timestamp: 3 }),
      ocrFrame({ seq: 3, timestamp: 6, text: "RAW ~ TEXT", cleaned_text: "RAW TEXT", confidence: 0.6 }),
    ]);
    const user = userEvent.setup();
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Text in keyframes (OCR)" });
    expect(panel).toHaveTextContent("Provisional:");
    expect(panel).toHaveTextContent("not a verified transcription");

    const statusList = within(panel).getByRole("list", { name: "Keyframe OCR status" });
    const rows = within(statusList).getAllByRole("listitem");
    expect(rows).toHaveLength(4); // every keyframe, analysed or not

    // Frame 1: ran, text found, confidence labelled, thumbnail beside the text.
    expect(rows[0]).toHaveTextContent("#1 · 0:00 · OCR ran · Tesseract confidence 91% (the engine's own estimate)");
    expect(within(rows[0]).getAllByText("CAPTION HERE").length).toBeGreaterThanOrEqual(1); // cleaned + raw
    expect(within(rows[0]).getByRole("img")).toHaveAttribute(
      "src",
      `/api/v1/artifacts/${ARTIFACT_ID}/derived/df_${"1".repeat(32)}/content`,
    );

    // Frame 2: ran, no text — worded so it does not imply the frame contains none.
    expect(rows[1]).toHaveTextContent("OCR ran");
    expect(rows[1]).toHaveTextContent(
      "No text was detected in this frame. This does not mean the frame contains no text.",
    );

    // Frame 3: cleaned text shown, raw available in an expandable section.
    expect(within(rows[2]).getByText("RAW TEXT")).toBeInTheDocument();
    await user.click(within(rows[2]).getByText("Raw OCR output (unchanged)"));
    expect(within(rows[2]).getByText("RAW ~ TEXT")).toBeInTheDocument();

    // Frame 4: not analysed, with the reason.
    expect(rows[3]).toHaveTextContent("#4 · 0:09");
    expect(rows[3]).toHaveTextContent("Not analysed — outside the 3-frame OCR limit for this analysis.");
    expect(rows[3]).not.toHaveTextContent("OCR ran");
  });

  it("ties a recorded frame failure to its row", async () => {
    serveOCR([ocrFrame({ seq: 1, text: "OK", confidence: 0.8 })], {
      errors: [
        {
          type: "OCR_FRAME_FAILED",
          message: "OCR failed on the keyframe at 3.000 s: Tesseract exited with code 1 (boom).",
        },
      ],
    });
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Text in keyframes (OCR)" });
    const statusList = within(panel).getByRole("list", { name: "Keyframe OCR status" });
    const failedRow = within(statusList)
      .getAllByRole("listitem")
      .find((row) => row.textContent?.includes("#2"))!;
    expect(failedRow).toHaveTextContent("OCR failed on this frame:");
    expect(failedRow).toHaveTextContent("Tesseract exited with code 1 (boom).");
  });

  it("shows the disabled state with its reason", async () => {
    const base = videoReport();
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(videoDetail())),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          videoReport({
            keyframe_ocr: {
              ...base.keyframe_ocr!,
              frames: [],
              analyzed: 0,
              provenance: provenance("keyframe_ocr", {
                status: "skipped",
                tool_version: null,
                skip_reason: "Disabled by the analysis option 'keyframe_ocr'.",
              }),
            },
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Text in keyframes (OCR)" });
    expect(panel).toHaveTextContent("Skipped. Disabled by the analysis option 'keyframe_ocr'.");
    expect(panel).not.toHaveTextContent("Provisional:");
  });
});
