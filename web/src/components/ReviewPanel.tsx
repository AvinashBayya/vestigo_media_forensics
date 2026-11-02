import { useState, type FormEvent } from "react";

import { errorMessage, updateReview } from "../api/client";
import { REVIEW_STATES, type ArtifactDetail, type ReviewState } from "../api/types";
import { REVIEW_LABELS, formatDateTime } from "../lib/format";
import { ErrorBanner } from "./Messages";

interface ReviewPanelProps {
  artifact: ArtifactDetail;
  onSaved: (artifact: ArtifactDetail) => void;
}

export function ReviewPanel({ artifact, onSaved }: ReviewPanelProps) {
  const [state, setState] = useState<ReviewState>(artifact.review.state);
  const [notes, setNotes] = useState(artifact.review.analyst_notes);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      onSaved(await updateReview(artifact.artifact_id, state, notes));
      setSaved(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
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
          className="block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-800"
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
          className="block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-800"
        />
      </label>
      {error && <ErrorBanner message={error} />}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-slate-900 px-3 py-1.5 font-medium text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
        >
          Save review
        </button>
        {saved && (
          <span role="status" className="text-emerald-700 dark:text-emerald-400">
            Saved
          </span>
        )}
      </div>
      <p className="text-xs text-slate-600 dark:text-slate-400">
        Only you set the review state; Vestigo never changes it. Last updated {formatDateTime(artifact.review.updated_at)}.
      </p>
    </form>
  );
}
