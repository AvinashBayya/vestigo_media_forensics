import type { JobStatus, StageStatus } from "../api/types";

type Status = JobStatus | StageStatus;

const STYLES: Record<Status, { label: string; className: string }> = {
  pending: { label: "Waiting", className: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
  queued: { label: "Queued", className: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
  running: { label: "Running", className: "bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200" },
  succeeded: { label: "Done", className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200" },
  completed: { label: "Completed", className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200" },
  partial: { label: "Done with warnings", className: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100" },
  completed_with_errors: {
    label: "Completed with errors",
    className: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100",
  },
  failed: { label: "Failed", className: "bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-100" },
  skipped: { label: "Skipped", className: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400" },
};

export function StatusBadge({ status }: { status: Status }) {
  const style = STYLES[status];
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${style.className}`}>
      {style.label}
    </span>
  );
}
