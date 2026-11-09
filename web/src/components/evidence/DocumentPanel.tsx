import { derivedContentUrl } from "../../api/client";
import type { PdfImagesSection, PdfStructureSection, PdfTextSection } from "../../api/types";
import { formatBytes } from "../../lib/format";
import { Panel } from "../Panel";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";

const MARKER_LABELS: Record<string, string> = {
  encryption_dictionary: "Encryption dictionary",
  javascript: "JavaScript",
  javascript_action: "JavaScript action",
  open_action: "Automatic action on open",
  additional_actions: "Additional actions",
  launch_action: "Launch action",
  embedded_file: "Embedded file",
  file_specification: "File specification",
  interactive_form: "Interactive form",
  xfa_form: "XFA form",
  signature_byte_range: "Signature byte range",
  object_stream: "Compressed object stream",
  uri_action: "Link to a URL",
};

/** What the PDF declares about itself (Pass 2). Structural facts, nothing validated. */
export function PdfStructurePanel({ section }: { section: PdfStructureSection | null }) {
  return (
    <Panel title="Document structure" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
            {[
              ["PDF version", section.pdf_version ?? "not readable"],
              ["Pages declared", String(section.page_count)],
              ["Indirect objects", String(section.object_count)],
              ["Saves (%%EOF markers)", String(section.eof_markers)],
              ["Encrypted", section.encrypted ? "declared" : "no"],
              ["Signature dictionaries", String(section.signature_count)],
              ["Linearised for web", section.linearized ? "yes" : "no"],
            ].map(([term, value]) => (
              <div key={term} className="contents">
                <dt className="font-medium">{term}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>

          {section.incremental_updates > 0 && (
            <p className={MUTED}>
              The file was saved {section.eof_markers} times ({section.incremental_updates}{" "}
              incremental update{section.incremental_updates === 1 ? "" : "s"}). This is how PDFs are
              normally annotated and re-saved; it is not a sign of tampering.
            </p>
          )}

          {section.signature_count > 0 && (
            <p className="text-amber-900 dark:text-amber-200">
              The document contains {section.signature_count} signature structure
              {section.signature_count === 1 ? "" : "s"}. Vestigo does not validate PDF signatures,
              check certificates, or establish signer trust — presence is all that is reported here.
            </p>
          )}

          {Object.keys(section.markers).length > 0 && (
            <div>
              <h3 className="font-medium">Features present</h3>
              <ul aria-label="Document features" className="mt-1 flex flex-wrap gap-1">
                {Object.entries(section.markers).map(([marker, count]) => (
                  <li
                    key={marker}
                    className="rounded bg-slate-100 px-1.5 py-0.5 text-xs dark:bg-slate-800"
                  >
                    {MARKER_LABELS[marker] ?? marker} ×{count}
                  </li>
                ))}
              </ul>
              <p className={`mt-1 ${MUTED}`}>
                Presence counts only. Ordinary documents from ordinary software contain JavaScript,
                actions, embedded files, and forms routinely, so none of these is a finding of
                wrongdoing.
              </p>
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

/** Provisional text from the document's content streams (Pass 2). Never a transcription. */
export function PdfTextPanel({ section }: { section: PdfTextSection | null }) {
  return (
    <Panel title="Text in document" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
            <span className="font-medium">Provisional:</span> read from content-stream operators
            without font mapping, so characters can be wrong, reordered, or missing. Not a verified
            transcription, and the order is operator order rather than reading order.
          </p>
          {section.text ? (
            <>
              <pre className="max-h-80 overflow-auto rounded-md bg-slate-100 p-2 font-mono text-sm whitespace-pre-wrap dark:bg-slate-800">
                {section.text}
              </pre>
              <p className={MUTED}>
                {section.character_count.toLocaleString()} characters from{" "}
                {section.streams_read} text stream{section.streams_read === 1 ? "" : "s"}
                {section.streams_skipped > 0 && ` · ${section.streams_skipped} non-text stream(s) skipped`}
                {section.streams_failed > 0 && ` · ${section.streams_failed} could not be decompressed`}
              </p>
            </>
          ) : (
            <p>
              No text operators were readable. This does <strong>not</strong> mean the pages are
              blank — the document may be image-only or use structures Vestigo does not expand.
            </p>
          )}
          {section.notes.map((note) => (
            <p key={note} className={MUTED}>
              {note}
            </p>
          ))}
        </>
      )}
    </Panel>
  );
}

/** Images embedded in the document, copied out byte for byte. Not rendered pages. */
export function PdfImagesPanel({
  artifactId,
  section,
}: {
  artifactId: string;
  section: PdfImagesSection | null;
}) {
  return (
    <Panel title="Images embedded in the document" provenance={section?.provenance ?? null}>
      {section && (
        <>
          {section.images.length === 0 ? (
            <p>No JPEG-compressed images were extracted from this document.</p>
          ) : (
            <ul
              aria-label="Embedded images"
              className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
            >
              {section.images.map((image) => (
                <li key={image.index} className="min-w-0 space-y-1">
                  {image.derived_file_id && (
                    <div className="flex aspect-video w-full items-center justify-center overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
                      <img
                        src={derivedContentUrl(artifactId, image.derived_file_id)}
                        alt={`Embedded image ${image.index}`}
                        loading="lazy"
                        className="max-h-full max-w-full object-contain"
                      />
                    </div>
                  )}
                  <p className={MUTED}>
                    #{image.index} · {image.encoding} · {formatBytes(image.size_bytes)}
                    {image.width && image.height && ` · ${image.width}×${image.height}`}
                  </p>
                </li>
              ))}
            </ul>
          )}
          <p className={MUTED}>
            These are images stored inside the document, copied out byte for byte — not rendered
            pages. Vestigo has no PDF renderer, so page appearance is not reproduced, and images in
            other encodings are counted but not extracted because rebuilding them would mean
            re-encoding.
          </p>
          {section.notes.map((note) => (
            <p key={note} className={MUTED}>
              {note}
            </p>
          ))}
        </>
      )}
    </Panel>
  );
}
