import { useState } from "react";

import { derivedContentUrl } from "../../api/client";
import type { KeyframeInfo, KeyframesSection } from "../../api/types";
import { formatSeconds } from "../../lib/format";
import { Panel } from "../Panel";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";

function reasonLabel(frame: KeyframeInfo): string {
  if (frame.reason === "first_frame") return "first frame";
  if (frame.reason === "scene_change") return `scene change${frame.scene_score ? ` (${frame.scene_score})` : ""}`;
  if (frame.reason === "uniform_sample") return "uniform sample";
  return frame.reason;
}

export function KeyframesPanel({ artifactId, section }: { artifactId: string; section: KeyframesSection | null }) {
  return (
    <Panel title="Keyframes" provenance={section?.provenance ?? null}>
      {section &&
        (section.frames.length === 0 ? (
          <p>
            No keyframes were extracted for this analysis. Run the analysis again to extract keyframes
            from the current file.
          </p>
        ) : (
          <>
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {section.frames.map((frame) => (
                <li key={frame.seq} className="min-w-0 space-y-1">
                  {frame.derived_file_id && (
                    <KeyframeThumbnail
                      src={derivedContentUrl(artifactId, frame.derived_file_id)}
                      alt={`Keyframe ${frame.seq} at ${formatSeconds(frame.timestamp)}`}
                    />
                  )}
                  <p className={MUTED}>
                    #{frame.seq} · <span className="font-mono">{formatSeconds(frame.timestamp)}</span> ·{" "}
                    {reasonLabel(frame)}
                  </p>
                </li>
              ))}
            </ul>
            <p className={MUTED}>
              {section.extracted} of {section.requested} selected frames extracted (limit{" "}
              {String(section.policy.max_keyframes ?? "—")}). Keyframes are a bounded sample; content
              between them is not shown, and they say nothing about authenticity or manipulation.
            </p>
          </>
        ))}
    </Panel>
  );
}

/**
 * One thumbnail in a fixed-aspect cell, so portrait and landscape frames share a tidy grid with no
 * horizontal scrolling. A load failure shows an inline error with Retry (cache-busting reload).
 */
function KeyframeThumbnail({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  if (failed) {
    return (
      <div
        role="alert"
        className="flex aspect-video w-full flex-col items-center justify-center gap-1 rounded bg-slate-100 p-2 text-center text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-400"
      >
        <span>Thumbnail could not be loaded.</span>
        <button
          type="button"
          onClick={() => {
            setFailed(false);
            setAttempt((n) => n + 1);
          }}
          className="rounded-md border border-slate-300 px-2 py-0.5 font-medium text-slate-900 dark:border-slate-600 dark:text-slate-100"
        >
          Retry
        </button>
      </div>
    );
  }
  return (
    <div className="flex aspect-video w-full items-center justify-center overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
      <img
        src={attempt === 0 ? src : `${src}?r=${attempt}`}
        alt={alt}
        loading="lazy"
        onError={() => setFailed(true)}
        className="max-h-full max-w-full object-contain"
      />
    </div>
  );
}
