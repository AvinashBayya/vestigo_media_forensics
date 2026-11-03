import { useEffect, useId, useState } from "react";

import type { ReviewState } from "../../api/types";
import { REVIEW_LABELS } from "../../lib/format";
import {
  STATUS_CHOICES,
  TYPE_CHOICES,
  type LibraryState,
  type StatusChoice,
} from "../../lib/libraryState";

export const SEARCH_DEBOUNCE_MS = 300;
const ACTIVE_REVIEW_STATES: ReviewState[] = ["UNREVIEWED", "IN_REVIEW", "REVIEWED", "FLAGGED"];
const CONTROL =
  "rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800";

interface FilterBarProps {
  state: LibraryState;
  counts: Record<ReviewState, number> | null;
  onChange: (changes: Partial<LibraryState>, options?: { replace?: boolean }) => void;
  onClear: () => void;
  filtered: boolean;
}

export function FilterBar({ state, counts, onChange, onClear, filtered }: FilterBarProps) {
  const ids = useId();
  return (
    <div className="space-y-3">
      <SearchBox value={state.q} onSearch={(q) => onChange({ q }, { replace: true })} />
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Review state">
        {ACTIVE_REVIEW_STATES.map((reviewState) => {
          const pressed = state.review.includes(reviewState);
          return (
            <button
              key={reviewState}
              type="button"
              aria-pressed={pressed}
              onClick={() =>
                onChange({
                  review: pressed ? state.review.filter((s) => s !== reviewState) : [...state.review, reviewState],
                })
              }
              className={`rounded-full border px-3 py-1 text-sm ${
                pressed
                  ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                  : "border-slate-300 bg-white hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900"
              }`}
            >
              {REVIEW_LABELS[reviewState]}
              {counts && " "}
              {counts && <span className="text-xs opacity-75">({counts[reviewState]})</span>}
            </button>
          );
        })}
        <label className="ml-1 inline-flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={state.archived}
            onChange={(event) => onChange({ archived: event.target.checked })}
          />
          Show archived
          {counts && " "}
          {counts && <span className="text-xs text-slate-600 dark:text-slate-400">({counts.ARCHIVED})</span>}
        </label>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1 text-sm">
          <span className="block text-xs text-slate-600 dark:text-slate-400">Analysis</span>
          <select
            value={state.status}
            onChange={(event) => onChange({ status: event.target.value as StatusChoice })}
            className={CONTROL}
          >
            {STATUS_CHOICES.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="block text-xs text-slate-600 dark:text-slate-400">File type</span>
          <select
            value={state.type}
            onChange={(event) => onChange({ type: event.target.value as LibraryState["type"] })}
            className={CONTROL}
          >
            {TYPE_CHOICES.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm" htmlFor={`${ids}-from`}>
          <span className="block text-xs text-slate-600 dark:text-slate-400">Uploaded from</span>
          <input
            id={`${ids}-from`}
            type="date"
            value={state.from}
            max={state.to || undefined}
            onChange={(event) => onChange({ from: event.target.value })}
            className={CONTROL}
          />
        </label>
        <label className="space-y-1 text-sm" htmlFor={`${ids}-to`}>
          <span className="block text-xs text-slate-600 dark:text-slate-400">Uploaded to</span>
          <input
            id={`${ids}-to`}
            type="date"
            value={state.to}
            min={state.from || undefined}
            onChange={(event) => onChange({ to: event.target.value })}
            className={CONTROL}
          />
        </label>
        <label className="inline-flex items-center gap-1.5 pb-1.5 text-sm">
          <input
            type="checkbox"
            checked={state.problems}
            onChange={(event) => onChange({ problems: event.target.checked })}
          />
          Has problems
        </label>
        <label className="inline-flex items-center gap-1.5 pb-1.5 text-sm">
          <input
            type="checkbox"
            checked={state.duplicates}
            onChange={(event) => onChange({ duplicates: event.target.checked })}
          />
          Has duplicate matches
        </label>
        {filtered && (
          <button type="button" onClick={onClear} className="pb-1.5 text-sm text-sky-700 underline dark:text-sky-400">
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
}

function SearchBox({ value, onSearch }: { value: string; onSearch: (q: string) => void }) {
  const [text, setText] = useState(value);

  // Follow the URL when it changes from elsewhere (Clear filters, back button).
  useEffect(() => setText(value), [value]);

  useEffect(() => {
    if (text === value) return;
    const timer = window.setTimeout(() => onSearch(text), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [text, value, onSearch]);

  return (
    <label className="block max-w-xl space-y-1 text-sm">
      <span className="font-medium">Search</span>
      <input
        type="search"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Filename, analyst notes, artifact ID, or SHA-256/MD5 prefix"
        className={`block w-full ${CONTROL}`}
      />
    </label>
  );
}
