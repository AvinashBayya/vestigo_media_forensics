import type { SceneChangesSection } from "../../api/types";
import { formatSeconds } from "../../lib/format";
import { Panel } from "../Panel";

export function SceneChangesPanel({ section }: { section: SceneChangesSection | null }) {
  return (
    <Panel title="Scene changes" provenance={section?.provenance ?? null}>
      {section && (
        <>
          {section.count === 0 ? (
            <p>No scene changes above the threshold were detected.</p>
          ) : (
            <ul className="space-y-1">
              {section.changes.map((change) => (
                <li key={change.time}>
                  <span className="font-mono">{formatSeconds(change.time)}</span>
                  <span className="text-xs text-slate-600 dark:text-slate-400"> · score {change.score}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-slate-600 dark:text-slate-400">
            Frame-difference score above {section.threshold ?? "—"}. Scene changes are ordinary editing, not a
            sign of manipulation.
          </p>
        </>
      )}
    </Panel>
  );
}
