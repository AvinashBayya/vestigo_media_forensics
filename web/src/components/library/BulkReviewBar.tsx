import { useState } from "react";

import { bulkReview, errorMessage } from "../../api/client";
import { REVIEW_STATES, type BulkReviewResult, type ReviewState } from "../../api/types";
import { REVIEW_LABELS } from "../../lib/format";
import { ConfirmDialog } from "../ConfirmDialog";

export const BULK_REVIEW_LIMIT = 200;

export type BulkOutcome = { kind: "success"; result: BulkReviewResult } | { kind: "error"; message: string };

interface BulkReviewBarProps {
  selectedIds: string[];
  onClear: () => void;
  onDone: (outcome: BulkOutcome) => void;
}

/** Sets one review state on the selected artifacts, after explicit confirmation (M2-5). */
export function BulkReviewBar({ selectedIds, onClear, onDone }: BulkReviewBarProps) {
  const [state, setState] = useState<ReviewState>("REVIEWED");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const count = selectedIds.length;
  const tooMany = count > BULK_REVIEW_LIMIT;

  async function apply() {
    setBusy(true);
    try {
      onDone({ kind: "success", result: await bulkReview(selectedIds, state) });
    } catch (err) {
      onDone({ kind: "error", message: errorMessage(err) });
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <div
      role="region"
      aria-label="Bulk review"
      className="flex flex-wrap items-center gap-3 rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
    >
      <span className="font-medium">{count === 1 ? "1 artifact selected" : `${count} artifacts selected`}</span>
      <label className="inline-flex items-center gap-2">
        Set review state to
        <select
          value={state}
          onChange={(event) => setState(event.target.value as ReviewState)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
        >
          {REVIEW_STATES.map((value) => (
            <option key={value} value={value}>
              {REVIEW_LABELS[value]}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        disabled={tooMany}
        onClick={() => setConfirming(true)}
        className="rounded-md bg-slate-900 px-3 py-1 font-medium text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
      >
        Apply…
      </button>
      <button type="button" onClick={onClear} className="text-sky-700 underline dark:text-sky-400">
        Clear selection
      </button>
      {tooMany && <span className="text-rose-700 dark:text-rose-400">Select at most {BULK_REVIEW_LIMIT} artifacts.</span>}
      {confirming && (
        <ConfirmDialog
          title={`Set ${count === 1 ? "1 artifact" : `${count} artifacts`} to ${REVIEW_LABELS[state]}?`}
          confirmLabel={busy ? "Applying…" : `Set to ${REVIEW_LABELS[state]}`}
          busy={busy}
          onCancel={() => setConfirming(false)}
          onConfirm={apply}
        >
          <p>
            Each selected artifact's review state becomes {REVIEW_LABELS[state]}, and the change is recorded in its
            review history. Analyst notes are not changed.
          </p>
          <p>If any selected artifact no longer exists, nothing is changed.</p>
        </ConfirmDialog>
      )}
    </div>
  );
}

export function describeBulkResult(result: BulkReviewResult): string {
  const label = REVIEW_LABELS[result.state];
  const updated = result.updated.length;
  const unchanged = result.unchanged.length;
  const main = `Set ${updated === 1 ? "1 artifact" : `${updated} artifacts`} to ${label}.`;
  if (!unchanged) return main;
  return `${main} ${unchanged === 1 ? "1 was" : `${unchanged} were`} already ${label}.`;
}
