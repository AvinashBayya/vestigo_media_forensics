import type { StructuralSection } from "../../api/types";
import { formatBytes } from "../../lib/format";
import { Panel } from "../Panel";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";

const FINDING_LABELS: Record<string, string> = {
  trailing_data: "Data after the end of the format",
  trailing_padding: "Repeated bytes at the end of the file",
  embedded_signature: "File signature inside the file",
  large_comment_segment: "Large comment segment",
  large_text_chunk: "Large text chunk",
  chunk_crc_mismatch: "Chunk checksum does not match",
  truncated_chunk: "Chunk declares more data than the file holds",
  invalid_box_size: "Container box declares an impossible size",
  box_past_end: "Container box extends past the end of the file",
  declared_size_past_end: "Declared size runs past the end of the file",
  missing_end_marker: "No end marker found",
};

/** Structure and byte statistics (Pass 2): placed facts and measurements, never a verdict. */
export function StructuralPanel({ section }: { section: StructuralSection | null }) {
  const nothingFound = section !== null && section.findings.length === 0;
  return (
    <Panel title="Structure and hidden-data checks" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <p className={MUTED}>
            {section.container ? `Read as ${section.container}. ` : ""}
            {formatBytes(section.file_size)}
            {section.logical_end !== null &&
              ` · the format's own data ends at byte ${section.logical_end.toLocaleString()}`}
            {section.binwalk_ran && " · binwalk signature scan included"}
          </p>

          {nothingFound ? (
            <p>
              Nothing structurally unusual was found. That is <strong>not</strong> a finding that the
              file is clean: well-implemented concealment is undetectable by these checks.
            </p>
          ) : (
            <ul aria-label="Structural findings" className="space-y-1">
              {section.findings.map((finding, index) => (
                <li key={`${finding.kind}-${finding.offset}-${index}`} className="flex flex-wrap gap-2">
                  <span className="font-medium">{FINDING_LABELS[finding.kind] ?? finding.kind}</span>
                  <span className={`font-mono ${MUTED}`}>
                    offset {finding.offset.toLocaleString()}
                    {finding.size != null && ` · ${formatBytes(finding.size)}`}
                  </span>
                  {finding.detail && <span className="min-w-0 break-words">{finding.detail}</span>}
                </li>
              ))}
            </ul>
          )}

          {section.trailing_bytes > 0 && (
            <p className={MUTED}>
              {formatBytes(section.trailing_bytes)} follow the format's data. Cameras, editors, and
              publishing tools append data routinely, so this is a place to look rather than a
              conclusion.
            </p>
          )}

          {section.measurements.length > 0 && (
            <div>
              <h3 className="font-medium">Measurements</h3>
              <ul aria-label="Byte measurements" className="mt-1 space-y-1">
                {section.measurements.map((measurement) => (
                  <li key={measurement.name}>
                    <span className="font-mono">{measurement.name}</span>{" "}
                    <span className="font-medium">{measurement.value}</span>
                    <p className={MUTED}>
                      {measurement.method}
                      {measurement.note && ` ${measurement.note}`}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {section.inventory.length > 0 && (
            <details className={MUTED}>
              <summary className="cursor-pointer">
                Declared segments, chunks, or boxes ({section.inventory.length})
              </summary>
              <ul className="mt-1 space-y-0.5 font-mono">
                {section.inventory.slice(0, 60).map((entry, index) => (
                  <li key={index}>{JSON.stringify(entry)}</li>
                ))}
              </ul>
            </details>
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
