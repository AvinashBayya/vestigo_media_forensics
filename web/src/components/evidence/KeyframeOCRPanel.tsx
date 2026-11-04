import { derivedContentUrl } from "../../api/client";
import type { KeyframeOCRFrame, KeyframeOCRSection, KeyframesSection } from "../../api/types";
import { formatPercent, formatSeconds } from "../../lib/format";
import { Panel } from "../Panel";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";

/** The stage writes frame failures as "… at {timestamp} s: …", which ties an error to its frame. */
function errorForTimestamp(section: KeyframeOCRSection, timestamp: number): string | null {
  for (const error of section.provenance.errors) {
    const match = /at (\d+(?:\.\d+)?) s/.exec(error.message);
    if (match && Math.abs(Number(match[1]) - timestamp) < 0.01) return error.message;
  }
  return null;
}

interface KeyframeOCRPanelProps {
  artifactId: string;
  section: KeyframeOCRSection | null;
  /** The same analysis's keyframes, for thumbnails and for frames outside the OCR limit. */
  keyframes: KeyframesSection | null;
}

export function KeyframeOCRPanel({ artifactId, section, keyframes }: KeyframeOCRPanelProps) {
  const ocrBySeq = new Map((section?.frames ?? []).map((frame) => [frame.seq, frame]));
  // Every keyframe gets a status row; fall back to the OCR frames alone if keyframes are missing.
  const allFrames: { seq: number; timestamp: number; derived_file_id: string | null }[] =
    keyframes?.frames ?? section?.frames.map((f) => ({ seq: f.seq, timestamp: f.timestamp, derived_file_id: null })) ?? [];

  return (
    <Panel title="Text in keyframes (OCR)" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
            <span className="font-medium">Provisional:</span> best-effort automatic OCR of{" "}
            {section.analyzed} sampled {section.analyzed === 1 ? "keyframe" : "keyframes"} (limit{" "}
            {section.frame_limit}), not a verified transcription. Text can be missed or misread —
            check it against the frames.
          </p>
          <ul aria-label="Keyframe OCR status" className="space-y-3">
            {allFrames.map((frame) => (
              <FrameStatus
                key={frame.seq}
                artifactId={artifactId}
                frame={frame}
                ocr={ocrBySeq.get(frame.seq)}
                section={section}
              />
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}

function FrameStatus({
  artifactId,
  frame,
  ocr,
  section,
}: {
  artifactId: string;
  frame: { seq: number; timestamp: number; derived_file_id: string | null };
  ocr: KeyframeOCRFrame | undefined;
  section: KeyframeOCRSection;
}) {
  const error = ocr ? null : errorForTimestamp(section, frame.timestamp);
  return (
    <li className="flex min-w-0 items-start gap-3">
      {frame.derived_file_id && (
        <img
          src={derivedContentUrl(artifactId, frame.derived_file_id)}
          alt={`Keyframe ${frame.seq} at ${formatSeconds(frame.timestamp)}`}
          loading="lazy"
          className="w-24 shrink-0 rounded bg-slate-100 object-contain dark:bg-slate-800"
        />
      )}
      <div className="min-w-0 flex-1 space-y-1">
        <p className={MUTED}>
          #{frame.seq} · <span className="font-mono">{formatSeconds(frame.timestamp)}</span>
          {ocr && " · OCR ran"}
          {ocr?.confidence != null &&
            ` · Tesseract confidence ${formatPercent(ocr.confidence)} (the engine's own estimate)`}
          {ocr?.selected && ` · ${ocr.selected.variant} pass`}
        </p>
        {ocr ? (
          ocr.text ? (
            <>
              <pre className="max-h-40 overflow-auto rounded-md bg-slate-100 p-2 font-mono text-sm whitespace-pre-wrap dark:bg-slate-800">
                {ocr.cleaned_text ?? ocr.text}
              </pre>
              <details className={MUTED}>
                <summary className="cursor-pointer">Raw OCR output (unchanged)</summary>
                <pre className="mt-1 max-h-40 overflow-auto rounded-md bg-slate-100 p-2 font-mono whitespace-pre-wrap dark:bg-slate-800">
                  {ocr.text}
                </pre>
              </details>
            </>
          ) : (
            <p className="text-sm">
              No text was detected in this frame. This does not mean the frame contains no text.
            </p>
          )
        ) : error ? (
          <p className="text-sm text-rose-800 dark:text-rose-300">OCR failed on this frame: {error}</p>
        ) : (
          <p className={MUTED}>
            Not analysed — outside the {section.frame_limit}-frame OCR limit for this analysis.
          </p>
        )}
      </div>
    </li>
  );
}
