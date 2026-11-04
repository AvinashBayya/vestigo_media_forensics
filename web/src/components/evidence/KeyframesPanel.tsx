import { derivedContentUrl } from "../../api/client";
import type { KeyframeInfo, KeyframesSection } from "../../api/types";
import { formatSeconds } from "../../lib/format";
import { Panel } from "../Panel";

function reasonLabel(frame: KeyframeInfo): string {
  if (frame.reason === "first_frame") return "first frame";
  if (frame.reason === "scene_change") return `scene change${frame.scene_score ? ` (${frame.scene_score})` : ""}`;
  if (frame.reason === "uniform_sample") return "even sample";
  return frame.reason;
}

export function KeyframesPanel({ artifactId, section }: { artifactId: string; section: KeyframesSection | null }) {
  return (
    <Panel title="Keyframes" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {section.frames.map((frame) => (
              <li key={frame.seq} className="space-y-1">
                {frame.derived_file_id && (
                  <img
                    src={derivedContentUrl(artifactId, frame.derived_file_id)}
                    alt={`Keyframe at ${formatSeconds(frame.timestamp)}`}
                    className="w-full rounded bg-slate-100 object-contain dark:bg-slate-800"
                  />
                )}
                <p className="text-xs text-slate-600 dark:text-slate-400">
                  <span className="font-mono">{formatSeconds(frame.timestamp)}</span> · {reasonLabel(frame)}
                </p>
              </li>
            ))}
          </ul>
          <p className="text-xs text-slate-600 dark:text-slate-400">
            {section.extracted} of {section.requested} selected frames extracted (limit{" "}
            {String(section.policy.max_keyframes ?? "—")}). Keyframes are a bounded sample; content between
            them is not shown.
          </p>
        </>
      )}
    </Panel>
  );
}
