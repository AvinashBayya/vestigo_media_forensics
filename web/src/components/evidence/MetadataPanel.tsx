import { useId, useState } from "react";

import type { MetadataSection, TagGroups } from "../../api/types";
import { countTags, formatValue } from "../../lib/format";
import { Panel } from "../Panel";

const TABS = [
  { key: "exif", label: "EXIF" },
  { key: "xmp", label: "XMP" },
  { key: "iptc", label: "IPTC" },
  { key: "other", label: "Other" },
  { key: "composite", label: "Composite" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export function MetadataPanel({ section }: { section: MetadataSection | null }) {
  const [active, setActive] = useState<TabKey>("exif");
  const baseId = useId();
  const activeLabel = TABS.find((tab) => tab.key === active)!.label;

  return (
    <Panel title="Embedded metadata" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <div role="tablist" aria-label="Metadata groups" className="flex flex-wrap gap-1">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                id={`${baseId}-${tab.key}`}
                aria-selected={active === tab.key}
                aria-controls={`${baseId}-panel`}
                onClick={() => setActive(tab.key)}
                className={`rounded-md px-2 py-1 text-xs font-medium ${
                  active === tab.key
                    ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
                }`}
              >
                {tab.label} ({countTags(section[tab.key])})
              </button>
            ))}
          </div>
          <div role="tabpanel" id={`${baseId}-panel`} aria-labelledby={`${baseId}-${active}`}>
            <TagGroupTables groups={section[active]} emptyLabel={`No ${activeLabel} metadata found.`} />
          </div>
          {active === "composite" && (
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Composite values are calculated by ExifTool from other tags; they are not stored in the file.
            </p>
          )}
        </>
      )}
    </Panel>
  );
}

function TagGroupTables({ groups, emptyLabel }: { groups: TagGroups; emptyLabel: string }) {
  const entries = Object.entries(groups);
  if (entries.length === 0) return <p>{emptyLabel}</p>;
  return (
    <div className="space-y-3">
      {entries.map(([group, tags]) => (
        <div key={group}>
          <h3 className="mb-1 font-mono text-xs font-medium text-slate-600 dark:text-slate-400">{group}</h3>
          <table className="w-full table-fixed text-xs">
            <tbody>
              {Object.entries(tags).map(([tag, value]) => (
                <tr key={tag} className="border-t border-slate-100 align-top dark:border-slate-800">
                  <th scope="row" className="w-2/5 py-1 pr-3 text-left font-medium break-words">
                    {tag}
                  </th>
                  <td className="py-1 font-mono break-all whitespace-pre-wrap">{formatValue(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
