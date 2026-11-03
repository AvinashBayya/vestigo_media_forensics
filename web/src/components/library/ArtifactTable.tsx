import { Link } from "react-router";

import type { ArtifactListItem, ArtifactSort, SortOrder } from "../../api/types";
import { formatBytes, formatDateTime } from "../../lib/format";
import { ReviewBadge } from "../ReviewBadge";
import { StatusBadge } from "../StatusBadge";

interface ArtifactTableProps {
  items: ArtifactListItem[];
  sort: ArtifactSort;
  order: SortOrder;
  onSort: (sort: ArtifactSort) => void;
}

const MUTED = "text-xs text-slate-600 dark:text-slate-400";

export function ArtifactTable({ items, sort, order, onSort }: ArtifactTableProps) {
  const header = (key: ArtifactSort, label: string) => (
    <th scope="col" aria-sort={sort === key ? (order === "asc" ? "ascending" : "descending") : "none"} className="py-2 pr-3 font-medium">
      <button type="button" onClick={() => onSort(key)} className="inline-flex items-center gap-1 hover:underline">
        {label}
        <span aria-hidden="true">{sort === key ? (order === "asc" ? "▲" : "▼") : ""}</span>
      </button>
    </th>
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-600 dark:text-slate-400">
          <tr>
            {header("filename", "File")}
            {header("created_at", "Uploaded")}
            {header("size_bytes", "Size")}
            <th scope="col" className="py-2 pr-3 font-medium">
              Analysis
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Problems
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              Duplicates
            </th>
            {header("review_state", "Review")}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.artifact_id} className="border-t border-slate-200 align-top dark:border-slate-800">
              <td className="py-2 pr-3">
                <Link to={`/artifacts/${item.artifact_id}`} className="break-all text-sky-700 underline dark:text-sky-400">
                  {item.filename}
                </Link>
                {!item.in_duplicate_library && <p className={MUTED}>Excluded from duplicate search</p>}
              </td>
              <td className="py-2 pr-3 whitespace-nowrap">{formatDateTime(item.created_at)}</td>
              <td className="py-2 pr-3 whitespace-nowrap">{formatBytes(item.size_bytes)}</td>
              <td className="py-2 pr-3">
                {item.latest_job_status ? <StatusBadge status={item.latest_job_status} /> : <span className={MUTED}>Not analysed</span>}
              </td>
              <td className="py-2 pr-3">
                <ProblemIndicator count={item.problem_count} />
              </td>
              <td className="py-2 pr-3">
                <DuplicateIndicator item={item} />
              </td>
              <td className="py-2">
                <ReviewBadge state={item.review_state} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ProblemIndicator({ count }: { count: number | null }) {
  if (count === null) return <span className={MUTED}>—</span>;
  if (count === 0) return <span className={MUTED}>None</span>;
  return (
    <span className="inline-block rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium whitespace-nowrap text-amber-900 dark:bg-amber-900 dark:text-amber-100">
      {count === 1 ? "1 problem" : `${count} problems`}
    </span>
  );
}

function DuplicateIndicator({ item }: { item: ArtifactListItem }) {
  if (item.duplicate_match_count === null) return <span className={MUTED}>Not searched</span>;
  return (
    <div>
      <span>{item.duplicate_match_count === 1 ? "1 match" : `${item.duplicate_match_count} matches`}</span>
      {item.added_since_analysis !== null && item.added_since_analysis > 0 && (
        <p className={MUTED}>{item.added_since_analysis} added since search</p>
      )}
    </div>
  );
}
