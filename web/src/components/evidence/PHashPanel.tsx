import type { PerceptualHashSection } from "../../api/types";
import { Panel } from "../Panel";

export function PHashPanel({ section }: { section: PerceptualHashSection | null }) {
  return (
    <Panel title="Perceptual hash" provenance={section?.provenance ?? null}>
      {section && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-2">
          <dt className="font-medium">Value</dt>
          <dd className="font-mono">{section.value}</dd>
          <dt className="font-medium">Algorithm</dt>
          <dd>
            {section.algorithm}, {section.bits} bits
          </dd>
        </dl>
      )}
    </Panel>
  );
}
