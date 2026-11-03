import type { EvidenceReport, JobHistoryItem, Provenance } from "../api/types";
import { STAGE_LABELS } from "../lib/format";
import { sectionAnchor } from "./Panel";
import { StatusBadge } from "./StatusBadge";

const SECTIONS = ["hashes", "metadata", "c2pa", "perceptual_hash", "ocr", "duplicates"] as const;

/**
 * Lists every check of the shown analysis that failed or finished with warnings, with its first error,
 * linking to the section. Tool failures are surfaced here, never hidden (04 §6).
 */
export function ProblemsSummary({ report, job }: { report: EvidenceReport; job: JobHistoryItem | null }) {
  const problems = SECTIONS.map((stage) => report[stage]?.provenance)
    .filter((p): p is Provenance => p !== undefined && (p.status === "failed" || p.status === "partial"));
  if (problems.length === 0 && !job?.error) return null;

  return (
    <section aria-label="Problems in this analysis" className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
      <h2 className="font-medium">
        {problems.length + (job?.error ? 1 : 0) === 1
          ? "1 problem in this analysis"
          : `${problems.length + (job?.error ? 1 : 0)} problems in this analysis`}
      </h2>
      <ul className="space-y-1">
        {job?.error && (
          <li>
            The analysis stopped: {job.error.message} <span className="font-mono text-xs">({job.error.code})</span>
          </li>
        )}
        {problems.map((provenance) => (
          <li key={provenance.stage} className="flex flex-wrap items-center gap-2">
            <a href={`#${sectionAnchor(provenance.stage)}`} className="font-medium underline">
              {STAGE_LABELS[provenance.stage] ?? provenance.stage}
            </a>
            <StatusBadge status={provenance.status} />
            {provenance.errors[0] && (
              <span>
                {provenance.errors[0].message} <span className="font-mono text-xs">({provenance.errors[0].type})</span>
                {provenance.errors.length > 1 && ` and ${provenance.errors.length - 1} more`}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
