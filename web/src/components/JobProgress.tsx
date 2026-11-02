import type { JobStatusResponse } from "../api/types";
import { STAGE_LABELS } from "../lib/format";
import { StatusBadge } from "./StatusBadge";

export function JobProgress({ job }: { job: JobStatusResponse }) {
  return (
    <section
      aria-live="polite"
      aria-label="Analysis progress"
      className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-medium">Analysis in progress</h2>
        <StatusBadge status={job.status} />
      </div>
      <ol className="space-y-2 text-sm">
        {job.stages.map((stage) => (
          <li key={stage.stage} className="flex items-center justify-between gap-3">
            <span>{STAGE_LABELS[stage.stage] ?? stage.stage}</span>
            <StatusBadge status={stage.status} />
          </li>
        ))}
      </ol>
    </section>
  );
}
