import type { ReviewState } from "../../api/types";
import { REVIEW_LABELS } from "../../lib/format";

export interface CurrentReview {
  state: ReviewState;
  analyst_notes: string;
  updated_at: string | null;
}

/** Shown when the review changed elsewhere (e.g. another tab) after this form was opened. */
export function ConflictNotice({
  current,
  onUseCurrent,
  onOverwrite,
}: {
  current: CurrentReview;
  onUseCurrent: () => void;
  onOverwrite: () => void;
}) {
  return (
    <div role="alert" className="space-y-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
      <p className="font-medium">This review was changed elsewhere since you opened it. Nothing was saved.</p>
      <p>
        Saved review: {REVIEW_LABELS[current.state]}
        {current.analyst_notes ? "" : ", no notes"}.
      </p>
      {current.analyst_notes && <p className="whitespace-pre-wrap">Saved notes: {current.analyst_notes}</p>}
      <p>Your version is still in the form below.</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onUseCurrent} className="rounded-md border border-amber-400 px-2 py-1 font-medium">
          Use the saved review
        </button>
        <button type="button" onClick={onOverwrite} className="rounded-md border border-amber-400 px-2 py-1 font-medium">
          Save my version over it
        </button>
      </div>
    </div>
  );
}

export function conflictDetails(details: Record<string, unknown>): CurrentReview | null {
  const current = details.current as CurrentReview | undefined;
  return current && typeof current.state === "string" ? current : null;
}
