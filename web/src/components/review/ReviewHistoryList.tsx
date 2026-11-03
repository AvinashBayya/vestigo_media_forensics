import { getReviewHistory } from "../../api/client";
import type { ReviewEvent } from "../../api/types";
import { REVIEW_LABELS, STAGE_LABELS, formatDateTime } from "../../lib/format";
import { useApiResource } from "../../lib/useApiResource";
import { ErrorState } from "../States";

function originLabel(event: ReviewEvent): string {
  if (event.origin === "bulk") return "Bulk change";
  if (event.origin === "record") return `Evidence: ${STAGE_LABELS[event.stage ?? ""] ?? event.stage ?? "record"}`;
  return "Artifact review";
}

/** The append-only review history, newest first, with full note text. */
export function ReviewHistoryList({ artifactId, version }: { artifactId: string; version: number }) {
  const { data, error, reload } = useApiResource(() => getReviewHistory(artifactId), `${artifactId}:${version}`);
  const events = data?.events ?? [];

  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-slate-700 dark:text-slate-300">
        Review history{data ? ` (${events.length})` : ""}
      </summary>
      <div className="mt-2 space-y-2">
        {error && <ErrorState error={error} onRetry={reload} title="The review history could not be loaded." />}
        {data && events.length === 0 && <p className="text-slate-600 dark:text-slate-400">No review changes yet.</p>}
        <ol className="space-y-2">
          {events.map((event) => (
            <li key={event.event_id} className="border-l-2 border-slate-200 pl-2 dark:border-slate-700">
              <p className="font-medium">
                {originLabel(event)}: {REVIEW_LABELS[event.from_state]} → {REVIEW_LABELS[event.to_state]}
              </p>
              <p className="text-slate-600 dark:text-slate-400">{formatDateTime(event.created_at)}</p>
              {event.notes_after !== event.notes_before && (
                <div className="mt-1 space-y-1">
                  <p className="whitespace-pre-wrap">{event.notes_after || "(notes cleared)"}</p>
                  {event.notes_before && (
                    <details>
                      <summary className="cursor-pointer text-slate-600 dark:text-slate-400">Previous notes</summary>
                      <p className="mt-1 whitespace-pre-wrap text-slate-600 dark:text-slate-400">{event.notes_before}</p>
                    </details>
                  )}
                </div>
              )}
            </li>
          ))}
        </ol>
      </div>
    </details>
  );
}
