import { useState, type FormEvent } from "react";

import { ApiError, errorMessage, updateReview } from "../api/client";
import { REVIEW_STATES, type ArtifactDetail, type ReviewState } from "../api/types";
import { REVIEW_LABELS, formatDateTime } from "../lib/format";
import { ErrorBanner } from "./Messages";
import { ConflictNotice, conflictDetails, type CurrentReview } from "./review/ConflictNotice";
import { useDirty, useReviewContext } from "./review/ReviewContext";
import { ReviewHistoryList } from "./review/ReviewHistoryList";

interface ReviewPanelProps {
  artifact: ArtifactDetail;
  onSaved: (artifact: ArtifactDetail) => void;
}

const FIELD = "block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-800";

export function ReviewPanel({ artifact, onSaved }: ReviewPanelProps) {
  const context = useReviewContext();
  const [state, setState] = useState<ReviewState>(artifact.review.state);
  const [notes, setNotes] = useState(artifact.review.analyst_notes);
  // The saved review this form is based on; sent back so a newer save elsewhere is not overwritten.
  const [base, setBase] = useState<CurrentReview>({
    state: artifact.review.state,
    analyst_notes: artifact.review.analyst_notes,
    updated_at: artifact.review.updated_at,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<CurrentReview | null>(null);
  const dirty = state !== base.state || notes !== base.analyst_notes;
  useDirty("artifact-review", dirty);

  async function save(expectedUpdatedAt: string | null) {
    setSaving(true);
    setSaved(false);
    setError(null);
    setConflict(null);
    try {
      const detail = await updateReview(artifact.artifact_id, state, notes, expectedUpdatedAt ?? undefined);
      setBase({ state: detail.review.state, analyst_notes: detail.review.analyst_notes, updated_at: detail.review.updated_at });
      onSaved(detail);
      setSaved(true);
      context?.reviewSaved();
    } catch (err) {
      const current = err instanceof ApiError && err.code === "REVIEW_CONFLICT" ? conflictDetails(err.details) : null;
      if (current) setConflict(current);
      else setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void save(base.updated_at);
  }

  return (
    <form
      onSubmit={onSubmit}
      className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <h2 className="font-medium">Analyst review</h2>
      <label className="block space-y-1">
        <span className="font-medium">Review state</span>
        <select
          value={state}
          onChange={(event) => {
            setState(event.target.value as ReviewState);
            setSaved(false);
          }}
          className={FIELD}
        >
          {REVIEW_STATES.map((value) => (
            <option key={value} value={value}>
              {REVIEW_LABELS[value]}
            </option>
          ))}
        </select>
      </label>
      <label className="block space-y-1">
        <span className="font-medium">Analyst notes</span>
        <textarea
          value={notes}
          onChange={(event) => {
            setNotes(event.target.value);
            setSaved(false);
          }}
          rows={4}
          maxLength={20000}
          className={FIELD}
        />
      </label>
      {conflict && (
        <ConflictNotice
          current={conflict}
          onUseCurrent={() => {
            setState(conflict.state);
            setNotes(conflict.analyst_notes);
            setBase(conflict);
            setConflict(null);
          }}
          onOverwrite={() => void save(conflict.updated_at)}
        />
      )}
      {error && <ErrorBanner message={error} />}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-slate-900 px-3 py-1.5 font-medium text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
        >
          Save review
        </button>
        {saved && !dirty && (
          <span role="status" className="text-emerald-700 dark:text-emerald-400">
            Saved
          </span>
        )}
        {dirty && <span className="text-amber-700 dark:text-amber-400">Unsaved changes</span>}
      </div>
      <p className="text-xs text-slate-600 dark:text-slate-400">
        Only you set the review state; Vestigo never changes it. Last updated {formatDateTime(base.updated_at)}.
      </p>
      <ReviewHistoryList artifactId={artifact.artifact_id} version={context?.historyVersion ?? 0} />
    </form>
  );
}
