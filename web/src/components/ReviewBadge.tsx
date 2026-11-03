import type { ReviewState } from "../api/types";
import { REVIEW_LABELS } from "../lib/format";

const STYLES: Record<ReviewState, string> = {
  UNREVIEWED: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  IN_REVIEW: "bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200",
  REVIEWED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
  FLAGGED: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100",
  ARCHIVED: "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
};

/** The analyst's review state. Set only by the analyst; never a judgement by Vestigo. */
export function ReviewBadge({ state }: { state: ReviewState }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${STYLES[state]}`}>
      {REVIEW_LABELS[state]}
    </span>
  );
}
