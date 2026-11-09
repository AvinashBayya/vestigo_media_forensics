import type { ForensicIndicatorsSection } from "../../api/types";
import { Panel } from "../Panel";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";

function Series({ label, series }: { label: string; series: Record<string, unknown> }) {
  const keys = ["count", "mean", "standard_deviation", "minimum", "median", "maximum"];
  const present = keys.filter((key) => series[key] !== undefined);
  if (present.length === 0) return null;
  return (
    <p>
      <span className="font-medium">{label}:</span>{" "}
      {present.map((key) => `${key.replace(/_/g, " ")} ${String(series[key])}`).join(" · ")}
    </p>
  );
}

/** Encoding and pixel measurements (Pass 2). Numbers with methods, never editing verdicts. */
export function ForensicIndicatorsPanel({ section }: { section: ForensicIndicatorsSection | null }) {
  const video = section?.video_statistics ?? {};
  return (
    <Panel title="Forensic indicators" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <p className={MUTED}>
            These describe how the file was encoded. They change whenever media is re-saved, resized,
            or passed through a platform, and stay unremarkable in files that were edited heavily, so
            no threshold separates "edited" from "original" anywhere in Vestigo.
          </p>

          {section.quantization_tables.length > 0 && (
            <div>
              <h3 className="font-medium">JPEG quantisation tables</h3>
              <ul aria-label="Quantisation tables" className="mt-1 space-y-1">
                {section.quantization_tables.map((table) => (
                  <li key={table.index}>
                    Table {table.index} ({table.precision}-bit) ·{" "}
                    {table.implied_quality != null
                      ? `implies quality ${table.implied_quality} for the last save`
                      : "no quality could be implied"}
                    {table.matches_standard && " · exactly the standard table"}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(section.decoded_width || section.declared_width) && (
            <div>
              <h3 className="font-medium">Dimensions</h3>
              <p>
                Decoded {section.decoded_width ?? "—"}×{section.decoded_height ?? "—"}
                {section.declared_width != null &&
                  ` · metadata declares ${section.declared_width}×${section.declared_height ?? "—"}`}
              </p>
              {section.dimensions_match === false && (
                <p className="text-amber-900 dark:text-amber-200">
                  Declared and decoded dimensions differ. Recorded as found — cropping tools,
                  resizers, and metadata editors all cause this.
                </p>
              )}
            </div>
          )}

          {section.channel_statistics.length > 0 && (
            <div>
              <h3 className="font-medium">Channel statistics</h3>
              <ul aria-label="Channel statistics" className="mt-1 space-y-0.5">
                {section.channel_statistics.map((entry, index) => (
                  <li key={index}>
                    <span className="font-medium">{String(entry.channel)}</span> · mean{" "}
                    {String(entry.mean)} · sd {String(entry.standard_deviation)} · range{" "}
                    {String(entry.minimum)}–{String(entry.maximum)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {Object.keys(video).length > 0 && (
            <div>
              <h3 className="font-medium">Video encoding</h3>
              <p className={MUTED}>
                {String(video.packets_examined ?? 0)} packets examined ·{" "}
                {String(video.keyframe_count ?? 0)} keyframes
              </p>
              <Series
                label="Keyframe spacing (seconds)"
                series={(video.keyframe_interval_seconds as Record<string, unknown>) ?? {}}
              />
              <Series
                label="Packet size (bytes)"
                series={(video.packet_size_bytes as Record<string, unknown>) ?? {}}
              />
            </div>
          )}

          {section.notes.map((note) => (
            <p key={note} className={MUTED}>
              {note}
            </p>
          ))}
          {section.warnings.map((warning) => (
            <p key={warning} className="text-amber-900 dark:text-amber-200">
              {warning}
            </p>
          ))}
        </>
      )}
    </Panel>
  );
}
