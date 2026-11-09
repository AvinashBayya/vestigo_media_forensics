import { useCallback, useEffect, useId, useState } from "react";

import { errorMessage, getGeoTools } from "../../api/client";
import type { GeoToolsResponse } from "../../api/types";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";
const BUTTON = "rounded-md border border-slate-300 px-2 py-1 text-sm font-medium dark:border-slate-600";

function kilometres(metres: number): string {
  return metres >= 1000 ? `${(metres / 1000).toFixed(2)} km` : `${Math.round(metres)} m`;
}

/** Local coordinate conversions and geometry (Pass 3). Calculation only, never a location finding. */
export function GeoToolsPanel({ artifactId, refreshKey }: { artifactId: string; refreshKey?: string }) {
  const headingId = useId();
  const [tools, setTools] = useState<GeoToolsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setTools(await getGeoTools(artifactId));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [artifactId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  if (tools !== null && tools.points.length === 0 && error === null) return null;

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-lg border border-slate-200 bg-white shadow-xs dark:border-slate-800 dark:bg-slate-900"
    >
      <header className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <h2 id={headingId} className="font-medium">
          Coordinate tools
        </h2>
      </header>
      <div className="space-y-3 px-4 py-3 text-sm">
        {error ? (
          <div role="alert" className="space-y-2">
            <p className="text-rose-800 dark:text-rose-300">Coordinate tools could not load: {error}</p>
            <button type="button" onClick={() => void load()} className={BUTTON}>
              Retry
            </button>
          </div>
        ) : tools === null ? (
          <p className={MUTED}>Loading…</p>
        ) : (
          <>
            <p className={MUTED}>{tools.notice}</p>

            <ul aria-label="Held coordinates" className="space-y-2">
              {tools.points.map((point, index) => (
                <li key={`${point.source}-${index}`} className="space-y-0.5">
                  <p className="font-medium">{point.source}</p>
                  <dl className="grid grid-cols-[max-content_1fr] gap-x-3">
                    {[
                      ["Decimal", point.formats.decimal],
                      ["DMS", point.formats.degrees_minutes_seconds],
                      ["DDM", point.formats.degrees_decimal_minutes],
                      ["ISO 6709", point.formats.iso6709],
                    ].map(([term, value]) => (
                      <div key={term} className="contents">
                        <dt className={MUTED}>{term}</dt>
                        <dd className="font-mono">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </li>
              ))}
            </ul>

            {tools.pairs.length > 0 && (
              <div>
                <h3 className="font-medium">Between these points</h3>
                <ul aria-label="Distances between points" className="mt-1 space-y-1">
                  {tools.pairs.map((pair, index) => (
                    <li key={index}>
                      {kilometres(pair.distance_metres)} apart, bearing{" "}
                      {pair.bearing_degrees.toFixed(1)}° · <span className={MUTED}>{pair.from_source}</span>{" "}
                      → <span className={MUTED}>{pair.to_source}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <p className={MUTED}>
              {tools.offline_map_available
                ? `Offline map data is configured at ${tools.offline_map_path}.`
                : "No offline map data is configured. Vestigo never downloads map data or tiles."}
            </p>
            <details className={MUTED}>
              <summary className="cursor-pointer">What these numbers are not</summary>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {tools.limitations.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            </details>
          </>
        )}
      </div>
    </section>
  );
}
