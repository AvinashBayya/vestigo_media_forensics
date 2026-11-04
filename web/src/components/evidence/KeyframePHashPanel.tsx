import type { KeyframePHashSection } from "../../api/types";
import { formatSeconds } from "../../lib/format";
import { Panel } from "../Panel";

export function KeyframePHashPanel({ section }: { section: KeyframePHashSection | null }) {
  return (
    <Panel title="Keyframe perceptual hashes" provenance={section?.provenance ?? null}>
      {section && (
        <details>
          <summary className="cursor-pointer text-sm">
            {section.count} {section.count === 1 ? "hash" : "hashes"} ({section.algorithm}, {section.bits} bits)
          </summary>
          <ul className="mt-2 space-y-1 font-mono text-xs">
            {section.frames.map((frame) => (
              <li key={frame.seq}>
                {formatSeconds(frame.timestamp)} · {frame.value}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}
