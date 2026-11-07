import { useCallback, useEffect, useId, useState } from "react";

import { errorMessage, getCustody } from "../../api/client";
import type { CustodyDerivedFile, CustodyReport, CustodyTimelineEvent } from "../../api/types";
import { formatBytes, formatDateTime } from "../../lib/format";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";

const EVENT_LABELS: Record<string, string> = {
  uploaded: "Uploaded",
  analysis_started: "Analysis started",
  analysis_finished: "Analysis finished",
  review_changed: "Review changed",
  exported: "Evidence package exported",
  library_changed: "Duplicate library changed",
  preview_created: "Playable preview created",
  lead_recorded: "External lead recorded",
  lead_updated: "External lead edited",
  lead_deleted: "External lead deleted",
};

function shortHash(value: unknown): string {
  return typeof value === "string" ? `${value.slice(0, 12)}…` : "";
}

/** One factual line per event, from its recorded detail only. */
function eventSummary(event: CustodyTimelineEvent): string {
  const d = event.detail;
  switch (event.type) {
    case "uploaded":
      return `${String(d.filename)} · ${formatBytes(Number(d.size_bytes))} · SHA-256 ${shortHash(d.sha256)}`;
    case "analysis_started":
      return `${String(d.pipeline)} (job ${shortHash(d.job_id)})`;
    case "analysis_finished":
      return (
        `${String(d.pipeline)} ${String(d.status)} · ${String(d.evidence_records)} evidence records · ` +
        `${String(d.derived_files)} derived files` +
        (d.error_code ? ` · ${String(d.error_code)}` : "")
      );
    case "review_changed":
      return (
        `${String(d.origin)} review: ${String(d.from_state)} → ${String(d.to_state)}` +
        (d.stage ? ` (${String(d.stage)})` : "") +
        (d.notes_changed ? " · notes changed" : "")
      );
    case "exported":
      return (
        `package SHA-256 ${shortHash(d.package_sha256)} · original ` +
        (d.original_included ? "included" : "not included")
      );
    case "library_changed":
      return d.included_after ? "included in future duplicate searches" : "excluded from future duplicate searches";
    case "preview_created":
      return `viewing copy · ${formatBytes(Number(d.size_bytes))} · SHA-256 ${shortHash(d.sha256)}`;
    case "lead_recorded":
      return `${String(d.provider)}${d.derived_file_id ? " · from a keyframe" : ""}`;
    case "lead_updated":
      return `fields changed: ${Array.isArray(d.fields) ? d.fields.join(", ") : String(d.fields)}`;
    case "lead_deleted":
      return `${String(d.provider)} · earlier events for this lead remain above`;
    default:
      return JSON.stringify(d);
  }
}

interface ChainOfCustodyPanelProps {
  artifactId: string;
  /** Any value that changes when the timeline may have grown (new job, library toggle, preview). */
  refreshKey?: string;
}

export function ChainOfCustodyPanel({ artifactId, refreshKey }: ChainOfCustodyPanelProps) {
  const headingId = useId();
  const [custody, setCustody] = useState<CustodyReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setCustody(await getCustody(artifactId));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [artifactId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-lg border border-slate-200 bg-white shadow-xs dark:border-slate-800 dark:bg-slate-900"
    >
      <header className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <h2 id={headingId} className="font-medium">
          Chain of custody
        </h2>
      </header>
      <div className="space-y-4 px-4 py-3 text-sm">
        {error ? (
          <div role="alert" className="space-y-2">
            <p className="text-rose-800 dark:text-rose-300">The chain of custody could not be loaded: {error}</p>
            <button
              type="button"
              onClick={() => void load()}
              className="rounded-md border border-slate-300 px-2 py-0.5 font-medium dark:border-slate-600"
            >
              Retry
            </button>
          </div>
        ) : custody === null ? (
          <p className={MUTED}>Loading…</p>
        ) : (
          <>
            <p className={MUTED}>{custody.notice}</p>
            <ol aria-label="Custody timeline" className="space-y-2">
              {custody.events.map((event, index) => (
                <li key={`${event.at}-${event.type}-${index}`} className="flex min-w-0 items-baseline gap-2">
                  <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium dark:bg-slate-800">
                    {EVENT_LABELS[event.type] ?? event.type}
                  </span>
                  <span className="min-w-0 break-words">
                    <span className="font-mono text-xs">{formatDateTime(event.at)}</span>
                    {" · "}
                    {eventSummary(event)}
                  </span>
                </li>
              ))}
            </ol>
            <DerivedFileLineage files={custody.derived_files} />
          </>
        )}
      </div>
    </section>
  );
}

/** The recorded lineage as an indented tree: the original upload, then each file under its source. */
function DerivedFileLineage({ files }: { files: CustodyDerivedFile[] }) {
  if (files.length === 0) return null;
  const children = new Map<string, CustodyDerivedFile[]>();
  const roots: CustodyDerivedFile[] = [];
  for (const file of files) {
    if (file.source_kind === "derived_file" && file.source_derived_file_id) {
      const list = children.get(file.source_derived_file_id) ?? [];
      list.push(file);
      children.set(file.source_derived_file_id, list);
    } else {
      roots.push(file);
    }
  }
  return (
    <div>
      <h3 className="mb-1 font-medium">Derived files (recorded lineage)</h3>
      <ul aria-label="Derived-file lineage" className="space-y-1">
        <li className={MUTED}>original upload</li>
        {roots.map((file) => (
          <LineageRow key={file.derived_file_id} file={file} childrenOf={children} depth={1} />
        ))}
      </ul>
    </div>
  );
}

function LineageRow({
  file,
  childrenOf,
  depth,
}: {
  file: CustodyDerivedFile;
  childrenOf: Map<string, CustodyDerivedFile[]>;
  depth: number;
}) {
  return (
    <>
      <li className={MUTED} style={{ paddingLeft: `${depth}rem` }}>
        <span className="font-mono">{file.filename}</span> · {file.stage} · {file.kind} ·{" "}
        {formatBytes(file.size_bytes)} · <span className="font-mono">{file.sha256.slice(0, 12)}…</span>
        {file.source_kind === null && (
          <span className="ml-1 text-amber-800 dark:text-amber-300">· source not recorded (pre-M4B record)</span>
        )}
      </li>
      {(childrenOf.get(file.derived_file_id) ?? []).map((child) => (
        <LineageRow key={child.derived_file_id} file={child} childrenOf={childrenOf} depth={depth + 1} />
      ))}
    </>
  );
}
