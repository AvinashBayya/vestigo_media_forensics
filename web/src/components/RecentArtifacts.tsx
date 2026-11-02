import { useEffect, useState } from "react";
import { Link } from "react-router";

import { errorMessage, listArtifacts } from "../api/client";
import type { ArtifactSummary } from "../api/types";
import { REVIEW_LABELS, formatBytes, formatDateTime } from "../lib/format";
import { ErrorBanner } from "./Messages";
import { StatusBadge } from "./StatusBadge";

export function RecentArtifacts() {
  const [items, setItems] = useState<ArtifactSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listArtifacts(20)
      .then((list) => !cancelled && setItems(list.items))
      .catch((err) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <ErrorBanner message={error} />;
  if (items === null) return <p className="text-sm text-slate-600">Loading…</p>;
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
