import { Link } from "react-router";

import { listArtifacts } from "../api/client";
import { REVIEW_LABELS, formatBytes, formatDateTime } from "../lib/format";
import { useApiResource } from "../lib/useApiResource";
import { ErrorState, TableSkeleton } from "./States";
import { StatusBadge } from "./StatusBadge";

export function RecentArtifacts() {
  const { data, error, reload } = useApiResource(() => listArtifacts({ limit: 5 }), "recent");
  const items = data?.items ?? null;

  if (error) return <ErrorState error={error} onRetry={reload} title="Recent uploads could not be loaded." />;
  if (items === null) return <TableSkeleton rows={3} label="Loading recent uploads" />;
  if (items.length === 0) return <p className="text-sm text-slate-600 dark:text-slate-400">No uploads yet.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-600 dark:text-slate-400">
          <tr>
            <th className="py-2 pr-3 font-medium">File</th>
            <th className="py-2 pr-3 font-medium">Size</th>
            <th className="py-2 pr-3 font-medium">Uploaded</th>
            <th className="py-2 pr-3 font-medium">Analysis</th>
            <th className="py-2 font-medium">Review</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.artifact_id} className="border-t border-slate-200 dark:border-slate-800">
              <td className="py-2 pr-3">
                <Link to={`/artifacts/${item.artifact_id}`} className="text-sky-700 underline dark:text-sky-400">
                  {item.filename}
                </Link>
              </td>
              <td className="py-2 pr-3">{formatBytes(item.size_bytes)}</td>
              <td className="py-2 pr-3">{formatDateTime(item.created_at)}</td>
              <td className="py-2 pr-3">
                {item.latest_job_status ? <StatusBadge status={item.latest_job_status} /> : "Not analysed"}
              </td>
              <td className="py-2">{REVIEW_LABELS[item.review_state]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
