import { useState, type FormEvent } from "react";

import { ApiError, errorMessage, updateRecordReview } from "../../api/client";
import { REVIEW_STATES, type Provenance, type ReviewState } from "../../api/types";
import { REVIEW_LABELS, formatDateTime } from "../../lib/format";
import { ErrorBanner } from "../Messages";
import { ReviewBadge } from "../ReviewBadge";
import { ConflictNotice, conflictDetails, type CurrentReview } from "./ConflictNotice";
import { useDirty, useReviewContext } from "./ReviewContext";

const FIELD = "block w-full rounded-md border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-800";

/** Review of one evidence record (M2-2). Separate from the artifact's review; never changes classification. */
export function RecordReview({ provenance }: { provenance: Provenance }) {
  const context = useReviewContext();
  const [saved, setSavedReview] = useState<CurrentReview>({
    state: provenance.review_state,
    analyst_notes: provenance.analyst_notes,
    updated_at: provenance.review_updated_at,
  });
  const [editing, setEditing] = useState(false);
  const [state, setState] = useState<ReviewState>(saved.state);
  const [notes, setNotes] = useState(saved.analyst_notes);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<CurrentReview | null>(null);
  const dirty = editing && (state !== saved.state || notes !== saved.analyst_notes);
  useDirty(`record:${provenance.evidence_id}`, dirty);

  if (!context) return null;
  const artifactId = context.artifactId;

  async function save(expectedUpdatedAt: string | null) {
    setBusy(true);
    setError(null);
    setConflict(null);
    try {
      const result = await updateRecordReview(artifactId, provenance.evidence_id, state, notes, expectedUpdatedAt);
      setSavedReview({ state: result.review_state, analyst_notes: result.analyst_notes, updated_at: result.review_updated_at });
      setEditing(false);
      context?.reviewSaved();
    } catch (err) {
      const current = err instanceof ApiError && err.code === "REVIEW_CONFLICT" ? conflictDetails(err.details) : null;
      if (current) setConflict(current);
      else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void save(saved.updated_at);
  }

  return (
    <div className="mt-2 space-y-2 border-t border-slate-200 pt-2 dark:border-slate-800">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-slate-700 dark:text-slate-300">Your review of this section:</span>
        <ReviewBadge state={saved.state} />
        {saved.updated_at && <span>{formatDateTime(saved.updated_at)}</span>}
        {!editing && (
          <button
            type="button"
            onClick={() => {
              setState(saved.state);
              setNotes(saved.analyst_notes);
              setEditing(true);
            }}
            className="text-sky-700 underline dark:text-sky-400"
          >
            {saved.updated_at ? "Edit review" : "Review this section"}
          </button>
        )}
      </div>
      {!editing && saved.analyst_notes && <p className="whitespace-pre-wrap">{saved.analyst_notes}</p>}
      {editing && (
        <form onSubmit={onSubmit} className="space-y-2" aria-label={`Review of ${provenance.stage}`}>
          <label className="block space-y-1">
            <span>Review state</span>
            <select value={state} onChange={(event) => setState(event.target.value as ReviewState)} className={FIELD}>
              {REVIEW_STATES.map((value) => (
                <option key={value} value={value}>
                  {REVIEW_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1">
            <span>Notes on this section</span>
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} maxLength={20000} className={FIELD} />
          </label>
          {conflict && (
            <ConflictNotice
              current={conflict}
              onUseCurrent={() => {
                setSavedReview(conflict);
                setState(conflict.state);
                setNotes(conflict.analyst_notes);
                setConflict(null);
              }}
              onOverwrite={() => void save(conflict.updated_at)}
            />
          )}
          {error && <ErrorBanner message={error} />}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-slate-900 px-2 py-1 font-medium text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
            >
              Save section review
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setEditing(false);
                setConflict(null);
                setError(null);
              }}
              className="rounded-md border border-slate-300 px-2 py-1 dark:border-slate-700"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
