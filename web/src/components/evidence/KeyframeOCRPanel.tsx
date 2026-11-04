import type { KeyframeOCRFrame, KeyframeOCRSection } from "../../api/types";
import { formatPercent, formatSeconds } from "../../lib/format";
import { Panel } from "../Panel";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";

export function KeyframeOCRPanel({ section }: { section: KeyframeOCRSection | null }) {
  const withText = section?.frames.filter((frame) => frame.text) ?? [];
  const empty = (section?.frames.length ?? 0) - withText.length;
  return (
    <Panel title="Text in keyframes (OCR)" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <p className="rounded-md bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800">
            <span className="font-medium">Provisional:</span> best-effort automatic OCR of{" "}
            {section.analyzed} sampled {section.analyzed === 1 ? "keyframe" : "keyframes"} (limit{" "}
            {section.frame_limit}), not a verified transcription. Check the text against the frames.
          </p>
          {withText.length === 0 ? (
            <p>No text was detected in the analysed keyframes.</p>
          ) : (
            <ul className="space-y-2">
              {withText.map((frame) => (
                <FrameText key={frame.seq} frame={frame} />
              ))}
            </ul>
          )}
          {empty > 0 && withText.length > 0 && (
            <p className={MUTED}>
              {empty} analysed {empty === 1 ? "frame" : "frames"} had no readable text.
            </p>
          )}
        </>
      )}
    </Panel>
  );
}

function FrameText({ frame }: { frame: KeyframeOCRFrame }) {
  return (
    <li>
      <p className={MUTED}>
        <span className="font-mono">{formatSeconds(frame.timestamp)}</span>
        {frame.confidence !== null && ` · Tesseract confidence ${formatPercent(frame.confidence)} (the engine's own estimate)`}
        {frame.selected && ` · ${frame.selected.variant} pass`}
      </p>
      <pre className="max-h-40 overflow-auto rounded-md bg-slate-100 p-2 font-mono text-sm whitespace-pre-wrap dark:bg-slate-800">
        {frame.cleaned_text ?? frame.text}
      </pre>
    </li>
  );
}
