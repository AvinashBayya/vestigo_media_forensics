import { Link } from "react-router";

import { contentUrl } from "../../api/client";
import type { DuplicateMatch, DuplicatesSection, MatchType } from "../../api/types";
import { formatDateTime, formatPercent, formatSeconds } from "../../lib/format";
import { Panel } from "../Panel";

const MATCH_LABELS: Record<MatchType, string> = {
  exact_file: "Same file (identical bytes)",
  visually_identical: "Visually identical (pHash distance 0)",
  near: "Similar",
};

interface DuplicatesPanelProps {
  section: DuplicatesSection | null;
  /** Library artifacts uploaded after this search, when this is the latest analysis. */
  addedSince?: number | null;
  onRerun?: () => void;
}

export function DuplicatesPanel({ section, addedSince, onRerun }: DuplicatesPanelProps) {
  return (
    <Panel title="Duplicate search (local library)" provenance={section?.provenance ?? null}>
      {section && (
        <>
          {section.matches.length === 0 ? (
            <p>
              No match among the {section.library_size ?? 0} other artifacts that were in the local library when
              this analysis ran ({formatDateTime(section.provenance.completed_at)}). Images added later are not
              included. Run the analysis again to search the current library.
            </p>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {section.matches.map((match) => (
                <MatchRow key={match.artifact_id} match={match} />
              ))}
            </ul>
          )}
          <p className="text-xs text-slate-600 dark:text-slate-400">
            Searched {section.library_size ?? 0} other artifacts ({section.compared ?? 0} with a perceptual hash).
            Threshold: Hamming distance ≤ {section.threshold} of 64 bits.
            {section.excluded_count ? ` ${section.excluded_count} excluded from duplicate search and not compared.` : ""}
          </p>
          {addedSince ? (
            <p className="rounded-md bg-sky-50 px-3 py-2 text-sm text-sky-900 dark:bg-sky-950 dark:text-sky-100">
              {addedSince === 1 ? "1 artifact was" : `${addedSince} artifacts were`} added to the library after this search
              and {addedSince === 1 ? "was" : "were"} not compared.{" "}
              {onRerun && (
                <button type="button" onClick={onRerun} className="font-medium underline">
                  Run analysis again
                </button>
              )}
            </p>
          ) : null}
        </>
      )}
    </Panel>
  );
}

function MatchRow({ match }: { match: DuplicateMatch }) {
  return (
    <li className="flex items-center gap-3 py-2">
      {match.available ? (
        <img
          src={contentUrl(match.artifact_id)}
          alt=""
          className="h-12 w-12 shrink-0 rounded bg-slate-100 object-cover dark:bg-slate-800"
        />
      ) : (
        <div className="h-12 w-12 shrink-0 rounded bg-slate-100 dark:bg-slate-800" />
      )}
      <div className="min-w-0">
        {match.available ? (
          <Link to={`/artifacts/${match.artifact_id}`} className="font-medium text-sky-700 underline dark:text-sky-400">
            {match.filename}
          </Link>
        ) : (
          <span className="text-slate-600 dark:text-slate-400">Deleted artifact</span>
        )}
        <p className="text-xs text-slate-600 dark:text-slate-400">
          {match.media_type === "video" && "Video · "}
          {MATCH_LABELS[match.match_type]} · distance {match.distance}/64 · similarity {formatPercent(match.similarity)}
        </p>
        {match.frame_matches && match.frame_matches.length > 0 && (
          <details className="text-xs text-slate-600 dark:text-slate-400">
            <summary className="cursor-pointer">
              {match.matched_frame_count === 1 ? "1 matching frame pair" : `${match.matched_frame_count} matching frame pairs`}
            </summary>
            <ul className="mt-1 space-y-0.5 font-mono">
              {match.frame_matches.map((pair, index) => (
                <li key={index}>
                  {pair.query_timestamp === null ? "this image" : `this video at ${formatSeconds(pair.query_timestamp)}`}
                  {" ↔ "}
                  {pair.matched_timestamp === null ? "matched image" : `matched video at ${formatSeconds(pair.matched_timestamp)}`}
                  {` · distance ${pair.distance}/64`}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </li>
  );
}
