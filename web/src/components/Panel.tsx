import { useId, type ReactNode } from "react";

import type { Provenance } from "../api/types";
import { CLASSIFICATION_LABELS, REVIEW_LABELS, formatBytes, formatDateTime } from "../lib/format";
import { StatusBadge } from "./StatusBadge";

interface PanelProps {
  title: string;
  provenance: Provenance | null;
  children?: ReactNode;
}

/** A report section: its findings, any errors, and how they were produced. */
export function Panel({ title, provenance, children }: PanelProps) {
  const headingId = useId();
  const status = provenance?.status;
  const hasFindings = status === "succeeded" || status === "partial";

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-lg border border-slate-200 bg-white shadow-xs dark:border-slate-800 dark:bg-slate-900"
    >
      <header className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <h2 id={headingId} className="font-medium">
          {title}
        </h2>
        {provenance && <StatusBadge status={provenance.status} />}
      </header>
      <div className="space-y-3 px-4 py-3 text-sm">
        {!provenance && <p className="text-slate-600 dark:text-slate-400">This check did not run.</p>}
        {status === "skipped" && (
          <p className="text-slate-600 dark:text-slate-400">Skipped. {provenance?.skip_reason}</p>
        )}
        {provenance && provenance.errors.length > 0 && (
          <div className="rounded-md bg-amber-50 px-3 py-2 text-amber-950 dark:bg-amber-950 dark:text-amber-100">
            <p className="font-medium">{status === "failed" ? "This check failed:" : "Warnings:"}</p>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {provenance.errors.map((error, index) => (
                <li key={index}>
                  <span className="font-mono text-xs">{error.type}</span> — {error.message}
                </li>
              ))}
            </ul>
          </div>
        )}
        {hasFindings && children}
      </div>
      {provenance && <ProvenanceFooter provenance={provenance} />}
    </section>
  );
}

function ProvenanceFooter({ provenance }: { provenance: Provenance }) {
  const tool = provenance.tool_version ? `${provenance.tool} ${provenance.tool_version}` : provenance.tool;
  return (
    <footer className="border-t border-slate-200 px-4 py-2 text-xs text-slate-600 dark:border-slate-800 dark:text-slate-400">
      <p>
        {tool} · {formatDateTime(provenance.completed_at)} · Review: {REVIEW_LABELS[provenance.review_state]}
      </p>
      <details className="mt-1">
        <summary className="cursor-pointer text-slate-700 dark:text-slate-300">
          Method and limitations ({provenance.limitations.length})
        </summary>
        <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
          <dt className="font-medium">Method</dt>
          <dd>{provenance.method}</dd>
          <dt className="font-medium">Evidence type</dt>
          <dd>{CLASSIFICATION_LABELS[provenance.classification]}</dd>
          <dt className="font-medium">Source</dt>
          <dd className="font-mono">{provenance.source}</dd>
          <dt className="font-medium">Started</dt>
          <dd>{formatDateTime(provenance.started_at)}</dd>
          <dt className="font-medium">Completed</dt>
          <dd>{formatDateTime(provenance.completed_at)}</dd>
          <dt className="font-medium">Record</dt>
          <dd className="font-mono">{provenance.evidence_id}</dd>
        </dl>
        <p className="mt-2 font-medium">Limitations</p>
        <ul className="mt-1 list-disc space-y-1 pl-5">
          {provenance.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
        {provenance.derived_files.length > 0 && (
          <>
            <p className="mt-2 font-medium">Raw tool output kept</p>
            <ul className="mt-1 space-y-1">
              {provenance.derived_files.map((file) => (
                <li key={file.derived_file_id} className="font-mono">
                  {file.kind} · {formatBytes(file.size_bytes)} · sha256 {file.sha256.slice(0, 16)}…
                </li>
              ))}
            </ul>
          </>
        )}
      </details>
    </footer>
  );
}
