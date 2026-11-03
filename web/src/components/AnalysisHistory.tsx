import type { JobHistoryItem } from "../api/types";
import { formatDateTime } from "../lib/format";
import { ProblemIndicator } from "./library/ArtifactTable";
import { StatusBadge } from "./StatusBadge";

interface AnalysisHistoryProps {
  jobs: JobHistoryItem[];
  viewingJobId: string | null;
  onView: (jobId: string) => void;
}

/** Every analysis run, newest first. Finished runs can be opened; earlier evidence is kept. */
export function AnalysisHistory({ jobs, viewingJobId, onView }: AnalysisHistoryProps) {
  if (jobs.length === 0) return null;
  return (
    <section aria-label="Analysis history" className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="font-medium">Analysis history</h2>
      <ol className="space-y-2">
        {jobs.map((job, index) => {
          const finished = job.status !== "queued" && job.status !== "running";
          const viewing = job.job_id === viewingJobId;
          return (
            <li key={job.job_id} className="space-y-1 border-t border-slate-200 pt-2 first:border-0 first:pt-0 dark:border-slate-800">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={job.status} />
                <span>{formatDateTime(job.created_at)}</span>
                {index === 0 && <span className="text-xs text-slate-600 dark:text-slate-400">latest</span>}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <ProblemIndicator count={job.problem_count} />
                {viewing ? (
                  <span className="font-medium">Shown below</span>
                ) : (
                  finished && (
                    <button type="button" onClick={() => onView(job.job_id)} className="text-sky-700 underline dark:text-sky-400">
                      View this analysis
                    </button>
                  )
                )}
              </div>
              {job.error && (
                <p className="text-xs text-rose-800 dark:text-rose-300">
                  {job.error.message} <span className="font-mono">({job.error.code})</span>
                </p>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
