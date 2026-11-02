import { Link } from "react-router";

import { contentUrl } from "../../api/client";
import type { DuplicateMatch, DuplicatesSection, MatchType } from "../../api/types";
import { formatPercent } from "../../lib/format";
import { Panel } from "../Panel";

const MATCH_LABELS: Record<MatchType, string> = {
  exact_file: "Same file (identical bytes)",
  visually_identical: "Visually identical (pHash distance 0)",
  near: "Similar",
};

export function DuplicatesPanel({ section }: { section: DuplicatesSection | null }) {
  return (
    <Panel title="Duplicate search (local library)" provenance={section?.provenance ?? null}>
      {section && (
        <>
          {section.matches.length === 0 ? (
            <p>No matching images in the local library.</p>
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
          </p>
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
          {MATCH_LABELS[match.match_type]} · distance {match.distance}/64 · similarity {formatPercent(match.similarity)}
        </p>
      </div>
    </li>
  );
}
